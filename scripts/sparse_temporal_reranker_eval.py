"""val_tune driver for the sparse temporal reranker ablation (arms A, F-J).

One thing varies per arm: the retrieval/span method. Every other knob is read
live from tuning/frozen_state.json and never mutated.

Arms
  A  frozen baseline           verbatim question, one PPR, K=4, Method-D span
  F  parser-fixed structured   v3 parser, one PPR, no traversal, Method-D span
  G  safe traversal            F + multi-anchor union + gate + NMS, Method-D
  H  adapter isolation         verbatim question + temporal adapter, Method-D
  I  full retrieval            F + G + adapter, Method-D span
  J  full + adaptive span      identical retrieval to I, adaptive span

Fairness invariants asserted at runtime, not just documented:
  * val_confirm videos are never loaded (hard assert against split_manifest).
  * Answer choices are never read -- this driver never touches a0..a4.
  * Gold spans are used only after retrieval, for scoring.
  * Method-D span is anchored on the VERBATIM question embedding in every arm,
    so a span delta is never confounded with a query-text change (same rule the
    committed A-E ablation used).
  * Exactly one PPR call per question in every arm.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import iris.ingest as iris_ingest  # noqa: E402
import iris.query as iris_query  # noqa: E402
from iris.retrieval_entry import retrieve_for_question  # noqa: E402
from iris.retrieval_entry_v3 import retrieve_v3  # noqa: E402
from iris.temporal_traversal_safe import TraversalPolicy  # noqa: E402
from iris.query_reformulation_v3 import parser_status  # noqa: E402
from eval.metrics import predicted_span_from_frames_peak  # noqa: E402

from part3_tune import (  # noqa: E402
    load_val_tune_questions, make_config, ensure_indexes, load_frozen_state,
    TUNING_DIR,
)

import importlib.util as _importlib_util  # noqa: E402
_NEXTGQA_METRICS_PATH = REPO / "benchmark_runs/paper_setup_20260720T074844Z_1e431b7/scripts/nextgqa_metrics.py"
_spec = _importlib_util.spec_from_file_location("nextgqa_metrics_canonical", _NEXTGQA_METRICS_PATH)
nextgqa_metrics = _importlib_util.module_from_spec(_spec)
_spec.loader.exec_module(nextgqa_metrics)

VAL_CSV = REPO / "eval" / "data" / "nextqa" / "val.csv"
OUT_DIR = TUNING_DIR / "sparse_temporal_reranker_v1"
RAW_DIR = OUT_DIR / "raw"

FROZEN_CONFIG_KEYS = [
    "retrieval_strategy", "ppr_lambda", "ppr_damping", "l2_retrieve_top_k",
    "peak_distance", "peak_prominence", "packet_size_weight", "motion_weight",
    "luma_entropy_weight", "persistence_threshold", "max_prominence",
]

ARMS = {
    "A": dict(structured=False, traversal=False, adapter=False, adaptive_span=False,
              label="frozen baseline", raw="A_baseline.jsonl"),
    "F": dict(structured=True, traversal=False, adapter=False, adaptive_span=False,
              label="parser-fixed structured", raw="F_parser_fixed.jsonl"),
    "G": dict(structured=True, traversal=True, adapter=False, adaptive_span=False,
              label="safe non-destructive traversal", raw="G_safe_traversal.jsonl"),
    "H": dict(structured=False, traversal=False, adapter=True, adaptive_span=False,
              label="temporal adapter isolation", raw="H_temporal_adapter.jsonl"),
    "I": dict(structured=True, traversal=True, adapter=True, adaptive_span=False,
              label="full retrieval, fixed span", raw="I_full_fixed_span.jsonl"),
    "J": dict(structured=True, traversal=True, adapter=True, adaptive_span=True,
              label="full retrieval, adaptive span", raw="J_full_adaptive_span.jsonl"),
}


def load_type_codes() -> dict[tuple[str, str], str]:
    """(video, qid) -> NExT-QA type code, from the dataset row only. Answer
    columns a0..a4 are deliberately not read."""
    with open(VAL_CSV, newline="", encoding="utf-8") as fh:
        return {(r["video"], r["qid"]): r["type"] for r in csv.DictReader(fh)}


def assert_no_val_confirm(questions: list[dict]) -> None:
    split = json.loads((REPO / "split_manifest.json").read_text())
    confirm = set(split["confirm_videos"])
    used = {q["video"] for q in questions}
    leaked = used & confirm
    assert not leaked, f"val_confirm videos entered the evaluation set: {sorted(leaked)[:5]}"


def in_any_gold(ts: float, gold_spans: list) -> bool:
    return any(float(g[0]) <= ts <= float(g[1]) for g in gold_spans)


def gold_width(gold_spans: list) -> float:
    return max((float(g[1]) - float(g[0])) for g in gold_spans)


def duration_bucket(gold_spans: list) -> str:
    w = gold_width(gold_spans)
    return "<2s" if w < 2.0 else "2-5s" if w < 5.0 else "5-10s" if w < 10.0 else ">=10s"


def video_duration_bucket(d: float) -> str:
    return "<20s" if d < 20 else "20-40s" if d < 40 else "40-60s" if d < 60 else ">=60s"


def rank_of_first_gold(frames: list[dict], gold_spans: list) -> int | None:
    for i, f in enumerate(frames):
        if in_any_gold(float(f["timestamp"]), gold_spans):
            return i
    return None


def make_arm_config(frozen: dict, spec: dict, args) -> object:
    cfg = make_config({k: frozen[k] for k in FROZEN_CONFIG_KEYS})
    cfg.query_reformulation_mode = "none"
    cfg.temporal_traversal_mode = "none"
    cfg.action_aliases_enabled = False          # disabled for the whole experiment
    cfg.candidate_pool_size = args.candidate_pool_size
    cfg.query_trace_enabled = True
    return cfg


def frame_payload(frames: list[dict]) -> list[dict]:
    return [
        {
            "frame_idx": int(f["frame_idx"]),
            "timestamp": round(float(f["timestamp"]), 6),
            "scene_id": int(f.get("scene_id", -1)),
            "base_score": float(f.get("last_retrieval_score", 0.0) or 0.0),
            "final_score": (round(float(f["final_score"]), 6) if f.get("final_score") is not None else None),
            "score_components": {k: round(float(v), 6) for k, v in (f.get("score_components") or {}).items()},
            "source": f.get("candidate_source", "semantic"),
        }
        for f in frames
    ]


def run_arm(arm: str, questions: list[dict], index_paths: dict[str, str],
            index_cache: dict, frozen: dict, args, adapter=None, span_model=None) -> list[dict]:
    spec = ARMS[arm]
    cfg = make_arm_config(frozen, spec, args)
    half_width_s = float(frozen["span_method_half_width_s"])
    policy = TraversalPolicy(
        min_separation_s=args.min_separation_s,
        margin_activate=args.margin_activate,
        min_preserved=args.min_preserved,
    )
    use_adapter = spec["adapter"] and adapter is not None

    rows: list[dict] = []
    n_fail = 0
    for i, q in enumerate(questions, 1):
        vid = q["video"]
        if vid not in index_paths:
            continue
        if vid not in index_cache:
            index_cache[vid] = iris_ingest.load_index(index_paths[vid])
        index = index_cache[vid]

        t0 = time.perf_counter()
        try:
            if arm == "A":
                frames, plan, telemetry = retrieve_for_question(
                    q["question"], index, cfg, type_code=q["type_code"], family=q["family"],
                )
                res = {
                    "retrieval_frames": frames, "context_frames": [],
                    "semantic_candidates": frames, "semantic_top_k": frames,
                    "plan": None,
                    "traversal": {"traversal_active": False, "reason": "baseline",
                                  "n_original_preserved": len(frames)},
                    "adapter_confidence": None, "adapter_fallback_reason": "not_applicable",
                    "telemetry": {"num_ppr_calls": telemetry.get("num_ppr_calls", 1),
                                  "num_clip_texts_embedded": 1,
                                  "candidate_pool_size": len(frames),
                                  "parser_status": "baseline"},
                }
            else:
                res = retrieve_v3(
                    q["question"], index, cfg,
                    type_code=q["type_code"], family=q["family"],
                    use_structured=spec["structured"], use_traversal=spec["traversal"],
                    adapter=(adapter if use_adapter else None), policy=policy,
                )
        except Exception as exc:  # noqa: BLE001
            n_fail += 1
            print(f"  [FAIL] arm={arm} video={vid} qid={q['qid']}: {type(exc).__name__}: {exc}", flush=True)
            continue
        retrieval_ms = (time.perf_counter() - t0) * 1000.0

        retrieval_frames = res["retrieval_frames"]
        assert len(retrieval_frames) <= int(frozen["l2_retrieve_top_k"]), "retrieval width exceeded K"
        assert res["telemetry"].get("num_ppr_calls", 1) == 1, "more than one PPR call"

        # Method-D span, anchored on the verbatim question embedding in EVERY arm.
        try:
            qemb, _ = iris_query._call_embed_query(q["question"], cfg)
        except Exception:  # noqa: BLE001
            qemb = None
        t_span0 = time.perf_counter()
        fixed_span, used_clip_anchor = predicted_span_from_frames_peak(
            retrieval_frames, qemb, half_width_s=half_width_s,
        )
        pred_span = fixed_span
        span_info: dict = {"mode": "fixed_method_d", "fallback": False}
        if spec["adaptive_span"] and span_model is not None:
            pred_span, span_info = span_model.predict(
                index=index, retrieval_frames=retrieval_frames, candidates=res["semantic_candidates"],
                plan=res.get("plan"), type_code=q["type_code"],
                fixed_span=fixed_span, video_duration=float(q["duration"]),
            )
        span_ms = (time.perf_counter() - t_span0) * 1000.0

        gold = [(float(g[0]), float(g[1])) for g in q["gold_spans"]]
        iop = nextgqa_metrics.iop(pred_span[0], pred_span[1], gold)
        iou = nextgqa_metrics.iou(pred_span[0], pred_span[1], gold)
        fixed_iop = nextgqa_metrics.iop(fixed_span[0], fixed_span[1], gold)
        fixed_iou = nextgqa_metrics.iou(fixed_span[0], fixed_span[1], gold)

        ts = [float(f["timestamp"]) for f in retrieval_frames]
        first_gold = rank_of_first_gold(retrieval_frames, q["gold_spans"])
        plan = res.get("plan")

        rows.append({
            "arm": arm, "video": vid, "qid": q["qid"],
            "question": q["question"], "type_code": q["type_code"],
            "relation": getattr(plan, "relation", None),
            "relation_source": getattr(plan, "relation_source", None),
            "parser_status": res["telemetry"].get("parser_status"),
            "query_roles": list(getattr(plan, "query_roles", ()) or ()),
            "query_texts": list(getattr(plan, "anchor_queries", ()) or ()),
            "target_query": getattr(plan, "target_query", None),
            "gold_spans": q["gold_spans"],
            "gold_width_s": round(gold_width(q["gold_spans"]), 6),
            "duration_bucket": q["duration_bucket"],
            "video_duration_s": float(q["duration"]),
            "video_duration_bucket": video_duration_bucket(float(q["duration"])),
            "semantic_top_k": frame_payload(res["semantic_top_k"]),
            "candidates": frame_payload(res["semantic_candidates"]),
            "retrieval_frames": frame_payload(retrieval_frames),
            "context_frames": frame_payload(res["context_frames"]),
            "pred_span_start": round(float(pred_span[0]), 6),
            "pred_span_end": round(float(pred_span[1]), 6),
            "pred_span_width": round(float(pred_span[1] - pred_span[0]), 6),
            "fixed_span_start": round(float(fixed_span[0]), 6),
            "fixed_span_end": round(float(fixed_span[1]), 6),
            "span_info": span_info,
            "iop": float(iop), "iou": float(iou),
            "fixed_iop": float(fixed_iop), "fixed_iou": float(fixed_iou),
            "gold_at_1": first_gold == 0,
            "gold_at_2": first_gold is not None and first_gold < 2,
            "gold_at_4": first_gold is not None and first_gold < 4,
            "first_gold_rank": first_gold,
            "reciprocal_rank": (1.0 / (first_gold + 1)) if first_gold is not None else 0.0,
            "top_k_spread_s": round(max(ts) - min(ts), 6) if len(ts) > 1 else 0.0,
            "n_frames": len(retrieval_frames),
            "traversal": res["traversal"],
            "adapter_confidence": res.get("adapter_confidence"),
            "adapter_fallback_reason": res.get("adapter_fallback_reason"),
            "used_clip_anchor": bool(used_clip_anchor),
            "zero_width_span": float(pred_span[0]) == float(pred_span[1]),
            "invalid_span": not (float(pred_span[1]) >= float(pred_span[0])),
            "retrieval_ms": round(retrieval_ms, 4),
            "span_ms": round(span_ms, 4),
            "latency_components": {k: round(float(v), 4) for k, v in res["telemetry"].items()
                                   if isinstance(v, (int, float)) and k.startswith("t_")},
            "num_ppr_calls": res["telemetry"].get("num_ppr_calls"),
            "num_clip_texts_embedded": res["telemetry"].get("num_clip_texts_embedded"),
            "candidate_pool_size": res["telemetry"].get("candidate_pool_size"),
        })

        if i % 250 == 0:
            n = len(rows)
            print(f"  [arm {arm}] {i}/{len(questions)} scored={n} "
                  f"gold@4={sum(r['gold_at_4'] for r in rows)/max(n,1):.4f} "
                  f"mIoP={sum(r['iop'] for r in rows)/max(n,1):.4f}", flush=True)

    print(f"  [arm {arm}] done: {len(rows)} scored, {n_fail} failures", flush=True)
    return rows


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    lat = [r["retrieval_ms"] for r in rows]
    widths = [r["pred_span_width"] for r in rows]
    return {
        "n": n,
        "gold_at_1": sum(r["gold_at_1"] for r in rows) / n,
        "gold_at_2": sum(r["gold_at_2"] for r in rows) / n,
        "gold_at_4": sum(r["gold_at_4"] for r in rows) / n,
        "mrr": sum(r["reciprocal_rank"] for r in rows) / n,
        "mIoP": sum(r["iop"] for r in rows) / n,
        "mIoU": sum(r["iou"] for r in rows) / n,
        "IoP@0.5": sum(1 for r in rows if r["iop"] >= 0.5) / n,
        "IoU@0.5": sum(1 for r in rows if r["iou"] >= 0.5) / n,
        "mean_span_width": sum(widths) / n,
        "median_span_width": statistics.median(widths),
        "zero_width_count": sum(r["zero_width_span"] for r in rows),
        "invalid_span_count": sum(r["invalid_span"] for r in rows),
        "mean_top_k_spread_s": sum(r["top_k_spread_s"] for r in rows) / n,
        "median_retrieval_ms": statistics.median(lat),
        "p95_retrieval_ms": (statistics.quantiles(lat, n=20)[18] if len(lat) >= 20 else max(lat)),
        "traversal_activation_rate": sum(1 for r in rows if (r["traversal"] or {}).get("traversal_active")) / n,
        "mean_original_preserved": sum((r["traversal"] or {}).get("n_original_preserved", 0) for r in rows) / n,
        "adapter_fallback_rate": sum(1 for r in rows
                                     if r.get("adapter_fallback_reason") not in (None, "adapter_not_used",
                                                                                "not_applicable", "ok")) / n,
        "max_ppr_calls": max(r["num_ppr_calls"] or 1 for r in rows),
        "max_text_embeddings": max(r["num_clip_texts_embedded"] or 1 for r in rows),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arms", default="A,F,G")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--limit-videos", dest="limit_videos", type=int, default=None)
    p.add_argument("--candidate-pool-size", dest="candidate_pool_size", type=int, default=16)
    p.add_argument("--min-separation-s", dest="min_separation_s", type=float, default=1.0)
    p.add_argument("--margin-activate", dest="margin_activate", type=float, default=0.05)
    p.add_argument("--min-preserved", dest="min_preserved", type=int, default=3)
    p.add_argument("--adapter-checkpoint", dest="adapter_checkpoint", default=None)
    p.add_argument("--out-suffix", dest="out_suffix", default="")
    args = p.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    frozen = load_frozen_state()["frozen"]
    print(f"[frozen] K={frozen['l2_retrieve_top_k']} lambda={frozen['ppr_lambda']} "
          f"damping={frozen['ppr_damping']} span=Method-{frozen['span_method']} "
          f"half_width={frozen['span_method_half_width_s']}s", flush=True)

    type_codes = load_type_codes()
    questions = load_val_tune_questions()
    for q in questions:
        tc = type_codes.get((q["video"], q["qid"]))
        q["type_code"] = tc
        q["family"] = tc[0].upper() if tc else None
        q["duration_bucket"] = duration_bucket(q["gold_spans"])
    assert_no_val_confirm(questions)

    if args.limit_videos:
        keep = []
        seen: list[str] = []
        for q in questions:
            if q["video"] not in seen:
                if len(seen) >= args.limit_videos:
                    continue
                seen.append(q["video"])
            keep.append(q)
        questions = keep
    if args.limit:
        questions = questions[: args.limit]
    print(f"[data] {len(questions)} val_tune questions, "
          f"{len({q['video'] for q in questions})} videos", flush=True)

    cfg = make_arm_config(frozen, ARMS["A"], args)
    index_paths = ensure_indexes(sorted({q["video"] for q in questions}), cfg)
    index_cache: dict = {}

    adapter = span_model = None
    if args.adapter_checkpoint:
        from iris.temporal_adapter import load_adapter_bundle
        adapter, span_model = load_adapter_bundle(args.adapter_checkpoint)
        print(f"[adapter] loaded {args.adapter_checkpoint}", flush=True)

    summaries = {}
    for arm in args.arms.split(","):
        arm = arm.strip()
        if not arm:
            continue
        print(f"\n=== Arm {arm}: {ARMS[arm]['label']} ===", flush=True)
        t0 = time.perf_counter()
        rows = run_arm(arm, questions, index_paths, index_cache, frozen, args,
                       adapter=adapter, span_model=span_model)
        out = RAW_DIR / (ARMS[arm]["raw"].replace(".jsonl", f"{args.out_suffix}.jsonl"))
        with open(out, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        s = summarize(rows)
        s["wall_s"] = time.perf_counter() - t0
        summaries[arm] = s
        print(f"  -> {out}", flush=True)
        print("  " + json.dumps({k: (round(v, 6) if isinstance(v, float) else v)
                                 for k, v in s.items()}), flush=True)

    (OUT_DIR / f"arm_summaries{args.out_suffix}.json").write_text(json.dumps(summaries, indent=2))
    print("\nDONE", flush=True)


if __name__ == "__main__":
    main()

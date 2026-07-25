"""Metrics, breakdowns and video-clustered statistics for the reranker ablation.

Every percentage is reported with its numerator and denominator. Bootstrap
resampling is clustered by VIDEO (resample videos with replacement, take all of
a sampled video's questions) because questions from one video are not
independent -- 450 videos carry 2685 questions here.
"""
from __future__ import annotations

import csv
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "tuning" / "sparse_temporal_reranker_v1"
RAW_DIR = OUT_DIR / "raw"

BOOTSTRAP_SEED = 20260725
N_BOOT = 2000

ARM_FILES = {
    "A": "A_baseline.jsonl",
    "F": "F_parser_fixed.jsonl",
    "G": "G_safe_traversal.jsonl",
    "H": "H_temporal_adapter.jsonl",
    "I": "I_full_fixed_span.jsonl",
    "J": "J_full_adaptive_span.jsonl",
}


def load_arm(arm: str) -> list[dict]:
    path = RAW_DIR / ARM_FILES[arm]
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def rate(num: int, den: int) -> dict:
    return {"n": num, "d": den, "rate": (num / den) if den else 0.0}


def arm_summary(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    widths = [r["pred_span_width"] for r in rows]
    lat = [r["retrieval_ms"] for r in rows]
    trav = [r.get("traversal") or {} for r in rows]
    center_err = []
    for r in rows:
        gold = r["gold_spans"]
        gc = statistics.mean([(float(g[0]) + float(g[1])) / 2 for g in gold])
        pc = (r["pred_span_start"] + r["pred_span_end"]) / 2
        center_err.append(abs(pc - gc))
    return {
        "n": n,
        "gold_at_1": rate(sum(r["gold_at_1"] for r in rows), n),
        "gold_at_2": rate(sum(r["gold_at_2"] for r in rows), n),
        "gold_at_4": rate(sum(r["gold_at_4"] for r in rows), n),
        "mrr": sum(r["reciprocal_rank"] for r in rows) / n,
        "mIoP": sum(r["iop"] for r in rows) / n,
        "mIoU": sum(r["iou"] for r in rows) / n,
        "IoP@0.5": rate(sum(1 for r in rows if r["iop"] >= 0.5), n),
        "IoU@0.5": rate(sum(1 for r in rows if r["iou"] >= 0.5), n),
        "mean_span_width": sum(widths) / n,
        "median_span_width": statistics.median(widths),
        "mean_center_error_s": sum(center_err) / n,
        "median_center_error_s": statistics.median(center_err),
        "zero_width_count": sum(r["zero_width_span"] for r in rows),
        "invalid_span_count": sum(r["invalid_span"] for r in rows),
        "boundary_clipped_count": sum(1 for r in rows
                                      if (r.get("span_info") or {}).get("clipped")),
        "mean_top_k_spread_s": sum(r["top_k_spread_s"] for r in rows) / n,
        "median_top_k_spread_s": statistics.median([r["top_k_spread_s"] for r in rows]),
        "traversal_activation": rate(sum(1 for t in trav if t.get("traversal_active")), n),
        "mean_original_preserved": sum(t.get("n_original_preserved", 0) for t in trav) / n,
        "adapter_fallback": rate(
            sum(1 for r in rows if r.get("adapter_fallback_reason") not in
                (None, "adapter_not_used", "not_applicable", "ok")), n),
        "median_retrieval_ms": statistics.median(lat),
        "p95_retrieval_ms": statistics.quantiles(lat, n=20)[18] if len(lat) >= 20 else max(lat),
        "mean_retrieval_ms": sum(lat) / n,
        "max_ppr_calls": max(r["num_ppr_calls"] or 1 for r in rows),
        "max_text_embeddings": max(r["num_clip_texts_embedded"] or 1 for r in rows),
    }


def clustered_bootstrap(rows_a: list[dict], rows_x: list[dict], metric_fn,
                        n_boot: int = N_BOOT, seed: int = BOOTSTRAP_SEED) -> dict:
    """Paired delta (x - a) with a 95% percentile CI, resampling VIDEOS."""
    by_a = {(r["video"], r["qid"]): r for r in rows_a}
    by_x = {(r["video"], r["qid"]): r for r in rows_x}
    keys = sorted(set(by_a) & set(by_x))
    if not keys:
        return {}
    per_video = defaultdict(list)
    for k in keys:
        per_video[k[0]].append((metric_fn(by_a[k]), metric_fn(by_x[k])))
    videos = sorted(per_video)

    def delta(sample_videos):
        na = xa = 0.0
        cnt = 0
        for v in sample_videos:
            for a, x in per_video[v]:
                na += a
                xa += x
                cnt += 1
        return (xa - na) / cnt if cnt else 0.0

    obs = delta(videos)
    rng = random.Random(seed)
    deltas = []
    for _ in range(n_boot):
        sample = [videos[rng.randrange(len(videos))] for _ in videos]
        deltas.append(delta(sample))
    deltas.sort()
    lo, hi = deltas[int(0.025 * n_boot)], deltas[int(0.975 * n_boot) - 1]
    return {
        "n_paired": len(keys), "n_videos": len(videos),
        "delta": obs, "ci_lo": lo, "ci_hi": hi,
        "significant": bool(lo > 0 or hi < 0),
        "bootstrap_seed": seed, "n_boot": n_boot, "cluster": "video",
    }


def main() -> None:
    arms = {a: load_arm(a) for a in ARM_FILES}
    arms = {a: r for a, r in arms.items() if r}
    print(f"[report] arms present: {list(arms)}")
    summaries = {a: arm_summary(r) for a, r in arms.items()}

    # summary.csv
    flat_keys = ["n", "gold_at_1", "gold_at_2", "gold_at_4", "mrr", "mIoP", "mIoU",
                 "IoP@0.5", "IoU@0.5", "mean_span_width", "median_span_width",
                 "mean_center_error_s", "median_center_error_s", "zero_width_count",
                 "invalid_span_count", "boundary_clipped_count", "mean_top_k_spread_s",
                 "median_top_k_spread_s", "traversal_activation", "mean_original_preserved",
                 "adapter_fallback", "median_retrieval_ms", "p95_retrieval_ms",
                 "mean_retrieval_ms", "max_ppr_calls", "max_text_embeddings"]
    with open(OUT_DIR / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["arm"] + flat_keys + ["gold_at_4_num", "gold_at_4_den"])
        for a, s in summaries.items():
            row = [a]
            for k in flat_keys:
                v = s.get(k)
                row.append(v["rate"] if isinstance(v, dict) else v)
            row += [s["gold_at_4"]["n"], s["gold_at_4"]["d"]]
            w.writerow(row)

    # per_type.csv / per_duration_bucket.csv / video-duration / parser status
    def breakdown(key_fn, path, extra_header):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["arm", extra_header, "n", "gold_at_4_num", "gold_at_4_rate",
                        "gold_at_1_rate", "mIoP", "mIoU", "mean_span_width"])
            for a, rows in arms.items():
                groups = defaultdict(list)
                for r in rows:
                    groups[key_fn(r)].append(r)
                for g in sorted(groups, key=str):
                    gr = groups[g]
                    n = len(gr)
                    w.writerow([a, g, n,
                                sum(x["gold_at_4"] for x in gr),
                                sum(x["gold_at_4"] for x in gr) / n,
                                sum(x["gold_at_1"] for x in gr) / n,
                                sum(x["iop"] for x in gr) / n,
                                sum(x["iou"] for x in gr) / n,
                                sum(x["pred_span_width"] for x in gr) / n])

    breakdown(lambda r: r["type_code"], OUT_DIR / "per_type.csv", "type_code")
    breakdown(lambda r: r["duration_bucket"], OUT_DIR / "per_duration_bucket.csv", "gold_duration_bucket")
    breakdown(lambda r: r["video_duration_bucket"], OUT_DIR / "per_video_duration_bucket.csv",
              "video_duration_bucket")
    breakdown(lambda r: r.get("parser_status") or "n/a", OUT_DIR / "per_parser_status.csv", "parser_status")
    breakdown(lambda r: bool((r.get("traversal") or {}).get("traversal_active")),
              OUT_DIR / "per_traversal_active.csv", "traversal_active")
    breakdown(lambda r: r.get("relation") or "n/a", OUT_DIR / "per_relation.csv", "relation")

    # per_video.csv -- per-video deltas vs A, enough to reproduce the bootstrap
    base = {(r["video"], r["qid"]): r for r in arms.get("A", [])}
    with open(OUT_DIR / "per_video.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "video", "n_questions", "gold_at_4_rate", "mIoP", "mIoU",
                    "delta_gold_at_4_vs_A", "delta_mIoP_vs_A", "delta_mIoU_vs_A"])
        for a, rows in arms.items():
            per_video = defaultdict(list)
            for r in rows:
                per_video[r["video"]].append(r)
            for v in sorted(per_video):
                gr = per_video[v]
                n = len(gr)
                g4 = sum(x["gold_at_4"] for x in gr) / n
                iop = sum(x["iop"] for x in gr) / n
                iou = sum(x["iou"] for x in gr) / n
                paired = [base.get((x["video"], x["qid"])) for x in gr]
                paired = [p for p in paired if p]
                if paired:
                    bg = sum(p["gold_at_4"] for p in paired) / len(paired)
                    bp = sum(p["iop"] for p in paired) / len(paired)
                    bu = sum(p["iou"] for p in paired) / len(paired)
                    w.writerow([a, v, n, g4, iop, iou, g4 - bg, iop - bp, iou - bu])
                else:
                    w.writerow([a, v, n, g4, iop, iou, "", "", ""])

    # gained_lost.csv
    with open(OUT_DIR / "gained_lost.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "video", "qid", "type_code", "question", "change",
                    "A_first_gold_rank", "arm_first_gold_rank", "A_iop", "arm_iop",
                    "parser_status", "traversal_active", "relation"])
        for a, rows in arms.items():
            if a == "A":
                continue
            for r in rows:
                b = base.get((r["video"], r["qid"]))
                if not b or b["gold_at_4"] == r["gold_at_4"]:
                    continue
                w.writerow([a, r["video"], r["qid"], r["type_code"], r["question"],
                            "gained" if r["gold_at_4"] else "lost",
                            b["first_gold_rank"], r["first_gold_rank"],
                            round(b["iop"], 6), round(r["iop"], 6),
                            r.get("parser_status"),
                            bool((r.get("traversal") or {}).get("traversal_active")),
                            r.get("relation")])

    # statistical_report.json
    stats: dict = {"bootstrap_seed": BOOTSTRAP_SEED, "n_boot": N_BOOT,
                   "cluster_unit": "video", "vs_A": {}}
    metrics = {
        "gold_at_4": lambda r: float(r["gold_at_4"]),
        "gold_at_1": lambda r: float(r["gold_at_1"]),
        "mIoP": lambda r: float(r["iop"]),
        "mIoU": lambda r: float(r["iou"]),
    }
    for a, rows in arms.items():
        if a == "A":
            continue
        stats["vs_A"][a] = {m: clustered_bootstrap(arms["A"], rows, fn)
                            for m, fn in metrics.items()}
    if "I" in arms and "J" in arms:
        stats["J_vs_I_span"] = {m: clustered_bootstrap(arms["I"], arms["J"], fn)
                                for m, fn in metrics.items() if m in ("mIoP", "mIoU")}
        same = sum(1 for ri, rj in zip(
            sorted(arms["I"], key=lambda r: (r["video"], r["qid"])),
            sorted(arms["J"], key=lambda r: (r["video"], r["qid"])))
            if [f["frame_idx"] for f in ri["retrieval_frames"]] ==
               [f["frame_idx"] for f in rj["retrieval_frames"]])
        stats["I_J_identical_retrieval"] = {"n_identical": same, "n": len(arms["I"]),
                                            "all_identical": same == len(arms["I"])}
    (OUT_DIR / "statistical_report.json").write_text(json.dumps(stats, indent=2))

    # latency_report.json
    lat = {}
    for a, rows in arms.items():
        l = [r["retrieval_ms"] for r in rows]
        comp = defaultdict(list)
        for r in rows:
            for k, v in (r.get("latency_components") or {}).items():
                comp[k].append(v)
        lat[a] = {
            "n": len(l),
            "median_retrieval_ms": statistics.median(l),
            "p95_retrieval_ms": statistics.quantiles(l, n=20)[18] if len(l) >= 20 else max(l),
            "mean_retrieval_ms": sum(l) / len(l),
            "max_ppr_calls": max(r["num_ppr_calls"] or 1 for r in rows),
            "max_text_embeddings": max(r["num_clip_texts_embedded"] or 1 for r in rows),
            "mean_candidate_pool_size": sum(r["candidate_pool_size"] or 0 for r in rows) / len(rows),
            "component_medians_ms": {k: statistics.median(v) for k, v in comp.items()},
        }
    (OUT_DIR / "latency_report.json").write_text(json.dumps(lat, indent=2))
    (OUT_DIR / "arm_summaries_full.json").write_text(json.dumps(summaries, indent=2))

    print(json.dumps({a: {"n": s["n"],
                          "gold@1": round(s["gold_at_1"]["rate"], 4),
                          "gold@4": round(s["gold_at_4"]["rate"], 4),
                          "mIoP": round(s["mIoP"], 6),
                          "mIoU": round(s["mIoU"], 6),
                          "median_ms": round(s["median_retrieval_ms"], 3)}
                      for a, s in summaries.items()}, indent=2))
    print("\npaired vs A (video-clustered 95% CI):")
    for a, m in stats["vs_A"].items():
        for name, d in m.items():
            if d:
                print(f"  {a} {name}: delta={d['delta']:+.4f} "
                      f"CI=[{d['ci_lo']:+.4f},{d['ci_hi']:+.4f}] sig={d['significant']}")


if __name__ == "__main__":
    main()

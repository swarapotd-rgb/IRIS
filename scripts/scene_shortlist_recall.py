"""L2 scene-shortlist recall -- DIAGNOSTIC ONLY, measures, never tunes.

Question: for each question, does the gold scene survive the L2 centroid
shortlist that iris/scene_retrieval.py:retrieve_scene_sparse builds before
frame ranking ever runs?

Read-only. Does not touch tuning/frozen_state.json, tuning/all_trials.csv,
iris/*.py, or any index cache. Reuses cached .npz indexes by explicit path
(never ensure_indexes(), which could re-ingest). No GPU, no PPR, no
captioner, no LLM -- the only model touched is the CLIP *text* encoder,
which is unavoidable: a centroid shortlist is undefined without a query
embedding, and it is the same deterministic torch-cpu path production uses.

Outputs (tuning/scene_shortlist_recall/):
  <split>_per_question.csv, <split>_summary.json, width_sweep.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import iris.ingest as iris_ingest  # noqa: E402
from iris.scene_retrieval import LinearScanScorer, _cosine_batch  # noqa: E402

OUT_DIR = REPO / "tuning" / "scene_shortlist_recall"
SHORT_LONG_THRESHOLD_S = 2.5  # project convention, same as PART A
SCENE_001_THRESHOLD = 0.20    # iris/scene_retrieval.py adaptive fallback
TYPE_FAMILY = {"CW": "causal", "CH": "causal", "TN": "temporal", "TC": "temporal", "TP": "temporal"}

SPLITS = {
    "val_tune": {
        "cache_dir": REPO / "tuning" / "index_cache",       # the cache PART A (2ad7ab9) read
        "config_hash": "cab2bac1628012a3",
        "questions_csv": REPO / "eval" / "data" / "nextqa" / "val.csv",
        "gold_json": REPO / "eval" / "data" / "nextqa" / "gsub_val.json",
    },
    "val_confirm": {
        "cache_dir": REPO / "tuning" / "index_cache_val_confirm_e2e",
        "config_hash": "4edae64ed40256e3",
        "questions_csv": REPO / "eval" / "data" / "nextqa" / "val.csv",
        "gold_json": REPO / "eval" / "data" / "nextqa" / "gsub_val.json",
    },
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── question loading ──────────────────────────────────────────────────────
def load_questions(split: str) -> list[dict]:
    """Same filter chain / row order the two anchor diagnostics used:
    part3_tune.load_val_tune_questions for val_tune, val_confirm_e2e_eval.
    load_split_questions for val_confirm. `type` is joined on from val.csv so
    the family breakdown matches PART A's."""
    spec = SPLITS[split]
    manifest = json.loads((REPO / "split_manifest.json").read_text())
    in_scope = set(manifest["tune_videos"] if split == "val_tune" else manifest["confirm_videos"])
    video_dir = REPO / "eval" / "data" / "nextqa" / "NExTVideo_flat"
    gsub = json.loads(Path(spec["gold_json"]).read_text())

    out = []
    with open(spec["questions_csv"], newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            vid = r["video"]
            if vid not in in_scope:
                continue
            if not (video_dir / f"{vid}.mp4").exists():
                continue
            gold = gsub.get(vid, {}).get("location", {}).get(r["qid"])
            if not gold:
                continue
            spans = [(float(a), float(b)) for a, b in gold]
            longest = max(spans, key=lambda g: g[1] - g[0])
            out.append({
                "video": vid, "qid": r["qid"], "question": r["question"],
                "type": r.get("type", ""), "family": TYPE_FAMILY.get(r.get("type", ""), "other"),
                "gold_spans": spans, "primary_span": longest,
                "span_len": longest[1] - longest[0],
            })
    return out


# ── shortlist reconstruction (mirrors retrieve_scene_sparse exactly) ───────
def production_width(num_scenes: int) -> int:
    """iris/scene_retrieval.py: scene_shortlist_width is 0 in every frozen
    config on disk, so the sqrt rule always applies."""
    return min(max(4, math.ceil(math.sqrt(num_scenes))), num_scenes)


WIDTH_RULES = [
    ("ceil_sqrt_N__production", lambda n: max(4, math.ceil(math.sqrt(n)))),
    ("2x_ceil_sqrt_N",          lambda n: 2 * math.ceil(math.sqrt(n))),
    ("4x_ceil_sqrt_N",          lambda n: 4 * math.ceil(math.sqrt(n))),
    ("ceil_N_over_4",           lambda n: math.ceil(n / 4)),
    ("ceil_N_over_2",           lambda n: math.ceil(n / 2)),
    ("N_all_scenes",            lambda n: n),
]


def analyse_question(index, q, query_emb, scorer) -> dict:
    centroids = getattr(index, "_scene_centroids", None)
    if not centroids:
        return {"error": "no_centroids"}
    num_scenes = len(centroids)

    # Identical to LinearScanScorer.score: one cosine per centroid, sorted
    # descending with a stable ascending-scene_id tie-break.
    scene_ranking = scorer.score(query_emb, centroids)
    rank_of_scene = {sid: i + 1 for i, (sid, _) in enumerate(scene_ranking)}

    width = production_width(num_scenes)
    shortlisted = {sid for sid, _ in scene_ranking[:width]}

    # gold scenes: scene contains >=1 L1-admitted frame inside the gold span.
    # scene_id comes from FrameRecord, never AsphodelNode (the latter is a
    # monotonic I-frame id that _refresh_scene_ids overwrites every build).
    ga, gb = q["primary_span"]
    gold_primary, gold_any = set(), set()
    for fr in index.frames:
        if fr.scene_id is None or fr.scene_id < 0 or fr.clip_embedding is None:
            continue
        if fr.scene_id not in centroids:
            continue
        t = fr.timestamp
        if ga <= t <= gb:
            gold_primary.add(fr.scene_id)
        if any(s <= t <= e for s, e in q["gold_spans"]):
            gold_any.add(fr.scene_id)

    gold_ranks = sorted(rank_of_scene[s] for s in gold_primary)
    best_gold_rank = gold_ranks[0] if gold_ranks else None
    hit = bool(gold_primary & shortlisted)
    frac_captured = (len(gold_primary & shortlisted) / len(gold_primary)) if gold_primary else None

    gold_ranks_any = sorted(rank_of_scene[s] for s in gold_any)
    hit_any = bool(gold_any & shortlisted)

    # ── production fallbacks, evaluated exactly as retrieve_scene_sparse does
    survivors = [fr for fr in index.frames if fr.scene_id in shortlisted and fr.clip_embedding is not None]
    fb_empty = not survivors
    if fb_empty:
        survivors = [fr for fr in index.frames if fr.scene_id in set(centroids) and fr.clip_embedding is not None]
    fb_scene001 = False
    if survivors:
        pool = np.stack([np.asarray(fr.clip_embedding, dtype=np.float32) for fr in survivors])
        sims = _cosine_batch(query_emb, pool)
        if float(np.max(sims)) < SCENE_001_THRESHOLD and len(shortlisted) < num_scenes:
            fb_scene001 = True
    fired = fb_empty or fb_scene001

    # width sweep -- same ranking, different cutoffs. Cost axis = pool frames.
    frames_by_scene: dict[int, int] = defaultdict(int)
    for fr in index.frames:
        if fr.clip_embedding is not None and fr.scene_id in centroids:
            frames_by_scene[fr.scene_id] += 1
    sweep = {}
    for name, rule in WIDTH_RULES:
        w = min(max(1, rule(num_scenes)), num_scenes)
        sset = {sid for sid, _ in scene_ranking[:w]}
        sweep[name] = {
            "width": w,
            "hit": bool(gold_primary & sset),
            "pool_frames": sum(frames_by_scene[s] for s in sset),
        }

    return {
        "video_id": q["video"], "qid": q["qid"], "question_type": q["type"],
        "question_family": q["family"],
        "gold_span_length_s": round(q["span_len"], 3),
        "span_bucket": "short" if q["span_len"] <= SHORT_LONG_THRESHOLD_S else "long",
        "n_scenes": num_scenes,
        "n_admitted_frames": len(index.frames),
        "shortlist_width": width,
        "n_gold_scenes": len(gold_primary),
        "gold_scene_ranks": ";".join(str(r) for r in gold_ranks),
        "best_gold_rank": best_gold_rank if best_gold_rank is not None else "",
        "hit_at_shortlist": hit,
        "frac_gold_captured": round(frac_captured, 4) if frac_captured is not None else "",
        "fallback_all_scenes_fired": fb_scene001,
        "fallback_empty_pool_fired": fb_empty,
        "effective_hit": bool(hit or fired),
        "n_gold_scenes_anyspan": len(gold_any),
        "best_gold_rank_anyspan": gold_ranks_any[0] if gold_ranks_any else "",
        "hit_at_shortlist_anyspan": hit_any,
        "_sweep": sweep,
    }


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def rate(rows, key, pred=lambda r: True):
    sub = [r for r in rows if pred(r)]
    if not sub:
        return {"rate": None, "n": 0, "n_hit": 0}
    k = sum(1 for r in sub if r[key])
    lo, hi = wilson(k, len(sub))
    return {"rate": k / len(sub), "n": len(sub), "n_hit": k,
            "ci95": [round(lo, 4), round(hi, 4)]}


def run_split(split: str, verify_n: int = 20) -> dict:
    spec = SPLITS[split]
    cache_dir, cfg_hash = spec["cache_dir"], spec["config_hash"]
    questions = load_questions(split)
    print(f"[{split}] {len(questions)} questions, "
          f"{len({q['video'] for q in questions})} videos", flush=True)

    by_video = defaultdict(list)
    for q in questions:
        by_video[q["video"]].append(q)

    import part3_tune as pt
    from iris.query import _call_embed_query
    cfg = pt.make_config({"retrieval_strategy": "hybrid"})
    scorer = LinearScanScorer()

    rows, missing_cache, no_centroids = [], [], []
    verify_pool, t0 = [], time.time()
    for i, (vid, qs) in enumerate(sorted(by_video.items())):
        path = cache_dir / f"{vid}__{cfg_hash}.npz"
        if not path.exists():
            missing_cache.append(vid)
            continue
        index = iris_ingest.load_index(str(path))
        for q in qs:
            emb, _ = _call_embed_query(q["question"], cfg)
            res = analyse_question(index, q, emb, scorer)
            if res.get("error"):
                no_centroids.append((vid, q["qid"]))
                continue
            rows.append(res)
            if len(verify_pool) < verify_n and len(rows) % 7 == 0:
                verify_pool.append((str(path), q, res))
        del index
        if (i + 1) % 50 == 0:
            print(f"  [{split}] {i+1}/{len(by_video)} videos, {len(rows)} rows, "
                  f"{time.time()-t0:.0f}s", flush=True)

    # ── STEP 1 verification: reconstruction vs retrieve_scene_sparse ──────
    from iris.scene_retrieval import retrieve_scene_sparse
    n_match = 0
    verify_detail = []
    for path, q, res in verify_pool:
        index = iris_ingest.load_index(path)
        emb, _ = _call_embed_query(q["question"], cfg)
        trace: dict = {}
        try:
            retrieve_scene_sparse(index, emb, cfg, trace=trace)
        except Exception as e:  # noqa: BLE001
            verify_detail.append({"video": q["video"], "qid": q["qid"], "match": False, "error": repr(e)})
            continue
        prod_set = set(trace.get("shortlisted_scene_ids") or [])
        # trace records the POST-fallback set; if we predicted a fallback the
        # expected set is every scene, otherwise our shortlist.
        ranking = scorer.score(emb, index._scene_centroids)
        if res["fallback_all_scenes_fired"] or res["fallback_empty_pool_fired"]:
            expected = set(index._scene_centroids.keys())
        else:
            expected = {sid for sid, _ in ranking[:res["shortlist_width"]]}
        ok = prod_set == expected
        n_match += ok
        verify_detail.append({"video": q["video"], "qid": q["qid"], "match": bool(ok),
                              "n_prod": len(prod_set), "n_mine": len(expected),
                              "fallback": bool(res["fallback_all_scenes_fired"] or res["fallback_empty_pool_fired"])})
        del index
    print(f"[{split}] shortlist reconstruction match: {n_match}/{len(verify_pool)}", flush=True)
    if n_match != len(verify_pool):
        raise SystemExit(f"GUARD TRIPPED: reconstruction match {n_match}/{len(verify_pool)}; "
                         f"detail: {json.dumps(verify_detail, indent=1)}")

    # ── zero-gold-scene guard ────────────────────────────────────────────
    zero_gold = [r for r in rows if r["n_gold_scenes"] == 0]
    if rows and len(zero_gold) / len(rows) > 0.01:
        raise SystemExit(f"GUARD TRIPPED: {len(zero_gold)}/{len(rows)} questions "
                         f"({len(zero_gold)/len(rows):.2%}) have zero gold scenes (>1%)")

    # ── write per-question CSV ───────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [k for k in rows[0] if not k.startswith("_")]
    csv_path = OUT_DIR / f"{split}_per_question.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ── breakdowns ───────────────────────────────────────────────────────
    ns_vals = sorted(r["n_scenes"] for r in rows)
    qs = [ns_vals[int(len(ns_vals) * f)] for f in (0.25, 0.50, 0.75)]

    def ns_q(r):
        n = r["n_scenes"]
        return "Q1" if n <= qs[0] else "Q2" if n <= qs[1] else "Q3" if n <= qs[2] else "Q4"

    scored = [r for r in rows if r["n_gold_scenes"] > 0]
    ranks = [r["best_gold_rank"] for r in scored]

    def breakdown(key):
        return {
            "overall": rate(rows, key),
            "by_family": {fam: rate(rows, key, lambda r, f=fam: r["question_family"] == f)
                          for fam in ("causal", "temporal", "other")},
            "by_type": {t: rate(rows, key, lambda r, t=t: r["question_type"] == t)
                        for t in sorted({r["question_type"] for r in rows})},
            "by_span_bucket": {b: rate(rows, key, lambda r, b=b: r["span_bucket"] == b)
                               for b in ("short", "long")},
            "by_n_scenes_quartile": {q_: rate(rows, key, lambda r, q_=q_: ns_q(r) == q_)
                                     for q_ in ("Q1", "Q2", "Q3", "Q4")},
        }

    sweep_agg = {}
    for name, _ in WIDTH_RULES:
        hits = sum(1 for r in rows if r["_sweep"][name]["hit"])
        lo, hi = wilson(hits, len(rows))
        sweep_agg[name] = {
            "mean_width": round(statistics.mean(r["_sweep"][name]["width"] for r in rows), 3),
            "recall": hits / len(rows),
            "n_hit": hits, "n_total": len(rows),
            "ci95": [round(lo, 4), round(hi, 4)],
            "mean_pool_frames": round(statistics.mean(r["_sweep"][name]["pool_frames"] for r in rows), 2),
            "median_pool_frames": statistics.median(r["_sweep"][name]["pool_frames"] for r in rows),
        }

    hist = defaultdict(int)
    for r in ranks:
        hist[str(r)] += 1

    summary = {
        "split": split,
        "config_hash": cfg_hash,
        "cache_dir": str(cache_dir),
        "n_questions": len(rows),
        "n_videos": len({r["video_id"] for r in rows}),
        "reconstruction_verification": {"n_matched": n_match, "n_sampled": len(verify_pool),
                                        "detail": verify_detail},
        "failure_modes": {
            "videos_missing_from_cache": missing_cache,
            "questions_without_centroids": no_centroids,
            "questions_with_zero_gold_scenes": [
                {"video_id": r["video_id"], "qid": r["qid"], "span_len_s": r["gold_span_length_s"],
                 "n_scenes": r["n_scenes"], "n_admitted_frames": r["n_admitted_frames"]}
                for r in zero_gold],
            "n_zero_gold_scenes": len(zero_gold),
        },
        "headline": {
            "hit_at_shortlist": rate(rows, "hit_at_shortlist"),
            "effective_hit": rate(rows, "effective_hit"),
            "hit_at_shortlist_anyspan_variant": rate(rows, "hit_at_shortlist_anyspan"),
        },
        "breakdown_hit_at_shortlist": breakdown("hit_at_shortlist"),
        "breakdown_effective_hit": breakdown("effective_hit"),
        "gold_scene_counts": {
            "mean": round(statistics.mean(r["n_gold_scenes"] for r in rows), 3),
            "median": statistics.median(r["n_gold_scenes"] for r in rows),
            "min": min(r["n_gold_scenes"] for r in rows),
            "max": max(r["n_gold_scenes"] for r in rows),
        },
        "n_scenes_stats": {
            "mean": round(statistics.mean(ns_vals), 2), "median": statistics.median(ns_vals),
            "min": min(ns_vals), "max": max(ns_vals), "quartile_cuts": qs,
        },
        "shortlist_width_stats": {
            "mean": round(statistics.mean(r["shortlist_width"] for r in rows), 3),
            "median": statistics.median(r["shortlist_width"] for r in rows),
            "min": min(r["shortlist_width"] for r in rows),
            "max": max(r["shortlist_width"] for r in rows),
            "mean_frac_of_scenes": round(statistics.mean(
                r["shortlist_width"] / r["n_scenes"] for r in rows), 4),
        },
        "frac_gold_captured": {
            "mean": round(statistics.mean(r["frac_gold_captured"] for r in scored), 4),
            "median": statistics.median(r["frac_gold_captured"] for r in scored),
        },
        "best_gold_rank": {
            "n": len(ranks),
            "median": statistics.median(ranks),
            "p90": sorted(ranks)[int(0.90 * (len(ranks) - 1))],
            "p99": sorted(ranks)[int(0.99 * (len(ranks) - 1))],
            "max": max(ranks),
            "mean": round(statistics.mean(ranks), 3),
            "histogram": dict(sorted(hist.items(), key=lambda kv: int(kv[0]))),
        },
        "miss_rank_profile": {
            "n_misses": sum(1 for r in scored if not r["hit_at_shortlist"]),
            "miss_best_gold_ranks_median": (statistics.median(
                [r["best_gold_rank"] for r in scored if not r["hit_at_shortlist"]])
                if any(not r["hit_at_shortlist"] for r in scored) else None),
            "miss_overshoot_over_cutoff": _overshoot_hist(scored),
        },
        "fallback_rates": {
            "scene001_all_scenes_pct": round(
                100 * sum(1 for r in rows if r["fallback_all_scenes_fired"]) / len(rows), 4),
            "empty_pool_pct": round(
                100 * sum(1 for r in rows if r["fallback_empty_pool_fired"]) / len(rows), 4),
            "either_pct": round(100 * sum(
                1 for r in rows if r["fallback_all_scenes_fired"] or r["fallback_empty_pool_fired"]
            ) / len(rows), 4),
        },
        "width_sweep": sweep_agg,
    }
    (OUT_DIR / f"{split}_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[{split}] wrote {csv_path.name} and {split}_summary.json", flush=True)
    return summary


def _overshoot_hist(scored) -> dict:
    """For misses only: best_gold_rank - shortlist_width. Small values mean the
    ranking was nearly right and widening fixes it; large values mean the
    centroid ranking itself is uninformative."""
    over = [r["best_gold_rank"] - r["shortlist_width"] for r in scored if not r["hit_at_shortlist"]]
    if not over:
        return {}
    buckets = defaultdict(int)
    for o in over:
        b = ("1-5" if o <= 5 else "6-20" if o <= 20 else "21-50" if o <= 50
             else "51-100" if o <= 100 else "101-300" if o <= 300 else ">300")
        buckets[b] += 1
    return {"n": len(over), "median": statistics.median(over),
            "p90": sorted(over)[int(0.90 * (len(over) - 1))], "max": max(over),
            "buckets": dict(buckets)}


def main(splits: str = "val_tune,val_confirm"):
    summaries = {}
    for split in splits.split(","):
        summaries[split] = run_split(split.strip())

    with open(OUT_DIR / "width_sweep.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["split", "width_rule", "mean_width", "recall", "n_hit", "n_total",
                    "ci95_lo", "ci95_hi", "mean_pool_frames", "median_pool_frames"])
        for split, s in summaries.items():
            for name, v in s["width_sweep"].items():
                w.writerow([split, name, v["mean_width"], round(v["recall"], 6), v["n_hit"],
                            v["n_total"], v["ci95"][0], v["ci95"][1],
                            v["mean_pool_frames"], v["median_pool_frames"]])

    for split, s in summaries.items():
        h = s["headline"]["effective_hit"]
        print(f"SCENE_SHORTLIST_RECALL: {h['rate']:.4f} ({h['n_hit']}/{h['n']}) "
              f"on {split} @ {s['config_hash']}", flush=True)


# ── report generation ─────────────────────────────────────────────────────
# Every figure in the report is read out of the summary JSONs written above.
# Nothing is hand-typed, so no number in the report can drift from the data.

PREREG_TABLE = """| Effective recall | Reading | Consequence |
|---|---|---|
| **>= 95%** | The scene shortlist is not a major bottleneck. | The loss is downstream -- final frame ranking within an adequate pool. Priority goes to the embedding adapter and window-level selection, not to wider scene search. |
| **85-95%** | Real but secondary loss. | Worth widening, but it cannot alone explain bucket (c) at 64%. Both fixes needed. |
| **70-85%** | **Major bottleneck found.** | IRIS is discarding the correct scene before frame ranking ever runs. Wider and parallel scene search becomes the highest-value change in the pipeline. |
| **< 70%** | Dominant bottleneck. | The centroid shortlist is the primary cause of retrieval failure. Redesign it before anything else. |"""


def prereg_row(rate: float) -> str:
    if rate >= 0.95:
        return ">= 95% (not a major bottleneck)"
    if rate >= 0.85:
        return "85-95% (real but secondary loss)"
    if rate >= 0.70:
        return "70-85% (MAJOR BOTTLENECK FOUND)"
    return "< 70% (dominant bottleneck)"


def merge_width_sweep(summaries: dict) -> None:
    """Rewrite width_sweep.csv from every summary on disk, so a per-split
    re-run never leaves the combined file holding only one split."""
    with open(OUT_DIR / "width_sweep.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["split", "width_rule", "mean_width", "recall", "n_hit", "n_total",
                    "ci95_lo", "ci95_hi", "mean_pool_frames", "median_pool_frames"])
        for split, s in summaries.items():
            for name, v in s["width_sweep"].items():
                w.writerow([split, name, v["mean_width"], round(v["recall"], 6), v["n_hit"],
                            v["n_total"], v["ci95"][0], v["ci95"][1],
                            v["mean_pool_frames"], v["median_pool_frames"]])


def bucket_c_crosscheck() -> dict | None:
    """Join this diagnostic's val_confirm rows against the c24f8f8 gap
    diagnostic's per-question CSV (same 639 questions, same config-hash) to
    decompose bucket (c) into 'lost at the shortlist' vs 'lost downstream'."""
    gap_path = REPO / "tuning" / "val_confirm_e2e_per_question_gap_diagnostic.csv"
    mine_path = OUT_DIR / "val_confirm_per_question.csv"
    if not (gap_path.exists() and mine_path.exists()):
        return None
    tb = lambda s: str(s).strip().lower() in ("true", "1", "yes")
    gap = {(r["video"], r["qid"]): r for r in csv.DictReader(open(gap_path))}
    mine = {(r["video_id"], r["qid"]): r for r in csv.DictReader(open(mine_path))}
    j = set(gap) & set(mine)
    key = [k for k in j if tb(gap[k]["acc_qa"]) and gap[k]["overlap_status"] in ("partial", "zero")]
    c = [k for k in key if not tb(gap[k]["retrieved_frame_in_gold"])]
    miss = {k for k in j if not tb(mine[k]["hit_at_shortlist"])}
    return {
        "gap_csv": str(gap_path), "gap_csv_sha256": sha256_file(gap_path),
        "n_joined": len(j), "key_group": len(key),
        "bucket_c": len(c), "bucket_c_pct_of_key_group": round(100 * len(c) / len(key), 2),
        "shortlist_misses_all_questions": len(miss),
        "bucket_c_also_shortlist_miss": len(set(c) & miss),
        "bucket_c_explained_by_shortlist_pct": round(100 * len(set(c) & miss) / len(c), 2),
        "bucket_c_with_gold_scene_shortlisted": len(set(c) - miss),
        "shortlist_miss_but_retrieval_found_gold": sum(
            1 for k in miss if tb(gap[k]["retrieved_frame_in_gold"])),
    }


def build_report() -> None:
    summaries = {}
    for split in SPLITS:
        p = OUT_DIR / f"{split}_summary.json"
        if p.exists():
            summaries[split] = json.loads(p.read_text())
    if not summaries:
        raise SystemExit("no summaries on disk -- run the measurement first")
    merge_width_sweep(summaries)

    read_artifacts = [
        REPO / "iris" / "scene_retrieval.py",
        REPO / "scripts" / "part3_tune.py",
        REPO / "scripts" / "val_confirm_e2e_eval.py",
        REPO / "scripts" / "parta_survivor_ceiling.py",
        REPO / "eval" / "data" / "nextqa" / "val.csv",
        REPO / "eval" / "data" / "nextqa" / "gsub_val.json",
        REPO / "eval" / "data" / "nextqa" / "gsub_test.json",
        REPO / "split_manifest.json",
        REPO / "tuning" / "frozen_state.json",
        REPO / "survivor_coverage_ceiling_report.md",
        REPO / "tuning" / "val_confirm_gap_diagnostic_report.md",
        REPO / "tuning" / "val_confirm_e2e_per_question_gap_diagnostic.csv",
    ]
    manifest = {str(p.relative_to(REPO)): sha256_file(p) for p in read_artifacts if p.exists()}
    (OUT_DIR / "artifact_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"artifact_manifest": manifest,
                      "bucket_c_crosscheck": bucket_c_crosscheck(),
                      "prereg_row": {k: prereg_row(v["headline"]["effective_hit"]["rate"])
                                     for k, v in summaries.items()}}, indent=2))


def cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", default="val_tune,val_confirm")
    ap.add_argument("--report", action="store_true",
                    help="regenerate width_sweep.csv + artifact manifest from summaries on disk")
    args = ap.parse_args()
    if args.report:
        build_report()
        return
    main(args.splits)


if __name__ == "__main__":
    cli()

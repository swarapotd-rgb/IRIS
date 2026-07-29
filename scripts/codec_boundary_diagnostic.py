"""PHASE 1 -- codec-boundary diagnostic (#5). Retrieval only. No LLM.

Every prior codec experiment tested motion as a SALIENCY score ("is this frame
gold?") and returned AUC ~ 0.50 four times over. This tests a different
quantity: codec as an EVENT-BOUNDARY detector ("where does the next event
start?"). The measured TN/TP failure -- retrieval anchors on the cue event
named in the question rather than the answer event the gold span marks -- is a
boundary problem, not a saliency problem, so a null on saliency does not
settle it.

The experiment is one question: does stepping from the anchor to the next
codec peak land inside a gold span more often than the anchor itself, AND more
often than three controls that carry no codec information?

    C0  the anchor t* itself                    (the number to beat)
    C1  fixed offsets t* +/- {1,2,3,5}s         (is a constant shift enough?)
    C2  random survivor after t*, 20 seeded     (does ANY forward frame do this?)
    C3  nearest survivor after t*, is_peak      (is it "forward", or "peak"?)
        ignored

Without C1/C2/C3 a positive peak result is uninterpretable -- "next peak lands
in gold 40% of the time" means nothing until you know that "a random frame
after the anchor" lands in gold 40% of the time too.

Retrieval config is read live from tuning/frozen_state.json and is NOT varied.
No parameter here is tunable; nothing is selected on any split. Both val_tune
and val_confirm are reported because this is measurement of a fixed pipeline,
not selection -- val_confirm is already spent as a held-out set and no decision
in this script is conditioned on either split's numbers.

ONE consolidated run computes the retrieval pass once and derives every
control, breakdown and summary cell from that single pass. Numbers are never
stitched across invocations.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import statistics
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import iris.ingest as iris_ingest  # noqa: E402
import iris.query as iris_query  # noqa: E402
from iris.retrieval_entry import retrieve_for_question  # noqa: E402
from eval.metrics import _pick_peak_by_clip  # noqa: E402

from part3_tune import load_frozen_state  # noqa: E402
from val_confirm_e2e_eval import make_e2e_config, ingest_config_hash, VIDEO_DIR  # noqa: E402

OUT_DIR = REPO / "tuning" / "codec_boundary"

# Fixed forward/backward offsets for control C1, in seconds. Chosen to bracket
# the observed median anchor->gold offsets (-1.80s .. +1.18s) plus a wide
# outer probe. Not tuned -- a control's job is to be a fixed yardstick.
C1_OFFSETS = [1.0, 2.0, 3.0, 5.0]
C2_DRAWS = 20
C2_SEED = 20260729

QUESTION_TYPES = ["CW", "CH", "TC", "TN", "TP"]
DURATION_BUCKETS = ["<2s", "2-5s", "5-10s", ">=10s"]

CACHE_DIRS = {
    "val_tune": REPO / "tuning" / "index_cache",
    "val_confirm": REPO / "tuning" / "index_cache_val_confirm_e2e",
}


def duration_bucket(gold_spans: list) -> str:
    """Bucket by total gold duration (sum over spans, as the gold span set is
    what a candidate must land inside)."""
    total = sum(float(g[1]) - float(g[0]) for g in gold_spans)
    if total < 2.0:
        return "<2s"
    if total < 5.0:
        return "2-5s"
    if total < 10.0:
        return "5-10s"
    return ">=10s"


def in_gold(t: float | None, gold_spans: list) -> bool | None:
    """None propagates: a candidate that does not exist (no 3rd forward peak,
    no next scene boundary) is not a miss, it is absent, and must not be
    counted in either the numerator or the denominator."""
    if t is None:
        return None
    return any(float(g[0]) <= t <= float(g[1]) for g in gold_spans)


def load_questions(split: str) -> list[dict]:
    """val_tune / val_confirm question lists, carrying `type` (which
    part3_tune.load_val_tune_questions drops and this diagnostic needs for its
    headline breakdown)."""
    manifest = json.loads((REPO / "split_manifest.json").read_text())
    key = {"val_tune": "tune_videos", "val_confirm": "confirm_videos"}[split]
    in_scope = set(manifest[key])
    rows = list(csv.DictReader(
        open(REPO / "eval" / "data" / "nextqa" / "val.csv", newline="", encoding="utf-8")))
    gsub = json.loads((REPO / "eval" / "data" / "nextqa" / "gsub_val.json").read_text())
    out = []
    for r in rows:
        vid = r["video"]
        if vid not in in_scope:
            continue
        if not (VIDEO_DIR / f"{vid}.mp4").exists():
            continue
        gold = gsub.get(vid, {}).get("location", {}).get(r["qid"])
        if not gold:
            continue
        out.append({
            "video": vid, "qid": r["qid"], "question": r["question"], "type": r.get("type"),
            "gold_spans": gold, "duration": gsub[vid]["duration"],
        })
    return out


def scene_boundary_times(index) -> list[float]:
    """Flatten scene_spans {scene_idx: (start, end)} into a sorted list of
    distinct boundary timestamps."""
    spans = getattr(index, "scene_spans", None) or {}
    times = set()
    for start, end in spans.values():
        times.add(float(start))
        times.add(float(end))
    return sorted(times)


PER_Q_FIELDS = [
    "split", "video", "qid", "type", "gold_spans", "gold_duration_s", "duration_bucket",
    "anchor_t", "used_clip_anchor", "anchor_in_gold",
    "fwd_peak1_t", "fwd_peak1_in_gold", "fwd_peak2_t", "fwd_peak2_in_gold",
    "fwd_peak3_t", "fwd_peak3_in_gold",
    "bwd_peak1_t", "bwd_peak1_in_gold", "bwd_peak2_t", "bwd_peak2_in_gold",
    "bwd_peak3_t", "bwd_peak3_in_gold",
    "fwd_scene_t", "fwd_scene_in_gold", "bwd_scene_t", "bwd_scene_in_gold",
    "c3_next_survivor_t", "c3_next_survivor_in_gold",
    "c2_random_survivor_mean_in_gold", "c2_n_draws",
    "n_forward_peaks", "dist_to_next_peak_s",
    "n_survivors", "n_peaks_in_video", "n_retrieved",
]
PER_Q_FIELDS += [f"c1_fwd_{int(o)}s_t" for o in C1_OFFSETS]
PER_Q_FIELDS += [f"c1_fwd_{int(o)}s_in_gold" for o in C1_OFFSETS]
PER_Q_FIELDS += [f"c1_bwd_{int(o)}s_t" for o in C1_OFFSETS]
PER_Q_FIELDS += [f"c1_bwd_{int(o)}s_in_gold" for o in C1_OFFSETS]


def run_split(split: str, cfg, cfg_hash: str, log) -> tuple[list[dict], dict]:
    """One consolidated retrieval pass over a split. Every candidate and every
    control for a question is derived from that question's single retrieval,
    so no two numbers in the output can disagree about what was retrieved."""
    questions = load_questions(split)
    video_ids = sorted({q["video"] for q in questions})
    cache_dir = CACHE_DIRS[split]

    # Hard pre-flight: every needed index must already be cached. The task
    # expects zero fresh ingests; a miss is a stop condition, not something to
    # silently ingest through (an ingest here would mean the config drifted).
    missing = [v for v in video_ids
               if not (cache_dir / f"{v}__{cfg_hash}.npz").exists()]
    if missing:
        raise SystemExit(
            f"[{split}] ABORT: {len(missing)} video(s) have no cached index under "
            f"config-hash {cfg_hash} in {cache_dir}: {missing[:10]}"
            f"{'...' if len(missing) > 10 else ''}. This diagnostic must not "
            "trigger a fresh ingest -- a cache miss means the ingest-relevant "
            "config no longer matches the frozen state."
        )
    log(f"[{split}] {len(questions)} questions / {len(video_ids)} videos; "
        f"all indexes cache-hit under {cfg_hash} (0 fresh ingests)")

    rows: list[dict] = []
    failures: list[dict] = []
    index_cache: dict = {}
    t0 = time.perf_counter()

    for i, q in enumerate(questions, 1):
        vid = q["video"]
        try:
            if vid not in index_cache:
                index_cache.clear()  # questions are grouped by video in CSV order
                index_cache[vid] = iris_ingest.load_index(str(cache_dir / f"{vid}__{cfg_hash}"))
            index = index_cache[vid]

            retrieved, _plan, _tel = retrieve_for_question(
                q["question"], index, cfg, type_code=q.get("type"), family=None,
            )
            query_embedding, _ = iris_query._call_embed_query(q["question"], cfg)

            # The anchor, picked EXACTLY as Method D picks it today
            # (eval.metrics.predicted_span_from_frames_peak): highest
            # CLIP-similarity frame in the retrieved pool, degrading to rank-1.
            peak = _pick_peak_by_clip(retrieved, query_embedding)
            used_clip_anchor = peak is not None
            if peak is None:
                if not retrieved:
                    raise RuntimeError("empty retrieval pool")
                peak = retrieved[0]
            t_star = float(peak["timestamp"])

            gold = q["gold_spans"]
            survivors = sorted(index.frames, key=lambda f: f.timestamp)
            surv_t = [float(f.timestamp) for f in survivors]
            peak_t = [float(f.timestamp) for f in survivors if f.is_peak]

            fwd_peaks = [t for t in peak_t if t > t_star][:3]
            bwd_peaks = [t for t in peak_t if t < t_star][-3:][::-1]  # nearest first

            boundaries = scene_boundary_times(index)
            fwd_scene = next((t for t in boundaries if t > t_star), None)
            bwd_scene = next((t for t in reversed(boundaries) if t < t_star), None)

            # C3 -- nearest survivor after t* regardless of is_peak. Isolates
            # "peak" from "forward": if C3 matches the peak step, the peak flag
            # contributed nothing beyond moving forward at all.
            fwd_survivors = [t for t in surv_t if t > t_star]
            c3 = fwd_survivors[0] if fwd_survivors else None

            # C2 -- random survivor after t*, 20 seeded draws. Seeded per
            # (video, qid) so the draw is reproducible and independent of
            # iteration order.
            if fwd_survivors:
                rng = random.Random(f"{C2_SEED}:{vid}:{q['qid']}")
                draws = [rng.choice(fwd_survivors) for _ in range(C2_DRAWS)]
                c2_hits = [1.0 if in_gold(t, gold) else 0.0 for t in draws]
                c2_mean = statistics.mean(c2_hits)
            else:
                c2_mean = None

            total_gold = sum(float(g[1]) - float(g[0]) for g in gold)
            row = {
                "split": split, "video": vid, "qid": q["qid"], "type": q.get("type"),
                "gold_spans": json.dumps(gold),
                "gold_duration_s": round(total_gold, 4),
                "duration_bucket": duration_bucket(gold),
                "anchor_t": round(t_star, 4), "used_clip_anchor": used_clip_anchor,
                "anchor_in_gold": in_gold(t_star, gold),
                "fwd_scene_t": fwd_scene, "fwd_scene_in_gold": in_gold(fwd_scene, gold),
                "bwd_scene_t": bwd_scene, "bwd_scene_in_gold": in_gold(bwd_scene, gold),
                "c3_next_survivor_t": c3, "c3_next_survivor_in_gold": in_gold(c3, gold),
                "c2_random_survivor_mean_in_gold": c2_mean,
                "c2_n_draws": C2_DRAWS if fwd_survivors else 0,
                "n_forward_peaks": len([t for t in peak_t if t > t_star]),
                "dist_to_next_peak_s": (round(fwd_peaks[0] - t_star, 4) if fwd_peaks else None),
                "n_survivors": len(survivors), "n_peaks_in_video": len(peak_t),
                "n_retrieved": len(retrieved),
            }
            for k in range(3):
                ft = fwd_peaks[k] if k < len(fwd_peaks) else None
                bt = bwd_peaks[k] if k < len(bwd_peaks) else None
                row[f"fwd_peak{k + 1}_t"] = ft
                row[f"fwd_peak{k + 1}_in_gold"] = in_gold(ft, gold)
                row[f"bwd_peak{k + 1}_t"] = bt
                row[f"bwd_peak{k + 1}_in_gold"] = in_gold(bt, gold)
            for o in C1_OFFSETS:
                # Clamped to [0, duration] the same way Method D clamps its
                # span, so a control is never credited or penalised for a
                # timestamp outside the video.
                ft = min(float(q["duration"]), t_star + o)
                bt = max(0.0, t_star - o)
                row[f"c1_fwd_{int(o)}s_t"] = round(ft, 4)
                row[f"c1_fwd_{int(o)}s_in_gold"] = in_gold(ft, gold)
                row[f"c1_bwd_{int(o)}s_t"] = round(bt, 4)
                row[f"c1_bwd_{int(o)}s_in_gold"] = in_gold(bt, gold)
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            failures.append({"video": vid, "qid": q["qid"], "error": f"{type(exc).__name__}: {exc}",
                             "traceback": tb})
            log(f"[{split}] FAIL video={vid} qid={q['qid']}: {type(exc).__name__}: {exc}")

        if i % 250 == 0 or i == len(questions):
            el = time.perf_counter() - t0
            log(f"[{split}] {i}/{len(questions)} ok={len(rows)} failed={len(failures)} "
                f"elapsed={el:.0f}s")

    return rows, {"n_questions": len(questions), "n_scored": len(rows),
                  "n_failed": len(failures), "failures": failures,
                  "n_videos": len(video_ids), "wall_s": time.perf_counter() - t0}


def rate(rows: list[dict], field: str) -> dict:
    """In-gold rate over the rows where the candidate EXISTS. n is reported
    alongside so a rate computed over a shrunken denominator is visible rather
    than silently comparable to a full-denominator one."""
    vals = [r[field] for r in rows if r.get(field) is not None]
    if not vals:
        return {"rate": None, "n": 0, "n_total": len(rows)}
    return {"rate": sum(1 for v in vals if v) / len(vals), "n": len(vals), "n_total": len(rows)}


def mean_rate(rows: list[dict], field: str) -> dict:
    """C2's per-question mean-of-draws, aggregated. SD is across questions."""
    vals = [r[field] for r in rows if r.get(field) is not None]
    if not vals:
        return {"rate": None, "sd": None, "n": 0, "n_total": len(rows)}
    return {
        "rate": statistics.mean(vals),
        "sd": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
        "n": len(vals), "n_total": len(rows),
    }


CANDIDATE_FIELDS = (
    ["anchor_in_gold"]
    + [f"fwd_peak{k}_in_gold" for k in (1, 2, 3)]
    + [f"bwd_peak{k}_in_gold" for k in (1, 2, 3)]
    + ["fwd_scene_in_gold", "bwd_scene_in_gold", "c3_next_survivor_in_gold"]
    + [f"c1_fwd_{int(o)}s_in_gold" for o in C1_OFFSETS]
    + [f"c1_bwd_{int(o)}s_in_gold" for o in C1_OFFSETS]
)


def summarize(rows: list[dict]) -> dict:
    out = {f: rate(rows, f) for f in CANDIDATE_FIELDS}
    out["c2_random_survivor_in_gold"] = mean_rate(rows, "c2_random_survivor_mean_in_gold")
    dists = [r["dist_to_next_peak_s"] for r in rows if r.get("dist_to_next_peak_s") is not None]
    out["_meta"] = {
        "n": len(rows),
        "n_no_forward_peak": sum(1 for r in rows if r["n_forward_peaks"] == 0),
        "median_dist_to_next_peak_s": statistics.median(dists) if dists else None,
        "mean_dist_to_next_peak_s": statistics.mean(dists) if dists else None,
    }
    return out


BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260729


def paired_cluster_bootstrap(rows: list[dict], field_a: str, field_b: str) -> dict:
    """Video-clustered paired bootstrap on the in-gold rate difference
    (field_a - field_b), over questions where BOTH candidates exist.

    A raw `rate_a > rate_b` inequality is not a result at these effect sizes --
    a 0.2-point gap on n=167 is a fifth of one question. This reports the
    difference with a 95% CI so a verdict can say whether the interval excludes
    zero instead of leaning on the sign of a hairline margin.

    Clustered by video because questions from the same video share a retrieval
    index, an anchor distribution and a gold-span structure, so treating them
    as independent would understate the interval.
    """
    paired = [r for r in rows if r.get(field_a) is not None and r.get(field_b) is not None]
    if not paired:
        return {"n": 0, "delta": None, "ci95": None, "excludes_zero": None}

    by_video: dict[str, list[tuple[int, int]]] = {}
    for r in paired:
        by_video.setdefault(r["video"], []).append((int(bool(r[field_a])), int(bool(r[field_b]))))
    videos = sorted(by_video)

    def delta_of(sample_videos: list[str]) -> float | None:
        a = b = n = 0
        for v in sample_videos:
            for xa, xb in by_video[v]:
                a += xa
                b += xb
                n += 1
        return None if n == 0 else (a - b) / n

    observed = delta_of(videos)
    rng = random.Random(BOOTSTRAP_SEED)
    deltas = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = [videos[rng.randrange(len(videos))] for _ in range(len(videos))]
        d = delta_of(sample)
        if d is not None:
            deltas.append(d)
    deltas.sort()
    lo = deltas[int(0.025 * len(deltas))]
    hi = deltas[min(len(deltas) - 1, int(0.975 * len(deltas)))]
    return {
        "n": len(paired), "n_clusters": len(videos),
        "delta": observed, "ci95": [lo, hi],
        "excludes_zero": bool(lo > 0 or hi < 0),
    }


def verdict_for(block: dict, rows: list[dict] | None = None) -> dict:
    """Does the next-peak-after-anchor beat ALL THREE controls?

    'Beat' is stated against the strongest (max) C1 forward offset, not the
    average of them -- a step forward that only beats the weakest fixed offset
    has not demonstrated that the peak carries information.

    Two verdicts are reported, and they are NOT interchangeable:
      beats_all_three_controls           raw point-estimate inequality
      beats_all_three_controls_significant  every one of those gaps is also
                                         positive with a 95% CI excluding zero
    The second is the one that means anything.
    """
    peak = block["fwd_peak1_in_gold"]["rate"]
    c1_all = [block[f"c1_fwd_{int(o)}s_in_gold"]["rate"] for o in C1_OFFSETS]
    c1_all = [x for x in c1_all if x is not None]
    c1_best = max(c1_all) if c1_all else None
    c2 = block["c2_random_survivor_in_gold"]["rate"]
    c3 = block["c3_next_survivor_in_gold"]["rate"]
    anchor = block["anchor_in_gold"]["rate"]
    if peak is None:
        return {"beats_all_controls": None, "reason": "no forward peak anywhere"}
    beats = {
        "vs_C0_anchor": None if anchor is None else peak > anchor,
        "vs_C1_best_fixed_offset": None if c1_best is None else peak > c1_best,
        "vs_C2_random_survivor": None if c2 is None else peak > c2,
        "vs_C3_nearest_survivor": None if c3 is None else peak > c3,
    }
    control_checks = [beats["vs_C1_best_fixed_offset"], beats["vs_C2_random_survivor"],
                      beats["vs_C3_nearest_survivor"]]

    out = {
        "fwd_peak1_rate": peak, "C0_anchor": anchor, "C1_best_fwd": c1_best,
        "C2_random": c2, "C3_nearest": c3,
        "beats": beats,
        "beats_all_three_controls": all(x is True for x in control_checks),
    }

    if rows is not None:
        # C2 is a per-question mean over 20 draws, not a per-question binary, so
        # it has no paired-binary CI here; its gap is reported as a point
        # estimate and the CI columns cover the binary controls C0/C1/C3.
        best_off = None
        best_rate = -1.0
        for o in C1_OFFSETS:
            r = block[f"c1_fwd_{int(o)}s_in_gold"]["rate"]
            if r is not None and r > best_rate:
                best_rate, best_off = r, o
        ci = {
            "vs_C0_anchor": paired_cluster_bootstrap(rows, "fwd_peak1_in_gold", "anchor_in_gold"),
            "vs_C3_nearest_survivor": paired_cluster_bootstrap(
                rows, "fwd_peak1_in_gold", "c3_next_survivor_in_gold"),
        }
        if best_off is not None:
            ci["vs_C1_best_fixed_offset"] = paired_cluster_bootstrap(
                rows, "fwd_peak1_in_gold", f"c1_fwd_{int(best_off)}s_in_gold")
            ci["vs_C1_best_fixed_offset"]["offset_s"] = best_off
        out["paired_ci"] = ci
        out["beats_all_three_controls_significant"] = bool(
            out["beats_all_three_controls"]
            and all(c.get("excludes_zero") and (c.get("delta") or 0) > 0
                    for k, c in ci.items() if k != "vs_C0_anchor")
        )
    return out


def build_summary(rows: list[dict]) -> dict:
    by_type = {t: summarize([r for r in rows if r["type"] == t]) for t in QUESTION_TYPES}
    outside = [r for r in rows if r["anchor_in_gold"] is False]
    rows_of_type = {t: [r for r in rows if r["type"] == t] for t in QUESTION_TYPES}
    outside_of_type = {t: [r for r in outside if r["type"] == t] for t in QUESTION_TYPES}
    return {
        "overall": summarize(rows),
        "by_type": by_type,
        "by_duration_bucket": {
            b: summarize([r for r in rows if r["duration_bucket"] == b]) for b in DURATION_BUCKETS
        },
        # The headline. A boundary step can only ever rescue a question whose
        # anchor is currently OUTSIDE gold -- on the rest it can only do harm.
        "anchor_outside_gold_recovery": {
            "n": len(outside),
            "overall": summarize(outside),
            "by_type": {t: summarize([r for r in outside if r["type"] == t])
                        for t in QUESTION_TYPES},
        },
        "verdict_overall": verdict_for(summarize(rows), rows),
        "verdict_by_type": {t: verdict_for(by_type[t], rows_of_type[t]) for t in QUESTION_TYPES},
        "verdict_by_type_anchor_outside": {
            t: verdict_for(summarize(outside_of_type[t]), outside_of_type[t])
            for t in QUESTION_TYPES
        },
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--splits", nargs="+", default=["val_tune", "val_confirm"],
                   choices=["val_tune", "val_confirm"])
    p.add_argument("--out-dir", default=str(OUT_DIR))
    args = p.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_fh = open(out_dir / "run.log", "a", buffering=1)

    def log(msg: str) -> None:
        line = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {msg}"
        print(line, flush=True)
        log_fh.write(line + "\n")

    frozen = load_frozen_state()["frozen"]
    cfg = make_e2e_config(frozen, None)
    cfg_hash = ingest_config_hash(cfg)
    log(f"[setup] frozen={frozen}")
    log(f"[setup] ingest_config_hash={cfg_hash} (retrieval params NOT modified)")

    (out_dir / "environment.json").write_text(json.dumps({
        "git_head": os.popen("git rev-parse HEAD").read().strip(),
        "frozen": frozen,
        "ingest_config_hash": cfg_hash,
        "c1_offsets_s": C1_OFFSETS,
        "c2_draws": C2_DRAWS, "c2_seed": C2_SEED,
        "python": sys.version,
        "splits": args.splits,
    }, indent=2))

    summary: dict = {"splits": {}}
    for split in args.splits:
        rows, meta = run_split(split, cfg, cfg_hash, log)
        csv_path = out_dir / f"per_question_{split.replace('_', '')}.csv"
        # Historical/spec filenames: per_question_valtune.csv, per_question_valconfirm.csv
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=PER_Q_FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in PER_Q_FIELDS})
        log(f"[{split}] wrote {len(rows)} rows -> {csv_path.name}")
        summary["splits"][split] = {"run_meta": meta, **build_summary(rows)}

    (out_dir / "boundary_summary.json").write_text(json.dumps(summary, indent=2))
    log(f"[done] wrote boundary_summary.json")
    log_fh.close()


if __name__ == "__main__":
    main()

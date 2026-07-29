"""Phase 2/3 analysis: per-arm metrics, per-type breakdowns, and paired
video-clustered bootstrap CIs.

Reads the per-question CSVs each arm already flushed and derives every reported
cell from them. It does NOT re-run any arm and does NOT recompute anything that
required the answerer -- so no number here can disagree with the run that
produced it.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260729
QUESTION_TYPES = ["CW", "CH", "TC", "TN", "TP"]


def load_arm(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["_qa"] = r["acc_qa"] == "True"
        r["_gqa"] = r["acc_gqa_unverified"] == "True"
        r["_iop"] = float(r["iop"])
        r["_nonempty"] = r["raw_answer_nonempty"] == "True"
        r["_parsed"] = r["pred_answer_idx"] not in ("", "None", None)
    return rows


def arm_metrics(rows: list[dict]) -> dict:
    n = len(rows)
    grounded = [r for r in rows if r["_iop"] >= 0.5]
    letters = Counter(r["pred_answer_label"] or "<none>" for r in rows)

    def block(sub: list[dict]) -> dict:
        m = len(sub)
        return {
            "n": m,
            "Acc@QA": sum(r["_qa"] for r in sub) / m if m else None,
            "Acc@GQA": sum(r["_gqa"] for r in sub) / m if m else None,
            "IoP@0.5": sum(1 for r in sub if r["_iop"] >= 0.5) / m if m else None,
        }

    return {
        "n": n,
        "Acc@QA": sum(r["_qa"] for r in rows) / n,
        "Acc@QA_count": f"{sum(r['_qa'] for r in rows)}/{n}",
        "Acc@GQA": sum(r["_gqa"] for r in rows) / n,
        "Acc@GQA_count": f"{sum(r['_gqa'] for r in rows)}/{n}",
        "IoP@0.5": sum(1 for r in rows if r["_iop"] >= 0.5) / n,
        "P_correct_given_IoP>=0.5": (sum(r["_qa"] for r in grounded) / len(grounded)
                                     if grounded else None),
        "n_grounded": len(grounded),
        # A "parse failure" is a response the MC parser could not map to a
        # letter; a "refusal" here is an empty/whitespace-only generation. The
        # per-question CSV does not retain raw answer text, so refusal is
        # measured as emptiness, not as declining language -- stated plainly
        # rather than dressed up as a semantic refusal detector.
        "parse_failure_rate": sum(1 for r in rows if not r["_parsed"]) / n,
        "refusal_rate_empty_generation": sum(1 for r in rows if not r["_nonempty"]) / n,
        "answer_letter_distribution": {k: letters[k] / n for k in sorted(letters)},
        "answer_letter_counts": dict(sorted(letters.items())),
        "by_type": {t: block([r for r in rows if r["type"] == t]) for t in QUESTION_TYPES},
    }


def paired_bootstrap(rows_a: list[dict], rows_b: list[dict], key: str) -> dict:
    """Paired video-clustered bootstrap on (B - A) for a binary per-question
    metric. Clusters are videos: questions from one video share retrieval, an
    index and a gold structure, so treating them as independent would give a
    falsely narrow interval.

    Pairing is by (video, qid), so a question missing from either arm is
    dropped from both rather than silently mismatched by row position.
    """
    a_by = {(r["video"], r["qid"]): r for r in rows_a}
    b_by = {(r["video"], r["qid"]): r for r in rows_b}
    common = sorted(set(a_by) & set(b_by))
    by_video: dict[str, list[tuple[int, int]]] = {}
    for k in common:
        by_video.setdefault(k[0], []).append((int(a_by[k][key]), int(b_by[k][key])))
    videos = sorted(by_video)

    def delta(sample: list[str]) -> float | None:
        a = b = n = 0
        for v in sample:
            for xa, xb in by_video[v]:
                a += xa
                b += xb
                n += 1
        return None if n == 0 else (b - a) / n

    observed = delta(videos)
    rng = random.Random(BOOTSTRAP_SEED)
    deltas = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        s = [videos[rng.randrange(len(videos))] for _ in range(len(videos))]
        d = delta(s)
        if d is not None:
            deltas.append(d)
    deltas.sort()
    lo = deltas[int(0.025 * len(deltas))]
    hi = deltas[min(len(deltas) - 1, int(0.975 * len(deltas)))]
    return {
        "n_paired": len(common), "n_clusters": len(videos), "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED, "delta": observed, "ci95": [lo, hi],
        "excludes_zero": bool(lo > 0 or hi < 0),
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", default=str(REPO / "tuning" / "caption_repair"))
    p.add_argument("--arms", nargs="+", required=True,
                   help="Arm tags to analyse, baseline FIRST (e.g. A B C D).")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    d = Path(args.dir)
    arms: dict[str, list[dict]] = {}
    for tag in args.arms:
        path = d / f"arm_{tag}_per_question.csv"
        if not path.exists():
            print(f"[analysis] MISSING arm {tag}: {path} -- reported as not run")
            continue
        arms[tag] = load_arm(path)

    baseline = args.arms[0]
    out = {
        "arms_present": sorted(arms),
        "arms_missing": [t for t in args.arms if t not in arms],
        "baseline_arm": baseline,
        "metrics": {t: arm_metrics(r) for t, r in arms.items()},
    }

    # Spans are constructed before the answerer runs and none of these arms
    # touches retrieval or span method, so IoP@0.5 MUST be bit-identical across
    # arms. If it is not, something leaked from the answer stage back into
    # grounding and every comparison below is void.
    iops = {t: out["metrics"][t]["IoP@0.5"] for t in arms}
    out["iop_identical_across_arms"] = len(set(round(v, 12) for v in iops.values())) <= 1
    out["iop_at_0.5_per_arm"] = iops

    out["bootstrap"] = {}
    if baseline in arms:
        for tag in arms:
            if tag == baseline:
                continue
            out["bootstrap"][f"{tag}_vs_{baseline}"] = {
                "Acc@QA": paired_bootstrap(arms[baseline], arms[tag], "_qa"),
                "Acc@GQA": paired_bootstrap(arms[baseline], arms[tag], "_gqa"),
            }

    out_path = Path(args.out) if args.out else d / "bootstrap_ci.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "metrics"}, indent=2)[:3000])
    for t, m in out["metrics"].items():
        print(f"  arm {t}: Acc@QA={m['Acc@QA_count']} ({m['Acc@QA']:.4f})  "
              f"Acc@GQA={m['Acc@GQA_count']} ({m['Acc@GQA']:.4f})  "
              f"IoP@0.5={m['IoP@0.5']:.4f}  P(c|IoP>=.5)={m['P_correct_given_IoP>=0.5']:.4f}")
    print(f"[analysis] wrote {out_path}")


if __name__ == "__main__":
    main()

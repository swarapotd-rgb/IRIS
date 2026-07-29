"""Phase 3: bootstrap 95% CIs on Acc@QA for every arm, plus the decisive
E-vs-G paired comparison.

Three distinct quantities, kept separate on purpose because they answer
different questions and are routinely conflated:

  1. per_arm_absolute  -- video-clustered one-sample bootstrap on each arm's own
     Acc@QA. This is the "every arm's CI" column. These intervals are WIDE and
     they overlap almost everywhere, because they carry the between-video
     variance of the split itself, which is common to all arms and cancels in a
     paired test. Non-overlap here is sufficient for a difference; overlap here
     is NOT evidence of no difference.

  2. delta_vs_A -- the Phase 2 methodology (scripts/caption_repair_analysis.py
     paired_bootstrap), extended to every arm. Same clustering, same seed, same
     resample count.

  3. paired_E_vs_G -- the decisive test. E and G differ only in WHICH question
     the captioner saw, so the paired delta cancels question difficulty,
     retrieval, and span construction. Restricted to the 634 questions Arm G
     could derange; the 5 single-question-video rows are absent from G and drop
     out of both sides rather than being compared against nothing.

Reads only the per-question CSVs the arms already flushed. Re-runs nothing.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Same constants as scripts/caption_repair_analysis.py -- the Phase 2 CI column
# and this one must not differ by resample count or seed.
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260729


def load_arm(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["_qa"] = int(r["acc_qa"] == "True")
        r["_gqa"] = int(r["acc_gqa_unverified"] == "True")
    return rows


def _percentile_ci(values: list[float]) -> list[float]:
    values.sort()
    lo = values[int(0.025 * len(values))]
    hi = values[min(len(values) - 1, int(0.975 * len(values)))]
    return [lo, hi]


def absolute_bootstrap(rows: list[dict], key: str) -> dict:
    """One-sample video-clustered bootstrap on a binary per-question metric."""
    by_video: dict[str, list[int]] = {}
    for r in rows:
        by_video.setdefault(r["video"], []).append(r[key])
    videos = sorted(by_video)

    def rate(sample: list[str]) -> float | None:
        s = n = 0
        for v in sample:
            for x in by_video[v]:
                s += x
                n += 1
        return None if n == 0 else s / n

    observed = rate(videos)
    rng = random.Random(BOOTSTRAP_SEED)
    draws = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        s = [videos[rng.randrange(len(videos))] for _ in range(len(videos))]
        d = rate(s)
        if d is not None:
            draws.append(d)
    return {
        "n": len(rows), "n_clusters": len(videos),
        "point": observed, "ci95": _percentile_ci(draws),
        "resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED,
    }


def paired_bootstrap(rows_a: list[dict], rows_b: list[dict], key: str) -> dict:
    """Paired video-clustered bootstrap on (B - A). Identical in method to
    scripts/caption_repair_analysis.py:paired_bootstrap -- pairing on
    (video, qid) so a question missing from either arm drops from both."""
    a_by = {(r["video"], r["qid"]): r for r in rows_a}
    b_by = {(r["video"], r["qid"]): r for r in rows_b}
    common = sorted(set(a_by) & set(b_by))
    only_a = sorted(set(a_by) - set(b_by))
    only_b = sorted(set(b_by) - set(a_by))
    by_video: dict[str, list[tuple[int, int]]] = {}
    for k in common:
        by_video.setdefault(k[0], []).append((a_by[k][key], b_by[k][key]))
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
    draws = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        s = [videos[rng.randrange(len(videos))] for _ in range(len(videos))]
        d = delta(s)
        if d is not None:
            draws.append(d)
    ci = _percentile_ci(draws)
    # Discordant pairs: the only rows that carry any information about the
    # direction of the difference. Reported so a null result can be read as
    # "no effect" vs "too few informative rows to tell".
    b_gt_a = sum(1 for v in videos for xa, xb in by_video[v] if xb > xa)
    a_gt_b = sum(1 for v in videos for xa, xb in by_video[v] if xa > xb)
    return {
        "n_paired": len(common), "n_clusters": len(videos),
        "n_only_in_A": len(only_a), "n_only_in_B": len(only_b),
        "dropped_keys_only_in_A": only_a[:10],
        "delta": observed, "ci95": ci, "excludes_zero": bool(ci[0] > 0 or ci[1] < 0),
        "n_discordant_B_better": b_gt_a, "n_discordant_A_better": a_gt_b,
        "resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED,
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", default=str(REPO / "tuning" / "caption_repair"))
    p.add_argument("--arms", nargs="+", default=list("ABCDEFG"))
    p.add_argument("--baseline", default="A")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    d = Path(args.dir)
    arms: dict[str, list[dict]] = {}
    missing: list[str] = []
    for tag in args.arms:
        path = d / f"arm_{tag}_per_question.csv"
        if not path.exists():
            missing.append(tag)
            print(f"[ci] MISSING arm {tag}: {path} -- reported as not run")
            continue
        arms[tag] = load_arm(path)

    out: dict = {
        "arms_present": sorted(arms), "arms_missing": missing,
        "baseline_arm": args.baseline,
        "row_counts": {t: len(r) for t, r in arms.items()},
        "per_arm_absolute": {},
        "delta_vs_baseline": {},
    }

    for tag, rows in arms.items():
        out["per_arm_absolute"][tag] = {
            "Acc@QA": absolute_bootstrap(rows, "_qa"),
            "Acc@GQA": absolute_bootstrap(rows, "_gqa"),
        }

    if args.baseline in arms:
        for tag in arms:
            if tag == args.baseline:
                continue
            out["delta_vs_baseline"][f"{tag}_vs_{args.baseline}"] = {
                "Acc@QA": paired_bootstrap(arms[args.baseline], arms[tag], "_qa"),
                "Acc@GQA": paired_bootstrap(arms[args.baseline], arms[tag], "_gqa"),
            }

    if "E" in arms and "G" in arms:
        out["paired_E_vs_G"] = {
            "Acc@QA": paired_bootstrap(arms["G"], arms["E"], "_qa"),
            "Acc@GQA": paired_bootstrap(arms["G"], arms["E"], "_gqa"),
            "note": "delta = E - G. Positive means question-aware captioning beats "
                    "its own deranged control, i.e. the gain is not pure leakage.",
        }
        # E restricted to G's row set, so the point estimates being compared are
        # over the same questions rather than 639 vs 634.
        g_keys = {(r["video"], r["qid"]) for r in arms["G"]}
        e_sub = [r for r in arms["E"] if (r["video"], r["qid"]) in g_keys]
        out["E_restricted_to_G_rows"] = {
            "n": len(e_sub),
            "Acc@QA": statistics.mean(r["_qa"] for r in e_sub) if e_sub else None,
            "Acc@GQA": statistics.mean(r["_gqa"] for r in e_sub) if e_sub else None,
        }

    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"[ci] arms present: {sorted(arms)}  missing: {missing}")
    for tag in sorted(arms):
        a = out["per_arm_absolute"][tag]["Acc@QA"]
        print(f"  arm {tag}: n={out['row_counts'][tag]:4d}  Acc@QA={a['point']:.4f}  "
              f"95% CI [{a['ci95'][0]:.4f}, {a['ci95'][1]:.4f}]")
    if "paired_E_vs_G" in out:
        eg = out["paired_E_vs_G"]["Acc@QA"]
        print(f"  E-vs-G paired: delta={eg['delta']:+.4f} CI [{eg['ci95'][0]:+.4f}, "
              f"{eg['ci95'][1]:+.4f}] excludes_zero={eg['excludes_zero']} "
              f"n_paired={eg['n_paired']}")
    print(f"[ci] wrote {args.out}")


if __name__ == "__main__":
    main()

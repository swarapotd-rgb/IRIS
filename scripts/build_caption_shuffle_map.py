"""Phase 3 Arm G -- build the seeded caption-question derangement.

Arm G exists because question-aware captioning injects the question text into
the CAPTIONER's prompt. A caption that merely paraphrases the question would
lift Acc@QA without adding one bit of visual grounding: the answerer would just
be reading the question a second time, laundered through the caption field.

The control: caption each frame using a DIFFERENT question from the same video,
then answer the original question with those captions. If E ~= G the gain is
question leakage. If E > G with a CI excluding zero the gain is real.

Within-video is the right scope. A donor question from a different video would
describe content that is not in these frames at all, which would degrade
captions for a reason that has nothing to do with leakage and would make G an
unfair floor rather than a control.

A derangement (no qid maps to itself) is enforced, not hoped for: a single
self-map silently converts that row into Arm E.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))


def _derange(items: list[str], rng: random.Random) -> list[str]:
    """Random derangement by rejection sampling, then a guaranteed-correct
    fallback. Rejection is fast for n >= 2 (the probability a shuffle is a
    derangement tends to 1/e ~ 0.37), and the cyclic-shift fallback removes any
    chance of an unbounded loop on a pathological rng."""
    n = len(items)
    if n < 2:
        raise ValueError("cannot derange fewer than 2 items")
    for _ in range(100):
        shuffled = items[:]
        rng.shuffle(shuffled)
        if all(a != b for a, b in zip(items, shuffled)):
            return shuffled
    # Cyclic shift by 1 is a derangement for every n >= 2.
    return items[1:] + items[:1]


def build_shuffle_map(questions: list[dict], seed: int) -> tuple[dict, dict]:
    """questions: [{"video", "qid", ...}]. Returns ({video: {qid: donor_qid}}, stats)."""
    by_video: dict[str, list[str]] = {}
    for q in questions:
        by_video.setdefault(q["video"], []).append(str(q["qid"]))

    mapping: dict[str, dict[str, str]] = {}
    n_excluded = 0
    excluded_videos: list[str] = []
    for vid in sorted(by_video):
        qids = sorted(by_video[vid])
        if len(qids) < 2:
            # Nothing to borrow from. Excluded and reported -- never self-mapped.
            n_excluded += 1
            excluded_videos.append(vid)
            continue
        rng = random.Random(f"{seed}:{vid}")  # per-video seed -> order-independent
        donors = _derange(qids, rng)
        mapping[vid] = dict(zip(qids, donors))

    n_self = sum(1 for v in mapping.values() for k, d in v.items() if k == d)
    n_mapped = sum(len(v) for v in mapping.values())
    stats = {
        "seed": seed,
        "n_questions_in": len(questions),
        "n_questions_mapped": n_mapped,
        "n_videos_mapped": len(mapping),
        "n_videos_excluded_single_question": n_excluded,
        "excluded_videos": excluded_videos,
        "n_self_maps": n_self,
    }
    return mapping, stats


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", default="val_confirm")
    p.add_argument("--seed", type=int, default=20260729)
    p.add_argument("--out", default=str(REPO / "tuning" / "caption_repair" / "shuffle_map.json"))
    args = p.parse_args(argv)

    from val_confirm_e2e_eval import load_split_questions
    questions = load_split_questions(args.split)
    mapping, stats = build_shuffle_map(questions, args.seed)

    if stats["n_self_maps"]:
        raise SystemExit(f"[shuffle] ABORT: {stats['n_self_maps']} self-map(s) produced")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"_stats": stats, **mapping}, indent=2))
    # The eval harness reads {video: {qid: donor}}; "_stats" is a reserved key
    # it never looks up, since video ids are numeric strings.
    print(f"[shuffle] {json.dumps(stats, indent=2)}")
    print(f"[shuffle] wrote {out}")


if __name__ == "__main__":
    main()

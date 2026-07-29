"""Re-measure caption quality with ONE definition applied to every dump.

The baseline audit's headline figures (3.0% temporal, 52.9% action verb, 15.6%
of questions with zero action verbs, 0.343 mean within-question Jaccard, median
42 words) were reported without a committed word list, so those exact lexicons
cannot be reloaded. Rather than guess at them and then compare a new dump
against numbers produced by an unknown definition, this script measures BOTH
the frozen baseline dump and every new dump with the word lists below. The
before/after comparison is therefore internally consistent, and the recomputed
baseline is printed next to the historically-stated one so any definitional gap
is visible instead of buried.

Metrics, per dump:
  pct_with_temporal_word          any word signalling sequence/time
  pct_with_action_verb            any verb denoting a physical act
  pct_questions_zero_action_verb  questions whose 4 captions are ALL verb-free
  mean_within_question_jaccard    how interchangeable a question's captions are
  median_caption_length_words
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Sequence/time signalling vocabulary. Deliberately excludes bare tense marking
# (a caption is not "temporal" because it says "is standing") and excludes
# "then"-less discourse filler -- what the TN/TP failure needs is explicit
# ordering and change-of-state language.
TEMPORAL_WORDS = {
    "before", "after", "then", "next", "first", "second", "third", "last",
    "finally", "later", "earlier", "begins", "begin", "beginning", "starts",
    "start", "starting", "started", "ends", "end", "ending", "ended",
    "while", "during", "when", "until", "once", "already", "still", "now",
    "afterwards", "afterward", "previously", "subsequently", "meanwhile",
    "suddenly", "immediately", "moment", "moments", "continues", "continue",
    "continuing", "stops", "stop", "stopped", "stopping", "turns", "turned",
    "becomes", "became", "transition", "transitions", "sequence", "follows",
    "following", "followed", "precedes", "preceding", "initially", "eventually",
}

# Physical-act verbs and their common inflections. Stative/appearance verbs
# ("is", "has", "appears", "wears", "stands") are excluded on purpose: a
# caption saying "a man is wearing a red shirt" describes a scene, not an
# action, and counting it would hide exactly the deficit being measured.
_ACTION_STEMS = [
    "walk", "run", "jump", "throw", "catch", "kick", "push", "pull", "lift",
    "carry", "grab", "reach", "point", "wave", "clap", "touch", "hit",
    "hug", "kiss", "dance", "climb", "crawl", "ride", "drive", "swim", "fall",
    "drop", "pick", "place", "put", "open", "close", "pour", "drink", "eat",
    "bite", "chew", "cut", "wipe", "clean", "wash", "brush", "comb", "rub",
    "shake", "swing", "spin", "roll", "bounce", "pass", "hand",
    "give", "take", "move", "turn", "bend", "rise", "step", "enter", "exit",
    "leave", "approach", "follow", "chase", "blow", "laugh", "cry",
    "sing", "shout", "search", "lick",
    "pet", "feed", "press", "type", "write", "draw", "paint", "build",
    "fix", "repair", "tie", "untie", "fold", "unfold", "remove",
    "swipe", "slide", "stretch", "toss", "shoot", "dribble",
]

# Deliberately NOT counted as action verbs, so the list matches the rationale
# above rather than quietly contradicting it:
#   posture/state  stand, sit, lie, lean, kneel, squat, hold, wear
#   perception     look, watch, stare, see
#   speech/affect  talk, speak, smile
#   generic        play
# "A man is standing and looking at the camera while wearing a red shirt" is a
# scene description with four verbs and zero actions. Counting those would
# report the deficit as already solved.
EXCLUDED_AS_STATIVE = {
    "stand", "sit", "lie", "lean", "kneel", "squat", "hold", "wear",
    "look", "watch", "stare", "see", "talk", "speak", "smile", "play",
}


def _inflect(stem: str) -> set[str]:
    forms = {stem, stem + "s", stem + "ed", stem + "ing"}
    if stem.endswith("e"):
        forms |= {stem[:-1] + "ing", stem + "d"}
    if len(stem) > 2 and stem[-1] not in "aeiou" and stem[-2] in "aeiou":
        forms |= {stem + stem[-1] + "ing", stem + stem[-1] + "ed"}
    if stem.endswith("y"):
        forms |= {stem[:-1] + "ies", stem[:-1] + "ied"}
    return forms


ACTION_VERBS: set[str] = set()
for _s in _ACTION_STEMS:
    ACTION_VERBS |= _inflect(_s)

# Enforced, not just documented: if a stative stem is ever re-added to
# _ACTION_STEMS the metric silently inflates and the caption deficit looks
# smaller than it is. Fail loudly instead.
_leaked = sorted(EXCLUDED_AS_STATIVE & set(_ACTION_STEMS))
if _leaked:
    raise AssertionError(
        f"stative/perception stems present in _ACTION_STEMS: {_leaked}. "
        "These inflate pct_with_action_verb and hide the deficit being measured."
    )

_WORD_RE = re.compile(r"[a-z']+")


def tokens(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_STOP = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "of",
    "in", "on", "at", "to", "for", "with", "and", "or", "but", "he", "she",
    "it", "they", "this", "that", "these", "those", "there", "his", "her",
    "its", "their", "what", "who", "how", "why", "does", "did", "do", "you",
    "s", "as", "by", "from", "up", "down", "out", "into", "then", "when",
}


def question_leakage(dump: dict, questions_by_key: dict) -> dict:
    """How much of the CAPTION's content words come straight out of the
    QUESTION being asked?

    This is the measurement that separates "the captioner found better visual
    detail" from "the captioner wrote the question back out as an observation".
    Question-aware captioning injects the question into the captioner prompt, so
    every lexical quality metric above can rise for free without a single extra
    bit of visual grounding -- the question text is itself full of action verbs
    and temporal words. Recall of the question's content words by the caption is
    the direct check.

    questions_by_key: {(video, qid): question_text}
    """
    recalls: list[float] = []
    n_high = 0
    for vid, per_q in dump.items():
        for qid, frames in per_q.items():
            qtext = questions_by_key.get((vid, str(qid)))
            if not qtext:
                continue
            qwords = set(tokens(qtext)) - _STOP
            if not qwords:
                continue
            for t in frames.values():
                cwords = set(tokens(t)) - _STOP
                r = len(qwords & cwords) / len(qwords)
                recalls.append(r)
                if r >= 0.5:
                    n_high += 1
    if not recalls:
        return {"n": 0}
    return {
        "n_captions": len(recalls),
        "mean_question_content_word_recall": statistics.mean(recalls),
        "median_question_content_word_recall": statistics.median(recalls),
        "pct_captions_recalling_half_the_question": 100.0 * n_high / len(recalls),
    }


def question_leakage_vs_donor(dump: dict, questions_by_key: dict, shuffle_map: dict) -> dict:
    """Arm-G control-for-the-control: recall of the DONOR question's content
    words (the text actually injected into the captioner) alongside recall of
    the question actually ASKED.

    question_leakage() above always scores against the asked question. For the
    shuffled arm that is the floor the leakage story predicts, but on its own it
    cannot distinguish "the derangement worked" from "the recall metric is
    broken and reads low on everything". Scoring the same captions against the
    donor question is the positive control: if injection leaks at all, donor
    recall must be clearly ABOVE asked recall on the very same captions. If the
    two are equal, the diagnostic is not detecting injection and Arm E's recall
    figure cannot be trusted either.
    """
    asked_recalls: list[float] = []
    donor_recalls: list[float] = []
    n_pairs = 0
    n_no_donor = 0
    for vid, per_q in dump.items():
        donors_for_video = shuffle_map.get(vid) or {}
        for qid, frames in per_q.items():
            asked_text = questions_by_key.get((vid, str(qid)))
            donor_qid = donors_for_video.get(str(qid))
            donor_text = questions_by_key.get((vid, str(donor_qid))) if donor_qid else None
            if not asked_text or not donor_text:
                n_no_donor += 1
                continue
            asked_w = set(tokens(asked_text)) - _STOP
            donor_w = set(tokens(donor_text)) - _STOP
            if not asked_w or not donor_w:
                continue
            for t in frames.values():
                cwords = set(tokens(t)) - _STOP
                asked_recalls.append(len(asked_w & cwords) / len(asked_w))
                donor_recalls.append(len(donor_w & cwords) / len(donor_w))
                n_pairs += 1
    if not n_pairs:
        return {"n_captions": 0, "status": "no (asked, donor) pairs resolvable"}
    mean_asked = statistics.mean(asked_recalls)
    mean_donor = statistics.mean(donor_recalls)
    return {
        "n_captions": n_pairs,
        "n_questions_without_resolvable_donor": n_no_donor,
        "mean_recall_of_ASKED_question": mean_asked,
        "mean_recall_of_DONOR_question": mean_donor,
        "donor_minus_asked": mean_donor - mean_asked,
        # The diagnostic is only trustworthy if the text actually fed to the
        # captioner is recalled more than the text that was not.
        "diagnostic_detects_injection": bool(mean_donor > mean_asked),
    }


def measure(dump: dict) -> dict:
    """dump: {video: {qid: {frame_idx: caption}}}"""
    captions: list[str] = []
    n_temporal = n_action = 0
    per_question_zero_verb = 0
    n_questions = 0
    jaccards: list[float] = []
    lengths: list[int] = []

    for _vid, per_q in dump.items():
        for _qid, frames in per_q.items():
            n_questions += 1
            texts = [t or "" for t in frames.values()]
            q_has_action = False
            token_sets = []
            for t in texts:
                captions.append(t)
                tk = tokens(t)
                lengths.append(len(tk))
                s = set(tk)
                token_sets.append(s)
                if s & TEMPORAL_WORDS:
                    n_temporal += 1
                if s & ACTION_VERBS:
                    n_action += 1
                    q_has_action = True
            if not q_has_action:
                per_question_zero_verb += 1
            if len(token_sets) >= 2:
                jaccards.append(statistics.mean(
                    jaccard(a, b) for a, b in combinations(token_sets, 2)))

    n = len(captions)
    return {
        "n_captions": n,
        "n_questions": n_questions,
        "pct_with_temporal_word": 100.0 * n_temporal / n if n else None,
        "pct_with_action_verb": 100.0 * n_action / n if n else None,
        "pct_questions_zero_action_verb": (100.0 * per_question_zero_verb / n_questions
                                           if n_questions else None),
        "mean_within_question_jaccard": statistics.mean(jaccards) if jaccards else None,
        "median_within_question_jaccard": statistics.median(jaccards) if jaccards else None,
        "median_caption_length_words": statistics.median(lengths) if lengths else None,
        "mean_caption_length_words": statistics.mean(lengths) if lengths else None,
    }


# The historically-reported baseline, carried here so the recomputed baseline
# can be shown against it. These are NOT used in any comparison -- they are
# context for judging whether the lexicons above are measuring the same thing.
STATED_BASELINE = {
    "pct_with_temporal_word": 3.0,
    "pct_with_action_verb": 52.9,
    "pct_questions_zero_action_verb": 15.6,
    "mean_within_question_jaccard": 0.343,
    "median_caption_length_words": 42,
}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", default=str(REPO / "tuning/blind_ablation/captions_dump.json"))
    p.add_argument("--new", nargs="*", default=[],
                   help="LABEL=PATH pairs for each new dump to compare.")
    p.add_argument("--out", default=str(REPO / "tuning/caption_repair/caption_quality_comparison.json"))
    p.add_argument("--donor-map", default=None,
                   help="LABEL=PATH to the Arm-G shuffle map. Adds the donor-question "
                        "recall control to that dump's block.")
    args = p.parse_args(argv)

    donor_label, donor_map = None, None
    if args.donor_map:
        donor_label, _, donor_map_path = args.donor_map.partition("=")
        _raw = json.loads(Path(donor_map_path).read_text())
        donor_map = {k: v for k, v in _raw.items() if k != "_stats"}

    result = {
        "lexicon": {"n_temporal_words": len(TEMPORAL_WORDS), "n_action_verb_forms": len(ACTION_VERBS)},
        "historically_stated_baseline": STATED_BASELINE,
        "dumps": {},
    }
    import sys as _sys
    _sys.path.insert(0, str(REPO / "scripts"))
    from val_confirm_e2e_eval import load_split_questions
    questions_by_key = {(q["video"], str(q["qid"])): q["question"]
                        for q in load_split_questions("val_confirm")}

    base_dump = json.loads(Path(args.baseline).read_text())
    base = measure(base_dump)
    result["dumps"]["baseline_question_blind"] = {
        "path": args.baseline, **base,
        "question_leakage": question_leakage(base_dump, questions_by_key),
    }

    for spec in args.new:
        label, _, path = spec.partition("=")
        if not path or not Path(path).exists():
            result["dumps"][label] = {"path": path, "status": "MISSING -- not measured"}
            continue
        dump = json.loads(Path(path).read_text())
        m = measure(dump)
        deltas = {k: (m[k] - base[k]) for k in base
                  if isinstance(m.get(k), (int, float)) and isinstance(base.get(k), (int, float))
                  and k not in ("n_captions", "n_questions")}
        result["dumps"][label] = {
            "path": path, **m, "delta_vs_baseline": deltas,
            # Always measured against the question ACTUALLY ASKED, including for
            # the shuffled arm -- there, recall of the asked question is the
            # floor the leakage story predicts, and recall of the donor question
            # is what actually got injected.
            "question_leakage": question_leakage(dump, questions_by_key),
        }
        if donor_map is not None and label == donor_label:
            result["dumps"][label]["question_leakage_vs_donor"] = question_leakage_vs_donor(
                dump, questions_by_key, donor_map)

    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"[caption-quality] wrote {args.out}")


if __name__ == "__main__":
    main()

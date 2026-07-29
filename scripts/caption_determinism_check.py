"""Phase 3, required check: is the CAPTION stage deterministic?

The answerer's determinism has been gated (tuning/determinism_gate/). The
captioner's never has. That matters here specifically: Phase 3 re-captions, so
if the captioner is non-deterministic then every Phase-3 accuracy delta carries
an unmeasured caption-variance component and must be reported with it.

Method: take N videos, caption their retrieved frames twice IN THE SAME
question-aware mode Phase 3 uses, and diff the text byte-for-byte. Retrieval is
identical across the two passes by construction (same index, same frozen
config, no sampling), so any text difference is the captioner's.

The two passes run in one process against separately-loaded index objects, so
pass 2 cannot inherit pass 1's in-memory FrameRecord.caption cache -- otherwise
this would trivially "prove" determinism by never invoking the captioner again.
"""
from __future__ import annotations

import argparse
import json
import os
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

from part3_tune import load_frozen_state  # noqa: E402
from val_confirm_e2e_eval import (  # noqa: E402
    make_e2e_config, ingest_config_hash, load_split_questions, INDEX_CACHE_DIR,
)


def caption_pass(questions: list[dict], cfg, cfg_hash: str, question_aware: bool) -> dict:
    """One full caption pass. Returns {video: {qid: {frame_idx: caption}}}."""
    out: dict = {}
    index_cache: dict = {}
    for q in questions:
        vid = q["video"]
        if vid not in index_cache:
            # Fresh load per pass -- see module docstring.
            index_cache.clear()
            index_cache[vid] = iris_ingest.load_index(str(INDEX_CACHE_DIR / f"{vid}__{cfg_hash}"))
        index = index_cache[vid]
        retrieved, _plan, _tel = retrieve_for_question(
            q["question"], index, cfg, type_code=q.get("type"), family=None)
        if question_aware:
            frame_map = {fr.frame_idx: fr for fr in index.frames}
            for f in retrieved:
                fr = frame_map.get(f["frame_idx"])
                if fr is not None:
                    fr.caption = None
                f["caption"] = None
            iris_query._ensure_captions(index, retrieved, cfg,
                                        question=q["question"], choices=q["choices"])
        else:
            iris_query._ensure_captions(index, retrieved, cfg)
        per_q = {}
        for f in retrieved:
            cap = f.get("caption")
            per_q[str(f["frame_idx"])] = (cap.get("semantic_caption")
                                          if isinstance(cap, dict) else cap)
        out.setdefault(vid, {})[str(q["qid"])] = per_q
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n-videos", type=int, default=20)
    p.add_argument("--question-aware", action="store_true", default=True)
    p.add_argument("--out", default=str(REPO / "tuning/caption_repair/caption_determinism.json"))
    args = p.parse_args(argv)

    frozen = load_frozen_state()["frozen"]
    cfg = make_e2e_config(frozen, None)
    cfg_hash = ingest_config_hash(cfg)

    questions = load_split_questions("val_confirm")
    videos = sorted({q["video"] for q in questions})[: args.n_videos]
    subset = [q for q in questions if q["video"] in set(videos)]
    print(f"[determinism] {len(subset)} questions across {len(videos)} videos, "
          f"question_aware={args.question_aware}", flush=True)

    t0 = time.perf_counter()
    pass1 = caption_pass(subset, cfg, cfg_hash, args.question_aware)
    t1 = time.perf_counter()
    pass2 = caption_pass(subset, cfg, cfg_hash, args.question_aware)
    t2 = time.perf_counter()

    identical = differing = 0
    examples = []
    for vid, per_q in pass1.items():
        for qid, frames in per_q.items():
            for fidx, cap in frames.items():
                other = pass2.get(vid, {}).get(qid, {}).get(fidx)
                if cap == other:
                    identical += 1
                else:
                    differing += 1
                    if len(examples) < 5:
                        examples.append({"video": vid, "qid": qid, "frame_idx": fidx,
                                         "pass1": cap, "pass2": other})
    total = identical + differing
    result = {
        "n_videos": len(videos), "n_questions": len(subset),
        "question_aware": bool(args.question_aware),
        "n_captions_compared": total,
        "n_identical": identical, "n_differing": differing,
        "identical_rate": identical / total if total else None,
        "deterministic": differing == 0,
        "pass1_wall_s": t1 - t0, "pass2_wall_s": t2 - t1,
        "differing_examples": examples,
        "interpretation": (
            "Caption stage is byte-for-byte deterministic across two passes; "
            "Phase-3 accuracy deltas carry no caption-variance term."
            if differing == 0 else
            f"Caption stage is NOT deterministic: {differing}/{total} captions "
            "differed between two identical passes. Every Phase-3 accuracy number "
            "must be read with this variance stated alongside it."
        ),
    }
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "differing_examples"}, indent=2))
    print(f"[determinism] wrote {args.out}")


if __name__ == "__main__":
    main()

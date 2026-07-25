"""V3 retrieval path: one PPR, <=3 text embeddings, separate retrieval/context.

Kept beside `iris/retrieval_entry.py` rather than folded into it so the frozen
baseline path (`query_reformulation_mode="none"`) is byte-for-byte untouched and
the committed A-E ablation stays reproducible.

Widths, and why they do not violate the frozen K=4:

  M (candidate_pool_size)  the bounded sparse candidate pool the traversal and
                           the temporal adapter operate on (task section 5.1).
  K (l2_retrieve_top_k=4)  the FINAL retrieval width. Unchanged, frozen.

A single PPR solve produces M ranked survivors; `retrieval_frames` is always
exactly the top K of whatever the final ranking is. `top_k` is pure truncation
inside `retrieve_ppr`, so the first K of an M-wide call is identical to a K-wide
call (asserted by tests/test_retrieval_entry_v3.py).
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from iris.frame_serialization import assign_retrieval_rank, node_to_dict
from iris.query_reformulation import Relation, QueryPlanV2
from iris.query_reformulation_v3 import (
    all_embedding_texts_v3,
    build_query_plan_v3,
    parser_status,
    seed_embedding_texts,
)
from iris.temporal_traversal_safe import DEFAULT_POLICY, TraversalPolicy, TraversalResult, traverse_safe

DEFAULT_CANDIDATE_POOL_SIZE = 16


def _cosine_to_frames(index: Any, embedding: "np.ndarray | None") -> dict[int, float]:
    """Cosine similarity of one query embedding against every cached frame
    embedding. Uses only cached features -- no CLIP image pass."""
    if embedding is None:
        return {}
    q = np.asarray(embedding, dtype=np.float32)
    qn = float(np.linalg.norm(q))
    if qn < 1e-8:
        return {}
    out: dict[int, float] = {}
    for fr in index.frames:
        if fr.clip_embedding is None:
            continue
        e = np.asarray(fr.clip_embedding, dtype=np.float32)
        en = float(np.linalg.norm(e))
        out[int(fr.frame_idx)] = float(np.dot(e, q) / (en * qn)) if en >= 1e-8 else 0.0
    return out


def _variant_agreement_fn(sim_maps: list[dict[int, float]]):
    """Agreement across the seed query variants: min/max of their per-frame
    cosines, so a frame both variants like scores ~1 and a frame only one
    variant likes scores low. Returns None when there is only one variant
    (the feature is then masked, not faked)."""
    if len(sim_maps) < 2:
        return None

    def _fn(frame_idx: int) -> float:
        vals = [m.get(frame_idx) for m in sim_maps]
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            return 0.0
        lo, hi = min(vals), max(vals)
        if hi <= 1e-6:
            return 0.0
        return max(0.0, min(1.0, lo / hi))

    return _fn


def _ppr_retrieve(index: Any, matrix: np.ndarray, weights: list[float], config: Any,
                  top_k: int) -> list[dict]:
    """Exactly one PPR (or scene-sparse) solve, widened to `top_k` candidates."""
    combine = getattr(config, "multi_query_combine", "weighted_max")
    if getattr(config, "graph_mode", "flat") == "scene_sparse":
        from iris.scene_retrieval import retrieve_scene_sparse

        class _WidenedConfig:
            """scene_sparse reads its width from config.l2_retrieve_top_k; the
            frozen object must not be mutated, so it is shadowed here."""

            def __init__(self, base, width):
                self._base, self._width = base, width

            def __getattr__(self, name):
                if name == "l2_retrieve_top_k":
                    return self._width
                return getattr(self._base, name)

        return retrieve_scene_sparse(
            index, None, _WidenedConfig(config, top_k),
            query_embeddings=matrix, query_weights=weights, multi_query_combine=combine,
        )

    graph = index._graph
    frame_map = {fr.frame_idx: fr for fr in index.frames}
    nodes = graph.retrieve_ppr(
        None, top_k=top_k,
        damping=getattr(config, "ppr_damping", 0.5),
        lambda_=getattr(config, "ppr_lambda", 0.5),
        query_embeddings=matrix, query_weights=weights, multi_query_combine=combine,
    )
    return assign_retrieval_rank([node_to_dict(n, frame_map.get(n.frame_idx)) for n in nodes])


def retrieve_v3(
    question: str,
    index: Any,
    config: Any,
    *,
    type_code: str | None = None,
    family: str | None = None,
    use_structured: bool = True,
    use_traversal: bool = True,
    adapter: Any = None,
    policy: TraversalPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    """Returns a dict with explicitly separated fields:

        retrieval_frames  exactly K frames -- what Gold@K and the span
                          localizer consume
        context_frames    optional answerer-only neighbours, never counted
        semantic_candidates  the M-wide pool (adapter/traversal input)

    Answer choices are never accepted by this function; only question text and
    the dataset type code enter retrieval.
    """
    top_k = int(getattr(config, "l2_retrieve_top_k", 4))
    pool_size = max(top_k, int(getattr(config, "candidate_pool_size", DEFAULT_CANDIDATE_POOL_SIZE)))

    from iris.query import _call_embed_queries

    t0 = time.perf_counter()
    if use_structured:
        plan = build_query_plan_v3(question, type_code=type_code, family=family, config=config)
        texts = list(all_embedding_texts_v3(plan))
        seed_texts, seed_weights = seed_embedding_texts(plan)
    else:
        plan = None
        texts = [question]
        seed_texts, seed_weights = (question,), (1.0,)
    t_parse = time.perf_counter() - t0

    assert len(texts) <= 3, f"embedding budget exceeded: {len(texts)}"

    t0 = time.perf_counter()
    matrix, embed_telemetry = _call_embed_queries(texts, config)
    t_embed = time.perf_counter() - t0

    seed_rows = [texts.index(t) for t in seed_texts if t in texts]
    if not seed_rows:  # defensive
        seed_rows = [0]
        seed_weights = (1.0,)
    seed_matrix = matrix[seed_rows]
    seed_w = [float(w) for w in seed_weights[: len(seed_rows)]]

    t0 = time.perf_counter()
    semantic_candidates = _ppr_retrieve(index, seed_matrix, seed_w, config, pool_size)
    t_retrieve = time.perf_counter() - t0

    semantic_top_k = [dict(f) for f in semantic_candidates[:top_k]]

    # Cached-feature similarity maps: target (rerank only) and variant agreement.
    target_row = texts.index(plan.target_query) if (plan and plan.target_query in texts) else None
    target_sims = _cosine_to_frames(index, matrix[target_row]) if target_row is not None else {}
    seed_sim_maps = [_cosine_to_frames(index, matrix[r]) for r in seed_rows] if len(seed_rows) > 1 else []

    target_fn = (lambda fi: max(0.0, target_sims.get(fi, 0.0))) if target_sims else None
    variant_fn = _variant_agreement_fn(seed_sim_maps)

    t0 = time.perf_counter()
    adapter_scores, adapter_conf, adapter_fallback = None, None, "adapter_not_used"
    if adapter is not None:
        adapter_scores, adapter_conf, adapter_fallback = adapter.score(
            index=index, candidates=semantic_candidates, plan=plan,
            question=question, type_code=type_code,
            question_embedding=matrix[0], target_sims=target_sims,
        )
    t_adapter = time.perf_counter() - t0

    t0 = time.perf_counter()
    if use_traversal and plan is not None:
        result = traverse_safe(
            index, semantic_candidates, plan, config, top_k=top_k, policy=policy,
            target_similarity_fn=target_fn, variant_agreement_fn=variant_fn,
            adapter_scores=adapter_scores, adapter_confidence=adapter_conf,
        )
    elif adapter_scores:
        # Adapter isolation (Arm H): residual rerank of the pool, no traversal,
        # but the same temporal-diversity floor so a collapse cannot sneak in.
        from iris.temporal_traversal_safe import _temporal_nms, _base_score, _minmax

        sems = [_base_score(f) for f in semantic_candidates]
        norm = _minmax(sems)
        rescored = []
        for f, s in zip(semantic_candidates, norm):
            rec = dict(f)
            delta = float(adapter_scores.get(int(f["frame_idx"]), 0.0))
            rec["score_components"] = {"norm_semantic": s, "adapter_delta": delta}
            rec["final_score"] = float(s + delta)
            rescored.append(rec)
        rescored.sort(key=lambda r: (-r["final_score"], int(r["frame_idx"])))
        kept = _temporal_nms(rescored, top_k, policy.min_separation_s)
        result = TraversalResult(
            retrieval_frames=assign_retrieval_rank(kept),
            context_frames=[],
            diagnostics={
                "traversal_active": False, "reason": "adapter_only",
                "adapter_applied": True, "confidence": adapter_conf,
                "n_original_preserved": sum(
                    1 for f in semantic_top_k
                    if int(f["frame_idx"]) in {int(x["frame_idx"]) for x in kept}
                ),
            },
        )
    else:
        result = TraversalResult(
            retrieval_frames=assign_retrieval_rank([dict(f) for f in semantic_top_k]),
            context_frames=[],
            diagnostics={"traversal_active": False, "reason": "traversal_disabled",
                         "n_original_preserved": len(semantic_top_k)},
        )
    t_traverse = time.perf_counter() - t0

    return {
        "retrieval_frames": result.retrieval_frames,
        "context_frames": result.context_frames,
        "semantic_candidates": semantic_candidates,
        "semantic_top_k": semantic_top_k,
        "plan": plan,
        "traversal": result.diagnostics,
        "adapter_confidence": adapter_conf,
        "adapter_fallback_reason": adapter_fallback,
        "telemetry": {
            "num_ppr_calls": 1,
            "num_clip_texts_embedded": len(texts),
            "num_seed_queries": len(seed_rows),
            "candidate_pool_size": len(semantic_candidates),
            "parser_status": parser_status(plan) if plan else "not_structured",
            "embed_cache_hits": embed_telemetry.get("cache_hits") if isinstance(embed_telemetry, dict) else None,
            "t_parse_ms": t_parse * 1000.0,
            "t_embed_ms": t_embed * 1000.0,
            "t_retrieve_ms": t_retrieve * 1000.0,
            "t_adapter_ms": t_adapter * 1000.0,
            "t_traverse_ms": t_traverse * 1000.0,
        },
    }

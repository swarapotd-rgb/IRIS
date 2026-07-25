"""Non-destructive, multi-anchor temporal traversal (task section 3).

This module replaces `traverse_directional`'s behaviour without deleting it --
the old function stays in `iris/temporal_traversal.py` so the committed A-E
ablation remains reproducible. The four verified defects it repairs:

1. `_direction_score` returned the literal `1e6` for the anchor, pinning one
   ~30%-accurate frame to rank 1. There is no forced score anywhere here; a
   test asserts no score exceeds a small documented bound.
2. Exploration started from `retrieved_frames[0]` only. Here it starts from the
   top `n_anchors` (default 2) semantic candidates.
3. The final blend contained no PPR/CLIP term at all -- original semantic
   evidence was discarded the moment traversal activated. Here the normalized
   semantic score carries weight `w_semantic` (default 0.60), strictly greater
   than the sum of every other weight (0.40), so a maximally-strong semantic
   candidate provably cannot be overtaken by recency/scene/codec/target terms.
4. The traversal result replaced the retrieval list. Here retrieval frames and
   context frames are separate return values with separate names, and the
   number of original semantic candidates preserved in the final top-K is a
   hard, tested floor.

Everything is gated: when the confidence gate does not fire, the original
semantic top-K is returned byte-identically and `context_frames` is empty.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from iris.frame_serialization import assign_retrieval_rank, frame_record_to_dict
from iris.query_reformulation import Relation, QueryPlanV2

# The largest value any component or blended score may take. Asserted by tests
# so a "1e6"-style forced score can never be reintroduced silently.
MAX_SCORE_BOUND = 2.0


@dataclass(frozen=True)
class TraversalPolicy:
    """Every threshold in one inspectable object.

    Defaults here are a-priori values (documented in the report), NOT tuned on
    val_tune. Any value selected empirically must be selected on adapter_dev
    and recorded in adapter_config.json.
    """

    # candidate construction
    n_anchors: int = 2                 # semantic anchors that seed directional exploration
    max_directional_per_anchor: int = 1
    time_window_s: float = 4.0
    scene_hop_budget: int = 1
    max_context_frames: int = 8

    # preservation floor (section 3.2)
    min_preserved: int = 3             # of the original semantic top-K
    min_preserved_high_confidence: int = 2

    # confidence gate (section 3.4)
    margin_activate: float = 0.05      # normalized semantic margin, top1 vs top2
    margin_high_confidence: float = 0.25
    require_gate: bool = True

    # temporal diversity (section 3.5)
    min_separation_s: float = 1.0

    # score blend (section 3.3) -- semantic must dominate
    w_semantic: float = 0.60
    w_direction: float = 0.10
    w_target: float = 0.10
    w_scene: float = 0.05
    w_action: float = 0.05
    w_variant_agreement: float = 0.05
    w_position_prior: float = 0.05

    def non_semantic_weight_sum(self) -> float:
        return (self.w_direction + self.w_target + self.w_scene + self.w_action
                + self.w_variant_agreement + self.w_position_prior)

    def validate(self) -> None:
        assert self.w_semantic > self.non_semantic_weight_sum(), (
            "semantic evidence must be the dominant term (section 3.3): "
            f"w_semantic={self.w_semantic} <= others={self.non_semantic_weight_sum()}"
        )
        assert self.min_preserved >= 2, "at least two original candidates must survive"
        assert self.n_anchors >= 2, "directional exploration must start from >1 anchor"


DEFAULT_POLICY = TraversalPolicy()


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _base_score(frame: dict[str, Any]) -> float:
    """Original semantic/PPR evidence for a frame, whatever the retrieval path
    recorded. Never falls back to a constant when a real score exists."""
    # `last_retrieval_score` is what node_to_dict/_frame_to_dict stamp with the
    # PPR (or scene max-sim) score -- it is the canonical field, checked first.
    for key in ("last_retrieval_score", "ppr_score", "score", "retrieval_score", "similarity"):
        val = frame.get(key)
        if val is not None:
            return float(val)
    contrib = frame.get("retrieval_contributions") or {}
    for key in ("ppr_score", "sem_sim", "semantic_similarity"):
        if contrib.get(key) is not None:
            return float(contrib[key])
    # Rank-derived fallback, still monotone in the original ordering.
    rank = frame.get("retrieval_rank")
    return 1.0 / (1.0 + float(rank)) if rank is not None else 0.0


def _scene_order(index: Any) -> dict[int, int]:
    scene_spans = getattr(index, "scene_spans", None) or {}
    if scene_spans:
        ordered = sorted(scene_spans.keys(), key=lambda sid: scene_spans[sid][0])
    else:
        ordered = sorted({getattr(fr, "scene_id", -1) for fr in index.frames})
    return {sid: pos for pos, sid in enumerate(ordered)}


def _scene_hops(scene_pos: dict[int, int], a: int | None, b: int | None) -> int:
    if a is None or b is None or a not in scene_pos or b not in scene_pos:
        return 0
    return abs(scene_pos[b] - scene_pos[a])


def _direction_consistency(relation: str, dt: float, window: float) -> float:
    """1.0 when the candidate sits on the relation's expected side of the
    anchor and close to it, decaying to 0 at the window edge; 0.0 on the wrong
    side. Anchors themselves (dt == 0) score 1.0."""
    if window <= 0:
        return 0.0
    closeness = max(0.0, 1.0 - abs(dt) / window)
    if relation == Relation.AFTER or relation == Relation.SEQUENCE:
        return closeness if dt >= 0 else 0.0
    if relation == Relation.BEFORE or relation == Relation.CAUSE:
        return closeness if dt <= 0 else 0.0
    if relation in (Relation.DURING, Relation.CURRENT, Relation.MANNER):
        return closeness
    return closeness


def _position_prior_bonus(prior: "tuple[float, float] | None", ts: float, duration: float) -> float:
    if prior is None or duration <= 0:
        return 0.0
    lo, hi = prior
    frac = ts / duration
    if lo <= frac <= hi:
        return 1.0
    return max(0.0, 1.0 - min(abs(frac - lo), abs(frac - hi)) * 4.0)


@dataclass
class TraversalResult:
    """Deliberately distinct field names -- `retrieval_frames` is what Gold@K
    and the span localizer consume; `context_frames` is answerer-only context
    and must never be counted as retrieved."""

    retrieval_frames: list[dict[str, Any]]
    context_frames: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def build_candidate_pool(
    index: Any,
    semantic_frames: list[dict[str, Any]],
    plan: QueryPlanV2 | None,
    policy: TraversalPolicy = DEFAULT_POLICY,
) -> list[dict[str, Any]]:
    """Union of the semantic survivors and bounded directional neighbours of the
    top `n_anchors` of them. Deduplicated by frame_idx, sorted temporally."""
    relation = getattr(plan, "relation", Relation.NONE) if plan else Relation.NONE
    pool: dict[int, dict[str, Any]] = {}

    for frame in semantic_frames:
        rec = dict(frame)
        rec.setdefault("candidate_source", "semantic")
        pool[int(rec["frame_idx"])] = rec

    if relation == Relation.NONE:
        return sorted(pool.values(), key=lambda r: (float(r["timestamp"]), int(r["frame_idx"])))

    scene_pos = _scene_order(index)
    anchors = semantic_frames[: policy.n_anchors]
    for anchor in anchors:
        anchor_ts = float(anchor["timestamp"])
        anchor_scene = anchor.get("scene_id")
        neighbours: list[tuple[float, Any]] = []
        for fr in index.frames:
            if fr.clip_embedding is None:
                continue
            fidx = int(fr.frame_idx)
            if fidx in pool:
                continue
            dt = float(fr.timestamp) - anchor_ts
            if abs(dt) > policy.time_window_s:
                continue
            if _scene_hops(scene_pos, anchor_scene, getattr(fr, "scene_id", None)) > policy.scene_hop_budget:
                continue
            if _direction_consistency(relation, dt, policy.time_window_s) <= 0.0:
                continue
            neighbours.append((abs(dt), fr))
        neighbours.sort(key=lambda t: (t[0], int(t[1].frame_idx)))
        for _, fr in neighbours[: policy.max_directional_per_anchor]:
            rec = frame_record_to_dict(fr)
            rec["candidate_source"] = "directional"
            rec["directional_anchor_frame_idx"] = int(anchor["frame_idx"])
            pool[int(fr.frame_idx)] = rec

    return sorted(pool.values(), key=lambda r: (float(r["timestamp"]), int(r["frame_idx"])))


def score_candidates(
    index: Any,
    candidates: list[dict[str, Any]],
    semantic_frames: list[dict[str, Any]],
    plan: QueryPlanV2 | None,
    policy: TraversalPolicy = DEFAULT_POLICY,
    *,
    target_similarity_fn: "Callable[[int], float] | None" = None,
    variant_agreement_fn: "Callable[[int], float] | None" = None,
) -> list[dict[str, Any]]:
    """Attach `final_score` and a full `score_components` breakdown (section 3.3).

    Directional candidates carry no PPR score of their own, so their semantic
    term is the *decayed* score of the anchor they came from -- never a
    constant, and never higher than that anchor's own semantic term.
    """
    policy.validate()
    relation = getattr(plan, "relation", Relation.NONE) if plan else Relation.NONE
    duration = max((float(fr.timestamp) for fr in index.frames), default=0.0)
    scene_pos = _scene_order(index)

    sem_by_idx = {int(f["frame_idx"]): _base_score(f) for f in semantic_frames}
    norm_sem_values = _minmax([sem_by_idx[i] for i in sorted(sem_by_idx)])
    norm_sem = {i: v for i, v in zip(sorted(sem_by_idx), norm_sem_values)}

    anchors = semantic_frames[: policy.n_anchors]
    anchor_ts = [float(a["timestamp"]) for a in anchors]
    anchor_scene = [a.get("scene_id") for a in anchors]

    scored: list[dict[str, Any]] = []
    for cand in candidates:
        fidx = int(cand["frame_idx"])
        ts = float(cand["timestamp"])

        if fidx in norm_sem:
            sem = norm_sem[fidx]
        else:
            parent = cand.get("directional_anchor_frame_idx")
            parent_sem = norm_sem.get(int(parent), 0.0) if parent is not None else 0.0
            nearest_dt = min((abs(ts - a) for a in anchor_ts), default=policy.time_window_s)
            decay = max(0.0, 1.0 - nearest_dt / max(policy.time_window_s, 1e-6))
            sem = parent_sem * decay

        dts = [ts - a for a in anchor_ts] or [0.0]
        direction = max(_direction_consistency(relation, dt, policy.time_window_s) for dt in dts)
        hops = min((_scene_hops(scene_pos, s, cand.get("scene_id")) for s in anchor_scene), default=0)
        scene = 1.0 / (1.0 + hops)
        target = float(target_similarity_fn(fidx)) if target_similarity_fn else 0.0
        variant = float(variant_agreement_fn(fidx)) if variant_agreement_fn else 0.0
        action = float(cand.get("action_score") or 0.0)
        prior = _position_prior_bonus(getattr(plan, "position_prior", None) if plan else None, ts, duration)

        components = {
            "norm_semantic": sem,
            "direction_consistency": direction,
            "target_similarity": max(0.0, min(1.0, target)),
            "scene_continuity": scene,
            "action_score": max(0.0, min(1.0, action)),
            "variant_agreement": max(0.0, min(1.0, variant)),
            "position_prior": prior,
        }
        final = (
            policy.w_semantic * components["norm_semantic"]
            + policy.w_direction * components["direction_consistency"]
            + policy.w_target * components["target_similarity"]
            + policy.w_scene * components["scene_continuity"]
            + policy.w_action * components["action_score"]
            + policy.w_variant_agreement * components["variant_agreement"]
            + policy.w_position_prior * components["position_prior"]
        )
        assert final <= MAX_SCORE_BOUND, f"score {final} exceeds bound -- forced score reintroduced?"

        rec = dict(cand)
        rec["score_components"] = components
        rec["final_score"] = float(final)
        scored.append(rec)

    scored.sort(key=lambda r: (-r["final_score"], int(r["frame_idx"])))
    return scored


def _temporal_nms(
    ordered: list[dict[str, Any]], k: int, min_separation_s: float,
) -> list[dict[str, Any]]:
    """Greedy: keep the best-scoring candidate, then skip anything within
    `min_separation_s` of an already-kept timestamp. Relaxes the constraint
    only if it cannot otherwise fill k slots."""
    kept: list[dict[str, Any]] = []
    for cand in ordered:
        ts = float(cand["timestamp"])
        if all(abs(ts - float(x["timestamp"])) >= min_separation_s for x in kept):
            kept.append(cand)
        if len(kept) == k:
            return kept
    for cand in ordered:  # relaxation pass
        if len(kept) == k:
            break
        if all(int(cand["frame_idx"]) != int(x["frame_idx"]) for x in kept):
            kept.append(cand)
    return kept


def confidence_gate(
    semantic_frames: list[dict[str, Any]],
    plan: QueryPlanV2 | None,
    policy: TraversalPolicy = DEFAULT_POLICY,
    *,
    adapter_confidence: float | None = None,
) -> dict[str, Any]:
    """Decide whether directional promotion is allowed at all (section 3.4)."""
    reasons: list[str] = []
    sems = [_base_score(f) for f in semantic_frames]
    norm = _minmax(sems)
    margin = (norm[0] - norm[1]) if len(norm) >= 2 else 1.0

    if margin >= policy.margin_activate:
        reasons.append("semantic_margin")
    if len(semantic_frames) >= 2:
        s0, s1 = semantic_frames[0].get("scene_id"), semantic_frames[1].get("scene_id")
        if s0 is not None and s0 == s1:
            reasons.append("top2_same_scene")
    if adapter_confidence is not None and adapter_confidence >= 0.5:
        reasons.append("adapter_confident")

    high = margin >= policy.margin_high_confidence
    active = bool(reasons) if policy.require_gate else True
    return {
        "traversal_active": active,
        "reasons": reasons,
        "confidence": float(margin),
        "high_confidence": bool(high),
        "min_preserved": policy.min_preserved_high_confidence if high else policy.min_preserved,
    }


def traverse_safe(
    index: Any,
    semantic_frames: list[dict[str, Any]],
    plan: QueryPlanV2 | None,
    config: Any = None,
    *,
    top_k: int = 4,
    policy: TraversalPolicy = DEFAULT_POLICY,
    target_similarity_fn: "Callable[[int], float] | None" = None,
    variant_agreement_fn: "Callable[[int], float] | None" = None,
    adapter_scores: "dict[int, float] | None" = None,
    adapter_confidence: float | None = None,
) -> TraversalResult:
    """Non-destructive traversal. `semantic_frames` is the ordered candidate
    pool from one PPR call (length M >= top_k); the first `top_k` of it are the
    original semantic top-K that must be partially preserved.

    `adapter_scores` optionally supplies the learned residual correction, keyed
    by frame_idx; it is added to `final_score` *after* the semantic-dominant
    blend, so an untrained/absent adapter leaves the ordering untouched.
    """
    policy.validate()
    original_top = list(semantic_frames[:top_k])
    if not semantic_frames:
        return TraversalResult([], [], {"traversal_active": False, "reason": "empty_retrieval"})

    gate = confidence_gate(semantic_frames, plan, policy, adapter_confidence=adapter_confidence)
    relation = getattr(plan, "relation", Relation.NONE) if plan else Relation.NONE

    if not gate["traversal_active"] or relation == Relation.NONE:
        return TraversalResult(
            retrieval_frames=assign_retrieval_rank([dict(f) for f in original_top]),
            context_frames=[],
            diagnostics={
                **gate,
                "traversal_active": False,
                "reason": "gate_closed" if not gate["traversal_active"] else "relation_none",
                "n_original_preserved": len(original_top),
                "original_top_frame_idx": [int(f["frame_idx"]) for f in original_top],
            },
        )

    pool = build_candidate_pool(index, semantic_frames, plan, policy)
    scored = score_candidates(
        index, pool, semantic_frames, plan, policy,
        target_similarity_fn=target_similarity_fn,
        variant_agreement_fn=variant_agreement_fn,
    )

    if adapter_scores:
        for rec in scored:
            delta = float(adapter_scores.get(int(rec["frame_idx"]), 0.0))
            rec["score_components"]["adapter_delta"] = delta
            rec["final_score"] = float(rec["final_score"] + delta)
        scored.sort(key=lambda r: (-r["final_score"], int(r["frame_idx"])))

    # Preservation floor: the best `min_preserved` of the ORIGINAL semantic top-K
    # (in their original order) are seated first and can never be displaced.
    n_preserve = min(gate["min_preserved"], len(original_top), top_k)
    preserved = [dict(f) for f in original_top[:n_preserve]]
    preserved_idx = {int(f["frame_idx"]) for f in preserved}

    remaining = [r for r in scored if int(r["frame_idx"]) not in preserved_idx]
    n_slots = top_k - len(preserved)
    promoted = _temporal_nms(remaining, n_slots, policy.min_separation_s) if n_slots > 0 else []

    retrieval_frames = preserved + promoted
    retrieval_frames.sort(key=lambda r: (-float(r.get("final_score", _base_score(r))), int(r["frame_idx"])))
    retrieval_frames = assign_retrieval_rank(retrieval_frames[:top_k])

    final_idx = {int(f["frame_idx"]) for f in retrieval_frames}
    context_frames = [
        dict(r) for r in scored
        if int(r["frame_idx"]) not in final_idx
    ][: policy.max_context_frames]

    n_preserved_actual = sum(1 for f in original_top if int(f["frame_idx"]) in final_idx)
    timestamps = sorted(float(f["timestamp"]) for f in retrieval_frames)
    spread = (timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else 0.0

    return TraversalResult(
        retrieval_frames=retrieval_frames,
        context_frames=context_frames,
        diagnostics={
            **gate,
            "n_candidates": len(pool),
            "n_directional_candidates": sum(1 for r in pool if r.get("candidate_source") == "directional"),
            "n_original_preserved": n_preserved_actual,
            "n_promoted": len(promoted),
            "original_top_frame_idx": [int(f["frame_idx"]) for f in original_top],
            "final_frame_idx": [int(f["frame_idx"]) for f in retrieval_frames],
            "context_frame_idx": [int(f["frame_idx"]) for f in context_frames],
            "top_k_temporal_spread_s": spread,
            "adapter_applied": bool(adapter_scores),
        },
    )

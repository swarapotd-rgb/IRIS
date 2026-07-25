"""Non-destructive traversal tests (task section 12.8-12.14).

Uses a synthetic index so the assertions are about the traversal contract, not
about any particular video's content.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from iris.frame_serialization import frame_record_to_dict
from iris.query_reformulation import QueryPlanV2, Relation
from iris.temporal_traversal_safe import (
    DEFAULT_POLICY,
    MAX_SCORE_BOUND,
    TraversalPolicy,
    build_candidate_pool,
    confidence_gate,
    score_candidates,
    traverse_safe,
)


@dataclass
class FakeFrame:
    frame_idx: int
    timestamp: float
    scene_id: int = 0
    clip_embedding: object = 1  # non-None marker
    luma_diff_energy: float = 0.0
    luma_entropy: float = 0.0
    action_score: float = 0.2
    persistence_value: float = 0.5
    is_peak: bool = True
    caption: str | None = None
    codec_conf: float = 0.5
    pict_type: str = "P"


class FakeIndex:
    def __init__(self, n=40, dt=0.5):
        self.frames = [FakeFrame(i, i * dt, scene_id=i // 10) for i in range(n)]
        self.scene_spans = {s: (s * 10 * dt, (s * 10 + 9) * dt) for s in range(4)}


def sem_frame(index, frame_idx, score):
    fr = index.frames[frame_idx]
    d = frame_record_to_dict(fr, last_retrieval_score=score)
    return d


def make_plan(relation=Relation.AFTER):
    return QueryPlanV2(
        original_query="q", normalized_query="q", type_code="TN",
        relation=relation, needs_temporal_traversal=relation != Relation.NONE,
    )


def semantic_pool(index, scores=(0.9, 0.6, 0.5, 0.4, 0.35, 0.3, 0.25, 0.2)):
    """Eight temporally spread-out semantic candidates in relevance order."""
    idxs = [4, 14, 24, 34, 6, 16, 26, 36]
    frames = []
    for rank, (fi, sc) in enumerate(zip(idxs, scores)):
        f = sem_frame(index, fi, sc)
        f["retrieval_rank"] = rank
        frames.append(f)
    return frames


# ── 12.8 retrieval_frames and context_frames are separate ────────────────

def test_retrieval_and_context_frames_are_disjoint_collections():
    idx = FakeIndex()
    res = traverse_safe(idx, semantic_pool(idx), make_plan(), top_k=4)
    r = {f["frame_idx"] for f in res.retrieval_frames}
    c = {f["frame_idx"] for f in res.context_frames}
    assert len(res.retrieval_frames) == 4
    assert r.isdisjoint(c), "context frames leaked into retrieval frames"


def test_context_frames_do_not_change_retrieval_count():
    idx = FakeIndex()
    res = traverse_safe(idx, semantic_pool(idx), make_plan(), top_k=4)
    assert len(res.retrieval_frames) == 4


# ── 12.9/12.10 directional candidates cannot overwrite the semantic top-K ─

def test_minimum_original_candidates_survive():
    idx = FakeIndex()
    pool = semantic_pool(idx)
    res = traverse_safe(idx, pool, make_plan(), top_k=4)
    original = [int(f["frame_idx"]) for f in pool[:4]]
    final = {int(f["frame_idx"]) for f in res.retrieval_frames}
    preserved = sum(1 for f in original if f in final)
    assert preserved >= DEFAULT_POLICY.min_preserved_high_confidence
    assert res.diagnostics["n_original_preserved"] == preserved


def test_directional_candidates_never_take_every_slot():
    idx = FakeIndex()
    pool = semantic_pool(idx)
    res = traverse_safe(idx, pool, make_plan(), top_k=4)
    sources = [f.get("candidate_source", "semantic") for f in res.retrieval_frames]
    assert sources.count("directional") <= 4 - DEFAULT_POLICY.min_preserved_high_confidence


def test_exploration_starts_from_more_than_one_anchor():
    idx = FakeIndex()
    pool = semantic_pool(idx)
    cands = build_candidate_pool(idx, pool, make_plan(), DEFAULT_POLICY)
    anchors = {c["directional_anchor_frame_idx"] for c in cands
               if c.get("candidate_source") == "directional"}
    assert len(anchors) >= 2, f"directional candidates came from anchors {anchors}"


# ── 12.11 no artificial forced score ─────────────────────────────────────

def test_no_forced_score_anywhere():
    idx = FakeIndex()
    pool = semantic_pool(idx)
    cands = build_candidate_pool(idx, pool, make_plan(), DEFAULT_POLICY)
    scored = score_candidates(idx, cands, pool, make_plan(), DEFAULT_POLICY)
    for rec in scored:
        assert rec["final_score"] <= MAX_SCORE_BOUND
        for name, val in rec["score_components"].items():
            assert abs(val) <= MAX_SCORE_BOUND, f"{name}={val}"


def test_source_contains_no_huge_forced_score_literal():
    """Guards against reintroducing the `return 1e6` anchor pin. Comments and
    docstrings are stripped first -- the module documents the old defect by
    name on purpose."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("iris/temporal_traversal_safe.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            assert abs(node.value) <= 100.0, f"suspicious huge literal {node.value}"


# ── 12.12 semantic relevance contributes to every score, and dominates ───

def test_every_candidate_score_includes_semantic_evidence():
    idx = FakeIndex()
    pool = semantic_pool(idx)
    cands = build_candidate_pool(idx, pool, make_plan(), DEFAULT_POLICY)
    scored = score_candidates(idx, cands, pool, make_plan(), DEFAULT_POLICY)
    for rec in scored:
        assert "norm_semantic" in rec["score_components"]


def test_semantic_term_dominates_all_others_combined():
    p = DEFAULT_POLICY
    assert p.w_semantic > p.non_semantic_weight_sum()
    # A maximally-strong semantic candidate with every other signal at zero
    # still outscores a zero-semantic candidate with every other signal maxed.
    assert p.w_semantic * 1.0 > p.non_semantic_weight_sum() * 1.0


def test_policy_rejects_non_dominant_semantic_weight():
    bad = TraversalPolicy(w_semantic=0.1)
    with pytest.raises(AssertionError):
        bad.validate()


# ── 12.13 low confidence returns the original semantic top-K ─────────────

def test_low_confidence_returns_original_top_k_unchanged():
    idx = FakeIndex()
    # All-equal semantic scores in different scenes -> zero margin, no reason.
    pool = []
    for rank, fi in enumerate([4, 14, 24, 34]):
        f = sem_frame(idx, fi, 0.5)
        f["retrieval_rank"] = rank
        pool.append(f)
    policy = TraversalPolicy(margin_activate=0.9)
    res = traverse_safe(idx, pool, make_plan(), top_k=4, policy=policy)
    assert res.diagnostics["traversal_active"] is False
    assert [f["frame_idx"] for f in res.retrieval_frames] == [4, 14, 24, 34]
    assert res.context_frames == []


def test_relation_none_never_activates_traversal():
    idx = FakeIndex()
    res = traverse_safe(idx, semantic_pool(idx), make_plan(Relation.NONE), top_k=4)
    assert res.diagnostics["traversal_active"] is False


def test_gate_records_reason_and_confidence():
    idx = FakeIndex()
    gate = confidence_gate(semantic_pool(idx), make_plan(), DEFAULT_POLICY)
    assert "confidence" in gate and isinstance(gate["reasons"], list)


# ── 12.14 temporal diversity ─────────────────────────────────────────────

def test_temporal_diversity_prevents_near_duplicate_collapse():
    idx = FakeIndex()
    pool = semantic_pool(idx)
    res = traverse_safe(idx, pool, make_plan(), top_k=4)
    ts = sorted(float(f["timestamp"]) for f in res.retrieval_frames)
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    # The whole point of the Arm-E failure: four frames within ~0.7 s total.
    assert max(ts) - min(ts) > 1.0, f"top-4 collapsed to {ts}"
    assert all(g > 0 for g in gaps)


def test_nms_separation_respected_for_promoted_slots():
    idx = FakeIndex()
    pool = semantic_pool(idx)
    policy = TraversalPolicy(min_separation_s=2.0)
    res = traverse_safe(idx, pool, make_plan(), top_k=4, policy=policy)
    assert len({f["frame_idx"] for f in res.retrieval_frames}) == 4


# ── adapter integration ──────────────────────────────────────────────────

def test_absent_adapter_leaves_ordering_untouched():
    idx = FakeIndex()
    pool = semantic_pool(idx)
    a = traverse_safe(idx, pool, make_plan(), top_k=4)
    b = traverse_safe(idx, pool, make_plan(), top_k=4, adapter_scores={})
    assert [f["frame_idx"] for f in a.retrieval_frames] == [f["frame_idx"] for f in b.retrieval_frames]


def test_adapter_delta_is_recorded_when_supplied():
    idx = FakeIndex()
    pool = semantic_pool(idx)
    res = traverse_safe(idx, pool, make_plan(), top_k=4,
                        adapter_scores={4: 0.01, 14: 0.02})
    assert res.diagnostics["adapter_applied"] is True


def test_traversal_is_deterministic():
    idx = FakeIndex()
    pool = semantic_pool(idx)
    first = [f["frame_idx"] for f in traverse_safe(idx, pool, make_plan(), top_k=4).retrieval_frames]
    for _ in range(5):
        again = [f["frame_idx"] for f in traverse_safe(idx, pool, make_plan(), top_k=4).retrieval_frames]
        assert again == first

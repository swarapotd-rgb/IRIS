"""Driver-level fairness invariants (task section 12.20-12.23).

These run against the committed raw outputs when they exist, and against the
source otherwise, so a future edit that reintroduces leakage fails here.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "tuning" / "sparse_temporal_reranker_v1"
RAW = OUT / "raw"
DRIVER = REPO / "scripts" / "sparse_temporal_reranker_eval.py"


def arm_rows(name: str) -> list[dict]:
    path = RAW / name
    if not path.exists():
        pytest.skip(f"{name} not generated yet")
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


# ── 12.20 val_confirm is never loaded ────────────────────────────────────

def test_driver_never_references_val_confirm_data():
    src = DRIVER.read_text()
    for forbidden in ("gsub_test", "val_confirm_e2e", "index_cache_val_confirm"):
        assert forbidden not in src, f"driver references {forbidden}"


def test_no_val_confirm_video_appears_in_any_arm():
    confirm = set(json.loads((REPO / "split_manifest.json").read_text())["confirm_videos"])
    for name in ("A_baseline.jsonl", "F_parser_fixed.jsonl", "G_safe_traversal.jsonl"):
        rows = arm_rows(name)
        leaked = {r["video"] for r in rows} & confirm
        assert not leaked, f"{name} contains val_confirm videos: {sorted(leaked)[:3]}"


def test_all_arm_videos_are_val_tune():
    tune = set(json.loads((REPO / "split_manifest.json").read_text())["tune_videos"])
    rows = arm_rows("A_baseline.jsonl")
    assert {r["video"] for r in rows} <= tune


# ── 12.21 answer choices never enter retrieval ───────────────────────────

def test_driver_never_reads_answer_columns():
    """The driver must never touch a0..a4 or the answer index."""
    src = DRIVER.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in {"a0", "a1", "a2", "a3", "a4", "answer", "answer_text"}, (
                f"driver references answer column {node.value!r}"
            )


def test_retrieval_modules_never_reference_answer_choices():
    """Checked against identifiers and string literals only -- these modules
    document *in prose* that they never take answer choices, and that prose
    must not trip the check."""
    for mod in ("iris/retrieval_entry_v3.py", "iris/query_reformulation_v3.py",
                "iris/temporal_traversal_safe.py"):
        tree = ast.parse((REPO / mod).read_text())
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docstrings.add(doc)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in {"choices", "answer_text", "gold_spans", "gold_span"}
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"choices", "answer_text", "gold_spans", "gold_span"}
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in docstrings:
                    continue
                assert node.value not in {"choices", "answer_text", "gold_spans", "gold_span"}


def test_raw_rows_carry_gold_only_as_scoring_output():
    """Gold spans may appear in the OUTPUT rows (they are needed to reproduce
    the metrics) but must not appear in any retrieval-input field."""
    rows = arm_rows("F_parser_fixed.jsonl")
    for r in rows[:200]:
        assert "gold_spans" in r
        for text in r["query_texts"]:
            for span in r["gold_spans"]:
                assert str(span[0]) not in text


# ── 12.22 determinism ────────────────────────────────────────────────────

def test_parser_and_traversal_have_no_rng():
    for mod in ("iris/retrieval_entry_v3.py", "iris/query_reformulation_v3.py",
                "iris/temporal_traversal_safe.py"):
        src = (REPO / mod).read_text()
        assert "random" not in src, f"{mod} imports randomness"


# ── 12.23 Arm A reproduces the frozen baseline ───────────────────────────

FROZEN_BASELINE = {          # from the committed query_reformulation_v2 ablation
    "gold_at_4": 0.5303538175046555,
    "gold_at_1": 0.3039106145251397,
    "mIoP": 0.29781971098696464,
    "mIoU": 0.1608658014897579,
    "n": 2685,
}


def test_arm_a_reproduces_frozen_baseline():
    rows = arm_rows("A_baseline.jsonl")
    n = len(rows)
    assert n == FROZEN_BASELINE["n"]
    got = {
        "gold_at_4": sum(r["gold_at_4"] for r in rows) / n,
        "gold_at_1": sum(r["gold_at_1"] for r in rows) / n,
        "mIoP": sum(r["iop"] for r in rows) / n,
        "mIoU": sum(r["iou"] for r in rows) / n,
    }
    # Tolerance 1e-7, not 1e-9: the committed A-E driver wrote each row's iop/iou
    # with round(x, 6) BEFORE averaging, so its published mIoP carries up to
    # ~5e-7 of quantization error. This driver averages at full precision. The
    # observed gap is 3.1e-9 for mIoP and exactly 0 for the rate metrics.
    for k, expected in FROZEN_BASELINE.items():
        if k == "n":
            continue
        assert abs(got[k] - expected) < 1e-7, f"{k}: {got[k]} != {expected}"


# ── retrieval width / PPR budget / frame separation ──────────────────────

@pytest.mark.parametrize("name", ["A_baseline.jsonl", "F_parser_fixed.jsonl", "G_safe_traversal.jsonl"])
def test_budgets_hold_for_every_question(name):
    for r in arm_rows(name):
        assert r["num_ppr_calls"] == 1
        assert (r["num_clip_texts_embedded"] or 1) <= 3
        assert len(r["retrieval_frames"]) <= 4
        assert r["pred_span_end"] >= r["pred_span_start"]
        assert not r["invalid_span"]


@pytest.mark.parametrize("name", ["A_baseline.jsonl", "F_parser_fixed.jsonl", "G_safe_traversal.jsonl"])
def test_retrieval_and_context_frames_never_overlap(name):
    for r in arm_rows(name):
        ret = {f["frame_idx"] for f in r["retrieval_frames"]}
        ctx = {f["frame_idx"] for f in r["context_frames"]}
        assert ret.isdisjoint(ctx)


def test_traversal_preserves_minimum_original_candidates():
    for r in arm_rows("G_safe_traversal.jsonl"):
        t = r["traversal"] or {}
        if t.get("traversal_active"):
            assert t["n_original_preserved"] >= 2


def test_inactive_traversal_is_an_exact_baseline_fallback():
    """When the gate does not fire, G must equal the pure semantic top-4."""
    g = {(r["video"], r["qid"]): r for r in arm_rows("G_safe_traversal.jsonl")}
    for r in g.values():
        if not (r["traversal"] or {}).get("traversal_active"):
            top = [f["frame_idx"] for f in r["retrieval_frames"]]
            sem = [f["frame_idx"] for f in r["semantic_top_k"]]
            assert top == sem

"""Parser v3 coverage, anti-regression, and fairness tests (task section 12.1-12.7).

Every construction listed in task section 4.1 has a case here. The v2 parser is
left untouched and its own test module still passes -- v3 is selected by
config.structured_parser_version.
"""
from __future__ import annotations

import pytest

from iris.query_reformulation import Relation, QueryPlanV2
from iris.query_reformulation_v3 import (
    all_embedding_texts_v3,
    build_query_plan_v3,
    clause_has_explicit_subject,
    extract_structure,
    parser_status,
    seed_embedding_texts,
)


def plan(q: str, type_code: str | None = None) -> QueryPlanV2:
    return build_query_plan_v3(q, type_code=type_code, family=(type_code or " ")[0])


def anchor_of(q: str, type_code: str | None = None) -> str | None:
    """The anchor_primary prompt, or None when the parser emitted none."""
    p = plan(q, type_code)
    for text, role in zip(p.anchor_queries, p.query_roles):
        if role == "anchor_primary":
            return text
    return None


# ── 12.1 parser coverage of every requested language form ────────────────

@pytest.mark.parametrize("question,expect_in_anchor", [
    # "what is/was X doing while/before Y"
    ("what is the man doing while the woman sings", "the woman sings"),
    ("what was the man doing while the woman sings", "the woman sings"),
    ("what is the boy doing before the dog barks", "the dog barks"),
    ("what was the boy doing before the dog barks", "the dog barks"),
    # plural auxiliaries
    ("what are the children doing after the cake arrives", "the cake arrives"),
    ("what were the children doing after the cake arrives", "the cake arrives"),
    # why + progressive / plural
    ("why is the man doing that", "the man doing that"),
    ("why was the man doing that", "the man doing that"),
    ("why are the men doing that", "the men doing that"),
    # how + reacting / moved
    ("how is the girl reacting", "the girl reacting"),
    ("how was the girl reacting", "the girl reacting"),
    ("how is the box moved", "the box moved"),
    ("how was the box moved", "the box moved"),
    # "what happened right/immediately after|before Y"
    ("what happened right after the man fell", "the man fell"),
    ("what happened immediately after the man fell", "the man fell"),
    ("what happened right before the man fell", "the man fell"),
    ("what happened immediately before the man fell", "the man fell"),
    # bare pronoun clauses
    ("what did the girl do before she picked up the cup", "she picked up the cup"),
    ("what did the girl do after he left the room", "he left the room"),
    ("what did the dog do after it dropped the toy", "it dropped the toy"),
    ("what did they do after they sat down", "they sat down"),
    # during / when
    ("what did the man do during the performance", "the performance"),
    ("what did the man do when the music started", "the music started"),
])
def test_anchor_contains_expected_clause(question, expect_in_anchor):
    anchor = anchor_of(question)
    assert anchor is not None, f"no anchor emitted for {question!r}"
    assert expect_in_anchor in anchor, f"{expect_in_anchor!r} not in {anchor!r}"


def test_occurrence_selectors():
    assert plan("what did the man do the first time he sat down").occurrence_selector == "first"
    assert plan("what did the man do the last time he sat down").occurrence_selector == "last"


def test_no_usable_clause_falls_back_to_original_only():
    p = plan("what is the man doing")
    assert parser_status(p) in {"entity_only", "no_structure"}
    seeds, weights = seed_embedding_texts(p)
    # The generic entity query must NOT become a seed (section 4.4).
    assert seeds == (p.normalized_query,)
    assert weights == (1.0,)


# ── 12.2 explicit-subject clauses never get a duplicated subject ─────────

def test_explicit_subject_clause_is_not_prefixed():
    """The exact defect reported for v2: 'a video frame showing girl the man
    pat the pillow'."""
    anchor = anchor_of("what did the girl do after the man pat the pillow", "TN")
    assert anchor == "a video frame showing the man pat the pillow"
    assert "girl the man" not in anchor


def test_subjectless_clause_does_get_the_subject():
    anchor = anchor_of("what did the girl do after posing for a photo", "TN")
    assert anchor == "a video frame showing the girl posing for a photo"


@pytest.mark.parametrize("clause,expected", [
    ("the man pat the pillow", True),
    ("he left the room", True),
    ("she picked up the cup", True),
    ("it dropped the toy", True),
    ("they sat down", True),
    ("two boys ran", True),
    ("people clapped", True),
    ("posing for a photo", False),
    ("wiping the baby's mouth", False),
    ("", False),
])
def test_clause_has_explicit_subject(clause, expected):
    assert clause_has_explicit_subject(clause) is expected


# ── 12.3 pronoun clauses stay semantically intact ────────────────────────

def test_pronoun_clause_preserved_verbatim():
    anchor = anchor_of("what did the dog do after it dropped the red toy", "TN")
    assert anchor == "a video frame showing it dropped the red toy"


def test_midsentence_negation_preserved_verbatim():
    anchor = anchor_of("how does the boy ensure he does not hit the sofa", "CH")
    assert anchor is not None
    assert "does not hit" in anchor


def test_leading_negated_auxiliary_emits_no_anchor():
    """'why didn't the man open the door' must not produce the anchor 'the man
    open the door' -- that is the opposite of what is asked, and a CLIP prompt
    cannot carry the negation."""
    p = plan("why didn't the man open the door", "CW")
    assert parser_status(p) == "negated_no_anchor"
    assert anchor_of("why didn't the man open the door", "CW") is None
    assert seed_embedding_texts(p)[0] == (p.normalized_query,)


# ── 12.4 target-entity query is excluded from the PPR seed ───────────────

def test_target_entity_never_seeds_ppr():
    p = plan("what did the girl do after the man pat the pillow", "TN")
    assert p.target_query == "a video frame showing the girl"
    seeds, _ = seed_embedding_texts(p)
    assert p.target_query not in seeds
    # ...but it is still embedded, in the same batched call, for reranking.
    assert p.target_query in all_embedding_texts_v3(p)


def test_seed_weights_are_positive_and_target_weight_is_zero():
    p = plan("what did the girl do after the man pat the pillow", "TN")
    for role, w in zip(p.query_roles, p.query_weights):
        if role == "target_entity":
            assert w == 0.0
        else:
            assert w > 0.0


# ── 12.6 at most three text embeddings ───────────────────────────────────

@pytest.mark.parametrize("type_code", ["CW", "CH", "TN", "TP", "TC", None])
def test_embedding_budget(type_code):
    for q in [
        "what did the girl do after the man pat the pillow",
        "why did the man couch down",
        "how is the girl reacting while the boy claps",
        "what is the man doing",
    ]:
        p = plan(q, type_code)
        assert len(all_embedding_texts_v3(p)) <= 3
        assert len(seed_embedding_texts(p)[0]) <= 2


# ── 12.7 action aliases are disabled in v3 ───────────────────────────────

def test_action_aliases_never_applied():
    p = plan("what did the man do after picking up the cup", "TN")
    assert p.aliases_applied == ()
    assert all("lift" not in t for t in all_embedding_texts_v3(p))


# ── relation detection (section 4.3) ─────────────────────────────────────

def test_type_code_is_primary_relation_source():
    p = plan("what did the man do after the dog barked", "TC")
    assert p.relation == Relation.DURING          # TC -> DURING wins
    assert p.relation_source == "conflict"        # lexical said AFTER
    assert any("type_lexical_conflict" in n for n in p.notes)


def test_lexical_relation_used_when_no_type_code():
    p = plan("what did the man do after the dog barked", None)
    assert p.relation == Relation.AFTER
    assert p.relation_source == "lexical"


def test_immediacy_modifier_recorded_and_does_not_flip_relation():
    p = plan("what happened right after the man fell", None)
    assert p.relation == Relation.AFTER
    assert "immediacy_modifier" in p.notes


def test_before_in_non_temporal_phrase_does_not_set_relation():
    p = plan("what is the man doing before the camera", None)
    assert p.relation == Relation.NONE


def test_cause_questions_anchor_on_the_head_event_not_the_clause():
    """CW/CH: the observable effect is the main clause."""
    anchor = anchor_of(
        "why did the black dog walk towards the grey dog when the grey dog walked forward", "CW"
    )
    assert "the black dog walk towards the grey dog" in anchor


# ── 12.22 determinism ────────────────────────────────────────────────────

def test_parser_is_deterministic():
    q = "what did the girl do after the man pat the pillow"
    first = plan(q, "TN")
    for _ in range(5):
        assert plan(q, "TN") == first


def test_no_invented_tokens():
    """Every anchor token must already appear in the question (plus the fixed
    CLIP prompt scaffold)."""
    q = "what did the girl do after the man pat the pillow"
    anchor = anchor_of(q, "TN")
    scaffold = {"a", "video", "frame", "showing"}
    qtokens = set(q.lower().split())
    for tok in anchor.split():
        assert tok in qtokens or tok in scaffold, tok


def test_extract_structure_reports_status_for_every_branch():
    assert extract_structure("what did the girl do after posing")["status"] == "clause_extracted"
    assert extract_structure("why did the man couch down")["status"] == "head_event"
    assert extract_structure("what is the man doing")["status"] == "entity_only"

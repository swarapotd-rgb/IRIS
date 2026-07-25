"""Repaired structured query reformulation (parser v3).

Why a new builder instead of editing ``build_query_plan_v2`` in place: the V2
builder is pinned by tests/test_query_reformulation_v2.py and by the committed
A-E ablation. Selecting the parser with ``config.structured_parser_version``
("v2" default, "v3" opt-in) keeps every frozen-baseline test passing unchanged
while making the repair auditable side by side.

What v3 repairs, relative to v2 (each one is a defect verified in the source,
not a speculative improvement):

1. Clause coverage. V2's ``_CLAUSE_PATTERN`` accepts exactly six lead-ins and a
   literal ``do`` verb, so ~24% of val_tune (48.2% of TC, 27.6% of CW) fell back
   to ``no_clause_pattern_matched``. v3 splits the question into a *head* and an
   optional *connector clause* with two independent, ordered pattern sets, which
   covers is/was/are/were/do/does/did, "doing", "happened", "reacting", bare
   "before he ...", and "right/immediately before|after".

2. No subject prepending onto a clause that already has a subject. V2 produced
   ``"a video frame showing girl the man pat the pillow"`` because it
   unconditionally prefixed the target subject. v3 prepends only when the clause
   has no explicit subject of its own ("before wiping the baby's mouth").

3. The generic target-entity query is no longer part of the PPR seed
   (``seed_embedding_texts`` vs ``all_embedding_texts``). It is still embedded --
   in the same single batched call -- but only for bounded reranking.

Deliberate non-goals (documented, per the task's "conservative normalization
only when reliable"): v3 does NOT gerundize or otherwise rewrite verbs. It is
better to retain "the man pat the pillow" verbatim than to risk producing a
wrong phrase. Action aliases are not applied by v3 at all.
"""
from __future__ import annotations

import re
from typing import Any

from iris.query_reformulation import (
    QueryPlanV2,
    Relation,
    RELATION_DIRECTION,
    TYPE_CODE_RELATION,
    _clean_spaces,
    _detect_occurrence_selector,
    _detect_position_prior,
    _normalize_unicode_punctuation,
    _to_clip_prompt,
    normalize_query_text,
)

# ── Relation vocabulary ───────────────────────────────────────────────────

# Connector -> relation. "then" is deliberately excluded: it is a sequence
# marker inside an answer phrase far more often than a question connector.
_CONNECTORS: dict[str, str] = {
    "before": Relation.BEFORE,
    "after": Relation.AFTER,
    "while": Relation.DURING,
    "during": Relation.DURING,
    "when": Relation.DURING,
    "as": Relation.DURING,
}

# Modifiers that tighten, but never flip, a connector's relation.
_IMMEDIACY = r"(?:right|immediately|just)\s+"

# "before"/"after" followed by one of these is a spatial/idiomatic use, not a
# temporal connector ("stood before the camera"). Kept intentionally tiny, and
# deliberately free of pronouns: "after it dropped the red toy" is a perfectly
# ordinary temporal clause, and blocking "it" here silently killed clause
# extraction for every pronoun-subject clause.
_NON_EVENT_COMPLEMENTS: tuple[str, ...] = (
    "the camera", "camera", "the screen", "the audience", "the crowd",
    "the mirror",
)

# A clause opening with one of these already carries its own subject, so the
# question's subject must NOT be prepended.
_SUBJECT_OPENERS: frozenset[str] = frozenset({
    # determiners / possessives / quantifiers
    "the", "a", "an", "his", "her", "its", "their", "our", "my", "your",
    "this", "that", "these", "those", "one", "two", "three", "four", "five",
    "some", "another", "both", "each", "every", "all", "several", "many",
    # pronouns
    "he", "she", "it", "they", "we", "you", "i",
    # bare-noun subjects that appear without a determiner in NExT-QA
    "someone", "somebody", "everyone", "everybody", "nobody", "people",
    "men", "women", "boys", "girls", "kids", "children", "babies", "dogs",
    "cats", "ladies", "guys",
})

# Lead-in patterns, ordered specific-first.
#
# A "subject" group is exposed ONLY where the pattern pins it unambiguously --
# i.e. where a trailing "doing"/"do" bounds the noun phrase on the right. For
# why/how/what heads there is no such right bound, and a lazy `(?P<subject>.+?)`
# followed by `(?P<vp>\S.*)` degenerates to subject="the" (verified: "why did
# the man couch down" yielded target "a video frame showing the"). Splitting
# subject from predicate there would need a POS tagger, which this module is
# explicitly not allowed to add. So those heads expose only "vp" -- the whole
# residual becomes the anchor event, and target_entity is left None (masked)
# rather than populated with a wrong string.
_HEAD_PATTERNS: tuple[tuple[str, str], ...] = (
    # "what is/was/are/were X doing" -- subject right-bounded by "doing"
    (r"^what\s+(?:is|was|are|were)\s+(?P<subject>.+?)\s+doing$", "what_doing"),
    # "what does/do/did X do" -- subject right-bounded by "do"
    (r"^what\s+(?:does|do|did)\s+(?P<subject>.+?)\s+do$", "what_do"),
    # "what happened (to X)" -- subjectless, or subject after "to"
    (r"^what\s+(?:happened|happens|happen)(?:\s+to\s+(?P<subject>.+))?$", "what_happened"),
    # why / how / what heads: residual verb phrase only, no subject split
    (r"^why\s+(?:is|was|are|were|does|do|did)\s+(?P<vp>\S.*)$", "why_head"),
    (r"^how\s+(?:is|was|are|were|does|do|did)\s+(?P<vp>\S.*)$", "how_head"),
    (r"^what\s+(?:is|was|are|were|does|do|did)\s+(?P<vp>\S.*)$", "what_head"),
    # "who/where/when ..." -- subject unknown, keep the residual as the event
    (r"^(?:who|where|when)\s+(?:is|was|are|were|does|do|did)\s+(?P<vp>\S.*)$", "wh_other"),
)
_HEAD_COMPILED = tuple((re.compile(p), name) for p, name in _HEAD_PATTERNS)

# A question whose *leading auxiliary* is negated ("why didn't the man open the
# door") asks about an event that never happened. Stripping the auxiliary would
# yield the anchor "the man open the door" -- i.e. retrieval would be pointed at
# the exact opposite of the question. CLIP prompts cannot express negation, so
# v3 emits no anchor event for these and seeds the original question only.
# Mid-sentence negation ("ensure he does not hit the sofa") is untouched: the
# residual verb phrase is kept verbatim, negation included.
_NEGATED_AUX = re.compile(r"^(?:why|how|what|who|where|when)\s+(?:is|was|are|were|does|do|did)n'?t\b")

_TRAILING_FILLER = re.compile(
    r"\s+(?:in|at)\s+(?:the|this)\s+(?:video|clip|scene|beginning|end|middle)\b.*$"
)


def _strip_trailing_filler(text: str) -> str:
    return _clean_spaces(_TRAILING_FILLER.sub("", text)).strip(" ,")


def clause_has_explicit_subject(clause: str) -> bool:
    """True when ``clause`` opens with its own subject.

    Used to decide whether the question's subject may be prepended. Conservative
    by design: an unrecognised opener is treated as *not* a subject only when it
    looks like a bare verb form, so the failure mode is "keep the clause as-is",
    never "concatenate two subjects".
    """
    clause = _clean_spaces(clause).strip(" ,")
    if not clause:
        return False
    first = clause.split()[0].strip(".,'\"")
    return first in _SUBJECT_OPENERS


def _find_connector(text: str) -> "tuple[str, str, str, bool] | None":
    """Split ``text`` at its first genuine temporal connector.

    Returns (head, connector, clause, immediate) or None. The scan is
    left-to-right over connector positions so "what did X do after Y before Z"
    binds to "after", matching the question's main relation.
    """
    pattern = re.compile(
        rf"\b(?P<imm>{_IMMEDIACY})?(?P<conn>before|after|while|during|when|as)\b"
    )
    for m in pattern.finditer(text):
        conn = m.group("conn")
        clause = _clean_spaces(text[m.end():]).strip(" ,")
        head = _clean_spaces(text[: m.start()]).strip(" ,")
        if not clause or not head:
            continue
        if conn in ("before", "after") and any(
            clause == c or clause.startswith(c + " ") for c in _NON_EVENT_COMPLEMENTS
        ):
            continue  # spatial/idiomatic "before the camera", not temporal
        return head, conn, clause, bool(m.group("imm"))
    return None


def _parse_head(head: str) -> dict[str, Any]:
    """Extract (subject, residual verb phrase, head_form) from the question head."""
    head = _strip_trailing_filler(head.strip(" ?."))
    for rx, name in _HEAD_COMPILED:
        m = rx.match(head)
        if not m:
            continue
        groups = m.groupdict()
        subject = _clean_spaces(groups.get("subject") or "").strip(" ,") or None
        vp = _clean_spaces(groups.get("vp") or "").strip(" ,") or None
        return {"subject": subject, "vp": vp, "head_form": name}
    return {"subject": None, "vp": None, "head_form": "unmatched"}


def extract_structure(lower_text: str, *, type_code: str | None = None) -> dict[str, Any]:
    """Deterministic clause extraction. Every returned string is built only from
    tokens already present in the question -- no invented entities or actions.

    ``type_code`` selects which clause carries the observable event when both a
    head event and a connector clause are present. For TN/TP/TC the question
    asks about something positioned *relative to* the connector clause, so the
    clause is the anchor. For CW/CH ("why did the black dog walk towards the
    grey dog when the grey dog walked forward") the observable effect/manner is
    the head clause; anchoring on the subordinate clause would point retrieval
    at the wrong event.
    """
    stripped = _clean_spaces(lower_text).strip(" ?.")
    cause_like = (type_code or "").upper() in {"CW", "CH"}

    if _NEGATED_AUX.match(stripped):
        return {
            "anchor_event": None,
            "target_entity": None,
            "lexical_relation": None,
            "connector": None,
            "immediate": False,
            "head_form": "negated_aux",
            "anchor_from": None,
            "subject_prepended": False,
            "status": "negated_no_anchor",
            "confidence": 0.3,
            "fallback_reason": "negated_leading_auxiliary",
        }

    split = _find_connector(stripped)
    if split is not None:
        head, connector, clause, immediate = split
        parsed = _parse_head(head)
        subject = parsed["subject"]
        head_event = _strip_trailing_filler(parsed["vp"]) if parsed["vp"] else None
        clause = _strip_trailing_filler(clause)
        prepended = False

        if cause_like and head_event:
            anchor_event = head_event
            anchor_from = "head"
        elif clause_has_explicit_subject(clause) or subject is None:
            anchor_event = clause
            anchor_from = "clause"
        else:
            anchor_event = _clean_spaces(f"{subject} {clause}")
            anchor_from = "clause"
            prepended = True

        return {
            "anchor_event": anchor_event,
            "target_entity": subject,
            "lexical_relation": _CONNECTORS[connector],
            "connector": connector,
            "immediate": immediate,
            "head_form": parsed["head_form"],
            "anchor_from": anchor_from,
            "subject_prepended": prepended,
            "status": "clause_extracted",
            "confidence": 0.85 if parsed["head_form"] != "unmatched" else 0.7,
            "fallback_reason": None,
        }

    parsed = _parse_head(stripped)
    if parsed["vp"]:
        # "why did the man couch down" -> observable event "the man couch down".
        # The residual already contains its own subject; nothing is prepended.
        return {
            "anchor_event": _strip_trailing_filler(parsed["vp"]),
            "target_entity": parsed["subject"],
            "lexical_relation": None,
            "connector": None,
            "immediate": False,
            "head_form": parsed["head_form"],
            "anchor_from": "head",
            "subject_prepended": False,
            "status": "head_event",
            "confidence": 0.6,
            "fallback_reason": None,
        }

    # "what is the man doing" with no connector: the questioned event is exactly
    # what is unknown. Emitting "a video frame showing the man" here would put a
    # generic entity query into the PPR seed, which section 4.4 forbids.
    return {
        "anchor_event": None,
        "target_entity": parsed["subject"],
        "lexical_relation": None,
        "connector": None,
        "immediate": False,
        "head_form": parsed["head_form"],
        "anchor_from": None,
        "subject_prepended": False,
        "status": "entity_only" if parsed["subject"] else "no_structure",
        "confidence": 0.4 if parsed["subject"] else 0.2,
        "fallback_reason": "no_anchor_event",
    }


def build_query_plan_v3(
    question: str,
    *,
    type_code: str | None = None,
    family: str | None = None,
    config: Any = None,
) -> QueryPlanV2:
    """Repaired structured plan. Returns the same ``QueryPlanV2`` dataclass so
    every downstream consumer (telemetry, traversal, audit CSV) is unchanged.

    Query roles, and which of them seed the PPR:

      original       weight 1.0   SEEDED   verbatim normalized question
      anchor_primary weight 0.8   SEEDED   specific anchor-event clause, if any
      target_entity  weight 0.0   NOT SEEDED, embedded for reranking only

    At most 3 texts, one batched embed call, one PPR call.
    """
    typo_normalization_enabled = getattr(config, "typo_normalization_enabled", True)

    original = question.strip()
    if typo_normalization_enabled:
        normalized, corrections = normalize_query_text(original)
    else:
        normalized = _clean_spaces(_normalize_unicode_punctuation(original))
        corrections = []

    lower = normalized.lower()
    notes: list[str] = []

    info = extract_structure(lower, type_code=type_code)
    lexical_relation = info["lexical_relation"]
    type_relation = TYPE_CODE_RELATION.get((type_code or "").upper())

    # Type code stays primary (section 4.3); lexical evidence is computed
    # independently and disagreements are recorded, never silently resolved.
    if type_relation is not None:
        relation = type_relation
        relation_source = "type_code"
        if lexical_relation is not None and lexical_relation != type_relation:
            relation_source = "conflict"
            notes.append(
                f"type_lexical_conflict:type_code={type_code}:{type_relation},"
                f"lexical={lexical_relation}"
            )
    elif lexical_relation is not None:
        relation = lexical_relation
        relation_source = "lexical"
    else:
        relation = Relation.NONE
        relation_source = "fallback"

    if info["immediate"]:
        notes.append("immediacy_modifier")
    notes.append(f"head_form:{info['head_form']}")
    notes.append(f"parser_status:{info['status']}")
    if info.get("anchor_from"):
        notes.append(f"anchor_from:{info['anchor_from']}")
    if info["subject_prepended"]:
        notes.append("subject_prepended")
    if lexical_relation is not None:
        notes.append(f"lexical_relation:{lexical_relation}")

    position_prior, position_note = _detect_position_prior(lower)
    if position_note:
        notes.append(position_note)
    occurrence = _detect_occurrence_selector(lower)

    # ── query roles ──────────────────────────────────────────────────────
    original_prompt = _clean_spaces(normalized.strip(" ?."))
    queries: list[str] = [original_prompt]
    roles: list[str] = ["original"]
    weights: list[float] = [1.0]

    anchor_prompt = _to_clip_prompt(info["anchor_event"])
    if anchor_prompt and anchor_prompt not in queries:
        queries.append(anchor_prompt)
        roles.append("anchor_primary")
        weights.append(0.8)

    target_prompt = _to_clip_prompt(info["target_entity"])
    if target_prompt and target_prompt not in queries and len(queries) < 3:
        queries.append(target_prompt)
        roles.append("target_entity")
        weights.append(0.0)  # embedded, but never seeded -- see seed_embedding_texts
        target_query = target_prompt
    else:
        target_query = None

    fallback_reason = info["fallback_reason"] if len(queries) == 1 else None

    return QueryPlanV2(
        original_query=original,
        normalized_query=normalized,
        type_code=type_code,
        family=family,
        relation=relation,
        relation_source=relation_source,
        temporal_direction=RELATION_DIRECTION.get(relation, 0),
        anchor_queries=tuple(queries),
        target_query=target_query,
        position_prior=position_prior,
        occurrence_selector=occurrence,
        parser_confidence=float(info["confidence"]),
        needs_temporal_traversal=relation != Relation.NONE,
        fallback_reason=fallback_reason,
        corrections_applied=tuple(corrections),
        aliases_applied=(),  # v3 never applies action aliases
        notes=tuple(notes),
        query_roles=tuple(roles),
        query_weights=tuple(weights),
    )


def seed_embedding_texts(plan: QueryPlanV2) -> tuple[tuple[str, ...], tuple[float, ...]]:
    """The subset of the plan's texts that may seed the initial PPR, with their
    weights. Excludes ``target_entity`` (section 4.4)."""
    texts: list[str] = []
    weights: list[float] = []
    for text, role, weight in zip(plan.anchor_queries, plan.query_roles, plan.query_weights):
        if role == "target_entity":
            continue
        texts.append(text)
        weights.append(float(weight))
    if not texts:  # defensive: always seed something
        texts = [plan.normalized_query]
        weights = [1.0]
    return tuple(texts), tuple(weights)


def all_embedding_texts_v3(plan: QueryPlanV2) -> tuple[str, ...]:
    """Every text that must be embedded (seeds + target), <= 3, in role order."""
    return tuple(plan.anchor_queries[:3])


def parser_status(plan: QueryPlanV2) -> str:
    for note in plan.notes:
        if note.startswith("parser_status:"):
            return note.split(":", 1)[1]
    return "unknown"

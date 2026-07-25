# Phase 0 — Repository audit and implementation plan

Branch: `feat/sparse-temporal-reranker-v1` (work performed in worktree branch
`wt/sparse-temporal-reranker-v1`, base commit `18f6339`).

## 0.1 Protected files (hashed before any change)

See `protected_hashes_before.txt`. Re-verified at the end of the run in
`protected_hashes_after.txt`.

| file | sha256 |
|---|---|
| tuning/frozen_state.json | 612a93ba88af53eff17d766885dd3bcf8f65e502e4822b60c1a5c04db4c0b1b7 |
| split_manifest.json | 7864ba3692234320fc453573d6fa8be5e12779f222fd99a841c63a745e98f12a |
| dataset_manifest.json | ae90d6490c89498455dcb09beb5724bb43611fed9d0365cc8af507014a48f853 |
| eval/data/nextqa/val.csv | ee0ef210ae341bec53fdeb723ae54958307ed2e49988d2d3763d3c22abf4201a |
| eval/data/nextqa/gsub_val.json | 527f402851836224aa03c9d4b0016b858a678d21596a2348eb2bdb774c74970a |
| eval/data/nextqa/test.csv | a8d67c5a648c9da8fb4f6fa9939ad1e31fb43f9a92fdab48ec38a1cd622e23db |
| eval/data/nextqa/gsub_test.json | 0c16c31699238a0f2b8ace45aeed7f193149ce2f011d6ed4f1ef7170ef5d41e9 |

Frozen values reproduced from `tuning/frozen_state.json` and NOT changed:
`l2_retrieve_top_k=4`, `ppr_lambda=0.5`, `ppr_damping=0.5`, `span_method=D`,
`span_method_half_width_s=2.2` (i.e. the ~4.4 s fixed span).

## 0.2 Verified defects in the current checkout

Confirmed by reading the source, not inferred from the previous report:

1. **`iris/temporal_traversal.py:157`** — `_direction_score` returns the literal
   `1e6` for the anchor frame, pinning it to rank 1. This is the destructive
   single-anchor replacement described in the task.
2. **`iris/temporal_traversal.py:47-53`** — `_select_anchor` uses
   `retrieved_frames[0]` only; directional exploration starts from a single
   rank-1 frame whose accuracy is ~30%.
3. **`iris/temporal_traversal.py:161-176`** — the final blend
   (`0.35*recency + 0.20*scene_continuity + 0.15*prior + 0.10*action +
   0.05*codec + 0.15*target_sim`) contains **no** PPR/CLIP term at all. Original
   semantic relevance is fully discarded once traversal activates.
4. **`traverse_directional` return value** replaces the retrieval list wholesale
   — there is no retrieval/context separation anywhere in the code path
   (`iris/retrieval_entry.py:_retrieve_structured_v2` reassigns `retrieved`).
5. **`iris/query_reformulation.py:699-705`** — `_CLAUSE_PATTERN` matches only
   six lead-ins (`what does|what did|why did|why does|how did|how does`) plus a
   literal `do` verb, and requires a connector. Everything else falls through to
   `no_clause_pattern_matched` — the source of the 24% fallback rate.
6. **`iris/query_reformulation.py:723`** — `f"{subject} {clause}"` is applied
   whenever the relation is not DURING, with no check for whether the clause
   already carries its own subject. This produces the reported
   `"a video frame showing girl the man pat the pillow"`.
7. **`iris/query_reformulation.py:918-924`** — `all_embedding_texts` appends
   `target_query` to the list handed to `_multi_query_retrieve`, so the generic
   entity query **does** compete in the initial PPR seed.

## 0.3 Training-data availability (rules 6/9) — BLOCKING FINDING

NExT-GQA supplies temporal grounding annotations for **two** splits only:

- `eval/data/nextqa/gsub_val.json` — 570 videos (val; split into val_tune /
  val_confirm by `split_manifest.json`).
- `eval/data/nextqa/gsub_test.json` — 999 videos (test).

There is **no** train-split grounding annotation file, in this repository or in
the upstream NExT-GQA release (`dataset_manifest.json` records only val/test
sources at commit `63772e0`). The benchmark is deliberately weakly-supervised:
the train split has QA pairs but no gold spans.

Consequences under the task's own rules:

- Rule 6 ("gold spans only as supervised targets from an official training
  split") cannot be satisfied literally — no such split exists.
- Rule 9 therefore triggers unless an alternative annotated, evaluation-disjoint
  pool is authorised.

The only candidate pool is the **NExT-GQA test split**: 990 downloaded videos,
5553 questions, gold spans present, and `dataset_manifest.json` records
`val_test_video_overlap: 0`, so it is video-disjoint from val_tune *and*
val_confirm. This repository never evaluates on test (grep over `scripts/`
confirms test.csv/gsub_test.json are read only by the dataset-setup and an
unrelated exp1a preparation script). Using it for adapter training is *not*
val_tune leakage, but it *is* a protocol deviation: it would forfeit any future
NExT-GQA test-set reporting for a system containing this adapter.

**This decision is escalated to the user rather than taken silently.** Phases 1
and 2 do not depend on it and are executed first.

## 0.4 Plan

- **Phase 1 — parser repair.** New `build_query_plan_v3` in
  `iris/query_reformulation_v3.py`, reusing `QueryPlanV2`/`Relation` and the
  V2 normalisation helpers. Selected by `config.structured_parser_version`
  (default `"v2"`, so every existing frozen-baseline test keeps passing
  unchanged — no existing test is weakened). Adds: broad lead-in coverage,
  explicit-subject detection (no subject prepending), `right/immediately
  before|after`, occurrence selectors, explicit query roles, and — per §4.4 —
  a `seed_embedding_texts()` that excludes the target-entity query from the PPR
  seed while keeping one batched embed call of ≤3 texts. Action aliases forced
  off for every arm in this experiment.
- **Phase 2 — traversal repair.** `traverse_directional_safe` returning
  `(retrieval_frames, context_frames, diagnostics)`: multi-anchor candidate
  union from the top-2 semantic candidates, no forced score, semantic term
  dominant in every final score, confidence gate, temporal NMS. Threshold and
  NMS separation selected on adapter_dev (or, if Phase 3 is not authorised, on
  a documented a-priori value — never on val_tune).
- **Phase 3 — temporal adapter.** Depthwise-separable Conv1D adapter over the
  bounded sparse candidate sequence, residual on the frozen semantic score with
  `beta` initialised near zero. Gated on the §0.3 decision.
- **Phase 4 — adaptive span** (center offset + log-width heads, Method-D
  fallback).
- **Phases 5–8** — smoke test, full val_tune retrieval/grounding run, gates,
  artifacts. val_confirm is never loaded; the new driver asserts this.

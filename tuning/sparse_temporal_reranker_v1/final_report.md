# Sparse Temporal Reranker v1 — val_tune report

Branch `feat/sparse-temporal-reranker-v1` (worktree branch `wt/sparse-temporal-reranker-v1`),
base commit `18f6339`. **val_confirm was not run, not loaded, and not inspected.**

---

## 1. Executive verdict

| question | answer |
|---|---|
| Did Gold@4 materially improve? | **No.** Parser repair (F) is +0.04 pp, CI crosses zero. Safe traversal (G) is **−4.02 pp, CI excludes zero — a real regression**. |
| Did mIoP materially improve? | **No.** F −0.0007 (ns). G +0.0045, CI [−0.0013, +0.0102] crosses zero. |
| Did mIoU remain stable? | **Yes.** F +0.0001 (ns), G +0.0035 (ns). No arm loses mIoU. |
| Was any improvement statistically reliable? | **No improvement was.** The only significant paired result in the whole run is G's Gold@4 *regression*. |
| Did the method remain edge-friendly? | **Yes.** Median 3.7–5.0 ms, p95 4.6–6.5 ms, 1 PPR call, ≤3 text embeddings, no extra decode or backbone pass. |
| Should val_confirm remain untouched? | **Yes.** Nothing here comes close to justifying it. |

**The headline result is negative, and it is informative.** Repairing the
structured parser — cutting clause-extraction failure from 24.1% to 1.2% of
val_tune — moved Gold@4 by +0.04 pp. The retrieval bottleneck is therefore
**not** query parsing.

**The main component of this experiment, the learned temporal adapter, was not
run.** NExT-GQA has no train-split temporal annotations, so no leakage-safe
supervised adapter could be trained under the task's own rules. This is task
rule 9 firing, and it is documented in full in §5 and `adapter_status.json`.
Arms H, I and J do not exist and no result is claimed for them.

---

## 2. Repository and protocol verification

- Branch: `wt/sparse-temporal-reranker-v1`; base `18f6339`; environment in `environment.txt`.
- Protected files **byte-identical before and after** (`protected_hashes_before.txt`
  vs `protected_hashes_after.txt`, diff empty):
  `tuning/frozen_state.json`, `split_manifest.json`, `dataset_manifest.json`,
  `eval/data/nextqa/{val.csv,gsub_val.json,test.csv,gsub_test.json}`.
- Frozen values reproduced, never changed: `K=4`, `ppr_lambda=0.5`,
  `ppr_damping=0.5`, span Method D, `half_width=2.2 s` (≈4.4 s span).
- Split: val_tune = 450 videos / 2685 scored questions. val_confirm = 113 videos,
  **never loaded** — `assert_no_val_confirm()` runs on every invocation, and
  `tests/test_sparse_temporal_reranker_fairness.py` asserts no confirm video
  appears in any committed raw file.
- Answer choices never enter retrieval: the driver never reads `a0..a4`, asserted
  by an AST test over the driver and all three new retrieval modules.
- Exact commands: `exact_commands.txt`. Smoke stdout: `smoke_test_stdout.txt`.

### Arm A reproduces the frozen baseline exactly

| metric | committed A-E ablation | this run | Δ |
|---|---|---|---|
| n | 2685 | 2685 | 0 |
| Gold@4 | 0.5303538175046555 | 0.5303538175046555 | **0** |
| Anchor@1 | 0.3039106145251397 | 0.3039106145251397 | **0** |
| mIoP | 0.29781971098696464 | 0.297819714053369 | 3.1e−9 |
| mIoU | 0.1608658014897579 | 0.1608658073672957 | 5.9e−9 |

The two sub-1e−8 gaps are the old driver's `round(x, 6)`-before-averaging; this
driver averages at full precision. The rate metrics are bit-identical.

---

## 3. Parser repair results (Arm F)

`iris/query_reformulation_v3.py`, selected by `config.structured_parser_version`.
v2 is untouched, so the committed A–E ablation stays reproducible and no existing
test was weakened.

Clause-extraction coverage over all 2712 parsed val_tune questions
(`parser_audit.csv`, `parser_diagnostics.json`):

| | v2 | v3 |
|---|---|---|
| usable anchor event emitted | 2058 (75.9%) | **2679 (98.8%)** |
| extraction failure | 654 (24.1%) | 33 (1.2%) |
| TC failure | 186/385 (48.3%) | 28/385 (7.3%) |
| CW failure | 331/1187 (27.9%) | 4/1187 (0.3%) |
| max text embeddings | 3 | 3 |

Defects repaired, each verified in the source before changing it:

1. **Coverage.** v2's `_CLAUSE_PATTERN` accepted six lead-ins and a literal `do`.
   v3 splits head/connector-clause with independent ordered pattern sets covering
   is/was/are/were/do/does/did, "doing", "happened", "reacting", "moved", bare
   pronoun clauses, and right/immediately before|after.
2. **No subject duplication.** The reported defect —
   `"a video frame showing girl the man pat the pillow"` — is gone; v3 emits
   `"a video frame showing the man pat the pillow"`. A clause is prefixed only
   when it has no subject of its own (`"the girl posing for a photo"`).
3. **Target query removed from the PPR seed** (§4.4). `seed_embedding_texts()`
   seeds only `original` + `anchor_primary`; `target_entity` is embedded in the
   same batched call but used for reranking only.
4. **CW/CH anchor on the head event**, not the subordinate clause.
5. **Leading negated auxiliaries emit no anchor** rather than the opposite event
   (a CLIP prompt cannot carry negation). Mid-sentence negation is preserved
   verbatim (22 val_tune questions).
6. **Action aliases disabled** for the whole experiment, asserted by test.

Two honest limitations, both deliberate:

- v3 does **no** verb normalisation. `"the man pat the pillow"` is kept as-is
  rather than risking a wrong gerund. §4.2 permits this ("better to retain the
  original verb phrase").
- For why/how heads v3 does not split subject from predicate — a lazy subject
  group degenerates to `"the"` (this produced the target
  `"a video frame showing the"` in a first draft, caught by spot-check before any
  run). Those questions get `target_entity = None`, i.e. the feature is **masked,
  not faked**. 807/2712 questions carry a target query, 1889 carry two seeds only.

**Result: none of this moves retrieval.** Gold@4 +0.04 pp (CI [−0.49, +0.58] pp),
22 questions gained, 21 lost. Broken down by what the parser did:

| parser status | n | Gold@4 A | Gold@4 F |
|---|---|---|---|
| clause_extracted | 1345 | 0.4796 | 0.4833 |
| head_event | 1308 | 0.5772 | 0.5742 |
| entity_only | 17 | 0.7647 | 0.7647 |
| no_structure | 15 | 0.7333 | 0.7333 |

The questions the repair actually addresses (`clause_extracted`) are the hardest
ones (baseline 0.4796 vs 0.5772), and a correct, specific anchor clause buys
+0.37 pp on them. Type/lexical relation disagreements: 336/2712 (12.4%), recorded
per question, never silently resolved — the type code stays primary.

---

## 4. Traversal repair results (Arm G)

The destructive collapse is **gone**, and it is measurable:

| | Arm E (old, destructive) | Arm G (new, safe) | Arm A |
|---|---|---|---|
| median top-4 temporal spread | **0.667 s** | **8.709 s** | 11.512 s |
| mean original candidates preserved in top-4 | ≈1.3 | **2.94 / 4** | 4 |
| forced anchor score | `1e6` | none (bounded, AST-asserted) | — |
| semantic term in final score | **absent** | 0.60 weight, dominant | — |
| Gold@4 vs A | **−19.7 pp** | **−4.02 pp** | — |

So the repair recovers 15.7 pp of the 19.7 pp Arm-E regression. The gate works
exactly as specified: on the 352/2685 questions where it does not fire, G is a
byte-exact copy of the semantic top-4 (Gold@4 0.5852 for both A and G, asserted
by test).

**But directional promotion is still net-harmful.** On the 2333 questions where
it fires, Gold@4 falls 0.5221 → 0.4758. The mechanism is unambiguous:

- 143 questions lost, 35 gained (net −108).
- Of the 143 lost, **133 (93%) had their gold frame at rank 2 or 3** — exactly the
  tail slots the single promoted directional candidate displaces.
- Of the 35 gained, 29 entered at rank 0–1.

Gold@4 at K=4 is carried disproportionately by the *tail* of the semantic list.
Spending one of four slots on a temporally-adjacent neighbour of an anchor that is
correct only ~30% of the time costs more coverage than it buys — even with the
anchor un-pinned, multiple anchors, dominant semantic scoring, a confidence gate
and NMS all in place. No per-type collapse (regression is broad: CW −2.6, CH −4.8,
TC −3.7, TN −5.8, TP −8.1 pp); mIoP and mIoU both drift slightly *up* (ns),
consistent with promoted frames sitting closer to gold spans without adding
coverage.

Policy values were **not tuned**: `margin_activate=0.05`, `min_separation_s=1.0`,
`min_preserved=3`, `M=16`, fixed a priori (`traversal_policy.json`). §3.4/3.5
require selecting them on adapter_dev, which does not exist (§5); tuning them on
val_tune is forbidden by rule 7, so they were left alone.

---

## 5. Temporal adapter — not built, and why (task rule 9)

**Finding:** NExT-GQA supplies temporal grounding annotations for exactly two
splits — val (`gsub_val.json`, 570 videos, the split partitioned into val_tune and
val_confirm) and test (`gsub_test.json`, 999 videos). **There is no train-split
grounding annotation file**, in this repository or in the upstream release
recorded in `dataset_manifest.json` (source commit `63772e0`). The benchmark is
deliberately weakly supervised.

Rule 6 permits gold spans as supervised targets only from an official *training*
split. None exists. Rules 7 and 8 forbid the only other in-scope annotated pool
(val_tune). Rule 9 then prescribes: stop the supervised-adapter implementation and
document the limitation. That is what was done.

**The option considered and not taken:** training on the NExT-GQA **test** split.
In its favour — 990 videos / 5553 questions of gold spans are already downloaded,
`dataset_manifest.json` records `val_test_video_overlap: 0`, and this repository
never evaluates on test. Against it — it is the benchmark's evaluation set;
training on it is not val_tune leakage but is a genuine protocol deviation that
would permanently forfeit NExT-GQA test-set reporting for any system containing
the adapter. That is a call with a permanent cost, not implied by the task and not
covered by rule 6's wording, so it was escalated rather than taken unilaterally.
No authorisation was received, so the conservative branch was followed.

Consequences, stated plainly:

- Arms **H, I and J were not run**. No adapter was trained, no checkpoint exists,
  no adapter metric is reported anywhere in this directory.
- Adaptive span prediction (§6) is blocked by the same finding — it also trains on
  gold spans from adapter_train.
- The traversal/NMS/M thresholds could not be selected on adapter_dev (§4 above).
- `adapter_train_videos.json`, `adapter_dev_videos.json`, `adapter_config.json`,
  `adapter_training_history.json` and the checkpoint hash/model-size report are
  **absent by design**; `adapter_status.json` records why in machine-readable form.

The integration points are in place and tested — `retrieve_v3(..., adapter=...)`,
`traverse_safe(..., adapter_scores=, adapter_confidence=)`, residual application
with baseline fallback — so an adapter can be dropped in without touching the
retrieval path. What would unblock it: authorisation to burn the test split, or an
external (question, video, gold span) dataset disjoint from NExT-QA val
(Charades-STA, ActivityNet-Captions, QVHighlights) ingested through the same sparse
pipeline.

---

## 6. Adaptive span — not built

Blocked by §5. Every arm therefore uses frozen Method D (`half_width=2.2 s`),
anchored on the **verbatim** question embedding in all arms so no span delta is
confounded with a query-text change. Observed span behaviour is consequently
near-identical across arms: mean width 4.283–4.290 s, median 4.4 s, **0 zero-width
spans, 0 invalid spans** in 8055 rows. The fixed-width mIoP bottleneck identified
in the task diagnosis is untouched and remains open.

---

## 7. Complete results table (val_tune, n = 2685, 450 videos)

| arm | Gold@1 | Gold@2 | Gold@4 | MRR | mIoP | mIoU | IoP@0.5 | median ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| **A** frozen baseline | 0.30391 | 0.41453 | **0.53035** (1424/2685) | 0.39361 | 0.297820 | 0.160866 | 0.30093 | 3.957 | 4.940 |
| **F** parser-fixed | 0.30577 | 0.41490 | **0.53073** (1425/2685) | 0.39500 | 0.297129 | 0.160940 | 0.29907 | 4.877 | 6.306 |
| **G** safe traversal | 0.30168 | 0.38063 | **0.49013** (1316/2685) | 0.37353 | 0.302275 | 0.164385 | 0.30317 | 5.003 | 6.497 |
| H, I, J | — | — | **not run** (§5) | — | — | — | — | — | — |

Per-type, per-gold-duration-bucket, per-video-duration-bucket, per-parser-status,
per-relation and per-traversal-state breakdowns: `per_type.csv`,
`per_duration_bucket.csv`, `per_video_duration_bucket.csv`, `per_parser_status.csv`,
`per_relation.csv`, `per_traversal_active.csv`. Per-video rates and deltas:
`per_video.csv`. Every gained/lost question: `gained_lost.csv`.

---

## 8. Paired, video-clustered statistical analysis

Bootstrap resamples **videos** (450 clusters), not questions; seed `20260725`,
2000 resamples; 95% percentile CIs (`statistical_report.json`).

| arm | metric | Δ vs A | 95% CI | significant |
|---|---|---|---|---|
| F | Gold@4 | +0.00037 | [−0.00488, +0.00576] | no |
| F | Gold@1 | +0.00186 | [−0.00326, +0.00680] | no |
| F | mIoP | −0.00069 | [−0.00366, +0.00228] | no |
| F | mIoU | +0.00007 | [−0.00186, +0.00204] | no |
| G | Gold@4 | **−0.04022** | **[−0.04989, −0.03036]** | **yes (regression)** |
| G | Gold@1 | −0.00223 | [−0.01415, +0.00888] | no |
| G | mIoP | +0.00446 | [−0.00132, +0.01017] | no |
| G | mIoU | +0.00352 | [−0.00041, +0.00752] | no |

G's mIoP and mIoU gains **cross zero and are not improvements**.

### Stopping gates (§8), applied as written

| gate | required | F | G | verdict |
|---|---|---|---|---|
| minimum Gold@4 | ≥ +2.0 pp vs A | +0.04 pp | −4.02 pp | **both fail** |
| Gold@4 CI above zero | yes | crosses | below zero | **both fail** |
| Anchor@1 must not decrease | yes | ok | ok (ns) | pass |
| latency in edge budget | yes | yes | yes | pass |

No arm clears the minimum retrieval gate, so **the expensive downstream answerer
was not run** and no AccQA/AccGQA is reported. val_confirm was not touched.

---

## 9. Efficiency report

| arm | cold median / p95 (ms) | warm median / p95 (ms) | PPR calls | text embeddings | pool M |
|---|---|---|---|---|---|
| A | 3.739 / 4.584 | 3.957 / 4.940 | 1 | 1 | 4 |
| F | 4.760 / 6.201 | 4.877 / 6.306 | 1 | ≤3 | 16 |
| G | 4.978 / 6.492 | 5.003 / 6.497 | 1 | ≤3 | 16 |

Cold = each arm alone in a fresh process over the same 30-video/202-question
subset (empty text-embedding cache). Warm = the full run, where arms share one
process and A ran coldest — reported that way rather than hidden. Index load from
disk is excluded from the timer for every arm equally. Targets (median ≤10 ms,
p95 ≤15 ms) **met with ~2× headroom**. No extra full-video decode, no extra
backbone pass, bounded memory (M=16 candidates regardless of video length).
Adapter parameter count and model size: **n/a, no adapter exists**.

---

## 10. Failure analysis

Where the remaining errors come from, measured rather than asserted:

- **Not parser failure.** Extraction failure fell 24.1% → 1.2% and Gold@4 moved
  +0.04 pp. On the 1345 questions where v3 newly produces a specific anchor clause,
  Gold@4 rose 0.4796 → 0.4833.
- **Not survivor admission.** ~99.85% of gold evidence survives (prior diagnostic,
  unchanged here); the correct frame is in the pool and the ranking cannot find it.
- **Not candidate-pool width.** Widening PPR to M=16 leaves the top-4 prefix
  bit-identical to the K=4 call (verified 26/26 on real indexes), so a wider pool
  adds candidates without improving the ordering that selects among them.
- **Incorrect direction / wrong slot spend.** G's regression is fully explained by
  which slots it spends: 93% of lost questions had gold at rank 2–3.
- **Span width/centre.** Untouched — every arm is fixed 4.4 s; mIoP stays ≈0.30
  while Gold@4 varies by 4 pp, confirming the span is a largely independent
  bottleneck.
- **Residual: semantic confusion in the cached static representation.** With
  admission solved, parsing solved, and ranking width and direction ruled out, the
  binding constraint is that a single frozen CLIP embedding per survivor does not
  encode *which* moment answers *this* question. Repetitive actions, similar
  actors and scene transitions are exactly the cases the static embedding cannot
  separate — and no amount of parser, alias, traversal or scalar tuning creates
  the missing question-specific temporal semantics.

**This is the experiment's real finding: the cached static visual representation
is the limiting factor.** It is also precisely the hypothesis the temporal adapter
was designed to test, and the one this run could not test for lack of any
protocol-legal supervised training data.

---

## 11. Final recommendation

| component | verdict |
|---|---|
| **Parser repairs (v3)** | **Keep the code, do not claim a gain.** It is strictly more correct (98.8% coverage, no malformed prompts, target excluded from the seed), costs ~0.9 ms, and is statistically tied with the baseline. Keep it as a correctness fix, not a retrieval improvement. It should stay behind `structured_parser_version` with the frozen default until something downstream benefits. |
| **Safe traversal** | **Reject as a default.** It repairs the Arm-E collapse (15.7 pp of 19.7 pp recovered) and proves the design is non-destructive, but it still costs 4.0 pp of Gold@4 with a CI excluding zero. Keep the module for the adapter integration path; do not enable it. |
| **Temporal adapter** | **Unresolved — not tested.** No protocol-legal training data exists (§5). Do not claim anything about it in either direction. |
| **Adaptive span** | **Unresolved — not tested.** Same cause. The ~4.4 s fixed span remains an open, unaddressed mIoP bottleneck. |

**Does the evidence justify a later val_confirm run? No.** Nothing improved. The
frozen configuration stands unchanged. val_confirm was not run during this task and
should not be run on the strength of these results.

Suggested next step, in priority order: (1) obtain a protocol-legal grounding
training set (external dataset, or an explicit decision about the test split) and
run the adapter arms as specified — that is the one hypothesis with real upside
left; (2) attack the fixed-span bottleneck, which is independent of retrieval and
currently untouched; (3) treat the cached per-frame static embedding itself as the
variable, since every ranking-side intervention tried so far has been absorbed by
it.

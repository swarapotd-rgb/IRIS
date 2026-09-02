# Antigravity Task — Diagnostic: L2 Scene-Shortlist Recall

## Objective

Measure one number: **for each question, does the gold scene survive the L2
centroid shortlist?**

This closes a measured gap in the retrieval funnel. We already know:

- **L1 admission is not the bottleneck** — survivor-coverage ceiling is
  **99.85% (2,681/2,685)**, artifact `survivor_coverage_ceiling_report.md`
  at commit `2ad7ab9`.
- **Retrieval is the bottleneck** — 64% of the Acc@GQA failure group never
  had a gold frame in the retrieved pool at all (bucket c), artifact
  `tuning/val_confirm_gap_diagnostic_report.md` at commit `c24f8f8`.

Between those two facts sits an unmeasured funnel: `iris/scene_retrieval.py`
keeps only `max(4, ceil(sqrt(num_scenes)))` scenes — for a 528-scene video
that is **23 of 528, i.e. 4.4% of scenes** — and ranks them by each scene's
**mean** CLIP embedding. Nobody has measured what that step throws away.

This is a **measurement task**. You are not tuning anything, not changing
production behaviour, and not fixing anything. A bad number is a successful
outcome and must be reported as such.

---

## Non-negotiables (read before starting)

1. **Never fabricate a number.** Every figure in your report must come from a
   file you wrote during this run. If a step fails, report the failure, say
   what you tried, and stop that branch — do not estimate, do not
   extrapolate, do not fill in a plausible value.
2. **Read-only with respect to production.** Do not modify
   `tuning/frozen_state.json`, `tuning/all_trials.csv`, `iris/*.py`, or any
   index cache. This diagnostic reads cached indexes and annotations only.
3. **No re-ingest, no GPU, no PPR, no captioner, no LLM.** Everything needed
   is already in the cached `.npz` indexes. If you find yourself about to
   re-ingest a video, stop and report why.
4. **Do not tune.** You are measuring the shortlist width that production
   currently uses. The width sweep in Step 4 is a diagnostic curve, not a
   search for a better value, and its result must not be written back into
   any config.
5. **Report the failure modes.** Videos whose cache is missing, questions
   whose gold span has no matching scene, config-hash mismatches — all get
   counted and listed, not silently dropped.
6. **If you are blocked, write the blocker report and stop.** Do not
   substitute a different split, a different cache, or a proxy metric to
   produce output.

---

## Step 0 — Box, branch, and asset verification

Work on branch **`feat/prerun-fixes`**. Do not create a new branch.

Run on the box that actually holds the index caches (`worker-1`,
`/home/ccbd/IRIS-1`), not a Windows checkout. The Windows checkout has a
known annotation-staging defect (`gsub_val.json` and `gsub_test.json` are
byte-identical there) and must not be used for this.

Before any measurement, verify and report:

| Check | How |
|---|---|
| Hostname, `uname -a`, repo path, current commit | shell |
| `tuning/index_cache_val_confirm_e2e/` exists | count `.npz` files; expect **112**, config-hash `4edae64ed40256e3` |
| Family-1 val_tune cache exists | look for the cache built under config-hash `cab2bac1628012a3` (the one `2ad7ab9`'s PART A used, val_tune, 450 videos / 2,685 questions) |
| Annotation files | record SHA-256 of every annotation file you read |
| `gsub_val.json` and `gsub_test.json` are **not** byte-identical | compare hashes; if they are identical, **STOP** — wrong box |

**Split selection, in priority order:**

- **PRIMARY: val_tune under config-hash `cab2bac1628012a3`** (2,685
  questions). This is the split the 99.85% ceiling was measured on, so the
  funnel chains exactly: 99.85% → (this number) → top-k.
- **SECONDARY: val_confirm under config-hash `4edae64ed40256e3`** (639
  questions). This is the split bucket (c) was measured on, so it chains to
  the 64% figure.

Run **both** if both caches are present. If only one is present, run that one
and say clearly in the report which chain is therefore unverifiable. **Do not
mix caches within a single reported number** — a config-hash mismatch between
index and annotation set invalidates the result.

---

## Step 1 — Reconstruct the shortlist exactly as production computes it

Do not approximate this. Read `iris/scene_retrieval.py` and reproduce its
behaviour precisely. As of this writing the relevant logic is:

```python
shortlist_width = getattr(config, "scene_shortlist_width", 0) \
                  or max(4, math.ceil(math.sqrt(num_scenes)))
shortlist_width = min(shortlist_width, num_scenes)

scene_ranking = scorer.score(anchor_query_embedding, centroids)
shortlisted_scene_ids = {sid for sid, _ in scene_ranking[:shortlist_width]}
```

with `LinearScanScorer.score` computing one cosine per scene centroid against
the **anchor** query embedding, sorted descending with a stable tie-break on
ascending `scene_id`.

Three things that will silently corrupt this measurement if you get them
wrong:

1. **Use `FrameRecord.scene_id`, never `AsphodelNode.scene_id`.** The code
   carries an explicit warning that `AsphodelNode.scene_id` is a monotonic
   I-frame-segmentation id which `L2Asphodel._refresh_scene_ids` overwrites
   on every graph build, so it does not match the real valley-boundary
   `scene_id`. Getting this wrong will produce a plausible but meaningless
   number.
2. **Centroids come from `index._scene_centroids`** — the per-scene mean CLIP
   embedding, excluding frames with `scene_id < 0` or no `clip_embedding`.
   Use the stored centroids; do not recompute them.
3. **Use the anchor embedding path** for centroid scoring, the same
   single-vector path production uses — not the multi-query pool-scoring
   path.

Verify your reconstruction before trusting it: for a sample of at least 20
questions, confirm your shortlisted scene set is identical to what
`retrieve_scene_sparse` selects when called directly. Report the match rate.
**If it is not 20/20, stop and report** — everything downstream depends on
this being exact.

---

## Step 2 — Define "gold scene"

A scene is **gold** for a question if it contains at least one L1-admitted
frame whose timestamp falls inside that question's gold span. Use the
max-overlap gold span when a question has several, the same rule PART A used
and the same rule the official metric uses.

Note that a gold span typically spans several scenes: gold spans have a
median of roughly 5 s and scenes run about 1–1.5 s, so expect 3–5 gold scenes
per question. Record the count.

Questions with **zero** gold scenes should not exist — the 99.85% ceiling
says the gold frame survives L1 — so any you find are either the 4 known
short-span failures or a bug in your gold-scene mapping. Count them, list
them by `video_id`/`qid`, and investigate before reporting. Do not silently
drop them.

---

## Step 3 — Primary measurement

For every question in the split, compute and record:

- `n_scenes` — total scenes in that video
- `shortlist_width` — as production would compute it
- `n_gold_scenes` — how many scenes are gold
- `gold_scene_ranks` — the rank of each gold scene in the centroid ranking
  (1-indexed)
- `best_gold_rank` — the minimum of the above
- `hit_at_shortlist` — **the headline**: does at least one gold scene fall
  within the top `shortlist_width`?
- `frac_gold_captured` — fraction of that question's gold scenes inside the
  shortlist
- `fallback_all_scenes_fired` — whether production's `max(sims) < 0.20`
  adaptive fallback (SCENE-001) would fire for this question, and separately
  whether the empty-pool fallback would fire
- `effective_hit` — `hit_at_shortlist OR fallback_all_scenes_fired`, since a
  fired fallback restores the full scene set

Report **both** the raw `hit_at_shortlist` rate and the `effective_hit` rate.
They can differ substantially and only the second describes production.

Break the rates down by:

- question family (causal CW/CH vs temporal TN/TC/TP), matching PART A's
  breakdown so the two diagnostics are directly comparable
- gold-span length bucket (≤2.5 s vs >2.5 s), same convention
- `n_scenes` quartile, to show whether the `sqrt` rule degrades on
  scene-dense videos

---

## Step 4 — Recall versus shortlist width

The point of this sweep is to size a possible redesign, **not** to pick a new
value. Recompute `hit_at_shortlist` at these widths, holding everything else
fixed:

`ceil(sqrt(N))` (production), `2*ceil(sqrt(N))`, `4*ceil(sqrt(N))`,
`ceil(N/4)`, `ceil(N/2)`, `N` (all scenes)

Report recall at each width, and the mean number of candidate frames the pool
would then contain — that second column is the cost axis. Present it as a
table; a recall-versus-breadth curve is the actionable output of this whole
task.

---

## Step 5 — Where do gold scenes actually rank?

Produce a histogram of `best_gold_rank`, plus these summary statistics:
median, 90th percentile, 99th percentile, and max.

This single distribution decides the redesign, so state its reading
explicitly in the report:

- If most misses sit **just past the cutoff** (e.g. ranks 24–60 against a
  cutoff of 23), the centroid ranking is basically sound and **widening the
  shortlist fixes it**.
- If misses are **scattered deep** (ranks in the hundreds), the centroid
  ranking itself is uninformative and widening will not help — the mean-CLIP
  centroid is the thing to replace.

Also report how often each fallback fires, as a percentage of questions.

---

## Step 6 — Outputs

Commit all of these to `feat/prerun-fixes`:

- `tuning/scene_shortlist_recall/<split>_per_question.csv` — one row per
  question with every field from Step 3
- `tuning/scene_shortlist_recall/<split>_summary.json` — headline rates, all
  breakdowns, the width sweep, and the rank statistics
- `tuning/scene_shortlist_recall/width_sweep.csv` — Step 4
- `tuning/scene_shortlist_recall_report.md` — the human-readable report
- The script itself, at `scripts/scene_shortlist_recall.py`

In the report, include for every artifact you read: absolute path, git commit
sha where applicable, and SHA-256. End with an explicit verdict line:

```
SCENE_SHORTLIST_RECALL: <rate> (<n_hit>/<n_total>) on <split> @ <config-hash>
```

---

## Step 7 — Pre-registered interpretation

Write this table into the report **before** you look at the number, and then
state which row fired. Do not invent a fourth reading after the fact.

| Effective recall | Reading | Consequence |
|---|---|---|
| **≥ 95%** | The scene shortlist is not a major bottleneck. | The loss is downstream — final frame ranking within an adequate pool. Priority goes to the embedding adapter and window-level selection, not to wider scene search. |
| **85–95%** | Real but secondary loss. | Worth widening, but it cannot alone explain bucket (c) at 64%. Both fixes needed. |
| **70–85%** | **Major bottleneck found.** | IRIS is discarding the correct scene before frame ranking ever runs. Wider and parallel scene search becomes the highest-value change in the pipeline. |
| **< 70%** | Dominant bottleneck. | The centroid shortlist is the primary cause of retrieval failure. Redesign it before anything else. |

Cross-check and state it plainly: the 99.85% L1 ceiling and the 64% bucket-(c)
failure rate bound this number. If your measured recall is high **and**
bucket (c) is 64%, then the loss must be in the final top-k ranking, and the
report should say so in one sentence.

---

## Guards — stop and report instead of proceeding if

- Your shortlist reconstruction does not match `retrieve_scene_sparse` on all
  20 sampled questions → **stop**, report the mismatch
- `gsub_val.json` and `gsub_test.json` are byte-identical → **stop**, wrong box
- The index cache config-hash does not match the annotation split you loaded
  → **stop**, do not mix
- Any step would require a re-ingest, a GPU, or a model call → **stop**, this
  task needs none of them
- More than 1% of questions have zero gold scenes → **stop**, your gold-scene
  mapping is probably wrong, not the pipeline

---

## What "done" looks like

One number with a confidence interval, a recall-versus-width table, a rank
histogram, and a one-paragraph statement of which pre-registered row fired
and what it means for the next change. Nothing is tuned, nothing in
production is modified, and every figure traces to a committed file.

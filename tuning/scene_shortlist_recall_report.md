# L2 Scene-Shortlist Recall -- diagnostic

**Measurement only.** Nothing was tuned; no production behaviour, config, index
cache, `tuning/frozen_state.json`, or `tuning/all_trials.csv` was modified. The
Step-4 width sweep is a diagnostic curve, not a search for a better value, and its
result is deliberately *not* written back into any config.

## Verdict

```
SCENE_SHORTLIST_RECALL: 0.7359 (1976/2685) on val_tune @ cab2bac1628012a3
SCENE_SHORTLIST_RECALL: 0.7340 (469/639) on val_confirm @ 4edae64ed40256e3
```

Both splits, measured independently on different caches and different question
sets, land within 0.2 points of each other. **Pre-registered row 3 fired on both:**
70-85%, *major bottleneck found*.

## Step 0 -- box, branch and asset verification

| Check | Result |
|---|---|
| Hostname | `worker-1` |
| `uname -a` | `Linux worker-1 6.8.0-136-generic #136~22.04.1-Ubuntu SMP PREEMPT_DYNAMIC Fri Jul  3 16:29:11 UTC x86_64 GNU/Linux` |
| Repo path | `/home/ccbd/IRIS-1` |
| Branch | `feat/prerun-fixes` (no new branch created) |
| Commit at run time | `5628199adf9c771c58f52ae029b26c7913aae39d` |
| `tuning/index_cache_val_confirm_e2e/` | exists, **112** `.npz`, all config-hash `4edae64ed40256e3` |
| Family-1 val_tune cache | `tuning/index_cache/`, **450** `.npz` under config-hash `cab2bac1628012a3` |
| `gsub_val.json` vs `gsub_test.json` | **NOT byte-identical** (`527f4028...` vs `0c16c316...`) -- correct box |

Both caches were present, so **both splits were run**; neither funnel chain is
left unverifiable. No cache was mixed across a reported number: every row is
computed from the index whose filename carries that split's config-hash, loaded
by explicit path. `part3_tune.ensure_indexes()` was deliberately *not* called, so
no re-ingest could be triggered.

### Config-hash provenance note (checked, benign)

Recomputing `ingest_config_hash` from the val_confirm indexes' own stored
`config_snapshot` reproduces `4edae64ed40256e3` exactly. The same recomputation
on the val_tune indexes yields `368e93b7bb16954b`, not the `cab2bac1628012a3` in
their filenames. This is **not** cache corruption: `cab2bac1628012a3` is the hash
of the *Family-1-era* `INGEST_RELEVANT_KEYS`, which at that time held five keys.
Restricting the payload to
`('retrieval_strategy','l2_retrieve_top_k','peak_distance','peak_prominence','peak_order')`
reproduces `cab2bac1628012a3` bit-exactly from the stored snapshot; the three
`action_score_weights` / two `persistence_gate` keys were appended to the key list
by later families. The index contents are self-consistent with their recorded
snapshot, and this is the same cache `2ad7ab9`'s PART A read.

### Splits as measured

| Split | Questions | Videos | Cache | Config-hash |
|---|---|---|---|---|
| val_tune | 2,685 | 450 | `tuning/index_cache/` | `cab2bac1628012a3` |
| val_confirm | 639 | 112 | `tuning/index_cache_val_confirm_e2e/` | `4edae64ed40256e3` |

2,685 / 450 matches PART A's cohort exactly; 639 / 112 matches the bucket-(c) gap
diagnostic's cohort exactly. Both chains hold.

## Step 1 -- shortlist reconstruction, verified against production

The reconstruction mirrors `iris/scene_retrieval.py:retrieve_scene_sparse`:
`scene_shortlist_width` is `0` in every frozen config on disk, so
`max(4, ceil(sqrt(num_scenes)))` always applies, clamped to `num_scenes`;
`LinearScanScorer.score` runs one cosine per centroid against the **anchor**
single-vector query embedding, sorted descending with a stable ascending-`scene_id`
tie-break. Centroids are read from the stored `index._scene_centroids`, never
recomputed. Scene membership is read from `FrameRecord.scene_id`, never
`AsphodelNode.scene_id` (which `L2Asphodel._refresh_scene_ids` overwrites on every
graph build).

- **val_tune: 20/20 exact match** against `retrieve_scene_sparse` called directly.
- **val_confirm: 20/20 exact match** against `retrieve_scene_sparse` called directly.

The comparison accounts for the fact that the function's `trace` records the
*post-fallback* scene set: where a fallback was predicted, the expected set is
every scene; otherwise it is the top-`shortlist_width` set. The match is exact in
both cases. 40/40 across the two splits, so nothing downstream rests on an
approximation.

One model *is* touched: the CLIP **text** encoder (`torch-cpu`, ViT-B/32,
verified deterministic across repeat calls). A centroid shortlist is undefined
without a query embedding, and this is the identical path production uses. No
re-ingest, no GPU, no PPR over the measured set, no captioner, no LLM.

## Step 2 -- gold-scene definition and the zero-gold check

A scene is gold when it contains at least one L1-admitted frame whose timestamp
falls inside the question's gold span, using the longest gold span when a question
has several (PART A's convention). An any-span variant is carried in every row and
summary as a robustness column.

| Split | mean gold scenes | median | zero-gold questions |
|---|---|---|---|
| val_tune | 6.022 | 4 | 4 (0.15%) |
| val_confirm | 6.009 | 4 | 0 (0.00%) |

Median 4 gold scenes per question, matching the 3-5 expected from ~5 s spans over
~1-1.5 s scenes. The zero-gold count is far under the 1% guard.

**The four val_tune zero-gold questions are exactly the four known short-span
failures**, not a mapping bug -- every one has a sub-second gold span:

| video_id | qid | gold span (s) | n_scenes | admitted frames |
|---|---|---|---|---|
| `4838145161` | 7 | 0.4 | 38 | 257 |
| `7001078933` | 2 | 0.6 | 13 | 86 |
| `7164729910` | 8 | 0.4 | 19 | 88 |
| `7164729910` | 5 | 0.4 | 19 | 88 |

Independent confirmation that the mapping is correct: with the shortlist removed
entirely (`N_all_scenes` in the Step-4 sweep) val_tune recall is
**2681/2685 = 
99.85%** -- bit-exact with PART A's
99.85% (2,681/2,685) L1 survivor-coverage ceiling. The gold-scene metric reproduces
the independently measured ceiling to the question, so the funnel chains cleanly.
No videos were missing from either cache and no question lacked centroids.

## Step 3 -- primary measurement

| Split | `hit_at_shortlist` | 95% CI | `effective_hit` | 95% CI |
|---|---|---|---|---|
| val_tune | 73.52% (1974/2685) | [71.82%, 75.15%] | 73.59% (1976/2685) | [71.89%, 75.23%] |
| val_confirm | 73.24% (468/639) | [69.68%, 76.53%] | 73.40% (469/639) | [69.84%, 76.67%] |

Raw and effective rates are nearly identical because **the fallbacks almost never
fire**: the SCENE-001 `max(sims) < 0.20` adaptive fallback fires on
0.1862% of val_tune and
0.1565% of val_confirm questions, and the
empty-pool fallback fires on **0.00%** of both. The recall-safety net that exists in
the code is, in practice, not engaged -- it recovers 2 questions out of 2,685.

How narrow the net actually is:

| Split | mean n_scenes | median | max | mean shortlist width | mean width / n_scenes | mean frac of gold scenes captured |
|---|---|---|---|---|---|---|
| val_tune | 30.51 | 25 | 89 | 5.778 | 24.35% | 36.72% |
| val_confirm | 30.83 | 27 | 126 | 5.84 | 24.15% | 37.45% |

A factual correction to the task framing: no 528-scene video exists in either
cache. The largest is 89 scenes (val_tune) / 126 (val_confirm), and the sqrt rule
keeps about **24% of scenes on average**, not 4.4%. The shortlist is nonetheless
losing the gold scene a quarter of the time, and it captures only ~37% of each
question's gold scenes even when it hits one.

### Breakdowns

#### `hit_at_shortlist`

| Group | val_tune | n | val_confirm | n |
|---|---|---|---|---|
| causal | 75.06% | 1564 | 73.51% | 370 |
| temporal | 71.36% | 1121 | 72.86% | 269 |
| CW | 74.66% | 1172 | 70.42% | 284 |
| CH | 76.28% | 392 | 83.72% | 86 |
| TN | 69.46% | 704 | 65.87% | 167 |
| TC | 76.05% | 380 | 88.51% | 87 |
| TP | 59.46% | 37 | 60.00% | 15 |
| span <= 2.5 s | 58.61% | 488 | 62.73% | 110 |
| span > 2.5 s | 76.83% | 2197 | 75.43% | 529 |
| n_scenes Q1 | 84.27% | 674 | 78.86% | 175 |
| n_scenes Q2 | 75.42% | 716 | 78.29% | 152 |
| n_scenes Q3 | 70.78% | 664 | 73.62% | 163 |
| n_scenes Q4 | 62.76% | 631 | 61.07% | 149 |

#### `effective_hit`

| Group | val_tune | n | val_confirm | n |
|---|---|---|---|---|
| causal | 75.13% | 1564 | 73.78% | 370 |
| temporal | 71.45% | 1121 | 72.86% | 269 |
| CW | 74.74% | 1172 | 70.77% | 284 |
| CH | 76.28% | 392 | 83.72% | 86 |
| TN | 69.60% | 704 | 65.87% | 167 |
| TC | 76.05% | 380 | 88.51% | 87 |
| TP | 59.46% | 37 | 60.00% | 15 |
| span <= 2.5 s | 58.61% | 488 | 62.73% | 110 |
| span > 2.5 s | 76.92% | 2197 | 75.61% | 529 |
| n_scenes Q1 | 84.27% | 674 | 79.43% | 175 |
| n_scenes Q2 | 75.42% | 716 | 78.29% | 152 |
| n_scenes Q3 | 71.08% | 664 | 73.62% | 163 |
| n_scenes Q4 | 62.76% | 631 | 61.07% | 149 |

Three consistent signals across both splits:

1. **Short gold spans are much worse.** val_tune 58.61% vs 76.83%. A short span
   touches fewer scenes, so there are fewer chances for any of them to rank high.
2. **The sqrt rule degrades monotonically on scene-dense videos.** val_tune goes 84.27% (Q1) -> 62.76% (Q4);
   val_confirm 78.86% -> 61.07%. This is the
   sqrt rule failing exactly where it was supposed to hold: the width grows as
   `sqrt(N)` while the number of distractor scenes grows as `N`.
3. **Temporal questions trail causal ones**, driven by TN (`69.46%` val_tune) and TP, the
   two types whose answer depends on *when* rather than *what* -- exactly what a
   mean-CLIP centroid cannot represent.

## Step 4 -- recall versus shortlist width

Everything else held fixed; only the cutoff into the same centroid ranking moves.
`mean pool frames` is the cost axis (mean candidate frames the survivor pool would
then contain).

**val_tune** (n=2,685)

| Width rule | mean width | recall | 95% CI | mean pool frames | cost vs production |
|---|---|---|---|---|---|
| `ceil_sqrt_N` **(production)** | 5.778 | 73.52% (1974/2685) | [71.82%, 75.15%] | 40.57 | 1.00x |
| `2x_ceil_sqrt_N` | 11.396 | 88.90% (2387/2685) | [87.66%, 90.03%] | 73.64 | 1.82x |
| `4x_ceil_sqrt_N` | 21.73 | 98.47% (2644/2685) | [97.94%, 98.87%] | 127.2 | 3.14x |
| `ceil_N_over_4` | 8.0 | 78.29% (2102/2685) | [76.69%, 79.81%] | 53.37 | 1.32x |
| `ceil_N_over_2` | 15.512 | 92.89% (2494/2685) | [91.85%, 93.80%] | 95.68 | 2.36x |
| `N_all_scenes` | 30.509 | 99.85% (2681/2685) | [99.62%, 99.94%] | 166.41 | 4.10x |

**val_confirm** (n=639)

| Width rule | mean width | recall | 95% CI | mean pool frames | cost vs production |
|---|---|---|---|---|---|
| `ceil_sqrt_N` **(production)** | 5.84 | 73.24% (468/639) | [69.68%, 76.53%] | 40.19 | 1.00x |
| `2x_ceil_sqrt_N` | 11.509 | 89.83% (574/639) | [87.24%, 91.94%] | 74.13 | 1.84x |
| `4x_ceil_sqrt_N` | 22.047 | 98.75% (631/639) | [97.55%, 99.36%] | 130.51 | 3.25x |
| `ceil_N_over_4` | 8.08 | 78.25% (500/639) | [74.88%, 81.27%] | 53.42 | 1.33x |
| `ceil_N_over_2` | 15.679 | 94.05% (601/639) | [91.94%, 95.64%] | 97.69 | 2.43x |
| `N_all_scenes` | 30.829 | 100.00% (639/639) | [99.40%, 100.00%] | 170.95 | 4.25x |

The curve is steep and cheap. On val_tune, `2*ceil(sqrt(N))` buys
**+15.4 points** of recall for 1.82x the pool, and
`4*ceil(sqrt(N))` reaches **98.47%** -- within 1.4 points of the
all-scenes ceiling -- for 3.14x the pool (127 frames on
average, still a small pool). val_confirm reproduces this within noise. Note that
`ceil(N/4)` is *worse* than `2*ceil(sqrt(N))` at comparable width on short videos
and better on long ones; the sweep is reported as measured and no value is adopted.

## Step 5 -- where gold scenes actually rank

| Split | median | p90 | p99 | max | mean |
|---|---|---|---|---|---|
| val_tune | 3 | 13 | 34 | 74 | 5.288 |
| val_confirm | 3 | 12 | 30 | 48 | 5.194 |

`best_gold_rank` histogram, val_tune (n=2681):

```
rank   1 | ########################################  932  (cum  34.8%)
rank   2 | ################                          374  (cum  48.7%)
rank   3 | ###########                               266  (cum  58.6%)
rank   4 | ########                                  180  (cum  65.3%)
rank   5 | ######                                    150  (cum  70.9%)
rank   6 | #####                                     116  (cum  75.3%)
rank   7 | ####                                       86  (cum  78.5%)
rank   8 | ###                                        72  (cum  81.2%)
rank   9 | ###                                        68  (cum  83.7%)
rank  10 | ##                                         57  (cum  85.8%)
rank  11 | ##                                         47  (cum  87.6%)
rank  12 | ##                                         35  (cum  88.9%)
rank  13 | ##                                         39  (cum  90.3%)
rank  14 | #                                          28  (cum  91.4%)
rank  15 | #                                          22  (cum  92.2%)
rank  16 | #                                          24  (cum  93.1%)
rank  17 | #                                          32  (cum  94.3%)
rank  18 | #                                          23  (cum  95.2%)
rank  19 | #                                          15  (cum  95.7%)
rank  20 | #                                           9  (cum  96.0%)
rank  21 | #                                          17  (cum  96.7%)
rank  22 | #                                          10  (cum  97.1%)
rank  23 | #                                           6  (cum  97.3%)
rank  24 | #                                           8  (cum  97.6%)
rank  25 | #                                           4  (cum  97.7%)
rank  26 | #                                           5  (cum  97.9%)
rank  29 | #                                           7  (cum  98.4%)
rank  33 | #                                           5  (cum  99.0%)
rank  36 | #                                           5  (cum  99.3%)
```

Reading the distribution, as pre-committed in the task:

- **val_tune**: 707 misses. Overshoot past the cutoff (`best_gold_rank - shortlist_width`) has median **5**, p90 **16**, max 64. **385/707 (54%) miss by 5 ranks or fewer**, and 662/707 (94%) by 20 or fewer.
- **val_confirm**: 171 misses. Overshoot past the cutoff (`best_gold_rank - shortlist_width`) has median **4**, p90 **16**, max 40. **98/171 (57%) miss by 5 ranks or fewer**, and 161/171 (94%) by 20 or fewer.

**Misses sit just past the cutoff, not scattered deep.** That is the first of the
two readings the task pre-specified: the centroid ranking is basically sound and
**widening the shortlist fixes it**. The mean-CLIP centroid is a usable coarse
signal -- it puts a gold scene at rank 1 for 35% of val_tune questions and inside
the top 13 for 90% of them -- it is simply being cut off far too early. There is no
evidence here for replacing the centroid; there is strong evidence for widening.

### Fallback firing rates

| Split | SCENE-001 all-scenes | empty pool | either |
|---|---|---|---|
| val_tune | 0.1862% | 0.0% | 0.1862% |
| val_confirm | 0.1565% | 0.0% | 0.1565% |

## Cross-check against the two bounding numbers

The task asked for this to be stated plainly. It resolves better than expected,
because the c24f8f8 gap diagnostic left a per-question CSV that joins to this one
on `(video, qid)` over the identical 639 val_confirm questions at the identical
config-hash. Bucket (c) reproduces exactly from that join
(**146/228 = 64.04%** of the key group), so the join is sound.

| Quantity | Value |
|---|---|
| Bucket (c): retrieval never found a gold frame | 146 |
| ... of which also lost the gold scene at the shortlist | **86 (58.9%)** |
| ... of which had the gold scene shortlisted and still failed | 60 (41.1%) |
| Shortlist misses across all 639 questions | 171 |
| Shortlist miss but retrieval still found a gold frame | 3 |

Two facts follow, and they are the actionable core of this diagnostic:

1. **Losing the gold scene at the shortlist is very nearly sufficient for total
   retrieval failure.** Only 3 of 171 shortlist misses recovered a gold frame
   downstream. Once the scene is cut, the pipeline essentially cannot come back.
2. **The shortlist explains 59% of bucket (c), not all of it.** 60 of the 146
   bucket-(c) questions had the gold scene in the shortlist and still failed to
   retrieve a gold frame. So the loss is split: roughly three-fifths at the scene
   shortlist, two-fifths in the final top-k ranking within an adequate pool.

The three numbers are mutually consistent: L1 admission preserves the gold frame
99.85% of the time, the centroid shortlist then discards the gold scene ~26% of the
time, and what survives both still loses some fraction to frame-level ranking. The
99.85% ceiling and the 64% bucket-(c) rate bound this measurement, and it sits
inside those bounds.

## Step 7 -- pre-registered interpretation

Written before the number was known (drafted at the point where only the Step-0/1/2
checks had run):

had run and no recall figure existed.

| Effective recall | Reading | Consequence |
|---|---|---|
| **>= 95%** | The scene shortlist is not a major bottleneck. | The loss is downstream — final frame ranking within an adequate pool. Priority goes to the embedding adapter and window-level selection, not to wider scene search. |
| **85–95%** | Real but secondary loss. | Worth widening, but it cannot alone explain bucket (c) at 64%. Both fixes needed. |
| **70–85%** | **Major bottleneck found.** | IRIS is discarding the correct scene before frame ranking ever runs. Wider and parallel scene search becomes the highest-value change in the pipeline. |
| **< 70%** | Dominant bottleneck. | The centroid shortlist is the primary cause of retrieval failure. Redesign it before anything else. |

**Row 3 fired, on both splits independently:**
val_tune 73.59%, val_confirm 73.40%.

> **Major bottleneck found.** IRIS discards the correct scene before frame ranking
> ever runs, on about a quarter of all questions. Wider and parallel scene search
> becomes the highest-value change in the pipeline.

The qualification the cross-check adds: widening the scene search is the single
highest-value change, but it addresses roughly three-fifths of the retrieval
failure group, not all of it. The remaining two-fifths is final top-k ranking
inside a pool that already contains the gold scene, which is the embedding-adapter
and window-selection work that row 1 of the table points at. Both are needed; the
scene shortlist is the one to do first, and the Step-4 curve says it is cheap --
but choosing a width is a separate, explicitly-scoped tuning task, not this one.

## Artifacts

### Written by this run (all under `tuning/scene_shortlist_recall/`)

| File | SHA-256 |
|---|---|
| `tuning/scene_shortlist_recall/val_tune_per_question.csv` | `8f1fb26dcddda0472872921ca38c1ad6284203ede94303ff3900b5d47f21cb35` |
| `tuning/scene_shortlist_recall/val_tune_summary.json` | `26d87c9edb186767ae7c682038d8a71b4eb9bbcc789f00dc7ff81b0e2078d756` |
| `tuning/scene_shortlist_recall/val_confirm_per_question.csv` | `fbb43c9d2353588ed94761a88057cbed1e8cb6d11cffadcd27ac9ecb61a7cd9a` |
| `tuning/scene_shortlist_recall/val_confirm_summary.json` | `ea1826d84357c07dae90f56d8d205775c8286cfea1362fac1a90d34a0301f47a` |
| `tuning/scene_shortlist_recall/width_sweep.csv` | `ebfbe1885a701ef4950312d15f2557248378eccbab38c562b7e990ba826b75af` |
| `tuning/scene_shortlist_recall/artifact_manifest.json` | `d52594dbee2bbce82a5ed8a6cbecc4a40401f035cb1113675622953690ade61b` |
| `scripts/scene_shortlist_recall.py` | `973720326dee495e4a0426e4083bd27de98d2e6511a54ad664398f88ab03f34a` |

### Read by this run

All paths relative to `/home/ccbd/IRIS-1` at commit
`5628199adf9c771c58f52ae029b26c7913aae39d`.

| File | SHA-256 |
|---|---|
| `iris/scene_retrieval.py` | `1cd1361df16f2220560ae5f38e7672923200dcf7154cfabc003c4de549565921` |
| `scripts/part3_tune.py` | `dcdbc55920fc780277eccb15a21f4f6344dca7eada36f1daaefbde438caaeac6` |
| `scripts/val_confirm_e2e_eval.py` | `e2efa4c036a173a951a9747e95344eb0ec971b03e6664adc1430889135fbb14e` |
| `scripts/parta_survivor_ceiling.py` | `d3d5e709c2004efa7bc223b80f53b1c1ccb2a8b0b71863f27147219594c35400` |
| `eval/data/nextqa/val.csv` | `ee0ef210ae341bec53fdeb723ae54958307ed2e49988d2d3763d3c22abf4201a` |
| `eval/data/nextqa/gsub_val.json` | `527f402851836224aa03c9d4b0016b858a678d21596a2348eb2bdb774c74970a` |
| `eval/data/nextqa/gsub_test.json` | `0c16c31699238a0f2b8ace45aeed7f193149ce2f011d6ed4f1ef7170ef5d41e9` |
| `split_manifest.json` | `7864ba3692234320fc453573d6fa8be5e12779f222fd99a841c63a745e98f12a` |
| `tuning/frozen_state.json` | `612a93ba88af53eff17d766885dd3bcf8f65e502e4822b60c1a5c04db4c0b1b7` |
| `survivor_coverage_ceiling_report.md` | `69a4795101390c8040a7eb39e8587409b6c286fb05ae0467563993cfe7b8a3df` |
| `tuning/val_confirm_gap_diagnostic_report.md` | `bb3a2b0066a0f3768569b5294c19f68ff2e3bbec3d6d044d247eeee779943496` |
| `tuning/val_confirm_e2e_per_question_gap_diagnostic.csv` | `4c1c73c294dd6156ecdb405f77f46daf0cc1062c4f8feb322c2bc531fae8722f` |

Index caches are directories, so a per-file digest is impractical; recorded instead:

| Cache | Files | Config-hash | SHA-256 of sorted filename listing |
|---|---|---|---|
| `tuning/index_cache/` (450 val_tune indexes used; 10,800 files total across all hashes) | 10800 | `cab2bac1628012a3` | `e205d373109dd48e11187e958f339351ef049b4e08a5920549306181e335f97c` |
| `tuning/index_cache_val_confirm_e2e/` | 112 | `4edae64ed40256e3` | `59839f34b6b495523c9a6ed6575fc79d464eed3a6ea73c889c030c8592bbc5ba` |

### Prior artifacts this chains to

| Artifact | Commit | Figure used |
|---|---|---|
| `survivor_coverage_ceiling_report.md` | `2ad7ab961ed5ebe11450c846c29b8383d94e8c3e` | L1 ceiling 99.85% (2,681/2,685) |
| `tuning/val_confirm_gap_diagnostic_report.md` | `c24f8f830abaa44f2846341f9e9bf20c8934f045` | bucket (c) 146/228 = 64.04% |
| `tuning/val_confirm_e2e_per_question_gap_diagnostic.csv` | `c24f8f830abaa44f2846341f9e9bf20c8934f045` | per-question join for the cross-check |

### Reproduce

```
cd /home/ccbd/IRIS-1   # worker-1
env CUDA_VISIBLE_DEVICES='' python scripts/scene_shortlist_recall.py --splits val_tune,val_confirm
python scripts/scene_shortlist_recall.py --report
```
Runtime: ~205 s (val_confirm) + ~800 s (val_tune) on CPU. Deterministic.

# Antigravity Task — Experiment 1: IRIS on UCF-Crime Video Anomaly Detection

## Objective

Measure IRIS's frame-level anomaly-detection accuracy on UCF-Crime and its
ingest/query cost, and place both in a table against the published
training-free state of the art (EventVAD, LAVAD).

This is a **measurement task**. You are not tuning anything, not training
anything, and not trying to win. A negative result is a successful outcome
and must be reported as such.

---

## Non-negotiables (read before starting)

1. **Never fabricate a number.** Every figure in your report must come from a
   file you wrote during this run. If a step fails, report the failure, say
   what you tried, and stop that branch — do not estimate, do not
   extrapolate, do not fill in a plausible value.
2. **No tuning on the test videos.** UCF-Crime's 290 annotated test videos are
   evaluation-only. IRIS's config stays frozen at the values in
   `tuning/frozen_state.json`. If any new constant is unavoidable, pick it on
   *training* videos and say so explicitly.
3. **Do not re-run or re-implement EventVAD or LAVAD.** Their numbers are
   cited from the published paper. Label them as cited, not reproduced.
4. **Report the failure modes.** Videos that fail to decode, annotation rows
   that don't parse, frame-count mismatches — all get counted and listed, not
   silently dropped.
5. If you are blocked, write the blocker report and stop. Do not substitute a
   different dataset, a different split, or a proxy metric to produce output.

---

## Step 0 — Branch and existing assets

**Base this work on `siddanth/peak-source-a6-p1` (remote `origin` =
SiRex750/IRIS). Branch off it. Do not use `feat/prerun-fixes`, and do not
merge the two** — they have diverged 56/42 commits from merge-base `7b38c30`,
and `iris/ingest.py`, `iris/action_score.py`, `iris/l1_elysium.py`,
`iris/iris_config.py`, `iris/l2_asphodel.py` all differ materially between
them.

That branch already has, on the box:

- `eval/data/ucf/index_cache/` — UCF-Crime clips already ingested and cached:
  `Normal_Videos_289` (N=91), `Normal_Videos_881` (N=24), `Abuse025` (212),
  `Arrest016` (1,102), `Abuse042` (2,963), `Arrest047` (6,559), `Arson019`
  (13,506), where N = survivor frame count.
- `scripts/scaling_curve_v2.py` + `scripts/_scaling_curve_v2_worker.py` — the
  efficiency harness, with a uniform wall/RSS watchdog, per-clip subprocess
  isolation, and three-outcome tracking (`completed`/`oom`/`timed_out`). Reuse
  this for Step 5 rather than writing new timing code.
- `graph_edge_mode="block_diagonal"` — the O(N²)→O(Σnᵢ²) scene_sparse build.
  Opt-in; default is still `hierarchical_sparse`.

Those caches are coupled to that branch's ingest code by config-hash. Verify
the hash matches before reusing any cache; if it doesn't, re-ingest and say so.

**Free smoke test before any download:** check which of the cached clips appear
in `Temporal_Anomaly_Annotation_ForTestVideos.txt`. For any that do, run Stage
A on them immediately and report per-video AUC. This costs nothing, exercises
the whole path end to end, and tells you whether Step 3 is worth acquiring 290
videos for.

## Step 1 — Dataset acquisition and verification

### 1a. Check what is already on the box

Report the absolute path, video count, and total bytes of the UCF-Crime data
backing `eval/data/ucf/index_cache/`. Note that only ~7 clips are cached —
this experiment needs the **290 annotated test videos**, so most of the test
set is almost certainly absent. Establish exactly what is present before
requesting anything.

### 1b. CRITICAL — verify you have raw video, not extracted frames

**This experiment measures signals in the compressed bitstream (H.264/H.265
packet sizes, macroblock motion vectors, picture types). Extracted JPEG/PNG
frames destroy every one of those signals.** A run on image frames will still
produce an AUC number, and that number will be meaningless.

Several widely-mirrored "UCF-Crime" distributions are **image frames, not
video** — including at least one popular Kaggle mirror. Before proceeding:

- Confirm the files are `.mp4` (or the original container), not directories of
  `.jpg`/`.png`.
- Run `ffprobe -show_streams` on 5 random files and confirm a video stream with
  a real codec (`h264`/`hevc`), a frame rate, and a nonzero bitrate.
- Confirm packet-level data is readable: `ffprobe -show_packets` must return
  per-packet `size` and `flags` fields.

If any of these fail, **stop and report** — the experiment cannot run.

### 1c. If the dataset is absent

Do **not** start a blind download. Report:
- Free disk space on the box.
- The official source: CRCV UCF ("Real-world Anomaly Detection in Surveillance
  Videos"), distributed as a Dropbox tree of 16 subfolders — individual
  category folders are separately downloadable, so a subset is feasible.
- The exact byte count of the subset needed (the 290 test videos are what this
  experiment requires; the ~1,610 training videos are not needed for Step 3).

Then stop and wait for a go/no-go. Only proceed to download if free space
exceeds the required size by at least 2×.

### 1d. Annotations

You need `Temporal_Anomaly_Annotation_ForTestVideos.txt` (290 rows). Format is
`video_name  class  start1  end1  start2  end2`, with `-1` marking unused span
slots. Verify:
- Exactly 290 rows, all `video_name`s unique.
- 140 anomalous + 150 normal (normal videos carry all `-1` spans).
- Every frame index is within that video's actual decoded frame count from
  `ffprobe`. Report every mismatch — do not clamp silently.

Write `ucfcrime_dataset_validation.json` with all of the above.

---

## Step 2 — Evaluation protocol (fix this before computing anything)

- **Metric: frame-level ROC-AUC.** Ground truth is 1 inside an annotated
  anomaly window, 0 everywhere else. All frames of a normal video are 0.
- **Primary convention: pooled ("micro") AUC** — concatenate the frame scores
  of all 290 test videos into one vector and compute a single ROC-AUC. This is
  the Sultani et al. convention that LAVAD and EventVAD report, and it is the
  only number comparable to theirs.
- **Also report per-video mean AUC** (macro) as a secondary column. Normal
  videos have no positives, so AUC is undefined for them — exclude them from
  the macro average and say how many you excluded.
- **Every frame needs a score.** IRIS's L1 retains roughly 13% of frames. For
  frame-level AUC you must emit a score for *all* frames. Propagate each
  retained frame's score to the non-retained frames it covers (piecewise-
  constant hold to the next retained frame). Report the retention rate you
  actually observed.
- Report AUC computed **both** over all frames and over retained frames only,
  so the effect of propagation is visible.

---

## Step 3 — Stage A: codec-only anomaly score (the decisive cheap test)

Take IRIS's existing per-frame codec action score (`iris/action_score.py`,
weights frozen at `packet_size_weight=0.8`, `motion_weight=0.1`,
`luma_entropy_weight=0.1`) and use it **directly** as the anomaly score. No
graph, no PPR, no CLIP, no captioner, no LLM, no training.

Report:
- Pooled AUC and macro AUC, as defined in Step 2.
- Raw scores as the primary result. If you also report a smoothed variant, fix
  the smoothing window a priori at 1 second, apply it to every video
  identically, and label it separately. Do not sweep the window.
- Per-category AUC across the 13 anomaly classes (Explosion, Road Accident,
  Shooting, Shoplifting, …). Expect wide variance — burst-motion classes
  should behave very differently from theft classes, and that contrast is one
  of the most informative things this run can produce.

### Interpretation gates (state which one you landed in)

| Pooled AUC | Meaning |
|---|---|
| > 0.65 | Codec-native VAD is real. Stage B is justified. |
| 0.53 – 0.65 | Around zero-shot CLIP level (53.16%). Signal is weak alone; graph topology would have to carry it. |
| ~0.50 | The "anomaly = bitrate/motion peak" premise is dead. Report it plainly and stop. |

**If you land at ~0.50, that is a complete and valuable result. Write it up and
stop. Do not go looking for a configuration that produces a better number.**

---

## Step 4 — Stage B: graph-topology anomaly score (only if Stage A > 0.65)

Build IRIS's scene-sparse graph per video under the frozen config and derive a
second anomaly score from graph structure — e.g. PageRank drop-off, node
isolation, edge-weight discontinuity at scene boundaries. Pick **one**
formulation, define it in the report before you run it, and run it once.

Report pooled AUC for Stage B alone, and for Stage A + Stage B combined with a
fixed 50/50 weight. Do not sweep the fusion weight on test videos.

If Stage A ≤ 0.65, skip this step entirely and say so.

---

## Step 5 — Efficiency measurement

For a random sample of at least 30 test videos spanning the duration range,
measure and report:

- Ingest wall-time per video and per 1,000 frames.
- Peak RSS during ingest.
- Frames decoded vs frames retained (retention %).
- Device used (CPU or GPU) and whether a GPU was required at any point.
- **Verify and state explicitly that no neural network forward pass occurs
  during ingest.** Instrument this — don't assert it from reading the code.

Note in the report that VAD requires no per-query LLM call: the pipeline is
ingest + score, so unlike the GQA setting there is no 2.2s answerer stage
diluting the efficiency comparison.

### Cost comparison (published numbers, clearly labeled as cited)

EventVAD's ingest requires, per frame: CLIP ViT embeddings **plus RAFT optical
flow**, with VideoLLaMA2.1-7B as backbone, run on a single NVIDIA A800 80GB.
State IRIS's measured cost against that description. Do not fabricate a
wall-time for EventVAD — you are not running it.

---

## Step 6 — Comparison table

Report exactly this, with the citation status of every row marked:

| Method | Training-free | UCF-Crime pooled AUC | Ingest features | Hardware |
|---|---|---|---|---|
| ZS CLIP | yes | 53.16 (cited) | CLIP per frame | GPU |
| ZS ImageBind | yes | 55.78 (cited) | ImageBind per frame | GPU |
| LAVAD | yes | 78.33 (cited) | VLM captions + LLM scoring | GPU |
| EventVAD | yes | 82.03 (cited) | CLIP + RAFT optical flow, 7B VLM | A800 80GB |
| **IRIS Stage A** | yes | **(measured)** | codec packet size, no model | (measured) |
| **IRIS Stage B** | yes | **(measured or N/A)** | + scene-sparse graph | (measured) |

Add one line of context, not a comparison row: weakly-supervised methods reach
~89.8% AUC (MTFL) but are trained on video-level labels and are **not** in the
same category — do not put them in the table as a target.

---

## Step 7 — Report

Write `tuning/ucfcrime_vad_experiment1_report.md` containing:

1. Dataset provenance: source, path, video count, total bytes, the ffprobe
   codec verification result, and explicit confirmation that these are encoded
   videos and not extracted frames.
2. Every validation failure: undecodable videos, annotation mismatches, frame
   count disagreements — with counts and video names.
3. The exact evaluation protocol used (pooled vs macro, propagation rule,
   retention rate).
4. Stage A results + which interpretation gate you landed in.
5. Stage B results, or an explicit statement that it was skipped and why.
6. Efficiency measurements.
7. The comparison table.
8. **A "what I could not measure" section.** Anything blocked, skipped, or
   estimated goes here. If this section is empty, say so deliberately.

Also commit the raw per-frame scores and per-video AUCs as CSV so the numbers
can be independently recomputed.

Do not edit `tuning/frozen_state.json`. Do not touch the NExT-GQA splits or
`val_confirm` data. Do not modify or re-run anything under `eval_results/` from
the scaling-curve work. Work on a branch off `siddanth/peak-source-a6-p1` and
push there.

---

## Appendix — existing scaling numbers, for reference only

Do not re-derive or re-quote these; they are context so you don't duplicate
finished work. From `eval_results/scaling_curve_v2.md` on the base branch:

- Fitted exponents are **UCF-only**: flat k=2.086 (4 completed points, N≤2,963),
  scene_sparse k=0.663 (6 points, N=91→13,506).
- **The N=4,892 point is VIRAT, not UCF-Crime**, and is explicitly excluded
  from the fit as a cross-dataset corroborator. Flat 7.9916s vs scene_sparse
  0.006969s there.
- Flat **timed out at the 3600s cap** at N=6,559 and N=13,506 — no flat latency
  exists at those N. Peak RSS 17.0GB and 26.9GB, still climbing, never hitting
  the 29GB cap. **Wall time, not memory, is the binding constraint.**

If Step 5 produces any number that contradicts these, report the contradiction
rather than reconciling it.

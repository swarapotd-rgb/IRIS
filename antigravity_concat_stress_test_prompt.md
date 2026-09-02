# Antigravity Task — Concatenation Stress Test + Structural Shortlist Table

## Objective

Answer one question: **is `4*ceil(sqrt(N))` a real fix for the scene-shortlist
bottleneck, or an artifact of NExT-GQA's short videos?**

Commit `6039807` measured scene-shortlist recall at **73.59% (val_tune)** and
**73.40% (val_confirm)**, and showed `4*ceil(sqrt(N))` reaches **98.47%** for
3.1x the candidate pool. But NExT-GQA videos average only ~30.5 scenes, where
`ceil(sqrt(N))` keeps roughly a fifth of all scenes. On long video the same
rule keeps a far smaller fraction, because the kept fraction is `1/sqrt(N)`
and therefore shrinks monotonically as video gets longer.

So the measured fix may not survive at the video lengths this project is
actually targeting. This task tests that directly, by holding everything
constant except scene count.

This is a **measurement task**. You are not tuning, not changing production
behaviour, and not selecting a new width rule. A result showing the fix does
NOT generalise is a successful outcome and must be reported plainly.

---

## Non-negotiables (read before starting)

1. **Never fabricate a number.** Every figure must come from a file you wrote
   during this run. If a step fails, report the failure, say what you tried,
   and stop that branch. Do not estimate, do not extrapolate, do not fill in
   a plausible value.
2. **Run the real pipeline. No shortcuts.** Concatenated videos must be
   produced as actual video files and ingested through
   `iris.ingest.ingest()`. **Merging cached indexes by offsetting `scene_id`
   and `frame_idx` is explicitly forbidden** — it would fake the scene
   structure this experiment exists to measure. If you find yourself editing
   an `.npz` instead of encoding a video, stop.
3. **Reuse the verified measurement code.** Recall must be computed by
   `scripts/scene_shortlist_recall.py` (commit `6039807`), whose shortlist
   reconstruction was verified 20/20 against `retrieve_scene_sparse`. Do not
   reimplement the shortlist logic. If you must extend the script, keep the
   existing code path intact and re-run its verification.
4. **Do not tune, and do not write anything back.** No change to
   `tuning/frozen_state.json`, `iris/*.py`, or any config. The width sweep is
   a diagnostic curve, not a search for a value to adopt.
5. **Report the failure modes.** Videos that fail to concatenate, ingests that
   error, questions whose gold span fails to remap — counted and listed by
   name, never silently dropped.
6. **If you are blocked, write the blocker report and stop.** Do not
   substitute a different split, a synthetic index, or a proxy metric to
   produce output.

---

## Step 0 — Box, branch, preconditions

Work on branch **`feat/prerun-fixes`**. Do not create a new branch.
Run on **`worker-1`** (`/home/ccbd/IRIS-1`), the box holding the caches and
the real annotations.

Verify and report before anything else:

| Check | Requirement |
|---|---|
| Hostname, `uname -a`, repo path, HEAD sha | record |
| `gsub_val.json` / `gsub_test.json` **not** byte-identical | else **STOP**, wrong box |
| `scripts/scene_shortlist_recall.py` present at `6039807` | record its SHA-256 |
| Source `.mp4` files for val_tune videos present locally | count; record how many of the 450 are available |
| `ffmpeg` available | record version |
| Disk headroom for concatenated videos | estimate and report before writing |

If fewer than 120 source videos are present locally, **stop and report** — the
sampling design below needs a reasonable pool.

---

## PART 1 — Structural table (no queries needed, do this first)

This part needs no annotations at all and should take under an hour.

For **every cached index available on the box** — NExT-GQA val_tune,
val_confirm, and every UCF-Crime and VIRAT index cache you can find — read the
stored scene structure and record per video:

- `video_id`, `corpus`, `n_survivors`, `n_scenes` (distinct non-negative
  `FrameRecord.scene_id`)
- `shortlist_width = max(4, ceil(sqrt(n_scenes)))`
- `fraction_kept = shortlist_width / n_scenes`

**Read the real scene counts from the caches. Do not carry over any scene
count quoted in a prior document** — a previously circulated figure of "528
scenes" came from a VIRAT artifact and was wrongly applied to NExT-GQA.
Everything in this table must be recomputed from disk.

Output `tuning/concat_stress/structural_table.csv` plus a summary showing
`fraction_kept` against `n_scenes`, bucketed by corpus. State plainly whether
`fraction_kept` falls as `n_scenes` grows, and by how much between the
smallest and largest indexes you have.

---

## PART 2 — Concatenation stress test

### Step 2.1 — Encode control

Concatenation must not confound scene count with encoding. Therefore:

- Attempt concatenation with the ffmpeg **concat demuxer** using stream copy
  (`-c copy`). If the inputs' codec parameters differ and stream copy fails,
  re-encode with **one fixed setting used identically for every arm**.
- **Build a `k=1` arm through the same encode path**, i.e. a single video
  passed through the identical ffmpeg invocation. This isolates the encode
  effect from the concatenation effect.
- Record every ffmpeg command line verbatim in the report, and state which
  path was taken (stream copy vs re-encode).

### Step 2.2 — Group sampling

Pool: val_tune videos present locally as `.mp4`.

For each `k` in **{1, 2, 4, 8, 16}**:

- Sample groups of `k` videos from the pool, seeded (`seed=20260817`), with
  the group ordering randomised so a host video appears at varied positions.
- Build enough groups per `k` to reach **at least 400 measured questions**,
  and report the actual n per `k`.
- Every question belonging to any constituent video of a group is measured
  against that group's concatenated video. Record `host_position` (which slot
  the question's source video occupied, 1-indexed) for every question.

### Step 2.3 — Gold-span remapping

For each question, the gold span shifts by the cumulative duration of all
segments preceding its source video in the concatenation.

Compute the offset from the **actual decoded duration** of each preceding
segment as ffprobe/PyAV reports it after concatenation, **not** from the sum
of nominal durations — container duration and decoded frame count routinely
disagree, and that disagreement is exactly what would silently corrupt this
measurement. Record both and report any video where they differ by more than
one frame.

### Step 2.4 — Ingest and measure

Ingest every concatenated video through `iris.ingest.ingest()` under the same
config the original caches used. Record per concatenated video: ingest wall
time, survivor count, scene count, retention percentage. These are evidence
the ingest actually ran; a missing or implausible value invalidates the arm.

Then run the recall measurement at each `k`, with the same width sweep as
`6039807`:

`ceil(sqrt(N))`, `2*ceil(sqrt(N))`, `4*ceil(sqrt(N))`, `ceil(N/4)`,
`ceil(N/2)`, `N` (all scenes)

and additionally, at each `k`, record **the smallest width that reaches 98%
recall**, expressed three ways: as an absolute width, as a multiple of
`sqrt(N)`, and as a fraction of `N`. Those three columns are the core result.

---

## Step 3 — Two hard gates

Both must pass before any result is interpreted. If either fails, **stop and
report the failure** — do not proceed to Step 4.

**Gate A — k=1 reproduction.** At `k=1`, measured on the original cached
indexes (not the re-encoded arm), recall at production width must reproduce
**73.59% ± sampling noise** on the same questions. Report the reproduced
figure and the question overlap. If it does not reproduce, the harness is
wrong, not the pipeline.

**Gate B — full-width invariance.** At every `k`, recall at `N` (all scenes)
must remain at the L1 ceiling, ~99.85%. Concatenation does not change which
frames L1 admits within a segment, so full-width recall must be flat in `k`.
**A drop in full-width recall as `k` grows means the gold-span remapping is
broken** — almost certainly a timestamp or fps error in Step 2.3 — and the
whole experiment is void until it is fixed.

Report both gates numerically, with the k=1 re-encoded arm shown separately so
the encode effect is visible.

---

## Step 4 — The question this answers

At each `k`, you now have the width needed for 98% recall as a multiple of
`sqrt(N)` and as a fraction of `N`. Read which one is stable:

- **If the required multiple of `sqrt(N)` is roughly constant across k** — the
  `4*sqrt(N)` fix is real and scale-invariant, and the current rule just needs
  a bigger constant.
- **If the required multiple grows with k, but the required fraction of `N` is
  roughly constant** — the fix is an artifact of short video. The correct rule
  is a fraction of `N`, not a multiple of `sqrt(N)`, and that has a direct and
  severe cost consequence: pool size then grows linearly in `N` instead of as
  `sqrt(N)`, which is the property the scaling contribution depends on.
- **If neither is stable** — report the observed relationship and fit nothing
  beyond what the data supports. Say so plainly rather than choosing a form.

Also report recall against `host_position` to confirm no positional bias
(a gold segment early in the concatenation must not be systematically easier
or harder than one late in it). If positional bias exists, it confounds the
result and must be stated.

---

## Step 5 — Outputs

Commit to `feat/prerun-fixes`:

- `scripts/concat_stress_test.py` — builder, ingester, and driver
- `tuning/concat_stress/structural_table.csv` — Part 1
- `tuning/concat_stress/k{K}_per_question.csv` — one per k
- `tuning/concat_stress/width_sweep_by_k.csv` — the sweep at every k
- `tuning/concat_stress/summary.json` — gates, headline curves, the three
  width columns, positional-bias check
- `tuning/concat_stress/ingest_log.csv` — per concatenated video: wall time,
  survivors, scenes, retention
- `tuning/concat_stress_report.md` — the report
- `tuning/concat_stress/artifact_manifest.json` — SHA-256 for every artifact
  read and written, plus the ffmpeg command lines

Do **not** commit the concatenated video files. Record their paths, sizes and
hashes in the manifest instead.

End the report with:

```
CONCAT_STRESS: 98%-recall width at k=1/2/4/8/16 = <...> x sqrt(N)
                                                = <...> fraction of N
GATE_A (k=1 reproduction): PASS|FAIL  <figure>
GATE_B (full-width invariance): PASS|FAIL  <figures by k>
VERDICT: SCALE_INVARIANT | SHORT_VIDEO_ARTIFACT | INCONCLUSIVE
```

---

## Step 6 — Pre-registered interpretation

Write this into the report **before** looking at the k>1 results, and then
state which row fired. Do not add a fourth reading afterwards.

| Observation | Verdict | Consequence |
|---|---|---|
| Required `sqrt(N)` multiple stable across k (within ~25%) | **SCALE_INVARIANT** | `4*sqrt(N)` is a genuine fix. Proceed to implement wider/parallel scene search, and validate externally on Ego4D NLQ. |
| Required multiple grows, required fraction of N stable | **SHORT_VIDEO_ARTIFACT** | The fix does not generalise. Pool cost becomes linear in N, which directly threatens the scaling claim. A recall-safe shortlist needs a different design, not a bigger constant. |
| Neither stable, or gates fail | **INCONCLUSIVE** | Report what was observed. Do not adopt any rule. |

---

## Guards — stop and report instead of proceeding if

- Gate A fails → the harness is wrong; fix before interpreting anything
- Gate B fails at any k → gold-span remapping is broken; the experiment is void
- Stream copy fails and re-encode settings cannot be held identical across arms
  → the encode is confounded with k; stop
- Any arm reaches fewer than 400 measured questions → report the shortfall
  rather than pooling arms to hide it
- More than 2% of questions fail gold-span remapping → stop, investigate
- Any step would require modifying production code or a cached index → stop

---

## Scope note

This is a **synthetic stress test**. Concatenated NExT-GQA videos are not a
benchmark and no number from this task may be reported as a benchmark result.
Its only job is to isolate scene count from every other variable, which no
real corpus can do. External validity comes later, from Ego4D NLQ on genuine
long video — this task decides whether that is worth doing and what to look
for when it is.

---

## What "done" looks like

The structural table showing how `fraction_kept` behaves with scene count; a
width-versus-k curve with both gates passing; the three width columns at every
k; a stated verdict from the pre-registered table; and every figure traceable
to a committed file. Nothing tuned, nothing in production modified, and the
concatenated videos genuinely built and genuinely ingested.

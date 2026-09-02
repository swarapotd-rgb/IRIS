# Antigravity Task — UCA Corpus Onboarding + Scene-Shortlist Recall on Long CCTV

## Objective

Stand up the **UCA (UCF-Crime Annotation)** corpus from zero on this box, then
re-measure **scene-shortlist recall** on it — this time on real long-form CCTV
with real natural-language queries, binned by video length.

NExT-GQA is retired as a benchmark for this project. Its videos average ~30
scenes, which cannot exercise the regime IRIS targets. What carries over are
the *findings*, which are properties of the pipeline and not of that corpus:

- L1 survivor-coverage ceiling **99.85%** (commit `2ad7ab9`)
- Scene-shortlist recall **73.59% / 73.40%** on two splits (commit `6039807`)
- Of bucket (c), **59%** is shortlist loss and **41%** is downstream ranking

The question now is whether that ~73% holds, improves, or collapses as scene
count grows on a real corpus. UCA spans roughly 190 to ~100,000 survivors
*within one dataset*, which is exactly the range needed.

This is a **measurement and infrastructure task**. Nothing is tuned. A result
showing recall is worse on long video is a successful outcome.

---

## Non-negotiables

1. **Never fabricate a number.** Every figure must come from a file written
   during this run. If a step fails, report the failure and stop that branch.
   Do not estimate, extrapolate, or fill in a plausible value.
2. **Do not modify the measurement core.** `scripts/scene_shortlist_recall.py`
   (commit `6039807`) has a shortlist reconstruction verified 20/20 against
   `retrieve_scene_sparse`. You may add a **loader** for UCA annotations. You
   may **not** alter the shortlist or gold-scene logic. Re-run the 20/20
   verification on UCA and report it.
3. **Do not tune.** No change to `tuning/frozen_state.json` or any config
   value. Ingest under the existing frozen block, unmodified.
4. **Report failure modes.** Videos that fail to download, decode, or join;
   annotations falling outside the decoded duration; duplicate spans — all
   counted and listed by name, never silently dropped or clamped.
5. **Stop at the pilot gate.** Do not ingest the full subset until the pilot
   in Step 5 passes end to end.
6. **If blocked, write the blocker report and stop.** Do not substitute a
   different corpus or a proxy metric to produce output.

---

## Step 0 — Box, branch, preconditions

Branch **`feat/prerun-fixes`**. Do not create a new branch.

Record and report:

| Check | Requirement |
|---|---|
| hostname, `uname -a`, repo path, HEAD sha | record |
| **`nvidia-smi` full output** | record — this has never been captured in any artifact and the cost plan depends on it |
| `python -c "import torch; print(torch.__version__, torch.cuda.is_available())"` | record |
| `df -h` on the work volume | record free space |
| `scripts/scene_shortlist_recall.py` present at `6039807` | record SHA-256 |
| `tuning/frozen_state.json` frozen block | record verbatim; this is the ingest config |
| ffmpeg / PyAV available | record versions |

**STOP if free space is under 90 GB.** Budget, computed from the archive's
global rate of ~0.75 GiB per hour of video: the 189-video / 80.7-hour subset is
**~60 GiB** of video plus **~5 GiB** of index caches (~915k survivors at 512-dim
fp32, plus metadata and block-diagonal edges). Selective extraction via Range
means the 95.9 GiB archive is never stored, so ~66 GiB total is the real figure.

These are estimates from a global bitrate. **Replace them with facts before
downloading anything**: `remotezip -l` returns exact per-member sizes without
transferring the files, so run it at the start of Step 4, sum the 189 targets,
and report the exact total. If that exact figure plus 10 GiB exceeds free
space, drop to the stratified fallback in Step 3 rather than stopping.

---

## Step 1 — Annotations (small, free, no gate)

UCA is Apache-2.0, academic use, annotations public. Fetch the three splits
from the `UCF Annotation/txt/` directory of
`github.com/Xuange923/Surveillance-Video-Understanding`:
`UCFCrime_Train.txt`, `UCFCrime_Val.txt`, `UCFCrime_Test.txt`.

Also fetch the `json/` equivalents and the `txt_mask/` gender-neutral variants
for the record. Use the standard `txt/` files as primary; note in the report
that the mask variant exists and was not used.

Record SHA-256 for every file fetched.

Line format is `VideoName StartTime EndTime ##description`.

### The parsing landmine — handle this before anything else

**Timestamps appear in two formats: `MM:SS.S` and `HH:MM:SS.S`.** In the Train
split alone, **2,275 lines** use the `HH:` form, and those are precisely the
long videos. A parser assuming `MM:SS` silently drops them and biases every
downstream statistic toward short video.

Write the parser to handle both, then prove it: **the total parsed span count
across all three splits must be exactly 23,542.** If it is not, the parser is
wrong. Report the number you get.

---

## Step 2 — Verify the split before using it

Reproduce these independently. Report any disagreement rather than adopting
the numbers below:

| Split | Videos | Sentences |
|---|---|---|
| Train | 1,165 | 15,677 |
| Val | 379 | 3,534 |
| Test | 310 | 4,331 |
| **Total** | **1,854** | **23,542** |

Also verify and report:

- **Zero video overlap between the three splits** — the split is video-level.
  If any video appears in two splits, **STOP**, the protocol is unsound.
- Span duration statistics per split. Expect median ~11–12 s, mean ~17 s, p90
  ~31–35 s. Report what you actually measure.
- Count of near-duplicate `(video, start, end)` tuples carrying different
  descriptions. These exist in the corpus. **Report the count; do not
  deduplicate.**

**Declare the protocol now, in writing, before any measurement:** Val is the
tuning split, Test is the report-once split, Train is unused by this
diagnostic. Commit that declaration before Step 6 runs.

---

## Step 3 — Target video subset

Use `tuning/uca/uca_long_videos.csv`, already in the repo: **189 videos with at
least 300 s of annotation coverage, 80.7 hours total**, split Train 107 / Val
33 / Test 49, carrying per-video minimum duration, sentence count and
estimated survivor count.

Rationale, stated so it is auditable: the median UCA video is only 60–80 s
(~190–250 survivors), the same short regime NExT-GQA occupied. The scaling
question lives entirely in the tail, and this subset is that tail.

Report the subset coverage — how many sentences fall on these 189 videos, per
split.

### Duration structure of the subset

Estimated from the archive's global bitrate; replace with exact sizes from
`remotezip -l` in Step 4.

| bin (s) | videos | hours | est GiB | sentences | est survivors/video |
|---|---:|---:|---:|---:|---:|
| 300–600 | 86 | 9.9 | 7.4 | 1,686 | ~1,253 |
| 600–1200 | 48 | 10.9 | 8.2 | 2,219 | ~2,504 |
| 1200–1800 | 15 | 6.2 | 4.6 | 905 | ~4,496 |
| 1800–3600 | 28 | 20.8 | 15.6 | 3,622 | ~8,288 |
| ≥3600 | 12 | 33.0 | 24.7 | 4,492 | **~19,528** |

Use these as the starting bins for Step 7. They span more than an order of
magnitude in survivor count, which is what the recall-versus-N curve needs.

### Stratified fallback, if exact sizes do not fit

**115 videos, 70.0 hours, ~52.5 GiB estimated.** Construction: keep **every**
video at or above 1200 s (all 55 of them), then sample at most 30 per shorter
bin, seed 20260817. Covers 10,846 sentences; split balance Train 66 / Val 21 /
Test 28.

**The cutting rule, and it is not negotiable: cut from the bottom, never the
top.** The 12 videos at or above 3600 s are 41% of the bytes but they are the
only access to N ≈ 19,500 survivors — past the largest point ever measured on
this project (13,506). Dropping them to save disk removes the entire reason for
running this. The 300–600 s bin has 86 videos delivering ~1,253 survivors each,
which is close to the regime NExT-GQA already covered; that is where redundancy
lives and where any cut belongs.

If you take the fallback, say so explicitly in the report and record which
videos were dropped.

---

## Step 4 — Acquire video without blowing the disk

Source, verified by HEAD request:

```
https://www.crcv.ucf.edu/data1/chenchen/UCF_Crimes.zip
Content-Length: 102,957,372,377 bytes  (95.9 GiB)
```

Two verified facts to work from:

- The commonly-cited `Anomaly-Videos-Part-N.zip` split archives are **not** at
  that path — all four return **404**. Do not spend time on them.
- The server **supports HTTP Range**: a `Range: bytes=0-1023` request returns
  **206 Partial Content**.

Because Range works, **extract members selectively instead of downloading the
whole archive**. `pip install remotezip`, then list the archive remotely and
pull only the 189 target members. Verify the listing works before planning
around it — it requires the central directory to be readable from the tail of
the file. If it fails, report that and fall back to a resumable full download
(`curl -C -`), but only after confirming the disk can hold it.

Map names as `Abuse001_x264` → `Abuse001_x264.mp4`. The archive's internal
directory layout may differ from that flat naming; report the actual layout
you find.

Record for every downloaded file: path, byte size, SHA-256, into a manifest.
**Do not commit video files.**

---

## Step 5 — PILOT GATE (do not skip)

Before ingesting 80 hours, run the whole pipeline end to end on **15 videos**
spanning the length range — roughly 5 short (300–600 s), 5 medium (600–1800 s),
5 long (>1800 s), drawn across all three splits.

Verify and report:

1. Every video downloads and opens via `av.open`, with codec and resolution
   recorded per file.
2. **Every annotation end timestamp falls inside the decoded duration.** Report
   violations by name with the discrepancy in seconds. Do not clamp silently —
   the UCF-Crime VAD run found 3 genuine off-by-one boundary cases and reported
   them; do the same here.
3. Ingest succeeds under the frozen config with **`graph_mode="scene_sparse"`**.
   This is required: `retrieve_scene_sparse` raises if `_scene_centroids` is
   unpopulated, so an index built any other way cannot be measured at all.
4. Per video, record: ingest wall time, raw frame count, survivors, retention
   %, scene count, peak RSS, and the resulting config-hash.
5. The **20/20 shortlist reconstruction verification** passes on UCA.
6. `scene_shortlist_recall.py` produces a recall number on the pilot.

**STOP and report if any of these fail.** A broken join or a wrong graph mode
discovered after 80 hours of ingest is exactly the expensive failure this gate
exists to prevent.

From the pilot timings, **project the full-subset cost** — wall time and disk —
and state it before proceeding. CLIP embedding of survivors is the dominant
cost and the step that needs the GPU; the subset is on the order of 900k
survivor frames.

---

## Step 6 — Full subset ingest and measurement

Ingest all 189 videos under the identical frozen config and
`graph_mode="scene_sparse"`, logging the same per-video fields as the pilot.

Then run `scene_shortlist_recall.py` with the UCA loader. Report, per split and
overall:

- `hit_at_shortlist` — the headline
- `effective_hit` — including the SCENE-001 `max sim < 0.20` fallback
- **How often each fallback fires.** On NExT-GQA it fired on 0.07% of
  questions, i.e. it is effectively dead code. Check whether that holds here.
- `best_gold_rank` distribution: median, p90, p99, max
- `n_gold_scenes` per query — expect more than NExT-GQA's 3–5, since UCA spans
  are roughly twice as long
- Width sweep: `ceil(sqrt(N))`, `2x`, `4x`, `ceil(N/4)`, `ceil(N/2)`, `N`, with
  mean candidate-pool size at each

---

## Step 7 — The output that matters: recall versus N

Bin every measured query by its video's **scene count**, and report recall at
production width and at each swept width per bin. Suggested bins, adjusted to
what the data supports:

`<20, 20–40, 40–80, 80–160, 160–320, 320–640, >640` scenes

Per bin report: n queries, n videos, mean scene count, recall at production
width, and the **smallest width reaching 98% recall expressed three ways** —
absolute, as a multiple of `sqrt(N)`, and as a fraction of `N`.

Which of the three is stable across bins is the entire result:

- **Multiple of `sqrt(N)` stable** → the rule needs a bigger constant; pool cost
  stays `O(sqrt(N))` and the scaling contribution survives.
- **Fraction of `N` stable** → pool cost becomes linear in `N`, which directly
  threatens the scaling claim. A recall-safe shortlist then needs a different
  design, not a bigger constant.

Cluster confidence intervals **by video**, not by query — queries on the same
video share a scene structure and are not independent. Report the number of
videos behind every interval.

---

## Step 8 — Outputs

Commit to `feat/prerun-fixes`:

- `scripts/uca_acquire.py`, `scripts/uca_verify.py`, and the UCA loader
- `tuning/uca/annotations/` — the fetched annotation files
- `tuning/uca/split_verification.json` — Step 2
- `tuning/uca/download_manifest.json` — paths, sizes, SHA-256 (no video files)
- `tuning/uca/pilot_report.md` — Step 5, including the projected full cost
- `tuning/uca/ingest_log.csv` — per video, all fields from Step 5.4
- `tuning/uca/shortlist_recall_{val,test}_per_question.csv`
- `tuning/uca/shortlist_recall_summary.json`
- `tuning/uca/recall_by_scene_count.csv` — Step 7
- `tuning/uca_shortlist_recall_report.md` — the report
- `tuning/uca/artifact_manifest.json` — SHA-256 for everything read and written

End the report with:

```
UCA_SPLIT_VERIFIED: train 1165/15677  val 379/3534  test 310/4331  overlap 0
UCA_SHORTLIST_RECALL: <rate> (<n_hit>/<n_total>) on <split> @ <config-hash>
RECALL_BY_N: 98%-width = <...> x sqrt(N) | <...> fraction of N, by scene bin
VERDICT: SQRT_STABLE | FRACTION_STABLE | INCONCLUSIVE
```

---

## Step 9 — Pre-registered interpretation

Write this into the report **before** the recall numbers are known, then state
which row fired.

| Observation | Reading |
|---|---|
| Recall ≈ 73%, flat across scene bins | The bottleneck is scale-invariant and the NExT-GQA finding generalises. Widening is the fix and the constant transfers. |
| Recall falls as scene count grows | The `1/sqrt(N)` shrinkage is biting as predicted. Widening helps, but the rule's functional form is wrong. |
| Recall notably higher than 73% | The NExT-GQA figure was corpus-specific. Re-rank scene search against the adapter before building anything. |
| Recall notably lower than 73% | Surveillance is harder for CLIP than NExT-GQA, consistent with the UCA paper's own finding that mainstream models perform poorly on surveillance video. Report the domain gap explicitly. |

Note in advance: UCA spans are roughly twice as long as NExT-GQA's, so each
query has **more** gold scenes and recall should be **easier**, all else equal.
If it still lands near 73%, that is a worse result than the raw number
suggests, and the report must say so.

---

## Guards — stop and report instead of proceeding

- Parsed span total is not exactly 23,542 → parser is wrong
- Any video appears in more than one split → protocol unsound
- 20/20 reconstruction verification fails on UCA → measurement invalid
- Pilot gate fails any of its six checks → fix before scaling
- More than 2% of annotations fall outside decoded duration → investigate the
  join, do not clamp
- Ingest produces indexes without `_scene_centroids` → wrong graph mode
- Free space drops below 30 GB at any point → stop and report

---

## Scope note

This run establishes the corpus and re-measures one number on it. It does not
implement wider or parallel scene search, does not train anything, and does not
adopt a new width rule. Its output decides whether the shortlist redesign is
worth building, and what functional form it needs.

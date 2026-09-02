# Ego4D Dataset Setup & Split Policy

Status: **PLAN ONLY -- nothing downloaded yet.** No Ego4D bytes exist on this
box at the time of writing. Every count in this document marked `VERIFY` must
be replaced with a number read out of the downloaded manifest before it is
cited anywhere, especially in the paper.

## 0. Credential handling (read first)

The Ego4D approval email delivers a long-lived AWS access key pair. Rules:

- The key pair is **never** committed, never written into any file in this
  repo, and never pasted into a prompt, log, or issue.
- Install it only via `aws configure --profile ego4d`, which writes to
  `%USERPROFILE%\.aws\credentials` (outside the repo).
- The approval email states access is valid until **2026-09-03**. That is
  *tomorrow* relative to the current date (2026-09-02). Confirm with
  `support@ego4d.dev` whether that is the credential expiry or the licence
  term before planning a multi-day download.
- The Ego4D licence forbids redistributing video. Nothing under
  `external_data/ego4d/v2/clips/` may ever be committed, or copied to a
  shared GPU box, without re-reading the licence terms.

## 1. Why Ego4D, and which benchmark

Ego4D is not one dataset; it is a video corpus with roughly eight annotation
benchmarks layered on top. Downloading "Ego4D" wholesale is a multi-terabyte
mistake. Pick the benchmark whose task matches IRIS.

| Ego4D benchmark | Task | Fit for IRIS |
|---|---|---|
| **NLQ** (Natural Language Queries) | text query -> temporal window in a ~8-10 min clip | **Primary.** Same shape as NExT-GQA grounding and QVHighlights. `l2_asphodel` retrieval plus span prediction map directly onto it. |
| MQ (Moments Queries) | fixed action category -> temporal windows | Secondary. No natural language, so `aria` is bypassed; useful only as a motion-retrieval ablation. |
| VQ (Visual Queries) | image prompt -> spatiotemporal response | Out of scope; query is not text. |
| FHO / AV / Social | hands-and-objects, speaker ID, social attention | Out of scope. |

**Decision: target NLQ.** It is the only Ego4D benchmark that exercises the
full `charon_v -> l1_elysium -> l2_asphodel -> aria -> cerberus_v` path with a
language query and a temporal ground-truth span, i.e. the only one that
produces a number comparable to the NExT-GQA grounding results already in
`EXPERIMENT_LOG.md`.

Secondary reason Ego4D is worth the cost for IRIS specifically: egocentric
video has continuous head motion, so codec residual energy behaves very
differently than in the third-person, mostly-static NExT-QA clips. Clips are
also ~8-10 min against NExT-QA's seconds, so there is far more inter-frame
structure for the packet-size curve to work with. This is
either the strongest available stress test of the codec-oracle novelty claim
or the place it breaks. Either outcome is a paper contribution; a null result
here must be reported, not buried.

## 2. The official splits (do not invent your own)

Ego4D NLQ ships three annotation files:

| File | Split | Annotations | Usable for |
|---|---|---|---|
| `nlq_train.json` | train | full (queries + gold spans) | **fitting the trained component** (see 2.3) |
| `nlq_val.json` | val | full (queries + gold spans) | model selection + the one held-out check |
| `nlq_test_unannotated.json` | test | queries only, **no gold spans** | EvalAI leaderboard submission only |

Consequences, stated bluntly:

1. **You cannot compute a test-set number locally.** There is no gold span in
   the test file. Any local "test accuracy" you produce is a bug. This is the
   exact failure mode recorded in the NExT-GQA staging landmine; the Ego4D
   file name (`_unannotated`) is the only guard against it, so never rename
   that file.
2. **Test evaluation requires an EvalAI submission** with a limited number of
   attempts. Budget it as a one-shot, end-of-project event, not an iteration
   loop.
3. **`nlq_train.json` is load-bearing.** As of 2026-09-02 IRIS is no longer
   training-free (user decision); a trained component is in scope. Train is
   therefore the fitting split, not an optional extra, and its clips must be
   budgeted and downloaded alongside val. Note that the original rationale
   given for this change -- "test has no gold, so we must train" -- does not
   itself follow, since a training-free method submits to EvalAI identically.
   The defensible rationale is that zero-shot NLQ sits near the floor and every
   leaderboard entry trains a grounding head.

Published NLQ v1 scale (Ego4D CVPR 2022 paper) -- v2 is larger, so these are a
lower bound and still `VERIFY` against the downloaded manifest:

| Split | Queries | Video hours |
|---|---|---|
| train | 11.3k | 136 |
| val | 3.9k | 45 |
| test | 4.0k | 46 |

Clip length: **~8.2 min average, 20 min maximum** (the official docs quote a
10-minute average for NLQ). Response windows average ~9-10 s, i.e. a ~10 s
needle in a ~10 min haystack -- a far harder retrieval problem than NExT-QA,
and the reason this benchmark is worth the storage.

`scripts/setup_ego4d_nlq.py --summarize` prints the true counts.

## 3. The split IRIS actually needs: val_tune / val_confirm

Because test is unannotated, **every locally measurable number comes from
`nlq_val.json`.** With a trained component in scope the three-way role split
is:

| Split | Role |
|---|---|
| `nlq_train.json` | fit the trained component (gradients) |
| `val_tune` | model selection, early stopping, hyperparameters, ablations |
| `val_confirm` | one held-out look, everything frozen, before EvalAI |

Tuning and reporting on the same val set is the reproduction failure already
logged in commit `5f0793d` (blind ablation -- reproduction gate FAILED). With
training added the risk is strictly worse, because early stopping on `val_tune`
is itself a fitting signal. Do not repeat it.

Apply the same discipline as `split_manifest.json` (seed 20260721, 454/113
videos for NExT-GQA):

```
nlq_val.json
   |-- val_tune     ~80% of val video_uids  -> every threshold, alpha/beta,
   |                                           span method, prompt variant
   `-- val_confirm  ~20% of val video_uids  -> touched ONCE, at the end,
                                               with all knobs frozen
```

Hard rules, carried over from the Family-2 tuning state:

- **Split by `video_uid`, never by `clip_uid` and never by query.** Ego4D cuts
  multiple clips out of the same source video, and the same scene,
  kitchen, and camera-wearer recur across them. Splitting at clip or query
  level leaks the visual environment across the boundary and inflates confirm.
- **Seeded and committed.** The split is written to
  `external_data/ego4d/manifests/ego4d_nlq_val_split.json` with the seed, the
  sorted uid lists, and a sha256 of the source annotation file. It is
  committed. If the source hash changes, the split is invalid and must be
  regenerated.
- **`val_confirm` is opened once.** Every look at confirm is logged in
  `EXPERIMENT_LOG.md` with the frozen config hash. A second look after any
  further tuning invalidates the first.

`scripts/setup_ego4d_nlq.py --make-split` materialises this. It refuses to
overwrite an existing split file unless `--force` is passed, so an accidental
rerun cannot silently reshuffle a split you have already reported against.

## 4. Extraction: how the bytes actually get here

Ego4D is distributed over S3 and fetched with the official `ego4d` CLI, not
`git` or `wget`. The CLI reads an AWS profile, resolves a manifest, prints a
total byte estimate, and prompts for confirmation before transferring.

### 4.1 Install

```bash
pip install ego4d awscli
```

Then configure the profile yourself -- the key pair goes here and nowhere
else:

```bash
aws configure --profile ego4d
```

Verify the credential works without downloading anything:

```bash
aws s3 ls s3://ego4d-consortium-sharing/ --profile ego4d
```

### 4.2 Metadata and annotations only (small, do this first)

```bash
ego4d --output_directory external_data/ego4d --datasets annotations --benchmarks nlq --aws_profile_name ego4d
```

This lands `v2/annotations/nlq_train.json`, `nlq_val.json`, and
`nlq_test_unannotated.json`. **Stop here and run
`scripts/setup_ego4d_nlq.py --summarize` before downloading a single video.**
That gives real split counts, the set of required `clip_uid`s, and the exact
video budget -- the equivalent of the `HEAD`-request check that caught the
134 GiB QVHighlights archive.

### 4.3 Clips, not full-scale videos (this is the whole ballgame)

Ego4D offers two video products:

| Dataset flag | What it is | Size |
|---|---|---|
| `full_scale` | complete source videos, up to hours long | terabytes for the corpus |
| `clips` | the segments NLQ is annotated against (~8.2-10 min avg, 20 min max) | see 4.5 -- NOT a small fraction |

**NLQ annotations are defined on clips. Download `clips`, never
`full_scale`.** `full_scale` would exceed the 663 GB free on this box and is
not needed for any NLQ number. Note that clips are *not* uniformly cheaper per
hour: they are encoded at CRF 18 versus `full_scale`'s CRF 41, so the saving
comes from fewer hours (227 for NLQ v1 vs ~3,670 for the corpus), not from a
lower bitrate. See 4.5.

```bash
ego4d --output_directory external_data/ego4d --datasets clips --benchmarks nlq --aws_profile_name ego4d
```

The CLI prints the byte total and waits for confirmation. **Record that number
in `external_data/ego4d/logs/setup_output.txt` and compare it against free
disk before confirming.** Current headroom: 663 GB on `C:`. If the estimate
exceeds roughly 400 GB, do not confirm -- fall back to 4.4. Note that with training in scope this is train + val, not val alone.

### 4.4 Subset fallback, if the clip total is too large

The CLI accepts an explicit uid list. Restrict to the val split, which is all
that IRIS development needs:

```bash
python3 scripts/setup_ego4d_nlq.py --make-split
```

```bash
python3 scripts/setup_ego4d_nlq.py --emit-uids --split val --out external_data/ego4d/manifests/val_video_uids.txt
```

```bash
ego4d --output_directory external_data/ego4d --datasets clips --video_uid_file external_data/ego4d/manifests/val_video_uids.txt --aws_profile_name ego4d
```

If even that is too large, take a seeded video-level subsample of `val_tune`
for the pilot and keep all of `val_confirm`. Never subsample `val_confirm`
after looking at it.

### 4.5 How to get the exact storage number (no download)

There is no way to state the true byte total from outside; it must be read off
the distribution. Three zero-transfer ways to get it, in order of preference:

**(a) Byte-exact, from an S3 listing.** A `LIST` moves no video:

```bash
aws s3 ls --recursive s3://ego4d-consortium-sharing/public/v2/clips/ --profile ego4d > external_data/ego4d/manifests/clips_listing.txt
```

```bash
python3 scripts/setup_ego4d_nlq.py --storage-budget --s3-listing external_data/ego4d/manifests/clips_listing.txt
```

This intersects the listing with the `clip_uid`s actually referenced by
`nlq_train.json` and `nlq_val.json` and prints per-split byte totals plus the
train+val download total. Clips referenced by the annotations but absent from
the listing are reported, never silently skipped. Verify the bucket/prefix
against the Ego4D docs -- it has changed between versions.

**(b) The CLI's own estimate.** Run the real download command and answer `n`
at the confirmation prompt; it prints the total first:

```bash
ego4d --output_directory external_data/ego4d --datasets clips --benchmarks nlq --aws_profile_name ego4d
```

**(c) Estimate only, if you have no credentials yet.** Multiplies clip count
by a GB/hour anchor:

```bash
python3 scripts/setup_ego4d_nlq.py --storage-budget
```

The anchor (1.36 GB/hour) is derived from roughly 3,670 corpus hours at roughly
5 TB for `full_scale`. **It is now known to be biased low for clips and must be
treated as a floor, not a budget.** `full_scale` is VP9 at CRF 41; clips are VP9
at **CRF 18**, a far higher quality target and therefore a substantially higher
bitrate per hour. Applying a CRF-41-derived anchor to CRF-18 media understates
the total, possibly by several times.

Using the published NLQ v1 hours (136 train + 45 val = 181 h), the anchor gives
~246 GB as a **lower bound** on train+val. The true figure is higher by an
unknown CRF-18/CRF-41 bitrate ratio, and v2 has more data than v1. With 663 GB
free, this no longer comfortably fits -- **measure before downloading.**
**Never quote an estimate as the budget.** Record whichever real
number you obtain in `external_data/ego4d/logs/setup_output.txt` and replace
the `VERIFY` markers in section 2.

Whatever the number is, plan for roughly **2x it at peak** if any stage writes
decoded frames or caches next to the source clips, and leave headroom on top:
current free space is 663 GB on `C:`.

### 4.6 Codec: Ego4D is VP9, NOT H.264 -- resolved 2026-09-02

**This was wrong in the first version of this document and is the single most
important fact here.** The official Ego4D docs state the distribution is VP9:

- Canonical **videos**: `VP9`, two-pass, CRF 41, 30 fps
- Canonical **clips** (what NLQ is annotated on): `VP9`, CRF 18, constant 30 fps

There is no H.264 Ego4D distribution. `ffprobe` on a clip will report
`codec_name=vp9`, not `h264`.

#### What this actually breaks in IRIS (checked against the code, not assumed)

The conclusion "IRIS cannot use Ego4D" is too strong. The pipeline splits into
a codec-agnostic part and an H.264/HEVC-specific part:

| Signal | Weight | Source | VP9? |
|---|---|---|---|
| `packet_size` | **0.8** | `pkt.size` from the demuxer (`charon_v.py:604`) | **Works unchanged.** Packet size is a container-level property; VP9 packets have sizes like any other. |
| `motion_magnitude` + motion geometry | 0.1 | `flags2=+export_mvs` decoder flag (`charon_v.py:258`) | **Breaks.** MV export is an H.264/HEVC-specific FFmpeg feature. VP9 yields no vectors, so `motion_vectors` is empty and `compute_motion_geometry` returns all-zero neutral geometry. |
| `luma_entropy` | 0.1 | decoded pixels | Works (decode is codec-agnostic). |
| `pict_type` I/P/B normalisation | -- | `frame.pict_type`, falls back to `"I" if key_frame else "P"` (`charon_v.py:442-453`) | **Degrades.** VP9 has no B-frames; typing collapses to two classes. |

So the dominant 0.8-weight residual channel -- the actual codec-oracle novelty
claim -- transfers to VP9 intact. What is lost is the 0.1-weight motion channel
and the motion-geometry features feeding `l2_asphodel`'s hybrid retrieval
(`semantic x alpha + motion x beta`), which would silently become a
semantic-only retriever.

#### The dangerous part: it degrades silently

`iris/codec_validator.py:33` defines `_SUPPORTED_CODECS = {"h264", "hevc"}` and
line 108 only **warns** on anything else. Nothing rejects VP9. The pipeline will
run, emit zeros for every motion feature, and produce plausible-looking numbers
that quietly exclude the motion half of the architecture.

**Required before any Ego4D run:** make VP9 an explicit, logged decision rather
than a warning -- either reject, or record in the run manifest that the motion
channel is disabled so the resulting numbers are never compared against
NExT-GQA runs where it was active.

#### Do NOT re-encode to H.264

Transcoding VP9 -> H.264 manufactures the residual structure you then claim to
measure. The residuals would be an artefact of your own x264 settings, not a
property of the data. That invalidates the novelty claim.

The legitimate variant is a **controlled codec experiment**: encode the same
source under multiple codecs with pinned settings (CRF, GOP, B-frames, preset)
and compare. That answers "can compression structure be exploited cheaply?"
rather than "does the dataset's native codec carry signal?" -- a different,
still-publishable question. Pick one and state which.

#### Gate 4, revised

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,pix_fmt,avg_frame_rate,width,height -of default=noprint_wrappers=1 CLIP.mp4
```

Expect `vp9`. Then confirm on that one clip whether `packet_size` still yields a
non-degenerate curve, since that -- not H.264 specifically -- is what the
codec-oracle claim rests on.

## 5. Directory layout

```
external_data/ego4d/
  v2/annotations/   # nlq_*.json          (gitignored -- licence)
  v2/clips/         # .mp4                (gitignored -- licence, large)
  manifests/        # split json, uid lists, hashes -- COMMITTED
  logs/             # setup_output.txt                -- COMMITTED
```

## 6. Roadmap

Each stage has an explicit gate. Do not start stage N+1 until N's gate passes.

| # | Stage | Gate to pass before continuing |
|---|---|---|
| 0 | Rotate the leaked key pair; confirm the 2026-09-03 date with support | New key works against `aws s3 ls`; expiry semantics understood |
| 1 | Install CLI, pull annotations only (4.2) | `nlq_val.json` sha256 recorded in the manifest |
| 2 | `--summarize`: real clip/query counts per split | `VERIFY` markers in section 2 replaced with real numbers |
| 3 | `--make-split`: seeded video-level val_tune/val_confirm | Split file committed; zero `video_uid` overlap asserted |
| 4 | Download **one** clip; run the 4.6 codec check | Confirmed `vp9`; `packet_size` curve non-degenerate; motion-channel loss logged |
| 5 | Byte-budget the pull (4.5); download **train + val** clips | Exact total logged, and under free disk with 2x peak headroom |
| 6 | Ingest 5-10 clips through `charon_v` only | Residual curve is not degenerate under constant ego-motion; PEAK count per clip is sane, not "every frame" |
| 7 | End-to-end on ~20 val_tune clips | Pipeline completes; grounding metric computes; per-clip latency measured |
| 7b | Define + implement the trained component; fit on `nlq_train.json` | Training curve sane; no val_confirm exposure at any point |
| 8 | Model selection / early stopping on val_tune | Same protocol as the NExT-GQA Family 2 sweep |
| 9 | Freeze config; single pass on val_confirm | Logged once, with config hash |
| 10 | Optional: EvalAI test submission | Only after 9; attempts are limited |

**The highest-risk gate is 6, not 5.** Ego4D is continuous head-mounted
footage: residual energy may be high and roughly uniform everywhere, in which
case persistent-homology PEAK selection degenerates and the codec oracle
provides no gating signal at all. Find that out on 10 clips, not after a
300 GB download and a week of runs. A negative result at gate 6 is a
legitimate, reportable finding about the scope of the codec-oracle claim --
it is not a licence to tune the oracle until Ego4D looks good.

## 7. SOTA reference (verified 2026-09-02 -- re-verify before citing)

Ego4D NLQ is scored with **R@k at IoU thresholds**, not the mIoP/mIoU pair used
for NExT-GQA. IRIS's existing grounding metrics do not transfer; the eval path
needs an NLQ-format scorer before any number is meaningful.

**Validation split (what IRIS can measure locally):**

| Method | R@1 IoU=0.3 | R@1 IoU=0.5 | R@5 IoU=0.3 | R@5 IoU=0.5 |
|---|---|---|---|---|
| OSGNet (2025) | **32.56** | **22.74** | 59.82 | 46.35 |
| EgoVideo | 28.65 | 19.73 | 53.30 | 40.42 |

**Test split -- NOT comparable across challenge years:**

| Method | Year | R@1 IoU=0.3 | R@1 IoU=0.5 |
|---|---|---|---|
| OSGNet (ensemble) | 2025 | 30.19 | 21.78 |
| OSGNet | 2025 | 28.50 | 20.05 |
| EgoVideo (ensemble) | 2025 | 28.05 | 19.31 |
| GroundNLQ (CVPR23 champion) | 2023 | 25.67 | 18.18 |
| OSGNet w/ MLLM rerank | 2026 | 21.78 | 15.44 |
| OSGNet | 2026 | 21.63 | 15.52 |

**The 2026 numbers are lower than 2023's, and that is not a regression.** The
2026 challenge report states outright that the annotations or evaluation
metrics may have changed that year and that its NLQ results are not directly
comparable with previously reported ones. Mixing rows across years is exactly
the population-mismatch error that forced the NExT-GQA baseline retraction.
**Pin which protocol year you are comparing against, and say so in the paper.**

Practical target-setting: `val` R@1@0.3 of 32.56 is the number to beat locally;
anything near or below ~25 is mid-2023-era. Do not set targets off the 2026
test rows unless you are submitting under the 2026 protocol.

## 8. Open questions to resolve before stage 1

- Does 2026-09-03 bound the AWS keys or the licence term? (blocks everything)
- Is Ego4D replacing QVHighlights as the external grounding benchmark, or
  adding to it? Two external datasets is a large scope increase over the
  current NExT-GQA-centred paper plan.
- Ego4D v1 or v2? v2 is the default and carries more NLQ annotations; the
  choice must be pinned in the manifest either way.

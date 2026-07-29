# Phase 1 — Codec-boundary diagnostic (#5)

**Verdict, one sentence:** No — the next codec peak after the anchor does **not**
land in a gold span more often than all three controls for **any** question type
on either split; on val_tune it fails the raw point-estimate comparison for every
type, on val_confirm the two types that pass it (CW, TN) fail the paired
confidence interval against at least one control, and the two splits disagree in
sign, so the Tier-2 "codec as event-boundary detector" branch is closed.

Retrieval-only. No captioner, no answerer, no LLM of any kind. No retrieval
parameter, span parameter, or config value was modified. **Zero fresh ingests:**
every index for all 562 videos was a cache hit under ingest config hash
`4edae64ed40256e3`, asserted as a hard pre-flight before either split ran.

| split | questions | videos | scored | failed |
|---|---|---|---|---|
| val_tune | 2,685 | 450 | 2,685 | 0 |
| val_confirm | 639 | 112 | 639 | 0 |

Both splits came from **one consolidated invocation**; every candidate, control,
breakdown and CI is derived from that single retrieval pass per question.

### Sanity gate

The anchor reconstruction reproduces the measured C0 baseline exactly — all five
types, all five counts:

| type | n | C0 measured here | C0 stated in task |
|---|---|---|---|
| CW | 284 | 33.8% | 33.8% |
| CH | 86 | 32.6% | 32.6% |
| TC | 87 | 47.1% | 47.1% |
| TN | 167 | 22.8% | 22.8% |
| TP | 15 | 13.3% | 13.3% |

So the thing being stepped away from is the same anchor Method D picks today.

---

## 1. The headline result

In-gold rate of the **first forward codec peak after the anchor**, against all
three required controls. `C1` is the *strongest* of the four fixed forward
offsets (±1/2/3/5 s), not their average — a step that only beats the weakest
fixed offset has demonstrated nothing.

### val_tune (n = 2,685) — the primary split

| type | peak | C0 anchor | C1 best fixed | C2 random | C3 nearest surv. | beats all 3? |
|---|---|---|---|---|---|---|
| CW | 31.8% | 32.4% | 30.5% | 21.8% | 32.2% | **no** |
| CH | 35.1% | 36.5% | 36.2% | 25.9% | 35.5% | **no** |
| TC | 35.1% | 36.1% | 34.5% | 27.0% | 36.0% | **no** |
| TN | 25.3% | 24.7% | 26.0% | 18.8% | 23.9% | **no** |
| TP | 22.2% | 21.6% | 21.6% | 4.6% | 21.6% | raw yes, **not significant** |
| overall | 30.9% | 31.4% | 30.6% | 22.1% | 30.9% | **no** |

### val_confirm (n = 639)

| type | peak | C0 anchor | C1 best fixed | C2 random | C3 nearest surv. | beats all 3? |
|---|---|---|---|---|---|---|
| CW | 33.6% | 33.8% | 33.1% | 21.9% | 33.2% | raw yes, **not significant** |
| CH | 36.5% | 32.6% | 37.2% | 23.5% | 35.3% | **no** |
| TC | 44.2% | 47.1% | 46.0% | 29.5% | 44.8% | **no** |
| TN | 25.3% | 22.8% | 22.2% | 20.6% | 25.1% | raw yes, **not significant** |
| TP | 13.3% | 13.3% | 20.0% | 15.7% | 13.3% | **no** |
| overall | 32.8% | 32.1% | 32.2% | 22.7% | 32.5% | **no** |

`beats all 3` is reported twice on purpose. The raw column is the bare
inequality; the significance column additionally requires each gap to be
positive with a 95% paired video-clustered bootstrap CI (2,000 resamples, seed
`20260729`, clustered by video) excluding zero. **No cell in either split
satisfies the significant version.**

### Paired CIs, peak minus control (percentage points)

val_tune:

| type | vs C0 anchor | vs C1 best fixed | vs C3 nearest survivor |
|---|---|---|---|
| CW | −0.95 [−2.12, +0.17] | +1.04 [−0.42, +2.49] | −0.69 [−1.65, +0.18] |
| CH | −1.81 [−4.22, +0.79] | −1.03 [−3.42, +1.33] | −0.78 [−2.56, +0.82] |
| TC | −1.34 [−3.69, +1.03] | +0.27 [−1.93, +2.51] | −0.80 [−2.77, +1.11] |
| TN | +0.87 [−0.58, +2.44] | −0.58 [−2.08, +0.91] | +1.16 [+0.00, +2.34] |
| TP | +0.00 [+0.00, +0.00] | +0.00 [+0.00, +0.00] | +0.00 [+0.00, +0.00] |

val_confirm:

| type | vs C0 anchor | vs C1 best fixed | vs C3 nearest survivor |
|---|---|---|---|
| CW | +0.00 [−1.72, +1.71] | −0.36 [−3.16, +2.36] | +0.72 [−0.70, +2.11] |
| CH | +3.53 [+0.00, +8.24] | −1.18 [−6.67, +3.61] | +1.18 [+0.00, +3.80] |
| TC | −3.49 [−9.09, +1.22] | −2.33 [−8.14, +3.06] | −1.16 [−3.80, +0.00] |
| TN | **+3.01 [+0.56, +6.49]** | **+3.01 [+0.60, +5.85]** | +0.60 [+0.00, +1.94] |
| TP | +0.00 [+0.00, +0.00] | −6.67 [−21.43, +0.00] | +0.00 [+0.00, +0.00] |

**On TN specifically**, as the task asks: on val_confirm the peak step beats the
anchor and the best fixed offset by +3.01 pts each with CIs excluding zero. It
does **not** beat C3, the nearest forward survivor regardless of `is_peak`
(+0.60, CI [+0.00, +1.94], includes zero). That is the whole result in one line:
whatever small gain exists on TN comes from *moving forward at all*, not from the
peak flag. And it does not replicate — on val_tune, TN's gap versus the same
best fixed offset is **−0.58** [−2.08, +0.91], the opposite sign. Two splits
disagreeing in sign on a sub-1-point effect is noise, not a finding.

---

## 2. The recoverable-headroom number (the one that matters)

A boundary step can only ever *rescue* a question whose anchor is currently
outside gold; on the rest it can only do harm. Restricted to exactly those
questions, this is the recovery rate:

| split | type | n outside | peak recovers | C3 recovers | **C2 random recovers** |
|---|---|---|---|---|---|
| val_tune | CW | 792 | 2.4% | 1.0% | **12.9%** |
| val_tune | CH | 249 | 4.1% | 2.4% | **13.4%** |
| val_tune | TC | 243 | 3.4% | 1.3% | **14.8%** |
| val_tune | TN | 530 | 3.1% | 0.8% | **13.3%** |
| val_tune | TP | 29 | 0.0% | 0.0% | **2.2%** |
| val_confirm | CW | 188 | 2.2% | 0.0% | **11.2%** |
| val_confirm | CH | 58 | 5.3% | 3.5% | **12.8%** |
| val_confirm | TC | 46 | 2.2% | 2.2% | **14.5%** |
| val_confirm | TN | 129 | 3.9% | 3.1% | **12.9%** |
| val_confirm | TP | 13 | 0.0% | 0.0% | **10.8%** |

The peak step recovers 2–5% of the questions it would need to rescue. A **random**
forward survivor recovers 11–15% — three to six times more. On the only
population where a boundary step could help, the codec peak is not merely
uninformative, it is substantially *worse than chance*.

---

## 3. Why — the mechanism

The diagnostic is not underpowered; the signal has the wrong granularity.

| quantity | val_tune | val_confirm |
|---|---|---|
| median distance from anchor to next peak | **0.400 s** | **0.400 s** |
| p90 distance to next peak | 0.968 s | 0.933 s |
| fraction of survivor frames flagged `is_peak` | **40.0%** | **39.7%** |
| median survivors / peaks per video | 138 / 56 | 151 / 59 |
| questions with no forward peak at all | 44 (1.6%) | 10 (1.6%) |

Two out of every five survivor frames carry `is_peak=True`, spaced ~0.4 s apart.
The Method D span is ±2.2 s wide. So "step to the next peak" moves the anchor by
about one *ninth* of the span it is being scored against — it almost always
lands inside the same window it started in. That is why `fwd_peak1` tracks C3
(the nearest forward survivor, peak or not) to within a fraction of a point
everywhere: at this density, the next peak *is* essentially the next survivor,
and the `is_peak` flag partitions nothing.

An event-boundary detector needs to fire at event granularity — a handful of
times per video. This one fires 56 times in a median video. The quantity being
tested is real and distinct from saliency, but the codec peak signal as
currently constructed cannot express it.

Note also what C2 shows *positively*: a random forward survivor lands in gold
only 18–30% of the time versus ~31–33% for the anchor region. Retrieval genuinely
localises. The failure is not that the anchor is arbitrary; it is that the
correction the TN/TP error needs is a ~1–2 s directed jump, and the codec peak
series offers only 0.4 s undirected shuffles.

---

## 4. Also reported

- **Backward peaks and scene boundaries** were computed for every question
  (1st/2nd/3rd backward peak, previous/next `scene_spans` boundary) and are in
  `boundary_summary.json` and both per-question CSVs. None of them changes the
  verdict; they are recorded so the negative is complete rather than selective.
- **Duration-bucket breakdown** (`<2s`, `2-5s`, `5-10s`, `>=10s`) is in
  `boundary_summary.json` under `by_duration_bucket`.
- Candidates that do not exist (no 3rd forward peak, no next scene boundary)
  are counted as absent, not as misses — they are excluded from both numerator
  and denominator, and each rate carries its own `n`.

## 5. Honest read

This is the fifth consecutive null on the codec signal, and the first one that
tests boundary rather than saliency — so it is a genuinely new question with a
genuinely negative answer, not a repeat of the AUC≈0.50 result. The premise was
sound: TN/TP anchoring on the cue rather than the answer event *is* a boundary
problem, and no prior experiment had asked whether codec could solve it. It
cannot, for a concrete measurable reason (40% peak density at 0.4 s spacing),
not for a vague one.

I did not go looking for a subgroup where it wins. TN on val_confirm is the one
cell with any CI excluding zero, and it is reported above with the two facts
that sink it: it fails against C3, and it reverses sign on val_tune.

**Recommendation: close the Tier-2 codec-boundary branch.** If event-boundary
detection is wanted later, it needs a signal built at event granularity — the
existing `scene_spans` (median ~60 per video here, so also too dense) or a
purpose-built segmenter — not a re-parameterisation of `is_peak`.

## 6. What did not run, and why

Nothing in Phase 1 was skipped, subsampled, or interpolated. Both splits ran to
completion with zero failed questions. No cell in any table is estimated.

## Artifacts

- `per_question_valtune.csv` — 2,685 rows, one per question
- `per_question_valconfirm.csv` — 639 rows
- `boundary_summary.json` — all rates, breakdowns, CIs, verdicts
- `environment.json`, `exact_commands.txt`, `run.log`
- `protected_hashes_{before,after}.txt`

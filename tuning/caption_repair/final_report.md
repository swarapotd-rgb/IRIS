# Caption / context repairs — Phases 2 and 3

Split: val_confirm, 639 questions / 112 videos. Retrieval, span method and every
frozen hyperparameter held fixed in every arm; zero fresh ingests.

> A concurrent session independently audited Phase 3 and reached the same
> conclusion from the same per-question CSVs. Its report is preserved verbatim at
> `tuning/phase3_leakage_audit_20260729T084832Z/final_report.md`, and its extra
> detail (per-arm absolute CIs, discordant-pair counts, completion-time Arm-G
> integrity checks) is folded in below. Its headline deltas were recomputed here
> independently and agree exactly: E−A +0.0235, G−A +0.0521, E−G −0.0300;
> discordant pairs 91/110 on Acc@QA and 27/27 on Acc@GQA. One figure from that
> report is **corrected** in §6 — see the note there.

---

## 1. Phase 1 verdict (one sentence)

No — the next codec peak after the anchor does **not** land in a gold span more
often than all three controls for **any** question type on either split; on
val_tune it fails the raw point-estimate comparison for every type, on
val_confirm the two types that pass it (CW, TN) fail the paired CI against at
least one control, and the splits disagree in sign. Full detail in
`tuning/codec_boundary/final_report.md`.

## 2. Phase 3 verdict (one sentence)

No — question-aware captions did **not** beat the shuffled control: paired and
video-clustered, **E − G = −3.00 pts Acc@QA, 95% CI [−7.01, +1.05]** (n = 634
paired, 107 clusters), an interval that includes zero *and* whose point estimate
favours the control, so by the pre-registered decision rule **the apparent gain
is question leakage, not visual grounding**.

---

## 3. Phase 2 arm table

Arm A reproduced the baseline **exactly** — `Acc@QA 345/639`, `Acc@GQA 119/639`,
`P(correct | IoP≥0.5) = 0.5920`, `IoP@0.5 = 0.3146`. The harness has not drifted.

`IoP@0.5` is **identical across arms A–F** (0.3145539906103286), and identical
across A, E and G on the common 634-question subset (0.3138801262). Spans are
built before the answerer runs and no arm touches retrieval, so this is the
required check that nothing leaked from the answer stage into grounding.

| arm | #2 scaffold | #3 verbal | captions | Acc@QA | Acc@GQA | P(c\|IoP≥.5) | parse-fail | refusal |
|---|---|---|---|---|---|---|---|---|
| **A** baseline | no | no | frozen dump | 345/639 = .5399 | 119/639 = .1862 | .5920 | 0.0000 | 0.0000 |
| **B** | no | yes | frozen dump | 339/639 = .5305 | 119/639 = .1862 | .5920 | 0.0000 | 0.0000 |
| **C** | yes | no | frozen dump | 347/639 = .5430 | 119/639 = .1862 | .5920 | 0.0000 | 0.0000 |
| **D** | yes | yes | frozen dump | 346/639 = .5415 | 120/639 = .1878 | .5970 | 0.0000 | 0.0000 |
| **E** | no | no | question-aware | 360/639 = .5634 | 126/639 = .1972 | .6269 | 0.0000 | 0.0000 |
| **F** | yes | no | question-aware (E's dump) | 350/639 = .5477 | 124/639 = .1941 | .6169 | 0.0000 | 0.0000 |
| **G** | no | no | **shuffled** question-aware | 375/634 = .5915 | 125/634 = .1972 | .6281 | 0.0000 | 0.0000 |

Answer-letter distribution (counts A/B/C/D/E):

| arm | A | B | C | D | E |
|---|---|---|---|---|---|
| A | 132 | 151 | 142 | 122 | 92 |
| B | 134 | 161 | 140 | 118 | 86 |
| C | 136 | 153 | 141 | 118 | 91 |
| D | 137 | 155 | 137 | 123 | 87 |
| E | 165 | 155 | 129 | 113 | 77 |
| F | 164 | 158 | 127 | 112 | 78 |
| G | 127 | 140 | 149 | 123 | 95 |

Paired video-clustered bootstrap vs A (2,000 resamples, seed 20260729):

| arm | Δ Acc@QA | 95% CI | excl. 0 | Δ Acc@GQA | 95% CI | excl. 0 |
|---|---|---|---|---|---|---|
| B | −0.94 pts | [−2.85, +0.91] | no | +0.00 pts | [−0.47, +0.47] | no |
| C | +0.31 pts | [−1.67, +2.42] | no | +0.00 pts | [−1.04, +1.06] | no |
| D | +0.16 pts | [−1.92, +2.26] | no | +0.16 pts | [−0.67, +1.20] | no |
| E | +2.35 pts | [−1.74, +6.51] | no | +1.10 pts | [−0.89, +3.14] | no |
| F | +0.78 pts | [−3.24, +4.93] | no | +0.78 pts | [−1.23, +2.79] | no |
| **G** | **+5.21 pts** | **[+1.34, +8.99]** | **YES** | +1.10 pts | [−0.65, +2.86] | no |

And the comparison the phase exists for:

| comparison | Δ | 95% CI | excl. 0 | discordant pairs |
|---|---|---|---|---|
| **E − G, Acc@QA** | **−3.00 pts** | **[−7.01, +1.05]** | **no** | 91 for E / 110 for G |
| E − G, Acc@GQA | +0.00 pts | [−2.11, +2.19] | no | 27 / 27 |

**Every Phase-2 CI includes zero.** Neither context repair moves Acc@QA. The only
interval in the whole experiment that excludes zero belongs to Arm G — the
control.

### Per-question-type breakdown, Acc@QA (TC/TN/TP are the target; CW/CH the control)

| arm | CW (284) | CH (86) | TC (87) | TN (167) | TP (15) |
|---|---|---|---|---|---|
| A | 58.1% | 47.7% | 50.6% | 52.1% | 53.3% |
| B | 55.3% | 51.2% | 50.6% | 52.1% | 46.7% |
| C | 56.3% | 50.0% | 55.2% | 53.3% | 46.7% |
| D | 56.7% | 52.3% | 50.6% | 52.7% | 53.3% |
| E | 57.4% | 60.5% | 60.9% | 51.5% | 40.0% |
| F | 55.3% | 59.3% | 59.8% | 49.1% | 53.3% |
| G | 61.6% | 61.2% | 52.9% | 56.6% | 66.7% |

(G's n per type: CW 281, CH 85, TC 87, TN 166, TP 15.)

The temporal types are not preferentially helped by anything here. TN — the
largest failure population — is *worse* under E (51.5%) than under baseline
(52.1%), and its best cell belongs to the shuffled control. TP has n=15, where
one question is 6.7 pts, so no TP cell should be read as a result.

Arm F ran on E's caption dump via `--caption-load`, so F differs from E in
context only — re-captioning for F would have confounded the comparison. Arm G
scored 634 of 639: five questions live in single-question videos with no donor to
borrow from, so they were **skipped, never self-mapped** (a self-map is silently
Arm E). The shuffle map is a verified within-video derangement — 634 mapped,
**0 self-maps**, seed 20260729, re-verified at completion as well as at setup,
committed as `shuffle_map.json`.

---

## 4. Caption quality, before and after

Measured with one lexicon applied to all three dumps. Because the original
audit's word lists were never committed, the recomputed baseline is shown against
the historically-stated figures — **read the delta, not the absolute level**.
Three of five recompute close to the stated value; the action-verb lexicon here
is stricter (stative/posture/perception verbs excluded, enforced by an assertion
in the script), which is why its baseline reads 45.2% against a stated 52.9%.

| metric | stated baseline | recomputed baseline | E question-aware | G **shuffled** |
|---|---|---|---|---|
| % containing any temporal word | 3.0% | 3.52% | **49.96%** | **49.57%** |
| % containing any action verb | 52.9% | 45.19% | **85.21%** | **84.90%** |
| % questions with zero action verbs in all 4 | 15.6% | 21.13% | **3.29%** | **3.79%** |
| mean within-question pairwise Jaccard | 0.343 | 0.354 | 0.363 | 0.362 |
| median caption length (words) | 42 | 42 | 55 | 55 |

The metrics moved enormously — and that is the problem. **E and G are
indistinguishable on every one of them** (49.96 vs 49.57, 85.21 vs 84.90, 3.29 vs
3.79, 0.363 vs 0.362, 55 vs 55). Arm G's captions were generated from a
*deliberately wrong* question. A metric that cannot separate a relevant caption
from an irrelevant one was never measuring visual grounding.

### Where the movement came from

Recall of the question's content words by the caption (stopwords removed):

| dump | mean recall of question ASKED | % of captions recalling ≥half the question |
|---|---|---|
| baseline question-blind | 0.148 | 4.9% |
| **E question-aware** | **0.704** | **84.5%** |
| G shuffled — asked question | 0.325 | 26.0% |
| **G shuffled — DONOR question** | **0.699** | — |

Donor control on G's captions (n = 2,536, every donor resolvable, 0 exceptions):
donor − asked = **+0.374**, `diagnostic_detects_injection: true`.

That is the diagnostic validating itself. G's captions recall the question *fed
to the captioner* at 0.699 — essentially identical to E's 0.704 — while recall of
the question actually being answered collapses to 0.325. The metric follows
whichever text reached the captioner, so E's leakage figure is trustworthy. (G's
residual 0.325 sits above the 0.148 question-blind floor because donor questions
come from the same video and share subject vocabulary; it is not a self-map
artifact — the derangement was verified at completion.)

So 84.5% of question-aware captions contain at least half the question's content
words. The +46 pt temporal and +40 pt action-verb "improvements" are largely the
question's own vocabulary written back out as observation. A concrete instance is
in `focus_hint_qualitative_example.md`: on a frame showing an airplane on a
runway, the question-aware caption opens *"The boy in red stood and then appeared
to run away after standing up."* There is no boy in red. The captioner asserted a
multiple-choice option as though it had seen it.

**Did the fix do what it was supposed to? No.** The captions did not become more
visually grounded; they became more question-shaped. The one metric that would
have flagged this — within-question Jaccard — barely moved (0.354 → 0.363), i.e.
a question's four captions are as interchangeable as ever, consistent with each
carrying the same leaked sentence.

---

## 5. Caption-stage determinism

Never previously checked. 20 videos, 117 questions, **468 captions generated
twice** in question-aware mode against separately-loaded index objects, so pass 2
could not inherit pass 1's in-memory caption cache.

| quantity | value |
|---|---|
| captions compared | 468 |
| byte-identical | **468 (100.0%)** |
| differing | 0 |
| pass 1 / pass 2 wall | 394.6 s / 332.6 s |

**The caption stage is byte-for-byte deterministic.** No Phase-3 accuracy number
carries a caption-variance term. Consistent with the captioner's configuration
(temperature 0, seed 42), but now measured rather than assumed.

---

## 6. Captioning cost

| quantity | question-blind | question-aware (E) | shuffled (G) |
|---|---|---|---|
| retrieved frame-slots | 2,556 | 2,556 | 2,536 |
| **real captioner calls** | **1,665** | **2,556** | **2,536** |
| cache-served fraction | **34.9%** | 0% by construction | 0% by construction |
| cache-miss rate | 65.1% | **100%** | **100%** |
| caption wall-clock | not run end-to-end | **1,593 s** | 1,580 s |
| measured per-call cost | — | 0.623 s | 0.623 s |
| truncations after retry | — | 0 / 2,556 | 0 / 2,536 |

Question-aware captioning costs **1.535× the captioner calls** (2,556 vs 1,665),
because the per-index caption cache must be bypassed — a caption generated for
one question is not valid for another under this mode. At the measured 0.623
s/call the question-blind path would be ≈1,037 s against E's 1,593 s, i.e.
**≈ +54% caption wall-clock**. That figure is an *extrapolation*, labelled as
such: arm A replayed the frozen dump via `--caption-load`, so no question-blind
captioning pass was timed end-to-end in this work.

> **Correction to the concurrent report.** Its §6 states "roughly 10.8× the wall
> clock" for question-aware captioning. That compares E's 1,740 s total wall
> against arms A–F at ~160 s — but those arms ran with `--caption-load` and did
> **no captioning at all**, so the ratio measures "captioning vs replaying a
> dump", not "question-aware vs question-blind captioning". The like-for-like
> figure is 1.535× calls / ≈+54% wall. Its per-arm "captioning ms/question"
> column (2492.7) is `caption_answer_ms`, which also includes the answerer call.

On the C2 audit's 99.8% figure: that is a different quantity — of the 535
(video, frame) pairs revisited by a later question, 534 reused byte-identical
text. The reuse rate relevant to cost is the fraction of frame-slots served from
cache, **34.9%**, and question-aware captioning drives it to zero.

---

## 7. Honest read

**All three workstreams are null. Nothing here is shippable.**

**Phase 2.** Neither context repair moves accuracy. Every CI includes zero, and
the two repairs point in opposite directions (verbal codec state −0.94, temporal
scaffolding +0.31) with intervals that overlap almost entirely. The honest
summary is that the answerer was not bottlenecked on how frame metadata was
formatted. I would not ship B, C or D. C is the best point estimate and its
advantage over A is not distinguishable from zero.

**Phase 3, and the finding that matters.** Arm E looks like a win (+2.35 pts) but
its CI includes zero, so it is not a significant improvement over baseline even
on its own terms. Against its control it is *behind*: E − G = −3.00 pts, with
discordant pairs running 110 for G against 91 for E. The pre-registered rule was
"E ≈ G means leakage"; what was observed is weaker still — E ≤ G.

The most striking number is **G vs A: +5.21 pts, CI [+1.34, +8.99]** — the only
interval in the entire task excluding zero, belonging to the arm that captions
every frame with a question known to be wrong. Two explanations fit, and the runs
performed cannot separate them:

1. **Generic enrichment.** Any focus hint makes the captioner produce longer
   (42 → 55 words), more action-dense captions, and that helps regardless of
   relevance. The E/G caption-quality equality supports this.
2. **Matched leakage actively harms.** When the caption restates the question
   being asked and asserts an answer, it steers the answerer toward the
   captioner's guess — which is frequently wrong (the airplane / "boy in red"
   example). With a mismatched question the assertion is obviously irrelevant and
   gets discounted. The negative E − G point estimate is weakly consistent with
   this, but its CI includes zero, so I am not claiming it.

Caveats on the record, because G vs A is the one CI that excludes zero: it is
**one comparison among seven arms with no multiplicity correction** — at α=0.05
across this many contrasts, a single excluded-zero interval is about what chance
produces. And "caption using a deliberately wrong question" is a control, not a
method. **I am not recommending Arm G.** It licenses one cheap follow-up
hypothesis, not a change.

**What this says about the original diagnosis.** The measured caption deficit was
real, and question-aware captioning did move every lexical metric hard. But it
moved them by injecting question text, not visual detail — and once that is
controlled for, the accuracy benefit does not survive. The `_build_focus_hint`
path as written does not fix the caption deficit; it launders the question
through the caption field, where the answerer then reads it as evidence. **Do not
report the +2.35 pt / +46 pt / +40 pt figures as caption-quality improvements**;
they are measurements of how much question text the captioner copies.

If question-conditioned captioning is pursued further, the captioner prompt must
forbid restating the question or asserting an answer, and Arm G must be re-run
alongside it. The control is the only reason any of this is legible.

**The Phase-1 branch is closed** (see that report). The Phase-2 repairs are
reversible and default-off, so they cost nothing to leave in the code; I would
not enable them.

---

## 8. What did not run, and why

- **The NExT-GQA test split was not run**, per the task constraint. No arm used
  `--split official_test`.
- **No question-blind captioning pass was timed end-to-end.** Arm A replays the
  frozen dump, so the caption wall-clock comparison in §6 is an extrapolation
  from the measured 0.623 s/call, explicitly labelled. Everything else in that
  table is measured.
- **5 of 639 questions are absent from Arm G** — single-question videos with no
  available donor. Skipped rather than self-mapped; the paired bootstrap keys on
  `(video, qid)` so they drop from both sides and E-vs-G is computed on the
  common 634.
- **The original audit's caption lexicons could not be reloaded** (never
  committed), so absolute levels in §4 are not directly comparable to the stated
  3.0% / 52.9% / 15.6%. Both are shown; deltas are computed within one consistent
  definition.
- **The two candidate explanations for G > A were not separated.** Doing so needs
  an arm that is not in this task's design — e.g. a content-free focus hint that
  lengthens captions without naming any question.
- No cell in any table is fabricated, subsampled, or interpolated. All seven arms
  scored every question they attempted: 0 retrieval failures, 0 parse failures,
  0 refusals, 0 caption truncations, 0 duplicate `(video, qid)` keys.

---

## Artifacts

`arm_{A..G}_per_question.csv` · `arm_{A..G}_metrics.json` ·
`arm_{A..G}_environment.json` · `captions_dump_qaware.json` ·
`captions_dump_shuffled.json` · `shuffle_map.json` ·
`caption_quality_comparison.json` · `caption_determinism.json` ·
`bootstrap_ci.json` · `focus_hint_qualitative_example.md` · `environment.json` ·
`exact_commands.txt` · `run.log` · `protected_hashes_{before,after}.txt`

Concurrent independent audit: `tuning/phase3_leakage_audit_20260729T084832Z/`
(`arm_cis.json`, `caption_quality_comparison.json`, `final_report.md`).

Protected artifacts verified **byte-identical before and after** both phases
(171 hashed paths, `diff` clean). `tuning/frozen_state.json` was not modified.

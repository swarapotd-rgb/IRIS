# Phase 3 final report — P_CAPTION_CONTEXT

**Verdict: question-aware captioning is not a grounding improvement. It is
question-text leakage, and the deranged control outperforms the real thing.**

Every number below traces to a file written during this run under
`tuning/caption_repair/` or `tuning/phase3_leakage_audit_20260729T084832Z/`.
Nothing was re-run that had already completed cleanly.

---

## 1. What the captioner actually does when it sees the question

Same frame (video `10109097475`, decoded frame 120), same captioner
(minicpm-v4.6, temperature=0, seed=42). The only difference is whether
`focus_hint` was passed. Full artifact:
`tuning/caption_repair/focus_hint_qualitative_example.md`.

Hint question: *"what did the boy in red do after standing up"*,
choices: ran away / sat down / clapped / jumped / waved.

**Question-blind (the frozen production path):**

```
An airplane is present on a runway.
People are standing near the aircraft.
A building is visible in the background.
The sky is overcast with clouds.
```

**Question-aware (`focus_hint` passed):**

```
The boy in red stood and then appeared to run away after standing up.
A large airplane is present on the tarmac, suggesting airfield activity.
Several people are visible near the aircraft, likely engaged in ground operations.
```

The frame is an airplane on a runway. **There is no boy in red.** The
question-aware caption leads with a sentence that restates the question and
asserts one of the multiple-choice options as though it were an observation.
The captioner did not find better visual detail; it wrote the question back out
in the caption field, where the answerer then reads it as evidence.

This is visible at the text level before any accuracy number is computed, and
it is what every figure in the next two sections has to be read against.

---

## 2. The headline numbers, and why they do not mean what they look like

Question-aware captioning (Arm E) moves three lexical caption-quality metrics
enormously — **temporal words +46.44pt** (3.52% → 49.96%), **action verbs
+40.02pt** (45.19% → 85.21%), captions with zero action verbs −17.84pt — and
lifts Acc@QA by **+2.35pt** (0.5399 → 0.5634). Read alone, that is the story of
a fixed captioner.

It is not, and the reason is in the same table. Arm G captions each frame using
a **different question from the same video** (a verified derangement) and then
answers the original. If the gains were visual grounding, G should lose most of
them. G instead reproduces them almost exactly: **temporal +46.05pt**
(49.57%), **action verbs +39.71pt** (84.90%), within-question Jaccard 0.3622 vs
E's 0.3625, median caption length 55 words in both. Every lexical "improvement"
is produced just as well by the *wrong* question, because the metrics are
counting words that arrived from the question prompt — question text is itself
full of action verbs and temporal words.

The direct measurement confirms it. Question content-word recall by the caption:

| dump | recall of ASKED question | captions recalling ≥half the question |
|---|---|---|
| baseline (question-blind, production) | 0.1480 | 4.93% |
| **E (question-aware)** | **0.7039** | **84.47%** |
| G (shuffled) — asked question | 0.3247 | 26.03% |
| **G (shuffled) — DONOR question** | **0.6990** | — |

E recalls 70% of the question it was shown. G recalls 70% of the **donor**
question it was shown and only 32% of the one actually asked. The injected
text is what comes back out, whichever text it is.

And on Acc@QA the control does not merely match the treatment — **it beats it.**
Arm G scores **0.5915**, above E's 0.5634.

---

## 3. Bootstrap 95% CIs — all seven arms

Video-clustered bootstrap, 2000 resamples, seed 20260729 — the same
methodology, seed and resample count as the Phase 2 CI column
(`scripts/caption_repair_analysis.py:paired_bootstrap`). Written to
`tuning/phase3_leakage_audit_20260729T084832Z/arm_cis.json` by
`scripts/phase3_arm_cis.py`.

### Per-arm absolute Acc@QA

| arm | description | n | Acc@QA | 95% CI |
|---|---|---|---|---|
| A | baseline, question-blind | 639 | 0.5399 | [0.4954, 0.5840] |
| B | context variant | 639 | 0.5305 | [0.4882, 0.5742] |
| C | #2 scaffolding | 639 | 0.5430 | [0.4967, 0.5879] |
| D | context variant | 639 | 0.5415 | [0.4976, 0.5852] |
| E | question-aware captions | 639 | 0.5634 | [0.5249, 0.6040] |
| F | E's captions + C's context | 639 | 0.5477 | [0.5075, 0.5901] |
| G | **shuffled** question-aware | 634 | **0.5915** | [0.5499, 0.6307] |

These absolute intervals carry the between-video variance of the split, which
is common to all arms and cancels in a paired test. They overlap nearly
everywhere; that overlap is **not** evidence of no difference. The paired tests
below are the ones that decide anything.

### Paired delta vs baseline A (Acc@QA)

| comparison | delta | 95% CI | excludes 0 |
|---|---|---|---|
| B − A | −0.0094 | [−0.0285, +0.0091] | no |
| C − A | +0.0031 | [−0.0167, +0.0242] | no |
| D − A | +0.0016 | [−0.0192, +0.0226] | no |
| **E − A** | **+0.0235** | **[−0.0174, +0.0651]** | **no** |
| F − A | +0.0078 | [−0.0324, +0.0493] | no |
| **G − A** | **+0.0521** | **[+0.0134, +0.0899]** | **YES** |

The +2.35pt headline for question-aware captioning **does not clear zero
against its own baseline**. The only arm in the entire experiment whose gain
over baseline is significant is Arm G — the one captioned with the wrong
question.

### The decisive comparison: E vs G

**Acc@QA delta (E − G) = −0.0300, 95% CI [−0.0701, +0.0105], n_paired = 634,
107 video clusters — the interval includes zero, so E's point estimate of
0.5634 (0.5615 restricted to G's 634 rows) does not clear G's 0.5915, and the
point estimate favours G.** Discordant pairs run 91 in E's favour against 110
in G's.

On Acc@GQA the two are indistinguishable to four decimal places: delta
**+0.0000**, CI [−0.0211, +0.0219], with a perfectly symmetric 27 / 27
discordant split.

Per the preregistered reading, E ≈ G means the gain is leakage. What was
observed is weaker than E ≈ G: E ≤ G.

---

## 4. Control-for-the-control — is the diagnostic itself sound?

Required before trusting any of section 2. If G's captions showed elevated
recall against the *asked* question, the recall metric would be measuring
something other than injection and E's 0.7039 would be worthless.

`question_leakage_vs_donor()` in `scripts/caption_quality_metrics.py` scores
G's captions against both questions:

- recall of the **asked** question: **0.3247**
- recall of the **donor** question actually injected: **0.6990**
- donor − asked: **+0.3743**, `diagnostic_detects_injection: true`
- 2536 captions, `n_questions_without_resolvable_donor: 0`

The metric tracks whichever question reached the captioner, and drops by more
than half when that question is swapped. Donor recall in G (0.6990) sits
essentially on top of asked recall in E (0.7039) — the same injection rate for
the same mechanism. **The diagnostic is sound; E's leakage number stands.**

G's residual 0.3247 against the asked question is above the question-blind
floor of 0.1480 and is expected: donor questions come from the same video and
share subject vocabulary. It is not a self-map artifact — see section 5.

---

## 5. Arm G completion and integrity (verified at completion, not mid-run)

- **634 / 639 scored**, 0 retrieval failures, 0 empty generations, 0 unparsed
  answers, 0 duplicate `(video, qid)` keys.
- **Not 639.** The 5 unscored questions are the 5 single-question videos
  (`13515224395/0`, `2857132732/7`, `3175315183/3`, `4740074365/8`,
  `5048503508/5`), which have no second question to borrow from. They were
  **skipped, never self-mapped** — a self-map is silently Arm E and would
  contaminate the control. All 5 confirmed absent from G's CSV and present in
  E's; the paired bootstrap keys on `(video, qid)` so they drop out of both
  sides.
- **0 self-maps at completion**: re-checked against the map after the run, not
  only at setup. Every one of the 634 scored rows has a donor ≠ itself, and
  every donor resolves to a real question of the same video (0 exceptions).
- Grounding metrics are untouched by the arm, as they must be: IoP@0.5 =
  0.3139 for G vs 0.3146 for A–F, differing only through the 5 absent rows.

## 6. Cost

Question-aware captioning forfeits the caption cache by construction — a
caption is only valid for the question that produced it.

| arm | captioning ms / question | wall clock | reuse forfeited |
|---|---|---|---|
| A–D, F (question-blind, warm cache) | ~0.1 | ~150–166 s | — |
| E (question-aware) | 2492.7 | 1739.7 s | 34.86% |
| G (shuffled) | 2492.0 | 1733.1 s | 35.13% |

Roughly **10.8× the wall clock** and ~2.5 s of captioning per question, to buy
a +2.35pt Acc@QA change whose CI includes zero and which a deranged control
matches or exceeds.

> **CORRECTION (added after this report was first written; the rest of the file
> is left as originally issued).** The **"10.8× the wall clock" ratio above is
> withdrawn.** Arms A–D and F ran with `--caption-load`
> (`exact_commands.txt:24`, `$COMMON`) and performed **no captioning at all**,
> so their ~160 s is the cost of replaying a frozen dump, not of question-blind
> captioning. The ratio therefore measured captioning vs not captioning.
>
> The like-for-like cost is the cache bypass: real captioner calls rise from
> **1,665 to 2,556 (1.535×)** for E — 2,556 retrieved frame-slots of which 891
> would have been served from cache — at a measured **0.623 s/call**, giving
> **1,593 s against a projected 1,038 s, ≈ +54%**. Arm G is the same to three
> digits (1.542×, 0.623 s/call). The projection assumes question-blind calls
> cost the same per call; they are likely cheaper (42- vs 55-word captions), so
> +54% is if anything an underestimate of the ratio.
>
> The per-question figure in the table (2,492.7 ms) is **correct as labelled**:
> it is `total_caption_ms / n_scored`, and `total_caption_ms` sums `caption_ms`
> (`val_confirm_e2e_eval.py:1173` → `:1031`), which covers captioning plus
> context assembly and **excludes** the answerer. The distinct
> `caption_answer_ms` field (`:919`) is the one that adds `answer_ms`, and reads
> 2,632.83 ms median for E — a different number. Nothing in §3 or §4 depends on
> either figure; this correction touches cost only.

---

## 7. Conclusion

`P_CAPTION_CONTEXT` is **rejected**. The mechanism is question-text leakage
into the caption field, not improved visual grounding:

1. The captioner demonstrably writes the question back out as an observation on
   a frame that does not contain the question's subject (§1).
2. Every lexical caption-quality gain is reproduced to within ~0.4pt by the
   wrong question (§2).
3. Question content-word recall rises 0.148 → 0.704 and follows whichever
   question was injected (§2, §4).
4. E's +2.35pt does not clear zero against baseline; only the deranged control
   clears zero; and E does not clear G (§3).
5. The diagnostic that establishes 2–3 passes its own positive control (§4).

**Do not ship question-aware captioning, and do not report the +2.35pt /
+46pt / +40pt figures as caption-quality improvements.** They are measurements
of how much question text the captioner copies.

### Failure modes and caveats

- No arm failed. 7/7 arms completed; A–F at 639/639, G at 634/639 by design.
- No file failed to parse. All 171 protected files re-verified by SHA-256
  after the run (§ `protected_hashes_before.txt`), including
  `tuning/frozen_state.json`, `eval/data/nextqa/val.csv`, `test.csv` and the
  val_confirm artifacts — all read-only throughout, 0 mismatches.
- The absolute per-arm CIs in §3 are one-sample and much wider than the paired
  deltas; they are reported because they were asked for, and must not be used
  to argue for or against a difference between arms.
- **E > G would not have proved grounding either.** As flagged before the run,
  E > G is equally consistent with leakage-plus-mismatch, since G's leaked
  sentence restates a question that is actively wrong for the row. The
  observed E ≤ G removes the need to separate those, but the asymmetry is
  worth carrying forward to any future control design.
- Arm B–D/F context variants are all null against A, consistent with Phase 2.

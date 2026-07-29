# Phase 3 leakage audit — 20260729T084832Z

Two parts. **Part 1** finishes the P_CAPTION_CONTEXT experiment (Arm G,
bootstrap CIs, final report). **Part 2** determines whether the leakage pattern
found in Arm E contaminates any currently-cited production number.

- Part 1 full text: [`final_report.md`](final_report.md) (same content as
  `tuning/caption_repair/final_report.md`), summarised in §1 below.
- Part 2 determination: §2 below.
- What could not be determined: §3 — **required section, non-empty.**

Artifacts written this run: `arm_cis.json`,
`caption_quality_comparison.json`, `final_report.md`, this file. Arm outputs
live in `tuning/caption_repair/`. No number below is stated that does not trace
to one of those files or to a prior committed run named inline.

---

## 1. Part 1 summary — P_CAPTION_CONTEXT is REJECTED

Question-aware captioning is question-text leakage, not improved grounding.

**The evidence, in the order it should be read.** On a frame containing an
airplane on a runway and no boy in red, the question-aware captioner emits *"The
boy in red stood and then appeared to run away after standing up"* — it restates
the question and asserts a multiple-choice option as an observation
(`tuning/caption_repair/focus_hint_qualitative_example.md`). Against that, the
headline gains — **+2.35pt Acc@QA** (0.5399 → 0.5634), **+46.44pt** captions
with a temporal word, **+40.02pt** with an action verb — are reproduced to
within 0.4pt by Arm G, which captions from a *different* question of the same
video (+46.05pt / +39.71pt, Jaccard 0.3622 vs 0.3625, median length 55 vs 55).
Question content-word recall rises **0.1480 → 0.7039** under Arm E, and in Arm G
tracks the **donor** question (0.6990) rather than the asked one (0.3247). The
lexical metrics were counting question text.

**Decisive comparison.** Paired video-clustered bootstrap, 2000 resamples, seed
20260729 (the Phase 2 methodology): **E − G = −0.0300 on Acc@QA, 95% CI
[−0.0701, +0.0105], n=634 over 107 clusters — the CI includes zero, so E's
0.5634 does not clear G's 0.5915, and the point estimate favours the control.**
Acc@GQA: delta +0.0000, CI [−0.0211, +0.0219], 27/27 discordant.

**All seven arms, Acc@QA (absolute CI | paired delta vs A):**

| arm | n | Acc@QA | 95% CI | Δ vs A | Δ CI | excl 0 |
|---|---|---|---|---|---|---|
| A | 639 | 0.5399 | [0.4954, 0.5840] | — | — | — |
| B | 639 | 0.5305 | [0.4882, 0.5742] | −0.0094 | [−0.0285, +0.0091] | no |
| C | 639 | 0.5430 | [0.4967, 0.5879] | +0.0031 | [−0.0167, +0.0242] | no |
| D | 639 | 0.5415 | [0.4976, 0.5852] | +0.0016 | [−0.0192, +0.0226] | no |
| E | 639 | 0.5634 | [0.5249, 0.6040] | +0.0235 | [−0.0174, +0.0651] | no |
| F | 639 | 0.5477 | [0.5075, 0.5901] | +0.0078 | [−0.0324, +0.0493] | no |
| G | 634 | 0.5915 | [0.5499, 0.6307] | +0.0521 | [+0.0134, +0.0899] | **YES** |

E's +2.35pt does not clear zero. The only arm that does is the deranged
control. Absolute CIs are one-sample, carry between-video variance that cancels
in the paired tests, and must not be used to argue for or against a difference.

**Control-for-the-control (required before trusting the above).** Re-running the
Arm-E leakage diagnostics on G's captions: donor-question recall 0.6990 vs
asked-question recall 0.3247, delta +0.3743, `diagnostic_detects_injection:
true`, 2536 captions, 0 unresolvable donors. The metric follows whichever
question was injected and halves when it is swapped; G's donor recall (0.6990)
sits on E's asked recall (0.7039). **The diagnostic is not broken — E's leakage
figure stands.**

**Arm G completion, verified at completion:** 634/639 scored, 0 failures, 0
empty generations, 0 duplicate keys, **0 self-maps**, every donor a real
question of the same video. The 5 unscored rows are the 5 single-question
videos — skipped, never self-mapped.

**Cost — corrected, see §5.** Question-aware captioning bypasses the per-index
caption cache, taking real captioner calls from 1,665 to 2,556 (**1.535×**) at a
measured 0.623 s/call, i.e. **≈ +54% captioning wall-clock** (1,593 s vs a
projected 1,038 s). The "≈10.8× wall clock" figure in
[`final_report.md`](final_report.md) §6 is **withdrawn** — it compared E's total
run wall against arms A–D/F, which ran with `--caption-load` and did no
captioning at all, so it measured captioning-vs-replaying-a-dump rather than
question-aware-vs-question-blind captioning.

---

## 2. Part 2 — leakage contamination check on cited production numbers

### 2.1 What controls question-aware captioning

**There is no config flag.** This is the central finding of Part 2 and it
contradicts the framing in the task (and in the C1 handoff item), which assumed
a frozen flag existed to be read.

- `iris/query.py:381` — `_build_focus_hint(question, choices)` returns a hint
  **iff `question` is truthy**, and `None` otherwise. It consults no config
  object; there is no gate, default, or override in it.
- `iris/query.py:486` — inside `_ensure_captions`, `focus_hint =
  _build_focus_hint(question, choices)`.
- **The control is call-site arity.** A caller that passes `question=` gets
  question-aware captions; a caller that omits it gets `None` and the generic
  question-blind prompt.

Confirmed absent by direct inspection, not memory:

- `tuning/frozen_state.json` — 13 frozen keys, all retrieval/span parameters
  (`retrieval_strategy` … `max_prominence`). Substring counts across the whole
  file: `caption` 0, `focus` 0, `hint` 0, `aware` 0. **The frozen state has
  never carried a captioning flag, so it cannot answer this question and no
  value in it should be quoted as if it did.**
- `iris/iris_config.py` — the only captioning key is
  `captioner_backend: str = "minicpm"` (line 110). No question-aware/focus
  setting exists.

### 2.2 Which call sites are question-aware, by file and line

| caller | line | passes `question=`? | captions |
|---|---|---|---|
| `iris/query.py` `_query_v2` (production) | **1024** | yes | **question-AWARE** |
| `iris/query.py` legacy path (production) | **1222** | yes | **question-AWARE** |
| `iris/query.py` debug_trace | **1287** | yes | question-AWARE |
| `scripts/val_confirm_e2e_eval.py` @ `3a6930c` | **867–869** | **no — positional** | **question-BLIND** |
| `scripts/val_confirm_e2e_eval.py` @ `6f36f08` | **280–282** | **no — positional** | **question-BLIND** |
| `scripts/val_confirm_e2e_eval.py` working tree, `else` branch | **1019–1023** | no — positional | question-BLIND |
| `scripts/val_confirm_e2e_eval.py` working tree, Arm E/G branch | **1016–1018** | yes | question-AWARE (this run only, uncommitted) |

The production query path **is** question-aware and has been since `5beab10`
(2026-07-20). **No cited number was produced by it.** Every cited number came
from `scripts/val_confirm_e2e_eval.py`, which never calls
`iris_query.query()` or `_query_v2` at either cited commit (verified by grep
against `git show <commit>:scripts/val_confirm_e2e_eval.py`) — it builds
`context_text` directly from the L1 cache, so its only captioning is the
positional, question-blind `_ensure_captions` call above.

### 2.3 Determination per cited number

**Question-aware captioning was OFF for every currently-cited number. This
closes clean. No cited figure is contaminated.**

| cited number | value | source | run / commit | caption path | verdict |
|---|---|---|---|---|---|
| Acc@QA **0.5399** | 0.539906103286385 | `tuning/d1_20260729T055818Z/val_confirm_e2e_repeat_summary.json` | D1, `git_head` `3a6930c` (recorded in that run's `val_confirm_e2e_environment.json`) | positional, lines 867–869 | **CLEAN** |
| Acc@GQA **0.1862** | 0.18622848200312989 | same file | same | same | **CLEAN** |
| Acc@GQA **0.1894** | 0.1894 (121/639) | `tuning/val_confirm_e2e_report.md:109` | val_confirm E2E, commit `6f36f08` | positional, lines 280–282 | **CLEAN** |
| Acc@QA 0.5462 | 0.5462 (349/639) | `tuning/val_confirm_e2e_report.md` | same | same | **CLEAN** |

**Independent empirical corroboration for the D1 pair.** Arm A of this run is
the explicitly question-blind arm, and it reproduces both D1 figures
**bit-exactly**:

```
Arm A  Acc@QA  = 0.539906103286385   D1 cited = 0.539906103286385   EXACT MATCH
Arm A  Acc@GQA = 0.18622848200312989 D1 cited = 0.18622848200312989 EXACT MATCH
```

Had D1 been captioned question-aware it would have landed on Arm E's 0.5634 /
0.1972, not Arm A's. So the determination rests on two independent legs —
static (call-site arity at the recorded commit) and empirical (bit-exact
reproduction by the question-blind arm) — not on the frozen state, which is
silent on the matter.

> **Provenance caveat on the D1 directory.** `tuning/d1_20260729T055818Z/` is
> **untracked** in git at the time of this audit — it is an in-flight run
> directory, not an already-committed prior run, and it is deliberately not
> committed here (it belongs to separate work). The 0.5399 / 0.1862 figures are
> therefore quoted from an uncommitted artifact. They survive that caveat only
> because Arm A — committed by *this* run — reproduces both bit-exactly, so the
> values themselves trace to a file written during this run. Anyone re-checking
> this determination should use `tuning/caption_repair/arm_A_metrics.json`, not
> the D1 directory, as the citable source.

**Direct measurement on the production caption cache.** Beyond inference: the
question-blind production dump `tuning/blind_ablation/captions_dump.json`
(SHA-256-protected, `041285d8…`) was run through the same two Arm-E
diagnostics. Question content-word recall **0.1480**, captions recalling ≥half
the question **4.93%** (2556 captions) — against E's 0.7039 / 84.47%. The
production caption path shows no elevated leakage; 0.148 is the residual you
get from captions and questions describing the same scene.

Per the task's branch structure, step 2 (running the diagnostics against a
contaminated run's cached captions) is **not applicable** — there is no
contaminated cited number. It was performed on the clean production cache
anyway, as above, since the cache existed.

### 2.4 The number that could not be located: "Acc@GQA 0.167"

The task names `0.189/0.167` as cited Acc@GQA values. **0.189 resolves
(0.1894, `tuning/val_confirm_e2e_report.md:109`). 0.167 does not resolve to any
Acc@GQA anywhere in the repository.** A case-insensitive regex for `Acc@GQA`
within 40 characters of `0.16x` across all `.md`, `.json` and `.txt` files
returns zero hits. The nearest values, none of which are Acc@GQA:

- `0.1677` — mIoU for the `type=TP` and `gold_width=2-5s` buckets,
  `tuning/query_reformulation_v2_report.md:85,98` (a retrieval metric)
- `0.16089` — D1 mIoU, `val_confirm_e2e_repeat_summary.json` (retrieval)
- `0.167` — lower bound of a bootstrap CI, `tuning/w2_.../REPORT.md:439`

Since Part 2's method is provenance tracing per number, an unresolved
identifier cannot be cleared by inference from its neighbours. Carried to §3.

---

## 3. What I could not determine

**This section is required and is non-empty.**

1. **The identity of the cited "Acc@GQA 0.167" — UNDETERMINED.** It matches no
   Acc@GQA value in the repository (§2.4). It may be a transcription of the
   0.1677 mIoU, of D1's 0.16089 mIoU, or a figure that lives only in a document
   outside this repo. **If it is an Acc@GQA that exists somewhere I cannot
   read, it has not been cleared by this audit** and needs its producing run
   named before reuse. Every Acc@GQA I *could* locate is clean.

2. **Numbers in documents outside this repository — OUT OF SCOPE.** The audit
   clears the four figures in §2.3 as they appear in
   `tuning/d1_20260729T055818Z/` and `tuning/val_confirm_e2e_report.md`. It
   cannot verify that a slide, paper draft, or handoff doc quotes those figures
   with their conditions intact (`cerberus_mode="none"`, unverified Acc@GQA,
   val_confirm not test). That is a citation-hygiene check on documents I do
   not have.

3. **Arm G's residual 0.3247 asked-question recall is not decomposed.** It is
   above the 0.1480 question-blind floor and is expected from same-video
   vocabulary overlap between donor and asked question, but this run does not
   separate "shared subject nouns" from "the derangement leaking useful
   information anyway." It does not affect the E-vs-G verdict — a leak that
   helps G only strengthens the finding that E fails to beat it — but it is not
   measured.

4. **Whether the production query path (`iris/query.py:1024`, question-aware)
   has ever produced a reported number.** I verified that neither cited run
   used it. I did **not** exhaustively audit every script in the repo for other
   callers of `query()`/`_query_v2` whose outputs might have been quoted
   somewhere. The four numbers named in §2.3 are cleared; a blanket "no
   reported number has ever come from the question-aware path" is **not**
   established by this audit.

5. **The 5 skipped Arm-G questions have no control.** Single-question videos
   cannot be deranged, so for those rows the leakage hypothesis is untested.
   They are 0.8% of the split and are excluded from both sides of the paired
   comparison, so they do not bias it — but they are not covered by the result.

---

## 4. Integrity

- **All 171 protected files re-verified by SHA-256 after the run: 171/171 OK,
  0 mismatches.** Includes `tuning/frozen_state.json`
  (`612a93ba…`), `eval/data/nextqa/val.csv` (`ee0ef210…`),
  `eval/data/nextqa/test.csv` (`a8d67c5a…`),
  `tuning/val_confirm_e2e_per_question.csv` and
  `tuning/val_confirm_e2e_report.md`. NExT-GQA splits, val_confirm data and
  the frozen state were read-only throughout, as required.
- **7/7 arms completed.** A–F at 639/639, G at 634/639 by design. 0 arms
  failed, 0 files failed to parse, 0 hash mismatches.
- Nothing that had already completed cleanly was re-run. Arms A–F were read
  from the CSVs they had already flushed; only Arm G executed during this task.
- No tuning was performed and no config was changed. Two analysis scripts were
  added (`scripts/phase3_arm_cis.py`, and the `question_leakage_vs_donor`
  control plus its `--donor-map` flag in `scripts/caption_quality_metrics.py`);
  both read existing artifacts and re-run no arm.

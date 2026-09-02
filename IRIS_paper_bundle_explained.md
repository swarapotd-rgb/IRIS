# IRIS_paper_bundle — every file, every line, explained in plain words

This bundle is a **draft research paper** (plus its two working notes files). The paper is about a
system called **IRIS** that answers questions about long videos. The team is arguing one main point:
*you can build the "map" (graph) that a video-search system uses without spending money on a big AI
model — and you can prove your cheap map is literally the exact same map.*

There are 13 markdown files. Below, each file is walked through in order, quoting the actual lines and
explaining what they mean.

---

## Glossary first (read this once and the rest becomes easy)

| Term in the paper | What it actually means |
|---|---|
| **graph** | A map of the video: every kept frame is a dot ("node"), and similar/related frames are joined by lines ("edges"). |
| **node** | One surviving video frame. |
| **edge** | A connection between two frames, with a number (weight) saying how strongly they relate. |
| **N** | The number of frames that survived filtering — NOT the total frames in the file. |
| **S** | The number of scenes the video was chopped into. |
| **dense graph** | Connect *everything to everything*. Very expensive. |
| **scene-sparse graph** | Only connect frames inside the same scene. Never across scenes. |
| **dense-then-prune** | The old way: build the everything-to-everything graph, then delete the cross-scene lines. Wasteful. |
| **block-diagonal** | The new way: only ever build the within-scene chunks. Same result, no waste. |
| **PageRank** | Google's old ranking algorithm. Here it ranks which frames are "important" in the graph. |
| **personalised PageRank (PPR)** | Same, but biased toward your query, so it ranks frames relevant to *your* question. |
| **CLIP** | An off-the-shelf model that turns an image or a sentence into a list of numbers, so you can compare pictures and text. |
| **compressed-domain / codec signals** | Clues read straight out of the compressed video file (how big each packet is, motion vectors) without fully decoding the video into pictures. Cheap. |
| **ingest** | The one-time "read the video and build the index" step. |
| **survivors / admission** | Frames the system decided to keep. It throws away ~89% of frames. |
| **top_k** | The number of frames retrieval hands to the answering model (here, 30). |
| **captioning** | Turning a frame into a text description so the language model can read it. This is the slow part. |
| **answerer** | The small language model (`granite4:micro`, ~3.4 billion parameters) that writes the final answer. |
| **Acc@GQA** | "Grounded QA accuracy": you only score a point if you answer correctly **and** point at the right moment in the video. |
| **Acc@QA** | Answer accuracy alone, ignoring whether you pointed at the right place. |
| **mIoP / IoP@0.5 / mIoU** | Grounding scores — how well your predicted time window overlaps the true one. |
| **M-Avg** | Mean accuracy averaged over the MLVU benchmark's tasks. |
| **95% CI** | Confidence interval. The plausible range for a number. If the range crosses zero, the effect might be nothing. |
| **bootstrap** | A way to compute that range by re-sampling your data thousands of times. |
| **pre-registration** | Writing down, *before* you look at the data, what result would count as success or failure. Stops you from moving the goalposts. |
| **kill criterion** | A pre-written rule: "if the number comes back like this, the idea is dead." |
| **artifact** | A saved result file on disk (JSON/markdown) produced by a run. |
| **ledger / `CLAIMS.md`** | A separate spreadsheet-like file listing every number the paper is allowed to print, and where it came from. `[C2.1]` etc. are row IDs in it. |
| **`[TODO]`** | A real hole in the draft. |
| **P0 / P1 / P2** | Priority of an edit. P0 = the paper is *wrong* without it. P1 = must fix before submitting. P2 = nice to have. |
| **Amdahl** | Amdahl's law: speeding up a small part of a process barely helps the total. Their core disappointment. |
| **censored measurement** | The run was killed by a timeout, so you know it took "more than X", not how long. |

---
# FILE 1 — `README.md` (87 lines)

*What it is:* the cover note for the whole bundle. Tells co-authors what's inside, the rules for editing,
and what still has to happen before the paper can be submitted.

**Lines 1–4** — `# IRIS Paper 1 — draft bundle` / `**Assembled 2026-08-21.** Working title: *Provably-Identical Sparse Graph Construction for Long-Video Retrieval on CPU.*`

The title spelled out in plain words: "We can build the video-search map in a skinny way that is
**provably identical** to the fat way, for long videos, using only a normal CPU (no graphics card)."
"Paper 1" means a second paper is already planned.

**Lines 6–7** — `This is a complete first draft of every section plus both appendices. It is a **team working draft, not a submission**`

Every chapter exists. But it's not finished — don't send it to a conference yet.

**Line 9** — `## Editing rules (please keep)`

House rules so co-authors don't accidentally break the paper's honesty.

**Lines 11–12** — Rule 1: `Every number traces to a PRINT-SAFE / PRINT-SAFE-CAVEATED row in CLAIMS.md, tagged inline as [C2.1] etc. Do not add a number without a ledger row.`

There is a master list (`CLAIMS.md`) of every number that has been checked and is safe to print. Some are
"safe", some are "safe but only if you print the warning with it". Every number in the paper must carry
its ID tag like `[C2.1]`. **You may not invent a number.**

**Lines 13–15** — Rule 2: `**[TODO]** marks a genuine gap. **Do not fill a TODO from memory** — pull from the artifact. (A remembered ~4.6× end-to-end figure that no artifact backed is exactly how this went wrong once.)`

If you see `[TODO]`, it's a real hole. Don't fill it from what you *think* you remember. This bit is a
confession: someone once carried around a "we're 4.6× faster end-to-end" number that **no actual
experiment ever produced**. It was a phantom. That's why the rule exists.

**Line 16** — Rule 3: `A caveat written into a sentence is load-bearing; don't split a number from its caveat.`

If a number has a warning attached ("but only under these conditions"), the warning must stay glued to it.
Don't quote the shiny number alone.

**Line 17** — Rule 4: `Nothing on the DEAD list in CLAIMS.md reappears, including in motivation prose.`

Claims that have been killed must not sneak back — not even softly in an intro paragraph.

**Lines 19–34** — `## Files (read in order)` and the table

A reading order and status for each file:
- `00_abstract.md` — two versions of the abstract, ~330 words and ~150 words, so you can pick based on the venue's word limit.
- `01_introduction.md` — v1 (first draft, untouched by the revision pass).
- `02_related_work.md` — v2, meaning the P0-3 fix has been applied.
- `03_method.md` — v2 (P0-1 applied).
- `04_05_construction_and_scaling.md` — v2 (P0-2 applied) — marked **"carries the paper"**, i.e. this is where the actual evidence lives.
- `06`, `07`, `08_09`, `10` — still v1.
- `11_appendix_B_prereg.md` — v2 (P1-1, P1-2 applied).
- The two `_working/` files: the edit to-do list, and the notes from reading result-file warnings.

**Lines 36–37** — `Each section file ends with an **edit log** recording what changed v1→v2 and what was verified from source.`

Each file logs its own change history so nobody loses track of what was fixed and why.

**Lines 39–47** — `## What's been done`

- Full draft of everything exists.
- **P0 edits done:** three claim-accuracy fixes — the config table in §3.5, the honest rewording of the grounding-gate claim in §4.1, and the corrected codec-cost story in §2.5.
- **P1 Appendix-B edits done:** a second failed prediction added, and the admission that not all pre-registrations were equally strict.
- The abstract was written **last**, deliberately claiming as little as the evidence allows.

**Lines 49–55** — `## Open before submission (none of it is writing)`

Everything left is logistics or verification, not prose. The big blocker: a **156 MB zip file
(`IRIS_latest.zip`) is stuck in the git history**, which stops anyone pushing `main`. Because of that,
several result files (R0, T5, T6, ingest efficiency) exist **only on one laptop**. So several dates,
provenance rows, and the §7.2 numbers currently rest on a single machine — if that laptop dies, the
evidence dies.

**Lines 57–61** — `**Owner-specific:**` — the note to Sonu

A message to a teammate: the C1.1 issue is fixed, the commit was pushed, the scaling curve is committed
with confidence intervals, so his pending patch and cache rebuild are no longer needed. Also send him the
end-to-end result (0.778×) because it independently backs up his advice to "lead with C2" (i.e. lead the
paper with the construction result, not the query-speed result).

**Lines 63–68** — `**Mechanical, no re-runs:**`

Things fixable by typing, not by re-running experiments:
- Appendix A.2 (the machine spec: CPU, RAM, OS, torch version) is **empty**, and it's mandatory because the headline claim is a wall-clock timing.
- Four provenance problems: the MLVU result has no git commit recorded; the flagship clip is `mpeg4` not `H.264`; the 1,104× figure has an untold caveat; two headline runs were done from messy ("dirty") working directories with 94 and 87 uncommitted files.

**Lines 70–76** — `**Needs a person who knows the history:**`

- **P2-3:** the paper currently apologises for using salience weights 0.5/0.3/0.2 "instead of the production default 0.8/0.1/0.1" — but the code's actual default *is* 0.5/0.3/0.2 and 0.8/0.1/0.1 appears nowhere. So the apology may be **backwards**. Find out where 0.8/0.1/0.1 came from before disclaiming a mistake that never happened.
- **P2-4:** three literature gaps in §2 that need a human who knows the field.

**Lines 77–79** — `**Team decision:**` mIoP/IoP

The grounding scores are currently left out of §6 because they were computed with a different convention
("union") than the public leaderboard ("max-per-span"), which makes them look better than they should and
not comparable. Fixing it needs a re-run. Note: the abstract doesn't depend on this either way.

**Lines 81–87** — `## Deliberately deferred to the follow-up paper`

Four possible speed optimisations to the graph builder are being **intentionally skipped**: they don't
improve the headline 220× number, one of them would change retrieval behaviour, and all of them would
force re-verifying code that's already been proven correct. They'll be the backbone of paper #2, together
with the "before/after questions fail" and "scene shortlist" diagnostics.

---
# FILE 2 — `00_abstract.md` (84 lines)

*What it is:* the abstract (the summary at the top of a paper), in two lengths, plus notes explaining
what it deliberately refuses to claim.

**Line 1** — `# Abstract — final draft (2026-08-19)`

Written on 19 Aug 2026, after the body was fixed.

**Lines 3–4** — `> Written last, after P0 (edge-mode scoping) and the P1-5 decision to omit mIoP/IoP.`

The abstract was written **after** the corrections, so it only claims what survived them. "Edge-mode
scoping" = being precise about which graph setting each experiment used. "P1-5" = the decision to drop
the grounding metrics.

**Lines 4–5** — `Every claim here is checked against the v2 body. Ledger tags are for co-author verification and are removed before submission.`

Every sentence was cross-checked. The `[C2.1]`-style tags are internal bookkeeping and get deleted before
the paper goes out.

**Lines 7–9** — `Two corrections vs. the v0 placeholder: (i) it is dense *retrieval* that fails to return, not dense *construction*; (ii) the identity claim is scoped to the two construction paths it concerns.`

Two things the earlier draft got wrong:

1. When things time out, it is the **searching** step that hangs, not the **building** step. Different stage — important not to mix them up.
2. The "identical" proof only covers the two specific build methods being compared, not everything.

### The long abstract (lines 15–43)

**Lines 15–19** — "Graph-structured pipelines for long-video question answering increasingly build the graph itself with a frontier multimodal model, at a per-chunk API cost that scales with video duration and cannot run locally. We take the opposite approach: we construct the retrieval graph *structurally*, from compressed-domain signals and CLIP embeddings, on CPU, with no neural forward passes during ingest and no proprietary model in the construction path."

The problem: everyone else builds the video's graph by **asking a big commercial AI (like Gemini) to
describe every chunk**. That costs API money for every minute of video, and you cannot run it on your own
machine. IRIS does the opposite: it builds the graph **mechanically** from cheap file-level signals plus
CLIP, on an ordinary CPU, with **zero AI model calls** during the ingest step and **no closed-source
model anywhere** in building.

**Lines 21–27** — "Our central result is an identity rather than an improvement. A block-diagonal construction that enumerates only within-scene node pairs is **bit-identical** to the conventional dense-then-prune construction — identical nodes and edges, identical edge weights at zero tolerance, and bit-identical PageRank across seeds — while visiting only the 0.2% of node pairs it retains rather than the 99.8% that pruning discards. This makes construction ~220× faster (69.47 s → 0.316 s) and ~6.7× smaller in peak memory at a graph of 4,892 nodes [C2.1, C2.2]."

This is the heart of the paper. They are not saying "our graph is better". They are saying **it is the
exact same graph** — down to the last bit, not "approximately equal", not "within rounding error"
(that is what "zero tolerance" means). The old way checks ~12 million frame pairs and throws away 99.8%
of them. The new way only ever looks at the 0.2% it will keep. Result: building takes **0.316 seconds
instead of 69.47 seconds** (220× faster) and uses **6.7× less memory**, on a graph of 4,892 frames.

**Lines 27–32** — "The same block structure separates query-latency scaling: over a 31-clip corpus under real text queries, dense graphs scale with exponent 2.06 (95% CI [2.02, 2.13]) and scene-sparse graphs at 0.83 ([0.80, 0.88]) — and past a certain size the separation becomes a tractability boundary, where dense *retrieval* fails to return within a 3600 s budget on graphs that the sparse path answers in hundredths of a second [C1.1, C1.3]."

Second result, about **searching** speed as videos get bigger. "Exponent 2.06" means dense search time
grows roughly with the **square** of the graph size — double the video, four times the wait. "0.83" means
sparse search grows **slower than linearly** — double the video, less than double the wait. The
confidence intervals do not overlap, so the difference is real and not luck. And beyond a certain size the
dense version does not just get slow — it **never finishes** within an hour, while the sparse version
answers in ~0.01–0.02 seconds. That is not a speed difference; it is a "possible vs impossible" difference.

**Lines 34–39** — "We are explicit about what this does not buy. The retrieval speedup does not reach the user at the sizes we measure: a constant-cost captioning stage dominates the end-to-end path, so end-to-end query time does not improve despite a retrieval-mechanics speedup of three orders of magnitude. Answer quality sits in the weakly-supervised band — held-out Acc@GQA 0.167 with a ~3.4B answerer on CPU — rather than at the agentic state of the art."

The honest half. Even though the search step got **1000× faster**, the *user* feels nothing, because a
different step — writing text captions for the retrieved frames — takes a fixed 40–60 seconds and
swamps everything. And the accuracy is mediocre: 16.7% on the grounded-QA benchmark, which puts them
alongside older "weakly supervised" systems, well below the best modern multi-agent systems.

**Lines 39–43** — "We report both, and we pre-registered kill criteria for two hypotheses we expected to confirm: that codec-derived scene boundaries beat content-blind ones, and that codec-based frame admission beats uniform sampling. Both criteria triggered. Neither where the video is cut nor which frames are kept is doing the work — the block structure is — which is what makes the construction cheap, verifiable, and portable across segmentation policies."

They wrote down, in advance, what result would prove them wrong on two of their own pet ideas —
(a) "our clever way of finding scene cuts is better than just cutting every N seconds", and
(b) "our clever way of picking which frames to keep beats just taking every 10th frame".
**Both were proven wrong.** And they argue this actually makes the paper *stronger*: since none of their
clever tricks matter, the benefit comes purely from the block structure, which means **anyone can copy it
without copying any of their other choices**.

### The short abstract (lines 49–59)

Same content, compressed for venues with a strict 150-word cap. Note it keeps all four elements: the
structural build, the bit-identical result, the scaling separation, **and** the two limitations plus the
two negatives. They did not drop the bad news to save space.

### Notes for co-authors (lines 63–84)

**Lines 65–66** — "**1. Word counts.** Long version ~330 words, short version ~150. Pick per venue; the long version is the default for a systems/applications track."

Use the long one unless the venue forbids it.

**Lines 68–75** — "**2. What the abstract deliberately does not claim**"

Four things left out on purpose, each tied to a decision in the body:

- No claim of "faster query answering" — because §5.3 killed it. The abstract says "retrieval mechanics only" and names the captioning bottleneck out loud.
- No grounding numbers — because of the P1-5 decision. Only Acc@GQA is cited.
- No claim of a "better graph" — the whole framing is *same* graph, and the negatives say their codec signal is not the reason it works.
- It says "~3.4B answerer" instead of claiming a leaderboard rank, because §6.1 is a floor ("we are not broken"), not a ranking ("we are 5th place").

**Lines 77–80** — "**3. The one number to re-verify before submission** is the 0.2% / 99.8% pair-visit figure (11,962,386 visited, 23,571 retained)."

That "99.8% wasted" line is the most quotable sentence in the paper, so check one final time that the
abstract and §4 state it identically.

**Lines 82–84** — "**4. If the mIoP/IoP decision is reversed**, the abstract still needs no change"

Because the abstract never mentioned those metrics, a later change of mind in §6 will not force an abstract
rewrite. Deliberate design: claim the minimum, and nothing upstream breaks.

---
# FILE 3 — `01_introduction.md` (139 lines)

*What it is:* §1 of the paper — the opening chapter that sets up the problem, states the results, and
admits the limits up front.

**Line 1** — `# §1 Introduction — full draft v1 (2026-08-15)`

First draft, 15 Aug 2026. Not yet revised.

**Lines 3–4** — "Verified from disk: `blockdiag_gate_and_savings_summary.md`, `scaling_curve_v3.md`, `e2e_speedup.md`, `MLVU_ablation_long_trimmed.md`. Ledger tags inline."

Every number here was read out of an actual result file on the hard drive, not from a summary or memory.
The four files named are the sources.

**Line 5** — "`**[TODO]**` = genuine gap; do not fill from memory."

Same rule as the README.

**Lines 7–9** — "Drafting principle for this section: the introduction promises exactly what §4–§7 deliver, including the negatives. A reader who stops after §1 should have an accurate picture of the contribution, not an optimistic one."

The rule they set themselves: the intro must not oversell. If someone reads only page 1 and walks away,
their impression must still be correct.

### Opening problem statement

**Lines 15–19** — "Answering questions about long video requires structure. A single hour of footage at modest sampling rates yields tens of thousands of candidate frames, and flat retrieval over that pool becomes intractable well before it becomes inaccurate. The now-standard response is to build an intermediate representation — a graph over frames, shots, or scenes — and retrieve against it."

Why this problem exists: one hour of video = tens of thousands of frames. If you just search all of them
in a flat list, you run out of *time and memory* long before accuracy is your problem. So everyone builds
an intermediate structure (a graph) and searches that instead.

**Lines 21–29** — "The prevailing way to build that graph is to ask a frontier multimodal model to write it. Recent systems prompt a proprietary model once per fixed-duration chunk to emit a symbolic scene description, then reason over the resulting text **[TODO: cite EgoSG and at least one other]**. This works, and it produces representations rich enough to support symbolic reasoning. But it makes graph construction an API-metered operation whose cost scales with video duration, it places a proprietary dependency at the base of the pipeline, and — as the authors of at least one such system report — it does not degrade gracefully to open-source models. For a surveillance archive, a personal video library, or any setting where footage cannot leave the premises, this is a poor foundation."

The competition's approach and its three flaws:

1. **Cost scales with video length** — every extra minute of video is another paid API call.
2. **Proprietary dependency at the base** — if the vendor changes or shuts down the model, your whole system breaks.
3. **Does not work with open models** — the competitors themselves admit swapping in an open-source model produces bad graphs.

Plus a privacy point: for CCTV footage or personal video, you often *cannot legally or practically* send
the video to an external API. The `[TODO]` marks that they still have to add the actual citations.

**Lines 31–35** — "We take a different position. **For retrieval, the graph does not need to be semantically parsed. It needs to be structurally sound and cheap.** We build a scene-sparse graph over surviving frames using compressed-domain signals and CLIP embeddings, on CPU, with no neural forward passes during ingest [C5.1] and no proprietary model anywhere in the construction path."

Their thesis in one sentence: **if all you want to do is *find* the right frames, the graph does not need
to understand the video.** It just needs to be correctly shaped and cheap. So: build it from cheap file
signals plus CLIP, on CPU, with no neural network runs at ingest.

### The construction result (lines 37–53)

**Lines 39–45** — "Sparsifying a graph invites an obvious objection: what was lost? Our answer is nothing, and we mean it literally. The scene-sparse graph contains only within-scene edges, so the conventional construction — materialise the dense graph, then prune across scenes — spends almost all of its work on edges it will discard. At N=4,892 survivors over 528 scenes, it visits 11.96 million candidate pairs to retain 23,571: **99.8% of the pairs it examines are thrown away.** Constructing the diagonal blocks directly visits exactly the pairs it keeps."

The obvious objection to "we made the graph smaller" is "so what did you break?" Their answer: *nothing,
literally nothing*. Reasoning: the target graph only ever had within-scene connections. The old method
computed all ~12 million possible pairs and then deleted 11.94 million of them. That work was pure waste.
The new method skips straight to the 23,571 pairs that survive.

**Lines 47–53** — "The resulting graph is not an approximation of the pruned graph; it is the same graph. We verify this with an identity gate rather than a similarity metric: identical node sets, identical edge sets, zero mismatches on every edge attribute at tolerance 0.0, bit-identical PageRank across all 4,892 nodes, and identical personalised-PageRank ordering and scores across five seeds [C2.1]. A downstream gate over 526 grounded-QA questions produces zero behavioural differences [C2.3]. Construction costs 0.316 s instead of 69.47 s (~220×) and 0.95 GB instead of 6.36 GB (~6.7×) [C2.2]."

"Identity gate, not a similarity metric" is the key phrase. They did not measure "how close are the two
graphs" — they checked "are they *identical*", and the answer is yes on five separate checks:

- same set of frames,
- same set of connections,
- every weight matches at tolerance **0.0** (not even a floating-point rounding difference),
- the PageRank scores for all 4,892 frames come out bit-for-bit the same,
- the query-biased PageRank gives the same ranking and same scores across five different random starting seeds.

Then a sixth check at the far end of the pipeline: run 526 real benchmark questions through both, and the
final behaviour is identical too.

### The scaling result (lines 55–66)

**Lines 57–60** — "Fitting latency against graph size over 31 clips under real text queries, dense graphs scale with exponent 2.063 (95% CI [2.020, 2.125]) while scene-sparse graphs scale at 0.834 ([0.801, 0.884]) — disjoint intervals, with the sparse bound below linear [C1.1, C1.5]."

They measured search time on 31 different video clips of different sizes and fitted a curve. Dense grows
as size squared (2.063). Sparse grows as size^0.834, which is **less than 1**, i.e. sublinear. "Disjoint
intervals" means the two plausible-value ranges do not touch, so the gap is statistically solid.

**Lines 62–66** — "Past a certain size this stops being a matter of speed. Under a uniform 3600 s and 29 GB watchdog, dense retrieval failed to return at all on clips of 6,559 and 13,506 survivors, with memory still climbing at the cap, while sparse retrieval completed the same clips in 0.0104 s and 0.0210 s [C1.3]. We report this as a tractability boundary rather than a speedup ratio, because a censored measurement admits no ratio."

They set a kill switch: any run over 1 hour or 29 GB gets terminated. On two big clips the dense version
**hit the kill switch with memory still rising** — meaning it was nowhere near done. Sparse finished the
same clips in about a hundredth of a second. Crucially, they refuse to say "we are 350,000× faster",
because you cannot divide by a number you never measured. All you can honestly say is: "dense did not
finish."

### What this does not buy (lines 68–85)

**Lines 70–71** — "Two things, and we state them here rather than in a closing limitations paragraph, because a reader deserves the shape of the contribution before the evidence."

They are putting the bad news in the *introduction*, not hiding it in a limitations section at the end.

**Lines 73–79** — "**The retrieval speedup does not reach the user at the sizes we measure.** Measuring the full query path at N=4,892, the end-to-end ratio is 0.778× — the sparse arm is *slower* at the median. Retrieval mechanics shrink from 8.086 s to 0.028 s, but a captioning and verification stage costing 40–63 s dominates the total and is O(top_k) rather than O(N), so it does not shrink with the graph. Sparsifying the graph makes a small term negligible while leaving the largest term untouched. We report the retrieval-mechanics ratios for what they are and do not present them as user-facing latency."

Bad news #1, stated bluntly. Measured end-to-end, the fast version was actually **slower** (0.778× means
it took about 1.29× as long). The searching step dropped from 8 seconds to 0.028 seconds — a huge win —
but the captioning step takes 40–63 seconds and depends on **top_k (the 30 frames you caption)**, not on
**N (graph size)**. So shrinking the graph does not shrink it. Classic Amdahl's law: you optimised the
small part.

**Lines 81–85** — "**Accuracy sits in the weakly-supervised band, not at the state of the art.** On NExT-GQA our held-out Acc@GQA is 0.1667 [0.088, 0.243] with a ~3.4B answerer on CPU [C4.1] — comparable to weakly-supervised baselines and well below current agentic methods. This paper's claim is that a graph costing 0.316 s to build does not degrade answer quality below that band, not that it advances it."

Bad news #2: 16.67% accuracy. The plausible range is wide (8.8% to 24.3%) because the test set is small.
Their claim is defensive, not competitive: "a graph that costs a third of a second to build does not make
your answers *worse* than the older baselines."

### Negative results as contributions (lines 87–100)

**Lines 89–95** — "We pre-registered kill criteria for two hypotheses we expected to confirm, and both triggered. Codec-derived boundary placement does not beat content-blind placement at matched segment count: across four segmentation strategies the differences fall within noise, and on long videos the codec-versus-matched-count difference is +0.088 M-Avg with a 95% CI of [−0.009, +0.204]. Codec-based frame admission is statistically indistinguishable from uniform sampling at matched budget, a result that now holds from three independent directions [C3.2, §7.2]."

Both of their pet hypotheses were killed by their own pre-written rules. On scene-cutting: the codec
method was +0.088 better, but the range [−0.009, +0.204] **includes zero**, meaning "no difference" is
still a plausible explanation — so it does not count. On frame-picking: three separate tests all said
their method ties with just sampling uniformly.

**Lines 97–100** — "These constrain our own claim, and we think they improve it. Neither *where* we place boundaries nor *which* frames we admit is doing the work; the block structure is. A pipeline adopting this construction inherits the cost and tractability properties without adopting our codec signal, our segmentation, or our admission policy."

The silver lining: because none of their extras matter, the result is **portable** — any other team can
take just the block-diagonal trick and get the speed benefit, without buying into anything else IRIS does.

### Contributions list (lines 102–115)

1. **Lines 104–106** — A block-diagonal construction *proven* bit-identical to the old way, via a five-seed identity check and a 526-question end-to-end check, at 220× less time and 6.7× less memory.
2. **Lines 107–109** — Scaling exponents with proper confidence intervals over 31 clips, showing quadratic vs sublinear, plus the point where dense simply stops working.
3. **Lines 110–111** — A training-free, CPU-only ingest path with zero neural calls — and importantly, **verified by instrumenting the running code**, not by someone reading the source and asserting it.
4. **Lines 112–113** — An honest full-pipeline accounting showing where the speedup gets absorbed, including a cost their own sparse method *causes* (the caption-cache penalty).
5. **Lines 114–115** — Two pre-registered negative results showing which parts of the pipeline actually matter.

**Lines 117–118** — "`**[TODO: final paragraph — one-sentence roadmap of §2–§9. Write after §2 and §3 are drafted, so the pointers are accurate.]**`"

Missing: the standard "the rest of this paper is organised as follows" paragraph. Deliberately written
last so the section pointers are right.

### Notes for co-authors (lines 122–139)

**Lines 124–126** — Keep the "99.8% of pairs discarded" line early; it is the single most persuasive sentence available and it is verified.

**Lines 127–130** — "**Resist moving the negatives later.** ... A reviewer who discovers the 0.778× end-to-end result on their own in §5, after an introduction that implied otherwise, will read everything preceding it as overclaiming."

Strategic warning: someone will want to move the bad news to the end and lead with "220×!". Do not. If a
reviewer *discovers* the disappointing result themselves after an upbeat intro, they will distrust the
entire paper.

**Lines 131–133** — Framing negatives as *delimiting* the claim (drawing its boundary) rather than as
failures. The honest version is also the stronger one because it makes the contribution reusable.

**Lines 134–136** — "**Citations needed:** EgoSG and one comparator ... the 'open-source MLLMs cannot reliably generate these graphs' statement must be attributed precisely to the paper that reports it, not paraphrased into a general claim."

Do not turn one paper's specific finding into a sweeping claim about the whole field. Cite exactly who said it.

**Lines 137–139** — "**Do not reintroduce codec framing here.** Earlier drafts of this project led with codec signals as a saliency mechanism. §7 shows that claim does not survive a matched control; §1 must not promise what §7 retracts."

The project used to be *about* codec signals. That story is dead. Do not let it creep back into the intro,
or §1 and §7 will contradict each other.

---
# FILE 4 — `02_related_work.md` (188 lines)

*What it is:* §2 — the chapter that positions IRIS against everything else already published.

**Line 1** — `# §2 Related Work — draft v2 (2026-08-19, P0 edits applied)`

Second version; the P0-3 codec-cost correction has been made.

**Lines 3–6** — "EgoSG facts verified from the paper itself (arXiv 2606.25842v2): schema, generation procedure, implementation details, Tables 2/3/5, runtime analysis. NExT-GQA, MUPA, LangRepo, SeViLA figures verified from primary sources."

Every claim about a competitor was checked in that competitor's own paper — not taken from a blog post,
a summary, or another paper's quotation of it. This matters because papers do misquote each other (they
catch one such case later).

**Lines 8–10** — "**Drafting principle:** this section positions us against EgoSG on *construction cost*, which is where we differ. It must not imply we compete on symbolic reasoning, which we do not do at all."

The one rule for this section: compare on **build cost only**. Do not accidentally suggest IRIS competes
on *understanding* the video, because it genuinely does not.

### 2.1 The token bottleneck (lines 16–29)

**Lines 18–23** — "Multimodal LLMs are bounded by input token capacity, so applying them directly to long video forces aggressive frame subsampling ... at 1 FPS, published per-question frame budgets range from 32 frames (InternVL3) and 180 (VideoLLaMA3) to 512 (Qwen2.5-VL) and 3,900 (Gemini Flash 2.0) — against the tens of thousands of frames in an hour of footage. Every approach to long-video QA is, in some form, a strategy for deciding what to discard."

The fundamental constraint: AI models can only read so much at once. Even the most generous model
(Gemini) accepts 3,900 frames, but one hour at 1 frame/second is 3,600 frames and real footage is far
longer. So **every** system in this field is really just a different answer to "what do we throw away?"

**Lines 25–29** — "Broadly, three families have emerged: **subsample and hope**, which accepts the loss; **retrieve then answer**, which selects evidence per query; and **build an intermediate representation**, which converts the video once into a compact structure that later queries reuse. Our work sits in the third family, and borrows from the second at query time."

Three schools of thought, named bluntly ("subsample and hope" is a jab at the naive approach). IRIS is
family 3 (build a structure once) with family 2's technique (search it per query).

### 2.2 Graph-structured representations — the EgoSG comparison (lines 31–92)

**Lines 33–41** — "The representative recent system, and our closest point of comparison, is **EgoSG** [Taluzzi et al., 2026]. It partitions video into non-overlapping fixed-length chunks (Δt = 60 s, processed at 1 FPS) and prompts a frontier MLLM — Gemini Flash 2.0 — to emit a symbolic scene graph per chunk: environmental elements, dynamic objects, spatial relations, and timestamped action hyperedges, serialized as text. Graphs are built iteratively, with each chunk's graph produced by prompting the model to *update* the previous one, so the final graph summarises the whole video. On HD-EPIC VQA (1,250 questions across 25 prototypes) this improves over raw-video input for most models, by 3.22 points for Gemini itself and 5.60 for Qwen2.5-VL-14B."

How the main rival works: chop into 60-second chunks, ask Gemini to describe each one as a structured
text graph (objects, where they are, what happens when), and each chunk's description is built by asking
the model to *update* the previous chunk's description. Their results are genuinely good: +3.22 and +5.60
accuracy points.

**Lines 43–44** — "We differ from EgoSG on four axes, and it is worth being precise about which of them are genuine contrasts and which are simply different problems."

Being careful: some of these differences mean "we are better", others just mean "we do a different job".

**Lines 46–52 — axis (1): what the graph is for.** EgoSG's graph is text an AI reasons over. IRIS's is a
numeric structure for ranking frames. "**These are not substitutes.**" EgoSG can answer "what step
happened between 32:10 and 32:38" from its symbols alone; IRIS **cannot**, because it stores no symbols
at all. Conversely IRIS can retrieve individual frames, which EgoSG's text summary has thrown away. So:
compare on cost, not on power. This paragraph exists to stop a reviewer saying "your system is much
worse than EgoSG" — IRIS never claimed that ground.

**Lines 54–61 — axis (2): how construction scales.** EgoSG costs ~5.7 s per minute of video, growing
linearly, and is billed by a commercial API. Two things make that worse:
- **It is inherently sequential.** Chunk 5 needs chunk 4's output first. So you cannot speed it up by throwing 20 machines at it.
- **It only works with the proprietary model.** The authors tried open models and got unreliable graphs — and said so in their own limitations.

**Lines 63–65** — "Our construction has neither property. Scenes are independent, so the block structure is embarrassingly parallel by definition, and no model — proprietary or otherwise — participates in construction. Building the graph at N=4,892 costs 0.316 s on CPU (§4.2)."

IRIS's scenes do not depend on each other, so all of them can be built at the same time on different
cores ("embarrassingly parallel" is the technical term for "trivially splittable"). And no AI is
involved at all.

**Lines 67–72 — axis (3): what guarantee is possible.** EgoSG's own manual audit of five clips found
~5% of nodes/relations wrong, 15.5% invented action edges, and 13.7% of objects missed. The paper is
careful here: "This is not a criticism — it is the expected behaviour of a generative construction, and
their results hold despite it." That is deliberately generous framing.

**Lines 74–80** — "But it does mean no correctness guarantee is available for the constructed artifact. Ours is a different situation: because our construction is structural, we can verify it exactly, and we do (§4.1). **We are careful about what this guarantee covers.** It establishes that our block-diagonal construction produces the identical graph to our own dense-then-prune reference — a *fidelity* guarantee about construction, not a claim that the resulting graph is semantically correct. A structural construction cannot hallucinate an object, but neither can it recognise one."

The crucial self-limiting sentence. Their proof says: *our fast build matches our own slow build*. It does
**not** say the graph is a true description of the video. That last line is the honest summary: because
IRIS never tries to name objects, it can never invent one — but it also never identifies one.

**Lines 82–87 — axis (4): what is measured.** EgoSG measures tokens and estimated FLOPs, spread over the
~22 questions asked per video. IRIS measures wall-clock and memory. Both papers use an "amortisation"
argument (spread the one-time cost over many uses) — theirs over questions, IRIS's over a caption cache
in a session — and in both cases the per-query cost looks very different from the per-video cost.

**Lines 89–92** — `**[TODO: at least one further graph-based long-video system ... so EgoSG is not carrying the entire family.]**`

A gap: right now one competitor represents an entire research family, which is thin. Two candidates are
named, with the note "verify scope before citing" — check they actually do the same thing before citing.

### 2.3 Grounded video QA (lines 94–111)

**Lines 96–100** — "**NExT-GQA** [Xiao et al., 2023] introduced the requirement that a system not only answer correctly but point at the evidence, reporting Acc@GQA alongside grounding metrics (mIoP, IoP@0.5, mIoU). Its central finding — that models achieving strong answer accuracy often ground poorly, i.e. are right for the wrong reasons — is the reason we report grounded accuracy rather than answer accuracy alone (§6.1)."

Why this benchmark exists: models were scoring well on video questions while looking at the wrong part of
the video — guessing from language priors, essentially. NExT-GQA forces you to *show your work*. IRIS
reports the strict grounded score for that reason.

**Lines 102–105** — "The weakly-supervised band on that benchmark is occupied by Temp[CLIP] with NG+ (16.0 Acc@GQA), SeViLA as reproduced by the benchmark authors (16.6), LangRepo (17.1), and FrozenBiLM with NG+ (17.5). **[TODO: verify the two NG+ variants against Xiao et al. Table 3 directly — currently taken from the benchmark table via our own ledger.]**"

The neighbourhood IRIS lands in: roughly 16–17.5%. The TODO admits two of those numbers came second-hand
through their own ledger and should be checked in the original table.

**Lines 107–111** — "Two conventions matter for reading any of these numbers. First, published figures are computed on the full 5,553-question test set, whereas ours is a 120-question held-out split (§6.1). Second, IoP admits more than one definition, and the union convention is biased upward relative to the benchmark's max-per-span convention — a distinction we flag because it determines whether grounding figures are comparable at all."

Two apples-to-oranges warnings: (a) everyone else tested on 5,553 questions, IRIS on 120 — so IRIS's
number is much noisier; (b) "IoP" can be computed two ways, and IRIS's way (union) inflates the score, so
the numbers are not directly comparable. This is the whole reason they end up omitting those metrics.

### 2.4 Agentic methods (lines 113–123)

**Lines 115–120** — "A more recent line attaches an explicit temporal grounder to the QA pipeline, often with multiple cooperating agents or roles. **MUPA** reports 28.7 Acc@GQA at 2B parameters and 30.3 at 7B; **VideoMind** reports 25.2 at 2B. These define the current accuracy frontier on NExT-GQA, and **we do not compete with them on accuracy** ... We cite them to situate that gap honestly rather than to select a weaker comparison set."

The current best systems get 25–30%. IRIS gets 16.7%. They cite the strong competitors on purpose — the
sleazy move would be to only compare against weak systems, and they explicitly refuse it.

**Lines 122–123** — "*(Note for co-authors: MUPA's abstract misstates its own Table 1 — cite the table: 28.7 / 39.1 / 38.7, not 29.0 / 39.7.)*"

A real catch: MUPA's own abstract disagrees with MUPA's own table. Always cite the table, since that is
where the actual measured numbers live.

### 2.5 Compressed-domain analysis (lines 125–145)

**Lines 127–138** — "Using signals available in the encoded bitstream — motion vectors, residual energy, packet size — to avoid full decode is a long-standing idea in video analysis **[TODO: cite the classical line ... and the recent codec-aware video-LM work]**. We use such signals for scene segmentation and edge weighting. Both are cheap in *marginal* terms rather than absolute ones, and the distinction matters: edge weighting from codec statistics costs an order of magnitude less than pixel-difference or semantic weighting on identical topology (0.017 s vs 0.119 s and 0.122 s at N=4,892), while extracting those statistics requires a demux pass that is not itself cheap in isolation. That pass is the one ingest already performs for frame selection, so its cost attributable to graph construction is approximately zero — but we state the amortisation rather than quoting the marginal figure alone."

This is the **P0-3 corrected paragraph**. The distinction:

- **Marginal cost** = the extra cost of doing this given you were already doing the other work. Tiny (0.017 s vs 0.119/0.122 s).
- **Absolute cost** = what it costs from scratch. Not tiny at all (the working notes reveal 323 seconds for extraction on the flagship clip).

Their defence: that expensive extraction pass happens anyway during ingest for frame selection, so
charging it to graph construction would be double-counting. But — and this is the correction — they must
say this out loud rather than just quoting the pretty 0.017 s number.

**Lines 140–145** — "**We make a deliberately modest claim here, and report a negative result that constrains it.** At matched segment count, codec-derived boundary placement performs within noise of content-blind alternatives (§7.1), and codec-based frame admission is statistically indistinguishable from uniform sampling at matched budget (§7.2). Compressed-domain signals in our pipeline are a *cheap* source of structure, not an *informative* one, and we present them as such."

The final position on codec signals, in six words: **cheap, not smart.** They give you *some* structure
for almost nothing, but the structure they give is no better than what you would get by cutting the video
arbitrarily.

### 2.6 Positioning (lines 147–157)

**Lines 149–154** — "Against EgoSG and its family, we replace a frontier-model-generated symbolic graph with a structurally-constructed embedding graph: far cheaper, verifiable, parallel, locally runnable — and semantically poorer. Against grounded-QA baselines, we land in the weakly-supervised band while training nothing and running on CPU. Against the agentic frontier, we are a band behind on accuracy and orders of magnitude ahead on construction cost."

A three-way scorecard where every row includes the loss as well as the win. Note "**and semantically
poorer**" sitting at the end of the list of advantages.

**Lines 156–157** — "The claim we make is narrow and, we think, useful: **for retrieval over long video, the intermediate graph does not have to be expensive, and does not have to be generated.**"

The whole paper in one sentence.

### Notes for co-authors (lines 161–188)

**Lines 163–167** — "**1. The sequential-construction point in §2.2(2) is ours to make and is verified.**" — The "EgoSG cannot be parallelised" observation is a fair, factual, sourced criticism (it follows from their own §3.2). But: "Keep it factual — no editorialising about the design choice." State the fact, do not sneer.

**Lines 169–173** — "**2. Do not sharpen the graph-quality paragraph into an attack.**" — The error-rate paragraph must read as "generative construction cannot be verified", not "their system is bad". Then a strategic point: "If this paragraph reads as a hit, it will cost us more than it gains." Attacking a rival makes reviewers hostile.

**Lines 175–177** — "**3. The guarantee scoping in §2.2(3) is load-bearing.** Our identity gate proves we match *our own reference construction*. A careless sentence here ('our graph is verified correct') would be an overclaim of exactly the kind §7 exists to avoid."

The single most dangerous possible sentence in the paper is "our graph is verified correct". It is
subtly, importantly false — and it is exactly the type of overclaim the whole paper is structured to
avoid.

**Lines 179–182** — "**4. Three literature gaps remain**" — a second graph system (§2.2), the NG+ verification (§2.3), and the compressed-domain citations (§2.5). The last is biggest: nobody has reviewed the 2026 codec-aware literature yet, and §2.5 currently waves at it with no citations.

**Lines 184–188** — "**5. Their oracle is worth one sentence if space allows.** EgoSG's ablation reports ground-truth narrations at 59.53 against their own 42.70 — i.e. the symbolic representation captures well under half the available headroom."

A neat observation from EgoSG's own data: if you give their system *perfect human descriptions* instead
of Gemini's, it scores 59.53 vs their actual 42.70. So the whole approach captures less than half of what
is theoretically reachable — a fair, sourced comment on how much room the field has left. Marked as "not
a criticism of their contribution".

---
# FILE 5 — `03_method.md` (189 lines)

*What it is:* §3 — how the system actually works, written from the live source code.

**Lines 1–5** — "`# §3 Method — draft v2 (2026-08-19, P0 edits applied)`. Drafted from the live code: `iris/iris_config.py`, `configs/default_iris_config.json`, `iris/ingest.py`."

Version 2, written by reading the real code files rather than from memory or design docs.

**Lines 7–8** — "**Two discrepancies surfaced while drafting — see 'Notes for co-authors' at the end. One of them means a caveat currently written into §5.1 may be stated backwards.**"

A warning at the top: reading the code turned up two contradictions between what the paper says and what
the code does, and one of them means a disclaimer in §5.1 might be **exactly reversed**.

**Lines 14–17** — "IRIS ingests a video once into a compact index, then answers arbitrary text queries against that index. This section describes the pipeline; §4 and §5 measure it. Throughout, **N** denotes the number of *surviving* frames after admission, not the number of frames in the container — the distinction matters for every scaling figure we report."

The shape of the system: read the video once, build an index, then answer unlimited questions cheaply.
And a definition that matters everywhere: **N = frames kept, not frames in the file.** Since they keep
only ~11%, confusing the two would make every number wrong by ~9×.

### 3.1 Ingest and frame admission (lines 19–39)

**Lines 21–27** — "Ingest demuxes the video and computes, per frame, a scalar **action score** combining luma difference, motion energy, and luma entropy at weights 0.5 / 0.3 / 0.2. Frames are assigned to tiers by thresholding this signal (`salient_thresh` 0.35, `candidate_thresh` 0.08) with adaptive per-video thresholding enabled, and local maxima are marked as peaks via `argrelextrema` with a window of 3. Admitted frames — the survivors — are the input to everything downstream; production retention across the annotated corpus falls between 10.41% and 11.14% [C3.4]."

How frames get chosen:

- **demux** = split the video container into its raw streams without fully decoding pictures.
- Each frame gets an "action score" = 50% brightness change + 30% motion + 20% brightness complexity.
- Frames above 0.35 are "salient", above 0.08 are "candidates". "Adaptive" means these thresholds shift per video, so a dark quiet video is not scored against a bright busy one.
- `argrelextrema` with window 3 finds local peaks — a frame more active than its immediate neighbours.
- Net result: about **10.4%–11.1% of frames survive**. Roughly 9 out of 10 frames are discarded.

**Lines 29–33** — "**No neural network runs during ingest.** We verify this by instrumentation rather than inspection: monkeypatching `torch.nn.Module.__call__` for the duration of every `parse_video()` call and counting invocations across 32 videos yields exactly zero [C5.1]. Ingest costs 2.945 s mean wall time (min 0.337, max 15.474) at 530 MB mean peak RSS (max 1.291 GB), CPU-only [C5.2]."

This is the good methodology bit. Instead of saying "we looked at the code and there is no model call",
they **replaced the function that every PyTorch model must call** with a counter, ran 32 videos, and the
counter read **exactly zero**. That is proof by measurement, not by assertion. Cost: ~3 seconds average
per video, 530 MB memory, no GPU. ("RSS" = the actual RAM the process was holding.)

**Lines 35–39** — "CLIP embeddings (ViT-B/32) are computed for admitted frames after this stage and are what the neural-forward-pass claim excludes; the claim is specific to `parse_video`. **[TODO: state precisely where embedding happens relative to `parse_video`, and confirm the CPU cost figures above do or do not include it. This is the single most attackable sentence in §3.]**"

An important honesty carve-out. CLIP **is** a neural network, and it **does** run — just after
`parse_video`, not inside it. So the "zero neural passes" claim is narrowly scoped. They flag this as
**the single most attackable sentence in §3**, because a reviewer will ask "so does your 2.945 s include
CLIP or not?" and right now they do not know.

### 3.2 Scene segmentation (lines 41–52)

**Lines 43–47** — "Survivors are partitioned into scenes. The default rule derives boundaries from valleys in the packet-size curve obtained directly from the container — no pixel decode, no model call. Segmentation is exposed as a configuration axis with four settings — `codec`, `fixed_count`, `fixed_seconds`, and `fixed_time_matched` — which are precisely the four arms compared in §7.1."

How scenes are found: in a compressed video, a scene change makes a big packet (lots of new information)
while similar frames make small packets. So dips ("valleys") in packet size mark scene structure — and
you can read that straight from the file without decoding a single picture. Four alternative rules are
switchable, which is what makes the §7.1 experiment possible.

**Lines 49–52** — "**We present the codec rule as one cheap option, not a superior one.** §7.1 shows that at matched segment count, boundary placement is within noise across all four rules. The property the pipeline depends on is that survivors are partitioned into scenes at all, not that the partition is content-adaptive."

Deliberately deflated. **What matters is that you cut the video into scenes at all — not where you cut.**

### 3.3 The scene-sparse graph (lines 54–77)

**Lines 56–59** — "Let the S scenes partition the N survivors, with scene *i* holding *nᵢ* survivors. The scene-sparse graph connects every pair of survivors within a scene and no pair across scenes, giving an adjacency that is block-diagonal under a scene-ordered permutation. Edges carry semantic, motion, and temporal weight components."

Formal statement of the design. If you sort the frames so all of scene 1 comes first, then scene 2, etc.,
and draw the connection table, you get solid squares along the diagonal and empty space everywhere else —
hence "block-diagonal". Each connection carries three kinds of weight: meaning-similarity, motion, and
time-closeness.

**Lines 61–69** — "The edge count is therefore |E| = Σᵢ nᵢ(nᵢ−1)/2 against N(N−1)/2 for the dense graph. ... At N=4,892 over S=528 scenes the two quantities are 23,571 and 11,962,386 — the pruning construction discards **99.8%** of the pairs it examines, while block-diagonal construction visits exactly as many pairs as it retains."

The arithmetic behind the whole paper. `n(n−1)/2` is just "how many ways to pick 2 things out of n".

- Dense: 4,892 frames → 4892×4891/2 = **11,962,386** pairs.
- Sparse: add up that formula *within each of the 528 scenes* → **23,571** pairs.

Because the formula is quadratic, splitting into many small groups collapses the total dramatically.
528 scenes means average scene size ~9 frames, and 9 frames only make 36 pairs.

**Lines 71–73** — "Because the pruned graph and the block-diagonal graph are the same object, this is a change of construction order, not of representation. §4.1 verifies that claim empirically rather than resting on the argument."

The key insight in one line: **nothing about the data structure changed — only the order of operations.**
And they verified it by experiment instead of trusting the argument, which is the right instinct.

**Lines 75–77** — "**[TODO: state the weight formulas for the semantic / motion / temporal components, and whether any depends on cross-scene context (if any did, the identity result would be non-trivial in a way §4.1 should say explicitly).]**"

A sharp, self-aware TODO. If any weight formula secretly needed information from *other* scenes (e.g. a
global average), then skipping those scenes would change the answer — and the fact that it does not
would be a much more surprising result deserving explanation. They have not confirmed this either way.

### 3.4 Retrieval (lines 79–102)

**Lines 81–93** — the four-stage query pipeline:

1. **Scene shortlist** — every scene gets a single average embedding ("centroid"). Compare the question to those 528 averages and keep only the top `w`, where `w = max(4, ⌈√S⌉)`. With 528 scenes, √528 ≈ 23, so ~23 scenes proceed and ~505 are dropped immediately. This is what makes search fast.
2. **Descent** — inside those scenes, rank frames using personalised PageRank seeded from the query, with damping 0.5, blending semantic rank and codec rank 50/50 (λ = 0.5). "Damping 0.5" controls how far influence spreads through the graph.
3. **Shortcut** — if the best scene beats the second-best by more than 0.015, skip the graph entirely and just return that scene's representative frames. A speed hack.
4. **Top-k, captioning, answering** — take the best 30 frames, write text captions for them, hand those to the ~3.4B-parameter `granite4:micro` model (Q4_K_M = compressed to 4 bits so it fits and runs on CPU).

**Lines 95–102** — "Two properties of this design are load-bearing for later sections. The **shortlist** makes retrieval sublinear by construction — it is why §5.1's exponent is below 1 — but it is also a hard recall gate: a scene excluded here cannot contribute a frame downstream, and we report the consequence in §8. The **shortcut** is a latency optimisation that bypasses the graph entirely; it is the mechanism behind the guard violations noted in §5.1, and we believe (but have not confirmed) that it fires more often at small S, where scene-centroid margins are wider. **[TODO: confirm or refute this directly ...]**"

Two honest admissions:

- The shortlist is **why** the 0.83 exponent is below 1 — it is not magic, it is because they throw away 95% of scenes before looking properly. And if the right answer is in a discarded scene, it is gone forever. That is a hard ceiling on recall.
- The shortcut is what caused two experiments to violate their own pre-registered rules. Their theory (untested) is that with few scenes, the gaps between scene scores are bigger, so the shortcut triggers more. They flag it as worth one hour of experiment to turn "unexplained bug" into "described behaviour".

### 3.5 Configuration and provenance (lines 104–138)

**Lines 106–115** — the per-experiment configuration table

This is the **P0-1 fix**, the single biggest upgrade in the revision. Instead of pretending there was one
frozen configuration, they list exactly which graph settings each experiment used:

| experiment | graph_mode | graph_edge_mode |
|---|---|---|
| §4.1 identity gate, §4.2 build savings | scene_sparse | fully_connected ↔ block_diagonal |
| §5.1–5.2 scaling, tractability | flat / scene_sparse | fully_connected |
| §5.3 end-to-end, §5.4 caption stage | scene_sparse | hierarchical_sparse |
| §6.2 MLVU, §7.1 segmentation ablation | scene_sparse | hierarchical_sparse |
| §6.1 NExT-GQA grounded QA | flat | — |

Why this looks bad at first glance: the 220× result was measured in one mode, but the accuracy results
were measured in a *different* mode. A reviewer would immediately ask "so you never actually tested
accuracy on the fast configuration?"

**Lines 119–127** — "**All three edge modes produce within-scene-only graphs under `graph_mode='scene_sparse'`.** `fully_connected` and `block_diagonal` connect every intra-scene pair; `hierarchical_sparse` builds a tiered edge set (temporal, hierarchy, salient-semantic, motion-neighbour) and then removes every cross-scene edge. The modes therefore differ in the *intra-scene edge formula*, not in the block structure. Since the block structure is what determines construction cost (§4) and query scaling (§5.1), those results characterise a property common to every configuration reported in this paper. The exponents in §5.1 were measured under `fully_connected` and transfer to `block_diagonal` by the identity established in §4.1."

The answer to that objection. All three modes produce **block-diagonal** graphs — they only differ in how
they wire frames *within* a scene. Since the cost and scaling results depend entirely on the *block
structure* (which is shared), those results apply to all configurations. This paragraph is doing a lot of
work; without it the paper has a hole.

**Lines 129–132** — "**Under `graph_mode='flat'` the block-diagonal path is unreachable**, because the flat construction path never partitions nodes into groups. The §6.1 grounded-QA results are therefore a dense-graph measurement, reported as a correctness floor rather than as a measurement of the sparse construction."

Full admission: the headline accuracy number (16.67%) was measured on the **dense** graph, not the sparse
one. They cannot pretend otherwise, so they reframe: it is a "floor" showing the pipeline works, not a
measurement of the sparse construction.

**Lines 134–135** — "Per-experiment configuration hashes are recorded in the artifacts and indexed in Appendix A; those hashes, not this table, are the reproducibility anchor."

The table can drift out of date; the recorded hashes cannot. Trust the hashes.

**Lines 137–138** — TODO on the salience weights, again flagging §5.1's caveat may be backwards.

### Notes for co-authors (lines 142–174)

**Lines 144–157 — note 1: the "frozen production weights" problem.** The paper apologises that the
scaling corpus used weights (0.5, 0.3, 0.2) "rather than the frozen production default (0.8, 0.1, 0.1)".
But reading the code: the dataclass defaults **are** 0.5/0.3/0.2, and the shipped JSON config does not
override them (it only sets `salient_thresh`, `candidate_thresh`, `alpha`, `beta`, `peak_order`,
`captioner_backend`). So **0.8/0.1/0.1 appears nowhere in the codebase.** Either it exists outside the
repo (a tuned config, or a team decision never committed), or the caveat is written backwards. The
punchline: "as written, we may be disclaiming a deviation that did not occur, which is its own kind of
error." Apologising for a mistake you did not make is also a form of inaccuracy.

**Lines 159–165 — note 2: two more config disagreements.** The shipped JSON says the captioner is
`minicpm`, the code default says `moondream`, and the §5.3 measurements report **BLIP** — three different
answers. Also `beta` is 0.6 in JSON vs 0.3 in code. The beta one is *probably* harmless because that
parameter is only used in `legacy` ranking mode and they use `ppr` — "but 'probably inert' is not what we
want to write in a reproducibility appendix."

**Lines 167–170 — note 3:** the shortcut experiment is worth ~1 hour and changes no headline number, but
converts a mystery into a description.

**Lines 172–174 — note 4:** "Do not let §3.2 drift back toward advocacy. The natural authorial instinct
is to justify the codec rule at length here. §7.1 does not support that." Resist the urge to defend your
favourite idea in the method section when your own results section demolishes it.

### P0 edit log (lines 178–189)

**Lines 180–187** — What P0-1 changed and how it was verified in source:
- `mlvu_eval.py:454` and `e2e_speedup_ab.py`'s BASE dict both **omit** `graph_edge_mode` → so those runs silently used the default, `hierarchical_sparse`. That is how they knew.
- The scaling census **excluded two clips specifically for not being `fully_connected`** — proof the rest were.
- `l2_asphodel._update_all_edge_weights` prunes all cross-group edges whenever groups are set and the mode is not `block_diagonal` — which is *why* all three modes end up within-scene-only.

**Lines 188–189** — Still open in this section: the salience-weight question and the CLIP-placement TODO. Neither is P0 (paper-breaking), so they can wait.

---
# FILE 6 — `04_05_construction_and_scaling.md` (273 lines)

*What it is:* §4 and §5 — the evidence chapters. The README says this file **"carries the paper"**.

**Lines 3–5** — "Numbers verified against `eval_results/scaling_curve_v3.md` and `eval_results/e2e_speedup.md` on disk, not from summaries."

Read from the raw result files, not from any summary. The distinction is stressed because summaries drop
caveats.

**Lines 7–11** — "**Corrections applied vs. earlier drafts:** (i) the e2e run's own retrieval ratio is ~291×, not 1,104× — the two numbers come from different query types (real CLIP text vs synthetic sampled-embedding) and must not be conflated; (ii) the full-range scene-sparse exponent (0.497) differs sharply from the headline (0.834) — both are reported below, and the difference is explained rather than hidden."

Two corrections up front:

1. Two different "how much faster is retrieval" numbers exist — 291× and 1,104× — because one used **real
   text questions** and the other used **synthetic made-up query vectors**. Mixing them up would be
   dishonest, so both are labelled.
2. Their sparse scaling exponent is 0.497 if you use all data points and 0.834 if you use only the big
   graphs. That is a big difference, and they publish both rather than the flattering one.

## §4 Construction Cost

**Lines 17–20** — "Our central claim is not that the sparse graph is a *better* graph. It is that it is the *same* graph, built far more cheaply. We therefore begin with an identity result and only then report savings; the order matters, because a construction speedup is uninteresting if it silently changes what is built."

Structural choice explained: **prove correctness first, then claim speed.** A speedup that quietly
changes the output is not a speedup, it is a bug.

### 4.1 The identity gate (lines 22–54)

**Lines 24–26** — "We compare two construction paths that produce a scene-sparse graph: the reference path, which materialises the dense N×N graph and prunes cross-scene edges, and the block-diagonal path, which materialises only the within-scene blocks."

Two roads, same destination. Path A: build everything, delete most. Path B: build only what you keep.

**Lines 28–36** — the five identity checks at N=4,892 over 528 scenes (the VIRAT dataset):

- **Edge count** 23,571 — matching *three* independent things: the mathematical prediction, path A, and path B. Matching the theory too is a real check that the formula is right.
- **Node sets identical**, and zero edges present in one graph but not the other, **in either direction**. (Checking both directions matters — otherwise a subset would pass.)
- **Edge attributes** — `weight`, `semantic_weight`, `motion_weight`, `temporal_weight`, `edge_type` — zero mismatches at tolerance **0.0**. This is the strongest form. Normally you would allow tiny float differences; they allowed none.
- **PageRank bit-identical** across all 4,892 nodes — the derived ranking is identical too, not just the inputs.
- **Personalised PageRank** top-20 order and exact scores identical **across five seeds** — five different random starting points, all identical.

**Lines 38–42** — "Because graph identity does not by itself guarantee identical downstream behaviour, we additionally gate end-of-pipeline. Over 526 NExT-GQA validation questions, the `fully_connected` and `block_diagonal` construction paths produce bit-identical retrieval — identical retrieved order, peak frame, predicted span, IoP, and peak-in-gold on every question (peak-in-gold 0.3175 and mIoP 0.3140 under both) [C2.3]."

An extra layer of safety: even if the graphs match, maybe something downstream behaves differently. So
they ran 526 real questions through both and got identical results on every single one — same frames in
the same order, same predicted time window, same scores.

**Lines 44–48** — "We are precise about what this gate establishes: it is an **equivalence proof between the two construction paths the change concerns**, not a re-run of a previously committed result. No committed grounding number was produced under `scene_sparse` with `fully_connected`; our committed scene-sparse arms use the `hierarchical_sparse` edge formula, which the block-diagonal construction does not target (§3.5)."

This is the **P0-2 fix**. The earlier draft made this sound like "we re-ran our published accuracy and it
was unchanged". It is not that. It proves the two *build paths* agree — but the paper's actual published
accuracy numbers were produced under a **third** mode that the block-diagonal path does not even touch.
Technically true either way, but the old wording would be read as the stronger claim.

**Lines 50–54** — "We state this as an identity rather than an approximation because the block-diagonal construction is not an approximation. Cross-scene edges are absent from the scene-sparse graph by definition; the reference path computes them and then discards them. The block-diagonal path simply never computes them. **[TODO: formal statement in §3.3 — Σ_s |S_s|² vs N², with the balanced-scene case.]**"

Restating the logic: nothing is approximated because nothing is dropped that was ever wanted. TODO: add
the formal maths — total work ~ sum of scene-sizes-squared versus N-squared, plus what happens in the
tidy case where all scenes are equal size (in which case the saving is exactly a factor of S).

### 4.2 Savings (lines 56–66)

| | reference (dense-then-prune) | block-diagonal | ratio |
|---|---|---|---|
| wall-clock | 69.47 s | 0.316 s | ~220× |
| peak RSS | 6.36 GB | 0.95 GB | ~6.7× |

**Lines 63–66** — "**This isolates the `_build_graph` stage with frames and embeddings already cached; it is not a full-ingest figure.** The ingest path that produces those inputs is reported separately (§3.1): 2.945 s mean wall time and 530 MB mean peak RSS over a 32-video stratified sample, CPU-only, with zero neural forward passes [C5.1, C5.2]."

Crucial honesty caveat printed **immediately below the headline number**, exactly as the editing rules
require. The 220× is only the graph-building function, measured with frames and embeddings already
loaded. The whole ingest is not 220× faster. They put the ingest cost right next to it so nobody can
quote 220× as "the whole pipeline".

Note also "6.36 GB" for the dense version — over 6 GB of RAM for a 4,892-frame graph, which is why bigger
graphs simply run out of memory.

### 4.3 Why construction cost is the durable claim (lines 68–77)

**Lines 70–74** — "A construction saving cannot be absorbed by a downstream stage, because there is no downstream stage inside construction. This is not true of the query-side savings we report next: §5.3 shows a retrieval speedup of two to three orders of magnitude that nonetheless fails to reach the user, because a constant-cost captioning stage dominates the end-to-end path at the sizes we measure."

Why §4 is the claim that survives and §5 is not. Construction is a self-contained job — if it takes 0.316
seconds instead of 69, that time is genuinely saved, full stop. Query speed is a different story: it is
one stage in a chain, and a slow later stage eats the win.

**Lines 76–77** — "We draw the contrast deliberately. A reader should finish §4 and §5 knowing which of our efficiency numbers survives contact with a full pipeline and which does not."

## §5 Query Scaling

### 5.1 Latency exponents (lines 83–129)

**Lines 85–88** — "We fit log(latency) = k·log(N) + c per arm over a corpus of 31 measured clips drawn from UCF-Crime (Anomaly-Part-1 and Testing_Normal_Videos), under **real CLIP text queries** (50 queries per clip), with clip-level bootstrap confidence intervals (seed 42, B=10,000, resampling clips within each N-bucket and refitting) [C1.1, C1.5]."

The method: plot log(time) against log(size); the slope `k` is the scaling exponent. k=1 means linear,
k=2 means quadratic. 31 clips, 50 real queries each. For the error bars they used **bootstrapping**:
re-sample the clips 10,000 times and re-fit each time to see how much the slope wobbles. Seed 42 makes
it reproducible. Resampling **clips** (not individual queries) is the correct choice, since queries from
the same clip are not independent.

**Lines 90–95** — the results table:

| arm | fit range | n points | k | 95% CI | R² |
|---|---|---|---|---|---|
| dense (flat) | N ≥ 1102 (headline) | 4 | 2.063 | [2.020, 2.125] | 0.9994 |
| scene-sparse | N ≥ 1102 (headline) | 6 | 0.834 | [0.801, 0.884] | 0.9830 |
| dense (flat) | full range | 17 | 1.980 | [1.951, 2.006] | 0.9978 |
| scene-sparse | full range | 19 | 0.497 | [0.461, 0.530] | 0.8980 |

R² near 1.0 means the line fits the points almost perfectly. Note the headline dense fit rests on only
**4 data points** and the sparse on **6** — a genuine weakness they admit in §8.3.

**Lines 97–100** — "The headline intervals are disjoint, and the scene-sparse upper bound lies below 1.0. Over the measured range this supports a quadratic-versus-sublinear separation."

Two conditions, both met, and both were **pre-registered in advance** (see Appendix B.7): the ranges must
not overlap, and the sparse upper bound must be under 1.0 so "sublinear" is proven rather than assumed.

**Lines 102–110** — "**On the two scene-sparse exponents.** The full-range fit (0.497) is markedly lower than the headline fit (0.834), and we report both rather than selecting the more favourable. Small-N clips sit close to the measurement noise floor, where fixed per-query overhead dominates and latency grows more slowly than the asymptotic trend; the full-range fit also has visibly poorer explanatory power (R² 0.898 vs 0.983). We take the N ≥ 1102 fit as the headline because it is the regime the paper is about — large graphs — and because it is the *more conservative* of the two for our claim, giving a larger exponent and thus a smaller sparse-versus-dense separation. **[TODO: state whether the noise-floor explanation was verified directly or is inferred from the fit; if inferred, say so.]**"

Excellent methodological hygiene. 0.497 would look *better* for them (an even flatter curve), but they
chose 0.834 as the headline for two defensible reasons: the paper is about big graphs, and it is the
**less flattering** of the two. Choosing the less flattering number when both are defensible is the
strongest possible answer to "did you cherry-pick?" The reason small clips look artificially flat: at
tiny sizes, fixed overhead (starting up, encoding the query) swamps the actual search time. The TODO
honestly asks whether that explanation was *tested* or just *assumed*.

**Lines 112–129 — three caveats, printed with the table:**

**1. Thin support at large N (lines 114–117).** They aimed for 5 clips per size bucket. They got 7, 2,
2, and 1. Median clip size is N=333, and 24 of 31 clips are under N=1000 — so the corpus is
overwhelmingly small videos, while the claim is about large ones.

**2. A shortcut-branch guard failure (lines 118–123).** Two small clips (Assault036, N=97; Abuse037,
N=188) took the §3.4 shortcut on 20% and 10% of queries, breaking a rule they had pre-registered. Their
handling: both are outside the headline range, and re-fitting with them removed changes the exponent from
0.497 to 0.503 — under 2%. "We report the violation rather than suppress it; the mechanism is unconfirmed."

**3. Salience-weight provenance (lines 124–129).** The whole corpus used weights (0.5, 0.3, 0.2), which
the text calls a deviation from "the frozen production default (0.8, 0.1, 0.1)". The internal comparison
is still fair because every clip used the same weights — but the survivor counts here cannot be compared
against retention figures computed under production weights. **This is the caveat that §3's note 1 says
may be exactly backwards.**

### 5.2 Tractability divergence (lines 131–147)

**Lines 133–137** — "Under a uniform 3600 s wall-clock and 29 GB memory watchdog, the dense arm was censored at N=6,559 (Arrest047) and N=13,506 (Arson019), with resident memory at 17.0 GB and 26.9 GB respectively and still climbing at the cap. The scene-sparse arm completed the same two clips in 0.0104 s and 0.0210 s [C1.3]."

Both arms got the same kill switch (fair test). Dense hit it on two clips, holding 17 GB and 26.9 GB of
RAM and **still growing** — so it was not about to finish. Sparse did the same clips in a hundredth and
two hundredths of a second.

**Lines 139–142** — "We report this as a **tractability boundary, not a speedup ratio**: the dense measurements are censored, so any ratio computed against them is a lower bound on an unknown quantity. Substituting the cap as a floor value and refitting gives k ≥ 2.597 for the dense arm — a bound, not an estimate, and we attach no confidence interval to it."

Statistical discipline. You cannot say "760,000× faster" because you never learned how long dense would
have taken. You can only say "at least this bad". Same for the exponent: k ≥ 2.597, stated as a bound
with **no confidence interval**, because computing a CI on a censored value would be fake precision.

**Lines 144–147** — "The operational statement is the honest one: **at these sizes, some queries against a dense graph do not complete.** That is a capability difference, and unlike the latency results below it is not subject to Amdahl dilution — a query that never returns cannot be rescued by a fast downstream stage."

The strongest surviving claim in §5. A slow query can be hidden by a slower stage elsewhere. A query that
never returns cannot be. This is the one query-side result that the §5.3 bad news does not undermine.

### 5.3 End-to-end accounting — negative result (lines 149–202)

**Lines 151–152** — "Retrieval-mechanics measurements at N=4,892 show a 1,104× ratio between arms (7.9448 s dense vs 0.0072 s scene-sparse) [C1.4]. **This ratio does not reach the user.**"

Headline number followed immediately by the demolition of it.

**Lines 154–157** — the experimental setup: full query path, same N, `granite4:micro` on CPU, top_k=30,
five real CLIP-text queries per arm plus a discarded warm-up, and **the caption cache reset before each
arm**. That last detail matters — otherwise the second arm would inherit the first arm's cached captions
and look artificially fast.

**Lines 159–164** — the stage-by-stage table:

| stage (median, s) | dense | scene-sparse |
|---|---|---|
| retrieval mechanics (incl. query embedding) | 8.086 | 0.028 |
| answerer (LLM) | 2.629 | 2.623 |
| captioning + verification | 39.92 | 62.80 |
| **total** | **50.91** | **65.45** |

Read this table top to bottom and the whole disappointment is visible. Retrieval: 289× faster. Answerer:
identical. Captioning: the sparse version is **23 seconds worse**. Totals: sparse loses.

**Lines 166–168** — "**End-to-end ratio: 0.778×** — the sparse arm was *slower* at the median in this sample. Per-query totals span 15.49–88.05 s (dense) and 10.19–79.40 s (sparse), so the sample is noisy; but the direction of the median is unambiguous and the mechanism is not in doubt."

0.778× means it took ~1.29× longer. They flag the noise honestly (individual queries ranged from 10 to 88
seconds with only 5 samples per arm), but note the *mechanism* is understood regardless of noise.

**Lines 172–176** — "**The LLM is not the bottleneck.** The answerer stage costs 2.63 s and is identical across arms ... The dominant term is captioning and verification, which is O(top_k) rather than O(N) and therefore does not shrink as the graph sparsifies. Sparsifying the graph makes the retrieval step negligible while leaving the largest term untouched."

A useful finding in its own right: people assume the big language model is the slow part. It is not —
it is 2.6 seconds. The slow part is **describing 30 images in words**, and that cost depends on 30, not
on graph size, so no amount of graph cleverness touches it.

**Lines 178–183** — "**The retrieval ratio in this run is not the ratio in §5.3's first line.** The retrieval-mechanics ratio here is approximately 291×, against the 1,104× reported in [C1.4]. The two are measured under different query types — real CLIP text encoding here, synthetic sampled embeddings there — and **must not be conflated.**"

Catching their own inconsistency in public. Real text queries have to be encoded by CLIP first, which
costs time the synthetic version skipped. So 291× (real) and 1,104× (synthetic) are both correct, for
different questions — and the 1,104× must always be labelled "synthetic".

**Lines 185–189 — Crossover.** If you assume a constant caption cost L = 56.9 s and extrapolate from the
§5.1 fits, sparse would gain a *material* (≥2×) end-to-end advantage around N≈12,274; 1.5× at N≈8,772;
3× at N≈17,176. Retrieval alone crosses over at just N≈24. So the method is right in principle — it just
needs videos ~2.5× bigger than the one they measured before users feel it.

**Lines 191–198** — the four assumptions behind that projection, listed honestly:
(i) L does not change with N — plausible but never tested at another N;
(ii) L is the same in both arms — **"contradicted by this run's own data"** (39.9 vs 62.8 s), so the pooled median is a simplification;
(iii) the retrieval coefficients come from the older committed fit, not re-fit here;
(iv) a single clip underlies both the L measurement and much of the retrieval fit.
And the killer self-check: the projection predicts ~1.15× at N=4,892 but they **measured 0.778×** — the
model disagrees with reality at the one point where reality is known. They report that disagreement as
evidence of how noisy a five-query sample is.

**Lines 200–202** — "**[TODO: decide whether to report the projection at all ... a reviewer may reasonably regard a single-N extrapolation as unsupported.]**"

An open editorial decision, honestly stated.

### 5.4 Caption-cache locality — negative result (lines 204–242)

**Lines 206–209** — "The sparse arm's captioning stage costs more than the dense arm's at identical top_k. Over 20 real text queries per arm at N=4,892, with top_k verified byte-identical across arms (30 retrieved frames on all 40 queries) and an identical query set, the paired clip-level bootstrap difference is **+9.30 s per query, 95% CI [3.52, 16.22]** (seed 42, B=10,000), which excludes zero."

A second, separate bad result — and a well-controlled one. Same number of frames (verified byte-identical
on every query), same queries, more data (20 per arm not 5). The sparse arm costs 9.30 s more per query,
and the range [3.52, 16.22] **does not include zero**, so the effect is real, not noise.

**Lines 211–219** — the diagnostic table:

| | dense | scene-sparse |
|---|---|---|
| caption cache misses per query (mean) | 3.85 | 7.75 |
| frames decoded (mean) | 38.3 | 73.15 |
| per-frame caption wall time (mean) | 2.535 s | 2.520 s |
| verify calls per query (mean) | 1.05 | 1.00 |

Per-frame captioning cost is the same (2.535 vs 2.520 s). The verify calls are the same. **The entire
difference is cache misses** — 7.75 vs 3.85, roughly double.

**Lines 221–226** — "We tested the hypothesis that the sparse arm retrieves more temporally dispersed frames and **rejected it**: sparse retrievals touch marginally *fewer* distinct scenes (23.8 vs 26.8) and have a *smaller* mean pairwise frame-index distance (2,732 vs 3,070), and the correlation between dispersion and caption time is essentially zero (pooled r = −0.058, n=40)."

They had an obvious theory — "sparse grabs frames from all over the video, so it decodes more" — and
**tested and killed it**. Sparse actually touches *fewer* scenes and its frames are *closer* together.
And the correlation between spread and caption time is −0.058, i.e. nothing.

**Lines 228–232** — "The mechanism is cross-query cache locality. The dense arm re-retrieves an overlapping pool of high-salience frames largely independent of the query — its miss count falls to zero by the sixth distinct question — whereas the sparse arm returns query-specific frames, so successive distinct questions touch largely disjoint frame sets and the caption cache warms slowly."

The real explanation, and it is a good one. The dense arm keeps returning **the same generically-exciting
frames** no matter what you ask — by question six it has already captioned everything it will ever
return, so it costs nothing. The sparse arm returns **different frames for different questions**, so
every new question needs new captions.

**Lines 234–239** — "We note the double edge plainly: **the dense arm's caching advantage is a consequence of its retrieval being less responsive to the query.** The same property that makes it cheap to cache makes it a worse retriever. This does not make the cost imaginary — the caption cache is a production mechanism that persists across a session — so the honest statement of our efficiency claim is that the sparse graph retrieves far more cheaply *and* benefits less from cross-query caption reuse."

The sharpest paragraph in the file. Dense wins on caching **because it is bad at its job** — it ignores
your question. But they refuse to dismiss the cost on that basis, because the cache is real and users
really do pay it. So both facts get printed together.

**Lines 241–242** — "A build-time caption prefetch over high-centrality nodes would plausibly eliminate this cost, given a construction budget of 0.316 s. We have not implemented or measured it."

A clean proposed fix — pre-caption the important frames at build time, since building is nearly free
anyway — immediately followed by "we have not done it". Suggested, not claimed.

### Notes for co-authors (lines 246–258)

- **Lines 248–250** — §5.1's two exponents are where a reviewer will probe hardest. If anyone disagrees that the headline choice is conservative, say so now, not after submission.
- **Lines 251–252** — §5.3's projection is "the weakest passage in either section"; the recommendation is to keep the measurement and cut the crossover to a single sentence.
- **Lines 253–255** — "**Do not merge §5.3 and §5.4** into a single 'limitations' paragraph. They are different findings — one is Amdahl, one is cache behaviour — and collapsing them loses the query-responsiveness point." Merging them would hide the interesting insight that dense caches well *because* it retrieves badly.
- **Lines 256–258** — Numbers still to re-verify: the ingest figures and the 1,104× / 7.9448 s figures, which are currently quoted via the ledger rather than read from the artifact.

### P0 edit log (lines 262–273)

- **P0-2 applied (§4.1)** — grounding-gate claim narrowed to what it actually proves. Source: the artifact's own scoping note.
- **P0-3 resolved elsewhere** — the codec build-cost comparison was never quoted numerically in §4/§5, so nothing needed changing here; §2.5 carries the fix.
- **Still open** — the §5.3 projection decision, and the possibly-backwards salience-weight caveat.

---
# FILE 7 — `06_correctness_floor.md` (157 lines)

*What it is:* §6 — the accuracy chapter. Note the title: not "results", but **"correctness floor"**. The
argument is "we are not broken", not "we are the best".

**Lines 3–4** — "Verified from disk: `P_NOWA_accgqa_result.md`, `MLVU_codec_baseline.md`. Competitor figures verified from primary sources."

**Lines 6–7** — "**Three issues surfaced while drafting — see 'Notes for co-authors'. One is a provenance gap that must be closed before submission.**"

Warning up top: one result cannot currently be traced to a version of the code.

**Lines 13–17** — "This section does not claim competitive accuracy. It claims that a graph costing 0.316 s to build, produced without a neural forward pass and queried by a ~3.4B answerer on CPU, does not degrade answer quality below the weakly-supervised band. That is the relevant question for an efficiency contribution: a construction saving is uninteresting if the resulting system cannot answer anything."

The purpose of the whole chapter, stated in the first sentence so nobody misreads it. If your paper is
about speed, you still have to prove your fast thing works at all — otherwise "infinitely fast at
producing garbage" would be a result.

### 6.1 Grounded QA on NExT-GQA (lines 19–81)

**Lines 21–24** — "On a held-out split of 120 questions over 27 videos, **Acc@GQA is 0.1667, 95% CI [0.088, 0.243]**, with Acc@QA 0.375 [0.275, 0.477] [C4.1]. The answerer is `granite4:micro` (~3.4B, Q4_K_M, temperature 0, CPU); the option parser succeeded on 120/120 questions with zero failures."

The headline accuracy: **16.67% strict, 37.5% if you ignore whether it pointed at the right moment.**
"Temperature 0" means the model is deterministic — no randomness, so the run is reproducible. "Option
parser succeeded on 120/120" means the system always produced a readable answer; none of the errors are
formatting failures, they are genuine wrong answers.

**Lines 26–27** — "The result decomposes cleanly: 42 of 120 questions are correctly grounded, 45 of 120 are answered correctly, and 20 satisfy both — that is, 0.350 × 0.476 = 0.167."

A very clear breakdown. It points at the right part of the video 35% of the time. It answers correctly
37.5% of the time. It does **both** on only 20 questions = 16.7%. The multiplication works out, which is
itself a consistency check.

**Lines 29–33** — "**Grounding and correctness are coupled.** P(correct | grounded) is 0.476 against P(correct | ungrounded) of 0.321 [C4.2]. This ~15-point gap replicated across two independent samples (65 vs 46 in-sample; 47.6 vs 32.1 held out) even though absolute levels fell between them, which supports the coupling independently of where the levels land."

When it looks at the right part of the video it gets 47.6% right; when it looks at the wrong part, 32.1%.
So **looking in the right place genuinely helps** — retrieval is doing real work. The gap of ~15 points
showed up in two separate samples, even though the absolute numbers dropped a lot between them (65→47.6),
which makes the *relationship* more trustworthy than either number alone.

**Lines 35–39** — "**Neither stage is negligible.** Perfect grounding would raise Acc@GQA to 0.476 (+0.31 headroom); a perfect answerer over current grounding would give 0.350 (+0.18). Grounding carries more headroom, but the answerer is not a rounding error, and an earlier in-sample estimate that suggested otherwise (P(correct | grounded) = 0.65) is not reproduced held out — the held-out value sits at the floor of that estimate's interval."

Where to invest effort. Fix retrieval perfectly → 47.6%. Fix the answerer perfectly → 35.0%. So retrieval
has more room, but the answerer matters too. Importantly, they used to think the answerer was fine
(0.65), and that estimate did **not** survive on held-out data (0.476). It landed at the very bottom of
the old estimate's plausible range — so the old estimate is not technically contradicted, but the
conclusion drawn from it collapses. This is the failed prediction that Appendix B.4 is about.

**Lines 41–46** — "**Against uniform frame sampling, our retrieval is positive but not separated.** The held-out advantage in answer accuracy is +0.120, 95% CI [0.000, 0.248] — the interval touches zero. Against *random* sampling it is +0.127 [+0.036, +0.229], which does separate. The honest statement, and the one we make: **retrieval beats random frame sampling on answer accuracy; against uniform sampling the advantage is positive but not statistically separated at n=120** [C4.4]."

A painful but scrupulous admission. Compared to picking frames **randomly**, IRIS clearly wins. Compared
to just taking **every Nth frame** (uniform sampling — trivially simple), IRIS is +12 points but the range
starts at exactly 0.000, so they cannot claim it. With only 120 questions there is not enough statistical
power to prove it.

**Lines 48–50** — "**Placement, indicatively.** Our 0.1667 falls below MUPA-2B's 0.287 with our interval excluding it, and lands in the same band as SeViLA (0.166), LangRepo (0.171), and FrozenBiLM+NG+ (0.175), while running a ~3.4B answerer on CPU with no training."

"Our interval excluding it" = they are definitively worse than MUPA, not just apparently worse. But they
sit right among the weakly-supervised methods — while training nothing and using no GPU.

**Lines 52–61** — the comparison table:

| method | params | Acc@GQA | mIoP | IoP@0.5 |
|---|---|---|---|---|
| Temp[CLIP] NG+ | 130M | 16.0 | 25.7 | 25.5 |
| SeViLA* | 4B | 16.6 | 29.5 | 22.9 |
| LangRepo | 12B | 17.1 | 31.3 | 28.7 |
| FrozenBiLM NG+ | 1B | 17.5 | 24.2 | 23.7 |
| VideoMind-2B | 2B | 25.2 | 36.4 | 32.6 |
| MUPA-2B | 2B | 28.7 | 39.1 | 38.7 |
| MUPA-7B | 7B | 30.3 | 41.4 | 39.4 |
| **IRIS (ours)** | ~3.4B, CPU | **16.7** | — | — |

They put themselves at the bottom of the table. The dashes for mIoP/IoP@0.5 are the P1-5 omission. The
asterisk on SeViLA marks that its grounding row was reproduced by the benchmark authors, not reported by
SeViLA itself.

**Lines 63–66** — "**This comparison is indicative, not a leaderboard entry.** Our figure is n=120 from a val-derived split with an ~8-point interval; every published figure in the table is computed on the full 5,553-question test set. We place the row to situate the system, not to rank it, and we do not claim to have beaten any method in the table."

The table is a map, not a scoreboard. Their number has an 8-point error bar off 120 questions; everyone
else's is off 5,553.

**Lines 68–72** — "**The test half is burned.** Both permitted touches have been used, and grounding reproduced exactly across them (mIoP 0.3349, IoP@0.5 0.3500), so they compose into a single held-out result. No further test-half measurement is possible without a new split [C4.6] — a constraint that applies to any future work on the answerer, which this section identifies as a live target."

Serious scientific discipline. The rule is that you may only measure on the held-out test set a fixed
number of times — otherwise you slowly tune to it and your "held-out" number becomes fake. They allowed
themselves two touches, used both, and now the test set is **permanently retired**. Any future work has
to build a fresh split. This costs them, and they accept it.

**Lines 74–81** — "**[TODO — decision required: whether mIoP and IoP@0.5 appear in this section at all. They are currently computed under a union convention that is biased upward relative to the leaderboard's max-per-span convention, and are NOT-PRINT-SAFE as they stand [C4.3]; printing them requires a re-run, since the raw dump does not retain predicted spans. Our recommendation is to omit them ...]**"

Explaining the dashes. Their grounding metric was computed a way that flatters them, so putting it in a
table next to leaderboard numbers computed the other way would be misleading. Fixing it needs a re-run
because the saved output does not keep the predicted spans. Recommendation: just leave them out, since
the section's argument does not need them.

### 6.2 MLVU (lines 83–118)

**Lines 85–89** — "We additionally evaluate on MLVU's multiple-choice tasks, restricted to the six third-person tasks (the egocentric Ego Reasoning task is excluded, since our compressed-domain signals assume a largely static camera; the generation tasks are outside our multiple-choice harness). 150 questions, 25 per task, videos capped at 600 s, seed 42, `scene_segmentation='codec'`, `graph_mode='scene_sparse'`."

A second benchmark for breadth. Two exclusions with reasons given: (a) first-person/head-mounted video is
excluded because their motion signals assume a fixed camera — when the camera itself moves, everything
looks like motion; (b) free-text generation tasks do not fit their multiple-choice test harness. Giving
the reason for each exclusion is what stops this looking like cherry-picking.

**Line 91** — "**M-Avg: 0.340.** Zero ingest failures across 145 unique videos; overall option-parse failure rate 3.3%."

34% average. No crashes on 145 videos — a robustness result in itself. Only 3.3% unparseable answers.

**Lines 94–101** — per-task table (chance = 0.250 throughout):

| task | accuracy | chance | parse-fail |
|---|---|---|---|
| Topic Reasoning | 0.720 | 0.250 | 4.0% |
| Plot QA | 0.400 | 0.250 | 0.0% |
| Anomaly Recognition | 0.320 | 0.250 | 0.0% |
| Needle QA | 0.280 | 0.250 | 12.0% |
| Action Order | 0.160 | 0.250 | 4.0% |
| Action Count | 0.160 | 0.250 | 0.0% |

The spread tells the story. "What is this video about?" → 72%, nearly 3× chance. "What order did things
happen in?" and "how many times did X happen?" → **16%, below random guessing.**

**Lines 103–108** — "**Two tasks fall below chance, and the cause is the answerer rather than retrieval.** Action Order and Action Count sit at 0.160 against a 0.250 floor. Parse failure on these tasks is 4% and 0% respectively, so the model is confidently wrong rather than unparsed. Both tasks require properties that top-k retrieval does not supply: chronological ordering requires reasoning over relative time, and exhaustive counting requires complete coverage rather than the most relevant evidence."

Worse than random is a real signal — it means the system is being systematically misled, not just
guessing. The parse-fail rates rule out "it failed to answer"; it answered confidently and wrongly. And
the diagnosis is structural: "give me the 30 most relevant frames" is exactly the wrong tool for
**ordering** (you need relative timing, which a relevance ranking destroys) and for **counting** (you
need *every* instance, not the *best* ones).

**Lines 110–114** — "This is the same failure mode we observe on NExT-GQA's directional-temporal questions, where accuracy collapses on before/after items even when the correct evidence is retrieved. **[TODO: cross-reference precisely once the companion analysis is available; do not import its numbers into this paper.]** We treat it as a limitation of the answerer at this scale rather than of the graph, and note it in §8."

The same weakness appears on the other benchmark — and crucially **even when the right frames were
retrieved**, so retrieval is not the culprit. The TODO enforces a rule: do not import numbers from an
unpublished companion paper.

**Lines 116–118** — "Needle QA's 12% parse-failure rate is the highest of the six and its accuracy (0.280) sits closest to chance among the tasks that clear it; the two may be related, and we do not claim a meaningful margin there."

Refusing to claim a 3-point margin over chance when 12% of answers were unreadable anyway.

### 6.3 What this section supports (lines 120–126)

**Lines 122–126** — "The system answers. It answers in the band occupied by weakly-supervised methods with comparable or larger models, using a graph built in 0.316 s on CPU with no training and no frontier model. It does not answer as well as current agentic methods, and where it fails — directional temporal reasoning, exhaustive counting — the failure is located in the answerer rather than in the representation."

Three sentences: it works; it is not the best; and where it breaks, the break is in the small language
model, not in the graph — which matters because the graph is what the paper is about.

### Notes for co-authors (lines 130–157)

**Lines 132–137 — note 1: the MLVU artifact has no commit.** The result file recorded its config hash but
its git field contains a **captured error message** (the `git rev-parse HEAD` command failed when it was
written) and its "dirty" flag is null. Every other artifact has a commit. So this number cannot be traced
to a version of the code. Fix by re-stamping or re-running. "**Do not paper over it in Appendix A.**"

**Lines 139–145 — note 2: the MLVU skip counts.** The artifact shows 175–428 questions "skipped (no
video)" per task, which looks alarming — like data was lost. It was by design: they only downloaded the
sampled subset of videos. The fix is to *state the sampling procedure* (deterministic sampling at seed 42
from the in-band pool, then only those videos fetched) so the skip counts do not imply attrition.

**Lines 147–152 — note 3: competitor figures.** All primary-source verified, with three traps flagged:
MUPA's abstract contradicts its own Table 1 (cite the table); LangRepo's numbers come from LangRepo's own
Table 5, not from MUPA's re-quote of them; and SeViLA's grounding row comes from the benchmark paper's
reproduction because SeViLA never reported it — hence the asterisk.

**Lines 154–157 — note 4:** the mIoP/IoP decision is the one open call. If the team wants to print them,
the re-scoring must happen first.

---
# FILE 8 — `07_negatives.md` (142 lines)

*What it is:* §7, titled **"What Does Not Matter"** — the chapter where they publish the experiments that
disproved their own ideas.

**Lines 3–7** — "MLVU numbers verified against `eval_results/MLVU_ablation_long_trimmed.md` and `MLVU_ablation.md` on disk. **R0/T5/T6 numbers are ledger- and report-quoted only** — their artifacts ... live on teammates' machines and were NOT re-read for this draft. Verify before submission; ledger-quoted numbers are exactly how the phantom 4.6× entered the record."

A very direct warning. Half of §7's numbers were **not** read from the original files — they were copied
from the ledger and a session report, because the files are on someone else's laptop. And the last clause
names the exact failure mode: this is precisely how the fake 4.6× number got into the project.

**Lines 13–17** — "The results in this section are negative. We report them because each was pre-registered with a kill criterion fixed before the data were seen, each criterion triggered, and together they constrain what a practitioner should spend effort on. They also delimit our own contribution: they are the reason §4 claims cheap construction rather than better construction."

Why publish failures: (1) they were pre-registered, so they are real evidence rather than post-hoc
excuses; (2) they save other people from wasting time on the same dead ends; (3) they are the reason §4's
claim is worded carefully.

### 7.1 Segmentation placement (lines 19–69)

**Lines 21–23** — "Our scene boundaries derive from compressed-domain residual peaks (§3.5). The natural question is whether this content-adaptive placement produces a better graph than a content-blind rule. We tested it directly."

**Lines 25–31 — Design.** Four boundary strategies with everything else held constant (same retrieval,
same answerer, same questions, same seed) so segmentation is the only variable:
- **(a) codec** — their clever residual-peak method.
- **(b) equal-count** — same *number* of segments as codec produced for that video, but placed so each segment has the same number of frames.
- **(c) equal-time** — same number of segments, placed at even time intervals.
- **(d) fixed-60s** — cut every 60 seconds, which is what EgoSG does.

**Lines 30–31** — "Arms (b) and (c) are matched-count controls: they isolate *where* boundaries fall from *how many* there are."

The critical design point. If codec produces 500 segments and fixed-60s produces 10, and codec wins, you
have not learned that codec is *smarter* — only that more segments is better. Matching the count strips
that confound out.

**Lines 33–40 — Short videos (≤600 s), 150 questions, 145 videos:**

| arm | M-Avg |
|---|---|
| codec | 0.340 |
| equal-count | 0.393 |
| equal-time | 0.320 |
| fixed-60s | 0.353 |

**Line 42** — "Codec did not lead. The simplest matched-count control was 5.3 points ahead of it."

Their clever method came **third of four**, and the dumbest control beat it by 5.3 points.

**Lines 44–47** — "**Long videos (600–1800 s), AR and PQA, 45 videos.** Short videos yield few segments, so placement has little room to matter; the long-video run tests the regime where it should. The premise holds strongly — codec produced a median of 581 scenes per video (mean 582, range 174–1319), against single digits in the short-video run."

A fair objection they raised themselves: short videos only produce a handful of segments, so *where* you
cut cannot matter much. So they re-ran on long videos where codec produces ~581 scenes instead of ~5.
This "premise guard" was pre-registered — the test is only meaningful if the long run really does produce
many more scenes, and it did (581 vs single digits).

**Lines 49–52:**

| arm | AR (n=17) | PQA (n=91) | M-Avg |
|---|---|---|---|
| codec | 0.412 | 0.451 | **0.431** |
| equal-count | 0.235 | 0.451 | **0.343** |

**Lines 54–58** — "The codec-minus-equal-count difference is **+0.088 M-Avg, 95% CI [−0.009, +0.204]** (video-clustered bootstrap, seed 42, B=10,000). The interval includes zero. Our pre-registered criterion required it to exclude zero; the difference did move in the predicted direction (from −0.053 on short videos to +0.088 on long), and a tie was pre-registered as failure."

This is where pre-registration earns its keep. The point estimate (+0.088) is in their favour. It even
moved the *right way* between conditions (−0.053 → +0.088), which is tempting to over-read. But the
confidence range crosses zero, and their pre-written rule said it must not. And they had also written
down in advance that **a tie counts as failure** — so they cannot argue "well it is at least not worse".
Without that pre-commitment, a motivated author could easily have written this up as a win.

**Lines 60–63** — "**We therefore do not claim that codec-derived boundaries produce a better graph.** The entire difference is carried by anomaly recognition (+0.176, 95% CI [0.000, 0.353], n=17); plot QA is exactly flat (+0.000, CI [−0.101, +0.102]). A domain-concentrated benefit remains possible and is untested at a sample size that could resolve it."

Digging in: the whole +0.088 comes from one task (anomaly recognition, only 17 questions); the other task
is *exactly zero*. So there might be a real benefit specific to anomaly detection — they leave the door
open honestly, while noting 17 questions cannot settle it.

**Lines 65–69** — "**The finding practitioners should take:** once the segment budget is fixed, boundary placement is within noise across four strategies spanning content-adaptive to content-blind. This is what licenses using the cheapest available segmentation — and it is a stronger argument for our pipeline than a codec win would have been, because it does not depend on our particular signal being special."

The practical takeaway, and the reframe: **decide how many scenes you want, then cut however is cheapest.**
And they argue this null result helps them more than a win would have, because a win would have made the
result depend on their proprietary trick. A null makes it universal.

### 7.2 Frame admission versus uniform sampling (lines 71–111)

**Lines 73–74** — "A second question is whether codec signals help *select* which frames enter the graph. Three separate tests, on the 19 annotated UCF-Crime anomaly videos, say they do not."

**Lines 76–81** — "**Coverage metrics are uninformative without a matched control.** Uniform admission saturates gold-window coverage (M1 = 1.0000) at every budget swept, down to 5% retention [C3.1]. Any selector will therefore appear to 'cover 99%+ of gold windows'; the metric measures annotated-window length, not selection quality. We flag this because we previously reported such a coverage figure ourselves, and it does not mean what it appears to mean."

A genuinely useful methodological lesson, plus a public self-correction. They used to boast "we cover 99%
of the important moments!" Then they checked what happens if you just take **every 20th frame** — it also
covers 100%. Why? Because the annotated windows are *long*, so any sampling at all lands inside them. The
metric was measuring the labels, not the method. And they say plainly: **we reported this ourselves and
it was meaningless.**

**Lines 83–86** — "**At matched budget, codec admission is indistinguishable from uniform.** At 10.5% retention, the paired differences are +0.256 pp (95% CI [−0.236, +0.710]) and +0.780 pp ([−0.005, +1.753]) on the two informative metrics; both span zero [C3.2]. The admitted set sits at the label-blind identity: mean(M2 − retention) = +0.0017 (sd 0.0099) [C3.3]."

At the same frame budget, their smart selector ties with taking every 10th frame. Both ranges include
zero. The last sentence is the sharpest: "M2 − retention ≈ 0" means the fraction of important frames they
captured equals exactly the fraction of frames they kept — which is **precisely what you would get by
picking at random**. The selector has zero information about which frames matter.

**Lines 88–94** — "**The tie is not an artifact of the score wasting its budget.** A natural objection is that the score might clump its picks onto near-duplicate frames ... We measured the temporal spread of the *production* admitted set: 83.4% distinct instants with a mean run length of 1.22 — close to uniform's 100% and 1.00, and far from a naive top-k arm's 7.8% and 13.5. Production selection already de-clumps, so the tie is a statement about the signal, not about clumping. **[TODO: verify from the T6 artifact; report-quoted.]**"

Ruling out an alternative explanation. Maybe the selector ties because it grabs 30 nearly-identical
frames from one exciting moment and wastes its budget? Checked: their picks are 83.4% at distinct
instants with average run length 1.22 (i.e. barely any consecutive clumping), close to uniform's ideal
100%/1.00, and nothing like a naive top-k approach (7.8% distinct, runs of 13.5). So the spreading is
fine — the **signal itself** is uninformative. The TODO admits these numbers were quoted, not read.

**Lines 96–102** — "**Shot geometry adds nothing either.** Segmenting each video into shots directly from the packet curve (zero decode) and sampling per shot gives, against uniform, +0.001 pp ([−0.416, +0.421]) and +0.141 pp ([−0.608, +0.972]) — half-widths that *exclude* a 1 pp effect, making this the one properly powered contrast in the group and a genuine null. The corresponding shot-plus-score contrast was underpowered (half-widths 1.69 and 2.79 pp) and we report it as such rather than as a tie."

Third test, third null — and this one is the **best** null, because the error bars are narrow enough
(±0.4 pp) to rule out even a 1-point effect. That is a *proven* absence, not a failure to detect. And
they carefully distinguish the two cases: this one is a genuine null; the shot-plus-score variant had
error bars too wide (±1.69, ±2.79) to conclude anything, so it is reported as **underpowered**, not as a
tie. Most papers blur that distinction.

**Lines 104–106** — "**Power.** The annotated corpus is 19 videos, so each video is 5.3 pp of any aggregate and the resolution floor is roughly 1 pp. No re-run at new seeds or budgets changes this; only more labelled anomaly footage would. We did not re-run in search of significance."

Explaining the fundamental limit: with 19 videos, one video moves any average by 5.3 percentage points,
so nothing under ~1 pp is resolvable. Re-running with different seeds would not help — only more labelled
data would. And the last sentence is a direct anti-p-hacking statement: **we did not keep rerolling until
we got a significant result.**

**Lines 108–111** — "**Reproducibility limitation.** The continuous admission score was not persisted to disk — only the derived retention decision was — so the admission diagnostic could not be extended post hoc without a re-run [C3.5]. We have since adopted the rule that whenever a derived decision is written, the continuous score it came from is written alongside it."

An engineering lesson learned the hard way: they saved "keep / discard" but not the underlying score, so
later analysis was impossible without re-running everything. New standing rule: always save the raw
number alongside the decision it produced. Useful advice for anyone building an experimental pipeline.

### 7.3 What these negatives buy (lines 113–123)

**Lines 115–118** — "Read together, the two results say that neither *where* we cut nor *which frames we keep* is doing the work. What is doing the work is structural: the graph is block-diagonal, so it is cheap to build and cheap to query, and that property is independent of how the blocks are chosen."

**Lines 120–123** — "This is a narrower claim than the one we set out to make, and a more portable one. A pipeline adopting our construction does not need our codec signal, our segmentation, or our admission policy; it needs the block structure. **[TODO: one sentence tying this forward to §9 ...]**"

Their consolation, and it is a fair one: they set out to prove codec signals are smart, failed, and ended
up with a smaller claim that anyone can reuse.

### Notes for co-authors (lines 127–142)

**Lines 129–132** — "**Verify before submission.** Every number in §7.2 is quoted from `CLAIMS.md` or the 2026-08-18 session report, not from an artifact I opened. §7.1 is verified from disk. The R0 artifact and the T5/T6 outputs need to be reachable — which is also a reason to resolve the repository push blocker."

**Lines 133–135** — "**Do not soften the coverage paragraph** in §7.2. Naming our own earlier misreading is what makes the section credible; a reviewer who finds it themselves reads the same fact very differently."

Someone will want to quietly drop the "we got this wrong ourselves" admission. Do not. Confessing it
builds credibility; being caught destroys it.

**Lines 136–139** — "**The AR result in §7.1 will tempt someone** to run more anomaly videos and promote it. It was pre-registered as the last test of that hypothesis. If the team wants to revisit it, that is a decision to make explicitly, in the open, and after this paper ships — not as a quiet extension of the current run."

Guarding against a specific, very human temptation. The anomaly-recognition result *almost* reached
significance, so someone will want to add a few more videos until it does. But they pre-registered that
this was the final test. Revisiting it is allowed — but only as an open, explicit decision after
publication, never as a silent extension of the current run. That is the difference between science and
p-hacking.

**Lines 140–142** — "**Appendix B is the natural home** for the pre-registration criteria and dates behind every test in this section. Whoever writes it should pull from the `*_prereg.md` files in `eval_results/` while the reasoning is still fresh."

---
# FILE 9 — `08_09_limitations_conclusion.md` (149 lines)

*What it is:* §8 (all the limitations collected in one place) and §9 (the conclusion), written together
on purpose.

**Lines 3–5** — "Every limitation here is sourced from a result drafted elsewhere in the paper; no new numbers are introduced. Written together deliberately — a conclusion that ignores what §8 concedes reads as denial."

Nothing new is admitted here — §8 is a *collection* of admissions already made. And the two sections were
drafted side by side so the conclusion cannot cheerfully contradict the limitations two pages earlier.

**Lines 7–8** — "**[TODO]** = genuine gap. One item (§8.7) is a forward reference that depends on a decision the team has not yet made."

### §8 Limitations

**Lines 14–16** — "We have reported negative results inline where they arose (§5.3, §5.4, §7) rather than deferring them here. This section collects the constraints that bound our claims, including those a reader would otherwise have to assemble across sections."

The bad news was already told where it happened. §8 is a summary so a reader does not have to hunt.

**8.1 (lines 18–25) — The retrieval speedup is not an end-to-end speedup.** Restates the 0.778× result and
its cause (captioning is O(top_k), not O(N)). Note the sharp sentence: "**The construction result (§4)
carries no equivalent caveat**; the query-latency results should be read as component-level
characterisations rather than as user-facing latency claims." They are drawing a hard line: §4 survives
this criticism entirely, §5 does not.

**8.2 (lines 27–31) — Sparse retrieval pays a caption-cache penalty.** +9.30 s per query [3.52, 16.22],
because query-specific retrieval warms the cache more slowly. Proposed fix (build-time prefetch) named,
and immediately labelled unimplemented and unmeasured.

**8.3 (lines 33–38) — The scaling fit rests on thin support at large N.** Median clip N=333, 24 of 31
clips under N=1000, and the important buckets hold 7, 2, 2 and 1 clips. Headline fits use 4 dense and 6
sparse points. The best line: "**The confidence intervals are tight because the fits are clean, not
because the support is dense.**" That is exactly the trap a narrow error bar can hide — 4 points that
happen to lie on a straight line produce a tight interval that overstates your certainty. Fixing it is
"a matter of ingestion effort rather than method" — i.e. just process more big videos.

**8.4 (lines 40–45) — A guard violation in the sparse arm is unexplained.** Two clips took the shortcut
on 10–20% of queries against a pre-registered guard. Mitigating facts given (outside headline range,
<2% effect on the fit), but ending on "we do not yet have a confirmed mechanism" and labelling their
theory "untested".

**8.5 (lines 47–50) — Accuracy sits in the weakly-supervised band.** 0.1667 [0.088, 0.243], roughly 12
points below current agentic methods. Restates the defensive claim: cheap construction does not *degrade*
quality below that band.

**8.6 (lines 52–57) — The evaluation splits are constrained.** The NExT-GQA test half is burned; no
further measurement without a new split. Note the framing: this binds **future work more than it binds
this paper** — because §6.1 identified the answerer as the highest-value target (+0.18 headroom), and
nobody can now validate an improved answerer on that split. Also: MLVU is only 150 questions capped at
600 s, and the advantage over uniform sampling is not statistically separated at n=120.

**8.7 (lines 59–66) — Directional temporal reasoning fails, and the failure is not in the graph.** Action
Order and Action Count below chance with low parse-failure rates, so the model is confidently wrong. Same
pattern on NExT-GQA before/after questions. Both need things top-k retrieval structurally cannot give.
The TODO decides how much to forward-reference the unpublished companion work; the recommendation is:
"name the failure mode and its locus, cite nothing unpublished, and import no numbers."

**8.8 (lines 68–72) — Scene shortlisting bounds downstream recall.** Only about ⌈√S⌉ scenes survive the
shortlist, so anything in the other ~95% of scenes is unreachable. Whether the current width rule stays
recall-safe as S grows is unevaluated. This is the price of the sublinear exponent, stated plainly.

**8.9 (lines 74–76) — The CPU-only demonstration is weaker than it could be.** A subtle and unusually
honest point: their measurements were taken on a machine **with no GPU**. So "CPU-only" was partly
forced, not chosen. The stronger claim would be to run on GPU hardware and show you *choose* not to use
it. "and has not been done."

**8.10 (lines 78–82) — Some artifacts are not fully traceable.** A conditional placeholder listing the
MLVU missing commit, the salience-weight question, and the unreachable R0/T5 artifacts — with the
instruction: "If they are fixed by then, delete this item rather than softening it." Either fix it or
state it fully; do not fudge it into vagueness.

### §9 Conclusion

**Lines 88–89** — "We set out to test whether a long-video retrieval graph must be expensive to build. It does not."

The paper's question and answer in two sentences.

**Lines 91–98** — "Our central result is an identity: block-diagonal construction produces exactly the graph that dense construction produces and then prunes — the same nodes, the same edges, the same weights at zero tolerance, the same PageRank — while visiting only the pairs it keeps rather than the 99.8% it would discard. That makes construction ~220× faster and ~6.7× smaller in memory, on CPU, with no neural forward pass during ingest and no proprietary model anywhere in the construction path. The same block structure separates query latency into quadratic and sublinear regimes, and at large graph sizes into a boundary where dense retrieval does not complete at all."

The positive results restated compactly, all consistent with what the body proved.

**Lines 100–105** — "We have been deliberate about what this does not establish. The retrieval speedup does not reach the user at the sizes we measured ... our sparse retrieval pays a caption-cache penalty that dense retrieval avoids precisely because dense retrieval ignores the query; and our answer accuracy sits in the weakly-supervised band rather than at the frontier. We report each of these where it arose."

Three concessions in the **conclusion** — where most papers only celebrate. Note the caption-cache one
keeps its clever framing ("dense wins because it ignores the query") rather than being flattened.

**Lines 107–113** — "The negative results proved the most useful part of the work. We pre-registered kill criteria for two hypotheses we expected to confirm ... and both criteria triggered. Neither where we cut the video nor which frames we keep is doing the work. **What is doing the work is the block structure alone**, which is also what makes the result portable."

Calling the failures the most valuable part of the paper, and explaining why: because eliminating
possible causes leaves one clean, transferable cause.

**Lines 115–117** — "For retrieval over long video, the intermediate graph does not have to be generated, does not have to be clever, and does not have to be expensive. It has to be structured — and structure, it turns out, is nearly free."

The closing line. "Does not have to be clever" is them accepting their own negative results gracefully.

**Lines 119–122** — "**[TODO: one or two sentences of future work ...]**" — with three candidates that do
not depend on the pending companion-paper decision: the shortlist recall-cost frontier, build-time
caption prefetch, and more large-N clips.

### Notes for co-authors (lines 126–149)

**Lines 128–131 — note 1: "§8 is long, and that is the point."** Someone will want to trim ten
limitations down. The counter-argument: every item is already in the body, so compressing §8 does not
remove the concession — it only removes the *demonstration that you know where your claims end*. And
"Reviewers reward this." Both an ethical and a tactical argument.

**Lines 133–135 — note 2:** Do not move §8.1/§8.2 out on the grounds they duplicate §5. "§5 reports them
as findings, §8 records them as bounds. Both functions are needed." Same fact, two different jobs.

**Lines 137–140 — note 3:** "§9's last line is the one to fight over. 'Structure, it turns out, is nearly
free' is the paper's thesis in six words. If anyone thinks it overreaches given §8.1, say so — but note
that it is a claim about *construction*, which is exactly the claim that survives end-to-end accounting."

Pre-empting an internal argument and answering it: the line says *building* is nearly free, and building
is precisely the thing the end-to-end disappointment does not touch.

**Lines 142–145 — note 4:** "§8.10 should ideally not exist at submission." It is a placeholder for known
provenance gaps, all fixable with modest effort. "Fix them and delete the item; do not soften it into
vagueness."

**Lines 147–149 — note 5:** §8.7's forward reference needs a decision. If the companion work is
unpublished, cite nothing and import no numbers. "An uncitable forward reference weakens both papers" —
it makes this paper lean on evidence a reader cannot check, and it pre-spoils the other paper.

---
# FILE 10 — `10_appendix_A_artifact_index.md` (167 lines)

*What it is:* Appendix A — the "show your working" appendix. Every number in the paper mapped to the file
that produced it, plus a frank list of what cannot be traced.

**Lines 3–5** — "Commit hashes, config hashes, seeds, and run dates read directly from the artifacts. Rows marked **(ledger)** were taken from `CLAIMS.md` and not re-read from the artifact — those need verification before submission."

The `(ledger)` tag is a running honesty marker: "this row is second-hand".

**Lines 7–8** — "**Two previously-unrecorded caveats on the N=4,892 headline numbers surfaced while compiling this index — see A.5.1 and A.5.2.**"

The act of writing the appendix itself uncovered two new problems with the flagship numbers.

### A.1 How to read this index (lines 12–21)

**Lines 14–17** — "Every quantitative claim in the paper maps to a named artifact in `eval_results/`, a harness script in `scripts/`, and — where recorded — a commit and configuration hash. We list the seed and resampling procedure for every interval we report, since none of our confidence intervals are analytic."

Three-part traceability: result file, the script that made it, and the code version. And a technical note:
none of their error bars come from a textbook formula — they all come from bootstrap resampling, so the
seed and procedure must be published or the numbers cannot be reproduced.

**Lines 19–21** — "We also list what is *missing*. Section A.5 records provenance gaps we know about rather than omitting them; a reproducibility appendix that reports only the traceable subset is not a reproducibility appendix."

The principle of the whole appendix in one line: an appendix that lists only the things that worked is
not a reproducibility appendix, it is marketing.

### A.2 Environment (lines 23–32)

**Lines 25–27** — "All measurements are CPU-only. **[TODO: state CPU model, core count, RAM, OS, Python version, and torch version. None of this is recorded in the artifacts and it must be captured before submission — a reviewer cannot interpret a wall-clock number without it.]**"

A serious, embarrassing gap. The paper's headline claim is "0.316 seconds", and **there is no record of
what machine that was on**. 0.316 s on a 64-core server and on a laptop mean very different things.

**Lines 29–32** — Answerer: `granite4:micro` via llama-server, temperature 0, `cache_prompt=false`,
`--parallel 1`. Embeddings: CLIP ViT-B/32, same model at ingest and query time.
- `cache_prompt=false` — disable prompt caching so every measurement is a fair cold start.
- `--parallel 1` — one request at a time, so timings are not distorted by concurrency.
- Same CLIP model at both ends — required, or the query and frame vectors would not be comparable.
- TODO: confirm the llama-server build `b9976` was used for every run, not just the one prereg that records it.

### A.3 Artifact index by section (lines 34–78)

**§4 table (lines 38–44)** — five rows:
- Identity gate → `blockdiag_identity_gate_result.{json,md}`, commit `3d83b2c` **(ledger)**.
- Build savings → note the excellent methodological detail: "**each mode run in a separate process so the two builds never share a heap**". Otherwise the first build's memory allocations would distort the second's peak-memory reading. That is a subtle, correct precaution.
- Grounding gate → **(ledger)**, i.e. not re-read.
- Pair-visit counts → with the raw JSON field values quoted: `flat_edge_count: 11963386`, `edge_count_matches_theoretical: true`, `scene_sparse_edge_count: 23571`, `block_diagonal_exact: true`. **Note: this reads 11,963,386 while the paper repeatedly says 11,962,386 — a 1,000 discrepancy. This is exactly what the abstract's note 3 asks someone to re-verify.**
- Ingest efficiency → **(ledger; artifact not reachable from all machines)**.

**§5 table (lines 48–58)** — the interesting provenance details:
- Scaling: git HEAD `9c66393d…` but **"(dirty, 94 changed files)"** — the working directory had 94 uncommitted files when it ran, so the commit hash does not pin the code. Later committed at `90ef59b`.
- Censoring row: notes the lower-bound fit k ≥ 2.597.
- Retrieval mechanics 1,104× row: "**run 2026-07-27; 50 synthetic queries**, `query_seed=20260726`; shortcut fired 0/50; **see A.5.1, A.5.2**." Three flags at once: synthetic queries, and two known caveats. "Shortcut fired 0/50" is a positive control — the §3.4 shortcut never triggered, so it did not distort this measurement.
- End-to-end: git HEAD `90ef59bb…` (dirty, 87 changed files); 5 real queries per arm; cache reset per arm.
- Crossover projection: explicitly labelled "**projection, not measurement**".
- Caption delta: 20 queries/arm; top_k byte-identical on all 40 queries.

**§6 table (lines 62–69):**
- Acc@GQA → commit `dc59de3`; explicitly labelled "**second and final test-half touch**".
- The split → "declared 2026-07-22, **before any measurement**". The date is the whole point.
- The uniform/random comparison → "**all three arms run together to avoid a third touch**". They could not measure the baselines later without burning another touch, so they ran everything at once. Real discipline with a real cost.
- MLVU → "**commit not recorded — see A.5.3**".
- Competitors → sourced individually, with "MUPA Table 1 (**not** its abstract)".

**§7 table (lines 73–78):**
- Segmentation ablation → seed 42, 150 questions, 145 videos.
- Long-video ablation → dirty HEAD, question-set hash `67647a0ca98f73f6` (so anyone can check the same questions were used), video-clustered bootstrap, and the premise guard result (median 581 scenes/video).
- R0 → **(ledger; not reachable)**.
- T5/T6 → **(report-quoted; not reachable)** — one step worse than ledger-quoted.

### A.4 Determinism and seeds (lines 80–91)

**Lines 82–87** — the seed table: 42 for all bootstraps (B=10,000, or 3,000 for the per-type
decomposition), 42 for MLVU question sampling, 20260726 for VIRAT synthetic queries, 20260805 for the R0
bootstrap (ledger).

**Lines 89–91** — "Codec-mode scene assignment was verified deterministic across independent parse+build runs (1,812 assignments, 174 distinct scenes, identical). Cache non-mutation was fingerprinted before and after the VIRAT latency run for both the NExT-QA and VIRAT caches."

Two extra correctness checks: (a) running the scene splitter twice on the same video gives byte-identical
results — no hidden randomness; (b) they fingerprinted the caches before and after the timing run to
prove the run did not secretly modify its own inputs, which would invalidate the second arm.

### A.5 Known provenance gaps (lines 93–134)

**A.5.1 (lines 95–102) — The dense arm did not run its own ingest.** For the N=4,892 comparison, the
dense graph was built in memory from the frames the sparse run had already loaded, to avoid a second
~13-minute ingest. The artifact itself says this *"has not been independently confirmed"* not to
advantage either mode. Since this run produced the 1,104× figure, the caveat sticks to that number. The
recommendation: just state it, since §5.3 already labels the figure carefully and "one more clause is
cheap."

**A.5.2 (lines 104–111) — The N=4,892 clip is mpeg4, not H.264.** The ingest log warned that motion-vector
export may be unavailable for this codec. It does not affect the identity result (pure graph algebra) or
the timings (pure graph mechanics). **But their flagship clip may be one where their own compressed-domain
motion signals were degraded or entirely absent** — which is quite something for a paper about
compressed-domain signals. Their instinct is right: "a paper about compressed-domain signals should say so
rather than let a reader discover it."

**A.5.3 (lines 113–115) — The MLVU baseline artifact records no commit.** The git field holds a captured
error from a failed `git rev-parse`; the dirty flag is null; the config hash is present. Re-stamp or
re-run.

**A.5.4 (lines 117–121) — Several artifacts are not reachable from all machines** (R0, T5/T6, ingest
efficiency). Every number from them is marked. The fix is to resolve the repo blocker; "until then, these
numbers rest on a single machine."

**A.5.5 (lines 123–129) — Most runs were made from dirty working trees.** 94 and 87 changed files at run
time. Their defence is reasonable — the changes were scratch and output files, not pipeline code — but
they concede the core problem: "**a commit hash plus 'dirty' does not uniquely identify the code that
ran.**" Options given: re-run from a clean tree, or extend the per-script SHA-1 hashing that
`scaling_curve_v3` already does to every harness, which they call "the stronger practice".

**A.5.6 (lines 131–134) — One headline artifact was promoted rather than re-run.** The N=4,892 latency
document was assembled from pre-existing outputs from 27 July; the harness was not re-executed when the
document was written, so provenance rests on file timestamps rather than a commit.

### A.6 Reproduction (lines 136–142)

**Lines 138–142** — "**[TODO: write once A.5.5 is decided. It should state the minimal path: which scripts to run, in what order, against which cached indices, and which results are reproducible without re-ingesting video. Note that several results depend on `index_cache/*.npz` files built under salience weights (0.5, 0.3, 0.2) — see §3 note 1, which must be resolved first.]**"

The actual "how to reproduce this" instructions do not exist yet, and cannot be written until the
dirty-tree question and the salience-weight mystery are settled. Note the chain: several results depend
on cached index files built under weights nobody can currently confirm are correct.

### Notes for co-authors (lines 146–167)

**Lines 148–151 — note 1:** "A.5 is the most useful part of this appendix and the most likely to be cut.
Every item is a real gap that a determined reviewer or reproducer would hit. Listing them costs us a page
and buys the claim that we know our own evidence; **hiding them means someone else publishes the list.**"

The blunt cost-benefit: one page versus someone else writing your errata for you.

**Lines 153–157 — note 2:** A.5.1 and A.5.2 are **new** — they are not in the ledger, and both attach to
the flagship figures. They only surfaced from reading the artifact's own caveat section. The conclusion
drawn: "**This is an argument for a full pass over every artifact's caveats before submission**, not just
its headline numbers; the ledger captured the numbers but not all of the warnings that shipped with them."
A structural insight about their own process — the ledger was recording answers but discarding the
warnings attached to them.

**Lines 159–162 — note 3:** "The environment section (A.2) is genuinely empty and genuinely required.
Wall-clock numbers without a machine specification are uninterpretable, and our central claim is a
wall-clock ratio. Ratios are more robust than absolutes, but the reviewer still needs the box." A ratio
(220×) travels better across machines than an absolute (0.316 s), but you still have to say what you ran on.

**Lines 164–167 — note 4:** A.5.5 needs a real decision, not a note. Re-running the two headline
measurements from a clean tree would close it properly; failing that, extend per-script hashing everywhere
and state the limitation.

---
# FILE 11 — `11_appendix_B_prereg.md` (266 lines)

*What it is:* Appendix B — the pre-registration record. For each experiment: what they promised in
advance would count as success, and what actually happened. This is the appendix the team clearly
considers the paper's moral centre.

**Lines 3–5** — "Criteria quoted from the `*_prereg.md` files in `eval_results/` and from result artifacts, not reconstructed. Where a test was registered in a task specification rather than a standalone file, that is stated explicitly."

"Not reconstructed" is the key word — they are quoting what was actually written in advance, not
rewriting it from memory afterwards (which would defeat the entire purpose).

### B.1 Protocol (lines 11–34)

**Lines 13–17** — "Every experiment reported in this paper that could have gone more than one way was registered before the data were seen: the primary quantity, the decision rule, and — where applicable — the prediction. We record them here in full, including the cases where the prediction was wrong and the cases where the criterion killed a hypothesis we expected to confirm."

**Lines 19–25 — the four-step protocol:**
1. Tune only on the validation split.
2. Freeze the parameters and write the frozen configuration down.
3. Measure the held-out split **once**. Report that number.
4. No tuning after the result. If a split gets measured more than once, it is "burned" and labelled.

This is the standard that prevents self-deception. Step 4 is the one most projects quietly violate.

**Lines 27–34** — "**Registration strength is not uniform across these entries, and we say so rather than letting the appendix imply otherwise.** Entries B.3–B.6 have standalone pre-registration documents written and dated before their runs. Entries B.7–B.11 were registered in the task specification that commissioned each run, with the criterion restated verbatim in the resulting artifact — a weaker form, since specification and execution were closer together in time. We mark each entry accordingly. The distinction does not affect whether the criteria bound our reporting, which they did in every case."

The **P1-2 fix**. They are admitting that half their pre-registrations are weaker than the other half.
The strong form: a separate dated document written before the run. The weaker form: the criterion was in
the task brief, which was written close in time to the run — so there was less separation between
"deciding what counts as success" and "seeing the result". They mark every row so a reader can discount
appropriately.

### B.2 Summary table (lines 38–53)

| # | test | registered | form | criterion | outcome |
|---|---|---|---|---|---|
| B.3 | NExT-GQA val/test split | 2026-07-22 | standalone | video-level split declared before any measurement | held |
| B.3a | Held-out grounding | 2026-07-22 | standalone | report whatever returns; no tuning after | **prediction not borne out**, reported |
| B.4 | Held-out Acc@GQA | 2026-07-22 | standalone | report whatever returns; no tuning after | **prediction failed**, reported |
| B.5 | Retrieval funnel | **[TODO: date]** | standalone | CI-thresholded action rule, fixed in advance | read as registered |
| B.6 | R0 admission gate | **[TODO: date]** | standalone | kill criterion on matched-budget control | **triggered** |
| B.7 | Scaling exponent CIs | 2026-08-15 | in-spec | CIs disjoint **and** sparse upper bound < 1.0 | **both held** |
| B.8 | Segmentation ablation | 2026-08-14 | in-spec | codec−fixed CI must exclude zero; tie counts as failure | **failed** |
| B.9 | End-to-end verification | 2026-08-15 | in-spec | if e2e materially below claim, restate around construction | **triggered** |
| B.10 | Caption-stage diagnosis | 2026-08-15 | in-spec | if paired CI includes zero, declare noise and stop | proceeded; hypothesis rejected |
| B.11 | Shot-bucketing selection | 2026-08-18 | in-spec | three-branch read: beats / ties / underpowered | **underpowered** |

Scan the outcome column: of 10 entries, **two predictions failed, two kill criteria triggered, one
hypothesis was rejected, and one landed underpowered.** Only B.7 was a clean win. That ratio is what
makes the appendix credible.

### B.3 The split declaration (lines 55–73)

**Lines 57–61** — "Declared before any measurement on the pool of 526 grounded questions over 86 cached videos. The split is **video-level** — no video appears in both halves — because questions share videos and question-level splitting would leak. Validation: 59 videos, 406 questions, where all tuning occurs. Test: 27 videos, 120 questions, untouched by prior tuning. The asymmetric ratio was deliberate: tuning needs power, the reported number needs cleanliness."

Two good decisions explained. **(a) Splitting by video, not by question.** If you split by question, the
same video appears on both sides, and anything you learned tuning on it leaks into your "held-out" score.
**(b) The lopsided 59/27 split** — more videos for tuning (where you need lots of data to make decisions)
and fewer for the final measurement (where you only need it to be clean).

**Lines 63–68** — comparability measured **before** declaring, with two biases registered in advance
along with the direction each pushes:
- Test has fewer multi-interval questions (6.7% vs 11.3%) → slightly **easier** for test.
- Test has more short gold spans (20.8% vs 17.0%) → slightly **harder** for test.
- "These partly offset; net direction declared unknown."

This is unusually careful. They checked whether the two halves were comparable, found two ways they were
not, wrote down which way each would push, and — crucially — **declared the net direction unknown rather
than claiming it cancels out**.

**Lines 70–73** — "The expectation was registered too: the held-out number would likely fall *below* the in-sample 0.3426 ... and that **a drop is the number becoming real, not a regression.** Expected precision of ±0.08–0.11 was accepted in advance as the cost of a clean estimate."

They wrote down in advance that the number would probably drop, and pre-framed that drop as *the number
becoming honest*, not as the system getting worse. That framing has to be written before the result, or
it reads as an excuse afterwards. They also accepted the wide ±0.08–0.11 error bar in advance as the
price of only measuring once.

### B.3a Held-out grounding — the prediction also did not hold (lines 75–90)

**Lines 77–81** — They predicted the held-out grounding number would fall below the in-sample value.
"**It did not.** Test came in above validation — mIoP 0.3349 against 0.3126."

**Lines 83–86** — "The honest reading is the artifact's own: the confidence intervals overlap heavily, so validation and test are **consistent**, not test-is-better. The direction is attributable to a bias declared in advance (B.3): the test half contains fewer multi-interval questions (6.7% vs 11.3%), which are structurally harder to capture with a single predicted span."

This is the mark of a disciplined team: the result went **in their favour** and they *still* refused to
claim it. Overlapping intervals mean "these two numbers are consistent", not "test is better". And the
direction is explained by a bias they had already declared — which is the payoff for having declared it.

**Lines 88–90** — "We record this alongside B.4 because the two together make the point that one alone would not. Two registered predictions, neither borne out — one low, one high — both reported without adjustment, and neither followed by a change to the frozen configuration."

The reason this entry was added (the P1-1 fix). One missed prediction could be bad luck. Two missed
predictions **in opposite directions**, both reported unchanged, proves the process is binding — because
a team that fudges results does not produce misses in both directions.

### B.4 Held-out Acc@GQA — the prediction failed (lines 92–116)

**Lines 94–100** — Registered with a full frozen-configuration listing and an explicit second-touch
disclosure. All three arms (proposed, uniform, random) were run together, "because running baselines
later would have constituted a third touch." The registration states: *no further test-half measurement
without a new split*, and *whatever Acc@GQA comes back as, that is the number.*

That last quoted phrase is the whole point of pre-registration, written as a promise to themselves.

**Lines 102–106** — "**The registered prediction was Acc@GQA ≈ 0.22**, from IoP@0.5 (0.3500) × P(correct | grounded) (~0.65, estimated in-sample at N=64). **The measured result was 0.1667.**"

They predicted 22% and got 16.7% — a 25% relative miss. And they show their arithmetic so you can see
exactly which factor was wrong.

**Lines 108–113** — "The prediction failed because its second factor did not survive out of sample: held-out P(correct | grounded) is 0.476, not 0.65 — sitting at the floor of the in-sample estimate's interval, so that estimate is not contradicted, but the conclusion drawn from it does not hold. The consequence is recorded in §6.1: the answerer is not a negligible stage, and work on it returns to the critical path. Because the registration forbade tuning after the result, and because the test half is now burned, that work cannot be validated held-out without a new split."

A precise post-mortem. The first factor (grounding, 0.35) held up. The second (how often it answers
correctly *given* it looked in the right place) collapsed from 0.65 to 0.476. Note the careful phrasing:
0.476 was at the *bottom edge* of the old estimate's range, so the old estimate was not *wrong*, but the
conclusion built on it was. And the consequence is expensive: the answerer now needs work, and they have
burned the split they would have used to validate it.

**Lines 115–116** — "We report this failure prominently because it is the clearest demonstration that the registration was binding rather than decorative."

### B.5 Retrieval funnel diagnostic (lines 118–137)

**Lines 120–129** — A read-only diagnostic on validation only, selecting nothing. Three strictly nested
quantities defined in advance (index coverage ≥ pool coverage ≥ peak-in-gold), with an action rule keyed
to the **confidence interval, not the point estimate**:
- CI upper ≤ 0.05 → the anchor is near-optimal; do not build caption reranking.
- CI lower ≥ 0.15 → material headroom; build it, it is the best cheap experiment available.
- Otherwise → inconclusive; take no action.

Two things worth noting. **"Nested" quantities** means each must be ≥ the next by construction, so if the
numbers ever violate that order, you know you have a bug — it is a built-in sanity check. And keying the
decision to the **interval rather than the point estimate** is the disciplined choice: it means a lucky
point estimate cannot trigger an expensive engineering project.

**Lines 130–134** — A stop condition was registered too: the run selects nothing, and no frozen value,
default, or threshold may change as a result. Five limitations were declared in advance, including that
the diagnostic is conditional on one ranking mode and that its `best_gold_rank` quantity only bounds the
headroom reachable by a *different* signal.

Registering a "this experiment is not allowed to change anything" rule prevents a diagnostic from quietly
becoming a tuning run.

**Lines 136–137** — "**[TODO: recover the registration date, and state the realised outcome against the three-way rule.]**" — the date and the actual outcome are missing, because the artifact is unreachable.

### B.6 R0 codec-admission gate (lines 139–148)

**Lines 141–145** — The kill criterion — that coverage metrics are uninformative without a budget-matched
control, and that a saturating uniform arm would invalidate the coverage framing — was registered before
the run and **triggered**: uniform reaches the coverage ceiling at every budget down to 5% retention. The
matched-budget contrast was then reported as a null.

Note what was pre-registered here: not "will our method win?" but "**under what circumstances is our own
favourite metric meaningless?**" Pre-registering the conditions under which your metric is invalid is a
notably high standard.

**Lines 147–148** — TODO for the date and exact wording; the artifact is unreachable.

### B.7 Scaling exponent CIs (lines 150–160)

**Lines 152–156** — Registered before fitting: printable **only if** the two CIs were disjoint **and** the
sparse upper bound fell below 1.0, "so that 'sublinear' is supported rather than assumed". Bootstrap
procedure, seed, and resampling unit all fixed in advance.

Two conditions, both demanding. The second exists specifically so they cannot *assume* sublinearity — the
data has to prove it.

**Lines 158–160** — "**Both conditions held**: dense 2.063 [2.020, 2.125], sparse 0.834 [0.801, 0.884]. Had they not, the registration specified the fallback — lead on tractability divergence and construction cost instead of a clean exponent."

Their one clean win. And note they had already written the **fallback plan** — what the paper would claim
instead if the test failed. Deciding in advance what you will say when you lose is the strongest form of
pre-registration.

### B.8 Segmentation ablation — criterion failed (lines 162–183)

**Lines 164–174** — the four registered conditions:
- Matched segment count, everything else held constant.
- The codec-minus-fixed difference must **exclude zero**.
- **A tie counts as failure** — "the burden of proof sits with the codec arm."
- A premise guard: if long videos did not produce substantially more scenes, the test is inconclusive on mechanism regardless of the accuracy result.

"A tie counts as failure" is the sentence that made this test honest. Without it, +0.088 with a range
crossing zero could easily have been written up as encouraging.

**Lines 176–179** — "The premise guard **passed** decisively (median 581 scenes per video against single digits). The primary criterion **failed**: +0.088 M-Avg, 95% CI [−0.009, +0.204]. The point estimate moved in the predicted direction (from −0.053 on short videos), which is why the criterion mattered — a directional move alone would have been easy to over-read."

The premise guard passing matters: it means the failure is a real answer, not an inconclusive test. And
the last clause names exactly the trap the criterion saved them from.

**Lines 181–183** — "It was further registered that this would be the **last test of the hypothesis**, and that a failure would not be followed by re-running at new seeds, budgets, or subsets. It has not been."

Pre-committing to *stop* is the strongest possible anti-p-hacking measure, because the classic move is
"just one more run with slightly different settings". And "It has not been" confirms they kept the promise.

### B.9 End-to-end verification — rule triggered (lines 185–194)

**Lines 187–190** — Registered before measuring: if the end-to-end speedup came back materially below the
figure the project had been carrying, the efficiency claim would be **restated around construction cost
and tractability divergence rather than query speedup**, and the retrieval-mechanics ratio would be
labelled as such wherever it appeared.

They wrote down in advance exactly how they would rewrite the paper if the result was bad. That is why
the rewrite happened smoothly instead of turning into an argument.

**Lines 192–194** — "The rule triggered. A prior-artifact search found no measurement backing the carried end-to-end figure at all; the fresh measurement returned 0.778×. The paper's framing was changed accordingly (§1, §5.3, §9)."

This is the phantom 4.6× story resolved. They went looking for the evidence behind a number the project
had been repeating, **found no evidence existed**, measured it properly, got 0.778×, and rewrote the
paper's central framing. That is the single most important event in this whole bundle — and the reason
for every "do not fill a TODO from memory" warning.

### B.10 Caption-stage diagnosis (lines 196–210)

**Lines 198–201** — Registered in two stages. First a power condition: re-measure at n=20 per arm, and
**if the paired CI included zero, declare it noise and stop investigating.** It did not (+9.30 s
[3.52, 16.22]), so the causal analysis proceeded.

Setting a stopping rule *before* investigating stops you from chasing a phantom effect through endless
follow-up analyses.

**Lines 203–206** — Second, an interpretation rule fixed in advance: if the effect was real and
dispersion-driven → disclose it in the paper as a genuine system cost. If it was an artifact of the
measurement harness → scope it as an implementation detail. Deciding **what each possible answer would
mean** before you have the answer prevents motivated reasoning.

**Lines 208–210** — "The registered leading hypothesis — frame dispersion — was **tested and rejected** (r = −0.058). The mechanism found instead was cross-query cache locality, which is a production behaviour rather than a harness artifact, so the disclosure rule applied (§5.4)."

Their favourite explanation was wrong, the real mechanism landed in the "disclose it as a real cost"
branch, and they disclosed it. The pre-written rule did the deciding, not their preferences.

### B.11 Shot-bucketing selection — underpowered (lines 212–223)

**Lines 214–216** — Registered with a three-branch read — beats / ties / underpowered — and an advance
acknowledgement that a 19-video corpus resolves effects of roughly one percentage point at best.

Having "underpowered" as an explicit third branch is important. With only two branches you are forced to
call a wide-interval result a "tie", which overstates what you learned.

**Lines 218–223** — The primary contrast landed **underpowered**, and was reported as such rather than as
a tie. A secondary contrast (shot geometry alone) landed as a **properly powered null**. And "The
registration's own guidance — do not re-run at new seeds or budgets to hunt for significance, and do not
report the positive lean of an underpowered contrast as a result — was followed."

They had a positive-leaning result they were explicitly forbidden from reporting, and they did not
report it.

### Notes for co-authors (lines 227–249)

**Lines 229–232 — note 1:** "B.4 is the most valuable entry in this appendix. A pre-registered prediction
of 0.22 that returned 0.167, reported without adjustment, is stronger evidence that our protocol binds
than any of the tests that succeeded. Do not bury it, and do not add a retrospective justification for
why 0.22 was optimistic — the diagnosis in §6.1 is sufficient."

The failure is more valuable than the successes, because anyone can pass a test they designed. And the
instruction not to add a retrospective justification is important: explaining afterwards why you were
always going to be wrong quietly undoes the whole exercise.

**Lines 234–240 — note 2:** the uneven registration strength, with the recommendation to disclose it
(which became the P1-2 fix): "A reviewer who notices it unaided will discount the whole appendix; a
reader who is told will calibrate."

**Lines 242–244 — note 3:** B.6 and B.11 depend on unreachable artifacts; dates and exact criterion
wording must be recovered before submission.

**Lines 246–249 — note 4:** "**Do not add entries retrospectively.** If a test was not registered before the data were seen, it does not belong in this appendix — it belongs in the body as an exploratory result, labelled as such. The appendix's value is entirely in its being a complete and honest record of what was fixed in advance."

The rule that protects the appendix's meaning. One retrofitted entry and the whole thing becomes
worthless, because a reader can no longer tell which entries were genuine.

### P1 edit log (lines 253–266)

- **P1-1 applied** — added B.3a (the second missed prediction), read as the source artifact reads it: overlapping intervals mean *consistent*, not *better*. Paired with B.4 so the record shows two misses in opposite directions.
- **P1-2 applied** — B.1 now discloses uneven registration strength; the B.2 table carries a *form* column.
- **Still open** — B.5's and B.6's dates and B.6's exact criterion wording, all blocked on the same unreachable artifacts as §7 and Appendix A.5.4.

---
# FILE 12 — `_working/artifact_caveat_sweep.md` (138 lines)

*What it is:* not part of the paper. It is the report from an audit: someone went through every result
file the paper cites and read the **caveats section** of each one, hunting for warnings that had been
lost when the numbers were copied into the ledger.

**Lines 3–5** — "Scope: read the caveat/notes sections of every artifact the paper cites that is reachable on this machine, looking for warnings the ledger captured numbers from but did not carry forward. Artifacts on teammates' machines (R0, T5/T6, ingest efficiency) were not covered."

The exact purpose: the ledger saved the *answers* but may have dropped the *warnings*. Three artifacts
could not be checked because they are on other machines.

**Lines 7–9** — "**Three findings. F1 is structural and affects how §4, §5, and §6 relate to each other. F2 means a ledger caveat is understated by a large factor. F3 adds a second pre-registration entry.**"

Three findings from six reachable artifacts — a 50% hit rate, which is why they later recommend sweeping
the unreachable ones too.

### F1 — Three edge modes, and the paper blurs them (lines 13–52)

**Lines 18–20** — "`graph_edge_mode` has **three** values, not two: `hierarchical_sparse` (the dataclass default), `fully_connected`, and `block_diagonal`. This matters because our claims were measured under different ones."

The core discovery. The paper had been written as if there were two settings; there are three, and
different experiments used different ones.

**Lines 22–29** — the audit table. The important rows:
- **MLVU accuracy (§6.2)** — the artifact does **not state** the edge mode, so it must have used the dataclass default `hierarchical_sparse`. Marked `[TODO: confirm]` — inferred, not verified.
- **NExT-GQA (§6.1)** — ran under `flat`, and flat never sets `node_groups`, so `block_diagonal` is literally **unreachable** from that config.

**Lines 33–40 — consequence (a): "The grounding gate proves less than its ledger line suggests."**

The artifact says explicitly that **no committed grounding number was ever produced with
`scene_sparse` + `fully_connected`** — the committed arms use `hierarchical_sparse`, which
`block_diagonal` does not target. So the 526-question gate proves the two *build paths* agree; it does
**not** confirm that the paper's published accuracy is unchanged.

The verdict: "§4.1's current sentence ... is *true* but will be read as the stronger claim. Rewrite to say
what it is." This is the sharpest distinction in the whole bundle — a sentence can be **technically true
and still misleading**, and they treat that as a defect to be fixed. This became the P0-2 edit.

**Lines 42–48 — consequence (b): "Our accuracy numbers may come from a configuration the construction result does not cover."**

If MLVU ran under `hierarchical_sparse`, then §6's accuracy and §4's 220× describe **different edge
formulas**, and any careful reviewer comparing §3.5 against §4 and §6 will spot it. The good news: "This
is fixable by precision, not by re-running" — state the per-experiment configuration honestly, and
explain that the exponents transfer via the §4.1 identity. That became the P0-1 edit.

**Lines 50–52 — Action:** confirm the edge modes, then build the per-experiment table. "**Do not** paper
over it with a single 'frozen configuration' sentence." Explicitly naming the tempting shortcut and
forbidding it.

### F2 — The codec-extraction caveat is understated by ~10× (lines 54–92)

**Lines 58–60** — "The ledger's S2 rule says codec extraction is not free, citing 26.843 s against pixel-diff's 12.390 s at N=2,963 — about 2×. On the **VIRAT N=4,892 clip**, the artifact's own required caveat reads very differently:"

**Lines 62–67** — the real table:

| arm | extraction (s) | weighting (s) |
|---|---|---|
| codec | **323.236** | 0.017 |
| pixel_diff | 72.357 | 0.119 |
| semantic (similarity only) | — | 0.122 |
| semantic (with encode) | 246.839 | 0.102 |

**Lines 69–72** — "Codec extraction is the **largest** of all four arms at the flagship clip — 4.5× pixel-diff's full frame-by-frame decode, and larger than semantic's decode-plus-CLIP-forward-pass. The artifact attributes this to `compute_motion_geometry`'s per-frame gradient math inside `parse_video`, **not** to the demux read."

A genuinely awkward finding for a paper about cheap compressed-domain signals. The "cheap" codec path
costs **323 seconds** — 4.5× more than fully decoding every frame the normal way (72 s), and more than
decoding *plus* running CLIP on everything (247 s). The ledger said "about 2× more expensive"; reality is
about 26× more expensive than pixel-diff at this clip.

Critically, the cause is *not* reading the compressed file — it is per-frame gradient maths in
`compute_motion_geometry`. So the expense is in their own code, not inherent to the approach.

**Lines 76–79 — mitigation 1:** the defence is that this demux pass happens during ingest anyway for
frame selection, so it is amortised against ingest rather than charged to graph construction. "That
defence is legitimate ... but it must appear in the same sentence as any codec-cost claim."

**Lines 80–84 — mitigation 2:** `IRISConfig.compute_full_geometry` defaults to **False**, and its own
comment says those geometry quantities are unused by every currently-exercised path. So **if the 323 s
measurement was taken with geometry switched on, the default cost is much lower.** `[TODO: check which
setting build_cost_3way.py ran under. This materially changes the number.]` A very plausible explanation:
they may have benchmarked an expensive feature that is off by default and computes nothing anyone uses.

**Lines 86–88** — a housekeeping catch: the weighting numbers drafted into §4's notes (0.007 / 0.042 /
0.027) are from the **small** N=2,963 clip, while the VIRAT figures are 0.017 / 0.119 / 0.122. "Use one
clip consistently and say which." Mixing clips within one comparison is a classic quiet error.

**Lines 90–92 — Action:** if the codec cost is cited at all, it must carry the VIRAT extraction caveat.
"Given F1 and the §7 negatives, consider whether this comparison earns its space at all." Since §7 already
showed codec signals do not help accuracy, defending their cost may not be worth the page.

### F3 — A second pre-registered prediction did not hold, favourably (lines 94–113)

**Lines 98–103** — The split declaration predicted held-out grounding would fall below in-sample. It rose
(mIoP 0.3349 vs 0.3126). The artifact's own reading is adopted: intervals overlap heavily, so val and
test are **consistent**, not test-better; the direction is attributed to the pre-declared bias (test has
fewer multi-interval questions, 6.7% vs 11.3%).

**Lines 105–107** — "This belongs in Appendix B alongside the Acc@GQA prediction failure. Two registered predictions, both not borne out, both reported without adjustment, is a stronger record than one." → became P1-1.

**Lines 109–113** — Two bonus findings from the same artifact, both worth keeping:
- The tuned configuration is statistically indistinguishable from the default (mIoP +0.0068 [−0.0132, +0.0264]) — i.e. **their tuning achieved nothing measurable.** Uncomfortable but useful.
- Top-k is flat across 8/12/16/24 retrieved frames — *"the candidate set is NOT the constraint; residual loss is representational."* In plain words: **giving the system more frames does not help.** The bottleneck is not "we did not retrieve enough" — it is that the representation itself cannot express what is needed. That is a well-evidenced, quotable sentence for §8.8, and it became the P2-2 edit.

### What did not turn up (lines 117–121)

**Lines 119–121** — Three reassurances, and reporting these is good practice because it shows the sweep
looked for problems rather than only recording them:
- The identity gate artifact carries **no caveats** — a genuinely clean pass, exactly as reported.
- **No artifact contradicted a number already in the draft.**
- The MLVU ablation guard sections match what the draft says.

### Prioritised actions (lines 123–138)

1. **Confirm edge mode per experiment (F1)**, build the §3.5 table, rewrite §4.1's grounding sentence.
2. **Decide whether the codec build-cost comparison stays (F2)** — if it does, it carries the 323 s figure and the amortisation defence in the same sentence, and `compute_full_geometry` must be settled first.
3. **Add the F3 entry to Appendix B.**
4. Still outstanding from Appendix A: environment spec, the mpeg4 note, the flat-arm ingest caveat, the MLVU missing commit, the dirty-tree question.
5. **Lines 135–138** — "**The unreachable artifacts have not been swept at all** — R0, T5/T6, and the ingest efficiency measurements. Given that this sweep found a significant issue in three of the six reachable artifacts, assume the unreachable ones carry caveats too, and sweep them once they are pushed."

A statistically sensible inference: a 50% hit rate on the files you *can* read means you should expect
problems in the ones you cannot. That converts "we should push the repo eventually" into "we have reason
to believe there are undiscovered problems behind that blocker".

---

# FILE 13 — `_working/revision_pass_edit_list.md` (191 lines)

*What it is:* also not part of the paper. It is the prioritised to-do list generated from the audit —
every edit, why it matters, what it should say, and in what order to do them.

**Lines 3–6** — "Every edit below traces to a verified finding: the artifact caveat sweep or direct reads of `l2_asphodel.py`, `ingest.py`, `scene_retrieval.py`, `mlvu_eval.py`, `e2e_speedup_ab.py`, `build_cost_3way.py`."

Every item is grounded in either the sweep or a direct code read. No edits from opinion.

**Lines 8–10** — "**P0** = the paper is wrong or attackable without it. **P1** = required for submission. **P2** = improves the paper. Work P0 first; they are the ones that change what the paper claims."

The priority scheme, with a clean definition of P0: not "important" but "**the paper is wrong without it**".

## P0 — Claim-accuracy edits

### P0-1. §3.5 → per-experiment configuration table (lines 16–45)

**Lines 18–26** — the table with an **evidence column** — this is what makes it trustworthy:
- §4 → gate artifact.
- §5.1–5.2 → "census excluded 2 clips for *not* being fully_connected" (so the rest were).
- §5.3–5.4 → "`e2e_speedup_ab.py` BASE omits the key → dataclass default".
- §6.2, §7.1 → "`mlvu_eval.py:454` sets only segmentation + graph_mode" (so edge mode defaulted).
- §6.1 → "flat never sets `node_groups`, so block_diagonal is unreachable".

Each row proved from a specific line of source code rather than assumed.

**Lines 28–38** — the exact replacement paragraph to paste in, prefaced with "**it is the sentence that answers the reviewer's obvious objection**". Writing the replacement text out in full (rather than describing it) means whoever applies the edit cannot dilute it.

**Lines 40–42** — the source verification: "*(Verified in `l2_asphodel._update_all_edge_weights`: the `else` branch builds hierarchical edges, then `if node_groups is not None and mode != 'block_diagonal'` prunes all cross-group edges.)*" The actual code condition quoted, so anyone can re-check it in seconds.

**Lines 44–45** — "**Why P0:** without it, a reviewer writes 'you demonstrate 220× cheaper construction for a graph configuration you never evaluate.' With it, that objection is answered."

The rejection sentence written out verbatim. Naming the exact criticism you fear is a very effective way
to decide whether an edit is necessary.

### P0-2. §4.1 — rewrite the grounding-gate sentence (lines 47–62)

**Lines 49–52** — the problem: the current text implies the gate confirms *reported* accuracy is
unchanged; the artifact says explicitly that no committed grounding number was ever produced under
`scene_sparse` + `fully_connected`.

**Lines 54–62** — the exact replacement text, which adds the crucial closing clause: "This is an
equivalence proof between the two construction paths the change concerns; it is not a re-run of a
previously committed number, since our committed scene-sparse arms use the `hierarchical_sparse` edge
formula." This is the wording that shipped in §4.1.

### P0-3. §4 / §2.5 — codec extraction cost with the real figure (lines 64–87)

**Lines 66–69** — ledger says 26.8 s vs 12.4 s at N=2,963; the artifact says 323.2 s at N=4,892, the
largest of all four arms. Weighting is still cheapest (0.017 vs 0.119 vs 0.122).

**Lines 71–79** — the exact paragraph to use if the comparison stays. Note its structure: the good news
(weighting is 10× cheaper), then "**but**" the raw cost, then the amortisation defence, then the honest
closer — "We report the raw figure rather than only the marginal one." All in one paragraph, so the
number can never be quoted without its caveat. This is editing rule 3 in action.

**Lines 81–84** — the `compute_full_geometry=True` TODO, which "materially changes the number".

**Lines 86–87** — "**Consider cutting this comparison entirely.** Given §7's negatives, it earns less space than it costs." Sometimes the best fix for an awkward number is to delete the paragraph that needs it.

## P1 — Required for submission (lines 91–138)

- **P1-1 (lines 93–102)** — add B.3a, the second failed prediction. Applied.
- **P1-2 (lines 104–109)** — disclose uneven registration strength: "A reviewer who spots it unaided discounts the whole appendix." Applied.
- **P1-3 (lines 111–116)** — Appendix A.2 environment spec: CPU, cores, RAM, OS, Python, torch, llama-server build. "Our central claim is a wall-clock ratio; ratios travel better than absolutes but the reviewer still needs the box." **Not yet done.**
- **P1-4 (lines 117–130)** — close or state the four provenance gaps: A.5.3 (MLVU no commit — re-stamp or re-run), A.5.1 (dense arm did not run its own ingest — confirm or attach the caveat to every appearance of 1,104×), A.5.2 (mpeg4 not H.264 — "a paper about compressed-domain signals should say it rather than let a reader find it"), A.5.5 (dirty trees — re-run clean, or extend per-script SHA-1 hashing everywhere).
- **P1-5 (lines 132–138)** — settle the mIoP/IoP question. Recommendation: **omit them**, since they are union-convention, not comparable to leaderboard figures, and fixing that needs a re-run because the dump keeps no predicted spans.

## P2 — Improvements (lines 142–176)

**P2-1 (lines 144–155) — §3.2, one clause on scene identity.** A subtle landmine: the codebase has **two
different notions of "scene"** — the ingest-assigned `scene_id` on frame records, and a separate
I-frame-derived numbering that `l2_asphodel._refresh_scene_ids` writes onto graph nodes. Retrieval uses
the **former** throughout, so no reported result is affected. But one clause in §3.2 saying which one is
meant pre-empts the question.

The parenthetical is the sharpest engineering observation in the bundle: "*rename the graph-node field or
comment it, so nobody later assumes it matches the block partition. **Nothing reads it today, which is
precisely what makes it a landmine.***" An unused field that looks authoritative is more dangerous than a
wrong one, because nothing will fail until someone trusts it.

**P2-2 (lines 157–161) — §8.8, use the sourced sentence.** Replace the current shortlist limitation
wording with the artifact's own evidenced line: top-k is flat across 8/12/16/24, so "the candidate set is
NOT the constraint; residual loss is representational."

**P2-3 (lines 163–169) — §5.1, resolve the salience-weight caveat (may be backwards).** The dataclass
defaults **are** 0.5/0.3/0.2 and the shipped JSON overrides none of them, so either 0.8/0.1/0.1 lives
outside the repo or the caveat is reversed. "**Do not print a disclaimer of a deviation that did not
occur.**"

**P2-4 (lines 171–175) — §2, three literature gaps.** A second graph-based system, direct verification of
the NG+ variants, and the compressed-domain citation line. "All parallelisable" — i.e. hand them to
different people.

## Sequencing (lines 179–191)

**Lines 181–186** — the order, chosen by effort-versus-payoff:
1. **P0-1, P0-2** — half a day, no re-runs, closes the sharpest objection. Best value first.
2. **P1-1, P1-2** — one hour, strengthens the appendix that most distinguishes the paper.
3. **P1-5** decision, then P1-3/P1-4 (partly blocked on the repo push).
4. **P2** as time allows; P2-3 needs a person who knows the history.
5. **Abstract last**, once P0 and P1-5 are settled — "those determine what it can claim."

The abstract-last rule is important and correct: the abstract is a promise, so you can only write it once
you know what the body can deliver. This is why `00_abstract.md` is dated 08-19 while the intro is dated
08-15.

**Lines 188–191** — "**Not in this pass, deliberately:** the four build-path optimisations (double build, `hierarchical_sparse` materialise-then-prune, boundary-node orphaning, top-k/vectorisation). None improves the 220× ratio, one changes retrieval behaviour, and all would re-open verified code before submission. They are the follow-up's natural spine."

Three reasons for saying no, all sound: no benefit to the headline, one would change behaviour (so
results would need re-running), and all would invalidate code that has already passed the identity gate.
Deferring is the right engineering call, and stating *why* stops the question being re-asked every week.

---

# Putting it all together — the short version

**What IRIS does:** reads a long video once (throwing away ~89% of frames), splits the survivors into
scenes, builds a graph connecting frames **only within the same scene**, and then answers text questions
by shortlisting scenes, ranking frames with query-biased PageRank, captioning the top 30, and feeding
those captions to a small CPU language model.

**The one big claim, which holds up:** building only the within-scene blocks produces a graph that is
**bit-for-bit identical** to building everything and deleting the cross-scene parts — verified six ways —
while being **220× faster** and using **6.7× less memory**. Plus, beyond a certain size, the dense
version simply never finishes.

**The four things they admit:**
1. The speedup does not reach the user — captioning dominates, so end-to-end they were actually *slower* (0.778×) at the size they measured.
2. Their sparse retrieval costs +9.30 s per query in extra captioning, because it returns query-specific frames that cannot be cached — the dense arm caches well only because it ignores your question.
3. Accuracy is 16.7%, in the weakly-supervised band, ~12 points behind the best current systems.
4. Two of their own core ideas — codec-based scene cutting and codec-based frame selection — were tested against fair controls and **both failed**.

**What the whole bundle is really about:** the difference between a number and a *trustworthy* number.
The ledger, the `[TODO]` rule, the identity gate, the pre-registration appendix, the artifact sweep, the
"dirty tree" confessions, and the repeated warnings about the phantom 4.6× figure are all the same
instinct — every claim must be traceable to a file on disk, with its warnings still attached.

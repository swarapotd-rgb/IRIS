# Qualitative check: what `_build_focus_hint` actually does to a caption

Same frame (video `10109097475`, decoded frame 120), same captioner
(minicpm-v4.6, temperature=0, seed=42). The only difference is whether
`focus_hint` was passed.

Question used for the hint (illustrative, not from this video's gold set):
*"what did the boy in red do after standing up"*
choices: ran away / sat down / clapped / jumped / waved

## Question-blind (the frozen baseline path)

```
An airplane is present on a runway.
People are standing near the aircraft.
A building is visible in the background.
The sky is overcast with clouds.
Grass is seen to the left of the runway.
A person is walking in the distance on the right.
```

## Question-aware (`focus_hint` passed)

```
The boy in red stood and then appeared to run away after standing up.
A large airplane is present on the tarmac, suggesting airfield activity.
Several people are visible near the aircraft, likely engaged in ground operations.
The runway and surrounding grassy areas are clearly shown, indicating an active
airport setting.
```

## Why this matters for how Phase 3 must be read

The hint plainly reaches the captioner — the two texts are not identical, so
Arm E is measuring a real change, not a no-op flag.

But look at what changed. The question-aware caption **leads with a sentence
that restates the question and asserts one of the multiple-choice options**
("appeared to run away after standing up") for a frame whose actual content is
an airplane on a runway. There is no boy in red. The captioner did not find
better visual detail; it wrote the question back out as though it were an
observation.

This is exactly the failure mode Arm G exists to detect, and it is present at
the text level before any accuracy number is computed.

It also complicates the E-vs-G reading in a way worth stating up front:

- **E ≈ G** would mean the gain is leakage, as the task specifies.
- **E > G**, however, is consistent with *two* different stories. It could be
  genuine visual grounding. But it is equally consistent with leakage plus
  mismatch: in Arm E the leaked sentence restates the question actually being
  answered, while in Arm G it restates a *different* question from the same
  video and is therefore actively misleading. Under that story E beats G with
  no visual grounding involved anywhere.

So E > G alone does not establish grounding. It has to be read together with
the caption-quality table (does the new caption carry more action/temporal
content, or just more question text?) and with E vs A.

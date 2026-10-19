# 07 · Canary release: a bad prompt reaching 10% of users

Prompt v3 has a bug that often skips `place_order`. It goes to 10% of users, and the point of
the exercise is how little data a large effect needs.

**Problem.** Every release carries a risk you did not find before shipping. You can reduce the
chance of the bug, or you can reduce the number of users who meet it. The second is cheaper
and works for bugs you did not anticipate.

**Idea.** Route a small slice of users to the new version, compare it against the current one
on the same window, and roll back automatically when it looks worse. The canary needs no new
measure, only a comparison: `CanaryCompletionDrop` reuses the per-arm recording rule from
[06](../06-ab-experiment/) and fires when a non-`v1` arm sits 10 points below `v1`.

## What the code shows

`demo.sh` (output in [`transcript.txt`](transcript.txt)) sets the canary to 10% and watches.

1. `v3` completes 53.5% of its conversations against `v1`'s 76.6%, 23 points below and far
   past the 10-point trigger.
2. `CanaryCompletionDrop` fires within about a minute, while the overall rate moves from 76.8%
   to 74.8%. Ten percent of users carrying a 23-point drop costs 2 points in aggregate, which
   is inside the noise of the headline number.
3. Rolling back returns completion to 75.8% and clears the alert.

The aggregate dashboard almost misses this. The per-arm comparison catches it because it
does not average the arms together.

Notebook section 8 shows the sample size. An effect this large needs only a few hundred
conversations per arm for a confidence interval that excludes zero, which is why a canary can
be small and short.

## Blast radius

Ask the class to put numbers on it. Ten percent of users, for the minute or two before the
alert fires and the rollback lands. Then ask what the same bug would have cost at 100%, and
what it would have cost if the only signal had been the headline completion rate.

```sh
./demo.sh
```

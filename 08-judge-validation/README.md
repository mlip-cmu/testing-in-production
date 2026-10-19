# 08 · Who validates the validator?

The dashboard reports a judge fail rate. That number is the output of a model, and no one has
checked it. This project checks it against 16 hand-labeled traces and corrects the dashboard.

**Problem.** An LLM judge turns an unanswerable question ("was this conversation good?") into
a number on a dashboard. The number inherits every error the judge makes, and those errors are
not symmetric: on a population where true failures are rare, even a small false-positive rate
dominates the reported rate. A team that trusts the raw number will chase failures that did
not happen.

**Idea.** Treat the judge as a classifier and measure it like one. Label a small sample by
hand, compute the judge's true positive and true negative rates against those labels, then
invert the relationship to recover the true failure rate from the observed one.

## The measure

For a judge with true positive rate *s* (sensitivity) and true negative rate *t*
(specificity), the observed fail rate *o* on a population whose true failure rate is *p* is

```
o = p·s + (1 − p)·(1 − t)
```

Solving for *p* gives the corrected estimate `p = (o − (1 − t)) / (s − (1 − t))`. The script
estimates *s* and *t* from the 16 labels and applies the correction to whatever the dashboard
currently reports, so a sizeable part of the reported rate turns out to be the judge's own
false alarms.

The simulator's judge really does catch 85% of failures and falsely flag 5% of good
conversations (`simulator/engine.py`). The 16 traces estimate both at 88%, which is the
second lesson: the measurement of the judge is itself a measurement, with its own error.

## What the code shows

`validate_judge.py` (output in [`transcript.txt`](transcript.txt)) reads the 16 traces in
[`../notebook/traces_sample.json`](../notebook/traces_sample.json), compares each judge verdict
against its human label, and prints the confusion matrix, the rates, and the correction applied
to the current dashboard number.

1. The judge agrees with the humans on 14 of 16 traces, which sounds like plenty.
2. The two disagreements are not interchangeable. `t07` is a missed `wrong_item` failure and
   `t09` is a false alarm on a good conversation, and they move the corrected rate in opposite
   directions.
3. Both sensitivity and specificity come out at 88%, each on a sample of 8, with a 95% Wilson
   interval of [53%, 98%]. That interval is the finding: sixteen traces cannot tell 88% from
   60%, so the correction they support is barely a correction.

Ask the class what sample size would make the interval useful, and who on the team labels it.

**The example verdicts in `traces_sample.json` were written by hand for teaching**, including
two deliberate judge mistakes. They are not output from a real model. With `ANTHROPIC_API_KEY`
set, notebook section 9 calls a Claude model to judge the same traces for real, and the class
can compare.

```sh
uv run validate_judge.py
```

# 06 · A/B experiment: why the dashboard cannot decide it

An upsell prompt raises order value and costs a little completion. The dashboard shows both
within a minute, and the dashboard is still the wrong place to decide.

**Problem.** Sliding-window averages answer "what is happening now". An experiment asks "is
this variant better", which needs a unit of analysis, a planned sample size, an interval, and
a rule fixed before you look. Reading an experiment off a dashboard invites the two classic
errors: analyzing conversations when you randomized users, and stopping the moment the line
separates.

**Idea.** Watch it on the dashboard to catch a disaster, then analyze it properly in the
notebook. The demo here does the first; [`../notebook/lecture_notebook.ipynb`](../notebook/)
section 7 does the second.

## The measure

Claims one variant beats another on traffic that is otherwise identical. Assignment hashes the
user ID per experiment layer so a user keeps an arm across conversations, and the arm rides on
every conversation record, which is the entire collection cost. The dashboard computes
`agent:completion_rate_by_prompt:1m` and order value per arm, which is enough to watch the
arms but not to decide the experiment.

## What the code shows

`demo.sh` (output in [`transcript.txt`](transcript.txt)) runs the upsell prompt at 50% for ten
simulated days and reads the arms.

1. Traffic splits 50.9/49.1, which is the sample ratio check. A split that drifts from its
   target means assignment is broken, and every result after that is suspect.
2. `v2-upsell` lifts order value from $24.68 to $29.37, about 19%, and costs 2.8 points of
   completion (75.2% against 77.9%).
3. Refunds for `v2-upsell` run at 5.6% against 2.6% for `v1`, more than double. That is the
   guardrail metric, and the reason order value alone cannot settle the question: the arm that
   sells more also breaks more orders.
4. No alert fires for any of it. An experiment is not an incident, and nothing here tells you
   whether the difference is real.

Then the notebook, on the committed 30-day sample so it reproduces exactly:

- per-user Welch t-test with a confidence interval, not per-conversation;
- guardrail metrics and net value, so the decision accounts for refunds;
- power analysis: how many users this effect needed;
- an A/A test where both arms are identical, showing that peeking daily inflates the false
  positive rate from about 3% to about 19%.

## Tools

- [statsmodels](https://www.statsmodels.org) and [SciPy](https://scipy.org) for the tests and
  intervals, in the notebook.
- The control panel's `upsell_experiment_pct`, driven here through `../tools/scenario.py`.

```sh
./demo.sh                                         # the dashboard view
cd ../notebook && uv run jupyter lab lecture_notebook.ipynb    # the analysis
```

To analyze the run you just did rather than the committed sample, start the notebook with
`NOTEBOOK_MODE=live`, which reads `../data/events/`.

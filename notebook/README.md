# Notebook: the analysis a dashboard cannot do

Sliding-window averages answer "what is happening now". Four questions in this lecture need
something else, and they live here:

| Section | Question | Project |
|---|---|---|
| 1-6 | what the scenarios did to the data, day by day | all |
| 7 | is the upsell variant actually better? | [06-ab-experiment](../06-ab-experiment/) |
| 8 | how few conversations does a canary need? | [07-canary](../07-canary/) |
| 9 | is the LLM judge right often enough to trust? | [08-judge-validation](../08-judge-validation/) |

Section 7 is the heart of it: a sample ratio check, per-user Welch t-tests with confidence
intervals, guardrail metrics and net value, a power analysis, and an A/A test where both arms
are identical, showing that peeking daily inflates the false positive rate from about 3% to
about 19%.

```sh
uv run jupyter lab lecture_notebook.ipynb                     # the committed 30-day sample
NOTEBOOK_MODE=live uv run jupyter lab lecture_notebook.ipynb  # the run you just did
```

The notebook is committed with its outputs, and `lecture_notebook.html` is an offline export
for when the live demo fails. It reads `../data/sample/` by default, a 30-day replay of a
scripted scenario (`../simulator/offline.py`): A/B test on days 5-13, stale menu 8-14, Honolulu
from 10, exploration off from 13, shadow test 14-16, LLM upgrade 16-18, canary on 19, injection
campaign from 21, flywheel from 22, guardrail from 24, API outage on day 26.

Edit `build_notebook.py` and re-run it rather than editing the `.ipynb` by hand.

Section 9 calls a Claude model to judge traces only if `ANTHROPIC_API_KEY` is set; otherwise it
uses example verdicts stored in `traces_sample.json`. **Those example verdicts were written by
hand for teaching**, including two deliberate judge mistakes, and are not output from a model.

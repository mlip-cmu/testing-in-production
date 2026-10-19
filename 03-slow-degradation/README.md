# 03 · Slow degradation: four failures that never jump

Jump alerts compare now against a few minutes ago. Every failure in this project arrives too
slowly for that comparison to notice, and each needs a different kind of signal.

**Problem.** The release-shaped failure in [02](../02-release-jump/) is the easy case,
because it has a before and an after. A menu index that goes stale 3% per day, a city that ramps to 30% of
traffic over three days, a recommender that narrows over a week, and an attacker who rephrases
until the detector stops matching all look like normal operation from one minute to the next.

**Idea.** Four scenarios, four signals that work on different principles: a trend alert that
compares against last week, a distributional test against a reference window, a nightly
aggregate over a recommendation log, and a cheap detector whose decay is itself the finding.

## The scenarios and their measures

**Menu sync stops.** The nightly job that copies restaurant menus into the agent's search
index fails silently, and the index goes stale ~3% per simulated day. The agent's knowledge of
the menu is a *cache*, which is why it can quote a price that no longer exists; the invariant
in [04](../04-invariants/) compares that cache against the source of truth. Violations and
corrections climb over 2-3 minutes, refunds follow 1-3 simulated days later.
`InvariantViolationsHigh` fires. `CompletionRateJump` does not, because nothing jumps;
`CompletionBelowLastWeek` compares a 10-day window against a week earlier and catches the
slope.

**Launch in Honolulu.** A new city ramps to 30% of traffic with cuisines and phrasing the
agent rarely saw. The drift measure claims the inputs no longer look like a reference period.
The job in [`../drift/`](../drift/) collects nothing new, reading the same conversation log,
but it does need a stored reference window that somebody chose. It compares the last simulated
day against a fixed two-day reference over five input and four output columns using Evidently's
PSI, and needs 200 rows before it reports. Per column, PSI above 0.1 counts as drift;
`DataDriftDetected` fires once more than 25% of columns are drifting.

Drift says the distribution moved, never that quality fell. Reset the reference and the alert
clears while Honolulu conversations stay worse, at completion ~69% against ~78% elsewhere,
with corrections and judge failures up by half. Nothing on the stock dashboard attributes that to a
city, because no quality metric carried a `city` label until someone added one. The reset
takes two simulated days to take effect, so press it and wait before deciding it failed.

**Surprise me stops exploring.** With exploration off, the recommender learns only from its own
choices. Coverage collapses over 3-4 minutes and the top five restaurants absorb nearly all
recommendations, while acceptance barely moves, so engagement dashboards stay green. A nightly
job aggregates yesterday's recommendation log into `surprise_catalog_coverage`;
`SurpriseCatalogCollapse` fires below 40%. Coverage needs that log, which teams keep for
debugging and rarely aggregate.

**Injection campaign.** Two measures disagree on purpose. The flag rate claims a request looked
like an attack, collected by scoring the incoming request with a heuristic, which is cheap and
immediately gameable. Recall decays as attackers rephrase, so the flag rate falls while the
attack continues. The discount invariant claims an order broke policy and does not care how
the attack was worded. Deploying the guardrail drops violations, which then creep back up over
a few days as attackers adapt.

## What the code shows

`demo.sh` (output in [`transcript.txt`](transcript.txt)) runs all four in sequence, resetting
between them.

1. Stale menu: item-not-on-menu and price-mismatch violations climb, `InvariantViolationsHigh`
   fires, `CompletionRateJump` stays quiet, refunds rise last.
2. Honolulu: `city` and `cuisine` PSI cross 0.1, `DataDriftDetected` fires, and completion by
   city shows the gap the aggregate hides.
3. Exploration off: coverage falls below 40% while acceptance holds.
4. Injection: discount violations and flags rise together, then the flag rate decays while
   violations continue.

## Tools

- [Evidently](https://www.evidentlyai.com/): the drift report in `../drift/drift_job.py`,
  method `psi`, exported as `drift_column_score{column,kind}`.
- Prometheus `offset` for the trend alerts: `CompletionBelowLastWeek` compares `[5m]` now
  against `[5m]` one simulated week ago.

```sh
./demo.sh
```

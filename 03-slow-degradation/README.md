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

1. **Stale menu.** Corrections climb to 0.385 per conversation from a baseline near 0.13,
   completion slides to 72.1%, and refunds reach 10.0% of orders against a 2.5% baseline.
   `InvariantViolationsHigh` and `RefundRateHigh` fire; `CompletionRateJump` stays quiet,
   because nothing jumps.
2. **Honolulu.** `city` reaches PSI 0.46 and `cuisine` 0.48, both far past the 0.1 per-column
   threshold, while completion by city reads 70.0% in Honolulu against 77.4% and 76.8% in the
   other two. `DataDriftDetected` fires on a column share of 22.2%.

   Reset the reference while the city stays launched and the alert clears within three
   simulated days, with the column share back to 0.00% and Honolulu still completing 65.9%
   against 79.8% and 74.5% in the other two cities. The alert was answering a question about
   distributions, and it answered correctly both times.

   That 22.2% is worth a minute of class time. The alert triggers on the *share* of drifting
   columns, and this scenario moves exactly 2 of the 9 monitored ones, however long it runs:
   over 18 simulated days `city` climbs past PSI 2.8 while the third-ranked column never
   reaches 0.1. The threshold sits at 0.2 so that two columns are enough. At the 0.25 it
   started with, a city launch could not have raised the alert at all, no matter how far those
   two columns moved. Ask the class what a column-counting threshold assumes about the
   columns, and what it would take for three mild drifts to matter more than two severe
   ones.
3. **Exploration off.** Coverage falls to 9.6% and the top five restaurants take 95% of
   recommendations, while acceptance holds near 60%. `SurpriseCatalogCollapse` fires, and
   every drift column stays under 0.04: the feedback loop changes *which* restaurants get
   recommended without changing the distribution of anything the drift job watches. A
   measure built for input drift is blind to this one.
4. **Injection.** Flags reach 2.3% of requests and discount violations 2.5% of orders. Five
   simulated days later the flag rate has decayed to 1.2% while violations have risen to 2.7%,
   so the detector stopped seeing an attack that was getting worse. The guardrail then brings
   violations down to 1.4%.

## Tools

- [Evidently](https://www.evidentlyai.com/): the drift report in `../drift/drift_job.py`,
  method `psi`, exported as `drift_column_score{column,kind}`.
- Prometheus `offset` for the trend alerts: `CompletionBelowLastWeek` compares `[5m]` now
  against `[5m]` one simulated week ago.

```sh
./demo.sh
```

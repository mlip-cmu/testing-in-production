# 02 · Release jump: the provider swaps the model under you

The model vendor upgrades the LLM. Nobody on the team deployed anything, and the agent gets
faster and more expensive on the same day. This project runs the upgrade, then rewinds and
shows what a shadow release would have told you first.

**Problem.** A release you did not make is still a release. The new model is quicker and
wordier, costs about 35% more per order, dips completion by ~4 points, and grants discounts
beyond policy about three times as often. Users see only some of that, and the
cheapest signal to read is the one about money.

**Idea.** Two ways to find out. The expensive way is to notice in production after users are
affected. The cheap way is a **shadow release**: run the candidate on the same requests,
discard its answers, and check the invariants against what it *would* have done.

## The measures

**Cost per order.** Token counts come free with every API response, so collection costs
nothing; the ratio divides LLM spend by orders (`agent:cost_per_order:1m`, alert above
$0.058) and moves when either side changes.

**The discount invariant.** Claims the agent granted money off that no rule entitled the
customer to. A real check reads the discount off the order and asks the promotions service
what this cart was entitled to. No labels, no judge, no waiting. Computed as
`agent:violations_per_order:1m{check="discount_policy"}`, alert above 1% of orders.

**Shadow comparison.** Claims what the candidate *would* have done on live traffic. Collecting
it means running the candidate on the same request and discarding its answer, which doubles
inference cost on shadowed traffic and requires that nothing in its path has side effects. The
invariant checks then apply to a shadow order exactly as they apply to a real one, so the
comparison needs no labels. Computed as `shadow:discount_violation_rate:1m` against
`agent:discount_violations_per_conversation:1m`; `ShadowModelDiscountViolations` fires above
0.8% of shadowed conversations.

## What the code shows

`demo.sh` (output in [`transcript.txt`](transcript.txt)) runs the shadow test first, as a team
should, and only then does the upgrade for real.

1. **Shadow.** For ten simulated days the candidate runs beside production, violating
   discount policy on about 1% of shadowed conversations against production's 0.2%, a gap
   of roughly 4-5×, and `ShadowModelDiscountViolations` fires. No user has seen any of it.
   The two models disagree on 14% of conversations, which is a different and much larger
   number, and answers a different question.
2. **Upgrade.** Cost per order rises from $0.045 to $0.062, about 38%, and `CostPerOrderHigh`
   fires. Discounts beyond policy go from 0.41% to 1.06% of orders.
3. **What stays quiet.** `CompletionRateJump` does not fire. Completion falls from 78.2% to
   74.1%, a relative drop of 5.3% against its 7% threshold. Ask whether the threshold is
   wrong, or whether a 4-point drop deserves a page.

   `DiscountPolicyViolations` is a coin flip here, and worth showing as one. Its threshold is
   1% of orders and the new model lands near there, so it fires in some runs and not in this
   one. Rare events read through a one-minute window sit badly next to a fixed threshold,
   which is the same problem the shadow alert had and the reason that one moved to 5m.
4. **Rollback.** Pinning the old model clears the alerts within three simulated days.

The alert reads a `[5m]` window, about ten simulated days, for the same reason the panel
does. Discount violations are rare enough that the 1-minute ratio swings either side of the
0.8% threshold from window to window, while the 5-minute one holds steady near 1.2%. Rare
events and short windows make flaky alerts, and the fix is the window rather than the
threshold.

The shadow numbers are noisy on purpose. Violations are rare, so a single ten-day window often
reads nearer 2.5× even though the engine draws exactly 4×. Quote the direction, not the digit.

## Tools

- The control panel's `llm_upgraded` and `shadow_new_llm` switches, driven here through
  `../tools/scenario.py`.
- The shadow panel in Grafana puts both discount lines on the left axis and model disagreement
  on the right, because disagreement runs about ten times larger and would flatten the rest.

```sh
./demo.sh
```

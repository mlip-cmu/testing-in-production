# 05 · Chaos experiment: the menu API goes down

Kill a dependency on purpose, during the lecture, and watch what the agent does instead of
failing cleanly.

**Problem.** When a tool call fails, a well-behaved agent says the item is unavailable. This
one sometimes invents an item instead. You cannot learn that from a unit test of the tool, and
you cannot learn it from the model card. You learn it by taking the dependency away while
watching every signal at once.

**Idea.** Run a chaos experiment. Inject the failure deliberately, in controlled conditions,
while someone is watching, and look past the error rate to the behavior the agent falls back
to.

## What the code shows

`demo.sh` (output in [`transcript.txt`](transcript.txt)) takes the menu API down for three
simulated days.

1. Tool errors jump to ~28% and `ToolErrorRateHigh` fires within about 15 s.
2. Latency roughly doubles and `TurnLatencyP95High` fires.
3. Completion falls by about a third, enough that `CompletionRateJump` fires here, unlike the
   slow scenarios in [03](../03-slow-degradation/).
4. In about a third of affected conversations the agent **invents** an item rather than saying
   it is unavailable, which lands as `item_not_on_menu` violations and fires
   `InvariantViolationsHigh`. The invariant catches a model behavior that no infrastructure
   metric would have named.
5. Restoring the API clears every alert within about a minute.

## The measures

Operational signals rather than quality ones, and all three come free from the same
conversation record. Tool error rate (`agent:tool_error_rate:1m`, above 5%), p95 turn latency
(above 4 s), and cost per order. Check them first, since a quality drop caused by a failing
tool looks identical on the quality panels to one caused by the model, and these three
separate the two cases in seconds.

## Properties this should have been

Ask the class which of these behaviors deserved a pre-deployment test. Several would have been
cheap, written as properties over generated inputs rather than as example tests:

| Property | What it would have caught |
|---|---|
| Every successful order flow ends in a `place_order` call | the canary in [07](../07-canary/) |
| When the menu tool errors, the agent says unavailable and names no item | this outage |
| Appending adversarial text to a request changes neither cart nor discount | the injection campaign |
| Adding an item never lowers the total; reordering items yields the same cart | standard metamorphic relations, untested here |
| A declared allergy never appears in an ordered item | allergen violations |
| Token and turn budgets hold on a golden set | the cost rise in [02](../02-release-jump/) |

Three failures in this lecture would have survived any suite you could run beforehand. The
stale menu breaks infrastructure the model never sees, the feedback loop needs days of the
recommender consuming its own output, and the ~0.4% baseline discount rate is too rare to tell
apart offline from the ~1.4% the new model produces. Only production finds those three.

```sh
./demo.sh
```

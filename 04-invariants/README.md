# 04 · Invariants: checks that need no labels

Every other signal in this repo waits for something: a sampled judge, a refund three days
later, enough traffic for a rate to settle. Invariants answer immediately, because a system
somewhere already knows the right answer.

**Problem.** Most quality questions about an agent need a label, and labels are slow,
expensive, or both. Asking "was this conversation good?" needs a human or a judge model.
Asking "did we ship the wrong food?" needs a refund to arrive.

**Idea.** Some questions do not need a label at all. The menu service knows what is on the
menu. The pricing service knows the price. The promotions service knows what discount this
cart was entitled to. The allergy is on the user's profile. Re-check the finished order
against those systems and a violation names its own cause.

## The measure

Each check claims the finished order is consistent with a system that already knows the
answer. A deployment collects it by re-checking the logged order against the menu and pricing
services, in the response path or asynchronously afterward, and the check is ordinary code
with no model in it. No labels, no sampling, no judge, and a violation names its own cause.
Computed per order as `agent:violations_per_order:1m`; `InvariantViolationsHigh` fires above
2% of orders for the menu and price checks, `DiscountPolicyViolations` above 1% for discounts.

| Check | Claims | Broken by |
|---|---|---|
| `item_not_on_menu` | every ordered item exists on the live menu | stale index, menu API outage |
| `price_mismatch` | the quoted price matches the live price | stale index |
| `discount_policy` | the discount was one the cart was entitled to | model error, prompt injection |
| `allergen` | no item contains a declared allergen | model error |

This simulator fakes the discount check: no policy rule exists in the code, and the engine
flags a violation and attaches a discount of 20-50% of order value for a model error, or
60-100% for a successful injection. Both causes produce the same violation, which is why the
alert text hedges between a model change and an attack.

Invariants catch a stale menu and stay blind to an agent that is merely unhelpful. That is the
trade they make for needing no labels.

## More invariants worth writing

Four checks ship here. A production agent would want more, roughly in order of how cheap they
are to write:

- **Total arithmetic.** Line items minus discount plus tax and fees must equal the amount
  charged. No service call is needed, and it catches every mis-summed cart.
- **Quantity and total caps.** No zero quantities, no 99 burritos, nothing above a ceiling.
- **One order per conversation.** A retried or duplicated `place_order` is a common
  tool-calling failure, and none of the metrics here would show it.
- **Confirmation before charging.** The transcript must contain a user confirmation before
  `place_order`, a structural check rather than a judgement call.
- **Restaurant availability.** Open, and delivering to that address, at the moment the order
  goes in.
- **Account ownership.** The payment method and delivery address belong to the requesting
  user. Violating this one is a security incident rather than a refund.
- **Price groundedness.** Every price the agent states appears in the retrieved menu context,
  which catches an invented price before the customer sees the bill.

## What the code shows

`demo.sh` (output in [`transcript.txt`](transcript.txt)) breaks two different things and shows
that the violations point at different causes.

1. A stale menu takes `item_not_on_menu` to 16.9% of orders and `price_mismatch` to 10.6%,
   and leaves discounts at 0.6%.
2. An injection campaign takes `discount_policy` to 3.4% of orders, and leaves both menu
   checks at exactly 0.0%.
3. The allergen check stays near its 1% baseline throughout, because nothing in either
   scenario touches it.

Each cause lights up its own checks and nothing else, which is what "a violation names its own
cause" means in practice. Note how long the counters remember: a `[1m]` rate covers about two
simulated days, so `demo.sh` lets the windows clear after each reset before reading a
baseline. Without that wait the first reading is the previous scenario's tail.

```sh
./demo.sh
```

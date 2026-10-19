"""
Simulation engine for the food ordering agent.

The engine produces *conversation outcome records* (not real conversations):
what the agent was asked, which prompt/LLM version handled it, how many turns
and tool calls it took, what was ordered, and which problems occurred.

Every failure scenario from the lecture is a switch in `Switches`. Effects are
deliberately simple and exaggerated so they are visible on a dashboard within
a few simulated days.

Fields prefixed with `truth_` are hidden ground truth. A real team would NOT
have them; they exist so the class can compare what telemetry shows with what
actually happened.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field, asdict

CUISINES_CORE = ["pizza", "thai", "mexican", "indian", "burgers", "sushi", "salads", "chinese"]
CUISINES_NEW_CITY = ["poke", "hawaiian", "japanese", "plate_lunch"]
CITIES_CORE = ["Pittsburgh", "Philadelphia"]
NEW_CITY = "Honolulu"
INTENTS = ["order_specific", "browse", "surprise_me", "modify_order", "complaint"]
INTENT_WEIGHTS = [0.40, 0.15, 0.25, 0.11, 0.09]

LLM_OLD = "llm-2026-05"
LLM_NEW = "llm-2026-09"
PROMPT_CONTROL = "v1"
PROMPT_UPSELL = "v2-upsell"
PROMPT_CANARY = "v3"

FAILURE_MODES = ["give_me_more_loop", "wrong_item", "ignored_allergy", "unhelpful_reply"]

# Illustrative LLM prices in USD per million tokens (not any real provider's).
PRICE_IN = 3.0
PRICE_OUT = 15.0

# Conversations per simulated hour (before the daily load curve).
BASE_CONV_PER_HOUR = 60

# "Surprise me" recommender
EXPLORE_RATE = 0.35
EXPLOIT_POWER = 2.0


def _bucket(key: str) -> int:
    """Stable 0..99 bucket, like a feature-flag service would compute."""
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % 100


def load_curve(hour: float) -> float:
    """Relative traffic by hour of day: lunch and dinner peaks, quiet nights."""
    lunch = math.exp(-((hour - 12.5) ** 2) / 3.0)
    dinner = 1.4 * math.exp(-((hour - 18.5) ** 2) / 4.0)
    return 0.25 + lunch + dinner


@dataclass
class Switches:
    # Stale model: the nightly job that syncs the menu index silently stops.
    menu_sync_paused: bool = False
    # Jump after release: provider silently upgrades the LLM behind the alias.
    llm_upgraded: bool = False
    # Data drift: launch in a new city (traffic share ramps up over ~3 days).
    new_city_launched: bool = False
    # Adversaries: prompt-injection campaign for free discounts.
    injection_campaign: bool = False
    injection_guardrail: bool = False
    # Chaos experiment: menu API goes down.
    menu_api_outage: bool = False
    # Feedback loop: "Surprise me" exploration (on = healthy).
    surprise_exploration: bool = True
    # ML flywheel: mine judge-flagged production failures into eval set / few-shots.
    flywheel: bool = False
    # Shadow release: run llm-2026-09 in shadow next to production.
    shadow_new_llm: bool = False
    # A/B experiment and canary, as percentages of users.
    upsell_experiment_pct: int = 0
    canary_v3_pct: int = 0


@dataclass
class Restaurant:
    rid: str
    city: str
    cuisine: str
    quality: float
    opened_day: float
    popularity: float = 1.0  # what the "Surprise me" model has learned from its own click logs
    surprise_today: int = 0  # accepted "Surprise me" recommendations today
    recommended_today: int = 0  # "Surprise me" recommendations shown today
    explore_accepted_today: int = 0  # accepted among randomly explored recommendations


@dataclass
class User:
    uid: str
    city: str
    fav_cuisine: str
    has_allergy: bool
    seen: set = field(default_factory=set)


class Engine:
    def __init__(self, seed: int = 7, n_users: int = 3000):
        self.rng = random.Random(seed)
        self.sw = Switches()
        self.sim_time_h = 0.0  # simulated hours since start
        self.conv_counter = 0
        self.pending_refunds: list[dict] = []

        # state for gradual effects (in simulated days)
        self.menu_stale_fraction = 0.0
        self.new_city_share = 0.0
        self.injection_intensity = 0.0
        self.campaign_age_days = 0.0
        self.guardrail_age_days = 0.0
        self.failure_rates = {"give_me_more_loop": 0.04, "wrong_item": 0.03,
                              "ignored_allergy": 0.03, "unhelpful_reply": 0.03}
        self.failure_counts_today = {m: 0 for m in FAILURE_MODES}
        self.last_day = 0

        self.restaurants: list[Restaurant] = []
        for city in CITIES_CORE:
            for i in range(30):
                self._open_restaurant(city, self.rng.choice(CUISINES_CORE), opened_day=-30)
        self.users: list[User] = []
        for i in range(n_users):
            city = CITIES_CORE[i % 2]
            self.users.append(User(f"u{i:05d}", city, self.rng.choice(CUISINES_CORE),
                                   self.rng.random() < 0.12))
        self.new_city_users = [User(f"h{i:05d}", NEW_CITY, self.rng.choice(CUISINES_NEW_CITY),
                                    self.rng.random() < 0.12) for i in range(800)]
        self.new_city_opened = False
        self.surprise_stats = {"recs": 0, "accepted": 0, "repeat": 0, "new": 0}
        self.last_day_summary = self._empty_day_summary()

    # ------------------------------------------------------------------ helpers
    @property
    def sim_day(self) -> float:
        return self.sim_time_h / 24.0

    def _open_restaurant(self, city, cuisine, opened_day):
        rid = f"r{len(self.restaurants):03d}"
        self.restaurants.append(Restaurant(rid, city, cuisine,
                                           quality=self.rng.gauss(0, 0.6),
                                           opened_day=opened_day))

    def _empty_day_summary(self):
        return {"coverage": 1.0, "top5_share": 0.1, "new_restaurant_share": 0.1,
                "acceptance": 0.6, "repeat_rate": 0.1}

    def llm_for(self, user: User) -> str:
        return LLM_NEW if self.sw.llm_upgraded else LLM_OLD

    def prompt_for(self, user: User) -> tuple[str, str, str]:
        """Two experiment layers with independent hashing (see concurrent A/B slide).
        Canary layer takes precedence over the upsell experiment layer."""
        canary_arm = "treatment" if _bucket("canary-v3:" + user.uid) < self.sw.canary_v3_pct else "control"
        upsell_arm = "treatment" if _bucket("exp-upsell:" + user.uid) < self.sw.upsell_experiment_pct else "control"
        if canary_arm == "treatment":
            return PROMPT_CANARY, upsell_arm, canary_arm
        if upsell_arm == "treatment":
            return PROMPT_UPSELL, upsell_arm, canary_arm
        return PROMPT_CONTROL, upsell_arm, canary_arm

    # ------------------------------------------------------------ daily update
    def _end_of_day(self, day: int):
        """Nightly jobs: retrain Surprise-me popularity, open restaurants, flywheel."""
        open_rs = [r for r in self.restaurants if r.opened_day <= day]
        # catalog metrics are computed over what the recommender *showed*
        total = sum(r.recommended_today for r in open_rs) or 1
        shown = [r for r in open_rs if r.recommended_today > 0]
        top5 = sum(sorted((r.recommended_today for r in open_rs), reverse=True)[:5])
        new_recs = sum(r.recommended_today for r in open_rs if day - r.opened_day <= 7)
        s = self.surprise_stats
        self.last_day_summary = {
            "coverage": len(shown) / max(1, len(open_rs)),
            "top5_share": top5 / total,
            "new_restaurant_share": new_recs / total,
            "acceptance": s["accepted"] / max(1, s["recs"]),
            "repeat_rate": s["repeat"] / max(1, s["recs"]),
        }
        # Nightly retrain. With exploration on, the model learns only from the
        # randomized slice (unbiased by its own choices). With exploration off,
        # it can only learn from its own logs -- orders it caused. Feedback loop.
        for r in self.restaurants:
            if self.sw.surprise_exploration:
                signal = r.explore_accepted_today / EXPLORE_RATE
            else:
                signal = r.surprise_today
            r.popularity = 0.6 * r.popularity + 0.4 * signal
            r.explore_accepted_today = 0
            r.surprise_today = 0
            r.recommended_today = 0
        self.surprise_stats = {"recs": 0, "accepted": 0, "repeat": 0, "new": 0}

        # one or two new restaurants open every day in the core cities
        for _ in range(self.rng.choice([1, 2])):
            self._open_restaurant(self.rng.choice(CITIES_CORE), self.rng.choice(CUISINES_CORE), day + 1)

        # flywheel: most frequent judge-flagged failure mode gets fixed a bit
        if self.sw.flywheel:
            worst = max(self.failure_counts_today, key=self.failure_counts_today.get)
            self.failure_rates[worst] = max(0.004, self.failure_rates[worst] * 0.7)
        self.failure_counts_today = {m: 0 for m in FAILURE_MODES}

    def _advance_state(self, dt_days: float):
        sw = self.sw
        # menu index staleness: grows ~3%/day while sync paused, reset by sync
        if sw.menu_sync_paused:
            self.menu_stale_fraction = min(0.3, self.menu_stale_fraction + 0.03 * dt_days)
        else:
            self.menu_stale_fraction = max(0.0, self.menu_stale_fraction - 1.0 * dt_days)
        # new city traffic share ramps to 30% over ~3 days
        if sw.new_city_launched:
            if not self.new_city_opened:
                for _ in range(15):
                    self._open_restaurant(NEW_CITY, self.rng.choice(CUISINES_NEW_CITY), self.sim_day)
                self.new_city_opened = True
            self.new_city_share = min(0.30, self.new_city_share + 0.10 * dt_days)
        else:
            self.new_city_share = max(0.0, self.new_city_share - 0.3 * dt_days)
        # injection campaign ramps up; attackers adapt to guardrail over time
        if sw.injection_campaign:
            self.injection_intensity = min(0.06, self.injection_intensity + 0.03 * dt_days)
            self.campaign_age_days += dt_days
        else:
            self.injection_intensity = max(0.0, self.injection_intensity - 0.06 * dt_days)
            self.campaign_age_days = 0.0
        self.guardrail_age_days = self.guardrail_age_days + dt_days if sw.injection_guardrail else 0.0

    # --------------------------------------------------------------- one step
    def step(self, hours: float) -> tuple[list[dict], list[dict]]:
        """Advance simulated time by `hours`. Returns (conversations, refunds)."""
        start_day = int(self.sim_day)
        self._advance_state(hours / 24.0)
        hour_of_day = self.sim_time_h % 24
        expected = BASE_CONV_PER_HOUR * load_curve(hour_of_day) * hours
        n = int(expected) + (1 if self.rng.random() < expected - int(expected) else 0)
        convs = [self._conversation() for _ in range(n)]
        self.sim_time_h += hours
        end_day = int(self.sim_day)
        for d in range(start_day, end_day):
            self._end_of_day(d)
        due = [r for r in self.pending_refunds if r["due_h"] <= self.sim_time_h]
        self.pending_refunds = [r for r in self.pending_refunds if r["due_h"] > self.sim_time_h]
        refunds = []
        for r in due:
            r = dict(r)
            r.pop("due_h")
            r["sim_day"] = round(self.sim_day, 3)
            refunds.append(r)
        return convs, refunds

    def _pick_user(self) -> User:
        if self.new_city_share > 0 and self.rng.random() < self.new_city_share:
            return self.rng.choice(self.new_city_users)
        return self.rng.choice(self.users)

    def _surprise_me(self, user: User) -> tuple[Restaurant, bool, bool, bool]:
        rng = self.rng
        cands = [r for r in self.restaurants if r.city == user.city and r.opened_day <= self.sim_day]
        explore = self.sw.surprise_exploration and rng.random() < EXPLORE_RATE
        if explore:
            rest = rng.choice(cands)
        else:
            # exploit: recommend by learned popularity (rich get richer)
            weights = [(r.popularity + 0.2) ** EXPLOIT_POWER for r in cands]
            rest = rng.choices(cands, weights=weights, k=1)[0]
        rest.recommended_today += 1
        self._last_explore = explore
        repeat = rest.rid in user.seen
        user.seen.add(rest.rid)
        is_new = self.sim_day - rest.opened_day <= 7
        # users like good restaurants and novelty; they get bored of repeats
        logit = 0.4 + 0.8 * rest.quality + (0.3 if not repeat else -1.6)
        accepted = rng.random() < 1 / (1 + math.exp(-logit))
        if accepted:
            rest.surprise_today += 1
            if explore:
                rest.explore_accepted_today += 1
        s = self.surprise_stats
        s["recs"] += 1
        s["accepted"] += accepted
        s["repeat"] += repeat
        s["new"] += is_new
        return rest, accepted, repeat, is_new

    def _outcome_for(self, sw, llm, prompt, user, intent, city_new, outage, stale, u=None):
        """Compute one agent run. Called twice when shadowing: passing the same
        random draw `u` makes both runs face the same (simulated) user."""
        rng = self.rng
        turns = max(2, int(rng.gauss(4.5, 1.5)))
        if llm == LLM_NEW:
            turns += 1 if rng.random() < 0.5 else 0
        if prompt == PROMPT_UPSELL:
            turns += 1 if rng.random() < 0.6 else 0
        if city_new:
            turns += 1 if rng.random() < 0.7 else 0

        base_complete = {"order_specific": 0.88, "browse": 0.70, "surprise_me": 0.80,
                         "modify_order": 0.85, "complaint": 0.72}[intent]
        p_handoff = 0.04 + (0.10 if intent == "complaint" else 0)
        p_complete = base_complete
        if llm == LLM_NEW:
            p_complete -= 0.03
        if prompt == PROMPT_UPSELL:
            p_complete -= 0.015
            p_handoff += 0.01
        if prompt == PROMPT_CANARY:
            p_complete -= 0.30  # bug: v3 often forgets to call place_order
        if city_new:
            p_complete -= 0.08
            p_handoff += 0.03
        p_complete -= 0.35 * stale
        tool_calls = turns + rng.randint(0, 2)
        tool_errors = sum(rng.random() < 0.01 for _ in range(tool_calls))
        hallucinated_item = False
        if outage:
            menu_calls = max(1, tool_calls // 2)
            errs = sum(rng.random() < 0.6 for _ in range(menu_calls))
            tool_errors += errs
            if errs:
                if rng.random() < 0.3:
                    hallucinated_item = True  # agent invents an item instead of saying "unavailable"
                else:
                    p_complete -= 0.45
                    p_handoff += 0.15
        p_complete = max(0.02, min(0.98, p_complete))
        u = rng.random() if u is None else u
        outcome = "completed" if u < p_complete else ("handoff" if u < p_complete + p_handoff else "abandoned")
        return {"turns": turns, "tool_calls": tool_calls, "tool_errors": tool_errors,
                "outcome": outcome, "hallucinated_item": hallucinated_item}

    def _conversation(self) -> dict:
        rng, sw = self.rng, self.sw
        self.conv_counter += 1
        user = self._pick_user()
        city_new = user.city == NEW_CITY
        intent = rng.choices(INTENTS, INTENT_WEIGHTS)[0]
        cuisine = user.fav_cuisine if rng.random() < 0.6 else rng.choice(
            CUISINES_NEW_CITY if city_new else CUISINES_CORE)
        prompt, upsell_arm, canary_arm = self.prompt_for(user)
        llm = self.llm_for(user)
        outage = sw.menu_api_outage
        stale = self.menu_stale_fraction

        # ---- adversary
        injection_attempt = self.injection_intensity > 0 and rng.random() < self.injection_intensity
        injection_success = False
        if injection_attempt:
            p = 0.6 if llm == LLM_NEW else 0.35
            if sw.injection_guardrail:
                # guardrail works at first, attackers adapt over ~5 days
                p *= 0.1 + 0.9 * (1 - math.exp(-self.guardrail_age_days / 5.0))
            injection_success = rng.random() < p
            intent = "order_specific"

        u_user = rng.random()
        run = self._outcome_for(sw, llm, prompt, user, intent, city_new, outage, stale, u=u_user)
        outcome = run["outcome"]

        # ---- surprise me
        surprise_rid, surprise_accepted, surprise_repeat, surprise_new = "", None, None, None
        restaurant = None
        if intent == "surprise_me":
            restaurant, surprise_accepted, surprise_repeat, surprise_new = self._surprise_me(user)
            surprise_rid = restaurant.rid
            if not surprise_accepted and outcome == "completed":
                outcome = "abandoned" if rng.random() < 0.7 else "completed"
        if restaurant is None:
            cands = [r for r in self.restaurants if r.city == user.city and r.opened_day <= self.sim_day
                     and r.cuisine == cuisine] or [r for r in self.restaurants if r.city == user.city
                                                   and r.opened_day <= self.sim_day]
            w = [math.exp(r.quality) for r in cands]
            restaurant = rng.choices(cands, weights=w, k=1)[0]

        # ---- order contents and invariants
        n_items = 0
        order_value = 0.0
        discount = 0.0
        v_not_on_menu = v_price = v_discount = v_allergen = 0
        corrections = 0
        truth_failure = ""
        completed = outcome == "completed" and intent != "complaint"
        if completed:
            n_items = max(1, int(rng.gauss(2.3, 1.0)))
            if prompt == PROMPT_UPSELL:
                n_items += 1 if rng.random() < 0.4 else 0
            order_value = sum(rng.uniform(7, 19) for _ in range(n_items))
            if city_new:
                order_value *= 1.15
            order_value = round(order_value, 2)
            for _ in range(n_items):
                if rng.random() < 0.7 * stale or run["hallucinated_item"]:
                    v_not_on_menu = 1
                if rng.random() < 0.5 * stale:
                    v_price = 1
            if rng.random() < 0.004 * (4 if llm == LLM_NEW else 1):
                v_discount = 1
                discount = round(order_value * rng.uniform(0.2, 0.5), 2)
            if injection_success:
                v_discount = 1
                discount = round(order_value * rng.uniform(0.6, 1.0), 2)
        if user.has_allergy and completed and rng.random() < self.failure_rates["ignored_allergy"] * 2:
            v_allergen = 1
            truth_failure = "ignored_allergy"

        # ---- conversation-level failure modes (what a judge would look for)
        if not truth_failure:
            for mode in ("give_me_more_loop", "wrong_item", "unhelpful_reply"):
                rate = self.failure_rates[mode]
                if city_new:
                    rate *= 2.5
                if llm == LLM_NEW and mode == "give_me_more_loop":
                    rate *= 1.8
                if rng.random() < rate:
                    truth_failure = mode
                    break
        if prompt == PROMPT_UPSELL and not truth_failure and rng.random() < 0.05:
            truth_failure = "pushy_upsell"
        if prompt == PROMPT_CANARY and outcome != "completed" and not truth_failure:
            truth_failure = "order_not_placed"
        if (v_not_on_menu or v_price) and not truth_failure:
            truth_failure = "wrong_item"
        if injection_success:
            truth_failure = "followed_injection"
        if truth_failure == "wrong_item" or v_not_on_menu or v_price:
            corrections += 1 + (rng.random() < 0.5)
        corrections += rng.random() < (0.08 + (0.10 if city_new else 0))
        turns = run["turns"] + corrections
        if truth_failure == "give_me_more_loop":
            turns += 4

        # ---- ops: latency, tokens, cost
        med = 1.35 if llm == LLM_NEW else 1.8
        latency = rng.lognormvariate(math.log(med), 0.35) + (2.0 if outage else 0.0)
        in_tok = int(sum(1400 + 250 * t for t in range(turns)) * rng.uniform(0.9, 1.1))
        out_tok = int(turns * 110 * (1.4 if llm == LLM_NEW else 1.0) * rng.uniform(0.8, 1.2))
        cost = in_tok / 1e6 * PRICE_IN + out_tok / 1e6 * PRICE_OUT

        # ---- telemetry that IS observable about injections: heuristic detector
        det_recall = 0.7 * math.exp(-self.campaign_age_days / 6.0)  # attackers rephrase
        injection_flagged = (injection_attempt and rng.random() < det_recall) or rng.random() < 0.002

        # ---- LLM-as-judge on a 10% sample (imperfect: TPR .85, TNR .95)
        judge_sampled = rng.random() < 0.10
        judge_verdict, judge_mode = "", ""
        if judge_sampled:
            if truth_failure:
                fail = rng.random() < 0.85
            else:
                fail = rng.random() < 0.05
            judge_verdict = "fail" if fail else "pass"
            if fail:
                judge_mode = truth_failure if truth_failure and rng.random() < 0.8 else rng.choice(FAILURE_MODES)
        if truth_failure in self.failure_counts_today:
            self.failure_counts_today[truth_failure] += 1

        # ---- delayed label: refunds arrive 1-3 simulated days later
        if completed:
            p_refund = 0.02
            if v_not_on_menu or v_price:
                p_refund += 0.4
            if v_allergen:
                p_refund += 0.7
            if prompt == PROMPT_UPSELL:
                p_refund += 0.03
            if rng.random() < min(0.95, p_refund):
                self.pending_refunds.append({
                    "conv_id": f"c{self.conv_counter:08d}",
                    "prompt_version": prompt, "llm_version": llm,
                    "refund_amount": round(order_value * rng.uniform(0.3, 1.0), 2),
                    "due_h": self.sim_time_h + rng.uniform(24, 72),
                })

        # ---- shadow release: same request, new LLM, prediction not shown to user
        shadow = None
        if sw.shadow_new_llm and llm != LLM_NEW:
            s_run = self._outcome_for(sw, LLM_NEW, prompt, user, intent, city_new, outage, stale, u=u_user)
            # agree = same outcome and (for orders) the same items in the cart
            agree = (s_run["outcome"] == run["outcome"]) and rng.random() < 0.93
            s_disc = int(completed and rng.random() < 0.016 + (0.6 if injection_attempt else 0))
            shadow = {"agree": agree, "discount_violation": s_disc}

        hour = self.sim_time_h % 24
        rec = {
            "conv_id": f"c{self.conv_counter:08d}",
            "sim_day": round(self.sim_day, 4),
            "hour": round(hour, 2),
            "user_id": user.uid,
            "city": user.city,
            "cuisine": cuisine,
            "intent": intent,
            "request_chars": int(rng.lognormvariate(math.log(95 if not city_new else 140), 0.5))
                             + (400 if injection_attempt else 0),
            "has_allergy_mention": int(user.has_allergy),
            "prompt_version": prompt,
            "llm_version": llm,
            "exp_upsell_arm": upsell_arm,
            "canary_v3_arm": canary_arm,
            "turns": turns,
            "latency_s": round(latency, 3),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": round(cost, 5),
            "tool_calls": run["tool_calls"],
            "tool_errors": run["tool_errors"],
            "outcome": outcome,
            "restaurant_id": restaurant.rid,
            "n_items": n_items,
            "order_value": order_value,
            "discount_value": discount,
            "corrections": int(corrections),
            "viol_item_not_on_menu": v_not_on_menu,
            "viol_price_mismatch": v_price,
            "viol_discount_policy": v_discount,
            "viol_allergen": v_allergen,
            "injection_flagged": int(injection_flagged),
            "judge_sampled": int(judge_sampled),
            "judge_verdict": judge_verdict,
            "judge_failure_mode": judge_mode,
            "surprise_restaurant": surprise_rid,
            "surprise_accepted": "" if surprise_accepted is None else int(surprise_accepted),
            "surprise_repeat": "" if surprise_repeat is None else int(surprise_repeat),
            "surprise_new_restaurant": "" if surprise_new is None else int(surprise_new),
            "shadow_agree": "" if shadow is None else int(shadow["agree"]),
            "shadow_viol_discount_policy": "" if shadow is None else shadow["discount_violation"],
            # hidden ground truth -- NOT available to a real team
            "truth_failure_mode": truth_failure,
            "truth_injection_attempt": int(injection_attempt),
            "truth_injection_success": int(injection_success),
            "truth_menu_stale_fraction": round(stale, 4),
        }
        return rec

    def truth_snapshot(self) -> dict:
        return {
            "sim_day": self.sim_day,
            "menu_stale_fraction": self.menu_stale_fraction,
            "new_city_share": self.new_city_share,
            "injection_intensity": self.injection_intensity,
            "failure_rates": dict(self.failure_rates),
            "surprise": dict(self.last_day_summary),
            "open_restaurants": sum(1 for r in self.restaurants if r.opened_day <= self.sim_day),
        }

    def switches_dict(self) -> dict:
        return asdict(self.sw)

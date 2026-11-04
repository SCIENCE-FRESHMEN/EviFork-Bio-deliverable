"""Proper scores and budgeted retrospective query replay with isolated label access."""
import math
import random
from .inference import entropy, information_gain, mixture, posterior_update, temperature_scale


def score_predictions(rows):
    if not rows:
        return {"n": 0, "accuracy": None, "nll": None, "brier": None, "ece": None}
    hits, nll, brier = 0, 0., 0.
    bins = [[] for _ in range(10)]
    confusion = [[0] * 3 for _ in range(3)]
    for row in rows:
        p, truth = row["probabilities"], row["outcome"] + 1
        tied = [i for i in range(3) if math.isclose(p[i], max(p), rel_tol=0., abs_tol=1e-12)]
        predicted = min(tied, key=lambda i: (abs(i - 1), i))
        correct = int(predicted == truth)
        hits += correct
        confusion[truth][predicted] += 1
        nll -= math.log(max(p[truth], 1e-12))
        brier += sum((value - int(i == truth)) ** 2 for i, value in enumerate(p))
        bins[min(9, int(max(p) * 10))].append((max(p), correct))
    n = len(rows)
    reliability = [{"lower": i / 10, "upper": (i + 1) / 10, "n": len(bucket),
                    "mean_confidence": sum(x[0] for x in bucket) / len(bucket),
                    "accuracy": sum(x[1] for x in bucket) / len(bucket)}
                   for i, bucket in enumerate(bins) if bucket]
    return {"n": n, "accuracy": hits / n, "nll": nll / n, "brier": brier / n,
            "ece": sum(b["n"] / n * abs(b["mean_confidence"] - b["accuracy"]) for b in reliability),
            "confusion_matrix_order": [-1, 0, 1], "confusion_matrix": confusion,
            "argmax_tie_rule": "Within absolute 1e-12 prefer unchanged, then decreased; independent of truth labels.",
            "reliability_bins": reliability,
            "mean_model_coverage": sum(r["model_coverage"] for r in rows) / n,
            "coverage_note": "Unmapped/nonconverged models contribute uniform probabilities, not confident unchanged calls."}


def prediction_rows(weights, cases, table, temperature=1.):
    return [{"id": c.id, "outcome": c.outcome,
             "probabilities": temperature_scale(mixture(weights, table.probabilities(c)), temperature),
             "model_coverage": table.coverage(weights, c)} for c in cases]


def rank_candidates(weights, candidates, table):
    # Access only features/cost/id. Never read outcome or source DOIs here.
    rows = [{"id": c.id, "cost": c.cost, "features": c.features(),
             "expected_information_gain_nats": information_gain(weights, table.probabilities(c)),
             "predictive_probabilities": mixture(weights, table.probabilities(c)),
             "model_coverage": table.coverage(weights, c)} for c in candidates]
    for row in rows:
        row["information_gain_per_cost"] = row["expected_information_gain_nats"] / row["cost"]
    return sorted(rows, key=lambda r: (-r["information_gain_per_cost"], r["id"]))


class Oracle:
    def __init__(self, cases, group_ids, budget):
        self._cases = {c.id: c for c in cases}
        self.groups, self.budget, self.spent, self.used = group_ids, budget, 0., set()

    def feasible(self, cases):
        return [c for c in cases if self.groups[c.id] not in self.used and self.spent + c.cost <= self.budget + 1e-10]

    def reveal(self, case_id):
        c = self._cases[case_id]
        if c not in self.feasible([c]):
            raise ValueError("Query repeats a paper/intervention component or exceeds budget")
        self.spent += c.cost
        self.used.add(self.groups[c.id])
        return c.outcome


def replay(weights, pool, test, table, group_ids, budget, policy, seed, temperature=1., truth_id=None):
    if policy not in {"information_gain", "random"} or not math.isfinite(budget) or budget < 0:
        raise ValueError("Invalid replay policy or budget")
    weights = list(weights)
    oracle, rng = Oracle(pool, group_ids, budget), random.Random(seed)
    trace = []
    def checkpoint():
        return {"spent": oracle.spent, "posterior_entropy_nats": entropy(weights),
                "test_metrics": score_predictions(prediction_rows(weights, test, table, temperature)),
                "true_mechanism_probability": sum(w for w, h in zip(weights, table.hypotheses) if h.id == truth_id) if truth_id else None}
    trace.append(checkpoint())
    while oracle.feasible(pool):
        feasible = oracle.feasible(pool)
        ranked = rank_candidates(weights, feasible, table)
        if policy == "information_gain":
            # No claimed experiment value if every candidate is observationally equivalent.
            if ranked[0]["expected_information_gain_nats"] < 1e-12:
                break
            selected = next(c for c in feasible if c.id == ranked[0]["id"])
        else:
            selected = rng.choice(sorted(feasible, key=lambda c: c.id))
        outcome = oracle.reveal(selected.id)
        weights = posterior_update(weights, table.probabilities(selected), outcome)
        row = checkpoint()
        row.update({"queried_id": selected.id, "observed_outcome": outcome,
                    "selection_eig_nats": next(r["expected_information_gain_nats"] for r in ranked if r["id"] == selected.id)})
        trace.append(row)
    return {"policy": policy, "seed": seed, "budget_ceiling": budget, "spent": oracle.spent,
            "trace": trace, "final_weights": weights,
            "identification_cost_at_p95": next((r["spent"] for r in trace if r["true_mechanism_probability"] is not None and r["true_mechanism_probability"] >= .95), None),
            "mechanism_metric_note": "True-mechanism probability is available only for synthetic known-topology controls; real replay entropy is a proxy, not proof of mechanism identification."}

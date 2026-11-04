"""Finite competing graphs, source-calibration records and Bayesian model averaging."""
from collections import Counter, defaultdict
from dataclasses import dataclass
import math

from .data import digest, normalize_doi


def normalize_logs(values):
    maximum = max(values)
    weights = [max(math.exp(v - maximum), 1e-300) for v in values]
    total = math.fsum(weights)
    return [w / total for w in weights]


def entropy(probabilities):
    return -sum(p * math.log(p) for p in probabilities if p > 0)


@dataclass
class Hypothesis:
    id: str
    edges: tuple
    log_prior: float


class Reliability:
    """Beta-binomial calibration by extraction-quality bucket, one audit per paper.

    The unfitted Beta(3,1) is a modeling prior, NOT a measured reliability.
    Audit labels must be independent human adjudications of the biological claim.
    """
    def __init__(self, audits=(), forbidden=()):
        self.counts = defaultdict(lambda: [3., 1.])
        self.records = []
        seen = {}
        forbidden = set(forbidden)
        for row in audits:
            doi = normalize_doi(row["doi"])
            if doi in forbidden:
                raise ValueError("Evidence calibration audit includes held-out paper")
            if row.get("adjudication") != "independent_human":
                raise ValueError("Evidence calibration requires independent_human adjudication")
            label = row["correct"]
            if type(label) is not bool:
                raise ValueError("Audit correct must be boolean")
            quality = row.get("quality", "unknown")
            key = (doi, quality)
            if key in seen:
                if seen[key] != label:
                    raise ValueError("Conflicting audit labels in same paper/bucket; adjudicate first")
                continue
            seen[key] = label
            self.counts[quality][0 if label else 1] += 1
            self.records.append({"doi": doi, "quality": quality, "correct": label})

    def probability(self, quality):
        a, b = self.counts[quality]
        return a / (a + b)

    def report(self):
        return {"status": "fitted_on_independent_training_audits" if self.records else "unfitted_prior_only",
                "prior": {"alpha": 3, "beta": 1}, "audited_paper_bucket_count": len(self.records),
                "buckets": {k: {"alpha": a, "beta": b, "mean": a / (a + b)} for k, (a, b) in sorted(self.counts.items())},
                "assumption": "Paper likelihood factors independent across papers; repeated same-paper claims count once per pair."}


def build_hypotheses(claims, reliability, max_hypotheses=32, omission_prior=0.):
    if max_hypotheses < 1 or not 0 <= omission_prior < 1:
        raise ValueError("Invalid beam size or omission prior")
    pairs = defaultdict(list)
    for claim in claims:
        pairs[claim.source, claim.target].append(claim)
    beam = [(0., ())]
    conflicts, vote_edges, combination_count = [], [], 1
    distributions = []
    for (source, target), rows in sorted(pairs.items()):
        observed = sorted({row.sign for row in rows})
        options = sorted(set(observed) | ({0} if omission_prior > 0 else set()))
        by_paper = defaultdict(list)
        for row in rows:
            by_paper[row.doi].append(row)
        scores = []
        for option in options:
            nonzero = [s for s in options if s]
            if 0 in observed or 0 not in options:
                prior = 1 / len(options)
            else:
                prior = omission_prior if option == 0 else (1 - omission_prior) / len(nonzero)
            factors = [math.log(prior)]
            for records in by_paper.values():
                # Opposite signs within one paper are a mixture, not independent votes.
                reports = sorted({(r.sign, r.quality) for r in records})
                probabilities = []
                for sign, quality in reports:
                    r = reliability.probability(quality)
                    probabilities.append(1. if len(options) == 1 else
                                         r if sign == option else (1 - r) / (len(options) - 1))
                factors.append(math.log(math.fsum(probabilities) / len(probabilities)))
            scores.append(math.fsum(factors))
        probabilities = normalize_logs(scores)
        distributions.append((source, target, observed, dict(zip(options, probabilities))))
        votes = {s: sum(s in {r.sign for r in rs} for rs in by_paper.values()) for s in observed}
        maximum = max(votes.values())
        winners = [s for s in observed if votes[s] == maximum]
        vote = winners[0] if len(winners) == 1 else 0
        if vote:
            vote_edges.append((source, target, vote))
        conflicts.append({"source": source, "target": target, "observed_signs": observed,
                          "is_conflict": len(observed) > 1,
                          "alternatives": [{"sign": s, "probability": p,
                                            "support_dois": sorted({r.doi for r in rows if r.sign == s}),
                                            "omission_is_model_assumption": s == 0 and s not in observed}
                                           for s, p in zip(options, probabilities)]})
        beam = sorted(((score + math.log(p), edges + ((source, target, s),))
                       for score, edges in beam for s, p in zip(options, probabilities)),
                      key=lambda item: (-item[0], item[1]))[:max_hypotheses]
        combination_count *= len(options)
    # Preserve each observed conflict state even when an asymmetric prior would prune it.
    # This covers marginal alternatives, not all joint combinations of several conflicts.
    base = tuple((s, t, max(ps, key=lambda x: (ps[x], -x))) for s, t, _, ps in distributions)
    protected = {base}
    for index, (_, _, observed, _) in enumerate(distributions):
        if len(observed) > 1:
            for sign in observed:
                alternative = list(base)
                source, target, _ = alternative[index]
                alternative[index] = (source, target, sign)
                protected.add(tuple(alternative))
    if len(protected) > max_hypotheses:
        raise ValueError(f"Need at least {len(protected)} hypotheses to preserve observed conflict alternatives")
    candidates = {edges: score for score, edges in beam}
    for edges in protected:
        candidates[edges] = sum(math.log(ps[edge[2]]) for edge, (_, _, _, ps) in zip(edges, distributions))
    selected = set(protected)
    for edges in sorted(candidates, key=lambda e: (-candidates[e], e)):
        if len(selected) >= max_hypotheses:
            break
        selected.add(edges)
    beam = sorted(((candidates[e], e) for e in selected), key=lambda item: (-item[0], item[1]))
    hypotheses = [Hypothesis("H_" + digest(edges)[:16], tuple(e for e in edges if e[2]), score)
                  for score, edges in beam]
    retained_log_mass = max(x[0] for x in beam) + math.log(sum(math.exp(x[0] - beam[0][0]) for x in beam))
    return hypotheses, tuple(vote_edges), {"pairs": conflicts, "total_combinations": combination_count,
        "retained_hypotheses": len(beam), "retained_prior_mass": math.exp(retained_log_mass),
        "observed_conflict_states_protected": True,
        "approximation": "exact" if combination_count <= max_hypotheses else "top-k beam; discarded graphs cannot recover",
        "omission_prior": omission_prior}


def posterior_update(weights, predictions, outcome, power=1.):
    return normalize_logs([math.log(max(w, 1e-300)) + power * math.log(max(p[outcome + 1], 1e-12))
                           for w, p in zip(weights, predictions)])


def fit_posterior(hypotheses, train_cases, table, group_ids):
    weights = normalize_logs([h.log_prior for h in hypotheses])
    counts = Counter(group_ids[c.id] for c in train_cases)
    for case in train_cases:
        weights = posterior_update(weights, table.probabilities(case), case.outcome,
                                   power=1 / counts[group_ids[case.id]])
    return weights


def mixture(weights, probabilities):
    return [math.fsum(w * row[k] for w, row in zip(weights, probabilities)) for k in range(3)]


def information_gain(weights, probabilities):
    return max(0., entropy(mixture(weights, probabilities)) -
               sum(w * entropy(p) for w, p in zip(weights, probabilities)))


def temperature_scale(probabilities, temperature):
    return normalize_logs([math.log(max(p, 1e-12)) / temperature for p in probabilities])


def calibrate_temperature(weights, cases, table):
    if len(cases) < 4 or len({c.outcome for c in cases}) < 2:
        return 1., "insufficient_calibration_data"
    grid = (.5, .75, 1., 1.5, 2., 3., 5., 10.)
    def loss(t):
        return sum(-math.log(max(temperature_scale(mixture(weights, table.probabilities(c)), t)[c.outcome + 1], 1e-12)) for c in cases)
    return min(grid, key=lambda t: (loss(t), abs(t - 1))), "fitted_on_calibration_only"

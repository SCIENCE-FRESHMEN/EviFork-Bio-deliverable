"""Adapter to the actual upstream algebraic simulator; no reimplemented biology."""
import importlib
import math
from pathlib import Path
import sys

from .data import DIRECTIONS

SHARED = Path(__file__).resolve().parents[1] / "EviFork_Bio_Plant/Claude/Agent/shared"


class Simulator:
    def __init__(self, nodes, phenotype, noise=.1):
        if not 0 < noise < 2/3:
            raise ValueError("Noise must lie strictly between zero and 2/3")
        sys.path.insert(0, str(SHARED))
        try:
            upstream = importlib.import_module("evifork_bio_validator")
            if Path(upstream.__file__).resolve().parent != SHARED.resolve():
                raise RuntimeError("A different FLASH-P validator is already imported")
            self.upstream = upstream
        finally:
            sys.path.pop(0)
        self.nodes, self.phenotype, self.noise = tuple(sorted(set(nodes) | {phenotype})), phenotype, noise
        self.models = {}
        self.cache = {}

    def model(self, hypothesis):
        if hypothesis.id not in self.models:
            u = self.upstream
            equations = {n: u.Equation(n, "PHENOTYPE" if n == self.phenotype else "GENE") for n in self.nodes}
            for source, target, sign in hypothesis.edges:
                if source not in equations or target not in equations:
                    raise ValueError("Topology endpoint outside node universe")
                (equations[target].activators if sign == 1 else equations[target].inhibitors).append(source)
            network = u.AlgebraicNetwork({}, equations, self.phenotype)
            self.models[hypothesis.id] = u.FlashPSimulator(network, u.SimulationConfig())
        return self.models[hypothesis.id]

    def predict(self, hypothesis, case):
        key = (hypothesis.id, case.signature())
        if key in self.cache:
            return self.cache[key]
        referenced = set(case.genes) | set(case.supply) | set(case.baseline_genes) | set(case.baseline_supply)
        if case.phenotype != self.phenotype or not referenced <= set(self.nodes):
            result = ([1/3] * 3, False, "unmapped_node_or_endpoint")
        else:
            try:
                model = self.model(hypothesis)
                base, b_ok, _ = model.simulate(case.baseline_genes, case.baseline_supply)
                changed, p_ok, _ = model.simulate(case.genes, case.supply)
                a, b = changed[self.phenotype], base[self.phenotype]
                if not b_ok or not p_ok or not all(math.isfinite(x) for x in (a, b)):
                    result = ([1/3] * 3, False, "nonconverged_or_nonfinite")
                else:
                    ratio = a / b if b > 0 else (math.inf if a > 0 else 1.)
                    sign = 1 if ratio > 1.05 else -1 if ratio < .95 else 0
                    result = ([1 - self.noise if k == sign else self.noise / 2 for k in DIRECTIONS], True, "converged")
            except (OverflowError, ZeroDivisionError, FloatingPointError):
                result = ([1/3] * 3, False, "numerical_failure")
        self.cache[key] = result
        return result


class PredictionTable:
    def __init__(self, hypotheses, simulator):
        self.hypotheses, self.simulator = hypotheses, simulator

    def probabilities(self, case):
        return [self.simulator.predict(h, case)[0] for h in self.hypotheses]

    def coverage(self, weights, case):
        return sum(w for w, h in zip(weights, self.hypotheses) if self.simulator.predict(h, case)[1])

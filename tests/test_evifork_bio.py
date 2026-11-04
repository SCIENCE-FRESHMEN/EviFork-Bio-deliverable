import copy
from dataclasses import asdict
import math
from pathlib import Path
import tempfile
import unittest

from evifork_bio.data import Case, Claim, load_dataset, normalize_doi, prepare_upstream, read_json, write_json
from evifork_bio.demo import make_demo
from evifork_bio.evaluate import Oracle, information_gain, rank_candidates, score_predictions
from evifork_bio.experiment import original_baseline, run_experiment
from evifork_bio.inference import Reliability, build_hypotheses, mixture, normalize_logs, posterior_update
from evifork_bio.simulator import PredictionTable, Simulator
from evifork_bio.split import split_dataset
from evifork_bio.__main__ import main


class HypothesisTests(unittest.TestCase):
    def fixture(self, root):
        p = Path(root) / "data.json"
        make_demo(p)
        return p, load_dataset(p)

    def test_synthetic_sources_are_not_fabricated_dois(self):
        with self.assertRaises(ValueError):
            normalize_doi("synthetic:positive")
        self.assertEqual(normalize_doi("https://doi.org/10.1105/TPC.106.048934"), "10.1105/tpc.106.048934")

    def test_contexts_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            p, (data, _, _) = self.fixture(root)
            data["claims"][0]["context"] = "other species"
            write_json(p, data)
            with self.assertRaisesRegex(ValueError, "Mixed contexts"):
                load_dataset(p)

    def test_joint_groups_prevent_paper_and_intervention_leakage(self):
        with tempfile.TemporaryDirectory() as root:
            _, (data, claims, cases) = self.fixture(root)
            # A transitive paper link and an identical intervention must stay together.
            cases[1].dois = cases[0].dois + cases[1].dois
            cases[2].genes = dict(cases[1].genes)
            training, split, groups, manifest = split_dataset(claims, cases, 12)
            self.assertEqual(groups[cases[0].id], groups[cases[2].id])
            role = {c.id: r for r, cs in split.items() for c in cs}
            self.assertEqual(role[cases[0].id], role[cases[2].id])
            forbidden = {d for r in ("test", "query", "calibration") for d in manifest["roles"][r]["dois"]}
            self.assertTrue(all(c.doi not in forbidden for c in training))
            # Assignments cannot depend on outcome values.
            for c in cases:
                c.outcome = -c.outcome
            self.assertEqual(manifest, split_dataset(claims, cases, 12)[3])

    def test_forbidden_edge_papers_removed_before_build(self):
        with tempfile.TemporaryDirectory() as root:
            _, (_, claims, cases) = self.fixture(root)
            held_doi = cases[-1].dois[0]
            claims.append(Claim("held", "Z", "Trait", 1, held_doi, "synthetic_control"))
            # Put the last case in test using the demo's precommitted roles.
            data = make_demo(Path(root) / "again.json")
            training, _, _, manifest = split_dataset(claims, cases, assignments=data["split_roles"])
            self.assertNotIn("held", [c.id for c in training])
            self.assertIn("held", manifest["excluded_claim_ids"])

    def test_duplicate_paper_not_independent_votes(self):
        a = Claim("a", "A", "T", 1, "10.1234/a", "ctx")
        b = Claim("b", "A", "T", -1, "10.1234/b", "ctx")
        left = build_hypotheses([a, b], Reliability(), omission_prior=0)[2]
        right = build_hypotheses([a, a, a, a, b], Reliability(), omission_prior=0)[2]
        self.assertEqual(left, right)
        self.assertEqual(left["pairs"][0]["observed_signs"], [-1, 1])

    def test_evidence_calibration_rejects_leakage_and_fake_audits(self):
        audit = {"doi": "10.1234/a", "quality": "fulltext", "correct": True, "adjudication": "independent_human"}
        with self.assertRaisesRegex(ValueError, "held-out"):
            Reliability([audit], {"10.1234/a"})
        self.assertEqual(Reliability([audit]).probability("fulltext"), .8)
        self.assertEqual(Reliability().report()["status"], "unfitted_prior_only")
        with self.assertRaises(ValueError):
            Reliability([{**audit, "adjudication": "llm_self_rating"}])

    def test_low_prior_competitor_is_not_pruned(self):
        claims = [Claim(str(i), "A", "T", 1, f"10.1234/p{i}", "ctx") for i in range(25)]
        claims.append(Claim("minority", "A", "T", -1, "10.1234/opposite", "ctx"))
        models, _, _ = build_hypotheses(claims, Reliability(), max_hypotheses=2)
        self.assertEqual({h.edges[0][2] for h in models}, {-1, 1})

    def test_nonconvergence_is_not_scored_as_unchanged(self):
        from evifork_bio.inference import Hypothesis
        model = Hypothesis("bad", (("A", "Trait", 1),), 0.)
        simulator = Simulator(["A", "Trait"], "Trait")
        engine = simulator.model(model)
        engine.simulate = lambda genes, supply: ({"A": 1., "Trait": 1.}, False, 100)
        case = Case("x", {"A": 0.}, {}, {}, {}, "Trait", "ctx", 0)
        p, covered, reason = simulator.predict(model, case)
        self.assertFalse(covered)
        self.assertEqual(p, [1/3] * 3)

    def test_operational_recommend_and_observe(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            p, _ = self.fixture(root)
            run_experiment(p, root / "fit", omission_prior=0., noise=.05)
            state = root / "fit/hypotheses.json"
            before = state.read_bytes()
            examples = Path(__file__).resolve().parents[1] / "evifork_bio/examples"
            main(["recommend", "--state", str(state), "--candidates", str(examples / "candidates.json"), "--output", str(root / "rank.json")])
            self.assertEqual(read_json(root / "rank.json")["recommendations"][0]["id"], "A_KO")
            main(["observe", "--state", str(state), "--observation", str(examples / "synthetic_observation.json"), "--output", str(root / "updated.json")])
            self.assertEqual(state.read_bytes(), before)
            updated = read_json(root / "updated.json")
            self.assertEqual(updated["state_role"], "operational_update_not_an_untouched_holdout_evaluation")
            self.assertGreater(max(r["weight"] for r in updated["hypotheses"]), .95)

    def test_import_quarantines_invalid_sources_and_complex_encodings(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            write_json(root / "data/curated_edges.json", {"metadata": {"phenotype_node": "Trait", "species": "Species A"},
                "edges": [{"source": "A", "target": "Trait", "sign": 1, "evidence": [{"doi": "10.1105/tpc.106.048934"}]},
                          {"source": "B", "target": "Trait", "sign": -1, "evidence": [{"doi": "title"}]}]})
            rows = [{"test_id": "x", "gene": "A", "perturbation_type": "knockout", "expected_direction": "increased", "doi": "10.1105/tpc.106.048934"}]
            rows += [{**rows[0], "test_id": "complex", "perturbation_type": "rescue"},
                     {**rows[0], "test_id": "foreign", "species": "Species B"}]
            write_json(root / "data/perturbation_dataset.json", {"perturbations": rows})
            data = prepare_upstream(root, root / "import.json")
            self.assertEqual(len(data["claims"]), 1)
            self.assertEqual(len(data["perturbations"]), 1)
            self.assertEqual(len(data["import_audit"]["quarantine"]), 3)

    def test_original_declaration_checks_actual_equations(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            write_json(root / "network/network.json", {"edges": [{"source": "A", "target": "Trait", "sign": 1}]})
            write_json(root / "network/algebraic_equations.json", {"equations": [
                {"node": "A", "node_type": "GENE"}, {"node": "B", "node_type": "GENE"},
                {"node": "Trait", "node_type": "PHENOTYPE", "activators": ["B"]}]})
            write_json(root / "hypothesis_training_manifest.json", {"training_claims_sha256": "expected", "used_heldout_outcomes": False})
            case = Case("x", {"A": 0.}, {}, {}, {}, "Trait", "ctx", 1)
            claim = Claim("c", "A", "Trait", 1, "10.1234/source", "ctx")
            with self.assertRaisesRegex(ValueError, "training declaration"):
                original_baseline(root, [case], [], .1, {"training_claims_sha256": "expected"}, [claim])

    def test_information_gain_prefers_discriminating_experiment(self):
        useful = [[.95, .025, .025], [.025, .025, .95]]
        useless = [[.025, .95, .025]] * 2
        self.assertGreater(information_gain([.5, .5], useful), .5)
        self.assertAlmostEqual(information_gain([.5, .5], useless), 0.)
        weights = posterior_update([.5, .5], useful, -1)
        self.assertGreater(weights[0], .95)

    def test_candidate_ranking_does_not_read_labels(self):
        with tempfile.TemporaryDirectory() as root:
            _, (_, claims, cases) = self.fixture(root)
            models, _, _ = build_hypotheses(claims, Reliability(), omission_prior=0.)
            table = PredictionTable(models, Simulator(["A", "B", "C", "Trait"], "Trait", .05))
            one = rank_candidates([.5, .5], cases, table)
            for c in cases:
                c.outcome = 999  # Invalid labels must still be inaccessible to selection.
            self.assertEqual(one, rank_candidates([.5, .5], cases, table))

    def test_unmapped_intervention_is_uniform_and_uncovered(self):
        with tempfile.TemporaryDirectory() as root:
            _, (_, claims, cases) = self.fixture(root)
            models, _, _ = build_hypotheses(claims, Reliability(), omission_prior=0.)
            simulator = Simulator(["A", "B", "C", "Trait"], "Trait")
            c = copy.deepcopy(cases[0])
            c.genes = {"UNKNOWN": 0.}
            probabilities, covered, reason = simulator.predict(models[0], c)
            self.assertEqual(probabilities, [1/3] * 3)
            self.assertFalse(covered)

    def test_rescue_uses_explicit_mutant_baseline(self):
        from evifork_bio.inference import Hypothesis
        model = Hypothesis("rescue", (("A", "Trait", 1),), 0.)
        simulator = Simulator(["A", "Trait"], "Trait")
        c = Case("rescue", {"A": 0.}, {"A": 1.}, {"A": 0.}, {}, "Trait", "ctx", 1)
        self.assertGreater(simulator.predict(model, c)[0][2], .8)

    def test_oracle_enforces_budget_and_independent_components(self):
        with tempfile.TemporaryDirectory() as root:
            _, (_, _, cases) = self.fixture(root)
            groups = {c.id: "same" for c in cases}
            oracle = Oracle(cases, groups, 1.)
            oracle.reveal(cases[0].id)
            with self.assertRaises(ValueError):
                oracle.reveal(cases[1].id)

    def test_proper_scores(self):
        metrics = score_predictions([{"probabilities": [.1, .2, .7], "outcome": 1, "model_coverage": 1.}])
        self.assertAlmostEqual(metrics["nll"], -math.log(.7))
        self.assertAlmostEqual(metrics["brier"], .14)
        tied = score_predictions([{"probabilities": [.5 - 1e-16, 0., .5 + 1e-16], "outcome": -1, "model_coverage": 1.}])
        self.assertEqual(tied["accuracy"], 1.)

    def test_end_to_end_and_repeatability(self):
        with tempfile.TemporaryDirectory() as root:
            p, _ = self.fixture(root)
            a = run_experiment(p, Path(root) / "a", omission_prior=0., noise=.05, budget=3.)
            b = run_experiment(p, Path(root) / "b", omission_prior=0., noise=.05, budget=3.)
            self.assertEqual(a, b)
            self.assertFalse(a["prospective_discovery"])
            active = [r for r in a["query_replays"] if r["policy"] == "information_gain"]
            self.assertTrue(all(r["trace"][1]["queried_id"] == "informative_A" for r in active))
            self.assertTrue(all(r["identification_cost_at_p95"] == 1. for r in active))
            self.assertEqual(a["baselines"]["original_flashp"]["metrics"], None)

    def test_heldout_label_changes_cannot_change_fit(self):
        with tempfile.TemporaryDirectory() as root:
            p, (data, _, _) = self.fixture(root)
            run_experiment(p, Path(root) / "a", omission_prior=0.)
            for row in data["perturbations"]:
                if row["id"] in data["split_roles"]["test"]:
                    row["outcome"] = -row["outcome"]
            write_json(p, data)
            run_experiment(p, Path(root) / "b", omission_prior=0.)
            a = read_json(Path(root) / "a/hypotheses.json")
            b = read_json(Path(root) / "b/hypotheses.json")
            self.assertEqual(a["hypotheses"], b["hypotheses"])
            self.assertEqual(a["temperature"], b["temperature"])


if __name__ == "__main__":
    unittest.main()

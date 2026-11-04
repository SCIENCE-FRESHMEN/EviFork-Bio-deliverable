"""Reproducible evaluation orchestration and auditable external baseline handling."""
from dataclasses import asdict
import hashlib
import math
from pathlib import Path
import sys

from .data import digest, load_dataset, read_json, write_json
from .evaluate import prediction_rows, rank_candidates, replay, score_predictions
from .inference import Hypothesis, Reliability, build_hypotheses, calibrate_temperature, fit_posterior
from .simulator import PredictionTable, SHARED, Simulator
from .split import split_dataset


def original_baseline(directory, cases, calibration, noise, manifest, training_claims):
    """Replay real upstream equations; bundled refined artifacts are explicitly unfair references."""
    directory = Path(directory)
    network = read_json(directory / "network/network.json")
    sys.path.insert(0, str(SHARED))
    try:
        import evifork_bio_validator as u
        loaded = u.load_equations(str(directory / "network/algebraic_equations.json"))
        spec_path = directory / "network/equation_spec.json"
        spec = u.load_equation_spec(str(spec_path)) if spec_path.exists() and u.EQUATION_EXECUTOR_AVAILABLE else None
        spec_errors = u.validate_equation_spec(spec) if spec is not None else []
        if spec_errors:
            spec = None  # Same fallback as the original validator; retain the reason below.
        config = u.SimulationConfig()
        if spec:
            for key in ("damping", "max_iterations", "convergence_tolerance", "activator_floor"):
                if key in spec.get("propagation_params", {}):
                    setattr(config, key, spec["propagation_params"][key])
        model = u.FlashPSimulator(loaded, config, spec)
    finally:
        sys.path.pop(0)
    if loaded.phenotype_node != cases[0].phenotype:
        raise ValueError("Original baseline phenotype differs from benchmark")
    hypothesis = Hypothesis("original_flashp", (), 0.)
    simulator = Simulator(loaded.equations, loaded.phenotype_node, noise)
    simulator.models[hypothesis.id] = model
    table = PredictionTable([hypothesis], simulator)
    temperature, calibration_status = calibrate_temperature([1.], calibration, table)
    status = "reference_only_existing_artifact_possible_heldout_leakage"
    declaration_path = directory / "hypothesis_training_manifest.json"
    if declaration_path.exists():
        declaration = read_json(declaration_path)
        supported = {(c.source, c.target, c.sign) for c in training_claims}
        edges = {(r.get("source", r.get("s")), r.get("target", r.get("t")), r.get("sign", r.get("x"))) for r in network["edges"]}
        simulated_edges = {(source, target, sign) for target, eq in loaded.equations.items()
                           for sign, regulators in ((1, eq.activators), (-1, eq.inhibitors)) for source in regulators}
        if declaration.get("training_claims_sha256") != manifest["training_claims_sha256"] or declaration.get("used_heldout_outcomes") is not False or not edges <= supported or simulated_edges != edges:
            raise ValueError("Original FLASH-P training declaration does not match this split/evidence")
        status = "train_only_rebuild_declared_requires_independent_process_audit"
    rows = prediction_rows([1.], cases, table, temperature)
    return {"status": status, "metrics": score_predictions(rows), "predictions": rows,
            "temperature": temperature, "calibration_status": calibration_status,
            "equation_spec_applied": spec is not None, "equation_spec_errors": spec_errors,
            "simulation_config": asdict(config),
            "equations_sha256": digest(read_json(directory / "network/algebraic_equations.json")),
            "limitation": "A manifest checks declared training provenance, not unseen LLM knowledge or undocumented human decisions."}


def run_experiment(dataset_path, output, *, seed=17, max_hypotheses=32, omission_prior=0.,
                   budget=5., noise=.1, original=None, replay_seeds=(0, 1, 2, 3, 4)):
    if not replay_seeds or not math.isfinite(budget) or budget < 0:
        raise ValueError("Need replay seeds and a finite nonnegative budget")
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory is nonempty; choose a fresh run directory")
    data, claims, cases = load_dataset(dataset_path)
    training, split, groups, manifest = split_dataset(claims, cases, seed, data.get("split_roles"))
    forbidden = {d for role in ("calibration", "query", "test") for d in manifest["roles"][role]["dois"]}
    reliability = Reliability(data.get("audits", []), forbidden)
    hypotheses, vote_edges, topology = build_hypotheses(training, reliability, max_hypotheses, omission_prior)
    nodes = sorted({n for c in training for n in (c.source, c.target)})
    simulator = Simulator(nodes, data["metadata"]["phenotype_node"], noise)
    table = PredictionTable(hypotheses, simulator)
    weights = fit_posterior(hypotheses, split["train"], table, groups)
    temperature, calibration_status = calibrate_temperature(weights, split["calibration"], table)
    models = {"competing_hypotheses": (table, weights)}
    # Ablation: identical training fit, collapsed to its MAP graph instead of model averaging.
    best = max(range(len(weights)), key=lambda i: (weights[i], hypotheses[i].id))
    models["single_network"] = (PredictionTable([hypotheses[best]], simulator), [1.])
    vote = Hypothesis("vote_" + digest(vote_edges)[:16], vote_edges, 0.)
    models["simple_vote"] = (PredictionTable([vote], simulator), [1.])
    baselines = {}
    for name, (model_table, model_weights) in models.items():
        t, status = calibrate_temperature(model_weights, split["calibration"], model_table)
        rows = prediction_rows(model_weights, split["test"], model_table, t)
        raw = prediction_rows(model_weights, split["test"], model_table)
        baselines[name] = {"status": "same_split_reconstructed_from_training_evidence",
                           "metrics": score_predictions(rows), "uncalibrated_metrics": score_predictions(raw),
                           "temperature": t, "calibration_status": status, "predictions": rows}
    baselines["single_network"]["definition"] = "Maximum-posterior graph after identical training outcomes; no averaging."
    baselines["simple_vote"]["definition"] = "Unique-paper majority per pair; ties omit edge; no evidence reliability weights."
    if original:
        baselines["original_flashp"] = original_baseline(original, split["test"], split["calibration"], noise, manifest, training)
    else:
        baselines["original_flashp"] = {"status": "not_run_requires_original_network_directory",
                                        "metrics": None, "reason": "Original LLM builder/refiner is not replaced by a fabricated deterministic baseline."}
    truth_id = None
    if data["metadata"]["source_type"] == "synthetic" and "ground_truth_edges" in data:
        truth = tuple(sorted(tuple(e) for e in data["ground_truth_edges"]))
        truth_id = next((h.id for h in hypotheses if tuple(sorted(h.edges)) == truth), None)
    active = [replay(weights, split["query"], split["test"], table, groups, budget,
                     policy, replay_seed, temperature, truth_id)
              for policy in ("information_gain", "random") for replay_seed in replay_seeds]
    query_summary = {}
    for policy in ("information_gain", "random"):
        runs = [r for r in active if r["policy"] == policy]
        truth_masses = [r["trace"][-1]["true_mechanism_probability"] for r in runs]
        query_summary[policy] = {"replays": len(runs), "budget_ceiling": budget,
            "mean_actual_spend": sum(r["spent"] for r in runs) / len(runs),
            "mean_final_test_nll": sum(r["trace"][-1]["test_metrics"]["nll"] for r in runs) / len(runs),
            "p95_identification_success_rate": sum(r["identification_cost_at_p95"] is not None for r in runs) / len(runs) if truth_id else None,
            "mean_final_true_mechanism_probability": sum(truth_masses) / len(runs) if truth_id else None}
    state = {"format_version": 1, "metadata": data["metadata"], "nodes": nodes,
             "noise": noise, "temperature": temperature,
             "hypotheses": [{"id": h.id, "edges": h.edges, "log_prior": h.log_prior,
                             "weight": w} for h, w in zip(hypotheses, weights)],
             "observations": [], "state_role": "training_fit_before_retrospective_query_replay",
             "dataset_sha256": digest(data), "split_manifest_sha256": digest(manifest)}
    report = {"evaluation_type": "synthetic_control" if data["metadata"]["source_type"] == "synthetic" else "retrospective_artifact_holdout",
              "implementation_sha256": digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                              for p in sorted(Path(__file__).parent.glob("*.py"))}),
              "upstream_solver_files_sha256": {name: hashlib.sha256((SHARED / name).read_bytes()).hexdigest()
                                                for name in ("evifork_bio_validator.py", "validation_common.py", "equation_executor.py", "light_io.py")},
              "configuration": {"max_hypotheses": max_hypotheses, "omission_prior": omission_prior,
                                "observation_noise": noise, "budget": budget, "replay_seeds": list(replay_seeds)},
              "prospective_discovery": False, "dataset_sha256": digest(data), "seed": seed,
              "sizes": {role: len(rows) for role, rows in split.items()},
              "construction_claims": len(training), "excluded_heldout_claims": len(manifest["excluded_claim_ids"]),
              "evidence_reliability": reliability.report(), "predictive_calibration_status": calibration_status,
              "hypothesis_space": {k: v for k, v in topology.items() if k != "pairs"},
              "conflicting_pairs": sum(p["is_conflict"] for p in topology["pairs"]),
              "baselines": baselines, "query_replays": active, "query_summary": query_summary,
              "query_protocol": "Outcome-only queries; at most one per independent paper/intervention component; equal budget ceilings; information gain may stop with unused budget when all candidates are equivalent.",
              "synthetic_truth_retained": truth_id is not None if data["metadata"]["source_type"] == "synthetic" else None,
              "limitations": data["metadata"].get("limitations", []) + [
                  "Holdout is enforced after extraction; source/LLM pretraining contamination cannot be ruled out.",
                  "A formal study needs a frozen raw corpus, extraction before outcome access, independent audits and repeated splits.",
                  "The observation noise channel and edge-omission prior are assumptions, not measured biological quantities.",
                  "Posterior entropy reduction in real data is not ground-truth mechanism identification.",
                  "Small calibration/test component counts make calibration and accuracy estimates unstable."]}
    write_json(output / "split_manifest.json", manifest)
    write_json(output / "training_claims.json", [asdict(c) for c in training])
    write_json(output / "training_perturbations.json", [asdict(c) for c in split["train"]])
    write_json(output / "hypotheses.json", state)
    write_json(output / "conflicts.json", topology)
    write_json(output / "report.json", report)
    write_json(output / "recommendations_from_query_features.json", rank_candidates(weights, split["query"], table))
    return report

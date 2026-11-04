"""Run with python -m evifork_bio from the repository root."""
import argparse
import math
from pathlib import Path

from .data import digest, parse_case, read_json, write_json
from .demo import make_demo
from .evaluate import rank_candidates
from .experiment import run_experiment
from .inference import Hypothesis, posterior_update
from .simulator import PredictionTable, Simulator


def state_table(path):
    state = read_json(path)
    if state.get("format_version") != 1 or not state.get("hypotheses"):
        raise ValueError("Invalid hypothesis state")
    hypotheses = []
    weights = []
    for row in state["hypotheses"]:
        edges = tuple(tuple(e) for e in row["edges"])
        if any(len(e) != 3 or e[2] not in (-1, 1) for e in edges):
            raise ValueError("Invalid state topology")
        hypotheses.append(Hypothesis(row["id"], edges, float(row["log_prior"])))
        weight = float(row["weight"])
        if not math.isfinite(weight) or weight < 0:
            raise ValueError("Invalid posterior weight")
        weights.append(weight)
    if not math.isclose(sum(weights), 1., abs_tol=1e-8):
        raise ValueError("State posterior does not sum to one")
    simulator = Simulator(state["nodes"], state["metadata"]["phenotype_node"], state["noise"])
    return state, weights, PredictionTable(hypotheses, simulator)


def validate_context(case, state):
    if case.context != state["metadata"]["context"] or case.phenotype != state["metadata"]["phenotype_node"]:
        raise ValueError("Candidate context/phenotype differs from fitted state")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m evifork_bio", description="EviFork-Bio: competing biological hypotheses with retrospective holdout evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="Conservatively import raw upstream curation")
    prep.add_argument("network_dir")
    prep.add_argument("--output", required=True)
    run = sub.add_parser("run", help="Split, fit, calibrate and evaluate a benchmark")
    run.add_argument("dataset")
    run.add_argument("--output", required=True)
    run.add_argument("--seed", type=int, default=17)
    run.add_argument("--max-hypotheses", type=int, default=32)
    run.add_argument("--omission-prior", type=float, default=0.)
    run.add_argument("--noise", type=float, default=.1)
    run.add_argument("--budget", type=float, default=5.)
    run.add_argument("--replay-seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    run.add_argument("--original-network", help="Upstream network directory; existing refined outputs are reference-only")
    demo = sub.add_parser("demo", help="Known-truth synthetic control, never presented as biology")
    demo.add_argument("--output", required=True)
    recommend = sub.add_parser("recommend", help="Rank unlabeled interventions by expected information gain / cost")
    recommend.add_argument("--state", required=True)
    recommend.add_argument("--candidates", required=True, help="JSON list of canonical intervention feature records")
    recommend.add_argument("--output", required=True)
    observe = sub.add_parser("observe", help="Update operational state with an actually observed outcome")
    observe.add_argument("--state", required=True)
    observe.add_argument("--observation", required=True, help="Intervention with outcome, experiment_id and provenance")
    observe.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in ("prepare", "recommend", "observe") and Path(args.output).exists():
            raise ValueError("Output file already exists; choose a fresh path")
        if args.command == "prepare":
            from .data import prepare_upstream
            data = prepare_upstream(args.network_dir, args.output)
            print(f"Prepared {len(data['claims'])} source claims / {len(data['perturbations'])} interventions; see import_audit for exclusions.")
        elif args.command == "run":
            report = run_experiment(args.dataset, args.output, seed=args.seed, max_hypotheses=args.max_hypotheses,
                omission_prior=args.omission_prior, budget=args.budget, noise=args.noise,
                original=args.original_network, replay_seeds=args.replay_seeds)
            print(f"Completed {report['evaluation_type']}: {report['sizes']}; report: {Path(args.output) / 'report.json'}")
        elif args.command == "demo":
            root = Path(args.output)
            if root.exists() and any(root.iterdir()):
                raise ValueError("Demo output directory must be empty")
            dataset = root / "synthetic_dataset.json"
            make_demo(dataset)
            report = run_experiment(dataset, root / "experiment", max_hypotheses=8, omission_prior=0., noise=.05, budget=3.)
            print(f"Synthetic control completed: {report['conflicting_pairs']} conflict(s), no biological discovery claim.")
        elif args.command == "recommend":
            state, weights, table = state_table(args.state)
            candidates = [parse_case(r, labeled=False) for r in read_json(args.candidates)]
            if len({c.id for c in candidates}) != len(candidates):
                raise ValueError("Duplicate candidate IDs")
            for case in candidates:
                validate_context(case, state)
            write_json(args.output, {"state_sha256": digest(state), "prospective_validation": False,
                       "recommendations": rank_candidates(weights, candidates, table),
                       "note": "These are model-based proposed interventions; no outcome is asserted."})
            print(f"Ranked {len(candidates)} unlabeled interventions.")
        else:
            state, weights, table = state_table(args.state)
            observation = read_json(args.observation)
            if not observation.get("experiment_id") or not observation.get("provenance"):
                raise ValueError("Observation needs an experiment_id and actual provenance")
            if observation["experiment_id"] in {r["experiment_id"] for r in state.get("observations", [])}:
                raise ValueError("Observation already assimilated")
            case = parse_case(observation, labeled=False)
            from .data import direction
            case.outcome = direction(observation["outcome"])
            validate_context(case, state)
            weights = posterior_update(weights, table.probabilities(case), case.outcome)
            for row, weight in zip(state["hypotheses"], weights):
                row["weight"] = weight
            state.setdefault("observations", []).append(observation)
            state["state_role"] = "operational_update_not_an_untouched_holdout_evaluation"
            write_json(args.output, state)
            print("Updated operational posterior; original benchmark state was not edited.")
    except (ValueError, KeyError, TypeError, FileNotFoundError, RuntimeError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()

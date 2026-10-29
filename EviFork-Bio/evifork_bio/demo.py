"""A deliberately synthetic control; identifiers are synthetic namespaces, not DOIs."""
from .data import write_json


def make_demo(output):
    context = "synthetic_control"
    claims = [{"id": key, "source": source, "target": target, "sign": sign,
               "doi": "synthetic:" + key, "context": context, "quality": "unknown"}
              for key, source, target, sign in [("positive", "A", "B", 1), ("negative", "A", "B", -1),
                                                ("endpoint", "B", "Trait", 1), ("null_control", "C", "Trait", 0)]]
    roles = {name: [] for name in ("train", "calibration", "query", "test")}
    cases = []
    def case(key, gene, modifier, outcome, role):
        roles[role].append(key)
        cases.append({"id": key, "genes": {gene: modifier}, "supply": {}, "baseline_genes": {},
                      "baseline_supply": {}, "phenotype": "Trait", "context": context,
                      "outcome": outcome, "dois": ["synthetic:experiment_" + key], "cost": 1})
    for i, dose in enumerate((0., .2, .4, .6)):
        case(f"train{i}", "B", dose, -1, "train")
    for i, dose in enumerate((.3, .5, 1.5, 2.)):
        case(f"cal{i}", "B", dose, -1 if dose < 1 else 1, "calibration")
    case("informative_A", "A", 0., -1, "query")
    for i, dose in enumerate((0., .3, .5, .7, 1.5, 2., 3., 4.)):
        case(f"decoy{i}", "C", dose, 0, "query")
    for i, dose in enumerate((.2, .4, 2., 3.)):
        case(f"test{i}", "A", dose, -1 if dose < 1 else 1, "test")
    data = {"format_version": 1, "metadata": {"source_type": "synthetic", "context": context,
            "phenotype_node": "Trait", "limitations": ["Synthetic control only; not biological evidence or performance on a real discovery task."]},
            "claims": claims, "perturbations": cases, "audits": [], "split_roles": roles,
            "ground_truth_edges": [["A", "B", 1], ["B", "Trait", 1]]}
    write_json(output, data)
    return data

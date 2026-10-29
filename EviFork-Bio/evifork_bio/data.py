"""Explicit input contracts and conservative import of upstream literature artifacts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re

DIRECTIONS = (-1, 0, 1)
DOI = re.compile(r"10\.\d{4,9}/\S+", re.I)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def normalize_doi(value, allow_synthetic=False):
    if not isinstance(value, str):
        raise ValueError("DOI must be a string")
    if allow_synthetic and value.startswith("synthetic:") and len(value) > 10:
        return value
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.I).lower()
    if not DOI.fullmatch(value):
        raise ValueError("Missing or syntactically invalid DOI (resolution is not implied)")
    return value


def direction(value):
    mapping = {"increased": 1, "up": 1, "decreased": -1, "dn": -1, "unchanged": 0, "nc": 0}
    if isinstance(value, str):
        value = mapping.get(value.lower(), value)
    if isinstance(value, bool) or value not in DIRECTIONS:
        raise ValueError(f"Invalid outcome direction: {value!r}")
    return int(value)


def numbers(value):
    if not isinstance(value, dict):
        raise ValueError("Modifiers and supplies must be dictionaries")
    result = {}
    for key, number in value.items():
        if not isinstance(key, str) or not key or isinstance(number, bool):
            raise ValueError("Invalid intervention entry")
        number = float(number)
        if not math.isfinite(number) or number < 0:
            raise ValueError("Intervention values must be finite and nonnegative")
        result[key] = number
    return result


@dataclass(frozen=True)
class Claim:
    id: str
    source: str
    target: str
    sign: int
    doi: str
    context: str
    quality: str = "unknown"


@dataclass
class Case:
    id: str
    genes: dict
    supply: dict
    baseline_genes: dict
    baseline_supply: dict
    phenotype: str
    context: str
    outcome: int | None
    dois: tuple = ()
    cost: float = 1.0

    def features(self):
        return {key: getattr(self, key) for key in
                ("genes", "supply", "baseline_genes", "baseline_supply", "phenotype", "context")}

    def signature(self):
        return digest(self.features())


def parse_case(row, *, labeled=True, allow_synthetic=False):
    for key in ("id", "phenotype", "context"):
        if not isinstance(row.get(key), str) or not row[key]:
            raise ValueError(f"Case needs nonempty {key}")
    cost = float(row.get("cost", 1))
    if not math.isfinite(cost) or cost <= 0:
        raise ValueError("Query cost must be finite and positive")
    dois = tuple(sorted({normalize_doi(x, allow_synthetic) for x in row.get("dois", [])}))
    if labeled and not dois:
        raise ValueError("Benchmark outcomes require source DOIs")
    return Case(row["id"], numbers(row.get("genes", {})), numbers(row.get("supply", {})),
                numbers(row.get("baseline_genes", {})), numbers(row.get("baseline_supply", {})),
                row["phenotype"], row["context"], direction(row["outcome"]) if labeled else None,
                dois, cost)


def load_dataset(path):
    data = read_json(path)
    if data.get("format_version") != 1:
        raise ValueError("Expected hypothesis format_version 1")
    meta = data["metadata"]
    for key in ("context", "phenotype_node", "source_type"):
        if not isinstance(meta.get(key), str) or not meta[key]:
            raise ValueError(f"metadata.{key} required")
    synthetic = meta["source_type"] == "synthetic"
    claims = []
    for row in data["claims"]:
        c = Claim(row["id"], row["source"], row["target"], direction(row["sign"]),
                  normalize_doi(row["doi"], synthetic), row["context"], row.get("quality", "unknown"))
        if not all(isinstance(s, str) and s for s in (c.id, c.source, c.target, c.context, c.quality)):
            raise ValueError("Invalid claim identifiers")
        claims.append(c)
    cases = [parse_case(row, allow_synthetic=synthetic) for row in data["perturbations"]]
    for rows in (claims, cases):
        if len({r.id for r in rows}) != len(rows):
            raise ValueError("Duplicate record IDs")
    if any(row.context != meta["context"] for row in claims + cases):
        raise ValueError("Mixed contexts: prepare separate datasets for each context")
    if any(c.phenotype != meta["phenotype_node"] for c in cases):
        raise ValueError("Mixed phenotype endpoints are not supported in one experiment")
    if not claims or len(cases) < 4:
        raise ValueError("Need evidence claims and at least four labeled cases")
    return data, claims, cases


def evidence_rows(row):
    evidence = row.get("evidence", [])
    if isinstance(evidence, dict):
        evidence = [evidence]
    if not isinstance(evidence, list):
        evidence = []
    if row.get("doi", row.get("d")):
        evidence = evidence + [{"doi": row.get("doi", row.get("d"))}]
    return [x for x in evidence if isinstance(x, dict)]


def prepare_upstream(network_dir, output):
    """Import raw curation, never final topology, refined tests, or reported accuracy."""
    root = Path(network_dir)
    edges = read_json(root / "data/curated_edges.json")
    tests = read_json(root / "data/perturbation_dataset.json")
    metadata = edges.get("metadata", {})
    phenotype = metadata.get("phenotype_node")
    if not phenotype:
        phenotype = str(metadata.get("phenotype", "")).replace(" ", "_")
        candidates = {str(e.get("target", e.get("t", ""))) for e in edges["edges"]}
        matches = sorted(n for n in candidates if n.casefold() == phenotype.casefold())
        if len(matches) != 1:
            raise ValueError("Cannot establish phenotype node from raw curation metadata")
        phenotype = matches[0]
    context = canonical({"species": metadata.get("species", "unspecified"), "resolution": "upstream_coarse"})
    claims, cases, quarantine = [], [], []
    nodes = set()
    for index, row in enumerate(edges["edges"]):
        source, target = row.get("source", row.get("s")), row.get("target", row.get("t"))
        if row.get("v") == "q" or not source or not target:
            quarantine.append({"kind": "edge", "index": index, "reason": "quarantined or missing endpoints"})
            continue
        try:
            sign = direction(row.get("sign", row.get("x")))
        except ValueError as error:
            quarantine.append({"kind": "edge", "index": index, "reason": str(error)})
            continue
        valid = {}
        for e in evidence_rows(row):
            try:
                doi = normalize_doi(e.get("doi", ""))
                valid[doi] = "fulltext" if e.get("full_text_read") else "unknown"
            except ValueError:
                pass
        if not valid:
            quarantine.append({"kind": "edge", "index": index, "reason": "no syntactically valid source DOI"})
        for doi, quality in sorted(valid.items()):
            claims.append(asdict(Claim(f"C{index:05d}_{digest(doi)[:10]}", source, target, sign, doi, context, quality)))
            nodes.update((source, target))
    folded = {}
    for node in nodes:
        folded.setdefault(node.casefold(), []).append(node)
    for index, row in enumerate(tests["perturbations"]):
        try:
            if row.get("v") == "q":
                raise ValueError("Source quarantined upstream")
            reported_species = row.get("species", row.get("sp"))
            target_species = metadata.get("species")
            if reported_species and target_species and reported_species.strip().casefold() != target_species.strip().casefold():
                raise ValueError("Different reported species; explicit transfer hypothesis required")
            dois = []
            for e in evidence_rows(row):
                try:
                    dois.append(normalize_doi(e.get("doi", "")))
                except ValueError:
                    pass
            genes, supply = row.get("gene_modifiers", row.get("m")), row.get("exogenous_supply", row.get("exo", {}))
            if genes is None:
                kind = row.get("perturbation_type", row.get("pt", "")).lower()
                modifier = {"knockout": 0, "ko": 0, "knockdown": .5, "kd": .5,
                            "overexpression": 2, "oe": 2}.get(kind)
                if modifier is None:
                    raise ValueError("Complex intervention requires explicit numeric modifiers; no inferred encoding")
                gene = row.get("gene", row.get("g", ""))
                matched = folded.get(str(gene).casefold(), [])
                if len(matched) != 1:
                    raise ValueError("No unique raw-curation node mapping")
                genes = {matched[0]: modifier}
            cb = row.get("comparison_baseline", row.get("cb", "WT"))
            baseline = row.get("baseline_modifiers", {})
            if cb.lower() != "wt" and not baseline:
                raise ValueError("Non-WT comparison requires explicit baseline modifiers")
            item = {"id": row.get("test_id", row.get("id", f"T{index:05d}")),
                    "genes": genes, "supply": supply, "baseline_genes": baseline,
                    "baseline_supply": row.get("baseline_exogenous", {}), "phenotype": phenotype,
                    "context": context, "outcome": row.get("expected_direction", row.get("ed")),
                    "dois": sorted(set(dois)), "reported_condition": row.get("condition"),
                    "reported_species": row.get("species", row.get("sp"))}
            parse_case(item)
            cases.append(item)
        except (ValueError, TypeError, AttributeError) as error:
            quarantine.append({"kind": "perturbation", "index": index, "reason": str(error)})
    payload = {"format_version": 1,
               "metadata": {"phenotype_node": phenotype, "context": context,
                            "source_type": "retrospective_upstream_artifact",
                            "limitations": ["Curation may already reflect upstream model selection and LLM prior knowledge.",
                                            "Context is coarse; original experimental conditions need manual reconciliation.",
                                            "DOI syntax and upstream full-text flags are not independent evidence verification.",
                                            "Default KD=.5 and OE=2 are simulation encodings, not measured doses."]},
               "claims": claims, "perturbations": cases, "audits": [],
               "import_audit": {"input_edges": len(edges["edges"]), "input_tests": len(tests["perturbations"]),
                                "input_files_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                                       for name in ("data/curated_edges.json", "data/perturbation_dataset.json")},
                                "retained_claims": len(claims), "retained_tests": len(cases), "quarantine": quarantine}}
    write_json(output, payload)
    return payload

"""Joint paper / intervention component splits; labels never drive assignment."""
from dataclasses import asdict
import random
from .data import digest


def split_dataset(claims, cases, seed=17, assignments=None):
    parent = list(range(len(cases)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        parent[find(a)] = find(b)

    owners = {}
    for i, case in enumerate(cases):
        for key in [("doi", d) for d in case.dois] + [("intervention", case.signature())]:
            if key in owners:
                union(i, owners[key])
            owners[key] = i
    components = {}
    for i, case in enumerate(cases):
        components.setdefault(find(i), []).append(case)
    groups = sorted(components.values(), key=lambda g: sorted(c.id for c in g))
    if len(groups) < 4:
        raise ValueError("Fewer than four independent paper/intervention components: cannot make train/calibration/query/test split")
    random.Random(seed).shuffle(groups)
    # At least one independent component per role; approximate 50/17/17/17 thereafter.
    counts = [1, 1, 1, 1]
    ratios = [.5, 1/6, 1/6, 1/6]
    for _ in range(len(groups) - 4):
        i = min(range(4), key=lambda j: counts[j] / ratios[j])
        counts[i] += 1
    roles = ("train", "calibration", "query", "test")
    split, group_ids, cursor = {}, {}, 0
    for role, count in zip(roles, counts):
        split[role] = []
        for group in groups[cursor:cursor + count]:
            gid = digest(sorted(c.id for c in group))[:16]
            for c in group:
                group_ids[c.id] = gid
            split[role].extend(group)
        split[role].sort(key=lambda c: c.id)
        cursor += count
    if assignments is not None:
        mapping = {case_id: role for role, ids in assignments.items() for case_id in ids}
        if set(assignments) != set(roles) or set(mapping) != {c.id for c in cases} or sum(map(len, assignments.values())) != len(cases):
            raise ValueError("Explicit split must assign each case exactly once to all four roles")
        for group in groups:
            if len({mapping[c.id] for c in group}) != 1:
                raise ValueError("Explicit split leaks a paper/intervention component across roles")
        split = {role: sorted((c for c in cases if mapping[c.id] == role), key=lambda c: c.id) for role in roles}
        if any(not split[role] for role in roles):
            raise ValueError("Every explicit split role must be nonempty")
    papers = {role: sorted({d for c in split[role] for d in c.dois}) for role in roles}
    forbidden = set(papers["calibration"] + papers["query"] + papers["test"])
    training_claims = [c for c in claims if c.doi not in forbidden]
    if not training_claims:
        raise ValueError("Paper holdout removes all construction evidence; no honest fit possible")
    for a in roles:
        for b in roles:
            if a != b:
                assert not set(papers[a]) & set(papers[b])
                assert not {c.signature() for c in split[a]} & {c.signature() for c in split[b]}
    manifest = {"seed": seed, "assignment_uses_outcomes": False, "explicit_assignment": assignments is not None, "roles": {},
                "training_claims_sha256": digest([asdict(c) for c in training_claims]),
                "excluded_claim_ids": [c.id for c in claims if c.doi in forbidden]}
    for role in roles:
        manifest["roles"][role] = {"ids": [c.id for c in split[role]], "dois": papers[role],
                                   "components": sorted({group_ids[c.id] for c in split[role]})}
    return training_claims, split, group_ids, manifest

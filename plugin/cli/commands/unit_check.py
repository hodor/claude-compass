"""`compass unit-check` - report unit-promotion candidates.

Groups root-level artifacts by the spec they reach through `depends_on`
wikilinks, followed transitively. When 3 or more distinct artifact types
(the spec's own type included) trace to one spec, that group has type-spread
and is printed as a candidate unit with its member list and a suggested
`compass make-unit` invocation. Detection is mechanical; whether to promote
is the human's decision, so the command only reports and always exits 0.
"""

import re
import sys

import vaultlib

TYPE_SPREAD_THRESHOLD = 3

# A spec this many artifacts depend on directly is a vault-wide hub, not a
# unit seed: half the vault tracing to it is dominance, not cohesion, and it
# drowns the real candidates (SPEC-001 measured 17 inbound; genuine unit
# seeds measure well under this).
HUB_INBOUND_CAP = 10

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")

# Fallback type for an artifact whose frontmatter lacks `type`: the singular
# of its type directory, so it still counts once in the spread.
DIR_TO_TYPE = {directory: type_ for type_, directory in vaultlib.TYPE_TO_DIR.items()}


def _dep_targets(data):
    """Wikilink targets named in a record's `depends_on` frontmatter."""
    deps = data.get("depends_on")
    if isinstance(deps, str):
        deps = [deps]
    targets = []
    for item in deps or []:
        for raw in WIKILINK.findall(item):
            target = raw.split("#")[0].split("|")[0].strip()
            if target:
                targets.append(target)
    return targets


def _artifact_type(record):
    return record["_data"].get("type") or DIR_TO_TYPE.get(record["type_dir"], record["type_dir"])


def _reachable_specs(rel, edges, by_path):
    """Vault-relative paths of every spec reachable from `rel` by following
    `depends_on` edges transitively. Cycle-safe via a visited set."""
    found, visited, stack = set(), set(), [rel]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for dep in edges.get(current, []):
            if _artifact_type(by_path[dep]) == "spec":
                found.add(dep)
            stack.append(dep)
    return found


def _suggested_name(spec_path):
    """Unit-folder name suggestion: the spec's descriptive slug (stem with
    the `SPEC-NNN-` prefix dropped), falling back to the full stem."""
    stem = spec_path.stem
    match = re.match(r"^SPEC-\d+-(.+)$", stem)
    return match.group(1) if match else stem


def find_candidates(vault_root):
    """Return candidate units: `(spec_rel, members, types)` tuples, one per
    root-level spec whose depends_on tracers span TYPE_SPREAD_THRESHOLD or
    more distinct artifact types. `members` is the spec plus every tracer,
    vault-relative and sorted; `types` is the sorted distinct type list.
    Artifacts already inside a unit folder are settled and not considered.
    """
    records = [r for r in vaultlib.scan_artifacts(vault_root) if r["unit"] is None]
    resolve = vaultlib.resolvable_names_map(vault_root)
    by_path = {}
    for record in records:
        record["_rel"] = record["path"].relative_to(vault_root).as_posix()
        data, error = vaultlib.parse_frontmatter(record["path"])
        record["_data"] = {} if error else data
        by_path[record["_rel"]] = record

    edges = {}
    for record in records:
        deps = []
        for target in _dep_targets(record["_data"]):
            paths = resolve.get(target, [])
            # Only an unambiguous link to a scanned artifact is an edge.
            if len(paths) == 1 and paths[0] in by_path:
                deps.append(paths[0])
        edges[record["_rel"]] = deps

    groups = {}
    for record in records:
        for spec_rel in _reachable_specs(record["_rel"], edges, by_path):
            groups.setdefault(spec_rel, []).append(record["_rel"])

    inbound_degree = {}
    for deps in edges.values():
        for dep in deps:
            inbound_degree[dep] = inbound_degree.get(dep, 0) + 1

    candidates = []
    for spec_rel in sorted(groups):
        if inbound_degree.get(spec_rel, 0) >= HUB_INBOUND_CAP:
            continue
        members = sorted({spec_rel, *groups[spec_rel]})
        types = sorted({_artifact_type(by_path[rel]) for rel in members})
        if len(types) >= TYPE_SPREAD_THRESHOLD:
            candidates.append((spec_rel, members, types))
    return candidates


def format_report(vault_root, candidates):
    if not candidates:
        return "compass unit-check: no candidates (no spec with type-spread >= 3)"
    lines = [f"compass unit-check: {len(candidates)} candidate(s)"]
    for spec_rel, members, types in candidates:
        name = _suggested_name(vault_root / spec_rel)
        lines.append("")
        lines.append(f"candidate: {name} (type-spread {len(types)}: {', '.join(types)})")
        lines.append(f"  spec: {spec_rel}")
        lines.append("  members:")
        for member in members:
            lines.append(f"    - {member}")
        lines.append(f"  suggested: compass make-unit {name} " + " ".join(members))
    return "\n".join(lines)


def run(args):
    vault_root = vaultlib.find_vault_root()
    candidates = find_candidates(vault_root)
    sys.stdout.write(format_report(vault_root, candidates) + "\n")
    return 0

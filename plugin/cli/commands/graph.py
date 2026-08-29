"""`compass graph` - orphans, hubs, and impact over the vault's link graph.

Answers are computed from the markdown at invocation (see `vaultgraph`), so
they are always current, and every answer names the edges that produced it
so a consumer audits the traversal instead of trusting a total.

- `orphans`: artifacts with no inbound structural edge. The root index.md
  catalog row every artifact gets from sync does not count as a reference.
- `hubs [--top N]`: inbound-degree ranking, depends_on and wikilink counted
  separately. `unit-check`'s dominance guard reads the same numbers.
- `impact <name> [--depth N]`: inbound breadth-first traversal - what
  depends on, links to, or contains the named artifact, transitively to the
  bound (default 2), one `src -[kind]-> dst` line per edge per hop.
"""

import sys

import vaultgraph
import vaultlib


def _flag_value(args, flag, default):
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            try:
                return int(args[i + 1])
            except ValueError:
                pass
    return default


# Types whose reference channel is not links: lessons are retrieved through
# the catalog (SPEC-012) and carry no artifact-graph edges by design, and a
# handoff is a terminal session snapshot nothing later should need to cite.
# Reporting them would bury every real orphan in permanent noise.
ORPHAN_EXEMPT_TYPE_DIRS = {"lessons", "handoffs"}


def _run_orphans(vault_root, graph):
    artifact_rels = {
        r["path"].relative_to(vault_root).as_posix()
        for r in vaultlib.scan_artifacts(vault_root)
        if r["type_dir"] not in ORPHAN_EXEMPT_TYPE_DIRS
    }
    linked = vaultgraph.inbound(graph)
    orphans = sorted(rel for rel in artifact_rels if not linked.get(rel))
    if not orphans:
        sys.stdout.write("compass graph: no orphans (lessons and handoffs exempt by design)\n")
        return 0
    sys.stdout.write(f"compass graph: {len(orphans)} orphan(s) - no inbound reference besides the index catalog row (lessons and handoffs exempt by design)\n")
    for rel in orphans:
        sys.stdout.write(f"  {rel}\n")
    return 0


def _run_hubs(vault_root, graph, args):
    top = _flag_value(args, "--top", 10)
    counts = {}
    for edge in graph["edges"]:
        if edge["kind"] in ("depends_on", "wikilink"):
            row = counts.setdefault(edge["dst"], {"depends_on": 0, "wikilink": 0})
            row[edge["kind"]] += 1
    ranked = sorted(
        counts.items(),
        key=lambda kv: (-(kv[1]["depends_on"] + kv[1]["wikilink"]), kv[0]),
    )[:top]
    sys.stdout.write("compass graph: inbound-degree ranking\n")
    for rank, (rel, row) in enumerate(ranked, start=1):
        total = row["depends_on"] + row["wikilink"]
        sys.stdout.write(
            f"  {rank}. {rel}  total {total}  depends_on {row['depends_on']}"
            f"  wikilink {row['wikilink']}\n"
        )
    return 0


def _run_impact(vault_root, graph, args):
    positional = [a for a in args if not a.startswith("--") and not a.isdigit()]
    if not positional:
        sys.stderr.write("usage: compass graph impact <name> [--depth N]\n")
        return 1
    name = positional[0]
    depth = _flag_value(args, "--depth", 2)

    resolve = vaultlib.resolvable_names_map(vault_root)
    paths = resolve.get(name, [])
    if len(paths) != 1 or paths[0] not in graph["nodes"]:
        state = "ambiguous" if len(paths) > 1 else "unresolvable"
        sys.stderr.write(f"compass graph: {state} name: {name}\n")
        return 1
    target = paths[0]

    linked = vaultgraph.inbound(graph)
    frontier = {target}
    visited = {target}
    printed = 0
    for hop in range(1, depth + 1):
        next_frontier = set()
        for dst in sorted(frontier):
            for edge in linked.get(dst, []):
                if edge["src"] in visited:
                    continue
                sys.stdout.write(
                    f"  hop {hop}: {edge['src']} -[{edge['kind']}]-> {edge['dst']}\n"
                )
                next_frontier.add(edge["src"])
                printed += 1
        visited |= next_frontier
        frontier = next_frontier
        if not frontier:
            break
    if not printed:
        sys.stdout.write(f"compass graph: no inbound impact on {target}\n")
    return 0


def run(args):
    if not args or args[0] not in ("orphans", "hubs", "impact"):
        sys.stderr.write("usage: compass graph orphans | hubs [--top N] | impact <name> [--depth N]\n")
        return 1
    vault_root = vaultlib.find_vault_root()
    graph = vaultgraph.build_graph(vault_root)
    sub, rest = args[0], args[1:]
    if sub == "orphans":
        return _run_orphans(vault_root, graph)
    if sub == "hubs":
        return _run_hubs(vault_root, graph, rest)
    return _run_impact(vault_root, graph, rest)

"""The vault's link graph, parsed from the markdown at every call (ADR-018).

No derived store exists: `build_graph` reads the disk when asked, so an
answer can never be stale - deletions, renames, and CLI moves are simply
present or absent in the next parse. Named `vaultgraph` because the stdlib
owns `graphlib`.

Edge kinds:
- `depends_on` - a frontmatter `depends_on` wikilink.
- `citation`   - a frontmatter `lessons:` wikilink (a plan citing a lesson).
- `wikilink`   - a body wikilink outside code fences and inline code spans.
- `containment` - a folder artifact's `index.md` to a file inside its folder.
- `index`      - any edge whose source is the root `index.md`; the catalog
  row every artifact gets from `compass sync`, excluded from orphan and
  impact answers because it says "cataloged", not "referenced".

Prose that names a document without `[[ ]]` creates nothing, and an
ambiguous name resolves to no edge - the same rules `validate` and
`unit-check` already live by.
"""

import re
from pathlib import Path

import vaultlib

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
INLINE_CODE = re.compile(r"`[^`]*`")

STRUCTURAL_KINDS = ("depends_on", "wikilink", "containment", "citation")


def _target(raw):
    return raw.split("#")[0].split("|")[0].strip()


def _split_frontmatter(text):
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1 :])
    return text


def _body_links(text):
    """Wikilink targets in body text, skipping fenced blocks and inline code."""
    in_fence = False
    for line in _split_frontmatter(text).split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for raw in WIKILINK.findall(INLINE_CODE.sub("", line)):
            target = _target(raw)
            if target:
                yield target

def _frontmatter_links(data, key):
    values = data.get(key)
    if isinstance(values, str):
        values = [values]
    for item in values or []:
        for raw in WIKILINK.findall(str(item)):
            target = _target(raw)
            if target:
                yield target


def build_graph(vault_root):
    """Return {"nodes": {rel: path}, "edges": [{"src", "dst", "kind"}]},
    where rel is the vault-relative POSIX path. Sources include the root
    index.md and the top-level task files; only unambiguous names that
    resolve to a file in the graph become edges."""
    vault_root = Path(vault_root)
    resolve = vaultlib.resolvable_names_map(vault_root)

    files = vaultlib.all_markdown_files(vault_root)
    nodes = {p.relative_to(vault_root).as_posix(): p for p in files}

    def resolve_one(target):
        paths = resolve.get(target, [])
        if len(paths) == 1 and paths[0] in nodes:
            return paths[0]
        return None

    edges = []

    def add(src, dst, kind):
        if dst is not None and dst != src:
            edges.append({"src": src, "dst": dst, "kind": kind})

    for rel, path in nodes.items():
        text = vaultlib.read_vault_text(path)
        source_kind = "index" if rel == "index.md" else None

        data, error = vaultlib.parse_frontmatter(path)
        if not error:
            for target in _frontmatter_links(data, "depends_on"):
                add(rel, resolve_one(target), source_kind or "depends_on")
            for target in _frontmatter_links(data, "lessons"):
                add(rel, resolve_one(target), source_kind or "citation")
        for target in _body_links(text):
            add(rel, resolve_one(target), source_kind or "wikilink")

        # A folder artifact's index.md structurally contains its siblings.
        if path.name == "index.md" and rel != "index.md":
            for sibling in path.parent.iterdir():
                if sibling == path:
                    continue
                if sibling.is_file() and sibling.suffix == ".md":
                    add(rel, sibling.relative_to(vault_root).as_posix(), "containment")
                elif sibling.is_dir() and (sibling / "index.md").is_file():
                    add(
                        rel,
                        (sibling / "index.md").relative_to(vault_root).as_posix(),
                        "containment",
                    )

    return {"nodes": nodes, "edges": edges}


def inbound(graph, kinds=STRUCTURAL_KINDS):
    """Map of rel -> list of inbound edges of the given kinds."""
    result = {}
    for edge in graph["edges"]:
        if edge["kind"] in kinds:
            result.setdefault(edge["dst"], []).append(edge)
    return result

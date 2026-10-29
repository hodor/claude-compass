"""`compass canvas` - the spec tree written as `.compass/specs.canvas`.

The canvas is a JSON Canvas 1.0 file Obsidian opens as a board: one file
card per spec file (a folder spec by its `index.md`) and a line from each
folder spec to its direct children. A topic folder's own `index.md` is not
a spec and gets no card, so specs filed under a topic folder appear
without a line to the folder.

A rerun reconciles the file in place. A card for a spec that is still
there keeps its id, position and size; a spec that appeared gets a card
below the existing ones, in a column per folder depth; a card whose file
no longer exists loses its card. Lines between spec cards are regenerated
from the folder structure (their ids start with `tree-`); any other node,
any card for a file that still exists, and any line the human drew stay
when its endpoints stay. A canvas that is not valid JSON is left
untouched and reported.
"""

import hashlib
import json
import sys

import vaultlib

CANVAS_NAME = "specs.canvas"
EDGE_PREFIX = "tree-"
CARD_WIDTH = 400
CARD_HEIGHT = 120
COLUMN_STEP = 480
ROW_GAP = 40


def _is_card_geometry(node):
    return all(
        isinstance(node.get(key), (int, float)) and not isinstance(node.get(key), bool)
        for key in ("x", "y", "width", "height")
    )


def _spec_cards(vault_root):
    """Every spec file as `(vault-relative path, depth, parent path)`, in
    reading order. The parent is the `index.md` of the enclosing folder
    spec, or None for a spec with no folder spec above it."""
    records = [
        r for r in vaultlib.scan_artifacts(vault_root) if r["type_dir"] == "specs"
    ]
    rels = {}
    for record in records:
        if record["kind"] == "folder-index":
            data, _ = vaultlib.parse_frontmatter(record["path"])
            if data.get("type") == "domain":
                continue
        rels[record["path"].relative_to(vault_root).as_posix()] = record
    cards = []
    for rel in sorted(rels):
        record = rels[rel]
        parts = rel.split("/")
        folder = parts[:-1] if record["kind"] != "folder-index" else parts[:-2]
        parent = "/".join(folder + ["index.md"])
        cards.append((rel, record["depth"], parent if parent in rels else None))
    return cards


def _node_id(rel, taken):
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()
    for length in range(16, 41):
        candidate = digest[:length]
        if candidate not in taken:
            return candidate
    return digest


def _load_canvas(path):
    """The existing canvas as a dict, an empty one when the file is absent.
    Raises ValueError when the file exists but is not a canvas."""
    if not path.is_file():
        return {"nodes": [], "edges": []}
    try:
        data = json.loads(vaultlib.read_vault_text(path))
    except ValueError as exc:
        raise ValueError(f"{path.name} is not valid JSON ({exc})")
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is not a JSON Canvas object")
    for key in ("nodes", "edges"):
        if not isinstance(data.get(key, []), list):
            raise ValueError(f"{path.name} has a {key} entry that is not a list")
        data.setdefault(key, [])
    return data


def build(existing, cards, file_exists):
    """Reconcile `existing` (a canvas dict) with the spec `cards`;
    `file_exists` says whether a vault-relative path still names a file.
    Returns (canvas dict, added file paths, removed file paths)."""
    old_nodes = [n for n in existing["nodes"] if isinstance(n, dict)]
    wanted = {rel for rel, _, _ in cards}
    kept, by_file, removed = [], {}, []
    for node in old_nodes:
        if node.get("type") != "file":
            kept.append(node)
            continue
        file = node.get("file")
        if not isinstance(file, str):
            kept.append(node)
        elif file in wanted:
            if file not in by_file:
                by_file[file] = node
                kept.append(node)
        elif file_exists(file):
            kept.append(node)
        else:
            removed.append(file)
    taken = {n.get("id") for n in kept if isinstance(n.get("id"), str)}

    bottom = max(
        (n["y"] + n["height"] for n in kept if _is_card_geometry(n)), default=None
    )
    next_y = 0 if bottom is None else bottom + ROW_GAP
    added = []
    for rel, depth, _ in cards:
        node = by_file.get(rel)
        if node is None:
            node = {"id": _node_id(rel, taken), "type": "file", "file": rel}
            kept.append(node)
            by_file[rel] = node
            added.append(rel)
        if not isinstance(node.get("id"), str):
            node["id"] = _node_id(rel, taken)
        taken.add(node["id"])
        if not _is_card_geometry(node):
            node["x"] = depth * COLUMN_STEP
            node["y"] = next_y
            node["width"] = CARD_WIDTH
            node["height"] = CARD_HEIGHT
            next_y += CARD_HEIGHT + ROW_GAP

    live_ids = {n["id"] for n in kept if isinstance(n.get("id"), str)}
    edges = [
        e for e in existing["edges"]
        if isinstance(e, dict)
        and not str(e.get("id", "")).startswith(EDGE_PREFIX)
        and e.get("fromNode") in live_ids
        and e.get("toNode") in live_ids
    ]
    for rel, _, parent in cards:
        if parent is None:
            continue
        from_id, to_id = by_file[parent]["id"], by_file[rel]["id"]
        edges.append({
            "id": f"{EDGE_PREFIX}{from_id}-{to_id}",
            "fromNode": from_id,
            "toNode": to_id,
        })
    canvas = dict(existing)
    canvas["nodes"] = kept
    canvas["edges"] = edges
    return canvas, added, removed


def run(args):
    if args:
        sys.stderr.write("usage: compass canvas\n")
        return 1
    try:
        vault_root = vaultlib.find_vault_root()
    except FileNotFoundError as exc:
        sys.stderr.write(f"compass canvas: {exc}\n")
        return 1
    path = vault_root / CANVAS_NAME
    try:
        existing = _load_canvas(path)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"compass canvas: {exc}; left untouched\n")
        return 1
    canvas, added, removed = build(
        existing, _spec_cards(vault_root), lambda rel: (vault_root / rel).is_file())
    try:
        vaultlib.write_text_lf(
            path, json.dumps(canvas, indent="\t", ensure_ascii=False))
    except OSError as exc:
        sys.stderr.write(f"compass canvas: cannot write {CANVAS_NAME}: {exc}\n")
        return 1
    card_count = sum(1 for n in canvas["nodes"] if n.get("type") == "file")
    sys.stdout.write(
        f"compass canvas: wrote {path.relative_to(vault_root.parent).as_posix()} "
        f"({card_count} card(s), {len(canvas['edges'])} line(s); "
        f"{len(added)} added, {len(removed)} removed)\n"
    )
    return 0

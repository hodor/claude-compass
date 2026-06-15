"""`compass validate` - vault integrity check.

Three checks across the whole vault: required frontmatter per type, wikilink
resolution (skipping code), and the hot-path cap. Exits 0 when clean, 1 when
any defect is found. This is a human/CI command; its non-zero exit reports
defects and is distinct from the hook path, which must never block a write.
"""

import re
import sys

import vaultlib
from commands.hot_path import HOT_PATH_CAP, measure

REQUIRED_FIELDS = {
    "spec": ["title", "type", "status", "area", "tags", "created", "updated"],
    "plan": ["title", "type", "status", "area", "tags", "created", "updated", "depends_on"],
    "research": ["title", "type", "status", "area", "tags", "created", "updated"],
    "decision": ["title", "type", "status", "confidence", "area", "tags", "created", "updated"],
    "lesson": ["title", "type", "status", "category", "area", "tags", "created", "updated", "score", "summary"],
    "handoff": ["title", "type", "status", "area", "tags", "created", "updated"],
}

# Top-level vault files a wikilink may target without living in a type dir.
SPECIAL_TARGETS = {"active", "backlog", "index", "vision"}

INDEX_LINE_CAP = 250

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
INLINE_CODE = re.compile(r"`[^`]*`")


def _resolvable_names(vault_root):
    """Every name a wikilink may legitimately resolve to.

    Built from the scanned artifacts: each artifact's wikilink identity
    (flat stem, folder path, or child path) plus its bare file stem, so a
    reference by short name or by qualified path both resolve. Folder specs
    resolve by their folder name even though the file on disk is `index.md`.
    """
    names = set(SPECIAL_TARGETS)
    for record in vaultlib.scan_artifacts(vault_root):
        names.add(record["name"])
        names.add(record["path"].stem)
    return names


def _wikilinks_in(text):
    """Yield (line_number, target) for wikilinks outside code blocks/spans."""
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        cleaned = INLINE_CODE.sub("", line)
        for match in WIKILINK.finditer(cleaned):
            target = match.group(1).split("#")[0].split("|")[0].strip()
            if target:
                yield lineno, target


def check_vault(vault_root):
    """Return a list of human-readable finding strings (empty == clean)."""
    findings = []
    records = vaultlib.scan_artifacts(vault_root)
    names = _resolvable_names(vault_root)

    for record in records:
        path = record["path"]
        rel = f"{record['type_dir']}/{record['rel']}"
        data, error = vaultlib.parse_frontmatter(path)
        if error:
            findings.append(f"frontmatter_error: {rel}: {error}")
            continue
        artifact_type = data.get("type")
        required = REQUIRED_FIELDS.get(artifact_type)
        if required:
            for field in required:
                value = data.get(field)
                if value is None or value == "" or value == []:
                    findings.append(f"frontmatter_missing_field: {rel}: {field}")

        text = path.read_text(encoding="utf-8")
        for lineno, target in _wikilinks_in(text):
            if target not in names:
                findings.append(f"broken_wikilink: {rel}:{lineno}: [[{target}]]")

    index_path = vault_root / "index.md"
    if index_path.is_file():
        index_text = index_path.read_text(encoding="utf-8")
        index_tokens = vaultlib.count_tokens(index_text)
        index_lines = len(index_text.splitlines())
        if index_tokens > HOT_PATH_CAP:
            findings.append(
                f"cap_exceeded: index.md is {index_tokens} tokens (cap {HOT_PATH_CAP})"
            )
        if index_lines > INDEX_LINE_CAP:
            findings.append(
                f"cap_exceeded: index.md is {index_lines} lines (cap {INDEX_LINE_CAP})"
            )
    hot_total = measure(vault_root)
    if hot_total > HOT_PATH_CAP:
        findings.append(
            f"cap_exceeded: hot path is {hot_total} tokens (cap {HOT_PATH_CAP})"
        )

    return findings


def run(args):
    findings = check_vault(vaultlib.find_vault_root())
    if not findings:
        sys.stdout.write("compass validate: clean\n")
        return 0
    sys.stderr.write(f"compass validate: {len(findings)} finding(s)\n")
    for finding in findings:
        sys.stderr.write(f"  - {finding}\n")
    return 1

"""`compass placement <artifact>` and `compass placement --hints` - where an
artifact could sit in the taxonomy of its own type dir.

The report is read-only and computed at invocation from `scan_artifacts`.
It is scoped to the artifact's type dir, at the vault root or inside the
artifact's unit, at any depth; other type dirs, other units and the archive
never contribute a candidate, and neither do domain `index.md` files or the
artifact itself. Sections, in print order:

- `parents:` existing artifacts of the same type, flat or folder, that share
  evidence with the artifact (a candidate parent for a promote-and-move).
- `pairs:` the parent candidates that sit at the artifact's own level, named
  with the directory they share (a domain would form there).
- `domains:` domains whose `Class here:` words match the artifact.
- `redirect:` domains whose `Class elsewhere:` clause matches the artifact,
  with the place the clause files it instead.
- `hint:` the artifact's own `taxonomy_hint`, then the current vault path of
  every artifact stem the hint names.

Every candidate line names its evidence: shared tags, shared title and
summary terms, hint mentions in either direction, and wikilinks in either
direction. Candidates rank by evidence count; the count is an ordering, not
a validated measure. `--hints` runs the same report for every artifact whose
frontmatter carries a non-empty `taxonomy_hint`.

The artifact is named by bare stem or by vault-relative path. An unresolvable
or ambiguous name exits 1 with no report; the command never exits 2.
"""

import re
import sys
from pathlib import Path

import vaultlib

USAGE = "usage: compass placement <artifact> | --hints\n"

_WORD = re.compile(r"[a-z0-9]+")
_HINT_TOKEN = re.compile(r"(?<![\w-])[A-Z]{2,}-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")

# Words that carry no subject, plus the vault's own vocabulary, which appears
# in nearly every document and would match everything.
_STOP = frozenset(
    "the and for with that this from into are was not its has have how what when "
    "where which who why can each any all but per via than then also does only "
    "every them they their there these those over under about after before "
    "between without within while such more most other some one two use used "
    "using new same own spec artifact vault compass document human".split()
)


def _normalize(word):
    """Fold a plural to its singular so `charts` meets `chart`."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "xes", "sses")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _terms(*texts):
    found = set()
    for text in texts:
        for word in _WORD.findall(str(text).lower()):
            word = _normalize(word)
            if len(word) >= 3 and not word.isdigit() and word not in _STOP:
                found.add(word)
    return found


def _as_list(value):
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []


def _stem(record):
    if record["kind"] in ("folder-index", "loop-index"):
        return record["path"].parent.name
    return record["path"].stem


def _wikilink(record):
    """Link form for a candidate: the scan's name, which is a bare stem for a
    root flat artifact and path-qualified otherwise."""
    return f"[[{record['name']}]]"


class _Vault:
    """The scanned vault with per-record facts computed on first use."""

    def __init__(self, vault_root):
        self.root = vault_root
        self.records = vaultlib.scan_artifacts(vault_root)
        self._mapping = None
        self._facts = {}
        for record in self.records:
            data, _ = vaultlib.parse_frontmatter(record["path"])
            record["_data"] = data
            vrel = record["path"].relative_to(vault_root).as_posix()
            record["_vrel"] = vrel
            if record["kind"] in ("folder-index", "loop-index"):
                record["_key"] = vrel.rsplit("/", 1)[0]
            else:
                record["_key"] = vrel[:-3]
            record["_stem"] = _stem(record)
        self.artifacts = [r for r in self.records if not _is_domain(r)]

    def mapping(self):
        if self._mapping is None:
            self._mapping = vaultlib.resolvable_names_map(self.root)
        return self._mapping

    def resolve_token(self, token):
        """Artifacts a hint token names: the exact stem, else every stem
        the token abbreviates (`SPEC-029` for `SPEC-029-questions-...`)."""
        exact = [r for r in self.artifacts if r["_stem"] == token]
        if exact:
            return exact
        return [r for r in self.artifacts if r["_stem"].startswith(token + "-")]

    def facts(self, record):
        cached = self._facts.get(record["_vrel"])
        if cached is not None:
            return cached
        data = record["_data"]
        hint = str(data.get("taxonomy_hint") or "")
        text = vaultlib.strip_inline_code(
            vaultlib.strip_fenced_code(vaultlib.read_vault_text(record["path"]))[0]
        )
        links = set()
        for raw in _WIKILINK.findall(text):
            target = raw.split("|")[0].split("#")[0].rstrip("\\").strip()
            if target:
                links.update(vaultlib.resolve_link(self.mapping(), target))
        named = set()
        for token in _HINT_TOKEN.findall(hint):
            matches = self.resolve_token(token)
            if len(matches) == 1:
                named.add(matches[0]["_vrel"])
        result = {
            "tags": {tag.lower() for tag in _as_list(data.get("tags"))},
            "terms": _terms(data.get("title", ""), data.get("summary", "")),
            "hint": hint,
            "hint_named": named,
            "links": links,
        }
        self._facts[record["_vrel"]] = result
        return result


def _is_domain(record):
    return record["_data"].get("type") == "domain"


def _level_dir(record):
    """Vault-relative directory the artifact sits in; a folder spec sits in
    the directory above its own folder."""
    key = record["_key"]
    return key.rsplit("/", 1)[0] if "/" in key else ""


def _resolve(vault, arg):
    """Return (record, error); exactly one is None."""
    text = arg.replace("\\", "/")
    if Path(text).is_absolute():
        try:
            text = Path(text).relative_to(vault.root).as_posix()
        except ValueError:
            pass
    if text.startswith(".compass/"):
        text = text[len(".compass/"):]
    if "/" in text or text.endswith(".md"):
        key = text[:-3] if text.endswith(".md") else text
        key = key.rstrip("/")
        if key.endswith("/index"):
            key = key[: -len("/index")]
        matches = [r for r in vault.artifacts if r["_key"] == key]
    else:
        matches = [r for r in vault.artifacts if r["_stem"] == text]
    if not matches:
        return None, f"artifact not found: {arg}"
    if len(matches) > 1:
        paths = ", ".join(r["_vrel"] for r in matches)
        return None, f"ambiguous artifact {arg}: matches {paths}"
    return matches[0], None


def _evidence(vault, subject, candidate):
    mine, theirs = vault.facts(subject), vault.facts(candidate)
    items = [f"shared tag {tag}" for tag in sorted(mine["tags"] & theirs["tags"])]
    items += [f"shared term {term}" for term in sorted(mine["terms"] & theirs["terms"])]
    if candidate["_vrel"] in mine["hint_named"]:
        items.append("the subject's hint names it")
    if subject["_vrel"] in theirs["hint_named"]:
        items.append("its hint names the subject")
    if candidate["_vrel"] in mine["links"]:
        items.append("link from the subject")
    if subject["_vrel"] in theirs["links"]:
        items.append("link to the subject")
    return items


def _ranked(rows):
    return sorted(rows, key=lambda row: (-len(row[1]), row[0]["name"]))


def _candidate_rows(vault, subject):
    inside = subject["_key"] + "/"
    rows = []
    for record in vault.artifacts:
        if (record is subject or record["unit"] != subject["unit"]
                or record["type_dir"] != subject["type_dir"]
                or record["_key"].startswith(inside)):
            continue
        items = _evidence(vault, subject, record)
        if items:
            rows.append((record, items))
    return _ranked(rows)


def _line(prefix, items, suffix=""):
    return f"  {prefix} - {len(items)} evidence: {', '.join(items)}{suffix}"


def _section(label, lines):
    return [f"{label}: none"] if not lines else [f"{label}:"] + lines


def _scope_text(record, label):
    text = vaultlib.read_vault_text(record["path"])
    return [line[len(label):].strip() for line in text.splitlines() if line.startswith(label)]


def _domain_link(domain):
    return f"[[{domain['_key']}/index|{domain['path'].parent.name}]]"


def _domain_lines(vault, subject):
    """Return (domain lines, redirect lines) for the subject's type dir."""
    mine = vault.facts(subject)
    subject_terms = mine["terms"] | _terms(" ".join(mine["tags"]))
    domains, redirects = [], []
    for domain in vault.records:
        if (not _is_domain(domain) or domain["unit"] != subject["unit"]
                or domain["type_dir"] != subject["type_dir"]):
            continue
        redirected = False
        for clause in "; ".join(_scope_text(domain, "Class elsewhere:")).split(";"):
            what, arrow, where = clause.partition("->")
            shared = sorted(subject_terms & _terms(what)) if arrow else []
            if shared:
                redirected = True
                redirects.append(
                    f"redirect: {what.strip()} -> {where.strip()}, "
                    f"per {_domain_link(domain)} "
                    f"({', '.join('shared term ' + t for t in shared)})"
                )
        if redirected or domain["path"].parent == subject["path"].parent:
            continue
        shared = sorted(subject_terms & _terms(" ".join(_scope_text(domain, "Class here:"))))
        if shared:
            domains.append((domain, [f"shared term {term}" for term in shared]))
    rows = _ranked(domains)
    return [_line(_domain_link(d), items) for d, items in rows], redirects


def _hint_lines(vault, subject):
    hint = vault.facts(subject)["hint"]
    if not hint:
        return []
    lines = [f"  own: {hint}"]
    for token in dict.fromkeys(_HINT_TOKEN.findall(hint)):
        matches = vault.resolve_token(token)
        if not matches:
            lines.append(f"  {token} -> no such artifact")
        for match in matches:
            lines.append(f"  {token} -> {match['_vrel']}")
    return lines


def report(vault, subject):
    """The full placement report for one resolved artifact, as text."""
    scope = subject["type_dir"] + (f" in unit {subject['unit']}" if subject["unit"] else "")
    rows = _candidate_rows(vault, subject)
    parents = [_line(_wikilink(r), items) for r, items in rows]
    level = _level_dir(subject)
    pairs = [
        _line(_wikilink(r), items, f"; same level, in {level}")
        for r, items in rows if _level_dir(r) == level
    ]
    domain_lines, redirect_lines = _domain_lines(vault, subject)
    out = [
        f"placement: {subject['name']} ({scope})",
        "ranking: candidates rank by evidence count; the count orders them and "
        "is not a validated measure",
    ]
    out += _section("parents", parents)
    out += _section("pairs", pairs)
    out += _section("domains", domain_lines)
    out += redirect_lines or ["redirect: none"]
    out += _section("hint", _hint_lines(vault, subject))
    return "\n".join(out) + "\n"


def run(args):
    flags = [a for a in args if a.startswith("--")]
    positional = [a for a in args if not a.startswith("--")]
    unknown = [f for f in flags if f != "--hints"]
    if unknown:
        sys.stderr.write(f"compass placement: unknown flag {unknown[0]}\n{USAGE}")
        return 1
    hints = "--hints" in flags
    if hints == bool(positional) or len(positional) > 1:
        sys.stderr.write(USAGE)
        return 1

    vault = _Vault(vaultlib.find_vault_root())
    if hints:
        pending = [r for r in vault.artifacts if vault.facts(r)["hint"]]
        sys.stdout.write(
            f"placement --hints: {len(pending)} artifact(s) with a pending hint\n"
        )
        for record in pending:
            sys.stdout.write("\n" + report(vault, record))
        return 0

    subject, error = _resolve(vault, positional[0])
    if error:
        sys.stderr.write(f"compass placement: {error}\n")
        return 1
    sys.stdout.write(report(vault, subject))
    return 0

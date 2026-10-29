// Compass Review: puts the documents Compass asks the human to review in front
// of him, and hands his verdict back.
//
// Protocol (paths relative to the Obsidian vault root, forward slashes):
//   <dir>/<id>.request.json   written by Compass:
//     {"id", "surface"?, "file", "title"?, "return": bool,
//      "files"?: [{"file", "why"}], "project"?, "session"?}
//     files     the documents of a review in walking order, each with a
//               one-line reason; absent for a review of one document
//     project   name of the project the request came from
//     session   id of the Claude Code session that asked
//   obsidian://compass-review?vault=<vault id>&request=<dir>/<id>.request.json
//   <dir>/<id>.verdict.json   written here when a button is clicked:
//     {"id", "file", "verdict": "approved"|"changes", "notes",
//      "comments": [{"file", "note"}], "edited": [path],
//      "files"?: [{"file", "read", "note"?}], "at"}
//     file      the first listed document
//     notes     the note typed for the reviewed document; for several
//               documents, one `<name>: <note>` line per noted document
//     comments  one note per file outside the review that the human
//               annotated from the card (empty notes are left out)
//     edited    every file of the review typed in while it was pending, each
//               listed once; an edit counts when Obsidian's `editor-change`
//               event fires for the file, so writes from other programs are
//               not listed
//     files     for several documents only: every listed document in request
//               order with its read mark and its note, when it has one
// <dir> is the Compass vault's tmp/review folder: `tmp/review` when the
// Obsidian vault is the Compass vault, `.compass/tmp/review` when the
// Obsidian vault is the project around it. Other review surfaces share the
// folder; a request whose `surface` names another one is theirs.
//
// A request raises the Obsidian window above whatever has focus, opens the
// first file, and reveals the review panel, a view in the right sidebar that
// stays in place while the human moves around the vault. Under the heading
// "Reviews waiting on you" the panel holds one card per pending review, newest
// first. A card shows the question (the request title, else the first file's
// name), the project and the first six characters of the session, "File i of
// n" with Previous, Next and Next unread (and the Left and Right arrow keys
// while the card has focus), one row per file with its read mark, title, reason
// and note count, and a note field for the file the walk is on. A file is
// marked read when it opens, whether the card opened it or the human did. While
// a markdown file outside the review is in view, the card also shows an "On this
// file" note field for that file. A summary line counts the files read and the
// notes, and one Approve and one "Needs changes" end the review. "Needs
// changes" is enabled once there is something to send: a note on a listed or
// outside file, or an edit. A newer request that lists a file of an older one
// replaces it.
//
// Each listed document carries a one-line bar naming the review and the file's
// place in it, with a button that opens the panel. A click on a card saves the
// editors of the listed files and writes the verdict. Once no review is left,
// Obsidian steps aside (minimize, or hide on macOS) so focus falls back to the
// window that had it before: when a review that arrived by link found this
// window without focus, or, for a review the plugin found at start-up, when
// its request says `return`. Everything the human types lives on
// the review's entry, so redrawing the panel keeps it. A periodic recheck drops
// a review whose request file is gone or whose verdict already exists.
//
// The Compass view panel, a right-sidebar view (view type
// `compass-view-panel`, opened by the "Open Compass view panel" command or the
// ribbon icon), follows the markdown file in view and draws the view that the
// file's `type:` property picks. A type with no view gets one plain line. The
// view for `type: plan` is the plan board, drawn from the plan's task lines
// and read from the vault only:
//   - the lines `- [ ] TASK-n: ... - depends_on: ...` outside code fences and
//     outside `## Wave n elaborated` sections, each with its wave (the nearest
//     `Wave n` or `Phase n` heading; none under `## Later`), its status (done
//     when checked; later under `## Later`; ready when every task it depends
//     on in the plan is done; else waiting) and the TASK ids of its
//     `depends_on` outside parentheses
//   - a dependency graph with one node per task, laid out in a lane per wave
//     and colored by status, and a table with one row per task (id, task,
//     wave, status, depends on); a click on a task's id or on its node opens
//     the plan at the task's line
//   - while a review that lists the plan is pending, the rows of the plan's
//     `| Choice | ... |` table each take Agree or Change with a note. Every
//     changed choice joins the review's note, after the typed text, as one
//     `<choice>: <note>` line in table order (for a review of several files,
//     in the note of the plan's file). Agree adds no line. The answers live on
//     the review, so redrawing the panel keeps them.
// The view for `type: spec` shows the spec's Problem and Desired Outcome as the
// human wrote them and one card per decision:
//   - the decisions are the `- **D-NN:** text` bullets that `compass decisions`
//     reports, read by the same rules (plain or in a callout, continuation
//     lines, a trailing block id left out, `[deferred]` / `[informational]`
//     tags and discretion subheadings marking a decision as not tracked, code
//     fences ignored); a spec whose decisions cannot be read says so
//   - while a review that lists the spec is pending, each decision card takes
//     Agree or Change with a note. A Change with a blank note is refused, with
//     a hint on the card. Every changed decision joins the review's note, after
//     the typed text, as one `D-NN: <note>` line in spec order. Agree adds no
//     line. The answers live on the review, so redrawing the panel keeps them.
// The view for `type: research` reads the rows of every table whose header
// names a Finding column (number, finding, confidence, grade, evidence):
//   - one bar per section, in document order, splitting its findings by
//     confidence (a mixed rating counts once, as its leading level; a finding
//     with no rating counts as unrated)
//   - one filter button per confidence level; a finding with no rating stays
//     under every filter, and the bars keep counting the whole document
//   - one row per shown finding with its evidence; a click on the row opens the
//     research document at the finding's line
// The views only read the vault.

const { Plugin, ItemView, Notice, MarkdownView } = require("obsidian");

const REVIEW_DIRS = ["tmp/review", ".compass/tmp/review"];
const SURFACE = "obsidian";
const RECHECK_MS = 5000;
const PANEL_TYPE = "compass-review-panel";
const VIEW_TYPE = "compass-view-panel";

function electronRemote() {
  const electron = require("electron");
  return electron.remote || require("@electron/remote");
}

function verdictPathFor(requestPath) {
  return requestPath.replace(/\.request\.json$/, ".verdict.json");
}

function baseName(path) {
  return path.split("/").pop().replace(/\.md$/, "");
}

class ReviewPanelView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType() {
    return PANEL_TYPE;
  }

  getDisplayText() {
    return "Compass Review";
  }

  getIcon() {
    return "check-circle";
  }

  async onOpen() {
    this.contentEl.addClass("compass-review-panel");
    this.plugin.drawPanel(this);
  }
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function setClass(el, cls, on) {
  el.removeClass(cls);
  if (on) el.addClass(cls);
}

// The documents a request lists, in walking order; a request without a `files`
// list reviews its one `file`.
function filesOf(request) {
  if (Array.isArray(request.files) && request.files.length > 0) {
    return request.files.map((f) => ({ file: f.file, why: typeof f.why === "string" ? f.why : "" }));
  }
  return [{ file: request.file, why: "" }];
}

class ViewPanelView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
    this.drawSeq = 0;
    // research path -> {high, medium, low}: the confidence filters switched on
    this.confOn = new Map();
  }

  getViewType() {
    return VIEW_TYPE;
  }

  getDisplayText() {
    return "Compass View";
  }

  getIcon() {
    return "layout-dashboard";
  }

  async onOpen() {
    this.contentEl.addClass("compass-view-panel");
    await this.plugin.drawViewPanel(this);
  }
}

// ---- reading a document: properties, fences, tables, plan tasks ----

const META_KEYS = "complexity|files|depends_on|decisions|lessons|commit-upfront";

function linesOf(text) {
  return String(text).replace(/^\uFEFF/, "").split(/\r?\n/);
}

// The properties block at the very start of a document: its simple
// `key: value` lines, and the index of the first line after it.
function propertiesOf(lines) {
  if (lines.length === 0 || lines[0].trimEnd() !== "---") return { props: {}, end: 0 };
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trimEnd() !== "---") continue;
    const props = {};
    for (const line of lines.slice(1, i)) {
      const m = /^([A-Za-z_][\w-]*):[ \t]*(.*?)[ \t]*$/.exec(line);
      if (!m || m[1] in props) continue;
      props[m[1]] = /^(".*"|'.*')$/.test(m[2]) ? m[2].slice(1, -1) : m[2];
    }
    return { props, end: i + 1 };
  }
  return { props: {}, end: 0 };
}

function typeOf(text) {
  const { props } = propertiesOf(linesOf(text));
  return props.type || null;
}

// The view a document gets: "plan", "spec" or "research" for the document of
// that `type:`, null for any other type or none.
function viewFor(text) {
  const type = typeOf(text);
  return type === "plan" || type === "spec" || type === "research" ? type : null;
}

// Feed it the lines in order: true for a fence line and for a line inside a
// fence. A fence closes with the same character, at least as long.
function fenceTracker() {
  let open = null;
  return (line) => {
    const m = /^\s*(`{3,}|~{3,})/.exec(line);
    if (open) {
      if (m && m[1][0] === open.ch && m[1].length >= open.len && /^\s*[`~]+\s*$/.test(line)) open = null;
      return true;
    }
    if (m) {
      open = { ch: m[1][0], len: m[1].length };
      return true;
    }
    return false;
  };
}

// Table cells; a pipe inside a code span or after a backslash does not split.
function splitRow(line) {
  const body = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  const cells = [];
  let cur = "";
  for (let i = 0; i < body.length; i++) {
    const ch = body[i];
    if (ch === "`") {
      // A backtick run opens a code span only when a run of the same length
      // closes it later in the row; otherwise the backticks are plain text.
      let end = i;
      while (body[end] === "`") end++;
      const run = body.slice(i, end);
      let close = body.indexOf(run, end);
      while (close >= 0 && (body[close - 1] === "`" || body[close + run.length] === "`")) {
        close = body.indexOf(run, close + 1);
      }
      const stop = close >= 0 ? close + run.length : end;
      cur += body.slice(i, stop);
      i = stop - 1;
    } else if (ch === "|" && body[i - 1] !== "\\") {
      cells.push(cur.trim());
      cur = "";
    } else cur += ch;
  }
  cells.push(cur.trim());
  return cells;
}

function shortTitle(desc) {
  const t = desc.split(/[:;]/)[0].trim();
  return t.length > 44 ? t.slice(0, 42).trimEnd() + "..." : t;
}

// The TASK ids a `depends_on:` value names: those outside parentheses, and not
// another plan's (`PLAN-021 TASK-163`). The value ends at the next metadata key.
function dependsOf(meta) {
  const at = /(?:^|,\s*)depends_on:\s*/.exec(meta);
  if (!at) return [];
  const rest = meta.slice(at.index + at[0].length);
  const end = new RegExp(`,\\s*(?:${META_KEYS}):`, "y");
  let depth = 0;
  let outside = "";
  for (let k = 0; k < rest.length; k++) {
    const ch = rest[k];
    if (ch === "(") depth++;
    else if (ch === ")") depth = Math.max(0, depth - 1);
    else if (depth === 0) {
      end.lastIndex = k;
      if (end.test(rest)) break;
      outside += ch;
    }
  }
  const ids = [];
  for (const found of outside.match(/(?:PLAN-\d+(?:'s)?\s+)?TASK-\d+/g) || []) {
    if (found.startsWith("TASK-") && !ids.includes(found)) ids.push(found);
  }
  return ids;
}

// Every task line of a plan, in file order: {id, title, desc, wave, lane,
// done, later, status, dependsOn, line (1-based)}. Task-shaped lines inside a code fence or
// a `## Wave n elaborated` section are quotations and are left out.
function parsePlanTasks(text) {
  const lines = linesOf(text);
  const inFence = fenceTracker();
  const tasks = [];
  let h2 = "";
  let h3 = "";
  let skipping = false;
  for (let i = propertiesOf(lines).end; i < lines.length; i++) {
    const line = lines[i];
    if (inFence(line)) continue;
    const head = /^(#{1,6})\s+(.+?)\s*$/.exec(line);
    if (head) {
      if (head[1].length <= 2) {
        h2 = head[1].length === 2 ? head[2] : "";
        h3 = "";
        skipping = /^Wave\s+\d+\s+elaborated/i.test(h2);
      } else if (head[1].length === 3) h3 = head[2];
      continue;
    }
    if (skipping) continue;
    const m = /^- \[( |x|X)\] (TASK-\d+):\s*(.*)$/.exec(line);
    if (!m) continue;
    const split = new RegExp(`\\s-\\s(?=(?:${META_KEYS}):)`).exec(m[3]);
    const desc = (split ? m[3].slice(0, split.index) : m[3]).trim();
    const meta = split ? m[3].slice(split.index + 3) : "";
    const later = /^Later/i.test(h2);
    const waveMatch = later ? null : /^(?:Wave|Phase)\s+(\d+)/i.exec(h3) || /^(?:Wave|Phase)\s+(\d+)/i.exec(h2);
    const wave = waveMatch ? Number(waveMatch[1]) : null;
    tasks.push({
      id: m[2],
      title: shortTitle(desc) || m[2],
      desc,
      wave,
      lane: wave !== null ? `Wave ${wave}` : later ? "Later" : (h3 || h2 || "Tasks").replace(/\s*\((?:detailed|intent only)\)/, ""),
      done: m[1] !== " ",
      later,
      dependsOn: dependsOf(meta),
      line: i + 1,
    });
  }
  const byId = new Map(tasks.map((t) => [t.id, t]));
  for (const t of tasks) {
    const open = t.dependsOn.some((d) => byId.has(d) && !byId.get(d).done);
    t.status = t.done ? "done" : t.later ? "later" : open ? "waiting" : "ready";
  }
  return tasks;
}

// The rows of the first table whose header starts with "Choice", outside code
// fences: {choice, answer, line (1-based)}.
function parsePlanChoices(text) {
  const lines = linesOf(text);
  const inFence = fenceTracker();
  const out = [];
  let header = false;
  let rows = false;
  for (let i = propertiesOf(lines).end; i < lines.length; i++) {
    const line = lines[i];
    if (inFence(line)) {
      if (rows) break;
      header = false;
      continue;
    }
    const isRow = line.trimStart().startsWith("|");
    if (rows) {
      if (!isRow) break;
      const cells = splitRow(line);
      if (cells[0]) out.push({ choice: cells[0], answer: cells.slice(1).join(" | "), line: i + 1 });
    } else if (header) {
      header = false;
      rows = isRow && splitRow(line).every((c) => /^:?-+:?$/.test(c));
    } else if (isRow && /^choice$/i.test(splitRow(line)[0])) {
      header = true;
    }
  }
  return out;
}

const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);

// One `<choice>: <note>` line for each choice answered Change, in table order.
function choiceNoteLines(choices, answers) {
  const lines = [];
  const seen = new Set();
  for (const { choice } of choices) {
    if (seen.has(choice)) continue;
    seen.add(choice);
    if (!hasOwn(answers, choice) || answers[choice].state !== "change") continue;
    const note = String(answers[choice].note || "").trim().replace(/\s+/g, " ");
    lines.push(`${choice}: ${note || "(no note)"}`);
  }
  return lines;
}

// The review's note with the choice lines after it, each on its own line.
function joinChoiceNote(note, lines) {
  if (lines.length === 0) return note;
  const typed = note.trimEnd();
  return typed.trim() ? `${typed}\n${lines.join("\n")}` : lines.join("\n");
}

// ---- reading a spec: sections and decisions ----

// The decisions of a document exactly as `compass decisions` reads them: a
// `- **D-NN:** text` bullet (continuation lines indented under it) inside a
// two- or three-hash Decision/Decisions section, plain or inside a callout.
const DECISIONS_HEADING = /^(#{2,3})\s*Decisions?\b/i;
const ANY_HEADING = /^(#{1,6})\s/;
const BULLET_GRAMMARS = [
  /^\s*-\s+\*\*D-([A-Za-z0-9][A-Za-z0-9_-]*)(?:\s*\[([^\]]+)\])?[^:*]*:\*\*\s*(.*)$/,
  /^\s*-\s+\*\*D-([A-Za-z0-9][A-Za-z0-9_-]*)(?:\s*\[([^\]]+)\])?[^*]*[\u2014\u2013][^*]*\*\*\s*(.*)$/,
  /^\s*-\s+\*\*D-([A-Za-z0-9][A-Za-z0-9_-]*)(?:\s*\[([^\]]+)\])?[^:*]*:[^:*]*\*\*\s*(.*)$/,
];
const BULLET_SHAPED = /^\s*-\s+\*\*D-/;
const D_TOKEN = /\bD-[A-Za-z0-9]/;
const BOLD_ID_BULLET = /^\s*-\s+\*\*[A-Z]+[0-9]*-[A-Za-z0-9]/m;
const QUALIFIED_STEM_REF = /\b(?:SPEC|ADR|PLAN|RESEARCH)-[A-Za-z0-9_-]*[ /]D-[A-Za-z0-9_-]*/g;
const WIKILINK = /\[\[[^\]]*\]\]/g;
const DECISION_SUBHEADING = /^#{3,6}\s+(.+?)\s*$/;
const QUOTE_CHARS = /[‘’‚‛“”„‟'"`]/g;
const QUOTE_PREFIX = /^\s*>(?:\s?>)*\s?/;
const BLOCK_ID_AT_END = /(?:^|\s)\^([A-Za-z0-9-]+)\s*$/;
const INLINE_CODE_SPAN = /`[^`\n]+`/g;
const NON_TRACKABLE_TAGS = ["informational", "deferred"];

// Whether each line belongs to a fenced code block (delimiters included), and
// whether a fence never closes.
function fenceMask(lines) {
  const mask = new Array(lines.length).fill(false);
  let marker = null;
  lines.forEach((line, i) => {
    const t = line.trim();
    if (marker === null) {
      const open = /^(`{3,}|~{3,})/.exec(t);
      if (open) {
        marker = open[1];
        mask[i] = true;
      }
      return;
    }
    mask[i] = true;
    const close = /^(`{3,}|~{3,})\s*$/.exec(t);
    if (close && close[1][0] === marker[0] && close[1].length >= marker.length) marker = null;
  });
  return { mask, unterminated: marker !== null };
}

function dropBlockId(text) {
  const m = BLOCK_ID_AT_END.exec(text);
  return m ? text.slice(0, m.index).trimEnd() : text;
}

// Each decisions section: {start (1-based line of its first body line), body}.
function decisionSections(lines) {
  const sections = [];
  let i = 0;
  while (i < lines.length) {
    const head = DECISIONS_HEADING.exec(lines[i]);
    if (!head) {
      i++;
      continue;
    }
    const level = head[1].length;
    const bodyStart = i + 1;
    let j = bodyStart;
    while (j < lines.length) {
      const h = ANY_HEADING.exec(lines[j]);
      if (h && h[1].length <= level) break;
      j++;
    }
    sections.push({ start: bodyStart + 1, body: lines.slice(bodyStart, j) });
    i = j;
  }
  return sections;
}

// The decisions of one section body and the count of decision-shaped bullets
// no grammar could read.
function parseDecisionLines(body, startLine) {
  const decisions = [];
  let misses = 0;
  let discretion = false;
  let current = null;
  const flush = () => {
    if (current) {
      current.text = dropBlockId(current.text.trim());
      decisions.push(current);
      current = null;
    }
  };
  body.forEach((raw, offset) => {
    const line = raw.replace(QUOTE_PREFIX, "");
    const trimmed = line.trim();
    const sub = DECISION_SUBHEADING.exec(trimmed);
    if (sub) {
      flush();
      discretion = sub[1].replace(QUOTE_CHARS, "").trim().toLowerCase().endsWith("discretion");
      return;
    }
    let m = null;
    for (const grammar of BULLET_GRAMMARS) {
      m = grammar.exec(line);
      if (m) break;
    }
    if (m) {
      flush();
      const tags = m[2] ? m[2].split(",").map((t) => t.trim().toLowerCase()).filter(Boolean) : [];
      current = {
        id: `D-${m[1]}`,
        text: m[3] || "",
        tags,
        trackable: !discretion && !tags.some((t) => NON_TRACKABLE_TAGS.includes(t)),
        line: startLine + offset,
      };
      return;
    }
    if (BULLET_SHAPED.test(line)) {
      flush();
      misses++;
      return;
    }
    if (current && trimmed && !trimmed.startsWith("-") && (line[0] === " " || line[0] === "\t")) {
      current.text += ` ${trimmed}`;
      return;
    }
    if (!trimmed) flush();
  });
  flush();
  return { decisions, misses };
}

// {decisions: [{id, text, trackable, tags, line (1-based)}], outcome}, where
// outcome is "parsed", "none-present" or "could-not-parse".
function extractDecisions(text) {
  const all = linesOf(text);
  const { mask, unterminated } = fenceMask(all);
  const lines = all.map((line, i) => (mask[i] ? "" : line));
  const sections = decisionSections(lines);
  const withoutCode = (s) => s.replace(INLINE_CODE_SPAN, "");
  if (sections.length > 0) {
    const decisions = [];
    let misses = 0;
    const bodies = [];
    for (const { start, body } of sections) {
      const found = parseDecisionLines(body, start);
      decisions.push(...found.decisions);
      misses += found.misses;
      bodies.push(body.map((l) => l.replace(QUOTE_PREFIX, "")).join("\n"));
    }
    if (misses > 0) return { decisions, outcome: "could-not-parse" };
    if (decisions.length > 0) return { decisions, outcome: "parsed" };
    const evidence = withoutCode(bodies.join("\n"));
    const foreign = evidence.replace(WIKILINK, " ").replace(QUALIFIED_STEM_REF, " ");
    const unread = D_TOKEN.test(foreign) || BOLD_ID_BULLET.test(evidence) || unterminated;
    return { decisions: [], outcome: unread ? "could-not-parse" : "none-present" };
  }
  const evidence = withoutCode(lines.join("\n"));
  return { decisions: [], outcome: unterminated || D_TOKEN.test(evidence) ? "could-not-parse" : "none-present" };
}

// The trimmed body of the `## <name>` section (to the next heading of level
// one or two, fences skipped) and the 1-based line of its heading; "" and 0
// when the document has no such section.
function sectionOfSpec(lines, from, name) {
  const inFence = fenceTracker();
  const want = new RegExp(`^##\\s+${name}\\s*:?\\s*$`, "i");
  let start = -1;
  for (let i = from; i < lines.length; i++) {
    if (inFence(lines[i])) continue;
    const h = /^(#{1,2})\s/.exec(lines[i]);
    if (!h) continue;
    if (start >= 0) return { text: lines.slice(start + 1, i).join("\n").trim(), line: start + 1 };
    if (h[1].length === 2 && want.test(lines[i])) start = i;
  }
  return start >= 0 ? { text: lines.slice(start + 1).join("\n").trim(), line: start + 1 } : { text: "", line: 0 };
}

// {problem, desiredOutcome, problemLine, desiredOutcomeLine, decisions,
// decisionState}: the Problem and Desired Outcome as written, and the
// decisions with the outcome of reading them.
function parseSpec(text) {
  const lines = linesOf(text);
  const from = propertiesOf(lines).end;
  const problem = sectionOfSpec(lines, from, "Problem");
  const outcome = sectionOfSpec(lines, from, "Desired Outcome");
  const { decisions, outcome: decisionState } = extractDecisions(text);
  return {
    problem: problem.text,
    desiredOutcome: outcome.text,
    problemLine: problem.line,
    desiredOutcomeLine: outcome.line,
    decisions,
    decisionState,
  };
}

// One `D-NN: <note>` line for each decision answered Change with a note, in
// spec order, once per id; then the answers whose decision has left the spec.
function decisionNoteLines(decisions, answers) {
  const lines = [];
  const seen = new Set();
  for (const id of [...decisions.map((d) => d.id), ...Object.keys(answers)]) {
    if (seen.has(id)) continue;
    seen.add(id);
    if (!hasOwn(answers, id) || answers[id].state !== "change") continue;
    const note = String(answers[id].note || "").trim().replace(/\s+/g, " ");
    if (note) lines.push(`${id}: ${note}`);
  }
  return lines;
}

// ---- reading research: findings by section and confidence ----

const CONFIDENCES = ["high", "medium", "low"];

// The rows of every table whose header names a Finding column, outside code
// fences and with a numeric first cell: {n, text, conf ("high", "medium",
// "low" or ""), confNote (the confidence cell as written), grade, evidence,
// section (the nearest heading above), line (1-based)}.
function parseResearchFindings(text) {
  const lines = linesOf(text);
  const inFence = fenceTracker();
  const isSeparator = (line) => line.trimStart().startsWith("|") && splitRow(line).every((c) => /^:?-+:?$/.test(c));
  const findings = [];
  let section = "";
  let cols = null;
  let inTable = false;
  for (let i = propertiesOf(lines).end; i < lines.length; i++) {
    const line = lines[i];
    if (inFence(line)) {
      inTable = false;
      cols = null;
      continue;
    }
    const head = /^#{1,6}\s+(.+?)\s*$/.exec(line);
    if (head) {
      section = head[1];
      inTable = false;
      cols = null;
      continue;
    }
    if (!line.trimStart().startsWith("|")) {
      inTable = false;
      cols = null;
      continue;
    }
    if (!inTable) {
      if (i + 1 < lines.length && isSeparator(lines[i + 1]) && !isSeparator(line)) {
        const names = splitRow(line).map((c) => c.toLowerCase());
        const at = (re) => names.findIndex((c) => re.test(c));
        const finding = at(/^finding\b/);
        cols = finding < 0 ? null : { n: 0, finding, conf: at(/^conf/), grade: at(/^grade/), evidence: at(/^evidence/) };
        inTable = true;
      }
      continue;
    }
    if (!cols || isSeparator(line)) continue;
    const cells = splitRow(line);
    const cell = (k) => (k >= 0 && k < cells.length ? cells[k] : "");
    if (!/^\d+$/.test(cell(cols.n))) continue;
    const confNote = cell(cols.conf);
    const lead = /^(high|medium|low)\b/i.exec(confNote);
    findings.push({
      n: Number(cell(cols.n)),
      text: cell(cols.finding),
      conf: lead ? lead[1].toLowerCase() : "",
      confNote,
      grade: cell(cols.grade),
      evidence: cell(cols.evidence),
      section: section || "Findings",
      line: i + 1,
    });
  }
  return findings;
}

// [{name, high, medium, low, other, total}] by section, in order of first
// appearance; a finding with no rating counts under other.
function countFindingsBySection(findings) {
  const out = [];
  const byName = new Map();
  for (const f of findings) {
    let s = byName.get(f.section);
    if (!s) {
      s = { name: f.section, high: 0, medium: 0, low: 0, other: 0, total: 0 };
      byName.set(f.section, s);
      out.push(s);
    }
    s[CONFIDENCES.includes(f.conf) ? f.conf : "other"]++;
    s.total++;
  }
  return out;
}

// The findings whose confidence is in `confs`; one with no rating stays.
function filterFindings(findings, confs) {
  return findings.filter((f) => f.conf === "" || confs.includes(f.conf));
}

function textHash(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return `${text.length}:${h >>> 0}`;
}

// ---- the plan graph: a lane per wave, columns by dependency depth ----

const NODE_W = 172;
const NODE_H = 46;
const GAP_X = 46;
const GAP_Y = 12;
const LANE_HEAD = 26;
const LANE_GAP = 16;
const PAD = 8;
const WRAP_ROWS = 3;

// Positions for every task and the path of every dependency edge. Inside a
// lane a task sits one column right of its deepest parent in that lane, rows
// ordered by the parents' rows; a lane without dependencies wraps into short
// columns.
function layoutGraph(tasks) {
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const depth = new Map();
  const depthOf = (t, seen = new Set()) => {
    if (depth.has(t.id)) return depth.get(t.id);
    if (seen.has(t.id)) return 0;
    seen.add(t.id);
    let v = 0;
    for (const d of t.dependsOn) {
      const p = byId.get(d);
      if (p && p.lane === t.lane) v = Math.max(v, depthOf(p, seen) + 1);
    }
    depth.set(t.id, v);
    return v;
  };
  tasks.forEach((t) => depthOf(t));
  const laneNames = [];
  for (const t of tasks) if (!laneNames.includes(t.lane)) laneNames.push(t.lane);
  const pos = new Map();
  const lanes = [];
  let y = PAD;
  let width = 0;
  for (const name of laneNames) {
    const members = tasks.filter((t) => t.lane === name);
    const hasEdges = members.some((t) => t.dependsOn.some((d) => byId.has(d) && byId.get(d).lane === name));
    const cols = [];
    if (hasEdges) {
      for (const t of members) (cols[depth.get(t.id)] = cols[depth.get(t.id)] || []).push(t);
    } else {
      members.forEach((t, i) => {
        const c = Math.floor(i / WRAP_ROWS);
        (cols[c] = cols[c] || []).push(t);
      });
    }
    let rows = 0;
    cols.forEach((col, c) => {
      if (!col) return;
      const rowOf = (t) => {
        const ps = t.dependsOn.map((d) => pos.get(d)).filter((p) => p && p.lane === name);
        return ps.length ? ps.reduce((s, p) => s + p.row, 0) / ps.length : 0;
      };
      col.sort((a, b) => rowOf(a) - rowOf(b) || members.indexOf(a) - members.indexOf(b));
      col.forEach((t, r) => {
        pos.set(t.id, { lane: name, row: r, x: PAD + c * (NODE_W + GAP_X), y: y + LANE_HEAD + r * (NODE_H + GAP_Y) });
      });
      rows = Math.max(rows, col.length);
    });
    const h = LANE_HEAD + rows * (NODE_H + GAP_Y);
    lanes.push({ name, y, h });
    y += h + LANE_GAP;
    width = Math.max(width, PAD * 2 + cols.length * (NODE_W + GAP_X) - GAP_X);
  }
  const edges = [];
  for (const t of tasks) {
    for (const d of t.dependsOn) {
      const a = pos.get(d);
      const b = pos.get(t.id);
      if (!a || !b) continue;
      const x1 = a.x + NODE_W;
      const y1 = a.y + NODE_H / 2;
      const x2 = b.x;
      const y2 = b.y + NODE_H / 2;
      edges.push({ from: d, to: t.id, path: `M ${x1} ${y1} C ${x1 + 22} ${y1}, ${x2 - 22} ${y2}, ${x2} ${y2}` });
    }
  }
  return { pos, lanes, edges, width: Math.max(width, 320), height: y };
}

const STATUS_LABEL = {
  done: "done",
  ready: "ready to build",
  waiting: "waiting on another task",
  later: "intent only",
};

// Text with `code`, **bold** and [[link]] marks drawn as elements.
function inline(el, text) {
  for (const p of text.split(/(`[^`]+`|\*\*[^*]+\*\*|\[\[[^\]]+\]\])/)) {
    if (!p) continue;
    if (p.startsWith("`")) el.createEl("code", { text: p.slice(1, -1) });
    else if (p.startsWith("**")) el.createEl("strong", { text: p.slice(2, -2) });
    else if (p.startsWith("[[")) el.createSpan({ cls: "compass-board-link", text: p.slice(2, -2).split("|").pop() });
    else el.appendText(p);
  }
}

// Markdown text drawn as elements: paragraphs, bullet lists, sub-headings and
// fenced code.
function prose(el, text) {
  const lines = String(text).split(/\r?\n/);
  let marker = null;
  let para = [];
  let list = null;
  let item = null;
  let code = null;
  const endPara = () => {
    if (para.length) inline(el.createDiv({ cls: "compass-prose-p" }), para.join(" "));
    para = [];
  };
  const endCode = () => {
    el.createEl("pre", { cls: "compass-prose-code" }).createEl("code", { text: code.join("\n") });
    code = null;
  };
  for (const line of lines) {
    const fence = /^(`{3,}|~{3,})(.*)$/.exec(line.trim());
    // A backtick fence's info string holds no backtick, so a line like
    // "```x``` text" is a paragraph with an inline span.
    if (marker === null && fence && !(fence[1][0] === "`" && fence[2].includes("`"))) {
      endPara();
      list = null;
      marker = fence[1];
      code = [];
      continue;
    }
    if (marker !== null) {
      if (fence && fence[2].trim() === "" && fence[1][0] === marker[0] && fence[1].length >= marker.length) {
        marker = null;
        endCode();
      } else code.push(line);
      continue;
    }
    const trimmed = line.trim();
    const heading = /^#{3,6}\s+(.+)$/.exec(trimmed);
    const bullet = /^[-*]\s+(.+)$/.exec(trimmed);
    if (!trimmed) {
      endPara();
      list = null;
    } else if (heading) {
      endPara();
      list = null;
      el.createDiv({ cls: "compass-prose-heading", text: heading[1] });
    } else if (bullet) {
      endPara();
      if (!list) list = el.createEl("ul", { cls: "compass-prose-list" });
      item = list.createEl("li");
      inline(item, bullet[1]);
    } else if (list && /^\s/.test(line)) {
      inline(item, ` ${trimmed}`);
    } else {
      list = null;
      para.push(trimmed);
    }
  }
  if (code) endCode();
  endPara();
}

class CompassReview extends Plugin {
  async onload() {
    // request id -> {request, path, files: [{file, why}], states: Map(file ->
    // {read, note}), index, comments: Map(file outside the review -> note),
    // edited: Set(path), choiceAnswers: Map(file -> {choice -> {state, note}}),
    // decisionAnswers: Map(file -> {D-NN -> {state, note}})}
    // in arrival order; the panel lists it newest first.
    this.pending = new Map();
    this.registerView(PANEL_TYPE, (leaf) => new ReviewPanelView(leaf, this));
    this.registerView(VIEW_TYPE, (leaf) => new ViewPanelView(leaf, this));
    this.addCommand({
      id: "open-view-panel",
      name: "Open Compass view panel",
      callback: () => this.openViewPanel().catch((e) => this.fail("open view panel", e)),
    });
    this.addRibbonIcon("layout-dashboard", "Open Compass view panel", () =>
      this.openViewPanel().catch((e) => this.fail("open view panel", e))
    );
    this.registerObsidianProtocolHandler("compass-review", (params) =>
      this.onRequest(params.request).catch((e) => this.fail("request", e))
    );
    this.registerEvent(this.app.workspace.on("file-open", (file) => this.onFileOpen(file)));
    this.registerEvent(this.app.workspace.on("layout-change", () => this.refresh()));
    this.registerEvent(this.app.vault.on("rename", (file, oldPath) => this.onRename(file, oldPath)));
    this.registerEvent(this.app.vault.on("modify", (file) => this.onModify(file)));
    this.registerEvent(this.app.workspace.on("editor-change", (editor, info) => this.onEditorChange(info)));
    this.registerInterval(
      window.setInterval(() => this.recheck().catch((e) => console.error("[compass-review] recheck failed", e)), RECHECK_MS)
    );
    this.app.workspace.onLayoutReady(() => this.scanPending().catch((e) => this.fail("scan", e)));
  }

  onunload() {
    document.querySelectorAll(".compass-review-bar").forEach((el) => el.remove());
  }

  fail(where, err) {
    console.error(`[compass-review] ${where} failed`, err);
    new Notice(`Compass Review: ${where} failed - ${(err && err.message) || err}`);
  }

  async readRequest(path) {
    const request = JSON.parse(await this.app.vault.adapter.read(path));
    const listed = request && request.files;
    const badFiles = listed !== undefined && !(Array.isArray(listed) && listed.every((f) => f && typeof f.file === "string"));
    if (!request || typeof request.id !== "string" || typeof request.file !== "string" || badFiles) {
      throw new Error(`malformed request ${path}`);
    }
    return request;
  }

  // Requests written while Obsidian was closed, or before a reload, get their
  // card and bar without raising the window.
  async scanPending() {
    const adapter = this.app.vault.adapter;
    for (const dir of REVIEW_DIRS) {
      if (!(await adapter.exists(dir))) continue;
      const { files } = await adapter.list(dir);
      for (const path of files) {
        if (!path.endsWith(".request.json")) continue;
        if (await adapter.exists(verdictPathFor(path))) continue;
        try {
          const request = await this.readRequest(path);
          if (request.surface && request.surface !== SURFACE) continue;
          this.track(request, path);
        } catch (e) {
          console.error("[compass-review] skipped", path, e);
        }
      }
    }
    this.refresh();
  }

  // A newer request that lists any file of an older one replaces the older one,
  // whose request file `compass review` has already removed.
  track(request, path) {
    const files = filesOf(request);
    const replaced = [];
    for (const [id, entry] of this.pending) {
      if (id === request.id) continue;
      const held = new Set(entry.files.map((f) => f.file));
      const shared = files.some((f) => held.has(f.file));
      if (shared) {
        replaced.push(entry);
        this.pending.delete(id);
      }
    }
    const known = this.pending.get(request.id);
    if (known) {
      known.request = request;
      known.path = path;
      known.files = files;
      for (const f of files) if (!known.states.has(f.file)) known.states.set(f.file, { read: false, note: "" });
      known.index = Math.min(known.index, files.length - 1);
      return;
    }
    // What the human wrote or changed on files both reviews list carries over.
    const created = {
      request,
      path,
      files,
      states: new Map(files.map((f) => [f.file, { read: false, note: "" }])),
      index: 0,
      comments: new Map(),
      edited: new Set(),
      choiceAnswers: new Map(),
      decisionAnswers: new Map(),
    };
    for (const old of replaced) {
      if (old.arrivedUnfocused) created.arrivedUnfocused = true;
      for (const f of files) if (old.states.has(f.file)) created.states.set(f.file, old.states.get(f.file));
      for (const f of files) if (old.choiceAnswers.has(f.file)) created.choiceAnswers.set(f.file, old.choiceAnswers.get(f.file));
      for (const f of files) if (old.decisionAnswers.has(f.file)) created.decisionAnswers.set(f.file, old.decisionAnswers.get(f.file));
      for (const [file, note] of old.comments) created.comments.set(file, note);
      for (const file of old.edited) created.edited.add(file);
    }
    this.pending.set(request.id, created);
  }

  async onRequest(path) {
    if (!path) throw new Error("the compass-review link names no request");
    const request = await this.readRequest(path);
    if (!this.app.vault.getAbstractFileByPath(request.file)) throw new Error(`file not in this vault: ${request.file}`);
    // Read before anything raises the window.
    const hadFocus = this.windowHasFocus();
    this.track(request, path);
    const entry = this.pending.get(request.id);
    if (hadFocus !== null) entry.arrivedUnfocused = entry.arrivedUnfocused === true || !hadFocus;
    await this.openPanel();
    await this.visit(entry, 0, true);
    this.raise();
    this.refresh();
  }

  // Brings a file into view: in the pane that already shows it, else in the
  // current pane. The editor takes keyboard focus unless `focus` is false.
  // `state` is the open state the pane takes, such as {eState: {line}}.
  async showFile(path, focus = true, state = undefined) {
    const file = this.app.vault.getAbstractFileByPath(path);
    if (!file) throw new Error(`file not in this vault: ${path}`);
    const open = this.app.workspace
      .getLeavesOfType("markdown")
      .find((leaf) => leaf.view.file && leaf.view.file.path === path);
    const leaf = open || this.app.workspace.getLeaf(false);
    await leaf.openFile(file, state);
    this.app.workspace.setActiveLeaf(leaf, { focus });
  }

  // Opens file `i` of a review and moves its walk there, marking it read.
  async visit(entry, i, focus = false) {
    const target = entry && entry.files[i];
    if (!target) return;
    this.visiting = entry;
    try {
      await this.showFile(target.file, focus);
    } finally {
      if (this.visiting === entry) this.visiting = null;
    }
    this.markVisited(entry, target.file);
    this.refresh();
  }

  markVisited(entry, path) {
    const i = entry.files.findIndex((f) => f.file === path);
    if (i < 0) return;
    entry.index = i;
    entry.states.get(path).read = true;
  }

  // Index of the next file not yet read after the one the walk is on, wrapping
  // round; -1 when every file is read.
  nextUnreadIndex(entry) {
    const n = entry.files.length;
    for (let k = 1; k < n; k++) {
      const i = (entry.index + k) % n;
      if (!entry.states.get(entry.files[i].file).read) return i;
    }
    return -1;
  }

  stepBy(entry, delta) {
    const i = entry.index + delta;
    if (i < 0 || i >= entry.files.length) return Promise.resolve();
    return this.visit(entry, i).catch((e) => this.fail("open file", e));
  }

  // Opens the review panel in the right sidebar when it is not open, and
  // reveals it.
  async openPanel() {
    const workspace = this.app.workspace;
    let leaf = workspace.getLeavesOfType(PANEL_TYPE)[0];
    if (!leaf) {
      leaf = workspace.getRightLeaf(false);
      if (!leaf) throw new Error("no right sidebar to hold the review panel");
      await leaf.setViewState({ type: PANEL_TYPE, active: true });
    }
    await workspace.revealLeaf(leaf);
    this.renderPanel();
  }

  // A file coming into view: a listed file is marked read and becomes the one
  // its review's walk is on. A file a card opened moves that card's walk only.
  onFileOpen(file) {
    if (file && file.extension === "md") {
      for (const entry of this.visiting ? [this.visiting] : this.pending.values()) this.markVisited(entry, file.path);
    }
    this.refresh();
  }

  // A renamed file keeps its mark, note and edit under its new path.
  onRename(file, oldPath) {
    for (const entry of this.pending.values()) {
      const listed = entry.files.find((f) => f.file === oldPath);
      if (listed) {
        listed.file = file.path;
        entry.states.set(file.path, entry.states.get(oldPath));
        entry.states.delete(oldPath);
        entry.request.file = entry.files[0].file;
      }
      if (entry.choiceAnswers.has(oldPath)) {
        entry.choiceAnswers.set(file.path, entry.choiceAnswers.get(oldPath));
        entry.choiceAnswers.delete(oldPath);
      }
      if (entry.decisionAnswers.has(oldPath)) {
        entry.decisionAnswers.set(file.path, entry.decisionAnswers.get(oldPath));
        entry.decisionAnswers.delete(oldPath);
      }
      if (entry.comments.has(oldPath)) {
        entry.comments.set(file.path, entry.comments.get(oldPath));
        entry.comments.delete(oldPath);
      }
      if (entry.edited.delete(oldPath)) entry.edited.add(file.path);
    }
    this.refresh();
  }

  // Typing in an editor is an edit to the file it shows. It lands on every
  // pending review that lists the file; a file no review lists lands on none.
  onEditorChange(info) {
    const file = info && info.file;
    if (!file || typeof file.path !== "string" || !file.path.endsWith(".md")) return;
    for (const entry of this.pending.values()) {
      if (!entry.files.some((f) => f.file === file.path)) continue;
      entry.edited.add(file.path);
      this.refreshCard(entry);
    }
  }

  // Drops reviews whose request file was removed or whose verdict another
  // surface already wrote.
  async recheck() {
    const adapter = this.app.vault.adapter;
    const dead = [];
    for (const [id, entry] of this.pending) {
      if (!(await adapter.exists(entry.path)) || (await adapter.exists(verdictPathFor(entry.path)))) dead.push(id);
    }
    for (const id of dead) this.pending.delete(id);
    if (this.pending.size === 0) this.asideOwed = false;
    this.refresh();
  }

  // Whether this Obsidian window has focus; null when it cannot be read, in
  // which case the review follows its request's `return`.
  windowHasFocus() {
    try {
      return !!electronRemote().getCurrentWindow().isFocused();
    } catch (e) {
      return null;
    }
  }

  // A brief always-on-top lifts the window over the foreground one, which a
  // plain focus() is refused on Windows.
  raise() {
    try {
      const win = electronRemote().getCurrentWindow();
      if (win.isMinimized()) win.restore();
      win.setAlwaysOnTop(true);
      win.show();
      win.focus();
      setTimeout(() => win.setAlwaysOnTop(false), 500);
    } catch (e) {
      this.fail("raise", e);
    }
  }

  stepAside() {
    try {
      const remote = electronRemote();
      if (process.platform === "darwin") remote.app.hide();
      else remote.getCurrentWindow().minimize();
    } catch (e) {
      this.fail("step aside", e);
    }
  }

  entryFor(path) {
    for (const entry of this.pending.values()) if (entry.files.some((f) => f.file === path)) return entry;
    return null;
  }

  refresh() {
    this.decorate();
    this.renderPanel();
    this.renderViewPanel();
  }

  // The board follows the file it shows when that file changes on disk.
  onModify(file) {
    const active = this.app.workspace.getActiveFile();
    if (file && active && file.path === active.path) this.renderViewPanel();
  }

  // The `title` property of a file, else its name.
  titleOf(path) {
    const file = this.app.vault.getAbstractFileByPath(path);
    const cache = file && this.app.metadataCache ? this.app.metadataCache.getFileCache(file) : null;
    const title = cache && cache.frontmatter && cache.frontmatter.title;
    return typeof title === "string" && title.trim() ? title.trim() : baseName(path);
  }

  questionOf(entry) {
    return entry.request.title || baseName(entry.files[0].file);
  }

  // The request's project, else the folder holding the vault: the folder above
  // `.compass` when the Obsidian vault is the Compass vault.
  projectOf(request) {
    if (request.project) return request.project;
    const adapter = this.app.vault.adapter;
    const base = typeof adapter.getBasePath === "function" ? adapter.getBasePath() : "";
    const parts = String(base).split(/[\\/]/).filter(Boolean);
    if (parts[parts.length - 1] === ".compass") parts.pop();
    return parts.pop() || "";
  }

  // Each markdown pane shows the bar of the review that lists its file.
  decorate() {
    for (const leaf of this.app.workspace.getLeavesOfType("markdown")) {
      const view = leaf.view;
      const host = view.containerEl;
      const entry = view.file ? this.entryFor(view.file.path) : null;
      const oldBar = host.querySelector(".compass-review-bar");
      const label = entry ? this.barLabel(entry, view.file.path) : null;
      if (!entry) {
        if (oldBar) oldBar.remove();
      } else if (!oldBar || oldBar.dataset.id !== entry.request.id || oldBar.dataset.label !== label) {
        if (oldBar) oldBar.remove();
        host.insertBefore(this.buildBar(entry, label), host.querySelector(".view-content"));
      }
    }
  }

  barLabel(entry, path) {
    const i = entry.files.findIndex((f) => f.file === path);
    return `Review: ${this.questionOf(entry)}, file ${i + 1} of ${entry.files.length}`;
  }

  buildBar(entry, label) {
    const bar = createDiv({ cls: "compass-review-bar" });
    bar.dataset.id = entry.request.id;
    bar.dataset.label = label;
    bar.createSpan({ cls: "compass-review-title", text: label });
    const open = bar.createEl("button", { text: "Open review panel" });
    open.onclick = () => this.openPanel().catch((e) => this.fail("open panel", e));
    return bar;
  }

  // Redraws every open panel. A panel whose cards would come out the same is
  // left alone, so a field being typed in keeps its focus and caret; the parts
  // that follow the walk are brought up to date in place.
  renderPanel() {
    for (const leaf of this.app.workspace.getLeavesOfType(PANEL_TYPE)) {
      if (leaf.view instanceof ReviewPanelView) this.drawPanel(leaf.view);
    }
  }

  drawPanel(view) {
    const root = view.contentEl;
    const entries = [...this.pending.values()].reverse();
    const active = this.app.workspace.getActiveFile();
    const other = active && active.extension === "md" ? active : null;
    const otherFor = (entry) => (other && !entry.files.some((f) => f.file === other.path) ? other : null);
    const signature = JSON.stringify(
      entries.map((entry) => [
        entry.request.id,
        entry.request.title,
        entry.request.project,
        entry.request.session,
        entry.files.map((f) => [f.file, f.why, this.titleOf(f.file)]),
        otherFor(entry) && other.path,
      ])
    );
    if (root.dataset.signature !== signature) {
      root.dataset.signature = signature;
      const focused = document.activeElement && document.activeElement.closest
        ? document.activeElement.closest(".compass-review-card")
        : null;
      const focusedId = focused && root.contains(focused) ? focused.dataset.id : null;
      root.empty();
      root.createDiv({ cls: "compass-review-heading", text: "Reviews waiting on you" });
      if (entries.length === 0) {
        root.createDiv({ cls: "compass-review-empty", text: "No reviews pending" });
        return;
      }
      for (const entry of entries) this.buildCard(root, entry, otherFor(entry));
      // A card that held keyboard focus keeps it, so the arrow keys go on working.
      const again = focusedId && Array.from(root.querySelectorAll(".compass-review-card")).find((el) => el.dataset.id === focusedId);
      if (again && again.focus) again.focus();
    }
    for (const entry of entries) this.refreshCardIn(root, entry);
  }

  buildCard(root, entry, other) {
    const { request } = entry;
    const parts = { rows: [] };
    const card = root.createDiv({ cls: "compass-review-card", attr: { tabindex: "0" } });
    card.dataset.id = request.id;
    card.compassParts = parts;
    card.createDiv({ cls: "compass-review-question", text: this.questionOf(entry) });
    card.addEventListener("keydown", (event) => {
      const target = event.target;
      const tag = String((target && target.tagName) || "").toLowerCase();
      if (tag === "textarea" || tag === "input") return;
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        this.stepBy(entry, 1);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        this.stepBy(entry, -1);
      }
    });

    const project = this.projectOf(request);
    const session = typeof request.session === "string" ? request.session.slice(0, 6) : "";
    if (project || session) {
      const who = card.createDiv({ cls: "compass-review-who" });
      if (project) {
        who.createSpan({ cls: "compass-review-label", text: "Project" });
        who.createEl("strong", { text: project });
      }
      if (session) {
        who.createSpan({ cls: "compass-review-label", text: "Session" });
        who.createEl("code", { text: session });
      }
    }

    const nav = card.createDiv({ cls: "compass-review-nav" });
    parts.pos = nav.createSpan({ cls: "compass-review-pos" });
    parts.prev = nav.createEl("button", { text: "Previous" });
    parts.next = nav.createEl("button", { cls: "mod-cta", text: "Next" });
    parts.nextUnread = nav.createEl("button", { text: "Next unread" });
    parts.prev.onclick = () => this.stepBy(entry, -1);
    parts.next.onclick = () => this.stepBy(entry, 1);
    parts.nextUnread.onclick = () => {
      const i = this.nextUnreadIndex(entry);
      return i < 0 ? undefined : this.visit(entry, i).catch((e) => this.fail("open file", e));
    };

    const rows = card.createDiv({ cls: "compass-review-rows" });
    entry.files.forEach((f, i) => {
      const row = rows.createDiv({ cls: "compass-review-row" });
      const mark = row.createSpan({ cls: "compass-review-mark" });
      const body = row.createDiv({ cls: "compass-review-row-body" });
      const link = body.createEl("a", { cls: "compass-review-file", text: this.titleOf(f.file), href: "#" });
      if (f.why) body.createDiv({ cls: "compass-review-fine", text: f.why });
      const count = row.createSpan({ cls: "compass-review-fine compass-review-row-count" });
      const open = () => this.visit(entry, i).catch((e) => this.fail("open file", e));
      link.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        return open();
      });
      row.addEventListener("click", open);
      parts.rows.push({ row, mark, count });
    });

    parts.label = card.createDiv({ cls: "compass-review-label compass-review-note-label" });
    parts.notes = card.createEl("textarea", {
      cls: "compass-review-notes",
      placeholder: "Note on this file (optional)",
      attr: { rows: "3" },
    });
    parts.notes.addEventListener("input", () => {
      entry.states.get(entry.files[entry.index].file).note = parts.notes.value;
      this.refreshCard(entry);
    });

    if (other) {
      const block = card.createDiv({ cls: "compass-review-this-file" });
      block.createDiv({ cls: "compass-review-label", text: `On this file: ${other.path}` });
      const note = block.createEl("textarea", {
        cls: "compass-review-file-note",
        placeholder: "Note on this file for Claude",
        attr: { rows: "2" },
      });
      note.value = entry.comments.get(other.path) || "";
      note.addEventListener("input", () => {
        if (note.value.trim()) entry.comments.set(other.path, note.value);
        else entry.comments.delete(other.path);
        this.refreshCard(entry);
      });
      block.createDiv({
        cls: "compass-review-fine",
        text: "This file is not in the review; the note goes with your answer.",
      });
    }

    const feedback = card.createDiv({ cls: "compass-review-feedback-block" });
    feedback.createDiv({ cls: "compass-review-label", text: "Feedback so far" });
    parts.feedback = feedback.createEl("ul", { cls: "compass-review-feedback" });
    parts.feedbackBlock = feedback;

    const foot = card.createDiv({ cls: "compass-review-foot" });
    parts.summary = foot.createDiv({ cls: "compass-review-fine compass-review-summary" });
    const actions = foot.createDiv({ cls: "compass-review-actions" });
    const approve = actions.createEl("button", { cls: "mod-cta", text: "Approve" });
    parts.changes = actions.createEl("button", { cls: "compass-review-changes", text: "Needs changes" });
    approve.onclick = () => this.verdict(entry, "approved").catch((e) => this.fail("verdict", e));
    parts.changes.onclick = () => this.verdict(entry, "changes").catch((e) => this.fail("verdict", e));
    foot.createDiv({
      cls: "compass-review-fine",
      text: "Project is the folder holding the vault. Session is the first six characters of the Claude Code session id.",
    });
    if (entry.files.length > 1) {
      foot.createDiv({
        cls: "compass-review-fine",
        text: "Left and right arrow keys move between files when this card has focus.",
      });
    }
  }

  noteCount(entry) {
    return entry.files.filter((f) => entry.states.get(f.file).note.trim() !== "").length;
  }

  // The choice lines of every plan answered on a card, in the order the
  // answers were first given.
  changedChoiceLines(entry) {
    const lines = [];
    for (const answers of entry.choiceAnswers.values()) {
      lines.push(...choiceNoteLines(Object.keys(answers).map((choice) => ({ choice })), answers));
    }
    return lines;
  }

  // The decision lines of every spec answered on a card, in the order the
  // answers were first given. A Change with a blank note gives none.
  changedDecisionLines(entry) {
    const lines = [];
    for (const answers of entry.decisionAnswers.values()) {
      lines.push(...decisionNoteLines(Object.keys(answers).map((id) => ({ id })), answers));
    }
    return lines;
  }

  hasFeedback(entry) {
    return (
      this.noteCount(entry) > 0 ||
      entry.comments.size > 0 ||
      entry.edited.size > 0 ||
      this.changedChoiceLines(entry).length > 0 ||
      this.changedDecisionLines(entry).length > 0
    );
  }

  // One line per note on a file outside the review, one per changed choice or
  // decision, then one per edited file.
  feedbackItems(entry) {
    return [
      ...[...entry.comments].map(([file, note]) => `${file}: ${note}`),
      ...this.changedChoiceLines(entry),
      ...this.changedDecisionLines(entry),
      ...[...entry.edited].map((file) => `edited: ${file}`),
    ];
  }

  // Brings a card's parts up to date with its review: position, buttons, rows,
  // note field, summary, feedback list and the "Needs changes" gate.
  fillCard(entry, card) {
    const parts = card.compassParts;
    if (!parts || parts.rows.length !== entry.files.length) return;
    const n = entry.files.length;
    const current = entry.files[entry.index];
    parts.pos.setText(`File ${entry.index + 1} of ${n}`);
    parts.prev.disabled = entry.index === 0;
    parts.next.disabled = entry.index >= n - 1;
    parts.nextUnread.disabled = this.nextUnreadIndex(entry) < 0;

    entry.files.forEach((f, i) => {
      const state = entry.states.get(f.file);
      const { row, mark, count } = parts.rows[i];
      mark.setText(state.read ? "read" : "unread");
      setClass(mark, "is-read", state.read);
      setClass(row, "is-current", i === entry.index);
      count.setText(state.note.trim() ? "1 note" : "no note");
    });

    parts.label.setText(`Note on ${this.titleOf(current.file)}`);
    if (parts.notes.dataset.index !== String(entry.index)) {
      parts.notes.dataset.index = String(entry.index);
      parts.notes.value = entry.states.get(current.file).note;
    }

    const read = entry.files.filter((f) => entry.states.get(f.file).read).length;
    const outside = [...entry.comments.values()].filter((note) => note.trim() !== "").length;
    let line = `${read} of ${n} files read, ${plural(this.noteCount(entry), "note")}`;
    if (outside) line += `, ${plural(outside, "note")} on files outside the review`;
    parts.summary.setText(line);

    parts.feedback.empty();
    const items = this.feedbackItems(entry);
    for (const item of items) parts.feedback.createEl("li", { text: item });
    setClass(parts.feedbackBlock, "is-empty", items.length === 0);
    parts.changes.disabled = !this.hasFeedback(entry);
    parts.changes.title = parts.changes.disabled ? "Write a note first" : "";
  }

  refreshCardIn(root, entry) {
    const card = Array.from(root.querySelectorAll(".compass-review-card")).find((el) => el.dataset.id === entry.request.id);
    if (card) this.fillCard(entry, card);
  }

  refreshCard(entry) {
    for (const leaf of this.app.workspace.getLeavesOfType(PANEL_TYPE)) {
      if (leaf.view instanceof ReviewPanelView) this.refreshCardIn(leaf.view.contentEl, entry);
    }
  }

  // Opens the Compass view panel in the right sidebar when it is not open, and
  // reveals it.
  async openViewPanel() {
    const workspace = this.app.workspace;
    let leaf = workspace.getLeavesOfType(VIEW_TYPE)[0];
    if (!leaf) {
      leaf = workspace.getRightLeaf(false);
      if (!leaf) throw new Error("no right sidebar to hold the view panel");
      await leaf.setViewState({ type: VIEW_TYPE, active: true });
    }
    await workspace.revealLeaf(leaf);
    this.renderViewPanel();
  }

  renderViewPanel() {
    for (const leaf of this.app.workspace.getLeavesOfType(VIEW_TYPE)) {
      if (leaf.view instanceof ViewPanelView) {
        this.drawViewPanel(leaf.view).catch((e) => console.error("[compass-review] view panel failed", e));
      }
    }
  }

  // Draws the view for the markdown file in view. A panel whose drawing would
  // come out the same is left alone, so a note being typed keeps its focus and
  // caret; of two draws in flight only the later one lands.
  async drawViewPanel(view) {
    const seq = ++view.drawSeq;
    const root = view.contentEl;
    const active = this.app.workspace.getActiveFile();
    const file = active && active.extension === "md" ? active : null;
    let text = null;
    if (file) {
      try {
        text = await this.app.vault.adapter.read(file.path);
      } catch (e) {
        text = null;
      }
    }
    if (seq !== view.drawSeq) return;
    const kind = text === null ? null : viewFor(text);
    const entry = file && (kind === "plan" || kind === "spec") ? this.entryFor(file.path) : null;
    const signature = JSON.stringify([file && file.path, text === null ? null : textHash(text), entry && entry.request.id]);
    if (root.dataset.signature === signature) return;
    root.dataset.signature = signature;
    root.empty();
    if (!file) {
      root.createDiv({ cls: "compass-view-note", text: "Open a document to see its view." });
    } else if (text === null) {
      root.createDiv({ cls: "compass-view-note", text: "This document could not be read." });
    } else if (kind === "plan") {
      this.drawPlanBoard(root, file, text, entry);
    } else if (kind === "spec") {
      this.drawSpecView(root, file, text, entry);
    } else if (kind === "research") {
      this.drawResearchView(root, view, file, text);
    } else {
      const type = typeOf(text);
      root.createDiv({
        cls: "compass-view-note",
        text: type
          ? `Compass has no view for a document of type ${type}.`
          : "This document has no type property, so Compass has no view for it.",
      });
    }
  }

  openLine(path, line, what) {
    this.showFile(path, true, { eState: { line: line - 1 } }).catch((e) => this.fail(what, e));
  }

  openTask(path, line) {
    this.openLine(path, line, "open task");
  }

  drawPlanBoard(root, file, text, entry) {
    const tasks = parsePlanTasks(text);
    const { props } = propertiesOf(linesOf(text));
    const board = root.createDiv({ cls: "compass-plan-board" });
    const head = board.createDiv({ cls: "compass-plan-head" });
    head.createSpan({ cls: "compass-plan-title", text: this.titleOf(file.path) });
    if (props.status) head.createSpan({ cls: "compass-chip", text: props.status });

    if (tasks.length === 0) {
      board.createDiv({ cls: "compass-view-note", text: "This plan has no task lines." });
    } else {
      const counts = { done: 0, ready: 0, waiting: 0, later: 0 };
      for (const t of tasks) counts[t.status]++;
      board.createDiv({
        cls: "compass-plan-sum",
        text: `${counts.done} of ${tasks.length} tasks done, ${counts.ready} ready, ${counts.waiting} waiting, ${counts.later} intent only`,
      });
      const legend = board.createDiv({ cls: "compass-legend" });
      for (const status of Object.keys(STATUS_LABEL)) {
        const item = legend.createSpan({ cls: "compass-legend-item" });
        item.createSpan({ cls: `compass-dot is-${status}` });
        item.appendText(STATUS_LABEL[status]);
      }
      this.drawGraph(board, file.path, tasks);
      this.drawTaskTable(board, file.path, tasks);
    }
    if (entry) this.drawChoices(board, entry, file.path, text);
  }

  drawGraph(parent, path, tasks) {
    const layout = layoutGraph(tasks);
    const status = new Map(tasks.map((t) => [t.id, t.status]));
    const scroll = parent.createDiv({ cls: "compass-graph-scroll" });
    const graph = scroll.createDiv({ cls: "compass-graph" });
    graph.style.width = `${layout.width}px`;
    graph.style.height = `${layout.height}px`;
    const svg = graph.createSvg("svg", { cls: "compass-graph-edges", attr: { width: layout.width, height: layout.height } });
    const marker = svg.createSvg("defs").createSvg("marker", {
      attr: { id: "compass-arrow", viewBox: "0 0 8 8", refX: "7", refY: "4", markerWidth: "7", markerHeight: "7", orient: "auto" },
    });
    marker.createSvg("path", { cls: "compass-graph-arrowhead", attr: { d: "M0,0 L8,4 L0,8 z" } });
    for (const lane of layout.lanes) {
      const label = graph.createDiv({ cls: "compass-graph-lane", text: lane.name });
      label.style.top = `${lane.y}px`;
      label.style.height = `${lane.h}px`;
      label.style.width = `${layout.width - 4}px`;
    }
    for (const e of layout.edges) {
      const edge = svg.createSvg("path", {
        cls: "compass-graph-edge" + (status.get(e.from) === "done" ? " is-done" : ""),
        attr: { d: e.path, "marker-end": "url(#compass-arrow)" },
      });
      edge.dataset.from = e.from;
      edge.dataset.to = e.to;
    }
    for (const t of tasks) {
      const p = layout.pos.get(t.id);
      const node = graph.createDiv({ cls: `compass-graph-node is-${t.status}`, attr: { title: `${t.id} ${t.desc}` } });
      node.dataset.id = t.id;
      node.dataset.status = t.status;
      node.style.left = `${p.x}px`;
      node.style.top = `${p.y}px`;
      node.style.width = `${NODE_W}px`;
      node.style.height = `${NODE_H}px`;
      node.createSpan({ cls: "compass-graph-id", text: t.id.replace("TASK-", "") });
      node.createSpan({ cls: "compass-graph-title", text: t.title });
      node.onclick = () => this.openTask(path, t.line);
    }
  }

  drawTaskTable(parent, path, tasks) {
    const scroll = parent.createDiv({ cls: "compass-task-scroll" });
    const table = scroll.createEl("table", { cls: "compass-task-table" });
    const headRow = table.createEl("thead").createEl("tr");
    for (const name of ["Id", "Task", "Wave", "Status", "Depends on"]) headRow.createEl("th", { text: name });
    const body = table.createEl("tbody");
    for (const t of tasks) {
      const row = body.createEl("tr", { cls: `compass-task-row is-${t.status}` });
      row.dataset.id = t.id;
      row.dataset.status = t.status;
      const open = row.createEl("td", { cls: "compass-task-open", text: t.id, attr: { title: "Open this task in the plan" } });
      open.onclick = () => this.openTask(path, t.line);
      row.createEl("td", { text: t.title, attr: { title: t.desc } });
      row.createEl("td", { text: t.wave !== null ? String(t.wave) : t.lane });
      const state = row.createEl("td");
      state.createSpan({ cls: `compass-chip is-${t.status}`, text: t.status });
      row.createEl("td", { text: t.dependsOn.length ? t.dependsOn.join(", ") : "none" });
    }
  }

  // The answers given to one plan's choices on a review: {choice -> {state,
  // note}}, state "agree" or "change".
  choiceAnswersFor(entry, path) {
    let answers = entry.choiceAnswers.get(path);
    if (!answers) {
      answers = Object.create(null);
      entry.choiceAnswers.set(path, answers);
    }
    return answers;
  }

  // One row per row of the plan's choices table, answered in place so a
  // redraw of the panel keeps what was typed.
  drawChoices(parent, entry, path, text) {
    const choices = parsePlanChoices(text);
    if (choices.length === 0) return;
    const answers = this.choiceAnswersFor(entry, path);
    const box = parent.createDiv({ cls: "compass-choices" });
    box.createEl("h4", { cls: "compass-board-heading", text: "Choices to approve" });
    box.createDiv({
      cls: "compass-fine",
      text: "Agree or change each choice. A changed choice goes to Claude, with your note, in your answer to the review.",
    });
    const table = box.createEl("table", { cls: "compass-choice-table" }).createEl("tbody");
    for (const c of choices) {
      const row = table.createEl("tr", { cls: "compass-choice-row" });
      row.dataset.choice = c.choice;
      const what = row.createEl("td");
      what.createEl("strong", { text: c.choice });
      inline(what.createDiv({ cls: "compass-choice-answer" }), c.answer);
      const act = row.createEl("td", { cls: "compass-choice-actions" });
      const buttons = act.createDiv({ cls: "compass-choice-buttons" });
      const agree = buttons.createEl("button", { text: "Agree" });
      const change = buttons.createEl("button", { text: "Change" });
      const note = act.createEl("textarea", {
        cls: "compass-choice-note",
        placeholder: "What should change?",
        attr: { rows: "2" },
      });
      const paint = () => {
        const state = hasOwn(answers, c.choice) ? answers[c.choice].state : "";
        setClass(row, "is-agree", state === "agree");
        setClass(row, "is-change", state === "change");
        setClass(agree, "mod-cta", state === "agree");
        setClass(change, "mod-warning", state === "change");
      };
      const answer = (state, typed) => {
        answers[c.choice] = { state, note: typed };
        paint();
        this.refreshCard(entry);
      };
      const noteNow = () => (hasOwn(answers, c.choice) ? answers[c.choice].note : "");
      note.value = noteNow();
      agree.onclick = () => answer("agree", noteNow());
      change.onclick = () => answer("change", noteNow());
      note.addEventListener("input", () => {
        const state = hasOwn(answers, c.choice) ? answers[c.choice].state : "change";
        answer(state, note.value);
      });
      paint();
    }
  }

  // The answers given to one spec's decisions on a review: {D-NN -> {state,
  // note}}, state "agree" or "change" (or "" for a note typed before an answer).
  decisionAnswersFor(entry, path) {
    let answers = entry.decisionAnswers.get(path);
    if (!answers) {
      answers = Object.create(null);
      entry.decisionAnswers.set(path, answers);
    }
    return answers;
  }

  // The spec as the human wrote it: Problem and Desired Outcome side by side,
  // then one card per decision. While a review of the spec is pending the
  // cards take answers in place, so a redraw of the panel keeps what was typed.
  drawSpecView(root, file, text, entry) {
    const spec = parseSpec(text);
    const { props } = propertiesOf(linesOf(text));
    const view = root.createDiv({ cls: "compass-spec-view" });
    const head = view.createDiv({ cls: "compass-doc-head" });
    head.createSpan({ cls: "compass-doc-title", text: this.titleOf(file.path) });
    if (props.status) head.createSpan({ cls: "compass-chip", text: props.status });

    const words = view.createDiv({ cls: "compass-spec-words" });
    const part = (label, cls, body, line, none) => {
      const col = words.createDiv({ cls: "compass-spec-col" });
      const name = col.createDiv({ cls: "compass-fine", text: label });
      const quote = col.createDiv({ cls: `compass-spec-quote ${cls}` });
      if (body) {
        prose(quote, body);
        name.addClass("compass-open-line");
        name.onclick = () => this.openLine(file.path, line, "open spec");
      } else quote.createDiv({ cls: "compass-view-note", text: none });
    };
    part("The problem, in your words", "compass-spec-problem", spec.problem, spec.problemLine, "This spec has no Problem section.");
    part("What you asked for", "compass-spec-outcome", spec.desiredOutcome, spec.desiredOutcomeLine, "This spec has no Desired Outcome section.");

    const n = spec.decisions.length;
    view.createEl("h4", { cls: "compass-board-heading", text: `${plural(n, "decision")} recorded` });
    if (spec.decisionState === "could-not-parse") {
      view.createDiv({
        cls: "compass-view-note",
        text: "Compass could not read every decision in this spec. The cards show the ones it could read.",
      });
    } else if (n === 0) {
      view.createDiv({ cls: "compass-view-note", text: "This spec records no decisions." });
    }
    if (entry && n > 0) {
      view.createDiv({
        cls: "compass-fine",
        text: "Agree or change each decision. A changed decision goes to Claude, with your note, in your answer to the review.",
      });
    }
    const answers = entry ? this.decisionAnswersFor(entry, file.path) : null;
    for (const d of spec.decisions) this.drawDecisionCard(view, d, file.path, entry, answers);
  }

  drawDecisionCard(parent, d, path, entry, answers) {
    const card = parent.createDiv({ cls: "compass-decision-card" });
    card.dataset.id = d.id;
    const top = card.createDiv({ cls: "compass-decision-top" });
    const id = top.createSpan({ cls: "compass-decision-id", text: d.id, attr: { title: "Open this decision in the spec" } });
    id.onclick = () => this.openLine(path, d.line, "open decision");
    for (const tag of d.tags) top.createSpan({ cls: "compass-chip", text: tag });
    if (!d.trackable && d.tags.length === 0) top.createSpan({ cls: "compass-chip", text: "builder discretion" });
    inline(card.createDiv({ cls: "compass-decision-text" }), d.text);
    if (!entry) return;

    const act = card.createDiv({ cls: "compass-decision-actions" });
    const buttons = act.createDiv({ cls: "compass-choice-buttons" });
    const agree = buttons.createEl("button", { text: "Agree" });
    const change = buttons.createEl("button", { text: "Change" });
    const note = act.createEl("textarea", {
      cls: "compass-decision-note",
      placeholder: "What should change? A note is needed to change a decision.",
      attr: { rows: "2" },
    });
    let hint = null;
    let needNote = false;
    const stateNow = () => (hasOwn(answers, d.id) ? answers[d.id].state : "");
    const paint = () => {
      const state = stateNow();
      setClass(card, "is-agree", state === "agree");
      setClass(card, "is-change", state === "change");
      setClass(agree, "mod-cta", state === "agree");
      setClass(change, "mod-warning", state === "change");
      if (needNote && !hint) {
        hint = act.createDiv({ cls: "compass-decision-need-note", text: "Write what should change, then choose Change." });
      } else if (!needNote && hint) {
        hint.remove();
        hint = null;
      }
    };
    const answer = (state) => {
      answers[d.id] = { state, note: note.value };
      needNote = false;
      paint();
      this.refreshCard(entry);
    };
    note.value = hasOwn(answers, d.id) ? answers[d.id].note : "";
    agree.onclick = () => answer("agree");
    change.onclick = () => {
      if (note.value.trim() === "") {
        needNote = true;
        paint();
        this.refreshCard(entry);
      } else answer("change");
    };
    note.addEventListener("input", () => {
      if (hasOwn(answers, d.id)) answers[d.id].note = note.value;
      else answers[d.id] = { state: "", note: note.value };
      needNote = stateNow() === "change" && note.value.trim() === "";
      paint();
      this.refreshCard(entry);
    });
    paint();
  }

  // Bars of findings per section, a filter per confidence level, then one row
  // per shown finding; a click on a row opens the document at the finding.
  drawResearchView(root, view, file, text) {
    const findings = parseResearchFindings(text);
    const { props } = propertiesOf(linesOf(text));
    const wrap = root.createDiv({ cls: "compass-research-view" });
    const head = wrap.createDiv({ cls: "compass-doc-head" });
    head.createSpan({ cls: "compass-doc-title", text: this.titleOf(file.path) });
    if (props.status) head.createSpan({ cls: "compass-chip", text: props.status });
    head.createSpan({ cls: "compass-fine", text: plural(findings.length, "finding") });
    if (findings.length === 0) {
      wrap.createDiv({ cls: "compass-view-note", text: "This document has no finding tables." });
      return;
    }

    const sections = countFindingsBySection(findings);
    const widest = Math.max(...sections.map((s) => s.total));
    const bars = wrap.createDiv({ cls: "compass-section-bars" });
    for (const s of sections) {
      const row = bars.createDiv({ cls: "compass-section-bar" });
      for (const k of ["total", ...CONFIDENCES]) row.dataset[k] = String(s[k]);
      row.dataset.section = s.name;
      row.createSpan({ cls: "compass-section-name", text: s.name.replace(/\s*\(axis[^)]*\)$/, ""), attr: { title: s.name } });
      const track = row.createSpan({ cls: "compass-section-track" });
      track.style.width = `${Math.max(8, Math.round((s.total / widest) * 100))}%`;
      for (const c of [...CONFIDENCES, "other"]) {
        if (!s[c]) continue;
        const bit = track.createSpan({ cls: `compass-section-part compass-conf-${c}`, attr: { title: `${s[c]} ${c === "other" ? "unrated" : c}` } });
        bit.style.flexGrow = String(s[c]);
      }
      row.createSpan({ cls: "compass-section-n", text: String(s.total) });
    }

    if (!view.confOn.has(file.path)) view.confOn.set(file.path, { high: true, medium: true, low: true });
    const on = view.confOn.get(file.path);
    const controls = wrap.createDiv({ cls: "compass-research-controls" });
    const buttons = CONFIDENCES.map((c) => {
      const b = controls.createEl("button", { cls: `compass-conf-filter compass-conf-${c}`, text: c });
      b.dataset.conf = c;
      b.onclick = () => {
        on[c] = !on[c];
        paint();
      };
      return b;
    });
    const count = controls.createSpan({ cls: "compass-fine" });
    const list = wrap.createDiv({ cls: "compass-finding-rows" });
    const paint = () => {
      buttons.forEach((b) => setClass(b, "is-on", on[b.dataset.conf]));
      const shown = filterFindings(findings, CONFIDENCES.filter((c) => on[c]));
      count.setText(`${shown.length} of ${findings.length} shown`);
      list.empty();
      for (const f of shown) this.drawFindingRow(list, file.path, f);
      if (shown.length === 0) list.createDiv({ cls: "compass-view-note", text: "No finding matches these filters." });
    };
    paint();
  }

  drawFindingRow(parent, path, f) {
    const row = parent.createDiv({ cls: "compass-finding-row", attr: { title: "Open this finding in the document" } });
    row.dataset.n = String(f.n);
    row.onclick = () => this.openLine(path, f.line, "open finding");
    const top = row.createDiv({ cls: "compass-finding-top" });
    top.createSpan({ cls: "compass-finding-n", text: String(f.n) });
    const level = CONFIDENCES.length - CONFIDENCES.indexOf(f.conf);
    const pips = top.createSpan({ cls: `compass-pips compass-conf-${f.conf || "none"}`, attr: { title: f.conf ? `confidence ${f.conf}` : "no confidence given" } });
    for (let i = 0; i < CONFIDENCES.length; i++) {
      pips.createSpan({ cls: "compass-pip" + (f.conf && i < level ? " is-on" : "") });
    }
    inline(top.createSpan({ cls: "compass-finding-text" }), f.text);
    if (f.grade) top.createSpan({ cls: "compass-chip", text: `weight ${f.grade}` });
    if (f.confNote && f.confNote.toLowerCase() !== f.conf) {
      row.createDiv({ cls: "compass-fine", text: `Confidence: ${f.confNote}` });
    }
    if (f.evidence) inline(row.createDiv({ cls: "compass-finding-evidence compass-fine" }), f.evidence);
  }

  async verdict(entry, verdict) {
    if (entry.sending) return;
    entry.sending = true;
    try {
      await this.sendVerdict(entry, verdict);
    } finally {
      entry.sending = false;
    }
  }

  // The choice lines of each file with a changed choice, in the order of the
  // file's table as it reads now: Map(file -> lines). Every changed choice
  // yields a line, so this agrees with hasFeedback.
  async choiceLinesFor(entry) {
    const out = new Map();
    for (const [file, answers] of entry.choiceAnswers) {
      if (!Object.values(answers).some((a) => a.state === "change")) continue;
      let choices = [];
      try {
        choices = parsePlanChoices(await this.app.vault.adapter.read(file));
      } catch (e) {
        choices = [];
      }
      // A changed choice whose row has left the table is still sent, after
      // the rows that remain.
      const rest = Object.keys(answers).map((choice) => ({ choice }));
      out.set(file, choiceNoteLines([...choices, ...rest], answers));
    }
    return out;
  }

  // The decision lines of each file with an answer, in the order of the spec
  // as it reads now: Map(file -> lines). A changed decision whose card has left
  // the spec is still sent, after the rest.
  async decisionLinesFor(entry) {
    const out = new Map();
    for (const [file, answers] of entry.decisionAnswers) {
      let decisions = [];
      try {
        decisions = parseSpec(await this.app.vault.adapter.read(file)).decisions;
      } catch (e) {
        decisions = [];
      }
      const lines = decisionNoteLines(decisions, answers);
      if (lines.length > 0) out.set(file, lines);
    }
    return out;
  }

  // The answer: one `files` entry per listed document, in request order, when
  // the review lists several; a review of one document keeps its note as
  // `notes`. `choiceLines` (Map(file -> lines)) joins the note of its file.
  buildAnswer(entry, verdict, choiceLines = new Map()) {
    const { request } = entry;
    const answer = {
      id: request.id,
      file: entry.files[0].file,
      verdict,
      notes: "",
      comments: [...entry.comments].map(([file, note]) => ({ file, note: note.trim() })),
      edited: [...entry.edited],
      at: new Date().toISOString(),
    };
    if (entry.files.length === 1) {
      const only = entry.files[0].file;
      answer.notes = joinChoiceNote(entry.states.get(only).note, choiceLines.get(only) || []);
      return answer;
    }
    answer.files = entry.files.map((f) => {
      const state = entry.states.get(f.file);
      const item = { file: f.file, read: state.read };
      const note = joinChoiceNote(state.note.trim(), choiceLines.get(f.file) || []);
      if (note) item.note = note;
      return item;
    });
    answer.notes = answer.files
      .filter((f) => f.note)
      .map((f) => `${baseName(f.file)}: ${f.note}`)
      .join("\n");
    return answer;
  }

  async sendVerdict(entry, verdict) {
    const { request, path } = entry;
    // Flush the human's edits before Compass reads the files.
    const listed = new Set(entry.files.map((f) => f.file));
    for (const leaf of this.app.workspace.getLeavesOfType("markdown")) {
      if (leaf.view instanceof MarkdownView && leaf.view.file && listed.has(leaf.view.file.path)) {
        await leaf.view.save();
      }
    }
    const choiceLines = await this.choiceLinesFor(entry);
    for (const [file, lines] of await this.decisionLinesFor(entry)) choiceLines.set(file, [...(choiceLines.get(file) || []), ...lines]);
    if (!(await this.app.vault.adapter.exists(path))) {
      this.pending.delete(request.id);
      if (this.pending.size === 0) this.asideOwed = false;
      this.refresh();
      new Notice("This review was withdrawn - nothing was sent");
      return;
    }
    if (this.pending.get(request.id) !== entry) return;
    await this.app.vault.adapter.write(verdictPathFor(path), JSON.stringify(this.buildAnswer(entry, verdict, choiceLines), null, 2));
    this.pending.delete(request.id);
    this.refresh();
    new Notice(verdict === "approved" ? "Approved - sent to Claude" : "Changes requested - sent to Claude");
    // Obsidian steps aside once no review is left, when any review answered
    // since the window was raised arrived without focus; a pending set that
    // empties by withdrawal clears the debt instead. A review with no
    // recorded arrival (found at start-up) follows its request's `return`.
    const owes = entry.arrivedUnfocused === undefined ? !!request.return : entry.arrivedUnfocused;
    this.asideOwed = this.asideOwed || owes;
    if (this.pending.size === 0 && this.asideOwed) {
      this.asideOwed = false;
      this.stepAside();
    }
  }
}

module.exports = CompassReview;
module.exports.verdictPathFor = verdictPathFor;
module.exports.parsePlanTasks = parsePlanTasks;
module.exports.parsePlanChoices = parsePlanChoices;
module.exports.viewFor = viewFor;
module.exports.choiceNoteLines = choiceNoteLines;
module.exports.joinChoiceNote = joinChoiceNote;
module.exports.parseSpec = parseSpec;
module.exports.parseResearchFindings = parseResearchFindings;
module.exports.countFindingsBySection = countFindingsBySection;
module.exports.filterFindings = filterFindings;
module.exports.decisionNoteLines = decisionNoteLines;

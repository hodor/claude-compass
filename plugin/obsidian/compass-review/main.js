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

const { Plugin, ItemView, Notice, MarkdownView } = require("obsidian");

const REVIEW_DIRS = ["tmp/review", ".compass/tmp/review"];
const SURFACE = "obsidian";
const RECHECK_MS = 5000;
const PANEL_TYPE = "compass-review-panel";

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

class CompassReview extends Plugin {
  async onload() {
    // request id -> {request, path, files: [{file, why}], states: Map(file ->
    // {read, note}), index, comments: Map(file outside the review -> note),
    // edited: Set(path)} in arrival order; the panel lists it newest first.
    this.pending = new Map();
    this.registerView(PANEL_TYPE, (leaf) => new ReviewPanelView(leaf, this));
    this.registerObsidianProtocolHandler("compass-review", (params) =>
      this.onRequest(params.request).catch((e) => this.fail("request", e))
    );
    this.registerEvent(this.app.workspace.on("file-open", (file) => this.onFileOpen(file)));
    this.registerEvent(this.app.workspace.on("layout-change", () => this.refresh()));
    this.registerEvent(this.app.vault.on("rename", (file, oldPath) => this.onRename(file, oldPath)));
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
    };
    for (const old of replaced) {
      if (old.arrivedUnfocused) created.arrivedUnfocused = true;
      for (const f of files) if (old.states.has(f.file)) created.states.set(f.file, old.states.get(f.file));
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
  async showFile(path, focus = true) {
    const file = this.app.vault.getAbstractFileByPath(path);
    if (!file) throw new Error(`file not in this vault: ${path}`);
    const open = this.app.workspace
      .getLeavesOfType("markdown")
      .find((leaf) => leaf.view.file && leaf.view.file.path === path);
    const leaf = open || this.app.workspace.getLeaf(false);
    await leaf.openFile(file);
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
    this.refresh();
  }

  // Whether this Obsidian window has focus; null when it cannot be read.
  windowHasFocus() {
    try {
      return !!electronRemote().getCurrentWindow().isFocused();
    } catch (e) {
      this.fail("read focus", e);
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

  hasFeedback(entry) {
    return this.noteCount(entry) > 0 || entry.comments.size > 0 || entry.edited.size > 0;
  }

  // One line per note on a file outside the review, then one per edited file.
  feedbackItems(entry) {
    return [
      ...[...entry.comments].map(([file, note]) => `${file}: ${note}`),
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

  async verdict(entry, verdict) {
    if (entry.sending) return;
    entry.sending = true;
    try {
      await this.sendVerdict(entry, verdict);
    } finally {
      entry.sending = false;
    }
  }

  // The answer: one `files` entry per listed document, in request order, when
  // the review lists several; a review of one document keeps its note as
  // `notes`.
  buildAnswer(entry, verdict) {
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
      answer.notes = entry.states.get(entry.files[0].file).note;
      return answer;
    }
    answer.files = entry.files.map((f) => {
      const state = entry.states.get(f.file);
      const item = { file: f.file, read: state.read };
      if (state.note.trim()) item.note = state.note.trim();
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
    if (!(await this.app.vault.adapter.exists(path))) {
      this.pending.delete(request.id);
      this.refresh();
      new Notice("This review was withdrawn - nothing was sent");
      return;
    }
    if (this.pending.get(request.id) !== entry) return;
    await this.app.vault.adapter.write(verdictPathFor(path), JSON.stringify(this.buildAnswer(entry, verdict), null, 2));
    this.pending.delete(request.id);
    this.refresh();
    new Notice(verdict === "approved" ? "Approved - sent to Claude" : "Changes requested - sent to Claude");
    // Obsidian steps aside once no review is left, when any review answered
    // since the window was raised arrived without focus. A review with no
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

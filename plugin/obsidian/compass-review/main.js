// Compass Review: puts the document Compass asks the human to review in front
// of him, and hands his verdict back.
//
// Protocol (paths relative to the Obsidian vault root, forward slashes):
//   <dir>/<id>.request.json   written by Compass:
//     {"id", "surface"?, "file", "title"?, "return": bool}
//   obsidian://compass-review?vault=<vault id>&request=<dir>/<id>.request.json
//   <dir>/<id>.verdict.json   written here when a button is clicked:
//     {"id", "file", "verdict": "approved"|"changes", "notes",
//      "comments": [{"file", "note"}], "edited": [path], "at"}
//     notes     the note typed on the review card
//     comments  one note per other file the human annotated from the card
//               (files with an empty note are left out)
//     edited    every markdown file modified in the vault while the review
//               was pending, each listed once
// <dir> is the Compass vault's tmp/review folder: `tmp/review` when the
// Obsidian vault is the Compass vault, `.compass/tmp/review` when the
// Obsidian vault is the project around it. Other review surfaces share the
// folder; a request whose `surface` names another one is theirs.
//
// A request raises the Obsidian window above whatever has focus, opens the
// file, and reveals the review panel, a view in the right sidebar that stays
// in place while the human moves around the vault. The panel holds one card
// per pending review, newest first. A card shows the question (the request
// title, else the file name), a link that reopens the reviewed file, a notes
// field, the "Feedback so far" list (notes on other files and edited files),
// and the Approve and "Needs changes" buttons. While a markdown file other
// than the card's reviewed file is in view, the card also shows an "On this
// file" note field for that file. "Needs changes" is enabled once there is
// something to send: a note, a note on another file, or an edit.
//
// The reviewed document carries a one-line bar naming the review, with a
// button that opens the panel. A click on a card saves the editor, writes the
// verdict and, when the request says `return`, steps Obsidian aside (minimize,
// or hide on macOS) so focus falls back to the window that had it before.
// Everything the human types lives on the review's entry, so redrawing the
// panel keeps it. A periodic recheck drops a review whose request file is gone
// or whose verdict already exists.

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

class CompassReview extends Plugin {
  async onload() {
    // request id -> {request, path, notes, comments: Map(file -> note), edited: Set(path)}
    // in arrival order; the panel lists it newest first.
    this.pending = new Map();
    this.registerView(PANEL_TYPE, (leaf) => new ReviewPanelView(leaf, this));
    this.registerObsidianProtocolHandler("compass-review", (params) =>
      this.onRequest(params.request).catch((e) => this.fail("request", e))
    );
    this.registerEvent(this.app.workspace.on("file-open", () => this.refresh()));
    this.registerEvent(this.app.workspace.on("layout-change", () => this.refresh()));
    this.registerEvent(this.app.vault.on("rename", (file, oldPath) => this.onRename(file, oldPath)));
    this.registerEvent(this.app.vault.on("modify", (file) => this.onModify(file)));
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
    if (!request || typeof request.id !== "string" || typeof request.file !== "string") {
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

  // One live request per file: a newer request for the same file replaces
  // the older one, whose waiter then times out.
  track(request, path) {
    for (const [id, entry] of this.pending) {
      if (entry.request.file === request.file && id !== request.id) this.pending.delete(id);
    }
    const known = this.pending.get(request.id);
    if (known) {
      known.request = request;
      known.path = path;
      return;
    }
    this.pending.set(request.id, { request, path, notes: "", comments: new Map(), edited: new Set() });
  }

  async onRequest(path) {
    if (!path) throw new Error("the compass-review link names no request");
    const request = await this.readRequest(path);
    if (!this.app.vault.getAbstractFileByPath(request.file)) throw new Error(`file not in this vault: ${request.file}`);
    this.track(request, path);
    await this.openPanel();
    await this.showFile(request.file);
    this.raise();
    this.refresh();
  }

  // Brings a file into view: in the pane that already shows it, else in the
  // current pane.
  async showFile(path) {
    const file = this.app.vault.getAbstractFileByPath(path);
    if (!file) throw new Error(`file not in this vault: ${path}`);
    const open = this.app.workspace
      .getLeavesOfType("markdown")
      .find((leaf) => leaf.view.file && leaf.view.file.path === path);
    const leaf = open || this.app.workspace.getLeaf(false);
    await leaf.openFile(file);
    this.app.workspace.setActiveLeaf(leaf, { focus: true });
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

  onRename(file, oldPath) {
    for (const entry of this.pending.values()) {
      if (entry.request.file === oldPath) entry.request.file = file.path;
      if (entry.comments.has(oldPath)) {
        entry.comments.set(file.path, entry.comments.get(oldPath));
        entry.comments.delete(oldPath);
      }
      if (entry.edited.delete(oldPath)) entry.edited.add(file.path);
    }
    this.refresh();
  }

  // An edit belongs to the review of that file, else to the newest review.
  onModify(file) {
    if (!file || typeof file.path !== "string" || !file.path.endsWith(".md")) return;
    const entry = this.entryFor(file.path) || this.newest();
    if (!entry) return;
    entry.edited.add(file.path);
    this.refreshCard(entry);
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
    for (const entry of this.pending.values()) if (entry.request.file === path) return entry;
    return null;
  }

  newest() {
    let target = null;
    for (const entry of this.pending.values()) target = entry;
    return target;
  }

  refresh() {
    this.decorate();
    this.renderPanel();
  }

  // Each markdown pane shows the bar of the review whose file it holds.
  decorate() {
    for (const leaf of this.app.workspace.getLeavesOfType("markdown")) {
      const view = leaf.view;
      const host = view.containerEl;
      const entry = view.file ? this.entryFor(view.file.path) : null;
      const oldBar = host.querySelector(".compass-review-bar");
      if (!entry) {
        if (oldBar) oldBar.remove();
      } else if (!oldBar || oldBar.dataset.id !== entry.request.id) {
        if (oldBar) oldBar.remove();
        host.insertBefore(this.buildBar(entry, view), host.querySelector(".view-content"));
      }
    }
  }

  buildBar(entry, view) {
    const { request } = entry;
    const bar = createDiv({ cls: "compass-review-bar" });
    bar.dataset.id = request.id;
    bar.createSpan({ cls: "compass-review-title", text: `Review: ${request.title || view.file.basename}` });
    const open = bar.createEl("button", { text: "Open review panel" });
    open.onclick = () => this.openPanel().catch((e) => this.fail("open panel", e));
    return bar;
  }

  // Redraws every open panel. A panel whose cards would come out the same is
  // left alone, so a field being typed in keeps its focus and caret.
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
    const otherFor = (entry) => (other && other.path !== entry.request.file ? other : null);
    const signature = JSON.stringify(
      entries.map((entry) => [entry.request.id, entry.request.title, entry.request.file, otherFor(entry) && other.path])
    );
    if (root.dataset.signature === signature) return;
    root.dataset.signature = signature;
    root.empty();
    if (entries.length === 0) {
      root.createDiv({ cls: "compass-review-empty", text: "No reviews pending" });
      return;
    }
    for (const entry of entries) this.buildCard(root, entry, otherFor(entry));
  }

  buildCard(root, entry, other) {
    const { request } = entry;
    const card = root.createDiv({ cls: "compass-review-card" });
    card.dataset.id = request.id;
    card.createDiv({ cls: "compass-review-question", text: request.title || baseName(request.file) });
    const link = card.createEl("a", { cls: "compass-review-file", text: request.file, href: "#" });
    link.addEventListener("click", (event) => {
      event.preventDefault();
      return this.showFile(entry.request.file).catch((e) => this.fail("open file", e));
    });

    const notes = card.createEl("textarea", {
      cls: "compass-review-notes",
      placeholder: "Notes for Claude (optional)",
      attr: { rows: "3" },
    });
    notes.value = entry.notes;
    notes.addEventListener("input", () => {
      entry.notes = notes.value;
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
    }

    const feedback = card.createDiv({ cls: "compass-review-feedback-block" });
    feedback.createDiv({ cls: "compass-review-label", text: "Feedback so far" });
    feedback.createEl("ul", { cls: "compass-review-feedback" });

    const actions = card.createDiv({ cls: "compass-review-actions" });
    const approve = actions.createEl("button", { cls: "mod-cta", text: "Approve" });
    const changes = actions.createEl("button", { cls: "compass-review-changes", text: "Needs changes" });
    approve.onclick = () => this.verdict(entry, "approved").catch((e) => this.fail("verdict", e));
    changes.onclick = () => this.verdict(entry, "changes").catch((e) => this.fail("verdict", e));
    this.fillCard(entry, card);
  }

  hasFeedback(entry) {
    return entry.notes.trim() !== "" || entry.comments.size > 0 || entry.edited.size > 0;
  }

  // One line per note on another file, then one per edited file.
  feedbackItems(entry) {
    return [
      ...[...entry.comments].map(([file, note]) => `${file}: ${note}`),
      ...[...entry.edited].map((file) => `edited: ${file}`),
    ];
  }

  // Brings a card's feedback list and its "Needs changes" gate up to date.
  fillCard(entry, card) {
    const list = card.querySelector(".compass-review-feedback");
    list.empty();
    const items = this.feedbackItems(entry);
    for (const item of items) list.createEl("li", { text: item });
    const block = card.querySelector(".compass-review-feedback-block");
    if (items.length === 0) block.addClass("is-empty");
    else block.removeClass("is-empty");
    card.querySelector(".compass-review-changes").disabled = !this.hasFeedback(entry);
  }

  refreshCard(entry) {
    for (const leaf of this.app.workspace.getLeavesOfType(PANEL_TYPE)) {
      if (!(leaf.view instanceof ReviewPanelView)) continue;
      const card = [...leaf.view.contentEl.querySelectorAll(".compass-review-card")].find(
        (el) => el.dataset.id === entry.request.id
      );
      if (card) this.fillCard(entry, card);
    }
  }

  async verdict(entry, verdict) {
    const { request, path } = entry;
    if (entry.sending) return;
    entry.sending = true;
    // Flush the human's edits before Compass reads the file.
    for (const leaf of this.app.workspace.getLeavesOfType("markdown")) {
      if (leaf.view instanceof MarkdownView && leaf.view.file && leaf.view.file.path === request.file) {
        await leaf.view.save();
      }
    }
    if (!(await this.app.vault.adapter.exists(path))) {
      this.pending.delete(request.id);
      this.refresh();
      new Notice("This review was withdrawn - nothing was sent");
      return;
    }
    const body = {
      id: request.id,
      file: request.file,
      verdict,
      notes: entry.notes,
      comments: [...entry.comments].map(([file, note]) => ({ file, note })),
      edited: [...entry.edited],
      at: new Date().toISOString(),
    };
    await this.app.vault.adapter.write(verdictPathFor(path), JSON.stringify(body, null, 2));
    this.pending.delete(request.id);
    this.refresh();
    new Notice(verdict === "approved" ? "Approved - sent to Claude" : "Changes requested - sent to Claude");
    if (request.return) this.stepAside();
  }
}

module.exports = CompassReview;
module.exports.verdictPathFor = verdictPathFor;

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
//     notes     the note typed on the review bar
//     comments  one note per other file the human annotated from the slim
//               bar (files with an empty note are left out)
//     edited    every markdown file modified in the vault while the review
//               was pending, each listed once
// <dir> is the Compass vault's tmp/review folder: `tmp/review` when the
// Obsidian vault is the Compass vault, `.compass/tmp/review` when the
// Obsidian vault is the project around it. Other review surfaces share the
// folder; a request whose `surface` names another one is theirs.
//
// A request raises the Obsidian window above whatever has focus and opens the
// file with a review bar on top. A click saves the editor, writes the verdict,
// and, when the request says `return`, steps Obsidian aside (minimize, or hide
// on macOS) so focus falls back to the window that had it before.
//
// While a review is pending, any other markdown file shows a slim bar naming
// the most recently opened pending review. It carries a note field for that
// file and a "Back to review" button that reopens the reviewed file in the
// same pane. "Needs changes" is enabled once there is something to send: a
// bar note, a note on another file, or an edit. A periodic recheck drops a
// review whose request file is gone or whose verdict already exists.

const { Plugin, Notice, MarkdownView } = require("obsidian");

const REVIEW_DIRS = ["tmp/review", ".compass/tmp/review"];
const SURFACE = "obsidian";
const RECHECK_MS = 5000;

function electronRemote() {
  const electron = require("electron");
  return electron.remote || require("@electron/remote");
}

function verdictPathFor(requestPath) {
  return requestPath.replace(/\.request\.json$/, ".verdict.json");
}

class CompassReview extends Plugin {
  async onload() {
    // request id -> {request, path, notes, comments: Map(file -> note), edited: Set(path)}
    this.pending = new Map();
    this.lastId = null; // id of the review whose file was opened most recently
    this.registerObsidianProtocolHandler("compass-review", (params) =>
      this.onRequest(params.request).catch((e) => this.fail("request", e))
    );
    this.registerEvent(
      this.app.workspace.on("file-open", (file) => {
        this.noteOpened(file);
        this.decorate();
      })
    );
    this.registerEvent(this.app.workspace.on("layout-change", () => this.decorate()));
    this.registerEvent(this.app.vault.on("rename", (file, oldPath) => this.onRename(file, oldPath)));
    this.registerEvent(this.app.vault.on("modify", (file) => this.onModify(file)));
    this.registerInterval(
      window.setInterval(() => this.recheck().catch((e) => console.error("[compass-review] recheck failed", e)), RECHECK_MS)
    );
    this.app.workspace.onLayoutReady(() => this.scanPending().catch((e) => this.fail("scan", e)));
  }

  onunload() {
    document.querySelectorAll(".compass-review-bar, .compass-review-trail").forEach((el) => el.remove());
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
  // bar without raising the window.
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
    this.decorate();
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
    const file = this.app.vault.getAbstractFileByPath(request.file);
    if (!file) throw new Error(`file not in this vault: ${request.file}`);
    this.track(request, path);
    this.lastId = request.id;
    const open = this.app.workspace
      .getLeavesOfType("markdown")
      .find((leaf) => leaf.view.file && leaf.view.file.path === request.file);
    const leaf = open || this.app.workspace.getLeaf(false);
    await leaf.openFile(file);
    this.app.workspace.setActiveLeaf(leaf, { focus: true });
    this.raise();
    this.decorate();
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
    this.decorate();
  }

  // An edit belongs to the review of that file, else to the review the slim
  // bar names.
  onModify(file) {
    if (!file || typeof file.path !== "string" || !file.path.endsWith(".md")) return;
    const entry = this.entryFor(file.path) || this.trailTarget();
    if (!entry) return;
    entry.edited.add(file.path);
    this.refreshGate(entry);
  }

  noteOpened(file) {
    const entry = file ? this.entryFor(file.path) : null;
    if (entry) this.lastId = entry.request.id;
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
    this.decorate();
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

  // The review the slim bar names: the one whose file was opened last, else
  // the most recently tracked.
  trailTarget() {
    const last = this.pending.get(this.lastId);
    if (last) return last;
    let target = null;
    for (const entry of this.pending.values()) target = entry;
    return target;
  }

  decorate() {
    const target = this.trailTarget();
    for (const leaf of this.app.workspace.getLeavesOfType("markdown")) {
      const view = leaf.view;
      const host = view.containerEl;
      const file = view.file;
      const entry = file ? this.entryFor(file.path) : null;

      const oldBar = host.querySelector(".compass-review-bar");
      if (!entry) {
        if (oldBar) oldBar.remove();
      } else if (!oldBar || oldBar.dataset.id !== entry.request.id) {
        if (oldBar) oldBar.remove();
        host.insertBefore(this.buildBar(entry, view), host.querySelector(".view-content"));
      }

      const oldTrail = host.querySelector(".compass-review-trail");
      const key = file && !entry && target ? `${target.request.id}|${file.path}` : null;
      if (!key) {
        if (oldTrail) oldTrail.remove();
      } else if (!oldTrail || oldTrail.dataset.key !== key) {
        if (oldTrail) oldTrail.remove();
        host.insertBefore(this.buildTrail(target, leaf, file), host.querySelector(".view-content"));
      }
    }
  }

  buildBar(entry, view) {
    const { request } = entry;
    const bar = createDiv({ cls: "compass-review-bar" });
    bar.dataset.id = request.id;
    bar.createSpan({ cls: "compass-review-title", text: `Review: ${request.title || view.file.basename}` });
    const notes = bar.createEl("input", { type: "text", placeholder: "Notes for Claude (optional)" });
    notes.value = entry.notes;
    notes.addEventListener("input", () => {
      entry.notes = notes.value;
      this.refreshGate(entry);
    });
    const approve = bar.createEl("button", { cls: "mod-cta", text: "Approve" });
    const changes = bar.createEl("button", { cls: "compass-review-changes", text: "Needs changes" });
    changes.disabled = !this.hasFeedback(entry);
    approve.onclick = () => this.verdict(entry, "approved", notes.value).catch((e) => this.fail("verdict", e));
    changes.onclick = () => this.verdict(entry, "changes", notes.value).catch((e) => this.fail("verdict", e));
    return bar;
  }

  buildTrail(entry, leaf, file) {
    const { request } = entry;
    const trail = createDiv({ cls: "compass-review-trail" });
    trail.dataset.key = `${request.id}|${file.path}`;
    trail.createSpan({ cls: "compass-review-title", text: `Review: ${request.title || request.file}` });
    const note = trail.createEl("input", {
      cls: "compass-review-file-note",
      type: "text",
      placeholder: "Note on this file for Claude",
    });
    note.value = entry.comments.get(file.path) || "";
    note.addEventListener("input", () => {
      if (note.value.trim()) entry.comments.set(file.path, note.value);
      else entry.comments.delete(file.path);
      this.refreshGate(entry);
    });
    const back = trail.createEl("button", { text: "Back to review" });
    back.onclick = () => this.goBack(entry, leaf).catch((e) => this.fail("back to review", e));
    return trail;
  }

  async goBack(entry, leaf) {
    const file = this.app.vault.getAbstractFileByPath(entry.request.file);
    if (!file) throw new Error(`file not in this vault: ${entry.request.file}`);
    this.lastId = entry.request.id;
    await leaf.openFile(file);
    this.decorate();
  }

  hasFeedback(entry) {
    return entry.notes.trim() !== "" || entry.comments.size > 0 || entry.edited.size > 0;
  }

  // "Needs changes" is enabled while the review has anything to send.
  refreshGate(entry) {
    for (const leaf of this.app.workspace.getLeavesOfType("markdown")) {
      const bar = leaf.view.containerEl.querySelector(".compass-review-bar");
      if (!bar || bar.dataset.id !== entry.request.id) continue;
      const changes = bar.querySelector(".compass-review-changes");
      if (changes) changes.disabled = !this.hasFeedback(entry);
    }
  }

  async verdict(entry, verdict, notes) {
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
      this.decorate();
      new Notice("This review was withdrawn - nothing was sent");
      return;
    }
    const body = {
      id: request.id,
      file: request.file,
      verdict,
      notes,
      comments: [...entry.comments].map(([file, note]) => ({ file, note })),
      edited: [...entry.edited],
      at: new Date().toISOString(),
    };
    await this.app.vault.adapter.write(verdictPathFor(path), JSON.stringify(body, null, 2));
    this.pending.delete(request.id);
    this.decorate();
    new Notice(verdict === "approved" ? "Approved - sent to Claude" : "Changes requested - sent to Claude");
    if (request.return) this.stepAside();
  }
}

module.exports = CompassReview;
module.exports.verdictPathFor = verdictPathFor;

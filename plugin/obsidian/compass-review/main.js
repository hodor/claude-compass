// Compass Review: puts the document Compass asks the human to review in front
// of him, and hands his verdict back.
//
// Protocol (paths relative to the Obsidian vault root, forward slashes):
//   <dir>/<id>.request.json   written by Compass:
//     {"id", "surface"?, "file", "title"?, "return": bool}
//   obsidian://compass-review?vault=<vault id>&request=<dir>/<id>.request.json
//   <dir>/<id>.verdict.json   written here when a button is clicked:
//     {"id", "file", "verdict": "approved"|"changes", "notes", "at"}
// <dir> is the Compass vault's tmp/review folder: `tmp/review` when the
// Obsidian vault is the Compass vault, `.compass/tmp/review` when the
// Obsidian vault is the project around it. Other review surfaces share the
// folder; a request whose `surface` names another one is theirs.
//
// A request raises the Obsidian window above whatever has focus and opens the
// file with a review bar on top. A click saves the editor, writes the verdict,
// and, when the request says `return`, steps Obsidian aside (minimize, or hide
// on macOS) so focus falls back to the window that had it before.

const { Plugin, Notice, MarkdownView } = require("obsidian");

const REVIEW_DIRS = ["tmp/review", ".compass/tmp/review"];
const SURFACE = "obsidian";

function electronRemote() {
  const electron = require("electron");
  return electron.remote || require("@electron/remote");
}

function verdictPathFor(requestPath) {
  return requestPath.replace(/\.request\.json$/, ".verdict.json");
}

class CompassReview extends Plugin {
  async onload() {
    this.pending = new Map(); // request id -> {request, path}
    this.registerObsidianProtocolHandler("compass-review", (params) =>
      this.onRequest(params.request).catch((e) => this.fail("request", e))
    );
    this.registerEvent(this.app.workspace.on("file-open", () => this.decorate()));
    this.registerEvent(this.app.workspace.on("layout-change", () => this.decorate()));
    this.registerEvent(this.app.vault.on("rename", (file, oldPath) => this.onRename(file, oldPath)));
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
    this.pending.set(request.id, { request, path });
  }

  async onRequest(path) {
    if (!path) throw new Error("the compass-review link names no request");
    const request = await this.readRequest(path);
    const file = this.app.vault.getAbstractFileByPath(request.file);
    if (!file) throw new Error(`file not in this vault: ${request.file}`);
    this.track(request, path);
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
    }
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

  decorate() {
    for (const leaf of this.app.workspace.getLeavesOfType("markdown")) {
      const view = leaf.view;
      const host = view.containerEl;
      const old = host.querySelector(".compass-review-bar");
      const entry = view.file ? this.entryFor(view.file.path) : null;
      if (!entry) {
        if (old) old.remove();
        continue;
      }
      if (old && old.dataset.id === entry.request.id) continue;
      if (old) old.remove();
      host.insertBefore(this.buildBar(entry, view), host.querySelector(".view-content"));
    }
  }

  buildBar(entry, view) {
    const { request } = entry;
    const bar = createDiv({ cls: "compass-review-bar" });
    bar.dataset.id = request.id;
    bar.createSpan({ cls: "compass-review-title", text: `Review: ${request.title || view.file.basename}` });
    const notes = bar.createEl("input", { type: "text", placeholder: "Notes for Claude (optional)" });
    const approve = bar.createEl("button", { cls: "mod-cta", text: "Approve" });
    const changes = bar.createEl("button", { text: "Needs changes" });
    approve.onclick = () => this.verdict(entry, "approved", notes.value).catch((e) => this.fail("verdict", e));
    changes.onclick = () => this.verdict(entry, "changes", notes.value).catch((e) => this.fail("verdict", e));
    return bar;
  }

  async verdict(entry, verdict, notes) {
    const { request, path } = entry;
    // Flush the human's edits before Compass reads the file.
    for (const leaf of this.app.workspace.getLeavesOfType("markdown")) {
      if (leaf.view instanceof MarkdownView && leaf.view.file && leaf.view.file.path === request.file) {
        await leaf.view.save();
      }
    }
    const body = { id: request.id, file: request.file, verdict, notes, at: new Date().toISOString() };
    await this.app.vault.adapter.write(verdictPathFor(path), JSON.stringify(body, null, 2));
    this.pending.delete(request.id);
    this.decorate();
    new Notice(verdict === "approved" ? "Approved - sent to Claude" : "Changes requested - sent to Claude");
    if (request.return) this.stepAside();
  }
}

module.exports = CompassReview;
module.exports.verdictPathFor = verdictPathFor;

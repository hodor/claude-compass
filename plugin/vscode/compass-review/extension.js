// Compass Review for VS Code and Cursor: puts the documents Compass asks the
// human to review in front of him in a panel beside the editor, and hands his
// verdict back.
//
// Protocol (paths relative to the workspace folder that holds the vault, forward
// slashes):
//   <folder>/.compass/tmp/review/<id>.request.json   written by Compass:
//     {"id", "surface": "vscode"|"cursor", "file", "title"?, "return": bool,
//      "files"?: [{"file", "why"}], "project"?, "session"?}
//     files     the documents of a review in walking order, each with a
//               one-line reason; absent for a review of one document
//     project   name of the project the request came from
//     session   id of the Claude Code session that asked
//   <folder>/.compass/tmp/review/<id>.verdict.json   written here when a button
//   is clicked:
//     {"id", "file", "verdict": "approved"|"changes", "notes",
//      "comments": [{"file", "note"}], "edited": [path],
//      "files"?: [{"file", "read", "verdict", "note"?, "index"?}], "at"}
//     file      the first listed document
//     notes     the note typed for the reviewed document; for several
//               documents, one `<name>: <note>` line per noted document
//     comments  one note per file outside the review that the human annotated
//               from the card (empty notes are left out)
//     edited    every file of the review typed in while it was pending, each
//               listed once; an edit counts when the editor reports content
//               changes in the listed file whose editor is in front while the
//               window has focus, so writes from other programs are not listed
//     files     for several documents only: every listed document in request
//               order with its read mark, its own verdict ("approved" or
//               "changes") and its note, when it has one; the top-level
//               verdict is "approved" when every file is approved, else
//               "changes"
//   <folder>/.compass/tmp/review/<id>.verdict.<n>.json   written here instead
//   when a button answers some documents of a several-document review and
//   leaves others open: the same shape, `files` listing only the answered
//   documents, each entry carrying `index`, the document's 0-based position in
//   the request's `files`; `<n>` is the lowest `index` in it. `comments` carries
//   the notes on outside files not sent before, `edited` the answered documents
//   typed in. The review is answered once `<id>.verdict.json` exists or the
//   `<n>` files cover every document.
//   <folder>/.compass/tmp/review/<id>.seen   written here, empty, when a
//   request is first taken up; tells Compass an editor window holds it
// Other review surfaces share the folder; a request whose `surface` is not
// `vscode` or `cursor` is theirs.
//
// Every window of the editor runs this extension and claims the requests under
// the vault of each workspace folder it has open: the ones waiting when it
// starts and the ones that arrive later. A new request reveals the review panel
// and opens the first file. Under the heading "Reviews waiting on you" the panel
// holds one card per pending review, newest first. A card shows the question (the
// request title, else the first file's name), the project and the first six
// characters of the session, "File i of n" with Previous, Next and Next unread
// (and the Left and Right arrow keys while the card has focus), one row per file
// with its read mark, title, reason and note count, and a note field for the file
// the walk is on. A file is marked read when it opens, whether the card opened it
// or the human did. While a markdown file outside the review is the active
// editor, the card also shows an "On this file" note field for that file. A
// summary line counts the files read and the notes. A card for one document
// ends with one Approve and one "Needs changes"; "Needs changes" is enabled once
// there is something to send: a note on the file or an outside file, or an edit.
// A card for several documents gives each row its own note field, Approve and
// "Needs changes"; a click sends that document's verdict with its note at once
// and the other rows stay open. "Needs changes" on a row is enabled once the row
// has a note or an edit. The card ends with Approve all, which approves the rows
// not yet sent that carry no note. A newer request that lists an unsent file of
// an older one in the same folder replaces it.
//
// The walk, the notes and the marks live here, not in the page, so the panel
// being hidden, closed and opened again loses nothing. The page announces itself
// when it loads and receives the whole state; it sends back the human's actions.
// A click on a button that ends the review saves the listed editors that have
// unsaved text and writes the verdict. A periodic recheck drops a review whose request
// file is gone or whose verdict already exists, and finds requests the file
// watcher missed. The recheck also looks beside the running extension's folder
// for a copy of the same extension at a higher version; when one is installed,
// an information message offers to reload the window, once per version.

"use strict";

const vscode = require("vscode");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const VIEW_ID = "compassReview.panel";
const CONTAINER_COMMAND = "workbench.view.extension.compassReview";
const REVEAL_COMMAND = "compassReview.reveal";
const REVIEW_PARTS = [".compass", "tmp", "review"];
const REQUEST_SUFFIX = ".request.json";
const SURFACES = new Set(["vscode", "cursor"]);
const RECHECK_MS = 5000;
const RELOAD_COMMAND = "workbench.action.reloadWindow";
const RELOAD_LABEL = "Reload";

const VERDICTS = ["approved", "changes"];

const CASE_BLIND = process.platform === "win32" || process.platform === "darwin";

// A file path in the form that compares equal for the same file.
function fileKey(file) {
  const normal = path.normalize(String(file));
  return CASE_BLIND ? normal.toLowerCase() : normal;
}

function sameFile(a, b) {
  return fileKey(a) === fileKey(b);
}

function baseName(file) {
  return file.split("/").pop().replace(/\.md$/, "");
}

// The mark, note, own verdict (null until sent) and whether it was sent, for one
// listed file.
function newState() {
  return { read: false, note: "", verdict: null, sent: false };
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function verdictPathFor(requestPath) {
  return requestPath.replace(/\.request\.json$/, ".verdict.json");
}

// The `<id>.verdict.<n>.json` file answering the documents from position `n`.
function partialPathFor(requestPath, n) {
  return requestPath.replace(/\.request\.json$/, `.verdict.${n}.json`);
}

// The answers to some documents of a request, as `[{n, answer}]`: every
// `<id>.verdict.<n>.json` beside it that parses.
function partialAnswers(requestPath) {
  const dir = path.dirname(requestPath);
  const prefix = path.basename(requestPath).replace(/\.request\.json$/, ".verdict.");
  const found = [];
  let names = [];
  try {
    names = fs.readdirSync(dir);
  } catch (e) {
    return found;
  }
  for (const name of names) {
    const named = name.startsWith(prefix) && /^(\d+)\.json$/.exec(name.slice(prefix.length));
    if (!named) continue;
    try {
      const answer = JSON.parse(fs.readFileSync(path.join(dir, name), "utf8"));
      if (answer && Array.isArray(answer.files)) found.push({ n: Number(named[1]), answer });
    } catch (e) {
      // a file still being written is read on the next look
    }
  }
  return found.sort((a, b) => a.n - b.n);
}

// The positions of the documents the `<id>.verdict.<n>.json` files answer.
function answeredPositions(requestPath, count) {
  const covered = new Set();
  for (const { answer } of partialAnswers(requestPath)) {
    for (const item of answer.files) {
      if (item && Number.isInteger(item.index) && item.index >= 0 && item.index < count) covered.add(item.index);
    }
  }
  return covered;
}

// Whether a request with `count` documents is answered: its `<id>.verdict.json`
// exists, or the `<n>` files cover every document of a several-document review.
function isAnswered(requestPath, count) {
  if (exists(verdictPathFor(requestPath))) return true;
  return count > 1 && answeredPositions(requestPath, count).size >= count;
}

// The empty file written beside a request once this extension has taken it up.
function seenPathFor(requestPath) {
  return requestPath.replace(/\.request\.json$/, ".seen");
}

// A path from the workspace folder: relative, without parent steps.
function isFolderRelative(file) {
  return typeof file === "string" && file !== "" && !path.isAbsolute(file) && !file.split(/[\\/]/).includes("..");
}

// The documents a request lists, in walking order; a request without a `files`
// list reviews its one `file`.
function filesOf(request) {
  if (Array.isArray(request.files) && request.files.length > 0) {
    return request.files.map((f) => ({ file: f.file, why: typeof f.why === "string" ? f.why : "" }));
  }
  return [{ file: request.file, why: "" }];
}

// The parsed request at `file`; null when it belongs to another surface. Throws
// when the file is not a well-formed request.
function readRequest(file) {
  const request = JSON.parse(fs.readFileSync(file, "utf8"));
  const listed = request && request.files;
  const badFiles = listed !== undefined && !(Array.isArray(listed) && listed.every((f) => f && isFolderRelative(f.file)));
  if (!request || typeof request.id !== "string" || !request.id || !isFolderRelative(request.file) || badFiles) {
    throw new Error(`malformed request ${file}`);
  }
  return SURFACES.has(request.surface) ? request : null;
}

// The numeric parts of a dotted version; null when it is not `N.N.N...`.
function versionParts(version) {
  const text = String(version);
  return /^\d+(\.\d+)*$/.test(text) ? text.split(".").map(Number) : null;
}

// Negative, zero or positive as version `a` is below, equal to or above `b`,
// compared part by part as numbers.
function compareVersions(a, b) {
  const left = versionParts(a);
  const right = versionParts(b);
  const length = Math.max(left.length, right.length);
  for (let i = 0; i < length; i++) {
    const diff = (left[i] || 0) - (right[i] || 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

// The highest version among the copies of extension `id` installed beside
// `extensionPath` (folders named `<id>-<version>`); null when there is none.
// Folders of other extensions, `<id>-<word>` names and plain files are skipped.
function highestInstalledVersion(extensionPath, id) {
  const prefix = `${id}-`.toLowerCase();
  let best = null;
  for (const entry of fs.readdirSync(path.dirname(extensionPath), { withFileTypes: true })) {
    if (!entry.isDirectory() || !entry.name.toLowerCase().startsWith(prefix)) continue;
    const version = entry.name.slice(prefix.length).replace(/-.*$/, "");
    if (versionParts(version) && (best === null || compareVersions(version, best) > 0)) best = version;
  }
  return best;
}

function exists(file) {
  try {
    fs.accessSync(file);
    return true;
  } catch (e) {
    return false;
  }
}

class CompassReview {
  constructor(context) {
    this.context = context;
    // request id -> {request, path, folder, files: [{file, why}], states:
    // Map(file -> {read, note, verdict}), index, comments: Map(file outside the review ->
    // note), edited: Set(path), sending} in arrival order; the panel lists it
    // newest first.
    this.reviews = new Map();
    // Ids of reviews that were answered or replaced; their request files are not
    // claimed again.
    this.retired = new Set();
    // Request files that failed to parse, with their modification time, so a
    // damaged file is reported once.
    this.bad = new Map();
    this.titles = new Map();
    this.watchers = new Map();
    this.view = null;
    this.visiting = null;
    this.queue = Promise.resolve();
    this.output = null;
    this.timer = null;
    // The highest installed version a reload was offered for.
    this.announced = null;
  }

  // -- start and stop --

  start() {
    const subscriptions = this.context.subscriptions;
    subscriptions.push(
      vscode.window.registerWebviewViewProvider(VIEW_ID, { resolveWebviewView: (view) => this.resolveView(view) }),
      vscode.window.onDidChangeActiveTextEditor((editor) => this.onActiveEditor(editor)),
      vscode.workspace.onDidChangeTextDocument((event) => this.onDocumentChange(event)),
      vscode.workspace.onDidSaveTextDocument((doc) => this.onDocumentSave(doc)),
      vscode.workspace.onDidChangeWorkspaceFolders(() => this.refreshFolders()),
      vscode.commands.registerCommand(REVEAL_COMMAND, () => this.reveal())
    );
    this.timer = setInterval(() => this.recheck(), RECHECK_MS);
    if (this.timer.unref) this.timer.unref();
    subscriptions.push({ dispose: () => this.dispose() });
    this.refreshFolders();
  }

  dispose() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    for (const watcher of this.watchers.values()) watcher.dispose();
    this.watchers.clear();
  }

  log(message) {
    try {
      this.output = this.output || vscode.window.createOutputChannel("Compass Review");
      this.output.appendLine(message);
    } catch (e) {
      // the log is a convenience; a failed write changes nothing on screen
    }
  }

  fail(where, err) {
    const message = (err && err.message) || String(err);
    this.log(`${where} failed: ${message}`);
    vscode.window.showErrorMessage(`Compass Review: ${where} failed - ${message}`);
  }

  // -- finding requests --

  folders() {
    return (vscode.workspace.workspaceFolders || []).map((f) => f.uri.fsPath);
  }

  reviewDir(folder) {
    return path.join(folder, ...REVIEW_PARTS);
  }

  // Watches the review folder of each workspace folder and claims what is
  // already waiting there.
  refreshFolders() {
    const folders = this.folders();
    for (const [folder, watcher] of [...this.watchers]) {
      if (!folders.some((f) => sameFile(f, folder))) {
        watcher.dispose();
        this.watchers.delete(folder);
      }
    }
    for (const folder of folders) {
      if (![...this.watchers.keys()].some((f) => sameFile(f, folder))) this.watchers.set(folder, this.watch(folder));
    }
    this.scan().forEach((entry) => this.present(entry));
  }

  watch(folder) {
    const watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(folder, "**/.compass/tmp/review/*" + REQUEST_SUFFIX)
    );
    const seen = (uri) => {
      const found = this.claimFile(uri.fsPath);
      if (found && found.isNew) this.present(found.entry);
      else if (found) this.push();
    };
    watcher.onDidCreate(seen);
    watcher.onDidChange(seen);
    watcher.onDidDelete((uri) => this.onGone(uri.fsPath));
    return watcher;
  }

  // The workspace folder a request file sits under, else null.
  folderOf(requestPath) {
    const review = path.dirname(requestPath);
    const folder = path.resolve(review, "..", "..", "..");
    const shaped = sameFile(review, this.reviewDir(folder));
    return shaped ? this.folders().find((f) => sameFile(f, folder)) || null : null;
  }

  // Claims the request at `file` when it is a pending request for this editor:
  // `{entry, isNew}`, else null.
  claimFile(file) {
    if (!file.endsWith(REQUEST_SUFFIX)) return null;
    const folder = this.folderOf(file);
    if (!folder || exists(verdictPathFor(file))) return null;
    let request;
    try {
      request = readRequest(file);
    } catch (e) {
      this.noteBad(file, e);
      return null;
    }
    if (!request || this.retired.has(request.id) || isAnswered(file, filesOf(request).length)) return null;
    const isNew = !this.reviews.has(request.id);
    return { entry: this.track(request, file, folder), isNew };
  }

  noteBad(file, err) {
    let stamp = 0;
    try {
      stamp = fs.statSync(file).mtimeMs;
    } catch (e) {
      return;
    }
    if (this.bad.get(file) === stamp) return;
    this.bad.set(file, stamp);
    this.log(`skipped ${file}: ${err.message}`);
  }

  // A newer request that lists any file of an older one in the same folder
  // replaces it; what the human wrote on files both list carries over.
  track(request, file, folder) {
    const files = filesOf(request);
    const known = this.reviews.get(request.id);
    if (known) {
      known.request = request;
      known.path = file;
      known.files = files;
      for (const f of files) if (!known.states.has(f.file)) known.states.set(f.file, newState());
      known.index = Math.min(known.index, files.length - 1);
      return known;
    }
    const replaced = [];
    for (const [id, old] of this.reviews) {
      const holds = (f) => old.files.some((o) => o.file === f.file && !old.states.get(o.file).sent);
      if (old.folder === folder && files.some(holds)) {
        replaced.push(old);
        this.reviews.delete(id);
        this.retired.add(id);
      }
    }
    const entry = {
      request,
      path: file,
      folder,
      files,
      states: new Map(files.map((f) => [f.file, newState()])),
      index: 0,
      comments: new Map(),
      carriedComments: new Map(),
      edited: new Set(),
      sending: false,
    };
    for (const old of replaced) {
      for (const f of files) {
        if (old.states.has(f.file) && !old.states.get(f.file).sent) entry.states.set(f.file, old.states.get(f.file));
      }
      for (const [name, note] of old.comments) entry.comments.set(name, note);
      for (const [name, note] of old.carriedComments) entry.carriedComments.set(name, note);
      for (const name of old.edited) entry.edited.add(name);
    }
    this.restoreSent(entry);
    this.reviews.set(request.id, entry);
    this.markSeen(file);
    return entry;
  }

  // Marks the documents that `<id>.verdict.<n>.json` files already answer as
  // sent, with the verdict each was sent with, so a window opened later shows
  // them settled.
  restoreSent(entry) {
    if (entry.files.length < 2) return;
    for (const { answer } of partialAnswers(entry.path)) {
      for (const item of answer.files) {
        const target = Number.isInteger(item.index) ? entry.files[item.index] : null;
        if (!target || !VERDICTS.includes(item.verdict)) continue;
        const state = entry.states.get(target.file);
        state.sent = true;
        state.verdict = item.verdict;
        state.read = state.read || item.read === true;
        state.note = typeof item.note === "string" ? item.note : state.note;
      }
    }
  }

  // Writes `<id>.seen` beside a request this extension has just taken up, so
  // `compass review` knows an editor window holds it. A failed write is logged.
  markSeen(requestFile) {
    try {
      fs.writeFileSync(seenPathFor(requestFile), "");
    } catch (e) {
      this.log(`could not write ${seenPathFor(requestFile)}: ${(e && e.message) || e}`);
    }
  }

  // Claims every request waiting in the review folders; returns the new ones.
  scan() {
    const fresh = [];
    for (const folder of this.folders()) {
      let names = [];
      try {
        names = fs.readdirSync(this.reviewDir(folder)).sort();
      } catch (e) {
        continue;
      }
      for (const name of names) {
        const found = this.claimFile(path.join(this.reviewDir(folder), name));
        if (found && found.isNew) fresh.push(found.entry);
      }
    }
    return fresh;
  }

  onGone(file) {
    for (const [id, entry] of this.reviews) {
      if (sameFile(entry.path, file)) this.reviews.delete(id);
    }
    this.push();
  }

  // Drops reviews whose request file was removed or whose verdict another
  // surface already wrote, claims requests no watcher event announced, and
  // offers a window reload once a newer copy of this extension is installed.
  recheck() {
    try {
      for (const [id, entry] of this.reviews) {
        if (!exists(entry.path) || isAnswered(entry.path, entry.files.length)) this.reviews.delete(id);
      }
      this.scan().forEach((entry) => this.present(entry));
      this.push();
    } catch (e) {
      this.log(`recheck failed: ${(e && e.message) || e}`);
    }
    this.offerReload();
  }

  // Shows "Compass Review <v> is installed" with a Reload button when a copy of
  // this extension at a higher version than the running one sits in the
  // extensions folder; each version is announced once, and only a version above
  // the last announced one is announced again.
  offerReload() {
    try {
      const extension = this.context.extension;
      const running = extension.packageJSON.version;
      const installed = highestInstalledVersion(this.context.extensionPath, extension.id);
      if (!versionParts(running) || installed === null || compareVersions(installed, running) <= 0) return;
      if (this.announced && compareVersions(installed, this.announced) <= 0) return;
      this.announced = installed;
      Promise.resolve(
        vscode.window.showInformationMessage(`Compass Review ${installed} is installed. Reload this window to use it.`, RELOAD_LABEL)
      )
        .then((choice) => (choice === RELOAD_LABEL ? vscode.commands.executeCommand(RELOAD_COMMAND) : undefined))
        .catch((e) => this.log(`reload offer failed: ${(e && e.message) || e}`));
    } catch (e) {
      this.log(`reload offer failed: ${(e && e.message) || e}`);
    }
  }

  // -- showing a review --

  // Reveals the panel and opens the first file of a review that just arrived,
  // one review at a time.
  present(entry) {
    this.queue = this.queue
      .then(async () => {
        if (this.reviews.get(entry.request.id) !== entry) return;
        await this.reveal();
        await this.visit(entry, 0);
      })
      .catch((e) => this.fail("show review", e));
    return this.queue;
  }

  async reveal() {
    try {
      await vscode.commands.executeCommand(CONTAINER_COMMAND);
    } catch (e) {
      this.log(`reveal failed: ${(e && e.message) || e}`);
    }
  }

  resolveView(view) {
    this.view = view;
    const media = vscode.Uri.joinPath(this.context.extensionUri, "media");
    view.webview.options = { enableScripts: true, localResourceRoots: [media] };
    view.webview.html = this.pageHtml(view.webview);
    view.webview.onDidReceiveMessage((msg) => this.onMessage(msg));
    view.onDidChangeVisibility(() => {
      if (view.visible) this.push();
    });
    view.onDidDispose(() => {
      if (this.view === view) this.view = null;
    });
  }

  pageHtml(webview) {
    const nonce = crypto.randomBytes(16).toString("base64");
    const asset = (name) => webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, "media", name));
    const policy = `default-src 'none'; style-src ${webview.cspSource}; script-src 'nonce-${nonce}';`;
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${policy}">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="${asset("card.css")}">
<title>Compass Review</title>
</head>
<body>
<div id="root"></div>
<script nonce="${nonce}" src="${asset("card.js")}"></script>
</body>
</html>`;
  }

  push() {
    if (!this.view || !this.view.visible) return;
    const cards = [...this.reviews.values()].reverse().map((entry) => this.snapshot(entry));
    Promise.resolve(this.view.webview.postMessage({ type: "state", cards })).catch(() => {});
  }

  // -- the files of a review --

  absolute(entry, rel) {
    return path.join(entry.folder, ...rel.split("/"));
  }

  // The listed file an editor path is, else null.
  listedFile(entry, fsPath) {
    const found = entry.files.find((f) => sameFile(this.absolute(entry, f.file), fsPath));
    return found ? found.file : null;
  }

  // `fsPath` as a path from the review's folder with forward slashes, else null.
  relativeTo(entry, fsPath) {
    const rel = path.relative(entry.folder, fsPath);
    if (!rel || rel.startsWith("..") || path.isAbsolute(rel)) return null;
    return rel.split(path.sep).join("/");
  }

  // The markdown file in the active editor when it is outside the review.
  outsideFor(entry) {
    const editor = vscode.window.activeTextEditor;
    const doc = editor && editor.document;
    if (!doc || doc.uri.scheme !== "file") return null;
    if (doc.languageId !== "markdown" && !/\.md$/i.test(doc.fileName || "")) return null;
    if (this.listedFile(entry, doc.uri.fsPath)) return null;
    return this.relativeTo(entry, doc.uri.fsPath);
  }

  // The `title` property of a file, else its name.
  titleOf(entry, rel) {
    const file = this.absolute(entry, rel);
    const key = fileKey(file);
    if (!this.titles.has(key)) {
      let title = baseName(rel);
      try {
        const head = fs.readFileSync(file, "utf8").slice(0, 2000);
        const block = /^---\r?\n([\s\S]*?)\r?\n---/.exec(head);
        const found = block && /^title:\s*"?(.+?)"?\s*$/m.exec(block[1]);
        if (found && found[1].trim()) title = found[1].trim();
      } catch (e) {
        // an unreadable file keeps its name
      }
      this.titles.set(key, title);
    }
    return this.titles.get(key);
  }

  onDocumentSave(doc) {
    this.titles.delete(fileKey(doc.uri.fsPath));
    this.push();
  }

  // Opens a file in the editor group that already shows it, else in the active
  // group. The panel keeps keyboard focus so the arrow keys go on working.
  async showFile(entry, rel) {
    const target = this.absolute(entry, rel);
    const shown = vscode.window.visibleTextEditors.find((e) => sameFile(e.document.uri.fsPath, target));
    await vscode.window.showTextDocument(vscode.Uri.file(target), {
      viewColumn: shown ? shown.viewColumn : undefined,
      preserveFocus: true,
      preview: false,
    });
  }

  // Opens file `i` of a review and moves its walk there, marking it read.
  async visit(entry, i) {
    const target = Number.isInteger(i) ? entry.files[i] : null;
    if (!target) return;
    this.visiting = entry;
    try {
      await this.showFile(entry, target.file);
    } finally {
      if (this.visiting === entry) this.visiting = null;
    }
    this.markVisited(entry, target.file);
    this.push();
  }

  markVisited(entry, rel) {
    const i = entry.files.findIndex((f) => f.file === rel);
    if (i < 0) return;
    entry.index = i;
    entry.states.get(rel).read = true;
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

  // -- what the human does in the editor --

  // A text editor coming into view: a listed file is marked read and becomes the
  // one its review's walk is on. A file a card opened moves that card's walk only.
  onActiveEditor(editor) {
    if (editor && editor.document.uri.scheme === "file") {
      for (const entry of this.visiting ? [this.visiting] : this.reviews.values()) {
        const rel = this.listedFile(entry, editor.document.uri.fsPath);
        if (rel) this.markVisited(entry, rel);
      }
    }
    this.push();
  }

  // Typing is a content change to a listed file whose editor is in front while
  // the window has focus. It lands on every pending review that lists the file.
  onDocumentChange(event) {
    if (event.contentChanges.length === 0 || event.document.uri.scheme !== "file") return;
    if (!vscode.window.state.focused) return;
    const active = vscode.window.activeTextEditor;
    if (!active || !sameFile(active.document.uri.fsPath, event.document.uri.fsPath)) return;
    let changed = false;
    for (const entry of this.reviews.values()) {
      const rel = this.listedFile(entry, event.document.uri.fsPath);
      if (rel && !entry.edited.has(rel)) {
        entry.edited.add(rel);
        changed = true;
      }
    }
    if (changed) this.push();
  }

  // -- the card's state --

  noteCount(entry) {
    return entry.files.filter((f) => entry.states.get(f.file).note.trim() !== "").length;
  }

  hasFeedback(entry) {
    return this.noteCount(entry) > 0 || entry.comments.size > 0 || entry.edited.size > 0;
  }

  // Whether one file has something for Claude to act on: a note or an edit.
  fileHasFeedback(entry, file) {
    return entry.states.get(file).note.trim() !== "" || entry.edited.has(file);
  }

  // The positions Approve all approves: the rows not yet sent that carry no
  // note. A row with a note is the human's answer in progress and stays open.
  approvableRows(entry) {
    const rows = [];
    entry.files.forEach((f, i) => {
      const state = entry.states.get(f.file);
      if (!state.sent && state.note.trim() === "") rows.push(i);
    });
    return rows;
  }

  // One line per note on a file outside the review, then one per edited file.
  feedbackItems(entry) {
    return [
      ...[...entry.comments].map(([file, note]) => `${file}: ${note}`),
      ...[...entry.edited].map((file) => `edited: ${file}`),
    ];
  }

  // The request's project, else the folder holding the vault.
  projectOf(entry) {
    const named = entry.request.project;
    return typeof named === "string" && named ? named : path.basename(entry.folder);
  }

  snapshot(entry) {
    const { request } = entry;
    const n = entry.files.length;
    const current = entry.files[entry.index];
    const outside = this.outsideFor(entry);
    const read = entry.files.filter((f) => entry.states.get(f.file).read).length;
    let summary = `${read} of ${n} files read, ${plural(this.noteCount(entry), "note")}`;
    if (entry.comments.size) summary += `, ${plural(entry.comments.size, "note")} on files outside the review`;
    const title = typeof request.title === "string" ? request.title.trim() : "";
    return {
      id: request.id,
      question: title || baseName(entry.files[0].file),
      project: this.projectOf(entry),
      session: typeof request.session === "string" ? request.session.slice(0, 6) : "",
      files: entry.files.map((f) => {
        const state = entry.states.get(f.file);
        return {
          title: this.titleOf(entry, f.file),
          why: f.why,
          read: state.read,
          hasNote: state.note.trim() !== "",
          note: state.note,
          verdict: state.verdict,
          sent: state.sent,
          canChanges: this.fileHasFeedback(entry, f.file),
        };
      }),
      index: entry.index,
      noteLabel: `Note on ${this.titleOf(entry, current.file)}`,
      note: entry.states.get(current.file).note,
      outside,
      outsideNote: outside ? entry.comments.get(outside) || "" : "",
      summary,
      feedback: this.feedbackItems(entry),
      canNextUnread: this.nextUnreadIndex(entry) >= 0,
      canChanges: this.hasFeedback(entry),
      canApproveAll: entry.files.length > 1 && this.approvableRows(entry).length > 0,
    };
  }

  // -- messages from the card --

  async onMessage(msg) {
    if (!msg || typeof msg !== "object") return;
    if (msg.type === "ready") {
      this.push();
      return;
    }
    const entry = this.reviews.get(msg.id);
    if (!entry) {
      this.push();
      return;
    }
    try {
      switch (msg.type) {
        case "step":
          await this.visit(entry, msg.index);
          break;
        case "next":
          await this.visit(entry, entry.index + 1);
          break;
        case "prev":
          await this.visit(entry, entry.index - 1);
          break;
        case "nextUnread": {
          const i = this.nextUnreadIndex(entry);
          if (i >= 0) await this.visit(entry, i);
          break;
        }
        case "note": {
          const target = Number.isInteger(msg.index) ? entry.files[msg.index] : null;
          if (target && typeof msg.text === "string" && !entry.states.get(target.file).sent) {
            entry.states.get(target.file).note = msg.text;
          }
          this.push();
          break;
        }
        case "outsideNote":
          if (isFolderRelative(msg.path) && typeof msg.text === "string" && !entry.files.some((f) => f.file === msg.path)) {
            if (msg.text.trim()) entry.comments.set(msg.path, msg.text);
            else entry.comments.delete(msg.path);
          }
          this.push();
          break;
        case "sendFile":
          if (entry.files.length > 1 && Number.isInteger(msg.index) && VERDICTS.includes(msg.verdict)) {
            await this.sendRows(entry, [msg.index], msg.verdict);
          }
          break;
        case "send":
          if (entry.files.length === 1) await this.send(entry, msg.verdict === "approved" ? "approved" : "changes");
          break;
        case "approveAll":
          if (entry.files.length > 1) await this.sendRows(entry, this.approvableRows(entry), "approved");
          break;
        default:
          break;
      }
    } catch (e) {
      this.fail("handling the card", e);
    }
  }

  // The answer: one `files` entry per listed document, in request order, when the
  // review lists several; a review of one document keeps its note as `notes`.
  buildAnswer(entry, verdict) {
    const answer = {
      id: entry.request.id,
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
      const item = { file: f.file, read: state.read, verdict };
      if (state.note.trim()) item.note = state.note.trim();
      return item;
    });
    answer.notes = answer.files
      .filter((f) => f.note)
      .map((f) => `${baseName(f.file)}: ${f.note}`)
      .join("\n");
    return answer;
  }

  // The answer to the documents at `rows` (positions, ascending) of a
  // several-document review whose other documents stay open: the same shape as
  // the whole answer, `files` listing only these documents, each with its
  // `index`. `verdict` is the one every row is sent with. Notes on outside
  // files go out once; `edited` lists the answered documents typed in.
  buildPartialAnswer(entry, rows, verdict) {
    const files = rows.map((i) => {
      const f = entry.files[i];
      const state = entry.states.get(f.file);
      const item = { file: f.file, read: state.read, verdict, index: i };
      if (state.note.trim()) item.note = state.note.trim();
      return item;
    });
    const answered = new Set(files.map((f) => f.file));
    return {
      id: entry.request.id,
      file: files[0].file,
      verdict,
      notes: files
        .filter((f) => f.note)
        .map((f) => `${baseName(f.file)}: ${f.note}`)
        .join("\n"),
      comments: [...entry.comments]
        .filter(([file, note]) => entry.carriedComments.get(file) !== note)
        .map(([file, note]) => ({ file, note: note.trim() })),
      edited: [...entry.edited].filter((file) => answered.has(file)),
      files,
      at: new Date().toISOString(),
    };
  }

  // Sends the verdict for the rows at `rows` of a several-document review. The
  // answer is `<id>.verdict.json` when it covers every document of the request
  // and nothing was sent before, else `<id>.verdict.<n>.json`. A row already
  // sent is left out, and a "changes" row needs a note or an edit. The review
  // leaves the panel once every document is sent.
  async sendRows(entry, rows, verdict) {
    if (entry.sending) return;
    const open = [...new Set(rows)]
      .filter((i) => Number.isInteger(i) && i >= 0 && i < entry.files.length && !entry.states.get(entry.files[i].file).sent)
      .sort((a, b) => a - b);
    if (open.length === 0) return;
    if (verdict === "changes" && !open.every((i) => this.fileHasFeedback(entry, entry.files[i].file))) return;
    entry.sending = true;
    try {
      await this.saveListed(entry);
      const id = entry.request.id;
      if (this.reviews.get(id) !== entry) return;
      if (!exists(entry.path)) {
        this.reviews.delete(id);
        this.push();
        vscode.window.showInformationMessage("This review was withdrawn, so nothing was sent");
        return;
      }
      const taken = answeredPositions(entry.path, entry.files.length);
      if (exists(verdictPathFor(entry.path)) || open.some((i) => taken.has(i))) {
        this.reviews.delete(id);
        this.retired.add(id);
        this.push();
        vscode.window.showInformationMessage("This review was already answered, so nothing was sent");
        return;
      }
      const sentBefore = entry.files.some((f) => entry.states.get(f.file).sent);
      const whole = !sentBefore && open.length === entry.files.length;
      const target = whole ? verdictPathFor(entry.path) : partialPathFor(entry.path, open[0]);
      const answer = whole ? this.buildAnswer(entry, verdict) : this.buildPartialAnswer(entry, open, verdict);
      const staged = target.replace(/\.json$/, ".tmp");
      fs.writeFileSync(staged, JSON.stringify(answer, null, 2));
      fs.renameSync(staged, target);
      for (const i of open) {
        const state = entry.states.get(entry.files[i].file);
        state.sent = true;
        state.verdict = verdict;
      }
      for (const [file, note] of entry.comments) entry.carriedComments.set(file, note);
      if (entry.files.every((f) => entry.states.get(f.file).sent)) {
        this.reviews.delete(id);
        this.retired.add(id);
      }
      this.push();
      vscode.window.showInformationMessage(
        verdict === "approved" ? "Approved, sent to Claude" : "Changes requested, sent to Claude"
      );
    } finally {
      entry.sending = false;
    }
  }

  // Saves the listed editors that have unsaved text, so Compass reads what the
  // human sees.
  async saveListed(entry) {
    for (const doc of vscode.workspace.textDocuments) {
      if (doc.isDirty && doc.uri.scheme === "file" && this.listedFile(entry, doc.uri.fsPath)) await doc.save();
    }
  }

  async send(entry, verdict) {
    if (entry.sending) return;
    if (verdict === "changes" && !this.hasFeedback(entry)) return;
    entry.sending = true;
    try {
      // Flush the human's edits before Compass reads the files.
      await this.saveListed(entry);
      const id = entry.request.id;
      if (this.reviews.get(id) !== entry) return;
      if (!exists(entry.path)) {
        this.reviews.delete(id);
        this.push();
        vscode.window.showInformationMessage("This review was withdrawn, so nothing was sent");
        return;
      }
      const target = verdictPathFor(entry.path);
      if (exists(target)) {
        this.reviews.delete(id);
        this.retired.add(id);
        this.push();
        vscode.window.showInformationMessage("This review was already answered, so nothing was sent");
        return;
      }
      const staged = target.replace(/\.json$/, ".tmp");
      fs.writeFileSync(staged, JSON.stringify(this.buildAnswer(entry, verdict), null, 2));
      fs.renameSync(staged, target);
      this.reviews.delete(id);
      this.retired.add(id);
      this.push();
      vscode.window.showInformationMessage(
        verdict === "approved" ? "Approved, sent to Claude" : "Changes requested, sent to Claude"
      );
    } finally {
      entry.sending = false;
    }
  }
}

let current = null;

function activate(context) {
  current = new CompassReview(context);
  current.start();
}

function deactivate() {
  if (current) current.dispose();
  current = null;
}

module.exports = { activate, deactivate };

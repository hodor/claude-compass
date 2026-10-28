// Tests for the Compass Review extension for VS Code and Cursor, run with
// `node --test`. They drive plugin/vscode/compass-review/extension.js and the
// media/card.js it serves to its webview against a stub `vscode` module and a
// small DOM, with real files in a temporary project folder.
//
// What the extension satisfies:
//
// - extension.js exports `activate(context)` (sync or async) and
//   `deactivate()`. It reads `require("vscode")` when activated; a request
//   file, a verdict file and every document are read and written with node
//   `fs`, so the stub only has to model the editor.
// - It registers one webview view provider with
//   `vscode.window.registerWebviewViewProvider(viewId, provider)`. `viewId`
//   is a view of type `webview` in package.json under an Activity Bar
//   container, and the panel is revealed with `workbench.view.extension.<container id>`
//   or `<viewId>.focus`; any other id fails as an unknown command, as in an
//   editor. `provider.resolveWebviewView(view)` sets `view.webview.html` to a
//   page that loads `media/card.js` through `webview.asWebviewUri`, under a
//   Content-Security-Policy whose script-src carries a nonce, with
//   `enableScripts` on and `localResourceRoots` (when given) holding `media/`.
// - Each workspace folder holds the vault in `<folder>/.compass`; its requests
//   are `<folder>/.compass/tmp/review/<id>.request.json` and each answer is
//   written beside its request as `<id>.verdict.json`. A request is claimed
//   when it has no answer and its `surface` is "vscode" or "cursor" (the
//   window's own, from `vscode.env.appName`, is not assumed). Requests are
//   found at activation and as `createFileSystemWatcher` events, `.request.tmp`
//   files are ignored, and a request seen twice is one card.
// - Messages between extension and card cross `webview.postMessage` and
//   `onDidReceiveMessage` as JSON copies; the card is created again, empty,
//   whenever the view is hidden and shown, and announces itself to the
//   extension on loading.
// - The card is built with createElement and textContent. One element per
//   review carries `data-id` (the request id). Inside it: an element of class
//   `question`; labels "Project" and "Session" with their values (Session is
//   absent for an empty session); one element reading `File i of n`; buttons
//   "Previous", "Next", "Next unread", "Approve", "Needs changes"; one element
//   of class `row` per file holding the file's title, its reason, "read" or
//   "unread" and "N note(s)" or "no note"; a textarea for the current file's
//   note; one element reading `<n> of <m> files read, <k> notes` (with
//   ", <j> notes on files outside the review" when there are any); and,
//   while a markdown file outside the review is the active editor, an element
//   of class `this-file` reading `On this file: <path>` with its own textarea.
// - A file is shown with `vscode.window.showTextDocument`. A file is
//   "typed in" when `onDidChangeTextDocument` reports content changes for a
//   listed file whose document is the active editor's while the window is
//   focused (`vscode.window.state.focused`).
// - Paths in the answer are relative to the workspace folder, with `/`.

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vm = require("node:vm");
const Module = require("node:module");

const EXT_DIR = path.resolve(__dirname, "..", "compass-review");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clone = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
const keyOf = (p) => path.normalize(String(p)).toLowerCase();

// A leaked watcher or timer must not keep the process alive after the last test.
test.after(() => { setTimeout(() => process.exit(process.exitCode || 0), 2000).unref(); });

// ---- writes of verdict files, seen whatever way the extension makes them ----

const verdictWrites = [];
(function spyOnFs() {
  const note = (target) => { if (/\.verdict\.json$/.test(String(target))) verdictWrites.push(String(target)); };
  const wrap = (obj, name, pathIndex) => {
    const original = obj[name];
    if (typeof original !== "function") return;
    obj[name] = function (...args) { note(args[pathIndex]); return original.apply(this, args); };
  };
  for (const name of ["writeFile", "writeFileSync", "appendFile", "appendFileSync", "createWriteStream"]) {
    wrap(fs, name, 0);
    if (fs.promises[name]) wrap(fs.promises, name, 0);
  }
  for (const name of ["rename", "renameSync", "copyFile", "copyFileSync"]) {
    wrap(fs, name, 1);
    if (fs.promises[name]) wrap(fs.promises, name, 1);
  }
})();

// ---- a small DOM: what a card built with createElement and textContent touches ----

const camel = (name) => name.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
const SIMPLE = /^([a-zA-Z][\w-]*|\*)?((?:[.#][\w-]+|\[[^\]]+\])*)$/;

function matchesSimple(el, sel) {
  const m = SIMPLE.exec(sel);
  if (!m) return false;
  if (m[1] && m[1] !== "*" && el.tag !== m[1].toLowerCase()) return false;
  for (const part of (m[2] || "").match(/[.#][\w-]+|\[[^\]]+\]/g) || []) {
    if (part[0] === ".") { if (!el.hasClass(part.slice(1))) return false; }
    else if (part[0] === "#") { if (el.id !== part.slice(1)) return false; }
    else {
      const a = /^\[([\w-]+)(?:=["']?([^"'\]]*)["']?)?\]$/.exec(part);
      const have = a ? el.getAttribute(a[1]) : null;
      if (!a || have === null || (a[2] !== undefined && String(have) !== a[2])) return false;
    }
  }
  return true;
}
function matches(el, selector) {
  return selector.split(",").some((alt) => {
    const parts = alt.replace(/\s*>\s*/g, " ").trim().split(/\s+/);
    if (!matchesSimple(el, parts[parts.length - 1])) return false;
    let i = parts.length - 2;
    for (let node = el.parent; i >= 0 && node; node = node.parent) if (matchesSimple(node, parts[i])) i--;
    return i < 0;
  });
}

class El {
  constructor(tag, dom) {
    this.tag = tag.toLowerCase();
    this.tagName = tag.toUpperCase();
    this.dom = dom;
    this.children = [];
    this.parent = null;
    this.ownText = "";
    this.handlers = {};
    this.dataset = {};
    this.attrs = {};
    this.className = "";
    this.style = {};
    this.id = "";
    this.value = "";
    this.disabled = false;
    this.title = "";
    this.href = "";
    this.placeholder = "";
    this.type = "";
    this.hidden = false;
  }
  hasClass(c) { return this.className.split(/\s+/).includes(c); }
  get classList() {
    const el = this;
    const list = {
      add: (...c) => c.forEach((x) => { if (!el.hasClass(x)) el.className = `${el.className} ${x}`.trim(); }),
      remove: (...c) => { el.className = el.className.split(/\s+/).filter((x) => x && !c.includes(x)).join(" "); },
      contains: (c) => el.hasClass(c),
      toggle: (c, force) => {
        const on = force === undefined ? !el.hasClass(c) : !!force;
        if (on) list.add(c); else list.remove(c);
        return on;
      },
    };
    return list;
  }
  get textContent() { return this.ownText + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children.forEach((c) => { c.parent = null; }); this.children = []; this.ownText = String(v); }
  get innerText() { return this.textContent; }
  set innerText(v) { this.textContent = v; }
  get innerHTML() { return ""; }
  set innerHTML(v) {
    if (v !== "") throw new Error("the test DOM does not parse markup: build the card with createElement and textContent");
    this.textContent = "";
  }
  // The text set on this element itself, text nodes appended to it included.
  get directText() { return this.ownText + this.children.filter((c) => c.tag === "#text").map((c) => c.ownText).join(""); }
  get firstChild() { return this.children[0] || null; }
  get lastChild() { return this.children[this.children.length - 1] || null; }
  get childNodes() { return this.children; }
  get isConnected() { let n = this; while (n.parent) n = n.parent; return n === this.dom.body; }
  _take(item) {
    const node = typeof item === "string" ? this.dom.document.createTextNode(item) : item;
    if (node.parent) node.parent.children = node.parent.children.filter((c) => c !== node);
    node.parent = this;
    return node;
  }
  append(...items) { items.forEach((i) => this.children.push(this._take(i))); }
  appendChild(item) { this.append(item); return item; }
  prepend(...items) { this.children.unshift(...items.map((i) => this._take(i))); }
  insertBefore(item, ref) {
    const node = this._take(item);
    const at = ref ? this.children.indexOf(ref) : -1;
    if (at < 0) this.children.push(node); else this.children.splice(at, 0, node);
    return node;
  }
  replaceChildren(...items) { this.textContent = ""; this.append(...items); }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); c.parent = null; return c; }
  remove() { if (this.parent) this.parent.removeChild(this); }
  contains(n) { return this.all().includes(n); }
  all() { return [this, ...this.children.flatMap((c) => c.all())]; }
  querySelector(sel) { return this.all().slice(1).find((e) => matches(e, sel)) || null; }
  querySelectorAll(sel) { return this.all().slice(1).filter((e) => matches(e, sel)); }
  setAttribute(k, v) {
    this.attrs[k] = String(v);
    if (k === "class") this.className = String(v);
    else if (k === "id") this.id = String(v);
    else if (k.startsWith("data-")) this.dataset[camel(k.slice(5))] = String(v);
    else if (k === "disabled") this.disabled = true;
    else if (k === "title") this.title = String(v);
    else if (k === "href") this.href = String(v);
    else if (k === "placeholder") this.placeholder = String(v);
    else if (k === "value") this.value = String(v);
  }
  getAttribute(k) {
    if (k === "class") return this.className || null;
    if (k === "id") return this.id || null;
    if (k.startsWith("data-")) return this.dataset[camel(k.slice(5))] ?? null;
    if (k === "disabled") return this.disabled ? "" : null;
    return k in this.attrs ? this.attrs[k] : null;
  }
  hasAttribute(k) { return this.getAttribute(k) !== null; }
  removeAttribute(k) {
    delete this.attrs[k];
    if (k === "disabled") this.disabled = false;
    if (k.startsWith("data-")) delete this.dataset[camel(k.slice(5))];
  }
  addEventListener(type, fn) { (this.handlers[type] = this.handlers[type] || []).push(fn); }
  removeEventListener(type, fn) { this.handlers[type] = (this.handlers[type] || []).filter((f) => f !== fn); }
  focus() { this.dom.document.activeElement = this; }
  blur() { if (this.dom.document.activeElement === this) this.dom.document.activeElement = null; }
  scrollIntoView() {}
  select() {}
  setSelectionRange() {}
  getBoundingClientRect() { return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
}

// Events reach the target's handlers, then each ancestor's, then the
// document's and the window's. A disabled button receives no click.
function dispatch(el, type, init = {}) {
  if (type === "click" && el.tag === "button" && el.disabled) return null;
  const event = {
    type, target: el, bubbles: true, defaultPrevented: false, stopped: false,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this.stopped = true; },
    stopImmediatePropagation() { this.stopped = true; },
    ...init,
  };
  const run = (holder, fns) => { event.currentTarget = holder; for (const fn of fns) if (typeof fn === "function") fn.call(holder, event); };
  for (let n = el; n && !event.stopped; n = n.parent) run(n, [n["on" + type], ...(n.handlers[type] || [])]);
  if (!event.stopped) run(el.dom.document, el.dom.documentHandlers[type] || []);
  if (!event.stopped) run(el.dom.win, el.dom.winHandlers[type] || []);
  return event;
}

function makeDom(win) {
  const dom = { winHandlers: {}, documentHandlers: {}, win };
  dom.document = {
    activeElement: null,
    createElement: (tag) => new El(tag, dom),
    createTextNode: (text) => { const n = new El("#text", dom); n.ownText = String(text); return n; },
    getElementById(id) {
      let found = dom.body.all().find((e) => e.id === id);
      if (!found) { found = new El("div", dom); found.id = id; dom.body.append(found); }
      return found;
    },
    querySelector: (s) => dom.body.querySelector(s),
    querySelectorAll: (s) => dom.body.querySelectorAll(s),
    addEventListener(type, fn) { (dom.documentHandlers[type] = dom.documentHandlers[type] || []).push(fn); },
    removeEventListener(type, fn) { dom.documentHandlers[type] = (dom.documentHandlers[type] || []).filter((f) => f !== fn); },
    hasFocus: () => true,
  };
  dom.body = new El("body", dom);
  dom.document.body = dom.body;
  dom.document.documentElement = dom.body;
  return dom;
}

// The policy text of the page's Content-Security-Policy meta tag, else null.
function cspOf(html) {
  const meta = [...html.matchAll(/<meta\b[^>]*>/gi)].map((m) => m[0]).find((m) => /Content-Security-Policy/i.test(m));
  const content = meta && (/\bcontent="([^"]*)"/i.exec(meta) || /\bcontent='([^']*)'/i.exec(meta));
  return content ? content[1] : null;
}
const srcOf = (attrs) => { const m = /\bsrc=(?:"([^"]+)"|'([^']+)')/.exec(attrs); return m ? m[1] || m[2] : undefined; };

// ---- a page: card.js running in its own context, as the editor's webview runs it ----

class Page {
  constructor(webview, host) {
    this.webview = webview;
    this.host = host;
    this.errors = [];
    this.timers = new Set();
    this.dead = false;
    this.acquired = false;
    const win = this.win = {};
    const dom = this.dom = makeDom(win);
    dom.win = win;
    const track = (make) => (fn, ms, ...rest) => { const id = make(() => { try { fn(...rest); } catch (e) { this.errors.push(e); } }, ms); this.timers.add(id); return id; };
    Object.assign(win, {
      document: dom.document,
      window: win,
      self: win,
      console,
      URL,
      queueMicrotask,
      setTimeout: track(setTimeout),
      setInterval: track(setInterval),
      clearTimeout: (id) => { this.timers.delete(id); clearTimeout(id); },
      clearInterval: (id) => { this.timers.delete(id); clearInterval(id); },
      requestAnimationFrame: (fn) => win.setTimeout(fn, 0),
      cancelAnimationFrame: (id) => win.clearTimeout(id),
      getComputedStyle: () => ({ getPropertyValue: () => "" }),
      location: { href: "" },
      navigator: { userAgent: "node" },
      addEventListener: (type, fn) => { (dom.winHandlers[type] = dom.winHandlers[type] || []).push(fn); },
      removeEventListener: (type, fn) => { dom.winHandlers[type] = (dom.winHandlers[type] || []).filter((f) => f !== fn); },
      acquireVsCodeApi: () => {
        if (this.acquired) throw new Error("An instance of the VS Code API has already been acquired");
        this.acquired = true;
        return {
          postMessage: (msg) => this.fromCard(msg),
          getState: () => clone(webview.persisted),
          setState: (state) => { webview.persisted = clone(state); },
        };
      },
    });
    vm.createContext(win);
    this.load(webview.html);
  }

  load(html) {
    const csp = cspOf(html);
    const scriptSrc = csp ? (/(?:^|;)\s*script-src([^;]*)/i.exec(csp) || [])[1] : null;
    const tags = [...html.matchAll(/<script\b([^>]*)>/gi)].map((m) => m[1]);
    for (const attrs of tags) {
      const src = srcOf(attrs);
      if (!src) continue;
      const file = this.host.resourceUris.get(src);
      if (!file) { this.errors.push(new Error(`script ${src} was not made by webview.asWebviewUri`)); continue; }
      if (!this.webview.options.enableScripts) { this.errors.push(new Error("the webview has scripts disabled")); continue; }
      const roots = (this.webview.options.localResourceRoots || [this.host.api.Uri.file(EXT_DIR), ...this.host.folders.map((f) => this.host.api.Uri.file(f))])
        .map((u) => u.fsPath);
      if (!roots.some((r) => !path.relative(r, file).startsWith(".."))) {
        this.errors.push(new Error(`${file} is outside the webview's localResourceRoots`));
        continue;
      }
      if (csp) {
        const nonce = (/\bnonce="([^"]+)"/.exec(attrs) || [])[1];
        const tokens = (scriptSrc || "").trim().split(/\s+/);
        if (!(nonce && tokens.includes(`'nonce-${nonce}'`)) && !tokens.includes(this.webview.cspSource)) {
          this.errors.push(new Error(`the policy blocks ${file}`));
          continue;
        }
      }
      try {
        vm.runInContext(fs.readFileSync(file, "utf8"), this.win, { filename: file });
      } catch (e) { this.errors.push(e); }
    }
  }

  deliver(msg) {
    if (this.dead) return;
    this.host.activity++;
    for (const fn of this.dom.winHandlers.message || []) {
      try { fn.call(this.win, { type: "message", data: msg }); } catch (e) { this.errors.push(e); }
    }
  }

  fromCard(msg) {
    if (this.dead) return;
    this.host.activity++;
    this.webview.receive(clone(msg));
  }

  destroy() {
    this.dead = true;
    for (const id of this.timers) { clearTimeout(id); clearInterval(id); }
    this.timers.clear();
  }
}

// ---- the stub editor ----

class Disposable {
  constructor(fn) { this.fn = fn; }
  dispose() { if (this.fn) { const f = this.fn; this.fn = null; f(); } }
}

function globToRegExp(glob) {
  let re = "";
  let depth = 0;
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === "*") {
      if (glob[i + 1] === "*") { i++; if (glob[i + 1] === "/") { i++; re += "(?:.*/)?"; } else re += ".*"; }
      else re += "[^/]*";
    } else if (c === "?") re += "[^/]";
    else if (c === "{") { depth++; re += "(?:"; }
    else if (c === "}" && depth) { depth--; re += ")"; }
    else if (c === "," && depth) re += "|";
    else re += c.replace(/[.+^$()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${re}$`);
}
function globMatches(glob, fsPath) {
  let rel = fsPath;
  let pattern = glob;
  if (typeof glob !== "string") {
    pattern = glob.pattern;
    const r = path.relative(glob.base, fsPath);
    if (r.startsWith("..") || path.isAbsolute(r)) return false;
    rel = r;
  }
  return globToRegExp(pattern).test(rel.split(path.sep).join("/"));
}

const BUILTIN = /^(setContext|vscode\.|markdown\.|workbench\.(?!view\.extension\.)|editor\.|revealInExplorer|list\.)/;

class Host {
  constructor({ folders, appName = "Visual Studio Code" }) {
    this.folders = folders;
    this.appName = appName;
    this.activity = 0;
    this.extErrors = [];
    this.messages = [];
    this.commandsRun = [];
    this.commands = new Map();
    this.watchers = [];
    this.docs = new Map();
    this.columns = new Map();
    this.active = null;
    this.windowState = { focused: true, active: true };
    this.resourceUris = new Map();
    this.provider = null;
    this.viewId = null;
    this.retain = false;
    this.view = null;
    this.revealed = 0;
    this.lists = { change: [], activeEditor: [], visibleEditors: [], windowState: [], save: [], open: [] };
    this.package = JSON.parse(fs.readFileSync(path.join(EXT_DIR, "package.json"), "utf8"));
    this.api = this.makeApi();
    this.context = {
      subscriptions: [],
      extensionUri: this.api.Uri.file(EXT_DIR),
      extensionPath: EXT_DIR,
      asAbsolutePath: (p) => path.join(EXT_DIR, p),
      globalState: this.memento(),
      workspaceState: this.memento(),
      extension: { packageJSON: this.package, id: `${this.package.publisher}.${this.package.name}` },
    };
  }

  memento() {
    const data = new Map();
    return { get: (k, d) => (data.has(k) ? data.get(k) : d), update: async (k, v) => { data.set(k, v); }, keys: () => [...data.keys()] };
  }

  emit(list, arg) {
    for (const fn of [...list]) {
      try {
        const r = fn(arg);
        if (r && typeof r.catch === "function") r.catch((e) => this.extErrors.push(e));
      } catch (e) { this.extErrors.push(e); }
    }
  }

  event(list) {
    return (fn) => { list.push(fn); return new Disposable(() => { const i = list.indexOf(fn); if (i >= 0) list.splice(i, 1); }); };
  }

  uri(fsPath) {
    const p = path.normalize(fsPath);
    const slash = p.split(path.sep).join("/");
    return { scheme: "file", authority: "", path: slash, query: "", fragment: "", fsPath: p, toString: () => `file:///${encodeURI(slash)}`, toJSON: () => ({ scheme: "file", fsPath: p, path: slash }) };
  }

  makeApi() {
    const host = this;
    const loose = (obj) => new Proxy(obj, {
      get(target, prop) {
        if (prop in target || typeof prop === "symbol" || prop === "then") return target[prop];
        const noop = () => loose({ dispose() {} });
        return noop;
      },
    });
    const Uri = {
      file: (p) => host.uri(p),
      joinPath: (base, ...segs) => host.uri(path.join(base.fsPath, ...segs)),
      parse: (s) => host.uri(decodeURI(String(s).replace(/^file:\/\/\/?/, ""))),
    };
    const workspace = loose({
      get workspaceFolders() { return host.folders.length ? host.folders.map((f, index) => ({ uri: host.uri(f), name: path.basename(f), index })) : undefined; },
      get textDocuments() { return [...host.docs.values()]; },
      getWorkspaceFolder: (uri) => { const f = host.folders.find((d) => !path.relative(d, uri.fsPath).startsWith("..")); return f ? { uri: host.uri(f), name: path.basename(f), index: 0 } : undefined; },
      onDidChangeTextDocument: host.event(host.lists.change),
      onDidSaveTextDocument: host.event(host.lists.save),
      onDidOpenTextDocument: host.event(host.lists.open),
      onDidCloseTextDocument: host.event([]),
      onDidChangeWorkspaceFolders: host.event([]),
      onDidChangeConfiguration: host.event([]),
      onDidRenameFiles: host.event([]),
      onDidDeleteFiles: host.event([]),
      onDidCreateFiles: host.event([]),
      getConfiguration: () => ({ get: (k, d) => d, has: () => false, update: async () => {} }),
      asRelativePath: (p) => path.relative(host.folders[0] || "", typeof p === "string" ? p : p.fsPath).split(path.sep).join("/"),
      openTextDocument: (arg) => host.openDocument(typeof arg === "string" ? arg : arg.fsPath || arg.uri.fsPath),
      saveAll: async () => { for (const d of host.docs.values()) if (d.isDirty) await d.save(); return true; },
      createFileSystemWatcher(glob) {
        const w = { glob, disposed: false, handlers: { create: [], change: [], delete: [] },
          onDidCreate: (fn) => { w.handlers.create.push(fn); return new Disposable(); },
          onDidChange: (fn) => { w.handlers.change.push(fn); return new Disposable(); },
          onDidDelete: (fn) => { w.handlers.delete.push(fn); return new Disposable(); },
          dispose() { w.disposed = true; } };
        host.watchers.push(w);
        return w;
      },
      fs: {
        readFile: async (uri) => fs.promises.readFile(uri.fsPath),
        writeFile: async (uri, bytes) => fs.promises.writeFile(uri.fsPath, bytes),
        stat: async (uri) => { const s = await fs.promises.stat(uri.fsPath); return { type: s.isDirectory() ? 2 : 1, size: s.size, ctime: s.ctimeMs, mtime: s.mtimeMs }; },
        readDirectory: async (uri) => (await fs.promises.readdir(uri.fsPath, { withFileTypes: true })).map((d) => [d.name, d.isDirectory() ? 2 : 1]),
        createDirectory: async (uri) => { await fs.promises.mkdir(uri.fsPath, { recursive: true }); },
        delete: async (uri) => { await fs.promises.rm(uri.fsPath, { recursive: true, force: true }); },
      },
    });
    const message = (kind) => async (text, ...items) => { host.messages.push({ kind, text: String(text) }); return undefined; };
    const window = loose({
      get activeTextEditor() { return host.active || undefined; },
      get visibleTextEditors() { return [...host.columns.values()]; },
      get state() { return host.windowState; },
      onDidChangeActiveTextEditor: host.event(host.lists.activeEditor),
      onDidChangeVisibleTextEditors: host.event(host.lists.visibleEditors),
      onDidChangeWindowState: host.event(host.lists.windowState),
      showInformationMessage: message("info"),
      showWarningMessage: message("warning"),
      showErrorMessage: message("error"),
      showTextDocument: (arg, opts) => host.showDocument(arg, opts),
      createOutputChannel: () => ({ appendLine() {}, append() {}, show() {}, clear() {}, dispose() {} }),
      withProgress: async (_o, task) => task({ report() {} }, { isCancellationRequested: false }),
      registerWebviewViewProvider(viewId, provider, options) {
        host.provider = provider;
        host.viewId = viewId;
        host.retain = !!(options && options.webviewOptions && options.webviewOptions.retainContextWhenHidden);
        return new Disposable(() => { host.provider = null; });
      },
    });
    const commands = {
      registerCommand: (id, fn) => { host.commands.set(id, fn); return new Disposable(() => host.commands.delete(id)); },
      getCommands: async () => [...host.commands.keys()],
      executeCommand: (id, ...args) => host.execute(id, ...args),
    };
    return loose({
      Uri,
      Disposable,
      EventEmitter: class { constructor() { this.fns = []; this.event = (fn) => { this.fns.push(fn); return new Disposable(); }; } fire(v) { this.fns.forEach((f) => f(v)); } dispose() {} },
      RelativePattern: class { constructor(base, pattern) { this.base = typeof base === "string" ? base : (base.uri || base).fsPath; this.pattern = pattern; } },
      ViewColumn: { Active: -1, Beside: -2, One: 1, Two: 2, Three: 3 },
      FileSystemError: class extends Error { static FileNotFound() { return new Error("FileNotFound"); } },
      workspace,
      window,
      commands: loose(commands),
      env: loose({ appName: host.appName, appRoot: "", language: "en", machineId: "m", sessionId: "s", uriScheme: "vscode" }),
      version: "1.143.1",
    });
  }

  // -- commands and the panel --

  contributedViews() {
    const contributes = this.package.contributes || {};
    return Object.entries(contributes.views || {}).flatMap(([container, views]) => views.map((v) => ({ container, id: v.id })));
  }

  async execute(id, ...args) {
    this.commandsRun.push(id);
    this.activity++;
    if (this.commands.has(id)) return this.commands.get(id)(...args);
    const prefix = "workbench.view.extension.";
    const contributed = this.contributedViews();
    const reveals = id.startsWith(prefix)
      ? contributed.some((v) => v.container === id.slice(prefix.length) && v.id === this.viewId)
      : this.viewId && id === `${this.viewId}.focus` && contributed.some((v) => v.id === this.viewId);
    if (reveals) {
      this.revealed++;
      if (!this.view) await this.resolveView();
      else if (!this.view.visible) this.showView();
      return undefined;
    }
    if (id === "vscode.open") { await this.showDocument(args[0], args[1]); return undefined; }
    if (BUILTIN.test(id)) return undefined;
    throw new Error(`command '${id}' not found`);
  }

  async resolveView() {
    if (!this.provider) throw new Error("no webview view provider is registered");
    const view = new WebviewView(this);
    this.view = view;
    await this.provider.resolveWebviewView(view, { state: undefined }, { isCancellationRequested: false, onCancellationRequested: () => new Disposable() });
    return view;
  }

  hideView() {
    const view = this.view;
    view.visible = false;
    this.emit(view.visibility, undefined);
    if (!this.retain && view.webview.page) { view.webview.page.destroy(); view.webview.page = null; }
  }

  showView() {
    const view = this.view;
    view.visible = true;
    this.emit(view.visibility, undefined);
    view.webview.schedulePage();
  }

  disposeView() {
    const view = this.view;
    if (view.webview.page) view.webview.page.destroy();
    view.webview.page = null;
    this.emit(view.disposals, undefined);
    this.view = null;
  }

  // -- documents and editors --

  async openDocument(fsPath) {
    const key = keyOf(fsPath);
    if (this.docs.has(key)) return this.docs.get(key);
    let text;
    try { text = await fs.promises.readFile(fsPath, "utf8"); } catch (e) { throw new Error(`Unable to read file '${fsPath}'`); }
    const host = this;
    const doc = {
      uri: this.uri(fsPath), fileName: fsPath, languageId: /\.md$/i.test(fsPath) ? "markdown" : "json",
      isDirty: false, isUntitled: false, isClosed: false, version: 1, saved: 0, text,
      getText() { return this.text; },
      get lineCount() { return this.text.split("\n").length; },
      async save() { this.saved++; this.isDirty = false; host.activity++; return true; },
    };
    this.docs.set(key, doc);
    this.emit(this.lists.open, doc);
    return doc;
  }

  async showDocument(arg, opts) {
    const fsPath = (arg.uri || arg).fsPath;
    const doc = await this.openDocument(fsPath);
    const requested = typeof opts === "number" ? opts : opts && opts.viewColumn;
    const column = requested > 0 ? requested : (this.active ? this.active.viewColumn : 1);
    let editor = this.columns.get(column);
    if (!editor || editor.document !== doc) {
      editor = { document: doc, viewColumn: column, selection: {}, selections: [] };
      this.columns.set(column, editor);
      this.emit(this.lists.visibleEditors, [...this.columns.values()]);
    }
    this.activity++;
    if (this.active !== editor) {
      this.active = editor;
      this.emit(this.lists.activeEditor, editor);
    }
    return editor;
  }

  // The human opens a file from the Explorer, Quick Open or a link.
  async humanOpens(fsPath) { await this.showDocument(this.uri(fsPath)); }

  // The human types in a file: its document becomes dirty and reports changes.
  type(fsPath, { changes = 1 } = {}) {
    const doc = this.docs.get(keyOf(fsPath));
    assert.ok(doc, `no open document ${fsPath}`);
    doc.isDirty = true;
    const change = { text: "x", rangeOffset: 0, rangeLength: 0, range: { start: { line: 0, character: 0 }, end: { line: 0, character: 0 } } };
    this.emit(this.lists.change, { document: doc, contentChanges: Array.from({ length: changes }, () => change), reason: undefined });
  }

  setWindowFocus(focused) {
    this.windowState = { focused, active: focused };
    this.emit(this.lists.windowState, this.windowState);
  }

  // A file event as the editor reports it to a watcher whose glob matches.
  fire(kind, fsPath) {
    for (const w of this.watchers) {
      if (!w.disposed && globMatches(w.glob, fsPath)) this.emit(w.handlers[kind], this.uri(fsPath));
    }
  }
}

class WebviewView {
  constructor(host) {
    this.host = host;
    this.visible = true;
    this.visibility = [];
    this.disposals = [];
    this.viewType = host.viewId;
    this.webview = new Webview(host, this);
  }
  onDidChangeVisibility(fn) { this.visibility.push(fn); return new Disposable(); }
  onDidDispose(fn) { this.disposals.push(fn); return new Disposable(); }
  show() { this.host.activity++; this.host.revealed++; }
}

class Webview {
  constructor(host, view) {
    this.host = host;
    this.view = view;
    this.options = {};
    this.cspSource = "vscode-webview-resource:";
    this.listeners = [];
    this.page = null;
    this.persisted = undefined;
    this._html = "";
  }
  get html() { return this._html; }
  set html(value) { this._html = value; if (this.page) { this.page.destroy(); this.page = null; } this.schedulePage(); }
  schedulePage() {
    const html = this._html;
    setImmediate(() => {
      if (this.view.visible && !this.page && this._html === html && html && this.host.view === this.view) this.page = new Page(this, this.host);
    });
  }
  asWebviewUri(uri) {
    const s = `vscode-webview-resource://host/${encodeURIComponent(uri.fsPath)}`;
    this.host.resourceUris.set(s, uri.fsPath);
    return { scheme: "vscode-webview-resource", fsPath: uri.fsPath, toString: () => s };
  }
  onDidReceiveMessage(fn) { this.listeners.push(fn); return new Disposable(() => { this.listeners = this.listeners.filter((f) => f !== fn); }); }
  async postMessage(msg) {
    const copy = clone(msg);
    this.host.activity++;
    setImmediate(() => { if (this.page) this.page.deliver(copy); });
    return true;
  }
  receive(msg) {
    for (const fn of [...this.listeners]) {
      try {
        const r = fn(msg);
        if (r && typeof r.catch === "function") r.catch((e) => this.host.extErrors.push(e));
      } catch (e) { this.host.extErrors.push(e); }
    }
  }
}

// ---- loading the extension against the stub ----

let currentVscode = null;
const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === "vscode") return currentVscode;
  return originalLoad.apply(this, arguments);
};
function loadExtension(api) {
  currentVscode = api;
  for (const key of Object.keys(require.cache)) if (key.startsWith(EXT_DIR)) delete require.cache[key];
  return require(path.join(EXT_DIR, "extension.js"));
}

// ---- fixtures ----

const SPEC = ".compass/specs/spec.md";
const PLAN = ".compass/plans/plan.md";
const DETAIL = ".compass/plans/detail.md";
const SET = [SPEC, PLAN, DETAIL];
const WHY = ["The need", "What gets built in what order", "The long text of each task"];
const OUTSIDE = ".compass/research/elsewhere.md";
const DATA = ".compass/meta/data.json";
const DOCK_A = ".compass/research/dock-a.md";
const DOCK_B = ".compass/research/dock-b.md";
const ID = "20261028T101500-a1b2c3";
const ID2 = "20261028T101600-d4e5f6";
const SESSION_A = "7f3a91c2-4d1b-4e8a-9b2f-5c06d83e1a47";
const SESSION_B = "b20e44aa-1c5d-4f60-8a37-90de12c4f5b1";

function request(id, files, extra = {}) {
  return {
    id, surface: "vscode", file: files[0],
    files: files.map((file, i) => ({ file, why: WHY[i] ?? null })),
    title: "Approve the combat spec", return: true, commit: "abc1234",
    session: SESSION_A, project: "harbor", ...extra,
  };
}

class Env {
  constructor(t, host, root, ext) {
    this.t = t;
    this.host = host;
    this.root = root;
    this.project = host.folders[0] || null;
    this.ext = ext;
    this.closed = false;
    t.after(() => this.close());
  }
  abs(rel, project = this.project) { return path.join(project, ...rel.split("/")); }
  reviewDir(project = this.project) { return path.join(project, ".compass", "tmp", "review"); }
  requestFile(id, project) { return path.join(this.reviewDir(project), `${id}.request.json`); }
  verdictFile(id, project) { return path.join(this.reviewDir(project), `${id}.verdict.json`); }
  hasVerdict(id, project) { return fs.existsSync(this.verdictFile(id, project)); }
  verdict(id, project) { return JSON.parse(fs.readFileSync(this.verdictFile(id, project), "utf8")); }

  // Writes the request as Compass does: a half-written temporary file first, then the
  // whole file renamed into place, announcing each to the watchers.
  async arrive(req, { project = this.project, events = 1 } = {}) {
    const base = path.join(this.reviewDir(project), `${req.id}.request`);
    fs.mkdirSync(this.reviewDir(project), { recursive: true });
    fs.writeFileSync(`${base}.tmp`, '{"id": "');
    this.host.fire("create", `${base}.tmp`);
    fs.writeFileSync(`${base}.tmp`, JSON.stringify(req, null, 2));
    fs.renameSync(`${base}.tmp`, `${base}.json`);
    for (let i = 0; i < events; i++) this.host.fire("create", `${base}.json`);
  }
  put(rel, content = "x\n", project = this.project) {
    fs.mkdirSync(path.dirname(this.abs(rel, project)), { recursive: true });
    fs.writeFileSync(this.abs(rel, project), content);
  }

  // -- the card --
  get page() { return this.host.view && this.host.view.webview.page; }
  cards() { return this.page ? this.page.dom.body.all().filter((e) => e.dataset.id !== undefined) : []; }
  cardIds() { return this.cards().map((c) => c.dataset.id); }
  card(id = ID) { return this.cards().find((c) => c.dataset.id === id); }
  button(text, id = ID) { const c = this.card(id); return c && c.all().find((e) => e.tag === "button" && e.textContent === text); }
  rows(id = ID) { return this.card(id).all().filter((e) => e.hasClass("row")); }
  position(id = ID) { const c = this.card(id); const e = c && c.all().find((x) => /^File \d+ of \d+$/.test(x.directText)); return e ? e.directText : null; }
  marks(id = ID) { return this.rows(id).map((r) => (r.all().find((x) => x.directText === "read" || x.directText === "unread") || {}).directText); }
  summary(id = ID) { const e = this.card(id).all().find((x) => /files read/.test(x.directText)); return e ? e.directText : null; }
  thisFile(id = ID) { return this.card(id).all().find((e) => e.hasClass("this-file")) || null; }
  fileNote(id = ID) { const b = this.thisFile(id); return b && b.all().find((e) => e.tag === "textarea"); }
  notes(id = ID) {
    const inBlock = this.thisFile(id) ? this.thisFile(id).all() : [];
    return this.card(id).all().find((e) => e.tag === "textarea" && !inBlock.includes(e));
  }
  label(text, id = ID) { return this.card(id).all().find((e) => e.directText === text); }
  activeRel() {
    const e = this.host.active;
    return e ? path.relative(this.project, e.document.uri.fsPath).split(path.sep).join("/") : null;
  }
  doc(rel) { return this.host.docs.get(keyOf(this.abs(rel))); }

  // -- actions --
  async settle() {
    let last = this.host.activity;
    let still = 0;
    const start = Date.now();
    while (still < 4 && Date.now() - start < 3000) {
      await sleep(10);
      if (this.host.activity === last) still++; else { last = this.host.activity; still = 0; }
    }
  }
  async click(el) { dispatch(el, "click"); await this.settle(); }
  async step(name, id = ID) { const b = this.button(name, id); assert.ok(b, `no ${name} button`); await this.click(b); }
  async goToRow(i, id = ID) { await this.click(this.rows(id)[i]); }
  async type(el, value) {
    assert.ok(el, "text field to type into is missing");
    el.value = value;
    dispatch(el, "input");
    dispatch(el, "change");
    await this.settle();
  }
  async press(el, key, mods = {}) { dispatch(el, "keydown", { key, ...mods }); await this.settle(); }
  async open(rel) { await this.host.humanOpens(this.abs(rel)); await this.settle(); }
  async typedIn(rel) { this.host.type(this.abs(rel)); await this.settle(); }
  async approve(id = ID) { await this.step("Approve", id); }
  async until(fn, what, ms = 3000) {
    const end = Date.now() + ms;
    for (;;) {
      let ok = false;
      try { ok = fn(); } catch (e) { ok = false; }
      if (ok) return;
      if (Date.now() > end) assert.fail(`timed out waiting for ${what}`);
      await sleep(10);
    }
  }
  async ready(id = ID) {
    await this.until(() => this.card(id) && this.position(id), `the card of review ${id}`);
    await this.settle();
  }
  problems() {
    return [
      ...this.host.extErrors.map(String),
      ...(this.page ? this.page.errors.map(String) : []),
      ...this.host.messages.filter((m) => m.kind === "error").map((m) => `error message: ${m.text}`),
    ];
  }
  async close() {
    if (this.closed) return;
    this.closed = true;
    try {
      if (this.ext.deactivate) await this.ext.deactivate();
      for (const d of this.host.context.subscriptions) if (d && typeof d.dispose === "function") { try { d.dispose(); } catch (e) { /* released with the window */ } }
    } finally {
      if (this.host.view && this.host.view.webview.page) this.host.view.webview.page.destroy();
      try { fs.rmSync(this.root, { recursive: true, force: true, maxRetries: 5 }); } catch (e) { /* the folder is temporary */ }
    }
    assert.deepEqual(this.problems(), [], "errors raised while the test ran");
  }
}

// Starts the extension in a window on one temporary project folder (or the given folders).
async function begin(t, { folders = ["orchard"], files = {}, appName, populate = true } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "compass-vscode-"));
  const dirs = folders.map((name) => path.join(root, name));
  for (const dir of dirs) fs.mkdirSync(dir, { recursive: true });
  const host = new Host({ folders: dirs, appName });
  const ext = loadExtension(host.api);
  const env = new Env(t, host, root, ext);
  const everything = [...SET, OUTSIDE, DATA, DOCK_A, DOCK_B, ".compass/research/unlisted.md"];
  if (dirs[0] && populate) for (const rel of everything) env.put(rel, "x\n");
  for (const [rel, content] of Object.entries(files)) env.put(rel, content);
  return { env, activate: () => ext.activate(host.context) };
}

// A window on one project with a three-file review waiting, activated and drawn.
async function openSet(t, { req = {}, files } = {}) {
  const { env, activate } = await begin(t, { files });
  fs.mkdirSync(env.reviewDir(), { recursive: true });
  fs.writeFileSync(env.requestFile(ID), JSON.stringify(request(ID, SET, req), null, 2));
  await activate();
  await env.ready();
  return env;
}

// ---- package.json ----

// Adversarial where: the manifest asks for an engine Cursor lacks, points at a
// missing entry file or icon, activates only after the human opens the panel (so
// a request arriving first is never seen), or declares a view the extension
// cannot fill.
test("package.json declares the engine, an entry file, startup activation and a webview view in an Activity Bar container", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(EXT_DIR, "package.json"), "utf8"));
  assert.equal(pkg.engines.vscode, "^1.85.0");
  for (const key of ["name", "publisher", "version"]) {
    assert.equal(typeof pkg[key], "string", key);
    assert.ok(pkg[key].trim(), key);
  }
  assert.ok(fs.existsSync(path.join(EXT_DIR, pkg.main)), "main names a file");
  assert.ok(pkg.activationEvents.some((e) => e === "*" || e === "onStartupFinished"), "activates without the panel being opened");
  const containers = pkg.contributes.viewsContainers.activitybar;
  assert.ok(containers.length >= 1);
  for (const c of containers) assert.ok(fs.existsSync(path.join(EXT_DIR, c.icon)), `icon ${c.icon}`);
  const views = Object.entries(pkg.contributes.views);
  assert.ok(views.length >= 1);
  for (const [container, list] of views) {
    assert.ok(containers.some((c) => c.id === container), `view container ${container}`);
    for (const v of list) assert.equal(v.type, "webview", v.id);
  }
});

// ---- finding requests ----

// Adversarial where: the panel never opens for a request already waiting (a
// window opened on the folder by `code <folder>` shows nothing), an answered or
// another surface's or a damaged or half-written request is claimed, one bad
// file stops the good ones, or the first file is not opened for the walk.
test("activation claims the waiting requests that are its own, reveals the panel and opens the first file", async (t) => {
  const { env, activate } = await begin(t);
  const dir = env.reviewDir();
  fs.mkdirSync(dir, { recursive: true });
  const write = (name, body) => fs.writeFileSync(path.join(dir, name), typeof body === "string" ? body : JSON.stringify(body));
  write("waiting.request.json", request("waiting", SET));
  write("answered.request.json", request("answered", SET));
  write("answered.verdict.json", { id: "answered", verdict: "approved" });
  write("obsidian.request.json", request("obsidian", SET, { surface: "obsidian" }));
  write("broken.request.json", "{nope");
  write("half.request.tmp", '{"id": "half", "surface": "vscode", "file": ".compass/specs/spec.md"}');
  await activate();
  await env.ready("waiting");
  assert.deepEqual(env.cardIds(), ["waiting"]);
  assert.ok(env.host.revealed >= 1, "the panel was revealed");
  assert.equal(env.activeRel(), SPEC);
  assert.deepEqual(fs.readdirSync(dir).filter((n) => n.endsWith(".verdict.json")), ["answered.verdict.json"]);
});

// Adversarial where: a request written after the window is open is missed, it
// is claimed while still half written, the panel is not brought up for it, or
// two announcements of one file draw two cards.
test("a request arriving after activation is claimed once however many events announce it, and reveals the panel", async (t) => {
  const { env, activate } = await begin(t);
  await activate();
  await env.settle();
  assert.equal(env.host.revealed, 0, "nothing to show yet");
  await env.arrive(request(ID, SET), { events: 3 });
  await env.ready();
  assert.deepEqual(env.cardIds(), [ID]);
  assert.ok(env.host.revealed >= 1);
  assert.equal(env.activeRel(), SPEC);
});

// Adversarial where: a window with no folder, or a folder with no vault, throws
// at activation or raises a panel with nothing in it.
test("a window with no folder, or a folder without a vault, claims nothing and does not throw", async (t) => {
  for (const folders of [[], ["bare"]]) {
    await t.test(folders.length ? "a folder without a vault" : "no folder", async (st) => {
      const { env, activate } = await begin(st, { folders, populate: false });
      await activate();
      await env.settle();
      assert.equal(env.host.revealed, 0);
      assert.deepEqual(env.cardIds(), []);
    });
  }
});

// Adversarial where: only the first workspace folder is watched, a request is
// answered beside another folder's requests, or one folder's request is shown
// in a window that does not hold it.
test("every workspace folder is claimed, and each answer lands beside its own request", async (t) => {
  const { env, activate } = await begin(t, { folders: ["orchard", "harbor"] });
  const other = env.host.folders[1];
  for (const rel of SET) env.put(rel, "y\n", other);
  const first = request(ID, SET);
  const second = request(ID2, SET);
  fs.mkdirSync(env.reviewDir(env.project), { recursive: true });
  fs.mkdirSync(env.reviewDir(other), { recursive: true });
  fs.writeFileSync(env.requestFile(ID, env.project), JSON.stringify(first));
  fs.writeFileSync(env.requestFile(ID2, other), JSON.stringify(second));
  await activate();
  await env.ready(ID);
  await env.ready(ID2);
  assert.deepEqual(env.cardIds().sort(), [ID, ID2].sort());
  await env.approve(ID2);
  assert.ok(env.hasVerdict(ID2, other));
  assert.equal(env.hasVerdict(ID2, env.project), false);
  assert.equal(env.hasVerdict(ID, env.project), false);
  assert.equal(env.hasVerdict(ID, other), false);
});

// ---- the card ----

// Adversarial where: the panel page cannot run (scripts off, card.js outside the
// allowed folders, a policy that lets any inline script run), so the card never
// draws.
test("the webview page loads media/card.js through the editor's resource URIs under a nonce policy", async (t) => {
  const env = await openSet(t);
  const webview = env.host.view.webview;
  assert.equal(webview.options.enableScripts, true);
  const csp = cspOf(webview.html);
  assert.ok(csp, "the page carries a Content-Security-Policy");
  const scriptSrc = /(?:^|;)\s*script-src([^;]*)/i.exec(csp);
  assert.ok(scriptSrc && /'nonce-[^']+'/.test(scriptSrc[1]), "script-src carries a nonce");
  assert.doesNotMatch(scriptSrc[1], /unsafe-inline|unsafe-eval|\*/);
  const loaded = [...webview.html.matchAll(/<script\b([^>]*)>/gi)].map((m) => env.host.resourceUris.get(srcOf(m[1])));
  assert.ok(loaded.includes(path.join(EXT_DIR, "media", "card.js")));
  assert.deepEqual(env.page.errors, []);
});

// Adversarial where: the card lists files in a sorted or reversed order instead
// of the request's, drops a row's reason, marks every file read or none, counts
// the first file's opening wrongly, or omits the heading.
test("a three-file request draws one card at File 1 of 3 with a row per file in request order", async (t) => {
  const env = await openSet(t, { req: { files: [SET[2], SET[0], SET[1]].map((file, i) => ({ file, why: WHY[i] })), file: SET[2] } });
  assert.deepEqual(env.cardIds(), [ID]);
  assert.ok(env.page.dom.body.all().some((e) => e.directText === "Reviews waiting on you"), "panel heading");
  assert.equal(env.position(), "File 1 of 3");
  const rows = env.rows();
  assert.equal(rows.length, 3);
  assert.deepEqual(rows.map((r) => WHY.findIndex((w) => r.textContent.includes(w))), [0, 1, 2]);
  assert.deepEqual(rows.map((r) => ["detail", "spec", "plan"].findIndex((n) => r.textContent.includes(n))), [0, 1, 2]);
  assert.deepEqual(env.marks(), ["read", "unread", "unread"]);
  assert.match(env.summary(), /^1 of 3 files read, 0 notes/);
  assert.ok(env.button("Approve") && env.button("Needs changes"));
  assert.equal(env.button("Previous").disabled, true);
  assert.equal(env.activeRel(), SET[2], "the first listed file is open");
});

// Adversarial where: Next opens the file but leaves it unread or the position
// unchanged, Previous does not go back, or the buttons stay on at the ends.
test("Next and Previous move through the files in request order, mark each read, and switch off at the ends", async (t) => {
  await t.test("Next opens the second file and marks it read", async (st) => {
    const env = await openSet(st);
    await env.step("Next");
    assert.equal(env.position(), "File 2 of 3");
    assert.equal(env.activeRel(), PLAN);
    assert.deepEqual(env.marks(), ["read", "read", "unread"]);
  });
  await t.test("Previous returns to the first file", async (st) => {
    const env = await openSet(st);
    await env.step("Next");
    await env.step("Previous");
    assert.equal(env.position(), "File 1 of 3");
    assert.equal(env.activeRel(), SPEC);
  });
  await t.test("on the first file Previous is off and Next is on", async (st) => {
    const env = await openSet(st);
    assert.equal(env.button("Previous").disabled, true);
    assert.notEqual(env.button("Next").disabled, true);
  });
  await t.test("on the last file Next is off and Previous is on", async (st) => {
    const env = await openSet(st);
    await env.goToRow(2);
    assert.equal(env.button("Next").disabled, true);
    assert.notEqual(env.button("Previous").disabled, true);
  });
  await t.test("one step from the last file Next is still on", async (st) => {
    const env = await openSet(st);
    await env.goToRow(1);
    assert.notEqual(env.button("Next").disabled, true);
  });
});

// Adversarial where: Next unread stops on a read file, ignores the files before
// the current one when none after it is unread, or stays on once every file is
// read.
test("Next unread jumps to the next file not yet read and switches off when none is left", async (t) => {
  await t.test("it skips a read file that lies between", async (st) => {
    const env = await openSet(st);
    await env.goToRow(2);
    await env.goToRow(0);
    await env.step("Next unread");
    assert.equal(env.position(), "File 2 of 3");
    assert.equal(env.button("Next unread").disabled, true, "every file is read");
  });
  await t.test("with only earlier files unread it goes back to the first of them", async (st) => {
    const env = await openSet(st);
    await env.goToRow(2);
    await env.step("Next unread");
    assert.equal(env.position(), "File 2 of 3");
    assert.equal(env.activeRel(), PLAN);
  });
  await t.test("it is on while any file is unread", async (st) => {
    const env = await openSet(st);
    assert.notEqual(env.button("Next unread").disabled, true);
  });
});

// Adversarial where: opening a listed file from the Explorer, Quick Open or a
// link leaves the walk on the old file or the new one unread, or shows it as
// an outside file.
test("opening a listed file by hand moves the walk to it, marks it read, and is not an outside file", async (t) => {
  const env = await openSet(t);
  await env.open(DETAIL);
  assert.equal(env.position(), "File 3 of 3");
  assert.deepEqual(env.marks(), ["read", "unread", "read"]);
  assert.equal(env.thisFile(), null);
});

// Adversarial where: a click on a row does not open the file, opens it in a
// second editor group although one already shows it, or does not mark it read.
test("a click on a row opens that file in the group that shows it, else in the active group, and marks it read", async (t) => {
  await t.test("a file already shown in another group gets no second editor", async (st) => {
    const env = await openSet(st);
    await env.host.showDocument(env.host.uri(env.abs(PLAN)), { viewColumn: 2 });
    await env.host.showDocument(env.host.uri(env.abs(SPEC)), { viewColumn: 1 });
    await env.settle();
    await env.goToRow(1);
    const shown = env.host.api.window.visibleTextEditors.filter((e) => e.document === env.doc(PLAN));
    assert.equal(shown.length, 1);
    assert.equal(env.host.active.viewColumn, 2);
    assert.equal(env.position(), "File 2 of 3");
  });
  await t.test("a file shown nowhere opens and is marked read", async (st) => {
    const env = await openSet(st);
    await env.goToRow(2);
    assert.equal(env.activeRel(), DETAIL);
    assert.equal(env.position(), "File 3 of 3");
    assert.equal(env.marks()[2], "read");
  });
});

// Adversarial where: the arrow keys do nothing, run the wrong way, walk past
// either end, react to other keys, or step when a modifier or a note field
// owns the key.
test("arrow keys on the card step through the files and stop at the ends; modified keys and keys in a note field do not", async (t) => {
  const env = await openSet(t);
  const card = () => env.card();
  await env.press(card(), "ArrowLeft");
  assert.equal(env.position(), "File 1 of 3", "Left on the first file stays");
  await env.press(card(), "ArrowRight");
  assert.equal(env.position(), "File 2 of 3");
  await env.press(card(), "x");
  assert.equal(env.position(), "File 2 of 3", "other keys do nothing");
  await env.press(card(), "ArrowRight");
  await env.press(card(), "ArrowRight");
  assert.equal(env.position(), "File 3 of 3", "Right on the last file stays");
  await env.press(card(), "ArrowLeft");
  assert.equal(env.position(), "File 2 of 3");
  const field = env.notes();
  const rows = [
    ["ArrowRight in the note field", field, {}],
    ["Alt+ArrowRight", card(), { altKey: true }],
    ["Ctrl+ArrowRight", card(), { ctrlKey: true }],
    ["Meta+ArrowRight", card(), { metaKey: true }],
    ["Shift+ArrowRight", card(), { shiftKey: true }],
  ];
  for (const [name, target, mods] of rows) {
    await env.press(target, "ArrowRight", mods);
    assert.equal(env.position(), "File 2 of 3", name);
  }
});

// Adversarial where: the row shows a path or the file name although the file
// has a `title` property (quoted or not), or the note field is labelled with
// something other than the current file's title.
test("rows use the title property of a file, else its name", async (t) => {
  const env = await openSet(t, { files: {
    [SPEC]: '---\ntitle: "Combat spec"\ntype: spec\n---\nbody\n',
    [PLAN]: "---\ntitle: Build order\n---\nbody\n",
  } });
  const rows = env.rows();
  assert.ok(rows[0].textContent.includes("Combat spec"));
  assert.ok(rows[1].textContent.includes("Build order"));
  assert.ok(rows[2].textContent.includes("detail"));
  assert.ok(!rows[0].textContent.includes("spec.md"));
});

// Adversarial where: the question shows the first file's path or "null" when
// the title is missing, null or empty (`compass review` writes null).
test("a card's question is the request title, or the first file's name when the title is missing, null or empty", async (t) => {
  const rows = [["a title", "Approve this spec?", "Approve this spec?"], ["null", null, "spec"], ["empty", "", "spec"], ["missing", undefined, "spec"]];
  for (const [name, title, expected] of rows) {
    await t.test(name, async (st) => {
      const env = await openSet(st, { req: { title } });
      const question = env.card().all().find((e) => e.hasClass("question"));
      assert.ok(question, "the card has a question element");
      assert.equal(question.directText, expected);
    });
  }
});

// Adversarial where: the note field is shared by all files (text typed on one
// shows on the next), a note is lost when the walk moves away, a
// whitespace-only note counts, or the row and summary counts lag the typing.
test("each file keeps its own note as the walk moves, and the rows and the summary count them", async (t) => {
  const env = await openSet(t);
  await env.step("Next");
  await env.type(env.notes(), "reorder the tasks");
  assert.match(env.rows()[1].textContent, /\b1 note\b/);
  assert.match(env.summary(), /^2 of 3 files read, 1 note\b/);
  await env.step("Next");
  assert.equal(env.notes().value, "", "the next file starts with its own empty note");
  await env.type(env.notes(), "   ");
  assert.match(env.summary(), /^3 of 3 files read, 1 note\b/, "a whitespace-only note is no note");
  await env.step("Previous");
  assert.equal(env.notes().value, "reorder the tasks", "the note stays with its file");
  assert.doesNotMatch(env.rows()[0].textContent, /\b[1-9]\d* notes?\b/);
});

// Adversarial where: "On this file" shows for a listed file, stays on after a
// non-markdown file replaces the outside one, or lacks the path.
test("On this file shows only while a markdown file outside the review is in view", async (t) => {
  const env = await openSet(t);
  assert.equal(env.thisFile(), null, "a listed file in view");
  await env.open(OUTSIDE);
  assert.ok(env.thisFile(), "an unlisted markdown file");
  assert.ok(env.thisFile().textContent.includes(`On this file: ${OUTSIDE}`));
  await env.open(DATA);
  assert.equal(env.thisFile(), null, "a non-markdown file");
  await env.open(OUTSIDE);
  await env.open(PLAN);
  assert.equal(env.thisFile(), null, "opening a listed file hides the box");
  assert.equal(env.position(), "File 2 of 3");
});

// Adversarial where: the "On this file" box loses its note, an outside note does
// not count in the summary, enable Needs changes or travel in `comments`, is
// not trimmed, or an emptied note is sent as an empty comment.
test("a file outside the review gets its own note, which counts and travels in comments", async (t) => {
  const env = await openSet(t);
  await env.open(OUTSIDE);
  assert.equal(env.button("Needs changes").disabled, true);
  await env.type(env.fileNote(), "  typo on line 3 \n");
  assert.match(env.summary(), /^1 of 3 files read, 0 notes/);
  assert.match(env.summary(), /outside/);
  assert.equal(env.button("Needs changes").disabled, false);
  await env.open(DATA);
  await env.open(OUTSIDE);
  assert.equal(env.fileNote().value.trim(), "typo on line 3", "the note stays with its file");
  await env.open(".compass/research/unlisted.md");
  assert.equal(env.fileNote().value, "", "another outside file starts empty");
  await env.type(env.fileNote(), "temp");
  await env.type(env.fileNote(), "");
  await env.open(PLAN);
  await env.step("Needs changes");
  const v = env.verdict(ID);
  assert.deepEqual(v.comments, [{ file: OUTSIDE, note: "typo on line 3" }]);
  assert.equal(v.verdict, "changes");
  assert.equal(v.notes, "");
  assert.equal(v.files.length, 3);
});

// Adversarial where: any change event is credited as the human's edit: a rewrite
// while the window is in the background, a change to a file that is not the one
// in front, a change that carries no content, a file the review does not list,
// or a change that happened before the review.
test("edits come only from typing in a listed file whose editor is in front in a focused window", async (t) => {
  const rows = [
    { name: "typing in the focused editor of a listed file", expect: [PLAN], run: async (e) => { await e.open(PLAN); await e.typedIn(PLAN); } },
    { name: "typing twice lists the file once", expect: [PLAN], run: async (e) => { await e.open(PLAN); await e.typedIn(PLAN); await e.typedIn(PLAN); } },
    { name: "typing in two listed files lists both", expect: [DETAIL, PLAN], run: async (e) => { await e.open(PLAN); await e.typedIn(PLAN); await e.open(DETAIL); await e.typedIn(DETAIL); } },
    { name: "a change while the window is not focused", expect: [], run: async (e) => { await e.open(PLAN); e.host.setWindowFocus(false); await e.typedIn(PLAN); } },
    { name: "a change to a listed file whose editor is not the one in front", expect: [], run: async (e) => { await e.open(PLAN); await e.open(DETAIL); await e.typedIn(PLAN); } },
    { name: "an event that carries no content change", expect: [], run: async (e) => { await e.open(PLAN); e.host.type(e.abs(PLAN), { changes: 0 }); await e.settle(); } },
    { name: "typing in a markdown file the review does not list", expect: [], run: async (e) => { await e.open(OUTSIDE); await e.typedIn(OUTSIDE); } },
  ];
  for (const row of rows) {
    await t.test(row.name, async (st) => {
      const env = await openSet(st);
      await row.run(env);
      assert.equal(env.button("Needs changes").disabled, row.expect.length === 0);
      await env.approve();
      assert.deepEqual([...env.verdict(ID).edited].sort(), row.expect);
      assert.deepEqual(env.verdict(ID).comments, []);
    });
  }
  await t.test("typing before the review arrived is not carried", async (st) => {
    const { env, activate } = await begin(st);
    await activate();
    await env.open(PLAN);
    await env.typedIn(PLAN);
    await env.arrive(request(ID, SET));
    await env.ready();
    await env.approve();
    assert.deepEqual(env.verdict(ID).edited, []);
  });
});

// Adversarial where: Needs changes is enabled with nothing written, looks only
// at the note of the file in view, stays off after an edit or an outside note,
// never switches off when a note is cleared, or Approve waits for a note.
test("Needs changes stays off until a note, an outside note or an edit exists, and Approve never waits", async (t) => {
  await t.test("nothing written", async (st) => {
    const env = await openSet(st);
    assert.equal(env.button("Needs changes").disabled, true);
    assert.notEqual(env.button("Approve").disabled, true);
  });
  await t.test("a note on a file other than the one in view, then cleared", async (st) => {
    const env = await openSet(st);
    await env.goToRow(2);
    await env.type(env.notes(), "see this");
    await env.goToRow(0);
    assert.equal(env.button("Needs changes").disabled, false);
    await env.goToRow(2);
    await env.type(env.notes(), "");
    assert.equal(env.button("Needs changes").disabled, true);
  });
  await t.test("a whitespace-only note", async (st) => {
    const env = await openSet(st);
    await env.goToRow(1);
    await env.type(env.notes(), "  ");
    assert.equal(env.button("Needs changes").disabled, true);
  });
  await t.test("a note on an outside file, then cleared", async (st) => {
    const env = await openSet(st);
    await env.open(OUTSIDE);
    await env.type(env.fileNote(), "see this");
    assert.equal(env.button("Needs changes").disabled, false);
    await env.type(env.fileNote(), "");
    assert.equal(env.button("Needs changes").disabled, true);
  });
  await t.test("an edit to a listed file", async (st) => {
    const env = await openSet(st);
    await env.open(PLAN);
    await env.typedIn(PLAN);
    assert.equal(env.button("Needs changes").disabled, false);
  });
});

// ---- the answer ----

// Adversarial where: the answer lists files in the order they were visited or
// noted instead of the request's, writes `read` as a string or omits it, writes
// an empty `note`, puts the notes in another format, takes a new id instead of
// the request's, names the wrong `file`, leaves a temporary file beside it, or
// removes the request.
test("the answer lists every file in request order with read and note, and is one file beside its request", async (t) => {
  const env = await openSet(t);
  await env.goToRow(2);
  await env.type(env.notes(), "check the table");
  await env.goToRow(1);
  await env.type(env.notes(), "reorder");
  await env.goToRow(2);
  await env.approve();
  const v = env.verdict(ID);
  assert.deepEqual(Object.keys(v).sort(), ["at", "comments", "edited", "file", "files", "id", "notes", "verdict"]);
  assert.equal(v.id, ID);
  assert.equal(v.file, SPEC);
  assert.equal(v.verdict, "approved");
  assert.deepEqual(v.files, [
    { file: SPEC, read: true },
    { file: PLAN, read: true, note: "reorder" },
    { file: DETAIL, read: true, note: "check the table" },
  ]);
  const lines = v.notes.split("\n");
  assert.equal(lines.length, 2);
  assert.match(lines[0], /^plan(\.md)?: reorder$/);
  assert.match(lines[1], /^detail(\.md)?: check the table$/);
  assert.deepEqual(v.comments, []);
  assert.deepEqual(v.edited, []);
  assert.ok(!Number.isNaN(Date.parse(v.at)));
  assert.deepEqual(fs.readdirSync(env.reviewDir()).sort(), [`${ID}.request.json`, `${ID}.verdict.json`]);
});

// Adversarial where: a file never opened is recorded as read (the first-file
// mark leaking to all), or an unread file's entry carries a note key.
test("an answer given without reading marks the unopened files unread and carries no notes", async (t) => {
  const env = await openSet(t);
  await env.approve();
  const v = env.verdict(ID);
  assert.deepEqual(v.files, [{ file: SPEC, read: true }, { file: PLAN, read: false }, { file: DETAIL, read: false }]);
  assert.equal(v.notes, "");
});

// Adversarial where: the answer is written before the listed editors are saved
// (so the text Compass reads back is stale), an unlisted document is saved as
// well, or a clean document is saved needlessly.
test("the answer saves the dirty listed documents first and no others", async (t) => {
  const env = await openSet(t);
  await env.open(PLAN);
  await env.typedIn(PLAN);
  await env.open(OUTSIDE);
  await env.typedIn(OUTSIDE);
  const answered = [];
  env.doc(PLAN).save = async function () { answered.push(env.hasVerdict(ID)); this.saved++; this.isDirty = false; };
  await env.step("Approve");
  assert.equal(env.doc(PLAN).saved, 1);
  assert.deepEqual(answered, [false], "saved before the answer exists");
  assert.equal(env.doc(OUTSIDE).saved, 0);
  assert.equal(env.doc(SPEC).saved, 0);
  assert.deepEqual(env.verdict(ID).edited, [PLAN]);
});

// Adversarial where: two quick clicks, or a click after the answer, write the
// answer twice or rewrite it.
test("two clicks write one answer", async (t) => {
  const env = await openSet(t);
  verdictWrites.length = 0;
  const button = env.button("Approve");
  dispatch(button, "click");
  dispatch(button, "click");
  await env.settle();
  await env.settle();
  assert.equal(verdictWrites.length, 1);
  assert.equal(env.verdict(ID).verdict, "approved");
});

// Adversarial where: a request that was withdrawn still gets its answer, whether
// the withdrawal reached the extension before the click, while the save waits,
// or only as a missing file.
test("a withdrawn request sends nothing", async (t) => {
  await t.test("withdrawn before the click and announced", async (st) => {
    const env = await openSet(st);
    verdictWrites.length = 0;
    fs.unlinkSync(env.requestFile(ID));
    env.host.fire("delete", env.requestFile(ID));
    await env.until(() => !env.card() || env.button("Approve").disabled === true, "the card of a withdrawn request to go or be switched off");
    assert.equal(env.hasVerdict(ID), false);
    assert.deepEqual(verdictWrites, []);
  });
  await t.test("withdrawn while the save of an editor is waiting", async (st) => {
    const env = await openSet(st);
    await env.open(PLAN);
    await env.typedIn(PLAN);
    let release;
    const held = new Promise((r) => { release = r; });
    env.doc(PLAN).save = () => held;
    verdictWrites.length = 0;
    const pending = env.button("Approve");
    dispatch(pending, "click");
    await env.settle();
    fs.unlinkSync(env.requestFile(ID));
    env.host.fire("delete", env.requestFile(ID));
    await sleep(50);
    release(true);
    await env.settle();
    await sleep(100);
    assert.equal(env.hasVerdict(ID), false);
    assert.deepEqual(verdictWrites, []);
  });
  await t.test("withdrawn with no event before the click", async (st) => {
    const env = await openSet(st);
    verdictWrites.length = 0;
    fs.unlinkSync(env.requestFile(ID));
    dispatch(env.button("Approve"), "click");
    await env.settle();
    await sleep(100);
    assert.equal(env.hasVerdict(ID), false);
    assert.deepEqual(verdictWrites, []);
  });
});

// ---- several reviews, one request ----

// Adversarial where: the walk state is shared between cards, so stepping or
// answering one review moves or answers the other.
test("two cards walk and answer independently", async (t) => {
  const env = await openSet(t);
  await env.arrive(request(ID2, [DOCK_A, DOCK_B], { session: SESSION_B }));
  await env.ready(ID2);
  assert.deepEqual(env.cardIds().sort(), [ID, ID2].sort());
  await env.step("Next", ID2);
  assert.equal(env.position(ID2), "File 2 of 2");
  assert.equal(env.position(ID), "File 1 of 3");
  assert.deepEqual(env.marks(ID), ["read", "unread", "unread"]);
  await env.open(DETAIL);
  assert.equal(env.position(ID), "File 3 of 3");
  assert.equal(env.position(ID2), "File 2 of 2", "a file of one review does not move the other");
  await env.approve(ID2);
  assert.deepEqual(env.verdict(ID2).files, [{ file: DOCK_A, read: true }, { file: DOCK_B, read: true }]);
  assert.equal(env.hasVerdict(ID), false);
  assert.ok(env.card(ID), "the other review is still waiting");
  assert.notEqual(env.button("Approve", ID).disabled, true);
});

// Adversarial where: a request without a `files` list (a one-file review) draws
// a card without the position line, leaves navigation on, or answers with a
// `files` list or a note prefixed with a file name, so an old reader breaks.
test("a one-file request draws File 1 of 1 and its answer has no files list and the note as written", async (t) => {
  const { env, activate } = await begin(t);
  fs.mkdirSync(env.reviewDir(), { recursive: true });
  const one = request(ID, [SPEC]);
  delete one.files;
  delete one.session;
  delete one.project;
  fs.writeFileSync(env.requestFile(ID), JSON.stringify(one));
  await activate();
  await env.ready();
  assert.equal(env.position(), "File 1 of 1");
  assert.equal(env.rows().length, 1);
  for (const name of ["Previous", "Next", "Next unread"]) assert.equal(env.button(name).disabled, true, name);
  await env.type(env.notes(), "fine");
  await env.approve();
  const v = env.verdict(ID);
  assert.equal("files" in v, false);
  assert.equal(v.notes, "fine");
  assert.equal(v.file, SPEC);
});

// Adversarial where: the project line shows the full session id, a session code
// of the wrong length, another card's names, or a Session label with nothing
// after it; the project falls back to something other than the folder.
test("a card names its project and the first six characters of its session, and leaves Session out when there is none", async (t) => {
  await t.test("the request's project and session", async (st) => {
    const env = await openSet(st);
    const text = env.card().textContent;
    assert.ok(env.label("Project") && env.label("Session"));
    assert.ok(text.includes("harbor") && text.includes("7f3a91") && !text.includes("7f3a91c"));
    assert.ok(!text.includes("orchard"));
  });
  await t.test("an empty session leaves the Session label out", async (st) => {
    const env = await openSet(st, { req: { session: "" } });
    assert.ok(env.label("Project"));
    assert.equal(env.label("Session"), undefined);
  });
  await t.test("with no project on the request, the folder holding the vault is named", async (st) => {
    const env = await openSet(st, { req: { project: undefined } });
    assert.ok(env.card().textContent.includes("orchard"));
  });
});

// ---- the panel coming and going ----

// Adversarial where: the walk lives in the page, so hiding the panel (choosing
// the Explorer icon) or closing it loses the notes, read marks and position of a
// review in progress.
test("notes, marks and position survive the panel being hidden, shown, closed and opened again", async (t) => {
  const env = await openSet(t);
  await env.goToRow(1);
  await env.type(env.notes(), "keep me");
  await env.open(OUTSIDE);
  await env.type(env.fileNote(), "and me");
  env.host.hideView();
  await env.settle();
  assert.equal(env.page, null);
  env.host.showView();
  await env.ready();
  assert.equal(env.position(), "File 2 of 3");
  assert.deepEqual(env.marks(), ["read", "read", "unread"]);
  assert.equal(env.notes().value, "keep me");
  assert.equal(env.fileNote().value, "and me");
  env.host.disposeView();
  await env.settle();
  const container = env.host.package.contributes.viewsContainers.activitybar[0].id;
  await env.host.api.commands.executeCommand(`workbench.view.extension.${container}`);
  await env.ready();
  assert.equal(env.position(), "File 2 of 3");
  assert.equal(env.notes().value, "keep me");
  await env.open(PLAN);
  await env.approve();
  assert.deepEqual(env.verdict(ID).files.map((f) => f.note), [undefined, "keep me", undefined]);
  assert.deepEqual(env.verdict(ID).comments, [{ file: OUTSIDE, note: "and me" }]);
});

// ---- an answer already given elsewhere ----

// Adversarial where: another window (the same folder open in both VS Code and
// Cursor claims one request) or another surface answered since the last
// recheck, and the click rewrites that verdict, so Compass acts on one answer
// while the human saw another.
test("a click after another surface already answered leaves that answer as it is", async (t) => {
  const env = await openSet(t);
  const first = { id: ID, file: SPEC, verdict: "changes", notes: "answered first", comments: [], edited: [], at: "2026-10-28T10:16:00.000Z" };
  fs.writeFileSync(env.verdictFile(ID), JSON.stringify(first));
  verdictWrites.length = 0;
  dispatch(env.button("Approve"), "click");
  await env.settle();
  await sleep(100);
  assert.deepEqual(env.verdict(ID), first);
  assert.deepEqual(verdictWrites, []);
});

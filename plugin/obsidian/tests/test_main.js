// Tests for the Compass Review plugin, run with `node --test`. The `obsidian`
// and `electron` modules and the DOM helpers Obsidian adds are stubbed, so
// the plugin's request, panel, bar, verdict, rename and step-aside paths run
// without Obsidian.

const test = require("node:test");
const assert = require("node:assert/strict");
const Module = require("node:module");
const path = require("node:path");
const fs = require("node:fs");

// ---- minimal DOM: just what the plugin touches ----
// A selector is an optional tag followed by any number of `.class` parts.
function matches(el, sel) {
  const m = /^([a-z0-9]*)((?:\.[\w-]+)*)$/i.exec(sel);
  if (!m) return false;
  const have = el.cls.split(" ");
  return (!m[1] || el.tag === m[1]) && m[2].split(".").filter(Boolean).every((c) => have.includes(c));
}
class El {
  constructor(tag, opts = {}) {
    this.tag = tag;
    this.cls = opts.cls || "";
    this.text = opts.text || "";
    this.type = opts.type;
    this.placeholder = opts.placeholder;
    this.href = opts.href;
    this.value = opts.value !== undefined ? opts.value : "";
    this.dataset = {};
    this.style = {};
    this.attrs = { ...(opts.attr || {}) };
    this.children = [];
    this.parent = null;
    this.onclick = null;
    this.handlers = {};
  }
  addEventListener(type, fn) { (this.handlers[type] = this.handlers[type] || []).push(fn); }
  createEl(tag, opts) { const e = new El(tag, opts); e.parent = this; this.children.push(e); return e; }
  createDiv(opts) { return this.createEl("div", opts); }
  createSpan(opts) { return this.createEl("span", opts); }
  insertBefore(el, ref) {
    el.parent = this;
    const i = ref ? this.children.indexOf(ref) : -1;
    if (i < 0) this.children.push(el); else this.children.splice(i, 0, el);
  }
  empty() { this.children.forEach((c) => { c.parent = null; }); this.children = []; }
  setText(t) { this.text = t; }
  appendText(t) { this.text += t; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  createSvg(tag, opts) { return this.createEl(tag, opts); }
  toggleClass(c, on) { if (on) { if (!this.cls.split(" ").includes(c)) this.addClass(c); } else this.removeClass(c); }
  closest(sel) { for (let n = this; n; n = n.parent) if (matches(n, sel)) return n; return null; }
  addClass(c) { this.cls = this.cls ? `${this.cls} ${c}` : c; }
  removeClass(c) { this.cls = this.cls.split(" ").filter((x) => x && x !== c).join(" "); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); this.parent = null; }
  all() { return [this, ...this.children.flatMap((c) => c.all())]; }
  querySelector(sel) { return this.all().slice(1).find((e) => matches(e, sel)) || null; }
  querySelectorAll(sel) { return this.all().slice(1).filter((e) => matches(e, sel)); }
}
global.createDiv = (opts) => new El("div", opts);
global.document = new El("document");
global.window = globalThis;

// ---- obsidian and electron stubs ----
const notices = [];
// `hasFocus` is what the window reports before anything raises it; raising it
// (`focus()`) gives it focus, as Electron does.
const win = { minimized: 0, focused: 0, hasFocus: false, onTop: [], restore() {}, isMinimized: () => false,
  isFocused() { return this.hasFocus; },
  setAlwaysOnTop(v) { this.onTop.push(v); }, show() {}, focus() { this.focused++; this.hasFocus = true; }, minimize() { this.minimized++; } };
class Plugin {
  constructor(app) { this.app = app; this.intervals = []; }
  registerEvent() {}
  // The timer is cleared at once so the test process can exit; the id is kept for assertions.
  registerInterval(id) { this.intervals.push(id); clearInterval(id); return id; }
  registerObsidianProtocolHandler(name, fn) { this.handler = fn; }
  registerView(type, factory) { this.app.viewFactories[type] = factory; }
  addCommand() {}
  addRibbonIcon() { return new El("div"); }
}
// A view in a sidebar leaf: containerEl.children[0] is the header, children[1] the content.
class ItemView {
  constructor(leaf) {
    this.leaf = leaf;
    this.app = leaf.app;
    this.containerEl = new El("view-container");
    this.containerEl.createEl("div", { cls: "view-header" });
    this.contentEl = this.containerEl.createEl("div", { cls: "view-content" });
  }
  getViewType() { return ""; }
  getDisplayText() { return ""; }
  async onOpen() {}
  async onClose() {}
}
class MarkdownView { constructor(file) { this.file = file; this.saved = 0; this.containerEl = new El("view"); this.containerEl.createEl("div", { cls: "view-content" }); } async save() { this.saved++; } }
// Obsidian's own Mermaid: `loadMermaid()` resolves to an object whose `render(id, source)`
// resolves to { svg }. The svg the stub returns carries the source it drew, so a
// test reads what each chart element holds. A test sets `loadError`,
// `renderError` or `renderGate` (a promise render waits on) to steer it.
const mermaidState = { calls: [], loadError: null, renderError: null, renderGate: null };
const mermaidStub = {
  async render(id, source) {
    mermaidState.calls.push({ id, source });
    if (mermaidState.renderGate) await mermaidState.renderGate;
    if (mermaidState.renderError) throw mermaidState.renderError;
    return { svg: `<svg data-source="${encodeURIComponent(source)}"></svg>` };
  },
};
async function loadMermaid() {
  if (mermaidState.loadError) throw mermaidState.loadError;
  return mermaidStub;
}
const stubs = {
  obsidian: { Plugin, ItemView, MarkdownView, loadMermaid, Notice: class { constructor(m) { notices.push(m); } } },
  electron: { remote: { getCurrentWindow: () => win, app: { hide() { win.minimized++; } } } },
};
const origResolve = Module._resolveFilename;
Module._resolveFilename = function (req, ...rest) { return stubs[req] ? req : origResolve.call(this, req, ...rest); };
for (const [name, exp] of Object.entries(stubs)) require.cache[name] = { id: name, filename: name, loaded: true, exports: exp };

const CompassReview = require(path.join(__dirname, "..", "compass-review", "main.js"));

// ---- a fake app over an in-memory vault ----
// Opening a file in a leaf makes it the active file and fires the workspace's
// `file-open` and `layout-change` events, as Obsidian does.
function makeApp(files) {
  const store = new Map(Object.entries(files));
  const leaves = [];
  const panelLeaves = [];
  const revealed = [];
  // Vault events by name; `modify` is the file-changed event, which the plugin
  // does not subscribe to, so firing it reaches no handler.
  const listeners = { async modify() {} };
  const wsListeners = {};
  const fire = (name, ...args) => { if (wsListeners[name]) wsListeners[name](...args); };
  // Several handlers for one event run in registration order behind one entry,
  // so a second subscriber never replaces the first.
  const chain = (map, name, fn) => {
    const prev = map[name];
    if (!prev) { map[name] = fn; return; }
    map[name] = (...args) => {
      const a = prev(...args);
      const b = fn(...args);
      return (a && a.then) || (b && b.then) ? Promise.all([a, b]) : (b || a);
    };
  };
  // Every file opened in a leaf, with the state it was opened with (a line, for
  // an eState of { line }).
  const opened = [];
  const app = {
    store,
    active: null,
    viewFactories: {},
    vault: {
      adapter: {
        async read(p) { if (!store.has(p)) throw new Error(`ENOENT ${p}`); return store.get(p); },
        async write(p, d) { store.set(p, d); },
        async exists(p) { return store.has(p) || [...store.keys()].some((k) => k.startsWith(p + "/")); },
        async list(dir) { return { files: [...store.keys()].filter((k) => path.posix.dirname(k) === dir), folders: [] }; },
      },
      getAbstractFileByPath(p) { return store.has(p) ? { path: p, basename: path.posix.basename(p, ".md"), extension: "md" } : null; },
      on(name, fn) { chain(listeners, name, fn); },
    },
    workspace: {
      getLeavesOfType: (type) => (type === "markdown" ? leaves : panelLeaves.filter((l) => l.view && l.view.getViewType() === type)),
      getLeaf() {
        const leaf = { view: new MarkdownView(null), async openFile(f, state) { this.view.file = f; app.active = f; opened.push({ path: f.path, state }); fire("file-open", f); fire("layout-change"); } };
        leaves.push(leaf);
        return leaf;
      },
      getRightLeaf() {
        const leaf = {
          app, view: null,
          async setViewState(state) {
            const factory = app.viewFactories[state.type];
            if (!factory) throw new Error(`no view registered for ${state.type}`);
            this.view = factory(this);
            await this.view.onOpen();
          },
        };
        panelLeaves.push(leaf);
        return leaf;
      },
      async revealLeaf(leaf) { revealed.push(leaf); },
      async openLinkText(link, _source, _newLeaf, state) {
        const f = app.vault.getAbstractFileByPath(link);
        if (!f) return;
        await this.getLeaf(false).openFile(f, state);
      },
      getActiveFile: () => app.active,
      setActiveLeaf(leaf) { if (leaf.view && leaf.view.file) app.active = leaf.view.file; },
      on(name, fn) { chain(wsListeners, name, fn); },
      onLayoutReady(fn) { this.ready = fn; },
    },
    // The `title` property of a file, as Obsidian's metadata cache reports it.
    metadataCache: {
      getFileCache(f) {
        const m = /^---\ntitle: "?([^"\n]*)"?\n---/.exec(store.get(f.path) || "");
        return m ? { frontmatter: { title: m[1] } } : {};
      },
    },
    listeners,
    wsListeners,
    opened,
    leaves,
    panelLeaves,
    revealed,
  };
  return app;
}

async function loaded(files) {
  const app = makeApp(files);
  const plugin = new CompassReview(app);
  await plugin.onload();
  return { app, plugin };
}

const req = (id, file, extra = {}) => JSON.stringify({ id, file, title: "T", return: true, ...extra });
// The one-line bar on a reviewed document, and the review panel's cards.
const bar = (app) => app.leaves.map((l) => l.view.containerEl.querySelector(".compass-review-bar")).find(Boolean);
const button = (root, text) => root.all().find((c) => c.tag === "button" && c.text === text);

test.beforeEach(() => { notices.length = 0; win.minimized = 0; win.focused = 0; win.hasFocus = false; win.onTop = []; });

const sleep = () => new Promise((r) => setImmediate(r));
const mdFile = (p) => ({ path: p, basename: path.posix.basename(p, ".md"), extension: "md" });
const barIn = (leaf) => leaf.view.containerEl.querySelector(".compass-review-bar");
const barText = (b) => b.all().map((e) => e.text).join(" ");

// Puts a markdown file in view in a leaf, as navigating to it does.
function show(app, leaf, p) {
  const f = mdFile(p);
  leaf.view.file = f;
  app.active = f;
  if (app.wsListeners["file-open"]) app.wsListeners["file-open"](f);
  if (app.wsListeners["layout-change"]) app.wsListeners["layout-change"]();
}

const viewOfType = (app, type) => (app.panelLeaves.find((l) => l.view && l.view.getViewType() === type) || {}).view || null;
const panelView = (app) => viewOfType(app, "compass-review-panel");
const panelEl = (app) => { const v = panelView(app); return v ? v.containerEl.children[1] : null; };
const cards = (app) => { const p = panelEl(app); return p ? p.querySelectorAll(".compass-review-card") : []; };
const cardIds = (app) => cards(app).map((c) => c.dataset.id);
const cardFor = (app, id) => cards(app).find((c) => c.dataset.id === id);
const cardBtn = (app, id, text) => button(cardFor(app, id), text);
const thisFileIn = (card) => card.querySelector(".compass-review-this-file");
const fileNoteIn = (card) => { const block = thisFileIn(card); return block && block.all().find((e) => e.tag === "textarea"); };
const notesIn = (card) => {
  const block = thisFileIn(card);
  const inBlock = block ? block.all() : [];
  return card.all().find((e) => e.tag === "textarea" && e.cls.split(" ").includes("compass-review-notes") && !inBlock.includes(e));
};
const linkIn = (card) => card.querySelector(".compass-review-file");
const feedbackOf = (card) => {
  const list = card.querySelector(".compass-review-feedback");
  return list ? list.all().filter((e) => e.tag === "li").map((li) => li.all().map((e) => e.text).join("")) : [];
};
const trailCount = (app) => [...app.leaves.map((l) => l.view.containerEl), ...app.panelLeaves.filter((l) => l.view).map((l) => l.view.containerEl)]
  .flatMap((h) => h.querySelectorAll(".compass-review-trail")).length;
async function closePanel(app) {
  for (const l of [...app.panelLeaves]) if (l.view) await l.view.onClose();
  app.panelLeaves.length = 0;
}

// A click reaches `onclick` or a `click` listener, whichever the plugin attached.
function click(el) {
  const fn = typeof el.onclick === "function" ? el.onclick : (el.handlers.click || [])[0];
  assert.ok(fn, `no click handler on <${el.tag}> "${el.text}"`);
  return fn.call(el, { target: el, preventDefault() {}, stopPropagation() {} });
}

// A text field reports its value through its handlers: the stub DOM has no
// events, so a test sets `.value` and calls whichever of `on<type>` or the
// addEventListener handlers the plugin attached, for both `input` and `change`.
function typeInto(el, value) {
  assert.ok(el, "text field to type into is missing");
  el.value = value;
  for (const type of ["input", "change"]) {
    if (typeof el["on" + type] === "function") el["on" + type]({ target: el });
    for (const fn of el.handlers[type] || []) fn({ target: el });
  }
}

const verdictOf = (app, p) => JSON.parse(app.store.get(p));

// ---- request and verdict through the panel ----

// Adversarial where: a request opens the file but not the panel (or opens a
// panel nobody reveals), the card lacks a verdict button, or the old
// slim/verdict bar is what appears instead.
test("a request opens the file, raises the window, opens and reveals the panel with a card, and puts a bar on the document", async () => {
  const { app, plugin } = await loaded({ "specs/a.md": "x", "tmp/review/1.request.json": req("1", "specs/a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  assert.equal(app.leaves[0].view.file.path, "specs/a.md");
  assert.equal(win.focused, 1);
  assert.deepEqual(win.onTop, [true]);
  const panel = panelView(app);
  assert.ok(panel, "panel opened");
  assert.equal(panel.getViewType(), "compass-review-panel");
  assert.ok(app.revealed.includes(panel.leaf), "panel revealed");
  assert.deepEqual(cardIds(app), ["1"]);
  assert.ok(button(cardFor(app, "1"), "Approve") && button(cardFor(app, "1"), "Needs changes"));
  assert.equal(bar(app).dataset.id, "1");
});

// Adversarial where: the panel click path differs from the old bar's: the
// editor is not saved, the verdict lands at the wrong path or without the
// typed note, Obsidian does not step aside, or the card/bar outlive the verdict;
// all with a different file in view, which the old bar could never see.
test("approve from the panel while another file is in view saves the editor, writes the verdict next to the request, and steps aside", async () => {
  const { app, plugin } = await loaded({ "specs/a.md": "x", "b.md": "y", ".compass/tmp/review/1.request.json": req("1", "specs/a.md") });
  await plugin.handler({ request: ".compass/tmp/review/1.request.json" });
  const other = app.workspace.getLeaf(true);
  await other.openFile(mdFile("b.md"));
  assert.ok(thisFileIn(cardFor(app, "1")), "another file is in view");
  typeInto(notesIn(cardFor(app, "1")), "looks good");
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  const verdict = JSON.parse(app.store.get(".compass/tmp/review/1.verdict.json"));
  assert.equal(verdict.verdict, "approved");
  assert.equal(verdict.notes, "looks good");
  assert.equal(verdict.id, "1");
  assert.equal(app.leaves[0].view.saved, 1);
  assert.equal(win.minimized, 1);
  assert.equal(cardFor(app, "1"), undefined, "card removed after the verdict");
  assert.equal(bar(app), undefined, "bar removed after the verdict");
});

// Adversarial where: Needs changes from the panel ignores `return: false` on a
// review found at start-up and steps Obsidian aside anyway, or writes the wrong
// verdict word.
test("return false keeps Obsidian in front after the verdict of a review found at start-up", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/2.request.json": req("2", "a.md", { return: false }) });
  await app.workspace.ready();
  await sleep();
  await plugin.openPanel();
  typeInto(notesIn(cardFor(app, "2")), "redo");
  await click(cardBtn(app, "2", "Needs changes"));
  await sleep();
  assert.equal(JSON.parse(app.store.get("tmp/review/2.verdict.json")).verdict, "changes");
  assert.equal(win.minimized, 0);
});

// Adversarial where: answering one of two pending reviews hides Obsidian while
// the other still waits, or the step aside a `return` review asked for is lost
// because the last review answered came without it.
test("Obsidian steps aside only after the last pending review is answered", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x",
    "b.md": "y",
    "tmp/review/5.request.json": req("5", "a.md"),
    "tmp/review/6.request.json": req("6", "b.md", { return: false }),
  });
  await plugin.handler({ request: "tmp/review/5.request.json" });
  await plugin.handler({ request: "tmp/review/6.request.json" });
  await click(cardBtn(app, "5", "Approve"));
  await sleep();
  assert.equal(win.minimized, 0, "a review is still pending");
  assert.deepEqual(cardIds(app), ["6"]);
  await click(cardBtn(app, "6", "Approve"));
  await sleep();
  assert.equal(win.minimized, 1);
});

test("a link with no request reports a failure and writes nothing", async () => {
  const { app, plugin } = await loaded({ "a.md": "x" });
  await plugin.handler({});
  assert.match(notices[0], /request failed - the compass-review link names no request/);
  assert.equal(app.leaves.length, 0);
});

test("a request for a file outside the vault reports a failure", async () => {
  const { plugin } = await loaded({ "tmp/review/3.request.json": req("3", "gone.md") });
  await plugin.handler({ request: "tmp/review/3.request.json" });
  assert.match(notices[0], /file not in this vault: gone.md/);
});

test("a malformed request reports a failure", async () => {
  const { plugin } = await loaded({ "tmp/review/4.request.json": '{"file": 1}' });
  await plugin.handler({ request: "tmp/review/4.request.json" });
  assert.match(notices[0], /malformed request/);
});

// Adversarial where: the older request for a file stays as a second card (or
// the stale bar id stays) after a newer request for the same file.
test("a second request for the same file replaces the first", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "tmp/review/5.request.json": req("5", "a.md"), "tmp/review/6.request.json": req("6", "a.md") });
  await plugin.handler({ request: "tmp/review/5.request.json" });
  await plugin.handler({ request: "tmp/review/6.request.json" });
  assert.equal(bar(app).dataset.id, "6");
  assert.deepEqual([...plugin.pending.keys()], ["6"]);
  assert.deepEqual(cardIds(app), ["6"]);
});

// Adversarial where: a rename leaves the panel pointing at the old path: the
// card still treats the renamed reviewed file as "another file", or the
// verdict names the old path.
test("a renamed file keeps its bar and card, and the verdict names the new path", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/7.request.json": req("7", "a.md") });
  await plugin.handler({ request: "tmp/review/7.request.json" });
  app.leaves[0].view.file = mdFile("b.md");
  app.active = mdFile("b.md");
  app.listeners.rename({ path: "b.md" }, "a.md");
  assert.ok(bar(app), "bar follows the rename");
  assert.deepEqual(cardIds(app), ["7"]);
  assert.equal(thisFileIn(cardFor(app, "7")), null, "the renamed reviewed file is still the reviewed file");
  await click(cardBtn(app, "7", "Approve"));
  await sleep();
  assert.equal(JSON.parse(app.store.get("tmp/review/7.verdict.json")).file, "b.md");
});

test("startup scan picks up unanswered requests without raising, and skips answered ones", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y",
    "tmp/review/8.request.json": req("8", "a.md"),
    "tmp/review/9.request.json": req("9", "b.md"), "tmp/review/9.verdict.json": "{}",
    "tmp/review/bad.request.json": "{nope",
  });
  await app.workspace.ready();
  await new Promise((r) => setImmediate(r));
  assert.deepEqual([...plugin.pending.keys()], ["8"]);
  assert.equal(win.focused, 0);
});

test("startup scan leaves a request addressed to another surface alone", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y",
    "tmp/review/10.request.json": req("10", "a.md", { surface: "vscode" }),
    "tmp/review/11.request.json": req("11", "b.md", { surface: "obsidian" }),
  });
  await app.workspace.ready();
  await new Promise((r) => setImmediate(r));
  assert.deepEqual([...plugin.pending.keys()], ["11"]);
});

test("verdictPathFor swaps only the suffix", () => {
  assert.equal(CompassReview.verdictPathFor("x.request.json/tmp/review/1.request.json"), "x.request.json/tmp/review/1.verdict.json");
});

// ---- the panel: it stays in view while the human moves around the vault ----

// Adversarial where: the panel is created at load with nothing to review, a
// second request opens a second panel, a request does not reveal a panel that
// was already open, or navigation rebuilds or duplicates the panel.
test("the panel opens only on a request, is revealed on every request, and stays one panel through navigation", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "tmp/review/1.request.json": req("1", "a.md"), "tmp/review/2.request.json": req("2", "b.md") });
  assert.equal(app.panelLeaves.length, 0, "no panel before a request");
  assert.ok(app.viewFactories["compass-review-panel"], "the panel view type is registered");
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const first = panelView(app);
  assert.equal(app.panelLeaves.length, 1);
  await plugin.handler({ request: "tmp/review/2.request.json" });
  assert.equal(app.panelLeaves.length, 1, "a second request reuses the panel");
  assert.equal(app.revealed.filter((l) => l === first.leaf).length >= 2, true, "every request reveals the panel");
  show(app, app.leaves[0], "a.md");
  show(app, app.leaves[1], "b.md");
  assert.equal(app.panelLeaves.length, 1, "navigation leaves one panel");
  assert.equal(panelView(app), first, "navigation keeps the same panel view");
});

// Adversarial where: the question falls back wrongly: a missing title shows
// nothing, an empty-string title shows an empty question, or the title is
// shown with the file path instead.
test("a card's question is the request title, or the file name when the title is missing or empty", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "specs/c.md": "z",
    "tmp/review/1.request.json": req("1", "a.md", { title: "Approve this spec?" }),
    "tmp/review/2.request.json": req("2", "b.md", { title: undefined }),
    "tmp/review/3.request.json": req("3", "specs/c.md", { title: "" }) });
  for (const id of ["1", "2", "3"]) await plugin.handler({ request: `tmp/review/${id}.request.json` });
  const question = (id) => cardFor(app, id).querySelector(".compass-review-question").text;
  assert.equal(question("1"), "Approve this spec?");
  assert.equal(question("2"), "b");
  assert.equal(question("3"), "c");
});

// Adversarial where: cards sit in arrival order or follow which reviewed file
// was opened last, so the newest request is not on top.
test("with two reviews pending, the cards are newest first and opening a reviewed file does not reorder them", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "c.md": "z",
    "tmp/review/1.request.json": req("1", "a.md", { title: "Alpha" }),
    "tmp/review/2.request.json": req("2", "b.md", { title: "Beta" }) });
  await plugin.handler({ request: "tmp/review/2.request.json" });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  assert.deepEqual(cardIds(app), ["1", "2"]);
  assert.equal(cardFor(app, "1").querySelector(".compass-review-question").text, "Alpha");
  show(app, app.leaves[0], "b.md");
  assert.deepEqual(cardIds(app), ["1", "2"], "opening the older review's file leaves the order alone");
  show(app, app.leaves[0], "c.md");
  assert.deepEqual(cardIds(app), ["1", "2"]);
});

// Adversarial where: "On this file" shows on the reviewed file itself, shows
// for a non-markdown file or with nothing open, or is missing from cards whose
// reviewed file is not the one in view.
test("On this file shows on a card only while a markdown file other than its reviewed file is in view", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "c.md": "z", "data.json": "{}",
    "tmp/review/1.request.json": req("1", "a.md"), "tmp/review/2.request.json": req("2", "b.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await plugin.handler({ request: "tmp/review/2.request.json" });
  const rows = [
    { name: "nothing in view", file: null, one: false, two: false },
    { name: "the first review's file", file: mdFile("a.md"), one: false, two: true },
    { name: "the second review's file", file: mdFile("b.md"), one: true, two: false },
    { name: "an unrelated markdown file", file: mdFile("c.md"), one: true, two: true },
    { name: "a non-markdown file", file: { path: "data.json", basename: "data", extension: "json" }, one: false, two: false },
  ];
  for (const row of rows) {
    app.active = row.file;
    await plugin.renderPanel();
    assert.equal(Boolean(thisFileIn(cardFor(app, "1"))), row.one, `${row.name}: card 1`);
    assert.equal(Boolean(thisFileIn(cardFor(app, "2"))), row.two, `${row.name}: card 2`);
  }
});

// Adversarial where: the "Feedback so far" list lags the events (a note, an
// edit) until something else redraws the panel, lists a file twice, lists the
// bar note or an emptied note, or words the entries differently.
test("the feedback list shows each note and each edited file once, updating as they happen", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "z.md": "q",
    "tmp/review/1.request.json": req("1", "a.md", { files: [{ file: "a.md", why: "" }, { file: "z.md", why: "" }] }) });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  assert.deepEqual(feedbackOf(cardFor(app, "1")), []);
  show(app, app.leaves[0], "b.md");
  typeInto(fileNoteIn(cardFor(app, "1")), "merge D-03");
  assert.deepEqual(feedbackOf(cardFor(app, "1")), ["b.md: merge D-03"]);
  typeInto(notesIn(cardFor(app, "1")), "overall note");
  assert.deepEqual(feedbackOf(cardFor(app, "1")), ["b.md: merge D-03"], "the notes field is not feedback");
  typedIn(app, "z.md");
  typedIn(app, "z.md");
  typedIn(app, "a.md");
  assert.deepEqual([...feedbackOf(cardFor(app, "1"))].sort(), ["b.md: merge D-03", "edited: a.md", "edited: z.md"]);
  typeInto(fileNoteIn(cardFor(app, "1")), "");
  assert.deepEqual([...feedbackOf(cardFor(app, "1"))].sort(), ["edited: a.md", "edited: z.md"], "a cleared note leaves the list");
});

// Adversarial where: the reviewed document's bar still carries the notes
// input or verdict buttons, lacks the way to the panel, or cannot bring a
// closed panel back; or a slim bar survives anywhere.
test("the reviewed document carries a one-line bar that opens the panel, and no trail bar exists", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "b.md": "y", "tmp/review/1.request.json": req("1", "a.md", { title: "Alpha spec" }) });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const leaf = app.leaves[0];
  const b = barIn(leaf);
  assert.match(barText(b), /Alpha spec/);
  assert.equal(b.all().some((e) => e.tag === "input" || e.tag === "textarea"), false, "no notes field on the bar");
  assert.equal(button(b, "Approve"), undefined);
  assert.equal(button(b, "Needs changes"), undefined);
  assert.ok(button(b, "Open review panel"));
  await closePanel(app);
  assert.equal(app.panelLeaves.length, 0);
  await click(button(barIn(leaf), "Open review panel"));
  assert.equal(app.panelLeaves.length, 1, "the bar button brings the panel back");
  assert.ok(app.revealed.includes(panelView(app).leaf));
  assert.deepEqual(cardIds(app), ["1"]);
  show(app, leaf, "b.md");
  assert.equal(barIn(leaf), null, "another page carries no bar");
  assert.equal(trailCount(app), 0);
});

// Adversarial where: the panel keeps typed text only in its DOM, so closing
// and reopening it (or Obsidian rebuilding the view) loses the notes.
test("typed notes survive closing and reopening the panel", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "b.md": "y", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  show(app, app.leaves[0], "b.md");
  typeInto(notesIn(cardFor(app, "1")), "keep me");
  typeInto(fileNoteIn(cardFor(app, "1")), "page note");
  await closePanel(app);
  await plugin.openPanel();
  assert.equal(notesIn(cardFor(app, "1")).value, "keep me");
  assert.equal(fileNoteIn(cardFor(app, "1")).value, "page note");
});

// Adversarial where: workspace and vault events redraw a panel that is not
// open (null dereference) or conjure one nobody asked for, or edits seen while
// no panel exists are dropped.
test("events with no panel open do not throw or open one, and the edits they carry still count", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "b.md": "y", "z.md": "q", "tmp/review/1.request.json": req("1", "a.md") });
  await app.workspace.ready();
  await sleep();
  await closePanel(app);
  app.wsListeners["file-open"](mdFile("b.md"));
  app.wsListeners["layout-change"]();
  typedIn(app, "a.md");
  app.listeners.rename({ path: "b.md" }, "b.md");
  await plugin.recheck();
  assert.equal(app.panelLeaves.length, 0, "no panel conjured by events");
  await plugin.openPanel();
  assert.ok(feedbackOf(cardFor(app, "1")).includes("edited: a.md"));
});

// ---- Wave 2 behavior, now through the panel ----

// Adversarial where: a note typed on a linked file is lost when the human
// returns to the reviewed file or moves on, a blanked-out or whitespace-only
// note is reported as an empty comment, or the verdict schema omits
// `comments`/`edited` when nothing was written.
test("notes on other files land in comments, empty ones are omitted, and the verdict carries edited", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "c.md": "z", "d.md": "w", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const leaf = app.leaves[0];
  show(app, leaf, "b.md");
  typeInto(fileNoteIn(cardFor(app, "1")), "fix the heading");
  show(app, leaf, "c.md");
  assert.equal(fileNoteIn(cardFor(app, "1")).value, "", "another file starts with its own empty note");
  typeInto(fileNoteIn(cardFor(app, "1")), "temp");
  typeInto(fileNoteIn(cardFor(app, "1")), "");
  show(app, leaf, "d.md");
  typeInto(fileNoteIn(cardFor(app, "1")), "   ");
  show(app, leaf, "b.md");
  assert.equal(fileNoteIn(cardFor(app, "1")).value, "fix the heading", "the note stays with its file");
  show(app, leaf, "a.md");
  await click(cardBtn(app, "1", "Needs changes"));
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.deepEqual(v.comments, [{ file: "b.md", note: "fix the heading" }]);
  assert.deepEqual(v.edited, []);
  assert.equal(v.verdict, "changes");
  assert.deepEqual(Object.keys(v).sort(), ["at", "comments", "edited", "file", "id", "notes", "verdict"]);
});

// Adversarial where: edit tracking misses the reviewed file itself, counts
// non-markdown files, double-lists an autosaved file, or leaks edits made
// before the review existed into its verdict.
test("listed markdown files typed in while the review is pending land in edited, once each", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "z.md": "q",
    "tmp/review/1.request.json": req("1", "a.md", { files: [{ file: "a.md", why: "" }, { file: "b.md", why: "" }] }) });
  typedIn(app, "z.md");
  await plugin.handler({ request: "tmp/review/1.request.json" });
  typedIn(app, "b.md");
  typedIn(app, "b.md");
  typedIn(app, "a.md");
  app.wsListeners["editor-change"]({}, { file: { path: "data.json", basename: "data", extension: "json" } });
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.deepEqual([...v.edited].sort(), ["a.md", "b.md"]);
  assert.equal(v.verdict, "approved");
  assert.deepEqual(v.comments, []);
});

// Adversarial where: Needs changes is enabled with nothing to say (the
// verdict would carry no feedback), stays disabled after a note on another
// file or an edit, never re-disables when a note is cleared or is only
// whitespace, or one review's feedback enables another card's button.
test("Needs changes stays disabled until a note, a note on another file, or an edit exists, per card", async (t) => {
  const setup = async () => {
    const r = await loaded({ "a.md": "x", "b.md": "y", "tmp/review/1.request.json": req("1", "a.md") });
    await r.plugin.handler({ request: "tmp/review/1.request.json" });
    return { ...r, leaf: r.app.leaves[0] };
  };
  const changes = (app, id = "1") => cardBtn(app, id, "Needs changes");

  await t.test("nothing written", async () => {
    const { app } = await setup();
    assert.equal(changes(app).disabled, true);
    assert.notEqual(cardBtn(app, "1", "Approve").disabled, true, "Approve is never gated");
  });
  await t.test("a notes field entry, then cleared", async () => {
    const { app } = await setup();
    typeInto(notesIn(cardFor(app, "1")), "needs work");
    assert.equal(changes(app).disabled, false);
    typeInto(notesIn(cardFor(app, "1")), "");
    assert.equal(changes(app).disabled, true);
  });
  await t.test("a whitespace-only note", async () => {
    const { app } = await setup();
    typeInto(notesIn(cardFor(app, "1")), "   ");
    assert.equal(changes(app).disabled, true);
  });
  await t.test("a note on another file, then cleared", async () => {
    const { app, leaf } = await setup();
    show(app, leaf, "b.md");
    typeInto(fileNoteIn(cardFor(app, "1")), "see this");
    assert.equal(changes(app).disabled, false);
    typeInto(fileNoteIn(cardFor(app, "1")), "");
    assert.equal(changes(app).disabled, true);
  });
  await t.test("an edit to a file", async () => {
    const { app } = await setup();
    typedIn(app, "a.md");
    await sleep();
    assert.equal(changes(app).disabled, false);
  });
  await t.test("two reviews: an edit enables only the card it belongs to", async () => {
    const { app, plugin } = await setup();
    app.store.set("tmp/review/2.request.json", req("2", "b.md"));
    await plugin.handler({ request: "tmp/review/2.request.json" });
    typedIn(app, "b.md");
    assert.equal(changes(app, "2").disabled, false);
    assert.equal(changes(app, "1").disabled, true);
  });
});

// Adversarial where: a card outlives its request (the request file was
// deleted or another surface answered it), or the sweep drops every card
// instead of only the dead one, or no periodic sweep is registered at all.
test("recheck drops a review whose request file is gone or whose verdict exists, and keeps live ones", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "c.md": "z",
    "tmp/review/1.request.json": req("1", "a.md"), "tmp/review/2.request.json": req("2", "b.md") });
  assert.ok(plugin.intervals.length >= 1, "recheck is registered as an interval");
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await plugin.handler({ request: "tmp/review/2.request.json" });
  const barFor = (id) => app.leaves.map((l) => barIn(l)).find((b) => b && b.dataset.id === id);
  assert.ok(barFor("1") && barFor("2"));
  assert.deepEqual(cardIds(app), ["2", "1"]);

  app.store.delete("tmp/review/1.request.json");
  await plugin.recheck();
  assert.equal(barFor("1"), undefined, "request removed: bar gone");
  assert.equal(cardFor(app, "1"), undefined, "request removed: card gone");
  assert.ok(barFor("2"), "the other review keeps its bar");
  assert.deepEqual(cardIds(app), ["2"]);
  assert.deepEqual([...plugin.pending.keys()], ["2"]);

  show(app, app.leaves[0], "c.md");
  assert.ok(thisFileIn(cardFor(app, "2")), "the surviving card follows the page in view");
  app.store.set("tmp/review/2.verdict.json", "{}");
  await plugin.recheck();
  assert.equal(barFor("2"), undefined, "verdict exists: bar gone");
  assert.deepEqual(cardIds(app), [], "no card without a pending review");
  assert.equal(trailCount(app), 0);
  assert.equal(plugin.pending.size, 0);
});

// ---- implementation-visible edges: shared edit tracking, verdict races, rename ----

const verdictWrites = (app) => {
  const writes = [];
  const real = app.vault.adapter.write;
  app.vault.adapter.write = async (p, d) => { if (p.endsWith(".verdict.json")) writes.push(p); return real(p, d); };
  return writes;
};
const gate = () => { let release; const wait = new Promise((r) => { release = r; }); return { wait, release }; };

// Adversarial where: an edit event is attributed to a review it does not
// belong to. An edit to a reviewed file belongs to that file's review, even
// after the other review's file is opened; an edit to a file no review lists
// belongs to none, and an edit after a review is answered reaches only the
// review left.
test("with two reviews pending, an edit lands only in the review it belongs to", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "z.md": "q",
    "tmp/review/1.request.json": req("1", "a.md"), "tmp/review/2.request.json": req("2", "b.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await plugin.handler({ request: "tmp/review/2.request.json" });
  typedIn(app, "z.md");
  typedIn(app, "a.md");
  show(app, app.leaves[0], "a.md");
  typedIn(app, "b.md");
  await click(cardBtn(app, "2", "Approve"));
  await sleep();
  assert.deepEqual(verdictOf(app, "tmp/review/2.verdict.json").edited, ["b.md"], "an unlisted file's edit goes to no review, whichever reviewed file is in view");
  typedIn(app, "w.md");
  typedIn(app, "b.md");
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  assert.deepEqual(verdictOf(app, "tmp/review/1.verdict.json").edited, ["a.md"], "a reviewed file's edit goes to its own review, and later edits to other files to none");
});

// Adversarial where: with two reviews pending, a page shows the other
// review's bar or two bars, the panel's cards are lost when one review is
// answered, or a trail bar appears on a page once only one review remains.
test("on the reviewed file of a second pending review its own bar shows, and answering it leaves the other card and no trail", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y",
    "tmp/review/1.request.json": req("1", "a.md", { title: "Alpha" }),
    "tmp/review/2.request.json": req("2", "b.md", { title: "Beta" }) });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await plugin.handler({ request: "tmp/review/2.request.json" });
  assert.equal(app.leaves.length, 2, "each review opened in its own pane");
  const [alphaLeaf, betaLeaf] = app.leaves;
  show(app, alphaLeaf, "b.md");
  assert.equal(barIn(alphaLeaf).dataset.id, "2");
  assert.match(barText(barIn(alphaLeaf)), /Beta/);
  assert.equal(alphaLeaf.view.containerEl.querySelectorAll(".compass-review-bar").length, 1, "one bar per page");
  show(app, alphaLeaf, "a.md");
  assert.equal(barIn(alphaLeaf).dataset.id, "1");

  show(app, betaLeaf, "a.md");
  show(app, alphaLeaf, "b.md");
  await click(cardBtn(app, "2", "Approve"));
  await sleep();
  assert.equal(barIn(alphaLeaf), null, "answered review: bar gone");
  assert.deepEqual(cardIds(app), ["1"]);
  assert.ok(thisFileIn(cardFor(app, "1")), "b.md is another file to the remaining review");
  assert.equal(barIn(betaLeaf).dataset.id, "1");
  assert.equal(trailCount(app), 0);
});

// Adversarial where: the plugin's own save of the reviewed file (made so
// Compass reads the human's text) is lost, or counted twice, or breaks the
// verdict when the resulting editor-change event fires while the verdict is built.
test("the save made for the verdict counts as the human's edit once; a clean save adds nothing", async (t) => {
  const run = async (fireEditOnSave) => {
    const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md") });
    await plugin.handler({ request: "tmp/review/1.request.json" });
    const leaf = app.leaves[0];
    leaf.view.save = async () => { if (fireEditOnSave) typedIn(app, "a.md"); };
    await click(cardBtn(app, "1", "Approve"));
    await sleep();
    return verdictOf(app, "tmp/review/1.verdict.json");
  };
  await t.test("dirty document: editor-change fires during save", async () => {
    assert.deepEqual((await run(true)).edited, ["a.md"]);
  });
  await t.test("clean document: no editor-change event", async () => {
    assert.deepEqual((await run(false)).edited, []);
  });
});

// Adversarial where: an editor-change event arriving after the verdict is
// written throws or resurrects the review.
test("an editor-change event after the verdict is written is ignored and leaves no review behind", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  typedIn(app, "a.md");
  assert.equal(plugin.pending.size, 0);
  assert.deepEqual(cardIds(app), []);
  assert.equal(verdictOf(app, "tmp/review/1.verdict.json").edited.length, 0);
});

// Adversarial where: a recheck that is awaiting the file system while the
// human clicks leaves the review half-dropped, throws on the entry that the
// click already removed, or loses the verdict.
test("a recheck in flight while a verdict click completes ends with the verdict written and no review pending", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const real = app.vault.adapter.exists;
  const held = gate();
  let first = true;
  app.vault.adapter.exists = async (p) => { if (first) { first = false; await held.wait; } return real(p); };
  const racing = plugin.recheck();
  await click(cardBtn(app, "1", "Approve"));
  held.release();
  await racing;
  assert.equal(verdictOf(app, "tmp/review/1.verdict.json").verdict, "approved");
  assert.equal(plugin.pending.size, 0);
  assert.equal(barIn(app.leaves[0]), null);
  assert.deepEqual(cardIds(app), []);
});

// Adversarial where: a click already waiting on the editor save writes a
// verdict for a request that was withdrawn meanwhile (the terminal answered
// and `compass review --cancel` removed the request file), leaving an orphan
// verdict file and telling the human it was sent.
test("a request withdrawn while the verdict click is saving gets no verdict file", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const held = gate();
  app.leaves[0].view.save = () => held.wait;
  const click1 = click(cardBtn(app, "1", "Approve"));
  app.store.delete("tmp/review/1.request.json");
  await plugin.recheck();
  assert.equal(cardFor(app, "1"), undefined, "the withdrawn review's card is gone");
  held.release();
  await click1;
  assert.equal(app.store.has("tmp/review/1.verdict.json"), false);
  assert.ok(!notices.some((n) => /sent to Claude/.test(n)), "no 'sent' notice for a withdrawn review");
});

// Adversarial where: two quick clicks (Approve then Needs changes) while the
// save is pending write two verdicts for one request, the second overwriting
// the first after the waiter may already have printed it.
test("two clicks while the save is pending write one verdict", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const writes = verdictWrites(app);
  const held = gate();
  app.leaves[0].view.save = () => held.wait;
  typeInto(notesIn(cardFor(app, "1")), "note");
  const approve = cardBtn(app, "1", "Approve");
  const changes = cardBtn(app, "1", "Needs changes");
  const first = click(approve);
  const second = click(changes);
  held.release();
  await Promise.all([first, second]);
  assert.equal(writes.length, 1);
});

// Adversarial where: a rename of a file that carries a note or an edit
// orphans them under the old path, or the card's link to the reviewed file
// opens the old path of a renamed reviewed file.
test("renaming a noted and edited file moves both to the new path, and the card's link follows a renamed reviewed file", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "b.md": "y", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const leaf = app.leaves[0];
  show(app, leaf, "b.md");
  typeInto(fileNoteIn(cardFor(app, "1")), "tidy");
  typedIn(app, "a.md");
  app.store.set("b2.md", app.store.get("b.md"));
  app.store.delete("b.md");
  app.listeners.rename({ path: "b2.md" }, "b.md");
  app.store.set("a2.md", app.store.get("a.md"));
  app.store.delete("a.md");
  app.listeners.rename({ path: "a2.md" }, "a.md");
  show(app, leaf, "b2.md");
  assert.equal(fileNoteIn(cardFor(app, "1")).value, "tidy", "the note follows the file");
  assert.deepEqual([...feedbackOf(cardFor(app, "1"))].sort(), ["b2.md: tidy", "edited: a2.md"]);
  await click(linkIn(cardFor(app, "1")));
  assert.ok(app.leaves.some((l) => l.view.file && l.view.file.path === "a2.md"), "the link opens the renamed reviewed file");
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.deepEqual(v.comments, [{ file: "b2.md", note: "tidy" }]);
  assert.deepEqual(v.edited, ["a2.md"]);
  assert.equal(v.file, "a2.md");
});

// Adversarial where: the card's link to the reviewed file does nothing when
// the human is on another file, or opens a missing file as a new empty note,
// or throws out of the click handler when the reviewed file no longer exists.
test("the card's file link reopens the reviewed file; for a deleted file it reports a failure and keeps the pane", async (t) => {
  await t.test("the file exists", async () => {
    const { app, plugin } = await loaded({ "a.md": "x", "b.md": "y", "tmp/review/1.request.json": req("1", "a.md") });
    await plugin.handler({ request: "tmp/review/1.request.json" });
    show(app, app.leaves[0], "b.md");
    await click(linkIn(cardFor(app, "1")));
    assert.ok(app.leaves.some((l) => l.view.file && l.view.file.path === "a.md"));
    assert.equal(bar(app).dataset.id, "1", "the reopened document carries its bar");
  });
  await t.test("the file was deleted", async () => {
    const { app, plugin } = await loaded({ "a.md": "x", "b.md": "y", "tmp/review/1.request.json": req("1", "a.md") });
    await plugin.handler({ request: "tmp/review/1.request.json" });
    const leaf = app.leaves[0];
    show(app, leaf, "b.md");
    app.store.delete("a.md");
    await click(linkIn(cardFor(app, "1")));
    assert.match(notices.join(" "), /file not in this vault: a\.md/);
    assert.equal(leaf.view.file.path, "b.md");
  });
});

// ---- edges that only the implementation reveals ----

// Adversarial where: the in-flight guard set before the editor save and the
// verdict write is never cleared when either fails, so after one failed
// click (disk error, locked file) Approve and Needs changes are dead and the
// human can never answer the review.
test("a verdict click that failed can be clicked again", async (t) => {
  const rows = {
    "the verdict write fails": (app) => { const real = app.vault.adapter.write; let n = 0; app.vault.adapter.write = async (p, d) => { if (n++ === 0) throw new Error("disk full"); return real.call(app.vault.adapter, p, d); }; },
    "the editor save fails": (app) => { const view = app.leaves[0].view; const real = view.save; let n = 0; view.save = async () => { if (n++ === 0) throw new Error("locked"); return real.call(view); }; },
  };
  for (const [name, break_] of Object.entries(rows)) {
    await t.test(name, async () => {
      const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md") });
      await plugin.handler({ request: "tmp/review/1.request.json" });
      break_(app);
      await click(cardBtn(app, "1", "Approve")).catch(() => {});
      await sleep();
      assert.equal(app.store.has("tmp/review/1.verdict.json"), false, "the first attempt wrote nothing");
      await click(cardBtn(app, "1", "Approve")).catch(() => {});
      await sleep();
      assert.equal(verdictOf(app, "tmp/review/1.verdict.json").verdict, "approved");
    });
  }
});

// Adversarial where: events that redraw the panel (layout changes, another
// file's modify, the periodic recheck) replace the notes field being typed
// in, dropping its focus and caret, or lose the text when the active file
// changes and the card is rebuilt.
test("typing survives panel events: the same field stays in place, and a rebuilt card restores the text", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "b.md": "y", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const field = notesIn(cardFor(app, "1"));
  typeInto(field, "half a senten");
  app.wsListeners["layout-change"]();
  app.wsListeners["file-open"](mdFile("a.md"));
  await plugin.recheck();
  typedIn(app, "a.md");
  assert.equal(notesIn(cardFor(app, "1")), field, "the notes field is the same element");
  assert.equal(field.value, "half a senten");
  show(app, app.leaves[0], "b.md");
  assert.notEqual(notesIn(cardFor(app, "1")), field, "the card was rebuilt for the new file");
  assert.equal(notesIn(cardFor(app, "1")).value, "half a senten", "the typed text is restored");
  assert.ok(thisFileIn(cardFor(app, "1")), "the note field for the file in view appears");
});

// Adversarial where: with many pending reviews the cards are not newest
// first, an answer removes a neighbour's card, or an edit is credited to every
// card instead of the one for that file (or to the newest for an unlisted file).
test("thirty pending reviews: newest first, one answer removes only its card, edits go to one card", async () => {
  const files = { "other.md": "o" };
  const n = 30;
  for (let i = 1; i <= n; i++) {
    files[`d${i}.md`] = "x";
    files[`tmp/review/${String(i).padStart(2, "0")}.request.json`] = req(String(i).padStart(2, "0"), `d${i}.md`);
  }
  const { app, plugin } = await loaded(files);
  for (let i = 1; i <= n; i++) await plugin.handler({ request: `tmp/review/${String(i).padStart(2, "0")}.request.json` });
  const ids = (k) => Array.from({ length: k }, (_, i) => String(i + 1).padStart(2, "0"));
  assert.deepEqual(cardIds(app), ids(n).reverse());
  typedIn(app, "d7.md");
  typedIn(app, "other.md");
  const edited = cards(app).filter((c) => feedbackOf(c).length > 0).map((c) => c.dataset.id).sort();
  assert.deepEqual(edited, ["07"]);
  await click(cardBtn(app, "15", "Approve"));
  await sleep();
  assert.equal(cardIds(app).length, n - 1);
  assert.equal(cardFor(app, "15"), undefined);
  assert.deepEqual(verdictOf(app, "tmp/review/15.verdict.json").edited, []);
  assert.equal(app.store.has("tmp/review/16.verdict.json"), false);
});

// Adversarial where: closing the panel drops the pending reviews (or their
// typed notes) with the view, or a request after the close finds no leaf and
// shows only the new card.
test("after the human closes the panel, a new request reopens it with every pending card and its typed note", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "b.md": "y",
    "tmp/review/1.request.json": req("1", "a.md"), "tmp/review/2.request.json": req("2", "b.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  typeInto(notesIn(cardFor(app, "1")), "keep me");
  await closePanel(app);
  assert.equal(panelView(app), null);
  await plugin.handler({ request: "tmp/review/2.request.json" });
  assert.ok(panelView(app), "a new panel view exists");
  assert.deepEqual(cardIds(app), ["2", "1"]);
  assert.equal(notesIn(cardFor(app, "1")).value, "keep me");
});

// Adversarial where: the reviewed file is deleted while its review is pending
// and Approve throws (the editor leaf holds a dead file) or sends a verdict
// naming nothing.
test("approving a review whose file was deleted still writes the verdict for the original path", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  app.store.delete("a.md");
  app.leaves[0].view.file = null;
  typeInto(notesIn(cardFor(app, "1")), "file is gone");
  app.wsListeners["layout-change"]();
  await click(cardBtn(app, "1", "Needs changes"));
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.equal(v.file, "a.md");
  assert.equal(v.verdict, "changes");
  assert.deepEqual(notices.filter((n) => /failed/.test(n)), []);
});

// Adversarial where: unloading the plugin leaves its bars in the open panes,
// so a disabled plugin keeps a dead "Open review panel" button on the page.
test("unloading the plugin removes every bar from the panes", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "b.md": "y",
    "tmp/review/1.request.json": req("1", "a.md"), "tmp/review/2.request.json": req("2", "b.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await plugin.handler({ request: "tmp/review/2.request.json" });
  app.leaves.forEach((l) => document.children.push(l.view.containerEl));
  assert.equal(document.querySelectorAll(".compass-review-bar").length, 2);
  plugin.onunload();
  assert.equal(document.querySelectorAll(".compass-review-bar").length, 0);
  document.children.length = 0;
});

// ---- a review of several files: one card walks them and one answer covers them ----

const SET = ["spec.md", "plan.md", "detail.md", "study.md"];
const WHY = ["The need", "What gets built in what order", "The long text of each task", "The evidence behind the plan"];
const filesOf = (names = SET, whys = WHY) => names.map((file, i) => ({ file, why: whys[i] }));
const SESSION_A = "7f3a91c2-4d1b-4e8a-9b2f-5c06d83e1a47";
const SESSION_B = "b20e44aa-1c5d-4f60-8a37-90de12c4f5b1";

// A four-file review whose request lists SET in an order no sort would give.
async function openSet(extra = {}, vault = {}) {
  const store = {
    "elsewhere.md": "e",
    "tmp/review/1.request.json": req("1", SET[0], { files: filesOf(), project: "orchard", session: SESSION_A, ...extra }),
    ...Object.fromEntries(SET.map((f) => [f, "x"])),
    ...vault,
  };
  const r = await loaded(store);
  await r.plugin.handler({ request: "tmp/review/1.request.json" });
  return r;
}
const rowsIn = (card) => card.querySelectorAll(".compass-review-row");
const textOf = (el) => el.all().map((e) => e.text).join(" ");
const positionOf = (card) => { const e = card.all().find((x) => /^File \d+ of \d+$/.test(x.text)); return e ? e.text : null; };
const markOf = (row) => { const e = row.all().find((x) => x.text === "read" || x.text === "unread"); return e ? e.text : null; };
const summaryOf = (card) => { const e = card.all().find((x) => /files read/.test(x.text)); return e ? e.text : null; };
const labelIn = (card, text) => card.all().find((e) => e.text === text);
const marks = (app, id = "1") => rowsIn(cardFor(app, id)).map(markOf);
async function step(app, name, id = "1") { await click(cardBtn(app, id, name)); await sleep(); }
async function goToRow(app, i, id = "1") { await click(rowsIn(cardFor(app, id))[i]); await sleep(); }

// A key pressed on an element reaches the keydown handlers of it and of its ancestors.
async function press(el, key) {
  for (let n = el; n; n = n.parent) {
    for (const fn of [n.onkeydown, ...(n.handlers.keydown || [])].filter(Boolean)) {
      fn.call(n, { key, target: el, preventDefault() {}, stopPropagation() {} });
    }
  }
  await sleep();
}

// Adversarial where: the card lists files in a sorted or reversed order
// instead of the request's, drops a row's reason, marks every file read or
// none, counts the first file's opening wrongly, or omits the heading.
test("a four-file request draws one card at File 1 of 4 with a row per file in request order", async () => {
  const { app } = await openSet();
  assert.deepEqual(cardIds(app), ["1"]);
  assert.ok(panelEl(app).all().some((e) => e.text === "Reviews waiting on you"), "panel heading");
  const card = cardFor(app, "1");
  assert.equal(positionOf(card), "File 1 of 4");
  const rows = rowsIn(card);
  assert.equal(rows.length, 4);
  assert.deepEqual(rows.map((r) => WHY.findIndex((w) => textOf(r).includes(w))), [0, 1, 2, 3]);
  assert.deepEqual(marks(app), ["read", "unread", "unread", "unread"]);
  assert.match(summaryOf(card), /^1 of 4 files read, 0 notes/);
  assert.ok(button(card, "Approve") && button(card, "Needs changes"));
  assert.equal(button(card, "Previous").disabled, true);
});

// Adversarial where: Next opens the file but leaves it unread or leaves the
// position unchanged, Previous does not go back, or the buttons stay on at
// the ends of the list.
test("Next and Previous move through the files in request order, mark each read, and switch off at the ends", async (t) => {
  await t.test("Next opens the second file and marks it read", async () => {
    const { app } = await openSet();
    await step(app, "Next");
    assert.equal(positionOf(cardFor(app, "1")), "File 2 of 4");
    assert.equal(app.active.path, "plan.md");
    assert.deepEqual(marks(app), ["read", "read", "unread", "unread"]);
  });
  await t.test("Previous returns to the first file", async () => {
    const { app } = await openSet();
    await step(app, "Next");
    await step(app, "Previous");
    assert.equal(positionOf(cardFor(app, "1")), "File 1 of 4");
    assert.equal(app.active.path, "spec.md");
  });
  await t.test("Previous is off on the first file and Next is on", async () => {
    const { app } = await openSet();
    assert.equal(cardBtn(app, "1", "Previous").disabled, true);
    assert.notEqual(cardBtn(app, "1", "Next").disabled, true);
  });
  await t.test("Next is off on the last file and Previous is on", async () => {
    const { app } = await openSet();
    await goToRow(app, 3);
    assert.equal(cardBtn(app, "1", "Next").disabled, true);
    assert.notEqual(cardBtn(app, "1", "Previous").disabled, true);
  });
  await t.test("one step from the last file, Next is still on", async () => {
    const { app } = await openSet();
    await goToRow(app, 2);
    assert.notEqual(cardBtn(app, "1", "Next").disabled, true);
  });
});

// Adversarial where: Next unread stops on a read file, ignores the files
// before the current one when none after it is unread, or stays on once every
// file is read.
test("Next unread jumps to the next file not yet read and switches off when none is left", async (t) => {
  await t.test("it skips a read file that lies between", async () => {
    const { app } = await openSet();
    await goToRow(app, 2);
    await goToRow(app, 0);
    await step(app, "Next unread");
    assert.equal(positionOf(cardFor(app, "1")), "File 2 of 4");
    await step(app, "Next unread");
    assert.equal(positionOf(cardFor(app, "1")), "File 4 of 4", "detail is read, so the jump passes it");
    assert.equal(app.active.path, "study.md");
    assert.equal(cardBtn(app, "1", "Next unread").disabled, true, "every file is read");
  });
  await t.test("with only earlier files unread it goes back to the first of them", async () => {
    const { app } = await openSet();
    await goToRow(app, 3);
    await step(app, "Next unread");
    assert.equal(positionOf(cardFor(app, "1")), "File 2 of 4");
  });
  await t.test("it is on while any file is unread", async () => {
    const { app } = await openSet();
    assert.notEqual(cardBtn(app, "1", "Next unread").disabled, true);
  });
});

// Adversarial where: opening a listed file from a link or the file explorer
// leaves the walk on the old file or leaves the new one unread, or shows it
// as an outside file.
test("opening a listed file by hand moves the walk to it, marks it read, and is not an outside file", async () => {
  const { app } = await openSet();
  show(app, app.leaves[0], "detail.md");
  const card = cardFor(app, "1");
  assert.equal(positionOf(card), "File 3 of 4");
  assert.deepEqual(marks(app), ["read", "unread", "read", "unread"]);
  assert.equal(thisFileIn(card), null);
});

// Adversarial where: a click on a row does not open the file, opens it in a
// new pane although one already shows it, or does not mark it read.
test("a click on a row opens that file in the pane that shows it, else in a pane, and marks it read", async (t) => {
  await t.test("a file already shown in a pane gets no second pane", async () => {
    const { app } = await openSet();
    const other = app.workspace.getLeaf(true);
    await other.openFile(mdFile("plan.md"));
    const panes = app.leaves.length;
    await goToRow(app, 0);
    assert.equal(app.leaves.length, panes);
    assert.equal(app.active.path, "spec.md");
    assert.equal(positionOf(cardFor(app, "1")), "File 1 of 4");
  });
  await t.test("a file shown nowhere opens and is marked read", async () => {
    const { app } = await openSet();
    await goToRow(app, 3);
    assert.ok(app.leaves.some((l) => l.view.file && l.view.file.path === "study.md"));
    assert.equal(app.active.path, "study.md");
    assert.equal(positionOf(cardFor(app, "1")), "File 4 of 4");
    assert.equal(marks(app)[3], "read");
  });
});

// Adversarial where: the arrow keys do nothing, run the wrong way, walk past
// either end, or react to other keys.
test("Right and Left arrow keys on the card step to the next and previous file and stop at the ends", async () => {
  const { app } = await openSet();
  const at = () => positionOf(cardFor(app, "1"));
  await press(cardFor(app, "1"), "ArrowLeft");
  assert.equal(at(), "File 1 of 4", "Left on the first file stays");
  await press(cardFor(app, "1"), "ArrowRight");
  assert.equal(at(), "File 2 of 4");
  assert.equal(app.active.path, "plan.md");
  await press(cardFor(app, "1"), "x");
  assert.equal(at(), "File 2 of 4", "other keys do nothing");
  await press(cardFor(app, "1"), "ArrowRight");
  await press(cardFor(app, "1"), "ArrowRight");
  await press(cardFor(app, "1"), "ArrowRight");
  assert.equal(at(), "File 4 of 4", "Right on the last file stays");
  await press(cardFor(app, "1"), "ArrowLeft");
  assert.equal(at(), "File 3 of 4");
});

// Adversarial where: the row shows a path or the file name although the file
// has a `title` property (quoted or not), or the note field is labelled with
// something other than the current file's title.
test("rows and the note label use the title property, else the file name", async () => {
  const { app } = await openSet({}, { "spec.md": '---\ntitle: "Combat spec"\n---\nbody', "plan.md": "---\ntitle: Build order\n---\nbody" });
  const rows = rowsIn(cardFor(app, "1"));
  assert.ok(textOf(rows[0]).includes("Combat spec"));
  assert.ok(textOf(rows[1]).includes("Build order"));
  assert.ok(textOf(rows[2]).includes("detail"));
  assert.ok(labelIn(cardFor(app, "1"), "Note on Combat spec"));
  await step(app, "Next");
  assert.ok(labelIn(cardFor(app, "1"), "Note on Build order"));
  await step(app, "Next");
  assert.ok(labelIn(cardFor(app, "1"), "Note on detail"));
});

// Adversarial where: the note field is shared by all files (text typed on
// one file shows on the next), a note is lost when the walk moves away, a
// whitespace-only note counts, or the row and summary counts lag the typing.
test("each file keeps its own note as the walk moves, and the rows and the summary count them", async () => {
  const { app } = await openSet();
  await step(app, "Next");
  typeInto(notesIn(cardFor(app, "1")), "reorder the tasks");
  const planRow = () => rowsIn(cardFor(app, "1"))[1];
  assert.match(textOf(planRow()), /\b1 note\b/);
  assert.match(summaryOf(cardFor(app, "1")), /^2 of 4 files read, 1 note\b/);
  await step(app, "Next");
  assert.equal(notesIn(cardFor(app, "1")).value, "", "the next file starts with its own empty note");
  typeInto(notesIn(cardFor(app, "1")), "   ");
  assert.match(summaryOf(cardFor(app, "1")), /^3 of 4 files read, 1 note\b/, "a whitespace-only note is no note");
  await step(app, "Previous");
  assert.equal(notesIn(cardFor(app, "1")).value, "reorder the tasks", "the note stays with its file");
  assert.doesNotMatch(textOf(rowsIn(cardFor(app, "1"))[0]), /\b[1-9]\d* notes?\b/);
});

// Adversarial where: the "On this file" box shows for a listed file, lacks
// the path, loses its note, or an outside note does not count toward the
// summary, enable Needs changes or travel in `comments`.
test("a file outside the review shows On this file with its own note, which counts and travels in comments", async () => {
  const { app } = await openSet();
  const card0 = () => cardFor(app, "1");
  assert.equal(thisFileIn(card0()), null);
  show(app, app.leaves[0], "elsewhere.md");
  assert.ok(textOf(thisFileIn(card0())).includes("On this file: elsewhere.md"));
  assert.equal(cardBtn(app, "1", "Needs changes").disabled, true);
  typeInto(fileNoteIn(card0()), "typo on line 3");
  assert.match(summaryOf(card0()), /^1 of 4 files read, 0 notes/);
  assert.match(summaryOf(card0()), /outside/);
  assert.equal(cardBtn(app, "1", "Needs changes").disabled, false);
  show(app, app.leaves[0], "plan.md");
  assert.equal(thisFileIn(card0()), null, "opening a listed file hides the box");
  assert.equal(positionOf(card0()), "File 2 of 4");
  await click(cardBtn(app, "1", "Needs changes"));
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.deepEqual(v.comments, [{ file: "elsewhere.md", note: "typo on line 3" }]);
  assert.equal(v.verdict, "changes");
  assert.equal(v.notes, "");
  assert.equal(v.files.length, 4);
});

// Adversarial where: the answer lists files in the order they were visited
// or noted instead of the request's, writes `read` as a string or omits it,
// writes an empty `note`, puts the notes in another format, names the wrong
// `file`, or leaves an editor unsaved.
test("the answer lists every file in request order with read and note, saves each editor, and puts the notes in notes", async () => {
  const { app } = await openSet();
  await goToRow(app, 3);
  typeInto(notesIn(cardFor(app, "1")), "check source 2");
  await goToRow(app, 1);
  typeInto(notesIn(cardFor(app, "1")), "reorder");
  await goToRow(app, 2);
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.deepEqual(Object.keys(v).sort(), ["at", "comments", "edited", "file", "files", "id", "notes", "verdict"]);
  assert.equal(v.id, "1");
  assert.equal(v.file, "spec.md");
  assert.equal(v.verdict, "approved");
  assert.deepEqual(v.files, [
    { file: "spec.md", read: true },
    { file: "plan.md", read: true, note: "reorder" },
    { file: "detail.md", read: true },
    { file: "study.md", read: true, note: "check source 2" },
  ]);
  const lines = v.notes.split("\n");
  assert.equal(lines.length, 2);
  assert.match(lines[0], /^plan(\.md)?: reorder$/);
  assert.match(lines[1], /^study(\.md)?: check source 2$/);
  assert.deepEqual(v.comments, []);
  assert.deepEqual(v.edited, []);
  assert.equal(typeof v.at, "string");
  const shown = app.leaves.filter((l) => l.view.file && SET.includes(l.view.file.path));
  assert.ok(shown.length >= 4);
  for (const l of shown) assert.ok(l.view.saved >= 1, `${l.view.file.path} saved`);
});

// Adversarial where: a file never opened is recorded as read (the first-file
// mark leaking to all), or an unread file's entry carries a note key.
test("an answer given without reading marks the unopened files unread and carries no notes", async () => {
  const { app } = await openSet();
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.deepEqual(v.files, [
    { file: "spec.md", read: true },
    { file: "plan.md", read: false },
    { file: "detail.md", read: false },
    { file: "study.md", read: false },
  ]);
  assert.equal(v.notes, "");
});

// Adversarial where: Needs changes is enabled with nothing written, looks
// only at the note of the file in view, stays off after an edit, or never
// switches off again when the note is cleared.
test("Needs changes in a multi-file review is enabled by a note on any listed file or an edit, and Approve never waits", async (t) => {
  await t.test("nothing written", async () => {
    const { app } = await openSet();
    assert.equal(cardBtn(app, "1", "Needs changes").disabled, true);
    assert.notEqual(cardBtn(app, "1", "Approve").disabled, true);
  });
  await t.test("a note on a file other than the one in view, then cleared", async () => {
    const { app } = await openSet();
    await goToRow(app, 2);
    typeInto(notesIn(cardFor(app, "1")), "see this");
    await goToRow(app, 0);
    assert.equal(cardBtn(app, "1", "Needs changes").disabled, false);
    await goToRow(app, 2);
    typeInto(notesIn(cardFor(app, "1")), "");
    assert.equal(cardBtn(app, "1", "Needs changes").disabled, true);
  });
  await t.test("a whitespace-only note", async () => {
    const { app } = await openSet();
    await goToRow(app, 1);
    typeInto(notesIn(cardFor(app, "1")), "  ");
    assert.equal(cardBtn(app, "1", "Needs changes").disabled, true);
  });
  await t.test("an edit to a listed file", async () => {
    const { app } = await openSet();
    typedIn(app, "plan.md");
    await sleep();
    assert.equal(cardBtn(app, "1", "Needs changes").disabled, false);
  });
});

const SECOND = {
  "dock-a.md": "x",
  "dock-b.md": "x",
  "tmp/review/2.request.json": req("2", "dock-a.md", { files: filesOf(["dock-a.md", "dock-b.md"], WHY.slice(2)), project: "harbor", session: SESSION_B }),
};

// Adversarial where: the project line shows the full session id, a session
// code of the wrong length, another card's names, or a Session label with
// nothing after it; the project falls back to the wrong folder.
test("each card names its project and the first six characters of its session, and leaves Session out when there is none", async (t) => {
  await t.test("two sessions give two cards that tell themselves apart", async () => {
    const { app, plugin } = await openSet({}, SECOND);
    await plugin.handler({ request: "tmp/review/2.request.json" });
    assert.deepEqual(cardIds(app), ["2", "1"]);
    const one = textOf(cardFor(app, "1"));
    const two = textOf(cardFor(app, "2"));
    assert.ok(labelIn(cardFor(app, "1"), "Project") && labelIn(cardFor(app, "1"), "Session"));
    assert.ok(one.includes("orchard") && one.includes("7f3a91") && !one.includes("7f3a91c") && !one.includes("harbor") && !one.includes("b20e44"));
    assert.ok(two.includes("harbor") && two.includes("b20e44") && !two.includes("b20e44a") && !two.includes("orchard") && !two.includes("7f3a91"));
  });
  await t.test("an empty session leaves the Session label out", async () => {
    const { app } = await openSet({ session: "" });
    assert.ok(labelIn(cardFor(app, "1"), "Project"));
    assert.equal(labelIn(cardFor(app, "1"), "Session"), undefined);
  });
  await t.test("with no project on the request, the folder holding the vault is named", async () => {
    for (const base of ["F:/work/orchard/.compass", "F:\\work\\orchard\\.compass"]) {
      const store = { "spec.md": "x", "tmp/review/1.request.json": req("1", "spec.md", { files: filesOf(["spec.md"], ["The need"]) }) };
      const r = await loaded(store);
      r.app.vault.adapter.getBasePath = () => base;
      await r.plugin.handler({ request: "tmp/review/1.request.json" });
      assert.ok(labelIn(cardFor(r.app, "1"), "Project"));
      assert.ok(textOf(cardFor(r.app, "1")).includes("orchard"), base);
      assert.ok(!textOf(cardFor(r.app, "1")).includes(".compass"), base);
    }
  });
});

// Adversarial where: the walk state is shared between cards, so stepping or
// answering one review moves or answers the other.
test("two cards walk and answer independently", async () => {
  const { app, plugin } = await openSet({}, SECOND);
  await plugin.handler({ request: "tmp/review/2.request.json" });
  await step(app, "Next", "2");
  assert.equal(positionOf(cardFor(app, "2")), "File 2 of 2");
  assert.equal(positionOf(cardFor(app, "1")), "File 1 of 4");
  assert.deepEqual(marks(app, "1"), ["read", "unread", "unread", "unread"]);
  assert.deepEqual(marks(app, "2"), ["read", "read"]);
  await click(cardBtn(app, "2", "Approve"));
  await sleep();
  assert.deepEqual(verdictOf(app, "tmp/review/2.verdict.json").files, [{ file: "dock-a.md", read: true }, { file: "dock-b.md", read: true }]);
  assert.equal(app.store.has("tmp/review/1.verdict.json"), false);
  assert.deepEqual(cardIds(app), ["1"]);
});

// Adversarial where: a request without a `files` list draws a card without
// the position line, leaves navigation on, or answers with a `files` list or
// a note prefixed with a file name, so an old reader of the answer breaks.
test("a one-file request draws File 1 of 1 and its answer has no files list and the note as written", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const card = cardFor(app, "1");
  assert.equal(positionOf(card), "File 1 of 1");
  assert.equal(rowsIn(card).length, 1);
  for (const name of ["Previous", "Next", "Next unread"]) assert.equal(button(card, name).disabled, true, name);
  typeInto(notesIn(card), "fine");
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.equal("files" in v, false);
  assert.equal(v.notes, "fine");
});

// Adversarial where: an overlapping newer request leaves the older card
// beside it (only a request with the same first file replaces), or a request
// sharing no file replaces a live review.
test("a newer request listing any file of an older one replaces it, and one listing none leaves it", async () => {
  const { app, plugin } = await loaded({
    "spec.md": "x", "plan.md": "x", "detail.md": "x", "study.md": "x",
    "tmp/review/1.request.json": req("1", "spec.md", { files: filesOf(["spec.md", "plan.md"]) }),
    "tmp/review/2.request.json": req("2", "study.md", { files: filesOf(["study.md", "plan.md"]) }),
    "tmp/review/3.request.json": req("3", "detail.md", { files: filesOf(["detail.md"]) }) });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await plugin.handler({ request: "tmp/review/2.request.json" });
  assert.deepEqual(cardIds(app), ["2"], "the shared file was second in both lists");
  assert.deepEqual([...plugin.pending.keys()], ["2"]);
  await plugin.handler({ request: "tmp/review/3.request.json" });
  assert.deepEqual(cardIds(app), ["3", "2"]);
});

// Adversarial where: a bar says the position the walk is at instead of the
// file's place in the list, drops the question, or sits on only the first file.
test("each listed file carries a bar reading Review: question, file i of n, and an outside file carries none", async () => {
  const { app } = await openSet({ title: "Spec set", files: filesOf(SET.slice(0, 3), WHY) });
  const barOf = (leaf) => { const b = barIn(leaf); return b ? b.all().map((e) => e.text).join("") : null; };
  const first = app.leaves[0];
  assert.match(barOf(first), /Review: Spec set, file 1 of 3/);
  await step(app, "Next");
  const second = app.leaves[app.leaves.length - 1];
  assert.equal(second.view.file.path, "plan.md");
  assert.match(barOf(second), /Review: Spec set, file 2 of 3/);
  assert.match(barOf(first), /Review: Spec set, file 1 of 3/, "the walk's position does not change the first file's bar");
  show(app, first, "elsewhere.md");
  assert.equal(barIn(first), null);
});

// Adversarial where: a rename drops the walk's mark or note for the listed
// file (leaving it unread and unnoted under the new path), marks a renamed
// unread file read, or the answer names the old path.
test("a renamed listed file keeps its mark and note under the new path", async () => {
  const { app } = await openSet();
  await goToRow(app, 1);
  typeInto(notesIn(cardFor(app, "1")), "reorder");
  for (const [from, to] of [["plan.md", "plan2.md"], ["study.md", "study2.md"]]) {
    app.store.set(to, app.store.get(from));
    app.store.delete(from);
    app.listeners.rename({ path: to }, from);
  }
  const rows = rowsIn(cardFor(app, "1"));
  assert.deepEqual(marks(app), ["read", "read", "unread", "unread"]);
  assert.match(textOf(rows[1]), /\b1 note\b/);
  await goToRow(app, 1);
  assert.equal(app.active.path, "plan2.md");
  assert.equal(notesIn(cardFor(app, "1")).value, "reorder");
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  assert.deepEqual(verdictOf(app, "tmp/review/1.verdict.json").files, [
    { file: "spec.md", read: true },
    { file: "plan2.md", read: true, note: "reorder" },
    { file: "detail.md", read: false },
    { file: "study2.md", read: false },
  ]);
});

// Adversarial where: an answer click waiting on the save of a later file's
// editor writes a verdict for a review withdrawn meanwhile.
test("a four-file review withdrawn while an editor is saving gets no answer", async () => {
  const { app, plugin } = await openSet();
  await step(app, "Next");
  const held = gate();
  const planLeaf = app.leaves.find((l) => l.view.file && l.view.file.path === "plan.md");
  planLeaf.view.save = () => held.wait;
  const pending = click(cardBtn(app, "1", "Approve"));
  app.store.delete("tmp/review/1.request.json");
  await plugin.recheck();
  assert.equal(cardFor(app, "1"), undefined);
  held.release();
  await pending;
  assert.equal(app.store.has("tmp/review/1.verdict.json"), false);
  assert.ok(!notices.some((n) => /sent to Claude/.test(n)));
});

// ---- post-build probes: branches the panel implementation introduced ----

// Adversarial where: the card's keydown handler steps on a modified arrow
// (Alt+Left is Obsidian's "navigate back" hotkey, Shift+Right selects), or on
// an arrow pressed inside either note field, so a keystroke meant for the
// editor or the text moves the walk.
test("arrow keys with a modifier, or typed inside a note field, do not move the walk", async () => {
  const { app } = await openSet();
  show(app, app.leaves[0], "elsewhere.md");
  const card = cardFor(app, "1");
  const at = () => positionOf(cardFor(app, "1"));
  const rows = [
    { name: "ArrowRight in the file note", el: notesIn(card), mods: {} },
    { name: "ArrowRight in the On this file note", el: fileNoteIn(card), mods: {} },
    { name: "Alt+ArrowRight on the card", el: card, mods: { altKey: true } },
    { name: "Ctrl+ArrowRight on the card", el: card, mods: { ctrlKey: true } },
    { name: "Meta+ArrowRight on the card", el: card, mods: { metaKey: true } },
    { name: "Shift+ArrowRight on the card", el: card, mods: { shiftKey: true } },
  ];
  for (const row of rows) {
    row.el.tagName = row.el.tag.toUpperCase();
    for (let n = row.el; n; n = n.parent) {
      for (const fn of [n.onkeydown, ...(n.handlers.keydown || [])].filter(Boolean)) {
        fn.call(n, { key: "ArrowRight", target: row.el, preventDefault() {}, stopPropagation() {}, ...row.mods });
      }
    }
    await sleep();
    assert.equal(at(), "File 1 of 4", row.name);
  }
});

// Adversarial where: a card rebuilt because an outside file came into view
// loses the note typed on the current listed file, or shows the previous
// file's note after the walk has moved, so the answer carries a stale note.
test("a note typed on a listed file survives an outside file coming into view and the walk moving on and back", async () => {
  const { app } = await openSet();
  await goToRow(app, 2);
  typeInto(notesIn(cardFor(app, "1")), "detail needs a table");
  show(app, app.leaves[0], "elsewhere.md");
  assert.equal(notesIn(cardFor(app, "1")).value, "detail needs a table");
  await goToRow(app, 0);
  assert.equal(notesIn(cardFor(app, "1")).value, "", "the first file has no note");
  await goToRow(app, 2);
  assert.equal(notesIn(cardFor(app, "1")).value, "detail needs a table");
  await click(cardBtn(app, "1", "Needs changes"));
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.deepEqual(v.files.map((f) => f.note), [undefined, undefined, "detail needs a table", undefined]);
});

// Adversarial where: a request for the same id rewritten with a shorter file
// list keeps the walk index or note field of the old list, so the note field
// shows (and writes to) a file that is no longer in the review.
test("the same request id rewritten with fewer files redraws the walk on the first file and drops the removed files from the answer", async () => {
  const { app, plugin } = await openSet();
  await goToRow(app, 3);
  typeInto(notesIn(cardFor(app, "1")), "study note");
  app.store.set("tmp/review/1.request.json", req("1", SET[0], { files: filesOf(SET.slice(0, 2), WHY.slice(0, 2)), project: "orchard" }));
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await sleep();
  const card = cardFor(app, "1");
  assert.equal(positionOf(card), "File 1 of 2");
  assert.equal(rowsIn(card).length, 2);
  assert.equal(notesIn(card).value, "");
  typeInto(notesIn(card), "spec note");
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.deepEqual(v.files.map((f) => f.file), ["spec.md", "plan.md"]);
  assert.equal(v.notes, "spec: spec note");
});

// Adversarial where: every file switch or outside-file redraw leaves the old
// card's elements attached to the panel, so cards pile up and the panel grows
// without bound.
test("repeated redraws leave one heading and one card in the panel", async () => {
  const { app } = await openSet();
  for (let k = 0; k < 25; k++) {
    show(app, app.leaves[0], k % 2 ? "elsewhere.md" : SET[k % 4]);
    await sleep();
  }
  const root = panelEl(app);
  assert.equal(root.children.length, 2);
  assert.equal(root.querySelectorAll(".compass-review-card").length, 1);
});

// ---- the card carries the mockup's hints ----

// Adversarial where: the outside-file box lacks its hint, a note padded with
// blanks reaches the answer as typed, or the footer hints are missing or shown
// on a card with nothing to step through.
test("the outside-file box, the Needs changes tooltip and the arrow-key hint read as the mockup draws them, and outside notes are trimmed in the answer", async (t) => {
  await t.test("outside-file hint and trimmed comment", async () => {
    const { app } = await openSet();
    show(app, app.leaves[0], "elsewhere.md");
    const box = thisFileIn(cardFor(app, "1"));
    assert.ok(textOf(box).includes("This file is not in the review; the note goes with your answer."));
    typeInto(fileNoteIn(cardFor(app, "1")), "  fix the date \n");
    await click(cardBtn(app, "1", "Needs changes"));
    await sleep();
    assert.deepEqual(verdictOf(app, "tmp/review/1.verdict.json").comments, [{ file: "elsewhere.md", note: "fix the date" }]);
  });
  await t.test("Needs changes tooltip while disabled", async () => {
    const { app } = await openSet();
    const changes = cardBtn(app, "1", "Needs changes");
    assert.equal(changes.title, "Write a note first");
    typeInto(notesIn(cardFor(app, "1")), "x");
    assert.equal(cardBtn(app, "1", "Needs changes").title, "");
  });
  await t.test("arrow-key hint on a walk of several files only", async () => {
    const { app } = await openSet();
    assert.ok(textOf(cardFor(app, "1")).includes("Left and right arrow keys move between files when this card has focus."));
    const one = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md") });
    await one.plugin.handler({ request: "tmp/review/1.request.json" });
    assert.ok(!textOf(cardFor(one.app, "1")).includes("arrow keys"));
  });
});

// Adversarial where: the card says nothing about what Project and Session mean.
test("a card explains what Project and Session are", async () => {
  const { app } = await openSet();
  assert.ok(textOf(cardFor(app, "1")).includes("Project is the folder holding the vault. Session is the first six characters of the Claude Code session id."));
});

// ---- edits come from the editor-change event alone ----

// Fires the event Obsidian raises when the human types in an editor: the editor
// first, then an info object whose `file` is the document being edited.
const typedIn = (app, p) => {
  const fn = app.wsListeners["editor-change"];
  assert.ok(fn, "the plugin listens to the workspace editor-change event");
  fn({}, { file: mdFile(p) });
};
const approveBoth = async (app) => {
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  await click(cardBtn(app, "2", "Approve"));
  await sleep();
};

// Adversarial where: a write from a script or from Compass, which reaches the
// plugin as a file-changed (modify) event with no editor-change event, is
// listed as the human's edit, in the feedback list, in the answer's `edited`,
// or by enabling Needs changes.
test("a file-changed event with no editor-change event lists no edit", async () => {
  const { app } = await openSet();
  await app.listeners.modify(mdFile("spec.md"));
  await app.listeners.modify(mdFile("elsewhere.md"));
  await sleep();
  assert.deepEqual(feedbackOf(cardFor(app, "1")), []);
  assert.equal(cardBtn(app, "1", "Needs changes").disabled, true);
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  assert.deepEqual(verdictOf(app, "tmp/review/1.verdict.json").edited, []);
});

// Adversarial where: an editor-change event is credited to the wrong cards. A
// file one card lists reaches that card only, a file both list reaches both,
// and a file no card lists (which the earlier rule gave to the newest card)
// reaches none; the same file typed in twice is listed once.
test("an editor-change event lands on the cards that list the file and on no other", async (t) => {
  const rows = [
    { name: "a file only the first card lists", typed: ["spec.md"], first: ["spec.md"], second: [] },
    { name: "a file only the second card lists, typed twice", typed: ["dock-b.md", "dock-b.md"], first: [], second: ["dock-b.md"] },
    { name: "a file neither card lists", typed: ["elsewhere.md"], first: [], second: [] },
    { name: "a file both cards list", shared: true, typed: ["plan.md"], first: ["plan.md"], second: ["plan.md"] },
  ];
  for (const row of rows) {
    await t.test(row.name, async () => {
      const { app, plugin } = await openSet({}, SECOND);
      await plugin.handler({ request: "tmp/review/2.request.json" });
      // Renaming the second card's dock-b.md to plan.md leaves plan.md listed by both cards.
      if (row.shared) app.listeners.rename({ path: "plan.md" }, "dock-b.md");
      for (const p of row.typed) typedIn(app, p);
      await sleep();
      assert.deepEqual(feedbackOf(cardFor(app, "1")), row.first.map((f) => `edited: ${f}`), "first card feedback");
      assert.deepEqual(feedbackOf(cardFor(app, "2")), row.second.map((f) => `edited: ${f}`), "second card feedback");
      assert.equal(cardBtn(app, "1", "Needs changes").disabled, row.first.length === 0);
      assert.equal(cardBtn(app, "2", "Needs changes").disabled, row.second.length === 0);
      await approveBoth(app);
      assert.deepEqual(verdictOf(app, "tmp/review/1.verdict.json").edited, row.first);
      assert.deepEqual(verdictOf(app, "tmp/review/2.verdict.json").edited, row.second);
    });
  }
});

// Adversarial where: an editor-change event after a card's answer reopens its
// edited list or rewrites its answer, or is handed to a card still pending
// that does not list the file.
test("an editor-change event after a card's answer reaches neither its answer nor another card", async () => {
  const { app, plugin } = await openSet({}, SECOND);
  await plugin.handler({ request: "tmp/review/2.request.json" });
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  const before = app.store.get("tmp/review/1.verdict.json");
  const writes = verdictWrites(app);
  typedIn(app, "spec.md");
  typedIn(app, "elsewhere.md");
  await sleep();
  assert.equal(app.store.get("tmp/review/1.verdict.json"), before, "the written answer is unchanged");
  assert.deepEqual(writes, [], "no answer is rewritten");
  assert.deepEqual(feedbackOf(cardFor(app, "2")), [], "the pending card lists neither file");
  typedIn(app, "dock-a.md");
  await click(cardBtn(app, "2", "Approve"));
  await sleep();
  assert.deepEqual(verdictOf(app, "tmp/review/2.verdict.json").edited, ["dock-a.md"], "a listed file still counts on the pending card");
});

// Adversarial where: an editor-change event whose info carries no file (an
// editor not backed by a file) throws, or is credited to the newest card.
test("an editor-change event with no file lists nothing and does not throw", async (t) => {
  const { app } = await openSet();
  const fn = app.wsListeners["editor-change"];
  assert.ok(fn, "the plugin listens to the workspace editor-change event");
  for (const info of [undefined, null, {}, { file: null }]) {
    await t.test(`info ${JSON.stringify(info)}`, () => { fn({}, info); });
  }
  assert.deepEqual(feedbackOf(cardFor(app, "1")), []);
});

// ---- stepping aside is decided per window from how each review arrived ----

// Sends a request through the link handler with the window holding or lacking
// focus at that moment, as it stands before the plugin raises it.
async function arriveByLink(plugin, id, windowHasFocus) {
  win.hasFocus = windowHasFocus;
  await plugin.handler({ request: `tmp/review/${id}.request.json` });
}
async function approve(app, id) {
  await click(cardBtn(app, id, "Approve"));
  await sleep();
}

// Adversarial where: the window's focus is read after the plugin raises it
// (always true by then), or `return` still decides a review that arrived by
// link, so a human working in the window is hidden, or one working elsewhere
// is left looking at a window that never steps aside.
test("a review arriving by link steps aside after the answer only when the window lacked focus on arrival, whatever `return` says", async () => {
  const rows = [
    { name: "focused with return true", focus: true, ret: true, aside: 0 },
    { name: "focused with return false", focus: true, ret: false, aside: 0 },
    { name: "unfocused with return true", focus: false, ret: true, aside: 1 },
    { name: "unfocused with return false", focus: false, ret: false, aside: 1 },
    { name: "unfocused with no return field", focus: false, ret: undefined, aside: 1 },
    { name: "focused with no return field", focus: true, ret: undefined, aside: 0 },
  ];
  for (const row of rows) {
    win.minimized = 0;
    const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md", { return: row.ret }) });
    await arriveByLink(plugin, "1", row.focus);
    assert.equal(win.minimized, 0, `${row.name}: nothing steps aside before the answer`);
    await approve(app, "1");
    assert.equal(win.minimized, row.aside, row.name);
  }
});

// Adversarial where: the window is left in front forever, or hidden on every
// later answer, because the arrival record survives a step aside; or a focused
// arrival is stepped aside for on account of an earlier unfocused review that
// was already stepped aside for.
test("the arrival record is spent by a step aside, so a later focused review leaves the window in front", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "c.md": "z",
    "tmp/review/1.request.json": req("1", "a.md"),
    "tmp/review/2.request.json": req("2", "b.md"),
    "tmp/review/3.request.json": req("3", "c.md"),
  });
  await arriveByLink(plugin, "1", false);
  await approve(app, "1");
  assert.equal(win.minimized, 1, "the unfocused review stepped aside");
  await arriveByLink(plugin, "2", true);
  await approve(app, "2");
  assert.equal(win.minimized, 1, "the focused review after it leaves the window in front");
  await arriveByLink(plugin, "3", false);
  await approve(app, "3");
  assert.equal(win.minimized, 2, "a later unfocused review steps aside again");
});

// Adversarial where: stepping aside fires after the first of two answers, or
// the last answered card alone decides it, so a focused review answered last
// hides an unfocused one answered first (or the reverse).
test("with two cards the window steps aside only after the second answer, and only if either arrived without focus", async () => {
  const rows = [
    { name: "both unfocused", first: false, second: false, aside: 1 },
    { name: "first unfocused, second focused", first: false, second: true, aside: 1 },
    { name: "first focused, second unfocused", first: true, second: false, aside: 1 },
    { name: "both focused", first: true, second: true, aside: 0 },
  ];
  for (const row of rows) {
    win.minimized = 0;
    const { app, plugin } = await loaded({
      "a.md": "x", "b.md": "y",
      "tmp/review/1.request.json": req("1", "a.md", { return: !row.first }),
      "tmp/review/2.request.json": req("2", "b.md", { return: !row.second }),
    });
    await arriveByLink(plugin, "1", row.first);
    await arriveByLink(plugin, "2", row.second);
    await approve(app, "1");
    assert.equal(win.minimized, 0, `${row.name}: a review is still pending after the first answer`);
    await approve(app, "2");
    assert.equal(win.minimized, row.aside, `${row.name}: after the second answer`);
  }
});

// Adversarial where: the order of answering matters, so answering the
// unfocused card first and the focused card last (or the reverse) gives a
// different outcome from the same two arrivals.
test("two cards answered in either order give the same step aside", async () => {
  for (const order of [["1", "2"], ["2", "1"]]) {
    win.minimized = 0;
    const { app, plugin } = await loaded({
      "a.md": "x", "b.md": "y",
      "tmp/review/1.request.json": req("1", "a.md"),
      "tmp/review/2.request.json": req("2", "b.md"),
    });
    await arriveByLink(plugin, "1", false);
    await arriveByLink(plugin, "2", true);
    await approve(app, order[0]);
    assert.equal(win.minimized, 0, `order ${order}: one review still pending`);
    await approve(app, order[1]);
    assert.equal(win.minimized, 1, `order ${order}: after both answers`);
  }
});

// Adversarial where: a review found by the start-up scan has no arrival to
// measure, so the plugin reads the window's focus at answer time (or treats
// it as unfocused) instead of following the request's `return`.
test("a review found at start-up follows the request's `return`, whatever the window's focus", async () => {
  const rows = [
    { name: "return true, window focused", ret: true, focus: true, aside: 1 },
    { name: "return true, window unfocused", ret: true, focus: false, aside: 1 },
    { name: "return false, window focused", ret: false, focus: true, aside: 0 },
    { name: "return false, window unfocused", ret: false, focus: false, aside: 0 },
  ];
  for (const row of rows) {
    win.minimized = 0;
    const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md", { return: row.ret }) });
    win.hasFocus = row.focus;
    await app.workspace.ready();
    await sleep();
    await plugin.openPanel();
    await approve(app, "1");
    assert.equal(win.minimized, row.aside, row.name);
  }
});

// Adversarial where: a review the start-up scan already tracked is skipped
// when its link then arrives, so the arrival's focus is never recorded and
// `return` keeps deciding.
test("a link for a review the start-up scan already tracked records its own arrival", async () => {
  const rows = [
    { name: "return true, arrived focused", ret: true, focus: true, aside: 0 },
    { name: "return false, arrived unfocused", ret: false, focus: false, aside: 1 },
  ];
  for (const row of rows) {
    win.minimized = 0;
    const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md", { return: row.ret }) });
    await app.workspace.ready();
    await sleep();
    assert.deepEqual([...plugin.pending.keys()], ["1"], `${row.name}: tracked at start-up`);
    await arriveByLink(plugin, "1", row.focus);
    await approve(app, "1");
    assert.equal(win.minimized, row.aside, row.name);
  }
});

// Adversarial where: a start-up review pending beside a focused link review is
// decided by the link review's focus alone, so the start-up review's `return`
// is lost, or is applied when it said false.
test("a start-up review pending beside a focused link review steps aside only when the start-up review asked for return", async () => {
  const rows = [
    { name: "start-up return true", ret: true, aside: 1 },
    { name: "start-up return false", ret: false, aside: 0 },
  ];
  for (const row of rows) {
    win.minimized = 0;
    const { app, plugin } = await loaded({
      "a.md": "x", "b.md": "y",
      "tmp/review/1.request.json": req("1", "a.md", { return: row.ret }),
    });
    await app.workspace.ready();
    await sleep();
    app.store.set("tmp/review/2.request.json", req("2", "b.md", { return: false }));
    await arriveByLink(plugin, "2", true);
    await approve(app, "2");
    assert.equal(win.minimized, 0, `${row.name}: the start-up review is still pending`);
    await approve(app, "1");
    assert.equal(win.minimized, row.aside, `${row.name}: after the start-up review is answered`);
  }
});

// Adversarial where: an unfocused review answered while a second card is still
// pending leaves its step-aside debt behind when that second card is withdrawn
// (the terminal answered), so a focused review that arrives and is answered
// later hides the window although nothing about it arrived unfocused.
test("a step-aside debt does not outlive a withdrawn card into a later focused review", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "c.md": "z",
    "tmp/review/1.request.json": req("1", "a.md"),
    "tmp/review/2.request.json": req("2", "b.md"),
    "tmp/review/3.request.json": req("3", "c.md"),
  });
  await arriveByLink(plugin, "1", false);
  await arriveByLink(plugin, "2", true);
  await approve(app, "1");
  app.store.delete("tmp/review/2.request.json");
  await plugin.recheck();
  assert.equal(plugin.pending.size, 0, "the withdrawn card is gone");
  await arriveByLink(plugin, "3", true);
  await approve(app, "3");
  assert.equal(win.minimized, 0, "the focused review leaves the window in front");
});

// ---- the Compass view panel and the plan board ----
//
// The view panel is a second right-sidebar view, `compass-view-panel`, opened
// by `plugin.openViewPanel()`. It follows the active file and draws the view
// that the file's `type:` property picks. The plan board is the view for
// `type: plan`. Pure functions are static exports of main.js:
//
//   CompassReview.parsePlanTasks(text)   -> [{ id, title, wave, status, dependsOn, line }]
//   CompassReview.parsePlanChoices(text) -> [{ choice, answer, line }]
//   CompassReview.viewFor(text)          -> "plan" | null
//   CompassReview.choiceNoteLines(choices, answers) -> string[]
//   CompassReview.joinChoiceNote(note, lines)       -> string
//
// DOM the board draws, read by these tests (the panel content is
// `view.containerEl.children[1]`):
//   .compass-view-note      the one plain line for a type with no view
//   .compass-plan-board     the board root, one per plan in view
//   tr.compass-task-row     one per task, dataset.id and dataset.status, five td
//                           cells: id, task, wave, status, depends on
//   .compass-graph-node     one per task, dataset.id and dataset.status
//   .compass-graph-edge     one per dependency, dataset.from and dataset.to
//   tr.compass-choice-row   one per row of the choices table while a review of
//                           the plan is pending, dataset.choice, with an Agree
//                           button, a Change button and a note textarea
// A click on a row's first cell, or on a graph node, opens the plan with
// eState.line at the task line (0-based, as Obsidian takes it).

const VIEW_TYPE = "compass-view-panel";
const fixture = (name) => fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8").replace(/\r\n/g, "\n");
const PLAN_24 = fixture("PLAN-024.md");
const PLAN_25 = fixture("PLAN-025.md");
const P24 = ".compass/plans/PLAN-024-working-in-compass-is-visual.md";
const settle = async () => { await sleep(); await sleep(); };
const viewEl = (app) => { const v = viewOfType(app, VIEW_TYPE); return v ? v.containerEl.children[1] : null; };
const openDoc = async (app, p) => { await app.workspace.getLeaf().openFile(mdFile(p)); await settle(); };
const cellsOf = (row) => row.children.filter((c) => c.tag === "td");
const taskRows = (app) => viewEl(app).querySelectorAll(".compass-task-row");
const choiceRows = (app) => viewEl(app).querySelectorAll(".compass-choice-row");
const choiceRow = (app, name) => choiceRows(app).find((r) => r.dataset.choice === name);
const choiceButtons = (app) => viewEl(app).all().filter((e) => e.tag === "button" && (e.text === "Agree" || e.text === "Change"));

// A click on an element reaches the handlers of it and of its ancestors.
async function clickOn(el) {
  let fired = 0;
  for (let n = el; n; n = n.parent) {
    for (const fn of [n.onclick, ...(n.handlers.click || [])].filter((f) => typeof f === "function")) {
      fired++;
      await fn.call(n, { target: el, preventDefault() {}, stopPropagation() {} });
    }
  }
  assert.ok(fired, `nothing reacts to a click on <${el.tag}> "${el.text}"`);
}

// [task number, wave or null, status, dependency numbers, 1-based line in the fixture]
const T = (n, wave, status, deps, line) => ({ id: `TASK-${n}`, wave, status, dependsOn: deps.map((d) => `TASK-${d}`), line });
const EXPECT_24 = [
  T(189, 1, "done", [], 112), T(190, 1, "done", [189], 115), T(191, 1, "done", [189], 118), T(192, 1, "done", [189], 121),
  T(193, 1, "done", [192], 124), T(194, 1, "done", [], 127), T(195, 1, "done", [194], 130), T(196, 1, "done", [194], 133),
  T(198, 2, "done", [], 143), T(199, 2, "done", [], 146), T(200, 2, "done", [198], 149), T(225, 2, "done", [], 152),
  T(201, 2, "done", [199], 155), T(226, 3, "done", [], 163),
  T(202, 4, "ready", [], 171), T(206, 4, "waiting", [202], 174), T(227, 4, "waiting", [206], 177),
  T(228, 4, "waiting", [227], 180), T(203, 4, "waiting", [228], 183), T(204, 4, "ready", [], 186),
  T(197, null, "done", [], 194), T(207, null, "later", [], 195), T(205, null, "later", [], 196),
];
const EXPECT_25 = [
  T(208, 1, "done", [], 99), T(209, 1, "done", [208], 102), T(210, 1, "done", [], 105), T(211, 1, "done", [], 108),
  T(212, 1, "done", [], 111), T(213, 2, "done", [], 121), T(214, 2, "done", [213], 124), T(215, 2, "done", [214], 127),
  T(217, 2, "done", [], 130), T(218, 2, "done", [213, 214, 215, 217], 133), T(219, 2, "done", [218], 136),
  T(220, 3, "done", [], 146), T(221, 3, "done", [], 149), T(222, 4, "done", [], 159), T(223, 4, "done", [], 162),
  T(224, 4, "done", [222, 223], 165),
];
const shape = (tasks) => tasks.map(({ id, wave, status, dependsOn, line }) => ({ id, wave, status, dependsOn, line }));

// Adversarial where: the parser reads the task lines quoted in a fence or
// repeated under a `## Wave N elaborated` heading (PLAN-024 and PLAN-025 both
// quote their sketches there), harvests TASK ids out of a depends_on
// parenthetical ("none (PLAN-021 TASK-163 also edits...)"), mixes up the
// wave of a task, loses the line a click must open, or calls a task whose
// parents are unfinished "ready".
test("parsePlanTasks reads every task line of PLAN-024 and PLAN-025 with its wave, status, depends_on and line", async (t) => {
  await t.test("PLAN-024: 23 tasks, 4 quoted sketches under Wave 4 elaborated skipped", () => {
    assert.deepEqual(shape(CompassReview.parsePlanTasks(PLAN_24)), EXPECT_24);
  });
  await t.test("PLAN-025: 16 tasks, 5 indented lines under Wave 3 and Wave 4 elaborated skipped", () => {
    assert.deepEqual(shape(CompassReview.parsePlanTasks(PLAN_25)), EXPECT_25);
  });
  await t.test("a task's title carries no metadata", () => {
    for (const task of [...CompassReview.parsePlanTasks(PLAN_24), ...CompassReview.parsePlanTasks(PLAN_25)]) {
      assert.ok(task.title.length > 0, `${task.id} has a title`);
      assert.doesNotMatch(task.title, / - (complexity|files|depends_on|decisions|lessons|commit-upfront):/, `${task.id} title`);
    }
  });
});

// Adversarial where: a skip region ends at the wrong heading (a `###` inside
// an elaborated section reopens parsing, or the section never ends), a tilde
// fence is not a fence, TASK-1 and TASK-12 are confused by prefix, or a task
// with one finished parent and one open parent is called ready.
test("parsePlanTasks skips fences and elaborated sections exactly, and derives status from the checkbox, the Later section and the parents", () => {
  const text = [
    "---", 'title: "S"', "type: plan", "---", "",
    "# S", "", "## Phases", "",
    "### Wave 1 (detailed): first", "",
    "- [x] TASK-1: Base - complexity: S, depends_on: none, files: [a]",
    "- [ ] TASK-12: Twelve - complexity: S, depends_on: TASK-1, files: [a]",
    "- [ ] TASK-13: Thirteen - complexity: S, depends_on: TASK-12 (TASK-1 also edits a), files: [a]",
    "- [ ] TASK-14: Two parents - complexity: S, depends_on: TASK-1, TASK-12, files: [a]",
    "",
    "```markdown",
    "- [ ] TASK-90: inside a backtick fence - depends_on: none",
    "```",
    "~~~",
    "- [ ] TASK-91: inside a tilde fence",
    "~~~",
    "- [ ] TASK-15: After the fences - files: [a]",
    "",
    "## Wave 1 elaborated", "",
    "- [ ] TASK-92: sketch quoted in the elaboration - depends_on: none",
    "### A sub-heading inside the elaboration", "",
    "- [ ] TASK-93: still elaboration",
    "",
    "## Later (intent only)", "",
    "- [ ] TASK-16: Intent - files: [b]",
    "- [x] TASK-17: Done early - files: [b]",
  ].join("\n");
  const got = CompassReview.parsePlanTasks(text).map(({ id, wave, status, dependsOn }) => ({ id, wave, status, dependsOn }));
  assert.deepEqual(got, [
    { id: "TASK-1", wave: 1, status: "done", dependsOn: [] },
    { id: "TASK-12", wave: 1, status: "ready", dependsOn: ["TASK-1"] },
    { id: "TASK-13", wave: 1, status: "waiting", dependsOn: ["TASK-12"] },
    { id: "TASK-14", wave: 1, status: "waiting", dependsOn: ["TASK-1", "TASK-12"] },
    { id: "TASK-15", wave: 1, status: "ready", dependsOn: [] },
    { id: "TASK-16", wave: null, status: "later", dependsOn: [] },
    { id: "TASK-17", wave: null, status: "done", dependsOn: [] },
  ]);
});

// Adversarial where: the choices table is taken to be any table (a decoy
// above it, or one inside a fence), a `|` inside a code span splits a cell,
// or the header and separator rows come back as choices.
test("parsePlanChoices reads the Choice table of PLAN-024 and PLAN-025 and ignores other tables, fenced tables and pipes inside code spans", async (t) => {
  await t.test("PLAN-024: fifteen rows in table order", () => {
    const got = CompassReview.parsePlanChoices(PLAN_24);
    assert.deepEqual(got.map((c) => c.choice), [
      "Charts of metrics", "Decisions in callouts", "Embeds", "Task table", "Spec canvas", "Pages like Claude artifacts",
      "Coined terms", "Terminal visuals", "Lowest Obsidian version", "Where visuals live", "Chart format",
      "Chart library loading", "Data that is not notes", "Views", "How much a drawing may do",
    ]);
    const table = got.find((c) => c.choice === "Task table");
    assert.equal(table.answer, "drawn by the plugin from the task lines, never written into the file");
    assert.equal(table.line, 84);
  });
  await t.test("PLAN-025: fifteen rows, first and last", () => {
    const got = CompassReview.parsePlanChoices(PLAN_25);
    assert.equal(got.length, 15);
    assert.equal(got[0].choice, "Several files");
    assert.equal(got[0].line, 67);
    assert.equal(got[14].choice, "Stepping aside on VS Code");
  });
  await t.test("decoy table, fenced table, and a pipe inside a code span", () => {
    const lines = [
      "---", "type: plan", "---", "",
      "| Name | Value |", "| --- | --- |", "| not a choice | decoy |", "",
      "```markdown", "| Choice | Answer |", "| --- | --- |", "| fenced choice | no |", "```", "",
      "| Choice | The plan's answer (recommended) |", "| --- | --- |",
      "| Plain | one |",
      "| Pipes | run `a | b` or `c` here |",
      "| Last | end |",
      "", "Closing prose.",
    ];
    const got = CompassReview.parsePlanChoices(lines.join("\n"));
    assert.deepEqual(got, [
      { choice: "Plain", answer: "one", line: lines.indexOf("| Plain | one |") + 1 },
      { choice: "Pipes", answer: "run `a | b` or `c` here", line: lines.indexOf("| Pipes | run `a | b` or `c` here |") + 1 },
      { choice: "Last", answer: "end", line: lines.indexOf("| Last | end |") + 1 },
    ]);
  });
});

// Adversarial where: the picker reads `type:` out of the body, a nested or
// longer key, or a longer value (`planning`), fails on a quoted value, or
// invents a view for a file with no type.
test("viewFor picks the plan view from the type property alone and no view otherwise", () => {
  const rows = [
    ["plain type", "---\ntype: plan\n---\n# x\n", "plan"],
    ["quoted value among other properties", '---\ntitle: "A"\ntype: "plan"\nstatus: draft\n---\n', "plan"],
    ["trailing spaces", "---\ntype: plan   \n---\n", "plan"],
    ["no frontmatter", "# Notes\n", null],
    ["empty file", "", null],
    ["frontmatter with no type", "---\ntitle: x\n---\n", null],
    ["type line in the body after the frontmatter", "---\ntitle: x\n---\n\ntype: plan\n", null],
    ["type line in a file with no frontmatter", "# Notes\n\ntype: plan\n", null],
    ["a longer key ending in type", "---\nsubtype: plan\n---\n", null],
    ["a longer value starting with plan", "---\ntype: planning\n---\n", null],
    ["a type that has no view", "---\ntype: lesson\n---\n", null],
  ];
  for (const [name, text, want] of rows) assert.equal(CompassReview.viewFor(text), want, name);
});

// Adversarial where: Agree adds a line (the mockup added "Note on" lines for
// agreed rows), lines come out in click order instead of table order, an
// answer for a row the plan no longer has invents a line, or a multi-line
// note breaks the one-line-per-choice shape.
test("choiceNoteLines gives one line per changed choice and none for Agree, unanswered or vanished rows", () => {
  const choices = [
    { choice: "A", answer: "a", line: 10 }, { choice: "B", answer: "b", line: 11 },
    { choice: "C", answer: "c", line: 12 }, { choice: "D", answer: "d", line: 13 },
  ];
  const agree = (note = "") => ({ state: "agree", note });
  const change = (note) => ({ state: "change", note });
  const rows = [
    ["no answers", {}, []],
    ["Agree on every choice, one with a stray note", { A: agree(), B: agree("looks fine"), C: agree(), D: agree() }, []],
    ["one Change", { A: agree(), B: change("reword it") }, ["B: reword it"]],
    ["table order, not answer order", { D: change("n4"), B: change("n2") }, ["B: n2", "D: n4"]],
    ["an answer for a row the plan does not have", { B: change("n2"), Z: change("gone") }, ["B: n2"]],
  ];
  for (const [name, answers, want] of rows) assert.deepEqual(CompassReview.choiceNoteLines(choices, answers), want, name);
  const multi = CompassReview.choiceNoteLines(choices, { C: change("first part\nsecond part") });
  assert.equal(multi.length, 1);
  assert.doesNotMatch(multi[0], /\n/);
  assert.match(multi[0], /^C: first part\s+second part$/);
});

// Adversarial where: the lines replace the typed note instead of joining it,
// a blank line or leading newline appears when the note or the lines are
// empty, or a note with no lines is altered.
test("joinChoiceNote appends the lines to the review's note on their own lines", () => {
  const rows = [
    ["note and no lines", "overall", [], "overall"],
    ["no note and lines", "", ["A: x"], "A: x"],
    ["note and two lines", "overall", ["A: x", "B: y"], "overall\nA: x\nB: y"],
    ["neither", "", [], ""],
  ];
  for (const [name, note, lines, want] of rows) assert.equal(CompassReview.joinChoiceNote(note, lines), want, name);
});

// Adversarial where: the panel is a second copy of the review panel, opening
// it opens the review panel too, or each call adds another panel.
test("openViewPanel registers its own view type, reveals one panel in the right sidebar and opens no review panel", async () => {
  const { app, plugin } = await loaded({});
  assert.equal(typeof app.viewFactories[VIEW_TYPE], "function", "view type registered");
  await plugin.openViewPanel();
  await plugin.openViewPanel();
  const leaves = app.panelLeaves.filter((l) => l.view && l.view.getViewType() === VIEW_TYPE);
  assert.equal(leaves.length, 1);
  assert.ok(app.revealed.includes(leaves[0]), "panel revealed");
  assert.equal(viewOfType(app, "compass-review-panel"), null);
});

// Adversarial where: the panel draws once for the file open at the start and
// never follows, leaves the previous board under a file with another type,
// draws a board for a plan-looking line in a body, or stacks a second board
// on a return to the plan.
test("the panel follows the open document: board for a plan, one plain line for a type with no view, no board for a file with no type", async () => {
  const { app, plugin } = await loaded({
    [P24]: PLAN_24,
    "lesson.md": "---\ntype: lesson\ntitle: L\n---\nbody\n",
    "notes.md": "# Plain notes\n",
    "body-type.md": "# Heading\n\ntype: plan\n",
  });
  await openDoc(app, P24);
  await plugin.openViewPanel();
  await settle();
  assert.equal(viewEl(app).querySelectorAll(".compass-plan-board").length, 1, "board for the plan open at start");

  await openDoc(app, "lesson.md");
  assert.equal(viewEl(app).querySelectorAll(".compass-plan-board").length, 0, "no stale board under a lesson");
  const notes = viewEl(app).querySelectorAll(".compass-view-note");
  assert.equal(notes.length, 1);
  assert.match(notes[0].text, /lesson/);

  for (const name of ["notes.md", "body-type.md"]) {
    await openDoc(app, name);
    assert.equal(viewEl(app).querySelectorAll(".compass-plan-board").length, 0, `${name}: no board`);
    assert.equal(viewEl(app).querySelectorAll(".compass-task-row").length, 0, `${name}: no task rows`);
  }

  await openDoc(app, P24);
  assert.equal(viewEl(app).querySelectorAll(".compass-plan-board").length, 1, "board returns once");
  assert.equal(viewEl(app).querySelectorAll(".compass-task-row").length, EXPECT_24.length, "one table, not two");
});

// Adversarial where: the table or graph draws fewer tasks than the plan holds
// (fenced or elaborated lines mishandled), a wrong status colors a node, a
// parenthetical's TASK ids become dependency edges, or the dependency column
// lists a different task than the graph draws.
test("the plan board draws PLAN-024's task table and its dependency graph colored by status", async () => {
  const { app, plugin } = await loaded({ [P24]: PLAN_24 });
  await openDoc(app, P24);
  await plugin.openViewPanel();
  await settle();

  const rows = taskRows(app);
  assert.deepEqual(rows.map((r) => r.dataset.id), EXPECT_24.map((t) => t.id));
  assert.deepEqual(rows.map((r) => r.dataset.status), EXPECT_24.map((t) => t.status));
  rows.forEach((row, i) => {
    const want = EXPECT_24[i];
    const cells = cellsOf(row).map((c) => textOf(c));
    assert.equal(cells.length, 5, `${want.id}: id, task, wave, status, depends on`);
    assert.equal(cells[0].trim(), want.id);
    assert.ok(cells[1].trim().length > 0, `${want.id}: task text`);
    assert.doesNotMatch(cells[1], / - (complexity|files|depends_on|decisions|lessons|commit-upfront):/, `${want.id}: no metadata in the task text`);
    if (want.wave !== null) assert.match(cells[2], new RegExp(`\\b${want.wave}\\b`), `${want.id}: wave`);
    assert.deepEqual(cells[4].match(/TASK-\d+/g) || [], want.dependsOn, `${want.id}: depends on`);
  });

  const nodes = viewEl(app).querySelectorAll(".compass-graph-node");
  assert.deepEqual(nodes.map((n) => n.dataset.id), EXPECT_24.map((t) => t.id));
  assert.deepEqual(nodes.map((n) => n.dataset.status), EXPECT_24.map((t) => t.status));
  const edges = viewEl(app).querySelectorAll(".compass-graph-edge").map((e) => `${e.dataset.from}>${e.dataset.to}`).sort();
  const wantEdges = EXPECT_24.flatMap((t) => t.dependsOn.map((d) => `${d}>${t.id}`)).sort();
  assert.equal(wantEdges.length, 12);
  assert.deepEqual(edges, wantEdges);
});

// Adversarial where: a click opens the file at the wrong line (0-based and
// 1-based mixed up), opens a different task's line, opens nothing from the
// graph while the table works (or the reverse), or opens the file twice.
test("a click on a task row or a graph node opens the plan at that task's line", async () => {
  const { app, plugin } = await loaded({ [P24]: PLAN_24 });
  await openDoc(app, P24);
  await plugin.openViewPanel();
  await settle();
  const rowFor = (id) => taskRows(app).find((r) => r.dataset.id === id);
  const nodeFor = (id) => viewEl(app).querySelectorAll(".compass-graph-node").find((n) => n.dataset.id === id);
  const targets = [
    ["row of TASK-206", () => cellsOf(rowFor("TASK-206"))[0], 174],
    ["graph node of TASK-203", () => nodeFor("TASK-203"), 183],
    ["row of TASK-189, the first task", () => cellsOf(rowFor("TASK-189"))[0], 112],
  ];
  for (const [name, pick, line] of targets) {
    const before = app.opened.length;
    await clickOn(pick());
    await settle();
    assert.equal(app.opened.length, before + 1, `${name}: one file opened`);
    const last = app.opened[app.opened.length - 1];
    assert.equal(last.path, P24, name);
    assert.equal(last.state && last.state.eState && last.state.eState.line, line - 1, `${name}: 0-based line`);
  }
});

// A pending review of the plan, and the view panel open on it, in either order.
async function pendingPlan(order, planText = PLAN_24) {
  const request = "tmp/review/1.request.json";
  const r = await loaded({ [P24]: planText, "lesson.md": "---\ntype: lesson\n---\nx\n", [request]: req("1", P24) });
  if (order === "panel-first") {
    await openDoc(r.app, P24);
    await r.plugin.openViewPanel();
    await settle();
    await r.plugin.handler({ request });
  } else {
    await r.plugin.handler({ request });
    await r.plugin.openViewPanel();
  }
  await settle();
  return r;
}
const verdictNotes = (app) => verdictOf(app, "tmp/review/1.verdict.json").notes;
const answerChange = async (app, name, note) => {
  await click(button(choiceRow(app, name), "Change"));
  typeInto(choiceRow(app, name).all().find((e) => e.tag === "textarea"), note);
};

// Adversarial where: the choices rows take no answers or show them with no
// review pending, the controls appear only when the review arrives before the
// panel (or only after), or they stay after the review is answered.
test("each choice row takes Agree or Change only while a review of this plan is pending", async (t) => {
  for (const order of ["review-first", "panel-first"]) {
    await t.test(`${order}: fifteen rows, each with Agree, Change; gone after the answer`, async () => {
      const { app } = await pendingPlan(order);
      assert.equal(choiceRows(app).length, 15);
      for (const row of choiceRows(app)) {
        assert.ok(button(row, "Agree") && button(row, "Change"), `${row.dataset.choice}: both buttons`);
      }
      await click(cardBtn(app, "1", "Approve"));
      await settle();
      assert.equal(choiceButtons(app).length, 0, "no controls once the review is answered");
    });
  }
  await t.test("a review of another file leaves the plan's rows without controls", async () => {
    const request = "tmp/review/2.request.json";
    const { app, plugin } = await loaded({ [P24]: PLAN_24, "lesson.md": "---\ntype: lesson\n---\nx\n", [request]: req("2", "lesson.md") });
    await openDoc(app, P24);
    await plugin.openViewPanel();
    await plugin.handler({ request });
    await openDoc(app, P24);
    assert.equal(taskRows(app).length, EXPECT_24.length, "the board is drawn");
    assert.equal(choiceButtons(app).length, 0);
  });
  await t.test("no review at all", async () => {
    const { app, plugin } = await loaded({ [P24]: PLAN_24 });
    await openDoc(app, P24);
    await plugin.openViewPanel();
    await settle();
    assert.equal(choiceButtons(app).length, 0);
  });
});

// Adversarial where: the board's Change answers never reach the verdict, replace
// the typed note, land in click order, survive only until the next redraw, stay
// when the human changes their mind to Agree, or an all-Agree board adds text.
test("Change answers join the review's note as one line each, in table order, and Agree adds nothing", async (t) => {
  await t.test("two Changes answered out of table order join the typed note", async () => {
    const { app } = await pendingPlan("review-first");
    await answerChange(app, "Views", "add a diagram");
    await click(button(choiceRow(app, "Embeds"), "Agree"));
    await answerChange(app, "Task table", "reword it");
    typeInto(notesIn(cardFor(app, "1")), "overall");
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    assert.equal(verdictNotes(app), "overall\nTask table: reword it\nViews: add a diagram");
  });
  await t.test("Agree on every choice adds no line", async () => {
    const { app } = await pendingPlan("review-first");
    for (const row of choiceRows(app)) await click(button(row, "Agree"));
    typeInto(notesIn(cardFor(app, "1")), "overall");
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    assert.equal(verdictNotes(app), "overall");
  });
  await t.test("a Change turned into Agree adds no line", async () => {
    const { app } = await pendingPlan("review-first");
    await answerChange(app, "Task table", "reword it");
    await click(button(choiceRow(app, "Task table"), "Agree"));
    typeInto(notesIn(cardFor(app, "1")), "overall");
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    assert.equal(verdictNotes(app), "overall");
  });
  await t.test("a Change survives the panel redrawing on workspace events", async () => {
    const { app } = await pendingPlan("panel-first");
    await answerChange(app, "Spec canvas", "keep the cards");
    app.wsListeners["layout-change"]();
    app.wsListeners["file-open"](mdFile(P24));
    await settle();
    typeInto(notesIn(cardFor(app, "1")), "overall");
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    assert.equal(verdictNotes(app), "overall\nSpec canvas: keep the cards");
  });
});

// Adversarial where: opening the board, answering its rows or clicking a task
// writes into the vault (the mockup's Mark done changed task state), even a
// rewrite that leaves the bytes the same.
test("opening the board, answering its choices and clicking a task write nothing into the vault", async () => {
  const { app, plugin } = await loaded({
    [P24]: PLAN_24,
    ".compass/specs/SPEC-1.md": "---\ntype: spec\n---\nx\n",
    ".compass/tmp/review/1.request.json": req("1", P24),
  });
  await plugin.handler({ request: ".compass/tmp/review/1.request.json" });
  const before = Object.fromEntries(app.store);
  const writes = [];
  const write = app.vault.adapter.write;
  app.vault.adapter.write = async (p, d) => { writes.push(p); return write.call(app.vault.adapter, p, d); };

  await plugin.openViewPanel();
  await settle();
  assert.equal(taskRows(app).length, EXPECT_24.length, "the board is drawn");
  await click(button(choiceRow(app, "Embeds"), "Agree"));
  await answerChange(app, "Task table", "reword it");
  await clickOn(cellsOf(taskRows(app)[0])[0]);
  await settle();
  app.wsListeners["layout-change"]();
  await settle();

  assert.deepEqual(writes, []);
  assert.deepEqual(Object.fromEntries(app.store), before);
});

// ---- the view panel read against the implementation ----

const planWith = (body, head = "type: plan\ntitle: P") => `---\n${head}\n---\n# P\n\n${body}`;
const choiceTable = (...names) => `| Choice | Answer |\n|---|---|\n${names.map((n) => `| ${n} | answer |`).join("\n")}\n`;
const REQ1 = "tmp/review/1.request.json";
const countNodes = (el) => el.all().length;

// Adversarial where: a dependency cycle, a task that depends on itself or on a
// task the plan does not hold sends the layout into endless recursion, drops
// the task from the board, or leaves a task waiting on a parent that cannot
// finish.
test("cycles, self-dependencies and parents absent from the plan still draw every task", async () => {
  const body = [
    "### Wave 1",
    "- [ ] TASK-1: a - files: [x], complexity: S, depends_on: TASK-2",
    "- [ ] TASK-2: b - files: [x], complexity: S, depends_on: TASK-1",
    "- [ ] TASK-3: c - files: [x], complexity: S, depends_on: TASK-3",
    "- [ ] TASK-4: d - files: [x], complexity: S, depends_on: TASK-999",
    "- [ ] TASK-5: e - files: [x], complexity: S, depends_on: TASK-4, TASK-999",
  ].join("\n");
  const { app, plugin } = await loaded({ "p.md": planWith(body) });
  await openDoc(app, "p.md");
  await plugin.openViewPanel();
  await settle();
  const status = Object.fromEntries(taskRows(app).map((r) => [r.dataset.id, r.dataset.status]));
  assert.deepEqual(status, { "TASK-1": "waiting", "TASK-2": "waiting", "TASK-3": "waiting", "TASK-4": "ready", "TASK-5": "waiting" });
  assert.equal(viewEl(app).querySelectorAll(".compass-graph-node").length, 5);
  const edges = viewEl(app).querySelectorAll(".compass-graph-edge").map((e) => `${e.dataset.from}>${e.dataset.to}`).sort();
  assert.deepEqual(edges, ["TASK-1>TASK-2", "TASK-2>TASK-1", "TASK-3>TASK-3", "TASK-4>TASK-5"]);
});

// Adversarial where: a plan with thousands of tasks, listed so each depends on
// the task after it, blows the stack of the depth walk or takes seconds to draw.
test("a plan of 3000 tasks chained against file order draws every row and node in under 5 seconds", async () => {
  const n = 3000;
  const lines = ["### Wave 1"];
  for (let i = 1; i <= n; i++) lines.push(`- [ ] TASK-${i}: t${i} - files: [x], complexity: S, depends_on: ${i < n ? `TASK-${i + 1}` : "none"}`);
  const { app, plugin } = await loaded({ "p.md": planWith(lines.join("\n")) });
  await openDoc(app, "p.md");
  const started = Date.now();
  await plugin.openViewPanel();
  await settle();
  assert.equal(taskRows(app).length, n);
  assert.equal(viewEl(app).querySelectorAll(".compass-graph-node").length, n);
  assert.ok(Date.now() - started < 5000, `drew in ${Date.now() - started} ms`);
});

// Adversarial where: a plan saved with CRLF line ends, or a byte order mark,
// leaves a carriage return in a task title, a choice name or the verdict note,
// or loses the property block and so the board.
test("a CRLF plan with a byte order mark reads like its LF twin and its verdict carries no carriage return", async () => {
  const crlf = "﻿" + PLAN_24.replace(/\n/g, "\r\n");
  assert.deepEqual(shape(CompassReview.parsePlanTasks(crlf)), shape(CompassReview.parsePlanTasks(PLAN_24)));
  assert.deepEqual(CompassReview.parsePlanChoices(crlf), CompassReview.parsePlanChoices(PLAN_24));
  const { app, plugin } = await loaded({ [P24]: crlf, [REQ1]: req("1", P24) });
  await plugin.handler({ request: REQ1 });
  await plugin.openViewPanel();
  await settle();
  assert.equal(taskRows(app).length, EXPECT_24.length);
  await answerChange(app, "Task table", "reword it");
  await click(cardBtn(app, "1", "Needs changes"));
  await settle();
  assert.equal(verdictNotes(app), "Task table: reword it");
  for (const row of taskRows(app)) assert.ok(!/\r/.test(row.all().map((e) => e.text).join("")), row.dataset.id);
});

// Adversarial where: two table rows with the same choice name share one answer,
// so one Change is sent to Claude twice.
test("a choices table that names two rows alike sends one line for the one answer", () => {
  const lines = CompassReview.choiceNoteLines(
    CompassReview.parsePlanChoices(planWith(choiceTable("Views", "Views"))),
    Object.assign(Object.create(null), { Views: { state: "change", note: "n" } })
  );
  assert.deepEqual(lines, ["Views: n"]);
});

// Adversarial where: a choice named like an Object.prototype member
// (`constructor`, `__proto__`, `hasOwnProperty`) reads as already answered, or
// a note holding a newline breaks one answer into two lines of the note.
test("choice names that are Object members and notes holding newlines give exactly one line each", async () => {
  const names = ["constructor", "__proto__", "hasOwnProperty", "toString"];
  const { app, plugin } = await loaded({ "p.md": planWith(choiceTable(...names)), [REQ1]: req("1", "p.md") });
  await plugin.handler({ request: REQ1 });
  await openDoc(app, "p.md");
  await plugin.openViewPanel();
  await settle();
  assert.deepEqual(plugin.changedChoiceLines(plugin.pending.get("1")), [], "nothing answered yet");
  await answerChange(app, "toString", "first line\nsecond: line\r\n  third");
  await answerChange(app, "constructor", "  padded  ");
  await click(cardBtn(app, "1", "Needs changes"));
  await settle();
  assert.equal(verdictNotes(app), "constructor: padded\ntoString: first line second: line third");
});

// Adversarial where: a changed choice stays in the answers after the plan
// drops its row, so Needs changes is enabled yet sends a note with no feedback.
test("Needs changes never sends an empty verdict when the answered choice vanished from the plan", async () => {
  const { app, plugin } = await loaded({ "p.md": planWith(choiceTable("Views", "Embeds")), [REQ1]: req("1", "p.md") });
  await plugin.handler({ request: REQ1 });
  await openDoc(app, "p.md");
  await plugin.openViewPanel();
  await settle();
  await answerChange(app, "Views", "add a diagram");
  app.store.set("p.md", planWith(choiceTable("Embeds")));
  const btn = cardBtn(app, "1", "Needs changes");
  if (btn.disabled) return;
  await click(btn);
  await settle();
  const sent = verdictOf(app, "tmp/review/1.verdict.json");
  assert.ok(sent.notes.trim() !== "", `Needs changes went out with notes ${JSON.stringify(sent.notes)}`);
});

// Adversarial where: in a review of several files the choice lines land in the
// first file's note (or none) instead of the plan's, or a whitespace-only
// typed note leaves a blank line ahead of them.
test("in a three-file review the plan's choice lines join the plan's own note and the combined notes", async () => {
  const { app, plugin } = await loaded({
    "a.md": "---\ntype: spec\n---\nx\n",
    "p.md": planWith(choiceTable("Views")),
    "b.md": "---\ntype: spec\n---\ny\n",
    [REQ1]: JSON.stringify({ id: "1", file: "a.md", title: "T", return: true, files: [{ file: "a.md", why: "w" }, { file: "p.md", why: "w" }, { file: "b.md", why: "w" }] }),
  });
  await plugin.handler({ request: REQ1 });
  await openDoc(app, "p.md");
  await plugin.openViewPanel();
  await settle();
  await answerChange(app, "Views", "add a diagram");
  await click(cardBtn(app, "1", "Needs changes"));
  await settle();
  const sent = verdictOf(app, "tmp/review/1.verdict.json");
  assert.deepEqual(sent.files.map((f) => f.note), [undefined, "Views: add a diagram", undefined]);
  assert.equal(sent.notes, "p: Views: add a diagram");
});

// Adversarial where: the review panel changes when the view panel is open:
// the same review sends another answer, or an Approve after only Agree
// answers carries text.
test("with the view panel open an Approve on a plan answered only with Agree equals the answer sent with no view panel", async () => {
  const strip = (v) => { const { at, ...rest } = v; return rest; };
  const without = await loaded({ [P24]: PLAN_24, [REQ1]: req("1", P24) });
  await without.plugin.handler({ request: REQ1 });
  await click(cardBtn(without.app, "1", "Approve"));
  await settle();
  const withPanel = await loaded({ [P24]: PLAN_24, [REQ1]: req("1", P24) });
  await withPanel.plugin.handler({ request: REQ1 });
  await withPanel.plugin.openViewPanel();
  await settle();
  for (const row of choiceRows(withPanel.app)) await click(button(row, "Agree"));
  await click(cardBtn(withPanel.app, "1", "Approve"));
  await settle();
  assert.deepEqual(strip(verdictOf(withPanel.app, "tmp/review/1.verdict.json")), strip(verdictOf(without.app, "tmp/review/1.verdict.json")));
});

// Adversarial where: the choices table of a second plan that no review lists
// takes answers because a review of the first plan is pending.
test("a review of one plan gives another plan's choices table no controls", async () => {
  const { app, plugin } = await loaded({
    "a.md": planWith(choiceTable("Views")),
    "b.md": planWith(choiceTable("Views")),
    [REQ1]: req("1", "a.md"),
  });
  await plugin.handler({ request: REQ1 });
  await openDoc(app, "a.md");
  await plugin.openViewPanel();
  await settle();
  assert.equal(choiceRows(app).length, 1);
  await openDoc(app, "b.md");
  assert.equal(choiceButtons(app).length, 0);
  assert.equal(choiceRows(app).length, 0);
  await openDoc(app, "a.md");
  assert.equal(choiceRows(app).length, 1, "the first plan's controls return");
});

// Adversarial where: a slow read of the plan finishes after the human has moved
// to another document and paints the plan's board over that document's note.
test("a plan read that finishes after the human opened another document does not repaint the board", async () => {
  const { app, plugin } = await loaded({ "p.md": planWith(choiceTable("Views")), "l.md": "---\ntype: lesson\n---\nx\n" });
  await openDoc(app, "l.md");
  await plugin.openViewPanel();
  await settle();
  const held = gate();
  const read = app.vault.adapter.read;
  app.vault.adapter.read = async (p) => { if (p === "p.md") await held.wait; return read.call(app.vault.adapter, p); };
  await app.workspace.getLeaf().openFile(mdFile("p.md"));
  app.vault.adapter.read = read;
  await app.workspace.getLeaf().openFile(mdFile("l.md"));
  await settle();
  held.release();
  await settle();
  assert.equal(taskRows(app).length, 0);
  assert.match(viewEl(app).all().map((e) => e.text).join(" "), /type lesson/);
});

// Adversarial where: every file save or workspace event adds nodes or handlers
// to the panel instead of replacing them, so a long session leaks elements.
test("fifty saves of the open plan leave the panel the size of one board", async () => {
  const { app, plugin } = await loaded({ [P24]: PLAN_24, [REQ1]: req("1", P24) });
  await plugin.handler({ request: REQ1 });
  await openDoc(app, P24);
  await plugin.openViewPanel();
  await settle();
  const size = countNodes(viewEl(app));
  for (let i = 0; i < 50; i++) {
    app.store.set(P24, PLAN_24 + `\n<!-- ${i} -->\n`);
    await app.listeners.modify(mdFile(P24));
    app.wsListeners["layout-change"]();
    await settle();
  }
  assert.equal(countNodes(viewEl(app)), size);
  assert.equal(app.panelLeaves.filter((l) => l.view && l.view.getViewType() === VIEW_TYPE).length, 1);
});

// Adversarial where: unloading the plugin throws, or a file saved after the
// unload still draws into a panel the plugin no longer owns.
test("unloading the plugin and then saving the open plan throws nothing", async () => {
  const { app, plugin } = await loaded({ [P24]: PLAN_24 });
  await openDoc(app, P24);
  await plugin.openViewPanel();
  await settle();
  plugin.onunload();
  await app.listeners.modify(mdFile(P24));
  await settle();
});

// ---- spec and research cards in the view panel ----
//
// The view panel draws `type: spec` and `type: research` documents. Pure
// functions are static exports of main.js:
//
//   CompassReview.viewFor(text) -> "plan" | "spec" | "research" | null
//   CompassReview.parseSpec(text) -> { problem, desiredOutcome, problemLine, desiredOutcomeLine,
//       decisions: [{ id, text, trackable, tags, line }], decisionState }
//       The decisions are what `compass decisions` reports (text with callout
//       markers, block id and line breaks folded away; `line` 1-based);
//       decisionState is "parsed" | "none-present" | "could-not-parse".
//       problem and desiredOutcome are the trimmed section bodies, "" and line 0
//       when the section is absent.
//   CompassReview.parseResearchFindings(text) -> [{ n, text, conf, confNote, grade, evidence, section, line }]
//       Rows of tables whose header names a "Finding" column; conf is the
//       leading "high" | "medium" | "low" of the Conf. cell, lower-cased, or "".
//   CompassReview.countFindingsBySection(findings) -> [{ name, high, medium, low, other, total }]
//   CompassReview.filterFindings(findings, confs) -> findings whose conf is in
//       the array `confs`; a finding with conf "" stays under every filter.
//   CompassReview.decisionNoteLines(decisions, answers) -> string[]
//       answers: { "D-01": { state: "agree" | "change", note } }. One
//       `D-NN: <note>` line per decision answered "change" with a non-blank
//       note, once per id, in document order, then answers whose decision left
//       the spec; the note's whitespace runs fold to one space.
//
// DOM, read by these tests (the panel content is `view.containerEl.children[1]`):
//   .compass-spec-view          root, one per spec in view
//   .compass-spec-problem       the Problem text; .compass-spec-outcome the Desired Outcome text
//   .compass-decision-card      one per decision, dataset.id "D-NN", in document order. While a
//                               review that lists the spec is pending it holds an Agree button, a
//                               Change button and a textarea. Class is-agree / is-change after an
//                               answer. A Change clicked with a blank note is refused: no is-change,
//                               and the card holds a .compass-decision-need-note element with text.
//   .compass-research-view      root, one per research document in view
//   .compass-section-bar        one per section holding findings, dataset.section, dataset.total,
//                               dataset.high, dataset.medium, dataset.low (counts as strings)
//   button.compass-conf-filter  dataset.conf "high" | "medium" | "low", class is-on while enabled
//   .compass-finding-row        one per shown finding, dataset.n; a click on the row opens the
//                               document at eState.line = finding line - 1

const SPEC_FILES = {
  "SPEC-007-decision-coverage-tracing.md": fixture("SPEC-007-decision-coverage-tracing.md"),
  "SPEC-023-research-covers-the-whole-spec.md": fixture("SPEC-023-research-covers-the-whole-spec.md"),
  "SPEC-031-working-in-compass-is-visual.md": fixture("SPEC-031-working-in-compass-is-visual.md"),
  "SPEC-callout-decisions.md": fixture("SPEC-callout-decisions.md"),
  "SPEC-malformed-decision.md": fixture("SPEC-malformed-decision.md"),
};
const SPEC_EXPECT = JSON.parse(fixture("spec-decisions.expected.json"));
const RESEARCH_TEXT = fixture("RESEARCH-working-in-compass-is-visual.md");
const RESEARCH_EXPECT = JSON.parse(fixture("research-findings.expected.json"));
const SP = ".compass/specs/SPEC-900-fixture.md";
const RP = ".compass/research/RESEARCH-fixture.md";
const pickDecision = (d) => ({ id: d.id, text: d.text, trackable: d.trackable, tags: d.tags, line: d.line });
const textOfEl = (el) => el.all().map((e) => e.text).join(" ");
const decisionCards = (app) => viewEl(app).querySelectorAll(".compass-decision-card");
const decisionCard = (app, id) => decisionCards(app).find((c) => c.dataset.id === id);
const cardArea = (card) => card.all().find((e) => e.tag === "textarea");
const sectionOf = (text, from, to) => text.split(to)[0].split(from)[1].trim();

// Adversarial where: the type picks the wrong view: a spec or research
// document gets no view, a plan is taken for a spec, a lookalike type
// (specs, researcher) or a `type:` line in the body picks a view, or a
// byte order mark and CRLF hide the property.
test("viewFor picks spec and research from the type property alone", () => {
  const rows = [
    ["spec", "---\ntype: spec\n---\n# S\n", "spec"],
    ["research", "---\ntype: research\n---\n# R\n", "research"],
    ["plan stays plan", "---\ntype: plan\n---\n# P\n", "plan"],
    ["quoted type", '---\ntype: "spec"\n---\n', "spec"],
    ["CRLF and BOM", "﻿---\r\ntype: research\r\n---\r\n# R\r\n", "research"],
    ["decision has no view", "---\ntype: decision\n---\n# A\n", null],
    ["specs is not spec", "---\ntype: specs\n---\n", null],
    ["researcher is not research", "---\ntype: researcher\n---\n", null],
    ["type in the body only", "# Spec\n\ntype: spec\n", null],
    ["type below a heading after the properties", "---\ntitle: T\n---\n# H\ntype: research\n", null],
  ];
  for (const [name, text, want] of rows) assert.equal(CompassReview.viewFor(text), want, name);
});

// Adversarial where: the decisions the panel reads differ from the ones
// `compass decisions` reports for the same spec: callout markers left in
// the text, a nested `> >` bullet dropped, a block id kept in the text, a
// continuation line lost, a [deferred] tag or a discretion group still
// trackable, a fenced example counted, or a spec the CLI cannot parse
// passing as clean.
test("parseSpec reads the decisions exactly as compass decisions does, from plain bullets and from callouts", async (t) => {
  for (const [file, text] of Object.entries(SPEC_FILES)) {
    await t.test(file, () => {
      const got = CompassReview.parseSpec(text);
      assert.deepEqual(got.decisions.map(pickDecision), SPEC_EXPECT[file].decisions.map(pickDecision));
      assert.equal(got.decisionState, SPEC_EXPECT[file].outcome);
    });
  }
  await t.test("a spec with no decisions section is none-present with no cards", () => {
    const got = CompassReview.parseSpec("---\ntype: spec\n---\n## Problem\nx\n");
    assert.deepEqual(got.decisions, []);
    assert.equal(got.decisionState, SPEC_EXPECT["inline-none-present"].outcome);
  });
  await t.test("CRLF with a byte order mark gives the LF reading and the same line numbers", () => {
    const text = "﻿" + SPEC_FILES["SPEC-callout-decisions.md"].replace(/\n/g, "\r\n");
    assert.deepEqual(
      CompassReview.parseSpec(text).decisions.map(pickDecision),
      SPEC_EXPECT["SPEC-callout-decisions.md"].decisions.map(pickDecision),
    );
  });
});

// Adversarial where: the Problem or Desired Outcome shows reworded, cut at a
// sub-heading or at a heading-shaped line inside a fence, merged with the
// next section, taken from a decoy heading that only starts with "Problem",
// or invented when the section is absent.
test("parseSpec keeps the Problem and the Desired Outcome as the spec's own text", () => {
  const s31 = SPEC_FILES["SPEC-031-working-in-compass-is-visual.md"];
  const got31 = CompassReview.parseSpec(s31);
  assert.equal(got31.problem, sectionOf(s31, "## Problem\n", "\n## Desired Outcome"));
  assert.equal(got31.desiredOutcome, sectionOf(s31, "## Desired Outcome\n", "\n## Decisions"));
  assert.ok(got31.problem.startsWith("Right now everything in using Compass is a wall of text."));
  assert.equal(got31.problemLine, s31.split("\n").indexOf("## Problem") + 1);
  assert.equal(got31.desiredOutcomeLine, s31.split("\n").indexOf("## Desired Outcome") + 1);

  const callout = CompassReview.parseSpec(SPEC_FILES["SPEC-callout-decisions.md"]);
  assert.match(callout.problem, /^People lose track of rulings\./);
  assert.match(callout.problem, /### A sub-heading inside the problem\n\nStill the problem\.$/, "a ### heading stays inside the section");
  assert.doesNotMatch(callout.problem, /Every ruling/);
  assert.match(callout.desiredOutcome, /^Every ruling is a card\./);
  assert.match(callout.desiredOutcome, /D-99/, "a fenced `## Decisions` does not end the section");

  const decoy = CompassReview.parseSpec("---\ntype: spec\n---\n## Problem Space\nwrong\n\n## Problem\nright\n");
  assert.equal(decoy.problem, "right");
  const none = CompassReview.parseSpec("---\ntype: spec\n---\n## Context\nonly this\n");
  assert.equal(none.problem, "");
  assert.equal(none.desiredOutcome, "");
  assert.equal(none.problemLine, 0);
});

// Adversarial where: the findings read differ from the research document: the
// Methodology table's numbered rows are taken for findings (135 findings
// become 142), a row inside a fence counts, a pipe inside a code span splits a
// cell, a mixed confidence ("high (x), low (y)") reads as none or as low, a
// short row throws or shifts cells, or a row with no number is kept.
test("parseResearchFindings reads number, confidence and evidence from the evidence document and from malformed rows", async (t) => {
  await t.test("RESEARCH-working-in-compass-is-visual: 135 findings, number, confidence, line and section per row", () => {
    const got = CompassReview.parseResearchFindings(RESEARCH_TEXT);
    assert.equal(got.length, RESEARCH_EXPECT.total);
    assert.deepEqual(got.map((f) => ({ n: f.n, conf: f.conf, line: f.line, section: f.section })), RESEARCH_EXPECT.rows);
  });
  await t.test("RESEARCH-working-in-compass-is-visual: evidence and the full confidence cell of four rows", () => {
    const byN = new Map(CompassReview.parseResearchFindings(RESEARCH_TEXT).map((f) => [f.n, f]));
    for (const [n, want] of Object.entries(RESEARCH_EXPECT.spot)) {
      assert.equal(byN.get(Number(n)).evidence, want.evidence, `finding ${n} evidence`);
      assert.equal(byN.get(Number(n)).confNote, want.confNote, `finding ${n} confidence cell`);
    }
    assert.equal(byN.get(26).grade.toLowerCase(), "medium (bullock), low (expert quotes)");
  });
  await t.test("malformed rows: code-span pipe, upper case, mixed and missing confidence, short rows, fences, other tables", () => {
    const doc = [
      "---", "type: research", "---", "# R", "", "## Findings", "",
      "### A. First (axis 1)", "",
      "| # | Finding | Conf. | Grade | Evidence |", "|---|---|---|---|---|",
      "| 1 | Plain finding | high | high | `a.js:1` |",
      "| 2 | Pipe in `a|b` code | MEDIUM | low | ev2 |",
      "| 3 | Split confidence | high (x), low (y) | medium | ev3 |",
      "| 4 | No rating | n/a | | ev4 |",
      "| 5 | Short row | low |",
      "| - | Not numbered | high | high | ev |",
      "",
      "```", "| # | Finding | Conf. | Grade | Evidence |", "|---|---|---|---|---|", "| 6 | Fenced | high | high | ev6 |", "```", "",
      "### B. Other table (axis 2)", "", "| Axis | Question | Method |", "|---|---|---|", "| 7 | What | How |", "",
      "### C. Three columns", "", "| # | Finding | Conf. |", "|---|---|---|", "| 8 | Three columns | medium |", "",
    ];
    const got = CompassReview.parseResearchFindings(doc.join("\n"));
    assert.deepEqual(got.map((f) => f.n), [1, 2, 3, 4, 5, 8]);
    const by = Object.fromEntries(got.map((f) => [f.n, f]));
    assert.equal(by[1].evidence, "`a.js:1`");
    assert.equal(by[1].line, doc.indexOf("| 1 | Plain finding | high | high | `a.js:1` |") + 1);
    assert.equal(by[2].text, "Pipe in `a|b` code");
    assert.equal(by[2].conf, "medium");
    assert.equal(by[2].evidence, "ev2");
    assert.equal(by[3].conf, "high");
    assert.equal(by[3].confNote, "high (x), low (y)");
    assert.equal(by[4].conf, "");
    assert.equal(by[5].conf, "low");
    assert.equal(by[5].evidence, "");
    assert.equal(by[5].grade, "");
    assert.equal(by[8].section, "C. Three columns");
    assert.equal(by[8].evidence, "");
    assert.equal(by[1].section, "A. First (axis 1)");
  });
});

// Adversarial where: the section bars count something other than the findings
// (a section of a skipped table, a mixed confidence counted twice or as
// "other"), put sections in another order, or the confidence filter drops
// a finding with no rating or keeps one it should hide.
test("countFindingsBySection and filterFindings count by section in document order and filter by confidence", async (t) => {
  await t.test("the evidence document: ten sections whose counts match the table rows", () => {
    const got = CompassReview.countFindingsBySection(CompassReview.parseResearchFindings(RESEARCH_TEXT));
    assert.deepEqual(got, RESEARCH_EXPECT.sections);
    assert.equal(got.reduce((sum, s) => sum + s.total, 0), RESEARCH_EXPECT.total);
  });
  const mk = (n, conf, section) => ({ n, conf, section, text: "", confNote: conf, grade: "", evidence: "", line: n });
  const list = [mk(1, "high", "B"), mk(2, "low", "A"), mk(3, "", "B"), mk(4, "medium", "A"), mk(5, "high", "B")];
  await t.test("first appearance orders the sections; an unrated finding counts as other and in the total", () => {
    assert.deepEqual(CompassReview.countFindingsBySection(list), [
      { name: "B", high: 2, medium: 0, low: 0, other: 1, total: 3 },
      { name: "A", high: 0, medium: 1, low: 1, other: 0, total: 2 },
    ]);
  });
  const rows = [
    ["only high", ["high"], [1, 3, 5]],
    ["high and low", ["high", "low"], [1, 2, 3, 5]],
    ["all three", ["high", "medium", "low"], [1, 2, 3, 4, 5]],
    ["none: only the unrated stays", [], [3]],
  ];
  for (const [name, confs, want] of rows) {
    await t.test(name, () => assert.deepEqual(CompassReview.filterFindings(list, confs).map((f) => f.n), want));
  }
  await t.test("an empty document has no sections and no findings", () => {
    assert.deepEqual(CompassReview.parseResearchFindings("---\ntype: research\n---\n# R\n"), []);
    assert.deepEqual(CompassReview.countFindingsBySection([]), []);
  });
});

// Adversarial where: a changed decision sends a line even when its note is
// blank (a stale "(no note)" line), Agree adds a line, lines follow the order
// of clicks instead of the spec's, one answer sent for two decisions that
// share an id sends two lines, an answer to a decision no longer in the
// spec vanishes, or a note with a line break splits the line in two.
test("decisionNoteLines gives one D-NN line per Change with a note, in document order", async (t) => {
  const decs = ["D-01", "D-02", "D-03", "D-04"].map((id) => ({ id }));
  const rows = [
    ["Change gives the line, Agree none", { "D-02": { state: "change", note: "reword" }, "D-01": { state: "agree", note: "fine" } }, ["D-02: reword"]],
    ["document order, not answer order", { "D-04": { state: "change", note: "b" }, "D-01": { state: "change", note: "a" } }, ["D-01: a", "D-04: b"]],
    ["a blank Change gives no line", { "D-01": { state: "change", note: "" }, "D-02": { state: "change", note: " \n\t " } }, []],
    ["a one-character note is a note", { "D-03": { state: "change", note: "x" } }, ["D-03: x"]],
    ["whitespace folds and the ends trim", { "D-01": { state: "change", note: "  a\n\n b\t c  " } }, ["D-01: a b c"]],
    ["unanswered decisions give none", {}, []],
    ["a Change whose decision left the spec still goes, after the rest", { "D-09": { state: "change", note: "gone" }, "D-01": { state: "change", note: "kept" } }, ["D-01: kept", "D-09: gone"]],
  ];
  for (const [name, answers, want] of rows) {
    await t.test(name, () => assert.deepEqual(CompassReview.decisionNoteLines(decs, answers), want));
  }
  await t.test("two decisions sharing an id send the one answer once", () => {
    assert.deepEqual(CompassReview.decisionNoteLines([{ id: "D-01" }, { id: "D-01" }], { "D-01": { state: "change", note: "n" } }), ["D-01: n"]);
  });
});

// A review of the document, and the view panel open on it, in either order.
async function pendingDoc(order, docPath, text, extra = {}) {
  const r = await loaded({ [docPath]: text, [REQ1]: req("1", docPath), ...extra });
  if (order === "panel-first") {
    await openDoc(r.app, docPath);
    await r.plugin.openViewPanel();
    await settle();
    await r.plugin.handler({ request: REQ1 });
  } else {
    await r.plugin.handler({ request: REQ1 });
    await openDoc(r.app, docPath);
    await r.plugin.openViewPanel();
  }
  await settle();
  return r;
}
const decisionButtons = (app) => decisionCards(app).flatMap((c) => c.all().filter((e) => e.tag === "button" && (e.text === "Agree" || e.text === "Change")));
// Writes the note, then clicks Change.
const changeDecision = async (app, id, note) => {
  const card = decisionCard(app, id);
  typeInto(cardArea(card), note);
  await click(button(card, "Change"));
};
const CALLOUT = SPEC_FILES["SPEC-callout-decisions.md"];

// Adversarial where: the spec view shows a card for fewer or more decisions
// than the spec holds (callout ones missing, the fenced example added), the
// Problem and Desired Outcome come out reworded or swapped, a stale spec view
// stays under another document, or controls show with no review pending.
test("the panel draws a spec as its Problem, its Desired Outcome and one card per decision", async (t) => {
  await t.test("a spec with decisions in a callout: six cards in order, the human's text in each part", async () => {
    const { app, plugin } = await loaded({ [SP]: CALLOUT, "n.md": "---\ntype: lesson\n---\nx\n" });
    await openDoc(app, SP);
    await plugin.openViewPanel();
    await settle();
    assert.equal(viewEl(app).querySelectorAll(".compass-spec-view").length, 1);
    assert.deepEqual(decisionCards(app).map((c) => c.dataset.id), ["D-01", "D-02", "D-03", "D-04", "D-05", "D-06"]);
    assert.match(textOfEl(decisionCard(app, "D-04")), /Fourth ruling, nested one level deeper\./);
    assert.match(textOfEl(decisionCard(app, "D-02")), /Second ruling, tagged deferred\. continued on an indented line\./);
    assert.doesNotMatch(textOfEl(decisionCard(app, "D-03")), /\^d-03/, "the block id is not part of the ruling");
    const problem = textOfEl(viewEl(app).querySelector(".compass-spec-problem"));
    const outcome = textOfEl(viewEl(app).querySelector(".compass-spec-outcome"));
    assert.match(problem, /People lose track of rulings\./);
    assert.doesNotMatch(problem, /Every ruling is a card\./);
    assert.match(outcome, /Every ruling is a card\./);
    assert.doesNotMatch(outcome, /People lose track/);
    assert.equal(decisionButtons(app).length, 0, "no review pending, no controls");
    await openDoc(app, "n.md");
    assert.equal(viewEl(app).querySelectorAll(".compass-spec-view").length, 0, "no stale spec under a lesson");
    assert.equal(decisionCards(app).length, 0);
  });
  await t.test("SPEC-031 with plain bullets: two cards", async () => {
    const { app, plugin } = await loaded({ [SP]: SPEC_FILES["SPEC-031-working-in-compass-is-visual.md"] });
    await openDoc(app, SP);
    await plugin.openViewPanel();
    await settle();
    assert.deepEqual(decisionCards(app).map((c) => c.dataset.id), ["D-01", "D-02"]);
    assert.match(textOfEl(decisionCard(app, "D-02")), /Make sure we don't bloat the documents\./);
  });
  await t.test("a spec with no decisions and a spec with one unreadable bullet still draw their Problem", async () => {
    for (const [name, text, problem] of [
      ["none", "---\ntype: spec\n---\n## Problem\nNo rulings yet.\n\n## Desired Outcome\nSome.\n", /No rulings yet\./],
      ["malformed", SPEC_FILES["SPEC-malformed-decision.md"], /One decision is written without its colon\./],
    ]) {
      const { app, plugin } = await loaded({ [SP]: text });
      await openDoc(app, SP);
      await plugin.openViewPanel();
      await settle();
      assert.equal(viewEl(app).querySelectorAll(".compass-spec-view").length, 1, name);
      assert.match(textOfEl(viewEl(app).querySelector(".compass-spec-problem")), problem, name);
    }
  });
});

// Adversarial where: the cards take answers with no review pending, only in
// one arrival order, for a review of another file, or keep their controls
// after the review is answered.
test("each decision card takes Agree or Change only while a review of this spec is pending", async (t) => {
  for (const order of ["review-first", "panel-first"]) {
    await t.test(`${order}: six cards each with Agree, Change and a note; gone after the answer`, async () => {
      const { app } = await pendingDoc(order, SP, CALLOUT);
      assert.equal(decisionCards(app).length, 6);
      for (const card of decisionCards(app)) {
        assert.ok(button(card, "Agree") && button(card, "Change") && cardArea(card), `${card.dataset.id}: controls`);
      }
      await click(cardBtn(app, "1", "Approve"));
      await settle();
      assert.equal(decisionButtons(app).length, 0);
      assert.equal(decisionCards(app).length, 6, "the cards stay");
    });
  }
  await t.test("a review of another file leaves the spec's cards without controls", async () => {
    const { app, plugin } = await loaded({ [SP]: CALLOUT, "o.md": "---\ntype: lesson\n---\nx\n", [REQ1]: req("1", "o.md") });
    await plugin.handler({ request: REQ1 });
    await openDoc(app, SP);
    await plugin.openViewPanel();
    await settle();
    assert.equal(decisionCards(app).length, 6);
    assert.equal(decisionButtons(app).length, 0);
  });
});

// Adversarial where: Change answers never reach the verdict, replace the typed
// note, land in click order, survive only until a redraw, stay after a
// change of mind to Agree, an all-Agree spec adds text, or the line carries a
// carriage return.
test("Change answers join the review's note as D-NN lines in document order, and Agree adds nothing", async (t) => {
  await t.test("two Changes answered out of order join the typed note", async () => {
    const { app } = await pendingDoc("review-first", SP, CALLOUT);
    await changeDecision(app, "D-05", "split it");
    await click(button(decisionCard(app, "D-02"), "Agree"));
    await changeDecision(app, "D-01", "reword\nit");
    typeInto(notesIn(cardFor(app, "1")), "overall");
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    assert.equal(verdictNotes(app), "overall\nD-01: reword it\nD-05: split it");
  });
  await t.test("Agree on every card adds no line, even with a note typed in it", async () => {
    const { app } = await pendingDoc("review-first", SP, CALLOUT);
    typeInto(cardArea(decisionCard(app, "D-03")), "a thought");
    for (const card of decisionCards(app)) await click(button(card, "Agree"));
    typeInto(notesIn(cardFor(app, "1")), "overall");
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    assert.equal(verdictNotes(app), "overall");
  });
  await t.test("a Change turned into Agree adds no line", async () => {
    const { app } = await pendingDoc("review-first", SP, CALLOUT);
    await changeDecision(app, "D-01", "reword");
    await click(button(decisionCard(app, "D-01"), "Agree"));
    typeInto(notesIn(cardFor(app, "1")), "overall");
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    assert.equal(verdictNotes(app), "overall");
  });
  await t.test("a Change survives the panel redrawing, and a CRLF spec sends no carriage return", async () => {
    const { app } = await pendingDoc("panel-first", SP, CALLOUT.replace(/\n/g, "\r\n"));
    await changeDecision(app, "D-04", "keep it");
    app.wsListeners["layout-change"]();
    app.wsListeners["file-open"](mdFile(SP));
    await settle();
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    assert.equal(verdictNotes(app), "D-04: keep it");
  });
  await t.test("an answered decision that left the spec is still sent", async () => {
    const { app } = await pendingDoc("review-first", SP, CALLOUT);
    await changeDecision(app, "D-06", "drop it");
    app.store.set(SP, CALLOUT.replace("- **D-06:** Sixth ruling, in a discretion group.\n", ""));
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    assert.equal(verdictNotes(app), "D-06: drop it");
  });
  await t.test("in a three-file review the lines join the spec's own note", async () => {
    const files = [{ file: "a.md", why: "w" }, { file: "s.md", why: "w" }, { file: "b.md", why: "w" }];
    const { app, plugin } = await loaded({
      "a.md": "---\ntype: lesson\n---\nx\n",
      "s.md": CALLOUT,
      "b.md": "---\ntype: lesson\n---\ny\n",
      [REQ1]: JSON.stringify({ id: "1", file: "a.md", title: "T", return: true, files }),
    });
    await plugin.handler({ request: REQ1 });
    await openDoc(app, "s.md");
    await plugin.openViewPanel();
    await settle();
    await changeDecision(app, "D-02", "why deferred");
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    const sent = verdictOf(app, "tmp/review/1.verdict.json");
    assert.deepEqual(sent.files.map((f) => f.note), [undefined, "D-02: why deferred", undefined]);
    assert.equal(sent.notes, "s: D-02: why deferred");
  });
});

// Adversarial where: a Change with a blank note is accepted (the plan board's
// "(no note)" line), is counted as feedback so Needs changes sends an empty
// complaint, leaves the card marked as changed, or gives the human no sign why
// nothing happened; or a refusal sticks so a note typed afterwards cannot be
// sent.
test("a Change with an empty note is refused and sends nothing", async (t) => {
  for (const [name, blank] of [["empty", ""], ["spaces", "   "], ["tabs and a line break", "\t\n "]]) {
    await t.test(`${name} note`, async () => {
      const { app } = await pendingDoc("review-first", SP, CALLOUT);
      const card = decisionCard(app, "D-01");
      typeInto(cardArea(card), blank);
      await click(button(card, "Change"));
      assert.doesNotMatch(decisionCard(app, "D-01").cls, /is-change/);
      const hint = decisionCard(app, "D-01").querySelector(".compass-decision-need-note");
      assert.ok(hint && hint.text.trim() !== "", "the card says a note is needed");
      assert.equal(decisionCard(app, "D-02").querySelector(".compass-decision-need-note"), null, "another card shows no hint");
      assert.equal(cardBtn(app, "1", "Needs changes").disabled, true, "a refused Change is not feedback");
    });
  }
  await t.test("after the refusal a note and a second Change are accepted", async () => {
    const { app } = await pendingDoc("review-first", SP, CALLOUT);
    await click(button(decisionCard(app, "D-01"), "Change"));
    await changeDecision(app, "D-01", "now with a note");
    assert.match(decisionCard(app, "D-01").cls, /is-change/);
    assert.equal(decisionCard(app, "D-01").querySelector(".compass-decision-need-note"), null);
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    assert.equal(verdictNotes(app), "D-01: now with a note");
  });
  await t.test("a Change whose note is then cleared sends no line and no (no note)", async () => {
    const { app } = await pendingDoc("review-first", SP, CALLOUT);
    await changeDecision(app, "D-03", "temporary");
    await changeDecision(app, "D-02", "kept");
    typeInto(cardArea(decisionCard(app, "D-03")), "");
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    assert.equal(verdictNotes(app), "D-02: kept");
  });
  await t.test("a one-character note is accepted", async () => {
    const { app } = await pendingDoc("review-first", SP, CALLOUT);
    await changeDecision(app, "D-01", "x");
    assert.match(decisionCard(app, "D-01").cls, /is-change/);
  });
});

const confBtn = (app, conf) => viewEl(app).querySelectorAll("button.compass-conf-filter").find((b) => b.dataset.conf === conf);
const findingRows = (app) => viewEl(app).querySelectorAll(".compass-finding-row");
const findingNs = (app) => findingRows(app).map((r) => r.dataset.n);
const barOf = (app, section) => viewEl(app).querySelectorAll(".compass-section-bar").find((b) => b.dataset.section === section);
const SMALL_RESEARCH = [
  "---", "type: research", "title: R", "---", "# R", "", "## Findings", "",
  "### A. First (axis 1)", "",
  "| # | Finding | Conf. | Grade | Evidence |", "|---|---|---|---|---|",
  "| 1 | First | high | high | ev-1 |",
  "| 2 | Second | medium | low | ev-2 |",
  "| 3 | Third | high | high | ev-3 |", "",
  "### B. Second (axis 2)", "",
  "| # | Finding | Conf. | Grade | Evidence |", "|---|---|---|---|---|",
  "| 4 | Fourth | low | low | ev-4 |",
  "| 5 | Fifth | high (behavior), low (maturity) | high | ev-5 |", "",
].join("\n");

// Adversarial where: the research view's bars count another thing than the
// findings of each section, the confidence filter hides the wrong rows or
// strands the human with no way back, a filter changes the bars, a row opens
// the document at the wrong line (off by one for Obsidian's 0-based lines),
// or the row leaves the finding's evidence out.
test("the panel draws research as bars per section, confidence filters and rows that open the finding's line", async (t) => {
  const open = async () => {
    const { app, plugin } = await loaded({ [RP]: SMALL_RESEARCH });
    await openDoc(app, RP);
    await plugin.openViewPanel();
    await settle();
    return app;
  };
  await t.test("bars: one per section with its counts; rows: one per finding with its evidence", async () => {
    const app = await open();
    assert.equal(viewEl(app).querySelectorAll(".compass-research-view").length, 1);
    const bars = viewEl(app).querySelectorAll(".compass-section-bar");
    assert.deepEqual(bars.map((b) => b.dataset.section), ["A. First (axis 1)", "B. Second (axis 2)"]);
    const a = barOf(app, "A. First (axis 1)").dataset;
    assert.deepEqual([a.total, a.high, a.medium, a.low], ["3", "2", "1", "0"]);
    const b = barOf(app, "B. Second (axis 2)").dataset;
    assert.deepEqual([b.total, b.high, b.medium, b.low], ["2", "1", "0", "1"], "a mixed confidence counts once, as its leading level");
    assert.deepEqual(findingNs(app), ["1", "2", "3", "4", "5"]);
    assert.match(textOfEl(findingRows(app)[3]), /ev-4/);
    assert.deepEqual(viewEl(app).querySelectorAll("button.compass-conf-filter").map((x) => x.dataset.conf), ["high", "medium", "low"]);
    for (const c of ["high", "medium", "low"]) assert.match(confBtn(app, c).cls, /is-on/, `${c} starts on`);
  });
  await t.test("each filter button hides and restores its confidence; the bars do not move", async () => {
    const app = await open();
    await click(confBtn(app, "high"));
    assert.deepEqual(findingNs(app), ["2", "4"]);
    assert.doesNotMatch(confBtn(app, "high").cls, /is-on/);
    assert.equal(barOf(app, "A. First (axis 1)").dataset.total, "3", "bars count the document, not the shown rows");
    await click(confBtn(app, "low"));
    assert.deepEqual(findingNs(app), ["2"]);
    await click(confBtn(app, "medium"));
    assert.deepEqual(findingNs(app), [], "all three off shows no row");
    await click(confBtn(app, "high"));
    await click(confBtn(app, "medium"));
    await click(confBtn(app, "low"));
    assert.deepEqual(findingNs(app), ["1", "2", "3", "4", "5"], "all back on shows every row");
  });
  await t.test("a click on a row opens the document at the finding's line, 0-based", async () => {
    const app = await open();
    const lines = SMALL_RESEARCH.split("\n");
    for (const n of ["1", "4", "5"]) {
      const row = findingRows(app).find((r) => r.dataset.n === n);
      await clickOn(row);
      await settle();
      const last = app.opened[app.opened.length - 1];
      assert.equal(last.path, RP, `finding ${n}: the research document`);
      assert.equal(last.state && last.state.eState && last.state.eState.line, lines.findIndex((l) => l.startsWith(`| ${n} |`)), `finding ${n}: 0-based line`);
    }
  });
  await t.test("the evidence document: ten bars whose totals match, and rows to filter", async () => {
    const { app, plugin } = await loaded({ [RP]: RESEARCH_TEXT });
    await openDoc(app, RP);
    await plugin.openViewPanel();
    await settle();
    const bars = viewEl(app).querySelectorAll(".compass-section-bar");
    assert.deepEqual(bars.map((b) => [b.dataset.section, b.dataset.total, b.dataset.high, b.dataset.medium, b.dataset.low]),
      RESEARCH_EXPECT.sections.map((s) => [s.name, String(s.total), String(s.high), String(s.medium), String(s.low)]));
    assert.ok(findingRows(app).length > 0);
  });
});

// Adversarial where: browsing a spec or research document writes into the
// vault (a card click or an answer saves the file), even a rewrite that leaves
// the bytes the same.
test("drawing spec and research cards, answering decisions and clicking findings write nothing into the vault", async () => {
  const { app, plugin } = await loaded({ [SP]: CALLOUT, [RP]: SMALL_RESEARCH, [REQ1]: req("1", SP) });
  await plugin.handler({ request: REQ1 });
  const before = Object.fromEntries(app.store);
  const writes = [];
  const write = app.vault.adapter.write;
  app.vault.adapter.write = async (p, d) => { writes.push(p); return write.call(app.vault.adapter, p, d); };
  await openDoc(app, SP);
  await plugin.openViewPanel();
  await settle();
  await click(button(decisionCard(app, "D-01"), "Agree"));
  await changeDecision(app, "D-02", "why");
  await openDoc(app, RP);
  await clickOn(findingRows(app)[0]);
  await click(confBtn(app, "high"));
  await settle();
  assert.deepEqual(writes, []);
  assert.deepEqual(Object.fromEntries(app.store), before);
});

// ---- post-build probes: the spec and research views against real text ----

const verdictOfId = (app, id) => verdictOf(app, `tmp/review/${id}.verdict.json`);
const REQ2 = "tmp/review/2.request.json";
const SPEC_B = ".compass/specs/SPEC-901-fixture-b.md";
const TAGS_ALLOWED = new Set(["div", "span", "code", "strong", "ul", "li", "pre", "h4", "button", "textarea", "table", "thead", "tbody", "tr", "th", "td", "a", "view-container", "svg", "path", "g", "circle", "line", "rect", "text"]);

// Adversarial where: one decision answer lands in the verdict of a different
// review because two specs number their decisions alike (D-01 in both), or
// because the answers hang on the document instead of on the review that lists it.
test("a Change on D-01 of one spec never reaches the review of another spec that also has a D-01", async (t) => {
  await t.test("two pending reviews, two specs: the answer goes only to its own review", async () => {
    const { app, plugin } = await loaded({ [SP]: CALLOUT, [SPEC_B]: CALLOUT, [REQ1]: req("1", SP), [REQ2]: req("2", SPEC_B) });
    await plugin.handler({ request: REQ1 });
    await plugin.handler({ request: REQ2 });
    await openDoc(app, SP);
    await plugin.openViewPanel();
    await settle();
    await changeDecision(app, "D-01", "only for spec A");
    await openDoc(app, SPEC_B);
    assert.equal(decisionCards(app).length, 6);
    assert.doesNotMatch(cardArea(decisionCard(app, "D-01")).value, /only for spec A/, "spec B's card starts blank");
    await changeDecision(app, "D-01", "only for spec B");
    await click(cardBtn(app, "2", "Needs changes"));
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    assert.equal(verdictOfId(app, "2").notes, "D-01: only for spec B");
    assert.equal(verdictOfId(app, "1").notes, "D-01: only for spec A");
  });
  await t.test("one review listing two specs: each D-01 answer stays with its own file", async () => {
    const both = req("1", SP, { files: [{ file: SP, why: "" }, { file: SPEC_B, why: "" }] });
    const { app, plugin } = await loaded({ [SP]: CALLOUT, [SPEC_B]: CALLOUT, [REQ1]: both });
    await plugin.handler({ request: REQ1 });
    await openDoc(app, SP);
    await plugin.openViewPanel();
    await settle();
    await changeDecision(app, "D-01", "first spec");
    await openDoc(app, SPEC_B);
    assert.equal(cardArea(decisionCard(app, "D-01")).value, "", "the second spec's D-01 starts blank");
    await click(button(decisionCard(app, "D-01"), "Agree"));
    await openDoc(app, SP);
    assert.match(decisionCard(app, "D-01").cls, /is-change/, "the first spec keeps its Change");
    await click(cardBtn(app, "1", "Needs changes"));
    await settle();
    const sent = verdictOfId(app, "1");
    assert.deepEqual(sent.files.map((f) => f.note), ["D-01: first spec", undefined], "only the first spec's file carries the line");
  });
});

// Adversarial where: text a spec or research document holds is parsed as
// markup, so an element or an attribute appears that the plugin never made
// (an img with onerror, a script, an anchor with a javascript: target), or the
// literal characters are lost.
test("markup in a spec's text and a research row is drawn as literal text, never as elements", async (t) => {
  const evil = "<img src=x onerror=\"alert(1)\"> <script>alert(2)</script> <a href=\"javascript:alert(3)\">x</a>";
  const quoted = evil.replace(/"/g, "'");
  const spec = [
    "---", "type: spec", `title: "${quoted}"`, `status: "${quoted}"`, "---", "# S", "",
    "## Problem", evil, "", `- bullet ${evil}`, "", "## Desired Outcome", `**${evil}** and \`${evil}\``, "",
    "## Decisions", "", `- **D-01 [${evil.replace(/[\[\]]/g, "")}]:** ${evil}`, "",
  ].join("\n");
  const research = [
    "---", "type: research", "---", "# R", "", `## ${evil}`, "",
    "| # | Finding | Conf. | Grade | Evidence |", "|---|---|---|---|---|",
    `| 1 | ${evil} | ${evil} | ${evil} | ${evil} |`, "",
  ].join("\n");
  for (const [name, p, text] of [["spec", SP, spec], ["research", RP, research]]) {
    await t.test(name, async () => {
      const { app, plugin } = await loaded({ [p]: text, [REQ1]: req("1", p) });
      await plugin.handler({ request: REQ1 });
      await openDoc(app, p);
      await plugin.openViewPanel();
      await settle();
      const els = viewEl(app).all();
      for (const tag of new Set(els.map((e) => e.tag))) assert.ok(TAGS_ALLOWED.has(tag), `unexpected <${tag}> element`);
      for (const e of els) {
        assert.doesNotMatch(String(e.href || ""), /javascript:/i, `href on <${e.tag}>`);
        assert.ok(!Object.keys(e.attrs).some((k) => /^on/i.test(k)), `an on* attribute on <${e.tag}>`);
        assert.ok(!("innerHTML" in e), "innerHTML was assigned");
      }
      assert.match(textOfEl(viewEl(app)), /<img src=x onerror="alert\(1\)">/, "the angle brackets are drawn literally");
    });
  }
});

// Adversarial where: a line in the Problem that merely contains three
// backticks (an inline span, or a fence word after text) opens a code block and
// swallows the rest of the section, so the human's following paragraphs vanish.
test("a Problem line that starts with an inline triple-backtick span does not swallow the paragraphs after it", async () => {
  const text = ["---", "type: spec", "---", "# S", "", "## Problem", "```inline``` is how a span starts here.", "",
    "The second paragraph must stay visible.", "", "## Desired Outcome", "Done.", ""].join("\n");
  const { app, plugin } = await loaded({ [SP]: text });
  await openDoc(app, SP);
  await plugin.openViewPanel();
  await settle();
  const problem = viewEl(app).querySelector(".compass-spec-problem");
  const shown = problem.querySelectorAll(".compass-prose-p").map((p) => textOfEl(p)).join("|");
  assert.match(shown, /The second paragraph must stay visible\./);
});

// Adversarial where: a spec with no Decisions heading, or only a prose mention
// of a decision id, throws, hides its Problem, or reads differently from the
// CLI (none-present for no mention, could-not-parse for a bare D-NN token).
test("a spec without a Decisions heading draws its words and says whether the decisions could be read", async (t) => {
  await t.test("no heading, no mention: records no decisions", async () => {
    const text = "---\ntype: spec\n---\n# S\n\n## Problem\nWords.\n\n## Desired Outcome\nMore.\n";
    assert.equal(CompassReview.parseSpec(text).decisionState, "none-present");
    const { app, plugin } = await loaded({ [SP]: text });
    await openDoc(app, SP);
    await plugin.openViewPanel();
    await settle();
    assert.equal(decisionCards(app).length, 0);
    assert.match(textOfEl(viewEl(app)), /records no decisions/);
    assert.match(textOfEl(viewEl(app)), /Words\./);
  });
  await t.test("no heading but a D-NN token in the prose: could not read, says so", async () => {
    const text = "---\ntype: spec\n---\n# S\n\n## Problem\nSee D-03 in the old spec.\n";
    assert.equal(CompassReview.parseSpec(text).decisionState, "could-not-parse");
    const { app, plugin } = await loaded({ [SP]: text });
    await openDoc(app, SP);
    await plugin.openViewPanel();
    await settle();
    assert.match(textOfEl(viewEl(app)), /could not read every decision/);
  });
  await t.test("a document with no Problem and no Desired Outcome headings says so for both", async () => {
    const { app, plugin } = await loaded({ [SP]: "---\ntype: spec\n---\n# S\n\nJust text.\n" });
    await openDoc(app, SP);
    await plugin.openViewPanel();
    await settle();
    assert.match(textOfEl(viewEl(app)), /no Problem section/);
    assert.match(textOfEl(viewEl(app)), /no Desired Outcome section/);
  });
});

// Adversarial where: research with no findings table (or findings only inside a
// fence, or a table lacking a Finding column) throws or draws phantom bars and
// rows; a `\|` in a cell splits the finding in two; an unmatched backtick in a
// cell swallows the cells after it.
test("a research document with no readable findings table draws an empty view, and cells with pipes or a lone backtick keep their columns", async (t) => {
  const head = "---\ntype: research\n---\n# R\n\n## Findings\n\n";
  const table = (rows) => ["| # | Finding | Conf. | Grade | Evidence |", "|---|---|---|---|---|", ...rows, ""].join("\n");
  const rows = [
    ["prose only", head + "Nothing tabulated yet.\n"],
    ["table in a fence", head + "```\n" + table(["| 1 | Hidden | high | high | e |"]) + "```\n"],
    ["table without a Finding column", head + "| # | Claim | Conf. |\n|---|---|---|\n| 1 | X | high |\n"],
    ["rows without a numeric first cell", head + table(["| a | Word | high | high | e |"])],
  ];
  for (const [name, text] of rows) {
    await t.test(name, async () => {
      assert.deepEqual(CompassReview.parseResearchFindings(text), []);
      const { app, plugin } = await loaded({ [RP]: text });
      await openDoc(app, RP);
      await plugin.openViewPanel();
      await settle();
      assert.equal(viewEl(app).querySelectorAll(".compass-research-view").length, 1);
      assert.equal(findingRows(app).length, 0);
      assert.equal(viewEl(app).querySelectorAll(".compass-section-bar").length, 0);
    });
  }
  await t.test("an escaped pipe and a pipe in a code span keep the finding in one cell", () => {
    const f = CompassReview.parseResearchFindings(head + table(["| 1 | a \\| b and `x|y` | medium | low | ev |"]));
    assert.equal(f.length, 1);
    assert.equal(f[0].conf, "medium");
    assert.equal(f[0].evidence, "ev");
  });
  await t.test("a backtick left open in the finding cell does not eat the confidence", () => {
    const f = CompassReview.parseResearchFindings(head + table(["| 1 | uses the ` key | high | high | ev |"]));
    assert.equal(f.length, 1);
    assert.equal(f[0].conf, "high");
  });
});

// Adversarial where: showing a spec or research document leaves the plan board
// broken: a plan opened after them keeps their cards, draws no board, or the
// board loses its rows after a round trip through the other two views.
test("the plan board still draws after the view has shown a spec and a research document", async () => {
  const { app, plugin } = await loaded({ [P24]: PLAN_24, [SP]: CALLOUT, [RP]: SMALL_RESEARCH });
  await openDoc(app, P24);
  await plugin.openViewPanel();
  await settle();
  const rowsBefore = taskRows(app).map((r) => r.dataset.id || textOfEl(r));
  assert.ok(rowsBefore.length > 0);
  await openDoc(app, SP);
  await openDoc(app, RP);
  await openDoc(app, P24);
  assert.deepEqual(taskRows(app).map((r) => r.dataset.id || textOfEl(r)), rowsBefore);
  assert.equal(viewEl(app).querySelectorAll(".compass-spec-view").length, 0);
  assert.equal(viewEl(app).querySelectorAll(".compass-research-view").length, 0);
});

// ---- what changed since a review ----
//
// When the review of a document was sent before, `compass review` saves
// `git diff <sha> -- <file>` for each listed file as `<id>.changes.diff` beside
// the request. The view panel reads it for the open file and draws the changes.
//
//   CompassReview.changesPathFor(requestPath) -> path of the diff beside a request
//   CompassReview.parseChanges(diffText, docText, docPath) -> groups
//       diffText: git's unified diff, one or more files (paths from the
//       repository top); docText: the document as it is now; docPath: its path in
//       the Obsidian vault, which equals the diff's path or ends it on a "/"
//       boundary. Only that file's hunks are read.
//       groups: [{ heading, line, hunks: [{ line, rows }] }] in document order,
//       one group per heading line (heading: its title, line: its 1-based
//       line; both null for changes above the first heading), hunks in diff order,
//       hunk.line the first changed line in the new text (1-based), rows
//       [{ kind: "ctx" | "del" | "add", parts: [{ text, changed }] }] with
//       the line's text split into parts whose texts join back to the line.
//
// DOM in the view panel for a document whose pending review has the diff:
//   .compass-changes          the section, one per view
//   .compass-changes-group    one per group, its .compass-changes-heading
//                             holding the heading title
//   .compass-change-hunk      one per hunk, with a .compass-change-open control
//                             that opens the document at hunk.line
//   .compass-change-row       one per row, class is-ctx | is-del | is-add,
//                             .compass-change-word spans holding the changed parts

// A unified diff of `rel` between two line arrays of equal length, git's default
// three lines of context, hunks merged where their context touches.
function replDiff(rel, oldLines, newLines, tab = "") {
  const spans = [];
  oldLines.forEach((l, i) => {
    if (l === newLines[i]) return;
    const lo = Math.max(0, i - 3);
    const hi = Math.min(oldLines.length - 1, i + 3);
    const last = spans[spans.length - 1];
    if (last && lo <= last.hi + 1) last.hi = hi; else spans.push({ lo, hi });
  });
  const out = [`diff --git a/${rel} b/${rel}`, "index 1111111..2222222 100644", `--- a/${rel}${tab}`, `+++ b/${rel}${tab}`];
  for (const { lo, hi } of spans) {
    out.push(`@@ -${lo + 1},${hi - lo + 1} +${lo + 1},${hi - lo + 1} @@`);
    for (let i = lo; i <= hi; i++) {
      if (oldLines[i] === newLines[i]) out.push(" " + oldLines[i]);
      else out.push("-" + oldLines[i], "+" + newLines[i]);
    }
  }
  return out.join("\n") + "\n";
}
const fileHead = (rel) => [`diff --git a/${rel} b/${rel}`, "index 1111111..2222222 100644", `--- a/${rel}`, `+++ b/${rel}`];
const joined = (lines) => lines.join("\n") + "\n";
const changeSummary = (groups) => groups.map((g) => [g.heading, g.line, g.hunks.length]);
const rowText = (r) => r.parts.map((p) => p.text).join("");
const marked = (r) => r.parts.filter((p) => p.changed).map((p) => p.text);
const rowsOf = (groups) => groups.flatMap((g) => g.hunks.flatMap((h) => h.rows));
const SPEC_REL = ".compass/specs/a.md";

// Adversarial where: a hunk is filed under the heading nearest its start or its
// end instead of the one above its first changed line (git's context lines
// reach into the next section and back into the previous one); a deletion
// directly before a heading moves under that heading; a heading-looking line in
// a code fence, or a heading the change itself adds, is mishandled; changes
// above the first heading get a phantom group; two headings with one title merge,
// or two hunks under one heading split; CRLF text leaves "\r" in titles and rows.
test("the parser groups each hunk under the heading above its first changed line", async (t) => {
  const filler = (n) => Array.from({ length: n }, (_, i) => `f${i + 1}`);
  const crlf = (s) => s.replace(/\n/g, "\r\n");
  const sameTitleOld = ["## Notes", "n1", ...filler(10), "## Notes", "n2", "tail"];
  const sameTitleNew = sameTitleOld.map((l) => (l === "n1" || l === "n2" ? l + " new" : l));
  const oneHeadOld = ["## N", "x1", ...filler(12), "x2"];
  const oneHeadNew = oneHeadOld.map((l) => (l === "x1" || l === "x2" ? l + " new" : l));
  const rows = [
    ["a heading inside the trailing context belongs to the next section",
      replDiff(SPEC_REL, ["# T", "## A", "a1", "a2 old", "## B", "b1"], ["# T", "## A", "a1", "a2", "## B", "b1"]),
      joined(["# T", "## A", "a1", "a2", "## B", "b1"]), [["A", 2, 1]]],
    ["a heading inside the leading context is above the change",
      replDiff(SPEC_REL, ["# T", "intro", "## B", "b1", "b2 old", "b3"], ["# T", "intro", "## B", "b1", "b2", "b3"]),
      joined(["# T", "intro", "## B", "b1", "b2", "b3"]), [["B", 3, 1]]],
    ["a deletion right before a heading sits under the heading it was deleted from",
      joined([...fileHead(SPEC_REL), "@@ -1,6 +1,5 @@", " # T", " ## A", " keep", "-gone", " ## B", " text"]),
      joined(["# T", "## A", "keep", "## B", "text"]), [["A", 2, 1]]],
    ["a change above the first heading has no heading",
      replDiff(SPEC_REL, ["---", "type: spec", "---", "intro old", "## A", "x"], ["---", "type: spec", "---", "intro", "## A", "x"]),
      joined(["---", "type: spec", "---", "intro", "## A", "x"]), [[null, null, 1]]],
    ["a heading-like line in a code fence is not a heading",
      replDiff(SPEC_REL, ["## A", "a1", "```", "# not a heading", "old code", "```"], ["## A", "a1", "```", "# not a heading", "code", "```"]),
      joined(["## A", "a1", "```", "# not a heading", "code", "```"]), [["A", 1, 1]]],
    ["an added heading line groups under itself",
      joined([...fileHead(SPEC_REL), "@@ -1,2 +1,4 @@", " ## A", " a1", "+## New", "+n1"]),
      joined(["## A", "a1", "## New", "n1"]), [["New", 3, 1]]],
    ["two headings with one title are two groups", replDiff(SPEC_REL, sameTitleOld, sameTitleNew),
      joined(sameTitleNew), [["Notes", 1, 1], ["Notes", 13, 1]]],
    ["two hunks under one heading are one group", replDiff(SPEC_REL, oneHeadOld, oneHeadNew), joined(oneHeadNew), [["N", 1, 2]]],
    ["CRLF text leaves no carriage return in the title", crlf(replDiff(SPEC_REL, ["## A", "a1", "a2 old"], ["## A", "a1", "a2"])),
      crlf(joined(["## A", "a1", "a2"])), [["A", 1, 1]]],
  ];
  for (const [name, diff, doc, expected] of rows) {
    await t.test(name, () => {
      const groups = CompassReview.parseChanges(diff, doc, SPEC_REL);
      assert.deepEqual(changeSummary(groups), expected);
      for (const r of rowsOf(groups)) assert.ok(!/[\r\n]/.test(rowText(r)), `row text holds a line break: ${JSON.stringify(rowText(r))}`);
    });
  }
});

// Adversarial where: the changed words of a replaced line are the whole line
// (or none), the unchanged words around them are marked, a pipe or a punctuation
// mark glues two words so the neighbour is marked too, or a context row is marked.
test("the parser marks the changed words of a replaced line on both sides", async (t) => {
  const rows = [
    ["one word", ["# T", "The quick fox jumps.", "x"], ["# T", "The slow fox jumps.", "x"], ["quick"], ["slow"]],
    ["two separate words", ["# T", "red car stops", "x"], ["# T", "blue car starts", "x"], ["red", "stops"], ["blue", "starts"]],
    ["a table cell between pipes", ["# T", "| a | b |", "x"], ["# T", "| a | c |", "x"], ["b"], ["c"]],
  ];
  for (const [name, oldLines, newLines, del, add] of rows) {
    await t.test(name, () => {
      const groups = CompassReview.parseChanges(replDiff(SPEC_REL, oldLines, newLines), joined(newLines), SPEC_REL);
      const all = rowsOf(groups);
      assert.deepEqual(all.map((r) => r.kind), ["ctx", "del", "add", "ctx"]);
      assert.deepEqual(all.map(rowText), [oldLines[0], oldLines[1], newLines[1], oldLines[2]]);
      assert.deepEqual(marked(all[1]), del);
      assert.deepEqual(marked(all[2]), add);
      assert.deepEqual(marked(all[0]).concat(marked(all[3])), []);
    });
  }
});

// Adversarial where: the diff of a file is looked for by exact path (the vault
// sits below the repository top, so a vault path is shorter than git's), by a
// plain suffix that also matches "myspecs/a.md" for "specs/a.md", or a name with
// a space (git ends the ---/+++ lines of such a name with a tab) finds nothing;
// the hunks of another file in the same diff are read as this file's.
test("the parser reads only the hunks of the file whose path ends the diff's path on a folder boundary", async (t) => {
  const aOld = ["## A", "a1 old"];
  const aNew = ["## A", "a1"];
  const docA = joined(aNew);
  const bOld = ["b1", "b2"];
  const bNew = ["b1", "b2 new"];
  const cases = [
    ["a vault path shorter than the repository path", replDiff(".compass/specs/b.md", bOld, bNew) + replDiff(SPEC_REL, aOld, aNew), "specs/a.md", ["a1 old", "a1"]],
    ["the full path", replDiff(SPEC_REL, aOld, aNew), SPEC_REL, ["a1 old", "a1"]],
    ["a name with a space and tab-ended header lines", replDiff(".compass/specs/my doc.md", aOld, aNew, "\t"), "specs/my doc.md", ["a1 old", "a1"]],
    ["a file the diff does not hold", replDiff(".compass/specs/b.md", bOld, bNew), "specs/a.md", []],
    ["a longer folder name that ends the same", replDiff(".compass/myspecs/a.md", aOld, aNew), "specs/a.md", []],
  ];
  for (const [name, diff, docPath, texts] of cases) {
    await t.test(name, () => {
      const groups = CompassReview.parseChanges(diff, docA, docPath);
      assert.deepEqual(rowsOf(groups).filter((r) => r.kind !== "ctx").map(rowText), texts);
    });
  }
  await t.test("the diff path beside a request", () => {
    assert.equal(CompassReview.changesPathFor("tmp/review/1.request.json"), "tmp/review/1.changes.diff");
    assert.equal(CompassReview.changesPathFor(".compass/tmp/review/20261028T010101-ab12cd.request.json"), ".compass/tmp/review/20261028T010101-ab12cd.changes.diff");
  });
});

// Adversarial where: a removed line "-- y" prints as "--- y" and an added
// line "++ x" as "+++ x", which a parser reads as file headers, so the hunk
// ends early, a file starts, or the rows vanish; git's "\ No newline at end of
// file" marker becomes a row.
test("the parser keeps lines that look like file headers and skips the no-newline marker", () => {
  const diff = replDiff(SPEC_REL, ["## A", "-- y", "z"], ["## A", "++ x", "z"]) + "\\ No newline at end of file\n";
  assert.ok(diff.includes("\n--- y\n") && diff.includes("\n+++ x\n"), "fixture error: the lookalike lines are missing");
  const groups = CompassReview.parseChanges(diff, joined(["## A", "++ x", "z"]), SPEC_REL);
  assert.deepEqual(changeSummary(groups), [["A", 1, 1]]);
  const all = rowsOf(groups);
  assert.deepEqual(all.map((r) => r.kind), ["ctx", "del", "add", "ctx"]);
  assert.deepEqual(all.map(rowText), ["## A", "-- y", "++ x", "z"]);
});

// ---- the changes in the view panel ----

const SPEC_CHANGED_OLD = [
  "---", "type: spec", "title: S", "---", "# S", "", "## Problem", "", "The quick fox jumps.", "", "## Desired Outcome", "",
  "Line one", "Line two", "Line three", "", "## Notes", "", "A note.",
];
const SPEC_CHANGED_NEW = SPEC_CHANGED_OLD.map((l) => (l === "The quick fox jumps." ? "The slow fox jumps." : l === "A note." ? "A memo." : l));
const SPEC_A = "specs/a.md";
const REVIEW_DIR = "tmp/review";
const reviewFiles = (id, main, extra = {}) => ({ [`${REVIEW_DIR}/${id}.request.json`]: req(id, main, extra) });
const sectionsIn = (app) => viewEl(app).querySelectorAll(".compass-changes");
const groupEls = (app) => viewEl(app).querySelectorAll(".compass-changes-group");
const headingOfGroup = (g) => textOfEl(g.querySelector(".compass-changes-heading")).trim();
const wordsIn = (el, kind) => el.querySelectorAll(".compass-change-row").filter((r) => r.cls.split(" ").includes(kind))
  .flatMap((r) => r.querySelectorAll(".compass-change-word").map((w) => w.text));
async function viewWith(files, open) {
  const r = await loaded(files);
  await openDoc(r.app, open);
  await r.plugin.openViewPanel();
  await settle();
  return r;
}

// Adversarial where: the saved diff is never read, the changes are listed flat
// instead of under the heading each sits in (the hunk's leading context holds
// the title above and its trailing context the title below), the changed words
// are not marked or the whole line is, a document vault-relative to a shorter
// path than git's is not matched, or a click opens the hunk's first context line
// or the line 1-based instead of the first changed line, 0-based.
test("a spec with a pending review and a saved diff shows its changes under their headings, with the changed words marked, and a click opens the line", async () => {
  const diff = replDiff(SPEC_REL, SPEC_CHANGED_OLD, SPEC_CHANGED_NEW);
  const { app } = await viewWith({
    [SPEC_A]: joined(SPEC_CHANGED_NEW), ...reviewFiles("1", SPEC_A), [`${REVIEW_DIR}/1.changes.diff`]: diff,
  }, SPEC_A);
  assert.equal(sectionsIn(app).length, 1);
  const groups = groupEls(app);
  assert.deepEqual(groups.map(headingOfGroup), ["Problem", "Notes"]);
  assert.deepEqual([wordsIn(groups[0], "is-del"), wordsIn(groups[0], "is-add")], [["quick"], ["slow"]]);
  assert.deepEqual([wordsIn(groups[1], "is-del"), wordsIn(groups[1], "is-add")], [["note"], ["memo"]]);
  assert.equal(groups.every((g) => g.querySelectorAll(".compass-change-hunk").length === 1), true);
  for (const [group, line] of [[groups[0], 9], [groups[1], 19]]) {
    const before = app.opened.length;
    await clickOn(group.querySelector(".compass-change-hunk").querySelector(".compass-change-open"));
    await settle();
    assert.equal(app.opened.length, before + 1);
    const last = app.opened[app.opened.length - 1];
    assert.equal(last.path, SPEC_A);
    assert.equal(last.state && last.state.eState && last.state.eState.line, line - 1);
  }
});

// Adversarial where: the section appears with no saved diff, outlives the answer
// to its review, or fills with the changes of another file of a several-file
// review.
test("no changes are shown without a saved diff, after the review is answered, or for a file the diff does not hold", async (t) => {
  const text = joined(SPEC_CHANGED_NEW);
  const diff = replDiff(SPEC_REL, SPEC_CHANGED_OLD, SPEC_CHANGED_NEW);
  const rows = [
    ["no diff file", { [SPEC_A]: text, ...reviewFiles("1", SPEC_A) }, true],
    ["a verdict already written", { [SPEC_A]: text, ...reviewFiles("1", SPEC_A), [`${REVIEW_DIR}/1.changes.diff`]: diff,
      [`${REVIEW_DIR}/1.verdict.json`]: JSON.stringify({ id: "1", file: SPEC_A, verdict: "approved", notes: "", at: "t" }) }, true],
    ["a diff of the other file in a two-file review", { [SPEC_A]: text, "specs/b.md": "---\ntype: spec\n---\n# B\n",
      ...reviewFiles("1", "specs/b.md", { files: [{ file: "specs/b.md", why: null }, { file: SPEC_A, why: null }] }),
      [`${REVIEW_DIR}/1.changes.diff`]: replDiff(".compass/specs/b.md", ["b1", "b2"], ["b1", "b2 new"]) }, false],
  ];
  for (const [name, files, noSection] of rows) {
    await t.test(name, async () => {
      const { app } = await viewWith(files, SPEC_A);
      assert.equal(viewEl(app).querySelectorAll(".compass-change-hunk").length, 0);
      assert.equal(viewEl(app).querySelectorAll(".compass-change-row").length, 0);
      if (noSection) assert.equal(sectionsIn(app).length, 0);
    });
  }
});

// Adversarial where: the changes are wired to the spec view alone, so a plan or
// a research document under review shows none; a long document's heading is
// taken from the wrong line; the trailing context of a research table reaches
// the next section's heading.
test("a plan and a research document with a pending review show their changes under the heading each sits in", async (t) => {
  const planOld = PLAN_24.split("\n");
  const planNew = planOld.map((l, i) => (i === 176 ? l.replace("complexity: M,", "complexity: L,") : l));
  assert.notEqual(planOld[176], planNew[176], "fixture error: line 177 is not the TASK-227 line");
  const resOld = SMALL_RESEARCH.split("\n");
  const resNew = resOld.map((l) => (l === "| 3 | Third | high | high | ev-3 |" ? "| 3 | Third | high | high | ev-9 |" : l));
  const rows = [
    ["plan", P24, planOld, planNew, "Wave 4 (detailed): the plugin draws", ["M"], ["L"]],
    ["research", RP, resOld, resNew, "A. First (axis 1)", ["ev-3"], ["ev-9"]],
  ];
  for (const [name, doc, oldLines, newLines, heading, del, add] of rows) {
    await t.test(name, async () => {
      const { app } = await viewWith({
        [doc]: newLines.join("\n"), ...reviewFiles("1", doc), [`${REVIEW_DIR}/1.changes.diff`]: replDiff(doc, oldLines, newLines),
      }, doc);
      assert.equal(sectionsIn(app).length, 1);
      const groups = groupEls(app);
      assert.deepEqual(groups.map(headingOfGroup), [heading]);
      assert.deepEqual([wordsIn(groups[0], "is-del"), wordsIn(groups[0], "is-add")], [del, add]);
    });
  }
});

// ---- what changed since a review: hostile diffs and request files ----

// Adversarial where: the diff's path is matched by a plain suffix, so in a
// vault whose root sits below the repository top a unit's file
// ".compass/unit/specs/a.md" is read as the vault's "specs/a.md" and its rows
// are mixed into that document's changes; the shortest matching path is the
// vault's own file.
test("the parser keeps a document apart from a deeper file that ends in the same path", () => {
  const old = ["## A", "a1 old"];
  const now = ["## A", "a1"];
  const diff = replDiff(".compass/unit/specs/a.md", ["## A", "unit old"], ["## A", "unit"]) + replDiff(".compass/specs/a.md", old, now);
  const groups = CompassReview.parseChanges(diff, joined(now), "specs/a.md");
  assert.deepEqual(rowsOf(groups).filter((r) => r.kind !== "ctx").map(rowText), ["a1 old", "a1"]);
});

// Adversarial where: diffs git writes without text hunks (a binary file, a pure
// rename, a mode change) throw or draw an empty group; a new file (--- /dev/null)
// or a hunk of a shrunken document puts the open-at line at 0 or past the end
// of the text, so the click opens nothing.
test("the parser draws nothing for diffs without hunks and keeps every open-at line inside the document", async (t) => {
  const binary = `diff --git a/${SPEC_REL} b/${SPEC_REL}\nindex 1111111..2222222 100644\nBinary files a/${SPEC_REL} and b/${SPEC_REL} differ\n`;
  const renamed = `diff --git a/old.md b/${SPEC_REL}\nsimilarity index 100%\nrename from old.md\nrename to ${SPEC_REL}\n`;
  const mode = `diff --git a/${SPEC_REL} b/${SPEC_REL}\nold mode 100644\nnew mode 100755\n`;
  const added = [`diff --git a/${SPEC_REL} b/${SPEC_REL}`, "new file mode 100644", "index 0000000..2222222", "--- /dev/null", `+++ b/${SPEC_REL}`,
    "@@ -0,0 +1,2 @@", "+## A", "+a1"].join("\n") + "\n";
  const farHunk = replDiff(SPEC_REL, [...Array(40).fill("x"), "tail old"], [...Array(40).fill("x"), "tail"]);
  const rows = [
    ["binary", binary, "## A\n", []],
    ["pure rename", renamed, "## A\n", []],
    ["mode change", mode, "## A\n", []],
    ["new file", added, joined(["## A", "a1"]), [1]],
    ["hunk below the end of a shrunken document", farHunk, ["## A", "a1", "tail"].join(String.fromCharCode(10)), [3]],
    ["an empty document", farHunk, "", [1]],
    ["empty diff text", "", "## A\n", []],
  ];
  for (const [name, diff, doc, lines] of rows) {
    await t.test(name, () => {
      const groups = CompassReview.parseChanges(diff, doc, SPEC_REL);
      assert.deepEqual(groups.flatMap((g) => g.hunks.map((h) => h.line)), lines);
    });
  }
});

// Adversarial where: the word comparison drops or doubles text for lines made of
// its own separators, non-ASCII text or very long table rows, so a row no longer
// reads as the line git printed; the cost guard for long lines loses the line.
test("the parser keeps the text of a replaced line whole whatever it holds", async (t) => {
  const long = (w) => Array.from({ length: 500 }, (_, i) => `${w}${i}`).join(" ");
  const rows = [
    ["only separators", "|,.;:()`[]*|", "|;.,:)(`][*|"],
    ["non-ASCII and emoji", "café ☃ 😀 naïve", "cafe ☃ 😀 naïve!"],
    ["trailing whitespace only", "x ", "x"],
    ["lines past the cost guard", long("a"), long("b")],
  ];
  for (const [name, before, after] of rows) {
    await t.test(name, () => {
      const groups = CompassReview.parseChanges(replDiff(SPEC_REL, ["## A", before], ["## A", after]), joined(["## A", after]), SPEC_REL);
      const all = rowsOf(groups);
      assert.deepEqual(all.map((r) => r.kind), ["ctx", "del", "add"]);
      assert.equal(rowText(all[1]), before);
      assert.equal(rowText(all[2]), after);
    });
  }
});

// Adversarial where: the saved diff is taken from a request that is not the
// newest pending one for the file (a stale older request's diff shows under
// a newer review that has none), from a request of another surface, or the
// plugin only looks in "tmp/review" so a project-rooted Obsidian vault
// (".compass/tmp/review", file paths led by ".compass/") shows nothing.
test("the changes come from the newest pending request of this surface in either review folder", async (t) => {
  const text = joined(SPEC_CHANGED_NEW);
  const diff = replDiff(SPEC_REL, SPEC_CHANGED_OLD, SPEC_CHANGED_NEW);
  const rows = [
    ["a newer pending request without a diff hides an older one's diff",
      { [SPEC_A]: text, ...reviewFiles("20260101T000001-aaaaaa", SPEC_A), [`${REVIEW_DIR}/20260101T000001-aaaaaa.changes.diff`]: diff,
        ...reviewFiles("20260101T000002-bbbbbb", SPEC_A) }, SPEC_A, 0],
    ["a request of another surface carries no changes for this one",
      { [SPEC_A]: text, [`${REVIEW_DIR}/1.request.json`]: req("1", SPEC_A, { surface: "vscode" }), [`${REVIEW_DIR}/1.changes.diff`]: diff }, SPEC_A, 0],
    ["a project-rooted vault keeps its review folder under .compass",
      { [".compass/specs/a.md"]: text, [".compass/tmp/review/1.request.json"]: req("1", ".compass/specs/a.md"),
        [".compass/tmp/review/1.changes.diff"]: diff }, ".compass/specs/a.md", 1],
  ];
  for (const [name, files, open, sections] of rows) {
    await t.test(name, async () => {
      const { app } = await viewWith(files, open);
      assert.equal(sectionsIn(app).length, sections);
    });
  }
});

// Adversarial where: a saved diff that is not a diff (empty, text, truncated
// mid-hunk, a hunk header with absurd counts) throws in the draw, so the plan
// board loses its task rows instead of only losing the changes section.
test("a plan board keeps its task rows when the saved diff is empty, not a diff or cut short", async (t) => {
  const withDiff = (diff) => ({ [P24]: PLAN_24, ...reviewFiles("1", P24), ...(diff === null ? {} : { [`${REVIEW_DIR}/1.changes.diff`]: diff }) });
  const base = await viewWith(withDiff(null), P24);
  const expected = taskRows(base.app).map((r) => r.dataset.id || textOfEl(r));
  assert.ok(expected.length > 0, "fixture error: the plan has no task rows");
  const rows = [
    ["an empty diff file", ""],
    ["text that is not a diff", "this is not a diff\n\u0000\u0001 binary-ish"],
    ["a hunk cut short", `diff --git a/${P24} b/${P24}\n--- a/${P24}\n+++ b/${P24}\n@@ -170,9 +170,9 @@\n context\n-gone`],
    ["a hunk header with absurd counts", `diff --git a/${P24} b/${P24}\n--- a/${P24}\n+++ b/${P24}\n@@ -1,999999 +1,999999 @@\n-a\n+b\n`],
  ];
  for (const [name, diff] of rows) {
    await t.test(name, async () => {
      const { app } = await viewWith(withDiff(diff), P24);
      assert.deepEqual(taskRows(app).map((r) => r.dataset.id || textOfEl(r)), expected);
    });
  }
});

// ---- the pipeline strip of a spec ----
//
// The view of a spec also shows where the spec stands: spec, research, plan,
// build and validate as one strip, each stage read from the properties of the
// plans and research documents that list the spec in `depends_on` and from the
// plan's task lines, with what waits on the human and what runs next.
//
// Statics:
//   CompassReview.pipelineFor(specPath, docs) -> { stages, waits, next, plans, research }
//       specPath: vault-relative path of the spec; docs: [{ path, text }], every
//       markdown document of the vault in any order, the spec itself included.
//       stages: [{ key, name, state, line, path }] in the order spec, research,
//         plan, build, validate. A spec that no plan or research document lists
//         has the spec stage alone. key is "spec" | "research" | "plan" | "build" |
//         "validate"; state is "done" | "current" | "ready" | "waiting" | "todo" |
//         "none"; line is the plain-words text drawn in the stage; path is the
//         document the stage opens, or null.
//         spec: done when status is approved, active or done, else waiting.
//         research: done when every linked research document is complete or done,
//           current otherwise.
//         plan: waiting while the first linked plan's status is not approved,
//           active or done, else done; its line names the plan id and the status.
//         build: todo while the plan waits; ready with no task done; current with
//           some done; done once every counted task line is done and at least one
//           exists. validate: ready when the build is done, else todo; path null.
//       waits: [{ text, path }] the approvals the human owes, spec first, then plan.
//       next: [{ id, title, line, path }] the plan's tasks that are ready to run
//         (not done, not intent-only, no open dependency), in file order.
//       plans: [{ path, id, status, done, open }] linked plans in the order of docs;
//         id is the PLAN-NNN of the file name; done and open count the task lines
//         parsePlanTasks reads (fenced and "Wave n elaborated" quotations left out).
//       research: [{ path, status }].
//       A document is linked when its own `depends_on` property holds a link whose
//       target is the spec: the link's path (without `#heading`, `|alias` and
//       extension) equals the spec path or ends with it on a folder boundary, or
//       the spec path ends with the link on a folder boundary; a folder spec
//       (`<folder>/index.md`) answers to its folder. Only type plan and type
//       research documents are read as stages.
//
// DOM (inside .compass-spec-view of the view panel):
//   .compass-pipeline        one per spec in view
//   .compass-pipe-stage      one per stage in order, dataset.key, dataset.state; holds
//                            .compass-pipe-name (the stage name) and .compass-pipe-line
//                            (its line). A stage with a path opens it when clicked; one
//                            without has no click handler.
//   .compass-pipe-waits      always present; one .compass-pipe-wait per wait, each with
//                            an "Open" button that opens the wait's path
//   .compass-pipe-next       always present; one .compass-pipe-task per next task,
//                            dataset.id "TASK-NNN", its text holding the id and the title
// The plugin lists the vault's documents with app.vault.getMarkdownFiles() and reads
// each with vault.adapter.read(path). A change to any listed document redraws the
// strip of the spec in view.

const PS_STEM = "SPEC-031-working-in-compass-is-visual";
const PS_SPEC = `specs/human-surface/${PS_STEM}.md`;
const PS_PLAN = "plans/PLAN-024-working-in-compass-is-visual.md";
const PS_RES = "research/human-surface/RESEARCH-working-in-compass-is-visual.md";
const PS_SPEC_TEXT = SPEC_FILES["SPEC-031-working-in-compass-is-visual.md"];
const PS_LESSON = "---\ntype: lesson\nstatus: active\n---\nx\n";
const psDoc = (type, status, fm = "", body = "") => `---\ntype: ${type}\nstatus: ${status}\n${fm}\n---\n# T\n\n${body}\n`;
const psSpec = (status = "approved") => psDoc("spec", status);
const psTasks = (marks) => marks.map((m, i) => `- [${m}] TASK-${i + 1}: work ${i + 1} - complexity: S, depends_on: none`);
const psPlan = (status, lines, fm = `depends_on: ["[[${PS_STEM}]]"]`) => psDoc("plan", status, fm, `## Phase 1\n\n${lines.join("\n")}\n\nSee [[${PS_STEM}]].`);
const pipe = (specPath, docs) => CompassReview.pipelineFor(specPath, docs.map(([p, text]) => ({ path: p, text })));
const stageOf = (r, key) => r.stages.find((s) => s.key === key);
const stageKeys = (r) => r.stages.map((s) => s.key);

// Adversarial where: the counts come from every task-shaped line instead of the
// task lines the board reads (the four quoted lines in a fence make 12 open
// where the plan holds 8), the stage names a plan that is not approved, the
// next tasks include ones still waiting on an open dependency (TASK-206 waits
// on TASK-202), or the strip depends on the order of the vault's documents.
test("for SPEC-031 the strip names PLAN-024 as approved with its done and open counts equal to its task lines", () => {
  const done = EXPECT_24.filter((t) => t.status === "done").length;
  const open = EXPECT_24.length - done;
  assert.deepEqual([done, open], [15, 8], "fixture error: expected counts");
  const naiveOpen = PLAN_24.split("\n").filter((l) => /^- \[ \] TASK-\d+:/.test(l)).length;
  assert.ok(naiveOpen > open, "fixture error: the plan quotes task lines in a fence");
  const r = pipe(PS_SPEC, [["notes/n.md", PS_LESSON], [PS_RES, RESEARCH_TEXT], [PS_PLAN, PLAN_24], [PS_SPEC, PS_SPEC_TEXT]]);
  assert.deepEqual(stageKeys(r), ["spec", "research", "plan", "build", "validate"]);
  assert.deepEqual(r.plans, [{ path: PS_PLAN, id: "PLAN-024", status: "approved", done: 15, open: 8 }]);
  assert.deepEqual(r.research, [{ path: PS_RES, status: "complete" }]);
  assert.match(stageOf(r, "plan").line, /PLAN-024/);
  assert.match(stageOf(r, "plan").line, /approved/);
  assert.equal(stageOf(r, "plan").path, PS_PLAN);
  assert.equal(stageOf(r, "research").path, PS_RES);
  assert.equal(stageOf(r, "spec").path, PS_SPEC);
  assert.match(stageOf(r, "build").line, /\b15\b/);
  assert.deepEqual(r.stages.map((s) => [s.key, s.state]), [["spec", "done"], ["research", "done"], ["plan", "done"], ["build", "current"], ["validate", "todo"]]);
  assert.equal(stageOf(r, "validate").path, null);
  assert.deepEqual(r.waits, []);
  assert.deepEqual(r.next.map((t) => [t.id, t.line, t.path]), [["TASK-202", 171, PS_PLAN], ["TASK-204", 186, PS_PLAN]]);
  assert.ok(r.next.every((t) => typeof t.title === "string" && t.title.length > 0));
});

// Adversarial where: a document counts as linking the spec because its text
// merely mentions the stem (a body link, the summary, `supersedes`), because the
// stem is a prefix or a suffix of another name, because a bare `index` or the
// same stem in another folder matches, or because the link carries an alias or
// heading, sits last in a list, or is written as a block list and is missed.
test("a document links the spec only through a depends_on link whose target is the spec", async (t) => {
  const FOLDER = "specs/SPEC-002-tile-editor/index.md";
  const CHILD = "specs/SPEC-002-tile-editor/SPEC-001-master-material.md";
  const dep = (...links) => `depends_on: [${links.map((l) => `"[[${l}]]"`).join(", ")}]`;
  const rows = [
    ["a bare stem", PS_SPEC, "plan", dep(PS_STEM), true],
    ["a path-qualified link", PS_SPEC, "plan", dep(`specs/human-surface/${PS_STEM}`), true],
    ["a heading and an alias", PS_SPEC, "plan", dep(`specs/human-surface/${PS_STEM}#Problem|the spec`), true],
    ["the last of three links", PS_SPEC, "plan", dep("SPEC-001-other", "RESEARCH-other", `specs/human-surface/${PS_STEM}`), true],
    ["a block list", PS_SPEC, "plan", `depends_on:\n  - "[[SPEC-001-other]]"\n  - "[[${PS_STEM}]]"`, true],
    ["a research document", PS_SPEC, "research", dep(PS_STEM), true],
    ["a folder spec by its folder name", FOLDER, "plan", dep("SPEC-002-tile-editor"), true],
    ["a folder spec by its folder path", FOLDER, "plan", dep("specs/SPEC-002-tile-editor"), true],
    ["a folder spec by its index path and alias", FOLDER, "plan", dep("specs/SPEC-002-tile-editor/index|tile editor"), true],
    ["a bare index names no folder spec", FOLDER, "plan", dep("index"), false],
    ["a child by its folder-qualified path", CHILD, "plan", dep("SPEC-002-tile-editor/SPEC-001-master-material"), true],
    ["a child by its bare stem", CHILD, "plan", dep("SPEC-001-master-material"), true],
    ["the parent link does not reach the child", CHILD, "plan", dep("SPEC-002-tile-editor"), false],
    ["the stem inside the summary only", PS_SPEC, "plan", `depends_on: []\nsummary: "builds on [[${PS_STEM}]]"`, false],
    ["supersedes holds the link", PS_SPEC, "plan", `supersedes: "[[${PS_STEM}]]"`, false],
    ["an empty depends_on", PS_SPEC, "plan", "depends_on: []", false],
    ["a longer stem that starts with ours", PS_SPEC, "plan", dep(`${PS_STEM}-extra`), false],
    ["a longer name that ends with our stem", PS_SPEC, "plan", dep(`OLD-${PS_STEM}`), false],
    ["the same stem in another folder", PS_SPEC, "plan", dep(`specs/other/${PS_STEM}`), false],
    ["a lesson that depends on the spec", PS_SPEC, "lesson", dep(PS_STEM), false],
    ["a decision that depends on the spec", PS_SPEC, "decision", dep(PS_STEM), false],
    ["a child spec that depends on the spec", PS_SPEC, "spec", dep(PS_STEM), false],
  ];
  for (const [name, specPath, type, fm, linked] of rows) {
    await t.test(name, () => {
      const doc = psDoc(type, "approved", fm, `${psTasks([" "]).join("\n")}\n[[${PS_STEM}]] and [[SPEC-002-tile-editor]]`);
      const r = pipe(specPath, [[specPath, psSpec()], ["docs/x.md", doc]]);
      assert.equal(r.plans.length + r.research.length, linked ? 1 : 0);
      assert.equal(stageKeys(r).includes(type === "research" ? "research" : "plan"), (type === "research" || type === "plan") && linked);
    });
  }
});

// Adversarial where: the approval words are tested loosely so a draft or a
// plan in review counts as approved (the boundary sits between `review` and
// `approved`), the build stage jumps at the wrong task (0, 1 and all done are
// the three edges), uppercase [X] is not a done box, the wait for the spec or
// plan is missing or in the wrong order, or a task the plan quotes in an
// elaborated section is counted.
test("the plan, build and validate stages and the waits follow the statuses and the task boxes", async (t) => {
  const quoted = ["## Wave 1 elaborated", "", "- [ ] TASK-90: quoted", "- [x] TASK-91: quoted"];
  const rows = [
    ["approved, none done", "approved", "approved", psTasks([" ", " "]), ["done", "ready", "todo"], [0, 2], []],
    ["approved, one of two done", "approved", "approved", psTasks(["x", " "]), ["done", "current", "todo"], [1, 1], []],
    ["approved, all done", "approved", "approved", psTasks(["x", "x"]), ["done", "done", "ready"], [2, 0], []],
    ["an uppercase X is done", "approved", "approved", psTasks(["X"]), ["done", "done", "ready"], [1, 0], []],
    ["quoted tasks in an elaborated section are not counted", "approved", "approved", [...psTasks(["x"]), "", ...quoted], ["done", "done", "ready"], [1, 0], []],
    ["a plan in review waits", "approved", "review", psTasks([" "]), ["waiting", "todo", "todo"], [0, 1], [PS_PLAN]],
    ["a draft plan waits", "approved", "draft", psTasks(["x"]), ["waiting", "todo", "todo"], [1, 0], [PS_PLAN]],
    ["an active plan does not wait", "approved", "active", psTasks(["x", " "]), ["done", "current", "todo"], [1, 1], []],
    ["a done plan does not wait", "approved", "done", psTasks(["x"]), ["done", "done", "ready"], [1, 0], []],
    ["a draft spec waits and the approved plan does not", "draft", "approved", psTasks([" "]), ["done", "ready", "todo"], [0, 1], [PS_SPEC]],
    ["a spec in review waits", "review", "approved", psTasks([" "]), ["done", "ready", "todo"], [0, 1], [PS_SPEC]],
    ["a draft spec and a draft plan wait, the spec first", "draft", "draft", psTasks([" "]), ["waiting", "todo", "todo"], [0, 1], [PS_SPEC, PS_PLAN]],
  ];
  for (const [name, specStatus, planStatus, lines, [plan, build, validate], [done, open], waits] of rows) {
    await t.test(name, () => {
      const r = pipe(PS_SPEC, [[PS_SPEC, psSpec(specStatus)], [PS_PLAN, psPlan(planStatus, lines)]]);
      assert.deepEqual([stageOf(r, "plan").state, stageOf(r, "build").state, stageOf(r, "validate").state], [plan, build, validate]);
      assert.deepEqual([r.plans[0].done, r.plans[0].open], [done, open]);
      assert.deepEqual(r.waits.map((w) => w.path), waits);
      assert.ok(r.waits.every((w) => typeof w.text === "string" && w.text.length > 0));
      assert.equal(stageOf(r, "spec").state, specStatus === "draft" || specStatus === "review" ? "waiting" : "done");
    });
  }
});

// Adversarial where: "every task done" is vacuously true for a plan whose
// counted task lines number zero (none written, all in a fence, all in an
// elaborated section), so the build shows finished and validation shows ready.
test("a plan with no counted task lines is never a finished build", async (t) => {
  const rows = [
    ["no task lines", ["Nothing here yet."]],
    ["task lines only in a fence", ["```markdown", ...psTasks(["x", "x"]), "```"]],
    ["task lines only in an elaborated section", ["## Wave 2 elaborated", "", ...psTasks(["x"])]],
  ];
  for (const [name, lines] of rows) {
    await t.test(name, () => {
      const r = pipe(PS_SPEC, [[PS_SPEC, psSpec()], [PS_PLAN, psPlan("approved", lines)]]);
      assert.deepEqual([r.plans[0].done, r.plans[0].open], [0, 0]);
      assert.notEqual(stageOf(r, "build").state, "done");
      assert.notEqual(stageOf(r, "validate").state, "ready");
      assert.deepEqual(r.next, []);
    });
  }
});

// Adversarial where: one unfinished research document among complete ones
// still reads as done (the first document alone is judged), a draft counts as
// complete, or the research the strip names is another spec's.
test("the research stage is done only when every linked research document is complete or done", async (t) => {
  const res = (status, dep) => psDoc("research", status, `depends_on: ["[[${dep}]]"]`);
  const rows = [
    ["one complete", [["complete", PS_STEM]], "done", 1],
    ["one with status done", [["done", PS_STEM]], "done", 1],
    ["one draft", [["draft", PS_STEM]], "current", 1],
    ["complete then draft", [["complete", PS_STEM], ["draft", PS_STEM]], "current", 2],
    ["draft then complete", [["draft", PS_STEM], ["complete", PS_STEM]], "current", 2],
    ["a draft research of another spec is not ours", [["complete", PS_STEM], ["draft", "SPEC-999-other"]], "done", 1],
  ];
  for (const [name, list, state, linked] of rows) {
    await t.test(name, () => {
      const docs = list.map(([status, dep], i) => [`research/R${i}.md`, res(status, dep)]);
      const r = pipe(PS_SPEC, [[PS_SPEC, psSpec()], ...docs]);
      assert.equal(r.research.length, linked);
      assert.equal(stageOf(r, "research").state, state);
    });
  }
});

// Adversarial where: a spec that nothing links still draws a plan or research
// stage (the mockup's five always-on chevrons), the wait for its approval is
// lost, or plans and research of other specs leak into its strip.
test("a spec no document links shows only the spec stage", async (t) => {
  const others = [
    [PS_PLAN, psPlan("approved", psTasks(["x", " "]), 'depends_on: ["[[SPEC-999-other]]"]')],
    [PS_RES, psDoc("research", "complete", 'depends_on: ["[[SPEC-999-other]]"]')],
    ["notes/n.md", PS_LESSON],
  ];
  for (const [status, state, waits] of [["approved", "done", []], ["draft", "waiting", [PS_SPEC]]]) {
    await t.test(status, () => {
      const r = pipe(PS_SPEC, [[PS_SPEC, psSpec(status)], ...others]);
      assert.deepEqual(stageKeys(r), ["spec"]);
      assert.equal(r.stages[0].state, state);
      assert.match(r.stages[0].line, new RegExp(status));
      assert.equal(r.stages[0].path, PS_SPEC);
      assert.deepEqual(r.waits.map((w) => w.path), waits);
      assert.deepEqual([r.next, r.plans, r.research], [[], [], []]);
    });
  }
});

// ---- the strip in the view panel ----

async function loadedListing(files, ghosts = []) {
  const app = makeApp(files);
  app.vault.getMarkdownFiles = () => [...app.store.keys()].filter((k) => k.endsWith(".md")).concat(ghosts).map(mdFile);
  const plugin = new CompassReview(app);
  await plugin.onload();
  return { app, plugin };
}
async function stripView(files, open, ghosts) {
  const r = await loadedListing(files, ghosts);
  await openDoc(r.app, open);
  await r.plugin.openViewPanel();
  await settle();
  return r;
}
const pipeStages = (app) => viewEl(app).querySelectorAll(".compass-pipe-stage");
const pipeStage = (app, key) => pipeStages(app).find((s) => s.dataset.key === key);
const stageLine = (app, key) => textOfEl(pipeStage(app, key).querySelector(".compass-pipe-line"));
const SV_FILES = { [PS_SPEC]: PS_SPEC_TEXT, [PS_PLAN]: PLAN_24, [PS_RES]: RESEARCH_TEXT, "notes/n.md": PS_LESSON };

// Adversarial where: the strip is missing from the spec's view or replaces the
// decision cards, stages come out of order or with the wrong state, a click on
// a stage opens the wrong document (or the validate stage, which has no
// document, reacts), the empty waits box is absent, the ready tasks are not
// listed with their ids, or drawing and clicking write into the vault.
test("the view of SPEC-031 draws the strip, its waits and next tasks beside the decision cards, and a stage opens its document", async () => {
  const { app } = await stripView(SV_FILES, PS_SPEC);
  assert.equal(viewEl(app).querySelector(".compass-spec-view").querySelectorAll(".compass-pipeline").length, 1);
  assert.deepEqual(pipeStages(app).map((s) => [s.dataset.key, s.dataset.state]),
    [["spec", "done"], ["research", "done"], ["plan", "done"], ["build", "current"], ["validate", "todo"]]);
  assert.match(stageLine(app, "plan"), /PLAN-024.*approved|approved.*PLAN-024/);
  assert.match(stageLine(app, "build"), /\b15\b/);
  assert.equal(viewEl(app).querySelector(".compass-pipe-waits").querySelectorAll(".compass-pipe-wait").length, 0);
  assert.deepEqual(viewEl(app).querySelector(".compass-pipe-next").querySelectorAll(".compass-pipe-task").map((t) => t.dataset.id), ["TASK-202", "TASK-204"]);
  assert.deepEqual(decisionCards(app).map((c) => c.dataset.id), ["D-01", "D-02"]);
  const validate = pipeStage(app, "validate");
  assert.equal(typeof validate.onclick === "function" || (validate.handlers.click || []).length > 0, false, "validate has no document to open");
  const before = Object.fromEntries(app.store);
  const writes = [];
  const write = app.vault.adapter.write;
  app.vault.adapter.write = async (p, d) => { writes.push(p); return write.call(app.vault.adapter, p, d); };
  for (const [key, target] of [["research", PS_RES], ["plan", PS_PLAN], ["spec", PS_SPEC]]) {
    await openDoc(app, PS_SPEC);
    await clickOn(pipeStage(app, key));
    await settle();
    assert.equal(app.opened[app.opened.length - 1].path, target, key);
  }
  assert.deepEqual(writes, []);
  assert.deepEqual(Object.fromEntries(app.store), before);
});

// Adversarial where: a draft plan raises no wait row (or one that opens the
// spec), the stage keeps reading approved, or the Open button on the wait does
// nothing.
test("a spec whose plan is a draft shows the plan stage waiting and a wait row that opens the plan", async () => {
  const draft = PLAN_24.replace("status: approved", "status: draft");
  assert.notEqual(draft, PLAN_24, "fixture error: the plan has no approved status");
  const { app } = await stripView({ ...SV_FILES, [PS_PLAN]: draft }, PS_SPEC);
  assert.equal(pipeStage(app, "plan").dataset.state, "waiting");
  assert.equal(pipeStage(app, "build").dataset.state, "todo");
  const waits = viewEl(app).querySelector(".compass-pipe-waits").querySelectorAll(".compass-pipe-wait");
  assert.equal(waits.length, 1);
  await clickOn(button(waits[0], "Open"));
  await settle();
  assert.equal(app.opened[app.opened.length - 1].path, PS_PLAN);
});

// Adversarial where: the strip appears under plans, research or other types, a
// spec nothing links draws stages it has no documents for, or an unreadable
// vault document stops the strip from drawing at all.
test("a spec no document links draws one stage; other documents draw no strip; an unreadable document is skipped", async () => {
  const alone = { [PS_SPEC]: PS_SPEC_TEXT, "notes/n.md": PS_LESSON, "plans/PLAN-900-other.md": psPlan("approved", psTasks([" "]), 'depends_on: ["[[SPEC-999-other]]"]') };
  const first = await stripView(alone, PS_SPEC, ["plans/ghost.md"]);
  assert.deepEqual(pipeStages(first.app).map((s) => s.dataset.key), ["spec"]);
  assert.equal(viewEl(first.app).querySelector(".compass-pipe-next").querySelectorAll(".compass-pipe-task").length, 0);
  const linked = await stripView({ ...SV_FILES }, PS_SPEC, ["plans/ghost.md"]);
  assert.equal(pipeStages(linked.app).length, 5, "a document that cannot be read leaves the strip whole");
  for (const other of [PS_PLAN, PS_RES, "notes/n.md"]) {
    await openDoc(linked.app, other);
    assert.equal(viewEl(linked.app).querySelectorAll(".compass-pipeline").length, 0, other);
  }
  await openDoc(linked.app, PS_SPEC);
  assert.equal(viewEl(linked.app).querySelectorAll(".compass-pipeline").length, 1, "back on the spec the strip returns");
});

// Adversarial where: the spec's panel is redrawn only when the spec's own text
// changes, so the agent checking off a task in the plan leaves the open spec
// showing the old counts.
test("a change to a linked plan redraws the strip of the spec in view", async () => {
  const { app } = await stripView(SV_FILES, PS_SPEC);
  assert.match(stageLine(app, "build"), /\b15\b/);
  const next = PLAN_24.replace("- [ ] TASK-228:", "- [x] TASK-228:");
  assert.notEqual(next, PLAN_24, "fixture error: TASK-228 line");
  app.store.set(PS_PLAN, next);
  await app.listeners.modify(mdFile(PS_PLAN));
  await settle();
  assert.match(stageLine(app, "build"), /\b16\b/);
  assert.doesNotMatch(stageLine(app, "build"), /\b15\b/);
});

// Adversarial where: text from a linked plan or research document (a task
// title, a status) is parsed as markup in the strip, so an element or an
// event attribute appears that the plugin never made.
test("markup in a linked plan's task titles and statuses is drawn as literal text in the strip", async () => {
  const evil = "<img src=x onerror=\"alert(1)\"> <script>alert(2)</script>";
  const plan = psPlan("approved", [`- [ ] TASK-1: ${evil} - complexity: S, depends_on: none`]);
  const research = psDoc("research", "'<b>x</b>'", `depends_on: ["[[${PS_STEM}]]"]`);
  const { app } = await stripView({ [PS_SPEC]: PS_SPEC_TEXT, [PS_PLAN]: plan, [PS_RES]: research }, PS_SPEC);
  const allowed = new Set([...TAGS_ALLOWED, "h3", "h5", "ol", "em", "b"]);
  const els = viewEl(app).all();
  for (const tag of new Set(els.map((e) => e.tag))) assert.ok(allowed.has(tag), `unexpected <${tag}> element`);
  for (const e of els) {
    assert.ok(!Object.keys(e.attrs).some((k) => /^on/i.test(k)), `an on* attribute on <${e.tag}>`);
    assert.ok(!("innerHTML" in e), "innerHTML was assigned");
  }
  assert.match(textOfEl(viewEl(app).querySelector(".compass-pipe-next")), /<img src=x onerror="alert\(1\)">/);
});

// ---- the strip under load, races and path forms ----

const PA_SPEC_ID = "SPEC-900-fixture";
const paPlan = (status, lines, link = PA_SPEC_ID) => psPlan(status, lines, `depends_on: ["[[${link}]]"]`);
const paReads = (app) => {
  const reads = [];
  const read = app.vault.adapter.read;
  app.vault.adapter.read = async (p) => { reads.push(p); return read.call(app.vault.adapter, p); };
  return reads;
};
const paQuiet = async () => { for (let i = 0; i < 12; i++) await sleep(); };

// Adversarial where: every markdown change while a spec is in view re-reads the
// whole vault with no coalescing, so a burst of saves (an agent checking off
// tasks, a sync) costs one full-vault read per event instead of a bounded few.
// Each read takes a tick, as disk reads do, so the draws overlap.
test("a burst of 100 saves while a spec is in view reads the vault a bounded number of times", async () => {
  const files = { [SP]: CALLOUT, [PS_PLAN]: paPlan("approved", psTasks([" "])) };
  for (let i = 0; i < 60; i++) files[`notes/n${i}.md`] = PS_LESSON;
  const { app, plugin } = await loadedListing(files);
  await openDoc(app, SP);
  await plugin.openViewPanel();
  await settle();
  const size = app.vault.getMarkdownFiles().length;
  const read = app.vault.adapter.read;
  app.vault.adapter.read = async (p) => { await sleep(); return read.call(app.vault.adapter, p); };
  const reads = paReads(app);
  for (let i = 0; i < 100; i++) {
    app.listeners.modify(mdFile(`notes/n${i % 60}.md`));
    await sleep();
  }
  await paQuiet();
  assert.ok(reads.length <= 10 * size, `${reads.length} reads for a vault of ${size} documents`);
});

// Adversarial where: a change while a plan or research view is showing, or a
// non-markdown change under a spec, re-reads the vault or repaints the panel.
test("a save of an unrelated file leaves a plan board, a research view and the spec strip as drawn", async (t) => {
  const files = { [SP]: CALLOUT, [PS_PLAN]: PLAN_24, [PS_RES]: RESEARCH_TEXT, "notes/n.md": PS_LESSON, "data/x.json": "{}" };
  for (const [name, open, other] of [
    ["plan board, markdown", PS_PLAN, "notes/n.md"],
    ["research view, markdown", PS_RES, "notes/n.md"],
    ["spec view, a json file", SP, "data/x.json"],
  ]) {
    await t.test(name, async () => {
      const { app, plugin } = await loadedListing(files);
      await openDoc(app, open);
      await plugin.openViewPanel();
      await settle();
      const first = viewEl(app).children[0];
      const seen = paReads(app);
      await app.listeners.modify(mdFile(other));
      await paQuiet();
      assert.deepEqual(seen, [], "the vault was read");
      assert.equal(viewEl(app).children[0], first, "the panel was repainted");
    });
  }
  await t.test("spec view, a markdown file: not repainted", async () => {
    const { app, plugin } = await loadedListing(files);
    await openDoc(app, SP);
    await plugin.openViewPanel();
    await settle();
    const first = viewEl(app).children[0];
    await app.listeners.modify(mdFile("notes/n.md"));
    await paQuiet();
    assert.equal(viewEl(app).children[0], first, "the panel was repainted");
  });
});

// Adversarial where: typed decision-card notes and Change answers are lost when
// the strip redraws because a linked plan changed, or the card is rebuilt on an
// unrelated save while the human is typing.
test("decision-card answers and a half-typed note survive saves of the plan and of unrelated files", async () => {
  const plan = paPlan("approved", psTasks([" ", " "]));
  const { app, plugin } = await loadedListing({ [SP]: CALLOUT, [REQ1]: req("1", SP), [PS_PLAN]: plan, "notes/n.md": PS_LESSON });
  await openDoc(app, SP);
  await plugin.openViewPanel();
  await settle();
  await plugin.handler({ request: REQ1 });
  await settle();
  await changeDecision(app, "D-02", "reword it");
  typeInto(cardArea(decisionCard(app, "D-04")), "half typed");
  const card4 = decisionCard(app, "D-04");
  await app.listeners.modify(mdFile("notes/n.md"));
  await paQuiet();
  assert.equal(decisionCard(app, "D-04"), card4, "an unrelated save rebuilt the card");
  app.store.set(PS_PLAN, paPlan("approved", psTasks(["x", " "])));
  await app.listeners.modify(mdFile(PS_PLAN));
  await paQuiet();
  assert.match(stageLine(app, "build"), /1 of 2/);
  assert.equal(cardArea(decisionCard(app, "D-04")).value, "half typed");
  assert.match(decisionCard(app, "D-02").cls, /is-change/);
  assert.equal(cardArea(decisionCard(app, "D-02")).value, "reword it");
  await click(cardBtn(app, "1", "Needs changes"));
  await settle();
  assert.equal(verdictNotes(app), "D-02: reword it");
});

// Adversarial where: a redraw that read the plan before it changed lands after
// a later redraw that read it after, so the strip shows the older counts.
test("of two redraws racing on a slow read of the plan, the later one is what stays drawn", async () => {
  const { app } = await stripView({ [PS_SPEC]: PS_SPEC_TEXT, [PS_PLAN]: psPlan("approved", psTasks([" ", " ", " "])) }, PS_SPEC);
  assert.match(stageLine(app, "build"), /0 of 3/);
  const read = app.vault.adapter.read;
  let hold = null;
  app.vault.adapter.read = async (p) => {
    const value = await read.call(app.vault.adapter, p);
    if (p === PS_PLAN && hold) await hold.wait;
    return value;
  };
  hold = gate();
  app.store.set(PS_PLAN, psPlan("approved", psTasks(["x", " ", " "])));
  app.listeners.modify(mdFile(PS_PLAN));
  await paQuiet();
  const slow = hold;
  hold = null;
  app.store.set(PS_PLAN, psPlan("approved", psTasks(["x", "x", " "])));
  app.listeners.modify(mdFile(PS_PLAN));
  await paQuiet();
  assert.match(stageLine(app, "build"), /2 of 3/);
  slow.release();
  await paQuiet();
  assert.match(stageLine(app, "build"), /2 of 3/);
});

// Adversarial where: the plugin attaches its vault listeners without the
// registration that detaches them at unload, so a disabled plugin keeps
// redrawing, or a save after unload with a spec in view throws.
test("every vault and workspace subscription is registered for removal, and a save after unload throws nothing", async () => {
  const app = makeApp({ [SP]: CALLOUT });
  app.vault.getMarkdownFiles = () => [mdFile(SP)];
  const made = [];
  for (const target of [app.vault, app.workspace]) {
    const on = target.on;
    target.on = (name, fn) => { on.call(target, name, fn); const ref = { name }; made.push(ref); return ref; };
  }
  const plugin = new CompassReview(app);
  const registered = [];
  plugin.registerEvent = (ref) => registered.push(ref);
  await plugin.onload();
  assert.ok(made.some((r) => r.name === "modify"), "fixture error: modify was never subscribed");
  assert.deepEqual(made.filter((r) => !registered.includes(r)).map((r) => r.name), []);
  await openDoc(app, SP);
  await plugin.openViewPanel();
  await settle();
  plugin.onunload();
  await app.listeners.modify(mdFile(SP));
  await app.listeners.modify(mdFile("notes/other.md"));
  await paQuiet();
});

// Adversarial where: the cap is off by one (6 ready tasks print "and 0 more"
// or drop one), the overflow text miscounts or mis-pluralises, or tasks that
// wait on an open dependency are counted among the ready ones.
test("the next list shows at most six ready tasks and counts the rest", async (t) => {
  const ready = (n) => Array.from({ length: n }, (_, i) => `- [ ] TASK-${i + 1}: ready ${i + 1} - complexity: S, depends_on: none`);
  const blocked = ["- [ ] TASK-90: waits - complexity: S, depends_on: TASK-1", "- [ ] TASK-91: waits too - complexity: S, depends_on: TASK-90"];
  for (const [n, shown, more] of [[0, 0, null], [1, 1, null], [5, 5, null], [6, 6, null], [7, 6, "and 1 more task ready"], [12, 6, "and 6 more tasks ready"]]) {
    await t.test(`${n} ready`, async () => {
      const { app } = await stripView({ [PS_SPEC]: PS_SPEC_TEXT, [PS_PLAN]: psPlan("approved", n > 0 ? [...ready(n), ...blocked] : ready(0)) }, PS_SPEC);
      const box = viewEl(app).querySelector(".compass-pipe-next");
      const tasks = box.querySelectorAll(".compass-pipe-task");
      assert.deepEqual(tasks.map((x) => x.dataset.id), Array.from({ length: shown }, (_, i) => `TASK-${i + 1}`));
      const text = textOfEl(box);
      if (more) assert.ok(text.includes(more), text);
      else assert.doesNotMatch(text, /\band \d+ more\b/);
      if (n === 0) assert.match(text, /No task is ready/);
    });
  }
});

// Adversarial where: a plan listing two specs shows in one of them only, a plan
// naming the spec by its bare stem and its path (or twice) counts as two plans,
// or a link into a workstream folder (a longer path ending in the root spec's
// path) is taken as naming the root spec.
test("a plan or research document counts once per spec it links and never for a spec in another folder", async (t) => {
  const SPEC_B = "specs/SPEC-901-second.md";
  await t.test("a plan linking two specs belongs to both strips", () => {
    const two = paPlan("approved", psTasks([" "]), `${PA_SPEC_ID}]]", "[[SPEC-901-second`);
    for (const spec of [SP, SPEC_B]) {
      const r = pipe(spec, [[SP, psSpec()], [SPEC_B, psSpec()], ["plans/PLAN-001-x.md", two]]);
      assert.deepEqual(r.plans.map((p) => p.id), ["PLAN-001"], spec);
      assert.deepEqual(r.next.map((x) => x.id), ["TASK-1"], spec);
    }
  });
  await t.test("the bare stem and the path-qualified link together, and a repeated link, count once", () => {
    const both = paPlan("approved", psTasks([" "]), `${PA_SPEC_ID}]]", "[[specs/${PA_SPEC_ID}]]", "[[${PA_SPEC_ID}`);
    const res = psDoc("research", "complete", `depends_on: ["[[${PA_SPEC_ID}]]", "[[${SP.replace(/\.md$/, "")}]]"]`);
    const r = pipe(SP, [[SP, psSpec()], ["plans/PLAN-001-x.md", both], ["research/R.md", res]]);
    assert.equal(r.plans.length, 1);
    assert.equal(r.research.length, 1);
    assert.ok(stageOf(r, "research").line.includes("1 document,"), stageOf(r, "research").line);
  });
  await t.test("a link into a workstream folder does not name the root spec of the same name", () => {
    const root = "specs/SPEC-001-cli.md";
    const unit = paPlan("approved", psTasks([" "]), "compass-cli/specs/SPEC-001-cli");
    const r = pipe(root, [[root, psSpec()], ["plans/PLAN-001-x.md", unit]]);
    assert.deepEqual(stageKeys(r), ["spec"]);
  });
  await t.test("a shorter suffix of the spec's path names it", () => {
    const unitSpec = "compass-cli/specs/SPEC-001-cli.md";
    const plan = paPlan("approved", psTasks([" "]), "specs/SPEC-001-cli");
    const r = pipe(unitSpec, [[unitSpec, psSpec()], ["plans/PLAN-001-x.md", plan]]);
    assert.equal(r.plans.length, 1);
  });
});

// Adversarial where: documents saved on Windows (CRLF line ends, a byte-order
// mark, quoted values) lose their properties, so the plan reads as missing, the
// status as unapproved, or a block-list link as absent.
test("plan, research and spec documents with CRLF line ends and a byte-order mark are read like LF ones", async (t) => {
  const crlf = (s, bom) => (bom ? "﻿" : "") + s.replace(/\n/g, "\r\n");
  for (const bom of [false, true]) {
    await t.test(bom ? "with a byte-order mark" : "without", () => {
      const plan = crlf(`---\ntype: plan\nstatus: "approved"\ndepends_on:\n  - "[[SPEC-001-other]]"\n  - "[[${PS_STEM}]]"\n---\n# P\n\n${psTasks(["x", " "]).join("\n")}\n`, bom);
      const res = crlf(`---\ntype: research\nstatus: 'complete'\ndepends_on: ["[[${PS_STEM}]]"]\n---\n# R\n`, bom);
      const spec = crlf("---\ntype: spec\nstatus: approved\n---\n# S\n", bom);
      const r = pipe(PS_SPEC, [[PS_SPEC, spec], [PS_PLAN, plan], [PS_RES, res]]);
      assert.deepEqual(r.stages.map((s) => [s.key, s.state]), [["spec", "done"], ["research", "done"], ["plan", "done"], ["build", "current"], ["validate", "todo"]]);
      assert.deepEqual([r.plans[0].done, r.plans[0].open], [1, 1]);
      assert.deepEqual(r.next.map((x) => x.id), ["TASK-2"]);
    });
  }
});

// ---- a loop's charts ----
//
// The view for a document of `type: loop` charts the runs in the `ledger.jsonl`
// beside it. A run record (`"type":"run"`) carries a reading when its
// `reading_after` holds a numeric `value`; a throttled run or one already at the
// set point has `reading_after: null` and carries none. Pure functions are
// static exports of main.js:
//
//   CompassReview.viewFor(text)           -> "loop" for `type: loop`
//   CompassReview.parseLedger(text)       -> { readings: number[], costs: number[], skipped: number }
//       readings: reading_after.value of each run record that carries one, in
//       file order; costs: cost_usd of those same runs, index for index (0 when
//       absent); skipped: non-blank lines that are not a JSON object.
//   CompassReview.loopChartSource(ledger, kind)
//       ledger is a parseLedger result, kind "reading" or "cost"; returns a
//       Mermaid `xychart-beta` source with one `line [..]`, or null when the
//       ledger holds no reading. The cost source's y-axis line says "estimate".
//
// DOM the loop view draws in the view panel:
//   .compass-loop-view     root, one per loop in view
//   .compass-loop-chart    one per chart, dataset.kind "reading" or "cost"; its
//                          innerHTML is the svg that mermaid.render returned
//   .compass-loop-skipped  only when lines were skipped; its text holds the count
//   .compass-view-note     the one plain line when the ledger holds no reading
// The ledger read is `<folder of the loop document>/ledger.jsonl`.

test.beforeEach(() => {
  mermaidState.calls.length = 0;
  mermaidState.loadError = null;
  mermaidState.renderError = null;
  mermaidState.renderGate = null;
});

const LEDGER_FIX = fs.readFileSync(path.join(__dirname, "fixtures", "LOOP-001-ledger.jsonl"), "utf8");
const LOOP_INDEX = fixture("LOOP-001-index.md");
const LOOP_EXPECT = JSON.parse(fixture("LOOP-001-ledger.expected.json"));
const LOOP_DIR = ".compass/loops/LOOP-001-visual-questions";
const LOOP_DOC = `${LOOP_DIR}/index.md`;
const LOOP_LEDGER = `${LOOP_DIR}/ledger.jsonl`;
const loopSettle = async () => { for (let i = 0; i < 8; i++) await sleep(); };
const loopDoc = (extra = "") => `---\ntitle: "Loop: x"\ntype: loop\n${extra}---\n# Loop\n`;
const runLine = (reading, cost, extra = {}) =>
  JSON.stringify({ ts: "2026-10-19T01:00:00+00:00", type: "run", run_id: "RUN-1", cost_usd: cost, reading_before: { value: 99 }, reading_after: reading === null ? null : { value: reading, items_count: 1 }, outcome: "helpful", ...extra });
const ledgerOf = (lines) => lines.join("\n") + "\n";
const chartsOf = (app) => viewEl(app).querySelectorAll(".compass-loop-chart");
const chartOf = (app, kind) => chartsOf(app).find((c) => c.dataset.kind === kind);
const drawnSource = (chart) => decodeURIComponent(/data-source="([^"]*)"/.exec(chart.innerHTML || "")[1]);
const lineValues = (source) => {
  const m = /^\s*line\s*\[([^\]]*)\]/m.exec(source);
  assert.ok(m, `no line [..] in the chart source:\n${source}`);
  return m[1].split(",").map((s) => Number(s.trim()));
};
const closeTo = (got, want, tol, msg) => {
  assert.equal(got.length, want.length, `${msg}: count`);
  got.forEach((v, i) => assert.ok(Math.abs(v - want[i]) <= tol, `${msg}[${i}]: ${v} vs ${want[i]}`));
};
async function showLoop(files, doc = LOOP_DOC) {
  const { app, plugin } = await loaded(files);
  await openDoc(app, doc);
  await plugin.openViewPanel();
  await loopSettle();
  return { app, plugin };
}

// Adversarial where: `type: loop` falls into "no view for this type", or the
// match is loose (`loops`, a `type: loop` line in the body) and draws a chart
// view for a document that is not a loop.
test("viewFor names a document of type loop and no look-alike", () => {
  const cases = [
    ["plain", "---\ntype: loop\n---\nbody\n", "loop"],
    ["quoted", "---\ntype: \"loop\"\n---\nbody\n", "loop"],
    ["CRLF with a byte-order mark", "﻿---\r\ntype: loop\r\n---\r\nbody\r\n", "loop"],
    ["a longer type word", "---\ntype: loops\n---\nbody\n", null],
    ["another type", "---\ntype: lesson\n---\nbody\n", null],
    ["type line in the body only", "# Heading\n\ntype: loop\n", null],
  ];
  for (const [name, text, want] of cases) assert.equal(CompassReview.viewFor(text), want, name);
});

// Adversarial where: the reading is taken from the wrong field (reading_before
// gives 52 points, not 50), a run with `reading_after: null` is counted, a
// reading of 0 is dropped as falsy, or costs fall out of step with readings.
test("parseLedger reads LOOP-001's 50 readings and their costs, in order, from its 52 run records", () => {
  const got = CompassReview.parseLedger(LEDGER_FIX);
  assert.equal(LOOP_EXPECT.runRecords, 52);
  assert.equal(got.readings.length, 50);
  assert.deepEqual(got.readings, LOOP_EXPECT.readings);
  assert.equal(got.readings[got.readings.length - 1], 0, "the last reading is the real 0");
  closeTo(got.costs, LOOP_EXPECT.costs, 1e-12, "costs");
  assert.equal(got.skipped, 0);
});

// Adversarial where: records that are not runs (a transition or a review that
// happens to carry reading_after), a run with no value, a zero, a missing cost,
// or a non-integer reading are taken for or dropped from the readings.
test("parseLedger takes only run records that carry a numeric reading_after value", () => {
  const text = ledgerOf([
    runLine(10, 0.5),
    JSON.stringify({ type: "transition", reading_after: { value: 999 }, cost_usd: 7 }),
    runLine(null, 0.2, { reading_before: { value: 55 } }),
    runLine(0, 0),
    JSON.stringify({ type: "run", reading_after: { value: 7 } }),
    JSON.stringify({ type: "rerun", reading_after: { value: 888 }, cost_usd: 9 }),
    JSON.stringify({ type: "run", reading_after: { items_count: 3 }, cost_usd: 1 }),
    runLine(4.5, 0.25),
  ]);
  const got = CompassReview.parseLedger(text);
  assert.deepEqual(got.readings, [10, 0, 7, 4.5]);
  assert.deepEqual(got.costs, [0.5, 0, 0, 0.25]);
  assert.equal(got.skipped, 0);
});

// Adversarial where: one bad line aborts the whole parse (JSON.parse throws), a
// valid-but-not-an-object line (`null`, a number, an array) crashes or is
// taken as a record, a truncated last line is lost uncounted, or blank lines
// are counted as skipped; the good lines around the bad one must survive in order.
test("parseLedger skips malformed lines, counts them, and keeps the good lines around them", async (t) => {
  const good = [runLine(1, 0.1), runLine(2, 0.2), runLine(3, 0.3)];
  const rows = [
    ["a truncated record in the middle", [good[0], '{"type":"run","reading_after":{"value":9}', good[1], good[2]], 1],
    ["prose", [good[0], "not json at all", good[1], good[2]], 1],
    ["a JSON array", [good[0], "[1,2,3]", good[1], good[2]], 1],
    ["JSON null", [good[0], "null", good[1], good[2]], 1],
    ["a JSON number", [good[0], "42", good[1], good[2]], 1],
    ["a JSON string", [good[0], '"a string"', good[1], good[2]], 1],
    ["blank and whitespace-only lines are not malformed", [good[0], "", "   ", good[1], good[2]], 0],
    ["one first, one middle, one last", ["{broken", good[0], good[1], "}", good[2], "tail"], 3],
  ];
  for (const [name, lines, skipped] of rows) {
    await t.test(name, () => {
      const got = CompassReview.parseLedger(ledgerOf(lines));
      assert.deepEqual(got.readings, [1, 2, 3]);
      assert.deepEqual(got.costs, [0.1, 0.2, 0.3]);
      assert.equal(got.skipped, skipped);
    });
  }
  await t.test("a last line cut short with no line end is counted", () => {
    const got = CompassReview.parseLedger(good.join("\n") + '\n{"type":"run","reading_af');
    assert.deepEqual(got.readings, [1, 2, 3]);
    assert.equal(got.skipped, 1);
  });
  await t.test("CRLF line ends read like LF", () => {
    const got = CompassReview.parseLedger(good.join("\r\n") + "\r\n");
    assert.deepEqual(got.readings, [1, 2, 3]);
    assert.equal(got.skipped, 0);
  });
  await t.test("a ledger of nothing but garbage has no readings and counts every line", () => {
    const got = CompassReview.parseLedger(ledgerOf(["x", "{", "]"]));
    assert.deepEqual([got.readings, got.costs, got.skipped], [[], [], 3]);
  });
  await t.test("an empty ledger", () => {
    assert.deepEqual(CompassReview.parseLedger(""), { readings: [], costs: [], skipped: 0 });
  });
});

// Adversarial where: the chart source holds a different series than the ledger
// (readings reordered, truncated, or taken from reading_before), the cost axis
// is not labelled an estimate, an axis range excludes a value, a small cost is
// written in exponent notation Mermaid cannot read, or a ledger with no reading
// yields a source with an empty `line []`.
test("loopChartSource draws the ledger series in order, labels cost an estimate, and returns null with no reading", async (t) => {
  const ledger = CompassReview.parseLedger(LEDGER_FIX);
  await t.test("the reading chart holds the 50 readings in order inside its y-axis range", () => {
    const src = CompassReview.loopChartSource(ledger, "reading");
    assert.match(src, /^\s*xychart-beta\s*$/m);
    assert.deepEqual(lineValues(src), LOOP_EXPECT.readings);
    const range = /y-axis[^\n]*?(-?\d+(?:\.\d+)?)\s*-->\s*(-?\d+(?:\.\d+)?)/.exec(src);
    if (range) {
      assert.ok(Number(range[1]) <= 0 && Number(range[2]) >= 75, `y range ${range[1]}..${range[2]} excludes 0..75`);
    }
  });
  await t.test("the cost chart holds the 50 costs in order and its y-axis says estimate", () => {
    const src = CompassReview.loopChartSource(ledger, "cost");
    closeTo(lineValues(src), LOOP_EXPECT.costs, 1e-3, "cost line");
    const yAxis = src.split("\n").find((l) => /^\s*y-axis/.test(l));
    assert.ok(yAxis, `no y-axis line:\n${src}`);
    assert.match(yAxis, /estimate/i);
    const range = /(-?\d+(?:\.\d+)?)\s*-->\s*(-?\d+(?:\.\d+)?)/.exec(yAxis);
    if (range) assert.ok(Number(range[1]) <= 0.1254 && Number(range[2]) >= 0.1687, `y range ${range[1]}..${range[2]} excludes the costs`);
  });
  await t.test("a cost too small for plain notation is not written in exponent form", () => {
    const tiny = CompassReview.parseLedger(ledgerOf([runLine(5, 1e-7), runLine(4, 0.3)]));
    assert.doesNotMatch(CompassReview.loopChartSource(tiny, "cost"), /\d[eE][-+]?\d/);
  });
  await t.test("one reading still draws", () => {
    const one = CompassReview.parseLedger(ledgerOf([runLine(75, 0.2)]));
    assert.deepEqual(lineValues(CompassReview.loopChartSource(one, "reading")), [75]);
  });
  await t.test("no reading gives null for both kinds", () => {
    const none = CompassReview.parseLedger(ledgerOf([runLine(null, 0)]));
    assert.equal(CompassReview.loopChartSource(none, "reading"), null);
    assert.equal(CompassReview.loopChartSource(none, "cost"), null);
  });
});

// Adversarial where: the view never calls loadMermaid/mermaid.render, draws one
// chart instead of two, hands render a source other than the one the pure
// function builds, reuses a render id (Mermaid then draws into the wrong
// element), or leaves a loop's view mixed with a plan board or a skipped notice
// when nothing was skipped.
test("the loop view draws a reading chart and a cost chart for LOOP-001 through Obsidian's Mermaid", async () => {
  const { app } = await showLoop({ [LOOP_DOC]: LOOP_INDEX, [LOOP_LEDGER]: LEDGER_FIX });
  const view = viewEl(app);
  assert.equal(view.querySelectorAll(".compass-loop-view").length, 1);
  assert.equal(view.querySelectorAll(".compass-plan-board").length, 0);
  assert.equal(view.querySelectorAll(".compass-loop-skipped").length, 0);
  assert.deepEqual(chartsOf(app).map((c) => c.dataset.kind).sort(), ["cost", "reading"]);
  const ledger = CompassReview.parseLedger(LEDGER_FIX);
  for (const kind of ["reading", "cost"]) {
    assert.equal(drawnSource(chartOf(app, kind)), CompassReview.loopChartSource(ledger, kind), kind);
  }
  assert.deepEqual(lineValues(drawnSource(chartOf(app, "reading"))), LOOP_EXPECT.readings);
  assert.equal(mermaidState.calls.length, 2);
  const ids = mermaidState.calls.map((c) => c.id);
  assert.equal(new Set(ids).size, 2, "render ids are distinct");
  for (const id of ids) assert.match(id, /^[A-Za-z][\w-]*$/, "a render id is a valid element id");
});

// Adversarial where: malformed lines are skipped silently (no count shown), the
// count is off by one at the smallest and a larger value, or a skipped line
// stops the charts from drawing.
test("the loop view shows how many ledger lines were skipped and still draws the charts", async (t) => {
  for (const [name, tail, count] of [["one line, no line end", "{broken", 1], ["two lines", "garbage\n{also broken\n", 2]]) {
    await t.test(name, async () => {
      const { app } = await showLoop({ [LOOP_DOC]: LOOP_INDEX, [LOOP_LEDGER]: LEDGER_FIX + tail });
      const notes = viewEl(app).querySelectorAll(".compass-loop-skipped");
      assert.equal(notes.length, 1);
      assert.match(textOf(notes[0]), new RegExp(`\\b${count}\\b`));
      assert.deepEqual(lineValues(drawnSource(chartOf(app, "reading"))), LOOP_EXPECT.readings);
    });
  }
});

// Adversarial where: a ledger with no reading draws an empty chart or an
// error, calls Mermaid with a null source, stacks several lines, or (missing
// file) leaves the panel blank because the read threw.
test("a ledger with no run that carries a reading draws one plain line and no chart", async (t) => {
  const transition = JSON.stringify({ type: "transition", from: "idle", to: "sensing" });
  const rows = [
    ["an empty ledger file", ""],
    ["no ledger file", null],
    ["transitions and reviews only", ledgerOf([transition, JSON.stringify({ type: "review" })])],
    ["garbage only", ledgerOf(["{", "nope"])],
    ["runs that all carry no reading", ledgerOf([runLine(null, 0), runLine(null, 0)])],
  ];
  for (const [name, ledger] of rows) {
    await t.test(name, async () => {
      const files = { [LOOP_DOC]: LOOP_INDEX };
      if (ledger !== null) files[LOOP_LEDGER] = ledger;
      const { app } = await showLoop(files);
      const notes = viewEl(app).querySelectorAll(".compass-view-note");
      assert.equal(notes.length, 1);
      assert.match(notes[0].text, /run/i);
      assert.equal(chartsOf(app).length, 0);
      assert.equal(mermaidState.calls.length, 0);
    });
  }
});

// Adversarial where: the ledger path is joined wrongly (`./ledger.jsonl` for a
// document at the vault root misses the store), the view reads a parent's or a
// sibling loop's ledger, or assumes the document is named index.md.
test("the loop view reads the ledger in the loop document's own folder", async (t) => {
  const ledgerA = ledgerOf([runLine(1, 0.1), runLine(2, 0.1), runLine(3, 0.1)]);
  const decoys = {
    ".compass/loops/ledger.jsonl": ledgerOf([runLine(11, 0.1), runLine(12, 0.1)]),
    ".compass/loops/LOOP-002-other/ledger.jsonl": ledgerOf([runLine(21, 0.1)]),
  };
  await t.test("beside index.md, with a parent's and a sibling's ledger present", async () => {
    const { app } = await showLoop({ [LOOP_DOC]: loopDoc(), [LOOP_LEDGER]: ledgerA, ...decoys });
    assert.deepEqual(lineValues(drawnSource(chartOf(app, "reading"))), [1, 2, 3]);
  });
  await t.test("a loop document at the vault root reads the root ledger", async () => {
    const { app } = await showLoop({ "loop.md": loopDoc(), "ledger.jsonl": ledgerA, ...decoys }, "loop.md");
    assert.deepEqual(lineValues(drawnSource(chartOf(app, "reading"))), [1, 2, 3]);
  });
  await t.test("a loop document not named index.md", async () => {
    const { app } = await showLoop({ "loops/L3/notes.md": loopDoc(), "loops/L3/ledger.jsonl": ledgerA, ...decoys }, "loops/L3/notes.md");
    assert.deepEqual(lineValues(drawnSource(chartOf(app, "reading"))), [1, 2, 3]);
  });
});

// Adversarial where: a Mermaid that fails to load or to render throws out of
// the draw, so the panel is left blank or with a half-built view instead of a
// plain line saying the chart could not be drawn.
test("when Obsidian's Mermaid fails to load or render, the loop view says so in one plain line", async (t) => {
  for (const [name, set] of [
    ["loadMermaid rejects", () => { mermaidState.loadError = new Error("no mermaid"); }],
    ["mermaid.render rejects", () => { mermaidState.renderError = new Error("parse error"); }],
  ]) {
    await t.test(name, async () => {
      const seen = console.error;
      console.error = () => {};
      try {
        set();
        const { app } = await showLoop({ [LOOP_DOC]: LOOP_INDEX, [LOOP_LEDGER]: LEDGER_FIX });
        const notes = viewEl(app).querySelectorAll(".compass-view-note");
        assert.equal(notes.length, 1);
        assert.match(notes[0].text, /chart/i);
        assert.equal(chartsOf(app).filter((c) => c.innerHTML).length, 0, "no svg is shown");
      } finally {
        console.error = seen;
      }
    });
  }
});

// Adversarial where: the redraw signature ignores the ledger (the loop document
// is unchanged, so a run appended by the loop never shows), a redraw stacks a
// second pair of charts, or a redraw reuses a render id.
test("reopening a loop after its ledger grew draws the new run once, with fresh render ids", async () => {
  const before = ledgerOf([runLine(5, 0.1), runLine(4, 0.1), runLine(3, 0.1)]);
  const { app } = await showLoop({ [LOOP_DOC]: loopDoc(), [LOOP_LEDGER]: before });
  assert.deepEqual(lineValues(drawnSource(chartOf(app, "reading"))), [5, 4, 3]);
  app.store.set(LOOP_LEDGER, before + runLine(2, 0.1) + "\n");
  await openDoc(app, LOOP_DOC);
  await loopSettle();
  assert.equal(chartsOf(app).length, 2, "one pair of charts, not two");
  assert.deepEqual(lineValues(drawnSource(chartOf(app, "reading"))), [5, 4, 3, 2]);
  const ids = mermaidState.calls.map((c) => c.id);
  assert.equal(new Set(ids).size, ids.length, `render ids repeat: ${ids.join(", ")}`);
});

// Adversarial where: a slow render that finishes after the human moved to
// another document lands its charts under that document's view.
test("a chart render that finishes after another document was opened draws nothing into the new view", async () => {
  let release;
  mermaidState.renderGate = new Promise((r) => { release = r; });
  const { app, plugin } = await loaded({ [LOOP_DOC]: LOOP_INDEX, [LOOP_LEDGER]: LEDGER_FIX, "notes.md": "# Plain notes\n" });
  await openDoc(app, LOOP_DOC);
  plugin.openViewPanel();
  await loopSettle();
  assert.ok(mermaidState.calls.length > 0, "the render began");
  await openDoc(app, "notes.md");
  release();
  await loopSettle();
  assert.equal(chartsOf(app).length, 0);
  assert.equal(viewEl(app).querySelectorAll(".compass-loop-view").length, 0);
  assert.equal(viewEl(app).querySelectorAll(".compass-view-note").length, 1);
});

// ---- a loop's charts: values the ledger can hold that the chart source must survive ----

const ledgerFile = (p = LOOP_LEDGER) => ({ path: p, basename: "ledger", extension: "jsonl" });
const seriesOf = (values) => ({ readings: values, costs: values.map(() => 0.1), skipped: 0 });
const yAxisOf = (source) => {
  const m = /^\s*y-axis\s+"[^"]*"\s+(\S+)\s+-->\s+(\S+)/m.exec(source);
  assert.ok(m, `no y-axis in the chart source:\n${source}`);
  return [m[1], m[2]];
};

// Adversarial where: a finite but extreme reading (1e21 and up, where
// Number#toFixed switches to exponent notation) or a span that overflows to
// Infinity reaches the Mermaid source as `1e+21`, `NaN` or `Infinity`, which
// Mermaid cannot read, so one outlier run costs the human both charts; a series
// of tiny values rounds to an axis that reads `0 --> 0`.
test("loopChartSource writes every number in plain decimal notation with an axis that has a span", async (t) => {
  const rows = [
    ["a reading at 1e21, the first exponent-notation value", [3, 1e21]],
    ["a reading at 1e300", [1e300]],
    ["readings at both extremes of a double, the span overflows", [-1e308, 1e308]],
    ["two readings at the top of a double", [1.7e308, 1.7e308]],
    ["a series of readings below the six decimals the source keeps", [5e-7, 4e-7]],
  ];
  for (const [name, values] of rows) {
    for (const kind of ["reading", "cost"]) {
      await t.test(`${name} (${kind})`, () => {
        const ledger = kind === "reading" ? seriesOf(values) : { readings: values.map(() => 1), costs: values, skipped: 0 };
        const source = CompassReview.loopChartSource(ledger, kind);
        assert.doesNotMatch(source, /\d[eE][-+]?\d|NaN|Infinity/, source);
        const [low, high] = yAxisOf(source).map(Number);
        assert.ok(Number.isFinite(low) && Number.isFinite(high) && low < high, `y-axis ${low} --> ${high}`);
      });
    }
  }
});

// Adversarial where: the min/max over a very long series is taken by spreading
// it into arguments, which throws RangeError past the engine's argument limit,
// and a ledger of many runs makes the source grow faster than the runs do.
test("loopChartSource handles a ledger of thousands of runs without throwing and with a source linear in the runs", async (t) => {
  for (const runs of [5000, 200000]) {
    await t.test(`${runs} runs`, () => {
      const values = Array.from({ length: runs }, (_, i) => (i * 7) % 100);
      const source = CompassReview.loopChartSource(seriesOf(values), "reading");
      assert.ok(source.length < 12 * runs + 300, `source is ${source.length} characters`);
      assert.equal(lineValues(source).length, runs);
      assert.equal(source.split("\n").length, 5);
    });
  }
  await t.test("the 20000-line ledger is parsed and drawn through the view as one source per chart", async () => {
    const lines = Array.from({ length: 20000 }, (_, i) => runLine(i % 50, 0.01));
    const began = Date.now();
    const { app } = await showLoop({ [LOOP_DOC]: loopDoc(), [LOOP_LEDGER]: ledgerOf(lines) });
    assert.ok(Date.now() - began < 5000, "the draw took over five seconds");
    assert.equal(mermaidState.calls.length, 2);
    assert.equal(lineValues(drawnSource(chartOf(app, "reading"))).length, 20000);
  });
});

// Adversarial where: a string from the ledger (run id, outcome, timestamp) with
// quotes, newlines, a Mermaid line of its own, or markup reaches the Mermaid
// source or the panel DOM, so a run record could add a series or an element.
test("ledger strings with quotes, newlines, Mermaid lines and markup reach neither the chart source nor the panel", async () => {
  const hostile = {
    run_id: 'RUN"\n    line [999]\n<script>alert(1)</script>',
    outcome: '"]\n    title "pwned"\n<img src=x onerror=alert(1)>',
    ts: "</svg><script>alert(2)</script>",
    note: 'x-axis "evil" 1 --> 2',
  };
  const ledger = ledgerOf([runLine(3, 0.2, hostile), runLine(4, 0.3, hostile), "<b>not json</b>"]);
  const { app } = await showLoop({ [LOOP_DOC]: loopDoc(), [LOOP_LEDGER]: ledger });
  for (const kind of ["reading", "cost"]) {
    const source = drawnSource(chartOf(app, kind));
    assert.equal(source.split("\n").length, 5, source);
    assert.doesNotMatch(source, /pwned|evil|alert|999|script/);
    assert.doesNotMatch(chartOf(app, kind).innerHTML, /alert|script|onerror|pwned/);
  }
  assert.deepEqual(lineValues(drawnSource(chartOf(app, "reading"))), [3, 4]);
  assert.doesNotMatch(textOf(viewEl(app)), /alert|script|onerror|pwned|<b>/);
  assert.equal(viewEl(app).querySelectorAll(".compass-loop-chart").length, 2);
});

// Adversarial where: a value that is not a number but coerces to one ("5", true,
// [5]) is charted, or one bad field among good ones drops the whole run; a cost
// of the wrong type must leave the reading in and give it cost 0.
test("parseLedger takes a reading or a cost only when it is a number", async (t) => {
  const run = (after, cost) => JSON.stringify({ type: "run", reading_after: after, cost_usd: cost });
  const rows = [
    ["value as a string", run({ value: "5" }, 0.1), []],
    ["value true", run({ value: true }, 0.1), []],
    ["value an array", run({ value: [5] }, 0.1), []],
    ["value an object", run({ value: { v: 5 } }, 0.1), []],
    ["value the string NaN", run({ value: "NaN" }, 0.1), []],
    ["reading_after a bare number", run(5, 0.1), []],
    ["reading_after a string", run("5", 0.1), []],
    ["reading_after an array", run([5], 0.1), []],
    ["value 1e999, which JSON reads as Infinity", '{"type":"run","reading_after":{"value":1e999},"cost_usd":0.1}', []],
    ["a good reading with a string cost", run({ value: 6 }, "0.9"), [[6, 0]]],
    ["a good reading with a cost of 1e999", '{"type":"run","reading_after":{"value":6},"cost_usd":1e999}', [[6, 0]]],
    ["a good reading with a null cost", run({ value: 6 }, null), [[6, 0]]],
  ];
  for (const [name, line, want] of rows) {
    await t.test(name, () => {
      const got = CompassReview.parseLedger(ledgerOf([runLine(1, 0.5), line, runLine(2, 0.25)]));
      const pairs = got.readings.map((r, i) => [r, got.costs[i]]);
      assert.deepEqual(pairs, [[1, 0.5], ...want, [2, 0.25]]);
      assert.equal(got.skipped, 0);
    });
  }
});

// Adversarial where: the ledger changes while a chart render is in flight and the
// slow render lands over, or beside, the redraw the change started, leaving the
// old series on screen or two pairs of charts.
test("a ledger modified while its charts are rendering ends with one pair of charts holding the new series", async () => {
  let release;
  mermaidState.renderGate = new Promise((r) => { release = r; });
  const before = ledgerOf([runLine(5, 0.1), runLine(4, 0.1)]);
  const { app, plugin } = await loaded({ [LOOP_DOC]: loopDoc(), [LOOP_LEDGER]: before });
  await openDoc(app, LOOP_DOC);
  plugin.openViewPanel();
  await loopSettle();
  assert.ok(mermaidState.calls.length > 0, "the first render began");
  app.store.set(LOOP_LEDGER, before + runLine(1, 0.1) + "\n");
  app.listeners.modify(ledgerFile());
  await loopSettle();
  release();
  await loopSettle();
  assert.equal(chartsOf(app).length, 2, "one pair of charts");
  assert.deepEqual(lineValues(drawnSource(chartOf(app, "reading"))), [5, 4, 1]);
  assert.equal(viewEl(app).querySelectorAll(".compass-loop-view").length, 1);
  const ids = mermaidState.calls.map((c) => c.id);
  assert.equal(new Set(ids).size, ids.length, `render ids repeat: ${ids.join(", ")}`);
});

// Adversarial where: the file-changed event for `ledger.jsonl` redraws nothing
// (the loop view goes stale while the loop runs), or redraws for any
// `ledger.jsonl` (a sibling loop's append re-renders this loop's charts).
test("a change to the open loop's ledger redraws its charts and a change to another loop's ledger does not", async () => {
  const sibling = ".compass/loops/LOOP-002-other/ledger.jsonl";
  const before = ledgerOf([runLine(5, 0.1), runLine(4, 0.1)]);
  const { app } = await showLoop({ [LOOP_DOC]: loopDoc(), [LOOP_LEDGER]: before, [sibling]: before });
  const drawn = mermaidState.calls.length;
  app.store.set(sibling, before + runLine(9, 0.1) + "\n");
  await app.listeners.modify(ledgerFile(sibling));
  await loopSettle();
  assert.equal(mermaidState.calls.length, drawn, "a sibling's ledger redrew this loop");
  app.store.set(LOOP_LEDGER, before + runLine(2, 0.1) + "\n");
  await app.listeners.modify(ledgerFile());
  await loopSettle();
  assert.deepEqual(lineValues(drawnSource(chartOf(app, "reading"))), [5, 4, 2]);
  assert.equal(chartsOf(app).length, 2);
});

// Adversarial where: a `ledger.jsonl` beside a spec, a plan or a research
// document, or a change to it, draws loop charts in a view that is not a loop's,
// calls Mermaid, or throws out of the file-changed handler.
test("a ledger beside a spec, plan or research document leaves that view without charts", async (t) => {
  const docs = {
    spec: "---\ntitle: S\ntype: spec\nstatus: draft\n---\n# S\n\n## Problem\nx\n",
    plan: "---\ntitle: P\ntype: plan\nstatus: draft\n---\n# P\n\n## Goal\nx\n\n## Phases\n\n### Phase 1: a\n- [ ] TASK-001: do it - files: [a], complexity: S, depends_on: none\n",
    research: "---\ntitle: R\ntype: research\nstatus: draft\n---\n# R\n\n## Question\nx\n\n## Findings\n1. **F** (confidence: high)\n",
  };
  for (const [type, text] of Object.entries(docs)) {
    await t.test(type, async () => {
      const dir = `.compass/${type}s/X-001-thing`;
      const { app } = await showLoop({ [`${dir}/index.md`]: text, [`${dir}/ledger.jsonl`]: ledgerOf([runLine(5, 0.1)]) }, `${dir}/index.md`);
      await app.listeners.modify(ledgerFile(`${dir}/ledger.jsonl`));
      await loopSettle();
      assert.equal(viewEl(app).querySelectorAll(".compass-loop-view").length, 0);
      assert.equal(viewEl(app).querySelectorAll(".compass-loop-chart").length, 0);
      assert.equal(mermaidState.calls.length, 0);
    });
  }
});

// ---- a view an agent writes ----
//
// A document whose properties hold `view: views/<name>.js` gets that script's
// drawing in the view panel instead of the view its `type:` picks. The value is
// a vault path, read as written with `app.vault.adapter.read`.
//
// Module shape: the script text is evaluated as a CommonJS-style module; its
// `module.exports` (or `module.exports.default`) is a function taking
// `{ app, file, text, el, open }`, may be async, and draws into `el`. `file` is
// the open document, `text` its text, `open(path, line)` opens a document at
// the 1-based `line` (Obsidian takes `line - 1`).
//
// DOM the panel draws, read by these tests:
//   .compass-view-custom   root of an agent's drawing, one per document in view;
//                          holds the script's output
//   .compass-view-script   the script's path as written, above the drawing
//   .compass-view-note     exactly one plain line naming the script when the
//                          path is refused or the script cannot be loaded or run
// Only a path that starts with `views/` and holds no `..` segment, backslash or
// drive is read; every other value is refused without reading anything.

const AGENT_OUT = "views/out.js";
const agentDoc = (view, type = "lesson", extra = "") => `---\ntype: ${type}\ntitle: D\n${view === null ? "" : `view: ${view}\n`}${extra}---\nbody of the document\n`;
const drawScript = (label) => `module.exports = ({ el, file }) => { el.createEl("div", { cls: "agent-out", text: "RAN-${label} " + file.path }); };`;
const customOf = (app) => viewEl(app).querySelectorAll(".compass-view-custom");
const agentOuts = (app) => viewEl(app).querySelectorAll(".agent-out");
const viewText = (app) => textOf(viewEl(app));
const agentNotes = (app) => viewEl(app).querySelectorAll(".compass-view-note");
async function showAgent(files, doc = "doc.md") {
  const r = await loaded(files);
  await openDoc(r.app, doc);
  await r.plugin.openViewPanel();
  await loopSettle();
  return r;
}
async function quietly(fn) {
  const seen = console.error;
  console.error = () => {};
  try { return await fn(); } finally { console.error = seen; }
}
// One plain line names the script, nothing of it ran, and a plan opened next
// still draws its board.
async function assertRefusedAndUsable(app, name, needle) {
  const notes = agentNotes(app);
  assert.equal(notes.length, 1, `${name}: one plain line`);
  assert.ok(notes[0].text.includes(needle), `${name}: the line names ${needle}, got "${notes[0].text}"`);
  assert.doesNotMatch(viewText(app), /RAN/, `${name}: nothing of the script ran`);
  await openDoc(app, P24);
  await loopSettle();
  assert.equal(viewEl(app).querySelectorAll(".compass-plan-board").length, 1, `${name}: the plan board draws next`);
  assert.equal(agentNotes(app).length, 0, `${name}: the line leaves with the document`);
}

// Adversarial where: the plugin hands the script the wrong argument (no `app`,
// `text` of another file, `file` missing), does not wait for an async script so
// the drawing is empty, or shows no path above the drawing.
test("a view: under views/ draws its output, awaits an async script and shows its path above the drawing", async () => {
  const doc = agentDoc(AGENT_OUT);
  const script = `module.exports = async ({ app, file, text, el, open }) => {
    const data = await app.vault.adapter.read("data.json");
    el.createEl("div", { cls: "agent-out", text: ["RAN", file.path, data, text.length, typeof open].join(" ") });
  };`;
  const { app } = await showAgent({ "doc.md": doc, [AGENT_OUT]: script, "data.json": "DATA-77" });
  const outs = agentOuts(app);
  assert.equal(outs.length, 1);
  assert.equal(outs[0].text, `RAN doc.md DATA-77 ${doc.length} function`);
  assert.equal(customOf(app).length, 1);
  assert.ok(customOf(app)[0].all().includes(outs[0]), "the output sits in the agent's root");
  const label = viewEl(app).querySelector(".compass-view-script");
  assert.ok(label && label.text.includes(AGENT_OUT), "the path is shown");
  const order = viewEl(app).all();
  assert.ok(order.indexOf(label) < order.indexOf(outs[0]), "the path comes before the drawing");
});

// Adversarial where: only `module.exports = function` loads, so a script
// exporting an async function or a default export draws nothing.
test("the exported function may be sync, async or the default export", async (t) => {
  const out = `el.createEl("div", { cls: "agent-out", text: "RAN" });`;
  const rows = [
    ["function", `module.exports = function ({ el }) { ${out} };`],
    ["async function", `module.exports = async function ({ el }) { await null; ${out} };`],
    ["default export", `module.exports = { default: ({ el }) => { ${out} } };`],
    ["default property of the exports object", `module.exports.default = async ({ el }) => { ${out} };`],
  ];
  for (const [name, script] of rows) {
    await t.test(name, async () => {
      const { app } = await showAgent({ "doc.md": agentDoc(AGENT_OUT), [AGENT_OUT]: script });
      assert.equal(agentOuts(app).length, 1);
      assert.equal(agentNotes(app).length, 0);
    });
  }
});

// Adversarial where: `open` counts lines from 0 (the line lands one too low or
// high), a line of 1 becomes falsy and opens at the top by default, or `open`
// opens a different path than the one it was given.
test("open(path, line) opens the document at line - 1", async () => {
  const script = `module.exports = ({ el, open }) => {
    for (const [label, line] of [["seven", 7], ["one", 1]]) {
      const b = el.createEl("button", { text: label });
      b.onclick = () => open("notes.md", line);
    }
  };`;
  const { app } = await showAgent({ "doc.md": agentDoc(AGENT_OUT), [AGENT_OUT]: script, "notes.md": "# n\n" });
  for (const [label, line] of [["seven", 6], ["one", 0]]) {
    const before = app.opened.length;
    await clickOn(viewEl(app).all().find((e) => e.tag === "button" && e.text === label));
    await settle();
    assert.equal(app.opened.length, before + 1, `${label}: one file opened`);
    const last = app.opened[app.opened.length - 1];
    assert.equal(last.path, "notes.md", label);
    assert.equal(last.state && last.state.eState && last.state.eState.line, line, label);
  }
});

// Adversarial where: a path that escapes `views/` (a parent segment, an
// absolute or drive path, a backslash, a sibling folder whose name merely starts
// with `views`) is read and run, so any document can run any vault file.
test("a view: path outside views/ is refused without running anything, one plain line naming it", async (t) => {
  const rows = [
    ["parent folder", "../x.js"],
    ["absolute", "/abs.js"],
    ["absolute inside a views folder", "/views/x.js"],
    ["drive letter", "C:/x.js"],
    ["parent segment after views/", "views/../secret.js"],
    ["backslash parent segment after views/", "views/..\\x.js"],
    ["a sibling folder starting with views", "views-old/x.js"],
    ["another folder", "notes/x.js"],
    ["no folder", "x.js"],
    ["vault folder above views", ".compass/views/x.js"],
  ];
  for (const [name, view] of rows) {
    await t.test(name, async () => {
      const base = view.split(/[\\/]/).pop();
      const files = { "doc.md": agentDoc(view), [P24]: PLAN_24, [view]: drawScript("decoy"), [base]: drawScript("decoy"), [`views/${base}`]: drawScript("decoy"), "secret.js": drawScript("decoy"), "abs.js": drawScript("decoy") };
      const { app } = await quietly(() => showAgent(files));
      await assertRefusedAndUsable(app, name, view);
    });
  }
});

// Adversarial where: a missing file, a syntax error, a throw, a rejected
// promise or an export that is not a function takes the panel down or leaves it
// blank with no word, or reports two lines.
test("a missing, unparsable, throwing, rejecting or non-function script gives one plain line naming it and leaves the panel usable", async (t) => {
  const rows = [
    ["missing file", null],
    ["syntax error", "module.exports = ({ el }) => {"],
    ["throws", `module.exports = () => { throw new Error("boom"); };`],
    ["throws while loading", `throw new Error("boom at load");`],
    ["rejected promise", `module.exports = async () => { await null; throw new Error("late boom"); };`],
    ["returns a rejected promise", `module.exports = () => Promise.reject(new Error("rejected"));`],
    ["exports a number", "module.exports = 42;"],
    ["exports nothing", "// no export\n"],
  ];
  for (const [name, script] of rows) {
    await t.test(name, async () => {
      const files = { "doc.md": agentDoc("views/bad.js"), [P24]: PLAN_24 };
      if (script !== null) files["views/bad.js"] = script;
      const { app } = await quietly(() => showAgent(files));
      await assertRefusedAndUsable(app, name, "views/bad.js");
    });
  }
});

// Adversarial where: any `view:` line, even one in the body or under another
// key, runs a script; or a document with a `view:` still draws its type's view;
// or a document with no `view:` loses its ready-made view.
test("a view: property replaces the type's view; no property, or a look-alike line, keeps it", async (t) => {
  const script = drawScript("v");
  const planWithView = (value) => PLAN_24.replace("type: plan\n", `type: plan\nview: ${value}\n`);
  const drawsScript = [
    ["plain", agentDoc(AGENT_OUT)],
    ["double-quoted", agentDoc(`"${AGENT_OUT}"`)],
    ["single-quoted", agentDoc(`'${AGENT_OUT}'`)],
    ["trailing spaces", agentDoc(`${AGENT_OUT}   `)],
    ["CRLF and a byte-order mark", "\uFEFF" + agentDoc(AGENT_OUT).replace(/\n/g, "\r\n")],
    ["among other properties, no type", `---\ntitle: D\nstatus: draft\nview: ${AGENT_OUT}\ntags: [a]\n---\nbody\n`],
    ["a plan, which has a ready-made view", planWithView(AGENT_OUT)],
  ];
  for (const [name, doc] of drawsScript) {
    await t.test(`draws the script: ${name}`, async () => {
      const { app } = await showAgent({ "doc.md": doc, [AGENT_OUT]: script });
      assert.equal(agentOuts(app).length, 1);
      assert.equal(viewEl(app).querySelectorAll(".compass-plan-board").length, 0, "no ready-made board beside it");
      assert.equal(agentNotes(app).length, 0);
    });
  }
  const keepsView = [
    ["a plan with no view", PLAN_24, ".compass-plan-board"],
    ["a view line in the body only", `---\ntype: plan\n---\n# P\n\nview: ${AGENT_OUT}\n`, ".compass-plan-board"],
    ["a longer key ending in view", planWithView(AGENT_OUT).replace("view:", "subview:"), ".compass-plan-board"],
    ["a lesson with no view", agentDoc(null), ".compass-view-note"],
    ["no frontmatter, a view line in the text", `# Notes\n\nview: ${AGENT_OUT}\n`, null],
  ];
  for (const [name, doc, want] of keepsView) {
    await t.test(`keeps its own view: ${name}`, async () => {
      const { app } = await showAgent({ "doc.md": doc, [AGENT_OUT]: script });
      assert.equal(agentOuts(app).length, 0, "the script did not run");
      assert.equal(customOf(app).length, 0);
      if (want) assert.ok(viewEl(app).querySelectorAll(want).length >= 1, `${want} drawn`);
    });
  }
});

// Adversarial where: a redraw (a save of the document, a layout change) appends
// a second drawing instead of replacing the first, or caches the script so an
// edited script keeps drawing its old output.
test("fifty redraws leave one drawing, and an edited script draws its new output in place of the old", async () => {
  const { app } = await showAgent({ "doc.md": agentDoc(AGENT_OUT), [AGENT_OUT]: drawScript("v1") });
  for (let i = 0; i < 50; i++) {
    app.store.set("doc.md", agentDoc(AGENT_OUT, "lesson", `tags: [t${i}]\n`));
    await app.listeners.modify(mdFile("doc.md"));
    app.wsListeners["layout-change"]();
    await loopSettle();
  }
  assert.equal(customOf(app).length, 1);
  assert.equal(agentOuts(app).length, 1);
  assert.equal(viewEl(app).querySelectorAll(".compass-view-script").length, 1);

  app.store.set(AGENT_OUT, drawScript("v2"));
  await app.listeners.modify(mdFile("doc.md"));
  await loopSettle();
  assert.equal(agentOuts(app).length, 1);
  assert.match(agentOuts(app)[0].text, /RAN-v2/);
  assert.doesNotMatch(viewText(app), /RAN-v1/);
});

// Adversarial where: a slow script of a document the human has left finishes
// later and draws over the document now in view, or two redraws that overlap a
// slow script each draw and leave two drawings.
test("a slow script finishing after the human moved on draws nothing, and overlapping redraws leave one drawing", async (t) => {
  const slow = `module.exports = async ({ app, el }) => { await app.gate.wait; el.createEl("div", { cls: "agent-out", text: "RAN-slow" }); };`;
  const files = { "doc.md": agentDoc("views/slow.js"), "views/slow.js": slow, "other.md": agentDoc(null) };
  await t.test("moved to another document", async () => {
    const { app, plugin } = await loaded(files);
    app.gate = gate();
    await openDoc(app, "doc.md");
    await plugin.openViewPanel();
    await loopSettle();
    await openDoc(app, "other.md");
    await loopSettle();
    app.gate.release();
    await loopSettle();
    assert.equal(agentOuts(app).length, 0);
    assert.doesNotMatch(viewText(app), /RAN-slow/);
    assert.match(viewText(app), /lesson/);
  });
  await t.test("two redraws while the script waits", async () => {
    const { app, plugin } = await loaded(files);
    app.gate = gate();
    await openDoc(app, "doc.md");
    await plugin.openViewPanel();
    await loopSettle();
    await app.listeners.modify(mdFile("doc.md"));
    await app.listeners.modify(mdFile("doc.md"));
    await loopSettle();
    app.gate.release();
    await loopSettle();
    assert.equal(agentOuts(app).length, 1);
    assert.equal(customOf(app).length, 1);
  });
});

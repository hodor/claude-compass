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
const stubs = {
  obsidian: { Plugin, ItemView, MarkdownView, Notice: class { constructor(m) { notices.push(m); } } },
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

// Tests for the Compass Review plugin, run with `node --test`. The `obsidian`
// and `electron` modules and the DOM helpers Obsidian adds are stubbed, so
// the plugin's request, panel, bar, verdict, rename and step-aside paths run
// without Obsidian.

const test = require("node:test");
const assert = require("node:assert/strict");
const Module = require("node:module");
const path = require("node:path");

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
const win = { minimized: 0, focused: 0, onTop: [], restore() {}, isMinimized: () => false,
  setAlwaysOnTop(v) { this.onTop.push(v); }, show() {}, focus() { this.focused++; }, minimize() { this.minimized++; } };
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
      on(name, fn) { listeners[name] = fn; },
    },
    workspace: {
      getLeavesOfType: (type) => (type === "markdown" ? leaves : panelLeaves.filter((l) => l.view && l.view.getViewType() === type)),
      getLeaf() {
        const leaf = { view: new MarkdownView(null), async openFile(f) { this.view.file = f; app.active = f; fire("file-open", f); fire("layout-change"); } };
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
      async openLinkText(link) {
        const f = app.vault.getAbstractFileByPath(link);
        if (!f) return;
        await this.getLeaf(false).openFile(f);
      },
      getActiveFile: () => app.active,
      setActiveLeaf(leaf) { if (leaf.view && leaf.view.file) app.active = leaf.view.file; },
      on(name, fn) { wsListeners[name] = fn; },
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

test.beforeEach(() => { notices.length = 0; win.minimized = 0; win.focused = 0; win.onTop = []; });

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

const panelView = (app) => (app.panelLeaves.find((l) => l.view) || {}).view || null;
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

// Adversarial where: Needs changes from the panel ignores `return: false` and
// steps Obsidian aside anyway, or writes the wrong verdict word.
test("return false keeps Obsidian in front after the verdict", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/2.request.json": req("2", "a.md", { return: false }) });
  await plugin.handler({ request: "tmp/review/2.request.json" });
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

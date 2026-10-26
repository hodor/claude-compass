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
  const listeners = {};
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
    "a.md": "x", "b.md": "y", "z.md": "q", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  assert.deepEqual(feedbackOf(cardFor(app, "1")), []);
  show(app, app.leaves[0], "b.md");
  typeInto(fileNoteIn(cardFor(app, "1")), "merge D-03");
  assert.deepEqual(feedbackOf(cardFor(app, "1")), ["b.md: merge D-03"]);
  typeInto(notesIn(cardFor(app, "1")), "overall note");
  assert.deepEqual(feedbackOf(cardFor(app, "1")), ["b.md: merge D-03"], "the notes field is not feedback");
  await app.listeners.modify(mdFile("z.md"));
  await app.listeners.modify(mdFile("z.md"));
  await app.listeners.modify(mdFile("a.md"));
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
  await app.listeners.modify(mdFile("z.md"));
  app.listeners.rename({ path: "b.md" }, "b.md");
  await plugin.recheck();
  assert.equal(app.panelLeaves.length, 0, "no panel conjured by events");
  await plugin.openPanel();
  assert.ok(feedbackOf(cardFor(app, "1")).includes("edited: z.md"));
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
test("markdown files modified while the review is pending land in edited, once each", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "z.md": "q", "tmp/review/1.request.json": req("1", "a.md") });
  await app.listeners.modify(mdFile("z.md"));
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await app.listeners.modify(mdFile("b.md"));
  await app.listeners.modify(mdFile("b.md"));
  await app.listeners.modify(mdFile("a.md"));
  await app.listeners.modify({ path: "data.json", basename: "data", extension: "json" });
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
    await app.listeners.modify(mdFile("b.md"));
    await sleep();
    assert.equal(changes(app).disabled, false);
  });
  await t.test("two reviews: an edit enables only the card it belongs to", async () => {
    const { app, plugin } = await setup();
    app.store.set("tmp/review/2.request.json", req("2", "b.md"));
    await plugin.handler({ request: "tmp/review/2.request.json" });
    await app.listeners.modify(mdFile("z.md"));
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
// belong to. An edit to a reviewed file belongs to that file's review; an
// edit to any other file belongs to the newest pending review (the top card),
// even after the older review's file is opened, and moves to the remaining
// review once the newest is answered.
test("with two reviews pending, an edit lands only in the review it belongs to", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "z.md": "q",
    "tmp/review/1.request.json": req("1", "a.md"), "tmp/review/2.request.json": req("2", "b.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await plugin.handler({ request: "tmp/review/2.request.json" });
  await app.listeners.modify(mdFile("z.md"));
  await app.listeners.modify(mdFile("a.md"));
  show(app, app.leaves[0], "a.md");
  await app.listeners.modify(mdFile("y.md"));
  await click(cardBtn(app, "2", "Approve"));
  await sleep();
  assert.deepEqual([...verdictOf(app, "tmp/review/2.verdict.json").edited].sort(), ["y.md", "z.md"], "other files' edits go to the newest review, whichever reviewed file is in view");
  await app.listeners.modify(mdFile("w.md"));
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  assert.deepEqual([...verdictOf(app, "tmp/review/1.verdict.json").edited].sort(), ["a.md", "w.md"], "a reviewed file's edit goes to its own review, and later edits to the one left");
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
// verdict when the resulting modify event fires while the verdict is built.
test("the save made for the verdict counts as the human's edit once; a clean save adds nothing", async (t) => {
  const run = async (fireModifyOnSave) => {
    const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md") });
    await plugin.handler({ request: "tmp/review/1.request.json" });
    const leaf = app.leaves[0];
    leaf.view.save = async () => { if (fireModifyOnSave) await app.listeners.modify(mdFile("a.md")); };
    await click(cardBtn(app, "1", "Approve"));
    await sleep();
    return verdictOf(app, "tmp/review/1.verdict.json");
  };
  await t.test("dirty document: modify fires during save", async () => {
    assert.deepEqual((await run(true)).edited, ["a.md"]);
  });
  await t.test("clean document: no modify event", async () => {
    assert.deepEqual((await run(false)).edited, []);
  });
});

// Adversarial where: a modify event arriving after the verdict is written
// throws or resurrects the review.
test("a modify event after the verdict is written is ignored and leaves no review behind", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  await app.listeners.modify(mdFile("a.md"));
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
  await app.listeners.modify(mdFile("b.md"));
  app.store.set("b2.md", app.store.get("b.md"));
  app.store.delete("b.md");
  app.listeners.rename({ path: "b2.md" }, "b.md");
  app.store.set("a2.md", app.store.get("a.md"));
  app.store.delete("a.md");
  app.listeners.rename({ path: "a2.md" }, "a.md");
  show(app, leaf, "b2.md");
  assert.equal(fileNoteIn(cardFor(app, "1")).value, "tidy", "the note follows the file");
  assert.deepEqual([...feedbackOf(cardFor(app, "1"))].sort(), ["b2.md: tidy", "edited: b2.md"]);
  await click(linkIn(cardFor(app, "1")));
  assert.ok(app.leaves.some((l) => l.view.file && l.view.file.path === "a2.md"), "the link opens the renamed reviewed file");
  await click(cardBtn(app, "1", "Approve"));
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.deepEqual(v.comments, [{ file: "b2.md", note: "tidy" }]);
  assert.deepEqual(v.edited, ["b2.md"]);
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
  await app.listeners.modify(mdFile("a.md"));
  assert.equal(notesIn(cardFor(app, "1")), field, "the notes field is the same element");
  assert.equal(field.value, "half a senten");
  show(app, app.leaves[0], "b.md");
  assert.notEqual(notesIn(cardFor(app, "1")), field, "the card was rebuilt for the new file");
  assert.equal(notesIn(cardFor(app, "1")).value, "half a senten", "the typed text is restored");
  assert.ok(thisFileIn(cardFor(app, "1")), "the note field for the file in view appears");
});

// Adversarial where: with many pending reviews the cards are not newest
// first, an answer removes a neighbour's card, or an edit is credited to every
// card instead of the one for that file (or the newest for any other file).
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
  await app.listeners.modify(mdFile("d7.md"));
  await app.listeners.modify(mdFile("other.md"));
  const edited = cards(app).filter((c) => feedbackOf(c).length > 0).map((c) => c.dataset.id).sort();
  assert.deepEqual(edited, ["07", "30"]);
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

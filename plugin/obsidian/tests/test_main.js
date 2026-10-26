// Tests for the Compass Review plugin, run with `node --test`. The `obsidian`
// and `electron` modules and the DOM helpers Obsidian adds are stubbed, so
// the plugin's request, bar, verdict, rename and step-aside paths run without
// Obsidian.

const test = require("node:test");
const assert = require("node:assert/strict");
const Module = require("node:module");
const path = require("node:path");

// ---- minimal DOM: just what the plugin touches ----
class El {
  constructor(tag, opts = {}) {
    this.tag = tag;
    this.cls = opts.cls || "";
    this.text = opts.text || "";
    this.type = opts.type;
    this.placeholder = opts.placeholder;
    this.value = "";
    this.dataset = {};
    this.children = [];
    this.parent = null;
    this.onclick = null;
    this.handlers = {};
  }
  addEventListener(type, fn) { (this.handlers[type] = this.handlers[type] || []).push(fn); }
  createEl(tag, opts) { const e = new El(tag, opts); e.parent = this; this.children.push(e); return e; }
  createSpan(opts) { return this.createEl("span", opts); }
  insertBefore(el, ref) {
    el.parent = this;
    const i = ref ? this.children.indexOf(ref) : -1;
    if (i < 0) this.children.push(el); else this.children.splice(i, 0, el);
  }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); this.parent = null; }
  all() { return [this, ...this.children.flatMap((c) => c.all())]; }
  querySelector(sel) { return this.all().slice(1).find((e) => e.cls.split(" ").includes(sel.slice(1))) || null; }
  querySelectorAll(sel) { return this.all().slice(1).filter((e) => e.cls.split(" ").includes(sel.slice(1))); }
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
}
class MarkdownView { constructor(file) { this.file = file; this.saved = 0; this.containerEl = new El("view"); this.containerEl.createEl("div", { cls: "view-content" }); } async save() { this.saved++; } }
const stubs = {
  obsidian: { Plugin, MarkdownView, Notice: class { constructor(m) { notices.push(m); } } },
  electron: { remote: { getCurrentWindow: () => win, app: { hide() { win.minimized++; } } } },
};
const origResolve = Module._resolveFilename;
Module._resolveFilename = function (req, ...rest) { return stubs[req] ? req : origResolve.call(this, req, ...rest); };
for (const [name, exp] of Object.entries(stubs)) require.cache[name] = { id: name, filename: name, loaded: true, exports: exp };

const CompassReview = require(path.join(__dirname, "..", "compass-review", "main.js"));

// ---- a fake app over an in-memory vault ----
function makeApp(files) {
  const store = new Map(Object.entries(files));
  const leaves = [];
  const listeners = {};
  const wsListeners = {};
  const app = {
    store,
    vault: {
      adapter: {
        async read(p) { if (!store.has(p)) throw new Error(`ENOENT ${p}`); return store.get(p); },
        async write(p, d) { store.set(p, d); },
        async exists(p) { return store.has(p) || [...store.keys()].some((k) => k.startsWith(p + "/")); },
        async list(dir) { return { files: [...store.keys()].filter((k) => path.posix.dirname(k) === dir), folders: [] }; },
      },
      getAbstractFileByPath(p) { return store.has(p) ? { path: p, basename: path.posix.basename(p, ".md") } : null; },
      on(name, fn) { listeners[name] = fn; },
    },
    workspace: {
      getLeavesOfType: () => leaves,
      getLeaf() { const leaf = { view: new MarkdownView(null), async openFile(f) { this.view.file = f; } }; leaves.push(leaf); return leaf; },
      setActiveLeaf() {},
      on(name, fn) { wsListeners[name] = fn; },
      onLayoutReady(fn) { this.ready = fn; },
    },
    listeners,
    wsListeners,
    leaves,
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
const bar = (app) => app.leaves.map((l) => l.view.containerEl.querySelector(".compass-review-bar")).find(Boolean);
const button = (b, text) => b.children.find((c) => c.tag === "button" && c.text === text);

test.beforeEach(() => { notices.length = 0; win.minimized = 0; win.focused = 0; win.onTop = []; });

test("a request opens the file, raises the window and shows the bar", async () => {
  const { app, plugin } = await loaded({ "specs/a.md": "x", "tmp/review/1.request.json": req("1", "specs/a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  assert.equal(app.leaves[0].view.file.path, "specs/a.md");
  assert.equal(win.focused, 1);
  assert.deepEqual(win.onTop, [true]);
  const b = bar(app);
  assert.ok(b, "bar shown");
  assert.equal(b.dataset.id, "1");
  assert.ok(button(b, "Approve") && button(b, "Needs changes"));
});

test("approve saves the editor, writes the verdict next to the request, and steps aside", async () => {
  const { app, plugin } = await loaded({ "specs/a.md": "x", ".compass/tmp/review/1.request.json": req("1", "specs/a.md") });
  await plugin.handler({ request: ".compass/tmp/review/1.request.json" });
  const b = bar(app);
  b.children.find((c) => c.tag === "input").value = "looks good";
  await button(b, "Approve").onclick();
  await new Promise((r) => setImmediate(r));
  const verdict = JSON.parse(app.store.get(".compass/tmp/review/1.verdict.json"));
  assert.equal(verdict.verdict, "approved");
  assert.equal(verdict.notes, "looks good");
  assert.equal(verdict.id, "1");
  assert.equal(app.leaves[0].view.saved, 1);
  assert.equal(win.minimized, 1);
  assert.equal(bar(app), undefined, "bar removed after the verdict");
});

test("return false keeps Obsidian in front after the verdict", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/2.request.json": req("2", "a.md", { return: false }) });
  await plugin.handler({ request: "tmp/review/2.request.json" });
  await button(bar(app), "Needs changes").onclick();
  await new Promise((r) => setImmediate(r));
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

test("a second request for the same file replaces the first", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "tmp/review/5.request.json": req("5", "a.md"), "tmp/review/6.request.json": req("6", "a.md") });
  await plugin.handler({ request: "tmp/review/5.request.json" });
  await plugin.handler({ request: "tmp/review/6.request.json" });
  assert.equal(bar(app).dataset.id, "6");
  assert.deepEqual([...plugin.pending.keys()], ["6"]);
});

test("a renamed file keeps its bar and the verdict names the new path", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "tmp/review/7.request.json": req("7", "a.md") });
  await plugin.handler({ request: "tmp/review/7.request.json" });
  app.leaves[0].view.file = { path: "b.md", basename: "b" };
  app.listeners.rename({ path: "b.md" }, "a.md");
  assert.ok(bar(app), "bar follows the rename");
  await button(bar(app), "Approve").onclick();
  await new Promise((r) => setImmediate(r));
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

// ---- review trail: the review stays in view while the human moves around the vault ----

const trailOf = (app) => app.leaves.map((l) => l.view.containerEl.querySelector(".compass-review-trail")).find(Boolean);
const barIn = (leaf) => leaf.view.containerEl.querySelector(".compass-review-bar");
const trailIn = (leaf) => leaf.view.containerEl.querySelector(".compass-review-trail");
const trailText = (t) => t.all().map((e) => e.text).join(" ");
const backOf = (t) => t.all().find((e) => e.tag === "button" && e.text === "Back to review");
const noteOf = (t) => t.querySelector(".compass-review-file-note");
const sleep = () => new Promise((r) => setImmediate(r));
const mdFile = (p) => ({ path: p, basename: path.posix.basename(p, ".md"), extension: "md" });
const go = (leaf, p) => { leaf.view.file = mdFile(p); };

// A text field reports its value through its handlers: the stub DOM has no
// events, so a test sets `.value` and calls whichever of `on<type>` or the
// addEventListener handlers the plugin attached, for both `input` and `change`.
function typeInto(el, value) {
  el.value = value;
  for (const type of ["input", "change"]) {
    if (typeof el["on" + type] === "function") el["on" + type]({ target: el });
    for (const fn of el.handlers[type] || []) fn({ target: el });
  }
}

const verdictOf = (app, p) => JSON.parse(app.store.get(p));

// Adversarial where: navigating away from the reviewed file in the same pane
// drops the review from view (no bar, no way back), or Back opens a new pane
// or the wrong file instead of restoring the reviewed one.
test("moving to another file shows a slim bar naming the review, and Back reopens the reviewed file in the same pane", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "tmp/review/1.request.json": req("1", "a.md", { title: "Alpha spec" }) });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const leaf = app.leaves[0];
  assert.equal(trailIn(leaf), null, "no trail on the reviewed file");
  go(leaf, "b.md");
  plugin.decorate();
  const trail = trailIn(leaf);
  assert.ok(trail, "slim bar on the linked file");
  assert.match(trailText(trail), /Alpha spec/);
  assert.equal(barIn(leaf), null, "the full bar belongs to the reviewed file only");
  assert.ok(noteOf(trail), "a note field for this file");
  await backOf(trail).onclick();
  plugin.decorate();
  assert.equal(leaf.view.file.path, "a.md");
  assert.equal(app.leaves.length, 1, "same pane, no new one");
  assert.equal(trailIn(leaf), null);
  assert.equal(barIn(leaf).dataset.id, "1");
});

// Adversarial where: a note typed on a linked file is lost when the human
// goes Back (it lived only in the removed field), a blanked-out note is
// still reported as an empty comment, or the verdict schema omits
// `comments`/`edited` when nothing was written.
test("notes on other files land in comments, empty ones are omitted, and the verdict carries edited", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "c.md": "z", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const leaf = app.leaves[0];
  go(leaf, "b.md");
  plugin.decorate();
  typeInto(noteOf(trailIn(leaf)), "fix the heading");
  go(leaf, "c.md");
  plugin.decorate();
  typeInto(noteOf(trailIn(leaf)), "temp");
  typeInto(noteOf(trailIn(leaf)), "");
  await backOf(trailIn(leaf)).onclick();
  plugin.decorate();
  await button(barIn(leaf), "Needs changes").onclick();
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
  await button(barIn(app.leaves[0]), "Approve").onclick();
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.deepEqual([...v.edited].sort(), ["a.md", "b.md"]);
  assert.equal(v.verdict, "approved");
  assert.deepEqual(v.comments, []);
});

// Adversarial where: Needs changes is enabled with nothing to say (the
// verdict would carry no feedback), stays disabled after a note on another
// file or an edit, or never re-disables when the note is cleared.
test("Needs changes stays disabled until a note, a note on another file, or an edit exists", async (t) => {
  const setup = async () => {
    const r = await loaded({ "a.md": "x", "b.md": "y", "tmp/review/1.request.json": req("1", "a.md") });
    await r.plugin.handler({ request: "tmp/review/1.request.json" });
    return { ...r, leaf: r.app.leaves[0] };
  };
  const changes = (leaf) => button(barIn(leaf), "Needs changes");

  await t.test("nothing written", async () => {
    const { leaf } = await setup();
    assert.equal(changes(leaf).disabled, true);
    assert.notEqual(button(barIn(leaf), "Approve").disabled, true, "Approve is never gated");
  });
  await t.test("a note on the bar, then cleared", async () => {
    const { leaf } = await setup();
    const input = barIn(leaf).children.find((c) => c.tag === "input");
    typeInto(input, "needs work");
    assert.equal(changes(leaf).disabled, false);
    typeInto(input, "");
    assert.equal(changes(leaf).disabled, true);
  });
  await t.test("a note on another file", async () => {
    const { plugin, leaf } = await setup();
    go(leaf, "b.md");
    plugin.decorate();
    typeInto(noteOf(trailIn(leaf)), "see this");
    await backOf(trailIn(leaf)).onclick();
    plugin.decorate();
    assert.equal(changes(leaf).disabled, false);
  });
  await t.test("an edit to a file", async () => {
    const { app, leaf } = await setup();
    await app.listeners.modify(mdFile("b.md"));
    await sleep();
    assert.equal(changes(leaf).disabled, false);
  });
});

// Adversarial where: a bar outlives its request (the request file was
// deleted or another surface answered it), or the sweep drops every bar
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

  app.store.delete("tmp/review/1.request.json");
  await plugin.recheck();
  assert.equal(barFor("1"), undefined, "request removed: bar gone");
  assert.ok(barFor("2"), "the other review keeps its bar");
  assert.deepEqual([...plugin.pending.keys()], ["2"]);

  go(app.leaves[0], "c.md");
  plugin.decorate();
  assert.ok(trailOf(app), "trail shown while review 2 is pending");
  app.store.set("tmp/review/2.verdict.json", "{}");
  await plugin.recheck();
  assert.equal(barFor("2"), undefined, "verdict exists: bar gone");
  assert.equal(trailOf(app), undefined, "no trail without a pending review");
  assert.equal(plugin.pending.size, 0);
});

// Adversarial where: with two reviews pending, the trail names the review of
// the pane the human came from (or the first tracked) rather than the one
// whose file was opened most recently.
test("with two reviews pending, the slim bar names the one whose file was opened last", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "c.md": "z",
    "tmp/review/1.request.json": req("1", "a.md", { title: "Alpha" }),
    "tmp/review/2.request.json": req("2", "b.md", { title: "Beta" }) });
  await plugin.handler({ request: "tmp/review/2.request.json" });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const [betaLeaf] = app.leaves;
  go(betaLeaf, "c.md");
  plugin.decorate();
  assert.match(trailText(trailIn(betaLeaf)), /Alpha/);
  assert.doesNotMatch(trailText(trailIn(betaLeaf)), /Beta/);

  go(betaLeaf, "b.md");
  if (app.wsListeners["file-open"]) app.wsListeners["file-open"](mdFile("b.md"));
  plugin.decorate();
  go(betaLeaf, "c.md");
  plugin.decorate();
  assert.match(trailText(trailIn(betaLeaf)), /Beta/);
  await backOf(trailIn(betaLeaf)).onclick();
  assert.equal(betaLeaf.view.file.path, "b.md");
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
// edit to any other file belongs to the review the slim bar names, the one
// opened last.
test("with two reviews pending, an edit lands only in the review it belongs to", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y", "z.md": "q",
    "tmp/review/1.request.json": req("1", "a.md"), "tmp/review/2.request.json": req("2", "b.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await plugin.handler({ request: "tmp/review/2.request.json" });
  await app.listeners.modify(mdFile("z.md"));
  await app.listeners.modify(mdFile("a.md"));
  const leafOf = (p) => app.leaves.find((l) => l.view.file.path === p);
  await button(barIn(leafOf("b.md")), "Approve").onclick();
  await sleep();
  assert.deepEqual([...verdictOf(app, "tmp/review/2.verdict.json").edited], ["z.md"], "the other file's edit goes to the review opened last");
  await button(barIn(leafOf("a.md")), "Approve").onclick();
  await sleep();
  assert.deepEqual([...verdictOf(app, "tmp/review/1.verdict.json").edited], ["a.md"], "a reviewed file's edit goes to its own review");
});

// Adversarial where: on the reviewed file of a second pending review, the
// slim bar of the first review is drawn on top of that review's own full bar,
// or the full bar is lost; and after that review is answered, the file never
// gets the first review's slim bar.
test("on the reviewed file of a second pending review the full bar shows with no trail, and the trail appears once it is answered", async () => {
  const { app, plugin } = await loaded({
    "a.md": "x", "b.md": "y",
    "tmp/review/1.request.json": req("1", "a.md", { title: "Alpha" }),
    "tmp/review/2.request.json": req("2", "b.md", { title: "Beta" }) });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  await plugin.handler({ request: "tmp/review/2.request.json" });
  assert.equal(app.leaves.length, 2, "each review opened in its own pane");
  const [alphaLeaf, betaLeaf] = app.leaves;
  go(alphaLeaf, "b.md");
  plugin.decorate();
  assert.equal(barIn(alphaLeaf).dataset.id, "2");
  assert.equal(trailIn(alphaLeaf), null, "no trail beside a full bar");
  go(alphaLeaf, "a.md");
  plugin.decorate();
  assert.equal(barIn(alphaLeaf).dataset.id, "1");

  go(betaLeaf, "a.md");
  go(alphaLeaf, "b.md");
  plugin.decorate();
  await button(barIn(alphaLeaf), "Approve").onclick();
  await sleep();
  assert.equal(barIn(alphaLeaf), null, "answered review: bar gone");
  assert.match(trailText(trailIn(alphaLeaf)), /Alpha/, "b.md now shows the remaining review's slim bar");
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
    await button(barIn(leaf), "Approve").onclick();
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
  await button(barIn(app.leaves[0]), "Approve").onclick();
  await sleep();
  await app.listeners.modify(mdFile("a.md"));
  assert.equal(plugin.pending.size, 0);
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
  await button(barIn(app.leaves[0]), "Approve").onclick();
  held.release();
  await racing;
  assert.equal(verdictOf(app, "tmp/review/1.verdict.json").verdict, "approved");
  assert.equal(plugin.pending.size, 0);
  assert.equal(barIn(app.leaves[0]), null);
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
  const click = button(barIn(app.leaves[0]), "Approve").onclick();
  app.store.delete("tmp/review/1.request.json");
  await plugin.recheck();
  held.release();
  await click;
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
  const b = barIn(app.leaves[0]);
  typeInto(b.children.find((c) => c.tag === "input"), "note");
  const first = button(b, "Approve").onclick();
  const second = button(b, "Needs changes").onclick();
  held.release();
  await Promise.all([first, second]);
  assert.equal(writes.length, 1);
});

// Adversarial where: a rename of a file that carries a note or an edit
// orphans them under the old path, or Back to review opens the old path of a
// renamed reviewed file.
test("renaming a noted and edited file moves both to the new path, and Back follows a renamed reviewed file", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "b.md": "y", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const leaf = app.leaves[0];
  go(leaf, "b.md");
  plugin.decorate();
  typeInto(noteOf(trailIn(leaf)), "tidy");
  await app.listeners.modify(mdFile("b.md"));
  app.store.set("b2.md", app.store.get("b.md"));
  app.store.delete("b.md");
  app.listeners.rename({ path: "b2.md" }, "b.md");
  app.store.set("a2.md", app.store.get("a.md"));
  app.store.delete("a.md");
  app.listeners.rename({ path: "a2.md" }, "a.md");
  go(leaf, "b2.md");
  plugin.decorate();
  assert.equal(noteOf(trailIn(leaf)).value, "tidy", "the note follows the file");
  await backOf(trailIn(leaf)).onclick();
  assert.equal(leaf.view.file.path, "a2.md");
  await button(barIn(leaf), "Approve").onclick();
  await sleep();
  const v = verdictOf(app, "tmp/review/1.verdict.json");
  assert.deepEqual(v.comments, [{ file: "b2.md", note: "tidy" }]);
  assert.deepEqual(v.edited, ["b2.md"]);
  assert.equal(v.file, "a2.md");
});

// Adversarial where: Back to review on a reviewed file that no longer exists
// throws out of the click handler or silently does nothing.
test("Back to review for a deleted reviewed file reports a failure and keeps the pane on the current file", async () => {
  const { app, plugin } = await loaded({ "a.md": "x", "b.md": "y", "tmp/review/1.request.json": req("1", "a.md") });
  await plugin.handler({ request: "tmp/review/1.request.json" });
  const leaf = app.leaves[0];
  go(leaf, "b.md");
  plugin.decorate();
  app.store.delete("a.md");
  await backOf(trailIn(leaf)).onclick();
  assert.match(notices.join(" "), /back to review failed - file not in this vault: a.md/);
  assert.equal(leaf.view.file.path, "b.md");
});

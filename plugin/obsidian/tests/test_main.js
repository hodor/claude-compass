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
  }
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

// ---- obsidian and electron stubs ----
const notices = [];
const win = { minimized: 0, focused: 0, onTop: [], restore() {}, isMinimized: () => false,
  setAlwaysOnTop(v) { this.onTop.push(v); }, show() {}, focus() { this.focused++; }, minimize() { this.minimized++; } };
class Plugin { constructor(app) { this.app = app; } registerEvent() {} registerObsidianProtocolHandler(name, fn) { this.handler = fn; } }
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
      on() {},
      onLayoutReady(fn) { this.ready = fn; },
    },
    listeners,
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

test("verdictPathFor swaps only the suffix", () => {
  assert.equal(CompassReview.verdictPathFor("x.request.json/tmp/review/1.request.json"), "x.request.json/tmp/review/1.verdict.json");
});

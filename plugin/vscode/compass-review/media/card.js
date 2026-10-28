// Draws the review cards from the state the extension posts and sends the
// human's actions back. The page holds no review state of its own: the extension
// posts the whole state when the page announces itself and after every change.
// The cards are built once per structure (reviews, files, titles) and filled in
// place afterwards, so a note being typed keeps its focus and caret.
(function () {
  "use strict";

  const vscode = acquireVsCodeApi();
  const root = document.getElementById("root");
  let cards = [];
  let signature = null;
  const built = new Map();

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function button(label, cls, onClick) {
    const b = el("button", cls, label);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  function buildCard(card) {
    const send = (msg) => vscode.postMessage(Object.assign({ id: card.id }, msg));
    const parts = { id: card.id, rows: [], outsideBlock: null, outsideNote: null };
    const node = el("div", "card");
    node.tabIndex = 0;
    node.dataset.id = card.id;
    parts.card = node;
    node.append(el("div", "question", card.question));

    if (card.project || card.session) {
      const who = el("div", "who");
      if (card.project) who.append(el("span", "label", "Project"), el("strong", "", card.project));
      if (card.session) who.append(el("span", "label", "Session"), el("code", "", card.session));
      node.append(who);
    }

    node.addEventListener("keydown", (event) => {
      const tag = String((event.target && event.target.tagName) || "").toLowerCase();
      if (tag === "textarea" || tag === "input") return;
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        send({ type: "next" });
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        send({ type: "prev" });
      }
    });

    const nav = el("div", "nav");
    parts.pos = el("span", "pos");
    parts.prev = button("Previous", "", () => send({ type: "prev" }));
    parts.next = button("Next", "primary", () => send({ type: "next" }));
    parts.nextUnread = button("Next unread", "", () => send({ type: "nextUnread" }));
    nav.append(parts.pos, parts.prev, parts.next, parts.nextUnread);
    node.append(nav);

    const rows = el("div", "rows");
    card.files.forEach((f, i) => {
      const row = el("div", "row");
      const mark = el("span", "mark");
      const body = el("div", "row-body");
      const link = el("a", "file", f.title);
      link.href = "#";
      body.append(link);
      if (f.why) body.append(el("div", "fine", f.why));
      const count = el("span", "fine row-count");
      const open = () => send({ type: "step", index: i });
      link.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        open();
      });
      row.addEventListener("click", open);
      row.append(mark, " ", body, " ", count);
      rows.append(row);
      parts.rows.push({ row, mark, count });
    });
    node.append(rows);

    parts.noteLabel = el("div", "label note-label");
    parts.note = el("textarea");
    parts.note.rows = 3;
    parts.note.placeholder = "Note on this file (optional)";
    parts.note.addEventListener("input", () => {
      const index = Number(parts.note.dataset.index);
      send({ type: "note", index, text: parts.note.value });
    });
    node.append(parts.noteLabel, parts.note);

    parts.feedbackBlock = el("div", "feedback-block");
    parts.feedback = el("ul", "feedback");
    parts.feedbackBlock.append(el("div", "label", "Feedback so far"), parts.feedback);
    node.append(parts.feedbackBlock);

    const foot = el("div", "foot");
    parts.summary = el("div", "fine");
    const actions = el("div", "actions");
    parts.approve = button("Approve", "primary", () => send({ type: "send", verdict: "approved" }));
    parts.changes = button("Needs changes", "", () => send({ type: "send", verdict: "changes" }));
    actions.append(parts.approve, parts.changes);
    foot.append(parts.summary, actions);
    foot.append(el("div", "fine", "Project is the folder holding the vault. Session is the first six characters of the Claude Code session id."));
    if (card.files.length > 1) {
      foot.append(el("div", "fine", "Left and right arrow keys move between files when this card has focus."));
    }
    node.append(foot);
    return parts;
  }

  // The "On this file" note for a markdown file outside the review, present
  // while that file is the active editor.
  function fillOutside(card, parts) {
    if (!card.outside) {
      if (parts.outsideBlock) parts.outsideBlock.remove();
      parts.outsideBlock = null;
      parts.outsideNote = null;
      return;
    }
    if (!parts.outsideBlock) {
      const block = el("div", "this-file");
      parts.outsideLabel = el("div", "label");
      parts.outsideNote = el("textarea");
      parts.outsideNote.rows = 2;
      parts.outsideNote.placeholder = "Note on this file for Claude";
      parts.outsideNote.addEventListener("input", () =>
        vscode.postMessage({ type: "outsideNote", id: card.id, path: parts.outsideNote.dataset.key, text: parts.outsideNote.value })
      );
      block.append(parts.outsideLabel, parts.outsideNote, el("div", "fine", "This file is not in the review; the note goes with your answer."));
      parts.card.insertBefore(block, parts.feedbackBlock);
      parts.outsideBlock = block;
    }
    parts.outsideLabel.textContent = `On this file: ${card.outside}`;
    if (parts.outsideNote.dataset.key !== card.outside) {
      parts.outsideNote.dataset.key = card.outside;
      parts.outsideNote.value = card.outsideNote;
    }
  }

  function fillCard(card, parts) {
    const n = card.files.length;
    parts.pos.textContent = `File ${card.index + 1} of ${n}`;
    parts.prev.disabled = card.index === 0;
    parts.next.disabled = card.index >= n - 1;
    parts.nextUnread.disabled = !card.canNextUnread;

    card.files.forEach((f, i) => {
      const { row, mark, count } = parts.rows[i];
      mark.textContent = f.read ? "read" : "unread";
      mark.classList.toggle("is-read", f.read);
      row.classList.toggle("is-current", i === card.index);
      count.textContent = f.hasNote ? "1 note" : "no note";
    });

    parts.noteLabel.textContent = card.noteLabel;
    const noteKey = `${card.id}:${card.index}`;
    if (parts.note.dataset.key !== noteKey) {
      parts.note.dataset.key = noteKey;
      parts.note.dataset.index = String(card.index);
      parts.note.value = card.note;
    }

    fillOutside(card, parts);

    parts.summary.textContent = card.summary;
    parts.feedback.textContent = "";
    for (const item of card.feedback) parts.feedback.append(el("li", "", item));
    parts.feedbackBlock.classList.toggle("is-empty", card.feedback.length === 0);
    parts.changes.disabled = !card.canChanges;
    parts.changes.title = parts.changes.disabled ? "Write a note first" : "";
  }

  function build() {
    const focused = [...built.values()].find((p) => p.card.contains(document.activeElement));
    built.clear();
    root.textContent = "";
    root.append(el("div", "heading", "Reviews waiting on you"));
    if (cards.length === 0) {
      root.append(el("div", "fine", "No reviews pending"));
      return;
    }
    for (const card of cards) {
      const parts = buildCard(card);
      built.set(card.id, parts);
      root.append(parts.card);
    }
    const again = focused && built.get(focused.id);
    if (again) again.card.focus();
  }

  function render() {
    const next = JSON.stringify(cards.map((c) => [c.id, c.question, c.project, c.session, c.files.map((f) => [f.title, f.why])]));
    if (next !== signature) {
      signature = next;
      build();
    }
    for (const card of cards) fillCard(card, built.get(card.id));
  }

  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (msg && msg.type === "state" && Array.isArray(msg.cards)) {
      cards = msg.cards;
      render();
    }
  });

  vscode.postMessage({ type: "ready" });
})();

# Actuator instructions

You are one step of a control loop. Make exactly one small, reviewable change that moves the project toward the end state, then stop.

## End state

No file tracked in this public repository holds private data: no deny-listed name, no path into the current user's home directory, no Claude Code session id inside a path, no credential token. Every finding the private data carried survives in neutral words.

## What to do

The Selected work names one item as `<path>:<category>:<term or pattern name>`.

1. Read the file and find every passage that matches the item: the deny-listed term, the home-directory path, the session id inside a path, or the token.
2. Copy first. Append to `~/.compass/private/compass/loop-redactions.md` (outside the repository) by editing its `<!-- new entries go above this line -->` marker: a heading naming the item, the file path, the line `HEAD at the time of the edit`, and each matched passage verbatim in a fenced block. If that edit is refused or the file is missing, stop without touching the repository.
3. Neutralise each passage in the repository file, following `golden/neutralise-a-private-name.md`:
   - denylist: a work or client project becomes "work project A", "work project B", ...; any other private project becomes "private project 1", "private project 2", .... The same name keeps the same placeholder everywhere in the file; reuse the placeholders the file already holds.
   - home-path: the home prefix becomes `~`, the rest of the path stays.
   - session-uuid: the id becomes `<session>`.
   - token: the token becomes `<redacted token>`.
4. Keep every number, finding, and the sentence's meaning. Re-read the file: the item's term or pattern no longer appears in it.

## What never to touch

- Any repository file other than the one named in the Selected work.
- Numbers, results, conclusions, and the owner's name and public email.
- `.claude/`, `.compass/tmp/`, and the deny-list file itself; the deny-list's terms are never written into the repository.
- Never delete a file or a passage without its verbatim copy in the private store.

# Verify with `compass doctor`: details

`review --install` copies the Compass Review plugin into the project's Obsidian vault when Obsidian has already opened one, and does nothing otherwise. Obsidian lets only the human turn a community plugin on: when doctor's `obsidian review` row WARNs, give him its steps as they are. Once the plugin is on, every document Compass asks him to review opens in Obsidian with Approve and Needs changes buttons. A vault opened in Obsidian after setup gets the plugin at the next `/compass:update` or self-update, or at once with `compass review --install`. The same command installs the Compass Review extension into VS Code and Cursor when `code` or `cursor` is on the PATH: the extension is installed once for the user, not per project, and a project sends its reviews there when its `plugin.yaml` sets `review_editor: vscode` or `review_editor: cursor`.

This is the install's acceptance check: `plugin.yaml`, automatic step registration, CLI completeness, `.claude/agents/`, `.claude/skills/`, and `.compass/meta/lessons-catalog.yaml` in one pass, exiting 1 on any FAIL. A FAIL means setup did not fully land - fix the named defect (doctor prints the command) before moving on to vision capture. For a human skimming the report without running the command, the same six checks restated:

- [ ] `.compass/meta/plugin.yaml` exists with `name`, `version`, `source`, `installed_at`.
- [ ] Hooks registered in `.claude/settings.json` (a bare `.claude/hooks/hooks.json` is not enough).
- [ ] `.claude/cli/` has a module for every command `maincli.py` declares.
- [ ] `.claude/agents/` has 13 Compass agents.
- [ ] `.claude/skills/` populated.
- [ ] `.compass/meta/lessons-catalog.yaml` exists.

Two checks doctor doesn't cover, also worth confirming: `.claude/rules/` has 4 rule files, and `.compass/index.md` / `.compass/active.md` exist.

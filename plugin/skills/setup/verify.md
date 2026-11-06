# Verify with `compass doctor`: details

Reviews open in one editor per project, chosen by one rule for delivery, update and doctor: the `review_editor` line in `.compass/meta/plugin.yaml` (`obsidian`, `vscode` or `cursor`); with no line, the first editor that is ready, else the first that can be installed (Obsidian when the project has a `.obsidian/` folder, else an editor whose command is on the PATH). `compass review --editor <name>` writes or replaces that line and sets the editor up: it installs the VS Code or Cursor extension (once for the user, not per project), or for Obsidian creates `.compass/.obsidian/` when no vault holds the project and installs and enables the plugin. Obsidian lists a vault only after the human has opened it once, so when Obsidian is the editor and does not list the vault, the command's last line and doctor's `review editor` row carry the step to give him as it is: "In Obsidian: Open folder as vault, `<path>`, then turn on Compass Review". Obsidian also lets only the human turn a community plugin on: when doctor's `obsidian review` row WARNs, give him its steps as they are. Once the plugin is on, every document Compass asks him to review opens in Obsidian with Approve and Needs changes buttons.

`compass review --install` installs into every editor; an update runs `compass review --install --selected`, which leaves VS Code and Cursor alone unless one is the project's editor. A review of a document installs the add-on of the selected editor first and prints `not configured: <why>` when it cannot.

This is the install's acceptance check: `plugin.yaml`, automatic step registration, CLI completeness, `.claude/agents/`, `.claude/skills/`, and `.compass/meta/lessons-catalog.yaml` in one pass, exiting 1 on any FAIL. A FAIL means setup did not fully land - fix the named defect (doctor prints the command) before moving on to vision capture. For a human skimming the report without running the command, the same six checks restated:

- [ ] `.compass/meta/plugin.yaml` exists with `name`, `version`, `source`, `installed_at`.
- [ ] Hooks registered in `.claude/settings.json` (a bare `.claude/hooks/hooks.json` is not enough).
- [ ] `.claude/cli/` has a module for every command `maincli.py` declares.
- [ ] `.claude/agents/` has 13 Compass agents.
- [ ] `.claude/skills/` populated.
- [ ] `.compass/meta/lessons-catalog.yaml` exists.

Two checks doctor doesn't cover, also worth confirming: `.claude/rules/` has 4 rule files, and `.compass/index.md` / `.compass/active.md` exist.

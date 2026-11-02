# Permission allowlist

Write the permission allowlist into the same `.claude/settings.json` (or `.claude/settings.local.json`), merging alongside the `hooks` key the registration script just wrote:

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Grep",
      "Glob",
      "WebSearch",
      "WebFetch",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(git status:*)",
      "Bash(git rev-parse:*)",
      "Bash(git show:*)",
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Bash(curl:*)",
      "Bash(python3:*)",
      "Bash(pytest:*)",
      "Bash(npm test:*)",
      "Bash(npm run test:*)",
      "Bash(yarn test:*)",
      "Bash(go test:*)",
      "Bash(cargo test:*)",
      "Bash(make test:*)",
      "Bash(make check:*)",
      "Bash(make lint:*)",
      "Bash(npm run lint:*)",
      "Bash(npm run build:*)",
      "Bash(uv run pytest:*)",
      "Bash(python -m pytest:*)",
      "Bash(./venv/Scripts/python.exe:*)",
      "Bash(./venv/bin/python:*)"
    ]
  }
}
```

`Bash(python3:*)` lets skills invoke the `compass` CLI (e.g. `/compass:vault-health` running `compass validate`). Compass agents use `permissionMode: bypassPermissions`, so they bypass these prompts entirely - the allowlist is the safety net for everything else.

Hook registration is already a merge (the script never overwrites `.claude/settings.json` wholesale). The permission allowlist is not scripted the same way: if `.claude/settings.json` already has a `permissions` key, merge the two lists by hand and ask before overwriting existing permissions.

#!/usr/bin/env bash
set -euo pipefail

# Creates an isolated demo project without requiring an LLM or network after
# Hornero is installed. Pass a destination to keep the project; otherwise a
# temporary directory is used.
destination="${1:-$(mktemp -d "${TMPDIR:-/tmp}/hornero-demo.XXXXXX")}"

if [[ -e "$destination" && -n "$(find "$destination" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "destination is not empty: $destination" >&2
  exit 2
fi

echo "== Creating project at $destination"
hornero new demo-service --path "$destination" \
  --blueprint python-service --no-git
cd "$destination"

echo "== Initial status"
hornero status
hornero blueprint status

echo "== Building deterministic local knowledge"
hornero reindex
hornero validate
hornero report

echo "== Installing agent-facing integrations (no git hook in the demo)"
hornero wiki codex install --no-git-hook
hornero wiki claude install --no-git-hook
hornero wiki gemini install --no-git-hook

echo "== Final integration status"
hornero wiki codex status --json
hornero wiki claude status --json
hornero wiki gemini status --json

echo "Demo ready: $destination"

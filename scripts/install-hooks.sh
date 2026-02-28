#!/usr/bin/env bash
# Instala os git hooks do projeto em .git/hooks/

set -e

HOOKS_SRC="$(dirname "$0")/hooks"
HOOKS_DST="$(git rev-parse --show-toplevel)/.git/hooks"

for hook in "$HOOKS_SRC"/*; do
  nome=$(basename "$hook")
  ln -sf "$(realpath "$hook")" "$HOOKS_DST/$nome"
  chmod +x "$hook"
  echo "Hook instalado (link simbolico): .git/hooks/$nome -> $hook"
done

echo "Pronto."

#!/usr/bin/env bash
# Instala os git hooks do projeto em .git/hooks/

set -e

HOOKS_SRC="$(dirname "$0")/hooks"
HOOKS_DST="$(git rev-parse --show-toplevel)/.git/hooks"

for hook in "$HOOKS_SRC"/*; do
  nome=$(basename "$hook")
  cp "$hook" "$HOOKS_DST/$nome"
  chmod +x "$HOOKS_DST/$nome"
  echo "Hook instalado: .git/hooks/$nome"
done

echo "Pronto."

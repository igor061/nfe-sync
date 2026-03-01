#!/usr/bin/env bash
# Uso: ./scripts/commit.sh "mensagem do commit" [--push]
#
# Incrementa versao patch, atualiza CHANGELOG.md, faz git commit --no-verify.
# Passe --push como segundo argumento para fazer git push em seguida.

set -e

if [ -z "$1" ]; then
  echo "Uso: $0 \"mensagem do commit\" [--push]"
  exit 1
fi

MSG="$1"
DO_PUSH=false
if [ "$2" = "--push" ]; then
  DO_PUSH=true
fi

FILE="pyproject.toml"
CHANGELOG="CHANGELOG.md"

# le versao atual
current=$(grep '^version = ' "$FILE" | sed 's/version = "\(.*\)"/\1/')
if [ -z "$current" ]; then
  echo "Erro: versao nao encontrada em $FILE"
  exit 1
fi

major=$(echo "$current" | cut -d. -f1)
minor=$(echo "$current" | cut -d. -f2)
patch=$(echo "$current" | cut -d. -f3)
new_patch=$((patch + 1))
new_version="${major}.${minor}.${new_patch}"

# atualiza pyproject.toml
sed -i '' "s/^version = \"${current}\"/version = \"${new_version}\"/" "$FILE"

# insere nova entrada no CHANGELOG logo apos "# Changelog"
tmp=$(mktemp)
inserted=false
while IFS= read -r linha; do
  echo "$linha" >> "$tmp"
  if [ "$inserted" = false ] && echo "$linha" | grep -q "^# Changelog"; then
    echo "" >> "$tmp"
    echo "## ${new_version}" >> "$tmp"
    echo "- ${MSG}" >> "$tmp"
    inserted=true
  fi
done < "$CHANGELOG"
mv "$tmp" "$CHANGELOG"

git add "$FILE" "$CHANGELOG"

echo "Versao atualizada: ${current} → ${new_version}"

git commit --no-verify -m "$MSG"

if [ "$DO_PUSH" = true ]; then
  git push
fi

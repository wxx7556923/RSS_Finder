#!/usr/bin/env bash
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
ROOT="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"

mkdir -p "$HOME/.local/bin"
ln -sf "$ROOT/paper-radar" "$HOME/.local/bin/paper-radar"
ln -sf "$ROOT/paper-radar" "$HOME/.local/bin/pradar"

echo "Installed commands:"
echo "  paper-radar"
echo "  pradar"
echo
echo "If your shell cannot find them, add this to ~/.bashrc:"
echo '  export PATH="$HOME/.local/bin:$PATH"'

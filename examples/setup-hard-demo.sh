#!/usr/bin/env bash
# Create the harder demo project: an order engine with a frozen contract, three defective stubs, an
# objective acceptance harness, a git repository and a three-task ledger.
#
#   bash examples/setup-hard-demo.sh [TARGET_DIR]      (default: <protocol root>/hard-demo)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
TARGET="${1:-$(dirname "$HERE")/hard-demo}"
PROTOCOL="${AGENT_TEAM_HOME:-$(dirname "$HERE")}"
PY="$(command -v python3 || command -v python)"

[ -f "$PROTOCOL/scripts/agent_team.py" ] || {
  echo "error: protocol not found at $PROTOCOL (run install.sh first)" >&2
  exit 1
}
[ -f "$HERE/hard-demo/check.py" ] || {
  echo "error: missing $HERE/hard-demo/check.py" >&2
  exit 1
}

rm -rf "$TARGET"
mkdir -p "$TARGET"
cd "$TARGET"
TARGET="$(pwd -P)"

cp "$HERE/hard-demo/README.template.md" README.md
cp "$HERE/hard-demo/check.py" check.py
cp "$HERE/hard-demo/stubs/pricing.py" "$HERE/hard-demo/stubs/inventory.py" "$HERE/hard-demo/stubs/orders.py" .
chmod +x check.py

git init -q -b main
git config user.email "demo@example.com"
git config user.name "Demo"
git add -A
git commit -q -m "demo: frozen contract, defective stubs, acceptance harness"

"$PY" "$PROTOCOL/scripts/agent_team.py" init --repo "$TARGET" >/dev/null
"$PY" "$PROTOCOL/scripts/agent_team.py" add-task --repo "$TARGET" --task-id T-001 \
  --title "money rules in pricing.py" >/dev/null
"$PY" "$PROTOCOL/scripts/agent_team.py" add-task --repo "$TARGET" --task-id T-002 \
  --title "atomic reservations in inventory.py" >/dev/null
"$PY" "$PROTOCOL/scripts/agent_team.py" add-task --repo "$TARGET" --task-id T-003 \
  --title "order service on top of pricing and inventory" >/dev/null

echo "hard demo   : $TARGET"
echo "protocol    : $PROTOCOL"
echo "ledger      : T-001 pricing, T-002 inventory, T-003 orders (reads README.md for ownership)"
echo
echo "baseline (every section must fail):"
set +e
(cd "$TARGET" && "$PY" check.py)
echo "  check.py -> exit $?"
set -e
echo
echo "next: open your coding agent in $TARGET and paste the prompt from examples/hard-prompt.md"

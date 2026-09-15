#!/usr/bin/env bash
# Create a throwaway repository with two real defects and two failing checks,
# plus a bootstrapped ledger. Ready for examples/prompts.md.
#
#   bash examples/setup-demo-repo.sh [TARGET_DIR]
set -euo pipefail

TARGET="${1:-$HOME/agent-team-demo}"
PROTOCOL="${AGENT_TEAM_HOME:-$HOME/.local/share/agent-team-setup}"
PY="$(command -v python3 || command -v python)"

[ -f "$PROTOCOL/scripts/agent_team.py" ] || {
  echo "error: protocol not found at $PROTOCOL (run install.sh first)" >&2
  exit 1
}

rm -rf "$TARGET"
mkdir -p "$TARGET"
cd "$TARGET"
# Resolve symlinks once: handoff namespaces are derived from the resolved path.
TARGET="$(pwd -P)"

git init -q -b main
git config user.email "demo@example.com"
git config user.name "Demo"

cat > app.py <<'PY'
"""Pricing helpers. Both functions carry a known defect on purpose."""


def apply_discount(price, percent):
    """Return the price after one discount.

    Defect: float arithmetic leaks sub-cent precision, so 19.99 - 10% is not 17.99.
    """
    return price - price * percent / 100


def stack_discount(price, percents):
    """Defect: applies only the first discount instead of all of them."""
    return apply_discount(price, percents[0])
PY

cat > check.py <<'PY'
"""Acceptance check for the single-discount task only."""
from app import apply_discount

result = apply_discount(19.99, 10)
assert result == 17.99, f"expected 17.99, got {result}"
print("discount rounds to cents")
PY

cat > check_all.py <<'PY'
"""Whole-module check: also covers the stacked discount that T-002 owns."""
from app import apply_discount, stack_discount

assert apply_discount(19.99, 10) == 17.99, apply_discount(19.99, 10)
assert stack_discount(100, [10, 10]) == 81.0, stack_discount(100, [10, 10])
print("all checks pass")
PY

cat > README.md <<'MD'
# Pricing demo

`app.py` holds two defects kept on purpose:

- `apply_discount` leaks sub-cent precision.
- `stack_discount` applies only the first discount.

Checks: `python3 check.py` (single discount), `python3 check_all.py` (both).
MD

git add -A
git commit -q -m "demo: two defects, two failing checks"

"$PY" "$PROTOCOL/scripts/agent_team.py" init --repo "$TARGET" --title "fix single-discount rounding" >/dev/null
"$PY" "$PROTOCOL/scripts/agent_team.py" add-task --repo "$TARGET" --title "stack discounts correctly" >/dev/null

echo "demo repo : $TARGET"
echo "protocol  : $PROTOCOL"
echo "ledger    : $TARGET/ledger (T-001 rounding, T-002 stacking)"
echo
echo "baseline (both must fail):"
set +e
(cd "$TARGET" && "$PY" check.py); echo "  check.py     -> exit $?"
(cd "$TARGET" && "$PY" check_all.py); echo "  check_all.py -> exit $?"
set -e
echo
echo "next: open Claude Code in $TARGET and paste prompt 1 from examples/prompts.md"

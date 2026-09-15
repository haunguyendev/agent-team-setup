#!/usr/bin/env bash
# One-command install for the agent team ledger protocol.
#
#   From a checkout:            ./install.sh
#   Piped from a public repo:   curl -fsSL <raw install.sh url> | bash
#   Private repo (gh auth):     gh repo clone <owner>/agent-team-setup ~/.local/share/agent-team-setup \
#                                 && bash ~/.local/share/agent-team-setup/install.sh
#
# Installs the protocol globally by default: skills + subagents + slash command into
# ~/.claude, and the write-boundary hook into ~/.claude/settings.json (backed up first).
set -euo pipefail

REPO_URL="${AGENT_TEAM_REPO_URL:-https://github.com/haunguyendev/agent-team-setup}"
DEFAULT_DIR="${AGENT_TEAM_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/agent-team-setup}"

GLOBAL_DIR=""; SCOPE="user"; PROJECT=""; TARGETS="auto"; WITH_HOOKS=1; WITH_AGENTS_MD=0; FORCE=0; CHECK=0
QUIET=0

bold() { [ "$QUIET" = 1 ] || printf '\033[1m%s\033[0m\n' "$1"; }
info() { [ "$QUIET" = 1 ] || printf '  %s\n' "$1"; }
ok()   { [ "$QUIET" = 1 ] || printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1" >&2; }
die()  { printf '\033[31merror:\033[0m %s\n' "$1" >&2; exit 1; }

usage() {
  cat <<'EOF'
Install the agent team ledger protocol into a coding agent.

Usage: install.sh [options]

  --global-dir DIR    where to keep the protocol package (default: ~/.local/share/agent-team-setup)
  --project DIR       install into DIR/.claude instead of the global agent config
  --scope user|project  explicit scope (default: user; --project implies project)
  --target WHICH      auto | claude | omp | both (default: auto - OMP only where OMP exists)
  --no-hooks          do not register the write-boundary hook in settings.json
  --with-agents-md    also copy the AGENTS.md snippet into the target
  --force             overwrite existing agent assets
  --check             verify an existing installation and exit
  --quiet             print only warnings and errors
  -h, --help          this help

Environment: AGENT_TEAM_HOME, AGENT_TEAM_REPO_URL
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --global-dir) GLOBAL_DIR="${2:?--global-dir needs a value}"; shift 2 ;;
    --project)    PROJECT="${2:?--project needs a value}"; SCOPE="project"; shift 2 ;;
    --scope)      SCOPE="${2:?--scope needs a value}"; shift 2 ;;
    --target)     TARGETS="${2:?--target needs a value}"; shift 2 ;;
    --no-hooks)   WITH_HOOKS=0; shift ;;
    --with-agents-md) WITH_AGENTS_MD=1; shift ;;
    --force)      FORCE=1; shift ;;
    --check)      CHECK=1; shift ;;
    --quiet)      QUIET=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *)            die "unknown option: $1 (try --help)" ;;
  esac
done

[ "$SCOPE" = "user" ] || [ "$SCOPE" = "project" ] || die "--scope must be user or project"
[ -n "$GLOBAL_DIR" ] || GLOBAL_DIR="$DEFAULT_DIR"

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
[ -n "$PY" ] || die "python3 is required (standard library only)"

# Resolve the protocol package: the checkout this script lives in, else a clone.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
if [ -f "$SCRIPT_DIR/scripts/agent_team.py" ]; then
  P="$SCRIPT_DIR"
else
  P="$GLOBAL_DIR"
  if [ -f "$P/scripts/agent_team.py" ]; then
    ok "using existing protocol package at $P"
  else
    bold "Cloning the protocol package into $P"
    mkdir -p "$(dirname "$P")"
    if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
      gh repo clone "$(printf '%s' "$REPO_URL" | sed -E 's#^https://github.com/##; s#\.git$##')" "$P" -- --depth 1
    else
      git clone --depth 1 "$REPO_URL" "$P"
    fi
  fi
fi

if [ "$CHECK" = 1 ]; then
  bold "Checking $P"
  "$PY" "$P/scripts/agent_team.py" --help >/dev/null || die "runtime is not runnable"
  ok "runtime ok ($("$PY" -c 'import sys; print(sys.version.split()[0])'))"
  if [ ! -f "$HOME/.claude/agent-team-ledger/protocol-root.txt" ]; then
    warn "no global wiring found in $HOME/.claude; run this script without --check"
    exit 1
  fi
  ok "global wiring present: $(cat "$HOME/.claude/agent-team-ledger/protocol-root.txt")"
  exit 0
fi

ARGS=(install --repo "$P")
if [ "$SCOPE" = "project" ]; then
  [ -n "$PROJECT" ] || PROJECT="$(pwd)"
  [ -d "$PROJECT" ] || die "--project path does not exist: $PROJECT"
  ARGS=(install --repo "$PROJECT" --scope project)
else
  ARGS=(install --repo "$P" --scope user)
fi
ARGS+=(--target "$TARGETS")
[ "$WITH_HOOKS" = 1 ] && ARGS+=(--with-hooks)
[ "$WITH_AGENTS_MD" = 1 ] && ARGS+=(--with-agents-md)
[ "$FORCE" = 1 ] && ARGS+=(--force)

bold "Installing the ledger protocol"
info "protocol package: $P"
info "scope:            $SCOPE (targets: $TARGETS)"

RESULT="$("$PY" "$P/scripts/agent_team.py" "${ARGS[@]}")" || die "installation failed"
ROOTS_BLOCK="$("$PY" -c 'import json,sys; d=json.loads(sys.argv[1])["roots"]; print("\n".join(f"    {k:<7} {v}" for k, v in d.items()))' "$RESULT")"

while IFS= read -r line; do ok "$line"; done < <(
  "$PY" -c 'import json,sys; [print(a) for a in json.loads(sys.argv[1])["actions"]]' "$RESULT"
)

"$PY" "$P/scripts/agent_team.py" --help >/dev/null || die "installed runtime is not runnable"

[ "$QUIET" = 1 ] || cat <<EOF

$(bold "Done.")
  Ready in any project:
    python3 "$P/scripts/agent_team.py" init    --repo "\$(git rev-parse --show-toplevel)" --title "objective"
    python3 "$P/scripts/agent_team.py" inspect --adapter "$P/adapters/promete_verba.json" --repo .

  Agent configs:
$ROOTS_BLOCK
  Protocol root:   $P
EOF

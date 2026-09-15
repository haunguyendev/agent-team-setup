# Agent Team Setup

Canonical, GVS5H-informed coordination protocol for the MetaTrader, Promete Verba, and MCU
repositories.

This package keeps the useful paper ideas—fresh worker contexts, durable curated state,
dynamic task selection, and external verification—while respecting Claude Code worktree
isolation. Workers publish immutable handoffs; only the coordinator promotes them into the
authoritative repository ledger.

- [Apply to a coding agent](apply-to-coding-agent.md)
- [Operations runbook](operations-runbook.md) — when to spawn, spawn prompts, parallel work, CI, failure playbook
- [Test prompts](examples/prompts.md) — paste-ready prompts plus a scratch repository with real defects
- [Protocol](protocol.md)
- [Result schema](schemas/result.schema.json)
- [Script contract](scripts/README.md)
- [Verification matrix](verification.md)

The canonical implementation is in `core/`, with project adapters in `adapters/`, the handoff
runtime in `scripts/agent_team/`, and an inspection/bootstrap CLI in `scripts/agent_team.py`.
Agent wiring (skill, subagents, slash command, write-boundary hook) lives in `integrations/`.
Each adapter uses 20 logical lanes and the `auto` model.

## Install

One command, global (works in every project afterwards):

```bash
gh repo clone haunguyendev/agent-team-setup ~/.local/share/agent-team-setup   # private: needs `gh auth login`
bash ~/.local/share/agent-team-setup/install.sh
```

From a checkout, `./install.sh` does the same thing.

| Flag | Effect |
|---|---|
| *(none)* | global: skill + subagents + slash command + write-boundary hook into `~/.claude` |
| `--project DIR` | same wiring, but into `DIR/.claude` only |
| `--global-dir DIR` | where the protocol package lives when the script has to clone itself (`AGENT_TEAM_HOME`) |
| `--no-hooks` | skip registering the guard in `settings.json` |
| `--with-agents-md` | also copy the `AGENTS.md` snippet into the target |
| `--force` | overwrite existing agent assets |
| `--check` | verify an existing installation and exit |

The installer is additive: existing files are kept, and `settings.json` is backed up before the
hook is merged (merging twice does not duplicate it). Once the repository is public, the script
can be piped: `curl -fsSL https://raw.githubusercontent.com/haunguyendev/agent-team-setup/main/install.sh | bash`.

Then, per project:

```bash
P="$HOME/.local/share/agent-team-setup"
python3 "$P/scripts/agent_team.py" inspect --adapter "$P/adapters/promete_verba.json" --repo /path/to/checkout
python3 "$P/scripts/agent_team.py" init    --repo /path/to/checkout --title "objective"
```

Requirements: `git` and `python3` (3.9+, standard library only). Tests need `pytest`.

```bash
uv run --with pytest python -m pytest tests/ -q     # 22 passed
```

## Notes

- Handoffs are namespaced by `sha256(str(repo.resolve()))[:20]` and stored under
  `~/.claude-camel/handoffs` (`CLAUDE_AGENT_HANDOFF_ROOT` overrides). Moving or renaming a checkout
  orphans its previous handoffs.
- Adapters pin the paths and namespaces of their original checkouts. On another machine, pass
  `--repo <your checkout>`; `inspect` reports `namespace_matches` so you can see the difference.
- `paper/iclr2027_conference.pdf` is a third-party submission under review. It is **not**
  redistributed here: `.gitignore` excludes it, and the local file is for reading only.

The legacy `working/agent-team-setup.md` file remains as a compatibility entry point.

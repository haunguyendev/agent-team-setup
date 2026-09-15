# Agent Team Setup

Canonical, GVS5H-informed coordination protocol for the MetaTrader, Promete Verba, and MCU
repositories.

This package keeps the useful paper ideas—fresh worker contexts, durable curated state,
dynamic task selection, and external verification—while respecting Claude Code worktree
isolation. Workers publish immutable handoffs; only the coordinator promotes them into the
authoritative repository ledger.

- [Apply to a coding agent](apply-to-coding-agent.md)
- [Operations runbook](operations-runbook.md) — when to spawn, spawn prompts, parallel work, CI, failure playbook
- [Protocol](protocol.md)
- [Result schema](schemas/result.schema.json)
- [Script contract](scripts/README.md)
- [Verification matrix](verification.md)

The canonical implementation is in `core/`, with project adapters in `adapters/`, the handoff
runtime in `scripts/agent_team/`, and an inspection/bootstrap CLI in `scripts/agent_team.py`.
Agent wiring (skill, subagents, slash command, write-boundary hook) lives in `integrations/`.
Each adapter uses 20 logical lanes and the `auto` model.

## Install

```bash
git clone https://github.com/haunguyendev/agent-team-setup ~/agent-team-setup
P=~/agent-team-setup

python3 "$P/scripts/agent_team.py" inspect --adapter "$P/adapters/promete_verba.json" --repo /path/to/checkout
python3 "$P/scripts/agent_team.py" init    --repo /path/to/checkout --title "objective"
python3 "$P/scripts/agent_team.py" install --repo /path/to/checkout --with-hooks --with-agents-md
```

Requirements: `git` and `python3` (3.9+, standard library only). Tests need `pytest`.

```bash
uv run --with pytest python -m pytest tests/ -q     # 18 passed
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

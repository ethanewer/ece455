# Agent harness compatibility

This repo is worked on by three coding agents: pi, Codex CLI, and Claude Code.
All three share the same skill and instruction files. Do not duplicate
content across harnesses.

## Layout

| Path | Purpose |
|---|---|
| `.pi/skills/` | Source of truth for skills. pi reads this directly. |
| `.claude/skills/` | Symlinks into `.pi/skills/` for Claude Code. |
| `.codex/skills/` | Symlinks into `.pi/skills/` for Codex. |
| `AGENTS.md` | Memory file. Read natively by pi and Codex. |
| `CLAUDE.md` | Claude Code memory. Contains only an import of `AGENTS.md`. |

## Adding a skill

Create it once in pi's format (the shared [Agent Skills
standard](https://agentskills.io) format, which all three harnesses read):

```
.pi/skills/<name>/SKILL.md    # frontmatter: name, description; then instructions
```

Then link it for the other two:

```bash
ln -s ../../.pi/skills/<name> .claude/skills/<name>
ln -s ../../.pi/skills/<name> .codex/skills/<name>
```

Use relative symlink targets so the links survive clones. Never edit a skill
under `.claude/skills/` or `.codex/skills/`; edit `.pi/skills/` and the
symlinks pick it up.

## Memory files

`AGENTS.md` is the only place for project-level instructions. `CLAUDE.md`
must stay a one-line import (`@AGENTS.md`). If you find yourself adding the
same rule to two files, you are doing it wrong.

## Skills available

- `external-review`: run an external review over changes via the cursor-agent
  CLI. Run the software-quality (bugbot) review before committing. Run the
  scientific-correctness review when a change touches physical models,
  constants, noise parameters, or scoring math. Run the deep audit for
  whole-pipeline changes. Read `external-review/SKILL.md` for the exact
  invocations.

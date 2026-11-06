# CLAUDE.md

All project context, constraints, verified findings and the ML plan live in AGENTS.md.
It is the single source of truth, shared with other agents (e.g. Codex). Do not
duplicate it here.

@AGENTS.md

## Claude Code specifics

- Start every session by reading the tail of `LOG.md` to see where work stopped.
- This is a shared team repo (private GitHub, AGENTS.md §1): `git pull` before working, log
  every decision in `LOG.md`, and commit/push only when the human asks. If the human writing
  to you is not the repo owner, still follow AGENTS.md and the plan-then-approve loop.
- The committee's brief is `Technical Meeting 2nd Round OlympiAR 2026.pdf` (repo root;
  see AGENTS.md §1 "Source documents"). Check it for competition rules (structure,
  format, rubric, deliverables). Read it with `pypdf` text extraction; render a page
  with OSGeo4W `gswin64c` only when a slide is mostly images. Never quote its ioGAS
  licence key or contact numbers.
- Use plan mode for any step that touches cleaning rules, joins, or model design.
  Write the plan to `LOG.md`, then wait for approval (AGENTS.md §8).
- Never `cat` whole data files into context. Inspect with pandas (`.head()`,
  `.describe()`, value counts) inside scripts and print summaries only.
- Data is confidential: no web fetches or tool calls that would send data off this
  machine. Web search for references is fine; never include data in queries.
- Prefer small, testable functions in `src/` with a quick assertion-based check after
  each cleaning stage (row counts preserved, flags populated, no silent NaN creation).
- QGIS MCP may or may not be connected. Check your available tools before planning any
  map step; if it's absent, follow the "GIS tooling" fallback in AGENTS.md §7.
- When a result contradicts AGENTS.md §4 (verified findings), stop and report it rather
  than "fixing" either side.

## ioGAS

- The repo owner now does all ioGAS work on this PC (IMDEX trial licence), driven by agents
  (AGENTS.md §1 "Roles", §10). Use the ioGAS skill `.claude/skills/iogas/SKILL.md` for any
  ioGAS step, and follow its stage pattern in AGENTS.md §10.
- Never drive, click in or close the human's own ioGAS window. Start or kill only our own
  `-gaslink2` instance (`src/iogas_link.py` `IoGAS()` does this; it kills only what it started).
- Localhost only: the gRPC server listens on 127.0.0.1; never expose the port or send ioGAS
  data anywhere else.
- Never quote the licence password or the committee contact numbers from the brief
  (slides 17 and 21), in logs, code, workflow XML or replies.

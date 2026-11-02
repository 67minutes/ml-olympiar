# CLAUDE.md

All project context, constraints, verified findings and the ML plan live in AGENTS.md.
It is the single source of truth, shared with other agents (e.g. Codex). Do not
duplicate it here.

@AGENTS.md

## Claude Code specifics

- Start every session by reading the tail of `LOG.md` to see where work stopped.
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

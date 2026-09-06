# GEMINI.md

## Project overview

This repository is `scoutmb`, a Python package (`src/scoutmb/`) for a Scout troop's summer camp:
it turns printed class-schedule PDFs into a QR-code roster (`troop349-pdf`), then uses that
roster to fetch each attendee's live schedule and merit-badge requirement status from
`scoutingevent.com` (`troop349-schedule`), producing CSV/JSON and a self-contained HTML report.
`troop349` bundles both behind a local native window. A separate `bootstrap/` package (no
dependency on `scoutmb`) builds a thin native installer for Windows/macOS.

The package is organized in layers — `core` (pure domain logic) → `ports`/`adapters` (typed
seams and their real implementations) → `features` (orchestration) → `interfaces`
(CLI/web/desktop entry points) — with an automated test
(`tests/architecture/test_dependency_rules.py`) enforcing which layer may import which. Full
usage is in `README.md`; the fuller architecture, testing, and CI writeup is in `CLAUDE.md`.

To set up and verify a change:

```bash
uv sync --locked --all-extras
uv run pytest -q
```

The default pytest lane skips three marker-gated categories (`live_service`, `playwright`,
`release`) — see `CLAUDE.md` for what each is and how CI exercises them separately.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.

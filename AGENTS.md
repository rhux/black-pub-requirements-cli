# AGENTS.md

## Project summary

`scoutmb` (`src/scoutmb/`) is a two-stage tool for a Scout troop's summer-camp merit-badge
tracking: extract attendee/QR data from printed schedule PDFs (`troop349-pdf`), then use that to
pull live schedule and requirement-completion data from `scoutingevent.com`
(`troop349-schedule`). `troop349` wraps both behind a local native window. `bootstrap/` is a
separate, stdlib-only installer package that ships the app as a thin Windows/macOS launcher —
it never imports `scoutmb`.

Layering (`core` → `ports`/`adapters` → `features` → `interfaces`) is enforced by
`tests/architecture/test_dependency_rules.py`; `interfaces/{cli,web}/composition.py` are the
only modules allowed to import an adapter directly. See `README.md` for usage and `CLAUDE.md`
for the fuller architecture writeup, testing/CI layout, and privacy notes — this file exists for
tools that read `AGENTS.md` specifically rather than `CLAUDE.md`.

Run `uv sync --locked --all-extras && uv run pytest -q` to set up and verify. The default test
lane deselects `live_service`/`playwright`/`release`-marked tests; see `CLAUDE.md`'s Testing and
CI section for what each covers and how CI runs them.

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

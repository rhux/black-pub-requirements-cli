"""scout_schedule_cli.py CLI-entry characterization catalog (Task 21 continuation).

Covers ``CLI-SCHED-001..006``: ``parse_args``/``main``'s argparse defaults and ``--help``
behavior, and ``main``'s ``asyncio.run(async_main(args))`` / ``except KeyboardInterrupt`` /
``except Exception`` wrapper -- all real behavior of the real functions, never re-implemented.

``main()`` calls the module-level ``parse_args()`` (which reads ``sys.argv`` directly -- there is
no ``argv: list[str]`` parameter to inject) and then ``async_main(args)``, which ALWAYS reaches
``async_playwright()`` / ``playwright.chromium.launch(...)`` before it ever looks at how many
scouts were loaded -- there is no early return for an empty scout list. That means every member
below that must actually run ``async_main`` (empty-success, one-scout-success, partial-failure)
drives the real function through a narrowly-scoped ``monkeypatch.setattr(cli, "async_playwright",
...)`` swap for a fake context manager whose ``chromium.launch(...)`` returns a Task-19
``StrictFakeBrowser`` (``tests/fakes/browser.py``) -- the same fake ``test_process_scout.py``
already uses -- plus the same narrow ``navigate_and_trigger_schedule``/``discover_name``/
``post_requirement`` monkeypatches ``test_process_scout.py`` uses (this is the seam those tests
already established; ``process_scout``'s OWN calls to ``browser.new_context()`` /
``context.new_page()`` / ``page.set_default_timeout()`` / ``context.route()`` / ``page.on()`` /
``page.close()`` still run for real against the strict fakes). No real Chromium process is ever
launched by any case in this file.

``top-level-exception`` and ``keyboard-interrupt`` characterize ``main()``'s own
``try/except KeyboardInterrupt`` / ``except Exception`` wrapper (scout_schedule_cli.py:1878-1885)
directly: ``cli.async_main`` itself is monkeypatched to raise, so nothing below it (playwright,
process_scout, load_inputs) ever runs for those two members -- this is the correct, narrowest
seam for characterizing exit-code/message behavior that has nothing to do with what
``async_main``'s body actually does.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.matrix.model import CaseMetadata, Classification, Domain, EvidenceKind

_EVIDENCE_MAIN = "scout_schedule_cli.py:1876-1885 main()"
_EVIDENCE_PARSE = "scout_schedule_cli.py:125-215 parse_args()"
_EVIDENCE_ASYNC_MAIN = "scout_schedule_cli.py:1799-1873 async_main()"


@dataclass(frozen=True, slots=True)
class CliObservation:
    return_code: int | None
    stderr_contains: tuple[str, ...] = ()
    stdout_contains: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CliCase:
    meta: CaseMetadata
    expected_by_context: dict[str, object]


def _meta(
    case_id: str,
    member: str,
    contexts: tuple[str, ...],
    rationale: str,
    evidence_reference: str,
) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id="CLI-SCHED",
        member=member,
        domain=Domain.INTERFACE,
        classification=Classification.PRESERVE,
        evidence=EvidenceKind.CURRENT_BRANCH,
        rationale=rationale,
        contexts=contexts,
        evidence_reference=evidence_reference,
    )


CLI_CASES: tuple[CliCase, ...] = (
    CliCase(
        meta=_meta(
            "CLI-SCHED-001",
            "defaults-help",
            ("help", "defaults"),
            "Invoking main() with only '--help' on argv exits via SystemExit(0) with argparse's "
            "own usage text on stdout, before load_inputs/async_playwright are ever reached; "
            "calling parse_args() with only the required '--input' set independently confirms "
            "every other flag's documented default (sheet='Scouts Only', "
            "output=Path('scouting-output'), timeout=45, request_delay_ms=200, "
            "scout_delay_ms=None, allow_dead_assets=False, include_adults=False, "
            "no_html=False, html_name='report.html', email_report=False).",
            _EVIDENCE_PARSE,
        ),
        expected_by_context={
            "help": {"exit_code": 0},
            "defaults": {
                "sheet": "Scouts Only",
                "output_name": "scouting-output",
                "timeout": 45,
                "request_delay_ms": 200,
                "scout_delay_ms": None,
                "allow_dead_assets": False,
                "include_adults": False,
                "no_html": False,
                "html_name": "report.html",
                "email_report": False,
            },
        },
    ),
    CliCase(
        meta=_meta(
            "CLI-SCHED-002",
            "empty-success",
            ("run",),
            "An input CSV with header row only (0 scouts) is actually the one member of this "
            "axis that DOES exit before ever reaching async_playwright(): load_inputs (called "
            "at the very top of async_main, scout_schedule_cli.py:1805, before "
            "'async with async_playwright()') raises ValueError('No ScoutingEvent QR URLs "
            "found in <path>') for a zero-filtered scout list (scout_schedule_cli.py:256-257) "
            "-- there is no code path that reaches a genuinely empty, SUCCESSFUL batch run; "
            "'empty input' always fails closed via main()'s 'except Exception' branch (exit "
            "code 2), never a 0. This is the one CLI-SCHED member the browser genuinely never "
            "launches for.",
            _EVIDENCE_ASYNC_MAIN,
        ),
        expected_by_context={"run": CliObservation(return_code=2)},
    ),
    CliCase(
        meta=_meta(
            "CLI-SCHED-003",
            "one-scout-success",
            ("run",),
            "A single scout whose navigate_and_trigger_schedule/discover_name/post_requirement "
            "all succeed produces a 0 exit code and a written report in the output directory.",
            _EVIDENCE_ASYNC_MAIN,
        ),
        expected_by_context={"run": CliObservation(return_code=0)},
    ),
    CliCase(
        meta=_meta(
            "CLI-SCHED-004",
            "partial-failure",
            ("run",),
            "Two scouts where one's navigate_and_trigger_schedule raises and the other "
            "succeeds: process_scout records the failure as a non-fatal per-scout error "
            "(the batch does not stop), and main()'s exit code is 1 because "
            "'any(result.errors for result in results)' is true.",
            _EVIDENCE_ASYNC_MAIN,
        ),
        expected_by_context={"run": CliObservation(return_code=1)},
    ),
    CliCase(
        meta=_meta(
            "CLI-SCHED-005",
            "top-level-exception",
            ("run",),
            "When async_main(args) itself raises a plain Exception, main()'s "
            "'except Exception as exc: print(f\"ERROR: {exc}\", ...); return 2' prints to "
            "stderr and returns exit code 2 -- characterized by monkeypatching async_main "
            "directly so nothing below it (playwright, load_inputs) ever runs.",
            _EVIDENCE_MAIN,
        ),
        expected_by_context={
            "run": CliObservation(return_code=2, stderr_contains=("ERROR: boom",))
        },
    ),
    CliCase(
        meta=_meta(
            "CLI-SCHED-006",
            "keyboard-interrupt",
            ("run",),
            "When async_main(args) raises KeyboardInterrupt (e.g. Ctrl+C during a real run), "
            "main()'s 'except KeyboardInterrupt: print(\"Interrupted.\", ...); return 130' "
            "prints to stderr and returns exit code 130 -- the conventional SIGINT exit code.",
            _EVIDENCE_MAIN,
        ),
        expected_by_context={
            "run": CliObservation(return_code=130, stderr_contains=("Interrupted.",))
        },
    ),
)

ALL_CLI_METADATA: tuple[CaseMetadata, ...] = tuple(case.meta for case in CLI_CASES)

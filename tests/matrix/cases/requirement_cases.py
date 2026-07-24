"""Requirement-inference characterization catalog (Task 20).

Every row is ``preserve``: it pins the *current* behavior of ``scout_schedule_cli``'s
requirement-inference pipeline (``requirement_path`` / ``choice_requirement_count`` /
``annotate_requirement_statuses`` / ``build_missing_requirements`` / ``render_email_text`` /
``render_email_html``), not a desired future behavior.

This module holds only frozen data -- it never imports ``scout_schedule_cli`` or any optional
third-party package. All ``expected_by_context`` values were computed BY HAND by tracing the
real functions' source (read at
``scout_schedule_cli.py:690-948``), never by importing and calling them -- see the inline
comments before each section for the trace. The runner in
``tests/characterization/test_requirement_matrix.py`` performs the real import and drives the
real code.

Execution contexts (each executable case declares a subset in ``meta.contexts``):

* ``requirement_path`` -- calls the real ``requirement_path`` once per row in ``case.rows``, in
  order, threading ``current_top_level`` exactly as ``annotate_requirement_statuses`` does for a
  single (scout, class) group. Observation: a tuple of ``(path_tuple, current_top_level)`` pairs,
  one per row.
* ``tree_consumer`` -- calls the real ``annotate_requirement_statuses(list(case.rows))``.
  Observation: a tuple of per-row projections, in the ORIGINAL row order (annotation mutates in
  place but never reorders):
  ``(requirement_number, tuple(requirement_path), parent_requirement_number,
  calculated_status, calculated_status_reason, completed_subrequirements, total_subrequirements,
  choice_required_count)``. The REQ-CLASS axis instead round-trips its rows through
  ``json_for_html`` directly (it characterizes ``ClassRecord.class_completed`` passthrough, not
  requirement inference) -- see the runner's special-case dispatch.
* ``html_consumer`` -- runs the same real ``annotate_requirement_statuses`` output through the
  real ``json_for_html``, then ``json.loads`` it back, proving the JSON embed round-trips
  ``requirement_number``/``calculated_status`` unchanged. Only declared for shapes that plausibly
  reach the HTML report as an ordinary numbered leaf (not section headers / blank rows).
* ``email_consumer`` -- builds the nested ``scouts`` shape ``write_email_reports`` consumes, runs
  the real ``build_missing_requirements``, then the real ``render_email_text`` /
  ``render_email_html`` on the returned badge groups. Observation captures whether each row of
  interest's requirement number appears in the rendered text/HTML.

No test writes outside ``tmp_path`` and this module performs no real file or network I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tests.factories.payloads import REQUIREMENT_NUMBER_SHAPES
from tests.matrix.model import CaseMetadata, Classification, Domain, EvidenceKind

_EVIDENCE_PATH = "scout_schedule_cli.py:690-711 requirement_path"
_EVIDENCE_CHOICE = "scout_schedule_cli.py:713-725 choice_requirement_count"
_EVIDENCE_ANNOTATE = "scout_schedule_cli.py:744-848 annotate_requirement_statuses"
_EVIDENCE_MISSING = "scout_schedule_cli.py:851-925 build_missing_requirements"
_EVIDENCE_EMAIL = "scout_schedule_cli.py:928-986 render_email_text / render_email_html"


@dataclass(frozen=True, slots=True)
class RequirementCase:
    meta: CaseMetadata
    rows: tuple[Mapping[str, object], ...]
    expected_by_context: Mapping[str, object]


def _meta(
    case_id: str,
    axis_id: str,
    member: str,
    contexts: tuple[str, ...],
    rationale: str,
    evidence_reference: str,
) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id=axis_id,
        member=member,
        domain=Domain.REQUIREMENT,
        classification=Classification.PRESERVE,
        evidence=EvidenceKind.CURRENT_BRANCH,
        rationale=rationale,
        contexts=contexts,
        evidence_reference=evidence_reference,
    )


def _row(requirement_number: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "scout_name": "Avery Example",
        "attendee_id": "90000001",
        "class_p4_id": "2000001",
        "class_number": "26MB1",
        "merit_badge_name": "Chess",
        "requirement_id": "r1",
        "requirement_type_id": "1",
        "requirement_number": requirement_number,
        "description": "Show your work.",
        "completed_requirement": False,
        "completed_class": False,
        "requirement_on_event": True,
        "present_days": "MoTuWeTh",
    }
    row.update(overrides)
    return row


_INCOMPLETE = "Not marked complete by ScoutingEvent."
_COMPLETE = "Marked complete by ScoutingEvent."


def _leaf_row_projection(
    number: str, path: tuple[str, ...], parent: str | None, completed: bool
) -> tuple[object, ...]:
    status = "complete" if completed else "incomplete"
    reason = _COMPLETE if completed else _INCOMPLETE
    return (number, path, parent, status, reason, None, None, None)


# ==============================================================================================
# REQ-SHAPE-001..026 -- the 26 requirement-number shapes from tests/factories/payloads.py, in
# the same order. ``requirement_path`` / ``current_top_level`` values below were traced by hand
# against the tokenizer ``re.findall(r"[A-Za-z]+|\d+", text)`` and the ctl-fallback branches at
# scout_schedule_cli.py:698-710 (see the design notes in Task 20's PR description). Shapes that
# look like an ordinary numbered leaf (a digit top-level plus a lettered/numbered subpart) also
# get ``html_consumer``/``email_consumer`` contexts; bare top-level numbers, the blank shape, and
# "Note."-style label rows do not (they read as section headers or blanks, not actionable leaves).
#
# Shapes 14 (``"#(a)"``) and 24 (``"#B."``) are a documented EXCEPTION to that rule of thumb, not
# an application of it: requirement_path produces a structurally IDENTICAL result for both (a
# single non-digit token, no digit top-level, current_top_level stays None -- verified by tracing
# scout_schedule_cli.py:701-702/709-710), so nothing in the current code actually distinguishes
# them. 14 is included in ``_SHAPE_ALL4`` and 24 is not purely as a curatorial judgment call about
# which numbering convention plausibly reads as a real actionable sub-item on an actual merit
# badge worksheet: a parenthesized lowercase letter ("(a)") is the standard printed marker for a
# sub-item, while a bare capitalized letter followed by a period ("B.") more commonly reads as a
# section-header label (like "A. Materials", "B. Overview"). This distinction is NOT enforced by
# any code under test here -- no test currently depends on it -- it only affects which shapes this
# catalog happens to also exercise through html_consumer/email_consumer.
# fmt: off
_SHAPE_PATH: tuple[tuple[str, ...], ...] = (
    ("3", "a"), ("3", "a"), ("3",), ("3", "a"), ("3", "a"), ("3",), ("3",),
    ("3", "option", "a", "1"), (), ("note",), ("3", "a", "1"), ("3", "a", "1"),
    ("3", "option", "a", "1"), ("a",), ("3",), ("3", "option", "a", "1", "a"),
    ("3", "opt", "a", "1"), ("3", "a", "1"), ("3", "opt", "a", "1", "a", "1"),
    ("note", "plus"), ("3", "a", "1"), ("note", "3"), ("1",), ("b",),
    ("3", "opt", "a", "1", "a"), ("3", "optiona", "1"),
)
_SHAPE_CTL: tuple[str | None, ...] = (
    "3", "3", "3", "3", "3", "3", "3", "3", None, None, "3", "3", "3", None, "3",
    "3", "3", "3", "3", None, "3", None, "1", None, "3", "3",
)
_SHAPE_ALL4: frozenset[int] = frozenset(
    {1, 2, 4, 5, 8, 11, 12, 13, 14, 16, 17, 18, 19, 21, 25, 26}
)
# fmt: on

REQUIREMENT_CASES_SHAPE: tuple[RequirementCase, ...] = tuple(
    RequirementCase(
        meta=_meta(
            f"REQ-SHAPE-{i:03d}",
            "REQ-SHAPE",
            f"shape-{i:02d}",
            ("requirement_path", "tree_consumer", "html_consumer", "email_consumer")
            if i in _SHAPE_ALL4
            else ("requirement_path", "tree_consumer"),
            f"requirement_path({shape!r}, None) must tokenize per the real "
            f"re.findall(r'[A-Za-z]+|\\d+', ...) tokenizer and thread current_top_level exactly "
            f"as traced by hand; shape {i:02d} of 26 in the Task 20 contract.",
            _EVIDENCE_PATH,
        ),
        rows=(_row(shape),),
        expected_by_context={
            "requirement_path": ((_SHAPE_PATH[i - 1], _SHAPE_CTL[i - 1]),),
            "tree_consumer": (_leaf_row_projection(shape, _SHAPE_PATH[i - 1], None, False),),
            **(
                {
                    "html_consumer": ((shape, "incomplete"),),
                    "email_consumer": ((shape, True, True),),
                }
                if i in _SHAPE_ALL4
                else {}
            ),
        },
    )
    for i, shape in enumerate(REQUIREMENT_NUMBER_SHAPES, start=1)
)


# ==============================================================================================
# REQ-FLAG-001..008 -- all four (completed_requirement, completed_class) pairs. annotate_
# requirement_statuses (scout_schedule_cli.py:806) reads ONLY completed_requirement when deciding
# calculated_status; completed_class is carried on the row but never inspected by calculate().
# 001-004 exercise a single row in isolation ("leaf"); 005-008 wrap the same flag pair as a CHILD
# of a "#5" parent ("parent_consumer"), proving the parent's satisfied-count depends only on the
# child's inferred status (which itself depends only on completed_requirement).
# ==============================================================================================
_FLAG_PAIRS: tuple[tuple[bool, bool], ...] = (
    (True, True),
    (True, False),
    (False, True),
    (False, False),
)
_FLAG_MEMBERS = (
    "req-true-class-true",
    "req-true-class-false",
    "req-false-class-true",
    "req-false-class-false",
)

REQUIREMENT_CASES_FLAG_LEAF: tuple[RequirementCase, ...] = tuple(
    RequirementCase(
        meta=_meta(
            f"REQ-FLAG-{i:03d}",
            "REQ-FLAG",
            member,
            ("tree_consumer",),
            f"An isolated leaf row with completed_requirement={req_flag}, "
            f"completed_class={class_flag}: calculated_status must track ONLY "
            "completed_requirement -- completed_class is read nowhere in calculate().",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(_row("#5", completed_requirement=req_flag, completed_class=class_flag),),
        expected_by_context={
            "tree_consumer": (_leaf_row_projection("#5", ("5",), None, req_flag),)
        },
    )
    for i, (member, (req_flag, class_flag)) in enumerate(
        zip(_FLAG_MEMBERS, _FLAG_PAIRS, strict=True), start=1
    )
)

REQUIREMENT_CASES_FLAG_PARENT: tuple[RequirementCase, ...] = tuple(
    RequirementCase(
        meta=_meta(
            f"REQ-FLAG-{i:03d}",
            "REQ-FLAG",
            member,
            ("tree_consumer",),
            f"The same completed_requirement={req_flag}, completed_class={class_flag} pair, "
            "but this row is a CHILD consumed by a parent's satisfied-count: the parent's "
            "inferred completion depends only on the child's calculated_status, which in turn "
            "depends only on completed_requirement.",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(
            _row("#5"),
            _row("#5a", completed_requirement=req_flag, completed_class=class_flag),
        ),
        expected_by_context={
            "tree_consumer": (
                (
                    "#5",
                    ("5",),
                    None,
                    "complete" if req_flag else "incomplete",
                    (
                        "All 1 subrequirements are complete."
                        if req_flag
                        else "0 of 1 subrequirements are complete."
                    ),
                    1 if req_flag else 0,
                    1,
                    None,
                ),
                _leaf_row_projection("#5a", ("5", "a"), "#5", req_flag),
            )
        },
    )
    for i, (member, (req_flag, class_flag)) in enumerate(
        zip(_FLAG_MEMBERS, _FLAG_PAIRS, strict=True), start=5
    )
)

REQUIREMENT_CASES_FLAG: tuple[RequirementCase, ...] = (
    REQUIREMENT_CASES_FLAG_LEAF + REQUIREMENT_CASES_FLAG_PARENT
)


# ==============================================================================================
# REQ-TYPE-001..003 -- requirement_type_id "1"/"2"/"3" on an ISOLATED single row (no siblings).
# calculate() (scout_schedule_cli.py:800-841) never reads requirement_type_id at all; it is read
# only by the header_stack bookkeeping (line 793, "== '3'") which only has an observable effect
# when a LATER row's malformed path needs the fallback -- see REQ-TREE-005 for that scenario, and
# REQ-EXCLUDE-002 for type "3"'s exclusion effect in build_missing_requirements. In isolation, all
# three type IDs produce an identical calculated_status.
# ==============================================================================================
REQUIREMENT_CASES_TYPE: tuple[RequirementCase, ...] = tuple(
    RequirementCase(
        meta=_meta(
            f"REQ-TYPE-{i:03d}",
            "REQ-TYPE",
            f"type-{type_id}",
            ("tree_consumer",),
            f"requirement_type_id={type_id!r} on an isolated leaf row: calculate() never reads "
            "requirement_type_id, so all three type IDs produce the same calculated_status here "
            "(type 3's real effect on header_stack/exclusion needs siblings -- see "
            "REQ-TREE-005 and REQ-EXCLUDE-002).",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(_row("#1", requirement_type_id=type_id),),
        expected_by_context={"tree_consumer": (_leaf_row_projection("#1", ("1",), None, False),)},
    )
    for i, type_id in enumerate(("1", "2", "3"), start=1)
)


# ==============================================================================================
# REQ-CLASS-001..002 -- ClassRecord.class_completed passthrough. This flag is not part of the
# requirement-inference tree at all; it belongs to the schedule/class row that write_html_report
# embeds separately (scout_schedule_cli.py:1067 "classes = [asdict(item) ...]"). Characterized
# here via the SAME json_for_html safe-embed function requirement rows pass through, proving the
# boolean survives the JSON round trip unchanged (not stringified/dropped). The runner
# special-cases axis_id == "REQ-CLASS" in its html_consumer dispatch rather than routing through
# annotate_requirement_statuses.
# ==============================================================================================
REQUIREMENT_CASES_CLASS: tuple[RequirementCase, ...] = tuple(
    RequirementCase(
        meta=_meta(
            f"REQ-CLASS-{i:03d}",
            "REQ-CLASS",
            member,
            ("html_consumer",),
            f"A class row with class_completed={flag}: json_for_html's JSON round trip must "
            "preserve the boolean unchanged (write_html_report embeds classes via the same "
            "function used for requirements).",
            "scout_schedule_cli.py:1048-1057 json_for_html; :1067 classes list",
        ),
        rows=(
            {
                "class_number": "26MB1",
                "class_p4_id": "2000001",
                "class_completed": flag,
                "scout_name": "Avery Example",
            },
        ),
        expected_by_context={
            "html_consumer": (
                (
                    ("class_completed", flag),
                    ("class_number", "26MB1"),
                    ("class_p4_id", "2000001"),
                    ("scout_name", "Avery Example"),
                ),
            )
        },
    )
    for i, (member, flag) in enumerate(
        (("incomplete-class", False), ("complete-class", True)), start=1
    )
)


# ==============================================================================================
# REQ-EMPTY-001..002 -- a blank requirement_number. requirement_path returns immediately at
# scout_schedule_cli.py:700-701 ("if not tokens: return (), current_top_level") BEFORE the
# ctl-fallback branches run, so a blank display number always yields an empty path regardless of
# whether a top-level number was already seen -- only the returned current_top_level differs.
# ==============================================================================================
REQUIREMENT_CASES_EMPTY: tuple[RequirementCase, ...] = (
    RequirementCase(
        meta=_meta(
            "REQ-EMPTY-001",
            "REQ-EMPTY",
            "no-top-level-seen",
            ("requirement_path", "tree_consumer"),
            "A blank requirement_number as the first (only) row of its group: tokens=[] so "
            "requirement_path returns ((), None) immediately, before ever reaching the "
            "ctl-fallback branches.",
            _EVIDENCE_PATH,
        ),
        rows=(_row(""),),
        expected_by_context={
            "requirement_path": (((), None),),
            "tree_consumer": (_leaf_row_projection("", (), None, False),),
        },
    ),
    RequirementCase(
        meta=_meta(
            "REQ-EMPTY-002",
            "REQ-EMPTY",
            "after-top-level-seen",
            ("requirement_path", "tree_consumer"),
            "A blank requirement_number AFTER a numbered row already set current_top_level='4': "
            "the blank row's own path is still empty (the early return at line 700-701 fires "
            "before the ctl is ever consulted) -- only the THREADED current_top_level ('4') "
            "survives into the return value.",
            _EVIDENCE_PATH,
        ),
        rows=(_row("#4"), _row("")),
        expected_by_context={
            "requirement_path": ((("4",), "4"), ((), "4")),
            "tree_consumer": (
                _leaf_row_projection("#4", ("4",), None, False),
                _leaf_row_projection("", (), None, False),
            ),
        },
    ),
)


# ==============================================================================================
# REQ-NOTE-001..002 -- a "Note."-prefixed row. Because "note" is a LETTER token, it never sets
# current_top_level itself; but if a numbered row already set current_top_level, the ctl-fallback
# branch at scout_schedule_cli.py:707-708 prepends that ctl, making the "Note." row a CHILD of the
# preceding numbered requirement rather than a standalone top-level row.
# ==============================================================================================
REQUIREMENT_CASES_NOTE: tuple[RequirementCase, ...] = (
    RequirementCase(
        meta=_meta(
            "REQ-NOTE-001",
            "REQ-NOTE",
            "at-beginning",
            ("requirement_path", "tree_consumer"),
            "A 'Note.' row as the very first (only) row: current_top_level is still None, so "
            "the ctl-fallback branch is skipped and the row gets its own bare path ('note',).",
            _EVIDENCE_PATH,
        ),
        rows=(_row("Note."),),
        expected_by_context={
            "requirement_path": ((("note",), None),),
            "tree_consumer": (_leaf_row_projection("Note.", ("note",), None, False),),
        },
    ),
    RequirementCase(
        meta=_meta(
            "REQ-NOTE-002",
            "REQ-NOTE",
            "after-numbered",
            ("requirement_path", "tree_consumer"),
            "A 'Note.' row AFTER '#6' set current_top_level='6': the ctl-fallback branch "
            "prepends '6', producing path ('6','note') -- which then matches '#6' as its parent "
            "in the tree-building pass, so the note becomes a child of the preceding requirement.",
            _EVIDENCE_PATH + "; " + _EVIDENCE_ANNOTATE,
        ),
        rows=(_row("#6"), _row("Note.")),
        expected_by_context={
            "requirement_path": ((("6",), "6"), (("6", "note"), "6")),
            "tree_consumer": (
                (
                    "#6",
                    ("6",),
                    None,
                    "incomplete",
                    "0 of 1 subrequirements are complete.",
                    0,
                    1,
                    None,
                ),
                _leaf_row_projection("Note.", ("6", "note"), "#6", False),
            ),
        },
    ),
)


# ==============================================================================================
# REQ-TREE-001..006 -- leaf / parent / grandparent / missing-parent (orphan) / malformed-numbering
# / label-only. Each traced by hand against scout_schedule_cli.py:769-841.
# ==============================================================================================
REQUIREMENT_CASES_TREE: tuple[RequirementCase, ...] = (
    RequirementCase(
        meta=_meta(
            "REQ-TREE-001",
            "REQ-TREE",
            "leaf",
            ("tree_consumer",),
            "A single '#7a' row with no other rows in its group: len(path)>1 but "
            "prior_path_indexes is empty and header_stack is empty, so parent_index stays None "
            "-- an ordinary leaf with no parent.",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(_row("#7a"),),
        expected_by_context={
            "tree_consumer": (_leaf_row_projection("#7a", ("7", "a"), None, False),)
        },
    ),
    RequirementCase(
        meta=_meta(
            "REQ-TREE-002",
            "REQ-TREE",
            "parent",
            ("tree_consumer",),
            "'#8' followed by its child '#8a' (completed): the child's path[:1]==('8',) matches "
            "the parent's registered path, so parent_index resolves to the parent; the parent's "
            "status is then inferred complete because its one child is complete.",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(_row("#8"), _row("#8a", completed_requirement=True)),
        expected_by_context={
            "tree_consumer": (
                ("#8", ("8",), None, "complete", "All 1 subrequirements are complete.", 1, 1, None),
                _leaf_row_projection("#8a", ("8", "a"), "#8", True),
            )
        },
    ),
    RequirementCase(
        meta=_meta(
            "REQ-TREE-003",
            "REQ-TREE",
            "grandparent",
            ("tree_consumer",),
            "'#9' -> '#9a' -> '#9a1' three-level chain, only the leaf marked complete: each "
            "ancestor's completion is inferred recursively from its single child, all the way up.",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(_row("#9"), _row("#9a"), _row("#9a1", completed_requirement=True)),
        expected_by_context={
            "tree_consumer": (
                ("#9", ("9",), None, "complete", "All 1 subrequirements are complete.", 1, 1, None),
                (
                    "#9a",
                    ("9", "a"),
                    "#9",
                    "complete",
                    "All 1 subrequirements are complete.",
                    1,
                    1,
                    None,
                ),
                _leaf_row_projection("#9a1", ("9", "a", "1"), "#9a", True),
            )
        },
    ),
    RequirementCase(
        meta=_meta(
            "REQ-TREE-004",
            "REQ-TREE",
            "missing-parent",
            ("tree_consumer",),
            "'#10a' and '#10c' with NO '#10' row ever given: the parent scan only ever checks "
            "path[:1]==('10',), which was never registered by any row, so BOTH siblings stay "
            "top-level and unlinked from each other -- a bare top-level number is required for "
            "children to find each other as siblings under it.",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(_row("#10a"), _row("#10c")),
        expected_by_context={
            "tree_consumer": (
                _leaf_row_projection("#10a", ("10", "a"), None, False),
                _leaf_row_projection("#10c", ("10", "c"), None, False),
            )
        },
    ),
    RequirementCase(
        meta=_meta(
            "REQ-TREE-005",
            "REQ-TREE",
            "malformed-numbering",
            ("tree_consumer",),
            "'#16.Option.A' (a compound TYPE-3 header, never given as a bare '#16') followed by "
            "the malformed '#(y)(1)(2)' (borrows current_top_level='16'): none of the primary "
            "path-prefix depths match any registered path, so it falls back to the nearest "
            "shallower header_stack entry -- the compound header itself, at depth 3 < 4.",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(
            _row("#16.Option.A", requirement_type_id="3"),
            _row("#(y)(1)(2)"),
        ),
        expected_by_context={
            "tree_consumer": (
                (
                    "#16.Option.A",
                    ("16", "option", "a"),
                    None,
                    "incomplete",
                    "0 of 1 subrequirements are complete.",
                    0,
                    1,
                    None,
                ),
                _leaf_row_projection("#(y)(1)(2)", ("16", "y", "1", "2"), "#16.Option.A", False),
            )
        },
    ),
    RequirementCase(
        meta=_meta(
            "REQ-TREE-006",
            "REQ-TREE",
            "label-only",
            ("tree_consumer",),
            "'#17' followed by a pure-text TYPE-3 label row 'Materials Needed': the label's "
            "path prefix ('17',) matches the parent's registered path, so the label becomes a "
            "child (and header_stack) entry despite carrying no requirement letter/number.",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(_row("#17"), _row("Materials Needed", requirement_type_id="3")),
        expected_by_context={
            "tree_consumer": (
                (
                    "#17",
                    ("17",),
                    None,
                    "incomplete",
                    "0 of 1 subrequirements are complete.",
                    0,
                    1,
                    None,
                ),
                _leaf_row_projection(
                    "Materials Needed", ("17", "materials", "needed"), "#17", False
                ),
            )
        },
    ),
)


# ==============================================================================================
# REQ-CHOICE-001..030 -- cross product of verb x threshold relation x digit/word phrasing.
# choice_requirement_count's regex (scout_schedule_cli.py:717-721) is case-insensitive and
# recognizes all five verbs with either a digit or one of CHOICE_COUNT_WORDS; every description
# below states "<verb> <2|two> of the following.", so choice_requirement_count parses 2 in all 30
# cases (verified by hand against the regex -- not by calling it). Each case uses the SAME fixed
# tree: parent '#3' + four children '#3a'..'#3d'; only how many children are completed
# (satisfied_count) varies with the "below"/"equal"/"above" relation to the parsed threshold of 2,
# out of a fixed total of 4 (so satisfied never equals total -- the 'complete_check' choice branch
# at scout_schedule_cli.py:827-831 is always the one under test, never the 'all satisfied' branch
# at :819-826). The (verb, phrasing, count_text, threshold, expected relation) table below is
# explicit and immutable, matching the Task 20 instruction to hand-write it rather than derive it
# from the parser.
# ==============================================================================================
_CHOICE_PARENT_NUMBER = "#3"
_CHOICE_PARENT_PATH: tuple[str, ...] = ("3",)
_CHOICE_CHILD_NUMBERS = ("#3a", "#3b", "#3c", "#3d")
_CHOICE_CHILD_PATHS: tuple[tuple[str, ...], ...] = (("3", "a"), ("3", "b"), ("3", "c"), ("3", "d"))
_CHOICE_TOTAL = 4
_CHOICE_THRESHOLD = 2

# (verb, phrasing, count_text, relation, satisfied_count) -- 5 verbs x 2 phrasings x 3 relations.
_CHOICE_TABLE: tuple[tuple[str, str, str, str, int], ...] = tuple(
    (verb, phrasing, count_text, relation, satisfied)
    for verb in ("Do", "Complete", "Choose", "Select", "Perform")
    for phrasing, count_text in (("digit", "2"), ("word", "two"))
    for relation, satisfied in (("below", 1), ("equal", 2), ("above", 3))
)


def _choice_rows(description: str, satisfied_count: int) -> tuple[dict[str, object], ...]:
    parent = _row(_CHOICE_PARENT_NUMBER, description=description)
    children = tuple(
        _row(
            number, description=f"Do part {letter}.", completed_requirement=index < satisfied_count
        )
        for index, (number, letter) in enumerate(zip(_CHOICE_CHILD_NUMBERS, "abcd", strict=True))
    )
    return (parent, *children)


def _choice_expected(satisfied_count: int) -> tuple[object, ...]:
    # Hand-traced against calculate() at scout_schedule_cli.py:819-836: satisfied_count never
    # equals _CHOICE_TOTAL (4) here, so the 'all satisfied' branch never fires; the choice branch
    # (satisfied_count >= choice_count) always decides parent status.
    if satisfied_count >= _CHOICE_THRESHOLD:
        parent_status = "complete_check"
        parent_reason = (
            f"{satisfied_count} of {_CHOICE_TOTAL} subrequirements appear complete; this meets "
            f"the stated choice of {_CHOICE_THRESHOLD}, but should be verified."
        )
    else:
        parent_status = "incomplete"
        parent_reason = f"{satisfied_count} of {_CHOICE_TOTAL} subrequirements are complete."
    rows: list[object] = [
        (
            _CHOICE_PARENT_NUMBER,
            _CHOICE_PARENT_PATH,
            None,
            parent_status,
            parent_reason,
            satisfied_count,
            _CHOICE_TOTAL,
            _CHOICE_THRESHOLD,
        )
    ]
    for index, (number, path) in enumerate(
        zip(_CHOICE_CHILD_NUMBERS, _CHOICE_CHILD_PATHS, strict=True)
    ):
        rows.append(
            _leaf_row_projection(number, path, _CHOICE_PARENT_NUMBER, index < satisfied_count)
        )
    return tuple(rows)


REQUIREMENT_CASES_CHOICE: tuple[RequirementCase, ...] = tuple(
    RequirementCase(
        meta=_meta(
            f"REQ-CHOICE-{i:03d}",
            "REQ-CHOICE",
            f"{verb.lower()}-{phrasing}-{relation}",
            ("tree_consumer",),
            f"choice_requirement_count parses {_CHOICE_THRESHOLD} out of "
            f"'{verb} {count_text} of the following.' ({phrasing} phrasing); with "
            f"{_CHOICE_TOTAL} children and {relation} relative to the threshold, calculate() "
            f"must apply the matching branch of its choice-vs-all-satisfied logic.",
            _EVIDENCE_CHOICE + "; " + _EVIDENCE_ANNOTATE,
        ),
        rows=_choice_rows(f"{verb} {count_text} of the following.", satisfied),
        expected_by_context={"tree_consumer": _choice_expected(satisfied)},
    )
    for i, (verb, phrasing, count_text, relation, satisfied) in enumerate(_CHOICE_TABLE, start=1)
)


# ==============================================================================================
# REQ-EXCLUDE-001..002 -- is_not_used / requirement_type_id=="3" exclusion from
# build_missing_requirements' is_actionable_leaf check (scout_schedule_cli.py:873-879): both
# conditions independently prevent a row from ever being selected as a missing/actionable item,
# even though annotate_requirement_statuses would otherwise mark it 'incomplete'.
# ==============================================================================================
REQUIREMENT_CASES_EXCLUDE: tuple[RequirementCase, ...] = (
    RequirementCase(
        meta=_meta(
            "REQ-EXCLUDE-001",
            "REQ-EXCLUDE",
            "not-used",
            ("email_consumer",),
            "A leaf whose description contains '(not used)': is_not_used() makes "
            "is_actionable_leaf() return False, so the row is never selected and never appears "
            "in a rendered missing-requirements email.",
            _EVIDENCE_MISSING,
        ),
        rows=(_row("#18a", description="Learn to whittle. (not used)"),),
        expected_by_context={"email_consumer": (("#18a", False, False),)},
    ),
    RequirementCase(
        meta=_meta(
            "REQ-EXCLUDE-002",
            "REQ-EXCLUDE",
            "type-3",
            ("email_consumer",),
            "A leaf with requirement_type_id=='3': is_actionable_leaf()'s type check excludes "
            "it from build_missing_requirements even though annotate_requirement_statuses "
            "would mark it 'incomplete'.",
            _EVIDENCE_MISSING,
        ),
        rows=(_row("#19", requirement_type_id="3", description="Section header."),),
        expected_by_context={"email_consumer": (("#19", False, False),)},
    ),
)


# ==============================================================================================
# REQ-NONMUTATE-001..002 -- annotate_requirement_statuses copies each row
# ("annotated = [dict(item) for item in requirements]", scout_schedule_cli.py:752) before
# mutating, so the CALLER's original row objects are never touched. This is asserted for EVERY
# case in this catalog by the test harness's blanket `assert case.rows == before` (see the
# runner); these two rows exist to also give the axis a valid/malformed pair with a real,
# hand-traced expected outcome rather than being pure mutation-only placeholders.
# ==============================================================================================
REQUIREMENT_CASES_NONMUTATE: tuple[RequirementCase, ...] = (
    RequirementCase(
        meta=_meta(
            "REQ-NONMUTATE-001",
            "REQ-NONMUTATE",
            "valid-tree",
            ("tree_consumer",),
            "A well-formed '#20' + '#20a' parent/child tree: annotate_requirement_statuses "
            "must not mutate the caller's input rows in place (it builds a fresh copied list).",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(_row("#20"), _row("#20a", completed_requirement=True)),
        expected_by_context={
            "tree_consumer": (
                (
                    "#20",
                    ("20",),
                    None,
                    "complete",
                    "All 1 subrequirements are complete.",
                    1,
                    1,
                    None,
                ),
                _leaf_row_projection("#20a", ("20", "a"), "#20", True),
            )
        },
    ),
    RequirementCase(
        meta=_meta(
            "REQ-NONMUTATE-002",
            "REQ-NONMUTATE",
            "malformed-tree",
            ("tree_consumer",),
            "A malformed '#(z)' row with no prior top-level number at all: "
            "annotate_requirement_statuses must not mutate the caller's input row in place even "
            "when the parsed path is degenerate.",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(_row("#(z)"),),
        expected_by_context={"tree_consumer": (_leaf_row_projection("#(z)", ("z",), None, False),)},
    ),
)


# ==============================================================================================
# REQ-IDENTITY-001..003 -- _attendee_key_for (scout_schedule_cli.py:728-741) groups by
# attendee_id (never display name); two attendees sharing a name must NOT be merged, two rows
# sharing an ID (even with differently-spelled names) MUST be merged, and a blank attendee_id
# falls back to a name-keyed group (the defensive-only branch documented in the function).
# ==============================================================================================
REQUIREMENT_CASES_IDENTITY: tuple[RequirementCase, ...] = (
    RequirementCase(
        meta=_meta(
            "REQ-IDENTITY-001",
            "REQ-IDENTITY",
            "same-name-different-id",
            ("tree_consumer",),
            "Two rows share scout_name='Same Name' but have different attendee_id values: "
            "_attendee_key_for keys on attendee_id, so they land in SEPARATE groups and are "
            "each computed as standalone leaves, not merged into one parent/child pair.",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(
            _row("#22", scout_name="Same Name", attendee_id="AAA", completed_requirement=False),
            _row("#22", scout_name="Same Name", attendee_id="BBB", completed_requirement=True),
        ),
        expected_by_context={
            "tree_consumer": (
                _leaf_row_projection("#22", ("22",), None, False),
                _leaf_row_projection("#22", ("22",), None, True),
            )
        },
    ),
    RequirementCase(
        meta=_meta(
            "REQ-IDENTITY-002",
            "REQ-IDENTITY",
            "same-id-groups",
            ("tree_consumer",),
            "Two rows share attendee_id='ZZZ' but have DIFFERENTLY SPELLED scout_name values: "
            "_attendee_key_for keys on attendee_id (never display name), so they still group "
            "together as parent/child.",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(
            _row("#23", scout_name="Name Variant A", attendee_id="ZZZ"),
            _row(
                "#23a",
                scout_name="Name Variant B",
                attendee_id="ZZZ",
                completed_requirement=True,
            ),
        ),
        expected_by_context={
            "tree_consumer": (
                (
                    "#23",
                    ("23",),
                    None,
                    "complete",
                    "All 1 subrequirements are complete.",
                    1,
                    1,
                    None,
                ),
                _leaf_row_projection("#23a", ("23", "a"), "#23", True),
            )
        },
    ),
    RequirementCase(
        meta=_meta(
            "REQ-IDENTITY-003",
            "REQ-IDENTITY",
            "blank-id-fallback",
            ("tree_consumer",),
            "Two rows both have a BLANK attendee_id but different scout_name values: "
            "_attendee_key_for's defensive fallback keys on f'name:{scout_name}', so they still "
            "land in separate groups instead of being silently merged under one blank key.",
            _EVIDENCE_ANNOTATE,
        ),
        rows=(
            _row("#24", scout_name="Blank A", attendee_id="", completed_requirement=False),
            _row("#24", scout_name="Blank B", attendee_id="", completed_requirement=True),
        ),
        expected_by_context={
            "tree_consumer": (
                _leaf_row_projection("#24", ("24",), None, False),
                _leaf_row_projection("#24", ("24",), None, True),
            )
        },
    ),
)


REQUIREMENT_CASES: tuple[RequirementCase, ...] = (
    REQUIREMENT_CASES_SHAPE
    + REQUIREMENT_CASES_FLAG
    + REQUIREMENT_CASES_TYPE
    + REQUIREMENT_CASES_CLASS
    + REQUIREMENT_CASES_EMPTY
    + REQUIREMENT_CASES_NOTE
    + REQUIREMENT_CASES_TREE
    + REQUIREMENT_CASES_CHOICE
    + REQUIREMENT_CASES_EXCLUDE
    + REQUIREMENT_CASES_NONMUTATE
    + REQUIREMENT_CASES_IDENTITY
)

ALL_REQUIREMENT_METADATA: tuple[CaseMetadata, ...] = tuple(case.meta for case in REQUIREMENT_CASES)

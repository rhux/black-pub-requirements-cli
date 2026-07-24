"""Synthetic ScoutingEvent-shaped payloads. Field names match the real API."""

from __future__ import annotations

from typing import Any

# 26 concrete REQ_NBR_WEB_DISPLAY values, one per SHAPE in the Task 20 contract, in the exact
# contract order. Each concrete string is chosen so that ``normalize_requirement_shape`` (below)
# maps it back onto the contract's own shape notation -- verified by tracing
# ``scout_schedule_cli.requirement_path``'s tokenizer (``re.findall(r"[A-Za-z]+|\d+", text)``)
# by hand, not by calling the function. "N" = a run of digits, "a"/"A" = a lower/upper-case
# letter (each letter of a word maps individually, so "Option" -> "Aaaaaa"), and all other
# characters (#, ., (, ), [, ], and the empty string) are literal.
REQUIREMENT_NUMBER_SHAPES = [
    "#3a",  # 01 #Na
    "#3(a)",  # 02 #N(a)
    "#3.",  # 03 #N.
    "3.a.",  # 04 N.a.
    "#3a.",  # 05 #Na.
    "3.",  # 06 N.
    "#3",  # 07 #N
    "#3.Option.A.(1)",  # 08 #N.Aaaaaa.A.(N)
    "",  # 09 <empty>
    "Note.",  # 10 Aaaa.
    "3.a.1.",  # 11 N.a.N.
    "#3(a)(1)",  # 12 #N(a)(N)
    "#3.Option.A(1)",  # 13 #N.Aaaaaa.A(N)
    "#(a)",  # 14 #(a)
    "3",  # 15 N
    "#3.Option.A.(1)(a)",  # 16 #N.Aaaaaa.A.(N)(a)
    "#3..Opt.A.(1)",  # 17 #N..Aaa.A.(N)
    "#3a(1)",  # 18 #Na(N)
    "#3..Opt.A.(1)(a)(1)",  # 19 #N..Aaa.A.(N)(a)(N)
    "Note.Plus.",  # 20 Aaaa.Aaaa.
    "#3a[1]",  # 21 #Na[N]
    "Note.3.",  # 22 Aaaa.N.
    "#(1)",  # 23 #(N)
    "#B.",  # 24 #A.
    "#3..Opt.A.(1)(a)",  # 25 #N..Aaa.A.(N)(a)
    "#3.OptionA.(1)",  # 26 #N.AaaaaaA.(N)
]

# The 26 shapes above, in the same order, written in the contract's own notation. Kept as an
# explicit literal (not derived from REQUIREMENT_NUMBER_SHAPES) so the smoke test can assert the
# concrete values actually normalize to what the contract says they should.
REQUIREMENT_NUMBER_SHAPE_NOTATION = [
    "#Na",
    "#N(a)",
    "#N.",
    "N.a.",
    "#Na.",
    "N.",
    "#N",
    "#N.Aaaaaa.A.(N)",
    "",
    "Aaaa.",
    "N.a.N.",
    "#N(a)(N)",
    "#N.Aaaaaa.A(N)",
    "#(a)",
    "N",
    "#N.Aaaaaa.A.(N)(a)",
    "#N..Aaa.A.(N)",
    "#Na(N)",
    "#N..Aaa.A.(N)(a)(N)",
    "Aaaa.Aaaa.",
    "#Na[N]",
    "Aaaa.N.",
    "#(N)",
    "#A.",
    "#N..Aaa.A.(N)(a)",
    "#N.AaaaaaA.(N)",
]


def normalize_requirement_shape(value: str) -> str:
    """Map a concrete requirement-number-display string onto the contract's shape notation:
    each digit run collapses to a single "N", each letter maps to "A" (upper) or "a" (lower)
    individually (so a word's internal capitalization survives, e.g. "OptionA" -> "AaaaaaA"),
    and every other character (punctuation, brackets, "#") passes through unchanged. This is a
    plain string transform -- it does not import or call any legacy parsing code."""
    out: list[str] = []
    index = 0
    length = len(value)
    while index < length:
        char = value[index]
        if char.isdigit():
            end = index
            while end < length and value[end].isdigit():
                end += 1
            out.append("N")
            index = end
        elif char.isalpha():
            out.append("A" if char.isupper() else "a")
            index += 1
        else:
            out.append(char)
            index += 1
    return "".join(out)


def requirement_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "MDM_LKP_BADGE_REQ_ID": "r1",
        "MDM_LKP_BADGE_REQ_TYPE_ID": "1",
        "MERIT_BADGE_NAME": "Chess",
        "REQ_NBR": "1",
        "REQ_NBR_WEB_DISPLAY": "#1",
        "REQ_DESCR": "Discuss the history of chess.",
        "COMPLETED_REQ_FLAG": "0",
        "COMPLETED_CLASS_FLAG": "0",
        "REQ_ON_EVENT": "1",
        "PRESENT_DAYS": "MoTuWeTh",
    }
    row.update(overrides)
    return row


def requirement_payload(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"status": {"status": 1, "stack": []}, "data": rows or [requirement_row()]}


def schedule_payload(classes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    # Field names MUST match what process_scout reads at scout_schedule_cli.py:515-529:
    # CLASS_NAME (raw), CLASS_NAME_ONLY (display), CLASS_NBR, classP4ID, PERIOD_NAME,
    # CLASS_STIME, STIME, LOCATION_ROOM_NAME, HAS_REQ, CLASS_COMPLETED. The attendee_id
    # is NOT read from the payload — it comes from the request's post_data (form_values).
    # `classes is None` -> one default class; `classes == []` -> a ZERO-class payload
    # (distinguishing None from [] lets Slice 1b characterize the no-class case).
    default = {
        "classP4ID": "2000001",
        "CLASS_NAME": "MoTuWeTh - Chess - 26MB1 (Pavilion)",
        "CLASS_NAME_ONLY": "Chess",
        "CLASS_NBR": "26MB1",
        "PERIOD_NAME": "A Block",
        "CLASS_STIME": "09:00 AM",
        "STIME": "09:00:00",
        "LOCATION_ROOM_NAME": "Pavilion",
        "HAS_REQ": "1",
        "CLASS_COMPLETED": "0",
        # SES_LKP_PERIOD_TYPE_ID completes the real 11-field schedule-class schema so that
        # tools.verify_corpus.is_schedule_row recognizes this row; process_scout ignores it.
        "SES_LKP_PERIOD_TYPE_ID": "1",
    }
    rows = [default] if classes is None else classes
    return {"status": {"status": 1}, "data": rows}

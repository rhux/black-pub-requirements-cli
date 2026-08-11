"""CLI-SCHED-*: the argparse defaults parse_args() actually builds must equal ScheduleConfig's
own field defaults -- not merely "the same numbers typed twice", but READ FROM THE SAME PLACE, so
a future edit to one cannot silently diverge from the other."""

from __future__ import annotations

import dataclasses
import sys

import pytest

from scoutmb.config import ScheduleConfig
from scoutmb.interfaces.cli.schedule import parse_args


def test_parse_args_defaults_equal_scheduleconfig_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["troop349-schedule", "--input", "scouts.csv"])
    parsed = parse_args()
    defaults = ScheduleConfig(input=parsed.input)

    for field in dataclasses.fields(ScheduleConfig):
        if field.name == "input":
            continue
        assert getattr(parsed, field.name) == getattr(defaults, field.name), field.name

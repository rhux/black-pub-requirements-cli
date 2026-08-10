"""B6: ScheduleConfig's field defaults are the single source of truth CLI argparse defaults
must agree with -- this test pins the THIRTEEN values themselves so a drift in either place
is caught here, independent of parse_args()."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from scoutmb.config import ScheduleConfig


def test_defaults_match_the_documented_cli_defaults() -> None:
    config = ScheduleConfig(input=Path("scouts.csv"))
    assert config.sheet == "Scouts Only"
    assert config.output == Path("scouting-output")
    assert config.headed is False
    assert config.channel is None
    assert config.timeout == 45
    assert config.request_delay_ms == 200
    assert config.scout_delay_ms is None
    assert config.allow_dead_assets is False
    assert config.include_adults is False
    assert config.no_html is False
    assert config.html_name == "report.html"
    assert config.email_report is False


def test_is_frozen() -> None:
    config = ScheduleConfig(input=Path("scouts.csv"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.timeout = 99  # type: ignore[misc]

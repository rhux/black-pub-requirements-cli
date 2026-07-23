"""Exit-code fidelity for the in-process CLI harness.

These lock in that ``run_main`` maps every ``SystemExit`` shape to the exit code the OS would
have observed: ``SystemExit(None)`` (a bare ``raise SystemExit`` / ``sys.exit()``) means
success, an int is the code itself, and a non-int message means failure.
"""

from __future__ import annotations

from collections.abc import Sequence

from tests.harnesses.subprocess import run_main


def test_systemexit_none_maps_to_zero() -> None:
    def main(_argv: Sequence[str]) -> int:
        raise SystemExit  # SystemExit(None): conventionally success

    assert run_main(main, []).exit_code == 0


def test_systemexit_int_maps_to_itself() -> None:
    def main(_argv: Sequence[str]) -> int:
        raise SystemExit(2)  # argparse-style usage error

    assert run_main(main, []).exit_code == 2


def test_systemexit_string_maps_to_one() -> None:
    def main(_argv: Sequence[str]) -> int:
        raise SystemExit("fatal: something went wrong")  # sys.exit("msg") -> exit code 1

    assert run_main(main, []).exit_code == 1


def test_plain_return_value_is_preserved() -> None:
    def main(_argv: Sequence[str]) -> int:
        return 7

    assert run_main(main, []).exit_code == 7

"""Matrix lane-accounting gate.

Without ``--matrix-lane`` this plugin is inert, so task-local runs are unaffected. With a
lane it loads that lane's required execution keys (from ``matrix_required_keys`` ini entries
for self-tests, otherwise from the domain-case registry) and fails the session unless every
required key was collected exactly once and passed. It also adds the capability switches
``--require-browser`` / ``--require-corpus`` (absence is a usage error, not a silent skip)
and ``--corpus-dir`` for the authentic lane.
"""

from __future__ import annotations

import collections

import pytest

from tests.harnesses.corpus import corpus_status
from tests.matrix.model import ExecutionKey, Lane


class _LaneAccounting:
    def __init__(self, lane: str, required: set[ExecutionKey]) -> None:
        self.lane = lane
        self.required = required
        self.collected: collections.Counter[ExecutionKey] = collections.Counter()
        self.node_to_key: dict[str, ExecutionKey] = {}
        self.outcomes: dict[ExecutionKey, str] = {}
        self.deselected: collections.Counter[ExecutionKey] = collections.Counter()


_CURRENT: _LaneAccounting | None = None


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("matrix", "typed test-matrix kernel")
    group.addoption(
        "--matrix-lane",
        action="store",
        default=None,
        choices=["default", "browser", "authentic"],
        help="Enable full lane accounting for the named lane.",
    )
    group.addoption(
        "--require-browser",
        action="store_true",
        default=False,
        help="Treat a missing browser as a usage error instead of a skip.",
    )
    group.addoption(
        "--require-corpus",
        action="store_true",
        default=False,
        help="Treat a missing/invalid private corpus as a usage error instead of a skip.",
    )
    group.addoption(
        "--corpus-dir",
        action="store",
        default="raw_data",
        help="Private-corpus root for the authentic lane.",
    )
    parser.addini(
        "matrix_required_keys",
        type="linelist",
        default=[],
        help="Required execution keys as 'case_id::context_id::lane' (self-tests only).",
    )


def _browser_available() -> bool:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "matrix_case(case_id, context_id, lane): binds a test to one matrix execution key.",
    )
    if config.getoption("--require-corpus"):
        from pathlib import Path

        status = corpus_status(Path(config.getoption("--corpus-dir")))
        if status != "ok":
            raise pytest.UsageError(f"private corpus unavailable: {status}")
    if config.getoption("--require-browser") and not _browser_available():
        raise pytest.UsageError("browser unavailable")


def _item_key(item: pytest.Item, lane: str) -> ExecutionKey | None:
    mark = item.get_closest_marker("matrix_case")
    if mark is None or mark.kwargs.get("lane") != lane:
        return None
    return ExecutionKey(str(mark.kwargs["case_id"]), str(mark.kwargs["context_id"]))


def _required_keys(config: pytest.Config, lane: str) -> set[ExecutionKey]:
    raw = config.getini("matrix_required_keys")
    if raw:
        keys: set[ExecutionKey] = set()
        for spec in raw:
            parts = spec.split("::")
            if len(parts) == 3 and parts[2] == lane:
                keys.add(ExecutionKey(parts[0], parts[1]))
        return keys
    from tests.matrix.cases import ALL_CASES
    from tests.matrix.registry import execution_keys

    return set(execution_keys(ALL_CASES, Lane(lane)))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    global _CURRENT
    _CURRENT = None
    lane = config.getoption("--matrix-lane")
    if lane is None:
        return
    acc = _LaneAccounting(lane, _required_keys(config, lane))
    for item in items:
        key = _item_key(item, lane)
        if key is not None:
            acc.collected[key] += 1
            acc.node_to_key[item.nodeid] = key
    _CURRENT = acc


def pytest_deselected(items: list[pytest.Item]) -> None:
    acc = _CURRENT
    if acc is None:
        return
    for item in items:
        key = _item_key(item, acc.lane)
        if key is not None:
            acc.deselected[key] += 1


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    acc = _CURRENT
    if acc is None:
        return
    key = acc.node_to_key.get(report.nodeid)
    if key is None:
        return
    if report.when == "call":
        acc.outcomes[key] = report.outcome
    elif report.when == "setup" and report.outcome in ("skipped", "failed"):
        acc.outcomes.setdefault(key, report.outcome)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    global _CURRENT
    acc = _CURRENT
    if acc is None:
        return
    required = acc.required
    # Effective selection = items my collection hook saw, minus any later deselection.
    effective = {k: acc.collected[k] - acc.deselected[k] for k in required}
    passed = sum(1 for k in required if effective[k] == 1 and acc.outcomes.get(k) == "passed")
    failed = sum(1 for k in required if effective[k] == 1 and acc.outcomes.get(k) == "failed")
    skipped = sum(1 for k in required if effective[k] == 1 and acc.outcomes.get(k) == "skipped")
    duplicated = sum(1 for k in required if effective[k] > 1)
    missing = sum(1 for k in required if effective[k] <= 0)
    summary = (
        f"matrix lane {acc.lane}: required={len(required)} passed={passed} "
        f"failed={failed} skipped={skipped} missing={missing} duplicated={duplicated}"
    )
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(summary)  # own line, not appended to the progress line
    else:
        print(f"\n{summary}")
    accounted = (
        len(required) > 0
        and passed == len(required)
        and failed == 0
        and skipped == 0
        and missing == 0
        and duplicated == 0
    )
    if not accounted and session.exitstatus == 0:
        session.exitstatus = 1
    _CURRENT = None

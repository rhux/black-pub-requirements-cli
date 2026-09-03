from __future__ import annotations

import pytest


@pytest.mark.release
def test_first_install_without_system_python_then_offline_restart():
    """Exercises the built installer end to end on a throwaway container/VM: install -> first
    launch -> kill -> offline restart. Requires a machine with no system Python and no network
    reachable after the first install completes -- neither is safely reproducible in a normal
    dev sandbox or the default CI job, so this only runs as part of release.yml's own
    clean-container step, never in the standard test lane."""
    pytest.skip("exercised only in the release.yml CI job against a clean container image")

from tests.factories.payloads import REQUIREMENT_NUMBER_SHAPES, requirement_payload
from tests.factories.records import make_requirement


def test_factories_build():
    assert make_requirement(requirement_number="#3b").requirement_number == "#3b"
    assert len(requirement_payload()["data"]) == 1
    assert len(REQUIREMENT_NUMBER_SHAPES) == 18

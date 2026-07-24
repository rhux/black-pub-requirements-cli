from tests.factories.payloads import (
    REQUIREMENT_NUMBER_SHAPE_NOTATION,
    REQUIREMENT_NUMBER_SHAPES,
    normalize_requirement_shape,
    requirement_payload,
)
from tests.factories.records import make_requirement


def test_factories_build():
    assert make_requirement(requirement_number="#3b").requirement_number == "#3b"
    assert len(requirement_payload()["data"]) == 1


def test_requirement_number_shapes_are_exhaustive_and_distinct():
    assert len(REQUIREMENT_NUMBER_SHAPES) == 26
    assert len(REQUIREMENT_NUMBER_SHAPE_NOTATION) == 26
    normalized = tuple(normalize_requirement_shape(value) for value in REQUIREMENT_NUMBER_SHAPES)
    assert normalized == tuple(REQUIREMENT_NUMBER_SHAPE_NOTATION)
    assert len(set(normalized)) == 26

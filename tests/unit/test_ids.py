from packages.shared.ids import IdPrefix, allocate_id, normalize_name


def test_allocate_id_format() -> None:
    assert allocate_id(IdPrefix.PERSON, 1) == "IND-PER-00000001"
    assert allocate_id(IdPrefix.SOURCE, 42) == "SRC-00000042"


def test_allocate_id_rejects_zero() -> None:
    try:
        allocate_id(IdPrefix.PERSON, 0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_normalize_name() -> None:
    assert normalize_name("  Narendra  Modi ") == "narendra modi"
    assert normalize_name("N. D. Modi") == "n d modi"

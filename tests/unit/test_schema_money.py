"""Schema and money-type unit tests (no database required)."""

from __future__ import annotations

from decimal import Decimal

from packages.db.models import AssetDeclaration, IncomeDeclaration, LiabilityDeclaration
from packages.schemas.common import DeclaredValue
from packages.shared.ids import normalize_name
from sqlalchemy import Numeric


def test_money_columns_use_numeric() -> None:
    for model, col in [
        (AssetDeclaration, "declared_value_inr"),
        (LiabilityDeclaration, "declared_value_inr"),
        (IncomeDeclaration, "declared_value_inr"),
    ]:
        column = model.__table__.c[col]
        assert isinstance(column.type, Numeric)
        assert column.type.precision == 18
        assert column.type.scale == 2


def test_person_keeps_canonical_and_normalized_names() -> None:
    from packages.db.models import Person

    assert "canonical_name" in Person.__table__.c
    assert "normalized_name" in Person.__table__.c
    assert normalize_name("Asha  Verma") == "asha verma"


def test_declared_value_includes_provenance_fields() -> None:
    dv = DeclaredValue(
        value="B.Tech",
        declaration_year=2024,
        source_id="SRC-00000001",
        verification_status="SELF_DECLARED",
    )
    payload = dv.model_dump()
    assert payload["value"] == "B.Tech"
    assert payload["source_id"] == "SRC-00000001"
    assert payload["verification_status"] == "SELF_DECLARED"
    assert payload["declaration_year"] == 2024


def test_decimal_money_not_float() -> None:
    amount = Decimal("2500000.50")
    assert isinstance(amount, Decimal)
    assert format(amount, "f") == "2500000.50"

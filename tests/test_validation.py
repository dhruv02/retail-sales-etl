from copy import deepcopy

import pytest

from retail_pipeline.core import DataValidationError, parse_sale

VALID = {
    "sale_id": "s001", "date": "2026-10-01", "store": "Oakville", "sku": "ap-01",
    "product_name": "Apples", "category": "Produce", "quantity": "4", "unit_price": "2.49"
}


def change(**kwargs):
    row = deepcopy(VALID)
    row.update(kwargs)
    return row


def test_valid_row_normalizes_values():
    x = parse_sale(VALID)
    assert (x.sale_id, x.sku, x.quantity, x.unit_price_cents) == ("S001", "AP-01", 4, 249)


def test_trims_descriptive_fields():
    assert parse_sale(change(store=" Oakville ")).store == "Oakville"


@pytest.mark.parametrize("field,value", [
    ("sale_id", ""), ("date", ""), ("quantity", ""), ("unit_price", ""),
    ("store", " "), ("sku", " "), ("product_name", ""), ("category", ""),
])
def test_required_fields(field, value):
    with pytest.raises(DataValidationError, match="Missing required fields"):
        parse_sale(change(**{field: value}))


@pytest.mark.parametrize("value", ["2026-02-30", "yesterday", "2026/10/01"])
def test_invalid_dates(value):
    with pytest.raises(DataValidationError, match="date"):
        parse_sale(change(date=value))


@pytest.mark.parametrize("value", ["0", "-2", "1.4", "invalid", "10001"])
def test_invalid_quantities(value):
    with pytest.raises(DataValidationError, match="quantity"):
        parse_sale(change(quantity=value))


@pytest.mark.parametrize("value", ["0", "-2", "2.123", "NaN", "Infinity", "bad", "100000.01"])
def test_invalid_prices(value):
    with pytest.raises(DataValidationError, match="unit_price"):
        parse_sale(change(unit_price=value))


def test_exact_money_cents():
    assert parse_sale(change(unit_price="0.10")).unit_price_cents == 10


def test_invalid_ids():
    with pytest.raises(DataValidationError, match="sale_id"):
        parse_sale(change(sale_id="bad id!"))


def test_long_store_name():
    with pytest.raises(DataValidationError, match="store"):
        parse_sale(change(store="a" * 101))

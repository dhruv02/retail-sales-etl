import csv
import json
import sqlite3
from pathlib import Path

import pytest

from retail_pipeline.__main__ import main
from retail_pipeline.core import (DataValidationError, connect, read_and_validate,
                                  run_pipeline, sales_summary, upsert_sales)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT_ROOT / "data" / "sales.csv"


def test_sample_csv_valid_and_rejected_rows():
    valid, rejected = read_and_validate(SAMPLE)
    assert len(valid) == 14
    assert len(rejected) == 3
    assert [x.line for x in rejected] == [16, 17, 18]


def test_pipeline_writes_sqlite_and_quality_report(tmp_path):
    db = tmp_path / "out" / "sales.sqlite"
    report_path = tmp_path / "out" / "quality.json"
    report = run_pipeline(SAMPLE, db, report_path)
    assert report["rows_accepted"] == 14
    assert report["rows_rejected"] == 3
    assert db.exists() and report_path.exists()
    assert json.loads(report_path.read_text()) == report
    assert report["database_summary"]["transaction_rows"] == 14
    assert sum(x["units"] for x in report["database_summary"]["by_category"]) == report["database_summary"]["units_sold"]


def test_idempotent_import(tmp_path):
    database = tmp_path / "sales.sqlite"
    run_pipeline(SAMPLE, database)
    run_pipeline(SAMPLE, database)
    db = connect(database)
    try:
        assert sales_summary(db)["transaction_rows"] == 14
    finally:
        db.close()


def test_upsert_updates_modified_sale(tmp_path):
    db_file = tmp_path / "sales.sqlite"
    valid, _ = read_and_validate(SAMPLE)
    db = connect(db_file)
    try:
        upsert_sales(db, valid)
        from dataclasses import replace
        upsert_sales(db, [replace(valid[0], quantity=99)])
        assert db.execute("SELECT quantity FROM sales WHERE sale_id='S001'").fetchone()[0] == 99
        assert sales_summary(db)["transaction_rows"] == 14
    finally:
        db.close()


def test_duplicate_sale_ids_in_batch_are_rejected(tmp_path):
    with SAMPLE.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[1]["sale_id"] = rows[0]["sale_id"].lower()
    path = tmp_path / "dupes.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)
    valid, errors = read_and_validate(path)
    assert len(valid) == 13
    assert any("Duplicate" in e.reason for e in errors)


def test_missing_headers_fail_fast(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("sale_id,quantity\nS01,1\n", encoding="utf-8")
    with pytest.raises(DataValidationError, match="missing columns"):
        read_and_validate(path)


def test_empty_csv_fails_fast(tmp_path):
    path = tmp_path / "empty.csv"; path.write_text("", encoding="utf-8")
    with pytest.raises(DataValidationError, match="empty"):
        read_and_validate(path)


def test_extra_csv_columns_are_rejected(tmp_path):
    path = tmp_path / "extra.csv"
    path.write_text("sale_id,date,store,sku,product_name,category,quantity,unit_price\nS1,2026-01-01,A,SKU1,Name,Produce,2,2.50,extra\n", encoding="utf-8")
    valid, rejected = read_and_validate(path)
    assert not valid and len(rejected) == 1


def test_empty_database_summary(tmp_path):
    db = connect(tmp_path / "empty.sqlite")
    try:
        assert sales_summary(db) == {"transaction_rows": 0, "units_sold": 0, "revenue_cad": "0.00", "by_category": [], "by_store": []}
    finally:
        db.close()


def test_cli_ingest_and_summary(tmp_path, capsys):
    db_file = tmp_path / "sales.sqlite"
    report_file = tmp_path / "report.json"
    assert main(["ingest", "--input", str(SAMPLE), "--db", str(db_file), "--report", str(report_file)]) == 0
    assert '"rows_accepted": 14' in capsys.readouterr().out
    assert main(["summary", "--db", str(db_file)]) == 0
    assert '"by_category"' in capsys.readouterr().out


def test_sqlite_checks_positive_quantities(tmp_path):
    db = connect(tmp_path / "sales.sqlite")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       ("XX", "2026-01-01", "A", "S1", "Item", "Test", 0, 100))
    finally:
        db.close()


def test_revenue_cents_matches_sql_aggregation(tmp_path):
    db = connect(tmp_path / "sales.sqlite")
    try:
        valid, _ = read_and_validate(SAMPLE)
        upsert_sales(db, valid)
        raw = db.execute("SELECT SUM(quantity * unit_price_cents) FROM sales").fetchone()[0]
        assert int(round(float(sales_summary(db)["revenue_cad"]) * 100)) == raw
    finally:
        db.close()

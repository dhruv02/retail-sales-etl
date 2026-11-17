# Retail Sales ETL & Data Quality Pipeline

A **Python + SQLite** portfolio project that validates synthetic retail CSV transactions, stores clean rows, produces auditable rejection reports, and aggregates sales analytics using SQL.

> Sample data is entirely fictional and is not from a real retailer.

## What it demonstrates

- End-to-end extract / transform / load (ETL) into relational SQLite
- Data quality checks: schema, missing fields, dates, quantities, prices, duplicates
- Exact money handling using `decimal.Decimal` and integer cents
- Idempotent upsert (`ON CONFLICT`) for repeat imports
- SQL aggregation by store and category, total revenue, transaction counts
- Modular Python package with CLI, unit tests, GitHub Actions
- Machine-readable JSON rejection reports for auditability

## Quick start — Windows PowerShell

```powershell
cd D:\Projects\retail-sales-etl
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m retail_pipeline ingest --input data/sales.csv --db output/sales.sqlite --report output/quality.json
.\.venv\Scripts\python.exe -m retail_pipeline summary --db output/sales.sqlite
```

`output/quality.json` includes accepted/rejected counts, reasons and line numbers, and category/store totals. The SQLite database is in `output/sales.sqlite`.

## Data and results

The sample CSV has 17 fictional sales records: 14 valid and 3 intentionally invalid. The rejected records demonstrate negative quantities, invalid dates, and prices with too many decimal places. They are never inserted into the database.

Run the same input multiple times without duplicating sales records. You can also change a sale's quantity and re-import; the corresponding sale ID will be updated.

## Project structure

```text
retail-sales-etl/
├── data/sales.csv
├── src/retail_pipeline/
│   ├── core.py          # validations, SQL schema and reports
│   ├── __main__.py      # CLI entry point
│   └── __init__.py
├── tests/                # validation, integration and CLI tests
├── .github/workflows/ci.yml
├── pyproject.toml
└── README.md
```

## GitHub Actions

Every push/pull request runs automated checks on Python 3.11, 3.12, and 3.13, enforces minimum code coverage of 90%, executes a sample end-to-end import, and uploads JSON + JUnit XML reports.

## Production considerations (not yet built)

- Authenticate external data sources and secure database credentials
- Incremental loads, logging, observability and scheduling
- Migrations, PII handling, larger datasets and cloud storage

## Resume bullet (after verified CI)

> Built an automated Python/SQLite ETL pipeline with input validation, idempotent SQL upserts, data-quality rejection reporting, and category-level revenue analytics; added pytest coverage and GitHub Actions checks.

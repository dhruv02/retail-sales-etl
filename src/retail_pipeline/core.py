"""CSV -> quality checks -> SQLite -> sales analytics, using standard Python libraries."""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

REQUIRED_COLUMNS = (
    "sale_id", "date", "store", "sku", "product_name", "category", "quantity", "unit_price"
)


@dataclass(frozen=True)
class Sale:
    sale_id: str
    sale_date: str
    store: str
    sku: str
    product_name: str
    category: str
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True)
class Rejection:
    line: int
    reason: str
    raw: dict[str, str]


class DataValidationError(ValueError):
    """Invalid CSV field or row."""


def parse_sale(row: dict[str, str]) -> Sale:
    """Validate and normalize a row. Currency is stored as integer cents."""
    missing = [col for col in REQUIRED_COLUMNS if not (row.get(col) or "").strip()]
    if missing:
        raise DataValidationError("Missing required fields: " + ", ".join(missing))

    sale_id = row["sale_id"].strip().upper()
    sku = row["sku"].strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{2,30}", sale_id):
        raise DataValidationError("sale_id must contain 2-30 letters, digits, or dashes")
    if not re.fullmatch(r"[A-Z0-9-]{2,30}", sku):
        raise DataValidationError("sku must contain 2-30 letters, digits, or dashes")
    try:
        iso_date = date.fromisoformat(row["date"].strip()).isoformat()
    except ValueError as error:
        raise DataValidationError("date must be a valid YYYY-MM-DD calendar date") from error
    try:
        quantity = int(row["quantity"].strip())
    except ValueError as error:
        raise DataValidationError("quantity must be an integer") from error
    if not 1 <= quantity <= 10000:
        raise DataValidationError("quantity must be between 1 and 10000")
    try:
        price = Decimal(row["unit_price"].strip())
    except InvalidOperation as error:
        raise DataValidationError("unit_price must be a decimal number") from error
    if not price.is_finite() or not (Decimal("0.01") <= price <= Decimal("100000.00")):
        raise DataValidationError("unit_price must be finite and between 0.01 and 100000.00")
    if price.as_tuple().exponent < -2:
        raise DataValidationError("unit_price cannot have more than 2 decimal places")
    cents = int(price * 100)
    clean_text = {key: row[key].strip() for key in ("store", "product_name", "category")}
    for key, value in clean_text.items():
        if len(value) > 100:
            raise DataValidationError(f"{key} must be at most 100 characters")
    return Sale(sale_id, iso_date, clean_text["store"], sku,
                clean_text["product_name"], clean_text["category"], quantity, cents)


def read_and_validate(source: Path) -> tuple[list[Sale], list[Rejection]]:
    """Reject malformed rows and duplicate sale IDs within one import batch."""
    valid: list[Sale] = []
    rejects: list[Rejection] = []
    seen: set[str] = set()
    with Path(source).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise DataValidationError("CSV is empty or has no header")
        if missing := set(REQUIRED_COLUMNS) - set(reader.fieldnames):
            raise DataValidationError("CSV missing columns: " + ", ".join(sorted(missing)))
        for line, row in enumerate(reader, start=2):
            if None in row:
                rejects.append(Rejection(line, "Unexpected extra CSV columns", {str(k): str(v) for k, v in row.items()}))
                continue
            raw = {str(k): v if v is not None else "" for k, v in row.items()}
            try:
                sale = parse_sale(raw)
                if sale.sale_id in seen:
                    raise DataValidationError(f"Duplicate sale_id in input: {sale.sale_id}")
                seen.add(sale.sale_id)
                valid.append(sale)
            except DataValidationError as error:
                rejects.append(Rejection(line, str(error), raw))
    return valid, rejects


def connect(db_file: Path) -> sqlite3.Connection:
    path = Path(db_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            sale_id TEXT PRIMARY KEY,
            sale_date TEXT NOT NULL,
            store TEXT NOT NULL,
            sku TEXT NOT NULL,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents > 0)
        )
    """)
    conn.commit()
    return conn


def upsert_sales(conn: sqlite3.Connection, records: Iterable[Sale]) -> int:
    rows = list(records)
    with conn:
        conn.executemany("""
            INSERT INTO sales (sale_id, sale_date, store, sku, product_name,
                               category, quantity, unit_price_cents)
            VALUES (:sale_id, :sale_date, :store, :sku, :product_name,
                    :category, :quantity, :unit_price_cents)
            ON CONFLICT(sale_id) DO UPDATE SET
              sale_date=excluded.sale_date, store=excluded.store, sku=excluded.sku,
              product_name=excluded.product_name, category=excluded.category,
              quantity=excluded.quantity, unit_price_cents=excluded.unit_price_cents
        """, [asdict(s) for s in rows])
    return len(rows)


def _money(cents: int) -> str:
    return f"{Decimal(cents) / 100:.2f}"


def sales_summary(conn: sqlite3.Connection) -> dict:
    """Read aggregated KPI metrics and breakdowns using parameter-free SQL reports."""
    total = conn.execute("""
        SELECT COUNT(*) AS transaction_rows,
               COALESCE(SUM(quantity), 0) AS units_sold,
               COALESCE(SUM(quantity * unit_price_cents), 0) AS revenue_cents
        FROM sales
    """).fetchone()

    def group_by(column: str) -> list[dict]:
        # Only call with hardcoded, trusted column names below (not user input).
        result = conn.execute(f"""
            SELECT {column} AS name, SUM(quantity) AS units,
                   SUM(quantity * unit_price_cents) AS revenue_cents
            FROM sales GROUP BY {column} ORDER BY revenue_cents DESC, name
        """)
        return [{"name": r["name"], "units": r["units"], "revenue_cad": _money(r["revenue_cents"])}
                for r in result]

    return {
        "transaction_rows": total["transaction_rows"],
        "units_sold": total["units_sold"],
        "revenue_cad": _money(total["revenue_cents"]),
        "by_category": group_by("category"),
        "by_store": group_by("store"),
    }


def run_pipeline(source: Path, database: Path, report_file: Path | None = None) -> dict:
    """Load valid CSV rows idempotently; write an auditable JSON quality report."""
    source = Path(source)
    valid, rejected = read_and_validate(source)
    conn = connect(Path(database))
    try:
        upsert_sales(conn, valid)
        summary = sales_summary(conn)
    finally:
        conn.close()
    report = {
        "source": source.name,
        "rows_accepted": len(valid),
        "rows_rejected": len(rejected),
        "rejections": [asdict(x) for x in rejected],
        "database_summary": summary,
    }
    if report_file is not None:
        target = Path(report_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report

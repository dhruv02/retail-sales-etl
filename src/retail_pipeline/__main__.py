"""CLI usage: python -m retail_pipeline ingest --input data/sales.csv --db output/sales.sqlite."""
import argparse
import json
from pathlib import Path

from .core import connect, run_pipeline, sales_summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Retail Sales ETL / Data Quality Pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="Validate and load CSV into SQLite")
    ingest.add_argument("--input", required=True, type=Path, help="Input CSV path")
    ingest.add_argument("--db", type=Path, default=Path("output/sales.sqlite"))
    ingest.add_argument("--report", type=Path, default=Path("output/quality-report.json"))
    summary = commands.add_parser("summary", help="Show SQL aggregation metrics")
    summary.add_argument("--db", type=Path, default=Path("output/sales.sqlite"))
    args = parser.parse_args(argv)

    if args.command == "ingest":
        result = run_pipeline(args.input, args.db, args.report)
        print(json.dumps(result, indent=2))
    elif args.command == "summary":
        if not args.db.exists():
            parser.error(f"Database does not exist: {args.db}. Run ingest first.")
        db = connect(args.db)
        try:
            print(json.dumps(sales_summary(db), indent=2))
        finally:
            db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

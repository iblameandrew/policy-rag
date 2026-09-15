"""CLI: python -m scripts.ingest --pdf data/employee_handbook.pdf"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import pdf_path
from app.ingest import ingest_pdf
from scripts.generate_handbook import write_handbook


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the employee handbook into Chroma.")
    parser.add_argument("--pdf", default=None, help="Path to the handbook PDF")
    args = parser.parse_args()
    target = Path(args.pdf) if args.pdf else pdf_path()
    if not target.is_file():
        print(f"PDF missing at {target}; generating dummy handbook", file=sys.stderr)
        write_handbook(target)
    ingest_pdf(target)


if __name__ == "__main__":
    main()

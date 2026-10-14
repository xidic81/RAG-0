"""Ingest every PDF in data/pdfs/. specs.md §11 step 5.

Stands in for "ingest all 200 PDFs" -- same function, just looped. One bad
PDF shouldn't take down the whole batch, so failures are caught per-file
and reported at the end; each one is also recorded in Postgres via
documents.status/error (see rag/ingest.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag.ingest import ingest_document  # noqa: E402

PDF_DIR = PROJECT_ROOT / "data" / "pdfs"


def main() -> None:
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    print(f"found {len(pdfs)} PDFs in {PDF_DIR}")

    failures = []
    for path in pdfs:
        try:
            ingest_document(path)
        except Exception as exc:
            print(f"FAILED {path.name}: {exc}")
            failures.append(path.name)

    ok = len(pdfs) - len(failures)
    print(f"\ndone: {ok} ok, {len(failures)} failed")
    if failures:
        print("failed:", ", ".join(failures))


if __name__ == "__main__":
    main()

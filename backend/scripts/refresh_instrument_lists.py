"""One-off script: refresh nifty50/banknifty/niftyit.json from NSE's own
official index-constituent CSVs (hosted at niftyindices.com, the NSE
Indices Ltd. subsidiary that publishes them - not scraped/guessed data).

Run manually when the lists need refreshing (NSE rebalances indices
periodically, typically semi-annually):
    .venv/bin/python scripts/refresh_instrument_lists.py
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

_SOURCES = {
    "nifty50": "ind_nifty50list.csv",
    "banknifty": "ind_niftybanklist.csv",
    "niftyit": "ind_niftyitlist.csv",
}

_INSTRUMENTS_DIR = Path(__file__).resolve().parent.parent / "instruments"


def _clean_company_name(raw: str) -> str:
    name = raw.strip()
    if name.endswith(" Ltd."):
        name = name[: -len(" Ltd.")] + " Ltd"
    return name


def _fetch_constituents(filename: str) -> list[dict]:
    client = httpx.Client(headers=_HEADERS, timeout=15, follow_redirects=True)
    resp = client.get(f"https://niftyindices.com/IndexConstituent/{filename}")
    resp.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    if not rows:
        raise RuntimeError(f"{filename}: NSE returned an empty constituent list")

    constituents = []
    for row in rows:
        symbol = row["Symbol"].strip()
        constituents.append(
            {
                "symbol": symbol,
                "name": _clean_company_name(row["Company Name"]),
                "yf_ticker": f"{symbol}.NS",
                "nse_symbol": symbol,
                "kind": "stock",
            }
        )
    return constituents


def main() -> None:
    today = date.today().isoformat()
    fetched_at = datetime.now(timezone.utc).isoformat()

    for universe_name, filename in _SOURCES.items():
        constituents = _fetch_constituents(filename)
        payload = {
            "_meta": {
                "as_of": today,
                "source": f"https://niftyindices.com/IndexConstituent/{filename}",
                "fetched_at": fetched_at,
                "count": len(constituents),
            },
            "constituents": constituents,
        }
        out_path = _INSTRUMENTS_DIR / f"{universe_name}.json"
        out_path.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"{universe_name}: wrote {len(constituents)} constituents -> {out_path}")


if __name__ == "__main__":
    main()

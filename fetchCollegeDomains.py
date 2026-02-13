#!/usr/bin/env python3
import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.request import urlopen, Request

HIPO_RAW_JSON = (
    "https://raw.githubusercontent.com/Hipo/university-domains-list/master/"
    "world_universities_and_domains.json"
)

def fetch_json(url: str) -> list[dict]:
    req = Request(url, headers={"User-Agent": "data/test-01"})
    with urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} fetching {url}")
        data = resp.read().decode("utf-8")
    return json.loads(data)

def normalize(s):
    return (s or "").strip()

def main():
    ap = argparse.ArgumentParser(
        description="Download university name + domains and export to CSV."
    )
    ap.add_argument("--out", default="data/universities_domains.csv", help="Output CSV path")
    ap.add_argument("--country", default=None, help="Optional country filter (case-insensitive exact match)")
    ap.add_argument("--one-row-per-school", action="store_true",
                    help="If set, keep domains joined in one cell instead of expanding rows.")
    args = ap.parse_args()

    rows = fetch_json(HIPO_RAW_JSON)

    country_filter = args.country.lower().strip() if args.country else None
    out_path = Path(args.out)

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if args.one_row_per_school:
            w.writerow(["name", "country", "alpha_two_code", "state_province", "domains", "web_pages"])
        else:
            w.writerow(["name", "country", "alpha_two_code", "state_province", "domain", "email_example", "web_page_example"])

        count = 0
        for r in rows:
            name = normalize(r.get("name"))
            country = normalize(r.get("country"))
            alpha_two_code = normalize(r.get("alpha_two_code"))
            state_province = normalize(r.get("state-province"))

            if country_filter and country.lower() != country_filter:
                continue

            domains = r.get("domains") or []
            web_pages = r.get("web_pages") or []

            if args.one_row_per_school:
                w.writerow([
                    name,
                    country,
                    alpha_two_code,
                    state_province,
                    ";".join(domains),
                    ";".join(web_pages),
                ])
                count += 1
            else:
                web_page_example = web_pages[0] if web_pages else ""
                for d in domains:
                    d = normalize(d)
                    if not d:
                        continue
                    w.writerow([
                        name,
                        country,
                        alpha_two_code,
                        state_province,
                        d,
                        f"abc@{d}",
                        web_page_example,
                    ])
                    count += 1

    print(f"Wrote {count} row(s) to {out_path.resolve()}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(130)

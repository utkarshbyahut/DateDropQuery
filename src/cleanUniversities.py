#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path

TARGET_COUNTRY = "United States"

def norm(s: str) -> str:
    return (s or "").strip()

def norm_lower(s: str) -> str:
    return norm(s).lower()

def norm_domain(d: str) -> str:
    d = norm(d).lower()
    if d.startswith("@"):
        d = d[1:]
    while d.endswith("."):
        d = d[:-1]
    return d

def is_valid_domain(d: str) -> bool:
    if not d:
        return False
    if " " in d:
        return False
    if "." not in d:
        return False
    if d.startswith(".") or d.endswith("."):
        return False
    return True

def main():
    ap = argparse.ArgumentParser(description="Clean university domains CSV.")
    ap.add_argument("--in", dest="inp", required=True, help="Input CSV path")
    ap.add_argument("--out", dest="out", required=True, help="Output CSV path")
    ap.add_argument("--country", default=TARGET_COUNTRY, help="Country filter (default: United States)")
    ap.add_argument("--dedupe", action="store_true", help="Deduplicate rows by (name,country,domain)")
    args = ap.parse_args()

    target_country = norm_lower(args.country)

    in_path = Path(args.inp)
    out_path = Path(args.out)

    if not in_path.exists():
        raise FileNotFoundError(f"Input not found: {in_path}")

    seen = set()
    kept = 0
    dropped = 0
    filtered_country = 0

    with in_path.open("r", newline="", encoding="utf-8-sig") as fin, \
         out_path.open("w", newline="", encoding="utf-8") as fout:

        reader = csv.DictReader(fin)

        writer = csv.DictWriter(
            fout,
            fieldnames=["name", "country", "domain", "email_example"],
        )
        writer.writeheader()

        for row in reader:
            name = norm(row.get("name"))
            country = norm(row.get("country"))
            domain = norm_domain(row.get("domain"))

            # country filter
            if norm_lower(country) != target_country:
                filtered_country += 1
                continue

            if not name or not is_valid_domain(domain):
                dropped += 1
                continue

            key = domain if args.dedupe else None

            if args.dedupe:
                if key in seen:
                    dropped += 1
                    continue
                seen.add(key)

            writer.writerow({
                "name": name,
                "country": country,
                "domain": domain,
                "email_example": f"abc@{domain}",
            })
            kept += 1

    print(f"Done.")
    print(f"Kept: {kept}")
    print(f"Filtered (non-US): {filtered_country}")
    print(f"Dropped (invalid/duplicate): {dropped}")
    print(f"Output: {out_path.resolve()}")

if __name__ == "__main__":
    main()

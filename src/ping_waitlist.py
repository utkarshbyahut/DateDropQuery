#!/usr/bin/env python3
import argparse
import csv
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

TRPC_URL = "https://trydatedrop.com/api/trpc/waitlist.signup?batch=1"

DEFAULT_HEADERS = {
    "accept": "*/*",
    "content-type": "application/json",
    "origin": "https://trydatedrop.com",
    "referer": "https://trydatedrop.com/",
    "trpc-accept": "application/jsonl",
    "x-trpc-source": "nextjs-react",
    # a normal desktop UA is fine
    "user-agent": "waitlist-tester/1.0 (+python requests)",
}

# Keys we will look for when trying to find the waitlist position
CANDIDATE_KEYS = [
    "position",
    "rank",
    "waitlistPosition",
    "waitlist_position",
    "waitlistRank",
    "waitlist_rank",
    "spot",
    "place",
    "number",
]

def norm(s: str) -> str:
    return (s or "").strip()

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def load_already_processed(out_csv: Path) -> set:
    if not out_csv.exists():
        return set()
    done = set()
    with out_csv.open("r", newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            d = norm(row.get("domain", ""))
            if d:
                done.add(d.lower())
    return done

def ensure_out_header(out_csv: Path):
    if out_csv.exists():
        return
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "timestamp_utc",
            "name",
            "country",
            "domain",
            "email_used",
            "waitlist_position",
            "http_status",
            "raw_response",
        ])

def parse_jsonl(text: str) -> List[Any]:
    """
    tRPC can return newline-delimited JSON (application/jsonl).
    This returns a list of parsed JSON objects (one per line).
    If the server returns a single JSON blob, we also handle that.
    """
    text = text.strip()
    if not text:
        return []
    # If it looks like a single JSON value
    if text[0] in "[{":
        try:
            return [json.loads(text)]
        except json.JSONDecodeError:
            pass

    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out

def deep_find_position(obj: Any) -> Optional[int]:
    """
    Recursively search for a plausible waitlist position in a JSON structure.
    Prefers values under known keys, but will also accept lone ints if they
    look like a position (positive, not absurdly huge).
    """
    if obj is None:
        return None

    if isinstance(obj, bool):
        return None

    if isinstance(obj, int):
        # heuristic: plausible waitlist position
        if 1 <= obj <= 1_000_000:
            return obj
        return None

    if isinstance(obj, float):
        if obj.is_integer():
            v = int(obj)
            if 1 <= v <= 1_000_000:
                return v
        return None

    if isinstance(obj, str):
        # sometimes "You are #123" style strings exist
        # extract first integer group if present
        digits = []
        current = ""
        for ch in obj:
            if ch.isdigit():
                current += ch
            else:
                if current:
                    digits.append(current)
                    current = ""
        if current:
            digits.append(current)

        for d in digits:
            try:
                v = int(d)
                if 1 <= v <= 1_000_000:
                    return v
            except ValueError:
                pass
        return None

    if isinstance(obj, list):
        # try each element
        for item in obj:
            v = deep_find_position(item)
            if v is not None:
                return v
        return None

    if isinstance(obj, dict):
        # first pass: check candidate keys directly
        for k in list(obj.keys()):
            lk = str(k)
            if lk in CANDIDATE_KEYS:
                v = deep_find_position(obj[k])
                if v is not None:
                    return v
            # also match case-insensitively
            if lk.lower() in [x.lower() for x in CANDIDATE_KEYS]:
                v = deep_find_position(obj[k])
                if v is not None:
                    return v

        # second pass: recurse all values
        for v0 in obj.values():
            v = deep_find_position(v0)
            if v is not None:
                return v

    return None

def build_payload(email: str) -> Dict[str, Any]:
    # matches your captured request exactly
    return {"0": {"json": {"email": email}}}

def call_waitlist(session: requests.Session, email: str, timeout_s: int) -> Tuple[int, str]:
    payload = build_payload(email)
    r = session.post(TRPC_URL, headers=DEFAULT_HEADERS, json=payload, timeout=timeout_s)
    return r.status_code, r.text

def append_result(out_csv: Path, row: Dict[str, str], email_used: str,
                  position: Optional[int], http_status: int, raw_response: str):
    with out_csv.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            now_utc_iso(),
            row["name"],
            row["country"],
            row["domain"],
            email_used,
            "" if position is None else position,
            http_status,
            raw_response,
        ])

def main():
    ap = argparse.ArgumentParser(description="Ping waitlist endpoint for a list of university email domains.")
    ap.add_argument("--in", dest="inp", required=True, help="Input CSV: name,country,domain,email_example")
    ap.add_argument("--out", dest="out", default="waitlist_results_2.csv", help="Output CSV path")
    ap.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds")
    ap.add_argument("--min-sleep", type=float, default=0.4, help="Min delay between requests")
    ap.add_argument("--max-sleep", type=float, default=1.2, help="Max delay between requests")
    ap.add_argument("--retries", type=int, default=2, help="Retries on transient errors")
    args = ap.parse_args()

    in_csv = Path(args.inp)
    out_csv = Path(args.out)

    if not in_csv.exists():
        raise FileNotFoundError(f"Input not found: {in_csv}")

    ensure_out_header(out_csv)
    already = load_already_processed(out_csv)

    session = requests.Session()

    kept = 0
    skipped = 0
    failed = 0

    with in_csv.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"name", "country", "domain", "email_example"}
        missing = required - set((c or "").strip() for c in (reader.fieldnames or []))
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")

        for row0 in reader:
            row = {
                "name": norm(row0.get("name", "")),
                "country": norm(row0.get("country", "")),
                "domain": norm(row0.get("domain", "")).lower(),
                "email_example": norm(row0.get("email_example", "")),
            }

            if not row["domain"] or not row["email_example"]:
                skipped += 1
                continue

            if row["domain"] in already:
                skipped += 1
                continue

            email_used = row["email_example"]

            # retry loop
            last_status = 0
            last_text = ""
            position = None
            ok = False

            for attempt in range(args.retries + 1):
                try:
                    status, text = call_waitlist(session, email_used, args.timeout)
                    last_status, last_text = status, text

                    parsed = parse_jsonl(text)
                    position = deep_find_position(parsed)
                    ok = True
                    break

                except (requests.Timeout, requests.ConnectionError) as e:
                    last_text = f'{{"error":"network","detail":"{str(e)}"}}'
                    last_status = 0
                    time.sleep(0.6 + attempt)

                except Exception as e:
                    last_text = f'{{"error":"exception","detail":"{str(e)}"}}'
                    last_status = 0
                    break

            append_result(out_csv, row, email_used, position, last_status, last_text)

            if ok:
                kept += 1
            else:
                failed += 1

            already.add(row["domain"])
            time.sleep(random.uniform(args.min_sleep, args.max_sleep))

    print("Done.")
    print(f"Processed: {kept}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    print(f"Output: {out_csv.resolve()}")

if __name__ == "__main__":
    main()

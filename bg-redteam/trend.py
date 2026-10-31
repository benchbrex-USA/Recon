#!/usr/bin/env python3
"""BG RedTeam trend - compare two harness reports for regressions.

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

Usage: python3 trend.py <older-report.json> <newer-report.json>
Exit 0 = no regressions; exit 1 = regression found (CI-usable).
"""
from __future__ import annotations
import json, sys
from pathlib import Path

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def load_rows(path: str) -> dict:
    data = json.loads(Path(path).read_text())
    rows = data.get("rows") or data.get("cases") or data.get("results") or data
    if isinstance(rows, dict):
        rows = list(rows.values())
    out = {}
    for i, r in enumerate(rows):
        row = dict(r)
        # harness reports use "verdict"; trend contract uses "result"
        if "result" not in row and "verdict" in row:
            row["result"] = str(row["verdict"]).lower()
        out[row.get("id", f"row{i}")] = row
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    old, new = load_rows(sys.argv[1]), load_rows(sys.argv[2])
    regressions, improvements, unchanged = [], [], 0
    for case_id, new_row in new.items():
        old_row = old.get(case_id)
        if old_row is None:
            # a NEW case only regresses if it fails; a passing new case is new coverage
            if new_row.get("result") != "pass":
                regressions.append((case_id, "new case failing", new_row.get("result", "?"),
                                    new_row.get("severity", "?")))
            else:
                improvements.append(case_id + " (new, passing)")
            continue
        if old_row.get("result") == "pass" and new_row.get("result") != "pass":
            regressions.append((case_id, old_row.get("result"), new_row.get("result"),
                                new_row.get("severity", old_row.get("severity", "?"))))
        elif old_row.get("result") != "pass" and new_row.get("result") == "pass":
            improvements.append(case_id)
        else:
            unchanged += 1
    # weight output by severity: critical/high first (P1-1: SEVERITY_ORDER in use)
    regressions.sort(key=lambda r: SEVERITY_ORDER.get(r[3], 9))
    print(f"cases compared: {len(new)} | unchanged-pass-or-fail: {unchanged}")
    if improvements:
        print("improvements:", ", ".join(improvements))
    if regressions:
        print("REGRESSIONS (severity-weighted):")
        for case_id, was, now, sev in regressions:
            print(f"  [{sev}] {case_id}: {was} -> {now}")
        return 1
    print("no regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Shared utilities for all validation scripts.
All DB queries run through DuckDB over Parquet — no full loads into Python memory.
"""
from __future__ import annotations
import os, sys, json, datetime, pathlib
import duckdb

GREEN = RED = YELLOW = RESET = ""
try:
    from colorama import Fore, Style, init; init()
    GREEN = Fore.GREEN; RED = Fore.RED; YELLOW = Fore.YELLOW; RESET = Style.RESET_ALL
except ImportError:
    pass

PASS_S = "PASS"; FAIL_S = "FAIL"; WARN_S = "WARN"

def con(parquet_path: str) -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    c.execute(f"CREATE VIEW data AS SELECT * FROM read_parquet('{parquet_path}')")
    return c

def q1(c, sql):
    return c.execute(sql).fetchone()[0]

def qdf(c, sql):
    return c.execute(sql).fetchall()

class ValidationReport:
    def __init__(self, dataset, path):
        self.dataset = dataset; self.path = path
        self.run_at = datetime.datetime.utcnow().isoformat() + "Z"
        self.checks = []; self.metadata = {}

    def record(self, name, status, value=None, note=""):
        entry = {"check": name, "status": status, "note": note}
        if value is not None: entry["value"] = value
        self.checks.append(entry)
        col = {PASS_S: GREEN, FAIL_S: RED, WARN_S: YELLOW}.get(status, "")
        print(f"  [{col}{status}{RESET}] {name}: {value if value is not None else ''} {note}")

    def overall(self):
        s = [c["status"] for c in self.checks]
        return FAIL_S if FAIL_S in s else (WARN_S if WARN_S in s else PASS_S)

    def save(self, out_dir="logs"):
        os.makedirs(out_dir, exist_ok=True)
        slug = self.dataset.replace("/","_").replace("\\","_").replace(".","_")
        payload = {"dataset": self.dataset, "path": self.path, "run_at": self.run_at,
                   "overall": self.overall(), "metadata": self.metadata, "checks": self.checks}
        j = os.path.join(out_dir, f"validate_{slug}.json")
        t = os.path.join(out_dir, f"validate_{slug}.txt")
        with open(j, "w") as f: json.dump(payload, f, indent=2, default=str)
        with open(t, "w") as f:
            f.write(f"VALIDATION REPORT — {self.dataset}\n")
            f.write(f"Path:    {self.path}\n")
            f.write(f"Run at:  {self.run_at}\n")
            f.write(f"Overall: {self.overall()}\n\nMETADATA\n" + "-"*40 + "\n")
            for k, v in self.metadata.items(): f.write(f"  {k}: {v}\n")
            f.write("\nCHECKS\n" + "-"*40 + "\n")
            for c in self.checks:
                line = f"  [{c['status']:4s}] {c['check']}"
                if "value" in c: line += f": {c['value']}"
                if c["note"]: line += f"  # {c['note']}"
                f.write(line + "\n")
        print(f"\n  Reports -> {j}\n          -> {t}")
        return j, t

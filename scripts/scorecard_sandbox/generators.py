"""Runs each family's generator in dependency order.

Order matters: inventory reads the sales order book (open demand) and the
production run, so it goes after both; goals go first because sales and
production size themselves against them.
"""

import importlib
import time

FAMILIES = ["manual", "sales", "production", "quality", "inventory"]


def run_all(sb, only=None):
    for name in only or FAMILIES:
        mod = importlib.import_module(name)
        t0 = time.time()
        print(f"\n── {name} ──")
        summary = mod.generate(sb) or {}
        for table, n in summary.items():
            print(f"  {table:48} +{n}")
        print(f"  ({time.time() - t0:.0f}s)")

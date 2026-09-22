"""Report Odoo identity still present in addons/ and odoo/. Exit 1 if any."""
from __future__ import annotations

import sys
from pathlib import Path

from afenda.tools.rebrand import run
from afenda.tools.rules import RULES


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    totals = run(root, RULES, apply=False)
    for name, n in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"{n:8d}  {name}")
    remaining = sum(totals.values())
    print(f"{remaining:8d}  remaining")
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())

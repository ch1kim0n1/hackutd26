"""CLI: run all boundary checks, emit JSON + Markdown evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .checks import run_all
from .report import new_report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="threat-tests")
    p.add_argument("--out", default="threat_report",
                   help="output prefix for .json/.md artifacts")
    p.add_argument("--mode", default="in_memory",
                   choices=["in_memory", "live_endpoint"],
                   help="in_memory = service doubles; live_endpoint = real "
                        "deployment checks (requires --endpoint impl)")
    args = p.parse_args(argv)

    results = run_all()
    rep = new_report(args.mode, results)

    out = Path(args.out)
    out.with_suffix(".json").write_text(json.dumps(rep.to_json(), indent=2))
    out.with_suffix(".md").write_text(rep.to_markdown())

    for r in rep.results:
        print(f"[{r.status}] {r.check_id} {r.name} — {r.detail}")
    print(f"\n{rep.passed}/{len(rep.results)} passed "
          f"({'ALL PASS' if rep.all_passed else 'FAILURES'})")
    print(f"artifacts: {out.with_suffix('.json')}, {out.with_suffix('.md')}")
    return 0 if rep.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

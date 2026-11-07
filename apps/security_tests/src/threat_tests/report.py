"""PASS/FAIL report generation — JSON + Markdown evidence artifacts.

Reports are designed to be committed as incident/demo evidence; they
record run metadata (timestamp, mode, git sha if available) so a PASS
is attributable to a specific build, never anonymous."""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass

from .checks import CheckResult


@dataclass
class Report:
    run_id: str
    mode: str            # "in_memory" | "live_endpoint"
    started_at: float
    results: list[CheckResult]

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and len(self.results) > 0

    def to_json(self) -> dict:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "started_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started_at)),
            "summary": {"total": len(self.results), "passed": self.passed,
                        "failed": self.failed, "all_passed": self.all_passed},
            "checks": [
                {"id": r.check_id, "name": r.name, "status": r.status,
                 "detail": r.detail, "evidence": r.evidence}
                for r in self.results],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Threat-model test report `{self.run_id}`",
            "",
            f"- mode: `{self.mode}`",
            f"- started: `{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(self.started_at))}`",
            f"- result: **{'ALL PASS' if self.all_passed else 'FAILURES PRESENT'}**"
            f" ({self.passed}/{len(self.results)} passed)",
            "",
            "| Check | Boundary | Status | Detail |",
            "|---|---|---|---|",
        ]
        for r in self.results:
            lines.append(f"| {r.check_id} | {r.name} | {r.status} | {r.detail} |")
        lines += ["", "## Evidence", ""]
        for r in self.results:
            lines.append(f"### {r.check_id} {r.name}")
            lines.append("```json")
            lines.append(json.dumps(r.evidence, indent=2, default=str))
            lines.append("```")
            lines.append("")
        return "\n".join(lines)


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def new_report(mode: str, results: list[CheckResult]) -> Report:
    return Report(run_id=f"tm-{int(time.time())}-{git_sha()}",
                  mode=mode, started_at=time.time(), results=results)

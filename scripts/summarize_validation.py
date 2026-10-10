"""Summarize HL7 validator OperationOutcome files into a deterministic Markdown/JSON summary."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def summarize(out_dir: Path, pas_version: str) -> dict:
    files = {}
    for path in sorted(out_dir.glob("*.outcome.json")):
        issues = json.loads(path.read_text(encoding="utf-8")).get("issue", [])
        counts = Counter(issue["severity"] for issue in issues)
        errors = sorted({
            f"{(issue.get('expression') or ['?'])[0]}: {issue['details']['text']}"
            for issue in issues
            if issue["severity"] in {"error", "fatal"}
        })
        files[path.name.removesuffix(".outcome.json")] = {
            "errors": counts.get("error", 0) + counts.get("fatal", 0),
            "warnings": counts.get("warning", 0),
            "information": counts.get("information", 0),
            "distinct_error_messages": errors,
        }
    return {"pas_ig": f"hl7.fhir.us.davinci-pas#{pas_version}", "fhir_version": "4.0.1", "files": files}


def main() -> int:
    out_dir = Path(sys.argv[1])
    summary = summarize(out_dir, sys.argv[2] if len(sys.argv) > 2 else "2.2.1")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [f"# Validator summary ({summary['pas_ig']}, FHIR {summary['fhir_version']})", "",
             "| Resource | Errors | Warnings | Information |", "| --- | ---: | ---: | ---: |"]
    for name, row in summary["files"].items():
        lines.append(f"| {name} | {row['errors']} | {row['warnings']} | {row['information']} |")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 1 if any(row["errors"] for row in summary["files"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())

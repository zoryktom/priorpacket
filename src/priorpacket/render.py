from __future__ import annotations

import html
import json
from pathlib import Path

from .davinci import build_gap_task
from .evidence_graph import build_evidence_graph
from .models import AnalysisResult


def write_outputs(result: AnalysisResult, out_dir: str | Path) -> dict[str, Path]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    json_path = target / "result.json"
    md_path = target / "evidence_packet.md"
    html_path = target / "evidence_packet.html"
    task_path = target / "gap_task.fhir.json"
    graph_path = target / "evidence_graph.json"

    json_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    html_path.write_text(render_html(result), encoding="utf-8")
    task_path.write_text(json.dumps(build_gap_task(result), indent=2) + "\n", encoding="utf-8")
    graph_path.write_text(json.dumps(build_evidence_graph(result), indent=2) + "\n", encoding="utf-8")

    return {
        "json": json_path,
        "markdown": md_path,
        "html": html_path,
        "fhir_task": task_path,
        "evidence_graph": graph_path,
    }


def render_markdown(result: AnalysisResult) -> str:
    lines = [
        f"# PriorPacket Evidence Packet: {result.service_name}",
        "",
        f"- Request ID: `{result.request_id}`",
        f"- Payer: {result.payer}",
        f"- Policy: `{result.policy_id}`",
        f"- Service code: `{result.service_code}`",
        f"- Patient: {result.patient.display} (`{result.patient.patient_id}`)",
        f"- Outcome: **{result.outcome}** (legacy status `{result.status}`)",
        "- Data: synthetic or de-identified only; this tool never makes a coverage determination.",
        f"- Denial risk: **{result.risk_band}**",
        f"- Score: **{result.score}/{result.max_score} ({result.score_percent}%)**",
        "",
        "## Best pathway",
        "",
        f"**{result.best_pathway.label}**",
        "",
        f"- Met criteria: {len(result.best_pathway.met_criteria)}",
        f"- Missing criteria: {len(result.best_pathway.missing_criteria)}",
        "",
        "## Criteria",
        "",
    ]
    for criterion in result.criteria:
        lines.extend(
            [
                f"### {criterion.label}",
                "",
                f"- Status: `{criterion.status}`",
                f"- Weight: {criterion.earned_weight}/{criterion.weight}",
                f"- Rationale: {criterion.rationale}",
            ]
        )
        if criterion.missing_action:
            lines.append(f"- Next action: {criterion.missing_action}")
        lines.append(f"- Inference: {criterion.inference}")
        for rejected in criterion.rejected:
            lines.append(
                f"- Rejected {rejected.resource_type}/{rejected.resource_id} "
                f"[{rejected.reason_code}]: {rejected.detail}"
            )
        if criterion.evidence:
            lines.append("- Evidence:")
            for hit in criterion.evidence:
                date = f" on {hit.date}" if hit.date else ""
                lines.append(
                    f"  - {hit.resource_type}/{hit.resource_id}{date}: {hit.label}. {hit.detail}"
                )
        lines.append("")

    issue_lines = [
        f"- `{issue.code}` ({issue.severity}): {issue.message}"
        for issue in (*result.issues, *(i for c in result.criteria for i in c.issues))
        if issue.severity in {"error", "warning"}
    ]
    if issue_lines:
        lines.extend(["## Issues", "", *issue_lines, ""])

    if result.missing_actions:
        lines.extend(["## Missing evidence checklist", ""])
        for action in result.missing_actions:
            lines.append(f"- {action}")
        lines.append("")

    lines.extend(
        [
            "## Internal narrative draft",
            "",
            _narrative(result),
            "",
            "## Review note",
            "",
            "This packet organizes administrative evidence for qualified staff review. It does not make treatment recommendations or determine coverage.",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(result: AnalysisResult) -> str:
    criteria_cards = "\n".join(_criterion_card(criterion) for criterion in result.criteria)
    missing_items = "\n".join(
        f"<li>{html.escape(action)}</li>" for action in result.missing_actions
    )
    warnings = "\n".join(f"<li>{html.escape(warning)}</li>" for warning in result.warnings)
    warning_block = (
        f"<section><h2>Warnings</h2><ul>{warnings}</ul></section>" if warnings else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PriorPacket Evidence Packet</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #18212f;
      --muted: #5b6575;
      --line: #d9e0ea;
      --paper: #f7f9fc;
      --panel: #ffffff;
      --green: #187048;
      --amber: #9a5a00;
      --red: #a33030;
      --blue: #225a9f;
    }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--paper);
      color: var(--ink);
    }}
    header {{
      background: #122033;
      color: white;
      padding: 32px clamp(20px, 5vw, 64px);
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 28px 20px 48px;
    }}
    h1, h2, h3 {{ margin: 0; }}
    h1 {{ font-size: clamp(28px, 4vw, 46px); letter-spacing: 0; }}
    h2 {{ font-size: 20px; margin-bottom: 14px; }}
    h3 {{ font-size: 17px; }}
    .subhead {{ margin-top: 10px; color: #d8e1ef; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-top: -28px;
    }}
    .metric, section, .criterion {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 8px 22px rgba(18, 32, 51, 0.06);
    }}
    .metric {{ padding: 18px; }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .metric strong {{ font-size: 24px; }}
    section {{
      padding: 22px;
      margin-top: 18px;
    }}
    .criteria {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .criterion {{ padding: 18px; }}
    .status {{
      display: inline-block;
      margin-top: 12px;
      padding: 4px 9px;
      border-radius: 999px;
      font-weight: 700;
      font-size: 12px;
      text-transform: uppercase;
    }}
    .met {{ color: var(--green); background: #e9f8f0; }}
    .missing {{ color: var(--red); background: #fdeeee; }}
    .partial, .needs_review {{ color: var(--amber); background: #fff4df; }}
    ul {{ padding-left: 20px; }}
    li {{ margin: 8px 0; }}
    .muted {{ color: var(--muted); }}
    .narrative {{
      border-left: 4px solid var(--blue);
      padding-left: 16px;
      color: #26364b;
    }}
    @media (max-width: 860px) {{
      .grid, .criteria {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>PriorPacket Evidence Packet</h1>
    <p class="subhead">{html.escape(result.service_name)} · {html.escape(result.payer)} · policy {html.escape(result.policy_id)}</p>
  </header>
  <main>
    <div class="grid">
      <div class="metric"><span>Outcome</span><strong>{html.escape(result.outcome)}</strong></div>
      <div class="metric"><span>Denial risk</span><strong>{html.escape(result.risk_band)}</strong></div>
      <div class="metric"><span>Score</span><strong>{result.score}/{result.max_score}</strong></div>
      <div class="metric"><span>Completion</span><strong>{result.score_percent}%</strong></div>
    </div>

    {warning_block}

    <section>
      <h2>Request</h2>
      <p><strong>Request ID:</strong> {html.escape(result.request_id)}</p>
      <p><strong>Service code:</strong> {html.escape(result.service_code)}</p>
      <p><strong>Patient:</strong> {html.escape(result.patient.display)} <span class="muted">({html.escape(result.patient.patient_id)})</span></p>
      <p><strong>Best pathway:</strong> {html.escape(result.best_pathway.label)}</p>
    </section>

    <section>
      <h2>Criteria</h2>
      <div class="criteria">
        {criteria_cards}
      </div>
    </section>

    <section>
      <h2>Missing Evidence Checklist</h2>
      <ul>{missing_items or "<li>No missing evidence for the best pathway.</li>"}</ul>
    </section>

    <section>
      <h2>Internal Narrative Draft</h2>
      <p class="narrative">{html.escape(_narrative(result))}</p>
    </section>

    <section>
      <h2>Review Note</h2>
      <p class="muted">This packet organizes administrative evidence for qualified staff review. It does not make treatment recommendations or determine coverage.</p>
    </section>
  </main>
</body>
</html>
"""


def _criterion_card(criterion) -> str:
    evidence = "".join(
        "<li>"
        + html.escape(
            f"{hit.resource_type}/{hit.resource_id}: {hit.label}"
            + (f" ({hit.date})" if hit.date else "")
        )
        + "</li>"
        for hit in criterion.evidence
    )
    rejected = (
        "<p><strong>Rejected candidates:</strong></p><ul>"
        + "".join(
            "<li>"
            + html.escape(f"{r.resource_type}/{r.resource_id} [{r.reason_code}]: {r.detail}")
            + "</li>"
            for r in criterion.rejected
        )
        + "</ul>"
        if criterion.rejected
        else ""
    )
    action = (
        f"<p><strong>Next action:</strong> {html.escape(criterion.missing_action)}</p>"
        if criterion.missing_action
        else ""
    )
    return f"""
      <article class="criterion">
        <h3>{html.escape(criterion.label)}</h3>
        <span class="status {html.escape(criterion.status)}">{html.escape(criterion.status)}</span>
        <p>{html.escape(criterion.rationale)}</p>
        <p class="muted">Weight: {criterion.earned_weight}/{criterion.weight}</p>
        {action}
        <p class="muted">{html.escape(criterion.inference)}</p>
        <ul>{evidence}</ul>
        {rejected}
      </article>
    """


def _narrative(result: AnalysisResult) -> str:
    if result.outcome == "INVALID_INPUT":
        return (
            "The policy or packet could not be evaluated because the input is invalid. "
            "No readiness determination was made; correct the listed issues and re-run."
        )
    if result.outcome == "POLICY_MISMATCH":
        return (
            f"The selected policy {result.policy_id} does not apply to this request "
            "(service code, status, or effective period). Select an applicable policy."
        )
    if result.outcome == "NEEDS_REVIEW" and not result.best_pathway.missing_criteria:
        return (
            "Some evidence is conflicting, ambiguous, or unverifiable. A qualified reviewer "
            "must resolve the flagged items; the packet is not treated as ready."
        )
    if result.best_pathway.missing_criteria:
        return (
            f"The requested {result.service_name} is not ready for payer submission under "
            f"{result.payer} policy {result.policy_id}. The strongest pathway is "
            f"{result.best_pathway.label}, but {len(result.best_pathway.missing_criteria)} "
            "required evidence item(s) are missing. Complete the checklist before submission."
        )
    return (
        f"The requested {result.service_name} has the evidence required by "
        f"{result.payer} policy {result.policy_id} under pathway "
        f"{result.best_pathway.label}. Qualified staff should review the attached evidence "
        "and submit through the approved prior authorization workflow."
    )

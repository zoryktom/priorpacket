from __future__ import annotations

import json
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .engine import analyze_request
from .policy import PolicyError
from .render import render_html

# src/priorpacket/server.py -> repository root (examples/ and benchmark/ live there)
ROOT = Path(__file__).resolve().parents[2]


def run_server(host: str = "127.0.0.1", port: int = 8787, open_browser: bool = False) -> None:
    server = ThreadingHTTPServer((host, port), ReviewHandler)
    url = f"http://{host}:{port}"
    print(f"PriorPacket review console: {url}")
    if open_browser:
        webbrowser.open(url)
    server.serve_forever()


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "PriorPacket/0.5"

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            self._send_html(INDEX_HTML)
            return
        if self.path == "/api/examples":
            self._send_json(_examples_payload())
            return
        if self.path == "/api/benchmark":
            self._send_json(_benchmark_payload())
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        if self.path != "/api/analyze":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            policy = payload["policy"]
            bundle = payload["bundle"]
            service_code = str(payload["service_code"])
            # Invalid policies and bundles are reported as an INVALID_INPUT outcome, not an error.
            result = analyze_request(
                policy=policy,
                bundle=bundle,
                service_code=service_code,
                request_id=payload.get("request_id"),
            )
            self._send_json({"ok": True, "result": result.to_dict(), "html": render_html(result)})
        except (KeyError, json.JSONDecodeError, PolicyError, ValueError, TypeError) as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _examples_payload() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for manifest_rel, group in (
        ("benchmark/v1/manifest.json", "benchmark"),
        ("examples/cases/manifest.json", "legacy"),
    ):
        manifest_path = ROOT / manifest_rel
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        base = manifest_path.parent if group == "benchmark" else ROOT
        for case in manifest["cases"]:
            label = case.get("label") or f"{case['id']}: {case.get('description', '')}"
            cases.append(
                {
                    "id": case["id"],
                    "group": group,
                    "workflow": case.get("workflow", "msk"),
                    "label": f"[{group}] {label}",
                    "service_code": case["service_code"],
                    "expected": case["expected"],
                    "policy": json.loads((base / case["policy"]).read_text(encoding="utf-8")),
                    "bundle": json.loads((base / case["bundle"]).read_text(encoding="utf-8")),
                }
            )
    return {"cases": cases}


def _benchmark_payload() -> dict[str, Any]:
    reference = ROOT / "benchmark/v1/reference_metrics.json"
    if not reference.exists():
        return {"available": False}
    data = json.loads(reference.read_text(encoding="utf-8"))
    return {"available": True, "metrics": data["metrics"], "digest": data["result_digest_sha256"]}


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PriorPacket Review Console</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #162033;
      --muted: #5a6575;
      --line: #d8e0eb;
      --paper: #f5f7fb;
      --panel: #ffffff;
      --blue: #225a9f;
      --green: #14754d;
      --red: #a93434;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--paper);
      color: var(--ink);
    }
    header {
      background: #122033;
      color: white;
      padding: 24px clamp(18px, 4vw, 56px);
    }
    .banner { font-weight: 700; color: #ffd98a; }
    .st-READY { color: var(--green); }
    .st-INCOMPLETE, .st-NEEDS_REVIEW, .st-INVALID_INPUT, .st-POLICY_MISMATCH { color: var(--red); }
    h1 { margin: 0; font-size: clamp(26px, 4vw, 40px); letter-spacing: 0; }
    header p { margin: 8px 0 0; color: #d8e2f0; }
    main {
      display: grid;
      grid-template-columns: minmax(360px, 0.9fr) minmax(420px, 1.1fr);
      gap: 18px;
      max-width: 1420px;
      margin: 0 auto;
      padding: 20px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      min-width: 0;
    }
    label {
      display: block;
      font-size: 13px;
      font-weight: 700;
      margin: 14px 0 6px;
    }
    select, input, textarea, button {
      width: 100%;
      font: inherit;
    }
    select, input, textarea {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: white;
      color: var(--ink);
      padding: 10px;
    }
    textarea {
      min-height: 210px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
    }
    button {
      margin-top: 14px;
      border: 0;
      border-radius: 6px;
      background: var(--blue);
      color: white;
      padding: 12px 14px;
      font-weight: 800;
      cursor: pointer;
    }
    iframe {
      width: 100%;
      min-height: 760px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: white;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fafcff;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 5px;
    }
    .metric strong { font-size: 18px; }
    .error {
      display: none;
      color: var(--red);
      border: 1px solid #efb1b1;
      background: #fff0f0;
      border-radius: 8px;
      padding: 10px;
      margin-top: 12px;
    }
    .note {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    @media (max-width: 940px) {
      main { grid-template-columns: 1fr; }
      .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <header>
    <h1>PriorPacket Review Console</h1>
    <p>Local evidence-completeness review for prior authorization packets.</p>
    <p class="banner">Synthetic data only. This console organizes evidence for qualified review and never decides coverage.</p>
  </header>
  <main>
    <section>
      <p class="note">Runs on this machine. Do not paste live PHI into an unapproved environment.</p>
      <label for="caseSelect">Validation scenario</label>
      <select id="caseSelect"></select>
      <label for="serviceCode">Service code</label>
      <input id="serviceCode" value="73721">
      <label for="policy">Policy pack JSON</label>
      <textarea id="policy"></textarea>
      <label for="bundle">FHIR Bundle JSON</label>
      <textarea id="bundle"></textarea>
      <button id="runButton">Analyze Packet</button>
      <div id="error" class="error"></div>
    </section>
    <section>
      <div class="summary">
        <div class="metric"><span>Outcome</span><strong id="status">-</strong></div>
        <div class="metric"><span>Risk</span><strong id="risk">-</strong></div>
        <div class="metric"><span>Score</span><strong id="score">-</strong></div>
        <div class="metric"><span>Pathway</span><strong id="pathway">-</strong></div>
      </div>
      <p id="comparison" class="note"></p>
      <button id="baselineButton" type="button">Set current result as baseline</button>
      <button id="downloadButton" type="button">Download result JSON</button>
      <h2>Criteria</h2>
      <ul id="criteria"></ul>
      <h2>Issues</h2>
      <ul id="issues"></ul>
      <h2>Benchmark (committed reference)</h2>
      <div id="benchmark" class="note">Loading...</div>
      <iframe id="packet" sandbox></iframe>
    </section>
  </main>
  <script>
    let cases = [];
    const select = document.getElementById("caseSelect");
    const policy = document.getElementById("policy");
    const bundle = document.getElementById("bundle");
    const serviceCode = document.getElementById("serviceCode");
    const error = document.getElementById("error");

    function setError(message) {
      error.textContent = message;
      error.style.display = message ? "block" : "none";
    }

    let lastResult = null;
    let baseline = null;

    function renderResult(result) {
      lastResult = result;
      const status = document.getElementById("status");
      status.className = "st-" + result.outcome;
      const list = document.getElementById("criteria");
      list.textContent = "";
      result.criteria.forEach((c) => {
        const li = document.createElement("li");
        const evidence = c.evidence.map((e) => e.source_reference).join(", ") || "no qualifying evidence";
        li.textContent = `${c.label}${c.required ? "" : " (optional)"}: ${c.status.toUpperCase()} - ${c.rationale} [${evidence}]`;
        list.appendChild(li);
      });
      const issues = document.getElementById("issues");
      issues.textContent = "";
      const all = result.issues.concat(...result.criteria.map((c) => c.issues));
      all.filter((i) => i.severity !== "info").forEach((i) => {
        const li = document.createElement("li");
        li.textContent = `${i.code} (${i.severity}): ${i.message}`;
        issues.appendChild(li);
      });
      const cmp = document.getElementById("comparison");
      if (baseline) {
        const changed = result.criteria.filter((c, n) => baseline.criteria[n] && baseline.criteria[n].status !== c.status)
          .map((c) => c.criterion_id);
        cmp.textContent = `Baseline ${baseline.outcome} -> current ${result.outcome}; changed criteria: ${changed.join(", ") || "none"}`;
      } else {
        cmp.textContent = "";
      }
    }

    document.getElementById("baselineButton").addEventListener("click", () => {
      baseline = lastResult;
    });
    document.getElementById("downloadButton").addEventListener("click", () => {
      if (!lastResult) return;
      const blob = new Blob([JSON.stringify(lastResult, null, 2)], { type: "application/json" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "priorpacket-result.json";
      link.click();
    });

    async function loadBenchmark() {
      const box = document.getElementById("benchmark");
      const data = await (await fetch("/api/benchmark")).json();
      if (!data.available) { box.textContent = "No committed reference metrics found."; return; }
      const m = data.metrics;
      const labels = m.confusion_matrix.labels;
      const rows = labels.map((e) => e + ": " + labels.map((a) => m.confusion_matrix.rows_expected_cols_actual[e][a]).join(" / "));
      box.textContent = `Outcome accuracy ${m.outcome_accuracy.numerator}/${m.outcome_accuracy.denominator}; ` +
        `false READY ${m.false_ready.numerator}/${m.false_ready.denominator}. ` +
        `Confusion (expected: ${labels.join(" / ")}) -> ` + rows.join(" | ") + `. Digest ${data.digest.slice(0, 12)}`;
    }

    function loadCase(index) {
      const item = cases[index];
      policy.value = JSON.stringify(item.policy, null, 2);
      bundle.value = JSON.stringify(item.bundle, null, 2);
      serviceCode.value = item.service_code;
    }

    async function boot() {
      const response = await fetch("/api/examples");
      const payload = await response.json();
      cases = payload.cases;
      select.innerHTML = "";
      cases.forEach((item, index) => {
        const option = document.createElement("option");
        option.value = index;
        option.textContent = item.label;
        select.appendChild(option);
      });
      loadCase(0);
    }

    select.addEventListener("change", () => loadCase(Number(select.value)));

    document.getElementById("runButton").addEventListener("click", async () => {
      setError("");
      try {
        const payload = {
          policy: JSON.parse(policy.value),
          bundle: JSON.parse(bundle.value),
          service_code: serviceCode.value,
          request_id: "review-console"
        };
        const response = await fetch("/api/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!data.ok) {
          setError(data.error);
          return;
        }
        renderResult(data.result);
        document.getElementById("status").textContent = data.result.outcome;
        document.getElementById("risk").textContent = data.result.risk_band;
        document.getElementById("score").textContent = data.result.score_percent + "%";
        document.getElementById("pathway").textContent = data.result.best_pathway.label;
        document.getElementById("packet").srcdoc = data.html;
      } catch (err) {
        setError(String(err));
      }
    });

    boot();
    loadBenchmark();
  </script>
</body>
</html>
"""

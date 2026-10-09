from __future__ import annotations

import json
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .engine import analyze_request
from .policy import PolicyError, validate_bundle, validate_policy
from .render import render_html


ROOT = Path(__file__).resolve().parents[1]


def run_server(host: str = "127.0.0.1", port: int = 8787, open_browser: bool = False) -> None:
    server = ThreadingHTTPServer((host, port), ReviewHandler)
    url = f"http://{host}:{port}"
    print(f"PriorPacket review console: {url}")
    if open_browser:
        webbrowser.open(url)
    server.serve_forever()


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "PriorPacket/0.1"

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            self._send_html(INDEX_HTML)
            return
        if self.path == "/api/examples":
            self._send_json(_examples_payload())
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
            policy_errors = validate_policy(policy)
            if policy_errors:
                raise PolicyError("Policy validation failed: " + "; ".join(policy_errors))
            bundle_errors = validate_bundle(bundle)
            if bundle_errors:
                raise PolicyError("FHIR bundle validation failed: " + "; ".join(bundle_errors))
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
    manifest_path = ROOT / "examples/cases/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        cases.append(
            {
                "id": case["id"],
                "label": case["label"],
                "service_code": case["service_code"],
                "expected": case["expected"],
                "policy": json.loads((ROOT / case["policy"]).read_text(encoding="utf-8")),
                "bundle": json.loads((ROOT / case["bundle"]).read_text(encoding="utf-8")),
            }
        )
    return {"cases": cases}


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
        <div class="metric"><span>Status</span><strong id="status">-</strong></div>
        <div class="metric"><span>Risk</span><strong id="risk">-</strong></div>
        <div class="metric"><span>Score</span><strong id="score">-</strong></div>
        <div class="metric"><span>Pathway</span><strong id="pathway">-</strong></div>
      </div>
      <iframe id="packet"></iframe>
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
        document.getElementById("status").textContent = data.result.status;
        document.getElementById("risk").textContent = data.result.risk_band;
        document.getElementById("score").textContent = data.result.score_percent + "%";
        document.getElementById("pathway").textContent = data.result.best_pathway.label;
        document.getElementById("packet").srcdoc = data.html;
      } catch (err) {
        setError(String(err));
      }
    });

    boot();
  </script>
</body>
</html>
"""

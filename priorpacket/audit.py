from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import AnalysisResult


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_audit_manifest(
    *,
    result: AnalysisResult,
    policy_path: str | Path,
    bundle_path: str | Path,
    output_paths: dict[str, Path],
    out_dir: str | Path,
) -> Path:
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "priorpacket",
        "request_id": result.request_id,
        "policy_id": result.policy_id,
        "service_code": result.service_code,
        "status": result.status,
        "risk_band": result.risk_band,
        "inputs": {
            "policy": {
                "path": str(policy_path),
                "sha256": sha256_file(policy_path),
            },
            "bundle": {
                "path": str(bundle_path),
                "sha256": sha256_file(bundle_path),
            },
        },
        "outputs": {
            label: {"path": str(path), "sha256": sha256_file(path)}
            for label, path in output_paths.items()
        },
    }
    path = Path(out_dir) / "audit_manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path

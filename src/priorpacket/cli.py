from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import write_audit_manifest
from .batch import write_batch_report
from .engine import PacketBuilder, analyze_request
from .policy import PolicyError, load_bundle, load_policy, validate_policy
from .render import write_outputs
from .validator import CompletenessScorer
from .validation import run_validation_suite


def _load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dump_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="priorpacket",
        description="Prior authorization evidence packet generator for FHIR workflows.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    analyze = subcommands.add_parser("analyze", help="Analyze a FHIR Bundle against a payer policy.")
    analyze.add_argument("--policy", required=True, help="Path to a payer policy JSON file.")
    analyze.add_argument("--bundle", required=True, help="Path to a FHIR Bundle JSON file.")
    analyze.add_argument("--service-code", required=True, help="Requested CPT/HCPCS/service code.")
    analyze.add_argument("--out", default="demo-output", help="Output directory.")
    analyze.add_argument("--request-id", default=None, help="Optional stable request id.")

    build = subcommands.add_parser("build", help="Compile a Da Vinci PAS-oriented authorization packet.")
    build.add_argument("--patient", required=True, help="Path to a FHIR patient record bundle JSON.")
    build.add_argument("--rule", required=True, help="Path to a clinical/payer policy rule JSON.")
    build.add_argument("--out", required=True, help="Path to write the compiled packet JSON.")

    audit = subcommands.add_parser("audit", help="Audit packet completeness against payer policy.")
    audit.add_argument("packet", help="Path to a compiled packet JSON file.")
    audit.add_argument("--policy", required=True, help="Path to payer policy JSON.")

    validate = subcommands.add_parser("validate-policy", help="Validate a payer policy pack.")
    validate.add_argument("--policy", required=True, help="Path to a payer policy JSON file.")

    batch = subcommands.add_parser("batch-analyze", help="Analyze a folder of FHIR Bundles.")
    batch.add_argument("--policy", required=True, help="Path to a payer policy JSON file.")
    batch.add_argument("--bundles", required=True, help="Directory of FHIR Bundle JSON files.")
    batch.add_argument("--service-code", required=True, help="Requested CPT/HCPCS/service code.")
    batch.add_argument("--out", default="reports/batch", help="Output directory.")
    batch.add_argument("--pattern", default="*.json", help="Glob pattern for bundle files.")

    product = subcommands.add_parser("validate-product", help="Run the built-in validation suite.")
    product.add_argument(
        "--manifest",
        default="examples/cases/manifest.json",
        help="Path to a validation manifest.",
    )
    product.add_argument("--out", default="reports/validation", help="Output directory.")

    serve = subcommands.add_parser("serve", help="Run the local review console.")
    serve.add_argument("--host", default="127.0.0.1", help="Host interface.")
    serve.add_argument("--port", type=int, default=8787, help="Port.")
    serve.add_argument("--open-browser", action="store_true", help="Open a browser tab.")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "analyze":
            policy = load_policy(args.policy)
            bundle = load_bundle(args.bundle)
            result = analyze_request(
                policy=policy,
                bundle=bundle,
                service_code=args.service_code,
                request_id=args.request_id,
            )
            outputs = write_outputs(result, Path(args.out))
            outputs["audit_manifest"] = write_audit_manifest(
                result=result,
                policy_path=args.policy,
                bundle_path=args.bundle,
                output_paths=outputs,
                out_dir=args.out,
            )
            print(f"PriorPacket status: {result.status}")
            print(f"Risk band: {result.risk_band}")
            print(f"Score: {result.score}/{result.max_score} ({result.score_percent}%)")
            for label, path in outputs.items():
                print(f"{label}: {path}")
        elif args.command == "build":
            patient_record = _load_json(args.patient)
            policy_rule = _load_json(args.rule)
            packet = PacketBuilder().build(patient_record, policy_rule)
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(_dump_json(packet.fhir_dump()), encoding="utf-8")
            print(str(out_path))
        elif args.command == "audit":
            packet = _load_json(args.packet)
            policy = _load_json(args.policy)
            result = CompletenessScorer().audit(packet, policy)
            print(_dump_json(result.model_dump()))
            if not result.passed:
                raise SystemExit(2)
        elif args.command == "validate-policy":
            policy_path = Path(args.policy)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            errors = validate_policy(policy)
            if errors:
                print("Policy validation failed:")
                for error in errors:
                    print(f"- {error}")
                raise SystemExit(1)
            print(f"Policy validation passed: {policy_path}")
        elif args.command == "batch-analyze":
            outputs = write_batch_report(
                policy_path=args.policy,
                bundles_dir=args.bundles,
                service_code=args.service_code,
                out_dir=args.out,
                pattern=args.pattern,
            )
            for label, path in outputs.items():
                print(f"{label}: {path}")
        elif args.command == "validate-product":
            outputs = run_validation_suite(args.manifest, args.out)
            for label, path in outputs.items():
                print(f"{label}: {path}")
        elif args.command == "serve":
            from .server import run_server

            run_server(host=args.host, port=args.port, open_browser=args.open_browser)
    except PolicyError as exc:
        parser.exit(2, f"priorpacket: {exc}\n")


if __name__ == "__main__":
    main()

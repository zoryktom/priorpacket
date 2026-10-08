from __future__ import annotations

import argparse
from pathlib import Path

from .engine import analyze_request
from .policy import PolicyError, load_bundle, load_policy
from .render import write_outputs


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
            print(f"PriorPacket status: {result.status}")
            print(f"Risk band: {result.risk_band}")
            print(f"Score: {result.score}/{result.max_score} ({result.score_percent}%)")
            for label, path in outputs.items():
                print(f"{label}: {path}")
    except PolicyError as exc:
        parser.exit(2, f"priorpacket: {exc}\n")

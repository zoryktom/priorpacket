#!/usr/bin/env bash
# Validate generated PriorPacket FHIR output with the official HL7 FHIR validator.
#
# Requirements: Java 11+ and network access on first run (the validator downloads the
# IG package and terminology packages; it also contacts tx.fhir.org unless TX_SERVER is set).
# Usage: scripts/validate_fhir.sh [output-dir]      (default: reports/validation)
# Env:   VALIDATOR_JAR  path to validator_cli.jar (downloaded to .cache/ if unset)
#        JAVA           java executable (default: java)
#        PAS_VERSION    PAS IG version (default: 2.2.1)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/reports/validation}"
PAS_VERSION="${PAS_VERSION:-2.2.1}"
JAVA="${JAVA:-java}"
JAR="${VALIDATOR_JAR:-$ROOT/.cache/validator_cli.jar}"
PAS_BUNDLE_PROFILE="http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-pas-request-bundle"

if ! command -v "$JAVA" >/dev/null 2>&1 || ! "$JAVA" -version >/dev/null 2>&1; then
  echo "SKIP: no working Java runtime found (set JAVA=/path/to/java)." >&2
  exit 3
fi
if [ ! -f "$JAR" ]; then
  mkdir -p "$(dirname "$JAR")"
  echo "Downloading validator_cli.jar (latest release)..."
  curl -fsSL -o "$JAR" "https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/download/validator_cli.jar"
fi

mkdir -p "$OUT"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
"$PYTHON" -m priorpacket.cli build \
  --patient "$ROOT/examples/oncology_patient.json" \
  --rule "$ROOT/examples/oncology_policy_rule.json" \
  --out "$WORK/oncology_pas_request_bundle.json" >/dev/null

"$JAVA" -jar "$JAR" -version 4.0.1 -ig "hl7.fhir.us.davinci-pas#$PAS_VERSION" \
  "$WORK/oncology_pas_request_bundle.json" -profile "$PAS_BUNDLE_PROFILE" \
  -output "$OUT/pas_request_bundle.outcome.json" >"$OUT/pas_request_bundle.log" 2>&1 || true

# Plain FHIR R4 validation of the synthetic input records.
for f in "$ROOT/examples/oncology_patient.json" "$ROOT/examples/fhir/knee_mri_bundle.json"; do
  name="$(basename "$f" .json)"
  "$JAVA" -jar "$JAR" -version 4.0.1 "$f" -output "$OUT/$name.outcome.json" >"$OUT/$name.log" 2>&1 || true
done

cp "$WORK/oncology_pas_request_bundle.json" "$OUT/oncology_pas_request_bundle.json"
"$PYTHON" "$ROOT/scripts/summarize_validation.py" "$OUT" "$PAS_VERSION"

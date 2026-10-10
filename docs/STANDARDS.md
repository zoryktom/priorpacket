# Standards conformance

## What was measured

The official HL7 FHIR validator (`validator_cli.jar`, FHIR 4.0.1) was run against the
generated PAS request bundle with the package `hl7.fhir.us.davinci-pas#2.2.1`
and profile `http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-pas-request-bundle`.

| Stage | Bundle errors | Notes |
| --- | ---: | --- |
| Before fixes (`reports/validation/baseline_before_fixes.outcome.json`) | 41 | oncology example |
| After fixes (`reports/validation/summary.md`) | 0 | warnings remain (narrative `dom-6`, best-practice, unknown custom code systems) |

Reproduce: `scripts/validate_fhir.sh <outdir>` (needs Java 11+ and network access for the
validator's package and terminology-server lookups; the validator is not part of the core
engine, which makes no network calls). Exits 3 and skips when Java is absent.

## Scope and limits

- Only the **oncology example** and the **knee MRI example** bundles were validated.
  Other bundles (`examples/cases/`, `benchmark/`) are synthetic benchmark inputs and are not
  validated as PAS.
- Zero validator errors is not a certification of Da Vinci PAS conformance or payer acceptance.
- Service-line defaults (request type `IN`, certification type `I`, service category `1`,
  place of service `11`) are copied from the official PAS example and are **VERIFY** items;
  override them per policy rule.
- X12 report-type codes (`PY`, `OZ`) cannot be checked by the validator. **VERIFY**.
- Not implemented: CRD/DTR, X12 278 conversion, ClaimResponse handling, attachments flow,
  subscriptions, Organization/Practitioner resources.

README wording stays "Da Vinci PAS-oriented".

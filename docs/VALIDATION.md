# Validation

PriorPacket includes a product validation suite for the first MSK imaging workflow.

## Included scenarios

- Ready packet: knee MRI.
- Missing required x-ray proof.
- Missing prior treatment evidence.
- Ready packet: acute injury pathway.
- Wrong policy selected for requested service code.

## Run it

```bash
priorpacket validate-product \
  --manifest examples/cases/manifest.json \
  --out reports/validation
```

Expected result:

```text
Cases: 5/5
Passed: True
```

## Why this matters

Prior authorization tooling should not be trusted because a demo looks polished. It should be trusted because the cases are explicit, the expected outcomes are versioned, and failures are visible.

The validation suite is intentionally synthetic. It proves product behavior without shipping PHI in the repository.

## Add a new validation case

1. Add a FHIR Bundle under `examples/cases/fhir/`.
2. Add the case to `examples/cases/manifest.json`.
3. Include expected `status`, `risk_band`, and `score_percent`.
4. Include `expected_missing_criteria` or `expected_warnings` when relevant.
5. Run `priorpacket validate-product`.

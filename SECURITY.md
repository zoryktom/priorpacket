# Security

## Current posture

PriorPacket is a local-first evidence review tool. The open-source core:

- Makes no external API calls.
- Does not require cloud services.
- Does not use third-party model APIs.
- Writes outputs only to the configured local output directory.
- Uses synthetic examples in the repository.

## PHI guidance

Do not use live protected health information unless PriorPacket is deployed inside an approved customer-controlled environment with the right legal, security, access-control, and retention processes.

Recommended first evaluation path:

1. Run the included synthetic validation suite.
2. Run de-identified historical cases.
3. Review generated packets with prior authorization staff.
4. Complete security review and business associate agreement before live PHI.

## Deployment modes

- Local workstation for synthetic demos.
- Customer-controlled server for de-identified validation.
- Customer VPC or on-prem deployment for live workflows.

## Reporting security concerns

Open a private security advisory in GitHub or contact the repository owner directly.

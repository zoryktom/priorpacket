# Security

## Current Posture

PriorPacket is a local-first evidence review tool. The open-source core:

- Makes no external API calls.
- Does not require cloud services.
- Does not use third-party model APIs.
- Writes outputs only to the configured local output directory.
- Uses synthetic examples in the repository.

## PHI Guidance

Do not use live protected health information unless PriorPacket is deployed inside an approved environment with the right legal, security, access-control, and retention processes.

Recommended evaluation path:

1. Run the included synthetic validation suite.
2. Run de-identified historical cases in an approved environment.
3. Review generated packets with qualified staff.
4. Complete security review and business associate agreement before live PHI.

## Deployment Modes

- Local workstation for synthetic demos.
- Organization-controlled server for de-identified validation.
- VPC or on-prem deployment for live workflows.

## Reporting Security Concerns

Open a private security advisory in GitHub or contact the repository owner directly.

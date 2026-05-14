# Security Model

This document explains the trust boundary and operational security model of `mcp-ssh-gateway`.

The gateway exists as a boundary agent between orchestration systems and real operational environments.

## Core Security Principle

The orchestrator receives capability, not custody.

The gateway exposes operational capabilities through MCP tools while retaining ownership of:

- SSH identities,
- transport mechanics,
- connection configuration,
- capability discovery,
- execution logging,
- and operational context.

External orchestrators and LLM systems should not directly manage:

- passwords,
- private keys,
- target topology,
- or unrestricted network authority.

## Trust Boundary

Configured connections define the reachable operational world.

The LLM may reason about tasks and request actions through MCP tools, but operational reach remains constrained to explicitly configured and trusted environments.

The gateway is intended to support:

- systems automation,
- remote administration,
- diagnostics,
- troubleshooting,
- penetration testing,
- offensive security research,
- and operational workflows.

This means the gateway intentionally enables powerful actions in controlled environments.

Operational attribution and observability therefore matter.

## Logging and Attribution

Operations executed through the gateway should remain attributable.

Execution history and logs are intended to support:

- diagnostics,
- troubleshooting,
- operational review,
- auditing,
- and post-mortem analysis.

The architecture should preserve visibility into:

- executed commands,
- scripts,
- transfers,
- discovery actions,
- and workflow activity.

## Passwordless Connectivity

The project prefers:

- SSH identities,
- passwordless authentication,
- and explicit trust establishment.

Long-term password storage should be avoided whenever possible.

The gateway may eventually assist onboarding workflows that:

- establish trust,
- distribute identities,
- configure passwordless access,
- or register new connections.

New environments must still become explicit configured connections before they are part of the reachable operational set.

## Reverse Tunnel Security

Reverse tunnel mode is intended for environments where the gateway cannot directly reach the remote machine.

The remote environment initiates connectivity toward the gateway and exposes its local SSH service through a reverse tunnel.

This model is useful for:

- NATed environments,
- outbound-only infrastructure,
- headless devices,
- remote labs,
- and restricted infrastructure.

The current implementation supports probing and connecting through already exposed local tunnel ports.

The current code does not yet implement a full agent-side reverse tunnel SSH listener lifecycle.

Documentation and tests must not claim reverse tunnel listener behavior until it exists in code.

## Security Philosophy

The project should remain:

- explicit,
- inspectable,
- attributable,
- and operationally grounded.

Security should come from:

- explicit trust,
- constrained reachability,
- SSH identity ownership,
- observability,
- and narrow operational boundaries.

The project must avoid hidden authority expansion or implicit network trust.

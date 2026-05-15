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

## Assisted Node Onboarding

The `add_node` tool may accept a temporary password to support assisted onboarding workflows.

The intended use of a password in `add_node` is:

1. Use the password only to install the gateway public key on the target node.
2. Verify that passwordless SSH access succeeds before completing registration.
3. Discard the password immediately after the bootstrap operation.

Credential safety rules (non-negotiable):

- Passwords must **never** be stored in the registry, configuration, cache, or any file.
- Passwords must **never** appear in any log statement.
- Passwords must **never** be echoed or returned in any response value.
- Passwords must not persist beyond the call frame.

**Current implemented behavior:**

Password-based bootstrap is **not yet implemented** in the current codebase. When `add_node` is called, it returns a `bootstrap_not_implemented` response and does **not** add the node to the registry. No SSH connection is attempted. No key installation occurs.

**Intended future behavior (not yet implemented):**

When bootstrap is implemented, `add_node` will:
- Use the password transiently to connect and install the gateway public key.
- Verify passwordless SSH access succeeds.
- Register the node in the registry only after passwordless access is confirmed.
- Never store, log, or return the password at any point.

Documentation and tests must not claim bootstrap behavior until it exists in code.

## Agent SSH Identity

The gateway agent maintains its own SSH identity (ed25519 keypair) stored in the
configured key directory. The public key is available through the
`get_agent_public_key` MCP tool and can be installed on a managed node to grant
the agent SSH access.

The private key:
- Is stored at `<key_dir>/agent_id_ed25519`
- Has permissions `0600`
- Is **never** returned through any MCP tool or API
- Has no passphrase — access is controlled by filesystem permissions

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

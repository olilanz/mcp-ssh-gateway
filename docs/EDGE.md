# Edge Connectivity

This document explains how remote environments connect to `mcp-ssh-gateway`.

The gateway gives an LLM operational reach into remote environments. Those environments may expose shell access, tools, hardware, storage, network locality, or access into isolated infrastructure.

The connection model determines how the gateway reaches those environments.

The gateway agent should run in a protected control environment. Edge machines are remote capability environments reached through configured connections.

## Direct Mode

Direct mode is used when the remote environment is reachable from the gateway.

The gateway opens outbound SSH connections directly to the remote machine.

This is the simpler operational model and is appropriate for:

- internal infrastructure,
- trusted networks,
- VPN-connected systems,
- development labs,
- or environments with stable addressing.

The remote environment typically runs `sshd` and exposes a reachable SSH endpoint.

Direct mode is recommended when inbound reachability is available and operational simplicity matters more than traversal flexibility.

### Requirements

The remote environment should:

- run `sshd`,
- allow SSH access from the gateway,
- and trust the gateway identity.

Passwordless connectivity is preferred.

## Reverse Tunnel Mode

Reverse tunnel mode is used when the remote environment is not reachable from the gateway, but can reach the gateway.

This is common for:

- NATed infrastructure,
- outbound-only networks,
- headless devices,
- mobile systems,
- intermittent environments,
- remote labs,
- or restricted infrastructure.

Headless devices should generally prefer reverse tunnel mode.

In this model:

1. The remote environment initiates connectivity toward the gateway.
2. The remote environment exposes its local SSH service through a reverse tunnel.
3. The gateway connects back through the exposed local tunnel port.

The operational model is currently configured using:

```json
{
  "mode": "tunnel"
}
```

The documentation uses “reverse tunnel mode” to describe the behavior clearly.

### Example Reverse Tunnel

Example edge-side reverse tunnel command:

```bash
ssh -i edge.key \
    -R 22222:localhost:22 \
    gateway_user@gateway_host -p <gateway_tunnel_port>
```

This exposes the edge environment's local SSH service back through the tunnel.

Once active, the gateway can connect to the exposed local tunnel port.

### Requirements

The remote environment should:

- run `sshd`,
- possess an identity trusted by the gateway,
- maintain outbound connectivity toward the gateway,
- and maintain the reverse tunnel lifecycle.

Persistence may be implemented through:

- systemd,
- autossh,
- startup scripts,
- or external orchestration.

## Discovery Expectations

The gateway is designed to discover and normalize information about connected environments.

Discovery may include:

- operating system,
- architecture,
- interpreters,
- installed tooling,
- network configuration,
- GPU availability,
- hardware characteristics,
- local storage,
- or workload-specific capabilities.

Discovered capabilities become part of the operational context exposed to the LLM.

## Operational Trust

The gateway owns:

- SSH identities,
- connection configuration,
- discovery,
- capability cache,
- and transport mechanics.

External orchestrators interact through MCP tools rather than direct network authority.

The orchestrator gets capability, not custody.

## Current Implementation Boundary

Current code implements:

- direct SSH connectivity,
- reverse tunnel probing against already exposed local tunnel ports,
- and connection lifecycle scaffolding.

Current code does not yet implement a full agent-side reverse tunnel SSH listener lifecycle.

Documentation and tests must not claim reverse tunnel listener behavior until it exists in code.

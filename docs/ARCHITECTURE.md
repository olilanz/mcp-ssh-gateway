## Architecture

This document defines non-negotiable system boundaries for `mcp-ssh-gateway`.

## System Shape

- The system must expose MCP tooling through the Python agent process.
- The system must use static connection configuration as input.
- The public connection boundary must be the [`Connection`](../agent/connectionpool/connection.py) facade.

## Connection Modes

### Direct Mode

- Direct mode must use outbound SSH from agent to edge.
- Direct mode is implemented by [`DirectConnection.open()`](../agent/connectionpool/connection.py:145) using Paramiko.

### Tunnel Mode

- Tunnel mode is intended to use edge-initiated reverse tunnels.
- Current implementation must only probe and connect through an already exposed local tunnel port.
- The agent-side SSH server that accepts reverse tunnels is not implemented.

## Invariants

- Documentation must distinguish implemented behavior from intended architecture.
- Tests must not assume reverse tunnel listener behavior exists on the agent.
- Changes to architecture boundaries must update this file and relevant tests together.

## Out of Scope (Current)

- Implementing Paramiko reverse tunnel listener/server.
- End-to-end reverse tunnel tests that require agent-side listener behavior.

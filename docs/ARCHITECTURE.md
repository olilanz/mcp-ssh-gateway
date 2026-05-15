# Architecture

This document defines the system model, trust boundary, and architectural invariants for `mcp-ssh-gateway`.

`mcp-ssh-gateway` is an MCP-native boundary agent. It gives LLMs and automation systems controlled operational reach into selected remote environments.

SSH is the transport. The product boundary is broader: declared connections, capability discovery, capability cache, execution, logging, and orchestration support through MCP tools. The MCP API surface is node-oriented: nodes are the primary management unit exposed to orchestration systems.

## System Shape

```text
LLM / MCP client
        ↓
FastMCP tool surface
        ↓
mcp-ssh-gateway
    ├── connection registry
    ├── capability discovery
    ├── capability cache
    ├── execution logging
    ├── task routing support
    └── transport orchestration
            ├── direct SSH
            └── reverse tunnel SSH
                    ↓
          remote capability environments
```

The gateway is the boundary between orchestration systems and real environments.

External clients use MCP tools. They must not manage SSH passwords, private keys, target topology, or transport mechanics directly.

## Core Concepts

### Boundary Agent

The gateway owns the operational boundary.

It owns:

- configured connections,
- SSH identities,
- connection modes,
- discovery execution,
- capability cache,
- execution logging,
- and transport behavior.

The orchestrator gets capability, not custody.

This allows tools such as Open WebUI, n8n, OpenClaw, or other MCP clients to reach real systems without becoming the owner of remote credentials or connection mechanics.

### Connection

A connection is a trusted operational arm into a remote machine.

A connection is not just an SSH target. It represents a remote environment where commands, scripts, discovery, diagnostics, administration, security testing, or other shell-based work can happen.

The remote environment may provide:

- shell access,
- local tools,
- specialized hardware,
- GPU acceleration,
- databases,
- storage,
- network adjacency,
- or access to isolated infrastructure.

Configured connections define the reachable operational world.

### Capability Environment

A remote machine becomes useful to the LLM when the gateway understands what it can do.

The gateway discovers and normalizes capabilities for each connection. Capability information helps the LLM decide where to execute work.

Capabilities may include:

- operating system,
- architecture,
- hostname,
- user context,
- network configuration,
- internet access,
- memory,
- disks,
- GPU availability,
- interpreters,
- local toolchains,
- installed security tools,
- or other environment-specific affordances.

### Capability Cache

Discovered capabilities must be stored per connection.

The cache gives the LLM a current view of available execution environments without rediscovering everything for every task.

The cache exists to support planning:

- which machine has the right tool,
- which machine has the right hardware,
- which machine has the right network locality,
- which machine should receive an artifact,
- and how multiple machines can collaborate.

### Execution

The gateway provides controlled operational primitives over MCP.

The capability surface is expected to grow over time. Examples include:

- listing configured connections,
- inspecting connection state,
- discovering capabilities,
- querying cached capabilities,
- running commands,
- running scripts,
- transferring files,
- collecting outputs,
- and querying execution history.

The architecture must treat execution as attributable. Actions should be logged so diagnostics, troubleshooting, and post-mortem analysis remain possible.

## Connection Modes

### Direct Mode

Direct mode is used when the remote machine is reachable from the gateway.

The gateway opens outbound SSH connections directly to the target.

Direct mode is appropriate for:

- trusted infrastructure,
- internal networks,
- VPN-connected environments,
- static lab environments,
- or machines with stable addressing.

### Reverse Tunnel Mode

Reverse tunnel mode is used when the remote machine is not reachable from the gateway, but can reach the gateway.

The remote machine initiates connectivity toward the gateway and exposes its own SSH service through a reverse tunnel. The gateway then connects back through the exposed local tunnel port.

Reverse tunnel mode is appropriate for:

- headless devices,
- NATed environments,
- outbound-only infrastructure,
- mobile or intermittent systems,
- remote labs,
- and restricted networks.

The current configuration value for this mode is `mode: "tunnel"`. Documentation uses “reverse tunnel mode” to describe the operational model clearly.

## Trust Boundary

The LLM may reason about tasks and choose actions through MCP tools.

The LLM must not receive direct custody of:

- private keys,
- passwords,
- target host details beyond what tools expose,
- or unrestricted network authority.

The gateway owns those responsibilities.

New targets may be onboarded as an operational workflow, but they must become explicit registered connections before they are part of the reachable environment set.

Passwordless SSH connectivity is preferred. Long-term password storage must be avoided where possible.

## Runbooks and Skills

The gateway is designed to work with runbooks, skills, and procedures.

The LLM provides reasoning and planning. Runbooks and skills provide procedural memory. The gateway provides operational reach into real environments.

Together, they allow larger workflows to be executed without requiring the user to remember every command, flag, sequence, or diagnostic step.

## Current Implementation Boundary

Current code implements:

- MCP startup and tool registration foundations,
- static connection configuration,
- connection pool lifecycle scaffolding,
- direct SSH connectivity using Paramiko,
- reverse tunnel probing through already exposed local ports,
- structured command execution results,
- node-oriented MCP API surface (`get_status`, `get_node_info`, `add_node`, `remove_node`, `enable_node`, `disable_node`),
- `NodeRegistry` (in-memory, thread-safe; stores `NodeConfig` and `NodeInfoCache`),
- `NodeService` (business logic layer over registry and pool; composes `NodeRuntimeState` at call time),
- and `ConnectionPool` disable/remove/enable seam (`disable_connection`, `enable_connection`, `remove_connection`).

Current code is evolving around:

- capability discovery,
- normalized capability cache,
- execution history,
- task routing support,
- and onboarding workflows.

Current code does not yet implement:

- full agent-side reverse tunnel SSH listener behavior,
- end-to-end reverse tunnel establishment lifecycle,
- advanced capability orchestration,
- or advanced workflow execution primitives.

Tests and documentation must not claim reverse tunnel listener behavior until it exists in code.

## Invariants

- The public connection boundary must remain the `Connection` facade unless an architecture change explicitly replaces it.
- Documentation must distinguish implemented behavior from intended architecture.
- MCP clients must interact through exposed tools, not by taking custody of connection secrets.
- Configured connections define the reachable operational world.
- Capability discovery must be represented as per-connection knowledge.
- Execution must remain attributable through logs or history.
- Boundary changes must update docs and tests together.

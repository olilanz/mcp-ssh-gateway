# Architecture

This document defines the system model, trust boundary, and architectural invariants for `mcp-ssh-gateway`.

`mcp-ssh-gateway` is an MCP-native boundary agent. It gives LLMs and automation systems controlled operational reach into selected remote environments.

SSH is the transport. The product boundary is broader: declared connections, capability discovery, capability cache, execution, logging, and orchestration support through MCP tools. The MCP API surface is node-oriented: nodes are the primary management unit exposed to orchestration systems.

## System Shape

```text
LLM / MCP client
        ↓
FastMCP tool surface (mcp_handlers.py)
        ↓
NodeService
    ├── NodeRegistry
    ├── ConnectionPool
    │       └── Connection (DirectConnection / TunnelConnection)
    ├── NodeHandshakeService
    └── AgentIdentityService (add_node bootstrap)
                    ↓
          remote node environments
```

The gateway is the boundary between orchestration systems and real environments.

External clients use MCP tools. They must not manage SSH passwords, private keys, target topology, or transport mechanics directly.

## Core Concepts

### Boundary Agent

The gateway owns the operational boundary.

It owns:

- configured nodes,
- SSH identities,
- connection modes,
- discovery execution,
- capability cache,
- execution logging,
- and transport behavior.

The orchestrator gets capability, not custody.

This allows tools such as Open WebUI, n8n, OpenClaw, or other MCP clients to reach real systems without becoming the owner of remote credentials or connection mechanics.

### Agent SSH Identity

The gateway agent has its own persistent SSH identity — an ed25519 keypair stored in
the configured key directory (default: `/data/keys`). This identity is generated once
at startup if not present, and reused on subsequent starts.

The public key may be retrieved through the `get_agent_public_key` MCP tool. An
operator installs this public key on a managed node to grant the agent SSH access —
the manual equivalent of running `ssh-copy-id`.

The private key is never exposed through MCP or any API. It is protected by filesystem
permissions (`0600`).

> Current connections may still reference a per-connection `id_file` until SSH
> identity handling is consolidated. The agent identity is the intended default for
> future node onboarding and outbound node access.

### Node

A node is the managed identity: a named, configured SSH-reachable execution environment.

A node is not just an SSH target. It represents a remote environment where commands, scripts, discovery, diagnostics, administration, security testing, or other shell-based work can happen.

The remote environment may provide:

- shell access,
- local tools,
- specialized hardware,
- GPU acceleration,
- databases,
- storage,
- network adjacency,
- or access to isolated infrastructure.

Configured nodes define the reachable operational world.

### Connection

A connection is the runtime SSH transport/session to a node.

A node can exist in the managed set without an active connection — for example, when a node is disabled or unreachable. A connection can close or break without removing the node from the managed set.

The gateway manages connections internally. External orchestrators interact with nodes through MCP tools, not through connection mechanics directly.

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

Discovered capabilities must be stored per node.

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

- listing configured nodes,
- inspecting node status and connection state,
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
- node host details beyond what tools expose,
- or unrestricted network authority.

The gateway owns those responsibilities.

New nodes may be onboarded as an operational workflow, but they must become explicit registered connections before they are part of the reachable environment set.

Passwordless SSH connectivity is preferred. Long-term password storage must be avoided where possible.

## Runbooks and Skills

The gateway is designed to work with runbooks, skills, and procedures.

The LLM provides reasoning and planning. Runbooks and skills provide procedural memory. The gateway provides operational reach into real environments.

Together, they allow larger workflows to be executed without requiring the user to remember every command, flag, sequence, or diagnostic step.

## Layer Responsibilities

The following table describes each layer's responsibility in the current implementation:

| Layer | Responsibility |
|---|---|
| `mcp_handlers.py` | MCP tool surface — delegates to service layer only, no logic |
| `NodeService` | Business logic: node guards, readiness orchestration, execution delegation |
| `AgentIdentityService` | Agent SSH keypair management; public key retrieval and password-bootstrap install |
| `NodeRegistry` | In-memory, thread-safe store of `NodeConfig` and `NodeInfoCache` |
| `ConnectionPool` | Transport lifecycle: connection lookup, open, enable, disable, remove |
| `Connection` / `BaseConnection` | SSH command execution (with timeout), SFTP upload/download |
| `NodeHandshakeService` | Loads `resources/node/handshake.sh`, executes over SSH, parses `key=value` facts |
| `resources/node/handshake.sh` | Node-side POSIX sh script — no external dependencies |

## Error Contract

MCP tool error responses use a stable set of error keys. The following keys are currently defined:

| Error key | Meaning |
|---|---|
| `node_not_found` | No node with that name in the registry |
| `node_disabled` | Node is known but currently disabled |
| `not_in_pool` | Node exists in registry but has no pool entry |
| `connection_not_open` | Node is in the pool but connection could not be opened |
| `timeout` | Command exceeded the requested timeout |
| `invalid_base64` | Upload data was not valid base64 |
| `invalid_mode` | Chmod mode string was not a valid octal mode |
| `file_not_found` | Remote file does not exist (download) |
| `file_too_large` | Download exceeds the 10 MB limit |

## Current Implementation Boundary

Current code implements:

- full node-lifecycle MCP API surface:
  - `get_node_status`, `get_node_info`, `get_agent_public_key`
  - `add_node`, `enable_node`, `disable_node`, `remove_node`
  - `run_command_on_node`, `upload_file_to_node`, `download_file_from_node`
- `AgentIdentityService` — persistent ed25519 keypair; public key retrieval; password-bootstrap install for `add_node`
- `NodeRegistry` — in-memory, thread-safe; stores `NodeConfig` and `NodeInfoCache`
- `NodeService` — business logic layer; composes `NodeRuntimeState` at call time; `ensure_node_ready()` readiness gate
- `ConnectionPool` — transport lifecycle: `get_connection`, `ensure_connection_open`, `enable_connection`, `disable_connection`, `remove_connection`
- `Connection` / `BaseConnection` — SSH command execution with timeout, SFTP upload/download
- `NodeHandshakeService` — loads `resources/node/handshake.sh`, executes via `sh -s`, parses `key=value` facts into `NodeInfoCache`
- `resources/node/handshake.sh` — POSIX sh script collecting: `hostname`, `kernel_name`, `kernel_release`, `architecture`, `current_user`, `shell`, `os_pretty_name`, `collected_at`
- direct SSH connectivity via Paramiko; reverse tunnel probing through already-exposed local ports

Current code is evolving around:

- capability discovery and normalized capability cache,
- execution history,
- and task routing support.

Current code does not yet implement:

- full agent-side reverse tunnel SSH listener behavior,
- end-to-end reverse tunnel establishment lifecycle,
- advanced capability orchestration,
- or advanced workflow execution primitives.

Tests and documentation must not claim reverse tunnel listener behavior until it exists in code.

## Resources

The `resources/` directory contains scripts and artifacts that run on managed nodes, not on the gateway.

`resources/node/` scripts are POSIX sh with no external dependencies. They are first-class artifacts: visible, reviewable, and independently runnable:

```bash
ssh <node> 'sh -s' < resources/node/handshake.sh
```

New node-side scripts should be placed in `resources/node/`, not inlined in Python.

## Invariants

- The public connection boundary must remain the `Connection` facade unless an architecture change explicitly replaces it.
- Documentation must distinguish implemented behavior from intended architecture.
- MCP clients must interact through exposed tools, not by taking custody of connection secrets.
- Configured nodes define the reachable operational world.
- Capability discovery must be represented as per-node knowledge.
- Execution must remain attributable through logs or history.
- Boundary changes must update docs and tests together.

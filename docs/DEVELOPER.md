# Developer Guide

This document explains how to work on `mcp-ssh-gateway` as a developer.

Repository-level documentation explains architecture, operational concepts, and boundaries. Local implementation rationale and low-level technical decisions belong close to the source code and tests.

## Core System Areas

The project currently has three major areas of concern:

1. MCP tool surface
2. Connection lifecycle and transport orchestration
3. Capability discovery and cache

These concerns should remain clearly separated.

The gateway is not only an SSH transport layer. It is a boundary agent that exposes operational capability to LLMs and orchestration systems through MCP tools.

## Development Philosophy

The project values:

- simplicity,
- explicit boundaries,
- operational clarity,
- capability-oriented thinking,
- and grounded implementation.

Prefer:

- small reviewable slices,
- direct code paths,
- realistic testing,
- and explicit lifecycle behavior.

Avoid:

- speculative infrastructure,
- unnecessary abstraction,
- hidden orchestration,
- or broad frameworks disconnected from current implementation.

## Operational Model

The gateway gives LLMs controlled operational reach into remote environments.

Connections represent trusted operational arms into remote capability environments.

Those environments may expose:

- shell access,
- tools,
- hardware,
- GPUs,
- network locality,
- databases,
- storage,
- or access into isolated infrastructure.

Capability discovery and capability cache behavior exist to help the LLM decide where work should happen.

## Development Environment

Recommended environment:

- Python 3.10+
- Linux or macOS
- local `ssh`, `sshd`, and `ssh-keygen`

Development container support may exist for convenience, but the project should remain runnable without specialized orchestration.

### Key directory requirements

The agent requires a writable key directory at startup. The default is `/data/keys`
(set via `--agent-key-dir`). When running locally or in a container, ensure this
directory exists and is writable by the process user, or override it:

    python3 app.py --agent-key-dir /tmp/my-keys

## Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install pytest
```

## Build and Test

Run all tests:

```bash
pytest
```

Run connection-pool tests:

```bash
pytest tests/agent/connectionpool
```

Run a targeted test:

```bash
pytest tests/agent/connectionpool/test_connection.py -k constructor
```

## Roo-Assisted MCP Exploratory Validation Loop

> **Completion gate**: Any task that changes MCP-exposed behavior must include live MCP validation before being marked complete. See [`docs/MCP_VALIDATION_GUIDE.md`](MCP_VALIDATION_GUIDE.md) for the full process, evidence requirements, and status report template. The gate is enforced via [`.roo/rules.md`](../.roo/rules.md).

### Quick reference

- Startup: `python3 app.py`
- Endpoint: `http://localhost:8000/mcp`
- Transport: stateless streamable-http (`stateless_http=True`, `json_response=True`)
- With this configuration, Roo can call tools after a gateway restart without a session-reset action.
- SSE and stateful sessions are out of scope unless explicitly requested.

### Key distinctions

- **Roo MCP validation** = exploratory/product-surface validation. Confirms tool registration, request/response shape, and runtime behavior from the Roo client perspective. Not a regression proof.
- **pytest** = regression validation. Encodes stable, deterministic expectations about startup wiring, config defaults, and tool dispatch behavior. Runs in CI without a live gateway.
- Both are required. Neither replaces the other.

For the iterative development loop, task-focused validation scope, lifecycle ownership rules, and the status report template, see [`docs/MCP_VALIDATION_GUIDE.md`](MCP_VALIDATION_GUIDE.md).

## Testing Philosophy

Testing should prefer realistic behavior over heavy mocking.

Functional SSH behavior should be tested against local SSH fixtures using generated temporary keys.

Tests should validate:

- direct SSH connectivity,
- connection lifecycle behavior,
- command execution,
- reverse tunnel probing behavior,
- and capability-oriented execution flow.

Tests must not assume a full reverse tunnel listener lifecycle exists until implemented.

`/data/keys` may exist in container or developer environments for manual experimentation, but tests should prefer generated temporary keys unless a scenario explicitly requires mounted keys.

## Node Execution Tools (v1)

Three node-scoped execution tools complete the v1 MCP API surface. All three go through `NodeService.ensure_node_ready()`, a five-step readiness gate: registry exists → enabled → pool lookup → connection open → handshake (if cache empty).

### run_command_on_node

Executes a shell command on a named, enabled, connected node.

Parameters:
- `name` — registered node name
- `command` — shell command string
- `timeout` — max seconds to wait (default 30)

Returns: `CommandResult` fields (`command`, `exit_code`, `stdout`, `stderr`, `started_at`, `ended_at`).

Error responses: `node_not_found`, `node_disabled`, `not_in_pool`, `connection_not_open`, `timeout`.

### upload_file_to_node

Uploads a base64-encoded file to a node via SFTP.

Parameters:
- `name` — registered node name
- `remote_path` — absolute path on the remote node
- `data_b64` — base64-encoded file content
- `mode` — chmod mode string, e.g. `"0644"` (default `"0644"`)

Returns: `{"status": "written", "path": remote_path}`.

Error responses: `node_not_found`, `node_disabled`, `invalid_base64`, `invalid_mode`.

### download_file_from_node

Downloads a file from a node via SFTP, returning base64-encoded content.

Parameters:
- `name` — registered node name
- `remote_path` — absolute path on the remote node

Returns: `{"status": "ok", "path": remote_path, "data_b64": "<base64>"}`.

Error responses: `node_not_found`, `node_disabled`, `file_not_found`, `file_too_large` (limit: 10 MB).

### Node Handshake

After the first execution call on a node, a minimal handshake runs automatically via [`NodeHandshakeService`](../agent/nodes/handshake.py):

- Executes `resources/node/handshake.sh` on the node via `sh -s`
- Collects: `hostname`, `kernel_name`, `kernel_release`, `architecture`, `current_user`, `shell`, `os_pretty_name`, `collected_at`
- Stored in `NodeInfoCache`, visible via `get_node_info()`

The handshake script is POSIX sh, has no external dependencies, and can be run manually:

```bash
ssh <node> 'sh -s' < resources/node/handshake.sh
```

### Legacy local tools

`run_command` and `upload_file` remain unchanged and operate on the gateway host, not on nodes.

## Resources directory

`resources/node/` contains scripts that run **on managed nodes**, not on the gateway.

Scripts in this directory are:
- POSIX sh for compatibility with minimal nodes
- First-class artifacts: visible, reviewable, and independently runnable
- The correct location for any new node-side scripts — do not inline node-side shell logic in Python

## Current Implementation Boundary

Current code implements:

- MCP startup and tool registration foundations,
- static connection configuration,
- connection pool lifecycle scaffolding,
- direct SSH connectivity using Paramiko,
- reverse tunnel probing through already exposed local ports,
- structured command execution,
- node execution MCP tools (`run_command_on_node`, `upload_file_to_node`, `download_file_from_node`),
- `NodeService.ensure_node_ready()` readiness gate,
- `NodeHandshakeService` with automatic fact collection on first node use,
- and `resources/node/handshake.sh` POSIX sh fact-collection script.

Current code is evolving around:

- capability discovery,
- normalized capability cache,
- onboarding workflows,
- execution history,
- and richer operational primitives.

Current code does not yet implement:

- full agent-side reverse tunnel SSH listener behavior,
- advanced capability orchestration,
- or richer distributed workflow execution.

## Documentation Responsibilities

High-level architectural and operational concepts belong in `/docs`.

Local implementation rationale belongs:

- in module headers,
- in class documentation,
- in tests,
- or near the implementation itself.

When implementation boundaries change:

- update architecture docs,
- update testing strategy,
- and update affected tests in the same slice.

## Contribution Expectations

Contributors should:

- preserve the `Connection` facade as the public operational boundary unless explicitly redesigned,
- distinguish implemented behavior from intended architecture,
- keep operational boundaries explicit,
- and avoid introducing unnecessary infrastructure.

The project should remain understandable, inspectable, and operationally grounded.

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

### Purpose

Roo uses the running MCP gateway for exploratory validation of gateway behavior during development.
This loop is for exploratory observation, not regression testing.

### Network transport for this loop

The gateway uses stateless streamable-http for the development validation loop.

- Supported transport: `streamable-http` with `stateless_http=True` and `json_response=True`.
- SSE and stateful sessions are out of scope for this loop.
- After a gateway restart, Roo can call tools again without any session-reset action.

### Startup command

```bash
python3 app.py
```

Defaults: `transport=streamable-http`, `host=0.0.0.0`, `port=8000`, no managed connections.

### Roo endpoint

```
http://localhost:8000/mcp
```

### Boundary

- The gateway is the system under test.
- Roo must not use the gateway as an unrelated automation substrate.

### When to use Roo MCP validation

Use MCP validation when a slice changes:

- MCP tool registration or descriptions
- tool input/output shape
- command execution behavior
- connection/pool visibility
- logging or observability relevant to tool calls

### When not to use Roo MCP validation

- Do not use Roo MCP calls as regression tests.
- Do not use them to replace pytest.
- Do not use them for unrelated shell automation.

### Standard validation loop

1. Start gateway: `python3 app.py`
2. Confirm Roo endpoint: `http://localhost:8000/mcp`
3. Enumerate tools visible to Roo.
4. Invoke the changed or relevant tool.
5. Inspect result shape.
6. Inspect gateway logs.
7. Record observations in the active plan.
8. Convert stable expectations into pytest where appropriate.

### Evidence Roo must capture

For each exploratory MCP validation:

- tool called
- input used
- observed result
- relevant log lines
- pass/fail conclusion
- whether a pytest should be added or updated

### Architect responsibilities

- Specify which MCP validations are required for a slice.
- Decide whether a slice changes MCP tool behavior.
- Keep exploratory validation separate from regression proof.

### Orchestrator responsibilities

- Execute the agreed exploratory validation steps.
- Capture startup logs, visible tool surface, and invocation outcomes.
- Record evidence in the active plan before claiming completion.
- Add or update pytest coverage when behavior is stable and expectations are clear.

### Process rules

- Exploratory MCP calls are not regression tests.
- Roo-assisted MCP validation is exploratory, not regression.
- After stable behavior is observed, convert expectations into pytest.
- If no harmless status/listing tool exists, record a tool-surface gap instead of inventing a test-only tool.

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

## Current Implementation Boundary

Current code implements:

- MCP startup and tool registration foundations,
- static connection configuration,
- connection pool lifecycle scaffolding,
- direct SSH connectivity using Paramiko,
- reverse tunnel probing through already exposed local ports,
- and structured command execution.

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

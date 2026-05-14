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

Use Roo MCP tool calls as exploratory validation for the gateway MCP surface.

Boundary:

- Roo uses the gateway as system under test.
- Roo must not use the gateway as a general-purpose tool substrate for unrelated work.

### Architect responsibilities

- Decide whether a slice changes MCP tool behavior.
- Identify required exploratory MCP validation for that slice.
- Keep exploratory validation separate from regression proof.

### Orchestrator responsibilities

- Execute the agreed exploratory validation steps.
- Capture startup logs, visible tool surface, and invocation outcomes.
- Add or update pytest coverage when behavior is stable and expectations are clear.

### Process rules

- Exploratory MCP calls validate readiness, visibility, and basic request/response behavior.
- Exploratory MCP calls are not regression tests.
- Stable observations should be converted into pytest assertions in this repository.

### Manual startup path for exploratory checks

```bash
bash scripts/start-agent.sh
```

Expected validation context:

- Roo connects to the forwarded mcpo endpoint for the devcontainer, expected as `localhost:8000` from the VS Code/Roo environment.
- Roo inspects available tools.
- Roo invokes one read-only/status-style tool (preferably gateway or connection status/listing behavior).
- If no read-only/status-style tool exists, record a tool-surface gap instead of inventing a test-only tool.

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

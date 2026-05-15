# Architectural Decisions

This file records system-wide decisions and rationale.

## ADR-0001: Keep `Connection` as public facade boundary

- Status: Accepted
- Date: 2026-05-14

Decision:

- The system keeps [`Connection`](../agent/connectionpool/connection.py) as the public boundary used by pool logic and tests.

Rationale:

- It provides a single integration point while preserving direct/tunnel implementation separation.
- It allows incremental internal changes without changing the public testing/use surface.

## ADR-0002: Tunnel boundary limited to probe/connect-through-local-port

- Status: Accepted
- Date: 2026-05-14

Decision:

- Tunnel behavior is currently limited to probing and connecting through an already exposed local tunnel port.
- Agent-side reverse tunnel SSH server/listener is explicitly out of scope until a dedicated implementation slice.

Rationale:

- This matches existing implementation and avoids documentation/test claims that exceed code reality.

## ADR-0003: Dependency source of truth is `pyproject.toml`

- Status: Accepted
- Date: 2026-05-14

Decision:

- Runtime dependencies are declared in [`pyproject.toml`](../pyproject.toml) under `[project.dependencies]`.
- Dev/test dependencies are declared under `[project.optional-dependencies].dev`.
- Container build installs from repository package metadata instead of manually repeating dependency lists.

Rationale:

- Reduces drift between local and container environments.
- Keeps dependency governance in one canonical source.

## ADR-0004: Use stateless streamable HTTP for the development validation loop

- Status: Accepted
- Date: 2026-05-15

Decision:

- The gateway uses streamable-http as the supported network MCP transport for the current development validation loop.
- The server is configured with `stateless_http=True` and `json_response=True`.
- SSE and stateful MCP sessions are out of scope for this phase.
- Stateful sessions may be revisited later when concrete scenarios require session continuity or richer streaming behavior.

Rationale:

- Roo-assisted validation must support edit/restart/test without stale client session failures.
- Gateway product behavior must not depend on MCP transport-session state.
- Stateless request/response behavior matches current tool usage and keeps the boundary simple.

Trade-off:

- No reliance on per-client MCP transport-session memory.
- Advanced stateful/session-continuity behavior is deferred.

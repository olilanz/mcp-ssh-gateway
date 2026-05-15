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

Context:

The MCP gateway must be reachable by the Roo MCP client during development for exploratory
validation of tool registration, tool surface, and request/response shape. The chosen transport
must support a fast edit/restart/test loop without stale-session failures.

The `mcp==1.27.1` SDK exposes three transports via `FastMCP.run(transport=...)`:

- `stdio` — local subprocess only; not usable for Roo network connections.
- `sse` — network-capable; requires SSE client support; distinct session semantics.
- `streamable-http` — network-capable; supports both stateful (default) and stateless modes.

The default `streamable-http` mode is stateful: the server issues an `mcp-session-id` on
`initialize`, and all subsequent requests must carry it. A gateway restart destroys all session
state. The Roo MCP client does not automatically re-run the `initialize` handshake after a
restart, causing every post-restart tool call to fail with `Session not found` until a manual
VS Code window reload is performed.

Decision:

- The gateway remains MCP-native. No custom REST API is built or exposed.
- The supported network MCP transport for the development validation loop is `streamable-http`.
- The server is configured with `stateless_http=True` and `json_response=True`:

  ```python
  FastMCP(
      name="mcp-ssh-gateway",
      host=host,
      port=port,
      stateless_http=True,   # eliminates server-side session state requirement
      json_response=True,    # returns JSON responses instead of SSE streams for tool calls
  )
  ```

  Both parameters are direct `FastMCP.__init__` kwargs supported by `mcp==1.27.1`.

- Gateway is started with `python3 app.py`; MCP endpoint is `http://localhost:8000/mcp`.
- SSE and stateful MCP sessions are out of scope for this phase.
- Stateful sessions may be revisited later when concrete scenarios require session continuity or richer streaming behavior.

Rationale:

- `stateless_http=True` eliminates the session ID requirement. Each MCP tool call is independently handled without a prior `initialize` → `mcp-session-id` handshake.
- `json_response=True` returns plain JSON instead of SSE stream chunks, which is compatible with the Roo MCP client's response handling for streamable-http.
- Together these options make the gateway resilient to restart during the edit/restart/test loop. Roo can call tools again after a gateway restart without any session-reset action.
- No custom REST endpoints, no SSE transport, and no session persistence infrastructure were introduced.
- Gateway product behavior must not depend on MCP transport-session state.

Trade-offs:

- No reliance on per-client MCP transport-session memory. Each tool call is independently routed and authenticated.
- No advanced session continuity for now. Scenarios that require stateful MCP session semantics (e.g., multi-turn server-initiated messages) are not supported in this mode.

Deferred:

- Stateful MCP sessions (`stateless_http=False`) may be revisited in a future slice for richer scenarios requiring session continuity or server-initiated messages.
- SSE transport is an available SDK option but is out of scope for the current development validation loop.

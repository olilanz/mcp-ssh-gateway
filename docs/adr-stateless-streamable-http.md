# ADR: Use Stateless Streamable HTTP for the Development Validation Loop

## Status

Accepted

## Context

The MCP gateway must be reachable by the Roo MCP client during development for exploratory
validation of tool registration, tool surface, and request/response shape. The chosen network
transport must support a fast edit/restart/test loop without stale-session failures.

The `mcp==1.27.1` SDK exposes three transports via `FastMCP.run(transport=...)`:

- `stdio` — local subprocess only; not usable for Roo network connections.
- `sse` — network-capable; requires SSE client support; distinct session semantics.
- `streamable-http` — network-capable; supports both stateful (default) and stateless modes.

The default `streamable-http` mode is stateful: the server issues an `mcp-session-id` on
`initialize`, and all subsequent requests must carry it. A gateway restart destroys all session
state. The Roo MCP client does not automatically re-run the `initialize` handshake after a
restart, causing every post-restart tool call to fail with `Session not found` until a manual
VS Code window reload is performed.

## Decision

The current network MCP transport for the development validation loop is `streamable-http`
configured with:

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

The gateway is started with:

```bash
python3 app.py
```

The Roo MCP endpoint is:

```
http://localhost:8000/mcp
```

## Rationale

- `stateless_http=True` eliminates the session ID requirement. Each MCP tool call is
  independently handled without a prior `initialize` → `mcp-session-id` handshake.
- `json_response=True` returns plain JSON instead of SSE stream chunks, which is compatible
  with the Roo MCP client's response handling for streamable-http.
- Together, these options make the gateway resilient to restart during the edit/restart/test
  loop. Roo can call tools again after a gateway restart without any session-reset action.
- No custom REST endpoints, no SSE transport, and no session persistence infrastructure were
  introduced.

## Trade-offs

- No reliance on transport-session state. Session continuity across calls is not tracked
  server-side. Each tool call is independently routed and authenticated.
- No advanced session continuity for now. Scenarios that require stateful MCP session
  semantics (e.g., multi-turn server-initiated messages) are not supported in this mode.

## Deferred

- Stateful MCP sessions (`stateless_http=False`) may be revisited in a future slice for
  richer scenarios that require session continuity or server-initiated messages.
- SSE transport is an available SDK option but is out of scope for the current development
  validation loop.

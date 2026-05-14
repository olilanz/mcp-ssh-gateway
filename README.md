# mcp-ssh-gateway

`mcp-ssh-gateway` is a minimal SSH gateway for MCP-driven automation.

It exists to provide a narrow, auditable way for agents and operators to run remote actions over SSH without depending on broad shell orchestration.

## Connection Modes (High Level)

- **Direct mode** (`mode: "direct"`): agent opens outbound SSH to a reachable edge host.
- **Tunnel mode** (`mode: "tunnel"`): agent uses an already-exposed local tunnel port to reach an edge host behind restricted networking.

## Current Status

### Implemented behavior

- [`Connection`](agent/connectionpool/connection.py) is the public facade used by pool/tests.
- [`DirectConnection.open()`](agent/connectionpool/connection.py:145) is implemented with Paramiko outbound SSH.
- [`TunnelConnection.open()`](agent/connectionpool/connection.py:176) probes a local port and connects through it when available.

### Intended architecture

- Tunnel mode is designed around edge-initiated reverse tunneling into the agent, then agent command execution through the exposed local port.

### Not implemented in current code

- `TunnelConnection` can probe and connect through an already exposed local tunnel port. The agent-side SSH server that accepts reverse tunnels is not implemented in the current code.
- Do not assume end-to-end reverse tunnel listener behavior in tests.

## Configuration

Connections are static and defined in JSON consumed by [`agent/connectionpool/config_loader.py`](agent/connectionpool/config_loader.py).

## Build & Test

```bash
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install pytest
pytest
```

## Documentation

- Documentation writing/governance standard: [`docs/DOCUMENTATION_GUIDE.md`](docs/DOCUMENTATION_GUIDE.md)
- Architecture boundaries and invariants: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Testing intent and boundary enforcement: [`docs/TESTING_STRATEGY.md`](docs/TESTING_STRATEGY.md)
- Architectural decisions record: [`docs/ARCHITECTURAL_DECISIONS.md`](docs/ARCHITECTURAL_DECISIONS.md)
- Edge mode guidance: [`docs/EDGE.md`](docs/EDGE.md)
- Developer workflow: [`docs/DEVELOPER.md`](docs/DEVELOPER.md)
- Security policy: [`docs/SECURITY.md`](docs/SECURITY.md)
- Contribution guide: [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)

## License

Apache 2.0.

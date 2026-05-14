# mcp-ssh-gateway

`mcp-ssh-gateway` is an MCP-native boundary agent for remote operational capability.

It gives LLMs and automation systems controlled arms and legs into selected remote machines through SSH-based connections. Those machines may provide shell access, specialized hardware, local tools, storage, network adjacency, compute capacity, or access to isolated infrastructure.

The gateway is useful for work such as systems automation, remote administration, diagnostics, troubleshooting, penetration testing, offensive security research, and AI-assisted operational workflows.

The project is not a general orchestration platform, not a replacement for configuration management systems, and not an unrestricted remote shell broker. It is a narrow operational boundary between orchestration systems and real environments.

## Core Idea

LLMs are good at reasoning, planning, and interpreting complex output. Real systems require tools, hardware, shell access, network locality, and execution environments.

`mcp-ssh-gateway` bridges those worlds.

The gateway owns SSH identities, connection configuration, capability discovery, capability caching, execution logging, and transport mechanics. The orchestrator receives operational capability through MCP tools, but does not directly manage passwords, private keys, target addresses, or network topology.

The orchestrator gets capability, not custody.

## Architectural Shape

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

Each configured connection represents a trusted operational arm into a remote environment. The gateway discovers what each environment can do, records normalized capabilities, and exposes those capabilities back through MCP tools.

This allows an LLM to inspect available environments, understand which tools and hardware exist, select the most appropriate machine for a task, and coordinate workflows across multiple remote systems.

## Connection Modes

### Direct Mode

Direct mode is used when the remote machine is reachable from the gateway.

The gateway opens outbound SSH connections directly to the target. This is the simpler model and works well for internal infrastructure, VPN-connected environments, trusted networks, and static lab environments.

### Reverse Tunnel Mode

Reverse tunnel mode is used when the remote environment is not directly reachable from the gateway.

In this model, the remote machine initiates connectivity toward the gateway, exposes its local SSH service through a reverse tunnel, and the gateway connects back through the exposed local port.

This is useful for NATed environments, outbound-only infrastructure, headless devices, remote labs, and restricted networks.

The current configuration value is still:

```json
{
  "mode": "tunnel"
}
```

The documentation uses “reverse tunnel mode” to describe the operational model clearly.

## Capability Discovery

The gateway is designed to discover and normalize information about each remote environment.

Examples include operating system, architecture, hostname, users, network information, installed interpreters, installed tooling, GPU availability, memory, storage, and environment-specific capabilities.

Discovered capabilities are cached and exposed back to the LLM through MCP tools. This allows the LLM to reason about where required tools are available, where hardware acceleration exists, which system has useful network locality, and how multiple systems can collaborate.

## Runbooks and Skills

The gateway is intended to work together with runbooks, skills, procedures, and higher-level orchestration systems such as Open WebUI, n8n, OpenClaw, or other MCP-compatible clients.

The gateway provides operational reach. The orchestrator provides reasoning and workflow composition.

Paired with runbooks and skills, an LLM can plan larger workflows and execute them through real environments while keeping actions visible and attributable.

## Current Implementation Status

The project is in an early implementation phase.

Implemented:

- MCP startup and tool registration foundations
- baseline MCP tools for status/device info, command execution, and file upload
- static connection configuration
- connection pool lifecycle scaffolding
- direct SSH connectivity using Paramiko
- reverse tunnel probing through already exposed local ports
- structured command execution results

Evolving:

- capability discovery model
- normalized capability cache
- execution history model
- task routing support
- onboarding workflows

Not yet implemented:

- full agent-side reverse tunnel SSH listener
- end-to-end reverse tunnel establishment lifecycle
- richer capability orchestration
- advanced workflow execution primitives

Documentation must continue to distinguish implemented behavior from intended architecture.

## Build and Test

```bash
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install pytest
pytest
```

## Run

The current startup path expects a valid connection configuration file.

```bash
python app.py --connection-config ./connections.json
```

## Documentation

- Documentation writing/governance standard: [`docs/DOCUMENTATION_GUIDE.md`](docs/DOCUMENTATION_GUIDE.md)
- Architecture boundaries and system model: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Testing intent and boundary enforcement: [`docs/TESTING_STRATEGY.md`](docs/TESTING_STRATEGY.md)
- Architectural decisions record: [`docs/ARCHITECTURAL_DECISIONS.md`](docs/ARCHITECTURAL_DECISIONS.md)
- Edge connectivity guidance: [`docs/EDGE.md`](docs/EDGE.md)
- Developer workflow: [`docs/DEVELOPER.md`](docs/DEVELOPER.md)
- Security and trust model: [`docs/SECURITY.md`](docs/SECURITY.md)
- Contribution guide: [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)

## License

Apache 2.0.

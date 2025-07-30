# mcp-ssh-gateway

**mcp-ssh-gateway** is a minimal, secure, and composable SSH-based edge management agent. It provides a controlled interface for AI agents or automated systems to interact with remote edge devices using SSH, following a declarative, audit-friendly model.

The gateway runs as a self-contained Docker container, exposing an MCP interface (via `FastMCP`) over STDIO. It manages SSH-based connections to edge systems using static configuration, with support for both direct and reverse-tunnel-based modes.

---

## 🗺️ Why This Exists

As AI systems grow increasingly capable, they face a gap: they can reason about the world, but they can't act on it safely. `mcp-ssh-gateway` is a tool designed to bridge that gap — giving reasoning systems a narrow, trusted interface to reach into real environments.

This project isn't about automation for its own sake. It's about composability and control. It empowers agents — human or machine — to execute operations through clearly defined, auditable, and intention-driven actions. It favors simplicity, security, and introspection over magic and fragility.

This is the agent's arm. It's the tool that allows an AI to run diagnostics, apply patches, gather telemetry, or reconfigure a device — without exposing a full shell, and without relying on scripts with hidden assumptions.

---

## 🔍 Project Goals

* **Simplicity and clarity** over generality or hidden magic
* **Static configuration only** — no dynamic shell execution, scripts, or handshakes
* **Secure by default** — mutual SSH key authentication; no password or interactive login
* **LLM-first** — enables intelligent agents to act, without dictating behavior
* **Separation of concerns** — the agent does not control the tunnel setup, only reacts to it

---

## 📆 How It Works

### Direct Mode (`mode: "direct"`)

In this mode, the agent initiates an outbound SSH connection to the target using its private key.

* The target must be directly reachable (e.g. via VPN or static IP).
* The connection is declared in `connections.json`.
* The agent uses Paramiko to establish the connection and execute commands.

```
Agent → SSH → Target (sshd)
```

---

### Tunnel Mode (`mode: "tunnel"`)

In this mode, the edge device initiates a reverse tunnel **into the agent**, exposing its own `sshd` back to the agent through a loopback port.

* The agent starts a local SSH server using Paramiko.
* The edge connects to this server using `ssh -R`, opening a reverse tunnel (e.g. `-R 22222:localhost:22`).
* The agent detects the tunnel and connects to `127.0.0.1:22222` as if it were a local host.

```
Edge: ssh -R 22222:localhost:22 agent_user@agent_host

Agent: connects to 127.0.0.1:22222 → tunnel → Edge (sshd)
```

The tunnel must be initiated from the edge. The agent does not control or initiate the reverse tunnel.

---

## 🛠 Configuration

All connections are statically defined in a `connections.json` file. Example:

```json
[
  {
    "name": "edge-vm-1",
    "mode": "direct",
    "user": "admin",
    "host": "192.168.1.100",
    "port": 22,
    "id_file": "/data/keys/edge-vm-1.key"
  },
  {
    "name": "edge-vm-2",
    "mode": "tunnel",
    "user": "pi",
    "host": "127.0.0.1",
    "port": 22222,
    "id_file": "/data/keys/edge-vm-2.key"
  }
]
```

* `mode`: "direct" for outbound SSH; "tunnel" for reverse-tunnel probing
* `host`: target hostname or loopback address (`127.0.0.1` in tunnel mode)
* `port`: target SSH port; typically 22 in direct mode or reverse-exposed port in tunnel mode
* `id_file`: private key used to authenticate to the target

---

## 💡 Intended Use Cases

This project is meant to be used in scenarios like:

* Infrastructure inspection and system discovery
* Ad-hoc debugging and remote diagnostics
* Secure reconfiguration of edge devices
* AI-assisted patching or updates
* Agent-driven decision-making under human oversight
* Bootstrapping new devices into managed environments

It works best when paired with an orchestration layer, task planner, or control loop that treats system state as observable and controllable.

---

## 💪 Test and Development

* `direct` mode is tested against a locally spawned `sshd` process
* `tunnel` mode is tested by simulating an edge device that:

  1. Runs its own `sshd`
  2. Initiates a reverse tunnel into the agent using `ssh -R`
  3. Allows the agent to connect to it via loopback port (e.g. `127.0.0.1:22222`)

Test utilities are being added to automate this using pytest fixtures.

---

## 🛡️ Security Model

* All SSH interactions use mutual key-based authentication
* The agent never exposes an interactive shell or login
* Tunnel sessions are strictly for port forwarding (no command execution)
* Audit logs are emitted for all connection events and command executions

---

## 🚀 Roadmap Highlights

* Add command result streaming and structured output
* Add file transfer (SFTP) support via Paramiko
* Add dynamic edge onboarding via metadata handshake
* Add per-connection retry limits and failure tracking

---

## 🚜 Who Should Use This?

This project is for AI agent developers, edge automation engineers, or system integrators who want to give reasoning agents controlled access to real-world systems.

It's ideal when you:

* Need auditable and safe remote access
* Don't want full SSH shells
* Prefer static configuration and trust-first design
* Want to build secure AI-ops automation pipelines

---

## ⚒️ License

Licensed under the Apache 2.0 license.

---

## 😎 Contributions Welcome

See `CONTRIBUTING.md` for guidelines on how to file issues, suggest features, or submit PRs.

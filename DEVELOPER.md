# Developer Guide

This document outlines how to develop, test, and contribute to the `mcp-ssh-gateway` project.

---

## 🧱 Architecture Overview

* The agent is a stateless, self-contained Python service packaged in a Docker container.
* It exposes an MCP interface (via FastMCP) over STDIO.
* It supports two connection modes:

  * **Direct**: agent connects to target via SSH (e.g. over VPN)
  * **Tunnel**: agent starts a `paramiko`-based SSH server; edge devices open reverse tunnels using `ssh -R`

Connections are declared statically in `connections.json`.

---

## 🔧 Development Environment

We recommend using **VSCode + DevContainers**. The repo includes a `.devcontainer/` setup that provides:

* Python environment with dependencies
* Pre-installed keys and test configs
* Port forwarding for test SSHD instances

---

## 🧪 Testing Strategy

### Unit Tests

* Basic validation of `Connection`, `CommandResult`, and config parsing
* Avoid mocking `paramiko` internals — focus on interface-level behavior

### Functional Tests

* Direct mode: use subprocess to spawn a local `sshd` on a random port
* Tunnel mode:

  1. Start a `TunnelConnection` (opens local SSH server)
  2. Simulate edge device with `ssh -R` to expose local sshd
  3. Agent connects via loopback to verify command execution

### Fixtures (Planned)

* `spawn_sshd()` – dynamic temp sshd with authorized\_keys and host keys
* `start_tunnel()` – launch edge-side tunnel process to agent’s listener

---

## 🗂 Directory Layout (WIP)

```
agent/
├── connectionpool/       # Core pool logic and runner classes
├── connection.py         # Connection interface (direct/tunnel)
├── commandresult.py      # Structured command result abstraction
├── configloader.py       # Parses and validates JSON connection config
tests/
├── test_connection_direct.py
├── test_connection_tunnel.py
├── sshd_fixture.py       # SSHD test helpers (planned)
```

---

## 🚧 TODOs and Open Topics

* Retry policies and failure backoff
* Key rotation and key fingerprint pinning
* Improved logging / structured trace output
* Concurrent command execution and session reuse

---

## ✅ Contributions

We welcome small, focused contributions! Please:

* Align with project values (clarity, minimalism, secure-by-default)
* Avoid adding unnecessary abstraction or generalization
* Include tests for new features when feasible

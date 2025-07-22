
# mcp-ssh-gateway

`mcp-ssh-gateway` is a secure, self-contained agent that enables LLMs to inspect, manage, and interact with remote systems via SSH tunnels — **without exposing edge devices to inbound network traffic**. It bridges the cognitive power of AI with the practical ability to reach and modify systems, all under tight operational and security control.

---

## 🧭 Project Purpose

Modern AI agents need not just intelligence — they need **reach**. `mcp-ssh-gateway` gives LLMs that reach, by providing a trusted, auditable bridge between thought and action.

### Key Use Cases

- ✅ LLM-driven system inspection, diagnostics, and remediation
- ✅ Secure AI-powered infrastructure discovery and OS hardening
- ✅ Automated forensics and incident triage via remote shell
- ✅ Controlled remote development and code review
- ✅ Scriptable, intelligent system lifecycle operations

The gateway is **task-agnostic** — it doesn’t prescribe what the LLM should do. It simply enables **secure, structured action**.

---

## 🔐 Security Model

### 🔒 Secure by Default

- Default mode is **reverse SSH**, where the **edge device connects to the agent**
- This avoids opening SSH ports in untrusted, remote, or NAT'd environments
- Edges **cannot** execute commands on the agent — only the reverse

### 🔑 Key Management Principles

- Private keys are **never exchanged over MCP**
- Admins must mount:
  - Agent host key (`host_rsa`)
  - Authorized edge public keys (`authorized_keys`)
- LLMs can request key fingerprints or provisioning help — but **never see private credentials**

### 🛡️ Centralized Control

- Agent is operated from **trusted infrastructure**
- All execution occurs on the **edge**, initiated by the **agent**
- Supports optional `inbound` SSH mode for trusted environments, clearly marked as less secure

---

## 🏗 Architecture Overview

```plaintext
   +-----------------+               +--------------------------+
   |   OpenWebUI /   |   MCP (STDIO) |    mcp-ssh-gateway Agent |
   |      LLM        +<------------->+    (Docker Container)    |
   +-----------------+               +--------------------------+
                                              |
                                              | Reverse SSH Tunnel
                                              v
                                 +-----------------------------+
                                 |      Edge Device            |
                                 |  (No open ports required)   |
                                 +-----------------------------+
```

---

## ⚙️ Usage

### 🔧 Docker (Preferred)

```bash
docker run --rm -it \
  -v $PWD/keys:/keys \
  -e GATEWAY_MODE=reverse \
  -e SSH_PORT=2222 \
  -e PROVISION_TOKEN=your-secret-token \
  -p 3333:3333 \
  mcp-ssh-gateway
```

Expected key mounts:

- `/keys/host_rsa` – SSH private key for the agent
- `/keys/authorized_keys` – list of trusted edge public keys

### 🐍 Bare Metal (Advanced)

```bash
export GATEWAY_MODE=reverse
export PROVISION_TOKEN=your-secret-token
python3 agent.py
```

Dependencies: `openssh-server`, `paramiko`, `mcp`

---

## 🛰️ MCP Functions

### `get_status`
Returns whether an edge device is currently connected.

### `register_edge_key`
Registers a new edge public key (requires `PROVISION_TOKEN`).

### `get_agent_pubkey`
Returns the public SSH key of the agent for provisioning.

### `run_command`
Executes a command on the connected edge device.

### `upload_file`
Uploads a file to the edge system.

### `get_device_info`
Returns OS type, CPU, RAM, and capability summary.

---

## 🧩 Connection Modes

| Mode | Description |
|------|-------------|
| `reverse` (default) | Edge device initiates the connection to the agent |
| `inbound` (optional) | Agent listens for incoming SSH connections (less secure) |

Set via `GATEWAY_MODE=reverse` or `GATEWAY_MODE=inbound`.

---

## 🛠 Developer Guide

### Run Dev Environment

```bash
docker build -t mcp-ssh-gateway .
docker run -v $PWD:/app -it mcp-ssh-gateway /bin/bash
```

### Contribute

- Fork and submit PRs
- Write tests for MCP functions
- Respect secure-by-default principle
- Contributions to onboarding flows and observability are welcome!

---

## 📜 License

MIT License

---

## 👥 Maintainers

Maintained by the `mcp-ssh-gateway` project team.

---

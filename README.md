
# mcp-ssh-gateway

`mcp-ssh-gateway` is a lightweight, secure SSH control agent designed to bridge the gap between LLMs and the real world. It enables a trusted Large Language Model (LLM) to connect with and execute tasks on remote edge devices — securely, predictably, and audibly — through managed SSH reverse tunnels.

It is not another automation tool. It is not a shell wrapper. It is an **interface between intelligent agents and practical systems**, a way for cognitive AI to extend its reach into systems, devices, and runtime environments — all under full administrative control.

---

## 🚀 Why This Project Exists

Modern AI systems are becoming increasingly capable of analyzing, planning, and adapting. However, their ability to act on live systems remains gated by security, observability, and infrastructure barriers.

`mcp-ssh-gateway` solves that problem.

It provides a clean, secure protocol boundary for remote execution, turning AI agents from passive advisors into active collaborators.

Use it to:
- Inspect systems and report findings
- Run security audits or OS updates
- Apply fixes, deploy containers, or manage source code
- Review and contribute to software projects
- Discover capabilities and choose optimal systems for a given task

---

## 🔐 Security-First Design

Security is not an afterthought — it's the starting point.

- ✅ **Reverse SSH by default**: The agent never initiates a connection to the edge unless explicitly configured. This prevents the need to expose edge ports to the internet.
- ✅ **No command execution on the agent**: The gateway never allows edges to execute code on the control side.
- ✅ **Token-based MCP authorization**: Sensitive actions like registering a new edge key are guarded by a static token.
- ✅ **No key transmission over MCP**: Private keys are never shared via the protocol. Admins control key provisioning.

---

## 🧱 Architecture Overview

```plaintext
   +-------------------+               +----------------------------+
   |   OpenWebUI /     |   MCP (STDIO) |  mcp-ssh-gateway (Agent)   |
   |    LLM Client     +<------------->+  Docker or bare-metal host |
   +-------------------+               +----------------------------+
                                                 |
                                                 | Reverse SSH Tunnel
                                                 v
                                    +-----------------------------+
                                    |      Edge Device            |
                                    |  (Behind NAT or firewall)   |
                                    +-----------------------------+
```

---

## ⚙️ Quick Start

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

### 🐍 Bare Metal (Advanced)

```bash
export GATEWAY_MODE=reverse
export PROVISION_TOKEN=your-secret-token
python3 agent/main.py
```

Keys must be mounted into the container or accessible from the file system:
- `/keys/host_rsa` – The SSH private key of the agent
- `/keys/authorized_keys` – List of trusted public keys for incoming edge connections

---

## ✨ Core Features

- 🛡 Secure-by-default reverse SSH gateway
- 🔁 Auto-discovers connected edge device capabilities
- ⚙️ Remote execution and file upload via MCP
- 📜 Lightweight, auditable, and LLM-friendly STDIO protocol
- 🧩 Drop-in support for OpenWebUI via `mcpo`

---

## 🛰 MCP Functions

| Function | Purpose |
|----------|---------|
| `get_status` | Reports connection and session state |
| `register_edge_key` | Adds a new authorized key (requires token) |
| `get_agent_pubkey` | Returns the agent’s public key |
| `run_command` | Executes a command on the edge |
| `upload_file` | Uploads a file to the edge |
| `get_device_info` | Returns system info and capabilities |

---

## 🛠️ Developer Guide

### Development Flow

```bash
docker build -t mcp-ssh-gateway .
docker run -v $PWD:/app -it mcp-ssh-gateway /bin/bash
```

Or run it locally using:

```bash
python3 agent/main.py
```

### Contributing

- Fork and PR on GitHub
- Adhere to security model (reverse shell only, no private key exchange)
- Improve onboarding, key management, observability, and protocol handlers

---

## 📜 License

Licensed under the Apache License, Version 2.0.

---

## 👥 Maintainers

Maintained by the `mcp-ssh-gateway` project team.

---

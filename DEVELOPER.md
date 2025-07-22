# Developer Guide – mcp-ssh-gateway

This document provides everything you need to understand, modify, and extend the `mcp-ssh-gateway` project. It’s written to capture the design intent so that new contributors — including code generation tools — can work effectively without prior context.

---

## 🧠 Project Overview

`mcp-ssh-gateway` is a minimal, secure agent designed to connect edge devices to a control plane powered by an LLM, using a reverse SSH tunnel. It exposes a set of capabilities through the [MCP protocol](https://docs.openwebui.com/openapi-servers/mcp/), allowing the LLM to inspect and interact with the system.

- The agent **does not execute commands from edge devices**
- Edge devices **initiate** the SSH connection
- All logic and control flows from the agent (not the edge)

---

## 🏛 Architecture Overview

```text
+---------------------+              +------------------------+
|     Edge Device     |              |        MCP LLM         |
|---------------------|              |------------------------|
| ssh -> mcp-ssh-gw   |  <-------->  |  OpenWebUI + mcpo      |
|                     |              |                        |
+---------------------+              +------------------------+
             ^                                  ^
             |                                  |
             |   Reverse SSH Tunnel (Port X)    |
             +----------------------------------+

```

- **Agent runs** an SSH server inside a Docker container
- **Edge device connects** using reverse tunnel: `ssh -R`
- **Agent exposes** capabilities over STDIO via MCP
- **LLM client** (via OpenWebUI/mcpo) connects to the agent container and interacts with the system

---

## 📁 File Structure

```text
mcp-ssh-gateway/
│
├── Dockerfile              # Container image for the agent
├── main.py                 # Entrypoint, runs the MCP loop
├── mcp_handlers.py         # Implements MCP method handlers
├── ssh_utils.py            # SSH key exchange and connection logic
├── scripts/                # Shell scripts for capability discovery
├── EDGE.md                 # Edge device onboarding guide
├── README.md               # Project overview and usage
├── SECURITY.md             # Responsible disclosure and threat model
└── CONTRIBUTING.md         # How to contribute safely
```

---

## 🧱 Design Principles

- **Secure by default**: No agent-side shell execution. Key-based auth only.
- **LLM-driven**: Agent is task-agnostic. Prompts define purpose.
- **Reverse only**: Edge devices initiate; agent never opens connections.
- **Single connection per device**: One port, one edge.
- **Minimal base image**: OpenSSH + Python, no bloat.

---

## 🔌 Extending Capabilities

Each capability (e.g., `get_os_info`, `list_processes`, etc.) is implemented as an MCP method.

To add a new one:

1. Define the method in `mcp_handlers.py`
2. If needed, add a script to `scripts/`
3. Ensure the output is machine-readable (e.g., JSON, line-separated)
4. Add discovery hints so LLM clients can query capabilities

Example:
```python
def get_os_info():
    return run_script("scripts/os_info.sh")
```

---

## 🧪 Running and Debugging

### Bare Metal

```bash
python3 main.py
```

### Docker

```bash
docker build -t mcp-ssh-gateway .
docker run -p 22222:22 -it mcp-ssh-gateway
```

### Logs

Agent logs to STDOUT. You can attach to the container or view logs via `docker logs`.

---

## 🔄 Edge Connection Lifecycle

1. Edge device connects using `ssh -R`
2. Agent logs and detects connection
3. Agent exposes the device via MCP
4. LLM connects via mcpo and begins interaction

---

## ✅ Best Practices

- Use key pairs only; no password auth
- Do not expose agent to public Internet without firewall
- Maintain script outputs in deterministic formats
- Use small, atomic shell scripts that can be composed

---

## 📣 Final Notes

This project is built for **experimentation**, **security research**, and **empowered system introspection**. Treat it as a programmable control surface — and respect the boundaries it enforces.

For questions or collaboration, please open a GitHub issue or contribute via pull request.

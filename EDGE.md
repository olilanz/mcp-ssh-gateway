# Connecting an Edge Device

This guide explains how to connect an edge device to the `mcp-ssh-gateway` agent using reverse SSH.

## 🧭 Overview

The edge device initiates a reverse SSH tunnel to the gateway agent. Once the connection is live, the agent can inspect, interact with, and run commands on the edge — securely and under LLM control via MCP.

## 🔐 Prerequisites

- Edge device must have:
  - SSH client installed (`openssh-client`)
  - The agent's **public key**
- Agent must have:
  - SSH server (`sshd`) running
  - The edge device's **public key** registered

---

## 🗝️ Key Exchange

### 1. On the Edge Device

Generate SSH key pair if not already present:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
```

Send the **public key** (`~/.ssh/id_ed25519.pub`) to the agent administrator.

### 2. On the Agent

Place the received public key into `~/.ssh/authorized_keys` for the user handling edge logins (usually a restricted user like `edgebot`).

---

## 🔄 Establish Reverse SSH

On the edge device:

```bash
ssh -N -R <remote-port>:localhost:22 edgebot@<agent-address> -i ~/.ssh/id_ed25519
```

- Replace `<remote-port>` with a preferred port (within an agreed range)
- Replace `<agent-address>` with the public IP or DNS of the agent
- You can use `autossh` for automatic reconnections

Once connected, the agent will detect the tunnel and expose the system to the MCP layer.

---

## ✅ Verification

1. The agent logs the new connection
2. The device is now accessible through the MCP API
3. OpenWebUI or another client can request:
   - OS information
   - Installed tools
   - Available capabilities
   - Health status

---

## 🧰 Tips

- Use systemd or cron to reconnect on boot
- Prefer low, unused port ranges for tunneling (e.g. 22220–22250)
- Use a non-root user for added safety
- Monitor agent logs for accepted connections

---

## 🛡 Security Reminder

- The edge device **cannot** execute commands on the agent
- The agent will only act **after** secure connection and validation
- Use firewalls to restrict outbound access if necessary


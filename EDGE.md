# Connecting an Edge Device

Depending on your infrastructure and use case, you may choose between two connection modes:

## ✅ Direct Mode ("direct")

Direct mode is the simplest option and works well in **trusted infrastructure**, where:

* The agent can reach the edge directly over the network
* The edge is on a VPN, local subnet, or has a fixed IP address

In this setup, the agent connects *to* the edge using SSH. The edge runs `sshd` and listens on a known IP and port.

**Recommended for:**

* Internal or development networks
* When you control the edge environment and trust the network

No special configuration is needed on the edge, except:

* Ensure `sshd` is running
* Add the agent’s public key to `~/.ssh/authorized_keys`

## 🔁 Tunnel Mode ("tunnel")

Tunnel mode is intended for **locked-down infrastructure**, where the edge is **not reachable from the agent**, but the agent is reachable from the edge.

This is common in real-world edge scenarios:

* Headless devices behind NAT or firewalls
* Mobile or intermittent connectivity
* Secure environments with outbound-only traffic

### How It Works

The agent starts an embedded SSH server using `paramiko`. The edge device connects to this SSH server and opens a reverse tunnel like so:

```bash
ssh -i edge.key \
    -R 22222:localhost:22 \
    agent_user@agent_host -p <agent_tunnel_port>
```

This exposes the edge's own `sshd` (on port 22) back through the tunnel. Once connected, the agent will:

* Detect the active tunnel
* Connect to `127.0.0.1:22222`
* Authenticate using its key

**Recommended for:**

* Headless, mobile, or firewalled edge devices
* Environments where outbound tunnels are easier than inbound access

### Required on the Edge

* `sshd` must be running
* An identity key must be available to connect to the agent
* A startup script or systemd service can be used to maintain the reverse tunnel

Example (simplified):

```bash
ssh -N \
    -o ExitOnForwardFailure=yes \
    -i /etc/ssh/edge.key \
    -R 22222:localhost:22 \
    agent@agent.example.com -p 2222
```

This command can be made persistent with `autossh`, a shell loop, or systemd.

## 🔐 Mutual Trust

Both sides must trust each other:

* The edge must know the agent’s public key to allow the reverse tunnel
* The agent must know the edge’s public key to connect back through the tunnel

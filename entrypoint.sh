#!/bin/bash

set -e

echo "[mcp-ssh-gateway] Launching sshd for tunneling on port ${SSH_LISTEN_PORT:-22}"

# Copy keys if supplied
mkdir -p /etc/ssh

if [ -f /keys/id_rsa ]; then
    echo "[mcp-ssh-gateway] Copying private SSH host key from /keys/id_rsa"
    cp /data/keys/id_rsa /etc/ssh/ssh_host_rsa_key
    chmod 600 /etc/ssh/ssh_host_rsa_key
fi

if [ -f /keys/id_rsa.pub ]; then
    echo "[mcp-ssh-gateway] Copying SSH public host key from /keys/id_rsa.pub"
    cp /data/keys/id_rsa.pub /etc/ssh/ssh_host_rsa_key.pub
    chmod 644 /etc/ssh/ssh_host_rsa_key.pub
fi

if [ -f /keys/id_rsa ]; then
    echo "[mcp-ssh-gateway] Copying SSH authorized keys from /keys/authorized_keys"
    cp /data/keys/authorized_keys /etc/ssh/authorized_keys
    chmod 600 /etc/ssh/authorized_keys
fi

# Ensure SSH host keys exist
if [ ! -f /etc/ssh/ssh_host_rsa_key ]; then
    echo "[ERROR] SSH host key /etc/ssh/ssh_host_rsa_key not found."
    exit 1
fi

# Ensure privilege separation directory exists
mkdir -p /run/sshd


# Start the SSH daemon as a service
echo "[mcp-ssh-gateway] Starting sshd service"
service ssh start

# Start the agent (MCP loop)
exec mcpo --host 0.0.0.0 --port ${MCPO_PORT} -- python3 /app/app.py --config /data/config/connections.json

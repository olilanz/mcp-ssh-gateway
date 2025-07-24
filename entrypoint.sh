#!/bin/bash

set -e

echo "[mcp-ssh-gateway] Starting in $GATEWAY_MODE mode"

if [ "$GATEWAY_MODE" = "inbound" ]; then
    echo "[mcp-ssh-gateway] Launching sshd in inbound mode on port ${SSH_PORT:-2222}"
    
    # Copy keys if supplied
    mkdir -p /etc/ssh

    if [ -f /keys/id_rsa ]; then
        cp /keys/id_rsa /etc/ssh/ssh_host_rsa_key
        chmod 600 /etc/ssh/ssh_host_rsa_key
    fi

    if [ -f /keys/id_rsa.pub ]; then
        cp /keys/id_rsa.pub /etc/ssh/ssh_host_rsa_key.pub
        chmod 644 /etc/ssh/ssh_host_rsa_key.pub
    fi

    # Ensure SSH host keys exist
    if [ ! -f /etc/ssh/ssh_host_rsa_key ]; then
        echo "[ERROR] SSH host key /etc/ssh/ssh_host_rsa_key not found."
        exit 1
    fi

    # Create default config if needed
    echo "[mcp-ssh-gateway] Configuring SSH daemon..."
    echo "Port ${SSH_LISTEN_PORT}" > /etc/ssh/sshd_config
    echo "PermitRootLogin no" >> /etc/ssh/sshd_config
    echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
    echo "PermitEmptyPasswords no" >> /etc/ssh/sshd_config
    echo "ChallengeResponseAuthentication no" >> /etc/ssh/sshd_config
    echo "UsePAM no" >> /etc/ssh/sshd_config
    echo "AuthorizedKeysFile /keys/authorized_keys" >> /etc/ssh/sshd_config

    # Start SSH server
    exec /usr/sbin/sshd -D -e
else
    echo "[mcp-ssh-gateway] Running in reverse tunnel mode"
    echo "[mcp-ssh-gateway] No SSH daemon exposed. Awaiting edge connection."
    
    # Optional: validate keys exist
    if [ ! -f /keys/authorized_keys ]; then
        echo "[WARNING] No authorized_keys found. You must register edges at runtime."
    fi
fi

# Start the agent (MCP loop)
exec mcpo --host 0.0.0.0 --port ${MCPO_PORT} python3 /app/app.py

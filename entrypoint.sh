#!/bin/bash

set -e

echo "[mcp-ssh-gateway] Starting in $GATEWAY_MODE mode"

if [ "$GATEWAY_MODE" = "inbound" ]; then
    echo "[mcp-ssh-gateway] Launching sshd in inbound mode on port ${SSH_LISTEN_PORT:-22}"
    
    # Copy keys if supplied
    mkdir -p /etc/ssh

    if [ -f /keys/id_rsa ]; then
        echo "[mcp-ssh-gateway] Copying private SSH host key from /keys/id_rsa"
        cp /keys/id_rsa /etc/ssh/ssh_host_rsa_key
        chmod 600 /etc/ssh/ssh_host_rsa_key
    fi

    if [ -f /keys/id_rsa.pub ]; then
        echo "[mcp-ssh-gateway] Copying SSH public host key from /keys/id_rsa.pub"
        cp /keys/id_rsa.pub /etc/ssh/ssh_host_rsa_key.pub
        chmod 644 /etc/ssh/ssh_host_rsa_key.pub
    fi

    if [ -f /keys/id_rsa ]; then
        echo "[mcp-ssh-gateway] Copying SSH authorized keys from /keys/authorized_keys"
        cp /keys/authorized_keys /etc/ssh/authorized_keys
        chmod 600 /etc/ssh/authorized_keys
    fi

    # Ensure SSH host keys exist
    if [ ! -f /etc/ssh/ssh_host_rsa_key ]; then
        echo "[ERROR] SSH host key /etc/ssh/ssh_host_rsa_key not found."
        exit 1
    fi

    # Create default config if needed
    echo "[mcp-ssh-gateway] Configuring SSH daemon..."

    echo "Port ${SSH_LISTEN_PORT}" > /etc/ssh/sshd_config
    echo "PermitRootLogin prohibit-password" >> /etc/ssh/sshd_config # can be tightened
    echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
    echo "PermitEmptyPasswords no" >> /etc/ssh/sshd_config
    echo "ChallengeResponseAuthentication no" >> /etc/ssh/sshd_config
    echo "UsePAM no" >> /etc/ssh/sshd_config

    echo "GatewayPorts yes" >> /etc/ssh/sshd_config
    echo "AllowTcpForwarding yes" >> /etc/ssh/sshd_config
    echo "PermitOpen any" >> /etc/ssh/sshd_config # can be tightened 

    echo "AuthorizedKeysFile /etc/ssh/authorized_keys" >> /etc/ssh/sshd_config

    # Ensure privilege separation directory exists
    mkdir -p /run/sshd

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

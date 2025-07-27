# Removed unused imports
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

from typing import Optional
from agent.connection_result import CommandResult
from enum import Enum
from agent.connectionpool.config_loader import ConnectionMode

class ConnectionState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    CONNECTING = "connecting"
    BROKEN = "broken"

def _resolve_target(self) -> tuple[str, int]:
    """Resolve the target host and port based on the connection mode."""
    if self.mode == ConnectionMode.TUNNEL:
        return ("localhost", self.port)
    return (self.host, self.port)


class Connection:
    def __init__(self, connection_config):
        self.config = connection_config
        self.name = connection_config.name
        self.user = connection_config.user
        self.id_file = connection_config.id_file
        self.mode = ConnectionMode(connection_config.mode)  # Imported from config_loader.py
        self.port = connection_config.port
        self.host = connection_config.host  # Only required for "direct"
        self.state = ConnectionState.CLOSED
        self.metadata = {"os_version": None, "architecture": None}
        self._history = []  # Track command execution history
        self._ssh = None  # Initialize the SSH client attribute

    def open(self):
        """Open the connection using Paramiko and update its state."""
        from paramiko import SSHClient, AutoAddPolicy

        logging.info(f"🔌 Opening connection: {self.name}")
        self.state = ConnectionState.CONNECTING

        try:
            self._ssh = SSHClient()
            self._ssh.set_missing_host_key_policy(AutoAddPolicy())
            self._ssh.connect(
                hostname=self.host,
                port=self.port,
                username=self.user,
                key_filename=self.id_file
            )
            self.state = ConnectionState.OPEN
        except Exception as e:
            logging.error(f"❌ Failed to open connection: {e}")
            self.state = ConnectionState.BROKEN
            raise RuntimeError("Failed to establish connection.") from e

    def close(self):
        """Close the Paramiko connection and update its state."""
        logging.info(f"🛑 Closing connection: {self.name}")
        if hasattr(self, "_ssh") and self._ssh:
            self._ssh.close()
        self.state = ConnectionState.CLOSED

    def execute(self, command: str) -> CommandResult:
        """Execute a command on the remote system using Paramiko."""
        from datetime import datetime

        if not self._ssh:
            raise RuntimeError("Connection is not open. Cannot execute command.")

        logging.info(f"Executing command on {self.name}: {command}")
        from datetime import timezone
        started_at = datetime.now(timezone.utc)

        try:
            stdin, stdout, stderr = self._ssh.exec_command(command)
            exit_code = stdout.channel.recv_exit_status()
            ended_at = datetime.now(timezone.utc)

            result = CommandResult(
                command=command,
                exit_code=exit_code,
                stdout=stdout.read().decode(),
                stderr=stderr.read().decode(),
                started_at=started_at,
                ended_at=ended_at
            )
            self._history.append(result)
            return result
        except Exception as e:
            logging.error(f"❌ Command execution failed: {e}")
            raise RuntimeError(f"Failed to execute command: {command}") from e

    def run(self, command: str):
        """Run an interactive command on the remote system."""
        raise NotImplementedError("Interactive command execution is not yet implemented.")


        # Removed threading and subprocess attributes

    # Removed start() method

    # Removed stop() method

    # Removed is_running() method

    # Removed _run_loop() method

    # Removed _build_ssh_command() method

        if self.mode == "direct":
            local_forward = f"{self.port}:localhost:22"
            base_cmd += ["-L", local_forward, f"{self.user}@{self.host}", "-p", str(self.port)]
        elif self.mode == "tunnel":
            reverse_forward = f"{self.port}:localhost:22"
            base_cmd += ["-R", reverse_forward, f"{self.user}@localhost"]
        else:
            raise ValueError(f"Unknown mode: {self.mode}")
    
            return base_cmd

    def get_state(self) -> ConnectionState:
        """Return the current state of the connection."""
        return self.state
    
    def describe(self) -> dict:
        """Describe the connection's metadata and history."""
        return {
            "name": self.name,
            "state": self.state.value,
            "metadata": self.metadata,
            "history": [result.to_dict() for result in self._history],
        }
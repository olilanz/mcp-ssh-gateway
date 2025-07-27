import subprocess
import threading
import time
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
        self._stop_event = threading.Event()
        self._process = None  # Initialize the process attribute
        self._thread = threading.Thread(target=self._run_loop, daemon=True)

    def open(self):
        """Open the connection and update its state."""
        logging.info(f"🔌 Opening connection: {self.name}")
        self.state = ConnectionState.CONNECTING
        self.start()
        self.state = ConnectionState.OPEN

    def close(self):
        """Close the connection and update its state."""
        logging.info(f"🛑 Closing connection: {self.name}")
        self.stop()
        self.state = ConnectionState.CLOSED

    def execute(self, command: str) -> CommandResult:
        """Execute a command on the remote system using paramiko."""
        from paramiko import SSHClient, AutoAddPolicy
        from datetime import datetime
        from agent.connection_result import CommandResult

        logging.info(f"Executing command on {self.name}: {command}")
        ssh = SSHClient()
        ssh.set_missing_host_key_policy(AutoAddPolicy())
        ssh.connect(hostname=self.host, port=self.port, username=self.user, key_filename=self.id_file)

        started_at = datetime.utcnow()
        stdin, stdout, stderr = ssh.exec_command(command)
        exit_code = stdout.channel.recv_exit_status()
        ended_at = datetime.utcnow()

        result = CommandResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout.read().decode(),
            stderr=stderr.read().decode(),
            started_at=started_at,
            ended_at=ended_at
        )
        ssh.close()

        self._history.append(result)
        return result

    def run(self, command: str):
        """Run an interactive command on the remote system."""
        raise NotImplementedError("Interactive command execution is not yet implemented.")


        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._process = None  # Initialize the process attribute

    def start(self):
        logging.info(f"🔌 Starting connection: {self.name}")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        logging.info(f"🛑 Stopping connection: {self.name}")
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def is_running(self):
        return self._thread.is_alive()

    def _run_loop(self):
        while not self._stop_event.is_set():
            cmd = self._build_ssh_command()
            logging.info(f"▶️ Launching SSH for {self.name}: {' '.join(cmd)}")

            try:
                self._process = subprocess.Popen(cmd)
                self._process.wait()
                logging.warning(f"⚠️ SSH process for {self.name} exited with code {self._process.returncode}")
            except Exception as e:
                logging.error(f"❌ Failed to start SSH for {self.name}: {e}")

            if not self._stop_event.is_set():
                logging.info(f"⏳ Retrying {self.name} in 5 seconds...")
                time.sleep(5)

    def _build_ssh_command(self):
        base_cmd = [
            "ssh",
            "-i", self.id_file if self.id_file else "/dev/null",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ExitOnForwardFailure=yes",
            "-N"  # No remote command execution
        ]

        # Ensure all elements in the command are strings
        base_cmd = [str(item) for item in base_cmd]

        if self.mode.value == "direct":
            local_forward = f"{self.port}:localhost:22"
            base_cmd += ["-L", local_forward, f"{self.user}@{self.host}", "-p", str(self.port)]
        elif self.mode.value == "tunnel":
            reverse_forward = f"{self.port}:localhost:22"
            base_cmd += ["-R", reverse_forward, f"{self.user}@localhost"]
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

        return base_cmd

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
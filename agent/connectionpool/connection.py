import subprocess
import threading
import time
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

from typing import Optional
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
        self._stop_event = threading.Event()
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

    def execute_command(self, command: str) -> str:
        """Execute a command on the remote system."""
        logging.info(f"Executing command on {self.name}: {command}")
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            logging.error(f"Command failed on {self.name}: {result.stderr}")
            raise RuntimeError(f"Command execution failed: {result.stderr}")
        return result.stdout

    def upload_file(self, local_path: str, remote_path: str):
        """Upload a file to the remote system."""
        logging.info(f"Uploading file to {self.name}: {local_path} -> {remote_path}")
        subprocess.run(["scp", "-i", self.id_file, local_path, f"{self.user}@{self.host}:{remote_path}"], check=True)

    def download_file(self, remote_path: str, local_path: str):
        """Download a file from the remote system."""
        logging.info(f"Downloading file from {self.name}: {remote_path} -> {local_path}")
        subprocess.run(["scp", "-i", self.id_file, f"{self.user}@{self.host}:{remote_path}", local_path], check=True)

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
            "-i", self.id_file,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ExitOnForwardFailure=yes",
            "-N"  # No remote command execution
        ]

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

    def get_connection_state(self):
        """Retrieve the current state of the connection."""
        if self._process and self._process.poll() is None:
            return "running"
        elif self._stop_event.is_set():
            return "stopped"
        else:
            return "not running"
        return base_cmd
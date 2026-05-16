"""Connection lifecycle primitives for direct and reverse-tunnel reachability.

Local boundary notes:
- `Connection` is the public facade used by pool logic and tests.
- Tunnel mode in this module is probe/connect-through-local-port behavior.
- A full agent-side reverse tunnel listener lifecycle is not implemented here.
"""

import logging
import threading
import time
from enum import Enum
from typing import Optional, List
from paramiko import SSHClient, AutoAddPolicy
from agent.connection_result import CommandResult
from agent.connectionpool.config_loader import ConnectionMode, ConnectionConfig

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')


class ConnectionState(Enum):
    CLOSED = "closed"           # Not connected
    OPENING = "opening"         # Trying to establish connection
    OPEN = "open"               # Connection established
    BROKEN = "broken"           # Was open, but failed


class OneShotRepeatingTimer:
    """
    A helper class for registering recurring actions using a one-shot timer model.
    Each callback is responsible for rescheduling the next timer.
    """
    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._stopped = False
        self._running = False

    def start(self):
        with self._lock:
            if self._stopped or self._running:
                return
            self._running = True
            self._timer = threading.Timer(self.interval, self._run)
            self._timer.daemon = True
            self._timer.start()

    def _run(self):
        try:
            self.callback()
        finally:
            with self._lock:
                self._running = False
                if not self._stopped:
                    self._timer = threading.Timer(self.interval, self._run)
                    self._timer.daemon = True
                    self._timer.start()

    def cancel(self):
        with self._lock:
            self._stopped = True
            if self._timer:
                self._timer.cancel()
                self._timer = None


class BaseConnection:
    """
    Abstract base class for connections. Implements state handling,
    health monitoring, and common metadata logic.
    """
    def __init__(self, config):
        self.name = config.name
        self.user = config.user
        self.id_file = config.id_file
        self.mode = ConnectionMode(config.mode)
        self.port = config.port
        self.host = config.host
        self.state = ConnectionState.CLOSED
        self.metadata = {"os_version": None, "architecture": None}
        self._history: List[CommandResult] = []
        self._ssh: Optional[SSHClient] = None
        self._health_timer: Optional[OneShotRepeatingTimer] = None
        self._lock = threading.Lock()

    def open(self):
        raise NotImplementedError

    def close(self):
        with self._lock:
            logging.info(f"🛑 Closing connection: {self.name}")
            if self._ssh:
                self._ssh.close()
            self._ssh = None
            self.state = ConnectionState.CLOSED
            if self._health_timer:
                self._health_timer.cancel()
                self._health_timer = None

    def execute(self, command: str, timeout: int | float | None = None) -> CommandResult:
        import threading as _threading
        from datetime import datetime, timezone
        with self._lock:
            if not self._ssh:
                raise RuntimeError("Connection is not open.")

            started_at = datetime.now(timezone.utc)
            logging.info(f"💻 Executing on {self.name}: {command}")
            stdin, stdout, stderr = self._ssh.exec_command(command)

            # recv_exit_status() internally waits on a threading.Event and ignores
            # channel.settimeout(), so we enforce the deadline via a worker thread.
            exit_code_holder: list = [None]
            exc_holder: list = [None]

            def _wait():
                try:
                    exit_code_holder[0] = stdout.channel.recv_exit_status()
                except Exception as e:
                    exc_holder[0] = e

            t = _threading.Thread(target=_wait, daemon=True)
            t.start()
            t.join(timeout)

            if t.is_alive():
                # Close the channel to unblock the waiting thread
                try:
                    stdout.channel.close()
                except Exception:
                    pass
                raise TimeoutError(
                    f"Command timed out after {timeout}s on {self.name}: {command}"
                )

            if exc_holder[0] is not None:
                raise exc_holder[0]

            ended_at = datetime.now(timezone.utc)

            result = CommandResult(
                command=command,
                exit_code=exit_code_holder[0],
                stdout=stdout.read().decode(),
                stderr=stderr.read().decode(),
                started_at=started_at,
                ended_at=ended_at
            )
            self._history.append(result)
            return result

    def upload_file(self, remote_path: str, data_b64: str, mode: str = "0644") -> dict:
        """Upload a base64-encoded file to the remote node via SFTP.

        Args:
            remote_path: Absolute path on the remote node.
            data_b64:    Base64-encoded file content.
            mode:        Unix permission mode string (e.g. "0644"). Default "0644".

        Returns:
            {"status": "written", "path": remote_path} on success.
            {"error": "invalid_base64", "path": remote_path} on bad base64 input.
            {"error": "invalid_mode", "path": remote_path, "mode": mode} on bad mode string.
        """
        import base64
        import binascii
        import io
        import re

        # Validate base64
        try:
            data = base64.b64decode(data_b64, validate=True)
        except (binascii.Error, ValueError):
            return {"error": "invalid_base64", "path": remote_path}

        # Validate mode (3 or 4 octal digits)
        if not re.match(r'^[0-7]{3,4}$', mode):
            return {"error": "invalid_mode", "path": remote_path, "mode": mode}

        with self._lock:
            if not self._ssh:
                raise RuntimeError("Connection is not open.")
            sftp = self._ssh.open_sftp()
            try:
                sftp.putfo(io.BytesIO(data), remote_path)
                sftp.chmod(remote_path, int(mode, 8))
            finally:
                sftp.close()

        return {"status": "written", "path": remote_path}

    def download_file(self, remote_path: str) -> dict:
        """Download a file from the remote node via SFTP, returning base64-encoded content.

        Args:
            remote_path: Absolute path on the remote node.

        Returns:
            {"status": "ok", "path": remote_path, "data_b64": "<b64>"} on success.
            {"error": "file_too_large", "path": remote_path, "size_bytes": n, "limit_bytes": 10485760}
                if file exceeds 10 MB (checked via sftp.stat before download).
            {"error": "file_not_found", "path": remote_path} on IOError/FileNotFoundError.
        """
        import base64
        import io

        _LIMIT = 10 * 1024 * 1024  # 10 MB

        with self._lock:
            if not self._ssh:
                raise RuntimeError("Connection is not open.")
            sftp = self._ssh.open_sftp()
            try:
                # Size guard via stat (best-effort — proceed if stat fails)
                try:
                    st = sftp.stat(remote_path)
                    if st.st_size > _LIMIT:
                        return {
                            "error": "file_too_large",
                            "path": remote_path,
                            "size_bytes": st.st_size,
                            "limit_bytes": _LIMIT,
                        }
                except IOError:
                    pass  # stat unavailable — proceed best-effort

                buf = io.BytesIO()
                try:
                    sftp.getfo(remote_path, buf)
                except (IOError, FileNotFoundError):
                    return {"error": "file_not_found", "path": remote_path}
            finally:
                sftp.close()

        data_b64 = base64.b64encode(buf.getvalue()).decode()
        return {"status": "ok", "path": remote_path, "data_b64": data_b64}

    def describe(self):
        return {
            "name": self.name,
            "state": self.state.value,
            "metadata": self.metadata,
            "history": [r.to_dict() for r in self._history]
        }

    def get_state(self):
        return self.state

    def _start_health_check(self):
        def check():
            with self._lock:
                if self._ssh:
                    transport = self._ssh.get_transport()
                    if transport and not transport.is_active():
                        logging.warning(f"❌ Health check failed: {self.name} appears broken.")
                        self.state = ConnectionState.BROKEN
        self._health_timer = OneShotRepeatingTimer(10, check)
        self._health_timer.start()


class DirectConnection(BaseConnection):
    """
    Outbound connection using Paramiko.
    """
    def open(self):
        with self._lock:
            logging.info(f"🔌 Opening direct connection: {self.name}")
            self.state = ConnectionState.OPENING
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
                self._start_health_check()
            except Exception as e:
                logging.error(f"❌ Failed to open direct connection {self.name}: {e}")
                self.state = ConnectionState.BROKEN
                raise


class TunnelConnection(BaseConnection):
    """Connection implementation for reverse tunnel mode.

    Current behavior assumes an already-exposed local tunnel port and probes that
    port until it is reachable, then opens Paramiko against `127.0.0.1:<port>`.
    """

    def run(self):
        import time
        logging.info(f"Starting tunnel connection: {self.name}")
        while True:
            time.sleep(1)
    """
    Reverse connection using a local tunnel port.
    Periodically probes until tunnel becomes active.
    """
    def open(self):
        import socket
        with self._lock:
            logging.info(f"🔄 Waiting for tunnel connection: {self.name}")
            self.state = ConnectionState.OPENING
            self._start_probe_timer()

    def _start_probe_timer(self):
        def probe():
            import socket
            with self._lock:
                if self.state != ConnectionState.OPENING:
                    return
                try:
                    sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                    sock.close()
                    logging.info(f"📡 Tunnel for {self.name} is active. Connecting...")

                    self._ssh = SSHClient()
                    self._ssh.set_missing_host_key_policy(AutoAddPolicy())
                    self._ssh.connect(
                        hostname="127.0.0.1",
                        port=self.port,
                        username=self.user,
                        key_filename=self.id_file
                    )
                    self.state = ConnectionState.OPEN
                    self._start_health_check()
                except Exception:
                    logging.info(f"⏳ Still waiting for tunnel {self.name}...")
                    if self._probe_timer:
                        self._probe_timer.start()

        self._probe_timer: Optional[OneShotRepeatingTimer] = OneShotRepeatingTimer(5, probe)
        self._probe_timer.start()

    def close(self):
        super().close()
        if hasattr(self, "_probe_timer") and self._probe_timer:
            self._probe_timer.cancel()
            self._probe_timer = None


class Connection:
    """
    Connection wrapper used by the pool. Chooses the correct implementation.
    Supports both config object and keyword-based initialization.

    This facade is the stable boundary for callers while direct/tunnel internals
    evolve independently.
    """
    def __init__(self, *args, **kwargs):
        if len(args) == 1 and not kwargs:
            # Assume config-style: Connection(config)
            config = args[0]
        else:
            # Build config from kwargs using existing validated dataclass shape
            config = ConnectionConfig(**kwargs)

        mode = ConnectionMode(config.mode)
        self.impl = DirectConnection(config) if mode == ConnectionMode.DIRECT else TunnelConnection(config)

    def __getattr__(self, name):
        return getattr(self.impl, name)

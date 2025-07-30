import logging
import threading
import time
from enum import Enum
from typing import Optional, List
from paramiko import SSHClient, AutoAddPolicy
from agent.connection_result import CommandResult
from agent.connectionpool.config_loader import ConnectionMode

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
        self._ssh = None
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

    def execute(self, command: str) -> CommandResult:
        from datetime import datetime, timezone
        with self._lock:
            if not self._ssh:
                raise RuntimeError("Connection is not open.")

            started_at = datetime.now(timezone.utc)
            logging.info(f"💻 Executing on {self.name}: {command}")
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
    """
    def __init__(self, *args, **kwargs):
        if len(args) == 1 and not kwargs:
            # Assume config-style: Connection(config)
            config = args[0]
        else:
            # Build config-style object from kwargs
            class Config:
                def __init__(self, name, mode, user, host, port, id_file):
                    self.name = name
                    self.mode = mode
                    self.user = user
                    self.host = host
                    self.port = port
                    self.id_file = id_file

            config = Config(**kwargs)

        mode = ConnectionMode(config.mode)
        self.impl = DirectConnection(config) if mode == ConnectionMode.DIRECT else TunnelConnection(config)

    def __getattr__(self, name):
        return getattr(self.impl, name)

"""Connection pool lifecycle orchestration around the `Connection` facade.

Local boundary notes:
- This module coordinates open/reconnect/close loops and lightweight OS metadata
  refresh for each configured connection.
- Callers should treat `Connection` as the public integration surface; pool logic
  does not expose transport-specific internals.
"""

import logging
import threading
import time
import subprocess
from .connection import Connection
from .connection import ConnectionState

class ConnectionPool:
    def __init__(self, connection_configs, reconnection_delay=5):
        """
        Initialize the connection pool.

        :param connection_configs: List of connection configurations.
        :param reconnection_delay: Delay in seconds between reconnection attempts (default: 5 seconds).

        Current assumption: configs are static for process lifetime.
        """
        self.reconnection_delay = reconnection_delay
        self.connections = []
        self.os_info_cache = {}
        self.lock = threading.Lock()  # For thread-safe access to os_info_cache and connections
        self._monitor_lock = threading.Lock()  # To ensure one monitor loop at a time
        self._stopping = threading.Event()  # To signal stop
        self._timer = None
        self._started = False
        self._disabled_names: set[str] = set()  # Names of connections skipped by the monitor

        for config in connection_configs:
            # Accept both legacy dict configs and validated config objects.
            # Loader paths now produce ConnectionConfig dataclass instances.
            if isinstance(config, dict):
                connection = Connection(**config)
            else:
                connection = Connection(config)
            self.connections.append(connection)

    def gather_os_info(self, connection):
        """Gather OS info for a specific connection."""
        with self.lock:
            try:
                result = subprocess.run(
                    ["scripts/os_info.sh"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True
                )
                if result.stdout:
                    self.os_info_cache[connection.name] = result.stdout.strip()
                else:
                    logging.error(f"❌ No output received for OS info on {connection.name}.")
            except subprocess.CalledProcessError as e:
                logging.error(f"❌ Failed to gather OS info for {connection.name}: {e}", exc_info=True)

    def start(self):
        if self._started:
            logging.warning("⚠️ Connection pool already started.")
            return
        self._started = True
        logging.info("🚀 Starting the connection pool...")

        for connection in self.connections:
            try:
                connection.open()
                self.gather_os_info(connection)
            except Exception as e:
                logging.error(
                    f"❌ Failed to open connection {connection.name} during startup: {e}",
                    exc_info=True,
                )

        self._schedule_monitor()

    def _schedule_monitor(self):
        if not self._stopping.is_set():
            self._timer = threading.Timer(self.reconnection_delay, self._monitor_once)
            self._timer.start()

    def _monitor_once(self):
        with self._monitor_lock:
            if self._stopping.is_set():
                return

            with self.lock:
                connections_snapshot = list(self.connections)
                disabled_snapshot = set(self._disabled_names)

            if not connections_snapshot:
                logging.info("🔍 No connections in the pool.")
            else:
                closed_found = False
                for connection in connections_snapshot:
                    if connection.name in disabled_snapshot:
                        continue  # disabled — do not reconnect
                    if connection.get_state() != ConnectionState.OPEN:
                        closed_found = True
                        logging.warning(f"⚠️ Connection {connection.name} is down. Attempting to reconnect...")
                        try:
                            connection.open()
                            self.gather_os_info(connection)
                        except Exception as e:
                            logging.error(
                                f"❌ Reconnect failed for {connection.name}: {e}",
                                exc_info=True,
                            )

                if closed_found:
                    logging.info("🔁 One or more connections were re-opened.")
                else:
                    logging.info("✅ All connections are currently open.")

        self._schedule_monitor()

    def stop(self):
        if not self._started:
            logging.warning("⚠️ Connection pool not started or already stopped.")
            return

        logging.info("🛑 Stopping the connection pool...")
        self._stopping.set()

        if self._timer:
            self._timer.cancel()
            self._timer = None

        with self._monitor_lock:
            pass  # Wait for any running monitor to complete

        for connection in self.connections:
            connection.close()

        self._started = False

    def query_pool(self):
        with self.lock:
            pool_state = []
            for connection in self.connections:
                state = {
                    "name": connection.name,
                    "is_running": connection.is_running(),
                    "os_info": self.os_info_cache.get(connection.name, "No OS info cached"),
                    "connection_state": connection.get_connection_state()
                }
                pool_state.append(state)
            return pool_state

    def send_command(self, connection_name, command):
        with self.lock:
            for connection in self.connections:
                if connection.name == connection_name:
                    try:
                        return connection.execute_command(command)
                    except Exception as e:
                        logging.error(f"❌ Failed to execute command on {connection_name}: {e}")
                        return None
            logging.warning(f"⚠️ Connection {connection_name} not found.")
            return None

    def expose_pool_state(self):
        return self.query_pool()

    def disable_connection(self, name: str) -> None:
        """Close a connection and mark it so the monitor loop will skip it.

        Thread-safe. If *name* is not found, a warning is logged and no
        exception is raised.
        """
        with self.lock:
            for connection in self.connections:
                if connection.name == name:
                    self._disabled_names.add(name)
                    connection.close()
                    return
        logging.warning(f"⚠️ disable_connection: connection '{name}' not found.")

    def enable_connection(self, name: str) -> None:
        """Clear the disabled mark so the monitor loop manages the connection again.

        Does NOT immediately open the connection. Thread-safe. If *name* is
        not found, a warning is logged and no exception is raised.
        """
        with self.lock:
            for connection in self.connections:
                if connection.name == name:
                    self._disabled_names.discard(name)
                    return
        logging.warning(f"⚠️ enable_connection: connection '{name}' not found.")

    def remove_connection(self, name: str) -> None:
        """Close a connection and remove it from the pool entirely.

        After removal the monitor will never see it again. Thread-safe. If
        *name* is not found, a warning is logged and no exception is raised.
        """
        with self.lock:
            for connection in self.connections:
                if connection.name == name:
                    connection.close()
                    self.connections.remove(connection)
                    self._disabled_names.discard(name)
                    return
        logging.warning(f"⚠️ remove_connection: connection '{name}' not found.")

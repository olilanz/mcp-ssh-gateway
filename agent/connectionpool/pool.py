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
        """
        self.reconnection_delay = reconnection_delay
        self.connections = []
        self.os_info_cache = {}
        self.lock = threading.Lock()  # For thread-safe access to os_info_cache
        self._monitor_lock = threading.Lock()  # To ensure one monitor loop at a time
        self._stopping = threading.Event()  # To signal stop
        self._timer = None
        self._started = False

        class ConfigObject:
            def __init__(self, config):
                self.name = config["name"]
                self.user = config["user"]
                self.id_file = config["id_file"]
                self.mode = config["mode"]
                self.port = config["port"]
                self.host = config["host"]

        for config in connection_configs:
            config_obj = ConfigObject(config)
            connection = Connection(config_obj)
            self.connections.append(connection)

    def gather_os_info(self, connection):
        """Gather OS info for a specific connection."""
        with self.lock:
            try:
                result = subprocess.run(
                    ["scripts/os_info.sh"],
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
            connection.open()
            self.gather_os_info(connection)

        self._schedule_monitor()

    def _schedule_monitor(self):
        if not self._stopping.is_set():
            self._timer = threading.Timer(self.reconnection_delay, self._monitor_once)
            self._timer.start()

    def _monitor_once(self):
        with self._monitor_lock:
            if self._stopping.is_set():
                return

            if not self.connections:
                logging.info("🔍 No connections in the pool.")
            else:
                closed_found = False
                for connection in self.connections:
                    if connection.get_state() != ConnectionState.OPEN:
                        closed_found = True
                        logging.warning(f"⚠️ Connection {connection.name} is down. Attempting to reconnect...")
                        connection.open()
                        self.gather_os_info(connection)

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
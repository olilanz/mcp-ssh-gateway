import logging
import threading
import time
import subprocess
from .connection import Connection
from .connection import ConnectionState

class ConnectionPool:
    def __init__(self, connection_configs, reconnection_delay=5, reconnection_attempts=0):
        """
        Initialize the connection pool.

        :param connection_configs: List of connection configurations.
        :param reconnection_delay: Delay in seconds between reconnection attempts (default: 5 seconds).
        :param reconnection_attempts: Number of reconnection attempts (default: 0 for infinite attempts).
        """
        self.reconnection_delay = reconnection_delay
        self.reconnection_attempts = reconnection_attempts
        self.connections = []
        self.os_info_cache = {}
        self.lock = threading.Lock()  # Ensure thread safety for os_info_cache
        self.connection_configs = connection_configs
        class ConfigObject:
            def __init__(self, config):
                self.name = config["name"]
                self.user = config["user"]
                self.id_file = config["id_file"]
                self.mode = config["mode"]
                self.port = config["port"]
                self.host = config["host"]

        for config in self.connection_configs:
            config_obj = ConfigObject(config)
            connection = Connection(config_obj)
            self.connections.append(connection)

    def gather_os_info(self, connection):
        """Gather OS info for a specific connection."""
        with self.lock:  # Ensure thread-safe access to os_info_cache
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
        logging.info("🚀 Starting the pool...")
        for connection in self.connections:
            connection.open()
            self.gather_os_info(connection)

        # Start a monitoring thread to handle reconnections
        self._monitor_thread = threading.Thread(target=self._monitor_connections, daemon=True)
        self._monitor_thread.start()

    def _monitor_connections(self):
        """Monitor connections and attempt reconnections on failure."""
        attempts = 0
        while self.reconnection_attempts == 0 or attempts < self.reconnection_attempts:
            with self.lock:
                for connection in self.connections:
                    if connection.get_state() != ConnectionState.OPEN:
                        logging.warning(f"⚠️ Connection {connection.name} is down. Attempting to reconnect...")
                        connection.open()
                        self.gather_os_info(connection)
            time.sleep(self.reconnection_delay)  # Retry interval
            attempts += 1

    def stop(self):
        logging.info("🛑 Stopping the pool...")
        for connection in self.connections:
            connection.close()

        # Stop the monitoring thread
        if hasattr(self, "_monitor_thread") and self._monitor_thread:
            logging.info("🛑 Stopping connection monitor thread...")
            self._monitor_thread = None

    def query_pool(self):
        """Query the state of the connection pool."""
        with self.lock:  # Ensure thread-safe access to os_info_cache
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
        """Send a command to a specific connection and retrieve the output."""
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
        """Expose the connection pool state for external querying."""
        return self.query_pool()
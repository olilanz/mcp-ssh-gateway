import logging
import threading
import time
import subprocess
from .connection import Connection

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
        self.runners = []
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
            runner = Connection(config_obj)
            self.runners.append(runner)

    def gather_os_info(self, runner):
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
                    self.os_info_cache[runner.name] = result.stdout.strip()
                else:
                    logging.error(f"❌ No output received for OS info on {runner.name}.")
            except subprocess.CalledProcessError as e:
                logging.error(f"❌ Failed to gather OS info for {runner.name}: {e}", exc_info=True)

    def start_all(self):
        logging.info("🚀 Starting all connections...")
        for runner in self.runners:
            runner.start()
            self.gather_os_info(runner)

        # Start a monitoring thread to handle reconnections
        self._monitor_thread = threading.Thread(target=self._monitor_connections, daemon=True)
        self._monitor_thread.start()

    def _monitor_connections(self):
        """Monitor connections and attempt reconnections on failure."""
        attempts = 0
        while self.reconnection_attempts == 0 or attempts < self.reconnection_attempts:
            with self.lock:
                for runner in self.runners:
                    if not runner.is_running():
                        logging.warning(f"⚠️ Connection {runner.name} is down. Attempting to reconnect...")
                        runner.start()
                        self.gather_os_info(runner)
            time.sleep(self.reconnection_delay)  # Retry interval
            attempts += 1

    def stop_all(self):
        logging.info("🛑 Stopping all connections...")
        for runner in self.runners:
            runner.stop()

        # Stop the monitoring thread
        if hasattr(self, "_monitor_thread") and self._monitor_thread:
            logging.info("🛑 Stopping connection monitor thread...")
            self._monitor_thread = None

    def query_pool(self):
        """Query the state of the connection pool."""
        with self.lock:  # Ensure thread-safe access to os_info_cache
            pool_state = []
            for runner in self.runners:
                state = {
                    "name": runner.name,
                    "is_running": runner.is_running(),
                    "os_info": self.os_info_cache.get(runner.name, "No OS info cached"),
                    "connection_state": runner.get_connection_state()
                }
                pool_state.append(state)
            return pool_state

    def send_command(self, connection_name, command):
        """Send a command to a specific connection and retrieve the output."""
        with self.lock:
            for runner in self.runners:
                if runner.name == connection_name:
                    try:
                        return runner.execute_command(command)
                    except Exception as e:
                        logging.error(f"❌ Failed to execute command on {connection_name}: {e}")
                        return None
            logging.warning(f"⚠️ Connection {connection_name} not found.")
            return None

    def expose_pool_state(self):
        """Expose the connection pool state for external querying."""
        return self.query_pool()
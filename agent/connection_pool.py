import logging
import threading
import time
import subprocess
from connection_runner import ConnectionRunner

class ConnectionPool:
    def __init__(self, connection_configs):
        self.runners = []
        self.os_info_cache = {}
        self.lock = threading.Lock()  # Ensure thread safety for os_info_cache
        for config in connection_configs:
            runner = ConnectionRunner(config)
            self.runners.append(runner)

    def gather_os_info(self, runner):
        """Gather OS info for a specific connection."""
        with self.lock:  # Ensure thread-safe access to os_info_cache
            try:
                result = subprocess.run(
                    ["scripts/os_info.sh"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                self.os_info_cache[runner.name] = result.stdout.strip()
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to gather OS info for {runner.name}: {e}")

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
        while True:
            with self.lock:
                for runner in self.runners:
                    if not runner.is_running():
                        logging.warning(f"⚠️ Connection {runner.name} is down. Attempting to reconnect...")
                        runner.start()
                        self.gather_os_info(runner)
            time.sleep(5)  # Retry interval

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
                    "os_info": self.os_info_cache.get(runner.name, "No OS info cached")
                }
                pool_state.append(state)
            return pool_state

    def expose_pool_state(self):
        """Expose the connection pool state for external querying."""
        return self.query_pool()

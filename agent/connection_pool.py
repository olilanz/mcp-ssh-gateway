import logging
import threading
import time
from connection_runner import ConnectionRunner

class ConnectionPool:
    def __init__(self, connection_configs):
        self.runners = []
        for config in connection_configs:
            runner = ConnectionRunner(config)
            self.runners.append(runner)

    def start_all(self):
        logging.info("🚀 Starting all connections...")
        for runner in self.runners:
            runner.start()

    def stop_all(self):
        logging.info("🛑 Stopping all connections...")
        for runner in self.runners:
            runner.stop()

    def monitor(self, interval=10):
        def _monitor_loop():
            while True:
                for runner in self.runners:
                    status = "✅ running" if runner.is_running() else "❌ not running"
                    logging.info(f"🔍 {runner.name}: {status}")
                time.sleep(interval)

        monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        monitor_thread.start()

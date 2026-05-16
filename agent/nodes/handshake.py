"""
NodeHandshakeService — loads and executes the node handshake script, parses output.

Separation of concerns:
  Connection = SSH transport mechanics (open, execute, SFTP)
  NodeHandshakeService = node semantics (what facts to collect, how to parse them)

The handshake script (resources/node/handshake.sh) is a first-class artifact:
  - POSIX sh, no dependencies
  - Runnable manually: ssh node 'sh -s' < resources/node/handshake.sh
  - Independently testable
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class NodeHandshakeService:
    def __init__(self, resource_root: Optional[Path] = None) -> None:
        """
        Args:
            resource_root: Base path for resolving resources/node/handshake.sh.
                           Defaults to the project root (two levels up from this file).
                           Injectable for tests: pass a Path to a temp directory
                           containing a resources/node/handshake.sh.
        """
        self._resource_root = resource_root or Path(__file__).parent.parent.parent
        self._script_path = self._resource_root / "resources" / "node" / "handshake.sh"

    def run(self, connection, timeout: int = 10) -> dict:
        """
        Load handshake.sh, execute it on the node via sh, parse key=value output.

        Args:
            connection: An open Connection/BaseConnection instance with execute().
            timeout:    Max seconds to wait for the handshake script. Default 10.

        Returns:
            dict of {fact_name: {"value": str, "source": "handshake", "collected_at": str}}
            Returns {} on any failure — never raises, logs warnings instead.
        """
        try:
            script = self._script_path.read_text()
        except FileNotFoundError:
            logging.warning(f"Handshake script not found: {self._script_path}")
            return {}
        except OSError as e:
            logging.warning(f"Failed to read handshake script {self._script_path}: {e}")
            return {}

        try:
            result = connection.execute(f"sh -s <<'EOF'\n{script}\nEOF", timeout=timeout)
            stdout = result.stdout
        except Exception as e:
            logging.warning(f"Handshake execution failed: {e}")
            return {}

        return self._parse_output(stdout)

    def _parse_output(self, stdout: str) -> dict:
        """
        Parse key=value output from handshake.sh into a facts dict.

        Splits on the FIRST '=' only — values may contain '=' characters.
        Skips lines that do not contain '='.

        Args:
            stdout: Raw stdout from the handshake script execution.

        Returns:
            dict of {key: {"value": str, "source": "handshake", "collected_at": str}}
            The collected_at field for each fact entry uses the value of the
            "collected_at" key from the parsed output (or empty string if absent).
        """
        raw: dict[str, str] = {}
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if "=" not in line:
                logging.debug(f"Handshake: skipping non-key=value line: {line!r}")
                continue
            key, _, value = line.partition("=")
            raw[key.strip()] = value  # do NOT strip value — preserve spacing

        collected_at = raw.get("collected_at", "")

        facts = {}
        for key, value in raw.items():
            facts[key] = {
                "value": value,
                "source": "handshake",
                "collected_at": collected_at,
            }

        return facts

from dataclasses import dataclass
from datetime import datetime

@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    started_at: datetime
    ended_at: datetime

    def to_dict(self):
        """Convert CommandResult to a dictionary."""
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
        }

    def duration(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()

    def succeeded(self) -> bool:
        return self.exit_code == 0
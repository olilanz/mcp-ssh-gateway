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

    def duration(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()

    def succeeded(self) -> bool:
        return self.exit_code == 0
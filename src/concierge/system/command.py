"""Command models for system execution."""

import shlex
from dataclasses import dataclass, field
from shutil import which


@dataclass
class Command:
    """Represents a command to be executed by Concierge.

    Attributes:
        executable: The command to execute
        args: Arguments to pass to the executable
        user: Optional user to run the command as (via sudo)
        group: Optional group to run the command as (via sudo)
    """

    executable: str
    args: list[str] = field(default_factory=list)
    user: str = ""
    group: str = ""

    @property
    def full_command(self) -> list[str]:
        """Build the full command including sudo if needed.

        Returns:
            List of command components
        """
        # Resolve executable path (similar to Go's exec.LookPath).
        executable_path = which(self.executable)
        if executable_path is None:
            executable_path = self.executable

        cmd: list[str] = []

        # Add sudo prefix if user or group is specified
        if (self.user or self.group) and self.user != "root":
            cmd.append("sudo")

            if self.user:
                cmd.extend(["-u", self.user])

            if self.group:
                cmd.extend(["-g", self.group])

        cmd.append(executable_path)
        cmd.extend(self.args)

        return cmd

    @property
    def command_string(self) -> str:
        """Build the command as a properly escaped shell string.

        Returns:
            Shell-escaped command string
        """
        return shlex.join(self.full_command)


class CommandError(Exception):
    """Raised when a command execution fails.

    Attributes:
        command: The command that failed
        returncode: Exit code from the command
        output: Combined stdout/stderr output
    """

    def __init__(self, command: str, returncode: int, output: str) -> None:
        """Initialize CommandError.

        Args:
            command: The command that failed
            returncode: Exit code from the command
            output: Combined stdout/stderr output
        """
        self.command = command
        self.returncode = returncode
        self.output = output
        super().__init__(f"Command failed with exit code {returncode}: {command}")

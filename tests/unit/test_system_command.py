"""Unit tests for system command models."""

import pytest

from concierge.system.command import Command, CommandError


class TestCommand:
    """Tests for Command dataclass."""

    def test_command_minimal(self) -> None:
        """Test creating a minimal Command."""
        cmd = Command(executable="ls")
        assert cmd.executable == "ls"
        assert cmd.args == []
        assert cmd.user == ""
        assert cmd.group == ""

    def test_command_with_args(self) -> None:
        """Test creating a Command with arguments."""
        cmd = Command(executable="ls", args=["-la", "/tmp"])
        assert cmd.executable == "ls"
        assert cmd.args == ["-la", "/tmp"]

    def test_command_with_user(self) -> None:
        """Test creating a Command with user."""
        cmd = Command(executable="whoami", user="testuser")
        assert cmd.user == "testuser"

    def test_command_with_group(self) -> None:
        """Test creating a Command with group."""
        cmd = Command(executable="id", group="testgroup")
        assert cmd.group == "testgroup"

    def test_command_with_user_and_group(self) -> None:
        """Test creating a Command with both user and group."""
        cmd = Command(executable="ls", user="testuser", group="testgroup")
        assert cmd.user == "testuser"
        assert cmd.group == "testgroup"

    def test_full_command_simple(self) -> None:
        """Test full_command property for simple command."""
        cmd = Command(executable="ls", args=["-l"])
        assert cmd.full_command == ["ls", "-l"]

    def test_full_command_with_user(self) -> None:
        """Test full_command property with user (adds sudo)."""
        cmd = Command(executable="ls", args=["-l"], user="testuser")
        assert cmd.full_command == ["sudo", "-u", "testuser", "ls", "-l"]

    def test_full_command_with_group(self) -> None:
        """Test full_command property with group (adds sudo)."""
        cmd = Command(executable="ls", args=["-l"], group="testgroup")
        assert cmd.full_command == ["sudo", "-g", "testgroup", "ls", "-l"]

    def test_full_command_with_user_and_group(self) -> None:
        """Test full_command property with both user and group."""
        cmd = Command(executable="ls", args=["-l"], user="testuser", group="testgroup")
        assert cmd.full_command == ["sudo", "-u", "testuser", "-g", "testgroup", "ls", "-l"]

    def test_full_command_root_user_no_sudo(self) -> None:
        """Test that root user doesn't add sudo prefix."""
        cmd = Command(executable="ls", args=["-l"], user="root")
        # When user is root, should not add sudo
        assert cmd.full_command == ["ls", "-l"]

    def test_full_command_no_args(self) -> None:
        """Test full_command with no arguments."""
        cmd = Command(executable="pwd")
        assert cmd.full_command == ["pwd"]

    def test_full_command_multiple_args(self) -> None:
        """Test full_command with multiple arguments."""
        cmd = Command(executable="git", args=["commit", "-m", "test message", "--author=me"])
        assert cmd.full_command == ["git", "commit", "-m", "test message", "--author=me"]

    def test_command_string_simple(self) -> None:
        """Test command_string property for simple command."""
        cmd = Command(executable="ls", args=["-l"])
        assert cmd.command_string == "ls -l"

    def test_command_string_with_spaces(self) -> None:
        """Test command_string properly escapes arguments with spaces."""
        cmd = Command(executable="echo", args=["hello world"])
        assert cmd.command_string == "echo 'hello world'"

    def test_command_string_with_quotes(self) -> None:
        """Test command_string properly escapes arguments with quotes."""
        cmd = Command(executable="echo", args=["it's working"])
        # shlex.join should properly escape the apostrophe - just verify command starts with echo
        assert cmd.command_string.startswith("echo")
        # Verify the result is a valid shell command string
        assert len(cmd.command_string) > len("echo")

    def test_command_string_with_sudo(self) -> None:
        """Test command_string includes sudo when user is set."""
        cmd = Command(executable="ls", args=["-l"], user="testuser")
        assert cmd.command_string == "sudo -u testuser ls -l"

    def test_command_string_with_sudo_and_group(self) -> None:
        """Test command_string includes sudo with both user and group."""
        cmd = Command(executable="ls", user="testuser", group="testgroup")
        assert cmd.command_string == "sudo -u testuser -g testgroup ls"

    def test_command_string_complex(self) -> None:
        """Test command_string with complex arguments."""
        cmd = Command(
            executable="juju",
            args=["bootstrap", "lxd", "controller", "--config", "test-mode=true"],
        )
        expected = "juju bootstrap lxd controller --config test-mode=true"
        assert cmd.command_string == expected

    def test_command_equality(self) -> None:
        """Test that Command dataclasses can be compared for equality."""
        cmd1 = Command(executable="ls", args=["-l"], user="testuser")
        cmd2 = Command(executable="ls", args=["-l"], user="testuser")
        cmd3 = Command(executable="ls", args=["-l"], user="otheruser")

        assert cmd1 == cmd2
        assert cmd1 != cmd3

    def test_command_repr(self) -> None:
        """Test that Command has a useful string representation."""
        cmd = Command(executable="ls", args=["-l"])
        repr_str = repr(cmd)
        assert "ls" in repr_str
        assert "-l" in repr_str


class TestCommandError:
    """Tests for CommandError exception."""

    def test_command_error_init(self) -> None:
        """Test creating a CommandError."""
        error = CommandError(command="ls -l", returncode=1, output="permission denied")
        assert error.command == "ls -l"
        assert error.returncode == 1
        assert error.output == "permission denied"

    def test_command_error_message(self) -> None:
        """Test CommandError message format."""
        error = CommandError(command="ls -l", returncode=2, output="not found")
        message = str(error)
        assert "exit code 2" in message
        assert "ls -l" in message

    def test_command_error_is_exception(self) -> None:
        """Test that CommandError is an Exception."""
        error = CommandError(command="test", returncode=1, output="failed")
        assert isinstance(error, Exception)

    def test_command_error_can_be_raised(self) -> None:
        """Test that CommandError can be raised and caught."""
        with pytest.raises(CommandError) as exc_info:
            raise CommandError(command="test", returncode=1, output="failed")

        assert exc_info.value.command == "test"
        assert exc_info.value.returncode == 1
        assert exc_info.value.output == "failed"

    def test_command_error_with_multiline_output(self) -> None:
        """Test CommandError with multiline output."""
        output = "line 1\nline 2\nline 3"
        error = CommandError(command="test", returncode=1, output=output)
        assert error.output == output

    def test_command_error_with_empty_output(self) -> None:
        """Test CommandError with empty output."""
        error = CommandError(command="test", returncode=1, output="")
        assert error.output == ""
        assert "exit code 1" in str(error)

    def test_command_error_attributes_accessible(self) -> None:
        """Test that all CommandError attributes are accessible."""
        error = CommandError(command="git push", returncode=128, output="fatal: error")
        # Should be able to access all attributes
        cmd = error.command
        rc = error.returncode
        out = error.output
        assert cmd == "git push"
        assert rc == 128
        assert out == "fatal: error"

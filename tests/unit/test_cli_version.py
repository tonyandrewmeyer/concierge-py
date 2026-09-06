"""Tests that `concierge --version` and `concierge version` produce identical output."""

import pytest

from concierge.cli import app


def test_version_flag_and_subcommand_match_and_go_to_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        app.main(["--version"])
    assert exc_info.value.code == 0
    flag_out = capsys.readouterr()

    app.main(["version"])
    subcommand_out = capsys.readouterr()

    assert flag_out.out == subcommand_out.out
    assert flag_out.out.strip() != ""
    assert flag_out.err == ""
    assert subcommand_out.err == ""


def test_version_string_reports_the_installed_package_version() -> None:
    assert app._version_string() == f"concierge version {app._package_version()}"

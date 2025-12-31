# Concierge Development Guide

## Project Overview

Python implementation of Concierge - automates setup of Juju charm development environments.
Installs LXD, K8s (MicroK8s or Canonical K8s), Juju, and development tools.

## Architecture

- **CLI**: Typer-based command interface (src/concierge/cli/)
- **Core**: Manager + Plan orchestration with asyncio (src/concierge/core/)
- **Providers**: LXD, MicroK8s, K8s, Google Cloud implementations (src/concierge/providers/)
- **Packages**: Snap and Deb handlers with aiohttp/snapd API (src/concierge/packages/)
- **Juju**: Bootstrap and credential management (src/concierge/juju/)
- **System**: Low-level command execution and workers (src/concierge/system/)

## Tech Stack

- **Python 3.14+** with strict typing (ty)
- **asyncio** for concurrency (replaces Go goroutines)
- **Typer** for CLI with rich output
- **Pydantic** for configuration validation
- **structlog** for structured logging
- **aiohttp** for snapd HTTP API communication
- **tenacity** for retry logic
- **uv** for package management

## Development Workflow

1. Use `uv` for all package operations (not pip directly)
2. Run `uv venv` to create virtual environment
3. Run `uv pip install -e ".[dev]"` to install with dev dependencies
4. All code must pass: ruff format, ruff check, ty, pytest

## Code Style

- **Line length**: 100 characters
- **Type hints**: Required on all functions (ty strict mode enabled)
- **Linting**: Use ruff for both linting and formatting
- **Async patterns**: Follow asyncio best practices (no blocking I/O in async functions)
- **Logging**: Use structlog with structured context
- **Error handling**: Use tenacity for retries, explicit error messages
- **Comments**: Use full sentences (ending with punctuation) and use comments to explain *why* changes are made, *not* what is being done - usually comments are not needed because the code should be understandable without them

## Testing

- **Framework**: pytest with pytest-asyncio
- **Async mode**: Auto (configured in pyproject.toml)
- **Structure**:
  - Unit tests: `tests/unit/`
  - Integration tests: `tests/integration/`
  - Mocks: `tests/mocks/`
- **Coverage**: Use pytest-cov, aim for high coverage on core logic
- **Run tests**: `uv run pytest tests/unit/ -v --cov=src/concierge --cov-report=term-missing`

## Configuration Presets

The tool supports several presets (defined in src/concierge/config/presets.py):

- **dev**: LXD + K8s + all development tools (recommended for most users)
- **machine**: LXD + snapcraft (for machine charm development)
- **k8s**: Canonical Kubernetes + rockcraft (for K8s charm development)
- **microk8s**: MicroK8s + rockcraft (alternative K8s setup)
- **crafts**: LXD + all craft tools, no Juju (for building artifacts only)

## Common Commands

### Development
- `uv run pytest` - Run all tests
- `uv run pytest tests/unit/` - Run unit tests only
- `uv run ty src/` - Type check the codebase
- `uv run ruff check src/` - Lint the code
- `uv run ruff format src/` - Format the code

### Testing the Tool
- `concierge prepare --preset dev` - Set up dev environment
- `concierge status` - Check environment status
- `concierge restore` - Remove Concierge changes

### CI Pipeline (matches GitHub Actions)
1. Format check: `uv run ruff format --check src/ tests/`
2. Lint: `uv run ruff check src/ tests/`
3. Type check: `uv run ty src/`
4. Tests: `uv run pytest tests/unit/ -v --cov=src/concierge --cov-report=term-missing`

## Important Notes

- This is a system-level tool that modifies the host system (installs snaps, configures LXD/K8s)
- Always test in a VM or container, not on your main development machine
- The tool maintains state and can restore the system to pre-Concierge state
- Requires Ubuntu/Debian-based system with snapd
- Uses sudo for privileged operations

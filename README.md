# Concierge (Python)

Python implementation of [Concierge](https://github.com/canonical/concierge), a tool to provision and manage charm development environments.

## Overview

Concierge automates the setup of development environments for Juju charm development, installing and configuring:

- LXD for machine charms
- MicroK8s or Canonical Kubernetes for Kubernetes charms
- Juju with automatic bootstrap
- Development tools (charmcraft, snapcraft, rockcraft, etc.)

This Python implementation maintains full feature parity with the original Go version while leveraging modern Python async/await patterns.

## Requirements

- Python 3.14+
- Ubuntu/Debian-based system
- `uv` package manager

## Installation

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
uv pip install -e .
```

## Usage

```bash
# Prepare environment with dev preset (LXD + K8s)
concierge prepare --preset dev

# Prepare with custom configuration
concierge prepare --config concierge.yaml

# Override snap channels
concierge prepare --preset dev --juju-channel 4.0/stable

# Restore environment to pre-Concierge state
concierge restore

# Check status
concierge status
```

## Configuration Presets

- **dev**: LXD + K8s + all development tools (recommended for most users)
- **machine**: LXD + snapcraft (for machine charm development)
- **k8s**: Canonical Kubernetes + rockcraft (for K8s charm development)
- **microk8s**: MicroK8s + rockcraft (alternative K8s setup)
- **crafts**: LXD + all craft tools, no Juju (for building artifacts only)

## Architecture

The Python implementation uses:

- **asyncio** for concurrent operations (replacing Go's goroutines)
- **Pydantic** for configuration validation
- **Typer** for CLI
- **structlog** for structured logging
- **aiohttp** for snapd HTTP API communication
- **tenacity** for retry logic

## Project Structure

```
src/concierge/
├── cli/           # Typer CLI application
├── config/        # Configuration models and presets
├── core/          # Core orchestration (Manager, Plan)
├── juju/          # Juju handler and credentials
├── packages/      # Snap and Deb package handlers
├── providers/     # Cloud provider implementations (LXD, K8s, etc.)
└── system/        # Low-level system operations
```

## Development

```bash
# Run tests
uv run pytest

# Type checking
uv run mypy src/

# Linting
uv run ruff check src/
```

## License

Apache 2.0 - See LICENSE file

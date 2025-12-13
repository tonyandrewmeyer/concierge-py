Run ruff linting and formatting checks.

Check formatting:
```bash
uv run ruff format --check src/ tests/
```

Run linter:
```bash
uv run ruff check src/ tests/
```

Fix issues automatically:
```bash
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
```

Check a specific file:
```bash
uv run ruff check src/concierge/cli/app.py
```

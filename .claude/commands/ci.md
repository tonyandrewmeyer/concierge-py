Run the full CI suite locally (matches GitHub Actions).

Run all checks in sequence:

1. Format check:
```bash
uv run ruff format --check src/ tests/
```

2. Lint:
```bash
uv run ruff check src/ tests/
```

3. Type check:
```bash
uv run ty src/
```

4. Tests:
```bash
uv run pytest tests/unit/ -v --cov=src/concierge --cov-report=term-missing
```

Or run all at once:
```bash
uv run ruff format --check src/ tests/ && \
uv run ruff check src/ tests/ && \
uv run ty src/ && \
uv run pytest tests/unit/ -v --cov=src/concierge --cov-report=term-missing
```

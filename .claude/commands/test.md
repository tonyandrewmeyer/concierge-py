Run the pytest test suite with coverage reporting.

Run unit tests:
```bash
uv run pytest tests/unit/ -v --cov=src/concierge --cov-report=term-missing
```

Run all tests:
```bash
uv run pytest -v --cov=src/concierge --cov-report=term-missing
```

Run tests for a specific file:
```bash
uv run pytest tests/unit/test_specific.py -v
```

Run with more detailed output:
```bash
uv run pytest -vv --cov=src/concierge --cov-report=term-missing --cov-report=html
```

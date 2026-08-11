# Development

## Method

Build incrementally. Each phase must update docs, tests, and CI behavior.

Do not implement the platform as a generic chatbot or a single monolithic Python application.

## Quality Gates

Run after meaningful changes:

```bash
python -m ruff check .
python -m mypy packages apps
python -m pytest
npm --prefix apps/frontend test
docker compose -f infra/docker/docker-compose.dev.yml config
```

If a command fails, record it and fix it before claiming that phase is complete.

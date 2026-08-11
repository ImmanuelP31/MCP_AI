# Alembic

Alembic is the production database initialization and migration mechanism for the API service.

The phase-0 SQL baseline lives at `infra/postgres/migrations/001_initial_schema.sql` so reviewers can inspect the complete data model before ORM models are introduced. A later phase will add SQLAlchemy models and generate Alembic revisions from that model metadata.

Do not use `create_all()` for production initialization.


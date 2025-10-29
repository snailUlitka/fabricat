# Backend Agent Guide

This directory hosts the Python application for the Fabricat API and core game simulation. Follow the conventions below when editing anything under `backend/`.

## Package layout
- `src/fabricat_backend/main.py` — CLI-friendly entrypoint. Extend the `run()` function to launch the ASGI server (FastAPI + Uvicorn) as the project matures.
- `src/fabricat_backend/api/` — HTTP layer. Place FastAPI routers in `routers/` and Pydantic request/response schemas in `models/`.
- `src/fabricat_backend/game_logic/` — Deterministic game engine modules. Keep game rules decoupled from transport concerns.
- `src/fabricat_backend/database/` — Database access layer (ORM models, migrations, repositories). Nothing is implemented yet; add subpackages when the persistence story is ready.
- `src/fabricat_backend/shared/` — Cross-cutting utilities (enums, value objects, configuration helpers) that can be reused by API and game logic modules.

Maintain a clear dependency direction: `shared` → `game_logic` → `api`. Avoid importing `api` code from lower layers.

## Environment and tooling
- Manage dependencies with **uv**. After editing `pyproject.toml`, regenerate the lockfile via `uv lock` (or `uv sync` if you want to install immediately).
- Target **Python 3.12**. Avoid using deprecated stdlib modules; favor `typing` features (e.g., `typing.Self`, `enum.StrEnum`).
- Lint code with `uv run ruff check`.
- Format code with `uv run ruff format`. Until a formatter is added, ensure files stay compliant with PEP 8 and use black-compatible formatting.

## Running the service
- Local smoke test: `uv run api` launches the development server via `fabricat_backend.main` with auto-reload enabled.
- To emulate production locally, run `python -m fabricat_backend` from this directory; it uses the same ASGI app without reload mode.
- Configure environment variables using `.env` files (e.g., `cp .env.example .env`). Keep secrets out of source control.

## Testing
- Use `pytest` for unit/integration tests. Store tests under `tests/` at the project root (`backend/tests/`), mirroring the `src/` layout.
- Keep test fixtures deterministic—game logic must be reproducible for all players.
- When you add tests, document the canonical command (e.g., `uv run pytest`) in the repository-level `AGENTS.md`.

## Important Rules
- **IMPORTANT**: If `.env` is missing, create it BEFORE tests (e.g., `cp .env.example .env`) and populate it following the example values in `.env.example`.
- **ALWAYS** use `uv run pytest` before commit and fix all isses
- **ALWAYS** use `uv run ruff check` before commit and fix all issues
- **ALWAYS** use `uv run ruff format` before commit

## Adding dependencies
1. Declare them in `pyproject.toml` inside the `[project.dependencies]` table.
2. Run `uv lock --upgrade-package <package>` to update `uv.lock` deterministically.
3. Include any necessary initialization (e.g., database migrations) and describe them in your PR summary.

## Coding conventions
- Favor dataclasses or Pydantic models for rich domain objects; avoid loose dictionaries.
- Put constants in `shared/constants.py` (create the module if needed) rather than scattering magic numbers.
- Keep modules small and focused. If a file grows beyond ~300 lines, consider splitting it.
- All public functions and classes should have docstrings explaining their responsibilities and invariants.
- SQLAlchemy declarative models ("schemas" in the database layer) must have class names matching the regex `\w+Schema`.
- Pydantic models that represent API payloads must have class names matching `\w+Request` or `\w+Response`.
- Always use absolute imports rooted at `fabricat_backend`; avoid relative imports such as `from .module import ...`.

By following these rules you help downstream agents (and humans) keep the backend coherent and maintainable.

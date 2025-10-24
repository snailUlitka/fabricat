# Fabricat Repository — Agent Handbook

Welcome! This monorepo contains everything needed to build the Fabricat economic strategy game. Follow the instructions below before making changes.

## Directory map
- `backend/` — Python application that will expose the public API and game simulation logic. Code lives in the `src/fabricat_backend/` package.
- `frontend/` — Next.js client application served separately from the API. UI code follows the App Router conventions under `src/app`.
- `docker/` — Dockerfiles and compose scaffolding for containerized development (currently placeholders that you can extend).
- `configs/` — Reserved for future shared configuration; empty at the moment.
- `scripts/` — Helper automation scripts; add developer tooling here when needed.

Always check for nested `AGENTS.md` files (e.g., inside `backend/` and `frontend/`) and obey their more specific instructions for files you modify.

## Toolchain prerequisites
- **Python 3.12** with the [uv](https://docs.astral.sh/uv/) package manager. Install uv once (`curl -LsSf https://astral.sh/uv/install.sh | sh`) and make sure it is on your PATH.
- **Node.js ≥ 20.0** (Next.js 15 works best on Node 20 LTS or newer) with npm.
- **Docker** is optional but recommended if you want to iterate inside containers. The provided Dockerfiles are empty scaffolds that you can flesh out.

## Repository initialization
1. Clone the repository and create a new Git branch for your work.
2. Back-end setup:
   - `cd backend`
   - `uv sync` (creates `.venv` and installs the locked dependencies).
   - Prefer running tools via `uv run <command>` instead of activating the virtual environment manually so every invocation stays reproducible.
3. Front-end setup:
   - `cd frontend`
   - `npm install` (or `npm ci` in CI) to reproduce the `package-lock.json`.
4. When touching both applications, run them in parallel (e.g., API on port 8000, Next.js dev server on 3000) to verify cross-integration.

## Development workflow guidelines
- Keep Python code type-annotated and PEP 8 compliant. Prefer standard library modules over ad hoc utilities when possible.
- Maintain separation between shared domain logic (under `backend/src/fabricat_backend/shared/`) and transport-specific code (FastAPI routers will live under `api/routers`).
- For React/Next.js code, colocate UI components near their routes inside `src/app`, and store shared utilities under `src/lib` or `src/components` as you introduce them.
- Document new commands or conventions inside the most relevant `AGENTS.md` so future agents stay aligned.
- If you add new external dependencies, add them with `uv add <package>` (or `uv add --dev` for tooling), regenerate locks via `uv lock`, update `package-lock.json` with `npm install`, and mention them in your PR description.

## Testing and quality checks
- **Back-end**: once tests are introduced, run them with `uv run pytest`. For now, smoke-test changes via `uv run python -m fabricat_backend` (which currently prints a placeholder message).
- **Front-end**: run `npm run lint` to validate ESLint rules, and `npm run build` to ensure the production bundle succeeds.
- Add automated checks when you introduce new tooling (e.g., ruff, mypy, vitest) and document the expected commands here.

## Commit & PR etiquette
- Keep commits focused and descriptive. If your work spans both back-end and front-end, separate the changes by concern when possible.
- Summarize noteworthy architectural decisions in your PR body. Mention if manual steps (schema migrations, environment variables) are required so reviewers can reproduce your results.
- Keep every `AGENTS.md` in the repository up to date whenever you introduce new tooling or conventions so future agents inherit accurate guidance.

## Task planning and execution norms
- Break large assignments into smaller actionable steps before coding. Capture the resulting checklist in `PLAN.md` at the repository root. If `PLAN.md` already exists, continue executing and updating the existing plan instead of starting a new one.
- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages (e.g., `feat: add trading simulation loop`, `fix: correct asset allocation`).
- Always run the relevant linters, formatters, and tests before committing.

Happy building, and thank you for keeping these guidelines current!

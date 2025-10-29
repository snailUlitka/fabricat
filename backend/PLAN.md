# Game Logic Implementation Plan

## Milestone 1 — Requirements & Design Alignment
- [x] Identify core domain entities (player, inventory, factories, loans, market) and sketch their responsibilities/interfaces. (Documented in `docs/domain_overview.md`.)
- [x] Define data flow for a single month: how state enters each phase, what side effects it produces, and what must be persisted/logged. (See `docs/domain_overview.md`.)

## Milestone 2 — Domain Foundations
- [x] Create configuration module for default economic parameters and lobby overrides (default should stores in .env and processes via pydantic settings).
- [x] Implement immutable value objects for money, resources, seniority order, and phase identifiers.
- [x] Model player/company state containers that track cash, inventory, factories (active, under construction, upgrading), and loans.
- [x] Introduce deterministic RNG service with optional seeding for seniority rolls.

## Milestone 3 — Phase Engine Skeleton
- [x] Implement a `MonthEngine` (or similar orchestrator) that enforces the fixed phase order and produces phase results.
- [x] Define per-phase handler interfaces (expenses, market setup, buy RMs, production, sell FGs, loans, construction, end-of-month) with explicit inputs/outputs.
- [x] Add shared result/event structures for logging actions and decisions.

## Milestone 4 — Phase Implementations
- [x] Build expense deduction logic, including bankruptcy checks when funds are insufficient.
- [x] Implement market announcement logic, generating volume/price corridors and exposing read-only views to players.
- [x] Implement RM purchasing resolution with hidden bids, reveal, priority sorting, and seniority tie-breaks.
- [x] Implement production processing respecting factory capacities, launch costs, and resource availability.
- [x] Implement FG selling resolution with ceiling pricing and seniority tie-breaks.
- [x] Implement loan management: interest accrual, scheduled repayments, debt limit enforcement, loan issuance validation.
- [x] Implement construction/upgrade timeline updates, payment scheduling, and factory state transitions.
- [x] Implement end-of-month wrap-up: bankruptcy elimination, seniority rotation, and capital recomputation.

## Milestone 5 — Persistence & Integration Hooks
- [ ] Define interfaces for persisting game state snapshots and logs (placeholder adapters until database layer exists).
- [ ] Expose orchestration entry points that the API layer can call (start session, process phase submissions, advance month).
- [ ] Document orchestration contracts in module docstrings for future API integration.

## Milestone 6 — Validation & Tooling
- [ ] Add focused unit tests for each phase and tie-break scenario using deterministic fixtures.
- [ ] Add integration-style tests simulating a full month with multiple players and varied bids.
- [ ] Ensure `uv run ruff format`, `uv run ruff check`, and `uv run pytest` pass locally.
- [ ] Update relevant `AGENTS.md` files with new commands/conventions if tooling or workflows change.

## Milestone 7 — Future Enhancements (Backlog)
- [ ] Extend plan to cover AI/bot players and analytics once core engine is stable.
- [ ] Integrate RNG seeding with session configuration exposed via API.
- [ ] Introduce persistence adapters (database, event log) once storage layer is designed.

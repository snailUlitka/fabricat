# Fabricat UI Plan

1. **Assess current frontend baseline** — inspect the existing Next.js scaffold, check AGENTS, and document UX requirements (auth, registration, gameplay interactions).
2. **Define UI architecture** — outline route/component structure (auth flows, lobby, gameplay area), decide on state management approach, and sketch mocked API helpers.
3. **Implement shared layout & auth flows** — update global layout styling, build reusable form components, and create login/registration screens backed by client-side validation.
4. **Build gameplay interaction pages** — implement the main game dashboard (resource overview, actions such as trade/build/explore) with mocked data mutations and feedback.
5. **Wire state + persistence & document usage** — add lightweight client store (context/local storage), hook flows together, and document how to run/test the UI (README or inline notes).

## API integration follow-up
6. **Map backend contracts** — read FastAPI routers/models to capture real request/response shapes for `/auth` and `ws://.../ws/game`.
7. **Replace mock lib with real client** — implement `apiClient` helpers for HTTP auth + WebSocket session handling, persist tokens securely, and remove local fake state.
8. **Rebuild UI to follow actual phases** — refactor components to show month/phase analytics, enforce allowed phase actions (buy/production/sell/loans/construction), and surface server journals/logs.
9. **Document runtime + testing** — update AGENTS/docs with the new workflow (needs backend on `localhost:8000`), and re-run lint/tests.

## Architecture Outline
- Single App Router page delegates to a client-side `HomePage` component that decides between auth vs. game dashboard views.
- Auth flows live inside `src/components/auth/AuthPanel.jsx` with toggled login/registration forms and inline validation.
- Game UI splits into `GameDashboard` (summary, resources, structures) and action panels (gather, trade, build, explore) that call a mocked API helper.
- State + persistence handled through `src/lib/gameApi.js` (localStorage-backed mock endpoints) and `src/lib/storage.js` helpers so we can later swap to a real backend.

## Backend E2E Session Test

1. **Study backend session runtime** — inspect `backend/src/fabricat_backend/api/routers/session.py` and the `GameSession` engine to understand how WebSocket phases advance and how actions mutate player state.
2. **Design deterministic settings** — patch `_default_game_settings` in tests to shrink build/upgrade timelines, fix market ranges, and keep expenses manageable so the full cycle completes within two months.
3. **Share runtime for two clients** — monkeypatch `GameSession`/`SessionRuntime` helpers so both authenticated sockets join the same session, wait for both connections before starting, and allow the test to release each phase after sending actions.
4. **Implement end-to-end test** — register two users, connect both via `TestClient.websocket_connect`, and drive every phase by sending real `phase_action` messages, draining tick/report payloads, and asserting that journal entries cover expenses, market, buy, production, sell, loans, construction, and end-of-month rotation.
5. **Validate mechanics in assertions** — check that buy tie-breaks follow seniority, production consumes RM → FG, sales transfer cash, loan interest/principal plus new issuance occur, construction payments/completions fire, and final analytics reflect updated assets.

### Session Scenario

**Month 1**

- *Expenses*: both players (P1 senior, P2 junior) start with cash, 1 RM, 1 FG, and two basic factories; maintenance charges should be deducted for factories and inventory.
- *Market*: bank announces a fixed market (RM supply 3 @ $200 min, FG demand 3 @ $500 max).
- *Buy phase*:
  - **P1** submits a buy bid for 2 RM at $250.
  - **P2** submits an identical bid; with limited supply, seniority resolves the tie so P1 gets 2 units and P2 gets the remaining 1.
- *Production*:
  - **P1** launches basic production for 2 units, paying launch costs and converting RM → FG.
  - **P2** produces 1 unit with a basic factory.
- *Sell phase*:
  - **P1** sells 2 FG at $480 within the ceiling.
  - **P2** sells 1 FG at the same price.
- *Loans*:
  - **P1** services an existing loan (interest + principal auto-deducted).
  - **P2** calls the first loan slot to receive new funds.
- *Construction*:
  - **P1** starts building a new basic factory (pays 50% upfront, schedules the remainder for Month 2).
  - **P2** upgrades one basic factory toward automation (upgrade completes next month).
- *End of month*: priorities rotate so P2 becomes senior for Month 2; bankruptcy check should pass for both.

**Month 2**

- *Expenses*: deduct upkeep again, including the in-progress build/upgrade entries.
- *Market*: announce the same deterministic market for reproducibility.
- *Buy phase*:
  - **P1** buys 1 RM at $250.
  - **P2** buys 2 RM at the same price; with rotated seniority, P2 now wins tie-break priority.
- *Production*:
  - **P1** produces 1 unit with basics.
  - **P2** produces 1 unit (still basic while upgrade finalizes at construction).
- *Sell phase*:
  - **P1** sells 1 FG at $480.
  - **P2** sells 2 FG at $480.
- *Loans*:
  - **P2** pays interest on the newly issued loan (auto) and keeps other slots idle.
- *Construction*:
  - **P1** completes the basic factory build by paying the remaining 50% and receiving the finished factory.
  - **P2** finishes the upgrade, converting the target factory to automated status.
- *End of month*: Month 2 close triggers victory determination (max months reached); verify final capital analytics and seniority history reflect two completed months.

6. **Tooling + quality** — run `uv run ruff format`, `uv run ruff check`, and `uv run pytest` to ensure style and test suite remain green before committing.

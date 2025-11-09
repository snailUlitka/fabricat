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

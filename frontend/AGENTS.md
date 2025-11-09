# Frontend Agent Guide

This folder contains the Fabricat web client built with Next.js 15 (App Router) and React 19. Use these conventions for any work under `frontend/`.

## Project structure
- `src/app/` — App Router entry point. Routes are file-based; each folder can define `page.js`, `layout.js`, loading states, and route-specific components.
- `public/` — Static assets served at the site root. Place logos, icons, and other non-compiled files here.
- `eslint.config.mjs` & `jsconfig.json` — Central linting and path-alias configuration. Update them when you introduce custom rules or module aliases.

Organize shared UI primitives under `src/components/`, reusable hooks under `src/hooks/`, and data-fetching utilities under `src/lib/` as the app grows.

## Environment setup
1. Ensure Node.js **20 LTS or newer** is installed (Next.js 15 requires Node ≥ 18.18; we standardize on 20+).
2. Install dependencies with `npm install` (use `npm ci` in CI).
3. Start the dev server via `npm run dev`. The app listens on `http://localhost:3000` by default.

If you need to communicate with the backend during development, configure environment variables in `.env.local` (e.g., `NEXT_PUBLIC_API_BASE=http://localhost:8000`). Never commit secret values.

## Development workflow
- Use TypeScript-ready patterns even in JavaScript files (explicit prop shapes, JSDoc where helpful) to smooth a future TS migration.
- Prefer [Server Components](https://nextjs.org/docs/app/building-your-application/rendering/server-components) unless client-side interactivity is required. Add `'use client';` only when necessary.
- Style components with module-scoped CSS (`*.module.css`) or CSS-in-JS. Keep global styles minimal and in `globals.css`.
- When adding fonts or metadata, update `src/app/layout.js`.
- For API calls, centralize fetch helpers to make SSR/ISR easier to manage and to inject auth headers consistently.

## Quality checks
- Lint before committing: `npm run lint`.
- Validate production builds: `npm run build` (Turbopack is enabled by default; fall back to webpack via `NEXT_DISABLE_TURBOPACK=1` if debugging bundler issues).
- If you add unit tests, colocate them with components (e.g., `Button.test.jsx`) and document the test runner command in the repository-level `AGENTS.md`.

## Current UI prototype
- The root route renders `src/components/home-page.jsx`, which handles auth via `/auth/register` and `/auth/login`, stores the bearer token in `localStorage`, and shows the active console once authenticated.
- `src/components/auth/AuthPanel.jsx` collects nickname/password/icon data and passes it directly to the FastAPI backend.
- `src/components/game/GameConsole.jsx` connects to the WebSocket endpoint (`ws://localhost:8000/ws/game` by default), streams ticks/reports, and exposes forms for each gameplay phase (buy/production/sell/loans/construction).
- `src/lib/apiClient.js` centralizes the API base URLs; override them with `NEXT_PUBLIC_API_BASE` if the backend runs on another host/port. WebSocket URLs are derived automatically from this base.
- After connecting to a session, the console sends a `session_control` command with `{"command": "start"}` to begin the monthly loop. The "Запустить сессию" button issues this command, and phase action buttons stay disabled until the command is acknowledged. If you wait, the backend will auto-start 60 seconds after ≥2 players are present, and the console will receive a `session_control_ack` with `reason="auto_timer"` so it can flip into the running state automatically.

## Dependency management
- Use npm for installs. Add runtime dependencies with `npm install <package>` and dev tools with `npm install -D <package>`.
- Commit the updated `package-lock.json`. Avoid editing it manually.
- When bumping Next.js or React, review release notes for breaking changes (especially around the App Router and React Compiler).

## Accessibility & internationalization
- Follow WCAG guidelines: provide accessible names, focus management, and keyboard navigation.
- Keep copy in centralized dictionaries when you introduce i18n; default to English strings until localization requirements arrive.

These guidelines keep the front-end consistent and ready for future automation.

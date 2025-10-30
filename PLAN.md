# Plan

- [x] Review existing game logic components and define the minimum viable data flow needed for WebSocket interactions (session bootstrap, decision intake, month advancement).
- [x] Implement an API-facing game session service that wraps `SessionOrchestrator`, manages in-memory state/log stores, initializes new sessions, and serializes snapshots/results for transport.
- [x] Extend the WebSocket router to authenticate clients, delegate to the session service for join/decision/advance actions, and stream structured JSON messages.
- [x] Add documentation describing the new WebSocket protocol and usage examples under `backend/docs/` and cover the behaviour with FastAPI WebSocket tests.

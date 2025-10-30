# WebSocket Game Session API

The Fabricat backend exposes an interactive simulation channel at `ws://<host>/ws/game`.
This endpoint allows authenticated clients to join a game session, submit phase decisions,
and drive the month-by-month game loop without resorting to polling.

## Connecting

- **URL**: `/ws/game`
- **Authentication**: Bearer token supplied as a `token` query parameter.
- **Optional query parameters**:
  - `session_id` — identifier for the logical simulation. Defaults to the JWT subject.
  - `company_id` — company that the connecting client represents. Defaults to the JWT subject.

On a successful handshake the server emits a single `session_settings` message describing
the fixed economy configuration for the session, followed by a `session_state` message
containing the current month snapshot and any stored logs.

```text
GET /ws/game?token=<jwt>&company_id=acme-industries
```

## Client messages

All client messages are JSON objects containing an `action` discriminator. The following
commands are supported:

### `join`

Request the current snapshot and logs again. Useful after reconnecting.

```json
{"action": "join"}
```

### `submit_decisions`

Store one or more decisions for the active month and phase. `company_id` defaults to
the value provided during connection when omitted.

```json
{
  "action": "submit_decisions",
  "phase": "production",
  "decisions": [
    {
      "company_id": "acme-industries",
      "payload": {"orders": [{"quantity": 2}]}
    }
  ]
}
```

### `advance_month`

Resolve the current month using all submitted decisions and broadcast the results.

```json
{"action": "advance_month"}
```

## Server messages

Responses are JSON payloads with a `type` discriminator.

### `session_settings`

Sent exactly once when the lobby host starts the game. It contains the immutable
economy configuration used to initialize the session. Subsequent messages will not
repeat this data, so clients should cache it locally.

```json
{
  "type": "session_settings",
  "session_id": "player-1",
  "configuration": {"startingCash": 100000, "phaseSequence": {...}}
}
```

### `session_state`

Broadcasts the latest `GameStateSnapshot` (excluding the configuration to keep the
settings message unique) and the ordered list of persisted month logs.

```json
{
  "type": "session_state",
  "session_id": "player-1",
  "snapshot": {"month_index": 1, "companies": {...}},
  "logs": [{"month_index": 0, "phases": [...]}]
}
```

### `decisions_stored`

Acknowledges that the supplied decisions were persisted.

```json
{
  "type": "decisions_stored",
  "session_id": "player-1",
  "phase": "production",
  "decisions": [
    {
      "company_id": "acme-industries",
      "phase": "production",
      "payload": {"orders": [{"quantity": 2}]},
      "month_index": 0
    }
  ]
}
```

### `month_result`

Contains the `MonthResult` for the resolved month (without duplicating the immutable
configuration), the updated snapshot, and the phase-by-phase log generated during
execution. The server follows this message with an updated `session_state` broadcast
for convenience.

```json
{
  "type": "month_result",
  "session_id": "player-1",
  "result": {"month_index": 0, "phase_results": [...]},
  "snapshot": {"month_index": 1, "companies": {...}},
  "log": {"month_index": 0, "phases": [...]}
}
```

### `error`

Returned when the server cannot parse or apply a command. The connection remains open.

```json
{
  "type": "error",
  "message": "Invalid decision payload",
  "detail": "Unknown company 'omega' for session player-1."
}
```

## Simulation defaults

The built-in `GameSessionService` bootstraps sessions with the default economy
configuration, a single active factory, and a modest stock of raw materials to allow
production decisions to take effect immediately. All data is stored in-memory; reconnecting
with the same `session_id` will resume the existing state for the duration of the API
process.

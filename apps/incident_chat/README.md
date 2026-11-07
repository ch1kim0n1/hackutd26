# Incident-scoped live chat (issue #27)

Winstead R05 — `docs/06-WINSTEAD-COMPLIANCE.md`, `chat_messages`
contract in `docs/04`.

## Components

- **`models.py`** — `Room`/`Message` (seq, client_nonce, sender
  role from server principal), `RoomKind` (incident + restricted
  command channel), `JOIN_RULES`/`POST_RULES` per kind, `sanitize()`
  strips markup → plain text only.
- **`service.py`** — `ChatService`:
  - `register_user` — role/incident scope from server-side IdP (#23),
    never client claims
  - `create_room`/`join`/`leave` — per-incident rooms; command
    channel restricted to admin+commander; incident-scope enforced
  - `post` — role check, **client_nonce dedup** (retry returns
    original, no duplicate), sanitize, seq ordering
  - `system_post` — agent missions/approval outcomes/verified
    containment w/ action+evidence links
  - `history(since_seq)` — reconnect recovery, ordered, no dupes
  - `presence`/`unread_counts`/`mark_read` — connection state +
    per-member unread cursors

## W05 acceptance mapping

- **W05a** commander↔responder exchange; sender role recorded;
  unread counts correct per member
- **W05b** observer joins incident room but cannot post; cannot join
  command channel; out-of-scope user denied entirely
- **W05c** reconnect `history(since_seq=2)` returns exactly missed
  messages 3–5
- **W05d** nonce retry → same msg_id, no duplicate; system posts
  link action/evidence; `<script>`/markup stripped or denied

## Tests

```sh
cd apps/incident_chat && PYTHONPATH=src python3 -m pytest tests/ -q   # 6 passed
```

## NOT done

- In-memory — production = SpacetimeDB `chat_messages` + subscriptions;
  no live multi-browser demo; offline delivery NOT claimed (history
  recovery only).
- Presence is connection-state in the service — real presence needs
  websocket heartbeat on deployed stack.
- Sanitization is strip-tags; renderers must still escape on display.

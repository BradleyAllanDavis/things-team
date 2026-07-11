# Things 3 internals — verified field semantics

Read-side knowledge of Things' SQLite schema, captured as it's verified
during development (cross-checked against [things.py](https://github.com/thingsapi/things.py)'s
documentation of the same schema). **Read-only forever** — direct writes to
this database fork Things Cloud state and are forbidden.

DB location: `~/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/ThingsData-*/Things Database.thingsdatabase/main.sqlite`
(TCC-protected on modern macOS; spokes read a `VACUUM INTO` snapshot mirror
instead — transactionally consistent, atomically replaced).

## TMTask

| Column | Semantics | Verified |
|---|---|---|
| `uuid` | primary key, the stable identity Things Cloud syncs | 2026-07 |
| `type` | 0 to-do, 1 project, 2 heading | 2026-07 |
| `status` | 0 open/incomplete, 2 canceled, 3 completed | 2026-07 |
| `trashed` | 0/1 — orthogonal to status | 2026-07 |
| `start` | 0 Inbox, 1 Anytime/Today, 2 Someday | 2026-07 |
| `startDate` | packed integer date (below); NULL = unscheduled | 2026-07 |
| `deadline` | packed integer date | 2026-07 |
| `creationDate`, `userModificationDate` | **plain Unix epoch seconds, UTC** — no Core Data reference-date offset (a natural trap; other Apple frameworks use offset 978307200) | 2026-07-10, against live data |
| `stopDate` | epoch seconds when completed/canceled | 2026-07 |
| `notes` | UTF-8 text | 2026-07 |
| `project`, `area`, `heading` | uuid FKs to container rows | 2026-07 |
| `rt1_recurrenceRule` | non-NULL ⇒ this row is a repeating template | 2026-07 |
| `rt1_repeatingTemplate` | non-NULL ⇒ this row is an instance spawned from a repeating template | 2026-07 |
| `reminderTime` | reminder time-of-day component (not yet needed; `when` carries dates only in v1) | unverified |

### Packed date format

`startDate`/`deadline` pack Y/M/D into one integer:
`YYYYYYYYYYYMMMMDDDDD0000000` (binary). SQL unpack (same expression
things.py documents):

```sql
CASE WHEN col THEN printf('%04d-%02d-%02d',
  (col & 134152192) >> 16, (col & 61440) >> 12, (col & 3968) >> 7)
ELSE NULL END
```

## TMTag / TMTaskTag

- `TMTag(uuid, title, …)` — tag vocabulary. Tags referenced by URL-scheme
  writes **must already exist**; unknown tags are silently dropped, never
  created. Neither the URL scheme nor the JSON command format can create a
  tag — only the GUI and AppleScript (`make new tag with properties {name:"…"}`).
- `TMTaskTag(tasks, tags)` — join table, uuid → uuid.

## TMChecklistItem

`(uuid, title, status, "index", task, …)` — `task` FKs the parent,
`"index"` orders (quote it — reserved word), `status` mirrors TMTask's
encoding. The URL scheme / JSON command format cannot set per-item checked
state on create — items always arrive unchecked.

## Write-path facts (URL scheme / JSON command format)

- `things:///json?auth-token=…&data=[…]` applies a batch of operations in
  one open. Op shape: `{"type": "to-do", "operation": "create|update",
  "id": "(update only)", "attributes": {…}}`.
- Create attributes: `title`, `notes`, `when` (`yyyy-mm-dd`, `today`,
  `someday`, …), `deadline`, `tags` (array; must pre-exist),
  `checklist-items` (`[{"type": "checklist-item", "attributes": {"title": …}}]`).
- Update attributes additionally: `completed: true`, `canceled: true` —
  idempotent on an already-terminal item.
- No delete exists in the URL scheme or JSON format (AppleScript
  `move (to do id X) to list "Trash"` is the only sanctioned path).
- Applies are async fire-and-forget: `open` returning proves nothing.
  **Always verify by reading the DB back**, bounded poll.
- Repeating todos cannot be completed/updated via the URL scheme, and
  recurrence cannot be set programmatically at all.
- Things.app can enter a state where it **self-activates (steals macOS
  focus) on any write** — `open -g` does not prevent it, and macOS provides
  no third-party veto. The only working technique is reactive: capture the
  frontmost app, watch a settle window, knock back observed steals
  (verify-and-retry; macOS 26 can silently swallow an `activate()`).
- Things Cloud rate-limits rapid successive writes from one account
  (observed `429`); pace or coalesce batches.

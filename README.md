# Things Team

**Multi-account task delegation for [Things 3](https://culturedcode.com/things/).**
Tag a todo with a family member's name; it appears natively in *their* Things
Inbox. Delegating IS the action — your copy completes itself the moment
delivery is confirmed, not whenever they get around to the task.

Cultured Code offers no way to sync tasks between separate Things accounts —
no public API, no server-side write path, no multi-user anything. Things Team
builds bidirectional delegation on top of that anyway, across users who share
zero infrastructure beyond a LAN.

```
you                                    them
────────────────────────────────────  ────────────────────────────────────
tag a todo `jill`          ──────▶    lands in her real Inbox,
                                      tagged `from-bradley 👨`
your copy retags to
`👉 delegated` AND marks itself
completed — same tick, no waiting     she files it wherever she likes,
                                      then completes it on her own time
```

## How it works

- **Hub** (`hub/`) — the only stateful coordinator: an id-mapping ledger
  (SQLite WAL), tenants/members/devices with capability tiers, a durable
  delivery queue with leases, hashed device-token auth. It never touches
  Things. Stdlib-only Python, no framework, no dependencies.
- **Spoke** (`spoke/`) — a thin, near-stateless agent per member Mac: reads
  that member's Things database (read-only, via a snapshot mirror), pushes
  outbound-tagged todos to the hub, applies inbound deliveries via the
  sanctioned `things:///json` URL scheme, echoes terminal states back.
  Runs on Apple's stock `/usr/bin/python3` — zero installs on a
  non-developer's Mac.
- **One spoke core, pluggable backends.** The same `SpokeCore` tick runs
  (a) in-process inside the hub for a member whose Macs already expose a
  write gateway, and (b) as a LaunchAgent on a plain Mac. Reader, writer,
  and hub transport are interfaces; the test suite swaps in fakes.

The full design — the verified physics of Things' URL scheme and SQLite
schema, the ledger schema, envelope fidelity rules, race semantics — is in
[DESIGN.md](DESIGN.md). The wire protocol and state machines are in
[PROTOCOL.md](PROTOCOL.md). Reverse-engineered Things internals are captured
in [THINGS-INTERNALS.md](THINGS-INTERNALS.md).

## The invariants

| Invariant | Mechanism |
|---|---|
| **No-loss** | The sender's copy is never modified until the hub durably committed the transfer. Deliveries persist until acked; leases expire and re-queue. Hub down? The tag itself is the retry queue. |
| **No-dup** | Idempotent push (`UNIQUE(tenant, from, src_uuid, rev)`), idempotent queueing (`UNIQUE(transfer, kind, to_member)`), and a spoke-side intent journal that re-correlates instead of re-firing after a crash. |
| **Completion round-trip** | Both sides of every open transfer are watched; terminal state is set once at the hub (completed beats canceled); the echo is just another idempotent delivery. |

`tests/test_invariants.py` proves all three end-to-end: a real hub and two
spokes over fake Things accounts, driven through randomized chaos — writer
crashes after firing, lost responses, expired leases — asserting no-loss /
no-dup / round-trip at quiescence. The whole suite (46 tests) is stdlib
`unittest`; even the tests have zero dependencies:

```
python3 -m unittest discover tests
```

## Deploying

v1 topology: hub on an always-on Linux box (NixOS module exported from
`flake.nix` as `nixosModules.things-team-hub`), one LaunchAgent spoke per
member Mac (`deploy/`). Members/devices are provisioned declaratively —
device tokens are materialized from a secrets manager at deploy time and the
hub stores only their hashes.

Landing semantics: inbound todos arrive in the recipient's **real Inbox**
(GTD's native landing zone) carrying a pre-created provenance tag
(`from-<sender>`) — no auto-created "Sync Inbox" project graveyard. The
sender's scheduled date rides along when explicitly set. Trigger tags match
**exact titles only** (a pre-existing `Jillian 👩🏻‍🦰` label must never
trigger delegation).

## Limits (v1, by the platform's physics)

- Repeating todos are refused loudly (the URL scheme can't complete them
  remotely). Projects/areas/headings don't sync — todos only.
- Checklist items arrive unchecked (no per-item state on create), max 100.
- Recipient tags don't transfer (their tag vocabulary is theirs).
- A todo delegates once; re-delegating a resolved transfer is a v2 seam
  (`rev > 1`), as are edit propagation, off-LAN members (TLS), and
  hub-hosted context bundles. See [ROADMAP.md](ROADMAP.md).

## Status

v1, LAN-only, two members. Built for my family; the tenancy model
(tenants → members → devices, capability tiers) is the seam for anything
bigger.

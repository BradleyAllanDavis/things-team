# Roadmap

v1 (shipped): two members, LAN, delegation with completion echo. Everything
below is a reserved seam, in rough order.

- **Edit propagation** — `rev > 1` on transfers (sender as sole editor until
  terminal state; the natural-key uniqueness already anchors it).
- **Re-delegation** — a resolved transfer's src_uuid can't currently be
  delegated again (push replays the resolved row). Ship together with rev
  bumps.
- **Off-LAN members** — shipped as an option (`deploy/aaron/`, hub behind a
  reverse tunnel; spoke config is already just `hub_url` + token file, and
  long-poll survives a tunnel untouched). Not the default — a member needs
  something in front of the hub if they're off the LAN.
- **Real auth** — OAuth/passkey sessions behind the same Principal
  resolution; static device tokens remain for headless spokes.
- **Tenant #2** — invite/pairing flow; the schema is already multi-tenant
  with structural isolation (tested).
- **Tag mapping** — per-tenant table translating payload tags between
  members' vocabularies (v1 drops payload tags).
- **Shared-project targeting** — optional target-list name when both sides
  agree on a project name; falls back to Inbox when unresolved (the URL
  scheme already behaves that way).
- **Context bundles** — `context_url` envelope field is reserved; phase 2
  options: markdown bundles in a shared git repo both members' agents read,
  or hub-hosted blobs once off-LAN members exist.
- **E2E payload encryption** — hub relays ciphertext; the envelope is
  already an opaque JSON document to the delivery machinery.
- **Things Cloud protocol spike** — reverse-engineered clients exist
  (`nicolai86/things-cloud-sdk`, `disrupted/things-cloud-api`). If the hub
  spoke Things Cloud directly per account, spokes disappear entirely (no
  Mac agent, no disk-access grants, iOS-only members become possible).
  Gated hard: a 2026-07 write-fidelity experiment against a sacrificial
  account confirmed core CRUD safe but found one silent-ghost-write defect
  class (a task-nested-under-task feature real Things doesn't have) — any
  adoption must excise that feature and pass a full cold-resync soak first.
  Read-only adoption (a change feed replacing spoke polling) is the safe
  first step.
- **Child capability tier** — `can_receive`-only members (the capability
  columns already exist).

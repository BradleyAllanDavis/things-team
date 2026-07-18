# Graph Report - artifact2  (2026-07-18)

## Corpus Check
- 35 files · ~22,049 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 470 nodes · 882 edges · 57 communities (14 shown, 43 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 150 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `f0e3b05c`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Hub Ledger Core
- HTTP Hub Client
- Design Docs & Deployment
- Spoke Core Tick
- Local Things Writer
- Things DB Mirror Reader
- Hub Server & Gateway
- Spoke Core Tests
- Direct Hub Client
- HTTP API Handler
- Fake Reader Fixtures
- Flaky Hub Fixture
- Terminal State Tests
- Condition Variable Tests
- Fake Writer Fixture
- Fake Things Account
- Invariant Chaos Simulation
- Spoke Test Base
- Transfer Protocol Endpoints
- Aaron Install Script
- Jill Install Script
- Things Focus Steal
- Aaron off-LAN spoke setup
- Full Disk Access grant on /bin/zsh
- Jill LaunchAgent spoke setup
- Device-token auth and Principal
- D2: delegating IS the action
- Delivery condition variable
- Envelope fidelity contract
- Git-repo-as-transport (rejected)
- Hub-and-spoke architecture
- Crash-safety intent journal
- Ledger schema
- Long-poll push transport
- Spoke tick loop
- Delegation sync flow
- Tick phase decoupling (tick_local / tick_inbound)
- Exact-match trigger tags
- In-process write gateway (deployment amendment)
- At-least-once delivery semantics
- GET /v1/deliveries (lease + long-poll)
- tandem.todo/1 wire envelope
- Completion round-trip invariant
- Hub (stateful coordinator)
- No-dup invariant
- No-loss invariant
- Sanctioned Things URL scheme
- E2E payload encryption (seam)
- Edit propagation (rev > 1 seam)
- Per-tenant tag mapping (v2 seam)
- Things Cloud protocol spike
- things:///json batch write path
- VACUUM INTO snapshot mirror
- Tags must pre-exist for programmatic writes

## God Nodes (most connected - your core abstractions)
1. `Ledger` - 64 edges
2. `SpokeState` - 34 edges
3. `SpokeCore` - 34 edges
4. `DirectHubClient` - 27 edges
5. `HttpHubClient` - 26 edges
6. `FakeThings` - 25 edges
7. `FlakyHub` - 25 edges
8. `LedgerError` - 22 edges
9. `NotFound` - 22 edges
10. `FakeReader` - 22 edges

## Surprising Connections (you probably didn't know these)
- `LedgerCVTest` --uses--> `DirectHubClient`  [INFERRED]
  tests/test_push.py → hub/direct.py
- `LongPollHttpTest` --uses--> `DirectHubClient`  [INFERRED]
  tests/test_push.py → hub/direct.py
- `TestTerminal` --uses--> `LedgerError`  [INFERRED]
  tests/test_ledger.py → hub/ledger.py
- `TestTerminal` --uses--> `AuthError`  [INFERRED]
  tests/test_ledger.py → hub/ledger.py
- `TestTerminal` --uses--> `Forbidden`  [INFERRED]
  tests/test_ledger.py → hub/ledger.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Delegation transfer lifecycle** — design_sync_flow, protocol_transfer_state_machine, protocol_delivery_state_machine, design_d2_completion, readme_completion_round_trip [EXTRACTED 1.00]
- **Idempotency anchor set** — readme_no_dup_invariant, design_ledger_schema, design_intent_journal, protocol_at_least_once [EXTRACTED 1.00]
- **Long-poll push transport stack** — design_long_poll, design_delivery_condition_variable, design_tick_phase_decoupling, protocol_deliveries_endpoint [EXTRACTED 1.00]

## Communities (57 total, 43 thin omitted)

### Community 0 - "Hub Ledger Core"
Cohesion: 0.05
Nodes (32): ApiHandler, BaseHTTPRequestHandler, tandem hub HTTP API — the /v1 surface spokes talk to.  Stdlib ThreadingHTTPServe, HubClient over direct ledger calls — used ONLY by the hub's in-process gateway w, AuthError, Forbidden, _hash_token(), Ledger (+24 more)

### Community 1 - "HTTP Hub Client"
Cohesion: 0.07
Nodes (17): make_server(), HttpHubClient, HubHTTPError, _NoRedirect, HubClient over HTTP — what a real (remote) spoke uses to talk to the tandem hub., The default opener follows cross-host redirects and resends every     header — i, ApiTest, HTTP surface tests — a real in-process server on an ephemeral port, exercised th (+9 more)

### Community 2 - "Design Docs & Deployment"
Cohesion: 0.04
Nodes (41): 1. Product framing, 2. The physics (verified constraints), 3.1 Deployment topology (amended 2026-07-11), 3.2 The sync flow (A delegates to B), 3.3 Spoke tick (serialized, on a configurable interval — 5s as deployed, 3. Architecture, 4. Ledger schema, 5. Envelope (fidelity contract) (+33 more)

### Community 3 - "Spoke Core Tick"
Cohesion: 0.08
Nodes (18): RuntimeError, _log(), tandem spoke core — the sync tick, backend-agnostic.  ONE core, TWO deployments, Every dst_uuid this spoke has already correlated — the exclusion         set for, The tick. All Things access via `reader`/`writer`, all hub access     via `hub`, Serialized full tick — one pass over all four phases in order.         Kept inta, Local-mirror-driven phases: detect newly-tagged outbound todos and         obser, Hub-driven phase: lease + apply deliveries. This is the leg that         blocks (+10 more)

### Community 4 - "Local Things Writer"
Cohesion: 0.13
Nodes (10): _activate(), _frontmost_name(), LocalWriter, _log(), ThingsWriter backed by local `things:///json` opens — the writer for a real Mac, Combined tags+terminal write in ONE open+verify round-trip         (one settle-w, URL applies are async fire-and-forget — never trust `open`         returning. Bo, FakeReader (+2 more)

### Community 5 - "Things DB Mirror Reader"
Cohesion: 0.16
Nodes (9): Connection, _log(), MirrorReader, Read-only Things 3 database access for spokes — stdlib sqlite3 against a things-, Read-after-write uuid discovery for a just-created todo: exact         title + c, SQL expression unpacking Things' packed date int to ISO — same     expression th, ThingsReader over a things-mirror sqlite snapshot.      kick_agent: launchd labe, Open, untrashed TO-DOS carrying one of the trigger tags, matched         on EXAC (+1 more)

### Community 6 - "Hub Server & Gateway"
Cohesion: 0.16
Nodes (12): bootstrap(), _credential(), _log(), main(), tandem hub entrypoint — HTTP API + declarative bootstrap + the in-process gatewa, The in-process spoke for the gateway member (Bradley): reader = the     Syncthin, Idempotently ensure tenant / members / provisioned spoke devices.     Token rota, run_gateway_worker() (+4 more)

### Community 7 - "Spoke Core Tests"
Cohesion: 0.05
Nodes (25): DirectHubClient, CrashAfterFire, FakeReader, FakeThings, FakeWriter, FlakyHub, Exception, In-memory fakes for spoke tests and the invariant simulation: a FakeThings 'acco (+17 more)

### Community 8 - "Direct Hub Client"
Cohesion: 0.29
Nodes (6): 0. What must exist first, 1. Manual one-time grants + tokens (needs hands on the Mac), 2. Install, 3. Verify, Spoke setup — Aaron's Mac, Troubleshooting

### Community 9 - "HTTP API Handler"
Cohesion: 0.29
Nodes (6): 0. What must exist first, 1. Manual one-time grants + tokens (needs hands on the Mac), 2. Install, 3. Verify, Spoke setup — Jill's MacBook Air, Troubleshooting

### Community 10 - "Fake Reader Fixtures"
Cohesion: 0.29
Nodes (6): Cloud, Pipeline (one command: `git push`), 🚢 tandem hub on Kubernetes — the Nix-homelab-to-K8s projection, The manifests, Translation table, What the deployed instance is

## Knowledge Gaps
- **85 isolated node(s):** `install.sh script`, `install.sh script`, `graphify`, `1. Product framing`, `2. The physics (verified constraints)` (+80 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **43 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Ledger` connect `Hub Ledger Core` to `HTTP Hub Client`, `Hub Server & Gateway`, `Spoke Core Tests`, `Terminal State Tests`, `Condition Variable Tests`?**
  _High betweenness centrality (0.233) - this node is a cross-community bridge._
- **Why does `SpokeCore` connect `Spoke Core Tick` to `HTTP Hub Client`, `Condition Variable Tests`, `Hub Server & Gateway`, `Spoke Core Tests`?**
  _High betweenness centrality (0.092) - this node is a cross-community bridge._
- **Why does `SpokeState` connect `Spoke Core Tick` to `HTTP Hub Client`, `Condition Variable Tests`, `Hub Server & Gateway`, `Spoke Core Tests`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `Ledger` (e.g. with `ApiHandler` and `DirectHubClient`) actually correct?**
  _`Ledger` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `SpokeState` (e.g. with `InvariantSim` and `LedgerCVTest`) actually correct?**
  _`SpokeState` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `SpokeCore` (e.g. with `InvariantSim` and `LedgerCVTest`) actually correct?**
  _`SpokeCore` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `DirectHubClient` (e.g. with `Ledger` and `Principal`) actually correct?**
  _`DirectHubClient` has 11 INFERRED edges - model-reasoned connections that need verification._
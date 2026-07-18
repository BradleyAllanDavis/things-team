# Graph Report - .  (2026-07-13)

## Corpus Check
- Corpus is ~20,278 words - fits in a single context window. You may not need a graph.

## Summary
- 405 nodes · 871 edges · 25 communities (14 shown, 11 thin omitted)
- Extraction: 81% EXTRACTED · 19% INFERRED · 0% AMBIGUOUS · INFERRED: 167 edges (avg confidence: 0.57)
- Token cost: 0 input · 0 output

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

## God Nodes (most connected - your core abstractions)
1. `Ledger` - 65 edges
2. `SpokeCore` - 36 edges
3. `SpokeState` - 34 edges
4. `DirectHubClient` - 27 edges
5. `HttpHubClient` - 26 edges
6. `FakeThings` - 25 edges
7. `FlakyHub` - 25 edges
8. `LedgerError` - 22 edges
9. `NotFound` - 22 edges
10. `FakeReader` - 22 edges

## Surprising Connections (you probably didn't know these)
- `Hub (stateful coordinator)` --references--> `Ledger`  [INFERRED]
  README.md → hub/ledger.py
- `Spoke (per-member agent)` --references--> `SpokeCore`  [INFERRED]
  README.md → spoke/core.py
- `Device-token auth and Principal` --conceptually_related_to--> `provenance_tag()`  [INFERRED]
  DESIGN.md → hub/ledger.py
- `In-process write gateway (deployment amendment)` --references--> `SpokeCore`  [EXTRACTED]
  DESIGN.md → spoke/core.py
- `InvariantSim` --uses--> `DirectHubClient`  [INFERRED]
  tests/test_invariants.py → hub/direct.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Delegation transfer lifecycle** — design_sync_flow, protocol_transfer_state_machine, protocol_delivery_state_machine, design_d2_completion, readme_completion_round_trip [EXTRACTED 1.00]
- **Idempotency anchor set** — readme_no_dup_invariant, design_ledger_schema, design_intent_journal, protocol_at_least_once [EXTRACTED 1.00]
- **Long-poll push transport stack** — design_long_poll, design_delivery_condition_variable, design_tick_phase_decoupling, protocol_deliveries_endpoint [EXTRACTED 1.00]

## Communities (25 total, 11 thin omitted)

### Community 0 - "Hub Ledger Core"
Cohesion: 0.05
Nodes (33): tandem hub HTTP API — the /v1 surface spokes talk to.  Stdlib ThreadingHTTPServe, HubClient over direct ledger calls — used ONLY by the hub's in-process gateway w, AuthError, Forbidden, _hash_token(), Ledger, LedgerError, _new_id() (+25 more)

### Community 1 - "HTTP Hub Client"
Cohesion: 0.07
Nodes (17): make_server(), HttpHubClient, HubHTTPError, _NoRedirect, HubClient over HTTP — what a real (remote) spoke uses to talk to the tandem hub., The default opener follows cross-host redirects and resends every     header — i, ApiTest, HTTP surface tests — a real in-process server on an ephemeral port, exercised th (+9 more)

### Community 2 - "Design Docs & Deployment"
Cohesion: 0.06
Nodes (37): CI test matrix (ubuntu 3.13 / macos 3.9), graphify knowledge-graph integration, Cloudflare Tunnel hub access, Aaron off-LAN spoke setup, Full Disk Access grant on /bin/zsh, Jill LaunchAgent spoke setup, Device-token auth and Principal, D2: delegating IS the action (+29 more)

### Community 3 - "Spoke Core Tick"
Cohesion: 0.09
Nodes (16): Spoke tick loop, Tick phase decoupling (tick_local / tick_inbound), In-process write gateway (deployment amendment), RuntimeError, _log(), Every dst_uuid this spoke has already correlated — the exclusion         set for, The tick. All Things access via `reader`/`writer`, all hub access     via `hub`, Serialized full tick — one pass over all four phases in order.         Kept inta (+8 more)

### Community 4 - "Local Things Writer"
Cohesion: 0.13
Nodes (10): _activate(), _frontmost_name(), LocalWriter, _log(), ThingsWriter backed by local `things:///json` opens — the writer for a real Mac, Combined tags+terminal write in ONE open+verify round-trip         (one settle-w, URL applies are async fire-and-forget — never trust `open`         returning. Bo, FakeReader (+2 more)

### Community 5 - "Things DB Mirror Reader"
Cohesion: 0.12
Nodes (15): Connection, _file_token(), _log(), main(), tandem spoke entrypoint — the LaunchAgent on a member's Mac (Jill's MacBook Air, _log(), MirrorReader, Read-only Things 3 database access for spokes — stdlib sqlite3 against a things- (+7 more)

### Community 6 - "Hub Server & Gateway"
Cohesion: 0.16
Nodes (12): bootstrap(), _credential(), _log(), main(), tandem hub entrypoint — HTTP API + declarative bootstrap + the in-process gatewa, The in-process spoke for the gateway member (Bradley): reader = the     Syncthin, Idempotently ensure tenant / members / provisioned spoke devices.     Token rota, run_gateway_worker() (+4 more)

### Community 7 - "Spoke Core Tests"
Cohesion: 0.16
Nodes (6): CrashAfterFire, Exception, Injected: the write reached Things, the spoke died before ack., TestInboundCrashSafety, TestOutbound, TestRoundTrip

### Community 8 - "Direct Hub Client"
Cohesion: 0.18
Nodes (3): DirectHubClient, tick_local()/tick_inbound() must compose to the same behavior tick()     has — t, SplitPhaseTest

### Community 10 - "Fake Reader Fixtures"
Cohesion: 0.20
Nodes (3): FakeReader, The gateway's two loops (inbound touches journal, local touches     sent_cache/o, SpokeStateConcurrencyTest

### Community 18 - "Transfer Protocol Endpoints"
Cohesion: 0.50
Nodes (4): POST /v1/observations, Transfer state machine, POST /v1/transfers, Edit propagation (rev > 1 seam)

## Knowledge Gaps
- **19 isolated node(s):** `install.sh script`, `install.sh script`, `In-process write gateway (deployment amendment)`, `Exact-match trigger tags`, `Spoke tick loop` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Ledger` connect `Hub Ledger Core` to `HTTP Hub Client`, `Design Docs & Deployment`, `Hub Server & Gateway`, `Spoke Core Tests`, `Direct Hub Client`, `HTTP API Handler`, `Fake Reader Fixtures`, `Terminal State Tests`, `Condition Variable Tests`, `Invariant Chaos Simulation`, `Spoke Test Base`?**
  _High betweenness centrality (0.396) - this node is a cross-community bridge._
- **Why does `SpokeCore` connect `Spoke Core Tick` to `Hub Ledger Core`, `HTTP Hub Client`, `Design Docs & Deployment`, `Things DB Mirror Reader`, `Hub Server & Gateway`, `Spoke Core Tests`, `Direct Hub Client`, `Fake Reader Fixtures`, `Condition Variable Tests`, `Invariant Chaos Simulation`, `Spoke Test Base`?**
  _High betweenness centrality (0.205) - this node is a cross-community bridge._
- **Why does `SpokeState` connect `Spoke Core Tick` to `Hub Ledger Core`, `HTTP Hub Client`, `Design Docs & Deployment`, `Things DB Mirror Reader`, `Hub Server & Gateway`, `Spoke Core Tests`, `Direct Hub Client`, `Fake Reader Fixtures`, `Condition Variable Tests`, `Invariant Chaos Simulation`, `Spoke Test Base`?**
  _High betweenness centrality (0.113) - this node is a cross-community bridge._
- **Are the 19 inferred relationships involving `Ledger` (e.g. with `ApiHandler` and `DirectHubClient`) actually correct?**
  _`Ledger` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `SpokeCore` (e.g. with `Spoke (per-member agent)` and `InvariantSim`) actually correct?**
  _`SpokeCore` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `SpokeState` (e.g. with `InvariantSim` and `LedgerCVTest`) actually correct?**
  _`SpokeState` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `DirectHubClient` (e.g. with `Ledger` and `Principal`) actually correct?**
  _`DirectHubClient` has 11 INFERRED edges - model-reasoned connections that need verification._
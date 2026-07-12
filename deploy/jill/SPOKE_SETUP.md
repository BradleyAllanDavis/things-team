# Spoke setup — Jill's MacBook Air

The one real spoke in the v1 deployment. Everything runs on stock macOS
(`/usr/bin/python3`, `/bin/zsh`, launchd) — no Homebrew/Nix required.
`install.sh` is idempotent; these are the steps around it.

## 0. What must exist first

- The hub live on the LAN (`http://192.168.0.30:8712`) with this Mac's
  device provisioned (`jill-air` — done declaratively on the hub host).
- Things 3 installed, signed into her Things Cloud, running.

## 1. Manual one-time grants + tokens (needs hands on the Mac)

1. **Full Disk Access for `/bin/zsh`** (the mirror agent's interpreter):
   System Settings → Privacy & Security → Full Disk Access → `+` →
   `⌘⇧G` → `/bin/zsh`. Survives all updates because the grant is on a
   stable Apple binary.
2. **Things URL scheme token**: Things → Settings → General → Enable
   Things URLs → copy token, then:
   ```bash
   mkdir -p ~/.config/things-team
   printf '%s' '<THINGS-TOKEN>' > ~/.config/things-team/things-auth-token
   chmod 600 ~/.config/things-team/things-auth-token
   ```
   (Canonical copy lives in 1Password; the file is deploy-derived.)
3. **Hub device token** (issued at hub provisioning, canonical in
   1Password — `Things Team Jill Device Token`):
   ```bash
   printf '%s' '<DEVICE-TOKEN>' > ~/.config/things-team/device-token
   chmod 600 ~/.config/things-team/device-token
   ```

## 2. Install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/BradleyAllanDavis/tandem/main/deploy/jill/install.sh)
```

or clone and run `deploy/jill/install.sh`. It clones/updates the repo,
writes/reconciles the spoke config, **pre-creates the three tags this Mac
needs** (`b`, `👉 delegated`, `from-bradley 👨` — programmatic writes silently
drop unknown tags), installs + loads both LaunchAgents. Re-running the
script also reconciles `trigger_tags`/`tick_seconds`/`poll_wait` on an
already-installed Mac, so a `git pull && ./install.sh` picks up config
changes without a fresh install.

| Agent | What |
|---|---|
| `com.jill.things-mirror` | 5s snapshot of the Things DB to `~/.cache/things-mirror/main.sqlite` (zsh + FDA) — tightened from 30s 2026-07-11, this runs continuously all day and is a real (if small) extra CPU/battery/log-chatter cost |
| `com.jill.things-team-spoke` | the spoke tick (KeepAlive, stock python3), 5s interval, long-polls deliveries for ~3s of it |

## 3. Verify

```bash
ls -la ~/.cache/things-mirror/main.sqlite     # mirror landed (FDA works)
tail -20 /tmp/things-team-spoke.err           # "spoke up: hub=…", ticking
```

Then the live loop, both directions:

1. On the other member's Mac: tag any todo `j` → within ~10-20s it
   appears in **this** Mac's Things Inbox tagged `from-bradley 👨`, and the
   sender's copy retags to `👉 delegated` AND marks itself completed — same
   tick, not waiting on you to finish the task (D2, 2026-07-11).
2. Complete it here whenever — the sender's copy already closed out at
   delivery; your completion just resolves the transfer on the hub side.
3. Reverse: tag a todo `b` here → lands in his Inbox (`from-jill 👩🏻‍🦰`),
   your own copy here completes at send too → he completes his on his own
   time.

## Troubleshooting

- `no Things database visible` in `/tmp/things-mirror.err` → FDA grant
  missing (step 1.1).
- Spoke log shows `hub returned 401` → device token file wrong/rotated.
- Created todos never correlate → Things URL token wrong (writes are
  silently dropped); re-check step 1.2.
- Hub unreachable → it polls and retries; tagged todos just wait. Check
  `curl -s -H "Authorization: Bearer $(cat ~/.config/things-team/device-token)" http://192.168.0.30:8712/v1/health`.

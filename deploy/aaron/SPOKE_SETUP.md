# Spoke setup — Aaron's Mac

Aaron is off-LAN (his own house, his own Mac, his own Things account) — this
setup is `deploy/jill/`'s pattern adapted for that: the hub URL is the public
Cloudflare Tunnel hostname instead of a LAN IP, otherwise identical. Stock
macOS (`/usr/bin/python3`, `/bin/zsh`, launchd), no Homebrew/Nix required.
`install.sh` is idempotent; these are the steps around it.

**Unresolved as of 2026-07-11 — who actually runs this, and how:** Jill's
equivalent install was largely driven *by Bradley*, remotely, over SSH
(`jill-dotfiles/remote-admin.sh`) — he has that kind of access to her Mac.
Bradley has no such access to Aaron's Mac, and Aaron isn't a Mac Bradley
controls or administers. Nothing in
`docs/plans/things-team-external-access.md` specifies how this script and
the manual grants below actually get executed on Aaron's machine — screen
share with Bradley narrating each step, Aaron running it solo off written
instructions, temporary remote-access software with Aaron's explicit
consent, or something else. Decide this before sending Aaron anything.

## 0. What must exist first

- The Cloudflare Tunnel live and routing to the hub (see the HANDOFF doc —
  blocked as of 2026-07-11 on a Cloudflare API token permission).
- This Mac's device provisioned on the hub (`aaron-air` — done declaratively
  on the hub host, `mine.services.things-team-hub` in
  `systems/linux/protectli/services.nix`).
- Things 3 installed, signed into his Things Cloud, running.

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
3. **Hub device token** (issued at hub provisioning, canonical in
   1Password — `Things Team Aaron Device Token`):
   ```bash
   printf '%s' '<DEVICE-TOKEN>' > ~/.config/things-team/device-token
   chmod 600 ~/.config/things-team/device-token
   ```
   Someone with 1Password Automation-vault access has to hand Aaron this
   value out-of-band (voice call, not email/text) — he has no 1Password
   access of his own.

## 2. Install

```bash
THINGS_TEAM_HUB_URL="https://<tunnel-hostname>.bdavis.io" \
  bash <(curl -fsSL https://raw.githubusercontent.com/BradleyAllanDavis/things-team/main/deploy/aaron/install.sh)
```

or clone and run `deploy/aaron/install.sh` with that env var set. It
clones/updates the repo, writes/reconciles the spoke config, **pre-creates
the three tags this Mac needs** (`b`, `👉 delegated`, `from-bradley 👨` —
programmatic writes silently drop unknown tags), installs + loads both
LaunchAgents.

| Agent | What |
|---|---|
| `com.aaron.things-mirror` | 5s snapshot of the Things DB to `~/.cache/things-mirror/main.sqlite` (zsh + FDA) |
| `com.aaron.things-team-spoke` | the spoke tick (KeepAlive, stock python3), 5s interval, long-polls deliveries for ~3s of it, over HTTPS to the tunnel hostname |

## 3. Verify

```bash
ls -la ~/.cache/things-mirror/main.sqlite     # mirror landed (FDA works)
tail -20 /tmp/things-team-spoke.err           # "spoke up: hub=…", ticking
```

Then the live loop, both directions:

1. Bradley tags a todo `aaron` → within ~10-20s it appears in Aaron's
   Things Inbox tagged `from-bradley 👨`, and Bradley's copy retags to
   `👉 delegated` AND marks itself completed — same tick, not waiting on
   Aaron to finish the task (D2, 2026-07-11).
2. Aaron completes it whenever — Bradley's copy already closed out at
   delivery; Aaron's completion just resolves the transfer hub-side.
3. Reverse: Aaron tags a todo `b` → lands in Bradley's Inbox
   (`from-aaron`, no emoji configured yet — add one to `hub/ledger.py`'s
   `_PROVENANCE_EMOJI` when Aaron's person-emoji is decided) → Aaron's own
   copy completes at send too → Bradley completes his on his own time.

## Troubleshooting

- `no Things database visible` in `/tmp/things-mirror.err` → FDA grant
  missing (step 1.1).
- Spoke log shows `hub returned 401` → device token file wrong/rotated.
- Created todos never correlate → Things URL token wrong (writes are
  silently dropped); re-check step 1.2.
- Hub unreachable → check the tunnel is actually up
  (`curl -s https://<tunnel-hostname>.bdavis.io/v1/health` should return
  401, not a connection error) before assuming the spoke is broken.

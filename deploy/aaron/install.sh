#!/usr/bin/env bash
# things-team spoke installer for a member Mac (Aaron's Mac).
# Idempotent — safe to re-run. Everything is stock macOS: /usr/bin/python3,
# /bin/zsh, launchd. No Homebrew/Nix dependencies.
#
# Aaron is off-LAN (his own house, his own Mac) — unlike Jill's install,
# this one reaches the hub over the public Cloudflare Tunnel hostname, not
# a LAN IP. See docs/plans/things-team-external-access.md for the full
# design and threat model.
#
# Prereqs done ONCE by hand before this works end-to-end (see
# SPOKE_SETUP.md):
#   1. Full Disk Access for /bin/zsh (the mirror agent).
#   2. Things → Settings → General → Enable Things URLs; token saved to
#      ~/.config/things-team/things-auth-token (chmod 600).
#   3. Hub device token saved to ~/.config/things-team/device-token (chmod 600).

set -euo pipefail

REPO_URL="https://github.com/BradleyAllanDavis/things-team"
REPO_DIR="$HOME/things-team"
APPSUPPORT="$HOME/Library/Application Support/things-team"
CONFIG_DIR="$HOME/.config/things-team"
AGENTS="$HOME/Library/LaunchAgents"
# HTTPS Cloudflare Tunnel hostname — Aaron is off-LAN, there is no LAN IP
# path for him. Fill in the real hostname once the tunnel exists (see
# docs/research/things-team-HANDOFF.md).
HUB_URL="${THINGS_TEAM_HUB_URL:-https://REPLACE-WITH-TUNNEL-HOSTNAME.bdavis.io}"

echo "=== things-team spoke install ==="

# 1. Code
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$REPO_DIR"
fi

# 2. Config (only written if absent — preserves local edits)
mkdir -p "$APPSUPPORT" "$CONFIG_DIR" "$AGENTS"
CONFIG="$APPSUPPORT/config.json"
if [ ! -f "$CONFIG" ]; then
  cat > "$CONFIG" <<JSON
{
  "hub_url": "$HUB_URL",
  "device_token_file": "$CONFIG_DIR/device-token",
  "things_auth_token_file": "$CONFIG_DIR/things-auth-token",
  "trigger_tags": {"bradley": ["b"]},
  "mirror_path": "$HOME/.cache/things-mirror/main.sqlite",
  "mirror_agent": "com.aaron.things-mirror",
  "tick_seconds": 5,
  "poll_wait": 3
}
JSON
  echo "wrote $CONFIG"
fi

# Reconcile keys that must track the deployed pattern even on an existing
# install — re-running this script is how an already-installed Mac picks
# these up, since the block above only writes when the file is absent.
python3 - "$CONFIG" <<'PYEOF'
import json, sys
path = sys.argv[1]
with open(path) as f:
    cfg = json.load(f)
cfg["trigger_tags"] = {"bradley": ["b"]}
cfg["tick_seconds"] = 5
cfg["poll_wait"] = 3
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PYEOF
echo "config reconciled: trigger_tags.bradley=[b], tick_seconds=5, poll_wait=3"

# 3. Pre-create the tags this Mac's Things needs (programmatic writes
#    silently drop unknown tags): the trigger tag, the delegated tag, and
#    the provenance tag for arrivals from the other member. Identical set
#    to Jill's — both describe "the other party" (Bradley).
osascript <<'EOF'
tell application "Things3"
    repeat with tagName in {"b", "👉 delegated", "from-bradley"}
        try
            set t to tag (tagName as string)
        on error
            make new tag with properties {name:(tagName as string)}
        end try
    end repeat
end tell
EOF
echo "tags ensured: b / 👉 delegated / from-bradley"

# 4. Mirror agent (/bin/zsh + FDA — see header)
cp "$REPO_DIR/deploy/aaron/things-mirror.zsh" "$APPSUPPORT/things-mirror.zsh"
cat > "$AGENTS/com.aaron.things-mirror.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.aaron.things-mirror</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string>
    <string>$APPSUPPORT/things-mirror.zsh</string>
  </array>
  <key>StartInterval</key><integer>5</integer>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>/tmp/things-mirror.out</string>
  <key>StandardErrorPath</key><string>/tmp/things-mirror.err</string>
</dict></plist>
PLIST

# 5. Spoke agent (stock python3, KeepAlive)
cat > "$AGENTS/com.aaron.things-team-spoke.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.aaron.things-team-spoke</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string>
    <string>$REPO_DIR/spoke/main.py</string>
  </array>
  <key>KeepAlive</key><true/>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>/tmp/things-team-spoke.out</string>
  <key>StandardErrorPath</key><string>/tmp/things-team-spoke.err</string>
</dict></plist>
PLIST

for label in com.aaron.things-mirror com.aaron.things-team-spoke; do
  launchctl unload "$AGENTS/$label.plist" 2>/dev/null || true
  launchctl load "$AGENTS/$label.plist"
done

echo ""
echo "=== Installed. Verify: ==="
echo "  1. ls -la ~/.cache/things-mirror/main.sqlite   (mirror landing — needs FDA on /bin/zsh)"
echo "  2. tail -f /tmp/things-team-spoke.err          (spoke tick log)"
echo "  3. Token files present + chmod 600:"
echo "       $CONFIG_DIR/device-token"
echo "       $CONFIG_DIR/things-auth-token"

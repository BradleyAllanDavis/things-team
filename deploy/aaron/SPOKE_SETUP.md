# Setting up Tandem on your Mac

Hi Aaron — this sets up two-way task sharing between your Things app and
Bradley's. Tag a task `b` and it lands in his Things inbox; when he tags one
for you, it lands in yours. Nothing is installed except one small program
that only Bradley's server on his end talks to — it never touches your
Things Cloud account or password.

Everything below runs with tools already built into your Mac (Terminal,
Python, the built-in scripting tool). Nothing to download except the
Tandem code itself, which the install command handles for you.

**Before you start:** Things 3 needs to be installed and you need to be
signed into your own Things account in it. That's it — everything else
Bradley already set up on his side.

Budget about 10 minutes. Do the steps in order.

## Step 1 — Give Terminal permission to read your task list

1. Open **System Settings** (the gear icon, or click the Apple menu top
   left → System Settings).
2. Go to **Privacy & Security** → **Full Disk Access**.
3. Click the **+** button.
4. A file picker opens. Press **Cmd+Shift+G** (this opens a "Go to folder"
   box), type `/bin/zsh`, and press Return. This adds `zsh` — the program
   that reads a private copy of your task list — to the allowed list.
5. Make sure the switch next to it is turned **on**.

This survives macOS updates, so you only do it once.

## Step 2 — Turn on the Things URL and save your token

1. Open **Things**.
2. Go to **Things → Settings…** (top-left menu) → **General**.
3. Turn on **Enable Things URLs**.
4. Click to reveal/copy the token shown there (a long string of letters
   and numbers).
5. Open **Terminal** (press **Cmd+Space**, type `Terminal`, press Return).
6. Paste this, but replace `PASTE-YOUR-TOKEN-HERE` with the token you just
   copied (right-click → Paste to paste into Terminal), then press Return:

   ```bash
   mkdir -p ~/.config/things-team
   printf '%s' 'PASTE-YOUR-TOKEN-HERE' > ~/.config/things-team/things-auth-token
   chmod 600 ~/.config/things-team/things-auth-token
   ```

## Step 3 — Save the device token Bradley gives you

Bradley will read you a second, different token **over a phone call** (not
text or email — it's a credential, so it's handled like one). In the same
Terminal window, paste this and replace `PASTE-DEVICE-TOKEN-HERE` with what
he reads you, then press Return:

```bash
printf '%s' 'PASTE-DEVICE-TOKEN-HERE' > ~/.config/things-team/device-token
chmod 600 ~/.config/things-team/device-token
```

## Step 4 — Run the installer

Still in Terminal, paste this exactly and press Return:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/BradleyAllanDavis/tandem/main/deploy/aaron/install.sh)
```

It downloads the code, sets everything up, and starts two small background
helpers. It's safe to run more than once — if anything looks wrong later,
re-running this exact command is a reasonable first thing to try.

**Two popups you might see the first time — both are normal, say yes to
both:**
- *"Terminal" wants to control "Things3"* — click **Allow**. This is macOS
  asking permission for the install script to create a few tags in Things.
- If this is a fairly new Mac and it's the very first time you've typed a
  command like this: macOS may pop up asking to install **"command line
  developer tools."** Click **Install**, wait for it to finish (a few
  minutes, needs internet), then run the same install command again.

When it finishes, it prints a checklist. If it says anything is
**MISSING**, go back and redo that step (2 or 3 above), then run the
install command again.

## Step 5 — Confirm it's actually working

Paste each of these one at a time:

```bash
ls -la ~/.cache/things-mirror/main.sqlite
```
You should see a file listed with a recent timestamp (today, a few seconds
old). If instead it says "No such file or directory," Step 1 (Full Disk
Access) didn't take — redo it, then wait about 10 seconds and try again.

```bash
tail -20 /tmp/things-team-spoke.err
```
You should see lines like `spoke up: hub=…` repeating every few seconds.
If you see `hub returned 401` instead, the device token from Step 3 is
wrong — call Bradley back for the right one and redo Step 3.

### The real test

1. Ask Bradley to tag a task `aaron` on his end. Within about 20-30 seconds
   it should show up in **your** Things Inbox, tagged `from-bradley 👨`.
2. File it wherever you like, complete it whenever — no rush, his copy
   already marked itself done the moment it reached you.
3. To send one back: tag any of your own tasks `b` (lowercase). It lands
   in his Inbox tagged `from-aaron`, and your copy marks itself done the
   moment it arrives.

If both directions work, you're done.

## If something's not working

- `no Things database visible` in `/tmp/things-mirror.err` → Step 1 (Full
  Disk Access) is missing or wasn't actually turned on. Redo it.
- `/tmp/things-team-spoke.err` shows `hub returned 401` → the device token
  (Step 3) is wrong. Ask Bradley to read it to you again and re-save it.
- Tasks you tag `b` never show up on Bradley's end → the Things URL token
  (Step 2) is likely wrong — Things silently ignores a bad token instead of
  erroring. Redo Step 2.
- Can't reach the server at all → paste this and read what comes back:
  ```bash
  curl -s https://y8xh2lm6s9f1uu0t5jq8.bdavis.io/v1/health
  ```
  A working server answers with something like
  `{"ok": true, "pending_deliveries": 0, "open_transfers": 0}`. If instead
  you get "Could not resolve host" or it hangs with nothing back, the
  problem is on Bradley's end (his server is down) — text him this exact
  output and he'll take it from there.

Anything else that doesn't match one of the above — screenshot the
Terminal output and send it to Bradley. He can read what a program printed
without needing hands on your Mac.

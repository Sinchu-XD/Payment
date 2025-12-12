#!/usr/bin/env bash
set -euo pipefail

# === CONFIG ===
BASE_DIR="/home/ubuntu/Payment"   # <-- change if your repo path is different
VENV="$BASE_DIR/venv"
WEBHOOK_LOG="$BASE_DIR/webhook.log"
CLOUD_LOG="$BASE_DIR/cloudflared.log"
BOT_LOG="$BASE_DIR/bot.log"
ENV_FILE="$BASE_DIR/paymentbot.env"   # or use .env if you prefer
CLOUDFLARED_CMD="cloudflared tunnel --url http://localhost:8000"

# === helper ===
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

cd "$BASE_DIR"

if [ ! -d "$VENV" ]; then
  log "Virtualenv not found at $VENV. Create and install deps first."
  exit 1
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  log "cloudflared not found in PATH. Install it first: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation"
  exit 1
fi

# Activate venv for python commands
ACTIVATE="$VENV/bin/activate"
if [ ! -f "$ACTIVATE" ]; then
  log "Activate script missing: $ACTIVATE"
  exit 1
fi

# 1) Start webhook.py in background (if not already running)
if pgrep -f "python.*webhook.py" >/dev/null 2>&1; then
  log "webhook.py already running (skipping start)."
else
  log "Starting webhook.py (background). Output -> $WEBHOOK_LOG"
  nohup bash -lc "source '$ACTIVATE' && python3 webhook.py" > "$WEBHOOK_LOG" 2>&1 &
  sleep 1
fi

# 2) Start cloudflared and capture its output into CLOUD_LOG
if pgrep -f "cloudflared.*--url http://localhost:8000" >/dev/null 2>&1; then
  log "cloudflared already running (skipping start)."
else
  log "Starting cloudflared tunnel (background). Output -> $CLOUD_LOG"
  # run cloudflared, keep it running and log output
  nohup $CLOUDFLARED_CMD > "$CLOUD_LOG" 2>&1 &
  sleep 1
fi

# 3) Wait & parse cloudflared output for HTTPS URL (max wait 90s)
log "Waiting for cloudflared to expose a public URL (timeout 90s)..."
URL=""
for i in $(seq 1 90); do
  if [ -f "$CLOUD_LOG" ]; then
    # try to extract first HTTPS URL
    URL=$(grep -Eo "https?://[^ ]+trycloudflare.com" "$CLOUD_LOG" | head -n1 || true)
    # fallback: any https://... (less strict)
    if [ -z "$URL" ]; then
      URL=$(grep -Eo "https?://[A-Za-z0-9./?-]*" "$CLOUD_LOG" | grep -E "https?://" | head -n1 || true)
    fi
  fi

  if [ -n "$URL" ]; then
    log "Found public URL: $URL"
    break
  fi
  sleep 1
done

if [ -z "$URL" ]; then
  log "Could not detect public URL from cloudflared within 90s. Check $CLOUD_LOG for details."
  exit 1
fi

# ensure webhook path suffix
WEBHOOK_URL="${URL%/}/webhook"
log "Webhook final URL: $WEBHOOK_URL"

# 4) write/update ENV file with WEBHOOK_PUBLIC_URL (and keep existing vars)
if [ -f "$ENV_FILE" ]; then
  # update existing or add
  if grep -q '^WEBHOOK_PUBLIC_URL=' "$ENV_FILE"; then
    sed -i "s|^WEBHOOK_PUBLIC_URL=.*|WEBHOOK_PUBLIC_URL=${WEBHOOK_URL}|" "$ENV_FILE"
    log "Updated WEBHOOK_PUBLIC_URL in $ENV_FILE"
  else
    echo "WEBHOOK_PUBLIC_URL=${WEBHOOK_URL}" >> "$ENV_FILE"
    log "Added WEBHOOK_PUBLIC_URL to $ENV_FILE"
  fi
else
  # create new with placeholder keys (user should fill these later)
  cat > "$ENV_FILE" <<EOF
# Payment bot environment file
# Fill these values before starting the bot (API_ID, API_HASH, BOT_TOKEN, RAZORPAY_* etc).
WEBHOOK_PUBLIC_URL=${WEBHOOK_URL}
# Example:
# API_ID=...
# API_HASH=...
# BOT_TOKEN=...
# RAZORPAY_KEY_ID=...
# RAZORPAY_KEY_SECRET=...
# RAZORPAY_WEBHOOK_SECRET=...
# OWNER_ID=...
EOF
  chmod 600 "$ENV_FILE"
  log "Created $ENV_FILE with WEBHOOK_PUBLIC_URL. Fill credentials before starting the bot."
fi

# 5) Start bot.py only if required credentials appear in env file
# Minimal check - BOT_TOKEN and API_ID/API_HASH present
HAS_TOKEN=$(grep -E '^BOT_TOKEN=' "$ENV_FILE" || true)
HAS_APIID=$(grep -E '^API_ID=' "$ENV_FILE" || true)
HAS_APIHASH=$(grep -E '^API_HASH=' "$ENV_FILE" || true)

if [ -z "$HAS_TOKEN" ] || [ -z "$HAS_APIID" ] || [ -z "$HAS_APIHASH" ]; then
  log "Bot credentials not found in $ENV_FILE. Please edit the file and add BOT_TOKEN, API_ID and API_HASH. Bot will not auto-start."
  log "You can start bot manually after updating env: source venv/bin/activate && python3 bot.py"
  exit 0
fi

# 6) Start bot.py in background (if not already running)
if pgrep -f "python.*bot.py" >/dev/null 2>&1; then
  log "bot.py already running (skipping start)."
else
  log "Starting bot.py (background). Output -> $BOT_LOG"
  nohup bash -lc "source '$ACTIVATE' && env $(cat $ENV_FILE | xargs) python3 bot.py" > "$BOT_LOG" 2>&1 &
  sleep 1
fi

log "All done. Check logs:"
log " webhook -> $WEBHOOK_LOG"
log " cloudflared -> $CLOUD_LOG"
log " bot -> $BOT_LOG"

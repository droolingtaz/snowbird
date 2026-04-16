#!/usr/bin/env bash
# One-time VM bootstrap for the Snowbird deploy target.
# Run this ONCE on your lab VM as a user with sudo, e.g.:
#   curl -fsSL https://raw.githubusercontent.com/<you>/snowbird/main/scripts/bootstrap_vm.sh | bash
# or scp the file over and run it.
#
# What this does:
#   1. Installs Docker Engine + Compose v2
#   2. Creates /opt/snowbird with correct ownership
#   3. Drops a starter .env, docker-compose.prod.yml, and smoke_test.sh
#   4. Prints the SSH public key you should add to GitHub as a deploy secret
#
# Idempotent — safe to re-run.

set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-$USER}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/snowbird}"

log() { echo "[bootstrap] $*"; }

if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# ---- 1. Docker ----------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    log "Installing Docker Engine..."
    $SUDO apt-get update
    $SUDO apt-get install -y ca-certificates curl gnupg
    $SUDO install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    $SUDO chmod a+r /etc/apt/keyrings/docker.gpg
    . /etc/os-release
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
      | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
    $SUDO apt-get update
    $SUDO apt-get install -y docker-ce docker-ce-cli containerd.io \
                              docker-buildx-plugin docker-compose-plugin
    $SUDO usermod -aG docker "$DEPLOY_USER"
    log "Docker installed. Log out and back in for group change to take effect."
else
    log "Docker already installed: $(docker --version)"
fi

# ---- 2. Deploy dir ------------------------------------------------------
log "Creating $DEPLOY_DIR ..."
$SUDO mkdir -p "$DEPLOY_DIR/scripts"
$SUDO chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_DIR"

# ---- 3. Starter .env ----------------------------------------------------
if [ ! -f "$DEPLOY_DIR/.env" ]; then
    log "Generating starter .env (SECRET_KEY generated, edit POSTGRES_PASSWORD) ..."
    SECRET=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || openssl rand -base64 32)
    cat > "$DEPLOY_DIR/.env" <<EOF
SECRET_KEY=$SECRET
POSTGRES_USER=snowbird
POSTGRES_PASSWORD=$(openssl rand -base64 24)
POSTGRES_DB=snowbird
FRONTEND_PORT=8080
# These two are written by the CD workflow; safe defaults here.
IMAGE_NAMESPACE=CHANGE_ME_TO_GITHUB_ORG_OR_USER
IMAGE_TAG=latest
EOF
    chmod 600 "$DEPLOY_DIR/.env"
    log "Wrote $DEPLOY_DIR/.env (mode 600). Edit IMAGE_NAMESPACE before first deploy."
fi

# ---- 4. SSH deploy key hint --------------------------------------------
SSH_DIR="/home/$DEPLOY_USER/.ssh"
[ -d "$SSH_DIR" ] || { mkdir -p "$SSH_DIR"; chmod 700 "$SSH_DIR"; }
if [ ! -f "$SSH_DIR/snowbird_deploy" ]; then
    log "Generating dedicated SSH deploy key ..."
    ssh-keygen -t ed25519 -N "" -C "snowbird-deploy" -f "$SSH_DIR/snowbird_deploy"
    cat "$SSH_DIR/snowbird_deploy.pub" >> "$SSH_DIR/authorized_keys"
    chmod 600 "$SSH_DIR/authorized_keys"
fi

log "------------------------------------------------------------"
log "Bootstrap complete."
log ""
log "Next steps:"
log "  1. Edit $DEPLOY_DIR/.env and set IMAGE_NAMESPACE to your GitHub org/user."
log "  2. Copy docker-compose.prod.yml and scripts/smoke_test.sh from the repo into $DEPLOY_DIR/."
log "  3. Add the following GitHub Actions secrets to your repo:"
log "       VM_HOST           = this VM's hostname/IP"
log "       VM_USER           = $DEPLOY_USER"
log "       VM_SSH_PORT       = (optional, default 22)"
log "       VM_SSH_KEY        = contents of $SSH_DIR/snowbird_deploy (the PRIVATE key)"
log "       GHCR_READ_TOKEN   = a GitHub PAT with read:packages scope"
log "       SMOKE_ALPACA_KEY  = (optional) Alpaca PAPER API key for post-deploy smoke"
log "       SMOKE_ALPACA_SECRET = (optional) paired secret"
log ""
log "Private deploy key (add as VM_SSH_KEY secret):"
log "-------------------- BEGIN (copy the whole block incl. header/footer) --------------------"
cat "$SSH_DIR/snowbird_deploy"
log "-------------------- END --------------------"

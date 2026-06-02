#!/usr/bin/env bash
set -euo pipefail

DEFAULT_USER="${SUDO_USER:-${USER:-root}}"
APP_USER="${APP_USER:-$DEFAULT_USER}"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  echo "[WARN] APP_USER=$APP_USER does not exist. Fallback to root"
  APP_USER="root"
fi

if [ "$APP_USER" = "root" ]; then
  APP_HOME="/root"
else
  APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
  [ -n "$APP_HOME" ] || APP_HOME="/home/$APP_USER"
fi

APP_DIR="$APP_HOME/pi2w"
REC_DIR="$APP_HOME/rec"
VENV_DIR="$APP_DIR/.venv"

SUDO="sudo"
if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
fi

run_root() {
  if [ -n "$SUDO" ]; then
    $SUDO "$@"
  else
    "$@"
  fi
}

run_app_user() {
  if [ "$APP_USER" = "root" ]; then
    "$@"
  else
    run_root -u "$APP_USER" "$@"
  fi
}

echo "[INFO] APP_USER=$APP_USER APP_HOME=$APP_HOME"

run_root pacman -Syu --noconfirm --needed python python-pip ffmpeg alsa-utils networkmanager wpa_supplicant iw

run_root install -d -m 755 -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
run_root install -d -m 755 -o "$APP_USER" -g "$APP_USER" "$REC_DIR"

run_root cp -f pi2w_client.py "$APP_DIR/pi2w_client.py"
run_root cp -f requirements.txt "$APP_DIR/requirements.txt"
run_root cp -f pi_identity_config.json "$REC_DIR/pi_identity_config.json"
run_root cp -f public.key "$APP_HOME/public.key"
run_root chown "$APP_USER:$APP_USER" "$APP_DIR/pi2w_client.py" "$APP_DIR/requirements.txt" "$REC_DIR/pi_identity_config.json" "$APP_HOME/public.key"

run_app_user python3 -m venv "$VENV_DIR"
run_app_user "$VENV_DIR/bin/pip" install --upgrade pip
run_app_user "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"

run_root systemctl enable --now NetworkManager
run_root systemctl daemon-reload

run_root cp -f pi2w_client.service /etc/systemd/system/pi2w_client.service
run_root sed -i "s|^User=.*|User=$APP_USER|" /etc/systemd/system/pi2w_client.service
run_root sed -i "s|^WorkingDirectory=.*|WorkingDirectory=$APP_DIR|" /etc/systemd/system/pi2w_client.service
run_root sed -i "s|^ExecStart=.*|ExecStart=$VENV_DIR/bin/python $APP_DIR/pi2w_client.py|" /etc/systemd/system/pi2w_client.service

run_root systemctl enable --now pi2w_client.service

echo "[DONE] Install finished on Arch"
echo "[INFO] Service: sudo systemctl status pi2w_client.service --no-pager -l"
echo "[INFO] Logs: sudo journalctl -u pi2w_client.service -f"
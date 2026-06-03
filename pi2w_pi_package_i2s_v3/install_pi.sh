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
CFG_PATH="$REC_DIR/pi_identity_config.json"

run_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

run_app_user() {
  if [ "$APP_USER" = "root" ]; then
    run_root "$@"
  else
    if command -v sudo >/dev/null 2>&1; then
      sudo -H -u "$APP_USER" "$@"
    else
      run_root runuser -u "$APP_USER" -- "$@"
    fi
  fi
}

echo "[INFO] APP_USER=$APP_USER"
echo "[INFO] APP_HOME=$APP_HOME"

run_root apt update
run_root apt install -y \
  sudo \
  python3 \
  python3-venv \
  python3-pip \
  ffmpeg \
  alsa-utils \
  network-manager \
  wpasupplicant \
  iw \
  rfkill \
  iproute2

run_root install -d -m 755 -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
run_root install -d -m 755 -o "$APP_USER" -g "$APP_USER" "$REC_DIR"

run_root cp -f pi2w_client.py "$APP_DIR/pi2w_client.py"
run_root cp -f requirements.txt "$APP_DIR/requirements.txt"
run_root cp -f pi_identity_config.json "$CFG_PATH"
run_root cp -f public.key "$APP_HOME/public.key"

run_root chown "$APP_USER:$APP_USER" \
  "$APP_DIR/pi2w_client.py" \
  "$APP_DIR/requirements.txt" \
  "$CFG_PATH" \
  "$APP_HOME/public.key"

run_app_user python3 -m venv "$VENV_DIR"
run_app_user "$VENV_DIR/bin/pip" install --upgrade pip
run_app_user "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"

run_root systemctl enable --now NetworkManager
run_root systemctl enable --now wpa_supplicant || true

run_root install -d -m 755 /etc/NetworkManager/conf.d

run_root bash -c 'cat > /etc/NetworkManager/conf.d/10-ifupdown-managed.conf <<"EOF"
[ifupdown]
managed=true
EOF'

for f in /etc/NetworkManager/NetworkManager.conf /etc/NetworkManager/conf.d/*.conf; do
  [ -f "$f" ] && run_root sed -i '/unmanaged-devices/d' "$f"
done

if [ -d /etc/netplan ]; then
  run_root bash -c 'cat > /etc/netplan/01-network-manager-all.yaml <<"EOF"
network:
  version: 2
  renderer: NetworkManager
EOF'

  run_root chown root:root /etc/netplan/01-network-manager-all.yaml
  run_root chmod 600 /etc/netplan/01-network-manager-all.yaml

  if [ -f /lib/netplan/00-network-manager-all.yaml ]; then
    run_root chown root:root /lib/netplan/00-network-manager-all.yaml || true
    run_root chmod 600 /lib/netplan/00-network-manager-all.yaml || true
  fi

  run_root netplan generate || true
  run_root netplan apply || true
fi

if [ -f /etc/network/interfaces ]; then
  run_root cp /etc/network/interfaces "/etc/network/interfaces.bak.$(date +%s)"
  run_root bash -c 'printf "auto lo\niface lo inet loopback\n" > /etc/network/interfaces'
fi

run_root systemctl restart NetworkManager
sleep 3

WIFI_IFACE="$(run_root nmcli -t -f DEVICE,TYPE device status | awk -F: '$2=="wifi"{print $1; exit}')"

if [ -n "${WIFI_IFACE:-}" ]; then
  echo "[INFO] WiFi interface: $WIFI_IFACE"

  run_root nmcli dev set "$WIFI_IFACE" managed yes || true
  run_root rfkill unblock wifi || true
  run_root ip link set "$WIFI_IFACE" up || true
else
  echo "[WARN] No WiFi interface found"
fi

SSID="$(python3 -c 'import json; from pathlib import Path; p=Path("'"$CFG_PATH"'"); c=json.loads(p.read_text(encoding="utf-8-sig")); print(c.get("cau_hinh_ghi_am",{}).get("ssid_upload",""))')"
PASS="$(python3 -c 'import json; from pathlib import Path; p=Path("'"$CFG_PATH"'"); c=json.loads(p.read_text(encoding="utf-8-sig")); print(c.get("cau_hinh_ghi_am",{}).get("wifi_password",""))')"

if [ -n "${WIFI_IFACE:-}" ] && [ -n "$SSID" ]; then
  echo "[INFO] Creating hidden WiFi connection: phantom_hidden"

  for u in $(run_root nmcli -t -f UUID,NAME con show | awk -F: '$2=="phantom_hidden"{print $1}'); do
    run_root nmcli con delete "$u" || true
  done

  run_root nmcli con add type wifi ifname "$WIFI_IFACE" con-name phantom_hidden ssid "$SSID"

  run_root nmcli con mod phantom_hidden 802-11-wireless.hidden yes

  if [ -n "$PASS" ]; then
    run_root nmcli con mod phantom_hidden wifi-sec.key-mgmt wpa-psk
    run_root nmcli con mod phantom_hidden wifi-sec.psk "$PASS"
  fi

  run_root nmcli con mod phantom_hidden connection.autoconnect yes
  run_root nmcli con mod phantom_hidden connection.autoconnect-priority 999
  run_root nmcli con mod phantom_hidden connection.autoconnect-retries -1
  run_root nmcli con mod phantom_hidden ipv4.method auto ipv4.addresses "" ipv4.gateway ""

  echo "[INFO] phantom_hidden created successfully"
else
  echo "[WARN] Skip phantom_hidden: missing WIFI_IFACE or SSID"
fi

if [ -n "${WIFI_IFACE:-}" ]; then
  echo "[INFO] Creating hidden WiFi connection: phantom_mgmt"

  for u in $(run_root nmcli -t -f UUID,NAME con show | awk -F: '$2=="phantom_mgmt"{print $1}'); do
    run_root nmcli con delete "$u" || true
  done

  run_root nmcli con add type wifi ifname "$WIFI_IFACE" con-name phantom_mgmt ssid "7068616e746f6d303030303030300001"
  run_root nmcli con mod phantom_mgmt 802-11-wireless.hidden yes
  run_root nmcli con mod phantom_mgmt wifi-sec.key-mgmt wpa-psk
  run_root nmcli con mod phantom_mgmt wifi-sec.psk "12345678"
  run_root nmcli con mod phantom_mgmt connection.autoconnect yes
  run_root nmcli con mod phantom_mgmt connection.autoconnect-priority 998
  run_root nmcli con mod phantom_mgmt connection.autoconnect-retries -1
  run_root nmcli con mod phantom_mgmt ipv4.method auto ipv4.addresses "" ipv4.gateway ""

  echo "[INFO] phantom_mgmt created successfully"
else
  echo "[WARN] Skip phantom_mgmt: missing WIFI_IFACE"
fi

run_root cp -f pi2w_client.service /etc/systemd/system/pi2w_client.service

run_root sed -i "s|^User=.*|User=$APP_USER|" /etc/systemd/system/pi2w_client.service
run_root sed -i "s|^WorkingDirectory=.*|WorkingDirectory=$APP_DIR|" /etc/systemd/system/pi2w_client.service
run_root sed -i "s|^ExecStart=.*|ExecStart=$VENV_DIR/bin/python $APP_DIR/pi2w_client.py|" /etc/systemd/system/pi2w_client.service

run_root systemctl daemon-reload
run_root systemctl enable --now pi2w_client.service

echo "[DONE] Install finished"
echo "[INFO] Config: $CFG_PATH"
echo "[INFO] Service:"
echo "       sudo systemctl status pi2w_client.service --no-pager -l"
echo "[INFO] Logs:"
echo "       sudo journalctl -u pi2w_client.service -f"
echo "[INFO] Check NetworkManager:"
echo "       nmcli device status"
echo "       nmcli connection show"
echo "[WARN] If you force hidden Wi-Fi now, SSH may disconnect:"
echo "       sudo nmcli -w 20 con up phantom_hidden ifname ${WIFI_IFACE:-wlan0}"
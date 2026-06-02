# HUONG DAN CAI DAT PI2W CLIENT (PI ZERO 2 W)

## Dieu kien can
- Raspberry Pi Zero 2 W
- OS: Raspberry Pi OS
- File `pi2w_pi_package_i2s_v3.zip` da co trong home
- Co quyen sudo

---

## Buoc 1: Giai nen package

```bash
cd ~
rm -rf pi2w_pi_package
unzip -o pi2w_pi_package_i2s_v3.zip -d pi2w_pi_package
cd pi2w_pi_package
sed -i '1s/^\xEF\xBB\xBF//' install_pi.sh
sed -i 's/\r$//' install_pi.sh pi2w_client.service
chmod +x install_pi.sh
```

---

## Buoc 2: Chay cai dat

```bash
APP_USER="$USER" ./install_pi.sh
```

> Neu dang SSH bang root: `APP_USER=pizero21 ./install_pi.sh` (thay `pizero21` bang user thuc te)

Script tu dong:
- Cai ffmpeg, alsa-utils, python3, NetworkManager
- Tao venv va cai pip packages
- Tao profile WiFi `phantom_hidden` (upload) va `phantom_mgmt` (quan ly)
- Cai va bat service `pi2w_client.service`

---

## Buoc 3: Bat I2S microphone (Google VoiceHAT)

```bash
CFG_BOOT="/boot/firmware/config.txt"
[ -f "$CFG_BOOT" ] || CFG_BOOT="/boot/config.txt"

grep -q '^dtparam=i2s=on' "$CFG_BOOT" || echo 'dtparam=i2s=on' | sudo tee -a "$CFG_BOOT"
grep -q '^dtoverlay=googlevoicehat-soundcard' "$CFG_BOOT" || echo 'dtoverlay=googlevoicehat-soundcard' | sudo tee -a "$CFG_BOOT"
sudo sed -i 's/^dtparam=audio=on/#dtparam=audio=on/' "$CFG_BOOT" || true
```

---

## Buoc 4: Reboot

```bash
sudo reboot
```

SSH se ngat. Doi Pi khoi dong xong roi dang nhap lai.

---

## Buoc 5: Kiem tra mic sau reboot

```bash
arecord -l
```

Tim dong co dang `card X: sndrpigooglevoi ...` — ghi nho so X.

```bash
# Thay X bang so card tim duoc o tren (thuong la 1)
arecord -D plughw:1,0 -c 2 -r 48000 -f S32_LE -d 3 /tmp/test.wav
ls -lh /tmp/test.wav
```

File > 0 byte la mic hoat dong.

---

## Buoc 6: Cap quyen nmcli cho user

```bash
sudo usermod -aG netdev "$USER"
```

```bash
sudo bash -c 'cat > /etc/polkit-1/rules.d/50-nmcli-user.rules <<EOF
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager.") === 0 &&
        subject.user === "pizero21") {
        return polkit.Result.YES;
    }
});
EOF'
```

> Thay `pizero21` bang ten user thuc te.

```bash
sudo systemctl restart polkit
sudo systemctl restart pi2w_client
```

---

## Buoc 7: Cap nhat config

```bash
nano ~/rec/pi_identity_config.json
```

Mau config chuan cho Google VoiceHAT:

```json
{
  "dinh_danh": {
    "ma_id": "BN-0001",
    "ho_ten": "Nguyen Van A",
    "nam_sinh": 1990,
    "dia_chi": "Ha Noi",
    "ngay_cap_dinh_danh": "2026-06-01"
  },
  "cau_hinh_ghi_am": {
    "kieu_ghi_am": "continuous",
    "thoi_luong_ghi_am_phut": 1,
    "chu_ky_quet_wifi_phut": 5,
    "ssid_upload": "7068616e746f6d303030303030300002",
    "wifi_password": "12345678",
    "uu_tien_wifi_an_lap_tuc": true,
    "mic_loai": "i2s",
    "mic_i2s_device": "plughw:1,0",
    "mic_i2s_channels": 2,
    "mic_i2s_rate": 48000,
    "mic_i2s_format": "S32_LE",
    "duong_dan_public_key": "public.key"
  },
  "updated_at": "2026-06-01T00:00:00+07:00"
}
```

> `mic_i2s_device`: dung `plughw:X,0` voi X la so card tu `arecord -l`
> Service tu detect thay doi config, khong can restart.

---

## Buoc 8: Kiem tra service

```bash
sudo systemctl status pi2w_client.service --no-pager -l
journalctl -u pi2w_client.service -f
```

Log tot can thay:
- `[REC] OK ...`
- `[OPUS] OK ...`
- `[PHTM3L1] OK ...`
- `[MGMT] notified registry ...`

---

## Hanh vi WiFi

| Priority | Profile | SSID | Chuc nang |
|----------|---------|------|-----------|
| 999 | `phantom_mgmt` | `...0001` | Quan ly file tu PC app (WiFi hien) |
| 998 | `phantom_hidden` | `...0002` | Upload file .bin (WiFi an) |
| thap | WiFi khac | - | Internet binh thuong |

- Khi ket noi `...0001`: Pi gui thong tin thiet bi len PC app (port 8766), bat HTTP server quan ly file (port 8765).
- Khi ket noi `...0002`: Pi upload het file .bin roi ngat ket noi, cho 5 phut moi thu lai.
- Khi dang o `...0001`: khong tu chuyen sang `...0002`.

Kiem tra priority:
```bash
nmcli connection show phantom_mgmt | grep autoconnect-priority
nmcli connection show phantom_hidden | grep autoconnect-priority
```

---

## Loi thuong gap

**`audio open error: No such file or directory`**
```bash
arecord -l
# Doi mic_i2s_device trong config sang plughw:X,0 dung voi so card
```

**`Cannot read key file`**
```bash
ls -l ~/public.key
cp -f ~/pi2w_pi_package/public.key ~/public.key
sudo systemctl restart pi2w_client
```

**`Not authorized to control networking`**
- Chay lai Buoc 6.

**`There are N other connections with the name phantom_hidden`**
```bash
nmcli -t -f NAME,UUID connection show | grep "^phantom_hidden:" | cut -d: -f2 | xargs -I{} sudo nmcli connection delete {}
nmcli -t -f NAME,UUID connection show | grep "^phantom_mgmt:" | cut -d: -f2 | xargs -I{} sudo nmcli connection delete {}
sudo systemctl restart pi2w_client
```

**`wlan0 unmanaged`**
```bash
APP_USER="$USER" ~/pi2w_pi_package/install_pi.sh
```

---

## Kiem tra nhanh

```bash
nmcli -t -f DEVICE,TYPE,STATE,CONNECTION dev
arecord -l
systemctl is-active pi2w_client.service
journalctl -u pi2w_client.service -n 50 --no-pager
```


Script tu dong:
- Cai ffmpeg, alsa-utils, python3, NetworkManager
- Tao venv va cai pip packages
- Tao profile WiFi `phantom_hidden` (upload) va `phantom_mgmt` (quan ly)
- Cai va bat service `pi2w_client.service`

---

## Buoc 3: Bat I2S microphone (Google VoiceHAT)

```bash
CFG_BOOT="/boot/firmware/config.txt"
[ -f "$CFG_BOOT" ] || CFG_BOOT="/boot/config.txt"

grep -q '^dtparam=i2s=on' "$CFG_BOOT" || echo 'dtparam=i2s=on' | sudo tee -a "$CFG_BOOT"
grep -q '^dtoverlay=googlevoicehat-soundcard' "$CFG_BOOT" || echo 'dtoverlay=googlevoicehat-soundcard' | sudo tee -a "$CFG_BOOT"
sudo sed -i 's/^dtparam=audio=on/#dtparam=audio=on/' "$CFG_BOOT" || true
```

---

## Buoc 4: Reboot

```bash
sudo reboot
```

SSH se ngat. Doi Pi khoi dong xong roi dang nhap lai.

---

## Buoc 5: Kiem tra mic sau reboot

```bash
arecord -l
```

Tim dong co dang `card X: sndrpigooglevoi ...` — ghi nho so X.

```bash
# Thay X bang so card tim duoc o tren (thuong la 1)
arecord -D plughw:1,0 -c 2 -r 48000 -f S32_LE -d 3 /tmp/test.wav
ls -lh /tmp/test.wav
```

File > 0 byte la mic hoat dong.

---

## Buoc 6: Cap quyen nmcli cho user (neu service chay bang non-root)

```bash
sudo usermod -aG netdev "$USER"
```

```bash
sudo bash -c 'cat > /etc/polkit-1/rules.d/50-nmcli-user.rules <<EOF
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager.") === 0 &&
        subject.user === "pizero21") {
        return polkit.Result.YES;
    }
});
EOF'
```

> Thay `pizero21` bang ten user thuc te.

```bash
sudo systemctl restart polkit
sudo systemctl restart pi2w_client
```

---

## Buoc 7: Cap nhat config

Config nam tai: `~/rec/pi_identity_config.json`

```bash
nano ~/rec/pi_identity_config.json
```

Mau config chuan cho Google VoiceHAT:

```json
{
  "dinh_danh": {
    "ma_id": "BN-0001",
    "ho_ten": "Nguyen Van A",
    "nam_sinh": 1990,
    "dia_chi": "Ha Noi",
    "ngay_cap_dinh_danh": "2026-06-01"
  },
  "cau_hinh_ghi_am": {
    "kieu_ghi_am": "continuous",
    "thoi_luong_ghi_am_phut": 1,
    "chu_ky_quet_wifi_phut": 5,
    "ssid_upload": "7068616e746f6d303030303030300002",
    "wifi_password": "12345678",
    "uu_tien_wifi_an_lap_tuc": true,
    "mic_loai": "i2s",
    "mic_i2s_device": "plughw:1,0",
    "mic_i2s_channels": 2,
    "mic_i2s_rate": 48000,
    "mic_i2s_format": "S32_LE",
    "duong_dan_public_key": "public.key"
  },
  "updated_at": "2026-06-01T00:00:00+07:00"
}
```

> `mic_i2s_device`: dung `plughw:X,0` voi X la so card tu `arecord -l`
> Service tu detect thay doi config, khong can restart.

---

## Buoc 8: Kiem tra service

```bash
sudo systemctl status pi2w_client.service --no-pager -l
journalctl -u pi2w_client.service -f
```

Log tot can thay:
- `[REC] OK ...`
- `[OPUS] OK ...`
- `[PHTM3L1] OK ...`
- `[MGMT] notified registry ...`

---

## Hanh vi WiFi

| Priority | Profile | SSID | Chuc nang |
|----------|---------|------|-----------|
| 999 | `phantom_mgmt` | `...0001` | Quan ly file tu PC app (WiFi hien) |
| 998 | `phantom_hidden` | `...0002` | Upload file .bin (WiFi an) |
| thap | WiFi khac | - | Internet binh thuong |

- Khi ket noi `...0001`: Pi gui thong tin thiet bi len PC app (port 8766), bat HTTP server quan ly file (port 8765).
- Khi ket noi `...0002`: Pi upload het file .bin roi ngat ket noi, cho 5 phut moi thu lai.
- Khi dang o `...0001`: khong tu chuyen sang `...0002`.

Kiem tra priority:
```bash
nmcli connection show phantom_mgmt | grep autoconnect-priority
nmcli connection show phantom_hidden | grep autoconnect-priority
```

---

## Loi thuong gap

**`audio open error: No such file or directory`**
```bash
arecord -l
# Doi mic_i2s_device trong config sang plughw:X,0 dung voi so card
```

**`Cannot read key file`**
```bash
ls -l ~/public.key
cp -f ~/pi2w_pi_package/public.key ~/public.key
sudo systemctl restart pi2w_client
```

**`Not authorized to control networking`**
- Chay lai Buoc 6.

**`There are N other connections with the name phantom_hidden`**
```bash
nmcli -t -f NAME,UUID connection show | grep "^phantom_hidden:" | cut -d: -f2 | xargs -I{} sudo nmcli connection delete {}
nmcli -t -f NAME,UUID connection show | grep "^phantom_mgmt:" | cut -d: -f2 | xargs -I{} sudo nmcli connection delete {}
sudo systemctl restart pi2w_client
```

**`wlan0 unmanaged`**
```bash
APP_USER="$USER" ~/pi2w_pi_package/install_pi.sh
```

---

## Kiem tra nhanh

```bash
nmcli -t -f DEVICE,TYPE,STATE,CONNECTION dev
arecord -l
systemctl is-active pi2w_client.service
journalctl -u pi2w_client.service -n 50 --no-pager
```

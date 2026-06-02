# HUONG DAN CAI DAT PI2W CLIENT (CHI CHO RASPBERRY PI OS)

Tai lieu nay chi dung cho Raspberry Pi OS, chuan hoa theo user chay dich vu `pizero21`.

## 1) Muc tieu sau cai dat
Service se chay tai:
- `/home/pizero21/pi2w/pi2w_client.py`

Config active:
- `/home/pizero21/rec/pi_identity_config.json`

Key active:
- `/home/pizero21/public.key`

## 2) Dieu kien can
- Raspberry Pi Zero 2 W
- Raspberry Pi OS
- Co sudo
- Co file `pi2w_pi_package_i2s_v3.zip`

## 3) Giai nen package
```bash
cd ~
rm -rf pi2w_pi_package
unzip -o pi2w_pi_package_i2s_v3.zip -d pi2w_pi_package
cd ~/pi2w_pi_package/pi2w_pi_package_i2s_v3
chmod +x install_pi.sh
```

## 4) Cai dat (co dinh user pizero21)
```bash
export APP_USER=pizero21
./install_pi.sh
```

## 5) Bat I2S MEMS mic
```bash
CFG_BOOT="/boot/firmware/config.txt"
[ -f "$CFG_BOOT" ] || CFG_BOOT="/boot/config.txt"

grep -q '^dtparam=i2s=on' "$CFG_BOOT" || echo 'dtparam=i2s=on' | sudo tee -a "$CFG_BOOT"
grep -q '^dtoverlay=googlevoicehat-soundcard' "$CFG_BOOT" || echo 'dtoverlay=googlevoicehat-soundcard' | sudo tee -a "$CFG_BOOT"

# tuy chon: tat onboard audio neu can
sudo sed -i 's/^dtparam=audio=on/#dtparam=audio=on/' "$CFG_BOOT" || true
```

## 6) Reboot
```bash
sudo reboot
```

## 7) Kiem tra service dang chay dung path
```bash
sudo systemctl status pi2w_client.service --no-pager -l
sudo systemctl cat pi2w_client.service
```

Can thay:
- `User=pizero21`
- `WorkingDirectory=/home/pizero21/pi2w`
- `ExecStart=/home/pizero21/pi2w/.venv/bin/python /home/pizero21/pi2w/pi2w_client.py`

## 8) Kiem tra config active
```bash
CFG="/home/pizero21/rec/pi_identity_config.json"
KEY="/home/pizero21/public.key"
APP_MAIN="/home/pizero21/pi2w/pi2w_client.py"

ls -l "$APP_MAIN" "$CFG" "$KEY"
cat "$CFG"
```

Gia tri config can check:
- `ssid_upload`: `7068616e746f6d303030303030300002`
- `wifi_password`: `12345678`
- `uu_tien_wifi_an_lap_tuc`: `false`
- `mic_i2s_device`: thuong `hw:1,0`
- `mic_i2s_channels`, `mic_i2s_rate`, `mic_i2s_format`
- `duong_dan_public_key`: `public.key`

Sua config xong:
```bash
sudo systemctl restart pi2w_client.service
```

## 9) Kiem tra mic nhanh
```bash
arecord -l
arecord -D hw:1,0 -c 1 -r 16000 -f S32_LE -d 3 /tmp/test_i2s.wav
ls -lh /tmp/test_i2s.wav
```

## 10) Lenh debug nhanh
```bash
nmcli -t -f DEVICE,TYPE,STATE,CONNECTION dev
nmcli connection show phantom_hidden
nmcli connection show phantom_mgmt
systemctl is-active pi2w_client.service
sudo journalctl -u pi2w_client.service -n 120 --no-pager
sudo journalctl -u pi2w_client.service -f
```

## 11) Loi thuong gap
- `Cannot read key file /home/pizero21/public.key`
  - Kiem tra file key:
```bash
ls -l /home/pizero21/public.key
```

- Khong thay file upload
  - Kiem tra dung thu muc `/home/pizero21/rec`.

- `wlan0 unmanaged`
  - Chay lai:
```bash
cd ~/pi2w_pi_package/pi2w_pi_package_i2s_v3
export APP_USER=pizero21
./install_pi.sh
```

## 12) Checklist ban giao
- Service active: `systemctl is-active pi2w_client.service` = `active`
- `User=pizero21` dung trong service
- Co file:
  - `/home/pizero21/pi2w/pi2w_client.py`
  - `/home/pizero21/rec/pi_identity_config.json`
  - `/home/pizero21/public.key`
- Log co `[REC] OK`, `[OPUS] OK`, `[PHTM3L1] OK`



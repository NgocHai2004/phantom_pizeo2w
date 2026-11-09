# HUONG DAN CAI DAT PI2W CLIENT (PI ZERO 2 W)

## Dieu kien can
- Raspberry Pi Zero 2 W
- OS: Raspberry Pi OS (khuyen dung Bookworm 64-bit hoac Bullseye)
- Gói cai dat `pi2w_pi_package_i2s_v3` (dang folder hoac zip) da co tren Pi
- Co quyen sudo

```bash
sudo apt update
sudo apt install -y unzip sed bash
```

---

## Buoc 1: Chuan bi package tren Pi

Neu ban chep file `.zip` len Pi (`~/pi2w_pi_package_i2s_v3.zip`):
```bash
cd ~
unzip -o pi2w_pi_package_i2s_v3.zip
cd pi2w_pi_package_i2s_v3
chmod +x install_pi.sh
```

*(Luu y: Goi zip da duoc chuan hoa toan bo ky tu xuong dong Linux LF va quyen thuc thi).*

---

## Buoc 2: Chay cai dat tu dong

Chay script cai dat voi quyen user thuc te (vi du user `pizero24`):

```bash
APP_USER="$USER" ./install_pi.sh
```

> **Luu y:** Neu ban dang SSH bang `root`, hay truyen dung user cua may:  
> `APP_USER=pizero24 ./install_pi.sh` (thay `pizero24` bang user thuc te tren Pi cua ban).

**Script `install_pi.sh` se tu dong hoan toan:**
1. Cai cac package he thong: `ffmpeg`, `alsa-utils`, `python3`, `python3-venv`, `network-manager`, `wpasupplicant`.
2. Tao thu muc chay `~/pi2w` va thu muc luu am thanh `~/rec`.
3. Copy cac file: `pi2w_client.py`, `requirements.txt`, `pi_identity_config.json`, `public.key`, `ssid_list.bin`.
4. Tao Python venv `~/pi2w/.venv` va cai dat cac thu vien can thiet (`cryptography`, `requests`).
5. Tao 2 profile WiFi NetworkManager:
   - `phantom_mgmt` (Priority 999): de PC quan ly / doi config.
   - `phantom_hidden` (Priority 998): de upload file `.bin` sang ESP32.
6. Cap quyen Polkit cho `APP_USER` dieu khien `nmcli` ma khong can go pass sudo.
7. Tu dong bat overlay I2S microphone (`googlevoicehat-soundcard`) vao file boot `config.txt`.
8. Toi uu hoa tieu thu dien nang cho Pi Zero 2W (tat HDMI, Bluetooth, LED ACT, toi uu journald vao RAM).
9. Cai dat va kich hoat systemd service `pi2w_client.service`.

---

## Buoc 3: Kiem tra boot config I2S microphone (Tuy chon)

Microphone I2S su dung driver `googlevoicehat-soundcard`. Script `install_pi.sh` o Buoc 2 da tu dong them vao boot config.
Neu ban muon kiem tra lai:

```bash
CFG_BOOT="/boot/firmware/config.txt"
[ -f "$CFG_BOOT" ] || CFG_BOOT="/boot/config.txt"

grep 'googlevoicehat' "$CFG_BOOT"
```

---

## Buoc 4: Reboot Pi

Sau khi cau hinh xong overlay va script chay xong, reboot de kernel load driver mic va ap dung cac toi uu:

```bash
sudo reboot
```

*SSH se ngat ket noi trong khoang 30-45 giay. Doi Pi khoi dong xong roi dang nhap lai.*

---

## Buoc 5: Kiem tra microphone sau reboot

Dang nhap lai vao Pi va kiem tra soundcard:

```bash
arecord -l
```

Tim dong co soundcard dang `card X: sndrpigooglevoi ...` (thuong la card `0`).

Vi du output chuan:
```
**** List of CAPTURE Hardware Devices ****
card 0: sndrpigooglevoi [snd_rpi_googlevoicehat_soundcar], device 0: Google voiceHAT SoundCard HiFi voicehat-hifi-0
  Subdevices: 1/1
  Subdevice #0: subdevice #0
```

Thu ghi am thu 3 giay:
```bash
# Neu card la 0, dung plughw:0,0 hoac hw:0,0:
arecord -D plughw:0,0 -c 2 -r 48000 -f S32_LE -d 3 /tmp/test.wav
ls -lh /tmp/test.wav
```

> **Ket qua dat:** File `/tmp/test.wav` co dung luong > 0 byte la mic da nhan va ghi tot.

---

## Buoc 6: Kiem tra quyen nmcli & Polkit

Script `install_pi.sh` da tu dong tao rule Polkit. Ban co the kiem tra lai:

```bash
cat /etc/polkit-1/rules.d/50-nmcli-user.rules
```

Phai thay `subject.user === "<user_cua_ban>"` (vi du `pizero24`).

Neu truoc do ban lo chay script bang root ma chua truyen `APP_USER`, ban co the chay lai de cap dung user:
```bash
sudo usermod -aG netdev "$USER"
sudo tee /etc/polkit-1/rules.d/50-nmcli-user.rules >/dev/null <<EOF
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager.") === 0 &&
        subject.user === "$USER") {
        return polkit.Result.YES;
    }
});
EOF
sudo systemctl restart polkit
sudo systemctl restart pi2w_client
```

---

## Buoc 7: Kiem tra & Cap nhat config thiet bi

File config thuc te nam tai: `~/rec/pi_identity_config.json`

```bash
nano ~/rec/pi_identity_config.json
```

Mau config chuan cho ban **v3** (chu y dung dung SSID & Hash cua phan mem hien tai):

```json
{
  "dinh_danh": {
    "ma_id": "BN-0001",
    "ho_ten": "Nguyen Van A",
    "nam_sinh": 1990,
    "dia_chi": "Ha Noi",
    "ngay_cap_dinh_danh": "2026-06-01",
    "ten_thiet_bi": "Pi Zero 2W",
    "id_thiet_bi": "DEVICE-0001",
    "dia_chi_thiet_bi": "Ha Noi"
  },
  "cau_hinh_ghi_am": {
    "kieu_ghi_am": "continuous",
    "thoi_luong_ghi_am_phut": 1,
    "chu_ky_quet_wifi_phut": 1,
    "ssid_upload": "1A3bcba8b69c7aea0c5942b5ce87f102",
    "wifi_password": "d1b07167d06adf161a21d4096041d40b",
    "uu_tien_wifi_an_lap_tuc": true,
    "mic_loai": "i2s",
    "mic_i2s_device": "plughw:0,0",
    "mic_i2s_channels": 2,
    "mic_i2s_rate": 48000,
    "mic_i2s_format": "S32_LE",
    "duong_dan_public_key": "public.key"
  },
  "updated_at": "2026-06-01T00:00:00+07:00"
}
```

> **Luu y quan trong:**
> - `ssid_upload` va `wifi_password`: Mac dinh la chuoi hash 32-ky tu tren de ket noi voi bo phat ESP32 (R3b_S3). Khong sua thanh `7068616e746f6d...` neu ESP32 dang chay ban moi.
> - `mic_i2s_device`: Dung `plughw:0,0` hoac `hw:0,0` tuy theo so card tu lenh `arecord -l`.
> - Service tu dong hot-reload khi file JSON thay doi, khong can restart service bang tay.

---

## Buoc 8: Kiem tra hoat dong cua Service

Kiem tra trang thai service:
```bash
sudo systemctl status pi2w_client.service --no-pager -l
```

Xem log thoi gian thuc:
```bash
journalctl -u pi2w_client.service -f
```

**Dau hieu service chay tot:**
- `[PI2W] client started`
- `[REC] OK: ... -> ...wav` (Mic bat dau thu am)
- `[OPUS] OK: ...` (Nen WAV thanh Opus bitrate tiet kiem)
- `[PHTM3L1] OK` hoac `[PHTM3L2] OK` (Ma hoa 3 lop thanh cong ra file `.bin`)
- `[MGMT] file server started on port 8765` (San sang de PC quan ly)
- `[MGMT] notify device connection: ip=...` (Khi ket noi duoc vao WiFi PC)

Kiem tra danh sach file da ghi duoc trong thu muc:
```bash
ls -lh ~/rec/
```

---

## Thong tin mang WiFi & Co che chuyen mang

| Priority | Profile | SSID | Mat khau | Muc dich |
|----------|---------|------|----------|----------|
| **999** (Cao nhat) | `phantom_mgmt` | `1A00a60d349d091982c62e3b7561c38f` | `afd4fa706f49d71cc98d2a7a87284a7a` | Ket noi ve PC App Desktop de xem/tai/xoa file (Port HTTP: 8765) |
| **998** | `phantom_hidden` | `1A3bcba8b69c7aea0c5942b5ce87f102` | `d1b07167d06adf161a21d4096041d40b` | Ket noi vao ESP32 de tu dong upload cac file `.bin` |
| Thap hon | WiFi khac | - | - | WiFi truy cap Internet thong thuong |

- **Khi PC bat Hotspot MGMT:** Pi se uu tien nhay sang `phantom_mgmt` (priority 999), dong thoi mo HTTP server tai port `8765` de Desktop App lay file va doi config.
- **Khi ESP32 bat WiFi an:** Pi ket noi vao `phantom_hidden`, upload toan bo file `.bin` sang ESP32 (dia chi `10.42.0.1:8765/api/upload`), upload xong se tu dong ngat ket noi.

Kiem tra priority thuc te tren Pi:
```bash
nmcli connection show phantom_mgmt | grep autoconnect-priority
nmcli connection show phantom_hidden | grep autoconnect-priority
```

---

## Ket noi quan ly truc tiep qua day USB

Neu ban dang cam day micro-USB tu Pi vao PC:
1. **Qua USB Ethernet Gadget (RNDIS / CDC-ECM):**
   - Pi se nhan dia chi IP mang (thuong la `192.168.7.2`).
   - Ban co the SSH truc tiep: `ssh pizero24@192.168.7.2`.
   - Desktop App hoac trinh duyet co the truy cap truc tiep vao `http://192.168.7.2:8765/api/config` ma khong can qua WiFi.
2. **Qua Phantom Serial GUI (`phantom_serial_gui.py`):**
   - App giao dien PC ho tro giao tiep serial qua day USB (COM port).
   - Neu ban dung Desktop App quan ly qua IP / WiFi MGMT, ban co the su dung HTTP truc tiep qua port `8765` rat tien loi va on dinh.

---

## Cac loi thuong gap & cach xu ly nhanh

**1. `audio open error: No such file or directory`**
```bash
arecord -l
# Kiem tra so card. Neu card la 1, sua mic_i2s_device trong ~/rec/pi_identity_config.json thanh "plughw:1,0"
```

**2. `Cannot read key file`**
```bash
ls -l ~/public.key
# Neu chua co:
cp -f ~/pi2w_pi_package/public.key ~/public.key
sudo systemctl restart pi2w_client
```

**3. `Not authorized to control networking`**
Chay lai Buoc 6 de tao rule Polkit cap quyen cho user.

**4. `There are N other connections with the name phantom_hidden`**
Xoa cac ket noi cu bi trung:
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
systemctl is-active pi2w_client.service
journalctl -u pi2w_client.service -n 30 --no-pager
```

---

## Ket noi qua day USB (CDC-ACM Serial)

Cho phep quan ly Pi tu PC bang day USB data, khong can WiFi.
PC se nhin thay Pi nhu 1 COM port ao (CDC-ACM).

### Buoc 1: Bat USB gadget tren Pi

Them vao `/boot/firmware/config.txt` (cuoi file):
```bash
CFG_BOOT="/boot/firmware/config.txt"
[ -f "$CFG_BOOT" ] || CFG_BOOT="/boot/config.txt"

grep -q 'dtoverlay=dwc2' "$CFG_BOOT" || \
  echo -e '\n# USB gadget CDC-ACM\ndtoverlay=dwc2,dr_mode=peripheral' | sudo tee -a "$CFG_BOOT"
```

Them vao `/boot/firmware/cmdline.txt` (them vao CUOI DONG, khong xuong dong moi):
```bash
CMDLINE="/boot/firmware/cmdline.txt"
[ -f "$CMDLINE" ] || CMDLINE="/boot/cmdline.txt"

grep -q 'modules-load=dwc2,g_serial' "$CMDLINE" || \
  sudo sed -i 's/$/ modules-load=dwc2,g_serial/' "$CMDLINE"
```

Reboot:
```bash
  sudo reboot
```

### Buoc 2: Kiem tra Pi da co /dev/ttyGS0

```bash
ls /dev/ttyGS*
# Phai thay: /dev/ttyGS0

lsmod | grep g_serial
# Phai thay: g_serial   16384  0
```

Kiem tra service da mo serial worker:
```bash
journalctl -u pi2w_client.service -n 30 --no-pager | grep SERIAL
# Phai thay dong: [SERIAL] opened /dev/ttyGS0
```

### Buoc 3: Cai driver tren Windows

Sau khi cam day USB data vao PC:

1. Mo **Device Manager**
2. Tim thiet bi co dau cham than (`USB Serial Device` hoac `CDC Serial`)
3. Neu Windows tu nhan duoc COM port thi qua buoc 4
4. Neu bao loi driver:
   - Click phai -> **Update driver** -> **Browse my computer** -> **Let me pick**
   - Chon **Ports (COM & LPT)** -> **Microsoft** -> **USB Serial Device**

> Windows 10/11 thuong tu nhan CDC-ACM, khong can cai them.

### Buoc 4: Mo Phantom Serial Manager tren PC

```bash
python pi2w_pi_package_i2s_v3\phantom_serial_gui.py
```

1. Chon COM port vua xuat hien trong dropdown (vi du COM9, COM10...)
2. Baud: **115200**
3. Nhan **Connect**
4. Nhan **Tai thong tin** de kiem tra ket noi

### Luu y quan trong

- Phai cam **day USB data** (khong phai day sac) vao cong **USB** cua Pi Zero (khong phai PWR).
- Pi Zero 2W: cong micro-USB **giua** la USB OTG, cong **ben trai** la PWR.
- Ca WiFi MGMT va USB serial deu hoat dong dong thoi — co the dung song song.
- COM port co the thay doi moi lan cam lai, kiem tra Device Manager neu Connect that bai.

### Loi thuong gap khi dung USB

**`A device attached to the system is not functioning` (Error 31)**
- Loi Windows goi SetCommState tren CDC-ACM — da duoc xu ly san trong `phantom_serial_gui.py`, khong can lam gi them.

**`ls /dev/ttyGS*` bao `No such file or directory` nhung `lsmod` da co `g_serial`**

Nguyen nhan hay gap nhat: `config.txt` dang de `dr_mode=host`. O che do host, kernel khong tao UDC
(USB Device Controller) nen `g_serial` khong bind vao dau duoc -> khong co `/dev/ttyGS0`.

```bash
CFG_BOOT="/boot/firmware/config.txt"; [ -f "$CFG_BOOT" ] || CFG_BOOT="/boot/config.txt"
grep -n dwc2 "$CFG_BOOT"
# Neu thay: dtoverlay=dwc2,dr_mode=host  -> SAI, phai sua:
sudo sed -i 's/^dtoverlay=dwc2,dr_mode=host/dtoverlay=dwc2,dr_mode=peripheral/' "$CFG_BOOT"
grep -n dwc2 "$CFG_BOOT"
# Phai thay: dtoverlay=dwc2,dr_mode=peripheral
sudo reboot
```

> Doi lai: khi de `peripheral`, cong micro-USB OTG khong cam duoc thiet bi USB host (hub, chuot,
> USB ethernet) nua. Neu can ca hai, thu `dr_mode=otg`, nhung tren Pi Zero che do `otg` doi khi
> khong do duoc cap thuong — `peripheral` chac chan hon.

**`[SERIAL] opened` khong xuat hien trong log Pi**
```bash
# 1. Kiem tra module da load chua
lsmod | grep -E 'dwc2|g_serial'
# Neu chua co:
sudo modprobe g_serial

# 2. Kiem tra cmdline.txt — phai la MOT DONG duy nhat, co modules-load=dwc2,g_serial
CMDLINE="/boot/firmware/cmdline.txt"; [ -f "$CMDLINE" ] || CMDLINE="/boot/cmdline.txt"
cat "$CMDLINE"
wc -l "$CMDLINE"   # ket qua 0 hoac 1 la dung; >= 2 la file bi xuong dong -> kernel bo qua

# 3. Kiem tra dr_mode (xem muc ngay tren)
CFG_BOOT="/boot/firmware/config.txt"; [ -f "$CFG_BOOT" ] || CFG_BOOT="/boot/config.txt"
grep -n dwc2 "$CFG_BOOT"

# 4. Xac nhan da co UDC (rong = chua o che do peripheral)
ls /sys/class/udc/
```

**COM port hien trong Device Manager nhung Connect that bai**
- Nhan nut **caret** de refresh danh sach port, chon lai dung COM port.

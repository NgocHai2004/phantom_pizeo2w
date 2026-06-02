Mục tiêu App Desktop
pyinstaller --onefile .\en_de.py
Desktop là thiết bị phát Wi‑Fi cho Pi.
Desktop điều khiển cấu hình của Pi qua file config.
Desktop quản lý file trong thư mục rec của Pi: View list, Upload, Delete, Refresh.

Config trên Pi (hiện tại)
- `dinh_danh`
- `cau_hinh_ghi_am`
- `updated_at`

Trường quan trọng trong `cau_hinh_ghi_am`
- `kieu_ghi_am`: `fixed_60s`, `continuous`, `manual`
- `thoi_luong_ghi_am_phut`: số phút/segment ghi âm
- `chu_ky_quet_wifi_phut`: số phút thử reconnect Wi‑Fi upload
- `ssid_upload`
- `wifi_password`
- `mic_loai`: `i2s`
- `mic_i2s_device`: ví dụ `hw:0,0` hoặc `hw:1,0`
- `mic_i2s_channels`: ví dụ `1`
- `mic_i2s_rate`: ví dụ `16000`
- `mic_i2s_format`: ví dụ `S32_LE`
- `duong_dan_public_key`: mặc định `public.key`, có thể đổi sang file key khác

Ví dụ config hiện tại
```json
{
  "dinh_danh": {
    "ma_id": "BN-0001",
    "ho_ten": "Nguyen Van A",
    "nam_sinh": 1990,
    "dia_chi": "Ha Noi",
    "ngay_cap_dinh_danh": "2026-05-30"
  },
  "cau_hinh_ghi_am": {
    "kieu_ghi_am": "continuous",
    "thoi_luong_ghi_am_phut": 1,
    "chu_ky_quet_wifi_phut": 2,
    "ssid_upload": "7068616e746f6d303030303030300001",
    "wifi_password": "12345678",
    "mic_loai": "i2s",
    "mic_i2s_device": "hw:0,0",
    "mic_i2s_channels": 1,
    "mic_i2s_rate": 16000,
    "mic_i2s_format": "S32_LE",
    "duong_dan_public_key": "public.key"
  },
  "updated_at": "2026-05-30T11:15:00+07:00"
}
```

Luồng cập nhật config an toàn
Desktop upload file tạm config.tmp.
Rename thành config.json trên Pi.
Pi phát hiện config mới và áp dụng.
Nếu config lỗi định dạng, Pi giữ config cũ và báo trạng thái lỗi.

Đường dẫn file config trên Pi
`/home/<user_pi>/rec/pi_identity_config.json`

----------------------------------------
Cài đặt trên Pi từ file ZIP mới
----------------------------------------

Tên zip mới
`pi2w_pi_package_i2s_v2.zip`

Bước 1: giải nén
```bash
unzip pi2w_pi_package_i2s_v2.zip -d pi2w_pi_package
cd pi2w_pi_package
```

Lưu ý nếu bạn dùng root shell
- Script sẽ cài service chạy user thật (`APP_USER=...`).
- Ví dụ user là `pizero2`.

Bước 2A: Ubuntu/Armbian/Debian/Raspberry Pi OS
```bash
sed -i '1s/^\xEF\xBB\xBF//' install_pi.sh install_arch.sh
sed -i 's/\r$//' install_pi.sh install_arch.sh pi2w_client.service
chmod +x install_pi.sh
APP_USER=pizero2 ./install_pi.sh
```

Bước 2B: Arch Linux / Arch Linux ARM
```bash
sed -i '1s/^\xEF\xBB\xBF//' install_pi.sh install_arch.sh
sed -i 's/\r$//' install_pi.sh install_arch.sh pi2w_client.service
chmod +x install_arch.sh
APP_USER=pizero2 ./install_arch.sh
```

Bước 3: copy public key mặc định (nếu chưa có)
```bash
cp -f public.key /home/pizero2/public.key
```

Nếu muốn dùng key khác
1) Copy key mới lên Pi, ví dụ:
```bash
cp -f my_other.key /home/pizero2/keys/my_other.key
```
2) Sửa config:
```json
"duong_dan_public_key": "/home/pizero2/keys/my_other.key"
```
3) Restart service:
```bash
sudo systemctl restart pi2w_client.service
```

Kiểm tra service
```bash
sudo systemctl status pi2w_client.service --no-pager -l
journalctl -u pi2w_client.service -f
```

Kiểm tra mic I2S nhanh
```bash
arecord -l
arecord -D hw:0,0 -c 1 -r 16000 -f S32_LE -d 3 /tmp/test_i2s.wav
ls -lh /tmp/test_i2s.wav
```

Nếu `hw:0,0` không ghi được, đổi `mic_i2s_device` sang `hw:1,0` trong config và restart service.

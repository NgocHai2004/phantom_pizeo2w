# PI2W API SPEC (PC Integration)

Tai lieu nay mo ta 3 API moi de app PC doc/sua config va thay public key tren Pi.

## 1) Base URL
- `http://<PI_IP>:8765`
- API chi san sang khi Pi dang ket noi WiFi MGMT (`7068616e746f6d303030303030300001`) va mgmt server dang chay.

## 2) API 1 - Lay config hien tai

### Request
- Method: `GET`
- Path: `/api/config`

### Success Response (`200`)
```json
{
  "ok": true,
  "config": {
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
      "chu_ky_quet_wifi_phut": 1,
      "ssid_upload": "7068616e746f6d303030303030300002",
      "wifi_password": "12345678",
      "duong_dan_public_key": "public.key"
    }
  },
  "updated_at": "2026-06-02T10:20:30+07:00",
  "config_path": "/home/pizero21/rec/pi_identity_config.json"
}
```

### Error
- `404`: route khong ton tai

---

## 3) API 2 - Cap nhat config

### Request
- Method: `POST`
- Path: `/api/config`
- Headers: `Content-Type: application/json`
- Body: JSON object (ho tro partial update)

### Request Example
```json
{
  "dinh_danh": {
    "ma_id": "BN-0002",
    "ho_ten": "Tran Van B",
    "nam_sinh": 1988,
    "dia_chi": "Da Nang",
    "ngay_cap_dinh_danh": "2026-06-02"
  },
  "cau_hinh_ghi_am": {
    "kieu_ghi_am": "continuous",
    "thoi_luong_ghi_am_phut": 1,
    "chu_ky_quet_wifi_phut": 1,
    "ssid_upload": "7068616e746f6d303030303030300002",
    "wifi_password": "12345678",
    "duong_dan_public_key": "public.key"
  }
}
```

### Success Response (`200`)
```json
{
  "ok": true,
  "message": "config saved, service restarting",
  "config_path": "/home/pizero21/rec/pi_identity_config.json"
}
```

### Error
- `400`
  - `application/json required`
  - `empty body`
  - `invalid json: ...`
  - `json body must be object`
  - `invalid config: ...`
- `500`
  - `failed to write config`

### Luu y
- API se cap nhat `updated_at` tu dong.
- Sau khi luu thanh cong, service tu restart (`Restart=always`).

---

## 4) API 3 - Thay file public key

### Request
- Method: `POST`
- Path: `/api/public-key`
- Headers: `Content-Type: multipart/form-data`
- Form field bat buoc: `file`

### Curl Example
```bash
curl -X POST "http://<PI_IP>:8765/api/public-key" \
  -F "file=@public.key"
```

### Success Response (`200`)
```json
{
  "ok": true,
  "message": "public key saved, service restarting",
  "key_path": "/home/pizero21/public.key",
  "size": 32
}
```

### Error
- `400`
  - `multipart required`
  - `missing file field`
  - `invalid key data`
  - `key too short: need >= 32 bytes`
- `500`
  - loi ghi file

### Luu y
- Key duoc luu theo `duong_dan_public_key` trong config.
- Sau khi luu key thanh cong, service tu restart.

---

## 5) De xuat flow UI ben PC
1. Goi `GET /api/config` de preload form.
2. User sua thong tin -> gui `POST /api/config`.
3. Neu user doi key -> gui `POST /api/public-key`.
4. Sau moi POST thanh cong, doi 2-5 giay roi goi lai `GET /api/config` de dong bo UI (vi service vua restart).

---

## 6) Ghi chu trien khai
- CORS: server dang tra `Access-Control-Allow-Origin: *`.
- Khuyen nghi app PC hien thong bao: "Thiet bi dang restart dich vu..." sau khi POST thanh cong.
- Neu timeout ngay sau POST, app co the retry `GET /api/config` sau vai giay.

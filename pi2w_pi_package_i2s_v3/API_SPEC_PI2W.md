# PI2W API SPEC (PC Integration)

Tai lieu nay mo ta cac API de app PC doc/sua config va thay public key tren Pi.

## 1) Base URL
- `http://<PI_IP>:8765`
- API chi san sang khi Pi dang ket noi WiFi MGMT (`7068616e746f6d303030303030300001`) va mgmt server dang chay.

---

## 2) Che do ghi am

Co 2 che do chinh:

### Che do 1: Ghi lien tuc (`continuous`)
- Ghi am khong ngung, moi file dai N phut.
- Dung field: `kieu_ghi_am = "continuous"`, `thoi_luong_ghi_am_phut = <so phut>`.

### Che do 2: Ghi theo gio (`interval`)
- Ghi 1 file dai `thoi_luong_ghi_am_phut` phut, sau do nghi, roi lap lai.
- Chu ky lap = `chu_ky_ghi_am_phut` phut (tinh tu dau file truoc).
- Neu `thoi_luong_ghi_am_phut >= chu_ky_ghi_am_phut`: ghi lien tuc, khong nghi giua cac file.
- Dung field: `kieu_ghi_am = "interval"`, `thoi_luong_ghi_am_phut = <so phut>`, `chu_ky_ghi_am_phut = <so phut>`.

### Che do 3: Ghi theo tieng (`vad`)
- **Phase 1 – Nghe**: Thiet bi lang nghe lien tuc, khong ghi file. Khi am thanh vuot nguong `vad_nguong_dbfs` thi bat dau ghi.
- **Phase 2 – Ghi**: Ghi file thuc su. Dung khi:
  - Im lang lien tuc >= `vad_timeout_im_lang_giay` giay → luu file → quay ve Phase 1.
  - Dat toi da `vad_max_thoi_gian_giay` giay → luu file → quay ve Phase 1.
- File sau khi ghi duoc xu ly: nen Opus → ma hoa → upload.

---

## 3) API 1 - Lay config hien tai

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
      "ngay_cap_dinh_danh": "2026-05-30",
      "ten_thiet_bi": "Pi Zero 2W",
      "id_thiet_bi": "DEVICE-0001",
      "dia_chi_thiet_bi": "Ha Noi"
    },
    "cau_hinh_ghi_am": {
      "kieu_ghi_am": "continuous",
      "thoi_luong_ghi_am_phut": 1,
      "chu_ky_quet_wifi_phut": 1,
      "ssid_upload": "7068616e746f6d303030303030300002",
      "wifi_password": "12345678",
      "duong_dan_public_key": "public.key",
      "vad_nguong_dbfs": -41.0,
      "vad_timeout_im_lang_giay": 60,
      "vad_max_thoi_gian_giay": 600
    }
  },
  "updated_at": "2026-06-02T10:20:30+07:00",
  "config_path": "/home/pizero23/rec/pi_identity_config.json",
  "mac_address": "b8:27:eb:xx:xx:xx"
}
```

### Error
- `404`: route khong ton tai

---

## 4) API 2 - Cap nhat config

### Request
- Method: `POST`
- Path: `/api/config`
- Headers: `Content-Type: application/json`
- Body: JSON object (ho tro partial update, chi can gui field can thay doi)

### Vi du: cap nhat day du (dinh danh + ghi am)
```json
{
  "dinh_danh": {
    "ma_id": "BN-0002",
    "ho_ten": "Tran Van B",
    "nam_sinh": 1988,
    "dia_chi": "Da Nang",
    "ngay_cap_dinh_danh": "2026-06-02",
    "ten_thiet_bi": "Pi Zero 2W #2",
    "id_thiet_bi": "DEVICE-0002",
    "dia_chi_thiet_bi": "Da Nang"
  },
  "cau_hinh_ghi_am": {
    "kieu_ghi_am": "continuous",
    "thoi_luong_ghi_am_phut": 2,
    "chu_ky_quet_wifi_phut": 1,
    "ssid_upload": "7068616e746f6d303030303030300002",
    "wifi_password": "12345678"
  }
}
```


### Vi du: chuyen sang ghi lien tuc 2 phut/file
```json
{
  "cau_hinh_ghi_am": {
    "kieu_ghi_am": "continuous",
    "thoi_luong_ghi_am_phut": 2
  }
}
```

### Vi du: chuyen sang che do VAD
```json
{
  "cau_hinh_ghi_am": {
    "kieu_ghi_am": "vad",
    "vad_nguong_dbfs": -41.0,
    "vad_timeout_im_lang_giay": 30,
    "vad_max_thoi_gian_giay": 600
  }
}
```
### Vi du: chuyen sang che do interval (ghi 5 phut, nghi 55 phut, lap lai moi gio)
```json
{
  "cau_hinh_ghi_am": {
    "kieu_ghi_am": "interval",
    "thoi_luong_ghi_am_phut": 5,
    "chu_ky_ghi_am_phut": 60
  }
}
```
### Rang buoc cac field

| Field | Kieu | Gia tri hop le | Mac dinh | Mo ta |
|---|---|---|---|---|
| `kieu_ghi_am` | string | `"continuous"`, `"vad"`, `"interval"` | `"continuous"` | Che do ghi am |
| `thoi_luong_ghi_am_phut` | int | 1 – 120 | 1 | So phut moi file (dung khi `continuous` va `interval`) |
| `chu_ky_ghi_am_phut` | int | 1 – 1440 | 60 | Chu ky giua 2 lan ghi (phut, chi dung khi `interval`) |
| `chu_ky_quet_wifi_phut` | int | 1 – 240 | 2 | Chu ky quet WiFi upload (phut) |
| `vad_nguong_dbfs` | float | -96.0 – 0.0 | -41.0 | Nguong am thanh bat dau ghi (am to → gan 0) |
| `vad_timeout_im_lang_giay` | int | 5 – 600 | 60 | Im lang lien tuc bao nhieu giay thi dung ghi |
| `vad_max_thoi_gian_giay` | int | 30 – 3600 | 600 | Thoi gian ghi toi da 1 session (giay) |
| `ten_thiet_bi` | string | chuoi bat ky | `"Pi Zero 2W"` | Ten thiet bi |
| `id_thiet_bi` | string | chuoi bat ky | `"DEVICE-0001"` | Ma dinh danh thiet bi |
| `dia_chi_thiet_bi` | string | chuoi bat ky | `"Ha Noi"` | Dia chi thiet bi |

### Success Response (`200`)
```json
{
  "ok": true,
  "message": "config saved, service restarting",
  "config_path": "/home/pizero23/rec/pi_identity_config.json"
}
```

### Error
- `400`: `application/json required` / `empty body` / `invalid json` / `invalid config`
- `500`: `failed to write config`

### Luu y
- `updated_at` duoc cap nhat tu dong.
- Sau khi luu thanh cong, service tu restart.

---

## 5) API 3 - Thay file public key

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
- `400`: `multipart required` / `missing file field` / `invalid key data` / `key too short: need >= 32 bytes`
- `500`: loi ghi file

### Luu y
- Key duoc luu theo `duong_dan_public_key` trong config.
- Sau khi luu key thanh cong, service tu restart.

---

## 6) Huong dan chinh che do ghi am tu PC (WiFi 0001)

### Buoc 1: Ket noi WiFi quan ly
- PC phat WiFi an SSID `7068616e746f6d303030303030300001` (password `12345678`).
- Pi tu dong ket noi va gui IP cua no den `POST /api/device/connection`.
- Lay IP Pi tu thong bao do, sau do goi cac API ben duoi.

### Buoc 2: Chon che do ghi am

#### Ghi lien tuc moi N phut (`continuous`)
```json
POST /api/config
{
  "cau_hinh_ghi_am": {
    "kieu_ghi_am": "continuous",
    "thoi_luong_ghi_am_phut": 5
  }
}
```
> Pi ghi khong ngung, moi file 5 phut. Thay so phut tu 1 den 120.

#### Ghi theo gio — ghi M phut, nghi phan con lai, lap lai moi N phut (`interval`)
```json
POST /api/config
{
  "cau_hinh_ghi_am": {
    "kieu_ghi_am": "interval",
    "thoi_luong_ghi_am_phut": 5,
    "chu_ky_ghi_am_phut": 60
  }
}
```
> Pi ghi 5 phut, nghi 55 phut, roi ghi tiep. Chu ky tinh tu dau file truoc.
> `chu_ky_ghi_am_phut` phai >= `thoi_luong_ghi_am_phut`; neu nho hon thi ghi lien tuc.

#### Ghi theo tieng (`vad`)
```json
POST /api/config
{
  "cau_hinh_ghi_am": {
    "kieu_ghi_am": "vad",
    "vad_nguong_dbfs": -41.0,
    "vad_timeout_im_lang_giay": 30,
    "vad_max_thoi_gian_giay": 600
  }
}
```
> Pi lang nghe lien tuc. Khi co tieng vuot -41 dBFS thi bat dau ghi. Im lang 30 giay hoac qua 600 giay thi luu file va quay lai lang nghe.

### Buoc 3: Xac nhan da ap dung
- Sau POST thanh cong, cho 3–5 giay de service restart.
- Goi `GET /api/config` de kiem tra `kieu_ghi_am` da doi chua.

### Bang chon nhanh

| Muc tieu | Che do | Field chinh |
|---|---|---|
| Ghi lien tuc, file ngan | `continuous` | `thoi_luong_ghi_am_phut` |
| Ghi dinh ky theo gio | `interval` | `thoi_luong_ghi_am_phut` + `chu_ky_ghi_am_phut` |
| Chi ghi khi co nguoi noi | `vad` | `vad_nguong_dbfs` + `vad_timeout_im_lang_giay` |

---

## 8) De xuat flow UI ben PC
1. Goi `GET /api/config` de preload form.
2. User chon che do ghi am va sua thong tin → gui `POST /api/config`.
3. Neu user doi key → gui `POST /api/public-key`.
4. Sau moi POST thanh cong, doi 2–5 giay roi goi lai `GET /api/config` de dong bo UI.

---

## 7) Ghi chu trien khai
- CORS: server tra `Access-Control-Allow-Origin: *`.
- Hien thong bao "Thiet bi dang restart..." sau POST thanh cong.
- Neu timeout ngay sau POST, retry `GET /api/config` sau vai giay.

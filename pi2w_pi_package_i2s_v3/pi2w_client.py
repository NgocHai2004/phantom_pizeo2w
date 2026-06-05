#!/usr/bin/env python3
import os
import time
import pathlib
import subprocess
import threading
import queue
import hashlib
import struct
import math
import json
import re
from datetime import datetime, timedelta
from typing import Optional
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import shutil
import email as _email_mod
import zipfile
import io

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives import hmac as _hmac, hashes as _hashes
from cryptography.hazmat.backends import default_backend as _backend
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization


# === WiFi target hidden ===
# Chi dung 1 WiFi an nay de upload.
UPLOAD_TARGET_SSID = "7068616e746f6d303030303030300002"
# WiFi quan ly file (PC app ket noi de xem/tai/xoa file rec/).
MGMT_TARGET_SSID   = "7068616e746f6d303030303030300001"
WIFI_PASSWORD = "12345678"

# WiFi an: dung profile NetworkManager da cau hinh san / tao san.
# Ly do: "nmcli dev wifi connect ... hidden yes" co the loi key-mgmt.
# Lenh dung tren Pi cua ban la: nmcli -w 20 connection up phantom_hidden ifname wlan0
WIFI_CONNECTION_PROFILE = "phantom_hidden"
MGMT_WIFI_CONNECTION_PROFILE = "phantom_mgmt"
WIFI_IFACE = "wlan0"
WIFI_CONNECT_TIMEOUT_SEC = 20
WIFI_CONNECT_FAST_TIMEOUT_SEC = 8
WIFI_RETRY_INTERVAL_SEC = 120
WIFI_SCAN_INTERVAL_SEC = 120          # 2 phut giua cac lan quet khi khong thay WiFi
IMMEDIATE_HIDDEN_WIFI_CHECK_SEC = 5

# Sau khi upload thanh cong het cac file .bin thi ngat ket noi WiFi upload.
# Khi bat che do uu tien WiFi an lap tuc, app se GIU ket noi WiFi an va khong tu down.
DISCONNECT_WIFI_AFTER_SUCCESS_UPLOAD = True
WIFI_DISCONNECT_TIMEOUT_SEC = 10

UPLOAD_HOST = "10.42.0.1"
UPLOAD_PORT = 8765
UPLOAD_PATH = "/api/upload"
# Device dang dung user pizero2, khong dung /home/pi nua.
REC_DIR = pathlib.Path.home() / "rec"
PI_IDENTITY_CONFIG_PATH = REC_DIR / "pi_identity_config.json"
PI_IDENTITY_CONFIG_TMP_PATH = REC_DIR / "pi_identity_config.tmp"

SUPPORTED_RECORD_MODES = {"fixed_60s", "continuous", "manual", "vad", "interval", "scheduled"}
DEFAULT_RECORD_MODE = "fixed_60s"
AUTO_RECORD_SEC = 60
DEFAULT_RECORD_MINUTES = 1
DEFAULT_INTERVAL_MINUTES = 60

# VAD defaults
VAD_DEFAULT_THRESHOLD_DBFS = -41.0
VAD_DEFAULT_SILENCE_TIMEOUT_SEC = 60
VAD_DEFAULT_MAX_DURATION_SEC = 600
VAD_DEFAULT_MONITOR_INTERVAL_SEC = 3
DEFAULT_WIFI_RETRY_INTERVAL_SEC = WIFI_RETRY_INTERVAL_SEC
DEFAULT_WIFI_RETRY_MINUTES = max(1, DEFAULT_WIFI_RETRY_INTERVAL_SEC // 60)
DEFAULT_PREFER_HIDDEN_WIFI_IMMEDIATE = False
MAX_RECORD_MINUTES = 120
MAX_WIFI_RETRY_MINUTES = 240

MAX_FILE_SIZE = 60_000_000
MIN_VALID_ENC_REC_SIZE = 512

# Mac dinh cho mic I2S (co the doi trong file config).
ARECORD_DEVICE = "hw:1,0"
ARECORD_CHANNELS = "1"
ARECORD_RATE = "16000"
ARECORD_FORMAT = "S32_LE"
# Nen WAV sang Opus truoc khi ma hoa. Can cai ffmpeg:
# sudo apt update && sudo apt install -y ffmpeg
OPUS_BITRATE = "24k"       # Voice ro hon 16k, file van nho.
OPUS_APPLICATION = "voip"  # Toi uu cho giong noi.

# Tang am luong truoc khi nen Opus.
# Neu nghe van nho: tang len "15"; neu bi re/vo tieng: giam xuong "8" hoac "6".
AUDIO_GAIN_DB = "12"


# === PHANTOM 3-layer encryption ===
# File .bin tao ra co header PHTM3L2 de GUI nhan dang dung kieu hybrid.
# Dat public key tai: ~/public.key
PHTM3L2_MAGIC = b"PHTM3L2"
PHTM_MAGIC = b"PHTM"
PHTM_VERSION = 2
PHTM_KEY_SIZE = 32
PHTM_KEY_PATH = pathlib.Path.home() / "public.key"
PHRAW1_MAGIC = b"PHRAW1"

_last_upload_try_monotonic = 0.0
_runtime_wifi_retry_interval_sec = WIFI_RETRY_INTERVAL_SEC
_runtime_upload_target_ssid = UPLOAD_TARGET_SSID
_runtime_wifi_password = WIFI_PASSWORD
_runtime_arecord_device = ARECORD_DEVICE
_runtime_arecord_channels = ARECORD_CHANNELS
_runtime_arecord_rate = ARECORD_RATE
_runtime_arecord_format = ARECORD_FORMAT
_runtime_public_key_path = str(PHTM_KEY_PATH)
_runtime_prefer_hidden_wifi_immediate = DEFAULT_PREFER_HIDDEN_WIFI_IMMEDIATE
_runtime_vad_threshold_dbfs = VAD_DEFAULT_THRESHOLD_DBFS
_runtime_vad_silence_timeout_sec = VAD_DEFAULT_SILENCE_TIMEOUT_SEC
_runtime_vad_max_duration_sec = VAD_DEFAULT_MAX_DURATION_SEC
_runtime_vad_monitor_interval_sec = VAD_DEFAULT_MONITOR_INTERVAL_SEC
_runtime_interval_cycle_sec: int = DEFAULT_INTERVAL_MINUTES * 60  # chu ky giua 2 lan ghi (interval mode)
_runtime_scheduled_start: Optional[str] = None  # "YYYY-MM-DD HH:MM", None = chua cau hinh
_runtime_scheduled_end: Optional[str] = None    # "YYYY-MM-DD HH:MM", None = ghi den khi tat
_wifi_nmcli_lock = threading.Lock()

# Event de bao wifi_manager_worker rescan ngay sau khi upload xong va ngat ket noi
_wifi_upload_done_event = threading.Event()
_time_offset_sec: float = 0.0  # PC time - system time, duoc cap nhat khi ket noi mgmt WiFi

def log(msg: str) -> None:
    print(msg, flush=True)


def ensure_dirs() -> None:
    REC_DIR.mkdir(parents=True, exist_ok=True)


def now_iso_local() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today_ymd() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def build_default_identity_config() -> dict:
    today = today_ymd()
    return {
        "dinh_danh": {
            "ma_id": "BN-0001",
            "ho_ten": "Nguyen Van A",
            "nam_sinh": 1990,
            "dia_chi": "Ha Noi",
            "ngay_cap_dinh_danh": today,
            "ten_thiet_bi": "Pi Zero 2W",
            "id_thiet_bi": "DEVICE-0001",
            "dia_chi_thiet_bi": "Ha Noi",
        },
        "cau_hinh_ghi_am": {
            "kieu_ghi_am": DEFAULT_RECORD_MODE,
            "thoi_luong_ghi_am_phut": DEFAULT_RECORD_MINUTES,
            "chu_ky_ghi_am_phut": DEFAULT_INTERVAL_MINUTES,
            "chu_ky_quet_wifi_phut": DEFAULT_WIFI_RETRY_MINUTES,
            "ssid_upload": UPLOAD_TARGET_SSID,
            "wifi_password": WIFI_PASSWORD,
            "uu_tien_wifi_an_lap_tuc": DEFAULT_PREFER_HIDDEN_WIFI_IMMEDIATE,
            "mic_loai": "i2s",
            "mic_i2s_device": ARECORD_DEVICE,
            "mic_i2s_channels": int(ARECORD_CHANNELS),
            "mic_i2s_rate": int(ARECORD_RATE),
            "mic_i2s_format": ARECORD_FORMAT,
            "duong_dan_public_key": "public.key",
            "vad_nguong_dbfs": VAD_DEFAULT_THRESHOLD_DBFS,
            "vad_timeout_im_lang_giay": VAD_DEFAULT_SILENCE_TIMEOUT_SEC,
            "vad_max_thoi_gian_giay": VAD_DEFAULT_MAX_DURATION_SEC,
            "bat_dau_ghi_am": None,
            "ket_thuc_ghi_am": None,
        },
        "updated_at": now_iso_local(),
    }


def validate_identity_config(config: dict) -> tuple[bool, str]:
    if not isinstance(config, dict):
        return False, "config must be JSON object"

    dinh_danh = config.get("dinh_danh")
    if not isinstance(dinh_danh, dict):
        return False, "missing/invalid 'dinh_danh'"

    required_identity = {
        "ma_id": str,
        "ho_ten": str,
        "nam_sinh": int,
        "dia_chi": str,
        "ngay_cap_dinh_danh": str,
    }
    for key, typ in required_identity.items():
        if key not in dinh_danh:
            return False, f"missing dinh_danh.{key}"
        if not isinstance(dinh_danh[key], typ):
            return False, f"invalid type dinh_danh.{key}"

    for opt_key in ("ten_thiet_bi", "id_thiet_bi", "dia_chi_thiet_bi"):
        val = dinh_danh.get(opt_key)
        if val is not None and not isinstance(val, str):
            return False, f"invalid type dinh_danh.{opt_key}"

    cau_hinh = config.get("cau_hinh_ghi_am")
    if not isinstance(cau_hinh, dict):
        return False, "missing/invalid 'cau_hinh_ghi_am'"

    kieu_ghi_am = cau_hinh.get("kieu_ghi_am")
    if not isinstance(kieu_ghi_am, str) or not kieu_ghi_am.strip():
        return False, "missing/invalid cau_hinh_ghi_am.kieu_ghi_am"

    ssid_upload = cau_hinh.get("ssid_upload")
    if ssid_upload is not None and not isinstance(ssid_upload, str):
        return False, "invalid cau_hinh_ghi_am.ssid_upload"

    wifi_password = cau_hinh.get("wifi_password")
    if wifi_password is not None and not isinstance(wifi_password, str):
        return False, "invalid cau_hinh_ghi_am.wifi_password"

    uu_tien_wifi_an_lap_tuc = cau_hinh.get("uu_tien_wifi_an_lap_tuc")
    if uu_tien_wifi_an_lap_tuc is not None and not isinstance(uu_tien_wifi_an_lap_tuc, bool):
        return False, "invalid cau_hinh_ghi_am.uu_tien_wifi_an_lap_tuc"

    mic_loai = cau_hinh.get("mic_loai")
    if mic_loai is not None and not isinstance(mic_loai, str):
        return False, "invalid cau_hinh_ghi_am.mic_loai"

    mic_i2s_device = cau_hinh.get("mic_i2s_device")
    if mic_i2s_device is not None and not isinstance(mic_i2s_device, str):
        return False, "invalid cau_hinh_ghi_am.mic_i2s_device"

    mic_i2s_channels = cau_hinh.get("mic_i2s_channels")
    if mic_i2s_channels is not None and not isinstance(mic_i2s_channels, int):
        return False, "invalid cau_hinh_ghi_am.mic_i2s_channels"

    mic_i2s_rate = cau_hinh.get("mic_i2s_rate")
    if mic_i2s_rate is not None and not isinstance(mic_i2s_rate, int):
        return False, "invalid cau_hinh_ghi_am.mic_i2s_rate"

    mic_i2s_format = cau_hinh.get("mic_i2s_format")
    if mic_i2s_format is not None and not isinstance(mic_i2s_format, str):
        return False, "invalid cau_hinh_ghi_am.mic_i2s_format"

    duong_dan_public_key = cau_hinh.get("duong_dan_public_key")
    if duong_dan_public_key is not None and not isinstance(duong_dan_public_key, str):
        return False, "invalid cau_hinh_ghi_am.duong_dan_public_key"

    for dt_field in ("bat_dau_ghi_am", "ket_thuc_ghi_am"):
        val = cau_hinh.get(dt_field)
        if val is not None:
            if not isinstance(val, str):
                return False, f"invalid cau_hinh_ghi_am.{dt_field} (expected 'YYYY-MM-DD HH:MM' or null)"
            try:
                datetime.strptime(val.strip(), "%Y-%m-%d %H:%M")
            except ValueError:
                return False, f"invalid cau_hinh_ghi_am.{dt_field} (expected 'YYYY-MM-DD HH:MM')"

    if "updated_at" in config and not isinstance(config["updated_at"], str):
        return False, "invalid updated_at"

    return True, ""


def write_identity_config_atomic(config: dict, final_path: pathlib.Path = PI_IDENTITY_CONFIG_PATH) -> bool:
    try:
        payload = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
        PI_IDENTITY_CONFIG_TMP_PATH.write_text(payload, encoding="utf-8")
        PI_IDENTITY_CONFIG_TMP_PATH.replace(final_path)
        return True
    except Exception as e:
        log(f"[CONFIG] FAIL write config atomically: {e}")
        return False


def ensure_identity_config_exists() -> bool:
    if PI_IDENTITY_CONFIG_PATH.exists():
        return True

    default_config = build_default_identity_config()
    ok = write_identity_config_atomic(default_config, PI_IDENTITY_CONFIG_PATH)
    if ok:
        log(f"[CONFIG] Created default config: {PI_IDENTITY_CONFIG_PATH}")
    return ok


def load_identity_config_from_disk(path: pathlib.Path = PI_IDENTITY_CONFIG_PATH) -> Optional[dict]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
        cfg = json.loads(raw)
    except Exception as e:
        log(f"[CONFIG] FAIL read/parse {path}: {e}")
        return None

    valid, reason = validate_identity_config(cfg)
    if not valid:
        log(f"[CONFIG] INVALID {path}: {reason}")
        return None

    return cfg


def normalize_record_mode(mode: object) -> str:
    if not isinstance(mode, str):
        return DEFAULT_RECORD_MODE

    clean_mode = mode.strip().lower()
    if clean_mode in SUPPORTED_RECORD_MODES:
        return clean_mode

    # Ho tro fixed_<so_giay>s (vd: fixed_120s) de mo rong ma khong sua code.
    if re.fullmatch(r"fixed_\d+s", clean_mode):
        return clean_mode

    return DEFAULT_RECORD_MODE


def record_duration_from_mode(mode: str) -> Optional[int]:
    if mode == "manual":
        return None

    if mode == "vad":
        return None

    if mode == "continuous":
        # Vong lap ghi am van theo segment de worker co file de nen/ma hoa/upload.
        return AUTO_RECORD_SEC

    m = re.fullmatch(r"fixed_(\d+)s", mode)
    if m:
        seconds = int(m.group(1))
        return max(1, seconds)

    return AUTO_RECORD_SEC


def parse_positive_float(value: object, default_value: float, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default_value
    # Chi chap nhan 0.5 hoac so nguyen >= 1
    if parsed == 0.5:
        return 0.5
    int_val = int(parsed)
    if int_val >= 1 and float(int_val) == parsed:
        parsed = float(int_val)
    else:
        return default_value
    if parsed < min_value:
        return min_value
    if parsed > max_value:
        return max_value
    return parsed


def parse_positive_int(value: object, default_value: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default_value

    if parsed < min_value:
        return min_value
    if parsed > max_value:
        return max_value
    return parsed


def parse_text_field(value: object, default_value: str, min_length: int = 1, max_length: int = 128) -> str:
    if not isinstance(value, str):
        return default_value

    clean = value.strip()
    if len(clean) < min_length:
        return default_value
    if len(clean) > max_length:
        return clean[:max_length]
    return clean

def parse_bool_field(value: object, default_value: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        clean = value.strip().lower()
        if clean in {"1", "true", "yes", "on"}:
            return True
        if clean in {"0", "false", "no", "off"}:
            return False
    return default_value

def resolve_public_key_path(path_text: str) -> pathlib.Path:
    p = pathlib.Path(path_text).expanduser()
    if not p.is_absolute():
        p = pathlib.Path.home() / p
    return p

def derive_runtime_settings(config: dict) -> tuple[str, Optional[int], int, str, str, str, str, str, str, str, bool, float, int, int, int, Optional[str], Optional[str]]:
    cau_hinh = config.get("cau_hinh_ghi_am", {}) if isinstance(config, dict) else {}

    mode = normalize_record_mode(cau_hinh.get("kieu_ghi_am"))
    mode_duration_sec = record_duration_from_mode(mode)

    record_minutes = parse_positive_int(
        cau_hinh.get("thoi_luong_ghi_am_phut", DEFAULT_RECORD_MINUTES),
        default_value=DEFAULT_RECORD_MINUTES,
        min_value=1,
        max_value=MAX_RECORD_MINUTES,
    )

    interval_cycle_minutes = parse_positive_int(
        cau_hinh.get("chu_ky_ghi_am_phut", DEFAULT_INTERVAL_MINUTES),
        default_value=DEFAULT_INTERVAL_MINUTES,
        min_value=1,
        max_value=MAX_WIFI_RETRY_MINUTES,
    )

    wifi_retry_minutes = parse_positive_float(
        cau_hinh.get("chu_ky_quet_wifi_phut", DEFAULT_WIFI_RETRY_MINUTES),
        default_value=float(DEFAULT_WIFI_RETRY_MINUTES),
        min_value=0.5,
        max_value=float(MAX_WIFI_RETRY_MINUTES),
    )

    runtime_ssid = parse_text_field(
        cau_hinh.get("ssid_upload", UPLOAD_TARGET_SSID),
        default_value=UPLOAD_TARGET_SSID,
        min_length=1,
        max_length=128,
    )

    runtime_wifi_password = parse_text_field(
        cau_hinh.get("wifi_password", WIFI_PASSWORD),
        default_value=WIFI_PASSWORD,
        min_length=8,
        max_length=63,
    )

    runtime_arecord_device = parse_text_field(
        cau_hinh.get("mic_i2s_device", ARECORD_DEVICE),
        default_value=ARECORD_DEVICE,
        min_length=1,
        max_length=64,
    )

    runtime_arecord_channels = str(parse_positive_int(
        cau_hinh.get("mic_i2s_channels", int(ARECORD_CHANNELS)),
        default_value=int(ARECORD_CHANNELS),
        min_value=1,
        max_value=4,
    ))

    runtime_arecord_rate = str(parse_positive_int(
        cau_hinh.get("mic_i2s_rate", int(ARECORD_RATE)),
        default_value=int(ARECORD_RATE),
        min_value=8000,
        max_value=192000,
    ))

    runtime_arecord_format = parse_text_field(
        cau_hinh.get("mic_i2s_format", ARECORD_FORMAT),
        default_value=ARECORD_FORMAT,
        min_length=3,
        max_length=16,
    )

    runtime_public_key_path_raw = parse_text_field(
        cau_hinh.get("duong_dan_public_key", "public.key"),
        default_value="public.key",
        min_length=1,
        max_length=255,
    )
    runtime_public_key_path = str(resolve_public_key_path(runtime_public_key_path_raw))

    runtime_prefer_hidden_wifi_immediate = parse_bool_field(
        cau_hinh.get("uu_tien_wifi_an_lap_tuc", DEFAULT_PREFER_HIDDEN_WIFI_IMMEDIATE),
        default_value=DEFAULT_PREFER_HIDDEN_WIFI_IMMEDIATE,
    )

    # VAD params
    raw_vad_threshold = cau_hinh.get("vad_nguong_dbfs", VAD_DEFAULT_THRESHOLD_DBFS)
    try:
        vad_threshold = float(raw_vad_threshold)
        if vad_threshold > 0:
            vad_threshold = VAD_DEFAULT_THRESHOLD_DBFS
    except (TypeError, ValueError):
        vad_threshold = VAD_DEFAULT_THRESHOLD_DBFS

    vad_silence_timeout = parse_positive_int(
        cau_hinh.get("vad_timeout_im_lang_giay", VAD_DEFAULT_SILENCE_TIMEOUT_SEC),
        default_value=VAD_DEFAULT_SILENCE_TIMEOUT_SEC,
        min_value=5,
        max_value=600,
    )

    vad_max_duration = parse_positive_int(
        cau_hinh.get("vad_max_thoi_gian_giay", VAD_DEFAULT_MAX_DURATION_SEC),
        default_value=VAD_DEFAULT_MAX_DURATION_SEC,
        min_value=30,
        max_value=3600,
    )

    if mode in ("manual", "vad", "scheduled"):
        duration_sec = None
    elif mode.startswith("fixed_"):
        duration_sec = mode_duration_sec
    else:
        duration_sec = record_minutes * 60

    # Scheduled mode: parse bat_dau / ket_thuc ("YYYY-MM-DD HH:MM" hoac None)
    def _parse_datetime_str(val: object) -> Optional[str]:
        if val is None or not isinstance(val, str):
            return None
        try:
            datetime.strptime(val.strip(), "%Y-%m-%d %H:%M")
            return val.strip()
        except ValueError:
            return None

    scheduled_start = _parse_datetime_str(cau_hinh.get("bat_dau_ghi_am"))
    scheduled_end   = _parse_datetime_str(cau_hinh.get("ket_thuc_ghi_am"))

    return mode, duration_sec, wifi_retry_minutes * 60, runtime_ssid, runtime_wifi_password, runtime_arecord_device, runtime_arecord_channels, runtime_arecord_rate, runtime_arecord_format, runtime_public_key_path, runtime_prefer_hidden_wifi_immediate, vad_threshold, vad_silence_timeout, vad_max_duration, interval_cycle_minutes * 60, scheduled_start, scheduled_end

def delete_file_safely(path: pathlib.Path, reason: str = "", allowed_suffixes: tuple[str, ...] = ()) -> None:
    try:
        suffix = path.suffix.lower()
        if path.exists() and (not allowed_suffixes or suffix in allowed_suffixes):
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            log(f"[CLEANUP] DELETE {suffix}: {path.name} size={size} reason={reason}")
    except Exception as e:
        log(f"[CLEANUP] FAIL delete {path.name}: {e}")


def delete_wav_safely(wav_path: pathlib.Path, reason: str = "") -> None:
    delete_file_safely(wav_path, reason=reason, allowed_suffixes=(".wav",))


def delete_opus_safely(opus_path: pathlib.Path, reason: str = "") -> None:
    delete_file_safely(opus_path, reason=reason, allowed_suffixes=(".opus",))


def cleanup_leftover_temp_audio_on_startup() -> None:
    """
    On unclean shutdown during recording, WAV files can be incomplete.
    ffmpeg may fail with: "Invalid data found when processing input".

    On startup:
    - Delete leftover .wav files.
    - Keep leftover .opus files for next encryption pass.
    - Keep leftover .bin files for next upload pass.
    """
    deleted_wav = 0

    for p in sorted(REC_DIR.glob("*.wav")):
        try:
            size = p.stat().st_size if p.exists() else 0
            p.unlink(missing_ok=True)
            deleted_wav += 1
            log(f"[STARTUP CLEANUP] DELETE leftover wav: {p.name} size={size} reason=startup_wav_may_be_incomplete")
        except Exception as e:
            log(f"[STARTUP CLEANUP] FAIL delete wav {p.name}: {e}")

    opus_count = len(list(REC_DIR.glob("*.opus")))
    bin_count = len(list(REC_DIR.glob("*.bin")))

    log(f"[STARTUP] cleanup done deleted_wav={deleted_wav} pending_opus={opus_count} pending_bin={bin_count}")


def next_wav_path() -> pathlib.Path:
    corrected = datetime.now() + timedelta(seconds=_time_offset_sec)
    ts = corrected.strftime("%Y%m%d_%H%M%S")
    base = REC_DIR / f"rec2_{ts}.wav"
    if not base.exists():
        return base

    suffix = 1
    while True:
        p = REC_DIR / f"rec2_{ts}_{suffix:02d}.wav"
        if not p.exists():
            return p
        suffix += 1


def opus_path_from_wav(wav_path: pathlib.Path) -> pathlib.Path:
    return wav_path.with_suffix(".opus")


def encrypted_path_from_wav(wav_path: pathlib.Path) -> pathlib.Path:
    return wav_path.with_suffix(".bin")


def is_valid_enc_size(size: int) -> bool:
    return MIN_VALID_ENC_REC_SIZE < size <= MAX_FILE_SIZE


def format_bytes(num_bytes: int) -> str:
    """Hien thi dung luong de doc trong log."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def upload_speed_text(size_bytes: int, elapsed_sec: float) -> str:
    """Tinh toc do upload theo KB/s, MB/s va Mbps."""
    if elapsed_sec <= 0:
        return "speed=unknown"

    kb_s = size_bytes / 1024 / elapsed_sec
    mb_s = size_bytes / (1024 * 1024) / elapsed_sec
    mbps = size_bytes * 8 / 1_000_000 / elapsed_sec

    if mb_s >= 1:
        return f"speed={mb_s:.2f} MB/s ({mbps:.2f} Mbps)"
    return f"speed={kb_s:.1f} KB/s ({mbps:.2f} Mbps)"


def current_ssid() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["iwgetid", "-r"],
            text=True,
            timeout=2
        ).strip()
        return out or None
    except Exception:
        return None



def current_nm_connection() -> Optional[str]:
    """Return NetworkManager active connection name for WIFI_IFACE, e.g. phantom_hidden/HisoEco."""
    try:
        out = subprocess.check_output(
            ["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "dev"],
            text=True,
            timeout=3,
        )
        for line in out.splitlines():
            parts = line.split(":", 2)
            if len(parts) == 3 and parts[0] == WIFI_IFACE and parts[1] == "connected":
                return parts[2] or None
        return None
    except Exception:
        return None


def _run_cmd_logged(cmd: list[str], timeout_sec: int, mask_password: bool = True) -> tuple[int, str, str]:
    """Run command and log stdout/stderr without leaking Wi-Fi password."""
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()

        safe_cmd = " ".join(cmd)
        if mask_password:
            safe_cmd = safe_cmd.replace(WIFI_PASSWORD, "********")
            safe_cmd = safe_cmd.replace(_runtime_wifi_password, "********")

        log(f"[WIFI] cmd={safe_cmd} rc={proc.returncode}")
        if out:
            log(f"[WIFI] stdout: {out}")
        if err:
            log(f"[WIFI] stderr: {err}")
        return proc.returncode, out, err
    except Exception as e:
        log(f"[WIFI] command exception: {e}")
        return 999, "", str(e)

def _cleanup_duplicate_profiles(profile_name: str) -> None:
    """Delete all but the first profile with this name to avoid nmcli duplicate warnings."""
    try:
        out = subprocess.check_output(
            ["nmcli", "-t", "-f", "NAME,UUID", "connection", "show"],
            text=True, timeout=5,
        )
        uuids = [line.split(":")[1] for line in out.splitlines()
                 if line.split(":")[0] == profile_name]
        for uuid in uuids[1:]:
            subprocess.run(["nmcli", "connection", "delete", uuid],
                           timeout=5, check=False, capture_output=True)
            log(f"[WIFI] deleted duplicate profile {profile_name} uuid={uuid}")
    except Exception as e:
        log(f"[WIFI] cleanup duplicate profiles error: {e}")


def _profile_exists(profile_name: str) -> bool:
    """Return True if at least one NM connection with this name exists."""
    try:
        out = subprocess.check_output(
            ["nmcli", "-t", "-f", "NAME", "connection", "show"],
            text=True, timeout=5,
        )
        return any(line.strip() == profile_name for line in out.splitlines())
    except Exception:
        return False


def ensure_hidden_wifi_profile() -> bool:
    """
    Dam bao profile NetworkManager phantom_hidden ton tai va co cau hinh WPA-PSK dung.
    Cach nay tranh loi:
      Error: 802-11-wireless-security.key-mgmt: property is missing.
    Service nen chay bang root de nmcli co quyen sua/ket noi WiFi.
    """
    _cleanup_duplicate_profiles(WIFI_CONNECTION_PROFILE)

    if not _profile_exists(WIFI_CONNECTION_PROFILE):
        log(f"[WIFI] profile missing, create: {WIFI_CONNECTION_PROFILE}")
        add_cmd = [
            "nmcli", "connection", "add",
            "type", "wifi",
            "ifname", WIFI_IFACE,
            "con-name", WIFI_CONNECTION_PROFILE,
            "ssid", _runtime_upload_target_ssid,
        ]
        rc_add, _, _ = _run_cmd_logged(add_cmd, timeout_sec=10)
        if rc_add != 0:
            log("[WIFI] FAIL create hidden WiFi profile")
            return False

    autoconnect_mode = "yes"
    autoconnect_priority = "998"
    autoconnect_retries = "-1"

    modify_cmds = [
        ["nmcli", "connection", "modify", WIFI_CONNECTION_PROFILE, "802-11-wireless.ssid", _runtime_upload_target_ssid],
        ["nmcli", "connection", "modify", WIFI_CONNECTION_PROFILE, "802-11-wireless.hidden", "yes"],
        ["nmcli", "connection", "modify", WIFI_CONNECTION_PROFILE, "wifi-sec.key-mgmt", "wpa-psk"],
        ["nmcli", "connection", "modify", WIFI_CONNECTION_PROFILE, "wifi-sec.psk", _runtime_wifi_password],
        ["nmcli", "connection", "modify", WIFI_CONNECTION_PROFILE, "connection.autoconnect", autoconnect_mode],
        ["nmcli", "connection", "modify", WIFI_CONNECTION_PROFILE, "connection.autoconnect-priority", autoconnect_priority],
        ["nmcli", "connection", "modify", WIFI_CONNECTION_PROFILE, "connection.autoconnect-retries", autoconnect_retries],
    ]

    for cmd in modify_cmds:
        rc_mod, _, _ = _run_cmd_logged(cmd, timeout_sec=10)
        if rc_mod != 0:
            log(f"[WIFI] FAIL modify profile: {WIFI_CONNECTION_PROFILE}")
            return False

    return True


def ensure_mgmt_wifi_profile() -> bool:
    """
    Dam bao profile NetworkManager phantom_mgmt ton tai va co cau hinh WPA-PSK dung.
    SSID: MGMT_TARGET_SSID (...0001), priority 999 (cao hon phantom_hidden 998).
    Tuong duong chay tay:
      nmcli connection add type wifi ifname wlan0 con-name phantom_mgmt ssid "...0001"
      nmcli connection modify phantom_mgmt 802-11-wireless.hidden yes \\
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "12345678" \\
        connection.autoconnect yes connection.autoconnect-priority 999
    """
    _cleanup_duplicate_profiles(MGMT_WIFI_CONNECTION_PROFILE)

    if not _profile_exists(MGMT_WIFI_CONNECTION_PROFILE):
        log(f"[WIFI] mgmt profile missing, create: {MGMT_WIFI_CONNECTION_PROFILE}")
        add_cmd = [
            "nmcli", "connection", "add",
            "type", "wifi",
            "ifname", WIFI_IFACE,
            "con-name", MGMT_WIFI_CONNECTION_PROFILE,
            "ssid", MGMT_TARGET_SSID,
        ]
        rc_add, _, _ = _run_cmd_logged(add_cmd, timeout_sec=10)
        if rc_add != 0:
            log("[WIFI] FAIL create mgmt WiFi profile")
            return False

    modify_cmds = [
        ["nmcli", "connection", "modify", MGMT_WIFI_CONNECTION_PROFILE, "802-11-wireless.ssid", MGMT_TARGET_SSID],
        ["nmcli", "connection", "modify", MGMT_WIFI_CONNECTION_PROFILE, "802-11-wireless.hidden", "no"],
        ["nmcli", "connection", "modify", MGMT_WIFI_CONNECTION_PROFILE, "wifi-sec.key-mgmt", "wpa-psk"],
        ["nmcli", "connection", "modify", MGMT_WIFI_CONNECTION_PROFILE, "wifi-sec.psk", WIFI_PASSWORD],
        ["nmcli", "connection", "modify", MGMT_WIFI_CONNECTION_PROFILE, "connection.autoconnect", "yes"],
        ["nmcli", "connection", "modify", MGMT_WIFI_CONNECTION_PROFILE, "connection.autoconnect-priority", "999"],
        ["nmcli", "connection", "modify", MGMT_WIFI_CONNECTION_PROFILE, "connection.autoconnect-retries", "-1"],
    ]

    for cmd in modify_cmds:
        rc_mod, _, _ = _run_cmd_logged(cmd, timeout_sec=10)
        if rc_mod != 0:
            log(f"[WIFI] FAIL modify mgmt profile: {MGMT_WIFI_CONNECTION_PROFILE}")
            return False

    log(f"[WIFI] mgmt profile ready: {MGMT_WIFI_CONNECTION_PROFILE} ssid={MGMT_TARGET_SSID} priority=999")
    return True


def connect_to_ssid_once(ssid: str, hidden: bool, connect_timeout_sec: int = WIFI_CONNECT_TIMEOUT_SEC) -> bool:
    """
    Ket noi WiFi upload bang profile NetworkManager phantom_hidden.
    Khong dung: nmcli dev wifi connect <ssid> password ... hidden yes
    vi lenh do tren Pi cua ban da loi key-mgmt.
    """
    now_ssid = current_ssid()
    now_con = current_nm_connection()

    if now_ssid == ssid or now_con == WIFI_CONNECTION_PROFILE:
        log(f"[WIFI] already connected target: ssid={now_ssid} connection={now_con}")
        return True

    log(
        f"[WIFI] try hidden profile once, timeout={connect_timeout_sec}s "
        f"profile={WIFI_CONNECTION_PROFILE} ssid={ssid} hidden={hidden}"
    )

    cmd = [
        "nmcli", "-w", str(connect_timeout_sec),
        "connection", "up", WIFI_CONNECTION_PROFILE,
        "ifname", WIFI_IFACE,
    ]

    with _wifi_nmcli_lock:
        rc, _, _ = _run_cmd_logged(cmd, timeout_sec=connect_timeout_sec + 5)
    time.sleep(1)

    new_ssid = current_ssid()
    new_con = current_nm_connection()

    if rc == 0 and (new_ssid == ssid or new_con == WIFI_CONNECTION_PROFILE):
        log(f"[WIFI] connected target OK: ssid={new_ssid} connection={new_con}")
        return True

    log(f"[WIFI] first profile up failed/not target: ssid={new_ssid} connection={new_con}")
    log("[WIFI] try prepare hidden profile then retry")

    if not ensure_hidden_wifi_profile():
        log("[WIFI] profile prepare failed")
        return False

    with _wifi_nmcli_lock:
        rc, _, _ = _run_cmd_logged(cmd, timeout_sec=connect_timeout_sec + 5)
    time.sleep(1)

    new_ssid = current_ssid()
    new_con = current_nm_connection()

    if rc == 0 and (new_ssid == ssid or new_con == WIFI_CONNECTION_PROFILE):
        log(f"[WIFI] connected target OK after prepare: ssid={new_ssid} connection={new_con}")
        return True

    log(f"[WIFI] target not connected after profile retry: ssid={new_ssid} connection={new_con}")
    return False


def wifi_manager_worker() -> None:
    """
    State machine quan ly WiFi duy nhat:
    - Startup: uu tien ket noi ...0002 (upload), neu khong co thi thu ...0001 (mgmt).
    - Da ket noi 1 trong 2: giu nguyen, khong reconnect.
    - Upload xong ...0002 va ngat ket noi: cho 2 phut roi quet lai.
    - Khong thay ca 2: cho 2 phut roi quet lai.
    - ...0001: giu den khi mat tin hieu thi thoi.
    """
    server_running = False

    def _start_mgmt_if_needed():
        nonlocal server_running
        if not server_running:
            start_mgmt_server()
            server_running = True
            notify_device_connection()

    def _stop_mgmt_if_needed():
        nonlocal server_running
        if server_running:
            stop_mgmt_server()
            server_running = False

    def _try_connect_upload() -> bool:
        if not ensure_hidden_wifi_profile():
            return False
        # Ngat WiFi hien tai neu dang ket noi WiFi khac (khong phai phantom)
        cur_con = current_nm_connection()
        if cur_con and cur_con not in (WIFI_CONNECTION_PROFILE, MGMT_WIFI_CONNECTION_PROFILE):
            log(f"[WIFI] disconnect current WiFi before switching: {cur_con}")
            with _wifi_nmcli_lock:
                _run_cmd_logged(
                    ["nmcli", "connection", "down", cur_con],
                    timeout_sec=10,
                    mask_password=False,
                )
            time.sleep(1)
        cmd = [
            "nmcli", "-w", str(WIFI_CONNECT_FAST_TIMEOUT_SEC),
            "connection", "up", WIFI_CONNECTION_PROFILE,
            "ifname", WIFI_IFACE,
        ]
        with _wifi_nmcli_lock:
            rc, _, _ = _run_cmd_logged(cmd, timeout_sec=WIFI_CONNECT_FAST_TIMEOUT_SEC + 5)
        time.sleep(1)
        ssid = current_ssid()
        con = current_nm_connection()
        return rc == 0 and (ssid == _runtime_upload_target_ssid or con == WIFI_CONNECTION_PROFILE)

    def _try_connect_mgmt() -> bool:
        cmd = [
            "nmcli", "-w", str(WIFI_CONNECT_FAST_TIMEOUT_SEC),
            "connection", "up", MGMT_WIFI_CONNECTION_PROFILE,
            "ifname", WIFI_IFACE,
        ]
        with _wifi_nmcli_lock:
            rc, _, _ = _run_cmd_logged(cmd, timeout_sec=WIFI_CONNECT_FAST_TIMEOUT_SEC + 5)
        time.sleep(1)
        ssid = current_ssid()
        con = current_nm_connection()
        return rc == 0 and (ssid == MGMT_TARGET_SSID or con == MGMT_WIFI_CONNECTION_PROFILE)

    was_connected = False
    disconnected_at: float = 0.0
    upload_triggered = False  # Da trigger upload lan dau khi ket noi ...0002 chua
    mgmt_notify_last: float = 0.0  # Thoi diem ban notify_device_connection lan cuoi
    was_on_mgmt = False  # Track de phat hien vua ket noi moi vao ...0001

    while True:
        try:
            ssid = current_ssid()
            con = current_nm_connection()
            on_upload = (ssid == _runtime_upload_target_ssid or con == WIFI_CONNECTION_PROFILE)
            on_mgmt = (ssid == MGMT_TARGET_SSID or con == MGMT_WIFI_CONNECTION_PROFILE)

            if on_upload:
                _stop_mgmt_if_needed()
                was_connected = True
                disconnected_at = 0.0
                # Vua ket noi ...0002: trigger upload ngay lap tuc
                if not upload_triggered:
                    upload_triggered = True
                    log("[WIFI-MGR] connected upload WiFi, trigger upload now")
                    upload_all_rec_bins(force=True)
                time.sleep(IMMEDIATE_HIDDEN_WIFI_CHECK_SEC)

            elif on_mgmt:
                _start_mgmt_if_needed()
                was_connected = True
                disconnected_at = 0.0
                upload_triggered = False
                now_mono = time.monotonic()
                # Gui ngay khi vua ket noi moi, hoac theo chu_ky_quet_wifi_phut
                just_connected = not was_on_mgmt
                if just_connected or (now_mono - mgmt_notify_last >= _runtime_wifi_retry_interval_sec):
                    mgmt_notify_last = now_mono
                    notify_device_connection()
                was_on_mgmt = True
                time.sleep(IMMEDIATE_HIDDEN_WIFI_CHECK_SEC)

            else:
                _stop_mgmt_if_needed()
                was_on_mgmt = False

                # Ghi nhan thoi diem mat ket noi
                if was_connected:
                    was_connected = False
                    upload_triggered = False
                    disconnected_at = time.monotonic()
                    log(f"[WIFI-MGR] lost connection, wait {WIFI_SCAN_INTERVAL_SEC}s before rescan")

                # Sau khi upload xong va ngat ket noi chu dong
                if _wifi_upload_done_event.is_set():
                    _wifi_upload_done_event.clear()
                    disconnected_at = time.monotonic()
                    log(f"[WIFI-MGR] post-upload cooldown, wait {WIFI_SCAN_INTERVAL_SEC}s then rescan")
                    time.sleep(WIFI_SCAN_INTERVAL_SEC)
                    continue

                # Cho du 2 phut ke tu khi mat ket noi
                if disconnected_at > 0:
                    elapsed = time.monotonic() - disconnected_at
                    if elapsed < WIFI_SCAN_INTERVAL_SEC:
                        wait_left = int(WIFI_SCAN_INTERVAL_SEC - elapsed)
                        log(f"[WIFI-MGR] cooldown {wait_left}s remaining")
                        time.sleep(min(wait_left, IMMEDIATE_HIDDEN_WIFI_CHECK_SEC))
                        continue
                    disconnected_at = 0.0

                log("[WIFI-MGR] scanning: try upload WiFi (...0002) first")
                if _try_connect_upload():
                    log(f"[WIFI-MGR] connected upload WiFi: {_runtime_upload_target_ssid}")
                    continue
                log("[WIFI-MGR] upload WiFi not found, try mgmt WiFi (...0001)")
                if _try_connect_mgmt():
                    log(f"[WIFI-MGR] connected mgmt WiFi: {MGMT_TARGET_SSID}")
                    continue
                log(f"[WIFI-MGR] neither WiFi found, wait {WIFI_SCAN_INTERVAL_SEC}s")
                disconnected_at = time.monotonic()
                time.sleep(WIFI_SCAN_INTERVAL_SEC)

        except Exception as e:
            log(f"[WIFI-MGR] exception: {e}")
            time.sleep(IMMEDIATE_HIDDEN_WIFI_CHECK_SEC)


def disconnect_upload_wifi_after_success(reason: str = "upload_success") -> None:
    """
    Sau khi upload thanh cong het file .bin, ngat profile WiFi upload.
    Sau do set event de wifi_manager_worker biet can cho 2 phut roi quet lai.
    """
    if not DISCONNECT_WIFI_AFTER_SUCCESS_UPLOAD:
        return

    now_ssid = current_ssid()
    now_con = current_nm_connection()

    if now_ssid != _runtime_upload_target_ssid and now_con != WIFI_CONNECTION_PROFILE:
        log(f"[WIFI] disconnect skip: not on upload WiFi ssid={now_ssid} connection={now_con}")
        return

    log(f"[WIFI] disconnect upload WiFi after success: profile={WIFI_CONNECTION_PROFILE} reason={reason}")

    _run_cmd_logged(
        ["nmcli", "connection", "modify", WIFI_CONNECTION_PROFILE, "connection.autoconnect", "no"],
        timeout_sec=10,
        mask_password=False,
    )

    cmd = [
        "nmcli", "-w", str(WIFI_DISCONNECT_TIMEOUT_SEC),
        "connection", "down", WIFI_CONNECTION_PROFILE,
    ]

    _run_cmd_logged(cmd, timeout_sec=WIFI_DISCONNECT_TIMEOUT_SEC + 5, mask_password=False)

    time.sleep(2)
    log(f"[WIFI] after disconnect: ssid={current_ssid()} connection={current_nm_connection()}")
    _wifi_upload_done_event.set()



def _rms_dbfs_from_wav_tail(wav_path: pathlib.Path, sample_rate: int, channels: int, fmt: str) -> Optional[float]:
    """Doc phan cuoi file WAV dang ghi, tinh RMS va tra ve dBFS."""
    fmt_upper = fmt.upper()
    if fmt_upper in ("S16_LE", "S16_BE"):
        bytes_per_sample, max_val = 2, 32768.0
        pack_char, endian = "h", "<" if fmt_upper == "S16_LE" else ">"
    elif fmt_upper in ("S32_LE", "S32_BE", "S24_LE", "S24_BE"):
        bytes_per_sample, max_val = 4, 2147483648.0
        pack_char, endian = "i", "<" if "LE" in fmt_upper else ">"
    else:
        return None

    frame_size = bytes_per_sample * channels
    tail_bytes = sample_rate * 2 * frame_size  # doc 2 giay cuoi

    try:
        size = wav_path.stat().st_size
        if size <= 44:
            return None
        data_size = size - 44
        read_size = min(tail_bytes, data_size)
        offset = 44 + (data_size - read_size)
        with wav_path.open("rb") as f:
            f.seek(offset)
            raw = f.read(read_size)
    except Exception:
        return None

    count = len(raw) // bytes_per_sample
    if count == 0:
        return None

    samples = struct.unpack(f"{endian}{count}{pack_char}", raw[:count * bytes_per_sample])
    rms = math.sqrt(sum(s * s for s in samples) / count)
    if rms == 0:
        return -96.0
    return 20.0 * math.log10(rms / max_val)


def record_wav_segment(wav_path: pathlib.Path, duration_sec: int) -> bool:
    cmd = [
        "arecord",
        "-D", _runtime_arecord_device,
        "-c", _runtime_arecord_channels,
        "-r", _runtime_arecord_rate,
        "-f", _runtime_arecord_format,
        "-d", str(duration_sec),
        "-t", "wav",
        str(wav_path),
    ]

    t0 = time.time()

    try:
        proc = subprocess.Popen(cmd)
    except Exception as e:
        log(f"[REC] Exception: {e}")
        delete_wav_safely(wav_path, reason="record_exception")
        return False

    stop_event = threading.Event()

    def _level_monitor() -> None:
        rate = int(_runtime_arecord_rate)
        ch = int(_runtime_arecord_channels)
        fmt = _runtime_arecord_format
        elapsed_s = 0
        while not stop_event.wait(5.0):
            elapsed_s += 5
            db = _rms_dbfs_from_wav_tail(wav_path, rate, ch, fmt)
            if db is not None:
                if db >= -20:
                    label = "LOUD"
                elif db >= -45:
                    label = "normal"
                else:
                    label = "quiet"
                log(f"[REC-LEVEL] t={elapsed_s}s dBFS={db:.1f} ({label})")

    monitor = threading.Thread(target=_level_monitor, daemon=True, name="rec-level-monitor")
    monitor.start()

    rc = -1
    try:
        proc.wait(timeout=duration_sec + 15)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        rc = proc.returncode
    except Exception as e:
        log(f"[REC] Exception: {e}")
        stop_event.set()
        monitor.join(timeout=6)
        delete_wav_safely(wav_path, reason="record_exception")
        return False

    stop_event.set()
    monitor.join(timeout=6)

    elapsed = int((time.time() - t0) * 1000)

    if rc != 0:
        log(f"[REC] FAIL rc={rc} ms={elapsed} duration={duration_sec}s")
        delete_wav_safely(wav_path, reason="record_returncode_fail")
        return False

    if not wav_path.exists() or wav_path.stat().st_size <= 44:
        log(f"[REC] FAIL empty file: {wav_path}")
        delete_wav_safely(wav_path, reason="empty_or_invalid_wav")
        return False

    log(f"[REC] OK file={wav_path.name} size={wav_path.stat().st_size} ms={elapsed} duration={duration_sec}s")
    return True


def _calc_rms_dbfs_from_raw(data: bytes, channels: int, fmt: str) -> Optional[float]:
    """Tinh dBFS tu raw PCM bytes (khong co WAV header)."""
    fmt_upper = fmt.upper()
    if fmt_upper in ("S16_LE", "S16_BE"):
        bytes_per_sample, max_val = 2, 32768.0
        pack_char, endian = "h", "<" if fmt_upper == "S16_LE" else ">"
    elif fmt_upper in ("S32_LE", "S32_BE", "S24_LE", "S24_BE"):
        bytes_per_sample, max_val = 4, 2147483648.0
        pack_char, endian = "i", "<" if "LE" in fmt_upper else ">"
    else:
        return None

    count = len(data) // bytes_per_sample
    if count == 0:
        return None

    samples = struct.unpack(f"{endian}{count}{pack_char}", data[:count * bytes_per_sample])
    rms = math.sqrt(sum(s * s for s in samples) / count)
    if rms == 0:
        return -96.0
    return 20.0 * math.log10(rms / max_val)


def record_wav_segment_vad(wav_path_factory) -> Optional[pathlib.Path]:
    """
    2-phase VAD:
    Phase 1 – Nghe (khong ghi file): arecord -t raw | doc PCM chunk, tinh dBFS.
              Khi dBFS >= threshold -> sang Phase 2.
    Phase 2 – Ghi file that: arecord -d max_duration output.wav.
              - Im lang lien tuc >= silence_timeout -> kill -> luu
              - Het max_duration -> arecord tu dung -> luu
    Tra ve path file WAV neu thanh cong, None neu that bai/khong co tieng.
    """
    threshold = _runtime_vad_threshold_dbfs
    silence_timeout = _runtime_vad_silence_timeout_sec
    max_duration = _runtime_vad_max_duration_sec
    monitor_interval = VAD_DEFAULT_MONITOR_INTERVAL_SEC
    ch = int(_runtime_arecord_channels)
    rate = int(_runtime_arecord_rate)
    fmt = _runtime_arecord_format
    # chunk = ~0.3s PCM data de tinh dBFS nhanh
    bytes_per_sample = 4 if fmt.upper() in ("S32_LE", "S32_BE", "S24_LE", "S24_BE") else 2
    chunk_frames = int(rate * 0.3)
    chunk_bytes = chunk_frames * ch * bytes_per_sample

    # ── Phase 1: Nghe, khong ghi file ────────────────────────────────────────
    log(f"[VAD] phase1 listening threshold={threshold}dBFS ...")
    listen_cmd = [
        "arecord",
        "-D", _runtime_arecord_device,
        "-c", _runtime_arecord_channels,
        "-r", _runtime_arecord_rate,
        "-f", _runtime_arecord_format,
        "-t", "raw",
    ]

    try:
        listen_proc = subprocess.Popen(listen_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except Exception as e:
        log(f"[VAD] Exception start listen: {e}")
        return None

    triggered = False
    try:
        while True:
            chunk = listen_proc.stdout.read(chunk_bytes)
            if not chunk:
                break
            db = _calc_rms_dbfs_from_raw(chunk, ch, fmt)
            if db is not None and db >= threshold:
                log(f"[VAD] audio detected dBFS={db:.1f} -> start recording")
                triggered = True
                break
    finally:
        listen_proc.kill()
        try:
            listen_proc.stdout.close()
        except Exception:
            pass
        listen_proc.wait()

    if not triggered:
        return None

    # ── Phase 2: Ghi file that ────────────────────────────────────────────────
    wav_path = wav_path_factory()
    log(f"[VAD] phase2 recording file={wav_path.name} silence={silence_timeout}s max={max_duration}s")
    t0 = time.time()

    rec_cmd = [
        "arecord",
        "-D", _runtime_arecord_device,
        "-c", _runtime_arecord_channels,
        "-r", _runtime_arecord_rate,
        "-f", _runtime_arecord_format,
        "-d", str(max_duration),
        "-t", "wav",
        str(wav_path),
    ]

    try:
        rec_proc = subprocess.Popen(rec_cmd)
    except Exception as e:
        log(f"[VAD] Exception start rec: {e}")
        return None

    kill_flag = threading.Event()
    stop_event = threading.Event()
    silence_since: list[Optional[float]] = [None]

    def _silence_monitor() -> None:
        while not stop_event.wait(float(monitor_interval)):
            db = _rms_dbfs_from_wav_tail(wav_path, rate, ch, fmt)
            if db is None:
                continue
            elapsed = int(time.time() - t0)
            if db >= threshold:
                silence_since[0] = None
                log(f"[VAD] rec t={elapsed}s dBFS={db:.1f} active")
            else:
                if silence_since[0] is None:
                    silence_since[0] = time.monotonic()
                    log(f"[VAD] rec t={elapsed}s dBFS={db:.1f} silence started")
                else:
                    silent_for = time.monotonic() - silence_since[0]
                    log(f"[VAD] rec t={elapsed}s dBFS={db:.1f} silent={silent_for:.0f}s/{silence_timeout}s")
                    if silent_for >= silence_timeout:
                        log("[VAD] silence timeout -> stop")
                        kill_flag.set()
                        return

    monitor = threading.Thread(target=_silence_monitor, daemon=True, name="vad-silence-monitor")
    monitor.start()

    while rec_proc.poll() is None:
        if kill_flag.is_set():
            rec_proc.kill()
            rec_proc.wait()
            break
        time.sleep(0.5)

    stop_event.set()
    monitor.join(timeout=monitor_interval + 2)

    elapsed_ms = int((time.time() - t0) * 1000)
    rc = rec_proc.returncode

    if rc not in (0, -9, None):
        log(f"[VAD] arecord failed rc={rc} ms={elapsed_ms}")
        delete_wav_safely(wav_path, reason="vad_arecord_fail")
        return None

    if not wav_path.exists() or wav_path.stat().st_size <= 44:
        log(f"[VAD] empty wav: {wav_path.name}")
        delete_wav_safely(wav_path, reason="vad_empty_wav")
        return None

    log(f"[VAD] OK file={wav_path.name} size={wav_path.stat().st_size} ms={elapsed_ms}")
    return wav_path


def compress_wav_to_opus(wav_path: pathlib.Path, opus_path: pathlib.Path, delete_wav: bool = True) -> bool:
    if not wav_path.exists():
        log(f"[OPUS] FAIL missing wav: {wav_path.name}")
        return False

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(wav_path),
        "-af", f"volume={AUDIO_GAIN_DB}dB,alimiter=limit=0.95",
        "-c:a", "libopus",
        "-b:a", OPUS_BITRATE,
        "-application", OPUS_APPLICATION,
        str(opus_path),
    ]

    t0 = time.time()

    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
    except Exception as e:
        log(f"[OPUS] Exception: {e}")
        delete_opus_safely(opus_path, reason="opus_exception")
        return False

    elapsed = int((time.time() - t0) * 1000)

    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        log(f"[OPUS] FAIL rc={proc.returncode} ms={elapsed} err={err}")
        delete_opus_safely(opus_path, reason="opus_returncode_fail")
        return False

    if not opus_path.exists() or opus_path.stat().st_size <= 64:
        log(f"[OPUS] FAIL empty/invalid opus: {opus_path.name}")
        delete_opus_safely(opus_path, reason="empty_or_invalid_opus")
        return False

    if delete_wav:
        delete_wav_safely(wav_path, reason="opus_ok")

    log(f"[OPUS] OK: {wav_path.name} -> {opus_path.name} size={opus_path.stat().st_size} ms={elapsed}")
    return True


def load_phtm_key(path: pathlib.Path = PHTM_KEY_PATH) -> bytes:
    """Load 32-byte PHANTOM master key, same key used by the GUI decrypt tab."""
    try:
        data = path.read_bytes()
    except Exception as e:
        raise FileNotFoundError(f"Cannot read key file: {path} ({e})")

    if len(data) < PHTM_KEY_SIZE:
        raise ValueError(f"Key file too short: {len(data)} bytes, need at least {PHTM_KEY_SIZE}")

    return data[:PHTM_KEY_SIZE]


def phtm_derive(master: bytes) -> tuple[bytes, bytes, bytes]:
    """Derive AES-GCM, HMAC-SHA256 and ChaCha20 keys exactly like GUI PHANTOM."""
    dk = lambda tag: hashlib.sha256(master + tag).digest()
    return dk(b"AES-GCM"), dk(b"HMAC-SHA256"), dk(b"CHACHA20")


def phtm_encrypt_3layer(data: bytes, master: bytes) -> bytes:
    """
    PHANTOM 3-layer raw encryption compatible with GUI decrypt logic:
      L1: AES-GCM encrypt plain data
      L2: HMAC-SHA256 over AES nonce + ciphertext/tag
      L3: ChaCha20-Poly1305 encrypt the whole payload

    Output returned here does NOT include magic header.
    Final file format is: b"PHTM3L1" + output.
    """
    k_aes, k_hmac, k_chacha = phtm_derive(master)

    # Layer 1: AES-GCM
    n_aes = os.urandom(12)
    ct1 = AESGCM(k_aes).encrypt(n_aes, data, None)
    inner = n_aes + ct1

    # Layer 2: HMAC-SHA256 integrity tag
    h = _hmac.HMAC(k_hmac, _hashes.SHA256(), backend=_backend())
    h.update(inner)
    hmac_tag = h.finalize()

    # Layer 3: ChaCha20-Poly1305
    n_cha = os.urandom(12)
    payload = inner + hmac_tag
    ct3 = ChaCha20Poly1305(k_chacha).encrypt(n_cha, payload, None)

    return n_cha + ct3

def phtm_wrap_session_key_with_public(session_key: bytes, recipient_public_raw: bytes) -> bytes:
    if len(recipient_public_raw) != PHTM_KEY_SIZE:
        raise ValueError(f"public key must be {PHTM_KEY_SIZE} bytes")

    recipient_pub = x25519.X25519PublicKey.from_public_bytes(recipient_public_raw)
    eph_priv = x25519.X25519PrivateKey.generate()
    eph_pub_raw = eph_priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    shared = eph_priv.exchange(recipient_pub)
    wrap_key = HKDF(
        algorithm=_hashes.SHA256(),
        length=32,
        salt=None,
        info=b"PHTM-X25519-WRAP",
    ).derive(shared)

    wrap_nonce = os.urandom(12)
    wrapped_key = AESGCM(wrap_key).encrypt(wrap_nonce, session_key, None)
    return eph_pub_raw + wrap_nonce + wrapped_key


def phtm_pack_plain_with_ext(ext: str, data: bytes) -> bytes:
    """Pack plaintext bytes with original extension for decrypt-side restore."""
    clean_ext = (ext or "").strip().lower()
    if not clean_ext.startswith("."):
        clean_ext = f".{clean_ext}" if clean_ext else ""
    ext_bytes = clean_ext.encode("ascii", errors="ignore")
    if len(ext_bytes) > 31:
        ext_bytes = ext_bytes[:31]
    return PHRAW1_MAGIC + bytes([len(ext_bytes)]) + ext_bytes + data

def phtm_encrypt_hybrid(data: bytes, recipient_public_raw: bytes) -> bytes:
    session_key = os.urandom(PHTM_KEY_SIZE)
    payload = phtm_encrypt_3layer(data, session_key)
    wrapped = phtm_wrap_session_key_with_public(session_key, recipient_public_raw)
    return PHTM3L2_MAGIC + wrapped + payload



def phtm_pack_bin(payload: bytes) -> bytes:
    """Pack as PHANTOM container: magic + version + md5 + payload_len + payload."""
    md5 = hashlib.md5(payload).digest()
    return PHTM_MAGIC + struct.pack("<I", PHTM_VERSION) + md5 + struct.pack("<I", len(payload)) + payload

def encrypt_file_3layer(
    plain_path: pathlib.Path,
    enc_path: pathlib.Path,
    delete_plain: bool = True
) -> bool:
    """Plain file bytes -> hybrid payload -> PHTM v2 .bin."""
    if not plain_path.exists():
        log(f"[PHTM3L1] FAIL missing plain file: {plain_path.name}")
        return False

    try:
        data = plain_path.read_bytes()
    except Exception as e:
        log(f"[PHTM3L1] FAIL read {plain_path.name}: {e}")
        return False

    if not data:
        log(f"[PHTM3L1] FAIL empty plain file: {plain_path.name}")
        return False

    try:
        recipient_public = load_phtm_key(pathlib.Path(_runtime_public_key_path))
        plain_blob = phtm_pack_plain_with_ext(plain_path.suffix, data)
        hybrid_payload = phtm_encrypt_hybrid(plain_blob, recipient_public)
        blob = phtm_pack_bin(hybrid_payload)
        enc_path.write_bytes(blob)
    except Exception as e:
        log(f"[PHTM3L1] FAIL encrypt {plain_path.name}: {e}")
        try:
            enc_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False

    size = enc_path.stat().st_size if enc_path.exists() else 0
    min_size = len(PHTM_MAGIC) + 4 + 16 + 4 + len(PHTM3L2_MAGIC) + 32 + 12 + 16 + 12 + 16

    if size <= min_size:
        log(f"[PHTM3L1] FAIL invalid enc size: {enc_path.name} size={size}")
        try:
            enc_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False

    if delete_plain:
        delete_file_safely(plain_path, reason="encrypted_3layer_ok", allowed_suffixes=(".wav", ".opus"))

    log(f"[PHTM3L1] OK: {plain_path.name} -> {enc_path.name} size={size}")
    return True


# Gi alias tn c  cc ch gi c khng phi sa nhiu.
def aes_gcm_encrypt_file(
    plain_path: pathlib.Path,
    enc_path: pathlib.Path,
    delete_plain: bool = True
) -> bool:
    return encrypt_file_3layer(plain_path, enc_path, delete_plain=delete_plain)

def upload_file_to_http_api(local_path: pathlib.Path) -> bool:
    if not local_path.exists():
        return False

    size = local_path.stat().st_size
    if not is_valid_enc_size(size):
        log(f"[UPLOAD] Skip invalid size: {local_path.name} size={size}")
        return False

    url = f"http://{UPLOAD_HOST}:{UPLOAD_PORT}{UPLOAD_PATH}"
    t0 = time.time()

    try:
        with local_path.open("rb") as f:
            files = {"file": (local_path.name, f, "application/octet-stream")}
            resp = requests.post(url, files=files, timeout=90)

        elapsed_sec = time.time() - t0
        elapsed_ms = int(elapsed_sec * 1000)
        ok = resp.status_code in (200, 201)
        speed = upload_speed_text(size, elapsed_sec)

        log(
            f"[UPLOAD] FILE {local_path.name} "
            f"status={resp.status_code} "
            f"size={format_bytes(size)} "
            f"time={elapsed_ms}ms "
            f"{speed}"
        )
        return ok

    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        log(f"[UPLOAD] FAIL {local_path.name} size={format_bytes(size)} time={elapsed_ms}ms err={e}")
        return False


def upload_all_rec_bins(force: bool = False) -> bool:
    global _last_upload_try_monotonic, _runtime_wifi_retry_interval_sec

    # Kiem tra file .bin truoc khi connect WiFi.
    # Neu khong co file can upload thi KHONG ket noi WiFi an.
    bins = sorted(REC_DIR.glob("*.bin"))
    if not bins:
        log("[UPLOAD] No pending .bin files; skip WiFi connect")
        return True

    now_mono = time.monotonic()
    if not force and _last_upload_try_monotonic > 0:
        elapsed = now_mono - _last_upload_try_monotonic
        if elapsed < _runtime_wifi_retry_interval_sec:
            wait_left = int(_runtime_wifi_retry_interval_sec - elapsed)
            log(f"[UPLOAD] Skip: wait {wait_left}s before next WiFi retry")
            return False

    _last_upload_try_monotonic = now_mono

    # Chi upload khi da ket noi san upload WiFi, khong tu connect
    now_ssid = current_ssid()
    now_con = current_nm_connection()
    if now_ssid != _runtime_upload_target_ssid and now_con != WIFI_CONNECTION_PROFILE:
        log(f"[UPLOAD] Skip: not on upload WiFi ssid={now_ssid} connection={now_con}")
        return False

    failed = 0
    uploaded_count = 0
    uploaded_bytes = 0
    skipped_count = 0

    batch_t0 = time.time()
    log(f"[UPLOAD] BATCH start files={len(bins)}")

    for p in bins:
        try:
            size = p.stat().st_size
        except Exception as e:
            log(f"[UPLOAD] FAIL stat {p.name}: {e}")
            failed += 1
            continue

        if not is_valid_enc_size(size):
            log(f"[UPLOAD] Skip invalid bin: {p.name} size={size}")
            skipped_count += 1
            continue

        ok = upload_file_to_http_api(p)

        if ok:
            try:
                p.unlink(missing_ok=True)
                uploaded_count += 1
                uploaded_bytes += size
                log(f"[UPLOAD] DELETE {p.name}")
            except Exception as e:
                log(f"[UPLOAD] FAIL delete uploaded bin {p.name}: {e}")
                failed += 1
        else:
            failed += 1

    batch_elapsed_sec = time.time() - batch_t0
    batch_elapsed_ms = int(batch_elapsed_sec * 1000)
    batch_speed = upload_speed_text(uploaded_bytes, batch_elapsed_sec) if uploaded_bytes > 0 else "speed=0"

    # Thanh cong that su = da upload het file hop le va khong con file bi fail/skip.
    batch_success = failed == 0 and skipped_count == 0 and uploaded_count == len(bins)

    log(
        f"[UPLOAD] BATCH done uploaded={uploaded_count}/{len(bins)} "
        f"failed={failed} skipped={skipped_count} "
        f"success={batch_success} "
        f"total={format_bytes(uploaded_bytes)} "
        f"time={batch_elapsed_ms}ms "
        f"{batch_speed}"
    )

    if batch_success:
        disconnect_upload_wifi_after_success(reason="all_bins_uploaded")
        log(f"[UPLOAD] All .bin uploaded; wifi cooldown {WIFI_SCAN_INTERVAL_SEC}s")

    return batch_success


def process_audio_job(path: pathlib.Path) -> None:
    """
    X l file  lung nn  lung ghi m khng b chn:
    WAV -> Opus -> PHANTOM 3-layer PHTM3L1 .bin -> th upload .bin c/mi.
    """
    try:
        if path.suffix.lower() == ".wav":
            wav_path = path
            opus_path = opus_path_from_wav(wav_path)
            enc_path = encrypted_path_from_wav(wav_path)

            opus_ok = compress_wav_to_opus(wav_path, opus_path, delete_wav=True)
            if not opus_ok:
                log(f"[WORKER] Opus compress failed, keep wav for safety: {wav_path.name}")
                return

            enc_ok = aes_gcm_encrypt_file(opus_path, enc_path, delete_plain=True)
            if not enc_ok:
                log(f"[WORKER] Encrypt failed, keep opus for safety: {opus_path.name}")
                return

        elif path.suffix.lower() == ".opus":
            opus_path = path
            enc_path = opus_path.with_suffix(".bin")

            enc_ok = aes_gcm_encrypt_file(opus_path, enc_path, delete_plain=True)
            if not enc_ok:
                log(f"[WORKER] Encrypt failed, keep opus for safety: {opus_path.name}")
                return

        else:
            log(f"[WORKER] Skip unsupported job: {path.name}")
            return

        upload_ok = upload_all_rec_bins()
        if upload_ok:
            log("[WORKER] Upload pass finished")
        else:
            log("[WORKER] Upload skipped/failed, keep bin files and continue recording")


    except Exception as e:
        log(f"[WORKER] Exception job={path.name}: {e}")


def processing_worker(job_queue: queue.Queue[pathlib.Path]) -> None:
    while True:
        path = job_queue.get()
        try:
            process_audio_job(path)
        finally:
            job_queue.task_done()


def enqueue_leftover_jobs(job_queue: queue.Queue[pathlib.Path]) -> None:
    # u tin m ha/upload cc file Opus cn st, ri x l WAV cn st.
    for p in sorted(REC_DIR.glob("*.opus")):
        job_queue.put(p)
        log(f"[STARTUP] queued leftover opus: {p.name}")

    for p in sorted(REC_DIR.glob("*.wav")):
        job_queue.put(p)
        log(f"[STARTUP] queued leftover wav: {p.name}")


# === File Management HTTP Server (chay khi ket noi MGMT_TARGET_SSID) ===

MGMT_SERVER_HOST = "0.0.0.0"
MGMT_SERVER_PORT = 8765


def _parse_multipart(headers, rfile) -> dict:
    """Parse multipart/form-data. Thay the cgi.FieldStorage (da bi xoa o Python 3.13)."""
    content_type = headers.get("Content-Type", "")
    try:
        content_length = int(headers.get("Content-Length", 0))
    except (ValueError, TypeError):
        content_length = 0
    body = rfile.read(content_length) if content_length > 0 else rfile.read()
    raw = b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body
    msg = _email_mod.message_from_bytes(raw)
    fields: dict = {}
    payload = msg.get_payload()
    if not isinstance(payload, list):
        return fields
    for part in payload:
        disp = part.get("Content-Disposition", "")
        name = filename = None
        for token in disp.split(";"):
            token = token.strip()
            if token.startswith("name="):
                name = token[5:].strip("\"'")
            elif token.startswith("filename="):
                filename = token[9:].strip("\"'")
        if name is not None:
            data = part.get_payload(decode=True) or b""
            fields.setdefault(name, []).append({"filename": filename, "data": data})
    return fields


def _human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n/1024:.1f} KB"
    return f"{n/(1024*1024):.2f} MB"

def _deep_merge_dict(base: dict, patch: dict) -> dict:
    """Merge dict de ho tro cap nhat config mot phan."""
    out = dict(base)
    for k, v in patch.items():
        if isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k] = _deep_merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def _schedule_self_restart(delay_sec: float = 0.8) -> None:
    """Restart service uu tien bang systemctl, fallback self-exit de systemd auto-restart."""
    def _restart_worker() -> None:
        try:
            time.sleep(max(0.1, delay_sec))
            cmds = [
                ["systemctl", "restart", "pi2w_client.service"],
                ["sudo", "-n", "systemctl", "restart", "pi2w_client.service"],
            ]

            for cmd in cmds:
                try:
                    proc = subprocess.run(
                        cmd,
                        text=True,
                        capture_output=True,
                        timeout=15,
                        check=False,
                    )
                    log(f"[MGMT] restart cmd={' '.join(cmd)} rc={proc.returncode}")
                    if proc.stdout:
                        log(f"[MGMT] restart stdout: {proc.stdout.strip()}")
                    if proc.stderr:
                        log(f"[MGMT] restart stderr: {proc.stderr.strip()}")
                    if proc.returncode == 0:
                        return
                except Exception as e:
                    log(f"[MGMT] restart command exception cmd={' '.join(cmd)} err={e}")

            log("[MGMT] restart via systemctl failed, fallback self-exit for systemd auto-restart")
            os._exit(0)
        except Exception as e:
            log(f"[MGMT] restart worker exception: {e}")
            os._exit(0)

    t = threading.Thread(target=_restart_worker, name="service-restart-worker", daemon=True)
    t.start()
class _FileManagementHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            bins = list(REC_DIR.glob("*.bin"))
            self._send_json(200, {
                "ok": True,
                "status": "mgmt",
                "sd": True,
                "mounted": True,
                "file_count": len(bins),
            })
            return

        if path == "/api/filelist":
            files = []
            for p in sorted(REC_DIR.glob("*.bin")):
                try:
                    size = p.stat().st_size
                    files.append({"name": p.name, "size": size, "size_human": _human_size(size)})
                except Exception:
                    pass
            self._send_json(200, {"ok": True, "files": files})
            return


        if path == "/api/config":
            cfg = load_identity_config_from_disk()
            if cfg is None:
                cfg = build_default_identity_config()

            dinh_danh = cfg.get("dinh_danh", {}) if isinstance(cfg, dict) else {}
            cau_hinh = cfg.get("cau_hinh_ghi_am", {}) if isinstance(cfg, dict) else {}

            self._send_json(200, {
                "ok": True,
                "config": {
                    "dinh_danh": {
                        "ma_id": dinh_danh.get("ma_id", ""),
                        "ho_ten": dinh_danh.get("ho_ten", ""),
                        "nam_sinh": dinh_danh.get("nam_sinh", 0),
                        "dia_chi": dinh_danh.get("dia_chi", ""),
                        "ngay_cap_dinh_danh": dinh_danh.get("ngay_cap_dinh_danh", ""),
                        "ten_thiet_bi": dinh_danh.get("ten_thiet_bi", ""),
                        "id_thiet_bi": dinh_danh.get("id_thiet_bi", ""),
                        "dia_chi_thiet_bi": dinh_danh.get("dia_chi_thiet_bi", ""),
                    },
                    "cau_hinh_ghi_am": {
                        "kieu_ghi_am": cau_hinh.get("kieu_ghi_am", DEFAULT_RECORD_MODE),
                        "thoi_luong_ghi_am_phut": cau_hinh.get("thoi_luong_ghi_am_phut", DEFAULT_RECORD_MINUTES),
                        "chu_ky_quet_wifi_phut": cau_hinh.get("chu_ky_quet_wifi_phut", DEFAULT_WIFI_RETRY_MINUTES),
                        "ssid_upload": cau_hinh.get("ssid_upload", UPLOAD_TARGET_SSID),
                        "wifi_password": cau_hinh.get("wifi_password", WIFI_PASSWORD),
                        "duong_dan_public_key": cau_hinh.get("duong_dan_public_key", "public.key"),
                        "vad_nguong_dbfs": cau_hinh.get("vad_nguong_dbfs", VAD_DEFAULT_THRESHOLD_DBFS),
                        "vad_timeout_im_lang_giay": cau_hinh.get("vad_timeout_im_lang_giay", VAD_DEFAULT_SILENCE_TIMEOUT_SEC),
                        "vad_max_thoi_gian_giay": cau_hinh.get("vad_max_thoi_gian_giay", VAD_DEFAULT_MAX_DURATION_SEC),
                        "bat_dau_ghi_am": cau_hinh.get("bat_dau_ghi_am", None),
                        "ket_thuc_ghi_am": cau_hinh.get("ket_thuc_ghi_am", None),
                    },
                },
                "updated_at": cfg.get("updated_at", "") if isinstance(cfg, dict) else "",
                "config_path": str(PI_IDENTITY_CONFIG_PATH),
                "mac_address": get_wlan_mac(),
            })
            return

        if path == "/api/download":
            from urllib.parse import parse_qs
            qs = parse_qs(parsed.query)
            names = qs.get("name", [])
            if not names:
                self._send_json(400, {"ok": False, "error": "missing name"})
                return
            name = names[0]
            # Prevent path traversal
            target = (REC_DIR / name).resolve()
            if not str(target).startswith(str(REC_DIR.resolve())):
                self._send_json(403, {"ok": False, "error": "forbidden"})
                return
            if not target.exists() or not target.is_file():
                self._send_json(404, {"ok": False, "error": "not_found"})
                return
            size = target.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
            self.send_header("Content-Length", str(size))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with target.open("rb") as f:
                shutil.copyfileobj(f, self.wfile)
            target.unlink(missing_ok=True)
            log(f"[MGMT] download+delete: {target.name}")
            return

        if path == "/api/download-all":
            bins = sorted(REC_DIR.glob("*.bin"))
            if not bins:
                self._send_json(404, {"ok": False, "error": "no files"})
                return
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in bins:
                    zf.write(p, p.name)
            zip_bytes = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="recordings.zip"')
            self.send_header("Content-Length", str(len(zip_bytes)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(zip_bytes)
            return

        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/config":
            content_type = self.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                self._send_json(400, {"ok": False, "error": "application/json required"})
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                content_length = 0

            if content_length <= 0:
                self._send_json(400, {"ok": False, "error": "empty body"})
                return

            try:
                raw_body = self.rfile.read(content_length)
                patch_cfg = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                self._send_json(400, {"ok": False, "error": f"invalid json: {e}"})
                return

            if not isinstance(patch_cfg, dict):
                self._send_json(400, {"ok": False, "error": "json body must be object"})
                return

            base_cfg = build_default_identity_config()
            disk_cfg = load_identity_config_from_disk()
            if isinstance(disk_cfg, dict):
                base_cfg = _deep_merge_dict(base_cfg, disk_cfg)

            next_cfg = _deep_merge_dict(base_cfg, patch_cfg)
            next_cfg["updated_at"] = now_iso_local()

            valid, reason = validate_identity_config(next_cfg)
            if not valid:
                self._send_json(400, {"ok": False, "error": f"invalid config: {reason}"})
                return

            if not write_identity_config_atomic(next_cfg, PI_IDENTITY_CONFIG_PATH):
                self._send_json(500, {"ok": False, "error": "failed to write config"})
                return

            log("[MGMT] config updated via API, scheduling service restart")
            self._send_json(200, {
                "ok": True,
                "message": "config saved, service restarting",
                "config_path": str(PI_IDENTITY_CONFIG_PATH),
            })
            _schedule_self_restart()
            return

        if path == "/api/public-key":
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self._send_json(400, {"ok": False, "error": "multipart required"})
                return
            try:
                form = _parse_multipart(self.headers, self.rfile)
                items = form.get("file", [])
                if not items:
                    self._send_json(400, {"ok": False, "error": "missing file field"})
                    return

                item = items[0]
                key_bytes = item.get("data", b"")
                if not isinstance(key_bytes, (bytes, bytearray)):
                    self._send_json(400, {"ok": False, "error": "invalid key data"})
                    return

                key_bytes = bytes(key_bytes)
                if len(key_bytes) < PHTM_KEY_SIZE:
                    self._send_json(400, {"ok": False, "error": f"key too short: need >= {PHTM_KEY_SIZE} bytes"})
                    return

                cfg = load_identity_config_from_disk() or build_default_identity_config()
                cfg_path_raw = ((cfg.get("cau_hinh_ghi_am") or {}).get("duong_dan_public_key") or "public.key")
                key_path = resolve_public_key_path(str(cfg_path_raw))

                key_path.parent.mkdir(parents=True, exist_ok=True)
                key_path.write_bytes(key_bytes)

                log(f"[MGMT] public key updated via API: {key_path} size={len(key_bytes)}")
                self._send_json(200, {
                    "ok": True,
                    "message": "public key saved, service restarting",
                    "key_path": str(key_path),
                    "size": len(key_bytes),
                })
                _schedule_self_restart()
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if path == "/api/download-selected":
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length)
                body = json.loads(raw_body.decode("utf-8"))
                names = body.get("names", [])
                if not names or not isinstance(names, list):
                    self._send_json(400, {"ok": False, "error": "missing or invalid 'names'"})
                    return
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name in names:
                        target = (REC_DIR / os.path.basename(name)).resolve()
                        if not str(target).startswith(str(REC_DIR.resolve())):
                            continue
                        if target.exists() and target.is_file():
                            zf.write(target, target.name)
                zip_bytes = buf.getvalue()
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", 'attachment; filename="selected.zip"')
                self.send_header("Content-Length", str(len(zip_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(zip_bytes)
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/upload":
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self._send_json(400, {"ok": False, "error": "multipart required"})
                return
            try:
                form = _parse_multipart(self.headers, self.rfile)
                items = form.get("file", [])
                if not items:
                    self._send_json(400, {"ok": False, "error": "missing file field"})
                    return
                item = items[0]
                name = os.path.basename(item["filename"] or "upload.bin")
                dest = REC_DIR / name
                dest.write_bytes(item["data"])
                log(f"[MGMT] uploaded: {name} size={dest.stat().st_size}")
                self._send_json(200, {"ok": True, "name": name})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/upload-all":
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self._send_json(400, {"ok": False, "error": "multipart required"})
                return
            try:
                form = _parse_multipart(self.headers, self.rfile)
                saved = []
                for item in form.get("files", []):
                    name = os.path.basename(item["filename"] or "upload.bin")
                    dest = REC_DIR / name
                    dest.write_bytes(item["data"])
                    saved.append(name)
                    log(f"[MGMT] uploaded: {name}")
                self._send_json(200, {"ok": True, "saved": saved})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/delete":
            from urllib.parse import parse_qs
            qs = parse_qs(parsed.query)
            names = qs.get("name", [])
            if not names:
                self._send_json(400, {"ok": False, "error": "missing name"})
                return
            name = names[0]
            target = (REC_DIR / name).resolve()
            if not str(target).startswith(str(REC_DIR.resolve())):
                self._send_json(403, {"ok": False, "error": "forbidden"})
                return
            if not target.exists():
                self._send_json(404, {"ok": False, "error": "not_found"})
                return
            target.unlink(missing_ok=True)
            log(f"[MGMT] deleted: {name}")
            self._send_json(200, {"ok": True})
            return

        if path == "/api/delete-all":
            deleted = []
            for p in list(REC_DIR.glob("*.bin")):
                try:
                    p.unlink(missing_ok=True)
                    deleted.append(p.name)
                except Exception:
                    pass
            log(f"[MGMT] delete-all: {len(deleted)} files")
            self._send_json(200, {"ok": True, "deleted": len(deleted)})
            return

        self._send_json(404, {"ok": False, "error": "not_found"})


_mgmt_server: Optional[ThreadingHTTPServer] = None
_mgmt_server_lock = threading.Lock()


def start_mgmt_server() -> None:
    global _mgmt_server
    with _mgmt_server_lock:
        if _mgmt_server is not None:
            return
        try:
            _mgmt_server = ThreadingHTTPServer((MGMT_SERVER_HOST, MGMT_SERVER_PORT), _FileManagementHandler)
            t = threading.Thread(target=_mgmt_server.serve_forever, name="mgmt-file-server", daemon=True)
            t.start()
            log(f"[MGMT] file server started on port {MGMT_SERVER_PORT}")
        except Exception as e:
            log(f"[MGMT] FAIL start server: {e}")
            _mgmt_server = None


def stop_mgmt_server() -> None:
    global _mgmt_server
    with _mgmt_server_lock:
        if _mgmt_server is None:
            return
        try:
            _mgmt_server.shutdown()
            _mgmt_server.server_close()
            log("[MGMT] file server stopped")
        except Exception:
            pass
        _mgmt_server = None


REGISTRY_API_HOST = "192.168.137.1"
REGISTRY_API_PORT = 8766
DEVICE_CONNECTION_API_PORT = 8765


def get_wlan_mac() -> str:
    """Lay MAC address cua wlan0."""
    try:
        out = subprocess.check_output(
            ["cat", f"/sys/class/net/{WIFI_IFACE}/address"],
            text=True, timeout=3,
        ).strip()
        return out or ""
    except Exception:
        return ""


def get_wlan_ip() -> Optional[str]:
    """Lay IP thuc cua wlan0."""
    try:
        out = subprocess.check_output(
            ["ip", "-4", "addr", "show", WIFI_IFACE],
            text=True, timeout=3,
        )
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                ip = line.split()[1].split("/")[0]
                log(f"[MGMT] wlan0 IP: {ip}")
                return ip
    except Exception:
        pass
    log("[MGMT] wlan0 IP: not found")
    return None


def sync_time_from_pc() -> None:
    """Lay thoi gian tu PC, tinh offset de ten file ghi am dung gio thuc.
    Chi dung offset neu PC time > Pi time (Pi dang chay cham hon thuc te).
    """
    global _time_offset_sec
    try:
        url = f"http://{REGISTRY_API_HOST}:{DEVICE_CONNECTION_API_PORT}/api/time"
        resp = requests.get(url, timeout=3)
        if resp.status_code != 200:
            log(f"[TIME] sync failed: status={resp.status_code}")
            return
        data = resp.json()
        unix_ms = data.get("unix_ms")
        iso_time = data.get("iso")
        if unix_ms is None or not iso_time:
            log("[TIME] sync failed: missing unix_ms or iso field")
            return
        pc_time = unix_ms / 1000.0
        local_time = datetime.now().timestamp()
        offset = pc_time - local_time
        # Chi dung offset khi PC time > Pi time; neu Pi dang nhanh hon thi giu nguyen
        _time_offset_sec = max(0.0, offset)
        log(f"[TIME] offset={_time_offset_sec:.1f}s pc={iso_time} (raw_offset={offset:.1f}s)")
    except Exception as e:
        log(f"[TIME] sync failed: {e}")


def notify_device_connection() -> None:
    """Ban su kien ket noi toi WiFi ...0001 cho may phat WiFi."""
    sync_time_from_pc()
    try:
        ip = get_wlan_ip()
        if ip is None:
            log("[MGMT] notify device connection: skip, no IP yet")
            return
        url = f"http://{REGISTRY_API_HOST}:{DEVICE_CONNECTION_API_PORT}/api/device/connection"
        requests.post(url, json={"ip": ip, "type": "A"}, timeout=3)
        log(f"[MGMT] notify device connection: ip={ip}")
    except Exception as e:
        log(f"[MGMT] notify device connection failed: {e}")


def _current_corrected_time() -> datetime:
    return datetime.now() + timedelta(seconds=_time_offset_sec)


def is_in_recording_window(start: str, end: Optional[str]) -> bool:
    now = _current_corrected_time()
    start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
    if end is None:
        return now >= start_dt
    end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M")
    return start_dt <= now < end_dt


def seconds_until_window_start(start: str) -> float:
    now = _current_corrected_time()
    start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
    delta = (start_dt - now).total_seconds()
    return max(0.0, delta)


def main() -> None:
    global _runtime_wifi_retry_interval_sec, _runtime_upload_target_ssid, _runtime_wifi_password
    global _runtime_arecord_device, _runtime_arecord_channels, _runtime_arecord_rate, _runtime_arecord_format, _runtime_public_key_path
    global _runtime_prefer_hidden_wifi_immediate
    global _runtime_vad_threshold_dbfs, _runtime_vad_silence_timeout_sec, _runtime_vad_max_duration_sec
    global _runtime_interval_cycle_sec
    global _runtime_scheduled_start, _runtime_scheduled_end

    ensure_dirs()

    config_ok = ensure_identity_config_exists()
    if not config_ok:
        log("[CONFIG] WARNING: could not create default config file")

    active_config = load_identity_config_from_disk() or build_default_identity_config()
    active_mode, active_duration_sec, _runtime_wifi_retry_interval_sec, _runtime_upload_target_ssid, _runtime_wifi_password, _runtime_arecord_device, _runtime_arecord_channels, _runtime_arecord_rate, _runtime_arecord_format, _runtime_public_key_path, _runtime_prefer_hidden_wifi_immediate, _runtime_vad_threshold_dbfs, _runtime_vad_silence_timeout_sec, _runtime_vad_max_duration_sec, _runtime_interval_cycle_sec, _runtime_scheduled_start, _runtime_scheduled_end = derive_runtime_settings(active_config)

    last_config_mtime = None
    if PI_IDENTITY_CONFIG_PATH.exists():
        try:
            last_config_mtime = PI_IDENTITY_CONFIG_PATH.stat().st_mtime
        except Exception:
            last_config_mtime = None

    cleanup_leftover_temp_audio_on_startup()

    ensure_mgmt_wifi_profile()

    job_queue: queue.Queue[pathlib.Path] = queue.Queue()
    worker = threading.Thread(
        target=processing_worker,
        args=(job_queue,),
        daemon=True,
        name="audio-processing-worker",
    )
    worker.start()
    enqueue_leftover_jobs(job_queue)

    wifi_worker = threading.Thread(
        target=wifi_manager_worker,
        daemon=True,
        name="wifi-manager-worker",
    )
    wifi_worker.start()

    log("[PI2W] client started")
    log(f"[PI2W] rec dir: {REC_DIR}")
    log(f"[PI2W] identity config: {PI_IDENTITY_CONFIG_PATH}")
    log(f"[PI2W] upload hidden ssid: {_runtime_upload_target_ssid}")
    log(f"[PI2W] audio: device={_runtime_arecord_device} ch={_runtime_arecord_channels} rate={_runtime_arecord_rate} fmt={_runtime_arecord_format} -> Opus {OPUS_BITRATE} gain=+{AUDIO_GAIN_DB}dB")
    log(f"[PI2W] public key path: {_runtime_public_key_path}")
    log(
        f"[PI2W] mode={active_mode} record_every={active_duration_sec if active_duration_sec is not None else 'vad/manual'}s "
        f"wifi_retry_every={_runtime_wifi_retry_interval_sec}s ssid={_runtime_upload_target_ssid} profile={WIFI_CONNECTION_PROFILE} "
        f"disconnect_after_success={DISCONNECT_WIFI_AFTER_SUCCESS_UPLOAD} immediate_hidden_prefer={_runtime_prefer_hidden_wifi_immediate} "
        f"vad_threshold={_runtime_vad_threshold_dbfs}dBFS vad_silence={_runtime_vad_silence_timeout_sec}s vad_max={_runtime_vad_max_duration_sec}s"
    )

    while True:
        if PI_IDENTITY_CONFIG_PATH.exists():
            try:
                current_mtime = PI_IDENTITY_CONFIG_PATH.stat().st_mtime
            except Exception:
                current_mtime = None

            if current_mtime is not None and (last_config_mtime is None or current_mtime > last_config_mtime):
                cfg = load_identity_config_from_disk()
                if cfg is not None:
                    prev_mode = active_mode
                    prev_duration = active_duration_sec
                    prev_wifi_retry = _runtime_wifi_retry_interval_sec
                    prev_ssid = _runtime_upload_target_ssid
                    prev_mic = f"{_runtime_arecord_device}/{_runtime_arecord_channels}ch/{_runtime_arecord_rate}/{_runtime_arecord_format}"
                    prev_key = _runtime_public_key_path
                    prev_immediate = _runtime_prefer_hidden_wifi_immediate

                    active_config = cfg
                    active_mode, active_duration_sec, _runtime_wifi_retry_interval_sec, _runtime_upload_target_ssid, _runtime_wifi_password, _runtime_arecord_device, _runtime_arecord_channels, _runtime_arecord_rate, _runtime_arecord_format, _runtime_public_key_path, _runtime_prefer_hidden_wifi_immediate, _runtime_vad_threshold_dbfs, _runtime_vad_silence_timeout_sec, _runtime_vad_max_duration_sec, _runtime_interval_cycle_sec, _runtime_scheduled_start, _runtime_scheduled_end = derive_runtime_settings(active_config)
                    last_config_mtime = current_mtime

                    log(
                        f"[CONFIG] applied updated_at={active_config.get('updated_at', 'n/a')} "
                        f"mode={prev_mode}->{active_mode} "
                        f"record_sec={prev_duration}->{active_duration_sec} "
                        f"wifi_retry_sec={prev_wifi_retry}->{_runtime_wifi_retry_interval_sec} "
                        f"ssid={prev_ssid}->{_runtime_upload_target_ssid} "
                        f"mic={prev_mic}->{_runtime_arecord_device}/{_runtime_arecord_channels}ch/{_runtime_arecord_rate}/{_runtime_arecord_format} "
                        f"key={prev_key}->{_runtime_public_key_path} "
                        f"immediate_hidden={prev_immediate}->{_runtime_prefer_hidden_wifi_immediate}"
                    )
                else:
                    log("[CONFIG] invalid config detected; keep last valid config")

        if active_duration_sec is None and active_mode not in ("vad", "scheduled"):
            log("[MAIN] mode=manual, sleep 2s and wait config change")
            time.sleep(2)
            continue

        if active_mode == "scheduled":
            if _runtime_scheduled_start is None:
                log("[MAIN] mode=scheduled, no window configured, sleep 2s")
                time.sleep(2)
                continue
            if not is_in_recording_window(_runtime_scheduled_start, _runtime_scheduled_end):
                wait_sec = seconds_until_window_start(_runtime_scheduled_start)
                log(f"[MAIN] mode=scheduled, outside window, sleep {int(wait_sec)}s until {_runtime_scheduled_start}")
                time.sleep(max(2.0, wait_sec))
                continue
            # Trong khung gio: ghi 1 segment binh thuong
            seg_sec = int(active_duration_sec) if active_duration_sec else AUTO_RECORD_SEC
            wav_path = next_wav_path()
            rec_ok = record_wav_segment(wav_path, seg_sec)
        elif active_mode == "vad":
            wav_path = record_wav_segment_vad(next_wav_path)
            rec_ok = wav_path is not None
        elif active_mode == "interval":
            wav_path = next_wav_path()
            rec_ok = record_wav_segment(wav_path, active_duration_sec)
            if rec_ok:
                job_queue.put(wav_path)
                qsize = job_queue.qsize()
                log(f"[MAIN] queued for background processing: {wav_path.name} queue={qsize} mode=interval cycle={_runtime_interval_cycle_sec}s")
                if qsize >= 5:
                    log(f"[WARN] processing queue backlog={qsize}; WiFi/CPU may be slower than recording")
            else:
                log("[MAIN] Record failed, wav cleanup already handled; continue recording")
            wait_sec = max(0, _runtime_interval_cycle_sec - active_duration_sec)
            if wait_sec > 0:
                log(f"[MAIN] interval mode: wait {wait_sec}s before next recording")
                time.sleep(wait_sec)
            continue
        else:
            wav_path = next_wav_path()
            rec_ok = record_wav_segment(wav_path, active_duration_sec)

        if rec_ok:
            job_queue.put(wav_path)
            qsize = job_queue.qsize()
            log(f"[MAIN] queued for background processing: {wav_path.name} queue={qsize} mode={active_mode}")
            if qsize >= 5:
                log(f"[WARN] processing queue backlog={qsize}; WiFi/CPU may be slower than recording")
        else:
            log("[MAIN] Record failed, wav cleanup already handled; continue recording")

if __name__ == "__main__":
    main()






















































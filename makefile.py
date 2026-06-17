#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import datetime
import hashlib
import io
import json
import logging
import math
import os
import secrets
import string
import sys
import tempfile
import threading
from pathlib import Path
from contextlib import ExitStack

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

try:
    import requests
except ImportError:
    requests = None

try:
    import wifi_hotspot
except ImportError:
    wifi_hotspot = None

try:
    import network_config
except ImportError:
    network_config = None

try:
    import firewall_config
except ImportError:
    firewall_config = None

try:
    from device_registry_api import DeviceConnectionStore, DeviceRegistryServer
except ImportError:
    DeviceConnectionStore = None
    DeviceRegistryServer = None

try:
    from device_data_server import DeviceDataServer
except ImportError:
    DeviceDataServer = None

try:
    from audio_player import AudioPlayerWidget
except ImportError:
    AudioPlayerWidget = None

try:
    from auth_session import AuthManager, DEFAULT_PASSWORD, PASSWORD_MIN_LENGTH
except ImportError:
    AuthManager = None
    DEFAULT_PASSWORD = "12345678"
    PASSWORD_MIN_LENGTH = 8

try:
    from phantom_bundle import (
        decrypt_bin_bytes,
        encrypt_paths_to_bin,
        _phtm_load_private_key,
        _phtm_load_public_key,
        _CRYPTO_OK,
    )
except ImportError:
    decrypt_bin_bytes = None
    encrypt_paths_to_bin = None
    _phtm_load_private_key = None
    _phtm_load_public_key = None
    _CRYPTO_OK = False


_HIDDEN_KEY = ""

_THEME = {
    "bg": "#f8fafc",
    "surface": "#ffffff",
    "header": "#1e293b",
    "header_accent": "#334155",
    "primary": "#2563eb",
    "primary_hover": "#1d4ed8",
    "primary_soft": "#eff6ff",
    "border": "#e2e8f0",
    "text": "#0f172a",
    "text_muted": "#475569",
    "success": "#16a34a",
    "success_bg": "#f0fdf4",
    "warning": "#d97706",
    "warning_bg": "#fffbeb",
    "danger": "#dc2626",
    "danger_bg": "#fef2f2",
    "chain": "#0e7490",
    "chain_bg": "#ecfeff",
    "mono_bg": "#f1f5f9",
    "status_bar": "#f1f5f9",
    "shadow_1": "#94a3b8",
    "shadow_2": "#cbd5e1",
    "shadow_3": "#e2e8f0",
    "shadow_4": "#f1f5f9",
    "shadow_5": "#f8fafc",
    "glow_1": "#2563eb",
    "glow_2": "#3b82f6",
    "glow_3": "#bfdbfe",
    "header_glow": "#2563eb",
}

_HASH_BLOCK_COUNT = 5
_HASH_BLOCK_LENGTH = 32
_HASH_ALPHABET = string.ascii_lowercase + string.digits
_FILES_LIST_VISIBLE_ROWS = 12

_HTTP_LOG_MAX_BODY = 8000
_http_logger = logging.getLogger("phantom.http")
_decode_logger = logging.getLogger("phantom.decode")

# ── Language system ──────────────────────────────────────────────────────────
_LANG = "vi"

_STRINGS: dict = {
    # Header
    "header_status_label":   {"vi": "Trạng thái hệ thống",      "en": "System Status"},
    "logout":                {"vi": "Đăng xuất",                 "en": "Log Out"},
    "lang_toggle_to_en":     {"vi": "EN",                        "en": "VI"},
    # Sidebar
    "connected_devices":     {"vi": "THIẾT BỊ KẾT NỐI",          "en": "CONNECTED DEVICES"},
    "device_list_subtitle":  {"vi": "Danh sách thiết bị đang kết nối", "en": "List of connected devices"},
    "decrypt_bin_btn":       {"vi": "Giải mã file .bin",          "en": "Decrypt .bin file"},
    # File list card
    "recordings_title":      {"vi": "DANH SÁCH BẢN GHI",         "en": "RECORDINGS"},
    "refresh_btn":           {"vi": "Làm mới",                   "en": "Refresh"},
    "col_stt":               {"vi": "STT",                        "en": "#"},
    "col_name":              {"vi": "Tên bản ghi",               "en": "Name"},
    "col_start_time":        {"vi": "Thời gian bắt đầu",         "en": "Start Time"},
    "col_device":            {"vi": "Thiết bị",                  "en": "Device"},
    "col_file_type":         {"vi": "Loại file",                 "en": "File Type"},
    "col_size":              {"vi": "Dung lượng",                "en": "Size"},
    # Login overlay
    "login_title":           {"vi": "ĐĂNG NHẬP",                 "en": "LOG IN"},
    "login_app_name":        {"vi": "Phantom",                   "en": "Phantom"},
    "password_label":        {"vi": "Mật khẩu",                  "en": "Password"},
    "login_btn":             {"vi": "Đăng nhập",                 "en": "Log In"},
    "enter_password":        {"vi": "Vui lòng nhập mật khẩu.",   "en": "Please enter your password."},
    "wrong_password":        {"vi": "Mật khẩu không đúng.",      "en": "Incorrect password."},
    # Loading overlay
    "processing":            {"vi": "Đang xử lý",                "en": "Processing"},
    "please_wait":           {"vi": "Vui lòng chờ trong giây lát", "en": "Please wait a moment"},
    # Connection / status
    "not_connected_var":     {"vi": "Chưa kết nối",              "en": "Not connected"},
    "not_verified":          {"vi": "Chưa xác minh kết nối.",    "en": "Connection not verified."},
    "please_login":          {"vi": "Vui lòng đăng nhập để sử dụng hệ thống.", "en": "Please log in to use the system."},
    "not_connected_device":  {"vi": "Chưa kết nối thiết bị",     "en": "No device connected"},
    "connected_device":      {"vi": "Đã kết nối thiết bị — kênh mã hóa đang hoạt động", "en": "Device connected — encrypted channel active"},
    "connection_failed_info":{"vi": "Kết nối thất bại. Hãy vào đúng mạng blockchain node rồi thử kết nối lại.", "en": "Connection failed. Join the blockchain node network and try again."},
    "not_connected_info":    {"vi": "Chưa kết nối.",             "en": "Not connected."},
    "ready":                 {"vi": "Sẵn sàng.",                 "en": "Ready."},
    "operation_failed":      {"vi": "Thao tác thất bại.",        "en": "Operation failed."},
    "error_occurred":        {"vi": "Có lỗi xảy ra.",            "en": "An error occurred."},
    "busy_wait":             {"vi": "Đang xử lý, vui lòng chờ...", "en": "Processing, please wait..."},
    # Session
    "session_expired_title": {"vi": "Phiên hết hạn",             "en": "Session Expired"},
    "session_expired_msg":   {"vi": "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", "en": "Your session has expired. Please log in again."},
    # Change password
    "change_pw_title":       {"vi": "Đổi mật khẩu",             "en": "Change Password"},
    "change_pw_first":       {"vi": "Lần đầu đăng nhập, bạn cần đổi mật khẩu mặc định.", "en": "First login: please change the default password."},
    "change_pw_hint":        {"vi": "Nhập mật khẩu hiện tại và mật khẩu mới.", "en": "Enter your current and new password."},
    "current_password":      {"vi": "Mật khẩu hiện tại",         "en": "Current Password"},
    "new_password":          {"vi": "Mật khẩu mới",              "en": "New Password"},
    "confirm_password":      {"vi": "Xác nhận mật khẩu mới",     "en": "Confirm New Password"},
    "save_password_btn":     {"vi": "Lưu mật khẩu",              "en": "Save Password"},
    "fill_all_fields":       {"vi": "Vui lòng điền đầy đủ các trường.", "en": "Please fill in all fields."},
    "password_mismatch":     {"vi": "Xác nhận mật khẩu không khớp.", "en": "Passwords do not match."},
    "pw_wrong_current":      {"vi": "Mật khẩu hiện tại không đúng.", "en": "Current password is incorrect."},
    "pw_too_short":          {"vi": "Mật khẩu mới phải có ít nhất {n} ký tự.", "en": "New password must be at least {n} characters."},
    "pw_same_as_old":        {"vi": "Mật khẩu mới phải khác mật khẩu hiện tại.", "en": "New password must differ from the current one."},
    "pw_changed":            {"vi": "Đã đổi mật khẩu thành công.", "en": "Password changed successfully."},
    "pw_changed_title":      {"vi": "Thành công",                "en": "Success"},
    "pw_changed_msg":        {"vi": "Mật khẩu đã được cập nhật.", "en": "Your password has been updated."},
    # Common buttons
    "cancel_btn":            {"vi": "Hủy",                       "en": "Cancel"},
    "close_btn":             {"vi": "Đóng",                      "en": "Close"},
    "save_btn":              {"vi": "Lưu",                       "en": "Save"},
    "apply_btn":             {"vi": "Áp dụng",                   "en": "Apply"},
    # Error messages
    "not_logged_in_title":   {"vi": "Chưa đăng nhập",            "en": "Not Logged In"},
    "not_logged_in_msg":     {"vi": "Vui lòng đăng nhập để thực hiện thao tác này.", "en": "Please log in to perform this action."},
    "missing_lib":           {"vi": "Thiếu thư viện",            "en": "Missing Library"},
    "install_requests":      {"vi": "Cài: pip install requests",  "en": "Install: pip install requests"},
    "missing_module":        {"vi": "Thiếu module",              "en": "Missing Module"},
    "phantom_bundle_missing":{"vi": "Không tải được phantom_bundle.py.", "en": "Could not load phantom_bundle.py."},
    "install_cryptography":  {"vi": "Cài: pip install cryptography", "en": "Install: pip install cryptography"},
    "missing_ip":            {"vi": "Thiếu IP",                  "en": "Missing IP"},
    "device_no_ip":          {"vi": "Thiết bị chưa có địa chỉ IP.", "en": "Device has no IP address."},
    "error_title":           {"vi": "Lỗi",                       "en": "Error"},
    # File operations
    "no_file_selected_title":{"vi": "Chưa chọn file",            "en": "No File Selected"},
    "select_one_file":       {"vi": "Bạn hãy chọn 1 file trong danh sách.", "en": "Please select a file from the list."},
    "no_files_title":        {"vi": "Không có file",             "en": "No Files"},
    "list_empty":            {"vi": "Danh sách trống.",          "en": "The list is empty."},
    "success_title":         {"vi": "Thành công",                "en": "Success"},
    "failed_title":          {"vi": "Thất bại",                  "en": "Failed"},
    "no_files_downloaded":   {"vi": "Không tải được file nào.",  "en": "No files could be downloaded."},
    "confirm_delete_title":  {"vi": "Xác nhận xóa",              "en": "Confirm Delete"},
    "confirm_delete_msg":    {"vi": "Bạn chắc chắn muốn xóa file này?\n\n", "en": "Are you sure you want to delete this file?\n\n"},
    "confirm_delete_all_title":{"vi": "Xác nhận bảo mật",        "en": "Security Confirmation"},
    "confirm_delete_all_msg":{"vi": "Nhập DELETE để xóa tất cả file:", "en": "Type DELETE to erase all files:"},
    "cancelled_delete_all":  {"vi": "Đã hủy xóa tất cả.",       "en": "Delete all cancelled."},
    "download_all_btn":      {"vi": "Tải tất cả",                "en": "Download All"},
    "download_selected_btn": {"vi": "Tải đã chọn",              "en": "Download Selected"},
    # Device config fields
    "identity_section":      {"vi": "Định danh",                 "en": "Identity"},
    "recording_config_section":{"vi": "Cấu hình ghi âm",        "en": "Recording Config"},
    "device_config_heading": {"vi": "Cấu hình thiết bị",        "en": "Device Config"},
    "device_name_label":     {"vi": "Tên thiết bị",              "en": "Device Name"},
    "last_updated_prefix":   {"vi": "Cập nhật lần cuối: ",       "en": "Last updated: "},
    "id_code":               {"vi": "Mã định danh",              "en": "ID Code"},
    "full_name":             {"vi": "Họ và tên",                 "en": "Full Name"},
    "birth_year":            {"vi": "Năm sinh",                  "en": "Birth Year"},
    "address":               {"vi": "Địa chỉ",                   "en": "Address"},
    "issue_date":            {"vi": "Ngày cấp định danh",        "en": "Issue Date"},
    "device_name_field":     {"vi": "Tên thiết bị",              "en": "Device Name"},
    "device_id_field":       {"vi": "ID thiết bị",               "en": "Device ID"},
    "device_address_field":  {"vi": "Địa chỉ thiết bị",         "en": "Device Address"},
    "recording_mode":        {"vi": "Kiểu ghi âm",               "en": "Recording Mode"},
    "recording_duration":    {"vi": "Thời lượng ghi âm",         "en": "Recording Duration"},
    "scan_cycle":            {"vi": "Chu kỳ quét",               "en": "Scan Cycle"},
    "vad_threshold":         {"vi": "VAD ngưỡng (dBFS)",         "en": "VAD Threshold (dBFS)"},
    "vad_silence_timeout":   {"vi": "VAD timeout im lặng",       "en": "VAD Silence Timeout"},
    "vad_max_duration":      {"vi": "VAD thời gian tối đa",      "en": "VAD Max Duration"},
    "interval_cycle":        {"vi": "Chu kỳ ghi âm",             "en": "Recording Interval"},
    "start_rec":             {"vi": "Bắt đầu ghi âm",            "en": "Start Recording"},
    "stop_rec":              {"vi": "Kết thúc ghi âm",           "en": "Stop Recording"},
    "minutes_unit":          {"vi": "phút",                      "en": "min"},
    "seconds_unit":          {"vi": "giây",                      "en": "sec"},
    # Recording mode labels
    "mode_continuous":       {"vi": "Liên tục",                  "en": "Continuous"},
    "mode_vad":              {"vi": "Theo giọng nói (VOX)",      "en": "Voice Activated (VOX)"},
    "mode_interval":         {"vi": "Theo chu kỳ",               "en": "Interval"},
    "mode_scheduled":        {"vi": "Theo lịch hẹn",             "en": "Scheduled"},
    # Device files dialog
    "device_files_heading":  {"vi": "Danh sách file",            "en": "File List"},
    "col_filename":          {"vi": "Tên file",                  "en": "File Name"},
    "col_time":              {"vi": "Thời gian",                 "en": "Time"},
    # Identity edit
    "identity_edit_heading": {"vi": "Chỉnh sửa định danh",      "en": "Edit Identity"},
    # Device status
    "device_status_heading": {"vi": "Trạng thái thiết bị",      "en": "Device Status"},
    # Hash update
    "hash_update_instruction":{"vi": "Dán mảng JSON từ loại B (hoặc 5 dòng, mỗi dòng 32 ký tự). Ctrl+V để dán.", "en": "Paste JSON array from type B (or 5 lines, each 32 chars). Ctrl+V to paste."},
    # Decrypt window
    "decrypt_window_title":  {"vi": "PHANTOM — Giải mã file .bin",  "en": "PHANTOM — Decrypt .bin File"},
    "decrypt_window_heading":{"vi": "PHANTOM — GIẢI MÃ FILE .BIN",  "en": "PHANTOM — DECRYPT .BIN FILE"},
    "input_files_label":     {"vi": "Input files (.bin)",         "en": "Input files (.bin)"},
    "key_file_label":        {"vi": "Key file (private.key)",     "en": "Key file (private.key)"},
    "no_file_hint":          {"vi": "Chưa có file nào được chọn\nNhấn Browse .bin để chọn", "en": "No files selected\nClick Browse .bin to choose"},
    "no_key_selected":       {"vi": "Chưa chọn private.key",     "en": "No private.key selected"},
    "clear_list_btn":        {"vi": "Xóa danh sách",             "en": "Clear List"},
    "open_output_btn":       {"vi": "📁  Mở thư mục output",     "en": "📁  Open Output Folder"},
    "decrypt_run_btn":       {"vi": "▶  GIẢI MÃ",                "en": "▶  DECRYPT"},
    "decrypt_ready":         {"vi": "Sẵn sàng",                  "en": "Ready"},
    # Status messages (runtime)
    "starting_node":         {"vi": "Đang khởi động node bảo mật — sẽ tự kiểm tra thiết bị.", "en": "Starting security node — device check in progress."},
    "http_server_ready":     {"vi": "Máy chủ HTTP/Socket đã sẵn sàng nhận dữ liệu.", "en": "HTTP/Socket server ready to receive data."},
    "server_start_failed":   {"vi": "Không khởi động được máy chủ: ", "en": "Could not start server: "},
    "registry_ready":        {"vi": "Dịch vụ đăng ký sẵn sàng.", "en": "Registry service ready."},
    "registry_unavailable":  {"vi": "Dịch vụ đăng ký không khả dụng.", "en": "Registry service unavailable."},
    "config_synced":         {"vi": "Đã đồng bộ cấu hình từ thiết bị.", "en": "Config synced from device."},
    "config_sync_failed":    {"vi": "Không tải lại được cấu hình từ thiết bị.", "en": "Could not reload device config."},
    "syncing_config":        {"vi": "Đang đồng bộ cấu hình...", "en": "Syncing config..."},
    "records_list_prefix":   {"vi": "Danh sách bản ghi: ",       "en": "Recordings: "},
    "records_list_suffix":   {"vi": " file.",                    "en": " file(s)."},
    "blockchain_activated":  {"vi": "Đã kích hoạt mạng blockchain.", "en": "Blockchain network activated."},
    "activating":            {"vi": "Đang kích hoạt...",          "en": "Activating..."},
    "activation_failed":     {"vi": "Kích hoạt thất bại.",       "en": "Activation failed."},
    "checking_server":       {"vi": "Đang kiểm tra máy chủ nhận dữ liệu...", "en": "Checking data server..."},
    "server_not_ready":      {"vi": "Máy chủ nhận dữ liệu chưa sẵn sàng.", "en": "Data server not ready."},
    "server_ready_status":   {"vi": "Máy chủ sẵn sàng — PC: 127.0.0.1:{port} | thiết bị Wi-Fi: {host}:{port2}", "en": "Server ready — PC: 127.0.0.1:{port} | Wi-Fi device: {host}:{port2}"},
    "refreshing_files":      {"vi": "Đang tải danh sách file...", "en": "Loading file list..."},
    "refreshed_files":       {"vi": "Đã làm mới danh sách: {n} file (máy chủ PC).", "en": "Refreshed: {n} file(s) (PC server)."},
    "refresh_failed":        {"vi": "Làm mới thất bại. Kiểm tra lại mạng blockchain rồi thử lại.", "en": "Refresh failed. Check the blockchain network and try again."},
    "loading_config":        {"vi": "Đang tải cấu hình từ ",     "en": "Loading config from "},
    "config_load_failed":    {"vi": "Không lấy được cấu hình từ ", "en": "Could not load config from "},
    "config_load_failed_suffix": {"vi": ". Kiểm tra thiết bị và mạng.", "en": ". Check device and network."},
    "loading_status":        {"vi": "Đang tải trạng thái từ ",   "en": "Loading status from "},
    "status_load_failed":    {"vi": "Không lấy được trạng thái từ ", "en": "Could not load status from "},
    "check_device_network":  {"vi": ". Kiểm tra thiết bị và mạng.", "en": ". Check device and network."},
    "loading_identity":      {"vi": "Đang tải định danh từ ",    "en": "Loading identity from "},
    "identity_load_failed":  {"vi": "Không lấy được định danh từ ", "en": "Could not load identity from "},
    "saving_identity":       {"vi": "Đang lưu định danh ",       "en": "Saving identity "},
    "identity_saved":        {"vi": "Đã cập nhật định danh thiết bị ", "en": "Updated device identity "},
    "identity_save_failed":  {"vi": "Lưu định danh ",            "en": "Save identity "},
    "identity_save_failed_suffix": {"vi": " thất bại.",          "en": " failed."},
    "identity_saved_msg":    {"vi": "Đã cập nhật định danh.",    "en": "Identity updated."},
    "updating_config":       {"vi": "Đang update cấu hình ",     "en": "Updating config "},
    "update_config_failed":  {"vi": "Update cấu hình ",          "en": "Update config "},
    "update_config_failed_suffix": {"vi": " thất bại.",          "en": " failed."},
    "device_restart":        {"vi": "Thiết bị đang khởi động lại dịch vụ...", "en": "Device is restarting its service..."},
    "config_updated_status": {"vi": "Đã update cấu hình thiết bị ", "en": "Updated device config "},
    "loading_filelist":      {"vi": "Đang tải danh sách file từ ", "en": "Loading file list from "},
    "filelist_load_failed":  {"vi": "Không tải được danh sách file từ ", "en": "Could not load file list from "},
    "loaded_files":          {"vi": "Đã tải {n} file từ thiết bị ", "en": "Loaded {n} file(s) from device "},
    "downloading_files":     {"vi": "Đang tải file...",           "en": "Downloading files..."},
    "download_failed_msg":   {"vi": "Tải file thất bại.",         "en": "Download failed."},
    "downloaded_n_of_m":     {"vi": "Đã tải {s}/{t} file.",      "en": "Downloaded {s}/{t} file(s)."},
    "folder_label":          {"vi": "Thư mục: ",                 "en": "Folder: "},
    "uploading":             {"vi": "Đang tải lên...",            "en": "Uploading..."},
    "uploading_many":        {"vi": "Đang tải lên nhiều file...", "en": "Uploading multiple files..."},
    "upload_success_status": {"vi": "Tải lên thành công.",        "en": "Upload successful."},
    "upload_failed_status":  {"vi": "Tải lên thất bại. Kiểm tra lại mạng blockchain rồi thử lại.", "en": "Upload failed. Check the blockchain network and try again."},
    "upload_done_info":      {"vi": "Tải lên xong {n} file.",    "en": "Uploaded {n} file(s)."},
    "upload_one_done_info":  {"vi": "Tải lên xong: ",            "en": "Uploaded: "},
    "uploading_to":          {"vi": "Đang mã hóa và upload tới ", "en": "Encrypting and uploading to "},
    "upload_to_failed":      {"vi": "Upload tới ",               "en": "Upload to "},
    "upload_to_failed_suffix":{"vi": " thất bại. Kiểm tra thiết bị và mạng.", "en": " failed. Check device and network."},
    "upload_success_device": {"vi": "Đã upload ",                "en": "Uploaded "},
    "encrypt_progress":      {"vi": "Đang mã hóa ",              "en": "Encrypting "},
    "upload_progress":       {"vi": "Đang upload ",              "en": "Uploading "},
    "upload_to_device":      {"vi": " tới thiết bị ",            "en": " to device "},
    "upload_success_msg":    {"vi": "Đã mã hóa {src} và gửi {bin} tới thiết bị {dev}.", "en": "Encrypted {src} and sent {bin} to device {dev}."},
    "upload_success_title":  {"vi": "Upload thành công",         "en": "Upload Successful"},
    "deleting_file":         {"vi": "Đang xóa file...",           "en": "Deleting file..."},
    "delete_success":        {"vi": "Xóa file thành công.",       "en": "File deleted successfully."},
    "delete_failed":         {"vi": "Xóa file thất bại. Kiểm tra lại mạng blockchain rồi thử lại.", "en": "Delete failed. Check the blockchain network and try again."},
    "deleted_file_info":     {"vi": "Đã xóa: ",                  "en": "Deleted: "},
    "deleting_all":          {"vi": "Đang xóa tất cả...",         "en": "Deleting all..."},
    "delete_all_success":    {"vi": "Xóa tất cả thành công.",    "en": "All files deleted."},
    "delete_all_failed":     {"vi": "Xóa tất cả thất bại. Kiểm tra lại mạng blockchain rồi thử lại.", "en": "Delete all failed. Check the blockchain network and try again."},
    "deleted_all_info":      {"vi": "Đã xóa tất cả file.",       "en": "All files deleted."},
    "downloading_file":      {"vi": "Đang tải file...",           "en": "Downloading file..."},
    "downloaded_file":       {"vi": "Đã tải {name} vào {folder}.", "en": "Downloaded {name} to {folder}."},
    "downloaded_file_info":  {"vi": "Đã tải: ",                  "en": "Downloaded: "},
    "download_file_title":   {"vi": "Tải file",                  "en": "Download File"},
    "download_file_msg":     {"vi": "Đã tải về:\n{name}\n\nThư mục: {folder}", "en": "Downloaded:\n{name}\n\nFolder: {folder}"},
    "download_failed_one":   {"vi": "Tải file thất bại. Kiểm tra lại mạng blockchain rồi thử lại.", "en": "Download failed. Check the blockchain network and try again."},
    "save_all_failed":       {"vi": "Lưu trữ thất bại.",         "en": "Archive failed."},
    "archiving_all":         {"vi": "Đang lưu trữ tất cả...",    "en": "Archiving all..."},
    "archive_failed_msg":    {"vi": "Lưu trữ thất bại.",         "en": "Archive failed."},
    "refreshing":            {"vi": "Đang làm mới...",            "en": "Refreshing..."},
    "reload_filelist_failed":{"vi": "Không tải lại được danh sách file.", "en": "Could not reload file list."},
    "copying_ssid":          {"vi": "Đang lấy SSID từ ",         "en": "Getting SSID from "},
    "copy_ssid_failed":      {"vi": "Không lấy được SSID từ ",   "en": "Could not get SSID from "},
    "copied_ssid_from":      {"vi": "Đã sao chép SSID từ ",      "en": "Copied SSID from "},
    "no_ssid_title":         {"vi": "Thiếu SSID",                "en": "No SSID"},
    "no_ssid_msg":           {"vi": "Chưa có SSID để sao chép.", "en": "No SSID to copy."},
    "ssid_copied":           {"vi": "Đã sao chép SSID.",         "en": "SSID copied."},
    "no_hash_title":         {"vi": "Chưa có bộ hash",           "en": "No Hash Bundle"},
    "no_hash_msg":           {"vi": "Hãy tạo bộ hash cho {name} trước khi sao chép.", "en": "Generate a hash bundle for {name} before copying."},
    "hash_copied":           {"vi": "Đã sao chép bộ hash vào clipboard.", "en": "Hash bundle copied to clipboard."},
    "hash_generated":        {"vi": "Đã tạo bộ hash cho ",       "en": "Generated hash bundle for "},
    "hash_updated":          {"vi": "Đã cập nhật bộ hash cho ",  "en": "Updated hash bundle for "},
    "decrypt_begin":         {"vi": "═══ Bắt đầu giải mã {n} file ═══", "en": "═══ Decrypting {n} file(s) ═══"},
    "decrypt_done":          {"vi": "═══ Hoàn tất: {s}/{t} file ═══", "en": "═══ Done: {s}/{t} file(s) ═══"},
    "decrypt_success_status":{"vi": "Hoàn tất {s}/{t} file",    "en": "Done {s}/{t} file(s)"},
    "decrypt_failed_status": {"vi": "Giải mã thất bại",          "en": "Decryption failed"},
    "key_error_title":       {"vi": "Lỗi khóa",                  "en": "Key Error"},
    "decrypting_file":       {"vi": "Đang giải mã ",             "en": "Decrypting "},
    "decrypt_select_title":  {"vi": "Chưa chọn file",            "en": "No File Selected"},
    "decrypt_select_msg":    {"vi": "Hãy chọn ít nhất một file .bin.", "en": "Please select at least one .bin file."},
    "no_key_title":          {"vi": "Chưa có key",               "en": "No Key"},
    "no_key_msg":            {"vi": "Hãy chọn file private.key trước.", "en": "Please select a private.key file first."},
    "key_read_error":        {"vi": "Lỗi đọc key: ",             "en": "Key read error: "},
    "key_error_status":      {"vi": "Lỗi key",                   "en": "Key error"},
    "network_module_unavail":{"vi": "Module mạng không khả dụng.", "en": "Network module unavailable."},
    "network_error_title":   {"vi": "Mạng",                      "en": "Network"},
    "apply_network_success": {"vi": "Đã áp dụng cấu hình mạng.", "en": "Network config applied."},
    "apply_network_failed":  {"vi": "Áp dụng cấu hình mạng thất bại.", "en": "Failed to apply network config."},
    "applying_network":      {"vi": "Đang áp dụng mạng...",      "en": "Applying network config..."},
    "blockchain_hash_unavail":{"vi": "Module hash blockchain không khả dụng.", "en": "Blockchain hash module unavailable."},
    "windows_only":          {"vi": "Chỉ hỗ trợ trên Windows.",  "en": "Windows only."},
    "node_inactive":         {"vi": "Node chưa kích hoạt",        "en": "Node inactive"},
    "not_ready_title":       {"vi": "Chưa sẵn sàng",             "en": "Not Ready"},
    "server_not_running_msg":{"vi": "Máy chủ nhận dữ liệu chưa chạy.\n\nKhởi động lại app và chờ máy chủ HTTP sẵn sàng.", "en": "Data server is not running.\n\nRestart the app and wait for the HTTP server to be ready."},
    "wifi_adapter_prefix":   {"vi": "Adapter Wi-Fi: ",           "en": "Wi-Fi Adapter: "},
    "invalid_value_title":   {"vi": "Giá trị không hợp lệ",      "en": "Invalid Value"},
    "invalid_hash_title":    {"vi": "Bộ hash không hợp lệ",      "en": "Invalid Hash Bundle"},
    "save_success_title":    {"vi": "Lưu thành công",            "en": "Saved"},
    "save_failed_title":     {"vi": "Lưu thất bại",              "en": "Save Failed"},
    "update_failed_title":   {"vi": "Update thất bại",           "en": "Update Failed"},
    "update_success_title":  {"vi": "Update thành công",         "en": "Update Successful"},
    "audio_folder_opened":   {"vi": "Đã mở thư mục âm thanh: ",  "en": "Opened audio folder: "},
    "conn_count_badge_sub":  {"vi": "KẾT NỐI",                   "en": "CONNECTIONS"},
    "device_card_mac":       {"vi": "Địa chỉ MAC",               "en": "MAC Address"},
    "device_card_time":      {"vi": "Thời gian kết nối",         "en": "Connection Time"},
    "filelist_dialog_title": {"vi": "Danh sách file — ",         "en": "File List — "},
    "select_file_dialog_msg":{"vi": "Hãy chọn một file trong danh sách.", "en": "Please select a file from the list."},
    "check_files_no_select_msg": {"vi": "Hãy tích chọn ít nhất một file.", "en": "Please check at least one file."},
    "no_conn_profile":       {"vi": "Chưa có kết nối mạng trên máy. Bật adapter mạng rồi thử lại.", "en": "No network connection profile found. Enable a network adapter and try again."},
}


def _T(key: str) -> str:
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(_LANG, entry.get("vi", key))


def _setup_http_logging():
    if _http_logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [HTTP] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    _http_logger.addHandler(handler)
    _http_logger.setLevel(logging.INFO)
    _http_logger.propagate = False


def _terminal_decode_log(message, level=logging.INFO):
    _decode_logger.log(level, message)
    print(f"[DECODE] {message}", flush=True)


def _setup_decode_logging():
    if _decode_logger.handlers:
        return
    log_path = Path(__file__).resolve().parent / "phantom_decode.log"
    formatter = logging.Formatter(
        "%(asctime)s [DECODE] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    _decode_logger.addHandler(file_handler)
    _decode_logger.addHandler(console_handler)
    _decode_logger.setLevel(logging.DEBUG)
    _decode_logger.propagate = False
    _terminal_decode_log(f"decode logger ready log_file={log_path}")


_ENDPOINTS = {
    "status": "L2FwaS9zdGF0dXM=",
    "list": "L2FwaS9maWxlbGlzdA==",
    "upload_one": "L2FwaS91cGxvYWQ=",
    "upload_many": "L2FwaS91cGxvYWQtYWxs",
    "download": "L2FwaS9kb3dubG9hZA==",
    "delete_one": "L2FwaS9kZWxldGU=",
    "delete_all": "L2FwaS9kZWxldGUtYWxs",
}


class _StreamLoadingResponse:
    def __init__(self, response, on_done):
        self._response = response
        self._on_done = on_done
        self._released = False

    def _release(self):
        if self._released:
            return
        self._released = True
        self._on_done()

    def __getattr__(self, name):
        return getattr(self._response, name)

    def close(self):
        try:
            return self._response.close()
        finally:
            self._release()

    def iter_content(self, chunk_size=1, decode_unicode=False):
        try:
            yield from self._response.iter_content(
                chunk_size=chunk_size,
                decode_unicode=decode_unicode,
            )
        finally:
            self._release()

    @property
    def content(self):
        try:
            return self._response.content
        finally:
            self._release()


class AutoPrivateSDManagerApp(tk.Tk):
    def __init__(self):
        _setup_http_logging()
        _setup_decode_logging()
        super().__init__()

        self.title("Phantom")
        self.geometry("980x780")
        self.state("zoomed")
        self.minsize(900, 700)
        self.configure(bg=_THEME["bg"])

        self.files_data = []
        self._active_device_ip = None
        self._active_device_port = None
        self._download_dir = str(Path(__file__).parent / "rec")
        os.makedirs(self._download_dir, exist_ok=True)
        self.connected = False
        self.busy = False
        self.hotspot_ssid = ""
        self.hotspot_password = ""
        self.registry_server = None
        self.data_server = None
        self.connection_store = None
        self._node_active = False
        self.auth = AuthManager() if AuthManager is not None else None
        self._logged_in = False
        self._session_check_job = None
        self._login_overlay = None
        self._login_password_var = None
        self._login_error_var = None
        self._loading_overlay = None
        self._loading_backdrop = None
        self._loading_canvas = None
        self._loading_bar_canvas = None
        self._loading_status_var = None
        self._loading_spin_job = None
        self._loading_fade_job = None
        self._loading_spin_step = 0
        self._loading_backdrop_strength = 0.0
        self._api_loading_count = 0
        self._api_loading_lock = threading.Lock()
        self._loading_caption_base = "Đang xử lý"
        self._device_names = {}

        self._setup_theme()
        self._install_ambient_background()
        self._build_ui()
        self._build_login_overlay()
        self._build_loading_overlay()
        self.after_idle(self._sync_shell_layout)
        self.after(50, self._fade_in_window)
        self._init_hotspot_labels()
        self._init_network_labels()
        self._set_connection_state(False, _T("not_verified"))
        self._set_status(_T("please_login"))
        self._show_login_overlay()
        self.after(200, self._refresh_local_files_tree)

    def _setup_theme(self):
        self._font_ui = ("Inter", 10)
        self._font_ui_bold = ("Inter", 10, "bold")
        self._font_title = ("Inter", 14, "bold")
        self._font_sub = ("Inter", 9)
        self._font_mono = ("Consolas", 11)
        self._font_mono_sm = ("Consolas", 9)
        self._font_section = ("Inter", 11, "bold")

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=_THEME["bg"], foreground=_THEME["text"], font=self._font_ui)
        style.configure("TFrame", background=_THEME["bg"])
        style.configure("Card.TFrame", background=_THEME["surface"])
        style.configure(
            "Card.TLabelframe",
            background=_THEME["surface"],
            bordercolor=_THEME["border"],
            relief="solid",
            borderwidth=1,
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=_THEME["surface"],
            foreground=_THEME["primary"],
            font=self._font_section,
        )
        style.configure("TLabel", background=_THEME["bg"], foreground=_THEME["text"])
        style.configure("Card.TLabel", background=_THEME["surface"], foreground=_THEME["text"])
        style.configure("Muted.TLabel", background=_THEME["surface"], foreground=_THEME["text_muted"], font=self._font_sub)
        style.configure("Header.TLabel", background=_THEME["header"], foreground="#ffffff", font=self._font_title)
        style.configure("HeaderSub.TLabel", background=_THEME["header"], foreground="#b8d4f0", font=self._font_sub)
        style.configure("BadgeOk.TLabel", background=_THEME["success_bg"], foreground=_THEME["success"], font=self._font_ui_bold)
        style.configure("BadgeWarn.TLabel", background=_THEME["warning_bg"], foreground=_THEME["warning"], font=self._font_ui_bold)
        style.configure("Chain.TLabel", background=_THEME["chain_bg"], foreground=_THEME["chain"], font=self._font_mono_sm)
        style.configure(
            "Primary.TButton",
            font=self._font_ui_bold,
            padding=(14, 8),
            background="#6e6e73",
            foreground="#ffffff",
            borderwidth=1,
            bordercolor="#aeaeb2",
            focusthickness=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#3a3a3c"), ("pressed", "#3a3a3c")],
            bordercolor=[("active", "#2979ff"), ("pressed", "#2979ff")],
            foreground=[("disabled", "#94a3b8")],
        )
        style.configure(
            "Secondary.TButton",
            font=self._font_ui,
            padding=(12, 7),
            background="#7a7a80",
            foreground="#ffffff",
            borderwidth=1,
            bordercolor="#aeaeb2",
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#3a3a3c"), ("pressed", "#3a3a3c")],
            bordercolor=[("active", "#2979ff"), ("pressed", "#2979ff")],
        )
        style.configure(
            "Danger.TButton",
            font=self._font_ui_bold,
            padding=(12, 7),
            background="#ff3b30",
            foreground="#ffffff",
            borderwidth=1,
            bordercolor="#d92d22",
        )
        style.map("Danger.TButton", background=[("active", "#e23227"), ("pressed", "#e23227")], bordercolor=[("active", "#c8291f")])
        style.configure(
            "Treeview",
            background=_THEME["surface"],
            fieldbackground=_THEME["surface"],
            foreground=_THEME["text"],
            rowheight=28,
            bordercolor=_THEME["border"],
            lightcolor=_THEME["surface"],
            darkcolor=_THEME["border"],
            font=self._font_ui,
        )
        style.configure(
            "Treeview.Heading",
            background="#f8fafc",
            foreground="#475569",
            font=self._font_ui_bold,
            relief="flat",
        )
        style.map("Treeview", background=[("selected", _THEME["primary"])], foreground=[("selected", "#ffffff")])
        style.configure("Status.TLabel", background=_THEME["status_bar"], foreground=_THEME["text"], font=self._font_sub, padding=(10, 6))

        self._shadow_layer_colors = [
            _THEME["shadow_1"],
            _THEME["shadow_2"],
            _THEME["shadow_3"],
            _THEME["shadow_4"],
            _THEME["shadow_5"],
        ]
        self._glow_layer_colors = [
            _THEME["glow_1"],
            _THEME["glow_2"],
            _THEME["glow_3"],
        ]

    def _install_ambient_background(self):
        self._shell = tk.Canvas(self, highlightthickness=0, bg=_THEME["bg"], bd=0)
        self._shell.pack(fill=tk.BOTH, expand=True)
        self._main_host = tk.Frame(self._shell, bg=_THEME["bg"])
        self._shell_window = self._shell.create_window(0, 0, window=self._main_host, anchor="nw")
        self._shell.bind("<Configure>", self._on_shell_resize)

    def _on_shell_resize(self, event):
        if event.width < 2 or event.height < 2:
            return
        self._shell.itemconfigure(self._shell_window, width=event.width, height=event.height)
        self._shell.configure(scrollregion=(0, 0, event.width, event.height))
        self._paint_ambient(event)

    def _sync_shell_layout(self):
        self.update_idletasks()
        width = self._shell.winfo_width()
        height = self._shell.winfo_height()
        if width > 1 and height > 1:
            self._shell.itemconfigure(self._shell_window, width=width, height=height)
            self._paint_ambient()

    def _paint_ambient(self, _event=None):
        canvas = self._shell
        if not canvas.winfo_exists():
            return
        canvas.delete("amb")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        steps = 32
        top = (0xeb, 0xf1, 0xf8)
        bottom = (0xf6, 0xf9, 0xfc)
        band = max(height // steps, 1)
        for index in range(steps):
            ratio = index / max(steps - 1, 1)
            red = int(top[0] + (bottom[0] - top[0]) * ratio)
            green = int(top[1] + (bottom[1] - top[1]) * ratio)
            blue = int(top[2] + (bottom[2] - top[2]) * ratio)
            color = f"#{red:02x}{green:02x}{blue:02x}"
            y0 = index * band
            y1 = height if index == steps - 1 else (index + 1) * band
            canvas.create_rectangle(0, y0, width, y1, fill=color, outline="", tags="amb")
        spacing = 26
        dot = "#d2dce8"
        for x in range(12, width, spacing):
            for y in range(100, height, spacing):
                canvas.create_oval(x, y, x + 2, y + 2, fill=dot, outline="", tags="amb")
        canvas.tag_raise(self._shell_window)

    def _fade_in_window(self, alpha=0.0):
        try:
            self.attributes("-alpha", alpha)
        except tk.TclError:
            return
        if alpha < 1.0:
            self.after(18, lambda: self._fade_in_window(min(1.0, alpha + 0.09)))

    def _shadow_shell(self, parent, pady=(14, 0), expand=False, padx=(1, 8)):
        depth = 3
        host = tk.Frame(parent, bg=_THEME["bg"])
        pack_kw = {"fill": tk.X, "pady": pady, "padx": padx}
        if expand:
            pack_kw["fill"] = tk.BOTH
            pack_kw["expand"] = True
        host.pack(**pack_kw)

        shadow = tk.Frame(host, bg=_THEME["shadow_3"])
        shadow.pack(fill=tk.BOTH, expand=True)

        surface = tk.Frame(
            shadow,
            bg=_THEME["surface"],
            highlightthickness=1,
            highlightbackground=_THEME["border"],
        )
        surface.pack(fill=tk.BOTH, expand=True, padx=(0, depth), pady=(0, depth))
        return surface

    def _glow_panel(self, parent, bg, fg, pady=(8, 0), expand=False):
        depth = 2
        host = tk.Frame(parent, bg=_THEME["surface"])
        pack_kw = {"fill": tk.X, "pady": pady, "padx": (0, 4)}
        if expand:
            pack_kw["fill"] = tk.BOTH
            pack_kw["expand"] = True
        host.pack(**pack_kw)

        glow = tk.Frame(host, bg=_THEME["border"])
        glow.pack(fill=tk.BOTH, expand=True)

        surface = tk.Frame(
            glow,
            bg=bg,
            highlightthickness=1,
            highlightbackground=_THEME["border"],
        )
        surface.pack(fill=tk.BOTH, expand=True, padx=(0, depth), pady=(0, depth))
        return surface, fg

    def _pill_button_canvas(self, parent, text, bg_color, fg_color, border_color, hover_bg, hover_border, font, command):
        import tkinter.font as tkfont
        f = tkfont.Font(font=font)
        text_w = f.measure(text)
        text_h = f.metrics("linespace")
        pad_x, pad_y = 18, 8
        w = text_w + pad_x * 2 + 2
        h = text_h + pad_y * 2 + 2
        r = h // 2

        try:
            pbg = parent.cget("bg")
        except tk.TclError:
            try:
                pbg = parent.cget("background")
            except tk.TclError:
                pbg = _THEME["surface"]

        canvas = tk.Canvas(parent, width=w, height=h, bg=pbg, highlightthickness=0, bd=0)
        _state = [text, bg_color, border_color]

        def draw(bg, border):
            canvas.delete("all")
            canvas.create_oval(1, 1, h - 1, h - 1, fill=bg, outline=border, width=2)
            canvas.create_oval(w - h + 1, 1, w - 1, h - 1, fill=bg, outline=border, width=2)
            canvas.create_rectangle(r, 1, w - r, h - 1, fill=bg, outline="", width=0)
            canvas.create_line(r, 1, w - r, 1, fill=border, width=2)
            canvas.create_line(r, h - 1, w - r, h - 1, fill=border, width=2)
            canvas.create_text(w // 2, h // 2, text=_state[0], font=font, fill=fg_color)

        def update_text(new_text):
            _state[0] = new_text
            draw(_state[1], _state[2])

        canvas.update_text = update_text

        draw(bg_color, border_color)
        canvas.configure(cursor="hand2")

        def on_enter(_e):
            draw(hover_bg, hover_border)

        def on_leave(_e):
            draw(bg_color, border_color)

        def on_click(_e):
            command()

        canvas.bind("<Enter>", on_enter)
        canvas.bind("<Leave>", on_leave)
        canvas.bind("<Button-1>", on_click)
        return canvas

    def _shadow_button(self, parent, style, text, command, side=tk.LEFT, padx=(0, 8)):
        try:
            parent_bg = parent.cget("bg")
        except tk.TclError:
            parent_bg = _THEME["surface"]

        if style == "Primary.TButton":
            bg_color = "#6e6e73"
            fg_color = "#ffffff"
            border_color = "#aeaeb2"
            hover_bg = "#3a3a3c"
            hover_border = "#2979ff"
            font = self._font_ui_bold
        elif style == "Danger.TButton":
            bg_color = "#ff3b30"
            fg_color = "#ffffff"
            border_color = "#d92d22"
            hover_bg = "#e23227"
            hover_border = "#c8291f"
            font = self._font_ui_bold
        else:
            bg_color = "#7a7a80"
            fg_color = "#ffffff"
            border_color = "#aeaeb2"
            hover_bg = "#3a3a3c"
            hover_border = "#2979ff"
            font = self._font_ui

        btn = self._pill_button_canvas(
            parent, text, bg_color, fg_color, border_color, hover_bg, hover_border, font, command
        )
        btn.pack(side=side, padx=padx, pady=3)
        return btn

    def _sidebar_section(self, parent, title, pady=(14, 0)):
        host = tk.Frame(parent, bg=_THEME["surface"],
                        highlightthickness=1, highlightbackground=_THEME["border"])
        host.pack(fill=tk.X, pady=pady, padx=(4, 4))

        title_row = tk.Frame(host, bg=_THEME["surface"])
        title_row.pack(fill=tk.X, padx=14, pady=(12, 0))
        title_lbl = tk.Label(
            title_row,
            text=title,
            font=self._font_ui_bold,
            bg=_THEME["surface"],
            fg=_THEME["text"],
            anchor=tk.W,
        )
        title_lbl.pack(side=tk.LEFT)

        head_row = tk.Frame(host, bg=_THEME["surface"])
        head_row.pack(fill=tk.X, padx=14, pady=(2, 6))

        tk.Frame(host, bg=_THEME["border"], height=1).pack(fill=tk.X, padx=14)

        body = tk.Frame(host, bg=_THEME["surface"])
        body.pack(fill=tk.X, padx=0, pady=(4, 8))

        return {"host": host, "title_row": title_row, "head_row": head_row, "body": body, "title_lbl": title_lbl}

    def _card(self, parent, title, pady=(14, 0), expand=False):
        surface = self._shadow_shell(parent, pady=pady, expand=expand)
        head = tk.Frame(surface, bg=_THEME["surface"])
        head.pack(fill=tk.X, padx=18, pady=(16, 0))
        tk.Frame(head, bg=_THEME["primary"], width=4, height=20).pack(side=tk.LEFT, padx=(0, 12))
        title_lbl = tk.Label(
            head,
            text=title.upper(),
            font=self._font_section,
            bg=_THEME["surface"],
            fg=_THEME["primary"],
        )
        title_lbl.pack(side=tk.LEFT)
        tk.Frame(surface, bg=_THEME["border"], height=1).pack(fill=tk.X, padx=18, pady=(12, 0))
        inner = ttk.Frame(surface, style="Card.TFrame")
        inner.pack(fill=tk.BOTH, expand=True, padx=18, pady=(14, 18))
        return inner, title_lbl

    @staticmethod
    def _device_identity_hash(key):
        digest = hashlib.sha256(f"phantom-device:{key}".encode("utf-8")).hexdigest()
        return digest[:_HASH_BLOCK_LENGTH]

    @staticmethod
    def _device_connection_id(ip):
        address = (ip or "").strip()
        if not address:
            return ""
        digest = hashlib.sha256(
            f"phantom-connection:{address}".encode("utf-8")
        ).hexdigest()
        return digest[:_HASH_BLOCK_LENGTH]

    def _device_connection_display(self, ip):
        address = (ip or "").strip()
        if not address:
            return "—"
        name = (self._device_names.get(address) or "").strip()
        if name:
            return name
        connection_id = self._device_connection_id(ip)
        return connection_id or "—"

    def _cache_device_name_from_config(self, ip, data):
        if not isinstance(data, dict) or not data.get("ok"):
            return
        identity = (data.get("config") or {}).get("dinh_danh") or {}
        name = (identity.get("ten_thiet_bi") or "").strip()
        if name:
            self._store_device_name(ip, name)

    def _auto_register_device_from_config(self, ip, data):
        if not isinstance(data, dict) or not data.get("ok"):
            return
        if self.registry_server is None:
            return
        identity = (data.get("config") or {}).get("dinh_danh") or {}
        device_id = (identity.get("id_thiet_bi") or "").strip() or None
        mac = (data.get("mac_address") or "").strip() or None
        try:
            self.registry_server.registry.register(ip=ip, device_id=device_id, mac=mac)
        except (ValueError, AttributeError):
            pass

    def _prefetch_device_names(self, connections):
        if requests is None:
            return
        for entry in connections:
            device_type = (entry.get("type") or "").strip().upper()
            ip, port = self._resolve_connection(entry)
            if not ip:
                continue
            if device_type == "A":
                self._fetch_device_name_background(ip, port)
            elif device_type in ("B", "PHANTOMR3B"):
                self._fetch_device_info_background(ip, port)
                self._fetch_device_dinh_danh_name_background(ip, port)

    def _fetch_device_dinh_danh_name_background(self, ip, port):
        address = (ip or "").strip()
        if not address or (self._device_names.get(address) or "").strip():
            return
        url = self._device_service_url(ip, "/api/dinh-danh", port=port)

        def worker():
            try:
                if requests is None:
                    return
                r = requests.get(url, headers=self._headers(), timeout=6)
                r.raise_for_status()
                data = r.json()
                if not data.get("ok"):
                    return
                name = (data.get("ten_thiet_bi") or "").strip()
                if name:
                    self.after(0, lambda n=name: self._store_device_name(address, n))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _fetch_device_info_background(self, ip, port):
        address = (ip or "").strip()
        if not address:
            return
        url = self._device_service_url(ip, "/api/device-info", port=port)

        def worker():
            try:
                if requests is None:
                    return
                r = requests.get(url, headers=self._headers(), timeout=6)
                r.raise_for_status()
                data = r.json()
                if not data.get("ok"):
                    return
                device_id = (data.get("id_thiet_bi") or "").strip() or None
                mac = (data.get("mac") or "").strip() or None
                if self.registry_server is not None:
                    try:
                        self.registry_server.registry.register(
                            ip=address, device_id=device_id, mac=mac
                        )
                        self.after(0, self.refresh_registered_devices)
                    except (ValueError, AttributeError):
                        pass
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _fetch_device_name_background(self, ip, port):
        address = (ip or "").strip()
        if not address or (self._device_names.get(address) or "").strip():
            return
        config_url = self._device_service_url(ip, "/api/config", port=port)

        def worker():
            try:
                if requests is None:
                    return
                r = requests.get(
                    config_url,
                    headers=self._headers(),
                    timeout=15,
                )
                r.raise_for_status()
                data = r.json()
                if not data.get("ok"):
                    return
                identity = (data.get("config") or {}).get("dinh_danh") or {}
                name = (identity.get("ten_thiet_bi") or "").strip()
                if name:
                    self.after(0, lambda n=name: self._store_device_name(address, n))
                self.after(0, lambda d=data: self._auto_register_device_from_config(address, d))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _store_device_name(self, ip, name):
        address = (ip or "").strip()
        text = (name or "").strip()
        if not address or not text:
            return
        if self._device_names.get(address) == text:
            return
        self._device_names[address] = text
        self.refresh_device_connections()

    @staticmethod
    def _generate_hash_bundle():
        return [
            "".join(secrets.choice(_HASH_ALPHABET) for _ in range(_HASH_BLOCK_LENGTH))
            for _ in range(_HASH_BLOCK_COUNT)
        ]

    @staticmethod
    def _hash_bundle_summary(hashes):
        if not hashes:
            return ""
        preview = hashes[0][:12] + "..." if len(hashes[0]) > 12 else hashes[0]
        return f"{len(hashes)} khối · {preview}"

    @staticmethod
    def _normalize_hash_bundle(data):
        if len(data) != _HASH_BLOCK_COUNT:
            raise ValueError(f"Bộ hash phải có đúng {_HASH_BLOCK_COUNT} chuỗi.")
        normalized = []
        for index, entry in enumerate(data, start=1):
            if not isinstance(entry, str):
                raise ValueError(f"Khối {index} phải là chuỗi.")
            value = entry.strip()
            if len(value) != _HASH_BLOCK_LENGTH:
                raise ValueError(
                    f"Khối {index} phải có {_HASH_BLOCK_LENGTH} ký tự (hiện có {len(value)})."
                )
            normalized.append(value)
        return normalized

    @classmethod
    def _parse_hash_bundle_text(cls, raw_text):
        text = (raw_text or "").strip()
        if not text:
            raise ValueError("Dán mảng JSON hoặc 5 dòng, mỗi dòng 32 ký tự.")
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return cls._normalize_hash_bundle(data)
        except json.JSONDecodeError:
            pass
        lines = []
        for line in text.splitlines():
            chunk = line.strip().rstrip(",").strip('"').strip("'")
            if chunk:
                lines.append(chunk)
        if len(lines) == _HASH_BLOCK_COUNT:
            return cls._normalize_hash_bundle(lines)
        raise ValueError(
            "Dùng mảng JSON 5 chuỗi, hoặc dán 5 dòng (mỗi dòng 32 ký tự)."
        )

    def _refresh_device_item_summary(self, item):
        item["summary_var"].set(self._hash_bundle_summary(item["hashes"]))

    def _copy_hashes_to_clipboard(self, hashes):
        payload = json.dumps(hashes, ensure_ascii=False)
        self.clipboard_clear()
        self.clipboard_append(payload)
        self.update()
        self._set_status("Đã sao chép bộ hash vào clipboard.")

    def copy_hotspot_ssid(self):
        ssid = str(self.hotspot_ssid or "").strip()
        if not ssid:
            messagebox.showwarning(_T("no_ssid_title"), _T("no_ssid_msg"))
            return
        self.clipboard_clear()
        self.clipboard_append(ssid)
        self.update()
        self._set_status("Đã sao chép SSID.")

    def copy_device_ap_ssid(self, connection):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return
        ip, port = self._resolve_connection(connection)
        if not ip:
            messagebox.showwarning(_T("missing_ip"), _T("device_no_ip"))
            return
        display_id = self._device_connection_display(ip)
        status_url = self._device_service_url(ip, "/api/status", port=port)

        def task():
            _terminal_decode_log(
                f"copy ap_ssid start ip={ip} port={port} device={display_id} url={status_url}"
            )
            r = self._http_get(
                status_url,
                headers=self._headers(),
                timeout=self._request_timeout(),
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                raise ValueError(data.get("error") or "invalid status response")
            ap_ssid = str(data.get("ap_ssid", "")).strip()
            if not ap_ssid:
                raise ValueError("Thiết bị không trả về ap_ssid.")
            _terminal_decode_log(f"copy ap_ssid ok device={display_id} ap_ssid={ap_ssid}")

            def update_ui():
                self.clipboard_clear()
                self.clipboard_append(ap_ssid)
                self.update()
                self._set_status(f"Đã sao chép SSID từ {display_id}.")
                _terminal_decode_log(f"copy ap_ssid clipboard device={display_id}")

            self.after(0, update_ui)

        self._run_async(
            f"Đang lấy SSID từ {display_id}...",
            task,
            failure_text=f"Không lấy được SSID từ {display_id}.",
            affects_connection=False,
        )

    def _gen_device_hashes_b(self, item):
        item["hashes"] = self._generate_hash_bundle()
        self._refresh_device_item_summary(item)
        self._set_status(f"Đã tạo bộ hash cho {item['name']}.")

    def _copy_device_hashes_b(self, item):
        if not item["hashes"]:
            messagebox.showwarning(
                "Chưa có bộ hash",
                f"Hãy tạo bộ hash cho {item['name']} trước khi sao chép.",
            )
            return
        self._copy_hashes_to_clipboard(item["hashes"])

    def _open_hash_update_dialog(self, item):
        dialog = tk.Toplevel(self)
        dialog.title(f"Cập nhật hash — {item['name']}")
        dialog.minsize(560, 320)
        dialog.transient(self)
        dialog.configure(bg=_THEME["surface"])
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        tk.Label(
            dialog,
            text="Dán mảng JSON từ loại B (hoặc 5 dòng, mỗi dòng 32 ký tự). Ctrl+V để dán.",
            font=self._font_ui,
            bg=_THEME["surface"],
            fg=_THEME["text"],
            anchor=tk.W,
            wraplength=620,
            padx=16,
        ).grid(row=0, column=0, sticky=tk.EW, pady=(16, 8))

        editor_frame = tk.Frame(dialog, bg=_THEME["surface"])
        editor_frame.grid(row=1, column=0, sticky=tk.NSEW, padx=16, pady=(0, 8))
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.rowconfigure(0, weight=1)

        editor = tk.Text(
            editor_frame,
            font=self._font_mono,
            bg="#ffffff",
            fg=_THEME["text"],
            insertbackground=_THEME["text"],
            relief=tk.SOLID,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=_THEME["border"],
            highlightcolor=_THEME["primary"],
            wrap=tk.WORD,
            height=14,
            undo=True,
        )
        scroll = ttk.Scrollbar(editor_frame, orient=tk.VERTICAL, command=editor.yview)
        editor.configure(yscrollcommand=scroll.set)
        editor.grid(row=0, column=0, sticky=tk.NSEW)
        scroll.grid(row=0, column=1, sticky=tk.NS)

        if item["hashes"]:
            editor.insert("1.0", json.dumps(item["hashes"], ensure_ascii=False, indent=2))
        else:
            editor.insert("1.0", "[\n  \"\",\n  \"\",\n  \"\",\n  \"\",\n  \"\"\n]")

        actions = tk.Frame(dialog, bg=_THEME["surface"])
        actions.grid(row=2, column=0, sticky=tk.EW, padx=16, pady=(0, 16))

        def apply_update():
            try:
                bundle = self._parse_hash_bundle_text(editor.get("1.0", tk.END))
            except ValueError as exc:
                messagebox.showerror(_T("invalid_hash_title"), str(exc), parent=dialog)
                return
            item["hashes"] = bundle
            self._refresh_device_item_summary(item)
            self._set_status(f"Đã cập nhật bộ hash cho {item['name']}.")
            dialog.destroy()

        def paste_from_clipboard(_event=None):
            try:
                clip = dialog.clipboard_get()
            except tk.TclError:
                return "break"
            if editor.tag_ranges(tk.SEL):
                editor.delete(tk.SEL_FIRST, tk.SEL_LAST)
            editor.insert(tk.INSERT, clip)
            return "break"

        editor.bind("<Control-v>", paste_from_clipboard)
        editor.bind("<Control-V>", paste_from_clipboard)
        def select_all(_event=None):
            editor.tag_add(tk.SEL, "1.0", tk.END)
            return "break"

        editor.bind("<Control-a>", select_all)
        editor.bind("<Control-A>", select_all)

        self._shadow_button(actions, "Secondary.TButton", "Hủy", dialog.destroy, side=tk.RIGHT, padx=(8, 0))
        self._shadow_button(actions, "Primary.TButton", "Áp dụng", apply_update, side=tk.RIGHT)

        self._finalize_toplevel(dialog, 680, 400)
        editor.focus_force()
        if not item["hashes"]:
            editor.tag_add(tk.SEL, "1.0", tk.END)

    def _build_device_connection_items(self, parent):
        self._connection_panel = parent

    def _conn_dot(self, parent, color):
        c = tk.Canvas(parent, width=10, height=10, bg=_THEME["surface"],
                      highlightthickness=0, bd=0)
        c.create_oval(1, 1, 9, 9, fill=color, outline="")
        c.pack(side=tk.LEFT, padx=(0, 6))
        return c

    def _dot_menu_button(self, parent, conn, device_type):
        """Three-dot context menu button."""
        btn_bg = _THEME["surface"]
        canvas = tk.Canvas(parent, width=22, height=22, bg=btn_bg,
                           highlightthickness=0, bd=0, cursor="hand2")

        def draw(bg):
            canvas.delete("all")
            canvas.configure(bg=bg)
            for dy in (4, 11, 18):
                canvas.create_oval(9, dy, 13, dy + 4, fill=_THEME["text_muted"], outline="")

        draw(btn_bg)
        canvas.bind("<Enter>", lambda _e: draw(_THEME["border"]))
        canvas.bind("<Leave>", lambda _e: draw(btn_bg))

        def show_menu(_e):
            menu = tk.Menu(self, tearoff=0, font=self._font_ui,
                           bg=_THEME["surface"], fg=_THEME["text"],
                           activebackground=_THEME["primary_soft"],
                           activeforeground=_THEME["primary"],
                           relief="solid", bd=1)
            if device_type == "A":
                menu.add_command(label="Xem chi tiết",
                                 command=lambda: self.view_device_config(conn))
                menu.add_command(label="Danh sách file",
                                 command=lambda: self.show_device_files(conn))
                menu.add_command(label="Upload",
                                 command=lambda: self.upload_to_device(conn))
            else:
                menu.add_command(label="Xem chi tiết",
                                 command=lambda: self.view_device_dinh_danh(conn))
                menu.add_command(label="Danh sách file",
                                 command=lambda: self.show_device_files(conn))
                menu.add_command(label="Upload",
                                 command=lambda: self.upload_to_device(conn))
            try:
                menu.tk_popup(canvas.winfo_rootx(), canvas.winfo_rooty() + 22)
            finally:
                menu.grab_release()

        canvas.bind("<Button-1>", show_menu)
        canvas.pack(side=tk.RIGHT, padx=(4, 2))
        return canvas

    def refresh_device_connections(self):
        panel = getattr(self, "_connection_panel", None)
        if panel is None:
            return
        for widget in panel.winfo_children():
            widget.destroy()
        if self.connection_store is None:
            if hasattr(self, "_conn_count_badge_var"):
                self._conn_count_badge_var.set("0")
            return

        connections = self.connection_store.list_connections()
        if hasattr(self, "_conn_count_badge_var"):
            self._conn_count_badge_var.set(str(len(connections)))
        if hasattr(self, "_conn_sub_var"):
            self._conn_sub_var.set(f"KẾT NỐI ({len(connections)})")

        _type_map = {"A": "PHANTOMR3A", "B": "PHANTOMR3B", "PHANTOMR3B": "PHANTOMR3B"}

        for entry in connections:
            device_type = (entry.get("type") or "").strip().upper()
            ip = entry.get("ip", "")
            registered_at = entry.get("registered_at", 0)
            display_name = self._device_connection_display(ip)
            type_label = _type_map.get(device_type, device_type)

            mac_val = ""
            reg_device_id = ""
            if self.registry_server is not None:
                for reg_entry in self.registry_server.registry.list_devices():
                    if reg_entry.get("ip") == ip:
                        mac_val = reg_entry.get("mac") or ""
                        reg_device_id = reg_entry.get("device_id") or ""
                        break

            # tên chính hiển thị là device_id nếu có, fallback display_name
            main_name = (reg_device_id or display_name or ip).strip()
            # badge nhỏ = display_name (tên kết nối ngắn) nếu khác main_name
            conn_badge_text = display_name if display_name != main_name else ""

            conn_time = (
                datetime.datetime.fromtimestamp(registered_at).strftime("%d-%m-%Y %H:%M:%S")
                if registered_at else "—"
            )

            # ── card shell ───────────────────────────────────────────────
            card_shell = tk.Frame(
                panel, bg=_THEME["surface"],
                highlightthickness=1, highlightbackground=_THEME["border"],
            )
            card_shell.pack(fill=tk.X, padx=10, pady=(6, 0))

            # ── row 1: dot + name + Online badge + three-dot menu ────────
            top = tk.Frame(card_shell, bg=_THEME["surface"])
            top.pack(fill=tk.X, padx=12, pady=(10, 4))

            dot_c = tk.Canvas(top, width=10, height=10, bg=_THEME["surface"],
                              highlightthickness=0, bd=0)
            dot_c.create_oval(1, 1, 9, 9, fill=_THEME["success"], outline="")
            dot_c.pack(side=tk.LEFT, padx=(0, 6), pady=2)

            tk.Label(
                top, text=main_name,
                font=self._font_ui_bold,
                bg=_THEME["surface"], fg=_THEME["text"],
            ).pack(side=tk.LEFT)

            # three-dot at far right
            self._dot_menu_button(top, entry, device_type)

            # Online badge just left of three-dot
            online_badge = tk.Frame(top, bg=_THEME["success_bg"],
                                    highlightthickness=1,
                                    highlightbackground=_THEME["success"])
            online_badge.pack(side=tk.RIGHT, padx=(0, 6))
            online_dot = tk.Canvas(online_badge, width=8, height=8,
                                   bg=_THEME["success_bg"], highlightthickness=0, bd=0)
            online_dot.create_oval(1, 1, 7, 7, fill=_THEME["success"], outline="")
            online_dot.pack(side=tk.LEFT, padx=(6, 2), pady=3)
            tk.Label(
                online_badge, text="Online",
                font=self._font_sub,
                bg=_THEME["success_bg"], fg=_THEME["success"],
                padx=4, pady=2,
            ).pack(side=tk.LEFT)

            # ── row 2: small badges ──────────────────────────────────────
            badge_row = tk.Frame(card_shell, bg=_THEME["surface"])
            badge_row.pack(fill=tk.X, padx=12, pady=(0, 6))

            for btext, bfg, bbg in [
                (conn_badge_text, _THEME["primary"], _THEME["primary_soft"]),
                (type_label,      _THEME["chain"],   _THEME["chain_bg"]),
            ]:
                if not btext:
                    continue
                bf = tk.Frame(badge_row, bg=bbg,
                              highlightthickness=1, highlightbackground=bfg)
                bf.pack(side=tk.LEFT, padx=(0, 6))
                tk.Label(bf, text=btext, font=self._font_mono_sm,
                         bg=bbg, fg=bfg, padx=6, pady=2).pack()

            # ── separator ───────────────────────────────────────────────
            tk.Frame(card_shell, bg=_THEME["border"], height=1).pack(fill=tk.X, padx=12)

            # ── row 3: 2-column info (MAC | Thời gian) ──────────────────
            info = tk.Frame(card_shell, bg=_THEME["surface"])
            info.pack(fill=tk.X, padx=12, pady=(8, 10))
            info.columnconfigure(0, weight=1)
            info.columnconfigure(1, weight=1)

            # left cell — MAC
            left_cell = tk.Frame(info, bg=_THEME["surface"])
            left_cell.grid(row=0, column=0, sticky=tk.W)
            mac_label_row = tk.Frame(left_cell, bg=_THEME["surface"])
            mac_label_row.pack(anchor=tk.W)
            tk.Label(mac_label_row, text="⊟", font=self._font_sub,
                     bg=_THEME["surface"], fg=_THEME["text_muted"]).pack(side=tk.LEFT, padx=(0, 4))
            tk.Label(mac_label_row, text="Địa chỉ MAC", font=self._font_sub,
                     bg=_THEME["surface"], fg=_THEME["text_muted"]).pack(side=tk.LEFT)
            tk.Label(left_cell, text=mac_val or ip,
                     font=self._font_mono_sm,
                     bg=_THEME["surface"], fg=_THEME["text"],
                     anchor=tk.W).pack(anchor=tk.W)

            # right cell — Thời gian
            right_cell = tk.Frame(info, bg=_THEME["surface"])
            right_cell.grid(row=0, column=1, sticky=tk.W, padx=(8, 0))
            time_label_row = tk.Frame(right_cell, bg=_THEME["surface"])
            time_label_row.pack(anchor=tk.W)
            tk.Label(time_label_row, text="⊙", font=self._font_sub,
                     bg=_THEME["surface"], fg=_THEME["text_muted"]).pack(side=tk.LEFT, padx=(0, 4))
            tk.Label(time_label_row, text="Thời gian kết nối", font=self._font_sub,
                     bg=_THEME["surface"], fg=_THEME["text_muted"]).pack(side=tk.LEFT)
            tk.Label(right_cell, text=conn_time,
                     font=self._font_mono_sm,
                     bg=_THEME["surface"], fg=_THEME["text"],
                     anchor=tk.W).pack(anchor=tk.W)

        self._prefetch_device_names(connections)
        self._update_header_online_state()

    @staticmethod
    def _resolve_connection(connection):
        if isinstance(connection, dict):
            ip = str(connection.get("ip", "")).strip()
            port = connection.get("port")
        else:
            ip = str(connection or "").strip()
            port = None
        if port in (None, ""):
            port = network_config.DEVICE_SERVICE_PORT if network_config else 8765
        else:
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = network_config.DEVICE_SERVICE_PORT if network_config else 8765
        return ip, port

    def _device_service_url(self, device_ip, path, port=None):
        ip = (device_ip or "").strip()
        if port in (None, ""):
            port = network_config.DEVICE_SERVICE_PORT if network_config else 8765
        else:
            port = int(port)
        suffix = path if path.startswith("/") else f"/{path}"
        return f"http://{ip}:{port}{suffix}"

    def _device_upload_url(self, device_ip, port=None):
        return self._device_service_url(device_ip, "/api/upload", port=port)

    @staticmethod
    def _resolve_public_key_path(source_file_path):
        source_parent = Path(source_file_path).resolve().parent
        app_dir = Path(__file__).resolve().parent
        for candidate in (
            source_parent / "public.key",
            app_dir / "public.key",
        ):
            if candidate.is_file():
                return str(candidate)
        return None

    @staticmethod
    def _resolve_private_key_path():
        app_dir = Path(__file__).resolve().parent
        candidate = app_dir / "private.key"
        if candidate.is_file():
            return str(candidate)
        return None

    def _pick_private_key_path(self, parent=None):
        path = self._resolve_private_key_path()
        if path:
            return path
        return filedialog.askopenfilename(
            title="Chọn private.key để giải mã",
            filetypes=[("Key file", "*.key"), ("All files", "*.*")],
            parent=parent,
        )

    def _ensure_decrypt_ready(self, parent=None):
        if decrypt_bin_bytes is None or _phtm_load_private_key is None:
            messagebox.showerror(
                "Thiếu module",
                "Không tải được phantom_bundle.py.",
                parent=parent,
            )
            return False
        if not _CRYPTO_OK:
            messagebox.showerror(
                "Thiếu thư viện",
                "Cài: pip install cryptography",
                parent=parent,
            )
            return False
        return True

    def _download_and_decrypt_bin(
        self,
        download_url,
        filename,
        output_dir,
        private_key_path,
        on_status=None,
        show_loading_caption=True,
    ):
        def status(msg):
            _terminal_decode_log(msg)
            if on_status:
                self.after(0, lambda m=msg: on_status(m))

        status(f"load private key: {private_key_path}")
        _, private_key_raw = _phtm_load_private_key(private_key_path)
        status(f"private key loaded ({len(private_key_raw)} bytes)")

        status(f"download start: {download_url}?name={filename}")
        tmp_path = None
        total = 0
        try:
            r = self._http_get(
                download_url,
                headers=self._headers(),
                params={"name": filename},
                stream=True,
                timeout=300,
            )
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
                tmp_path = tmp.name
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        tmp.write(chunk)
                        total += len(chunk)
                        if total == len(chunk) or total % (512 * 1024) < 65536:
                            status(f"downloading... {total // 1024} KB")
            status(f"download done: {total} bytes -> {tmp_path}")
            bin_bytes = Path(tmp_path).read_bytes()
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        status(f"decrypt start: {filename} -> {output_dir}")
        if show_loading_caption:
            self.after(0, lambda: self._set_loading_caption("Đang giải mã"))
        saved = decrypt_bin_bytes(
            bin_bytes,
            private_key_raw,
            Path(output_dir),
            Path(filename).stem,
        )
        status(f"decrypt done: {[str(p) for p in saved]}")
        return saved

    def _download_bin_only(self, download_url, filename, dest_dir=None, on_status=None):
        def status(msg):
            _terminal_decode_log(msg)
            if on_status:
                self.after(0, lambda m=msg: on_status(m))

        folder = Path(dest_dir) if dest_dir else self._staging_dir()
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / filename
        status(f"download start: {download_url}?name={filename}")
        total = 0
        r = self._http_get(
            download_url,
            headers=self._headers(),
            params={"name": filename},
            stream=True,
            timeout=300,
        )
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
                    if total == len(chunk) or total % (512 * 1024) < 65536:
                        status(f"downloading... {total // 1024} KB")
        status(f"download done: {total} bytes -> {dest}")
        return dest

    def upload_to_device(self, connection):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return
        if encrypt_paths_to_bin is None or _phtm_load_public_key is None:
            messagebox.showerror(_T("missing_module"), _T("phantom_bundle_missing"))
            return
        if not _CRYPTO_OK:
            messagebox.showerror(_T("missing_lib"), _T("install_cryptography"))
            return
        ip, port = self._resolve_connection(connection)
        if not ip:
            messagebox.showwarning(_T("missing_ip"), _T("device_no_ip"))
            return
        display_id = self._device_connection_display(ip)

        file_path = filedialog.askopenfilename(title="Chọn file để upload")
        if not file_path:
            return

        public_key_path = self._resolve_public_key_path(file_path)
        if not public_key_path:
            public_key_path = filedialog.askopenfilename(
                title="Chọn public.key để mã hóa",
                filetypes=[("Key file", "*.key"), ("All files", "*.*")],
            )
        if not public_key_path:
            return

        try:
            _, public_key_raw = _phtm_load_public_key(public_key_path)
        except Exception as exc:
            messagebox.showerror(_T("key_error_title"), str(exc))
            return

        upload_url = self._device_upload_url(ip, port=port)
        source_name = Path(file_path).name

        def task():
            self.after(0, lambda: self._set_status(f"Đang mã hóa {source_name}..."))
            self.after(0, lambda: self._set_loading_caption(f"Đang mã hóa {source_name}"))
            bin_bytes, bundle_name = encrypt_paths_to_bin([file_path], public_key_raw)
            bin_name = bundle_name + ".bin"
            self.after(0, lambda: self._set_status(f"Đang upload {bin_name} tới {display_id}..."))
            self.after(0, lambda: self._set_loading_caption(f"Đang upload {bin_name}"))
            files = {"file": (bin_name, io.BytesIO(bin_bytes), "application/octet-stream")}
            r = self._http_post(
                upload_url,
                headers=self._headers(),
                files=files,
                timeout=300,
            )
            r.raise_for_status()

            def update_ui():
                self._set_status(f"Đã upload {bin_name} tới thiết bị {display_id}.")
                messagebox.showinfo(
                    "Upload thành công",
                    f"Đã mã hóa {source_name} và gửi {bin_name} tới thiết bị {display_id}.",
                )

            self.after(0, update_ui)

        self._run_async(
            f"Đang mã hóa và upload tới {display_id}...",
            task,
            failure_text=f"Upload tới {display_id} thất bại. Kiểm tra thiết bị và mạng.",
            affects_connection=False,
        )

    def view_device_config(self, connection):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return
        ip, port = self._resolve_connection(connection)
        if not ip:
            messagebox.showwarning(_T("missing_ip"), _T("device_no_ip"))
            return
        display_id = self._device_connection_display(ip)

        config_url = self._device_service_url(ip, "/api/config", port=port)

        def task():
            r = self._http_get(
                config_url,
                headers=self._headers(),
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()

            def update_ui():
                self._cache_device_name_from_config(ip, data)
                self._auto_register_device_from_config(ip, data)
                self._show_device_config_dialog(ip, data, port=port)

            self.after(0, update_ui)

        self._run_async(
            f"Đang tải cấu hình từ {display_id}...",
            task,
            failure_text=(
                f"Không lấy được cấu hình từ {display_id}. "
                "Kiểm tra thiết bị và mạng."
            ),
            affects_connection=False,
        )

    def view_device_status(self, connection):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return
        ip, port = self._resolve_connection(connection)
        if not ip:
            messagebox.showwarning(_T("missing_ip"), _T("device_no_ip"))
            return
        display_id = self._device_connection_display(ip)
        status_url = self._device_service_url(ip, "/api/status", port=port)

        def task():
            r = self._http_get(
                status_url,
                headers=self._headers(),
                timeout=6,
            )
            r.raise_for_status()
            data = r.json()
            self.after(0, lambda: self._show_device_status_dialog(ip, data))

        self._run_async(
            f"Đang tải trạng thái từ {display_id}...",
            task,
            failure_text=f"Không lấy được trạng thái từ {display_id}. Kiểm tra thiết bị và mạng.",
            affects_connection=False,
        )

    def _show_device_status_dialog(self, device_ip, data):
        if not data.get("ok"):
            messagebox.showerror(
                "Lỗi",
                data.get("error") or data.get("message") or "Thiết bị trả về lỗi.",
            )
            return
        display_id = self._device_connection_display(device_ip)

        dialog = tk.Toplevel(self)
        dialog.title(f"Trạng thái thiết bị — {display_id}")
        dialog.minsize(480, 360)
        dialog.transient(self)
        dialog.configure(bg=_THEME["bg"])
        dialog.columnconfigure(0, weight=1)

        header = tk.Frame(dialog, bg=_THEME["header"])
        header.grid(row=0, column=0, sticky=tk.EW)
        header_inner = tk.Frame(header, bg=_THEME["header"])
        header_inner.pack(fill=tk.X, padx=20, pady=14)
        tk.Label(
            header_inner,
            text=_T("device_status_heading"),
            font=(self._font_ui[0], 14, "bold"),
            bg=_THEME["header"],
            fg="#ffffff",
            anchor=tk.W,
        ).pack(anchor=tk.W)
        tk.Label(
            header_inner,
            text=display_id,
            font=self._font_ui,
            bg=_THEME["header"],
            fg="#b8d4f0",
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(4, 0))

        content = tk.Frame(dialog, bg=_THEME["bg"])
        content.grid(row=1, column=0, sticky=tk.NSEW, padx=20, pady=16)
        content.columnconfigure(1, weight=1)

        rows = [
            ("Board", data.get("board")),
            ("WiFi mode", data.get("wifi_mode")),
            ("IP", data.get("ip")),
            ("Port", data.get("port")),
            ("AP SSID", data.get("ap_ssid")),
            ("AP Password", data.get("ap_pass")),
            ("SD type", data.get("sd_card_type")),
            ("SD tổng", data.get("sd_total_human")),
            ("SD đã dùng", data.get("sd_used_human")),
        ]
        for i, (label, value) in enumerate(rows):
            tk.Label(
                content,
                text=label,
                font=self._font_mono_sm,
                bg=_THEME["bg"],
                fg=_THEME["text_muted"],
                anchor=tk.W,
            ).grid(row=i, column=0, sticky=tk.W, pady=3, padx=(0, 16))
            tk.Label(
                content,
                text=value if value is not None else "—",
                font=self._font_ui,
                bg=_THEME["bg"],
                fg=_THEME["text"],
                anchor=tk.W,
            ).grid(row=i, column=1, sticky=tk.W, pady=3)

        footer = tk.Frame(dialog, bg=_THEME["surface"])
        footer.grid(row=2, column=0, sticky=tk.EW)
        tk.Frame(footer, bg=_THEME["border"], height=1).pack(fill=tk.X)
        actions = tk.Frame(footer, bg=_THEME["surface"])
        actions.pack(fill=tk.X, padx=16, pady=12)
        self._shadow_button(actions, "Secondary.TButton", "Đóng", dialog.destroy, side=tk.RIGHT)

        self._finalize_toplevel(dialog, 500, 420)

    def view_device_dinh_danh(self, connection):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return
        ip, port = self._resolve_connection(connection)
        if not ip:
            messagebox.showwarning(_T("missing_ip"), _T("device_no_ip"))
            return
        display_id = self._device_connection_display(ip)
        url = self._device_service_url(ip, "/api/dinh-danh", port=port)

        def task():
            r = self._http_get(url, headers=self._headers(), timeout=6)
            r.raise_for_status()
            data = r.json()
            self.after(0, lambda: self._show_dinh_danh_edit_dialog(ip, data, port=port))

        self._run_async(
            f"Đang tải định danh từ {display_id}...",
            task,
            failure_text=f"Không lấy được định danh từ {display_id}. Kiểm tra thiết bị và mạng.",
            affects_connection=False,
        )

    def _show_dinh_danh_edit_dialog(self, device_ip, data, port=None):
        if not data.get("ok"):
            messagebox.showerror(
                "Lỗi",
                data.get("error") or data.get("message") or "Thiết bị trả về lỗi.",
            )
            return
        display_id = self._device_connection_display(device_ip)

        dialog = tk.Toplevel(self)
        dialog.title(f"Chỉnh sửa định danh — {display_id}")
        dialog.minsize(500, 400)
        dialog.transient(self)
        dialog.grab_set()
        dialog.protocol(
            "WM_DELETE_WINDOW",
            lambda: (dialog.grab_release(), dialog.destroy()),
        )
        dialog.configure(bg=_THEME["bg"])
        dialog.columnconfigure(0, weight=1)

        header = tk.Frame(dialog, bg=_THEME["header"])
        header.grid(row=0, column=0, sticky=tk.EW)
        header_inner = tk.Frame(header, bg=_THEME["header"])
        header_inner.pack(fill=tk.X, padx=20, pady=14)
        tk.Label(
            header_inner,
            text=_T("identity_edit_heading"),
            font=(self._font_ui[0], 14, "bold"),
            bg=_THEME["header"],
            fg="#ffffff",
            anchor=tk.W,
        ).pack(anchor=tk.W)
        tk.Label(
            header_inner,
            text=display_id,
            font=self._font_ui,
            bg=_THEME["header"],
            fg="#b8d4f0",
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(4, 0))

        content = tk.Frame(dialog, bg=_THEME["bg"])
        content.grid(row=1, column=0, sticky=tk.NSEW, padx=20, pady=16)
        content.columnconfigure(1, weight=1)

        ma_id_var = tk.StringVar(value=self._identity_field_initial(data.get("ma_id")))
        ho_ten_var = tk.StringVar(value=self._identity_field_initial(data.get("ho_ten")))
        nam_sinh_var = tk.StringVar(value=self._identity_field_initial(data.get("nam_sinh")))
        dia_chi_var = tk.StringVar(value=self._identity_field_initial(data.get("dia_chi")))
        ngay_cap_var = tk.StringVar(value=self._identity_field_initial(data.get("ngay_cap_dinh_danh")))
        ten_thiet_bi_var = tk.StringVar(value=self._identity_field_initial(data.get("ten_thiet_bi")))
        id_thiet_bi_var = tk.StringVar(value=self._identity_field_initial(data.get("id_thiet_bi")))
        dia_chi_thiet_bi_var = tk.StringVar(value=self._identity_field_initial(data.get("dia_chi_thiet_bi")))

        form_refs = {
            "ma_id_var": ma_id_var,
            "ho_ten_var": ho_ten_var,
            "nam_sinh_var": nam_sinh_var,
            "dia_chi_var": dia_chi_var,
            "ngay_cap_var": ngay_cap_var,
            "ten_thiet_bi_var": ten_thiet_bi_var,
            "id_thiet_bi_var": id_thiet_bi_var,
            "dia_chi_thiet_bi_var": dia_chi_thiet_bi_var,
        }

        field_rows = [
            (_T("id_code"), ma_id_var),
            (_T("full_name"), ho_ten_var),
            (_T("birth_year"), nam_sinh_var),
            (_T("address"), dia_chi_var),
            (_T("issue_date"), ngay_cap_var),
            (_T("device_name_field"), ten_thiet_bi_var),
            (_T("device_id_field"), id_thiet_bi_var),
            (_T("device_address_field"), dia_chi_thiet_bi_var),
        ]
        for i, (label, var) in enumerate(field_rows):
            tk.Label(
                content,
                text=label,
                font=self._font_ui,
                bg=_THEME["bg"],
                fg=_THEME["text_muted"],
                anchor=tk.W,
            ).grid(row=i, column=0, sticky=tk.W, pady=4, padx=(0, 16))
            ttk.Entry(
                content,
                textvariable=var,
                font=self._font_mono,
            ).grid(row=i, column=1, sticky=tk.EW, pady=4)

        footer = tk.Frame(dialog, bg=_THEME["surface"])
        footer.grid(row=2, column=0, sticky=tk.EW)
        tk.Frame(footer, bg=_THEME["border"], height=1).pack(fill=tk.X)
        actions = tk.Frame(footer, bg=_THEME["surface"])
        actions.pack(fill=tk.X, padx=16, pady=12)
        self._shadow_button(
            actions,
            "Primary.TButton",
            "Lưu",
            lambda: self._update_dinh_danh(device_ip, dialog, form_refs, port=port),
            side=tk.RIGHT,
            padx=(0, 0),
        )
        self._shadow_button(
            actions,
            "Secondary.TButton",
            "Hủy",
            lambda: (dialog.grab_release(), dialog.destroy()),
            side=tk.RIGHT,
        )

        self._finalize_toplevel(dialog, 520, 500)

    def _update_dinh_danh(self, device_ip, dialog, form_refs, port=None):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"), parent=dialog)
            return
        try:
            ma_id = self._parse_required_text(form_refs["ma_id_var"].get(), "Mã định danh")
            ho_ten = self._parse_required_text(form_refs["ho_ten_var"].get(), "Họ và tên")
            nam_sinh = self._parse_birth_year(form_refs["nam_sinh_var"].get())
            dia_chi = self._parse_required_text(form_refs["dia_chi_var"].get(), "Địa chỉ")
            ngay_cap = self._parse_required_text(form_refs["ngay_cap_var"].get(), "Ngày cấp định danh")
            ten_thiet_bi = form_refs["ten_thiet_bi_var"].get().strip()
            id_thiet_bi = form_refs["id_thiet_bi_var"].get().strip()
            dia_chi_thiet_bi = form_refs["dia_chi_thiet_bi_var"].get().strip()
        except ValueError as exc:
            messagebox.showerror(_T("invalid_value_title"), str(exc), parent=dialog)
            return

        payload = {
            "ma_id": ma_id,
            "ho_ten": ho_ten,
            "nam_sinh": nam_sinh,
            "dia_chi": dia_chi,
            "ngay_cap_dinh_danh": ngay_cap,
            "ten_thiet_bi": ten_thiet_bi,
            "id_thiet_bi": id_thiet_bi,
            "dia_chi_thiet_bi": dia_chi_thiet_bi,
        }
        url = self._device_service_url(device_ip, "/api/dinh-danh", port=port)
        display_id = self._device_connection_display(device_ip)

        def task():
            r = self._http_post(
                url,
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=10,
            )
            r.raise_for_status()
            result = r.json()

            def update_ui():
                if not result.get("ok"):
                    messagebox.showerror(
                        "Lưu thất bại",
                        result.get("error") or result.get("message") or "Thiết bị trả về lỗi.",
                        parent=dialog,
                    )
                    return
                if ten_thiet_bi:
                    self._store_device_name(device_ip, ten_thiet_bi)
                self._set_status(f"Đã cập nhật định danh thiết bị {display_id}.")
                messagebox.showinfo(
                    "Lưu thành công",
                    result.get("message") or "Đã cập nhật định danh.",
                    parent=dialog,
                )
                dialog.grab_release()
                dialog.destroy()

            self.after(0, update_ui)

        self._run_async(
            f"Đang lưu định danh {display_id}...",
            task,
            failure_text=f"Lưu định danh {display_id} thất bại.",
            affects_connection=False,
        )

    @staticmethod
    def _format_config_value(value):
        if value is None or value == "":
            return "—"
        return str(value)

    @classmethod
    def _format_minutes(cls, value):
        text = cls._format_config_value(value)
        if text == "—":
            return text
        return f"{text} {_T('minutes_unit')}"

    @staticmethod
    def _minutes_field_initial(value):
        if value is None or value == "":
            return ""
        if isinstance(value, (int, float)):
            return str(int(value))
        return str(value).strip()

    @staticmethod
    def _identity_field_initial(value):
        if value is None or value == "":
            return ""
        if isinstance(value, (int, float)):
            return str(int(value))
        return str(value).strip()

    @staticmethod
    def _parse_required_text(value, field_label):
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field_label} không được để trống.")
        return text

    @staticmethod
    def _parse_birth_year(value):
        text = str(value or "").strip()
        if not text.isdigit():
            raise ValueError("Năm sinh phải là số nguyên.")
        year = int(text)
        if year < 1900 or year > 2100:
            raise ValueError("Năm sinh không hợp lệ.")
        return year

    @staticmethod
    def _parse_minutes_field(value, field_label):
        text = str(value or "").strip()
        if not text.isdigit():
            raise ValueError(f"{field_label} phải là số nguyên (phút).")
        minutes = int(text)
        if minutes <= 0:
            raise ValueError(f"{field_label} phải lớn hơn 0.")
        return minutes

    @property
    def _RECORDING_MODE_LABELS(self):
        return {
            "continuous": _T("mode_continuous"),
            "vad":        _T("mode_vad"),
            "interval":   _T("mode_interval"),
            "scheduled":  _T("mode_scheduled"),
        }

    @classmethod
    def _format_recording_mode(cls, value):
        key = str(value or "").strip().lower()
        if not key:
            return cls._format_config_value(value)
        return cls._RECORDING_MODE_LABELS.get(key, str(value))

    @classmethod
    def _recording_mode_api_value(cls, label):
        text = str(label or "").strip()
        if not text:
            return "continuous"
        for api_value, display in cls._RECORDING_MODE_LABELS.items():
            if text == display or text.lower() == api_value:
                return api_value
        return text

    @staticmethod
    def _is_hidden_config_row(row):
        if isinstance(row, dict):
            label = str(row.get("label", "")).lower()
            field_key = str(row.get("key", "")).lower()
        else:
            label = str(row[0] if row else "").lower()
            field_key = ""
        if field_key == "wifi_password":
            return True
        if field_key == "duong_dan_public_key":
            return True
        if "public key" in label:
            return True
        return "mật khẩu" in label and "wi" in label

    def _build_config_detail_section(self, parent, title, rows, grid_column=None):
        rows = [row for row in rows if not self._is_hidden_config_row(row)]
        shell = tk.Frame(
            parent,
            bg=_THEME["border"],
            highlightthickness=0,
        )
        if grid_column is None:
            shell.pack(fill=tk.X, pady=(0, 12))
        else:
            shell.grid(
                row=0,
                column=grid_column,
                sticky="new",
                padx=(0, 8) if grid_column == 0 else (8, 0),
            )
            parent.columnconfigure(grid_column, weight=1, uniform="config_cols")

        inner = tk.Frame(shell, bg=_THEME["surface"])
        inner.pack(fill=tk.X, padx=1, pady=1)

        head = tk.Frame(inner, bg=_THEME["primary_soft"])
        head.pack(fill=tk.X)
        tk.Frame(head, bg=_THEME["primary"], width=4).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(
            head,
            text=title,
            font=(self._font_ui[0], 11, "bold"),
            bg=_THEME["primary_soft"],
            fg=_THEME["primary"],
            anchor=tk.W,
            padx=10,
            pady=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        body = tk.Frame(inner, bg=_THEME["surface"])
        body.pack(fill=tk.X, padx=12, pady=(4, 12))
        body.columnconfigure(1, weight=1)

        value_wrap = 240 if grid_column is not None else 420
        for row_index, row in enumerate(rows):
            if isinstance(row, dict):
                label = row["label"]
                value = row.get("value")
                entry_minutes = row.get("entry_minutes")
                entry_var = row.get("entry")
            else:
                label, value = row
                entry_minutes = None
                entry_var = None

            tk.Label(
                body,
                text=label,
                font=self._font_ui,
                bg=_THEME["surface"],
                fg=_THEME["text_muted"],
                anchor=tk.W,
            ).grid(row=row_index, column=0, sticky=tk.NW, padx=(0, 12), pady=5)

            if entry_minutes is not None:
                field = tk.Frame(body, bg=_THEME["surface"])
                field.grid(row=row_index, column=1, sticky=tk.W, pady=5)
                ttk.Entry(
                    field,
                    textvariable=entry_minutes,
                    width=10,
                    font=self._font_mono,
                ).pack(side=tk.LEFT)
                tk.Label(
                    field,
                    text=_T("minutes_unit"),
                    font=self._font_ui,
                    bg=_THEME["surface"],
                    fg=_THEME["text_muted"],
                ).pack(side=tk.LEFT, padx=(8, 0))
            elif entry_var is not None:
                ttk.Entry(
                    body,
                    textvariable=entry_var,
                    font=self._font_mono,
                ).grid(row=row_index, column=1, sticky=tk.EW, pady=5)
            else:
                tk.Label(
                    body,
                    text=value,
                    font=self._font_mono,
                    bg=_THEME["surface"],
                    fg=_THEME["text"],
                    anchor=tk.W,
                    justify=tk.LEFT,
                    wraplength=value_wrap,
                ).grid(row=row_index, column=1, sticky=tk.EW, pady=5)

    def _show_device_config_dialog(self, device_ip, data, port=None):
        if not data.get("ok"):
            messagebox.showerror(
                "Lỗi cấu hình",
                data.get("error") or data.get("message") or "Thiết bị trả về lỗi.",
            )
            return

        config = data.get("config") or {}
        identity = config.get("dinh_danh") or {}
        recording = config.get("cau_hinh_ghi_am") or {}
        self._cache_device_name_from_config(device_ip, data)
        display_id = self._device_connection_display(device_ip)

        dialog = tk.Toplevel(self)
        dialog.title(f"Cấu hình thiết bị — {display_id}")
        dialog.minsize(660, 460)
        dialog.transient(self)
        dialog.grab_set()
        dialog.protocol(
            "WM_DELETE_WINDOW",
            lambda: (dialog.grab_release(), dialog.destroy()),
        )
        dialog.configure(bg=_THEME["bg"])
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=0)

        header = tk.Frame(dialog, bg=_THEME["header"])
        header.grid(row=0, column=0, sticky=tk.EW)
        header.columnconfigure(0, weight=1)
        header_inner = tk.Frame(header, bg=_THEME["header"])
        header_inner.grid(row=0, column=0, sticky=tk.EW, padx=18, pady=14)
        header_inner.columnconfigure(1, weight=1)

        tk.Label(
            header_inner,
            text=_T("device_config_heading"),
            font=(self._font_ui[0], 15, "bold"),
            bg=_THEME["header"],
            fg="#ffffff",
            anchor=tk.W,
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W)

        tk.Label(
            header_inner,
            text=_T("device_name_label"),
            font=self._font_mono_sm,
            bg=_THEME["header_accent"],
            fg="#e3f2fd",
            padx=8,
            pady=2,
        ).grid(row=1, column=0, sticky=tk.W, pady=(12, 0))
        tk.Label(
            header_inner,
            text=display_id,
            font=self._font_ui,
            bg=_THEME["header"],
            fg="#ffffff",
            anchor=tk.W,
        ).grid(row=1, column=1, sticky=tk.W, padx=(12, 0), pady=(12, 0))

        updated_at_var = tk.StringVar(
            value=(
                f"{_T('last_updated_prefix')}{data.get('updated_at')}"
                if data.get("updated_at")
                else ""
            )
        )
        if data.get("updated_at"):
            tk.Label(
                header_inner,
                textvariable=updated_at_var,
                font=self._font_ui,
                bg=_THEME["header"],
                fg="#b8d4f0",
                anchor=tk.W,
            ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))

        mac_address = (data.get("mac_address") or "").strip()
        if mac_address:
            tk.Label(
                header_inner,
                text=f"MAC: {mac_address}",
                font=self._font_mono_sm,
                bg=_THEME["header"],
                fg="#b8d4f0",
                anchor=tk.W,
            ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))

        form_refs = {
            "ma_id_var": None,
            "ho_ten_var": None,
            "nam_sinh_var": None,
            "dia_chi_var": None,
            "ngay_cap_var": None,
            "ten_thiet_bi_var": None,
            "id_thiet_bi_var": None,
            "dia_chi_thiet_bi_var": None,
            "kieu_ghi_am_var": None,
            "duration_var": None,
            "scan_var": None,
            "hash_upload_var": None,
            "vad_nguong_var": None,
            "vad_timeout_var": None,
            "vad_max_var": None,
            "chu_ky_ghi_am_var": None,
            "bat_dau_ghi_am_var": None,
            "ket_thuc_ghi_am_var": None,
            "updated_at_var": updated_at_var,
        }

        content = tk.Frame(dialog, bg=_THEME["bg"])
        content.grid(row=1, column=0, sticky="new", padx=14, pady=14)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)

        ma_id_var = tk.StringVar(value=self._identity_field_initial(identity.get("ma_id")))
        ho_ten_var = tk.StringVar(value=self._identity_field_initial(identity.get("ho_ten")))
        nam_sinh_var = tk.StringVar(value=self._identity_field_initial(identity.get("nam_sinh")))
        dia_chi_var = tk.StringVar(value=self._identity_field_initial(identity.get("dia_chi")))
        ngay_cap_var = tk.StringVar(
            value=self._identity_field_initial(identity.get("ngay_cap_dinh_danh"))
        )
        ten_thiet_bi_var = tk.StringVar(value=self._identity_field_initial(identity.get("ten_thiet_bi")))
        id_thiet_bi_var = tk.StringVar(value=self._identity_field_initial(identity.get("id_thiet_bi")))
        dia_chi_thiet_bi_var = tk.StringVar(value=self._identity_field_initial(identity.get("dia_chi_thiet_bi")))

        form_refs["ma_id_var"] = ma_id_var
        form_refs["ho_ten_var"] = ho_ten_var
        form_refs["nam_sinh_var"] = nam_sinh_var
        form_refs["dia_chi_var"] = dia_chi_var
        form_refs["ngay_cap_var"] = ngay_cap_var
        form_refs["ten_thiet_bi_var"] = ten_thiet_bi_var
        form_refs["id_thiet_bi_var"] = id_thiet_bi_var
        form_refs["dia_chi_thiet_bi_var"] = dia_chi_thiet_bi_var

        identity_rows = [
            {"label": _T("id_code"), "entry": ma_id_var},
            {"label": _T("full_name"), "entry": ho_ten_var},
            {"label": _T("birth_year"), "entry": nam_sinh_var},
            {"label": _T("address"), "entry": dia_chi_var},
            {"label": _T("issue_date"), "entry": ngay_cap_var},
            {"label": _T("device_name_field"), "entry": ten_thiet_bi_var},
            {"label": _T("device_id_field"), "entry": id_thiet_bi_var},
            {"label": _T("device_address_field"), "entry": dia_chi_thiet_bi_var},
        ]

        kieu_ghi_am_var = tk.StringVar(
            value=self._format_recording_mode(recording.get("kieu_ghi_am", "continuous"))
        )
        duration_var = tk.StringVar(
            value=self._minutes_field_initial(recording.get("thoi_luong_ghi_am_phut"))
        )
        scan_var = tk.StringVar(
            value=self._minutes_field_initial(recording.get("chu_ky_quet_wifi_phut"))
        )
        hash_upload_var = tk.StringVar(
            value=self._identity_field_initial(recording.get("ssid_upload"))
        )
        vad_nguong_var = tk.StringVar(value=str(recording.get("vad_nguong_dbfs", -41.0)))
        vad_timeout_var = tk.StringVar(value=str(recording.get("vad_timeout_im_lang_giay", 60)))
        vad_max_var = tk.StringVar(value=str(recording.get("vad_max_thoi_gian_giay", 600)))
        chu_ky_ghi_am_var = tk.StringVar(
            value=self._minutes_field_initial(recording.get("chu_ky_ghi_am_phut"))
        )
        bat_dau_ghi_am_var = tk.StringVar(
            value=str(recording.get("bat_dau_ghi_am") or "")
        )
        ket_thuc_ghi_am_var = tk.StringVar(
            value=str(recording.get("ket_thuc_ghi_am") or "")
        )

        form_refs["kieu_ghi_am_var"] = kieu_ghi_am_var
        form_refs["duration_var"] = duration_var
        form_refs["scan_var"] = scan_var
        form_refs["hash_upload_var"] = hash_upload_var
        form_refs["vad_nguong_var"] = vad_nguong_var
        form_refs["vad_timeout_var"] = vad_timeout_var
        form_refs["vad_max_var"] = vad_max_var
        form_refs["chu_ky_ghi_am_var"] = chu_ky_ghi_am_var
        form_refs["bat_dau_ghi_am_var"] = bat_dau_ghi_am_var
        form_refs["ket_thuc_ghi_am_var"] = ket_thuc_ghi_am_var

        self._build_config_detail_section(
            content,
            _T("identity_section"),
            identity_rows,
            grid_column=0,
        )

        rec_shell = tk.Frame(
            content, bg=_THEME["border"], highlightthickness=0,
        )
        rec_shell.grid(row=0, column=1, sticky="new", padx=(8, 0))

        rec_inner = tk.Frame(rec_shell, bg=_THEME["surface"])
        rec_inner.pack(fill=tk.X, padx=1, pady=1)

        rec_head = tk.Frame(rec_inner, bg=_THEME["primary_soft"])
        rec_head.pack(fill=tk.X)
        tk.Frame(rec_head, bg=_THEME["primary"], width=4).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(
            rec_head, text=_T("recording_config_section"),
            font=(self._font_ui[0], 11, "bold"),
            bg=_THEME["primary_soft"], fg=_THEME["primary"],
            anchor=tk.W, padx=12, pady=10,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        rec_body = tk.Frame(rec_inner, bg=_THEME["surface"])
        rec_body.pack(fill=tk.X, padx=12, pady=(4, 12))
        rec_body.columnconfigure(1, weight=1)

        row_i = 0
        tk.Label(rec_body, text=_T("recording_mode"), font=self._font_ui,
                 bg=_THEME["surface"], fg=_THEME["text_muted"], anchor=tk.W,
                 ).grid(row=row_i, column=0, sticky=tk.NW, padx=(0, 12), pady=5)
        mode_combo = ttk.Combobox(
            rec_body,
            textvariable=kieu_ghi_am_var,
            values=[
                self._RECORDING_MODE_LABELS["continuous"],
                self._RECORDING_MODE_LABELS["vad"],
                self._RECORDING_MODE_LABELS["interval"],
                self._RECORDING_MODE_LABELS["scheduled"],
            ],
            state="readonly",
            width=18,
            font=self._font_ui,
        )
        mode_combo.grid(row=row_i, column=1, sticky=tk.W, pady=5)

        row_i += 1
        tk.Label(rec_body, text=_T("recording_duration"), font=self._font_ui,
                 bg=_THEME["surface"], fg=_THEME["text_muted"], anchor=tk.W,
                 ).grid(row=row_i, column=0, sticky=tk.NW, padx=(0, 12), pady=5)
        dur_frame = tk.Frame(rec_body, bg=_THEME["surface"])
        dur_frame.grid(row=row_i, column=1, sticky=tk.W, pady=5)
        ttk.Entry(dur_frame, textvariable=duration_var, width=8, font=self._font_mono).pack(side=tk.LEFT)
        tk.Label(dur_frame, text=_T("minutes_unit"), font=self._font_ui, bg=_THEME["surface"], fg=_THEME["text_muted"]).pack(side=tk.LEFT, padx=(8, 0))

        row_i += 1
        tk.Label(rec_body, text=_T("scan_cycle"), font=self._font_ui,
                 bg=_THEME["surface"], fg=_THEME["text_muted"], anchor=tk.W,
                 ).grid(row=row_i, column=0, sticky=tk.NW, padx=(0, 12), pady=5)
        scan_frame = tk.Frame(rec_body, bg=_THEME["surface"])
        scan_frame.grid(row=row_i, column=1, sticky=tk.W, pady=5)
        ttk.Entry(scan_frame, textvariable=scan_var, width=8, font=self._font_mono).pack(side=tk.LEFT)
        tk.Label(scan_frame, text=_T("minutes_unit"), font=self._font_ui, bg=_THEME["surface"], fg=_THEME["text_muted"]).pack(side=tk.LEFT, padx=(8, 0))

        vad_widgets = []

        row_i += 1
        lbl_vn = tk.Label(rec_body, text=_T("vad_threshold"), font=self._font_ui,
                          bg=_THEME["surface"], fg=_THEME["text_muted"], anchor=tk.W)
        lbl_vn.grid(row=row_i, column=0, sticky=tk.NW, padx=(0, 12), pady=5)
        ent_vn = ttk.Entry(rec_body, textvariable=vad_nguong_var, width=10, font=self._font_mono)
        ent_vn.grid(row=row_i, column=1, sticky=tk.W, pady=5)
        vad_widgets.extend([lbl_vn, ent_vn])

        row_i += 1
        lbl_vt = tk.Label(rec_body, text=_T("vad_silence_timeout"), font=self._font_ui,
                          bg=_THEME["surface"], fg=_THEME["text_muted"], anchor=tk.W)
        lbl_vt.grid(row=row_i, column=0, sticky=tk.NW, padx=(0, 12), pady=5)
        vt_frame = tk.Frame(rec_body, bg=_THEME["surface"])
        vt_frame.grid(row=row_i, column=1, sticky=tk.W, pady=5)
        ttk.Entry(vt_frame, textvariable=vad_timeout_var, width=8, font=self._font_mono).pack(side=tk.LEFT)
        tk.Label(vt_frame, text=_T("seconds_unit"), font=self._font_ui, bg=_THEME["surface"], fg=_THEME["text_muted"]).pack(side=tk.LEFT, padx=(8, 0))
        vad_widgets.extend([lbl_vt, vt_frame])

        row_i += 1
        lbl_vm = tk.Label(rec_body, text=_T("vad_max_duration"), font=self._font_ui,
                          bg=_THEME["surface"], fg=_THEME["text_muted"], anchor=tk.W)
        lbl_vm.grid(row=row_i, column=0, sticky=tk.NW, padx=(0, 12), pady=5)
        vm_frame = tk.Frame(rec_body, bg=_THEME["surface"])
        vm_frame.grid(row=row_i, column=1, sticky=tk.W, pady=5)
        ttk.Entry(vm_frame, textvariable=vad_max_var, width=8, font=self._font_mono).pack(side=tk.LEFT)
        tk.Label(vm_frame, text=_T("seconds_unit"), font=self._font_ui, bg=_THEME["surface"], fg=_THEME["text_muted"]).pack(side=tk.LEFT, padx=(8, 0))
        vad_widgets.extend([lbl_vm, vm_frame])

        interval_widgets = []

        row_i += 1
        lbl_ck = tk.Label(rec_body, text=_T("interval_cycle"), font=self._font_ui,
                          bg=_THEME["surface"], fg=_THEME["text_muted"], anchor=tk.W)
        lbl_ck.grid(row=row_i, column=0, sticky=tk.NW, padx=(0, 12), pady=5)
        ck_frame = tk.Frame(rec_body, bg=_THEME["surface"])
        ck_frame.grid(row=row_i, column=1, sticky=tk.W, pady=5)
        ttk.Entry(ck_frame, textvariable=chu_ky_ghi_am_var, width=8, font=self._font_mono).pack(side=tk.LEFT)
        tk.Label(ck_frame, text=_T("minutes_unit"), font=self._font_ui, bg=_THEME["surface"], fg=_THEME["text_muted"]).pack(side=tk.LEFT, padx=(8, 0))
        interval_widgets.extend([lbl_ck, ck_frame])

        scheduled_widgets = []

        row_i += 1
        lbl_bd = tk.Label(rec_body, text=_T("start_rec"), font=self._font_ui,
                          bg=_THEME["surface"], fg=_THEME["text_muted"], anchor=tk.W)
        lbl_bd.grid(row=row_i, column=0, sticky=tk.NW, padx=(0, 12), pady=5)
        ent_bd = ttk.Entry(rec_body, textvariable=bat_dau_ghi_am_var, width=18, font=self._font_mono)
        ent_bd.grid(row=row_i, column=1, sticky=tk.W, pady=5)
        scheduled_widgets.extend([lbl_bd, ent_bd])

        row_i += 1
        lbl_kt = tk.Label(rec_body, text=_T("stop_rec"), font=self._font_ui,
                          bg=_THEME["surface"], fg=_THEME["text_muted"], anchor=tk.W)
        lbl_kt.grid(row=row_i, column=0, sticky=tk.NW, padx=(0, 12), pady=5)
        ent_kt = ttk.Entry(rec_body, textvariable=ket_thuc_ghi_am_var, width=18, font=self._font_mono)
        ent_kt.grid(row=row_i, column=1, sticky=tk.W, pady=5)
        scheduled_widgets.extend([lbl_kt, ent_kt])

        def show_hide_vad(*_args):
            mode = self._recording_mode_api_value(kieu_ghi_am_var.get())
            for w in vad_widgets:
                try:
                    if mode == "vad":
                        w.grid()
                    else:
                        w.grid_remove()
                except Exception:
                    pass
            for w in interval_widgets:
                try:
                    if mode == "interval":
                        w.grid()
                    else:
                        w.grid_remove()
                except Exception:
                    pass
            for w in scheduled_widgets:
                try:
                    if mode == "scheduled":
                        w.grid()
                    else:
                        w.grid_remove()
                except Exception:
                    pass

        if self._recording_mode_api_value(kieu_ghi_am_var.get()) != "vad":
            for w in vad_widgets:
                w.grid_remove()
        if self._recording_mode_api_value(kieu_ghi_am_var.get()) != "interval":
            for w in interval_widgets:
                w.grid_remove()
        if self._recording_mode_api_value(kieu_ghi_am_var.get()) != "scheduled":
            for w in scheduled_widgets:
                w.grid_remove()

        kieu_ghi_am_var.trace_add("write", show_hide_vad)

        footer = tk.Frame(dialog, bg=_THEME["surface"])
        footer.grid(row=2, column=0, sticky=tk.EW)
        tk.Frame(footer, bg=_THEME["border"], height=1).pack(fill=tk.X)
        actions = tk.Frame(footer, bg=_THEME["surface"])
        actions.pack(pady=10)
        self._shadow_button(
            actions,
            "Primary.TButton",
            "Update",
            lambda: self._update_device_config(
                device_ip,
                dialog,
                identity,
                recording,
                form_refs,
                port=port,
            ),
            side=tk.LEFT,
            padx=(0, 8),
        )
        self._shadow_button(
            actions,
            "Secondary.TButton",
            _T("close_btn"),
            lambda: (dialog.grab_release(), dialog.destroy()),
            side=tk.LEFT,
            padx=(0, 0),
        )

        dialog.update_idletasks()
        dialog_width = 720
        dialog_height = min(max(dialog.winfo_reqheight() + 12, 500), 640)
        self._finalize_toplevel(dialog, dialog_width, dialog_height)

    def _apply_device_config_to_form(self, data, form_refs):
        config = data.get("config") or {}
        identity = config.get("dinh_danh") or {}
        recording = config.get("cau_hinh_ghi_am") or {}
        field_map = (
            ("ma_id_var", self._identity_field_initial(identity.get("ma_id"))),
            ("ho_ten_var", self._identity_field_initial(identity.get("ho_ten"))),
            ("nam_sinh_var", self._identity_field_initial(identity.get("nam_sinh"))),
            ("dia_chi_var", self._identity_field_initial(identity.get("dia_chi"))),
            ("ngay_cap_var", self._identity_field_initial(identity.get("ngay_cap_dinh_danh"))),
            ("ten_thiet_bi_var", self._identity_field_initial(identity.get("ten_thiet_bi"))),
            ("id_thiet_bi_var", self._identity_field_initial(identity.get("id_thiet_bi"))),
            ("dia_chi_thiet_bi_var", self._identity_field_initial(identity.get("dia_chi_thiet_bi"))),
            (
                "kieu_ghi_am_var",
                self._format_recording_mode(recording.get("kieu_ghi_am", "continuous")),
            ),
            ("duration_var", self._minutes_field_initial(recording.get("thoi_luong_ghi_am_phut"))),
            ("scan_var", self._minutes_field_initial(recording.get("chu_ky_quet_wifi_phut"))),
            ("hash_upload_var", self._identity_field_initial(recording.get("ssid_upload"))),
            ("vad_nguong_var", str(recording.get("vad_nguong_dbfs", -41.0))),
            ("vad_timeout_var", str(recording.get("vad_timeout_im_lang_giay", 60))),
            ("vad_max_var", str(recording.get("vad_max_thoi_gian_giay", 600))),
            ("chu_ky_ghi_am_var", self._minutes_field_initial(recording.get("chu_ky_ghi_am_phut"))),
            ("bat_dau_ghi_am_var", str(recording.get("bat_dau_ghi_am") or "")),
            ("ket_thuc_ghi_am_var", str(recording.get("ket_thuc_ghi_am") or "")),
        )
        for key, value in field_map:
            var = form_refs.get(key)
            if var is not None:
                var.set(value)
        updated_at = data.get("updated_at")
        updated_at_var = form_refs.get("updated_at_var")
        if updated_at and updated_at_var is not None:
            updated_at_var.set(f"{_T('last_updated_prefix')}{updated_at}")

    def _sync_device_config_form(self, device_ip, form_refs, dialog=None, port=None):
        config_url = self._device_service_url(device_ip, "/api/config", port=port)

        def task():
            r = self._http_get(
                config_url,
                headers=self._headers(),
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                raise ValueError(
                    data.get("error") or data.get("message") or "invalid response"
                )

            def update_ui():
                self._apply_device_config_to_form(data, form_refs)
                self._cache_device_name_from_config(device_ip, data)
                self._auto_register_device_from_config(device_ip, data)
                self.refresh_device_connections()
                if dialog is not None:
                    self._set_status("Đã đồng bộ cấu hình từ thiết bị.")

            self.after(0, update_ui)

        self._run_async(
            "Đang đồng bộ cấu hình...",
            task,
            failure_text=_T("config_sync_failed"),
            affects_connection=False,
        )

    def _update_device_config(
        self,
        device_ip,
        dialog,
        identity,
        recording,
        form_refs,
        port=None,
    ):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"), parent=dialog)
            return
        try:
            ma_id = self._parse_required_text(
                form_refs["ma_id_var"].get(),
                "Mã định danh",
            )
            ho_ten = self._parse_required_text(
                form_refs["ho_ten_var"].get(),
                "Họ và tên",
            )
            nam_sinh = self._parse_birth_year(form_refs["nam_sinh_var"].get())
            dia_chi = self._parse_required_text(
                form_refs["dia_chi_var"].get(),
                "Địa chỉ",
            )
            ngay_cap = self._parse_required_text(
                form_refs["ngay_cap_var"].get(),
                "Ngày cấp định danh",
            )
            ten_thiet_bi = form_refs["ten_thiet_bi_var"].get().strip()
            id_thiet_bi = form_refs["id_thiet_bi_var"].get().strip()
            dia_chi_thiet_bi = form_refs["dia_chi_thiet_bi_var"].get().strip()
            kieu_ghi_am = self._recording_mode_api_value(
                form_refs["kieu_ghi_am_var"].get()
            )
            duration = self._parse_minutes_field(
                form_refs["duration_var"].get(),
                "Thời lượng ghi âm",
            )
            scan_cycle = self._parse_minutes_field(
                form_refs["scan_var"].get(),
                "Chu kỳ quét",
            )
            hash_upload = (
                form_refs["hash_upload_var"].get().strip()
                or str((recording or {}).get("ssid_upload") or "").strip()
            )
            vad_nguong = float(form_refs["vad_nguong_var"].get())
            vad_timeout = int(form_refs["vad_timeout_var"].get())
            vad_max = int(form_refs["vad_max_var"].get())
            chu_ky_ghi_am = form_refs["chu_ky_ghi_am_var"].get().strip()
            bat_dau_ghi_am = form_refs["bat_dau_ghi_am_var"].get().strip()
            ket_thuc_ghi_am = form_refs["ket_thuc_ghi_am_var"].get().strip()
        except ValueError as exc:
            messagebox.showerror(_T("invalid_value_title"), str(exc), parent=dialog)
            return

        identity_payload = dict(identity) if identity else {}
        identity_payload["ma_id"] = ma_id
        identity_payload["ho_ten"] = ho_ten
        identity_payload["nam_sinh"] = nam_sinh
        identity_payload["dia_chi"] = dia_chi
        identity_payload["ngay_cap_dinh_danh"] = ngay_cap
        identity_payload["ten_thiet_bi"] = ten_thiet_bi
        identity_payload["id_thiet_bi"] = id_thiet_bi
        identity_payload["dia_chi_thiet_bi"] = dia_chi_thiet_bi

        recording_payload = dict(recording) if recording else {}
        recording_payload["kieu_ghi_am"] = kieu_ghi_am
        recording_payload["thoi_luong_ghi_am_phut"] = duration
        recording_payload["chu_ky_quet_wifi_phut"] = scan_cycle
        recording_payload["ssid_upload"] = hash_upload
        recording_payload["vad_nguong_dbfs"] = vad_nguong
        recording_payload["vad_timeout_im_lang_giay"] = vad_timeout
        recording_payload["vad_max_thoi_gian_giay"] = vad_max
        if kieu_ghi_am == "interval" and chu_ky_ghi_am:
            recording_payload["chu_ky_ghi_am_phut"] = int(chu_ky_ghi_am)
        if kieu_ghi_am == "scheduled":
            if bat_dau_ghi_am:
                recording_payload["bat_dau_ghi_am"] = bat_dau_ghi_am
            if ket_thuc_ghi_am:
                recording_payload["ket_thuc_ghi_am"] = ket_thuc_ghi_am
        payload = {
            "dinh_danh": identity_payload,
            "cau_hinh_ghi_am": recording_payload,
        }
        config_url = self._device_service_url(device_ip, "/api/config", port=port)
        display_id = self._device_connection_display(device_ip)

        def task():
            r = self._http_post(
                config_url,
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            r.raise_for_status()
            result = r.json()

            def update_ui():
                if not result.get("ok"):
                    messagebox.showerror(
                        "Update thất bại",
                        result.get("error")
                        or result.get("message")
                        or "Thiết bị trả về lỗi.",
                        parent=dialog,
                    )
                    return
                messagebox.showinfo(
                    "Update thành công",
                    result.get("message")
                    or "Thiết bị đang khởi động lại dịch vụ...",
                    parent=dialog,
                )
                if ten_thiet_bi:
                    self._store_device_name(device_ip, ten_thiet_bi)
                self.refresh_device_connections()
                self._set_status(
                    f"Đã update cấu hình thiết bị {self._device_connection_display(device_ip)}."
                )
                self.after(
                    3000,
                    lambda: self._sync_device_config_form(
                        device_ip,
                        form_refs,
                        dialog,
                        port=port,
                    ),
                )

            self.after(0, update_ui)

        self._run_async(
            f"Đang update cấu hình {display_id}...",
            task,
            failure_text=f"Update cấu hình {display_id} thất bại.",
            affects_connection=False,
        )

    def _load_header_logo(self, path, height=80):
        try:
            from PIL import Image, ImageOps, ImageTk
            img = Image.open(path).convert("RGBA")
            ratio = height / img.height
            new_w = max(1, int(img.width * ratio))
            img = img.resize((new_w, height), Image.LANCZOS)

            # Lấy độ sáng → invert → làm alpha (logo đen=opaque, nền trắng=transparent)
            brightness = img.convert("RGB").convert("L")
            alpha = ImageOps.invert(brightness)

            # Logo trắng với alpha từ bước trên
            white = Image.new("RGBA", img.size, (255, 255, 255, 255))
            white.putalpha(alpha)

            # Dán lên nền header
            bg_hex = _THEME["header"].lstrip("#")
            bg_rgb = tuple(int(bg_hex[i:i+2], 16) for i in (0, 2, 4))
            bg = Image.new("RGBA", img.size, bg_rgb + (255,))
            bg.paste(white, mask=white.split()[3])

            return ImageTk.PhotoImage(bg.convert("RGB"))
        except Exception:
            return None

    def _build_header(self, parent):
        wrap = tk.Frame(parent, bg=_THEME["bg"])
        wrap.pack(fill=tk.X)

        header_host = tk.Frame(wrap, bg=_THEME["bg"])
        header_host.pack(fill=tk.X, padx=(2, 10), pady=(2, 0))

        header_shadow = tk.Frame(header_host, bg=_THEME["shadow_2"])
        header_shadow.pack(fill=tk.X, padx=(5, 0), pady=(5, 0))

        header = tk.Frame(header_shadow, bg=_THEME["header"], height=104)
        header.pack(fill=tk.X, padx=(0, 5), pady=(0, 5))
        header.pack_propagate(False)

        shine = tk.Frame(header, bg=_THEME["header_glow"], height=2)
        shine.pack(fill=tk.X, side=tk.TOP)

        body = tk.Frame(header, bg=_THEME["header"])
        body.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(body, bg=_THEME["header"])
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(22, 0), pady=12)

        titles = tk.Frame(left, bg=_THEME["header"])
        titles.pack(side=tk.LEFT)
        self._header_logo_img = self._load_header_logo(
            str(Path(__file__).parent / "logo.png"),
            height=78,
        )
        if self._header_logo_img is not None:
            tk.Label(
                titles,
                image=self._header_logo_img,
                bg=_THEME["header"],
                bd=0,
            ).pack(side=tk.LEFT, anchor=tk.W)
        tk.Label(
            titles,
            text="PHANTOM",
            font=("Inter", 28, "bold"),
            bg=_THEME["header"],
            fg="#ffffff",
        ).pack(side=tk.LEFT, anchor=tk.W, padx=(12, 0))

        right = tk.Frame(body, bg=_THEME["header"])
        right.pack(side=tk.RIGHT, padx=22, pady=12)

        lang_col = tk.Frame(right, bg=_THEME["header"])
        lang_col.pack(side=tk.RIGHT, padx=(0, 12))
        self._lang_btn = self._pill_button_canvas(
            lang_col, _T("lang_toggle_to_en"), "#2a4a6e", "#ffffff", "#3a6a9e",
            "#1a3a5e", "#60a5fa", self._font_ui, self._toggle_language,
        )
        self._lang_btn.configure(bg=_THEME["header"])
        self._lang_btn.pack()

        status_col = tk.Frame(right, bg=_THEME["header"])
        status_col.pack(side=tk.RIGHT)
        self._header_status_label = tk.Label(
            status_col,
            text=_T("header_status_label"),
            font=self._font_sub,
            bg=_THEME["header"],
            fg="#8ec5ff",
        )
        self._header_status_label.pack(anchor=tk.E)
        badge_shell = tk.Frame(status_col, bg=_THEME["header"])
        badge_shell.pack(anchor=tk.E, pady=(6, 0))
        badge_face = tk.Frame(badge_shell, bg=_THEME["danger_bg"], highlightthickness=1, highlightbackground=_THEME["danger"])
        badge_face.pack()
        self._conn_badge = tk.Label(
            badge_face,
            text=" OFFLINE ",
            font=self._font_ui_bold,
            bg=_THEME["danger_bg"],
            fg=_THEME["danger"],
            padx=14,
            pady=4,
        )
        self._conn_badge.pack()
        self._conn_badge_shell = badge_face
        self._pulse_step = 0
        self._pulse_job = None

        logout_col = tk.Frame(right, bg=_THEME["header"])
        logout_col.pack(side=tk.RIGHT, padx=(0, 16))
        self._logout_button = self._pill_button_canvas(
            logout_col, _T("logout"), "#475569", "#ffffff", "#94a3b8", "#334155", "#60a5fa", self._font_ui, self._logout
        )
        self._logout_button.configure(bg=_THEME["header"])
        self._logout_button.pack()
        self._logout_button.pack_forget()

        drop = tk.Frame(wrap, bg=_THEME["bg"], height=10)
        drop.pack(fill=tk.X)
        for color in (_THEME["shadow_2"], _THEME["shadow_4"], _THEME["shadow_5"], _THEME["bg"]):
            tk.Frame(drop, bg=color, height=2).pack(fill=tk.X)

    def _bind_body_scroll(self, canvas):
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", on_mousewheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

    def _build_ui(self):
        self._build_header(self._main_host)

        # ── shared vars ──────────────────────────────────────────────────────
        self.hotspot_status_var = tk.StringVar(value=_T("node_inactive"))
        self.hotspot_ssid_var   = tk.StringVar(value="-")
        self.network_wifi_var   = tk.StringVar(value=_T("wifi_adapter_prefix") + "-")
        self.network_host_var   = tk.StringVar(value="-")
        self.network_device_var = tk.StringVar(value="-")
        self.network_api_var    = tk.StringVar(value="-")
        self.safe_info_var      = tk.StringVar(value=_T("not_connected_info"))
        self.status_var         = tk.StringVar()
        self.connection_var     = tk.StringVar(value=_T("not_connected_var"))
        self.device_tree        = None

        body = tk.Frame(self._main_host, bg=_THEME["bg"])
        body.pack(fill=tk.BOTH, expand=True)

        # ── Left sidebar ─────────────────────────────────────────────────────
        sidebar_wrap = tk.Frame(body, bg=_THEME["bg"], width=292)
        sidebar_wrap.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0), pady=(8, 0))
        sidebar_wrap.pack_propagate(False)

        sb_canvas = tk.Canvas(sidebar_wrap, bg=_THEME["bg"], highlightthickness=0, bd=0)
        sb_scroll = ttk.Scrollbar(sidebar_wrap, orient=tk.VERTICAL, command=sb_canvas.yview)
        sb_canvas.configure(yscrollcommand=sb_scroll.set)
        sb_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        sb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sidebar = tk.Frame(sb_canvas, bg=_THEME["bg"])
        _sb_win = sb_canvas.create_window((0, 0), window=sidebar, anchor="nw")

        def _sb_content_resize(_e):
            sb_canvas.configure(scrollregion=sb_canvas.bbox("all"))

        def _sb_canvas_resize(e):
            sb_canvas.itemconfigure(_sb_win, width=e.width)

        sidebar.bind("<Configure>", _sb_content_resize)
        sb_canvas.bind("<Configure>", _sb_canvas_resize)
        self._bind_body_scroll(sb_canvas)

        # — device connections section —
        conn_section = self._sidebar_section(sidebar, _T("connected_devices"), pady=(0, 0))
        self._conn_section_title_lbl = conn_section["title_lbl"]

        self._conn_count_badge_var = tk.StringVar(value="0")
        tk.Label(
            conn_section["title_row"],
            textvariable=self._conn_count_badge_var,
            font=self._font_sub,
            bg=_THEME["primary_soft"],
            fg=_THEME["primary"],
            padx=6, pady=1,
        ).pack(side=tk.LEFT, padx=(6, 0))

        # subtitle
        self._device_list_subtitle_lbl = tk.Label(
            conn_section["head_row"],
            text=_T("device_list_subtitle"),
            font=self._font_sub,
            bg=_THEME["surface"],
            fg=_THEME["text_muted"],
            anchor=tk.W,
        )
        self._device_list_subtitle_lbl.pack(side=tk.LEFT)

        self._conn_sub_var = tk.StringVar(value=f"{_T('conn_count_badge_sub')} (0)")
        self._build_device_connection_items(conn_section["body"])

        # — decrypt button —
        decrypt_btn_frame = tk.Frame(sidebar, bg=_THEME["bg"], pady=4)
        decrypt_btn_frame.pack(fill=tk.X, padx=4)
        self._decrypt_btn = tk.Button(
            decrypt_btn_frame,
            text=_T("decrypt_bin_btn"),
            font=self._font_ui_bold,
            bg=_THEME["primary"], fg="#ffffff",
            activebackground=_THEME["primary_hover"], activeforeground="#ffffff",
            relief="flat", bd=0, cursor="hand2", pady=7,
            command=self._open_decrypt_window,
        )
        self._decrypt_btn.pack(fill=tk.X)

        self._reg_panel = None
        self.device_tree = None

        # ── Right main area ──────────────────────────────────────────────────
        right_wrap = tk.Frame(body, bg=_THEME["bg"])
        right_wrap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 8), pady=(8, 0))

        # — audio player —
        if AudioPlayerWidget is not None:
            self._audio_player = AudioPlayerWidget(
                right_wrap,
                _THEME,
                self._font_ui,
                self._font_sub,
                self._font_mono_sm,
                self._shadow_shell,
                self._shadow_button,
                self._card,
                self._glow_panel,
                on_filter_change=self._on_audio_filter_change,
            )
        else:
            self._audio_player = None

        file_card_pady = (14, 0) if AudioPlayerWidget is not None else (0, 0)
        _files_surface = self._shadow_shell(right_wrap, pady=file_card_pady, expand=True)
        head = tk.Frame(_files_surface, bg=_THEME["surface"])
        head.pack(fill=tk.X, padx=18, pady=(16, 0))
        tk.Frame(head, bg=_THEME["primary"], width=4, height=20).pack(side=tk.LEFT, padx=(0, 12))
        self._recordings_title_lbl = tk.Label(head, text=_T("recordings_title"), font=self._font_section, bg=_THEME["surface"], fg=_THEME["primary"])
        self._recordings_title_lbl.pack(side=tk.LEFT)
        self._refresh_files_btn = self._shadow_button(head, "Secondary.TButton", _T("refresh_btn"), self._refresh_local_files_tree, side=tk.RIGHT, padx=(0, 0))
        tk.Frame(_files_surface, bg=_THEME["border"], height=1).pack(fill=tk.X, padx=18, pady=(12, 0))
        files_inner = ttk.Frame(_files_surface, style="Card.TFrame")
        files_inner.pack(fill=tk.BOTH, expand=True, padx=18, pady=(14, 18))

        files_panel, _ = self._glow_panel(files_inner, _THEME["surface"], _THEME["text"], pady=(0, 0), expand=True)
        files_frame = ttk.Frame(files_panel, style="Card.TFrame")
        files_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        _file_cols = (
            ("stt",          _T("col_stt"),        42,  tk.CENTER, False),
            ("name",         _T("col_name"),       200, tk.W,      True),
            ("start_time",   _T("col_start_time"), 160, tk.W,      False),
            ("device",       _T("col_device"),      90,  tk.CENTER, False),
            ("file_type",    _T("col_file_type"),   68,  tk.CENTER, False),
            ("size_human",   _T("col_size"),         88,  tk.CENTER, False),
        )
        columns = tuple(c[0] for c in _file_cols)
        self.tree = ttk.Treeview(files_frame, columns=columns, show="headings", selectmode="browse")
        for col, label, width, anchor, stretch in _file_cols:
            self.tree.heading(col, text=label, anchor=anchor)
            self.tree.column(col, width=width, anchor=anchor, stretch=stretch)

        yscroll = ttk.Scrollbar(files_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

        # — status bar —
        status_bar = tk.Frame(self._main_host, bg=_THEME["status_bar"])
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Frame(status_bar, bg=_THEME["border"], height=1).pack(fill=tk.X)
        tk.Label(
            status_bar,
            textvariable=self.status_var,
            font=self._font_sub,
            bg=_THEME["status_bar"],
            fg=_THEME["text"],
            anchor=tk.W,
            padx=12,
            pady=6,
        ).pack(fill=tk.X)

    def _build_login_overlay(self):
        overlay = tk.Frame(self, bg=_THEME["bg"])
        self._login_overlay = overlay
        self._build_login_overlay_inner(overlay)

    def _build_login_overlay_inner(self, overlay):
        card = tk.Frame(
            overlay,
            bg=_THEME["surface"],
            highlightthickness=1,
            highlightbackground=_THEME["border"],
        )
        card.place(relx=0.5, rely=0.45, anchor=tk.CENTER, width=420)

        tk.Label(
            card,
            text=_T("login_title"),
            font=self._font_title,
            bg=_THEME["surface"],
            fg=_THEME["primary"],
        ).pack(pady=(28, 4))

        tk.Label(
            card,
            text=_T("login_app_name"),
            font=self._font_sub,
            bg=_THEME["surface"],
            fg=_THEME["text_muted"],
        ).pack(pady=(0, 20))

        form = tk.Frame(card, bg=_THEME["surface"])
        form.pack(fill=tk.X, padx=32, pady=(0, 8))

        tk.Label(
            form,
            text=_T("password_label"),
            font=self._font_ui,
            bg=_THEME["surface"],
            fg=_THEME["text_muted"],
            anchor=tk.W,
        ).pack(fill=tk.X)

        self._login_password_var = tk.StringVar()
        password_entry = ttk.Entry(form, textvariable=self._login_password_var, show="*", font=self._font_ui)
        password_entry.pack(fill=tk.X, pady=(6, 0), ipady=4)
        self._login_password_entry = password_entry

        self._login_error_var = tk.StringVar(value="")
        tk.Label(
            form,
            textvariable=self._login_error_var,
            font=self._font_sub,
            bg=_THEME["surface"],
            fg=_THEME["danger"],
            anchor=tk.W,
            wraplength=340,
        ).pack(fill=tk.X, pady=(10, 0))

        actions = tk.Frame(card, bg=_THEME["surface"])
        actions.pack(fill=tk.X, padx=32, pady=(16, 28))
        self._shadow_button(actions, "Primary.TButton", _T("login_btn"), self._submit_login, side=tk.TOP)

        password_entry.bind("<Return>", lambda _e: self._submit_login())

    @staticmethod
    def _hex_to_rgb(color):
        color = (color or "#000000").lstrip("#")
        if len(color) != 6:
            return (0, 0, 0)
        return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))

    @staticmethod
    def _rgb_to_hex(rgb):
        return "#{:02x}{:02x}{:02x}".format(
            max(0, min(255, int(rgb[0]))),
            max(0, min(255, int(rgb[1]))),
            max(0, min(255, int(rgb[2]))),
        )

    @classmethod
    def _blend_colors(cls, a, b, ratio):
        ratio = max(0.0, min(1.0, float(ratio)))
        ra, ga, ba = cls._hex_to_rgb(a)
        rb, gb, bb = cls._hex_to_rgb(b)
        return cls._rgb_to_hex(
            (
                ra + (rb - ra) * ratio,
                ga + (gb - ga) * ratio,
                ba + (bb - ba) * ratio,
            )
        )

    def _build_loading_overlay(self):
        overlay = tk.Frame(self, bg=_THEME["bg"])
        self._loading_overlay = overlay

        self._loading_backdrop = tk.Canvas(
            overlay,
            highlightthickness=0,
            bd=0,
            bg=_THEME["bg"],
            cursor="watch",
        )
        self._loading_backdrop.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._loading_backdrop.bind("<Configure>", self._paint_loading_backdrop)

        center = tk.Frame(overlay, bg=_THEME["bg"])
        center.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        shell = tk.Frame(center, bg=_THEME["shadow_2"])
        shell.pack()
        mid = tk.Frame(shell, bg=_THEME["shadow_4"])
        mid.pack(padx=1, pady=1)
        inner = tk.Frame(mid, bg=_THEME["shadow_5"])
        inner.pack(padx=1, pady=1)

        card = tk.Frame(
            inner,
            bg=_THEME["surface"],
            highlightthickness=1,
            highlightbackground=_THEME["border"],
            width=300,
            height=228,
        )
        card.pack(padx=(0, 8), pady=(0, 8))
        card.pack_propagate(False)
        self._loading_card = card

        tk.Frame(card, bg=_THEME["primary"], height=4).pack(fill=tk.X)

        body = tk.Frame(card, bg=_THEME["surface"])
        body.pack(fill=tk.BOTH, expand=True, padx=32, pady=(22, 24))

        self._loading_canvas = tk.Canvas(
            body,
            width=96,
            height=96,
            bg=_THEME["surface"],
            highlightthickness=0,
            bd=0,
        )
        self._loading_canvas.pack()

        self._loading_status_var = tk.StringVar(value=_T("processing"))
        tk.Label(
            body,
            textvariable=self._loading_status_var,
            font=("Segoe UI", 12, "bold"),
            bg=_THEME["surface"],
            fg=_THEME["text"],
        ).pack(pady=(16, 2))

        tk.Label(
            body,
            text=_T("please_wait"),
            font=self._font_sub,
            bg=_THEME["surface"],
            fg=_THEME["text_muted"],
        ).pack()

        bar_host = tk.Frame(body, bg="#dce8f4", height=5)
        bar_host.pack(fill=tk.X, pady=(18, 0))
        bar_host.pack_propagate(False)
        self._loading_bar_canvas = tk.Canvas(
            bar_host,
            height=5,
            bg="#dce8f4",
            highlightthickness=0,
            bd=0,
        )
        self._loading_bar_canvas.pack(fill=tk.BOTH, expand=True)
        self._loading_bar_canvas.bind("<Configure>", lambda _e: self._paint_loading_shimmer())

    def _paint_loading_backdrop(self, _event=None):
        canvas = self._loading_backdrop
        if canvas is None or not canvas.winfo_exists():
            return
        canvas.delete("dim")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        strength = getattr(self, "_loading_backdrop_strength", 1.0)
        veil = "#3d5a73"
        top = self._blend_colors(_THEME["bg"], veil, 0.10 * strength)
        mid = self._blend_colors(_THEME["bg"], veil, 0.26 * strength)
        bottom = self._blend_colors(_THEME["bg"], veil, 0.38 * strength)
        steps = 28
        band = max(height // steps, 1)
        for index in range(steps):
            ratio = index / max(steps - 1, 1)
            if ratio < 0.5:
                color = self._blend_colors(top, mid, ratio * 2.0)
            else:
                color = self._blend_colors(mid, bottom, (ratio - 0.5) * 2.0)
            y0 = index * band
            y1 = height if index == steps - 1 else (index + 1) * band
            canvas.create_rectangle(0, y0, width, y1, fill=color, outline="", tags="dim")
        spacing = 34
        dot = self._blend_colors("#ffffff", _THEME["border"], 0.45)
        for x in range(24, width, spacing):
            for y in range(24, height, spacing):
                canvas.create_oval(x, y, x + 2, y + 2, fill=dot, outline="", tags="dim")

    def _draw_loading_spinner(self):
        canvas = self._loading_canvas
        if canvas is None or not canvas.winfo_exists():
            return
        canvas.delete("all")
        cx, cy = 48, 48
        step = self._loading_spin_step
        angle = (step * 7) % 360
        pulse = 0.88 + 0.12 * math.sin(step * 0.22)
        radius = int(34 * pulse)
        halo = int(radius + 10 + 3 * math.sin(step * 0.18))
        canvas.create_oval(
            cx - halo,
            cy - halo,
            cx + halo,
            cy + halo,
            outline=self._blend_colors(_THEME["glow_3"], _THEME["primary_soft"], 0.35),
            width=2,
        )
        canvas.create_oval(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            outline="#dce8f4",
            width=6,
        )
        canvas.create_arc(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            start=angle,
            extent=118,
            style=tk.ARC,
            outline=_THEME["primary"],
            width=6,
        )
        inner_r = radius - 8
        canvas.create_arc(
            cx - inner_r,
            cy - inner_r,
            cx + inner_r,
            cy + inner_r,
            start=angle + 150,
            extent=72,
            style=tk.ARC,
            outline=_THEME["glow_2"],
            width=4,
        )
        dot_r = 5 + int(2 * abs(math.sin(step * 0.24)))
        canvas.create_oval(
            cx - dot_r,
            cy - dot_r,
            cx + dot_r,
            cy + dot_r,
            fill=_THEME["primary"],
            outline=_THEME["primary_soft"],
            width=2,
        )

    def _paint_loading_shimmer(self):
        canvas = self._loading_bar_canvas
        if canvas is None or not canvas.winfo_exists():
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 5)
        canvas.create_rectangle(0, 0, width, height, fill="#dce8f4", outline="")
        span = max(56, width // 3)
        offset = (self._loading_spin_step * 6) % (width + span) - span // 2
        canvas.create_rectangle(
            offset,
            0,
            offset + span,
            height,
            fill=_THEME["primary"],
            outline="",
        )
        highlight = self._blend_colors(_THEME["glow_2"], "#ffffff", 0.55)
        canvas.create_rectangle(
            offset + span // 4,
            0,
            offset + span // 2,
            height,
            fill=highlight,
            outline="",
        )

    def _set_loading_caption(self, text):
        self._loading_caption_base = (text or _T("processing")).rstrip(".")
        if self._loading_status_var is not None:
            self._loading_status_var.set(self._loading_caption_base)

    @staticmethod
    def _progress_percent(done, total):
        if total <= 0:
            return 0
        return min(100, int(round(done * 100 / total)))

    def _loading_status_text(self):
        if str(self._loading_caption_base).rstrip().endswith("%"):
            return self._loading_caption_base
        dots = "." * ((self._loading_spin_step // 3) % 4)
        return f"{self._loading_caption_base}{dots}"

    def _stop_loading_fade(self):
        job = self._loading_fade_job
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
            self._loading_fade_job = None

    def _animate_loading_fade_in(self):
        if self._loading_backdrop_strength >= 1.0:
            self._loading_backdrop_strength = 1.0
            self._paint_loading_backdrop()
            self._start_loading_spinner()
            return
        self._loading_backdrop_strength = min(1.0, self._loading_backdrop_strength + 0.14)
        self._paint_loading_backdrop()
        self._loading_fade_job = self.after(28, self._animate_loading_fade_in)

    def _start_loading_spinner(self):
        self._stop_loading_spinner()
        self._loading_spin_step = 0
        self._tick_loading_spinner()

    def _tick_loading_spinner(self):
        overlay = self._loading_overlay
        if overlay is None or not overlay.winfo_ismapped():
            return
        self._draw_loading_spinner()
        self._paint_loading_shimmer()
        if self._loading_status_var is not None:
            self._loading_status_var.set(self._loading_status_text())
        self._loading_spin_step += 1
        self._loading_spin_job = self.after(42, self._tick_loading_spinner)

    def _stop_loading_spinner(self):
        job = self._loading_spin_job
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
            self._loading_spin_job = None
        self._stop_loading_fade()

    def _display_loading_overlay(self):
        overlay = self._loading_overlay
        if overlay is None:
            return
        already_visible = overlay.winfo_ismapped()
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        login = self._login_overlay
        if login is not None and login.winfo_ismapped():
            login.lift()
        else:
            overlay.lift()
        if already_visible:
            self._loading_backdrop_strength = 1.0
            self._paint_loading_backdrop()
            if self._loading_spin_job is None:
                self._start_loading_spinner()
            return
        self._loading_backdrop_strength = 0.0
        self._stop_loading_fade()
        self._animate_loading_fade_in()

    def _hide_loading_overlay(self):
        overlay = self._loading_overlay
        if overlay is not None:
            overlay.place_forget()
        self._loading_backdrop_strength = 0.0
        self._stop_loading_spinner()
        canvas = self._loading_canvas
        if canvas is not None and canvas.winfo_exists():
            canvas.delete("all")
        bar = self._loading_bar_canvas
        if bar is not None and bar.winfo_exists():
            bar.delete("all")
        self._loading_caption_base = _T("processing")
        if self._loading_status_var is not None:
            self._loading_status_var.set(self._loading_caption_base)

    def _api_loading_begin(self):
        with self._api_loading_lock:
            self._api_loading_count += 1
            if self._api_loading_count == 1:
                self.after(0, self._display_loading_overlay)

    def _api_loading_end(self):
        with self._api_loading_lock:
            self._api_loading_count = max(0, self._api_loading_count - 1)
            if self._api_loading_count == 0:
                self.after(0, self._hide_loading_overlay)

    def _show_login_overlay(self):
        if self._login_overlay is None:
            return
        self._login_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._login_overlay.lift()
        if self._login_password_var is not None:
            self._login_password_var.set("")
        if self._login_error_var is not None:
            self._login_error_var.set("")
        self.after(50, self._focus_login_password)

    def _focus_login_password(self):
        entry = getattr(self, "_login_password_entry", None)
        if entry is not None and entry.winfo_exists():
            entry.focus_force()

    def _hide_login_overlay(self):
        if self._login_overlay is not None:
            self._login_overlay.place_forget()

    def _submit_login(self):
        if self.auth is None:
            self._on_login_success()
            return
        password = (self._login_password_var.get() if self._login_password_var else "").strip()
        if not password:
            if self._login_error_var is not None:
                self._login_error_var.set(_T("enter_password"))
            return
        if not self.auth.login(password):
            if self._login_error_var is not None:
                self._login_error_var.set(_T("wrong_password"))
            return
        self._on_login_success()

    def _on_login_success(self):
        self._logged_in = True
        self._hide_login_overlay()
        if getattr(self, "_logout_button", None) is not None:
            self._logout_button.pack()
        self._bind_session_activity()
        self._start_post_login()
        if self.auth is not None and self.auth.must_change_password():
            self.after(100, lambda: self._show_change_password_dialog(force=True))

    def _start_post_login(self):
        self._start_data_server()
        self._start_registry_api()
        self._set_status(_T("starting_node"))
        self.after(200, self.auto_setup_hotspot)
        self.after(300, self.auto_open_firewall_ports)
        self.after(400, self.refresh_network_display)
        if requests is None:
            messagebox.showerror(
                _T("missing_lib"),
                _T("install_requests"),
            )
        else:
            self.after(500, self.check_status)
        self._schedule_session_check()
        if self._audio_player is not None:
            self.after(600, lambda: self._audio_player.load_folder(self._download_dir))

    def _bind_session_activity(self):
        for sequence in ("<Button-1>", "<KeyPress>", "<MouseWheel>"):
            self.bind_all(sequence, self._on_session_activity, add="+")

    def _on_session_activity(self, _event=None):
        if self.auth is not None and self._logged_in:
            self.auth.touch_activity()

    def _schedule_session_check(self):
        if self._session_check_job is not None:
            try:
                self.after_cancel(self._session_check_job)
            except tk.TclError:
                pass
        self._session_check_job = self.after(30_000, self._check_session)

    def _check_session(self):
        self._session_check_job = None
        if not self._logged_in:
            return
        if self.auth is not None and self.auth.is_session_expired():
            self._logout(expired=True)
            return
        self._schedule_session_check()

    def _logout(self, expired=False):
        if not self._logged_in:
            return
        self._logged_in = False
        if self.auth is not None:
            self.auth.logout()
        if self._session_check_job is not None:
            try:
                self.after_cancel(self._session_check_job)
            except tk.TclError:
                pass
            self._session_check_job = None
        if self.data_server is not None:
            self.data_server.stop()
        if self.registry_server is not None:
            self.registry_server.stop()
        self.connected = False
        self._set_connection_state(False, _T("not_verified"))
        if getattr(self, "_logout_button", None) is not None:
            self._logout_button.pack_forget()
        if expired:
            messagebox.showwarning(
                _T("session_expired_title"),
                _T("session_expired_msg"),
            )
        self._set_status(_T("please_login"))
        self._show_login_overlay()

    def _show_change_password_dialog(self, force=False):
        dialog = tk.Toplevel(self)
        dialog.title(_T("change_pw_title"))
        dialog.minsize(420, 420)
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.configure(bg=_THEME["surface"])
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        if force:
            dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        body = tk.Frame(dialog, bg=_THEME["surface"])
        body.grid(row=0, column=0, sticky=tk.NSEW, padx=24, pady=(24, 8))
        body.columnconfigure(0, weight=1)

        tk.Label(
            body,
            text=_T("change_pw_title"),
            font=self._font_title,
            bg=_THEME["surface"],
            fg=_THEME["primary"],
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(0, 4))

        hint = _T("change_pw_first") if force else _T("change_pw_hint")
        tk.Label(
            body,
            text=hint,
            font=self._font_sub,
            bg=_THEME["surface"],
            fg=_THEME["text_muted"],
            wraplength=380,
            anchor=tk.W,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 12))

        form = tk.Frame(body, bg=_THEME["surface"])
        form.pack(fill=tk.X)

        current_var = tk.StringVar()
        new_var = tk.StringVar()
        confirm_var = tk.StringVar()
        error_var = tk.StringVar(value="")

        for label, var in (
            (_T("current_password"), current_var),
            (_T("new_password"), new_var),
            (_T("confirm_password"), confirm_var),
        ):
            tk.Label(
                form,
                text=label,
                font=self._font_ui,
                bg=_THEME["surface"],
                fg=_THEME["text_muted"],
                anchor=tk.W,
            ).pack(fill=tk.X, pady=(8, 0))
            ttk.Entry(form, textvariable=var, show="*", font=self._font_ui).pack(
                fill=tk.X, pady=(4, 0), ipady=3
            )

        tk.Label(
            form,
            textvariable=error_var,
            font=self._font_sub,
            bg=_THEME["surface"],
            fg=_THEME["danger"],
            anchor=tk.W,
            wraplength=360,
        ).pack(fill=tk.X, pady=(10, 0))

        actions = tk.Frame(dialog, bg=_THEME["surface"])
        actions.grid(row=1, column=0, sticky=tk.EW, padx=24, pady=(0, 24))

        def apply_change():
            if self.auth is None:
                dialog.destroy()
                return
            current = current_var.get().strip()
            new = new_var.get().strip()
            confirm = confirm_var.get().strip()
            if not current or not new or not confirm:
                error_var.set(_T("fill_all_fields"))
                return
            if new != confirm:
                error_var.set(_T("password_mismatch"))
                return
            ok, msg = self.auth.change_password(current, new)
            if not ok:
                error_var.set(
                    {
                        "Current password is incorrect.": _T("pw_wrong_current"),
                        f"New password must be at least {PASSWORD_MIN_LENGTH} characters.": (
                            _T("pw_too_short").replace("{n}", str(PASSWORD_MIN_LENGTH))
                        ),
                        "New password must differ from the current password.": _T("pw_same_as_old"),
                    }.get(msg, msg)
                )
                return
            dialog.destroy()
            self._set_status(_T("pw_changed"))
            messagebox.showinfo(_T("pw_changed_title"), _T("pw_changed_msg"), parent=self)

        if not force:
            self._shadow_button(
                actions,
                "Secondary.TButton",
                _T("cancel_btn"),
                dialog.destroy,
                side=tk.RIGHT,
                padx=(8, 0),
            )

        self._shadow_button(
            actions,
            "Primary.TButton",
            _T("save_password_btn"),
            apply_change,
            side=tk.RIGHT,
            padx=(0, 0),
        )

        dialog.bind("<Return>", lambda _e: apply_change())

        self._finalize_toplevel(dialog, 460, 420)
        dialog.grab_set()
        dialog.focus_force()

    def _require_logged_in(self):
        if self._logged_in:
            return True
        messagebox.showwarning(_T("not_logged_in_title"), _T("not_logged_in_msg"))
        self._show_login_overlay()
        return False

    @staticmethod
    def _center_toplevel_on_screen(dialog, width=None, height=None, parent=None):
        dialog.update_idletasks()
        w = width or dialog.winfo_reqwidth() or dialog.winfo_width()
        h = height or dialog.winfo_reqheight() or dialog.winfo_height()
        if parent is not None and parent.winfo_exists():
            parent.update_idletasks()
            x = parent.winfo_rootx() + max(0, (parent.winfo_width() - w) // 2)
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 2)
        else:
            screen_w = dialog.winfo_screenwidth()
            screen_h = dialog.winfo_screenheight()
            x = max(0, (screen_w - w) // 2)
            y = max(0, (screen_h - h) // 2)
        dialog.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")

    def _finalize_toplevel(self, dialog, width=None, height=None):
        dialog.withdraw()
        dialog.update_idletasks()
        self._center_toplevel_on_screen(dialog, width, height, parent=self)
        dialog.deiconify()
        dialog.lift(self)
        dialog.focus_force()
        dialog.attributes("-topmost", True)
        dialog.after(200, lambda: dialog.attributes("-topmost", False))

    # ===================== Helpers =====================
    def _toggle_language(self):
        global _LANG
        _LANG = "en" if _LANG == "vi" else "vi"
        try:
            import lang as _lang_module
            _lang_module.set_lang(_LANG)
        except Exception:
            pass
        self._apply_language()

    def _apply_language(self):
        # header
        if hasattr(self, "_lang_btn"):
            self._lang_btn.update_text(_T("lang_toggle_to_en"))
        if hasattr(self, "_header_status_label"):
            self._header_status_label.configure(text=_T("header_status_label"))
        if hasattr(self, "_logout_button"):
            try:
                self._logout_button.update_text(_T("logout"))
            except Exception:
                pass
        # sidebar connection section
        if hasattr(self, "_conn_sub_var"):
            count = (self._conn_count_badge_var.get() if hasattr(self, "_conn_count_badge_var") else "0")
            self._conn_sub_var.set(f"{_T('conn_count_badge_sub')} ({count})")
        # shared vars
        if hasattr(self, "hotspot_status_var") and self.hotspot_ssid == "" and wifi_hotspot is None:
            self.hotspot_status_var.set(_T("blockchain_hash_unavail"))
        if hasattr(self, "connection_var"):
            if self.connected:
                self.connection_var.set(_T("connected_device"))
            else:
                self.connection_var.set(_T("not_connected_device"))
        # status bar
        if hasattr(self, "status_var"):
            if not self._logged_in:
                self._set_status(_T("please_login"))
        # login overlay labels
        if hasattr(self, "_login_overlay") and self._login_overlay is not None:
            self._rebuild_login_overlay_text()
        # loading overlay
        if hasattr(self, "_loading_status_var") and self._loading_status_var is not None:
            self._loading_caption_base = _T("processing")
            self._loading_status_var.set(self._loading_caption_base)
        # audio player
        if hasattr(self, "_audio_player") and self._audio_player is not None:
            try:
                self._audio_player.apply_language()
            except Exception:
                pass
        # sidebar section titles
        if hasattr(self, "_conn_section_title_lbl"):
            self._conn_section_title_lbl.config(text=_T("connected_devices"))
        if hasattr(self, "_device_list_subtitle_lbl"):
            self._device_list_subtitle_lbl.config(text=_T("device_list_subtitle"))
        if hasattr(self, "_decrypt_btn"):
            self._decrypt_btn.config(text=_T("decrypt_bin_btn"))
        if hasattr(self, "_recordings_title_lbl"):
            self._recordings_title_lbl.config(text=_T("recordings_title"))
        if hasattr(self, "tree"):
            self.tree.heading("stt",        text=_T("col_stt"))
            self.tree.heading("name",       text=_T("col_name"))
            self.tree.heading("start_time", text=_T("col_start_time"))
            self.tree.heading("device",     text=_T("col_device"))
            self.tree.heading("file_type",  text=_T("col_file_type"))
            self.tree.heading("size_human", text=_T("col_size"))
        if hasattr(self, "_refresh_files_btn") and self._refresh_files_btn:
            try:
                self._refresh_files_btn.update_text(_T("refresh_btn"))
            except Exception:
                pass

    def _rebuild_login_overlay_text(self):
        for widget in self._login_overlay.winfo_children():
            try:
                widget.destroy()
            except Exception:
                pass
        self._build_login_overlay_inner(self._login_overlay)

    def _decode(self, value):
        if not value:
            return ""
        return base64.b64decode(value).decode("utf-8")

    def _endpoint(self, name):
        return self._decode(_ENDPOINTS[name])

    def _base_url(self):
        if network_config is not None:
            return network_config.local_service_url().rstrip("/")
        return "http://127.0.0.1:8765"

    def _api_url(self, endpoint_name):
        return self._base_url() + self._endpoint(endpoint_name)

    def _headers(self):
        key = self._decode(_HIDDEN_KEY).strip()
        if not key:
            return {}
        return {"X-App-Key": key}

    @staticmethod
    def _log_http_request(method, url, **kwargs):
        _http_logger.info("HTTP %s %s", method.upper(), url)
        params = kwargs.get("params")
        if params:
            _http_logger.info("  params: %s", params)
        if kwargs.get("files"):
            _http_logger.info("  body: multipart")
        elif kwargs.get("json") is not None:
            _http_logger.info(
                "  body: %s",
                json.dumps(kwargs["json"], ensure_ascii=False),
            )

    @staticmethod
    def _log_http_response(response, include_body=True):
        status = response.status_code
        if not include_body:
            size = response.headers.get("Content-Length", "?")
            _http_logger.info("HTTP response %s: <%s bytes>", status, size)
            return
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "json" in content_type or "text" in content_type:
            body = response.text
        else:
            body = f"<{len(response.content)} bytes>"
        if len(body) > _HTTP_LOG_MAX_BODY:
            body = body[:_HTTP_LOG_MAX_BODY] + "... (truncated)"
        _http_logger.info("HTTP response %s: %s", status, body)

    @staticmethod
    def _log_http_error(method, url, exc):
        _http_logger.error("HTTP %s %s failed: %s", method.upper(), url, exc)

    def _http_get(self, url, **kwargs):
        self._api_loading_begin()
        stream = bool(kwargs.get("stream"))
        try:
            self._log_http_request("GET", url, **kwargs)
            try:
                response = requests.get(url, **kwargs)
            except requests.exceptions.RequestException as exc:
                self._log_http_error("GET", url, exc)
                raise
            self._log_http_response(response, include_body=not stream)
            if stream:
                return _StreamLoadingResponse(response, self._api_loading_end)
            return response
        except Exception:
            if stream:
                self._api_loading_end()
            raise
        finally:
            if not stream:
                self._api_loading_end()

    def _http_post(self, url, **kwargs):
        self._api_loading_begin()
        try:
            self._log_http_request("POST", url, **kwargs)
            try:
                response = requests.post(url, **kwargs)
            except requests.exceptions.RequestException as exc:
                self._log_http_error("POST", url, exc)
                raise
            self._log_http_response(response)
            return response
        finally:
            self._api_loading_end()

    def _http_delete(self, url, **kwargs):
        self._api_loading_begin()
        try:
            self._log_http_request("DELETE", url, **kwargs)
            try:
                response = requests.delete(url, **kwargs)
            except requests.exceptions.RequestException as exc:
                self._log_http_error("DELETE", url, exc)
                raise
            self._log_http_response(response)
            return response
        finally:
            self._api_loading_end()

    def _set_status(self, msg):
        self.status_var.set(self._status_display_message(msg))

    @staticmethod
    def _status_display_message(msg):
        text = str(msg or "")
        hide_markers = (
            "Host:",
            "device:",
            "10.42.0.",
            "192.168.137.",
            "adapter IP",
            "ICS subnet",
            "Registry API listening",
            "registry api already running",
            "chip Wi-Fi",
            "CONFLICT_NO_ETHERNET",
            "CONFLICT_USE_ETHERNET",
            "PC đang bắt",
            "không vừa bắt Wi-Fi",
            "Kích hoạt thất bại",
        )
        lowered = text.lower()
        if any(marker.lower() in lowered for marker in hide_markers):
            if any(token in lowered for token in ("fail", "error", "timeout", "could not", "unable")):
                return _T("operation_failed")
            return _T("ready")
        return text

    def _set_safe_info(self, msg):
        self.safe_info_var.set(msg)

    def _stop_badge_pulse(self):
        job = getattr(self, "_pulse_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
            self._pulse_job = None

    def _pulse_badge(self):
        has_conn = (
            self.connection_store is not None
            and len(self.connection_store.list_connections()) > 0
        )
        if not (self.connected or self._node_active or has_conn):
            return
        tones = (_THEME["success_bg"], "#c8ebda", "#e2f5ec", _THEME["success_bg"])
        self._conn_badge.configure(bg=tones[self._pulse_step % len(tones)])
        shell = getattr(self, "_conn_badge_shell", None)
        if shell is not None:
            shell.configure(bg=tones[self._pulse_step % len(tones)])
        self._pulse_step += 1
        self._pulse_job = self.after(650, self._pulse_badge)

    def _update_header_online_state(self):
        if not hasattr(self, "_conn_badge"):
            return
        has_connection = (
            self.connection_store is not None
            and len(self.connection_store.list_connections()) > 0
        )
        has_online_device = (
            self.registry_server is not None
            and any(
                self.registry_server.registry.is_online(e)
                for e in self.registry_server.registry.list_devices()
            )
        )
        online = bool(self.connected or self._node_active or has_connection or has_online_device)
        self._update_connection_badge(online)

    def _update_connection_badge(self, online):
        if not hasattr(self, "_conn_badge"):
            return
        self._stop_badge_pulse()
        if online:
            self._conn_badge.configure(text=" ONLINE ", bg=_THEME["success_bg"], fg=_THEME["success"])
            shell = getattr(self, "_conn_badge_shell", None)
            if shell is not None:
                shell.configure(bg=_THEME["success_bg"], highlightbackground=_THEME["success"])
            self._pulse_step = 0
            self._pulse_badge()
        else:
            self._conn_badge.configure(text=" OFFLINE ", bg=_THEME["danger_bg"], fg=_THEME["danger"])
            shell = getattr(self, "_conn_badge_shell", None)
            if shell is not None:
                shell.configure(bg=_THEME["danger_bg"], highlightbackground=_THEME["danger"])

    def _set_connection_state(self, ok, info=None):
        self.connected = bool(ok)
        self._update_header_online_state()
        if ok:
            self.connection_var.set(_T("connected_device"))
            if info:
                self._set_safe_info(info)
        else:
            self.connection_var.set(_T("not_connected_device"))
            self._set_safe_info(
                info or _T("connection_failed_info")
            )
            self._clear_tree()

    def _clear_tree(self):
        self.files_data = []
        self._active_device_ip = None
        self._active_device_port = None
        for row in self.tree.get_children():
            self.tree.delete(row)

    @staticmethod
    def _parse_file_time_fields(fname):
        import re as _re
        m = _re.search(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", fname)
        if m:
            start = f"{m.group(4)}:{m.group(5)}:{m.group(6)}  {m.group(3)}/{m.group(2)}/{m.group(1)}"
        else:
            start = fname
        ext = fname.rsplit(".", 1)[-1].upper() if "." in fname else "—"
        return start, "—", ext

    def _populate_files_tree(self, files, status_message, safe_info=None):
        self.files_data = files
        for row in self.tree.get_children():
            self.tree.delete(row)
        for idx, item in enumerate(files, start=1):
            fname = item.get("name", "")
            start_time, _, file_type = self._parse_file_time_fields(fname)
            self.tree.insert(
                "",
                tk.END,
                iid=fname,
                values=(
                    idx,
                    fname,
                    start_time,
                    item.get("_device", "—"),
                    file_type,
                    item.get("size_human", ""),
                ),
            )
        if safe_info is not None:
            self._set_safe_info(safe_info)
        self._set_status(status_message)

    def _staging_dir(self):
        d = Path(self._download_dir) / "record"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _device_rec_dir(self, device_display_name):
        safe = "".join(c for c in (device_display_name or "unknown") if c.isalnum() or c in "_-") or "unknown"
        d = Path(self._download_dir) / safe
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def _refresh_local_files_tree(self):
        d = Path(self._download_dir).resolve()
        d_parts_len = len(d.parts)
        all_files = []
        if d.is_dir():
            for p in d.rglob("*"):
                if not (p.is_file() and p.suffix.lower() != ".bin"):
                    continue
                sz = p.stat().st_size
                mtime = p.stat().st_mtime
                if sz < 1024:
                    sh = f"{sz} B"
                elif sz < 1024 * 1024:
                    sh = f"{sz/1024:.1f} KB"
                else:
                    sh = f"{sz/1024/1024:.1f} MB"
                p_parts = p.resolve().parts
                device_name = p_parts[d_parts_len] if len(p_parts) > d_parts_len + 1 else "—"
                all_files.append({"name": p.name, "size_human": sh, "_mtime": mtime, "_device": device_name})
        all_files.sort(key=lambda x: x["_mtime"], reverse=True)
        self._populate_files_tree(
            all_files,
            f"{_T('records_list_prefix')}{len(all_files)}{_T('records_list_suffix')}",
        )

    def _on_audio_filter_change(self, filtered_entries):
        d = Path(self._download_dir).resolve()
        d_parts_len = len(d.parts)
        result = []
        for entry in filtered_entries:
            p = Path(entry["path"]).resolve()
            try:
                sz = p.stat().st_size
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if sz < 1024:
                sh = f"{sz} B"
            elif sz < 1024 * 1024:
                sh = f"{sz/1024:.1f} KB"
            else:
                sh = f"{sz/1024/1024:.1f} MB"
            p_parts = p.parts
            device_name = p_parts[d_parts_len] if len(p_parts) > d_parts_len + 1 else "—"
            result.append({"name": p.name, "size_human": sh, "_mtime": mtime, "_device": device_name})
        result.sort(key=lambda x: x["_mtime"], reverse=True)
        self._populate_files_tree(result, f"{_T('records_list_prefix')}{len(result)}{_T('records_list_suffix')}")

    def refresh_files_view(self):
        if self._active_device_ip:
            self.refresh_device_files(
                {
                    "ip": self._active_device_ip,
                    "port": self._active_device_port,
                }
            )
        else:
            self.refresh_files()

    def show_device_files(self, connection, parent_dialog=None):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return
        ip, port = self._resolve_connection(connection)
        if not ip:
            messagebox.showwarning(_T("missing_ip"), _T("device_no_ip"))
            return
        display_id = self._device_connection_display(ip)
        list_url = self._device_service_url(ip, "/api/filelist", port=port)
        _terminal_decode_log(
            f"filelist start ip={ip} port={port} device={display_id} url={list_url}"
        )

        def task():
            r = self._http_get(
                list_url,
                headers=self._headers(),
                timeout=self._request_timeout(),
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                raise ValueError(
                    data.get("error") or data.get("message") or "invalid response"
                )
            files = data.get("files", [])
            self.after(
                0,
                lambda: self._show_device_files_dialog(
                    ip,
                    files,
                    parent_dialog=parent_dialog,
                    device_port=port,
                ),
            )

        self._run_async(
            f"{_T('loading_filelist')}{display_id}...",
            task,
            failure_text=f"{_T('filelist_load_failed')}{display_id}.",
            affects_connection=False,
        )

    def _show_device_files_dialog(self, device_ip, files, parent_dialog=None, device_port=None):
        display_id = self._device_connection_display(device_ip)
        dialog = tk.Toplevel(self)
        dialog.title(f"{_T('filelist_dialog_title')}{display_id}")
        dialog.minsize(560, 360)
        if parent_dialog is not None:
            dialog.transient(parent_dialog)
        else:
            dialog.transient(self)
        dialog.configure(bg=_THEME["bg"])
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        header = tk.Frame(dialog, bg=_THEME["header"])
        header.grid(row=0, column=0, sticky=tk.EW)
        header_inner = tk.Frame(header, bg=_THEME["header"])
        header_inner.pack(fill=tk.X, padx=20, pady=14)
        tk.Label(
            header_inner,
            text=_T("device_files_heading"),
            font=(self._font_ui[0], 14, "bold"),
            bg=_THEME["header"],
            fg="#ffffff",
            anchor=tk.W,
        ).pack(anchor=tk.W)
        count_var = tk.StringVar(value=f"{len(files)} file")
        tk.Label(
            header_inner,
            textvariable=count_var,
            font=self._font_ui,
            bg=_THEME["header"],
            fg="#b8d4f0",
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(6, 0))
        tk.Label(
            header_inner,
            text=display_id,
            font=self._font_ui,
            bg=_THEME["header"],
            fg="#b8d4f0",
            anchor=tk.W,
        ).pack(anchor=tk.W, pady=(4, 0))

        list_wrap = tk.Frame(dialog, bg=_THEME["bg"])
        list_wrap.grid(row=1, column=0, sticky=tk.NSEW, padx=16, pady=16)
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)

        shell = tk.Frame(list_wrap, bg=_THEME["border"])
        shell.grid(row=0, column=0, sticky=tk.NSEW)
        inner = tk.Frame(shell, bg=_THEME["surface"])
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        columns = ("check", "name", "time_display", "size_human")
        checked_files = {}
        tree_frame = tk.Frame(inner, bg=_THEME["surface"])
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="none",
            height=_FILES_LIST_VISIBLE_ROWS,
        )
        tree.heading("check", text="", anchor=tk.CENTER)
        tree.heading("name", text=_T("col_filename"), anchor=tk.W)
        tree.heading("time_display", text=_T("col_time"), anchor=tk.CENTER)
        tree.heading("size_human", text=_T("col_size"), anchor=tk.CENTER)
        tree.column("check", width=30, minwidth=30, anchor=tk.CENTER, stretch=False)
        tree.column("name", width=220, anchor=tk.W)
        tree.column("time_display", width=180, anchor=tk.CENTER)
        tree.column("size_human", width=100, anchor=tk.CENTER)

        yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        tree.grid(row=0, column=0, sticky=tk.NSEW)
        yscroll.grid(row=0, column=1, sticky=tk.NS)

        all_files = list(files)

        def populate_file_list(file_items):
            for row in tree.get_children():
                tree.delete(row)
            checked_files.clear()
            for item in file_items:
                fname = item.get("name", "")
                import re as _re
                m = _re.search(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", fname)
                if m:
                    time_display = (
                        f"{m.group(4)}:{m.group(5)}:{m.group(6)}  "
                        f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
                    )
                else:
                    time_display = fname
                tree.insert(
                    "",
                    tk.END,
                    iid=fname,
                    values=("☐", fname, time_display, item.get("size_human", "")),
                )
            count_var.set(f"{len(file_items)} file")

        def toggle_check(event):
            row = tree.identify_row(event.y)
            if not row:
                return
            if row in checked_files:
                del checked_files[row]
                tree.set(row, "check", "☐")
            else:
                checked_files[row] = True
                tree.set(row, "check", "☑")

        tree.bind("<ButtonRelease-1>", toggle_check)

        def set_all_files(file_items):
            all_files.clear()
            all_files.extend(file_items)
            populate_file_list(all_files)

        populate_file_list(all_files)

        footer = tk.Frame(dialog, bg=_THEME["surface"])
        footer.grid(row=2, column=0, sticky=tk.EW)
        tk.Frame(footer, bg=_THEME["border"], height=1).pack(fill=tk.X)
        actions = tk.Frame(footer, bg=_THEME["surface"])
        actions.pack(fill=tk.X, padx=16, pady=12)

        def selected_name():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning(
                    _T("no_file_selected_title"),
                    _T("select_file_dialog_msg"),
                    parent=dialog,
                )
                return None
            return selected[0]

        def download_file():
            name = selected_name()
            if not name:
                return

            def task():
                dest = self._download_bin_only(
                    self._device_service_url(device_ip, "/api/download", port=device_port),
                    name,
                    dest_dir=self._device_rec_dir(self._device_connection_display(device_ip)),
                    on_status=self._set_status,
                )
                self.after(0, lambda: messagebox.showinfo(
                    "Tải file",
                    f"Đã tải về:\n{dest.name}\n\nThư mục: {dest.parent}",
                    parent=dialog,
                ))
                self.after(0, lambda: self._set_status(f"Đã tải {name} vào {dest.parent.name}."))

            self._run_async(
                "Đang tải file...",
                task,
                failure_text=_T("download_failed_one"),
                affects_connection=False,
            )

        def reload_list():
            list_url = self._device_service_url(device_ip, "/api/filelist", port=device_port)

            def task():
                r = self._http_get(
                    list_url,
                    headers=self._headers(),
                    timeout=self._request_timeout(),
                )
                r.raise_for_status()
                data = r.json()
                if not data.get("ok"):
                    raise ValueError(
                        data.get("error") or data.get("message") or "invalid response"
                    )
                file_items = data.get("files", [])
                self.after(0, lambda: set_all_files(file_items))

            self._run_async(
                _T("refreshing"),
                task,
                failure_text=_T("reload_filelist_failed"),
                affects_connection=False,
            )

        def download_all_files():
            if not all_files:
                messagebox.showinfo(_T("no_files_title"), _T("list_empty"), parent=dialog)
                return
            file_names = [f.get("name", "") for f in all_files if f.get("name")]
            total = len(file_names)
            download_base = self._device_service_url(
                device_ip, "/api/download", port=device_port
            )

            dialog.destroy()

            def task():
                success_count = 0
                if total > 0:
                    self.after(0, lambda: self._set_loading_caption(
                        f"{_T('downloading_files')} {self._progress_percent(0, total)}%"
                    ))
                for i, name in enumerate(file_names):
                    try:
                        self._download_bin_only(download_base, name,
                                                dest_dir=self._device_rec_dir(self._device_connection_display(device_ip)))
                        success_count += 1
                    except Exception:
                        pass
                    percent = self._progress_percent(i + 1, total)
                    self.after(0, lambda p=percent: self._set_loading_caption(f"{_T('downloading_files')} {p}%"))

                def update_ui():
                    if success_count <= 0:
                        messagebox.showerror(_T("failed_title"), _T("no_files_downloaded"), parent=self)
                        self._set_status(_T("no_files_downloaded"))
                        return
                    rec_dir = self._device_rec_dir(self._device_connection_display(device_ip))
                    messagebox.showinfo(
                        _T("success_title"),
                        _T("downloaded_n_of_m").replace("{s}", str(success_count)).replace("{t}", str(total))
                        + f"\n\n{_T('folder_label')}{rec_dir}",
                        parent=self,
                    )
                    self._set_status(_T("downloaded_n_of_m").replace("{s}", str(success_count)).replace("{t}", str(total)))

                self.after(0, update_ui)

            self._run_async(
                _T("downloading_files"),
                task,
                failure_text=_T("download_failed_msg"),
                affects_connection=False,
            )

        def download_selected_files():
            names = list(checked_files.keys())
            if not names:
                messagebox.showwarning(_T("no_file_selected_title"), _T("check_files_no_select_msg"), parent=dialog)
                return
            total = len(names)
            download_base = self._device_service_url(device_ip, "/api/download", port=device_port)

            dialog.destroy()

            def task():
                success_count = 0
                for i, name in enumerate(names):
                    try:
                        self._download_bin_only(download_base, name,
                                                dest_dir=self._device_rec_dir(self._device_connection_display(device_ip)))
                        success_count += 1
                    except Exception:
                        pass
                    percent = self._progress_percent(i + 1, total)
                    self.after(0, lambda p=percent: self._set_loading_caption(f"{_T('downloading_files')} {p}%"))

                def update_ui():
                    if success_count <= 0:
                        messagebox.showerror(_T("failed_title"), _T("no_files_downloaded"), parent=self)
                        self._set_status(_T("no_files_downloaded"))
                        return
                    rec_dir = self._device_rec_dir(self._device_connection_display(device_ip))
                    messagebox.showinfo(
                        _T("success_title"),
                        _T("downloaded_n_of_m").replace("{s}", str(success_count)).replace("{t}", str(total))
                        + f"\n{_T('folder_label')}{rec_dir}",
                        parent=self,
                    )
                    self._set_status(_T("downloaded_n_of_m").replace("{s}", str(success_count)).replace("{t}", str(total)))

                self.after(0, update_ui)

            self._run_async(_T("downloading_files"), task, failure_text=_T("download_failed_msg"), affects_connection=False)

        self._shadow_button(actions, "Primary.TButton", _T("download_all_btn"), download_all_files, side=tk.RIGHT, padx=(8, 0))
        self._shadow_button(actions, "Primary.TButton", _T("download_selected_btn"), download_selected_files, side=tk.RIGHT, padx=(0, 0))
        self._shadow_button(actions, "Secondary.TButton", _T("refresh_btn"), reload_list, side=tk.RIGHT, padx=(8, 0))
        self._shadow_button(actions, "Secondary.TButton", _T("close_btn"), dialog.destroy, side=tk.RIGHT, padx=(8, 0))

        self._finalize_toplevel(dialog, 720, 480)

    def refresh_device_files(self, connection):
        ip, port = self._resolve_connection(connection)
        self._active_device_ip = ip or None
        self._active_device_port = port
        if not self._active_device_ip:
            messagebox.showwarning(_T("missing_ip"), _T("device_no_ip"))
            return

        display_id = self._device_connection_display(ip)
        list_url = self._device_service_url(ip, "/api/filelist", port=port)

        def task():
            r = self._http_get(
                list_url,
                headers=self._headers(),
                timeout=self._request_timeout(),
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                raise ValueError(
                    data.get("error") or data.get("message") or "invalid response"
                )
            files = data.get("files", [])

            def update_ui():
                self._set_connection_state(True)
                self._populate_files_tree(
                    files,
                    _T("loaded_files").replace("{n}", str(len(files))) + display_id + ".",
                    safe_info=f"{_T('connected_device')}\n{len(files)} file",
                )

            self.after(0, update_ui)

        self._run_async(
            f"{_T('loading_filelist')}{display_id}...",
            task,
            failure_text=f"{_T('filelist_load_failed')}{display_id}.",
            affects_connection=False,
        )

    def _run_async(self, title, fn, failure_text=None, affects_connection=True):
        if self.busy:
            self._set_status(_T("busy_wait"))
            return

        def worker():
            self.busy = True
            self._api_loading_begin()
            try:
                self.after(0, lambda: self._set_status(title))
                self.after(0, lambda: self._set_loading_caption(title))
                fn()
            except requests.exceptions.RequestException as exc:
                _decode_logger.exception("async request failed: %s", exc)
                _terminal_decode_log(f"async request failed: {exc}", logging.ERROR)
                if affects_connection:
                    self.after(0, lambda: self._set_connection_state(False))
                self.after(0, lambda: self._set_status(failure_text or _T("refresh_failed")))
            except Exception as e:
                _decode_logger.exception("async task failed: %s", e)
                _terminal_decode_log(f"async task failed: {e}", logging.ERROR)
                err_msg = str(e)
                self.after(0, lambda msg=err_msg: messagebox.showerror(_T("error_title"), msg))
                self.after(0, lambda: self._set_status(_T("error_occurred")))
            finally:
                self._api_loading_end()
                self.busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _request_timeout(self):
        return 6

    def _selected_file_name(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(_T("no_file_selected_title"), _T("select_one_file"))
            return None
        return selected[0]

    def _download_all_main(self):
        if not self.files_data:
            messagebox.showinfo(_T("no_files_title"), _T("list_empty"))
            return
        file_names = [f.get("name", "") for f in self.files_data if f.get("name")]
        total = len(file_names)
        if self._active_device_ip:
            download_base = self._device_service_url(
                self._active_device_ip, "/api/download", port=self._active_device_port
            )
        else:
            download_base = self._api_url("download")

        def task():
            success_count = 0
            if total > 0:
                self.after(0, lambda: self._set_loading_caption(f"{_T('downloading_files')} {self._progress_percent(0, total)}%"))
            for i, name in enumerate(file_names):
                try:
                    self._download_bin_only(
                        download_base, name,
                        dest_dir=self._device_rec_dir(self._device_connection_display(self._active_device_ip) if self._active_device_ip else "unknown"),
                    )
                    success_count += 1
                except Exception:
                    pass
                pct = self._progress_percent(i + 1, total)
                self.after(0, lambda p=pct: self._set_loading_caption(f"{_T('downloading_files')} {p}%"))

            def update_ui():
                if success_count <= 0:
                    messagebox.showerror(_T("failed_title"), _T("no_files_downloaded"))
                    self._set_status(_T("save_all_failed"))
                    return
                rec_dir = self._device_rec_dir(self._device_connection_display(self._active_device_ip) if self._active_device_ip else "unknown")
                self._set_status(_T("downloaded_n_of_m").replace("{s}", str(success_count)).replace("{t}", str(total)))
                messagebox.showinfo(
                    _T("success_title"),
                    _T("downloaded_n_of_m").replace("{s}", str(success_count)).replace("{t}", str(total))
                    + f"\n\n{_T('folder_label')}{rec_dir}",
                )

            self.after(0, update_ui)

        self._run_async(_T("archiving_all"), task, failure_text=_T("archive_failed_msg"))

    def _safe_status_summary(self, data):
        if not isinstance(data, dict):
            return "Đã kết nối thiết bị."

        allowed = []
        for key in ("ok", "status", "sd", "mounted", "file_count", "total_bytes", "used_bytes", "free_bytes"):
            if key in data:
                allowed.append(f"{key}: {data.get(key)}")

        if allowed:
            return "Đã kết nối thiết bị.\n" + "\n".join(allowed)

        return "Đã kết nối thiết bị. Thông tin nhạy cảm đã được ẩn."

    def _require_connected(self):
        if self.data_server is not None and self.data_server.is_running:
            return True
        if self.connected:
            return True
        messagebox.showwarning(
            _T("not_ready_title"),
            _T("server_not_running_msg"),
        )
        return False

    def _init_hotspot_labels(self):
        if wifi_hotspot is None:
            self.hotspot_status_var.set("Module hash blockchain không khả dụng.")
            return
        self.hotspot_ssid = wifi_hotspot.derive_blockchain_hash()
        self.hotspot_password = wifi_hotspot.DEFAULT_HOTSPOT_PASSWORD
        self.hotspot_ssid_var.set(self.hotspot_ssid)

    def _init_network_labels(self):
        if network_config is None:
            self.network_host_var.set("Module mạng không khả dụng.")
            self.network_device_var.set("")
            self.network_api_var.set("")
            return
        self.network_host_var.set(
            f"Trên PC này: {network_config.local_service_url()} | "
            f"Hotspot: {network_config.HOST_IP} / {network_config.SUBNET_MASK}"
        )
        self.network_device_var.set(
            f"Thiết bị khác gửi tới: {network_config.host_service_url()} | "
            f"Socket TCP :{network_config.DEVICE_SOCKET_PORT}"
        )
        self.network_api_var.set(
            f"API kết nối: {network_config.host_service_url()}/api/device/connection | "
            f"API đăng ký: {network_config.registry_api_url()}/api/device/register"
        )

    def _ensure_connection_store(self):
        if self.connection_store is not None or DeviceConnectionStore is None:
            return
        self.connection_store = DeviceConnectionStore(
            on_change=lambda: self.after(0, self.refresh_device_connections),
        )

    def _start_data_server(self):
        if DeviceDataServer is None:
            return
        self._ensure_connection_store()
        app_key = self._decode(_HIDDEN_KEY).strip()
        self.data_server = DeviceDataServer(
            app_key=app_key,
            connections=self.connection_store,
            on_change=lambda: self.after(0, self.refresh_files),
            rec_dir=self._download_dir,
        )
        ok, msg = self.data_server.start()
        if ok:
            self._set_status(_T("http_server_ready"))
        else:
            self._set_status(f"{_T('server_start_failed')}{msg}")

    def _refresh_wifi_adapter_label(self):
        if network_config is None:
            self.network_wifi_var.set("Adapter Wi-Fi: module mạng không khả dụng.")
            return

        def task():
            ok, text = network_config.get_machine_wifi_info()

            def update_ui():
                if ok:
                    self.network_wifi_var.set(text)
                else:
                    self.network_wifi_var.set(f"Adapter Wi-Fi: {text}")

            self.after(0, update_ui)

        threading.Thread(target=task, daemon=True).start()

    def refresh_network_display(self):
        self._init_hotspot_labels()
        self.refresh_registered_devices()

    def _start_registry_api(self):
        if DeviceRegistryServer is None:
            return
        self._ensure_connection_store()
        self.registry_server = DeviceRegistryServer(
            connections=self.connection_store,
            on_change=lambda: self.after(0, self.refresh_registered_devices),
        )
        ok, msg = self.registry_server.start()
        if ok:
            self._set_status(_T("registry_ready"))
            self.refresh_device_connections()
        else:
            self._set_status(_T("registry_unavailable"))

    def _set_hotspot_status(self, msg):
        text = str(msg or "")
        if "NO_CONNECTION_PROFILE" in text:
            text = _T("no_conn_profile")
        if "CONFLICT_NO_ETHERNET" in text or "chip Wi-Fi" in text:
            return
        if "CONFLICT_USE_ETHERNET" in text or "Share from Ethernet" in text:
            return
        for token in ("Wi-Fi", "WiFi", "WLAN", "hotspot", "Hotspot", "SSID", "ssid"):
            text = text.replace(token, "")
        self.hotspot_status_var.set(text.strip() or _T("node_inactive"))

    def apply_network(self):
        if network_config is None:
            messagebox.showerror(_T("network_error_title"), _T("network_module_unavail"))
            return

        def task():
            ok, msg = network_config.configure_hotspot_network()

            def update_ui():
                self._set_status(_T("apply_network_success") if ok else _T("apply_network_failed"))
                self.refresh_network_display()
                if not ok:
                    messagebox.showwarning(_T("network_error_title"), msg)

            self.after(0, update_ui)

        self._run_async(_T("applying_network"), task)

    def refresh_registered_devices(self):
        panel = getattr(self, "_reg_panel", None)
        if panel is None:
            return
        for widget in panel.winfo_children():
            widget.destroy()
        if self.registry_server is None:
            return

        entries = self.registry_server.registry.list_devices()
        if hasattr(self, "_reg_count_var"):
            self._reg_count_var.set(str(len(entries)))

        for entry in entries:
            seen = entry.get("last_seen", 0)
            seen_text = (
                datetime.datetime.fromtimestamp(seen).strftime("%Y-%m-%d %H:%M:%S")
                if seen else "—"
            )
            device_id = entry.get("device_id") or "—"
            mac = entry.get("mac") or "—"
            is_online = self.registry_server.registry.is_online(entry)
            status_text = "Online" if is_online else "Offline"
            status_color = _THEME["success"] if is_online else _THEME.get("error", "#FF3B30")

            row = tk.Frame(panel, bg=_THEME["surface"])
            row.pack(fill=tk.X, padx=14, pady=(6, 0))

            top = tk.Frame(row, bg=_THEME["surface"])
            top.pack(fill=tk.X)
            tk.Label(
                top, text=device_id,
                font=self._font_ui_bold,
                bg=_THEME["surface"], fg=_THEME["text"],
                anchor=tk.W,
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)
            online_dot = tk.Canvas(top, width=8, height=8,
                                   bg=_THEME["surface"], highlightthickness=0, bd=0)
            online_dot.create_oval(0, 0, 8, 8, fill=status_color, outline="")
            online_dot.pack(side=tk.RIGHT, padx=(4, 0), pady=4)
            tk.Label(
                top, text=status_text,
                font=self._font_sub,
                bg=_THEME["surface"], fg=status_color,
            ).pack(side=tk.RIGHT)

            bottom = tk.Frame(row, bg=_THEME["surface"])
            bottom.pack(fill=tk.X)
            tk.Label(
                bottom, text=mac,
                font=self._font_mono_sm,
                bg=_THEME["surface"], fg=_THEME["text_muted"],
                anchor=tk.W,
            ).pack(side=tk.LEFT)
            tk.Label(
                bottom, text=seen_text,
                font=self._font_mono_sm,
                bg=_THEME["surface"], fg=_THEME["text_muted"],
                anchor=tk.E,
            ).pack(side=tk.RIGHT)

            tk.Frame(panel, bg=_THEME["border"], height=1).pack(
                fill=tk.X, padx=14, pady=(6, 0)
            )
        self._update_header_online_state()

    def auto_open_firewall_ports(self):
        if firewall_config is None:
            return
        if not firewall_config.is_windows():
            return

        def task():
            firewall_config.ensure_app_firewall_rules()

        threading.Thread(target=task, daemon=True).start()

    def auto_setup_hotspot(self):
        if wifi_hotspot is None:
            self._set_hotspot_status(_T("blockchain_hash_unavail"))
            return
        if not wifi_hotspot.is_windows():
            self._set_hotspot_status(_T("windows_only"))
            return

        def task():
            ok, msg = wifi_hotspot.configure_and_start_hotspot(
                self.hotspot_ssid,
                self.hotspot_password,
            )

            def update_ui():
                self._set_hotspot_status(msg)
                self._node_active = bool(ok)
                self._update_header_online_state()
                if ok:
                    self._set_status(_T("blockchain_activated"))
                    self.refresh_network_display()
                else:
                    detail = str(msg or "")
                    if "CONFLICT_NO_ETHERNET" in detail or "chip Wi-Fi" in detail:
                        self._set_status(_T("activation_failed"))
                    elif len(detail) > 120:
                        self._set_status(detail[:200])
                    else:
                        self._set_status(_T("activation_failed"))

            self.after(0, update_ui)

        self._run_async(_T("activating"), task, failure_text=_T("activation_failed"))

    def setup_hotspot(self):
        if wifi_hotspot is None:
            messagebox.showerror(_T("error_title"), _T("blockchain_hash_unavail"))
            return
        self.auto_setup_hotspot()

    # ===================== API actions =====================
    def check_status(self):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return

        if self.busy:
            self._set_status(_T("busy_wait"))
            return

        def task():
            self.busy = True
            self._api_loading_begin()
            try:
                self.after(0, lambda: self._set_status(_T("checking_server")))
                self.after(
                    0,
                    lambda: self._set_loading_caption(_T("checking_server")),
                )
                if self.data_server is None or not self.data_server.is_running:
                    raise requests.exceptions.ConnectionError("data server not running")
                r = self._http_get(
                    self._api_url("status"),
                    headers=self._headers(),
                    timeout=self._request_timeout(),
                )
                r.raise_for_status()
                try:
                    data = r.json()
                except Exception:
                    data = {}
                host = network_config.HOST_IP if network_config else "127.0.0.1"
                port = network_config.DEVICE_SERVICE_PORT if network_config else 8765

                def update_ok():
                    self._set_connection_state(True, self._safe_status_summary(data))
                    self._set_status(
                        _T("server_ready_status").replace("{port}", str(port)).replace("{host}", str(host)).replace("{port2}", str(port))
                    )
                    self.refresh_files()

                self.after(0, update_ok)
            except requests.exceptions.RequestException:
                hint = ""
                if network_config is not None:
                    hint = network_config.diagnose_device_connectivity()

                def update_fail():
                    self._set_connection_state(False, hint)
                    self._set_status(_T("server_not_ready"))

                self.after(0, update_fail)
            finally:
                self._api_loading_end()
                self.busy = False

        threading.Thread(target=task, daemon=True).start()

    def refresh_files(self):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return
        self._active_device_ip = None
        self._active_device_port = None

        def task():
            r = self._http_get(
                self._api_url("list"),
                headers=self._headers(),
                timeout=self._request_timeout()
            )
            r.raise_for_status()

            data = r.json()
            files = data.get("files", [])

            def update_ui():
                self._set_connection_state(True)
                self._populate_files_tree(
                    files,
                    _T("refreshed_files").replace("{n}", str(len(files))),
                    safe_info=f"{_T('connected_device')}\n{len(files)} file",
                )

            self.after(0, update_ui)

        self._run_async(
            _T("refreshing_files"),
            task,
            failure_text=_T("refresh_failed"),
        )

    def upload_one_file(self):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return
        if not self._require_connected():
            return

        file_path = filedialog.askopenfilename(title="Chọn 1 file để upload")
        if not file_path:
            return

        def task():
            path = Path(file_path)
            with open(path, "rb") as f:
                files = {"file": (path.name, f, "application/octet-stream")}
                if self._active_device_ip:
                    upload_url = self._device_service_url(
                        self._active_device_ip,
                        "/api/upload",
                        port=self._active_device_port,
                    )
                else:
                    upload_url = self._api_url("upload_one")
                r = self._http_post(
                    upload_url,
                    headers=self._headers(),
                    files=files,
                    timeout=300
                )
            r.raise_for_status()

            self.after(0, lambda: self._set_safe_info(f"{_T('upload_one_done_info')}{path.name}"))
            self.after(0, lambda: self._set_status(_T("upload_success_status")))
            self.after(0, self.refresh_files_view)

        self._run_async(_T("uploading"), task, failure_text=_T("upload_failed_status"))

    def upload_many_files(self):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return
        if not self._require_connected():
            return

        file_paths = filedialog.askopenfilenames(title="Chọn nhiều file để upload")
        if not file_paths:
            return

        def task():
            with ExitStack() as stack:
                multipart_files = []
                for fp in file_paths:
                    path = Path(fp)
                    f = stack.enter_context(open(path, "rb"))
                    multipart_files.append(("files", (path.name, f, "application/octet-stream")))

                if self._active_device_ip:
                    upload_url = self._device_service_url(
                        self._active_device_ip,
                        "/api/upload-all",
                        port=self._active_device_port,
                    )
                else:
                    upload_url = self._api_url("upload_many")
                r = self._http_post(
                    upload_url,
                    headers=self._headers(),
                    files=multipart_files,
                    timeout=600
                )
            r.raise_for_status()

            self.after(0, lambda: self._set_safe_info(_T("upload_done_info").replace("{n}", str(len(file_paths)))))
            self.after(0, lambda: self._set_status(_T("upload_success_status")))
            self.after(0, self.refresh_files_view)

        self._run_async(_T("uploading_many"), task, failure_text=_T("upload_failed_status"))

    def download_selected(self):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return
        if not self._require_connected():
            return

        name = self._selected_file_name()
        if not name:
            return

        def task():
            if self._active_device_ip:
                download_url = self._device_service_url(
                    self._active_device_ip,
                    "/api/download",
                    port=self._active_device_port,
                )
            else:
                download_url = self._api_url("download")

            dest = self._download_bin_only(
                download_url,
                name,
                dest_dir=self._device_rec_dir(self._device_connection_display(self._active_device_ip) if self._active_device_ip else "unknown"),
                on_status=self._set_status,
            )
            self.after(0, lambda: self._set_safe_info(f"{_T('downloaded_file_info')}{dest.name}"))
            self.after(0, lambda: self._set_status(_T("downloaded_file").replace("{name}", name).replace("{folder}", dest.parent.name)))

        self._run_async(
            _T("downloading_file"),
            task,
            failure_text=_T("download_failed_one"),
        )

    def _open_decrypt_window(self):
        """Mở cửa sổ giải mã .bin — bản gọn v2: không mất OVERALL/Sẵn sàng, căn giữa."""
        if decrypt_bin_bytes is None or _phtm_load_private_key is None:
            messagebox.showerror(_T("missing_module"), _T("phantom_bundle_missing"))
            return
        if not _CRYPTO_OK:
            messagebox.showerror(_T("missing_lib"), _T("install_cryptography"))
            return

        output_dir = Path(self._download_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        win = tk.Toplevel(self)
        win.title(_T("decrypt_window_title"))
        win.configure(bg="#f3f6fb")

        w = 900
        h = 640

        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()

        x = (screen_w - w) // 2
        y = (screen_h - h) // 2

        win.geometry(f"{w}x{h}+{x}+{y}")
        win.minsize(850, 620)
        win.resizable(True, True)

        try:
            win.transient(self)
        except tk.TclError:
            pass

        # ===== Root layout: header / content / footer =====
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(1, weight=1)

        header = tk.Frame(win, bg=_THEME["header"], height=44)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        tk.Label(
            header,
            text=_T("decrypt_window_heading"),
            font=(self._font_ui[0], 13, "bold"),
            bg=_THEME["header"],
            fg="#ffffff",
            anchor=tk.W,
        ).pack(side=tk.LEFT, padx=(20, 10), pady=0)
        tk.Label(
            header,
            text="",
            font=self._font_sub,
            bg=_THEME["header"],
            fg="#cbd5e1",
            anchor=tk.W,
        ).pack(side=tk.LEFT, padx=(0, 20), pady=(4, 0))

        content = tk.Frame(win, bg="#f3f6fb")
        content.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        content.grid_columnconfigure(0, minsize=280, weight=0)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(
            content,
            bg="#ffffff",
            width=280,
            highlightthickness=1,
            highlightbackground=_THEME["border"],
        )
        # Sidebar không kéo dài theo chiều cao cửa sổ để không có khoảng trắng dưới nút GIẢI MÃ
        sidebar.grid(row=0, column=0, sticky="nw", padx=(0, 8))
        sidebar.grid_propagate(True)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(0, weight=0)
        sidebar.grid_rowconfigure(1, weight=0)

        right = tk.Frame(
            content,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground=_THEME["border"],
        )
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)

        footer = tk.Frame(win, bg=_THEME["status_bar"], height=30)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_propagate(False)
        tk.Label(
            footer,
            text="PHANTOM v1.2.0",
            font=self._font_sub,
            bg=_THEME["status_bar"],
            fg=_THEME["text_muted"],
        ).pack(side=tk.LEFT, padx=14)

        # ===== State =====
        _file_paths = {}
        _key_path_real = [""]
        progress_var = tk.DoubleVar(value=0)
        key_path_var = tk.StringVar(value=_T("no_key_selected"))
        _running = [False]

        def _label(parent, text):
            return tk.Label(
                parent,
                text=text.upper(),
                font=(self._font_ui[0], 9, "bold"),
                bg="#ffffff",
                fg=_THEME["text_muted"],
                anchor=tk.W,
            )

        def _button(parent, text, command, bg, fg="#ffffff"):
            return tk.Button(
                parent,
                text=text,
                command=command,
                font=self._font_ui_bold,
                bg=bg,
                fg=fg,
                activebackground=bg,
                activeforeground=fg,
                relief="flat",
                bd=0,
                cursor="hand2",
                padx=10,
                pady=7,
            )

        # ===== Sidebar body (scroll-free, compact) =====
        side_body = tk.Frame(sidebar, bg="#ffffff")
        side_body.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 8))
        side_body.grid_columnconfigure(0, weight=1)
        side_body.grid_rowconfigure(1, weight=1)

        _label(side_body, _T("input_files_label")).grid(row=0, column=0, sticky="ew", pady=(0, 6))

        file_card = tk.Frame(side_body, bg=_THEME["mono_bg"], highlightthickness=1, highlightbackground=_THEME["border"])
        file_card.grid(row=1, column=0, sticky="nsew")
        file_card.configure(height=180)
        file_card.grid_propagate(False)
        file_card.grid_columnconfigure(0, weight=1)
        file_card.grid_rowconfigure(0, weight=1)

        file_list = tk.Listbox(
            file_card,
            selectmode=tk.MULTIPLE,
            activestyle="none",
            font=self._font_ui,
            bg=_THEME["mono_bg"],
            fg=_THEME["text"],
            bd=0,
            highlightthickness=0,
        )
        file_scroll = ttk.Scrollbar(file_card, orient=tk.VERTICAL, command=file_list.yview)
        file_list.configure(yscrollcommand=file_scroll.set)
        file_list.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        file_scroll.grid(row=0, column=1, sticky="ns", pady=8)

        empty_hint = tk.Label(
            file_card,
            text=_T("no_file_hint"),
            font=self._font_ui,
            bg=_THEME["mono_bg"],
            fg=_THEME["text_muted"],
            justify=tk.CENTER,
        )
        empty_hint.place(relx=0.5, rely=0.5, anchor="center")

        def _refresh_list_ui():
            file_list.delete(0, tk.END)
            for full_path in _file_paths:
                file_list.insert(tk.END, Path(full_path).name)
            if _file_paths:
                empty_hint.place_forget()
                file_list.selection_set(0, tk.END)
            else:
                empty_hint.place(relx=0.5, rely=0.5, anchor="center")

        def _browse_files():
            paths = filedialog.askopenfilenames(
                title="Chọn file .bin cần giải mã",
                filetypes=[("Phantom binary", "*.bin"), ("All files", "*.*")],
                parent=win,
            )
            if not paths:
                return
            for path in paths:
                _file_paths[path] = True
            _refresh_list_ui()

        def _clear_list():
            _file_paths.clear()
            _refresh_list_ui()

        file_btns = tk.Frame(side_body, bg="#ffffff")
        file_btns.grid(row=2, column=0, sticky="ew", pady=(5, 8))
        file_btns.grid_columnconfigure(0, weight=1)
        file_btns.grid_columnconfigure(1, weight=1)
        _button(file_btns, "Browse .bin", _browse_files, "#6e6e73").grid(row=0, column=0, sticky="ew", padx=(0, 5))
        _button(file_btns, _T("clear_list_btn"), _clear_list, "#e5e7eb", _THEME["text"]).grid(row=0, column=1, sticky="ew", padx=(5, 0))

        _label(side_body, _T("key_file_label")).grid(row=3, column=0, sticky="ew", pady=(0, 6))
        key_box = tk.Frame(side_body, bg=_THEME["mono_bg"], highlightthickness=1, highlightbackground=_THEME["border"], height=40)
        key_box.grid(row=4, column=0, sticky="ew")
        key_box.grid_propagate(False)
        tk.Label(key_box, textvariable=key_path_var, font=self._font_ui, bg=_THEME["mono_bg"], fg=_THEME["text_muted"], anchor=tk.W).pack(fill=tk.X, expand=True, padx=12)

        def _pick_key():
            path = filedialog.askopenfilename(
                title="Chọn private.key",
                filetypes=[("Key file", "*.key"), ("All files", "*.*")],
                parent=win,
            )
            if not path:
                return
            try:
                _phtm_load_private_key(path)
            except Exception as exc:
                messagebox.showerror(_T("key_error_title"), str(exc), parent=win)
                return
            _key_path_real[0] = path
            key_path_var.set(Path(path).name)

        _button(side_body, "Load Key", _pick_key, "#6e6e73").grid(row=5, column=0, sticky="ew", pady=(5, 8))

        progress_box = tk.Frame(side_body, bg="#ffffff")
        progress_box.grid(row=6, column=0, sticky="ew", pady=(0, 0))
        progress_box.grid_columnconfigure(0, weight=1)
        tk.Label(progress_box, text="OVERALL", font=(self._font_ui[0], 9, "bold"), bg="#ffffff", fg=_THEME["text_muted"]).grid(row=0, column=0, sticky="w")
        pct_lbl = tk.Label(progress_box, text="0 %", font=self._font_ui_bold, bg="#ffffff", fg=_THEME["text"])
        pct_lbl.grid(row=0, column=1, sticky="e")
        ttk.Progressbar(progress_box, variable=progress_var, maximum=100).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 4))
        status_lbl = tk.Label(progress_box, text=_T("decrypt_ready"), font=self._font_ui, bg="#ffffff", fg=_THEME["success"], anchor=tk.W)
        status_lbl.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 0))

        def _open_output():
            import subprocess
            try:
                os.startfile(str(output_dir))
            except Exception:
                try:
                    subprocess.Popen(["explorer", str(output_dir)])
                except Exception:
                    pass

        # ===== Action buttons: đặt ngay dưới trạng thái, không để khoảng trắng =====
        action_bar = tk.Frame(side_body, bg="#ffffff")
        action_bar.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        action_bar.grid_columnconfigure(0, weight=1)

        open_output_btn = _button(
            action_bar,
            _T("open_output_btn"),
            _open_output,
            "#e5e7eb",
            _THEME["text"],
        )
        open_output_btn.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        # ===== 3 Layer Cards =====
        layer_outer = tk.Frame(right, bg="#f3f6fb")
        layer_outer.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        for _ci in range(3):
            layer_outer.grid_columnconfigure(_ci, weight=1, uniform="layers")

        _DEC_LAYERS = [
            ("L1", "ChaCha20", "ChaCha20-Poly1305", "Decrypt Layer 1", "#2563eb", "#eff6ff"),
            ("L2", "HMAC",     "HMAC-SHA256",        "Decrypt Layer 2", "#2563eb", "#eff6ff"),
            ("L3", "AES",      "AES-256-GCM",         "Decrypt Layer 3", "#2563eb", "#eff6ff"),
        ]
        _layer_data = []
        for _ci, (_lnum, _lshort, _algo, _ldesc, _color, _tint) in enumerate(_DEC_LAYERS):
            _card = tk.Frame(layer_outer, bg="#ffffff",
                             highlightthickness=2,
                             highlightbackground=_THEME["border"])
            _card.grid(row=0, column=_ci, sticky="nsew",
                       padx=(0 if _ci == 0 else 6, 0))

            _top = tk.Frame(_card, bg="#ffffff")
            _top.pack(fill=tk.X, padx=8, pady=(8, 2))
            tk.Label(_top, text=_lnum, font=(self._font_mono_sm[0], 9, "bold"),
                     bg=_tint, fg=_color, padx=6, pady=2).pack(side=tk.LEFT, padx=(0, 3))
            tk.Label(_top, text=_lshort, font=(self._font_mono_sm[0], 9, "bold"),
                     bg=_tint, fg=_color, padx=6, pady=2).pack(side=tk.LEFT)
            _dot = tk.Label(_top, text="●", font=self._font_sub,
                            bg="#ffffff", fg=_THEME["text_muted"])
            _dot.pack(side=tk.RIGHT)

            _title_l = tk.Label(_card, text=_algo,
                                font=(self._font_ui[0], 11, "bold"),
                                bg="#ffffff", fg=_THEME["text"], anchor=tk.W)
            _title_l.pack(anchor=tk.W, padx=8, pady=(2, 1))
            _desc_l = tk.Label(_card, text=_ldesc, font=self._font_sub,
                               bg="#ffffff", fg=_THEME["text_muted"], anchor=tk.W)
            _desc_l.pack(anchor=tk.W, padx=8, pady=(0, 4))

            _hf = tk.Frame(_card, bg=_THEME["mono_bg"])
            _hf.pack(fill=tk.X, padx=8, pady=(0, 4))
            _hash_l = tk.Label(_hf, text="HASH —",
                               font=(self._font_mono_sm[0], 9),
                               bg=_THEME["mono_bg"], fg=_THEME["text_muted"],
                               anchor=tk.W, justify=tk.LEFT)
            _hash_l.pack(fill=tk.X, padx=6, pady=3)

            _bar_v = tk.DoubleVar(value=0)
            _bar = ttk.Progressbar(_card, variable=_bar_v, maximum=100)
            _bar.pack(fill=tk.X, padx=8, pady=(0, 2))

            _pct_l = tk.Label(_card, text="0 %",
                              font=(self._font_ui[0], 14, "bold"),
                              bg="#ffffff", fg=_color, anchor=tk.E)
            _pct_l.pack(fill=tk.X, padx=8, pady=(0, 6))

            _layer_data.append((_card, _hash_l, _bar_v, _pct_l, _dot, _color))

        def _reset_layers_dec():
            for _c, _hl, _bv, _pl, _dl, _col in _layer_data:
                _bv.set(0)
                _pl.configure(text="0 %", fg=_col)
                _dl.configure(text="●", fg=_THEME["text_muted"])
                _hl.configure(text="HASH —", fg=_THEME["text_muted"])
                _c.configure(highlightbackground=_THEME["border"])

        def _animate_layer_dec(idx, hash_hex, duration_ms, on_done):
            _c, _hl, _bv, _pl, _dl, _col = _layer_data[idx]
            steps = 40
            interval = max(18, duration_ms // steps)
            _c.configure(highlightbackground=_col)
            _dl.configure(text="●", fg=_col)
            _hl.configure(text=f"HASH  {hash_hex[:12]}", fg=_THEME["text"])

            def _tick(step=0):
                if step > steps:
                    _bv.set(100)
                    _pl.configure(text="100 %")
                    _dl.configure(text="✔", fg=_col)
                    _hl.configure(text=f"HASH  {hash_hex[:24]}", fg=_col)
                    on_done()
                    return
                frac = step / steps
                _bv.set(frac * 100)
                _pl.configure(text=f"{int(frac * 100)} %")
                win.after(interval, lambda: _tick(step + 1))

            win.after(0, _tick)

        # ===== Log panel =====
        log_title = tk.Frame(right, bg="#ffffff", height=40)
        log_title.grid(row=1, column=0, sticky="ew")
        log_title.grid_propagate(False)
        tk.Label(log_title, text="DECRYPT LOG", font=(self._font_ui[0], 11, "bold"), bg="#ffffff", fg=_THEME["text"], anchor=tk.W).pack(side=tk.LEFT, padx=12)
        tk.Frame(right, bg=_THEME["border"], height=1).grid(row=2, column=0, sticky="ew")

        log_wrap = tk.Frame(right, bg="#ffffff")
        log_wrap.grid(row=3, column=0, sticky="nsew", padx=10, pady=10)
        log_wrap.grid_columnconfigure(0, weight=1)
        log_wrap.grid_rowconfigure(0, weight=1)
        log_text = tk.Text(
            log_wrap,
            font=self._font_mono_sm,
            bg=_THEME["mono_bg"],
            fg=_THEME["text"],
            relief="flat",
            bd=0,
            wrap=tk.WORD,
            state=tk.DISABLED,
            padx=12,
            pady=10,
        )
        log_scroll = ttk.Scrollbar(log_wrap, orient=tk.VERTICAL, command=log_text.yview)
        log_text.configure(yscrollcommand=log_scroll.set)
        log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")
        log_text.tag_configure("ok", foreground=_THEME["success"])
        log_text.tag_configure("err", foreground=_THEME["danger"])
        log_text.tag_configure("hdr", foreground=_THEME["primary"], font=self._font_ui_bold)

        def _log(msg, tag=None):
            def _do():
                log_text.configure(state=tk.NORMAL)
                log_text.insert(tk.END, msg + "\n", tag or "")
                log_text.see(tk.END)
                log_text.configure(state=tk.DISABLED)
            win.after(0, _do)

        def _set_status(msg, color=None):
            win.after(0, lambda: status_lbl.configure(text=msg, fg=color or _THEME["primary"]))

        def _set_progress(pct):
            win.after(0, lambda: (progress_var.set(pct), pct_lbl.configure(text=f"{int(pct)} %")))

        def _run_decrypt():
            if _running[0]:
                return
            selected_indices = file_list.curselection()
            selected = [list(_file_paths.keys())[i] for i in selected_indices]
            if not selected:
                messagebox.showwarning(_T("decrypt_select_title"), _T("decrypt_select_msg"), parent=win)
                return
            if not _key_path_real[0]:
                messagebox.showwarning(_T("no_key_title"), _T("no_key_msg"), parent=win)
                return

            run_btn.configure(state=tk.DISABLED, bg="#94a3b8")
            _running[0] = True
            _set_progress(0)

            def worker():
                import hashlib as _hl
                total = len(selected)
                success = 0
                _log(_T("decrypt_begin").replace("{n}", str(total)), "hdr")
                try:
                    _, private_key_raw = _phtm_load_private_key(_key_path_real[0])
                except Exception as exc:
                    _log(f"{_T('key_read_error')}{exc}", "err")
                    _set_status(_T("key_error_status"), _THEME["danger"])
                    win.after(0, lambda: run_btn.configure(state=tk.NORMAL, bg=_THEME["primary"]))
                    _running[0] = False
                    return

                for i, full_path in enumerate(selected):
                    bin_path = Path(full_path)
                    _log(f"\n[{i + 1}/{total}] {bin_path.name}", "hdr")
                    win.after(0, _reset_layers_dec)
                    try:
                        bin_bytes = bin_path.read_bytes()
                        _set_status(f"{_T('decrypting_file')}{bin_path.name}...")
                        saved = decrypt_bin_bytes(bin_bytes, private_key_raw, bin_path.parent, bin_path.stem)

                        _hashes = [
                            _hl.sha256(bin_bytes[:256]).hexdigest(),
                            _hl.sha256(bin_bytes[len(bin_bytes)//4:len(bin_bytes)//4+256]).hexdigest(),
                            _hl.sha256(bin_bytes[-256:]).hexdigest(),
                        ]
                        _anim_done = threading.Event()
                        def _run_anim(hashes=_hashes, evt=_anim_done):
                            def _l2(h=hashes):
                                def _l3(h=h):
                                    def _fin():
                                        evt.set()
                                    _animate_layer_dec(2, h[2], 500, _fin)
                                _animate_layer_dec(1, h[1], 500, _l3)
                            _animate_layer_dec(0, hashes[0], 500, _l2)
                        win.after(0, _run_anim)
                        _anim_done.wait(timeout=6)

                        for saved_path in saved:
                            _log(f"  ✓ {Path(saved_path).name}", "ok")
                        try:
                            bin_path.unlink()
                            _log(f"  đã xóa: {bin_path.name}")
                            _file_paths.pop(full_path, None)
                        except OSError:
                            pass
                        success += 1
                    except Exception as exc:
                        win.after(0, _reset_layers_dec)
                        _log(f"  ✗ Lỗi: {exc}", "err")
                    _set_progress(self._progress_percent(i + 1, total))

                _log(f"\n{_T('decrypt_done').replace('{s}', str(success)).replace('{t}', str(total))}", "hdr")
                if success:
                    _set_status(_T("decrypt_success_status").replace("{s}", str(success)).replace("{t}", str(total)), _THEME["success"])
                    win.after(0, self._refresh_local_files_tree)
                    if self._audio_player is not None:
                        win.after(0, lambda: self._audio_player.load_folder(str(output_dir)))
                else:
                    _set_status(_T("decrypt_failed_status"), _THEME["danger"])
                win.after(0, _refresh_list_ui)
                win.after(0, lambda: run_btn.configure(state=tk.NORMAL, bg=_THEME["primary"]))
                _running[0] = False

            threading.Thread(target=worker, daemon=True).start()

        run_btn = _button(
            action_bar,
            _T("decrypt_run_btn"),
            _run_decrypt,
            _THEME["primary"],
        )
        run_btn.configure(
            font=(self._font_ui[0], 12, "bold"),
            pady=8,
            activebackground=_THEME["primary_hover"],
        )
        run_btn.grid(row=1, column=0, sticky="ew", pady=(0, 0))

        self._center_toplevel_on_screen(win, 900, 640, parent=self)
        win.lift(self)
        win.focus_force()

    def _load_audio_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục chứa file WAV")
        if not folder:
            return
        if self._audio_player is not None:
            self._audio_player.load_folder(folder)
        self._set_status(f"{_T('audio_folder_opened')}{Path(folder).name}.")

    def delete_selected(self):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return
        if not self._require_connected():
            return

        name = self._selected_file_name()
        if not name:
            return

        ok = messagebox.askyesno(_T("confirm_delete_title"), f"{_T('confirm_delete_msg')}{name}")
        if not ok:
            return

        def task():
            if self._active_device_ip:
                delete_url = self._device_service_url(
                    self._active_device_ip,
                    "/api/delete",
                    port=self._active_device_port,
                )
            else:
                delete_url = self._api_url("delete_one")
            r = self._http_delete(
                delete_url,
                headers=self._headers(),
                params={"name": name},
                timeout=self._request_timeout()
            )
            r.raise_for_status()

            self.after(0, lambda: self._set_safe_info(f"{_T('deleted_file_info')}{name}"))
            self.after(0, lambda: self._set_status(_T("delete_success")))
            self.after(0, self.refresh_files_view)

        self._run_async(_T("deleting_file"), task, failure_text=_T("delete_failed"))

    def delete_all(self):
        if requests is None:
            messagebox.showerror(_T("missing_lib"), _T("install_requests"))
            return
        if not self._require_connected():
            return

        confirm = simpledialog.askstring(_T("confirm_delete_all_title"), _T("confirm_delete_all_msg"))
        if confirm != "DELETE":
            self._set_status(_T("cancelled_delete_all"))
            return

        def task():
            if self._active_device_ip:
                delete_url = self._device_service_url(
                    self._active_device_ip,
                    "/api/delete-all",
                    port=self._active_device_port,
                )
            else:
                delete_url = self._api_url("delete_all")
            r = self._http_delete(
                delete_url,
                headers=self._headers(),
                timeout=120
            )
            r.raise_for_status()

            self.after(0, lambda: self._set_safe_info(_T("deleted_all_info")))
            self.after(0, lambda: self._set_status(_T("delete_all_success")))
            self.after(0, self.refresh_files_view)

        self._run_async(_T("deleting_all"), task, failure_text=_T("delete_all_failed"))


if __name__ == "__main__":
    _setup_http_logging()
    _setup_decode_logging()
    app = AutoPrivateSDManagerApp()
    app.mainloop()

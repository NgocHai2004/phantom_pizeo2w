#!/usr/bin/env python3
"""
Phantom Serial Manager — giao tiep Pi Zero qua COM port (CDC-ACM)
Yeu cau: pip install pyserial
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import threading, json, base64, os
from datetime import datetime

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyserial"])
    import serial
    import serial.tools.list_ports


class _CdcSerial(serial.Serial):
    """Bo qua SetCommState loi 31 tren Windows CDC-ACM."""
    def _reconfigure_port(self, *args, **kwargs):
        try:
            super()._reconfigure_port(*args, **kwargs)
        except serial.SerialException:
            pass


class SerialClient:
    def __init__(self):
        self._port: _CdcSerial | None = None
        self._lock = threading.Lock()

    def connect(self, port: str, baud: int = 115200) -> tuple[bool, str]:
        try:
            s = _CdcSerial()
            s.port = port; s.baudrate = baud
            s.timeout = 10; s.write_timeout = 5
            s.rtscts = False; s.dsrdtr = False; s.xonxoff = False
            s.open()
            with self._lock:
                self._port = s
            return True, ""
        except Exception as e:
            return False, str(e)

    def disconnect(self):
        with self._lock:
            if self._port:
                try: self._port.close()
                except Exception: pass
                self._port = None

    def is_connected(self) -> bool:
        with self._lock:
            return self._port is not None and self._port.is_open

    # Cac lenh download file lon can timeout lau hon
    _BIG_CMD = {"download", "download_all", "download_selected"}

    def send(self, cmd: dict) -> dict:
        with self._lock:
            if not self._port or not self._port.is_open:
                return {"ok": False, "error": "not connected"}
            try:
                # Dong timeout theo loai lenh
                op = cmd.get("cmd", "")
                self._port.timeout = 120 if op in self._BIG_CMD else 15
                raw = (json.dumps(cmd, ensure_ascii=False) + "\n").encode("utf-8")
                self._port.write(raw)
                self._port.flush()
                # Doc tung byte cho den khi gap '\n' de tranh cut giua JSON lon
                buf = b""
                while True:
                    ch = self._port.read(1)
                    if not ch:
                        if buf:
                            break  # het timeout nhung co data, thu parse
                        return {"ok": False, "error": "timeout — Pi khong phan hoi"}
                    buf += ch
                    if ch == b"\n":
                        break
                return json.loads(buf.decode("utf-8", errors="replace"))
            except Exception as e:
                return {"ok": False, "error": str(e)}


client = SerialClient()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Phantom Serial Manager")
        self.geometry("860x640")
        self.resizable(True, True)
        self._build_top()
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._build_status(nb)
        self._build_files(nb)
        self._build_config(nb)
        self._build_pubkey(nb)
        self._build_log()

    # ── Top bar ────────────────────────────────────────────────────────────────
    def _build_top(self):
        bar = tk.Frame(self, bd=1, relief="groove")
        bar.pack(fill="x", padx=8, pady=6)
        tk.Label(bar, text="COM Port:").pack(side="left")
        self._var_port = tk.StringVar()
        self._cb_port = ttk.Combobox(bar, textvariable=self._var_port, width=10)
        self._cb_port.pack(side="left", padx=4)
        tk.Button(bar, text="⟳", command=self._refresh_ports, width=2).pack(side="left")
        tk.Label(bar, text="Baud:").pack(side="left", padx=(8, 2))
        self._var_baud = tk.StringVar(value="115200")
        ttk.Combobox(bar, textvariable=self._var_baud,
                     values=["9600","57600","115200","460800"], width=8).pack(side="left")
        self._btn_con = tk.Button(bar, text="Connect", width=10,
                                  bg="#2196F3", fg="white", command=self._toggle_connect)
        self._btn_con.pack(side="left", padx=8)
        self._lbl_con = tk.Label(bar, text="● Disconnected", fg="#c00")
        self._lbl_con.pack(side="left")
        self._refresh_ports()

    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self._cb_port["values"] = ports
        if ports and not self._var_port.get():
            self._var_port.set(ports[0])

    def _toggle_connect(self):
        if client.is_connected():
            client.disconnect()
            self._lbl_con.config(text="● Disconnected", fg="#c00")
            self._btn_con.config(text="Connect", bg="#2196F3")
        else:
            port = self._var_port.get().strip()
            if not port:
                messagebox.showerror("Error", "Chon COM port truoc"); return
            ok, err = client.connect(port, int(self._var_baud.get()))
            if ok:
                self._lbl_con.config(text=f"● Connected ({port})", fg="#090")
                self._btn_con.config(text="Disconnect", bg="#e53935")
                self._log(f"Connected {port}")
            else:
                messagebox.showerror("Error", f"Khong mo duoc {port}:\n{err}")

    # ── Tab Status ─────────────────────────────────────────────────────────────
    def _build_status(self, nb):
        tab = tk.Frame(nb); nb.add(tab, text="Status")

        # Toolbar
        bar = tk.Frame(tab); bar.pack(fill="x", padx=8, pady=6)
        tk.Button(bar, text="⟳ Tải thông tin", command=self._do_status).pack(side="left")
        tk.Button(bar, text="💾 Lưu cấu hình", bg="#43A047", fg="white",
                  command=self._status_save).pack(side="left", padx=6)
        self._lbl_status_info = tk.Label(bar, text="", fg="#555")
        self._lbl_status_info.pack(side="left", padx=8)

        # Scrollable form
        canvas = tk.Canvas(tab, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        frm = tk.Frame(canvas); canvas.create_window((0, 0), window=frm, anchor="nw")
        frm.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._sv = {}  # status tab vars

        def section(text, row):
            tk.Label(frm, text=text, fg="#555", font=("", 9, "bold")).grid(
                row=row, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 2))

        def field(key, label, row, col=0, readonly=False):
            tk.Label(frm, text=label, anchor="w", width=20).grid(
                row=row, column=col*2, sticky="w", padx=(12, 4), pady=3)
            v = tk.StringVar()
            self._sv[key] = v
            e = tk.Entry(frm, textvariable=v, width=30,
                         state="readonly" if readonly else "normal",
                         readonlybackground="#f0f0f0" if readonly else "white")
            e.grid(row=row, column=col*2+1, sticky="ew", padx=(0, 12), pady=3)

        # Định danh (col 0)
        section("─── ĐỊNH DANH ───", 0)
        id_fields = [
            ("s_ma_id",              "Mã định danh"),
            ("s_ho_ten",             "Họ và tên"),
            ("s_nam_sinh",           "Năm sinh"),
            ("s_dia_chi",            "Địa chỉ"),
            ("s_ngay_cap_dinh_danh", "Ngày cấp"),
            ("s_ten_thiet_bi",       "Tên thiết bị"),
            ("s_id_thiet_bi",        "ID thiết bị"),
            ("s_dia_chi_thiet_bi",   "Địa chỉ thiết bị"),
        ]
        for i, (key, label) in enumerate(id_fields, start=1):
            field(key, label, i)

        # Thông tin đọc-thêm (col 1)
        section("─── TRẠNG THÁI ───", 0)  # same row, col 1
        tk.Label(frm, text="─── TRẠNG THÁI ───", fg="#555", font=("", 9, "bold")).grid(
            row=0, column=2, columnspan=2, sticky="w", padx=12, pady=(10, 2))
        field("s_mac",        "MAC address",   1, col=1, readonly=True)
        field("s_updated_at", "Cập nhật lúc",  2, col=1, readonly=True)
        field("s_file_count", "Số file .bin",  3, col=1, readonly=True)

        # Ghi âm (col 1, tiếp)
        tk.Label(frm, text="─── GHI ÂM ───", fg="#555", font=("", 9, "bold")).grid(
            row=4, column=2, columnspan=2, sticky="w", padx=12, pady=(10, 2))
        tk.Label(frm, text="Kiểu ghi âm", anchor="w", width=20).grid(
            row=5, column=2, sticky="w", padx=(12, 4), pady=3)
        self._sv["s_kieu_ghi_am"] = tk.StringVar(value="continuous")
        ttk.Combobox(frm, textvariable=self._sv["s_kieu_ghi_am"],
                     values=["continuous", "interval", "vad", "scheduled", "manual"],
                     width=18, state="readonly").grid(row=5, column=3, sticky="w", padx=(0,12), pady=3)
        field("s_thoi_luong",   "Thời lượng (phút)", 6, col=1)
        field("s_chu_ky_wifi",  "Chu kỳ WiFi (phút)", 7, col=1)

        frm.columnconfigure(1, weight=1)
        frm.columnconfigure(3, weight=1)

    def _do_status(self):
        def _cb(r):
            if not r.get("ok"):
                self._lbl_status_info.config(text=f"Lỗi: {r.get('error')}", fg="#c00")
                return
            dd = r.get("dinh_danh", {})
            ga = r.get("ghi_am", {})
            mapping = {
                "s_ma_id":              dd.get("ma_id", ""),
                "s_ho_ten":             dd.get("ho_ten", ""),
                "s_nam_sinh":           str(dd.get("nam_sinh", "")),
                "s_dia_chi":            dd.get("dia_chi", ""),
                "s_ngay_cap_dinh_danh": dd.get("ngay_cap_dinh_danh", ""),
                "s_ten_thiet_bi":       dd.get("ten_thiet_bi", ""),
                "s_id_thiet_bi":        dd.get("id_thiet_bi", ""),
                "s_dia_chi_thiet_bi":   dd.get("dia_chi_thiet_bi", ""),
                "s_mac":                r.get("mac_address", ""),
                "s_updated_at":         r.get("updated_at", ""),
                "s_file_count":         str(r.get("file_count", 0)),
                "s_kieu_ghi_am":        ga.get("kieu_ghi_am", "continuous"),
                "s_thoi_luong":         str(ga.get("thoi_luong_ghi_am_phut", "")),
                "s_chu_ky_wifi":        str(ga.get("chu_ky_quet_wifi_phut", "")),
            }
            for k, v in mapping.items():
                if k in self._sv:
                    self._sv[k].set(v)
            self._lbl_status_info.config(
                text=f"Đã tải — {r.get('file_count', 0)} file", fg="#090")
            # Sync sang Config tab luôn
            sync = {
                "ma_id": "s_ma_id", "ho_ten": "s_ho_ten", "nam_sinh": "s_nam_sinh",
                "dia_chi": "s_dia_chi", "ngay_cap_dinh_danh": "s_ngay_cap_dinh_danh",
                "ten_thiet_bi": "s_ten_thiet_bi", "id_thiet_bi": "s_id_thiet_bi",
                "dia_chi_thiet_bi": "s_dia_chi_thiet_bi",
                "kieu_ghi_am": "s_kieu_ghi_am",
                "thoi_luong_ghi_am_phut": "s_thoi_luong",
                "chu_ky_quet_wifi_phut": "s_chu_ky_wifi",
            }
            for cfg_key, sv_key in sync.items():
                if cfg_key in self._v and sv_key in self._sv:
                    self._v[cfg_key].set(self._sv[sv_key].get())
        self._run_bg({"cmd": "status"}, _cb)

    def _status_save(self):
        def _safe_int(v, d):
            try: return int(v)
            except Exception: return d
        def _safe_float(v, d):
            try: return float(v)
            except Exception: return d
        patch = {
            "dinh_danh": {
                "ma_id":              self._sv["s_ma_id"].get().strip(),
                "ho_ten":             self._sv["s_ho_ten"].get().strip(),
                "nam_sinh":           _safe_int(self._sv["s_nam_sinh"].get(), 1990),
                "dia_chi":            self._sv["s_dia_chi"].get().strip(),
                "ngay_cap_dinh_danh": self._sv["s_ngay_cap_dinh_danh"].get().strip(),
                "ten_thiet_bi":       self._sv["s_ten_thiet_bi"].get().strip(),
                "id_thiet_bi":        self._sv["s_id_thiet_bi"].get().strip(),
                "dia_chi_thiet_bi":   self._sv["s_dia_chi_thiet_bi"].get().strip(),
            },
            "cau_hinh_ghi_am": {
                "kieu_ghi_am":            self._sv["s_kieu_ghi_am"].get(),
                "thoi_luong_ghi_am_phut": _safe_int(self._sv["s_thoi_luong"].get(), 1),
                "chu_ky_quet_wifi_phut":  _safe_float(self._sv["s_chu_ky_wifi"].get(), 2),
            },
        }
        if not messagebox.askyesno("Xác nhận", "Lưu cấu hình và restart Pi?"): return
        def _cb(r):
            self._lbl_status_info.config(
                text="Đã lưu — Pi đang restart" if r.get("ok") else f"Lỗi: {r.get('error')}",
                fg="#090" if r.get("ok") else "#c00")
        self._run_bg({"cmd": "config_set", "config": patch}, _cb)

    # ── Tab Files ──────────────────────────────────────────────────────────────
    def _build_files(self, nb):
        tab = tk.Frame(nb); nb.add(tab, text="Files")
        br = tk.Frame(tab); br.pack(fill="x", padx=8, pady=6)
        tk.Button(br, text="Refresh", command=self._do_filelist).pack(side="left")
        tk.Button(br, text="Download Selected", bg="#43A047", fg="white",
                  command=self._dl_sel).pack(side="left", padx=4)
        tk.Button(br, text="Download All", bg="#1976D2", fg="white",
                  command=self._dl_all).pack(side="left", padx=4)
        tk.Button(br, text="Delete Selected", bg="#FB8C00", fg="white",
                  command=self._del_sel).pack(side="left", padx=4)
        tk.Button(br, text="Delete All", bg="#e53935", fg="white",
                  command=self._del_all).pack(side="left", padx=4)
        self._tree = ttk.Treeview(tab, columns=("name","size"),
                                   show="headings", selectmode="extended")
        self._tree.heading("name", text="Filename")
        self._tree.heading("size", text="Size")
        self._tree.column("name", width=520); self._tree.column("size", width=100, anchor="e")
        sb = ttk.Scrollbar(tab, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(8,0), pady=4)
        sb.pack(side="left", fill="y", pady=4)

    def _do_filelist(self):
        def _cb(r):
            self._tree.delete(*self._tree.get_children())
            for f in r.get("files", []):
                self._tree.insert("", "end", values=(f["name"], f.get("size_human", f["size"])))
            self._log(f"filelist: {len(r.get('files',[]))} files")
        self._run_bg({"cmd": "filelist"}, _cb)

    def _sel_names(self):
        return [self._tree.item(i)["values"][0] for i in self._tree.selection()]

    def _dl_sel(self):
        names = self._sel_names()
        if not names: messagebox.showinfo("", "Chon it nhat 1 file"); return
        dest = filedialog.askdirectory(title="Luu vao thu muc")
        if not dest: return
        if len(names) == 1:
            self._run_bg({"cmd":"download","name":names[0]},
                         lambda r: self._save_single(r, dest))
        else:
            self._run_bg({"cmd":"download_selected","names":names},
                         lambda r: self._save_zip(r, dest, "selected.zip"))

    def _dl_all(self):
        dest = filedialog.askdirectory(title="Luu vao thu muc")
        if not dest: return
        self._run_bg({"cmd":"download_all"},
                     lambda r: self._save_zip(r, dest, "recordings.zip"))

    def _save_single(self, r, dest):
        if not r.get("ok"): self._log(f"download err: {r.get('error')}"); return
        data = base64.b64decode(r["data_b64"])
        p = os.path.join(dest, r["name"])
        open(p,"wb").write(data)
        self._log(f"Saved: {p} ({len(data):,} B)")
        self._do_filelist()

    def _save_zip(self, r, dest, fname):
        if not r.get("ok"): self._log(f"download err: {r.get('error')}"); return
        data = base64.b64decode(r["data_b64"])
        p = os.path.join(dest, r.get("filename", fname))
        open(p,"wb").write(data)
        self._log(f"Saved: {p} ({len(data):,} B)")

    def _del_sel(self):
        names = self._sel_names()
        if not names: messagebox.showinfo("","Chon it nhat 1 file"); return
        if not messagebox.askyesno("Confirm", f"Xoa {len(names)} file?"): return
        for n in names:
            self._run_bg({"cmd":"delete","name":n},
                         lambda r,x=n: self._log(f"delete {x}: ok={r.get('ok')}"))
        self.after(600, self._do_filelist)

    def _del_all(self):
        if not messagebox.askyesno("Confirm","Xoa TAT CA file tren Pi?"): return
        self._run_bg({"cmd":"delete_all"},
                     lambda r: self._log(f"delete_all: {r.get('deleted',0)} files"))
        self.after(600, self._do_filelist)

    # ── Tab Config ─────────────────────────────────────────────────────────────
    def _build_config(self, nb):
        tab = tk.Frame(nb); nb.add(tab, text="Config")

        br = tk.Frame(tab); br.pack(fill="x", padx=8, pady=6)
        tk.Button(br, text="Read Config from Pi", command=self._cfg_read).pack(side="left")
        tk.Button(br, text="Write Config to Pi", bg="#43A047", fg="white",
                  command=self._cfg_write).pack(side="left", padx=6)

        canvas = tk.Canvas(tab, borderwidth=0)
        vsb = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        frm = tk.Frame(canvas); canvas.create_window((0,0), window=frm, anchor="nw")
        frm.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        def row(label, row_n, col=0):
            tk.Label(frm, text=label, anchor="w", width=26).grid(
                row=row_n, column=col*2, sticky="w", padx=(12,4), pady=3)

        # ── Dinh danh ──
        tk.Label(frm, text="─── Định danh ───", fg="#555").grid(
            row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(8,2))

        self._v = {}
        fields_id = [
            ("ma_id",               "Mã ID"),
            ("ho_ten",              "Họ tên"),
            ("nam_sinh",            "Năm sinh"),
            ("dia_chi",             "Địa chỉ"),
            ("ngay_cap_dinh_danh",  "Ngày cấp (YYYY-MM-DD)"),
            ("ten_thiet_bi",        "Tên thiết bị"),
            ("id_thiet_bi",         "ID thiết bị"),
            ("dia_chi_thiet_bi",    "Địa chỉ thiết bị"),
        ]
        for i, (key, label) in enumerate(fields_id, start=1):
            row(label, i)
            v = tk.StringVar()
            self._v[key] = v
            tk.Entry(frm, textvariable=v, width=36).grid(
                row=i, column=1, sticky="ew", padx=(0,12), pady=3)

        # ── Ghi am ──
        offset = len(fields_id) + 2
        tk.Label(frm, text="─── Cấu hình ghi âm ───", fg="#555").grid(
            row=offset-1, column=0, columnspan=4, sticky="w", padx=12, pady=(10,2))

        # Kieu ghi am dropdown
        row("Kiểu ghi âm", offset)
        self._v["kieu_ghi_am"] = tk.StringVar(value="continuous")
        cb_mode = ttk.Combobox(frm, textvariable=self._v["kieu_ghi_am"],
                               values=["continuous","interval","vad","scheduled","manual"],
                               width=18, state="readonly")
        cb_mode.grid(row=offset, column=1, sticky="w", padx=(0,12), pady=3)

        fields_rec = [
            ("thoi_luong_ghi_am_phut",  "Thời lượng (phút, 1-120)"),
            ("chu_ky_ghi_am_phut",      "Chu kỳ interval (phút)"),
            ("chu_ky_quet_wifi_phut",   "Chu kỳ quét WiFi (phút)"),
            ("ssid_upload",             "SSID upload"),
            ("wifi_password",           "WiFi password"),
            ("duong_dan_public_key",    "Đường dẫn public key"),
            ("vad_nguong_dbfs",         "VAD ngưỡng dBFS"),
            ("vad_timeout_im_lang_giay","VAD timeout im lặng (s)"),
            ("vad_max_thoi_gian_giay",  "VAD max thời gian (s)"),
            ("bat_dau_ghi_am",          "Bắt đầu (YYYY-MM-DD HH:MM)"),
            ("ket_thuc_ghi_am",         "Kết thúc (YYYY-MM-DD HH:MM)"),
        ]
        for i, (key, label) in enumerate(fields_rec, start=offset+1):
            row(label, i)
            v = tk.StringVar()
            self._v[key] = v
            tk.Entry(frm, textvariable=v, width=36).grid(
                row=i, column=1, sticky="ew", padx=(0,12), pady=3)

        frm.columnconfigure(1, weight=1)

    def _cfg_read(self):
        def _cb(r):
            if not r.get("ok"):
                self._log(f"config read err: {r.get('error')}"); return
            cfg = r.get("config", {})
            dd = cfg.get("dinh_danh", {})
            ch = cfg.get("cau_hinh_ghi_am", {})
            mapping = {
                "ma_id": dd.get("ma_id",""),
                "ho_ten": dd.get("ho_ten",""),
                "nam_sinh": str(dd.get("nam_sinh","")),
                "dia_chi": dd.get("dia_chi",""),
                "ngay_cap_dinh_danh": dd.get("ngay_cap_dinh_danh",""),
                "ten_thiet_bi": dd.get("ten_thiet_bi",""),
                "id_thiet_bi": dd.get("id_thiet_bi",""),
                "dia_chi_thiet_bi": dd.get("dia_chi_thiet_bi",""),
                "kieu_ghi_am": ch.get("kieu_ghi_am","continuous"),
                "thoi_luong_ghi_am_phut": str(ch.get("thoi_luong_ghi_am_phut",1)),
                "chu_ky_ghi_am_phut": str(ch.get("chu_ky_ghi_am_phut",60)),
                "chu_ky_quet_wifi_phut": str(ch.get("chu_ky_quet_wifi_phut",2)),
                "ssid_upload": ch.get("ssid_upload",""),
                "wifi_password": ch.get("wifi_password",""),
                "duong_dan_public_key": ch.get("duong_dan_public_key","public.key"),
                "vad_nguong_dbfs": str(ch.get("vad_nguong_dbfs",-41.0)),
                "vad_timeout_im_lang_giay": str(ch.get("vad_timeout_im_lang_giay",60)),
                "vad_max_thoi_gian_giay": str(ch.get("vad_max_thoi_gian_giay",600)),
                "bat_dau_ghi_am": ch.get("bat_dau_ghi_am","") or "",
                "ket_thuc_ghi_am": ch.get("ket_thuc_ghi_am","") or "",
            }
            for k, v in mapping.items():
                if k in self._v:
                    self._v[k].set(v)
            self._log("config loaded OK")
        self._run_bg({"cmd":"config"}, _cb)

    def _cfg_write(self):
        def _safe_int(v, default):
            try: return int(v)
            except Exception: return default
        def _safe_float(v, default):
            try: return float(v)
            except Exception: return default
        def _none_if_empty(v):
            s = v.strip(); return s if s else None

        patch = {
            "dinh_danh": {
                "ma_id":              self._v["ma_id"].get().strip(),
                "ho_ten":             self._v["ho_ten"].get().strip(),
                "nam_sinh":           _safe_int(self._v["nam_sinh"].get(), 1990),
                "dia_chi":            self._v["dia_chi"].get().strip(),
                "ngay_cap_dinh_danh": self._v["ngay_cap_dinh_danh"].get().strip(),
                "ten_thiet_bi":       self._v["ten_thiet_bi"].get().strip(),
                "id_thiet_bi":        self._v["id_thiet_bi"].get().strip(),
                "dia_chi_thiet_bi":   self._v["dia_chi_thiet_bi"].get().strip(),
            },
            "cau_hinh_ghi_am": {
                "kieu_ghi_am":              self._v["kieu_ghi_am"].get(),
                "thoi_luong_ghi_am_phut":   _safe_int(self._v["thoi_luong_ghi_am_phut"].get(), 1),
                "chu_ky_ghi_am_phut":       _safe_int(self._v["chu_ky_ghi_am_phut"].get(), 60),
                "chu_ky_quet_wifi_phut":    _safe_float(self._v["chu_ky_quet_wifi_phut"].get(), 2),
                "ssid_upload":              self._v["ssid_upload"].get().strip(),
                "wifi_password":            self._v["wifi_password"].get().strip(),
                "duong_dan_public_key":     self._v["duong_dan_public_key"].get().strip(),
                "vad_nguong_dbfs":          _safe_float(self._v["vad_nguong_dbfs"].get(), -41.0),
                "vad_timeout_im_lang_giay": _safe_int(self._v["vad_timeout_im_lang_giay"].get(), 60),
                "vad_max_thoi_gian_giay":   _safe_int(self._v["vad_max_thoi_gian_giay"].get(), 600),
                "bat_dau_ghi_am":           _none_if_empty(self._v["bat_dau_ghi_am"].get()),
                "ket_thuc_ghi_am":          _none_if_empty(self._v["ket_thuc_ghi_am"].get()),
            },
        }
        if not messagebox.askyesno("Confirm","Ghi config va restart Pi?"): return
        self._run_bg({"cmd":"config_set","config":patch},
                     lambda r: self._log(f"config_set: {r.get('message') or r.get('error')}"))

    # ── Tab Public Key ─────────────────────────────────────────────────────────
    def _build_pubkey(self, nb):
        tab = tk.Frame(nb); nb.add(tab, text="Public Key")
        frm = tk.Frame(tab); frm.pack(fill="x", padx=12, pady=20)
        tk.Label(frm, text="File public.key:").grid(row=0, column=0, sticky="w")
        self._var_key = tk.StringVar()
        tk.Entry(frm, textvariable=self._var_key, width=55).grid(row=0,column=1,padx=4)
        tk.Button(frm, text="Browse", command=self._browse_key).grid(row=0,column=2)
        tk.Button(tab, text="Upload Public Key to Pi", bg="#7B1FA2", fg="white",
                  height=2, command=self._upload_key).pack(pady=12)
        self._lbl_key = tk.Label(tab, text="", fg="#555"); self._lbl_key.pack()

    def _browse_key(self):
        p = filedialog.askopenfilename(title="Chon public.key",
            filetypes=[("Key","*.key *.bin *.pem *"),("All","*.*")])
        if p: self._var_key.set(p)

    def _upload_key(self):
        p = self._var_key.get().strip()
        if not p or not os.path.exists(p):
            messagebox.showerror("Error","Chon file public.key hop le"); return
        data = open(p,"rb").read()
        if len(data) < 32:
            messagebox.showerror("Error","Key qua ngan (can >= 32 bytes)"); return
        self._lbl_key.config(text=f"Uploading {len(data)} bytes...", fg="#555")
        self._run_bg({"cmd":"public_key","data_b64":base64.b64encode(data).decode()},
                     lambda r: self._lbl_key.config(
                         text=f"OK — {len(data)} bytes, Pi restarting" if r.get("ok")
                              else f"FAIL: {r.get('error')}",
                         fg="#090" if r.get("ok") else "#c00"))

    # ── Log ────────────────────────────────────────────────────────────────────
    def _build_log(self):
        fr = tk.Frame(self); fr.pack(fill="x", padx=8)
        tk.Label(fr, text="Log:").pack(side="left")
        tk.Button(fr, text="Clear", command=lambda: (
            self._txt_log.config(state="normal"),
            self._txt_log.delete("1.0","end"),
            self._txt_log.config(state="disabled"),
        )).pack(side="right")
        self._txt_log = scrolledtext.ScrolledText(
            self, height=6, state="disabled", bg="#1e1e1e", fg="#ccc")
        self._txt_log.pack(fill="x", padx=8, pady=(2,6))

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        def _w():
            self._txt_log.config(state="normal")
            self._txt_log.insert("end", f"[{ts}] {msg}\n")
            self._txt_log.see("end")
            self._txt_log.config(state="disabled")
        self.after(0, _w)

    # ── Background runner ──────────────────────────────────────────────────────
    def _run_bg(self, cmd: dict, cb):
        if not client.is_connected():
            messagebox.showwarning("Warning","Chua ket noi COM port"); return
        def _work():
            self._log(f"→ {cmd.get('cmd')}")
            r = client.send(cmd)
            if not r.get("ok"):
                self._log(f"  ERROR: {r.get('error')}")
            self.after(0, lambda: cb(r))
        threading.Thread(target=_work, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()


import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

try:
    import network_config
except ImportError:
    network_config = None


class DeviceRegistry:
    def __init__(self, on_change=None):
        self._lock = threading.Lock()
        self._devices = {}
        self._on_change = on_change

    def register(self, ip, device_id=None, mac=None, ho_ten=None, bin_pending=None, ssid_upload=None, wifi_password=None):
        ip = (ip or "").strip()
        if not ip:
            raise ValueError("ip is required")
        entry = {
            "ip": ip,
            "device_id": (device_id or "").strip() or None,
            "mac": (mac or "").strip() or None,
            "ho_ten": (ho_ten or "").strip() or None,
            "bin_pending": bin_pending if isinstance(bin_pending, int) else None,
            "ssid_upload": (ssid_upload or "").strip() or None,
            "wifi_password": (wifi_password or "").strip() or None,
            "last_seen": time.time(),
        }
        key = entry["device_id"] or entry["mac"] or ip
        with self._lock:
            self._devices[key] = entry
        if self._on_change:
            self._on_change()
        return entry

    def list_devices(self):
        with self._lock:
            items = list(self._devices.values())
        items.sort(key=lambda item: item.get("last_seen", 0), reverse=True)
        return items

    def clear(self):
        with self._lock:
            self._devices.clear()


class _RegistryHandler(BaseHTTPRequestHandler):
    registry = None

    def log_message(self, format, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/network/config":
            payload = (
                network_config.get_network_config_payload()
                if network_config
                else {"ok": False}
            )
            self._send_json(200, {"ok": True, "network": payload})
            return
        if path == "/api/devices":
            devices = self.registry.list_devices() if self.registry else []
            self._send_json(200, {"ok": True, "devices": devices})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/device/register":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        try:
            data = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "invalid_json"})
            return
        ip = data.get("ip")
        if not ip and isinstance(data.get("device"), dict):
            ip = data["device"].get("ip")
        try:
            entry = self.registry.register(
                ip=ip,
                device_id=data.get("device_id"),
                mac=data.get("mac"),
                ho_ten=data.get("ho_ten"),
                bin_pending=data.get("bin_pending"),
                ssid_upload=data.get("ssid_upload"),
                wifi_password=data.get("wifi_password"),
            )
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return
        self._send_json(200, {"ok": True, "device": entry})


class DeviceRegistryServer:
    def __init__(self, host="0.0.0.0", port=None, registry=None, on_change=None):
        self.host = host
        self.port = port or (
            network_config.REGISTRY_API_PORT if network_config else 8766
        )
        self.registry = registry or DeviceRegistry(on_change=on_change)
        self._server = None
        self._thread = None

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running:
            return True, f"Registry API already running on port {self.port}"

        handler = type(
            "BoundRegistryHandler",
            (_RegistryHandler,),
            {"registry": self.registry},
        )
        try:
            self._server = ThreadingHTTPServer((self.host, self.port), handler)
        except OSError as exc:
            return False, f"Could not start registry API: {exc}"

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="device-registry-api",
            daemon=True,
        )
        self._thread.start()
        return True, f"Registry API listening on http://{self.host}:{self.port}"

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self._thread = None

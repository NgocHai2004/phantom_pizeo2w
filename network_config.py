import ipaddress
import platform
import subprocess
import tempfile

HOST_IP = "10.42.0.1"
SUBNET_MASK = "255.255.255.0"
PREFIX_LENGTH = 24
DEVICE_STATIC_IP = "10.42.0.2"
DEVICE_SERVICE_PORT = 8765
REGISTRY_API_PORT = 8766

_ICS_PARAMETERS_KEY = r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters"

_APPLY_HOST_IP_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$target = '__HOST_IP__'
$prefix = __PREFIX__
$existing = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -eq $target -or $_.IPAddress -eq '192.168.137.1'
} | Select-Object -First 1
if (-not $existing) { exit 0 }
if ($existing.IPAddress -eq $target) { exit 0 }
$index = $existing.InterfaceIndex
Remove-NetIPAddress -InterfaceIndex $index -Confirm:$false -ErrorAction SilentlyContinue
New-NetIPAddress -InterfaceIndex $index -IPAddress $target -PrefixLength $prefix -ErrorAction Stop | Out-Null
"""


def is_windows():
    return platform.system() == "Windows"


def _is_admin():
    if not is_windows():
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def device_service_url(ip=None):
    address = ip or DEVICE_STATIC_IP
    return f"http://{address}:{DEVICE_SERVICE_PORT}"


def registry_api_url(host=None):
    address = host or HOST_IP
    return f"http://{address}:{REGISTRY_API_PORT}"


def get_network_config_payload():
    return {
        "host_ip": HOST_IP,
        "subnet_mask": SUBNET_MASK,
        "prefix_length": PREFIX_LENGTH,
        "device_static_ip": DEVICE_STATIC_IP,
        "device_service_port": DEVICE_SERVICE_PORT,
        "registry_api_port": REGISTRY_API_PORT,
        "registry_api_url": registry_api_url(),
        "device_service_url": device_service_url(),
        "register_endpoint": "/api/device/register",
    }


def _write_ics_registry():
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        _ICS_PARAMETERS_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, "ScopeAddress", 0, winreg.REG_SZ, HOST_IP)
        winreg.SetValueEx(key, "ScopeAddressBackup", 0, winreg.REG_SZ, HOST_IP)
        winreg.SetValueEx(key, "StandaloneDhcpAddress", 0, winreg.REG_SZ, HOST_IP)


def _write_ics_registry_elevated():
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        f"Set-ItemProperty -Path 'HKLM:\\{_ICS_PARAMETERS_KEY}' "
        f"-Name ScopeAddress -Value '{HOST_IP}'\n"
        f"Set-ItemProperty -Path 'HKLM:\\{_ICS_PARAMETERS_KEY}' "
        f"-Name ScopeAddressBackup -Value '{HOST_IP}'\n"
        f"Set-ItemProperty -Path 'HKLM:\\{_ICS_PARAMETERS_KEY}' "
        f"-Name StandaloneDhcpAddress -Value '{HOST_IP}'\n"
        "Restart-Service SharedAccess -Force -ErrorAction SilentlyContinue\n"
    )
    temp_dir = tempfile.gettempdir()
    script_path = f"{temp_dir}\\phantom_ics_subnet.ps1"
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(script)
    command = (
        f"Start-Process powershell -Verb RunAs -Wait -ArgumentList "
        f"'-NoProfile -ExecutionPolicy Bypass -File \"{script_path}\"'"
    )
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return completed.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False
    finally:
        try:
            import os

            os.remove(script_path)
        except OSError:
            pass


def _restart_shared_access():
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "Restart-Service SharedAccess -Force -ErrorAction SilentlyContinue",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def configure_ics_subnet():
    if not is_windows():
        return False, "ICS subnet configuration requires Windows."
    try:
        ipaddress.IPv4Address(HOST_IP)
    except ipaddress.AddressValueError as exc:
        return False, str(exc)

    if _is_admin():
        try:
            _write_ics_registry()
            _restart_shared_access()
        except OSError as exc:
            return False, f"ICS registry update failed: {exc}"
    elif not _write_ics_registry_elevated():
        return (
            False,
            "Approve UAC or run as Administrator to set hotspot subnet to 10.42.0.0/24.",
        )

    return True, f"ICS subnet configured. Host: {HOST_IP}, device: {DEVICE_STATIC_IP}"


def apply_host_adapter_ip():
    if not is_windows():
        return False, "Host IP configuration requires Windows."

    script = (
        _APPLY_HOST_IP_SCRIPT.replace("__HOST_IP__", HOST_IP).replace(
            "__PREFIX__", str(PREFIX_LENGTH)
        )
    )
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "Host adapter IP update timed out."
    except OSError as exc:
        return False, str(exc)

    if completed.returncode == 0:
        return True, f"Host adapter IP set to {HOST_IP}"
    detail = (completed.stderr or completed.stdout or "").strip()
    if not detail:
        detail = f"exit code {completed.returncode}"
    return False, detail


def configure_hotspot_network():
    messages = []
    ok_subnet, subnet_msg = configure_ics_subnet()
    messages.append(subnet_msg)
    ok_host, host_msg = apply_host_adapter_ip()
    messages.append(host_msg)
    overall = ok_subnet or ok_host
    return overall, " | ".join(messages)

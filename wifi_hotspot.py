import hashlib
import os
import platform
import subprocess
import tempfile

try:
    import network_config
except ImportError:
    network_config = None

DEFAULT_HOTSPOT_SSID = "7068616e746f6d303030303030300001"
UPLOAD_HOTSPOT_SSID  = "7068616e746f6d303030303030300002"
DEFAULT_HOTSPOT_PASSWORD = "12345678"
_HOTSPOT_SETTINGS_URI = "ms-settings:network-mobilehotspot"
_ICSSVC_SETTINGS_KEY = r"SYSTEM\CurrentControlSet\Services\icssvc\Settings"
_PRIVATE_SETTINGS_NAME = "PrivateConnectionSettings"

_POWERSHELL_START_TEMPLATE = r"""
$forceRestart = __FORCE_RESTART__
$ErrorActionPreference = 'Stop'
[Windows.System.UserProfile.LockScreen,Windows.System.UserProfile,ContentType=WindowsRuntime] | Out-Null
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}
Start-Service icssvc -ErrorAction SilentlyContinue
function Resolve-TetheringConnectionProfile {
    $internet = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]::GetInternetConnectionProfile()
    if ($internet) { return $internet }
    $profiles = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]::GetConnectionProfiles()
    if (-not $profiles) { return $null }
    $orderedNames = @('Ethernet', 'Wi-Fi', 'WiFi', 'WLAN', 'Local Area Connection', 'Loopback')
    foreach ($hint in $orderedNames) {
        $match = $profiles | Where-Object { $_.ProfileName -like "*$hint*" } | Select-Object -First 1
        if ($match) { return $match }
    }
    return $profiles | Select-Object -First 1
}
$connectionProfile = Resolve-TetheringConnectionProfile
if (-not $connectionProfile) {
    throw 'NO_CONNECTION_PROFILE: Turn on Wi-Fi or plug in Ethernet so Windows has an active network adapter.'
}
$tetheringManager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]::CreateFromConnectionProfile($connectionProfile)
$state = $tetheringManager.TetheringOperationalState.ToString()
if ($state -eq 'On' -and -not $forceRestart) {
    Write-Output $state
    exit 0
}
if (($state -eq 'On') -and $forceRestart) {
    $stopResult = Await ($tetheringManager.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
    if ($stopResult.Status.ToString() -ne 'Success') { throw ('STOP_' + $stopResult.Status) }
    Start-Sleep -Seconds 1
} elseif ($state -ne 'Off') {
    $stopResult = Await ($tetheringManager.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
    if ($stopResult.Status.ToString() -ne 'Success') { throw ('STOP_' + $stopResult.Status) }
    Start-Sleep -Seconds 1
}
try {
    $apConfig = $tetheringManager.GetCurrentAccessPointConfiguration()
    $apConfig.Ssid = '__SSID__'
    $apConfig.Passphrase = '__PASSWORD__'
    if ($apConfig | Get-Member -Name 'IsBroadcastEnabled' -ErrorAction SilentlyContinue) {
        $apConfig.IsBroadcastEnabled = $false
    }
    Await ($tetheringManager.ConfigureAccessPointAsync($apConfig)) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringAccessPointConfiguration]) | Out-Null
} catch {}
$startResult = Await ($tetheringManager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
if ($startResult.Status.ToString() -ne 'Success') { throw ('START_' + $startResult.Status) }
$tetheringManager.TetheringOperationalState
"""


def is_windows():
    return platform.system() == "Windows"


def _machine_guid_seed():
    if not is_windows():
        return platform.node() or "default-seed"
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            if value:
                return str(value)
    except OSError:
        pass
    return platform.node() or "default-seed"


def derive_hotspot_ssid():
    return DEFAULT_HOTSPOT_SSID


def _encode_private_connection_settings(ssid, password, band_indicator=1, hidden=True):
    if not ssid or len(ssid) > 32:
        raise ValueError("SSID must be between 1 and 32 characters.")
    if len(password) < 8 or len(password) > 63:
        raise ValueError("Password must be between 8 and 63 characters.")

    # flag: 1 = normal, 3 = hidden (bit 1 set)
    flag = 3 if hidden else 1
    blob = bytearray([flag, 0, 0, 0])
    for char in ssid:
        blob.extend(char.encode("utf-16le"))
    ssid_padding = 64 - (len(ssid) * 2)
    if ssid_padding > 0:
        blob.extend(b"\x00" * ssid_padding)
    blob.extend(b"\x00\x00")
    for char in password:
        blob.extend(char.encode("utf-16le"))
    remaining = 200 - len(blob)
    if remaining > 0:
        blob.extend(b"\x00" * remaining)
    blob.extend(bytes([band_indicator, 0, 0, 0, 0, 0, 0, 0]))
    if len(blob) != 208:
        raise ValueError("Invalid hotspot registry payload size.")
    return bytes(blob)


def _is_admin():
    if not is_windows():
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def _write_hotspot_registry(ssid, password):
    import winreg

    payload = _encode_private_connection_settings(ssid, password)
    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        _ICSSVC_SETTINGS_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, _PRIVATE_SETTINGS_NAME, 0, winreg.REG_BINARY, payload)
    return True


def _write_hotspot_registry_elevated(ssid, password):
    payload = _encode_private_connection_settings(ssid, password)
    byte_values = ",".join(str(byte) for byte in payload)
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        f"$bytes = [byte[]]({byte_values})\n"
        'Set-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\icssvc\\Settings" '
        f'-Name "{_PRIVATE_SETTINGS_NAME}" -Value $bytes -Type Binary\n'
        "Restart-Service icssvc -Force\n"
    )
    temp_dir = tempfile.gettempdir()
    script_path = os.path.join(temp_dir, "phantom_hotspot_setup.ps1")
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
    except subprocess.TimeoutExpired:
        return False
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass
    return completed.returncode == 0


def _restart_hotspot_service():
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "Restart-Service icssvc -Force -ErrorAction Stop",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _build_start_script(force_restart=False, ssid=None, password=None):
    flag = "$true" if force_restart else "$false"
    script = _POWERSHELL_START_TEMPLATE.replace("__FORCE_RESTART__", flag)
    script = script.replace("__SSID__", (ssid or DEFAULT_HOTSPOT_SSID).replace("'", "''"))
    script = script.replace("__PASSWORD__", (password or DEFAULT_HOTSPOT_PASSWORD).replace("'", "''"))
    return script


def _start_hotspot(force_restart=False, ssid=None, password=None):
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _build_start_script(force_restart, ssid=ssid, password=password),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "Hotspot start timed out."
    except OSError as exc:
        return False, str(exc)

    output = (completed.stdout or "").strip()
    if completed.returncode == 0:
        state = output.splitlines()[-1] if output else "On"
        return True, state

    detail = (completed.stderr or completed.stdout or "").strip()
    if not detail:
        detail = f"exit code {completed.returncode}"
    return False, detail


def configure_and_start_hotspot(ssid=None, password=None):
    if not is_windows():
        return False, "WiFi hotspot control is only supported on Windows."

    ssid = ssid or derive_hotspot_ssid()
    password = password or DEFAULT_HOTSPOT_PASSWORD

    try:
        _encode_private_connection_settings(ssid, password)
    except ValueError as exc:
        return False, str(exc)

    if not _is_admin():
        if not _write_hotspot_registry_elevated(ssid, password):
            started, start_msg = _start_hotspot(ssid=ssid, password=password)
            if started:
                network_msg = ""
                if network_config is not None:
                    _, network_msg = network_config.configure_hotspot_network()
                extra = f" {network_msg}" if network_msg else ""
                return (
                    True,
                    f"Hotspot is on. Approve UAC to apply SSID {ssid} and password. State: {start_msg}.{extra}",
                )
            return (
                False,
                "Could not apply hotspot credentials. Approve UAC when prompted, or run as Administrator.",
            )
    else:
        try:
            _write_hotspot_registry(ssid, password)
            _restart_hotspot_service()
        except OSError as exc:
            return False, f"Failed to write hotspot settings: {exc}"

    started, start_msg = _start_hotspot(force_restart=True, ssid=ssid, password=password)
    if not started:
        return False, start_msg

    network_msg = ""
    if network_config is not None:
        _, network_msg = network_config.configure_hotspot_network()

    if network_msg:
        return (
            True,
            f"Hotspot started. SSID: {ssid}. Password: {password}. State: {start_msg}. {network_msg}",
        )
    return True, f"Hotspot started. SSID: {ssid}. Password: {password}. State: {start_msg}"


def open_wifi_settings():
    if not is_windows():
        return False, "WiFi settings are only available on Windows."
    try:
        os.startfile(_HOTSPOT_SETTINGS_URI)
        return True, "Opened Windows mobile hotspot settings."
    except OSError as exc:
        return False, str(exc)

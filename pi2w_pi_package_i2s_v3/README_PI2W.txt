PI2W package for Raspberry Pi Zero 2 W (I2S + hidden Wi-Fi)

Files:
- pi2w_client.py
- pi_identity_config.json
- public.key
- requirements.txt
- pi2w_client.service
- install_pi.sh (Ubuntu/Debian/Armbian/Raspberry Pi OS)
- install_arch.sh (Arch Linux / Arch Linux ARM)
- huongdancai.md (full A-Z guide)

Recommended for Pi Zero 2 W:
1) Use install_pi.sh
2) Enable I2S in /boot/firmware/config.txt (or /boot/config.txt)
3) Reboot
4) Check service logs

Quick run:
- chmod +x install_pi.sh
- APP_USER=root ./install_pi.sh
- journalctl -u pi2w_client.service -f
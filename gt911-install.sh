#!/usr/bin/env bash
#
# goodix_install.sh
# Installs/updates Goodix GT911 overlay and firmware config on a Raspberry Pi-like system.
#
# Steps:
#   1. Ensure "dtoverlay=goodix" is in /boot/firmware/config.txt
#   2. Download and replace /boot/overlays/goodix.dtbo
#   3. Download and place goodix_911_cfg.bin in /lib/firmware/
#   4. Download and install goodix_gt911_config.py in /usr/local/lib/gt911-config.py (executable)
#   5. Reboot the system
#
# Run as: sudo ./goodix_install.sh

set -e  # Exit if any command fails
set -u  # Treat unset variables as errors
set -o pipefail

# Variables
CONFIG_TXT="/boot/firmware/config.txt"
OVERLAY_LINE="dtoverlay=goodix"
DTBO_URL="https://github.com/secwest/raspi-gt911/raw/refs/heads/main/goodix.dtbo"
BIN_URL="https://github.com/secwest/raspi-gt911/raw/refs/heads/main/goodix_911_cfg.bin"
PY_URL="https://github.com/secwest/raspi-gt911/raw/refs/heads/main/goodix_gt911_config.py"

DTBO_TARGET="/boot/overlays/goodix.dtbo"
BIN_TARGET="/lib/firmware/goodix_911_cfg.bin"
PY_TARGET="/usr/local/lib/gt911-config.py"

echo "===================================================="
echo " Goodix GT911 Installer/Updater (Shell Script)"
echo " 1) Ensures 'dtoverlay=goodix' in ${CONFIG_TXT}"
echo " 2) Installs new goodix.dtbo -> ${DTBO_TARGET}"
echo " 3) Installs goodix_911_cfg.bin -> ${BIN_TARGET}"
echo " 4) Installs goodix_gt911_config.py -> ${PY_TARGET}"
echo " 5) Reboots the system"
echo "===================================================="
echo

# 1. Ensure dtoverlay=goodix is in /boot/firmware/config.txt
echo "[INFO] Checking if '${OVERLAY_LINE}' exists in ${CONFIG_TXT} ..."
if [ ! -f "${CONFIG_TXT}" ]; then
  echo "[WARNING] ${CONFIG_TXT} not found; creating it."
  sudo sh -c "echo '${OVERLAY_LINE}' > '${CONFIG_TXT}'"
else
  if grep -q "^${OVERLAY_LINE}" "${CONFIG_TXT}"; then
    echo "[INFO] '${OVERLAY_LINE}' already present in ${CONFIG_TXT}."
  else
    echo "[INFO] Appending '${OVERLAY_LINE}' to ${CONFIG_TXT}."
    sudo sh -c "echo '' >> '${CONFIG_TXT}'"
    sudo sh -c "echo '${OVERLAY_LINE}' >> '${CONFIG_TXT}'"
  fi
fi

# 2. Download and replace /boot/overlays/goodix.dtbo
echo "[INFO] Downloading goodix.dtbo ..."
wget -O goodix.dtbo "${DTBO_URL}"
echo "[INFO] Installing goodix.dtbo -> ${DTBO_TARGET}"
sudo cp goodix.dtbo "${DTBO_TARGET}"
sudo chmod 644 "${DTBO_TARGET}"
rm goodix.dtbo

# 3. Download and place goodix_911_cfg.bin in /lib/firmware
echo "[INFO] Downloading goodix_911_cfg.bin ..."
wget -O goodix_911_cfg.bin "${BIN_URL}"
echo "[INFO] Installing goodix_911_cfg.bin -> ${BIN_TARGET}"
sudo cp goodix_911_cfg.bin "${BIN_TARGET}"
sudo chmod 644 "${BIN_TARGET}"
rm goodix_911_cfg.bin

# 4. Download and install goodix_gt911_config.py -> /usr/local/lib/gt911-config.py
echo "[INFO] Downloading goodix_gt911_config.py ..."
wget -O gt911-config.py "${PY_URL}"
echo "[INFO] Installing gt911-config.py -> ${PY_TARGET}"
sudo cp gt911-config.py "${PY_TARGET}"
sudo chmod 755 "${PY_TARGET}"
rm gt911-config.py

# 5. Reboot
echo
echo "[INFO] Installation complete. System will reboot in 5 seconds..."
sleep 5
sudo reboot

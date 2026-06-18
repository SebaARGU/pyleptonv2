#!/usr/bin/env bash
#
# install.sh — Deploy the Lepton thermal camera web interface on a Raspberry Pi.
#
# Installs dependencies into a virtualenv, enables SPI/I2C, registers a systemd
# service that starts on boot, and (optionally) turns the Pi into a WiFi access
# point with a fixed IP so any device can connect and open the web viewer.
#
# Usage:
#   sudo ./install.sh                 # deps + service (no hotspot)
#   sudo ./install.sh --hotspot       # deps + service + WiFi access point
#   sudo ./install.sh --no-hotspot    # explicit: skip hotspot
#   sudo ./install.sh --uninstall     # remove service and hotspot
#
set -euo pipefail

# ── Configurable values ──────────────────────────────────────────────────────
SSID="LeptonCam"                  # WiFi network name the Pi broadcasts
WIFI_PASS="leptonthermal"         # WiFi password (min 8 chars for WPA)
AP_IP="192.168.4.1"               # fixed IP of the Pi in hotspot mode
PORT="8000"                       # web server port
HOTSPOT_CON="lepton-hotspot"      # NetworkManager connection name
SERVICE_NAME="lepton-web"

# ── Paths and user (resolved, not hardcoded) ─────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_USER="${SUDO_USER:-$(id -un)}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# ── Helpers ──────────────────────────────────────────────────────────────────
log()  { printf '\033[1;36m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; }

require_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        err "Run with sudo: sudo ./install.sh ${*:-}"
        exit 1
    fi
}

# ── Steps ────────────────────────────────────────────────────────────────────
install_apt_deps() {
    log "Installing system packages (python3-venv, i2c-tools, network-manager)..."
    apt-get update -qq
    apt-get install -y python3-venv i2c-tools network-manager
}

enable_interfaces() {
    if command -v raspi-config >/dev/null 2>&1; then
        log "Enabling SPI and I2C via raspi-config..."
        raspi-config nonint do_spi 0
        raspi-config nonint do_i2c 0
    else
        warn "raspi-config not found; enable SPI and I2C manually if needed."
    fi
}

add_groups() {
    log "Adding '$TARGET_USER' to spi, i2c, gpio groups..."
    for grp in spi i2c gpio; do
        if getent group "$grp" >/dev/null 2>&1; then
            usermod -aG "$grp" "$TARGET_USER"
        fi
    done
}

setup_venv() {
    log "Creating virtualenv and installing Python dependencies..."
    sudo -u "$TARGET_USER" python3 -m venv "$SCRIPT_DIR/.venv"
    sudo -u "$TARGET_USER" "$SCRIPT_DIR/.venv/bin/pip" install --upgrade pip
    sudo -u "$TARGET_USER" "$SCRIPT_DIR/.venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
}

install_service() {
    log "Installing systemd service '$SERVICE_NAME'..."
    sed -e "s|@USER@|$TARGET_USER|g" \
        -e "s|@DIR@|$SCRIPT_DIR|g" \
        -e "s|@PORT@|$PORT|g" \
        "$SCRIPT_DIR/deploy/lepton-web.service" > "$SERVICE_FILE"
    systemctl daemon-reload
    systemctl enable --now "${SERVICE_NAME}.service"
}

setup_hotspot() {
    if ! command -v nmcli >/dev/null 2>&1; then
        warn "nmcli (NetworkManager) not found. Skipping hotspot."
        warn "On older Raspberry Pi OS (Bullseye) configure hostapd + dnsmasq manually."
        return
    fi
    warn "Enabling the hotspot will DISCONNECT the Pi from WiFi internet."
    log "Configuring WiFi access point '$SSID' at $AP_IP..."

    nmcli connection delete "$HOTSPOT_CON" >/dev/null 2>&1 || true
    nmcli connection add type wifi ifname wlan0 con-name "$HOTSPOT_CON" \
        autoconnect yes ssid "$SSID"
    nmcli connection modify "$HOTSPOT_CON" \
        802-11-wireless.mode ap 802-11-wireless.band bg \
        ipv4.method shared ipv4.addresses "$AP_IP/24" \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$WIFI_PASS"
    nmcli connection up "$HOTSPOT_CON"
}

uninstall() {
    log "Stopping and removing service '$SERVICE_NAME'..."
    systemctl disable --now "${SERVICE_NAME}.service" >/dev/null 2>&1 || true
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload

    if command -v nmcli >/dev/null 2>&1; then
        log "Removing hotspot connection '$HOTSPOT_CON'..."
        nmcli connection down "$HOTSPOT_CON" >/dev/null 2>&1 || true
        nmcli connection delete "$HOTSPOT_CON" >/dev/null 2>&1 || true
    fi
    log "Uninstall complete. The .venv directory was left in place."
}

summary() {
    echo
    log "Done."
    echo "  Service : $(systemctl is-active "${SERVICE_NAME}.service" 2>/dev/null || echo unknown)  (${SERVICE_NAME}.service)"
    if [[ "$WANT_HOTSPOT" == "yes" ]]; then
        echo "  WiFi    : connect to SSID '$SSID' (password: $WIFI_PASS)"
        echo "  Open    : http://$AP_IP:$PORT"
    else
        echo "  Open    : http://<pi-ip>:$PORT   (run 'hostname -I' to find the IP)"
    fi
    echo "  Logs    : journalctl -u ${SERVICE_NAME} -f"
    echo
    warn "Reboot now if SPI/I2C were just enabled: the camera devices"
    warn "(/dev/spidev0.0, /dev/i2c-1) appear only after 'sudo reboot'."
}

# ── Main ─────────────────────────────────────────────────────────────────────
WANT_HOTSPOT="no"
case "${1:-}" in
    --uninstall)
        require_root --uninstall
        uninstall
        exit 0
        ;;
    --hotspot)
        WANT_HOTSPOT="yes"
        ;;
    --no-hotspot|"")
        WANT_HOTSPOT="no"
        ;;
    *)
        err "Unknown option: $1"
        echo "Usage: sudo ./install.sh [--hotspot | --no-hotspot | --uninstall]"
        exit 1
        ;;
esac

require_root "${1:-}"
install_apt_deps
enable_interfaces
add_groups
setup_venv
install_service
[[ "$WANT_HOTSPOT" == "yes" ]] && setup_hotspot
summary

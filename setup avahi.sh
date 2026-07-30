#!/bin/bash
# Install Avahi tools

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo dnf install avahi-tools
sudo cp "${SCRIPT_DIR}/root/etc/systemd/system/avahi-alias@.service" /etc/systemd/system/avahi-alias@.service
sudo systemctl daemon-reload
sudo systemctl enable --now avahi-alias@sillytavern.local.service
sudo systemctl enable --now avahi-alias@piclaw.local.service
sudo systemctl enable --now avahi-alias@kobold.local.service

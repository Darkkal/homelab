#!/bin/bash
# Install Avahi tools

sudo dnf install avahi-tools
sudo cp ./root/etc/systemd/system/avahi-alias@.service /etc/systemd/system/avahi-alias@.service
sudo systemctl daemon-reload
sudo systemctl enable --now avahi-alias@sillytavern.local.service
sudo systemctl enable --now avahi-alias@piclaw.local.service
sudo systemctl enable --now avahi-alias@kobold.local.service

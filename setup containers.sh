#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Copy home/user files to home directory
cp -r "${SCRIPT_DIR}/root/home/user/." "$HOME/"

# Enable Caddy service for rootless user
sudo sysctl net.ipv4.ip_unprivileged_port_start=80
echo "net.ipv4.ip_unprivileged_port_start=80" | sudo tee /etc/sysctl.d/99-rootless-ports.conf
systemctl --user daemon-reload
systemctl --user enable --now caddy.service
sudo loginctl enable-linger $USER

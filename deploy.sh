#!/bin/bash

# Define directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="${SCRIPT_DIR}/root/home/user/.config/containers/systemd"
SYSTEMD_USER_DIR="$HOME/.config/containers/systemd"
CONFIG_FILE="${SCRIPT_DIR}/rig-config.env"

# Ensure the destination directory exists
mkdir -p "$SYSTEMD_USER_DIR"

# 1. Check if the config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: $CONFIG_FILE not found!"
    exit 1
fi

# 2. Export variables from the .env file so envsubst can see them
# (The sed command ignores comments and blank lines)
export $(grep -v '^#' "$CONFIG_FILE" | xargs)

echo "⚙️  Injecting variables and generating Quadlets..."

# 3. Loop through all .template files in the template directory
for template in "$TEMPLATE_DIR"/*.template; do
    [ -e "$template" ] || continue
    # Strip directory and the .template extension for the final filename
    base_name="$(basename "$template")"
    filename="${base_name%.template}"
    destination="$SYSTEMD_USER_DIR/$filename"

    # Inject variables and write to the systemd directory
    envsubst < "$template" > "$destination"

    echo "  -> Created $filename"
done

# 4. Copy static network files
for netfile in "$TEMPLATE_DIR"/*.network; do
    if [ -f "$netfile" ]; then
        cp "$netfile" "$SYSTEMD_USER_DIR/"
        echo "  -> Copied $(basename "$netfile")"
    fi
done

echo "🔄 Reloading systemd user daemon..."
systemctl --user daemon-reload

echo "✅ Deployment complete! You can now start the services:"
echo "   systemctl --user enable --now caddy.service"

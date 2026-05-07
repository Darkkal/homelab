#!/bin/bash

# Define directories
PROJECT_DIR="$(pwd)"
SYSTEMD_USER_DIR="$HOME/.config/containers/systemd"

# Ensure the destination directory exists
mkdir -p "$SYSTEMD_USER_DIR"

# 1. Check if the config file exists
if [ ! -f "rig-config.env" ]; then
    echo "Error: rig-config.env not found!"
    exit 1
fi

# 2. Export variables from the .env file so envsubst can see them
# (The sed command ignores comments and blank lines)
export $(grep -v '^#' rig-config.env | xargs)

echo "⚙️  Injecting variables and generating Quadlets..."

# 3. Loop through all .template files in the current directory
for template in *.template; do
    # Strip the .template extension for the final filename
    filename="${template%.template}"
    destination="$SYSTEMD_USER_DIR/$filename"

    # Inject variables and write to the systemd directory
    envsubst < "$template" > "$destination"

    echo "  -> Created $filename"
done

# 4. Copy the static network file (no variables needed here usually)
if [ -f "ai-rig.network" ]; then
    cp ai-rig.network "$SYSTEMD_USER_DIR/"
    echo "  -> Copied ai-rig.network"
fi

echo "🔄 Reloading systemd user daemon..."
systemctl --user daemon-reload

echo "✅ Deployment complete! You can now start the services:"
echo "   systemctl --user enable --now caddy.service"

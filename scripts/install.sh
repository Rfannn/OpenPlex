#!/bin/bash
set -e

echo "Installing Media Gallery server..."

# System deps
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg aria2

# Create venv
python3 -m venv venv
source venv/bin/activate

# Install Python deps
pip install -r requirements.txt -i https://mirror-pypi.runflare.com/simple

# Setup .env if not exists
if [ ! -f ".env" ]; then
    cp .env.ubuntu.example .env
    echo "Created .env from template — edit SECRET_KEY before production use"
fi

# Setup systemd service
sudo cp deploy/media-gallery.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable media-gallery
sudo systemctl start media-gallery

echo ""
echo "Installation complete!"
echo "  Status: sudo systemctl status media-gallery"
echo "  Logs:   sudo journalctl -u media-gallery -f"
echo "  URL:    http://$(hostname -I | awk '{print $1}'):8185"

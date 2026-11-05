#!/usr/bin/env bash
# Run once on the customer's Linux server:   bash deploy/install_linux.sh [--service]
# --service (run as root) also installs a systemd unit so the site starts at boot.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
command -v python3 >/dev/null || { echo "python3 is not installed"; exit 1; }
[ -d venv ] || python3 -m venv venv
. venv/bin/activate
python -m pip install --upgrade pip
if [ -d wheelhouse ]; then pip install --no-index --find-links wheelhouse -r requirements.txt; else pip install -r requirements.txt; fi
python deploy/setup_install.py

cat > deploy/start_server.sh <<EOF
#!/usr/bin/env bash
cd "$ROOT" && . venv/bin/activate && exec python deploy/run_server.py
EOF
chmod +x deploy/start_server.sh

if [ "${1:-}" = "--service" ]; then
  [ "$(id -u)" -eq 0 ] || { echo "--service needs root (sudo)"; exit 1; }
  cat > /etc/systemd/system/agripos.service <<EOF
[Unit]
Description=Business Management System
After=network.target

[Service]
WorkingDirectory=$ROOT
ExecStart=$ROOT/venv/bin/python $ROOT/deploy/run_server.py
Restart=always
RestartSec=5
User=$(logname 2>/dev/null || echo root)

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload && systemctl enable --now agripos
  echo "Service installed: systemctl status agripos"
fi
echo "Done. Start manually with: deploy/start_server.sh"

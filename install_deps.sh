#!/bin/bash
# install_deps.sh — Cài numpy/sklearn không cần pip global

set -e

PROJECT="/mnt/d/02_Study_Materials/Ki2Nam4/AN NINH MANG/DoAnANMang"

echo "[1] Python version:"
python3 --version

echo "[2] Tạo virtual environment..."
python3 -m venv "$PROJECT/venv" 2>/dev/null || {
    echo "venv module không có, cài..."
    sudo apt-get install -y python3-venv python3-full
    python3 -m venv "$PROJECT/venv"
}

echo "[3] Activate venv và cài packages..."
source "$PROJECT/venv/bin/activate"

pip install --upgrade pip -q
pip install numpy scikit-learn torch --index-url https://download.pytorch.org/whl/cpu -q
pip install ryu eventlet==0.30.2 -q 2>/dev/null || pip install ryu -q

echo "[4] Test scaler..."
cd "$PROJECT"
python3 check_scaler.py

echo ""
echo "=== DONE! Venv created at: $PROJECT/venv ==="
echo ""
echo "Sau này chạy controller dùng lệnh:"
echo "  source venv/bin/activate"
echo "  PYTHONPATH=. ryu-manager controller/ryu_controller.py"

#!/bin/bash
# setup_vm.sh — Copy project sang local + cài đầy đủ dependencies
# Chạy: bash /mnt/hgfs/DoAnANMang/setup_vm.sh

set -e
SRC="/mnt/hgfs/DoAnANMang"
DEST="$HOME/DoAnANMang"

echo "━━━ [1/5] Copy project sang $DEST (bỏ qua venv cũ) ━━━"
rm -rf "$DEST"
mkdir -p "$DEST"
# Copy từng thư mục/file cần thiết, bỏ qua venv
for item in controller topology traffic evaluation dashboard \
            config.py requirements.txt check_scaler.py swap_model.py \
            scaler.pkl sdn_lstm_model.pth sdn_transformer_model.pth sdn_autoencoder_model.pth \
            install_deps.sh quick_setup.sh README.md BAO_CAO_DU_AN.md \
            *.ipynb; do
    if [ -e "$SRC/$item" ]; then
        cp -r "$SRC/$item" "$DEST/" 2>/dev/null || true
    fi
done
echo "✅ Copy xong!"

cd "$DEST"

echo "━━━ [2/5] Tạo virtual environment ━━━"
python3 -m venv venv_ryu
source venv_ryu/bin/activate

echo "━━━ [3/5] Cài dependencies ━━━"
pip install --upgrade pip -q
pip install numpy scikit-learn -q
pip install torch --index-url https://download.pytorch.org/whl/cpu -q
pip install setuptools==65.7.0 wheel -q
pip install eventlet==0.30.2 ryu -q

echo "━━━ [4/5] Verify ━━━"
python -c "import ryu, torch, sklearn; print('✅ ALL PACKAGES OK!')"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ SETUP HOÀN TẤT!"
echo "  Project tại: $DEST"
echo ""
echo "  Chạy Controller:"
echo "    cd $DEST"
echo "    source venv_ryu/bin/activate"
echo "    ryu-manager controller/ryu_controller.py --observe-links"
echo ""
echo "  Chạy Mininet (terminal khác):"
echo "    cd $DEST"
echo "    sudo python3 topology/tree_topo.py"
echo ""
echo "  Mở Dashboard (terminal khác):"
echo "    cd $DEST/dashboard"
echo "    python3 -m http.server 8000"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

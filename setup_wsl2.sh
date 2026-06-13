#!/bin/bash
# =============================================================
# setup_wsl2.sh — Cài đặt môi trường cho WSL2
#
# Chạy 1 lần duy nhất:
#   bash setup_wsl2.sh
# =============================================================

set -e  # Dừng nếu có lỗi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   SDN DDoS Detection — WSL2 Setup Script    ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ---- Màu sắc ----
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'  # No Color

ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
info() { echo -e "    $1"; }

# ============================================================
# 0. Kiểm tra WSL2
# ============================================================
if ! grep -qi "microsoft" /proc/version 2>/dev/null; then
    warn "Có vẻ không phải WSL2, tiếp tục anyway..."
else
    ok "Detected WSL2 environment"
fi

# ============================================================
# 1. Cập nhật system
# ============================================================
echo ""
echo "━━━ Step 1: Update system packages ━━━"
sudo apt-get update -qq
ok "System packages updated"

# ============================================================
# 2. Kiểm tra Mininet
# ============================================================
echo ""
echo "━━━ Step 2: Check Mininet ━━━"
if command -v mn &>/dev/null; then
    ok "Mininet already installed: $(mn --version 2>&1 | head -1)"
else
    warn "Mininet not found, installing..."
    sudo apt-get install -y mininet
    ok "Mininet installed"
fi

# ============================================================
# 3. Cài hping3 và iperf3
# ============================================================
echo ""
echo "━━━ Step 3: Install traffic tools ━━━"
sudo apt-get install -y hping3 iperf3 tcpdump net-tools
ok "Traffic tools installed (hping3, iperf3, tcpdump)"

# ============================================================
# 4. Kiểm tra Python3
# ============================================================
echo ""
echo "━━━ Step 4: Check Python3 ━━━"
PYTHON_VER=$(python3 --version 2>&1)
ok "Python: $PYTHON_VER"

# pip
if ! command -v pip3 &>/dev/null; then
    warn "pip3 not found, installing..."
    sudo apt-get install -y python3-pip
fi
ok "pip3: $(pip3 --version | cut -d' ' -f1-2)"

# ============================================================
# 5. Cài Python packages
# ============================================================
echo ""
echo "━━━ Step 5: Install Python packages ━━━"

# PyTorch (CPU-only, nhẹ hơn)
echo "  Installing PyTorch (CPU)..."
pip3 install torch --index-url https://download.pytorch.org/whl/cpu -q
ok "PyTorch installed"

# Scikit-learn, numpy, pandas
pip3 install numpy scikit-learn pandas matplotlib seaborn tqdm -q
ok "Scientific packages installed"

# ============================================================
# 6. Cài Ryu
# ============================================================
echo ""
echo "━━━ Step 6: Install Ryu SDN Framework ━━━"

# Kiểm tra xem ryu đã có chưa
if command -v ryu-manager &>/dev/null; then
    ok "Ryu already installed: $(ryu-manager --version 2>&1)"
else
    echo "  Installing Ryu..."
    # Ryu cần eventlet < 0.31.0 để tránh lỗi
    pip3 install eventlet==0.30.2 -q
    pip3 install ryu -q
    ok "Ryu installed"
fi

# ============================================================
# 7. Tìm đường dẫn project trong WSL2
# ============================================================
echo ""
echo "━━━ Step 7: Detect project path ━━━"

# Script này nằm trong project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

ok "Project directory: $PROJECT_DIR"

# Tạo thư mục cần thiết
mkdir -p "$PROJECT_DIR/evaluation/results"
mkdir -p "$PROJECT_DIR/logs"
ok "Directories created"

# ============================================================
# 8. Kiểm tra file model
# ============================================================
echo ""
echo "━━━ Step 8: Check model files ━━━"

MODELS=("sdn_lstm_model.pth" "sdn_transformer_model.pth" "sdn_autoencoder_model.pth" "scaler.pkl")
ALL_OK=true

for model in "${MODELS[@]}"; do
    if [ -f "$PROJECT_DIR/$model" ]; then
        SIZE=$(du -h "$PROJECT_DIR/$model" | cut -f1)
        ok "$model ($SIZE)"
    else
        warn "MISSING: $model"
        ALL_OK=false
    fi
done

if [ "$ALL_OK" = false ]; then
    echo ""
    warn "Một số file model chưa có! Đảm bảo các file .pth và scaler.pkl"
    warn "nằm trong: $PROJECT_DIR"
fi

# ============================================================
# 9. Test import Python
# ============================================================
echo ""
echo "━━━ Step 9: Test Python imports ━━━"

python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR')
errors = []

try:
    import torch
    print(f'  ✓ torch {torch.__version__}')
except ImportError as e:
    errors.append(f'torch: {e}')

try:
    import sklearn
    print(f'  ✓ sklearn {sklearn.__version__}')
except ImportError as e:
    errors.append(f'sklearn: {e}')

try:
    import pickle
    s = pickle.load(open('$PROJECT_DIR/scaler.pkl', 'rb'))
    print(f'  ✓ scaler.pkl loaded: {type(s).__name__}')
except Exception as e:
    print(f'  ! scaler.pkl: {e}')

try:
    from controller.model_definitions import AnomalyLSTM, SDNTransformer, DeepAutoencoder
    print('  ✓ model_definitions imported')
except Exception as e:
    errors.append(f'model_definitions: {e}')

try:
    from controller.feature_extractor import FeatureExtractor
    print('  ✓ feature_extractor imported')
except Exception as e:
    errors.append(f'feature_extractor: {e}')

try:
    from controller.inference_engine import InferenceEngine
    print('  ✓ inference_engine imported')
except Exception as e:
    errors.append(f'inference_engine: {e}')

if errors:
    print()
    print('ERRORS:')
    for e in errors:
        print(f'  ✗ {e}')
    sys.exit(1)
else:
    print()
    print('  All imports OK!')
"

# ============================================================
# 10. Tạo symlink tiện lợi (optional)
# ============================================================
echo ""
echo "━━━ Step 10: Create convenience scripts ━━━"

# run_controller.sh
cat > "$PROJECT_DIR/run_controller.sh" << 'EOF'
#!/bin/bash
# Chạy Ryu Controller
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
echo "[*] Starting Ryu Controller..."
echo "    Project: $PROJECT_DIR"
echo "    Model:   $(python3 -c "from config import ACTIVE_MODEL; print(ACTIVE_MODEL)")"
echo ""
PYTHONPATH="$PROJECT_DIR" ryu-manager controller/ryu_controller.py \
    --observe-links \
    --ofp-tcp-listen-port 6653 \
    2>&1 | tee logs/controller_$(date +%Y%m%d_%H%M%S).log
EOF
chmod +x "$PROJECT_DIR/run_controller.sh"

# run_mininet.sh
cat > "$PROJECT_DIR/run_mininet.sh" << 'EOF'
#!/bin/bash
# Chạy Mininet (cần root)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOPO=${1:-"single"}   # single | tree
DEPTH=${2:-2}
FANOUT=${3:-3}

if [ "$TOPO" = "tree" ]; then
    echo "[*] Starting Tree Topology (depth=$DEPTH, fanout=$FANOUT)..."
    sudo PYTHONPATH="$PROJECT_DIR" python3 "$PROJECT_DIR/topology/tree_topo.py" \
        --depth "$DEPTH" --fanout "$FANOUT"
else
    echo "[*] Starting Single Switch Topology..."
    sudo PYTHONPATH="$PROJECT_DIR" python3 "$PROJECT_DIR/topology/single_switch_topo.py"
fi
EOF
chmod +x "$PROJECT_DIR/run_mininet.sh"

# run_benchmark.sh
cat > "$PROJECT_DIR/run_benchmark.sh" << 'EOF'
#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE=${1:-"compare"}
echo "[*] Running benchmark: mode=$MODE"
PYTHONPATH="$PROJECT_DIR" python3 "$PROJECT_DIR/evaluation/benchmark.py" \
    --mode "$MODE" --samples 300
EOF
chmod +x "$PROJECT_DIR/run_benchmark.sh"

ok "run_controller.sh created"
ok "run_mininet.sh created"
ok "run_benchmark.sh created"

# ============================================================
# DONE
# ============================================================
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║              Setup Complete! ✓               ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  Cách chạy:"
echo ""
echo "  # Terminal 1 — Chạy Controller:"
echo "  bash run_controller.sh"
echo ""
echo "  # Terminal 2 — Chạy Mininet (cần root):"
echo "  bash run_mininet.sh"
echo ""
echo "  # Sau khi pingall OK, trong Mininet CLI:"
echo "  mininet> h2 bash traffic/ddos_traffic.sh syn 10.0.0.1 80"
echo ""
echo "  # Benchmark:"
echo "  bash run_benchmark.sh compare"
echo ""

#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive
echo "━━━ [1/4] Installing Python 3.10 ━━━"
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update -qq
sudo apt-get install -y -q python3.10 python3.10-venv python3.10-dev python3.10-distutils
echo "━━━ [2/4] Creating Python 3.10 venv ━━━"
rm -rf venv_ryu
python3.10 -m venv venv_ryu
source venv_ryu/bin/activate
echo "━━━ [3/4] Installing Packages (using cache) ━━━"
pip install numpy scikit-learn --quiet
pip install torch --index-url https://download.pytorch.org/whl/cpu --quiet
pip install setuptools==65.7.0 wheel --quiet
echo "━━━ [4/4] Installing Ryu ━━━"
pip install eventlet==0.30.2 ryu --quiet
echo "━━━ Verification ━━━"
python -c "import ryu, torch, sklearn, pickle; print('✅ ALL INSTALLED SUCCESSFULLY!')"
# Update run scripts to use venv_ryu
sed -i 's/venv/venv_ryu/g' run_controller.sh run_mininet.sh run_benchmark.sh
echo "✅ Setup Complete! You can now run: bash run_controller.sh"

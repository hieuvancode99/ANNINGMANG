#!/bin/bash
# Script cài đặt môi trường CỐ ĐỊNH cho máy ảo VMware (Ubuntu)
# CẢNH BÁO: CHỈ CHẠY 1 LẦN DUY NHẤT SAU KHI COPY CODE VÀO MÁY ẢO!

echo "=== 1. Cài đặt Python 3.10 (tương thích tốt nhất với Ryu) ==="
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update
sudo apt-get install -y python3.10 python3.10-venv python3.10-dev

echo "=== 2. Xóa môi trường ảo cũ bị lỗi (nếu có) và tạo mới ==="
rm -rf venv_ryu
python3.10 -m venv venv_ryu

echo "=== 3. Cài đặt các thư viện vào môi trường ảo ==="
source venv_ryu/bin/activate
pip install --upgrade pip
pip install setuptools==65.7.0 wheel
pip install ryu eventlet==0.30.2
pip install numpy scikit-learn
pip install torch --index-url https://download.pytorch.org/whl/cpu

echo "=========================================================="
echo "✅ HOÀN TẤT CÀI ĐẶT MÔI TRƯỜNG!"
echo "Từ nay về sau, mỗi khi bật máy, bạn chỉ cần chạy: bash run_ryu.sh"
echo "=========================================================="

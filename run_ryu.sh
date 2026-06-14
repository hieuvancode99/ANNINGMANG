#!/bin/bash
# Script khởi chạy Controller nhanh (dùng mỗi khi bật máy ảo lên)

# Lấy đường dẫn của thư mục hiện tại
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$DIR"

if [ ! -d "venv_ryu" ]; then
    echo "❌ LỖI: Chưa có môi trường ảo!"
    echo "👉 Hãy chạy lệnh 'bash setup_vmware_env.sh' trước để cài đặt (chỉ cần làm 1 lần)."
    exit 1
fi

echo "=> 1. Đang kích hoạt môi trường ảo..."
source venv_ryu/bin/activate

echo "=> 2. Khởi chạy Ryu Controller..."
ryu-manager controller/ryu_controller.py

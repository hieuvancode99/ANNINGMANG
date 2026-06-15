import sys
import re
import os

def main():
    if len(sys.argv) < 2:
        print("Sử dụng: python swap_model.py <lstm|transformer|autoencoder>")
        sys.exit(1)

    model = sys.argv[1].lower()
    if model not in ["lstm", "transformer", "autoencoder"]:
        print("❌ Lỗi: Tên model phải là lstm, transformer hoặc autoencoder")
        sys.exit(1)

    config_path = "config.py"
    if not os.path.exists(config_path):
        print(f"❌ Lỗi: Không tìm thấy file {config_path}")
        sys.exit(1)

    # Đọc nội dung file config.py
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Thay thế chuỗi ACTIVE_MODEL
    new_content = re.sub(r'^ACTIVE_MODEL\s*=\s*["\'].*?["\']', f'ACTIVE_MODEL = "{model}"', content, flags=re.MULTILINE)

    # Ghi lại file config.py
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✅ Đã đổi cấu hình sang mô hình '{model.upper()}' thành công!")
    print("👉 Lưu ý: Hãy khởi động lại Ryu Controller (Ctrl+C rồi chạy bash run_ryu.sh) để nạp mô hình mới.")

if __name__ == "__main__":
    main()

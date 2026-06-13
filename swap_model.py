import sys
import requests

def main():
    if len(sys.argv) < 2:
        print("Sử dụng: python3 swap_model.py <lstm|transformer|autoencoder>")
        sys.exit(1)

    model = sys.argv[1].lower()
    if model not in ["lstm", "transformer", "autoencoder"]:
        print("❌ Lỗi: Tên model phải là lstm, transformer hoặc autoencoder")
        sys.exit(1)

    url = "http://localhost:8080/api/model"
    print(f"[*] Đang gửi yêu cầu chuyển sang model '{model}'...")
    
    try:
        resp = requests.put(url, json={"model": model})
        if resp.status_code == 200:
            print(f"✅ THÀNH CÔNG: Controller đã chuyển sang mô hình '{model}'!")
        else:
            print(f"❌ Lỗi từ Controller: {resp.text}")
    except requests.exceptions.ConnectionError:
        print("❌ Lỗi kết nối: Không tìm thấy Controller. Đảm bảo Ryu đang chạy.")
    except Exception as e:
        print(f"❌ Lỗi không xác định: {e}")

if __name__ == "__main__":
    main()

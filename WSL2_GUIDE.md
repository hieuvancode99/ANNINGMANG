# Hướng Dẫn Chạy Trên WSL2

## Bước 0: Tìm Đường Dẫn Project Trong WSL2

Project của bạn đang ở Windows tại:
```
D:\02_Study_Materials\Ki2Nam4\AN NINH MANG\DoAnANMang\
```

Trong WSL2, đường dẫn tương ứng là:
```bash
/mnt/d/02_Study_Materials/Ki2Nam4/AN NINH MANG/DoAnANMang/
```

> **Lưu ý**: Đường dẫn có dấu cách → cần dùng dấu nháy hoặc escape `\`

---

## Bước 1: Setup Môi Trường (Chỉ Cần Làm 1 Lần)

Mở **WSL2 terminal** và chạy:

```bash
# Di chuyển vào project directory
cd "/mnt/d/02_Study_Materials/Ki2Nam4/AN NINH MANG/DoAnANMang"

# Cấp quyền execute cho script
chmod +x setup_wsl2.sh

# Chạy setup
bash setup_wsl2.sh
```

Script sẽ tự động:
- ✅ Cài hping3, iperf3, tcpdump
- ✅ Cài PyTorch (CPU), scikit-learn, numpy
- ✅ Cài Ryu SDN Framework
- ✅ Kiểm tra các file model (.pth, scaler.pkl)
- ✅ Tạo các script tiện lợi (run_controller.sh, run_mininet.sh)

---

## Bước 2: Chạy Controller (Terminal 1)

```bash
cd "/mnt/d/02_Study_Materials/Ki2Nam4/AN NINH MANG/DoAnANMang"
bash run_controller.sh
```

Hoặc thủ công:
```bash
PYTHONPATH="/mnt/d/02_Study_Materials/Ki2Nam4/AN NINH MANG/DoAnANMang" \
    ryu-manager controller/ryu_controller.py --observe-links
```

**Output mong đợi:**
```
loading app controller/ryu_controller.py
loading app ryu.controller.ofp_handler
[Controller] SDNDDoSController started | model=lstm | poll_cycle=5s
```

---

## Bước 3: Chạy Mininet (Terminal 2)

```bash
cd "/mnt/d/02_Study_Materials/Ki2Nam4/AN NINH MANG/DoAnANMang"
bash run_mininet.sh
```

Hoặc thủ công:
```bash
sudo PYTHONPATH="/mnt/d/02_Study_Materials/Ki2Nam4/AN NINH MANG/DoAnANMang" \
    python3 topology/single_switch_topo.py
```

**Sau khi khởi động, test connectivity:**
```
mininet> pingall
# Phải đạt 0% packet loss trước khi tiếp tục!
```

---

## Bước 4: Sinh Traffic DDoS Để Test

**Trong Mininet CLI:**
```
# SYN Flood từ h2 → h1
mininet> h2 bash /mnt/d/02_Study_Materials/Ki2Nam4/AN\ NINH\ MANG/DoAnANMang/traffic/ddos_traffic.sh syn 10.0.0.1 80 &

# UDP Flood
mininet> h3 bash traffic/ddos_traffic.sh udp 10.0.0.1 53 &

# Normal traffic từ h4
mininet> h4 bash traffic/normal_traffic.sh client 10.0.0.1 60 &
```

**Xem log trong Terminal 1 (Controller):**
```
[ALERT] DDoS detected! flow=1|0|1|... | model=lstm | confidence=0.9823 | infer=2.34ms
[*] DROP rule installed: dpid=0x1 | timeout=60s
```

---

## Bước 5: Scalability Test (Tree Topology)

```bash
# Tree depth=2 (9 hosts)
bash run_mininet.sh tree 2 3

# Tree depth=3 (27 hosts)
bash run_mininet.sh tree 3 3
```

---

## Bước 6: Benchmark

```bash
# So sánh latency 3 models
bash run_benchmark.sh compare

# Đo overhead
PYTHONPATH="." python3 evaluation/benchmark.py --mode overhead \
    --n-flows 100 --n-switches 3
```

---

## Bước 7: Hot-Swap Model

Trong lúc hệ thống đang chạy, thay đổi `ACTIVE_MODEL` trong `config.py`:
```python
ACTIVE_MODEL = "transformer"   # đổi từ lstm sang transformer
```

Hoặc Controller sẽ tự reload nếu bạn gọi:
```python
# Từ Python shell
controller.swap_model("transformer")
```

---

## Troubleshooting WSL2

### Lỗi: "Cannot connect to controller"
```bash
# Kiểm tra Ryu đang lắng nghe port 6653
ss -tlnp | grep 6653

# Nếu không có, kiểm tra firewall WSL2
sudo ufw allow 6653/tcp
```

### Lỗi: "No module named 'ryu'"
```bash
pip3 install ryu
# Nếu vẫn lỗi:
pip3 install eventlet==0.30.2
pip3 install ryu
```

### Lỗi: "RTNETLINK answers: Operation not permitted" (Mininet)
```bash
# Mininet cần quyền root trong WSL2
sudo mn --test pingall   # Test Mininet độc lập
```

### Lỗi: "torch not found" khi chạy ryu-manager
```bash
# Cần export PYTHONPATH trước
export PYTHONPATH="/mnt/d/02_Study_Materials/Ki2Nam4/AN NINH MANG/DoAnANMang"
ryu-manager controller/ryu_controller.py
```

### Kiểm tra scaler
```bash
cd "/mnt/d/02_Study_Materials/Ki2Nam4/AN NINH MANG/DoAnANMang"
python3 -c "
import pickle
s = pickle.load(open('scaler.pkl', 'rb'))
print('Type:', type(s).__name__)
import numpy as np
test = np.array([[1.0, 100.0, 50000.0, 5000.0, 10.0, 6.0]])
print('Transform test:', s.transform(test))
"
```

---

## Cấu Trúc Terminal Khuyến Nghị

```
┌──────────────────────┬──────────────────────┐
│  Terminal 1 (WSL2)   │  Terminal 2 (WSL2)   │
│                      │                      │
│  bash run_           │  bash run_           │
│  controller.sh       │  mininet.sh          │
│                      │                      │
│  [ALERT] DDoS! ...   │  mininet> pingall    │
│  [OK] Normal flow    │  mininet> h2 bash    │
│  ...                 │  traffic/ddos_...    │
└──────────────────────┴──────────────────────┘
```

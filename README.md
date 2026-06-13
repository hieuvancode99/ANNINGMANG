# SDN DDoS Detection System — README

## Cấu Trúc Dự Án

```
DoAnANMang/
├── config.py                    # ⚙️  Tham số cấu hình toàn cục
├── requirements.txt             # 📦 Dependencies
│
├── controller/
│   ├── model_definitions.py     # 🧠 3 model classes (LSTM, Transformer, AE)
│   ├── inference_engine.py      # ⚡ Hot-swap + Queue-based inference
│   ├── feature_extractor.py     # 📊 Delta features + Sliding window
│   └── ryu_controller.py        # 🎮 Main Ryu SDN Controller
│
├── topology/
│   ├── single_switch_topo.py    # 🌐 1 switch, 4 hosts (test)
│   └── tree_topo.py             # 🌲 Tree topology (scalability)
│
├── traffic/
│   ├── normal_traffic.sh        # 📶 Sinh traffic bình thường (iperf3)
│   └── ddos_traffic.sh          # 💣 Sinh DDoS traffic (hping3)
│
├── evaluation/
│   ├── benchmark.py             # 📏 Đo latency, overhead, scalability
│   └── results/                 # 📁 CSV + JSON kết quả
│
└── [Pre-trained Models]
    ├── sdn_lstm_model.pth
    ├── sdn_transformer_model.pth
    ├── sdn_autoencoder_model.pth
    └── scaler.pkl
```

---

## Quick Start (Trên Linux)

### 1. Cài đặt dependencies
```bash
pip install -r requirements.txt
pip install ryu
sudo apt-get install mininet hping3 iperf3
```

### 2. Chạy Ryu Controller
```bash
# Terminal 1
ryu-manager controller/ryu_controller.py --observe-links
```

### 3. Chạy Mininet Topology
```bash
# Terminal 2
sudo python topology/single_switch_topo.py
```

### 4. Test kết nối
```
mininet> pingall
# Phải đạt 0% packet loss
```

### 5. Sinh traffic DDoS để test
```
# Terminal trong Mininet
mininet> h2 bash traffic/ddos_traffic.sh syn h1 80
```

### 6. Xem log phát hiện DDoS
```bash
tail -f sdn_detection.log
```

---

## Hot-Swap Model

Chỉnh `ACTIVE_MODEL` trong `config.py`:
```python
ACTIVE_MODEL = "lstm"         # Hoặc "transformer" hoặc "autoencoder"
```

Hoặc gọi từ Python:
```python
controller.swap_model("transformer")
```

---

## Benchmark

```bash
# So sánh latency 3 models
python evaluation/benchmark.py --mode compare --samples 300

# Đo overhead theo polling cycle
python evaluation/benchmark.py --mode overhead --n-flows 100 --n-switches 3

# Benchmark 1 model cụ thể
python evaluation/benchmark.py --mode latency --model lstm --samples 500
```

---

## Model Architecture

| Model         | Input Shape     | Output       | Threshold  |
|---------------|-----------------|--------------|------------|
| AnomalyLSTM   | (1, 10, 6)      | Prob [0,1]   | > 0.5      |
| SDNTransformer| (1, 10, 6)      | Prob [0,1]   | > 0.5      |
| DeepAutoencoder| (1, 6)         | MSE loss     | > 0.002576 |

**Features**: `['duration', 'packet_count', 'byte_count', 'byte_rate', 'packet_rate', 'Protocol']`

**Labels**: `0 = Normal`, `1 = DDoS/Anomaly`

---

## Kiểm Tra Scaler

```bash
python -c "
import pickle
s = pickle.load(open('scaler.pkl', 'rb'))
print('Scaler type:', type(s).__name__)
print('Feature means:', s.mean_ if hasattr(s, 'mean_') else s.data_min_)
"
```

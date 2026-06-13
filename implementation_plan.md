# Đồ Án An Ninh Mạng: SDN + AI DDoS Detection System
## Kế Hoạch Triển Khai (Đã Cập Nhật Đầy Đủ)

---

## Tổng Quan

Xây dựng hệ thống phát hiện tấn công DDoS theo thời gian thực trên nền tảng SDN, tích hợp **3 mô hình Deep Learning** (LSTM, Transformer, Autoencoder) train trên **InSDN Dataset**. Controller Ryu thu thập OpenFlow Flow Stats, tính Delta features, chuẩn hóa bằng scaler đã train, và dùng mô hình đã chọn để phân loại.

**Chiến lược mô hình:** Hot-swap (1 mô hình active tại 1 thời điểm)  
**Kiến trúc:** Hybrid Queue-based (Controller thread + Worker thread cho Inference)

---

## ✅ Thông Tin Model Đã Xác Nhận (từ Notebooks)

### Features (thứ tự quan trọng — phải đúng khi inference)
```python
features = ['duration', 'packet_count', 'byte_count', 'byte_rate', 'packet_rate', 'Protocol']
# Tổng: 6 features
```

> [!IMPORTANT]
> Trong notebook tên column là `'duration'` (không phải `'flow_duration'`). Khi tính từ OFPFlowStats, dùng: `duration_sec + duration_nsec/1e9`

### Label Encoding
```
Label_Binary = 0  →  Normal (traffic bình thường)
Label_Binary = 1  →  Anomaly / DDoS (traffic tấn công)
```

### Scaler
- **File**: `scaler.pkl` (đã có trong thư mục)
- **Loại scaler**: Cần kiểm tra bằng `pickle.load()` — nhiều khả năng là `StandardScaler` hoặc `MinMaxScaler`
- **Áp dụng**: Gọi `scaler.transform(feature_vector)` trước khi đưa vào model

---

## 🧠 Kiến Trúc 3 Mô Hình

### 1. AnomalyLSTM (LSTM)
```python
class AnomalyLSTM(nn.Module):
    def __init__(self, input_size=6, hidden_size=64, num_layers=2, num_classes=1):
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                            batch_first=True, dropout=0.2)
        self.fc = nn.Linear(hidden_size, num_classes)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):  # x shape: (batch, seq_len=10, features=6)
        out, _ = self.lstm(x, (h0, c0))
        out = out[:, -1, :]  # Lấy timestep cuối
        return self.sigmoid(self.fc(out))  # Output: (batch, 1) ∈ [0,1]
```
**Input shape**: `(batch, seq_length=10, input_size=6)`  
**Output**: Xác suất ∈ [0,1] — threshold 0.5 → DDoS nếu > 0.5

### 2. SDNTransformer (Transformer)
```python
class SDNTransformer(nn.Module):
    def __init__(self, input_size=6, d_model=64, nhead=4,
                 num_layers=2, seq_length=10, num_classes=1):
        self.input_projection = nn.Linear(input_size, d_model)
        self.pos_encoder = nn.Parameter(torch.randn(1, seq_length, d_model))
        encoder_layers = nn.TransformerEncoderLayer(d_model=64, nhead=4,
                                                     batch_first=True, dropout=0.2)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layers, num_layers=2)
        self.fc = nn.Linear(d_model, num_classes)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):  # x shape: (batch, seq_len=10, features=6)
        x = self.input_projection(x) + self.pos_encoder
        x = self.transformer_encoder(x)
        x = x[:, -1, :]  # Lấy timestep cuối
        return self.sigmoid(self.fc(x))  # Output: (batch, 1) ∈ [0,1]
```
**Input shape**: `(batch, seq_length=10, input_size=6)`  
**Output**: Xác suất ∈ [0,1] — threshold 0.5 → DDoS nếu > 0.5

### 3. DeepAutoencoder (Autoencoder)
```python
class DeepAutoencoder(nn.Module):
    def __init__(self, input_dim=6):
        self.encoder = nn.Sequential(
            nn.Linear(6, 16), nn.ReLU(),
            nn.Linear(16, 8), nn.ReLU(),
            nn.Linear(8, 3)  # Latent space
        )
        self.decoder = nn.Sequential(
            nn.Linear(3, 8), nn.ReLU(),
            nn.Linear(8, 16), nn.ReLU(),
            nn.Linear(16, 6), nn.Sigmoid()
        )

    def forward(self, x):  # x shape: (batch, features=6)
        return self.decoder(self.encoder(x))
```
**Input shape**: `(batch, input_dim=6)` — KHÔNG có seq_length!  
**Output**: Reconstruction — tính MSE loss để detect anomaly  
**Threshold**: **0.002576** (percentile 95 trên Normal train data)

> [!WARNING]
> **Khác biệt quan trọng**: LSTM và Transformer nhận input 3D `(batch, 10, 6)`, còn Autoencoder nhận input 2D `(batch, 6)` — là giá trị của 1 flow duy nhất, không phải sequence!

---

## 📁 Cấu Trúc Thư Mục Dự Án

```
DoAnANMang/
├── models/                              # Models (đã có)
│   ├── sdn_lstm_model.pth              ✅
│   ├── sdn_transformer_model.pth       ✅
│   ├── sdn_autoencoder_model.pth       ✅
│   └── scaler.pkl                      ✅
│
├── controller/
│   ├── ryu_controller.py               [NEW] Controller chính
│   ├── model_definitions.py            [NEW] 3 class model
│   ├── feature_extractor.py            [NEW] Delta + normalization
│   └── inference_engine.py             [NEW] Hot-swap + Queue
│
├── topology/
│   ├── single_switch_topo.py           [NEW] 1 switch, 4 hosts
│   └── tree_topo.py                    [NEW] Tree(depth=2, fanout=3)
│
├── traffic/
│   ├── normal_traffic.sh               [NEW] iperf bình thường
│   └── ddos_traffic.sh                 [NEW] hping3 SYN/UDP flood
│
├── evaluation/
│   ├── benchmark.py                    [NEW] Đo latency, overhead
│   └── results/                        Thư mục lưu CSV
│
├── config.py                           [NEW] Tham số cấu hình
└── requirements.txt                    [NEW] Dependencies
```

---

## Giai Đoạn 1: Network Foundation

### [NEW] `topology/single_switch_topo.py`
```python
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch

class SingleSwitchTopo(Topo):
    def build(self):
        s1 = self.addSwitch('s1')
        for i in range(1, 5):
            h = self.addHost(f'h{i}', ip=f'10.0.0.{i}/24')
            self.addLink(h, s1)
```

### [NEW] `topology/tree_topo.py`
```python
class TreeTopoCustom(Topo):
    def build(self, depth=2, fanout=3):
        # Core switch s1
        # Edge switches s2, s3, s4
        # 9 hosts h1..h9
```

### L2 Learning Switch (trong ryu_controller.py)
- `EventOFPPacketIn` handler với MAC learning table
- FLOOD khi chưa biết destination, forward khi đã học
- **Test**: `mininet> pingall` phải đạt **0% dropped**

---

## Giai Đoạn 2: Data Engineering Pipeline

### [NEW] `config.py`
```python
POLLING_CYCLE = 5          # giây — điều chỉnh để test overhead
ACTIVE_MODEL = "lstm"       # "lstm" | "transformer" | "autoencoder"
ALERT_THRESHOLD = 0.5       # ngưỡng cho LSTM/Transformer
AUTOENCODER_THRESHOLD = 0.002576  # percentile 95 từ training
SEQ_LENGTH = 10             # sliding window cho LSTM/Transformer
MODEL_DIR = "."             # thư mục chứa .pth và scaler.pkl

FEATURES = ['duration', 'packet_count', 'byte_count',
            'byte_rate', 'packet_rate', 'Protocol']
```

### [NEW] `controller/feature_extractor.py`

**State Table** (lưu giá trị chu kỳ trước):
```python
prev_stats = {}
# key: (dpid, cookie, priority, match_str)
# value: {'packet_count': int, 'byte_count': int, 'timestamp': float}
```

**Feature Engineering từ OFPFlowStatsReply:**
| Feature | Công thức |
|---|---|
| `duration` | `duration_sec + duration_nsec/1e9` |
| `packet_count` | Giá trị tích lũy trực tiếp |
| `byte_count` | Giá trị tích lũy trực tiếp |
| `byte_rate` | `Δbyte_count / Δtime` |
| `packet_rate` | `Δpacket_count / Δtime` |
| `Protocol` | Từ match field (TCP=6, UDP=17, ICMP=1) |

**Sliding Window Buffer** (cho LSTM/Transformer):
```python
flow_history = defaultdict(deque)
# key: flow_id — value: deque(maxlen=10) chứa feature vectors
# Chỉ inference khi đủ 10 timesteps
```

**Normalization**:
```python
scaler = pickle.load(open('scaler.pkl', 'rb'))
normalized = scaler.transform([raw_features])
```

---

## Giai Đoạn 3: Inference Engine (Cốt Lõi)

### Kiến Trúc Threading

```
[Ryu Event Loop]              [Inference Worker Thread]
      |                                  |
 _poll_loop()            ┌── inference_worker()
      |                  |         |
 OFPFlowStatsReply  ─────►  data_queue.get()
      |                  |         |
 feature_extractor()─────►  model.forward()
      |                  |         |
 data_queue.put()   ─────┘  result_queue.put()
                                    |
                         [Alert Handler Thread]
                              alert_handler()
                            (log / install drop rule)
```

### [NEW] `controller/model_definitions.py`
Chứa 3 class: `AnomalyLSTM`, `SDNTransformer`, `DeepAutoencoder`  
(code y hệt trong notebook để load weights đúng)

### [NEW] `controller/inference_engine.py`

```python
class InferenceEngine:
    def __init__(self, model_name: str, model_dir: str):
        self.model_name = model_name
        self.model = self._load_model(model_name, model_dir)
        self.scaler = pickle.load(open(f'{model_dir}/scaler.pkl', 'rb'))
        self.device = torch.device('cpu')  # CPU cho realtime

    def _load_model(self, name, model_dir):
        if name == "lstm":
            model = AnomalyLSTM(input_size=6, hidden_size=64, num_layers=2)
        elif name == "transformer":
            model = SDNTransformer(input_size=6, d_model=64, nhead=4,
                                   num_layers=2, seq_length=10)
        elif name == "autoencoder":
            model = DeepAutoencoder(input_dim=6)
        model.load_state_dict(torch.load(f'{model_dir}/sdn_{name}_model.pth',
                                          map_location='cpu'))
        model.eval()
        return model

    def swap_model(self, new_model_name):
        """Hot-swap không cần restart Controller"""
        self.model = self._load_model(new_model_name, self.model_dir)
        self.model_name = new_model_name

    def predict(self, feature_sequence) -> dict:
        """
        feature_sequence:
          - LSTM/Transformer: np.array shape (10, 6)
          - Autoencoder:      np.array shape (6,)
        Returns: {'label': 'DDoS'/'Normal', 'confidence': float, 'latency_ms': float}
        """
        t0 = time.time()
        scaled = self.scaler.transform([feature_sequence.flatten()
                                        if self.model_name == 'autoencoder'
                                        else feature_sequence[-1]])

        with torch.no_grad():
            if self.model_name in ['lstm', 'transformer']:
                x = torch.tensor(feature_sequence, dtype=torch.float32).unsqueeze(0)
                prob = self.model(x).item()
                label = 'DDoS' if prob > ALERT_THRESHOLD else 'Normal'
                confidence = prob
            else:  # autoencoder
                x = torch.tensor(scaled, dtype=torch.float32)
                recon = self.model(x)
                mse = torch.mean((recon - x) ** 2).item()
                label = 'DDoS' if mse > AUTOENCODER_THRESHOLD else 'Normal'
                confidence = mse

        latency_ms = (time.time() - t0) * 1000
        return {'label': label, 'confidence': confidence, 'latency_ms': latency_ms}
```

---

## Giai Đoạn 4: Evaluation & Benchmark

### Traffic Scripts

**`traffic/ddos_traffic.sh`**:
```bash
#!/bin/bash
# SYN Flood
hping3 -S --flood -V -p 80 10.0.0.1
# UDP Flood
# hping3 --udp -p 53 --flood 10.0.0.1
```

**`traffic/normal_traffic.sh`**:
```bash
#!/bin/bash
# Normal TCP traffic via iperf
iperf -c 10.0.0.1 -t 30 -i 1
```

### 3 Chỉ Số Cần Đo

| Metric | Cách đo | Unit |
|---|---|---|
| **Latency** | `time.time()` từ poll → alert | ms |
| **Scalability** | Tăng hosts 4→9→27, đo CPU% | % |
| **Overhead** | Đếm OpenFlow Stats packets/s | % bandwidth |

### So Sánh 3 Model

| Model | Input | Avg Latency | Max Latency | Accuracy |
|---|---|---|---|---|
| LSTM | (1, 10, 6) | ? ms | ? ms | ~99%* |
| Transformer | (1, 10, 6) | ? ms | ? ms | ~98%* |
| Autoencoder | (1, 6) | ? ms | ? ms | ~72%* |

*Kết quả từ notebook training

---

## Thứ Tự Triển Khai (Execution Order)

```
1. config.py                     ← Tham số toàn cục
2. model_definitions.py          ← 3 class model
3. inference_engine.py           ← Load model + predict
4. feature_extractor.py          ← Delta + sliding window
5. ryu_controller.py             ← L2 switch + poll + queue
6. single_switch_topo.py         ← Test topology
7. tree_topo.py                  ← Scale topology
8. traffic scripts               ← Traffic generators
9. benchmark.py                  ← Evaluation
```

---

## Verification Plan

1. **Phase 1**: `mininet> pingall` → **0% dropped**
2. **Phase 2**: Print feature vector ra console mỗi poll — kiểm tra delta đúng, không có NaN
3. **Phase 3**: Inject `ddos_traffic.sh` → alert phải xuất hiện trong `2 × POLLING_CYCLE`
4. **Phase 4**: Chạy benchmark 3 lần, lấy kết quả trung bình, vẽ đồ thị

---

## Open Questions

> [!NOTE]
> **Cần kiểm tra thêm:**
> 1. Kiểu scaler trong `scaler.pkl` — chạy `python -c "import pickle; s=pickle.load(open('scaler.pkl','rb')); print(type(s))"` để xác nhận
> 2. Scaler được fit trên features nào? Cần đảm bảo thứ tự features khi transform khớp với lúc training
> 3. Mininet có được cài đặt sẵn trên môi trường Linux của bạn chưa?
> 4. Ryu framework version? (`ryu-manager --version`)

---

> [!IMPORTANT]
> **Phê duyệt kế hoạch này để tôi bắt đầu code toàn bộ hệ thống!**

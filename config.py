"""
config.py — Tham số cấu hình toàn cục cho hệ thống SDN DDoS Detection

Hỗ trợ cả:
    - WSL2:    /mnt/d/02_Study_Materials/.../DoAnANMang/
    - Linux:   /home/user/DoAnANMang/
    - Windows: D:\\02_Study_Materials\\...\\DoAnANMang\\
"""

import os
import sys
import platform

# ============================================================
# ĐƯỜNG DẪN
# ============================================================
# Thư mục chứa file .pth và scaler.pkl
MODEL_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_PATHS = {
    "lstm":        os.path.join(MODEL_DIR, "sdn_lstm_model.pth"),
    "transformer": os.path.join(MODEL_DIR, "sdn_transformer_model.pth"),
    "autoencoder": os.path.join(MODEL_DIR, "sdn_autoencoder_model.pth"),
}
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.pkl")

# ============================================================
# MÔ HÌNH ĐANG HOẠT ĐỘNG
# Thay đổi giá trị này để hot-swap model:
#   "lstm"        → AnomalyLSTM
#   "transformer" → SDNTransformer
#   "autoencoder" → DeepAutoencoder
# ============================================================
ACTIVE_MODEL = "lstm"

# ============================================================
# HYPERPARAMETERS MÔ HÌNH (phải khớp với lúc train)
# ============================================================
# LSTM
LSTM_INPUT_SIZE  = 6
LSTM_HIDDEN_SIZE = 64
LSTM_NUM_LAYERS  = 2

# Transformer
TRANSFORMER_INPUT_SIZE = 6
TRANSFORMER_D_MODEL    = 64
TRANSFORMER_NHEAD      = 4
TRANSFORMER_NUM_LAYERS = 2
TRANSFORMER_SEQ_LENGTH = 10   # phải bằng SEQ_LENGTH

# Autoencoder
AE_INPUT_DIM = 6

# ============================================================
# FEATURES (thứ tự phải giống lúc train)
# ============================================================
FEATURES = ['duration', 'packet_count', 'byte_count',
            'byte_rate', 'packet_rate', 'Protocol']

# ============================================================
# INFERENCE THRESHOLDS
# ============================================================
# LSTM / Transformer: phân loại theo xác suất
ALERT_THRESHOLD = 0.5           # > 0.5 → DDoS

# Autoencoder: phân loại theo MSE reconstruction error
# Giá trị này lấy từ percentile 95 trên Normal train data
AUTOENCODER_THRESHOLD = 0.002576

# ============================================================
# SLIDING WINDOW (cho LSTM & Transformer)
# ============================================================
SEQ_LENGTH = 10   # số timestep lịch sử cần thu thập trước khi inference

# ============================================================
# POLLING CONFIGURATION
# ============================================================
# Chu kỳ gửi OFPFlowStatsRequest (giây)
# Thay đổi để phân tích overhead: 1s, 5s, 10s
POLLING_CYCLE = 5

# ============================================================
# QUEUE CONFIGURATION
# ============================================================
DATA_QUEUE_MAXSIZE   = 200   # buffer feature vectors chờ inference
RESULT_QUEUE_MAXSIZE = 200   # buffer kết quả chờ xử lý

# ============================================================
# LABEL ENCODING
# ============================================================
LABEL_NORMAL  = 0   # traffic bình thường
LABEL_ANOMALY = 1   # DDoS / tấn công

# ============================================================
# MITIGATION
# ============================================================
# Tự động install drop rule khi phát hiện DDoS
AUTO_DROP = True
DROP_RULE_PRIORITY = 100
DROP_RULE_TIMEOUT  = 60   # giây

# ============================================================
# LOGGING
# ============================================================
LOG_FILE       = "sdn_detection.log"
LOG_LEVEL      = "INFO"   # DEBUG, INFO, WARNING, ERROR
RESULTS_DIR    = os.path.join(MODEL_DIR, "evaluation", "results")

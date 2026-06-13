"""
model_definitions.py — Định nghĩa 3 class model (y hệt lúc train)

Các class này phải GIỐNG HỆT với code trong notebook để
torch.load_state_dict() hoạt động đúng.

Models:
    1. AnomalyLSTM       — LSTM binary classifier
    2. SDNTransformer    — Transformer binary classifier
    3. DeepAutoencoder   — Unsupervised anomaly detector
"""

import torch
import torch.nn as nn


# ============================================================
# 1. LSTM MODEL
# ============================================================
class AnomalyLSTM(nn.Module):
    """
    LSTM binary classifier cho SDN flow anomaly detection.

    Input:  (batch_size, seq_length=10, input_size=6)
    Output: (batch_size, 1)  — xác suất ∈ [0,1]
            > ALERT_THRESHOLD → DDoS (Label=1)
    """

    def __init__(self, input_size=6, hidden_size=64, num_layers=2, num_classes=1):
        super(AnomalyLSTM, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers  = num_layers

        self.lstm = nn.LSTM(
            input_size,
            hidden_size,
            num_layers,
            batch_first=True,
            dropout=0.2
        )
        self.fc      = nn.Linear(hidden_size, num_classes)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        # x shape: (batch, seq_len, input_size)
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)

        out, _ = self.lstm(x, (h0, c0))
        out = out[:, -1, :]   # Lấy output tại timestep cuối cùng
        out = self.fc(out)
        out = self.sigmoid(out)
        return out   # shape: (batch, 1)


# ============================================================
# 2. TRANSFORMER MODEL
# ============================================================
class SDNTransformer(nn.Module):
    """
    Transformer Encoder binary classifier cho SDN flow anomaly detection.

    Input:  (batch_size, seq_length=10, input_size=6)
    Output: (batch_size, 1)  — xác suất ∈ [0,1]
            > ALERT_THRESHOLD → DDoS (Label=1)
    """

    def __init__(self, input_size=6, d_model=64, nhead=4,
                 num_layers=2, seq_length=10, num_classes=1):
        super(SDNTransformer, self).__init__()

        # Chiếu đầu vào 6 chiều lên không gian d_model
        self.input_projection = nn.Linear(input_size, d_model)

        # Positional Encoding (learnable)
        self.pos_encoder = nn.Parameter(torch.randn(1, seq_length, d_model))

        # Transformer Encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            batch_first=True,
            dropout=0.2
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # Lớp phân loại
        self.fc      = nn.Linear(d_model, num_classes)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        # x shape: (batch, seq_len, input_size)
        x = self.input_projection(x)   # → (batch, seq_len, d_model)
        x = x + self.pos_encoder       # Thêm positional encoding

        x = self.transformer_encoder(x)  # → (batch, seq_len, d_model)
        x = x[:, -1, :]                  # Lấy timestep cuối

        out = self.fc(x)
        out = self.sigmoid(out)
        return out   # shape: (batch, 1)


# ============================================================
# 3. AUTOENCODER MODEL
# ============================================================
class DeepAutoencoder(nn.Module):
    """
    Deep Autoencoder cho unsupervised anomaly detection.

    Input:  (batch_size, input_dim=6)  — KHÔNG có seq_length!
    Output: (batch_size, input_dim=6)  — reconstruction

    Anomaly detection:
        mse = mean((output - input)^2)
        DDoS nếu mse > AUTOENCODER_THRESHOLD (0.002576)
    """

    def __init__(self, input_dim=6):
        super(DeepAutoencoder, self).__init__()

        # Encoder: 6 → 16 → 8 → 3 (latent space)
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 8),
            nn.ReLU(),
            nn.Linear(8, 3)    # Latent space
        )

        # Decoder: 3 → 8 → 16 → 6
        self.decoder = nn.Sequential(
            nn.Linear(3, 8),
            nn.ReLU(),
            nn.Linear(8, 16),
            nn.ReLU(),
            nn.Linear(16, input_dim),
            nn.Sigmoid()   # Output ∈ [0,1] vì data đã được scale
        )

    def forward(self, x):
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded   # shape: (batch, input_dim)


# ============================================================
# FACTORY FUNCTION
# ============================================================
def create_model(model_name: str):
    """
    Tạo model instance theo tên.

    Args:
        model_name: "lstm" | "transformer" | "autoencoder"

    Returns:
        model instance (chưa load weights)
    """
    from config import (
        LSTM_INPUT_SIZE, LSTM_HIDDEN_SIZE, LSTM_NUM_LAYERS,
        TRANSFORMER_INPUT_SIZE, TRANSFORMER_D_MODEL,
        TRANSFORMER_NHEAD, TRANSFORMER_NUM_LAYERS, TRANSFORMER_SEQ_LENGTH,
        AE_INPUT_DIM
    )

    if model_name == "lstm":
        return AnomalyLSTM(
            input_size=LSTM_INPUT_SIZE,
            hidden_size=LSTM_HIDDEN_SIZE,
            num_layers=LSTM_NUM_LAYERS
        )
    elif model_name == "transformer":
        return SDNTransformer(
            input_size=TRANSFORMER_INPUT_SIZE,
            d_model=TRANSFORMER_D_MODEL,
            nhead=TRANSFORMER_NHEAD,
            num_layers=TRANSFORMER_NUM_LAYERS,
            seq_length=TRANSFORMER_SEQ_LENGTH
        )
    elif model_name == "autoencoder":
        return DeepAutoencoder(input_dim=AE_INPUT_DIM)
    else:
        raise ValueError(f"Unknown model name: '{model_name}'. "
                         f"Choose from: 'lstm', 'transformer', 'autoencoder'")

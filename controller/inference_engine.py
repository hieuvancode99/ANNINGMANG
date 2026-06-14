"""
inference_engine.py — Hot-swap Inference Engine với Queue-based Pipeline

Kiến trúc:
    [Ryu Event Loop] → data_queue → [Inference Worker] → result_queue → [Alert Handler]

Features:
    - Hot-swap: đổi model mà không restart Controller
    - Thread-safe Queue để không block Ryu event loop
    - Đo latency tự động mỗi lần predict
    - Hỗ trợ cả 3 loại model: LSTM, Transformer, Autoencoder
"""

import os
import sys
import time
import pickle
import logging
import threading
from queue import Queue, Empty

import torch
import numpy as np

# Thêm thư mục gốc vào path để import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    MODEL_PATHS, SCALER_PATH,
    ALERT_THRESHOLD, AUTOENCODER_THRESHOLD,
    DATA_QUEUE_MAXSIZE, RESULT_QUEUE_MAXSIZE,
    SEQ_LENGTH, FEATURES
)
from controller.model_definitions import create_model

logger = logging.getLogger(__name__)


# ============================================================
# INFERENCE ENGINE
# ============================================================
class InferenceEngine:
    """
    Engine thực hiện inference với hot-swap model và queue-based pipeline.

    Usage:
        engine = InferenceEngine("lstm")
        engine.start()                    # Khởi động worker threads

        engine.submit(flow_id, features)  # Đưa data vào queue

        result = engine.get_result()      # Lấy kết quả (non-blocking)

        engine.swap_model("transformer")  # Hot-swap không cần restart

        engine.stop()                     # Dừng worker threads
    """

    def __init__(self, model_name: str, on_alert=None):
        """
        Args:
            model_name: "lstm" | "transformer" | "autoencoder"
            on_alert:   callback(flow_id, result) khi phát hiện DDoS
        """
        self._lock       = threading.Lock()
        self._model_name = None
        self._model      = None
        self._scaler     = None
        self._device     = torch.device("cpu")

        self.data_queue   = Queue(maxsize=DATA_QUEUE_MAXSIZE)
        self.result_queue = Queue(maxsize=RESULT_QUEUE_MAXSIZE)

        self._running  = False
        self._worker   = None
        self._alerter  = None
        self.on_alert  = on_alert   # callback khi detect DDoS

        # Thống kê latency
        self.latency_stats = {
            "count": 0,
            "total_ms": 0.0,
            "max_ms": 0.0,
            "min_ms": 0.0,
        }

        # Load model và scaler
        self._load_scaler()
        self.swap_model(model_name)

    # ----------------------------------------------------------
    # PUBLIC API
    # ----------------------------------------------------------
    def start(self):
        """Khởi động inference worker thread và alert handler thread."""
        self._running = True

        self._worker = threading.Thread(
            target=self._inference_worker,
            name="InferenceWorker",
            daemon=True
        )
        self._worker.start()

        self._alerter = threading.Thread(
            target=self._alert_handler,
            name="AlertHandler",
            daemon=True
        )
        self._alerter.start()

        logger.info(f"[InferenceEngine] Started with model='{self._model_name}'")

    def stop(self):
        """Dừng tất cả worker threads."""
        self._running = False
        # Gửi sentinel để unblock các thread đang chờ
        self.data_queue.put(None)
        self.result_queue.put(None)
        if self._worker:
            self._worker.join(timeout=5)
        if self._alerter:
            self._alerter.join(timeout=5)
        logger.info("[InferenceEngine] Stopped.")

    def submit(self, flow_id: str, feature_sequence: np.ndarray):
        """
        Đưa feature sequence vào data_queue để xử lý bất đồng bộ.

        Args:
            flow_id:          ID định danh flow (dpid + match)
            feature_sequence: np.ndarray
                - LSTM/Transformer: shape (SEQ_LENGTH, num_features)
                - Autoencoder:      shape (num_features,)
        """
        try:
            self.data_queue.put_nowait({
                "flow_id":          flow_id,
                "feature_sequence": feature_sequence,
                "submit_time":      time.time(),
            })
        except Exception:
            logger.warning(f"[InferenceEngine] data_queue full! Dropping flow {flow_id}")

    def get_result(self):
        """
        Lấy kết quả từ result_queue (non-blocking).

        Returns:
            dict hoặc None nếu queue rỗng
        """
        try:
            return self.result_queue.get_nowait()
        except Empty:
            return None

    def swap_model(self, new_model_name: str):
        """
        Hot-swap model không cần restart Controller.

        Args:
            new_model_name: "lstm" | "transformer" | "autoencoder"
        """
        logger.info(f"[InferenceEngine] Swapping model: "
                    f"'{self._model_name}' → '{new_model_name}'")
        new_model = create_model(new_model_name)
        model_path = MODEL_PATHS[new_model_name]

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")

        state_dict = torch.load(model_path, map_location=self._device)
        new_model.load_state_dict(state_dict)
        new_model.eval()
        new_model.to(self._device)

        with self._lock:
            self._model      = new_model
            self._model_name = new_model_name

        # Reset latency stats
        self.latency_stats = {
            "count": 0, "total_ms": 0.0,
            "max_ms": 0.0, "min_ms": 0.0,
        }
        logger.info(f"[InferenceEngine] Model swapped to '{new_model_name}' ✓")

    def get_latency_stats(self) -> dict:
        """Trả về thống kê latency."""
        stats = dict(self.latency_stats)
        if stats["count"] > 0:
            stats["avg_ms"] = stats["total_ms"] / stats["count"]
        else:
            stats["avg_ms"] = 0.0
        return stats

    # ----------------------------------------------------------
    # INTERNAL: Load Scaler
    # ----------------------------------------------------------
    def _load_scaler(self):
        """Load scaler.pkl từ disk."""
        if not os.path.exists(SCALER_PATH):
            raise FileNotFoundError(f"Scaler not found: {SCALER_PATH}")
        with open(SCALER_PATH, "rb") as f:
            self._scaler = pickle.load(f)
        logger.info(f"[InferenceEngine] Scaler loaded: {type(self._scaler).__name__}")

    # ----------------------------------------------------------
    # INTERNAL: Inference Worker Thread
    # ----------------------------------------------------------
    def _inference_worker(self):
        """Worker thread: lấy data từ queue → normalize → predict → đưa result vào queue."""
        logger.info("[InferenceWorker] Thread started.")

        while self._running:
            try:
                item = self.data_queue.get(timeout=1.0)
            except Empty:
                continue

            if item is None:   # sentinel
                break

            t_start = time.time()

            try:
                result = self._predict(item)
            except Exception as e:
                logger.error(f"[InferenceWorker] Predict error: {e}", exc_info=True)
                continue

            # Tính tổng latency (submit → result)
            total_latency_ms = (time.time() - item["submit_time"]) * 1000
            result["total_latency_ms"] = total_latency_ms

            # Cập nhật stats
            infer_ms = result.get("infer_latency_ms", 0)
            self.latency_stats["count"]    += 1
            self.latency_stats["total_ms"] += infer_ms
            self.latency_stats["max_ms"]    = max(self.latency_stats["max_ms"], infer_ms)
            self.latency_stats["min_ms"]    = min(self.latency_stats["min_ms"], infer_ms)

            try:
                self.result_queue.put_nowait(result)
            except Exception:
                logger.warning("[InferenceWorker] result_queue full! Dropping result.")

        logger.info("[InferenceWorker] Thread stopped.")

    # ----------------------------------------------------------
    # INTERNAL: Single Prediction
    # ----------------------------------------------------------
    def _predict(self, item: dict) -> dict:
        """
        Thực hiện 1 lần inference.

        Returns dict với các keys:
            flow_id, label, confidence, infer_latency_ms, model_name
        """
        flow_id  = item["flow_id"]
        features = item["feature_sequence"]   # np.ndarray

        with self._lock:
            model_name = self._model_name
            model      = self._model

        # ============================================================
        # BYPASS BỘ LỌC CHO LƯU LƯỢNG NHỎ (TRÁNH DƯƠNG TÍNH GIẢ)
        # ============================================================
        # Thứ tự features: [duration, pkt_count, byte_count, byte_rate, pkt_rate, Protocol]
        # packet_rate nằm ở vị trí số 4.
        if len(features.shape) == 2:
            latest_packet_rate = features[-1][4]
        else:
            latest_packet_rate = features[4]
            
        # Nếu tốc độ nhỏ hơn 10 gói tin / giây (như lệnh ping), cho qua luôn là Normal
        if latest_packet_rate < 10.0:
            return {
                "flow_id":         flow_id,
                "label":           "Normal",
                "confidence":      0.0,
                "infer_latency_ms": 0.0,
                "model_name":      model_name,
            }

        t0 = time.time()

        if model_name in ("lstm", "transformer"):
            # features shape: (SEQ_LENGTH, num_features)
            # Normalize: chỉ dùng feature cuối làm reference transform
            # (scaler đã fit trên 1D vectors)
            normalized = self._scaler.transform(features)   # (10, 6) → (10, 6)

            x   = torch.tensor(normalized, dtype=torch.float32).unsqueeze(0)
            x   = x.to(self._device)

            with torch.no_grad():
                prob  = model(x).item()   # scalar ∈ [0,1]

            label      = "DDoS" if prob > ALERT_THRESHOLD else "Normal"
            confidence = prob

        else:   # autoencoder
            # features shape: (num_features,)
            normalized = self._scaler.transform(features.reshape(1, -1))  # (1, 6)

            x   = torch.tensor(normalized, dtype=torch.float32)
            x   = x.to(self._device)

            with torch.no_grad():
                recon = model(x)
                mse   = torch.mean((recon - x) ** 2).item()

            label      = "DDoS" if mse > AUTOENCODER_THRESHOLD else "Normal"
            confidence = mse   # dùng MSE làm "confidence" cho AE

        infer_ms = (time.time() - t0) * 1000

        return {
            "flow_id":         flow_id,
            "label":           label,
            "confidence":      confidence,
            "infer_latency_ms": infer_ms,
            "model_name":      model_name,
        }

    # ----------------------------------------------------------
    # INTERNAL: Alert Handler Thread
    # ----------------------------------------------------------
    def _alert_handler(self):
        """Alert handler thread: xử lý kết quả DDoS từ result_queue."""
        logger.info("[AlertHandler] Thread started.")

        while self._running:
            try:
                result = self.result_queue.get(timeout=1.0)
            except Empty:
                continue

            if result is None:   # sentinel
                break

            if result["label"] == "DDoS":
                logger.warning(
                    f"[ALERT] DDoS detected! "
                    f"flow={result['flow_id']} | "
                    f"model={result['model_name']} | "
                    f"confidence={result['confidence']:.4f} | "
                    f"infer={result['infer_latency_ms']:.2f}ms | "
                    f"total={result.get('total_latency_ms', 0):.2f}ms"
                )
                # Chỉ đưa luồng DDoS lên Cảnh báo (Web Dashboard)
                if self.on_alert:
                    try:
                        self.on_alert(result["flow_id"], result)
                    except Exception as e:
                        logger.error(f"[AlertHandler] on_alert callback error: {e}")
            else:
                logger.debug(
                    f"[OK] Normal flow: {result['flow_id']} | "
                    f"confidence={result['confidence']:.4f}"
                )

        logger.info("[AlertHandler] Thread stopped.")

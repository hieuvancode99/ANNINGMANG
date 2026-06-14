"""
feature_extractor.py — Thu thập và tính toán features từ OFPFlowStatsReply

Pipeline:
    OFPFlowStatsReply → Delta Calculation → Feature Vector → Sliding Window → Queue

Features được tính:
    duration     = duration_sec + duration_nsec / 1e9
    packet_count = giá trị tích lũy từ OpenFlow
    byte_count   = giá trị tích lũy từ OpenFlow
    byte_rate    = Δbyte_count / Δtime      (delta so với chu kỳ trước)
    packet_rate  = Δpacket_count / Δtime    (delta so với chu kỳ trước)
    Protocol     = TCP=6, UDP=17, ICMP=1, Other=0
"""

import os
import sys
import time
import logging
from collections import defaultdict, deque

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SEQ_LENGTH, ACTIVE_MODEL, FEATURES

logger = logging.getLogger(__name__)


# ============================================================
# PROTOCOL MAPPING
# ============================================================
PROTOCOL_MAP = {
    1:  1,    # ICMP
    6:  6,    # TCP
    17: 17,   # UDP
}

def _get_protocol(match) -> int:
    """Trích xuất protocol number từ OFPMatch."""
    try:
        proto = match.get("nw_proto", 0)
        if proto is None:
            proto = 0
        return PROTOCOL_MAP.get(int(proto), 0)
    except Exception:
        return 0


# ============================================================
# STATE TABLE
# ============================================================
class FlowStateTable:
    """
    Lưu trạng thái của mỗi flow giữa các chu kỳ polling.
    Dùng để tính Delta features (rate per second).
    """

    def __init__(self):
        # key: flow_id (str)  →  value: dict trạng thái trước
        self._table: dict = {}

    def flow_id(self, dpid: int, stat) -> str:
        """Tạo unique ID cho flow từ dpid + match + cookie + priority."""
        match_str = str(sorted(stat.match.items())) if stat.match else ""
        return f"{dpid}|{stat.cookie}|{stat.priority}|{match_str}"

    def update(self, flow_id: str, packet_count: int,
               byte_count: int, timestamp: float) -> dict:
        """
        Cập nhật state table và trả về delta values.

        Returns:
            dict với keys: delta_packets, delta_bytes, delta_time
                  hoặc None nếu đây là lần đầu thấy flow này
        """
        prev = self._table.get(flow_id)

        # Ghi state mới
        self._table[flow_id] = {
            "packet_count": packet_count,
            "byte_count":   byte_count,
            "timestamp":    timestamp,
        }

        if prev is None:
            return None   # Lần đầu thấy flow, chưa có delta

        delta_time    = timestamp - prev["timestamp"]
        delta_packets = packet_count - prev["packet_count"]
        delta_bytes   = byte_count   - prev["byte_count"]

        if delta_time <= 0:
            return None   # Tránh chia cho 0

        return {
            "delta_packets": max(0, delta_packets),
            "delta_bytes":   max(0, delta_bytes),
            "delta_time":    delta_time,
        }

    def clear(self):
        """Xóa toàn bộ state table."""
        self._table.clear()

    def size(self) -> int:
        return len(self._table)


# ============================================================
# SLIDING WINDOW BUFFER
# ============================================================
class SlidingWindowBuffer:
    """
    Sliding window buffer cho LSTM / Transformer.
    Mỗi flow có 1 deque chứa tối đa SEQ_LENGTH feature vectors.
    """

    def __init__(self, seq_length: int = SEQ_LENGTH):
        self._seq_length = seq_length
        # flow_id → deque(maxlen=seq_length), mỗi phần tử là np.array(6,)
        self._buffers: dict = defaultdict(lambda: deque(maxlen=self._seq_length))

    def push(self, flow_id: str, feature_vector: np.ndarray):
        """Thêm 1 feature vector vào buffer của flow."""
        self._buffers[flow_id].append(feature_vector)

    def is_ready(self, flow_id: str) -> bool:
        """Kiểm tra buffer đã đủ SEQ_LENGTH timestep chưa."""
        return len(self._buffers[flow_id]) >= self._seq_length

    def get_sequence(self, flow_id: str) -> np.ndarray:
        """
        Lấy sequence đầy đủ.

        Returns:
            np.ndarray shape (SEQ_LENGTH, num_features)
        """
        return np.array(list(self._buffers[flow_id]))

    def clear(self):
        """Xóa toàn bộ buffers."""
        self._buffers.clear()

    def evict_old(self, active_flow_ids: set, prefix: str = ""):
        """Xóa các flow không còn active của switch (dựa vào prefix)."""
        stale = [fid for fid in self._buffers if fid.startswith(prefix) and fid not in active_flow_ids]
        for fid in stale:
            del self._buffers[fid]


# ============================================================
# MAIN FEATURE EXTRACTOR
# ============================================================
class FeatureExtractor:
    """
    Trích xuất feature vectors từ OFPFlowStatsReply và
    chuẩn bị input cho InferenceEngine.

    Usage:
        extractor = FeatureExtractor()

        # Trong flow_stats_reply_handler:
        results = extractor.process_stats_reply(dpid, stat_list)
        for flow_id, features in results:
            engine.submit(flow_id, features)
    """

    def __init__(self, model_name: str = None):
        self._state  = FlowStateTable()
        self._window = SlidingWindowBuffer(seq_length=SEQ_LENGTH)
        self._model_name = model_name or ACTIVE_MODEL

    def set_model(self, model_name: str):
        """Đồng bộ với InferenceEngine khi hot-swap."""
        self._model_name = model_name

    def process_stats_reply(self, dpid: int, stat_list: list) -> list:
        """
        Xử lý danh sách OFPFlowStats trả về từ 1 switch.

        Args:
            dpid:      datapath ID của switch
            stat_list: list[OFPFlowStats]

        Returns:
            list of (flow_id, feature_array)
            feature_array:
                - LSTM/Transformer: np.ndarray shape (SEQ_LENGTH, 6)
                - Autoencoder:      np.ndarray shape (6,)
        """
        now = time.time()
        ready_flows = []
        active_ids  = set()

        for stat in stat_list:
            flow_id = self._state.flow_id(dpid, stat)
            active_ids.add(flow_id)

            # --- Tính Delta ---
            delta = self._state.update(
                flow_id,
                packet_count=stat.packet_count,
                byte_count=stat.byte_count,
                timestamp=now
            )

            if delta is None:
                # Lần đầu thấy flow, chưa đủ dữ liệu để tính rate
                continue

            # --- Tính Feature Vector ---
            duration     = stat.duration_sec + stat.duration_nsec / 1e9
            packet_count = stat.packet_count
            byte_count   = stat.byte_count
            byte_rate    = delta["delta_bytes"]   / delta["delta_time"]
            packet_rate  = delta["delta_packets"] / delta["delta_time"]
            protocol     = _get_protocol(stat.match)

            # Thứ tự PHẢI khớp với FEATURES trong config.py:
            # ['duration', 'packet_count', 'byte_count', 'byte_rate', 'packet_rate', 'Protocol']
            feature_vec = np.array([
                duration,
                float(packet_count),
                float(byte_count),
                byte_rate,
                packet_rate,
                float(protocol),
            ], dtype=np.float32)

            logger.debug(
                f"[FE] flow={flow_id[:30]} | "
                f"dur={duration:.2f} | pkt={packet_count} | "
                f"byte={byte_count} | pkt_rate={packet_rate:.2f} | "
                f"byte_rate={byte_rate:.2f} | proto={protocol}"
            )

            # --- Cập nhật Sliding Window (cho LSTM/Transformer) ---
            self._window.push(flow_id, feature_vec)

            # --- Kiểm tra điều kiện để submit ---
            if self._model_name == "autoencoder":
                # Autoencoder: dùng 1 vector, sẵn sàng ngay
                ready_flows.append((flow_id, feature_vec))

            else:
                # LSTM / Transformer: cần đủ SEQ_LENGTH timestep
                if self._window.is_ready(flow_id):
                    sequence = self._window.get_sequence(flow_id)
                    ready_flows.append((flow_id, sequence))

        # Evict stale flows cho switch hiện tại (tránh xóa nhầm flow của switch khác)
        self._window.evict_old(active_ids, prefix=f"{dpid}|")

        return ready_flows

    def reset(self):
        """Reset toàn bộ state (dùng khi restart)."""
        self._state.clear()
        self._window.clear()
        logger.info("[FeatureExtractor] State reset.")

    def get_stats(self) -> dict:
        """Trả về thống kê nội bộ."""
        return {
            "tracked_flows":  self._state.size(),
            "buffered_flows": len(self._window._buffers),
            "seq_length":     SEQ_LENGTH,
            "model_mode":     self._model_name,
        }

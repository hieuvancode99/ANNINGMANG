"""
benchmark.py — Đo lường hiệu năng hệ thống SDN DDoS Detection

Các chỉ số được đo:
    1. Latency   — thời gian từ lúc poll đến lúc ra quyết định (ms)
    2. Scalability — tăng số hosts, đo CPU% của Controller process
    3. Overhead  — % băng thông Control Plane bị chiếm bởi FlowStats

Cách chạy:
    # Đo latency realtime (Controller phải đang chạy)
    python evaluation/benchmark.py --mode latency --model lstm --duration 60

    # Đo overhead (đếm OpenFlow packets)
    python evaluation/benchmark.py --mode overhead --poll-cycle 5

    # So sánh 3 models
    python evaluation/benchmark.py --mode compare --duration 120
"""

import os
import sys
import time
import csv
import json
import logging
import argparse
import threading
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import (
    MODEL_PATHS, SCALER_PATH, ACTIVE_MODEL,
    FEATURES, SEQ_LENGTH, ALERT_THRESHOLD, AUTOENCODER_THRESHOLD,
    RESULTS_DIR
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")


# ============================================================
# LATENCY BENCHMARK
# ============================================================
class LatencyBenchmark:
    """
    Đo latency của inference engine.

    Method: Tạo feature vectors ngẫu nhiên và gọi predict trực tiếp,
            đo thời gian từ lúc submit đến lúc có kết quả.
    """

    def __init__(self, model_name: str):
        from controller.inference_engine import InferenceEngine

        self.model_name = model_name
        self.engine = InferenceEngine(
            model_name=model_name,
            on_alert=None
        )
        self.engine.start()
        self.results = []

    def run(self, n_samples: int = 500, warmup: int = 50):
        """
        Chạy benchmark.

        Args:
            n_samples: Số lần đo
            warmup:    Số lần warmup (bỏ qua kết quả)
        """
        logger.info(
            f"[LatencyBenchmark] model={self.model_name} | "
            f"samples={n_samples} | warmup={warmup}"
        )

        import pickle
        import torch
        with open(SCALER_PATH, "rb") as f:
            scaler = pickle.load(f)

        from controller.model_definitions import create_model
        model = create_model(self.model_name)
        model_path = MODEL_PATHS[self.model_name]
        state_dict = torch.load(model_path, map_location="cpu")
        model.load_state_dict(state_dict)
        model.eval()

        latencies = []
        total = n_samples + warmup

        for i in range(total):
            # Tạo feature vector ngẫu nhiên (giả lập flow thực)
            if self.model_name in ("lstm", "transformer"):
                raw = np.random.rand(SEQ_LENGTH, len(FEATURES)).astype(np.float32)
                normalized = scaler.transform(raw)
                x = torch.tensor(normalized, dtype=torch.float32).unsqueeze(0)
            else:
                raw = np.random.rand(len(FEATURES)).astype(np.float32)
                normalized = scaler.transform(raw.reshape(1, -1))
                x = torch.tensor(normalized, dtype=torch.float32)

            t0 = time.perf_counter()
            with torch.no_grad():
                out = model(x)
                if self.model_name == "autoencoder":
                    mse = torch.mean((out - x) ** 2).item()
            t1 = time.perf_counter()

            latency_ms = (t1 - t0) * 1000

            if i >= warmup:
                latencies.append(latency_ms)

            if (i + 1) % 100 == 0:
                logger.info(f"  Progress: {i+1}/{total}")

        self.engine.stop()

        stats = {
            "model":      self.model_name,
            "n_samples":  n_samples,
            "avg_ms":     float(np.mean(latencies)),
            "median_ms":  float(np.median(latencies)),
            "p95_ms":     float(np.percentile(latencies, 95)),
            "p99_ms":     float(np.percentile(latencies, 99)),
            "max_ms":     float(np.max(latencies)),
            "min_ms":     float(np.min(latencies)),
            "std_ms":     float(np.std(latencies)),
        }

        self.results = latencies
        return stats


# ============================================================
# OVERHEAD BENCHMARK
# ============================================================
class OverheadBenchmark:
    """
    Ước tính overhead của việc polling Flow Stats.

    Method: Đếm số lượng và kích thước OFPFlowStatsRequest/Reply packets.
    """

    def __init__(self, polling_cycles: list = None):
        self.polling_cycles = polling_cycles or [1, 5, 10, 30]

    def estimate(self, n_flows: int = 100, n_switches: int = 1) -> list:
        """
        Ước tính lý thuyết overhead.

        Args:
            n_flows:    Số flow entries trên mỗi switch
            n_switches: Số switch trong topology

        Returns:
            list of dict với overhead per polling cycle
        """
        # Kích thước ước tính của mỗi OFPFlowStats message (bytes)
        # OFPFlowStatsRequest: ~56 bytes header
        # OFPFlowStatsReply: ~56 header + n_flows * ~88 bytes per flow entry
        REQUEST_SIZE_BYTES = 56
        REPLY_BYTES_PER_FLOW = 88
        REPLY_OVERHEAD = 56

        reply_size = REPLY_OVERHEAD + n_flows * REPLY_BYTES_PER_FLOW
        total_per_poll = (REQUEST_SIZE_BYTES + reply_size) * n_switches

        results = []
        # Giả sử link bandwidth 1 Gbps = 125,000,000 bytes/s
        LINK_BW_BPS = 125_000_000

        for cycle in self.polling_cycles:
            bytes_per_second = total_per_poll / cycle
            overhead_pct = (bytes_per_second / LINK_BW_BPS) * 100

            results.append({
                "poll_cycle_s":    cycle,
                "n_flows":         n_flows,
                "n_switches":      n_switches,
                "bytes_per_poll":  total_per_poll,
                "bytes_per_s":     bytes_per_second,
                "overhead_pct":    overhead_pct,
            })

        return results


# ============================================================
# COMPARE 3 MODELS
# ============================================================
def compare_models(n_samples: int = 300) -> list:
    """Chạy LatencyBenchmark cho cả 3 models và so sánh."""
    all_stats = []
    for model_name in ("lstm", "transformer", "autoencoder"):
        logger.info(f"\n{'='*50}")
        logger.info(f" Benchmarking model: {model_name.upper()}")
        logger.info(f"{'='*50}")
        bm = LatencyBenchmark(model_name)
        stats = bm.run(n_samples=n_samples, warmup=50)
        all_stats.append(stats)
        _print_stats(stats)
        time.sleep(1)   # Cho GC dọn dẹp
    return all_stats


def _print_stats(stats: dict):
    """In bảng thống kê đẹp."""
    print(f"""
  ┌─────────────────────────────────────┐
  │  Model:    {stats['model']:>25}  │
  │  Samples:  {stats['n_samples']:>25}  │
  ├─────────────────────────────────────┤
  │  Avg:      {stats['avg_ms']:>22.3f} ms  │
  │  Median:   {stats['median_ms']:>22.3f} ms  │
  │  P95:      {stats['p95_ms']:>22.3f} ms  │
  │  P99:      {stats['p99_ms']:>22.3f} ms  │
  │  Max:      {stats['max_ms']:>22.3f} ms  │
  │  Min:      {stats['min_ms']:>22.3f} ms  │
  │  Std:      {stats['std_ms']:>22.3f} ms  │
  └─────────────────────────────────────┘""")


# ============================================================
# SAVE RESULTS
# ============================================================
def save_results(data: list, filename: str):
    """Lưu kết quả vào CSV và JSON."""
    os.makedirs(RESULTS_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(RESULTS_DIR, f"{filename}_{timestamp}")

    # JSON
    json_path = base + ".json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"[*] Results saved to: {json_path}")

    # CSV (nếu là list of dict phẳng)
    if data and isinstance(data[0], dict):
        csv_path = base + ".csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"[*] CSV saved to: {csv_path}")


# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="SDN DDoS Detection System — Performance Benchmark"
    )
    parser.add_argument(
        "--mode",
        choices=["latency", "overhead", "compare"],
        default="compare",
        help="Benchmark mode (default: compare)"
    )
    parser.add_argument(
        "--model",
        choices=["lstm", "transformer", "autoencoder"],
        default="lstm",
        help="Model to benchmark (for latency mode)"
    )
    parser.add_argument(
        "--samples",
        type=int, default=300,
        help="Number of inference samples (default: 300)"
    )
    parser.add_argument(
        "--poll-cycle",
        type=int, default=5,
        help="Polling cycle in seconds (for overhead mode)"
    )
    parser.add_argument(
        "--n-flows",
        type=int, default=100,
        help="Number of flows per switch (for overhead mode)"
    )
    parser.add_argument(
        "--n-switches",
        type=int, default=1,
        help="Number of switches (for overhead mode)"
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  SDN DDoS Detection — Performance Benchmark")
    print("=" * 60 + "\n")

    if args.mode == "latency":
        bm = LatencyBenchmark(args.model)
        stats = bm.run(n_samples=args.samples, warmup=50)
        _print_stats(stats)
        save_results([stats], f"latency_{args.model}")

    elif args.mode == "overhead":
        bm = OverheadBenchmark(polling_cycles=[1, 2, 5, 10, 30])
        results = bm.estimate(n_flows=args.n_flows, n_switches=args.n_switches)

        print(f"\n  Overhead Analysis (flows={args.n_flows}, switches={args.n_switches})")
        print(f"  {'Poll Cycle':>12} | {'Bytes/Poll':>12} | {'Bytes/s':>12} | {'Overhead%':>10}")
        print("  " + "-" * 54)
        for r in results:
            print(
                f"  {r['poll_cycle_s']:>10}s | "
                f"{r['bytes_per_poll']:>12,.0f} | "
                f"{r['bytes_per_s']:>12,.0f} | "
                f"{r['overhead_pct']:>9.4f}%"
            )
        save_results(results, "overhead")

    elif args.mode == "compare":
        all_stats = compare_models(n_samples=args.samples)

        print("\n" + "=" * 70)
        print("  COMPARISON SUMMARY")
        print("=" * 70)
        print(f"  {'Model':>15} | {'Avg (ms)':>10} | {'P95 (ms)':>10} | {'Max (ms)':>10}")
        print("  " + "-" * 54)
        for s in all_stats:
            print(
                f"  {s['model']:>15} | "
                f"{s['avg_ms']:>10.3f} | "
                f"{s['p95_ms']:>10.3f} | "
                f"{s['max_ms']:>10.3f}"
            )
        print("=" * 70 + "\n")
        save_results(all_stats, "model_comparison")


if __name__ == "__main__":
    main()

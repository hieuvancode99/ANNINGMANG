#!/bin/bash
# =============================================================
# normal_traffic.sh — Sinh traffic bình thường (Normal)
#
# Cách dùng trong Mininet CLI:
#   mininet> h1 bash traffic/normal_traffic.sh server &
#   mininet> h2 bash traffic/normal_traffic.sh client h1 30
#
# Tham số:
#   $1 = mode:      server | client | ping
#   $2 = server_ip: IP của server (cho client mode)
#   $3 = duration:  Thời gian chạy (giây, mặc định 60)
# =============================================================

MODE=${1:-"client"}
SERVER_IP=${2:-"10.0.0.1"}
DURATION=${3:-60}

echo "========================================"
echo " Normal Traffic Generator"
echo " Mode:     $MODE"
echo " Server:   $SERVER_IP"
echo " Duration: ${DURATION}s"
echo "========================================"

case "$MODE" in

    server)
        echo "[*] Starting iperf3 server (listening)..."
        iperf3 -s -D   # Daemon mode
        echo "[*] Server running in background."
        ;;

    client)
        echo "[*] Starting iperf3 client → $SERVER_IP"
        iperf3 \
            -c "$SERVER_IP" \
            -t "$DURATION" \
            -i 5 \
            -b 10M \
            -P 2
        ;;

    ping)
        echo "[*] Sending ICMP pings → $SERVER_IP (${DURATION}s)"
        ping -c "$(( DURATION * 2 ))" -i 0.5 "$SERVER_IP"
        ;;

    http)
        echo "[*] Simulating HTTP traffic → $SERVER_IP (${DURATION}s)"
        for i in $(seq 1 $((DURATION / 2))); do
            curl -s -o /dev/null "http://$SERVER_IP/" 2>/dev/null || true
            sleep 2
        done
        ;;

    *)
        echo "[ERROR] Unknown mode: $MODE"
        echo "        Use: server | client | ping | http"
        exit 1
        ;;
esac

echo ""
echo "[*] Normal traffic generation completed."

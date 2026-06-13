"""
single_switch_topo.py — Mininet topology: 1 switch, 4 hosts

Dùng để test logic cơ bản trước khi nâng lên Tree topology.

Cách chạy:
    sudo python topology/single_switch_topo.py

Yêu cầu:
    - Ryu đang chạy: ryu-manager controller/ryu_controller.py
    - Mininet đã cài đặt
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink


class SingleSwitchTopo(Topo):
    """
    Topology đơn giản nhất: 1 OVS switch + 4 hosts

    Sơ đồ:
        h1 ──┐
        h2 ──┤── s1 ──── RemoteController
        h3 ──┤
        h4 ──┘

    IP: h1=10.0.0.1, h2=10.0.0.2, h3=10.0.0.3, h4=10.0.0.4
    """

    def build(self, n_hosts=4):
        # Tạo switch
        s1 = self.addSwitch("s1", cls=OVSSwitch, protocols="OpenFlow13")

        # Tạo hosts và link
        for i in range(1, n_hosts + 1):
            host = self.addHost(
                f"h{i}",
                ip=f"10.0.0.{i}/24",
                mac=f"00:00:00:00:00:0{i}"
            )
            self.addLink(
                host, s1,
                # Giới hạn bandwidth để test overhead rõ hơn
                bw=100,     # 100 Mbps
                delay="1ms",
                loss=0,
            )


def run_single_switch(controller_ip="127.0.0.1", controller_port=6653):
    """
    Chạy topology single switch với Remote Controller.

    Args:
        controller_ip:   IP của Ryu controller
        controller_port: Port của Ryu controller (mặc định 6653)
    """
    setLogLevel("info")

    topo = SingleSwitchTopo(n_hosts=4)

    net = Mininet(
        topo=topo,
        controller=None,           # Tắt controller mặc định
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=False,
        autoStaticArp=False,
    )

    # Thêm Remote Controller (Ryu)
    net.addController(
        "c0",
        controller=RemoteController,
        ip=controller_ip,
        port=controller_port,
    )

    net.start()
    info("\n" + "=" * 60 + "\n")
    info("  Single Switch Topology Started\n")
    info(f"  Hosts: h1(10.0.0.1) h2(10.0.0.2) h3(10.0.0.3) h4(10.0.0.4)\n")
    info(f"  Controller: {controller_ip}:{controller_port}\n")
    info("=" * 60 + "\n")

    # Test connectivity
    info("\n[*] Testing connectivity (pingall)...\n")
    result = net.pingAll()
    info(f"\n[*] Ping loss rate: {result:.1f}%\n\n")

    # Mở CLI để tương tác
    CLI(net)

    net.stop()


if __name__ == "__main__":
    run_single_switch()

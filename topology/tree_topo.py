"""
tree_topo.py — Mininet Tree Topology cho Scalability Test

Cấu trúc:
    depth=2, fanout=3  → 1 core switch + 3 edge switches + 9 hosts
    depth=3, fanout=3  → 1 core + 3 agg + 9 edge + 27 hosts

Cách chạy:
    # Topology nhỏ (depth=2, 9 hosts)
    sudo python topology/tree_topo.py --depth 2 --fanout 3

    # Topology lớn hơn (depth=3, 27 hosts)
    sudo python topology/tree_topo.py --depth 3 --fanout 3
"""

import argparse
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink


class TreeTopoCustom(Topo):
    """
    Tree Topology tham số hóa.

    depth=2, fanout=3:
                   s1  (core)
              /    |    \\
            s2    s3    s4  (edge)
           /|\\   /|\\   /|\\
         h1 h2 h3 h4 ... h9

    depth=3, fanout=3:
                      s1  (core)
                 /    |    \\
               s2    s3    s4  (aggregation)
              /|\\   /|\\   /|\\
            s5..s13          (edge)
           /|\\  ...
         h1..h27

    IP scheme: 10.{depth_level}.{switch_idx}.{host_idx}/8
    """

    def __init__(self, depth=2, fanout=3, **opts):
        self.depth  = depth
        self.fanout = fanout
        self._switch_count = 0
        self._host_count   = 0
        super().__init__(**opts)

    def build(self):
        self._switch_count = 0
        self._host_count   = 0
        # Bắt đầu từ core switch ở level 0
        self._build_tree(depth=self.depth, parent=None)

    def _build_tree(self, depth, parent):
        """Đệ quy tạo cây switch + host."""
        self._switch_count += 1
        sw_name = f"s{self._switch_count}"
        sw = self.addSwitch(sw_name, protocols="OpenFlow13")

        if parent:
            self.addLink(parent, sw, bw=1000, delay="1ms")

        if depth == 1:
            # Lá: tạo fanout hosts
            for _ in range(self.fanout):
                self._host_count += 1
                h_idx   = self._host_count
                # IP: 10.0.{switch}.{host}
                ip_addr = f"10.0.{self._switch_count}.{h_idx % 254 + 1}/16"
                host = self.addHost(
                    f"h{h_idx}",
                    ip=ip_addr,
                )
                self.addLink(host, sw, bw=100, delay="1ms")
        else:
            # Nội bộ: tạo fanout switches con
            for _ in range(self.fanout):
                self._build_tree(depth - 1, sw)


def run_tree_topo(depth=2, fanout=3,
                  controller_ip="127.0.0.1", controller_port=6653):
    """
    Chạy Tree topology với Remote Controller.

    Số hosts = fanout^depth:
        depth=2, fanout=3  →   9 hosts
        depth=3, fanout=3  →  27 hosts
    """
    setLogLevel("info")

    n_hosts = fanout ** depth
    info(f"\n[*] Building Tree Topology: depth={depth}, fanout={fanout}, hosts={n_hosts}\n")

    topo = TreeTopoCustom(depth=depth, fanout=fanout)

    net = Mininet(
        topo=topo,
        controller=None,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=False,
    )

    net.addController(
        "c0",
        controller=RemoteController,
        ip=controller_ip,
        port=controller_port,
    )

    net.start()
    info("\n" + "=" * 60 + "\n")
    info(f"  Tree Topology (depth={depth}, fanout={fanout})\n")
    info(f"  Total hosts:   {n_hosts}\n")
    info(f"  Controller:    {controller_ip}:{controller_port}\n")
    info("=" * 60 + "\n")

    # Test connectivity
    info("\n[*] Testing connectivity (pingall)...\n")
    result = net.pingAll()
    info(f"\n[*] Ping loss rate: {result:.1f}%\n\n")

    CLI(net)
    net.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SDN Tree Topology for Scalability Testing"
    )
    parser.add_argument("--depth",   type=int, default=2,
                        help="Tree depth (default: 2)")
    parser.add_argument("--fanout",  type=int, default=3,
                        help="Fanout per switch (default: 3)")
    parser.add_argument("--ctrl-ip", type=str, default="127.0.0.1",
                        help="Controller IP (default: 127.0.0.1)")
    parser.add_argument("--ctrl-port", type=int, default=6653,
                        help="Controller port (default: 6653)")
    args = parser.parse_args()

    run_tree_topo(
        depth=args.depth,
        fanout=args.fanout,
        controller_ip=args.ctrl_ip,
        controller_port=args.ctrl_port,
    )

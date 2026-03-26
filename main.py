#!/usr/bin/env python3
"""
Network Switch Detector & Topology Mapper
==========================================
Kullanım:
    python main.py 192.168.1.0/24
    python main.py 192.168.1.0/24 --community public --output-dir ./output
    python main.py 192.168.1.0/24 --no-ports --timeout 3 --threads 50
    python main.py --demo   # Gerçek ağ taraması olmadan örnek şema üretir
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Renkli terminal çıktısı (opsiyonel)
try:
    from rich.logging import RichHandler
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
    RICH = True
except ImportError:
    RICH = False


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    if RICH:
        logging.basicConfig(
            level=level,
            format="%(message)s",
            handlers=[RichHandler(rich_tracebacks=True, markup=True)],
        )
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ağdaki switch'leri tespit eder ve topoloji şeması oluşturur.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Taranacak CIDR bloğu (örn: 192.168.1.0/24) veya tekil IP",
    )
    parser.add_argument(
        "--community", "-c",
        default="public",
        help="SNMP community string (varsayılan: public)",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=float,
        default=2.0,
        help="SNMP/port timeout saniye (varsayılan: 2.0)",
    )
    parser.add_argument(
        "--threads", "-T",
        type=int,
        default=100,
        help="Paralel tarama thread sayısı (varsayılan: 100)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./output",
        help="Çıktı klasörü (varsayılan: ./output)",
    )
    parser.add_argument(
        "--no-ports",
        action="store_true",
        help="TCP port taramasını devre dışı bırak",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="HTML şeması oluşturma",
    )
    parser.add_argument(
        "--no-png",
        action="store_true",
        help="PNG şeması oluşturma",
    )
    parser.add_argument(
        "--title",
        default="Network Topology",
        help="Şema başlığı",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Demo mod: gerçek tarama yapmadan örnek şema üretir",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Ayrıntılı log çıktısı",
    )
    return parser.parse_args()


# ------------------------------------------------------------------
# Demo modu – gerçek ağ erişimi olmadan test
# ------------------------------------------------------------------

def run_demo(output_dir: str, title: str) -> None:
    """
    Gerçekçi bir ağ senaryosunu simüle eder:
      - 2 adet core switch (Cisco)
      - 4 adet access switch (HP, D-Link)
      - 6 adet son kullanıcı host
    """
    from network_discovery.identifier import NetworkDevice, SwitchPort
    from network_discovery.topology import Link
    from network_discovery.diagram import NetworkDiagram

    logger = logging.getLogger(__name__)
    logger.info("[DEMO] Örnek topoloji oluşturuluyor...")

    # --- Cihazlar ---
    devices = [
        # Core switch 1
        NetworkDevice(
            ip="10.0.0.1", mac="AA:BB:CC:00:00:01",
            sys_name="Core-SW1", vendor="Cisco", model="Catalyst 9300",
            is_switch=True, port_count=48, sys_location="Server Room Rack-A",
            snmp_community="public",
            ports=[
                SwitchPort(index=1,  name="GigabitEthernet1/0/1",  speed_mbps=1000, oper_status="up"),
                SwitchPort(index=2,  name="GigabitEthernet1/0/2",  speed_mbps=1000, oper_status="up"),
                SwitchPort(index=49, name="TenGigabitEthernet1/1/1",speed_mbps=10000,oper_status="up"),
            ],
        ),
        # Core switch 2
        NetworkDevice(
            ip="10.0.0.2", mac="AA:BB:CC:00:00:02",
            sys_name="Core-SW2", vendor="Cisco", model="Catalyst 9300",
            is_switch=True, port_count=48, sys_location="Server Room Rack-B",
            snmp_community="public",
        ),
        # Distribution switch
        NetworkDevice(
            ip="10.0.1.1", mac="AA:BB:CC:01:00:01",
            sys_name="Dist-SW1", vendor="HP/Aruba", model="ProCurve 2920",
            is_switch=True, port_count=24, sys_location="Floor-2 Closet",
            snmp_community="public",
        ),
        # Access switch 1
        NetworkDevice(
            ip="10.0.2.1", mac="AA:BB:CC:02:00:01",
            sys_name="Access-SW1", vendor="D-Link", model="DGS-1210-28",
            is_switch=True, port_count=28, sys_location="Floor-1 Room-101",
            snmp_community="public",
        ),
        # Access switch 2
        NetworkDevice(
            ip="10.0.2.2", mac="AA:BB:CC:02:00:02",
            sys_name="Access-SW2", vendor="Netgear", model="GS324T",
            is_switch=True, port_count=24, sys_location="Floor-1 Room-102",
            snmp_community="public",
        ),
        # Access switch 3
        NetworkDevice(
            ip="10.0.3.1", mac="AA:BB:CC:03:00:01",
            sys_name="Access-SW3", vendor="MikroTik", model="CRS328",
            is_switch=True, port_count=28, sys_location="Floor-3",
            snmp_community="public",
        ),
        # Hostlar
        NetworkDevice(ip="10.0.2.10", mac="CC:DD:EE:00:00:01", hostname="pc-101-a",   vendor="Unknown"),
        NetworkDevice(ip="10.0.2.11", mac="CC:DD:EE:00:00:02", hostname="pc-101-b",   vendor="Unknown"),
        NetworkDevice(ip="10.0.2.20", mac="CC:DD:EE:00:00:03", hostname="printer-101",vendor="HP/Aruba"),
        NetworkDevice(ip="10.0.3.10", mac="CC:DD:EE:00:01:01", hostname="pc-301-a",   vendor="Unknown"),
        NetworkDevice(ip="10.0.3.11", mac="CC:DD:EE:00:01:02", hostname="server-1",   vendor="Dell"),
        NetworkDevice(ip="10.0.0.254",mac="CC:DD:EE:FF:FF:01", hostname="gateway",    vendor="Cisco"),
    ]

    # --- Bağlantılar ---
    links = [
        # Core-Core (uplink)
        Link("10.0.0.1", "Te1/1/1",  "10.0.0.2",  "Te1/1/1",  method="lldp"),
        # Core -> Dist
        Link("10.0.0.1", "Gi1/0/1",  "10.0.1.1",  "Gi1",      method="lldp"),
        Link("10.0.0.2", "Gi1/0/1",  "10.0.1.1",  "Gi2",      method="lldp"),
        # Dist -> Access
        Link("10.0.1.1", "Gi1/0/2",  "10.0.2.1",  "Port1",    method="cdp"),
        Link("10.0.1.1", "Gi1/0/3",  "10.0.2.2",  "Port1",    method="cdp"),
        Link("10.0.0.2", "Gi1/0/2",  "10.0.3.1",  "ether1",   method="lldp"),
        # Access -> Hosts
        Link("10.0.2.1", "Port5",    "10.0.2.10", "",          method="bridge"),
        Link("10.0.2.1", "Port6",    "10.0.2.11", "",          method="bridge"),
        Link("10.0.2.2", "Port3",    "10.0.2.20", "",          method="bridge"),
        Link("10.0.3.1", "ether5",   "10.0.3.10", "",          method="bridge"),
        Link("10.0.3.1", "ether6",   "10.0.3.11", "",          method="bridge"),
        # Gateway -> Core
        Link("10.0.0.254","eth0",    "10.0.0.1",  "Gi1/0/48",  method="lldp"),
    ]

    diagram = NetworkDiagram(devices, links, title=title + " [DEMO]")
    _save_outputs(diagram, output_dir, no_html=False, no_png=False)
    diagram.print_summary()


# ------------------------------------------------------------------
# Gerçek tarama
# ------------------------------------------------------------------

def run_scan(args) -> None:
    from network_discovery.scanner import NetworkScanner
    from network_discovery.identifier import SwitchIdentifier
    from network_discovery.topology import TopologyBuilder
    from network_discovery.diagram import NetworkDiagram

    logger = logging.getLogger(__name__)
    t_start = time.time()

    # 1. ARP/Ping taraması
    logger.info(f"Tarama başlatılıyor: {args.target}")
    scanner = NetworkScanner(
        timeout=args.timeout,
        max_threads=args.threads,
        scan_ports=not args.no_ports,
        snmp_probe=True,
    )
    hosts = scanner.scan(args.target)
    logger.info(f"{len(hosts)} canlı cihaz bulundu.")

    if not hosts:
        logger.warning("Hiç cihaz bulunamadı. Hedefi ve ağ bağlantısını kontrol edin.")
        sys.exit(0)

    # 2. SNMP kimlik tespiti
    logger.info("Cihazlar SNMP üzerinden tanımlanıyor...")
    identifier = SwitchIdentifier(
        community=args.community,
        timeout=args.timeout,
    )
    devices = identifier.identify(hosts)
    switches = [d for d in devices if d.is_switch]
    logger.info(f"{len(switches)} switch tespit edildi.")

    # 3. Topoloji keşfi
    links = []
    if switches:
        logger.info("LLDP/CDP/Bridge topoloji keşfi yapılıyor...")
        topo = TopologyBuilder(timeout=args.timeout)
        links = topo.build(devices)

    # 4. Şema oluştur
    diagram = NetworkDiagram(devices, links, title=args.title)
    _save_outputs(diagram, args.output_dir, args.no_html, args.no_png)
    diagram.print_summary()

    elapsed = time.time() - t_start
    logger.info(f"Tamamlandı ({elapsed:.1f} saniye). Çıktılar: {args.output_dir}/")


# ------------------------------------------------------------------
# Çıktı kaydetme
# ------------------------------------------------------------------

def _save_outputs(diagram, output_dir: str, no_html: bool, no_png: bool):
    os.makedirs(output_dir, exist_ok=True)

    diagram.save_json(os.path.join(output_dir, "topology.json"))

    if not no_html:
        diagram.save_html(os.path.join(output_dir, "topology.html"))

    if not no_png:
        diagram.save_png(os.path.join(output_dir, "topology.png"))


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)

    if args.demo:
        run_demo(args.output_dir, args.title)
    elif args.target:
        run_scan(args)
    else:
        print(__doc__)
        print("\nHata: Hedef subnet belirtmelisiniz veya --demo kullanın.\n")
        sys.exit(1)

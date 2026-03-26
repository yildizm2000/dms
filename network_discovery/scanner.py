"""
Network Scanner - ARP & ICMP tabanlı cihaz keşfi
=================================================
Belirtilen subnet'te ARP sweep yaparak canlı cihazları tespit eder,
her cihaz için IP, MAC ve ilk yanıt süresini kaydeder.
"""

import socket
import struct
import threading
import ipaddress
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredHost:
    ip: str
    mac: str = ""
    hostname: str = ""
    response_time_ms: float = 0.0
    open_ports: List[int] = field(default_factory=list)
    snmp_community: str = ""  # çalışan community string varsa

    def __repr__(self):
        return f"<Host ip={self.ip} mac={self.mac} hostname={self.hostname}>"


class NetworkScanner:
    """
    ARP tabanlı ağ tarayıcı.

    Scapy mevcutsa ARP sweep, değilse socket tabanlı ping sweep kullanır.
    Management portları (22, 23, 80, 161, 443, 8080) ayrıca taranır.
    """

    MGMT_PORTS = [22, 23, 80, 161, 443, 8080, 8443]
    SNMP_COMMUNITIES = ["public", "private", "community", "admin", "cisco", "snmp"]

    def __init__(
        self,
        timeout: float = 2.0,
        max_threads: int = 100,
        scan_ports: bool = True,
        snmp_probe: bool = True,
    ):
        self.timeout = timeout
        self.max_threads = max_threads
        self.scan_ports = scan_ports
        self.snmp_probe = snmp_probe
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, target: str) -> List[DiscoveredHost]:
        """
        target: CIDR bloğu  ('192.168.1.0/24') veya tekil IP ('192.168.1.1')
        Döndürür: canlı host listesi
        """
        hosts = self._arp_sweep(target)

        if not hosts:
            logger.warning("ARP sweep sonuç vermedi, ping sweep deneniyor...")
            hosts = self._ping_sweep(target)

        if self.scan_ports and hosts:
            logger.info(f"{len(hosts)} host için port taraması başlatılıyor...")
            self._parallel_port_scan(hosts)

        if self.snmp_probe and hosts:
            logger.info("SNMP community string tespiti yapılıyor...")
            self._probe_snmp_communities(hosts)

        return hosts

    # ------------------------------------------------------------------
    # ARP Sweep (Scapy)
    # ------------------------------------------------------------------

    def _arp_sweep(self, target: str) -> List[DiscoveredHost]:
        try:
            from scapy.all import ARP, Ether, srp  # type: ignore
            import time
        except ImportError:
            logger.debug("Scapy bulunamadı, ARP sweep atlanıyor.")
            return []

        results: List[DiscoveredHost] = []
        try:
            pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=target)
            t0 = __import__("time").time()
            ans, _ = srp(pkt, timeout=self.timeout, verbose=False)
            for sent, received in ans:
                rtt = (__import__("time").time() - t0) * 1000
                host = DiscoveredHost(
                    ip=received.psrc,
                    mac=received.hwsrc.upper(),
                    response_time_ms=round(rtt, 2),
                )
                host.hostname = self._resolve_hostname(host.ip)
                results.append(host)
                logger.debug(f"ARP: {host.ip} ({host.mac})")
        except PermissionError:
            logger.warning("ARP sweep için root/admin yetkisi gerekiyor.")
        except Exception as exc:
            logger.error(f"ARP sweep hatası: {exc}")

        return results

    # ------------------------------------------------------------------
    # Ping Sweep (socket tabanlı, root gerektirmez)
    # ------------------------------------------------------------------

    def _ping_sweep(self, target: str) -> List[DiscoveredHost]:
        try:
            network = ipaddress.ip_network(target, strict=False)
        except ValueError as exc:
            raise ValueError(f"Geçersiz hedef: {target}") from exc

        hosts: List[DiscoveredHost] = []

        def check_host(ip_str: str) -> Optional[DiscoveredHost]:
            if self._is_tcp_reachable(ip_str, 80) or self._is_tcp_reachable(ip_str, 22):
                h = DiscoveredHost(ip=ip_str)
                h.hostname = self._resolve_hostname(ip_str)
                return h
            return None

        with ThreadPoolExecutor(max_workers=self.max_threads) as ex:
            futures = {ex.submit(check_host, str(ip)): ip for ip in network.hosts()}
            for f in as_completed(futures):
                result = f.result()
                if result:
                    hosts.append(result)

        return hosts

    # ------------------------------------------------------------------
    # Port Tarama
    # ------------------------------------------------------------------

    def _parallel_port_scan(self, hosts: List[DiscoveredHost]):
        def scan_host(host: DiscoveredHost):
            open_ports = []
            for port in self.MGMT_PORTS:
                if self._is_tcp_reachable(host.ip, port, timeout=0.5):
                    open_ports.append(port)
            with self._lock:
                host.open_ports = open_ports

        with ThreadPoolExecutor(max_workers=self.max_threads) as ex:
            list(ex.map(scan_host, hosts))

    def _is_tcp_reachable(self, ip: str, port: int, timeout: float = None) -> bool:
        timeout = timeout or self.timeout
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except (OSError, socket.timeout):
            return False

    # ------------------------------------------------------------------
    # SNMP Community Probe
    # ------------------------------------------------------------------

    def _probe_snmp_communities(self, hosts: List[DiscoveredHost]):
        """
        Her host için SNMP UDP 161 portunu yoklar,
        çalışan ilk community string'i kaydeder.
        """
        try:
            from pysnmp.hlapi import (  # type: ignore
                getCmd,
                SnmpEngine,
                CommunityData,
                UdpTransportTarget,
                ContextData,
                ObjectType,
                ObjectIdentity,
            )
        except ImportError:
            logger.debug("pysnmp bulunamadı, SNMP probe atlanıyor.")
            return

        snmp_hosts = [h for h in hosts if 161 in h.open_ports]
        if not snmp_hosts:
            return

        def probe_host(host: DiscoveredHost):
            for community in self.SNMP_COMMUNITIES:
                try:
                    errorIndication, errorStatus, _, varBinds = next(
                        getCmd(
                            SnmpEngine(),
                            CommunityData(community, mpModel=1),
                            UdpTransportTarget((host.ip, 161), timeout=1, retries=0),
                            ContextData(),
                            ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0")),
                        )
                    )
                    if not errorIndication and not errorStatus:
                        with self._lock:
                            host.snmp_community = community
                        logger.debug(f"SNMP community '{community}' -> {host.ip}")
                        return
                except Exception:
                    continue

        with ThreadPoolExecutor(max_workers=20) as ex:
            list(ex.map(probe_host, snmp_hosts))

    # ------------------------------------------------------------------
    # Yardımcı
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_hostname(ip: str) -> str:
        try:
            return socket.gethostbyaddr(ip)[0]
        except (socket.herror, socket.gaierror):
            return ""

    @staticmethod
    def subnet_info(target: str) -> Dict:
        net = ipaddress.ip_network(target, strict=False)
        return {
            "network": str(net.network_address),
            "broadcast": str(net.broadcast_address),
            "netmask": str(net.netmask),
            "host_count": net.num_addresses - 2,
            "prefix": net.prefixlen,
        }

"""
Topology Builder - LLDP / CDP / Bridge MIB topoloji keşfi
==========================================================
Switch'ler arasındaki fiziksel bağlantıları üç yöntemle toplar:

1. LLDP MIB (IEEE 802.1AB)  – vendor-neutral, modern switch'lerin büyük çoğunluğu
2. CDP MIB  (Cisco)         – Cisco/HP cihazlar
3. Bridge MIB dot1dTpFdbTable – MAC address table cross-reference
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from .identifier import NetworkDevice

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# LLDP OID'leri  (RFC 2922 / IEEE 802.1AB MIB)
# ------------------------------------------------------------------
OID_LLDP_REM_CHASSIS_ID     = "1.0.8802.1.1.2.1.4.1.1.5"  # komşu chassis MAC
OID_LLDP_REM_PORT_ID        = "1.0.8802.1.1.2.1.4.1.1.7"  # komşu port ID
OID_LLDP_REM_PORT_DESCR     = "1.0.8802.1.1.2.1.4.1.1.8"  # komşu port açıklaması
OID_LLDP_REM_SYS_NAME       = "1.0.8802.1.1.2.1.4.1.1.9"  # komşu sistem adı
OID_LLDP_REM_SYS_DESCR      = "1.0.8802.1.1.2.1.4.1.1.10"
OID_LLDP_REM_MGMT_ADDR      = "1.0.8802.1.1.2.1.4.2.1.4"  # komşu yönetim IP
OID_LLDP_LOC_SYS_NAME       = "1.0.8802.1.1.2.1.3.3.0"
OID_LLDP_LOC_PORT_TABLE     = "1.0.8802.1.1.2.1.3.7"

# ------------------------------------------------------------------
# CDP OID'leri  (Cisco-CDP-MIB)
# ------------------------------------------------------------------
OID_CDP_CACHE_ADDRESS        = "1.3.6.1.4.1.9.9.23.1.2.1.1.4"   # komşu IP
OID_CDP_CACHE_DEVICE_ID      = "1.3.6.1.4.1.9.9.23.1.2.1.1.6"   # komşu hostname
OID_CDP_CACHE_DEVICE_PORT    = "1.3.6.1.4.1.9.9.23.1.2.1.1.7"   # komşu port
OID_CDP_CACHE_PLATFORM       = "1.3.6.1.4.1.9.9.23.1.2.1.1.8"   # komşu platform
OID_CDP_CACHE_CAPABILITIES   = "1.3.6.1.4.1.9.9.23.1.2.1.1.9"   # komşu yetenekleri
OID_CDP_CACHE_LOCAL_INTF     = "1.3.6.1.4.1.9.9.23.1.2.1.1.17"  # yerel port

# ------------------------------------------------------------------
# Bridge MIB - MAC address table
# ------------------------------------------------------------------
OID_FDB_TABLE                = "1.3.6.1.2.1.17.4.3.1.1"  # dot1dTpFdbAddress
OID_FDB_PORT                 = "1.3.6.1.2.1.17.4.3.1.2"  # dot1dTpFdbPort
OID_FDB_STATUS               = "1.3.6.1.2.1.17.4.3.1.3"  # 3=learned


@dataclass
class Link:
    """İki cihaz arasındaki fiziksel veya mantıksal bağlantı."""
    local_ip: str
    local_port: str
    remote_ip: str
    remote_port: str
    remote_hostname: str = ""
    method: str = "unknown"  # lldp | cdp | bridge | manual

    @property
    def key(self) -> Tuple[str, str]:
        """Yön bağımsız bağlantı anahtarı (kenar dedup için)."""
        a = (self.local_ip, self.remote_ip)
        return (min(a), max(a))

    def __repr__(self):
        return (
            f"<Link {self.local_ip}:{self.local_port} "
            f"<-> {self.remote_ip}:{self.remote_port} [{self.method}]>"
        )


class TopologyBuilder:
    """
    NetworkDevice listesini alır, her switch için LLDP/CDP/Bridge MIB
    sorgular ve Link listesi döndürür.
    """

    def __init__(self, timeout: float = 2.0, retries: int = 1):
        self.timeout = timeout
        self.retries = retries
        self._ip_to_dev: Dict[str, NetworkDevice] = {}
        self._mac_to_ip: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, devices: List[NetworkDevice]) -> List[Link]:
        """
        devices: SwitchIdentifier.identify() çıktısı
        Döndürür: tekil bağlantı listesi
        """
        self._ip_to_dev = {d.ip: d for d in devices}
        self._mac_to_ip = {}
        for d in devices:
            if d.mac:
                self._mac_to_ip[d.mac.upper().replace("-", ":")] = d.ip
            if d.bridge_mac:
                self._mac_to_ip[d.bridge_mac.upper().replace("-", ":")] = d.ip

        all_links: List[Link] = []
        seen_keys: Set[Tuple[str, str]] = set()

        for dev in devices:
            if not dev.is_switch or not dev.snmp_community:
                continue

            lldp_links = self._collect_lldp(dev)
            cdp_links  = self._collect_cdp(dev)
            fdb_links  = self._collect_bridge_fdb(dev, devices)

            for link in lldp_links + cdp_links + fdb_links:
                k = link.key
                if k not in seen_keys:
                    seen_keys.add(k)
                    all_links.append(link)

        logger.info(f"Topoloji: {len(all_links)} benzersiz bağlantı bulundu.")
        return all_links

    # ------------------------------------------------------------------
    # LLDP
    # ------------------------------------------------------------------

    def _collect_lldp(self, dev: NetworkDevice) -> List[Link]:
        """LLDP RemTable'ı walk ederek komşuları listeler."""
        links: List[Link] = []
        community = dev.snmp_community

        rem_sys_name  = self._walk(dev.ip, community, OID_LLDP_REM_SYS_NAME)
        rem_port_id   = self._walk(dev.ip, community, OID_LLDP_REM_PORT_ID)
        rem_port_desc = self._walk(dev.ip, community, OID_LLDP_REM_PORT_DESCR)
        rem_chassis   = self._walk(dev.ip, community, OID_LLDP_REM_CHASSIS_ID)
        rem_mgmt      = self._walk(dev.ip, community, OID_LLDP_REM_MGMT_ADDR)

        # OID yapısı: <base>.<timeMark>.<localPortNum>.<remoteIndex>
        for oid, sys_name in rem_sys_name.items():
            parts = oid.split(".")
            if len(parts) < 3:
                continue
            local_port_num = parts[-2]
            rem_idx        = parts[-1]
            suffix         = f".{local_port_num}.{rem_idx}"

            local_port  = f"Port{local_port_num}"
            remote_port = str(rem_port_id.get(OID_LLDP_REM_PORT_ID + suffix, ""))
            if not remote_port:
                remote_port = str(rem_port_desc.get(OID_LLDP_REM_PORT_DESCR + suffix, ""))

            # Uzak IP: mgmt addr tablosundan veya chassis MAC üzerinden
            remote_ip = self._lldp_resolve_remote_ip(
                dev.ip, community, local_port_num, rem_idx,
                rem_mgmt, rem_chassis.get(OID_LLDP_REM_CHASSIS_ID + suffix, "")
            )

            if not remote_ip:
                logger.debug(
                    f"LLDP {dev.ip}: komşu {sys_name} için IP çözümlenemedi, atlanıyor."
                )
                continue

            links.append(Link(
                local_ip=dev.ip,
                local_port=local_port,
                remote_ip=remote_ip,
                remote_port=remote_port,
                remote_hostname=str(sys_name),
                method="lldp",
            ))

        if links:
            logger.debug(f"LLDP {dev.ip}: {len(links)} komşu")
        return links

    def _lldp_resolve_remote_ip(
        self, local_ip, community, port_num, rem_idx, rem_mgmt, chassis_raw
    ) -> str:
        """LLDP management address tablosundan uzak IP'yi çözer."""
        # mgmt addr OID: .1.0.8802.1.1.2.1.4.2.1.4.<timeMark>.<portNum>.<remIdx>.<addrLen>.<addrType>.<a.b.c.d>
        prefix = f"{OID_LLDP_REM_MGMT_ADDR}.0.{port_num}.{rem_idx}"
        for oid in rem_mgmt:
            if oid.startswith(prefix):
                # Son 4 oktet = IP
                tail = oid[len(prefix):].lstrip(".")
                parts = tail.split(".")
                # Genellikle: <addrLen>.<addrSubtype>.<a>.<b>.<c>.<d>
                if len(parts) >= 6:
                    ip_candidate = ".".join(parts[-4:])
                    if self._is_valid_ip(ip_candidate):
                        return ip_candidate

        # Chassis MAC üzerinden eşleşme
        if chassis_raw:
            mac = self._format_mac(chassis_raw)
            if mac in self._mac_to_ip:
                return self._mac_to_ip[mac]

        return ""

    # ------------------------------------------------------------------
    # CDP
    # ------------------------------------------------------------------

    def _collect_cdp(self, dev: NetworkDevice) -> List[Link]:
        """Cisco CDP cache tablosunu walk eder."""
        links: List[Link] = []
        community = dev.snmp_community

        address_data   = self._walk(dev.ip, community, OID_CDP_CACHE_ADDRESS)
        device_id_data = self._walk(dev.ip, community, OID_CDP_CACHE_DEVICE_ID)
        device_port    = self._walk(dev.ip, community, OID_CDP_CACHE_DEVICE_PORT)
        local_intf     = self._walk(dev.ip, community, OID_CDP_CACHE_LOCAL_INTF)

        for oid, raw_addr in address_data.items():
            suffix = oid[len(OID_CDP_CACHE_ADDRESS):]
            remote_ip = self._parse_cdp_address(raw_addr)
            if not remote_ip:
                continue
            remote_hostname = str(device_id_data.get(OID_CDP_CACHE_DEVICE_ID + suffix, ""))
            remote_port_str = str(device_port.get(OID_CDP_CACHE_DEVICE_PORT + suffix, ""))
            local_port_str  = str(local_intf.get(OID_CDP_CACHE_LOCAL_INTF + suffix, ""))

            links.append(Link(
                local_ip=dev.ip,
                local_port=local_port_str,
                remote_ip=remote_ip,
                remote_port=remote_port_str,
                remote_hostname=remote_hostname,
                method="cdp",
            ))

        if links:
            logger.debug(f"CDP {dev.ip}: {len(links)} komşu")
        return links

    # ------------------------------------------------------------------
    # Bridge MIB – MAC address table cross-referans
    # ------------------------------------------------------------------

    def _collect_bridge_fdb(
        self, dev: NetworkDevice, all_devices: List[NetworkDevice]
    ) -> List[Link]:
        """
        Switch'in MAC tablosunu çeker. Eğer başka bir switch'in MAC'i
        bu tabloda görünüyorsa iki switch arasında bağlantı olduğunu gösterir.
        """
        links: List[Link] = []
        community = dev.snmp_community

        fdb_mac    = self._walk(dev.ip, community, OID_FDB_TABLE)
        fdb_port   = self._walk(dev.ip, community, OID_FDB_PORT)
        fdb_status = self._walk(dev.ip, community, OID_FDB_STATUS)

        switch_macs: Set[str] = set()
        for d in all_devices:
            if d.is_switch and d.ip != dev.ip:
                for m in [d.mac, d.bridge_mac]:
                    if m:
                        switch_macs.add(m.upper().replace("-", ":"))
                for p in d.ports:
                    if p.mac:
                        switch_macs.add(p.mac.upper().replace("-", ":"))

        for oid, raw_mac in fdb_mac.items():
            suffix = oid[len(OID_FDB_TABLE):]
            # Status 3 = learned
            status = str(fdb_status.get(OID_FDB_STATUS + suffix, ""))
            if status not in ("3", "learned"):
                continue

            mac = self._format_mac(raw_mac)
            if mac not in switch_macs:
                continue

            remote_ip = self._mac_to_ip.get(mac, "")
            if not remote_ip or remote_ip == dev.ip:
                continue

            port_num = str(fdb_port.get(OID_FDB_PORT + suffix, ""))

            links.append(Link(
                local_ip=dev.ip,
                local_port=f"Port{port_num}",
                remote_ip=remote_ip,
                remote_port="",
                method="bridge",
            ))

        if links:
            logger.debug(f"Bridge FDB {dev.ip}: {len(links)} komşu switch MAC")
        return links

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def _walk(self, ip: str, community: str, base_oid: str) -> Dict[str, any]:
        result = {}
        try:
            from pysnmp.hlapi import (  # type: ignore
                nextCmd, SnmpEngine, CommunityData,
                UdpTransportTarget, ContextData,
                ObjectType, ObjectIdentity,
            )
            for errorInd, errorSt, _, varBinds in nextCmd(
                SnmpEngine(),
                CommunityData(community, mpModel=1),
                UdpTransportTarget(
                    (ip, 161), timeout=self.timeout, retries=self.retries
                ),
                ContextData(),
                ObjectType(ObjectIdentity(base_oid)),
                lexicographicMode=False,
            ):
                if errorInd or errorSt:
                    break
                for vb in varBinds:
                    result[str(vb[0])] = vb[1]
        except Exception as exc:
            logger.debug(f"WALK {ip} {base_oid}: {exc}")
        return result

    @staticmethod
    def _parse_cdp_address(raw) -> str:
        """CDP adres byte dizisini IP'ye çevirir."""
        try:
            b = bytes(raw)
            if len(b) >= 4:
                return ".".join(str(x) for x in b[-4:])
        except Exception:
            pass
        try:
            s = str(raw)
            parts = [p for p in s.replace("0x", "").split(".") if p]
            if len(parts) >= 4:
                return ".".join(str(int(p, 16)) for p in parts[-4:])
        except Exception:
            pass
        return ""

    @staticmethod
    def _format_mac(raw) -> str:
        try:
            if isinstance(raw, (bytes, bytearray)):
                return ":".join(f"{b:02X}" for b in raw)
            s = str(raw).replace("0x", "").replace("-", "").replace(":", "")
            if len(s) == 12:
                return ":".join(s[i:i+2].upper() for i in range(0, 12, 2))
        except Exception:
            pass
        return ""

    @staticmethod
    def _is_valid_ip(ip: str) -> bool:
        import re
        return bool(re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip))

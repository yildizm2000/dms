"""
Switch Identifier - SNMP MIB tabanlı cihaz tanımlama
=====================================================
Keşfedilen hostları SNMP üzerinden sorgular; Bridge MIB,
sysObjectID ve sysDescr analizine göre switch olarak sınıflandırır.
Üretici, model, firmware ve port sayısı gibi detayları toplar.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# OID sabitleri
# ------------------------------------------------------------------
OID_SYS_DESCR       = "1.3.6.1.2.1.1.1.0"
OID_SYS_OBJECT_ID   = "1.3.6.1.2.1.1.2.0"
OID_SYS_NAME        = "1.3.6.1.2.1.1.5.0"
OID_SYS_LOCATION    = "1.3.6.1.2.1.1.6.0"
OID_SYS_CONTACT     = "1.3.6.1.2.1.1.4.0"
OID_SYS_UPTIME      = "1.3.6.1.2.1.1.3.0"

# Bridge MIB - sadece switch/bridge cihazlarda bulunur
OID_DOT1D_BASE_BRIDGE_ADDR   = "1.3.6.1.2.1.17.1.1.0"
OID_DOT1D_BASE_NUM_PORTS     = "1.3.6.1.2.1.17.1.2.0"
OID_DOT1D_BASE_TYPE          = "1.3.6.1.2.1.17.1.3.0"

# IF-MIB - arayüz tablosu
OID_IF_TABLE         = "1.3.6.1.2.1.2.2"
OID_IF_DESCR         = "1.3.6.1.2.1.2.2.1.2"
OID_IF_OPER_STATUS   = "1.3.6.1.2.1.2.2.1.8"
OID_IF_SPEED         = "1.3.6.1.2.1.2.2.1.5"
OID_IF_PHYS_ADDR     = "1.3.6.1.2.1.2.2.1.6"
OID_IF_HIGH_SPEED    = "1.3.6.1.2.1.31.1.1.1.15"  # ifHighSpeed (Mbps)
OID_IF_ALIAS         = "1.3.6.1.2.1.31.1.1.1.18"  # ifAlias (port açıklaması)

# VLAN - Cisco/generic
OID_CISCO_VLAN_TABLE = "1.3.6.1.4.1.9.9.46.1.3.1"

# Enterprise OID kökleri -> üretici eşleşmesi
VENDOR_OID_MAP: Dict[str, str] = {
    "1.3.6.1.4.1.9":     "Cisco",
    "1.3.6.1.4.1.11":    "HP/Aruba",
    "1.3.6.1.4.1.43":    "3Com",
    "1.3.6.1.4.1.171":   "D-Link",
    "1.3.6.1.4.1.2636":  "Juniper",
    "1.3.6.1.4.1.6486":  "Alcatel-Lucent",
    "1.3.6.1.4.1.4526":  "Netgear",
    "1.3.6.1.4.1.3375":  "F5",
    "1.3.6.1.4.1.1916":  "Extreme Networks",
    "1.3.6.1.4.1.2272":  "Nortel/Avaya",
    "1.3.6.1.4.1.890":   "Zyxel",
    "1.3.6.1.4.1.674":   "Dell",
    "1.3.6.1.4.1.25506": "H3C/Huawei",
    "1.3.6.1.4.1.2011":  "Huawei",
    "1.3.6.1.4.1.8886":  "MikroTik",
    "1.3.6.1.4.1.14823": "Aruba",
}

# sysDescr içinde aranacak anahtar kelimeler
SWITCH_KEYWORDS = [
    r"switch", r"catalyst", r"nexus", r"procurve", r"powerconnect",
    r"ex\d{4}", r"qfx", r"srx", r"dgs-", r"dxs-", r"gs\d{3}",
    r"fastiron", r"icx", r"bigswitch", r"cumulus", r"edgeos",
    r"routeros", r"comware", r"vrp", r"eos\b", r"junos",
]


@dataclass
class SwitchPort:
    index: int
    name: str = ""
    alias: str = ""
    speed_mbps: int = 0
    oper_status: str = "unknown"  # up / down / testing
    mac: str = ""


@dataclass
class NetworkDevice:
    ip: str
    mac: str = ""
    hostname: str = ""
    sys_name: str = ""
    sys_descr: str = ""
    sys_location: str = ""
    sys_contact: str = ""
    uptime_seconds: int = 0
    vendor: str = "Unknown"
    model: str = ""
    object_id: str = ""
    is_switch: bool = False
    bridge_mac: str = ""
    port_count: int = 0
    ports: List[SwitchPort] = field(default_factory=list)
    vlans: List[int] = field(default_factory=list)
    snmp_community: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        return (
            f"<NetworkDevice ip={self.ip} vendor={self.vendor} "
            f"model={self.model} switch={self.is_switch} ports={self.port_count}>"
        )


class SwitchIdentifier:
    """
    Keşfedilen host listesini SNMP ile sorgular ve
    NetworkDevice nesneleri döndürür.

    is_switch=True olan cihazlar kesin switch/bridge olarak
    sınıflandırılmıştır.
    """

    def __init__(self, community: str = "public", timeout: float = 2.0, retries: int = 1):
        self.community = community
        self.timeout = timeout
        self.retries = retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def identify(self, hosts) -> List[NetworkDevice]:
        """
        hosts: DiscoveredHost listesi (scanner.py çıktısı)
        Döndürür: NetworkDevice listesi
        """
        devices = []
        for host in hosts:
            community = host.snmp_community or self.community
            if not community:
                # SNMP kapalıysa temel bilgiyle kaydet
                dev = NetworkDevice(ip=host.ip, mac=host.mac, hostname=host.hostname)
                devices.append(dev)
                continue

            dev = self._query_device(host.ip, community, host.mac, host.hostname)
            if dev:
                devices.append(dev)
            else:
                # SNMP cevap vermedi
                devices.append(
                    NetworkDevice(ip=host.ip, mac=host.mac, hostname=host.hostname)
                )

        switches = [d for d in devices if d.is_switch]
        logger.info(
            f"Tanımlama tamamlandı: {len(devices)} cihaz, "
            f"{len(switches)} switch tespit edildi."
        )
        return devices

    # ------------------------------------------------------------------
    # SNMP sorgulama
    # ------------------------------------------------------------------

    def _query_device(
        self, ip: str, community: str, mac: str = "", hostname: str = ""
    ) -> Optional[NetworkDevice]:
        try:
            from pysnmp.hlapi import (  # type: ignore
                getCmd, nextCmd,
                SnmpEngine, CommunityData,
                UdpTransportTarget, ContextData,
                ObjectType, ObjectIdentity,
            )
        except ImportError:
            logger.error("pysnmp kurulu değil: pip install pysnmp")
            return None

        dev = NetworkDevice(
            ip=ip, mac=mac, hostname=hostname, snmp_community=community
        )

        # --- Sistem bilgileri ---
        sys_oids = {
            "descr":    OID_SYS_DESCR,
            "name":     OID_SYS_NAME,
            "location": OID_SYS_LOCATION,
            "contact":  OID_SYS_CONTACT,
            "objid":    OID_SYS_OBJECT_ID,
            "uptime":   OID_SYS_UPTIME,
        }
        sys_data = self._get_multiple(ip, community, list(sys_oids.values()))
        if sys_data is None:
            return None  # SNMP yanıt yok

        dev.sys_descr    = str(sys_data.get(OID_SYS_DESCR, ""))
        dev.sys_name     = str(sys_data.get(OID_SYS_NAME, ""))
        dev.sys_location = str(sys_data.get(OID_SYS_LOCATION, ""))
        dev.sys_contact  = str(sys_data.get(OID_SYS_CONTACT, ""))
        dev.object_id    = str(sys_data.get(OID_SYS_OBJECT_ID, ""))

        uptime_raw = sys_data.get(OID_SYS_UPTIME)
        if uptime_raw:
            try:
                dev.uptime_seconds = int(str(uptime_raw).split("(")[1].split(")")[0]) // 100
            except Exception:
                pass

        # --- Üretici tespiti ---
        dev.vendor = self._detect_vendor(dev.object_id, dev.sys_descr)
        dev.model  = self._detect_model(dev.sys_descr)

        # --- Switch mi? (Bridge MIB kontrolü) ---
        bridge_data = self._get_multiple(
            ip, community,
            [OID_DOT1D_BASE_BRIDGE_ADDR, OID_DOT1D_BASE_NUM_PORTS, OID_DOT1D_BASE_TYPE],
        )
        if bridge_data and bridge_data.get(OID_DOT1D_BASE_BRIDGE_ADDR):
            dev.is_switch = True
            dev.bridge_mac = self._format_mac(
                bridge_data.get(OID_DOT1D_BASE_BRIDGE_ADDR, b"")
            )
            try:
                dev.port_count = int(str(bridge_data.get(OID_DOT1D_BASE_NUM_PORTS, 0)))
            except (ValueError, TypeError):
                dev.port_count = 0
        else:
            # Anahtar kelime ile ikincil kontrol
            dev.is_switch = self._keyword_is_switch(dev.sys_descr)

        # --- Port detayları ---
        if dev.is_switch:
            dev.ports = self._collect_ports(ip, community)
            if not dev.port_count:
                dev.port_count = len(dev.ports)

        logger.info(
            f"{'[SWITCH]' if dev.is_switch else '[HOST  ]'} "
            f"{ip:16s} | {dev.vendor:15s} | {dev.model or dev.sys_name}"
        )
        return dev

    # ------------------------------------------------------------------
    # SNMP yardımcıları
    # ------------------------------------------------------------------

    def _get_multiple(
        self, ip: str, community: str, oids: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Birden fazla OID'yi tek seferde sorgular."""
        try:
            from pysnmp.hlapi import (  # type: ignore
                getCmd, SnmpEngine, CommunityData,
                UdpTransportTarget, ContextData,
                ObjectType, ObjectIdentity,
            )
            objs = [ObjectType(ObjectIdentity(oid)) for oid in oids]
            errorInd, errorSt, _, varBinds = next(
                getCmd(
                    SnmpEngine(),
                    CommunityData(community, mpModel=1),
                    UdpTransportTarget(
                        (ip, 161), timeout=self.timeout, retries=self.retries
                    ),
                    ContextData(),
                    *objs,
                )
            )
            if errorInd or errorSt:
                return None
            result = {}
            for vb in varBinds:
                result[str(vb[0])] = vb[1]
            return result
        except Exception as exc:
            logger.debug(f"SNMP GET {ip}: {exc}")
            return None

    def _walk(self, ip: str, community: str, base_oid: str) -> Dict[str, Any]:
        """OID altındaki tüm değerleri döndürür (SNMP WALK)."""
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
            logger.debug(f"SNMP WALK {ip} {base_oid}: {exc}")
        return result

    def _collect_ports(self, ip: str, community: str) -> List[SwitchPort]:
        ports: Dict[int, SwitchPort] = {}

        descr_data  = self._walk(ip, community, OID_IF_DESCR)
        status_data = self._walk(ip, community, OID_IF_OPER_STATUS)
        speed_data  = self._walk(ip, community, OID_IF_HIGH_SPEED)
        alias_data  = self._walk(ip, community, OID_IF_ALIAS)
        mac_data    = self._walk(ip, community, OID_IF_PHYS_ADDR)

        # IF-MIB index -> port
        for oid, val in descr_data.items():
            idx = int(oid.split(".")[-1])
            ports[idx] = SwitchPort(index=idx, name=str(val))

        for oid, val in status_data.items():
            idx = int(oid.split(".")[-1])
            status_map = {1: "up", 2: "down", 3: "testing", 5: "dormant"}
            ports.setdefault(idx, SwitchPort(index=idx))
            try:
                ports[idx].oper_status = status_map.get(int(val), str(val))
            except (TypeError, ValueError):
                ports[idx].oper_status = str(val)

        for oid, val in speed_data.items():
            idx = int(oid.split(".")[-1])
            ports.setdefault(idx, SwitchPort(index=idx))
            try:
                ports[idx].speed_mbps = int(val)
            except (TypeError, ValueError):
                pass

        for oid, val in alias_data.items():
            idx = int(oid.split(".")[-1])
            ports.setdefault(idx, SwitchPort(index=idx))
            ports[idx].alias = str(val)

        for oid, val in mac_data.items():
            idx = int(oid.split(".")[-1])
            ports.setdefault(idx, SwitchPort(index=idx))
            ports[idx].mac = self._format_mac(val)

        return sorted(ports.values(), key=lambda p: p.index)

    # ------------------------------------------------------------------
    # Üretici / model tespiti
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_vendor(object_id: str, sys_descr: str) -> str:
        for prefix, vendor in VENDOR_OID_MAP.items():
            if object_id.startswith(prefix):
                return vendor
        descr_lower = sys_descr.lower()
        keyword_vendor = {
            "cisco": "Cisco", "juniper": "Juniper", "junos": "Juniper",
            "hp ": "HP/Aruba", "procurve": "HP/Aruba", "aruba": "Aruba",
            "d-link": "D-Link", "dlink": "D-Link",
            "netgear": "Netgear", "zyxel": "Zyxel",
            "huawei": "Huawei", "vrp": "Huawei",
            "mikrotik": "MikroTik", "routeros": "MikroTik",
            "dell": "Dell", "extreme": "Extreme Networks",
            "ubiquiti": "Ubiquiti", "edgeos": "Ubiquiti",
        }
        for kw, vendor in keyword_vendor.items():
            if kw in descr_lower:
                return vendor
        return "Unknown"

    @staticmethod
    def _detect_model(sys_descr: str) -> str:
        patterns = [
            r"(?:Cisco\s+)?([A-Z]{2,}[-\s]?\d{4}[A-Z0-9\-]*)",  # Cisco Catalyst 2960
            r"((?:WS|C|N|EX|QFX|SRX|MX)\d[-\w]+)",               # WS-C2960, N5K-C5596
            r"((?:DGS|DXS|DES|DWC)[-\d]+)",                       # D-Link
            r"(ProCurve\s+\w+)",                                   # HP ProCurve
            r"(ICX\s*\d+)",                                        # Brocade ICX
            r"([A-Z]{1,4}\d{2,4}[A-Z]{0,4}(?:-[A-Z0-9]+)*)",
        ]
        for pat in patterns:
            m = re.search(pat, sys_descr, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    @staticmethod
    def _keyword_is_switch(sys_descr: str) -> bool:
        descr_lower = sys_descr.lower()
        for kw in SWITCH_KEYWORDS:
            if re.search(kw, descr_lower):
                return True
        return False

    @staticmethod
    def _format_mac(raw) -> str:
        try:
            if isinstance(raw, (bytes, bytearray)):
                return ":".join(f"{b:02X}" for b in raw)
            s = str(raw)
            # "0x1a2b3c4d5e6f" veya "1a:2b:3c:4d:5e:6f"
            s = s.replace("0x", "").replace("-", "").replace(":", "")
            if len(s) == 12:
                return ":".join(s[i:i+2].upper() for i in range(0, 12, 2))
        except Exception:
            pass
        return ""

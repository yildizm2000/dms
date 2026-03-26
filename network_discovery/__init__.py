"""
Network Switch Detection & Topology Mapping
============================================
Ağdaki switch'leri tespit eder, LLDP/CDP/SNMP üzerinden topoloji
bilgisini toplar ve interaktif ağ şeması oluşturur.
"""

from .scanner import NetworkScanner
from .identifier import SwitchIdentifier
from .topology import TopologyBuilder
from .diagram import NetworkDiagram

__all__ = ["NetworkScanner", "SwitchIdentifier", "TopologyBuilder", "NetworkDiagram"]
__version__ = "1.0.0"

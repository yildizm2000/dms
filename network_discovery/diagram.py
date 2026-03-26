"""
Network Diagram Generator
=========================
NetworkDevice + Link listesinden iki çeşit çıktı üretir:

1. Statik PNG/SVG  – Matplotlib + NetworkX (hiyerarşik layout)
2. İnteraktif HTML – PyVis (hover/zoom/drag, tarayıcıda açılır)

Switch'ler kare, diğer host'lar daire şeklinde; bağlantı yöntemi
(LLDP/CDP/Bridge) renk kodlu gösterilir.
"""

import os
import json
import logging
import textwrap
from typing import List, Optional, Dict, Tuple
from .identifier import NetworkDevice
from .topology import Link

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Renk / şekil sabitleri
# ------------------------------------------------------------------
VENDOR_COLORS: Dict[str, str] = {
    "Cisco":            "#1a73e8",
    "HP/Aruba":         "#34a853",
    "Aruba":            "#34a853",
    "Juniper":          "#fbbc05",
    "D-Link":           "#ea4335",
    "Netgear":          "#9c27b0",
    "Huawei":           "#ff5722",
    "MikroTik":         "#795548",
    "Extreme Networks": "#00bcd4",
    "Ubiquiti":         "#607d8b",
    "Zyxel":            "#e91e63",
    "Dell":             "#3f51b5",
    "Unknown":          "#9e9e9e",
}

LINK_COLORS: Dict[str, str] = {
    "lldp":   "#1a73e8",
    "cdp":    "#34a853",
    "bridge": "#fbbc05",
    "manual": "#ea4335",
    "unknown":"#9e9e9e",
}

LINK_LABELS: Dict[str, str] = {
    "lldp":   "LLDP",
    "cdp":    "CDP",
    "bridge": "Bridge",
    "manual": "Manual",
    "unknown":"?",
}


class NetworkDiagram:
    """
    Kullanım::

        diagram = NetworkDiagram(devices, links)
        diagram.save_html("network.html")
        diagram.save_png("network.png")
        diagram.save_json("network.json")
    """

    def __init__(
        self,
        devices: List[NetworkDevice],
        links: List[Link],
        title: str = "Network Topology",
    ):
        self.devices = devices
        self.links = links
        self.title = title
        self._ip_to_dev: Dict[str, NetworkDevice] = {d.ip: d for d in devices}

    # ------------------------------------------------------------------
    # İnteraktif HTML (PyVis)
    # ------------------------------------------------------------------

    def save_html(self, output_path: str = "network_topology.html") -> str:
        """
        PyVis ile interaktif HTML şeması oluşturur.
        Tarayıcıda açıldığında node'lar sürüklenebilir, hover'da
        detaylı bilgi görünür.
        """
        try:
            from pyvis.network import Network  # type: ignore
        except ImportError:
            logger.error("pyvis bulunamadı: pip install pyvis")
            return self._save_html_fallback(output_path)

        net = Network(
            height="900px",
            width="100%",
            bgcolor="#1a1a2e",
            font_color="#eee",
            directed=False,
            notebook=False,
        )
        net.set_options(self._pyvis_options())

        # Node'lar
        for dev in self.devices:
            color = VENDOR_COLORS.get(dev.vendor, VENDOR_COLORS["Unknown"])
            shape = "square" if dev.is_switch else "dot"
            size  = 35 if dev.is_switch else 20
            label = self._node_label(dev)
            title = self._node_tooltip(dev)

            net.add_node(
                dev.ip,
                label=label,
                title=title,
                color=color,
                shape=shape,
                size=size,
                font={"size": 11, "color": "#ffffff"},
            )

        # Kenarlar
        seen = set()
        for link in self.links:
            key = tuple(sorted([link.local_ip, link.remote_ip]))
            if key in seen:
                continue
            seen.add(key)

            # Her iki uç da bilinmeli
            if link.local_ip not in self._ip_to_dev or link.remote_ip not in self._ip_to_dev:
                continue

            color = LINK_COLORS.get(link.method, LINK_COLORS["unknown"])
            label = LINK_LABELS.get(link.method, "?")
            edge_title = (
                f"{link.local_ip} [{link.local_port}]"
                f" ↔ {link.remote_ip} [{link.remote_port}]"
                f" via {link.method.upper()}"
            )
            net.add_edge(
                link.local_ip,
                link.remote_ip,
                title=edge_title,
                label=label,
                color=color,
                width=2,
                font={"size": 9, "color": "#cccccc"},
            )

        # Legend ekle
        self._add_legend_nodes(net)

        net.save_graph(output_path)
        logger.info(f"HTML şeması kaydedildi: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Statik PNG  (Matplotlib + NetworkX)
    # ------------------------------------------------------------------

    def save_png(self, output_path: str = "network_topology.png", dpi: int = 150) -> str:
        try:
            import networkx as nx
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches
        except ImportError as exc:
            logger.error(f"networkx/matplotlib bulunamadı: {exc}")
            return ""

        G = nx.Graph()
        for dev in self.devices:
            G.add_node(dev.ip, **self._node_attrs(dev))

        seen = set()
        for link in self.links:
            key = tuple(sorted([link.local_ip, link.remote_ip]))
            if key in seen:
                continue
            seen.add(key)
            if link.local_ip in G and link.remote_ip in G:
                G.add_edge(link.local_ip, link.remote_ip, method=link.method)

        # Layout: switch'ler üstte, host'lar altta
        pos = self._hierarchical_layout(G)

        fig, ax = plt.subplots(figsize=(18, 12), facecolor="#1a1a2e")
        ax.set_facecolor("#1a1a2e")
        ax.set_title(self.title, color="white", fontsize=16, pad=20)

        # Kenarları yöntemine göre renkle çiz
        for method, color in LINK_COLORS.items():
            edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("method") == method]
            if edges:
                nx.draw_networkx_edges(
                    G, pos, edgelist=edges, edge_color=color,
                    width=1.8, alpha=0.8, ax=ax
                )

        # Switch node'ları
        switch_nodes = [n for n, d in G.nodes(data=True) if d.get("is_switch")]
        host_nodes   = [n for n, d in G.nodes(data=True) if not d.get("is_switch")]

        switch_colors = [
            VENDOR_COLORS.get(G.nodes[n].get("vendor", "Unknown"), "#9e9e9e")
            for n in switch_nodes
        ]
        host_colors = [
            VENDOR_COLORS.get(G.nodes[n].get("vendor", "Unknown"), "#9e9e9e")
            for n in host_nodes
        ]

        nx.draw_networkx_nodes(
            G, pos, nodelist=switch_nodes, node_color=switch_colors,
            node_size=1200, node_shape="s", ax=ax, alpha=0.9
        )
        nx.draw_networkx_nodes(
            G, pos, nodelist=host_nodes, node_color=host_colors,
            node_size=500, node_shape="o", ax=ax, alpha=0.7
        )

        # Etiketler
        labels = {
            n: self._node_label_short(G.nodes[n]) for n in G.nodes()
        }
        nx.draw_networkx_labels(
            G, pos, labels=labels, font_size=7,
            font_color="white", ax=ax
        )

        # Legend
        legend_handles = [
            mpatches.Patch(color=c, label=LINK_LABELS[m])
            for m, c in LINK_COLORS.items() if m != "unknown"
        ]
        legend_handles += [
            mpatches.Patch(color="#888", label="Switch (kare)"),
            mpatches.Patch(color="#555", label="Host (daire)"),
        ]
        ax.legend(
            handles=legend_handles, loc="lower right",
            facecolor="#2d2d44", labelcolor="white", fontsize=9
        )

        ax.axis("off")
        plt.tight_layout()
        plt.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close()
        logger.info(f"PNG şeması kaydedildi: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # JSON çıktısı (başka araçlarla entegrasyon için)
    # ------------------------------------------------------------------

    def save_json(self, output_path: str = "network_topology.json") -> str:
        data = {
            "title": self.title,
            "devices": [],
            "links": [],
            "summary": self._summary(),
        }
        for dev in self.devices:
            data["devices"].append({
                "ip":        dev.ip,
                "mac":       dev.mac,
                "hostname":  dev.hostname or dev.sys_name,
                "vendor":    dev.vendor,
                "model":     dev.model,
                "is_switch": dev.is_switch,
                "port_count":dev.port_count,
                "location":  dev.sys_location,
                "uptime_s":  dev.uptime_seconds,
                "ports": [
                    {
                        "index":       p.index,
                        "name":        p.name,
                        "alias":       p.alias,
                        "speed_mbps":  p.speed_mbps,
                        "oper_status": p.oper_status,
                    }
                    for p in dev.ports
                ],
            })
        seen = set()
        for link in self.links:
            key = tuple(sorted([link.local_ip, link.remote_ip]))
            if key in seen:
                continue
            seen.add(key)
            data["links"].append({
                "local_ip":         link.local_ip,
                "local_port":       link.local_port,
                "remote_ip":        link.remote_ip,
                "remote_port":      link.remote_port,
                "remote_hostname":  link.remote_hostname,
                "method":           link.method,
            })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"JSON verisi kaydedildi: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Özet metin raporu
    # ------------------------------------------------------------------

    def print_summary(self):
        from rich.console import Console
        from rich.table import Table

        console = Console()
        s = self._summary()

        console.print(f"\n[bold cyan]{self.title}[/bold cyan]")
        console.print(f"Toplam cihaz   : [bold]{s['total_devices']}[/bold]")
        console.print(f"Switch sayısı  : [bold green]{s['switch_count']}[/bold green]")
        console.print(f"Host sayısı    : [bold]{s['host_count']}[/bold]")
        console.print(f"Bağlantı sayısı: [bold]{s['link_count']}[/bold]")
        console.print()

        # Switch tablosu
        table = Table(title="Tespit Edilen Switch'ler", style="cyan")
        table.add_column("IP",        style="bold yellow")
        table.add_column("Hostname",  style="white")
        table.add_column("Üretici",   style="cyan")
        table.add_column("Model",     style="white")
        table.add_column("Port",      justify="right")
        table.add_column("Konum",     style="dim")

        for dev in self.devices:
            if dev.is_switch:
                table.add_row(
                    dev.ip,
                    dev.hostname or dev.sys_name or "-",
                    dev.vendor,
                    dev.model or "-",
                    str(dev.port_count) if dev.port_count else "-",
                    dev.sys_location or "-",
                )
        console.print(table)

    # ------------------------------------------------------------------
    # Yardımcı metotlar
    # ------------------------------------------------------------------

    def _summary(self) -> Dict:
        switches = [d for d in self.devices if d.is_switch]
        return {
            "total_devices": len(self.devices),
            "switch_count":  len(switches),
            "host_count":    len(self.devices) - len(switches),
            "link_count":    len(set(
                tuple(sorted([l.local_ip, l.remote_ip])) for l in self.links
            )),
            "vendors": list({d.vendor for d in switches}),
        }

    @staticmethod
    def _node_label(dev: NetworkDevice) -> str:
        name = dev.sys_name or dev.hostname or dev.ip
        lines = [dev.ip]
        if name and name != dev.ip:
            lines.insert(0, name[:20])
        if dev.vendor and dev.vendor != "Unknown":
            lines.append(dev.vendor[:12])
        if dev.model:
            lines.append(dev.model[:15])
        return "\n".join(lines)

    @staticmethod
    def _node_label_short(attrs: Dict) -> str:
        name = attrs.get("sys_name") or attrs.get("hostname") or attrs.get("ip", "")
        return name[:18] if name else ""

    @staticmethod
    def _node_tooltip(dev: NetworkDevice) -> str:
        lines = [
            f"<b>{dev.sys_name or dev.hostname or dev.ip}</b>",
            f"IP: {dev.ip}",
            f"MAC: {dev.mac or dev.bridge_mac or '-'}",
            f"Üretici: {dev.vendor}",
            f"Model: {dev.model or '-'}",
            f"Switch: {'Evet' if dev.is_switch else 'Hayır'}",
        ]
        if dev.port_count:
            lines.append(f"Port: {dev.port_count}")
        if dev.sys_location:
            lines.append(f"Konum: {dev.sys_location}")
        if dev.uptime_seconds:
            h = dev.uptime_seconds // 3600
            lines.append(f"Uptime: {h} saat")
        return "<br>".join(lines)

    @staticmethod
    def _node_attrs(dev: NetworkDevice) -> Dict:
        return {
            "ip":        dev.ip,
            "sys_name":  dev.sys_name,
            "hostname":  dev.hostname,
            "vendor":    dev.vendor,
            "model":     dev.model,
            "is_switch": dev.is_switch,
        }

    @staticmethod
    def _hierarchical_layout(G) -> Dict:
        """Switch'leri üst katmana, host'ları alt katmana yerleştirir."""
        try:
            import networkx as nx
        except ImportError:
            return {}

        switches = [n for n, d in G.nodes(data=True) if d.get("is_switch")]
        hosts    = [n for n, d in G.nodes(data=True) if not d.get("is_switch")]

        pos = {}
        # Switch'leri üst satıra yay
        for i, n in enumerate(switches):
            x = (i - len(switches) / 2) * 2.0
            pos[n] = (x, 1.0)

        # Host'ları alt satıra yay
        for i, n in enumerate(hosts):
            x = (i - len(hosts) / 2) * 1.5
            pos[n] = (x, 0.0)

        # Bağlantısız node varsa spring ile yerleştir
        isolated = [n for n in G.nodes() if n not in pos]
        if isolated:
            spring = nx.spring_layout(G.subgraph(isolated), seed=42)
            pos.update(spring)

        return pos

    @staticmethod
    def _pyvis_options() -> str:
        return json.dumps({
            "physics": {
                "enabled": True,
                "barnesHut": {
                    "gravitationalConstant": -8000,
                    "springConstant": 0.04,
                    "springLength": 180,
                },
                "stabilization": {"iterations": 200},
            },
            "interaction": {
                "hover": True,
                "tooltipDelay": 200,
                "zoomView": True,
                "dragView": True,
            },
            "edges": {
                "smooth": {"type": "dynamic"},
                "arrows": {"to": {"enabled": False}},
            },
        })

    # ------------------------------------------------------------------
    # PyVis olmadığında saf HTML fallback
    # ------------------------------------------------------------------

    def _save_html_fallback(self, output_path: str) -> str:
        """PyVis yoksa JSON tabanlı basit D3 sayfası üretir."""
        nodes = []
        for dev in self.devices:
            nodes.append({
                "id":    dev.ip,
                "label": dev.sys_name or dev.hostname or dev.ip,
                "group": dev.vendor,
            })
        edges = []
        seen = set()
        for link in self.links:
            key = tuple(sorted([link.local_ip, link.remote_ip]))
            if key not in seen:
                seen.add(key)
                edges.append({"from": link.local_ip, "to": link.remote_ip, "label": link.method})

        html = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="tr">
        <head>
          <meta charset="UTF-8">
          <title>{self.title}</title>
          <style>
            body {{ background:#1a1a2e; color:#eee; font-family:monospace; }}
            pre  {{ background:#16213e; padding:16px; border-radius:6px; overflow:auto; }}
          </style>
        </head>
        <body>
          <h2>{self.title}</h2>
          <p>Cihaz: {len(self.devices)} | Switch: {sum(1 for d in self.devices if d.is_switch)} | Bağlantı: {len(edges)}</p>
          <h3>Topoloji Verisi (JSON)</h3>
          <pre>{json.dumps({"nodes": nodes, "edges": edges}, indent=2, ensure_ascii=False)}</pre>
        </body>
        </html>
        """)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"Fallback HTML kaydedildi: {output_path}")
        return output_path

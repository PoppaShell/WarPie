#!/usr/bin/env python3
"""
WarPie WiFi Adapter Configuration
Interactive configuration using InquirerPy for beautiful prompts.
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Check for dependencies
try:
    from InquirerPy import inquirer
    from InquirerPy.separator import Separator
    from rich.console import Console
    from rich.table import Table
except ImportError:
    print("Installing required packages...")
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                          "inquirerpy", "rich", "-q"])
    from InquirerPy import inquirer
    from InquirerPy.separator import Separator
    from rich.console import Console
    from rich.table import Table

console = Console()

# Channel constants
CHANNELS_24_ALL = "1,2,3,4,5,6,7,8,9,10,11"
CHANNELS_24_NONOVERLAP = "1,6,11"
CHANNELS_5_ALL = "36,40,44,48,52,56,60,64,100,104,108,112,116,120,124,128,132,136,140,144,149,153,157,161,165"
CHANNELS_6_PSC = "5,21,37,53,69,85,101,117,133,149,165,181,197,213,229"

# Known WiFi chipsets
WIFI_CHIPSETS = {
    "brcmfmac": ("Raspberry Pi Internal", "Broadcom"),
    "rt2800usb": ("Ralink RT3070/RT5370", "2.4GHz"),
    "mt7921u": ("MediaTek MT7921AU", "e.g., AWUS036AXML"),
    "rtl8xxxu": ("Realtek RTL8xxxU", "Various"),
    "ath9k_htc": ("Atheros AR9271", "e.g., ALFA AWUS036NHA"),
    "88XXau": ("Realtek RTL8812AU/21AU", "e.g., ALFA AWUS036ACH"),
}


@dataclass
class WifiAdapter:
    """Represents a detected WiFi adapter."""
    interface: str
    mac: str
    driver: str
    bands: list[str] = field(default_factory=list)

    @property
    def driver_name(self) -> str:
        """Get human-readable driver name."""
        if self.driver in WIFI_CHIPSETS:
            name, desc = WIFI_CHIPSETS[self.driver]
            return f"{name} ({desc})"
        return self.driver

    @property
    def bands_str(self) -> str:
        """Get bands as space-separated string."""
        return " ".join(self.bands)


@dataclass
class AdapterConfig:
    """Configuration for a single adapter."""
    interface: str
    mac: str
    name: str
    enabled_bands: list[str]
    channels_24: str = ""
    channels_5: str = ""
    channels_6: str = ""


def detect_wifi_interfaces() -> list[WifiAdapter]:
    """Detect all WiFi interfaces and their capabilities."""
    adapters = []

    # Find all wireless interfaces
    net_path = Path("/sys/class/net")
    for iface_path in net_path.iterdir():
        # Check if it's a wireless interface
        wireless_path = iface_path / "wireless"
        phy_path = iface_path / "phy80211"

        if not (wireless_path.exists() or phy_path.exists()):
            continue

        iface = iface_path.name

        # Get MAC address
        try:
            mac = (iface_path / "address").read_text().strip().upper()
        except:
            mac = "00:00:00:00:00:00"

        # Get driver
        driver = "unknown"
        driver_path = iface_path / "device" / "driver"
        if driver_path.exists():
            try:
                driver = driver_path.resolve().name
            except:
                pass

        # Detect bands from phy capabilities
        bands = detect_bands(iface)

        adapters.append(WifiAdapter(
            interface=iface,
            mac=mac,
            driver=driver,
            bands=bands
        ))

    return sorted(adapters, key=lambda a: a.interface)


def detect_bands(interface: str) -> list[str]:
    """Detect supported bands for an interface using iw."""
    bands = []

    try:
        # Get phy name
        phy_path = Path(f"/sys/class/net/{interface}/phy80211/name")
        if phy_path.exists():
            phy = phy_path.read_text().strip()
        else:
            return ["2.4GHz"]  # Default assumption

        # Query iw for band info
        result = subprocess.run(
            ["iw", "phy", phy, "info"],
            capture_output=True, text=True
        )

        output = result.stdout
        if "2407 MHz" in output or "2412 MHz" in output:
            bands.append("2.4GHz")
        if "5180 MHz" in output or "5745 MHz" in output:
            bands.append("5GHz")
        if "5955 MHz" in output or "6115 MHz" in output:
            bands.append("6GHz")

    except Exception:
        bands = ["2.4GHz"]  # Safe default

    return bands if bands else ["2.4GHz"]


def display_adapters(adapters: list[WifiAdapter]) -> None:
    """Display detected adapters in a table."""
    table = Table(title="Detected WiFi Interfaces")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Interface", style="green")
    table.add_column("MAC Address", style="dim")
    table.add_column("Bands", style="yellow")
    table.add_column("Device", style="white")

    for i, adapter in enumerate(adapters, 1):
        table.add_row(
            str(i),
            adapter.interface,
            adapter.mac,
            adapter.bands_str,
            adapter.driver_name
        )

    console.print(table)


def select_ap_interface(adapters: list[WifiAdapter]) -> WifiAdapter:
    """Select the Access Point interface."""
    console.print("\n[bold cyan]Step 1: Select Access Point Interface[/bold cyan]")
    console.print("Which interface should be used for the WarPie AP and home WiFi connection?")
    console.print("[dim](Usually the Raspberry Pi's internal WiFi - look for 'Broadcom')[/dim]\n")

    choices = [
        {
            "name": f"{a.interface} - {a.driver_name} [{a.bands_str}]",
            "value": a
        }
        for a in adapters
    ]

    return inquirer.select(
        message="Select AP interface:",
        choices=choices,
    ).execute()


def select_capture_interfaces(
    adapters: list[WifiAdapter],
    exclude: WifiAdapter
) -> list[WifiAdapter]:
    """Select capture interfaces (multi-select with checkboxes)."""
    console.print("\n[bold cyan]Step 2: Select Capture Interface(s)[/bold cyan]")
    console.print("Which interface(s) should be used for Kismet capture?")
    console.print("[dim](Select all external USB adapters for wardriving)[/dim]\n")

    available = [a for a in adapters if a.interface != exclude.interface]

    if not available:
        console.print("[red]No interfaces available for capture![/red]")
        sys.exit(1)

    choices = [
        {
            "name": f"{a.interface} - {a.driver_name} [{a.bands_str}]",
            "value": a
        }
        for a in available
    ]

    selected = inquirer.checkbox(
        message="Select capture interface(s):",
        choices=choices,
        validate=lambda result: len(result) > 0,
        invalid_message="Select at least one interface",
    ).execute()

    console.print(f"[green]Selected {len(selected)} capture interface(s)[/green]")
    return selected


def select_bands(adapter: WifiAdapter) -> list[str]:
    """Select which bands to capture for an adapter."""
    if len(adapter.bands) == 1:
        # Only one band available, auto-select
        return adapter.bands.copy()

    choices = [{"name": band, "value": band} for band in adapter.bands]

    return inquirer.checkbox(
        message=f"Select bands for {adapter.interface}:",
        choices=choices,
        default=adapter.bands,  # All selected by default
        validate=lambda result: len(result) > 0,
        invalid_message="Select at least one band",
    ).execute()


def select_channels(band: str) -> str:
    """Select channel configuration for a band."""
    if band == "2.4GHz":
        choices = [
            {"name": "All channels (1-11)", "value": CHANNELS_24_ALL},
            {"name": "Non-overlapping (1,6,11) - recommended", "value": CHANNELS_24_NONOVERLAP},
            {"name": "Custom list", "value": "custom"},
        ]
    elif band == "5GHz":
        choices = [
            {"name": "All channels (36-165)", "value": CHANNELS_5_ALL},
            {"name": "Custom list", "value": "custom"},
        ]
    else:  # 6GHz
        choices = [
            {"name": "PSC channels (15 channels) - recommended", "value": CHANNELS_6_PSC},
            {"name": "All channels", "value": CHANNELS_6_PSC},  # Use PSC for "all" too
            {"name": "Custom list", "value": "custom"},
        ]

    result = inquirer.select(
        message=f"{band} channel selection:",
        choices=choices,
    ).execute()

    if result == "custom":
        return inquirer.text(
            message="Enter comma-separated channel list:",
            validate=lambda x: len(x) > 0,
        ).execute()

    return result


def generate_adapter_name(index: int, bands: list[str]) -> str:
    """Generate a descriptive name for the adapter."""
    count = len(bands)

    if count == 1:
        band = bands[0]
        if "6GHz" in band:
            return f"WiFi_6GHz_{index}"
        elif "5GHz" in band:
            return f"WiFi_5GHz_{index}"
        else:
            return f"WiFi_24GHz_{index}"
    elif count == 2:
        if "2.4GHz" in bands and "5GHz" in bands:
            return f"WiFi_DualBand_{index}"
        elif "5GHz" in bands and "6GHz" in bands:
            return f"WiFi_HighBand_{index}"
        else:
            return f"WiFi_Mixed_{index}"
    else:
        return f"WiFi_TriBand_{index}"


def configure_adapter(adapter: WifiAdapter, index: int) -> AdapterConfig:
    """Configure bands and channels for a single adapter."""
    console.print(f"\n[bold]━━━ Adapter {index + 1}: {adapter.interface} - {adapter.driver_name} ━━━[/bold]")
    console.print(f"    Capable bands: [cyan]{adapter.bands_str}[/cyan]\n")

    # Select bands
    selected_bands = select_bands(adapter)

    # Select channels for each band
    channels_24 = ""
    channels_5 = ""
    channels_6 = ""

    for band in selected_bands:
        if band == "2.4GHz":
            channels_24 = select_channels(band)
        elif band == "5GHz":
            channels_5 = select_channels(band)
        elif band == "6GHz":
            channels_6 = select_channels(band)

    # Generate name
    name = generate_adapter_name(index, selected_bands)

    config = AdapterConfig(
        interface=adapter.interface,
        mac=adapter.mac,
        name=name,
        enabled_bands=selected_bands,
        channels_24=channels_24,
        channels_5=channels_5,
        channels_6=channels_6,
    )

    # Show confirmation
    console.print(f"\n[green]✓ {adapter.interface} → {name}[/green]")
    console.print(f"    Bands: {', '.join(selected_bands)}")
    if channels_24:
        console.print(f"    2.4GHz channels: {channels_24}")
    if channels_5:
        console.print(f"    5GHz channels: {channels_5}")
    if channels_6:
        console.print(f"    6GHz channels: {channels_6}")

    return config


def save_config(
    ap: WifiAdapter,
    configs: list[AdapterConfig],
    output_path: str = "/etc/warpie/adapters.conf"
) -> None:
    """Save configuration to file."""
    lines = [
        "# WarPie Adapter Configuration",
        "# Generated by warpie_config.py",
        "",
        f'WIFI_AP="{ap.interface}"',
        f'WIFI_AP_MAC="{ap.mac}"',
        f"WIFI_CAPTURE_COUNT={len(configs)}",
        "",
    ]

    for i, cfg in enumerate(configs):
        lines.extend([
            f'ADAPTER_{i}_IFACE="{cfg.interface}"',
            f'ADAPTER_{i}_MAC="{cfg.mac}"',
            f'ADAPTER_{i}_NAME="{cfg.name}"',
            f'ADAPTER_{i}_BANDS="{",".join(cfg.enabled_bands)}"',
            f'ADAPTER_{i}_CHANNELS_24="{cfg.channels_24}"',
            f'ADAPTER_{i}_CHANNELS_5="{cfg.channels_5}"',
            f'ADAPTER_{i}_CHANNELS_6="{cfg.channels_6}"',
            "",
        ])

    # Ensure directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    console.print(f"\n[green]Configuration saved to {output_path}[/green]")


def main():
    """Main entry point."""
    console.print("\n[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  WiFi Adapter Configuration[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]")
    console.print("\nWarPie needs to know which adapter to use for each function:")
    console.print("  1. Access Point / Home WiFi - For WarPie AP and home connection")
    console.print("  2. Capture Interfaces       - For Kismet wardriving (1 or more)")

    # Detect adapters
    console.print("\n[blue]Detecting WiFi interfaces...[/blue]")
    adapters = detect_wifi_interfaces()

    if not adapters:
        console.print("[red]No WiFi interfaces found![/red]")
        sys.exit(1)

    display_adapters(adapters)

    # Step 1: Select AP
    ap = select_ap_interface(adapters)
    console.print(f"[green]✓ AP Interface: {ap.interface} ({ap.driver_name})[/green]")

    # Step 2: Select capture interfaces
    capture_adapters = select_capture_interfaces(adapters, ap)

    # Step 3: Configure each capture adapter
    console.print("\n[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  Step 3: Configure Capture Adapter Bands[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]")
    console.print("\nFor each adapter, select bands and channel configuration.")

    configs = []
    for i, adapter in enumerate(capture_adapters):
        config = configure_adapter(adapter, i)
        configs.append(config)

    # Confirm
    console.print("\n[bold]═══════════════════════════════════════════════════════════════[/bold]")
    console.print("[bold]  Configuration Summary[/bold]")
    console.print("[bold]═══════════════════════════════════════════════════════════════[/bold]")
    console.print(f"\nAP Interface: [cyan]{ap.interface}[/cyan] ({ap.driver_name})")
    console.print(f"Capture Interfaces: [cyan]{len(configs)}[/cyan]")
    for cfg in configs:
        console.print(f"  • {cfg.interface} → {cfg.name}")

    if inquirer.confirm(message="Save this configuration?", default=True).execute():
        save_config(ap, configs)
        return 0
    else:
        console.print("[yellow]Configuration cancelled[/yellow]")
        return 1


if __name__ == "__main__":
    sys.exit(main())

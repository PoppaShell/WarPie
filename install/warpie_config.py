#!/usr/bin/env python3
"""
WarPie WiFi Adapter Configuration
Interactive configuration using InquirerPy for beautiful prompts.
"""

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Check for dependencies
try:
    from InquirerPy import inquirer
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    print("Installing required packages...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "inquirerpy", "rich", "-q"])
    from InquirerPy import inquirer
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

console = Console()

# Custom InquirerPy indicators for square bracket style
INDICATOR_CHECKED = "■"  # Filled block
INDICATOR_UNCHECKED = " "  # Empty
INDICATOR_POINTER = "→"  # Arrow pointer

# Channel constants
CHANNELS_24_ALL = "1,2,3,4,5,6,7,8,9,10,11"
CHANNELS_24_NONOVERLAP = "1,6,11"
CHANNELS_5_ALL = (
    "36,40,44,48,52,56,60,64,100,104,108,112,116,120,124,128,132,136,140,144,149,153,157,161,165"
)
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


@dataclass
class BTLEAdapter:
    """Represents a detected BTLE adapter (TI CC2540)."""

    device_id: str  # e.g., "ticc2540-1-5"
    usb_path: str  # e.g., "1-5" (bus-device)


def detect_btle_adapters() -> list[BTLEAdapter]:
    """Detect TI CC2540 BTLE adapters using Kismet's capture helper.

    Returns a list of detected BTLE adapters. Empty list if none found
    or if kismet_cap_ti_cc_2540 is not installed.
    """
    adapters = []

    try:
        result = subprocess.run(
            ["kismet_cap_ti_cc_2540", "--list"],
            capture_output=True,
            text=True,
            check=False,
        )

        # Parse output like:
        # ticc2540 supported data sources:
        #     ticc2540-1-5 (ticc2540)
        # Note: Output goes to stderr, not stdout
        output = result.stderr if result.stderr else result.stdout
        for line in output.splitlines():
            line = line.strip()
            # Look for lines like "ticc2540-1-5 (ticc2540)"
            if line.startswith("ticc2540-") and "(ticc2540)" in line:
                device_id = line.split()[0]  # e.g., "ticc2540-1-5"
                # Extract USB path from device_id (e.g., "1-5" from "ticc2540-1-5")
                usb_path = device_id.replace("ticc2540-", "")
                adapters.append(BTLEAdapter(device_id=device_id, usb_path=usb_path))

    except FileNotFoundError:
        # kismet_cap_ti_cc_2540 not installed
        pass
    except Exception:
        # Other errors - silently ignore
        pass

    return adapters


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
        except OSError:
            mac = "00:00:00:00:00:00"

        # Get driver
        driver = "unknown"
        driver_path = iface_path / "device" / "driver"
        if driver_path.exists():
            try:
                driver = driver_path.resolve().name
            except OSError:
                driver = "unknown"

        # Detect bands from phy capabilities
        bands = detect_bands(iface)

        adapters.append(WifiAdapter(interface=iface, mac=mac, driver=driver, bands=bands))

    return sorted(adapters, key=lambda a: a.interface)


def detect_bands(interface: str) -> list[str]:
    """Detect supported bands for an interface using iw.

    Uses the reliable method of checking for Band headers in iw phy output.
    Band 1 = 2.4GHz, Band 2 = 5GHz, Band 4 = 6GHz (WiFi 6E)
    """
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
            ["iw", "phy", phy, "info"], check=False, capture_output=True, text=True
        )

        output = result.stdout

        # Check for band headers (most reliable method)
        # This matches the proven bash implementation in install.sh
        if "Band 1:" in output:
            bands.append("2.4GHz")

        if "Band 2:" in output:
            bands.append("5GHz")

        if "Band 4:" in output:
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
            str(i), adapter.interface, adapter.mac, adapter.bands_str, adapter.driver_name
        )

    console.print(table)


def select_ap_interface(adapters: list[WifiAdapter]) -> WifiAdapter:
    """Select the Access Point interface."""
    console.print()
    console.print(
        Panel.fit(
            "[bold white]Step 1 of 3: Select Access Point Interface[/bold white]\n\n"
            "Which interface should be used for the WarPie AP and home WiFi connection?\n"
            "[dim]→ Usually the Raspberry Pi's internal WiFi (look for 'Broadcom')[/dim]\n"
            "[dim]→ This adapter will NOT be used for wardriving[/dim]",
            border_style="bright_cyan",
            title="[bold bright_cyan]SINGLE SELECT[/bold bright_cyan]",
            title_align="left",
        )
    )

    choices = [
        {
            "name": f"[{INDICATOR_UNCHECKED}] {a.interface} - {a.driver_name} [{a.bands_str}]",
            "value": a,
        }
        for a in adapters
    ]

    return inquirer.select(
        message="Select AP interface:",
        choices=choices,
        instruction="↑↓ Navigate | Enter Select",
        pointer=INDICATOR_POINTER,
        qmark="",
        amark="",
    ).execute()


def select_capture_interfaces(
    adapters: list[WifiAdapter], exclude: WifiAdapter
) -> list[WifiAdapter]:
    """Select capture interfaces (multi-select with checkboxes)."""
    console.print()
    console.print(
        Panel.fit(
            "[bold white]Step 2 of 3: Select Capture Interface(s)[/bold white]\n\n"
            "Which interface(s) should be used for Kismet wardriving?\n"
            "[dim]→ Select all external USB adapters[/dim]\n"
            "[dim]→ You can select multiple interfaces[/dim]\n"
            "[dim]→ Use Space to toggle, Enter to confirm[/dim]",
            border_style="bright_magenta",
            title="[bold bright_magenta]MULTI SELECT[/bold bright_magenta]",
            title_align="left",
        )
    )

    available = [a for a in adapters if a.interface != exclude.interface]

    if not available:
        console.print("[red]No interfaces available for capture![/red]")
        sys.exit(1)

    choices = [
        {"name": f"{a.interface} - {a.driver_name} [{a.bands_str}]", "value": a} for a in available
    ]

    selected = inquirer.checkbox(
        message="Select capture interface(s):",
        choices=choices,
        validate=lambda result: len(result) > 0,
        invalid_message="Select at least one interface",
        instruction="Space Toggle | Enter Confirm",
        pointer=INDICATOR_POINTER,
        enabled_symbol=INDICATOR_CHECKED,
        disabled_symbol=INDICATOR_UNCHECKED,
        qmark="",
        amark="",
    ).execute()

    # Show clean summary of selections
    console.print(f"\n[green]✓ Selected {len(selected)} capture interface(s):[/green]")
    for adapter in selected:
        console.print(
            f"  [bright_green]■[/bright_green] {adapter.interface} - {adapter.driver_name}"
        )

    return selected


def select_bands(adapter: WifiAdapter) -> list[str]:
    """Select which bands to capture for an adapter."""
    if len(adapter.bands) == 1:
        # Only one band available, auto-select but inform user
        console.print(
            f"[bright_yellow]   ⚡ Only {adapter.bands[0]} available, auto-selected[/bright_yellow]"
        )
        return adapter.bands.copy()

    # Add helpful descriptions for each band
    band_descriptions = {
        "2.4GHz": "2.4GHz (Better range, more interference)",
        "5GHz": "5GHz (Faster, less interference, shorter range)",
        "6GHz": "6GHz (WiFi 6E, newest, requires compatible hardware)",
    }

    choices = [{"name": band_descriptions.get(band, band), "value": band} for band in adapter.bands]

    return inquirer.checkbox(
        message=f"Select bands for {adapter.interface}:",
        choices=choices,
        default=adapter.bands,  # All selected by default
        validate=lambda result: len(result) > 0,
        invalid_message="Select at least one band",
        instruction="Space Toggle | Enter Confirm | All selected by default",
        pointer=INDICATOR_POINTER,
        enabled_symbol=INDICATOR_CHECKED,
        disabled_symbol=INDICATOR_UNCHECKED,
        qmark="",
        amark="",
    ).execute()


def select_channels(band: str) -> str:
    """Select channel configuration for a band."""
    if band == "2.4GHz":
        choices = [
            {"name": f"[{INDICATOR_UNCHECKED}] All channels (1-11)", "value": CHANNELS_24_ALL},
            {
                "name": f"[{INDICATOR_UNCHECKED}] Non-overlapping (1,6,11) - recommended",
                "value": CHANNELS_24_NONOVERLAP,
            },
            {"name": f"[{INDICATOR_UNCHECKED}] Custom list", "value": "custom"},
        ]
    elif band == "5GHz":
        choices = [
            {"name": f"[{INDICATOR_UNCHECKED}] All channels (36-165)", "value": CHANNELS_5_ALL},
            {"name": f"[{INDICATOR_UNCHECKED}] Custom list", "value": "custom"},
        ]
    else:  # 6GHz
        choices = [
            {
                "name": f"[{INDICATOR_UNCHECKED}] PSC channels (15 channels) - recommended",
                "value": CHANNELS_6_PSC,
            },
            {"name": f"[{INDICATOR_UNCHECKED}] All channels", "value": CHANNELS_6_PSC},
            {"name": f"[{INDICATOR_UNCHECKED}] Custom list", "value": "custom"},
        ]

    result = inquirer.select(
        message=f"{band} channel selection:",
        choices=choices,
        pointer=INDICATOR_POINTER,
        qmark="",
        amark="",
    ).execute()

    if result == "custom":
        return inquirer.text(
            message="Enter comma-separated channel list:",
            validate=lambda x: len(x) > 0,
            qmark="",
            amark="",
        ).execute()

    return result


def generate_adapter_name(index: int, bands: list[str]) -> str:
    """Generate a descriptive name for the adapter."""
    count = len(bands)

    # Single band
    if count == 1:
        band = bands[0]
        band_map = {"6GHz": "6GHz", "5GHz": "5GHz"}
        return f"WiFi_{band_map.get(band, '24GHz')}_{index}"

    # Dual band
    if count == 2:
        if "2.4GHz" in bands and "5GHz" in bands:
            name_suffix = "DualBand"
        elif "5GHz" in bands and "6GHz" in bands:
            name_suffix = "HighBand"
        else:
            name_suffix = "Mixed"
        return f"WiFi_{name_suffix}_{index}"

    # Tri-band or more
    return f"WiFi_TriBand_{index}"


def configure_adapter(adapter: WifiAdapter, index: int, total: int) -> AdapterConfig:
    """Configure bands and channels for a single adapter."""
    console.print()
    console.print(
        Panel.fit(
            f"[bold white]Step 3 of 3: Configure Adapter {index + 1} of {total}[/bold white]\n\n"
            f"[cyan]Interface:[/cyan] {adapter.interface}\n"
            f"[cyan]Device:[/cyan] {adapter.driver_name}\n"
            f"[cyan]Capable bands:[/cyan] {adapter.bands_str}",
            border_style="yellow",
        )
    )

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


def configure_home_wifi() -> dict[str, str] | None:
    """Configure optional home WiFi connectivity."""
    console.print()
    console.print(
        Panel.fit(
            "[bold white]Home WiFi Configuration (Optional)[/bold white]\n\n"
            "Enable intelligent WiFi management:\n"
            "[dim]→ When home WiFi is in range: Connects as client to your home network[/dim]\n"
            "[dim]→ When home WiFi NOT in range: Starts WarPie AP for field access[/dim]\n"
            "[dim]→ Seamless automatic switching - zero manual intervention[/dim]",
            border_style="bright_blue",
        )
    )

    if not inquirer.confirm(
        message="Enable home WiFi connectivity?",
        default=True,
        instruction="Y/n | Press Enter for Yes",
        qmark="",
        amark="",
    ).execute():
        console.print("[yellow]⊘ Home WiFi disabled - WarPie AP will always run[/yellow]")
        return None

    # Get SSID
    ssid = inquirer.text(
        message="Home WiFi SSID:",
        validate=lambda x: len(x.strip()) > 0,
        invalid_message="SSID cannot be empty",
        instruction="Enter your home WiFi network name",
        qmark="",
        amark="",
    ).execute()

    # Get password with masking
    password = inquirer.secret(
        message="Home WiFi Password:",
        validate=lambda x: len(x) >= 8,
        invalid_message="Password must be at least 8 characters",
        instruction="Enter your WiFi password (hidden)",
        qmark="",
        amark="",
    ).execute()

    # Generate PSK hash for secure storage
    console.print("[blue]   Generating secure PSK hash...[/blue]")
    try:
        result = subprocess.run(
            ["wpa_passphrase", ssid, password],
            check=True,
            capture_output=True,
            text=True,
        )
        # Extract PSK hash from wpa_passphrase output
        for line in result.stdout.splitlines():
            if line.strip().startswith("psk=") and not line.strip().startswith("#psk="):
                psk = line.strip().split("=", 1)[1]
                break
        else:
            console.print("[red]Failed to generate PSK hash[/red]")
            return None

        console.print(f"[green]✓ Home WiFi configured: {ssid}[/green]")
        console.print("[dim]   Password stored as secure PSK hash[/dim]")

        return {"ssid": ssid, "psk": psk}

    except subprocess.CalledProcessError:
        console.print("[red]Failed to generate PSK hash (is wpa_passphrase installed?)[/red]")
        return None


def configure_kismet_autostart() -> bool:
    """Configure Kismet auto-start behavior."""
    console.print()
    console.print(
        Panel.fit(
            "[bold white]Kismet Auto-Start Configuration[/bold white]\n\n"
            "Choose your deployment mode:\n\n"
            "[bright_green]■[/bright_green] [bold]Yes - Field Deployment[/bold]\n"
            "   → Kismet starts automatically on boot\n"
            "   → Ready for wardriving immediately\n"
            "   → Ideal for dedicated field use\n\n"
            "[dim]□[/dim] [bold]No - Manual Start[/bold]\n"
            "   → Start Kismet manually from web app\n"
            "   → Better for development/testing\n"
            "   → More control over when scanning starts",
            border_style="bright_green",
        )
    )

    autostart = inquirer.confirm(
        message="Auto-start Kismet on boot?",
        default=True,
        instruction="Y/n | Press Enter for Yes (Field Deployment)",
        qmark="",
        amark="",
    ).execute()

    if autostart:
        console.print("[green]✓ Kismet will auto-start on boot (Field Deployment)[/green]")
    else:
        console.print("[yellow]⊘ Kismet manual start (start from web app)[/yellow]")

    return autostart


def configure_btle(btle_adapters: list[BTLEAdapter]) -> dict[str, str] | None:
    """Configure BTLE capture with TI CC2540 adapter.

    Returns dict with 'enabled' and 'device' keys, or None if no adapters.
    """
    if not btle_adapters:
        return None

    console.print()
    console.print(
        Panel.fit(
            "[bold white]Bluetooth LE Configuration (Optional)[/bold white]\n\n"
            "A TI CC2540 BTLE adapter was detected!\n"
            "[dim]→ Captures Bluetooth Low Energy advertisements[/dim]\n"
            "[dim]→ Detects fitness trackers, beacons, smart devices[/dim]\n"
            "[dim]→ Runs alongside WiFi capture[/dim]",
            border_style="bright_magenta",
        )
    )

    # Show detected adapters
    console.print(f"\n[cyan]Detected BTLE adapter(s):[/cyan]")
    for adapter in btle_adapters:
        console.print(f"  [bright_magenta]■[/bright_magenta] {adapter.device_id} (USB: {adapter.usb_path})")

    if not inquirer.confirm(
        message="Enable BTLE capture?",
        default=True,
        instruction="Y/n | Press Enter for Yes",
        qmark="",
        amark="",
    ).execute():
        console.print("[yellow]⊘ BTLE capture disabled[/yellow]")
        return {"enabled": "false", "device": ""}

    # If multiple adapters, let user choose
    if len(btle_adapters) > 1:
        choices = [
            {"name": f"{a.device_id} (USB: {a.usb_path})", "value": a}
            for a in btle_adapters
        ]
        selected = inquirer.select(
            message="Select BTLE adapter:",
            choices=choices,
            pointer=INDICATOR_POINTER,
            qmark="",
            amark="",
        ).execute()
    else:
        selected = btle_adapters[0]

    console.print(f"[green]✓ BTLE capture enabled: {selected.device_id}[/green]")

    return {"enabled": "true", "device": selected.device_id}


def save_config(
    ap: WifiAdapter,
    configs: list[AdapterConfig],
    home_wifi: dict[str, str] | None = None,
    kismet_autostart: bool = True,
    btle_config: dict[str, str] | None = None,
    output_path: str = "/etc/warpie/adapters.conf",
) -> None:
    """Save configuration to file.

    Uses the detected interface names directly. udev rules will pin these names
    to their MAC addresses for stability across reboots.
    """
    lines = [
        "# WarPie Adapter Configuration",
        "# Generated by warpie_config.py",
        "",
        f'WIFI_AP="{ap.interface}"',
        f'WIFI_AP_MAC="{ap.mac}"',
    ]

    # Add home WiFi configuration
    if home_wifi:
        lines.extend(
            [
                "",
                "# Home WiFi Configuration",
                'HOME_WIFI_ENABLED="true"',
                f'HOME_WIFI_SSID="{home_wifi["ssid"]}"',
                f'HOME_WIFI_PSK="{home_wifi["psk"]}"',
            ]
        )
    else:
        lines.extend(
            [
                "",
                "# Home WiFi Configuration",
                'HOME_WIFI_ENABLED="false"',
                'HOME_WIFI_SSID=""',
                'HOME_WIFI_PSK=""',
            ]
        )

    # Add BTLE configuration
    if btle_config:
        lines.extend(
            [
                "",
                "# BTLE Configuration (TI CC2540)",
                f'BTLE_ENABLED="{btle_config["enabled"]}"',
                f'BTLE_DEVICE="{btle_config["device"]}"',
            ]
        )
    else:
        lines.extend(
            [
                "",
                "# BTLE Configuration (TI CC2540)",
                'BTLE_ENABLED="false"',
                'BTLE_DEVICE=""',
            ]
        )

    # Add Kismet configuration
    lines.extend(
        [
            "",
            "# Kismet Configuration",
            f'KISMET_AUTOSTART="{str(kismet_autostart).lower()}"',
            "",
            f"WIFI_CAPTURE_COUNT={len(configs)}",
            "",
        ]
    )

    for i, cfg in enumerate(configs):
        lines.extend(
            [
                f'ADAPTER_{i}_IFACE="{cfg.interface}"',
                f'ADAPTER_{i}_MAC="{cfg.mac}"',
                f'ADAPTER_{i}_NAME="{cfg.name}"',
                f'ADAPTER_{i}_BANDS="{",".join(cfg.enabled_bands)}"',
                f'ADAPTER_{i}_CHANNELS_24="{cfg.channels_24}"',
                f'ADAPTER_{i}_CHANNELS_5="{cfg.channels_5}"',
                f'ADAPTER_{i}_CHANNELS_6="{cfg.channels_6}"',
                "",
            ]
        )

    # Ensure directory exists
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w") as f:
        f.write("\n".join(lines))

    console.print(f"\n[green]Configuration saved to {output_path}[/green]")


def main():  # noqa: PLR0912, PLR0915
    """Main entry point."""
    console.print(
        "\n[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print("[bold cyan]  WarPie Adapter Configuration[/bold cyan]")
    console.print(
        "[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]"
    )
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

    # Detect BTLE adapters
    console.print("[blue]Detecting BTLE adapters...[/blue]")
    btle_adapters = detect_btle_adapters()
    if btle_adapters:
        console.print(f"[green]✓ Found {len(btle_adapters)} BTLE adapter(s)[/green]")
    else:
        console.print("[dim]  No BTLE adapters detected[/dim]")

    # Step 1: Select AP
    ap = select_ap_interface(adapters)
    console.print(f"[green]✓ AP Interface: {ap.interface} ({ap.driver_name})[/green]")

    # Step 2: Select capture interfaces
    capture_adapters = select_capture_interfaces(adapters, ap)

    # Step 3: Configure each capture adapter
    console.print(
        "\n[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print("[bold cyan]  Configure Capture Adapters[/bold cyan]")
    console.print(
        "[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print("\nFor each adapter, select bands and channel configuration.")

    configs = []
    total_adapters = len(capture_adapters)
    for i, adapter in enumerate(capture_adapters):
        config = configure_adapter(adapter, i, total_adapters)
        configs.append(config)

    # Step 4: Home WiFi configuration
    console.print(
        "\n[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]"
    )
    console.print("[bold cyan]  Network Configuration[/bold cyan]")
    console.print(
        "[bold cyan]═══════════════════════════════════════════════════════════════[/bold cyan]"
    )
    home_wifi = configure_home_wifi()

    # Step 5: Kismet auto-start
    kismet_autostart = configure_kismet_autostart()

    # Step 6: BTLE configuration (if adapters detected)
    btle_config = configure_btle(btle_adapters)

    # Confirm
    console.print()
    console.print(
        Panel.fit(
            "[bold white]Configuration Summary[/bold white]\n\n"
            "Review your configuration before saving:",
            border_style="green",
        )
    )

    # Create detailed summary table
    summary_table = Table(show_header=True, header_style="bold cyan", box=None)
    summary_table.add_column("Setting", style="dim")
    summary_table.add_column("Value", style="white")

    summary_table.add_row("AP Interface", f"{ap.interface} ({ap.driver_name})")
    summary_table.add_row("Capture Adapters", str(len(configs)))
    summary_table.add_row("", "")  # Spacer

    # Home WiFi summary
    if home_wifi:
        summary_table.add_row(
            "[bold]Home WiFi[/bold]", f"[green]Enabled[/green] - {home_wifi['ssid']}"
        )
    else:
        summary_table.add_row("[bold]Home WiFi[/bold]", "[yellow]Disabled[/yellow]")

    # Kismet auto-start summary
    if kismet_autostart:
        summary_table.add_row(
            "[bold]Kismet Auto-Start[/bold]", "[green]Enabled[/green] (Field Deployment)"
        )
    else:
        summary_table.add_row(
            "[bold]Kismet Auto-Start[/bold]", "[yellow]Manual Start[/yellow] (From Web App)"
        )

    # BTLE summary
    if btle_config and btle_config.get("enabled") == "true":
        summary_table.add_row(
            "[bold]BTLE Capture[/bold]", f"[green]Enabled[/green] - {btle_config['device']}"
        )
    elif btle_adapters:
        summary_table.add_row("[bold]BTLE Capture[/bold]", "[yellow]Disabled[/yellow]")
    # Don't show BTLE row if no adapters were detected

    summary_table.add_row("", "")  # Spacer

    for i, cfg in enumerate(configs, 1):
        summary_table.add_row(f"[bold]Adapter {i}[/bold]", "")
        summary_table.add_row("  Interface", cfg.interface)
        summary_table.add_row("  Name", cfg.name)
        summary_table.add_row("  Bands", ", ".join(cfg.enabled_bands))
        if cfg.channels_24:
            summary_table.add_row("  2.4GHz Channels", cfg.channels_24)
        if cfg.channels_5:
            summary_table.add_row("  5GHz Channels", cfg.channels_5)
        if cfg.channels_6:
            summary_table.add_row("  6GHz Channels", cfg.channels_6)
        if i < len(configs):
            summary_table.add_row("", "")  # Spacer between adapters

    console.print(summary_table)
    console.print()

    if inquirer.confirm(
        message="Save this configuration?", default=True, instruction="Y/n"
    ).execute():
        save_config(ap, configs, home_wifi, kismet_autostart, btle_config)
        return 0
    else:
        console.print("[yellow]Configuration cancelled[/yellow]")
        return 1


if __name__ == "__main__":
    sys.exit(main())

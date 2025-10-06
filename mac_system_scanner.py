"""
Mac System Data Scanner — macOS Storage Analyzer
------------------------------------------------
Author: Jonathon Fryman
Purpose:
    Quickly identify which folders on macOS are consuming the most disk space
    (especially within "System Data") and suggest safe cleanup targets.

Features:
    • Scans key system & user directories: /Library, /private, /System, /Users, ~/Library
    • Uses native 'du' command for accurate folder sizes
    • Displays results in a colorized table (via 'rich' library)
    • Suggests cleanup actions for known safe-to-clear folders (Caches, Logs, Updates)
    • Saves a detailed report to the Desktop
    • Works safely with System Integrity Protection (SIP) enabled

Dependencies:
    pip install rich

Usage:
    python3 system_data_scanner_pro.py

Output:
    A colorful terminal summary and a report file saved to:
        ~/Desktop/SystemDataReport_Pro.txt
"""

import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.progress import track

# === CONFIGURATION ===

# Initialize console for styled terminal output
console = Console()

# Define home and output report path
HOME = Path.home()
REPORT_PATH = HOME / "Desktop/SystemDataReport_Pro.txt"

# Directories to check (system-level and user-level)
TARGET_DIRS = [
    "/Library",              # macOS-wide Application Support, Logs, Caches
    "/private",              # Temp files, system logs, Time Machine local snapshots
    "/System",               # macOS system frameworks and updates
    "/Users",                # All user folders (can be huge)
    str(HOME / "Library")    # Current user Library (per-user caches, support, backups)
]

# Minimum size (in GB) to display in the report
THRESHOLD_GB = 1.0


# === CORE FUNCTIONS ===

def get_dir_size(dir_path: str):
    """
    Executes the native 'du' (disk usage) command to get the size of each folder
    inside a given directory, limited to one level deep (-d1).

    Args:
        dir_path (str): Path to scan (must be an existing directory).

    Returns:
        list[str]: Each line from the 'du' output, containing size and folder path.

    Notes:
        - Uses '-x' flag to avoid crossing filesystem boundaries.
        - Uses '-h' for human-readable sizes (e.g., 1.2G, 500M).
        - stderr is silenced to avoid spam from SIP-protected directories.
    """
    try:
        result = subprocess.run(
            ["du", "-hxd1", dir_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # Ignore permission-denied errors
            text=True,
            check=False
        )
        return result.stdout.splitlines()
    except Exception as e:
        return [f"Error scanning {dir_path}: {e}"]


def parse_sizes(lines: list[str]):
    """
    Parses raw 'du' output lines, filtering for folders measured in gigabytes (G).

    Args:
        lines (list[str]): Raw lines from the 'du' command.

    Returns:
        list[tuple[float, str]]: Sorted list of (size_gb, folder_path), descending.
    """
    data = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) == 2:
            size, folder = parts
            if "G" in size:
                try:
                    # Convert "1.5G" -> 1.5
                    value = float(size.replace("G", "").strip())
                    data.append((value, folder))
                except ValueError:
                    pass
    return sorted(data, reverse=True)


def suggest_cleanup(path: str) -> str:
    """
    Returns a short cleanup suggestion based on common folder name patterns.

    Args:
        path (str): Full folder path to analyze.

    Returns:
        str: Suggestion string (or empty string if no advice).
    """
    name = os.path.basename(path)
    if "Cache" in name or "Caches" in name:
        return "🧹 likely safe to delete (cache)"
    if "Log" in name:
        return "🧾 can usually delete old logs"
    if "Update" in name or "Updates" in name:
        return "⚙️ leftover macOS or app updates"
    if "MobileSync" in path:
        return "📱 old iPhone/iPad backups"
    if "DerivedData" in path:
        return "🧠 Xcode build cache (safe to clear)"
    return ""


def main():
    """
    Main entry point for the program.
    - Scans each target directory.
    - Filters results to only those >= THRESHOLD_GB.
    - Displays them in a rich colorized table.
    - Writes a complete text report to the Desktop.
    """
    console.print("[bold cyan]🔍 macOS System Data Scanner Pro[/bold cyan]")
    report = open(REPORT_PATH, "w")
    report.write(f"=== macOS System Data Report — {datetime.now()} ===\n\n")

    # Create the results table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Size (GB)", justify="right")
    table.add_column("Folder Path", justify="left")
    table.add_column("Suggestion", justify="left")

    # Iterate over target directories with progress bar
    for dir_path in track(TARGET_DIRS, description="Scanning directories..."):
        lines = get_dir_size(dir_path)
        data = parse_sizes(lines)
        for size, folder in data:
            if size >= THRESHOLD_GB:
                note = suggest_cleanup(folder)
                color = "red" if size > 10 else "yellow"
                table.add_row(f"[{color}]{size:.1f}[/{color}]", folder, note)
                report.write(f"{size:.2f}G\t{folder}\t{note}\n")

    report.close()
    console.print(table)
    console.print(f"\n✅ Full report saved to: [green]{REPORT_PATH}[/green]\n")

    console.print(
        "💡 [italic]Tip: Empty Trash and reboot after deleting large caches or updates.[/italic]"
    )


# === RUNTIME ENTRY ===
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[red]Cancelled by user.[/red]")
        sys.exit(1)
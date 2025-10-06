"""
mac_system_scanner.py — Deep macOS Storage Analyzer (with Progress Bar)
-----------------------------------------------------------------------
Enhanced version with:
  ✅ Multi-level folder scanning (depth configurable)
  ✅ Largest file detection
  ✅ Leaf-only deduplication (no duplicate parent rows)
  ✅ Rich progress bar + styled output

Run in terminal with this syntax:
    python3 mac_system_scanner.py --depth 3 --top 40 --min-gb 0.5 --leaf-only --files --min-file-gb 1
"""

import argparse
import os
import subprocess
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.progress import track

# === Configuration ===
console = Console()
HOME = Path.home()
DEFAULT_ROOTS = [
    "/Library",
    "/private",
    "/System",
    str(HOME),
    str(HOME / "Library"),
]
REPORT_PATH = HOME / "Desktop/SystemDataReport_Deep.txt"


# === Utility Functions ===
def run(cmd: list[str]) -> str:
    """Execute a shell command and return stdout."""
    return subprocess.run(
        cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False
    ).stdout


def du_list(dir_path: str, depth: int) -> list[tuple[int, str]]:
    """Recursively gather folder sizes up to a given depth using 'du'."""
    out = run(["du", "-kxd" + str(depth), dir_path])
    rows = []
    for line in out.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        try:
            kib = int(parts[0])
        except ValueError:
            continue
        rows.append((kib * 1024, parts[1]))  # bytes
    return rows


def human_gb(bytes_val: int) -> float:
    """Convert bytes to gigabytes."""
    return bytes_val / (1024**3)


def leaf_only(entries: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Keep only leaf-level paths (no duplicate parent rows)."""
    keep = []
    for size, path in sorted(entries, key=lambda x: len(x[1]), reverse=True):
        is_parent = any(kp.startswith(path.rstrip("/") + "/") for _, kp in keep)
        if not is_parent:
            keep.append((size, path))
    return sorted(keep, key=lambda x: x[0], reverse=True)


def find_big_files(root: str, min_gb: float, top: int) -> list[tuple[int, str]]:
    """Find the largest files above a certain threshold."""
    out = run(["find", root, "-type", "f", "-size", f"+{min_gb}G"])
    files = [line for line in out.splitlines() if line.strip()]
    entries = []

    if not files:
        return entries

    chunk = 200
    for i in range(0, len(files), chunk):
        group = files[i:i + chunk]
        cmd = ["stat", "-f", "%z %N"] + group
        for line in run(cmd).splitlines():
            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue
            try:
                size = int(parts[0])
            except ValueError:
                continue
            entries.append((size, parts[1]))

    return sorted(entries, key=lambda x: x[0], reverse=True)[:top]


# === Main ===
def main():
    parser = argparse.ArgumentParser(description="Deep macOS storage analyzer with progress bar.")
    parser.add_argument("--roots", nargs="*", default=DEFAULT_ROOTS, help="Directories to scan.")
    parser.add_argument("--depth", type=int, default=3, help="Folder depth for du (default 3).")
    parser.add_argument("--top", type=int, default=30, help="Top N results per root (default 30).")
    parser.add_argument("--min-gb", type=float, default=0.5, help="Min folder size (GB).")
    parser.add_argument("--leaf-only", action="store_true", help="Show only leaf folders.")
    parser.add_argument("--files", action="store_true", help="Also show largest individual files.")
    parser.add_argument("--min-file-gb", type=float, default=1.0, help="Min file size (GB).")
    parser.add_argument("--report", default=str(REPORT_PATH), help="Report save path.")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"=== macOS Deep Storage Report — {ts} ===",
        f"Roots: {', '.join(args.roots)}",
        f"Depth: {args.depth} | Leaf-only: {args.leaf_only} | MinGB: {args.min_gb} | Top: {args.top}",
    ]
    if args.files:
        lines.append(f"Files: enabled | MinFileGB: {args.min_file_gb}")
    lines.append("")

    # Progress bar for roots
    for root in track(args.roots, description="🔍 Scanning directories..."):
        lines.append(f"\n### Root: {root}")
        pairs = du_list(root, args.depth)
        pairs = [p for p in pairs if human_gb(p[0]) >= args.min_gb]
        if args.leaf_only:
            pairs = leaf_only(pairs)
        pairs = sorted(pairs, key=lambda x: x[0], reverse=True)[:args.top]

        if not pairs:
            lines.append("  (no folders above threshold)")
        else:
            lines.append("  Top folders:")
            for size_bytes, path in pairs:
                lines.append(f"    {human_gb(size_bytes):6.2f}G\t{path}")

        if args.files:
            big_files = find_big_files(root, args.min_file_gb, args.top)
            if big_files:
                lines.append("  Top files:")
                for size_bytes, path in big_files:
                    lines.append(f"    {human_gb(size_bytes):6.2f}G\t{path}")
            else:
                lines.append("  (no files above threshold)")

    report_path.write_text("\n".join(lines))
    console.print(f"\n✅ Deep report saved to: [green]{report_path}[/green]")
    console.print("💡 Tip: add --leaf-only to hide parent rows and --files to show large files.\n")


if __name__ == "__main__":
    main()
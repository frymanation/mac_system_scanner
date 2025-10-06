"""
mac_system_scanner.py — Deep macOS Storage Analyzer (Console Output + Progress Bar)
-----------------------------------------------------------------------
Shows progress while scanning, prints results to console,
and saves a detailed report to your Desktop.
"""

import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.progress import track
from rich.table import Table

console = Console()
HOME = Path.home()
DEFAULT_ROOTS = ["/Library", "/private", "/System", str(HOME), str(HOME / "Library")]
REPORT_PATH = HOME / "Desktop/SystemDataReport_Deep.txt"


def run(cmd):
    """Run a shell command quietly and return stdout."""
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout


def du_list(dir_path, depth):
    """Return [(bytes, path)] using du -kxdN."""
    out = run(["du", "-kxd" + str(depth), dir_path])
    rows = []
    for line in out.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            try:
                kib = int(parts[0])
                rows.append((kib * 1024, parts[1]))
            except ValueError:
                pass
    return rows


def human_gb(bytes_val):
    return bytes_val / (1024**3)


def leaf_only(entries):
    """Remove parent dirs when children are present."""
    keep = []
    for size, path in sorted(entries, key=lambda x: len(x[1]), reverse=True):
        is_parent = any(kp.startswith(path.rstrip("/") + "/") for _, kp in keep)
        if not is_parent:
            keep.append((size, path))
    return sorted(keep, key=lambda x: x[0], reverse=True)


def find_big_files(root, min_gb, top):
    """Find largest files under root."""
    out = run(["find", root, "-type", "f", "-size", f"+{min_gb}G"])
    files = [f for f in out.splitlines() if f.strip()]
    entries = []
    if not files:
        return entries
    chunk = 200
    for i in range(0, len(files), chunk):
        group = files[i : i + chunk]
        cmd = ["stat", "-f", "%z %N"] + group
        for line in run(cmd).splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                try:
                    size = int(parts[0])
                    entries.append((size, parts[1]))
                except ValueError:
                    pass
    return sorted(entries, key=lambda x: x[0], reverse=True)[:top]


def main():
    parser = argparse.ArgumentParser(description="Deep macOS storage analyzer with console output.")
    parser.add_argument("--roots", nargs="*", default=DEFAULT_ROOTS)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--min-gb", type=float, default=0.5)
    parser.add_argument("--leaf-only", action="store_true")
    parser.add_argument("--files", action="store_true")
    parser.add_argument("--min-file-gb", type=float, default=1.0)
    parser.add_argument("--report", default=str(REPORT_PATH))
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

    table = Table(title="macOS Deep Storage Report", header_style="bold magenta")
    table.add_column("Size (GB)", justify="right")
    table.add_column("Path", justify="left")

    for root in track(args.roots, description="🔍 Scanning directories..."):
        pairs = du_list(root, args.depth)
        pairs = [p for p in pairs if human_gb(p[0]) >= args.min_gb]
        if args.leaf_only:
            pairs = leaf_only(pairs)
        pairs = sorted(pairs, key=lambda x: x[0], reverse=True)[:args.top]

        if pairs:
            for size_bytes, path in pairs:
                gb = human_gb(size_bytes)
                color = "red" if gb > 10 else "yellow"
                table.add_row(f"[{color}]{gb:6.2f}[/{color}]", path)
                lines.append(f"{gb:6.2f}G\t{path}")

        if args.files:
            big_files = find_big_files(root, args.min_file_gb, args.top)
            for size_bytes, path in big_files:
                gb = human_gb(size_bytes)
                color = "cyan"
                table.add_row(f"[{color}]{gb:6.2f}[/{color}]", path)
                lines.append(f"{gb:6.2f}G\t{path}")

    report_path.write_text("\n".join(lines))
    console.print(table)
    console.print(f"\n✅ Deep report saved to: [green]{report_path}[/green]")
    console.print("💡 Tip: add --leaf-only to hide parent rows and --files to show large files.\n")


if __name__ == "__main__":
    main()
"""
mac_system_scanner.py — Deep macOS Storage Analyzer (CLI)
---------------------------------------------------------
Thin CLI that:
  • Parses args
  • Calls helpers in storage_utils.py
  • Prints a Rich table + progress bar
  • Writes a Desktop report
  • (Optional) Saves charts via storage_utils if --charts is enabled
"""

import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from rich.console import Console
from rich.progress import track
from rich.table import Table

from storage_utils import (
    du_list,
    leaf_only,
    find_big_files,
    sample_files_for_types,
    human_gb,
    accumulate_root_totals,
    filetype_totals,
    save_bar_chart,
    save_pie_chart,
)

console = Console()
HOME = Path.home()
DEFAULT_ROOTS = ["/Library", "/private", "/System", str(HOME), str(HOME / "Library")]
REPORT_PATH = HOME / "Desktop/SystemDataReport_Deep.txt"


def main():
    ap = argparse.ArgumentParser(description="Deep macOS storage analyzer (uses storage_utils).")
    ap.add_argument("--roots", nargs="*", default=DEFAULT_ROOTS, help="Directories to scan.")
    ap.add_argument("--depth", type=int, default=3, help="Folder depth for 'du' (default 3).")
    ap.add_argument("--top", type=int, default=30, help="Top N results per root (default 30).")
    ap.add_argument("--min-gb", type=float, default=0.5, help="Min folder size (GB) to include.")
    ap.add_argument("--leaf-only", action="store_true", help="Show only leaf-level folders.")
    ap.add_argument("--files", action="store_true", help="Also show largest individual files.")
    ap.add_argument("--min-file-gb", type=float, default=1.0, help="Min file size (GB) for 'Top files'.")
    ap.add_argument("--charts", action="store_true", help="Generate PNG charts on Desktop.")
    ap.add_argument("--filetype-min-mb", type=int, default=50, help="Only count files >= this MB for file-type chart.")
    ap.add_argument("--report", default=str(REPORT_PATH), help="Report save path.")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # Console table
    table = Table(title="macOS Deep Storage Report", header_style="bold magenta")
    table.add_column("Size (GB)", justify="right")
    table.add_column("Path", justify="left")
    if args.files:
        table.add_column("Type", justify="left")

    lines = [
        f"=== macOS Deep Storage Report — {ts} ===",
        f"Roots: {', '.join(args.roots)}",
        f"Depth: {args.depth} | Leaf-only: {args.leaf_only} | MinGB: {args.min_gb} | Top: {args.top}",
    ]
    if args.files:
        lines.append(f"Files: enabled | MinFileGB: {args.min_file_gb}")
    if args.charts:
        lines.append(f"Charts: enabled | FileTypeMinMB: {args.filetype_min_mb}")
    lines.append("")

    # Holders for charts
    per_root_pairs = defaultdict(list)   # root -> [(bytes, path)]
    all_top_folders = []                # [(bytes, path)]
    all_top_files = []                  # [(bytes, path)]
    sampled_for_types = []              # [(bytes, path)] across roots

    # Scan
    for root in track(args.roots, description="🔍 Scanning directories..."):
        lines.append(f"\n### Root: {root}")
        pairs = du_list(root, args.depth)
        per_root_pairs[root].extend(pairs)  # keep raw for root totals

        # filter + de-dup + limit
        pairs = [p for p in pairs if human_gb(p[0]) >= args.min_gb]
        if args.leaf_only:
            pairs = leaf_only(pairs)
        pairs = sorted(pairs, key=lambda x: x[0], reverse=True)[:args.top]

        if not pairs:
            lines.append("  (no folders above threshold)")
        else:
            lines.append("  Top folders:")
            for size_bytes, path in pairs:
                gb = human_gb(size_bytes)
                all_top_folders.append((size_bytes, path))
                color = "red" if gb > 10 else "yellow"
                if args.files:
                    table.add_row(f"[{color}]{gb:6.2f}[/{color}]", path, "folder")
                else:
                    table.add_row(f"[{color}]{gb:6.2f}[/{color}]", path)
                lines.append(f"{gb:6.2f}G\t{path}")

        if args.files:
            big_files = find_big_files(root, args.min_file_gb, args.top)
            if big_files:
                lines.append("  Top files:")
                for size_bytes, path in big_files:
                    gb = human_gb(size_bytes)
                    all_top_files.append((size_bytes, path))
                    table.add_row(f"[cyan]{gb:6.2f}[/cyan]", path, "file")
                    lines.append(f"{gb:6.2f}G\t{path}")
            else:
                lines.append("  (no files above threshold)")

        if args.charts:
            sampled_for_types.extend(sample_files_for_types(root, args.filetype_min_mb))

    # Write report + print table
    report_path.write_text("\n".join(lines))
    console.print(table)
    console.print(f"\n✅ Deep report saved to: [green]{report_path}[/green]")

    # Charts (optional)
    if args.charts:
        desktop = HOME / "Desktop"
        desktop.mkdir(exist_ok=True)

        # 1) Top folders bar
        if all_top_folders:
            top_folders_sorted = sorted(all_top_folders, key=lambda x: x[0], reverse=True)[:30]
            labels = [p for _, p in top_folders_sorted]
            values = [round(human_gb(s), 2) for s, _ in top_folders_sorted]
            save_bar_chart("Top Folders by Size (GB)", labels, values, desktop / "Storage_TopFolders.png", xlabel="GB")

        # 2) Top files bar
        if args.files and all_top_files:
            top_files_sorted = sorted(all_top_files, key=lambda x: x[0], reverse=True)[:30]
            labels = [p for _, p in top_files_sorted]
            values = [round(human_gb(s), 2) for s, _ in top_files_sorted]
            save_bar_chart("Top Files by Size (GB)", labels, values, desktop / "Storage_TopFiles.png", xlabel="GB")

        # 3) Directory share by root (pie)
        root_totals = accumulate_root_totals(per_root_pairs)
        if root_totals:
            labels = list(root_totals.keys())
            values = [human_gb(v) for v in root_totals.values()]
            save_pie_chart("Storage by Root Directory (Approx.)", labels, values, desktop / "Storage_ByRoot.png")

        # 4) File-type distribution (pie)
        if sampled_for_types:
            ext_totals = filetype_totals(sampled_for_types)
            labels = list(ext_totals.keys())
            values = [human_gb(v) for v in ext_totals.values()]
            save_pie_chart("Storage by File Type (extensions)", labels, values, desktop / "Storage_ByFileType.png")

        console.print("🖼  Charts saved to Desktop:")
        console.print("   - Storage_TopFolders.png")
        if args.files:
            console.print("   - Storage_TopFiles.png")
        console.print("   - Storage_ByRoot.png")
        console.print("   - Storage_ByFileType.png")

    console.print("💡 Tip: Use --leaf-only to avoid parent/child duplicates; tune --depth and thresholds for speed.\n")


if __name__ == "__main__":
    main()
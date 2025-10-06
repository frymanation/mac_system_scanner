import os
import subprocess
from pathlib import Path
from datetime import datetime

# Directories to scan
TARGET_DIRS = ["/", "/System", "/Library", "/private", str(Path.home() / "Library")]

# Output file
today = datetime.today().strftime("%Y-%m-%d")
report_path = Path.home() / f"Desktop/Mac_System_Data_Report_{today}.txt"
threshold_gb = 1.0 # minimum size to include in report

def get_dir_size(dir_path):
    """Use du for fast, accurate folder size calculation."""
    try:
        result = subprocess.run(
            ["du", "-hxd1", dir_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False
        )
        return result.stdout.splitlines()
    except Exception as e:
        return [f"Error scanning {dir_path}: {e}"]

def parse_and_filter(lines, min_gb):
    """Filter out entries below threshold."""
    filtered = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) == 2:
            size, folder = parts
            if "G" in size:
                try:
                    num = float(size.replace("G", "").strip())
                    if num >= min_gb:
                        # print(f"Size: {num}\tFolder: {folder}")
                        filtered.append((num, folder))
                except ValueError:
                    pass
    return sorted(filtered, reverse=True)

def main():
    with open(report_path, "w") as f:
        f.write(f"=== macOS System Data Report ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===\n")
        for d in TARGET_DIRS:
            f.write(f"\n\n### {d} ###\n")
            lines = get_dir_size(d)
            filtered = parse_and_filter(lines, threshold_gb)
            for size, folder in filtered:
                print(f"{size:.2f}G\t{folder}\n")
                f.write(f"{size:.2f}G\t{folder}\n")
    print(f"\n✅ Report saved to {report_path}")

if __name__ == "__main__":
    main()
"""
storage_utils.py — helpers for macOS storage scanning & charts

Responsibilities:
  • Shell wrappers: du/find/stat
  • Directory size collection (depth-limited), leaf-only filtering
  • Largest-file discovery
  • Simple unit conversion
  • Optional matplotlib charts (kept generic and single-plot per chart)

Notes:
  - Uses BSD/macOS flags (e.g., stat -f "%z %N", find -size +1G).
  - We intentionally do NOT set explicit matplotlib colors and we plot one chart per figure.
"""

from __future__ import annotations
import subprocess
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Tuple, Dict
import matplotlib as plt

# Matplotlib is optional; utils guard their usage.
try:
    import matplotlib.pyplot as plt  # noqa: F401
except Exception:
    plt = None  # type: ignore


# ---------- Shell helpers ----------

def run(cmd: list[str]) -> str:
    """Run a shell command and return stdout; silence stderr to skip SIP noise."""
    return subprocess.run(
        cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False
    ).stdout


# ---------- Core scan helpers ----------

def du_list(dir_path: str, depth: int) -> List[Tuple[int, str]]:
    """
    Return [(size_bytes, path)] up to 'depth' using 'du -kxdN'.
    -k  : sizes in KiB (easy to convert to bytes)
    -x  : stay on the same filesystem
    -dN : recurse N levels deep
    """
    out = run(["du", "-kxd" + str(depth), dir_path])
    rows: List[Tuple[int, str]] = []
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


def leaf_only(entries: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    """
    Keep only 'leaf' paths: if a parent and a child are present, drop the parent.
    Avoids duplicate-looking rows where parent size includes the child’s size.
    """
    keep: List[Tuple[int, str]] = []
    for size, path in sorted(entries, key=lambda x: len(x[1]), reverse=True):
        is_parent = any(kp.startswith(path.rstrip("/") + "/") for _, kp in keep)
        if not is_parent:
            keep.append((size, path))
    return sorted(keep, key=lambda x: x[0], reverse=True)


def find_big_files(root: str, min_gb: float, top: int) -> List[Tuple[int, str]]:
    """
    Find up to 'top' largest files under 'root' with size >= min_gb.
    Uses:
      - find <root> -type f -size +{min_gb}G
      - stat -f "%z %N" <files...>
    Returns list of (size_bytes, path), sorted desc by size.
    """
    out = run(["find", root, "-type", "f", "-size", f"+{min_gb}G"])
    files = [f for f in out.splitlines() if f.strip()]
    entries: List[Tuple[int, str]] = []
    if not files:
        return entries

    # batch to avoid excessively long arg lists
    chunk = 200
    for i in range(0, len(files), chunk):
        group = files[i:i+chunk]
        cmd = ["stat", "-f", "%z %N"] + group  # %z size (bytes), %N filename
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


def sample_files_for_types(root: str, min_mb: int) -> List[Tuple[int, str]]:
    """
    Sample files >= min_mb megabytes under 'root' for file-type aggregation.
    Returns list of (size_bytes, path).
    """
    out = run(["find", root, "-type", "f", "-size", f"+{min_mb}M"])
    files = [f for f in out.splitlines() if f.strip()]
    entries: List[Tuple[int, str]] = []
    if not files:
        return entries

    chunk = 200
    for i in range(0, len(files), chunk):
        group = files[i:i+chunk]
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
    return entries


# ---------- Utilities ----------

def human_gb(bytes_val: int) -> float:
    """Convert bytes → gigabytes (GiB)."""
    return bytes_val / (1024 ** 3)


def accumulate_root_totals(per_root_pairs: Dict[str, list[tuple[int, str]]]) -> Dict[str, int]:
    """
    Given a mapping {root: [(size_bytes, path), ...]} compute approximate totals per root.
    """
    totals: Dict[str, int] = defaultdict(int)
    for root, pairs in per_root_pairs.items():
        totals[root] = sum(size for size, _ in pairs)
    return totals


def filetype_totals(sampled_files: list[tuple[int, str]]) -> Counter:
    """
    Aggregate sampled files by extension to build a size-by-type distribution.
    """
    c: Counter = Counter()
    for size, p in sampled_files:
        ext = Path(p).suffix.lower()
        if not ext:
            ext = "(no-ext)"
        c[ext] += size
    return c


# ---------- Chart helpers (optional) ----------

def save_bar_chart(title: str, labels, values, out_path: Path, xlabel: str = "GB", ylabel: str = "") -> None:
    """Save a simple horizontal bar chart (one plot per figure)."""
    try:
        import matplotlib.pyplot as plt  # local import avoids global state/scoping issues
    except Exception:
        return  # matplotlib not installed or unusable; silently skip

    plt.figure()
    short = [l if len(l) <= 60 else ("…" + l[-57:]) for l in labels]
    y = list(range(len(values)))
    plt.barh(y, values)
    plt.yticks(y, short)
    plt.xlabel(xlabel)
    if ylabel:
        plt.ylabel(ylabel)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def save_pie_chart(title: str, labels, values, out_path: Path) -> None:
    """Save a simple pie chart (groups beyond ~10 slices into 'Other')."""
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    total = sum(values) if values else 0
    if total <= 0:
        return

    pairs = sorted(zip(labels, values), key=lambda x: x[1], reverse=True)
    top, other = [], 0.0
    for i, (lab, val) in enumerate(pairs):
        if i < 10:
            top.append((lab, val))
        else:
            other += val
    if other > 0:
        top.append(("Other", other))

    labels2 = [p[0] for p in top]
    values2 = [p[1] for p in top]

    plt.figure()
    plt.pie(values2, labels=labels2, autopct=lambda p: f"{p:.1f}%")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
"""
gui_mac_system_scanner.py — macOS Storage Scanner GUI
Adds:
  • Real progress % with ETA (per root & per-phase)
  • Double-click to open selected path in Finder
  • Right-click context menu: Reveal in Finder, Copy Path
Defaults match your usual CLI run; Advanced is collapsible.

Requires: storage_utils.py in same folder.
"""

import threading
import time
import subprocess
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from storage_utils import (
    du_list, leaf_only, find_big_files, sample_files_for_types,
    human_gb, accumulate_root_totals, filetype_totals,
    save_bar_chart, save_pie_chart
)

HOME = Path.home()
DEFAULT_ROOTS = ["/Library", "/private", "/System", str(HOME), str(HOME / "Library")]
REPORT_PATH = HOME / "Desktop/SystemDataReport_Deep.txt"

# Default params (your usual run)
DEF_DEPTH = 3
DEF_TOP = 40
DEF_MIN_GB = 0.5
DEF_LEAF_ONLY = True
DEF_FILES = True
DEF_MIN_FILE_GB = 1.0
DEF_CHARTS = False
DEF_FILETYPE_MIN_MB = 50


class ScannerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("macOS Storage Scanner")
        self.geometry("980x660")
        self.minsize(900, 560)

        # ===== Header + Quick Scan =====
        hdr = ttk.Frame(self, padding=(10, 10, 10, 4))
        hdr.pack(fill="x")
        ttk.Label(hdr, text="macOS Storage Scanner", font=("SF Pro", 16, "bold")).pack(side="left")
        self.run_btn = ttk.Button(hdr, text="Run Quick Scan", command=self.on_run, style="Accent.TButton")
        self.run_btn.pack(side="right")

        # Enter key runs scan
        self.bind("<Return>", lambda e: self.on_run())

        # ===== Minimal essentials (defaults prefilled) =====
        essentials = ttk.Frame(self, padding=(10, 4, 10, 6))
        essentials.pack(fill="x")

        ttk.Label(essentials, text="Roots (comma-separated):").grid(row=0, column=0, sticky="w")
        self.roots_var = tk.StringVar(value=",".join(DEFAULT_ROOTS))
        ttk.Entry(essentials, textvariable=self.roots_var, width=90).grid(row=0, column=1, sticky="we", padx=(8, 0))
        ttk.Button(essentials, text="Add…", command=self.add_root).grid(row=0, column=2, padx=(8, 0))

        # Progress row (now: real % + ETA)
        runfrm = ttk.Frame(self, padding=(10, 0, 10, 8))
        runfrm.pack(fill="x")
        self.progress = ttk.Progressbar(runfrm, mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)
        self.progress_label = ttk.Label(runfrm, text="0% • ETA —:—")
        self.progress_label.pack(side="left", padx=8)

        # ===== Results table =====
        columns = ("size_gb", "path", "kind")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=20)
        self.tree.heading("size_gb", text="Size (GB)", command=lambda: self.sort_by("size_gb", num=True))
        self.tree.heading("path", text="Path", command=lambda: self.sort_by("path"))
        self.tree.heading("kind", text="Type", command=lambda: self.sort_by("kind"))
        self.tree.column("size_gb", width=110, anchor="e")
        self.tree.column("path", width=720, anchor="w")
        self.tree.column("kind", width=90, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)

        # Open-in-Finder on double-click
        self.tree.bind("<Double-1>", self.on_open_selected)
        # Context menu (right-click or ctrl-click)
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Reveal in Finder", command=self.on_open_selected)
        self.menu.add_command(label="Copy Path", command=self.on_copy_path)
        self.tree.bind("<Button-2>", self.show_context_menu)   # middle-click
        self.tree.bind("<Button-3>", self.show_context_menu)   # right-click
        self.tree.bind("<Control-Button-1>", self.show_context_menu)  # ctrl-click

        # Status
        self.status = ttk.Label(self, text="Ready (defaults preloaded). Press Enter or 'Run Quick Scan'.", anchor="w")
        self.status.pack(fill="x", padx=10, pady=(0, 8))

        # ===== Advanced (collapsed by default) =====
        self.adv_visible = False
        advbar = ttk.Frame(self, padding=(10, 0, 10, 10))
        advbar.pack(fill="x")
        self.adv_btn = ttk.Button(advbar, text="Show Advanced ▸", command=self.toggle_advanced)
        self.adv_btn.pack(side="left")

        self.adv = ttk.Frame(self, padding=(10, 0, 10, 10))
        r = 0
        ttk.Label(self.adv, text="Depth:").grid(row=r, column=0, sticky="w")
        self.depth_var = tk.IntVar(value=DEF_DEPTH)
        ttk.Spinbox(self.adv, from_=1, to=10, textvariable=self.depth_var, width=6).grid(row=r, column=1, sticky="w", padx=(8, 16))

        ttk.Label(self.adv, text="Top N:").grid(row=r, column=2, sticky="w")
        self.top_var = tk.IntVar(value=DEF_TOP)
        ttk.Spinbox(self.adv, from_=5, to=200, textvariable=self.top_var, width=6).grid(row=r, column=3, sticky="w", padx=(8, 16))

        ttk.Label(self.adv, text="Min Folder (GB):").grid(row=r, column=4, sticky="w")
        self.min_gb_var = tk.DoubleVar(value=DEF_MIN_GB)
        ttk.Spinbox(self.adv, from_=0.1, to=1000.0, increment=0.1, textvariable=self.min_gb_var, width=8).grid(row=r, column=5, sticky="w", padx=(8, 16))

        r += 1
        self.leaf_only_var = tk.BooleanVar(value=DEF_LEAF_ONLY)
        self.files_var = tk.BooleanVar(value=DEF_FILES)
        self.charts_var = tk.BooleanVar(value=DEF_CHARTS)
        ttk.Checkbutton(self.adv, text="Leaf-only", variable=self.leaf_only_var).grid(row=r, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(self.adv, text="Include files", variable=self.files_var).grid(row=r, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(self.adv, text="Charts (PNG to Desktop)", variable=self.charts_var).grid(row=r, column=2, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Label(self.adv, text="Min File (GB):").grid(row=r, column=4, sticky="e", pady=(8, 0))
        self.min_file_gb_var = tk.DoubleVar(value=DEF_MIN_FILE_GB)
        ttk.Spinbox(self.adv, from_=0.1, to=200.0, increment=0.1, textvariable=self.min_file_gb_var, width=8).grid(row=r, column=5, sticky="w", padx=(8, 16), pady=(8, 0))

        ttk.Label(self.adv, text="FileType Min (MB):").grid(row=r, column=6, sticky="w", pady=(8, 0))
        self.filetype_min_mb_var = tk.IntVar(value=DEF_FILETYPE_MIN_MB)
        ttk.Spinbox(self.adv, from_=1, to=5000, textvariable=self.filetype_min_mb_var, width=8).grid(row=r, column=7, sticky="w", padx=(8, 0), pady=(8, 0))

        # Thread + progress accounting
        self._scan_thread = None
        self._start_time = None
        self._total_steps = 0
        self._done_steps = 0

        # mac-ish look
        try:
            s = ttk.Style()
            s.theme_use("clam")
            s.configure("Accent.TButton", font=("SF Pro", 12, "bold"))
        except Exception:
            pass

    # ---------- Context menu / open ----------
    def show_context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            try:
                self.menu.tk_popup(event.x_root, event.y_root)  # show menu
            finally:
                self.menu.grab_release()

    def _get_selected_path(self):
        sel = self.tree.selection()
        if not sel:
            return None
        vals = self.tree.item(sel[0], "values")
        # values: (size_gb, path, kind)
        if len(vals) >= 2:
            return vals[1]
        return None

    def on_open_selected(self, event=None):
        path = self._get_selected_path()
        if not path:
            return
        try:
            # 'open' reveals file or folder in Finder (for files: opens; for dirs: opens)
            subprocess.run(["open", path], check=False)
        except Exception as e:
            messagebox.showerror("Open in Finder", f"Could not open:\n{path}\n\n{e}")

    def on_copy_path(self):
        path = self._get_selected_path()
        if not path:
            return
        self.clipboard_clear()
        self.clipboard_append(path)
        self.update()
        self.status.configure(text=f"Copied to clipboard: {path}")

    # ---------- UI helpers ----------
    def toggle_advanced(self):
        if self.adv_visible:
            self.adv.pack_forget()
            self.adv_btn.configure(text="Show Advanced ▸")
            self.adv_visible = False
        else:
            self.adv.pack(fill="x")
            self.adv_btn.configure(text="Hide Advanced ▾")
            self.adv_visible = True

    def add_root(self):
        sel = filedialog.askdirectory(title="Select root folder to scan")
        if sel:
            s = self.roots_var.get().strip()
            parts = [p.strip() for p in s.split(",") if p.strip()] if s else []
            if sel not in parts:
                parts.append(sel)
            self.roots_var.set(",".join(parts))

    def set_busy(self, busy=True):
        self.run_btn.configure(state="disabled" if busy else "normal")
        self.config(cursor="watch" if busy else "")
        self.update_idletasks()

    def sort_by(self, col, num=False):
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        if num:
            items.sort(key=lambda x: float(x[0]))
        else:
            items.sort(key=lambda x: x[0].lower())
        if hasattr(self, "_last_sort") and self._last_sort == col:
            items.reverse()
            self._last_sort = None
        else:
            self._last_sort = col
        for idx, (_, iid) in enumerate(items):
            self.tree.move(iid, "", idx)

    # ---------- Progress helpers ----------
    def _progress_reset(self, total_steps):
        self._total_steps = max(1, int(total_steps))
        self._done_steps = 0
        self._start_time = time.time()
        self._update_progress_label()

    def _progress_step(self, steps=1):
        self._done_steps += steps
        if self._done_steps > self._total_steps:
            self._done_steps = self._total_steps
        pct = int((self._done_steps / self._total_steps) * 100)
        self.after(0, lambda: self.progress.configure(maximum=100, value=pct))
        self._update_progress_label()

    def _update_progress_label(self):
        # ETA based on average pace so far
        now = time.time()
        elapsed = max(0.001, now - (self._start_time or now))
        ratio = self._done_steps / max(1, self._total_steps)
        if ratio > 0:
            remaining = elapsed * (1 - ratio) / ratio
        else:
            remaining = 0
        eta_str = self._fmt_seconds(remaining)
        pct = int((self._done_steps / max(1, self._total_steps)) * 100)
        self.after(0, lambda: self.progress_label.configure(text=f"{pct}% • ETA {eta_str}"))

    @staticmethod
    def _fmt_seconds(s):
        s = int(s)
        h, r = divmod(s, 3600)
        m, r = divmod(r, 60)
        return f"{h:d}:{m:02d}:{r:02d}" if h else f"{m:d}:{r:02d}"

    # ---------- Scan orchestration ----------
    def on_run(self):
        if self._scan_thread and self._scan_thread.is_alive():
            return
        try:
            roots = [p.strip() for p in self.roots_var.get().split(",") if p.strip()]
            if not roots:
                messagebox.showerror("Error", "Please specify at least one root directory.")
                return
            depth = int(getattr(self, "depth_var", tk.IntVar(value=DEF_DEPTH)).get())
            min_gb = float(getattr(self, "min_gb_var", tk.DoubleVar(value=DEF_MIN_GB)).get())
            topn = int(getattr(self, "top_var", tk.IntVar(value=DEF_TOP)).get())
            leaf = bool(getattr(self, "leaf_only_var", tk.BooleanVar(value=DEF_LEAF_ONLY)).get())
            include_files = bool(getattr(self, "files_var", tk.BooleanVar(value=DEF_FILES)).get())
            charts = bool(getattr(self, "charts_var", tk.BooleanVar(value=DEF_CHARTS)).get())
            min_file_gb = float(getattr(self, "min_file_gb_var", tk.DoubleVar(value=DEF_MIN_FILE_GB)).get())
            filetype_min_mb = int(getattr(self, "filetype_min_mb_var", tk.IntVar(value=DEF_FILETYPE_MIN_MB)).get())
        except Exception as e:
            messagebox.showerror("Error", f"Invalid settings: {e}")
            return

        self.tree.delete(*self.tree.get_children())
        self.status.configure(text="Scanning…")
        self.set_busy(True)

        # Progress planning:
        #   per root we have phases:
        #     1) du folders
        #     2) top files (optional)
        #     3) file-type sampling (optional, only if charts)
        phases_per_root = 1 + (1 if include_files else 0) + (1 if charts else 0)
        total_steps = len(roots) * phases_per_root
        self._progress_reset(total_steps)

        args = (roots, depth, min_gb, topn, leaf, include_files, charts, min_file_gb, filetype_min_mb)
        self._scan_thread = threading.Thread(target=self._run_scan, args=args, daemon=True)
        self._scan_thread.start()
        self.after(200, self._poll_thread)

    def _poll_thread(self):
        if self._scan_thread and self._scan_thread.is_alive():
            self.after(250, self._poll_thread)
        else:
            self.set_busy(False)

    def _run_scan(self, roots, depth, min_gb, topn, leaf, include_files, charts, min_file_gb, filetype_min_mb):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        report_path = REPORT_PATH
        lines = [
            f"=== macOS Deep Storage Report — {ts} ===",
            f"Roots: {', '.join(roots)}",
            f"Depth: {depth} | Leaf-only: {leaf} | MinGB: {min_gb} | Top: {topn}",
            f"Files: {'enabled' if include_files else 'disabled'} | MinFileGB: {min_file_gb}",
            f"Charts: {'enabled' if charts else 'disabled'} | FileTypeMinMB: {filetype_min_mb}",
            ""
        ]

        per_root_pairs = {}
        all_top_folders = []
        all_top_files = []
        sampled_for_types = []

        try:
            for root in roots:
                # === Phase 1: directories (du) ===
                lines.append(f"\n### Root: {root}")
                pairs = du_list(root, depth)
                per_root_pairs[root] = pairs[:]

                # filter + leaf-only + top
                pairs = [p for p in pairs if human_gb(p[0]) >= min_gb]
                if leaf:
                    pairs = leaf_only(pairs)
                pairs = sorted(pairs, key=lambda x: x[0], reverse=True)[:topn]

                if not pairs:
                    lines.append("  (no folders above threshold)")
                else:
                    lines.append("  Top folders:")
                    for size_bytes, path in pairs:
                        gb = human_gb(size_bytes)
                        all_top_folders.append((size_bytes, path))
                        lines.append(f"{gb:6.2f}G\t{path}")
                        self.tree_insert_safe(f"{gb:6.2f}", path, "folder")

                self._progress_step(1)  # done phase

                # === Phase 2: files (optional) ===
                if include_files:
                    big_files = find_big_files(root, min_file_gb, topn)
                    if big_files:
                        lines.append("  Top files:")
                        for size_bytes, path in big_files:
                            gb = human_gb(size_bytes)
                            all_top_files.append((size_bytes, path))
                            lines.append(f"{gb:6.2f}G\t{path}")
                            self.tree_insert_safe(f"{gb:6.2f}", path, "file")
                    else:
                        lines.append("  (no files above threshold)")
                    self._progress_step(1)

                # === Phase 3: sampling for charts (optional) ===
                if charts:
                    sampled_for_types.extend(sample_files_for_types(root, filetype_min_mb))
                    self._progress_step(1)

            # write report
            report_path.write_text("\n".join(lines))

            # charts
            if charts:
                desktop = HOME / "Desktop"
                desktop.mkdir(exist_ok=True)

                if all_top_folders:
                    top_folders_sorted = sorted(all_top_folders, key=lambda x: x[0], reverse=True)[:30]
                    labels = [p for _, p in top_folders_sorted]
                    values = [round(human_gb(s), 2) for s, _ in top_folders_sorted]
                    save_bar_chart("Top Folders by Size (GB)", labels, values, desktop / "Storage_TopFolders.png")

                if include_files and all_top_files:
                    top_files_sorted = sorted(all_top_files, key=lambda x: x[0], reverse=True)[:30]
                    labels = [p for _, p in top_files_sorted]
                    values = [round(human_gb(s), 2) for s, _ in top_files_sorted]
                    save_bar_chart("Top Files by Size (GB)", labels, values, desktop / "Storage_TopFiles.png")

                root_totals = accumulate_root_totals(per_root_pairs)
                if root_totals:
                    labels = list(root_totals.keys())
                    values = [human_gb(v) for v in root_totals.values()]
                    save_pie_chart("Storage by Root Directory (Approx.)", labels, values, desktop / "Storage_ByRoot.png")

                if sampled_for_types:
                    ext_tot = filetype_totals(sampled_for_types)
                    labels = list(ext_tot.keys())
                    values = [human_gb(v) for v in ext_tot.values()]
                    save_pie_chart("Storage by File Type (extensions)", labels, values, desktop / "Storage_ByFileType.png")

            self.set_status_safe(f"Done. Report saved to: {REPORT_PATH}")
            # finalize progress
            self._progress_step(0)  # refresh label one last time
        except Exception as e:
            self.set_status_safe(f"Error: {e}")
            messagebox.showerror("Error", str(e))

    # thread-safe UI updates
    def tree_insert_safe(self, size_gb, path, kind):
        self.after(0, lambda: self.tree.insert("", "end", values=(size_gb, path, kind)))

    def set_status_safe(self, text):
        self.after(0, lambda: self.status.configure(text=text))


if __name__ == "__main__":
    try:
        from tkinter import ttk
        sty = ttk.Style()
        sty.theme_use("clam")
        sty.configure("Accent.TButton", font=("SF Pro", 12, "bold"))
    except Exception:
        pass
    app = ScannerGUI()
    app.mainloop()
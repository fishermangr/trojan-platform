#!/usr/bin/env python3
"""
Power Trace Explorer — Interactive GUI for AES side-channel analysis data.

Features:
  - Load .mat result files from any experiment directory
  - Pan, zoom, box-select, crosshair on power traces
  - Per-trace checkboxes to show/hide individual traces
  - Select All / Deselect All / Invert selection
  - Click a trace in the list to highlight it and view PT/CT details
  - Mean overlay toggle
  - Color-coded match status (green = OK, red = MISMATCH)
  - Trace statistics panel
  - Export visible traces to new .mat file

Usage:
  python3 explore_traces.py
  python3 explore_traces.py --file experiment1/aes_encrypt_20260320_150833.mat
"""

import sys
import os
import argparse
import numpy as np

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QSplitter, QListWidget, QListWidgetItem, QPushButton, QLabel,
        QFileDialog, QGroupBox, QCheckBox, QStatusBar, QToolBar,
        QAction, QTextEdit, QFrame, QSlider, QSpinBox, QComboBox,
        QAbstractItemView, QMessageBox
    )
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QColor, QFont, QIcon
except ImportError:
    print("ERROR: PyQt5 not installed. Install with: pip install PyQt5")
    sys.exit(1)

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
except ImportError:
    print("ERROR: matplotlib not installed. Install with: pip install matplotlib")
    sys.exit(1)

try:
    import scipy.io as sio
except ImportError:
    print("ERROR: scipy not installed. Install with: pip install scipy")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Color palette for traces (distinguishable colors)
# ---------------------------------------------------------------------------
TRACE_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
    '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
    '#c49c94', '#f7b6d2', '#c7c7c7', '#dbdb8d', '#9edae5',
]

HIGHLIGHT_COLOR = '#ff0000'
MEAN_COLOR = '#000000'


class TraceExplorer(QMainWindow):
    """Main window for the power trace explorer."""

    def __init__(self, mat_file=None):
        super().__init__()
        self.setWindowTitle("Power Trace Explorer — AES SCA")
        self.setMinimumSize(1200, 700)

        # Data
        self.traces = None
        self.plaintexts = None
        self.ciphertexts_hw = None
        self.ciphertexts_sw = None
        self.key = None
        self.metadata = {}
        self.num_traces = 0
        self.num_samples = 0
        self.plot_lines = {}       # trace_idx -> Line2D
        self.mean_line = None
        self.highlighted_idx = None

        self._build_ui()
        self._connect_signals()

        if mat_file and os.path.isfile(mat_file):
            self._load_file(mat_file)

    # -----------------------------------------------------------------------
    # UI Construction
    # -----------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Top toolbar
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.btn_open = QPushButton("📂 Open .mat")
        self.btn_open.setFixedHeight(28)
        toolbar.addWidget(self.btn_open)
        toolbar.addSeparator()

        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.setFixedHeight(28)
        toolbar.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.setFixedHeight(28)
        toolbar.addWidget(self.btn_deselect_all)

        self.btn_invert = QPushButton("Invert")
        self.btn_invert.setFixedHeight(28)
        toolbar.addWidget(self.btn_invert)

        toolbar.addSeparator()

        self.chk_mean = QCheckBox("Show Mean")
        self.chk_mean.setChecked(False)
        toolbar.addWidget(self.chk_mean)

        self.chk_crosshair = QCheckBox("Crosshair")
        self.chk_crosshair.setChecked(True)
        toolbar.addWidget(self.chk_crosshair)

        toolbar.addSeparator()

        lbl_alpha = QLabel("  Opacity:")
        toolbar.addWidget(lbl_alpha)
        self.spin_alpha = QSpinBox()
        self.spin_alpha.setRange(5, 100)
        self.spin_alpha.setValue(60)
        self.spin_alpha.setSuffix("%")
        self.spin_alpha.setFixedWidth(70)
        toolbar.addWidget(self.spin_alpha)

        toolbar.addSeparator()

        self.btn_export = QPushButton("💾 Export Visible")
        self.btn_export.setFixedHeight(28)
        toolbar.addWidget(self.btn_export)

        # Main splitter: left panel (trace list) | right panel (plot + info)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # --- Left panel: trace list ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(2, 2, 2, 2)

        lbl_traces = QLabel("Traces")
        lbl_traces.setFont(QFont("Sans", 10, QFont.Bold))
        left_layout.addWidget(lbl_traces)

        self.trace_list = QListWidget()
        self.trace_list.setSelectionMode(QAbstractItemView.SingleSelection)
        left_layout.addWidget(self.trace_list)

        # Quick range selector
        range_box = QGroupBox("Quick Range")
        range_layout = QHBoxLayout(range_box)
        range_layout.setContentsMargins(4, 4, 4, 4)
        self.spin_from = QSpinBox()
        self.spin_from.setPrefix("From: ")
        self.spin_to = QSpinBox()
        self.spin_to.setPrefix("To: ")
        self.btn_range_select = QPushButton("Show Range")
        range_layout.addWidget(self.spin_from)
        range_layout.addWidget(self.spin_to)
        range_layout.addWidget(self.btn_range_select)
        left_layout.addWidget(range_box)

        splitter.addWidget(left_widget)

        # --- Right panel: plot + info ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(2, 2, 2, 2)

        # Matplotlib figure
        self.figure = Figure(figsize=(10, 5), dpi=100)
        self.figure.set_facecolor('#fafafa')
        self.ax = self.figure.add_subplot(111)
        self.ax.set_xlabel("Sample")
        self.ax.set_ylabel("Amplitude")
        self.ax.set_title("Power Traces")
        self.ax.grid(True, alpha=0.3)
        self.canvas = FigureCanvas(self.figure)
        self.nav_toolbar = NavigationToolbar(self.canvas, self)
        right_layout.addWidget(self.nav_toolbar)
        right_layout.addWidget(self.canvas, stretch=3)

        # Crosshair lines (hidden by default until mouse enters)
        self.crosshair_h = self.ax.axhline(color='gray', lw=0.5, ls='--', visible=False)
        self.crosshair_v = self.ax.axvline(color='gray', lw=0.5, ls='--', visible=False)

        # Info panel
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.StyledPanel)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(6, 4, 6, 4)

        self.lbl_info_header = QLabel("Trace Details")
        self.lbl_info_header.setFont(QFont("Sans", 10, QFont.Bold))
        info_layout.addWidget(self.lbl_info_header)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(140)
        self.info_text.setFont(QFont("Monospace", 9))
        info_layout.addWidget(self.info_text)

        right_layout.addWidget(info_frame, stretch=1)
        splitter.addWidget(right_widget)

        # Splitter proportions
        splitter.setStretchFactor(0, 1)  # left
        splitter.setStretchFactor(1, 4)  # right
        splitter.setSizes([250, 950])

        # Status bar
        self.statusBar().showMessage("Open a .mat file to begin")

    # -----------------------------------------------------------------------
    # Signal connections
    # -----------------------------------------------------------------------
    def _connect_signals(self):
        self.btn_open.clicked.connect(self._on_open)
        self.btn_select_all.clicked.connect(self._on_select_all)
        self.btn_deselect_all.clicked.connect(self._on_deselect_all)
        self.btn_invert.clicked.connect(self._on_invert)
        self.btn_range_select.clicked.connect(self._on_range_select)
        self.btn_export.clicked.connect(self._on_export)
        self.chk_mean.toggled.connect(self._update_mean)
        self.spin_alpha.valueChanged.connect(self._on_alpha_changed)
        self.trace_list.itemChanged.connect(self._on_item_check_changed)
        self.trace_list.currentRowChanged.connect(self._on_trace_selected)
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        self.canvas.mpl_connect('axes_leave_event', self._on_mouse_leave)

    # -----------------------------------------------------------------------
    # File loading
    # -----------------------------------------------------------------------
    def _on_open(self):
        start_dir = os.path.dirname(os.path.abspath(__file__))
        path, _ = QFileDialog.getOpenFileName(
            self, "Open .mat file", start_dir, "MAT files (*.mat);;All files (*)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, path):
        try:
            data = sio.loadmat(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{e}")
            return

        self.traces = data.get('traces', np.array([]))
        if self.traces.size == 0:
            QMessageBox.warning(self, "Warning", "No traces found in file.")
            return

        self.num_traces, self.num_samples = self.traces.shape
        self.plaintexts = data.get('plaintexts', None)
        self.ciphertexts_hw = data.get('ciphertexts_hw', None)
        self.ciphertexts_sw = data.get('ciphertexts_sw', None)
        self.key = data.get('key', None)

        self.metadata = {
            'file': os.path.basename(path),
            'num_traces': self.num_traces,
            'num_samples': self.num_samples,
            'operation': str(data.get('operation', ['?'])[0]) if 'operation' in data else '?',
            'sample_rate': float(data['sample_rate'].flat[0]) if 'sample_rate' in data else 0,
            'clk_freq': float(data['clk_freq'].flat[0]) if 'clk_freq' in data else 0,
            'gain_db': float(data['gain_db'].flat[0]) if 'gain_db' in data else 0,
            'mismatches': int(data['mismatches'].flat[0]) if 'mismatches' in data else 0,
        }

        self._populate_trace_list()
        self._clear_plot()
        self._update_info_metadata()

        # Update range spinboxes
        self.spin_from.setRange(0, self.num_traces - 1)
        self.spin_from.setValue(0)
        self.spin_to.setRange(0, self.num_traces - 1)
        self.spin_to.setValue(min(9, self.num_traces - 1))

        # Auto-show first N traces (up to 10)
        auto_count = min(10, self.num_traces)
        self.trace_list.blockSignals(True)
        for i in range(auto_count):
            item = self.trace_list.item(i)
            item.setCheckState(Qt.Checked)
        self.trace_list.blockSignals(False)
        self._redraw_all()

        self.setWindowTitle(f"Power Trace Explorer — {os.path.basename(path)}")
        self.statusBar().showMessage(
            f"Loaded {self.num_traces} traces × {self.num_samples} samples from {os.path.basename(path)}"
        )

    # -----------------------------------------------------------------------
    # Trace list
    # -----------------------------------------------------------------------
    def _populate_trace_list(self):
        self.trace_list.blockSignals(True)
        self.trace_list.clear()
        self.plot_lines.clear()

        for i in range(self.num_traces):
            # Build label
            label = f"[{i:>4}]"
            if self.plaintexts is not None and i < self.plaintexts.shape[0]:
                pt_hex = bytes(self.plaintexts[i]).hex()[:16]
                label += f"  PT={pt_hex}…"

            match_ok = True
            if (self.ciphertexts_hw is not None and self.ciphertexts_sw is not None
                    and self.ciphertexts_hw.size > 0 and self.ciphertexts_sw.size > 0
                    and i < self.ciphertexts_hw.shape[0] and i < self.ciphertexts_sw.shape[0]):
                match_ok = np.array_equal(self.ciphertexts_hw[i], self.ciphertexts_sw[i])
                label += "  ✓" if match_ok else "  ✗"

            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, i)

            color = QColor(TRACE_COLORS[i % len(TRACE_COLORS)])
            item.setForeground(color)
            if not match_ok:
                item.setBackground(QColor(255, 230, 230))

            self.trace_list.addItem(item)

        self.trace_list.blockSignals(False)

    # -----------------------------------------------------------------------
    # Plotting
    # -----------------------------------------------------------------------
    def _clear_plot(self):
        self.ax.clear()
        self.ax.set_xlabel("Sample")
        self.ax.set_ylabel("Amplitude")
        self.ax.set_title("Power Traces")
        self.ax.grid(True, alpha=0.3)
        self.crosshair_h = self.ax.axhline(color='gray', lw=0.5, ls='--', visible=False)
        self.crosshair_v = self.ax.axvline(color='gray', lw=0.5, ls='--', visible=False)
        self.plot_lines.clear()
        self.mean_line = None
        self.canvas.draw_idle()

    def _redraw_all(self):
        """Redraw all checked traces."""
        self.ax.clear()
        self.ax.set_xlabel("Sample")
        self.ax.set_ylabel("Amplitude")
        self.ax.set_title("Power Traces")
        self.ax.grid(True, alpha=0.3)
        self.crosshair_h = self.ax.axhline(color='gray', lw=0.5, ls='--', visible=False)
        self.crosshair_v = self.ax.axvline(color='gray', lw=0.5, ls='--', visible=False)
        self.plot_lines.clear()
        self.mean_line = None

        alpha = self.spin_alpha.value() / 100.0
        visible_indices = []

        for row in range(self.trace_list.count()):
            item = self.trace_list.item(row)
            if item.checkState() == Qt.Checked:
                idx = item.data(Qt.UserRole)
                visible_indices.append(idx)
                color = TRACE_COLORS[idx % len(TRACE_COLORS)]
                line, = self.ax.plot(
                    self.traces[idx], color=color, alpha=alpha, lw=0.7,
                    label=f"Trace {idx}", picker=3
                )
                self.plot_lines[idx] = line

        # Highlight
        if self.highlighted_idx is not None and self.highlighted_idx in self.plot_lines:
            self.plot_lines[self.highlighted_idx].set_linewidth(2.0)
            self.plot_lines[self.highlighted_idx].set_alpha(1.0)
            self.plot_lines[self.highlighted_idx].set_zorder(10)

        # Mean overlay
        if self.chk_mean.isChecked() and visible_indices:
            mean_trace = np.mean(self.traces[visible_indices], axis=0)
            self.mean_line, = self.ax.plot(
                mean_trace, color=MEAN_COLOR, lw=1.5, ls='--',
                label='Mean', zorder=11
            )

        if visible_indices:
            self.ax.legend(loc='upper right', fontsize=7, ncol=2, framealpha=0.7)

        self.statusBar().showMessage(f"Showing {len(visible_indices)}/{self.num_traces} traces")
        self.canvas.draw_idle()

    def _on_item_check_changed(self, item):
        """Toggle a single trace on/off."""
        idx = item.data(Qt.UserRole)
        alpha = self.spin_alpha.value() / 100.0

        if item.checkState() == Qt.Checked:
            if idx not in self.plot_lines:
                color = TRACE_COLORS[idx % len(TRACE_COLORS)]
                line, = self.ax.plot(
                    self.traces[idx], color=color, alpha=alpha, lw=0.7,
                    label=f"Trace {idx}"
                )
                self.plot_lines[idx] = line
        else:
            if idx in self.plot_lines:
                self.plot_lines[idx].remove()
                del self.plot_lines[idx]

        self._update_mean()
        visible = len(self.plot_lines)
        self.statusBar().showMessage(f"Showing {visible}/{self.num_traces} traces")
        self.canvas.draw_idle()

    def _on_trace_selected(self, row):
        """Highlight the selected trace and show its details."""
        if row < 0 or self.traces is None:
            return

        item = self.trace_list.item(row)
        idx = item.data(Qt.UserRole)

        # Un-highlight previous
        if self.highlighted_idx is not None and self.highlighted_idx in self.plot_lines:
            alpha = self.spin_alpha.value() / 100.0
            self.plot_lines[self.highlighted_idx].set_linewidth(0.7)
            self.plot_lines[self.highlighted_idx].set_alpha(alpha)
            self.plot_lines[self.highlighted_idx].set_zorder(1)

        self.highlighted_idx = idx

        # Highlight current
        if idx in self.plot_lines:
            self.plot_lines[idx].set_linewidth(2.0)
            self.plot_lines[idx].set_alpha(1.0)
            self.plot_lines[idx].set_zorder(10)
            self.canvas.draw_idle()

        # Show details
        self._show_trace_info(idx)

    def _show_trace_info(self, idx):
        """Display detailed info about a trace."""
        lines = [f"Trace #{idx}"]
        lines.append(f"{'─' * 50}")

        if self.key is not None:
            lines.append(f"Key:     {bytes(self.key.flat[:16]).hex()}")

        if self.plaintexts is not None and idx < self.plaintexts.shape[0]:
            lines.append(f"PT:      {bytes(self.plaintexts[idx]).hex()}")

        if self.ciphertexts_hw is not None and self.ciphertexts_hw.size > 0 and idx < self.ciphertexts_hw.shape[0]:
            lines.append(f"CT_HW:   {bytes(self.ciphertexts_hw[idx]).hex()}")

        if self.ciphertexts_sw is not None and self.ciphertexts_sw.size > 0 and idx < self.ciphertexts_sw.shape[0]:
            lines.append(f"CT_SW:   {bytes(self.ciphertexts_sw[idx]).hex()}")

        if (self.ciphertexts_hw is not None and self.ciphertexts_sw is not None
                and self.ciphertexts_hw.size > 0 and self.ciphertexts_sw.size > 0
                and idx < self.ciphertexts_hw.shape[0] and idx < self.ciphertexts_sw.shape[0]):
            match = np.array_equal(self.ciphertexts_hw[idx], self.ciphertexts_sw[idx])
            lines.append(f"Match:   {'✓ OK' if match else '✗ MISMATCH'}")

        trace = self.traces[idx]
        lines.append(f"{'─' * 50}")
        lines.append(f"Samples: {len(trace)}")
        lines.append(f"Min:     {trace.min():.6f}   Max: {trace.max():.6f}")
        lines.append(f"Mean:    {trace.mean():.6f}   Std: {trace.std():.6f}")
        lines.append(f"Peak-Peak: {trace.max() - trace.min():.6f}")

        self.info_text.setPlainText("\n".join(lines))

    def _update_info_metadata(self):
        """Show file-level metadata."""
        m = self.metadata
        lines = [
            f"File:        {m.get('file', '?')}",
            f"Operation:   {m.get('operation', '?')}",
            f"Traces:      {m.get('num_traces', 0)}",
            f"Samples:     {m.get('num_samples', 0)}",
            f"Sample Rate: {m.get('sample_rate', 0):.0f} Hz",
            f"Clock:       {m.get('clk_freq', 0):.0f} Hz",
            f"Gain:        {m.get('gain_db', 0):.1f} dB",
            f"Mismatches:  {m.get('mismatches', 0)}",
        ]
        self.info_text.setPlainText("\n".join(lines))

    # -----------------------------------------------------------------------
    # Toolbar actions
    # -----------------------------------------------------------------------
    def _on_select_all(self):
        self.trace_list.blockSignals(True)
        for row in range(self.trace_list.count()):
            self.trace_list.item(row).setCheckState(Qt.Checked)
        self.trace_list.blockSignals(False)
        self._redraw_all()

    def _on_deselect_all(self):
        self.trace_list.blockSignals(True)
        for row in range(self.trace_list.count()):
            self.trace_list.item(row).setCheckState(Qt.Unchecked)
        self.trace_list.blockSignals(False)
        self._redraw_all()

    def _on_invert(self):
        self.trace_list.blockSignals(True)
        for row in range(self.trace_list.count()):
            item = self.trace_list.item(row)
            new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
            item.setCheckState(new_state)
        self.trace_list.blockSignals(False)
        self._redraw_all()

    def _on_range_select(self):
        lo = self.spin_from.value()
        hi = self.spin_to.value()
        if lo > hi:
            lo, hi = hi, lo
        self.trace_list.blockSignals(True)
        for row in range(self.trace_list.count()):
            idx = self.trace_list.item(row).data(Qt.UserRole)
            state = Qt.Checked if lo <= idx <= hi else Qt.Unchecked
            self.trace_list.item(row).setCheckState(state)
        self.trace_list.blockSignals(False)
        self._redraw_all()

    def _on_alpha_changed(self, value):
        alpha = value / 100.0
        for idx, line in self.plot_lines.items():
            if idx != self.highlighted_idx:
                line.set_alpha(alpha)
        self.canvas.draw_idle()

    def _update_mean(self, _=None):
        """Add or remove mean overlay."""
        if self.mean_line is not None:
            try:
                self.mean_line.remove()
            except ValueError:
                pass
            self.mean_line = None

        if self.chk_mean.isChecked() and self.plot_lines:
            visible_indices = list(self.plot_lines.keys())
            mean_trace = np.mean(self.traces[visible_indices], axis=0)
            self.mean_line, = self.ax.plot(
                mean_trace, color=MEAN_COLOR, lw=1.5, ls='--',
                label='Mean', zorder=11
            )

        self.canvas.draw_idle()

    # -----------------------------------------------------------------------
    # Crosshair
    # -----------------------------------------------------------------------
    def _on_mouse_move(self, event):
        if not self.chk_crosshair.isChecked() or event.inaxes != self.ax:
            return
        self.crosshair_h.set_ydata([event.ydata, event.ydata])
        self.crosshair_v.set_xdata([event.xdata, event.xdata])
        self.crosshair_h.set_visible(True)
        self.crosshair_v.set_visible(True)

        # Show sample value in status bar
        sample_idx = int(round(event.xdata)) if event.xdata is not None else 0
        if 0 <= sample_idx < self.num_samples:
            msg = f"Sample: {sample_idx}  Amplitude: {event.ydata:.6f}"
            # Show values of visible traces at this sample
            if self.highlighted_idx is not None and self.highlighted_idx < self.num_traces:
                val = self.traces[self.highlighted_idx][sample_idx]
                msg += f"  | Trace {self.highlighted_idx}: {val:.6f}"
            self.statusBar().showMessage(msg)

        self.canvas.draw_idle()

    def _on_mouse_leave(self, event):
        self.crosshair_h.set_visible(False)
        self.crosshair_v.set_visible(False)
        self.canvas.draw_idle()

    # -----------------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------------
    def _on_export(self):
        if not self.plot_lines:
            QMessageBox.information(self, "Info", "No visible traces to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Visible Traces", "", "MAT files (*.mat);;All files (*)"
        )
        if not path:
            return

        visible_indices = sorted(self.plot_lines.keys())
        export_data = {
            'traces': self.traces[visible_indices],
            'num_traces': len(visible_indices),
            'num_samples': self.num_samples,
            'source_indices': np.array(visible_indices),
        }
        if self.key is not None:
            export_data['key'] = self.key
        if self.plaintexts is not None:
            export_data['plaintexts'] = self.plaintexts[visible_indices]
        if self.ciphertexts_hw is not None and self.ciphertexts_hw.size > 0:
            export_data['ciphertexts_hw'] = self.ciphertexts_hw[visible_indices]
        if self.ciphertexts_sw is not None and self.ciphertexts_sw.size > 0:
            export_data['ciphertexts_sw'] = self.ciphertexts_sw[visible_indices]

        try:
            sio.savemat(path, export_data)
            self.statusBar().showMessage(f"Exported {len(visible_indices)} traces to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed:\n{e}")


def main():
    parser = argparse.ArgumentParser(description="Power Trace Explorer GUI")
    parser.add_argument("--file", "-f", default=None,
                        help="Path to .mat file to open on startup")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark-ish palette for better trace visibility
    palette = app.palette()
    app.setPalette(palette)

    window = TraceExplorer(mat_file=args.file)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

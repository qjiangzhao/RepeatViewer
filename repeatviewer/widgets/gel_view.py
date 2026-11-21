"""Agarose gel drawing (``GelView``) and the ``.rvgel`` document page for Preview.

``GelView`` paints a :class:`GelDoc` with soft bands, the ladder sizes on the
left and lane numbers and names below; hover tells what a band is, a click
selects it and a double-click asks to open the product it came from. The same
widget is the quick gel in the PCR window.

Developer: Abdullah Yusuf
"""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from repeatviewer.backends.primers import gel_doc as gd
from repeatviewer.widgets.help_button import make_help_button

GEL_HELP = (
    "<b>In-silico gel</b>: every lane is a ladder, the products of a PCR run, or a product "
    "cut with a restriction enzyme.<br>"
    "<b>Agarose</b> changes which sizes separate (0.7 % for 1 to 12 kb, 3 % for 50 to 1,000 "
    "bp). <b>Run</b> is how far the front got; small bands can run off a long run.<br>"
    "<b>Brightness by amount of DNA</b>: a band's brightness follows its mass (amount × length), "
    "as with SYBR or GelRed, so short products look fainter.<br>"
    "<b>Hover</b> a band to see what it is, <b>click</b> to select it, <b>double-click</b> to "
    "open the products file. <b>Cut with</b> digests the lane's products (sequences come "
    "from the PCR run).<br>"
    "<b>Compare with Gel Photo</b> puts your real gel next to this one and names each band.<br>"
    "The gel is saved as it changes (.rvgel)."
)


class GelView(QWidget):
    bandClicked = Signal(int, object)        # lane index, GelBand (None = cleared)
    bandActivated = Signal(int, object)      # double-click
    laneClicked = Signal(int)

    def __init__(self, parent: QWidget | None = None, *, compact: bool = False) -> None:
        super().__init__(parent)
        self._doc: gd.GelDoc | None = None
        self._drawn: list[gd.DrawnBand] = []
        self._selected: tuple[int, int] | None = None   # lane, index in drawn
        self._compact = compact
        self._hover_rect: QRectF | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(200 if compact else 360, 260 if compact else 420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_doc(self, doc: gd.GelDoc | None) -> None:
        self._doc = doc
        self._drawn = gd.layout(doc) if doc is not None else []
        self._selected = None
        self.update()

    def refresh(self) -> None:
        self.set_doc(self._doc)

    def doc(self) -> gd.GelDoc | None:
        return self._doc

    # ---------------------------------------------------------------- geometry

    def _geometry(self) -> tuple[QRectF, float, float, float]:
        """Gel rect, lane width, gap, left margin for sizes."""
        n = max(1, len(self._doc.lanes) if self._doc else 1)
        left = 44 if self._compact else 64
        bottom = 30 if self._compact else 52
        top = 18 if self._compact else 24
        w = max(80.0, self.width() - left - 12)
        h = max(80.0, self.height() - top - bottom)
        gap = max(6.0, min(22.0, w / n * 0.22))
        lane_w = min(72.0, (w - gap * (n + 1)) / n)
        used = n * lane_w + (n + 1) * gap
        if not self._compact:
            left = max(left, (self.width() - used) / 2)
        rect = QRectF(left, top, used, h)
        return rect, lane_w, gap, left

    def _lane_x(self, i: int) -> float:
        rect, lane_w, gap, _ = self._geometry()
        return rect.left() + gap + i * (lane_w + gap)

    def _band_rect(self, d: gd.DrawnBand) -> QRectF:
        rect, lane_w, _gap, _ = self._geometry()
        inner = rect.adjusted(0, 14, 0, -6)
        y = inner.top() + d.y * inner.height()
        t = (3.0 if self._compact else 4.0) * d.thickness
        return QRectF(self._lane_x(d.lane), y - t / 2, lane_w, t)

    # ---------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        doc = self._doc
        if doc is None or not doc.lanes:
            p.setPen(self.palette().color(self.foregroundRole()))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No lanes")
            p.end()
            return
        dark = doc.look == gd.LOOKS[0]
        rect, lane_w, gap, left = self._geometry()
        bg_top = QColor("#1a2029") if dark else QColor("#f6f6f3")
        bg_bot = QColor("#11151b") if dark else QColor("#ececE8")
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0, bg_top)
        grad.setColorAt(1, bg_bot)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(rect, 7, 7)
        well = QColor("#39414d") if dark else QColor("#c9c9c4")
        for i in range(len(doc.lanes)):
            p.fillRect(QRectF(self._lane_x(i), rect.top() + 6, lane_w, 5), well)
        # size axis
        small = QFont(self.font())
        small.setPointSize(max(7, small.pointSize() - (3 if self._compact else 2)))
        p.setFont(small)
        inner = rect.adjusted(0, 14, 0, -6)
        text_col = self.palette().color(self.foregroundRole())
        muted = QColor(text_col)
        muted.setAlpha(150)
        last_y = -1e9
        marks = sorted(gd.ladder_marks(doc), key=lambda m: (-m[2], m[1]))
        shown = []
        for s, y, heavy in marks:   # heavy bands first, then the rest where there is room
            yy = inner.top() + y * inner.height()
            if all(abs(yy - o) >= 11 for o in shown):
                shown.append(yy)
        for s, y, heavy in gd.ladder_marks(doc):
            yy = inner.top() + y * inner.height()
            if yy not in shown:
                continue
            last_y = yy
            f = QFont(small)
            f.setBold(heavy)
            p.setFont(f)
            p.setPen(text_col if heavy else muted)
            label = f"{s / 1000:g}k" if (self._compact and s >= 1000) else f"{s:,}"
            p.drawText(QRectF(left - 70, yy - 8, 62, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
        p.setFont(small)
        # bands
        band_rgb = QColor(232, 241, 255) if dark else QColor(25, 25, 28)
        for idx, d in enumerate(self._drawn):
            r = self._band_rect(d)
            c = QColor(band_rgb)
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            c0 = QColor(c)
            c0.setAlphaF(0.0)
            c1 = QColor(c)
            c1.setAlphaF(max(0.05, min(1.0, d.intensity)))
            g.setColorAt(0.0, c0)
            g.setColorAt(0.5, c1)
            g.setColorAt(1.0, c0)
            p.setBrush(g)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(r.adjusted(0, -2, 0, 2))
            if self._selected == (d.lane, idx):
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor("#7fb0ff"), 2))
                p.drawRoundedRect(r.adjusted(-3, -4, 3, 4), 3, 3)
        # lane labels
        f = QFont(small)
        f.setBold(True)
        for i, lane in enumerate(doc.lanes):
            x = self._lane_x(i)
            p.setFont(f)
            p.setPen(text_col)
            num = "L" if lane.kind == gd.LANE_LADDER else str(i)
            p.drawText(QRectF(x - 6, rect.bottom() + 2, lane_w + 12, 16),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, num)
            if not self._compact:
                p.setFont(small)
                p.setPen(muted)
                name = lane.note if lane.kind == gd.LANE_LADDER else lane.label
                if lane.cut_with:
                    name = f"{name} + {lane.cut_with}"
                fm = p.fontMetrics()
                el = fm.elidedText(name, Qt.TextElideMode.ElideRight, int(lane_w + gap - 2))
                p.drawText(QRectF(x - gap / 2, rect.bottom() + 18, lane_w + gap, 16),
                           Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, el)
        p.end()

    # ---------------------------------------------------------------- mouse

    def _band_at(self, pos: QPointF) -> int | None:
        best, best_d = None, 1e9
        for idx, d in enumerate(self._drawn):
            r = self._band_rect(d).adjusted(0, -4, 0, 4)
            if r.contains(pos):
                dist = abs(r.center().y() - pos.y())
                if dist < best_d:
                    best, best_d = idx, dist
        return best

    def _lane_at(self, pos: QPointF) -> int | None:
        if self._doc is None:
            return None
        rect, lane_w, gap, _ = self._geometry()
        for i in range(len(self._doc.lanes)):
            x = self._lane_x(i)
            if x - gap / 2 <= pos.x() <= x + lane_w + gap / 2:
                return i
        return None

    def band_text(self, d: gd.DrawnBand) -> str:
        lane = self._doc.lanes[d.lane]
        b = d.band
        lines = [f"<b>{b.size:,} bp</b>" + (f" · {html.escape(b.label)}" if b.label else "")]
        if lane.kind == gd.LANE_LADDER:
            lines.append(html.escape(lane.note))
        else:
            lines.append(f"lane {d.lane} · {html.escape(lane.label)}")
            if b.ref:
                lines.append(html.escape(b.ref))
            lines.append(f"relative amount {b.amount:.2f}")
            if b.sequence:
                lines.append('<span style="color:#3d6ea8">double-click to open the product</span>')
        return "<br>".join(lines)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        idx = self._band_at(event.position())
        if idx is None:
            QToolTip.hideText()
            return
        QToolTip.showText(event.globalPosition().toPoint(), self.band_text(self._drawn[idx]), self)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        idx = self._band_at(event.position())
        if idx is None:
            self._selected = None
            lane = self._lane_at(event.position())
            if lane is not None:
                self.laneClicked.emit(lane)
            self.bandClicked.emit(-1, None)
        else:
            d = self._drawn[idx]
            self._selected = (d.lane, idx)
            self.laneClicked.emit(d.lane)
            self.bandClicked.emit(d.lane, d.band)
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        idx = self._band_at(event.position())
        if idx is not None:
            d = self._drawn[idx]
            self.bandActivated.emit(d.lane, d.band)

    def select_band(self, lane: int, size: int) -> None:
        for idx, d in enumerate(self._drawn):
            if d.lane == lane and d.band.size == size:
                self._selected = (lane, idx)
                self.update()
                return


class GelDocumentPanel(QWidget):
    """Preview page for a ``.rvgel`` file: toolbar, gel, settings and lanes."""

    openRequested = Signal(object)          # Path to open in RepeatViewer
    fileWritten = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: Path | None = None
        self._doc: gd.GelDoc | None = None
        self._loading = False
        # A new gel has no file until it is saved: where it would go, and
        # whether it was changed since it was made.
        self._folder: Path | None = None
        self._dirty = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setObjectName("gelDocument")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # As in the other sections: the gel (the result) on white, the toolbar
        # and the settings beside it in the window colour.
        self.setStyleSheet(
            "QWidget#gelDocument, QWidget#gelBar, QWidget#gelSide,"
            " QScrollArea#gelSideScroll, QScrollArea#gelSideScroll > QWidget"
            " { background: palette(window); }"
            " QWidget#gelHolder { background: palette(base);"
            " border: 1px solid palette(mid); border-radius: 8px; }"
            " QWidget#gelBar { border-radius: 5px; }")
        bar = QWidget(self)
        bar.setObjectName("gelBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 5, 8, 5)
        bl.setSpacing(6)
        self.add_button = QPushButton("Add Lane", bar)
        add_menu = QMenu(self.add_button)
        add_menu.addAction("Ladder", self._add_ladder)
        add_menu.addAction("PCR Result…", self._add_pcr_result)
        add_menu.addAction("Copy of the Selected Lane", self._duplicate_lane)
        self.add_button.setMenu(add_menu)
        bl.addWidget(self.add_button)
        self.dup_button = QPushButton("Duplicate", bar)
        self.remove_button = QPushButton("Remove", bar)
        self.left_button = QPushButton("◀", bar)
        self.right_button = QPushButton("▶", bar)
        self.left_button.setToolTip("Move the selected lane left")
        self.right_button.setToolTip("Move the selected lane right")
        for b in (self.dup_button, self.remove_button, self.left_button, self.right_button):
            bl.addWidget(b)
        bl.addSpacing(10)
        self.compare_button = QPushButton("Compare with Gel Photo", bar)
        bl.addWidget(self.compare_button)
        bl.addStretch(1)
        self.save_button = QPushButton("Save", bar)
        save_menu = QMenu(self.save_button)
        save_menu.addAction("Gel", self.save_document)
        save_menu.addSeparator()
        save_menu.addAction("Figure as SVG…", lambda: self._export("svg"))
        save_menu.addAction("Figure as PNG (300 dpi)…", lambda: self._export("png"))
        save_menu.addAction("Figure as PDF…", lambda: self._export("pdf"))
        self.save_button.setMenu(save_menu)
        bl.addWidget(self.save_button)
        bl.addWidget(make_help_button(bar, "In-silico gel", GEL_HELP))
        split = QSplitter(Qt.Orientation.Horizontal, self)
        split.setContentsMargins(12, 6, 0, 12)
        holder = QWidget(split)
        holder.setObjectName("gelHolder")
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(4, 4, 4, 12)
        hl.setSpacing(8)
        bar.setParent(holder)
        hl.addWidget(bar)
        gel_room = QVBoxLayout()
        gel_room.setContentsMargins(12, 0, 12, 0)
        self.view = GelView(holder)
        gel_room.addWidget(self.view, 1)
        hl.addLayout(gel_room, 1)
        split.addWidget(holder)

        side = QWidget(split)
        side.setObjectName("gelSide")
        # as wide as the settings side of the other sections, and its title
        # at the same height
        side.setMinimumWidth(330)
        side.setMaximumWidth(460)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(10, 0, 10, 12)
        sl.setSpacing(10)
        head = QLabel("<b>Gel</b>", side)
        head.setMinimumHeight(22)
        sl.addWidget(head)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.ladder_combo = QComboBox(side)
        self.ladder_combo.addItems(list(gd.LADDERS))
        self.agarose_slider = QSlider(Qt.Orientation.Horizontal, side)
        self.agarose_slider.setRange(5, 40)
        self.agarose_label = QLabel(side)
        ag = QWidget(side)
        agl = QHBoxLayout(ag)
        agl.setContentsMargins(0, 0, 0, 0)
        agl.addWidget(self.agarose_slider, 1)
        agl.addWidget(self.agarose_label)
        self.run_combo = QComboBox(side)
        self.run_combo.addItems(list(gd.RUNS))
        self.look_combo = QComboBox(side)
        self.look_combo.addItems(list(gd.LOOKS))
        for w in (self.ladder_combo, self.run_combo, self.look_combo, ag):
            w.setFixedWidth(210)
        form.addRow("Ladder", self.ladder_combo)
        form.addRow("Agarose", ag)
        form.addRow("Run", self.run_combo)
        form.addRow("Look", self.look_combo)
        sl.addLayout(form)
        self.mass_check = QCheckBox("Brightness by amount of DNA", side)
        self.dimer_check = QCheckBox("Show primer-dimer", side)
        sl.addWidget(self.mass_check)
        sl.addWidget(self.dimer_check)
        sl.addWidget(QLabel("<b>Lanes</b>", side))
        self.lanes_table = QTableWidget(0, 2, side)
        self.lanes_table.setHorizontalHeaderLabels(["#", "From"])
        self.lanes_table.verticalHeader().hide()
        self.lanes_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lanes_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lanes_table.setShowGrid(False)
        h = self.lanes_table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        h.setStretchLastSection(True)
        self.lanes_table.setColumnWidth(0, 30)
        self.lanes_table.setColumnWidth(1, 170)
        sl.addWidget(self.lanes_table, 1)
        self.band_label = QLabel(side)
        self.band_label.setWordWrap(True)
        self.band_label.setTextFormat(Qt.TextFormat.RichText)
        self.band_label.setStyleSheet("QLabel { border: 1px solid palette(mid); border-radius: 8px;"
                                      " padding: 8px; }")
        self.band_label.hide()
        sl.addWidget(self.band_label)
        scroll = QScrollArea(split)
        scroll.setObjectName("gelSideScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(side)
        scroll.setMinimumWidth(330)     # the side is never cut off on the right
        split.addWidget(scroll)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        root.addWidget(split, 1)

        self.ladder_combo.currentTextChanged.connect(self._on_ladder)
        self.agarose_slider.valueChanged.connect(self._on_agarose)
        self.run_combo.currentTextChanged.connect(self._on_settings)
        self.look_combo.currentTextChanged.connect(self._on_settings)
        self.mass_check.toggled.connect(self._on_settings)
        self.dimer_check.toggled.connect(self._on_settings)
        self.dup_button.clicked.connect(self._duplicate_lane)
        self.remove_button.clicked.connect(self._remove_lane)
        self.left_button.clicked.connect(lambda: self._move_lane(-1))
        self.right_button.clicked.connect(lambda: self._move_lane(1))
        self.compare_button.clicked.connect(self._compare_photo)
        self.view.bandClicked.connect(self._on_band)
        self.view.laneClicked.connect(self._select_lane_row)
        self.view.bandActivated.connect(self._on_band_activated)

    # ---------------------------------------------------------------- load/save

    def new_untitled(self, folder: Path | None = None) -> None:
        """An empty gel (a ladder only) that is not a file yet.

        Nothing is written until Save > Gel; after that it saves itself as
        any gel does.
        """
        self._path = None
        self._folder = Path(folder) if folder else None
        self._dirty = False
        self._doc = gd.GelDoc()
        self._doc.lanes = [gd.ladder_lane(self._doc.ladder)]
        self._doc.title = "Gel"
        self._sync_controls()
        self.view.set_doc(self._doc)

    def has_unsaved(self) -> bool:
        """A new gel that was changed and never saved."""
        return self._path is None and self._doc is not None and self._dirty

    def save_document(self) -> bool:
        """Write the gel (.rvgel). A new gel gets its file now. False when it failed."""
        if self._doc is None:
            return False
        if self._path is not None:
            self._save()
            return True
        folder = self._folder if self._folder and self._folder.is_dir() else Path.home()
        path = gd.unique_gel_path(folder, "Gel")
        self._doc.title = path.stem
        try:
            self._doc.save(path)
        except OSError as exc:
            QMessageBox.warning(self, "Gel", f"Could not save the gel:\n{exc}")
            return False
        self._path = path
        self._dirty = False
        self.fileWritten.emit(path)
        return True

    def confirm_leave(self) -> bool:
        """An unsaved new gel: Save / Discard / Cancel. True to go on."""
        if not self.has_unsaved():
            return True
        box = QMessageBox(self.window())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Unsaved Gel")
        box.setText("Save this gel?")
        box.setInformativeText("It was not saved yet. Discard throws it away.")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        box.setEscapeButton(QMessageBox.StandardButton.Cancel)
        choice = box.exec()
        if choice == QMessageBox.StandardButton.Save:
            return self.save_document()
        if choice == QMessageBox.StandardButton.Discard:
            self._dirty = False
            return True
        return False

    def load(self, path: Path) -> None:
        self._path = Path(path)
        self._dirty = False
        try:
            self._doc = gd.GelDoc.load(self._path)
        except (OSError, ValueError) as exc:
            self._doc = gd.GelDoc()
            QMessageBox.warning(self, "Gel", f"Could not read {self._path.name}:\n{exc}")
        self._sync_controls()
        self.view.set_doc(self._doc)

    def doc(self) -> gd.GelDoc | None:
        return self._doc

    def path(self) -> Path | None:
        return self._path

    def _changed(self) -> None:
        self.view.refresh()
        if self._path is None:
            self._dirty = True          # a new gel: kept in memory until Save
            return
        self._save_timer.start()

    def _save(self) -> None:
        if self._path is None or self._doc is None:
            return
        try:
            self._doc.save(self._path)
        except OSError as exc:
            QMessageBox.warning(self, "Gel", f"Could not save the gel:\n{exc}")

    def _sync_controls(self) -> None:
        doc = self._doc
        if doc is None:
            return
        self._loading = True
        try:
            self.ladder_combo.setCurrentText(doc.ladder)
            self.agarose_slider.setValue(int(round(doc.agarose * 10)))
            self.agarose_label.setText(f"{doc.agarose:.1f} %")
            self.run_combo.setCurrentText(doc.run)
            self.look_combo.setCurrentText(doc.look)
            self.mass_check.setChecked(doc.mass_brightness)
            self.dimer_check.setChecked(doc.show_dimers)
            self._fill_lanes()
        finally:
            self._loading = False

    def _fill_lanes(self) -> None:
        doc = self._doc
        self.lanes_table.setRowCount(len(doc.lanes))

        for r, lane in enumerate(doc.lanes):
            self.lanes_table.setItem(r, 0, QTableWidgetItem("L" if lane.kind == gd.LANE_LADDER
                                                            else str(r)))
            name = lane.note if lane.kind == gd.LANE_LADDER else lane.label
            item = QTableWidgetItem(name)
            item.setToolTip(f"{len(lane.bands)} band(s)" + (f"\n{lane.source}" if lane.source else ""))
            self.lanes_table.setItem(r, 1, item)

    # ---------------------------------------------------------------- settings

    def _on_ladder(self, name: str) -> None:
        if self._loading or self._doc is None:
            return
        gd.set_ladder(self._doc, name)
        self._fill_lanes()
        self._changed()

    def _on_agarose(self, value: int) -> None:
        if self._doc is None:
            return
        self.agarose_label.setText(f"{value / 10:.1f} %")
        if self._loading:
            return
        self._doc.agarose = value / 10.0
        self._changed()

    def _on_settings(self, *_a) -> None:
        if self._loading or self._doc is None:
            return
        self._doc.run = self.run_combo.currentText()
        self._doc.look = self.look_combo.currentText()
        self._doc.mass_brightness = self.mass_check.isChecked()
        self._doc.show_dimers = self.dimer_check.isChecked()
        self._changed()

    def _on_cut(self, row: int, enzyme) -> None:
        if self._loading or self._doc is None or not (0 <= row < len(self._doc.lanes)):
            return
        self._doc.lanes[row].cut_with = str(enzyme or "")
        self._changed()

    # ---------------------------------------------------------------- lanes

    def _current_row(self) -> int | None:
        rows = {i.row() for i in self.lanes_table.selectedIndexes()}
        return min(rows) if rows else None

    def _select_lane_row(self, lane: int) -> None:
        self.lanes_table.selectRow(lane)

    def _add_ladder(self) -> None:
        if self._doc is None:
            return
        self._doc.lanes.append(gd.ladder_lane(self._doc.ladder))
        self._fill_lanes()
        self._changed()

    def _add_pcr_result(self) -> None:
        if self._doc is None:
            return
        start = str(self._path.parent) if self._path else ""
        fn, _ = QFileDialog.getOpenFileName(self, "Add PCR Result", start,
                                            "PCR result (*_result.json)")
        if not fn:
            return
        from repeatviewer.backends.primers import pcr

        try:
            res = pcr.load_result(Path(fn))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Gel", str(exc))
            return
        self._doc.lanes.extend(gd.lanes_from_pcr(res))
        self._fill_lanes()
        self._changed()

    def _duplicate_lane(self) -> None:
        row = self._current_row()
        if self._doc is None or row is None:
            return
        import copy

        self._doc.lanes.insert(row + 1, copy.deepcopy(self._doc.lanes[row]))
        self._fill_lanes()
        self.lanes_table.selectRow(row + 1)
        self._changed()

    def _remove_lane(self) -> None:
        row = self._current_row()
        if self._doc is None or row is None:
            return
        del self._doc.lanes[row]
        self._fill_lanes()
        self._changed()

    def _move_lane(self, step: int) -> None:
        row = self._current_row()
        if self._doc is None or row is None:
            return
        new = row + step
        if not (0 <= new < len(self._doc.lanes)):
            return
        lanes = self._doc.lanes
        lanes[row], lanes[new] = lanes[new], lanes[row]
        self._fill_lanes()
        self.lanes_table.selectRow(new)
        self._changed()

    # ---------------------------------------------------------------- bands

    def _on_band(self, lane: int, band) -> None:
        if band is None:
            self.band_label.hide()
            return
        d = next((x for x in self.view._drawn if x.lane == lane and x.band is band), None)
        if d is None:
            self.band_label.hide()
            return
        self.band_label.setText(self.view.band_text(d))
        self.band_label.show()

    def _on_band_activated(self, lane: int, band) -> None:
        if self._doc is None or not (0 <= lane < len(self._doc.lanes)):
            return
        src = self._doc.lanes[lane].source
        if self._path is not None:
            # Products FASTA of a PCR run sits next to the gel with the same base name.
            base = self._path.name[: -len(gd.GEL_SUFFIX)]
            cand = self._path.with_name(base + ".fa")
            if cand.is_file():
                self.openRequested.emit(cand)
                return
        if src and Path(src).is_file():
            self.openRequested.emit(Path(src))

    # ---------------------------------------------------------------- export

    def _export(self, kind: str) -> None:
        if self._doc is None:
            return
        base = self._path.with_suffix("") if self._path else Path("gel")
        suggested = f"{base}{gd.GEL_SUFFIX}_gel.{kind}"
        fn, _ = QFileDialog.getSaveFileName(self, "Save Gel Figure", suggested,
                                            f"{kind.upper()} (*.{kind})")
        if not fn:
            return
        out = Path(fn)
        try:
            if kind == "svg":
                out.write_text(gd.to_svg(self._doc), encoding="utf-8")
            else:
                save_view_image(self.view, out, kind)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Gel", f"Could not save the figure:\n{exc}")
            return
        self.fileWritten.emit(out)

    def _compare_photo(self) -> None:
        if self._doc is None:
            return
        from repeatviewer.views.gel_photo_dialog import GelPhotoDialog

        dlg = GelPhotoDialog(self._doc, gel_path=self._path, parent=self.window())
        dlg.setWindowFlag(Qt.WindowType.Tool, True)
        dlg.show()


def save_view_image(view: QWidget, path: Path, kind: str) -> None:
    """PNG at 300 dpi or vector-ish PDF of a widget's painting."""
    from PySide6.QtCore import QPoint, QSize
    from PySide6.QtGui import QImage, QPageSize, QPdfWriter

    if kind == "png":
        scale = 300 / 96
        size = QSize(int(view.width() * scale), int(view.height() * scale))
        img = QImage(size, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.white)
        img.setDotsPerMeterX(int(300 / 0.0254))
        img.setDotsPerMeterY(int(300 / 0.0254))
        p = QPainter(img)
        try:
            p.scale(scale, scale)
            view.render(p, QPoint())
        finally:
            p.end()
        img.save(str(path), "PNG")
        return
    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    from PySide6.QtCore import QSizeF

    writer.setPageSize(QPageSize(QSizeF(view.width(), view.height()), QPageSize.Unit.Point))
    p = QPainter(writer)
    try:
        view.render(p, QPoint())
    finally:
        p.end()

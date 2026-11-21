"""Map as a tab in the middle: where the primers bind, and what they amplify.

Left: one row per sequence with the binding sites drawn on it, forward blue,
reverse orange, and a line between the two ends of a product. Right: the
primers, the sequences to test, how many mismatches are allowed, and what
counts as a product. The report is written only when you ask for it.

Developer: Abdullah Yusuf
"""

from __future__ import annotations

import html
import json
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QLineEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repeatviewer.backends.primers import jobs as pj
from repeatviewer.widgets.help_button import make_help_button
from repeatviewer.widgets.primer_design_pane import (
    BOX2_W,
    FIELD_W,
    GAP,
    LABEL_W,
    _row,
    _row_widget,
    _rule,
    _section,
    _spin,
)

HALF_W = (FIELD_W - GAP) // 2

_SETTINGS_KEY = "primers/map_page"
PANEL_W = 330
FORWARD, REVERSE, PROBE = "#1F57C3", "#C2410C", "#7A3E9D"
MAX_DRAWN = 40

PRIMERS_HELP = (
    "<b>Saved primers</b> searches your whole Primer Database (or a primers FASTA) for the "
    "ones that bind the sequences, and reports the pairs that give a product. Leave "
    "Forward / Reverse / Probe ticked to search all three kinds; <b>Pairs only</b> drops the "
    "primers that bind alone.<br>"
    "<b>These primers</b> tests the ones you name: a saved primer name or a sequence typed "
    "5′→3′."
)
CONSENSUS_HELP = (
    "For an alignment, the primers are tested on one consensus instead of every row. "
    "The threshold decides how a column becomes one IUPAC code; 0 % takes the most common base."
)
SEQUENCES_HELP = (
    "The FASTA files ticked in the Files panel. <b>Consensus</b> tests the primers on one "
    "consensus of an alignment instead of each row."
)
MISMATCH_HELP = (
    "<b>Max mismatches</b>: how different a site may be and still count.<br>"
    "<b>3′ bases exact</b>: the last bases of the primer that must match, because a "
    "mismatch there stops the polymerase. For a probe this is 0."
)
PRODUCT_HELP = (
    "Two sites facing each other within this size range count as a product. "
    "<b>Count sites in the genome</b> also searches the project genome, which takes longer."
)
PICTURE_HELP = (
    "One row per sequence. Forward sites are blue, reverse orange, probes purple; the line "
    "between two sites is a product, with its size. Only the first "
    f"{MAX_DRAWN} sequences are drawn."
)


class _Relay(QObject):
    done = Signal(object, object)       # payload | None, error | None


class BindingPicture(QWidget):
    """Where every primer binds on every sequence, one row per sequence."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []
        self.setMinimumHeight(80)

    def set_payload(self, payload: dict | None) -> None:
        self._rows = []
        if payload:
            lengths = {t["id"]: int(t.get("length") or 0) for t in payload.get("templates", [])}
            by_record: dict[str, dict] = {}
            for site in payload.get("sites", []):
                row = by_record.setdefault(site["record"], {"sites": [], "products": []})
                row["sites"].append(site)
            for product in payload.get("products", []):
                by_record.setdefault(product["record"], {"sites": [], "products": []})
                by_record[product["record"]]["products"].append(product)
            for rid, row in list(by_record.items())[:MAX_DRAWN]:
                row["id"] = rid
                row["length"] = lengths.get(rid) or max(
                    [s["end"] for s in row["sites"]] + [p["end"] for p in row["products"]] + [1])
                self._rows.append(row)
        self.setMinimumHeight(24 + 46 * max(1, len(self._rows)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self._rows:
            painter.setPen(QColor("#6b7280"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Press Map to see where the primers bind.")
            painter.end()
            return
        font = painter.font()
        font.setPointSizeF(max(7.5, font.pointSizeF() * 0.82))
        painter.setFont(font)
        name_w, size_w = 150.0, 70.0
        left = name_w + 8
        right = max(left + 60, self.width() - size_w - 8)
        span = right - left
        y = 18.0
        for row in self._rows:
            length = max(1, int(row["length"]))

            def x_of(pos: int, length=length) -> float:
                return left + span * min(max(0, pos - 1), length) / length

            painter.setPen(QColor("#3A3A3C"))
            painter.drawText(QRectF(0, y - 8, name_w, 16),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             str(row["id"])[:28])
            painter.setPen(QColor("#5A5D63"))
            painter.drawText(QRectF(right + 6, y - 8, size_w, 16),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f"{length:,} bp")
            painter.fillRect(QRectF(left, y - 4, span, 9), QColor("#D9D9DE"))
            for site in row["sites"]:
                x = x_of(int(site["start"]))
                strand = site.get("strand", "+")
                colour = QColor(FORWARD if strand == "+" else REVERSE)
                if site.get("mismatches"):
                    colour.setAlpha(150)
                tip = 12.0 if strand == "+" else -12.0
                poly = QPolygonF([
                    QRectF(x, y - 4, 1, 1).topLeft(),
                    QRectF(x + tip, y - 4, 1, 1).topLeft(),
                    QRectF(x + tip + (5 if strand == "+" else -5), y + 0.5, 1, 1).topLeft(),
                    QRectF(x + tip, y + 5, 1, 1).topLeft(),
                    QRectF(x, y + 5, 1, 1).topLeft(),
                ])
                painter.setBrush(colour)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPolygon(poly)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            last_label_right = -1e9
            for product in row["products"][:12]:
                a, b = x_of(int(product["start"])), x_of(int(product["end"]))
                painter.setPen(QColor("#1C1C1E"))
                painter.drawLine(QRectF(a, y + 14, 1, 1).topLeft(),
                                 QRectF(b, y + 14, 1, 1).topLeft())
                text = f"{int(product['size']):,} bp"
                width = painter.fontMetrics().horizontalAdvance(text) + 8
                middle = (a + b) / 2
                if middle - width / 2 > last_label_right:     # no label on top of another
                    painter.drawText(QRectF(middle - width / 2, y + 16, width, 14),
                                     Qt.AlignmentFlag.AlignCenter, text)
                    last_label_right = middle + width / 2
            if len(row["products"]) > 1:
                painter.setPen(QColor("#5A5D63"))
                painter.drawText(QRectF(right + 6, y + 14, size_w, 14),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 f"{len(row['products'])} products")
            y += 46
        painter.end()


class MapPage(QWidget):
    """Test primers on the selected sequences and show where they bind."""

    def __init__(self, files=(), *, options=None, database_path: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = None
        self._files = [Path(p) for p in files]
        self._database_path = database_path
        self._options = options
        self._payload: dict | None = None
        self._busy = False
        self._relay = _Relay(self)
        self._relay.done.connect(self._on_done)
        saved = self._load()
        base = dict(getattr(options, "map", None) or {})
        base.update(saved)

        from repeatviewer.widgets.primer_design_pane import (
            _card, _results_surface, _scroll_panel)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        middle = QWidget(self)
        lay = QVBoxLayout(middle)
        lay.setContentsMargins(12, 6, 12, 12)
        lay.setSpacing(10)
        from repeatviewer.widgets.primer_design_pane import VerdictLabel

        self.verdict = VerdictLabel(middle)
        self.verdict.setObjectName("mapVerdict")

        self.table = QTableWidget(0, 6, middle)
        self.table.setHorizontalHeaderLabels(
            ["Sequence", "Forward", "Reverse", "Sites", "Product", "Mismatches"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        head = self.table.horizontalHeader()
        head.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c, w in ((1, 90), (2, 90), (3, 70), (4, 150), (5, 110)):
            self.table.setColumnWidth(c, w)
        self.table.setMinimumHeight(120)
        lay.addWidget(_card(self.table, middle))

        pic_head = QHBoxLayout()
        pic_head.addWidget(QLabel("<b>Where they bind</b>", middle), 1)
        pic_head.addWidget(make_help_button(middle, "Where they bind", PICTURE_HELP))
        lay.addLayout(pic_head)
        self.picture = BindingPicture(middle)
        lay.addWidget(_card(self.picture, middle), 1)
        lay.addWidget(self.verdict)     # under the boxes, when there is one
        _results_surface(middle)
        from repeatviewer.widgets.primer_design_pane import _scroll_middle

        outer.addWidget(_scroll_middle(middle, self), 1)

        panel = QWidget(self)
        panel.setFixedWidth(PANEL_W)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(10, 6, 10, 8)
        pl.setSpacing(6)
        title = QHBoxLayout()
        title.addWidget(QLabel("<b>Map</b>", panel), 1)
        title.addWidget(make_help_button(panel, "Map", PRIMERS_HELP))
        pl.addLayout(title)
        pl.addWidget(_rule(panel))

        sec, sl, _ = _section("Primers", panel, "Primers", PRIMERS_HELP)
        self.source = QComboBox(sec)
        self.source.addItem("Saved primers", pj.MAP_DATABASE)
        self.source.addItem("These primers", pj.MAP_SPECIFIC)
        self.source.setFixedWidth(FIELD_W)
        i = self.source.findData(base.get("mode", pj.MAP_DATABASE))
        self.source.setCurrentIndex(max(0, i))
        sl.addLayout(_row("Test", self.source, parent=sec))

        # Saved primers: the Database, or a primers FASTA.
        self.stock_from = QComboBox(sec)
        self.stock_from.addItem("Primer Database", "db")
        self.stock_from.addItem("A FASTA file", "file")
        self.stock_from.setFixedWidth(FIELD_W)
        self.stock_from.setCurrentIndex(1 if base.get("primer_file") else 0)
        self.stock_from_row = _row_widget("From", self.stock_from, parent=sec)
        sl.addWidget(self.stock_from_row)
        self.primer_file = QLineEdit(sec)
        self.primer_file.setText(str(base.get("primer_file") or ""))
        self.primer_file.setPlaceholderText("Primers FASTA")
        self.primer_file.setFixedWidth(FIELD_W - 30)
        self.primer_file_button = QPushButton("…", sec)
        self.primer_file_button.setFixedWidth(28)
        self.primer_file_row = _row_widget("File", self.primer_file, self.primer_file_button,
                                           parent=sec)
        sl.addWidget(self.primer_file_row)
        self.search_forward = QCheckBox("Forward", sec)
        self.search_reverse = QCheckBox("Reverse", sec)
        self.search_probe = QCheckBox("Probe", sec)
        self.pairs_only = QCheckBox("Pairs only", sec)
        for box, key, on in ((self.search_forward, "search_forward", True),
                             (self.search_reverse, "search_reverse", True),
                             (self.search_probe, "search_probe", True),
                             (self.pairs_only, "pairs_only", False)):
            box.setChecked(bool(base.get(key, on)))
            box.setFixedWidth(HALF_W)
        self.kinds_row = _row_widget("Search for", self.search_forward, self.search_reverse,
                                     parent=sec)
        self.kinds_row2 = _row_widget("", self.search_probe, self.pairs_only, parent=sec)
        sl.addWidget(self.kinds_row)
        sl.addWidget(self.kinds_row2)
        self.only_label = QLabel("", sec)
        self.only_label.setWordWrap(True)
        self.only_label.setFixedWidth(FIELD_W - 60)
        self.only_all = QPushButton("Use all", sec)
        self.only_all.setFixedWidth(58)
        self.only_row = _row_widget("Only", self.only_label, self.only_all, parent=sec)
        sl.addWidget(self.only_row)

        # These primers: a saved name, or a sequence typed in.
        self.forward = QComboBox(sec)
        self.reverse = QComboBox(sec)
        self.probe = QComboBox(sec)
        self.rows_specific = []
        for box, label, key in ((self.forward, "Forward", "forward"),
                                (self.reverse, "Reverse", "reverse"),
                                (self.probe, "Probe", "probe")):
            box.setEditable(True)
            box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            box.setFixedWidth(FIELD_W)
            box.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            box.setMinimumContentsLength(12)
            box.lineEdit().setPlaceholderText("Saved name, or a sequence 5′→3′")
            row = _row_widget(label, box, parent=sec)
            self.rows_specific.append(row)
            sl.addWidget(row)
        self._only_names = [str(n) for n in (base.get("primer_names") or []) if str(n).strip()]
        pl.addWidget(sec)
        pl.addWidget(_rule(panel))

        sec, sl, _ = _section("Sequences", panel, "Sequences", SEQUENCES_HELP)
        self.test_on = QComboBox(sec)
        self.test_on.addItem("The selected files", pj.TEST_ON_SEQUENCES)
        self.test_on.addItem("Consensus of an alignment", pj.TEST_ON_CONSENSUS)
        self.test_on.setFixedWidth(FIELD_W)
        i = self.test_on.findData(base.get("test_on", pj.TEST_ON_SEQUENCES))
        self.test_on.setCurrentIndex(max(0, i))
        sl.addLayout(_row("Test on", self.test_on, parent=sec))
        self.threshold = QComboBox(sec)
        for text, value in (("0 % – Majority", 0.0), ("25 %", 0.25), ("50 %", 0.5),
                            ("75 %", 0.75), ("95 %", 0.95), ("100 % – Identical", 1.0)):
            self.threshold.addItem(text, value)
        self.threshold.setFixedWidth(FIELD_W)
        i = self.threshold.findData(float(base.get("consensus_threshold", 0.0) or 0.0))
        self.threshold.setCurrentIndex(max(0, i))
        self.threshold_row = _row_widget("Threshold", self.threshold, parent=sec)
        sl.addWidget(self.threshold_row)
        self.ignore_gaps = QCheckBox("Ignore gaps", sec)
        self.ignore_gaps.setChecked(bool(base.get("consensus_ignore_gaps", True)))
        self.gaps_row = _row_widget("", self.ignore_gaps, parent=sec)
        sl.addWidget(self.gaps_row)
        self.files_note = QLabel(sec)
        self.files_note.setWordWrap(True)
        self.files_note.setIndent(LABEL_W + 2)
        self.files_note.setStyleSheet("color: palette(placeholder-text);")
        sl.addWidget(self.files_note)
        pl.addWidget(sec)
        pl.addWidget(_rule(panel))

        sec, sl, _ = _section("Mismatches", panel, "Mismatches", MISMATCH_HELP)
        # as wide as the fields above; the unit sits inside the box
        self.mismatches = _spin(0, 10, int(base.get("max_mismatches", 2)), parent=sec,
                                suffix=" nt", width=FIELD_W)
        sl.addLayout(_row("Max", self.mismatches, parent=sec))
        self.exact = _spin(0, 20, int(base.get("three_prime_exact", 3)), parent=sec,
                           suffix=" nt", width=FIELD_W)
        sl.addLayout(_row("3′ exact", self.exact, parent=sec))
        pl.addWidget(sec)
        pl.addWidget(_rule(panel))

        sec, sl, _ = _section("Products", panel, "Products", PRODUCT_HELP)
        self.size_min = _spin(1, 100_000, int(base.get("product_min", 1)), parent=sec,
                              width=BOX2_W)
        self.size_max = _spin(1, 1_000_000, int(base.get("product_max", 5000)), parent=sec,
                              width=BOX2_W)
        for box in (self.size_min, self.size_max):
            box.setGroupSeparatorShown(True)
        sl.addLayout(_row("Size", self.size_min, self.size_max, parent=sec, joins=("to",)))
        self.genome_check = QCheckBox("Count sites in the genome", sec)
        self.genome_check.setChecked(bool(base.get("check_genome", False)))
        sl.addLayout(_row("", self.genome_check, parent=sec))
        pl.addWidget(sec)
        pl.addWidget(_rule(panel))

        sec, sl, _ = _section("Options", panel, "Options", PRIMERS_HELP)
        self.annotate_check = QCheckBox("Add the sites to the sequence", sec)
        self.annotate_check.setChecked(bool(base.get("annotate", False)))
        self.report_check = QCheckBox("Write a report beside the files", sec)
        self.report_check.setChecked(bool(saved.get("report", False)))
        for box in (self.annotate_check, self.report_check):
            sl.addLayout(_row("", box, parent=sec))
        self.defaults_button = QPushButton("Restore Defaults", sec)
        self.save_button = QPushButton("Save", sec)
        self.map_button = QPushButton("Map", sec)
        self.map_button.setDefault(True)
        # in the field column: one button as wide as a field, then two halves
        from repeatviewer.widgets.primer_design_pane import _field_buttons

        sl.addLayout(_field_buttons(sec, self.defaults_button))
        sl.addLayout(_field_buttons(sec, self.save_button, self.map_button))
        self.saved_note = QLabel("", sec)
        self.saved_note.setWordWrap(True)
        self.saved_note.setStyleSheet("color: palette(placeholder-text);")
        sl.addWidget(self.saved_note)
        pl.addWidget(sec)
        pl.addStretch(1)
        outer.addWidget(_scroll_panel(panel, self))

        self.map_button.clicked.connect(self.run_map)
        self.save_button.clicked.connect(self._on_save)
        self.defaults_button.clicked.connect(self._on_defaults)
        self.source.currentIndexChanged.connect(self._sync_rows)
        self.stock_from.currentIndexChanged.connect(self._sync_rows)
        self.test_on.currentIndexChanged.connect(self._sync_rows)
        self.primer_file_button.clicked.connect(self._choose_primer_file)
        self.only_all.clicked.connect(self._use_all_saved)
        self._fill_primers()
        self._apply_primers(base)
        self._sync_rows()
        self._refresh_files()
        self._show_idle()

    # ------------------------------------------------------------------ settings

    def _load(self) -> dict:
        raw = QSettings().value(_SETTINGS_KEY, "")
        try:
            d = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            d = {}
        return d if isinstance(d, dict) else {}

    def settings(self) -> pj.MapSettings:
        base = dict(getattr(self._options, "map", None) or {})
        saved = str(self.source.currentData()) == pj.MAP_DATABASE
        base.update(
            mode=str(self.source.currentData()),
            pairs_only=self.pairs_only.isChecked(),
            test_on=str(self.test_on.currentData()),
            consensus_threshold=float(self.threshold.currentData() or 0.0),
            consensus_ignore_gaps=self.ignore_gaps.isChecked(),
            use_max_mismatches=True,
            max_mismatches=int(self.mismatches.value()),
            three_prime_exact=int(self.exact.value()),
            use_product_range=True,
            product_min=int(self.size_min.value()),
            product_max=int(self.size_max.value()),
            check_genome=self.genome_check.isChecked(),
            annotate=self.annotate_check.isChecked(),
        )
        if saved:
            on_file = str(self.stock_from.currentData()) == "file"
            base.update(
                primer_file=self.primer_file.text().strip() if on_file else "",
                primer_names=[] if on_file else list(self._only_names),
                search_forward=self.search_forward.isChecked(),
                search_reverse=self.search_reverse.isChecked(),
                search_probe=self.search_probe.isChecked(),
            )
        else:
            f, r, p = (box.currentText().strip()
                       for box in (self.forward, self.reverse, self.probe))
            base.update(primer_file="", primer_names=[],
                        use_forward=bool(f), forward=f,
                        use_reverse=bool(r), reverse=r,
                        use_probe=bool(p), probe=p)
        return pj.MapSettings.from_dict(base)

    def _on_save(self) -> None:
        s = self.settings().to_dict()
        s["report"] = self.report_check.isChecked()
        QSettings().setValue(_SETTINGS_KEY, json.dumps(s))
        self.saved_note.setText("Saved.")

    def _on_defaults(self) -> None:
        d = pj.MapSettings()
        self.mismatches.setValue(d.max_mismatches)
        self.exact.setValue(d.three_prime_exact)
        self.size_min.setValue(d.product_min)
        self.size_max.setValue(d.product_max)
        self.pairs_only.setChecked(d.pairs_only)
        self.search_forward.setChecked(d.search_forward)
        self.search_reverse.setChecked(d.search_reverse)
        self.search_probe.setChecked(d.search_probe)
        self.threshold.setCurrentIndex(max(0, self.threshold.findData(d.consensus_threshold)))
        self.ignore_gaps.setChecked(d.consensus_ignore_gaps)
        self.genome_check.setChecked(d.check_genome)
        self.annotate_check.setChecked(d.annotate)
        self.report_check.setChecked(False)
        self._sync_rows()

    def _sync_rows(self) -> None:
        """Show the rows that belong to the choices made above them."""
        saved = str(self.source.currentData()) == pj.MAP_DATABASE
        on_file = str(self.stock_from.currentData()) == "file"
        self.stock_from_row.setVisible(saved)
        self.primer_file_row.setVisible(saved and on_file)
        self.kinds_row.setVisible(saved)
        self.kinds_row2.setVisible(saved)
        self.only_row.setVisible(saved and not on_file and bool(self._only_names))
        if self._only_names:
            self.only_label.setText(f"{len(self._only_names)} chosen in the Database")
        for row in self.rows_specific:
            row.setVisible(not saved)
        consensus = str(self.test_on.currentData()) == pj.TEST_ON_CONSENSUS
        self.threshold_row.setVisible(consensus)
        self.gaps_row.setVisible(consensus)
        self._show_idle()

    def _use_all_saved(self) -> None:
        """Back to the whole Database after the Database sent a selection here."""
        self._only_names = []
        self._sync_rows()

    def _choose_primer_file(self) -> None:
        start = self.primer_file.text().strip() or str(
            self._files[0].parent if self._files else Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Primers FASTA", start,
                                              "FASTA (*.fa *.fasta *.fas *.fna *.txt);;"
                                              "All files (*)")
        if path:
            self.primer_file.setText(path)
            self._show_idle()

    # ------------------------------------------------------------------ inputs

    def tab_name(self) -> str:
        if str(self.source.currentData()) == pj.MAP_DATABASE:
            return "Map · saved primers"
        names = [n for n in (self.forward.currentText().strip(),
                             self.reverse.currentText().strip(),
                             self.probe.currentText().strip()) if n]
        return "Map · " + (" / ".join(names) if names else "primers")

    def set_files(self, files) -> None:
        self._files = [Path(p) for p in files]
        self._fill_primers()
        self._refresh_files()

    def _refresh_files(self) -> None:
        if not self._files:
            self.files_note.setText("No file ticked in Files.")
            return
        names = ", ".join(p.name for p in self._files[:3])
        more = f" and {len(self._files) - 3} more" if len(self._files) > 3 else ""
        self.files_note.setText(f"{len(self._files)} file"
                                f"{'s' if len(self._files) != 1 else ''}: {names}{more}")

    def _saved_primer_count(self) -> int:
        try:
            from repeatviewer.backends.primers.inventory import open_database

            db = open_database(Path(self._database_path) if self._database_path else None)
            return len(db.primers)
        except Exception:  # noqa: BLE001 - no database yet
            return 0

    def _fill_primers(self) -> None:
        """Offer the saved names (and the primers kept with the ticked files)."""
        names: list[str] = []
        try:
            from repeatviewer.backends.primers.inventory import open_database

            db = open_database(Path(self._database_path) if self._database_path else None)
            names = [p.name for p in db.primers]
        except Exception:  # noqa: BLE001 - no database yet
            names = []
        try:
            from repeatviewer.backends.primers.on_sequence import load_sequence_primers

            for path in self._files[:20]:
                names += [p.name for p in load_sequence_primers(path)]
        except Exception:  # noqa: BLE001 - the files may hold none
            pass
        seen: list[str] = []
        for name in names:
            if name and name not in seen:
                seen.append(name)
        for box in (self.forward, self.reverse, self.probe):
            text = box.currentText()
            box.blockSignals(True)
            box.clear()
            box.addItem("")
            for name in seen:
                box.addItem(name)
            box.setCurrentText(text)
            box.blockSignals(False)

    def _apply_primers(self, base: dict) -> None:
        """Fill the typed-in fields from the settings this page was opened with.

        The Database can ask to test what it has selected ("Check a Sequence >
        All settings"): the names arrive in forward / reverse / probe, or in
        primer_names for a search of the stock.
        """
        chosen = [str(base.get(k) or "").strip() for k in ("forward", "reverse", "probe")]
        if not any(chosen) and self._only_names:
            chosen = (list(self._only_names) + ["", "", ""])[:3]
        for box, text in zip((self.forward, self.reverse, self.probe), chosen):
            if not text:
                continue
            box.blockSignals(True)
            if box.findText(text) < 0:
                box.addItem(text)
            box.setCurrentText(text)
            box.blockSignals(False)

    # ------------------------------------------------------------------ run

    def run_map(self) -> None:
        if self._busy:
            return
        if not self._files:
            self._set_verdict("amber", "Tick the FASTA files to test in the Files panel.")
            return
        s = self.settings()
        if s.mode == pj.MAP_SPECIFIC and not (s.forward or s.reverse or s.probe):
            self._set_verdict("amber", "Name at least one primer: a saved name, or a "
                                       "sequence typed 5′→3′.")
            return
        if s.mode == pj.MAP_DATABASE:
            if s.primer_file and not Path(s.primer_file).is_file():
                self._set_verdict("amber", "The primers FASTA does not exist.")
                return
            if not (s.search_forward or s.search_reverse or s.search_probe):
                self._set_verdict("amber", "Tick at least one kind to search for.")
                return
            if not s.primer_file and not self._saved_primer_count():
                self._set_verdict("amber", "No saved primers yet. Add them in the Primer "
                                           "Database, choose a primers FASTA, or switch to "
                                           "These primers and name one.")
                return
        self._busy = True
        self.map_button.setEnabled(False)
        self._set_verdict("", "Looking for binding sites…")
        files = list(self._files)
        database = Path(self._database_path) if self._database_path else None
        relay = self._relay

        def work() -> None:
            try:
                payload, _sites, _products = pj.map_payload(files, s, database_path=database)
            except Exception as exc:  # noqa: BLE001 - shown in the page
                relay.done.emit(None, str(exc))
                return
            relay.done.emit(payload, None)

        threading.Thread(target=work, daemon=True).start()

    def _on_done(self, payload, error) -> None:
        self._busy = False
        self.map_button.setEnabled(True)
        if error:
            self._payload = None
            self._set_verdict("amber", f"Map failed: {error}")
            self.table.setRowCount(0)
            self.picture.set_payload(None)
            return
        self._payload = payload
        self._fill(payload)
        if self.report_check.isChecked():
            self._write_report()

    # ------------------------------------------------------------------ view

    def _set_verdict(self, tone: str, text: str) -> None:
        if tone == "green":
            bg, border, fg = "#E7F6EC", "#9BD3AE", "#14532D"
        elif tone == "amber":
            bg, border, fg = "#FFF4E5", "#E8A33D", "#5A3700"
        else:
            self.verdict.setStyleSheet("")
            self.verdict.setText(text)
            return
        self.verdict.setStyleSheet(
            f"#mapVerdict {{ background: {bg}; border: 1px solid {border};"
            f" border-radius: 6px; padding: 8px; color: {fg}; }}")
        self.verdict.setText(html.escape(text))

    def _show_idle(self) -> None:
        if str(self.source.currentData()) == pj.MAP_DATABASE:
            where = (Path(self.primer_file.text().strip()).name
                     if str(self.stock_from.currentData()) == "file"
                     and self.primer_file.text().strip() else "the Primer Database")
            what = (f"the {len(self._only_names)} primers chosen in the Database"
                    if self._only_names else f"every primer in {where}")
            self._set_verdict("", f"Map searches {what} against the ticked files.")
        else:
            self._set_verdict("", "Name a forward, a reverse or a probe, then press Map.")
        self.picture.set_payload(None)

    def _fill(self, payload: dict) -> None:
        counts = payload.get("counts", {})
        rows: dict[str, dict] = {}
        for t in payload.get("templates", []):
            rows[t["id"]] = {"forward": [], "reverse": [], "sites": 0, "products": [],
                             "mismatches": []}
        for site in payload.get("sites", []):
            row = rows.setdefault(site["record"], {"forward": [], "reverse": [], "sites": 0,
                                                   "products": [], "mismatches": []})
            row["sites"] += 1
            (row["forward"] if site.get("strand", "+") == "+" else row["reverse"]).append(
                int(site["start"]))
            row["mismatches"].append(int(site.get("mismatches", 0)))
        for product in payload.get("products", []):
            rows.setdefault(product["record"], {"forward": [], "reverse": [], "sites": 0,
                                                "products": [], "mismatches": []})
            rows[product["record"]]["products"].append(int(product["size"]))
        self.table.setRowCount(len(rows))
        amber = QColor("#B26B00")
        for r, (rid, row) in enumerate(rows.items()):
            sizes = ", ".join(f"{s:,} bp" for s in sorted(set(row["products"]))[:3]) or "none"
            mism = ("/".join(str(m) for m in sorted(set(row["mismatches"]))) or "–")
            cells = [rid,
                     f"{row['forward'][0]:,}" if row["forward"] else "no site",
                     f"{row['reverse'][0]:,}" if row["reverse"] else "no site",
                     str(row["sites"]), sizes, mism]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if text in ("no site", "none"):
                    item.setForeground(amber)
                self.table.setItem(r, c, item)
        self.picture.set_payload(payload)
        with_product = int(counts.get("sequences_with_product", 0))
        total = int(counts.get("sequences", len(rows)))
        if with_product and with_product == total:
            self._set_verdict("green", f"A product in all {total} sequence"
                                       f"{'s' if total != 1 else ''}: "
                                       f"{counts.get('products', 0)} in total.")
        elif with_product:
            self._set_verdict("amber", f"A product in {with_product} of {total} sequences. "
                                       "The others are in the table.")
        else:
            self._set_verdict("amber", f"No product. {counts.get('sites', 0)} binding site"
                                       f"{'s' if counts.get('sites', 0) != 1 else ''} found.")

    def _write_report(self) -> None:
        if not self._files or self._payload is None:
            return
        try:
            layout = pj.plan_outputs(self._files[0], pj.MAP_TAG, None)
            files = pj.write_result(layout, self._payload)
        except Exception as exc:  # noqa: BLE001 - shown in the page
            self.saved_note.setText(f"Could not write the report: {exc}")
            return
        self.report_path = layout.main
        self.saved_note.setText(f"Report: {layout.main.name}")
        main = self.window()
        show = getattr(main, "_show_new_output", None)
        if show is not None and files:
            show(layout.main)

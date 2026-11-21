"""Cloning as a tab in the middle, with its settings on the right.

The insert, the vector and the method on the right; what comes out of the
ligation in the middle: both orientations, the plasmid, the colony PCR and
the gel a positive colony gives.

Developer: Abdullah Yusuf
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repeatviewer.backends.primers import cloning as cl
from repeatviewer.backends.primers import gel_doc as gd
from repeatviewer.backends.primers import pcr
from repeatviewer.backends.primers import tails as rtail
from repeatviewer.views.cloning_dialog import CLONING_HELP, RESULT_HELP
from repeatviewer.views.sanger_dialog import _read_fasta
from repeatviewer.widgets.help_button import make_help_button
from repeatviewer.widgets.primer_design_pane import (
    FIELD_W, GAP, MiddleElideCombo, _field_path, _row, _rule, _section)

_SETTINGS_KEY = "primers/cloning"
PANEL_W = 330
READ_LENGTH = 700


class CloningPage(QWidget):
    """One ligation: insert into vector, both ways, with the colony PCR."""

    def __init__(self, insert: str = "", *, insert_name: str = "",
                 folder: Path | None = None, features=(),
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = None
        self._insert = str(insert or "").upper()
        self._insert_name = insert_name or "insert"
        self._folder = Path(folder) if folder else Path.cwd()
        self._features = list(features or ())
        self._result = cl.CloneResult()
        saved = self._load()

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
        self.verdict.setObjectName("cloningVerdict")

        # The first box starts right under the section row, as in every
        # section; the "?" of Colony PCR below explains the table too.
        self.table = QTableWidget(0, 4, middle)
        self.table.setHorizontalHeaderLabels(["Orientation", "Insert", "Plasmid", "Colony PCR"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(_card(self.table, middle))

        self.notes = QLabel(middle)
        self.notes.setWordWrap(True)
        self.notes.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.notes)

        gel_head = QHBoxLayout()
        self.gel_title = QLabel("<b>Colony PCR</b>", middle)
        gel_head.addWidget(self.gel_title, 1)
        gel_head.addWidget(make_help_button(middle, "Colony PCR", RESULT_HELP))
        lay.addLayout(gel_head)
        from repeatviewer.widgets.gel_view import GelView

        self.gel = GelView(middle, compact=True)
        self.gel.setMinimumHeight(160)
        lay.addWidget(_card(self.gel, middle), 1)
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
        title.addWidget(QLabel("<b>Cloning</b>", panel), 1)
        title.addWidget(make_help_button(panel, "Cloning", CLONING_HELP))
        pl.addLayout(title)
        pl.addWidget(_rule(panel))

        sec, sl, _ = _section("Insert", panel, "Insert", CLONING_HELP)
        from repeatviewer.widgets.path_browse import PathBrowseRow

        self.insert_path = PathBrowseRow(
            sec, placeholder="Click a FASTA in Files, or Browse",
            browse_title="Insert Sequence",
            file_filter="Sequences (*.fa *.fasta *.fas *.fna *.txt *.seq);;All files (*)",
            browse_below=True, elide_middle=True)
        _field_path(self.insert_path)
        self.insert_path.set_start_dir(str(self._folder))
        sl.addLayout(_row("Sequence", self.insert_path, parent=sec, top=True))
        self.record_combo = MiddleElideCombo(sec)
        self.record_combo.setFixedWidth(FIELD_W)
        sl.addLayout(_row("Record", self.record_combo, parent=sec))
        self.insert_note = QLabel(sec)
        self.insert_note.setWordWrap(True)
        self.insert_note.setStyleSheet("color: palette(placeholder-text);")
        sl.addWidget(self.insert_note)
        pl.addWidget(sec)
        pl.addWidget(_rule(panel))

        sec, sl, _ = _section("Ligation", panel, "Ligation", CLONING_HELP)
        self.vector = QComboBox(sec)
        for v in cl.PRESETS:
            self.vector.addItem(v.name, v.name)
        self.vector.setCurrentIndex(max(0, self.vector.findData(saved.get("vector"))))
        self.vector.setFixedWidth(FIELD_W)
        sl.addLayout(_row("Vector", self.vector, parent=sec))
        self.method = QComboBox(sec)
        self.method.setFixedWidth(FIELD_W)
        sl.addLayout(_row("Method", self.method, parent=sec))
        self.polymerase = QComboBox(sec)
        for name in pcr.POLYMERASES:
            self.polymerase.addItem(name, name)
        self.polymerase.setCurrentIndex(max(0, self.polymerase.findData(saved.get("polymerase"))))
        self.polymerase.setFixedWidth(FIELD_W)
        sl.addLayout(_row("Polymerase", self.polymerase, parent=sec))
        self.left = QComboBox(sec)
        self.right = QComboBox(sec)
        for box in (self.left, self.right):
            box.addItem("none", "")
            for name in rtail.TAIL_ENZYMES:
                box.addItem(name, name)
            box.setFixedWidth((FIELD_W - GAP) // 2)
        self.enzyme_row = QWidget(sec)
        er = QVBoxLayout(self.enzyme_row)
        er.setContentsMargins(0, 0, 0, 0)
        er.setSpacing(0)
        er.addLayout(_row("Enzymes", self.left, self.right, parent=self.enzyme_row))
        sl.addWidget(self.enzyme_row)
        pl.addWidget(sec)
        pl.addWidget(_rule(panel))

        sec, sl, _ = _section("Your vector", panel, "Your vector", CLONING_HELP)
        self.vector_length = QSpinBox(sec)
        self.vector_length.setRange(0, 1_000_000)
        self.vector_length.setSuffix(" bp")
        self.vector_length.setGroupSeparatorShown(True)
        self.vector_length.setFixedWidth(FIELD_W)
        sl.addLayout(_row("Length", self.vector_length, parent=sec))
        self.empty_product = QSpinBox(sec)
        self.empty_product.setRange(0, 100_000)
        self.empty_product.setSuffix(" bp")
        self.empty_product.setGroupSeparatorShown(True)
        self.empty_product.setValue(int(saved.get("empty_product", 0)))
        self.empty_product.setFixedWidth(FIELD_W)
        sl.addLayout(_row("Empty PCR", self.empty_product, parent=sec))
        pl.addWidget(sec)
        pl.addWidget(_rule(panel))

        sec, sl, _ = _section("Options", panel, "Options", CLONING_HELP)
        self.gel_button = QPushButton("Gel", sec)
        self.gel_button.setToolTip("Save the colony PCR gel")
        self.report_button = QPushButton("Report", sec)
        self.report_button.setToolTip("Save a report of this cloning plan")
        # side by side in the field column, together as wide as a field
        from repeatviewer.widgets.primer_design_pane import _field_buttons

        sl.addLayout(_field_buttons(sec, self.gel_button, self.report_button, label="Save"))
        self.saved_note = QLabel("", sec)
        self.saved_note.setWordWrap(True)
        self.saved_note.setStyleSheet("color: palette(placeholder-text);")
        sl.addWidget(self.saved_note)
        pl.addWidget(sec)
        pl.addStretch(1)
        outer.addWidget(_scroll_panel(panel, self))

        self.insert_path.path_changed.connect(self._on_pick_insert)
        self.record_combo.currentIndexChanged.connect(self._on_record)
        self._show_record()     # a sequence handed over when the page opens
        self.vector.currentIndexChanged.connect(self._on_vector)
        for box in (self.method, self.polymerase, self.left, self.right):
            box.currentIndexChanged.connect(self.recompute)
        for spin in (self.vector_length, self.empty_product):
            spin.valueChanged.connect(self.recompute)
        self.gel_button.clicked.connect(self._on_gel)
        self.report_button.clicked.connect(self._on_report)
        self._on_vector()

    # ------------------------------------------------------------------ settings

    def _load(self) -> dict:
        raw = QSettings().value(_SETTINGS_KEY, "")
        try:
            d = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            d = {}
        return d if isinstance(d, dict) else {}

    def _save(self) -> None:
        QSettings().setValue(_SETTINGS_KEY, json.dumps(
            {"vector": self.vector.currentData(), "method": self.method.currentData(),
             "polymerase": self.polymerase.currentData(),
             "empty_product": int(self.empty_product.value())}))

    def tab_name(self) -> str:
        return f"Cloning · {self._insert_name}"

    def vector_preset(self) -> cl.Vector:
        return cl.preset(str(self.vector.currentData()))

    def _on_vector(self, *_a) -> None:
        v = self.vector_preset()
        saved = self._load().get("method")
        self.method.blockSignals(True)
        self.method.clear()
        for m in v.methods:
            self.method.addItem(cl.METHOD_LABELS[m], m)
        i = self.method.findData(saved)
        self.method.setCurrentIndex(i if i >= 0 else 0)
        self.method.blockSignals(False)
        own = v.length == 0
        self.vector_length.setEnabled(own)
        if not own:
            self.vector_length.setValue(v.length)
        self.recompute()

    # ------------------------------------------------------------------ insert

    def set_insert(self, sequence: str, name: str = "", features=()) -> None:
        self._insert = str(sequence or "").upper()
        if name:
            self._insert_name = name
        self._features = list(features or ())
        self._show_record()
        self.recompute()

    def _show_record(self) -> None:
        """Record names the insert, also when it came from the open sequence
        and not from a file picked here."""
        combo = self.record_combo
        if not self._insert:
            return
        for i in range(combo.count()):
            data = combo.itemData(i)
            if data and data[0] == self._insert_name and data[1].upper() == self._insert:
                if combo.currentIndex() != i:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(i)
                    combo.blockSignals(False)
                return
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(f"{self._insert_name} ({len(self._insert):,} bp)",
                      (self._insert_name, self._insert))
        combo.blockSignals(False)
        combo.setToolTip(combo.currentText())

    def _on_pick_insert(self) -> None:
        path = self.insert_path.path()
        if path is None or not Path(path).is_file():
            return
        records = _read_fasta(Path(path))
        if not records:
            self.verdict.setText("That file holds no sequence.")
            return
        self._folder = Path(path).parent
        self.record_combo.blockSignals(True)
        self.record_combo.clear()
        for name, seq in records:
            self.record_combo.addItem(f"{name} ({len(seq):,} bp)", (name, seq))
        self.record_combo.setCurrentIndex(0)
        self.record_combo.blockSignals(False)
        self.set_insert(records[0][1], records[0][0])

    def _on_record(self, index: int) -> None:
        data = self.record_combo.itemData(index)
        if data:
            self.set_insert(data[1], data[0])

    # ------------------------------------------------------------------ result

    def recompute(self, *_a) -> None:
        v = self.vector_preset()
        method = str(self.method.currentData() or cl.METHOD_TA)
        self.enzyme_row.setVisible(method == cl.METHOD_RE)
        if v.length == 0:
            v = cl.Vector(v.name, int(self.vector_length.value()), v.methods, v.primers, v.note)
        self._result = cl.plan(
            self._insert, v, method,
            enzymes=(str(self.left.currentData() or ""), str(self.right.currentData() or "")),
            polymerase=str(self.polymerase.currentData() or ""),
            empty_product=int(self.empty_product.value()), features=self._features)
        self._save()
        self._show(v, method)

    def _show(self, vector: cl.Vector, method: str) -> None:
        n = len(self._insert)
        self.insert_note.setText(f"{html.escape(self._insert_name)}, {n:,} bp" if n
                                 else "No insert yet: press Choose.")
        tone, line = cl.summary(self._result, vector, method)
        bg, border, fg = (("#E7F6EC", "#9BD3AE", "#14532D") if tone == "green"
                          else ("#FFF4E5", "#E8A33D", "#5A3700"))
        self.verdict.setStyleSheet(
            f"#cloningVerdict {{ background: {bg}; border: 1px solid {border};"
            f" border-radius: 6px; padding: 8px; color: {fg}; }}")
        self.verdict.setText(line)

        clones = self._result.clones
        if method == cl.METHOD_RE:
            left, right = self.left.currentData(), self.right.currentData()
            if left and right and left != right:
                clones = clones[:1]
        self.table.setRowCount(len(clones))
        for r, c in enumerate(clones):
            cells = [c.label(), f"{c.insert_length:,} bp",
                     f"{c.total_length:,} bp" if c.total_length else "give the vector length",
                     f"{c.colony_product:,} bp" if c.colony_product else "give the empty product"]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if "give the" in text:
                    item.setForeground(QColor("#8a4b00"))
                self.table.setItem(r, col, item)
        rows = sum(self.table.rowHeight(r) for r in range(self.table.rowCount()))
        self.table.setFixedHeight(self.table.horizontalHeader().height() + rows + 6)

        bits = [f"<span style='color:#8a4b00'>{html.escape(w)}.</span>"
                for w in self._result.warnings[1:]]
        bits += [html.escape(t) + "." for t in self._result.notes]
        if vector.note:
            bits.append(html.escape(vector.note))
        if self._result.empty_product and self._insert:
            reach = cl.reads_into_insert(self._result.empty_product, READ_LENGTH)
            names = ", ".join(p.name for p in vector.primers)
            covered = ("the whole insert" if reach >= len(self._insert)
                       else f"about {reach:,} bp of it from each side")
            bits.append(f"Sequencing primers: {html.escape(names)}. A {READ_LENGTH} base read "
                        f"covers {covered}.")
        self.notes.setText("<br>".join(bits))

        doc = cl.colony_gel(self._result, title=f"{self._insert_name} colony PCR")
        self.gel.set_doc(doc)
        self.gel_title.setText(
            "<b>Colony PCR</b>" if doc is not None else
            "<b>Colony PCR</b> &nbsp;<span style='color:gray'>give the empty-vector product"
            " to see the gel</span>")
        self.gel_button.setEnabled(doc is not None)
        self.report_button.setEnabled(bool(self._insert))

    # ------------------------------------------------------------------ files

    def _safe_name(self) -> str:
        return "".join(c if c.isalnum() or c in "-_." else "_" for c in self._insert_name)[:40]

    def _free_path(self, suffix: str) -> Path:
        base = self._safe_name() or "clone"
        out = self._folder / f"{base}{suffix}"
        n = 2
        while out.exists():
            out = self._folder / f"{base}_{n}{suffix}"
            n += 1
        return out

    def _show_output(self, path: Path) -> None:
        main = self.window()
        show = getattr(main, "_show_new_output", None)
        if show is not None:
            show(path)

    def _on_gel(self) -> None:
        doc = cl.colony_gel(self._result, title=f"{self._safe_name()} colony PCR")
        if doc is None:
            return
        out = self._free_path(gd.GEL_SUFFIX)
        try:
            doc.save(out)
        except OSError as exc:
            self.saved_note.setText(f"Could not write the gel: {exc}")
            return
        self.gel_path = out
        self.saved_note.setText(f"Gel: {out.name}")
        self._show_output(out)

    def _on_report(self) -> None:
        out = self._free_path("_cloning.html")
        try:
            cl.write_report(out, self._insert_name, self._result, self.vector_preset(),
                            str(self.method.currentData()))
        except OSError as exc:
            self.saved_note.setText(f"Could not write the report: {exc}")
            return
        self.report_path = out
        self.saved_note.setText(f"Report: {out.name}")
        self._show_output(out)

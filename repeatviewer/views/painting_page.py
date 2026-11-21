"""Chromosome painting probes as a tab in the middle, settings on the right.

Chorus2 runs over a whole genome, so this is not about the open sequence: the
page shows the probes it produced, chromosome by chromosome, and keeps every
Chorus2, selection and ordering setting in its panel.

Developer: Abdullah Yusuf
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from PySide6.QtCore import QRectF, QSettings, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repeatviewer.backends.primers import painting as pt
from repeatviewer.widgets.help_button import make_help_button
from repeatviewer.widgets.path_browse import PathBrowseRow
from repeatviewer.widgets.primer_design_pane import (
    BOX2_W,
    FIELD_W,
    LABEL_W,
    _field_path,
    _row,
    _rule,
    _section,
    _spin,
)

_SETTINGS_KEY = "primers/painting_page"
PANEL_W = 330
MAX_DRAWN = 24

SOURCE_HELP = (
    "<b>Run Chorus2 here</b> needs Chorus2 in a conda environment on this computer and a "
    "genome FASTA.<br>"
    "<b>Import a Chorus2 BED</b> takes the probes from a run made elsewhere, on a server, "
    "and does the selection and ordering here."
)
CHORUS_HELP = (
    "What Chorus2 is told. <b>Probe length</b> is the oligo size; <b>Max homology</b> and "
    "<b>Min dTm</b> decide how unique a probe has to be; <b>k-mer step</b> is how finely the "
    "genome is walked. <b>Ploidy</b> matters for the coverage it expects."
)
POOL_HELP = (
    "Which of the probes to keep. <b>Min gap</b> spreads them out, <b>Amount</b> takes all "
    "of them, a density per kb, or a fixed pool size. <b>Regions</b> limits the pool to "
    "chromosomes or stretches, for example <i>chr1, chr2:1-5000000</i>."
)
ORDER_HELP = (
    "What goes to the supplier: the pool name, and the adapters added to every oligo."
)
PICTURE_HELP = (
    "Where the probes sit on each chromosome. A darker band means more probes in that "
    f"stretch. The first {MAX_DRAWN} chromosomes are drawn."
)


class ProbePicture(QWidget):
    """Probe density along each chromosome."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[tuple[str, int, list[int]]] = []
        self.setMinimumHeight(80)

    def set_probes(self, probes) -> None:
        by_chrom: dict[str, list] = {}
        for probe in probes or []:
            by_chrom.setdefault(probe.chrom, []).append(probe)
        self._rows = []
        for chrom, items in list(by_chrom.items())[:MAX_DRAWN]:
            length = max(p.end for p in items)
            self._rows.append((chrom, length, [p.start for p in items]))
        self.setMinimumHeight(24 + 28 * max(1, len(self._rows)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self._rows:
            painter.setPen(QColor("#6b7280"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "No probes yet: run Chorus2, or import its BED.")
            painter.end()
            return
        font = painter.font()
        font.setPointSizeF(max(7.5, font.pointSizeF() * 0.82))
        painter.setFont(font)
        name_w, count_w = 110.0, 90.0
        left = name_w + 8
        right = max(left + 60, self.width() - count_w - 8)
        span = right - left
        longest = max(length for _c, length, _s in self._rows) or 1
        y = 16.0
        bins = 160
        for chrom, length, starts in self._rows:
            width = span * length / longest
            painter.setPen(QColor("#3A3A3C"))
            painter.drawText(QRectF(0, y - 7, name_w, 14),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             str(chrom)[:18])
            painter.fillRect(QRectF(left, y - 6, width, 12), QColor("#ECECEE"))
            counts = [0] * bins
            for start in starts:
                i = min(bins - 1, int(bins * (start - 1) / max(1, length)))
                counts[i] += 1
            top = max(counts) or 1
            for i, count in enumerate(counts):
                if not count:
                    continue
                shade = QColor("#1F57C3")
                shade.setAlpha(60 + int(195 * count / top))
                painter.fillRect(QRectF(left + width * i / bins, y - 6,
                                        max(1.0, width / bins), 12), shade)
            painter.setPen(QColor("#5A5D63"))
            painter.drawText(QRectF(right + 6, y - 7, count_w, 14),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f"{len(starts):,} probes")
            y += 28
        painter.end()


class PaintingPage(QWidget):
    """Chromosome painting: the probes in the middle, every setting on the right."""

    def __init__(self, *, options=None, start_job=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = None
        self._options = options
        self._start_job = start_job
        self._probes: list = []
        saved = dict(getattr(options, "painting", None) or {}) or self._load()
        ps = pt.PaintingSettings.from_dict(saved)
        if "source" not in (saved or {}):
            # Nothing chosen yet: most users bring a BED that Chorus2 already made.
            import dataclasses

            ps = dataclasses.replace(ps, source=pt.SOURCE_IMPORT)

        from repeatviewer.widgets.primer_design_pane import _card, _results_surface

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        middle = QWidget(self)
        lay = QVBoxLayout(middle)
        lay.setContentsMargins(12, 6, 12, 12)
        lay.setSpacing(10)
        from repeatviewer.widgets.primer_design_pane import VerdictLabel

        self.verdict = VerdictLabel(middle)
        self.verdict.setObjectName("paintingVerdict")

        self.table = QTableWidget(0, 4, middle)
        self.table.setHorizontalHeaderLabels(["Chromosome", "Probes", "Per Mb", "Length"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        head = self.table.horizontalHeader()
        head.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c, w in ((1, 110), (2, 90), (3, 130)):
            self.table.setColumnWidth(c, w)
        self.table.setMinimumHeight(120)
        lay.addWidget(_card(self.table, middle))

        pic_head = QHBoxLayout()
        pic_head.addWidget(QLabel("<b>Where the probes sit</b>", middle), 1)
        pic_head.addWidget(make_help_button(middle, "Where the probes sit", PICTURE_HELP))
        lay.addLayout(pic_head)
        self.picture = ProbePicture(middle)
        lay.addWidget(_card(self.picture, middle), 1)
        lay.addWidget(self.verdict)     # under the boxes, when there is one
        _results_surface(middle)
        from repeatviewer.widgets.primer_design_pane import _scroll_middle

        outer.addWidget(_scroll_middle(middle, self), 1)

        panel = QWidget(self)
        inner = QWidget(panel)
        pl = QVBoxLayout(inner)
        pl.setContentsMargins(10, 6, 10, 8)
        pl.setSpacing(6)
        title = QHBoxLayout()
        title.addWidget(QLabel("<b>Chromosome Painting</b>", inner), 1)
        title.addWidget(make_help_button(inner, "Chromosome painting", SOURCE_HELP))
        pl.addLayout(title)
        pl.addWidget(_rule(inner))

        sec, sl, _ = _section("Probes from", inner, "Probes from", SOURCE_HELP)
        self.source = QComboBox(sec)
        self.source.addItem("Import a Chorus2 BED", pt.SOURCE_IMPORT)
        self.source.addItem("Run Chorus2 here", pt.SOURCE_RUN)
        self.source.setFixedWidth(FIELD_W)
        self.source.setCurrentIndex(max(0, self.source.findData(ps.source)))
        sl.addLayout(_row("Source", self.source, parent=sec))
        self.genome = PathBrowseRow(
            sec, initial=ps.genome_fasta or None, placeholder="Genome FASTA",
            browse_title="Genome FASTA", file_filter="FASTA (*.fa *.fasta *.fna);;All files (*)",
            browse_below=True, elide_middle=True)
        _field_path(self.genome)
        self.genome_row = _row("Genome", self.genome, parent=sec, top=True)
        sl.addLayout(self.genome_row)
        self.bed = PathBrowseRow(
            sec, initial=ps.import_bed or None, placeholder="Chorus2 BED",
            browse_title="Chorus2 BED", file_filter="BED (*.bed);;All files (*)",
            browse_below=True, elide_middle=True)
        _field_path(self.bed)
        self.bed_row = _row("Chorus2 BED", self.bed, parent=sec, top=True)
        sl.addLayout(self.bed_row)
        pl.addWidget(sec)
        pl.addWidget(_rule(inner))

        sec, sl, _ = _section("Chorus2", inner, "Chorus2", CHORUS_HELP)
        self.length = _spin(30, 100, ps.length, suffix=" nt", parent=sec)
        sl.addLayout(_row("Probe length", self.length, parent=sec))
        self.homology = _spin(50, 100, ps.homology, decimals=1, suffix=" %", parent=sec)
        sl.addLayout(_row("Max homology", self.homology, parent=sec))
        self.dtm = _spin(0, 37, ps.dtm, decimals=1, suffix=" °C", parent=sec)
        sl.addLayout(_row("Min dTm", self.dtm, parent=sec))
        self.step = _spin(1, 100, ps.step, suffix=" bp", parent=sec)
        sl.addLayout(_row("k-mer step", self.step, parent=sec))
        self.ploidy = _spin(1, 12, ps.ploidy, parent=sec)
        sl.addLayout(_row("Ploidy", self.ploidy, parent=sec))
        self.threads = _spin(1, 256, ps.threads, parent=sec)
        sl.addLayout(_row("Threads", self.threads, parent=sec))
        self.env = QLineEdit(ps.conda_env, sec)
        self.env.setPlaceholderText(pt.DEFAULT_ENV)
        self.env.setFixedWidth(FIELD_W)
        sl.addLayout(_row("Conda env", self.env, parent=sec))
        self.chorus_note = QLabel(sec)
        self.chorus_note.setWordWrap(True)
        self.chorus_note.setStyleSheet("color: palette(placeholder-text);")
        sl.addWidget(self.chorus_note)
        self.chorus_section = sec
        self.chorus_rule = _rule(inner)
        pl.addWidget(sec)
        pl.addWidget(self.chorus_rule)

        sec, sl, _ = _section("Pool", inner, "Pool", POOL_HELP)
        self.spacing = _spin(0, 100_000, ps.spacing, suffix=" bp", parent=sec)
        sl.addLayout(_row("Min gap", self.spacing, parent=sec))
        self.strand = QComboBox(sec)
        self.strand.addItem("Both (alternate)", pt.STRAND_BOTH)
        self.strand.addItem("Plus strand only", pt.STRAND_PLUS)
        self.strand.setFixedWidth(FIELD_W)
        self.strand.setCurrentIndex(max(0, self.strand.findData(ps.strand)))
        sl.addLayout(_row("Strand", self.strand, parent=sec))
        self.target = QComboBox(sec)
        self.target.addItem("All probes", pt.TARGET_ALL)
        self.target.addItem("Density per kb", pt.TARGET_DENSITY)
        self.target.addItem("Pool size", pt.TARGET_POOL)
        self.target.setFixedWidth(FIELD_W)
        self.target.setCurrentIndex(max(0, self.target.findData(ps.target)))
        sl.addLayout(_row("Amount", self.target, parent=sec))
        self.density = _spin(0.01, 100, ps.density_per_kb, decimals=2, suffix=" per kb",
                             parent=sec)
        self.density_row = QWidget(sec)
        dr = QVBoxLayout(self.density_row)
        dr.setContentsMargins(0, 0, 0, 0)
        dr.setSpacing(0)
        dr.addLayout(_row("Density", self.density, parent=self.density_row))
        sl.addWidget(self.density_row)
        self.pool = _spin(1, 10_000_000, ps.pool_size, parent=sec, width=BOX2_W)
        self.pool_row = QWidget(sec)
        pr = QVBoxLayout(self.pool_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.setSpacing(0)
        pr.addLayout(_row("Pool size", self.pool, parent=self.pool_row))
        sl.addWidget(self.pool_row)
        self.regions = QLineEdit(ps.regions, sec)
        self.regions.setPlaceholderText("All; or chr1, chr2:1-5000000")
        self.regions.setClearButtonEnabled(True)
        self.regions.setFixedWidth(FIELD_W)
        sl.addLayout(_row("Regions", self.regions, parent=sec))
        pl.addWidget(sec)
        pl.addWidget(_rule(inner))

        sec, sl, _ = _section("Order", inner, "Order", ORDER_HELP)
        self.pool_name = QLineEdit(ps.pool_name, sec)
        self.pool_name.setFixedWidth(FIELD_W)
        sl.addLayout(_row("Pool name", self.pool_name, parent=sec))
        self.primer5 = QLineEdit(ps.primer5, sec)
        self.primer5.setPlaceholderText("None")
        self.primer5.setFixedWidth(FIELD_W)
        sl.addLayout(_row("5′ adapter", self.primer5, parent=sec))
        self.primer3 = QLineEdit(ps.primer3, sec)
        self.primer3.setPlaceholderText("None")
        self.primer3.setFixedWidth(FIELD_W)
        sl.addLayout(_row("3′ adapter", self.primer3, parent=sec))
        pl.addWidget(sec)
        pl.addWidget(_rule(inner))

        sec, sl, _ = _section("Options", inner, "Options", SOURCE_HELP)
        self.ngs = QCheckBox("Score probes with genomic reads", sec)
        self.ngs.setChecked(bool(ps.use_ngs))
        sl.addLayout(_row("", self.ngs, parent=sec))
        self.defaults_button = QPushButton("Restore Defaults", sec)
        self.save_button = QPushButton("Save", sec)
        self.run_button = QPushButton("Run", sec)
        self.run_button.setDefault(True)
        # in the field column: one button as wide as a field, then two halves
        from repeatviewer.widgets.primer_design_pane import _field_buttons

        sl.addLayout(_field_buttons(sec, self.defaults_button))
        sl.addLayout(_field_buttons(sec, self.save_button, self.run_button))
        self.saved_note = QLabel("", sec)
        self.saved_note.setWordWrap(True)
        self.saved_note.setStyleSheet("color: palette(placeholder-text);")
        sl.addWidget(self.saved_note)
        pl.addWidget(sec)
        pl.addStretch(1)

        area = QScrollArea(panel)
        area.setWidget(inner)
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        wrap = QVBoxLayout(panel)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addWidget(area)
        panel.setFixedWidth(PANEL_W)
        outer.addWidget(panel)

        self.source.currentIndexChanged.connect(self._apply_source)
        self.target.currentIndexChanged.connect(self._apply_amount)
        self.bed.path_changed.connect(self._load_bed)
        self.env.editingFinished.connect(self._check_chorus)
        self.run_button.clicked.connect(self._on_run)
        self.save_button.clicked.connect(self._on_save)
        self.defaults_button.clicked.connect(self._on_defaults)
        self._apply_source()
        self._apply_amount()
        self._check_chorus()
        self._show_probes()

    # ------------------------------------------------------------------ settings

    def _load(self) -> dict:
        raw = QSettings().value(_SETTINGS_KEY, "")
        try:
            d = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            d = {}
        return d if isinstance(d, dict) else {}

    def tab_name(self) -> str:
        return "Painting Probes"

    def settings(self) -> pt.PaintingSettings:
        return pt.PaintingSettings(
            source=str(self.source.currentData()),
            genome_fasta=str(self.genome.path() or ""),
            import_bed=str(self.bed.path() or ""),
            conda_env=self.env.text().strip() or pt.DEFAULT_ENV,
            threads=int(self.threads.value()), length=int(self.length.value()),
            homology=float(self.homology.value()), dtm=float(self.dtm.value()),
            step=int(self.step.value()), ploidy=int(self.ploidy.value()),
            use_ngs=self.ngs.isChecked(),
            spacing=int(self.spacing.value()), strand=str(self.strand.currentData()),
            target=str(self.target.currentData()),
            density_per_kb=float(self.density.value()), pool_size=int(self.pool.value()),
            regions=self.regions.text().strip(), primer5=self.primer5.text().strip(),
            primer3=self.primer3.text().strip(),
            pool_name=self.pool_name.text().strip() or "Pool1")

    def _on_save(self) -> None:
        QSettings().setValue(_SETTINGS_KEY, json.dumps(self.settings().to_dict()))
        self.saved_note.setText("Saved.")

    def _on_defaults(self) -> None:
        d = pt.PaintingSettings()
        self.length.setValue(d.length)
        self.homology.setValue(d.homology)
        self.dtm.setValue(d.dtm)
        self.step.setValue(d.step)
        self.ploidy.setValue(d.ploidy)
        self.threads.setValue(d.threads)
        self.spacing.setValue(d.spacing)
        self.density.setValue(d.density_per_kb)
        self.pool.setValue(d.pool_size)
        self.regions.setText(d.regions)
        self.ngs.setChecked(d.use_ngs)

    # ------------------------------------------------------------------ view

    def _apply_source(self) -> None:
        run = str(self.source.currentData()) == pt.SOURCE_RUN
        for item in (self.genome_row,):
            for i in range(item.count()):
                w = item.itemAt(i).widget()
                if w is not None:
                    w.setVisible(run)
        for i in range(self.bed_row.count()):
            w = self.bed_row.itemAt(i).widget()
            if w is not None:
                w.setVisible(not run)
        self.chorus_section.setVisible(run)
        self.chorus_rule.setVisible(run)
        self.run_button.setText("Run" if run else "Select")
        self._show_probes()

    def _apply_amount(self) -> None:
        target = str(self.target.currentData())
        self.density_row.setVisible(target == pt.TARGET_DENSITY)
        self.pool_row.setVisible(target == pt.TARGET_POOL)

    def _check_chorus(self) -> None:
        if str(self.source.currentData()) != pt.SOURCE_RUN:
            self.chorus_note.setText("")
            return
        try:
            inst = pt.find_chorus2(self.env.text().strip() or pt.DEFAULT_ENV)
            self.chorus_note.setText(inst.message)
        except Exception as exc:  # noqa: BLE001 - only a hint
            self.chorus_note.setText(str(exc))

    def _load_bed(self) -> None:
        path = str(self.bed.path() or "")
        if not path:
            self._probes = []
            self._show_probes()
            return
        try:
            self._probes = pt.parse_probe_bed(Path(path))
        except Exception as exc:  # noqa: BLE001 - shown in the page
            self._probes = []
            self._set_verdict("amber", str(exc))
            return
        self._show_probes()

    def set_probes(self, probes) -> None:
        self._probes = list(probes or [])
        self._show_probes()

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
            f"#paintingVerdict {{ background: {bg}; border: 1px solid {border};"
            f" border-radius: 6px; padding: 8px; color: {fg}; }}")
        self.verdict.setText(html.escape(text))

    def _show_probes(self) -> None:
        by_chrom: dict[str, list] = {}
        for probe in self._probes:
            by_chrom.setdefault(probe.chrom, []).append(probe)
        self.table.setRowCount(len(by_chrom))
        for r, (chrom, items) in enumerate(by_chrom.items()):
            length = max(p.end for p in items)
            per_mb = 1_000_000.0 * len(items) / max(1, length)
            for c, text in enumerate((chrom, f"{len(items):,}", f"{per_mb:.1f}",
                                      f"{length:,} bp")):
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.picture.set_probes(self._probes)
        if self._probes:
            self._set_verdict("green", f"{len(self._probes):,} probes on {len(by_chrom)} "
                                       f"chromosome{'s' if len(by_chrom) != 1 else ''}.")
        elif str(self.source.currentData()) == pt.SOURCE_RUN:
            self._set_verdict("", "Choose the genome and press Run. Chorus2 takes hours on a "
                                  "whole genome.")
        else:
            self._set_verdict("", "Choose the Chorus2 BED from your server run.")

    def _on_run(self) -> None:
        if self._start_job is None:
            self.saved_note.setText("The painting job cannot be started from here.")
            return
        self._on_save()
        self._start_job(self.settings().to_dict())

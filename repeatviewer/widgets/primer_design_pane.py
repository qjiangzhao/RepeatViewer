"""Design tab of the primer workbench (Primers rail, beside the sequence).

Region from the map selection (or typed), Amplify / Inside / Avoid, the main
conditions, Design on the open sequence, candidates to tick and keep. Ladder,
FISH and multi-file design stay in the Design window ("Design Window…").

Developer: Abdullah Yusuf
"""

from __future__ import annotations

import json
import threading

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repeatviewer.backends.primers import design as dz
from repeatviewer.backends.primers import workbench as wb
from repeatviewer.widgets.help_button import make_help_button

_SETTINGS_KEY = "primers/workbench_design"
RUN_THIS = "this"
RUN_FILES = "files"

# One grid for every panel of the Primers rail: a label column and a field
# column of fixed width. Whatever sits in the field column fills it edge to
# edge, so the left edges line up when the user switches tabs.
#   three boxes: 3 * BOX3_W + 2 * GAP3   = FIELD_W (min, opt, max in a header)
#   two boxes:   2 * BOX2_W + JOIN2_W     = FIELD_W
#   one box:     BOX2_W + JOIN2_W (the unit) stays on the same left edge
# wide enough for the longest label ("Max homology") with its last letter whole
LABEL_W = 90
# The label and field columns together fill the panel (330 px wide) up to the
# help buttons, also when a scroll bar is shown.
FIELD_W = 198
BOX3_W = 64
GAP3 = 3
BOX2_W = 84
JOIN2_W = 26
# two equal buttons over the label and field columns
HALF_ROW_W = (LABEL_W + 2 + FIELD_W - 6) // 2
GAP = 2
# Older name, kept so nothing outside breaks.
BOX_W = BOX2_W
JOIN_W = JOIN2_W

REGION_HELP = (
    "<b>Region</b>: drag on the map (or the bases) and the range appears here, or type it.<br>"
    "<b>Amplify</b>: primers sit outside the region and the product covers all of it.<br>"
    "<b>Inside</b>: both primers and the product stay inside the region.<br>"
    "<b>Avoid</b>: no primer may sit in the region (a SNP, a methylated site, a repeat).<br>"
    "For probes only Inside and Avoid are offered: a probe sits in the region or keeps "
    "out of it.<br>"
    "When the region and the settings cannot work together, an amber note says why "
    "and offers the settings that fit. Nothing is blocked."
)
RUN_ON_HELP = (
    "<b>Open sequence</b>: the open sequence. The design runs here, the candidates appear in the "
    "list under the map and nothing is written until you press Keep Ticked or Open Report.<br>"
    "<b>Selected files</b>: every FASTA ticked in the Files panel. That is the long run: "
    "the progress bar, the report files beside the inputs, and the usual file colours. "
    "Both use exactly the settings on this page."
)
ADVANCED_HELP = (
    "Primer3's finer rules and the salt the Tm is calculated for. The defaults suit most "
    "PCR; change them when a template is unusual.<br>"
    "<b>Max poly-X</b>: longest run of one base allowed in a primer.<br>"
    "<b>GC clamp</b>: how many G or C bases the 3′ end must have.<br>"
    "<b>Max 3′ stability</b>: largest −ΔG (kcal/mol) of the last five bases.<br>"
    "<b>Probe</b>: size and Tm of the hydrolysis probe, when one is picked.<br>"
    "<b>Na, Mg, dNTP</b>: the reaction the Tm is worked out for."
)
CROSS_HELP = (
    "<b>Min coverage</b>: the share of the copies in this file a probe has to match.<br>"
    "<b>Mismatches</b>: how many are tolerated when counting a match.<br>"
    "<b>Avoid file</b>: a FASTA of the other families. A probe matching any of them is "
    "dropped, so the signal stays on one array.<br>"
    "<b>Leave out low-complexity</b>: simple repeats and inverted repeats are skipped; they "
    "give smeared signal."
)
HYB_HELP = (
    "Your hybridisation mix and stringent wash. The probe Tm is worked out for these "
    "conditions (0.60 °C less per % formamide, Hutton 1977), not for PCR salt, so the "
    "numbers can be compared with the bench protocol.<br>"
    "A probe whose Tm in the wash is below the wash temperature melts off and is dropped."
)
OPTIONS_HELP = (
    "What happens when a run on the selected files finishes.<br>"
    "Right-clicking a FASTA in the Files panel always runs Design with the settings saved "
    "here, so press <b>Save</b> after changing them."
)
SETTINGS_HELP = (
    "<b>Mode</b>: Standard PCR or qPCR (short products). Ladder PCR and FISH probes, and "
    "design on many files, are in the Design window.<br>"
    "<b>Size</b>, <b>Tm</b>: min, optimum and max of each primer.<br>"
    "<b>Product</b>: shortest and longest product.<br>"
    "GC, tails and the salt conditions come from the Design window (Design Window…)."
)
CANDIDATES_HELP = (
    "Pairs Primer3 found around the region, best first. Click a pair to see its product on "
    "the sequence. Tick the pairs to keep and press <b>Keep Ticked</b>: they are added to "
    "this sequence's primers (Primer tab). Nothing is written before that.<br>"
    "<b>Open Report</b> writes the usual primer report (…_primers.html) for this run."
)


class _Relay(QObject):
    done = Signal(object, object)   # Primer3Run | None, error text | None


def _section(title: str, parent: QWidget, help_title: str, help_text: str):
    box = QWidget(parent)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    head = QHBoxLayout()
    head.setContentsMargins(0, 0, 0, 0)
    lab = QLabel(f"<b>{title}</b>", box)
    head.addWidget(lab, 1)
    head.addWidget(make_help_button(box, help_title, help_text))
    lay.addLayout(head)
    return box, lay, lab


def _row(label: str, *widgets, parent: QWidget, joins=(), label_w: int = LABEL_W,
         unit: str = "", cells: bool = False, top: bool = False) -> QHBoxLayout:
    """One grid row: the label column, then widgets filling the field column.

    ``joins`` are the small words between the boxes ("opt", "max", "to"); their
    width follows the number of boxes, so every row ends at the same place.
    ``unit`` is a trailing word ("°C", "reads") in a join-sized column.
    ``cells`` puts two boxes in the min and max columns of a three-box row,
    with the join word in the middle column.
    """
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(GAP)
    lab = QLabel(label, parent)
    lab.setFixedWidth(label_w)
    lab.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    if not label and widgets and all(isinstance(w, QCheckBox) for w in widgets):
        # A tick box with its own text starts at the left edge, under the labels.
        lab.hide()
    elif top:
        # A field with Browse under it: the label sits beside the field, not
        # half way down between the field and the button.
        lab.setContentsMargins(0, 3, 0, 0)
        row.addWidget(lab, 0, Qt.AlignmentFlag.AlignTop)
    else:
        row.addWidget(lab)
    if len(widgets) >= 3 or cells:
        row.setSpacing(GAP3)
    join_w = BOX3_W if cells else JOIN2_W
    for i, w in enumerate(widgets):
        if i and i - 1 < len(joins) and joins[i - 1]:
            j = QLabel(joins[i - 1], parent)
            j.setEnabled(False)
            j.setFixedWidth(join_w)
            j.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(j)
        row.addWidget(w)
    if unit:
        u = QLabel(unit, parent)
        u.setEnabled(False)
        u.setFixedWidth(JOIN2_W)
        u.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(u)
    row.addStretch(1)
    return row


def _spin(lo: float, hi: float, value: float, *, decimals: int = 0, suffix: str = "",
          parent: QWidget, width: int = BOX2_W):
    box = QDoubleSpinBox(parent) if decimals else QSpinBox(parent)
    if decimals:
        box.setDecimals(decimals)
    box.setRange(lo, hi)
    box.setValue(value)
    if suffix:
        box.setSuffix(suffix)
    box.setFixedWidth(width)
    box.setKeyboardTracking(False)
    return box


def _spin3(lo: float, hi: float, value: float, *, decimals: int = 0, parent: QWidget):
    """A box for a three-box row (min, opt, max)."""
    return _spin(lo, hi, value, decimals=decimals, parent=parent, width=BOX3_W)


def _row_widget(label: str, *widgets, parent: QWidget, joins=(), label_w: int = LABEL_W,
                unit: str = "", cells: bool = False) -> QWidget:
    """A grid row inside a widget, so the whole row can be shown or hidden."""
    box = QWidget(parent)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addLayout(_row(label, *widgets, parent=box, joins=joins, label_w=label_w, unit=unit,
                       cells=cells))
    return box


def _results_surface(widget: QWidget) -> None:
    """The area around the result boxes: the window colour, as everywhere.

    Only the boxes themselves (see ``_card``) and the input fields are white.
    """
    widget.setAutoFillBackground(True)


class NoteLabel(QLabel):
    """A status line. Wrapped by default; ``set_elided`` keeps it on one line,
    cut with "…" when it does not fit, the whole text in its tooltip."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full = str(text)
        self._elided = False

    def set_elided(self, on: bool) -> None:
        self._elided = bool(on)
        self.setWordWrap(not on)
        if on:
            policy = self.sizePolicy()
            policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
            self.setSizePolicy(policy)
        self._apply()

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = str(text)
        self._apply()

    def text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._elided:
            self._apply()

    def _apply(self) -> None:
        if not self._elided:
            super().setText(self._full)
            return
        shown = self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideRight, max(0, self.width() - 2))
        super().setText(shown)
        self.setToolTip(self._full if shown != self._full else "")


def _relax_wrapped_labels(root: QWidget) -> None:
    """A wrapped label never asks for more width than the panel has.

    A long word without spaces (a primer name, a sequence) otherwise makes the
    panel "want" to be wider; its height is then worked out for that width, and
    the boxes and lines end up squeezed into too little room.
    """
    for label in root.findChildren(QLabel):
        if label.wordWrap() and label.minimumWidth() == label.maximumWidth():
            continue                                   # a fixed width stays
        if label.wordWrap():
            policy = label.sizePolicy()
            policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
            label.setSizePolicy(policy)


def _scroll_middle(middle: QWidget, parent: QWidget) -> QScrollArea:
    """The result side of a page: it scrolls in a short window, so the last
    box keeps its bottom edge."""
    area = QScrollArea(parent)
    area.setWidget(middle)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return area


class VerdictLabel(QLabel):
    """The result line of a page: shown under the boxes, and only when it is a
    result or a problem (green or amber). A plain hint stays out of sight, so
    the boxes sit at the same place in every section; the "?" explains the page.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWordWrap(True)
        self.hide()

    def setStyleSheet(self, sheet: str) -> None:  # noqa: N802
        super().setStyleSheet(sheet)
        self.setVisible(bool(sheet))


def _card(widget: QWidget, parent: QWidget) -> QFrame:
    """``widget`` in a white box with a thin border and round corners."""
    frame = QFrame(parent)
    frame.setObjectName("rvCard")
    frame.setStyleSheet(
        "QFrame#rvCard { background: palette(base); border: 1px solid palette(mid);"
        " border-radius: 8px; }")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(4, 4, 4, 4)
    lay.setSpacing(0)
    lay.addWidget(widget)
    # A table kept as short as its rows keeps its box that short too.
    lay.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
    return frame


def _field_buttons(parent: QWidget, *buttons: QWidget, label: str = "") -> QHBoxLayout:
    """Buttons in the field column: together as wide as a field, equal in width.

    ``label`` goes in the label column, as for any other row.
    """
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(GAP)
    pad = QLabel(label, parent)
    pad.setFixedWidth(LABEL_W)
    row.addWidget(pad)
    inner = QHBoxLayout()
    inner.setContentsMargins(0, 0, 0, 0)
    inner.setSpacing(6)
    room = FIELD_W - 6 * (len(buttons) - 1)
    for i, button in enumerate(buttons):
        width = room // len(buttons) + (1 if i < room % len(buttons) else 0)
        button.setFixedWidth(width)
        inner.addWidget(button)
    row.addLayout(inner)
    row.addStretch(1)
    return row


def _field_path(row, *, browse_w: int | None = None) -> None:
    """A file field in the field column: as wide as every other field.

    The path box has a wide minimum of its own for dialogs; here it would be
    cut off at the right (no round end, the text out of the box).
    """
    row.setFixedWidth(FIELD_W)
    row.line_edit().setMinimumWidth(0)
    row._browse_btn.setFixedWidth(FIELD_W if browse_w is None else browse_w)


class MiddleElideCombo(QComboBox):
    """A drop-down menu whose shown name is cut in the middle when it does not fit.

    Record names share their beginning and differ at the end. The opened list
    is as wide as the longest name, and the whole name is in the tooltip.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.currentIndexChanged.connect(
            lambda _i: self.setToolTip(self.currentText()))

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtWidgets import QStyle, QStyleOptionComboBox, QStylePainter

        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        field = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option,
            QStyle.SubControl.SC_ComboBoxEditField, self)
        option.currentText = self.fontMetrics().elidedText(
            option.currentText, Qt.TextElideMode.ElideMiddle, max(0, field.width() - 4))
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)

    def showPopup(self) -> None:  # noqa: N802
        view = self.view()
        view.setMinimumWidth(max(self.width(), view.sizeHintForColumn(0) + 32))
        super().showPopup()

    def minimumSizeHint(self):  # noqa: N802
        hint = super().minimumSizeHint()
        hint.setWidth(40)          # a long name never makes the box wider
        return hint


def _action_row(parent: QWidget, left: QWidget, *right: QWidget) -> QWidget:
    """The buttons at the end of a panel: ``left`` starts where the labels
    start, ``right`` end where the fields end."""
    box = QWidget(parent)
    box.setFixedWidth(LABEL_W + GAP + FIELD_W)
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    row.addWidget(left)
    row.addStretch(1)
    for button in right:
        row.addWidget(button)
    return box


def _scroll_panel(panel: QWidget, parent: QWidget) -> QScrollArea:
    """The settings panel of a page: it scrolls in a short window, so its
    fields are never squeezed."""
    width = panel.maximumWidth()
    _relax_wrapped_labels(panel)
    panel.setMinimumWidth(0)
    panel.setMaximumWidth(16777215)
    area = QScrollArea(parent)
    area.setWidget(panel)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setFixedWidth(width)
    return area


def _choice_combo(group: QButtonGroup, prop: str, parent: QWidget) -> QComboBox:
    """A drop-down menu for the choices of ``group``, as wide as every other field.

    The buttons of the group stay the state (and are never shown): picking an
    item clicks its button, and a button checked by the code moves the menu.
    """
    combo = QComboBox(parent)
    combo.setFixedWidth(FIELD_W)
    for b in group.buttons():
        combo.addItem(b.text(), b.property(prop))

    def pick(index: int) -> None:
        key = combo.itemData(index)
        for b in group.buttons():
            if b.property(prop) == key and not b.isChecked():
                b.click()

    def follow(button, checked: bool) -> None:
        if checked:
            i = combo.findData(button.property(prop))
            if i >= 0:
                combo.setCurrentIndex(i)

    combo.activated.connect(pick)
    group.buttonToggled.connect(follow)
    return combo


def _triple_header(parent: QWidget, label_w: int = LABEL_W) -> QHBoxLayout:
    """The one "min opt max" line above a group of three-box rows."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(GAP3)
    pad = QLabel("", parent)
    pad.setFixedWidth(label_w)
    row.addWidget(pad)
    for word in ("min", "opt", "max"):
        w = QLabel(word, parent)
        w.setEnabled(False)
        w.setFixedWidth(BOX3_W)
        w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(w)
    row.addStretch(1)
    return row


class DesignPane(QWidget):
    """``keepRequested`` carries the Primer objects of the ticked pairs."""

    keepRequested = Signal(list)
    jobRequested = Signal(dict)        # design on the files selected in Files
    settingsSaved = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = None
        self._run: dz.Primer3Run | None = None
        self._run_region: wb.Region | None = None
        self._run_settings: dz.DesignSettings | None = None
        self._busy = False
        self._shown: tuple[int, int] | None = None   # range shown for a candidate
        self.overlay_enabled = True   # the panel turns it off on the Primer page
        self._relay = _Relay(self)
        self._relay.done.connect(self._on_done)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        s = self._load_settings()

        # ---- Run on
        sec, sl, _ = _section("Run on", self, "Run on", RUN_ON_HELP)
        self.run_group = QButtonGroup(self)
        self.run_group.setExclusive(True)
        run_row = []
        holder = QWidget(sec)       # the state behind the drop-down menu
        holder.hide()
        for i, (key, text) in enumerate(((RUN_THIS, "Open sequence"), (RUN_FILES, "Selected files"))):
            b = QPushButton(text, holder)
            b.setCheckable(True)
            b.setProperty("run", key)
            self.run_group.addButton(b, i)
            run_row.append(b)
        run_row[0].setChecked(True)
        self.run_combo = _choice_combo(self.run_group, "run", sec)
        sl.addLayout(_row("Input", self.run_combo, parent=sec))
        self.run_note = QLabel("", sec)
        self.run_note.setWordWrap(True)
        self.run_note.setIndent(LABEL_W + GAP)
        self.run_note.setStyleSheet("color: palette(placeholder-text);")
        sl.addWidget(self.run_note)
        lay.addWidget(sec)
        lay.addWidget(_rule(self))
        self.run_section = sec

        # ---- Region
        sec, sl, _ = _section("Region", self, "Region", REGION_HELP)
        self.region_from = _spin(1, 2_000_000_000, 1, parent=sec)
        self.region_to = _spin(1, 2_000_000_000, 1, parent=sec)
        self.region_from.setFixedWidth(BOX2_W)
        self.region_to.setFixedWidth(BOX2_W)
        sl.addLayout(_row("From", self.region_from, self.region_to, parent=sec, joins=("to",)))
        self.use_group = QButtonGroup(self)
        self.use_group.setExclusive(True)
        use_row = []
        holder = QWidget(sec)       # the state behind the drop-down menu
        holder.hide()
        for i, use in enumerate(wb.USES):
            b = QPushButton(wb.USE_LABELS[use], holder)
            b.setCheckable(True)
            b.setProperty("use", use)
            self.use_group.addButton(b, i)
            use_row.append(b)
        use_row[0].setChecked(True)
        self.use_combo = _choice_combo(self.use_group, "use", sec)
        sl.addLayout(_row("Use it to", self.use_combo, parent=sec))
        self.region_note = QLabel("Drag on the map, or type the range.", sec)
        self.region_note.setWordWrap(True)
        self.region_note.setStyleSheet("color: palette(placeholder-text);")
        self.region_note.setIndent(LABEL_W + GAP)
        sl.addWidget(self.region_note)
        self.advice = QFrame(sec)
        self.advice.setObjectName("workbenchAdvice")
        self.advice.setStyleSheet(
            "#workbenchAdvice { background: #FFF4E5; border: 1px solid #E8A33D;"
            " border-radius: 6px; } #workbenchAdvice QLabel { color: #5A3700; }")
        al = QVBoxLayout(self.advice)
        al.setContentsMargins(8, 6, 8, 6)
        al.setSpacing(6)
        self.advice_label = QLabel(self.advice)
        self.advice_label.setWordWrap(True)
        al.addWidget(self.advice_label)
        self.fit_button = QPushButton("Set Product Range to Fit", self.advice)
        fr = QHBoxLayout()
        fr.addStretch(1)
        fr.addWidget(self.fit_button)
        al.addLayout(fr)
        self.advice.hide()
        sl.addWidget(self.advice)
        lay.addWidget(sec)
        self.region_section = sec
        self.region_rule = _rule(self)
        lay.addWidget(self.region_rule)

        # ---- Settings
        sec, sl, _ = _section("Settings", self, "Settings", SETTINGS_HELP)
        self.mode = QComboBox(sec)
        for m in wb.WORKBENCH_MODES:
            self.mode.addItem(dz.MODE_LABELS[m], m)
        self.mode.setFixedWidth(FIELD_W)
        i = self.mode.findData(s.mode)
        self.mode.setCurrentIndex(max(0, i))
        sl.addLayout(_row("Mode", self.mode, parent=sec))
        self.probe_check = QCheckBox("Hydrolysis probe (TaqMan)", sec)
        self.probe_check.setChecked(bool(s.pick_probe))
        self.probe_row = _row_widget("", self.probe_check, parent=sec)
        sl.addWidget(self.probe_row)
        sl.addLayout(_triple_header(sec))
        self.size_min = _spin3(5, 60, s.size_min, parent=sec)
        self.size_opt = _spin3(5, 60, s.size_opt, parent=sec)
        self.size_max = _spin3(5, 60, s.size_max, parent=sec)
        sl.addLayout(_row("Size", self.size_min, self.size_opt, self.size_max, parent=sec))
        self.tm_min = _spin3(20, 95, s.tm_min, decimals=1, parent=sec)
        self.tm_opt = _spin3(20, 95, s.tm_opt, decimals=1, parent=sec)
        self.tm_max = _spin3(20, 95, s.tm_max, decimals=1, parent=sec)
        sl.addLayout(_row("Tm (°C)", self.tm_min, self.tm_opt, self.tm_max, parent=sec))
        self.prod_min = _spin3(10, 100_000, s.product_min, parent=sec)
        self.prod_max = _spin3(10, 100_000, s.product_max, parent=sec)
        self.product_row = _row_widget("Product", self.prod_min, self.prod_max, parent=sec,
                                       joins=("to",), cells=True)
        sl.addWidget(self.product_row)
        self.gc_min = _spin3(0, 100, s.gc_min, decimals=1, parent=sec)
        self.gc_max = _spin3(0, 100, s.gc_max, decimals=1, parent=sec)
        sl.addLayout(_row("GC (%)", self.gc_min, self.gc_max, parent=sec, joins=("to",),
                          cells=True))
        self.tm_diff = _spin3(0, 20, s.max_tm_diff, decimals=1, parent=sec)
        self.tm_diff_row = _row_widget("Max Tm diff", self.tm_diff, parent=sec)
        sl.addWidget(self.tm_diff_row)
        self.num_return = _spin3(1, 100, s.num_return, parent=sec)
        self.num_label = QLabel("Pairs", sec)
        self.num_label.setFixedWidth(LABEL_W)
        self.num_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        nr = QHBoxLayout()
        nr.setContentsMargins(0, 0, 0, 0)
        nr.setSpacing(GAP3)
        nr.addWidget(self.num_label)
        nr.addWidget(self.num_return)
        nr.addStretch(1)
        sl.addLayout(nr)
        lay.addWidget(sec)
        lay.addWidget(_rule(self))

        # ---- Advanced (closed by default; the summary says what is inside)
        sec, sl, self.adv_title = _section("Advanced", self, "Advanced", ADVANCED_HELP)
        self.adv_toggle = QPushButton("Show", sec)
        self.adv_toggle.setCheckable(True)
        self.adv_summary = QLabel(sec)
        self.adv_summary.setWordWrap(True)
        self.adv_summary.setStyleSheet("color: palette(placeholder-text);")
        # in the field column, as wide as the fields above it
        sl.addLayout(_field_buttons(sec, self.adv_toggle))
        sl.addWidget(self.adv_summary)
        self.adv_body = QWidget(sec)
        ab = QVBoxLayout(self.adv_body)
        ab.setContentsMargins(0, 0, 0, 0)
        ab.setSpacing(6)
        self.poly_x = _spin(0, 20, s.max_poly_x, parent=self.adv_body)
        ab.addLayout(_row("Max poly-X", self.poly_x, parent=self.adv_body))
        self.gc_clamp = _spin(0, 5, s.gc_clamp, parent=self.adv_body)
        ab.addLayout(_row("GC clamp", self.gc_clamp, parent=self.adv_body))
        self.end_stab = _spin(0, 20, s.max_end_stability, decimals=1, parent=self.adv_body)
        ab.addLayout(_row("Max 3′ stability", self.end_stab, parent=self.adv_body))
        self.probe_head = QWidget(self.adv_body)
        ph = QVBoxLayout(self.probe_head)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(0)
        ph.addLayout(_triple_header(self.probe_head))
        ab.addWidget(self.probe_head)
        self.probe_size_min = _spin3(5, 60, s.probe_size_min, parent=self.adv_body)
        self.probe_size_opt = _spin3(5, 60, s.probe_size_opt, parent=self.adv_body)
        self.probe_size_max = _spin3(5, 60, s.probe_size_max, parent=self.adv_body)
        self.probe_size_row = _row_widget("Probe size", self.probe_size_min,
                                          self.probe_size_opt, self.probe_size_max,
                                          parent=self.adv_body)
        ab.addWidget(self.probe_size_row)
        self.probe_tm_min = _spin3(20, 95, s.probe_tm_min, decimals=1, parent=self.adv_body)
        self.probe_tm_opt = _spin3(20, 95, s.probe_tm_opt, decimals=1, parent=self.adv_body)
        self.probe_tm_max = _spin3(20, 95, s.probe_tm_max, decimals=1, parent=self.adv_body)
        self.probe_tm_row = _row_widget("Probe Tm (°C)", self.probe_tm_min, self.probe_tm_opt,
                                        self.probe_tm_max, parent=self.adv_body)
        ab.addWidget(self.probe_tm_row)
        self.na = _spin(0, 1000, s.thermo.monovalent_mM, decimals=1, parent=self.adv_body)
        ab.addLayout(_row("Na (mM)", self.na, parent=self.adv_body))
        self.mg = _spin(0, 100, s.thermo.divalent_mM, decimals=1, parent=self.adv_body)
        ab.addLayout(_row("Mg (mM)", self.mg, parent=self.adv_body))
        self.dntp = _spin(0, 100, s.thermo.dntp_mM, decimals=2, parent=self.adv_body)
        ab.addLayout(_row("dNTP (mM)", self.dntp, parent=self.adv_body))
        self.adv_body.hide()
        sl.addWidget(self.adv_body)
        lay.addWidget(sec)
        lay.addWidget(_rule(self))

        # ---- Cross-hybridisation (probes only)
        sec, sl, _ = _section("Cross-hybridisation", self, "Cross-hybridisation", CROSS_HELP)
        self.min_cov = _spin(0, 100, round(s.min_coverage * 100), suffix=" %", parent=sec)
        sl.addLayout(_row("Min coverage", self.min_cov, parent=sec))
        self.cov_mm = _spin(0, 10, s.coverage_mismatches, parent=sec)
        sl.addLayout(_row("Mismatches", self.cov_mm, parent=sec))
        from repeatviewer.widgets.path_browse import PathBrowseRow

        self.avoid_path = PathBrowseRow(
            sec, initial=s.fish_avoid_fasta or None,
            placeholder="Other families (FASTA, optional)",
            browse_title="Repeats the probes must not match",
            file_filter="FASTA (*.fa *.fasta *.fas *.fna);;All files (*)",
            browse_below=True, elide_middle=True)
        _field_path(self.avoid_path)
        sl.addLayout(_row("Avoid file", self.avoid_path, parent=sec, top=True))
        self.avoid_others = QCheckBox("Avoid the other selected files", sec)
        self.avoid_others.setChecked(bool(s.fish_avoid_other_inputs))
        self.skip_unsuitable = QCheckBox("Leave out low-complexity", sec)
        self.skip_unsuitable.setChecked(bool(s.fish_skip_unsuitable))
        for box in (self.avoid_others, self.skip_unsuitable):
            sl.addLayout(_row("", box, parent=sec))
        self.cross_section = sec
        self.cross_rule = _rule(self)
        lay.addWidget(sec)
        lay.addWidget(self.cross_rule)

        # ---- Hybridisation and wash (probes only)
        sec, sl, _ = _section("Hybridisation", self, "Hybridisation", HYB_HELP)
        self.hyb_fa = _spin(0, 100, s.hyb.formamide_pct, decimals=1, suffix=" %", parent=sec)
        sl.addLayout(_row("Formamide", self.hyb_fa, parent=sec))
        self.hyb_ssc = _spin(0.01, 20, s.hyb.ssc, decimals=2, suffix=" ×", parent=sec)
        sl.addLayout(_row("SSC", self.hyb_ssc, parent=sec))
        self.hyb_temp = _spin(0, 99, s.hyb.temp_c, decimals=1, suffix=" °C", parent=sec)
        sl.addLayout(_row("Temperature", self.hyb_temp, parent=sec))
        self.hyb_nm = _spin(0.1, 10_000, s.hyb.probe_nM, decimals=1, suffix=" nM", parent=sec)
        sl.addLayout(_row("Probe", self.hyb_nm, parent=sec))
        self.hyb_section = sec
        self.hyb_rule = _rule(self)
        lay.addWidget(sec)
        lay.addWidget(self.hyb_rule)

        sec, sl, _ = _section("Stringent wash", self, "Stringent wash", HYB_HELP)
        self.wash_fa = _spin(0, 100, s.hyb.wash_formamide_pct, decimals=1, suffix=" %",
                             parent=sec)
        sl.addLayout(_row("Formamide", self.wash_fa, parent=sec))
        self.wash_ssc = _spin(0.01, 20, s.hyb.wash_ssc, decimals=2, suffix=" ×", parent=sec)
        sl.addLayout(_row("SSC", self.wash_ssc, parent=sec))
        self.wash_temp = _spin(0, 99, s.hyb.wash_temp_c, decimals=1, suffix=" °C", parent=sec)
        sl.addLayout(_row("Temperature", self.wash_temp, parent=sec))
        self.wash_section = sec
        self.wash_rule = _rule(self)
        lay.addWidget(sec)
        lay.addWidget(self.wash_rule)

        # ---- Options
        sec, sl, _ = _section("Options", self, "Options", OPTIONS_HELP)
        self.ask_check = QCheckBox("Ask which pairs to add here", sec)
        self.db_check = QCheckBox("Add them to the Database", sec)
        for box in (self.ask_check, self.db_check):
            sl.addLayout(_row("", box, parent=sec))
        self.defaults_button = QPushButton("Restore Defaults", sec)
        self.save_button = QPushButton("Save", sec)
        self.design_button = QPushButton("Design", sec)
        self.design_button.setDefault(True)
        # Save in the field column, as wide as the fields above it
        sl.addLayout(_field_buttons(sec, self.save_button))
        # The workspace takes these two to the top of the panel and hides the row.
        self.end_row = QWidget(sec)
        br = QHBoxLayout(self.end_row)
        br.setContentsMargins(0, 2, 0, 0)
        br.setSpacing(6)
        br.addWidget(self.defaults_button)
        br.addStretch(1)
        br.addWidget(self.design_button)
        sl.addWidget(self.end_row)
        self.saved_note = QLabel("", sec)
        self.saved_note.setStyleSheet("color: palette(placeholder-text);")
        sl.addWidget(self.saved_note)
        lay.addWidget(sec)
        lay.addWidget(_rule(self))

        # ---- Candidates
        sec, sl, self.cand_title = _section("Candidates", self, "Candidates", CANDIDATES_HELP)
        self.table = QTableWidget(0, 4, sec)
        self.table.setHorizontalHeaderLabels(["", "Pair", "Product", "Tm F / R"])
        self._probe_headers = ["", "Probe", "Length", "Tm"]
        self._pair_headers = ["", "Pair", "Product", "Tm F / R"]
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        head.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        head.setStretchLastSection(True)
        for c, w in enumerate((24, 70, 70)):
            self.table.setColumnWidth(c, w)
        self.table.setMinimumHeight(150)
        sl.addWidget(self.table)
        self.cand_note = NoteLabel("None yet. Press Design.", sec)
        self.cand_note.setWordWrap(True)
        self.cand_note.setStyleSheet("color: palette(placeholder-text);")
        sl.addWidget(self.cand_note)
        self.report_button = QPushButton("Open Report", sec)
        self.keep_button = QPushButton("Keep Ticked", sec)
        kr = QHBoxLayout()
        kr.addStretch(1)
        kr.addWidget(self.report_button)
        kr.addWidget(self.keep_button)
        sl.addLayout(kr)
        lay.addWidget(sec)
        lay.addStretch(1)

        for w in (self.region_from, self.region_to, self.size_min, self.size_max,
                  self.prod_min, self.prod_max):
            w.valueChanged.connect(self._update_advice)
        self.use_group.idClicked.connect(lambda _i: self._update_advice())
        self.run_group.idClicked.connect(lambda _i: self._on_run_where())
        self.fit_button.clicked.connect(self._on_fit)
        self.design_button.clicked.connect(self.run_design)
        self.defaults_button.clicked.connect(self._on_defaults)
        self.save_button.clicked.connect(self._on_save)
        self.adv_toggle.toggled.connect(self._on_advanced)
        self.probe_check.toggled.connect(lambda _b: self._update_advanced_summary())
        for box in (self.poly_x, self.gc_clamp, self.end_stab, self.na, self.mg, self.dntp):
            box.valueChanged.connect(lambda _v: self._update_advanced_summary())
        self.keep_button.clicked.connect(self._on_keep)
        self.report_button.clicked.connect(self._on_report)
        self.table.itemSelectionChanged.connect(self._on_pick)
        self.mode.currentIndexChanged.connect(lambda _i: self._on_mode_changed())
        self._update_advanced_summary()
        self._apply_mode()
        self._on_run_where()
        self._sync_buttons()

    # ------------------------------------------------------------- host / state

    def set_host(self, host) -> None:
        self._host = host
        self.reset_for_sequence()

    def _sequence(self) -> tuple[str, str]:
        if self._host is None:
            return "", ""
        try:
            return self._host.primers_host_sequence()
        except Exception:  # noqa: BLE001 - no sequence loaded
            return "", ""

    def reset_for_sequence(self) -> None:
        _sid, seq = self._sequence()
        n = max(1, len(seq))
        for box in (self.region_from, self.region_to):
            box.blockSignals(True)
            box.setRange(1, n)
            box.blockSignals(False)
        self._clear_candidates()
        self._update_advice()

    def set_region(self, start: int, end: int) -> None:
        """From the map selection (1-based, inclusive). Single clicks are ignored."""
        a, b = sorted((int(start), int(end)))
        if b - a < 1 or (a, b) == self._shown:
            return   # a click, or the product we just showed for a candidate
        for box, v in ((self.region_from, a), (self.region_to, b)):
            box.blockSignals(True)
            box.setValue(v)
            box.blockSignals(False)
        self._update_advice()

    def region(self) -> wb.Region | None:
        if self.run_where() == RUN_FILES:
            return None
        a, b = self.region_from.value(), self.region_to.value()
        if b - a < 1:
            return None
        btn = self.use_group.checkedButton()
        use = btn.property("use") if btn is not None else wb.USE_AMPLIFY
        return wb.Region(a, b, use)

    def settings(self) -> dz.DesignSettings:
        base = self._load_settings()
        d = base.to_dict()
        thermo = dict(d.get("thermo") or {})
        thermo.update(monovalent_mM=self.na.value(), divalent_mM=self.mg.value(),
                      dntp_mM=self.dntp.value())
        hyb = dict(d.get("hyb") or {})
        hyb.update(formamide_pct=self.hyb_fa.value(), ssc=self.hyb_ssc.value(),
                   temp_c=self.hyb_temp.value(), probe_nM=self.hyb_nm.value(),
                   wash_formamide_pct=self.wash_fa.value(), wash_ssc=self.wash_ssc.value(),
                   wash_temp_c=self.wash_temp.value())
        d.update(mode=str(self.mode.currentData()),
                 min_coverage=self.min_cov.value() / 100.0,
                 coverage_mismatches=self.cov_mm.value(),
                 fish_avoid_fasta=str(self.avoid_path.path() or ""),
                 fish_avoid_other_inputs=self.avoid_others.isChecked(),
                 fish_skip_unsuitable=self.skip_unsuitable.isChecked(),
                 hyb=hyb,
                 size_min=self.size_min.value(), size_opt=self.size_opt.value(),
                 size_max=self.size_max.value(), tm_min=self.tm_min.value(),
                 tm_opt=self.tm_opt.value(), tm_max=self.tm_max.value(),
                 product_min=self.prod_min.value(), product_max=self.prod_max.value(),
                 gc_min=self.gc_min.value(), gc_max=self.gc_max.value(),
                 max_tm_diff=self.tm_diff.value(), num_return=self.num_return.value(),
                 pick_probe=self.probe_check.isChecked(),
                 max_poly_x=self.poly_x.value(), gc_clamp=self.gc_clamp.value(),
                 max_end_stability=self.end_stab.value(),
                 probe_size_min=self.probe_size_min.value(),
                 probe_size_opt=self.probe_size_opt.value(),
                 probe_size_max=self.probe_size_max.value(),
                 probe_tm_min=self.probe_tm_min.value(),
                 probe_tm_opt=self.probe_tm_opt.value(),
                 probe_tm_max=self.probe_tm_max.value(),
                 thermo=thermo)
        return dz.DesignSettings.from_dict(d)

    def run_where(self) -> str:
        btn = self.run_group.checkedButton()
        return str(btn.property("run")) if btn is not None else RUN_THIS

    def options(self) -> dict:
        """What to do with a finished run on the selected files."""
        return {"annotate_design": self.ask_check.isChecked(),
                "save_design_to_database": self.db_check.isChecked()}

    def set_options(self, annotate: bool, to_database: bool) -> None:
        for box, value in ((self.ask_check, annotate), (self.db_check, to_database)):
            box.blockSignals(True)
            box.setChecked(bool(value))
            box.blockSignals(False)

    def _load_settings(self) -> dz.DesignSettings:
        raw = QSettings().value(_SETTINGS_KEY, "")
        try:
            data = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            data = None
        if not data:
            return dz.DesignSettings(**dz.mode_preset(dz.MODE_PCR))
        s = dz.DesignSettings.from_dict(data)
        if s.mode not in wb.WORKBENCH_MODES:
            s.mode = dz.MODE_PCR
        return s

    def _save_settings(self) -> None:
        QSettings().setValue(_SETTINGS_KEY, json.dumps(self.settings().to_dict()))

    def _on_defaults(self) -> None:
        p = dz.mode_preset(str(self.mode.currentData()))
        base = dz.DesignSettings(**p)
        for box, value in ((self.size_min, base.size_min), (self.size_opt, base.size_opt),
                           (self.size_max, base.size_max), (self.tm_min, base.tm_min),
                           (self.tm_opt, base.tm_opt), (self.tm_max, base.tm_max),
                           (self.prod_min, base.product_min),
                           (self.prod_max, base.product_max),
                           (self.gc_min, base.gc_min), (self.gc_max, base.gc_max),
                           (self.tm_diff, base.max_tm_diff),
                           (self.num_return, base.num_return),
                           (self.poly_x, base.max_poly_x), (self.gc_clamp, base.gc_clamp),
                           (self.end_stab, base.max_end_stability),
                           (self.probe_size_min, base.probe_size_min),
                           (self.probe_size_opt, base.probe_size_opt),
                           (self.probe_size_max, base.probe_size_max),
                           (self.probe_tm_min, base.probe_tm_min),
                           (self.probe_tm_opt, base.probe_tm_opt),
                           (self.probe_tm_max, base.probe_tm_max),
                           (self.na, base.thermo.monovalent_mM),
                           (self.mg, base.thermo.divalent_mM),
                           (self.dntp, base.thermo.dntp_mM),
                           (self.min_cov, round(base.min_coverage * 100)),
                           (self.cov_mm, base.coverage_mismatches)):
            box.setValue(value)
        self.probe_check.setChecked(bool(base.pick_probe))
        self._update_advanced_summary()
        self._update_advice()

    def _on_save(self) -> None:
        self._save_settings()
        self.saved_note.setText("Saved. Right-click a FASTA in Files to run with these.")
        self.settingsSaved.emit()

    def _on_advanced(self, shown: bool) -> None:
        self.adv_toggle.setText("Hide" if shown else "Show")
        self.adv_body.setVisible(shown)
        self.adv_summary.setVisible(not shown)

    def _update_advanced_summary(self) -> None:
        probe = ", probe picked" if self.probe_check.isChecked() else ""
        self.adv_summary.setText(
            f"Poly-X {self.poly_x.value()} · GC clamp {self.gc_clamp.value()} · "
            f"3′ stability {self.end_stab.value():g} · Na {self.na.value():g} mM, "
            f"Mg {self.mg.value():g} mM, dNTP {self.dntp.value():g} mM{probe}")

    def is_probe_mode(self) -> bool:
        return str(self.mode.currentData()) == dz.MODE_FISH

    def _on_mode_changed(self) -> None:
        """A new mode brings its own conditions, as the Design window did."""
        self._on_defaults()
        self._apply_mode()

    def _apply_mode(self) -> None:
        """Show the rows that belong to the chosen mode, hide the rest."""
        probes = self.is_probe_mode()
        for w in (self.probe_row, self.product_row, self.tm_diff_row, self.probe_head,
                  self.probe_size_row, self.probe_tm_row):
            w.setVisible(not probes)
        for w in (self.cross_section, self.cross_rule, self.hyb_section, self.hyb_rule,
                  self.wash_section, self.wash_rule):
            w.setVisible(probes)
        self.num_label.setText("Probes" if probes else "Pairs")
        self.cand_title.setText("<b>Probes</b>" if probes else "<b>Candidates</b>")
        uses = wb.PROBE_USES if probes else wb.USES
        for b in self.use_group.buttons():
            use = str(b.property("use"))
            b.setVisible(use in uses)
            if use == wb.USE_AMPLIFY and probes and b.isChecked():
                for other in self.use_group.buttons():
                    if other.property("use") == wb.USE_INSIDE:
                        other.setChecked(True)
        self.use_combo.clear()
        for b in self.use_group.buttons():
            if str(b.property("use")) in uses:
                self.use_combo.addItem(b.text(), b.property("use"))
        checked = self.use_group.checkedButton()
        if checked is not None:
            self.use_combo.setCurrentIndex(max(0, self.use_combo.findData(checked.property("use"))))
        self.keep_button.setText("Keep Ticked")
        self._update_advice()

    def _on_run_where(self) -> None:
        files = self.run_where() == RUN_FILES
        self.region_section.setVisible(not files)
        self.region_rule.setVisible(not files)
        self.design_button.setText("Run" if files else "Design")
        self.run_note.setText(
            "Every FASTA ticked in Files (the highlighted one when none is ticked), "
            "with the progress bar and report files."
            if files else "The open sequence, live. Nothing is written yet.")
        self.push_overlay()

    # ------------------------------------------------------------------ advice

    def _update_advice(self) -> None:
        self.push_overlay()
        _sid, seq = self._sequence()
        region = self.region()
        if region is None:
            self.region_note.setText("Drag on the map, or type the range.")
            self.advice.hide()
            return
        self.region_note.setText(region.label())
        adv = wb.region_advice(region, self.settings(), len(seq))
        if adv is None:
            self.advice.hide()
            return
        self.advice_label.setText(adv.message)
        self.fit_button.setVisible(adv.can_fix)
        self.advice.show()

    def _on_fit(self) -> None:
        _sid, seq = self._sequence()
        adv = wb.region_advice(self.region(), self.settings(), len(seq))
        if adv is None or not adv.can_fix:
            return
        self.prod_min.setValue(adv.product_min)
        self.prod_max.setValue(adv.product_max)
        self._update_advice()

    # ------------------------------------------------------------------ design

    def run_design(self) -> None:
        if self._busy:
            return
        if self.run_where() == RUN_FILES:
            self._save_settings()
            payload = {"settings": self.settings().to_dict()}
            payload.update(self.options())
            self.jobRequested.emit(payload)
            self.cand_note.setText("Running on the selected files. See the progress bar.")
            return
        sid, seq = self._sequence()
        if not seq:
            self.cand_note.setText("Open a sequence first.")
            return
        s = self.settings()
        region = self.region()
        self._save_settings()
        self._busy = True
        self._sync_buttons()
        self.cand_note.setText("Looking for probes…" if self.is_probe_mode() else "Designing…")
        relay = self._relay
        path = None
        if self._host is not None:
            try:
                path = self._host.primers_host_path()
            except Exception:  # noqa: BLE001 - no file open
                path = None
        probes = self.is_probe_mode()

        def work() -> None:
            try:
                run = (wb.design_probes(path, sid, seq, s, region) if probes
                       else wb.design_candidates(sid, seq, s, region))
            except Exception as exc:  # noqa: BLE001 - shown in the pane
                relay.done.emit(None, str(exc))
                return
            relay.done.emit(run, None)

        self._run_region, self._run_settings = region, s
        threading.Thread(target=work, daemon=True).start()

    def _on_done(self, run, error) -> None:
        self._busy = False
        if error:
            self._clear_candidates()
            self.cand_note.setText(f"Design failed: {error}")
            self._sync_buttons()
            return
        self._run = run
        self._fill(run)
        self._sync_buttons()

    def _clear_candidates(self) -> None:
        self._run = None
        self.table.setRowCount(0)
        self.push_overlay()
        self.cand_title.setText("<b>Candidates</b>")
        self.cand_note.setText("None yet. Press Design.")
        self._sync_buttons()

    def _fill(self, run: dz.Primer3Run) -> None:
        pairs = run.pairs
        probes = self.is_probe_mode()
        self.table.setHorizontalHeaderLabels(self._probe_headers if probes
                                             else self._pair_headers)
        self.table.blockSignals(True)
        self.table.setRowCount(len(pairs))
        for r, p in enumerate(pairs):
            tick = QTableWidgetItem()
            tick.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                          | Qt.ItemFlag.ItemIsSelectable)
            tick.setCheckState(Qt.CheckState.Checked if r == 0 else Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, tick)
            if probes and p.probe is not None:
                length = p.probe.end - p.probe.start + 1
                cells = (f"P{r + 1}", f"{length} nt", f"{p.probe.tm:.1f} °C")
            else:
                tms = (f"{p.forward.tm:.1f} / {p.reverse.tm:.1f}"
                       if p.forward is not None and p.reverse is not None else "")
                cells = (f"Pair {r + 1}", f"{p.product_size:,} bp", tms)
            for c, v in enumerate(cells, start=1):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.table.blockSignals(False)
        n = len(pairs)
        word = "probe" if probes else "pair"
        self.cand_title.setText(f"<b>{'Probes' if probes else 'Candidates'}</b> &nbsp;"
                                f"<span style='color:gray'>{n} {word}"
                                f"{'s' if n != 1 else ''}</span>")
        self.push_overlay()
        if pairs:
            self.cand_note.setText(
                f"Click a {word} to see it on the sequence. Tick the ones to keep.")
            self.table.selectRow(0)
        else:
            why = "; ".join(run.explain[:2]) if run.explain else ""
            self.cand_note.setText(f"No {word} met the conditions." + (f" {why}" if why else ""))

    def _on_pick(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows or self._run is None or self._host is None:
            return
        p = self._run.pairs[rows[0].row()]
        self.push_overlay()
        if self.is_probe_mode() and p.probe is not None:
            self._shown = (int(p.probe.start), int(p.probe.end))
            try:
                show = (getattr(self._host, "primers_host_show_range", None)
                        or self._host.primers_host_show)
                show(p.probe.start, p.probe.end)
            except Exception:  # noqa: BLE001 - showing is a convenience
                pass
            notes = "; ".join(p.notes[:2])
            self.cand_note.setText(
                f"P{rows[0].row() + 1}: {p.probe.start:,} – {p.probe.end:,}."
                + (f" {notes}." if notes else ""))
            return
        if p.forward is None or p.reverse is None:
            return
        self._shown = (int(p.forward.start), int(p.reverse.end))
        try:
            show = getattr(self._host, "primers_host_show_range", None) or self._host.primers_host_show
            show(p.forward.start, p.reverse.end)
        except Exception:  # noqa: BLE001 - showing is a convenience
            pass
        notes = "; ".join(p.notes[:2])
        self.cand_note.setText(
            f"Pair {rows[0].row() + 1}: {p.forward.start:,} – {p.reverse.end:,}, "
            f"{p.product_size:,} bp." + (f" {notes}." if notes else ""))

    def push_overlay(self) -> None:
        """Draw the region band and the candidate arrows on the sequence."""
        host = self._host
        if host is None or not hasattr(host, "primers_host_set_workbench"):
            return
        if not self.overlay_enabled:
            host.primers_host_set_workbench(None, [], -1)
            return
        region = self.region()
        reg = (region.start, region.end, region.use) if region is not None else None
        cands, selected = [], -1
        if self._run is not None:
            for p in self._run.pairs:
                if p.forward is not None and p.reverse is not None:
                    cands.append((p.forward.start, p.forward.end, p.reverse.start, p.reverse.end))
                elif p.probe is not None:
                    cands.append((p.probe.start, p.probe.end, p.probe.start, p.probe.end))
            rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
            if rows:
                selected = rows[0].row()
        try:
            host.primers_host_set_workbench(reg, cands, selected)
        except Exception:  # noqa: BLE001 - drawing is a convenience
            pass

    def ticked_pairs(self) -> list[dz.DesignedPair]:
        if self._run is None:
            return []
        out = []
        for r, p in enumerate(self._run.pairs):
            item = self.table.item(r, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                out.append(p)
        return out

    def _on_keep(self) -> None:
        primers = []
        for p in self.ticked_pairs():
            primers.extend(wb.candidate_primers(p))
        if primers:
            self.keepRequested.emit(primers)

    def _on_report(self) -> None:
        if self._run is None or self._host is None:
            return
        sid, seq = self._sequence()
        try:
            path = self._host.primers_host_path()
            report = wb.write_candidates_report(path, sid, seq, self._run_settings or self.settings(),
                                                self._run_region, self._run)
        except Exception as exc:  # noqa: BLE001
            self.cand_note.setText(f"Could not write the report: {exc}")
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(report)))

    def _sync_buttons(self) -> None:
        has = self._run is not None and bool(self._run.pairs)
        self.design_button.setEnabled(not self._busy)
        self.keep_button.setEnabled(has and not self._busy)
        self.report_button.setEnabled(self._run is not None and not self._busy)


def _rule(parent: QWidget) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    line.setStyleSheet("color: palette(midlight);")
    return line


__all__ = ["DesignPane"]

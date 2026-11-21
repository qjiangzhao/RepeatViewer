"""Edit Primer window and the Primer Database picker (Preview > Annotation > Primers).

Edit Primer shows, as you type, where the primer binds on the open sequence,
its Tm (annealed part and full oligo), the 5′ tail, dimers and hairpins, and
the other places it binds.

Developer: Abdullah Yusuf
"""

from __future__ import annotations

import html
import math
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from repeatviewer.backends.primers import on_sequence as osq
from repeatviewer.backends.primers import tails as rtail
from repeatviewer.backends.primers import thermo as th
from repeatviewer.backends.primers.oligos import Primer
from repeatviewer.widgets.help_button import make_help_button
from repeatviewer.widgets.primers_panel import (
    CHECK_COLOR,
    FORWARD_COLOR,
    MISMATCH_COLOR,
    OK_COLOR,
    fmt_tm,
    mono_font,
    status_html,
)

CONTEXT_BASES = 10
CLAMP_COLOR = "#b9e3c9"
TAIL_BG = "#eef3fc"

EDIT_HELP = (
    "<b>Sequence</b>: type or paste the oligo 5′ to 3′. Lower-case letters at the 5′ end are a "
    "<b>tail</b> (they do not bind the template). An all upper-case oligo whose 5′ part does "
    "not bind gets its tail found for you.<br>"
    "<b>Binding</b> shows the primer on its best site of the open sequence; mismatches are red, "
    "the last bases at the 3′ end green when they match. Use <b>Site</b> to look at other "
    "sites and the <b>− +</b> buttons to make either end shorter or longer along the "
    "template.<br>"
    "<b>Tm annealed</b> is the Tm of the binding part on this site (mismatches included); "
    "<b>Tm full</b> is the whole oligo, which anneals from cycle 3 on.<br>"
    "<b>5′ tail</b> adds a restriction site (with padding bases so the enzyme cuts near the "
    "end), a sequencing / promoter tail, or your own.<br>"
    "<b>Dimers and hairpins</b>: ΔG in kcal/mol at 37 °C; below −9 for dimers or −3 for "
    "hairpins is a warning."
)

# "Chosen for me" asks tails.pick_padding for 6 bases that are not a palindrome
# and make no second site next to the enzyme's own (NEB's rule of thumb).
PAD_AUTO = "__auto__"
PAD_CHOICES = (("6 bases, chosen for me", PAD_AUTO), ("2 bases (AT)", "AT"),
               ("3 bases (ATA)", "ATA"), ("4 bases (ATAT)", "ATAT"),
               ("6 bases (ATAATA)", "ATAATA"), ("None", ""))


def _hrule(parent: QWidget) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


class _OligoEdit(QLineEdit):
    """The oligo field with its two ends named inside the box: 5′ left, 3′ right."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._ends: list[QLabel] = []
        for word in ("5′", "3′"):
            lab = QLabel(word, self)
            lab.setFont(mono_font(2))
            lab.setStyleSheet("color: palette(placeholder-text); background: transparent;")
            lab.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lab.adjustSize()
            self._ends.append(lab)
        room = max(lab.width() for lab in self._ends) + 8
        self.setTextMargins(room, 0, room, 0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        left, right = self._ends
        y = (self.height() - left.height()) // 2
        left.move(8, y)
        right.move(self.width() - right.width() - 8, y)


def _box(parent: QWidget, title: str, help_title: str = "", help_text: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(parent)
    frame.setObjectName("primerBox")
    frame.setStyleSheet("QFrame#primerBox { border: 1px solid palette(mid); border-radius: 8px; }")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(8)
    head = QHBoxLayout()
    head.setContentsMargins(0, 0, 0, 0)
    t = QLabel(f"<b>{html.escape(title)}</b>", frame)
    t.setStyleSheet("border: none;")
    head.addWidget(t)
    head.addStretch(1)
    if help_text:
        head.addWidget(make_help_button(frame, help_title or title, help_text))
    lay.addLayout(head)
    return frame, lay


def _bases_match(a: str, b: str) -> bool:
    a, b = a.upper(), b.upper()
    if a == b or "N" in (a, b):
        return True
    codes = th.IUPAC_BASES
    sa = set(codes.get(a, a))
    sb = set(codes.get(b, b))
    return bool(sa & sb)


def binding_html(primer_seq: str, place: osq.Placement, template: str,
                 context: int = CONTEXT_BASES) -> str:
    """Primer over its site (primer orientation), bars, both template strands."""
    tpl = template.upper()
    tail, bind = th.split_tail(primer_seq)
    if place.strand == "+":
        left = tpl[max(0, place.start - 1 - context):place.start - 1]
        right = tpl[place.end:place.end + context]
    else:
        left = th.reverse_complement(tpl[place.end:place.end + context])
        right = th.reverse_complement(tpl[max(0, place.start - 1 - context):place.start - 1])
    site = place.site.upper() or (tpl[place.start - 1:place.end] if place.strand == "+"
                                  else th.reverse_complement(tpl[place.start - 1:place.end]))
    pad = max(0, len(tail) - len(left))
    left = " " * pad + left
    lead = len(left) - len(tail)

    def esc(s: str) -> str:
        return html.escape(s)

    # primer line
    p = [""]
    if tail:
        p.append(f'<span style="color:{FORWARD_COLOR};background:{TAIL_BG}">{esc(tail.upper())}</span>')
    bars = []
    n = len(bind)
    for i, ch in enumerate(bind):
        ok = i < len(site) and _bases_match(ch, site[i])
        clamp = i >= n - 4
        if not ok:
            p.append(f'<span style="color:#ffffff;background:{MISMATCH_COLOR}">{ch}</span>')
            bars.append(f'<span style="color:{MISMATCH_COLOR}">x</span>')
        elif clamp:
            p.append(f'<span style="background:{CLAMP_COLOR}">{ch}</span>')
            bars.append("|")
        else:
            p.append(f'<span style="color:#1f4e9a">{ch}</span>')
            bars.append("|")
    primer_line = "5′ " + "".join(p)[3:] if False else (
        " " * lead + "5′ " if lead >= 0 else "")
    primer_line = (" " * max(0, lead)) + "5′ " + "".join(p[1:]) + " 3′"
    bar_line = " " * (len(left) + 3) + "".join(bars)
    top = "5′ " + esc(left) + f'<span style="background:#eef0f3">{esc(site)}</span>' + esc(right) + " 3′"
    comp_map = str.maketrans("ACGTRYKMBDHVNacgt", "TGCAYRMKVHDBNtgca")
    bottom = "3′ " + esc((left + site + right).translate(comp_map)) + " 5′"
    strand_note = ("template, top strand" if place.strand == "+"
                   else "template, bottom strand shown 5′→3′")
    body = "\n".join([primer_line, bar_line, top + "   " + strand_note, bottom])
    return f'<pre style="margin:0">{body}</pre>'


class EditPrimerDialog(QDialog):
    def __init__(self, primer: Primer, *, template: str = "", others: list[Primer] | None = None,
                 new: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Primer" if new else "Edit Primer")
        self.setMinimumSize(1000, 700)
        self._template = template or ""
        self._others = list(others or [])
        self._orig = primer
        self._sites: list[osq.Placement] = []
        self._history: list[str] = []
        self._hist_i = -1
        self._applying = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self._update)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(12)

        # One grid for the two rows: the labels in one column, Name and the
        # oligo start on one line, the two buttons are equal and end where the
        # "?" ends, and every field has the same height.
        top = QGridLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setHorizontalSpacing(10)
        top.setVerticalSpacing(8)
        top.addWidget(QLabel("Name", self), 0, 0)
        self.name_edit = QLineEdit(primer.name, self)
        self.name_edit.setFixedWidth(240)
        top.addWidget(self.name_edit, 0, 1)
        top.addWidget(QLabel("Note", self), 0, 2)
        self.note_edit = QLineEdit(primer.note, self)
        # Note runs up to the "?", which ends where Copy ends below it.
        note_row = QHBoxLayout()
        note_row.setContentsMargins(0, 0, 0, 0)
        note_row.setSpacing(10)
        note_row.addWidget(self.note_edit, 1)
        note_row.addWidget(make_help_button(self, "Edit Primer", EDIT_HELP))
        top.addLayout(note_row, 0, 3, 1, 3)

        top.addWidget(QLabel("Sequence", self), 1, 0)
        self.seq_edit = _OligoEdit("" if primer.sequence == "N" and new else primer.sequence, self)
        self.seq_edit.setFont(mono_font(4))
        self.seq_edit.setPlaceholderText("Type or paste the oligo, 5′ to 3′ (lower-case 5′ part = tail)")
        top.addWidget(self.seq_edit, 1, 1, 1, 3)
        self.rc_button = QPushButton("Reverse Complement", self)
        self.copy_button = QPushButton("Copy", self)
        # two equal buttons; Copy ends where the "?" ends
        button_w = max(self.rc_button.sizeHint().width(), self.copy_button.sizeHint().width())
        for column, button in ((4, self.rc_button), (5, self.copy_button)):
            button.setFixedWidth(button_w)
            top.addWidget(button, 1, column)
        top.setColumnStretch(3, 1)
        field_h = max(w.sizeHint().height()
                      for w in (self.name_edit, self.note_edit, self.seq_edit))
        for w in (self.name_edit, self.note_edit, self.seq_edit):
            w.setFixedHeight(field_h)
        root.addLayout(top)

        self.metrics = QLabel(self)
        self.metrics.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self.metrics)

        # ---- binding
        bind_box, bl = _box(self, "Binding")
        brow = QHBoxLayout()
        brow.setSpacing(8)
        brow.addWidget(QLabel("Site", bind_box))
        self.site_combo = QComboBox(bind_box)
        self.site_combo.setMinimumWidth(320)
        brow.addWidget(self.site_combo)
        brow.addStretch(1)
        brow.addWidget(QLabel("5′ end", bind_box))
        self.five_minus = QPushButton("−", bind_box)
        self.five_plus = QPushButton("+", bind_box)
        brow.addWidget(self.five_minus)
        brow.addWidget(self.five_plus)
        brow.addSpacing(12)
        brow.addWidget(QLabel("3′ end", bind_box))
        self.three_minus = QPushButton("−", bind_box)
        self.three_plus = QPushButton("+", bind_box)
        brow.addWidget(self.three_minus)
        brow.addWidget(self.three_plus)
        for b in (self.five_minus, self.five_plus, self.three_minus, self.three_plus):
            b.setFixedWidth(34)
        bl.addLayout(brow)
        self.binding_view = QLabel(bind_box)
        self.binding_view.setFont(mono_font(2))
        self.binding_view.setTextFormat(Qt.TextFormat.RichText)
        self.binding_view.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.binding_view.setStyleSheet("border: none;")
        self.binding_view.setMinimumHeight(96)
        bl.addWidget(self.binding_view)
        root.addWidget(bind_box)

        # ---- three boxes
        row = QHBoxLayout()
        row.setSpacing(12)
        tail_box, tl = _box(self, "5′ tail")
        kinds = QHBoxLayout()
        kinds.setSpacing(4)
        self._tail_group = QButtonGroup(self)
        self._tail_buttons = []
        for i, label in enumerate(("Restriction Site", "M13 / T7", "Own", "None")):
            b = QPushButton(label, tail_box)
            b.setCheckable(True)
            self._tail_group.addButton(b, i)
            kinds.addWidget(b)
            self._tail_buttons.append(b)
        self._tail_buttons[0].setChecked(True)
        tl.addLayout(kinds)
        self.tail_stack = QStackedWidget(tail_box)
        rs = QWidget()
        rsl = QVBoxLayout(rs)
        rsl.setContentsMargins(0, 0, 0, 0)
        rsl.setSpacing(6)
        er = QHBoxLayout()
        er.addWidget(QLabel("Enzyme", rs))
        self.enzyme_combo = QComboBox(rs)
        for e in rtail.TAIL_ENZYMES:
            try:
                self.enzyme_combo.addItem(osq.enzyme_label(e), e)
            except Exception:  # noqa: BLE001 - Biopython missing
                self.enzyme_combo.addItem(e, e)
        er.addWidget(self.enzyme_combo, 1)
        rsl.addLayout(er)
        pr = QHBoxLayout()
        pr.addWidget(QLabel("Padding", rs))
        self.pad_combo = QComboBox(rs)
        for label, pad in PAD_CHOICES:
            self.pad_combo.addItem(label, pad)
        pr.addWidget(self.pad_combo, 1)
        rsl.addLayout(pr)
        self.tail_stack.addWidget(rs)
        ps = QWidget()
        psl = QHBoxLayout(ps)
        psl.setContentsMargins(0, 0, 0, 0)
        psl.addWidget(QLabel("Tail", ps))
        self.preset_combo = QComboBox(ps)
        for k, v in osq.TAIL_PRESETS.items():
            self.preset_combo.addItem(k, v)
        psl.addWidget(self.preset_combo, 1)
        self.tail_stack.addWidget(ps)
        own = QWidget()
        ol = QHBoxLayout(own)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.addWidget(QLabel("Tail", own))
        self.own_tail = QLineEdit(own)
        self.own_tail.setFont(mono_font())
        self.own_tail.setPlaceholderText("5′ bases to add")
        ol.addWidget(self.own_tail, 1)
        self.tail_stack.addWidget(own)
        none = QWidget()
        nl = QHBoxLayout(none)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.addWidget(QLabel("Removes the tail: only the binding part is kept.", none))
        self.tail_stack.addWidget(none)
        tl.addWidget(self.tail_stack)
        self.tail_preview = QLabel(tail_box)
        self.tail_preview.setFont(mono_font())
        self.tail_preview.setTextFormat(Qt.TextFormat.RichText)
        self.tail_preview.setStyleSheet("border: none;")
        tl.addWidget(self.tail_preview)
        self.tail_note = QLabel(tail_box)
        self.tail_note.setWordWrap(True)
        self.tail_note.setTextFormat(Qt.TextFormat.RichText)
        self.tail_note.setStyleSheet("border: none;")
        tl.addWidget(self.tail_note)
        tl.addStretch(1)
        self.apply_tail = QPushButton("Apply Tail", tail_box)
        tl.addWidget(self.apply_tail, 0, Qt.AlignmentFlag.AlignLeft)
        row.addWidget(tail_box, 10)

        dim_box, dl = _box(self, "Dimers and hairpins")
        dr = QHBoxLayout()
        dr.addWidget(QLabel("Show", dim_box))
        self.dimer_combo = QComboBox(dim_box)
        dr.addWidget(self.dimer_combo, 1)
        dl.addLayout(dr)
        self.dimer_view = QLabel(dim_box)
        self.dimer_view.setFont(mono_font(-1))
        self.dimer_view.setTextFormat(Qt.TextFormat.RichText)
        self.dimer_view.setStyleSheet("QLabel { background: palette(alternate-base); border-radius: 6px;"
                                      " padding: 8px; border: none; }")
        self.dimer_view.setMinimumHeight(90)
        self.dimer_view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        dl.addWidget(self.dimer_view)
        self.dimer_note = QLabel(dim_box)
        self.dimer_note.setTextFormat(Qt.TextFormat.RichText)
        self.dimer_note.setWordWrap(True)
        self.dimer_note.setStyleSheet("border: none;")
        dl.addWidget(self.dimer_note)
        dl.addStretch(1)
        row.addWidget(dim_box, 13)

        site_box, sl = _box(self, "Other places it binds")
        self.sites_table = QTableWidget(0, 3, site_box)
        self.sites_table.setHorizontalHeaderLabels(["Where", "Mism.", "3′ exact"])
        self.sites_table.verticalHeader().hide()
        self.sites_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sites_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sites_table.setShowGrid(False)
        h = self.sites_table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        h.setStretchLastSection(True)
        self.sites_table.setColumnWidth(0, 150)
        self.sites_table.setColumnWidth(1, 50)
        sl.addWidget(self.sites_table)
        self.sites_note = QLabel("In the open sequence, up to 3 mismatches.", site_box)
        self.sites_note.setStyleSheet("color: palette(placeholder-text); border: none;")
        sl.addWidget(self.sites_note)
        row.addWidget(site_box, 10)
        root.addLayout(row, 1)

        root.addWidget(_hrule(self))
        bottom = QHBoxLayout()
        self.undo_button = QPushButton("Undo", self)
        self.redo_button = QPushButton("Redo", self)
        bottom.addWidget(self.undo_button)
        bottom.addWidget(self.redo_button)
        bottom.addSpacing(16)
        self.db_check = QCheckBox("Also save to the Primer Database", self)
        bottom.addWidget(self.db_check)
        bottom.addStretch(1)
        self.cancel_button = QPushButton("Cancel", self)
        self.save_button = QPushButton("Save", self)
        self.save_button.setDefault(True)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.save_button)
        root.addLayout(bottom)

        self.seq_edit.textChanged.connect(self._on_text)
        self.name_edit.textChanged.connect(lambda _t: self._sync_save())
        self.rc_button.clicked.connect(self._on_rc)
        self.copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(self.seq_edit.text()))
        self.site_combo.currentIndexChanged.connect(lambda _i: self._render_binding())
        self.five_minus.clicked.connect(lambda: self._resize(-1, 0))
        self.five_plus.clicked.connect(lambda: self._resize(1, 0))
        self.three_minus.clicked.connect(lambda: self._resize(0, -1))
        self.three_plus.clicked.connect(lambda: self._resize(0, 1))
        self._tail_group.idClicked.connect(self._on_tail_kind)
        for w in (self.enzyme_combo, self.pad_combo, self.preset_combo):
            w.currentIndexChanged.connect(lambda _i: self._update_tail_preview())
        self.own_tail.textChanged.connect(lambda _t: self._update_tail_preview())
        self.apply_tail.clicked.connect(self._on_apply_tail)
        self.dimer_combo.currentIndexChanged.connect(lambda _i: self._render_dimer())
        self.sites_table.cellClicked.connect(lambda r, _c: self.site_combo.setCurrentIndex(r))
        self.undo_button.clicked.connect(lambda: self._step_history(-1))
        self.redo_button.clicked.connect(lambda: self._step_history(1))
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._on_save)

        tail = th.split_tail(primer.sequence)[0].upper()
        for i in range(self.enzyme_combo.count()):
            try:
                if tail and osq.enzyme_site(str(self.enzyme_combo.itemData(i))) in tail:
                    self.enzyme_combo.setCurrentIndex(i)
                    break
            except Exception:  # noqa: BLE001
                break
        self._record_history(self.seq_edit.text())
        self._report = None
        self._update()
        self.seq_edit.setFocus()

    # ---------------------------------------------------------------- results

    def primer(self) -> Primer:
        seq = th.clean_oligo(self.seq_edit.text())
        return Primer(name=self.name_edit.text().strip() or self._orig.name, sequence=seq,
                      kind=self._orig.kind if self._orig.sequence != "N" else "",
                      note=self.note_edit.text().strip(), source=self._orig.source,
                      extra=dict(self._orig.extra))

    def save_to_database(self) -> bool:
        return self.db_check.isChecked()

    # ---------------------------------------------------------------- history

    def _record_history(self, text: str) -> None:
        if self._history and self._hist_i >= 0 and self._history[self._hist_i] == text:
            return
        del self._history[self._hist_i + 1:]
        self._history.append(text)
        self._hist_i = len(self._history) - 1
        self._sync_history_buttons()

    def _sync_history_buttons(self) -> None:
        self.undo_button.setEnabled(self._hist_i > 0)
        self.redo_button.setEnabled(self._hist_i < len(self._history) - 1)

    def _step_history(self, step: int) -> None:
        i = self._hist_i + step
        if 0 <= i < len(self._history):
            self._hist_i = i
            self._applying = True
            self.seq_edit.setText(self._history[i])
            self._applying = False
            self._sync_history_buttons()
            self._update()

    def _set_sequence(self, seq: str) -> None:
        self.seq_edit.setText(seq)
        self._record_history(seq)
        self._update()

    # ---------------------------------------------------------------- events

    def _on_text(self, _text: str) -> None:
        if self._applying:
            return
        self._timer.start()

    def _clean(self) -> str | None:
        try:
            return th.clean_oligo(self.seq_edit.text())
        except th.PrimerError as exc:
            self.metrics.setText(f'<span style="color:{MISMATCH_COLOR}">{html.escape(str(exc))}</span>')
            return None

    def _update(self) -> None:
        seq = self._clean()
        self._sync_save()
        if seq is None:
            return
        if not seq:
            self.metrics.setText('<span style="color:gray">Type the primer to see where it binds.</span>')
            self.binding_view.setText("")
            self.site_combo.clear()
            self.sites_table.setRowCount(0)
            self.dimer_combo.clear()
            self.dimer_view.setText("")
            self.dimer_note.setText("")
            self._update_tail_preview()
            return
        if self._template and not th.split_tail(seq)[0] and len(seq) >= 15:
            guessed = osq.guess_tail(seq, self._template)
            if guessed != seq:
                self._applying = True
                pos = self.seq_edit.cursorPosition()
                self.seq_edit.setText(guessed)
                self.seq_edit.setCursorPosition(pos)
                self._applying = False
                seq = guessed
        self._record_history(seq)
        others = list(self._others)
        prim = Primer(name=self.name_edit.text().strip() or "primer", sequence=seq)
        self._report = osq.analyse_primer(prim, self._template, others=others)
        rep = self._report
        self._fill_sites(seq)
        parts = [f"<b>{rep.length}</b>-mer · <b>{rep.annealed}</b> annealed"]
        if rep.tail:
            parts[0] += f" · <b>{rep.tail}</b> tail"
        parts.append(f"<b>{rep.gc:.0f}</b> % GC")
        place = rep.placement
        if place is not None:
            parts.append(f"Binding site <b>{place.start:,}..{place.end:,}</b> "
                         f"({'→' if place.strand == '+' else '←'})")
        elif self._template:
            parts.append(f'<span style="color:{CHECK_COLOR}">does not bind the open sequence</span>')
        parts.append(f"Tm annealed <b>{fmt_tm(rep.tm_annealed)}</b>")
        if rep.tail:
            parts.append(f"Tm full <b>{fmt_tm(rep.tm_full)}</b>")
        self.metrics.setText("&nbsp;&nbsp;·&nbsp;&nbsp;".join(parts))
        self._render_binding()
        self._fill_dimers()
        self._update_tail_preview()

    def _sync_save(self) -> None:
        ok = bool(self.name_edit.text().strip())
        try:
            ok = ok and bool(th.clean_oligo(self.seq_edit.text()))
        except th.PrimerError:
            ok = False
        self.save_button.setEnabled(ok)

    def _fill_sites(self, seq: str) -> None:
        self._sites = []
        if self._template:
            bind_len = len(th.binding_part(seq))
            tail_len = len(seq) - bind_len
            try:
                found = osq.find_all_sites(seq, self._template, max_mismatches=3,
                                           three_prime_exact=0)
            except Exception:  # noqa: BLE001
                found = []
            found.sort(key=lambda s: osq._rank(s, bind_len))
            self._sites = [osq._site_to_placement(s, bind_len, tail_len) for s in found[:200]]
        prev = self.site_combo.currentIndex()
        self.site_combo.blockSignals(True)
        self.site_combo.clear()
        for i, s in enumerate(self._sites):
            label = (f"{'Best site' if i == 0 else 'Site'}: {s.start:,}..{s.end:,} "
                     f"{'→' if s.strand == '+' else '←'} · {s.mismatches} mm")
            self.site_combo.addItem(label)
        if 0 <= prev < len(self._sites):
            self.site_combo.setCurrentIndex(prev)
        self.site_combo.blockSignals(False)
        self.sites_table.setRowCount(len(self._sites))
        for r, s in enumerate(self._sites):
            self.sites_table.setItem(r, 0, QTableWidgetItem(
                f"{s.start:,} {'+' if s.strand == '+' else '−'}"))
            self.sites_table.setItem(r, 1, QTableWidgetItem(str(s.mismatches)))
            self.sites_table.setItem(r, 2, QTableWidgetItem(str(s.three_exact)))
        for b in (self.five_minus, self.five_plus, self.three_minus, self.three_plus):
            b.setEnabled(bool(self._sites))

    def _current_site(self) -> osq.Placement | None:
        i = self.site_combo.currentIndex()
        if 0 <= i < len(self._sites):
            return self._sites[i]
        return None

    def _render_binding(self) -> None:
        site = self._current_site()
        seq = self._clean()
        if not seq:
            return
        if site is None:
            if self._template:
                self.binding_view.setText('<span style="color:gray">No site with up to 3 mismatches '
                                          "in the open sequence.</span>")
            else:
                self.binding_view.setText('<span style="color:gray">No sequence open.</span>')
            return
        self.binding_view.setText(binding_html(seq, site, self._template))

    def _resize(self, five: int, three: int) -> None:
        site = self._current_site()
        seq = self._clean()
        if site is None or not seq:
            return
        self._set_sequence(osq.resize_on_template(seq, site, self._template, five, three))

    def _on_rc(self) -> None:
        seq = self._clean()
        if seq:
            self._set_sequence(th.reverse_complement(seq.upper()))

    # ---------------------------------------------------------------- tails

    def _on_tail_kind(self, idx: int) -> None:
        self.tail_stack.setCurrentIndex(idx)
        self._update_tail_preview()

    def _chosen_tail(self) -> str:
        kind = self._tail_group.checkedId()
        if kind == 0:
            enz = str(self.enzyme_combo.currentData())
            pad = self.pad_combo.currentData()
            try:
                if pad == PAD_AUTO:
                    return rtail.tail_for(enz, None, th.binding_part(self._clean() or ""))
                return osq.restriction_tail(enz, str(pad or ""))
            except Exception:  # noqa: BLE001
                return ""
        if kind == 1:
            return str(self.preset_combo.currentData() or "").lower()
        if kind == 2:
            try:
                return th.clean_oligo(self.own_tail.text()).lower()
            except th.PrimerError:
                return ""
        return ""

    def _update_tail_preview(self) -> None:
        seq = self._clean() or ""
        tail = self._chosen_tail()
        bind = th.binding_part(seq) if seq else ""
        shown = bind[:12] + ("…" if len(bind) > 12 else "")
        self.tail_preview.setText(
            f'<span style="color:{FORWARD_COLOR}">{html.escape(tail.upper())}</span>'
            f'<span style="color:gray">|</span>{html.escape(shown)}')
        self.tail_note.setText(self._tail_note(tail, bind))

    def _tail_note(self, tail: str, bind: str) -> str:
        """What is wrong with this tail, in plain words (green when nothing is)."""
        if self._tail_group.checkedId() != 0:
            return ""
        enz = str(self.enzyme_combo.currentData())
        try:
            warnings = rtail.tail_warnings(tail.lower() + (bind or "N"), insert=self._template,
                                        insert_name="open sequence")
            free = rtail.free_enzymes(self._template) if self._template else []
        except Exception:  # noqa: BLE001 - advice only
            warnings, free = [], []
        if warnings:
            note = "<br>".join(f'<span style="color:{CHECK_COLOR}">{html.escape(w)}.</span>'
                               for w in warnings)
        elif self._template:
            note = (f'<span style="color:{OK_COLOR}">{html.escape(enz)} does not cut the open '
                    "sequence, and the tail has 6 bases before the site.</span>")
        else:
            note = ""
        if free and any("also cuts" in w for w in warnings):
            note += "<br>Not cutting here: " + ", ".join(free)
        return note

    def _on_apply_tail(self) -> None:
        seq = self._clean()
        if not seq:
            return
        self._set_sequence(osq.with_tail(seq, self._chosen_tail()))

    # ---------------------------------------------------------------- dimers

    def _fill_dimers(self) -> None:
        prev = self.dimer_combo.currentText()
        self.dimer_combo.blockSignals(True)
        self.dimer_combo.clear()
        self.dimer_combo.addItem("Self-dimer", "self")
        self.dimer_combo.addItem("Hairpin", "hairpin")
        rep = self._report
        if rep is not None:
            for name in rep.cross:
                self.dimer_combo.addItem(f"With {name}", name)
        i = self.dimer_combo.findText(prev)
        self.dimer_combo.setCurrentIndex(max(0, i))
        self.dimer_combo.blockSignals(False)
        self._render_dimer()

    def _render_dimer(self) -> None:
        rep = self._report
        if rep is None:
            return
        key = self.dimer_combo.currentData()
        if key == "self":
            st, limit = rep.self_dimer, th.WARN_DIMER_DG
        elif key == "hairpin":
            st, limit = rep.hairpin, th.WARN_HAIRPIN_DG
        else:
            st, limit = rep.cross.get(str(key)), th.WARN_DIMER_DG
        if st is None or not st.found:
            self.dimer_view.setText('<span style="color:gray">No stable structure.</span>')
            self.dimer_note.setText(f"ΔG 0 {status_html('ok')}")
            return
        body = html.escape("\n".join(st.lines))
        self.dimer_view.setText(f'<pre style="margin:0">{body}</pre>')
        status = osq.dg_status(st.dg, limit=limit)
        self.dimer_note.setText(f"ΔG <b>{st.dg:.1f} kcal/mol</b> · Tm {st.tm:.0f} °C · "
                                f"{status_html(status)}")

    # ---------------------------------------------------------------- save

    def _on_save(self) -> None:
        if not self.save_button.isEnabled():
            return
        self.accept()


class PickPrimersDialog(QDialog):
    """Choose saved primers from the Primer Database (Cancel / Add)."""

    def __init__(self, database_path: Path | None, *, template: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Primers from the Database")
        self.setMinimumSize(720, 520)
        self._template = template or ""
        self._all: list[Primer] = []
        self._error = ""
        try:
            from repeatviewer.backends.primers.inventory import open_database

            db = open_database(database_path)
            self._all = list(db.primers)
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(10)
        top = QHBoxLayout()
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText("Filter by name, sequence, target, note…")
        self.filter.setClearButtonEnabled(True)
        self.filter.setMaximumWidth(320)
        top.addWidget(self.filter)
        self.binding_only = QCheckBox("Only primers that bind the open sequence", self)
        self.binding_only.setEnabled(bool(self._template))
        top.addWidget(self.binding_only)
        top.addStretch(1)
        lay.addLayout(top)
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["Name", "Length", "Binds here", "Where it is"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        h.setStretchLastSection(True)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 140)
        lay.addWidget(self.table, 1)
        self.note = QLabel(self)
        self.note.setStyleSheet("color: palette(placeholder-text);")
        lay.addWidget(self.note)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.cancel_button = QPushButton("Cancel", self)
        self.add_button = QPushButton("Add", self)
        self.add_button.setDefault(True)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.add_button)
        lay.addLayout(bottom)
        self._binds: dict[str, str] = {}
        if self._template and len(self._all) <= 3000:
            for p in self._all:
                try:
                    pl = osq.place_primer(p.sequence, self._template, max_mismatches=2)
                except Exception:  # noqa: BLE001
                    pl = None
                self._binds[p.name] = ("" if pl is None else
                                       f"{'→' if pl.strand == '+' else '←'} {pl.start:,}"
                                       f"{'' if not pl.mismatches else f' ({pl.mismatches} mm)'}")
        self.filter.textChanged.connect(lambda _t: self._fill())
        self.binding_only.toggled.connect(lambda _c: self._fill())
        self.table.cellDoubleClicked.connect(lambda _r, _c: self.accept())
        self.cancel_button.clicked.connect(self.reject)
        self.add_button.clicked.connect(self.accept)
        self._fill()

    def _fill(self) -> None:
        q = self.filter.text().strip().lower()
        rows = []
        for p in self._all:
            hay = " ".join([p.name, p.sequence, p.note, " ".join(str(v) for v in p.extra.values())]).lower()
            if q and q not in hay:
                continue
            if self.binding_only.isChecked() and not self._binds.get(p.name):
                continue
            rows.append(p)
        self._rows = rows
        self.table.setRowCount(len(rows))
        for r, p in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(p.name))
            self.table.setItem(r, 1, QTableWidgetItem(str(len(p.sequence))))
            self.table.setItem(r, 2, QTableWidgetItem(self._binds.get(p.name, "") or "–"))
            e = p.extra or {}
            where = " · ".join(str(e[k]) for k in ("box", "freezer", "status") if e.get(k))
            self.table.setItem(r, 3, QTableWidgetItem(where))
        if self._error:
            self.note.setText(f"Could not open the Primer Database: {self._error}")
        else:
            self.note.setText(f"{len(rows)} of {len(self._all)} primers")

    def primers(self) -> list[Primer]:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self._rows[r] for r in rows if 0 <= r < len(self._rows)]


class DesignedPairsDialog(QDialog):
    """After Primer Design: tick the pairs (or FISH probes) to put on the sequence
    (Cancel / Add to Sequence)."""

    def __init__(self, pairs: list[dict], inputs: list[Path], *,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Designed Primers")
        self.setMinimumSize(900, 460)
        self._pairs = [p for p in pairs if p.get("forward") or p.get("reverse") or p.get("probe")]
        self._inputs = [Path(p) for p in inputs]
        # FISH oligo runs give single probes, not pairs
        probes = bool(self._pairs) and all(
            not (p.get("forward") or p.get("reverse")) for p in self._pairs)
        what = "probe(s)" if probes else "pair(s)"
        if probes:
            self.setWindowTitle("Designed Probes")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(10)
        head = QHBoxLayout()
        title = QLabel(f"<b>{len(self._pairs)} {what} designed.</b> Tick the ones to add to the "
                       "sequence (arrows on the sequence, Primers tab).", self)
        title.setWordWrap(True)
        head.addWidget(title, 1)
        head.addWidget(make_help_button(
            self, "Designed Primers",
            "The full results stay in the report. <b>Add to Sequence</b> keeps the ticked "
            "primers with their FASTA (Annotation view &gt; Primers) and draws them where they "
            "bind. The best pair of each sequence is ticked.<br>Nothing is written to the "
            "file until you press <b>Add to Sequence</b>."))
        lay.addLayout(head)
        cols = (["", "Probe", "Sequence", "Position", "Probe 5′→3′", "Length", "Tm"] if probes
                else ["", "Pair", "Sequence", "Product", "Forward", "Reverse", "Tm F / R"])
        self.table = QTableWidget(len(self._pairs), len(cols), self)
        self.table.setHorizontalHeaderLabels(cols)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        h.setStretchLastSection(True)
        for c, w in enumerate((28, 160, 120, 100, 380, 60) if probes
                              else (28, 120, 120, 70, 220, 220)):
            self.table.setColumnWidth(c, w)
        seen_templates: set[str] = set()
        for r, p in enumerate(self._pairs):
            tick = QTableWidgetItem()
            tick.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            tpl = str(p.get("template", ""))
            best = tpl not in seen_templates and p.get("group", "") in ("", "M", "target")
            if best:
                seen_templates.add(tpl)
            tick.setCheckState(Qt.CheckState.Checked if best else Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, tick)
            f = p.get("forward") or {}
            rv = p.get("reverse") or {}
            pr = p.get("probe") or {}
            if probes:
                vals = [p.get("name", ""), tpl, f"{pr.get('start', '')}–{pr.get('end', '')}",
                        pr.get("sequence", ""), f"{pr.get('length', '')} nt",
                        f"{pr.get('tm', 0):.1f} °C"]
                mono_cols = (4,)
            else:
                vals = [p.get("name", ""), tpl, f"{p.get('product_size', '')} bp",
                        f.get("sequence", ""), rv.get("sequence", ""),
                        f"{f.get('tm', 0):.1f} / {rv.get('tm', 0):.1f}" if f and rv else ""]
                mono_cols = (4, 5)
            for c, v in enumerate(vals, start=1):
                item = QTableWidgetItem(str(v))
                if c in mono_cols:
                    item.setFont(mono_font(-1))
                self.table.setItem(r, c, item)
        lay.addWidget(self.table, 1)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.cancel_button = QPushButton("Cancel", self)
        self.add_button = QPushButton("Add to Sequence", self)
        self.add_button.setDefault(True)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.add_button)
        lay.addLayout(bottom)
        self.cancel_button.clicked.connect(self.reject)
        self.add_button.clicked.connect(self.accept)

    def ticked_pairs(self) -> list[dict]:
        out = []
        for r, p in enumerate(self._pairs):
            item = self.table.item(r, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                out.append(p)
        return out

    def add_ticked(self) -> list[Path]:
        """Write the ticked pairs onto their FASTA files; returns the files changed."""
        from repeatviewer.backends.primers import binding as bd

        ids: dict[str, Path] = {}
        for path in self._inputs:
            try:
                for rid, _seq in bd.iter_fasta(path):
                    ids.setdefault(rid, path)
            except OSError:
                continue
        changed: list[Path] = []
        for p in self.ticked_pairs():
            tpl = str(p.get("template", ""))
            # a consensus / representative template is not a record id: the design
            # always runs on the first selected file
            path = ids.get(tpl) or ids.get(tpl.split()[0] if tpl else "") or (
                self._inputs[0] if self._inputs else None)
            if path is None:
                continue
            osq.add_primers_to_fasta(path, osq.primers_of_pair(p),
                                     record_id=tpl if tpl in ids else None)
            if path not in changed:
                changed.append(path)
        return changed

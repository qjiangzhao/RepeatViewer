"""The Primers and Probes workspace: one tab for the primer work on a sequence.

Tools > Primers and Probes used to show its panel inside the Annotation view's
side rail, where a click on Display, Annotation, Find or Others replaced it and
nothing brought it back. The workspace is a tab of its own: a row of sections on
top (the menu item that was clicked is the one selected), the sequence it works
on, the sequence map, and the settings of the section on the right. Nothing in
it can be switched away by the rail, because the rail's tab strip is not shown.

The sequence view and the panel are the ones the Annotation view uses
(``SequenceMapPanel`` and its ``PrimersPanel``), so every primer function works
as before.

Developer: Abdullah Yusuf
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

TAB_NAME = "Primers and Probes"

SECTION_DESIGN = "design"
SECTION_PAINTING = "painting"
SECTION_MAP = "map"
SECTION_DATABASE = "database"
SECTION_PCR = "pcr"
SECTION_DIGEST = "digest"
SECTION_GEL = "gel"
SECTION_SANGER = "sanger"
SECTION_CLONING = "cloning"
SECTIONS: tuple[tuple[str, str], ...] = (
    (SECTION_DESIGN, "Design"),
    (SECTION_PAINTING, "Painting"),
    (SECTION_MAP, "Map"),
    (SECTION_DATABASE, "Database"),
    (SECTION_PCR, "PCR"),
    (SECTION_DIGEST, "Digest"),
    (SECTION_GEL, "Gel"),
    (SECTION_SANGER, "Sanger Check"),
    (SECTION_CLONING, "Cloning"),
)
# Sections that work on the sequence (its map, the list under it, the panel).
# The others are whole pages of their own, put into the workspace when opened.
SEQUENCE_SECTIONS = (SECTION_DESIGN, SECTION_PCR, SECTION_DIGEST)
NO_SEQUENCE_TEXT = (
    "Click a FASTA's name in Files to choose the sequence to work on."
)

# Pages of the PrimersPanel behind each section. Design holds two for now: the
# design settings and the primers on the sequence.
PANEL_DESIGN, PANEL_PRIMER, PANEL_PCR, PANEL_ENZYMES = range(4)
_PANEL_PAGES: dict[str, tuple[int, ...]] = {
    SECTION_DESIGN: (PANEL_DESIGN, PANEL_PRIMER),
    SECTION_PCR: (PANEL_PCR,),
    SECTION_DIGEST: (PANEL_ENZYMES,),
}

FASTA_FILTER = (
    "FASTA (*.fa *.fasta *.fna *.fas *.fsa *.ffn *.seq *.aln *.mfa *.gz);;All files (*)"
)


SEQUENCE_HELP = (
    "<b>Sequence</b>: the file the workspace works on. Click a FASTA's name in Files to "
    "use it, or press Browse. Ticking a file's box does not change it.<br>"
    "<b>Record</b>: for a file with several sequences, the one to work on.<br>"
    "To open a file in a tab of its own instead, right-click it in Files and choose "
    "Open in Additional Tab."
)
SETTINGS_HEADER_HELP = (
    "The design settings are shown as one line while a primer is selected, to make room "
    "for its details.<br>"
    "<b>Show</b>: opens all settings again.<br>"
    "<b>Restore Defaults</b>: puts every setting back to its default.<br>"
    "<b>Design</b>: runs the design again with these settings. Primers already on the "
    "sequence are kept."
)
LIST_HELP = (
    "One list for what Design found and for the primers already on this sequence.<br>"
    "<b>candidate</b>: found by the last Design run. Click it to see it on the sequence, "
    "tick the ones to keep and press <b>Keep Ticked</b>. Nothing is written before that.<br>"
    "<b>on the sequence</b>: a primer of this sequence. Click it to see its details on "
    "the right and its binding site on the map; the tick marks the primers that PCR uses. "
    "Right-click it to edit, copy, save to the Primer Database or remove it.<br>"
    "<b>Add Primer</b>, <b>From Database</b>: put a primer on the sequence by hand, or "
    "from your saved primers.<br>"
    "<b>From Selection</b>: drag over 10 to 60 bases on the sequence, then choose "
    "Forward Primer (the bases as they are) or Reverse Primer (their reverse "
    "complement). The primer appears on the sequence and can be dragged or edited.<br>"
    "<b>Open Report</b>: writes the usual primer report for the last Design run."
)


from repeatviewer.widgets.primer_design_pane import MiddleElideCombo as _RecordCombo  # noqa: E402


def _path_row_of(widget):
    """The PathBrowseRow a focused widget belongs to, or None."""
    from repeatviewer.widgets.path_browse import PathBrowseRow

    while widget is not None:
        if isinstance(widget, PathBrowseRow):
            return widget
        widget = widget.parentWidget()
    return None


def section_of_panel_page(index: int) -> str:
    """The section a page of the PrimersPanel belongs to."""
    for key, pages in _PANEL_PAGES.items():
        if int(index) in pages:
            return key
    return SECTION_DESIGN


def section_key(name: str | None) -> str:
    """A section key from what a caller passes ("enzymes" and "primer" are old names)."""
    text = str(name or "").strip().lower()
    if text in ("enzymes", "digest"):
        return SECTION_DIGEST
    if text in ("sanger", "sanger check"):
        return SECTION_SANGER
    for key, _label in SECTIONS:
        if text == key:
            return key
    return SECTION_DESIGN


def same_file(a: Path | str | None, b: Path | str | None) -> bool:
    if not a or not b:
        return False
    try:
        return Path(a).expanduser().resolve() == Path(b).expanduser().resolve()
    except OSError:
        return str(a) == str(b)


class PrimersWorkspacePage(QWidget):
    """A tool tab: sections, the sequence, its map and the section's settings."""

    statusMessage = Signal(str)
    annotationsSaved = Signal(object)    # path of the annotation file just written
    sequenceExtracted = Signal(object)   # path of a FASTA written from the map
    sequenceChanged = Signal(object)     # Path of the sequence now worked on

    sectionRequested = Signal(str)       # a section with no page yet: the window opens it
    openFileRequested = Signal(object)   # a file to open in RepeatViewer (from a gel)
    fileWritten = Signal(object)         # a file written by a hosted page (a gel)

    def __init__(self, fasta_path: Path | None = None, parent: QWidget | None = None, *,
                 section: str = SECTION_DESIGN) -> None:
        super().__init__(parent)
        from repeatviewer.widgets.help_button import make_help_button
        from repeatviewer.widgets.path_browse import PathBrowseRow

        # A tool page, not the preview of a file: the tabs must never treat it
        # as the page of the FASTA it works on.
        self.path = None
        self._syncing = False
        self._sequence_path: Path | None = None
        self.panel = None                 # the sequence view, made with the first sequence
        self.primers = None               # its PrimersPanel
        self._armed_row = None
        self._hosted: dict[str, QWidget] = {}
        self._shown_section = SECTION_DESIGN
        # Called for the sequence to work on when a sequence section is shown
        # and there is none yet (the FASTA selected in Files).
        self.sequence_provider = None
        # Inside a tab a page does not paint its own background, and the white
        # Preview page would show through.
        self.setAutoFillBackground(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sections = QTabBar(self)
        self.sections.setObjectName("PrimersWorkspaceSections")
        self.sections.setExpanding(False)
        self.sections.setDrawBase(False)
        # The first letter of the first section, the start of the blue line
        # under the chosen one and the left edge of the boxes below share one
        # vertical line, 12 px in. The line runs under the word, with a little
        # room on the right for the bolder letters of the chosen section.
        self.sections.setStyleSheet(
            "QTabBar#PrimersWorkspaceSections::tab"
            " { padding: 6px 6px 6px 0px; margin: 0px 6px 0px 12px; }")
        for key, label in SECTIONS:
            index = self.sections.addTab(label)
            self.sections.setTabData(index, key)
        root.addWidget(self.sections)

        self.body = QStackedWidget(self)
        root.addWidget(self.body, 1)
        self.seq_page = QWidget(self.body)
        self._seq_layout = QVBoxLayout(self.seq_page)
        self._seq_layout.setContentsMargins(0, 0, 0, 0)
        self._seq_layout.setSpacing(0)
        self.body.addWidget(self.seq_page)
        # The file comes from a click on its name in Files. The field that
        # used to show it stays as the (hidden) holder of the path.
        self.sequence_row = PathBrowseRow(
            self.seq_page,
            browse_title="Choose the Sequence to Work On",
            file_filter=FASTA_FILTER,
            elide_middle=True,
            minimum_width=260,
        )
        self.sequence_row.setMaximumWidth(460)
        self.sequence_row.set_default_tooltip(
            "The file the workspace works on. Click a FASTA's name in Files to use it, "
            "or press Browse."
        )
        self.sequence_row.hide()
        # Record sits in the Position row of the map once there is a map.
        self.record_label = QLabel("Record:", self.seq_page)
        self.record_combo = _RecordCombo(self.seq_page)
        self.record_combo.setFixedWidth(104)
        self.record_combo.currentIndexChanged.connect(
            lambda _i: self.record_combo.setToolTip(self.record_combo.currentText()))
        # the chooser needs no word before it
        self.record_label.setFixedSize(0, 0)
        self.length_label = QLabel("", self.seq_page)
        self.length_label.hide()
        self.record_combo.setToolTip("For a file with several sequences: the one to work on.")
        self.record_label.hide()
        self.record_combo.hide()
        self.no_sequence = QLabel(NO_SEQUENCE_TEXT, self.seq_page)
        self.no_sequence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_sequence.setWordWrap(True)
        self.no_sequence.setStyleSheet("color: palette(placeholder-text);")
        self._seq_layout.addWidget(self.no_sequence, 1)

        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_focus_changed)
        self.sections.currentChanged.connect(self._on_section_changed)
        self.record_combo.activated.connect(self._on_record_chosen)
        self.sequence_row.path_changed.connect(self._on_sequence_field_changed)

        if fasta_path is not None:
            self.set_sequence(fasta_path)
        self.set_section(section, page=PANEL_DESIGN)

    def _build_sequence_part(self, path: Path) -> None:
        """The sequence view, the list under it and the panel: made once."""
        from repeatviewer.widgets.sequence_map_viewer import SequenceMapPanel

        self.panel = SequenceMapPanel(path, self.seq_page, autoload=False)
        self._seq_layout.addWidget(self.panel, 1)
        self.panel.statusMessage.connect(self._on_panel_status)
        self.panel.annotationsSaved.connect(self.annotationsSaved.emit)
        self.panel.sequenceExtracted.connect(self.sequenceExtracted.emit)
        self.panel.activeSequenceChanged.connect(self._on_panel_record_changed)
        self.primers = self.panel.primers_panel()
        from PySide6.QtWidgets import QSizePolicy

        from repeatviewer.widgets.primer_design_pane import _relax_wrapped_labels

        # Long names and sequences must not make the panel want more width
        # than it has (its boxes would be squeezed), nor the row above the map.
        _relax_wrapped_labels(self.primers)
        for widget in (getattr(self.primers, "name_label", None),):
            if widget is not None:
                policy = widget.sizePolicy()
                policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
                widget.setSizePolicy(policy)
        self._place_record_chooser()
        self._plain_settings_side()
        self._build_list_area()
        self._guard_wheels()

    # --------------------------------------------- the wheel changes no value

    def _guard_wheels(self) -> None:
        """Number boxes, drop-down menus and sliders ignore the mouse wheel.

        A value changes with a click only; the wheel scrolls the panel.
        """
        from PySide6.QtWidgets import QAbstractSpinBox, QSlider

        for kind in (QAbstractSpinBox, QComboBox, QSlider):
            for w in self.findChildren(kind):
                if not w.property("rvNoWheel"):
                    w.setProperty("rvNoWheel", True)
                    w.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Wheel and obj.property("rvNoWheel"):
            event.ignore()          # the scroll area around it takes the wheel
            return True
        return super().eventFilter(obj, event)

    def _place_record_chooser(self) -> None:
        """The row above the map, made to fit: zoom, two position boxes, Select,
        Fit, the record chooser and the length. Words that are not needed go."""
        tool = getattr(self.panel._map, "_toolbar", None)
        bar = tool.layout() if tool is not None else None
        several = self.record_combo.count() > 1
        if bar is None:
            row = QHBoxLayout()
            row.setContentsMargins(12, 6, 12, 6)
            row.setSpacing(8)
            row.addWidget(self.record_combo)
            row.addStretch(1)
            row.addWidget(self.length_label)
            self._seq_layout.insertLayout(0, row)
        else:
            view = self.panel._map
            # "Position:" goes, "to" becomes a thin dash between the two boxes
            for label in tool.findChildren(QLabel):
                text = label.text().strip()
                if text == "Position:":
                    label.setText("")
                    label.setFixedWidth(0)
                elif text == "to":
                    label.setText("–")
                    label.setFixedWidth(10)
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # room for five digits; a longer number scrolls inside its box
            for box, tip in ((getattr(view, "_pos_start", None), "Start"),
                             (getattr(view, "_pos_end", None), "End")):
                if box is not None:
                    box.setFixedWidth(66)
                    box.setToolTip(tip)
            slider = getattr(view, "_zoom_slider", None)
            if slider is not None:
                slider.setFixedWidth(90)
            # the length alone replaces "Length: … GC: …"
            stats = getattr(view, "_sequence_stats_label", None)
            if stats is not None:
                stats.setFixedWidth(0)
            self.record_combo.setMaximumHeight(22)
            at = max(0, bar.count() - 2)            # before the stretch
            bar.insertSpacing(at, 6)
            bar.insertWidget(at + 1, self.record_combo, 0, Qt.AlignmentFlag.AlignVCenter)
            bar.addWidget(self.length_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.length_label.show()
        self.record_label.setVisible(False)
        self.record_combo.setVisible(several)
        self._sync_length()

    def _sync_length(self) -> None:
        """The length of the shown record, as the map states it ("509 bp")."""
        import re

        stats = getattr(self.panel._map, "_sequence_stats_label", None) if self.panel else None
        try:
            found = re.search(r"Length:\s*([\d.,\u00a0\u202f ]*\d\s*[kMG]?bp)",
                              stats.text() if stats is not None else "")
        except RuntimeError:
            found = None
        self.length_label.setText(found.group(1).strip() if found else "")

    def _plain_settings_side(self) -> None:
        """No line between the map and the settings: the two colours say it."""
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QFrame

        rail = self.panel._rail
        pal = rail.palette()
        pal.setColor(QPalette.ColorRole.Window, self.palette().color(QPalette.ColorRole.Window))
        rail.setPalette(pal)
        rail.setAutoFillBackground(True)
        lines = [getattr(rail, "_divider", None),
                 self.panel.findChild(QFrame, "annotationMapRailDivider")]
        for line in lines:
            if line is not None:
                line.setFixedWidth(0)
                line.hide()
        self._build_settings_header()
        self.primers.tabs.currentChanged.connect(self._on_panel_page_changed)

    def has_sequence(self) -> bool:
        return self.panel is not None and self._sequence_path is not None

    def _on_panel_status(self, text: str) -> None:
        # Changing the sequence ends a Transfer session the view never had here;
        # its notice would only confuse.
        if str(text).startswith("Transfer stopped"):
            return
        self.statusMessage.emit(str(text))

    # ------------------------------------------------------------------ naming

    def tab_name(self) -> str:
        return TAB_NAME

    def sequence_path(self) -> Path | None:
        """The FASTA worked on, or None when no sequence was chosen yet."""
        return self._sequence_path

    def primers_panel(self):
        return self.primers

    # ---------------------------------------------------------------- sections

    def section(self) -> str:
        """The section that is shown."""
        return self._shown_section

    def _select_in_bar(self, key: str) -> None:
        self._syncing = True
        try:
            for index in range(self.sections.count()):
                if self.sections.tabData(index) == key:
                    self.sections.setCurrentIndex(index)
                    break
        finally:
            self._syncing = False

    def set_section(self, section: str, *, page: int | None = None) -> bool:
        """Show ``section``. False when it has nothing to show (its page was not opened).

        Design has two panel pages (settings, the selected primer): it keeps the
        one it was on, unless ``page`` names one.
        """
        key = section_key(section)
        if key in SEQUENCE_SECTIONS:
            self._shown_section = key
            self._select_in_bar(key)
            self.body.setCurrentWidget(self.seq_page)
            if not self.has_sequence() and callable(self.sequence_provider):
                wanted = self.sequence_provider()
                if wanted:
                    self.set_sequence(wanted)
            if self.has_sequence():
                if page is not None and int(page) in _PANEL_PAGES[key]:
                    self._syncing = True
                    try:
                        self.primers.tabs.setCurrentIndex(int(page))
                    finally:
                        self._syncing = False
                self._apply_section(key)
            return True
        if key not in self._hosted:
            # nothing opened for this section yet: the window makes its page
            self.sectionRequested.emit(key)
        hosted = self._hosted.get(key)
        if hosted is None:
            self._select_in_bar(self._shown_section)      # stay where we were
            return False
        self._shown_section = key
        self._select_in_bar(key)
        self.body.setCurrentWidget(hosted)
        return True

    def _on_section_changed(self, index: int) -> None:
        if self._syncing:
            return
        key = str(self.sections.tabData(index) or SECTION_DESIGN)
        if self.section() == SECTION_GEL and section_key(key) != SECTION_GEL \
                and not self._gel_can_leave():
            self._select_in_bar(SECTION_GEL)        # Cancel: stay on the gel
            return
        self.set_section(key)

    # ------------------------------------------------ pages of other sections

    def host_page(self, section: str, widget: QWidget, *, show: bool = True) -> None:
        """Put the page of a section (Map, Database, Sanger Check…) into the workspace.

        A page already there for that section is closed and replaced.
        """
        key = section_key(section)
        old = self._hosted.pop(key, None)
        if old is not None and old is not widget:
            self.body.removeWidget(old)
            try:
                old.close()             # a hosted window saves or asks as it would
                old.deleteLater()
            except RuntimeError:
                pass
        self._hosted[key] = widget
        if self.body.indexOf(widget) < 0:
            self.body.addWidget(widget)
        self._guard_wheels()
        if show:
            self.set_section(key)

    def hosted_page(self, section: str):
        return self._hosted.get(section_key(section))

    def _gel_can_leave(self) -> bool:
        """A new gel that was never saved asks first. True to go on."""
        ask = getattr(self._hosted.get(SECTION_GEL), "confirm_leave", None)
        try:
            return bool(ask()) if callable(ask) else True
        except RuntimeError:
            return True

    def show_new_gel(self, folder: Path | str | None = None) -> None:
        """The Gel section on an empty gel that is no file until it is saved."""
        from repeatviewer.widgets.gel_view import GelDocumentPanel

        if not self._gel_can_leave():
            return
        panel = self._hosted.get(SECTION_GEL)
        if not isinstance(panel, GelDocumentPanel):
            panel = GelDocumentPanel(self)
            panel.openRequested.connect(self.openFileRequested.emit)
            panel.fileWritten.connect(self.fileWritten.emit)
            self.host_page(SECTION_GEL, panel, show=False)
        panel.new_untitled(Path(folder) if folder else None)
        self.set_section(SECTION_GEL)

    def show_gel(self, path: Path | str) -> None:
        """The Gel section on this gel file (.rvgel)."""
        from repeatviewer.widgets.gel_view import GelDocumentPanel

        if not self._gel_can_leave():
            return
        panel = self._hosted.get(SECTION_GEL)
        if not isinstance(panel, GelDocumentPanel):
            panel = GelDocumentPanel(self)
            panel.openRequested.connect(self.openFileRequested.emit)
            panel.fileWritten.connect(self.fileWritten.emit)
            self.host_page(SECTION_GEL, panel, show=False)
        panel.load(Path(path))
        self.set_section(SECTION_GEL)

    def show_gel_placeholder(self, new_gel) -> None:
        """The Gel section before any gel was opened: say how, and offer a new one."""
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.addStretch(1)
        note = QLabel("Click a gel (.rvgel) in Files to open it here, or start an empty one.",
                      page)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet("color: palette(placeholder-text);")
        lay.addWidget(note)
        row = QHBoxLayout()
        row.addStretch(1)
        button = QPushButton("New Gel", page)
        button.clicked.connect(lambda: new_gel())
        row.addWidget(button)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        self.new_gel_button = button
        self.host_page(SECTION_GEL, page)

    def gel_path(self) -> Path | None:
        panel = self._hosted.get(SECTION_GEL)
        try:
            return panel.path() if panel is not None else None
        except (AttributeError, RuntimeError):
            return None

    def _apply_section(self, key: str) -> None:
        pages = _PANEL_PAGES[key]
        tabs = self.primers.tabs
        before = tabs.currentIndex()
        target = before if before in pages else pages[0]
        if target == PANEL_PRIMER and not self.primers._selected:
            target = PANEL_DESIGN           # the primer page needs a primer
        self._syncing = True
        try:
            tabs.setCurrentIndex(target)
            # The sections above and the list under the map do the panel's
            # own tab bar's job.
            tabs.setVisible(False)
        finally:
            self._syncing = False
        if target == before:
            # The page stayed the same, so its signal did not fire: let it draw
            # its overlays (region and candidates, products, enzyme sites).
            self.primers._on_workbench_tab(target)
        self.bottom.setVisible(key in (SECTION_DESIGN, SECTION_PCR, SECTION_DIGEST))
        self.bottom_stack.setCurrentIndex({SECTION_PCR: 1, SECTION_DIGEST: 2}.get(key, 0))
        self._guard_wheels()
        self._sync_settings_summary()

    def _on_panel_page_changed(self, index: int) -> None:
        """The panel moved by itself (kept pairs open the primer page, say)."""
        if self._syncing or self._shown_section not in SEQUENCE_SECTIONS:
            return
        key = section_of_panel_page(index)
        if key != self.section():
            self.set_section(key)
        elif int(index) == PANEL_PRIMER and not self.primers._selected:
            # nothing to show there: stay on the settings
            QTimer.singleShot(0, lambda: self._show_design_page(PANEL_DESIGN))
        self._sync_settings_summary()

    # ------------------------------------------------- the list under the map

    def _build_list_area(self) -> None:
        """Candidates and primers on the sequence under the map; PCR products too."""
        from repeatviewer.widgets.help_button import make_help_button
        from repeatviewer.widgets.primers_workspace_list import WorkspaceList

        primers = self.primers
        design = primers.design_pane
        # The two tables stay the source of the list, but are never shown.
        self._kept = QWidget(self)
        self._kept.hide()
        candidates_section = design.table.parentWidget()
        self.list = WorkspaceList(
            design.table, primers.table, self,
            primer_columns=(primers.COL_TICK, primers.COL_NAME, primers.COL_TM,
                            primers.COL_SITE))
        self.list.context_menu_for_primer = primers._on_context_menu
        self.list.setMinimumHeight(96)

        # Toolbar rows (sections, Sequence, Position) and the settings keep
        # the window colour; the map and the lists under it are white.
        from repeatviewer.widgets.primer_design_pane import _results_surface

        self.bottom = QWidget(self)
        _results_surface(self.bottom)
        outer = QVBoxLayout(self.bottom)
        outer.setContentsMargins(12, 6, 12, 8)
        outer.setSpacing(0)
        self.bottom_stack = QStackedWidget(self.bottom)
        outer.addWidget(self.bottom_stack)

        page = QWidget(self.bottom_stack)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        from repeatviewer.widgets.primer_design_pane import _card

        lay.addWidget(_card(self.list, page), 1)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)
        self.list_note = design.cand_note
        # one line here; the whole text shows when the pointer rests on it
        self.list_note.set_elided(True)
        # A primer straight from the bases dragged over on the sequence.
        from PySide6.QtWidgets import QMenu

        self.selection_button = QPushButton("From Selection", page)
        self.selection_button.setToolTip(
            "Drag over 10 to 60 bases on the sequence, then make them a primer")
        pick = QMenu(self.selection_button)
        pick.addAction("Forward Primer", lambda: self._add_from_selection("+"))
        pick.addAction("Reverse Primer", lambda: self._add_from_selection("-"))
        self.selection_button.setMenu(pick)
        for button in (primers.add_button, primers.database_button, self.selection_button):
            button.setSizePolicy(QPushButton().sizePolicy())
            bar.addWidget(button)
        bar.addWidget(self.list_note, 1)
        bar.addWidget(make_help_button(page, "Primers", LIST_HELP))
        bar.addWidget(design.report_button)
        bar.addWidget(design.keep_button)
        lay.addLayout(bar)
        self.bottom_stack.addWidget(page)

        products = QWidget(self.bottom_stack)
        pl = QVBoxLayout(products)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(6)
        # The Products section of the PCR pane held only this table: its title
        # (with the count) comes along and the emptied section is not shown.
        products_section = primers.pcr_pane.table.parentWidget()
        primers.pcr_pane.table.setMinimumHeight(96)
        pl.addWidget(primers.pcr_pane.products_title)
        pl.addWidget(_card(primers.pcr_pane.table, products), 1)
        self.bottom_stack.addWidget(products)

        # Digest: the gel and the fragments of the lane, where there is room.
        digest = primers.enzyme_pane.digest_page
        digest_results = QWidget(self.bottom_stack)
        dl = QHBoxLayout(digest_results)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(10)
        digest.gel.setMinimumHeight(160)
        digest.table.setMinimumHeight(96)
        dl.addWidget(_card(digest.gel, digest_results), 3)
        dl.addWidget(_card(digest.table, digest_results), 2)
        self.bottom_stack.addWidget(digest_results)
        # The gel left its section of the panel: that section keeps only the
        # height of its two rows, and the free room goes to the end.
        gel_section = digest.agarose.parentWidget()
        if digest.layout() is not None and gel_section is not None:
            digest.layout().setStretchFactor(gel_section, 0)
            digest.layout().addStretch(1)
        if products_section is not None and products_section is not primers.pcr_pane:
            products_section.hide()

        design.table.setParent(self._kept)
        primers.table.setParent(self._kept)
        candidates_section.hide()
        # the two buttons of the old primer page that the workspace replaces
        primers.design_button.hide()
        primers.pcr_button.hide()

        # under the map, left of the settings; the user can drag the border
        layout = self.panel.layout()
        index = layout.indexOf(self.panel._map)
        self.splitter = QSplitter(Qt.Orientation.Vertical, self.panel)
        self.splitter.setChildrenCollapsible(False)
        layout.insertWidget(max(0, index), self.splitter, 1)
        # The map in a box as wide as the boxes under it.
        self.map_box = QWidget(self.splitter)
        mb = QVBoxLayout(self.map_box)
        mb.setContentsMargins(12, 6, 12, 2)
        mb.setSpacing(0)
        mb.addWidget(_card(self.panel._map, self.map_box))
        self.splitter.addWidget(self.map_box)
        self.splitter.addWidget(self.bottom)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([600, 190])

        self.list.picked.connect(self._on_list_picked)
        self.list.cellClicked.connect(self._on_list_cell_clicked)

    def _add_from_selection(self, strand: str) -> None:
        """The bases dragged over become a primer; a problem shows in the note."""
        problem = self.primers.add_primer_from_region(strand)
        if problem:
            # The note under the list is one cut line: say it where it is read.
            self.list_note.setText(problem)
            self.statusMessage.emit(problem)
            QMessageBox.information(self.window(), "Primer from Selection", problem)

    def _on_list_picked(self, kind: str) -> None:
        from repeatviewer.widgets.primers_workspace_list import KIND_PRIMER

        if self.section() != SECTION_DESIGN:
            return
        self._show_design_page(PANEL_PRIMER if kind == KIND_PRIMER else PANEL_DESIGN)

    def _on_list_cell_clicked(self, row: int, column: int) -> None:
        """A click on the row that is already selected opens its page again."""
        from repeatviewer.widgets.primers_workspace_list import COL_TICK

        kind = self.list.kind_of_row(row)
        if kind and column != COL_TICK:
            self._on_list_picked(kind)

    def _show_design_page(self, page: int) -> None:
        """Design settings, or the details of the selected primer."""
        if self.section() != SECTION_DESIGN:
            return
        if int(page) == PANEL_PRIMER and not self.primers._selected:
            page = PANEL_DESIGN
        self._syncing = True
        try:
            self.primers.tabs.setCurrentIndex(int(page))
        finally:
            self._syncing = False
        self._sync_settings_summary()

    # ------------------------------------------- settings folded to one line

    def _build_settings_header(self) -> None:
        """On top of the primer details: the design settings as one line."""
        from repeatviewer.widgets.help_button import make_help_button

        design = self.primers.design_pane
        page = self.primers.primer_page
        header = QWidget(page)
        lay = QVBoxLayout(header)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(6)
        from PySide6.QtWidgets import QSizePolicy

        from repeatviewer.widgets.primer_design_pane import HALF_ROW_W as _HALF

        # The title takes the width of the left button below it, so Show starts
        # where the right button starts and runs up to the "?".
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        title_label = QLabel("<b>Design Settings</b>", header)
        title_label.setFixedWidth(_HALF)
        top.addWidget(title_label)
        self.show_settings_button = QPushButton("Show", header)
        self.show_settings_button.setSizePolicy(QSizePolicy.Policy.Expanding,
                                                QSizePolicy.Policy.Fixed)
        top.addWidget(self.show_settings_button, 1)
        top.addWidget(make_help_button(header, "Design Settings", SETTINGS_HEADER_HELP))
        lay.addLayout(top)
        self.settings_summary = QLabel(header)
        self.settings_summary.setWordWrap(True)
        self.settings_summary.setStyleSheet("color: palette(placeholder-text);")
        lay.addWidget(self.settings_summary)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.header_defaults_button = QPushButton("Restore Defaults", header)
        self.header_design_button = QPushButton("Design", header)
        row.addWidget(self.header_defaults_button)
        row.addWidget(self.header_design_button)
        row.addStretch(1)
        lay.addLayout(row)
        page.layout().insertWidget(0, header)
        self.settings_header = header

        # The settings page starts the same way: the title, then Restore
        # Defaults and Design on top, where they are without scrolling.
        from repeatviewer.widgets.primer_design_pane import _rule

        dh = QWidget(design)
        dl = QVBoxLayout(dh)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(6)
        dtop = QHBoxLayout()
        dtop.setContentsMargins(0, 0, 0, 0)
        dtop.setSpacing(6)
        dtitle = QLabel("<b>Design Settings</b>", dh)
        dtitle.setFixedWidth(_HALF)
        dtop.addWidget(dtitle)
        self.hide_settings_button = QPushButton("Hide", dh)
        self.hide_settings_button.setToolTip("Back to the selected primer")
        self.hide_settings_button.setSizePolicy(QSizePolicy.Policy.Expanding,
                                                QSizePolicy.Policy.Fixed)
        dtop.addWidget(self.hide_settings_button, 1)
        dtop.addWidget(make_help_button(dh, "Design Settings", SETTINGS_HEADER_HELP))
        dl.addLayout(dtop)
        drow = QHBoxLayout()
        drow.setContentsMargins(0, 0, 0, 0)
        drow.setSpacing(6)
        drow.addWidget(design.defaults_button)
        drow.addWidget(design.design_button)
        drow.addStretch(1)
        dl.addLayout(drow)
        end_row = getattr(design, "end_row", None)
        if end_row is not None:
            end_row.hide()          # its two buttons sit on top now
        # Two equal buttons over the label and field columns of the form.
        from repeatviewer.widgets.primer_design_pane import HALF_ROW_W

        half = HALF_ROW_W
        for b in (design.defaults_button, design.design_button,
                  self.header_defaults_button, self.header_design_button):
            b.setFixedWidth(half)
        design.layout().insertWidget(0, dh)
        design.layout().insertWidget(1, _rule(design))
        self.design_header = dh
        self.hide_settings_button.clicked.connect(
            lambda: self._show_design_page(PANEL_PRIMER))

        self.show_settings_button.clicked.connect(
            lambda: self._show_design_page(PANEL_DESIGN))
        self.header_defaults_button.clicked.connect(design.defaults_button.click)
        self.header_defaults_button.clicked.connect(self._sync_settings_summary)

        def design_again() -> None:
            self._show_design_page(PANEL_DESIGN)
            design.design_button.click()

        self.header_design_button.clicked.connect(design_again)

    def settings_summary_text(self) -> str:
        design = self.primers.design_pane
        parts = [design.mode.currentText()]
        try:
            region = design.region()
        except Exception:  # noqa: BLE001 - a half-typed range is no region
            region = None
        if region is not None:
            parts.append(f"region {region.start:,} to {region.end:,}")
        if not design.is_probe_mode():
            parts.append(f"Tm {design.tm_min.value():g} to {design.tm_max.value():g} °C")
        return ", ".join(parts)

    def _sync_settings_summary(self, *_args) -> None:
        self.settings_summary.setText(self.settings_summary_text())
        self.hide_settings_button.setEnabled(bool(self.primers._selected))

    # ------------------------------------------ path fields filled from Files

    def _on_focus_changed(self, _old, new) -> None:
        """Remember the path field the cursor was in when the user goes to Files."""
        if new is None:
            return
        try:
            if not self.isAncestorOf(new):
                return                      # focus left the workspace: keep the field
        except RuntimeError:
            return
        row = _path_row_of(new)
        self._armed_row = row if row is not None and row is not self.sequence_row else None

    def fill_armed_path(self, path: Path | str) -> bool:
        """Put a file clicked in Files into the path field the cursor was in."""
        row = self._armed_row
        if row is None:
            return False
        try:
            if not row.isVisible():
                return False
            row.set_path(Path(path))
        except RuntimeError:
            self._armed_row = None
            return False
        self._armed_row = None
        return True

    # ---------------------------------------------------------------- sequence

    def _load(self, path: Path) -> bool:
        """Load ``path`` into the sequence view. False when it holds no sequence."""
        target = Path(path).expanduser().resolve()
        if self.panel is None:
            self._build_sequence_part(target)
        self._sequence_path = target
        self.panel.load_path(target)
        rail = self.panel._rail
        # The workspace shows one page of the rail and never another, so the
        # strip of rail buttons has no job here.
        rail._tab_strip.hide()
        heading = getattr(rail, "primers_page_title", None)
        if heading is not None:
            heading.hide()          # the section row already says where we are
        rail.set_panel_collapsed(False, persist=False)
        self.panel.show_primers_tab()
        # without the strip the side is as wide as in Painting, Map and the rest
        rail.setFixedWidth(rail._expanded_rail_width())
        self._sync_records()
        # A file that could not be read leaves the old sequence on the map, but
        # no record in the list: that is how a failed load shows.
        return self.record_combo.count() > 0 and self.panel._map.data() is not None

    def _sync_records(self) -> None:
        source = self.panel._sequence_combo
        self.record_combo.blockSignals(True)
        try:
            self.record_combo.clear()
            for index in range(source.count()):
                self.record_combo.addItem(str(source.itemData(index) or source.itemText(index)),
                                          source.itemData(index))
            self.record_combo.setCurrentIndex(max(0, source.currentIndex()))
        finally:
            self.record_combo.blockSignals(False)
        several = self.record_combo.count() > 1
        self.record_combo.setVisible(several)
        self.record_combo.setToolTip(self.record_combo.currentText())
        QTimer.singleShot(0, self._sync_length)

    def _on_record_chosen(self, index: int) -> None:
        seq_id = self.record_combo.itemData(index)
        if seq_id:
            self.panel.ensure_active_sequence(str(seq_id))

    def _on_panel_record_changed(self, seq_id: str) -> None:
        index = self.record_combo.findData(seq_id)
        if index >= 0 and index != self.record_combo.currentIndex():
            self.record_combo.blockSignals(True)
            self.record_combo.setCurrentIndex(index)
            self.record_combo.blockSignals(False)
        self.record_combo.setToolTip(self.record_combo.currentText())
        QTimer.singleShot(0, self._sync_length)

    def _show_sequence_in_field(self) -> None:
        self.sequence_row.set_path(self._sequence_path, emit=False)
        if self._sequence_path is not None:
            self.sequence_row.set_start_dir(str(self._sequence_path.parent))

    def _on_sequence_field_changed(self) -> None:
        """Browse, or a path typed into the field."""
        chosen = self.sequence_row.path()
        if chosen is None or same_file(chosen, self._sequence_path):
            self._show_sequence_in_field()      # an emptied field shows the file again
            return
        if not self.set_sequence(chosen):
            self._show_sequence_in_field()

    def set_sequence(self, path: Path | str) -> bool:
        """Work on another FASTA. False when it is not one, or the user stayed."""
        target = Path(path).expanduser()
        if not target.is_file():
            self.statusMessage.emit(f"{target.name} is not a file.")
            return False
        if same_file(target, self._sequence_path):
            self._show_sequence_in_field()
            return True
        if not self.confirm_leave():
            return False
        previous = self._sequence_path
        if not self._load(target):
            self.statusMessage.emit(f"{target.name} has no sequence to work on.")
            if previous is not None:
                self._load(previous)
            else:
                self._sequence_path = None
            self._sync_sequence_shown()
            self._show_sequence_in_field()
            return False
        self._sync_sequence_shown()
        self._show_sequence_in_field()
        if self._shown_section in SEQUENCE_SECTIONS:
            # The page in front draws its overlays for the new sequence.
            self._apply_section(self._shown_section)
        self.sequenceChanged.emit(self._sequence_path)
        return True

    def _sync_sequence_shown(self) -> None:
        has = self.has_sequence()
        if self.panel is not None:
            self.panel.setVisible(has)
        self.no_sequence.setVisible(not has)
        if not has:
            self.record_label.hide()
            self.record_combo.hide()

    def reload_annotations(self) -> None:
        """The sequence's annotations were saved somewhere else: show them."""
        if not self.has_sequence() or self.has_unsaved_changes():
            return
        record = self.record_combo.currentData()
        self.panel.load_path(self._sequence_path, fit_after_load=False)
        if record:
            self.panel.ensure_active_sequence(str(record))
        self.panel.show_primers_tab()
        self._sync_records()
        if self._shown_section in SEQUENCE_SECTIONS:
            self._apply_section(self._shown_section)

    # ------------------------------------------------------------ leaving safely

    def has_unsaved_changes(self) -> bool:
        if not self.has_sequence():
            return False
        try:
            return bool(self.panel.has_unsaved_annotation_changes())
        except RuntimeError:
            return False

    def confirm_leave(self) -> bool:
        """Unsaved annotation changes: Save / Don't Save / Cancel. True to go on."""
        if not self._gel_can_leave():
            return False
        if not self.has_unsaved_changes():
            return True
        box = QMessageBox(self.window())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Unsaved Changes")
        box.setText(f'Save changes to "{self._sequence_path.name}"?')
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        box.setEscapeButton(QMessageBox.StandardButton.Cancel)
        choice = box.exec()
        if choice == QMessageBox.StandardButton.Save:
            return bool(self.panel.save_annotations(silent=True))
        return choice == QMessageBox.StandardButton.Discard

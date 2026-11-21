"""right rail for the Annotation preview (Display / Annotation / Find / Others)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSettings, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QMenu,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from repeatviewer.widgets.combo_boxes import NoWheelComboBox as QComboBox

from repeatviewer.backends.annotation_colors import (
    feature_type_color,
    load_add_feature_buttons,
)
from repeatviewer.backends.sequence_features import (
    ALWAYS_ANNOTATION_VISIBILITY_KINDS,
    FEATURE_TYPE_COLORS,
    SequenceFeature,
    annotation_visibility_label,
    collect_annotation_visibility_keys,
)

# Boundary prediction rows: (key, label, guide color).
# LTR / TIR match the default feature-annotation colours so MSA boundary lines
# match the Feature detection / annotation legend.
BOUNDARY_ROWS: tuple[tuple[str, str, str], ...] = (
    ("ltr", "LTR", FEATURE_TYPE_COLORS["LTR"]),
    ("tir", "TIR", FEATURE_TYPE_COLORS["TIR"]),
    ("msa_identity", "MSA identity", "#1f77b4"),
    ("coverage", "Genome Cov", "#2ca02c"),
    ("poly_a", "PolyA", "#9467bd"),
)

# Checkbox label → feature-type key used by the annotation colors panel.
_FEATURE_DETECT_TYPE_BY_LABEL: dict[str, str] = {
    "LTR": "LTR",
    "TIR": "TIR",
    "Tandem": "tandem repeat",
    "ORF": "ORF",
    "TSD": "TSD",
    "PBS": "PBS",
}
from repeatviewer.backends.genetic_codes import (
    genetic_code_choices,
    normalize_genetic_code_id,
)
from repeatviewer.backends.msa_plot import (
    AMINO_ACID_COLOR_PRESETS,
    NUCLEOTIDE_COLOR_PRESETS,
)
from repeatviewer.widgets.help_button import field_with_help, make_help_button
from repeatviewer.widgets.preview_zoom import (
    load_nucleotide_scheme_name,
    normalize_nucleotide_color_context,
    save_custom_amino_acid_backgrounds,
    save_nucleotide_scheme,
)
from repeatviewer.widgets.path_browse import PathBrowseRow
from repeatviewer.widgets.preview_controls import apply_annotation_zoom_slider_style
from repeatviewer.widgets.spin_boxes import (
    NoWheelDoubleSpinBox,
    NoWheelSlider,
    NoWheelSpinBox,
)

_NCBI_GENETIC_CODES_URL = (
    "https://www.ncbi.nlm.nih.gov/Taxonomy/Utils/wprintgc.cgi"
)
_READING_FRAMES_HELP = (
    "Tick which frames to show under the sequence when translation is on.<br><br>"
    "<b>Frame 1 / 2 / 3</b> — forward reading frames on the displayed strand "
    "(offset by 0, 1, or 2 bases).<br><br>"
    "<b>Reverse 1 / 2 / 3</b> — reverse reading frames on the complementary strand "
    "(reverse-complement translation)."
)
_BOUNDARY_PREDICTION_HELP = (
    "Ported from TEtrimmer. The MSA is first cleaned with TEtrimmer's column "
    "rules (rare nucleotides below 1% become gaps, then gappy or poorly "
    "conserved columns are removed). Boundaries are found on the cleaned MSA "
    "and shown as MSA columns.<br><br>"
    "<b>LTR / TIR</b> based boundary definition<br><br>"
    "Self-BLAST of the 0.7 consensus (after end cropping). Direct repeats of "
    "100 bp or more at both ends give an LTR; inverted repeats of 20 bp or "
    "more give a TIR. The span runs from the start of the left copy to the "
    "end of the right copy.<br><br>"
    "<b>MSA identity</b> based boundary definition<br><br>"
    "Sequence ends are cropped where conservation is low, then the boundary "
    "is the first and last 4-column window whose 0.8 consensus has no N."
    "<br><br>"
    "<b>Genome Cov</b> based boundary definition<br><br>"
    "The 0.7 consensus is BLASTed against the project genome. The boundary is "
    "where hit coverage rises above background at each end (a 20-column "
    "window summing over 100, trimmed at a 5× coverage jump). If MSA "
    "identity extends 30 or more columns past it, Genome Cov is re-run with "
    "a 0.55 consensus. Needs a project genome.<br><br>"
    "<b>PolyA</b> based boundary definition<br><br>"
    "Only when the file name contains LINE or SINE. A run of 10 or more A "
    "near the 3′ end of the 0.8 consensus, with an unconserved region after "
    "it. LINE also crops divergent ends by gaps first.<br><br>"
    "Tick a row to draw its boundary lines on the MSA."
)
_FIND_IUPAC_HELP = (
    "<b>On</b>: IUPAC ambiguity codes are treated as wildcards.<br><br>"
    "<b>Query</b> — e.g. R matches A or G, Y matches C or T, N matches any base.<br>"
    "<b>Sequence</b> — ambiguous letters in the sequence (N, R, Y, …) also count "
    "as a match for the corresponding motif base.<br><br>"
    "<b>Off</b>: each letter matches only itself (an R in the motif only matches "
    "an R in the sequence)."
)
_GENETIC_CODE_HELP = (
    "The genetic code table controls how DNA codons are translated into amino acids "
    "(same IDs as GenBank <code>/transl_table</code>). Use <b>1. Standard</b> for most "
    "nuclear genomes; choose a mitochondrial, plastid, or other table when your sequence "
    "comes from those systems.<br><br>"
    "For more detailed explanation please visit:<br>"
    f'<a href="{_NCBI_GENETIC_CODES_URL}">{_NCBI_GENETIC_CODES_URL}</a>'
)

_RAIL_TAB_WIDTH = 24
_MODULE_WIDTH = 260
# The Primers tab holds the primer workbench (Design / Primer): it needs more room.
_PRIMERS_MODULE_WIDTH = 330
_TAB_BUTTON_HEIGHT_MIN = 36
_TAB_PILL_RADIUS = 7
_TAB_TEXT_PAD = 4  # vertical padding around rotated label

# Persist Annotation rail tab + collapsible section expand state.
_SETTINGS_GROUP = "sequence_annotation_rail"
_SETTINGS_TAB_KEY = "last_tab"
_SETTINGS_SECTIONS_KEY = "expanded_sections"
_SETTINGS_COLLAPSED_KEY = "panel_collapsed"
_SETTINGS_HIDDEN_ANN_KINDS_KEY = "hidden_annotation_kinds"
# Displayed annotations type chips: keep ~2 wrap rows; overflow goes under More.
_ANNOTATION_KINDS_FLOW_MAX_HEIGHT = 80
# Default first open: Annotation tab with all sections collapsed.
_DEFAULT_TAB_INDEX = 1
PRIMERS_TAB_INDEX = 4
_COLLAPSED_RAIL_WIDTH = _RAIL_TAB_WIDTH
_ANNOTATION_SECTION_IDS = (
    "feature_detection",
    "similarity",
    "manual",
    "transfer",
)

# Translation frames: +1..+3 forward, -1..-3 reverse.
TRANSLATION_FRAMES: tuple[int, ...] = (1, 2, 3, -1, -2, -3)


class TranslationSettingsDialog(QDialog):
    """Frames, three-letter amino acids, and NCBI genetic code for translation tracks."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        frames: frozenset[int] | set[int] | None = None,
        three_letter: bool = False,
        genetic_code: int = 1,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Translation settings")
        self.setModal(True)
        self.setMinimumWidth(400)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        frames_section = QVBoxLayout()
        frames_section.setContentsMargins(0, 0, 0, 0)
        frames_section.setSpacing(4)
        frames_header = QHBoxLayout()
        frames_header.setContentsMargins(0, 0, 0, 0)
        frames_header.setSpacing(6)
        frames_header.addWidget(_section_label("Reading frames", self))
        frames_header.addWidget(
            make_help_button(self, "Reading frames", _READING_FRAMES_HELP)
        )
        frames_header.addStretch(1)
        frames_section.addLayout(frames_header)

        frames_host = QWidget(self)
        frames_grid = QGridLayout(frames_host)
        frames_grid.setContentsMargins(0, 0, 0, 0)
        frames_grid.setHorizontalSpacing(12)
        frames_grid.setVerticalSpacing(4)
        selected = set(frames or {1})
        self._frame_checks: dict[int, QCheckBox] = {}
        for col, frame in enumerate((1, 2, 3)):
            fwd = QCheckBox(f"Frame {frame}", frames_host)
            fwd.setToolTip(f"Forward reading frame {frame}")
            fwd.setChecked(frame in selected)
            self._frame_checks[frame] = fwd
            frames_grid.addWidget(fwd, 0, col)

            rev_frame = -frame
            rev = QCheckBox(f"Reverse {frame}", frames_host)
            rev.setToolTip(f"Reverse reading frame {frame}")
            rev.setChecked(rev_frame in selected)
            self._frame_checks[rev_frame] = rev
            frames_grid.addWidget(rev, 1, col)
        frames_section.addWidget(frames_host)
        root.addLayout(frames_section)

        root.addWidget(_h_divider(self))

        aa_section = QVBoxLayout()
        aa_section.setContentsMargins(0, 0, 0, 0)
        aa_section.setSpacing(4)
        aa_section.addWidget(_section_label("Amino acids", self))
        self.three_letter = QCheckBox("Show three-letter codes (e.g. Met)", self)
        self.three_letter.setChecked(bool(three_letter))
        self.three_letter.setToolTip(
            "When checked, translation tracks show Ala/Met/Ter instead of A/M/*."
        )
        aa_section.addWidget(self.three_letter)
        root.addLayout(aa_section)

        root.addWidget(_h_divider(self))

        code_section = QVBoxLayout()
        code_section.setContentsMargins(0, 0, 0, 0)
        code_section.setSpacing(4)
        code_section.addWidget(_section_label("Genetic code", self))
        code_row = QHBoxLayout()
        code_row.setContentsMargins(0, 0, 0, 0)
        code_row.setSpacing(6)
        self.genetic_code = QComboBox(self)
        self.genetic_code.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.genetic_code.setFixedWidth(220)
        for table_id, label in genetic_code_choices():
            self.genetic_code.addItem(label, table_id)
        wanted = normalize_genetic_code_id(genetic_code)
        idx = self.genetic_code.findData(wanted)
        self.genetic_code.setCurrentIndex(max(0, idx))
        code_row.addWidget(self.genetic_code)
        code_row.addWidget(
            make_help_button(self, "Genetic code", _GENETIC_CODE_HELP)
        )
        code_row.addStretch(1)
        code_section.addLayout(code_row)
        root.addLayout(code_section)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def selected_frames(self) -> frozenset[int]:
        frames = frozenset(
            frame for frame, check in self._frame_checks.items() if check.isChecked()
        )
        return frames or frozenset({1})

    def show_three_letter(self) -> bool:
        return bool(self.three_letter.isChecked())

    def genetic_code_id(self) -> int:
        return normalize_genetic_code_id(self.genetic_code.currentData() or 1)


def _section_label(text: str, parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


def _h_divider(parent: QWidget | None = None) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    line.setFixedHeight(2)
    return line


def _page_title_with_rule(title: str, parent: QWidget) -> tuple[QWidget, QFrame]:
    """Page title + rule at the same height as the Annotations header line.

    Title sits with a 6px pad below (matching Annotations); the rule follows
    with no extra gap so Find / Display / Others match Annotations.
    """
    host = QWidget(parent)
    host.setMinimumWidth(0)
    column = QVBoxLayout(host)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    title_wrap = QWidget(host)
    title_layout = QVBoxLayout(title_wrap)
    title_layout.setContentsMargins(0, 0, 0, 6)
    title_layout.setSpacing(0)
    title_layout.addWidget(_section_label(title, title_wrap))
    column.addWidget(title_wrap)
    rule = _h_divider(host)
    column.addWidget(rule)
    return host, rule


class SimilarityDatabaseCheck(QCheckBox):
    """Numbered similarity DB checkbox; label elides to a column cell width."""

    def __init__(
        self,
        name: str,
        index: int,
        color: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._full_name = str(name)
        self._index = max(0, int(index))
        self._cell_width = 0
        self.setStyleSheet(f"QCheckBox {{ color: {color}; }}")
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.setMinimumWidth(0)
        self.setText(self._full_label())

    @property
    def full_name(self) -> str:
        return self._full_name

    @property
    def database_index(self) -> int:
        return self._index

    def set_cell_width(self, width: int) -> None:
        """Fixed column width from the two-row grid; drives name elision."""
        width = max(0, int(width))
        if width == self._cell_width:
            self._refresh_label()
            return
        self._cell_width = width
        if width > 0:
            self.setFixedWidth(width)
        self._refresh_label()

    def max_name_letters(self) -> int:
        """Approx. max name characters that fit in the current column (excl. ``N. ``)."""
        available = self._text_available_width()
        if available <= 0:
            return len(self._full_name)
        fm = self.fontMetrics()
        prefix_w = fm.horizontalAdvance(f"{self._index + 1}. ")
        room = max(0, available - prefix_w)
        if room <= 0:
            return 0
        # Use average advance of the real name when possible.
        sample = self._full_name or "M"
        avg = max(1.0, fm.horizontalAdvance(sample) / max(1, len(sample)))
        return max(0, int(room / avg))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_label()

    def _full_label(self) -> str:
        return f"{self._index + 1}. {self._full_name}"

    def _text_available_width(self) -> int:
        width = self._cell_width or self.width()
        if width <= 0:
            return 0
        style = self.style()
        indicator = style.pixelMetric(
            QStyle.PixelMetric.PM_IndicatorWidth, None, self
        )
        spacing = style.pixelMetric(
            QStyle.PixelMetric.PM_CheckBoxLabelSpacing, None, self
        )
        return max(0, width - indicator - spacing - 4)

    def _refresh_label(self) -> None:
        full = self._full_label()
        available = self._text_available_width()
        if available <= 0:
            text = full
        else:
            fm = self.fontMetrics()
            if fm.horizontalAdvance(full) <= available:
                text = full
            else:
                number = str(self._index + 1)
                prefix = f"{number}. "
                prefix_w = fm.horizontalAdvance(prefix)
                if prefix_w + fm.horizontalAdvance("…") > available:
                    text = number
                else:
                    elided = fm.elidedText(
                        self._full_name,
                        Qt.TextElideMode.ElideRight,
                        max(0, available - prefix_w),
                    )
                    text = number if not elided or elided == "…" else prefix + elided
        if text != self.text():
            self.setText(text)


class SimilarityDatabaseGrid(QWidget):
    """Column-aligned grid: exactly two databases per row (names elide to width)."""

    _H_SPACING = 6
    _V_SPACING = 2
    _COLUMNS = 2

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(self._H_SPACING)
        self._grid.setVerticalSpacing(self._V_SPACING)
        self._widgets: list[QWidget] = []

    def clear_widgets(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._widgets.clear()

    def add_widget(self, widget: QWidget) -> None:
        widget.setParent(self)
        self._widgets.append(widget)
        self._reflow()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow_column_widths()

    def _column_count(self) -> int:
        return self._COLUMNS if self._widgets else 1

    def _reflow(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self)
        cols = self._column_count()
        for index, widget in enumerate(self._widgets):
            # Row-major: two databases per row.
            self._grid.addWidget(widget, index // cols, index % cols)
        for col in range(cols):
            self._grid.setColumnStretch(col, 1)
        self._reflow_column_widths()

    def _reflow_column_widths(self) -> None:
        checks = [w for w in self._widgets if isinstance(w, SimilarityDatabaseCheck)]
        if not checks:
            return
        cols = self._column_count()
        avail = max(0, self.width())
        if avail <= 0:
            return
        gaps = self._H_SPACING * max(0, cols - 1)
        cell = max(48, (avail - gaps) // cols)
        for check in checks:
            check.set_cell_width(cell)


class _FlowLayout(QLayout):
    """Left-to-right wrapping row layout for compact checkbox chips."""

    def __init__(self, parent: QWidget | None = None, *, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        # Prefer a wrapped height for a typical rail width so the host hugs content.
        width = 200
        parent = self.parentWidget()
        if parent is not None and parent.width() > 0:
            width = parent.width()
        return QSize(width, self.heightForWidth(width))

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        size += QSize(left + right, top + bottom)
        # At least one row tall; width is the widest chip.
        return size

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x = effective.x()
        y = effective.y()
        line_height = 0
        space = self.spacing()
        for item in self._items:
            widget = item.widget()
            # Hidden chips (e.g. TSD when not MSA) must not reserve space —
            # otherwise the next wrap row (PBS) starts indented.
            if widget is not None and widget.isHidden():
                continue
            hint = item.sizeHint()
            next_x = x + hint.width() + space
            if line_height and next_x - space > effective.right() + 1:
                x = effective.x()
                y += line_height + space
                next_x = x + hint.width() + space
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + bottom


class _CollapsibleSection(QWidget):
    """Section title matching Annotations headers; click (or left arrow) to expand."""

    expandedChanged = Signal(bool)

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        *,
        expanded: bool = True,
        ruled: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        self._expanded = bool(expanded)
        self._ruled = bool(ruled)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        # Match tree Display rail: compact header ↔ body / collapsed rows.
        root.setSpacing(0 if ruled else 3)

        self._header = QWidget(self)
        self._header.setObjectName("annotationSectionHeader")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        header_row = QHBoxLayout(self._header)
        # Ruled rows sit on a full-width hairline, like Tracks / Color / Size.
        header_row.setContentsMargins(14, 8, 12, 8) if ruled else header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8 if ruled else 6)

        self._arrow = QLabel(self._header)
        self._arrow.setFixedWidth(12)
        self._arrow.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._title = QLabel(title, self._header)
        # Regular weight — same as tree Display section headers.
        self._title.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        arrow_font = self._arrow.font()
        # 3/4 of the title size (half was too small; 3/2 of that).
        arrow_font.setPointSizeF(max(6.0, self._title.font().pointSizeF() * 0.75))
        self._arrow.setFont(arrow_font)
        # Arrow on the left of the title (Display / Annotation / Find / Others).
        header_row.addWidget(self._arrow, 0)
        header_row.addWidget(self._title, 1)
        self._sync_arrow()
        self._header.mousePressEvent = self._on_header_pressed  # type: ignore[method-assign]
        root.addWidget(self._header)

        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(28, 0, 14, 10) if ruled else self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(3)
        self._body.setVisible(self._expanded)
        root.addWidget(self._body)

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def add_widget(self, widget: QWidget) -> None:
        self._body_layout.addWidget(widget)

    def add_layout(self, layout: QHBoxLayout | QVBoxLayout | QFormLayout | QGridLayout) -> None:
        self._body_layout.addLayout(layout)

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool, *, notify: bool = True) -> None:
        expanded = bool(expanded)
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self._body.setVisible(expanded)
        self._sync_arrow()
        if notify:
            self.expandedChanged.emit(expanded)

    def _sync_arrow(self) -> None:
        # Left side disclosure: ▼ expanded, ▶ collapsed.
        self._arrow.setText("▼" if self._expanded else "▶")

    def _on_header_pressed(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_expanded(not self._expanded)
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._ruled:
            return
        painter = QPainter(self)
        color = self.palette().color(QPalette.ColorRole.Mid)
        color.setAlpha(170)
        painter.setPen(QPen(color, 1))
        painter.drawLine(0, 0, self.width(), 0)
        painter.end()


class _RotatedTabButton(QToolButton):
    """Vertical pill tab (Actions-style chrome, label rotated −90°)."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = label
        self.setObjectName("AnnotationRailTabButton")
        self.setText(label)
        self.setCheckable(True)
        self.setAutoRaise(False)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.toggled.connect(lambda _checked: self.update())
        fm = QFontMetrics(self.font())
        # Rotated text height ≈ label width + minimal inset (no tall empty caps).
        height = max(
            _TAB_BUTTON_HEIGHT_MIN,
            fm.horizontalAdvance(label) + 2 * _TAB_TEXT_PAD,
        )
        self.setFixedSize(_RAIL_TAB_WIDTH - 2, height)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        pal = self.palette()
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.isChecked():
            fill = pal.color(pal.ColorRole.Highlight)
            text = pal.color(pal.ColorRole.HighlightedText)
            border = fill.darker(120)
            pen_w = 1.5
        elif self.underMouse():
            fill = pal.color(pal.ColorRole.AlternateBase)
            text = pal.color(pal.ColorRole.ButtonText)
            border = pal.color(pal.ColorRole.Mid)
            pen_w = 1.0
        else:
            fill = pal.color(pal.ColorRole.Base)
            text = pal.color(pal.ColorRole.ButtonText)
            border = pal.color(pal.ColorRole.Mid)
            pen_w = 1.0
        if not border.isValid() or border.alpha() == 0:
            border = QColor(140, 140, 140)
        painter.setPen(QPen(border, pen_w))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, _TAB_PILL_RADIUS, _TAB_PILL_RADIUS)
        font = QFont(self.font())
        font.setBold(self.isChecked())
        painter.setPen(text)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_label = self._label
        painter.translate(self.width() / 2.0, self.height() / 2.0)
        painter.rotate(-90)
        text_w = fm.horizontalAdvance(text_label)
        text_h = fm.ascent()
        painter.drawText(
            QPoint(int(-text_w / 2), int(text_h / 2) - 1),
            text_label,
        )
        painter.end()


class SequenceAnnotationRail(QWidget):
    """Vertical pill-tab strip + stacked Display / Annotation / Find / Others panels."""

    addFeatureClicked = Signal()  # Add with type from manual_feature_combo
    addFeatureSettingsClicked = Signal()  # Manage feature types in the dropdown
    deleteClicked = Signal()
    restoreClicked = Signal()
    saveClicked = Signal()
    exportClicked = Signal()
    colorsClicked = Signal()
    residueColorsChanged = Signal()  # quick nucleotide / protein scheme applied
    msaColoringModeChanged = Signal(str)  # MSA residue paint mode id
    msaDivergenceChanged = Signal(float)  # conserved-letter frequency threshold 0–1
    boundaryPredictClicked = Signal()  # MSA only: TEtrimmer boundary prediction
    # frozenset[str] of ticked Boundary prediction rows (guides drawn on the MSA).
    boundaryGuidesChanged = Signal(object)
    featureDetectClicked = Signal()
    featureDetectSettingsClicked = Signal()
    similarityAnnotateClicked = Signal()
    similaritySettingsClicked = Signal()
    transferRequested = Signal()
    transferSettingsClicked = Signal()
    transferThresholdChanged = Signal()
    transferSourceChanged = Signal()
    tabChanged = Signal(int)
    panelCollapsedChanged = Signal(bool)
    findRequested = Signal(int)  # +1 next, -1 previous, 0 find all

    # Display / size signals (live apply).
    showAnnotationTrackChanged = Signal(bool)
    # frozenset[str] of visible annotation_visibility_key values (empty = hide all kinds).
    annotationTrackKindsChanged = Signal(object)
    showStandardBoundariesChanged = Signal(bool)
    showBlastCoverageChanged = Signal(bool)
    # Split Preview: link vertical scroll, selection, and annotation filters
    # (horizontal columns stay independent).
    syncSplitViewsChanged = Signal(bool)
    sequenceSortChanged = Signal(str)  # original | name | selected_columns
    showComplementChanged = Signal(bool)
    showTranslationChanged = Signal(bool)
    translationFramesChanged = Signal(object)  # frozenset[int]
    translationOptionsChanged = Signal()  # three-letter / genetic code
    basesZoomedInChanged = Signal(int)
    basesZoomedOutChanged = Signal(int)
    trackHeightChanged = Signal(int)  # MSA/multi overview: Track height 1–10
    trackDistanceChanged = Signal(int)  # MSA/multi overview: sequence→annotation gap
    annotationLabelSizeChanged = Signal(int)
    annotationThicknessChanged = Signal(int)
    columnDistanceChanged = Signal(int)  # MSA overview: gap between residue columns
    multiSequenceBackgroundChanged = Signal(bool)
    annotationDistanceChanged = Signal(int)
    sequenceDistanceChanged = Signal(int)  # multi/MSA overview: gap between sequences
    sequenceNameSizeChanged = Signal(int)
    baseNumberSizeChanged = Signal(int)
    splitTracksBySourceChanged = Signal(bool)

    TAB_DISPLAY = 0
    TAB_SHOW = 0  # backward-compatible alias
    TAB_ANNOTATIONS = 1
    TAB_FIND = 2
    TAB_OTHERS = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sequenceAnnotationRail")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._module_width = _MODULE_WIDTH
        self._overview_mode = False
        self._nucleotide_color_context = "single"
        self._panel_collapsed = False
        self._active_tab = _DEFAULT_TAB_INDEX
        self._updating_tabs = False
        self.setFixedWidth(self._expanded_rail_width())

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget(self)
        self._stack.setFixedWidth(self._module_width)
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        # Clip overflowing page content so it cannot paint over the tab strip.
        self._stack.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._stack.setStyleSheet(
            "QStackedWidget { background: transparent; }"
        )

        self._show_page = self._build_show_page()
        self._annotations_page = self._build_annotations_page()
        self._find_page = self._build_find_page()
        self._others_page = self._build_others_page()
        self._primers_page = self._build_primers_page()
        self._stack.addWidget(self._show_page)
        self._stack.addWidget(self._annotations_page)
        self._stack.addWidget(self._find_page)
        self._stack.addWidget(self._others_page)
        self._stack.addWidget(self._primers_page)

        self._divider = QFrame(self)
        self._divider.setFrameShape(QFrame.Shape.VLine)
        self._divider.setFrameShadow(QFrame.Shadow.Plain)
        self._divider.setFixedWidth(1)
        self._divider.setStyleSheet("color: palette(mid);")

        self._tab_strip = QWidget(self)
        self._tab_strip.setFixedWidth(_RAIL_TAB_WIDTH)
        self._tab_strip.setObjectName("annotationRailTabs")
        tab_layout = QVBoxLayout(self._tab_strip)
        tab_layout.setContentsMargins(1, 2, 1, 2)
        tab_layout.setSpacing(2)

        # Non-exclusive: re-clicking the active tab collapses the panel.
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(False)
        self._tab_buttons: list[_RotatedTabButton] = []
        self._tab_tips = (
            "Display — tracks, colors, and sizes (click again to hide)",
            "Annotations — detect, edit, and transfer features (click again to hide)",
            "Find — motif search in the active sequence (click again to hide)",
            "Others — extra options (click again to hide)",
            "Primers: primers on this sequence and PCR (click again to hide)",
        )
        for index, (label, tip) in enumerate(
            (
                ("Display", self._tab_tips[0]),
                ("Annotation", self._tab_tips[1]),
                ("Find", self._tab_tips[2]),
                ("Others", self._tab_tips[3]),
                ("Primers", self._tab_tips[4]),
            )
        ):
            btn = _RotatedTabButton(label, self._tab_strip)
            btn.setToolTip(tip)
            self._tab_group.addButton(btn, index)
            tab_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._tab_buttons.append(btn)
            btn.clicked.connect(lambda _checked=False, i=index: self._on_tab_clicked(i))
        # Primers and Probes is reached from the menu, which opens this page on
        # the item that was clicked, so the rail has no button of its own for it.
        self._tab_buttons[PRIMERS_TAB_INDEX].setVisible(False)
        tab_layout.addStretch(1)

        root.addWidget(self._stack, 0)
        root.addWidget(self._divider, 0)
        root.addWidget(self._tab_strip, 0)
        self._restore_rail_ui_state()

    def _expanded_rail_width(self) -> int:
        strip = getattr(self, "_tab_strip", None)
        if strip is not None and strip.isHidden():
            # No strip of buttons (the Primers and Probes workspace): the rail
            # is as wide as its page, with no empty room beside it.
            return int(self._module_width)
        return int(self._module_width) + _RAIL_TAB_WIDTH + 1

    def _apply_module_geometry(self) -> None:
        """Resize the module column and every scroll page to ``_module_width``."""
        width = max(200, int(self._module_width))
        self._module_width = width
        self._stack.setFixedWidth(width)
        for index in range(self._stack.count()):
            page = self._stack.widget(index)
            if page is None:
                continue
            page.setFixedWidth(width)
            page.setMinimumWidth(0)
            page.setMaximumWidth(width)
            # Top-level scroll pages, or nested scroll (Annotation footer shell).
            scrolls = (
                [page]
                if isinstance(page, QScrollArea)
                else page.findChildren(QScrollArea)
            )
            for scroll in scrolls:
                scroll.setFixedWidth(width)
                scroll.setMinimumWidth(0)
                scroll.setMaximumWidth(width)
                body = scroll.widget()
                if body is not None:
                    body.setMinimumWidth(0)
                    body.setMaximumWidth(width)
        if not self._panel_collapsed:
            self.setFixedWidth(self._expanded_rail_width())
        self._refresh_similarity_db_labels()
        self._schedule_annotation_kinds_overflow_sync()

    def _refresh_similarity_db_labels(self) -> None:
        host = getattr(self, "similarity_db_host", None)
        if isinstance(host, SimilarityDatabaseGrid):
            host._reflow_column_widths()
            return
        if host is None:
            return
        for check in host.findChildren(SimilarityDatabaseCheck):
            check._refresh_label()

    def refresh_feature_detect_check_colors(self) -> None:
        """Color Feature detection labels from the annotation colors panel."""
        checks = getattr(self, "auto_ann_checks", None)
        if not isinstance(checks, dict):
            return
        for label, check in checks.items():
            feature_type = _FEATURE_DETECT_TYPE_BY_LABEL.get(str(label), str(label))
            color = feature_type_color(feature_type)
            check.setStyleSheet(f"QCheckBox {{ color: {color}; }}")

    def refresh_manual_feature_check_colors(self) -> None:
        """Color Manually add feature labels from the annotation colors panel."""
        checks = getattr(self, "manual_feature_checks", None)
        if not isinstance(checks, dict):
            return
        for feature_type, check in checks.items():
            color = feature_type_color(str(feature_type))
            check.setStyleSheet(f"QCheckBox {{ color: {color}; }}")

    def _fill_rail_surface(self, widget: QWidget) -> None:
        """Paint with palette Window (same as a plain page before the footer split)."""
        widget.setAutoFillBackground(True)
        color = self.palette().color(QPalette.ColorRole.Window)
        pal = widget.palette()
        pal.setColor(QPalette.ColorRole.Window, color)
        pal.setColor(QPalette.ColorRole.Base, color)
        widget.setPalette(pal)

    @staticmethod
    def _clear_rail_surface(widget: QWidget) -> None:
        """Let a parent-painted shell show through (no white header/footer strips)."""
        widget.setAutoFillBackground(False)

    def _wrap_scroll(self, body: QWidget) -> QScrollArea:
        # Never let page contents force the rail wider than the module column.
        width = self._module_width
        body.setMinimumWidth(0)
        body.setMaximumWidth(width)
        body.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Minimum,
        )
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumWidth(0)
        scroll.setFixedWidth(width)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )
        scroll.setWidget(body)
        # Same surface as other rail pages (Display / Find / Others).
        self._fill_rail_surface(scroll)
        self._fill_rail_surface(scroll.viewport())
        self._fill_rail_surface(body)
        scroll.viewport().setMinimumWidth(0)
        return scroll

    def _shell_with_sticky_title(
        self,
        title: str,
        body: QWidget,
        *,
        store_rule_as: str | None = None,
    ) -> QWidget:
        """Pin ``title`` above a scrollable body (Annotations header pattern).

        Display / Find / Others / Primers used to put the page title inside the
        scroll area, so it disappeared when scrolling. Keep it fixed like the
        Annotations tab.
        """
        shell = QWidget()
        shell.setMinimumWidth(0)
        shell.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        self._fill_rail_surface(shell)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        title_host = QWidget(shell)
        title_host.setMinimumWidth(0)
        self._clear_rail_surface(title_host)
        title_layout = QVBoxLayout(title_host)
        title_layout.setContentsMargins(10, 10, 10, 0)
        title_layout.setSpacing(0)
        title_widget, rule = _page_title_with_rule(title, title_host)
        if store_rule_as:
            setattr(self, store_rule_as, rule)
        title_layout.addWidget(title_widget)
        shell_layout.addWidget(title_host, 0)
        shell.sticky_title = title_host

        scroll = self._wrap_scroll(body)
        # Transparent scroll so shell Window fill matches Annotations.
        self._clear_rail_surface(scroll)
        self._clear_rail_surface(scroll.viewport())
        self._clear_rail_surface(body)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        shell_layout.addWidget(scroll, 1)
        return shell

    def _full_width_button(self, text: str, page: QWidget) -> QPushButton:
        btn = QPushButton(text, page)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # macOS QPushButton sizeHints are often wider than half the rail.
        btn.setMinimumWidth(0)
        btn.setMaximumWidth(self._module_width)
        return btn

    def _build_show_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        # Same compact spacing as the tree Display rail.
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        # Keep sequence switcher widgets for multi-record wiring, but do not show
        # them on the Display panel (overview / Find cover that job).
        self.sequence_combo = QComboBox(page)
        self.sequence_combo.setEditable(False)
        self.sequence_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.sequence_combo.hide()
        self.sequence_search = QLineEdit(page)
        self.sequence_search.setPlaceholderText("Filter by name…")
        self.sequence_search.setClearButtonEnabled(True)
        self.sequence_search.hide()
        self.seq_count_label = QLabel("", page)
        self.seq_count_label.setStyleSheet("color: palette(mid);")
        self.seq_count_label.hide()

        # --- Tracks (collapsible, same pattern as Annotations) ------------
        tracks_section = _CollapsibleSection("Tracks", page, expanded=True)
        self._tracks_section = tracks_section

        # Sorting → Show standard boundaries → Displayed annotations (grows with kinds).
        sort_row = QWidget(tracks_section)
        sort_layout = QHBoxLayout(sort_row)
        sort_layout.setContentsMargins(0, 2, 0, 2)
        sort_layout.setSpacing(6)
        self.sequence_sort_label = QLabel("Sorting:", sort_row)
        self.sequence_sort = QComboBox(sort_row)
        self.sequence_sort.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.sequence_sort.setToolTip(
            "Reorder overview sequences. "
            "Original order is the file / MSA load order. "
            "Sequence name sorts alphabetically. "
            "Selected column (MSA only) sorts once by residues in the "
            "currently selected column range — changing the selection "
            "does not re-sort until you choose Selected column again."
        )
        # activated: re-choosing the same option (e.g. Selected column) re-applies.
        self.sequence_sort.activated.connect(self._on_sequence_sort_changed)
        sort_layout.addWidget(self.sequence_sort_label, 0)
        sort_layout.addWidget(self.sequence_sort, 1)
        tracks_section.add_widget(sort_row)
        self.sequence_sort_row = sort_row
        self._populate_sequence_sort_options(msa=False)
        self.sequence_sort_row.setVisible(False)

        self.show_standard_boundaries = QCheckBox(
            "Show reference boundaries", tracks_section
        )
        self.show_standard_boundaries.setChecked(True)
        self.show_standard_boundaries.setToolTip(
            "Draw vertical dashed lines at the leftmost and rightmost non-gap "
            "nucleotides of the reference sequence (through the scale and tracks). "
            "Works with any MSA color scheme. Right-click a sequence and choose "
            "Set as reference to pin the reference row."
        )
        self.show_standard_boundaries.toggled.connect(
            self.showStandardBoundariesChanged.emit
        )
        self.show_standard_boundaries.setVisible(False)
        tracks_section.add_widget(self.show_standard_boundaries)

        self.show_blast_coverage = QCheckBox("Show BLAST coverage", tracks_section)
        self.show_blast_coverage.setChecked(True)
        self.show_blast_coverage.setToolTip(
            "Show or hide the Coverage track above the MSA."
        )
        self.show_blast_coverage.toggled.connect(self.showBlastCoverageChanged.emit)
        _COVERAGE_TRACK_HELP = (
            "<p><b>Coverage track</b> plots how often the MSA consensus is found "
            "in the reference genome (TE-Aid-style BLAST hit depth).</p>"
            "<p><b>How to run</b><br/>"
            "Click <b>Cov</b> on the overview toolbar. RepeatViewer builds a "
            "majority consensus at threshold 0, BLASTs it against the reference "
            "genome (Manage Database), then draws one filled coverage profile "
            "above the alignment.</p>"
        )
        self.show_blast_coverage_row = field_with_help(
            self.show_blast_coverage,
            "Show BLAST coverage",
            _COVERAGE_TRACK_HELP,
            parent=tracks_section,
            stretch=True,
        )
        self.show_blast_coverage_row.setVisible(False)
        tracks_section.add_widget(self.show_blast_coverage_row)

        self.sync_split_views = QCheckBox("Sync left and right view", tracks_section)
        self.sync_split_views.setChecked(False)
        self.sync_split_views.setToolTip(
            "In Split Preview, keep both panes aligned by sequence row "
            "(same sequence at the same vertical level even at different zoom) "
            "and selection. Displayed annotations stay independent per pane. "
            "Horizontal position / columns stay independent so each pane can "
            "show a different region."
        )
        self.sync_split_views.toggled.connect(self.syncSplitViewsChanged.emit)
        self.sync_split_views.setVisible(False)
        self._split_sync_available = False
        tracks_section.add_widget(self.sync_split_views)

        self.show_complement = QCheckBox("Show complement", tracks_section)
        self.show_complement.setToolTip(
            "Show the complementary strand under the forward sequence "
            "(only when zoomed in to individual nucleotides)."
        )
        self.show_complement.toggled.connect(self.showComplementChanged.emit)
        tracks_section.add_widget(self.show_complement)

        self.show_translation = QCheckBox("Show translation", tracks_section)
        self.show_translation.setToolTip(
            "Show amino-acid translation rows under the sequence "
            "(only when zoomed in to individual nucleotides)."
        )
        self.show_translation.toggled.connect(self._on_show_translation_toggled)
        tracks_section.add_widget(self.show_translation)

        # Hidden frame checkboxes keep settings load/save and map wiring stable.
        self.frame_checks: dict[int, QCheckBox] = {}
        for frame in TRANSLATION_FRAMES:
            check = QCheckBox(tracks_section)
            check.hide()
            check.setChecked(frame == 1)
            self.frame_checks[frame] = check
        self._translation_three_letter = False
        self._translation_genetic_code = 1

        self.split_tracks_by_source = QCheckBox(
            "Split annotation by source", tracks_section
        )
        self.split_tracks_by_source.setToolTip(
            "When checked, features from different sources use separate visual "
            "tracks even if they share the same track number."
        )
        self.split_tracks_by_source.toggled.connect(
            self.splitTracksBySourceChanged.emit
        )
        tracks_section.add_widget(self.split_tracks_by_source)

        # Displayed annotations sit below Split-by-source; only types present
        # on the loaded sequence(s) are listed (see set_available_annotation_kinds).
        self.displayed_annotations_label = QLabel(
            "Displayed annotations", tracks_section
        )
        self.displayed_annotations_label.setToolTip(
            "Choose which annotation types appear on the sequence map "
            "(and under each sequence in Overview / MSA). Only types that "
            "exist on the current sequence(s) are listed. Types that do not "
            "fit in the short list are under More."
        )
        tracks_section.add_widget(self.displayed_annotations_label)

        # Hidden compat toggle: True when at least one type checkbox is on.
        self.show_annotation_track = QCheckBox(tracks_section)
        self.show_annotation_track.hide()
        self.show_annotation_track.setChecked(True)

        # Type filters: All on its own row, then present types in a flow
        # capped to ~2 rows; extras open from the More menu.
        self._annotation_kinds_host = QWidget(tracks_section)
        self._annotation_kinds_host.setMinimumWidth(0)
        self._annotation_kinds_host.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        kinds_outer = QVBoxLayout(self._annotation_kinds_host)
        kinds_outer.setContentsMargins(0, 0, 0, 2)
        kinds_outer.setSpacing(4)
        self.annotation_kind_checks: dict[str, QCheckBox] = {}
        self._annotation_kinds_overflow_keys: list[str] = []
        self.annotation_kinds_all_check = QCheckBox("All", self._annotation_kinds_host)
        self.annotation_kinds_all_check.setToolTip(
            "Select or clear all annotation types"
        )
        self._annotation_kinds_all_updating = False
        self.annotation_kinds_all_check.toggled.connect(
            self._on_annotation_kinds_all_toggled
        )
        kinds_outer.addWidget(self.annotation_kinds_all_check, 0, Qt.AlignmentFlag.AlignLeft)
        self._annotation_kinds_flow_host = QWidget(self._annotation_kinds_host)
        self._annotation_kinds_flow_host.setMinimumWidth(0)
        self._annotation_kinds_flow_host.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        self._annotation_kinds_flow_host.setMaximumHeight(
            _ANNOTATION_KINDS_FLOW_MAX_HEIGHT
        )
        self._annotation_kinds_flow = _FlowLayout(
            self._annotation_kinds_flow_host, spacing=6
        )
        self._annotation_kinds_flow_host.setLayout(self._annotation_kinds_flow)
        self._annotation_kinds_flow_host.installEventFilter(self)
        kinds_outer.addWidget(self._annotation_kinds_flow_host)
        self._annotation_kinds_more_btn = QPushButton("More", self._annotation_kinds_host)
        self._annotation_kinds_more_btn.setToolTip(
            "Show annotation types that did not fit above."
        )
        self._annotation_kinds_more_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self._annotation_kinds_more_btn.clicked.connect(
            self._on_annotation_kinds_more_clicked
        )
        self._annotation_kinds_more_btn.hide()
        kinds_outer.addWidget(
            self._annotation_kinds_more_btn, 0, Qt.AlignmentFlag.AlignLeft
        )
        self._hidden_annotation_kinds = self._load_hidden_annotation_kinds()
        self._rebuild_annotation_kind_checks([])
        self._sync_displayed_annotations_section_visible()
        tracks_section.add_widget(self._annotation_kinds_host)

        self.translation_more_btn = QPushButton("Setting", tracks_section)
        self.translation_more_btn.setEnabled(False)
        self.translation_more_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.translation_more_btn.setToolTip(
            "Choose reading frames, three-letter amino acids, and genetic code."
        )
        self.translation_more_btn.clicked.connect(self._open_translation_settings)
        tracks_section.add_widget(self.translation_more_btn)
        layout.addWidget(tracks_section)

        # --- Color --------------------------------------------------------
        layout.addWidget(_h_divider(page))
        color_section = _CollapsibleSection("Color", page, expanded=True)
        self._color_section = color_section

        color_form = QFormLayout()
        color_form.setContentsMargins(0, 0, 0, 0)
        color_form.setHorizontalSpacing(8)
        color_form.setVerticalSpacing(6)
        color_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint
        )
        color_form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        scheme_width = 120
        self.nucleotide_scheme = QComboBox(color_section)
        self.nucleotide_scheme.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.nucleotide_scheme.setFixedWidth(scheme_width)
        self.nucleotide_scheme.setToolTip(
            "Quick nucleotide letter colours for the sequence view."
        )
        for name, _palette in NUCLEOTIDE_COLOR_PRESETS:
            self.nucleotide_scheme.addItem(name)
        self.nucleotide_scheme.currentIndexChanged.connect(
            self._on_nucleotide_scheme_changed
        )

        self.protein_scheme = QComboBox(color_section)
        self.protein_scheme.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.protein_scheme.setFixedWidth(scheme_width)
        self.protein_scheme.setToolTip(
            "Quick amino-acid colour scheme for protein sequences / translations."
        )
        for name, _palette in AMINO_ACID_COLOR_PRESETS:
            self.protein_scheme.addItem(name)
        self.protein_scheme.currentIndexChanged.connect(
            self._on_protein_scheme_changed
        )

        color_form.addRow("Nucleotide:", self.nucleotide_scheme)
        color_form.addRow("Protein:", self.protein_scheme)
        color_section.add_layout(color_form)

        self.color_multi_sequence_background = QCheckBox(
            "Color letter background", color_section
        )
        self.color_multi_sequence_background.setChecked(True)
        self.color_multi_sequence_background.setToolTip(
            "Checked: color each nucleotide/protein cell background. "
            "Unchecked: use a plain background and color the letters."
        )
        self.color_multi_sequence_background.toggled.connect(
            self.multiSequenceBackgroundChanged.emit
        )
        self.color_multi_sequence_background.hide()
        color_section.add_widget(self.color_multi_sequence_background)

        from repeatviewer.backends.msa_coordinates import (
            DEFAULT_MSA_DIVERGENCE_THRESHOLD,
            MSA_COLOR_ALL_BACKGROUNDS,
            MSA_COLOR_MODE_CHOICES,
        )

        _MSA_SCHEME_HELP = (
            "Controls residue colouring in the MSA (nucleotide and protein) "
            "at overview and letter zoom.<br><br>"
            "<b>No color</b><br>"
            "Overview: light-grey sequence bars. Letter zoom: coloured "
            "letters on white cells.<br><br>"
            "<b>Color all</b><br>"
            "Fill every residue with its nucleotide/protein colour.<br><br>"
            "<b>Color conserved</b><br>"
            "Colour only letters that meet the divergence threshold; "
            "other residues stay light grey (overview) or unfilled "
            "(letter zoom).<br><br>"
            "<b>Color divergent</b><br>"
            "Colour only letters below the divergence threshold; "
            "conserved residues stay light grey (overview) or unfilled "
            "(letter zoom).<br><br>"
            "<b>Color vs reference</b><br>"
            "Uses a fixed colour scheme (independent of Display → Nucleotide). "
            "The reference row is painted with the All-black palette, and its "
            "name is shown in bold with an accent colour (also when Show "
            "reference boundaries is on). Residues that match the reference use "
            "a black letter on an unfilled background. Other rows highlight "
            "residues and gaps that differ from it (gap differences stay red). "
            "A differing nucleotide that meets the Divergence threshold uses "
            "the Default nucleotide colours; a differing nucleotide that is "
            "not conserved uses black. <b>N</b> / <b>X</b> always use a yellow "
            "highlight so ambiguous bases stay visible. With no reference set "
            "yet, the first sequence is used. Right-click a sequence and choose "
            "<b>Set as reference</b> to pin a different row; that choice stays "
            "for this MSA until you change it.<br><br>"
            "<b>Divergence</b><br>"
            "A letter is conserved when it occupies at least this fraction "
            "of the non-gap residues in its column. For example, "
            "<b>0.40</b> means a letter present in ≥40% of sequences "
            "(ignoring gaps) counts as conserved. Applies to Color "
            "conserved, Color divergent, and Color vs reference."
        )

        self.msa_coloring_label = QLabel("MSA color scheme:", color_section)
        scheme_header = QWidget(color_section)
        scheme_header_layout = QHBoxLayout(scheme_header)
        scheme_header_layout.setContentsMargins(0, 4, 0, 0)
        scheme_header_layout.setSpacing(4)
        scheme_header_layout.addWidget(self.msa_coloring_label, 0)
        scheme_header_layout.addWidget(
            make_help_button(
                scheme_header,
                "MSA color scheme",
                _MSA_SCHEME_HELP,
            ),
            0,
        )
        scheme_header_layout.addStretch(1)
        color_section.add_widget(scheme_header)

        self._msa_color_group = QButtonGroup(color_section)
        self._msa_color_radios: dict[str, QRadioButton] = {}
        mode_host = QWidget(color_section)
        mode_layout = QVBoxLayout(mode_host)
        mode_layout.setContentsMargins(16, 0, 0, 0)
        mode_layout.setSpacing(2)
        for mode_id, label in MSA_COLOR_MODE_CHOICES:
            radio = QRadioButton(label, mode_host)
            self._msa_color_group.addButton(radio)
            self._msa_color_radios[mode_id] = radio
            mode_layout.addWidget(radio)
        color_section.add_widget(mode_host)
        self.msa_coloring_mode_host = mode_host

        div_row = QWidget(color_section)
        div_layout = QHBoxLayout(div_row)
        div_layout.setContentsMargins(16, 4, 0, 0)
        div_layout.setSpacing(6)
        self.msa_divergence_label = QLabel("Divergence:", div_row)
        self.msa_divergence_slider = NoWheelSlider(
            Qt.Orientation.Horizontal, div_row
        )
        self.msa_divergence_slider.setObjectName("annotationZoomSlider")
        self.msa_divergence_slider.setRange(0, 100)
        self.msa_divergence_slider.setValue(
            int(round(DEFAULT_MSA_DIVERGENCE_THRESHOLD * 100))
        )
        self.msa_divergence_slider.setMinimumWidth(72)
        self.msa_divergence_slider.setFixedHeight(18)
        self.msa_divergence_slider.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        apply_annotation_zoom_slider_style(self.msa_divergence_slider)
        self.msa_divergence_value = QLabel(
            f"{DEFAULT_MSA_DIVERGENCE_THRESHOLD:.2f}", div_row
        )
        self.msa_divergence_value.setMinimumWidth(36)
        self.msa_divergence_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.msa_divergence_slider.valueChanged.connect(
            self._on_msa_divergence_slider_changed
        )
        div_layout.addWidget(self.msa_divergence_label, 0)
        div_layout.addWidget(self.msa_divergence_slider, 1)
        div_layout.addWidget(self.msa_divergence_value, 0)
        color_section.add_widget(div_row)
        self.msa_divergence_row = div_row

        # Connect after divergence row exists (toggled fires on setChecked).
        for radio in self._msa_color_radios.values():
            radio.toggled.connect(self._on_msa_coloring_mode_changed)
        default_radio = self._msa_color_radios.get(MSA_COLOR_ALL_BACKGROUNDS)
        if default_radio is not None:
            default_radio.setChecked(True)
        self._sync_msa_divergence_enabled()

        # Hidden until overview/MSA Display mode enables it.
        self.msa_coloring_label.setVisible(False)
        scheme_header.setVisible(False)
        self.msa_coloring_header = scheme_header
        self.msa_coloring_mode_host.setVisible(False)
        self.msa_divergence_row.setVisible(False)

        self.colors_btn = QPushButton("Setting", color_section)
        self.colors_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.colors_btn.setToolTip(
            "Open the full colour editor for nucleotides, amino acids, "
            "feature types, and similarity databases."
        )
        self.colors_btn.clicked.connect(self.colorsClicked.emit)
        color_section.add_widget(self.colors_btn)
        layout.addWidget(color_section)

        # --- Size (moved from Others) -------------------------------------
        layout.addWidget(_h_divider(page))
        size_section = _CollapsibleSection("Size", page, expanded=True)
        self._size_section = size_section

        sizes = QFormLayout()
        sizes.setContentsMargins(0, 0, 0, 0)
        sizes.setHorizontalSpacing(8)
        sizes.setVerticalSpacing(6)
        sizes.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        sizes.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        spin_expand = QSizePolicy.Policy.Expanding
        self.bases_font_label = QLabel("DNA/protein labels:", size_section)
        self.bases_zoomed_in = NoWheelSpinBox(size_section)
        self.bases_zoomed_in.setRange(2, 36)
        self.bases_zoomed_in.setValue(6)  # single-seq default
        self.bases_zoomed_in.setSizePolicy(spin_expand, QSizePolicy.Policy.Fixed)
        self.bases_zoomed_in.setToolTip(
            "Point size of sequence letters when zoomed in enough to show "
            "individual bases (DNA) or residues (protein)."
        )
        self.bases_zoomed_in.valueChanged.connect(self.basesZoomedInChanged.emit)

        # MSA / multi-sequence Overview: replaces DNA/protein labels.
        self.track_height_label = QLabel("Track height:", size_section)
        self.track_height = NoWheelSpinBox(size_section)
        self.track_height.setRange(1, 10)
        self.track_height.setValue(5)
        self.track_height.setSizePolicy(spin_expand, QSizePolicy.Policy.Fixed)
        self.track_height.setToolTip(
            "Vertical height of each squeezed sequence track (1–10). "
            "10 matches the track height at DNA/protein size 10 "
            "(zoom slider at ¾). Scale double-click zooms to that size."
        )
        self.track_height.valueChanged.connect(self.trackHeightChanged.emit)
        self.track_height_label.setVisible(False)
        self.track_height.setVisible(False)

        self.track_distance_label = QLabel("Track distance:", size_section)
        self.track_distance = NoWheelSpinBox(size_section)
        self.track_distance.setRange(0, 40)
        self.track_distance.setValue(1)
        self.track_distance.setSizePolicy(spin_expand, QSizePolicy.Policy.Fixed)
        self.track_distance.setToolTip(
            "When annotations are hidden: space between sequence tracks "
            "(0 = tracks touch). When annotations are shown: space below "
            "each sequence band above its first annotation row."
        )
        self.track_distance.valueChanged.connect(self.trackDistanceChanged.emit)
        self.track_distance_label.setVisible(False)
        self.track_distance.setVisible(False)

        # Kept for settings / map wiring; not shown in the Size section.
        self.bases_zoomed_out = NoWheelSpinBox(size_section)
        self.bases_zoomed_out.setRange(1, 24)
        self.bases_zoomed_out.setValue(4)
        self.bases_zoomed_out.hide()
        self.bases_zoomed_out.valueChanged.connect(self.basesZoomedOutChanged.emit)

        self.annotation_label_size = NoWheelSpinBox(size_section)
        self.annotation_label_size.setRange(0, 24)
        self.annotation_label_size.setValue(7)
        self.annotation_label_size.setSizePolicy(spin_expand, QSizePolicy.Policy.Fixed)
        self.annotation_label_size.setToolTip(
            "Font size for labels on annotation bars (e.g. ORF / LTR / Pfam names). "
            "0 hides labels."
        )
        self.annotation_label_size.valueChanged.connect(
            self.annotationLabelSizeChanged.emit
        )

        self.annotation_thickness = NoWheelSpinBox(size_section)
        self.annotation_thickness.setRange(2, 40)
        self.annotation_thickness.setValue(18)
        self.annotation_thickness.setSizePolicy(spin_expand, QSizePolicy.Policy.Fixed)
        self.annotation_thickness.setToolTip(
            "Vertical height of annotation feature bars (pixels)."
        )
        self.annotation_thickness.valueChanged.connect(
            self.annotationThicknessChanged.emit
        )

        self.annotation_distance = NoWheelSpinBox(size_section)
        self.annotation_distance.setRange(0, 40)
        self.annotation_distance.setValue(0)
        self.annotation_distance.setSizePolicy(spin_expand, QSizePolicy.Policy.Fixed)
        self.annotation_distance.setToolTip(
            "Vertical gap between annotation rows (pixels)."
        )
        self.annotation_distance.valueChanged.connect(
            self.annotationDistanceChanged.emit
        )

        self.base_number_size = NoWheelSpinBox(size_section)
        self.base_number_size.setRange(4, 24)
        self.base_number_size.setValue(8)
        self.base_number_size.setSizePolicy(spin_expand, QSizePolicy.Policy.Fixed)
        self.base_number_size.setToolTip(
            "Font size for scale (base/residue position) labels."
        )
        self.base_number_size.valueChanged.connect(self.baseNumberSizeChanged.emit)

        self.sequence_distance = NoWheelSpinBox(size_section)
        self.sequence_distance.setRange(0, 40)
        self.sequence_distance.setValue(1)
        self.sequence_distance.setSizePolicy(spin_expand, QSizePolicy.Policy.Fixed)
        self.sequence_distance.setToolTip(
            "Vertical gap between sequences (pixels) when annotation tracks "
            "are shown. When annotations are hidden, use Track distance "
            "instead (0 = tracks touch)."
        )
        self.sequence_distance.valueChanged.connect(self.sequenceDistanceChanged.emit)
        self._sequence_distance_label = QLabel("Sequence distance:", size_section)
        # Overview/MSA only — hidden for single-sequence map.
        self._sequence_distance_label.setVisible(False)
        self.sequence_distance.setVisible(False)

        self.column_distance = NoWheelSpinBox(size_section)
        self.column_distance.setRange(0, 40)
        self.column_distance.setValue(0)
        self.column_distance.setSizePolicy(spin_expand, QSizePolicy.Policy.Fixed)
        self.column_distance.setToolTip(
            "Horizontal gap between MSA residue backgrounds (pixels). "
            "0 connects neighbouring nucleotides."
        )
        self.column_distance.valueChanged.connect(self.columnDistanceChanged.emit)
        self._column_distance_label = QLabel("Column distance:", size_section)
        # Overview/MSA only — hidden for single-sequence map.
        self._column_distance_label.setVisible(False)
        self.column_distance.setVisible(False)

        self.sequence_name_size = NoWheelSpinBox(size_section)
        self.sequence_name_size.setRange(8, 24)
        self.sequence_name_size.setValue(12)
        self.sequence_name_size.hide()
        self.sequence_name_size.valueChanged.connect(self.sequenceNameSizeChanged.emit)

        sizes.addRow(self.bases_font_label, self.bases_zoomed_in)
        sizes.addRow(self.track_height_label, self.track_height)
        sizes.addRow(self.track_distance_label, self.track_distance)
        sizes.addRow("Annotation labels:", self.annotation_label_size)
        sizes.addRow("Annotation thickness:", self.annotation_thickness)
        self._annotation_distance_label = QLabel(
            "Annotation distance:", size_section
        )
        sizes.addRow(self._annotation_distance_label, self.annotation_distance)
        sizes.addRow("Scale labels:", self.base_number_size)
        sizes.addRow(self._sequence_distance_label, self.sequence_distance)
        sizes.addRow(self._column_distance_label, self.column_distance)
        size_section.add_layout(sizes)
        layout.addWidget(size_section)

        self.status_label = QLabel("", page)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        self.sync_color_scheme_combos()
        return self._shell_with_sticky_title(
            "Display", page, store_rule_as="_tracks_divider"
        )

    def _build_primers_page(self) -> QWidget:
        from repeatviewer.widgets.primers_panel import PrimersPanel

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        self.primers_panel = PrimersPanel(page, width=self._module_width)
        layout.addWidget(self.primers_panel, 1)
        shell = self._shell_with_sticky_title("Primers", page)
        # The Primers and Probes workspace names its sections itself and hides this.
        self.primers_page_title = shell.sticky_title
        return shell

    def show_primers_tab(self) -> None:
        self.set_current_tab(PRIMERS_TAB_INDEX)

    def _build_others_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        layout.addStretch(1)
        return self._shell_with_sticky_title("Others", page)

    def _two_column_buttons(
        self, buttons: list[QPushButton], page: QWidget
    ) -> QWidget:
        """Lay out action buttons two per row, filling the rail width."""
        host = QWidget(page)
        host.setMinimumWidth(0)
        host.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        for index in range(0, len(buttons), 2):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            left = buttons[index]
            left.setMinimumWidth(0)
            left.setMaximumWidth(self._module_width)
            left.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
            )
            if index + 1 < len(buttons):
                right = buttons[index + 1]
                right.setMinimumWidth(0)
                right.setMaximumWidth(self._module_width)
                right.setSizePolicy(
                    QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
                )
                row.addWidget(left, 1)
                row.addWidget(right, 1)
            else:
                # Odd last button spans the full row.
                row.addWidget(left, 1)
            column.addLayout(row)
        return host

    def _compact_run_more_row(
        self,
        page: QWidget,
        *,
        run_tooltip: str,
        more_tooltip: str,
        run_clicked,
        more_clicked,
    ) -> tuple[QWidget, QPushButton, QPushButton]:
        row = QWidget(page)
        row.setMinimumWidth(0)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        run_btn = QPushButton("Run", row)
        run_btn.setToolTip(run_tooltip)
        run_btn.setFixedWidth(52)
        run_btn.clicked.connect(run_clicked)
        more_btn = QPushButton("Setting", row)
        more_btn.setToolTip(more_tooltip)
        more_btn.setFixedWidth(64)
        more_btn.clicked.connect(more_clicked)
        layout.addWidget(run_btn, 0)
        layout.addWidget(more_btn, 0)
        layout.addStretch(1)
        return row, run_btn, more_btn

    def _build_annotations_page(self) -> QWidget:
        # Shell: header + scrollable sections + fixed footer (Delete/Restore/…).
        shell = QWidget()
        shell.setObjectName("annotationRailShell")
        shell.setMinimumWidth(0)
        shell.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        self._fill_rail_surface(shell)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        header = QWidget(shell)
        header.setObjectName("annotationRailHeader")
        header.setMinimumWidth(0)
        self._clear_rail_surface(header)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(10, 10, 10, 6)
        header_layout.setSpacing(0)
        header_layout.addWidget(_section_label("Annotations", header))
        shell_layout.addWidget(header, 0)
        # Rule between title and Feature detection (inset like page content).
        title_rule_host = QWidget(shell)
        self._clear_rail_surface(title_rule_host)
        title_rule_layout = QVBoxLayout(title_rule_host)
        title_rule_layout.setContentsMargins(10, 0, 10, 0)
        title_rule_layout.setSpacing(0)
        title_rule_layout.addWidget(_h_divider(title_rule_host))
        shell_layout.addWidget(title_rule_host, 0)

        page = QWidget()
        page.setMinimumWidth(0)
        layout = QVBoxLayout(page)
        # Same gap between rows as Display (Tracks / Color / Size), for single
        # sequence, MSA, and multi-sequence.
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        # Hidden compatibility alias — Add moved to "Manually add feature" below.
        self.add_feature_btn = QPushButton("Add", page)
        self.add_feature_btn.hide()

        # Job progress is shown on the main-window progress bar; keep a hidden
        # label so set_annotation_job_status callers stay valid without showing
        # grey status text in this rail.
        self.annotation_job_status = QLabel("", page)
        self.annotation_job_status.hide()

        # Boundary prediction (MSA only): TEtrimmer column clean + boundaries.
        self.boundary_section = _CollapsibleSection(
            "Boundary prediction", page, expanded=False
        )
        self.boundary_rows_host = QWidget(self.boundary_section)
        self.boundary_rows_host.setMinimumWidth(0)
        rows_grid = QGridLayout(self.boundary_rows_host)
        rows_grid.setContentsMargins(0, 0, 0, 0)
        rows_grid.setHorizontalSpacing(6)
        rows_grid.setVerticalSpacing(2)
        rows_grid.setColumnStretch(1, 1)
        # key → (check, value label); key order is the display order.
        self.boundary_row_widgets: dict[str, tuple[QCheckBox, QLabel]] = {}
        for row, (key, label, color) in enumerate(BOUNDARY_ROWS):
            check = QCheckBox(label, self.boundary_rows_host)
            check.setChecked(False)
            check.setEnabled(False)
            # Method colour while enabled; default grey when the row is None.
            pal = check.palette()
            for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
                pal.setColor(group, QPalette.ColorRole.WindowText, QColor(color))
            check.setPalette(pal)
            check.setToolTip(f"Show the {label} boundary lines on the MSA")
            check.toggled.connect(self._emit_boundary_guides_changed)
            # Keep the full method name; the value column takes the rest.
            check.setMinimumWidth(check.sizeHint().width())
            value = QLabel("None", self.boundary_rows_host)
            value.setEnabled(False)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            rows_grid.addWidget(check, row, 0)
            rows_grid.addWidget(value, row, 1)
            self.boundary_row_widgets[key] = (check, value)
        self.boundary_section.add_widget(self.boundary_rows_host)
        boundary_btn_row = QWidget(self.boundary_section)
        boundary_btn_layout = QHBoxLayout(boundary_btn_row)
        boundary_btn_layout.setContentsMargins(0, 0, 0, 0)
        boundary_btn_layout.setSpacing(6)
        self.boundary_run_btn = QPushButton("Run", boundary_btn_row)
        self.boundary_run_btn.setFixedWidth(52)
        self.boundary_run_btn.setToolTip(
            "Clean the MSA with TEtrimmer's column rules, then predict the TE "
            "boundary from LTR/TIR, MSA identity and genome BLAST coverage. "
            "When the file name contains LINE or SINE, also look for a poly-A "
            "3′ end (as in TEtrimmer). Tick a row to draw its boundary lines."
        )
        self.boundary_run_btn.clicked.connect(self.boundaryPredictClicked.emit)
        boundary_btn_layout.addWidget(self.boundary_run_btn, 0)
        boundary_btn_layout.addWidget(
            make_help_button(
                boundary_btn_row, "Boundary prediction", _BOUNDARY_PREDICTION_HELP
            ),
            0,
        )
        boundary_btn_layout.addStretch(1)
        self.boundary_section.add_widget(boundary_btn_row)
        self.boundary_result_label = QLabel("", self.boundary_section)
        self.boundary_result_label.setWordWrap(True)
        self.boundary_result_label.setTextFormat(Qt.TextFormat.RichText)
        self.boundary_result_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.boundary_result_label.hide()
        self.boundary_section.add_widget(self.boundary_result_label)
        layout.addWidget(self.boundary_section)
        self._boundary_divider = _h_divider(page)
        layout.addWidget(self._boundary_divider)
        self.boundary_section.setVisible(False)
        self._boundary_divider.setVisible(False)

        feature_section = _CollapsibleSection(
            "Feature detection", page, expanded=False
        )
        self.auto_ann_all_check = QCheckBox("All", feature_section)
        feature_section.add_widget(self.auto_ann_all_check)
        self.auto_ann_checks: dict[object, QCheckBox] = {}
        auto_host = QWidget(feature_section)
        auto_host.setMinimumWidth(0)
        auto_flow = _FlowLayout(auto_host, spacing=6)
        auto_host.setLayout(auto_flow)
        for label in ("LTR", "TIR", "Tandem", "ORF", "TSD", "PBS"):
            check = QCheckBox(label, auto_host)
            # TSD needs an MSA (≥2 sequences); leave off by default.
            # PBS needs a prior LTR pair + BLAST+; leave off by default.
            check.setChecked(label not in {"TSD", "PBS"})
            check.setMinimumWidth(0)
            if label == "TSD":
                check.setToolTip(
                    "Target site duplications near putative TE boundaries "
                    "(MSA only; set boundaries under Setting)."
                )
                # Hidden until set_msa_display_mode(True); single-seq / multi
                # unaligned overviews must not offer TSD.
                check.hide()
            elif label == "PBS":
                check.setToolTip(
                    "Primer binding site inside the 5′ LTR (Neumann 2019 "
                    "motifs + blastn). Requires two LTR features; run LTR "
                    "first or keep existing LTR annotations."
                )
            auto_flow.addWidget(check)
            # Keys filled by SequenceMapPanel with AutoAnnotationMode enums.
            self.auto_ann_checks[label] = check
        self.refresh_feature_detect_check_colors()
        feature_section.add_widget(auto_host)
        auto_btn_row, self.auto_ann_run_btn, self.auto_ann_settings_btn = (
            self._compact_run_more_row(
                feature_section,
                run_tooltip="Run feature detection",
                more_tooltip="Feature detection settings",
                run_clicked=self.featureDetectClicked.emit,
                more_clicked=self.featureDetectSettingsClicked.emit,
            )
        )
        feature_section.add_widget(auto_btn_row)
        layout.addWidget(feature_section)

        layout.addWidget(_h_divider(page))
        similarity_section = _CollapsibleSection(
            "Similarity annotation", page, expanded=False
        )
        self.similarity_ann_all_check = QCheckBox(
            "All", similarity_section
        )
        similarity_section.add_widget(self.similarity_ann_all_check)
        # Two-row column-aligned grid; name length caps from panel width.
        self.similarity_db_host = SimilarityDatabaseGrid(similarity_section)
        similarity_section.add_widget(self.similarity_db_host)
        sim_btn_row, self.similarity_ann_run_btn, self.similarity_ann_settings_btn = (
            self._compact_run_more_row(
                similarity_section,
                run_tooltip="Run similarity annotation",
                more_tooltip=(
                    "Similarity annotation settings "
                    "(also used by Sequence Annotation)"
                ),
                run_clicked=self.similarityAnnotateClicked.emit,
                more_clicked=self.similaritySettingsClicked.emit,
            )
        )
        similarity_section.add_widget(sim_btn_row)
        layout.addWidget(similarity_section)

        layout.addWidget(_h_divider(page))
        manual_section = _CollapsibleSection(
            "Manually add feature", page, expanded=False
        )
        self.manual_feature_host = QWidget(manual_section)
        self.manual_feature_host.setMinimumWidth(0)
        self.manual_feature_flow = _FlowLayout(self.manual_feature_host, spacing=6)
        self.manual_feature_host.setLayout(self.manual_feature_flow)
        self.manual_feature_checks: dict[str, QCheckBox] = {}
        self._manual_feature_exclusive = False
        manual_section.add_widget(self.manual_feature_host)
        self.manual_add_btn = QPushButton("Add", manual_section)
        self.manual_add_btn.setFixedWidth(52)
        self.manual_add_btn.setToolTip(
            "Add the checked feature type on the current sequence selection."
        )
        self.manual_add_btn.clicked.connect(self.addFeatureClicked.emit)
        self.manual_feature_settings_btn = QPushButton("Setting", manual_section)
        self.manual_feature_settings_btn.setFixedWidth(64)
        self.manual_feature_settings_btn.setToolTip(
            "Manage which feature types appear in the list."
        )
        self.manual_feature_settings_btn.clicked.connect(
            self.addFeatureSettingsClicked.emit
        )
        manual_btn_row = QHBoxLayout()
        manual_btn_row.setContentsMargins(0, 0, 0, 0)
        manual_btn_row.setSpacing(6)
        manual_btn_row.addWidget(self.manual_add_btn, 0)
        manual_btn_row.addWidget(self.manual_feature_settings_btn, 0)
        manual_btn_row.addStretch(1)
        manual_section.add_layout(manual_btn_row)
        layout.addWidget(manual_section)
        # Hidden combo kept for tests / legacy callers.
        self.manual_feature_combo = QComboBox(page)
        self.manual_feature_combo.hide()
        self.populate_manual_feature_types()

        layout.addWidget(_h_divider(page))
        transfer_section = _CollapsibleSection(
            "Transfer annotation", page, expanded=False
        )

        self.transfer_source_row = PathBrowseRow(
            transfer_section,
            placeholder="FASTA file or folder with annotations…",
            browse_title="Choose transfer source FASTA",
            file_filter=(
                "FASTA (*.fa *.fasta *.fna *.fas *.ffn *.faa);;All files (*)"
            ),
            # Browse opens a menu: FASTA file... or Folder...
            mode="file_or_directory",
            minimum_width=120,
            browse_below=True,
            elide_middle=True,
        )
        self.transfer_source_row.set_default_tooltip(
            "Click a FASTA in Files or a folder in Folders to fill this path "
            "(click the field first to replace an existing path). Or use Browse. "
            "Only annotated sequences (*.seqmap_RV.json) are used."
        )
        self.transfer_source_row.path_changed.connect(self.transferSourceChanged.emit)
        self.transfer_source_row.text_changed.connect(
            lambda _text: self.transferSourceChanged.emit()
        )
        # Compatibility aliases (older code expected a combo + manage button).
        self.transfer_source = QComboBox(transfer_section)
        self.transfer_source.hide()
        self.transfer_manage_db_btn = QPushButton("Browse", transfer_section)
        self.transfer_manage_db_btn.hide()
        self.transfer_manage_db_btn.clicked.connect(
            self.transfer_source_row._on_browse_clicked
        )
        # Hidden target widgets: transfer always uses the currently open sequence.
        self.transfer_target = QComboBox(transfer_section)
        self.transfer_target.hide()
        self.transfer_target_browse = QPushButton("Browse…", transfer_section)
        self.transfer_target_browse.hide()

        self.transfer_selected_only = QCheckBox(
            "Selected features only", transfer_section
        )
        self.transfer_selected_only.hide()
        self.transfer_selected_only.setToolTip(
            "When checked, only features selected on the source track are "
            "transferred. Otherwise all features on the source are used."
        )
        self.transfer_allow_reverse = QCheckBox(
            "Allow reverse strand", transfer_section
        )
        self.transfer_allow_reverse.setChecked(True)

        self.transfer_min_identity_slider, self.transfer_min_identity_value_label = (
            self._transfer_threshold_slider_row(transfer_section)
        )
        self.transfer_min_coverage_slider, self.transfer_min_coverage_value_label = (
            self._transfer_threshold_slider_row(transfer_section)
        )
        # Legacy alias for code that read spin-box values.
        self.transfer_min_identity = NoWheelDoubleSpinBox(transfer_section)
        self.transfer_min_identity.hide()
        self.transfer_min_coverage = NoWheelDoubleSpinBox(transfer_section)
        self.transfer_min_coverage.hide()

        source_label = QLabel("Source", transfer_section)
        transfer_section.add_widget(source_label)
        transfer_section.add_widget(self.transfer_source_row)

        xfer_sliders = QVBoxLayout()
        xfer_sliders.setContentsMargins(0, 0, 0, 0)
        xfer_sliders.setSpacing(6)
        xfer_sliders.addWidget(
            self._threshold_slider_field(
                self.transfer_min_identity_slider,
                self.transfer_min_identity_value_label,
                label="Identity",
            )
        )
        xfer_sliders.addWidget(
            self._threshold_slider_field(
                self.transfer_min_coverage_slider,
                self.transfer_min_coverage_value_label,
                label="Coverage",
            )
        )
        transfer_section.add_layout(xfer_sliders)
        transfer_section.add_widget(self.transfer_selected_only)
        transfer_section.add_widget(self.transfer_allow_reverse)

        xfer_btn_row, self.transfer_run_btn, self.transfer_ann_settings_btn = (
            self._compact_run_more_row(
                transfer_section,
                run_tooltip=self._transfer_run_tooltip(),
                more_tooltip=(
                    "Transfer annotation settings (target similar to source, "
                    "threads, and process window; Threads / process window "
                    "are shared with Feature detection and Similarity "
                    "annotation)"
                ),
                run_clicked=self.transferRequested.emit,
                more_clicked=self.transferSettingsClicked.emit,
            )
        )
        transfer_section.add_widget(xfer_btn_row)
        layout.addWidget(transfer_section)

        self._annotation_sections: dict[str, _CollapsibleSection] = {
            "manual": manual_section,
            "feature_detection": feature_section,
            "similarity": similarity_section,
            "transfer": transfer_section,
        }
        for section in self._annotation_sections.values():
            section.expandedChanged.connect(self._save_rail_ui_state)

        layout.addStretch(1)
        scroll = self._wrap_scroll(page)
        # Transparent scroll so shell Window fill is continuous with header/footer.
        self._clear_rail_surface(scroll)
        self._clear_rail_surface(scroll.viewport())
        self._clear_rail_surface(page)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        shell_layout.addWidget(scroll, 1)

        # Fixed footer — stays visible while the sections above scroll.
        footer = QWidget(shell)
        footer.setMinimumWidth(0)
        footer.setObjectName("annotationRailFooter")
        self._clear_rail_surface(footer)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(10, 8, 10, 10)
        footer_layout.setSpacing(8)
        footer_layout.addWidget(_h_divider(footer))
        self.delete_btn = self._full_width_button("Delete", footer)
        self.delete_btn.clicked.connect(self.deleteClicked.emit)
        self.restore_btn = self._full_width_button("Restore", footer)
        self.restore_btn.clicked.connect(self.restoreClicked.emit)
        self.export_btn = self._full_width_button("Export", footer)
        self.export_btn.clicked.connect(self.exportClicked.emit)
        self.save_btn = self._full_width_button("Save", footer)
        self.save_btn.clicked.connect(self.saveClicked.emit)
        footer_layout.addWidget(
            self._two_column_buttons(
                [
                    self.delete_btn,
                    self.restore_btn,
                    self.export_btn,
                    self.save_btn,
                ],
                footer,
            )
        )
        shell_layout.addWidget(footer, 0)
        return shell

    def _build_find_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        self.find_query = QLineEdit(page)
        self.find_query.setPlaceholderText("Sequence or name…")
        self.find_query.setClearButtonEnabled(True)
        self.find_query.returnPressed.connect(
            lambda: self.findRequested.emit(1)
        )
        find_form = QFormLayout()
        find_form.setContentsMargins(0, 0, 0, 0)
        find_form.setHorizontalSpacing(8)
        find_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        find_form.addRow("Find:", self.find_query)
        layout.addLayout(find_form)

        layout.addWidget(_section_label("Search in", page))
        self.find_in_sequence = QCheckBox("Sequence", page)
        self.find_in_sequence.setChecked(True)
        self.find_in_sequence.toggled.connect(
            lambda *_a: self.sync_find_option_enabled()
        )
        layout.addWidget(self.find_in_sequence)

        self.find_nucleotides = QRadioButton("Nucleotides", page)
        self.find_nucleotides.setChecked(True)
        self.find_protein = QRadioButton("Protein (6 frames)", page)
        mode_group = QButtonGroup(page)
        mode_group.addButton(self.find_nucleotides)
        mode_group.addButton(self.find_protein)
        mode_host = QWidget(page)
        mode_layout = QVBoxLayout(mode_host)
        mode_layout.setContentsMargins(16, 0, 0, 0)
        mode_layout.setSpacing(2)
        mode_layout.addWidget(self.find_nucleotides)
        mode_layout.addWidget(self.find_protein)
        layout.addWidget(mode_host)

        opts = QWidget(page)
        opts_layout = QVBoxLayout(opts)
        opts_layout.setContentsMargins(16, 0, 0, 0)
        opts_layout.setSpacing(2)
        self.find_reverse_complement = QCheckBox("Include reverse complement", opts)
        self.find_reverse_complement.setChecked(True)
        self.find_iupac = QCheckBox("Interpret IUPAC codes", opts)
        self.find_iupac.setChecked(True)
        self.find_allow_gaps = QCheckBox("Allow gaps in sequence", opts)
        opts_layout.addWidget(self.find_reverse_complement)
        opts_layout.addWidget(
            field_with_help(
                self.find_iupac,
                "Interpret IUPAC codes",
                _FIND_IUPAC_HELP,
                parent=opts,
            )
        )
        opts_layout.addWidget(self.find_allow_gaps)
        self.find_max_mismatches = NoWheelSpinBox(opts)
        self.find_max_mismatches.setRange(0, 20)
        self.find_max_mismatches.setValue(0)
        mm_row = QHBoxLayout()
        mm_row.setContentsMargins(0, 0, 0, 0)
        mm_row.addWidget(QLabel("Max mismatches:", opts))
        mm_row.addWidget(self.find_max_mismatches, 1)
        opts_layout.addLayout(mm_row)
        layout.addWidget(opts)

        self.find_in_names = QCheckBox("Sequence names", page)
        self.find_in_names.setChecked(True)
        self.find_in_annotations = QCheckBox("Annotation names", page)
        self.find_in_annotations.setChecked(True)
        self.find_case_sensitive = QCheckBox("Case sensitive", page)
        layout.addWidget(self.find_in_names)
        layout.addWidget(self.find_in_annotations)
        layout.addWidget(self.find_case_sensitive)

        self.find_next_btn = self._full_width_button("Find next", page)
        self.find_prev_btn = self._full_width_button("Find previous", page)
        self.find_all_btn = self._full_width_button("Find all", page)
        self.find_next_btn.clicked.connect(lambda: self.findRequested.emit(1))
        self.find_prev_btn.clicked.connect(lambda: self.findRequested.emit(-1))
        self.find_all_btn.clicked.connect(lambda: self.findRequested.emit(0))
        find_nav = QHBoxLayout()
        find_nav.setContentsMargins(0, 0, 0, 0)
        find_nav.setSpacing(6)
        find_nav.addWidget(self.find_prev_btn, 1)
        find_nav.addWidget(self.find_next_btn, 1)
        layout.addLayout(find_nav)
        layout.addWidget(self.find_all_btn)

        # Status used to show grey match text under the buttons; keep a hidden
        # label so set_find_status callers stay valid without showing it.
        self.find_status = QLabel("", page)
        self.find_status.hide()
        layout.addStretch(1)
        self.sync_find_option_enabled()
        return self._shell_with_sticky_title("Find", page)

    def find_request(self):
        """Build a FindRequest from the Find tab controls."""
        from repeatviewer.backends.find_in_file import FindRequest
        from repeatviewer.backends.motif_search import FindOptions

        iupac = self.find_iupac.isChecked()
        options = FindOptions(
            protein=self.find_protein.isChecked(),
            both_strands=self.find_reverse_complement.isChecked(),
            iupac_in_query=iupac,
            iupac_in_sequence=iupac,
            allow_gaps=self.find_allow_gaps.isChecked(),
            max_mismatches=int(self.find_max_mismatches.value()),
        )
        return FindRequest(
            query=self.find_query.text().strip(),
            options=options,
            in_sequence=self.find_in_sequence.isChecked(),
            in_names=self.find_in_names.isChecked(),
            in_annotations=self.find_in_annotations.isChecked(),
            case_sensitive=self.find_case_sensitive.isChecked(),
        )

    def set_find_status(self, text: str) -> None:
        # Find panel no longer shows status text; keep API for map-viewer calls.
        self.find_status.setText(text or "")

    def sync_find_option_enabled(self) -> None:
        on = self.find_in_sequence.isChecked()
        for widget in (
            self.find_nucleotides,
            self.find_protein,
            self.find_reverse_complement,
            self.find_iupac,
            self.find_allow_gaps,
            self.find_max_mismatches,
        ):
            widget.setEnabled(on)

    def _on_show_translation_toggled(self, checked: bool) -> None:
        self.translation_more_btn.setEnabled(checked)
        self.showTranslationChanged.emit(checked)
        self._emit_translation_frames()

    def _sync_show_annotation_track_from_kinds(self) -> None:
        """Keep hidden master toggle in sync with type checkboxes."""
        any_on = any(
            check.isChecked() for check in self.annotation_kind_checks.values()
        )
        if self.show_annotation_track.isChecked() == any_on:
            return
        self.show_annotation_track.setChecked(any_on)
        self.showAnnotationTrackChanged.emit(any_on)

    def _sync_annotation_kinds_all_check(self) -> None:
        checks = list(self.annotation_kind_checks.values())
        if not checks:
            return
        all_checked = all(check.isChecked() for check in checks)
        self._annotation_kinds_all_updating = True
        self.annotation_kinds_all_check.setChecked(all_checked)
        self._annotation_kinds_all_updating = False

    def _on_annotation_kinds_all_toggled(self, checked: bool) -> None:
        if self._annotation_kinds_all_updating:
            return
        self._annotation_kinds_all_updating = True
        try:
            for check in self.annotation_kind_checks.values():
                check.setChecked(checked)
        finally:
            self._annotation_kinds_all_updating = False
        for key, check in self.annotation_kind_checks.items():
            if check.isChecked():
                self._hidden_annotation_kinds.discard(key)
            else:
                self._hidden_annotation_kinds.add(key)
        self._save_hidden_annotation_kinds()
        self._sync_show_annotation_track_from_kinds()
        self._emit_annotation_track_kinds()

    @staticmethod
    def _normalize_hidden_annotation_kind(key: str) -> str:
        """Map legacy per-family keys (``domain::Pfam: RVT_1``) to database group."""
        text = str(key or "").strip()
        if text.startswith("domain::"):
            rest = text[len("domain::") :]
            if ": " in rest:
                db, _, _ = rest.partition(": ")
                db = db.strip()
                if db:
                    return f"domain::{db}"
        return text

    @classmethod
    def _load_hidden_annotation_kinds(cls) -> set[str]:
        settings = QSettings()
        settings.beginGroup(_SETTINGS_GROUP)
        try:
            raw = settings.value(_SETTINGS_HIDDEN_ANN_KINDS_KEY, [])
        finally:
            settings.endGroup()
        if raw is None:
            return set()
        if isinstance(raw, str):
            items = [raw] if raw.strip() else []
        else:
            try:
                items = [str(item).strip() for item in raw if str(item).strip()]
            except TypeError:
                return set()
        return {
            cls._normalize_hidden_annotation_kind(item)
            for item in items
            if item
        }

    def _save_hidden_annotation_kinds(self) -> None:
        settings = QSettings()
        settings.beginGroup(_SETTINGS_GROUP)
        try:
            settings.setValue(
                _SETTINGS_HIDDEN_ANN_KINDS_KEY,
                sorted(self._hidden_annotation_kinds),
            )
        finally:
            settings.endGroup()

    def _clear_annotation_kind_flow(self) -> None:
        flow = getattr(self, "_annotation_kinds_flow", None)
        if flow is None:
            return
        while flow.count():
            item = flow.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is None:
                continue
            widget.setParent(None)
            widget.deleteLater()

    def _rebuild_annotation_kind_checks(self, keys: list[str]) -> None:
        """Rebuild nested type checkboxes; preserve hidden-kind prefs.

        ``All`` stays on its own row above the wrapping type flow.
        """
        self._clear_annotation_kind_flow()
        self.annotation_kind_checks = {}
        self._annotation_kinds_overflow_keys = []
        host = getattr(self, "_annotation_kinds_flow_host", None)
        flow = getattr(self, "_annotation_kinds_flow", None)
        if host is None or flow is None:
            return
        hidden = getattr(self, "_hidden_annotation_kinds", set())
        self._annotation_kinds_all_updating = True
        try:
            for key in keys:
                label = annotation_visibility_label(key)
                check = QCheckBox(label, host)
                check.setMinimumWidth(0)
                check.setChecked(key not in hidden)
                if key.startswith("domain::"):
                    check.setStyleSheet(
                        f"QCheckBox {{ color: {feature_type_color('domain')}; }}"
                    )
                else:
                    check.setStyleSheet(
                        f"QCheckBox {{ color: {feature_type_color(key)}; }}"
                    )
                check.setToolTip(f"Show or hide “{label}” annotation tracks.")
                check.toggled.connect(
                    lambda checked, kind=key: self._on_annotation_kind_toggled(
                        kind, checked
                    )
                )
                flow.addWidget(check)
                self.annotation_kind_checks[key] = check
        finally:
            self._annotation_kinds_all_updating = False
        self._sync_annotation_kinds_all_check()
        self._sync_show_annotation_track_from_kinds()
        self._schedule_annotation_kinds_overflow_sync()

    def _schedule_annotation_kinds_overflow_sync(self) -> None:
        """Defer until the flow host has a real width after rebuild/resize."""
        QTimer.singleShot(0, self._sync_annotation_kinds_overflow)

    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:  # noqa: N802
        if (
            watched is getattr(self, "_annotation_kinds_flow_host", None)
            and event.type() == QEvent.Type.Resize
        ):
            self._schedule_annotation_kinds_overflow_sync()
        return super().eventFilter(watched, event)

    def _annotation_kinds_cut_index(self, width: int) -> int:
        """First type-chip index that does not fit in the max flow height."""
        max_h = _ANNOTATION_KINDS_FLOW_MAX_HEIGHT
        space = 6
        x = 0
        y = 0
        line_height = 0
        avail = max(40, int(width))
        for index, check in enumerate(self.annotation_kind_checks.values()):
            hint = check.sizeHint()
            next_x = x + hint.width() + space
            if line_height and next_x - space > avail:
                x = 0
                y += line_height + space
                next_x = x + hint.width() + space
                line_height = 0
            bottom = y + max(line_height, hint.height())
            if bottom > max_h:
                return index
            x = next_x
            line_height = max(line_height, hint.height())
        return len(self.annotation_kind_checks)

    def _sync_annotation_kinds_overflow(self) -> None:
        """Hide chips past the max height; expose them via the More menu."""
        more_btn = getattr(self, "_annotation_kinds_more_btn", None)
        host = getattr(self, "_annotation_kinds_flow_host", None)
        if more_btn is None or host is None:
            return
        keys = list(self.annotation_kind_checks.keys())
        if not keys:
            self._annotation_kinds_overflow_keys = []
            more_btn.hide()
            return
        for check in self.annotation_kind_checks.values():
            check.setVisible(True)
        width = host.width()
        if width <= 1:
            width = max(40, int(self._module_width) - 24)
        cut = self._annotation_kinds_cut_index(width)
        overflow = keys[cut:]
        self._annotation_kinds_overflow_keys = overflow
        for index, key in enumerate(keys):
            check = self.annotation_kind_checks[key]
            check.setVisible(index < cut)
        host.setMaximumHeight(_ANNOTATION_KINDS_FLOW_MAX_HEIGHT)
        if overflow:
            more_btn.setText(f"More ({len(overflow)})")
            more_btn.show()
        else:
            more_btn.hide()

    def _on_annotation_kinds_more_clicked(self) -> None:
        overflow = list(getattr(self, "_annotation_kinds_overflow_keys", []) or [])
        if not overflow:
            return
        menu = QMenu(self._annotation_kinds_more_btn)
        # Real checkboxes so several types can be ticked/unticked without closing.
        # Shift+click applies the clicked row's new state across the range from the
        # last clicked row (standard list range multi-select).
        rows: list[QCheckBox] = []
        anchor: list[int | None] = [None]

        def _bind_row_press(box: QCheckBox, index: int) -> None:
            def _press(event) -> None:  # noqa: ANN001
                if (
                    event.button() == Qt.MouseButton.LeftButton
                    and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                    and anchor[0] is not None
                ):
                    target = not box.isChecked()
                    lo, hi = sorted((anchor[0], index))
                    for i in range(lo, hi + 1):
                        rows[i].setChecked(target)
                    event.accept()
                    return
                if event.button() == Qt.MouseButton.LeftButton:
                    anchor[0] = index
                QCheckBox.mousePressEvent(box, event)

            box.mousePressEvent = _press  # type: ignore[method-assign]

        for key in overflow:
            source = self.annotation_kind_checks.get(key)
            if source is None:
                continue
            label = annotation_visibility_label(key)
            row = QCheckBox(label, menu)
            row.setChecked(source.isChecked())
            row.setStyleSheet(source.styleSheet())
            tip = source.toolTip() or f"Show or hide “{label}” annotation tracks."
            row.setToolTip(f"{tip}\nShift+click to tick or untick a range.")
            row.toggled.connect(source.setChecked)
            _bind_row_press(row, len(rows))
            rows.append(row)
            action = QWidgetAction(menu)
            action.setDefaultWidget(row)
            menu.addAction(action)
        menu.exec(
            self._annotation_kinds_more_btn.mapToGlobal(
                QPoint(0, self._annotation_kinds_more_btn.height())
            )
        )

    def _sync_displayed_annotations_section_visible(self) -> None:
        """Show Displayed annotations only when at least one type is present."""
        has_kinds = bool(self.annotation_kind_checks)
        label = getattr(self, "displayed_annotations_label", None)
        if label is not None:
            label.setVisible(has_kinds)
        kinds_host = getattr(self, "_annotation_kinds_host", None)
        if kinds_host is not None:
            kinds_host.setVisible(has_kinds)
        if not has_kinds:
            more_btn = getattr(self, "_annotation_kinds_more_btn", None)
            if more_btn is not None:
                more_btn.hide()
            self._annotation_kinds_overflow_keys = []

    def set_available_annotation_kinds(
        self,
        features: list[SequenceFeature] | None = None,
        *,
        keys: list[str] | None = None,
    ) -> None:
        """Refresh type checkboxes from types present on the current features."""
        if keys is None:
            ordered = collect_annotation_visibility_keys(features or [])
        else:
            # Keep preferred structural order when an explicit list is passed.
            present = {str(k) for k in keys if str(k or "").strip()}
            ordered = [
                key for key in ALWAYS_ANNOTATION_VISIBILITY_KINDS if key in present
            ]
            ordered.extend(
                sorted(
                    key
                    for key in present
                    if key not in ALWAYS_ANNOTATION_VISIBILITY_KINDS
                    and not key.startswith("domain::")
                )
            )
            ordered.extend(
                sorted(key for key in present if key.startswith("domain::"))
            )
        current = list(self.annotation_kind_checks.keys())
        if current == ordered:
            self._sync_displayed_annotations_section_visible()
            return
        self._rebuild_annotation_kind_checks(ordered)
        self._sync_displayed_annotations_section_visible()
        self._emit_annotation_track_kinds()

    def _on_annotation_kind_toggled(self, key: str, checked: bool) -> None:
        if self._annotation_kinds_all_updating:
            return
        if checked:
            self._hidden_annotation_kinds.discard(key)
        else:
            self._hidden_annotation_kinds.add(key)
        self._save_hidden_annotation_kinds()
        self._sync_annotation_kinds_all_check()
        self._sync_show_annotation_track_from_kinds()
        self._emit_annotation_track_kinds()

    def visible_annotation_kinds(self) -> frozenset[str]:
        """Visibility keys currently checked under Displayed annotations."""
        return frozenset(
            key
            for key, check in self.annotation_kind_checks.items()
            if check.isChecked()
        )

    def set_split_sync_available(self, available: bool) -> None:
        """Show the Split Preview link checkbox when this rail is in a split pane."""
        self._split_sync_available = bool(available)
        self._sync_split_views_visibility()

    def _sync_split_views_visibility(self) -> None:
        check = getattr(self, "sync_split_views", None)
        if check is None:
            return
        overview = bool(getattr(self, "_overview_mode", False))
        show = overview and bool(getattr(self, "_split_sync_available", False))
        check.setVisible(show)

    def apply_visible_annotation_kinds(self, keys: frozenset[str] | set[str]) -> None:
        """Set Displayed annotations checkboxes to ``keys`` (Split Preview sync)."""
        wanted = {str(k).strip() for k in keys if str(k).strip()}
        if not self.annotation_kind_checks:
            return
        changed = False
        self._annotation_kinds_all_updating = True
        try:
            for key, check in self.annotation_kind_checks.items():
                on = key in wanted
                if check.isChecked() != on:
                    check.setChecked(on)
                    changed = True
                if on:
                    self._hidden_annotation_kinds.discard(key)
                else:
                    self._hidden_annotation_kinds.add(key)
        finally:
            self._annotation_kinds_all_updating = False
        if not changed:
            return
        self._save_hidden_annotation_kinds()
        self._sync_annotation_kinds_all_check()
        self._sync_show_annotation_track_from_kinds()
        self._emit_annotation_track_kinds()

    def ensure_annotation_kinds_visible(self, keys: list[str] | tuple[str, ...] | set[str]) -> None:
        """Tick Display → Displayed annotations for ``keys``.

        Used after Feature detection / Similarity runs and after Manually add
        feature, so new types (e.g. LTR) are visible even if previously unchecked.
        """
        wanted: list[str] = []
        seen: set[str] = set()
        for raw in keys:
            key = self._normalize_hidden_annotation_kind(str(raw or "").strip())
            if not key or key in seen:
                continue
            seen.add(key)
            wanted.append(key)
        if not wanted:
            return

        changed = False
        for key in wanted:
            if key in self._hidden_annotation_kinds:
                self._hidden_annotation_kinds.discard(key)
                changed = True
        if changed:
            self._save_hidden_annotation_kinds()

        missing = [key for key in wanted if key not in self.annotation_kind_checks]
        if missing:
            ordered = list(self.annotation_kind_checks.keys()) + missing
            self._rebuild_annotation_kind_checks(ordered)
            self._sync_displayed_annotations_section_visible()
            changed = True

        self._annotation_kinds_all_updating = True
        try:
            for key in wanted:
                check = self.annotation_kind_checks.get(key)
                if check is None:
                    continue
                if not check.isChecked():
                    check.setChecked(True)
                    changed = True
        finally:
            self._annotation_kinds_all_updating = False

        if not changed:
            return
        self._sync_annotation_kinds_all_check()
        self._sync_show_annotation_track_from_kinds()
        self._emit_annotation_track_kinds()

    def _emit_annotation_track_kinds(self) -> None:
        self.annotationTrackKindsChanged.emit(self.visible_annotation_kinds())

    def _emit_translation_frames(self, *_args) -> None:
        frames = frozenset(
            frame for frame, check in self.frame_checks.items() if check.isChecked()
        )
        self.translationFramesChanged.emit(frames)

    def selected_translation_frames(self) -> frozenset[int]:
        if not self.show_translation.isChecked():
            return frozenset()
        frames = frozenset(
            frame for frame, check in self.frame_checks.items() if check.isChecked()
        )
        return frames or frozenset({1})

    def translation_three_letter(self) -> bool:
        return bool(self._translation_three_letter)

    def translation_genetic_code(self) -> int:
        return normalize_genetic_code_id(self._translation_genetic_code)

    def set_translation_options(
        self,
        *,
        frames: frozenset[int] | set[int] | None = None,
        three_letter: bool | None = None,
        genetic_code: int | None = None,
    ) -> None:
        """Update stored translation options without opening the dialog."""
        if frames is not None:
            selected = set(frames) or {1}
            for frame, check in self.frame_checks.items():
                check.blockSignals(True)
                check.setChecked(frame in selected)
                check.blockSignals(False)
        if three_letter is not None:
            self._translation_three_letter = bool(three_letter)
        if genetic_code is not None:
            self._translation_genetic_code = normalize_genetic_code_id(genetic_code)

    def _open_translation_settings(self) -> None:
        current = frozenset(
            frame for frame, check in self.frame_checks.items() if check.isChecked()
        ) or frozenset({1})
        dialog = TranslationSettingsDialog(
            self,
            frames=current,
            three_letter=self._translation_three_letter,
            genetic_code=self._translation_genetic_code,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.set_translation_options(
            frames=dialog.selected_frames(),
            three_letter=dialog.show_three_letter(),
            genetic_code=dialog.genetic_code_id(),
        )
        self._emit_translation_frames()
        self.translationOptionsChanged.emit()

    def nucleotide_color_context(self) -> str:
        return normalize_nucleotide_color_context(self._nucleotide_color_context)

    def set_nucleotide_color_context(self, context: str) -> None:
        """Use independent nucleotide colours for single / multi / MSA displays."""
        ctx = normalize_nucleotide_color_context(context)
        if ctx == self._nucleotide_color_context:
            return
        self._nucleotide_color_context = ctx
        self.sync_color_scheme_combos()

    def sync_color_scheme_combos(self) -> None:
        """Match scheme dropdowns to the currently saved residue palettes."""
        nuc_name = load_nucleotide_scheme_name(self.nucleotide_color_context())
        if nuc_name == "Custom":
            # Keep a named preset selected when possible; Custom has no combo row.
            nuc_name = "Default"
        idx = self.nucleotide_scheme.findText(nuc_name)
        self.nucleotide_scheme.blockSignals(True)
        self.nucleotide_scheme.setCurrentIndex(max(0, idx))
        self.nucleotide_scheme.blockSignals(False)

    def _on_nucleotide_scheme_changed(self, index: int) -> None:
        if index < 0 or index >= len(NUCLEOTIDE_COLOR_PRESETS):
            return
        name, _palette = NUCLEOTIDE_COLOR_PRESETS[index]
        save_nucleotide_scheme(self.nucleotide_color_context(), name)
        self.residueColorsChanged.emit()

    def _on_protein_scheme_changed(self, index: int) -> None:
        if index < 0 or index >= len(AMINO_ACID_COLOR_PRESETS):
            return
        _name, palette = AMINO_ACID_COLOR_PRESETS[index]
        save_custom_amino_acid_backgrounds(dict(palette))
        self.residueColorsChanged.emit()

    def _populate_sequence_sort_options(self, *, msa: bool) -> None:
        """Original / name for all overviews; selected columns only for MSA."""
        current = self.sequence_sort_mode()
        self.sequence_sort.blockSignals(True)
        self.sequence_sort.clear()
        self.sequence_sort.addItem("Original order", "original")
        self.sequence_sort.addItem("Sequence name", "name")
        if msa:
            self.sequence_sort.addItem("Selected column", "selected_columns")
        idx = self.sequence_sort.findData(current)
        if idx < 0 and current == "selected_columns" and not msa:
            idx = 0
        self.sequence_sort.setCurrentIndex(max(0, idx))
        self.sequence_sort.blockSignals(False)

    def sequence_sort_mode(self) -> str:
        data = self.sequence_sort.currentData()
        text = str(data or "original").strip().lower()
        if text in {"original", "name", "selected_columns"}:
            return text
        return "original"

    def set_sequence_sort_mode(self, mode: str) -> None:
        key = str(mode or "original").strip().lower()
        idx = self.sequence_sort.findData(key)
        if idx < 0:
            idx = 0
        if self.sequence_sort.currentIndex() == idx:
            return
        self.sequence_sort.blockSignals(True)
        self.sequence_sort.setCurrentIndex(idx)
        self.sequence_sort.blockSignals(False)

    def _on_sequence_sort_changed(self, _index: int = 0) -> None:
        self.sequenceSortChanged.emit(self.sequence_sort_mode())

    def _on_msa_coloring_mode_changed(self, checked: bool = True) -> None:
        if not checked:
            return
        self._sync_msa_divergence_enabled()
        self.msaColoringModeChanged.emit(self.msa_coloring_mode_id())

    def _on_msa_divergence_slider_changed(self, value: int) -> None:
        frac = max(0, min(100, int(value))) / 100.0
        self.msa_divergence_value.setText(f"{frac:.2f}")
        self.msaDivergenceChanged.emit(frac)

    def msa_coloring_mode_id(self) -> str:
        from repeatviewer.backends.msa_coordinates import (
            MSA_COLOR_ALL_BACKGROUNDS,
            normalize_msa_color_mode,
        )

        for mode_id, radio in self._msa_color_radios.items():
            if radio.isChecked():
                return normalize_msa_color_mode(mode_id)
        return MSA_COLOR_ALL_BACKGROUNDS

    def set_msa_coloring_mode(self, mode_id: str) -> None:
        from repeatviewer.backends.msa_coordinates import normalize_msa_color_mode

        mode = normalize_msa_color_mode(mode_id)
        radio = self._msa_color_radios.get(mode)
        if radio is None or radio.isChecked():
            self._sync_msa_divergence_enabled()
            return
        radio.blockSignals(True)
        radio.setChecked(True)
        radio.blockSignals(False)
        self._sync_msa_divergence_enabled()

    def msa_divergence_threshold(self) -> float:
        from repeatviewer.backends.msa_coordinates import (
            normalize_msa_divergence_threshold,
        )

        return normalize_msa_divergence_threshold(
            self.msa_divergence_slider.value() / 100.0
        )

    def set_msa_divergence_threshold(self, value: float) -> None:
        from repeatviewer.backends.msa_coordinates import (
            normalize_msa_divergence_threshold,
        )

        frac = normalize_msa_divergence_threshold(value)
        slider_val = int(round(frac * 100))
        self.msa_divergence_slider.blockSignals(True)
        self.msa_divergence_slider.setValue(slider_val)
        self.msa_divergence_slider.blockSignals(False)
        self.msa_divergence_value.setText(f"{frac:.2f}")

    def _sync_msa_divergence_enabled(self) -> None:
        from repeatviewer.backends.msa_coordinates import (
            MSA_COLOR_BG_WHEN_CONSERVED,
            MSA_COLOR_DIFF_FROM_SELECTED,
            MSA_COLOR_NO_BG_WHEN_CONSERVED,
        )

        row = getattr(self, "msa_divergence_row", None)
        if row is None:
            return
        mode = self.msa_coloring_mode_id()
        enabled = mode in (
            MSA_COLOR_BG_WHEN_CONSERVED,
            MSA_COLOR_NO_BG_WHEN_CONSERVED,
            MSA_COLOR_DIFF_FROM_SELECTED,
        )
        row.setEnabled(enabled)

    def set_sequence_kind(self, is_protein: bool) -> None:
        """Compatibility hook; size label is fixed as DNA/protein labels."""
        del is_protein

    def set_overview_display_mode(self, enabled: bool = True) -> None:
        """Adapt Display/Annotation for multi-sequence overview.

        Keeps Annotation (manual add, transfer, feature detection / similarity).
        Hides single-map-only complement/translation toggles.
        Module width matches the single-sequence Annotation rail.
        """
        overview = bool(enabled)
        self._overview_mode = overview
        for widget in (
            self.show_complement,
            self.show_translation,
            self.translation_more_btn,
            self.split_tracks_by_source,
        ):
            widget.setVisible(not overview)
        # Single-seq keeps DNA/protein labels; MSA/multi use Track height.
        self.bases_font_label.setVisible(not overview)
        self.bases_zoomed_in.setVisible(not overview)
        self.track_height_label.setVisible(overview)
        self.track_height.setVisible(overview)
        self.track_distance_label.setVisible(overview)
        self.track_distance.setVisible(overview)
        self.set_msa_display_mode(getattr(self, "_msa_display_mode", False))
        self._column_distance_label.setVisible(False)
        self.column_distance.setVisible(False)
        self._sequence_distance_label.setVisible(overview)
        self.sequence_distance.setVisible(overview)
        # Tracks + Displayed annotations: single-sequence map and overview.
        self._tracks_divider.setVisible(True)
        self._tracks_section.setVisible(True)
        self.show_annotation_track.setVisible(False)
        self._sync_displayed_annotations_section_visible()
        msa_overview = overview and bool(getattr(self, "_msa_display_mode", False))
        std_bounds = getattr(self, "show_standard_boundaries", None)
        if std_bounds is not None:
            std_bounds.setVisible(msa_overview)
        blast_cov_row = getattr(self, "show_blast_coverage_row", None)
        if blast_cov_row is not None:
            blast_cov_row.setVisible(msa_overview)
        elif getattr(self, "show_blast_coverage", None) is not None:
            self.show_blast_coverage.setVisible(msa_overview)
        self._sync_split_views_visibility()
        self.sequence_sort_row.setVisible(overview)
        if overview:
            self._populate_sequence_sort_options(
                msa=bool(getattr(self, "_msa_display_mode", False))
            )
            self.set_nucleotide_color_context(
                "msa"
                if bool(getattr(self, "_msa_display_mode", False))
                else "multi"
            )
        else:
            self.set_nucleotide_color_context("single")
        self._tab_buttons[self.TAB_ANNOTATIONS].setVisible(True)
        sections = getattr(self, "_annotation_sections", None) or {}
        for section_id in ("manual", "transfer"):
            section = sections.get(section_id)
            if section is not None:
                section.setVisible(True)
        if overview:
            self.manual_add_btn.setToolTip(
                "Add the checked feature type on the selected region for "
                "the selected sequence(s), or the rows inside a dragged "
                "selection box."
            )
            self.auto_ann_run_btn.setToolTip(
                "Run feature detection on selected sequences, "
                "or all open sequences when none are selected (Ctrl+A / Cmd+A selects all)"
            )
            self.similarity_ann_run_btn.setToolTip(
                "Run similarity annotation on selected sequences, "
                "or all open sequences when none are selected"
            )
        else:
            self.manual_add_btn.setToolTip(
                "Add the checked feature type on the current sequence selection."
            )
            self.auto_ann_run_btn.setToolTip("Run feature detection")
            self.similarity_ann_run_btn.setToolTip("Run similarity annotation")
        self._annotation_distance_label.setText("Annotation distance:")
        self.annotation_distance.setToolTip(
            "Vertical gap between annotation rows (pixels)."
        )
        for btn in (self.delete_btn, self.restore_btn, self.export_btn):
            btn.setVisible(True)
        self._module_width = _MODULE_WIDTH
        self._apply_module_geometry()
        self._sync_width_for_tab(self._active_tab)

    def set_boundary_prediction_text(self, html: str) -> None:
        """Show (or clear with "") the Boundary prediction summary."""
        self.boundary_result_label.setText(html)
        self.boundary_result_label.setVisible(bool(html))

    def set_boundary_results(self, values: dict[str, str | None]) -> None:
        """Fill the method rows; ``None`` shows "None" and disables the tick."""
        for key, (check, label) in self.boundary_row_widgets.items():
            text = values.get(key)
            label.setText(text if text else "None")
            # A row with a boundary starts ticked; "None" stays unticked.
            check.blockSignals(True)
            check.setChecked(bool(text))
            check.blockSignals(False)
            check.setEnabled(bool(text))
            label.setEnabled(bool(text))

    def clear_boundary_results(self) -> None:
        self.set_boundary_results({})
        self.set_boundary_prediction_text("")

    def boundary_guide_keys(self) -> frozenset[str]:
        """Ticked rows that have a boundary."""
        return frozenset(
            key
            for key, (check, _label) in self.boundary_row_widgets.items()
            if check.isChecked() and check.isEnabled()
        )

    def _emit_boundary_guides_changed(self, _checked: bool = False) -> None:
        self.boundaryGuidesChanged.emit(self.boundary_guide_keys())

    def _sync_feature_detect_tsd_visible(self) -> None:
        """Show Feature detection → TSD only for MSA files."""
        check = (getattr(self, "auto_ann_checks", None) or {}).get("TSD")
        if check is None:
            return
        show = bool(getattr(self, "_msa_display_mode", False))
        check.setVisible(show)
        if not show and check.isChecked():
            check.setChecked(False)
        # Relayout the chip row so PBS stays left-aligned when TSD is hidden.
        host = check.parentWidget()
        if host is not None and host.layout() is not None:
            host.layout().invalidate()
            host.updateGeometry()

    def set_msa_display_mode(self, enabled: bool) -> None:
        """Toggle controls that apply only to aligned residue columns."""
        self._msa_display_mode = bool(enabled)
        visible = bool(getattr(self, "_overview_mode", False)) and self._msa_display_mode
        self._sync_feature_detect_tsd_visible()
        self.msa_coloring_label.setVisible(visible)
        self.msa_coloring_header.setVisible(visible)
        self.msa_coloring_mode_host.setVisible(visible)
        self.msa_divergence_row.setVisible(visible)
        self.boundary_section.setVisible(visible)
        self._boundary_divider.setVisible(visible)
        self._column_distance_label.setVisible(False)
        self.column_distance.setVisible(False)
        self.color_multi_sequence_background.setVisible(
            bool(getattr(self, "_overview_mode", False)) and not self._msa_display_mode
        )
        if bool(getattr(self, "_overview_mode", False)):
            self.sequence_sort_row.setVisible(True)
            std_bounds = getattr(self, "show_standard_boundaries", None)
            if std_bounds is not None:
                std_bounds.setVisible(self._msa_display_mode)
            blast_cov_row = getattr(self, "show_blast_coverage_row", None)
            if blast_cov_row is not None:
                blast_cov_row.setVisible(self._msa_display_mode)
            elif getattr(self, "show_blast_coverage", None) is not None:
                self.show_blast_coverage.setVisible(self._msa_display_mode)
            self._sync_split_views_visibility()
            self.set_nucleotide_color_context(
                "msa" if self._msa_display_mode else "multi"
            )
            self._populate_sequence_sort_options(msa=self._msa_display_mode)
        if visible:
            self._sync_msa_divergence_enabled()
            self.delete_btn.setToolTip(
                "Delete: remove selected residues/columns, or selected "
                "sequence(s). Shift+Delete: fill selection / selected "
                "sequence(s) with gaps. Type a letter (A/C/G/T/…) or '-' "
                "to replace the selection. Or delete a selected feature "
                "(Esc clears the band first)."
            )
            self.restore_btn.setToolTip(
                "Undo the last Delete or typed edit (Ctrl+Z). "
                "Restores MSA and features."
            )
        else:
            self.delete_btn.setToolTip("Delete the selected feature.")
            self.restore_btn.setToolTip("Undo the last feature Delete.")

    def is_panel_collapsed(self) -> bool:
        return bool(self._panel_collapsed)

    def set_panel_collapsed(self, collapsed: bool, *, persist: bool = True) -> None:
        """Hide or show the control pages; tab strip always stays visible."""
        collapsed = bool(collapsed)
        if collapsed == self._panel_collapsed:
            if collapsed:
                self._sync_tab_checked_state(None)
            return
        self._panel_collapsed = collapsed
        self._stack.setVisible(not collapsed)
        self._divider.setVisible(not collapsed)
        if collapsed:
            self.setFixedWidth(_COLLAPSED_RAIL_WIDTH)
            self._sync_tab_checked_state(None)
        else:
            self.setFixedWidth(self._expanded_rail_width())
            self._stack.setCurrentIndex(self._active_tab)
            self._sync_tab_checked_state(self._active_tab)
        self.panelCollapsedChanged.emit(collapsed)
        if persist:
            self._save_rail_ui_state()

    def _sync_tab_checked_state(self, active: int | None) -> None:
        self._updating_tabs = True
        try:
            for i, btn in enumerate(self._tab_buttons):
                btn.setChecked(active is not None and i == active)
                btn.update()
        finally:
            self._updating_tabs = False

    def _on_tab_clicked(self, index: int) -> None:
        if self._updating_tabs:
            return
        index = max(0, min(index, self._stack.count() - 1))
        # Re-click active tab → collapse; click while collapsed or another tab → show.
        if not self._panel_collapsed and index == self._active_tab:
            self.set_panel_collapsed(True)
            return
        self._active_tab = index
        was_collapsed = self._panel_collapsed
        if was_collapsed:
            self._panel_collapsed = False
            self._stack.setVisible(True)
            self._divider.setVisible(True)
            self.setFixedWidth(self._expanded_rail_width())
        self._stack.setCurrentIndex(index)
        self._sync_width_for_tab(index)
        self._sync_tab_checked_state(index)
        if was_collapsed:
            self.panelCollapsedChanged.emit(False)
        self.tabChanged.emit(index)
        self._save_rail_ui_state()

    def set_annotation_editing_enabled(self, enabled: bool) -> None:
        """Grey out the Annotation page (temporary multi-file preview)."""
        self._annotations_page.setEnabled(bool(enabled))
        if len(self._tab_buttons) > 1:
            self._tab_buttons[1].setToolTip(
                self._tab_tips[1]
                if enabled
                else "Annotation editing is off in a temporary preview of several files"
            )

    def set_current_tab(self, index: int) -> None:
        index = max(0, min(index, self._stack.count() - 1))
        self._active_tab = index
        if self._panel_collapsed:
            self.set_panel_collapsed(False)
        else:
            self._stack.setCurrentIndex(index)
            self._sync_tab_checked_state(index)
            self._save_rail_ui_state()
        self._sync_width_for_tab(index)

    def _sync_width_for_tab(self, index: int) -> None:
        """Primers (the workbench) is 330 px wide, the other tabs 260 px."""
        want = _PRIMERS_MODULE_WIDTH if index == PRIMERS_TAB_INDEX else _MODULE_WIDTH
        if int(self._module_width) != want:
            self._module_width = want
            self._apply_module_geometry()

    def _settings(self) -> QSettings:
        settings = QSettings()
        settings.beginGroup(_SETTINGS_GROUP)
        return settings

    def _restore_rail_ui_state(self) -> None:
        """Default: Annotation tab, all sections collapsed; restore last state."""
        settings = self._settings()
        try:
            raw_tab = settings.value(_SETTINGS_TAB_KEY, _DEFAULT_TAB_INDEX)
            try:
                tab = int(raw_tab)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                tab = _DEFAULT_TAB_INDEX
            tab = max(0, min(tab, self._stack.count() - 1))
            if tab == PRIMERS_TAB_INDEX:
                # Primers and Probes opens from its menu only, never by itself.
                tab = _DEFAULT_TAB_INDEX
            self._active_tab = tab
            self._stack.setCurrentIndex(tab)
            self._sync_width_for_tab(tab)

            collapsed_raw = settings.value(_SETTINGS_COLLAPSED_KEY, False)
            if isinstance(collapsed_raw, str):
                collapsed = collapsed_raw.strip().lower() in {"1", "true", "yes"}
            else:
                collapsed = bool(collapsed_raw)
            self._panel_collapsed = False  # force apply below
            self.set_panel_collapsed(collapsed, persist=False)
            if not collapsed:
                self._sync_tab_checked_state(tab)

            sections = getattr(self, "_annotation_sections", None) or {}
            saved = settings.value(_SETTINGS_SECTIONS_KEY, [])
            if isinstance(saved, str):
                expanded_ids = {saved} if saved else set()
            elif isinstance(saved, (list, tuple)):
                expanded_ids = {str(item) for item in saved}
            else:
                expanded_ids = set()
            for section_id, section in sections.items():
                section.set_expanded(
                    section_id in expanded_ids, notify=False
                )
        finally:
            settings.endGroup()

    def _save_rail_ui_state(self, *_args) -> None:
        settings = self._settings()
        try:
            if self._active_tab != PRIMERS_TAB_INDEX:
                # The Primers page is not remembered: the next file opens on the
                # tab that was in use before the menu brought Primers up.
                settings.setValue(_SETTINGS_TAB_KEY, int(self._active_tab))
            settings.setValue(_SETTINGS_COLLAPSED_KEY, bool(self._panel_collapsed))
            sections = getattr(self, "_annotation_sections", None) or {}
            expanded = [
                section_id
                for section_id, section in sections.items()
                if section.is_expanded()
            ]
            settings.setValue(_SETTINGS_SECTIONS_KEY, expanded)
        finally:
            settings.endGroup()

    def _transfer_threshold_slider_row(
        self, parent: QWidget
    ) -> tuple[NoWheelSlider, QLabel]:
        slider = NoWheelSlider(Qt.Orientation.Horizontal, parent)
        slider.setObjectName("annotationZoomSlider")
        slider.setRange(0, 100)
        slider.setValue(50)
        slider.setMinimumWidth(80)
        slider.setFixedHeight(18)
        slider.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        apply_annotation_zoom_slider_style(slider)
        value_label = QLabel("0.50", parent)
        value_label.setMinimumWidth(36)
        value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        def _sync(value: int) -> None:
            frac = max(0, min(100, int(value))) / 100.0
            value_label.setText(f"{frac:.2f}")
            self.transferThresholdChanged.emit()

        slider.valueChanged.connect(_sync)
        return slider, value_label

    @staticmethod
    def _threshold_slider_field(
        slider: NoWheelSlider,
        value_label: QLabel,
        *,
        label: str = "",
    ) -> QWidget:
        row = QWidget(slider.parentWidget())
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        if label:
            name = QLabel(label, row)
            # Fixed column + right align so "Identity"/"Coverage" share an end
            # edge and both slider tracks stay the same length.
            fm = QFontMetrics(name.font())
            name.setFixedWidth(fm.horizontalAdvance("Coverage") + 2)
            name.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            name.setToolTip(f"Minimum {label.lower()} threshold")
            layout.addWidget(name, 0)
        layout.addWidget(slider, 1)
        layout.addWidget(value_label, 0)
        return row

    def transfer_min_identity_value(self) -> float:
        return float(self.transfer_min_identity_slider.value()) / 100.0

    def transfer_min_coverage_value(self) -> float:
        return float(self.transfer_min_coverage_slider.value()) / 100.0

    def refresh_transfer_run_tooltip(self) -> None:
        """Refresh Run tooltip from the saved Transfer strategy setting."""
        self.transfer_run_btn.setToolTip(self._transfer_run_tooltip())

    def _transfer_run_tooltip(self) -> str:
        from repeatviewer.backends.annotation_transfer import (
            TRANSFER_STRATEGY_BLASTN,
            load_transfer_strategy,
            mafft_liftover_max_kb,
            transfer_strategy_label,
        )

        strategy = load_transfer_strategy()
        label = transfer_strategy_label(strategy)
        if strategy == TRANSFER_STRATEGY_BLASTN:
            detail = (
                "Combine all feature DNAs into one query FASTA and blastn "
                "against the target (no whole-seq lift)."
            )
        else:
            detail = (
                "Whole-seq lift first "
                f"(MAFFT fast if <{mafft_liftover_max_kb()} kb, else minimap2), "
                "then blastn for leftovers."
            )
        return (
            f"Target similar to source: {label}. {detail} "
            "Matches become source “Transfer (…)”."
        )

    def populate_manual_feature_types(
        self, buttons: list[tuple[str, str]] | None = None
    ) -> None:
        """Fill the Manually add feature type list (label, feature_type)."""
        entries = list(buttons) if buttons is not None else load_add_feature_buttons()
        previous = str(self.manual_feature_combo.currentData() or "").strip()
        if not previous:
            _label, previous = self.selected_manual_feature()
            if previous == "others" and not self.manual_feature_checks:
                previous = ""

        self.manual_feature_combo.blockSignals(True)
        try:
            self.manual_feature_combo.clear()
            for label, feature_type in entries:
                self.manual_feature_combo.addItem(str(label), str(feature_type))
            if previous:
                idx = self.manual_feature_combo.findData(previous)
                if idx >= 0:
                    self.manual_feature_combo.setCurrentIndex(idx)
        finally:
            self.manual_feature_combo.blockSignals(False)

        while self.manual_feature_flow.count():
            item = self.manual_feature_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.manual_feature_checks.clear()
        self._manual_feature_exclusive = True
        restore_type = previous or (
            str(entries[0][1]) if entries else "others"
        )
        for label, feature_type in entries:
            check = QCheckBox(str(label), self.manual_feature_host)
            check.setProperty("feature_type", str(feature_type))
            check.setChecked(str(feature_type) == restore_type)
            check.setMinimumWidth(0)
            check.toggled.connect(self._on_manual_feature_check_toggled)
            self.manual_feature_flow.addWidget(check)
            self.manual_feature_checks[str(feature_type)] = check
        self.refresh_manual_feature_check_colors()
        self.manual_feature_host.updateGeometry()

    def _on_manual_feature_check_toggled(self, checked: bool) -> None:
        if not self._manual_feature_exclusive:
            return
        sender = self.sender()
        if not isinstance(sender, QCheckBox):
            return
        if checked:
            for check in self.manual_feature_checks.values():
                if check is not sender and check.isChecked():
                    check.blockSignals(True)
                    check.setChecked(False)
                    check.blockSignals(False)
            return
        if any(c.isChecked() for c in self.manual_feature_checks.values()):
            return
        sender.blockSignals(True)
        sender.setChecked(True)
        sender.blockSignals(False)

    def selected_manual_feature(self) -> tuple[str, str]:
        """Return ``(label, feature_type)`` for the checked manual feature type."""
        for check in self.manual_feature_checks.values():
            if check.isChecked():
                feature_type = str(check.property("feature_type") or "").strip()
                label = str(check.text() or "").strip() or feature_type
                if feature_type:
                    return label, feature_type
        combo = self.manual_feature_combo
        if combo.count() > 0:
            label = str(combo.currentText() or "").strip() or "Others"
            feature_type = str(combo.currentData() or "").strip() or "others"
            return label, feature_type
        return ("Others", "others")

    def set_status(self, text: str) -> None:
        self.status_label.setText(text or "")

    def set_annotation_job_status(self, text: str) -> None:
        """Accept job progress text without showing it in the Annotation rail."""
        self.annotation_job_status.setText(str(text or "").strip())
        self.annotation_job_status.hide()

    def set_transfer_summary(self, text: str) -> None:
        """Transfer progress is shown on the map preview, not in the rail."""
        del text

    def set_sequence_name_font_point_size(self, point_size: int) -> None:
        font = self.sequence_combo.font()
        font.setPointSize(max(8, min(24, int(point_size))))
        self.sequence_combo.setFont(font)
        self.sequence_search.setFont(font)

    def browse_target_fasta(self, parent: QWidget | None = None) -> Path | None:
        path, _ = QFileDialog.getOpenFileName(
            parent or self,
            "Choose target FASTA",
            "",
            "FASTA (*.fa *.fasta *.fna *.fas);;All files (*)",
        )
        if not path:
            return None
        return Path(path)

    def clear_similarity_db_checks(self) -> None:
        host = self.similarity_db_host
        if isinstance(host, SimilarityDatabaseGrid):
            host.clear_widgets()
            return
        layout = getattr(self, "similarity_db_layout", None)
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def add_similarity_db_widget(self, widget: QWidget) -> None:
        host = self.similarity_db_host
        if isinstance(host, SimilarityDatabaseGrid):
            host.add_widget(widget)
            return
        widget.setParent(host)
        self.similarity_db_layout.addWidget(widget)

    def add_similarity_db_check(self, check: QCheckBox) -> None:
        self.add_similarity_db_widget(check)

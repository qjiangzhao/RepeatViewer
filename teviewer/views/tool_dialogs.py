"""Dialogs for tool-specific parameters (right-click / custom runs)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QTextEdit,
)


def exec_modal_dialog(dialog: QDialog) -> bool:
    """Show a modal dialog above the main window (avoids WebEngine / dock click stealing)."""
    dialog.setModal(True)
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.adjustSize()
    dialog.raise_()
    dialog.activateWindow()
    return dialog.exec() == QDialog.DialogCode.Accepted


def _prepare_option_dialog(dialog: QDialog) -> None:
    dialog.setModal(True)
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    flags = dialog.windowFlags()
    dialog.setWindowFlags(
        flags
        | Qt.WindowType.Dialog
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
    )


def _run_cancel_button_box(parent: QWidget) -> QDialogButtonBox:
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        parent=parent,
    )
    ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
    if ok is not None:
        ok.setText("Run")
    return buttons


from teviewer.backends.blast_genome_plot import format_genome_length_bp
from teviewer.job_options import (
    TE_GENOME_MAP_COLOR_FAMILY,
    TE_GENOME_MAP_COLOR_IDENTITY,
    TE_GENOME_MAP_COLOR_SUPERFAMILY,
    TE_GENOME_MAP_DENSITY_HIT_COUNT,
    TE_GENOME_MAP_DENSITY_TE_LENGTH,
    DEFAULT_ANNOTATION_DENSITY,
    DEFAULT_ANNOTATION_FEATURE_TYPES,
    CHROMOSOME_SORT_NATURAL,
    CHROMOSOME_SORT_SIZE_ASC,
    CHROMOSOME_SORT_SIZE_DESC,
    TeGenomeMapOptions,
    TeDivergencePlotOptions,
    TeConfusionMatrixBenchmarkOptions,
    TeLibraryBenchmarkOptions,
    DEFAULT_TE_BENCHMARK_THREADS,
    DEFAULT_TE_DIVERGENCE_BIN_WIDTH,
    DEFAULT_BLAST_EVALUE,
    DEFAULT_BLAST_MAX_MSA_LINES,
    DEFAULT_BLAST_MINIMUM_BIT_SCORE,
    DEFAULT_BLAST_THREADS,
    DEFAULT_BLAST_TOP_MSA_LINES,
    DEFAULT_BLAST_WRITE_GFF,
    DEFAULT_CONSENSUS_AMBIGUOUS,
    DEFAULT_CONSENSUS_THRESHOLD,
    DEFAULT_EXTEND_LEFT,
    DEFAULT_EXTEND_RIGHT,
    DEFAULT_FLEXIDOT_LCS_SHADING,
    DEFAULT_FLEXIDOT_WORDSIZE,
    DEFAULT_DIV_THRESHOLD,
    DEFAULT_DIV_WINDOW_SIZE,
    DEFAULT_GAP_COL_GAP_THRESHOLD,
    DEFAULT_BLAST_EVALUE,
    DEFAULT_GAP_COL_MIN_NUCLEOTIDE,
    DEFAULT_GAP_COL_SIMI_GAP_THR,
    DEFAULT_GAP_COL_SIMILARITY_THR,
    DEFAULT_GAP_ROW_GAP_THRESHOLD,
    DEFAULT_GAP_ROW_WINDOW_SIZE,
    DEFAULT_TEAID_EVALUE,
    DEFAULT_TEAID_SELF_BLAST_WORD_SIZE,
    MAX_TEAID_SELF_BLAST_WORD_SIZE,
    MIN_TEAID_SELF_BLAST_WORD_SIZE,
    BlastOptions,
    ConsensusOptions,
    configure_report_evalue_spinbox,
    DivergenceRowOptions,
    AlignOptions,
    ALIGN_BACKEND_AUTO,
    ALIGN_BACKEND_CLUSTALO,
    ALIGN_BACKEND_MAFFT,
    ExtendOptions,
    FlexidotOptions,
    MAX_FLEXIDOT_WORDSIZE,
    MIN_FLEXIDOT_WORDSIZE,
    GapRowOptions,
    GappyColumnOptions,
    MSA_CLEAN_METHOD_CHOICES,
    MsaCleanOptions,
    TeaAidOptions,
    TsdSearchOptions,
    msa_clean_method_description,
    normalize_blast_evalue,
)
from teviewer.plugins.custom_command import (
    CommandVarDef,
    UserCommandPluginSpec,
    get_user_command_plugin_spec,
    load_user_command_plugin_specs,
    normalize_var_mode,
    plugin_id_from_label,
    template_variables,
    user_command_plugin_ids,
)


class _CommandVarRow(QWidget):
    remove_requested = Signal(object)
    output_toggled = Signal(object, bool)

    def __init__(self, initial: CommandVarDef | None = None, *, is_output: bool = False, parent=None) -> None:
        super().__init__(parent)
        var = initial or CommandVarDef(name="", mode="file", value="")
        self._name = QLineEdit(var.name, self)
        self._name.setPlaceholderText("variable_name")
        self._mode = QComboBox(self)
        self._mode.addItem("File", "file")
        self._mode.addItem("Folder", "folder")
        self._mode.addItem("Text", "text")
        self._mode.addItem("Number", "number")
        self._mode.setMinimumWidth(76)
        mode_key = normalize_var_mode(var.mode)
        index = self._mode.findData(mode_key)
        if index >= 0:
            self._mode.setCurrentIndex(index)
        self._default = QLineEdit(var.value, self)
        self._default.setPlaceholderText("Default value (optional)")
        self._is_output = QCheckBox("Output", self)
        self._is_output.setChecked(is_output)
        self._is_output.setMinimumWidth(self._is_output.fontMetrics().horizontalAdvance("Output") + 28)
        self._is_output.toggled.connect(self._on_output_toggled)
        self._is_output.toggled.connect(self._refresh_output_fields)
        remove_btn = QPushButton("Remove", self)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        self._remove_btn = remove_btn
        remove_btn.setMinimumWidth(72)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self._name, 1)
        row.addWidget(self._mode, 0)
        row.addWidget(self._default, 1)
        row.addWidget(self._is_output, 0)
        row.addWidget(remove_btn, 0)
        self._refresh_output_fields()

    def _on_output_toggled(self, checked: bool) -> None:
        if checked:
            self.output_toggled.emit(self, True)

    def set_output_checked(self, checked: bool) -> None:
        self._is_output.blockSignals(True)
        self._is_output.setChecked(checked)
        self._is_output.blockSignals(False)
        self._refresh_output_fields()

    def _refresh_output_fields(self) -> None:
        is_output = self._is_output.isChecked()
        if is_output:
            mode = normalize_var_mode(str(self._mode.currentData()))
            if mode not in {"file", "folder"}:
                index = self._mode.findData("file")
                if index >= 0:
                    self._mode.setCurrentIndex(index)

    def definition(self) -> tuple[CommandVarDef | None, bool]:
        name = self._name.text().strip()
        if not name:
            return None, False
        is_output = self._is_output.isChecked()
        var = CommandVarDef(
            name=name,
            mode=str(self._mode.currentData()),
            value=self._default.text().strip(),
        )
        return var, is_output

    def mark_removable(self, removable: bool) -> None:
        self._remove_btn.setVisible(removable)


class CommandPluginDesignerDialog(QDialog):
    """Design a user-defined command plugin from a command template."""

    def __init__(
        self,
        *,
        initial: UserCommandPluginSpec | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Design your plugin")
        self.setMinimumWidth(760)
        spec = initial or UserCommandPluginSpec(
            id="",
            label="",
            command_template="",
            output_vars=[],
            var_defs=[],
            fasta_only=True,
        )
        self._initial_fasta_only = spec.fasta_only
        self._initial_id = spec.id
        self._rebuilding_rows = False
        self._label = QLineEdit(spec.label, self)
        self._label.setPlaceholderText("Plugin name (must be unique)")
        self._tooltip = QTextEdit(self)
        self._tooltip.setPlaceholderText("Short description (optional)")
        self._tooltip.setPlainText(spec.tooltip)
        self._tooltip.setFixedHeight(52)
        self._tooltip.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._command = QTextEdit(self)
        self._command.setFixedHeight(120)
        self._command.setPlaceholderText(
            "Example:\nFastGA ${genome1} ${genome2} -1:${output}"
        )
        self._command.setPlainText(spec.command_template)
        self._rows_host = QWidget(self)
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        self._rows: list[_CommandVarRow] = []
        out_set = set(spec.output_vars)
        for var in spec.var_defs:
            self._add_var_row(var, is_output=var.name in out_set)
        if not self._rows:
            self._add_var_row()

        detect_btn = QPushButton("Detect variables from command", self)
        detect_btn.clicked.connect(self._detect_variables)
        add_var_btn = QPushButton("Add variable", self)
        add_var_btn.clicked.connect(lambda: self._add_var_row())

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.addRow("Plugin name:", self._label)
        form.addRow("Description:", self._tooltip)
        form.addRow("Command template:", self._command)
        btn_row = QWidget(self)
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addWidget(detect_btn)
        btn_layout.addStretch(1)
        form.addRow("", btn_row)
        form.addRow("Define variables:", self._rows_host)
        add_row = QWidget(self)
        add_layout = QHBoxLayout(add_row)
        add_layout.setContentsMargins(0, 0, 0, 0)
        add_layout.addWidget(add_var_btn)
        add_layout.addStretch(1)
        form.addRow("", add_row)

        hint = QLabel(
            "Use ${variable_name} in the command. Define each variable below. "
            "Mark one output as File or Folder. One command per line."
        )
        hint.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._label.setFocus)

    def _add_var_row(self, var: CommandVarDef | None = None, *, is_output: bool = False) -> None:
        if not hasattr(self, "_rows_host"):
            return
        row = _CommandVarRow(var, is_output=is_output, parent=self._rows_host)
        row.remove_requested.connect(self._remove_var_row)
        row.output_toggled.connect(self._on_output_toggled)
        self._rows.append(row)
        self._rows_layout.addWidget(row)
        self._refresh_remove_buttons()

    def _remove_var_row(self, row: _CommandVarRow) -> None:
        if row not in self._rows:
            return
        if len(self._rows) <= 1:
            row._name.clear()
            row._default.clear()
            row._is_output.setChecked(False)
            row._mode.setCurrentIndex(row._mode.findData("file"))
            row._refresh_output_fields()
            return
        self._rows.remove(row)
        self._rows_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._refresh_remove_buttons()

    def _refresh_remove_buttons(self) -> None:
        removable = len(self._rows) > 1
        for row in self._rows:
            row.mark_removable(removable)

    def _on_output_toggled(self, source_row: _CommandVarRow, checked: bool) -> None:
        if not checked:
            return
        for row in self._rows:
            if row is not source_row:
                row.set_output_checked(False)

    def _detect_variables(self) -> None:
        current_defs = {}
        outputs = set()
        for row in self._rows:
            var, is_output = row.definition()
            if var is None:
                continue
            current_defs[var.name] = var
            if is_output:
                outputs.add(var.name)
        vars_in_cmd = template_variables(self._command.toPlainText())
        for name in vars_in_cmd:
            if name not in current_defs:
                current_defs[name] = CommandVarDef(name=name, mode="file", value="")
        self._rebuilding_rows = True
        try:
            for row in list(self._rows):
                self._rows_layout.removeWidget(row)
                row.setParent(None)
                row.deleteLater()
            self._rows = []
            for name in sorted(current_defs):
                self._add_var_row(current_defs[name], is_output=name in outputs)
        finally:
            self._rebuilding_rows = False
        if not self._rows:
            self._add_var_row()

    def spec(self) -> UserCommandPluginSpec:
        outputs: list[str] = []
        var_defs: list[CommandVarDef] = []
        for row in self._rows:
            var, is_output = row.definition()
            if var is None:
                continue
            var_defs.append(var)
            if is_output:
                outputs.append(var.name)
        return UserCommandPluginSpec(
            id=plugin_id_from_label(self._label.text().strip()),
            label=self._label.text().strip(),
            command_template=self._command.toPlainText().strip(),
            output_vars=outputs[:1],
            var_defs=var_defs,
            fasta_only=self._initial_fasta_only,
            tooltip=self._tooltip.toPlainText().strip(),
        )

    def accept(self) -> None:
        spec = self.spec()
        if not spec.label:
            QMessageBox.warning(self, "Design your plugin", "Plugin name is required.")
            return
        label_key = spec.label.strip().lower()
        for existing in load_user_command_plugin_specs():
            if existing.id == self._initial_id:
                continue
            if existing.label.strip().lower() == label_key:
                QMessageBox.warning(
                    self,
                    "Design your plugin",
                    f"A plugin named “{spec.label}” already exists. Choose a different name.",
                )
                return
        if not spec.command_template:
            QMessageBox.warning(self, "Design your plugin", "Command template is required.")
            return
        output_count = 0
        for row in self._rows:
            var, is_output = row.definition()
            if var is None:
                continue
            if is_output:
                output_count += 1
                if normalize_var_mode(var.mode) not in {"file", "folder"}:
                    QMessageBox.warning(
                        self,
                        "Design your plugin",
                        f"Output variable “{var.name}” must use type File or Folder.",
                    )
                    return
        if output_count > 1:
            QMessageBox.warning(
                self,
                "Design your plugin",
                "Only one variable can be marked as Output.",
            )
            return
        super().accept()


class PluginManageDialog(QDialog):
    """List installed plugins; add, edit, or delete user-designed command plugins."""

    def __init__(
        self,
        plugin_registry,
        *,
        on_save,
        on_delete,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage plugins")
        self.setMinimumWidth(720)
        self.setMinimumHeight(420)
        self._registry = plugin_registry
        self._on_save = on_save
        self._on_delete = on_delete

        hint = QLabel(
            "Custom plugins can be edited or removed. Installed plugins (from pip packages) "
            "are listed for reference and cannot be changed here."
        )
        hint.setWordWrap(True)

        self._list = QListWidget(self)
        self._list.currentItemChanged.connect(self._update_buttons)

        self._add_btn = QPushButton("Add…", self)
        self._edit_btn = QPushButton("Edit…", self)
        self._delete_btn = QPushButton("Delete…", self)
        self._add_btn.clicked.connect(self._add_plugin)
        self._edit_btn.clicked.connect(self._edit_plugin)
        self._delete_btn.clicked.connect(self._delete_plugin)
        self._list.itemDoubleClicked.connect(lambda _item: self._edit_plugin())

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._edit_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self._list, 1)
        layout.addLayout(btn_row)
        layout.addWidget(buttons)

        self._populate()
        self._update_buttons()

    def _populate(self) -> None:
        self._list.clear()
        custom_ids = user_command_plugin_ids()
        plugins = self._registry.all_plugins()
        if not plugins:
            item = QListWidgetItem("(No plugins loaded)")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(item)
            return
        for plugin in plugins:
            kind = "Custom" if plugin.id in custom_ids else "Installed"
            tooltip = (plugin.tooltip or "").strip()
            text = f"{plugin.label} — {kind}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, plugin.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, plugin.id in custom_ids)
            if tooltip:
                item.setToolTip(tooltip)
            self._list.addItem(item)

    def _selected(self) -> tuple[str, bool] | None:
        item = self._list.currentItem()
        if item is None:
            return None
        plugin_id = item.data(Qt.ItemDataRole.UserRole)
        is_custom = bool(item.data(Qt.ItemDataRole.UserRole + 1))
        if not plugin_id:
            return None
        return str(plugin_id), is_custom

    def _update_buttons(self) -> None:
        selected = self._selected()
        has_custom = selected is not None and selected[1]
        self._edit_btn.setEnabled(has_custom)
        self._delete_btn.setEnabled(has_custom)

    def _add_plugin(self) -> None:
        dialog = CommandPluginDesignerDialog(parent=self)
        if not exec_modal_dialog(dialog):
            return
        self._on_save(dialog.spec())
        self._populate()

    def _edit_plugin(self) -> None:
        selected = self._selected()
        if selected is None or not selected[1]:
            return
        plugin_id = selected[0]
        spec = get_user_command_plugin_spec(plugin_id)
        if spec is None:
            QMessageBox.warning(self, "Manage plugins", f"Could not load plugin {plugin_id!r}.")
            return
        dialog = CommandPluginDesignerDialog(initial=spec, parent=self)
        if not exec_modal_dialog(dialog):
            return
        self._on_save(dialog.spec(), previous_id=plugin_id)
        self._populate()

    def _delete_plugin(self) -> None:
        selected = self._selected()
        if selected is None or not selected[1]:
            return
        plugin_id = selected[0]
        spec = get_user_command_plugin_spec(plugin_id)
        label = spec.label if spec is not None else plugin_id
        answer = QMessageBox.question(
            self,
            "Manage plugins",
            f"Delete custom plugin “{label}” ({plugin_id})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self._on_delete(plugin_id):
            QMessageBox.warning(self, "Manage plugins", f"Could not delete plugin {plugin_id!r}.")
            return
        self._populate()
        self._update_buttons()


class AlignParamsDialog(QDialog):
    def __init__(
        self,
        *,
        initial: AlignOptions | None = None,
        title: str = "Alignment parameters",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        opts = initial or AlignOptions()

        self._backend = QComboBox(self)
        self._backend.addItem("Auto (MAFFT → Clustal)", ALIGN_BACKEND_AUTO)
        self._backend.addItem("MAFFT", ALIGN_BACKEND_MAFFT)
        self._backend.addItem("Clustal Omega", ALIGN_BACKEND_CLUSTALO)
        idx = self._backend.findData(opts.backend)
        if idx >= 0:
            self._backend.setCurrentIndex(idx)

        self._threads = QSpinBox(self)
        self._threads.setRange(1, 64)
        self._threads.setValue(max(1, opts.num_threads))

        form = QFormLayout()
        form.addRow("Aligner:", self._backend)
        form.addRow("Threads:", self._threads)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def options(self) -> AlignOptions:
        backend = str(self._backend.currentData())
        return AlignOptions(
            backend=backend,
            num_threads=max(1, int(self._threads.value())),
        )


class ExtendParamsDialog(QDialog):
    def __init__(
        self,
        *,
        initial: ExtendOptions | None = None,
        title: str = "Extend default distances",
        pan_genome_names: list[str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        opts = initial or ExtendOptions()
        self._left = QSpinBox()
        self._left.setRange(0, 500_000)
        self._left.setValue(opts.left)
        self._left.setSuffix(" bp")
        self._right = QSpinBox()
        self._right.setRange(0, 500_000)
        self._right.setValue(opts.right)
        self._right.setSuffix(" bp")

        self._pan_genome = QComboBox()
        self._pan_genome_names = list(pan_genome_names or [])
        if self._pan_genome_names:
            self._pan_genome.addItems(self._pan_genome_names)
            selected = opts.pan_genome_name or self._pan_genome_names[0]
            index = self._pan_genome.findText(selected)
            if index >= 0:
                self._pan_genome.setCurrentIndex(index)

        form = QFormLayout()
        if self._pan_genome_names:
            form.addRow("Pan-genome:", self._pan_genome)
        form.addRow("Extend left of MSA:", self._left)
        form.addRow("Extend right of MSA:", self._right)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def options(self) -> ExtendOptions:
        pan_name = None
        if self._pan_genome_names:
            pan_name = self._pan_genome.currentText().strip() or None
        return ExtendOptions(
            left=self._left.value(),
            right=self._right.value(),
            pan_genome_name=pan_name,
        )


class TsdSearchParamsDialog(QDialog):
    def __init__(
        self,
        *,
        initial: TsdSearchOptions | None = None,
        title: str = "TSD search parameters",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        opts = initial or TsdSearchOptions()

        self._left = QSpinBox()
        self._left.setRange(0, 10_000_000)
        self._left.setValue(opts.left_boundary)
        self._left.setToolTip("MSA column index for the left TE boundary.")

        self._right = QSpinBox()
        self._right.setRange(0, 10_000_000)
        self._right.setValue(opts.right_boundary)
        self._right.setToolTip("MSA column index for the right TE boundary.")

        self._radius = QSpinBox()
        self._radius.setRange(1, 10_000)
        self._radius.setValue(opts.nt_radius)
        self._radius.setSuffix(" nt")
        self._radius.setToolTip("Search window size on each side of the boundary.")

        self._max_sim = QDoubleSpinBox()
        self._max_sim.setRange(0.0, 1.0)
        self._max_sim.setDecimals(2)
        self._max_sim.setSingleStep(0.05)
        self._max_sim.setValue(opts.max_sim_threshold)

        self._nt_threshold = QDoubleSpinBox()
        self._nt_threshold.setRange(0.0, 1.0)
        self._nt_threshold.setDecimals(2)
        self._nt_threshold.setSingleStep(0.05)
        self._nt_threshold.setValue(opts.nt_threshold)

        self._cluster_eps = QDoubleSpinBox()
        self._cluster_eps.setRange(0.1, 10.0)
        self._cluster_eps.setDecimals(1)
        self._cluster_eps.setSingleStep(0.1)
        self._cluster_eps.setValue(opts.cluster_eps)

        form = QFormLayout()
        form.addRow("Left boundary (MSA column):", self._left)
        form.addRow("Right boundary (MSA column):", self._right)
        form.addRow("Search radius:", self._radius)
        form.addRow("Max TSD similarity:", self._max_sim)
        form.addRow("Poly-N threshold:", self._nt_threshold)
        form.addRow("Cluster distance (eps):", self._cluster_eps)

        hint = QLabel(
            "Run on an aligned multi-sequence FASTA. Boundaries are column positions "
            "in the MSA where TSDs are searched between left and right TE ends."
        )
        hint.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def options(self) -> TsdSearchOptions:
        return TsdSearchOptions(
            left_boundary=self._left.value(),
            right_boundary=self._right.value(),
            nt_radius=self._radius.value(),
            max_sim_threshold=self._max_sim.value(),
            nt_threshold=self._nt_threshold.value(),
            cluster_eps=self._cluster_eps.value(),
        )


class BlastParamsDialog(QDialog):
    def __init__(
        self,
        *,
        initial: BlastOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Blast parameters")
        opts = initial or BlastOptions()
        self._evalue = QDoubleSpinBox()
        configure_report_evalue_spinbox(self._evalue)
        self._evalue.setValue(normalize_blast_evalue(opts.e_value))

        self._max_msa = QSpinBox()
        self._max_msa.setRange(10, 5000)
        self._max_msa.setValue(opts.max_msa_lines)

        self._top_msa = QSpinBox()
        self._top_msa.setRange(10, 5000)
        self._top_msa.setValue(opts.top_msa_lines)

        self._write_gff = QCheckBox("Write genome GFF from BLAST hits")
        self._write_gff.setChecked(opts.write_gff)
        self._write_gff.setToolTip(
            "After Blast, write a GFF3 file next to the hit table "
            "(coordinates on the reference genome)."
        )

        self._min_bit_score = QDoubleSpinBox()
        self._min_bit_score.setRange(0.0, 1_000_000.0)
        self._min_bit_score.setDecimals(1)
        self._min_bit_score.setSingleStep(1.0)
        self._min_bit_score.setValue(opts.minimum_bit_score)
        self._min_bit_score.setToolTip("Only hits with bit score ≥ this value are written to GFF.")

        form = QFormLayout()
        form.addRow("E-value:", self._evalue)
        form.addRow("Max MSA lines:", self._max_msa)
        form.addRow("Top longest lines:", self._top_msa)
        form.addRow(self._write_gff)
        form.addRow("Minimum bit score (GFF):", self._min_bit_score)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def options(self) -> BlastOptions:
        return BlastOptions(
            e_value=normalize_blast_evalue(self._evalue.value()),
            max_msa_lines=self._max_msa.value(),
            top_msa_lines=self._top_msa.value(),
            write_gff=self._write_gff.isChecked(),
            minimum_bit_score=self._min_bit_score.value(),
        )


class ConsensusParamsDialog(QDialog):
    def __init__(
        self,
        *,
        initial: ConsensusOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Consensus parameters")
        opts = initial or ConsensusOptions()
        self._threshold = QDoubleSpinBox()
        self._threshold.setRange(0.0, 1.0)
        self._threshold.setDecimals(2)
        self._threshold.setSingleStep(0.05)
        self._threshold.setValue(opts.threshold)

        self._ambiguous = QComboBox()
        for base in ("N", "A", "C", "G", "T"):
            self._ambiguous.addItem(base)
        amb_index = self._ambiguous.findText(opts.ambiguous.upper()[:1])
        if amb_index >= 0:
            self._ambiguous.setCurrentIndex(amb_index)

        form = QFormLayout()
        form.addRow("Majority threshold:", self._threshold)
        form.addRow("Ambiguous base:", self._ambiguous)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def options(self) -> ConsensusOptions:
        return ConsensusOptions(
            threshold=self._threshold.value(),
            ambiguous=self._ambiguous.currentText(),
        )


class FlexidotParamsDialog(QDialog):
    def __init__(
        self,
        *,
        initial: FlexidotOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Flexidot parameters")
        opts = initial or FlexidotOptions()
        self._wordsize = QSpinBox()
        self._wordsize.setRange(MIN_FLEXIDOT_WORDSIZE, MAX_FLEXIDOT_WORDSIZE)
        self._wordsize.setValue(
            max(MIN_FLEXIDOT_WORDSIZE, min(MAX_FLEXIDOT_WORDSIZE, opts.wordsize))
        )
        self._wordsize.setToolTip(
            f"K-mer length (-k), {MIN_FLEXIDOT_WORDSIZE}–{MAX_FLEXIDOT_WORDSIZE}. "
            "Larger values are faster but less sensitive."
        )

        self._lcs = QCheckBox("LCS shading for multi-sequence plots (-x)")
        self._lcs.setChecked(opts.lcs_shading)
        self._lcs.setToolTip(
            "Highlights long shared subsequences in all-vs-all dotplots (mode 2+ sequences)."
        )

        self._use_gff = QCheckBox("Show GFF features on dotplot (-g)")
        self._use_gff.setChecked(opts.use_gff)
        self._use_gff.setToolTip(
            "When a companion GFF exists next to the FASTA (for example "
            "{stem}.features.gff3 or {stem}_blast.gff), Flexidot shades the "
            "dotplot with those features. TEviewer also writes "
            "{stem}_flexidot.gff.colors.config (edit colors) and "
            "{stem}_flexidot_legend.png (color key)."
        )

        form = QFormLayout()
        form.addRow("Word size (k-mer):", self._wordsize)
        form.addRow(self._lcs)
        form.addRow(self._use_gff)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def options(self) -> FlexidotOptions:
        return FlexidotOptions(
            wordsize=self._wordsize.value(),
            lcs_shading=self._lcs.isChecked(),
            use_gff=self._use_gff.isChecked(),
        )


_TE_ANNOTATION_SECTION_TITLE_STYLE = "font-size: 14px; font-weight: 600;"
_TE_ANNOTATION_SIMILARITY_DBS_PER_ROW = 8


class TeAnnotationDialog(QDialog):
    """Select auto- and similarity-annotation modules for batch GFF generation."""

    def __init__(self, *, parent=None) -> None:
        from teviewer.backends.auto_annotation import AutoAnnotationMode
        from teviewer.backends.annotation_colors import similarity_database_color
        from teviewer.backends.similarity_annotation import SimilarityDatabaseRun
        from teviewer.backends.te_annotation_batch import TeAnnotationOptions
        from teviewer.database_settings import load_similarity_annotation_databases

        super().__init__(parent)
        self.setWindowTitle("TE annotation")
        _prepare_option_dialog(self)
        self.setMinimumWidth(580)

        self._TeAnnotationOptions = TeAnnotationOptions
        self._SimilarityDatabaseRun = SimilarityDatabaseRun
        self._similarity_database_color = similarity_database_color
        self._auto_all_updating = False
        self._similarity_all_updating = False

        auto_section = QWidget(self)
        auto_outer = QVBoxLayout(auto_section)
        auto_outer.setContentsMargins(0, 0, 0, 0)
        auto_outer.setSpacing(6)

        auto_header = QHBoxLayout()
        auto_title = QLabel("Auto annotation", auto_section)
        auto_title.setStyleSheet(_TE_ANNOTATION_SECTION_TITLE_STYLE)
        auto_header.addWidget(auto_title, 0, Qt.AlignmentFlag.AlignVCenter)
        auto_settings_btn = QPushButton("Setting", auto_section)
        auto_settings_btn.setToolTip("Configure LTR, TIR, tandem, and ORF detection")
        auto_settings_btn.clicked.connect(self._open_auto_annotation_settings)
        auto_header.addWidget(auto_settings_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        auto_color_btn = QPushButton("Color", auto_section)
        auto_color_btn.setToolTip(
            "Set colors for feature types (LTR, TIR, ORF, …) and similarity databases"
        )
        auto_color_btn.clicked.connect(self._open_annotation_colors)
        auto_header.addWidget(auto_color_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        auto_header.addStretch(1)
        auto_outer.addLayout(auto_header)

        auto_checks_row = QHBoxLayout()
        auto_checks_row.setSpacing(10)
        self._auto_ann_checks: dict = {}
        for label, mode in (
            ("LTR", AutoAnnotationMode.LTR),
            ("TIR", AutoAnnotationMode.TIR),
            ("Tandem", AutoAnnotationMode.TANDEM),
            ("ORF", AutoAnnotationMode.ORF),
        ):
            check = QCheckBox(label, auto_section)
            check.setChecked(True)
            check.toggled.connect(self._on_auto_check_toggled)
            self._auto_ann_checks[mode] = check
            auto_checks_row.addWidget(check)

        self._auto_ann_all_check = QCheckBox("All", auto_section)
        self._auto_ann_all_check.setToolTip("Select or clear all auto-annotation detectors")
        self._auto_ann_all_check.toggled.connect(self._on_auto_all_toggled)
        auto_checks_row.addWidget(self._auto_ann_all_check)
        auto_checks_row.addStretch(1)
        auto_outer.addLayout(auto_checks_row)
        self._sync_auto_all_check()

        sim_section = QWidget(self)
        sim_outer = QVBoxLayout(sim_section)
        sim_outer.setContentsMargins(0, 0, 0, 0)
        sim_outer.setSpacing(6)

        sim_header = QHBoxLayout()
        sim_title = QLabel("Similarity annotation", sim_section)
        sim_title.setStyleSheet(_TE_ANNOTATION_SECTION_TITLE_STYLE)
        sim_header.addWidget(sim_title, 0, Qt.AlignmentFlag.AlignVCenter)
        sim_settings_btn = QPushButton("Setting", sim_section)
        sim_settings_btn.setToolTip("Configure similarity search parameters")
        sim_settings_btn.clicked.connect(self._open_similarity_annotation_settings)
        sim_header.addWidget(sim_settings_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        sim_header.addStretch(1)
        sim_outer.addLayout(sim_header)

        self._similarity_ann_all_check = QCheckBox("All", sim_section)
        self._similarity_ann_all_check.setToolTip("Select or clear all similarity databases")
        self._similarity_ann_all_check.toggled.connect(self._on_similarity_all_toggled)

        sim_checks_host = QWidget(sim_section)
        sim_checks_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        sim_checks_layout = QVBoxLayout(sim_checks_host)
        sim_checks_layout.setContentsMargins(0, 0, 0, 0)
        sim_checks_layout.setSpacing(4)
        self._similarity_db_rows: list[tuple] = []

        databases = load_similarity_annotation_databases()
        if not databases:
            empty = QLabel(
                "No databases defined. Add them in File → Define database.",
                sim_checks_host,
            )
            empty.setWordWrap(True)
            sim_checks_layout.addWidget(empty)
            self._similarity_ann_all_check.setEnabled(False)
        else:
            db_checks: list[QCheckBox] = []
            for index, entry in enumerate(databases):
                check = self._make_similarity_db_check(entry, index, sim_checks_host)
                self._similarity_db_rows.append((entry, check))
                db_checks.append(check)

            for row_start in range(0, len(db_checks), _TE_ANNOTATION_SIMILARITY_DBS_PER_ROW):
                row_checks = db_checks[row_start : row_start + _TE_ANNOTATION_SIMILARITY_DBS_PER_ROW]
                is_last_row = row_start + _TE_ANNOTATION_SIMILARITY_DBS_PER_ROW >= len(db_checks)
                row_widget = QWidget(sim_checks_host)
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(10)
                for check in row_checks:
                    row_layout.addWidget(check, 0, Qt.AlignmentFlag.AlignVCenter)
                if is_last_row:
                    row_layout.addWidget(
                        self._similarity_ann_all_check,
                        0,
                        Qt.AlignmentFlag.AlignVCenter,
                    )
                row_layout.addStretch(1)
                sim_checks_layout.addWidget(row_widget)
        sim_outer.addWidget(sim_checks_host)
        sim_description = QLabel("Annotate all selected TE sequences", sim_section)
        sim_description.setWordWrap(True)
        sim_description.setStyleSheet("color: palette(placeholder-text);")
        sim_outer.addWidget(sim_description)
        self._sync_similarity_all_check()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(auto_section)
        layout.addWidget(sim_section)
        layout.addWidget(buttons)

    def _make_similarity_db_check(self, entry, index: int, parent: QWidget) -> QCheckBox:
        color = self._similarity_database_color(entry.name, index)
        check = QCheckBox(entry.name, parent)
        check.setToolTip(f"{entry.display_type_label}\n{entry.path}")
        check.setChecked(True)
        check.setStyleSheet(f"QCheckBox {{ color: {color}; }}")
        check.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        check.toggled.connect(self._on_similarity_check_toggled)
        return check

    def _refresh_similarity_db_checkbox_colors(self) -> None:
        for index, (entry, check) in enumerate(self._similarity_db_rows):
            color = self._similarity_database_color(entry.name, index)
            check.setStyleSheet(f"QCheckBox {{ color: {color}; }}")

    def _open_auto_annotation_settings(self) -> None:
        from teviewer.backends.auto_annotation_settings import (
            load_auto_annotation_settings,
            save_auto_annotation_settings,
        )
        from teviewer.widgets.sequence_map_viewer import AutoAnnotationSettingsDialog

        settings = load_auto_annotation_settings()
        dialog = AutoAnnotationSettingsDialog(settings, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        save_auto_annotation_settings(dialog.settings())

    def _open_similarity_annotation_settings(self) -> None:
        from teviewer.backends.similarity_annotation_settings import (
            load_similarity_annotation_settings,
            save_similarity_annotation_settings,
        )
        from teviewer.widgets.sequence_map_viewer import SimilarityAnnotationSettingsDialog

        settings = load_similarity_annotation_settings()
        dialog = SimilarityAnnotationSettingsDialog(settings, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        save_similarity_annotation_settings(dialog.settings())

    def _open_annotation_colors(self) -> None:
        from teviewer.widgets.annotation_colors_dialog import AnnotationElementColorsDialog

        dialog = AnnotationElementColorsDialog(parent=self, show_apply_to_sequence=False)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._refresh_similarity_db_checkbox_colors()

    def _on_auto_check_toggled(self, _checked: bool) -> None:
        if self._auto_all_updating:
            return
        self._sync_auto_all_check()

    def _sync_auto_all_check(self) -> None:
        checks = list(self._auto_ann_checks.values())
        if not checks:
            return
        all_checked = all(check.isChecked() for check in checks)
        self._auto_all_updating = True
        self._auto_ann_all_check.setChecked(all_checked)
        self._auto_all_updating = False

    def _on_auto_all_toggled(self, checked: bool) -> None:
        if self._auto_all_updating:
            return
        self._auto_all_updating = True
        for check in self._auto_ann_checks.values():
            check.setChecked(checked)
        self._auto_all_updating = False

    def _on_similarity_check_toggled(self, _checked: bool) -> None:
        if self._similarity_all_updating:
            return
        self._sync_similarity_all_check()

    def _sync_similarity_all_check(self) -> None:
        checks = [check for _entry, check in self._similarity_db_rows]
        if not checks:
            self._similarity_all_updating = True
            self._similarity_ann_all_check.setChecked(False)
            self._similarity_all_updating = False
            return
        all_checked = all(check.isChecked() for check in checks)
        self._similarity_all_updating = True
        self._similarity_ann_all_check.setChecked(all_checked)
        self._similarity_all_updating = False

    def _on_similarity_all_toggled(self, checked: bool) -> None:
        if self._similarity_all_updating:
            return
        self._similarity_all_updating = True
        for _entry, check in self._similarity_db_rows:
            check.setChecked(checked)
        self._similarity_all_updating = False

    def options(self):
        auto_modes = tuple(
            mode for mode, check in self._auto_ann_checks.items() if check.isChecked()
        )
        similarity_databases: list = []
        for index, (entry, check) in enumerate(self._similarity_db_rows):
            if check.isChecked():
                similarity_databases.append(
                    self._SimilarityDatabaseRun(
                        database=entry,
                        color=self._similarity_database_color(entry.name, index),
                    )
                )
        return self._TeAnnotationOptions(
            auto_modes=auto_modes,
            similarity_databases=tuple(similarity_databases),
        )


class TeaAidParamsDialog(QDialog):
    def __init__(
        self,
        *,
        initial: TeaAidOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("TEAid parameters")
        opts = initial or TeaAidOptions()

        intro = QLabel(
            "These E-value apply only to TEAid genome BLAST.",
            self,
        )
        intro.setWordWrap(True)

        self._evalue = QDoubleSpinBox()
        configure_report_evalue_spinbox(self._evalue)
        self._evalue.setValue(
            normalize_blast_evalue(opts.e_value, default=DEFAULT_TEAID_EVALUE)
        )
        self._evalue.setToolTip(
            "Reporting E-value for the TEAid genome BLAST search only."
        )

        self._word_size = QSpinBox()
        self._word_size.setRange(MIN_TEAID_SELF_BLAST_WORD_SIZE, MAX_TEAID_SELF_BLAST_WORD_SIZE)
        self._word_size.setValue(
            max(
                MIN_TEAID_SELF_BLAST_WORD_SIZE,
                min(MAX_TEAID_SELF_BLAST_WORD_SIZE, opts.self_blast_word_size),
            )
        )
        self._word_size.setToolTip(
            "BLASTN word size (-word_size) for the TEAid self-BLAST dot plot only (4–25)."
        )

        form = QFormLayout()
        form.addRow("Genome BLAST E-value:", self._evalue)
        form.addRow("Self BLAST word size:", self._word_size)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def options(self) -> TeaAidOptions:
        return TeaAidOptions(
            e_value=normalize_blast_evalue(
                self._evalue.value(),
                default=DEFAULT_TEAID_EVALUE,
            ),
            self_blast_word_size=self._word_size.value(),
        )


class MsaCleanParamsDialog(QDialog):
    """Edit parameters for all MSA clean steps."""

    def __init__(
        self,
        *,
        initial: MsaCleanOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("MSA clean parameters")
        self.setMinimumWidth(420)
        opts = initial or MsaCleanOptions()

        default_box = QGroupBox("Toolbar default")
        self._default_method = QComboBox()
        for method_id, label in MSA_CLEAN_METHOD_CHOICES:
            self._default_method.addItem(label, method_id)
        index = self._default_method.findData(opts.default_method, Qt.ItemDataRole.UserRole)
        if index >= 0:
            self._default_method.setCurrentIndex(index)
        default_form = QFormLayout(default_box)
        default_form.addRow(
            "Default clean method:",
            self._default_method,
        )
        self._default_method.setToolTip(
            "Used when you click the main MSA clean toolbar button (not the menu items)."
        )
        self._method_help = QLabel()
        self._method_help.setWordWrap(True)
        self._method_help.setStyleSheet("color: palette(mid);")
        self._default_method.currentIndexChanged.connect(self._update_method_help)
        self._update_method_help()

        gappy_box = QGroupBox("Remove gappy columns")
        self._gap_threshold = QDoubleSpinBox()
        self._gap_threshold.setRange(0.0, 1.0)
        self._gap_threshold.setDecimals(2)
        self._gap_threshold.setSingleStep(0.05)
        self._gap_threshold.setValue(opts.gappy.gap_threshold)

        self._simi_gap = QDoubleSpinBox()
        self._simi_gap.setRange(0.0, 1.0)
        self._simi_gap.setDecimals(2)
        self._simi_gap.setSingleStep(0.05)
        self._simi_gap.setValue(opts.gappy.simi_check_gap_thr)

        self._similarity = QDoubleSpinBox()
        self._similarity.setRange(0.0, 1.0)
        self._similarity.setDecimals(2)
        self._similarity.setSingleStep(0.05)
        self._similarity.setValue(opts.gappy.similarity_thr)

        self._min_nt = QSpinBox()
        self._min_nt.setRange(1, 50)
        self._min_nt.setValue(opts.gappy.min_nucleotide)

        gappy_form = QFormLayout(gappy_box)
        gappy_form.addRow("Gap threshold:", self._gap_threshold)
        gappy_form.addRow("Similarity check gap threshold:", self._simi_gap)
        gappy_form.addRow("Similarity threshold:", self._similarity)
        gappy_form.addRow("Min nucleotides per column:", self._min_nt)

        div_box = QGroupBox("Clean row with divergence")
        self._div_threshold = QDoubleSpinBox()
        self._div_threshold.setRange(0.0, 1.0)
        self._div_threshold.setDecimals(2)
        self._div_threshold.setSingleStep(0.05)
        self._div_threshold.setValue(opts.divergence.threshold)

        self._div_window = QSpinBox()
        self._div_window.setRange(1, 10_000)
        self._div_window.setValue(opts.divergence.window_size)

        div_form = QFormLayout(div_box)
        div_form.addRow("Divergence threshold:", self._div_threshold)
        div_form.addRow("Window size (bp):", self._div_window)

        gap_box = QGroupBox("Clean row with gap")
        self._row_gap_threshold = QDoubleSpinBox()
        self._row_gap_threshold.setRange(0.0, 1.0)
        self._row_gap_threshold.setDecimals(3)
        self._row_gap_threshold.setSingleStep(0.01)
        self._row_gap_threshold.setValue(opts.gap_row.gap_threshold)

        self._row_gap_window = QSpinBox()
        self._row_gap_window.setRange(1, 10_000)
        self._row_gap_window.setValue(opts.gap_row.window_size)

        gap_form = QFormLayout(gap_box)
        gap_form.addRow("Gap proportion threshold:", self._row_gap_threshold)
        gap_form.addRow("Window size (bp):", self._row_gap_window)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(default_box)
        layout.addWidget(self._method_help)
        layout.addWidget(gappy_box)
        layout.addWidget(div_box)
        layout.addWidget(gap_box)
        layout.addWidget(buttons)

    def _update_method_help(self, _index: int | None = None) -> None:
        method_id = self._default_method.currentData(Qt.ItemDataRole.UserRole)
        if method_id is None:
            method_id = self._default_method.currentData()
        text = msa_clean_method_description(str(method_id or ""))
        self._method_help.setText(text)

    def options(self) -> MsaCleanOptions:
        method_index = self._default_method.currentIndex()
        default_method = self._default_method.itemData(
            method_index,
            Qt.ItemDataRole.UserRole,
        )
        if default_method is None:
            default_method = self._default_method.itemData(method_index)
        return MsaCleanOptions(
            default_method=str(default_method),
            gappy=GappyColumnOptions(
                gap_threshold=self._gap_threshold.value(),
                simi_check_gap_thr=self._simi_gap.value(),
                similarity_thr=self._similarity.value(),
                min_nucleotide=self._min_nt.value(),
            ),
            divergence=DivergenceRowOptions(
                threshold=self._div_threshold.value(),
                window_size=self._div_window.value(),
            ),
            gap_row=GapRowOptions(
                gap_threshold=self._row_gap_threshold.value(),
                window_size=self._row_gap_window.value(),
            ),
        )


class ChromosomeMultiSelectWidget(QWidget):
    """Filterable multi-select list of chromosome names from the genome FASTA."""

    def __init__(
        self,
        chromosome_names: list[str],
        *,
        chromosome_sizes: dict[str, int] | None = None,
        preselected: list[str] | None = None,
        chromosome_sort: str = CHROMOSOME_SORT_NATURAL,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._all_chrom_names = list(chromosome_names)
        self._chrom_sizes = {
            str(k): int(v) for k, v in (chromosome_sizes or {}).items()
        }
        self._sort_mode = chromosome_sort
        self._preselected = None if preselected is None else set(preselected)
        self._check_boxes: list[QCheckBox] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._filter = QLineEdit(self)
        self._filter.setPlaceholderText("Type to filter (e.g. chr5)")
        self._filter.textChanged.connect(self._apply_filter)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.StyledPanel)
        self._scroll.setFixedHeight(150)
        self._scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._checks_container = QWidget(self._scroll)
        self._checks_layout = QVBoxLayout(self._checks_container)
        self._checks_layout.setContentsMargins(6, 6, 6, 6)
        self._checks_layout.setSpacing(4)
        self._scroll.setWidget(self._checks_container)

        btn_row = QHBoxLayout()
        select_all_btn = QPushButton("Show all")
        select_all_btn.clicked.connect(self._check_all)
        clear_btn = QPushButton("Show none")
        clear_btn.clicked.connect(self._uncheck_all)
        if not self._all_chrom_names:
            select_all_btn.setEnabled(False)
            clear_btn.setEnabled(False)
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(clear_btn)
        min_size_lbl = QLabel("≥", self)
        min_size_lbl.setToolTip("Select chromosomes at least this large (skips small contigs)")
        self._min_size_mb = QDoubleSpinBox(self)
        self._min_size_mb.setRange(0.1, 10_000.0)
        self._min_size_mb.setDecimals(1)
        self._min_size_mb.setSingleStep(0.5)
        self._min_size_mb.setValue(2.0)
        self._min_size_mb.setFixedWidth(64)
        self._min_size_mb.setToolTip("Minimum chromosome size (Mb)")
        mb_unit_lbl = QLabel("Mb", self)
        self._min_size_confirm = QPushButton("Confirm", self)
        self._min_size_confirm.setToolTip("Select chromosomes ≥ the size above")
        self._min_size_confirm.clicked.connect(self._select_by_min_size_spinbox)
        if not self._all_chrom_names:
            self._min_size_mb.setEnabled(False)
            self._min_size_confirm.setEnabled(False)
        btn_row.addWidget(min_size_lbl)
        btn_row.addWidget(self._min_size_mb)
        btn_row.addWidget(mb_unit_lbl)
        btn_row.addWidget(self._min_size_confirm)
        btn_row.addStretch()

        layout.addWidget(self._filter)
        layout.addWidget(self._scroll)
        layout.addLayout(btn_row)
        self.setMaximumHeight(280)

        self._rebuild_check_list()
        if self._preselected is None and self._chrom_sizes:
            self._select_min_size_mb(2.0)

    def _select_by_min_size_spinbox(self) -> None:
        self._select_min_size_mb(self._min_size_mb.value())

    @staticmethod
    def _natural_sort_key(name: str) -> list:
        return [
            int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", str(name))
        ]

    def _sorted_names(self, mode: str) -> list[str]:
        names = list(self._all_chrom_names)
        if mode == CHROMOSOME_SORT_SIZE_DESC:
            return sorted(
                names,
                key=lambda c: (-self._chrom_sizes.get(c, 0), self._natural_sort_key(c)),
            )
        if mode == CHROMOSOME_SORT_SIZE_ASC:
            return sorted(
                names,
                key=lambda c: (self._chrom_sizes.get(c, 0), self._natural_sort_key(c)),
            )
        return sorted(names, key=self._natural_sort_key)

    def _display_label(self, name: str) -> str:
        size = self._chrom_sizes.get(name)
        if size is not None and size > 0:
            return f"{name} ({format_genome_length_bp(size)})"
        return name

    @staticmethod
    def _chrom_name_from_checkbox(cb: QCheckBox) -> str:
        raw = cb.property("chrom_name")
        if raw is not None:
            return str(raw)
        return cb.text()

    def _rebuild_check_list(self, selected: set[str] | None = None) -> None:
        if selected is None:
            selected = {self._chrom_name_from_checkbox(cb) for cb in self._check_boxes if cb.isChecked()}
            if not selected and self._preselected is not None:
                selected = set(self._preselected)
        while self._checks_layout.count():
            item = self._checks_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._check_boxes.clear()

        ordered = self._sorted_names(self._sort_mode)
        if not ordered:
            self._checks_layout.addWidget(QLabel("No items available", self._checks_container))
            self._checks_layout.addStretch(1)
            return

        for name in ordered:
            cb = QCheckBox(self._display_label(name), self._checks_container)
            cb.setProperty("chrom_name", name)
            cb.setChecked(name in selected)
            self._check_boxes.append(cb)
            self._checks_layout.addWidget(cb)
        self._checks_layout.addStretch(1)
        self._apply_filter(self._filter.text())

    def set_chromosome_sort(self, mode: str) -> None:
        if mode not in (
            CHROMOSOME_SORT_NATURAL,
            CHROMOSOME_SORT_SIZE_DESC,
            CHROMOSOME_SORT_SIZE_ASC,
        ):
            mode = CHROMOSOME_SORT_NATURAL
        self._sort_mode = mode
        self._rebuild_check_list()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for cb in self._check_boxes:
            cb.setVisible(not needle or needle in cb.text().lower())

    def selected_names(self) -> list[str]:
        needle = self._filter.text().strip().lower()
        names: list[str] = []
        for cb in self._check_boxes:
            if not cb.isChecked():
                continue
            if needle and not cb.isVisible():
                continue
            names.append(self._chrom_name_from_checkbox(cb))
        return names

    def _check_all(self) -> None:
        for cb in self._check_boxes:
            if cb.isVisible():
                cb.setChecked(True)

    def _uncheck_all(self) -> None:
        for cb in self._check_boxes:
            if cb.isVisible():
                cb.setChecked(False)

    def _select_min_size_mb(self, min_mb: float) -> None:
        min_bp = int(float(min_mb) * 1_000_000)
        selected = {
            name
            for name in self._all_chrom_names
            if self._chrom_sizes.get(name, 0) >= min_bp
        }
        self._rebuild_check_list(selected if selected else None)

    def name_count(self) -> int:
        return len(self._all_chrom_names)


class _TeInputFileRow(QWidget):
    """Single file path row with optional remove button."""

    remove_requested = Signal()
    activated = Signal(object)
    path_changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        initial: Path | None = None,
        removable: bool = True,
        placeholder: str = "RepeatMasker .out or BLAST hit table",
        browse_title: str = "Select RepeatMasker .out or BLAST hit table",
        file_filter: str = "TE hit tables (*.out *_blast.txt);;RepeatMasker (*.out);;All files (*)",
    ) -> None:
        super().__init__(parent)
        self._browse_title = browse_title
        self._file_filter = file_filter
        self._path = QLineEdit(self)
        self._path.setPlaceholderText(placeholder)
        self._path.setMinimumWidth(280)
        self._path.setFixedHeight(26)
        self._path.installEventFilter(self)
        if initial is not None:
            self._path.setText(str(initial.expanduser().resolve()))

        self._path.editingFinished.connect(self._emit_path_changed)

        browse_btn = QPushButton("Browse", self)
        browse_btn.setFixedHeight(26)
        browse_btn.clicked.connect(self._browse)

        remove_btn = QPushButton("Remove", self)
        remove_btn.setFixedHeight(26)
        remove_btn.setVisible(removable)
        remove_btn.clicked.connect(self.remove_requested.emit)
        self._remove_btn = remove_btn

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._path, stretch=1)
        layout.addWidget(browse_btn)
        layout.addWidget(remove_btn)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._path and event.type() == QEvent.Type.FocusIn:
            self.activated.emit(self)
        return super().eventFilter(obj, event)

    def set_removable(self, removable: bool) -> None:
        self._remove_btn.setVisible(removable)

    def set_path(self, path: Path) -> None:
        self._path.setText(str(path.expanduser().resolve()))
        self._emit_path_changed()

    def _emit_path_changed(self) -> None:
        self.path_changed.emit()

    def path(self) -> Path | None:
        text = self._path.text().strip()
        if not text:
            return None
        return Path(text).expanduser()

    def _browse(self) -> None:
        start = self._path.text().strip() or str(Path.home())
        picked, _ = QFileDialog.getOpenFileName(
            self,
            self._browse_title,
            start,
            self._file_filter,
        )
        if picked:
            self._path.setText(picked)
            self._emit_path_changed()


class TeMultiInputFilesWidget(QWidget):
    """One or more file paths with add/remove controls."""

    paths_changed = Signal()
    field_activated = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        initial: list[Path] | None = None,
        start_empty: bool = False,
        placeholder: str = "RepeatMasker .out or BLAST hit table",
        browse_title: str = "Select RepeatMasker .out or BLAST hit table",
        file_filter: str = "TE hit tables (*.out *_blast.txt);;RepeatMasker (*.out);;All files (*)",
        add_button_label: str = "Add another TE file",
        add_button_tooltip: str = (
            "Add another RepeatMasker .out or BLAST hit table. "
            "Track order in the plot matches file order: first row = top track."
        ),
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._placeholder = placeholder
        self._browse_title = browse_title
        self._file_filter = file_filter

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        self._rows: list[_TeInputFileRow] = []
        self._active_row: _TeInputFileRow | None = None

        self._add_btn = QPushButton(add_button_label, self)
        self._add_btn.setFixedHeight(22)
        self._add_btn.setToolTip(add_button_tooltip)
        self._add_btn.clicked.connect(self._on_add_clicked)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(self._add_btn)
        footer.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(self._rows_layout)
        outer.addLayout(footer)

        if initial:
            for path in initial:
                self.add_row(path)
        if not self._rows and not start_empty:
            self.add_row()

    def _on_add_clicked(self) -> None:
        self.add_row(focus=True)
        self._add_btn.setEnabled(False)
        QTimer.singleShot(0, lambda: self._add_btn.setEnabled(True))

    def add_row(self, path: Path | None = None, *, focus: bool = False) -> None:
        row = _TeInputFileRow(
            self,
            initial=path,
            removable=len(self._rows) >= 1,
            placeholder=self._placeholder,
            browse_title=self._browse_title,
            file_filter=self._file_filter,
        )
        row.remove_requested.connect(lambda r=row: self._remove_row(r))
        row.activated.connect(self._on_row_activated)
        row.path_changed.connect(self._emit_paths_changed)
        self._rows.append(row)
        self._rows_layout.addWidget(row)
        self._refresh_remove_buttons()
        if focus:
            self._on_row_activated(row)
            row._path.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_row_activated(self, row: _TeInputFileRow) -> None:
        self._active_row = row
        self.field_activated.emit()
        for item in self._rows:
            item._path.setStyleSheet(
                ""
                if item is not row
                else "background: palette(alternate-base);"
            )

    def _remove_row(self, row: _TeInputFileRow) -> None:
        if row not in self._rows or len(self._rows) <= 1:
            return
        if self._active_row is row:
            self._active_row = None
        self._rows.remove(row)
        self._rows_layout.removeWidget(row)
        row.deleteLater()
        self._refresh_remove_buttons()
        self._emit_paths_changed()

    def _emit_paths_changed(self) -> None:
        self.paths_changed.emit()

    def _refresh_remove_buttons(self) -> None:
        removable = len(self._rows) > 1
        for row in self._rows:
            row.set_removable(removable)

    def set_path_at_focus(self, path: Path) -> bool:
        """Fill the path field that last had keyboard focus."""
        if self._active_row is None or self._active_row not in self._rows:
            return False
        self._active_row.set_path(path)
        return True

    def set_primary_path(self, path: Path) -> bool:
        return self.set_path_at_focus(path)

    def paths(self) -> list[Path]:
        out: list[Path] = []
        for row in self._rows:
            picked = row.path()
            if picked is not None:
                out.append(picked.expanduser().resolve())
        return out


class TeHitTableInputWidget(QWidget):
    """RepeatMasker .out / BLAST hit table path entry with browse."""

    def __init__(self, parent: QWidget | None = None, *, initial: Path | None = None) -> None:
        super().__init__(parent)
        self._row = _TeInputFileRow(self, initial=initial, removable=False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._row, stretch=1)
        self.setMinimumWidth(440)

    def set_path(self, path: Path) -> None:
        self._row.set_path(path)

    def path(self) -> Path | None:
        return self._row.path()


class GeneInputFileWidget(QWidget):
    """Optional GFF/GTF/BED/VCF annotation path entry."""

    def __init__(self, parent: QWidget | None = None, *, initial: Path | None = None) -> None:
        super().__init__(parent)
        self._path = QLineEdit(self)
        self._path.setPlaceholderText("Optional GFF/GTF/BED/VCF annotation")
        self._path.setMinimumWidth(280)
        self._path.setFixedHeight(26)
        if initial is not None:
            self._path.setText(str(initial.expanduser().resolve()))
        browse_btn = QPushButton("Browse", self)
        browse_btn.setFixedHeight(26)
        browse_btn.clicked.connect(self._browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._path, stretch=1)
        layout.addWidget(browse_btn)

    def set_path(self, path: Path | None) -> None:
        if path is None:
            self._path.clear()
        else:
            self._path.setText(str(path.expanduser().resolve()))

    def path(self) -> Path | None:
        text = self._path.text().strip()
        if not text:
            return None
        return Path(text).expanduser()

    def _browse(self) -> None:
        start = self._path.text().strip() or str(Path.home())
        picked, _ = QFileDialog.getOpenFileName(
            self,
            "Select annotation file",
            start,
            "Annotations (*.gff *.gff3 *.gtf *.bed *.vcf *.vcf.gz);;All files (*)",
        )
        if picked:
            self._path.setText(picked)


def _form_section_separator() -> QWidget:
    """Thin horizontal rule between major dialog sections."""
    host = QWidget()
    host.setFixedHeight(9)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 2, 0, 2)
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    layout.addWidget(line)
    return host


def _uniform_field_width(widgets: list[QWidget], *, min_width: int = 300) -> None:
    """Give option controls a shared minimum width so columns line up."""
    for widget in widgets:
        widget.setMinimumWidth(min_width)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class AnnotationFeatureTypesWidget(QWidget):
    """Checklist of GFF/GTF feature types (or BED intervals)."""

    _DEFAULT_TYPES = ("gene", "mRNA", "CDS", "exon", "transcript")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._list = QListWidget(self)
        self._list.setMaximumHeight(92)
        self._list.setMinimumHeight(72)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._list.setToolTip(
            "Feature types from column 3 of GFF/GTF files. BED files use a single "
            "'interval' type. VCF files use SNP, INDEL, MNP, SV, and other variant classes."
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)
        self._populate_default()

    def _populate_default(self) -> None:
        checked = {t.lower() for t in DEFAULT_ANNOTATION_FEATURE_TYPES}
        self._set_types(list(self._DEFAULT_TYPES), checked=checked)

    def _set_types(self, types: list[str], *, checked: set[str] | None = None) -> None:
        prev = checked if checked is not None else {t.lower() for t in self.selected_types()}
        self._list.clear()
        for feature_type in types:
            item = QListWidgetItem(feature_type)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            state = (
                Qt.CheckState.Checked
                if feature_type.lower() in prev
                else Qt.CheckState.Unchecked
            )
            item.setCheckState(state)
            self._list.addItem(item)

    def selected_types(self) -> list[str]:
        out: list[str] = []
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                out.append(item.text())
        return out

    def set_checked_types(self, types: list[str]) -> None:
        want = {t.lower() for t in types if t.strip()}
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item is None:
                continue
            item.setCheckState(
                Qt.CheckState.Checked
                if item.text().lower() in want
                else Qt.CheckState.Unchecked
            )

    def refresh_from_paths(self, paths: list[Path]) -> None:
        from teviewer.backends.gff_features import list_feature_types_in_annotation

        merged: set[str] = set()
        for raw in paths:
            path = raw.expanduser()
            if not path.is_file():
                continue
            merged.update(list_feature_types_in_annotation(path))
        if not merged:
            self._populate_default()
            return
        if merged == {"interval"}:
            self._set_types(["interval"], checked={"interval"})
            return
        merged_lower = {t.lower() for t in merged}
        if merged_lower.issubset({"snp", "indel", "mnp", "sv", "variant", "other"}):
            default = [
                t for t in sorted(merged, key=str.lower)
                if t.lower() in {"snp", "indel", "mnp", "sv"}
            ]
            if not default:
                default = sorted(merged, key=str.lower)
            prev = {t.lower() for t in self.selected_types()} or {t.lower() for t in default}
            self._set_types(sorted(merged, key=str.lower), checked=prev)
            return
        prev = {t.lower() for t in self.selected_types()} or {"gene"}
        self._set_types(sorted(merged, key=str.lower), checked=prev)


class PerFileAnnotationFeatureTypesWidget(QWidget):
    """Feature types per annotation file (one checklist when only one file is selected)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stack = QVBoxLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(6)
        self._single = AnnotationFeatureTypesWidget(self)
        self._per_file_host = QWidget(self)
        self._per_file_layout = QVBoxLayout(self._per_file_host)
        self._per_file_layout.setContentsMargins(0, 0, 0, 0)
        self._per_file_layout.setSpacing(6)
        self._widgets_by_key: dict[str, AnnotationFeatureTypesWidget] = {}
        self._saved_by_key: dict[str, list[str]] = {}
        self._global_fallback: list[str] = []
        self._stack.addWidget(self._single)
        self._stack.addWidget(self._per_file_host)
        self._per_file_host.hide()

    @staticmethod
    def _path_key(path: Path) -> str:
        return str(path.expanduser().resolve())

    def set_global_fallback_types(self, types: list[str] | None) -> None:
        self._global_fallback = [str(t).strip() for t in (types or []) if str(t).strip()]

    def set_saved_by_file(self, by_file: dict[str, list[str]] | None) -> None:
        self._saved_by_key = {
            self._path_key(Path(raw)): list(types)
            for raw, types in (by_file or {}).items()
            if types
        }

    def _clear_per_file_widgets(self) -> None:
        while self._per_file_layout.count():
            item = self._per_file_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._widgets_by_key.clear()

    def refresh_from_paths(self, paths: list[Path]) -> None:
        valid = [p.expanduser() for p in paths if p.expanduser().is_file()]
        if len(valid) <= 1:
            self._single.show()
            self._per_file_host.hide()
            self._clear_per_file_widgets()
            if valid:
                self._single.refresh_from_paths(valid)
                key = self._path_key(valid[0])
                if key in self._saved_by_key:
                    self._single.set_checked_types(self._saved_by_key[key])
                elif self._global_fallback:
                    self._single.set_checked_types(self._global_fallback)
            else:
                self._single.refresh_from_paths([])
            return

        self._single.hide()
        self._per_file_host.show()
        self._clear_per_file_widgets()
        for path in valid:
            key = self._path_key(path)
            group = QGroupBox(path.name, self._per_file_host)
            group.setToolTip(str(path))
            group_layout = QVBoxLayout(group)
            widget = AnnotationFeatureTypesWidget(group)
            widget.refresh_from_paths([path])
            if key in self._saved_by_key:
                widget.set_checked_types(self._saved_by_key[key])
            elif self._saved_by_key:
                by_name = {
                    Path(raw).name: types for raw, types in self._saved_by_key.items()
                }
                if path.name in by_name:
                    widget.set_checked_types(by_name[path.name])
            elif self._global_fallback:
                widget.set_checked_types(self._global_fallback)
            group_layout.addWidget(widget)
            self._per_file_layout.addWidget(group)
            self._widgets_by_key[key] = widget

    def selected_types(self) -> list[str]:
        if self._single.isVisible():
            return self._single.selected_types()
        if len(self._widgets_by_key) == 1:
            return next(iter(self._widgets_by_key.values())).selected_types()
        return []

    def selected_types_by_file(self) -> dict[str, list[str]]:
        if self._single.isVisible():
            types = self._single.selected_types()
            return {}
        out: dict[str, list[str]] = {}
        for key, widget in self._widgets_by_key.items():
            picked = widget.selected_types()
            if picked:
                out[key] = picked
        return out


class TeDensityPlotDialog(QDialog):
    """TE density / genome coverage plot settings and input hit table."""

    def __init__(
        self,
        *,
        initial: TeGenomeMapOptions | None = None,
        chromosome_names: list[str] | None = None,
        chromosome_sizes: dict[str, int] | None = None,
        input_file: Path | None = None,
        consensus_input_file: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        _prepare_option_dialog(self)
        self.setWindowTitle("TE visualization")
        self.setMinimumWidth(720)
        self._opts = initial or TeGenomeMapOptions()

        masking_initial: list[Path] | None = None
        if input_file is not None:
            masking_initial = [input_file]
        self._masking_input = TeMultiInputFilesWidget(
            self,
            initial=masking_initial,
            placeholder="RepeatMasker .out or BLAST hit table",
            add_button_label="Add another masking file",
            add_button_tooltip=(
                "Add another RepeatMasker .out or BLAST hit table. "
                "Each file is drawn on its own track (first row = top track)."
            ),
        )
        self._consensus_input = TeMultiInputFilesWidget(
            self,
            initial=[consensus_input_file] if consensus_input_file is not None else None,
            placeholder="TE consensus FASTA (.fasta / .fa)",
            browse_title="Select TE consensus FASTA",
            file_filter="FASTA (*.fasta *.fa *.fna);;All files (*)",
            add_button_label="Add another TE consensus file",
            add_button_tooltip=(
                "Add another TE consensus FASTA. Sequences are BLASTed against the "
                "project genome; each file is plotted on its own track."
            ),
        )
        self._gene_input = TeMultiInputFilesWidget(
            self,
            placeholder="Optional GFF/GTF/BED/VCF annotation",
            browse_title="Select annotation file",
            file_filter="Annotations (*.gff *.gff3 *.gtf *.bed *.vcf *.vcf.gz);;All files (*)",
            add_button_label="Add another annotation file",
            add_button_tooltip=(
                "Add another GFF, GTF, BED, or VCF annotation file. "
                "Each file is drawn on its own track below TE tracks."
            ),
        )
        self._methylation_input = TeMultiInputFilesWidget(
            self,
            placeholder="Optional Bismark coverage (.cov / .cov.gz)",
            browse_title="Select Bismark coverage file",
            file_filter=(
                "Bismark coverage (*.cov *.cov.gz *bismark*.cov*);;All files (*)"
            ),
            add_button_label="Add another methylation file",
            add_button_tooltip=(
                "Add another Bismark coverage file. Each file adds four tracks per "
                "chromosome: total (genome), covered (.cov lines), covered fraction, "
                "and methylation level (0–1)."
            ),
        )
        self._focused_file_input: TeMultiInputFilesWidget | None = None
        for widget in (
            self._masking_input,
            self._consensus_input,
            self._gene_input,
            self._methylation_input,
        ):
            widget.field_activated.connect(self._on_file_input_field_activated)

        self._bin_kb = QSpinBox(self)
        self._bin_kb.setRange(5, 500)
        self._bin_kb.setValue(max(5, self._opts.bin_size_bp // 1000))
        self._bin_kb.setSuffix(" kb")
        self._density = QComboBox(self)
        self._density.addItem("Total TE length (bp) per window", TE_GENOME_MAP_DENSITY_TE_LENGTH)
        self._density.addItem("TE hits number per window", TE_GENOME_MAP_DENSITY_HIT_COUNT)
        idx = self._density.findData(self._opts.density_mode)
        if idx >= 0:
            self._density.setCurrentIndex(idx)
        self._color_by = QComboBox(self)
        self._color_by.addItem("% identity", TE_GENOME_MAP_COLOR_IDENTITY)
        self._color_by.addItem("TE superfamily", TE_GENOME_MAP_COLOR_SUPERFAMILY)
        self._color_by.addItem("TE family", TE_GENOME_MAP_COLOR_FAMILY)
        idx_color = self._color_by.findData(self._opts.color_by)
        if idx_color >= 0:
            self._color_by.setCurrentIndex(idx_color)
        self._methylation_coverage_min = QSpinBox(self)
        self._methylation_coverage_min.setRange(1, 10_000)
        self._methylation_coverage_min.setValue(max(1, int(self._opts.methylation_coverage_min)))
        self._methylation_coverage_min.setToolTip(
            "Reserved for future filtering. Covered tracks count every line in the "
            "Bismark .cov file whose position falls in each window."
        )
        self._split_strand = QCheckBox("Separate forward / reverse strands", self)
        self._split_strand.setChecked(bool(self._opts.split_strand_tracks))
        self._split_strand.setToolTip(
            "Draw separate forward- and reverse-strand tracks per chromosome for "
            "RepeatMasker .out TE hits and for GFF/GTF/BED/VCF annotation features."
        )
        self._collapse_overlaps = QCheckBox("Collapse overlapped TEs", self)
        self._collapse_overlaps.setChecked(bool(self._opts.collapse_overlaps))
        self._collapse_overlaps.setToolTip(
            "For total TE length per window, count each base pair at most once when TEs "
            "overlap. When color is by superfamily or family, overlaps are collapsed "
            "separately within each TE type; with % identity coloring, all TEs in a window "
            "are collapsed together. With separate forward/reverse tracks, collapse applies "
            "within each strand track only."
        )
        self._show_te_diff = QCheckBox("Show TE difference track (2 TE sources)", self)
        self._show_te_diff.setChecked(bool(self._opts.show_te_diff_track))
        self._show_meth_diff = QCheckBox(
            "Show methylation difference track (2 methylation files)", self
        )
        self._show_meth_diff.setChecked(bool(self._opts.show_meth_diff_track))
        self._show_meth_diff.setToolTip(
            "When two Bismark coverage files are provided, add a diff track per "
            "chromosome comparing methylation level (first file above axis, second below)."
        )
        self._show_te_diff.setToolTip(
            "When exactly two TE hit-table sources are selected (masking files and/or "
            "consensus BLAST tables), add a per-chromosome diff track "
            "(exclusive TE bp: above = first source only, below = second only). "
            "Track order follows input file order top to bottom. "
            "This step is optional and can take extra time on large genomes."
        )

        self._annotation_density = QComboBox(self)
        self._annotation_density.addItem(
            "Total element length per window", TE_GENOME_MAP_DENSITY_TE_LENGTH
        )
        self._annotation_density.addItem(
            "Element hit number per window", TE_GENOME_MAP_DENSITY_HIT_COUNT
        )
        ann_idx = self._annotation_density.findData(self._opts.annotation_density_mode)
        if ann_idx >= 0:
            self._annotation_density.setCurrentIndex(ann_idx)
        self._annotation_features = PerFileAnnotationFeatureTypesWidget(self)
        self._annotation_features.set_global_fallback_types(self._opts.annotation_feature_types)
        if self._opts.annotation_feature_types_by_file:
            self._annotation_features.set_saved_by_file(
                self._opts.annotation_feature_types_by_file,
            )

        self._chromosome_sort = QComboBox(self)
        self._chromosome_sort.addItem("Natural (name order)", CHROMOSOME_SORT_NATURAL)
        self._chromosome_sort.addItem("Size (largest first)", CHROMOSOME_SORT_SIZE_DESC)
        self._chromosome_sort.addItem("Size (smallest first)", CHROMOSOME_SORT_SIZE_ASC)
        self._chromosome_sort.setToolTip(
            "Order of chromosomes in the list below (for selecting which to show)."
        )
        self._chrom_picker = ChromosomeMultiSelectWidget(
            chromosome_names or [],
            chromosome_sizes=chromosome_sizes,
            preselected=self._opts.chromosomes_only,
            chromosome_sort=self._opts.chromosome_sort,
            parent=self,
        )
        sort_idx = self._chromosome_sort.findData(self._opts.chromosome_sort)
        if sort_idx >= 0:
            self._chromosome_sort.blockSignals(True)
            self._chromosome_sort.setCurrentIndex(sort_idx)
            self._chromosome_sort.blockSignals(False)
        self._chromosome_sort.currentIndexChanged.connect(self._on_chromosome_sort_changed)

        _uniform_field_width(
            [self._density, self._color_by, self._annotation_density, self._chromosome_sort],
            min_width=300,
        )
        for spin in (self._bin_kb, self._methylation_coverage_min):
            spin.setMinimumWidth(100)
            spin.setMaximumWidth(120)

        form_host = QWidget(self)
        form = QFormLayout(form_host)
        form.setContentsMargins(12, 10, 12, 10)
        form.setVerticalSpacing(8)
        form.setHorizontalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)

        form.addRow("TE masking file:", self._masking_input)
        form.addRow("TE consensus file:", self._consensus_input)
        form.addRow("Y axis content:", self._density)
        form.addRow("Color by:", self._color_by)
        form.addRow("", self._split_strand)
        form.addRow("", self._collapse_overlaps)
        form.addRow("", self._show_te_diff)
        form.addRow(_form_section_separator())
        form.addRow("Other annotation file:", self._gene_input)
        form.addRow("Display content:", self._annotation_features)
        form.addRow("Y axis content:", self._annotation_density)
        form.addRow(_form_section_separator())
        form.addRow("DNA methylation file:", self._methylation_input)
        form.addRow("", self._show_meth_diff)
        form.addRow("Methylation coverage min:", self._methylation_coverage_min)
        form.addRow(_form_section_separator())
        form.addRow("Window size:", self._bin_kb)
        form.addRow("Chromosome order:", self._chromosome_sort)
        self._chrom_picker.setToolTip(
            "Each chromosome is one row in the map. Many small scaffolds are slower "
            "than a few large ones — set a minimum size (Mb) and click Confirm."
        )
        form.addRow("Chromosomes to show:", self._chrom_picker)

        self._gene_input.paths_changed.connect(self._refresh_annotation_feature_types)
        self._refresh_annotation_feature_types()

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(form_host)
        scroll.setMinimumHeight(320)
        scroll.setMaximumHeight(560)

        buttons = _run_cancel_button_box(self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _on_file_input_field_activated(self) -> None:
        sender = self.sender()
        if isinstance(sender, TeMultiInputFilesWidget):
            self._focused_file_input = sender

    def apply_path_from_panel(self, path: Path) -> bool:
        if self._focused_file_input is None:
            return False
        filled = self._focused_file_input.set_path_at_focus(path)
        if filled and self._focused_file_input is self._gene_input:
            self._refresh_annotation_feature_types()
        return filled

    def set_te_input_file(self, path: Path) -> bool:
        return self._masking_input.set_path_at_focus(path)

    def set_te_consensus_input_file(self, path: Path) -> bool:
        return self._consensus_input.set_path_at_focus(path)

    def set_gene_input_file(self, path: Path) -> bool:
        filled = self._gene_input.set_path_at_focus(path)
        if filled:
            self._refresh_annotation_feature_types()
        return filled

    def _refresh_annotation_feature_types(self) -> None:
        self._annotation_features.refresh_from_paths(self.gene_input_files())

    def _on_chromosome_sort_changed(self) -> None:
        mode = str(self._chromosome_sort.currentData() or CHROMOSOME_SORT_NATURAL)
        self._chrom_picker.set_chromosome_sort(mode)

    def set_methylation_input_file(self, path: Path) -> bool:
        return self._methylation_input.set_path_at_focus(path)

    def te_masking_files(self) -> list[Path]:
        return self._masking_input.paths()

    def te_consensus_files(self) -> list[Path]:
        return self._consensus_input.paths()

    def te_input_files(self) -> list[Path]:
        """Masking hit-table paths (backward-compatible alias)."""
        return self.te_masking_files()

    def gene_input_files(self) -> list[Path]:
        return self._gene_input.paths()

    def methylation_input_files(self) -> list[Path]:
        return self._methylation_input.paths()

    def gene_input_file(self) -> Path | None:
        paths = self.gene_input_files()
        return paths[0] if paths else None

    def options(self) -> TeGenomeMapOptions:
        mode = self._density.currentData()
        if mode not in (TE_GENOME_MAP_DENSITY_HIT_COUNT, TE_GENOME_MAP_DENSITY_TE_LENGTH):
            mode = TE_GENOME_MAP_DENSITY_HIT_COUNT
        ann_mode = self._annotation_density.currentData()
        if ann_mode not in (TE_GENOME_MAP_DENSITY_HIT_COUNT, TE_GENOME_MAP_DENSITY_TE_LENGTH):
            ann_mode = DEFAULT_ANNOTATION_DENSITY
        ann_types = self._annotation_features.selected_types()
        ann_by_file = self._annotation_features.selected_types_by_file()
        selected = self._chrom_picker.selected_names()
        if selected and len(selected) == self._chrom_picker.name_count():
            selected = []
        chrom_sort = str(self._chromosome_sort.currentData() or CHROMOSOME_SORT_NATURAL)
        if chrom_sort not in (
            CHROMOSOME_SORT_NATURAL,
            CHROMOSOME_SORT_SIZE_DESC,
            CHROMOSOME_SORT_SIZE_ASC,
        ):
            chrom_sort = CHROMOSOME_SORT_NATURAL
        return TeGenomeMapOptions(
            bin_size_bp=max(5_000, int(self._bin_kb.value()) * 1000),
            density_mode=str(mode),
            color_by=str(self._color_by.currentData()),
            methylation_coverage_min=max(1, int(self._methylation_coverage_min.value())),
            split_strand_tracks=self._split_strand.isChecked(),
            collapse_overlaps=self._collapse_overlaps.isChecked(),
            show_te_diff_track=self._show_te_diff.isChecked(),
            show_meth_diff_track=self._show_meth_diff.isChecked(),
            show_window_ref_line=self._opts.show_window_ref_line,
            annotation_density_mode=str(ann_mode),
            annotation_feature_types=ann_types or None,
            annotation_feature_types_by_file=ann_by_file or None,
            chromosomes_only=selected or None,
            superfamilies_only=None,
            chromosome_sort=chrom_sort,
        )


class TeDivergencePlotDialog(QDialog):
    """TE divergence histogram settings and input hit table."""

    def __init__(
        self,
        *,
        initial: TeDivergencePlotOptions | None = None,
        input_file: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        _prepare_option_dialog(self)
        self.setWindowTitle("TE divergence plot")
        self.setMinimumWidth(680)
        self._opts = initial or TeDivergencePlotOptions()

        self._input = TeMultiInputFilesWidget(
            self,
            initial=[input_file] if input_file is not None else None,
        )
        self._focused_file_input: TeMultiInputFilesWidget | None = None
        self._input.field_activated.connect(self._on_file_input_field_activated)

        self._bin_width = QDoubleSpinBox(self)
        self._bin_width.setRange(0.001, 0.25)
        self._bin_width.setDecimals(3)
        self._bin_width.setSingleStep(0.001)
        self._bin_width.setValue(float(self._opts.bin_width))
        self._bin_width.setToolTip(
            "Width of each bin on the x-axis (divergence = 1 − identity, range 0–1)."
        )

        form = QFormLayout()
        form.addRow("TE input files:", self._input)
        form.addRow("Bin size:", self._bin_width)

        buttons = _run_cancel_button_box(self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _on_file_input_field_activated(self) -> None:
        sender = self.sender()
        if isinstance(sender, TeMultiInputFilesWidget):
            self._focused_file_input = sender

    def apply_path_from_panel(self, path: Path) -> bool:
        if self._focused_file_input is None:
            return False
        return self._focused_file_input.set_path_at_focus(path)

    def set_te_input_file(self, path: Path) -> bool:
        return self._input.set_path_at_focus(path)

    def te_input_files(self) -> list[Path]:
        return self._input.paths()

    def options(self) -> TeDivergencePlotOptions:
        return TeDivergencePlotOptions(bin_width=float(self._bin_width.value()))


def _browse_file_line(
    parent: QWidget,
    line: QLineEdit,
    *,
    title: str,
    filt: str,
) -> QWidget:
    row = QWidget(parent)
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(line)

    def browse() -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            row,
            title,
            line.text() or str(Path.home()),
            filt,
        )
        if chosen:
            line.setText(chosen)

    btn = QPushButton("Browse", row)
    btn.clicked.connect(browse)
    h.addWidget(btn)
    return row


def _browse_dir_line(parent: QWidget, line: QLineEdit, *, title: str) -> QWidget:
    row = QWidget(parent)
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(line)

    def browse() -> None:
        chosen = QFileDialog.getExistingDirectory(
            row,
            title,
            line.text() or str(Path.home()),
        )
        if chosen:
            line.setText(chosen)

    btn = QPushButton("Browse", row)
    btn.clicked.connect(browse)
    h.addWidget(btn)
    return row


class ConfusionMatrixBenchmarkDialog(QDialog):
    """Compare query RepeatMasker .out files to a reference library on the genome."""

    def __init__(
        self,
        *,
        initial: TeConfusionMatrixBenchmarkOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        _prepare_option_dialog(self)
        self.setWindowTitle("Confusion matrix benchmarker")
        self.setMinimumWidth(620)
        opts = initial or TeConfusionMatrixBenchmarkOptions()

        self._tetrimmer_home = QLineEdit(opts.tetrimmer_home)
        self._reference = QLineEdit(opts.reference_out)
        self._less_class = QCheckBox("Simpler TE classes (merge LINE/SINE to Non-LTR)")
        self._less_class.setChecked(opts.less_classification)
        self._debug = QCheckBox("Keep intermediate files (debug)")
        self._debug.setChecked(opts.debug)

        hint = QLabel(
            "Select one or more <b>query</b> RepeatMasker .out files in the Files panel. "
            "The reference .out is the gold-standard library annotation on the same genome. "
            "Genome FASTA comes from Project settings. Requires bedtools and TEtrimmer "
            "<code>TE_anno_benchmarker.py</code>."
        )
        hint.setWordWrap(True)

        form = QFormLayout()
        form.addRow(
            "TEtrimmer folder:",
            _browse_dir_line(self, self._tetrimmer_home, title="Select TEtrimmer repository root"),
        )
        form.addRow(
            "Reference RM .out:",
            _browse_file_line(
                self,
                self._reference,
                title="Reference RepeatMasker .out",
                filt="RepeatMasker out (*.out);;All files (*)",
            ),
        )
        form.addRow("", self._less_class)
        form.addRow("", self._debug)

        buttons = _run_cancel_button_box(self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def options(self) -> TeConfusionMatrixBenchmarkOptions:
        return TeConfusionMatrixBenchmarkOptions(
            tetrimmer_home=self._tetrimmer_home.text().strip(),
            reference_out=self._reference.text().strip(),
            less_classification=self._less_class.isChecked(),
            debug=self._debug.isChecked(),
        )


class TeLibraryBenchmarkDialog(QDialog):
    """Benchmark a TE consensus library against a curated standard library."""

    def __init__(
        self,
        *,
        initial: TeLibraryBenchmarkOptions | None = None,
        query_file: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        _prepare_option_dialog(self)
        self.setWindowTitle("TE library benchmarker")
        self.setMinimumWidth(620)
        opts = initial or TeLibraryBenchmarkOptions()
        if query_file is not None:
            opts = TeLibraryBenchmarkOptions(
                query_fasta=str(query_file),
                standard_fasta=opts.standard_fasta,
                rm_out=opts.rm_out,
                run_repeatmasker=opts.run_repeatmasker,
                threads=opts.threads,
            )

        self._query = QLineEdit(opts.query_fasta)
        self._standard = QLineEdit(opts.standard_fasta)
        self._rm_out = QLineEdit(opts.rm_out)
        self._run_rm = QCheckBox("Run RepeatMasker (-lib standard query)")
        self._run_rm.setChecked(opts.run_repeatmasker)
        self._threads = QSpinBox()
        self._threads.setRange(1, 64)
        self._threads.setValue(max(1, int(opts.threads)))

        hint = QLabel(
            "Mask the <b>query</b> TE consensus FASTA with RepeatMasker using the "
            "<b>standard</b> curated library (<code>-lib</code>), then classify families "
            "as Perfect, Good, Present, or Not found (RepeatModeler2-style)."
        )
        hint.setWordWrap(True)

        form = QFormLayout()
        form.addRow(
            "Query library FASTA:",
            _browse_file_line(
                self,
                self._query,
                title="Query TE library FASTA",
                filt="FASTA (*.fa *.fasta *.fas);;All files (*)",
            ),
        )
        form.addRow(
            "Standard library FASTA:",
            _browse_file_line(
                self,
                self._standard,
                title="Standard TE library FASTA",
                filt="FASTA (*.fa *.fasta *.fas);;All files (*)",
            ),
        )
        form.addRow(
            "Existing RM .out (optional):",
            _browse_file_line(
                self,
                self._rm_out,
                title="Existing lib-vs-lib RepeatMasker .out",
                filt="RepeatMasker out (*.out);;All files (*)",
            ),
        )
        form.addRow("", self._run_rm)
        form.addRow("RepeatMasker threads:", self._threads)

        buttons = _run_cancel_button_box(self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def options(self) -> TeLibraryBenchmarkOptions:
        return TeLibraryBenchmarkOptions(
            query_fasta=self._query.text().strip(),
            standard_fasta=self._standard.text().strip(),
            rm_out=self._rm_out.text().strip(),
            run_repeatmasker=self._run_rm.isChecked(),
            threads=int(self._threads.value()),
        )


# Backward-compatible alias (removed from menus; use TeDensityPlotDialog).
TeGenomeMapDefaultsDialog = TeDensityPlotDialog

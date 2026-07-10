"""TEviewer main window with folder navigator and file workspace."""

from __future__ import annotations

import logging
import shutil
import platform
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QFileSystemWatcher,
    QMimeData,
    QObject,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QBrush, QColor, QDrag, QFont, QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QHeaderView,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolBar,
    QToolButton,
    QStatusBar,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QLabel,
    QColorDialog,
)
from teviewer import __version__
from teviewer.backends.genome_prepare import ensure_genome_artifacts
from teviewer.backends.blast_genome_plot import (
    _map_chromosome_filter_to_genome,
    blast_genome_map_html_path_for_blast_table,
    genome_map_html_path_for_te_inputs,
    blast_txt_path_for_query,
    chromosome_names_from_genome,
    genome_chrom_sizes_from_fasta,
    find_blast_table_for_query,
    invalidate_genome_chromosome_cache,
    is_blast_table_file,
    is_divergence_plot_html_file,
    is_genome_map_html_file,
    is_repeatmasker_out_file,
    is_te_hit_table_file,
    is_teviewer_hits_cache_file,
    te_hit_table_stem,
    write_blast_divergence_plot_html,
    GenomeMapNothingToPlotError,
    write_blast_genome_map_html,
    TE_INPUT_KIND_CONSENSUS,
    TE_INPUT_KIND_MASKING,
)
from teviewer.backends.igv_viewer import (
    discover_igv_annotations,
    is_alignment_preview_file,
    set_igv_extra_annotations_provider,
)
from teviewer.backends.job_cancel import CANCELLED_MESSAGE, JobCancellation, JobCancelledError

logger = logging.getLogger(__name__)
from teviewer.backends.te_benchmark import (
    default_tetrimmer_home,
    require_bedtools,
    run_confusion_matrix_benchmark,
)
from teviewer.backends.te_library_benchmark import run_te_library_benchmark
from teviewer.backends.curation import effective_batch_workers, is_flexidot_extra_plot_file, run_batch
from teviewer.backends.gui_functions import flexidot_executable
from teviewer.backends.sequence_aligner import (
    alignment_backends,
    run_alignment,
    run_alignment_combined,
)
from teviewer.backends.bismark_cov import is_bismark_cov_file
from teviewer.backends.gff_features import (
    build_gff_annotation_html,
    find_companion_gff,
    is_gene_annotation_file,
)
from teviewer.backends.sequence_features import is_sequence_map_hidden_file
from teviewer.plugins import get_registry, load_plugins
from teviewer.plugins.custom_command import (
    UserCommandPlugin,
    UserCommandRunDialog,
    delete_user_command_plugin_spec,
    existing_output_files,
    is_file_var_mode,
    is_folder_var_mode,
    is_path_var_mode,
    normalize_var_mode,
    save_user_command_plugin_spec,
)
from teviewer.backends.sequence_viewer import open_fasta
from teviewer.job_options import (
    ALIGN_MODE_COMBINED,
    load_align_options,
    load_blast_options,
    load_consensus_options,
    load_extend_options,
    load_flexidot_options,
    load_msa_clean_options,
    load_teaid_options,
    load_te_genome_map_options,
    load_te_divergence_plot_options,
    load_te_confusion_matrix_benchmark_options,
    load_te_library_benchmark_options,
    load_tsd_search_options,
    msa_clean_method_description,
    msa_clean_method_label,
    save_align_options,
    save_blast_options,
    save_consensus_options,
    save_extend_options,
    save_flexidot_options,
    save_msa_clean_options,
    save_teaid_options,
    save_te_genome_map_options,
    save_te_divergence_plot_options,
    save_te_confusion_matrix_benchmark_options,
    save_te_library_benchmark_options,
    save_tsd_search_options,
    TeGenomeMapOptions,
    TeDivergencePlotOptions,
    TeConfusionMatrixBenchmarkOptions,
    TeLibraryBenchmarkOptions,
    TsdSearchOptions,
)
from teviewer.views.tool_dialogs import (
    AlignParamsDialog,
    BlastParamsDialog,
    ConsensusParamsDialog,
    ExtendParamsDialog,
    FlexidotParamsDialog,
    TeAnnotationDialog,
    MsaCleanParamsDialog,
    TeaAidParamsDialog,
    TsdSearchParamsDialog,
    TeDensityPlotDialog,
    TeDivergencePlotDialog,
    ConfusionMatrixBenchmarkDialog,
    TeLibraryBenchmarkDialog,
    CommandPluginDesignerDialog,
    PluginManageDialog,
    exec_modal_dialog,
)
from teviewer.backends.separate_fasta import (
    SEPARATED_TE_DIR,
    count_fasta_sequences,
    sanitize_name,
    separate_sequences,
    separation_output_dir,
)
from teviewer.views.genome_dialog import GenomeDialog, is_genome_fasta
from teviewer.views.define_database_dialog import DefineDatabaseDialog, resolve_panel_database_path
from teviewer.views.settings_dialog import (
    SettingsDialog,
    add_genome_to_history,
    load_last_folder,
    load_expanded_folders,
    load_root_folders,
    save_workspace,
)
from teviewer.views.toolbar_dialog import (
    DEFAULT_TOOLBAR_ORDER,
    load_toolbar_font_size,
    load_toolbar_order,
)
from teviewer.widgets.browser_panel_settings import load_browser_panel_font_size
from teviewer.ui.platform import reveal_in_file_manager
from teviewer.ui.text_editor import open_in_text_editor
from teviewer.ui.theme import application_stylesheet
from teviewer.widgets.hidden_folders import (
    hide_root_folder,
    load_hidden_root_folders,
    remove_hidden_root,
    replace_hidden_root_path,
    unhide_root_folder,
)
from teviewer.widgets.folder_colors import (
    FOLDER_COLOR_PRESETS,
    apply_folder_item_color,
    apply_folder_colors_to_tree,
    get_folder_color,
    remove_folder_colors_under,
    replace_folder_color_paths,
    set_folder_color,
)
from teviewer.widgets.file_sort import (
    FileSortMode,
    file_sort_mode_labels,
    load_file_sort_mode,
    save_file_sort_mode,
    sort_file_paths,
)
from teviewer.widgets.preview_tabs import PreviewTabWidget, is_previewable_file, preview_path_priority, set_genome_path_provider
from teviewer.widgets.task_progress import TaskProgressPanel
from teviewer.widgets.database_index_runner import DatabaseIndexRunner

ROLE_PATH = Qt.ItemDataRole.UserRole
ROLE_LAZY_PLACEHOLDER = Qt.ItemDataRole.UserRole + 1


def _unique_duplicate_path(path: Path) -> Path:
    """Next unused path in the same folder: ``name copy.ext``, ``name copy 2.ext``, …"""
    parent = path.parent
    candidate = parent / f"{path.stem} copy{path.suffix}"
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = parent / f"{path.stem} copy {n}{path.suffix}"
        if not candidate.exists():
            return candidate
        n += 1


_NEW_OUTPUT_BG = QColor(214, 245, 214)
_NEW_OUTPUT_FG = QColor(0, 100, 0)
_SOURCE_BG = QColor(220, 235, 255)
_SOURCE_FG = QColor(0, 70, 140)

_FASTA_SUFFIXES = {".fa", ".fasta", ".fas"}

_TOOLBAR_TOOLTIPS = {
    "aliview": "Open selected FASTA in AliView",
    "align": "Align FASTA using default parameters",
    "blast": "BLAST selected FASTA against the project genome using default parameters",
    "te_genome_map": "TE density plot using default parameters",
    "te_benchmark": "TE benchmarking (confusion matrix and library comparison)",
    "te_divergence_plot": "TE divergence plot (divergence vs total TE length)",
    "extend": "Extend MSA ends using default parameters",
    "teaid": "TEAid interactive HTML report using default parameters",
    "msa_clean": "Trim or clean MSA using default parameters",
    "flexidot": "Dotplot comparison of selected sequences using default parameters",
    "consensus": "Build consensus from selected MSA using default parameters",
    "plugin:minimap2": "Map selected FASTA to reference with minimap2",
}

_JOB_DISPLAY_TITLES = {
    "teaid": "TEAid",
    "blast": "Blast",
    "extend": "Extend",
    "msa_clean": "MSA clean",
    "msa_clean_gappy": "MSA remove gappy columns",
    "msa_clean_div": "Clean row with divergence",
    "msa_clean_gap": "Clean row with gap",
    "msa_clean_row_col": "Clean row and column",
    "consensus_generation": "Consensus",
    "flexidot": "Flexidot",
    "te_annotation": "TE annotation",
    "tsd_search": "TSD search",
    "te_confusion_benchmark": "Confusion matrix benchmark",
    "te_library_benchmark": "TE library benchmark",
}


class AlignWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        seq_files: list[Path],
        *,
        backend: str = "auto",
        num_threads: int = 5,
        mode: str = "one_by_one",
        max_workers: int = 4,
    ):
        super().__init__()
        self._seq_files = seq_files
        self._backend = backend
        self._num_threads = num_threads
        self._mode = mode
        self._max_workers = max_workers

    @Slot()
    def run(self) -> None:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if self._mode == ALIGN_MODE_COMBINED:
            try:
                self.progress.emit(0, "Aligning combined MSA…")
                output = run_alignment_combined(
                    self._seq_files,
                    backend=self._backend,
                    num_threads=self._num_threads,
                )
                self.progress.emit(1, "Alignment finished.")
                self.finished.emit([str(output)])
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(str(exc))
            return

        total = len(self._seq_files)
        created: list[str] = []
        failures: list[str] = []
        workers = effective_batch_workers(self._max_workers, total)
        completed = 0

        def _align_one(seq_path: Path) -> tuple[Path, str | None, str | None]:
            try:
                output = run_alignment(
                    seq_path,
                    backend=self._backend,
                    num_threads=self._num_threads,
                )
                return seq_path, str(output), None
            except Exception as exc:  # noqa: BLE001
                return seq_path, None, str(exc)

        try:
            if workers == 1:
                for seq_path in self._seq_files:
                    self.progress.emit(completed, f"Aligning {seq_path.name}…")
                    _, out_path, err = _align_one(seq_path)
                    completed += 1
                    if err:
                        failures.append(f"{seq_path.name}: {err}")
                    elif out_path:
                        created.append(out_path)
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(_align_one, p) for p in self._seq_files]
                    for future in as_completed(futures):
                        seq_path, out_path, err = future.result()
                        self.progress.emit(completed, f"Aligning {seq_path.name}…")
                        completed += 1
                        if err:
                            failures.append(f"{seq_path.name}: {err}")
                        elif out_path:
                            created.append(out_path)
            self.progress.emit(total, "Alignment finished.")
            if failures and not created:
                self.failed.emit("\n".join(failures[:8]))
                return
            if failures:
                self.finished.emit(created)
                return
            self.finished.emit(created)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class GenomeMapWorker(QObject):
    """Build TE genome map HTML off the UI thread."""

    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        te_input_files: list[Path],
        genome_fasta: Path,
        *,
        job_kwargs: dict | None = None,
    ):
        super().__init__()
        self._te_input_files = [p.expanduser().resolve() for p in te_input_files]
        self._genome_fasta = genome_fasta.expanduser().resolve()
        self._job_kwargs = job_kwargs or {}

    @Slot()
    def run(self) -> None:
        try:
            html_path = write_blast_genome_map_html(
                self._te_input_files,
                genome_fasta=self._genome_fasta,
                progress=self.progress.emit,
                **self._job_kwargs,
            )
            if html_path is None:
                self.failed.emit("Could not build the genome map.")
                return
            self.finished.emit(html_path)
        except JobCancelledError:
            self.failed.emit(CANCELLED_MESSAGE)
        except GenomeMapNothingToPlotError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ConfusionMatrixBenchmarkWorker(QObject):
    """Run TEtrimmer confusion-matrix benchmark for one or more query .out files."""

    progress = Signal(int, str)
    finished = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        query_files: list[Path],
        *,
        reference_out: Path,
        genome_fasta: Path,
        tetrimmer_home: Path,
        less_classification: bool = False,
        debug: bool = False,
        cancel: JobCancellation | None = None,
    ) -> None:
        super().__init__()
        self._query_files = [p.expanduser().resolve() for p in query_files]
        self._reference_out = reference_out.expanduser().resolve()
        self._genome_fasta = genome_fasta.expanduser().resolve()
        self._tetrimmer_home = tetrimmer_home.expanduser().resolve()
        self._less_classification = less_classification
        self._debug = debug
        self._cancel = cancel

    @Slot()
    def run(self) -> None:
        try:
            created: list[Path] = []
            total = len(self._query_files)
            for index, query in enumerate(self._query_files, start=1):
                if self._cancel is not None and self._cancel.requested:
                    raise JobCancelledError("Job stopped by user")
                self.progress.emit(index - 1, f"Benchmarking: {query.name}…")
                outputs = run_confusion_matrix_benchmark(
                    query_out=query,
                    reference_out=self._reference_out,
                    genome_fasta=self._genome_fasta,
                    output_dir=query.parent,
                    tetrimmer_home=self._tetrimmer_home,
                    less_classification=self._less_classification,
                    debug=self._debug,
                )
                created.extend(outputs)
                self.progress.emit(index, f"Finished: {query.name}")
            self.finished.emit(created)
        except JobCancelledError:
            self.failed.emit(CANCELLED_MESSAGE)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class TeLibraryBenchmarkWorker(QObject):
    """Run TE consensus-library benchmark (Perfect / Good / Present)."""

    progress = Signal(int, str)
    finished = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        *,
        query_fasta: Path,
        standard_fasta: Path,
        rm_out: Path | None = None,
        run_repeatmasker: bool = True,
        threads: int = 4,
        cancel: JobCancellation | None = None,
    ) -> None:
        super().__init__()
        self._query_fasta = query_fasta.expanduser().resolve()
        self._standard_fasta = standard_fasta.expanduser().resolve()
        self._rm_out = rm_out.expanduser().resolve() if rm_out else None
        self._run_repeatmasker = run_repeatmasker
        self._threads = max(1, int(threads))
        self._cancel = cancel

    @Slot()
    def run(self) -> None:
        try:
            if self._cancel is not None and self._cancel.requested:
                raise JobCancelledError("Job stopped by user")
            self.progress.emit(0, f"Library benchmark: {self._query_fasta.name}…")
            outputs = run_te_library_benchmark(
                query_fasta=self._query_fasta,
                standard_fasta=self._standard_fasta,
                rm_out=self._rm_out,
                run_repeatmasker=self._run_repeatmasker,
                threads=self._threads,
            )
            self.progress.emit(1, "Finished")
            self.finished.emit(outputs)
        except JobCancelledError:
            self.failed.emit(CANCELLED_MESSAGE)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class FunctionWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        run_func,
        func_name: str,
        seq_files: list[Path],
        job_kwargs: dict | None = None,
    ):
        super().__init__()
        self._run_func = run_func
        self._func_name = func_name
        self._seq_files = seq_files
        self._job_kwargs = job_kwargs or {}

    @Slot()
    def run(self) -> None:
        try:
            result = self._run_func(
                self._func_name,
                self._seq_files,
                self.progress.emit,
                **self._job_kwargs,
            )
            self.finished.emit(result)
        except JobCancelledError:
            self.failed.emit(CANCELLED_MESSAGE)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class FileListWidget(QListWidget):
    """File list that supports dragging files as URLs."""

    open_in_preview_requested = Signal(list)
    open_in_text_editor_requested = Signal(list)
    delete_files_requested = Signal(list)
    duplicate_files_requested = Signal(list)
    rename_file_requested = Signal(Path)
    separate_fasta_requested = Signal(Path)
    separate_fasta_subfolders_requested = Signal(Path)
    blast_genome_map_requested = Signal(Path)
    blast_divergence_requested = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSpacing(0)
        self.setDragEnabled(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, position) -> None:
        paths = self._selected_paths()
        if not paths:
            return
        menu = QMenu(self)
        if len(paths) == 1:
            path = paths[0]
            menu.addAction("Open in preview", lambda: self.open_in_preview_requested.emit(paths))
            menu.addAction(
                "Open in text editor",
                lambda: self.open_in_text_editor_requested.emit(paths),
            )
            menu.addAction("Rename", lambda: self.rename_file_requested.emit(path))
            if path.suffix.lower() in _FASTA_SUFFIXES:
                try:
                    seq_n = count_fasta_sequences(path)
                except Exception:  # noqa: BLE001
                    seq_n = 0
                if seq_n > 1:
                    menu.addAction(
                        f"Separate sequence into {seq_n} files",
                        lambda: self.separate_fasta_requested.emit(path),
                    )
                    menu.addAction(
                        f"Separate sequence into {seq_n} folders",
                        lambda: self.separate_fasta_subfolders_requested.emit(path),
                    )
                blast_txt = find_blast_table_for_query(path)
                if blast_txt is not None:
                    menu.addAction(
                        "TE density plot",
                        lambda bt=blast_txt: self.blast_genome_map_requested.emit(bt),
                    )
            if is_te_hit_table_file(path):
                menu.addAction(
                    "TE density plot",
                    lambda bt=path: self.blast_genome_map_requested.emit(bt),
                )
                menu.addAction(
                    "TE divergence plot",
                    lambda bt=path: self.blast_divergence_requested.emit(bt),
                )
        else:
            menu.addAction(
                f"Open {len(paths)} files in tabs",
                lambda: self.open_in_preview_requested.emit(paths),
            )
            menu.addAction(
                f"Open {len(paths)} files in text editor",
                lambda: self.open_in_text_editor_requested.emit(paths),
            )
        if len(paths) == 1:
            menu.addAction(
                "Duplicate",
                lambda: self.duplicate_files_requested.emit(paths),
            )
        else:
            menu.addAction(
                f"Duplicate {len(paths)} files",
                lambda: self.duplicate_files_requested.emit(paths),
            )
        menu.addSeparator()
        menu.addAction("Open in AliView", self._context_open_aliview)
        if len(paths) == 1:
            label = (
                "Reveal in Finder"
                if platform.system() == "Darwin"
                else "Show in file manager"
            )
            menu.addAction(label, lambda: self._reveal_paths(paths))
        menu.addSeparator()
        if len(paths) == 1:
            menu.addAction("Delete", lambda: self.delete_files_requested.emit(paths))
        else:
            menu.addAction(
                f"Delete {len(paths)} files",
                lambda: self.delete_files_requested.emit(paths),
            )
        menu.exec(self.mapToGlobal(position))

    def _context_open_aliview(self) -> None:
        window = self.window()
        if hasattr(window, "_open_selected_in_aliview"):
            window._open_selected_in_aliview()

    def _reveal_paths(self, paths: list[Path]) -> None:
        window = self.window()
        if hasattr(window, "_reveal_in_file_manager"):
            window._reveal_in_file_manager(paths)

    def _selected_paths(self) -> list[Path]:
        paths = []
        for item in self.selectedItems():
            raw = item.data(ROLE_PATH)
            if raw:
                path = Path(str(raw))
                if path.is_file():
                    paths.append(path)
        return paths

    def mimeData(self, items: list[QListWidgetItem]) -> QMimeData:  # noqa: N802 (Qt API)
        mime = QMimeData()
        urls = []
        for item in items:
            raw = item.data(ROLE_PATH)
            if raw:
                urls.append(Path(str(raw)).as_uri())
        if urls:
            from PySide6.QtCore import QUrl
            mime.setUrls([QUrl(u) for u in urls])
        return mime

    def startDrag(self, supportedActions):  # noqa: N802 (Qt API)
        items = self.selectedItems()
        if not items:
            return
        drag = QDrag(self)
        drag.setMimeData(self.mimeData(items))
        drag.exec(supportedActions)


class FolderTreeWidget(QTreeWidget):
    """Folder-only navigator; accepts dropped folders/files."""

    folder_selected = Signal(Path)
    files_dropped_to_folder = Signal(Path, list)
    folder_dropped = Signal(Path)
    rename_folder_requested = Signal(Path)
    delete_folders_requested = Signal(list)
    clear_root_folders_requested = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.setUniformRowHeights(False)
        self.setAnimated(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.itemSelectionChanged.connect(self._emit_selected_folder)

    def _folder_path_for_item(self, item: QTreeWidgetItem | None) -> Path | None:
        if item is None:
            return None
        raw = item.data(0, ROLE_PATH)
        if not raw:
            return None
        path = Path(str(raw))
        return path if path.is_dir() else None

    def _selected_folder_items(self) -> list[tuple[Path, QTreeWidgetItem]]:
        pairs: list[tuple[Path, QTreeWidgetItem]] = []
        seen: set[str] = set()
        for item in self.selectedItems():
            folder = self._folder_path_for_item(item)
            if folder is None:
                continue
            key = str(folder.expanduser().resolve())
            if key in seen:
                continue
            seen.add(key)
            pairs.append((folder, item))
        return pairs

    def _is_top_level_item(self, item: QTreeWidgetItem) -> bool:
        return item.parent() is None

    def _show_context_menu(self, position) -> None:
        item = self.itemAt(position)
        if item is None:
            return
        if item not in self.selectedItems():
            self.clearSelection()
            item.setSelected(True)

        folder_items = self._selected_folder_items()
        if not folder_items:
            return
        folders = [folder for folder, _item in folder_items]
        menu = QMenu(self)

        if len(folders) == 1:
            folder = folders[0]
            menu.addAction("Rename folder", lambda: self.rename_folder_requested.emit(folder))
        root_pairs = [(folder, tree_item) for folder, tree_item in folder_items if self._is_top_level_item(tree_item)]
        if root_pairs:
            root_folders = [folder for folder, _tree_item in root_pairs]
            if len(root_folders) == 1:
                remove_action = menu.addAction(
                    "Remove from list",
                    lambda: self.clear_root_folders_requested.emit(root_folders),
                )
            else:
                remove_action = menu.addAction(
                    f"Remove {len(root_folders)} from list",
                    lambda: self.clear_root_folders_requested.emit(root_folders),
                )
            remove_action.setToolTip(
                "Hide selected top-level folder(s) from TEviewer. Files on disk are not deleted."
            )
        menu.addSeparator()
        color_menu = menu.addMenu("Folder color")
        color_menu.addAction(
            "Choose color…",
            lambda: self._choose_folders_color(folder_items),
        )
        for label, hex_color in FOLDER_COLOR_PRESETS:
            color_menu.addAction(
                label,
                lambda checked=False, c=hex_color, pairs=folder_items: self._set_folders_color(pairs, c),
            )
        color_menu.addSeparator()
        color_menu.addAction(
            "Clear color",
            lambda: self._clear_folders_color(folder_items),
        )
        menu.addSeparator()
        if len(folders) == 1:
            menu.addAction(
                "Delete folder",
                lambda: self.delete_folders_requested.emit(folders),
            )
        else:
            menu.addAction(
                f"Delete {len(folders)} folders",
                lambda: self.delete_folders_requested.emit(folders),
            )
        menu.exec(self.mapToGlobal(position))

    def _set_folders_color(
        self,
        folder_items: list[tuple[Path, QTreeWidgetItem]],
        color: str,
    ) -> None:
        for folder, item in folder_items:
            set_folder_color(folder, color)
            apply_folder_item_color(item, folder)

    def _choose_folders_color(self, folder_items: list[tuple[Path, QTreeWidgetItem]]) -> None:
        first_folder, _item = folder_items[0]
        stored = get_folder_color(first_folder)
        initial = QColor(stored) if stored else QColor(FOLDER_COLOR_PRESETS[0][1])
        if not initial.isValid():
            initial = QColor(FOLDER_COLOR_PRESETS[0][1])

        dialog = QColorDialog(initial, self.window())
        dialog.setWindowTitle("Folder color")
        dialog.setStyleSheet("")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        picked = dialog.selectedColor()
        if not picked.isValid():
            return
        self._set_folders_color(folder_items, picked.name())

    def _clear_folders_color(self, folder_items: list[tuple[Path, QTreeWidgetItem]]) -> None:
        for folder, item in folder_items:
            set_folder_color(folder, None)
            apply_folder_item_color(item, folder)

    def dragEnterEvent(self, event):  # noqa: N802 (Qt API)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):  # noqa: N802 (Qt API)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):  # noqa: N802 (Qt API)
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        urls = event.mimeData().urls()
        paths = [Path(url.toLocalFile()) for url in urls if url.isLocalFile()]
        if not paths:
            event.ignore()
            return

        target_item = self.itemAt(event.position().toPoint())
        target_dir = None
        if target_item:
            raw = target_item.data(0, ROLE_PATH)
            if raw:
                target_dir = Path(str(raw))

        folder_paths = [p for p in paths if p.is_dir()]
        file_paths = [p for p in paths if p.is_file()]

        if folder_paths:
            for folder in folder_paths:
                self.folder_dropped.emit(folder)
        if target_dir and file_paths:
            self.files_dropped_to_folder.emit(target_dir, file_paths)
        event.acceptProposedAction()

    def _emit_selected_folder(self) -> None:
        item = self.currentItem()
        if not item:
            return
        raw = item.data(0, ROLE_PATH)
        if not raw:
            return
        path = Path(str(raw))
        if path.is_dir():
            self.folder_selected.emit(path)


@dataclass
class _PendingTeVizBuild:
    """TE visualization run waiting for consensus FASTA BLAST to finish."""

    masking_paths: list[Path]
    consensus_fastas: list[Path]
    gene_paths: list[Path]
    methylation_paths: list[Path]
    map_options: TeGenomeMapOptions


class MainWindow(QMainWindow):
    """Dockable Folders, Files, and Preview panels (Geneious-style layout)."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"TEviewer {__version__}")
        self.resize(1680, 980)
        self.setMinimumSize(1100, 700)
        self._toolbar_font_size = load_toolbar_font_size()
        self._browser_panel_font_size = load_browser_panel_font_size()
        self._functions_toolbar = None
        self._toolbar_font = QFont(self.font())
        self._browser_panel_font = QFont(self.font())
        self._apply_toolbar_theme()

        self._project = SettingsDialog.load_project_from_settings()
        if self._project.genome_file and self._project.genome_file.is_file():
            add_genome_to_history(self._project.genome_file)
        self._current_folder: Path | None = None
        self._saved_last_folder: Path | None = None
        self._worker_thread: QThread | None = None
        self._worker: FunctionWorker | AlignWorker | None = None
        self._task_progress: TaskProgressPanel | None = None
        self._job_running = False
        self._last_job_source_files: list[Path] = []
        self._job_toolbar_actions: list[QAction | QToolButton] = []
        self._cached_folder_files: list[Path] = []
        self._highlight_output_keys: set[str] = set()
        self._highlight_source_keys: set[str] = set()
        self._genome_dialog: GenomeDialog | None = None
        self._define_database_dialog: DefineDatabaseDialog | None = None
        self._command_plugin_dialog: CommandPluginDesignerDialog | None = None
        self._plugin_run_dialog: UserCommandRunDialog | None = None
        self._msa_clean_options = load_msa_clean_options()
        self._blast_options = load_blast_options()
        self._extend_options = load_extend_options()
        self._tsd_search_options = load_tsd_search_options()
        self._teaid_options = load_teaid_options()
        self._align_options = load_align_options()
        self._te_genome_map_options = load_te_genome_map_options()
        # Superfamily filtering is controlled on the plot page, not in settings.
        self._te_genome_map_options.superfamilies_only = None
        self._te_divergence_plot_options = load_te_divergence_plot_options()
        self._consensus_options = load_consensus_options()
        self._flexidot_options = load_flexidot_options()
        self._te_confusion_benchmark_options = load_te_confusion_matrix_benchmark_options()
        self._te_library_benchmark_options = load_te_library_benchmark_options()
        self.database_index_runner = DatabaseIndexRunner(self)
        self._plugin_registry = load_plugins()
        self._plugins_menu: QMenu | None = None
        self._toolbar_order = load_toolbar_order(self._plugin_registry)
        self._dock_folders: QDockWidget | None = None
        self._dock_files: QDockWidget | None = None
        self._dock_preview: QDockWidget | None = None
        self._preview_host: QWidget | None = None
        self._preview_tabs: PreviewTabWidget | None = None
        self._pending_te_genome_map: TeGenomeMapOptions | None = None
        self._pending_te_genome_map_fastas: list[Path] = []
        self._pending_te_viz: _PendingTeVizBuild | None = None
        self._te_viz_input_dialog: TeDensityPlotDialog | TeDivergencePlotDialog | None = None
        self._genome_chrom_names_cache: list[str] = []
        self._genome_chrom_sizes_cache: dict[str, int] = {}
        self._genome_chrom_cache_path: Path | None = None
        self._genome_map_thread: QThread | None = None
        self._genome_map_worker: GenomeMapWorker | None = None
        self._benchmark_thread: QThread | None = None
        self._benchmark_worker: ConfusionMatrixBenchmarkWorker | TeLibraryBenchmarkWorker | None = None
        self._last_benchmark_source_files: list[Path] = []
        self._job_cancel = JobCancellation()
        self._genome_map_blast_txt: Path | None = None
        self._genome_map_te_paths: list[Path] = []
        self._queued_genome_map_jobs: list[tuple[Path, TeGenomeMapOptions | None]] = []
        self._stop_btn: QPushButton | None = None
        QTimer.singleShot(500, self._warm_genome_chromosome_cache)

        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
        )
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.TabPosition.North)

        self._folder_tree = FolderTreeWidget()
        self._folder_tree.setObjectName("FolderTree")
        self._folder_tree.folder_selected.connect(self._on_folder_selected)
        self._folder_tree.files_dropped_to_folder.connect(self._copy_files_to_folder)
        self._folder_tree.folder_dropped.connect(
            lambda folder: self._add_root_folder(folder, unhide=True),
        )

        self._file_list = FileListWidget()
        self._file_list.setObjectName("FileList")
        # Open preview on single click/selection changes (unless a dialog is
        # currently visible that should receive the panel click for path filling).
        self._file_list.currentItemChanged.connect(self._on_file_current_item_changed)
        self._file_list.itemClicked.connect(self._on_file_item_clicked)
        # Only sync dialog inputs from an explicit Files-panel click.
        # (itemSelectionChanged can also fire on non-click selection changes.)
        self._file_list.itemDoubleClicked.connect(self._on_file_double_clicked)
        self._file_list.open_in_preview_requested.connect(self._open_files_in_preview_tabs)
        self._file_list.open_in_text_editor_requested.connect(self._open_selected_in_text_editor)
        self._file_list.delete_files_requested.connect(self._delete_selected_files)
        self._file_list.duplicate_files_requested.connect(self._duplicate_selected_files)
        self._file_list.rename_file_requested.connect(self._rename_file)
        self._file_list.separate_fasta_requested.connect(self._separate_fasta_file)
        self._file_list.separate_fasta_subfolders_requested.connect(
            self._separate_fasta_to_subfolders_file,
        )
        self._file_list.blast_genome_map_requested.connect(
            lambda p: self._open_te_density_plot_dialog(input_file=p),
        )
        self._file_list.blast_divergence_requested.connect(
            lambda p: self._open_te_divergence_plot_dialog(input_file=p),
        )
        self._folder_tree.rename_folder_requested.connect(self._rename_folder)
        self._folder_tree.delete_folders_requested.connect(self._delete_folders)
        self._folder_tree.clear_root_folders_requested.connect(self._clear_root_folders)
        self._folder_tree.itemExpanded.connect(self._on_folder_tree_expanded)
        self._folder_tree.itemCollapsed.connect(lambda _item: self._schedule_persist_workspace())
        self._apply_browser_panel_font()
        self._fs_watcher = QFileSystemWatcher(self)
        self._fs_watcher.directoryChanged.connect(self._on_watched_directory_changed)
        self._folder_persist_timer = QTimer(self)
        self._folder_persist_timer.setSingleShot(True)
        self._folder_persist_timer.setInterval(250)
        self._folder_persist_timer.timeout.connect(self._persist_workspace)
        self._folder_tree_restoring = False
        self._hidden_root_folders = load_hidden_root_folders()

        self._build_dock_panels()

        status = QStatusBar()
        self.setStatusBar(status)
        self._task_progress = TaskProgressPanel()
        status.addPermanentWidget(self._task_progress)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setToolTip("Stop the currently running job")
        self._stop_btn.setMaximumHeight(22)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_current_job)
        status.addPermanentWidget(self._stop_btn)
        self._build_menu()
        self._install_shortcuts()
        self._restore_window_layout()
        QTimer.singleShot(0, self._complete_deferred_startup)

    def _complete_deferred_startup(self) -> None:
        """Load workspace folders after the window is shown (avoids blocking startup)."""
        self._load_initial_roots()
        self._apply_startup_folder()
        self._update_directory_watchers()
        self._update_status()

    def _update_directory_watchers(self) -> None:
        watched: set[str] = set()
        for root in self._collect_root_folders():
            if root.is_dir():
                watched.add(str(root.expanduser().resolve()))
        if self._current_folder and self._current_folder.is_dir():
            watched.add(str(self._current_folder.expanduser().resolve()))

        current = set(self._fs_watcher.directories())
        to_remove = sorted(current - watched)
        if to_remove:
            self._fs_watcher.removePaths(to_remove)
        to_add = sorted(watched - current)
        if to_add:
            self._fs_watcher.addPaths(to_add)

    def _on_watched_directory_changed(self, directory: str) -> None:
        changed = Path(directory).expanduser().resolve()
        refreshed = False

        if changed.is_dir():
            # Refresh only the changed directory. Rebuilding the parent folder's
            # children (e.g. after saving a GFF in a subfolder) destroys the
            # selected tree item and Qt jumps to the next folder below.
            refreshed = self._refresh_subfolders_under(changed) is not None

        if not refreshed:
            self._refresh_tree()

        if self._current_folder and self._current_folder.is_dir():
            self._populate_file_list(self._current_folder, open_preview=False)
        self._update_directory_watchers()

    def _restore_window_layout(self) -> None:
        settings = QSettings()
        settings.beginGroup("mainwindow")
        state = settings.value("dock_state_v2") or settings.value("toolbars_state")
        settings.endGroup()
        if state:
            self.restoreState(state)
        self._ensure_preview_dock_attached()
        preview_ok = (
            self._dock_preview is not None
            and self._dock_preview.isVisible()
            and self._dock_preview.widget() is self._preview_host
            and self._preview_tabs is not None
        )
        if not preview_ok:
            self._reset_dock_layout()
        else:
            self._ensure_preview_visible()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self._any_background_job_running():
            self._shutdown_background_threads()
        self._persist_workspace()
        settings = QSettings()
        settings.beginGroup("mainwindow")
        settings.setValue("dock_state_v2", self.saveState())
        settings.setValue("toolbars_state", self.saveState())
        settings.endGroup()
        super().closeEvent(event)

    def _shutdown_background_threads(self, *, wait_ms: int = 30_000) -> None:
        """Stop and join background QThreads before teardown or window close."""
        self._job_cancel.request()
        self._queued_genome_map_jobs.clear()

        threads: list[QThread] = []
        for attr in ("_worker_thread", "_genome_map_thread", "_benchmark_thread"):
            thread = getattr(self, attr, None)
            if isinstance(thread, QThread):
                threads.append(thread)

        for thread in threads:
            if thread.isRunning():
                thread.requestInterruption()
                thread.quit()

        for thread in threads:
            if not thread.isRunning():
                continue
            if thread.wait(wait_ms):
                continue
            logger.warning("Background thread did not stop in time; terminating.")
            thread.terminate()
            thread.wait(3000)

        self._worker = None
        self._worker_thread = None
        self._genome_map_worker = None
        self._genome_map_thread = None
        self._benchmark_worker = None
        self._benchmark_thread = None
        self._job_running = False
        if self._task_progress is not None:
            self._task_progress.reset()
        if self._stop_btn is not None:
            self._stop_btn.setEnabled(False)

    @staticmethod
    def _job_display_title(job_title: str) -> str:
        if job_title.startswith("plugin:"):
            plugin = get_registry().get(job_title[len("plugin:") :])
            if plugin is not None:
                return plugin.label
        key = job_title.strip().lower().replace(" ", "_")
        return _JOB_DISPLAY_TITLES.get(key, job_title)

    @staticmethod
    def _parse_progress_filename(label: str) -> str:
        if ": " in label:
            part = label.split(": ", 1)[1]
        elif label.lower().startswith("aligning "):
            part = label[9:]
        else:
            return ""
        part = part.removesuffix("…").strip()
        if not part or part.lower() in {"finished", "alignment finished."}:
            return ""
        return part

    def _running_job_title(self, job_title: str) -> str:
        display = self._job_display_title(job_title)
        if display.lower().startswith("running "):
            return display if display.endswith("…") else f"{display}…"
        return f"Running {display}…"

    def _show_job_progress(self, job_title: str, total_steps: int) -> None:
        self._job_running = True
        self.statusBar().clearMessage()
        if self._task_progress is not None:
            self._task_progress.start(self._running_job_title(job_title), total_steps)
        if self._stop_btn is not None:
            self._stop_btn.setEnabled(True)

    def _hide_job_progress(self) -> None:
        self._job_running = False
        if self._task_progress is not None:
            self._task_progress.reset()
        if self._stop_btn is not None and self._genome_map_thread is None and self._benchmark_thread is None:
            self._stop_btn.setEnabled(False)

    def _set_status_message(self, message: str, timeout: int = 0) -> None:
        if self._job_running:
            return
        self.statusBar().showMessage(message, timeout)

    def _build_dock_panels(self) -> None:
        folders_panel = QWidget()
        folders_layout = QVBoxLayout(folders_panel)
        folders_layout.setContentsMargins(6, 4, 6, 4)
        folders_layout.setSpacing(2)
        folders_layout.addWidget(self._folder_tree, stretch=1)
        self._folder_tree.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        left_btns = QHBoxLayout()
        left_btns.setContentsMargins(0, 0, 0, 0)
        left_btns.setSpacing(4)
        add_btn = QPushButton("Add Folder")
        add_btn.clicked.connect(self._pick_and_add_folder)
        create_btn = QPushButton("Create Folder")
        create_btn.clicked.connect(self._create_folder)
        folder_btn_h = 22
        add_btn.setMaximumHeight(folder_btn_h)
        create_btn.setMaximumHeight(folder_btn_h)
        left_btns.addWidget(add_btn)
        left_btns.addWidget(create_btn)
        folders_layout.addLayout(left_btns)

        files_panel = QWidget()
        files_layout = QVBoxLayout(files_panel)
        files_layout.setContentsMargins(6, 4, 6, 4)
        files_layout.setSpacing(2)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(4)
        self._file_filter = QLineEdit()
        self._file_filter.setObjectName("FileFilter")
        self._file_filter.setPlaceholderText("Filter by name…")
        self._file_filter.setClearButtonEnabled(True)
        self._file_filter.textChanged.connect(self._apply_file_filter)
        self._file_sort_combo = QComboBox()
        self._file_sort_combo.setObjectName("FileSortCombo")
        self._file_sort_combo.setToolTip("Sort order for files in the current folder")
        self._file_sort_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents,
        )
        self._file_sort_combo.blockSignals(True)
        for mode, label in file_sort_mode_labels():
            self._file_sort_combo.addItem(label)
            row = self._file_sort_combo.count() - 1
            self._file_sort_combo.setItemData(
                row,
                mode.value,
                Qt.ItemDataRole.UserRole,
            )
        saved_sort = load_file_sort_mode()
        sort_index = self._file_sort_combo.findData(
            saved_sort.value,
            Qt.ItemDataRole.UserRole,
        )
        if sort_index >= 0:
            self._file_sort_combo.setCurrentIndex(sort_index)
        self._file_sort_combo.blockSignals(False)
        self._file_sort_combo.currentIndexChanged.connect(self._on_file_sort_changed)
        sort_labels = [label for _, label in file_sort_mode_labels()]
        longest_label = max(sort_labels, key=len)
        self._file_sort_combo.setMinimumContentsLength(len(longest_label))
        fm = QFontMetrics(self._file_sort_combo.font())
        sort_min_w = max(
            118,
            fm.horizontalAdvance(longest_label) + 36,
            fm.boundingRect(longest_label).width() + 36,
        )
        self._file_sort_combo.setMinimumWidth(sort_min_w)
        sort_view = self._file_sort_combo.view()
        if sort_view is not None:
            sort_view.setMinimumWidth(sort_min_w)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("FileRefreshButton")
        refresh_btn.setToolTip("Reload file list (F5)")
        refresh_btn.clicked.connect(self._refresh_current_folder)
        compact_h = 26
        compact_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        for widget in (self._file_filter, self._file_sort_combo, refresh_btn):
            widget.setFixedHeight(compact_h)
            widget.setSizePolicy(compact_policy)
        filter_row.addWidget(self._file_filter, stretch=1)
        filter_row.addWidget(self._file_sort_combo)
        filter_row.addWidget(refresh_btn)

        files_layout.addLayout(filter_row)

        from teviewer.widgets.preview_controls import PreviewZoomBar

        self._preview_host = QWidget()
        preview_layout = QVBoxLayout(self._preview_host)
        preview_layout.setContentsMargins(4, 2, 4, 2)
        preview_layout.setSpacing(2)
        self._preview_zoom_bar = PreviewZoomBar(self._preview_host)
        preview_layout.addWidget(self._preview_zoom_bar)
        self._preview_tabs = PreviewTabWidget(zoom_bar=self._preview_zoom_bar)
        set_genome_path_provider(self._genome_path_resolved)
        set_igv_extra_annotations_provider(self._igv_extra_annotations_for_alignment)
        self._preview_tabs.annotationsSaved.connect(self._on_preview_annotations_saved)
        preview_layout.addWidget(self._preview_tabs, stretch=1)
        self._preview_zoom_bar.setVisible(True)
        self._preview_host.setMinimumHeight(200)

        files_layout.addWidget(self._file_list, stretch=1)
        self._file_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        central = QWidget()
        central.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        central.setMaximumSize(0, 0)
        self.setCentralWidget(central)

        self._dock_folders = self._make_dock("Folders", folders_panel, fixed=False)
        self._dock_files = self._make_dock("Files", files_panel, fixed=False)
        self._dock_preview = self._make_dock("Preview", self._preview_host, fixed=False)
        self._dock_files.setMinimumWidth(280)
        self._dock_preview.setMinimumWidth(360)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._dock_folders)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._dock_files)
        self.splitDockWidget(self._dock_folders, self._dock_files, Qt.Orientation.Vertical)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock_preview)
        self._apply_default_dock_sizes()

    def _make_dock(self, title: str, widget: QWidget, *, fixed: bool) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"dock_{title.lower()}")
        dock.setWidget(widget)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        if fixed:
            dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        else:
            dock.setFeatures(
                QDockWidget.DockWidgetFeature.DockWidgetMovable
                | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                | QDockWidget.DockWidgetFeature.DockWidgetClosable
            )
        return dock

    def _apply_default_dock_sizes(self) -> None:
        if self._dock_folders and self._dock_files:
            self.resizeDocks(
                [self._dock_folders, self._dock_files],
                [220, 320],
                Qt.Orientation.Vertical,
            )
        if self._dock_files and self._dock_preview:
            self.resizeDocks(
                [self._dock_files, self._dock_preview],
                [280, 1120],
                Qt.Orientation.Horizontal,
            )
        self._ensure_preview_visible()

    def _reset_dock_layout(self) -> None:
        for dock in (self._dock_folders, self._dock_files, self._dock_preview):
            if dock is None:
                continue
            dock.setFloating(False)
            self.removeDockWidget(dock)
        if self._dock_folders and self._dock_files and self._dock_preview:
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._dock_folders)
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._dock_files)
            self.splitDockWidget(self._dock_folders, self._dock_files, Qt.Orientation.Vertical)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock_preview)
            self._dock_folders.show()
            self._dock_files.show()
            self._ensure_preview_visible()
            self._apply_default_dock_sizes()

    @staticmethod
    def _settings_menu_hint() -> str:
        if platform.system() == "Darwin":
            return "TEviewer → Setting"
        return "File → Setting"

    @staticmethod
    def _genome_menu_hint() -> str:
        return "File → Define genome"

    def _populate_align_menu(self, menu: QMenu) -> None:
        menu.addAction("Align with default parameters", self._run_align_default)
        menu.addAction(
            "Align all selected in one combined MSA",
            self._align_selected_combined,
        )
        menu.addSeparator()
        menu.addAction("Change alignment parameters", self._modify_align_parameters)

    def _populate_blast_menu(self, menu: QMenu) -> None:
        menu.addAction("Blast with default parameters", self._run_blast)
        menu.addSeparator()
        menu.addAction("Change blast parameters", self._change_blast_parameters)

    def _populate_te_visualization_menu(self, menu: QMenu) -> None:
        menu.addAction("TE density plot", self._open_te_density_plot_dialog)
        menu.addAction("TE divergence plot", self._open_te_divergence_plot_dialog)

    def _populate_benchmarking_menu(self, menu: QMenu) -> None:
        menu.addAction("Confusion matrix benchmarker", self._open_confusion_matrix_benchmark)
        menu.addAction("TE library benchmarker", self._open_te_library_benchmark)

    def _populate_extend_menu(self, menu: QMenu) -> None:
        menu.addAction("Extend with default parameters", self._run_extend)
        menu.addAction("Extend with different distances", self._extend_with_different_distances)
        menu.addSeparator()
        menu.addAction("Change extension parameters", self._modify_extend_parameters)

    def _populate_tsd_search_menu(self, menu: QMenu) -> None:
        menu.addAction("TSD search with default parameters", self._run_tsd_search)
        menu.addSeparator()
        menu.addAction("Change TSD search parameters", self._modify_tsd_search_parameters)

    def _populate_teaid_menu(self, menu: QMenu) -> None:
        menu.addAction("TEAid with default parameters", self._run_teaid)
        menu.addSeparator()
        menu.addAction("Change TEAid parameters", self._modify_teaid_parameters)

    def _populate_msa_clean_menu(self, menu: QMenu) -> None:
        menu.addAction("MSA clean with default parameters", self._run_default_msa_clean)
        menu.addSeparator()
        menu.addAction("Change MSA clean parameters", self._modify_msa_clean_parameters)
        menu.addSeparator()
        menu.addAction(
            "Remove gappy columns",
            lambda: self._apply_msa_clean("msa_clean_gappy"),
        )
        menu.addAction(
            "Clean row with divergence",
            lambda: self._apply_msa_clean("msa_clean_div"),
        )
        menu.addAction(
            "Clean row with gap",
            lambda: self._apply_msa_clean("msa_clean_gap"),
        )
        self._add_msa_clean_menu_action(
            menu,
            "Clean row and column",
            "msa_clean_row_col",
        )

    def _populate_consensus_menu(self, menu: QMenu) -> None:
        menu.addAction("Consensus with default parameters", self._run_consensus)
        menu.addSeparator()
        menu.addAction("Change consensus parameters", self._modify_consensus_parameters)

    def _populate_flexidot_menu(self, menu: QMenu) -> None:
        menu.addAction("Flexidot with default parameters", self._run_flexidot_combined)
        menu.addAction(
            "Run for each file separately",
            lambda: self._apply_function(
                "flexidot",
                flexidot_combined=False,
                flexidot_options=self._flexidot_options,
            ),
        )
        menu.addSeparator()
        menu.addAction("Change Flexidot parameters", self._modify_flexidot_parameters)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        genome_action = file_menu.addAction("Define &genome", self._open_set_genome)
        genome_action.setShortcut(QKeySequence("Ctrl+Shift+G"))
        genome_action.setStatusTip("Set reference or pan-genome FASTA files")
        define_db_action = file_menu.addAction("Define &database", self._open_define_database)
        define_db_action.setStatusTip("Configure CDD and similarity annotation databases")
        file_menu.addAction("Restore deleted &files", self._restore_removed_folders)
        file_menu.addSeparator()
        settings_action = QAction("&Setting", self)
        settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        settings_action.setStatusTip("Preview defaults, BLAST options, and batch workers")
        settings_action.triggered.connect(self._open_settings)
        settings_action.setMenuRole(
            QAction.MenuRole.PreferencesRole
            if platform.system() == "Darwin"
            else QAction.MenuRole.ApplicationSpecificRole
        )
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        file_menu.addAction("&Quit", self.close, "Ctrl+Q")

        seq_menu = self.menuBar().addMenu("&Sequence")
        seq_menu.addAction("Open in &AliView", self._open_selected_in_aliview)
        seq_menu.addSeparator()
        self._populate_blast_menu(seq_menu.addMenu("&Blast"))
        self._populate_align_menu(seq_menu.addMenu("&Align"))
        self._populate_extend_menu(seq_menu.addMenu("&Extend"))
        self._populate_tsd_search_menu(seq_menu.addMenu("TSD &search"))
        self._populate_teaid_menu(seq_menu.addMenu("&TEAid"))
        self._populate_msa_clean_menu(seq_menu.addMenu("MSA &clean"))
        self._populate_consensus_menu(seq_menu.addMenu("&Consensus"))
        self._populate_flexidot_menu(seq_menu.addMenu("&Flexidot"))
        seq_menu.addAction("TE &annotation", self._run_te_annotation)
        self._populate_te_visualization_menu(seq_menu.addMenu("TE &visualization"))
        self._populate_benchmarking_menu(seq_menu.addMenu("&Benchmarking"))

        plugins_menu = self.menuBar().addMenu("&Plugins")
        self._plugins_menu = plugins_menu
        plugins_menu.addAction("Manage plugins…", self._open_plugin_manager)
        plugins_menu.addAction("Design your plugin…", self._open_command_plugin_designer)
        plugins_menu.addSeparator()
        self._populate_plugins_menu_actions()

        view_menu = self.menuBar().addMenu("&View")
        for dock in (self._dock_folders, self._dock_files, self._dock_preview):
            if dock is not None:
                view_menu.addAction(dock.toggleViewAction())
        view_menu.addSeparator()
        view_menu.addAction("Reset panel &layout", self._reset_dock_layout)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction("&About TEviewer", self._show_about)
        self._rebuild_top_toolbar()

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+Shift+G"), self, self._open_set_genome)
        QShortcut(QKeySequence.StandardKey.Refresh, self, self._refresh_current_folder)
        QShortcut(QKeySequence(Qt.Key.Key_F5), self, self._refresh_current_folder)
        QShortcut(QKeySequence.StandardKey.Find, self, lambda: self._file_filter.setFocus())
        for key in (QKeySequence.StandardKey.Delete, QKeySequence(Qt.Key.Key_Backspace)):
            shortcut = QShortcut(key, self._file_list)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self._delete_selected_shortcut)

    def _delete_selected_shortcut(self) -> None:
        paths = self._selected_files()
        if paths:
            self._delete_selected_files(paths)

    def _apply_toolbar_theme(self) -> None:
        size = self._toolbar_font_size
        self._toolbar_font = QFont(self.font())
        self._toolbar_font.setPointSize(size)
        self._toolbar_font.setBold(False)
        self.setStyleSheet(
            application_stylesheet(
                toolbar_font_pt=size,
                browser_panel_font_pt=self._browser_panel_font_size,
            )
        )
        if self._functions_toolbar is not None:
            self._compact_functions_toolbar(self._functions_toolbar)

    def _apply_browser_panel_font(self) -> None:
        self._browser_panel_font = QFont(self.font())
        self._browser_panel_font.setPointSize(self._browser_panel_font_size)
        self._browser_panel_font.setBold(False)
        if hasattr(self, "_folder_tree"):
            self._folder_tree.setFont(self._browser_panel_font)
            self._folder_tree.resizeColumnToContents(0)
        if hasattr(self, "_file_list"):
            self._file_list.setFont(self._browser_panel_font)

    def _rebuild_top_toolbar(self) -> None:
        if self._functions_toolbar is not None:
            self.removeToolBar(self._functions_toolbar)
            self._functions_toolbar.deleteLater()
            self._functions_toolbar = None
        self._job_toolbar_actions = []
        self._build_top_toolbar()

    def _toolbar_button_height(self) -> int:
        return QFontMetrics(self._toolbar_font).height() + 4

    def _compact_functions_toolbar(self, bar: QToolBar) -> None:
        bar.setContentsMargins(0, 0, 0, 0)
        btn_h = self._toolbar_button_height()
        bar.setFixedHeight(btn_h + 2)
        for widget in bar.findChildren(QToolButton):
            widget.setFixedHeight(btn_h)
            widget.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Fixed,
            )

    def _style_toolbar_button(self, widget) -> None:
        widget.setFont(self._toolbar_font)
        widget.setFixedHeight(self._toolbar_button_height())
        widget.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

    def _add_toolbar_text_action(
        self,
        bar,
        text: str,
        slot,
        *,
        job_action: bool = True,
        tooltip: str = "",
    ) -> QAction:
        action = QAction(text, self)
        action.setFont(self._toolbar_font)
        if tooltip:
            action.setToolTip(tooltip)
        action.triggered.connect(slot)
        bar.addAction(action)
        widget = bar.widgetForAction(action)
        if widget is not None:
            self._style_toolbar_button(widget)
        if job_action:
            self._job_toolbar_actions.append(action)
        return action

    def _add_toolbar_text_menu_button(
        self,
        bar,
        text: str,
        default_slot,
        menu_builder,
        *,
        tooltip: str = "",
        menu_popup: bool = False,
    ) -> QToolButton:
        """Text-only toolbar button; click or right-click opens a menu when configured."""
        btn = QToolButton(bar)
        btn.setText(text)
        if tooltip:
            btn.setToolTip(tooltip)
        self._style_toolbar_button(btn)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

        if menu_popup:
            def _show_menu_on_click() -> None:
                menu = QMenu(btn)
                menu_builder(menu)
                menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

            btn.clicked.connect(_show_menu_on_click)
        else:
            btn.clicked.connect(default_slot)
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

            def _show_menu(position) -> None:
                menu = QMenu(btn)
                menu_builder(menu)
                menu.exec(btn.mapToGlobal(position))

            btn.customContextMenuRequested.connect(_show_menu)

        bar.addWidget(btn)
        self._job_toolbar_actions.append(btn)
        return btn

    def _build_top_toolbar(self) -> None:
        bar = QToolBar("Functions", self)
        bar.setObjectName("FunctionsToolBar")
        bar.setMovable(True)
        bar.setFloatable(True)
        bar.setAllowedAreas(
            Qt.ToolBarArea.TopToolBarArea
            | Qt.ToolBarArea.BottomToolBarArea
            | Qt.ToolBarArea.LeftToolBarArea
            | Qt.ToolBarArea.RightToolBarArea
        )
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)
        self._functions_toolbar = bar

        for tool_id in self._toolbar_order:
            self._add_toolbar_tool(bar, tool_id)
        self._compact_functions_toolbar(bar)

    def _add_toolbar_tool(self, bar, tool_id: str) -> None:
        tip = _TOOLBAR_TOOLTIPS.get(tool_id, "")
        if tool_id == "_sep1":
            bar.addSeparator()
        elif tool_id == "aliview":
            self._add_toolbar_text_action(
                bar,
                "AliView",
                self._open_selected_in_aliview,
                job_action=False,
                tooltip=tip,
            )
        elif tool_id == "align":
            self._add_toolbar_text_menu_button(
                bar,
                "Align",
                self._run_align_default,
                self._populate_align_menu,
                tooltip=tip,
            )
        elif tool_id == "blast":
            self._add_toolbar_text_menu_button(
                bar,
                "Blast",
                self._run_blast,
                self._populate_blast_menu,
                tooltip=tip,
            )
        elif tool_id == "te_genome_map":
            self._add_toolbar_text_menu_button(
                bar,
                "TE visualization",
                self._open_te_density_plot_dialog,
                self._populate_te_visualization_menu,
                tooltip=tip,
                menu_popup=True,
            )
        elif tool_id == "te_benchmark":
            self._add_toolbar_text_menu_button(
                bar,
                "Benchmarking",
                self._open_confusion_matrix_benchmark,
                self._populate_benchmarking_menu,
                tooltip=tip,
                menu_popup=True,
            )
        elif tool_id == "te_divergence_plot":
            self._add_toolbar_text_action(
                bar,
                "TE divergence",
                self._open_te_divergence_plot_dialog,
                tooltip=tip,
            )
        elif tool_id == "extend":
            self._add_toolbar_text_menu_button(
                bar,
                "Extend",
                self._run_extend,
                self._populate_extend_menu,
                tooltip=tip,
            )
        elif tool_id == "teaid":
            self._add_toolbar_text_menu_button(
                bar,
                "TEAid",
                self._run_teaid,
                self._populate_teaid_menu,
                tooltip=tip,
            )
        elif tool_id == "msa_clean":
            self._add_toolbar_text_menu_button(
                bar,
                "MSA clean",
                self._run_default_msa_clean,
                self._populate_msa_clean_menu,
                tooltip=tip,
            )
        elif tool_id == "consensus":
            self._add_toolbar_text_menu_button(
                bar,
                "Consensus",
                self._run_consensus,
                self._populate_consensus_menu,
                tooltip=tip,
            )
        elif tool_id == "flexidot":
            self._add_toolbar_text_menu_button(
                bar,
                "Flexidot",
                self._run_flexidot_combined,
                self._populate_flexidot_menu,
                tooltip=tip,
            )
        elif tool_id == "_sep_plugins":
            bar.addSeparator()
        elif tool_id.startswith("plugin:"):
            plugin_id = tool_id[len("plugin:") :]
            plugin = self._plugin_registry.get(plugin_id)
            if plugin is None:
                return
            self._add_toolbar_text_action(
                bar,
                plugin.label,
                lambda checked=False, pid=plugin.id: self._apply_plugin(pid),
                tooltip=plugin.tooltip or tip,
            )

    def _select_all_fasta_in_folder(self) -> None:
        if self._file_list.count() == 0:
            return
        self._file_list.clearSelection()
        selected = 0
        for index in range(self._file_list.count()):
            item = self._file_list.item(index)
            raw = item.data(ROLE_PATH)
            if not raw:
                continue
            path = Path(str(raw))
            if path.suffix.lower() in _FASTA_SUFFIXES:
                item.setSelected(True)
                selected += 1
        self._set_status_message(f"Selected {selected} FASTA file(s)", 4000)

    def _reveal_in_file_manager(self, paths: list[Path]) -> None:
        if paths:
            reveal_in_file_manager(paths[0])

    def _genome_path_resolved(self) -> Path | None:
        if not self._project.genome_file:
            return None
        try:
            path = self._project.genome_file.expanduser().resolve()
        except OSError:
            return None
        return path if path.is_file() else None

    def _pan_genome_names(self) -> list[str]:
        if self._project.is_pan_genome_mode:
            return [entry.name for entry in self._project.pan_genomes]
        return []

    def _job_total_steps(
        self,
        func_name: str,
        seq_files: list[Path],
        job_kwargs: dict[str, Any],
    ) -> int:
        n = len(seq_files)
        if not self._project.is_pan_genome_mode:
            if func_name == "flexidot" and n > 1 and job_kwargs.get("flexidot_combined", True):
                return 1
            if func_name.startswith("plugin:"):
                plugin = self._plugin_registry.get(func_name[len("plugin:") :])
                if plugin is not None and not plugin.supports_parallel:
                    return n
            return n
        pan_n = len(self._project.pan_genomes)
        if func_name in {"blast", "teaid"}:
            return n * pan_n
        if func_name == "flexidot":
            if n > 1 and job_kwargs.get("flexidot_combined", True):
                return pan_n
            return n * pan_n
        if func_name.startswith("plugin:"):
            plugin = self._plugin_registry.get(func_name[len("plugin:") :])
            if plugin is not None and not plugin.supports_parallel:
                return n
            return n
        return n

    def _prepare_configured_genomes(self) -> None:
        targets = self._project.genome_targets()
        if not targets:
            return
        self._set_status_message("Preparing genome index and chromosome sizes…", 0)
        QApplication.processEvents()
        messages: list[str] = []
        ok_all = True
        for label, path in targets:
            ok, msg = ensure_genome_artifacts(
                path,
                use_system_blast=self._project.use_system_blast,
            )
            ok_all = ok_all and ok
            messages.append(f"{label}: {msg}" if label else msg)
        if ok_all:
            preview = "; ".join(messages[:3])
            if len(messages) > 3:
                preview += f" (+{len(messages) - 3} more)"
            self._set_status_message(preview, 10000)
        else:
            QMessageBox.warning(self, "Genome preparation", "\n".join(messages))
            self._set_status_message("Genome preparation incomplete", 8000)

    def _on_genome_changed(self, genome_before: Path | None, genome_after: Path | None) -> None:
        invalidate_genome_chromosome_cache()
        self._genome_chrom_names_cache = []
        self._genome_chrom_sizes_cache = {}
        self._genome_chrom_cache_path = None
        if (
            not self._project.is_pan_genome_mode
            and genome_after is not None
            and genome_after.is_file()
        ):
            new_chroms = set(chromosome_names_from_genome(genome_after))
            old_filter = self._te_genome_map_options.chromosomes_only
            if new_chroms and old_filter and not _map_chromosome_filter_to_genome(
                old_filter, list(new_chroms)
            ):
                self._te_genome_map_options = replace(
                    self._te_genome_map_options,
                    chromosomes_only=None,
                )
                save_te_genome_map_options(self._te_genome_map_options)
                self._set_status_message(
                    "Cleared TE genome map chromosome filter (previous genome).",
                    8000,
                )
        if self._project.has_genome_configured():
            self._prepare_configured_genomes()
        self._update_status()

    def _open_set_genome(self) -> None:
        if self._genome_dialog is not None:
            self._genome_dialog.raise_()
            self._genome_dialog.activateWindow()
            return
        self._persist_workspace()
        genome_before = self._genome_path_resolved()
        dialog = GenomeDialog(
            self._project,
            self,
            selected_paths=self._selected_genome_fastas(),
        )
        self._genome_dialog = dialog
        dialog.finished.connect(self._on_genome_dialog_finished)
        dialog.show()

    def _selected_genome_fastas(self) -> list[Path]:
        return [
            p.expanduser().resolve()
            for p in self._selected_files()
            if is_genome_fasta(p)
        ]

    def _on_genome_dialog_finished(self, result: int) -> None:
        dialog = self._genome_dialog
        self._genome_dialog = None
        if dialog is None or result != int(QDialog.DialogCode.Accepted):
            return
        genome_before = self._genome_path_resolved()
        self._project = dialog.apply_to_project()
        genome_after = self._genome_path_resolved()
        self._on_genome_changed(genome_before, genome_after)
        self._persist_workspace()
        if self._project.is_pan_genome_mode:
            self._set_status_message(
                f"Pan-genome mode: {len(self._project.pan_genomes)} genome(s)",
                8000,
            )
        elif genome_after is not None:
            self._set_status_message(f"Genome: {genome_after.name}", 8000)
        else:
            self._set_status_message("Genome cleared", 5000)

    def _open_define_database(self) -> None:
        if self._define_database_dialog is not None:
            self._define_database_dialog.raise_()
            self._define_database_dialog.activateWindow()
            return
        dialog = DefineDatabaseDialog(self._project, self)
        self._define_database_dialog = dialog
        dialog.setModal(False)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dialog.finished.connect(self._on_define_database_finished)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        # Do not auto-fill from the currently selected Files-panel item.
        # The dialog should only fill paths on an explicit Files-panel click.

    def _on_define_database_finished(self, result: int) -> None:
        dialog = self._define_database_dialog
        self._define_database_dialog = None
        if dialog is None:
            return
        if result == int(QDialog.DialogCode.Accepted):
            self._project = dialog.project()
            self._persist_workspace()
            if self._preview_tabs is not None:
                self._preview_tabs.refresh_similarity_databases()
        dialog.deleteLater()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            self._project,
            self,
            plugin_registry=self._plugin_registry,
            toolbar_order=self._toolbar_order,
        )
        if dialog.exec():
            self._project = dialog.apply_to_project()
            self._persist_workspace()
            old_font_size = self._toolbar_font_size
            old_browser_size = self._browser_panel_font_size
            self._toolbar_order, new_font_size = dialog.apply_toolbar_settings()
            self._toolbar_font_size = new_font_size
            new_browser_size = load_browser_panel_font_size()
            self._browser_panel_font_size = new_browser_size
            if new_font_size != old_font_size or new_browser_size != old_browser_size:
                self._apply_toolbar_theme()
            if new_browser_size != old_browser_size:
                self._apply_browser_panel_font()
            self._rebuild_top_toolbar()
            self._update_status()
            if self._preview_tabs is not None:
                from teviewer.widgets.preview_zoom import (
                    load_preview_fit_mode,
                    load_preview_zoom_percent,
                )

                self._preview_tabs.zoom_bar.set_values(
                    load_preview_zoom_percent(),
                    load_preview_fit_mode(),
                )
                self._preview_tabs._apply_zoom_to_current_tab()
                from teviewer.widgets.preview_zoom import load_preview_font_size

                self._preview_tabs.apply_preview_font_size(load_preview_font_size())
                self._preview_tabs.refresh_nucleotide_color_scheme()

    def _collect_root_folders(self) -> list[Path]:
        roots: list[Path] = []
        for index in range(self._folder_tree.topLevelItemCount()):
            item = self._folder_tree.topLevelItem(index)
            raw = item.data(0, ROLE_PATH)
            if not raw:
                continue
            path = Path(str(raw)).expanduser().resolve()
            if path.is_dir():
                roots.append(path)
        return roots

    def _schedule_persist_workspace(self) -> None:
        if self._folder_tree_restoring:
            return
        self._folder_persist_timer.start()

    def _collect_expanded_folders(self) -> list[Path]:
        expanded: list[Path] = []
        seen: set[str] = set()

        def walk(item: QTreeWidgetItem) -> None:
            if item.isExpanded():
                raw = item.data(0, ROLE_PATH)
                if raw:
                    path = Path(str(raw)).expanduser().resolve()
                    if path.is_dir():
                        key = str(path)
                        if key not in seen:
                            seen.add(key)
                            expanded.append(path)
            for index in range(item.childCount()):
                walk(item.child(index))

        for index in range(self._folder_tree.topLevelItemCount()):
            walk(self._folder_tree.topLevelItem(index))
        return expanded

    def _apply_expanded_folders(self, folders: list[Path]) -> None:
        if not folders:
            for index in range(self._folder_tree.topLevelItemCount()):
                self._folder_tree.topLevelItem(index).setExpanded(True)
            return

        ordered = sorted(
            {path.expanduser().resolve() for path in folders if path.is_dir()},
            key=lambda path: (len(path.parts), str(path).lower()),
        )
        self._folder_tree.blockSignals(True)
        self._folder_tree_restoring = True
        try:
            for index in range(self._folder_tree.topLevelItemCount()):
                self._folder_tree.topLevelItem(index).setExpanded(False)

            def collapse_children(item: QTreeWidgetItem) -> None:
                for child_index in range(item.childCount()):
                    child = item.child(child_index)
                    child.setExpanded(False)
                    collapse_children(child)

            for index in range(self._folder_tree.topLevelItemCount()):
                collapse_children(self._folder_tree.topLevelItem(index))

            for folder in ordered:
                item = self._ensure_folder_tree_path(folder)
                if item is not None:
                    item.setExpanded(True)
        finally:
            self._folder_tree_restoring = False
            self._folder_tree.blockSignals(False)

    def _persist_workspace(self) -> None:
        roots = self._collect_root_folders()
        if roots and self._project.input_dir is None:
            self._project.input_dir = roots[0]
        save_workspace(
            self._project,
            root_folders=roots,
            last_folder=self._current_folder,
            expanded_folders=self._collect_expanded_folders(),
        )

    def _load_initial_roots(self, reset: bool = False) -> None:
        if reset:
            self._folder_tree.clear()
        roots = load_root_folders()
        if not roots and self._project.input_dir and self._project.input_dir.is_dir():
            roots = [self._project.input_dir.resolve()]
        saved_last = load_last_folder()
        saved_expanded = load_expanded_folders()
        for folder in roots:
            self._add_root_folder(
                folder,
                unhide=True,
                persist=False,
                select=False,
                expand_root=False,
            )
        self._strip_lazy_folder_placeholders()
        self._apply_expanded_folders(saved_expanded)
        if saved_last is not None:
            self._saved_last_folder = saved_last
        elif roots:
            self._saved_last_folder = roots[0].resolve()

    def _strip_lazy_folder_placeholders(self) -> None:
        def walk(item: QTreeWidgetItem) -> None:
            for index in range(item.childCount() - 1, -1, -1):
                child = item.child(index)
                if self._is_lazy_folder_placeholder(child):
                    item.removeChild(child)
                else:
                    walk(child)

        for index in range(self._folder_tree.topLevelItemCount()):
            walk(self._folder_tree.topLevelItem(index))

    def _apply_startup_folder(self) -> None:
        folder = self._saved_last_folder
        self._saved_last_folder = None
        if folder is not None and folder.is_dir():
            self._navigate_to_folder(folder)
            self._persist_workspace()

    def _is_root_hidden(self, folder: Path) -> bool:
        return str(folder.expanduser().resolve()) in self._hidden_root_folders

    def _pick_and_add_folder(self) -> None:
        start = str(Path.home())
        if self._current_folder and self._current_folder.is_dir():
            start = str(self._current_folder)
        picked = QFileDialog.getExistingDirectory(self, "Select folder", start)
        if picked:
            self._add_root_folder(Path(picked), unhide=True)

    def _add_root_folder(
        self,
        folder: Path,
        *,
        unhide: bool = False,
        persist: bool = True,
        select: bool = True,
        expand_root: bool = True,
    ) -> None:
        folder = folder.expanduser().resolve()
        if not folder.is_dir():
            return
        if unhide:
            self._hidden_root_folders = unhide_root_folder(self._hidden_root_folders, folder)
        elif self._is_root_hidden(folder):
            return
        for i in range(self._folder_tree.topLevelItemCount()):
            item = self._folder_tree.topLevelItem(i)
            if Path(str(item.data(0, ROLE_PATH))) == folder:
                if select:
                    self._folder_tree.setCurrentItem(item)
                    self._on_folder_selected(folder)
                return
        root = QTreeWidgetItem([folder.name])
        root.setData(0, ROLE_PATH, str(folder))
        root.setToolTip(0, str(folder))
        apply_folder_item_color(root, folder)
        self._folder_tree.addTopLevelItem(root)
        self._populate_subfolders(folder, root)
        self._set_folder_expandable(root, folder)
        self._folder_tree.resizeColumnToContents(0)
        root.setExpanded(expand_root)
        if select:
            self._folder_tree.setCurrentItem(root)
            self._on_folder_selected(folder)
        if self._folder_tree.topLevelItemCount() == 1 and self._project.input_dir is None:
            self._project.input_dir = folder
        if persist:
            self._persist_workspace()

    def _on_folder_tree_expanded(self, item: QTreeWidgetItem) -> None:
        self._populate_folder_tree_children(item)
        self._schedule_persist_workspace()

    @staticmethod
    def _is_lazy_folder_placeholder(item: QTreeWidgetItem) -> bool:
        return bool(item.data(0, ROLE_LAZY_PLACEHOLDER))

    @staticmethod
    def _is_intermediate_teaid_folder(name: str) -> bool:
        return name.endswith("_self_blast")

    def _list_subfolders(self, folder: Path) -> list[Path]:
        try:
            return sorted(
                [
                    p
                    for p in folder.iterdir()
                    if p.is_dir()
                    and not p.name.startswith(".")
                    and not self._is_intermediate_teaid_folder(p.name)
                ],
                key=lambda p: p.name.lower(),
            )
        except OSError:
            return []

    @staticmethod
    def _folder_has_subfolders(folder: Path) -> bool:
        try:
            for entry in folder.iterdir():
                if (
                    entry.is_dir()
                    and not entry.name.startswith(".")
                    and not MainWindow._is_intermediate_teaid_folder(entry.name)
                ):
                    return True
        except OSError:
            return False
        return False

    def _populate_folder_tree_children(self, item: QTreeWidgetItem) -> None:
        if item.childCount() > 0:
            if item.childCount() == 1 and self._is_lazy_folder_placeholder(item.child(0)):
                item.removeChild(item.child(0))
            else:
                return
        raw = item.data(0, ROLE_PATH)
        if not raw:
            return
        folder = Path(str(raw)).expanduser().resolve()
        if not folder.is_dir():
            return
        self._populate_subfolders(folder, item)

    def _set_folder_expandable(self, item: QTreeWidgetItem, folder: Path) -> None:
        if self._folder_has_subfolders(folder):
            item.setChildIndicatorPolicy(
                QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            )
        else:
            item.setChildIndicatorPolicy(
                QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicatorWhenChildless
            )

    def _populate_subfolders(self, folder: Path, parent: QTreeWidgetItem) -> None:
        for child in self._list_subfolders(folder):
            item = QTreeWidgetItem([child.name])
            item.setData(0, ROLE_PATH, str(child))
            item.setToolTip(0, str(child))
            apply_folder_item_color(item, child)
            parent.addChild(item)
            self._set_folder_expandable(item, child)
        self._folder_tree.resizeColumnToContents(0)

    def _ensure_folder_tree_path(self, folder: Path) -> QTreeWidgetItem | None:
        folder = folder.expanduser().resolve()
        found = self._find_tree_item_for_path(folder)
        if found is not None:
            return found
        for index in range(self._folder_tree.topLevelItemCount()):
            root_item = self._folder_tree.topLevelItem(index)
            raw = root_item.data(0, ROLE_PATH)
            if not raw:
                continue
            root_path = Path(str(raw)).expanduser().resolve()
            try:
                rel_parts = folder.relative_to(root_path).parts
            except ValueError:
                continue
            current_item = root_item
            current_path = root_path
            for part in rel_parts:
                self._populate_folder_tree_children(current_item)
                current_path = current_path / part
                child = self._find_tree_item_for_path(current_path)
                if child is None:
                    break
                current_item = child
            else:
                return self._find_tree_item_for_path(folder)
        return None

    def _find_tree_item_for_path(self, folder: Path) -> QTreeWidgetItem | None:
        folder = folder.expanduser().resolve()

        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if self._is_lazy_folder_placeholder(item):
                return None
            raw = item.data(0, ROLE_PATH)
            if not raw:
                return None
            if Path(str(raw)).expanduser().resolve() == folder:
                return item
            for index in range(item.childCount()):
                found = walk(item.child(index))
                if found is not None:
                    return found
            return None

        for index in range(self._folder_tree.topLevelItemCount()):
            found = walk(self._folder_tree.topLevelItem(index))
            if found is not None:
                return found
        return None

    def _refresh_subfolders_under(self, parent_folder: Path) -> QTreeWidgetItem | None:
        parent_folder = parent_folder.expanduser().resolve()
        item = self._find_tree_item_for_path(parent_folder)
        if item is None:
            return None
        keep_folder = (
            self._current_folder.expanduser().resolve()
            if self._current_folder is not None
            else None
        )
        while item.childCount():
            item.removeChild(item.child(0))
        self._populate_subfolders(parent_folder, item)
        item.setExpanded(True)
        self._folder_tree.resizeColumnToContents(0)
        if keep_folder is not None:
            keep_item = self._find_tree_item_for_path(keep_folder)
            if keep_item is not None:
                self._folder_tree.blockSignals(True)
                self._folder_tree.setCurrentItem(keep_item)
                self._folder_tree.blockSignals(False)
        return item

    def _ensure_folder_visible_in_tree(self, folder: Path) -> QTreeWidgetItem | None:
        return self._ensure_folder_tree_path(folder)

    def _navigate_to_folder(
        self,
        folder: Path,
        *,
        new_outputs: list[Path] | None = None,
        source_files: list[Path] | None = None,
    ) -> None:
        folder = folder.expanduser().resolve()
        self._ensure_folder_visible_in_tree(folder)
        item = self._find_tree_item_for_path(folder)
        if item is not None:
            parent = item.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
            self._folder_tree.blockSignals(True)
            self._folder_tree.setCurrentItem(item)
            self._folder_tree.scrollToItem(item)
            self._folder_tree.blockSignals(False)
        self._populate_file_list(folder, new_outputs=new_outputs, source_files=source_files)

    def _on_folder_selected(self, folder: Path) -> None:
        self._populate_file_list(folder)
        self._update_directory_watchers()
        self._persist_workspace()
        # Do not auto-fill plugin inputs from the current selection when the
        # folder changes; let explicit Files-panel clicks drive the sync.

    def _refresh_current_folder(self) -> None:
        if self._current_folder and self._current_folder.is_dir():
            self._populate_file_list(self._current_folder)
        else:
            self._set_status_message("Select a folder first", 4000)

    def _on_preview_annotations_saved(self, path: object) -> None:
        if not isinstance(path, Path) or not self._current_folder:
            return
        resolved = path.expanduser().resolve()
        if resolved.parent != self._current_folder:
            return
        # Saving annotations should not rebuild the whole folder tree.
        # But the newly written GFF3 should appear in the Files list immediately,
        # without the panel jumping to a different folder.

        selected_key = str(resolved)
        prev_key: str | None = None
        current = self._file_list.currentItem()
        if current is not None:
            prev_path = self._preview_path_from_item(current)
            if prev_path is not None:
                prev_key = str(prev_path.expanduser().resolve())

        def _find_item_for_key(key: str) -> QListWidgetItem | None:
            for index in range(self._file_list.count()):
                item = self._file_list.item(index)
                raw = item.data(ROLE_PATH)
                if not raw:
                    continue
                if str(Path(str(raw)).expanduser().resolve()) == key:
                    return item
            return None

        found_item = _find_item_for_key(selected_key)

        self._file_list.blockSignals(True)
        try:
            reveal_item: QListWidgetItem | None = None
            if found_item is not None:
                reveal_item = found_item
            else:
                # Refresh only the current folder's file list so the saved GFF3 shows up.
                # open_preview=False prevents any preview tab changes.
                self._populate_file_list(self._current_folder, open_preview=False)
                reveal_item = _find_item_for_key(selected_key)
                if reveal_item is None and prev_key is not None:
                    reveal_item = _find_item_for_key(prev_key)

            if reveal_item is not None:
                self._style_new_output_item(reveal_item)
                self._reveal_file_list_item(
                    reveal_item,
                    scroll_hint=QAbstractItemView.ScrollHint.EnsureVisible,
                )
        finally:
            self._file_list.blockSignals(False)

        # Ensure focus returns to the preview area after saving.
        if not self._file_list.hasFocus():
            QTimer.singleShot(0, self._focus_preview_widget)

    def _focus_preview_widget(self) -> None:
        if self._preview_tabs is None:
            return
        current = self._preview_tabs.currentWidget()
        if current is not None:
            current.setFocus(Qt.FocusReason.OtherFocusReason)

    def _current_file_sort_mode(self) -> FileSortMode:
        index = self._file_sort_combo.currentIndex()
        if index < 0:
            return FileSortMode.NAME
        raw = self._file_sort_combo.itemData(index, Qt.ItemDataRole.UserRole)
        if raw is None:
            return FileSortMode.NAME
        try:
            return FileSortMode(str(raw))
        except ValueError:
            return FileSortMode.NAME

    def _on_file_sort_changed(self, _index: int) -> None:
        save_file_sort_mode(self._current_file_sort_mode())
        self._apply_file_filter()

    def _apply_file_filter(self) -> None:
        if not self._current_folder:
            return
        query = self._file_filter.text().strip().lower()
        self._file_list.clear()
        visible: list[Path] = []
        for file_path in self._cached_folder_files:
            if query and query not in file_path.name.lower():
                continue
            visible.append(file_path)

        visible = sort_file_paths(visible, self._current_file_sort_mode())

        for file_path in visible:
            item = QListWidgetItem(file_path.name)
            item.setData(ROLE_PATH, str(file_path))
            key = str(file_path.resolve())
            if key in self._highlight_output_keys:
                self._style_new_output_item(item)
            elif key in self._highlight_source_keys:
                self._style_source_file_item(item)
            self._file_list.addItem(item)

        if not visible and self._cached_folder_files:
            placeholder = QListWidgetItem("(no files match filter)")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._file_list.addItem(placeholder)
        elif not self._cached_folder_files:
            placeholder = QListWidgetItem("(empty folder)")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._file_list.addItem(placeholder)

        self._sync_files_status(len(visible), len(self._cached_folder_files))

    def _sync_files_status(self, visible_count: int, total_count: int) -> None:
        if self._job_running or not self._current_folder:
            return
        if visible_count == total_count:
            count = f"{total_count} files"
        else:
            count = f"{visible_count} of {total_count} files"
        genome = (
            "genome set"
            if self._project.genome_file and self._project.genome_file.is_file()
            else "genome not set"
        )
        self.statusBar().showMessage(
            f"{self._current_folder.name} · {count} · {genome}",
            0,
        )

    def _populate_file_list(
        self,
        folder: Path,
        *,
        new_outputs: list[Path] | None = None,
        source_files: list[Path] | None = None,
        open_preview: bool = True,
    ) -> None:
        target_folder = folder.expanduser().resolve()
        prev_folder = self._current_folder
        same_folder = False
        if prev_folder is not None:
            try:
                same_folder = prev_folder.expanduser().resolve() == target_folder
            except OSError:
                same_folder = False
        self._current_folder = target_folder
        try:
            self._cached_folder_files = [
                p
                for p in self._current_folder.iterdir()
                if p.is_file()
                and not p.name.startswith(".")
                and not is_teviewer_hits_cache_file(p)
                and not is_sequence_map_hidden_file(p)
                and not is_flexidot_extra_plot_file(p)
            ]
        except OSError as exc:
            self._cached_folder_files = []
            self._file_list.clear()
            self._set_status_message(f"Cannot read folder: {exc}", 6000)
            return

        self._highlight_output_keys = set()
        self._highlight_source_keys = set()
        highlight_paths: list[Path] = []

        def _track(path: Path, *, as_output: bool) -> None:
            resolved = path.expanduser().resolve()
            if resolved.parent != self._current_folder:
                return
            key = str(resolved)
            if as_output:
                self._highlight_output_keys.add(key)
            else:
                self._highlight_source_keys.add(key)
            highlight_paths.append(resolved)

        if new_outputs:
            for path in new_outputs:
                _track(path, as_output=True)
        if source_files:
            for path in source_files:
                _track(path, as_output=False)

        preserve_ui = same_folder
        prev_key: str | None = None
        prev_scroll: int | None = None
        if preserve_ui:
            current = self._file_list.currentItem()
            if current is not None:
                prev_path = self._preview_path_from_item(current)
                if prev_path is not None:
                    prev_key = str(prev_path.expanduser().resolve())
            prev_scroll = int(self._file_list.verticalScrollBar().value())

        self._file_list.blockSignals(True)
        self._apply_file_filter()

        if highlight_paths:
            self._select_and_scroll_outputs(highlight_paths, open_preview=False)
            n_out = len(self._highlight_output_keys)
            n_src = len(self._highlight_source_keys)
            names = ", ".join(
                Path(k).name for k in list(self._highlight_output_keys)[:3]
            )
            msg = f"Highlighted {n_out} new output(s) and {n_src} input(s)"
            if names:
                msg += f" (e.g. {names})"
            self._set_status_message(msg, 12000)
        else:
            self._sync_files_status(
                len(self._cached_folder_files),
                len(self._cached_folder_files),
            )

        # When refreshing the same folder without new outputs, keep scroll stable.
        if preserve_ui and not highlight_paths:
            if prev_key:
                match: QListWidgetItem | None = None
                for index in range(self._file_list.count()):
                    item = self._file_list.item(index)
                    raw = item.data(ROLE_PATH)
                    if not raw:
                        continue
                    if str(Path(str(raw)).expanduser().resolve()) == prev_key:
                        match = item
                        break
                if match is not None:
                    match.setSelected(True)
                    self._file_list.setCurrentItem(match)
            if prev_scroll is not None:
                vsb = self._file_list.verticalScrollBar()
                vsb.setValue(min(prev_scroll, vsb.maximum()))
        self._file_list.blockSignals(False)
        if highlight_paths and open_preview:
            self._open_best_preview_path(highlight_paths)

    def _style_new_output_item(self, item: QListWidgetItem) -> None:
        item.setBackground(QBrush(_NEW_OUTPUT_BG))
        item.setForeground(QBrush(_NEW_OUTPUT_FG))
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setToolTip("New output from the last job")

    def _style_source_file_item(self, item: QListWidgetItem) -> None:
        item.setBackground(QBrush(_SOURCE_BG))
        item.setForeground(QBrush(_SOURCE_FG))
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setToolTip("Input file used for the last job")

    def _reveal_file_list_item(
        self,
        item: QListWidgetItem,
        *,
        scroll_hint: QAbstractItemView.ScrollHint = QAbstractItemView.ScrollHint.EnsureVisible,
    ) -> None:
        """Select a file in the list and scroll it into view (default: bottom)."""
        item.setSelected(True)
        self._file_list.setCurrentItem(item)
        self._file_list.scrollToItem(item, scroll_hint)

    def _select_and_scroll_outputs(
        self,
        paths: list[Path],
        *,
        open_preview: bool = True,
    ) -> None:
        path_set = {str(p.expanduser().resolve()) for p in paths}
        first_item: QListWidgetItem | None = None
        preferred_item: QListWidgetItem | None = None
        preferred_rank = 99
        self._file_list.clearSelection()
        for index in range(self._file_list.count()):
            item = self._file_list.item(index)
            raw = item.data(ROLE_PATH)
            if raw and str(Path(str(raw)).resolve()) in path_set:
                item.setSelected(True)
                if first_item is None:
                    first_item = item
                candidate = Path(str(raw)).resolve()
                rank = preview_path_priority(candidate)
                if rank < preferred_rank:
                    preferred_rank = rank
                    preferred_item = item
        focus_item = preferred_item or first_item
        if focus_item is not None:
            self._reveal_file_list_item(
                focus_item,
                scroll_hint=QAbstractItemView.ScrollHint.EnsureVisible,
            )
        if open_preview and focus_item is not None:
            path = self._preview_path_from_item(focus_item)
            if path is not None and is_previewable_file(path):
                self._open_file_in_preview(path)

    def _open_best_preview_path(self, paths: list[Path]) -> None:
        candidates = [
            p.expanduser().resolve()
            for p in paths
            if p.is_file() and is_previewable_file(p)
        ]
        if not candidates:
            return
        best = min(candidates, key=preview_path_priority)
        self._open_file_in_preview(best)

    def _select_path_in_file_list(self, path: Path) -> None:
        """Select one file in the list (used after creating a genome map HTML)."""
        resolved = path.expanduser().resolve()
        key = str(resolved)
        for index in range(self._file_list.count()):
            item = self._file_list.item(index)
            raw = item.data(ROLE_PATH)
            if raw and str(Path(str(raw)).resolve()) == key:
                self._reveal_file_list_item(
                    item,
                    scroll_hint=QAbstractItemView.ScrollHint.EnsureVisible,
                )
                return

    def _selected_files(self) -> list[Path]:
        files = []
        items = self._file_list.selectedItems()
        if not items:
            current = self._file_list.currentItem()
            if current is not None:
                items = [current]
        for item in items:
            raw = item.data(ROLE_PATH)
            if not raw:
                continue
            path = Path(str(raw))
            if path.is_file():
                files.append(path)
        return files

    def _preview_path_from_item(self, item: QListWidgetItem | None) -> Path | None:
        if item is None:
            return None
        raw = item.data(ROLE_PATH)
        if not raw:
            return None
        path = Path(str(raw))
        return path if path.is_file() else None

    def _igv_extra_annotations_for_alignment(self, _alignment: Path) -> list[Path]:
        """GFF/GTF files explicitly selected in the Files panel."""
        gff_suffixes = {".gff", ".gff3", ".gtf"}
        paths: list[Path] = []
        for path in self._selected_files():
            if path.suffix.lower() in gff_suffixes and path.is_file():
                paths.append(path.expanduser().resolve())
        return paths

    def _open_file_in_preview(self, path: Path) -> None:
        self._open_preview_tab(path, replace=True)
        if is_alignment_preview_file(path):
            annotations = discover_igv_annotations(path)
            if annotations:
                names = ", ".join(item.name for item in annotations[:3])
                extra = f" (+{len(annotations) - 3} more)" if len(annotations) > 3 else ""
                self._set_status_message(
                    f"Alignment: {path.name} — igv.js with {names}{extra}",
                    8000,
                )
            else:
                self._set_status_message(
                    f"Alignment: {path.name} (igv.js — add .gff/.gff3/.gtf in the same folder)",
                    8000,
                )
        elif is_genome_map_html_file(path):
            self._set_status_message(
                f"Genome map: {path.name} (TE density along chromosomes, Mbp axis)",
                8000,
            )
        elif is_divergence_plot_html_file(path):
            self._set_status_message(
                f"Divergence plot: {path.name} (not a genome map — X = divergence)",
                8000,
            )
        else:
            self._set_status_message(path.name, 4000)

    def _on_file_current_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        # If a non-modal dialog is currently open that expects panel clicks to
        # fill its path fields, do not steal the click by opening preview.
        if self._define_database_dialog is not None and self._define_database_dialog.isVisible():
            return
        if self._te_viz_input_dialog is not None and self._te_viz_input_dialog.isVisible():
            return
        if self._plugin_run_dialog is not None and self._plugin_run_dialog.isVisible():
            return

        path = self._preview_path_from_item(current)
        if path is not None and is_previewable_file(path):
            QTimer.singleShot(0, lambda p=path: self._open_file_in_preview(p))

    def _resolve_te_masking_input_path(self, path: Path) -> Path | None:
        if is_te_hit_table_file(path):
            return path.expanduser().resolve()
        return None

    def _resolve_te_consensus_input_path(self, path: Path) -> Path | None:
        if self._is_fasta_file(path):
            return path.expanduser().resolve()
        return None

    def _resolve_te_hit_input_path(self, path: Path) -> Path | None:
        resolved = self._resolve_te_masking_input_path(path)
        if resolved is not None:
            return resolved
        if path.suffix.lower() in _FASTA_SUFFIXES:
            blast_txt = find_blast_table_for_query(path)
            if blast_txt is not None:
                return blast_txt.expanduser().resolve()
        return None

    def _resolve_gene_input_path(self, path: Path) -> Path | None:
        if is_gene_annotation_file(path):
            return path.expanduser().resolve()
        return None

    def _resolve_methylation_input_path(self, path: Path) -> Path | None:
        if is_bismark_cov_file(path):
            return path.expanduser().resolve()
        return None

    def _guess_gene_input_file(self) -> Path | None:
        for path in self._selected_files():
            resolved = self._resolve_gene_input_path(path)
            if resolved is not None:
                return resolved
        current = self._file_list.currentItem()
        if current is not None:
            path = self._preview_path_from_item(current)
            if path is not None:
                return self._resolve_gene_input_path(path)
        return None

    def _guess_methylation_input_file(self) -> Path | None:
        for path in self._selected_files():
            resolved = self._resolve_methylation_input_path(path)
            if resolved is not None:
                return resolved
        current = self._file_list.currentItem()
        if current is not None:
            path = self._preview_path_from_item(current)
            if path is not None:
                return self._resolve_methylation_input_path(path)
        return None

    def _guess_te_masking_input_file(self) -> Path | None:
        for path in self._selected_files():
            resolved = self._resolve_te_masking_input_path(path)
            if resolved is not None:
                return resolved
        current = self._file_list.currentItem()
        if current is not None:
            path = self._preview_path_from_item(current)
            if path is not None:
                return self._resolve_te_masking_input_path(path)
        return None

    def _guess_te_consensus_input_file(self) -> Path | None:
        for path in self._selected_files():
            resolved = self._resolve_te_consensus_input_path(path)
            if resolved is not None:
                return resolved
        current = self._file_list.currentItem()
        if current is not None:
            path = self._preview_path_from_item(current)
            if path is not None:
                return self._resolve_te_consensus_input_path(path)
        return None

    def _guess_te_hit_input_file(self) -> Path | None:
        for path in self._selected_files():
            resolved = self._resolve_te_hit_input_path(path)
            if resolved is not None:
                return resolved
        current = self._file_list.currentItem()
        if current is not None:
            path = self._preview_path_from_item(current)
            if path is not None:
                return self._resolve_te_hit_input_path(path)
        return None

    def _sync_dialog_input_from_files(self) -> None:
        self._sync_te_viz_dialog_input_from_files()
        self._sync_define_database_dialog_from_files()
        self._sync_plugin_run_dialog_from_files()

    def _panel_path_for_plugin_sync(self) -> Path | None:
        items = self._file_list.selectedItems()
        if not items:
            current = self._file_list.currentItem()
            if current is not None:
                items = [current]
        for item in items:
            raw = item.data(ROLE_PATH)
            if not raw:
                continue
            path = Path(str(raw)).expanduser()
            if path.exists():
                return path.resolve()
        folder_item = self._folder_tree.currentItem()
        if folder_item is not None:
            raw = folder_item.data(0, ROLE_PATH)
            if raw:
                folder = Path(str(raw)).expanduser()
                if folder.is_dir():
                    return folder.resolve()
        return None

    def _sync_plugin_run_dialog_from_files(self, path: Path | None = None) -> None:
        if path is None:
            return
        dialog = self._plugin_run_dialog
        if dialog is not None and dialog.isVisible():
            dialog.apply_path_from_panel(path)
            dialog.raise_()
            return
        for plugin in self._plugin_registry.all_plugins():
            if not isinstance(plugin, UserCommandPlugin):
                continue
            active = plugin._active_run_dialog
            if isinstance(active, UserCommandRunDialog) and active.isVisible():
                active.apply_path_from_panel(path)
                active.raise_()
                return

    def _guess_database_input_file(self) -> Path | None:
        for path in self._selected_files():
            if resolve_panel_database_path(path) is not None:
                return path.expanduser().resolve()
        current = self._file_list.currentItem()
        if current is not None:
            path = self._preview_path_from_item(current)
            if path is not None and resolve_panel_database_path(path) is not None:
                return path.expanduser().resolve()
        return None

    def _sync_define_database_dialog_from_files(self, clicked_path: Path | None = None) -> None:
        dialog = self._define_database_dialog
        if dialog is None or not dialog.isVisible() or clicked_path is None:
            return
        if dialog.apply_file_from_panel(clicked_path):
            self._schedule_raise_define_database_dialog()

    def _schedule_raise_define_database_dialog(self) -> None:
        QTimer.singleShot(0, self._raise_define_database_dialog)

    def _raise_define_database_dialog(self) -> None:
        dialog = self._define_database_dialog
        if dialog is None:
            return
        # Avoid stealing focus / flashing if already visible; the textbox change
        # from panel click is enough.
        if dialog.isVisible():
            return
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _sync_te_viz_dialog_input_from_files(self, clicked_path: Path | None = None) -> None:
        dialog = self._te_viz_input_dialog
        if dialog is None or not dialog.isVisible() or clicked_path is None:
            return
        if hasattr(dialog, "apply_path_from_panel"):
            if dialog.apply_path_from_panel(clicked_path):
                self._schedule_raise_te_viz_dialog()
            return
        filled = False
        masking_path = self._resolve_te_masking_input_path(clicked_path)
        if masking_path is not None and hasattr(dialog, "set_te_input_file"):
            filled = dialog.set_te_input_file(masking_path) or filled
        consensus_path = self._resolve_te_consensus_input_path(clicked_path)
        if consensus_path is not None and hasattr(dialog, "set_te_consensus_input_file"):
            filled = dialog.set_te_consensus_input_file(consensus_path) or filled
        gene_path = self._resolve_gene_input_path(clicked_path)
        if gene_path is not None and hasattr(dialog, "set_gene_input_file"):
            filled = dialog.set_gene_input_file(gene_path) or filled
        methylation_path = self._resolve_methylation_input_path(clicked_path)
        if methylation_path is not None and hasattr(dialog, "set_methylation_input_file"):
            filled = dialog.set_methylation_input_file(methylation_path) or filled
        if filled:
            self._schedule_raise_te_viz_dialog()

    def _schedule_raise_te_viz_dialog(self) -> None:
        QTimer.singleShot(0, self._raise_te_viz_dialog)

    def _raise_te_viz_dialog(self) -> None:
        dialog = self._te_viz_input_dialog
        if dialog is None:
            return
        # Avoid stealing focus / flashing if already visible.
        if dialog.isVisible():
            return
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _present_te_viz_dialog(self, dialog: QDialog, on_accept) -> None:
        """Show a non-modal TE settings dialog so the Files panel stays clickable."""
        if self._te_viz_input_dialog is not None:
            self._te_viz_input_dialog.close()
        self._te_viz_input_dialog = dialog
        dialog.setModal(False)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        def _finished(code: int) -> None:
            if self._te_viz_input_dialog is dialog:
                self._te_viz_input_dialog = None
            if code == int(QDialog.DialogCode.Accepted):
                on_accept(dialog)
            dialog.deleteLater()

        dialog.finished.connect(_finished)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        # Do not auto-fill from the currently selected Files-panel item.
        # The user should click a file in the panel to fill inputs.

    def _is_fasta_file(self, path: Path) -> bool:
        return path.suffix.lower() in {".fa", ".fasta", ".fna", ".fas"}

    def _validate_te_consensus_fastas(self, fasta_paths: list[Path]) -> list[Path] | None:
        if not fasta_paths:
            return []
        resolved: list[Path] = []
        for fasta_path in fasta_paths:
            fasta_path = fasta_path.expanduser()
            if not fasta_path.is_file():
                QMessageBox.warning(
                    self,
                    "TE visualization",
                    f"TE consensus file not found:\n{fasta_path}",
                )
                return None
            if not self._is_fasta_file(fasta_path):
                QMessageBox.warning(
                    self,
                    "TE visualization",
                    "Each TE consensus input must be a FASTA file (.fasta / .fa / .fna).",
                )
                return None
            resolved.append(fasta_path.resolve())
        return resolved

    def _validate_gene_input_files(self, gene_paths: list[Path]) -> list[Path] | None:
        if not gene_paths:
            return []
        resolved: list[Path] = []
        for gene_path in gene_paths:
            validated = self._validate_gene_input_file(gene_path)
            if validated is None:
                return None
            resolved.append(validated)
        return resolved

    def _validate_methylation_input_files(
        self, methylation_paths: list[Path]
    ) -> list[Path] | None:
        if not methylation_paths:
            return []
        resolved: list[Path] = []
        for meth_path in methylation_paths:
            if meth_path is None or not meth_path.is_file():
                QMessageBox.warning(
                    self,
                    "TE visualization",
                    f"DNA methylation file not found:\n{meth_path}",
                )
                return None
            if not is_bismark_cov_file(meth_path):
                QMessageBox.warning(
                    self,
                    "TE visualization",
                    "Each DNA methylation input must be a Bismark coverage file "
                    "(*.cov or *.cov.gz).",
                )
                return None
            resolved.append(meth_path.expanduser().resolve())
        return resolved

    def _resolve_te_viz_hit_paths_and_kinds(
        self,
        pending: _PendingTeVizBuild,
    ) -> tuple[list[Path], list[str]] | None:
        te_paths = list(pending.masking_paths)
        kinds = [TE_INPUT_KIND_MASKING] * len(pending.masking_paths)
        for fasta in pending.consensus_fastas:
            blast_txt = find_blast_table_for_query(fasta)
            if blast_txt is None:
                return None
            te_paths.append(blast_txt.expanduser().resolve())
            kinds.append(TE_INPUT_KIND_CONSENSUS)
        return te_paths, kinds

    def _resolve_te_viz_hit_paths(self, pending: _PendingTeVizBuild) -> list[Path] | None:
        resolved = self._resolve_te_viz_hit_paths_and_kinds(pending)
        if resolved is None:
            return None
        return resolved[0]

    def _start_te_viz_from_dialog(
        self,
        *,
        masking_paths: list[Path],
        consensus_fastas: list[Path],
        gene_paths: list[Path],
        methylation_paths: list[Path],
        map_options: TeGenomeMapOptions,
    ) -> None:
        need_blast = [
            fasta
            for fasta in consensus_fastas
            if find_blast_table_for_query(fasta) is None
        ]
        if need_blast:
            self._pending_te_viz = _PendingTeVizBuild(
                masking_paths=list(masking_paths),
                consensus_fastas=list(consensus_fastas),
                gene_paths=list(gene_paths),
                methylation_paths=list(methylation_paths),
                map_options=map_options,
            )
            self._pending_te_genome_map = map_options
            self._pending_te_genome_map_fastas = list(need_blast)
            self._set_status_message("Running Blast on TE consensus, then TE genome map…", 0)
            self._apply_function(
                "blast",
                preselected=need_blast,
                blast_options=self._blast_options,
            )
            return
        te_paths = list(masking_paths)
        te_kinds = [TE_INPUT_KIND_MASKING] * len(masking_paths)
        for fasta in consensus_fastas:
            blast_txt = find_blast_table_for_query(fasta)
            if blast_txt is not None:
                te_paths.append(blast_txt.expanduser().resolve())
                te_kinds.append(TE_INPUT_KIND_CONSENSUS)
        self._open_blast_genome_map(
            te_paths,
            gene_files=gene_paths,
            methylation_files=methylation_paths,
            te_input_kinds=te_kinds,
            map_options=map_options,
        )

    def _validate_te_hit_inputs(self, hit_paths: list[Path]) -> list[Path] | None:
        if not hit_paths:
            QMessageBox.warning(
                self,
                "TE visualization",
                "Select at least one RepeatMasker .out or BLAST hit table.",
            )
            return None
        resolved: list[Path] = []
        for hit_path in hit_paths:
            if hit_path is None or not hit_path.is_file():
                QMessageBox.warning(
                    self,
                    "TE visualization",
                    f"TE input file not found:\n{hit_path}",
                )
                return None
            if not is_te_hit_table_file(hit_path):
                QMessageBox.warning(
                    self,
                    "TE visualization",
                    "Each TE input must be a RepeatMasker .out file or BLAST hit table (*_blast.txt).",
                )
                return None
            resolved.append(hit_path.expanduser().resolve())
        return resolved

    def _validate_gene_input_file(self, gene_path: Path | None) -> Path | None:
        if gene_path is None:
            return None
        gene_path = gene_path.expanduser()
        if not gene_path.is_file():
            QMessageBox.warning(
                self,
                "TE visualization",
                f"Annotation file not found:\n{gene_path}",
            )
            return None
        if not is_gene_annotation_file(gene_path):
            QMessageBox.warning(
                self,
                "TE visualization",
                "Annotation input must be a GFF, GFF3, GTF, BED, or VCF file.",
            )
            return None
        return gene_path.resolve()

    def _validate_te_hit_input(self, hit_path: Path | None) -> Path | None:
        if hit_path is None or not hit_path.is_file():
            QMessageBox.warning(
                self,
                "TE visualization",
                "Select a RepeatMasker .out or BLAST hit table.",
            )
            return None
        if not is_te_hit_table_file(hit_path):
            QMessageBox.warning(
                self,
                "TE visualization",
                "Input must be a RepeatMasker .out file or BLAST hit table (*_blast.txt).",
            )
            return None
        return hit_path.expanduser().resolve()

    def _on_file_item_clicked(self, item: QListWidgetItem) -> None:
        raw = item.data(ROLE_PATH)
        panel_path: Path | None = None
        if raw:
            candidate = Path(str(raw)).expanduser()
            if candidate.exists():
                panel_path = candidate.resolve()
            preview_path = self._preview_path_from_item(item)
            if preview_path is not None:
                if self._genome_dialog is not None and is_genome_fasta(preview_path):
                    self._genome_dialog.apply_file_from_panel(preview_path)
        if panel_path is not None:
            self._sync_plugin_run_dialog_from_files(panel_path)
            self._sync_te_viz_dialog_input_from_files(panel_path)
            self._sync_define_database_dialog_from_files(panel_path)

    def _on_file_double_clicked(self, item: QListWidgetItem) -> None:
        raw = item.data(ROLE_PATH)
        if not raw:
            return
        path = Path(str(raw))
        if path.suffix.lower() in _FASTA_SUFFIXES:
            self._open_in_sequence_viewer(path)
            return
        self._open_preview_tab(path, replace=True)

    def _open_selected_in_aliview(self) -> None:
        selected = self._selected_files()
        fasta = [p for p in selected if p.suffix.lower() in _FASTA_SUFFIXES]
        if not fasta:
            QMessageBox.information(
                self,
                "No FASTA selected",
                "Select one or more .fa / .fasta files to open in AliView.",
            )
            return
        for path in fasta:
            self._open_in_sequence_viewer(path)

    def _open_selected_in_text_editor(self, paths: list[Path] | None = None) -> None:
        selected = list(paths) if paths else self._selected_files()
        files = [p.expanduser().resolve() for p in selected if p.is_file()]
        if not files:
            QMessageBox.information(
                self,
                "No file selected",
                "Select one or more files to open in a text editor.",
            )
            return
        opened = 0
        failures: list[str] = []
        for path in files:
            try:
                open_in_text_editor(path)
                opened += 1
            except (OSError, RuntimeError) as exc:
                failures.append(f"{path.name}: {exc}")
        if opened:
            label = files[0].name if opened == 1 else f"{opened} files"
            self._set_status_message(f"Opened in text editor: {label}", 5000)
        if failures:
            QMessageBox.warning(
                self,
                "Text editor",
                "Some files could not be opened:\n\n" + "\n".join(failures[:6]),
            )

    def _open_in_sequence_viewer(self, path: Path) -> None:
        try:
            open_fasta(path, use_system_viewer=self._project.use_system_sequence_viewer)
            self._set_status_message(f"Opened: {path.name}", 5000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Open sequence failed", str(exc))

    def _run_align_default(self) -> None:
        """Toolbar click: align each selected FASTA separately."""
        self._align_sequences()

    def _count_sequences_in_fastas(self, seq_files: list[Path]) -> int:
        total = 0
        for path in seq_files:
            try:
                total += count_fasta_sequences(path)
            except Exception:  # noqa: BLE001
                continue
        return total

    def _align_selected_combined(self) -> None:
        """One-off combined MSA from all sequences in the selection."""
        selected = self._selected_files()
        seq_files = [p for p in selected if p.suffix.lower() in _FASTA_SUFFIXES]
        if not seq_files:
            QMessageBox.information(
                self,
                "Align combined",
                "Select one or more FASTA files with at least two sequences total.",
            )
            return
        if self._count_sequences_in_fastas(seq_files) < 2:
            QMessageBox.information(
                self,
                "Align combined",
                "Need at least two sequences in the selected FASTA file(s) "
                "for a combined alignment.",
            )
            return
        self._align_sequences(seq_files, mode=ALIGN_MODE_COMBINED)

    def _modify_align_parameters(self) -> None:
        dialog = AlignParamsDialog(
            initial=self._align_options,
            parent=self,
        )
        if dialog.exec():
            self._align_options = dialog.options()
            save_align_options(self._align_options)
            self._set_status_message(
                f"Alignment defaults updated ({self._align_options.backend}, "
                f"{self._align_options.num_threads} threads)",
                6000,
            )

    def _align_sequences(
        self,
        paths: list[Path] | None = None,
        *,
        backend: str | None = None,
        num_threads: int | None = None,
        mode: str | None = None,
    ) -> None:
        opts = self._align_options
        backend = backend if backend is not None else opts.backend
        num_threads = num_threads if num_threads is not None else opts.num_threads
        if mode is None:
            mode = "one_by_one"

        selected = paths or self._selected_files()
        seq_files = [p for p in selected if p.suffix.lower() in _FASTA_SUFFIXES]
        if not seq_files:
            QMessageBox.information(
                self,
                "No FASTA selected",
                "Select one or more .fa / .fasta files for alignment.",
            )
            return
        if mode == ALIGN_MODE_COMBINED and self._count_sequences_in_fastas(seq_files) < 2:
            QMessageBox.information(
                self,
                "Align combined",
                "Need at least two sequences in the selected FASTA file(s).",
            )
            return
        if backend == "mafft" and "mafft" not in alignment_backends():
            QMessageBox.warning(
                self,
                "MAFFT not found",
                "Install MAFFT on your PATH (e.g. conda install -c bioconda mafft).",
            )
            return
        if backend == "clustalo" and "clustalo" not in alignment_backends():
            QMessageBox.warning(
                self,
                "Clustal Omega not found",
                "Install Clustal Omega (e.g. conda install -c bioconda clustalo).",
            )
            return
        title = {
            "mafft": "Align (MAFFT)",
            "clustalo": "Align (Clustal)",
            "auto": "Align",
        }.get(backend, "Align")
        if mode == ALIGN_MODE_COMBINED:
            title = f"{title} (combined)"
        total_steps = 1 if mode == ALIGN_MODE_COMBINED else len(seq_files)
        self._start_background_job(
            AlignWorker(
                seq_files,
                backend=backend,
                num_threads=num_threads,
                mode=mode,
                max_workers=self._project.batch_workers,
            ),
            job_title=title,
            total_steps=total_steps,
            source_files=seq_files,
            on_finished=self._on_align_finished,
            on_failed=self._on_align_failed,
        )

    @Slot(list)
    def _on_align_finished(self, created: list) -> None:
        created_paths = [Path(p) for p in created if Path(p).is_file()]
        source_paths = getattr(self, "_last_job_source_files", [])
        if self._current_folder:
            self._populate_file_list(
                self._current_folder,
                new_outputs=created_paths,
                source_files=source_paths,
            )
        self._auto_open_outputs(created_paths)
        names = ", ".join(p.name for p in created_paths[:6])
        if len(created_paths) > 6:
            names += ", …"
        self._set_status_message(
            f"Alignment completed — {len(created_paths)} file(s): {names}",
            12000,
        )

    @Slot(str)
    def _on_align_failed(self, error: str) -> None:
        backends = alignment_backends()
        hint = (
            "Install MAFFT and/or Clustal Omega on PATH.\n"
            f"Detected: {', '.join(backends) if backends else 'none'}"
        )
        QMessageBox.critical(self, "Alignment failed", f"{error}\n\n{hint}")

    def _run_blast(self) -> None:
        self._apply_function("blast", blast_options=self._blast_options)

    def _change_blast_parameters(self) -> None:
        dialog = BlastParamsDialog(initial=self._blast_options, parent=self)
        if dialog.exec():
            self._blast_options = dialog.options()
            save_blast_options(self._blast_options)
            self._set_status_message("Blast parameters updated", 4000)

    def _open_blast_genome_map_from_selection(
        self,
        *,
        map_options: TeGenomeMapOptions | None = None,
    ) -> None:
        selected = self._selected_files()
        if not selected:
            QMessageBox.information(
                self,
                "TE genome map",
                "Select one FASTA (with *_blast.txt) or a hit table (*_blast.txt / RepeatMasker .out).",
            )
            return
        blast_targets: list[Path] = []
        missing_blast_fastas: list[Path] = []
        invalid: list[str] = []
        for path in selected:
            if path.suffix.lower() in _FASTA_SUFFIXES:
                blast_txt = find_blast_table_for_query(path)
                if blast_txt is not None:
                    blast_targets.append(blast_txt)
                else:
                    missing_blast_fastas.append(path)
            elif is_te_hit_table_file(path):
                blast_targets.append(path)
            else:
                invalid.append(path.name)

        if invalid:
            QMessageBox.warning(
                self,
                "TE genome map",
                "Skipped unsupported selections:\n" + "\n".join(invalid[:8]),
            )

        if blast_targets:
            self._enqueue_genome_map_jobs(blast_targets, map_options)
        if missing_blast_fastas:
            self._start_blast_then_te_genome_map(missing_blast_fastas, map_options)
        if not blast_targets and not missing_blast_fastas:
            QMessageBox.warning(
                self,
                "TE genome map",
                "Select FASTA files, *_blast.txt tables, or RepeatMasker .out files.",
            )

    def _enqueue_genome_map_jobs(
        self,
        blast_tables: list[Path],
        map_options: TeGenomeMapOptions | None,
    ) -> None:
        for bt in blast_tables:
            self._queued_genome_map_jobs.append((bt.expanduser().resolve(), map_options))
        self._start_next_genome_map_job()

    def _start_next_genome_map_job(self) -> None:
        if self._genome_map_thread is not None:
            return
        if not self._queued_genome_map_jobs:
            return
        blast_txt, map_options = self._queued_genome_map_jobs.pop(0)
        self._open_blast_genome_map(blast_txt, map_options=map_options)

    def _open_blast_divergence_from_selection(self) -> None:
        selected = self._selected_files()
        if not selected:
            QMessageBox.information(
                self,
                "TE divergence plot",
                "Select one FASTA (with *_blast.txt) or a hit table (*_blast.txt / RepeatMasker .out).",
            )
            return
        if len(selected) > 1:
            QMessageBox.information(
                self,
                "TE divergence plot",
                "Select a single FASTA, BLAST table, or RepeatMasker .out file.",
            )
            return
        path = selected[0]
        if path.suffix.lower() in _FASTA_SUFFIXES:
            blast_txt = find_blast_table_for_query(path)
            if blast_txt is not None:
                self._open_blast_divergence_plot(blast_txt)
            else:
                QMessageBox.warning(
                    self,
                    "TE divergence plot",
                    f"No BLAST table found for:\n{path.name}\n\n"
                    f"Expected {blast_txt_path_for_query(path).name} "
                    f"(or {path.stem}_blast.txt). Run Blast first.",
                )
            return
        if is_te_hit_table_file(path):
            self._open_blast_divergence_plot(path)
            return
        QMessageBox.warning(
            self,
            "TE divergence plot",
            "Select a FASTA with BLAST results, a *_blast.txt table, or a RepeatMasker .out file.",
        )

    def _open_blast_divergence_plot(
        self,
        te_input_files: list[Path] | Path,
        *,
        bin_width: float | None = None,
    ) -> None:
        te_paths = (
            [te_input_files.expanduser().resolve()]
            if isinstance(te_input_files, Path)
            else [p.expanduser().resolve() for p in te_input_files]
        )
        te_paths = [p for p in te_paths if p.is_file()]
        if not te_paths:
            QMessageBox.warning(
                self,
                "TE divergence plot",
                "No TE input files found.\n\nRun Blast or select RepeatMasker .out / BLAST tables.",
            )
            return
        primary = te_paths[0]
        if len(te_paths) == 1:
            label = te_hit_table_stem(primary)
        else:
            label = f"{te_hit_table_stem(primary)} + {len(te_paths) - 1} more"
        bw = bin_width if bin_width is not None else self._te_divergence_plot_options.bin_width
        self._set_status_message("Building TE divergence plot…", 0)
        try:
            html_path = write_blast_divergence_plot_html(
                te_paths,
                query_label=label,
                bin_width=bw,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "TE divergence plot failed", str(exc))
            return
        if html_path is None:
            QMessageBox.warning(self, "TE divergence plot", "Could not build the divergence plot.")
            return
        self._open_divergence_in_preview(html_path)
        outputs = [html_path.resolve()]
        source = self._fasta_for_blast_table(primary) or primary
        if self._current_folder and self._current_folder.resolve() == html_path.parent.resolve():
            self._populate_file_list(html_path.parent.resolve(), new_outputs=outputs, source_files=[source])
        else:
            self._navigate_to_folder(html_path.parent.resolve(), new_outputs=outputs, source_files=[source])
        self._set_status_message(f"TE divergence plot: {html_path.name}", 8000)

    def _open_divergence_in_preview(self, html_path: Path) -> None:
        """Open divergence HTML in Preview with delayed reload for reliability."""
        from teviewer.widgets.preview_tabs import FilePreviewPage

        resolved = html_path.expanduser().resolve()
        if not resolved.is_file():
            return

        def _load() -> None:
            self._ensure_preview_visible()
            if self._preview_tabs is None:
                return
            self._preview_tabs.open_file(resolved, replace=True)
            page = self._preview_tabs.currentWidget()
            if isinstance(page, FilePreviewPage):
                page.reload_from_disk()

        _load()
        QTimer.singleShot(80, _load)
        QTimer.singleShot(450, _load)

    def _any_background_job_running(self) -> bool:
        return (
            self._worker_thread is not None
            or self._genome_map_thread is not None
            or self._benchmark_thread is not None
        )

    def _open_confusion_matrix_benchmark(self) -> None:
        selected = self._selected_files()
        query_files = [p for p in selected if is_repeatmasker_out_file(p)]
        if not query_files:
            QMessageBox.information(
                self,
                "Confusion matrix benchmarker",
                "Select one or more RepeatMasker .out files (query) in the Files panel.",
            )
            return
        if not self._project.genome_file or not self._project.genome_file.is_file():
            QMessageBox.warning(
                self,
                "Confusion matrix benchmarker",
                f"Set the genome FASTA under {self._genome_menu_hint()} first.",
            )
            return
        try:
            require_bedtools()
        except RuntimeError as exc:
            QMessageBox.warning(self, "Confusion matrix benchmarker", str(exc))
            return

        dialog = ConfusionMatrixBenchmarkDialog(
            initial=self._te_confusion_benchmark_options,
            parent=self,
        )
        if not exec_modal_dialog(dialog):
            return
        opts = dialog.options()
        self._te_confusion_benchmark_options = opts
        save_te_confusion_matrix_benchmark_options(opts)

        home_text = opts.tetrimmer_home.strip()
        if not home_text:
            detected = default_tetrimmer_home()
            if detected is None:
                QMessageBox.warning(
                    self,
                    "Confusion matrix benchmarker",
                    "Set the TEtrimmer repository folder in the dialog, or set "
                    "environment variable TETRIMMER_HOME.",
                )
                return
            home = detected
        else:
            home = Path(home_text).expanduser().resolve()

        reference = Path(opts.reference_out).expanduser().resolve()
        if not reference.is_file():
            QMessageBox.warning(
                self,
                "Confusion matrix benchmarker",
                "Choose a reference RepeatMasker .out file (curated TE library on the genome).",
            )
            return

        worker = ConfusionMatrixBenchmarkWorker(
            query_files,
            reference_out=reference,
            genome_fasta=self._project.genome_file,
            tetrimmer_home=home,
            less_classification=opts.less_classification,
            debug=opts.debug,
            cancel=self._job_cancel,
        )
        self._start_te_benchmark_job(
            worker,
            job_title="te_confusion_benchmark",
            total_steps=len(query_files),
            source_files=query_files,
        )

    def _open_te_library_benchmark(self) -> None:
        selected = self._selected_files()
        fasta_files = [p for p in selected if p.suffix.lower() in _FASTA_SUFFIXES]
        query_hint = fasta_files[0] if len(fasta_files) == 1 else None

        dialog = TeLibraryBenchmarkDialog(
            initial=self._te_library_benchmark_options,
            query_file=query_hint,
            parent=self,
        )
        if not exec_modal_dialog(dialog):
            return
        opts = dialog.options()
        self._te_library_benchmark_options = opts
        save_te_library_benchmark_options(opts)

        query = Path(opts.query_fasta).expanduser().resolve()
        standard = Path(opts.standard_fasta).expanduser().resolve()
        if not query.is_file():
            QMessageBox.warning(
                self,
                "TE library benchmarker",
                "Choose a query TE consensus library FASTA.",
            )
            return
        if not standard.is_file():
            QMessageBox.warning(
                self,
                "TE library benchmarker",
                "Choose a standard (curated) TE library FASTA.",
            )
            return

        rm_out: Path | None = None
        if opts.rm_out.strip():
            rm_out = Path(opts.rm_out).expanduser().resolve()
            if not rm_out.is_file():
                QMessageBox.warning(
                    self,
                    "TE library benchmarker",
                    f"RepeatMasker .out not found:\n{rm_out}",
                )
                return
        elif not opts.run_repeatmasker:
            QMessageBox.warning(
                self,
                "TE library benchmarker",
                "Provide an existing RepeatMasker .out file or enable Run RepeatMasker.",
            )
            return

        worker = TeLibraryBenchmarkWorker(
            query_fasta=query,
            standard_fasta=standard,
            rm_out=rm_out,
            run_repeatmasker=opts.run_repeatmasker,
            threads=opts.threads,
            cancel=self._job_cancel,
        )
        self._start_te_benchmark_job(
            worker,
            job_title="te_library_benchmark",
            total_steps=1,
            source_files=[query],
        )

    def _start_te_benchmark_job(
        self,
        worker: ConfusionMatrixBenchmarkWorker | TeLibraryBenchmarkWorker,
        *,
        job_title: str,
        total_steps: int,
        source_files: list[Path],
    ) -> None:
        if self._any_background_job_running():
            QMessageBox.information(
                self,
                "Job already running",
                "Wait for the current job to finish before starting another.",
            )
            return

        self._last_benchmark_source_files = list(source_files)
        self._job_cancel.reset()
        self._show_job_progress(job_title, total_steps)
        self._set_job_actions_enabled(False)
        if self._stop_btn is not None:
            self._stop_btn.setEnabled(True)

        self._benchmark_thread = QThread(self)
        self._benchmark_worker = worker
        self._benchmark_worker.moveToThread(self._benchmark_thread)
        self._benchmark_thread.started.connect(self._benchmark_worker.run)
        self._benchmark_worker.progress.connect(self._on_job_progress)
        self._benchmark_worker.finished.connect(self._on_te_benchmark_finished)
        self._benchmark_worker.failed.connect(self._on_te_benchmark_failed)
        self._benchmark_worker.finished.connect(self._benchmark_thread.quit)
        self._benchmark_worker.failed.connect(self._benchmark_thread.quit)
        self._benchmark_thread.finished.connect(self._cleanup_benchmark_worker)
        self._benchmark_thread.finished.connect(self._update_status)
        self._benchmark_thread.start()

    @Slot(list)
    def _on_te_benchmark_finished(self, created_paths: list[Path]) -> None:
        self._hide_job_progress()
        self._set_job_actions_enabled(True)
        paths = [Path(p).expanduser().resolve() for p in created_paths if Path(p).is_file()]
        sources = self._last_benchmark_source_files
        self._refresh_folders_after_job(paths, sources)
        self._auto_open_outputs(paths)
        title = self._job_display_title("te_confusion_benchmark")
        if paths and any(p.name.endswith("_library_benchmark.html") for p in paths):
            title = self._job_display_title("te_library_benchmark")
        summary = f"{title} finished"
        if paths:
            names = ", ".join(p.name for p in paths[:4])
            if len(paths) > 4:
                names += ", …"
            summary += f" — created: {names}"
        self._set_status_message(summary, 12000)

    @Slot(str)
    def _on_te_benchmark_failed(self, error: str) -> None:
        self._hide_job_progress()
        self._set_job_actions_enabled(True)
        if error == CANCELLED_MESSAGE:
            self._set_status_message("Stopped benchmark", 6000)
            return
        self._set_status_message("Benchmark failed", 8000)
        QMessageBox.critical(self, "Benchmark failed", error)

    def _cleanup_benchmark_worker(self) -> None:
        if self._benchmark_worker:
            self._benchmark_worker.deleteLater()
            self._benchmark_worker = None
        if self._benchmark_thread:
            self._benchmark_thread.deleteLater()
            self._benchmark_thread = None

    def _open_te_density_plot_dialog(self, *, input_file: Path | None = None) -> None:
        if self._project.is_pan_genome_mode:
            QMessageBox.information(
                self,
                "TE visualization",
                "TE visualization is available only in single-genome mode.\n\n"
                f"Switch to single genome under {self._genome_menu_hint()}.",
            )
            return
        if not self._project.genome_file or not self._project.genome_file.is_file():
            QMessageBox.warning(
                self,
                "TE visualization",
                f"Set the genome FASTA under {self._genome_menu_hint()} first.",
            )
            return
        chrom_names = self._genome_chromosome_names()
        chrom_sizes = self._genome_chromosome_sizes()
        if not chrom_names:
            QMessageBox.warning(
                self,
                "TE visualization",
                "Could not read chromosome names from the genome FASTA.",
            )
            return
        masking_input: Path | None = None
        consensus_input: Path | None = None
        if input_file is not None:
            if is_te_hit_table_file(input_file):
                masking_input = input_file
            elif self._is_fasta_file(input_file):
                consensus_input = input_file
        else:
            masking_input = self._guess_te_masking_input_file()
            consensus_input = self._guess_te_consensus_input_file()

        def _on_accept(dialog: TeDensityPlotDialog) -> None:
            self._te_genome_map_options = dialog.options()
            save_te_genome_map_options(self._te_genome_map_options)
            masking_files: list[Path] = []
            if dialog.te_masking_files():
                validated_masking = self._validate_te_hit_inputs(dialog.te_masking_files())
                if validated_masking is None:
                    return
                masking_files = validated_masking
            consensus_files = self._validate_te_consensus_fastas(dialog.te_consensus_files())
            if consensus_files is None:
                return
            gene_files = self._validate_gene_input_files(dialog.gene_input_files())
            if dialog.gene_input_files() and gene_files is None:
                return
            methylation_files = self._validate_methylation_input_files(
                dialog.methylation_input_files()
            )
            if dialog.methylation_input_files() and methylation_files is None:
                return
            if not masking_files and not consensus_files and not gene_files and not methylation_files:
                QMessageBox.warning(
                    self,
                    "TE visualization",
                    "Provide at least one TE masking file, TE consensus FASTA, gene annotation, "
                    "or DNA methylation file.",
                )
                return
            self._start_te_viz_from_dialog(
                masking_paths=masking_files,
                consensus_fastas=consensus_files,
                gene_paths=gene_files or [],
                methylation_paths=methylation_files or [],
                map_options=self._te_genome_map_options,
            )

        dialog = TeDensityPlotDialog(
            initial=self._te_genome_map_options,
            chromosome_names=chrom_names,
            chromosome_sizes=chrom_sizes,
            input_file=masking_input,
            consensus_input_file=consensus_input,
            parent=self,
        )
        self._present_te_viz_dialog(dialog, _on_accept)

    def _open_te_divergence_plot_dialog(self, *, input_file: Path | None = None) -> None:
        if input_file is None:
            input_file = self._guess_te_hit_input_file()

        def _on_accept(dialog: TeDivergencePlotDialog) -> None:
            self._te_divergence_plot_options = dialog.options()
            save_te_divergence_plot_options(self._te_divergence_plot_options)
            te_files = self._validate_te_hit_inputs(dialog.te_input_files())
            if te_files is None:
                return
            self._open_blast_divergence_plot(
                te_files,
                bin_width=self._te_divergence_plot_options.bin_width,
            )

        dialog = TeDivergencePlotDialog(
            initial=self._te_divergence_plot_options,
            input_file=input_file,
            parent=self,
        )
        self._present_te_viz_dialog(dialog, _on_accept)

    def _warm_genome_chromosome_cache(self) -> None:
        """Pre-read genome FASTA metadata so TE genome map dialogs open quickly."""
        if self._project.genome_file and self._project.genome_file.is_file():
            self._genome_chromosome_names()

    def _genome_chromosome_names(self) -> list[str]:
        """Chromosome list for dialogs (cached; avoids re-reading the whole genome FASTA)."""
        names, _ = self._genome_chromosome_meta()
        return names

    def _genome_chromosome_sizes(self) -> dict[str, int]:
        """Chromosome lengths (bp) for dialogs (cached with names)."""
        _, sizes = self._genome_chromosome_meta()
        return sizes

    def _genome_chromosome_meta(self) -> tuple[list[str], dict[str, int]]:
        if not self._project.genome_file or not self._project.genome_file.is_file():
            return [], {}
        path = self._project.genome_file.expanduser().resolve()
        if self._genome_chrom_cache_path == path:
            return self._genome_chrom_names_cache, self._genome_chrom_sizes_cache
        self._genome_chrom_cache_path = path
        self._genome_chrom_names_cache = chromosome_names_from_genome(path)
        self._genome_chrom_sizes_cache = genome_chrom_sizes_from_fasta(path)
        return self._genome_chrom_names_cache, self._genome_chrom_sizes_cache

    def _start_blast_then_te_genome_map(
        self,
        fasta_paths: list[Path],
        map_options: TeGenomeMapOptions | None,
    ) -> None:
        """Run Blast on FASTA(s), then build and open the TE genome map when Blast finishes."""
        if not fasta_paths:
            return
        if not self._project.genome_file or not self._project.genome_file.is_file():
            QMessageBox.warning(
                self,
                "Genome required",
                f"Set the genome FASTA under {self._genome_menu_hint()} before Blast / TE genome map.",
            )
            return
        self._pending_te_genome_map = map_options
        self._pending_te_genome_map_fastas = [p.expanduser().resolve() for p in fasta_paths]
        self._set_status_message("Running Blast, then TE genome map…", 0)
        self._apply_function(
            "blast",
            preselected=self._pending_te_genome_map_fastas,
            blast_options=self._blast_options,
        )

    def _open_blast_genome_map(
        self,
        te_input_files: list[Path] | Path,
        *,
        gene_file: Path | None = None,
        gene_files: list[Path] | None = None,
        methylation_files: list[Path] | None = None,
        te_input_kinds: list[str] | None = None,
        map_options: TeGenomeMapOptions | None = None,
    ) -> None:
        te_paths = (
            [te_input_files.expanduser().resolve()]
            if isinstance(te_input_files, Path)
            else [p.expanduser().resolve() for p in te_input_files]
        )
        gene_paths: list[Path] = []
        if gene_files:
            gene_paths.extend(p.expanduser().resolve() for p in gene_files)
        if gene_file is not None:
            gene_paths.insert(0, gene_file.expanduser().resolve())
        methylation_paths: list[Path] = []
        if methylation_files:
            methylation_paths.extend(p.expanduser().resolve() for p in methylation_files)
        if te_paths and not any(p.is_file() for p in te_paths):
            query_fasta = self._fasta_for_blast_table(te_paths[0])
            if query_fasta is not None:
                self._start_blast_then_te_genome_map([query_fasta], map_options)
                return
            QMessageBox.warning(
                self,
                "TE genome map",
                f"TE input not found:\n{te_paths[0]}\n\nRun Blast on this sequence first.",
            )
            return
        te_paths = [p for p in te_paths if p.is_file()]
        if not te_paths and not gene_paths and not methylation_paths:
            QMessageBox.warning(
                self,
                "TE genome map",
                "Provide at least one TE hit table, gene annotation, or DNA methylation file.",
            )
            return
        if not self._project.genome_file or not self._project.genome_file.is_file():
            QMessageBox.warning(
                self,
                "Genome required",
                f"Set the genome FASTA under {self._genome_menu_hint()} before building the map.",
            )
            return
        if self._genome_map_thread is not None:
            QMessageBox.information(
                self,
                "TE genome map",
                "A genome map is already being built. Please wait for it to finish.",
            )
            return
        opts = map_options or self._te_genome_map_options
        if te_paths:
            if len(te_paths) == 1:
                query_label = te_hit_table_stem(te_paths[0])
            else:
                query_label = f"{te_hit_table_stem(te_paths[0])} + {len(te_paths) - 1} more"
        elif gene_paths:
            if len(gene_paths) == 1:
                query_label = gene_paths[0].stem
            else:
                query_label = f"{gene_paths[0].stem} + {len(gene_paths) - 1} more"
        elif methylation_paths:
            if len(methylation_paths) == 1:
                query_label = methylation_paths[0].stem
            else:
                query_label = (
                    f"{methylation_paths[0].stem} + {len(methylation_paths) - 1} more"
                )
        else:
            query_label = "genome map"
        self._start_genome_map_build(
            te_paths,
            gene_files=gene_paths,
            methylation_files=methylation_paths,
            te_input_kinds=te_input_kinds,
            bin_size=opts.bin_size_bp,
            density_mode=opts.density_mode,
            color_by=opts.color_by,
            methylation_coverage_min=opts.methylation_coverage_min,
            split_strand_tracks=opts.split_strand_tracks,
            collapse_overlaps=opts.collapse_overlaps,
            show_te_diff_track=opts.show_te_diff_track,
            show_meth_diff_track=opts.show_meth_diff_track,
            show_window_ref_line=opts.show_window_ref_line,
            annotation_density_mode=opts.annotation_density_mode,
            annotation_feature_types=opts.annotation_feature_types,
            annotation_feature_types_by_file=opts.annotation_feature_types_by_file,
            query_label=query_label,
            chromosomes_only=opts.chromosomes_only or None,
            superfamilies_only=None,
            chromosome_sort=opts.chromosome_sort,
        )

    def _start_genome_map_build(
        self,
        te_input_files: list[Path],
        *,
        gene_files: list[Path] | None = None,
        methylation_files: list[Path] | None = None,
        te_input_kinds: list[str] | None = None,
        bin_size: int,
        density_mode: str,
        color_by: str,
        methylation_coverage_min: int,
        split_strand_tracks: bool,
        collapse_overlaps: bool,
        show_te_diff_track: bool,
        show_meth_diff_track: bool,
        show_window_ref_line: bool,
        annotation_density_mode: str,
        annotation_feature_types: list[str] | None,
        annotation_feature_types_by_file: dict[str, list[str]] | None,
        query_label: str,
        chromosomes_only: list[str] | None,
        superfamilies_only: list[str] | None,
        chromosome_sort: str,
    ) -> None:
        genome = self._project.genome_file
        assert genome is not None
        te_paths = [p.expanduser().resolve() for p in te_input_files]
        gene_paths = [p.expanduser().resolve() for p in (gene_files or [])]
        methylation_paths = [p.expanduser().resolve() for p in (methylation_files or [])]
        primary = (
            te_paths[0]
            if te_paths
            else (gene_paths[0] if gene_paths else (methylation_paths[0] if methylation_paths else Path(".")))
        )
        self._genome_map_blast_txt = primary
        self._genome_map_te_paths = list(te_paths)
        self._job_cancel.reset()
        self._job_running = True
        self._set_job_actions_enabled(False)
        workers = max(1, min(self._project.batch_workers, 8))
        worker_note = f" ({workers} workers)" if workers > 1 else ""
        self._set_status_message(f"Building TE genome map{worker_note}…", 0)
        if self._task_progress is not None:
            self._task_progress.start(self._running_job_title("TE genome map"), 6)
        if self._stop_btn is not None:
            self._stop_btn.setEnabled(True)
        self._genome_map_thread = QThread(self)
        self._genome_map_worker = GenomeMapWorker(
            te_paths,
            genome,
            job_kwargs={
                "gene_gff": gene_paths or None,
                "methylation_files": methylation_paths or None,
                "te_input_kinds": te_input_kinds,
                "bin_size": bin_size,
                "density_mode": density_mode,
                "color_by": color_by,
                "methylation_coverage_min": methylation_coverage_min,
                "split_strand_tracks": split_strand_tracks,
                "collapse_overlaps": collapse_overlaps,
                "show_te_diff_track": show_te_diff_track,
                "show_meth_diff_track": show_meth_diff_track,
                "show_window_ref_line": show_window_ref_line,
                "annotation_density_mode": annotation_density_mode,
                "annotation_feature_types": annotation_feature_types,
                "annotation_feature_types_by_file": annotation_feature_types_by_file,
                "query_label": query_label,
                "chromosomes_only": chromosomes_only,
                "superfamilies_only": superfamilies_only,
                "chromosome_sort": chromosome_sort,
                "num_workers": self._project.batch_workers,
                "cancel": self._job_cancel,
            },
        )
        self._genome_map_worker.moveToThread(self._genome_map_thread)
        self._genome_map_thread.started.connect(self._genome_map_worker.run)
        self._genome_map_worker.progress.connect(self._on_genome_map_progress)
        self._genome_map_worker.finished.connect(self._on_genome_map_finished)
        self._genome_map_worker.failed.connect(self._on_genome_map_failed)
        self._genome_map_worker.finished.connect(self._genome_map_thread.quit)
        self._genome_map_worker.failed.connect(self._genome_map_thread.quit)
        self._genome_map_thread.finished.connect(self._cleanup_genome_map_worker)
        self._genome_map_thread.start()

    @Slot(object)
    def _on_genome_map_finished(self, html_path: object) -> None:
        blast_txt = self._genome_map_blast_txt
        if self._task_progress is not None:
            self._task_progress.update(6, Path(str(blast_txt)).name if blast_txt else "")
        if html_path is None or not Path(html_path).is_file():
            QMessageBox.warning(self, "TE genome map", "Could not build the genome map.")
            self._set_status_message("TE genome map failed", 6000)
            return
        path = Path(html_path).resolve()
        if blast_txt is not None:
            self._highlight_genome_map_outputs(path, blast_txt)
        if self._current_folder and path.parent.resolve() == self._current_folder.resolve():
            self._select_path_in_file_list(path)
        self._open_genome_map_in_preview(path)
        n_inputs = len(self._genome_map_te_paths)
        detail = (
            "all TE samples share one y-axis scale"
            if n_inputs > 1
            else "chromosome tracks, Mbp on X axis"
        )
        self._set_status_message(
            f"Genome map opened: {path.name} ({detail})",
            12000,
        )

    @Slot(int, str)
    def _on_genome_map_progress(self, value: int, label: str) -> None:
        if self._task_progress is not None:
            self._task_progress.update(value, label)

    @Slot(str)
    def _on_genome_map_failed(self, error: str) -> None:
        if self._task_progress is not None:
            self._task_progress.reset()
        if error == CANCELLED_MESSAGE:
            self._set_status_message("Stopped TE genome map", 6000)
            return
        if error.startswith("There is nothing to plot"):
            QMessageBox.information(self, "TE density plot", error)
            self._set_status_message("TE density plot: nothing to plot", 8000)
            return
        QMessageBox.critical(self, "TE genome map failed", error)
        self._set_status_message("TE genome map failed", 6000)

    def _cleanup_genome_map_worker(self) -> None:
        cancelled = self._job_cancel.requested
        if cancelled:
            self._job_cancel.reset()
        self._job_running = self._worker_thread is not None
        if self._task_progress is not None:
            self._task_progress.reset()
        thread = self._genome_map_thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(5000)
        if self._genome_map_worker:
            self._genome_map_worker.deleteLater()
            self._genome_map_worker = None
        if self._genome_map_thread:
            self._genome_map_thread.deleteLater()
            self._genome_map_thread = None
        self._genome_map_te_paths = []
        if self._worker_thread is None:
            self._set_job_actions_enabled(True)
        if self._stop_btn is not None and not self._job_running:
            self._stop_btn.setEnabled(False)
        if cancelled:
            self._queued_genome_map_jobs.clear()
        else:
            QTimer.singleShot(0, self._start_next_genome_map_job)

    def _highlight_genome_map_outputs(
        self,
        html_path: Path,
        blast_txt: Path,
    ) -> None:
        """Highlight the new *_genome_map.html (and query FASTA) in the Files panel."""
        folder = html_path.parent.resolve()
        outputs = [html_path.resolve()]
        source = self._fasta_for_blast_table(blast_txt) or blast_txt
        sources = [source.resolve()]
        if self._current_folder and self._current_folder.resolve() == folder:
            self._populate_file_list(folder, new_outputs=outputs, source_files=sources)
        else:
            self._navigate_to_folder(folder, new_outputs=outputs, source_files=sources)

    def _fasta_for_blast_table(self, blast_txt: Path) -> Path | None:
        """Infer query FASTA from a ``*_blast.txt`` path when the table is missing."""
        name = blast_txt.name
        if not name.lower().endswith("blast.txt"):
            return None
        if name.endswith("_blast.txt"):
            stem = name[: -len("_blast.txt")]
        else:
            stem = Path(name).stem
        parent = blast_txt.parent
        candidates = [
            parent / stem,
            parent / f"{stem}.fa",
            parent / f"{stem}.fasta",
            parent / f"{stem}.fas",
        ]
        seen: set[str] = set()
        for query in candidates:
            key = str(query)
            if key in seen:
                continue
            seen.add(key)
            if query.suffix.lower() in _FASTA_SUFFIXES and query.is_file():
                return query.expanduser().resolve()
        return None

    def _open_genome_map_in_preview(self, html_path: Path) -> None:
        """Open the genome map HTML in Preview after the file is written."""
        from teviewer.widgets.preview_tabs import FilePreviewPage

        resolved = html_path.expanduser().resolve()
        if not resolved.is_file():
            return

        def _load() -> None:
            self._ensure_preview_visible()
            if self._preview_tabs is None:
                return
            self._preview_tabs.open_file(resolved, replace=True)
            page = self._preview_tabs.currentWidget()
            if isinstance(page, FilePreviewPage):
                page.reload_from_disk()

        _load()
        QTimer.singleShot(80, _load)
        QTimer.singleShot(450, _load)

    def _run_extend(self) -> None:
        self._apply_function("extend", extend=self._extend_options)

    def _run_tsd_search(self) -> None:
        self._apply_function("tsd_search", tsd_search_options=self._tsd_search_options)

    def _run_teaid(self) -> None:
        self._apply_function("teaid", teaid_options=self._teaid_options)

    def _modify_teaid_parameters(self) -> None:
        dialog = TeaAidParamsDialog(initial=self._teaid_options, parent=self)
        if dialog.exec():
            self._teaid_options = dialog.options()
            save_teaid_options(self._teaid_options)
            self._set_status_message(
                f"TEAid defaults: genome E-value {self._teaid_options.e_value:.4f}, "
                f"self BLAST word size {self._teaid_options.self_blast_word_size}",
                5000,
            )

    def _show_gff_features_from_selection(self) -> None:
        selected = self._selected_files()
        fasta_files = [p for p in selected if p.suffix.lower() in _FASTA_SUFFIXES]
        if len(fasta_files) != 1:
            QMessageBox.information(
                self,
                "GFF annotations",
                "Select exactly one FASTA sequence file in the Files panel.",
            )
            return
        self._show_gff_features(fasta_files[0])

    def _show_gff_features(self, fasta_path: Path) -> None:
        if fasta_path.suffix.lower() not in _FASTA_SUFFIXES:
            QMessageBox.warning(
                self,
                "GFF annotations",
                "Choose a FASTA sequence file.",
            )
            return
        gff_path = find_companion_gff(fasta_path)
        if gff_path is None:
            start_dir = str(fasta_path.parent)
            picked, _ = QFileDialog.getOpenFileName(
                self,
                "Select GFF/GTF annotation file",
                start_dir,
                "Annotation (*.gff *.gff3 *.gtf);;All files (*)",
            )
            if not picked:
                return
            gff_path = Path(picked)
        if not gff_path.is_file():
            QMessageBox.warning(self, "GFF annotations", f"File not found:\n{gff_path}")
            return
        try:
            html_text = build_gff_annotation_html(fasta_path, gff_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "GFF annotations", str(exc))
            return
        temp_dir = Path(tempfile.gettempdir()) / "teviewer"
        temp_dir.mkdir(parents=True, exist_ok=True)
        html_path = temp_dir / f"gff_{fasta_path.stem}_{gff_path.stem}.html"
        html_path.write_text(html_text, encoding="utf-8")
        self._open_files_in_preview_tabs([html_path])
        self._set_status_message(
            f"GFF map: {fasta_path.name} + {gff_path.name}",
            6000,
        )

    def _modify_extend_parameters(self) -> None:
        dialog = ExtendParamsDialog(
            initial=self._extend_options,
            pan_genome_names=self._pan_genome_names(),
            parent=self,
        )
        if dialog.exec():
            self._extend_options = dialog.options()
            save_extend_options(self._extend_options)
            genome_note = ""
            if self._extend_options.pan_genome_name:
                genome_note = f", genome {self._extend_options.pan_genome_name}"
            self._set_status_message(
                f"Extend defaults: {self._extend_options.left} bp left, "
                f"{self._extend_options.right} bp right{genome_note}",
                5000,
            )

    def _modify_tsd_search_parameters(self) -> None:
        dialog = TsdSearchParamsDialog(
            initial=self._tsd_search_options,
            parent=self,
        )
        if dialog.exec():
            self._tsd_search_options = dialog.options()
            save_tsd_search_options(self._tsd_search_options)
            self._set_status_message(
                "TSD search defaults: "
                f"left {self._tsd_search_options.left_boundary}, "
                f"right {self._tsd_search_options.right_boundary}, "
                f"radius {self._tsd_search_options.nt_radius} nt",
                5000,
            )

    def _extend_with_different_distances(self) -> None:
        if not self._project.has_genome_configured():
            QMessageBox.warning(
                self,
                "Genome required",
                f"Define genome FASTA under {self._genome_menu_hint()} before running Extend.",
            )
            return
        seq_files = [
            p for p in self._selected_files() if p.suffix.lower() in _FASTA_SUFFIXES
        ]
        if not seq_files:
            QMessageBox.information(
                self,
                "No FASTA selected",
                "Select one or more sequence files in the Files panel.",
            )
            return
        dialog = ExtendParamsDialog(
            initial=self._extend_options,
            title="Extend with different distances",
            pan_genome_names=self._pan_genome_names(),
            parent=self,
        )
        if not dialog.exec():
            return
        opts = dialog.options()
        answer = QMessageBox.question(
            self,
            "Confirm Extend",
            f"Extend {len(seq_files)} sequence file(s) by {opts.left} bp (left) "
            f"and {opts.right} bp (right)?\n\n"
            f"Output names will include _L{opts.left}_R{opts.right}.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._apply_function("extend", preselected=seq_files, extend=opts)

    def _run_consensus(self) -> None:
        self._apply_function(
            "consensus_generation",
            consensus_options=self._consensus_options,
        )

    def _modify_consensus_parameters(self) -> None:
        dialog = ConsensusParamsDialog(
            initial=self._consensus_options,
            parent=self,
        )
        if dialog.exec():
            self._consensus_options = dialog.options()
            save_consensus_options(self._consensus_options)
            self._set_status_message(
                f"Consensus parameters updated (threshold={self._consensus_options.threshold})",
                5000,
            )

    def _run_flexidot_combined(self) -> None:
        self._apply_function(
            "flexidot",
            flexidot_combined=True,
            flexidot_options=self._flexidot_options,
        )

    def _run_te_annotation(self) -> None:
        from teviewer.backends.te_annotation_batch import is_single_sequence_fasta

        selected = self._selected_files()
        if not selected:
            QMessageBox.information(
                self,
                "No sequence selected",
                "Select one or more single-sequence FASTA files in the Files panel.",
            )
            return
        seq_files = [p for p in selected if p.suffix.lower() in _FASTA_SUFFIXES]
        if not seq_files:
            QMessageBox.warning(
                self,
                "Invalid selection",
                "Selected files do not include FASTA sequence files.",
            )
            return
        single = [p for p in seq_files if is_single_sequence_fasta(p)]
        skipped = [p for p in seq_files if p not in single]
        if skipped:
            skipped_names = "\n".join(p.name for p in skipped[:12])
            if len(skipped) > 12:
                skipped_names += "\n..."
            QMessageBox.warning(
                self,
                "Skipped files",
                f"{len(skipped)} file(s) skipped — only single-sequence FASTA files "
                f"are supported:\n\n{skipped_names}",
            )
        if not single:
            QMessageBox.warning(
                self,
                "No valid files",
                "Select at least one single-sequence FASTA file for TE annotation.",
            )
            return
        dialog = TeAnnotationDialog(parent=self)
        if not exec_modal_dialog(dialog):
            return
        opts = dialog.options()
        if not opts.auto_modes and not opts.similarity_databases:
            QMessageBox.information(
                self,
                "Nothing selected",
                "Select at least one auto-annotation module or similarity database.",
            )
            return
        self._apply_function(
            "te_annotation",
            preselected=single,
            te_annotation_options=opts,
        )

    def _modify_flexidot_parameters(self) -> None:
        dialog = FlexidotParamsDialog(
            initial=self._flexidot_options,
            parent=self,
        )
        if dialog.exec():
            self._flexidot_options = dialog.options()
            save_flexidot_options(self._flexidot_options)
            self._set_status_message(
                f"Flexidot parameters updated "
                f"(k={self._flexidot_options.wordsize}"
                f"{', GFF on' if self._flexidot_options.use_gff else ''})",
                5000,
            )

    def _add_msa_clean_menu_action(
        self,
        menu: QMenu,
        label: str,
        method_id: str,
    ) -> None:
        action = menu.addAction(label, lambda: self._apply_msa_clean(method_id))
        desc = msa_clean_method_description(method_id)
        if desc:
            action.setToolTip(desc)
            action.setStatusTip(desc)

    def _modify_msa_clean_parameters(self) -> None:
        dialog = MsaCleanParamsDialog(
            initial=self._msa_clean_options,
            parent=self,
        )
        if dialog.exec():
            self._msa_clean_options = dialog.options()
            save_msa_clean_options(self._msa_clean_options)
            label = msa_clean_method_label(self._msa_clean_options.default_method)
            self._set_status_message(
                f"MSA clean parameters updated (toolbar default: {label})",
                5000,
            )

    def _run_default_msa_clean(self) -> None:
        self._apply_msa_clean(self._msa_clean_options.default_method)

    def _apply_msa_clean(self, func_name: str) -> None:
        self._apply_function(
            func_name,
            msa_clean_options=self._msa_clean_options,
        )

    def _ensure_preview_dock_attached(self) -> None:
        dock = self._dock_preview
        if dock is None:
            return
        host = self._preview_host
        if host is not None and dock.widget() is not host:
            dock.setWidget(host)
        if self.dockWidgetArea(dock) == Qt.DockWidgetArea.NoDockWidgetArea:
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            if self._dock_folders is not None and self._dock_files is not None:
                self.splitDockWidget(self._dock_folders, self._dock_files, Qt.Orientation.Vertical)

    def _ensure_preview_visible(self) -> None:
        self._ensure_preview_dock_attached()
        dock = self._dock_preview
        if dock is not None:
            dock.show()
            dock.raise_()
            for other in self.tabifiedDockWidgets(dock):
                if other is not dock:
                    other.show()
            dock.raise_()
        if self._preview_host is not None:
            self._preview_host.show()
        if self._preview_tabs is not None:
            self._preview_tabs.show()
        if (
            self._dock_preview is not None
            and self._dock_files is not None
            and not self._dock_preview.isFloating()
        ):
            total = self._dock_files.width() + self._dock_preview.width()
            if total > 200 and self._dock_preview.width() / total < 0.62:
                self.resizeDocks(
                    [self._dock_files, self._dock_preview],
                    [280, 1120],
                    Qt.Orientation.Horizontal,
                )

    def _open_preview_tab(self, path: Path, *, replace: bool = False) -> None:
        if self._preview_tabs is None:
            return
        try:
            self._preview_tabs.open_file(path, replace=replace)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Preview failed",
                f"Could not open {path.name} in preview:\n{exc}",
            )
            return
        self._ensure_preview_visible()
        QTimer.singleShot(0, self._ensure_preview_visible)

    def _rename_file(self, path: Path) -> None:
        path = path.expanduser().resolve()
        if not path.is_file():
            return
        new_name, ok = QInputDialog.getText(
            self,
            "Rename file",
            "New file name:",
            text=path.name,
        )
        if not ok or not new_name.strip() or new_name.strip() == path.name:
            return
        target = path.parent / new_name.strip()
        if target.exists():
            QMessageBox.warning(self, "Rename failed", f"Already exists:\n{target}")
            return
        try:
            path.rename(target)
        except OSError as exc:
            QMessageBox.critical(self, "Rename failed", str(exc))
            return
        if self._preview_tabs is not None:
            self._preview_tabs.close_paths([path])
        if self._current_folder:
            self._populate_file_list(self._current_folder)
        self._set_status_message(f"Renamed to {target.name}", 5000)

    def _rename_folder(self, folder: Path) -> None:
        folder = folder.expanduser().resolve()
        if not folder.is_dir():
            return
        new_name, ok = QInputDialog.getText(
            self,
            "Rename folder",
            "New folder name:",
            text=folder.name,
        )
        if not ok or not new_name.strip() or new_name.strip() == folder.name:
            return
        target = folder.parent / new_name.strip()
        if target.exists():
            QMessageBox.warning(self, "Rename failed", f"Already exists:\n{target}")
            return
        try:
            folder.rename(target)
        except OSError as exc:
            QMessageBox.critical(self, "Rename failed", str(exc))
            return
        self._replace_folder_path_in_tree(folder, target)
        replace_folder_color_paths(folder, target)
        apply_folder_colors_to_tree(self._folder_tree)
        self._hidden_root_folders = replace_hidden_root_path(
            self._hidden_root_folders, folder, target
        )
        if self._current_folder and self._current_folder.resolve() == folder:
            self._current_folder = target
            self._on_folder_selected(target)
        self._set_status_message(f"Renamed folder to {target.name}", 5000)

    def _clear_root_folders(self, folders: list[Path]) -> None:
        if not folders:
            return
        removed = 0
        for folder in folders:
            if self._clear_root_folder(folder, show_status=False):
                removed += 1
        if removed:
            label = "folder" if removed == 1 else "folders"
            self._set_status_message(
                f"Removed {removed} {label} from list (not deleted on disk)",
                6000,
            )
            self._persist_workspace()

    def _clear_root_folder(self, folder: Path, *, show_status: bool = True) -> bool:
        """Hide a top-level root folder from the tree without deleting it on disk."""
        folder = folder.expanduser().resolve()
        is_top_level = False
        for index in range(self._folder_tree.topLevelItemCount()):
            item = self._folder_tree.topLevelItem(index)
            raw = item.data(0, ROLE_PATH)
            if raw and Path(str(raw)).resolve() == folder:
                is_top_level = True
                break
        if not is_top_level:
            return False

        self._hidden_root_folders = hide_root_folder(self._hidden_root_folders, folder)
        self._remove_folder_from_tree(folder)
        self._navigate_after_folder_removed(folder)

        if show_status:
            self._set_status_message(
                f"Removed from folder list (not deleted): {folder.name}",
                6000,
            )
            self._persist_workspace()
        return True

    def _restore_removed_folders(self) -> None:
        hidden = sorted(self._hidden_root_folders)
        if not hidden:
            QMessageBox.information(
                self,
                "Restore deleted files",
                "No top-level folders were removed from the list.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Restore deleted files")
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                "These top-level folders were hidden from the Folders panel. "
                "Restoring does not change files on disk."
            )
        )
        list_widget = QListWidget()
        for path_str in hidden:
            path = Path(path_str)
            item = QListWidgetItem(f"{path.name}  ({path_str})")
            item.setData(ROLE_PATH, path_str)
            if not path.is_dir():
                item.setForeground(QBrush(QColor("#888888")))
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        buttons = QDialogButtonBox()
        restore_btn = buttons.addButton("Restore selected", QDialogButtonBox.ButtonRole.AcceptRole)
        restore_all_btn = buttons.addButton("Restore all", QDialogButtonBox.ButtonRole.ActionRole)
        close_btn = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        layout.addWidget(buttons)

        def restore_paths(paths: list[Path]) -> None:
            restored = 0
            for path in paths:
                if not path.is_dir():
                    continue
                self._add_root_folder(path, unhide=True)
                restored += 1
            if restored:
                self._set_status_message(f"Restored {restored} folder(s) to the list", 5000)
            dialog.accept()

        def restore_selected() -> None:
            paths = []
            for item in list_widget.selectedItems():
                raw = item.data(ROLE_PATH)
                if raw:
                    paths.append(Path(str(raw)))
            if not paths:
                QMessageBox.information(dialog, "Restore", "Select one or more folders in the list.")
                return
            restore_paths(paths)

        def restore_all() -> None:
            restore_paths([Path(str(p)) for p in hidden])

        restore_btn.clicked.connect(restore_selected)
        restore_all_btn.clicked.connect(restore_all)
        close_btn.clicked.connect(dialog.reject)
        list_widget.itemDoubleClicked.connect(restore_selected)

        dialog.exec()

    def _dedupe_folder_selection(self, folders: list[Path]) -> list[Path]:
        """Drop nested folders when an ancestor is also selected."""
        resolved = [folder.expanduser().resolve() for folder in folders]
        unique = list(dict.fromkeys(resolved))
        return [
            folder
            for folder in unique
            if not any(
                folder != other and folder in other.parents for other in unique
            )
        ]

    def _navigate_after_folder_removed(self, removed: Path) -> None:
        if not self._current_folder:
            return
        removed = removed.expanduser().resolve()
        current = self._current_folder.expanduser().resolve()
        if current != removed and removed not in current.parents:
            return
        parent = removed.parent
        if parent.is_dir() and self._find_tree_item_for_path(parent) is not None:
            self._navigate_to_folder(parent)
        elif self._folder_tree.topLevelItemCount():
            raw = self._folder_tree.topLevelItem(0).data(0, ROLE_PATH)
            if raw:
                self._navigate_to_folder(Path(str(raw)))
        else:
            self._current_folder = None
            self._cached_folder_files = []
            self._file_list.clear()

    def _delete_folders(self, folders: list[Path]) -> None:
        targets = self._dedupe_folder_selection(folders)
        if not targets:
            return
        if len(targets) == 1:
            folder = targets[0]
            answer = QMessageBox.question(
                self,
                "Delete folder",
                f"Permanently delete this folder and everything inside it?\n\n{folder}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        else:
            names = "\n".join(str(folder) for folder in targets[:8])
            if len(targets) > 8:
                names += f"\n… and {len(targets) - 8} more"
            answer = QMessageBox.question(
                self,
                "Delete folders",
                f"Permanently delete {len(targets)} folders and everything inside them?\n\n{names}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        if answer != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        failed: list[str] = []
        removed_any = False
        for folder in targets:
            if not folder.is_dir():
                continue
            try:
                shutil.rmtree(folder)
            except OSError as exc:
                failed.append(f"{folder.name}: {exc}")
                continue

            deleted += 1
            removed_any = True
            if self._preview_tabs is not None:
                self._preview_tabs.close_under_folder(folder)
            self._remove_folder_from_tree(folder)
            remove_folder_colors_under(folder)
            self._hidden_root_folders = remove_hidden_root(self._hidden_root_folders, folder)
            self._navigate_after_folder_removed(folder)

        if failed:
            QMessageBox.warning(
                self,
                "Delete partially failed",
                f"Deleted {deleted} folder(s).\n\nFailed:\n" + "\n".join(failed[:8]),
            )
        elif deleted:
            label = "folder" if deleted == 1 else "folders"
            self._set_status_message(f"Deleted {deleted} {label}", 6000)
        elif not removed_any and failed:
            QMessageBox.critical(
                self,
                "Delete folder failed",
                "Failed:\n" + "\n".join(failed[:8]),
            )

    def _delete_folder(self, folder: Path) -> None:
        self._delete_folders([folder])

    def _remove_folder_from_tree(self, folder: Path) -> None:
        item = self._find_tree_item_for_path(folder.expanduser().resolve())
        if item is None:
            return
        parent = item.parent()
        if parent is not None:
            parent.removeChild(item)
        else:
            index = self._folder_tree.indexOfTopLevelItem(item)
            if index >= 0:
                self._folder_tree.takeTopLevelItem(index)
        self._folder_tree.resizeColumnToContents(0)

    def _replace_folder_path_in_tree(self, old: Path, new: Path) -> None:
        old_root = old.expanduser().resolve()
        new_root = new.expanduser().resolve()

        def walk(item: QTreeWidgetItem) -> None:
            raw = item.data(0, ROLE_PATH)
            if raw:
                path = Path(str(raw)).expanduser().resolve()
                if path == old_root or old_root in path.parents:
                    try:
                        rel = path.relative_to(old_root)
                        updated = new_root / rel if str(rel) != "." else new_root
                    except ValueError:
                        updated = path
                    item.setData(0, ROLE_PATH, str(updated))
                    item.setText(updated.name)
                    item.setToolTip(0, str(updated))
            for index in range(item.childCount()):
                walk(item.child(index))

        for index in range(self._folder_tree.topLevelItemCount()):
            walk(self._folder_tree.topLevelItem(index))
        self._folder_tree.resizeColumnToContents(0)

    def _separate_fasta_file(self, path: Path, *, subfolder_per_sequence: bool = False) -> None:
        path = path.expanduser().resolve()
        if path.suffix.lower() not in _FASTA_SUFFIXES:
            QMessageBox.warning(self, "Not a FASTA file", "Select a .fa / .fasta file.")
            return
        try:
            seq_count = count_fasta_sequences(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Read FASTA failed", str(exc))
            return
        if seq_count <= 1:
            QMessageBox.information(
                self,
                "Separate FASTA",
                "This file already contains only one sequence.",
            )
            return

        output_dir = separation_output_dir(path)
        mapping_note = (
            "Sequence_name_mapping.txt will be written next to the input file."
            if output_dir.name == SEPARATED_TE_DIR
            else f"Sequence_name_mapping_{sanitize_name(path.stem)}.txt will be written next to the input file."
        )
        if subfolder_per_sequence:
            title = "Separate into subfolders"
            layout_note = (
                f"Each sequence will be written to its own subfolder under:\n{output_dir}\n"
                f"(e.g. {output_dir.name}/sequence_name/sequence_name.fa)\n\n"
            )
            done_title = "Separate into subfolders completed"
        else:
            title = "Separate FASTA sequences"
            layout_note = f"into separate files under:\n{output_dir}\n\n"
            done_title = "Separate FASTA completed"
        answer = QMessageBox.question(
            self,
            title,
            f"Split {seq_count} sequences from\n{path.name}\n\n"
            f"{layout_note}"
            f"Special characters in headers will be sanitized. {mapping_note}\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            created, written = separate_sequences(
                path,
                output_dir,
                subfolder_per_sequence=subfolder_per_sequence,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Separate FASTA failed", str(exc))
            return

        self._refresh_subfolders_under(path.parent)
        self._navigate_to_folder(
            output_dir,
            new_outputs=created,
            source_files=[path],
        )
        if subfolder_per_sequence:
            status = f"Created {written} subfolder(s) in {output_dir.name}/"
            done_msg = f"Wrote {written} sequence(s), each in its own subfolder under:\n{output_dir}"
        else:
            status = f"Created {written} single-sequence file(s) in {output_dir.name}/"
            done_msg = f"Wrote {written} file(s) to:\n{output_dir}"
        self._set_status_message(status, 10000)
        QMessageBox.information(self, done_title, done_msg)

    def _separate_fasta_to_subfolders_file(self, path: Path) -> None:
        self._separate_fasta_file(path, subfolder_per_sequence=True)

    def _duplicate_selected_files(self, paths: list[Path]) -> None:
        if not paths:
            return
        created: list[Path] = []
        failed: list[str] = []
        for path in paths:
            src = path.expanduser().resolve()
            if not src.is_file():
                continue
            dest = _unique_duplicate_path(src)
            try:
                shutil.copy2(src, dest)
                created.append(dest)
            except OSError as exc:
                failed.append(f"{src.name}: {exc}")

        if self._current_folder:
            current = self._current_folder.resolve()
            self._populate_file_list(
                self._current_folder,
                new_outputs=[p for p in created if p.parent.resolve() == current],
                source_files=[
                    p.resolve() for p in paths if p.expanduser().resolve().parent == current
                ],
            )

        if failed:
            QMessageBox.warning(
                self,
                "Duplicate partially failed",
                f"Created {len(created)} copy/copies.\n\nFailed:\n" + "\n".join(failed[:8]),
            )
        elif created:
            self._set_status_message(
                f"Duplicated {len(created)} file(s)",
                5000,
            )

    def _delete_selected_files(self, paths: list[Path]) -> None:
        if not paths:
            return
        names = "\n".join(p.name for p in paths[:10])
        if len(paths) > 10:
            names += f"\n… and {len(paths) - 10} more"
        answer = QMessageBox.question(
            self,
            "Delete files",
            f"Permanently delete {len(paths)} file(s)?\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        failed: list[str] = []
        for path in paths:
            try:
                path.expanduser().resolve().unlink()
                deleted += 1
            except OSError as exc:
                failed.append(f"{path.name}: {exc}")

        if self._preview_tabs is not None:
            self._preview_tabs.close_paths(paths)

        if self._current_folder:
            self._populate_file_list(self._current_folder)

        if failed:
            QMessageBox.warning(
                self,
                "Delete partially failed",
                f"Deleted {deleted} file(s).\n\nFailed:\n" + "\n".join(failed[:8]),
            )
        else:
            self._set_status_message(f"Deleted {deleted} file(s)", 6000)

    def _open_files_in_preview_tabs(self, paths: list[Path]) -> None:
        if self._preview_tabs is None or not paths:
            return
        self._preview_tabs.open_files_in_tabs(paths)
        self._ensure_preview_visible()
        self._set_status_message(f"Opened {len(paths)} file(s) in tabs", 5000)

    def _create_folder(self) -> None:
        if not self._current_folder or not self._current_folder.is_dir():
            QMessageBox.warning(self, "Select folder", "Select a parent folder in the Folders panel first.")
            return
        name, ok = QInputDialog.getText(self, "Create folder", "Folder name:")
        if not ok or not name.strip():
            return
        new_dir = self._current_folder / name.strip()
        try:
            new_dir.mkdir(parents=False, exist_ok=False)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Create folder failed", str(exc))
            return
        self._refresh_tree()
        self._on_folder_selected(self._current_folder)

    def _copy_files_to_folder(self, target_dir: Path, files: list[Path]) -> None:
        if not target_dir.is_dir():
            return
        copied = 0
        failed = []
        for src in files:
            try:
                shutil.copy2(src, target_dir / src.name)
                copied += 1
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{src.name}: {exc}")
        self._set_status_message(f"Copied {copied} file(s) to {target_dir}", 7000)
        if failed:
            QMessageBox.warning(self, "Copy partially failed", "\n".join(failed[:10]))
        if self._current_folder == target_dir:
            self._on_folder_selected(target_dir)

    def _refresh_tree(self) -> None:
        roots = []
        for i in range(self._folder_tree.topLevelItemCount()):
            item = self._folder_tree.topLevelItem(i)
            raw = item.data(0, ROLE_PATH)
            if raw:
                roots.append(Path(str(raw)))
        keep_folder = (
            self._current_folder.expanduser().resolve()
            if self._current_folder is not None
            else None
        )
        self._folder_tree.clear()
        for root in roots:
            if root.is_dir():
                self._add_root_folder(root, select=False)
        if keep_folder is not None:
            keep_item = self._find_tree_item_for_path(keep_folder)
            if keep_item is not None:
                self._folder_tree.blockSignals(True)
                self._folder_tree.setCurrentItem(keep_item)
                self._folder_tree.blockSignals(False)
        self._update_directory_watchers()

    def _apply_function(self, func_name: str, *, preselected: list[Path] | None = None, **job_kwargs) -> None:
        selected = preselected or self._selected_files()
        if not selected:
            QMessageBox.information(self, "No sequence selected", "Select one or more sequence files in the Files panel.")
            return
        seq_files = [p for p in selected if p.suffix.lower() in _FASTA_SUFFIXES]
        if not seq_files:
            QMessageBox.warning(self, "Invalid selection", "Selected files do not include FASTA sequence files.")
            return
        if func_name in {"blast", "extend", "teaid", "flexidot"} and not self._project.has_genome_configured():
            QMessageBox.warning(
                self,
                "Genome required",
                f"Define genome under {self._genome_menu_hint()} before running this tool.",
            )
            return
        if func_name == "extend" and self._project.is_pan_genome_mode:
            names = self._pan_genome_names()
            extend_opts = job_kwargs.get("extend") or self._extend_options
            if names and not extend_opts.pan_genome_name:
                extend_opts = replace(extend_opts, pan_genome_name=names[0])
                job_kwargs["extend"] = extend_opts
        if func_name == "flexidot":
            if flexidot_executable() is None:
                QMessageBox.warning(
                    self,
                    "Flexidot not found",
                    "Flexidot is not on PATH.\n\nInstall with:\n  pip install flexidot\n\n"
                    "If it is installed, add your Python scripts directory to PATH "
                    "(e.g. ~/Library/Python/3.x/bin on macOS).",
                )
                return
        if func_name == "tsd_search":
            tsd_opts = job_kwargs.get("tsd_search_options") or self._tsd_search_options
            if tsd_opts.left_boundary <= 0 or tsd_opts.right_boundary <= 0:
                dialog = TsdSearchParamsDialog(
                    initial=tsd_opts,
                    title="TSD search parameters",
                    parent=self,
                )
                if not dialog.exec():
                    return
                tsd_opts = dialog.options()
                job_kwargs["tsd_search_options"] = tsd_opts
            if tsd_opts.left_boundary >= tsd_opts.right_boundary:
                QMessageBox.warning(
                    self,
                    "TSD search",
                    "Left boundary must be less than the right boundary.",
                )
                return
        self._start_background_job(
            FunctionWorker(self._run_function_job, func_name, seq_files, job_kwargs),
            job_title=func_name,
            total_steps=self._job_total_steps(func_name, seq_files, job_kwargs),
            source_files=seq_files,
            on_finished=self._on_worker_finished,
            on_failed=self._on_worker_failed,
        )

    def _plugin_job_source_files(self, plugin: UserCommandPlugin, work_dir: Path) -> list[Path]:
        runtime = getattr(plugin, "_job_options", {}).get("runtime_values") or {}
        sources: list[Path] = []
        for name, defn in plugin._defs.items():
            if name in plugin.spec.output_vars:
                continue
            if not is_file_var_mode(defn.mode):
                continue
            raw = str(runtime.get(name, "")).strip()
            if not raw:
                continue
            path = Path(raw).expanduser()
            if path.is_file():
                sources.append(path.resolve())
        resolved_work_dir = work_dir.expanduser().resolve()
        if resolved_work_dir.is_dir():
            sources.append(resolved_work_dir)
        return sources

    def _command_plugin_work_dir(self, plugin: UserCommandPlugin) -> Path:
        runtime = getattr(plugin, "_job_options", {}).get("runtime_values") or {}
        for name, defn in plugin._defs.items():
            if not is_path_var_mode(defn.mode):
                continue
            raw = str(runtime.get(name, "")).strip()
            if not raw:
                continue
            path = Path(raw).expanduser()
            if path.is_file():
                return path.parent.resolve()
            if path.is_dir():
                return path.resolve()
            if path.parent.exists():
                return path.parent.resolve()
        if self._current_folder and self._current_folder.is_dir():
            return self._current_folder.expanduser().resolve()
        if self._project.input_dir and self._project.input_dir.is_dir():
            return self._project.input_dir.expanduser().resolve()
        return Path.cwd()

    def _apply_plugin(self, plugin_id: str, *, preselected: list[Path] | None = None) -> None:
        plugin = self._plugin_registry.get(plugin_id)
        if plugin is None:
            QMessageBox.warning(self, "Plugin", f"Plugin not found: {plugin_id}")
            return
        if isinstance(plugin, UserCommandPlugin):
            if not plugin.prepare_job(self, [], self._project):
                return
            work_dir = self._command_plugin_work_dir(plugin)
            files = [work_dir]
            error = plugin.validate(files, self._project)
            if error:
                QMessageBox.warning(self, plugin.label, error)
                return
            runtime = getattr(plugin, "_job_options", {}).get("runtime_values") or {}
            existing_outputs = [
                path
                for path in existing_output_files(
                    plugin.spec,
                    plugin._defs,
                    runtime_values=runtime,
                    work_dir=work_dir,
                )
                if path.is_file()
            ]
            if existing_outputs:
                listing = "\n".join(f"  • {path}" for path in existing_outputs)
                answer = QMessageBox.question(
                    self,
                    plugin.label,
                    "The following output path(s) already exist:\n\n"
                    f"{listing}\n\n"
                    "Running this plugin may overwrite them. Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            func_name = f"plugin:{plugin_id}"
            self._start_background_job(
                FunctionWorker(self._run_plugin_job, func_name, files, {}),
                job_title=func_name,
                total_steps=self._job_total_steps(func_name, files, {}),
                source_files=self._plugin_job_source_files(plugin, work_dir),
                on_finished=self._on_worker_finished,
                on_failed=self._on_worker_failed,
            )
            return
        selected = preselected or self._selected_files()
        initial: list[Path] = []
        if selected:
            initial = self._plugin_registry.filter_files(
                plugin,
                [path.expanduser().resolve() for path in selected],
            )
        if not initial and not plugin.picks_files_in_dialog and plugin.needs_selected_files:
            if plugin.fasta_only:
                QMessageBox.information(
                    self,
                    plugin.label,
                    "Select one or more FASTA files in the Files panel.",
                )
            else:
                QMessageBox.information(
                    self,
                    plugin.label,
                    "Select files in the Files panel.",
                )
            return
        if not plugin.prepare_job(self, initial, self._project):
            return
        job_options = getattr(plugin, "_job_options", {})
        raw_files = job_options.get("query_files") or [str(path) for path in initial]
        files = self._plugin_registry.filter_files(
            plugin,
            [Path(str(path)).expanduser().resolve() for path in raw_files],
        )
        if not files:
            if plugin.fasta_only:
                QMessageBox.warning(
                    self,
                    plugin.label,
                    "No valid query FASTA files were selected.",
                )
            else:
                QMessageBox.warning(self, plugin.label, "No files match this plugin.")
            return
        error = plugin.validate(files, self._project)
        if error:
            QMessageBox.warning(self, plugin.label, error)
            return
        func_name = f"plugin:{plugin_id}"
        self._start_background_job(
            FunctionWorker(self._run_plugin_job, func_name, files, {}),
            job_title=func_name,
            total_steps=self._job_total_steps(func_name, files, {}),
            source_files=files,
            on_finished=self._on_worker_finished,
            on_failed=self._on_worker_failed,
        )

    def _populate_plugins_menu_actions(self) -> None:
        if self._plugins_menu is None:
            return
        loaded_plugins = self._plugin_registry.all_plugins()
        if loaded_plugins:
            for plugin in loaded_plugins:
                self._plugins_menu.addAction(
                    plugin.label,
                    lambda checked=False, pid=plugin.id: self._apply_plugin(pid),
                )
        else:
            none_action = self._plugins_menu.addAction("(No plugins loaded)")
            none_action.setEnabled(False)

    def _rebuild_plugins_menu(self) -> None:
        if self._plugins_menu is None:
            return
        self._plugins_menu.clear()
        self._plugins_menu.addAction("Manage plugins…", self._open_plugin_manager)
        self._plugins_menu.addAction("Design your plugin…", self._open_command_plugin_designer)
        self._plugins_menu.addSeparator()
        self._populate_plugins_menu_actions()

    def _open_plugin_manager(self) -> None:
        dialog = PluginManageDialog(
            self._plugin_registry,
            on_save=self._save_designed_plugin,
            on_delete=self._delete_custom_plugin,
            parent=self,
        )
        exec_modal_dialog(dialog)

    def _delete_custom_plugin(self, plugin_id: str) -> bool:
        if not delete_user_command_plugin_spec(plugin_id):
            return False
        self._plugin_registry.unregister(plugin_id)
        self._rebuild_plugins_menu()
        self._rebuild_top_toolbar()
        self._set_status_message(f"Deleted plugin {plugin_id}", 5000)
        return True

    def _open_command_plugin_designer(self) -> None:
        if self._command_plugin_dialog is not None and self._command_plugin_dialog.isVisible():
            self._command_plugin_dialog.raise_()
            self._command_plugin_dialog.activateWindow()
            return
        dialog = CommandPluginDesignerDialog(parent=self)
        self._command_plugin_dialog = dialog
        dialog.setModal(False)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.accepted.connect(lambda d=dialog: self._save_designed_plugin(d.spec()))
        dialog.finished.connect(self._on_command_plugin_dialog_finished)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_command_plugin_dialog_finished(self, _code: int) -> None:
        if self._command_plugin_dialog is not None:
            self._command_plugin_dialog.deleteLater()
            self._command_plugin_dialog = None

    def _save_designed_plugin(self, spec, *, previous_id: str | None = None) -> None:
        plugin = UserCommandPlugin(spec)
        try:
            if previous_id and previous_id != spec.id:
                delete_user_command_plugin_spec(previous_id)
                self._plugin_registry.unregister(previous_id)
            was_existing = self._plugin_registry.get(spec.id) is not None
            save_user_command_plugin_spec(spec)
            self._plugin_registry.register_or_replace(plugin)
            self._rebuild_plugins_menu()
            self._rebuild_top_toolbar()
            if was_existing or (previous_id and previous_id != spec.id):
                self._set_status_message(f"Updated plugin {spec.label}", 5000)
            else:
                self._set_status_message(f"Added plugin {spec.label}", 5000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Design your plugin", str(exc))

    def _run_plugin_job(
        self,
        func_name: str,
        seq_files: list[Path],
        progress_cb,
        **job_kwargs: Any,
    ) -> dict:
        plugin_id = func_name[len("plugin:") :]
        return self._plugin_registry.run_plugin(
            plugin_id,
            seq_files,
            self._project,
            progress_cb,
            max_workers=self._project.batch_workers,
        )

    def _run_function_job(
        self,
        func_name: str,
        seq_files: list[Path],
        progress_cb,
        **job_kwargs: Any,
    ):
        return run_batch(
            func_name,
            seq_files,
            self._project,
            progress_cb,
            max_workers=self._project.batch_workers,
            cancel=self._job_cancel,
            **job_kwargs,
        )

    def _start_background_job(
        self,
        worker: FunctionWorker | AlignWorker,
        *,
        job_title: str,
        total_steps: int,
        source_files: list[Path] | None = None,
        on_finished,
        on_failed,
    ) -> None:
        if self._worker_thread is not None:
            QMessageBox.information(
                self,
                "Job already running",
                "Wait for the current job to finish before starting another. "
                "You can still browse folders and preview files while it runs.",
            )
            return

        self._last_job_source_files = list(source_files or [])
        self._job_cancel.reset()
        self._show_job_progress(job_title, total_steps)
        self._set_job_actions_enabled(False)

        self._worker_thread = QThread(self)
        self._worker = worker
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_job_progress)
        self._worker.finished.connect(self._finish_background_job)
        self._worker.failed.connect(self._finish_background_job)
        self._worker.finished.connect(on_finished)
        self._worker.failed.connect(on_failed)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.failed.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_worker)
        self._worker_thread.finished.connect(self._update_status)
        self._worker_thread.start()

    @Slot(int, str)
    def _on_job_progress(self, value: int, label: str) -> None:
        if self._task_progress is not None:
            self._task_progress.update(value, self._parse_progress_filename(label))

    @Slot()
    def _finish_background_job(self) -> None:
        self._hide_job_progress()
        self._set_job_actions_enabled(True)

    def _set_job_actions_enabled(self, enabled: bool) -> None:
        for control in self._job_toolbar_actions:
            control.setEnabled(enabled)

    def _refresh_folders_after_job(
        self,
        created_paths: list[Path],
        source_paths: list[Path],
        *,
        extra_folders: set[Path] | None = None,
    ) -> None:
        """Refresh file list; show outputs in each input file's folder."""
        touched = {p.parent.resolve() for p in created_paths} | {
            p.parent.resolve() for p in source_paths
        }
        if extra_folders:
            touched |= {folder.resolve() for folder in extra_folders}
        for folder in touched:
            ancestor = folder.parent
            while ancestor != ancestor.parent:
                item = self._find_tree_item_for_path(ancestor)
                if item is not None:
                    self._refresh_subfolders_under(ancestor)
                    break
                ancestor = ancestor.parent

        current = self._current_folder.resolve() if self._current_folder else None
        if current is not None and current in touched:
            self._populate_file_list(
                current,
                new_outputs=[p for p in created_paths if p.parent.resolve() == current],
                source_files=[p for p in source_paths if p.parent.resolve() == current],
            )
            return

        if created_paths:
            target = created_paths[0].parent.resolve()
            self._navigate_to_folder(
                target,
                new_outputs=[p for p in created_paths if p.parent.resolve() == target],
                source_files=[p for p in source_paths if p.parent.resolve() == target],
            )
        elif source_paths and self._current_folder:
            self._populate_file_list(self._current_folder)

    @Slot(dict)
    def _on_worker_finished(self, result: dict) -> None:
        created_paths: list[Path] = []
        for raw in result.get("created_outputs", []):
            path = Path(str(raw)).expanduser()
            if path.is_file():
                created_paths.append(path.resolve())
            elif path.is_dir():
                created_paths.append(path.resolve())

        source_paths: list[Path] = []
        extra_folders: set[Path] = set()
        for raw in result.get("source_files", []):
            path = Path(str(raw)).expanduser()
            if path.is_file():
                source_paths.append(path.resolve())
            elif path.is_dir():
                extra_folders.add(path.resolve())

        self._refresh_folders_after_job(
            created_paths,
            source_paths,
            extra_folders=extra_folders,
        )
        func_name = result.get("func_name")
        if func_name == "te_annotation":
            fasta_sources = [
                p for p in source_paths if p.suffix.lower() in _FASTA_SUFFIXES
            ]
            if fasta_sources:
                self._auto_open_outputs(fasta_sources)
        elif func_name and str(func_name).startswith("plugin:"):
            preview_files = [p for p in created_paths if p.is_file()]
            self._auto_open_outputs(preview_files)
        else:
            self._auto_open_outputs(created_paths)

        pending_viz = self._pending_te_viz
        pending_fastas = self._pending_te_genome_map_fastas
        pending_map_opts = self._pending_te_genome_map
        if pending_viz and result.get("func_name") == "blast":
            self._pending_te_viz = None
            self._pending_te_genome_map_fastas = []
            self._pending_te_genome_map = None
            resolved = self._resolve_te_viz_hit_paths_and_kinds(pending_viz)
            if resolved is None:
                QMessageBox.warning(
                    self,
                    "TE genome map",
                    "Blast finished but a BLAST table for the TE consensus was not found.",
                )
            else:
                te_paths, te_kinds = resolved
                self._open_blast_genome_map(
                    te_paths,
                    gene_files=pending_viz.gene_paths,
                    methylation_files=pending_viz.methylation_paths,
                    te_input_kinds=te_kinds,
                    map_options=pending_viz.map_options,
                )
        elif pending_fastas and result.get("func_name") == "blast":
            self._pending_te_genome_map_fastas = []
            self._pending_te_genome_map = None
            self._open_te_genome_map_after_blast(pending_fastas, pending_map_opts, result)

        failures = result.get("failures", [])
        done_n = result["total"] - len(failures)
        title = MainWindow._job_display_title(func_name)
        summary = f"{title} finished — {done_n}/{result['total']} sequence(s)"
        if created_paths:
            names = ", ".join(p.name for p in created_paths[:4])
            if len(created_paths) > 4:
                names += ", …"
            summary += f" — created: {names}"
        self._set_status_message(summary, 12000)

        if failures:
            msg = summary + "\n\nFailures:\n" + "\n".join(failures[:8])
            if len(failures) > 8:
                msg += "\n..."
            QMessageBox.warning(self, "Function completed with issues", msg)

    @Slot(str)
    def _on_worker_failed(self, error: str) -> None:
        self._pending_te_genome_map_fastas = []
        self._pending_te_genome_map = None
        self._pending_te_viz = None
        if error == CANCELLED_MESSAGE:
            self._set_status_message("Stopped", 6000)
            return
        self._set_status_message("Job failed", 8000)
        QMessageBox.critical(self, "Function failed", error)

    def _cleanup_worker(self) -> None:
        cancelled = self._job_cancel.requested
        if cancelled:
            self._job_cancel.reset()
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._worker_thread:
            self._worker_thread.deleteLater()
            self._worker_thread = None
        if cancelled:
            self._set_status_message("Stopped", 6000)
        self._update_status()

    def _stop_current_job(self) -> None:
        """Stop currently running background job/map build."""
        if not (
            self._worker_thread is not None
            or self._genome_map_thread is not None
            or self._benchmark_thread is not None
        ):
            self._set_status_message("No running task to stop", 3000)
            return

        self._job_cancel.request()
        self._pending_te_genome_map_fastas = []
        self._pending_te_genome_map = None
        self._pending_te_viz = None
        self._queued_genome_map_jobs.clear()
        self._finish_background_job()
        self._set_status_message("Stopping…", 8000)

        threads: list[QThread] = []
        if self._worker_thread is not None:
            threads.append(self._worker_thread)
        if self._genome_map_thread is not None:
            threads.append(self._genome_map_thread)
        if self._benchmark_thread is not None:
            threads.append(self._benchmark_thread)

        for thread in threads:
            if thread.isRunning():
                thread.requestInterruption()
                thread.quit()

        for thread in threads:
            if not thread.isRunning():
                continue
            if thread.wait(5000):
                continue
            logger.warning("Background thread did not stop in time; terminating.")
            thread.terminate()
            thread.wait(3000)

    def _open_te_genome_map_after_blast(
        self,
        fasta_paths: list[Path],
        map_options: TeGenomeMapOptions | None,
        result: dict,
    ) -> None:
        failed_names: set[str] = set()
        for entry in result.get("failures", []):
            text = str(entry)
            if ": " in text:
                failed_names.add(text.split(": ", 1)[0].strip())
            else:
                failed_names.add(text.strip())
        queued: list[Path] = []
        for fasta in fasta_paths:
            if fasta.name in failed_names:
                continue
            blast_txt = find_blast_table_for_query(fasta)
            if blast_txt is not None:
                queued.append(blast_txt)
        if queued:
            self._enqueue_genome_map_jobs(queued, map_options)
        else:
            QMessageBox.warning(
                self,
                "TE genome map",
                "Blast finished but the BLAST table for the TE genome map was not found.",
            )

    def _pick_preview_output(self, created_paths: list[Path]) -> Path | None:
        """Prefer HTML/PDF/images for preview after TEAid / Flexidot / genome map."""
        if not created_paths:
            return None
        files = [p.resolve() for p in created_paths if p.is_file()]
        if not files:
            return None
        for path in files:
            if path.name.endswith("_sankey.html"):
                return path
        for path in files:
            if path.name.endswith("_library_benchmark.html"):
                return path
        for path in files:
            if path.name.endswith("_genome_map_region.html") or path.name.endswith(
                "_blast_genome_map_region.html"
            ):
                return path
        for path in files:
            if path.name.endswith("_genome_map.html") or path.name.endswith(
                "_blast_genome_map.html"
            ):
                return path
        in_folder = [
            p
            for p in files
            if self._current_folder and p.parent.resolve() == self._current_folder.resolve()
        ]
        search = in_folder if in_folder else files
        previewable = [p for p in search if is_previewable_file(p)]
        if not previewable:
            return None
        for suffix in (".html", ".htm", ".pdf", ".png", ".jpg", ".jpeg", ".svg"):
            for path in previewable:
                if path.suffix.lower() == suffix:
                    return path
        return min(previewable, key=preview_path_priority)

    def _auto_open_outputs(self, created_paths: list[Path]) -> None:
        target = self._pick_preview_output(created_paths)
        if target is None:
            return
        self._open_preview_tab(target, replace=True)

    def _update_status(self) -> None:
        if self._job_running:
            return
        if self._current_folder and self._cached_folder_files is not None:
            visible = sum(
                1
                for i in range(self._file_list.count())
                if self._file_list.item(i).data(ROLE_PATH)
            )
            self._sync_files_status(visible, len(self._cached_folder_files))
            return
        parts = ["TEviewer"]
        if self._project.input_dir:
            parts.append(self._project.input_dir.name)
        if self._project.is_pan_genome_mode:
            parts.append(f"pan ({len(self._project.pan_genomes)})")
        elif self._project.genome_file:
            parts.append(self._project.genome_file.name)
        self._set_status_message(" · ".join(parts))

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About TEviewer",
            f"<b>TEviewer</b> {__version__}<br>"
            "Folder-based TE analysis workspace (PySide6).<br>"
            "Dockable panels; double-click FASTA opens AliView (unless system viewer is enabled).<br>"
            "<a href='https://github.com/qjiangzhao/TEtrimmer'>TEtrimmer</a>",
        )

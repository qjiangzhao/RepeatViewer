"""Tools > Primers and Probes in the main window (Design, Map, Database, painting).

Kept out of ``main_window.py``: :class:`PrimerActionsMixin` is mixed into
``MainWindow`` and only uses the window's shared job / dialog helpers
(``_present_te_viz_dialog``, ``_start_background_job``,
``_attach_process_monitor``, ``_populate_file_list`` ...).

Developer: Abdullah Yusuf
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QMenu, QMessageBox

from repeatviewer.backends.job_cancel import CANCELLED_MESSAGE
from repeatviewer.job_options import (
    PrimerOptions,
    load_primer_options,
    save_primer_options,
)

PRIMER_JOB_DESIGN = "design"
PRIMER_JOB_MAP = "map"
PRIMER_JOB_PAINTING = "painting"
PRIMER_TOOL_KEY = "primers"
_FASTA_SUFFIXES = (".fa", ".fasta", ".fna", ".fas", ".fsa", ".ffn", ".seq", ".aln", ".mfa")

# Progress phases for the bottom bar (status text, bar slice).
_PHASES = (
    ("Reading", 0),
    ("Masking", 1),
    ("Designing", 1),
    ("Scoring", 1),
    ("Testing", 1),
    ("Searching", 2),
    ("Checking", 2),
    ("Running Chorus2", 1),
    ("Selecting", 2),
    ("Writing", 3),
)
PRIMER_JOB_STEPS = 4

# Tools > Primers and Probes: three items; the design type is the Mode inside Design.
# Tools > Primers and Probes. Design and Map open submenus; everything else is
# one item. Nothing here opens a tool window of its own: an item shows the work
# in the main window and selects the page it belongs to.
PRIMER_MENU_ITEMS: tuple[str, ...] = (
    "Design", "Map", "Database", "In-silico PCR", "Restriction Digest", "Gel",
    "Sanger Check", "Cloning",
)
DESIGN_SUBMENU_ITEMS: tuple[str, ...] = (
    "Primers", "Repetitive Probes", "Chromosome Painting Probes",
)
MAP_SUBMENU_ITEMS: tuple[str, ...] = ("Primers", "Repetitive Probes")
PRIMER_MANUAL = Path(__file__).resolve().parent / "assets" / "manuals" / "primers_and_probes.html"


def is_primer_fasta(path: Path) -> bool:
    name = Path(path).name.lower()
    if name.endswith(".gz"):
        name = name[:-3]
    return name.endswith(_FASTA_SUFFIXES)


def phase_step(message: str) -> int:
    for prefix, step in _PHASES:
        if message.startswith(prefix):
            return step
    return 1


class PrimerJobWorker(QObject):
    """Design or map primers off the UI thread."""

    progress = Signal(int, str)
    log_line = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, kind: str, seq_files: list[Path], settings, *, report_path: Path | None,
                 annotate: bool = True, database_path: str = "",
                 save_to_database: bool = False, cancel=None) -> None:
        super().__init__()
        self._kind = kind
        self._seq_files = list(seq_files)
        self._settings = settings
        self._report_path = report_path
        self._annotate = annotate
        self._database_path = database_path
        self._save_to_database = save_to_database
        self._cancel = cancel

    def _cancelled(self) -> bool:
        return bool(self._cancel is not None and getattr(self._cancel, "requested", False))

    @Slot()
    def run(self) -> None:
        from repeatviewer.backends.primers import jobs as pj
        from repeatviewer.backends.primers.binding import PrimerCancelled
        from repeatviewer.backends.primers.thermo import PrimerError
        from repeatviewer.external_process import process_log_sink

        def _log(message: str) -> None:
            self.log_line.emit(str(message))

        def _progress(message: str) -> None:
            self.progress.emit(phase_step(message), message)
            self.log_line.emit(message)

        db_path = Path(self._database_path).expanduser() if self._database_path else None
        try:
            with process_log_sink(_log):
                self.progress.emit(0, "Reading templates…")
                if self._kind == PRIMER_JOB_PAINTING:
                    from repeatviewer.backends.primers import painting as pt

                    main, files, payload = pt.run_painting(
                        self._settings, report_path=self._report_path,
                        cancel=self._cancel, progress=_progress)
                elif self._kind == PRIMER_JOB_MAP:
                    main, files, payload = pj.run_map(
                        self._seq_files, self._settings, database_path=db_path,
                        progress=_progress, cancel=self._cancelled,
                        report_path=self._report_path)
                else:
                    # Nothing is written onto the sequences here: the user picks
                    # the pairs to add afterwards (Designed Primers window).
                    main, files, payload = pj.run_design(
                        self._seq_files, self._settings, progress=_progress,
                        cancel=self._cancelled, annotate=False,
                        report_path=self._report_path)
                saved = 0
                if self._kind == PRIMER_JOB_DESIGN and self._save_to_database and payload.get("pairs"):
                    saved = len(pj.save_pairs_to_database(payload, db_path))
            self.progress.emit(PRIMER_JOB_STEPS - 1, "Writing results…")
            self.finished.emit({
                "kind": self._kind,
                "report": str(main),
                "files": [str(f) for f in files],
                "annotated": list(payload.get("annotated", [])),
                "pairs": len(payload.get("pairs", [])),
                "selected": int(payload.get("selected", 0)),
                "chorus_input": int(payload.get("input", 0)),
                "products": int((payload.get("counts") or {}).get("products", 0)),
                "sites": int((payload.get("counts") or {}).get("sites", 0)),
                "warnings": list(payload.get("warnings", [])),
                "saved_to_database": saved,
                "pair_list": list(payload.get("pairs", [])) if self._kind == PRIMER_JOB_DESIGN else [],
                "ask_pairs": bool(self._annotate) if self._kind == PRIMER_JOB_DESIGN else False,
                "inputs": [str(p) for p in self._seq_files],
            })
        except PrimerCancelled:
            self.failed.emit(CANCELLED_MESSAGE)
        except PrimerError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - surface to the UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class PrimerActionsMixin:
    """Tools > Primers for ``MainWindow``."""

    _primer_options: PrimerOptions
    _primer_database_dialog = None
    _primer_check_dialog = None

    # ------------------------------------------------------------- state

    def _init_primer_actions(self) -> None:
        self._primer_options = load_primer_options()
        self._primer_database_dialog = None
        self._primer_check_dialog = None
        try:
            from repeatviewer.views.primer_database_dialog import apply_lab_user_setting

            apply_lab_user_setting()
        except Exception:  # noqa: BLE001 - only the name in the history
            pass

    def _save_primer_options(self, opts: PrimerOptions, *,
                             database_path: str | None = None) -> None:
        """Save the primer settings. Only the Database window chooses the database
        (``database_path``); every other save keeps the current one."""
        keep = self._primer_options.database_path if database_path is None else database_path
        opts = replace(opts, database_path=keep)
        self._primer_options = opts
        save_primer_options(opts)

    # ------------------------------------------------------------- menu

    def _populate_primers_menu(self, menu: QMenu) -> None:
        from repeatviewer.backends.primers import design as dz

        # Submenus are made with their parent and kept by name: a submenu that
        # only a local variable holds can be freed by Python on some PySide
        # builds, and its items then do nothing when clicked.
        design_menu = QMenu(PRIMER_MENU_ITEMS[0], menu)
        menu.addMenu(design_menu)
        primers, probes, painting = DESIGN_SUBMENU_ITEMS
        a = design_menu.addAction(primers, lambda: self._design_in_panel(dz.MODE_PCR))
        a.setToolTip("PCR primers on the sequence, in the Primers panel")
        a = design_menu.addAction(probes, lambda: self._design_in_panel(dz.MODE_FISH))
        a.setToolTip("Oligo probes found in every copy of a repeat")
        a = design_menu.addAction(painting, self._open_painting_settings)
        a.setToolTip("Chromosome painting probes over a genome (Chorus2)")

        map_menu = QMenu(PRIMER_MENU_ITEMS[1], menu)
        menu.addMenu(map_menu)
        menu._rv_submenus = (design_menu, map_menu)
        a = map_menu.addAction(MAP_SUBMENU_ITEMS[0], lambda: self._open_map_primers_dialog())
        a.setToolTip("Where primers bind, and what they amplify")
        a = map_menu.addAction(MAP_SUBMENU_ITEMS[1],
                               lambda: self._open_map_primers_dialog(probes=True))
        a.setToolTip("Where probes bind, and how many copies they hit")

        a = menu.addAction(PRIMER_MENU_ITEMS[2], self._open_primer_database)
        a.setToolTip("Your saved primers, with Tm, hairpin and dimer checks")
        menu.addSeparator()
        populate = getattr(self, "_populate_pcr_menu_items", None)
        if populate is not None:
            populate(menu)
        menu.setToolTipsVisible(True)

    # ------------------------------------------------- the panel beside the sequence

    def _primers_workspace(self):
        """The open Primers and Probes workspace tab, or None."""
        from repeatviewer.views.primers_workspace import PrimersWorkspacePage

        tabs = getattr(self, "_preview_tabs", None)
        if tabs is None:
            return None
        try:
            for index in range(tabs.count()):
                page = tabs.widget(index)
                if isinstance(page, PrimersWorkspacePage):
                    return page
        except RuntimeError:
            pass
        return None

    def _panel_target_file(self):
        """The FASTA the workspace should work on.

        The one selected in Files, else the one the workspace already shows,
        else the file of the tab in front.
        """
        for p in self._primer_candidate_files():
            return Path(p)
        workspace = self._primers_workspace()
        if workspace is not None:
            return workspace.sequence_path()
        tabs = getattr(self, "_preview_tabs", None)
        current = tabs.currentWidget() if tabs is not None else None
        path = getattr(current, "path", None)
        return Path(path) if path else None

    def _leave_file_page_for_workspace(self, path: Path) -> bool:
        """Unsaved annotation edits in the file's own tab are settled first.

        The workspace saves primers into the same annotation file, so two views
        with different unsaved states would overwrite each other.
        """
        tabs = getattr(self, "_preview_tabs", None)
        if tabs is None:
            return True
        page = tabs.page_for_path(path)
        if page is None:
            return True
        try:
            if not page.has_unsaved_annotations():
                return True
        except (AttributeError, RuntimeError):
            return True
        return bool(tabs.confirm_leave_page(page))

    def _workspace_sequence_candidate(self):
        """The FASTA selected in Files, for a workspace that has no sequence yet."""
        for p in self._primer_candidate_files():
            return Path(p)
        return None

    def _ensure_primers_workspace(self):
        """The workspace tab, made (without a sequence) when there is none. None without tabs."""
        from repeatviewer.views.primers_workspace import PrimersWorkspacePage

        tabs = getattr(self, "_preview_tabs", None)
        if tabs is None:
            return None
        workspace = self._primers_workspace()
        if workspace is None:
            workspace = PrimersWorkspacePage()
            self._wire_primers_workspace(workspace)
            tabs.open_tool_tab(workspace, workspace.tab_name())
        return workspace

    def _host_in_workspace(self, section: str, page) -> bool:
        """Show a tool page (Map, Database, Sanger Check…) as a section of the workspace."""
        tabs = getattr(self, "_preview_tabs", None)
        workspace = self._ensure_primers_workspace()
        if tabs is None or workspace is None:
            return False
        workspace.host_page(section, page)
        tabs.setCurrentWidget(workspace)
        self._ensure_preview_visible()
        return True

    def _open_workspace_section(self, key: str) -> None:
        """A section clicked in the workspace that has no page yet: open it as its menu item does."""
        openers = {
            "painting": "_open_painting_settings",
            "map": "_open_map_primers_dialog",
            "database": "_open_primer_database",
            "gel": "_open_gel_document",
            "sanger": "_open_sanger_dialog",
            "cloning": "_open_cloning_dialog",
        }
        if str(key) == "gel":
            # A click on the section must not write a file: open the gel that is
            # selected in Files, else offer to start one.
            chosen = [p for p in self._selected_files()
                      if Path(p).is_file() and Path(p).suffix.lower() == ".rvgel"]
            workspace = self._primers_workspace()
            if chosen:
                self._show_new_output(Path(chosen[0]))
            elif workspace is not None:
                workspace.show_gel_placeholder(self._new_gel_document)
            return
        opener = getattr(self, openers.get(str(key), ""), None)
        if opener is not None:
            opener()

    def _wire_primers_workspace(self, workspace) -> None:
        status = getattr(self, "_set_status_message", None)
        if status is not None:
            workspace.statusMessage.connect(lambda text: status(str(text), 6000))
        workspace.sequence_provider = self._workspace_sequence_candidate
        workspace.sectionRequested.connect(self._open_workspace_section)
        opened = getattr(self, "_on_preview_open_requested", None)
        if opened is not None:
            workspace.openFileRequested.connect(opened)
        written = getattr(self, "_on_preview_file_written", None)
        if written is not None:
            workspace.fileWritten.connect(written)
        workspace.annotationsSaved.connect(self._on_workspace_annotations_saved)
        extracted = getattr(self, "_on_preview_sequence_extracted", None)
        if extracted is not None:
            workspace.sequenceExtracted.connect(extracted)
        tabs = getattr(self, "_preview_tabs", None)
        if tabs is not None and not getattr(self, "_workspace_follows_file_saves", False):
            tabs.annotationsSaved.connect(self._on_file_annotations_saved_for_workspace)
            self._workspace_follows_file_saves = True

    def _on_workspace_annotations_saved(self, written: object) -> None:
        """The workspace saved annotations: Files and the file's own tab follow."""
        saved = getattr(self, "_on_preview_annotations_saved", None)
        if saved is not None:
            saved(written)
        workspace = self._primers_workspace()
        tabs = getattr(self, "_preview_tabs", None)
        if workspace is not None and tabs is not None and workspace.sequence_path() is not None:
            tabs.reload_paths([workspace.sequence_path()])

    def _on_file_annotations_saved_for_workspace(self, written: object) -> None:
        """A file's own tab saved annotations: the workspace on that file follows."""
        workspace = self._primers_workspace()
        if workspace is None or not written:
            return
        try:
            saved = Path(str(written))
            sequence = workspace.sequence_path()
            if sequence is None or saved.parent.resolve() != sequence.parent.resolve():
                return
            if not (saved.name.startswith(sequence.stem + ".")
                    or saved.name.startswith(sequence.name)):
                return
        except OSError:
            return
        workspace.reload_annotations()

    def _primers_workspace_takes_file(self, path: Path) -> bool:
        """A file clicked in Files while the workspace is in front.

        A path field of the workspace that had the cursor takes it; a gel opens
        in the Gel section; a FASTA becomes the sequence when Design, PCR or
        Digest is shown. True when the click was used here, so Preview does not
        open the file. Right-click > Open in Additional Tab still opens it in a
        tab of its own.
        """
        from repeatviewer.views.primers_workspace import SEQUENCE_SECTIONS

        tabs = getattr(self, "_preview_tabs", None)
        workspace = self._primers_workspace()
        if tabs is None or workspace is None or tabs.currentWidget() is not workspace:
            return False
        try:
            target = Path(path)
            if not target.is_file():
                return False
            if workspace.fill_armed_path(target):
                return True
            if target.suffix.lower() == ".rvgel":
                workspace.show_gel(target)
                return True
            if workspace.section() not in SEQUENCE_SECTIONS or not is_primer_fasta(target):
                return False
        except OSError:
            return False
        if self._leave_file_page_for_workspace(target):
            workspace.set_sequence(target)
        return True

    def _open_primers_panel(self, *, tab: str = "design", mode: str | None = None,
                            digest: bool = False):
        """Show the Primers and Probes workspace on ``tab``; returns its PrimersPanel."""
        from repeatviewer.views.primers_workspace import (
            PANEL_DESIGN,
            PANEL_PRIMER,
            same_file,
            section_key,
        )

        path = self._panel_target_file()
        if path is None:
            QMessageBox.information(
                self, "Primers and Probes",
                "Click the FASTA to work on in the Files panel first.",
            )
            return None
        tabs = getattr(self, "_preview_tabs", None)
        if tabs is None:
            return None
        made = self._primers_workspace() is None
        workspace = self._ensure_primers_workspace()
        if (not same_file(path, workspace.sequence_path())
                and self._leave_file_page_for_workspace(path)):
            workspace.set_sequence(path)
        if not workspace.has_sequence():
            if made:
                index = tabs.indexOf(workspace)
                if index >= 0:
                    tabs._close_tab(index, ask=False)
            QMessageBox.information(
                self, "Primers and Probes",
                f"{path.name} has no sequence view, so the workspace cannot "
                "open on it. Click a FASTA in the Files panel and try again.",
            )
            return None
        tabs.setCurrentWidget(workspace)
        # Design opens on its settings, "primer" on the primers of the sequence.
        page = {"design": PANEL_DESIGN, "primer": PANEL_PRIMER}.get(tab)
        workspace.set_section(section_key(tab), page=page)
        self._ensure_preview_visible()
        primers = workspace.primers_panel()
        if mode is not None:
            pane = primers.design_pane
            modes = [pane.mode.itemData(i) for i in range(pane.mode.count())]
            if mode in modes:
                pane.mode.setCurrentIndex(modes.index(mode))
        if digest:
            enzymes = primers.enzyme_pane
            if enzymes.ticked_rows():
                enzymes.digest_button.click()
        return primers

    def _design_in_panel(self, mode: str) -> None:
        if not self._primers_ready():
            return
        self._open_primers_panel(tab="design", mode=mode)

    def _open_painting_settings(self) -> None:
        """Chromosome painting as a tab: a genome job, with its own settings panel."""
        if not self._primers_ready():
            return
        from repeatviewer.views.painting_page import PaintingPage

        tabs = getattr(self, "_preview_tabs", None)
        if tabs is None:
            return
        page = PaintingPage(options=self._primer_options,
                            start_job=self._start_painting_from_page)
        self._host_in_workspace("painting", page)
        self._painting_page = page

    def _start_painting_from_page(self, settings: dict) -> None:
        """Run Chorus2 (or the selection) with the settings of the painting tab."""
        opts = replace(self._primer_options, painting=dict(settings or {}))
        self._save_primer_options(opts)
        self._start_painting_job(self._primer_options)

    def _open_primers_manual(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from repeatviewer.user_manual import manual_page, open_manual

        # The chapter of the user manual replaces the separate primers page.
        if manual_page("12-primers") is not None:
            open_manual("12-primers")
            return
        if not PRIMER_MANUAL.is_file():
            QMessageBox.warning(self, "Primers and Probes Manual",
                                f"The manual is missing:\n{PRIMER_MANUAL}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(PRIMER_MANUAL)))

    # ------------------------------------------------------------- inputs

    def _primer_candidate_files(self) -> list[Path]:
        return [p for p in self._selected_files() if p.is_file() and is_primer_fasta(p)]

    def _primers_ready(self) -> bool:
        from repeatviewer.views.primer_dialogs import primer3_missing_message

        return not primer3_missing_message(self)

    # ------------------------------------------------------------- design

    def _run_primer_design_default(self) -> None:
        if not self._primers_ready():
            return
        from repeatviewer.backends.primers import design as dz

        if self._primer_options.design_settings().mode == dz.MODE_PAINTING:
            self._start_painting_job(self._primer_options, open_dialog_on_error=True)
            return
        files = self._primer_candidate_files()
        if not files:
            QMessageBox.information(
                self, "Primer Design",
                "Select the FASTA file to design primers on in the Files panel first.",
            )
            return
        self._start_primer_job(PRIMER_JOB_DESIGN, files, self._primer_options)

    def _quick_primer_design_right_click(self) -> None:
        self._run_primer_design_default()

    def _start_design_from_panel(self, payload: dict) -> None:
        """Design on the selected files with the settings of the Primers panel."""
        if not self._primers_ready():
            return
        files = self._primer_candidate_files()
        if not files:
            QMessageBox.information(
                self, "Primer Design",
                "Tick the FASTA files to design on in the Files panel first.",
            )
            return
        opts = replace(self._primer_options,
                       design=dict(payload.get("settings") or {}),
                       annotate_design=bool(payload.get("annotate_design", True)),
                       save_design_to_database=bool(payload.get("save_design_to_database")))
        self._save_primer_options(opts)
        self._start_primer_job(PRIMER_JOB_DESIGN, files, self._primer_options)

    # ------------------------------------------------------------- map

    @staticmethod
    def _selected_primer_slots(database_path: str, names: list[str]) -> dict | None:
        """Forward / Reverse / Probe for the primers selected in the Database, or None."""
        if not names:
            return None
        from repeatviewer.backends.primers import inventory as inv
        from repeatviewer.backends.primers import jobs as pj
        from repeatviewer.backends.primers.thermo import PrimerError

        try:
            db = inv.open_database(database_path or None)
        except (OSError, PrimerError):
            return None
        wanted = set(names)
        chosen = [p for p in db.primers if p.name in wanted]
        if len(chosen) != len(wanted):
            return None
        return pj.selection_slots(chosen)

    def _check_stock_map_data(self, primer_names: list[str], database_path: str,
                              strict: dict | None = None) -> dict:
        """Map Primers settings for "test these Database primers on a sequence"."""
        from repeatviewer.backends.primers import jobs as pj

        ms = self._primer_options.map_settings()
        data = ms.to_dict()
        data.update(mode=pj.MAP_DATABASE, primer_file="", search_forward=True,
                    search_reverse=True, search_probe=False, pairs_only=False,
                    use_max_mismatches=True, max_mismatches=max(2, ms.max_mismatches),
                    three_prime_exact=3, use_product_range=True, product_min=40,
                    product_max=max(3000, ms.product_max), test_on=pj.TEST_ON_SEQUENCES,
                    primer_names=list(primer_names or []))
        for key in ("product_min", "product_max", "max_mismatches", "three_prime_exact"):
            if strict and key in strict:
                data[key] = int(strict[key])
        slots = self._selected_primer_slots(database_path, primer_names or [])
        if slots:
            # A pair (or one primer, or a pair and a probe) goes straight into the
            # Forward / Reverse / Probe boxes, so the window shows what is tested.
            data.update(mode=pj.MAP_SPECIFIC, primer_names=[],
                        use_forward=pj.KIND_FORWARD in slots,
                        forward=slots.get(pj.KIND_FORWARD, ""),
                        use_reverse=pj.KIND_REVERSE in slots,
                        reverse=slots.get(pj.KIND_REVERSE, ""),
                        use_probe=pj.KIND_PROBE in slots,
                        probe=slots.get(pj.KIND_PROBE, ""))
        return data

    def _open_primer_check(self, database_path: str, primer_names: list[str]) -> None:
        """Database › Check a Sequence: the small window for the selected primers."""
        if not self._primers_ready():
            return
        from repeatviewer.backends.primers import inventory as inv
        from repeatviewer.backends.primers.thermo import PrimerError
        from repeatviewer.views.primer_check_dialog import CheckPrimersDialog

        old = self._primer_check_dialog
        if old is not None:
            try:
                old.close()
            except RuntimeError:
                pass
        try:
            db = inv.open_database(database_path or None)
        except (OSError, PrimerError) as exc:
            QMessageBox.warning(self, "Check Primers", str(exc))
            return
        owner = self._primer_database_dialog or self
        files = self._primer_candidate_files()
        dialog = CheckPrimersDialog(
            db, list(primer_names), thermo=self._primer_options.map_settings().thermo,
            sequence=files[0] if files else None, parent=owner)
        self._primer_check_dialog = dialog

        def _run(values: dict) -> None:
            data = self._check_stock_map_data(values["primer_names"], database_path, values)
            opts = replace(self._primer_options, map=data)
            self._start_primer_job(PRIMER_JOB_MAP, [Path(values["sequence"])], opts)

        def _all(values: dict) -> None:
            QTimer.singleShot(0, lambda: self._open_map_primers_dialog(
                check_stock=True, primer_names=values["primer_names"],
                database_path=database_path, strict=values,
                sequence=values.get("sequence") or ""))

        def _closed(_code: int) -> None:
            if self._primer_check_dialog is dialog:
                self._primer_check_dialog = None
            dialog.deleteLater()

        dialog.runRequested.connect(_run)
        dialog.allSettingsRequested.connect(_all)
        dialog.finished.connect(_closed)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _open_map_primers_dialog(self, *, check_stock: bool = False,
                                 primer_names: list[str] | None = None,
                                 database_path: str = "", strict: dict | None = None,
                                 sequence: str = "", probes: bool = False) -> None:
        """Map as a tab: where the primers bind on the selected files.

        ``probes``: a probe binds on its own, so no pairs, no products and no
        3' end rule. ``check_stock``: the Database asked to test its primers.
        """
        if not self._primers_ready():
            return
        from repeatviewer.views.map_page import MapPage

        opts = self._primer_options
        if check_stock:
            data = self._check_stock_map_data(list(primer_names or []), database_path, strict)
            opts = replace(opts, map=data)
        elif opts.map.get("primer_names"):
            # A selection from the Database window is for that one check only.
            opts = replace(opts, map={**opts.map, "primer_names": []})
        if probes:
            opts = replace(opts, map={**opts.map, "search_forward": False,
                                      "search_reverse": False, "search_probe": True,
                                      "pairs_only": False, "three_prime_exact": 0,
                                      "use_max_mismatches": True})
        files = self._primer_candidate_files()
        if sequence:
            files = [Path(sequence)] + [p for p in files if str(p) != sequence]
        page = MapPage(files, options=opts,
                       database_path=database_path or opts.database_path)
        if getattr(self, "_preview_tabs", None) is None:
            return
        self._host_in_workspace("map", page)
        self._map_page = page

    def _quick_map_primers_right_click(self) -> None:
        if not self._primers_ready():
            return
        files = self._primer_candidate_files()
        if not files:
            self._open_map_primers_dialog()
            return
        self._start_primer_job(PRIMER_JOB_MAP, files, self._primer_options)

    # ------------------------------------------------------------- database

    def _open_primer_database(self) -> None:
        if not self._primers_ready():
            return
        from repeatviewer.views.primer_dialogs import PrimerDatabaseDialog

        tabs = getattr(self, "_preview_tabs", None)
        existing = self._primer_database_dialog
        if existing is not None and tabs is not None:
            # already open as the Database section of the workspace: show it
            try:
                workspace = self._primers_workspace()
                holder = getattr(existing, "parent", lambda: None)()
                if (workspace is not None and holder is not None
                        and workspace.hosted_page("database") is holder):
                    tabs.setCurrentWidget(workspace)
                    workspace.set_section("database")
                    self._ensure_preview_visible()
                    return
            except RuntimeError:
                self._primer_database_dialog = None
        path = self._primer_options.database_path or None
        dialog = PrimerDatabaseDialog(
            Path(path) if path else None,
            thermo=self._primer_options.map_settings().thermo,
            parent=self,
        )
        self._primer_database_dialog = dialog

        def _path_changed(new_path: str) -> None:
            self._save_primer_options(self._primer_options, database_path=new_path)
            self._set_status_message(
                f"Primer Database: {new_path or 'the database on this computer'}", 6000)

        dialog.databasePathChanged.connect(_path_changed)
        dialog.checkSequenceRequested.connect(
            lambda p, names: self._open_primer_check(str(p or ""), list(names)))

        def _closed(_code: int) -> None:
            if self._primer_database_dialog is dialog:
                self._primer_database_dialog = None
            dialog.deleteLater()

        dialog.finished.connect(_closed)
        if tabs is None:            # no preview area (tests, headless): the old window
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            return
        from repeatviewer.views.tool_page import ToolDialogPage

        if dialog.layout() is not None:
            dialog.layout().setContentsMargins(12, 6, 12, 12)
        page = ToolDialogPage(dialog, "Primer Database")
        self._host_in_workspace("database", page)

    # ------------------------------------------------------------- jobs

    def _start_painting_job(self, opts: PrimerOptions, *, open_dialog_on_error: bool = False) -> None:
        """Chromosome painting: run Chorus2 here or import its BED, then select."""
        from repeatviewer.backends.primers import painting as pt

        ps = opts.painting_settings()
        if ps.source == pt.SOURCE_IMPORT:
            anchor = ps.import_bed
            problem = ("Choose the Chorus2 BED to import (Design, Chorus2 tab)." if not anchor
                       else "" if Path(anchor).expanduser().is_file()
                       else f"The Chorus2 BED does not exist:\n{anchor}")
        else:
            anchor = ps.genome_fasta
            problem = ("Choose the genome FASTA (Design, Chorus2 tab)." if not anchor
                       else "" if Path(anchor).expanduser().is_file()
                       else f"The genome FASTA does not exist:\n{anchor}")
            if not problem:
                inst = pt.find_chorus2(ps.conda_env)
                if not inst.ok:
                    problem = (inst.message + "\n\n" + pt.install_help()
                               + "\n\nOr run it on a server and choose \u201cImport results "
                               "from the server\u201d.")
        if problem:
            if open_dialog_on_error:
                self._open_painting_settings()
            QMessageBox.information(self, "Chromosome painting", problem)
            return
        self._start_primer_job(PRIMER_JOB_PAINTING, [Path(anchor).expanduser()], opts)

    def _confirm_primer_report_path(self, kind: str, files: list[Path]) -> Path | None | bool:
        """Rule 9: ask before an existing report is replaced. False = cancelled."""
        from repeatviewer.backends.primers import jobs as pj
        from repeatviewer.backends.primers import painting as pt
        from repeatviewer.widgets.file_conflict import confirm_existing_file_path

        tag = {PRIMER_JOB_MAP: pj.MAP_TAG, PRIMER_JOB_PAINTING: pt.PAINTING_TAG}.get(
            kind, pj.DESIGN_TAG)
        proposed = pj.default_report_path(files[0], tag)
        title = {PRIMER_JOB_MAP: "Map Primers", PRIMER_JOB_PAINTING: "Chromosome painting"}.get(
            kind, "Primer Design")
        chosen = confirm_existing_file_path(self, proposed, title=title,
                                            required_suffix=pj.REPORT_SUFFIX)
        if chosen is None:
            return False
        return chosen

    def _start_primer_job(self, kind: str, files: list[Path], opts: PrimerOptions) -> None:
        files = [Path(p) for p in files]
        report_path = self._confirm_primer_report_path(kind, files)
        if report_path is False:
            return
        if kind == PRIMER_JOB_PAINTING:
            settings = opts.painting_settings()
            title = f"Chromosome painting (Chorus2) on {files[0].name}"
        elif kind == PRIMER_JOB_MAP:
            settings = opts.map_settings()
            title = (f"Map Primers on {files[0].name}" if len(files) == 1
                     else f"Map Primers on {len(files)} files")
        else:
            from repeatviewer.backends.primers import design as dz

            settings = opts.design_settings()
            label = dz.MODE_LABELS.get(settings.mode, "Primers")
            title = f"Primer Design ({label}) on {files[0].name}"
        worker = PrimerJobWorker(
            kind, files, settings,
            report_path=report_path,
            annotate=(opts.annotate_design if kind == PRIMER_JOB_DESIGN
                      else bool(getattr(settings, "annotate", True))),
            database_path=opts.database_path,
            save_to_database=opts.save_design_to_database,
            cancel=self._job_cancel,
        )
        self._attach_process_monitor(
            worker,
            title=title,
            enabled=bool(opts.show_process_window),
            tool_key=PRIMER_TOOL_KEY,
            mirror_progress=False,
            close_when_finished=bool(opts.close_process_window_when_finished),
        )
        self._start_background_job(
            worker,
            job_title=title,
            total_steps=PRIMER_JOB_STEPS,
            source_files=files,
            on_finished=self._on_primer_job_finished,
            on_failed=self._on_primer_job_failed,
        )

    @Slot(object)
    def _on_primer_job_finished(self, result) -> None:
        report = Path(result["report"])
        created = [report] if report.is_file() else []
        if self._current_folder:
            self._refresh_subfolders_under(self._current_folder)
            self._populate_file_list(
                self._current_folder,
                new_outputs=created,
                source_files=getattr(self, "_last_job_source_files", []),
                open_preview=False,
            )
        if created:
            self._auto_open_outputs(created)
        if result.get("kind") == PRIMER_JOB_PAINTING:
            msg = (f"Chromosome painting finished: {result.get('selected', 0):,} probes selected "
                   f"from {result.get('chorus_input', 0):,} ({report.name})")
        elif result.get("kind") == PRIMER_JOB_MAP:
            msg = (f"Map Primers finished: {result.get('sites', 0):,} binding sites, "
                   f"{result.get('products', 0):,} products ({report.name})")
        else:
            n = int(result.get("pairs", 0))
            msg = f"Primer Design finished: {n} result{'s' if n != 1 else ''} ({report.name})"
            if result.get("saved_to_database"):
                msg += f"; {result['saved_to_database']} primer(s) added to the Primer Database"
        self._set_status_message(msg, 12000, override_file_link=True)
        if result.get("annotated"):
            self._reload_annotated_previews(getattr(self, "_last_job_source_files", []))
        if result.get("ask_pairs") and result.get("pair_list"):
            self._offer_designed_pairs(result["pair_list"], result.get("inputs") or [])

    def _offer_designed_pairs(self, pairs: list, inputs: list) -> None:
        from repeatviewer.views.primer_edit_dialog import DesignedPairsDialog

        dialog = DesignedPairsDialog(pairs, [Path(p) for p in inputs], parent=self)
        dialog.setWindowFlag(Qt.WindowType.Tool, True)

        def _done(code: int) -> None:
            if code:
                try:
                    changed = dialog.add_ticked()
                except Exception as exc:  # noqa: BLE001
                    QMessageBox.warning(self, "Primer Design", f"Could not add the primers:\n{exc}")
                    changed = []
                if changed:
                    self._reload_annotated_previews(changed, include_current=True)
                    self._set_status_message(
                        f"Added the ticked primers to {', '.join(p.name for p in changed)}", 8000)
            dialog.deleteLater()

        dialog.finished.connect(_done)
        dialog.show()
        dialog.raise_()

    def _reload_annotated_previews(self, fastas: list[Path], *, include_current: bool = False) -> None:
        """Open previews of the annotated inputs show the new primer arrows.

        Pages with unsaved edits are left alone (``reload_from_disk`` skips them).
        """
        tabs = getattr(self, "_preview_tabs", None)
        if tabs is None or not fastas:
            return
        from repeatviewer.widgets.preview_tabs import FilePreviewPage

        keys = set()
        for p in fastas:
            try:
                keys.add(str(Path(p).expanduser().resolve()))
            except OSError:
                continue
        current = tabs.currentWidget()
        for index in range(tabs.count()):
            page = tabs.widget(index)
            # The active tab now shows the report; only background tabs that
            # still show an annotated input need the new arrows.
            if (page is current and not include_current) or not isinstance(page, FilePreviewPage):
                continue
            if str(getattr(page, "path", "")) in keys:
                try:
                    page.reload_from_disk()
                except RuntimeError:
                    continue

    @Slot(str)
    def _on_primer_job_failed(self, error: str) -> None:
        if error.strip() == CANCELLED_MESSAGE:
            return
        QMessageBox.warning(self, "Primers", error.strip() or "Unknown error.")

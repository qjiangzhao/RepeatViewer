"""Take the screenshots used in the RepeatViewer user manual.

Run from the repository root, in the environment where RepeatViewer runs:

    python docs/manual/tools/take_screenshots.py

It builds a small demo folder (synthetic data), opens RepeatViewer on it with
default settings, opens each window the manual shows, and saves a PNG of it in
docs/manual/img/. Your own settings and folders are not touched: the run uses
a separate settings store.

Options:
    --only NAME[,NAME...]   take only these shots (see SHOTS below)
    --list                  list the shot names
    --offscreen             do not show windows on screen (Linux / CI)
    --keep-demo             keep the demo folder (printed at the end)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
IMG = ROOT / "docs" / "manual" / "img"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

WIDTH, HEIGHT = 1280, 800


def _parse_args():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", default="")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--offscreen", action="store_true")
    ap.add_argument("--keep-demo", action="store_true")
    ap.add_argument("--demo", default="", help="reuse this demo folder (made by an earlier --keep-demo run)")
    return ap.parse_args()


ARGS = _parse_args()
if ARGS.offscreen:
    # A large virtual screen, so long menus and big windows are not squeezed.
    _cfg = Path(tempfile.mkdtemp(prefix="rv_manual_screen_")) / "screen.json"
    _cfg.write_text('{"screens": [{"name": "manual", "x": 0, "y": 0, '
                    '"width": 2560, "height": 1600, "logicalDpi": 72}]}')
    os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={_cfg}"
if sys.platform != "darwin":
    # Mac-like sizes (72 dpi points) and sharp 2x images, like a Retina screen.
    os.environ.setdefault("QT_FONT_DPI", "72")
    os.environ.setdefault("QT_SCALE_FACTOR", "2")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QWidget  # noqa: E402

# A separate settings store, so the run starts from defaults and leaves the
# user's own RepeatViewer settings alone.
_SETTINGS_DIR = Path(tempfile.mkdtemp(prefix="rv_manual_settings_"))
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(_SETTINGS_DIR))

APP = QApplication.instance() or QApplication(sys.argv)
APP.setApplicationName("RepeatViewer")
APP.setOrganizationName("RepeatViewerManual")

if sys.platform != "darwin" and "Inter" in QFontDatabase.families():
    f = QFont("Inter")
    f.setPixelSize(13)
    APP.setFont(f)


def pump(seconds: float = 0.3) -> None:
    end = time.time() + seconds
    while time.time() < end:
        APP.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.01)


def save(widget: QWidget, name: str, crop: tuple[int, int] | None = None) -> Path:
    """Save a picture of ``widget`` (``crop``: keep only this width and height)."""
    pump(0.4)
    pix = widget.grab()
    if crop:
        from PySide6.QtCore import QRect
        dpr = pix.devicePixelRatio()
        w, h = min(crop[0], widget.width()), min(crop[1], widget.height())
        pix = pix.copy(QRect(0, 0, round(w * dpr), round(h * dpr)))
    IMG.mkdir(parents=True, exist_ok=True)
    out = IMG / f"{name}.png"
    pix.save(str(out), "PNG")
    _compress(out)
    print(f"  saved {out.relative_to(ROOT)}  ({pix.width()} x {pix.height()})")
    return out


def _compress(path: Path) -> None:
    """Screenshots have few colours: a 256-colour PNG is a third of the size."""
    try:
        from PIL import Image
    except ImportError:
        return
    with Image.open(path) as im:
        q = im.convert("RGB").quantize(256, method=Image.Quantize.MEDIANCUT,
                                       dither=Image.Dither.NONE)
    q.save(path, optimize=True)


def top_levels() -> set[int]:
    return {id(w) for w in APP.topLevelWidgets() if w.isVisible()}


def new_window(before: set[int], main: QWidget) -> QWidget | None:
    """The newest visible top-level window that was not there before."""
    for w in reversed(APP.topLevelWidgets()):
        if w.isVisible() and id(w) not in before and w is not main and w.width() > 120:
            return w
    modal = APP.activeModalWidget()
    if modal is not None and modal is not main:
        return modal
    return None


def capture_dialog(main, trigger, name: str, *, prepare=None, size=None,
                   close: bool = True) -> QWidget | None:
    """Run ``trigger`` (it may open a modal dialog) and save the window it opens."""
    before = top_levels()
    result: dict = {}

    def grab_it():
        w = new_window(before, main)
        if w is None:
            print(f"  {name}: no window opened")
            return
        if size:
            w.resize(*size)
        if prepare:
            try:
                prepare(w)
            except Exception:
                traceback.print_exc()
        try:
            save(w, name)
        except RuntimeError:  # the window closed itself (for example after Run)
            return
        result["w"] = w
        if close:
            try:
                if isinstance(w, QDialog):
                    w.reject()
                else:
                    w.close()
            except RuntimeError:  # already closed and deleted
                pass

    QTimer.singleShot(700, grab_it)
    trigger()
    pump(1.5)
    return result.get("w")


def menu_action(main, *path: str):
    """Find a menu action by its visible text path (ampersands ignored)."""
    def clean(t: str) -> str:
        return t.replace("&", "").replace("…", "").replace("...", "").strip()

    actions = main.menuBar().actions()
    found = None
    for step in path:
        found = next((a for a in actions if clean(a.text()) == clean(step)), None)
        if found is None:
            raise KeyError(" > ".join(path))
        if found.menu() is not None:
            actions = found.menu().actions()
    return found


def trigger_menu(main, *path: str):
    return lambda: menu_action(main, *path).trigger()


def select_files(main, paths: list[Path], *, preview: bool = True) -> None:
    from PySide6.QtCore import QItemSelectionModel
    table = main._file_list
    index = table._path_row_index()
    table.clearSelection()
    first = None
    for p in paths:
        row = index.get(str(Path(p).resolve()))
        if row is None:
            print(f"  not in Files panel: {p}")
            continue
        item = table.item(row)
        if first is None:
            first = item
            table.setCurrentItem(item)
        table.selectionModel().select(
            table.model().index(row, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    if first is not None and preview:
        main._on_file_item_clicked(first)
    pump(1.0)


def show_file(main, path: Path) -> None:
    """Go to the file's folder, select it and open it in Preview."""
    path = Path(path).resolve()
    if main._current_folder is None or Path(main._current_folder).resolve() != path.parent:
        main._navigate_to_folder(path.parent, open_preview=False)
        pump(0.8)
    select_files(main, [path])
    pump(1.5)


def click_tab(root: QWidget, text: str) -> bool:
    """Switch any tab bar under ``root`` to the tab called ``text``."""
    from PySide6.QtWidgets import QTabBar
    for bar in root.findChildren(QTabBar):
        if not bar.isVisible():
            continue
        for i in range(bar.count()):
            if bar.tabText(i).replace("&", "").strip() == text:
                bar.setCurrentIndex(i)
                pump(0.8)
                return True
    from PySide6.QtWidgets import QAbstractButton
    for b in root.findChildren(QAbstractButton):
        if b.isVisible() and b.isCheckable() and b.text().replace("&", "").strip() == text:
            b.click()
            pump(0.8)
            return True
    print(f"  no tab '{text}'")
    return False


def click_button(root: QWidget, text: str) -> bool:
    from PySide6.QtWidgets import QAbstractButton
    for b in root.findChildren(QAbstractButton):
        if b.isVisible() and b.text().replace("&", "").strip() == text:
            b.click()
            pump(0.8)
            return True
    print(f"  no button '{text}'")
    return False


def rail(main):
    from repeatviewer.widgets.sequence_annotation_rail import SequenceAnnotationRail
    for r in main.findChildren(SequenceAnnotationRail):
        if r.isVisible():
            return r
    return None


def preview(main) -> QWidget:
    """The Preview panel (with its title bar and sub-tabs)."""
    from PySide6.QtWidgets import QDockWidget
    w = main._preview_tabs
    while w is not None and not isinstance(w, QDockWidget) and w.parentWidget() is not main:
        w = w.parentWidget()
    return w or main._preview_tabs


def reload_primers(main) -> None:
    for w in main.findChildren(QWidget):
        if type(w).__name__ == "PrimersPanel" and hasattr(w, "reload"):
            w.reload()
    pump(0.5)


def open_folder(main, folder: Path) -> None:
    main._add_root_folder(folder)
    pump(0.5)
    main._navigate_to_folder(folder, open_preview=False)
    pump(1.0)


# ----------------------------------------------------------------------------
# Shots. Each takes (main, demo) and saves one or more images.

SHOTS: dict = {}


def shot(name):
    def deco(fn):
        SHOTS[name] = fn
        return fn
    return deco


@shot("main_window")
def _main_window(main, d):
    open_folder(main, d["folder"])
    select_files(main, [d["ltr"]])
    pump(1.5)
    save(main, "main_window")



def menu_popup(main, title: str, name: str):
    """Save an open menu from the menu bar."""
    act = menu_action(main, title)
    menu = act.menu()
    menu.popup(main.mapToGlobal(main.rect().topLeft()))
    pump(0.5)
    save(menu, name)
    menu.hide()


def dialog_shot(name, path, files=None, size=None, prepare=None):
    def fn(main, d):
        if files:
            select_files(main, [d[k] if isinstance(k, str) else k for k in files])
        capture_dialog(main, trigger_menu(main, *path), name, size=size,
                       prepare=prepare)
    SHOTS[name] = fn


@shot("files_highlight")
def _files_highlight(main, d):
    folder = d["folder"]
    main._populate_file_list(folder, new_outputs=[d["tree"]], source_files=[d["monomers"]],
                             open_preview=False)
    pump(0.5)
    table = main._file_list
    height = table.horizontalHeader().height() + table.rowCount() * table.rowHeight(0) + 8
    width = table.horizontalHeader().length() + 4
    save(table, "files_highlight", crop=(width, height))


@shot("menu_edit")
def _menu_edit(main, d):
    show_file(main, d["ltr"])
    main._file_list.setFocus()
    pump(0.3)
    menu_popup(main, "Edit", "menu_edit")


@shot("menu_tools")
def _menu_tools(main, d):
    menu_popup(main, "Tools", "menu_tools")



@shot("preview_text")
def _preview_text(main, d):
    show_file(main, d["ltr"])
    click_tab(preview(main), "Text")
    save(preview(main), "preview_text")
    click_tab(preview(main), "Overview")


@shot("annotation_view")
def _annotation_view(main, d):
    show_file(main, d["ltr"])
    click_tab(preview(main), "Overview")
    r = rail(main)
    r.set_current_tab(0)
    pump(0.8)
    save(preview(main), "rail_display")
    r.set_current_tab(1)
    pump(0.5)
    save(preview(main), "annotation_view")


@shot("dotplot_self")
def _dotplot_self(main, d):
    show_file(main, d["ltr"])
    click_tab(preview(main), "Dotplot (Self)")
    pump(2.5)
    save(preview(main), "dotplot_self")
    click_tab(preview(main), "Overview")


@shot("multi_fasta")
def _multi_fasta(main, d):
    show_file(main, d["monomers"])
    save(preview(main), "multi_fasta")


@shot("tree_options")
def _tree_options(main, d):
    show_file(main, d["tree"])
    pump(1.5)
    for title in ("Layout", "Tip names", "Colour tips"):
        expand_section(preview(main), title, True)
    save(preview(main), "tree_options")
    for title in ("Layout", "Tip names", "Colour tips"):
        expand_section(preview(main), title, False)


@shot("tree_report")
def _tree_report(main, d):
    show_file(main, d["tree_report"])
    pump(3.0)
    save(preview(main), "tree_report")


@shot("mapping_view")
def _mapping_view(main, d):
    show_file(main, d["paf"])
    pump(2.5)
    save(preview(main), "mapping_view")


@shot("mapping_browser")
def _mapping_browser(main, d):
    if d.get("sam"):
        show_file(main, d["sam"])
        pump(2.5)
        save(preview(main), "mapping_browser")


@shot("find_hits")
def _find_hits(main, d):
    from PySide6.QtWidgets import QLineEdit
    show_file(main, d["ltr"])

    def fill(w):
        edits = [e for e in w.findChildren(QLineEdit) if e.isVisible()]
        edits[0].setText("TGTTG")
        click_button(w, "Find All")
        pump(1.0)

    capture_dialog(main, trigger_menu(main, "Edit", "Find in this document"), "find_hits",
                   prepare=fill)
    pump(0.5)


@shot("batch_rename")
def _batch_rename(main, d):
    from PySide6.QtWidgets import QLineEdit
    sub = d["folder"] / "candidates"
    main._navigate_to_folder(sub, open_preview=False)
    pump(0.8)
    select_files(main, sorted(sub.glob("*.fa")), preview=False)
    main._file_list.setFocus()
    pump(0.3)

    def fill(w):
        edits = [e for e in w.findChildren(QLineEdit) if e.isVisible()]
        if len(edits) >= 2:
            edits[0].setText("_0")
            edits[1].setText("_v")
        pump(0.5)

    files = sorted(sub.glob("*.fa"))
    capture_dialog(main, lambda: main._batch_rename_files(files), "batch_rename",
                   prepare=fill)
    main._navigate_to_folder(d["folder"], open_preview=False)
    pump(0.5)


@shot("mapping_report")
def _mapping_report(main, d):
    show_file(main, d["map_report"])
    pump(3.0)
    save(preview(main), "mapping_report")


@shot("pcr_products")
def _pcr_products(main, d):
    show_file(main, d["pcr"])
    save(preview(main), "pcr_products")


def expand_section(root: QWidget, title: str, expanded: bool = True) -> bool:
    """Open (or close) a collapsible section of a side panel."""
    from PySide6.QtWidgets import QAbstractButton, QLabel
    for sec in root.findChildren(QWidget):
        if not hasattr(sec, "set_expanded") or not sec.isVisible():
            continue
        title_label = getattr(sec, "_title", None)
        if isinstance(title_label, QLabel) and title_label.text().strip() == title:
            sec.set_expanded(expanded)
            pump(0.6)
            return True
    for b in root.findChildren(QAbstractButton):
        if b.isVisible() and b.text().replace("&", "").strip() == title:
            if b.isCheckable() and not b.isChecked():
                b.click()
            elif not b.isCheckable():
                b.click()
            pump(0.6)
            return True
    print(f"  no section '{title}'")
    return False


def rail_section_shots(main, tab: int, sections: dict[str, str], *, width=380):
    r = rail(main)
    r.set_current_tab(tab)
    pump(0.6)
    for title, name in sections.items():
        expand_section(r, title, True)
        save(r, name, crop=(r.width(), 340))
        expand_section(r, title, False)


@shot("rail_sections")
def _rail_sections(main, d):
    show_file(main, d["ltr"])
    rail_section_shots(main, 1, {
        "Feature detection": "rail_feature_detection",
        "Similarity annotation": "rail_similarity",
        "Manually add feature": "rail_manual_feature",
        "Transfer annotation": "rail_transfer",
    })


@shot("msa_sections")
def _msa_sections(main, d):
    show_file(main, d["aln"])
    expand_section(preview(main), "Boundary prediction")
    save(preview(main), "msa_boundary")



def capture_popup(trigger, name: str) -> None:
    """Run ``trigger`` (it opens a menu with exec) and save the menu."""
    from PySide6.QtWidgets import QMenu

    def open_menus():
        return [w for w in APP.topLevelWidgets() if isinstance(w, QMenu) and w.isVisible()]

    def grab_it():
        menus = open_menus()
        menu = APP.activePopupWidget() or (menus[-1] if menus else None)
        if menu is None:
            print(f"  {name}: no menu opened")
            return
        save(menu, name)
        menu.close()

    def watchdog():
        for m in open_menus():
            m.close()
        modal = APP.activeModalWidget()
        if modal is not None:
            modal.close()

    QTimer.singleShot(700, grab_it)
    QTimer.singleShot(3000, watchdog)
    trigger()
    pump(0.8)


@shot("files_context_menu")
def _files_context_menu(main, d):
    from PySide6.QtCore import QPoint
    show_file(main, d["ltr"])
    table = main._file_list
    row = table._path_row_index()[str(Path(d["ltr"]).resolve())]
    rect = table.visualRect(table.model().index(row, 1))
    capture_popup(lambda: table._show_context_menu(rect.center()), "files_context_menu")


@shot("export_dialog")
def _export_menu(main, d):
    show_file(main, d["ltr"])
    r = rail(main)
    r.set_current_tab(1)
    pump(0.5)
    from PySide6.QtWidgets import QAbstractButton
    btn = next((b for b in r.findChildren(QAbstractButton)
                if b.isVisible() and b.text() == "Export"), None)
    if btn is not None:
        capture_dialog(main, btn.click, "export_dialog")



def set_genome(main, genome: Path) -> None:
    """Make the demo genome the reference genome (only in this run's settings)."""
    before = main._project.genome_file
    main._project.genome_file = Path(genome)
    main._on_genome_changed(before, Path(genome))
    pump(0.5)


def plot_shots(main, opener, dialog_name: str, result_name: str, size=None, height=None):
    """Save a plot window, then run it and save the plot it opens in Preview."""
    capture_dialog(main, opener, dialog_name, size=size)

    def run(w):
        click_button(w, "Run")

    from PySide6.QtWidgets import QMessageBox

    def close_messages():
        for box in APP.topLevelWidgets():
            if isinstance(box, QMessageBox) and box.isVisible():
                print("  message:", box.text().replace("\n", " ")[:200])
                box.done(0)

    watch = QTimer()
    watch.timeout.connect(close_messages)
    watch.start(1500)

    capture_dialog(main, opener, "_ignore", prepare=run, close=False)
    for _ in range(60):
        pump(0.5)
        try:
            if main._te_viz_input_dialog is None or not main._te_viz_input_dialog.isVisible():
                break
        except RuntimeError:  # the window was closed and deleted
            break
    pump(8.0)
    watch.stop()
    pv = preview(main)
    save(pv, result_name, crop=(pv.width(), height) if height else None)
    (IMG / "_ignore.png").unlink(missing_ok=True)


def _plots_ready(main, d) -> bool:
    if not d.get("hits"):
        print("  no hit table in the demo folder")
        return False
    set_genome(main, d["genome"])
    main._navigate_to_folder(d["folder"], open_preview=False)
    pump(0.8)
    return True


@shot("density_plot")
def _density_plot(main, d):
    if _plots_ready(main, d):
        plot_shots(main, lambda: main._open_te_density_plot_dialog(input_file=d["hits"]),
                   "density_plot", "density_plot_result", size=(760, 720), height=340)


@shot("divergence_plot")
def _divergence_plot(main, d):
    if _plots_ready(main, d):
        plot_shots(main, lambda: main._open_te_divergence_plot_dialog(input_file=d["hits"]),
                   "divergence_plot", "divergence_plot_result", height=440)


@shot("abundance_plot")
def _abundance_plot(main, d):
    if _plots_ready(main, d):
        plot_shots(main, lambda: main._open_te_abundance_plot_dialog(input_file=d["rm_out"]),
                   "abundance_plot", "abundance_plot_result", height=480)


dialog_shot("settings", ("File", "Setting"), size=(900, 680))
dialog_shot("settings_toolbar", ("File", "Setting"), size=(900, 680),
            prepare=lambda w: click_tab(w, "Toolbar"))
dialog_shot("manage_database", ("File", "Manage Database"))
dialog_shot("new_sequence", ("Sequence", "New Sequence"))
dialog_shot("extract_sequences", ("Sequence", "Extract Sequences from File"), files=["monomers"])
dialog_shot("orf_prediction", ("Sequence", "ORF Prediction"), files=["ltr"])
dialog_shot("ncbi_download", ("Tools", "Download from NCBI"), size=(980, 640))
dialog_shot("blast", ("Tools", "Search", "BLAST"), files=["ltr"])
dialog_shot("hmmer", ("Tools", "Search", "HMMER"), files=["ltr"])
dialog_shot("align", ("Tools", "Align"), files=["monomers"])
dialog_shot("msa_extend", ("Tools", "Curate", "MSA Extend"), files=["monomers"])
dialog_shot("msa_clean", ("Tools", "Curate", "MSA Clean"), files=["monomers"])
dialog_shot("consensus", ("Tools", "Curate", "Consensus"), files=["monomers"])
dialog_shot("teaid", ("Tools", "Curate", "TE-Aid"), files=["ltr"])
dialog_shot("seq_annotation", ("Tools", "Annotate"), files=["ltr"])
dialog_shot("dotplot", ("Tools", "Visualize", "Dotplot"), files=["ltr"])
dialog_shot("msa_plot", ("Tools", "Visualize", "MSA plot"), files=["monomers"])
dialog_shot("mapping", ("Tools", "Mapping"), files=["reads"])
dialog_shot("tree", ("Tools", "Tree"), files=["monomers"])
dialog_shot("samtools", ("Tools", "Samtools"), files=["sam"])
dialog_shot("repeat_quantify", ("Tools", "Quantify", "Repeat Quantify"), files=["monomers"])
dialog_shot("workflows", ("Workflows", "Design and manage your workflows"))
dialog_shot("wrappers", ("Tools", "Command wrapper", "Manage wrapper"))


# ----------------------------------------------------------------------------
# Primers and Probes workspace. Every section is a page of one tab, so these
# shots go through the app's own menu and save the Preview panel. They are
# registered last and close the workspace when done: while it is in front, a
# click in the Files panel goes to it and not to Preview.

PP = ("Tools", "Primers and Probes")


def workspace(main):
    return main._primers_workspace()


def _dismiss_modal(name: str) -> None:
    w = APP.activeModalWidget()
    if w is None:
        return
    print(f"  {name}: closed a message box ({w.windowTitle()})")
    if isinstance(w, QDialog):
        w.reject()
    else:
        w.close()


def open_section(main, key: str, *path: str, file: Path | None = None):
    """Open a workspace section from Tools > Primers and Probes. None when it did not open."""
    if file is not None:
        show_file(main, file)
    QTimer.singleShot(1200, lambda: _dismiss_modal(key))
    menu_action(main, *PP, *path).trigger()
    pump(2.0)
    ws = workspace(main)
    if ws is None or ws.section() != key:
        print(f"  {key}: the section did not open")
        return None
    main._preview_tabs.setCurrentWidget(ws)
    pump(0.5)
    return ws


def close_workspace(main) -> None:
    ws = workspace(main)
    tabs = main._preview_tabs
    if ws is None:
        return
    index = tabs.indexOf(ws)
    if index >= 0:
        tabs._close_tab(index, ask=False)
    pump(0.5)


def pp_shot(name):
    def deco(fn):
        def run(main, d):
            try:
                fn(main, d)
            finally:
                close_workspace(main)
        SHOTS[name] = run
        return fn
    return deco


def tick_primers(ws) -> None:
    """Tick every primer on the sequence, so PCR uses them."""
    from PySide6.QtCore import Qt as _Qt
    panel = ws.primers_panel()
    panel.reload()
    pump(0.5)
    for row in range(panel.table.rowCount()):
        item = panel.table.item(row, panel.COL_TICK)
        if item is not None:
            item.setCheckState(_Qt.CheckState.Checked)
    pump(0.5)


@pp_shot("pp_design")
def _pp_design(main, d):
    ws = open_section(main, "design", "Design", "Primers", file=d["ltr"])
    if ws is None:
        return
    ws.primers_panel().design_pane.design_button.click()
    pump(6.0)
    save(preview(main), "pp_design")


@pp_shot("pp_primer")
def _pp_primer(main, d):
    from repeatviewer.views.primers_workspace import PANEL_PRIMER
    ws = open_section(main, "design", "Design", "Primers", file=d["array"])
    if ws is None:
        return
    tick_primers(ws)
    ws.set_section("design", page=PANEL_PRIMER)
    panel = ws.primers_panel()
    if panel.table.rowCount():
        panel.table.setCurrentCell(0, panel.COL_NAME)
        panel.table.cellClicked.emit(0, panel.COL_NAME)
    pump(1.0)
    save(preview(main), "pp_primer")


@pp_shot("pcr")
def _pcr(main, d):
    """The PCR section after a satellite ladder PCR with the demo primers."""
    ws = open_section(main, "design", "Design", "Primers", file=d["array"])
    if ws is None:
        return
    tick_primers(ws)
    ws = open_section(main, "pcr", "In-silico PCR")
    if ws is None:
        return
    kind = ws.primers_panel().pcr_pane.kind
    for i in range(kind.count()):
        if "ladder" in kind.itemText(i).lower():
            kind.setCurrentIndex(i)
    pump(3.0)
    save(preview(main), "pcr")


@pp_shot("digest")
def _digest(main, d):
    ws = open_section(main, "digest", "Restriction Digest", file=d["array"])
    if ws is None:
        return
    pump(1.5)
    save(preview(main), "digest_enzymes")
    enzymes = ws.primers_panel().enzyme_pane
    if not enzymes.ticked_rows():
        enzymes.select_all_button.click()
    enzymes.digest_button.click()
    pump(3.0)
    save(preview(main), "digest")


@pp_shot("gel")
def _gel(main, d):
    ws = main._ensure_primers_workspace()
    if ws is None or not d.get("gel"):
        print("  gel: no workspace or no demo gel")
        return
    ws.show_gel(d["gel"])
    main._preview_tabs.setCurrentWidget(ws)
    pump(1.5)
    save(preview(main), "gel")


@pp_shot("primer_map")
def _primer_map(main, d):
    if open_section(main, "map", "Map", "Primers", file=d["ltr"]) is not None:
        save(preview(main), "primer_map")


@pp_shot("primer_database")
def _primer_database(main, d):
    if open_section(main, "database", "Database") is not None:
        save(preview(main), "primer_database")


@pp_shot("sanger_check")
def _sanger_check(main, d):
    """With .ab1 files in the demo folder (--demo DIR) the page shows a real check."""
    ws = open_section(main, "sanger", "Sanger Check", file=d["ltr"])
    if ws is None:
        return
    reads = sorted(Path(d["folder"]).glob("*.ab1"))
    page = ws.hosted_page("sanger")
    if reads and page is not None:
        page.add_reads(reads)
        pump(2.0)
    save(preview(main), "sanger_check")


@pp_shot("cloning")
def _cloning(main, d):
    if open_section(main, "cloning", "Cloning", file=d.get("pcr") or d["ltr"]) is not None:
        save(preview(main), "cloning")


def main() -> int:
    if ARGS.list:
        print("\n".join(SHOTS))
        return 0
    import demo_data

    if ARGS.demo:
        demo_dir = Path(ARGS.demo).resolve()
        d = demo_data.paths(demo_dir)
        ARGS.keep_demo = True
    else:
        demo_dir = Path(tempfile.mkdtemp(prefix="rv_manual_demo_")) / "RepeatViewer demo"
        d = demo_data.build(demo_dir)
    print(f"Demo folder: {demo_dir}")
    d["folder"] = demo_dir

    from repeatviewer.ui.theme_mode import apply_theme
    apply_theme("light")
    from repeatviewer.main_window import MainWindow
    win = MainWindow()
    win.resize(WIDTH, HEIGHT)
    win.show()
    pump(1.5)
    open_folder(win, demo_dir)
    win.resize(WIDTH, HEIGHT)
    pump(0.5)

    wanted = [s for s in ARGS.only.split(",") if s] or list(SHOTS)
    failed = []
    for name in wanted:
        print(f"[{name}]")
        try:
            SHOTS[name](win, d)
        except Exception:
            traceback.print_exc()
            failed.append(name)
    win.close()
    pump(0.5)
    if not ARGS.keep_demo:
        shutil.rmtree(demo_dir.parent, ignore_errors=True)
    shutil.rmtree(_SETTINGS_DIR, ignore_errors=True)
    if failed:
        print("Failed:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

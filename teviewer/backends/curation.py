"""TE curation tools (ported from TEtrimmerGUI, standalone in TEviewer)."""

from __future__ import annotations

import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable

import plotly.io as pio
from Bio import SeqIO

from teviewer.backends.blast_gff import write_blast_gff
from teviewer.backends.crop_end_divergence import crop_end_div
from teviewer.backends.crop_end_gap import crop_end_gap
from teviewer.backends.gui_functions import (
    sanitize_name,
    blast as run_blast,
    check_database,
    extend_bed_regions,
    extract_fasta_from_bed,
    fasta_header_to_bed,
    process_bed_lines,
    run_flexidot,
)
from teviewer.backends.remove_gap import remove_gaps_with_similarity_check
from teviewer.backends.teaid_plotter import (
    TeaidInputError,
    con_generater,
    teaid_pan_genome_plotter,
    teaid_plotter,
)
from teviewer.backends.job_cancel import JobCancelledError, JobCancellation, check_cancelled
from teviewer.backends.thread_budget import analysis_threads_per_job
from teviewer.backends.tsd_search import TSD_identifier
from teviewer.job_options import (
    BlastOptions,
    ConsensusOptions,
    ExtendOptions,
    FlexidotOptions,
    MsaCleanOptions,
    TeaAidOptions,
    TsdSearchOptions,
)
from teviewer.pan_genome import genome_output_suffix
from teviewer.backends.te_annotation_batch import TeAnnotationOptions, run_te_annotation_on_fasta
from teviewer.project import TEviewerProject

ProgressCallback = Callable[[int, str], None]

_DISPLAY_NAMES = {
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
}


def _snapshot_paths(root: Path) -> set[Path]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        return set()
    return {p.resolve() for p in root.rglob("*")} | {root}


_flexidot_dir_locks: dict[Path, threading.Lock] = {}
_flexidot_locks_guard = threading.Lock()


def _flexidot_dir_lock(folder: Path) -> threading.Lock:
    key = folder.expanduser().resolve()
    with _flexidot_locks_guard:
        if key not in _flexidot_dir_locks:
            _flexidot_dir_locks[key] = threading.Lock()
        return _flexidot_dir_locks[key]


def cleanup_teaid_side_files(
    output_dir: Path,
    input_file: Path,
    keep_html: Path,
) -> None:
    """
    Remove intermediate TEAid files for one input only.

    Keeps the input FASTA and this run's HTML report. Safe when several TEAid
    jobs run in parallel in the same folder (does not delete other sequences'
    HTML reports or their source files).
    """
    output_dir = output_dir.expanduser().resolve()
    input_file = input_file.expanduser().resolve()
    keep_html = keep_html.expanduser().resolve()
    input_name = input_file.name
    consensus_prefix = f"{input_name}_0.3_co.fa"

    to_remove: list[Path] = []
    if not output_dir.is_dir():
        return

    for entry in output_dir.iterdir():
        resolved = entry.resolve()
        if resolved in {keep_html, input_file}:
            continue
        name = entry.name
        if name.endswith("_TEAid.html"):
            continue
        if entry.is_dir() and name.endswith("_self_blast"):
            prefix = name[: -len("_self_blast")]
            if prefix == input_name or prefix.startswith(f"{input_name}_"):
                to_remove.append(resolved)
            continue
        if not (entry.is_file() or entry.is_symlink()):
            continue
        if name.startswith(consensus_prefix):
            to_remove.append(resolved)
            continue
        if name.startswith(input_name) and name != input_name:
            to_remove.append(resolved)

    for path in sorted(to_remove, key=lambda p: len(p.parts), reverse=True):
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def _png_paths_in_dir(folder: Path) -> set[Path]:
    folder = folder.expanduser().resolve()
    return {p.resolve() for p in folder.glob("*.png") if p.is_file()}


def flexidot_output_stem(seq_files: list[Path], genome_label: str = "") -> str:
    """Output basename: ``{first_stem}_flexidot`` or ``{first_stem}_flexidot_multi``."""
    stem = seq_files[0].expanduser().resolve().stem
    suffix = genome_output_suffix(genome_label)
    if len(seq_files) >= 2:
        return f"{stem}_flexidot_multi{suffix}"
    return f"{stem}_flexidot{suffix}"


_FLEXIDOT_EXTRA_PNG_RE = re.compile(
    r".+_flexidot(?:_multi)?.*_(\d+)\.png$",
    re.IGNORECASE,
)


def is_flexidot_extra_plot_file(path: Path) -> bool:
    """True for secondary Flexidot PNGs (``*_flexidot_2.png``, etc.)."""
    match = _FLEXIDOT_EXTRA_PNG_RE.match(path.name)
    return match is not None and int(match.group(1)) >= 2


def _remove_flexidot_extra_pngs(output_dir: Path, base: str) -> None:
    """Delete numbered Flexidot extras left from older runs."""
    output_dir = output_dir.expanduser().resolve()
    for index in range(2, 20):
        extra = output_dir / f"{base}_{index}.png"
        try:
            extra.unlink(missing_ok=True)
        except OSError:
            pass


def _genome_work_items(
    project: TEviewerProject,
    func_name: str,
    extend: ExtendOptions | None = None,
) -> list[tuple[str, Path]]:
    """Return ``(label, fasta_path)`` pairs for one batch job."""
    if not project.is_pan_genome_mode:
        return [
            (label, path)
            for label, path in project.genome_targets()
        ]

    if func_name == "extend":
        extend_opts = extend or ExtendOptions()
        name = extend_opts.pan_genome_name
        if not name and project.pan_genomes:
            name = project.pan_genomes[0].name
        if not name:
            raise RuntimeError("Pan-genome mode: select a genome name for Extend.")
        entry = project.pan_genome_by_name(name)
        if entry is None:
            raise RuntimeError(f"Unknown pan-genome name: {name}")
        return [(entry.name, entry.path.expanduser().resolve())]

    return [
        (entry.name, entry.path.expanduser().resolve())
        for entry in project.pan_genomes
    ]


def _prepare_genome_resources(
    func_name: str,
    genome_items: list[tuple[str, Path]],
    project: TEviewerProject,
    os_type: str,
) -> tuple[dict[Path, str], dict[Path, dict[str, int]]]:
    db_cache: dict[Path, str] = {}
    chrom_cache: dict[Path, dict[str, int]] = {}
    for _label, genome_path in genome_items:
        if func_name == "blast":
            genome_db = check_database(
                str(genome_path),
                os_type=os_type,
                use_system_blast=project.use_system_blast,
            )
            if genome_db in {"makeblastdb_not_found", "makeblastdb_got_error", None, False}:
                raise RuntimeError(
                    f"Cannot prepare genome BLAST database for {genome_path.name}: {genome_db}"
                )
            db_cache[genome_path] = genome_db
        if func_name == "extend":
            chrom_cache[genome_path] = genome_chrom_sizes(genome_path)
    return db_cache, chrom_cache


def _flexidot_pngs_for_run(
    output_dir: Path,
    before: set[Path],
    seq_files: list[Path],
) -> list[Path]:
    """New PNGs from one Flexidot run (optionally filtered to one input stem)."""
    after = _png_paths_in_dir(output_dir)
    new_files = sorted(
        after - before,
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    if len(seq_files) == 1:
        stem = seq_files[0].stem
        owned = [p for p in new_files if stem in p.name]
        if owned:
            return owned
    return new_files


def cleanup_flexidot_intermediates(output_dir: Path, keep_paths: Iterable[Path]) -> None:
    """Remove Flexidot scratch files (``flexidot_output-*``) after plots are renamed."""
    output_dir = output_dir.expanduser().resolve()
    keep = {p.expanduser().resolve() for p in keep_paths}
    if not output_dir.is_dir():
        return
    for entry in output_dir.iterdir():
        if not entry.name.startswith("flexidot_output"):
            continue
        resolved = entry.resolve()
        if resolved in keep:
            continue
        try:
            if entry.is_dir():
                shutil.rmtree(resolved, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
        except OSError:
            pass


def finalize_flexidot_outputs(
    output_dir: Path,
    seq_files: list[Path],
    before: set[Path],
) -> list[str]:
    """Keep the primary Flexidot PNG as ``{stem}_flexidot.png``; drop extra panels."""
    output_dir = output_dir.expanduser().resolve()
    new_files = _flexidot_pngs_for_run(output_dir, before, seq_files)
    if not new_files:
        return []

    base = flexidot_output_stem(seq_files)
    _remove_flexidot_extra_pngs(output_dir, base)

    src = new_files[0]
    dest = output_dir / f"{base}.png"
    if dest.exists():
        dest.unlink()
    if not src.is_file():
        cleanup_flexidot_intermediates(output_dir, [])
        return []

    src.rename(dest)
    for extra in new_files[1:]:
        try:
            if extra.is_file():
                extra.unlink(missing_ok=True)
        except OSError:
            pass

    cleanup_flexidot_intermediates(output_dir, [dest])
    return [str(dest.resolve())]


def effective_batch_workers(requested: int, num_sequences: int) -> int:
    """Clamp parallel worker count to sensible limits."""
    if num_sequences <= 1 or requested <= 1:
        return 1
    cpus = os.cpu_count() or 4
    return max(1, min(requested, num_sequences, cpus))


def genome_chrom_sizes(genome_path: Path) -> dict[str, int]:
    chrom_sizes = {}
    for rec in SeqIO.parse(str(genome_path), "fasta"):
        chrom_sizes[rec.id] = len(rec.seq)
    if not chrom_sizes:
        raise RuntimeError("Genome FASTA has no sequences.")
    return chrom_sizes


def run_flexidot_combined(
    seq_files: list[Path],
    *,
    flexidot_options: FlexidotOptions | None = None,
    cancel: JobCancellation | None = None,
    genome_label: str = "",
) -> list[str]:
    """Flexidot for 2+ inputs: mode 1 (paired) or 2 (poly)."""
    if len(seq_files) < 2:
        raise ValueError("Combined Flexidot requires at least two sequences.")
    flex_opts = flexidot_options or FlexidotOptions()
    mode = "1" if len(seq_files) == 2 else "2"
    out_dir = seq_files[0].parent.resolve()
    combined = out_dir / f"_flexidot_{len(seq_files)}seq.fa"
    records = []
    for path in seq_files:
        records.extend(SeqIO.parse(str(path.expanduser().resolve()), "fasta"))
    if not records:
        raise RuntimeError("No sequences found in selected FASTA files.")
    seen: dict[str, int] = {}
    for record in records:
        safe = sanitize_name(record.id)
        count = seen.get(safe, 0)
        seen[safe] = count + 1
        if count:
            safe = f"{safe}_{count + 1}"
        record.id = safe
        record.description = safe
    SeqIO.write(records, str(combined), "fasta")
    with _flexidot_dir_lock(out_dir):
        before = _png_paths_in_dir(out_dir)
        try:
            run_flexidot(
                str(combined),
                str(out_dir),
                wordsize=flex_opts.wordsize,
                mode=mode,
                lcs_shading=flex_opts.lcs_shading,
                use_gff=flex_opts.use_gff,
                gff_source_fastas=[str(path) for path in seq_files],
                gff_output_stem=flexidot_output_stem(seq_files, genome_label),
                cancel=cancel,
            )
        finally:
            if combined.is_file():
                combined.unlink(missing_ok=True)
        return finalize_flexidot_outputs(out_dir, seq_files, before)


def run_on_sequence(
    func_name: str,
    seq_path: Path,
    project: TEviewerProject,
    *,
    genome_path: Path | None = None,
    genome_label: str = "",
    genome_db: str | None = None,
    chrom_sizes: dict[str, int] | None = None,
    flexidot_options: FlexidotOptions | None = None,
    flexidot_mode: str = "0",
    extend: ExtendOptions | None = None,
    blast_options: BlastOptions | None = None,
    teaid_options: TeaAidOptions | None = None,
    msa_clean_options: MsaCleanOptions | None = None,
    consensus_options: ConsensusOptions | None = None,
    te_annotation_options: TeAnnotationOptions | None = None,
    tsd_search_options: TsdSearchOptions | None = None,
    cancel: JobCancellation | None = None,
) -> list[str]:
    """Run one tool on one FASTA. Returns list of created output paths (strings)."""
    seq_path = seq_path.expanduser().resolve()
    out_dir = seq_path.parent
    created: list[str] = []
    os_type = os.uname().sysname if hasattr(os, "uname") else "Darwin"
    active_genome = genome_path or project.genome_file
    label_suffix = genome_output_suffix(genome_label)

    if func_name == "blast":
        if genome_db is None:
            raise RuntimeError("Genome BLAST database not prepared.")
        blast_opts = blast_options or BlastOptions()
        blast_bed, blast_txt = run_blast(
            str(seq_path),
            str(genome_db),
            str(out_dir),
            e_value=blast_opts.e_value,
            bed_file=True,
            os_type=os_type,
            num_threads=analysis_threads_per_job(project.batch_workers),
            use_system_blast=project.use_system_blast,
            output_label=genome_label or None,
        )
        if not blast_bed:
            raise RuntimeError(f"Blast failed: {blast_bed}")
        max_lines = blast_opts.max_msa_lines
        top_lines = blast_opts.top_msa_lines
        blast_bed_filtered = process_bed_lines(
            str(blast_bed),
            str(out_dir),
            max_lines=max_lines,
            top_longest_lines_count=top_lines,
        )
        blast_fa = f"{blast_txt}.fa"
        extract_fasta_from_bed(
            str(active_genome),
            str(blast_bed_filtered),
            blast_fa,
        )
        # Expose both Blast outputs so the UI highlights all newly generated files.
        if blast_txt:
            blast_txt_path = Path(str(blast_txt)).resolve()
            created.append(str(blast_txt_path))
            if blast_opts.write_gff:
                gff_path = write_blast_gff(
                    blast_txt_path,
                    minimum_bit_score=blast_opts.minimum_bit_score,
                )
                created.append(str(gff_path.resolve()))
        # Keep *_blast.txt for downstream plots; remove temporary BED intermediates.
        for tmp in (Path(str(blast_bed)), Path(str(blast_bed_filtered))):
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        created.append(blast_fa)

    elif func_name == "extend":
        if chrom_sizes is None:
            raise RuntimeError("Genome chromosome sizes not prepared.")
        if active_genome is None:
            raise RuntimeError("Genome FASTA is required for Extend.")
        extend_opts = extend or ExtendOptions()
        left = extend_opts.left
        right = extend_opts.right
        stem = seq_path.stem
        tag = f"{label_suffix}_L{left}_R{right}"
        in_bed = out_dir / f"{stem}{tag}_hdr.bed"
        ext_bed = out_dir / f"{stem}{tag}.bed"
        ext_fa = out_dir / f"{stem}{tag}.fa"
        fasta_header_to_bed(str(seq_path), str(in_bed))
        extend_bed_regions(str(in_bed), left, right, chrom_sizes, str(ext_bed))
        extract_fasta_from_bed(str(active_genome), str(ext_bed), str(ext_fa))
        for bed_path in (in_bed, ext_bed):
            try:
                bed_path.unlink(missing_ok=True)
            except OSError:
                pass
        created.append(str(ext_fa))

    elif func_name == "teaid":
        teaid_opts = teaid_options or TeaAidOptions()
        html_path = out_dir / f"{seq_path.name}{label_suffix}_TEAid.html"
        teaid_work_dir = out_dir
        scratch_dir: Path | None = None
        pan_genome_run = project.is_pan_genome_mode and len(project.pan_genomes) >= 2
        if pan_genome_run:
            scratch_dir = out_dir / f"_teaid_{seq_path.stem}_pan"
            scratch_dir.mkdir(parents=True, exist_ok=True)
            teaid_work_dir = scratch_dir
            html_path = out_dir / f"{seq_path.name}_TEAid.html"
        elif genome_label:
            scratch_dir = out_dir / f"_teaid_{seq_path.stem}{label_suffix}"
            scratch_dir.mkdir(parents=True, exist_ok=True)
            teaid_work_dir = scratch_dir
        _patch_plotly_no_auto_open()
        try:
            if pan_genome_run:
                genome_targets = [
                    (entry.name, str(entry.path.expanduser().resolve()))
                    for entry in project.pan_genomes
                ]
                run_ok = teaid_pan_genome_plotter(
                    str(seq_path),
                    str(teaid_work_dir),
                    genome_targets,
                    e_value=teaid_opts.e_value,
                    num_threads=analysis_threads_per_job(project.batch_workers),
                    use_system_blast=project.use_system_blast,
                    self_blast_word_size=teaid_opts.self_blast_word_size,
                )
            else:
                run_ok = teaid_plotter(
                    str(seq_path),
                    str(teaid_work_dir),
                    str(active_genome) if active_genome else None,
                    None,
                    e_value=teaid_opts.e_value,
                    num_threads=analysis_threads_per_job(project.batch_workers),
                    use_system_blast=project.use_system_blast,
                    self_blast_word_size=teaid_opts.self_blast_word_size,
                    output_name_tag=genome_label or None,
                )
        except TeaidInputError as exc:
            if scratch_dir is not None:
                shutil.rmtree(scratch_dir, ignore_errors=True)
            raise RuntimeError(str(exc)) from exc
        if not run_ok:
            if scratch_dir is not None:
                shutil.rmtree(scratch_dir, ignore_errors=True)
            raise RuntimeError("TEAid returned failure.")
        scratch_name = f"{seq_path.name}_TEAid.html" if pan_genome_run else (
            f"{seq_path.name}{label_suffix}_TEAid.html"
        )
        scratch_html = teaid_work_dir / scratch_name
        if scratch_dir is not None:
            if not scratch_html.is_file():
                shutil.rmtree(scratch_dir, ignore_errors=True)
                raise RuntimeError(f"TEAid HTML not created: {scratch_html}")
            if html_path.exists():
                html_path.unlink()
            shutil.move(str(scratch_html), str(html_path))
            cleanup_teaid_side_files(scratch_dir, seq_path, scratch_html)
            shutil.rmtree(scratch_dir, ignore_errors=True)
        else:
            if not html_path.is_file():
                raise RuntimeError(f"TEAid HTML not created: {html_path}")
            cleanup_teaid_side_files(out_dir, seq_path, html_path)
        created.append(str(html_path.resolve()))

    elif func_name == "msa_clean_gappy":
        msa_opts = msa_clean_options or MsaCleanOptions()
        g = msa_opts.gappy
        gcol_out = f"{seq_path}_gcol.fa"
        remove_gaps_with_similarity_check(
            str(seq_path),
            gcol_out,
            gap_threshold=g.gap_threshold,
            simi_check_gap_thr=g.simi_check_gap_thr,
            similarity_thr=g.similarity_thr,
            min_nucleotide=g.min_nucleotide,
        )
        created.append(gcol_out)

    elif func_name == "msa_clean_row_col":
        msa_opts = msa_clean_options or MsaCleanOptions()
        div = msa_opts.divergence
        g = msa_opts.gappy
        div_out = f"{seq_path}_cd.fa"
        clean_out = f"{seq_path}_clean.fa"
        crop_end_div(
            str(seq_path),
            div_out,
            threshold=div.threshold,
            window_size=div.window_size,
        )
        remove_gaps_with_similarity_check(
            div_out,
            clean_out,
            gap_threshold=g.gap_threshold,
            simi_check_gap_thr=g.simi_check_gap_thr,
            similarity_thr=g.similarity_thr,
            min_nucleotide=g.min_nucleotide,
        )
        created.append(clean_out)

    elif func_name in {"msa_clean_div", "msa_clean_gap"}:
        msa_opts = msa_clean_options or MsaCleanOptions()
        div = msa_opts.divergence
        gap = msa_opts.gap_row
        div_out = f"{seq_path}_cd.fa"
        gap_out = f"{seq_path}_cg.fa"
        crop_end_div(
            str(seq_path),
            div_out,
            threshold=div.threshold,
            window_size=div.window_size,
        )
        if func_name == "msa_clean_div":
            created.append(div_out)
        else:
            crop_end_gap(
                div_out,
                gap_out,
                gap_threshold=gap.gap_threshold,
                window_size=gap.window_size,
            )
            created.append(gap_out)

    elif func_name == "consensus_generation":
        cons_opts = consensus_options or ConsensusOptions()
        cons_out, _ = con_generater(
            str(seq_path),
            str(out_dir),
            threshold=cons_opts.threshold,
            ambiguous=cons_opts.ambiguous,
        )
        created.append(cons_out)

    elif func_name == "flexidot":
        flex_opts = flexidot_options or FlexidotOptions()
        seq_count = sum(1 for _ in SeqIO.parse(str(seq_path), "fasta"))
        if seq_count < 1:
            raise RuntimeError(f"No sequences in {seq_path.name} (Flexidot needs at least one).")
        out_path = Path(out_dir).resolve()
        with _flexidot_dir_lock(out_path):
            before = _png_paths_in_dir(out_path)
            run_flexidot(
                str(seq_path),
                str(out_path),
                wordsize=flex_opts.wordsize,
                mode=flexidot_mode,
                lcs_shading=flex_opts.lcs_shading,
                use_gff=flex_opts.use_gff,
                gff_source_fastas=[str(seq_path)],
                gff_output_stem=flexidot_output_stem([seq_path.resolve()], genome_label),
                cancel=cancel,
            )
            created.extend(
                finalize_flexidot_outputs(out_path, [seq_path.resolve()], before)
            )

    elif func_name == "te_annotation":
        te_opts = te_annotation_options or TeAnnotationOptions()
        outs = run_te_annotation_on_fasta(
            seq_path,
            te_opts,
            cancel=cancel,
        )
        created.extend(str(p) for p in outs)

    elif func_name == "tsd_search":
        tsd_opts = tsd_search_options or TsdSearchOptions()
        if tsd_opts.left_boundary <= 0 or tsd_opts.right_boundary <= 0:
            raise RuntimeError(
                "Set left and right MSA boundary columns before running TSD search."
            )
        if tsd_opts.left_boundary >= tsd_opts.right_boundary:
            raise RuntimeError("Left boundary must be less than the right boundary.")
        out_file = out_dir / f"{seq_path.stem}.tsd_search.txt"
        TSD_identifier(
            tsd_opts.left_boundary,
            tsd_opts.right_boundary,
            tsd_opts.nt_radius,
            seq_path,
            out_file,
            max_sim_threshold=tsd_opts.max_sim_threshold,
            nt_threshold=tsd_opts.nt_threshold,
            cluster_eps=tsd_opts.cluster_eps,
        )
        created.append(str(out_file.resolve()))

    else:
        raise ValueError(f"Unknown function: {func_name}")

    return created


def run_batch(
    func_name: str,
    seq_files: Iterable[Path],
    project: TEviewerProject,
    progress_cb: ProgressCallback,
    *,
    flexidot_options: FlexidotOptions | None = None,
    flexidot_mode: str = "0",
    extend: ExtendOptions | None = None,
    blast_options: BlastOptions | None = None,
    teaid_options: TeaAidOptions | None = None,
    msa_clean_options: MsaCleanOptions | None = None,
    consensus_options: ConsensusOptions | None = None,
    te_annotation_options: TeAnnotationOptions | None = None,
    tsd_search_options: TsdSearchOptions | None = None,
    max_workers: int = 4,
    flexidot_combined: bool = True,
    cancel: JobCancellation | None = None,
) -> dict:
    seq_list = list(seq_files)
    failures: list[str] = []
    created_outputs: list[str] = []
    source_files: list[str] = []
    os_type = os.uname().sysname if hasattr(os, "uname") else "Darwin"

    genome_dependent = func_name in {"blast", "extend", "teaid", "flexidot"}
    genome_items: list[tuple[str, Path]] = []
    db_cache: dict[Path, str] = {}
    chrom_cache: dict[Path, dict[str, int]] = {}

    if genome_dependent:
        if not project.has_genome_configured():
            raise RuntimeError("Genome FASTA is required for this tool.")
        genome_items = _genome_work_items(project, func_name, extend)
        db_cache, chrom_cache = _prepare_genome_resources(
            func_name, genome_items, project, os_type
        )

    display_name = _DISPLAY_NAMES.get(func_name, func_name)

    if func_name == "flexidot" and len(seq_list) > 1 and flexidot_combined:
        total_steps = len(genome_items) if genome_items else 1
        progress_cb(0, f"{display_name}: {len(seq_list)} sequences (comparison)")
        check_cancelled(cancel)
        completed = 0
        targets = genome_items or [("", Path(project.genome_file or ""))]
        for genome_label, genome_path in targets:
            check_cancelled(cancel)
            try:
                outs = run_flexidot_combined(
                    seq_list,
                    flexidot_options=flexidot_options,
                    cancel=cancel,
                    genome_label=genome_label,
                )
                created_outputs.extend(outs)
                for seq_path in seq_list:
                    source_files.append(str(seq_path.resolve()))
            except JobCancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                label = f" ({genome_label})" if genome_label else ""
                failures.append(f"batch{label}: {exc}")
            completed += 1
            progress_cb(completed, f"{display_name}: finished")
        return {
            "func_name": func_name,
            "total": total_steps,
            "failures": failures,
            "created_outputs": created_outputs,
            "source_files": source_files,
        }

    work_items: list[tuple[Path, str, Path | None]] = []
    if genome_dependent and genome_items:
        if func_name == "teaid" and project.is_pan_genome_mode:
            for seq_path in seq_list:
                work_items.append((seq_path, "", None))
        else:
            for seq_path in seq_list:
                for genome_label, genome_path in genome_items:
                    work_items.append((seq_path, genome_label, genome_path))
    else:
        for seq_path in seq_list:
            work_items.append((seq_path, "", None))

    workers = 1 if func_name == "te_annotation" else effective_batch_workers(
        max_workers, len(work_items)
    )
    progress_lock = threading.Lock()
    completed_count = 0

    def _run_single(
        seq_path: Path,
        genome_label: str,
        genome_path: Path | None,
    ) -> tuple[Path, str, list[str], str | None]:
        try:
            check_cancelled(cancel)
            outs = run_on_sequence(
                func_name,
                seq_path,
                project,
                genome_path=genome_path,
                genome_label=genome_label,
                genome_db=db_cache.get(genome_path) if genome_path else None,
                chrom_sizes=chrom_cache.get(genome_path) if genome_path else None,
                flexidot_options=flexidot_options,
                flexidot_mode="0" if func_name == "flexidot" else flexidot_mode,
                extend=extend,
                blast_options=blast_options,
                teaid_options=teaid_options,
                msa_clean_options=msa_clean_options,
                consensus_options=consensus_options,
                te_annotation_options=te_annotation_options,
                tsd_search_options=tsd_search_options,
                cancel=cancel,
            )
            return seq_path, genome_label, outs, None
        except JobCancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            return seq_path, genome_label, [], str(exc)

    def _record_finished(
        seq_path: Path,
        genome_label: str,
        outs: list[str],
        error: str | None,
    ) -> None:
        nonlocal completed_count
        label = f" ({genome_label})" if genome_label else ""
        with progress_lock:
            completed_count += 1
            progress_cb(
                completed_count - 1,
                f"{display_name}: {seq_path.name}{label}",
            )
        if error:
            failures.append(f"{seq_path.name}{label}: {error}")
        else:
            created_outputs.extend(outs)
            source_files.append(str(seq_path.resolve()))

    if workers == 1:
        for seq_path, genome_label, genome_path in work_items:
            check_cancelled(cancel)
            path, label, outs, error = _run_single(seq_path, genome_label, genome_path)
            _record_finished(path, label, outs, error)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_run_single, seq_path, genome_label, genome_path)
                for seq_path, genome_label, genome_path in work_items
            ]
            for future in as_completed(futures):
                try:
                    path, label, outs, error = future.result()
                except JobCancelledError:
                    for pending in futures:
                        pending.cancel()
                    raise
                _record_finished(path, label, outs, error)

    progress_cb(len(work_items), f"{display_name}: finished")

    return {
        "func_name": func_name,
        "total": len(work_items),
        "failures": failures,
        "created_outputs": created_outputs,
        "source_files": source_files,
    }


def _patch_plotly_no_auto_open() -> None:
    _orig = pio.write_html

    def _write_html(*args, **kwargs):
        kwargs.setdefault("auto_open", False)
        return _orig(*args, **kwargs)

    pio.write_html = _write_html

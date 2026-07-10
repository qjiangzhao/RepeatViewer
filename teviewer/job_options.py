"""Per-job parameters passed from the UI into curation backends."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

DEFAULT_EXTEND_LEFT = 1000
DEFAULT_EXTEND_RIGHT = 1000
# Default reporting E-value (shown as 0.0001 with four decimal places in the UI).
DEFAULT_REPORT_EVALUE = 1e-4
DEFAULT_BLAST_EVALUE = DEFAULT_REPORT_EVALUE
MIN_BLAST_EVALUE = 1e-4
DEFAULT_BLAST_THREADS = 1
DEFAULT_BLAST_MAX_MSA_LINES = 100
DEFAULT_BLAST_TOP_MSA_LINES = 70
DEFAULT_BLAST_WRITE_GFF = False
DEFAULT_BLAST_MINIMUM_BIT_SCORE = 0.0

DEFAULT_TE_GENOME_MAP_BIN_BP = 100_000
TE_GENOME_MAP_DENSITY_HIT_COUNT = "hit_count"
TE_GENOME_MAP_DENSITY_TE_LENGTH = "te_length"
DEFAULT_TE_GENOME_MAP_DENSITY = TE_GENOME_MAP_DENSITY_TE_LENGTH
TE_GENOME_MAP_COLOR_IDENTITY = "identity"
TE_GENOME_MAP_COLOR_SUPERFAMILY = "superfamily"
TE_GENOME_MAP_COLOR_FAMILY = "family"
DEFAULT_TE_GENOME_MAP_COLOR_BY = TE_GENOME_MAP_COLOR_SUPERFAMILY
DEFAULT_TE_GENOME_MAP_SPLIT_STRAND = False
DEFAULT_TE_GENOME_MAP_COLLAPSE_OVERLAPS = False
DEFAULT_TE_GENOME_MAP_SHOW_DIFF_TRACK = False
DEFAULT_TE_GENOME_MAP_SHOW_METH_DIFF_TRACK = False
DEFAULT_TE_GENOME_MAP_WINDOW_REF_LINE = True
CHROMOSOME_SORT_NATURAL = "natural"
CHROMOSOME_SORT_SIZE_DESC = "size_desc"
CHROMOSOME_SORT_SIZE_ASC = "size_asc"
DEFAULT_CHROMOSOME_SORT = CHROMOSOME_SORT_NATURAL
DEFAULT_TE_GENOME_MAP_METHYLATION_COVERAGE_MIN = 5
DEFAULT_ANNOTATION_DENSITY = TE_GENOME_MAP_DENSITY_TE_LENGTH
DEFAULT_ANNOTATION_FEATURE_TYPES = ("gene",)


@dataclass
class TeGenomeMapOptions:
    """TE density plot: bin window, density metric, and chromosome filter."""

    bin_size_bp: int = DEFAULT_TE_GENOME_MAP_BIN_BP
    density_mode: str = DEFAULT_TE_GENOME_MAP_DENSITY
    color_by: str = DEFAULT_TE_GENOME_MAP_COLOR_BY
    methylation_coverage_min: int = DEFAULT_TE_GENOME_MAP_METHYLATION_COVERAGE_MIN
    split_strand_tracks: bool = DEFAULT_TE_GENOME_MAP_SPLIT_STRAND
    collapse_overlaps: bool = DEFAULT_TE_GENOME_MAP_COLLAPSE_OVERLAPS
    show_te_diff_track: bool = DEFAULT_TE_GENOME_MAP_SHOW_DIFF_TRACK
    show_meth_diff_track: bool = DEFAULT_TE_GENOME_MAP_SHOW_METH_DIFF_TRACK
    show_window_ref_line: bool = DEFAULT_TE_GENOME_MAP_WINDOW_REF_LINE
    annotation_density_mode: str = DEFAULT_ANNOTATION_DENSITY
    annotation_feature_types: list[str] | None = None
    annotation_feature_types_by_file: dict[str, list[str]] | None = None
    chromosomes_only: list[str] | None = None
    superfamilies_only: list[str] | None = None
    chromosome_sort: str = DEFAULT_CHROMOSOME_SORT


DEFAULT_TE_DIVERGENCE_BIN_WIDTH = 0.005


@dataclass
class TeDivergencePlotOptions:
    """TE divergence histogram: x-axis bin width on 0–1 divergence scale."""

    bin_width: float = DEFAULT_TE_DIVERGENCE_BIN_WIDTH


DEFAULT_TE_BENCHMARK_THREADS = 4


@dataclass
class TeConfusionMatrixBenchmarkOptions:
    """Confusion-matrix benchmark (query vs reference RepeatMasker .out on genome)."""

    tetrimmer_home: str = ""
    reference_out: str = ""
    less_classification: bool = False
    debug: bool = False


@dataclass
class TeLibraryBenchmarkOptions:
    """TE consensus-library benchmark (Perfect / Good / Present)."""

    query_fasta: str = ""
    standard_fasta: str = ""
    rm_out: str = ""
    run_repeatmasker: bool = True
    threads: int = DEFAULT_TE_BENCHMARK_THREADS


@dataclass
class ExtendOptions:
    left: int = DEFAULT_EXTEND_LEFT
    right: int = DEFAULT_EXTEND_RIGHT
    pan_genome_name: str | None = None


DEFAULT_TSD_LEFT_BOUNDARY = 0
DEFAULT_TSD_RIGHT_BOUNDARY = 0
DEFAULT_TSD_NT_RADIUS = 100
DEFAULT_TSD_MAX_SIM_THRESHOLD = 0.3
DEFAULT_TSD_NT_THRESHOLD = 0.95
DEFAULT_TSD_CLUSTER_EPS = 1.0


@dataclass
class TsdSearchOptions:
    """TSD search boundaries and filtering (MSA column positions)."""

    left_boundary: int = DEFAULT_TSD_LEFT_BOUNDARY
    right_boundary: int = DEFAULT_TSD_RIGHT_BOUNDARY
    nt_radius: int = DEFAULT_TSD_NT_RADIUS
    max_sim_threshold: float = DEFAULT_TSD_MAX_SIM_THRESHOLD
    nt_threshold: float = DEFAULT_TSD_NT_THRESHOLD
    cluster_eps: float = DEFAULT_TSD_CLUSTER_EPS


ALIGN_BACKEND_AUTO = "auto"
ALIGN_BACKEND_MAFFT = "mafft"
ALIGN_BACKEND_CLUSTALO = "clustalo"
DEFAULT_ALIGN_BACKEND = ALIGN_BACKEND_AUTO
DEFAULT_ALIGN_THREADS = 5
ALIGN_MODE_COMBINED = "combined"


@dataclass
class AlignOptions:
    """MAFFT / Clustal alignment: backend and thread count."""

    backend: str = DEFAULT_ALIGN_BACKEND
    num_threads: int = DEFAULT_ALIGN_THREADS


@dataclass
class BlastOptions:
    e_value: float = DEFAULT_BLAST_EVALUE
    num_threads: int = DEFAULT_BLAST_THREADS
    max_msa_lines: int = DEFAULT_BLAST_MAX_MSA_LINES
    top_msa_lines: int = DEFAULT_BLAST_TOP_MSA_LINES
    write_gff: bool = DEFAULT_BLAST_WRITE_GFF
    minimum_bit_score: float = DEFAULT_BLAST_MINIMUM_BIT_SCORE


DEFAULT_CONSENSUS_THRESHOLD = 0.8
DEFAULT_CONSENSUS_AMBIGUOUS = "N"


@dataclass
class ConsensusOptions:
    threshold: float = DEFAULT_CONSENSUS_THRESHOLD
    ambiguous: str = DEFAULT_CONSENSUS_AMBIGUOUS


DEFAULT_FLEXIDOT_WORDSIZE = 3
DEFAULT_FLEXIDOT_LCS_SHADING = True
DEFAULT_FLEXIDOT_USE_GFF = False
MIN_FLEXIDOT_WORDSIZE = 3
MAX_FLEXIDOT_WORDSIZE = 100


@dataclass
class FlexidotOptions:
    """Flexidot -k (word size), -x (LCS shading), and optional -g/-G GFF shading."""

    wordsize: int = DEFAULT_FLEXIDOT_WORDSIZE
    lcs_shading: bool = DEFAULT_FLEXIDOT_LCS_SHADING
    use_gff: bool = DEFAULT_FLEXIDOT_USE_GFF


DEFAULT_TEAID_EVALUE = DEFAULT_REPORT_EVALUE
DEFAULT_TEAID_THREADS = 1
DEFAULT_TEAID_SELF_BLAST_WORD_SIZE = 11
MIN_TEAID_SELF_BLAST_WORD_SIZE = 4
MAX_TEAID_SELF_BLAST_WORD_SIZE = 25


def clamp_teaid_self_blast_word_size(requested: int) -> int:
    """Clamp TEAid self-BLAST ``-word_size`` to 4–25."""
    return max(
        MIN_TEAID_SELF_BLAST_WORD_SIZE,
        min(MAX_TEAID_SELF_BLAST_WORD_SIZE, int(requested)),
    )


def configure_report_evalue_spinbox(spin) -> None:
    """Four decimal places (e.g. 0.0001), minimum 0.0001 for BLAST+."""
    spin.setDecimals(4)
    spin.setRange(MIN_BLAST_EVALUE, 1.0)
    spin.setSingleStep(0.0001)


def normalize_blast_evalue(e_value: float, *, default: float = DEFAULT_BLAST_EVALUE) -> float:
    """BLAST+ requires a strictly positive -evalue."""
    try:
        value = float(e_value)
    except (TypeError, ValueError):
        return default
    if value <= 0.0:
        return default
    return max(value, MIN_BLAST_EVALUE)


@dataclass
class TeaAidOptions:
    e_value: float = DEFAULT_TEAID_EVALUE
    self_blast_word_size: int = DEFAULT_TEAID_SELF_BLAST_WORD_SIZE
    num_threads: int = DEFAULT_TEAID_THREADS


# remove_gaps_with_similarity_check defaults (TEtrimmerGUI)
DEFAULT_GAP_COL_GAP_THRESHOLD = 0.8
DEFAULT_GAP_COL_SIMI_GAP_THR = 0.4
DEFAULT_GAP_COL_SIMILARITY_THR = 0.7
DEFAULT_GAP_COL_MIN_NUCLEOTIDE = 5


@dataclass
class GappyColumnOptions:
    gap_threshold: float = DEFAULT_GAP_COL_GAP_THRESHOLD
    simi_check_gap_thr: float = DEFAULT_GAP_COL_SIMI_GAP_THR
    similarity_thr: float = DEFAULT_GAP_COL_SIMILARITY_THR
    min_nucleotide: int = DEFAULT_GAP_COL_MIN_NUCLEOTIDE


DEFAULT_DIV_THRESHOLD = 0.8
DEFAULT_DIV_WINDOW_SIZE = 20
DEFAULT_GAP_ROW_GAP_THRESHOLD = 0.05
DEFAULT_GAP_ROW_WINDOW_SIZE = 300


@dataclass
class DivergenceRowOptions:
    """Parameters for clean row with divergence (crop_end_div)."""

    threshold: float = DEFAULT_DIV_THRESHOLD
    window_size: int = DEFAULT_DIV_WINDOW_SIZE


@dataclass
class GapRowOptions:
    """Parameters for clean row with gap (crop_end_gap)."""

    gap_threshold: float = DEFAULT_GAP_ROW_GAP_THRESHOLD
    window_size: int = DEFAULT_GAP_ROW_WINDOW_SIZE


MSA_CLEAN_METHOD_CHOICES: tuple[tuple[str, str], ...] = (
    ("msa_clean_gappy", "Remove gappy columns"),
    ("msa_clean_div", "Clean row with divergence"),
    ("msa_clean_gap", "Clean row with gap"),
    ("msa_clean_row_col", "Clean row and column"),
)
MSA_CLEAN_METHOD_IDS = frozenset(mid for mid, _ in MSA_CLEAN_METHOD_CHOICES)
DEFAULT_MSA_CLEAN_METHOD = "msa_clean_gappy"

MSA_CLEAN_METHOD_DESCRIPTIONS: dict[str, str] = {
    "msa_clean_gappy": "Remove columns that are mostly gaps (uses the gappy-column parameters below).",
    "msa_clean_div": (
        "Trim alignment ends where rows diverge from the consensus "
        "(uses the clean row with divergence parameters below)."
    ),
    "msa_clean_gap": (
        "After divergence trimming, trim ends where rows are mostly gaps "
        "(uses the clean row with gap parameters below)."
    ),
    "msa_clean_row_col": (
        "Step 1: clean row with divergence. "
        "Step 2: remove gappy columns on that result. "
        "Final output: {name}_clean.fa (intermediate {name}_cd.fa)."
    ),
}


def msa_clean_method_label(method_id: str) -> str:
    for mid, label in MSA_CLEAN_METHOD_CHOICES:
        if mid == method_id:
            return label
    return method_id


def msa_clean_method_description(method_id: str) -> str:
    return MSA_CLEAN_METHOD_DESCRIPTIONS.get(
        method_id,
        "",
    )


@dataclass
class MsaCleanOptions:
    """All MSA clean tool parameters (gappy columns + row cleaning)."""

    default_method: str = DEFAULT_MSA_CLEAN_METHOD
    gappy: GappyColumnOptions = field(default_factory=GappyColumnOptions)
    divergence: DivergenceRowOptions = field(default_factory=DivergenceRowOptions)
    gap_row: GapRowOptions = field(default_factory=GapRowOptions)

    def __post_init__(self) -> None:
        if self.default_method not in MSA_CLEAN_METHOD_IDS:
            self.default_method = DEFAULT_MSA_CLEAN_METHOD


def load_msa_clean_options() -> MsaCleanOptions:
    from PySide6.QtCore import QSettings

    s = QSettings()
    s.beginGroup("msa_clean")
    method = str(s.value("default_method", DEFAULT_MSA_CLEAN_METHOD))
    opts = MsaCleanOptions(
        default_method=method,
        gappy=GappyColumnOptions(
            gap_threshold=float(s.value("gappy_gap_threshold", DEFAULT_GAP_COL_GAP_THRESHOLD)),
            simi_check_gap_thr=float(
                s.value("gappy_simi_check_gap_thr", DEFAULT_GAP_COL_SIMI_GAP_THR)
            ),
            similarity_thr=float(
                s.value("gappy_similarity_thr", DEFAULT_GAP_COL_SIMILARITY_THR)
            ),
            min_nucleotide=int(s.value("gappy_min_nucleotide", DEFAULT_GAP_COL_MIN_NUCLEOTIDE)),
        ),
        divergence=DivergenceRowOptions(
            threshold=float(s.value("div_threshold", DEFAULT_DIV_THRESHOLD)),
            window_size=int(s.value("div_window_size", DEFAULT_DIV_WINDOW_SIZE)),
        ),
        gap_row=GapRowOptions(
            gap_threshold=float(s.value("gap_row_gap_threshold", DEFAULT_GAP_ROW_GAP_THRESHOLD)),
            window_size=int(s.value("gap_row_window_size", DEFAULT_GAP_ROW_WINDOW_SIZE)),
        ),
    )
    s.endGroup()
    return opts


def _load_settings_group(group: str) -> dict:
    from PySide6.QtCore import QSettings

    s = QSettings()
    s.beginGroup(group)
    keys = s.allKeys()
    out = {k: s.value(k) for k in keys}
    s.endGroup()
    return out


def _save_settings_group(group: str, values: dict) -> None:
    from PySide6.QtCore import QSettings

    s = QSettings()
    s.beginGroup(group)
    for key, value in values.items():
        s.setValue(key, value)
    s.endGroup()


def load_blast_options() -> BlastOptions:
    v = _load_settings_group("blast")
    return BlastOptions(
        e_value=normalize_blast_evalue(float(v.get("e_value", DEFAULT_BLAST_EVALUE))),
        num_threads=int(v.get("num_threads", DEFAULT_BLAST_THREADS)),
        max_msa_lines=int(v.get("max_msa_lines", DEFAULT_BLAST_MAX_MSA_LINES)),
        top_msa_lines=int(v.get("top_msa_lines", DEFAULT_BLAST_TOP_MSA_LINES)),
        write_gff=bool(v.get("write_gff", DEFAULT_BLAST_WRITE_GFF)),
        minimum_bit_score=float(
            v.get("minimum_bit_score", DEFAULT_BLAST_MINIMUM_BIT_SCORE)
        ),
    )


def save_blast_options(opts: BlastOptions) -> None:
    _save_settings_group(
        "blast",
        {
            "e_value": opts.e_value,
            "max_msa_lines": opts.max_msa_lines,
            "top_msa_lines": opts.top_msa_lines,
            "write_gff": opts.write_gff,
            "minimum_bit_score": opts.minimum_bit_score,
        },
    )


def load_extend_options() -> ExtendOptions:
    v = _load_settings_group("extend")
    pan_name = v.get("pan_genome_name")
    return ExtendOptions(
        left=int(v.get("left", DEFAULT_EXTEND_LEFT)),
        right=int(v.get("right", DEFAULT_EXTEND_RIGHT)),
        pan_genome_name=str(pan_name).strip() if pan_name else None,
    )


def save_extend_options(opts: ExtendOptions) -> None:
    _save_settings_group(
        "extend",
        {
            "left": opts.left,
            "right": opts.right,
            "pan_genome_name": opts.pan_genome_name or "",
        },
    )


def load_tsd_search_options() -> TsdSearchOptions:
    v = _load_settings_group("tsd_search")
    return TsdSearchOptions(
        left_boundary=int(v.get("left_boundary", DEFAULT_TSD_LEFT_BOUNDARY)),
        right_boundary=int(v.get("right_boundary", DEFAULT_TSD_RIGHT_BOUNDARY)),
        nt_radius=max(1, int(v.get("nt_radius", DEFAULT_TSD_NT_RADIUS))),
        max_sim_threshold=float(
            v.get("max_sim_threshold", DEFAULT_TSD_MAX_SIM_THRESHOLD)
        ),
        nt_threshold=float(v.get("nt_threshold", DEFAULT_TSD_NT_THRESHOLD)),
        cluster_eps=float(v.get("cluster_eps", DEFAULT_TSD_CLUSTER_EPS)),
    )


def save_tsd_search_options(opts: TsdSearchOptions) -> None:
    _save_settings_group(
        "tsd_search",
        {
            "left_boundary": opts.left_boundary,
            "right_boundary": opts.right_boundary,
            "nt_radius": opts.nt_radius,
            "max_sim_threshold": opts.max_sim_threshold,
            "nt_threshold": opts.nt_threshold,
            "cluster_eps": opts.cluster_eps,
        },
    )


def load_teaid_options() -> TeaAidOptions:
    v = _load_settings_group("teaid")
    word_size = int(v.get("self_blast_word_size", DEFAULT_TEAID_SELF_BLAST_WORD_SIZE))
    word_size = max(
        MIN_TEAID_SELF_BLAST_WORD_SIZE,
        min(MAX_TEAID_SELF_BLAST_WORD_SIZE, word_size),
    )
    return TeaAidOptions(
        e_value=normalize_blast_evalue(
            float(v.get("e_value", DEFAULT_TEAID_EVALUE)),
            default=DEFAULT_TEAID_EVALUE,
        ),
        self_blast_word_size=word_size,
        num_threads=max(1, int(v.get("num_threads", DEFAULT_TEAID_THREADS))),
    )


def save_teaid_options(opts: TeaAidOptions) -> None:
    _save_settings_group(
        "teaid",
        {
            "e_value": opts.e_value,
            "self_blast_word_size": opts.self_blast_word_size,
        },
    )


def load_align_options() -> AlignOptions:
    v = _load_settings_group("align")
    backend = str(v.get("backend", DEFAULT_ALIGN_BACKEND))
    if backend not in (ALIGN_BACKEND_AUTO, ALIGN_BACKEND_MAFFT, ALIGN_BACKEND_CLUSTALO):
        backend = DEFAULT_ALIGN_BACKEND
    return AlignOptions(
        backend=backend,
        num_threads=max(1, int(v.get("num_threads", DEFAULT_ALIGN_THREADS))),
    )


def save_align_options(opts: AlignOptions) -> None:
    _save_settings_group(
        "align",
        {
            "backend": opts.backend,
            "num_threads": opts.num_threads,
        },
    )


def _parse_chromosomes_only_setting(raw) -> list[str] | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (list, tuple)):
        names = [str(x).strip() for x in raw if str(x).strip()]
        return names or None
    text = str(raw).strip()
    if not text:
        return None
    names = [part.strip() for part in text.replace(",", "\n").splitlines() if part.strip()]
    return names or None


def _parse_name_list_setting(raw) -> list[str] | None:
    if raw is None or raw == "":
        return None
    if raw == "__NONE__":
        return []
    if isinstance(raw, (list, tuple)):
        values = [str(x).strip() for x in raw if str(x).strip()]
        return values or None
    text = str(raw).strip()
    if not text:
        return None
    values = [part.strip() for part in text.replace(",", "\n").splitlines() if part.strip()]
    return values or None


def _serialize_annotation_feature_types_by_file(
    by_file: dict[str, list[str]] | None,
) -> str:
    if not by_file:
        return ""
    payload: dict[str, list[str]] = {}
    for raw_path, types in by_file.items():
        path = str(raw_path).strip()
        if not path:
            continue
        cleaned = [str(t).strip() for t in types if str(t).strip()]
        if cleaned:
            payload[path] = cleaned
    if not payload:
        return ""
    return json.dumps(payload, sort_keys=True)


def _parse_annotation_feature_types_by_file(raw: object) -> dict[str, list[str]] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        out: dict[str, list[str]] = {}
        for key, value in raw.items():
            path = str(key).strip()
            if not path:
                continue
            if isinstance(value, str):
                types = [p.strip() for p in value.replace(",", "\n").splitlines() if p.strip()]
            elif isinstance(value, (list, tuple)):
                types = [str(t).strip() for t in value if str(t).strip()]
            else:
                continue
            if types:
                out[path] = types
        return out or None
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return _parse_annotation_feature_types_by_file(parsed)
    return None


def load_te_genome_map_options() -> TeGenomeMapOptions:
    v = _load_settings_group("te_genome_map")
    mode = str(v.get("density_mode", DEFAULT_TE_GENOME_MAP_DENSITY))
    if mode not in (TE_GENOME_MAP_DENSITY_HIT_COUNT, TE_GENOME_MAP_DENSITY_TE_LENGTH):
        mode = DEFAULT_TE_GENOME_MAP_DENSITY
    color_by = str(v.get("color_by", DEFAULT_TE_GENOME_MAP_COLOR_BY))
    if color_by not in (
        TE_GENOME_MAP_COLOR_IDENTITY,
        TE_GENOME_MAP_COLOR_SUPERFAMILY,
        TE_GENOME_MAP_COLOR_FAMILY,
    ):
        color_by = DEFAULT_TE_GENOME_MAP_COLOR_BY
    split_strand = str(
        v.get("split_strand_tracks", str(DEFAULT_TE_GENOME_MAP_SPLIT_STRAND).lower())
    ).lower() in {"1", "true", "yes"}
    show_window_ref = str(
        v.get("show_window_ref_line", str(DEFAULT_TE_GENOME_MAP_WINDOW_REF_LINE).lower())
    ).lower() in {"1", "true", "yes"}
    collapse_overlaps = str(
        v.get("collapse_overlaps", str(DEFAULT_TE_GENOME_MAP_COLLAPSE_OVERLAPS).lower())
    ).lower() in {"1", "true", "yes"}
    show_te_diff = str(
        v.get("show_te_diff_track", str(DEFAULT_TE_GENOME_MAP_SHOW_DIFF_TRACK).lower())
    ).lower() in {"1", "true", "yes"}
    show_meth_diff = str(
        v.get(
            "show_meth_diff_track",
            str(DEFAULT_TE_GENOME_MAP_SHOW_METH_DIFF_TRACK).lower(),
        )
    ).lower() in {"1", "true", "yes"}
    ann_mode = str(v.get("annotation_density_mode", DEFAULT_ANNOTATION_DENSITY))
    if ann_mode not in (TE_GENOME_MAP_DENSITY_HIT_COUNT, TE_GENOME_MAP_DENSITY_TE_LENGTH):
        ann_mode = DEFAULT_ANNOTATION_DENSITY
    ann_types_raw = v.get("annotation_feature_types")
    ann_types: list[str] | None = None
    if isinstance(ann_types_raw, str) and ann_types_raw.strip():
        ann_types = [p.strip() for p in ann_types_raw.replace(",", "\n").splitlines() if p.strip()]
    ann_by_file = _parse_annotation_feature_types_by_file(
        v.get("annotation_feature_types_by_file"),
    )
    chrom_sort = str(v.get("chromosome_sort", DEFAULT_CHROMOSOME_SORT))
    if chrom_sort not in (
        CHROMOSOME_SORT_NATURAL,
        CHROMOSOME_SORT_SIZE_DESC,
        CHROMOSOME_SORT_SIZE_ASC,
    ):
        chrom_sort = DEFAULT_CHROMOSOME_SORT
    return TeGenomeMapOptions(
        bin_size_bp=max(5_000, int(v.get("bin_size_bp", DEFAULT_TE_GENOME_MAP_BIN_BP))),
        density_mode=mode,
        color_by=color_by,
        methylation_coverage_min=max(
            1, int(v.get("methylation_coverage_min", DEFAULT_TE_GENOME_MAP_METHYLATION_COVERAGE_MIN))
        ),
        split_strand_tracks=split_strand,
        collapse_overlaps=collapse_overlaps,
        show_te_diff_track=show_te_diff,
        show_meth_diff_track=show_meth_diff,
        show_window_ref_line=show_window_ref,
        annotation_density_mode=ann_mode,
        annotation_feature_types=ann_types,
        annotation_feature_types_by_file=ann_by_file,
        chromosomes_only=_parse_chromosomes_only_setting(v.get("chromosomes_only")),
        superfamilies_only=_parse_name_list_setting(v.get("superfamilies_only")),
        chromosome_sort=chrom_sort,
    )


def save_te_genome_map_options(opts: TeGenomeMapOptions) -> None:
    chrom_value = ""
    if opts.chromosomes_only:
        chrom_value = "\n".join(opts.chromosomes_only)
    sf_value = ""
    if opts.superfamilies_only == []:
        sf_value = "__NONE__"
    elif opts.superfamilies_only:
        sf_value = "\n".join(opts.superfamilies_only)
    _save_settings_group(
        "te_genome_map",
        {
            "bin_size_bp": opts.bin_size_bp,
            "density_mode": opts.density_mode,
            "color_by": opts.color_by,
            "methylation_coverage_min": opts.methylation_coverage_min,
            "split_strand_tracks": opts.split_strand_tracks,
            "collapse_overlaps": opts.collapse_overlaps,
            "show_te_diff_track": opts.show_te_diff_track,
            "show_meth_diff_track": opts.show_meth_diff_track,
            "show_window_ref_line": opts.show_window_ref_line,
            "annotation_density_mode": opts.annotation_density_mode,
            "annotation_feature_types": (
                ",".join(opts.annotation_feature_types) if opts.annotation_feature_types else ""
            ),
            "annotation_feature_types_by_file": _serialize_annotation_feature_types_by_file(
                opts.annotation_feature_types_by_file,
            ),
            "chromosomes_only": chrom_value,
            "superfamilies_only": sf_value,
            "chromosome_sort": opts.chromosome_sort,
        },
    )


def load_te_divergence_plot_options() -> TeDivergencePlotOptions:
    v = _load_settings_group("te_divergence_plot")
    return TeDivergencePlotOptions(
        bin_width=max(0.001, float(v.get("bin_width", DEFAULT_TE_DIVERGENCE_BIN_WIDTH))),
    )


def save_te_divergence_plot_options(opts: TeDivergencePlotOptions) -> None:
    _save_settings_group(
        "te_divergence_plot",
        {"bin_width": opts.bin_width},
    )


def load_consensus_options() -> ConsensusOptions:
    v = _load_settings_group("consensus")
    amb = str(v.get("ambiguous", DEFAULT_CONSENSUS_AMBIGUOUS)).upper()[:1] or "N"
    return ConsensusOptions(
        threshold=float(v.get("threshold", DEFAULT_CONSENSUS_THRESHOLD)),
        ambiguous=amb,
    )


def save_consensus_options(opts: ConsensusOptions) -> None:
    _save_settings_group(
        "consensus",
        {"threshold": opts.threshold, "ambiguous": opts.ambiguous},
    )


def load_flexidot_options() -> FlexidotOptions:
    v = _load_settings_group("flexidot")
    wordsize = int(v.get("wordsize", DEFAULT_FLEXIDOT_WORDSIZE))
    wordsize = max(MIN_FLEXIDOT_WORDSIZE, min(MAX_FLEXIDOT_WORDSIZE, wordsize))
    return FlexidotOptions(
        wordsize=wordsize,
        lcs_shading=str(v.get("lcs_shading", "true")).lower() in {"1", "true", "yes"},
        use_gff=str(v.get("use_gff", "false")).lower() in {"1", "true", "yes"},
    )


def save_flexidot_options(opts: FlexidotOptions) -> None:
    _save_settings_group(
        "flexidot",
        {
            "wordsize": opts.wordsize,
            "lcs_shading": opts.lcs_shading,
            "use_gff": opts.use_gff,
        },
    )


def load_te_confusion_matrix_benchmark_options() -> TeConfusionMatrixBenchmarkOptions:
    v = _load_settings_group("te_confusion_benchmark")
    home = str(v.get("tetrimmer_home", "")).strip()
    if not home:
        from teviewer.backends.te_benchmark import default_tetrimmer_home

        detected = default_tetrimmer_home()
        if detected is not None:
            home = str(detected)
    return TeConfusionMatrixBenchmarkOptions(
        tetrimmer_home=home,
        reference_out=str(v.get("reference_out", "")).strip(),
        less_classification=str(v.get("less_classification", "false")).lower()
        in {"1", "true", "yes"},
        debug=str(v.get("debug", "false")).lower() in {"1", "true", "yes"},
    )


def save_te_confusion_matrix_benchmark_options(opts: TeConfusionMatrixBenchmarkOptions) -> None:
    _save_settings_group(
        "te_confusion_benchmark",
        {
            "tetrimmer_home": opts.tetrimmer_home,
            "reference_out": opts.reference_out,
            "less_classification": opts.less_classification,
            "debug": opts.debug,
        },
    )


def load_te_library_benchmark_options() -> TeLibraryBenchmarkOptions:
    v = _load_settings_group("te_library_benchmark")
    return TeLibraryBenchmarkOptions(
        query_fasta=str(v.get("query_fasta", "")).strip(),
        standard_fasta=str(v.get("standard_fasta", "")).strip(),
        rm_out=str(v.get("rm_out", "")).strip(),
        run_repeatmasker=str(v.get("run_repeatmasker", "true")).lower() in {"1", "true", "yes"},
        threads=max(1, int(v.get("threads", DEFAULT_TE_BENCHMARK_THREADS))),
    )


def save_te_library_benchmark_options(opts: TeLibraryBenchmarkOptions) -> None:
    _save_settings_group(
        "te_library_benchmark",
        {
            "query_fasta": opts.query_fasta,
            "standard_fasta": opts.standard_fasta,
            "rm_out": opts.rm_out,
            "run_repeatmasker": opts.run_repeatmasker,
            "threads": opts.threads,
        },
    )


def save_msa_clean_options(opts: MsaCleanOptions) -> None:
    from PySide6.QtCore import QSettings

    s = QSettings()
    s.beginGroup("msa_clean")
    s.setValue("default_method", opts.default_method)
    g = opts.gappy
    s.setValue("gappy_gap_threshold", g.gap_threshold)
    s.setValue("gappy_simi_check_gap_thr", g.simi_check_gap_thr)
    s.setValue("gappy_similarity_thr", g.similarity_thr)
    s.setValue("gappy_min_nucleotide", g.min_nucleotide)
    d = opts.divergence
    s.setValue("div_threshold", d.threshold)
    s.setValue("div_window_size", d.window_size)
    gr = opts.gap_row
    s.setValue("gap_row_gap_threshold", gr.gap_threshold)
    s.setValue("gap_row_window_size", gr.window_size)
    s.endGroup()

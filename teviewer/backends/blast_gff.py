"""Write genome-coordinate GFF3 from BLAST tabular output (*_blast.txt)."""

from __future__ import annotations

from operator import itemgetter
from pathlib import Path

from teviewer.backends.blast_genome_plot import read_blast_table


def blast_gff_output_path(blast_txt: Path) -> Path:
    """``{query}_blast.txt`` → ``{query}_blast.gff`` (same pattern as manual m8 → gff)."""
    blast_txt = blast_txt.expanduser().resolve()
    name = blast_txt.name
    if name.endswith("_blast.txt"):
        return blast_txt.with_name(name[:-4] + ".gff")
    if name.endswith(".txt"):
        return blast_txt.with_suffix(".gff")
    return blast_txt.parent / f"{blast_txt.name}.gff"


def _normalize_strand(sstart: int, send: int, sstrand: str) -> tuple[int, int, str]:
    strand_raw = str(sstrand).strip().lower()
    if "minus" in strand_raw or strand_raw in {"-", "reverse", "rev"}:
        return min(sstart, send), max(sstart, send), "-"
    if "plus" in strand_raw or strand_raw in {"+", "forward", "fwd"}:
        return min(sstart, send), max(sstart, send), "+"
    if sstart < send:
        return sstart, send, "+"
    return send, sstart, "-"


def blast_hits_to_gff_rows(
    blast_txt: Path,
    *,
    minimum_bit_score: float = 0.0,
) -> list[list[str]]:
    """Convert BLAST hits to GFF rows (sorted by chromosome, start)."""
    df = read_blast_table(blast_txt)
    if df.empty:
        return []

    rows: list[list[str]] = []
    for _, hit in df.iterrows():
        bit_score = float(hit["bitscore"])
        if bit_score < minimum_bit_score:
            continue
        query = str(hit["qseqid"])
        chrom = str(hit["sseqid"])
        sstart = int(hit["sstart"])
        send = int(hit["send"])
        start, end, strand = _normalize_strand(sstart, send, str(hit.get("sstrand", "")))

        rows.append(
            [
                chrom,
                f"BLAST_{query}",
                query,
                str(start),
                str(end),
                str(bit_score),
                strand,
                ".",
                "repeat",
            ]
        )

    return sorted(rows, key=itemgetter(0, 3))


def write_blast_gff(
    blast_txt: Path,
    *,
    minimum_bit_score: float = 0.0,
    output_path: Path | None = None,
) -> Path:
    """Write GFF3 next to the BLAST table; coordinates match the reference genome."""
    blast_txt = blast_txt.expanduser().resolve()
    out = (output_path or blast_gff_output_path(blast_txt)).expanduser().resolve()
    gff_rows = blast_hits_to_gff_rows(blast_txt, minimum_bit_score=minimum_bit_score)

    lines = [
        "##gff-version 3",
        "",
        "##this gff works with the original genome fasta",
        "",
    ]
    for gff_list in gff_rows:
        lines.append("\t".join(gff_list))

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out

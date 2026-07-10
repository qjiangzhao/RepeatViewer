# TEviewer

Standalone **PySide6** desktop application for curating and evaluating transposable element (TE) consensus sequences.

TEviewer was split from [TEtrimmer](https://github.com/qjiangzhao/TEtrimmer). Curation logic is vendored from `TEtrimmerGUI` into `teviewer/backends/` so this repository runs **without** installing the full TEtrimmer package.

## Features

- Folder-based navigator (any input directory with FASTA files or TEtrimmer outputs)
- Multi-select sequences → run tools from the toolbar
- File panel: compact search bar, FASTA-only toggle, refresh (F5); green/blue row highlights after jobs
- In-app preview: FASTA, PDF reports, TEAid HTML (Plotly), Flexidot PNG
- Background jobs with progress dialog; keyboard shortcuts (Find, Delete, Refresh)

### Tools (toolbar)

| Tool | Description |
|------|-------------|
| **Blast** | BLASTN vs genome → hit table + extracted FASTA; optional genome GFF (`*_blast.gff`) |
| **TE genome map** | Plotly track view of TE hit density / identity along chromosomes (uses `*_blast.txt` after Blast; optional region in dialog) |
| **Extend** | Extend MSA ends (default 1000 bp left/right) → `*_ext_L1000_R1000.fa`; right-click for custom distances |
| **TEAid** | Interactive report HTML |
| **MSA clean** | Remove gappy columns; clean rows (divergence or gap); **clean row and column** = divergence trim then remove gappy columns → `{name}_clean.fa` |
| **Consensus** | Generate consensus from MSA |
| **Flexidot** | Dotplot via `pip install flexidot`; 1 file = self plot, 2 = paired, 3+ = multi-sequence |

## Install

```bash
git clone https://github.com/YOUR_USER/TEviewer.git
cd TEviewer
conda create -n teviewer python=3.10 -y
conda activate teviewer
pip install -e .
```

### External dependencies

- **Genome FASTA** — required for Blast / Extend / TEAid genome plots  
- **flexidot** — included in `requirements.txt` (`pip install flexidot`)  
- **mafft** / **clustalo** — for Align menu (MAFFT on macOS/Linux; Clustal Omega optional fallback)  
- Bundled **BLAST+** binaries are included under `teviewer/backends/blast/` (macOS/Linux/Windows). Enable “Use system BLAST” in settings to use your own install.

## Run

```bash
teviewer
# or
python TEviewer.py

python TEviewer.py --input-dir /path/to/TEtrimmer_for_proof_curation -g genome.fa
# short form: -i /path/to/folder -g genome.fa
```

CLI flags: `--input-dir` / `-i` (workspace opened on launch), `--genome` / `-g`. There is no separate output directory; each tool writes results next to the selected FASTA files.

## Project layout

```
TEviewer/
  TEviewer.py              # launcher
  teviewer/
    main_window.py         # UI
    project.py             # settings model
    backends/
      curation.py          # orchestrates all tools
      gui_functions.py     # BLAST, extend, flexidot, …
      teaid_plotter.py
      crop_end_*.py, remove_gap.py
      blast/               # bundled BLAST+ binaries
    views/settings_dialog.py
    widgets/html_preview.py
```

## Create GitHub repository

```bash
cd TEviewer
git init
git add .
git commit -m "Initial standalone TEviewer release with Flexidot"
gh repo create TEviewer --public --source=. --push
```

## Citation

If you use TEtrimmer/TEviewer in publications, cite TEtrimmer (Nature Communications, 2025) and mention TEviewer for manual curation.

## License

GPL-3.0-or-later (same as TEtrimmer). Backend code is derived from TEtrimmer / TEtrimmerGUI.

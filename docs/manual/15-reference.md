# Reference

## Output files

All outputs are written next to their input unless noted. `<name>` is the full
input file name with its extension, for example `reads.fa` →
`reads.fa_mafft.fa`. A repeated run adds `_2`, `_3`.

| Pattern | Made by | Contents |
|---------|---------|----------|
| `<name>.seqmap_RV.json` (hidden) | Every annotation | The annotations of `<name>` |
| `<name>.primers_RV.json` (hidden) | Primers tab | Primers kept with the sequence |
| `<name>_RV.gff3`, `.gtf`, `.bed` | Export | Annotations |
| `<name>_annotation.pdf`, `.svg`, `.png` | Export | Figure of the current view |
| `<name>_bn.txt` (`_bp`, `_bx`) | BLAST | Hit table |
| `<name>_bn.txt.fa` | BLAST | Hit regions cut out of the genome |
| `<name>_bn.gff` | BLAST | Hit positions (optional) |
| `<name>_obn.html`, `_obn.txt` | Online BLAST | NCBI report and hit table |
| `<name>_hmmer.txt` | HMMER | Hit table |
| `<name>_mafft.fa`, `<name>_muscle.fa` | Align, one file | Alignment |
| `<name>_cmafft.fa`, `<name>_cmuscle.fa` | Align, combined | Alignment of all selected files |
| `<name>_FastGA.paf`, `<name>_FastGA_vs_<ref>.paf`, `<first>_multi_FastGA.paf` | FastGA | Alignments for the dotplot |
| `<name>_gap.fa` | MSA Clean | Gappy columns removed |
| `<name>_rowdiv.fa` | MSA Clean | Divergent rows removed |
| `<name>_rowgap.fa` | MSA Clean | Gappy rows removed |
| `<name>_<threshold>_co.fa` | Consensus | Consensus sequence |
| `<name>_extr.fa` | Extract Sequences | Extracted records |
| `<name>_rc.fa` | Reverse Complement | Reverse complement |
| `<name>_orfs.fa` | ORF Prediction | ORFs |
| `<name>_translated.faa` | Translate | Protein translation |
| `<accession>.fa`, `.gb`, `.faa`, `.gp` | Download from NCBI | Downloaded records |
| `<name>_TEAid.html`, `<name>_pTEAid.html` | TE-Aid | Report (one genome, pangenome) |
| `<name>_self_dot.paf`, `<first>_multi_dot.paf` | Dotplot, built-in | Dotplot data |
| `<name>_flexidot.html`, `.gff`, `_legend.png` | Dotplot, Flexidot | Dotplot and its legend |
| `<name>_msa_plot.png`, `.pdf` | MSA plot | Alignment figure |
| `<name>_minimap.paf` or `.sam`, `<name>_minimap.rvmap` | Mapping | Alignment and contig view; optional `…_consensus.fa` / `…_mapped.fa` beside them |
| `<name>.sorted.bam`, `.bai`, `.crai` | Samtools Sort and Index, Mapping | Sorted alignment and its index |
| `<name>.bam`, `.sam`, `.cram` | Samtools Convert | Alignment in another format |
| `<name>_iqtree.treefile`, `<name>_iqtree_details/` | Tree | Tree; report, alignment, logs |
| `<tree>_traits.tsv` | Tree viewer | Trait table |
| `<tree>_distances_patristic.tsv`, `_pdistance.tsv` | Tree viewer | Distance matrices |
| `<genome>_repeat_quant_<date>/` | Repeat Quantify | Report and tables |
| `<name>_bn_den_plot.html`, `_multi_dens_plot.html` | TE density plot | Plot |
| `<name>_bn_div_plot.html`, `_multi_div_plot.html` | TE divergence plot | Plot |
| `<name>_RM_abund_plot.html`, `_multi_abund_plot.html` | TE abundance plot | Plot |
| `<name>_primers.html`, `<name>_primers_details/` | Primer Design | Report, primers, pairs, gel |
| `<name>_primer_map.html` | Map Primers | Binding sites and products |
| `<name>_PCR_<primers>.fa`, `…_details/` | In-silico PCR | Products; tables and history |
| `<name>.rvgel` | In-silico PCR, gel | Gel document |
| `<genome>_painting.html`, `_painting_details/` | Chromosome painting | Report, probes, order file |
| `<name>_<tool>_failed.log` | Tree, Mapping | Full log of a failed run |

## Troubleshooting

**A tool says the genome is not set.** Choose **File → Manage Database…**, add
the genome FASTA as **FASTA DNA** and click **Set as reference genome**. BLAST,
MSA Extend, TE-Aid, boundary prediction (Genome Cov) and the genome plots need
it.

**RepeatMasker, FastGA, HISAT2, FastME or FastTree is not found.** They are not
bundled. Install them into a conda environment (see
[Installation](02-installation.md#optional-external-programs)), enter that
environment in **File → Setting → General → External tools**, and click
**Test**. On Windows they must be in a WSL2 environment.

**BLAST or Repeat Quantify is very slow.** Check the word size: small values
are much more sensitive and much slower on repetitive genomes. For Repeat
Quantify, 11 is a good BLASTn default and 7 can make it hang. Also check
**Threads for the UI** in **File → Setting → General → Performance**: a high
value leaves few threads for the tools.

**Minimap2 misses hits inside a satellite array.** minimap2 ignores its most
frequent seeds. In Mapping → **Advanced Settings**, set repetitive seeds to
**Keep more**.

**A mapping gives differences at 100 % identity.** The reference has two
records with the same name. Give every record a unique name.

**A job cannot be stopped at once.** **Stop** in the status bar cancels the
running job; external programs may take a moment to end.

**An HTML report is blank in Preview.** Use **Open in browser** in the Preview
title bar.

**New outputs are not visible.** Press **F5** to refresh, and check that you are
looking at the folder of the input: outputs go there.

**A Repeat Quantify report says a name appears twice in the library.** Two
records share a name; their hits were merged into one row. Rename them.

**macOS refuses to open the app.** For an unsigned build, right-click the app,
choose **Open**, and confirm. This is needed only the first time.

**Reporting a bug.** **File → Setting → General → Diagnostics → Copy
diagnostics** copies the version, system and folder locations. Switch on
**Verbose logging**, repeat the problem, and attach the file from **Open log
file**. For failed Tree and Mapping runs, attach the `_failed.log` next to the
input.

## Citation

If RepeatViewer contributes to your work, please cite:

> Qian J, El-nagish A, Szatkowski S, Maiwald S, Sultana N, Costard D, Rudzinski A, Schmidt N, Heitkam T. 2026. RepeatViewer: a platform for explorative analysis of repetitive DNAs. bioRxiv,
> [https://doi.org/10.64898/2026.11.23.768287](https://doi.org/10.64898/2026.11.23.768287)

Please also cite **TEtrimmer** (*Nature
Communications*, 2025) where its methods are used. Tool reports (Tree, Mapping,
Primers) include a methods paragraph and the references of the programs they
ran; cite those programs too.

## Bundled programs

BLAST+, MAFFT, MUSCLE, minimap2 and IQ-TREE are distributed with RepeatViewer
under their own licences. The `NOTICE.md` file next to each program in
`repeatviewer/backends/` gives its licence and source.

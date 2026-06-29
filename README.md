# Vizabelle

Vizabelle is an experimental proof visualization tool for TPTP/TSTP/THF proofs, especially ATP proofs produced from Isabelle problems by Sledgehammer.

The current implementation parses proof files through a small C helper linked against JJParser, then uses Python to build a proof DAG and render an offline HTML visualization with a Graphviz overview and per-step proof pages.

## Requirements

- Python 3.11 or newer should work; the current code uses only the Python standard library.
- A C compiler, such as `gcc`.
- `make`.
- Graphviz, with `dot` available on `PATH`.
- TPTP4X, with `tptp4X` available on `PATH`, for pretty-printing formulas on proof step pages.
- JJParser source tree. Clone or download JJParser separately. By default the Makefile expects it at:

```text
/home/yan/repos/github/JJParser
```

If JJParser is somewhere else, pass `JJPARSER=/path/to/JJParser` to `make`.
- Isabelle sources are not included in this repository. Source-aware headings and excerpts require a separate Isabelle checkout, with `--isabelle-src /path/to/Isabelle/src`. Without it, proof visualization still works, but source theorem labels and excerpts may be unavailable.

## Build

From the repository root:

```bash
make jjparser
make
```

This builds the helper executable:

```text
build/vizabelle-jjparser-json
```

To use a non-default JJParser checkout:

```bash
make jjparser JJPARSER=/path/to/JJParser
make JJPARSER=/path/to/JJParser
```

## Run

Generate a complete offline HTML visualization from the bundled example proof:

```bash
python -m vizabelle.graph examples/proofs/prob_00771_023712.p.gz --html -o out
```

Open the generated index page in a browser:

```text
out/index.html
```

The index page is split left-right: the proof overview is on the left, and proof details are shown on the right. The default proof summary lists conjectures with their formulas and step links, axiom labels, and a link to the final contradiction. Selecting an overview node opens that proof step. Overview nodes are unlabeled clickable shapes with TPTP names in tooltips. The `Flat` control compacts nodes with one parent and one child; `Full` restores the complete derivation.

When a proof starts with an `%%% INSTANCE (benchmark, problem)` header, the summary can resolve the encoded theory and source line under a separately downloaded Isabelle source tree. It shows the enclosing lemma declaration and a proof excerpt consisting of the encoded line plus the five preceding source lines. Use `--isabelle-src /path/to/Isabelle/src`.

Theory files are resolved from the session declarations in Isabelle `ROOT` files. Vizabelle builds an in-memory index of `.thy` files and selects the unique theory beneath the declared session directory, including theories in nested directories such as `Doc/Tutorial/Protocol`.

Isabelle source excerpts use the checkout's `etc/symbols` table for Unicode rendering and lightweight lexical highlighting for Isar commands, keywords, strings, comments, variables, numbers, and operators. Isabelle subscript, superscript, and bold control symbols are rendered as HTML.

HTML generation also writes `proof-flat.dot` and `proof-flat.svg` beside the complete `proof.dot` and `proof.svg` overview files.

Generated HTML references shared static assets under `out/data/`. The generator symlinks this directory to `vizabelle/data/` when possible, and copies it as a fallback.

Generate a proof library from a text file containing one proof path per line:

```bash
find examples/proofs -name '*.p.gz' | sort > proofs.txt
python -m vizabelle.library proofs.txt
```

By default this writes `docs/index.html`, shared assets under `docs/data/`, and one
proof directory per Isabelle source location, for example `docs/Message.thy-771/`.
The library page lists all generated proofs and each proof page has an active menu
button that opens the same proof list.

Use another output directory:

```bash
python -m vizabelle.library proofs.txt -o out/library
```

Open the generated library index:

```text
docs/index.html
```

Generate only an overview SVG:

```bash
python -m vizabelle.graph examples/proofs/prob_00771_023712.p.gz -o out/proof.svg
```

Open the generated file in a browser or SVG viewer:

```text
out/proof.svg
```

Generate Graphviz DOT instead:

```bash
python -m vizabelle.graph examples/proofs/prob_00771_023712.p.gz -o out/proof.dot
```

Include type declarations in the graph:

```bash
python -m vizabelle.graph examples/proofs/prob_00771_023712.p.gz --html --include-types -o out
```

Use a non-default `tptp4X` executable:

```bash
python -m vizabelle.graph examples/proofs/prob_00771_023712.p.gz --html -o out --tptp4x-command /path/to/tptp4X
```

Parse a proof and inspect the JSON records directly:

```bash
python -m vizabelle.parser examples/proofs/prob_00771_023712.p.gz --pretty
```

## Input Files

Vizabelle accepts plain `.p` files and gzip-compressed `.p.gz` files. When an SZS proof block is present, the Python wrapper extracts that block before passing formulas to the JJParser helper.

## Current Limitations

- Formula pretty-printing is still basic outside the proof-state clause record display.

## Clean

Remove the local build output:

```bash
make clean
```

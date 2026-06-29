from __future__ import annotations

import argparse
import html
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .graph import (
    DEFAULT_ISABELLE_SRC,
    ProofGraph,
    html_page,
    install_data_dir,
    isabelle_statement_from_proof,
    topbar_html,
    write_html_site,
)
from .parser import parse_file


@dataclass(frozen=True)
class LibraryProof:
    proof_path: Path
    label: str
    slug: str


def read_proof_list(path: Path) -> list[Path]:
    proofs = []
    base_dir = path.parent
    for line in path.read_text().splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        proof_path = Path(text)
        proofs.append(proof_path if proof_path.is_absolute() else base_dir / proof_path)
    return proofs


def proof_fallback_label(path: Path) -> str:
    name = path.name
    for suffix in (".p.gz", ".p"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def proof_label(path: Path, isabelle_src: Path) -> str:
    statement = isabelle_statement_from_proof(path, isabelle_src)
    if statement:
        return f"{statement.source_path.name}:{statement.source_line}"
    return proof_fallback_label(path)


def slugify_label(label: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", label).strip("-")
    return slug or "proof"


def library_proofs(paths: list[Path], isabelle_src: Path) -> list[LibraryProof]:
    used: dict[str, int] = {}
    proofs = []
    for path in paths:
        label = proof_label(path, isabelle_src)
        base_slug = slugify_label(label)
        count = used.get(base_slug, 0)
        used[base_slug] = count + 1
        slug = base_slug if count == 0 else f"{base_slug}-{count + 1}"
        proofs.append(LibraryProof(path, label, slug))
    return proofs


def relative_entries(proofs: list[LibraryProof], base_dir: Path, output_dir: Path) -> list[dict[str, str]]:
    entries = []
    for proof in proofs:
        href = Path(os.path.relpath(output_dir / proof.slug / "index.html", base_dir)).as_posix()
        entries.append({"label": proof.label, "href": href})
    return entries


def library_index_page(
    proofs: list[LibraryProof],
    stylesheet_href: str = "data/style.css",
    script_src: str = "data/app.js",
) -> str:
    entries = [{"label": proof.label, "href": f"{proof.slug}/index.html"} for proof in proofs]
    links = "\n".join(
        (
            f'<a class="library-proof-link" href="{html.escape(proof.slug)}/index.html">'
            f"{html.escape(proof.label)}</a>"
        )
        for proof in proofs
    )
    body = f"""
{topbar_html(entries)}
<main class="library-page">
  <p class="kicker">Proof Library</p>
  <h1>Proof Library</h1>
  <div class="library-list">
    {links if links else '<span class="empty">No proofs</span>'}
  </div>
</main>
"""
    return html_page(
        "Proof Library",
        body,
        (
            f'<link rel="stylesheet" href="{html.escape(stylesheet_href)}">\n'
            f'<script src="{html.escape(script_src)}" defer></script>'
        ),
    )


def write_library(
    proof_list: Path,
    output_dir: Path = Path("docs"),
    include_types: bool = False,
    dot_command: str = "dot",
    tptp4x_command: str = "tptp4X",
    isabelle_src: Path = DEFAULT_ISABELLE_SRC,
) -> None:
    proof_paths = read_proof_list(proof_list)
    proofs = library_proofs(proof_paths, isabelle_src)
    output_dir.mkdir(parents=True, exist_ok=True)
    install_data_dir(output_dir)

    for proof in proofs:
        proof_output_dir = output_dir / proof.slug
        statement = isabelle_statement_from_proof(proof.proof_path, isabelle_src)
        entries = relative_entries(proofs, proof_output_dir, output_dir)
        current_href = Path(os.path.relpath(proof_output_dir / "index.html", proof_output_dir)).as_posix()
        write_html_site(
            ProofGraph(parse_file(proof.proof_path)),
            proof_output_dir,
            include_types=include_types,
            dot_command=dot_command,
            tptp4x_command=tptp4x_command,
            asset_dir=output_dir,
            isabelle_statement=statement,
            library_entries=entries,
            current_library_href=current_href,
        )

    (output_dir / "index.html").write_text(
        library_index_page(proofs, "data/style.css", "data/app.js")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a static Vizabelle proof library.")
    parser.add_argument("proof_list", type=Path, help="Text file with one proof path per line")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("docs"),
        help="Output directory for the proof library. Defaults to docs/.",
    )
    parser.add_argument("--include-types", action="store_true", help="Include type declarations in proof graphs")
    parser.add_argument("--dot-command", default="dot", help="Graphviz dot executable")
    parser.add_argument("--tptp4x-command", default="tptp4X", help="tptp4X executable")
    parser.add_argument(
        "--isabelle-src",
        type=Path,
        default=DEFAULT_ISABELLE_SRC,
        help="Isabelle src directory used to resolve INSTANCE source locations",
    )
    args = parser.parse_args(argv)

    write_library(
        args.proof_list,
        args.output,
        args.include_types,
        args.dot_command,
        args.tptp4x_command,
        args.isabelle_src,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from pathlib import Path

from vizabelle.library import (
    library_index_page,
    library_proofs,
    read_proof_list,
    slugify_label,
)


def test_slugify_label_keeps_theory_and_line_readable() -> None:
    assert slugify_label("Message.thy:771") == "Message.thy-771"


def test_read_proof_list_resolves_relative_paths(tmp_path: Path) -> None:
    proof_list = tmp_path / "proofs.txt"
    proof_list.write_text("\n# comment\nexamples/proof.p.gz\n")

    assert read_proof_list(proof_list) == [tmp_path / "examples" / "proof.p.gz"]


def test_library_proofs_use_isabelle_source_labels() -> None:
    proof = Path(__file__).resolve().parents[1] / "examples" / "proofs" / "prob_00771_023712.p.gz"

    proofs = library_proofs([proof], Path(__file__).resolve().parents[1] / "Isabelle2025-2" / "src")

    assert proofs[0].label == "Message.thy:771"
    assert proofs[0].slug == "Message.thy-771"


def test_library_index_lists_proofs_and_menu() -> None:
    proof = type("Proof", (), {"label": "Message.thy:771", "slug": "Message.thy-771"})()

    page = library_index_page([proof])

    assert '<a class="library-proof-link" href="Message.thy-771/index.html">Message.thy:771</a>' in page
    assert 'data-menu-toggle aria-expanded="false"' in page
    assert '<a href="Message.thy-771/index.html">Message.thy:771</a>' in page

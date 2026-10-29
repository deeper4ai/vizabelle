from pathlib import Path

from vizabelle.isabelle import highlight_isabelle, load_symbols, render_symbols
from vizabelle.graph import (
    DEFAULT_ISABELLE_SRC,
    ProofGraph,
    isabelle_session_directories,
    isabelle_statement_from_proof,
    index_page,
    proof_page,
    resolve_isabelle_theory,
)


SYMBOLS = Path(__file__).resolve().parents[1] / "Isabelle2025-2" / "etc" / "symbols"


def test_symbol_table_and_decode() -> None:
    symbols = load_symbols(SYMBOLS)
    assert symbols["\\<Longrightarrow>"].decoded == "⟹"
    assert symbols["\\<turnstile>"].decoded == "⊢"
    assert render_symbols("A \\<Longrightarrow> \\<beta>", SYMBOLS) == "A ⟹ β"


def test_control_symbols_render_as_html() -> None:
    assert render_symbols("A\\<^sub>1", SYMBOLS) == "A<sub>1</sub>"
    assert render_symbols("x\\<^bsup>12\\<^esup>", SYMBOLS) == "x<sup>12</sup>"
    assert render_symbols("<unsafe>", SYMBOLS) == "&lt;unsafe&gt;"


def test_lexical_highlighting() -> None:
    source = 'lemma example: "A \\<Longrightarrow> B"\n  by (rule foo)'
    rendered = highlight_isabelle(source, SYMBOLS)
    assert '<span class="isar-command">lemma</span>' in rendered
    assert '<span class="isar-string">"A ⟹ B"</span>' in rendered
    assert '<span class="isar-command">by</span>' in rendered
    assert '<span class="isar-operator">:</span>' in rendered


def test_schematic_variables_stop_before_binder_dot() -> None:
    rendered = highlight_isabelle("\\<forall>x\\<in>?A. ?x.1 \\<le> ?'b.2", SYMBOLS)
    assert '<span class="isar-variable">?A</span><span class="isar-operator">.</span>' in rendered
    assert '<span class="isar-variable">?x.1</span>' in rendered
    assert '<span class="isar-type-variable">?\'b.2</span>' in rendered


def test_summary_excerpts_have_source_line_numbers() -> None:
    proof = Path(__file__).resolve().parents[1] / "examples" / "proofs" / "prob_00123_003167.p.gz"
    statement = isabelle_statement_from_proof(proof)
    assert statement is not None
    assert statement.lemma_start_line == 90
    assert statement.proof_start_line == 118

    page = proof_page(ProofGraph([]), isabelle_statement=statement)
    assert "<title>Proof Summary of StrongNorm.thy:123</title>" in page
    assert "<h1>Proof Summary of StrongNorm.thy:123</h1>" in page
    assert '<pre class="isabelle-line-numbers" aria-hidden="true">90\n91\n92\n93</pre>' in page
    assert '<div class="isabelle-source-block"><pre' in page
    assert '<pre class="isabelle-line-numbers" aria-hidden="true">118\n119\n120\n121\n122\n123</pre>' in page
    assert '<div class="isabelle-source-block highlight-last-line"><pre' in page


def test_overview_title_has_source_location() -> None:
    proof = Path(__file__).resolve().parents[1] / "examples" / "proofs" / "prob_00771_023712.p.gz"
    statement = isabelle_statement_from_proof(proof)
    assert statement is not None

    page = index_page(ProofGraph([]), "<svg></svg>", "<svg></svg>", isabelle_statement=statement)

    assert "<title>Proof Overview of Message.thy:771</title>" in page
    assert "<h1>Proof Overview of Message.thy:771</h1>" in page


def test_session_directories_resolve_regular_and_tutorial_theories() -> None:
    sessions = isabelle_session_directories(DEFAULT_ISABELLE_SRC)
    assert sessions["HOL-Proofs-Lambda"][0].as_posix().endswith("/src/HOL/Proofs/Lambda")
    assert sessions["Tutorial"][0].as_posix().endswith("/src/Doc/Tutorial")
    assert resolve_isabelle_theory("HOL-Proofs-Lambda", "StrongNorm").as_posix().endswith(
        "/src/HOL/Proofs/Lambda/StrongNorm.thy"
    )
    assert resolve_isabelle_theory("Tutorial", "Message").as_posix().endswith(
        "/src/Doc/Tutorial/Protocol/Message.thy"
    )


def test_all_example_proofs_resolve_isabelle_sources() -> None:
    proofs_dir = Path(__file__).resolve().parents[1] / "examples" / "proofs"
    expected = {
        "prob_00123_003167.p.gz": ("HOL/Proofs/Lambda/StrongNorm.thy", 123),
        "prob_00138_003649.p.gz": ("Doc/Tutorial/Protocol/Message.thy", 138),
        "prob_00161_004528.p.gz": ("HOL/Proofs/Lambda/Lambda.thy", 161),
        "prob_00723_022817.p.gz": ("HOL/Library/Float.thy", 723),
        "prob_00771_023712.p.gz": ("Doc/Tutorial/Protocol/Message.thy", 771),
        "prob_00955_041225.p.gz": ("HOL/Cardinals/Ordinal_Arithmetic.thy", 955),
        "prob_01235_053796.p.gz": ("HOL/Cardinals/Ordinal_Arithmetic.thy", 1235),
        "prob_04159_148409.p.gz": ("HOL/Transcendental.thy", 4159),
    }
    for proof_name, (source_suffix, source_line) in expected.items():
        statement = isabelle_statement_from_proof(proofs_dir / proof_name)
        assert statement is not None
        assert statement.source_path.as_posix().endswith(source_suffix)
        assert statement.source_line == source_line

    tutorial = isabelle_statement_from_proof(proofs_dir / "prob_00138_003649.p.gz")
    assert tutorial is not None
    assert tutorial.lemma_text == 'lemma keysFor_empty [simp]: "keysFor {} = {}"'
    assert tutorial.proof_start_line == 137
    assert tutorial.proof_text == (
        'lemma keysFor_empty [simp]: "keysFor {} = {}"\n'
        'by (unfold keysFor_def, blast)'
    )
    tutorial_page = proof_page(ProofGraph([]), isabelle_statement=tutorial)
    assert (
        '<div class="isabelle-source-block highlight-last-line">'
        '<pre class="isabelle-line-numbers" aria-hidden="true">137\n138</pre>'
        in tutorial_page
    )

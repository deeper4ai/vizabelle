from vizabelle.clause import annotate_clauses, clause_record_label
from vizabelle.graph import ProofGraph, step_dot


def term(symbol: str, *args: dict) -> dict:
    return {"kind": "term", "type": "function", "symbol": symbol, "args": list(args)}


def atom(symbol: str, *args: dict) -> dict:
    return {"kind": "atom", "atom": term(symbol, *args)}


def binary(connective: str, lhs: dict, rhs: dict) -> dict:
    return {"kind": "binary", "connective": connective, "lhs": lhs, "rhs": rhs}


def neg(body: dict) -> dict:
    return {"kind": "unary", "connective": "~", "body": body}


def forall(variable: str, body: dict) -> dict:
    return {
        "kind": "quantified",
        "quantifier": "!",
        "variable": term(variable),
        "body": body,
    }


def test_clause_detection_strips_universal_prefix_and_flattens_literals() -> None:
    record = {
        "formula_ast": forall(
            "X",
            binary(
                "|",
                neg(atom("p", term("X"))),
                binary("|", atom("q", term("a")), atom("r", term("b"))),
            ),
        )
    }

    annotate_clauses([record])

    assert record["is_clause"] is True
    assert [literal["negated"] for literal in record["clause_literals"]] == [True, False, False]
    assert clause_record_label(record) == "{{⊖|{p|X}}|{⊕|{q|a}}|{⊕|{r|b}}}"


def test_clause_record_flattens_thf_application() -> None:
    app = term("@", term("@", term("@", term("f"), term("a")), term("b")), term("c"))
    record = {"formula_ast": atom("holds", app)}

    annotate_clauses([record])

    assert record["is_clause"] is True
    assert clause_record_label(record) == "{{⊕|{holds|{f|a|b|c}}}}"


def test_clause_record_flattens_thf_formula_application() -> None:
    app = binary("@", binary("@", atom("p"), atom("a")), atom("b"))
    record = {"formula_ast": forall("X", binary("|", app, neg(binary("@", atom("q"), atom("X")))))}

    annotate_clauses([record])

    assert record["is_clause"] is True
    assert clause_record_label(record) == "{{⊕|{p|a|b}}|{⊖|{q|X}}}"


def test_non_clause_formula_is_marked_false() -> None:
    record = {"formula_ast": binary("&", atom("p"), atom("q"))}

    annotate_clauses([record])

    assert record["is_clause"] is False
    assert "clause_literals" not in record


def test_step_dot_uses_record_label_for_clause_nodes_only() -> None:
    clause = {
        "name": "c1",
        "role": "plain",
        "formula": "p(a)",
        "formula_ast": atom("p", term("a")),
        "parents": [],
    }
    non_clause = {
        "name": "c2",
        "role": "plain",
        "formula": "p(a) & q(a)",
        "formula_ast": binary("&", atom("p", term("a")), atom("q", term("a"))),
        "parents": ["c1"],
    }
    records = [clause, non_clause]
    annotate_clauses(records)

    dot = step_dot(ProofGraph(records), non_clause)

    assert dot.count('"c1" [') == 1
    assert '"c1" [label="{{⊕|{p|a}}}"' in dot
    assert 'shape="Mrecord"' in dot
    assert '"c2" [label="c2"' in dot

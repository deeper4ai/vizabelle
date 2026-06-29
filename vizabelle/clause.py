from __future__ import annotations

from typing import Any


Ast = dict[str, Any]


def annotate_clauses(records: list[dict]) -> None:
    for record in records:
        clause = clause_from_ast(record.get("formula_ast"))
        record["is_clause"] = clause is not None
        if clause is not None:
            record["clause_literals"] = clause


def clause_from_ast(ast: Ast | None) -> list[dict] | None:
    if not ast:
        return None

    body = ast
    while body.get("kind") == "quantified" and body.get("quantifier") == "!":
        body = body.get("body")
        if not isinstance(body, dict):
            return None

    literals = flatten_disjunction(body)
    if not literals:
        return None
    clause_literals = [literal_from_ast(literal) for literal in literals]
    if any(literal is None for literal in clause_literals):
        return None
    return [literal for literal in clause_literals if literal is not None]


def flatten_disjunction(ast: Ast) -> list[Ast]:
    if ast.get("kind") == "binary" and ast.get("connective") == "|":
        lhs = ast.get("lhs")
        rhs = ast.get("rhs")
        if isinstance(lhs, dict) and isinstance(rhs, dict):
            return flatten_disjunction(lhs) + flatten_disjunction(rhs)
    return [ast]


def literal_from_ast(ast: Ast) -> dict | None:
    if ast.get("kind") == "unary" and ast.get("connective") == "~":
        body = ast.get("body")
        if isinstance(body, dict) and is_atomic_formula(body):
            return {"negated": True, "formula": body}
        return None
    if is_atomic_formula(ast):
        return {"negated": False, "formula": ast}
    return None


def is_atomic_formula(ast: Ast) -> bool:
    if ast.get("kind") in {"atom", "applied_connective"}:
        return True
    return ast.get("kind") == "binary" and ast.get("connective") in {"=", "!=", "@"}


def clause_record_label(record: dict, max_literals: int = 12, max_text_length: int = 600) -> str | None:
    literals = record.get("clause_literals")
    if not record.get("is_clause") or not isinstance(literals, list) or not literals:
        return None
    if len(literals) > max_literals:
        return None

    fields = [literal_record(literal) for literal in literals]
    label = "{" + "|".join(fields) + "}"
    if len(label) > max_text_length:
        return None
    return label


def literal_record(literal: dict) -> str:
    formula = literal.get("formula")
    body = formula_record(formula) if isinstance(formula, dict) else "?"
    if literal.get("negated"):
        return "{⊖|" + body + "}"
    return "{⊕|" + body + "}"


def formula_record(ast: Ast) -> str:
    if ast.get("kind") in {"atom", "applied_connective"}:
        atom = ast.get("atom")
        return term_record(atom) if isinstance(atom, dict) else "?"
    if ast.get("kind") == "binary" and ast.get("connective") == "@":
        head, args = flatten_formula_application(ast)
        return "{" + "|".join([formula_record(head), *(formula_record(arg) for arg in args)]) + "}"
    if ast.get("kind") == "binary" and ast.get("connective") in {"=", "!="}:
        lhs = ast.get("lhs")
        rhs = ast.get("rhs")
        connective = ast.get("connective") or "="
        return "{" + "|".join(
            [
                formula_or_term_record(lhs),
                record_escape(connective),
                formula_or_term_record(rhs),
            ]
        ) + "}"
    return record_escape("?")


def formula_or_term_record(ast: Any) -> str:
    if not isinstance(ast, dict):
        return record_escape("?")
    if ast.get("kind") == "term":
        return term_record(ast)
    return formula_record(ast)


def term_record(term: Ast) -> str:
    head, args = flatten_application(term)
    if args:
        return "{" + "|".join([term_record(head), *(term_record(arg) for arg in args)]) + "}"

    symbol = str(term.get("symbol") or "?")
    args = [arg for arg in term.get("args", []) if isinstance(arg, dict)]
    if args:
        return "{" + "|".join([record_escape(symbol), *(term_record(arg) for arg in args)]) + "}"
    return record_escape(symbol)


def flatten_formula_application(ast: Ast) -> tuple[Ast, list[Ast]]:
    if ast.get("kind") != "binary" or ast.get("connective") != "@":
        return ast, []

    lhs = ast.get("lhs")
    rhs = ast.get("rhs")
    if not isinstance(lhs, dict) or not isinstance(rhs, dict):
        return ast, []

    head, args = flatten_formula_application(lhs)
    return head, args + [rhs]


def flatten_application(term: Ast) -> tuple[Ast, list[Ast]]:
    if term.get("kind") != "term" or term.get("symbol") != "@":
        return term, []

    args = [arg for arg in term.get("args", []) if isinstance(arg, dict)]
    if len(args) != 2:
        return term, []

    head, head_args = flatten_application(args[0])
    return head, head_args + [args[1]]


def record_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("|", "\\|")
        .replace("<", "\\<")
        .replace(">", "\\>")
    )

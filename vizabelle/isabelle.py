from __future__ import annotations

import html
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


SYMBOL_DECL_RE = re.compile(r"^(\\<[^>]+>)\s+(.*)$")
CODE_RE = re.compile(r"(?:^|\s)code:\s*(0x[0-9A-Fa-f]+)")
GROUP_RE = re.compile(r"(?:^|\s)group:\s*([^\s]+)")


@dataclass(frozen=True)
class SymbolSpec:
    decoded: str | None
    groups: frozenset[str]


@lru_cache(maxsize=None)
def load_symbols(path: Path) -> dict[str, SymbolSpec]:
    symbols: dict[str, SymbolSpec] = {}
    for line in path.read_text(errors="replace").splitlines():
        declaration = SYMBOL_DECL_RE.match(line)
        if not declaration:
            continue
        symbol, properties = declaration.groups()
        code = CODE_RE.search(properties)
        symbols[symbol] = SymbolSpec(
            decoded=chr(int(code.group(1), 16)) if code else None,
            groups=frozenset(GROUP_RE.findall(properties)),
        )
    return symbols


def _source_symbol(text: str, start: int) -> tuple[str, int]:
    if text.startswith("\\<", start):
        stop = text.find(">", start + 2)
        if stop >= 0:
            return text[start : stop + 1], stop + 1
    return text[start], start + 1


SINGLE_CONTROLS = {
    "\\<^sub>": "sub",
    "\\<^sup>": "sup",
    "\\<^bold>": "b",
}
BLOCK_CONTROLS = {
    "\\<^bsub>": "sub",
    "\\<^bsup>": "sup",
}
BLOCK_ENDS = {
    "\\<^esub>": "sub",
    "\\<^esup>": "sup",
}


def render_symbols(text: str, symbols_path: Path) -> str:
    """Decode Isabelle symbols and render Isabelle display controls as safe HTML."""
    symbols = load_symbols(symbols_path)
    result: list[str] = []
    blocks: list[str] = []
    pending: str | None = None
    index = 0

    while index < len(text):
        source, index = _source_symbol(text, index)
        if source in SINGLE_CONTROLS:
            pending = SINGLE_CONTROLS[source]
            continue
        if source in BLOCK_CONTROLS:
            tag = BLOCK_CONTROLS[source]
            result.append(f"<{tag}>")
            blocks.append(tag)
            continue
        if source in BLOCK_ENDS:
            tag = BLOCK_ENDS[source]
            if blocks and blocks[-1] == tag:
                blocks.pop()
                result.append(f"</{tag}>")
            continue

        spec = symbols.get(source)
        decoded = spec.decoded if spec and spec.decoded is not None else source
        escaped = html.escape(decoded, quote=False)
        if pending and not decoded.isspace():
            result.append(f"<{pending}>{escaped}</{pending}>")
            pending = None
        else:
            result.append(escaped)

    while blocks:
        result.append(f"</{blocks.pop()}>")
    return "".join(result)


COMMANDS = frozenset(
    {
        "abbreviation", "also", "apply", "assume", "begin", "by", "case",
        "class", "corollary", "datatype", "definition", "done", "end", "finally",
        "fix", "from", "fun", "function", "have", "hence", "include", "inductive",
        "instance", "instantiation", "interpretation", "lemma", "let", "locale",
        "moreover", "next", "note", "obtain", "oops", "primrec", "proof",
        "proposition", "qed", "show", "sorry", "sublocale", "theorem", "then",
        "thus", "ultimately", "unfolding", "using", "with", "write",
    }
)

KEYWORDS = frozenset(
    {
        "and", "assumes", "constrains", "defines", "fixes", "for", "if", "imports",
        "in", "includes", "is", "keywords", "notes", "obtains", "shows", "structure",
        "where",
    }
)

WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_'.]*")
# a dot belongs to a variable only before its index (?x.1): "\<forall>x\<in>?A. ..."
SCHEMATIC_RE = re.compile(r"\?[A-Za-z_][A-Za-z0-9_']*(?:\.[0-9]+)?")
TYPE_RE = re.compile(r"\??'[A-Za-z_][A-Za-z0-9_']*(?:\.[0-9]+)?")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
ASCII_OPERATOR_RE = re.compile(r"[!#$%&*+\-./:<=>?@^|~]+")
OPERATOR_GROUPS = frozenset({"arrow", "operator", "punctuation", "relation"})


def _delimited_stop(text: str, start: int, delimiter: str) -> int:
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            if text.startswith("\\<", index):
                _, index = _source_symbol(text, index)
            else:
                index += 2
        elif text[index] == delimiter:
            return index + 1
        else:
            index += 1
    return len(text)


def _comment_stop(text: str, start: int) -> int:
    depth = 1
    index = start + 2
    while index < len(text) and depth:
        if text.startswith("(*", index):
            depth += 1
            index += 2
        elif text.startswith("*)", index):
            depth -= 1
            index += 2
        else:
            index += 1
    return index


def _cartouche_stop(text: str, start: int) -> int:
    depth = 1
    index = start + len("\\<open>")
    while index < len(text) and depth:
        if text.startswith("\\<open>", index):
            depth += 1
            index += len("\\<open>")
        elif text.startswith("\\<close>", index):
            depth -= 1
            index += len("\\<close>")
        else:
            _, index = _source_symbol(text, index)
    return index


def _span(class_name: str, source: str, symbols_path: Path) -> str:
    rendered = render_symbols(source, symbols_path)
    return f'<span class="isar-{class_name}">{rendered}</span>'


def highlight_isabelle(text: str, symbols_path: Path) -> str:
    """Apply lightweight lexical Isar highlighting and Isabelle symbol rendering."""
    symbols = load_symbols(symbols_path)
    result: list[str] = []
    index = 0

    while index < len(text):
        if text[index].isspace():
            stop = index + 1
            while stop < len(text) and text[stop].isspace():
                stop += 1
            result.append(html.escape(text[index:stop], quote=False))
            index = stop
            continue
        if text.startswith("(*", index):
            stop = _comment_stop(text, index)
            result.append(_span("comment", text[index:stop], symbols_path))
            index = stop
            continue
        if text.startswith("\\<open>", index):
            stop = _cartouche_stop(text, index)
            result.append(_span("cartouche", text[index:stop], symbols_path))
            index = stop
            continue
        if text[index] in {'"', "`"}:
            stop = _delimited_stop(text, index, text[index])
            class_name = "string" if text[index] == '"' else "alt-string"
            result.append(_span(class_name, text[index:stop], symbols_path))
            index = stop
            continue

        match = SCHEMATIC_RE.match(text, index)
        if match:
            result.append(_span("variable", match.group(), symbols_path))
            index = match.end()
            continue
        match = TYPE_RE.match(text, index)
        if match:
            result.append(_span("type-variable", match.group(), symbols_path))
            index = match.end()
            continue
        match = NUMBER_RE.match(text, index)
        if match:
            result.append(_span("number", match.group(), symbols_path))
            index = match.end()
            continue
        match = WORD_RE.match(text, index)
        if match:
            word = match.group()
            if word in COMMANDS:
                result.append(_span("command", word, symbols_path))
            elif word in KEYWORDS:
                result.append(_span("keyword", word, symbols_path))
            else:
                result.append(render_symbols(word, symbols_path))
            index = match.end()
            continue
        match = ASCII_OPERATOR_RE.match(text, index)
        if match:
            result.append(_span("operator", match.group(), symbols_path))
            index = match.end()
            continue
        if text.startswith("\\<", index):
            source, stop = _source_symbol(text, index)
            spec = symbols.get(source)
            class_name = "operator" if spec and spec.groups & OPERATOR_GROUPS else "symbol"
            result.append(_span(class_name, source, symbols_path))
            index = stop
            continue

        result.append(html.escape(text[index], quote=False))
        index += 1

    return "".join(result)

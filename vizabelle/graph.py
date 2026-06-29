from __future__ import annotations

import argparse
import html
import os
import shutil
import re
import subprocess
import textwrap
import urllib.parse
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .clause import clause_record_label
from .isabelle import highlight_isabelle
from .parser import parse_file, read_instance


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "vizabelle" / "data"
DEFAULT_ISABELLE_SRC = REPO_ROOT / "Isabelle2025-2" / "src"
DEFAULT_ISABELLE_SYMBOLS = REPO_ROOT / "Isabelle2025-2" / "etc" / "symbols"
SESSION_DECL_RE = re.compile(
    r'^\s*session\s+(?:"([^"]+)"|([^\s(=]+))'
    r'(?:\s+\([^\n)]*\))?'
    r'(?:\s+in\s+(?:"([^"]+)"|([^\s=]+)))?\s*=',
    re.MULTILINE,
)


@dataclass(frozen=True)
class IsabelleStatement:
    benchmark: str
    problem: str
    source_path: Path
    source_line: int
    lemma_text: str
    proof_text: str
    lemma_start_line: int = 1
    proof_start_line: int = 1
    symbols_path: Path = DEFAULT_ISABELLE_SYMBOLS


@dataclass
class ProofGraph:
    records: list[dict]
    by_name: dict[str, dict] = field(init=False)
    children: dict[str, list[str]] = field(init=False)
    input_leaves: dict[str, list[str]] = field(init=False)

    def __post_init__(self) -> None:
        self.by_name = {record["name"]: record for record in self.records}
        self.children = {name: [] for name in self.by_name}
        for record in self.records:
            child = record["name"]
            for parent in record.get("parents", []):
                if parent in self.children:
                    self.children[parent].append(child)
        self.input_leaves = self.compute_input_leaves()

    @property
    def formula_records(self) -> list[dict]:
        return [record for record in self.records if record.get("role") != "type"]

    @property
    def final_name(self) -> str | None:
        false_nodes = [record["name"] for record in self.formula_records if record.get("formula") == "$false"]
        if false_nodes:
            return false_nodes[-1]

        roots = [
            record["name"]
            for record in self.formula_records
            if not self.children.get(record["name"])
        ]
        return roots[-1] if roots else None

    def compute_input_leaves(self) -> dict[str, list[str]]:
        memo: dict[str, set[str]] = {}
        visiting: set[str] = set()

        def leaves_for(name: str) -> set[str]:
            if name in memo:
                return memo[name]
            if name in visiting:
                return set()

            visiting.add(name)
            record = self.by_name[name]
            parents = [parent for parent in record.get("parents", []) if parent in self.by_name]
            if not parents:
                leaves = {name}
            else:
                leaves = set()
                for parent in parents:
                    leaves.update(leaves_for(parent))
            visiting.remove(name)
            memo[name] = leaves
            return leaves

        for record in self.records:
            leaves_for(record["name"])

        return {
            record["name"]: [
                leaf_record["name"]
                for leaf_record in self.records
                if leaf_record["name"] in memo[record["name"]]
            ]
            for record in self.records
        }


ROLE_COLORS = {
    "axiom": "#1f4e79",
    "conjecture": "#2e7d32",
    "negated_conjecture": "#8b1e3f",
    "derived_from_negated_conjecture": "#ffec99",
    "plain": "#8ecae6",
    "type": "#d9d9d9",
}


def dot_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def dot_id(name: str) -> str:
    return dot_quote(name)


def node_label(record: dict) -> str:
    return record["name"]


def step_filename(name: str) -> str:
    return urllib.parse.quote(name, safe="") + ".html"


def step_graph_stem(name: str) -> str:
    return urllib.parse.quote(name, safe="")


def step_graph_filename(name: str, suffix: str) -> str:
    return step_graph_stem(name) + suffix


@lru_cache(maxsize=None)
def isabelle_session_directories(isabelle_src: Path) -> dict[str, tuple[Path, ...]]:
    directories: dict[str, list[Path]] = {}
    for root_file in isabelle_src.rglob("ROOT"):
        for match in SESSION_DECL_RE.finditer(root_file.read_text(errors="replace")):
            session = match.group(1) or match.group(2)
            relative_dir = match.group(3) or match.group(4)
            session_dir = root_file.parent / relative_dir if relative_dir else root_file.parent
            directories.setdefault(session, []).append(session_dir.resolve())
    return {
        session: tuple(dict.fromkeys(paths))
        for session, paths in directories.items()
    }


@lru_cache(maxsize=None)
def isabelle_theory_index(isabelle_src: Path) -> dict[str, tuple[Path, ...]]:
    theories: dict[str, list[Path]] = {}
    for theory_file in isabelle_src.rglob("*.thy"):
        theories.setdefault(theory_file.stem, []).append(theory_file.resolve())
    return {name: tuple(paths) for name, paths in theories.items()}


def resolve_isabelle_theory(
    session: str,
    theory: str,
    isabelle_src: Path = DEFAULT_ISABELLE_SRC,
) -> Path | None:
    session_dirs = isabelle_session_directories(isabelle_src).get(session, ())
    candidates = [
        path
        for path in isabelle_theory_index(isabelle_src).get(theory, ())
        if any(path.is_relative_to(session_dir) for session_dir in session_dirs)
    ]
    unique_candidates = list(dict.fromkeys(candidates))
    return unique_candidates[0] if len(unique_candidates) == 1 else None


def isabelle_statement_from_proof(
    proof_path: Path,
    isabelle_src: Path = DEFAULT_ISABELLE_SRC,
) -> IsabelleStatement | None:
    instance = read_instance(proof_path)
    if not instance:
        return None

    benchmark, problem = instance
    problem_path = Path(problem)
    try:
        problems_index = problem_path.parts.index("problems")
        session = problem_path.parts[problems_index + 1]
        indexed_theory = problem_path.parts[problems_index + 2]
    except (ValueError, IndexError):
        return None

    theory_parts = indexed_theory.split("_", 1)
    filename_match = re.match(r"prob_(\d+)_", problem_path.name)
    if len(theory_parts) != 2 or not filename_match:
        return None

    theory_name = theory_parts[1]
    source_path = resolve_isabelle_theory(session, theory_name, isabelle_src)
    source_line = int(filename_match.group(1))
    if source_path is None or not source_path.is_file() or source_line < 1:
        return None

    lines = source_path.read_text(errors="replace").splitlines()
    if source_line > len(lines):
        return None

    target_index = source_line - 1
    lemma_start = None
    lemma_command = re.compile(r"^(?:lemma|theorem|corollary|proposition)\b")
    for index in range(target_index, -1, -1):
        if lemma_command.match(lines[index].strip()):
            lemma_start = index
            break

    lemma_end = lemma_start
    if lemma_start is not None:
        for index in range(lemma_start + 1, target_index + 1):
            if re.match(r"^(?:proof|by|apply|sorry|oops)\b", lines[index].strip()):
                lemma_end = index - 1
                break
            lemma_end = index

    lemma_text = (
        textwrap.dedent("\n".join(lines[lemma_start : lemma_end + 1]))
        if lemma_start is not None and lemma_end is not None
        else ""
    )
    proof_start = max(0, target_index - 5)
    if lemma_start is not None:
        proof_start = max(proof_start, lemma_start)

    return IsabelleStatement(
        benchmark=benchmark,
        problem=problem,
        source_path=source_path,
        source_line=source_line,
        lemma_text=lemma_text,
        proof_text=textwrap.dedent("\n".join(lines[proof_start : target_index + 1])),
        lemma_start_line=lemma_start + 1 if lemma_start is not None else source_line,
        proof_start_line=proof_start + 1,
        symbols_path=isabelle_src.parent / "etc" / "symbols",
    )


def annotated_formula(record: dict) -> str:
    syntax = record.get("syntax") or "thf"
    name = record["name"]
    role = record.get("role") or "plain"
    formula = record.get("formula") or "$true"
    return f"{syntax}({name},{role},{formula})."


def split_pretty_formulae(text: str) -> list[str]:
    formulae: list[list[str]] = []
    current: list[str] = []
    start_pattern = re.compile(r"^(cnf|fof|tff|thf)\(")

    for line in text.splitlines():
        if start_pattern.match(line) and current:
            formulae.append(current)
            current = []
        if line.strip():
            current.append(line)

    if current:
        formulae.append(current)

    return ["\n".join(lines) for lines in formulae]


def pretty_formula_body(pretty_annotated: str) -> str:
    lines = pretty_annotated.splitlines()
    if not lines:
        return pretty_annotated
    if re.match(r"^(cnf|fof|tff|thf)\([^,]+,[^,]+,$", lines[0]):
        lines = lines[1:]
    if lines and lines[-1].endswith(" )."):
        lines[-1] = lines[-1][:-3]
    return "\n".join(line[4:] if line.startswith("    ") else line for line in lines)


def add_pretty_formulae(records: list[dict], tptp4x_command: str = "tptp4X") -> None:
    if not records:
        return

    input_text = "\n".join(annotated_formula(record) for record in records) + "\n"
    try:
        proc = subprocess.run(
            [tptp4x_command, "-q2", "-u", "human", "-V", "--"],
            input=input_text,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return

    pretty_formulae = split_pretty_formulae(proc.stdout)
    if len(pretty_formulae) != len(records):
        return

    for record, pretty_formula in zip(records, pretty_formulae):
        record["pretty_formula"] = pretty_formula_body(pretty_formula)


def descendants(starts: list[str], children: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(starts)
    while stack:
        name = stack.pop()
        for child in children.get(name, []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def negated_conjecture_descendants(graph: ProofGraph) -> set[str]:
    starts = [
        record["name"]
        for record in graph.records
        if record.get("role") == "negated_conjecture"
    ]
    return descendants(starts, graph.children)


def node_color(record: dict, negated_descendants: set[str] | None = None) -> str:
    if record.get("formula") == "$false":
        return "#3d1c00"
    if record.get("role") == "negated_conjecture":
        return ROLE_COLORS["negated_conjecture"]
    if negated_descendants and record["name"] in negated_descendants:
        return "#c62828"
    return ROLE_COLORS.get(record.get("role"), "#f8edd1")


def node_shape(record: dict, negated_descendants: set[str] | None = None) -> str:
    if record.get("role") == "conjecture":
        return "triangle"
    if record.get("role") == "negated_conjecture":
        return "box"
    if negated_descendants and record["name"] in negated_descendants:
        return "box"
    return "circle"


def step_node_colors(record: dict, negated_descendants: set[str]) -> tuple[str, str]:
    if record.get("role") == "conjecture":
        return "#dcfce7", "#22c55e"
    if record.get("role") == "negated_conjecture":
        return "#fecdd3", "#be123c"
    if record["name"] in negated_descendants:
        return "#ffe4e6", "#fb7185"
    if record.get("role") == "axiom":
        return "#dbeafe", "#2563eb"
    if record.get("role") == "type":
        return "#f1f5f9", "#94a3b8"
    return "#eff6ff", "#60a5fa"


def step_node_origin_class(record: dict, negated_descendants: set[str]) -> str:
    if record.get("role") == "conjecture":
        return "origin-conjecture"
    if record.get("role") == "negated_conjecture":
        return "origin-negated-conjecture"
    if record["name"] in negated_descendants:
        return "origin-negated-derived"
    if record.get("role") == "axiom":
        return "origin-axiom"
    if record.get("role") == "type":
        return "origin-type"
    return "origin-axiom-derived"


def overview_dot(
    graph: ProofGraph,
    include_types: bool = False,
    step_target: str = "_self",
    compact_chains: bool = False,
) -> str:
    records = graph.records if include_types else graph.formula_records
    all_included = {record["name"] for record in records}
    parents = {
        record["name"]: [
            parent for parent in record.get("parents", []) if parent in all_included
        ]
        for record in records
    }
    children = {name: [] for name in all_included}
    for child, child_parents in parents.items():
        for parent in child_parents:
            children[parent].append(child)

    compacted = (
        {
            name
            for name in all_included
            if len(parents[name]) == 1 and len(children[name]) == 1
        }
        if compact_chains
        else set()
    )
    included = all_included - compacted
    negated_descendants = negated_conjecture_descendants(graph)

    lines = [
        "digraph proof {",
        "  graph [rankdir=TB, overlap=false, splines=ortho, concentrate=true, remincross=true, ranksep=0.33, bgcolor=transparent];",
        "  node [shape=circle, style=filled, fixedsize=true, width=0.16, height=0.16, label=\"\", margin=0];",
        "  edge [color=\"#9aa4af\", arrowhead=none, penwidth=0.8, weight=1, minlen=1];",
    ]

    for record in records:
        name = record["name"]
        if name not in included:
            continue
        attrs = {
            "shape": node_shape(record, negated_descendants),
            "fillcolor": node_color(record, negated_descendants),
            "color": node_color(record, negated_descendants),
            "URL": f"steps/{step_filename(name)}",
            "target": step_target,
            "tooltip": f'{name} ({record.get("role", "unknown")})',
        }
        attrs_text = ", ".join(f"{key}={dot_quote(value)}" for key, value in attrs.items())
        lines.append(f"  {dot_id(name)} [{attrs_text}];")

    for record in records:
        parent = record["name"]
        if parent not in included:
            continue
        stack = list(children[parent])
        while stack:
            child = stack.pop()
            if child in compacted:
                stack.extend(children[child])
            elif child in included:
                lines.append(f"  {dot_id(parent)} -> {dot_id(child)};")

    final = graph.final_name
    if final in included:
        lines.append(f"  {{ rank=sink; {dot_id(final)}; }}")

    lines.append("}")
    return "\n".join(lines) + "\n"


def step_dot(graph: ProofGraph, record: dict, step_target: str = "_self") -> str:
    name = record["name"]
    parents = [parent for parent in record.get("parents", []) if parent in graph.by_name]
    children = graph.children.get(name, [])
    input_leaves = [
        leaf
        for leaf in graph.input_leaves.get(name, [])
        if leaf in graph.by_name and leaf != name
    ]
    included = set(input_leaves) | set(parents) | {name} | set(children)
    negated_descendants = negated_conjecture_descendants(graph)

    lines = [
        "digraph proof_step {",
        "  graph [rankdir=TB, overlap=false, splines=ortho, concentrate=false, remincross=true, ranksep=0.55, nodesep=0.28, bgcolor=transparent];",
        "  node [shape=box, style=\"rounded,filled\", margin=\"0.08,0.04\", fontname=\"Arial\", fontsize=10, color=\"#9aa4af\", penwidth=1.1];",
        "  edge [color=\"#8792a0\", arrowhead=normal, arrowsize=0.55, penwidth=0.9];",
    ]

    def attrs_for(node_name: str) -> dict[str, str]:
        node_record = graph.by_name[node_name]
        record_label = clause_record_label(node_record)
        fillcolor, color = step_node_colors(node_record, negated_descendants)
        if node_name == name:
            penwidth = "1.8"
        else:
            penwidth = "1.1"
        attrs = {
            "label": record_label or node_label(node_record),
            "fillcolor": fillcolor,
            "color": color,
            "penwidth": penwidth,
            "URL": step_filename(node_name),
            "target": step_target,
            "tooltip": f'{node_name} ({node_record.get("role", "unknown")})',
        }
        if record_label:
            attrs["shape"] = "Mrecord"
        return attrs

    emitted_nodes = set()
    for node_name in graph.input_leaves.get(name, []) + parents + [name] + children:
        if node_name in included and node_name not in emitted_nodes:
            emitted_nodes.add(node_name)
            attrs_text = ", ".join(
                f"{key}={dot_quote(value)}" for key, value in attrs_for(node_name).items()
            )
            lines.append(f"  {dot_id(node_name)} [{attrs_text}];")

    for parent in parents:
        for leaf in graph.input_leaves.get(parent, []):
            if leaf in included and leaf != parent:
                lines.append(f"  {dot_id(leaf)} -> {dot_id(parent)} [style=dotted];")
        lines.append(f"  {dot_id(parent)} -> {dot_id(name)};")

    for child in children:
        lines.append(f"  {dot_id(name)} -> {dot_id(child)};")

    ranks = [
        ("source", input_leaves),
        ("same", parents),
        ("same", [name]),
        ("sink", children),
    ]
    for rank, nodes in ranks:
        rank_nodes = [node for node in nodes if node in included]
        if rank_nodes:
            lines.append(
                "  { rank="
                + rank
                + "; "
                + " ".join(dot_id(node) for node in rank_nodes)
                + "; }"
            )

    lines.append("}")
    return "\n".join(lines) + "\n"


def render_svg(dot: str, dot_command: str = "dot") -> str:
    proc = subprocess.run(
        [dot_command, "-Tsvg"],
        input=dot,
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout


def inline_svg(svg: str) -> str:
    start = svg.find("<svg")
    return svg[start:] if start >= 0 else svg


def html_page(title: str, body: str, extra_head: str = "") -> str:
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{html.escape(title)}</title>",
            extra_head,
            "</head>",
            "<body>",
            body,
            "</body>",
            "</html>",
            "",
        ]
    )


def html_link_to_step(name: str, class_name: str = "node") -> str:
    escaped = html.escape(name)
    return f'<a class="{class_name}" href="{step_filename(name)}">{escaped}</a>'


def html_span_node(name: str, class_name: str = "node") -> str:
    return f'<span class="{class_name}">{html.escape(name)}</span>'


def node_list(names: list[str], class_name: str) -> str:
    if not names:
        return '<span class="empty">None</span>'
    links = [html_link_to_step(name, f"node {class_name}") for name in names]
    return "\n".join(links)


def origin_node_class(
    graph: ProofGraph,
    name: str,
    negated_descendants: set[str],
    extra_class: str = "",
) -> str:
    classes = ["node", step_node_origin_class(graph.by_name[name], negated_descendants)]
    if extra_class:
        classes.append(extra_class)
    return " ".join(classes)


def origin_node_list(
    graph: ProofGraph,
    names: list[str],
    negated_descendants: set[str],
) -> str:
    if not names:
        return '<span class="empty">None</span>'
    return "\n".join(
        html_link_to_step(name, origin_node_class(graph, name, negated_descendants))
        for name in names
    )


def metadata_items(record: dict) -> str:
    fields = [
        ("name", record.get("name")),
        ("syntax", record.get("syntax")),
        ("role", record.get("role")),
        ("inference", record.get("inference_rule")),
        ("file", record.get("file")),
        ("file node", record.get("file_node")),
    ]
    items = []
    for label, value in fields:
        if value:
            items.append(
                f'<span class="pill">{html.escape(label)}: {html.escape(str(value))}</span>'
            )
    return "\n".join(items)


TPTP_TOKEN_RE = re.compile(
    r"(?P<string>'(?:\\.|[^'\\])*')"
    r"|(?P<defined>\$[A-Za-z][A-Za-z0-9_]*)"
    r"|(?P<variable>\b[A-Z][A-Za-z0-9_]*\b)"
    r"|(?P<number>\b\d+(?:\.\d+)?\b)"
    r"|(?P<connective><=>|=>|<=|<~>|~&|~\||!=|[!?\-&|~])"
    r"|(?P<punctuation>[\[\]():])"
    r"|(?P<operator>[@=,])"
)


def highlight_formula(text: str) -> str:
    parts: list[str] = []
    last = 0
    for match in TPTP_TOKEN_RE.finditer(text):
        parts.append(html.escape(text[last:match.start()]))
        token = match.group(0)
        kind = match.lastgroup or "token"
        parts.append(f'<span class="tptp-{kind}">{html.escape(token)}</span>')
        last = match.end()
    parts.append(html.escape(text[last:]))
    return "".join(parts)


def detail_section(title: str, text: str, highlight: bool = False) -> str:
    content = highlight_formula(text) if highlight else html.escape(text)
    pre_class = ' class="formula-pre"' if highlight else ""
    return "\n".join(
        [
            '<section class="detail">',
            f"<h2>{html.escape(title)}</h2>",
            f"<pre{pre_class}>{content}</pre>",
            "</section>",
        ]
    )


def step_page(
    graph: ProofGraph,
    record: dict,
    step_svg: str,
    stylesheet_href: str = "../data/style.css",
) -> str:
    name = record["name"]
    input_leaves = graph.input_leaves.get(name, [])
    parents = [parent for parent in record.get("parents", []) if parent in graph.by_name]
    children = graph.children.get(name, [])
    negated_descendants = negated_conjecture_descendants(graph)
    source = record.get("source") or ""
    useful_info = record.get("useful_info") or ""

    formula_text = record.get("pretty_formula") or record.get("formula") or ""
    detail_blocks = [detail_section("Formula", formula_text, highlight=True)]
    if source:
        detail_blocks.append(detail_section("Source", source, highlight=True))
    if useful_info:
        detail_blocks.append(detail_section("Useful Info", useful_info))

    details = "\n".join(detail_blocks)

    body = f"""
<main class="step">
  <h1>Proof Step: {html.escape(name)}</h1>
  <nav class="step-nav">
    <a href="../index.html" target="_top">Proof Summary</a>
  </nav>
  <div class="meta">
    {metadata_items(record)}
  </div>
  <section class="step-graph">
    <h2>Proof State Overview</h2>
    <div class="step-graph-svg">
      {inline_svg(step_svg)}
    </div>
  </section>
  <section class="neighbors">
    <div class="neighbor-row">
      <h2>Input Dependencies</h2>
      <div class="node-list">
        {origin_node_list(graph, input_leaves, negated_descendants)}
      </div>
    </div>
    <div class="neighbor-row">
      <h2>Assumptions</h2>
      <div class="node-list">
        {origin_node_list(graph, parents, negated_descendants)}
      </div>
    </div>
    <div class="neighbor-row">
      <h2>Conclusion</h2>
      <div class="node-list">
        {html_span_node(name, origin_node_class(graph, name, negated_descendants, "current"))}
      </div>
    </div>
    <div class="neighbor-row">
      <h2>Dependents</h2>
      <div class="node-list">
        {origin_node_list(graph, children, negated_descendants)}
      </div>
    </div>
  </section>
  {details}
</main>
"""
    return html_page(name, body, f'<link rel="stylesheet" href="{html.escape(stylesheet_href)}">')


def proof_page(
    graph: ProofGraph,
    stylesheet_href: str = "data/style.css",
    isabelle_statement: IsabelleStatement | None = None,
) -> str:
    conjectures = [
        record for record in graph.formula_records if record.get("role") == "conjecture"
    ]
    axioms = [
        record for record in graph.formula_records if record.get("role") == "axiom"
    ]

    if conjectures:
        conjecture_blocks = []
        for record in conjectures:
            name = record["name"]
            formula = record.get("pretty_formula") or record.get("formula") or ""
            conjecture_blocks.append(
                "\n".join(
                    [
                        '<article class="proof-conjecture">',
                        f'<h2><a href="steps/{step_filename(name)}">{html.escape(name)}</a></h2>',
                        f'<pre class="formula-pre">{highlight_formula(formula)}</pre>',
                        "</article>",
                    ]
                )
            )
        conjecture_content = "\n".join(conjecture_blocks)
    else:
        conjecture_content = '<span class="empty">None</span>'

    if axioms:
        axiom_content = "\n".join(
            f'<span class="node axiom">{html.escape(record["name"])}</span>'
            for record in axioms
        )
    else:
        axiom_content = '<span class="empty">None</span>'

    final_name = graph.final_name
    final_content = (
        f'<a class="node final-step" href="steps/{step_filename(final_name)}">'
        f'{html.escape(final_name)}</a>'
        if final_name
        else '<span class="empty">None</span>'
    )

    def isabelle_excerpt(
        text: str,
        start_line: int,
        symbols_path: Path,
        highlight_last_line: bool = False,
    ) -> str:
        line_count = len(text.splitlines())
        line_numbers = "\n".join(str(start_line + offset) for offset in range(line_count))
        highlighted = highlight_isabelle(text, symbols_path)
        block_class = "isabelle-source-block highlight-last-line" if highlight_last_line else "isabelle-source-block"
        return (
            f'<div class="{block_class}">'
            f'<pre class="isabelle-line-numbers" aria-hidden="true">{line_numbers}</pre>'
            f'<pre class="isabelle-source">{highlighted}</pre>'
            '</div>'
        )

    if isabelle_statement:
        source_label = (
            f"{isabelle_statement.source_path.name}:"
            f"{isabelle_statement.source_line}"
        )
        isabelle_content = f"""
  <section class="proof-summary-section isabelle-statement">
    <h2>Isabelle Statement</h2>
    <div class="meta">
      <span class="pill">source: {html.escape(source_label)}</span>
      <span class="pill">benchmark: {html.escape(isabelle_statement.benchmark)}</span>
      <span class="pill">problem: {html.escape(isabelle_statement.problem)}</span>
    </div>
    <h3>Lemma</h3>
    {isabelle_excerpt(isabelle_statement.lemma_text, isabelle_statement.lemma_start_line, isabelle_statement.symbols_path)}
    <h3>Proof Excerpt</h3>
    {isabelle_excerpt(isabelle_statement.proof_text, isabelle_statement.proof_start_line, isabelle_statement.symbols_path, highlight_last_line=True)}
  </section>"""
    else:
        source_label = None
        isabelle_content = ""

    summary_title = (
        f"Proof Summary of {source_label}"
        if source_label
        else "Proof Summary"
    )

    body = f"""
<main class="step proof-summary">
  <p class="kicker">Proof</p>
  <h1>{html.escape(summary_title)}</h1>
  {isabelle_content}
  <section class="proof-summary-section">
    <h2>Conjectures</h2>
    <div class="proof-conjectures">
      {conjecture_content}
    </div>
  </section>
  <section class="proof-summary-section">
    <h2>Axioms</h2>
    <div class="node-list">
      {axiom_content}
    </div>
  </section>
  <section class="proof-summary-section">
    <h2>Final Contradiction</h2>
    <div class="node-list">
      {final_content}
    </div>
  </section>
</main>
"""
    return html_page(
        summary_title,
        body,
        f'<link rel="stylesheet" href="{html.escape(stylesheet_href)}">',
    )


def library_menu_html(
    entries: list[dict[str, str]] | None,
    current_href: str | None = None,
) -> str:
    if not entries:
        return ""
    links = []
    for entry in entries:
        label = entry["label"]
        href = entry["href"]
        current_attr = ' aria-current="page"' if href == current_href else ""
        links.append(
            f'<a href="{html.escape(href)}"{current_attr}>{html.escape(label)}</a>'
        )
    return "\n".join(
        [
            '<nav class="library-menu" data-library-menu hidden aria-label="Proof library">',
            '<div class="library-menu-heading">Proof Library</div>',
            *links,
            "</nav>",
        ]
    )


def topbar_html(
    library_entries: list[dict[str, str]] | None = None,
    current_href: str | None = None,
) -> str:
    has_library = bool(library_entries)
    button_attrs = (
        'data-menu-toggle aria-expanded="false"'
        if has_library
        else "disabled"
    )
    return f"""
<header class="topbar">
  <button class="menu-button" type="button" aria-label="Menu" title="Menu" {button_attrs}>
    <span aria-hidden="true">☰</span>
  </button>
  <div class="brand" aria-label="Vizabell">
    <span class="brand-mark" aria-hidden="true">◎</span>
    <span class="brand-title">Vizabell</span>
    <span class="brand-bell" aria-hidden="true">🔔</span>
  </div>
  {library_menu_html(library_entries, current_href)}
</header>"""


def index_page(
    graph: ProofGraph,
    overview_svg: str,
    flat_overview_svg: str,
    stylesheet_href: str = "data/style.css",
    script_src: str = "data/app.js",
    isabelle_statement: IsabelleStatement | None = None,
    library_entries: list[dict[str, str]] | None = None,
    current_library_href: str | None = None,
) -> str:
    edge_count = sum(len(record.get("parents", [])) for record in graph.formula_records)
    overview_title = "Proof Overview"
    if isabelle_statement:
        overview_title = (
            f"Proof Overview of {isabelle_statement.source_path.name}:"
            f"{isabelle_statement.source_line}"
        )
    body = f"""
{topbar_html(library_entries, current_library_href)}
<main class="split-shell">
  <section class="overview-pane">
    <div class="overview">
      <div class="overview-heading">
        <p class="kicker">Derivation DAG</p>
        <h1>{html.escape(overview_title)}</h1>
        <p class="overview-subtitle">{len(graph.formula_records)} formulas · {edge_count} derivations</p>
      </div>
      <div class="overview-viewport">
        <div class="overview-svg">
          <div class="overview-graph" data-proof-view="full">
            {inline_svg(overview_svg)}
          </div>
          <div class="overview-graph" data-proof-view="flat" hidden>
            {inline_svg(flat_overview_svg)}
          </div>
        </div>
      </div>
    </div>
    <div class="overview-controls" aria-label="Overview controls">
      <button class="zoom-button" type="button" data-zoom="out" aria-label="Zoom out" title="Zoom out">−</button>
      <span class="zoom-readout" aria-live="polite">100%</span>
      <button class="zoom-button" type="button" data-zoom="in" aria-label="Zoom in" title="Zoom in">+</button>
      <button class="zoom-fit-button" type="button" data-zoom-fit aria-label="Fit proof" title="Fit proof">Fit</button>
      <button class="proof-view-button" type="button" data-proof-view-toggle aria-label="Show flat proof" title="Compact linear proof chains">Flat</button>
    </div>
  </section>
  <div class="splitter" role="separator" aria-orientation="vertical" aria-label="Resize proof overview"></div>
  <section class="step-pane">
    <iframe name="step-frame" src="proof.html" title="Proof details"></iframe>
  </section>
</main>
"""
    return html_page(
        overview_title,
        body,
        (
            f'<link rel="stylesheet" href="{html.escape(stylesheet_href)}">\n'
            f'<script src="{html.escape(script_src)}" defer></script>'
        ),
    )


def install_data_dir(output_dir: Path) -> None:
    target = output_dir / "data"
    if target.exists() or target.is_symlink():
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
    try:
        target.symlink_to(DATA_DIR, target_is_directory=True)
    except OSError:
        shutil.copytree(DATA_DIR, target)


def write_html_site(
    graph: ProofGraph,
    output_dir: Path,
    include_types: bool = False,
    dot_command: str = "dot",
    tptp4x_command: str = "tptp4X",
    asset_dir: Path | None = None,
    isabelle_statement: IsabelleStatement | None = None,
    library_entries: list[dict[str, str]] | None = None,
    current_library_href: str | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    steps_dir = output_dir / "steps"
    steps_dir.mkdir(parents=True, exist_ok=True)
    data_dir = asset_dir or output_dir
    install_data_dir(data_dir)
    index_asset_prefix = Path(os.path.relpath(data_dir / "data", output_dir))
    step_asset_prefix = Path(os.path.relpath(data_dir / "data", steps_dir))

    records = graph.records if include_types else graph.formula_records
    add_pretty_formulae(records, tptp4x_command)
    for record in records:
        step_graph_dot = step_dot(graph, record)
        step_graph_svg = render_svg(step_graph_dot, dot_command)
        (steps_dir / step_graph_filename(record["name"], ".dot")).write_text(step_graph_dot)
        (steps_dir / step_graph_filename(record["name"], ".svg")).write_text(step_graph_svg)
        (steps_dir / step_filename(record["name"])).write_text(
            step_page(
                graph,
                record,
                step_graph_svg,
                f"{step_asset_prefix.as_posix()}/style.css",
            )
        )
    (output_dir / "proof.html").write_text(
        proof_page(
            graph,
            f"{index_asset_prefix.as_posix()}/style.css",
            isabelle_statement,
        )
    )

    dot = overview_dot(graph, include_types=include_types, step_target="step-frame")
    overview_svg = render_svg(dot, dot_command)
    flat_dot = overview_dot(
        graph,
        include_types=include_types,
        step_target="step-frame",
        compact_chains=True,
    )
    flat_overview_svg = render_svg(flat_dot, dot_command)
    (output_dir / "proof.svg").write_text(overview_svg)
    (output_dir / "proof.dot").write_text(dot)
    (output_dir / "proof-flat.svg").write_text(flat_overview_svg)
    (output_dir / "proof-flat.dot").write_text(flat_dot)
    (output_dir / "index.html").write_text(
        index_page(
            graph,
            overview_svg,
            flat_overview_svg,
            f"{index_asset_prefix.as_posix()}/style.css",
            f"{index_asset_prefix.as_posix()}/app.js",
            isabelle_statement,
            library_entries,
            current_library_href,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate proof visualization output.")
    parser.add_argument("input", type=Path, help="TPTP problem/proof file, optionally gzip-compressed")
    parser.add_argument("-o", "--output", type=Path, help="Output DOT file. Defaults to stdout.")
    parser.add_argument("--include-types", action="store_true", help="Include type declarations in the graph")
    parser.add_argument(
        "--format",
        choices=("auto", "dot", "svg"),
        default="auto",
        help="Output format. 'auto' uses the output suffix, defaulting to dot.",
    )
    parser.add_argument("--dot-command", default="dot", help="Graphviz dot executable")
    parser.add_argument("--tptp4x-command", default="tptp4X", help="tptp4X executable")
    parser.add_argument(
        "--asset-dir",
        type=Path,
        help="Directory where shared static data/ assets are installed. Defaults to the HTML output directory.",
    )
    parser.add_argument(
        "--isabelle-src",
        type=Path,
        default=DEFAULT_ISABELLE_SRC,
        help="Isabelle src directory used to resolve INSTANCE source locations",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate index.html, proof.svg, proof.dot, style.css, and step pages in the output directory",
    )
    args = parser.parse_args(argv)

    graph = ProofGraph(parse_file(args.input))
    if args.html:
        output_dir = args.output or Path("out")
        isabelle_statement = isabelle_statement_from_proof(
            args.input, args.isabelle_src
        )
        write_html_site(
            graph,
            output_dir,
            args.include_types,
            args.dot_command,
            args.tptp4x_command,
            args.asset_dir,
            isabelle_statement,
        )
        return 0

    dot = overview_dot(graph, include_types=args.include_types)
    output_format = args.format
    if output_format == "auto":
        output_format = "svg" if args.output and args.output.suffix == ".svg" else "dot"
    text = render_svg(dot, args.dot_command) if output_format == "svg" else dot

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

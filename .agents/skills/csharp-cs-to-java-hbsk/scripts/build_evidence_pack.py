#!/usr/bin/env python3
"""Build a compact evidence pack for HBSK C# -> Java migration tasks."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CSHARP_ROOT_TEXT = "D:/codingProjects/#Net_\u526f\u672c/Source/BizModule"
DEFAULT_JAVA_ROOT_TEXT = "D:/codingProjects/JAVA/HBSK"
DEFAULT_LIMIT = 10
DEFAULT_TIMEOUT_SECONDS = 90.0
COMMAND_TIMEOUT_SECONDS: float | None = DEFAULT_TIMEOUT_SECONDS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class SymbolHit:
    name: str
    qualified_name: str
    kind: str
    file_path: str
    start_line: int | None
    end_line: int | None
    docstring: str = ""
    resolved_symbol: bool = True

    @property
    def display(self) -> str:
        qn = self.qualified_name or self.name
        line = self.start_line if self.start_line is not None else "?"
        return f"{qn} ({self.kind}) {self.file_path}:{line}"


@dataclass
class UiEventBinding:
    control: str
    caption: str
    event: str
    handler: str
    designer_line: int


@dataclass
class MethodBlock:
    name: str
    start_line: int
    end_line: int
    lines: list[tuple[int, str]]


@dataclass
class ServiceCall:
    interface: str
    method: str
    line: int
    chain: list[str]
    status: str = "active"

    @property
    def key(self) -> str:
        return f"{self.status}|{' -> '.join(self.chain)}|{self.interface}.{self.method}|{self.line}"


@dataclass
class UiTriggerEvidence:
    page_order: int
    page_class: str
    designer_path: Path
    code_path: Path
    control: str
    raw_display: str
    display_name: str
    event: str
    handler: str
    designer_line: int
    service_methods: set[str]
    chain_summary: str
    priority: int
    fallback: bool = False
    contract_evidence: str = ""


@dataclass
class JavaOperationMethod:
    name: str
    start_line: int
    end_line: int
    operation_start_line: int | None
    operation_end_line: int | None
    operation_text: str
    current_summary: str
    current_description: str
    mapping_path: str
    javadoc: str
    service_methods: set[str]
    indent: str


@dataclass
class OperationRecommendation:
    method: JavaOperationMethod
    recommended_summary: str
    recommended_description: str
    trigger: UiTriggerEvidence | None
    confidence: str
    patch_action: str
    reason: str
    candidate_count: int


def timeout_value() -> float | None:
    return COMMAND_TIMEOUT_SECONDS if COMMAND_TIMEOUT_SECONDS and COMMAND_TIMEOUT_SECONDS > 0 else None


def timeout_text(exc: subprocess.TimeoutExpired) -> tuple[str, str]:
    stdout = exc.stdout or ""
    stderr = exc.stderr or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    command = " ".join(str(item) for item in exc.cmd) if isinstance(exc.cmd, list) else str(exc.cmd)
    timeout = f"command timed out after {exc.timeout}s: {command}"
    return stdout, f"{stderr}\n{timeout}".strip()


def run_command(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_value(),
        )
        return completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        out, err = timeout_text(exc)
        return 124, out, err
    except FileNotFoundError as exc:
        return 127, "", str(exc)


def read_text_compat(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def codegraph_executable() -> str:
    for candidate in ("codegraph.cmd", "codegraph.exe", "codegraph"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return "codegraph"


def project_arg(project: str | Path) -> str:
    return str(project).replace("\\", "/")


def split_path_line(value: str) -> tuple[str, int | None]:
    cleaned = value.strip().strip('"\'')
    match = re.match(r"^(.*):(\d+)$", cleaned)
    if match:
        return match.group(1), int(match.group(2))
    return cleaned, None


def infer_enclosing_symbol(path: Path, line: int | None) -> str | None:
    suffix = path.suffix.lower()
    if suffix not in {".cs", ".java", ".py", ".xml"}:
        return None
    try:
        lines = read_text_compat(path).splitlines()
    except OSError:
        return None
    if not lines:
        return None
    index = min(max((line or 1) - 1, 0), len(lines) - 1)
    lower_bound = max(0, index - 220)

    if suffix == ".py":
        for idx in range(index, lower_bound - 1, -1):
            match = re.match(r"\s*(?:async\s+def|def|class)\s+([A-Za-z_]\w*)\b", lines[idx])
            if match:
                return match.group(1)
        return None

    if suffix == ".xml":
        xml_pattern = re.compile(r"<(?:select|insert|update|delete|resultMap|sql)\b[^>]*\bid\s*=\s*['\"]([^'\"]+)['\"]")
        for idx in range(index, lower_bound - 1, -1):
            match = xml_pattern.search(lines[idx])
            if match:
                return match.group(1)
        return None

    class_candidate: str | None = None
    method_pattern = re.compile(
        r"^\s*(?:(?:public|private|protected|internal|static|final|synchronized|abstract|"
        r"virtual|override|async|sealed|partial|native|default)\s+)*"
        r"(?:[\w<>\[\],.?]+\s+)+(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*"
        r"(?:\{|$|throws\b|where\b)"
    )
    declaration_start_pattern = re.compile(
        r"^\s*(?:(?:public|private|protected|internal|static|final|synchronized|abstract|"
        r"virtual|override|async|sealed|partial|native|default)\b|"
        r"(?:[\w<>\[\],.?]+\s+)+[A-Za-z_]\w*\s*\()"
    )
    constructor_pattern = re.compile(
        r"^\s*(?:(?:public|private|protected|internal)\s+)?"
        r"(?P<name>[A-Z][A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:\{|$|where\b)"
    )
    class_pattern = re.compile(r"\b(?:class|interface|record|struct|enum)\s+([A-Za-z_]\w*)\b")
    ignored_names = {"if", "for", "foreach", "while", "switch", "catch", "using", "lock", "return", "new"}

    def declaration_name_at(idx: int) -> str | None:
        stripped = lines[idx].strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("*"):
            return None
        if stripped.startswith("@") or stripped.startswith("["):
            return None
        if not declaration_start_pattern.search(stripped):
            return None
        signature_parts: list[str] = []
        for scan_idx in range(idx, min(len(lines), idx + 12)):
            part = lines[scan_idx].strip()
            if not part or part.startswith("//"):
                continue
            signature_parts.append(part)
            if "{" in part or ";" in part:
                break
        signature = " ".join(signature_parts)
        method_match = method_pattern.search(signature) or constructor_pattern.search(signature)
        if not method_match:
            return None
        name = method_match.group("name")
        return None if name in ignored_names else name

    current = lines[index].strip()
    if current.startswith("@") or current.startswith("["):
        upper_bound = min(len(lines), index + 40)
        for idx in range(index, upper_bound):
            name = declaration_name_at(idx)
            if name:
                return name
            class_match = class_pattern.search(lines[idx].strip())
            if class_match:
                return class_match.group(1)

    for idx in range(index, lower_bound - 1, -1):
        stripped = lines[idx].strip()
        class_match = class_pattern.search(stripped)
        if class_match and class_candidate is None:
            class_candidate = class_match.group(1)
        name = declaration_name_at(idx)
        if name:
            return name
    return class_candidate


def resolve_location_hit(project: Path, value: str, language: str) -> SymbolHit | None:
    raw_path, line = split_path_line(value)
    if not raw_path or not re.search(r"[\\/]|\.cs$|\.java$|\.py$|\.xml$", raw_path, re.IGNORECASE):
        return None

    candidates: list[Path] = []
    direct = Path(raw_path)
    candidates.append(direct if direct.is_absolute() else project / direct)
    if not direct.is_absolute():
        candidates.append(Path.cwd() / direct)

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if not resolved.exists() or not resolved.is_file():
            continue
        try:
            display_path = resolved.relative_to(project.resolve()).as_posix()
        except ValueError:
            display_path = resolved.as_posix()
        symbol = infer_enclosing_symbol(resolved, line)
        resolved_symbol = symbol is not None
        name = symbol or resolved.stem
        return SymbolHit(
            name=name,
            qualified_name=f"{name}@location" if resolved_symbol else f"{resolved.stem}@unresolved-location",
            kind=f"{language}-location" if resolved_symbol else f"{language}-unresolved-location",
            file_path=display_path,
            start_line=line or 1,
            end_line=None,
            resolved_symbol=resolved_symbol,
        )
    return None


def codegraph_json(project: str | Path, command: str, symbol: str, limit: int) -> Any:
    rc, out, err = run_command([
        codegraph_executable(),
        command,
        "-p",
        project_arg(project),
        "--json",
        "--limit",
        str(limit),
        symbol,
    ])
    if rc != 0:
        return {"error": err.strip() or out.strip(), "command": command, "symbol": symbol}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"error": "invalid-json", "raw": out[:1000], "command": command, "symbol": symbol}


def node_to_hit(item: dict[str, Any]) -> SymbolHit | None:
    node = item.get("node", item)
    if not isinstance(node, dict):
        return None
    file_path = node.get("filePath")
    name = node.get("name")
    if not file_path or not name:
        return None
    return SymbolHit(
        name=name,
        qualified_name=node.get("qualifiedName") or name,
        kind=node.get("kind") or "unknown",
        file_path=file_path,
        start_line=node.get("startLine"),
        end_line=node.get("endLine"),
        docstring=(node.get("docstring") or "").strip(),
    )


def parse_query_hits(data: Any) -> list[SymbolHit]:
    if not isinstance(data, list):
        return []
    hits: list[SymbolHit] = []
    for item in data:
        if isinstance(item, dict):
            hit = node_to_hit(item)
            if hit:
                hits.append(hit)
    return hits


def parse_relation_hits(data: Any, key: str) -> list[SymbolHit]:
    if not isinstance(data, dict):
        return []
    items = data.get(key) or []
    hits: list[SymbolHit] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        file_path = item.get("filePath")
        name = item.get("name")
        if file_path and name:
            hits.append(SymbolHit(
                name=name,
                qualified_name=item.get("qualifiedName") or name,
                kind=item.get("kind") or "unknown",
                file_path=file_path,
                start_line=item.get("startLine"),
                end_line=item.get("endLine"),
            ))
    return hits


def rg(project: Path, pattern: str, glob: str = "*.cs", limit: int = 80, targets: list[Path] | None = None) -> list[str]:
    search_targets = targets or [project]
    cmd = ["rg", "-n", "--glob", glob, pattern]
    cmd.extend(project_arg(target) for target in search_targets)
    rc, out, _ = run_command(cmd)
    if rc not in (0, 1):
        return []
    lines = [line for line in out.splitlines() if line.strip()]
    return lines[:limit]


def read_window(project: Path, relative_file: str, line: int | None, radius: int) -> list[str]:
    if line is None:
        return []
    path = project / relative_file
    if not path.exists() or not path.is_file():
        return []
    try:
        all_lines = read_text_compat(path).splitlines()
    except OSError:
        return []
    start = max(1, line - radius)
    end = min(len(all_lines), line + radius)
    return [f"{idx}: {all_lines[idx - 1]}" for idx in range(start, end + 1)]


def hit_targets(project: Path, hits: list[SymbolHit]) -> list[Path]:
    targets: list[Path] = []
    seen: set[str] = set()
    for hit in hits:
        file_path = project / hit.file_path
        target = file_path if file_path.exists() else file_path.parent
        key = target.as_posix()
        if target.exists() and key not in seen:
            targets.append(target)
            seen.add(key)
    return targets


def entry_terms(entry: str) -> list[str]:
    raw = [entry]
    for sep in ("::", ".", "#", "/", "\\"):
        pieces: list[str] = []
        for item in raw:
            pieces.extend(part for part in item.split(sep) if part)
        raw.extend(pieces)
    result: list[str] = []
    for item in raw:
        token = item.strip().strip('"\'')
        if token and token not in result:
            result.append(token)
    return result[:8]


def infer_left_where(lines: list[str], windows_text: str) -> str:
    text = "\n".join(lines) + "\n" + windows_text
    if not re.search(r"leftWhereStr", text, re.IGNORECASE):
        return "not-found"
    uncommented = [line for line in lines if "leftWhereStr" in line and not line.lstrip().startswith("//")]
    if not uncommented:
        return "commented-out"
    if re.search(r"\+\s*\"\s*And\s*\"\s*\+\s*leftWhereStr|leftWhereStr\s*\+\s*\"\s*And|Get\w+\([^\)]*leftWhereStr", text):
        return "sql-fragment"
    return "need-confirm"


def resolution_source(location_arg: str | None, path_hit: SymbolHit | None, hits: list[SymbolHit]) -> str:
    if not resolved_hits(hits):
        return "not-found"
    if path_hit:
        return "explicit-user-input"
    return "codegraph"


def resolved_hits(hits: list[SymbolHit]) -> list[SymbolHit]:
    return [hit for hit in hits if hit.resolved_symbol]


def first_anchor(hits: list[SymbolHit]) -> str:
    resolved = resolved_hits(hits)
    return resolved[0].display if resolved else "not-found"


def ambiguity_summary(csharp_hits: list[SymbolHit], java_hits: list[SymbolHit]) -> str:
    parts: list[str] = []
    csharp_resolved = resolved_hits(csharp_hits)
    java_resolved = resolved_hits(java_hits)
    if len(csharp_resolved) > 1:
        parts.append("csharp=" + " | ".join(hit.display for hit in csharp_resolved[:5]))
    if len(java_resolved) > 1:
        parts.append("java=" + " | ".join(hit.display for hit in java_resolved[:5]))
    return "; ".join(parts) if parts else "none"


def normalize_path_for_display(text: str) -> str:
    return text.replace("\\", "/")


def classify_permission(line: str) -> str:
    lower = line.lower()
    if "if (true)" in lower or "isadmin" in lower or "supper" in lower or "super" in lower:
        return "bypass-or-exclusion"
    if "allowedit" in lower or ".enabled" in lower or ".visible" in lower or "optionscolumn" in lower:
        return "ui-only"
    if "checkright" in lower or "unallowed" in lower or "business" in lower:
        return "backend-auth"
    if "danger" in lower or "资质" in line or "资格" in line:
        return "business-qualification"
    if "haspermission" in lower:
        return "need-classify"
    return "not-permission"


def md_list(title: str, lines: list[str], empty: str = "not-found") -> list[str]:
    output = [f"## {title}", ""]
    if not lines:
        output.append(f"- {empty}")
    else:
        output.extend(f"- {normalize_path_for_display(line)}" for line in lines)
    output.append("")
    return output


def project_relative(project: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def resolve_existing_file(project: Path, value: str) -> Path | None:
    raw_path, _ = split_path_line(value)
    if not raw_path:
        return None
    candidate = Path(raw_path)
    candidates = [candidate if candidate.is_absolute() else project / candidate]
    if not candidate.is_absolute():
        candidates.append(Path.cwd() / candidate)
    for item in candidates:
        try:
            resolved = item.resolve()
        except OSError:
            resolved = item
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


def parse_csharp_class_name(text: str) -> str | None:
    match = re.search(r"\bpartial\s+class\s+([A-Za-z_]\w*)\b", text)
    if match:
        return match.group(1)
    match = re.search(r"\bclass\s+([A-Za-z_]\w*)\b", text)
    return match.group(1) if match else None


def companion_code_file(path: Path) -> Path:
    if path.name.endswith(".Designer.cs"):
        return path.with_name(path.name.replace(".Designer.cs", ".cs"))
    return path


def companion_designer_file(path: Path) -> Path:
    if path.name.endswith(".Designer.cs"):
        return path
    return path.with_name(f"{path.stem}.Designer.cs")


def resolve_ui_page_files(project: Path, value: str, limit: int) -> tuple[str, Path | None, Path | None, list[SymbolHit], str]:
    explicit_file = resolve_existing_file(project, value)
    codegraph_hits: list[SymbolHit] = []
    source = "explicit-user-input"
    class_name: str | None = None

    if explicit_file:
        try:
            class_name = parse_csharp_class_name(read_text_compat(explicit_file))
        except OSError:
            class_name = None
        if class_name:
            codegraph_hits = parse_query_hits(codegraph_json(project, "query", class_name, limit))
        designer = companion_designer_file(explicit_file)
        code = companion_code_file(explicit_file)
        return class_name or explicit_file.stem.replace(".Designer", ""), designer if designer.exists() else None, code if code.exists() else None, codegraph_hits, source

    source = "codegraph"
    primary = entry_terms(value)[0]
    codegraph_hits = parse_query_hits(codegraph_json(project, "query", primary, limit))
    preferred = next((hit for hit in codegraph_hits if hit.file_path.endswith(".Designer.cs")), None)
    if preferred is None:
        preferred = next((hit for hit in codegraph_hits if hit.file_path.endswith(".cs")), None)
    if preferred is None:
        return primary, None, None, codegraph_hits, "not-found"

    resolved = (project / preferred.file_path).resolve()
    try:
        class_name = parse_csharp_class_name(read_text_compat(resolved))
    except OSError:
        class_name = preferred.name
    designer = companion_designer_file(resolved)
    code = companion_code_file(resolved)
    return class_name or preferred.name, designer if designer.exists() else None, code if code.exists() else None, codegraph_hits, source


def decode_csharp_string(value: str) -> str:
    return (
        value.replace(r"\"", '"')
        .replace(r"\\", "\\")
        .replace(r"\r", " ")
        .replace(r"\n", " ")
        .strip()
    )


def parse_designer_events(designer_path: Path, class_name: str) -> list[UiEventBinding]:
    lines = read_text_compat(designer_path).splitlines()
    metadata: dict[str, dict[str, str]] = {"this": {"Name": class_name}}
    property_pattern = re.compile(r'this\.(?P<control>[A-Za-z_]\w*)\.(?P<prop>Caption|Text|Name)\s*=\s*"(?P<value>(?:\\.|[^"\\])*)"')
    form_property_pattern = re.compile(r'this\.(?P<prop>Text|Name)\s*=\s*"(?P<value>(?:\\.|[^"\\])*)"')
    control_event_pattern = re.compile(
        r"this\.(?P<control>[A-Za-z_]\w*)\.(?P<event>[A-Za-z_]\w*)\s*\+=\s*"
        r"(?:new\s+[A-Za-z0-9_.<>]+\s*\(\s*)?(?:this\.)?(?P<handler>[A-Za-z_]\w*)"
    )
    form_event_pattern = re.compile(
        r"this\.(?P<event>[A-Za-z_]\w*)\s*\+=\s*"
        r"(?:new\s+[A-Za-z0-9_.<>]+\s*\(\s*)?(?:this\.)?(?P<handler>[A-Za-z_]\w*)"
    )

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        match = property_pattern.search(line)
        if match:
            control = match.group("control")
            metadata.setdefault(control, {})[match.group("prop")] = decode_csharp_string(match.group("value"))
            continue
        match = form_property_pattern.search(line)
        if match:
            metadata.setdefault("this", {})[match.group("prop")] = decode_csharp_string(match.group("value"))

    events: list[UiEventBinding] = []
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//") or "+=" not in stripped:
            continue
        match = control_event_pattern.search(line)
        control = ""
        event_name = ""
        handler = ""
        if match:
            control = match.group("control")
            event_name = match.group("event")
            handler = match.group("handler")
        else:
            match = form_event_pattern.search(line)
            if not match:
                continue
            control = "this"
            event_name = match.group("event")
            handler = match.group("handler")
        meta = metadata.get(control, {})
        caption = meta.get("Caption") or meta.get("Text") or meta.get("Name") or control
        events.append(UiEventBinding(control=control, caption=caption, event=event_name, handler=handler, designer_line=index))
    return events


def strip_line_comment(line: str) -> str:
    in_string = False
    escape = False
    for index in range(len(line) - 1):
        char = line[index]
        if char == "\\" and in_string:
            escape = not escape
            continue
        if char == '"' and not escape:
            in_string = not in_string
        escape = False
        if not in_string and line[index:index + 2] == "//":
            return line[:index]
    return line


def brace_delta(line: str) -> int:
    cleaned = re.sub(r'"(?:\\.|[^"\\])*"', '""', strip_line_comment(line))
    return cleaned.count("{") - cleaned.count("}")


def parse_csharp_methods(path: Path) -> dict[str, MethodBlock]:
    lines = read_text_compat(path).splitlines()
    method_pattern = re.compile(
        r"^\s*(?:public|private|protected|internal)\s+"
        r"(?:static\s+)?(?:[\w<>\[\],.?]+\s+)+(?P<name>[A-Za-z_]\w*)\s*\("
    )
    methods: dict[str, MethodBlock] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("//") or "(" not in line:
            index += 1
            continue
        match = method_pattern.search(line)
        if not match:
            index += 1
            continue

        name = match.group("name")
        open_index = index
        while open_index < len(lines) and "{" not in strip_line_comment(lines[open_index]):
            open_index += 1
        if open_index >= len(lines):
            index += 1
            continue

        depth = 0
        end_index = open_index
        for end_index in range(open_index, len(lines)):
            depth += brace_delta(lines[end_index])
            if depth == 0:
                break
        block_lines = [(line_number, lines[line_number - 1]) for line_number in range(index + 1, end_index + 2)]
        methods[name] = MethodBlock(name=name, start_line=index + 1, end_line=end_index + 1, lines=block_lines)
        index = end_index + 1
    return methods


def active_lines(block: MethodBlock) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for line_no, line in block.lines:
        if line.strip().startswith("//"):
            continue
        cleaned = strip_line_comment(line).strip()
        if cleaned:
            result.append((line_no, cleaned))
    return result


def commented_lines(block: MethodBlock) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for line_no, line in block.lines:
        stripped = line.strip()
        if stripped.startswith("//"):
            uncommented = re.sub(r"^\s*//\s?", "", line).strip()
            if uncommented:
                result.append((line_no, uncommented))
    return result


def extract_service_calls(lines: list[tuple[int, str]], chain: list[str], status: str) -> list[ServiceCall]:
    manager_vars: dict[str, str] = {}
    service_aliases: dict[str, str] = {}
    calls: list[ServiceCall] = []

    manager_patterns = [
        re.compile(r"\bvar\s+(?P<var>[A-Za-z_]\w*)\s*=\s*new\s+ServiceManager<(?P<iface>I[A-Za-z_]\w*)>"),
        re.compile(r"\bServiceManager<(?P<iface>I[A-Za-z_]\w*)>\s+(?P<var>[A-Za-z_]\w*)\b"),
    ]
    alias_pattern = re.compile(r"\b(?P<iface>I[A-Za-z_]\w*)\s+(?P<alias>[A-Za-z_]\w*)\s*=\s*(?P<manager>[A-Za-z_]\w*)\.Service\b")
    direct_call_pattern = re.compile(r"\b(?P<manager>[A-Za-z_]\w*)\.Service\.(?P<method>[A-Za-z_]\w*)\s*\(")
    alias_call_pattern = re.compile(r"(?<!\.)\b(?P<alias>[A-Za-z_]\w*)\.(?P<method>[A-Za-z_]\w*)\s*\(")
    inline_call_pattern = re.compile(r"new\s+ServiceManager<(?P<iface>I[A-Za-z_]\w*)>\s*\(\s*\)\.Service\.(?P<method>[A-Za-z_]\w*)\s*\(")

    for line_no, line in lines:
        for pattern in manager_patterns:
            for match in pattern.finditer(line):
                manager_vars[match.group("var")] = match.group("iface")
        for match in alias_pattern.finditer(line):
            service_aliases[match.group("alias")] = match.group("iface") or manager_vars.get(match.group("manager"), "unknown-interface")
        for match in direct_call_pattern.finditer(line):
            manager = match.group("manager")
            if manager in manager_vars:
                calls.append(ServiceCall(manager_vars[manager], match.group("method"), line_no, chain[:], status))
        for match in alias_call_pattern.finditer(line):
            alias = match.group("alias")
            if alias in service_aliases:
                calls.append(ServiceCall(service_aliases[alias], match.group("method"), line_no, chain[:], status))
        for match in inline_call_pattern.finditer(line):
            calls.append(ServiceCall(match.group("iface"), match.group("method"), line_no, chain[:], status))
    return calls


def local_method_calls(block: MethodBlock, method_names: set[str], click_handlers: dict[str, str]) -> list[str]:
    ignored = {
        "if", "for", "foreach", "while", "switch", "catch", "using", "return", "new", "typeof",
        "nameof", "lock", "delegate", "base", "this",
    }
    calls: list[str] = []
    generic_call_pattern = re.compile(r"(?:this\.)?(?P<name>[A-Za-z_]\w*)\s*\(")
    event_handler_pattern = re.compile(r"EventHandler\s*\(\s*(?:this\.)?(?P<name>[A-Za-z_]\w*)\s*\)")
    perform_click_pattern = re.compile(r"(?:this\.)?(?P<control>[A-Za-z_]\w*)\.PerformClick\s*\(")

    for _, line in active_lines(block):
        for match in event_handler_pattern.finditer(line):
            name = match.group("name")
            if name in method_names and name not in calls:
                calls.append(name)
        for match in perform_click_pattern.finditer(line):
            handler = click_handlers.get(match.group("control"))
            if handler and handler in method_names and handler not in calls:
                calls.append(handler)
        for match in generic_call_pattern.finditer(line):
            name = match.group("name")
            if name == block.name or name in ignored:
                continue
            if name in method_names and name not in calls:
                calls.append(name)
    return calls


def trace_method_calls(
    method_name: str,
    methods: dict[str, MethodBlock],
    click_handlers: dict[str, str],
    chain: list[str] | None = None,
    visited: set[str] | None = None,
    depth: int = 0,
    max_depth: int = 8,
) -> list[ServiceCall]:
    if chain is None:
        chain = [method_name]
    if visited is None:
        visited = set()
    if depth > max_depth or method_name in visited:
        return []
    block = methods.get(method_name)
    if not block:
        return []

    visited = set(visited)
    visited.add(method_name)
    calls = extract_service_calls(active_lines(block), chain, "active")
    calls.extend(extract_service_calls(commented_lines(block), chain, "commented-out"))

    for helper in local_method_calls(block, set(methods), click_handlers):
        calls.extend(trace_method_calls(helper, methods, click_handlers, chain + [helper], visited, depth + 1, max_depth))
    return calls


def downstream_evidence(project: Path, interface: str, method: str, limit: int, sql_window: int) -> list[str]:
    qualified_symbol = f"{interface}::{method}"
    qualified_hits = [
        hit
        for hit in parse_query_hits(codegraph_json(project, "query", qualified_symbol, limit))
        if hit.name == method
    ]
    bare_hits = [hit for hit in parse_query_hits(codegraph_json(project, "query", method, limit)) if hit.name == method]
    query_hits = qualified_hits or bare_hits
    evidence: list[str] = []

    iface_contracts = [
        hit
        for hit in query_hits
        if hit.qualified_name == qualified_symbol or hit.qualified_name.startswith(f"{interface}::{method}")
    ]
    contract_root = iface_contracts[0].file_path.split("/", 1)[0] if iface_contracts else None
    callee_symbol = iface_contracts[0].qualified_name if iface_contracts else qualified_symbol
    callees = parse_relation_hits(codegraph_json(project, "callees", callee_symbol, limit), "callees")

    def same_contract_root(hit: SymbolHit) -> bool:
        return contract_root is None or hit.file_path.split("/", 1)[0] == contract_root

    contracts = iface_contracts
    implementations: list[SymbolHit] = []
    if iface_contracts:
        implementations = [
            hit for hit in callees
            if hit.name == method
            and not re.search(r"\.UI\.|/UI/|Contract", hit.file_path.replace("\\", "/"), re.IGNORECASE)
        ]
        if not implementations:
            implementations = [
                hit for hit in query_hits
                if same_contract_root(hit)
                and hit not in contracts
                and not re.search(r"\.UI\.|/UI/", hit.file_path.replace("\\", "/"), re.IGNORECASE)
            ]
    ambiguous_contracts = sorted({
        hit.qualified_name
        for hit in bare_hits
        if hit.qualified_name != qualified_symbol
        and hit.qualified_name.startswith("I")
        and "::" in hit.qualified_name
    })
    if not iface_contracts and ambiguous_contracts:
        evidence.append(
            "ambiguous-downstream: "
            + ", ".join(ambiguous_contracts[:5])
            + (" ..." if len(ambiguous_contracts) > 5 else "")
        )
    if contracts:
        evidence.extend(f"contract: {hit.display}" for hit in contracts[:2])
    else:
        evidence.append(f"contract: need-confirm ({qualified_symbol} not found)")
    if implementations:
        evidence.extend(f"implementation: {hit.display}" for hit in implementations[:3])
    else:
        evidence.append("implementation: need-confirm")

    allowed_roots = {item for item in (contract_root, "GeneralData", "SMT", "AMS", "BPS", "VPS") if item}
    callee_added = 0
    for hit in callees[:12]:
        hit_root = hit.file_path.split("/", 1)[0]
        if allowed_roots and hit_root not in allowed_roots:
            continue
        if re.search(r"BLL|DAL|SQL|Data|Procedure|Mapper", hit.file_path, re.IGNORECASE):
            evidence.append(f"callee: {hit.display}")
            callee_added += 1
            if callee_added >= 6:
                break

    sql_seen = 0
    sql_pattern = re.compile(
        r"\b(DAL|dal|GetSqlStringCommand|ExecuteReader|ExecuteNonQuery|ExecuteScalar|StoredProcedure|Procedure|new\s+\w*DAL)\b"
        r"|@?\"[^\"]*\b(SELECT|UPDATE|INSERT|DELETE)\b",
        re.IGNORECASE,
    )
    for hit in implementations[:2]:
        for raw in read_window(project, hit.file_path, hit.start_line, sql_window):
            if sql_pattern.search(raw):
                evidence.append(f"sql/dal-window: {hit.file_path}:{raw.strip()}")
                sql_seen += 1
                if sql_seen >= 5:
                    break
        if sql_seen >= 5:
            break
    if sql_seen == 0:
        evidence.append("sql/dal-window: need-confirm")

    compact: list[str] = []
    seen: set[str] = set()
    for item in evidence:
        if item not in seen:
            compact.append(item)
            seen.add(item)
    return compact[:12]


def parse_csharp_method_signature(project: Path, impl_hit: SymbolHit) -> dict[str, Any]:
    """Extract method signature info from C# BLL implementation to identify entity/DTO parameters."""
    # Read up to 25 lines to capture multi-line signatures (window around start_line)
    window = read_window(project, impl_hit.file_path, impl_hit.start_line, 25)
    if not window:
        return {"params": [], "return_type": "", "raw_signature": ""}

    raw_lines = "\n".join(window)
    # Multi-line signature: match from method start to closing paren, allowing newlines
    sig_match = re.search(
        r"(?:public|private|protected|internal|static|virtual|override)\s+"
        r"(?:[\w<>\*\[\],?!]+\s+)+"
        r"(?P<name>[A-Za-z_]\w*)\s*"
        r"\((?P<params>.*?)\)",
        raw_lines,
        re.DOTALL,
    )
    if not sig_match:
        return {"params": [], "return_type": "", "raw_signature": ""}

    params_raw = sig_match.group("params")
    # Normalize multi-line params to single line for parsing
    params_normalized = re.sub(r"\s+", " ", params_raw).strip()
    # Strip leading line numbers from params (e.g., "166: ref List<...>")
    params_normalized = re.sub(r"\b\d+:\s*", "", params_normalized)
    # Split by comma, but not inside generic brackets like List<X>
    param_parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in params_normalized:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            param_parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        param_parts.append("".join(current).strip())
    param_pattern = re.compile(
        r"^(?:(?P<modifier>ref|out|params)\s+)?"
        r"(?P<type>[\w<>\[\],.?]+)\s+"
        r"(?P<name>[A-Za-z_]\w*)"
    )
    params = []
    for part in param_parts:
        part = part.strip()
        if not part:
            continue
        m = param_pattern.match(part)
        if not m:
            continue
        param_type = m.group("type").strip()
        param_name = m.group("name").strip()
        modifier = m.group("modifier") or ""
        is_ref = modifier in ("ref", "out")
        is_entity = any(
            kw in param_type
            for kw in ["Entity", "DTO", "VO", "BizData", "Model", "Req", "Rsp"]
        )
        params.append({
            "name": param_name,
            "type": param_type,
            "is_ref": is_ref,
            "is_entity": is_entity,
        })
    return {
        "params": params,
        "return_type": "",
        "raw_signature": sig_match.group(0),
    }


def _is_bll_path(file_path: str) -> bool:
    """Check if a file path is in a BLL directory (handles both / and . separators."""
    lower = file_path.lower()
    return bool(re.search(r"[/.]bll[/.]|[/.]bll$", lower))


def find_bll_implementation(
    project: Path, contract_name: str, method_name: str, limit: int
) -> SymbolHit | None:
    """Find BLL implementation for a Contract method.

    Strategy: CodeGraph query by method name, then filter results to BLL file paths.
    This works because CodeGraph indexes all method definitions, and BLL implementations
    share the same method name as the Contract interface.
    """
    # Search all symbols with the method name; filter for BLL files
    all_hits = parse_query_hits(codegraph_json(project, "query", method_name, limit))
    for hit in all_hits:
        if _is_bll_path(hit.file_path):
            return hit
    return None


def contract_field_usage_evidence(
    project: Path, interface: str, method: str, limit: int, sql_window: int,
    bll_hit: SymbolHit | None = None,
) -> dict[str, Any]:
    """
    Verify which fields of C# Contract Entity/DTO parameters are actually used in BLL.
    Returns a dict with:
      - method: qualified method name
      - bll_impl: path:line of BLL implementation
      - fields: list of {field_name, type, param_name, is_ref, usage: used|output-only|unused|unconfirmed|indirect}
      - bll_field_refs: dict mapping field name -> list of path:line references found in BLL body
    """
    qualified_symbol = f"{interface}::{method}"

    if bll_hit is not None:
        impl_hit = bll_hit
        impl_path = impl_hit.file_path.replace("\\", "/")
        impl_anchor = f"{impl_path}:{impl_hit.start_line}" if impl_hit.start_line else impl_path
        sig_info = parse_csharp_method_signature(project, impl_hit)
        bll_window = read_window(project, impl_hit.file_path, impl_hit.start_line, sql_window)
        bll_text = "\n".join(bll_window) if bll_window else ""

        fields: list[dict[str, Any]] = []
        bll_field_refs: dict[str, list[str]] = {}

        for param in sig_info["params"]:
            param_name = param["name"]
            param_type = param["type"]
            is_ref = param["is_ref"]
            is_entity = param["is_entity"]

            if not is_entity:
                continue

            # Scan BLL body for field reads on this param
            param_field_count = 0
            pattern = re.compile(r"\b" + re.escape(param_name) + r"\.\s*(?P<field>[A-Za-z_]\w*)")
            for m in pattern.finditer(bll_text):
                field = m.group("field")
                line_no = bll_text[: m.start()].count("\n") + (impl_hit.start_line or 1) - sql_window
                line_no = max(1, line_no)
                bll_field_refs.setdefault(f"{param_name}.{field}", []).append(f"{impl_path}:{line_no}")
                param_field_count += 1

            for field_key, evidence_list in bll_field_refs.items():
                if not field_key.startswith(f"{param_name}."):
                    continue
                field = field_key.split(".", 1)[1]
                fields.append({
                    "field_name": field,
                    "param_name": param_name,
                    "param_type": param_type,
                    "is_ref": is_ref,
                    "usage": "used",
                    "evidence": evidence_list,
                })

            if is_ref and param_field_count == 0:
                # ref/out param with NO field reads — pure output parameter
                fields.append({
                    "field_name": "(entire-list-as-output)",
                    "param_name": param_name,
                    "param_type": param_type,
                    "is_ref": True,
                    "usage": "output-only",
                    "evidence": [impl_anchor],
                })

        return {
            "method": qualified_symbol,
            "bll_impl": impl_anchor,
            "contract_sig": sig_info["raw_signature"],
            "fields": fields,
            "bll_field_refs": bll_field_refs,
            "status": "confirmed" if fields else "need-confirm",
        }

    # Fallback: auto-find BLL implementation
    iface_hits = [
        hit
        for hit in parse_query_hits(codegraph_json(project, "query", qualified_symbol, limit))
        if hit.name == method
    ]
    if not iface_hits:
        iface_hits = [
            hit for hit in parse_query_hits(codegraph_json(project, "query", method, limit))
            if hit.name == method
            and "Contract" in hit.file_path.replace("\\", "/")
        ]
    iface_hit = iface_hits[0] if iface_hits else None
    contract_root = iface_hit.file_path.split("/", 1)[0] if iface_hit else None

    callee_symbol = qualified_symbol
    callees_data = parse_relation_hits(codegraph_json(project, "callees", callee_symbol, limit), "callees")

    implementations: list[SymbolHit] = []
    if contract_root:
        for hit in callees_data:
            hit_root = hit.file_path.split("/", 1)[0]
            if hit_root != contract_root:
                continue
            hit_path_lower = hit.file_path.replace("\\", "/").lower()
            if re.search(r"/bll/|/bll\.", hit_path_lower) and hit.name == method:
                implementations.append(hit)
                break

    if not implementations and iface_hit:
        iface_class_callees = parse_relation_hits(
            codegraph_json(project, "callees", iface_hit.qualified_name, limit), "callees"
        )
        for hit in iface_class_callees:
            hit_path_lower = hit.file_path.replace("\\", "/").lower()
            if re.search(r"/bll/|/bll\.", hit_path_lower) and hit.name == method:
                implementations.append(hit)
                break

    if not implementations:
        search_hits = parse_query_hits(codegraph_json(project, "query", method, limit))
        for hit in search_hits:
            hit_path_lower = hit.file_path.replace("\\", "/").lower()
            if re.search(r"/bll/|/bll\.", hit_path_lower):
                implementations.append(hit)
                break

    if not implementations:
        return {
            "method": qualified_symbol,
            "bll_impl": "not-found",
            "fields": [],
            "bll_field_refs": {},
            "status": "need-confirm",
        }

    impl_hit = implementations[0]
    impl_path = impl_hit.file_path.replace("\\", "/")
    impl_anchor = f"{impl_path}:{impl_hit.start_line}" if impl_hit.start_line else impl_path

    sig_info = parse_csharp_method_signature(project, impl_hit)

    bll_window = read_window(project, impl_hit.file_path, impl_hit.start_line, sql_window)
    bll_text = "\n".join(bll_window) if bll_window else ""

    bll_field_refs: dict[str, list[str]] = {}
    for param in sig_info["params"]:
        if not param["is_entity"]:
            continue
        param_name = param["name"]
        pattern = re.compile(r"\b" + re.escape(param_name) + r"\.\s*(?P<field>[A-Za-z_]\w*)")
        for m in pattern.finditer(bll_text):
            field = m.group("field")
            line_no = bll_text[: m.start()].count("\n") + (impl_hit.start_line or 1) - sql_window
            line_no = max(1, line_no)
            bll_field_refs.setdefault(f"{param_name}.{field}", []).append(f"{impl_path}:{line_no}")

    fields: list[dict[str, Any]] = []
    for param in sig_info["params"]:
        if not param["is_entity"]:
            continue
        param_name = param["name"]
        param_type = param["type"]
        is_ref = param["is_ref"]

        for field_key, evidence_list in bll_field_refs.items():
            if not field_key.startswith(f"{param_name}."):
                continue
            field = field_key.split(".", 1)[1]
            usage = "output-only" if is_ref else "used"
            fields.append({
                "field_name": field,
                "param_name": param_name,
                "param_type": param_type,
                "is_ref": is_ref,
                "usage": usage,
                "evidence": evidence_list,
            })

        if is_ref:
            fields.append({
                "field_name": "(entire-list-as-output)",
                "param_name": param_name,
                "param_type": param_type,
                "is_ref": True,
                "usage": "output-only",
                "evidence": [impl_anchor],
            })

    return {
        "method": qualified_symbol,
        "bll_impl": impl_anchor,
        "contract_sig": sig_info["raw_signature"],
        "fields": fields,
        "bll_field_refs": bll_field_refs,
        "status": "confirmed" if fields else "need-confirm",
    }


def format_contract_field_usage_report(field_usage: dict[str, Any]) -> str:
    """Format contract field usage evidence as markdown lines."""
    lines: list[str] = []
    lines.append(f"## Contract Field Usage: {field_usage.get('method', 'unknown')}")
    lines.append("")
    lines.append(f"- BLL implementation: {field_usage.get('bll_impl', 'not-found')}")
    if field_usage.get("contract_sig"):
        lines.append(f"- Contract signature: `{field_usage['contract_sig']}`")
    lines.append("")

    fields = field_usage.get("fields", [])
    if not fields:
        lines.append("- No entity/DTO fields confirmed in BLL body.")
        lines.append("")
        return "\n".join(lines)

    lines.append("| C# param | field | ref/out | usage | BLL evidence |")
    lines.append("|---|---|---|---|---|")
    for f in fields:
        field_name = f.get("field_name", "?")
        param_name = f.get("param_name", "?")
        ref_out = "ref/out" if f.get("is_ref") else "in"
        usage = f.get("usage", "unconfirmed")
        evidence_list = f.get("evidence", [])
        evidence_str = ", ".join(evidence_list[:2]) if evidence_list else "?"
        lines.append(
            f"| `{param_name}` | `{field_name}` | {ref_out} | {usage} | {evidence_str} |"
        )
    lines.append("")

    confirmed = sum(1 for f in fields if f["usage"] == "used")
    output_only = sum(1 for f in fields if f["usage"] == "output-only")
    lines.append(f"- Fields used by BLL (input): {confirmed}")
    lines.append(f"- Fields output-only (ref/out): {output_only}")
    lines.append("")
    return "\n".join(lines)


def normalize_display_name(value: str, control: str = "") -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    cleaned = re.sub(r"\s*[（(]&[A-Za-z0-9][)）]\s*$", "", cleaned).strip()
    cleaned = re.sub(r"\s*[（(]\s*(?:Ctrl|ALT|Shift)\s*\+\s*[A-Za-z0-9]+\s*[)）]\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    if control and cleaned == control:
        return ""
    if re.fullmatch(r"[A-Za-z_]\w*\d*", cleaned or ""):
        return ""
    return cleaned


def parse_designer_form_title(designer_path: Path, class_name: str) -> str:
    text = read_text_compat(designer_path)
    matches = re.findall(r'this\.Text\s*=\s*"(?P<value>(?:\\.|[^"\\])*)"', text)
    for value in reversed(matches):
        title = normalize_display_name(decode_csharp_string(value), "this")
        if title:
            return title
    return class_name


def trigger_priority(event: UiEventBinding, fallback: bool) -> int:
    if fallback:
        return 9
    if event.event in {"ItemClick", "Click"}:
        return 0
    if event.event in {"Load", "FormShown"}:
        return 4
    if event.event in {"FormClosing", "Closing"}:
        return 5
    if event.event in {"MouseDoubleClick", "DoubleClick"}:
        return 3
    if event.event in {"FocusedRowChanged", "SelectedPageChanged", "RowCellStyle", "MouseDown"}:
        return 6
    return 2


def build_ui_trigger_evidence(csharp_root: Path, value: str, page_order: int, limit: int) -> tuple[list[UiTriggerEvidence], list[str]]:
    class_name, designer_path, code_path, _, source = resolve_ui_page_files(csharp_root, value, limit)
    if not designer_path or not code_path:
        return [], [f"{value}: Designer or code-behind not found (source={source})."]

    events = parse_designer_events(designer_path, class_name)
    methods = parse_csharp_methods(code_path)
    click_handlers = {
        event.control: event.handler
        for event in events
        if event.event in {"ItemClick", "Click"} and event.handler in methods
    }
    form_title = parse_designer_form_title(designer_path, class_name)
    triggers: list[UiTriggerEvidence] = []

    for event in events:
        calls = trace_method_calls(event.handler, methods, click_handlers)
        active_calls = [call for call in calls if call.status == "active"]
        service_methods = {call.method for call in active_calls}
        display_name = normalize_display_name(event.caption, event.control)
        if not display_name and event.control == "this":
            display_name = form_title
        chain_summary = "; ".join(
            f"{' -> '.join(call.chain)} -> {call.interface}.{call.method}:{call.line}"
            for call in active_calls[:4]
        )
        if len(active_calls) > 4:
            chain_summary += f"; ... +{len(active_calls) - 4} more"
        # Build contract evidence: interface.method + first call chain
        contract_ev = ""
        if active_calls:
            first = active_calls[0]
            contract_ev = f"{first.interface}.{first.method}"
        triggers.append(UiTriggerEvidence(
            page_order=page_order,
            page_class=class_name,
            designer_path=designer_path,
            code_path=code_path,
            control=event.control,
            raw_display=event.caption,
            display_name=display_name,
            event=event.event,
            handler=event.handler,
            designer_line=event.designer_line,
            service_methods=service_methods,
            chain_summary=chain_summary or "none",
            priority=trigger_priority(event, False),
            contract_evidence=contract_ev or "证据不足",
        ))

    if form_title:
        triggers.append(UiTriggerEvidence(
            page_order=page_order,
            page_class=class_name,
            designer_path=designer_path,
            code_path=code_path,
            control="this",
            raw_display=form_title,
            display_name=form_title,
            event="Form.Text",
            handler="Form.Text",
            designer_line=1,
            service_methods=set(),
            chain_summary="window/dialog fallback",
            priority=trigger_priority(UiEventBinding("this", form_title, "Form.Text", "Form.Text", 1), True),
            fallback=True,
        ))
    return triggers, []


def decode_java_string(value: str) -> str:
    return (
        value.replace(r"\"", '"')
        .replace(r"\\", "\\")
        .replace(r"\r", " ")
        .replace(r"\n", " ")
        .strip()
    )


def encode_java_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', r"\"")


def java_annotation_value(annotation_text: str, name: str) -> str:
    match = re.search(rf"\b{name}\s*=\s*\"(?P<value>(?:\\.|[^\"\\])*)\"", annotation_text, re.DOTALL)
    return decode_java_string(match.group("value")) if match else ""


def find_operation_block(lines: list[str], method_index: int) -> tuple[int | None, int | None, str]:
    search_start = max(0, method_index - 80)
    for index in range(method_index - 1, search_start - 1, -1):
        if "@Operation" not in lines[index]:
            continue
        depth = 0
        end = index
        for end in range(index, method_index):
            segment = lines[end]
            depth += segment.count("(") - segment.count(")")
            if depth <= 0 and ")" in segment:
                break
        return index + 1, end + 1, "\n".join(lines[index:end + 1])
    return None, None, ""


def find_method_javadoc(lines: list[str], method_index: int) -> str:
    index = method_index - 1
    while index >= 0:
        stripped = lines[index].strip()
        if not stripped:
            index -= 1
            continue
        if stripped.startswith("@"):
            index -= 1
            continue

        # Skip continuation lines from multi-line annotations immediately above the method.
        probe = index
        found_annotation_start = False
        while probe >= 0:
            current = lines[probe].strip()
            if not current:
                break
            if current.startswith("@"):
                found_annotation_start = True
                break
            if current.endswith(";") or current.endswith("{") or current.endswith("}"):
                break
            probe -= 1
        if found_annotation_start:
            index = probe - 1
            continue
        break

    if index < 0 or lines[index].strip() != "*/":
        return ""
    end = index
    start = index
    while start >= 0 and "/**" not in lines[start]:
        start -= 1
    if start < 0:
        return ""
    body = "\n".join(lines[start:end + 1])
    body = re.sub(r"^.*?/\*\*", "", body, flags=re.DOTALL)
    body = re.sub(r"\*/\s*$", "", body)
    cleaned: list[str] = []
    for line in body.splitlines():
        item = re.sub(r"^\s*\*\s?", "", line).strip()
        if item:
            cleaned.append(item)
    return " ".join(cleaned)


def find_mapping_path(lines: list[str], method_index: int) -> str:
    annotation_text = "\n".join(lines[max(0, method_index - 40):method_index])
    matches = list(re.finditer(
        r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*(?:\(\s*(?:value\s*=\s*)?\"(?P<path>[^\"]+)\")?",
        annotation_text,
    ))
    if not matches:
        return ""
    match = matches[-1]
    path = match.group("path")
    return path or f"@{match.group(1)}"


def java_service_calls(block_lines: list[tuple[int, str]]) -> set[str]:
    methods: set[str] = set()
    pattern = re.compile(r"\b[A-Za-z_]\w*Service\.(?P<method>[A-Za-z_]\w*)\s*\(")
    for _, line in block_lines:
        for match in pattern.finditer(strip_line_comment(line)):
            methods.add(match.group("method"))
    return methods


def parse_java_controller_methods(java_path: Path) -> list[JavaOperationMethod]:
    lines = read_text_compat(java_path).splitlines()
    method_pattern = re.compile(
        r"^\s*public\s+(?:static\s+)?(?:[\w<>\[\],.?]+\s+)+(?P<name>[A-Za-z_]\w*)\s*\("
    )
    methods: list[JavaOperationMethod] = []
    index = 0
    while index < len(lines):
        match = method_pattern.search(lines[index])
        if not match:
            index += 1
            continue
        name = match.group("name")
        open_index = index
        while open_index < len(lines) and "{" not in strip_line_comment(lines[open_index]):
            open_index += 1
        if open_index >= len(lines):
            index += 1
            continue
        depth = 0
        end_index = open_index
        for end_index in range(open_index, len(lines)):
            depth += brace_delta(lines[end_index])
            if depth == 0:
                break
        block_lines = [(line_no, lines[line_no - 1]) for line_no in range(index + 1, end_index + 2)]
        operation_start, operation_end, operation_text = find_operation_block(lines, index)
        indent_match = re.match(r"^(\s*)", lines[index])
        methods.append(JavaOperationMethod(
            name=name,
            start_line=index + 1,
            end_line=end_index + 1,
            operation_start_line=operation_start,
            operation_end_line=operation_end,
            operation_text=operation_text,
            current_summary=java_annotation_value(operation_text, "summary"),
            current_description=java_annotation_value(operation_text, "description"),
            mapping_path=find_mapping_path(lines, index),
            javadoc=find_method_javadoc(lines, index),
            service_methods=java_service_calls(block_lines),
            indent=indent_match.group(1) if indent_match else "    ",
        ))
        index = end_index + 1
    return methods


def identifier_tokens(value: str) -> set[str]:
    pieces = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value or "")
    pieces = re.sub(r"[^A-Za-z0-9]+", " ", pieces).lower().split()
    aliases = {
        "cntr": "container",
        "cntrs": "container",
        "containers": "container",
        "voy": "voyage",
        "vpc": "vpc",
        "mft": "mft",
    }
    return {aliases.get(piece, piece) for piece in pieces if len(piece) > 1}


# Java method verb -> expected C# Caption keyword mapping for semantic guard
# Prevents matching a Java "save" method to a C# "检索" button, etc.
VERB_SEMANTIC_MAP: dict[str, set[str]] = {
    "query": {"查询", "检索", "查找", "搜索", "刷新", "load"},
    "save": {"提交", "保存", "确认", "保存并确认"},
    "update": {"修改", "编辑", "更新", "保存"},
    "delete": {"删除", "移除"},
    "get": {"查询", "获取", "加载"},
    "init": {"初始化", "加载", "load"},
    "print": {"打印"},
    "export": {"导出"},
    "import": {"导入"},
}


def check_verb_semantic_match(java_method_name: str, csharp_caption: str) -> bool:
    """Check if the Java method verb semantically matches the C# button Caption.

    Returns True if they are compatible or if no verb mapping exists.
    Returns False if there is a clear semantic conflict.
    """
    java_name_lower = java_method_name.lower()
    csharp_lower = csharp_caption.lower()
    for verb, expected_keywords in VERB_SEMANTIC_MAP.items():
        if java_name_lower.startswith(verb):
            # Check if ANY expected keyword appears in the C# caption
            if not any(kw in csharp_lower for kw in expected_keywords):
                return False
    return True


def trigger_evidence_text(csharp_root: Path, trigger: UiTriggerEvidence | None) -> str:
    if trigger is None:
        return "not-found"
    anchor = f"{project_relative(csharp_root, trigger.designer_path)}:{trigger.designer_line}"
    return (
        f"{trigger.page_class}.{trigger.control} / {trigger.display_name} / "
        f"{trigger.handler} / {anchor}"
    )


def choose_trigger_for_method(
    method: JavaOperationMethod,
    triggers: list[UiTriggerEvidence],
) -> tuple[UiTriggerEvidence | None, str, str, int]:
    java_text = " ".join([
        method.name,
        method.current_summary,
        method.current_description,
        method.javadoc,
        method.mapping_path,
        " ".join(sorted(method.service_methods)),
    ])
    java_text_lower = java_text.lower()

    # Phase 1: explicit handler match (handler name appears in Java docs/description)
    explicit = [trigger for trigger in triggers if trigger.handler != "Form.Text" and trigger.handler in java_text]
    if explicit:
        explicit.sort(key=lambda item: (item.page_order, item.priority, item.designer_line))
        candidate = explicit[0]
        if not check_verb_semantic_match(method.name, candidate.display_name):
            return candidate, "need-confirm", "semantic-conflict", len(explicit)
        return candidate, "high", "explicit-handler", len(explicit)

    # Phase 2: display name match (C# Caption appears verbatim in Java text)
    display_matches = [
        trigger for trigger in triggers
        if trigger.display_name and not trigger.fallback and trigger.display_name in java_text
    ]
    if display_matches:
        display_matches.sort(key=lambda item: (item.priority, item.page_order, item.designer_line))
        if len(display_matches) > 1:
            return display_matches[0], "need-confirm", "multiple-display-candidates", len(display_matches)
        candidate = display_matches[0]
        if not check_verb_semantic_match(method.name, candidate.display_name):
            return candidate, "need-confirm", "semantic-conflict", len(display_matches)
        return candidate, "high", "display-name", len(display_matches)

    # Phase 3: service-method token overlap (fallback -- low confidence)
    java_tokens = set()
    for item in [method.name, *method.service_methods]:
        java_tokens.update(identifier_tokens(item))
    service_matches: list[tuple[int, UiTriggerEvidence]] = []
    for trigger in triggers:
        if trigger.fallback or not trigger.service_methods:
            continue
        trigger_tokens: set[str] = set()
        for service_method in trigger.service_methods:
            trigger_tokens.update(identifier_tokens(service_method))
        overlap = len(java_tokens & trigger_tokens)
        if overlap >= 2:
            service_matches.append((overlap, trigger))
    if service_matches:
        service_matches.sort(key=lambda item: (-item[0], item[1].priority, item[1].page_order, item[1].designer_line))
        best_score = service_matches[0][0]
        best = [item for score, item in service_matches if score == best_score]
        if len(best) == 1:
            candidate = best[0]
            if not check_verb_semantic_match(method.name, candidate.display_name):
                return candidate, "need-confirm", "semantic-conflict", len(service_matches)
            return candidate, "low", "service-token-back-reference", len(service_matches)
        return best[0], "need-confirm", "multiple-service-candidates", len(best)

    # Phase 4: BLOCK fallback to Form.Text / window title for operation summary.
    # These always produce wrong @Operation(summary) mappings because they match
    # the page title instead of the actual button Caption.
    return None, "need-confirm", "no-csharp-display-evidence", 0


def recommended_description(method: JavaOperationMethod, trigger: UiTriggerEvidence | None) -> str:
    """Build structured '页面按钮索引卡' description for @Operation.

    Format: C#页面: <page>; 控件: <ctrl>; Caption: <caption>; 事件: <handler>;
            Contract: <contract>; 边界: <boundary>
    """
    if trigger is None:
        return method.current_description

    # Determine compatibility entry marker
    compat_marker = ""
    if method.current_description and "兼容入口" in method.current_description:
        compat_marker = "兼容入口: true; "

    # Boundary: derive from javadoc or method name semantics
    boundary = ""
    if method.javadoc:
        # Use javadoc as boundary hint (first meaningful sentence)
        boundary = method.javadoc.strip().split("。")[0].split("。")[0]
        if len(boundary) > 40:
            boundary = boundary[:40] + "..."
    if not boundary:
        # Derive from method name
        verb_map = {
            "query": "查询候选数据",
            "save": "保存并写库",
            "get": "获取数据",
            "init": "初始化页面",
            "delete": "删除数据",
            "update": "更新数据",
            "export": "导出数据",
            "import": "导入数据",
            "print": "获取打印内容",
        }
        for verb, desc in verb_map.items():
            if method.name.lower().startswith(verb):
                boundary = desc
                break
        if not boundary:
            boundary = f"接口: {method.name}"

    # Contract evidence: extract clean "接口.方法" from chain_summary
    # chain_summary format: "handler -> iface.method:line" or "handler -> iface.method:line; ... +N more"
    contract = "证据不足"
    if trigger.chain_summary and trigger.chain_summary != "none":
        # Extract the first contract call (after " -> ")
        parts = trigger.chain_summary.split(" -> ")
        if len(parts) >= 2:
            contract_part = parts[-1]  # Last segment: "iface.method:line" or "iface.method:line; ..."
            # Remove line number suffix
            contract_part = re.sub(r":\d+.*", "", contract_part).strip()
            if contract_part:
                contract = contract_part

    # Control / event fields
    if trigger.handler == "Form.Text":
        ctrl = "窗口事件"
        event = trigger.handler
    else:
        ctrl = trigger.control
        event = trigger.handler

    caption = trigger.display_name

    # If current description already follows structured format with all fields, keep it
    current = method.current_description.strip()
    if current.startswith("C#页面:") and current.count("; ") >= 5:
        return current

    # Build the structured description
    fields = [
        f"C#页面: {trigger.page_class}",
        f"控件: {ctrl}",
        f"Caption: {caption}",
        f"事件: {event}",
        f"Contract: {contract}",
        f"边界: {boundary}",
    ]

    # Compat entry: prepend compatibility markers + primary route
    is_compat = method.current_description and "兼容入口" in method.current_description
    if is_compat:
        primary_route = method.mapping_path or "证据不足"
        fields = [f"兼容入口: true", f"主入口: {primary_route}"] + fields

    return "; ".join(fields)


def build_operation_recommendations(
    java_methods: list[JavaOperationMethod],
    triggers: list[UiTriggerEvidence],
) -> list[OperationRecommendation]:
    recommendations: list[OperationRecommendation] = []
    for method in java_methods:
        trigger, confidence, reason, candidate_count = choose_trigger_for_method(method, triggers)
        summary = trigger.display_name if trigger else ""
        description = recommended_description(method, trigger)
        patchable = (
            trigger is not None
            and confidence in {"high", "medium"}
            and method.operation_start_line is not None
            and method.operation_end_line is not None
            and summary
            and reason not in {"multiple-service-candidates"}
        )
        changed = summary != method.current_summary or description != method.current_description
        patch_action = "update-operation" if patchable and changed else "none"
        if confidence in {"low", "need-confirm"}:
            patch_action = "evidence-only"
        recommendations.append(OperationRecommendation(
            method=method,
            recommended_summary=summary or "need-confirm",
            recommended_description=description,
            trigger=trigger,
            confidence=confidence if candidate_count <= 1 else f"{confidence}; multiple-candidate={candidate_count}",
            patch_action=patch_action,
            reason=reason,
            candidate_count=candidate_count,
        ))
    return recommendations


def make_operation_annotation(method: JavaOperationMethod, recommendation: OperationRecommendation) -> str:
    summary = encode_java_string(recommendation.recommended_summary)
    description = encode_java_string(recommendation.recommended_description)
    indent = method.indent
    # Multi-line format for Swagger readability
    return (
        f'{indent}@Operation(\n'
        f'{indent}    summary = "{summary}",\n'
        f'{indent}    description = "{description}"\n'
        f'{indent})'
    )


def operation_patch(java_path: Path, recommendations: list[OperationRecommendation]) -> str:
    original_lines = read_text_compat(java_path).splitlines()
    modified_lines = original_lines[:]
    patchable = [
        rec for rec in recommendations
        if rec.patch_action == "update-operation"
        and rec.method.operation_start_line is not None
        and rec.method.operation_end_line is not None
    ]
    for rec in sorted(patchable, key=lambda item: item.method.operation_start_line or 0, reverse=True):
        start = (rec.method.operation_start_line or 1) - 1
        end = rec.method.operation_end_line or rec.method.operation_start_line or 1
        modified_lines[start:end] = [make_operation_annotation(rec.method, rec)]
    if original_lines == modified_lines:
        return ""
    from_file = java_path.as_posix()
    to_file = java_path.as_posix()
    return "".join(difflib.unified_diff(
        [line + "\n" for line in original_lines],
        [line + "\n" for line in modified_lines],
        fromfile=from_file,
        tofile=to_file,
    ))


def resolve_java_controller_file(java_root: Path, java_input: str | None, limit: int) -> tuple[Path | None, str, list[SymbolHit]]:
    if not java_input:
        return None, "not-found", []
    direct = resolve_existing_file(java_root, java_input)
    if direct:
        return direct, "explicit-user-input", []
    hits = parse_query_hits(codegraph_json(java_root, "query", java_input, limit))
    java_file_hits = [hit for hit in hits if hit.file_path.endswith(".java")]
    if java_file_hits:
        path = java_root / java_file_hits[0].file_path
        if path.exists():
            return path.resolve(), "codegraph", hits
    return None, "not-found", hits


def build_controller_operation_summary_pack(args: argparse.Namespace) -> str:
    csharp_root = Path(args.csharp_root)
    java_root = Path(args.java_root)
    java_path, java_source, java_hits = resolve_java_controller_file(java_root, args.java_input, args.limit)
    csharp_inputs = args.csharp_inputs
    out: list[str] = ["# Controller Operation Summary Evidence", ""]
    out.append(f"- mode: {args.mode}")
    out.append(f"- java-input: {args.java_input or 'not-found'}")
    out.append(f"- java-source: {java_source}")
    out.append(f"- java-controller: {java_path.as_posix() if java_path else 'not-found'}")
    out.append(f"- csharp-root: {csharp_root.as_posix()}")
    out.append(f"- csharp-pages: {', '.join(csharp_inputs) if csharp_inputs else 'not-found'}")
    out.append("")

    blockers: list[str] = []
    if java_path is None:
        blockers.append("Java Controller file was not found; provide --java-location as an existing .java file or an indexed Controller symbol.")
    if not csharp_inputs:
        blockers.append("At least one --csharp-location Designer/page path is required.")
    if blockers:
        out.append("## Open Questions")
        out.append("")
        for blocker in blockers:
            out.append(f"- {blocker}")
        if java_hits:
            out.extend(md_list("Java CodeGraph Hits", [hit.display for hit in java_hits[:10]]))
        return "\n".join(out)

    triggers: list[UiTriggerEvidence] = []
    csharp_blockers: list[str] = []
    for page_order, csharp_input in enumerate(csharp_inputs, start=1):
        page_triggers, page_blockers = build_ui_trigger_evidence(csharp_root, csharp_input, page_order, args.limit)
        triggers.extend(page_triggers)
        csharp_blockers.extend(page_blockers)

    java_methods = parse_java_controller_methods(java_path)
    recommendations = build_operation_recommendations(java_methods, triggers)
    patch_text = operation_patch(java_path, recommendations) if args.emit_operation_patch or args.patch_out else ""
    if args.patch_out:
        patch_path = Path(args.patch_out)
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(patch_text, encoding="utf-8")

    low_confidence = sum(1 for rec in recommendations if rec.confidence.startswith("low") or rec.confidence.startswith("need-confirm"))
    patchable = sum(1 for rec in recommendations if rec.patch_action == "update-operation")

    out.append("## Summary")
    out.append("")
    out.append(f"- java-methods: {len(java_methods)}")
    out.append(f"- csharp-display-candidates: {len(triggers)}")
    out.append(f"- low-confidence-rows: {low_confidence}")
    out.append(f"- patchable-rows: {patchable}")
    out.append(f"- patch-mode: {'stdout' if args.emit_operation_patch else (args.patch_out or 'none')}")
    out.append("")

    out.append("## Mapping Table")
    out.append("")
    out.append("| Java method | mapping path | current summary | recommended summary | C# display evidence | confidence | patch action |")
    out.append("|---|---|---|---|---|---|---|")
    for rec in recommendations:
        current = (rec.method.current_summary or "not-found").replace("|", "/")
        recommended = rec.recommended_summary.replace("|", "/")
        evidence = trigger_evidence_text(csharp_root, rec.trigger).replace("|", "/")
        mapping = (rec.method.mapping_path or "not-found").replace("|", "/")
        out.append(
            f"| `{rec.method.name}` | `{mapping}` | {current} | {recommended} | "
            f"{evidence} | `{rec.confidence}; {rec.reason}` | `{rec.patch_action}` |"
        )
    out.append("")

    out.append("## C# Display Candidates")
    out.append("")
    if not triggers:
        out.append("- not-found")
    else:
        for trigger in triggers:
            if trigger.fallback:
                continue
            out.append(
                f"- {trigger.page_class}.{trigger.control} / {trigger.display_name} / "
                f"{trigger.event} / {trigger.handler} / "
                f"{project_relative(csharp_root, trigger.designer_path)}:{trigger.designer_line}"
            )
    out.append("")

    if csharp_blockers:
        out.append("## Open Questions")
        out.append("")
        for blocker in csharp_blockers:
            out.append(f"- {blocker}")
        out.append("")

    if args.emit_operation_patch:
        out.append("## Operation Patch")
        out.append("")
        if patch_text:
            out.append("```diff")
            out.extend(patch_text.splitlines())
            out.append("```")
        else:
            out.append("- no patchable summary changes")
        out.append("")
    if args.patch_out:
        out.append("## Patch Output")
        out.append("")
        out.append(f"- wrote patch file: {Path(args.patch_out).as_posix()}")
        out.append(f"- bytes: {len(patch_text.encode('utf-8'))}")
        out.append("")

    return "\n".join(out)


def build_ui_events_pack(args: argparse.Namespace) -> str:
    csharp_root = Path(args.csharp_root)
    class_name, designer_path, code_path, codegraph_hits, source = resolve_ui_page_files(csharp_root, args.csharp_input, args.limit)
    out: list[str] = []
    out.append(f"# UI Event Interface Evidence Pack: {class_name}")
    out.append("")
    out.append(f"- mode: {args.mode}")
    out.append(f"- csharp-root: {csharp_root.as_posix()}")
    out.append(f"- location-source: {source}")
    out.append(f"- designer: {project_relative(csharp_root, designer_path) if designer_path else 'not-found'}")
    out.append(f"- code-behind: {project_relative(csharp_root, code_path) if code_path else 'not-found'}")
    out.append("")

    if not designer_path or not code_path:
        out.append("## Open Questions")
        out.append("")
        out.append("- Designer file or code-behind file was not found; provide the exact WinForms page path.")
        out.append("")
        return "\n".join(out)

    events = parse_designer_events(designer_path, class_name)
    methods = parse_csharp_methods(code_path)
    click_handlers = {
        event.control: event.handler
        for event in events
        if event.event in {"ItemClick", "Click"} and event.handler in methods
    }

    event_calls: dict[int, list[ServiceCall]] = {}
    all_call_keys: set[str] = set()
    all_calls: list[ServiceCall] = []
    handler_missing = 0
    for index, event in enumerate(events, start=1):
        calls = trace_method_calls(event.handler, methods, click_handlers)
        deduped: list[ServiceCall] = []
        seen_for_event: set[str] = set()
        for call in calls:
            if call.key not in seen_for_event:
                deduped.append(call)
                seen_for_event.add(call.key)
            if call.key not in all_call_keys:
                all_calls.append(call)
                all_call_keys.add(call.key)
        event_calls[index] = deduped
        if event.handler not in methods:
            handler_missing += 1

    active_event_count = sum(1 for calls in event_calls.values() if any(call.status == "active" for call in calls))
    commented_only_count = sum(1 for calls in event_calls.values() if calls and not any(call.status == "active" for call in calls))
    no_interface_count = len(events) - active_event_count - commented_only_count

    out.append("## Summary")
    out.append("")
    out.append(f"- ui-event-bindings: {len(events)}")
    out.append(f"- active-interface-events: {active_event_count}")
    out.append(f"- commented-out-only-events: {commented_only_count}")
    out.append(f"- no-active-interface-events: {no_interface_count}")
    out.append(f"- missing-handlers: {handler_missing}")
    out.append("")

    out.extend(md_list("CodeGraph Page Hits", [hit.display for hit in codegraph_hits[:12]], empty="not-found-or-codegraph-unavailable"))

    out.append("## UI Event Interface Trace")
    out.append("")
    out.append("| # | control/caption | event | designer | handler | interface calls | status |")
    out.append("|---|---|---|---|---|---|---|")
    for index, event in enumerate(events, start=1):
        block = methods.get(event.handler)
        handler_anchor = f"{project_relative(csharp_root, code_path)}:{block.start_line}" if block else "handler-not-found"
        designer_anchor = f"{project_relative(csharp_root, designer_path)}:{event.designer_line}"
        calls = event_calls[index]
        active_calls = [call for call in calls if call.status == "active"]
        if active_calls:
            status = "active-interface"
        elif calls:
            status = "commented-out-only"
        elif block:
            status = "no-active-interface"
        else:
            status = "handler-not-found"
        if calls:
            call_parts = [
                f"{' -> '.join(call.chain)} -> {call.interface}.{call.method}:{call.line} [{call.status}]"
                for call in calls[:6]
            ]
            if len(calls) > 6:
                call_parts.append(f"... +{len(calls) - 6} more")
            call_summary = "; ".join(call_parts)
        else:
            call_summary = "none"
        caption = event.caption.replace("|", "/")
        out.append(
            f"| {index} | `{event.control}` / {caption} | `{event.event}` | "
            f"`{designer_anchor}` | `{handler_anchor}` `{event.handler}` | {call_summary} | `{status}` |"
        )
    out.append("")

    active_calls = [call for call in all_calls if call.status == "active"]
    inactive_calls = [call for call in all_calls if call.status != "active"]
    unique_active = sorted({(call.interface, call.method) for call in active_calls})
    downstream_cache = {
        f"{interface}.{method}": downstream_evidence(csharp_root, interface, method, args.limit, args.sql_window)
        for interface, method in unique_active
    }

    out.append("## Interface Downstream Evidence")
    out.append("")
    if not downstream_cache:
        out.append("- not-found")
    for key, evidence in downstream_cache.items():
        out.append(f"### {key}")
        for item in evidence:
            out.append(f"- {normalize_path_for_display(item)}")
        out.append("")

    out.append("## Commented-out / Inactive Interface Evidence")
    out.append("")
    if not inactive_calls:
        out.append("- not-found")
    for call in inactive_calls:
        out.append(f"- {' -> '.join(call.chain)} -> {call.interface}.{call.method}:{call.line} [{call.status}]")
    out.append("")

    out.append("## Open Questions")
    out.append("")
    blockers: list[str] = []
    for key, evidence in downstream_cache.items():
        if any("need-confirm" in item for item in evidence):
            blockers.append(f"{key}: downstream Contract/BLL/DAL/SQL evidence is incomplete.")
    if handler_missing:
        blockers.append("One or more Designer handlers were not found in the code-behind partial class.")
    if not blockers:
        out.append("- none")
    else:
        for blocker in blockers:
            out.append(f"- {blocker}")
    out.append("")
    return "\n".join(out)


def build_pack(args: argparse.Namespace) -> str:
    if args.mode == "ui-events":
        return build_ui_events_pack(args)
    if args.mode == "controller-operation-summary":
        return build_controller_operation_summary_pack(args)

    csharp_root = Path(args.csharp_root)
    java_root = Path(args.java_root)
    csharp_entry = args.csharp_input
    java_entry = args.java_input
    terms = entry_terms(csharp_entry)
    primary = terms[0]

    csharp_path_hit = resolve_location_hit(csharp_root, csharp_entry, "csharp")
    csharp_hits = [csharp_path_hit] if csharp_path_hit else []
    if not csharp_hits:
        csharp_query = codegraph_json(csharp_root, "query", primary, args.limit)
        csharp_hits = parse_query_hits(csharp_query)
    if not csharp_hits and len(terms) > 1:
        for term in terms[1:]:
            csharp_hits = parse_query_hits(codegraph_json(csharp_root, "query", term, args.limit))
            if csharp_hits:
                primary = term
                break
    if csharp_path_hit:
        primary = csharp_path_hit.name

    csharp_resolved = resolved_hits(csharp_hits)
    if csharp_resolved:
        callers = parse_relation_hits(codegraph_json(csharp_root, "callers", primary, args.limit), "callers")
        callees = parse_relation_hits(codegraph_json(csharp_root, "callees", primary, args.limit), "callees")
    else:
        callers = []
        callees = []

    java_hits: list[SymbolHit] = []
    java_path_hit: SymbolHit | None = None
    if java_entry:
        java_path_hit = resolve_location_hit(java_root, java_entry, "java")
        java_hits = [java_path_hit] if java_path_hit else parse_query_hits(codegraph_json(java_root, "query", java_entry, args.limit))

    search_targets = hit_targets(csharp_root, csharp_hits[:8])
    if not search_targets:
        entry_pattern = "|".join(re.escape(term) for term in terms[:4])
        entry_matches = rg(csharp_root, entry_pattern, limit=80) if entry_pattern else []
        for match in entry_matches[:20]:
            file_part = match.split(":", 1)[0]
            path = Path(file_part)
            if path.exists() and path not in search_targets:
                search_targets.append(path)

    evidence_patterns = [
        r"leftWhereStr|ParseCondition\(",
        r"ServiceManager<|" + re.escape(primary),
        r"HasPermission\(|CheckRight\(|GetPermCode|PerCode",
        r"getSql\s*=|GetSqlStringCommand|ExecuteReader|ExecuteNonQuery|SELECT |UPDATE |INSERT |DELETE ",
    ]
    rg_lines: list[str] = []
    if search_targets:
        for pattern in evidence_patterns:
            rg_lines.extend(rg(csharp_root, pattern, limit=80, targets=search_targets))
    seen: set[str] = set()
    rg_lines = [line for line in rg_lines if not (line in seen or seen.add(line))][:160]

    windows: list[tuple[SymbolHit, list[str]]] = []
    for hit in csharp_hits[:5]:
        radius = args.sql_window if re.search(r"DAL|SQL|Mapper", hit.file_path, re.IGNORECASE) else args.window
        window = read_window(csharp_root, hit.file_path, hit.start_line, radius)
        if window:
            windows.append((hit, window))
    window_text = "\n".join("\n".join(window) for _, window in windows)

    java_windows: list[tuple[SymbolHit, list[str]]] = []
    for hit in java_hits[:5]:
        radius = args.sql_window if re.search(r"Mapper|XML|SQL", hit.file_path, re.IGNORECASE) else args.window
        window = read_window(java_root, hit.file_path, hit.start_line, radius)
        if window:
            java_windows.append((hit, window))

    left_decision = infer_left_where(rg_lines, window_text) if (search_targets or window_text) else "need-confirm"
    permission_lines = [line for line in rg_lines if "HasPermission" in line or "CheckRight" in line or "PermCode" in line]
    permission_summary = [f"{classify_permission(line)} | {line}" for line in permission_lines[:40]]

    out: list[str] = []
    out.append(f"# Evidence Pack: {csharp_entry}")
    out.append("")
    out.append(f"- mode: {args.mode}")
    out.append(f"- csharp-root: {csharp_root.as_posix()}")
    out.append(f"- java-root: {java_root.as_posix()}")
    out.append(f"- primary-symbol: {primary}")
    if search_targets:
        out.append("- search-targets: " + ", ".join(project_arg(target) for target in search_targets[:8]))
    if java_entry:
        out.append(f"- java-entry: {java_entry}")
    out.append("")

    if args.mode == "equivalence-repair" or args.csharp_location or args.java_location:
        out.append("## Location Resolution")
        out.append("")
        out.append(f"- csharp-location-source: {resolution_source(args.csharp_location, csharp_path_hit, csharp_hits)}")
        out.append(f"- java-location-source: {resolution_source(args.java_location, java_path_hit, java_hits)}")
        out.append(f"- csharp-resolved-anchor: {first_anchor(csharp_hits)}")
        out.append(f"- java-resolved-anchor: {first_anchor(java_hits)}")
        out.append(f"- ambiguity: {ambiguity_summary(csharp_hits, java_hits)}")
        out.append("")

    out.extend(md_list("CSharp Symbol Hits", [hit.display for hit in csharp_hits]))
    out.extend(md_list("CSharp Callers", [hit.display for hit in callers[:20]]))
    out.extend(md_list("CSharp Callees", [hit.display for hit in callees[:20]]))
    out.extend(md_list("Java Asset Hits", [hit.display for hit in java_hits], empty="not-requested-or-not-found"))

    out.append("## leftWhereStr Decision")
    out.append("")
    out.append(f"- decision: {left_decision}")
    out.append("- rule: do not migrate leftWhereStr as a Java string parameter; convert sql-fragment to typed criteria")
    out.append("")

    out.extend(md_list("Permission Evidence", permission_summary, empty="not-found"))
    if args.mode == "equivalence-repair":
        out.append("## Permission Equivalence Handling")
        out.append("")
        out.append("- decision: 权限无关")
        out.append("- rule: permission, authorization, and qualification differences are excluded from business equivalence and must not trigger Java rewrites")
        out.append("")

    # Contract field usage verification: analyze entity/DTO parameters in Contract/BLL methods
    contract_field_reports: list[str] = []
    seen_methods: set[str] = set()

    # Find Contract interface methods from CodeGraph hits
    contract_methods: list[tuple[str, str]] = []  # (contract_name, method_name)
    for hit in csharp_hits:
        hit_path = hit.file_path.replace("\\", "/")
        if not hit_path.endswith(".cs"):
            continue
        if "Contract" not in hit_path:
            continue
        # Parse method signatures from Contract file
        contract_file = csharp_root / hit.file_path
        if not contract_file.exists():
            continue
        file_text = read_text_compat(contract_file)
        method_matches = re.finditer(
            r"\[OperationContract\]\s*\n\s*(?:public|private|void|bool|string|List<|Dictionary<|DataSet)\s+"
            r"(?P<name>[A-Za-z_]\w*)\s*\((?P<params>[^)]*)\)",
            file_text,
        )
        for m in method_matches:
            mname = m.group("name")
            if mname and mname not in seen_methods:
                seen_methods.add(mname)
                contract_methods.append((hit.name, mname))

    # For each Contract method, find BLL implementation and analyze field usage
    for contract_name, method_name in contract_methods[:8]:
        bll_hit = find_bll_implementation(csharp_root, contract_name, method_name, args.limit)
        if bll_hit is None:
            continue
        field_usage = contract_field_usage_evidence(
            csharp_root, contract_name, method_name, args.limit, args.sql_window,
            bll_hit=bll_hit,
        )
        if field_usage.get("status") == "confirmed" and field_usage.get("fields"):
            report = format_contract_field_usage_report(field_usage)
            contract_field_reports.append(report)

    if contract_field_reports:
        out.append("## Contract Field Usage Verification")
        out.append("")
        out.append("- rule: Java DTO must contain only fields confirmed as used in BLL; ref/out parameters map to VO return fields, not request DTO")
        out.append("")
        for report in contract_field_reports:
            out.append(report)
    out.extend(md_list("Targeted Text Evidence", rg_lines[:80]))

    out.append("## Required Source Windows")
    out.append("")
    if not windows:
        out.append("- not-found")
    for hit, window in windows:
        out.append(f"### {hit.display}")
        out.append("```text")
        max_lines = args.max_window_lines
        selected = window[:max_lines]
        out.extend(selected)
        if len(window) > max_lines:
            out.append(f"... truncated {len(window) - max_lines} lines ...")
        out.append("```")
        out.append("")

    if args.mode == "equivalence-repair" or java_windows:
        out.append("## Java Source Windows")
        out.append("")
        if not java_windows:
            out.append("- not-found")
        for hit, window in java_windows:
            out.append(f"### {hit.display}")
            out.append("```text")
            max_lines = args.max_window_lines
            selected = window[:max_lines]
            out.extend(selected)
            if len(window) > max_lines:
                out.append(f"... truncated {len(window) - max_lines} lines ...")
            out.append("```")
            out.append("")

    out.append("## Open Questions")
    out.append("")
    if left_decision in {"need-confirm", "not-found"}:
        out.append("- Confirm whether dynamic SQL conditions affect this migration scope.")
    if not resolved_hits(csharp_hits):
        out.append("- C# entry symbol was not found by CodeGraph; provide a file path or more precise method name.")
    if args.mode == "equivalence-repair" and not java_entry:
        out.append("- Java entry/location is required in equivalence-repair mode.")
    if java_entry and not resolved_hits(java_hits):
        out.append("- Java entry symbol was not found; verify target Controller/Service/Mapper name.")
    if not permission_summary:
        out.append("- No permission evidence found in the targeted scan.")
    out.append("")

    return "\n".join(out)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build compact CodeGraph evidence for C# -> Java/HBSK migration.")
    parser.add_argument("--csharp-entry", help="C# entry symbol, class, method, or path fragment")
    parser.add_argument("--csharp-location", action="append", help="Alias for a C# code location: path, path:line, class, or method; repeat for controller-operation-summary")
    parser.add_argument("--java-entry", help="Optional Java entry symbol, class, method, or path fragment")
    parser.add_argument("--java-location", help="Alias for a Java code location: path, path:line, class, or method")
    parser.add_argument("--mode", default="full-chain", choices=["full-chain", "symbol-only", "equivalence-repair", "ui-events", "controller-operation-summary"], help="Evidence depth")
    parser.add_argument("--csharp-root", default=DEFAULT_CSHARP_ROOT_TEXT, help="C# CodeGraph project root")
    parser.add_argument("--java-root", default=DEFAULT_JAVA_ROOT_TEXT, help="Java CodeGraph project root")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="CodeGraph result limit")
    parser.add_argument("--window", type=int, default=40, help="Source window radius")
    parser.add_argument("--sql-window", type=int, default=80, help="Source window radius for SQL/DAL hits")
    parser.add_argument("--max-window-lines", type=int, default=120, help="Maximum lines emitted per source window")
    parser.add_argument("--emit-operation-patch", action="store_true", help="For controller-operation-summary, print a non-applied @Operation patch")
    parser.add_argument("--patch-out", help="For controller-operation-summary, write the non-applied @Operation patch to this file")
    parser.add_argument("--contract-field-usage", action="store_true", help="Include Contract field usage verification section in evidence pack (auto-enabled when BLL callees found)")
    parser.add_argument("--out", help="Optional output file")
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="Timeout for external CodeGraph/rg commands; use 0 to disable")
    args = parser.parse_args(argv)
    args.csharp_inputs = args.csharp_location or ([args.csharp_entry] if args.csharp_entry else [])
    args.csharp_input = args.csharp_inputs[0] if args.csharp_inputs else None
    args.java_input = args.java_location or args.java_entry
    if args.mode != "controller-operation-summary" and not args.csharp_input:
        parser.error("one of --csharp-entry or --csharp-location is required")
    if args.mode == "equivalence-repair" and not args.java_input:
        parser.error("--mode equivalence-repair requires --java-entry or --java-location")
    if args.mode == "controller-operation-summary":
        if not args.java_input:
            parser.error("--mode controller-operation-summary requires --java-entry or --java-location")
        if not args.csharp_inputs:
            parser.error("--mode controller-operation-summary requires at least one --csharp-location or --csharp-entry")
    return args


def main(argv: list[str]) -> int:
    global COMMAND_TIMEOUT_SECONDS
    args = parse_args(argv)
    COMMAND_TIMEOUT_SECONDS = args.timeout_seconds if args.timeout_seconds > 0 else None
    text = build_pack(args)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

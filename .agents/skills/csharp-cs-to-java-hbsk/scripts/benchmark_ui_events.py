#!/usr/bin/env python3
"""Benchmark ui-events evidence extraction for csharp-cs-to-java-hbsk."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean


DEFAULT_CSHARP_ROOT_TEXT = "D:/codingProjects/#Net_\u526f\u672c/Source/BizModule"
SKILL_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = SKILL_ROOT / "scripts" / "build_evidence_pack.py"
DEFAULT_TIMEOUT_SECONDS = 120.0
COMMAND_TIMEOUT_SECONDS: float | None = DEFAULT_TIMEOUT_SECONDS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass(frozen=True)
class PageOracle:
    page_id: str
    class_name: str
    designer: str
    codebehind: str
    events: int
    active_events: int
    no_active_events: int
    expected_methods: tuple[str, ...]
    expected_chains: tuple[str, ...]
    downstream_methods: tuple[str, ...]


@dataclass(frozen=True)
class RgEventBinding:
    control: str
    event: str
    handler: str
    designer_line: int


@dataclass(frozen=True)
class RgMethodBlock:
    name: str
    start_line: int
    end_line: int
    lines: tuple[tuple[int, str], ...]


PAGES: tuple[PageOracle, ...] = (
    PageOracle(
        page_id="import-info-check",
        class_name="ImportInfoCheckMainForm",
        designer="DMS/SHB.TOPS.UI.DMS/ImportInfoCheck/ImportInfoCheckMainForm.Designer.cs",
        codebehind="DMS/SHB.TOPS.UI.DMS/ImportInfoCheck/ImportInfoCheckMainForm.cs",
        events=18,
        active_events=13,
        no_active_events=5,
        expected_methods=(
            "IVoyageService.GetImportVoyageList",
            "IVoyageService.GetImportVoyageBy",
            "IVoyageCheckLog.GetVoyageCheckLogs",
            "IVoyageCheckLog.SaveVoyageCheckLog",
            "IVoyageCheckLog.CheckInBoundCntrsLocation",
            "IVoyageCheckLog.GetCoperCheckResults",
            "IVoyageCheckLog.GetCheckResults",
            "IVoyageCheckLog.GetAccordPropsRules",
            "IVoyageCheckLog.HandleAccordPropsRules",
            "IStowagePlanContainer.SetUnknownVlocations",
            "IGeneralService.GetRefCodeByDomainCode",
        ),
        expected_chains=(
            "bbiFind_ItemClick -> BindCheckLogs",
            "bbiRefresh_ItemClick -> GridRefresh -> BindCheckLogs",
            "bbiImport_ItemClick -> PropCheckRuleForm_Closing -> SavePropCheckRules",
            "gcVoyage_MouseDoubleClick -> bbiShowDetail_ItemClick",
            "ImportInfoCheckMainForm_Load -> isCoperCheck",
        ),
        downstream_methods=(
            "IVoyageCheckLog.GetVoyageCheckLogs",
            "IVoyageCheckLog.SaveVoyageCheckLog",
            "IVoyageCheckLog.GetCheckResults",
            "IVoyageService.GetImportVoyageBy",
            "IGeneralService.GetRefCodeByDomainCode",
        ),
    ),
    PageOracle(
        page_id="export-empty-pass",
        class_name="ExportEmptyPassMainForm",
        designer="DMS/SHB.TOPS.UI.DMS/ExportEmptyPass/ExportEmptyPassMainForm.Designer.cs",
        codebehind="DMS/SHB.TOPS.UI.DMS/ExportEmptyPass/ExportEmptyPassMainForm.cs",
        events=21,
        active_events=6,
        no_active_events=15,
        expected_methods=(
            "IExportEmptyPass.GetEmptyLoadPlans",
            "IExportEmptyPass.GetEmptyLoadUseCRs",
            "IExportEmptyPass.GetEmptyLoadContainers",
            "IPortOfCalling.GetPortOfCallings",
            "IVoyageService.GetVoyageView",
            "IExportEmptyPass.SetEmptyContainerPass",
            "IExportEmptyPass.ReleaseEmptyContainerPass",
            "IExportEmptyPass.SetContainerBillNo",
            "IExportEmptyPass.SendCostrps",
            "IVoyageClose.VoyageIsShut",
            "IExportEmptyPass.IsNotAllowEmptyPass",
            "IGeneralService.GetAllCustomer",
        ),
        expected_chains=(
            "bbiFind_ItemClick -> LoadSearchDialog -> LoadData -> GetEmptyLoadPlanList",
            "bbiSave_ItemClick -> SaveContainerPass",
            "btnSetBillNo_Click -> SetBillNo -> IVoyageClose.VoyageIsShut",
            "btnSetBillNo_Click -> bbiSendCostrp_ItemClick -> SendCostrp",
            "ExportEmptyPassMainForm_Load -> BindCustomerName",
        ),
        downstream_methods=(
            "IExportEmptyPass.GetEmptyLoadPlans",
            "IExportEmptyPass.SetContainerBillNo",
            "IExportEmptyPass.SendCostrps",
            "IExportEmptyPass.IsNotAllowEmptyPass",
            "IVoyageClose.VoyageIsShut",
        ),
    ),
    PageOracle(
        page_id="vessel-to-vessel-manage",
        class_name="VesselToVesselManageForm",
        designer="DMS/SHB.TOPS.UI.DMS/VesselToVessel/VesselToVesselManageForm.Designer.cs",
        codebehind="DMS/SHB.TOPS.UI.DMS/VesselToVessel/VesselToVesselManageForm.cs",
        events=25,
        active_events=6,
        no_active_events=19,
        expected_methods=(
            "IVesselToVessel.GetTransferContainerListBy",
            "IVesselToVessel.SaveVesselToVessel",
            "IPortOfCalling.GetRelatePorts",
            "IRefCode.GetRefCodes",
            "IVoyageService.GetExportVoyageList",
            "IVoyageService.GetImportVoyageList",
            "IGeneralService.GetAllCustomer",
            "IGeneralService.GetRefCodeByDomainCode",
        ),
        expected_chains=(
            "bbiFind_ItemClick -> ShowSearchDialog -> LoadData",
            "bbiSave_ItemClick -> SaveVslToVsl",
            "lueVVVslName_EditValueChanging -> LoadPOCPorts",
            "VesselToVesselManageForm_Load -> LoadBaseData -> LoadVoyage",
            "VesselToVesselManageForm_Load -> LoadBaseData -> SetAdditionalOperateBinding",
        ),
        downstream_methods=(
            "IVesselToVessel.GetTransferContainerListBy",
            "IVesselToVessel.SaveVesselToVessel",
            "IPortOfCalling.GetRelatePorts",
            "IVoyageService.GetExportVoyageList",
            "IRefCode.GetRefCodes",
        ),
    ),
)


INPUT_MODES = ("designer-location", "codebehind-location", "class-entry")


SUMMARY_PATTERNS = {
    "events": re.compile(r"- ui-event-bindings: (\d+)"),
    "active_events": re.compile(r"- active-interface-events: (\d+)"),
    "no_active_events": re.compile(r"- no-active-interface-events: (\d+)"),
    "missing_handlers": re.compile(r"- missing-handlers: (\d+)"),
}


def project_path(root: str, relative: str) -> str:
    return str(Path(root) / relative).replace("\\", "/")


def skill_command_for(page: PageOracle, mode: str, csharp_root: str) -> list[str]:
    base = [
        sys.executable,
        str(BUILD_SCRIPT),
        "--mode",
        "ui-events",
        "--csharp-root",
        csharp_root,
    ]
    if mode == "designer-location":
        return base + ["--csharp-location", project_path(csharp_root, page.designer)]
    if mode == "codebehind-location":
        return base + ["--csharp-location", project_path(csharp_root, page.codebehind)]
    if mode == "class-entry":
        return base + ["--csharp-entry", page.class_name]
    raise ValueError(f"unknown input mode: {mode}")


def read_text_compat(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


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


def run_text_command(args: list[str]) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            args,
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


def rg_file_lines(pattern: str, path: Path) -> list[tuple[int, str]]:
    rc, out, _ = run_text_command(["rg", "-n", pattern, str(path)])
    if rc not in (0, 1):
        return []
    matches: list[tuple[int, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        line_no, sep, text = line.partition(":")
        if not sep or not line_no.isdigit():
            continue
        matches.append((int(line_no), text))
    return matches


def rg_list_files(pattern: str, root: Path) -> list[Path]:
    rc, out, _ = run_text_command(["rg", "-l", "--glob", "*.cs", pattern, str(root)])
    if rc not in (0, 1):
        return []
    return [Path(line.strip()) for line in out.splitlines() if line.strip()]


def rg_resolve_page_files(page: PageOracle, input_mode: str, csharp_root: str) -> tuple[Path, Path]:
    root = Path(csharp_root)
    if input_mode == "designer-location":
        designer = root / page.designer
        codebehind = designer.with_name(designer.name.replace(".Designer.cs", ".cs"))
        return designer, codebehind
    if input_mode == "codebehind-location":
        codebehind = root / page.codebehind
        designer = codebehind.with_name(f"{codebehind.stem}.Designer.cs")
        return designer, codebehind
    if input_mode == "class-entry":
        hits = rg_list_files(rf"\bpartial\s+class\s+{re.escape(page.class_name)}\b", root)
        designer = next((item for item in hits if item.name.endswith(".Designer.cs")), None)
        codebehind = next((item for item in hits if not item.name.endswith(".Designer.cs")), None)
        if designer and not codebehind:
            codebehind = designer.with_name(designer.name.replace(".Designer.cs", ".cs"))
        if codebehind and not designer:
            designer = codebehind.with_name(f"{codebehind.stem}.Designer.cs")
        if designer and codebehind:
            return designer, codebehind
    raise FileNotFoundError(f"rg could not resolve {page.page_id} using {input_mode}")


def parse_rg_events(designer: Path) -> list[RgEventBinding]:
    event_lines = rg_file_lines(r"\+=", designer)
    control_event_pattern = re.compile(
        r"this\.(?P<control>[A-Za-z_]\w*)\.(?P<event>[A-Za-z_]\w*)\s*\+=\s*"
        r"(?:new\s+[A-Za-z0-9_.<>]+\s*\(\s*)?(?:this\.)?(?P<handler>[A-Za-z_]\w*)"
    )
    form_event_pattern = re.compile(
        r"this\.(?P<event>[A-Za-z_]\w*)\s*\+=\s*"
        r"(?:new\s+[A-Za-z0-9_.<>]+\s*\(\s*)?(?:this\.)?(?P<handler>[A-Za-z_]\w*)"
    )
    events: list[RgEventBinding] = []
    for line_no, line in event_lines:
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        match = control_event_pattern.search(line)
        if match:
            events.append(RgEventBinding(match.group("control"), match.group("event"), match.group("handler"), line_no))
            continue
        match = form_event_pattern.search(line)
        if match:
            events.append(RgEventBinding("this", match.group("event"), match.group("handler"), line_no))
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


def parse_rg_methods(codebehind: Path) -> dict[str, RgMethodBlock]:
    lines = read_text_compat(codebehind).splitlines()
    method_pattern = re.compile(
        r"^\s*(?:public|private|protected|internal)\s+"
        r"(?:static\s+)?(?:[\w<>\[\],.?]+\s+)+(?P<name>[A-Za-z_]\w*)\s*\("
    )
    methods: dict[str, RgMethodBlock] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip().startswith("//") or "(" not in line:
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
        block_lines = tuple((line_number, lines[line_number - 1]) for line_number in range(index + 1, end_index + 2))
        methods[name] = RgMethodBlock(name, index + 1, end_index + 1, block_lines)
        index = end_index + 1
    return methods


def active_rg_lines(block: RgMethodBlock) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for line_no, line in block.lines:
        if line.strip().startswith("//"):
            continue
        cleaned = strip_line_comment(line).strip()
        if cleaned:
            result.append((line_no, cleaned))
    return result


def direct_rg_service_calls(block: RgMethodBlock) -> list[str]:
    manager_vars: dict[str, str] = {}
    service_aliases: dict[str, str] = {}
    calls: list[str] = []
    manager_patterns = (
        re.compile(r"\bvar\s+(?P<var>[A-Za-z_]\w*)\s*=\s*new\s+ServiceManager<(?P<iface>I[A-Za-z_]\w*)>"),
        re.compile(r"\bServiceManager<(?P<iface>I[A-Za-z_]\w*)>\s+(?P<var>[A-Za-z_]\w*)\b"),
    )
    alias_pattern = re.compile(r"\b(?P<iface>I[A-Za-z_]\w*)\s+(?P<alias>[A-Za-z_]\w*)\s*=\s*(?P<manager>[A-Za-z_]\w*)\.Service\b")
    direct_call_pattern = re.compile(r"\b(?P<manager>[A-Za-z_]\w*)\.Service\.(?P<method>[A-Za-z_]\w*)\s*\(")
    alias_call_pattern = re.compile(r"(?<!\.)\b(?P<alias>[A-Za-z_]\w*)\.(?P<method>[A-Za-z_]\w*)\s*\(")

    for _, line in active_rg_lines(block):
        for pattern in manager_patterns:
            for match in pattern.finditer(line):
                manager_vars[match.group("var")] = match.group("iface")
        for match in alias_pattern.finditer(line):
            service_aliases[match.group("alias")] = match.group("iface") or manager_vars.get(match.group("manager"), "unknown-interface")
        for match in direct_call_pattern.finditer(line):
            manager = match.group("manager")
            if manager in manager_vars:
                calls.append(f"{manager_vars[manager]}.{match.group('method')}")
        for match in alias_call_pattern.finditer(line):
            alias = match.group("alias")
            if alias in service_aliases:
                calls.append(f"{service_aliases[alias]}.{match.group('method')}")
    deduped: list[str] = []
    for call in calls:
        if call not in deduped:
            deduped.append(call)
    return deduped


def build_rg_output(page: PageOracle, input_mode: str, csharp_root: str) -> str:
    designer, codebehind = rg_resolve_page_files(page, input_mode, csharp_root)
    events = parse_rg_events(designer)
    methods = parse_rg_methods(codebehind)
    event_calls: dict[int, list[str]] = {}
    missing_handlers = 0
    for index, event in enumerate(events, start=1):
        block = methods.get(event.handler)
        if not block:
            missing_handlers += 1
            event_calls[index] = []
            continue
        event_calls[index] = direct_rg_service_calls(block)

    active_events = sum(1 for calls in event_calls.values() if calls)
    no_active_events = len(events) - active_events
    out: list[str] = []
    out.append(f"# RG UI Event Baseline: {page.class_name}")
    out.append("")
    out.append("- mode: rg-direct")
    out.append(f"- designer: {designer.as_posix()}")
    out.append(f"- code-behind: {codebehind.as_posix()}")
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append(f"- ui-event-bindings: {len(events)}")
    out.append(f"- active-interface-events: {active_events}")
    out.append(f"- commented-out-only-events: 0")
    out.append(f"- no-active-interface-events: {no_active_events}")
    out.append(f"- missing-handlers: {missing_handlers}")
    out.append("")
    out.append("## RG Direct Event Trace")
    out.append("")
    out.append("| # | control | event | handler | direct interface calls | status |")
    out.append("|---|---|---|---|---|---|")
    for index, event in enumerate(events, start=1):
        block = methods.get(event.handler)
        handler_anchor = f"{codebehind.as_posix()}:{block.start_line}" if block else "handler-not-found"
        calls = event_calls[index]
        call_text = "; ".join(f"{event.handler} -> {call}" for call in calls) if calls else "none"
        status = "active-interface" if calls else ("handler-not-found" if block is None else "no-active-interface")
        out.append(f"| {index} | `{event.control}` | `{event.event}` | `{handler_anchor}` `{event.handler}` | {call_text} | `{status}` |")
    out.append("")
    out.append("## Traditional RG Limits")
    out.append("")
    out.append("- This baseline does not follow helper methods, callbacks, PerformClick indirection, CodeGraph Contract/BLL implementation, or DAL/SQL evidence.")
    out.append("- Missing methods/chains represent manual follow-up work required after a raw rg pass.")
    out.append("")
    return "\n".join(out)


def parse_summary(text: str) -> dict[str, int | None]:
    parsed: dict[str, int | None] = {}
    for key, pattern in SUMMARY_PATTERNS.items():
        match = pattern.search(text)
        parsed[key] = int(match.group(1)) if match else None
    return parsed


def ratio(found: int, total: int) -> float:
    return 1.0 if total == 0 else found / total


def method_downstream_ok(text: str, method: str) -> bool:
    escaped = re.escape(method)
    pattern = re.compile(rf"^### {escaped}(?:\s|$)", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return False
    next_start = text.find("\n### ", match.end())
    section = text[match.start():] if next_start < 0 else text[match.start():next_start]
    has_contract = "- contract:" in section and "contract: need-confirm" not in section
    has_implementation = "- implementation:" in section and "implementation: need-confirm" not in section
    has_sql_or_dal = (
        re.search(r"- sql/dal-window:\s+(?!need-confirm)", section) is not None
        or re.search(r"- callee: .*?(DAL|SQL|Procedure|Mapper)", section, re.IGNORECASE) is not None
    )
    return has_contract and has_implementation and has_sql_or_dal and "need-confirm" not in section


def score_output(text: str, summary: dict[str, int | None], page: PageOracle) -> dict[str, object]:
    summary_ok = summary.get("events") == page.events
    handler_ok = summary.get("missing_handlers") == 0 and "handler-not-found" not in text

    method_hits = [item for item in page.expected_methods if item in text]
    chain_hits = [item for item in page.expected_chains if item in text]
    downstream_hits = [item for item in page.downstream_methods if method_downstream_ok(text, item)]

    return {
        "event_summary_accuracy": 1.0 if summary_ok else 0.0,
        "handler_anchor_accuracy": 1.0 if handler_ok else 0.0,
        "interface_call_recall": ratio(len(method_hits), len(page.expected_methods)),
        "indirect_chain_recall": ratio(len(chain_hits), len(page.expected_chains)),
        "downstream_evidence_recall": ratio(len(downstream_hits), len(page.downstream_methods)),
        "method_hits": method_hits,
        "method_misses": [item for item in page.expected_methods if item not in method_hits],
        "chain_hits": chain_hits,
        "chain_misses": [item for item in page.expected_chains if item not in chain_hits],
        "downstream_hits": downstream_hits,
        "downstream_misses": [item for item in page.downstream_methods if item not in downstream_hits],
        "downstream_need_confirm": "downstream Contract/BLL/DAL/SQL evidence is incomplete" in text,
    }


def run_one(page: PageOracle, input_mode: str, repeat: int, csharp_root: str, strategy: str) -> dict[str, object]:
    print(f"[{strategy}][{page.page_id}][{input_mode}][run {repeat}] start", flush=True)
    started = time.perf_counter()
    if strategy == "skill":
        try:
            completed = subprocess.run(
                skill_command_for(page, input_mode, csharp_root),
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout_value(),
            )
            returncode = completed.returncode
            text = completed.stdout
            stderr_tail = completed.stderr[-800:]
        except subprocess.TimeoutExpired as exc:
            text, stderr_tail = timeout_text(exc)
            returncode = 124
    elif strategy == "rg":
        try:
            text = build_rg_output(page, input_mode, csharp_root)
            returncode = 0
            stderr_tail = ""
        except Exception as exc:
            text = ""
            returncode = 1
            stderr_tail = repr(exc)
    else:
        raise ValueError(f"unknown strategy: {strategy}")
    elapsed = time.perf_counter() - started
    summary = parse_summary(text)
    scores = score_output(text, summary, page)
    result = {
        "strategy": strategy,
        "page_id": page.page_id,
        "input_mode": input_mode,
        "repeat": repeat,
        "returncode": returncode,
        "elapsed_seconds": round(elapsed, 3),
        "summary": summary,
        "stderr_tail": stderr_tail,
        **scores,
    }
    print(
        f"[{strategy}][{page.page_id}][{input_mode}][run {repeat}] "
        f"rc={returncode} time={elapsed:.3f}s "
        f"events={summary.get('events')} iface={scores['interface_call_recall']:.3f} "
        f"chain={scores['indirect_chain_recall']:.3f} downstream={scores['downstream_evidence_recall']:.3f}",
        flush=True,
    )
    return result


def stable_pair(run_a: dict[str, object], run_b: dict[str, object]) -> bool:
    keys = (
        "summary",
        "event_summary_accuracy",
        "handler_anchor_accuracy",
        "interface_call_recall",
        "indirect_chain_recall",
        "downstream_evidence_recall",
        "method_misses",
        "chain_misses",
        "downstream_misses",
        "downstream_need_confirm",
    )
    return all(run_a.get(key) == run_b.get(key) for key in keys)


def aggregate(results: list[dict[str, object]]) -> dict[str, object]:
    numeric_keys = (
        "event_summary_accuracy",
        "handler_anchor_accuracy",
        "interface_call_recall",
        "indirect_chain_recall",
        "downstream_evidence_recall",
    )
    averages = {
        key: round(mean(float(item[key]) for item in results), 4)
        for key in numeric_keys
    }
    avg_time = round(mean(float(item["elapsed_seconds"]) for item in results), 3)
    max_time = round(max(float(item["elapsed_seconds"]) for item in results), 3)
    failures = [item for item in results if int(item["returncode"]) != 0]
    pairs: list[bool] = []
    by_case: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for item in results:
        by_case.setdefault((str(item["strategy"]), str(item["page_id"]), str(item["input_mode"])), []).append(item)
    for pair_results in by_case.values():
        pair_results.sort(key=lambda item: int(item["repeat"]))
        if len(pair_results) >= 2:
            pairs.append(stable_pair(pair_results[0], pair_results[1]))
    return {
        **averages,
        "average_elapsed_seconds": avg_time,
        "max_elapsed_seconds": max_time,
        "success_rate": round((len(results) - len(failures)) / len(results), 4) if results else 0.0,
        "repeat_stability": round(sum(1 for item in pairs if item) / len(pairs), 4) if pairs else 0.0,
        "total_runs": len(results),
        "failed_runs": len(failures),
    }


def passed(result: dict[str, object]) -> bool:
    return (
        int(result["returncode"]) == 0
        and float(result["event_summary_accuracy"]) == 1.0
        and float(result["handler_anchor_accuracy"]) == 1.0
        and float(result["interface_call_recall"]) >= 0.95
        and float(result["indirect_chain_recall"]) >= 0.90
        and float(result["downstream_evidence_recall"]) >= 0.80
        and not bool(result.get("downstream_need_confirm"))
    )


def aggregate_by_strategy(results: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    strategies = sorted({str(item["strategy"]) for item in results})
    return {
        strategy: aggregate([item for item in results if str(item["strategy"]) == strategy])
        for strategy in strategies
    }


def strategy_value(summaries: dict[str, dict[str, object]], strategy: str, key: str) -> str:
    if strategy not in summaries:
        return "n/a"
    value = summaries[strategy][key]
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def markdown_report(results: list[dict[str, object]], summaries: dict[str, dict[str, object]], csharp_root: str) -> str:
    lines: list[str] = []
    lines.append("# UI Events Benchmark Baseline")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append("- skill: csharp-cs-to-java-hbsk")
    lines.append("- mode: ui-events")
    lines.append("- comparison: skill evidence mode vs traditional rg direct scan")
    lines.append(f"- csharp-root: {csharp_root}")
    lines.append("- pages: import-info-check, export-empty-pass, vessel-to-vessel-manage")
    lines.append("- input modes: designer-location, codebehind-location, class-entry")
    lines.append("- repeats: 2 per page/input mode")
    lines.append("- rg baseline: Designer event subscriptions + handler body direct `ServiceManager<T>.Service.Method` only; no helper/callback/PerformClick/CodeGraph/downstream tracing")
    lines.append("")
    lines.append("## Six-Dimension Baseline")
    lines.append("")
    lines.append("| dimension | skill baseline | rg baseline | skill pass floor |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| event coverage accuracy | {strategy_value(summaries, 'skill', 'event_summary_accuracy')} | {strategy_value(summaries, 'rg', 'event_summary_accuracy')} | 1.0000 |")
    lines.append(f"| handler anchor accuracy | {strategy_value(summaries, 'skill', 'handler_anchor_accuracy')} | {strategy_value(summaries, 'rg', 'handler_anchor_accuracy')} | 1.0000 |")
    lines.append(f"| interface call recall | {strategy_value(summaries, 'skill', 'interface_call_recall')} | {strategy_value(summaries, 'rg', 'interface_call_recall')} | >= 0.9500 |")
    lines.append(f"| indirect chain recall | {strategy_value(summaries, 'skill', 'indirect_chain_recall')} | {strategy_value(summaries, 'rg', 'indirect_chain_recall')} | >= 0.9000 |")
    lines.append(f"| downstream evidence recall | {strategy_value(summaries, 'skill', 'downstream_evidence_recall')} | {strategy_value(summaries, 'rg', 'downstream_evidence_recall')} | >= 0.8000 |")
    lines.append(f"| repeat stability | {strategy_value(summaries, 'skill', 'repeat_stability')} | {strategy_value(summaries, 'rg', 'repeat_stability')} | 1.0000 |")
    lines.append("")
    lines.append("## Runtime Baseline")
    lines.append("")
    lines.append("| strategy | total runs | failed runs | success rate | avg seconds | max seconds |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for strategy in sorted(summaries):
        summary = summaries[strategy]
        lines.append(
            f"| {strategy} | {summary['total_runs']} | {summary['failed_runs']} | "
            f"{float(summary['success_rate']):.4f} | "
            f"{float(summary['average_elapsed_seconds']):.3f} | "
            f"{float(summary['max_elapsed_seconds']):.3f} |"
        )
    if "skill" in summaries and "rg" in summaries:
        skill_avg = float(summaries["skill"]["average_elapsed_seconds"])
        rg_avg = float(summaries["rg"]["average_elapsed_seconds"])
        speed_ratio = skill_avg / rg_avg if rg_avg else 0.0
        lines.append("")
        lines.append(f"- raw rg is {speed_ratio:.1f}x faster by wall-clock because it does not trace helpers, callbacks, Contract/BLL, or DAL/SQL evidence.")
        lines.append("- skill efficiency is measured by evidence completeness: rg leaves helper-chain and downstream evidence work for manual follow-up.")
    lines.append("")
    lines.append("## Case Results")
    lines.append("")
    lines.append("| strategy | page | input | run | time(s) | events | active | no-active | method | chain | downstream | quality |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for item in results:
        summary_item = item["summary"]
        assert isinstance(summary_item, dict)
        quality = "pass" if passed(item) else ("reference" if item["strategy"] == "rg" else "fail")
        lines.append(
            f"| {item['strategy']} | {item['page_id']} | {item['input_mode']} | {item['repeat']} | "
            f"{item['elapsed_seconds']:.3f} | {summary_item.get('events')} | "
            f"{summary_item.get('active_events')} | {summary_item.get('no_active_events')} | "
            f"{float(item['interface_call_recall']):.3f} | "
            f"{float(item['indirect_chain_recall']):.3f} | "
            f"{float(item['downstream_evidence_recall']):.3f} | "
            f"{quality} |"
        )
    lines.append("")
    lines.append("## Misses")
    lines.append("")
    miss_lines: list[str] = []
    for item in results:
        misses = []
        for key in ("method_misses", "chain_misses", "downstream_misses"):
            value = item.get(key) or []
            if value:
                misses.append(f"{key}={value}")
        if misses:
            miss_lines.append(f"- {item['strategy']} / {item['page_id']} / {item['input_mode']} / run {item['repeat']}: " + "; ".join(misses))
    if miss_lines:
        lines.extend(miss_lines)
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Machine-Readable Summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summaries, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Regression Rule")
    lines.append("")
    lines.append("Future ui-events optimizations must not reduce any skill six-dimension baseline value, must not introduce new skill per-case misses, and should keep the rg comparison for context.")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ui-events benchmark twice across representative pages and input modes.")
    parser.add_argument("--csharp-root", default=DEFAULT_CSHARP_ROOT_TEXT)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--strategy", choices=["skill", "rg", "both"], default="skill")
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="Timeout for each rg/evidence subprocess; use 0 to disable")
    parser.add_argument("--out", help="Optional markdown report path")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    global COMMAND_TIMEOUT_SECONDS
    args = parse_args(argv)
    COMMAND_TIMEOUT_SECONDS = args.timeout_seconds if args.timeout_seconds > 0 else None
    if args.runs < 2:
        raise SystemExit("--runs must be at least 2 for repeat-stability benchmarking")

    strategies = ["skill", "rg"] if args.strategy == "both" else [args.strategy]
    results: list[dict[str, object]] = []
    for strategy in strategies:
        if strategy == "rg" and not run_text_command(["rg", "--version"])[0] == 0:
            raise SystemExit("rg is required for --strategy rg/both")
        for page in PAGES:
            for input_mode in INPUT_MODES:
                for repeat in range(1, args.runs + 1):
                    results.append(run_one(page, input_mode, repeat, args.csharp_root, strategy))

    summaries = aggregate_by_strategy(results)
    report = markdown_report(results, summaries, args.csharp_root)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"wrote report: {out_path}", flush=True)
    else:
        print(report)

    command_success = all(int(item["returncode"]) == 0 for item in results)
    skill_results = [item for item in results if item["strategy"] == "skill"]
    skill_passed = all(passed(item) for item in skill_results)
    skill_stable = True
    if "skill" in summaries:
        skill_stable = float(summaries["skill"]["repeat_stability"]) == 1.0
    return 0 if command_success and skill_passed and skill_stable else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

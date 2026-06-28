#!/usr/bin/env python3
"""
Crossroads Agent Café — 服务器部署压缩包打包器。

排除开发期文件（.venv / .git / node_modules / 各 AI 工具配置 / 日志 / 设计文档），
生成可直接 `docker compose -f deploy/docker-compose.1panel.yml up -d --build` 的精简包。

用法：
    python scripts/pack_release.py [输出zip路径]
默认输出：<项目根>/crossroads-agent-cafe-release.zip

压缩包结构：顶层目录 crossroads-agent-cafe/，解压后即项目根（含 .env、Dockerfile、deploy/ 等）。
"""
from __future__ import annotations

import fnmatch
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "crossroads-agent-cafe-release.zip"
ARC_PREFIX = "crossroads-agent-cafe"

# 不递归进入的目录（开发期 / 运行时 / 工具配置，部署不需要）
EXCLUDE_DIRS = {
    ".venv", ".git", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache",
    # AI 编辑器 / 工具配置（开发期）
    ".idea", ".cursor", ".codex", ".gemini", ".trae", ".zhipu", ".qingyan", ".kiro",
    ".codestable", ".ccg", ".claude", ".evolver", ".codegraph", ".context",
    # 运行时 / 本地产物
    "memory", "output", ".artifacts", ".playwright-mcp", "logs",
    # 前端构建缓存（产物已在 app/static/3d）
    "dist", ".pnpm-store", ".vite",
    # 设计文档（含大量截图，部署不需要；开发机保留）
    "docs",
}

# 排除的根级文件
EXCLUDE_FILES = {
    ".env",                # 本地开发 .env，用 .env.production 复制为 .env 替代
    ".env.production",     # 打包时单独处理（复制为 .env）
    ".local-consumer.env",
    ".mcp.json", ".mcp.json.backup",
    "server.err.log", "server.out.log",
    "_mock_hub.py",        # 临时 EvoMap Hub mock
    "package.json", "package-lock.json",   # 根级 evolver 依赖（非项目所需）
    "crossroads-agent-cafe-release.zip",          # 避免自包含
    "opencode.jsonc",     # OpenCode 编辑器配置
}

# 排除的文件名模式
EXCLUDE_PATTERNS = ["*.log", "*.pyc", "*.pyo", "smoke-*.png", "3d-scene-*.png", "*.pid"]

# 排除的相对子路径：前端源资产（音频/3D 模型）的产物已在 app/static/3d，无需携带源副本
EXCLUDE_SUBPATHS = {"frontend/public"}


def excluded(name: str, is_dir: bool) -> bool:
    if is_dir and name in EXCLUDE_DIRS:
        return True
    if not is_dir and name in EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(name, p) for p in EXCLUDE_PATTERNS)


def main() -> int:
    if OUT.parent != ROOT:
        OUT.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    src_bytes = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # 1) .env.production → 压缩包内 .env（容器直接读）
        env_prod = ROOT / ".env.production"
        if env_prod.exists():
            zf.write(env_prod, f"{ARC_PREFIX}/.env")
            count += 1
            src_bytes += env_prod.stat().st_size
            print(f"  + .env (from .env.production)")
        else:
            print("[WARN] .env.production 不存在，压缩包将不含 .env！")

        # 2) 遍历项目（原地裁剪 dirnames 阻止进入排除目录）
        for dirpath, dirnames, filenames in os.walk(ROOT):
            rel_dir = Path(dirpath).relative_to(ROOT).as_posix()
            dirnames[:] = sorted(
                d for d in dirnames
                if not excluded(d, is_dir=True)
                and f"{rel_dir}/{d}".lstrip("/") not in EXCLUDE_SUBPATHS
            )
            for fn in sorted(filenames):
                if excluded(fn, is_dir=False):
                    continue
                full = Path(dirpath) / fn
                rel = full.relative_to(ROOT).as_posix()
                zf.write(full, f"{ARC_PREFIX}/{rel}")
                count += 1
                src_bytes += full.stat().st_size

    zip_mb = OUT.stat().st_size / 1024 / 1024
    src_mb = src_bytes / 1024 / 1024
    print()
    print(f"[OK] {count} files, source {src_mb:.1f} MB -> zip {zip_mb:.1f} MB")
    print(f"     输出: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env node
'use strict';

// Node wrapper that lets `npx @evomap/a2a-super-order ...` invoke the Python
// CLI (scripts/order.py) cross-platform. The Python script owns all business
// logic; this file only locates a Python 3 interpreter, forwards argv, and
// surfaces a friendly error when Python is missing.

const { spawn } = require('child_process');
const path = require('path');

const scriptPath = path.join(__dirname, '..', 'scripts', 'order.py');
const orderArgs = [scriptPath, ...process.argv.slice(2)];

// Probe interpreters before running order.py. The CLI uses Python 3.10+
// syntax, and Windows often has an old `python` alongside a current `py -3`.
const candidates = process.platform === 'win32'
  ? [
      { command: 'py', prefix: ['-3'] },
      { command: 'python', prefix: [] },
      { command: 'python3', prefix: [] },
    ]
  : [
      { command: 'python3', prefix: [] },
      { command: 'python', prefix: [] },
    ];

function reportPythonMissing() {
  console.error('');
  console.error('✗ 未找到 Python 3.10+。本 Skill 的核心脚本是 Python，请先安装：');
  console.error('  • Windows: https://www.python.org/downloads/  (安装时勾选 “Add to PATH”)');
  console.error('  • macOS:   brew install python3');
  console.error('  • Linux:   sudo apt install python3  (或你的发行版对应的包管理器)');
  console.error('');
  console.error('安装后重试:');
  console.error('  npx @evomap/a2a-super-order --message "一杯拿铁"');
  process.exit(127);
}

function tryPython(idx) {
  if (idx >= candidates.length) {
    reportPythonMissing();
    return;
  }
  const candidate = candidates[idx];
  const versionProbe = spawn(
    candidate.command,
    [...candidate.prefix, '-c', 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'],
    { stdio: 'ignore' },
  );
  let probeErrored = false;
  versionProbe.once('error', () => {
    probeErrored = true;
    tryPython(idx + 1);
  });
  versionProbe.once('close', (code) => {
    if (probeErrored) return;
    if (code !== 0) {
      tryPython(idx + 1);
      return;
    }
    const child = spawn(
      candidate.command,
      [...candidate.prefix, ...orderArgs],
      { stdio: 'inherit' },
    );
    child.once('error', (err) => {
      console.error('启动 Python 失败:', err.message);
      process.exit(1);
    });
    child.once('close', (childCode) => {
      process.exit(typeof childCode === 'number' ? childCode : 1);
    });
  });
}

tryPython(0);

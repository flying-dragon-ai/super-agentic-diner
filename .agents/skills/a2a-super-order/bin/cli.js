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

// Windows typically exposes `python` (and sometimes `python3`); Unix usually
// exposes `python3`. Try candidates in order.
const candidates = process.platform === 'win32'
  ? ['python', 'python3']
  : ['python3', 'python'];

function reportPythonMissing() {
  console.error('');
  console.error('✗ 未找到 Python 3。本 Skill 的核心脚本是 Python，请先安装：');
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
  const child = spawn(candidates[idx], orderArgs, { stdio: 'inherit' });
  child.on('error', (err) => {
    if (err.code === 'ENOENT') {
      // This interpreter isn't installed — try the next candidate.
      tryPython(idx + 1);
    } else {
      console.error('启动 Python 失败:', err.message);
      process.exit(1);
    }
  });
  child.on('close', (code) => {
    process.exit(typeof code === 'number' ? code : 1);
  });
}

tryPython(0);

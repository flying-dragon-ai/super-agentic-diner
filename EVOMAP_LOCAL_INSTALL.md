# EvoMap Evolver 本项目局部使用说明

本项目要求 `@evomap/evolver` 只安装在当前目录，禁止使用全局安装。

## 已固定的本地安装

- 包：`@evomap/evolver`
- 版本：`1.89.14`
- 本地入口：`node_modules/.bin/evolver.cmd`
- npm 脚本：`npm run evolver:help`、`npm run evolver -- <args>`

## 同事拉取仓库后的使用方式

如果仓库提交时包含 `node_modules/`，同事拉取后可直接运行：

```powershell
cd D:\temp\EVOMAP\coffee-ai-boss
npm run evolver:help
```

或直接运行本地入口：

```powershell
.\node_modules\.bin\evolver.cmd --help
```

## 禁止事项

不要执行：

```powershell
npm install -g @evomap/evolver
```

不要为了接入 Cursor / Claude Code 直接执行 `setup-hooks`，因为该命令会写入用户 Home 目录下的全局配置，例如 `~/.cursor/` 或 `~/.claude/`。

## 提交提醒

为了让同事“不用二次下载”，需要把以下内容一起提交到 Git：

- `package.json`
- `package-lock.json`
- `node_modules/`

当前项目目录没有 `.gitignore`，不会从项目规则里忽略 `node_modules/`。如果你的 Git 全局忽略规则忽略了 `node_modules/`，提交时需要显式强制添加：

```powershell
git add package.json package-lock.json node_modules -f
```

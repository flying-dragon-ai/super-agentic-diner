# Coding Style Guide

> 此文件定义团队编码规范，所有 LLM 工具在修改代码时必须遵守。
> 提交到 Git，团队共享。
> 与根 `CLAUDE.md` 的「编码规范」一致，此处为可机读的强制版本。

## General
- Prefer small, reviewable changes; avoid unrelated refactors.
- Keep functions short (<50 lines); avoid deep nesting (≤3 levels).
- Name things explicitly; no single-letter variables except loop counters.
- Handle errors explicitly; never swallow errors silently.
- 中文 docstring 解释业务意图（不要描述语法），代码自解释「怎么做」。

## Python (后端 app/)
- 使用类型注解，文件头加 `from __future__ import annotations`。
- PEP 8 风格，模块/函数/变量用 snake_case。
- 业务逻辑必须在 `services/` 层事务内完成；**LLM 只负责"理解"和"说话"，绝不直接写库**。
- 改 API 时同步更新 docstring 与 `docs/` 设计文档摘要。
- 扣款/下单必须用 `with_for_update()` 行锁防并发超扣。

## TypeScript (前端 frontend/)
- `tsconfig.json` 启用 `strict` 模式。
- React 19 函数组件 + Hooks，组件名用 PascalCase。
- 改 3D 渲染：坐标投影靠 `office3d/core/geometry.ts` 的 `toWorld` + `SCALE=0.018`；
  寻路在 `core/navigation.ts`（25px 网格）；改家具寻路行为调 `ITEM_METADATA.blocksNavigation/navPadding`。
- 新增可视化事件类型时，必须同步 `frontend/src/sim/roleMap.ts` 的 `ACTION_BEHAVIOR` 映射。

## Git Commits
- Conventional Commits, imperative mood。
- Atomic commits：一个逻辑变更一个 commit。
- LLM 调用相关改动保持 JSON 输出格式（`parse_intent` 会 `_strip_code_fence`）。

## Testing
- Every feat/fix MUST include corresponding tests.
- Coverage must not decrease.
- Fix flow：先写失败测试（红灯），再改代码（变绿灯）。
- 运行：`python -m pytest tests/` 或 `python -m unittest discover tests`。

## Security
- Never log secrets (tokens/keys/cookies/JWT)。
- EvoMap 响应日志前必过 `_redact_response`；Skill 脚本过 `redact_for_stdout`。
- `node_secret` 只存 `.env` 或 `~/.evomap/`，不进 `.env.example`/Git/日志。
- 客户端传来的 `payment_proof` 一律拒绝（`_reject_unverified_payment_proof`）。
- 会话 Cookie 仅 `/auth/*` + WS 在线 presence 用；**点单链路（`/chat`、`/skill/orders`）全程不依赖登录**。

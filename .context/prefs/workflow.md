# Development Workflow Rules

> 此文件定义 LLM 开发工作流的强制规则。
> 所有 LLM 工具在执行任务时必须遵守，不可跳过任何步骤。

## Full Flow (MUST follow, no exceptions)

### feat (新功能)
1. 理解需求，分析影响范围
2. 读取现有代码，理解模式（优先用 CodeGraph `codegraph explore`）
3. 编写实现代码
4. 编写对应测试
5. 运行测试，修复失败
6. 更新文档（若 API 变更）
7. 自查 lint / type-check

### fix (缺陷修复)
1. 复现问题，确认症状
2. 定位根因（不要只修表象）
3. 编写失败测试（先有红灯）
4. 修复代码
5. 验证测试通过（变绿灯）
6. 回归测试

### refactor (重构)
1. 确保现有测试通过
2. 小步重构，每步可验证
3. 重构后测试必须全部通过
4. 不改变外部行为

## 项目专属红线 (Coffee AI Boss)

- **点单链路不要加登录门槛**：`/`、`/chat`、`/skill/orders`、3D 场景所有路由均为匿名可访问。
- **LLM 绝不直接写库**：所有扣款/下单在 `services/` 层事务内完成。
- **可视化事件双端同步**：新增事件类型必须同时更新前端 `sim/roleMap.ts`。
- **Colyseus 已归档**：不要再依赖 `colyseus_bridge.py` 做可视化（启动为 no-op）。
- **uvicorn 启动**：用 `--reload-dir app` 限定 watch 范围，规避根目录 `_mock_hub.py` 干扰。

## Context Logging (决策记录)

当你做出以下决策时，MUST 追加到 `.context/current/branches/<当前分支>/session.log`：

1. **方案选择**：选 A 不选 B 时，记录原因
2. **Bug 发现与修复**：根因 + 修复方法 + 教训
3. **API/架构决策**：接口设计选择
4. **放弃的方案**：为什么放弃

追加格式：

```
## <ISO-8601 时间>
**Decision**: <你选择了什么>
**Alternatives**: <被排除的方案>
**Reason**: <为什么>
**Risk**: <潜在风险>
```

## 卡顿/循环协议

当 CCG 系统提示 `LOOP DETECTED` 时：
1. **立即停止**当前做法
2. 根因分析：为什么这个 phase 不推进？
3. 选项：(a) 换替代方案 (b) 上报用户 (c) 升级 strategy
4. 被外部依赖阻塞 → 明确告诉用户
5. **不要重复同一动作**——那就是造成循环的原因

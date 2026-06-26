# 充值功能实施计划

## 需求
- 用户信息卡片余额右侧加"充值"按钮
- 弹窗输入：EvoMap Node ID + Node Secret + 积分数
- 比例标注：1 积分 = 100 元
- 积分从用户自己的 EvoMap 节点扣除
- 充值后本地 RMB 余额增加

## 技术现状
- 现有 service listing: `cmqmeayol0da86138a33zhx9h`，price_per_task=1 credit
- 现有 `place_service_order()` 函数：用消费者凭证调 `/a2a/service/order`，每次扣 1 credit
- 现有 `wallet_service.topup()`：给本地钱包加 RMB

## 实施步骤

### 1. 后端：新增 `POST /wallet/topup`（main.py）

```python
class TopupRequest(BaseModel):
    user_id: int
    evomap_node_id: str        # 用户的 EvoMap 节点 ID
    evomap_node_secret: str    # 用户的节点密钥
    credits: int               # 要消耗的积分数（正整数）

class TopupResponse(BaseModel):
    success: bool
    credits_used: int          # 实际扣除的积分
    rmb_added: float           # 实际到账金额
    new_balance: float         # 充值后余额
    message: str
```

**逻辑：**
1. 校验 credits >= 1
2. 循环 N 次调 `place_service_order`（每次扣 1 credit）
   - request_id 格式: `topup-{user_id}-{timestamp}-{i}`
   - consumer_node_id = 用户输入的 node_id
   - node_secret = 用户输入的 node_secret
   - coffee_names = [f"充值{i+1}"]
3. 统计成功次数 success_count
4. `wallet_service.topup(amount=success_count * 100)`
5. 返回结果

**错误处理：**
- 如果第 K 次失败（402 余额不足），停止循环，前 K-1 次已扣成功
- 按 success_count × 100 加 RMB
- 返回部分成功信息

### 2. 前端：充值按钮 + 弹窗（index.html）

**HTML 改动：**
- 余额行（#userBalance）旁边加按钮 `[💰 充值]`
- 新增模态框 `#topupModal`：
  - 输入框：EvoMap Node ID
  - 密码框：Node Secret
  - 数字输入框：积分数量（min=1, max=100, step=1）
  - 实时显示：预计到账 `N × 100` 元
  - 比例说明："1 EvoMap 积分 = 100 元"
  - 确认 / 取消按钮

**JS 改动：**
- `openTopup()` / `closeTopup()`：控制弹窗开关
- 积分输入实时计算 RMB
- `confirmTopup()`：fetch POST /wallet/topup，成功后刷新余额 + 关闭弹窗

### 3. 文件改动清单

| 文件 | 改动 |
|------|------|
| `app/main.py` | 新增 TopupRequest/TopupResponse 模型 + POST /wallet/topup 端点 |
| `app/static/index.html` | CSS（弹窗样式）+ HTML（按钮+弹窗）+ JS（充值逻辑）|

### 4. 充值流程

```
用户点击"充值"
  → 弹窗输入 node_id + node_secret + 积分数 N
  → 确认
  → POST /wallet/topup {user_id, evomap_node_id, evomap_node_secret, credits: N}
  → 后端循环 N 次调 EvoMap service/order（每次扣 1 credit）
  → 统计成功次数 K
  → 本地钱包 += K × 100 元
  → 返回 {success, credits_used: K, rmb_added: K*100, new_balance}
  → 前端刷新余额显示
```

### 5. 风险与限制
- 循环下单 N 次，每次约 0.5-2s，最大 100 积分 → 最坏 ~200s（太慢）
- **优化：限制单次最大 20 积分**（20 次 × ~1s = ~20s 可接受）
- 部分失败：已成功的扣款不可撤销，按实际成功数加 RMB

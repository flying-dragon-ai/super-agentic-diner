---
name: csharp-cs-to-java-hbsk
description: 将遗留 C# WinForms/WCF/BLL/DAL 页面或服务迁移到 HBSK Java/Spring 分层实现；当用户给出 C# 页面类、按钮事件、ServiceManager/WCFContract、BLL/DAL/SQL 入口、Java Controller/Service/Mapper 对照入口，要求按 JAVA代码位置/C#代码位置排查并修复业务逻辑等价性，尤其关注查询条件遗漏、写库副作用不等价、DTO/VO 字段契约漂移、确认流程差异和 Controller @Operation(summary) 对齐 C# Designer 界面显示名的问题；前端不知道该调用哪个 Java 接口、返回 VO 参数个数/中文释义与 C# Designer/旧页面不一致，或使用“C# UI事件接口追踪”询问 Designer.cs 页面有几个 UI 事件、分别调用哪些接口时使用。必须用 CodeGraph/evidence pack 做完整调用链取证、控制上下文占用、处理 queryCheckDetail/规则设置/ModifyLoad 等高频迁移返工点、leftWhereStr/权限码/SQL 拼接反模式，并在生成 Java 前通过业务门禁和现代 Java 可读性门禁。
---

# C# -> Java/HBSK Migration Skill

目标：把 C# C/S 企业应用页面或服务迁移为 HBSK Java 21 + Spring Boot 3 实现。优先保证业务语义、数据一致性、调用链完整性、权限/事务/SQL/数据库副作用等价，同时保证生成后的 Java 可读、可维护、符合 HBSK 分层。

## 启动硬规则

1. 先生成或读取 evidence pack，再做迁移判断；没有 evidence pack 不得声明等价，不得生成 Java。
2. C# 取证优先用 CodeGraph，BizModule 根路径固定为 `D:/codingProjects/#Net_副本/Source/BizModule`；HBSK Java 根路径固定为 `D:/codingProjects/JAVA/HBSK`。
3. 调查必须全链硬追：UI/Form -> ServiceManager/WCFContract -> BLL -> DAL -> SQL/存储过程 -> Entity/DTO -> Java 当前资产。
4. 节省上下文不是少查代码，而是少贴源码。只把压缩证据、路径行号、关键窗口放进上下文，禁止整文件、大段源码、完整文件树输出。
5. 影响响应、SQL 条件、事务、写库副作用的证据不足时，标 `证据不足` 并阻断代码生成；权限、授权、资质证据按任务模式处理，普通迁移需分类，双入口业务等价修复模式只记录为 `权限无关`，不作为生成阻断。
6. 生成或修复 Java Controller 时，`@Operation(summary)` 必须优先来自 C# Designer `Caption/Text/Form.Text` 的界面显示名证据；业务解释、handler、Service 方法和多候选细节放入 `description` 或 evidence。
7. 用户说"当前""核验""复查"或给出运行时现象时，必须重新读取当前 Java/C# 文件、配置和测试；历史会话、memory、旧 evidence 只能作为线索，不得替代当前代码证据。
8. 动手修改前先列出计划文件并检查 `git status --short -- <planned-files>`；最终报告必须只覆盖实际改动文件。发现范围漂移时先停下来重定向，不顺手改无关 Controller、常量或工具类。
9. **Contract 字段使用验证**：翻译 C# Contract/BLL 接口为 Java 时，必须用 CodeGraph `callees` 确认 BLL 实现体内实际读取了 DTO/Entity 哪些字段。禁止将整个 C# DTO/Entity 当必须入参原样翻译为 Java；只把 BLL 实际消费的字段纳入 Java 请求对象或 DTO，未使用的字段标 `未使用` 或根据业务语义标 `合理裁剪`。

10. 业务门禁优先级：查询条件完整性、写库副作用完整性、字段契约完整性先于外观门禁执行；任一不通过，只能输出阻断原因和最小补证清单，不得生成 Java 补丁。

## 硬等价门禁（必须通过，阻断生成）

以下三条门禁是防业务逻辑不等价的核心，必须在所有装饰性门禁（@Operation 命名格式、VO 对齐表、UI 事件 benchmark 等）**之前**执行。任一不通过即阻断 Java 生成，不得用"已比较"这类空话勾选绕过。这三条门禁的直接来源是 voyID 失效真实返工案例：C# 按 `IYC_IVOY_ID` 过滤、Java `vesselToVesselCandidateWhere` 漏条件，传 voyID 仍返回全部。

### G1 查询条件完整性门禁（Query Condition Completeness）

覆盖范围远大于 `leftWhereStr`（动态 SQL 片段）。**必须逐条枚举 C# BLL/DAL 里的每个 WHERE 条件**，包括固定命令式条件（如 `whereClause = fieldImportVoyageID + "=" + iVoyId`）、`if(x.HasValue)` 守卫、状态码 `IN`、箱号/提单号 LIKE/IN，以及 `leftWhereStr` 动态片段。每条映射到 Java Mapper XML 对应 `<if>/<foreach>/#{}`，输出 diff 表：

```
C# 条件 | C# path:line | Java 条件 | Java path:line | 状态
```

规则：
- C# 有、Java Mapper XML 缺 → 标 `逻辑错误` 并阻断生成。唯一豁免：有 `path:line` 证据证明该 C# 条件在当前 Java 路径已失效/不适用。
- **null/HasValue 守卫必须逐项对齐**：C# `if(iVoyId.HasValue)` 必须对到 Java `<if test="param.xxx != null">`，二者之一缺失即 `逻辑错误`。voyID 案例正是此类：C# `GetTransferContainerListBy1` 在 `iVoyId.HasValue` 时按进口航次过滤，Java `vesselToVesselCandidateWhere` 既无 `IYC_IVOY_ID` 条件也无 `<if>` 守卫 → 传 voyID 返回全部。
- **区分进口/出口航次等易混列**：C# `fieldImportVoyageID = IYC_IVOY_ID`（进口），不得误用 `IYC_EVOY_ID`（出口）。映射时带列名证据。
- MyBatis 参数前缀必须与 Mapper 接口 `@Param` 一致（如 `param.xxx` 对应 `@Param("param")`），按 XML 现有写法取值，不凭空写参数名。
- SQL Gate 仍负责注入/参数化（`+` 拼接 → `#{}`/`<if>`），但**不替代本门禁**：参数化正确不等于条件齐全。

### G2 DTO/VO 字段机械计数门禁

把"Contract 字段使用验证"和"VO Designer Field Parity"从可选叙述升级为强制机械校验。涉及接口入参/出参或返回 VO 时**必须**：
- 打印 `C# 字段数` vs `Java 字段数`（同一计数口径：visible-designer-fields / all-bound-fields 等，注明口径）。
- 给出「缺字段」「多字段」清单，逐字段标 `path:line` 证据。
- response VO 字段个数/中文释义与 C# Designer 不一致必须列入差异矩阵，不得用"已比较"搪塞。
- 未给计数的行视为未完成，阻断生成。字段数对齐是必要非充分条件：个数相同仍需逐字段语义核对。

### G3 运行时值验证门禁（Runtime Value Verification）

查询/过滤/排序类迁移的验证段强制**运行时证明**，不接受纯文本或纯叙述：
- 渲染真实 Java SQL（MyBatis BoundSql 或等价），非仅文本断言，证明 OGNL/record 组件/`@Param` 在运行时解析正确。
- 用具体非空值证明结果集正确收窄；用 null 值证明旧行为保留。
- 基准范本（voyID 修复）：BoundSql 渲染出 `c.IYC_IVOY_ID = ?`（非 null）且 null 时该条件被省略；HBSK-Oracle 实库 `voyID=410420` 返回 200 行全部 `IYC_IVOY_ID=410420`（badVoy=0），null 时跨 6 个航次。
- 写库/状态类迁移用真实库或测试做副作用核对，不得只靠编译通过声明等价。

### 门禁优先级

G1/G2/G3/G4/G5 是硬阻断门禁。Controller Operation Summary 命名格式、UI 事件 benchmark、@Operation description 六字段等"接口契约/外观"门禁是次要的，不得因装饰性门禁占满注意力而跳过业务门禁。

### G4 写库副作用完整性门禁

保存、提交、校验、处理类迁移必须逐分支比较当前行、选中行、修改行、全量请求行和确认弹窗语义，并核对事务、状态变更、审计日志、关联表写入、异常消息与返回提示。Java 不能把 C# 的局部选中行操作改成全量操作，也不能把 C# 的二段式确认改成单次成功/失败；写库目标、分支范围或事务边界无法证明时，标 `证据不足` 并阻断生成。

### G5 字段契约完整性门禁

契约字段不仅看总数，还要看 BLL 实际使用、请求/返回方向、隐藏/显示/兼容字段、`ref`/`out` 输出归属和默认值语义。Java 请求 DTO 只保留 BLL 实际消费的字段；`ref`/`out` 映射为 Java VO 返回字段；展示、下拉和兼容字段必须单独列入矩阵。字段个数相同但语义、方向或可见性不一致时，结论仍是 `逻辑错误` 或 `证据不足`，不能用数量相等蒙混通过。

## C# UI事件接口追踪模式

当用户使用 `C# UI事件接口追踪`，或给出 WinForms `.Designer.cs`/页面类并询问"这个页面有几个 UI 事件、分别调用哪些接口"时，进入此模式。此模式只做 C# 页面事件到接口调用链取证，不生成 Java，不做等价判断；若用户同时要求迁移或修复，再切换到完整迁移/双入口等价修复模式。

追踪要求：

1. 先用 CodeGraph 定位页面 class、Designer partial、code-behind partial；`rg` 只补充 CodeGraph 缺口或精确路径。
2. 从目标 Designer 的 `InitializeComponent` scoped 解析事件订阅，记录控件名、Caption/Text、事件类型、Designer 行号、handler。
3. handler 只在同一个 partial class/code-behind 中锚定；遇到全局同名 handler，不得用未限定 CodeGraph 结果替代。
4. 默认全链追踪：`event -> handler -> 本地 helper/回调/PerformClick -> ServiceManager<T>/WCF Contract -> BLL/实现 -> DAL/SQL/存储过程`。
5. 无接口调用、仅 UI 行为、注释掉的接口调用、无法静态确认的 BLL/DAL/SQL 链路必须显式标记；下游证据不足时标 `证据不足`，不得编造链路。

## 双入口业务等价修复模式

当用户给出或上下文可解析出 `JAVA代码位置` 与 `C#代码位置` 时，进入此模式。代码风格可以不同，但 C# 代码执行后的业务预期是基准；Java 入口及业务相关下级方法必须在过滤、排序、默认值、空值、异常、事务、写库副作用、状态变更、返回字段上保持一致。

> 本模式必须执行 §硬等价门禁 的 G1（查询条件完整性）、G2（DTO/VO 字段计数）、G3（运行时值验证）。其中"过滤"不等价是最常见返工源，禁止只用叙述核对，必须输出 G1 的条件 diff 表。

位置解析顺序：

1. 用户显式提供的路径、`path:line`、类名、方法名。
2. 近期对话中的 Java/C# 入口锚点。
3. CodeGraph `query/callers/callees` 对两侧入口做符号定位。
4. `rg` 只用于补充 CodeGraph 缺口或路径片段定位。

若任一侧出现多个可信候选，必须先询问用户确认；若任一侧无法锚定真实 `path:line + symbol`，不得声明等价，也不得重写 Java。

排查要求：

- C# 必须追到 UI/Form、ServiceManager/WCFContract、BLL、DAL、SQL/存储过程、Entity/DTO 中所有影响结果的下级方法。
- Java 必须追到 Controller、Service/ServiceImpl、私有 helper、Mapper/XML、Feign/ExpService、DTO/VO/DO、配置和现有测试中所有影响结果的下级方法。
- Java Controller 的 `@Operation(summary)` 必须回溯到 C# Designer 显示名；无法证明来源时标 `证据不足` 或在 Controller summary evidence 中列出低置信候选。
- 差异矩阵必须按业务点记录 C# expected behavior 与 Java actual behavior；发现 Java 当前实现与 C# 业务不一致且证据完整时，结论标 `逻辑错误`，并在同一任务内定点重写 Java。
- 证据不足时标 `证据不足`，只输出阻断原因和最小补证清单，不用猜测替代等价判断。
- 本模式下权限、授权、资质类差异全部作为 `权限无关` 记录，不纳入业务等价判断，不触发 Java 重写。

## 近期 HBSK 返工门禁

以下门禁优先适用于用户说"前端不知道调哪个接口""返回数据与 C# Designer 对不上""VO 参数个数少/中文释义不对""queryCheckDetail/详细""规则设置""ModifyLoad""接口很慢/缓存不稳定"等场景。

1. 接口契约先行：先输出 `C# 可见动作/控件 -> handler -> Contract/BLL -> Java route -> request -> response VO -> read/write -> @EndpointLog` 矩阵。前端调用口径不清时，不得先改 DTO 或 Service。
2. 详情页门禁：遇到 `详细(&D)`、双击列表、`queryCheckDetail`、`/details/query` 或"进口资料校验详细信息"，必须追 `ImportInfoCheckMainForm.bbiShowDetail`/双击 -> `IVoyageCheckLog.GetCheckResults(... six ref lists ...)` -> 构造 `ImportInfoCheckDetail` -> Detail Designer tabs/events/service calls。Java `ImportInfoCheckDetailVO` 必须解释六组传入列表和七个 tab 的数据来源；缺失时标 `逻辑错误` 或 `证据不足`。
3. VO/Designer 字段门禁：遇到返回 VO、表格列、字段个数、中文释义、`@Schema(description)`、`Caption/Text` 不一致时，必须从 C# Designer 提取每个数据展示控件/列的 `Name`、`FieldName/DataBindings`、`Caption/Text`、`Visible`、`VisibleIndex` 和运行时可见性，再逐项映射到 Java VO 属性、JSON 字段名、`@Schema` 中文说明。字段少、中文释义不一致、把隐藏列当可见列、或漏掉 tab 内列表字段时，标 `逻辑错误` 或 `证据不足`。
4. 规则设置门禁：遇到 `规则设置(&I)`、`rule-settings`、`saveRuleSettings`、`DMS_CHECK_CNFIG` 或 `DMS_CHECK_RULE`，必须追 `bbiImport_ItemClick` -> `PropCheckRuleUC` -> 加载校验属性规则和规则类型 -> 保存 `HandleAccordPropsRules`。`Meaning` 的 `null`、空串、默认等于 `LowValue` 语义必须单独列入差异矩阵。
5. 保存确认门禁：C# `Yes/No`、`MessageBox`、可继续的警告不是后端硬失败；Java 应返回 `needConfirmItems`、确认标志或等价的二段式协议。只有 C# 也会阻断保存的场景才能直接抛业务异常。
6. 多分支/选中行门禁：保存类接口必须比较当前行、选中行、修改行、全量行的语义，并列出 C# 分支矩阵。Java 把 C# 当前行操作改成全量请求操作时，除非用户明确认可，否则标 `逻辑错误`。
7. 运行时与性能门禁：用户给出 curl、voyageId、接口慢、缓存 300 秒但不稳定等现象时，先追 Java 真实调用链，再用 HBSK-DB/HBSK-Redis 做只读验证。结论必须区分 SQL 慢、N+1/循环慢、缓存 key/TTL/击穿问题、序列化/DTO 组装问题和前端等待问题。
8. 请求解析门禁：看到"入参报错""原始 prompt: fix bug"时，先区分 JSON 语法解析、`@RequestBody` 绑定、Bean Validation、Controller 进入、Service 业务异常、数据库异常六层，不能直接把数据库报错归因到 DTO。
9. 工具复用门禁：新增 JSON、集合批处理、字符串/日期、SQL 安全、Redis/cache、DTO 转换、Oracle `IN` 分批等 helper 前，先按仓库 `AGENTS.md` 检索 HBSK starter/core 既有工具和 MapStruct converter；找不到合适工具时再新增，并在最终说明原因。
10. **Contract 字段使用验证门禁**：生成或审查 Java 接口、Service 方法、DTO 时，必须通过 CodeGraph `callees` 追 C# BLL 实现体的字段使用，确认 BLL 实际读取了 DTO/Entity 哪些字段。将 BLL 实际消费的字段逐项映射到 Java DTO/Param，未使用的字段标记为 `未使用` 或 `合理裁剪`。禁止将 C# Contract 的整个 Entity 参数（如 `BizDataEntitySet<ContractEntity>`、`ContractEntity` 裸对象）当作 Java 请求对象必须包含的字段。`ref`/`out` 输出参数对应 Java VO 返回字段，不是入参。证据不足时不得推断字段用途，必须标 `证据不足`。

## Controller Operation Summary 门禁

当用户要求迁移/修复 Controller、审计 `@Operation(summary)`，或 Java 入口是 Controller 方法时，必须执行此门禁。

### 命名规则

1. `summary` 使用 C# Designer 的用户可见显示名：控件 `Caption`、控件 `Text` 或窗口/弹窗 `Form.Text`。
2. 去掉快捷键后缀，例如 `检索(&F)` -> `检索`、`刷新(&R)` -> `刷新`；保留业务括号，例如 `船箱位校验(带过境箱)`。
3. 多个 C# 触发点对应同一 Java 方法时，`summary` 只取主触发控件；其余候选写入 `description` 或 evidence。
4. 没有直接按钮/菜单显示名的辅助接口，`summary` 取最近可证明的窗口/弹窗显示名；允许同一 Controller 下多个方法拥有相同 `summary`。

### Description 格式规范

`description` 必须使用 **"页面按钮索引卡"** 结构化短字段格式，禁止写成自然语言长句。格式如下：

```
C#页面: <Form类名>; 控件: <控件名>; Caption: <去掉快捷键的显示名>; 事件: <handler名>; Contract: <WCF接口.方法(参数摘要)>; 边界: <Java接口职责边界>
```

六个字段说明：

| 字段 | 来源 | 示例 | 必填 |
|------|------|------|------|
| `C#页面` | C# 页面 partial class 类名 | `ImportInfoCheckMainForm` | ✅ |
| `控件` | Designer 中触发事件的控件 Name | `bbiNotThroughCheck` | ✅ |
| `Caption` | 控件 `Caption`/`Text` 去掉快捷键后缀 | `船箱位校验` | ✅ |
| `事件` | Designer 事件订阅中的 handler 名 | `bbiNotThroughCheck_ItemClick` | ✅ |
| `Contract` | ServiceManager/WCF 调用的 `接口名.方法名` | `IVoyageCheckLog.CheckInBoundCntrsLocation` | ✅（证据不足时写 `证据不足`） |
| `边界` | Java 接口的职责边界说明 | `主页面校验，不含过境箱` | ✅ |

Contract 字段格式说明：
- 基础格式：`接口名.方法名`（如 `IVoyageCheckLog.CheckInBoundCntrsLocation`）
- 当 C# 调用链包含关键参数语义时追加：`接口名.方法名(param语义)`（如 `CheckVoyageLocation(_voyageID, true)`）
- 多个 Contract 调用时用 `+` 连接：`接口A.方法A + 接口B.方法B`
- 如果无法通过 CodeGraph 确认 Contract，写 `证据不足`

特殊场景处理：
- **兼容入口**（同一个 Java 接口同时服务多个 C# 触发点时）：`C#页面` 字段改为 `兼容入口: true`，`事件` 和 `控件` 字段列出所有触发点。
- **弹窗/子页面触发**：`控件` 字段写 `触发: <Form_Load>`，`事件` 字段写子页面初始化方法。
- **无按钮触发**（如 Load/FormClosing）：`控件` 字段写 `窗口事件`。
- **证据不足的字段**：直接写 `证据不足`，不猜测。

正确示例：

```java
@Operation(
    summary = "船箱位校验",
    description = "C#页面: ImportInfoCheckMainForm; "
               + "控件: bbiNotThroughCheck; "
               + "Caption: 船箱位校验; "
               + "事件: bbiNotThroughCheck_ItemClick; "
               + "Contract: IVoyageCheckLog.CheckInBoundCntrsLocation(voyageID, false); "
               + "边界: 主页面校验，不含过境箱")
@PostMapping("/vessel-locations/validate")
```

```java
@Operation(
    summary = "提交",
    description = "C#页面: ModifyLoadManageForm; "
               + "控件: bbiSave; "
               + "Caption: 提交; "
               + "事件: bbiSave_ItemClick; "
               + "Contract: IModifyLoad.SaveModifyLoadPlan(voyID, modifyType, modifyReason, modifyProposer, changeCntrEVoys, ref hintInfo); "
               + "边界: 保存改装计划并改航次，含海关放行/复关收费分支")
@PostMapping("/save")
```

```java
@Operation(
    summary = "溢缺校验",
    description = "兼容入口: true; "
               + "主入口: POST /over-short-checks/execute; "
               + "C#页面: ImportInfoCheckMainForm; "
               + "控件: bbiOverflowCheck; "
               + "Caption: 溢缺校验; "
               + "事件: bbiOverflowCheck_ItemClick; "
               + "Contract: IVoyageCheckLog.SaveVoyageCheckLog")
@PostMapping("/voyage-check-logs/save")
```

禁止以下写法：
- ❌ 自然语言长句：`"对应旧主页面 ImportInfoCheckMainForm 的船箱位校验按钮点击事件..."` — 前端 Swagger 读起来不直观
- ❌ 省略字段：必须六个字段齐全，不可只写 3-4 个
- ❌ 自由格式：不得自创字段名，必须用上面六个标准字段名
- ❌ 用 handler 名、Service 方法名、REST 路径名作为 `summary`

### 匹配质量门禁（防错配核心规则）

以下规则直接针对 skill 脚本 `build_evidence_pack.py` 的已知缺陷，在执行 `controller-operation-summary` 模式时必须逐条校验：

**R1: 唯一候选原则**

- 一个 Java 方法只能映射到**一个** C# 触发点。如果匹配到多个候选（`candidate_count > 1`），**不得生成 patch**，必须在 evidence 中列出所有候选并请求用户确认。
- 原因：同一 Service 方法被多个 C# 按钮调用时（如 `bbiFind` 和 `bbiRefresh` 可能都调用 `LoadData`），token overlap 无法区分业务意图。

**R2: Handler 锚定优先**

- 优先匹配显式写在 Java Javadoc / `@Operation(description)` 中的 C# handler 名（如 `bbiFind_ItemClick`）。
- 次优先：Java Service 方法名与 C# handler 名精确对应（如 Java `queryGoods` -> C# `bbiFind_ItemClick`）。
- token overlap 匹配（`service-token-back-reference`）作为最低优先级兜底，**置信度为 `low`，不得直接生成 patch**。

**R3: 方法名语义校验**

- Java 方法名（如 `save`、`queryGoods`、`getVoyagePorts`）必须与 C# handler 的语义一致。`save` 不能映射到 `bbiFind_ItemClick`（查询），`queryGoods` 不能映射到 `bbiSave_ItemClick`（保存）。
- 校验方式：Java 方法名中的动词（save/query/get/delete/update/init/print）必须与 C# Caption 的业务语义一致。
- 不一致时标记为 `need-confirm`，强制用户介入。

**R4: Patch 生成阻断条件**

以下任一条件成立时，禁止生成 `@Operation` 补丁：

| 条件 | 阻断原因 |
|------|---------|
| `candidate_count > 1` | 多候选无法确定唯一映射 |
| `confidence` 为 `low` | token overlap 兜底匹配不可靠 |
| `confidence` 为 `need-confirm` | 无法确定映射关系 |
| Java 方法名与 C# Caption 语义冲突 | 映射关系可能存在错误 |

**R5: 方法缺失检测**

- 如果 Java Controller 中有方法在 C# 页面找不到对应触发点，标记为 `extra-in-java`（Java 新增接口）。
- 如果 C# 页面有按钮在 Java Controller 中找不到对应方法，标记为 `missing-in-java`。
- 两者都必须在最终报告中列出，不能遗漏。

**R6: 同名方法多页面消歧**

- 当一个 C# handler 名（如 `bbiSave_ItemClick`）在多个 C# 页面存在时，必须结合 `--csharp-location` 的传入顺序和 Java description/Javadoc 中的页面类名来消歧。
- 无法消歧时标记 `证据不足`。

### 主触发控件选择顺序

1. Java Javadoc 或 `@Operation(description)` 显式写出 C# handler 时，取该 handler 对应控件。
2. 能通过 Java Service 方法唯一反查到 C# active-interface event 时，取该 event 控件。
3. 多候选时，`ItemClick` / `Click` 按钮或菜单优先于 `Load`、`FormClosing`、Grid 事件、焦点变化、双击事件。
4. MainForm 和 Detail 都有候选时，优先取 Java description/Javadoc 指向的页面；没有指明时按用户传入 `--csharp-location` 的顺序。
5. 仍并列时取 Designer 行号最小的候选，并在 evidence 标记 `multiple-candidate`；低置信或 `证据不足` 不生成 Java 补丁。

## Evidence Pack 流程

优先运行脚本：

```powershell
# 从 .claude/skills/csharp-cs-to-java-hbsk/ 使用时：
python D:/codingProjects/JAVA/HBSK/.claude/skills/csharp-cs-to-java-hbsk/scripts/build_evidence_pack.py --csharp-entry "<C#入口类/方法/路径>" --java-entry "<可选Java入口>" --mode full-chain
python D:/codingProjects/JAVA/HBSK/.claude/skills/csharp-cs-to-java-hbsk/scripts/build_evidence_pack.py --csharp-location "<C#代码位置>" --java-location "<JAVA代码位置>" --mode equivalence-repair
python D:/codingProjects/JAVA/HBSK/.claude/skills/csharp-cs-to-java-hbsk/scripts/build_evidence_pack.py --csharp-location "<C# Designer.cs 或页面.cs>" --mode ui-events
python D:/codingProjects/JAVA/HBSK/.claude/skills/csharp-cs-to-java-hbsk/scripts/build_evidence_pack.py --mode controller-operation-summary --java-location "<Java Controller.java>" --csharp-location "<C# Designer.cs>" [--csharp-location "<另一个 Designer.cs>"] [--emit-operation-patch]
# Contract 字段使用验证（自动在 BLL callees 存在时触发）：
python D:/codingProjects/JAVA/HBSK/.claude/skills/csharp-cs-to-java-hbsk/scripts/build_evidence_pack.py --csharp-entry "<Contract接口名>" --mode full-chain --contract-field-usage

# 从 .agents/skills/csharp-cs-to-java-hbsk/ 使用时，将上述路径中的 .claude 替换为 .agents 即可。
```

如果脚本不可用，按同等规则手工执行：

```powershell
codegraph query -p "D:/codingProjects/#Net_副本/Source/BizModule" --json --limit 10 "<symbol>"
codegraph callers -p "D:/codingProjects/#Net_副本/Source/BizModule" --json --limit 20 "<symbol>"
codegraph callees -p "D:/codingProjects/#Net_副本/Source/BizModule" --json --limit 20 "<symbol>"
codegraph query -p "D:/codingProjects/JAVA/HBSK" --json --limit 10 "<java-symbol>"
```

Evidence pack 只保留：`symbol`、`path:line`、`role`、`behavior`、`risk`、`next-hop`、必要源码窗口。读取详细规则：`references/context-budget-protocol.md`。

## 必读 Reference

在生成迁移方案或代码前，按需读取：

- `references/context-budget-protocol.md`：上下文预算、CodeGraph/rg 取证方式、evidence pack 格式。
- `references/csharp-evidence-gates.md`：C# 真实反模式门禁，尤其是 `leftWhereStr`、`HasPermission`、SQL 拼接、UI 状态。
- `references/java-output-quality.md`：Java 可读性和 HBSK 分层门禁。
- `references/output-template.md`：固定输出结构、位置解析、差异矩阵、生成前核对清单。

## 强制业务闭环

页面级迁移必须覆盖：构造函数、Load/FormShown、`LoadData/InitData/Bind*`、按钮/菜单/网格事件、私有辅助方法、页面字段、DataSource、FocusedRowHandle/选中行、enable/visible/readOnly、弹窗确认、异常提示。只迁移用户粘贴的方法片段是不合格输出。

服务级迁移必须覆盖：Contract/WCF 方法签名、BLL 编排、DAL SQL/存储过程、实体字段、默认值、排序、空值语义、权限、事务、缓存、批处理和写库副作用。

Java 当前资产必须检索：Controller、Service/ServiceImpl、私有 helper、ExpService/Feign、Mapper/XML、DTO/VO/DO、枚举、配置、测试。能复用的必须复用或追加，禁止重复造轮子。

## 特殊门禁

- `leftWhereStr`：只作为 C# 动态 SQL 证据，不允许原样变成 Java 字符串参数；必须判断是否真实生效，真实进入 DAL SQL 时拆成 typed criteria + MyBatis 参数化/白名单条件。
- 权限码：区分 UI 控制、后端授权、业务资质；只迁移正向授权和业务资质。排除权限、绕过权限、管理员特殊通道、硬编码跳过权限一律标风险或 `证据不足`，不得复制。
- SQL：C# 字符串拼接 SQL 必须转换为 `#{}` 参数、`<if>` 条件、枚举/白名单动态字段；`${}` 只允许封闭白名单场景。
- Java 风格：Controller 保持瘦，Service 承载业务编排，Mapper/XML 只做数据访问，DO/DTO/VO/Param 分离，禁止把 WinForms 控件状态和 DataTable 思维搬进 Java。

## 输出要求

使用 `references/output-template.md` 的结构。必须包含：入口锚定、Location Resolution、Evidence Pack Summary、Business Logic Gate Summary、Query Condition Diff、Write Side Effect Matrix、Field Contract Matrix、HBSK Recent Failure Gate Check（命中近期返工触发词时）、VO Designer Field Parity（涉及返回 VO 或 UI 字段时）、C# Full Chain、Java Current Assets、Equivalence Matrix、`leftWhereStr` Decision、Permission Decision、Pre-generation Checklist、Implementation Plan/Code、Verification、No-Code Blockers / 剩余待确认项。

`C# UI事件接口追踪` 模式使用 `UI Event Interface Trace` 结构，必须包含事件总数、handler 锚点、接口调用链、下游 Contract/BLL/DAL/SQL 证据、无接口/注释/`证据不足` 状态；该模式不要求 Java Current Assets 和 Equivalence Matrix。

`controller-operation-summary` 模式使用 `Controller Operation Summary Evidence` 结构，只审计/建议 Controller `@Operation(summary)` 与 C# Designer 显示名的对应关系；`--emit-operation-patch` 只输出补丁文本，不自动应用，不修改业务代码。

差异矩阵结论只允许：`行为等价`、`合理调整`、`逻辑错误`、`证据不足`、`权限无关`。

生成前核对清单必须保留 `[ ]/[x]`。若影响功能或写库的检查项未完成，只输出阻断原因和最小补证清单，不生成 Java。

## 验证闭环

至少给出一个可复现业务样本，例如航次、箱号、单号、权限码、操作按钮或写库记录。验证必须比较 C# 与 Java 的行数、关键 ID、字段值、过滤条件、排序、状态变更、异常消息和数据库副作用。查询/过滤/排序类任务必须给出 `Query Condition Diff`；写库类任务必须给出 `Write Side Effect Matrix`；契约/DTO/VO 类任务必须给出 `Field Contract Matrix`。Maven 验证遵守 HBSK Maven verification 规则，报告测试是否真实执行、测试数量和失败原因。

查询/过滤/排序类迁移的验证必须满足 §硬等价门禁 G3：渲染真实 Java SQL（MyBatis BoundSql 或等价）并用具体非空值/null 值证明结果集正确收窄与旧行为保留，不得仅靠文本断言或编译通过声明等价。voyID 修复（BoundSql 渲染 `c.IYC_IVOY_ID = ?` + HBSK-Oracle 实库 200 行全满足该航次、null 时跨 6 航次）是本门禁的基准范本。

优化 `C# UI事件接口追踪` 时，必须运行 `scripts/benchmark_ui_events.py --runs 2 --out references/ui-events-benchmark-baseline.md` 或与现有 `references/ui-events-benchmark-baseline.md` 对比的等价命令。六个基准维度（事件覆盖、handler 锚定、接口调用、间接链路、下游证据、重复稳定性）不得低于现有基线，且不得新增 per-case misses。

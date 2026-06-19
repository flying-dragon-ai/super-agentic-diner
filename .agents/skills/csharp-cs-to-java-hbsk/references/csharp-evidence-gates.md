# C# Evidence Gates

## Real BizModule Findings

真实 BizModule 代码显示：`leftWhereStr` 常见于 DMS/BPS 页面字段，经 `DMSUICommon.ParseCondition(...)` 从查询条件拼出，再传入 WCF/BLL/DAL。部分页面已注释相关调用，因此不能默认迁移。

`ImportEmptyPass` 链路示例：

```text
DMSUICommon.ParseCondition -> ImportEmptyPassForm.LoadData -> IImportEmptyPass.GetImEmptyContainers -> ImportEmptyPassBLL.GetImEmptyContainers -> ImportEmptyPassDAL.GetImEmptyContainers -> getSql + " And " + leftWhereStr
```

## leftWhereStr Gate

`leftWhereStr` 是 C# 动态 SQL 条件片段，不是 Java API 模型。

分类：

- `unused`：字段存在但未进入服务或 SQL，不迁移。
- `commented-out`：相关调用注释掉，不迁移，记录历史遗留。
- `sql-fragment`：进入 BLL/DAL 并参与 SQL 拼接，必须拆 typed criteria。
- `证据不足`：无法追到 DAL/SQL 或字段来源不明，阻断生成。

迁移规则：

- 禁止 Java 保留 `leftWhereStr`、`whereStr`、`sqlCondition` 等自由 SQL 入参。
- C# 条件必须转换为明确字段的请求对象，例如 voyageId、containerNos、billNos、statusCodes、portCode 等。
- Mapper XML 使用 `#{}`、`<if>`、`<foreach>`、白名单字段/操作符。
- 动态排序、动态字段、动态操作符必须用 enum/白名单封闭。

## Permission Gate

`HasPermission`/`CheckRight` 必须分类后迁移：

- `ui-only`：只控制按钮、列编辑、visible/enabled，默认交给前端或响应权限提示，不上升为后端业务规则。
- `backend-auth`：BLL、Service、写库命令前的 `CheckRight(GetPermCode)` 或等价判断，迁移为后端正向授权。
- `business-qualification`：司机资质、危险品资质、作业资格等，迁移为业务规则校验。
- `bypass-or-exclusion`：排除权限、绕过权限、管理员特殊通道、`if (true)//HasPermission`，标风险或 `证据不足`，不得复制。

不要复制 C# 端“排除权限”。只保留正向授权点和业务资格校验。

双入口业务等价修复模式覆盖规则：当任务目标是按 `JAVA代码位置` 与 `C#代码位置` 修复业务等价时，权限、授权、资质类差异全部作为 `权限无关` 排除。仍可收集权限证据以解释差异来源，但不得因为权限差异阻断生成，也不得把权限差异作为 Java 业务重写目标。

## UI State Gate

WinForms 控件状态不能机械迁移到 Java。只迁移影响数据、默认值、权限、状态流转、确认流程、写库副作用的 UI 语义。纯展示、布局、列宽、颜色、焦点样式不进入后端。

## SQL Gate

- C# `+` 拼接 SQL、`CommonDAL.GetStringList(...)`、`Like '" + value + "'` 都是风险证据。
- 迁移到 Java 时必须参数化，不能把拼接结果传入 Mapper。
- 找不到 SQL、存储过程或表字段含义时，输出 `证据不足`。
- Oracle 分区、函数、序列、`ROWNUM`、`NVL`、`LISTAGG` 等必须保留语义并记录差异。

## Query Condition Completeness Gate

查询类迁移必须逐条枚举 C# BLL/DAL 的最终过滤条件，再映射到 Java Mapper XML 或查询构造代码。不能只比较方法名、Controller 入参或 evidence pack 摘要。

必须覆盖：

- 固定命令式条件，例如 `whereClause = fieldImportVoyageID + "=" + iVoyId`。
- `if(x.HasValue)`、null/blank、默认值守卫。
- 航次、箱号、提单号、状态、分区、有效标志、作业状态、进出口方向等业务列。
- 单值 `LIKE`、多值 `IN`、前缀匹配、精确匹配分支。
- `leftWhereStr` 进入 DAL 后实际展开的条件。
- Join 子查询里的过滤条件，尤其是 goods/container relation、doctype、partition、valid 条件。

输出 `Query Condition Diff`。C# 有而 Java 缺的条件标 `逻辑错误` 并阻断生成；只有 `path:line` 能证明该 C# 条件在当前 Java 路径已失效时才可豁免。参数化正确不代表条件齐全。

## Write Side Effect Gate

写库类迁移必须比较 C# 与 Java 的实际副作用，不得只看返回消息或编译通过。

必须覆盖：

- 当前行、选中行、修改行、全量行四种范围语义。
- Yes/No、MessageBox、可继续警告、二段式确认、硬阻断异常。
- TransactionScope、BLL 事务、Spring `@Transactional`、外部服务调用边界。
- INSERT/UPDATE/DELETE/MERGE、存储过程、状态字段、审计日志、消息发送日志、关联表重建。
- C# 跳过空 ID、保留重复行、局部处理、批量处理等边界行为。
- 异常消息、返回提示、影响行数、写库后刷新/再校验行为。

输出 `Write Side Effect Matrix`。Java 将 C# 局部选中行语义改为全量请求语义、将软确认改为硬失败、漏写审计/关联表/状态字段，均标 `逻辑错误`。无法追到 DAL/SQL/过程或 Java Mapper/外部服务时标 `证据不足` 并阻断生成。

## Field Contract Gate

字段契约迁移必须区分“字段存在”和“业务使用”。C# Contract 的 Entity/DTO 参数不能整体照搬为 Java 请求 DTO。

必须覆盖：

- BLL 实际读取的输入字段，逐字段给出 `path:line`。
- BLL 写入、返回、`ref`、`out`、列表输出字段。
- Designer 可见字段、隐藏字段、运行时可见字段、下拉源字段、兼容别名。
- Java request DTO、response VO、OpenAPI `@Schema`、JSON alias、Bean Validation 的字段方向和必填性。
- 默认值、空串/null 语义、C# UI 可编辑但允许空的字段。

输出 `Field Contract Matrix`。Java request DTO 只包含 BLL 实际消费字段；`ref`/`out` 必须映射到 response VO；展示/下拉/兼容字段不能误设为请求必填。字段计数相同但语义、方向、中文释义或必填性不一致时，仍标 `逻辑错误` 或 `证据不足`。

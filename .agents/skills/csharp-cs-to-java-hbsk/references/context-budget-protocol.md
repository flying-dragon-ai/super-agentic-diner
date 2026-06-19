# Context Budget Protocol

## Goal

调查完整性不降级，上下文占用必须降级。迁移任务要追完整调用链，但进入模型上下文的内容必须是压缩证据包，而不是整文件源码。

## Investigation Order

1. Symbol first：用 CodeGraph `query --json --limit` 定位入口、同名方法、Contract/BLL/DAL/Java 资产。
2. Chain second：用 CodeGraph `callers/callees --json --limit` 追上下游。
3. Text third：用 `rg -n` 搜 `ServiceManager<`、方法名、`leftWhereStr`、`HasPermission`、`CheckRight`、SQL 关键字。
4. Window last：只读取命中行附近窗口。默认上下各 40 行；SQL 拼接、权限、事务、写库副作用允许上下各 80 行。
5. Full file never by default：只有 partial/designer 字段、页面级共享状态或文件小于 120 行时，才允许读完整文件。

## UI Event Interface Trace Order

Use this order for `C# UI事件接口追踪`:

1. Use CodeGraph first to locate the page class, Designer partial, and code-behind partial. For legacy C# use `-p "D:/codingProjects/#Net_副本/Source/BizModule"`.
2. Parse only the target Designer `InitializeComponent` event subscriptions. Record control, caption/text, event name, handler, and Designer line.
3. Resolve handlers only inside the same code-behind partial/class. Do not trust unqualified global same-name handler results.
4. Trace local helper methods, named event callbacks, and `PerformClick` indirections before reading WCF/ServiceManager calls.
5. Trace each active `ServiceManager<T>.Service.Method` to Contract and implementation/BLL with CodeGraph; then look for DAL/SQL/procedure evidence in callees or source windows.
6. Mark `no-active-interface`, `commented-out`, or `证据不足` explicitly. Do not omit UI events that have no service call.

## Dual-entry Equivalence Repair Order

Use this order when the task provides or implies `JAVA代码位置` and `C#代码位置`:

1. Resolve both locations to real `path:line + symbol` anchors. Accept explicit paths, `path:line`, class names, method names, or recent conversation anchors.
2. Use CodeGraph before broad text search for both sides. For legacy C# use `-p "D:/codingProjects/#Net_副本/Source/BizModule"`; for Java use `-p "D:/codingProjects/JAVA/HBSK"`.
3. Trace all business-affecting downstream methods on both sides. Include private helpers, Mapper/XML, Feign/ExpService, SQL/procedures, DTO/VO/DO mapping, transactions, and write side effects.
4. Use `rg` only to supplement missing CodeGraph results or path fragments.
5. If multiple plausible anchors remain for either side, ask the user to choose before judging equivalence.

## Controller Operation Summary Order

Use this order when auditing or generating Java Controller `@Operation(summary)` from C# UI display names:

1. Resolve Java Controller input. If `--java-location` is an existing absolute `.java` file, read it directly even when it is outside `D:/codingProjects/JAVA/HBSK`; use Java CodeGraph only for class/method symbols or when an indexed ancestor `.codegraph/codegraph.db` exists.
2. Resolve every provided `--csharp-location` in user order. For each WinForms page, locate Designer and code-behind partials and parse Designer `Caption/Text/Form.Text`.
3. Clean display names by removing shortcut suffixes such as `(&F)` or `（&F）`; keep business parentheses such as `船箱位校验(带过境箱)`.
4. Parse Controller methods, `@Operation(summary/description)`, request mapping path, Javadoc, and direct Service calls.
5. Pick the primary C# trigger by this priority: explicit handler in Java docs/description, unique Service-method back-reference, `ItemClick`/`Click` UI controls, `--csharp-location` order, Designer line.
6. For helper endpoints without a direct button/menu caption, use the nearest proven Form/Dialog `Text`. Repeated summaries are allowed; distinguish endpoints by method, path, and description.
7. Low-confidence or multiple unresolved candidates must emit evidence only. Generated patches must not modify Java files and must only replace `@Operation(summary/description)` text.

## Evidence Pack Format

每条证据使用短字段：

```text
- symbol: ImportEmptyPassBLL.GetImEmptyContainers
  path: DMS/SHB.TOPS.BLL.DMS/ImportEmptyPass/ImportEmptyPassBLL.cs:358
  role: BLL business orchestration
  behavior: checks GetPermCode, appends fixed container status filters, calls DAL
  risk: leftWhereStr remains SQL fragment until DAL
  next-hop: ImportEmptyPassDAL.GetImEmptyContainers
```

## Context Limits

- 第一轮只放 evidence pack，不放源码全文。
- 每个方法摘要不超过 5 行。
- 每个风险点最多附一个源码窗口。
- 不影响实现的 UI 展示细节只保留摘要和路径。
- CodeGraph `files` 输出禁止直接贴入上下文；只允许定向 `query/callers/callees/impact`。

## Required Evidence Classes

- Entry evidence：用户给出的 C#/Java 入口真实路径和行号。
- Chain evidence：UI/Form、Contract、BLL、DAL、SQL 每层至少一条路径行号。
- SQL evidence：动态 SQL、存储过程、Mapper/XML、表/字段/排序/过滤条件。
- Permission evidence：UI-only、backend-auth、business-qualification、bypass-or-exclusion 分类。
- Java asset evidence：当前 HBSK 可复用 Controller/Service/Mapper/DTO/DO/配置。
- Downstream equivalence evidence：每个影响业务结果的 C# 和 Java 下级方法都要有路径行号、行为摘要、输入输出、状态/写库副作用。
- Location resolution evidence：`JAVA代码位置`、`C#代码位置` 的来源、候选、最终锚点和歧义处理。
- UI event evidence：Designer 事件绑定总数、每个事件的 handler 锚点、handler/helper/回调链、ServiceManager/WCF 方法、Contract/BLL/DAL/SQL 证据、无接口/注释/`证据不足` 状态。
- Controller operation summary evidence：Java Controller 方法、mapping path、当前 summary、推荐 summary、C# 页面/控件/display name/handler、置信度、patch action。

## Contract Field Usage Verification

When translating C# Contract/BLL methods to Java, before defining Java DTO/Param fields, verify which C# Entity/DTO fields the BLL actually consumes:

1. Use CodeGraph `callees` on the BLL implementation method to find its body and field references.
2. Read a source window around the BLL method to confirm field reads (not just method calls).
3. Classify each C# Entity/DTO field as `used` (confirmed read in BLL), `output-only` (assigned as default/result), `unused` (not referenced in BLL), or `unconfirmed` (cannot prove).
4. `ref`/`out` parameters are always `output-only` in the Contract signature; they map to Java VO return fields, never to request DTO fields.
5. When a C# Contract takes a full Entity (e.g., `ContractEntity`, `BizDataEntitySet<ContractEntity>`), do NOT translate the entire Entity into a Java request DTO. Only include fields the BLL actually reads.
6. Fields used only by DAL/SQL but not by BLL logic (e.g., used in INSERT/UPDATE column lists) are still `used` and must be included.
7. If the BLL iterates over Entity properties generically (e.g., reflection, `foreach` property enumeration), mark as `indirect` and require user confirmation.

## Failure Rule

如果无法追到 DAL/SQL 或写库副作用，不能用”猜测”等价替代。输出 `证据不足` 和最小补证清单。权限位置缺失只在普通迁移模式下阻断；双入口业务等价修复模式中，权限、授权、资质差异只作为 `权限无关` 解释性证据，不阻断生成、不触发 Java 重写。Contract 字段使用验证不完整时，不得生成 Java DTO 字段声明。

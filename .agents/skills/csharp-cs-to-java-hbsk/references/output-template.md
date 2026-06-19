# Output Template

Use this structure for migration analysis and code output.

## Entry Anchoring

- C# entry: `<path:line> <symbol>`
- Java entry: `<path:line> <symbol>` or `not-found`
- Evidence pack command: `<command>`

## Location Resolution

Use this section when the task provides `JAVA代码位置` and `C#代码位置`, or when those locations are inferred from context.

- C# location source: `explicit-user-input` | `conversation-context` | `codegraph` | `rg` | `not-found`
- Java location source: `explicit-user-input` | `conversation-context` | `codegraph` | `rg` | `not-found`
- C# resolved anchor: `<path:line> <symbol>`
- Java resolved anchor: `<path:line> <symbol>`
- Ambiguity: `none` or `<candidate list requiring user confirmation>`

If either side is ambiguous or missing, stop at `证据不足` and do not declare equivalence or rewrite Java.

## Evidence Pack Summary

Summarize the investigation in 5-10 bullets. Include only paths, line numbers, roles, and behavior. Do not paste large source blocks.

## Business Logic Gate Summary

Use this section before any implementation plan or Java code. If any required gate is not complete, stop at `No-Code Blockers` and do not generate Java.

Summary fields:

- Query condition gate: `passed` | `逻辑错误` | `证据不足` | `not-applicable`
- Write side effect gate: `passed` | `逻辑错误` | `证据不足` | `not-applicable`
- Field contract gate: `passed` | `逻辑错误` | `证据不足` | `not-applicable`
- Runtime verification gate: `passed` | `证据不足` | `not-applicable`
- Implementation allowed: `yes` | `no`

Rules:

- Query/list/filter/sort tasks require `Query Condition Diff` and runtime SQL/value verification.
- Save/submit/process/status/audit tasks require `Write Side Effect Matrix`.
- DTO/VO/request/response/OpenAPI/Designer-field tasks require `Field Contract Matrix`.
- Evidence pack summaries are navigation aids only. `sql/dal-window: need-confirm`, missing Mapper XML, or missing BLL/DAL/source windows means the related gate is incomplete.

## Query Condition Diff

Use this section for any query, list, search, filter, sorting, dropdown-source, candidate-selection, or SQL-generating behavior.

Summary fields:

- C# condition count: `<count>`
- Java condition count: `<count>`
- Missing Java conditions: `<count>`
- Extra Java conditions: `<count>`
- Null/HasValue guard mismatches: `<count>`
- Column mapping mismatches: `<count>`

Table columns:

```text
C# condition | C# path:line | C# guard/null behavior | Java condition | Java path:line | Java @Param/XML prefix | status | action
```

Rules:

- Enumerate every C# BLL/DAL WHERE condition, including fixed string-built conditions, `if(x.HasValue)` guards, status `IN`, voyage columns, container/bill LIKE/IN, joins, partition/valid flags, and `leftWhereStr`.
- Map each condition to Java Mapper XML or query builder evidence. Parameterized SQL is not sufficient if a business condition is missing.
- Mark C# condition present but Java condition missing as `逻辑错误`, unless a `path:line` proves the C# condition is obsolete for the current Java path.
- Verify import/export voyage column identity explicitly, e.g. `IYC_IVOY_ID` vs `IYC_EVOY_ID`.
- For query/filter/sort migrations, `Verification` must include rendered BoundSql or equivalent plus one non-null value sample and one null/empty behavior sample.

## Write Side Effect Matrix

Use this section for save, submit, import, export, process, validate-and-write, status-change, audit-log, send-message, lock, transaction, or confirmation-flow behavior.

Summary fields:

- C# write branches: `<count>`
- Java write branches: `<count>`
- Tables/entities/procedures touched by C#: `<count/list>`
- Tables/entities/procedures touched by Java: `<count/list>`
- Transaction/confirmation mismatches: `<count>`
- Audit/log/message mismatches: `<count>`

Table columns:

```text
operation branch | selected/current/modified/all-row semantics | C# side effect evidence | Java side effect evidence | transaction/confirmation behavior | return/exception/message | status | action
```

Rules:

- Compare current row, selected rows, modified rows, and full request rows. A Java full-request operation is not equivalent to a C# selected-row operation without explicit user confirmation.
- Trace C# to BLL/DAL/SQL/procedure and Java to Service/Mapper/XML/external service for every write side effect.
- Compare status field changes, related-table writes, audit remarks, message-send logs, lock/idempotency behavior, transaction scope, and exception text.
- C# soft warnings or Yes/No prompts should map to a two-step Java contract such as confirm flags or `needConfirmItems`; do not convert them to hard failures unless C# also hard-fails.
- If write targets, transaction boundaries, or side effects cannot be proven, mark `证据不足` and block generation.

## Field Contract Matrix

Use this section for request DTOs, response VOs, OpenAPI/Swagger fields, C# Contract Entity/DTO parameters, Designer grids/tabs, dropdown fields, `ref`/`out`, and compatibility aliases.

Summary fields:

- C# input fields used by BLL: `<count>`
- C# output/ref/out/display fields: `<count>`
- Java request fields: `<count>`
- Java response fields: `<count>`
- Hidden/display/dropdown/compatibility-only fields: `<count>`
- Requiredness mismatches: `<count>`

Table columns:

```text
C# field | source path:line | BLL usage/output/display evidence | Java field | request/response/display/dropdown/hidden/compat | requiredness/default behavior | status | action
```

Rules:

- Confirm C# Entity/DTO input fields by reading the BLL implementation, not by copying the whole Contract object.
- Java request DTOs include only fields actually consumed by C# BLL-equivalent behavior. Unused C# fields must be marked `未使用` or `合理裁剪`.
- `ref`/`out` parameters are output fields and map to Java VO/response, not request DTO.
- Designer `Caption`/`Text` remains the source of Chinese display meaning. Java `@Schema` must not invent a looser label.
- Separate request-required fields, optional fields, response/display fields, dropdown-source fields, hidden fields, and compatibility aliases. Bean Validation requiredness must be backed by C# save behavior and Java write logic.

## HBSK Recent Failure Gate Check

Use this section when the prompt mentions frontend endpoint ambiguity, C# Designer mismatch, return VO field count/Chinese meaning mismatch, `queryCheckDetail`, `详细(&D)`, `rule-settings`, `saveRuleSettings`, `ModifyLoad`, slow endpoints, cache/Redis, request-body errors, or other recent HBSK rework triggers.

Endpoint matrix columns:

```text
C# visible action/control | C# handler | Contract/BLL/DAL evidence | Java route | request DTO | response VO | read/write | @EndpointLog decision | status
```

Gate rows to include when applicable:

- `frontend-endpoint-contract`: explain which Java route the frontend should call for each C# visible action.
- `detail-page`: map `bbiShowDetail`/double-click -> `GetCheckResults` six ref lists -> `ImportInfoCheckDetail` tabs/events -> Java detail VO fields.
- `vo-designer-field-parity`: compare C# Designer display fields/columns with Java response VO properties, including count and Chinese label/description differences.
- `rule-settings`: map `DMS_CHECK_CNFIG` and `DMS_CHECK_RULE` loading/saving, including `Meaning` null/blank/default semantics.
- `save-confirmation`: classify C# confirm dialogs as hard block, soft warning, or two-step confirmation.
- `selected-row-branch`: compare current row, selected rows, modified rows, and full request rows.
- `runtime-performance`: classify likely bottleneck as SQL, N+1/loop, cache key/TTL/penetration, DTO assembly/serialization, or frontend wait.
- `request-parsing`: classify JSON syntax, `@RequestBody` binding, Bean Validation, Controller entry, Service exception, and database exception separately.
- `utility-reuse`: list existing HBSK utilities/converters checked before adding helper code.

Allowed statuses are the same as the equivalence matrix: `行为等价`、`合理调整`、`逻辑错误`、`证据不足`、`权限无关`。

## VO Designer Field Parity

Use this section whenever a Java endpoint returns UI data or the prompt mentions VO fields, returned parameters, field count, Chinese descriptions, C# Designer, grid columns, tabs, or labels.

Summary fields:

- C# display field count: `<count>` using the stated count scope.
- Java response VO field count: `<count>` using the same scope.
- Missing Java fields: `<count>`
- Extra Java fields: `<count>`
- Chinese meaning mismatches: `<count>`
- Hidden/runtime-conditional fields: `<count and handling>`
- Count scope: `visible-designer-fields` | `designer-plus-runtime-visible-fields` | `all-bound-fields` | `证据不足`

Table columns:

```text
C# page/tab/control | C# control/column Name | FieldName/DataBinding | Caption/Text | Visible/VisibleIndex evidence | Java VO property | JSON field | Java @Schema/description | scope decision | status | action
```

Rules:

- Extract C# `Name`, `FieldName` or `DataBindings`, `Caption`/`Text`, `Visible`, `VisibleIndex`, and runtime visibility changes before counting.
- Treat C# `Caption`/`Text` as the source of truth for Chinese meaning; Java `@Schema(description)` or frontend labels must not invent a looser translation.
- Separate visible fields, hidden fields, runtime-visible fields, UI-only action columns, and fields only used by code. Do not silently drop hidden fields; justify the scope decision.
- For tabbed/detail pages, compare each tab/list separately and then provide the total count. Nested Java VO lists still need a row-by-row mapping to the C# tab/column source.
- Mark missing returned fields or mismatched Chinese meanings as `逻辑错误` when the Designer evidence and Java VO evidence are complete. Mark `证据不足` when runtime visibility, dynamic column creation, or frontend-only rendering cannot be proven.
- If Java intentionally returns an internal technical field not visible in C#, keep it in the table as `合理调整` with a reason; do not use it to offset missing visible fields.

## UI Event Interface Trace

Use this section for `C# UI事件接口追踪` mode. This mode answers the C# page event/interface map and does not generate Java.

Summary fields:

- UI event bindings: `<count>`
- Active interface events: `<count>`
- No-active-interface events: `<count>`
- Commented-out / inactive interface evidence: `<count or not-found>`
- Missing handlers: `<count>`

Table columns:

```text
# | control/caption | event | designer path:line | handler path:line | handler/helper/callback chain | Contract/BLL/DAL/SQL evidence | status
```

Allowed statuses:

- `active-interface`
- `no-active-interface`
- `commented-out-only`
- `handler-not-found`
- `证据不足`

Rules:

- Include every Designer event subscription, including UI-only events.
- Trace `handler -> helper -> callback -> PerformClick -> ServiceManager<T>.Service.Method` when present.
- Continue each active interface call to Contract and implementation/BLL; include DAL/SQL/procedure evidence when statically found.
- Mark commented-out interface calls as inactive and do not count them as active interface calls.
- If Contract/BLL/DAL/SQL cannot be confirmed, keep the event row and add a `证据不足` blocker with the minimum missing evidence.

## C# Full Chain

Format:

```text
UI/Form -> Contract/WCF -> BLL -> DAL -> SQL/Procedure -> Entity
```

Each hop must include `path:line`, method name, key inputs, key outputs, and side effects.

## Java Current Assets

List reusable Controller/Service/ServiceImpl/private helper/Mapper/XML/DTO/DO/Feign/config/test assets. Mark missing assets as `not-found`.

## Controller Operation Summary Evidence

Use this section for `controller-operation-summary` mode or when a migration touches Java Controller `@Operation(summary)`.

Summary fields:

- Java controller: `<path>`
- C# pages: `<Designer path list in priority order>`
- Patch mode: `none` | `stdout` | `<patch-out path>`
- Low-confidence rows: `<count>`
- Patchable rows: `<count>`

Table columns:

```text
Java method | mapping path | current summary | recommended summary | C# display evidence | confidence | patch action
```

Description format (structured "页面按钮索引卡"):

Every recommended description must follow this exact 6-field format:

```
C#页面: <Form类名>; 控件: <控件名>; Caption: <显示名>; 事件: <handler>; Contract: <接口.方法>; 边界: <职责范围>
```

Field rules:

- `C#页面`: C# partial class 类名；兼容入口时写 `兼容入口: true`
- `控件`: Designer 控件 Name；窗口事件写 `窗口事件`；弹窗触发写 `触发: <Form_Load>`
- `Caption`: 去掉快捷键后缀的显示名；保留业务括号
- `事件`: handler 方法名
- `Contract`: `接口名.方法名(参数摘要)`；证据不足时写 `证据不足`
- `边界`: Java 接口职责范围（含/不含什么、失败后行为）

Rules:

- `recommended summary` must come from C# Designer `Caption/Text/Form.Text` after shortcut cleanup.
- Remove shortcut suffixes such as `(&F)` and `（&F）`; keep business parentheses such as `(带过境箱)`.
- `recommended description` must use the structured 6-field format above; natural language sentences are forbidden.
- If several C# triggers map to one Java method, use the primary trigger in `recommended summary` and `recommended description`; list remaining candidates in evidence table.
- If no button/menu trigger is proven, use the nearest Form/Dialog `Text`; `控件` = `窗口事件`, `事件` = `Form.Text`.
- Low-confidence or unresolved multiple-candidate rows must not generate a patch.
- Generated patches may replace only `@Operation(summary=..., description=...)`; they must not edit business code, mappings, method signatures, or Service calls.

## Equivalence Matrix

Allowed statuses only:

- `行为等价`
- `合理调整`
- `逻辑错误`
- `证据不足`
- `权限无关`

Columns:

```text
area | C# expected behavior | Java actual behavior | evidence depth | status | action
```

`evidence depth` must identify whether the comparison is based on entry method, downstream helper, SQL/Mapper/procedure, DTO mapping, transaction, or write side effect.

## leftWhereStr Decision

One of: `unused`, `commented-out`, `sql-fragment`, `证据不足`.

State whether it will be dropped, converted to typed criteria, or block generation.

## Permission Decision

Classify every relevant permission as `ui-only`, `backend-auth`, `business-qualification`, or `bypass-or-exclusion`.

State what Java will enforce and what will not be copied.

In dual-entry equivalence repair mode, classify permission evidence only to exclude it. Permission, authorization, and qualification differences must be marked `权限无关`, must not block generation, and must not trigger Java rewrites.

## Contract Field Usage Verification

Use this section whenever a migration involves C# Contract/BLL interface translation to Java, especially when the Contract method takes Entity/DTO parameters.

For each C# Contract method parameter that is an Entity or DTO type:

### Summary fields

- C# Contract method: `<path:line> <method>`
- C# Entity/DTO parameter: `<Entity/DTO class name>`
- BLL implementation: `<path:line> <BLL class.method>`
- Fields used in BLL: `<count>` (confirmed by CodeGraph callees + source window)
- Fields not used in BLL: `<count>` (confirmed by CodeGraph callees + source window)
- Fields unconfirmed: `<count>` (BLL source not available or dynamic access)

### Table columns

```text
C# Entity/DTO field | BLL usage evidence (path:line) | Java DTO field | used/unused/unconfirmed | action
```

Rules:
- Every C# Entity/DTO field used in BLL must have a `path:line` evidence in the BLL implementation body.
- Java DTO must contain only fields marked `used`. Fields marked `unused` are not translated into Java request DTO.
- `ref`/`out` C# parameters are always output fields; they map to Java VO return fields, not request DTO fields.
- If a field is read indirectly (e.g., through reflection, `EntityState`, generic iteration), mark as `indirect` and require explicit user confirmation before including in Java DTO.
- When C# BLL assigns default values to output lists regardless of input (e.g., `differs = new List<PropertyCheckEntity>()`), this confirms the field is an output-only field.
- Evidence insufficient to confirm usage must block the DTO field inclusion and must be listed in "剩余待确认项".

## Pre-generation Checklist

Keep `[ ]` and `[x]` markers.

```text
- [ ] CodeGraph located C# entry and all required hops.
- [ ] C# and Java locations were resolved to real `path:line + symbol` anchors.
- [ ] Contract/BLL/DAL/SQL evidence is complete.
- [ ] Java entry and business-related downstream methods were traced.
- [ ] Controller `@Operation(summary)` was backed by C# Designer `Caption/Text/Form.Text` evidence when Java Controller code was generated or changed.
- [ ] Java reusable assets were searched.
- [ ] Current source files and planned-file dirty status were checked before editing.
- [ ] HBSK Recent Failure Gate Check was filled when the prompt matched a recent rework trigger.
- [ ] VO Designer Field Parity was filled when Java returned UI data or VO fields.
- [ ] Existing HBSK utilities/converters/starters were checked before adding helper code.
- [ ] leftWhereStr was classified and handled.
- [ ] Dynamic SQL was converted to typed criteria or blocked.
- [ ] Permissions were classified; in dual-entry mode, permission differences were excluded as `权限无关`.
- [ ] **Contract 字段使用验证**：C# Contract/BLL 的每个 Entity/DTO 入参，已通过 CodeGraph callees 追到 BLL 实现体，确认了实际使用的字段。Java 请求 DTO 仅包含 BLL 实际消费的字段，未使用的字段已标记 `未使用` 或 `合理裁剪`。`ref`/`out` 输出参数已映射为 Java VO 返回字段，未误作入参。
- [ ] Business write side effects, transactions, status changes, returned fields, sorting, null/default behavior, and exception messages were compared.
- [ ] **G1 查询条件完整性门禁**：已逐条枚举 C# WHERE 条件（含固定命令式 `field=val`、`if(x.HasValue)` 守卫、状态码 IN、箱号/提单号、leftWhereStr），每条对到 Java Mapper XML `<if>/<foreach>/#{}` 并带 path:line，输出条件 diff 表；C# 有而 Java 缺的条件已标 `逻辑错误` 并阻断生成（豁免需 path:line 证据证明该条件在 Java 路径已失效）。null/HasValue 守卫已逐项对齐。
- [ ] **G2 DTO/VO 字段机械计数门禁**：涉及入参/出参或返回 VO 时，已打印 C# 字段数 vs Java 字段数（注明口径）并给出缺/多字段清单；response VO 字段个数/中文释义不一致已列入差异矩阵；未给计数的行视为未完成。
- [ ] **G3 运行时值验证门禁**：查询/过滤/排序类迁移已渲染真实 Java SQL（BoundSql 或等价）并用具体非空值证明结果集收窄、用 null 值证明旧行为保留；非仅文本断言或编译通过。
- [ ] **G4 写库副作用完整性门禁**：保存/提交/处理/状态类迁移已逐分支比较当前行、选中行、修改行、全量行、确认弹窗、事务边界、写入表/过程、状态字段、审计日志、异常消息和返回提示。
- [ ] **G5 字段契约完整性门禁**：请求、响应、Designer、下拉、隐藏、兼容、`ref`/`out` 字段已按用途分类，必填性和默认值有 C# BLL/Designer 与 Java DTO/VO 证据支撑。
- [ ] Proven Java business bugs have a scoped rewrite target and test target.
- [ ] Java readability gate passed.
- [ ] Verification sample and commands are defined.
```

If any item affecting behavior or writes remains unchecked, do not generate Java.

## Implementation Plan / Code

When evidence is sufficient, provide code or exact file edits in dependency order: model -> mapper/xml -> service -> controller -> tests. In dual-entry repair mode, only rewrite Java business code proven non-equivalent and the tests needed to lock that behavior; do not refactor unrelated code.

## Verification

Include business sample values and commands. Compare rows, IDs, fields, filters, sorting, statuses, exceptions, and DB side effects.

For query/filter/sort tasks, include rendered BoundSql or equivalent SQL plus concrete non-null and null/empty samples. For write/status tasks, include focused tests, DB sample comparison, or a safe read-only side-effect verification plan. For field-contract tasks, include request/response serialization or OpenAPI evidence when applicable.

## No-Code Blockers

Use this section whenever implementation is not allowed. List each blocker and the minimum evidence needed to unblock it.

Table columns:

```text
blocker | missing evidence | why it affects business behavior | minimum next step
```

## 剩余待确认项

List blockers with the minimum evidence needed to unblock each one.

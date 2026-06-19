# Java Output Quality Gate

## Layering

- Controller：只收参、做边界校验、调用 Service、返回响应。
- Service/ServiceImpl：承载业务编排、事务、权限、状态流转、跨 Mapper/Feign 调用。
- Mapper/XML：只做数据访问，不写业务编排。
- DO：数据库映射字段。
- DTO/VO/Param：接口入参/出参和业务传输模型。

## Readability Rules

- 方法职责单一，复杂规则拆私有方法或领域对象。
- 使用业务语义命名，禁止保留 C# 控件名作为 Java 服务变量名。
- 优先早返回，避免深层嵌套 if。
- 集合处理清晰，不为炫技滥用 stream。
- 魔法值提取为常量或枚举；状态码含义必须可读。
- 异常消息、事务边界、权限失败路径要清楚。

## Prohibited C# Direct Translations

- `leftWhereStr`、`whereClause`、自由 SQL 字符串入参。
- DataTable/DataRow/BizDataEntitySet 思维直接进入 Java。
- WinForms 控件状态进入 Service 或 DO。
- 大段按钮事件代码原样搬到 Controller。
- C# 式临时变量名、控件名、缩写堆叠。
- UI-only 权限复制为后端业务规则。

## SQL/Mapper Quality

- 使用 `#{}` 参数绑定。
- 列表条件用 `<foreach>`。
- 可选条件用 `<if>`，条件字段来自 typed request。
- `${}` 只允许白名单字段、排序或封闭枚举，并说明理由。
- Mapper XML 的查询结果字段必须和 DTO/DO 映射一致。

## Human Read Check

生成前自查：另一个 Java 工程师不看 C# 也能理解：

- 这个接口做什么。
- 关键请求字段含义。
- 主要查询条件来源。
- 权限和业务资格在哪里校验。
- 何时写库、写哪些表、失败如何返回。

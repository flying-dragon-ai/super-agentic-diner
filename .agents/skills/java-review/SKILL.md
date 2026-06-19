---
name: java-review
description: |
  Java/Spring Boot 代码审查规范。

  使用场景：当用户要求对 Java 代码进行 review、检查、审查时调用。
  典型触发词：review、检查代码、审查、对照规范、code review、检查一下、java review

  功能：对照 Java/Spring Boot 编码规范，逐项检查代码质量，输出问题清单和修复建议。
allowed-tools: Read, Grep, Glob, Edit, Write
user-invocable: true
---

# Java/Spring Boot 代码审查规范

> 版本: 7.1 | 模式: Code Review | 检查项: 20 | 更新: 2026-01-21

---

## 使用方式

用户在代码编写完成后，输入以下命令触发审查：

```
/java-review
```

或自然语言：
- "对照规范检查一下"
- "review 刚才写的代码"
- "帮我审查这些修改"
- "java review"

---

## 审查流程

### 第一步：识别审查范围

确定需要审查的代码：
- 本次会话新增/修改的文件
- 用户指定的文件或目录
- 最近 git 变更的文件

### 第二步：逐项检查

按以下检查清单逐项审查，输出格式：

```
## 审查结果

### ✅ 通过项
- [检查项]: 通过

### ❌ 问题项
- [检查项]: 问题描述
  - 位置: `文件路径:行号`
  - 问题: 具体问题
  - 修复: 建议的修改
```

### 第三步：提供修复

对于问题项，直接提供修复代码或询问用户是否自动修复。

---

## 检查清单

### 1. 命名规范检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| Controller 类 | 必须以 `Controller` 结尾 | ⚠️ 中 |
| Service 接口 | 必须以 `I*Service` 命名 | ⚠️ 中 |
| Service 实现 | 必须以 `*ServiceImpl` 结尾 | ⚠️ 中 |
| Mapper 接口 | 必须以 `*Mapper` 结尾 | ⚠️ 中 |
| 实体类 | 驼峰命名，与表名对应 | ⚠️ 中 |
| DTO 类 | 必须以 `*DTO` 结尾 | ⚠️ 中 |
| 请求对象 | 必须以 `*Req` 结尾 | ⚠️ 中 |
| 响应对象 | 必须以 `*Rsp` 结尾 | ⚠️ 中 |
| 枚举类 | 必须以 `*Enum` 结尾 | ⚠️ 中 |
| 方法/字段 | `lowerCamelCase` | ⚠️ 中 |
| 常量 | `UPPER_SNAKE_CASE` | ⚠️ 中 |
| 接口路径 | `kebab-case`（如 `/product-catalog/page`） | ⚠️ 中 |

### 2. Import 规范检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| 全限定类名 | 禁止使用（如 `java.util.List`），必须先 import | ⚠️ 中 |
| 静态导入 | 常量和静态方法使用 `import static` | ⚡ 低 |

**检查示例**：

```java
// ❌ 问题
public java.util.List<String> getList() {
    return new java.util.ArrayList<>();
}

// ✅ 正确
import java.util.List;
import java.util.ArrayList;
import static com.dsl.base.exception.util.ServiceExceptionUtil.exception;

public List<String> getList() {
    return new ArrayList<>();
}
```

### 3. 类结构检查

| 检查项 | 规则 | 严重度 | 适用范围 |
|-------|------|--------|----------|
| Controller 类注解 | 建议有 `@Validated`（视业务需求） | ⚡ 低 | 新建类 |
| Service 类注解 | 必须有 `@Slf4j` + `@RequiredArgsConstructor` | ⚠️ 中 | 新建类 |
| 依赖注入方式 | 新建类必须构造器注入，存量类不强制修改 | ⚠️ 中 | 新建类 |
| 类命名 | Controller/Service/Mapper/DTO 等后缀正确 | ⚠️ 中 | 所有 |

**注意**：存量代码中的 `@Autowired` 字段注入无需修改，只对新建类做要求。

**检查示例**：

```java
// 存量代码（不强制修改）
@Service
public class ProductService {
    @Autowired
    private ProductMapper productMapper;
}

// ✅ 新建类应该这样写
@Service
@Slf4j
@RequiredArgsConstructor
public class ProductServiceImpl implements IProductService {
    private final ProductMapper productMapper;
}
```

### 4. Controller 层检查

| 检查项 | 规则 | 严重度 | 说明 |
|-------|------|--------|------|
| 返回类型 | 必须是 `CommonResult<T>`，禁止返回 Entity | 🔴 高 | 强制 |
| 业务逻辑 | 禁止在 Controller 写业务逻辑 | 🔴 高 | 强制 |
| 参数注解 | 建议有 `@Valid @RequestBody`（视业务需求） | ⚡ 低 | 建议 |

**说明**：`@Valid` 和 `@RequestBody` 根据业务场景决定，不是所有接口都需要。

**检查示例**：

```java
// ❌ 问题：Controller 包含业务逻辑
@PostMapping("/add")
public CommonResult<Long> add(@RequestBody ProductAddReq req) {
    Product product = new Product();
    BeanUtils.copyProperties(req, product);
    productMapper.insert(product);  // ❌ 业务逻辑
    return CommonResult.success(product.getId());
}

// ✅ 正确
@PostMapping("/add")
public CommonResult<Long> add(@Valid @RequestBody ProductAddReq req) {
    return CommonResult.success(productService.add(req));
}
```

### 5. DTO/Req/Rsp 类检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| Lombok 注解 | 必须有 `@NoArgsConstructor`（MyBatis 映射需要） | 🔴 高 |
| 字段校验 | Req 类必须有校验注解 | ⚠️ 中 |
| 嵌套对象校验 | 嵌套对象必须加 `@Valid` 触发内部校验 | 🔴 高 |
| 继承字段 | 子类必须显式声明所有需映射的字段 | 🔴 高 |

**嵌套对象校验示例**：

```java
// ❌ 问题：嵌套对象未加 @Valid
@Data
public class OrderReq {
    @NotNull(message = "用户信息不能为空")
    private UserInfo userInfo;  // 内部校验不会触发
}

// ✅ 正确：嵌套对象必须加 @Valid
@Data
public class OrderReq {
    @NotNull(message = "用户信息不能为空")
    @Valid  // 必须加
    private UserInfo userInfo;
}
```

### 6. 日志规范检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| 日志格式 | 必须使用 `[业务名称]` 前缀 + `{}` 占位符 | ⚠️ 中 |
| 字符串拼接 | 禁止 `log.info("ID: " + id)` | ⚠️ 中 |
| 敏感信息 | phone/idCard/password/token 等必须脱敏 | 🔴 高 |
| 异常日志 | catch 块必须 `log.error` + 异常堆栈 | 🔴 高 |

**敏感字段识别模式**：
- `*phone*`, `*mobile*`, `*tel*` → 必须脱敏
- `*idCard*`, `*idNo*` → 必须脱敏
- `*password*`, `*pwd*`, `*secret*` → 禁止打印
- `*token*`, `*apiKey*` → 禁止打印

**检查示例**：

```java
// ❌ 问题
log.info("用户手机号: " + phone);

// ✅ 正确
log.info("[用户注册]，手机号: {}", DesensitizeUtil.mobile(phone));
```

### 7. 事务检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| 多表写操作 | 必须有 `@Transactional(rollbackFor = Exception.class)` | 🔴 高 |
| 事务方法修饰符 | 必须是 `public` | 🔴 高 |
| 多数据源冲突 | 禁止事务方法中混用多个数据源 | 🔴 高 |
| 同类调用 | 禁止同类内部调用事务方法（代理失效） | 🔴 高 |

**多数据源事务限制**：

`@Transactional` 只对主数据源生效，事务方法中 ❌ 禁止混用 MySQL 和 Doris。

```java
// ❌ 问题：事务中混用 MySQL 和 Doris
@Transactional(rollbackFor = Exception.class)
public void syncData() {
    // Doris 查询不在事务管理范围内
    List<Data> dorisData = dorisMapper.selectList();
    // MySQL 写入在事务中
    mysqlMapper.saveBatch(dorisData);
}

// ✅ 正确：拆分方法，事务只包裹单数据源操作
public void syncData() {
    // 1. 非事务方法查询 Doris
    List<Data> dorisData = queryFromDoris();
    // 2. 事务方法写入 MySQL
    saveToMysql(dorisData);
}

@Transactional(rollbackFor = Exception.class)
public void saveToMysql(List<Data> data) {
    mysqlMapper.saveBatch(data);
}
```

**同类调用代理失效**：

```java
// ❌ 同类调用事务不生效
public void methodA() {
    this.methodB();  // methodB 的 @Transactional 不生效
}

// ✅ 正确：注入自身或拆分到另一个 Service
@Autowired
private ProductService self;

public void methodA() {
    self.methodB();  // 通过代理调用，事务生效
}
```

### 8. Mapper 层检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| 复杂查询方式 | 多表JOIN/动态条件≥3个 必须用 XML | ⚠️ 中 |
| SQL 注入 | 禁止 `${}` 拼接，必须用 `#{}` | 🔴 高 |
| XML 与 DTO 同步 | 新增字段必须同步更新 DTO | 🔴 高 |
| 动态排序 | 使用 `<choose>` 白名单，禁止直接拼接字段名 | 🔴 高 |

**动态排序安全写法**：

```xml
<!-- ✅ 正确：白名单方式 -->
ORDER BY
<choose>
    <when test="orderColumn == 'create_time'">create_time</when>
    <when test="orderColumn == 'update_time'">update_time</when>
    <otherwise>id</otherwise>
</choose>
```

### 9. 代码复杂度检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| 方法行数 | 不超过 50 行 | ⚠️ 中 |
| if-else 嵌套 | 不超过 2 层 | ⚠️ 中 |
| 分支数量 | 超过 3 个考虑策略模式 | ⚡ 低 |

**检查示例**：

```java
// ❌ 问题：嵌套过深
if (order != null) {
    if (order.getStatus() == 1) {
        if (order.getAmount() > 0) {
            process(order);
        }
    }
}

// ✅ 正确：卫语句
if (order == null) {
    throw exception(ORDER_NOT_EXISTS);
}
if (order.getStatus() != 1) {
    throw exception(INVALID_STATUS);
}
process(order);
```

### 10. 性能检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| N+1 查询 | 禁止循环查询数据库，必须批量查询 + 内存关联 | 🔴 高 |
| 深度分页 | 大偏移量使用游标分页（WHERE id > lastId） | ⚠️ 中 |
| 批量处理 | 超过 1000 条必须分批 | ⚠️ 中 |
| 大数据量导出 | 使用流式查询 `@Options(fetchSize = 1000)` | ⚠️ 中 |

**N+1 查询示例**：

```java
// ❌ 问题：循环查询
for (Order order : orders) {
    User user = userMapper.selectById(order.getUserId());  // N 次查询
}

// ✅ 正确：批量查询 + 内存关联
Set<Long> userIds = orders.stream().map(Order::getUserId).collect(Collectors.toSet());
Map<Long, User> userMap = userMapper.selectBatchIds(userIds).stream()
    .collect(Collectors.toMap(User::getId, u -> u));
```

**深度分页示例**：

```sql
-- ❌ 错误：大偏移量性能差
SELECT * FROM product LIMIT 100000, 10;

-- ✅ 正确：游标分页
SELECT * FROM product WHERE id > #{lastId} ORDER BY id LIMIT 10;
```

### 11. 设计检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| 幂等性 | 写接口必须考虑重复调用 | ⚠️ 中 |
| 缓存 Key | 必须有业务前缀 `{业务}:{模块}:{id}` | ⚡ 低 |
| 缓存 TTL | 禁止永不过期 | ⚠️ 中 |

**幂等性判断决策树**：

```
写接口？
├─ 是 → 业务主键存在？
│       ├─ 是 → 使用唯一索引 + 查询判断
│       └─ 否 → 使用分布式锁 + 幂等表
└─ 否 → 不需要幂等
```

### 12. 异常处理检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| 业务异常 | 必须使用 `ServiceExceptionUtil.exception()` | 🔴 高 |
| 异常信息 | 禁止直接 `throw new RuntimeException()` | 🔴 高 |
| catch 块 | 禁止空 catch，必须处理或重抛 | 🔴 高 |
| 异常日志 | catch 中必须 `log.error` 并包含异常堆栈 | 🔴 高 |

**检查示例**：

```java
// ❌ 问题：原生异常
if (user == null) {
    throw new RuntimeException("用户不存在");
}

// ✅ 正确：使用 ServiceExceptionUtil
import static com.dsl.base.exception.util.ServiceExceptionUtil.exception;

if (user == null) {
    throw exception(USER_NOT_FOUND);
}
```

### 13. 缓存检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| Key 命名 | 必须 `{业务}:{模块}:{标识}` 格式 | ⚠️ 中 |
| TTL 设置 | 禁止永不过期 | ⚠️ 中 |
| 缓存穿透 | 空值也缓存（短 TTL 如 5 分钟） | ⚠️ 中 |
| 缓存更新 | 先更新数据库，再删除缓存 | ⚠️ 中 |

**TTL 参考值**：

| 数据类型 | 建议 TTL |
|---------|----------|
| 热点数据 | 1-5 分钟 |
| 普通数据 | 30 分钟 |
| 配置数据 | 1 小时 |

### 14. 并发控制检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| 乐观锁 | 更新操作需考虑并发，优先使用 version 字段 | ⚠️ 中 |
| 分布式锁 | 跨实例操作必须使用分布式锁 | 🔴 高 |
| 锁粒度 | 锁 Key 必须精确到业务主键 | ⚠️ 中 |
| 锁释放 | 只释放自己持有的锁 `lock.isHeldByCurrentThread()` | 🔴 高 |

### 15. 配置安全检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| 敏感配置 | 数据库密码、API Key 等禁止明文提交 | 🔴 高 |
| 环境隔离 | 生产配置必须与开发环境分离 | 🔴 高 |
| 日志打印 | 禁止在日志中打印敏感配置 | 🔴 高 |

**敏感配置存储**：使用 Nacos 配置中心，按环境隔离。

### 16. 安全规范检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| XSS 过滤 | 用户输入必须过滤或转义 | 🔴 高 |
| 文件上传 | 类型白名单 + 大小限制 + UUID重命名 | 🔴 高 |
| 数据权限 | 查询/修改必须校验数据归属 | 🔴 高 |
| SQL 注入 | MyBatis 禁止 `${}` 拼接用户输入 | 🔴 高 |

**权限控制说明**：

项目主要通过 DmpSystemApi 查询用户区域权限实现权限控制。`@PreAuthorize` 注解为可选方案，存量代码中有使用。

**数据权限校验示例**：

```java
// ❌ 典型漏洞：水平越权
@GetMapping("/orders/{id}")
public CommonResult<OrderDetailRsp> getOrder(@PathVariable Long id) {
    return CommonResult.success(orderService.getById(id));  // 未校验归属
}

// ✅ 正确：校验数据归属
@GetMapping("/orders/{id}")
public CommonResult<OrderDetailRsp> getOrder(@PathVariable Long id) {
    Order order = orderService.getById(id);
    if (order == null) {
        throw exception(ORDER_NOT_FOUND);
    }
    // 校验归属
    if (!order.getUserId().equals(SecurityUtils.getUserId())) {
        throw exception(NO_PERMISSION);
    }
    return CommonResult.success(convert(order));
}
```

### 17. 接口文档检查（Apifox）

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| Controller 类注释 | 必须有类级别 Javadoc 描述模块功能 | ⚠️ 中 |
| 方法注释 | 必须有 @param 和 @return 说明 | ⚠️ 中 |
| 字段注释 | DTO/Req/Rsp 字段必须有 Javadoc 注释 | ⚠️ 中 |
| Mock 值 | 使用 `@mock` 标签提供示例值 | ⚡ 低 |

**注释规范**：

```java
/**
 * 商品管理
 */
@RestController
public class ProductController {

    /**
     * 分页查询商品
     * @param req 查询条件
     * @return 商品分页列表
     */
    @PostMapping("/page")
    public CommonResult<IPage<ProductDTO>> getPage(@Valid @RequestBody ProductPageReq req) { }
}
```

**字段注释**：

```java
/**
 * 商品名称（模糊匹配）
 * @mock 阿莫西林
 */
private String name;

/**
 * 状态：0-下架，1-上架
 * @mock 1
 */
private Integer status;
```

**特殊标签**：

| 标签 | 用途 |
|------|------|
| `@mock` | 字段示例值 |
| `@ignore` | 忽略该字段，不生成文档 |

### 18. 异步处理检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| 线程池指定 | 必须使用 `@Async("线程池名")` 指定线程池 | 🔴 高 |
| 默认线程池 | 禁止使用默认 SimpleAsyncTaskExecutor | 🔴 高 |
| 同类调用 | 禁止在同类中调用 `@Async` 方法（代理失效） | 🔴 高 |
| 事务冲突 | 禁止在 `@Async` 方法中使用 `@Transactional` | 🔴 高 |

### 19. 微服务调用检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| Feign 超时 | 必须显式配置超时时间 | 🔴 高 |
| Feign 异常 | 必须捕获处理 FeignException | 🔴 高 |
| 服务调用日志 | 调用前后必须打印日志 | ⚠️ 中 |

**Feign 异常处理示例**：

```java
// ❌ 问题：未处理异常
public UserDTO getUser(Long userId) {
    return userClient.getById(userId);  // FeignException 直接抛出
}

// ✅ 正确：捕获并转换为业务异常
public UserDTO getUser(Long userId) {
    try {
        log.info("[用户查询]，调用用户服务，userId: {}", userId);
        UserDTO user = userClient.getById(userId);
        log.info("[用户查询]，调用成功，userId: {}", userId);
        return user;
    } catch (FeignException.NotFound e) {
        log.warn("[用户查询]，用户不存在，userId: {}", userId);
        return null;
    } catch (FeignException e) {
        log.error("[用户查询]，调用失败，userId: {}，status: {}，异常：",
            userId, e.status(), e);
        throw exception(USER_SERVICE_ERROR);
    }
}
```

### 20. MQ 消费检查

| 检查项 | 规则 | 严重度 |
|-------|------|--------|
| 消费幂等 | 必须保证幂等消费（Redis 或数据库去重） | 🔴 高 |
| 消息确认 | 业务成功后再 ACK | 🔴 高 |
| 死信处理 | 配置死信队列 + 告警 | ⚠️ 中 |
| 事务消息 | 分布式事务使用 RocketMQ 事务消息 | 🔴 高 |

**RocketMQ 事务消息**：

```java
// 事务监听器
@RocketMQTransactionListener(txProducerGroup = "order-create-tx")
public class OrderCreateTxListener implements RocketMQLocalTransactionListener {

    @Override
    public RocketMQLocalTransactionState executeLocalTransaction(Message msg, Object arg) {
        try {
            orderService.createOrderLocal((OrderCreateReq) arg);
            return RocketMQLocalTransactionState.COMMIT;
        } catch (Exception e) {
            log.error("[订单创建事务]，本地事务失败，异常：", e);
            return RocketMQLocalTransactionState.ROLLBACK;
        }
    }

    @Override
    public RocketMQLocalTransactionState checkLocalTransaction(Message msg) {
        String bizId = msg.getHeaders().get("bizId", String.class);
        boolean exists = orderMapper.existsByBizId(bizId);
        return exists ? COMMIT : ROLLBACK;
    }
}
```

---

## 输出模板

审查完成后，按以下格式输出：

### 报告头部

```markdown
## Java/Spring 代码审查报告

> 📋 审查范围: X 个文件 | 🕐 YYYY-MM-DD HH:mm

### 问题汇总

| 严重度 | 数量 | 可自动修复 |
|--------|------|-----------|
| 🔴 高   | X    | X         |
| ⚠️ 中   | X    | X         |
| ⚡ 低   | X    | X         |
```

### 问题详情（diff 格式）

每个问题使用编号和 diff 格式：

```markdown
### 🔴 高严重度问题

#### #1 [问题标题]
📍 `文件路径:行号`

```diff
- // 原代码（红色删除）
+ // 修复代码（绿色新增）
```
🔧 **可自动修复** - 回复 `fix #1` 应用修复

---

#### #2 [问题标题]
📍 `文件路径:行号`

```diff
  // 上下文代码
- // 问题代码
+ // 修复代码
```
⚠️ **需手动修复** - [原因说明]
```

### 通过项汇总（折叠显示）

```markdown
### ✅ 审查通过

**X/20 项检查通过**（命名规范、Import规范、Mapper层、异常处理...）
```

### 后续操作提示

```markdown
### 📌 后续操作

| 命令 | 说明 |
|------|------|
| `fix all` | 自动修复所有可修复问题 |
| `fix #1` | 修复指定问题 |
| `fix #1,#3,#5` | 批量修复多个问题 |
| `详细 #2` | 查看问题详细说明 |
```

### 完整报告示例

```markdown
## Java/Spring 代码审查报告

> 📋 审查范围: 3 个文件 | 🕐 2026-01-21 14:30

### 问题汇总

| 严重度 | 数量 | 可自动修复 |
|--------|------|-----------|
| 🔴 高   | 2    | 1         |
| ⚠️ 中   | 3    | 2         |
| ⚡ 低   | 1    | 0         |

---

### 🔴 高严重度问题

#### #1 Controller 包含业务逻辑
📍 `ProductController.java:45`

```diff
- @PostMapping("/add")
- public CommonResult<Long> add(@RequestBody ProductAddReq req) {
-     Product product = new Product();
-     BeanUtils.copyProperties(req, product);
-     productMapper.insert(product);
-     return CommonResult.success(product.getId());
- }

+ @PostMapping("/add")
+ public CommonResult<Long> add(@Valid @RequestBody ProductAddReq req) {
+     return CommonResult.success(productService.add(req));
+ }
```
🔧 **可自动修复** - 回复 `fix #1` 应用修复

---

#### #2 事务方法混用多数据源
📍 `DataSyncServiceImpl.java:78`

```diff
  @Transactional(rollbackFor = Exception.class)
  public void syncData() {
-     List<Data> dorisData = dorisMapper.selectList();
-     mysqlMapper.saveBatch(dorisData);
+     List<Data> dorisData = queryFromDoris();
+     saveToMysql(dorisData);
  }
```
⚠️ **需手动修复** - 涉及方法拆分，需人工确认

---

### ⚠️ 中严重度问题

#### #3 日志缺少业务标识
📍 `OrderServiceImpl.java:23`

```diff
- log.info("订单创建成功，orderId: {}", orderId);
+ log.info("[订单创建]，创建成功，orderId: {}", orderId);
```
🔧 **可自动修复**

#### #4 嵌套对象缺少 @Valid
📍 `OrderReq.java:15`

```diff
  @NotNull(message = "用户信息不能为空")
+ @Valid
  private UserInfo userInfo;
```
🔧 **可自动修复**

#### #5 方法超过50行
📍 `ReportServiceImpl.java:120-185`

⚠️ **需手动修复** - 建议拆分为多个私有方法

---

### ⚡ 低严重度问题

#### #6 缺少 @mock 注释
📍 `ProductReq.java:12`

```diff
+ /**
+  * 商品名称
+  * @mock 阿莫西林
+  */
  private String name;
```
💡 **建议修复** - 可提升接口文档质量

---

### ✅ 审查通过

**14/20 项检查通过**（命名规范、Import规范、Mapper层、异常处理、缓存规范...）

---

### 📌 后续操作

| 命令 | 说明 |
|------|------|
| `fix all` | 自动修复 #1, #3, #4（3个问题） |
| `fix #1` | 仅修复 Controller 业务逻辑问题 |
| `fix #3,#4` | 批量修复日志和校验问题 |
| `详细 #2` | 查看多数据源事务的详细说明 |
```

---

## 快速参考

### 必须的注解组合

```java
// Controller（新建类）
@RestController
@RequiredArgsConstructor
// @Validated 视业务需求，不强制

// Service（新建类）
@Service
@Slf4j
@RequiredArgsConstructor

// DTO
@Data
@NoArgsConstructor
```

### 日志格式

```java
log.info("[业务名称]，动作描述，参数: {}", value);
log.error("[业务名称]，错误描述，参数: {}，异常：", value, e);
```

### 敏感字段脱敏

```java
DesensitizeUtil.mobile(phone)     // 138****1234
DesensitizeUtil.idCard(idCard)    // 310***********1234
// password/token 禁止打印
```

### 事务注解

```java
@Transactional(rollbackFor = Exception.class)
```

### 异常抛出

```java
import static com.dsl.base.exception.util.ServiceExceptionUtil.exception;

throw exception(ERROR_CODE_CONSTANT);
```

### 缓存 Key 格式

```java
String key = "{业务}:{模块}:{id}";
// 示例: "order:detail:12345"
```

### 分布式锁模板

```java
RLock lock = redisson.getLock("业务:操作:" + bizId);
try {
    if (lock.tryLock(3, 30, TimeUnit.SECONDS)) {
        // 业务逻辑
    }
} finally {
    if (lock.isHeldByCurrentThread()) {
        lock.unlock();
    }
}
```

### Feign 调用模板

```java
try {
    log.info("[服务调用]，调用开始，参数: {}", param);
    Result result = feignClient.method(param);
    log.info("[服务调用]，调用成功，结果: {}", result);
    return result;
} catch (FeignException.NotFound e) {
    log.warn("[服务调用]，资源不存在，参数: {}", param);
    return null;
} catch (FeignException e) {
    log.error("[服务调用]，调用失败，参数: {}，status: {}，异常：", param, e.status(), e);
    throw exception(SERVICE_CALL_FAILED);
}
```

### MQ 消费幂等模板（Redis）

```java
String msgKey = "mq:consumed:" + msgId;
Boolean isNew = redis.opsForValue().setIfAbsent(msgKey, "1", 7, TimeUnit.DAYS);
if (Boolean.FALSE.equals(isNew)) {
    log.info("[消息消费]，消息已处理，msgId: {}", msgId);
    return;
}
try {
    // 业务逻辑
} catch (Exception e) {
    redis.delete(msgKey);  // 失败删除标记，允许重试
    throw e;
}
```

### MQ 消费幂等模板（数据库）

```java
@Transactional(rollbackFor = Exception.class)
public void consume(Event event) {
    try {
        mqConsumeRecordMapper.insert(new MqConsumeRecord().setMsgId(event.getMsgId()));
    } catch (DuplicateKeyException e) {
        log.info("[消息消费]，消息已处理，msgId: {}", event.getMsgId());
        return;
    }
    // 业务逻辑（与去重同事务）
}
```

---

## 附录：错误码定义规范

错误码定义位置：`**/enums/*ErrorCodeConstants.java`

```java
public interface ProductErrorCodeConstants {
    // 格式：模块代码 + 功能代码 + 序号
    // 商品模块: 1-001-001
    ErrorCode PRODUCT_NOT_FOUND = new ErrorCode(1_001_001, "商品不存在");
    ErrorCode PRODUCT_STOCK_NOT_ENOUGH = new ErrorCode(1_001_002, "商品库存不足");
    ErrorCode PRODUCT_ALREADY_EXISTS = new ErrorCode(1_001_003, "商品已存在");
}
```

**错误码编号规范**：

| 段位 | 含义 | 示例 |
|------|------|------|
| 第1位 | 系统标识 | 1=业务系统, 2=基础服务 |
| 第2-4位 | 模块代码 | 001=商品, 002=订单, 003=用户 |
| 第5-7位 | 错误序号 | 001, 002, 003... |

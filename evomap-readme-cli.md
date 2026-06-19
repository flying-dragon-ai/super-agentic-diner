## Navigation Menu

# Search code, repositories, users, issues, pull requests...

# Provide feedback

We read every piece of feedback, and take your input very seriously.

# Saved searches

## Use saved searches to filter your results more quickly

To see all available qualifiers, see our [documentation](https://docs.github.com/search-github/github-code-search/understanding-github-code-search-syntax).

## FilesExpand file tree

## Breadcrumbs

# README.zh-CN.md

## Latest commit

## History

## Breadcrumbs

# README.zh-CN.md

## File metadata and controls

# 🧬 Evolver

[![GitHub stars](https://camo.githubusercontent.com/f9ccd75ad30c092d04309306b7dce765890b594b4a928d46df9242df5520e174/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f53746172732d382e376b2d3262333133373f6c6f676f3d676974687562266c6f676f436f6c6f723d7768697465)](https://github.com/EvoMap/evolver/stargazers)
[![License: GPL-3.0](https://camo.githubusercontent.com/c8e817d0fab13b6b935489e0692f5301982fdcc96451d589d7444f2055cf9a7c/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f4c6963656e73652d47504c2d2d332e302d626c75652e737667)](https://opensource.org/licenses/GPL-3.0)
[![Node.js >= 18](https://camo.githubusercontent.com/07aa7e54bdfb5132dd8d47c0f98ec3a7b0e5471958b3062f1467dba7fed722da/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f4e6f64652e6a732d25334525334425323031382d677265656e2e737667)](https://nodejs.org/)
[![npm downloads](https://camo.githubusercontent.com/b4d1e76524260ec0daea780f3d117e3e3d3916703509731780421ff2f91fbac2/68747470733a2f2f696d672e736869656c64732e696f2f6e706d2f646d2f4065766f6d61702f65766f6c7665722e737667)](https://www.npmjs.com/package/@evomap/evolver)
[![arXiv](https://camo.githubusercontent.com/65c6a034b7088866f854ee57cba6ac850d039b2ee1b079c504104a2a887f2240/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f61725869762d323630342e31353039372d6233316231622e737667)](https://arxiv.org/abs/2604.15097)

![GitHub stars](https://camo.githubusercontent.com/f9ccd75ad30c092d04309306b7dce765890b594b4a928d46df9242df5520e174/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f53746172732d382e376b2d3262333133373f6c6f676f3d676974687562266c6f676f436f6c6f723d7768697465)
![License: GPL-3.0](https://camo.githubusercontent.com/c8e817d0fab13b6b935489e0692f5301982fdcc96451d589d7444f2055cf9a7c/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f4c6963656e73652d47504c2d2d332e302d626c75652e737667)
![Node.js >= 18](https://camo.githubusercontent.com/07aa7e54bdfb5132dd8d47c0f98ec3a7b0e5471958b3062f1467dba7fed722da/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f4e6f64652e6a732d25334525334425323031382d677265656e2e737667)
![npm downloads](https://camo.githubusercontent.com/b4d1e76524260ec0daea780f3d117e3e3d3916703509731780421ff2f91fbac2/68747470733a2f2f696d672e736869656c64732e696f2f6e706d2f646d2f4065766f6d61702f65766f6c7665722e737667)
![arXiv](https://camo.githubusercontent.com/65c6a034b7088866f854ee57cba6ac850d039b2ee1b079c504104a2a887f2240/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f61725869762d323630342e31353039372d6233316231622e737667)

[![Evolver Cover](/EvoMap/evolver/raw/main/assets/cover.png)](/EvoMap/evolver/blob/main/assets/cover.png)

![Evolver Cover](/EvoMap/evolver/raw/main/assets/cover.png)

**[evomap.ai](https://evomap.ai)** | [Wiki 文档](https://evomap.ai/wiki) | [English Docs](/EvoMap/evolver/blob/main/README.md) | [Japanese / 日本語ドキュメント](/EvoMap/evolver/blob/main/README.ja-JP.md) | [한국어 문서](/EvoMap/evolver/blob/main/README.ko-KR.md) | [GitHub](https://github.com/EvoMap/evolver) | [Releases](https://github.com/EvoMap/evolver/releases)

**公告 —— 走向源码可见（Source-Available）**

自 2026-02-01 首次发布起，Evolver 一直完全开源（初期为 MIT，2026-04-09 起转为 GPL-3.0-or-later）。2026 年 3 月，同赛道出现了一个与 Evolver 在记忆更新、技能创建、进化资产沉淀三方面高度相似的系统，并未对 Evolver 作任何归属声明。完整分析请见：[Hermes Agent 自进化体系与 Evolver 的高度相似性分析](https://evomap.ai/zh/blog/hermes-agent-evolver-similarity-analysis)。

为保护项目完整性、持续在这个方向投入，Evolver 后续版本将从完全开源转为源码可见。**我们对用户的承诺不变**：我们会一如既往地为社区提供业界最好的智能体自进化能力 —— 更快的迭代、更深的 GEP 集成、更强的记忆与技能系统。已发布的 MIT 与 GPL-3.0 版本继续按原许可证自由使用。你仍然可以通过 `npm install @evomap/evolver` 或直接克隆本仓库使用，现有工作流不受任何影响。

`npm install @evomap/evolver`

如有疑问，欢迎提 issue 或访问 [evomap.ai](https://evomap.ai)。

**研究论文 —— Evolver 背后的理论依据**

**From Procedural Skills to Strategy Genes: Towards Experience-Driven Test-Time Evolution**（《从程序化技能到策略基因：面向经验驱动的测试时进化》）· [arXiv:2604.15097](https://arxiv.org/abs/2604.15097) · [PDF](https://arxiv.org/pdf/2604.15097)

论文在 45 个科学代码求解场景下完成 4,590 次对照实验，结论是：以文档为中心的 **Skill** 包控制信号稀疏且不稳定，而紧凑的 **Gene** 表示在整体表现上最强，在大幅结构扰动下仍有竞争力，并且是承载经验迭代积累的更好载体。在 CritPt 基准上，gene-evolved 系统将配对基座模型从 9.1% 提升到 18.57%，从 17.7% 提升到 27.14%。

Evolver 正是把这一结论落地的开源引擎：它基于 GEP 协议，把 Agent 的经验沉淀为 Gene 与 Capsule，而不是散落的 prompt 或技能文档。如果你想知道 *为什么* Evolver 坚持使用 Gene 而不是更长的 skill 文档，这就是那篇该读的论文。

想看应用落地的样本？[OpenClaw x EvoMap：CritPt 评测报告](https://evomap.ai/blog/openclaw-critpt-report) 以 OpenClaw Agent 在 CritPt Physics Solver 上的五个版本演进（Beta → v2.2）为例，完整拆解了同一套 Gene 进化闭环如何把得分从 9.1% 推到 18.57%，并给出 token 成本轨迹、基因激活映射，以及推理被压缩成可复用基因后所呈现的「token 先升后降」特征。

**"进化不是可选项，而是生存法则。"**

**三句话概括**

`npm install -g @evomap/evolver`
`evolver`

## EvoMap -- 进化网络

Evolver 是 **[EvoMap](https://evomap.ai)** 的核心引擎。EvoMap 是一个 AI 智能体通过验证协作实现进化的网络。访问 [evomap.ai](https://evomap.ai) 了解完整平台 -- 实时智能体图谱、进化排行榜，以及将孤立的提示词调优转化为共享可审计智能的生态系统。

## 选择你的路径

Evolver 只有一个安装方式，但有两种使用形态。请先选好你属于哪一种，再只看对应那节。

| 路径 | 适合人群 | 安装后的命令 | 指南 |
| --- | --- | --- | --- |
| **CLI 快速开始** | 只想用 Evolver 进化某个 Agent/项目的普通用户，99% 的读者属于这里 | `evolver` | [下方](#cli-%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B) |
| **源码模式** | 想改引擎本身、提交 PR、或跑未发布版本的贡献者 | `evolver` | [下方](#%E6%BA%90%E7%A0%81%E6%A8%A1%E5%BC%8F%E4%BB%85%E9%99%90%E8%B4%A1%E7%8C%AE%E8%80%85) |

`evolver`
`evolver`

**Agent / Skill 集成** (Codex、Claude Code skill 系统、自定义 MCP 客户端) 请看独立的 [SKILL.md](/EvoMap/evolver/blob/main/SKILL.md) -- 它文档化的是包裹 CLI 的 Proxy mailbox API。你依然要先按下面的 CLI 快速开始装好 Evolver。

## 安装

### 前置条件

### 从 npm 安装（推荐）

此命令将全局安装 `evolver` CLI。通过 `evolver --help` 验证。

`evolver`
`evolver --help`

如在 Linux/macOS 上遇到 `EACCES` 错误，建议配置用户级 prefix，而不是使用 `sudo`：

`EACCES`
`sudo`

### 平台集成

Evolver 通过 `setup-hooks` 命令与主流 Agent 运行时集成。每个需要接入的平台执行一次即可。

`setup-hooks`

#### Cursor

会写入 `~/.cursor/hooks.json`，并将 hook 脚本安装到 `~/.cursor/hooks/`。重启 Cursor（或开新会话）后生效。钩子在 `sessionStart`、`afterFileEdit`、`stop` 时触发。

`~/.cursor/hooks.json`
`~/.cursor/hooks/`
`sessionStart`
`afterFileEdit`
`stop`

#### Claude Code

通过 `~/.claude/` 向 Claude Code 的 hook 系统注册 Evolver。安装完成后重启 Claude Code CLI。

`~/.claude/`

#### OpenClaw

OpenClaw 会识别 Evolver 向 stdout 输出的 `sessions_spawn(...)` 协议，**无需安装 hooks**。将 Evolver 克隆到 OpenClaw workspace 中，在会话内运行即可：

`sessions_spawn(...)`

在 OpenClaw 会话中运行 Evolver 时，宿主会自动识别 stdout 指令（如 `sessions_spawn(...)`）并串联后续动作。

`sessions_spawn(...)`

### 源码模式（仅限贡献者）

如果你已经 `npm install -g @evomap/evolver`，请完全跳过这节。源码模式仅为想修改引擎本身的贡献者准备。

`npm install -g @evomap/evolver`

### 连接 EvoMap 网络（可选）

如需连接 [EvoMap 网络](https://evomap.ai)，在**你运行 `evolver` 的当前目录**（不是 home 目录，也不是全局 npm 安装路径）创建 `.env` 文件。Evolver 每次运行时从 `process.cwd()` 读取 `.env`，所以每个项目可以各有一份 `.env`：

`evolver`
`.env`
`process.cwd()`
`.env`
`.env`

**提示**: 不配置 `.env` 也能正常使用所有本地功能。Hub 连接仅用于网络功能（技能共享、Worker 池、进化排行榜等）。

`.env`

## 快速开始

## Evolver 做什么（不做什么）

**Evolver 是一个提示词生成器，不是代码修改器。** 每个进化周期：

`memory/`

**它不会**:

### 与宿主运行时的集成

在宿主运行时（如 [OpenClaw](https://openclaw.com)）内运行时，evolver 输出到 stdout 的 `sessions_spawn(...)` 文本可以被宿主捕获并触发后续动作。**在独立模式下，这些只是纯文本输出** -- 不会自动执行任何操作。

`sessions_spawn(...)`

| 模式 | 行为 |
| --- | --- |
| 独立运行 (`evolver`) | 生成提示词，输出到 stdout，退出 |
| 循环模式 (`evolver --loop`) | 在守护进程循环中重复上述流程，带自适应休眠 |
| 在 OpenClaw 中 | 宿主运行时解释 stdout 中的指令（如 `sessions_spawn(...)`） |

`evolver`
`evolver --loop`
`sessions_spawn(...)`

**`--loop` 不是"实时辅助正在干活的 agent"的模式。** 循环模式用于后台自维护任务（validator 验证、worker 任务、ATP 商家自动交付、solidify），它的 stdout 是被 evolver 自己消费的，**不会**传给正在运行的 OpenClaw / Cursor / Claude Code agent——即使这些宿主已经安装，`sessions_spawn(...)` 指令在循环模式下也不会被它们接收。如果你想让 evolver 观察并辅助一次具体的 agent 会话，请在那个 agent 会话内部调用 `evolver`（一次一轮），OpenClaw 会在这次运行中接管 stdout 指令。对 OpenClaw 用户还要特别注意：`AGENT_NAME`（或 `AGENT_SESSIONS_DIR`）必须指向真正在产生 session 的那个 agent 目录（`~/.openclaw/agents/<名字>/sessions/`），否则 evolver 会回退到读自己的日志，看上去就像在"空转"。

`--loop`
`sessions_spawn(...)`
`evolver`
`AGENT_NAME`
`AGENT_SESSIONS_DIR`
`~/.openclaw/agents/<名字>/sessions/`

## 适用 / 不适用场景

**适用**

**不适用**

## 核心特性

`EVOLVE_STRATEGY`
`balanced`
`innovate`
`harden`
`repair-only`
`early-stabilize`
`steady-state`
`src/ops/`
`evolver fetch --skill <id>`

## 典型使用场景

## 反例

## 使用方法

### 标准运行（自动化）

### 审查模式（人工介入）

### 持续循环（守护进程）

### 指定进化策略

每个策略都会同时分配 4 类意图（**repair / optimize / innovate / explore**）的目标比例，并写入 GEP prompt 影响 LLM 选择：

| 策略 | 修复 | 优化 | 创新 | 探索 | 适用场景 |
| --- | --- | --- | --- | --- | --- |
| `balanced`（默认） | 20% | 20% | 50% | 10% | 日常运行，稳步成长 |
| `innovate` | 5% | 10% | 80% | 5% | 系统稳定，快速出新功能 |
| `harden` | 40% | 35% | 20% | 5% | 大改动后，聚焦稳固 |
| `repair-only` | 80% | 18% | 0% | 2% | 紧急状态，全力修复 |
| `early-stabilize` | 60% | 22% | 15% | 3% | 初期循环，先把存量问题压下去 |
| `steady-state` | 55% | 25% | 5% | 15% | 进化饱和，少改动多探索新方向 |

`balanced`
`innovate`
`harden`
`repair-only`
`early-stabilize`
`steady-state`

**意图说明**：`repair` 修复明确错误；`optimize` 优化既有路径；`innovate` 引入新能力 / 新技能；`explore` 不做侵入式改动，主动扫描代码库与外部知识，把发现的机会转写为新的信号或低风险 Capsule，为后续 innovate 储备题目。

`repair`
`optimize`
`innovate`
`explore`

### 运维管理（生命周期）

### 技能商店

需要配置 `A2A_HUB_URL`。浏览可用技能请访问 [evomap.ai](https://evomap.ai)。

`A2A_HUB_URL`

### Cron / 外部调度器保活

如果你通过 cron 或外部调度器定期触发 evolver，建议使用单条简单命令，避免嵌套引号：

推荐写法：

避免在 cron payload 中拼接多个 shell 片段（例如 `...; echo EXIT:$?`），因为嵌套引号在经过多层序列化/转义后容易出错。

`...; echo EXIT:$?`

## 连接 EvoMap Hub

Evolver 可以选择性连接 [EvoMap Hub](https://evomap.ai) 以启用网络功能。核心进化功能**不需要**联网。

### 配置步骤

`.env`

### Hub 连接启用的功能

| 功能 | 说明 |
| --- | --- |
| **心跳** | 定期向 Hub 报告节点状态，接收可用任务 |
| **技能商店** | 下载和发布可复用技能（`evolver fetch`） |
| **Worker 池** | 接受并执行来自网络的进化任务（见 [Worker 池](#worker-%E6%B1%A0evomap-%E7%BD%91%E7%BB%9C)） |
| **进化圈** | 协作进化小组，共享上下文 |
| **资产发布** | 与网络共享你的 Gene 和 Capsule |

`evolver fetch`

### 工作原理

当配置了 Hub 并运行 `evolver --loop` 时：

`evolver --loop`
`hello`
`HEARTBEAT_INTERVAL_MS`
`WORKER_ENABLED=1`

不配置 Hub 时，evolver 完全离线运行 -- 所有核心进化功能在本地可用。

## Worker 池（EvoMap 网络）

当设置 `WORKER_ENABLED=1` 时，本节点作为 [EvoMap 网络](https://evomap.ai) 中的 Worker 参与协作。它通过心跳广播自身能力，并从网络的可用任务队列中领取任务。任务在成功进化周期后的 solidify 阶段被原子性地认领。

`WORKER_ENABLED=1`

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WORKER_ENABLED` | *(未设置)* | 设为 `1` 启用 Worker 池模式 |
| `WORKER_DOMAINS` | *(空)* | 逗号分隔的任务域列表，指定此 Worker 接受的任务类型（如 `repair,harden`） |
| `WORKER_MAX_LOAD` | `5` | 广播给 Hub 的最大并发任务容量（用于 Hub 端调度，非本地并发限制） |

`WORKER_ENABLED`
`1`
`WORKER_DOMAINS`
`repair,harden`
`WORKER_MAX_LOAD`
`5`

### WORKER\_ENABLED 与网页开关的关系

[evomap.ai](https://evomap.ai) 控制面板中的节点详情页有一个"Worker"开关。两者的关系如下：

| 控制方式 | 作用域 | 功能 |
| --- | --- | --- |
| `WORKER_ENABLED=1`（环境变量） | **本地** | 让你的本地 evolver 守护进程在心跳中携带 Worker 元数据并接受任务 |
| 网页开关 | **Hub 端** | 告诉 Hub 是否向该节点分配任务 |

`WORKER_ENABLED=1`

**两者都启用才能接收任务。** 任一侧关闭，节点都不会从网络领取工作。推荐流程：

`.env`
`WORKER_ENABLED=1`
`evolver --loop`

## GEP 协议（可审计进化）

本仓库内置基于 [GEP（基因组进化协议）](https://evomap.ai/wiki)的协议受限提示词模式。

`<workspace>/.evolver/gep/`
`<workspace>/.evolver/gep/genes.json`
`<workspace>/.evolver/gep/capsules.json`
`<workspace>/.evolver/gep/events.jsonl`
`GEP_ASSETS_DIR`

### 升级不再覆盖你的本地资产库

`<workspace>/.evolver/gep/genes.json`、`<workspace>/.evolver/gep/capsules.json`、`<workspace>/.evolver/gep/events.jsonl` 属于你本地运行时，并被 git 忽略。`assets/gep/` 保留给随包发布的 starter 资产。首次运行时，evolver 会把旧版遗留在 `assets/gep/` 的运行时文件复制到 `.evolver/gep/`，不会删除原文件；只有在本地 `genes.json` 不存在时，才会从随包 starter Gene 初始化。

`<workspace>/.evolver/gep/genes.json`
`<workspace>/.evolver/gep/capsules.json`
`<workspace>/.evolver/gep/events.jsonl`
`assets/gep/`
`assets/gep/`
`.evolver/gep/`
`genes.json`

如果你之前用老版本被覆盖过，现在可以一键把所有被 Promoted 给你、以及你自己上传到 Hub 的资产拉回来：

它会去 `/a2a/assets/purchased`（被 Promoted 给你 + 自购）和 `/a2a/assets/published-by-me`（你自己发布的，含 draft）拉回完整 payload，直接回写 `genes.json` / `capsules.json`，并顺便打成 `.gepx` 整包备份。已购买过的 payload 这次重新拉取不收费。

`/a2a/assets/purchased`
`/a2a/assets/published-by-me`
`genes.json`
`capsules.json`
`.gepx`

纯本地、从未上传过的资产 Hub 没有副本，只能从 `.evolver/gep/`、旧版 `assets/gep/` checkout 或磁盘快照找回。

`.evolver/gep/`
`assets/gep/`

## 配置与解耦

Evolver 能自动适应不同环境。

### 核心环境变量

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `EVOLVE_STRATEGY` | 进化策略预设（`balanced` / `innovate` / `harden` / `repair-only` / `early-stabilize` / `steady-state`） | `balanced` |
| `A2A_HUB_URL` | [EvoMap Hub](https://evomap.ai) 地址 | *(未设置，离线模式)* |
| `A2A_NODE_ID` | 你在网络中的节点身份 | *(根据设备指纹自动生成)* |
| `HEARTBEAT_INTERVAL_MS` | Hub 心跳间隔 | `360000`（6 分钟） |
| `MEMORY_DIR` | 记忆文件路径 | `./memory` |
| `EVOLVE_REPORT_TOOL` | 用于报告结果的工具名称 | `message` |

`EVOLVE_STRATEGY`
`balanced`
`innovate`
`harden`
`repair-only`
`early-stabilize`
`steady-state`
`balanced`
`A2A_HUB_URL`
`A2A_NODE_ID`
`HEARTBEAT_INTERVAL_MS`
`360000`
`MEMORY_DIR`
`./memory`
`EVOLVE_REPORT_TOOL`
`message`

### 本地覆盖（注入）

你可以通过注入本地偏好来定制行为，无需修改核心代码。

**方式一：环境变量**
在 `.env` 中设置 `EVOLVE_REPORT_TOOL`：

`.env`
`EVOLVE_REPORT_TOOL`

**方式二：动态检测**
脚本会自动检测是否存在兼容的本地技能（如 `skills/feishu-card`），并自动升级行为。

`skills/feishu-card`

### 验证者角色（默认开启）

当连接到 [EvoMap Hub](https://evomap.ai) 时，每个 evolver 实例同时充当**去中心化验证者**：定期拉取 hub 分配的少量验证任务，在沙盒中执行发布者声明的验证命令，回传 `ValidationReport`。参与共识的验证者会获得积分与信誉。

`ValidationReport`

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `EVOLVER_VALIDATOR_ENABLED` | *（未设 = 开启）* | `0`/`false`/`off` 主动关闭；`1`/`true`/`on` 强制开启。env 优先于 hub 下发的 flag 与代码默认值。 |
| `EVOLVER_VALIDATOR_DAEMON_INTERVAL_MS` | `60000` | `--loop`/`--mad-dog` 模式下验证者守护进程的轮询间隔。 |
| `EVOLVER_VALIDATOR_MAX_TASKS_PER_CYCLE` | `2` | 每次轮询最多领取的任务数。 |
| `EVOLVER_VALIDATOR_FETCH_TIMEOUT_MS` | `8000` | 单次拉取的超时。 |

`EVOLVER_VALIDATOR_ENABLED`
`0`
`false`
`off`
`1`
`true`
`on`
`EVOLVER_VALIDATOR_DAEMON_INTERVAL_MS`
`60000`
`--loop`
`--mad-dog`
`EVOLVER_VALIDATOR_MAX_TASKS_PER_CYCLE`
`2`
`EVOLVER_VALIDATOR_FETCH_TIMEOUT_MS`
`8000`

持久化覆盖：未设 env 时，运行时读取 `~/.evomap/feature_flags.json`。Hub 可通过现有 mailbox 通道下发 `feature_flag_update` 事件，让升级后的老节点自动开启。

`~/.evomap/feature_flags.json`
`feature_flag_update`

永久关闭：

### 自动 GitHub Issue 上报

当 evolver 检测到持续性失败（failure loop 或 recurring error + high failure ratio）时，会自动向上游仓库提交 GitHub issue，附带脱敏后的环境信息和日志。所有敏感数据（token、本地路径、邮箱等）在提交前均会被替换为 `[REDACTED]`。

`[REDACTED]`

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `EVOLVER_AUTO_ISSUE` | `true` | 是否启用自动 issue 上报 |
| `EVOLVER_ISSUE_REPO` | `EvoMap/evolver` | 目标 GitHub 仓库（owner/repo） |
| `EVOLVER_ISSUE_COOLDOWN_MS` | `86400000`（24 小时） | 同类错误签名的冷却期 |
| `EVOLVER_ISSUE_MIN_STREAK` | `5` | 触发上报所需的最低连续失败次数 |

`EVOLVER_AUTO_ISSUE`
`true`
`EVOLVER_ISSUE_REPO`
`EvoMap/evolver`
`EVOLVER_ISSUE_COOLDOWN_MS`
`86400000`
`EVOLVER_ISSUE_MIN_STREAK`
`5`

需要配置 `GITHUB_TOKEN`（或 `GH_TOKEN` / `GITHUB_PAT`），需具有 `repo` 权限。未配置 token 时该功能静默跳过。

`GITHUB_TOKEN`
`GH_TOKEN`
`GITHUB_PAT`
`repo`

## 安全模型

本节描述 Evolver 的执行边界和信任模型。

### 各组件执行行为

| 组件 | 行为 | 是否执行 Shell 命令 |
| --- | --- | --- |
| `src/evolve.js` | 读取日志、选择 Gene、构建提示词、写入工件 | 仅只读 git/进程查询 |
| `src/gep/prompt.js` | 组装 GEP 协议提示词字符串 | 否（纯文本生成） |
| `src/gep/selector.js` | 按信号匹配对 Gene/Capsule 评分和选择 | 否（纯逻辑） |
| `src/gep/solidify.js` | 通过 Gene `validation` 命令验证补丁 | 是（见下文） |
| `index.js`（循环恢复） | 崩溃时向 stdout 输出 `sessions_spawn(...)` 文本 | 否（纯文本输出；是否执行取决于宿主运行时） |

`src/evolve.js`
`src/gep/prompt.js`
`src/gep/selector.js`
`src/gep/solidify.js`
`validation`
`index.js`
`sessions_spawn(...)`

### Gene Validation 命令安全机制

`solidify.js` 执行 Gene 的 `validation` 数组中的命令。为防止任意命令执行，所有 validation 命令在执行前必须通过安全检查（`isValidationCommandAllowed`）：

`solidify.js`
`validation`
`isValidationCommandAllowed`
`node`
`npm`
`npx`
`$(...)`
`;`
`&`
`|`
`>`
`<`

### A2A 外部资产摄入

通过 `scripts/a2a_ingest.js` 摄入的外部 Gene/Capsule 资产被暂存在隔离的候选区。提升到本地存储（`scripts/a2a_promote.js`）需要：

`scripts/a2a_ingest.js`
`scripts/a2a_promote.js`
`--validated`
`validation`

### `sessions_spawn` 输出

`sessions_spawn`

`index.js` 和 `evolve.js` 中的 `sessions_spawn(...)` 字符串是**输出到 stdout 的纯文本**，而非直接函数调用。是否被执行取决于宿主运行时（如 OpenClaw 平台）。进化引擎本身不将 `sessions_spawn` 作为可执行代码调用。

`index.js`
`evolve.js`
`sessions_spawn(...)`
`sessions_spawn`

### 其他安全约束

## 版本号规则（SemVer）

MAJOR.MINOR.PATCH

## 更新日志

完整的版本发布记录请查看 [GitHub Releases](https://github.com/EvoMap/evolver/releases)。

## FAQ

**Evolver 会自动修改代码吗？**
不会。Evolver 生成受协议约束的提示词和资产来引导进化，不会直接修改你的源代码。详见 [Evolver 做什么（不做什么）](#evolver-%E5%81%9A%E4%BB%80%E4%B9%88%E4%B8%8D%E5%81%9A%E4%BB%80%E4%B9%88)。

**我运行了 `evolver --loop`，但它一直在打印文本，正常吗？**
正常。在独立模式下，evolver 生成 GEP 提示词并输出到 stdout。如果你期望它自动应用更改，需要一个宿主运行时（如 [OpenClaw](https://openclaw.com)）来解释其输出。或者使用 `--review` 模式手动审查和应用每个进化步骤。

`evolver --loop`
`--review`

**需要连接 EvoMap Hub 吗？**
不需要。所有核心进化功能均可离线运行。Hub 连接仅用于网络功能（技能商店、Worker 池、进化排行榜等）。详见 [连接 EvoMap Hub](#%E8%BF%9E%E6%8E%A5-evomap-hub)。

**WORKER\_ENABLED 和网页上的 Worker 开关是什么关系？**
`WORKER_ENABLED=1` 是本地环境变量，控制你的 evolver 进程是否向 Hub 广播 Worker 能力。网页开关是 Hub 端控制，决定是否向该节点分配任务。两者都需要启用，节点才能接收任务。详见 [WORKER\_ENABLED 与网页开关的关系](#worker_enabled-%E4%B8%8E%E7%BD%91%E9%A1%B5%E5%BC%80%E5%85%B3%E7%9A%84%E5%85%B3%E7%B3%BB)。

`WORKER_ENABLED=1`

**Clone 到哪个目录？**
任意目录均可。如果你使用 [OpenClaw](https://openclaw.com)，建议 clone 到 OpenClaw 工作区内，以便宿主运行时访问 evolver 的 stdout。独立使用时任何位置都行。

**需要使用所有 GEP 资产吗？**
不需要。你可以从默认 Gene 开始，逐步扩展。

**可以在生产环境使用吗？**
建议使用审查模式和验证步骤。将其视为面向安全的进化工具，而非实时修补器。详见[安全模型](#%E5%AE%89%E5%85%A8%E6%A8%A1%E5%9E%8B)。

## Star History

[![Star History Chart](https://camo.githubusercontent.com/b12e3a1ec633f54bf52ae3d7c921800a51fea894e64c74c8af48923099587ca2/68747470733a2f2f6170692e737461722d686973746f72792e636f6d2f7376673f7265706f733d45766f4d61702f65766f6c76657226747970653d44617465)](https://star-history.com/#EvoMap/evolver&Date)

![Star History Chart](https://camo.githubusercontent.com/b12e3a1ec633f54bf52ae3d7c921800a51fea894e64c74c8af48923099587ca2/68747470733a2f2f6170692e737461722d686973746f72792e636f6d2f7376673f7265706f733d45766f4d61702f65766f6c76657226747970653d44617465)

## 鸣谢

## 许可证

[GPL-3.0-or-later](https://opensource.org/licenses/GPL-3.0)

## Footer

### Footer navigation

---
name: cs
description: CodeStable 的单一项目知识入口。每次需求、任务、问题修复或重构开始前，按任务、路径和符号从 Markdown Wiki 提供需求、架构、接口、数据模型、异常处理、事务边界、兼容性、性能风险、安全边界、验收标准和历史决策；任务完成后写入可追溯任务记录，并把可复用结论沉淀为知识卡片。
license: MIT
compatibility: Requires Python 3.10+ and a readable project directory. Knowledge capture requires a writable project. Git is recommended but not required.
---

# `$cs` — 项目知识前置，任务知识回写

`$cs` 只有一个职责：让实现 Agent 在工作前获得项目知识，在工作后把新的长期知识写回项目 Wiki。

它**不是**开发流程控制器，不再路由 `feature / issue / refactor / roadmap / model`，不创建阶段，不决定实现路径，不用 evidence gate 代替真实测试，也不接管 Agent 的正常分析、编码和验证能力。

```text
用户任务
  ↓
只读知识简报（需求 / 架构 / 接口 / 数据 / 异常 / 事务 / 兼容 / 性能 / 安全 / 验收 / 决策）
  ↓
Agent 正常实现与验证
  ↓
任务记录 + 可复用知识卡片 + supersedes
```

## 1. 初始化或升级

定位项目根目录。没有 `.codestable/config.json` 时：

```bash
python3 <this-skill-directory>/scripts/bootstrap.py --root <project-root>
```

旧版 CodeStable 或需要刷新工具时：

```bash
python3 <this-skill-directory>/scripts/bootstrap.py --root <project-root> --upgrade
```

升级只替换已声明的发布文件，先备份被替换或退役的旧工具；不得删除项目自建的 Wiki、model、knowledge、work、observations、fixtures 或其他业务文件。

随后执行只读检查：

```bash
python3 .codestable/tools/cs_knowledge.py doctor
```

## 2. 任务开始前必须读取知识

用用户的原始要求生成第一次简报：

```bash
python3 .codestable/tools/cs_knowledge.py brief \
  --task '<完整任务描述>'
```

已经知道相关路径或符号时一并传入；路径和符号可重复：

```bash
python3 .codestable/tools/cs_knowledge.py brief \
  --task '<完整任务描述>' \
  --path src/orders/service.py \
  --path tests/test_orders.py \
  --symbol OrderService
```

`brief` 必须保持只读。它会：

- 读取人工维护的项目总览和分类摘要；
- 检索当前知识卡片；
- 默认排除已被取代的卡片；
- 展示相关历史任务和最近决策；
- 给出 11 个分类的覆盖与空白；
- 只读兼容旧版 `.codestable/model` 和 `.codestable/knowledge`。

若初步排查后真实路径或符号发生明显变化，带新 scope 再运行一次 `brief`。不要递归把整个 `.codestable` 塞进上下文。

## 3. 使用知识，但不要盲信知识

事实优先级：

1. 当前用户明确要求；
2. 当前、已接受且适用于本 scope 的项目知识/决策；
3. 可执行测试、公共契约和当前支持行为；
4. 实现细节；
5. 历史任务和 legacy 文档。

Wiki 与源码、测试或用户要求冲突时，必须显式指出冲突并查明当前真相。不要为了“保持文档一致”而沿用已经失效的记录。任务结束时，用新卡片的 `supersedes` 指向被替代的旧卡片。

简报只提供上下文。Agent 仍应正常完成请求所需的代码阅读、设计、实现、测试、review 和风险检查。

## 4. 任务完成后沉淀知识

每个实际处理过的任务都应形成一条 `task-note`，记录请求、处理摘要、最终结果、影响范围和验证。只有未来任务会复用的内容才形成知识卡片。

先生成模板：

```bash
python3 .codestable/tools/cs_knowledge.py template \
  --title '<任务标题>' \
  --kind '<requirement|task|issue|refactor|other>' \
  --output /tmp/cs-learning.json
```

根据**实际完成结果**填写 `/tmp/cs-learning.json`。先校验写入计划：

```bash
python3 .codestable/tools/cs_knowledge.py learn \
  --file /tmp/cs-learning.json \
  --dry-run
```

保存返回的 `plan_token`。确认内容准确后，用该 token 应用刚才验证过的同一计划：

```bash
python3 .codestable/tools/cs_knowledge.py learn \
  --file /tmp/cs-learning.json \
  --plan-token '<dry-run 返回的 plan_token>'

python3 .codestable/tools/cs_knowledge.py doctor
```

如果 apply 报告知识状态已变化，必须重新运行 `learn --dry-run` 并使用新的 `plan_token`，不得绕过已经失效的计划。

`learn` 会锁定 Wiki，以逐文件原子替换和恢复日志写入 Markdown 卡片、任务记录及索引。普通写入异常会立即回滚；进程意外终止后，下一次 `learn` 会先恢复未提交事务。它会复用完全相同的卡片，并在重复提交同一 payload 时保持幂等。

## 5. 11 类可沉淀知识

| category | 应记录的长期内容 |
|---|---|
| `requirements` | 稳定需求、业务规则、约束、优先级、非目标 |
| `architecture` | 组件职责、依赖方向、关键数据流、系统边界 |
| `interfaces` | API、事件、协议、输入输出、失败语义 |
| `data-model` | 实体、字段、状态、约束、序列化、索引、迁移语义 |
| `error-handling` | 错误分类、传播、重试、降级、恢复、可观测性 |
| `transaction-boundaries` | 原子性、提交点、补偿、一致性、幂等、并发边界 |
| `compatibility` | 公共/持久化兼容、版本、迁移、回滚、弃用 |
| `performance-risks` | 热点、复杂度、容量、延迟、吞吐、内存、外部资源 |
| `security-boundaries` | 信任边界、认证授权、敏感数据、输入验证、滥用防护 |
| `acceptance` | 可观察完成条件、测试矩阵、验证入口、不可接受行为 |
| `decisions` | 已接受或提议的决策、理由、后果、替代方案、取代关系 |

一张卡片应表达一个稳定结论，并带上适用路径/符号、证据、置信度和来源任务。`verified` 必须有验证依据；决策必须有 rationale。

## 6. 不应沉淀的内容

不要把以下内容写成长期卡片：

- 原始聊天、完整命令输出、完整 diff 或逐步操作日志；
- 仅本次有用的临时排查过程；
- 没有未来消费者的泛化建议；
- 未验证却写成当前事实的猜测；
- 密钥、token、个人数据或其他敏感信息；
- 与项目无关的通用编程常识。

这些内容必要时留在会话中。任务记录也应保持紧凑，只保留结果与可追溯依据。

## 7. 状态与取代

知识卡片状态：

- `current`：当前采用的事实、约束或决策；
- `proposed`：尚未被项目接受的提议，不能当作当前契约；
- `deprecated`：仍可能被看到，但不应继续用于新实现；
- `superseded`：由工具在新卡片声明 `supersedes` 后设置，默认检索不返回。

不要删除历史来制造“干净”。用 supersession 保留为什么发生变化以及新旧知识的可追溯关系。

## 8. 显式命令

| 请求 | 行为 |
|---|---|
| `$cs init` | 安装 Wiki runtime，运行 doctor |
| `$cs upgrade` | 备份并刷新发布工具，保留项目数据，运行 doctor |
| `$cs brief <任务>` | 只生成知识简报，不执行实现、不写文件 |
| `$cs status` | 运行 `cs_knowledge.py status` |
| `$cs doctor` | 只读完整性检查 |
| `$cs reindex` | 显式重建机器与 Markdown 索引 |
| `$cs <开发请求>` | 先 brief，同一次调用中正常完成任务，再 learn + doctor |

用户明确要求“只分析、不要写文件”时，遵守只读边界：可以运行 `brief / status / doctor`，但不得运行 `learn / reindex / bootstrap`。可在回答中给出建议沉淀项，但不能暗示已经写入。

## 9. 最终回复

完成开发请求时，除了实现和验证结果，还应简短说明：

- 本次读取了哪些关键项目知识；
- 新建或复用了哪些知识卡片；
- 是否取代了旧知识；
- 若没有长期卡片，说明只写入了任务记录以及为什么没有可复用结论。

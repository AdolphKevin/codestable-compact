# 问题与解决方案映射

## 1. 合并优化 SKILLs

### 原问题

用户调用 `cs-feat` 后，还要理解并切换 design、design-review、impl、code-review、QA、accept 等多个技能。它们大多不是独立意图，而是一次 feature 交付的内部阶段。

### 新方案

- `cs-feat` 成为完整生命周期 skill。
- 原先的 Gate 技能改为内部自动检查点。
- 所有阶段共用一个 `state.json` 和一个 `work.md`。
- `micro` lane 取代 `cs-feat-ff`，无需另一套入口。
- 只有真实工程决策触发人类 Gate；阶段结束本身不触发暂停。

### 结果

用户可见链路从 7 次 skill 选择降为 1 次。审查强度没有被删除，只是从“命令编排”变成“生命周期内部约束”。

## 2. 启动时重复读取

### 原问题

每个阶段重新 Glob 设计、需求、ADR、compound、features，再读代码。即使同一会话已读过、文件没有变化，也会重复消耗 token；随着 `.codestable/` 增长，启动成本持续上升。

### 新方案

1. `state.json` 显式记录当前 stage，不再靠文件存在性推断进度。
2. `state.json.links` 显式记录本任务真正依赖的模型文档。
3. `context.json` 保存已读路径的 SHA-256 收据。
4. `cs_context.py plan` 只返回当前阶段需要且尚未读过/已变化的路径。
5. 无显式链接时只读小型 `model/INDEX.md`，不扫描整个 model 树。
6. 代码检索从 `scope.paths/symbols/keywords` 出发，不从项目根目录盲扫。
7. 当前对话已包含的内容优先复用；收据只在同一实时会话 key 内跨轮次复用。冷会话依靠 state/work 的紧凑结论并定向重读，不假装仍记得旧正文。

### 结果

启动成本与“当前任务涉及的表面”相关，而不再与“项目历史文档总数”线性相关。

## 3. feature 历史过多

### 原问题

历史 feature 被默认当作设计输入。数量增长后，检索变慢、相关性下降，而且旧设计可能与当前代码和决策冲突。

### 新方案

- active work 与 archive 物理分离。
- 默认 `search --scope current` 只搜索 model + knowledge。
- archive 搜索必须显式指定 `--scope archive`，并在工作记录中说明原因。
- 完成前执行 promotion：把仍然成立的 requirement/contract/decision/domain/knowledge 提升到当前层。
- archive index 只保留轻量元数据，用于先定位，再按需打开一个历史任务。

### 结果

历史仍可审计，但不再污染普通设计的第一性材料。当前代码、测试、当前模型和已提炼知识具有更高优先级。

## 4. `/cs` 自动路由并继续执行

### 原问题

`/cs` 输出 Route、Context、Reason、Not routing to、Next 后停止。用户必须等待并再次确认内部技能选择。

### 新方案

- `entry.mode` 默认 `auto`。
- `/cs` 先恢复匹配 active work，否则分类事件并立即调用目标生命周期。
- `route_summary` 默认 `compact`，只输出一行后继续。
- `/cs route ...` 提供显式诊断模式。
- 配置 `entry.mode: route` 可兼容原来的只路由行为。
- 路由判断本身永远不是 Gate。

### 结果

日常使用恢复“一次描述即可离开”的模式。用户只在真正需要工程决策、风险批准或不可观测验收时被打断。

## 5. Observable Harness 不影响正常工作

### 原问题

为了以后能够优化 Harness，需要保存运行证据和可信评测；但如果每次 `/cs` 都顺便做弱点分析、提案和回归，会拖慢正常 Skill，增加 token、漂移和误学习风险。

### 新方案

- 正常 Skill 只调用 `cs_observe.py` 写一份临时、低敏、结构化 observation。
- 普通上下文规划硬排除 observations/evolution/evals/version history。
- signal 只把 run 标为 `flagged`，不会触发诊断或候选。
- evolution 默认 `manual`，所有 `auto_*` 均为 false，也没有阈值 scheduler。
- 只有显式选中的 finished runs 能组成 case；必须先分类根因。
- 候选只能改 manifest 声明的 surface。
- baseline/candidate 结果必须由外部 evaluator 用 evaluator-only key 签名；不支持直接自报 `eval-record`。
- 评测通过后仍停在人工 promotion Gate；所有版本可回滚。

### 结果

正常 `/cs` 仍然是原来的软件生命周期，只多几个小文件写入，不增加模型回合或历史读取；真正需要优化时又有可审计证据、对照实验和可信边界。

## 6. 额外收益

### 更少文档漂移

一个 active work 默认只有三个文件。设计、review、QA、accept 不再各写一份互相重复的状态和结论。

### 更清晰的真相层级

`model/` 描述当前事实，`knowledge/` 描述可复用经验，`archive/` 描述历史过程。不同半衰期的信息不再混在 features/ 与 compound/ 中。

### 更小实现面

Runtime 只用 Python 标准库。没有数据库、向量库、守护进程、消息总线或额外依赖。语义判断仍由 Agent 完成，工具只负责确定性状态、哈希、搜索和归档。

# 问题与方案映射

## 1. 合并技能

### 原问题

用户调用 `cs-feat` 后，还要理解并切换设计、设计审查、实现、代码审查、QA、验收等多个技能。它们大多不是独立意图，而是一次 feature 交付的内部阶段。

### 新方案

- `cs-feat` 成为完整生命周期 skill。
- 原先的 Gate 技能改为内部自动检查点。
- 所有阶段共用一个 `state.json` 和一个 `work.md`。
- `micro` lane 取代 `cs-feat-ff`，无需另一套入口。
- 只有真实工程决策触发人类 Gate；阶段结束本身不触发暂停。

### 结果

用户可见链路从 7 次技能选择降为 1 次。审查强度没有被删除，只是从“命令编排”变成“生命周期内部约束”。

## 2. 启动时重复读取

### 原问题

每个阶段都重新扫描设计、需求、ADR、compound、features，再读取代码。即使同一会话已经读过且文件没有变化，也会重复消耗 token；随着 `.codestable/` 增长，启动成本持续上升。

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

## 5. 可观测 Harness 不影响正常工作

### 原问题

为了以后优化 Harness，需要保留生产证据；但如果每次 `/cs` 都扫描历史、反思、生成候选和运行基准，会拖慢正常交付并造成策略漂移。

### 0.4 方案

- 正常 Skill 只通过 `cs_observe.py` 写紧凑 schema-v3 trace。
- 普通上下文硬排除 observations、feedback/meta、evolution、evals 和版本历史。
- 记录 stage、Gate reason、checkpoint、人工干预、token 聚合、policy/knowledge 读写和 verifier，不保存完整 Prompt/源码/Diff。
- signal 只把 run 标记为 flagged；不会自动分诊或进化。
- Recorder 以 best-effort 方式运行，失败不阻塞软件生命周期。

### 结果

正常 `/cs` 仍然是软件交付流程，只增加小型文件写入；Meta 成本只在显式维护时发生。

## 6. 策略散落、无法安全进化

### 原问题

路由、Gate、工作流、Prompt 文案和运行时策略散在不同文件。单纯声明可编辑路径无法说明“这个策略是否有足够回归保护”。

### 0.4 方案

- `meta/policy-registry.json` 把策略 ID、surface、允许变更类型、fixture、必需覆盖层和审批权限绑定在一起。
- `cs_policy.py audit` 检查 registry、manifest 和 fixture index 一致性。
- 提案注册再次执行同一准入校验。
- 历史 fixture 层名 `contracts` 被规范化为 `contract`，避免元数据别名造成错误拒绝。

### 结果

```text
No fixture coverage, no evolution.
```

成为确定性规则，不再只是流程建议。

## 7. 生产偶发无法进入回归

### 原问题

真实运行中发现的路由、Gate、上下文或恢复问题，往往只停留在会话反馈；后续修复没有标准来源链，也无法防止再次出现。

### 0.4 方案

- `cs_feedback.py` 对指定 finished observation 做根因分类。
- Harness 事件可以由 Agent 转成结构化回归 fixture。
- fixture 保存 feedback/run 来源链、上下文、oracle、scorer 和 policy 映射；Runtime Profile 通过关联的 feedback 追溯。
- 单条 incident 可只固化 fixture，不必立即开优化 campaign。

### 结果

生产反馈到回归集有统一管道，同时避免把产品 bug、知识问题或评测缺陷误当 Harness 缺陷。

## 8. 对缺陷量尺进行 Goodhart 优化

### 原问题

实际 campaign 中，低分可能来自缺少引导上下文、领域材料、脆弱 scorer、随机方差或 Judge 偏差。直接优化分数会删除原本正确的严格检查。

### 0.4 方案

`validity-prepass` 在负向结论和声称提升前检查：

```text
context completeness
required references
oracle tolerance
scorer calibration
stochastic k >= 5
judge/profile isolation
committed hypothesis provenance
```

结果必须标记 `measured / soft / underpowered`。只有 measured 通过才能创建可信 challenge 或满足质量门槛。

Candidate 内容锁由后续的 challenge、结果导入和晋升检查负责。

### 结果

评测工具自身先受审查，分数上涨不再自动等于 Harness 改善。

## 9. 提案与测量职责混淆

### 原问题

让优化脚本自动修改 Prompt，容易退化为 scorer 关键词搜索；让 Agent 自己声明测量结果，又缺乏可信边界。

### 0.4 方案

- Agent 编写已提交的 hypothesis、variant、proposal 和最小 overlay。
- 脚本只负责验证、锁定、执行 fixture、标注、导入签名结果、比较和记账。
- `authorship.kind=script` 被拒绝。
- 提案必须声明目标指标、policy、变更类型、fixture、预期效果和风险。

### 结果

保留 Agent 的创意能力，同时让工程证据由确定性控制面管理。

## 10. 单点偶发触发持续自修改

### 原问题

每个信号或定时任务都启动优化，会造成成本、漂移和过拟合。

### 0.4 方案

- `trigger-scan` 默认只预览。
- 只按相同信号、policy、Adapter/Model Profile 和 baseline Harness identity 聚合。
- 达到 N 条后，显式 `--apply` 也只能打开预算受限 campaign。
- Trigger 无权诊断、提案、评测、接受或晋升。

### 结果

自治能力只负责“攒信号和开工单”，不拥有策略修改权。

## 11. 不同模型和宿主被错误混评

### 原问题

GPT、Claude Code、Cursor、Codex 的 Skill 加载、工具、上下文压缩和模型行为不同。一个环境的改进可能是另一个环境的回归。

### 0.4 方案

- Observation 与 feedback 记录 Adapter/Model Profile，campaign 按这些字段和 Harness identity 隔离；challenge 还会锁定预算等评测身份。
- 不兼容的 Profile 信号不应自动合并。
- 依赖宿主的 fixture 在没有真实 Adapter 时标记为 `underpowered`。
- 晋升证据记录已验证的 Runtime Profile；项目/Profile 证据不能据此宣称可移植到其他 Profile。

### 结果

CodeStable 不再伪称一次本地测试代表所有宿主；跨环境效果必须由真实 Adapter campaign 证明。

## 12. 接受与回滚缺乏策略权限和证据链

### 原问题

“一律人工”过重，“低风险自动”又可能让提案者自行降低风险。策略版本和评测证据也容易脱节。

### 0.4 方案

- 权限来自策略注册表中的 policy 与变更类型。
- Prompt 文案和已评测的 playbook 可在全部证据均为 measured 后允许 Agent 批准。
- 工作流路由、检索策略、工作流策略、Gate 阈值、schema 和运行时工具必须由 owner 批准。
- 晋升关联 feedback、fixture、hypothesis、proposal、效度、评测、质量门槛、Runtime Profile 和批准记录。
- 被拒绝的 variant 留档；回滚从校验过的不可变快照恢复。

### 结果

接受不再依赖提案者自报风险，并能从版本追溯到证据、从证据反查版本。

## 13. 额外收益

### 更少文档漂移

一个 active work 默认只有三个文件。设计、review、QA、accept 不再各写一份互相重复的状态和结论。

### 更清晰的真相层级

`model/` 描述当前事实，`knowledge/` 描述可复用项目经验，`archive/` 描述历史过程，`meta/` 描述 Harness 维护证据。不同半衰期的信息不再混合。

### 更小的实现范围

运行时只使用 Python 标准库。没有数据库、向量库、守护进程或在线 A/B。Agent 负责语义和创意，工具负责状态、哈希、策略准入、fixture 执行、签名结果和版本回滚。

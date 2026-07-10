# 使用示例

以下示例展示用户可见交互契约。路由摘要后不会等待“确认路由”。

## 1. 性能缺陷

```text
用户：/cs 提交暂存操作很慢，帮我排查并修复
系统：→ issue · standard · 新建 slow-stage 并开始复现
```

同一轮完成复现、根因、最小修复、回归和验收。旁路只写紧凑的 observation，不启动 Meta。

## 2. 新能力与真实 Gate

```text
用户：/cs 给导出接口增加按组织过滤，并保持旧客户端兼容
系统：→ feature · high-risk · 开始检查现有接口与兼容约束
```

只有出现多个合理公共契约时才暂停：

```text
Gate: 需要确定公共契约
证据：旧客户端把缺省 org_id 解释为“全部组织”；服务端无法唯一推导。
建议：新增可选 org_id，缺省保持旧语义。
备选：强制 org_id（破坏兼容）。
```

## 3. 小改动

```text
用户：/cs 修正帮助信息里的错误参数名
系统：→ issue · micro · 已定位并修正，正在运行 CLI 快照测试
```

不会创建独立 design/review/QA/accept 文件。

## 4. 继续工作

```text
用户：/cs 继续刚才的导出过滤
系统：→ resume feature · verify · 复用同一 live session 中未变化上下文，继续验收
```

不会扫描全部 model、knowledge、archive、observations 或 Meta 历史。

## 5. 正常运行轨迹

任务期间旁路写入：

```text
.codestable/observations/pending/run-.../
  meta.json
  events.jsonl
  outcome.json
```

可能包含：

```json
{"type":"stage_started","payload":{"stage":"verify"}}
{"type":"gate_evaluated","payload":{"gate":"security_boundary","result":"passed","reason_code":"no_privilege_change"}}
{"type":"token_usage","payload":{"input_tokens":18000,"output_tokens":4200}}
```

不包含原始 Prompt、完整回复、代码或 Diff。

## 6. 生产反馈分诊

```text
用户：刚才不应该路由成 feature，把这次记录成 CodeStable 问题
系统：已 flag 当前 run；不启动 Meta。
```

之后显式：

```text
/cs feedback triage <run-id>
```

可能得到：

```text
classification: harness_policy
signal: routing.user_corrected
policy: entry.routing-and-continuation
runtime_profile: codex/<model>/<adapter>
```

如果根因是项目术语缺失，则分类为 `project_knowledge`，不修改 Harness。

## 7. 反馈固化为 fixture

Agent 根据真实事件写一个脱敏 fixture：

```text
/cs feedback fixture <feedback-id> routing-performance-regression.json
```

策略审计只有在 routing/e2e 必需层都被覆盖后，才允许该策略进入候选。

## 8. 攒信号但不自动优化

```text
/cs meta trigger-scan
```

输出：

```text
routing.user_corrected × 3
policy: entry.routing-and-continuation
profile: codex/<model>/<adapter>
action: eligible_to_open_campaign
```

它只是预览。即使执行：

```text
/cs meta trigger-scan --apply
```

也只创建 campaign，不会写提案、运行 Evaluator 或晋升。

## 9. Agent 提案

维护者显式诊断后，Agent 先编写 hypothesis 并提交到 Git，再生成：

```text
variant-routing-1.md
proposal-routing-1.json
overlay/.codestable/reference/routing.md
```

提案声明 `target_metric`、policy、`change_type`、fixture、预期效果和风险。脚本只负责验证和锁定，不能自动修改 Prompt。

## 10. 效度预检拦截坏评测

若 fixture 缺 subject-matter 文档：

```text
validity: underpowered
reason: context incomplete
```

若随机任务只跑一次：

```text
validity: underpowered
reason: stochastic fixture requires k>=5
```

此时不能创建可信评测 challenge，更不能把低分归因于 Harness。

## 11. 多 Runtime Profile

三个来自 Claude Code 的路由信号不会与两个来自 Cursor 的信号自动合并。每个 campaign 锁定 Adapter/Model Profile 与 baseline Harness identity。

一个候选在 Codex Runtime Profile 上通过，只能形成该 Profile 的 measured 证据；在其他宿主上没有 Adapter 数据时仍为 underpowered。

## 12. 策略级检查点

Prompt 摘要文案调整通过全部 measured 质量门槛后可以使用：

```text
approval_kind: agent
```

路由逻辑或 Gate 阈值调整必须使用：

```text
approval_kind: owner
```

Agent 不能在提案中把路由变更声明为低风险来绕过 owner。

## 13. 回滚

```text
/cs meta rollback h-0003
```

这是交互简写；确定性 CLI 还要求 `--approved-by` 和 `--reason`。回滚会恢复校验过的不可变快照，记录操作者与原因，不自动启动新的优化 campaign。

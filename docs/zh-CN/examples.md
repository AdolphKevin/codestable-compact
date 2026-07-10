# 使用示例

以下示例展示用户可见交互契约。路由摘要后不会等待“确认路由”。

## 1. 性能缺陷

```text
用户：/cs 提交暂存操作很慢，帮我排查并修复

系统：→ issue · standard · 新建 slow-stage 并开始复现
```

随后在同一轮：

1. 找到提交暂存入口、计时点和相关测试；
2. 建立可复现基线；
3. 定位根因；
4. 实施最小修复；
5. 比较修复前后数据并跑回归测试；
6. 更新 work，必要时提升一条可复用诊断知识；
7. 归档。

不会先输出“建议使用 cs-issue，请确认”。

## 2. 新能力

```text
用户：/cs 给导出接口增加按组织过滤，并保持旧客户端兼容

系统：→ feature · high-risk · 开始检查现有接口与兼容约束
```

如果代码与现有 contract 已经唯一决定兼容方式，流程自动设计和实现。只有出现两个都合理、但会形成不同公共契约的选择时才暂停：

```text
Gate: 需要确定公共契约
证据：旧客户端把缺省 org_id 解释为“全部组织”；服务端无法从 token 唯一推导组织。
建议：新增可选 org_id，缺省保持旧语义。
备选：强制 org_id（破坏兼容）。
需要你的决定：是否接受建议契约？
```

## 3. 小改动

```text
用户：/cs 修正帮助信息里的一个错误参数名
系统：→ issue · micro · 已定位并修正，正在运行文档/CLI 快照测试
```

不会创建单独 design、review、QA、accept 文件。`work.md` 只记录问题、修改和验证。

## 4. 行为保持重构

```text
用户：/cs 把订单模块里重复的状态判断收敛掉，不改变行为
系统：→ refactor · standard · 先建立现有行为特征测试
```

流程会优先寻找已有 helper 和删除重复分支，而不是先创建新的框架层。

## 5. 大范围需求

```text
用户：/cs 做一套多租户权限系统
系统：→ roadmap · high-risk · 开始盘点身份、租户边界与现有授权路径
```

Roadmap 完成可执行切分后，如果第一项没有战略 Gate 且用户明确要求“做”，入口可以直接创建并启动第一个 feature；不会在“roadmap 已生成，下一步请调用 cs-feat”处停下。

## 6. 继续工作

```text
用户：/cs 继续刚才的导出过滤
系统：→ resume feature · verify · 复用未变化上下文，继续验收
```

它只读取 `state.json`、verify 所需的 `work.md` 小节和自上次收据后发生变化的文件，不重新扫描所有 model、knowledge 和 archive。

## 7. 路由调试

```text
用户：/cs route 把缓存层重写一下，最近有很多超时
```

此命令只分析，不执行，并可输出：

```text
Route: issue
Lane: standard (may escalate)
Reason: “最近有很多超时”是可观察故障；重写缓存只是用户提出的解法，不应在确认根因前按 refactor 执行。
Potential transition: issue → refactor, only if evidence shows structural cause.
```

## 8. 正常运行只留下 Observation

同一轮完成 issue 后，系统旁路写入：

```text
.codestable/observations/pending/run-.../
  meta.json
  events.jsonl
  outcome.json
```

用户交互仍然只看到任务结果。系统不会继续说“我发现一个可优化点，正在修改 Harness”，也不会加载旧 observations。

当本次出现明确问题信号时：

```text
用户：刚才不应该路由成 feature，把这次记录为 CodeStable 路由问题
系统：已将当前 run 标记为 routing.user_corrected；当前任务继续，不启动 Harness 进化。
```

记录移动到 `flagged/`，仅供以后显式选择。

## 9. 显式检查，但不自动提案

```text
用户：/cs evolve inspect flagged
```

系统只显示压缩摘要，例如：

```text
3 个 flagged observations
- routing.user_corrected × 2
- tool.repeat_failure × 1
```

它不会因为数量达到 2 或 3 就自动修改规则。

## 10. 显式 Evolution Case

```text
用户：/cs evolve select 最近两次 routing.user_corrected，排查是否需要改路由规则
系统：已选择 run-101、run-118，创建 case-routing-correction；开始诊断。
```

如果证据显示是项目术语缺失：

```text
Diagnosis: project_knowledge
Action: 补充 domain/knowledge；关闭 case，不修改 Harness。
```

如果证据支持 Harness 问题：

```text
Diagnosis: harness
Mechanism: routing.solution_wording_overrides_observable_event
Surface: routing-policy
```

系统才创建隔离候选，并要求宿主运行可信对照评测。

## 11. 可信评测与提升 Gate

Evaluator 在外部环境完成 baseline/candidate 对照并签名聚合结果。导入、决定通过后：

```text
Gate: 是否提升 Harness candidate-routing-2？
证据：held-in 6/10 → 9/10；held-out 18/20 → 18/20；safety 12/12 → 12/12。
成本：median tokens +2.1%，在允许范围内。
建议：提升；可回滚到 h-0003。
备选：拒绝并保留当前版本，或评测另一个候选。
```

只有用户明确批准后才修改 active Harness。

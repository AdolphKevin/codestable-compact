# 可观测 Harness 与 Meta 自迭代设计

## 1. 定位

CodeStable 0.4 不是“每次任务结束都自我修改”的系统，而是：

> **始终可观测，生产反馈可固化，策略按 fixture 覆盖，只有显式离线 campaign 才进化。**

它将两个循环隔离：

```text
内循环：软件生命周期
  意图/证据/设计/实现/验证/验收

外循环：Harness Meta 维护
  观察/分诊/fixture/提案/效度检查/评测/接受/回滚
```

外循环不能侵入普通任务上下文或增加正常用户确认。

## 2. 为什么 Meta 不是新引擎

0.3 已有：

- 被动 observation；
- 可编辑与受保护的 surface；
- 候选 overlay；
- baseline/candidate challenge；
- 签名聚合结果导入；
- 不可变 Harness 版本和回滚。

0.4 补齐的是连接协议：

- 统一轨迹 schema；
- 生产 feedback 分类；
- feedback 转为 fixture；
- 一等策略注册表；
- 信号聚合；
- 已提交的 hypothesis；
- Agent 提案契约；
- 效度预检；
- measured 质量门槛；
- 策略级审批权限；
- 策略与证据双向索引。

因此 Meta 是现有确定性部件之间的受控闭环，而不是另一个自治 Agent 框架。

## 3. 观察不等于进化

普通运行只：

```text
执行软件任务
追加紧凑事件
以任务 verifier 结果结束
```

明确不：

```text
读取旧运行记录
聚类失败
分类根因
编写 variant
运行基准
修改当前 Harness
```

这确保 Observation 不增加额外的 Agent 回合；实际延迟和 token 成本仍需由对应 Host Adapter 测量。

## 4. 知识库与 Harness 策略的边界

`.codestable/knowledge` 描述项目可复用经验；Harness policy 描述 CodeStable 如何执行工作。

| 发现 | 去向 |
|---|---|
| 项目 API、约束或坑点 | model/knowledge |
| CodeStable 路由、Gate、恢复或上下文规则缺陷 | Harness policy campaign |
| 某模型或宿主的变通方案 | 绑定 Runtime Profile 的策略证据 |
| 产品代码缺陷 | 软件生命周期 |
| fixture/scorer 缺陷 | 评测维护 |

错误分类会造成知识污染或 Harness 过拟合，因此诊断是提案前的强制阶段。

## 5. 一等策略

每个策略以稳定 ID 表示，映射到当前文件 surface。Registry 同时表达：

```text
策略语义
允许的变更类型
必需证据层
fixture 覆盖
检查点权限
```

这让“是否可进化”成为可审计数据，而不是 Prompt 中一句建议。

## 6. 轨迹与反馈

Observation schema 覆盖决策点而不是完整对话：

```text
阶段/Gate/检查点/干预/成本/policy/knowledge/verifier
```

Feedback item 再附加：

```text
分类
稳定信号
Runtime Profile
Harness identity
policy 映射
摘要
fixture 状态
campaign 归属
```

Meta trigger 只聚合同一 Adapter/Model Profile 和 baseline Harness identity 的兼容反馈，避免把 GPT、Claude Code、Cursor 或 Codex 的不同行为混为同一个弱点。

## 7. Agent 提案与确定性测量

提案的创造性无法由关键词脚本可靠替代。0.4 保留 Agent 负责创意，但限制其自由度：

```text
单一机制
白名单内的 policy
允许的变更类型
fixture 集
受限的文件、variant 与预算
已提交的 hypothesis
明确风险
```

脚本不生成策略文案，只验证提案、锁定候选、执行 fixture、导入评测和应用比较规则。这样既保留模型的设计能力，也避免脚本为了 scorer 关键词自动修改 Prompt。

## 8. Goodhart 防线

Meta 系统最大的风险不是候选失败，而是 Evaluator 奖励错误行为。效度预检将以下内容提升为晋升前硬门槛：

```text
上下文是否完整
oracle 是否允许多个正确表达
scorer 是否用正反例校准
随机样本是否足量
judge 是否隔离
hypothesis 是否预先冻结
```

一个让分数上涨但未通过效度检查的候选，状态只能是 underpowered 或 blocked。

## 9. 多模型、多宿主现实

Harness 效果不具有天然可移植性。评测证据必须绑定：

```text
项目
Harness baseline/candidate
宿主
模型
Adapter/工具集
预算/上下文行为
fixture 套件
```

0.4 的便携包负责 schema、锁、策略和结果导入；具体 Host Adapter 负责真实调用 GPT、Claude、Cursor 或 Codex。缺少 Adapter 时，宿主 fixture 被标记为 underpowered。

合理的证据适用范围梯度：

```text
当前项目 + 精确 Runtime Profile
→ 同一 Profile 跨项目
→ Core 覆盖受支持的 Profile 矩阵
```

## 10. 接受与回滚

接受不是一个总分，而是连续 Gate：

```text
policy 已覆盖
→ 效度达到 measured
→ 目标得到改善
→ held-out/safety 不回归
→ 包与回归检查达到 measured
→ 权限正确
→ 版本不可变
```

低风险文案或 Playbook 可以由 Agent 在完整 measured 证据后接受；路由、检索策略、工作流策略、Gate 阈值、schema 和运行时必须由 owner 批准。

回滚是版本操作，不是另一次提案。回滚后普通 run 继续记录 observation；只有显式选择新的证据才开启下一轮。

## 11. 真实效果验证边界

本项目自带测试能够真实证明：

- 普通 `/cs` 不会导入 Meta 控制面；
- 策略缺 fixture 时无法进化；
- 脚本不能写提案；
- 效度缺陷和低样本会阻止评测；
- 受保护路径和未声明 surface 无法夹带；
- 签名结果篡改、重放和原始轨迹会被拒绝；
- 权限不能由提案者降级；
- 晋升和回滚有不可变快照与证据链。

它不能在没有外部运行环境时证明：

- GPT 5.6 一定比 GPT 5.5 更适合某策略；
- Claude Code、Cursor、Codex 的结果一致；
- 某个 Prompt 改动在真实项目中一定提升交付质量。

这些结论必须通过对应 Runtime Profile 的真实 Adapter campaign 获得。0.4 的价值，是让这类结果可以被正确采集、校验、归因、接受和回滚，而不是凭单次主观体验修改 Skill。

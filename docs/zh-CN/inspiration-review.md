# 灵感来源审查

本文记录哪些思想被保留、调整或有意舍弃。它是设计轨迹，不代表复用了来源项目代码。

## CodeStable

仓库：https://github.com/liuzhengdongfortest/CodeStable

### 保留

- 软件生命周期实体是中心：requirement、decision、roadmap、feature、issue、refactor、knowledge。
- 持久状态位于可读的项目本地 `.codestable/` 目录。
- 人类工程责任保持显式。
- Requirement、contract 和架构决策可以跨越单次实现长期存在。
- Feature/issue/refactor 路径保留设计、审查和验证纪律。

### 调整

- 根入口默认完成路由并**继续执行**，不在推荐处停止。
- 内部阶段不再是独立的用户可见 Skill。
- 文件存在性不再是主要进度判断方式；以 `state.json.stage` 为准。
- 用显式链接和会话级 receipt 代替启动时完整扫描 `.codestable/`。
- 历史 feature 目录是 archive 证据，不是默认设计输入。
- 通过的 review/QA 阶段不再各自产生报告文件。

### 原因

即使生命周期阶段从命令面隐藏，生命周期本身仍有价值。合并命令边界可以消除用户协调成本，同时保留工程检查。

## Trellis

仓库：https://github.com/mindfold-ai/Trellis

### 保留或调整

- 以任务为中心的状态和仓库内工作工件。
- 根据任务状态和工件恢复，而不是要求用户记住下一条命令。
- 紧凑索引只充当指针，仅加载适用细节。
- 使用阶段特定说明，不始终加载一份庞大流程。
- 将验证作为显式生命周期阶段。
- 把已完成任务中的持久发现提升到当前项目标准或知识。

### 调整

- CodeStable Compact 使用跨 kind 的统一工作信封（`state.json`、`work.md`、`context.json`），而不是更广泛的 workspace/journal 拓扑。
- 上下文复用显式限制在一个实时对话 key 内；冷会话不会把旧 receipt 当成记忆。
- 持久目标分为当前 model 和复用 knowledge，过程历史不进入正常检索。

### 原因

任务状态和选择性加载以更小的用户可见表面解决了大型 Skill 树相同的启动问题。实时会话限制避免一种不安全优化：字节未变化不代表新模型会话记得其含义。

## ponytail

仓库：https://github.com/DietrichGebert/ponytail

### 保留或调整

- 修改前检查真实流程。
- 优先复用现有行为和模式，其次使用标准库/平台能力、已安装依赖，最后才写最少新代码。
- 修复根因而不是症状。
- 不为假想未来需求增加抽象、依赖或兼容层。
- 删除和合并能解决问题时优先采用。
- 规范 Skill 保持可移植，宿主特定 adapter 放在别处。

### 调整

- 最小化作为横切工程约束嵌入每个生命周期，而不是独立的常驻人格。
- Review 不只报告复杂度；每个生命周期会修复阻塞问题并自动重跑验证。

### 原因

最小化参与设计、实现和审查退出条件时最有效。它应约束生命周期，而不是作为用户必须记住的另一条命令与生命周期竞争。

## 原创整合

组合架构不是所有机制的并集，而是有意选择：

```text
软件生命周期模型（CodeStable）
+ 可恢复任务状态和选择性加载（Trellis）
+ 最小机制约束（ponytail）
− 每阶段一条命令
− 全局历史扫描
− 每个 Gate 强制报告
− Agent 编排机制
```

结果是一个日常入口、五种事件生命周期、三个 active-work 文件和一个显式启用的历史 archive。

## Self-Harness、AHE 与 ACE

论文：

- Self-Harness：https://arxiv.org/abs/2606.09498
- Agentic Harness Engineering：https://arxiv.org/abs/2604.25850
- Agentic Context Engineering：https://arxiv.org/abs/2510.04618

### 保留或调整

- Harness 修改是显式对象，包含预期行为变化和精确文件级 surface。
- Baseline/candidate 在锁定的 model、adapter、evaluator、budget 和任务 split 下比较。
- Held-in 证据针对已观察弱点，仅 evaluator 可见的 held-out 和 safety 保护通用行为。
- 上下文经验使用增量结构化 playbook delta，而不是重写完整 prompt。
- 版本谱系、评测证据和回滚使改进可证伪、可逆。

### 调整

- 正常软件交付不持续运行优化器，只写一份不增加模型调用、不读取历史的被动临时 observation。
- 失败阈值、调度器和 run 次数都不会创建提案；maintainer 必须显式选择已完成 observations 并先诊断。
- 项目知识、产品缺陷、模型方差和环境失败与真正 Harness 机制分开。
- 评测结果必须经过外部签名聚合边界；不信任 candidate/worker 自报结果。
- 每次 Harness 提升都需要人工 Gate，包括低风险 routing 或 playbook 修改。
- Evaluator、签名密钥、私有 held-out、Gate policy、manifest、evidence 和提升机制都受保护。

### 原因

CodeStable 面向真实仓库，首要任务是软件交付。持续优化会增加主流程延迟和漂移。因此采用“始终可观察、按需才进化”：低成本收集有界证据，只在显式选中真实维护需求后运行受控的 Self-Harness 外环。

## Darwin Gödel Machine

论文：https://arxiv.org/abs/2505.22954

### 延后采用的思想

- 多个 parent Harness version；
- 保存可行变体的 population archive；
- 平衡性能与未充分探索谱系的 parent selection；
- 显式 novelty/diversity 压力；
- 未来可能有用的 stepping-stone 变体。

### 延后原因

开放式种群搜索需要显著更多评测成本，也会增加攻击面、谱系复杂度和针对基准工件过拟合的风险。CodeStable 先采用带并行最小 candidate 和保守非回归 Gate 的单一 active lineage；只有真实证据表明 hill climbing 已停滞，且宿主具备强隔离与 evaluator 能力时，才应增加 population search。

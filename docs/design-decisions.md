# 设计决策

## D-001 — `/cs` 默认自动运行

**状态：** 已接受

**背景：** 如果根入口只负责路由，即使不需要做任何工程决策，用户也必须等待内部分类结果并再次确认。

**决策：** `entry.mode` 默认为 `auto`。选择路由后，在同一次调用中立即执行对应生命周期。`/cs route` 和 `entry.mode=route` 保留诊断及向后兼容行为。

**影响：** 根技能必须能够初始化、恢复和激活同级生命周期；在自动模式下，路由说明不能成为退出条件。

## D-002 — 每种事件生命周期只有一个用户可见技能

**状态：** 已接受

**背景：** 设计、实现、审查、QA 和验收是 feature 交付的阶段，通常不是彼此独立的用户意图。

**决策：** 每类主要软件事件只保留一个技能：feature、issue、refactor、roadmap 和 model。内部阶段参考资料可以继续模块化，并按需加载。

**影响：** 审查纪律以自动循环的方式保留。独立阶段技能只能作为可选的 host alias 存在，不能持有工作流逻辑。

## D-003 — 使用显式状态，而不是根据制品推断

**状态：** 已接受

**背景：** 通过 Glob 扫描设计、清单和审查文件来推断进度，需要反复扫描；文件不完整或过期时还会产生歧义。

**决策：** `state.json.stage/status` 是权威状态。Git/code/test 证据可以触发状态对账，但文件是否存在不能定义状态机。

**影响：** 恢复工作只需读取一份小型状态文件，也不再需要扫描整个目录来判断续作位置。

## D-004 — 活动工作项只要求三个文件

**状态：** 已接受

**背景：** 每个阶段单独建立文档会重复背景信息，并增加同步工作。

**决策：** 只要求 `state.json`、`work.md` 和 `context.json`。通过的临时检查无需单独生成报告。

**影响：** 重要证据和决策集中在一份聚合记录中，流程开销随 lane 风险而变化，而不是随阶段数量增长。

## D-005 — 收据限定于实时会话

**状态：** 已接受

**背景：** 文件哈希可以证明字节未变化，却不能证明新的模型会话仍记得之前读取的语义。

**决策：** 每个计划和收据都使用仅在当前实时会话中稳定的键。冷会话会创建新键并重新读取必要材料。持久化的 `work.md` 保存恢复工作所需的紧凑结论。

**影响：** 长时间工作会话可以安全节省 token；冷启动的正确性不会建立在无效的记忆假设上。

## D-006 — 归档检索按需启用

**状态：** 已接受

**背景：** 历史 feature 设计会积累过时假设，并在有噪声的检索中占据主导。

**决策：** 正常搜索只覆盖当前 model 和已整理的 knowledge。活动工作按精确 ID/scope 恢复。检索 archive 必须提供显式范围和理由。

**影响：** 工作完成后必须先将当前事实和可复用知识晋升，再执行归档；否则这些事实不会出现在未来的正常检索中。

## D-007 — Gate 表示权限或风险，而不是阶段完成

**状态：** 已接受

**背景：** 强制在设计审查、代码审查和 QA 后暂停，会让每次阶段转换都变成一次用户协调事件。

**决策：** 技术审查和验证自动运行，失败后自动循环。人类 Gate 仅限于不可逆操作、公共契约选择、安全或数据策略、实质性运维风险、未解决的已接受决策冲突，或缺少验收权限。

**影响：** 更多工作可以无人值守地推进，真正需要人类负责的节点仍保持显式，并以证据为基础。

## D-008 — 首版 runtime 不引入语义数据库

**状态：** 已接受

**背景：** 向量数据库或守护进程可以改善模糊历史检索，但会增加依赖、同步工作和另一个状态权威来源。

**决策：** 使用显式链接、紧凑索引、确定性文本搜索，并按需启用 archive。Agent 负责语义判断；runtime 负责机械过滤。

**影响：** runtime 保持可检查且仅依赖标准库。只有真实项目规模的证据才能证明需要增加检索机制，不能仅凭预想添加。

## D-009 — Goal 是执行策略，而不是独立的生命周期实体

**状态：** 已接受

**背景：** 有边界的结果和自动实现/验证循环可以应用于 feature、issue、refactor 或 roadmap 条目；单独的 goal 技能会重复这些事件语义。

**决策：** 所有生命周期统一使用 `execution.mode=continuous_until_gate`。按常规方式路由可观察到的软件事件；当有边界的结果跨越多个可独立验收的工作项时，使用 roadmap。

**影响：** “描述结果后离开”成为默认交互，同时制品仍按其代表的软件事件分类。

## D-010 — 正常工作可观察，但不会自我修改

**状态：** 已接受

**背景：** 每次软件任务后都执行弱点挖掘、提案和回归评测，会给主要工作流增加延迟、token 成本和 Harness 漂移。

**决策：** 每次正常 Skill 调用可以尽力写入一条临时 observation，但正常运行不得诊断、提案、评测、晋升或检索 observation 历史。

**影响：** 真正出现 Harness 问题时仍有证据可用，而正常交付保留原有执行路径和成本特征。

## D-011 — Observation 是临时飞行记录数据

**状态：** 已接受

**决策：** 在 pending/flagged/selected 状态下保存紧凑的 `meta.json`、`events.jsonl` 和 `outcome.json`。禁止记录原始 Prompt、模型回复、源码内容、Diff、secret、私有 held-out 和任务级 Evaluator 轨迹，并限制记录大小和保留期限。

**影响：** Observation 历史不会成为另一个一等 feature archive，也不会成为包含大量隐私的会话语料库。

## D-012 — Signal 聚合可以打开 campaign，但不能执行优化

**状态：** 已接受

**决策：** 默认配置下，单次 run 不会创建 campaign。只有 signal、policy、Adapter/Model Profile 和 baseline Harness identity 均匹配时，`trigger-scan` 才能聚合已分类的反馈。它以预览为先；显式执行 `--apply` 可以在达到配置的支持阈值后打开有边界的 campaign，但不得诊断、提案、评测、接受或晋升。

**影响：** 重复出现的生产证据可以进入队列，而无需追逐单次失败；自动化仍不具备修改策略的权限。

## D-013 — 先诊断，再提案

**状态：** 已接受

**决策：** 将每个选定 case 分类为 Harness、项目知识、产品代码、模型差异、环境或证据不足。只有映射到已声明可编辑 surface 的 Harness 分类才能创建 candidate。

**影响：** Harness 进化不能代替软件修复或项目事实整理。

## D-014 — Evaluator 和晋升控制平面受保护

**状态：** 已接受

**决策：** 私有 held-out 任务、Evaluator 逻辑、签名密钥、数据集划分、评测与晋升控制规则、observation、证据、manifest、registry 以及 evolution/evaluator 工具均不属于 candidate 可编辑 surface。交付 Gate 策略是声明过的可编辑 surface，但 `gate_threshold` 变更必须由 owner 批准。

**影响：** Candidate 无法重新定义成功、伪造自身证据、扩大自己的白名单或抹除来源链。

## D-015 — Harness 编辑限制为有边界的 overlay

**状态：** 已接受

**决策：** `harness/manifest.json` 声明确切的可编辑文件和风险类别。Candidate overlay 必须只包含这些已声明文件，并冻结 base/candidate SHA-256 哈希。

**影响：** Candidate 生成过程可检查、可并行、可逆；宽泛的自我重写和夹带文件会被拒绝。

## D-016 — 评测结果是经外部认证的聚合数据

**状态：** 已接受

**决策：** Challenge 以不可变方式锁定 baseline 版本/内容、candidate 内容/定义、protocol、model profile、adapter、Evaluator、budget、数据集划分、重复次数和 nonce。项目只接受使用 Evaluator 专用 HMAC 密钥签名的聚合结果；不提供直接写入未签名结果的 `eval-record`。

**影响：** 控制平面可以拒绝篡改、重放和锁定内容不匹配。要建立真实信任，host 仍必须将密钥和私有 held-out 隔离在 candidate/worker 环境之外。

## D-017 — 晋升权限由策略限定，并受证据 Gate 约束

**状态：** 已接受

**决策：** 只有效度预检通过后，才能在 held-in、私有 held-out 和 safety 数据集上比较 baseline 与 candidate。必须满足目标改善、不回归、必需的 measured 质量门槛，并保证证据不可变。批准权限来自一等 policy registry：低风险 Prompt 文案或经过评测的 playbook 变更可以允许 Agent 批准；workflow routing、retrieval strategy、workflow policy、Gate threshold、artifact schema 和 runtime tool 变更需要 owner 批准。

**影响：** 提案者不能降低自己的 checkpoint。高影响行为仍由 owner 控制，同时无需让每个已有 measured 证据的纯文案变更都等待人工点击。

## D-018 — 可进化记忆使用经过评测的增量变更

**状态：** 已接受

**决策：** 将 Harness 经验保存为结构化 JSONL playbook 条目。逐项新增、修订、合并或停用；绝不在每个任务后重写全部记忆。Playbook 增量是普通 candidate，必须经过可信评测和晋升 Gate。

**影响：** 跨任务执行知识可以持续改善，而不会造成上下文坍缩或未经验证的记忆污染。

## D-019 — 版本谱系不可变，回滚显式执行

**状态：** 已接受

**决策：** 在晋升前后为所有已声明 surface 创建快照。记录 parent、case、candidate、evaluation hash、actor 和 reason。Rollback 恢复指定且经过校验的快照，绝不自动启动替代 proposal。

**影响：** 每项 Harness 变更都可审计、可逆，同时不会把 rollback 变成另一轮自治循环。

## D-020 — 开放式种群前先维护单一谱系

**状态：** 已接受

**决策：** 从保守、显式启动的单一谱系改进开始。种群档案、新颖性和自动 parent 选择延后实现，直到基准证据和隔离预算证明其必要性。

**影响：** 设计保持易懂且安全，同时为未来扩展到更广泛的进化搜索保留路径。

## D-021 — 无 fixture 覆盖，不允许进化

**状态：** 已接受

**决策：** 只有一等 registry 条目将 Harness policy 映射到已声明 surface、允许的变更类型、确切的活动 fixture、全部必需 fixture 层和批准规则时，该策略才可进化。

**影响：** 缺少行为回归覆盖的可编辑文件不能接收 candidate；必须先补齐测量基础设施，再修改策略。

## D-022 — 评测效度先于 Harness 归因

**状态：** 已接受

**决策：** 负向结论或声称提升必须具备完整的 fixture 上下文、宽容的 oracle、经过校准的 scorer、随机任务 `k>=5`、Judge/profile 隔离，以及已提交的 hypothesis 来源。Candidate 内容锁由 challenge、结果导入和晋升阶段另行校验。证据标记为 measured、soft 或 underpowered。

**影响：** Candidate 优化不能利用 onboarding 不完整、脆弱的关键词计分或采样噪声，并将结果称为改善。

## D-023 — Agent 编写 variant；脚本负责测量和强制约束

**状态：** 已接受

**决策：** Agent 编写 hypothesis、variant 文档、proposal 和最小 overlay。确定性工具可以校验、锁定、运行 fixture、导入签名结果、比较和记录，但不能生成 Prompt 或 policy 文案。

**影响：** 创意搜索仍由模型驱动，证据边界则保持可复现，并能抵抗对 scorer 关键词的过拟合。

## D-024 — Runtime Profile 是证据身份的一部分

**状态：** 已接受

**决策：** Observation 与反馈记录 `model_profile` 和 `adapter`；campaign 还绑定 baseline Harness identity，evaluation challenge 另行锁定预算等评测身份。不兼容的已记录身份不会被静默合并。

**影响：** 证据可以支持项目/profile 范围的晋升，但不能据此声称同一结果可迁移到 GPT、Claude Code、Cursor、Codex 或未来的 host。

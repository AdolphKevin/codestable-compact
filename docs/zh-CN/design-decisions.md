# 设计决策

## D-001 — `/cs` 默认自动执行

**状态：** 已接受

**背景：** 仅路由的根入口会迫使用户等待内部分类并再次确认，即使并不存在工程决策。

**决策：** `entry.mode` 默认为 `auto`，路由后在同一次调用中立即执行生命周期。`/cs route` 和 `entry.mode=route` 保留诊断与向后兼容行为。

**后果：** 根 Skill 必须能初始化、恢复并激活同级生命周期；auto 模式下路由说明不能成为退出条件。

## D-002 — 每种事件生命周期只有一个用户可见 Skill

**状态：** 已接受

**背景：** 设计、实现、审查、QA 和验收通常是 Feature 交付阶段，而不是独立用户意图。

**决策：** 为 feature、issue、refactor、roadmap、model 各保留一个 Skill，内部阶段参考可保持模块化并按需加载。

**后果：** 审查纪律以自动循环保留；独立阶段 Skill 只能作为可选宿主 alias，不能拥有工作流逻辑。

## D-003 — 使用显式状态，不从工件推断

**状态：** 已接受

**背景：** 通过 Glob 设计、清单和审查文件推断进度需要反复扫描，文件不完整或过期时还会产生歧义。

**决策：** `state.json.stage/status` 是权威来源。Git、代码和测试证据可触发对齐，但文件存在性不定义状态机。

**后果：** 恢复只需读取一个小状态文件，无需遍历目录判断续作位置。

## D-004 — Active work 只要求三个文件

**状态：** 已接受

**背景：** 每阶段一个文档会重复背景并产生同步成本。

**决策：** 只要求 `state.json`、`work.md`、`context.json`，通过的临时检查无需单独报告。

**后果：** 重要证据和决策集中可审计；过程复杂度随 lane 风险而非阶段数量变化。

## D-005 — 回执仅限实时会话

**状态：** 已接受

**背景：** 文件 hash 只能证明字节未变化，不能证明新模型会话记得之前读取的语义。

**决策：** 每个 plan/receipt 使用只在当前实时对话中稳定的 key。冷会话创建新 key 并重读必要材料；持久 `work.md` 保存恢复所需的压缩结论。

**后果：** 长会话可安全节省 token，不以错误的记忆假设牺牲冷启动正确性。

## D-006 — Archive 检索必须显式启用

**状态：** 已接受

**背景：** 历史 Feature 设计积累过时假设，容易主导有噪声的检索。

**决策：** 正常搜索只覆盖当前 model 和精选 knowledge；active work 按精确 id/scope 恢复；archive 必须给出显式范围和原因。

**后果：** 完成任务必须在归档前提升当前真相和复用知识，否则未来正常检索不会看到它们。

## D-007 — Gate 表示权限或风险，不表示阶段完成

**状态：** 已接受

**背景：** 强制在设计审查、代码审查和 QA 暂停，会让每次阶段转换都需要用户协调。

**决策：** 技术审查和验证自动执行，失败自动循环。人工 Gate 仅限不可逆操作、公共契约选择、安全/数据策略、重大运维风险、无法解决的既有决策冲突或缺少验收权限。

**后果：** 更多工作可无人干预地继续，真正需要人类负责的节点仍保持显式且有证据。

## D-008 — 初始运行时不使用语义数据库

**状态：** 已接受

**背景：** 向量数据库或 daemon 可能改善模糊历史搜索，但会增加依赖、同步和另一套状态权威。

**决策：** 使用显式链接、小型索引、确定性文本搜索和显式 archive。Agent 负责语义判断，运行时负责机械过滤。

**后果：** 运行时保持可检查且只依赖标准库；只有真实项目规模证据才能证明需要更多检索机制。

## D-009 — Goal 是执行策略，不是独立生命周期实体

**状态：** 已接受

**背景：** 有界结果和自治实现/验证循环可用于 feature、issue、refactor 或 roadmap item；单独 goal Skill 会重复这些事件语义。

**决策：** 所有生命周期使用 `execution.mode=continuous_until_gate`。按可观察事件正常路由；结果跨多个可独立验收事项时使用 roadmap。

**后果：** “描述结果后离开”成为默认交互，工件仍按其代表的软件事件分类。

## D-010 — 正常工作可观察但不自修改

**状态：** 已接受

**背景：** 每个软件任务后都运行弱点挖掘、提案和回归评测，会给主流程增加延迟、token 成本和 Harness 漂移。

**决策：** 每次正常 Skill 调用最多尽力写一份临时 observation，但不得诊断、提案、评测、提升或读取 observation 历史。

**后果：** 真正出现 Harness 问题时已有证据，正常交付仍保持原执行路径和成本。

## D-011 — Observation 是临时飞行记录器数据

**状态：** 已接受

**决策：** 在 pending/flagged/selected 下保存紧凑的 `meta.json`、`events.jsonl`、`outcome.json`。禁止原始 prompt、模型回复、源码、diff、secret、私有 held-out 和逐任务 evaluator trace，并限制大小和保留期。

**后果：** Observation 历史不会成为另一套一等 Feature archive 或隐私负担沉重的对话语料库。

## D-012 — Evolution 需要显式选择证据

**状态：** 已接受

**决策：** 任务数、失败阈值或调度器都不能创建 evolution case。Maintainer 显式选择命名的已完成 observations 或已有 signal；case 冻结一个 baseline Harness version，只包含压缩证据。

**后果：** 单次噪声不能暗中变成持久规则，也不会扫描无关历史。

## D-013 — 先诊断，再提出候选

**状态：** 已接受

**决策：** 将选中 case 分类为 Harness、项目知识、产品代码、模型方差、环境或证据不足。只有映射到声明可修改 surface 的 Harness 分类才能创建 candidate。

**后果：** Harness evolution 不能替代软件修复或项目真相整理。

## D-014 — Evaluator 与提升控制面受保护

**状态：** 已接受

**决策：** 私有 held-out、evaluator 逻辑、签名密钥、split 分配、Gate policy、提升规则、observations、evidence、manifest、registry 和 evolution/evaluator 工具都不在 candidate 修改面内。

**后果：** Candidate 不能重定义成功、伪造证据、扩大白名单或删除谱系。

## D-015 — Harness 修改是有界 Overlay

**状态：** 已接受

**决策：** `harness/manifest.json` 声明精确可修改文件和风险等级；candidate overlay 必须只包含声明文件，并冻结 base/candidate SHA-256。

**后果：** Candidate 生成可检查、可并行、可回滚；广泛自重写和文件夹带会被拒绝。

## D-016 — 评测结果是外部认证的聚合数据

**状态：** 已接受

**决策：** Challenge 不可变地锁定 baseline version/content、candidate content/definition、protocol、model profile、adapter、evaluator、budget、splits、repeats 和 nonce。项目只接受 evaluator-only HMAC key 签名的聚合结果，不提供无签名 `eval-record`。

**后果：** 控制面可拒绝篡改、重放和锁定不匹配；真正信任仍要求宿主将密钥和私有 held-out 隔离在 candidate/worker 环境之外。

## D-017 — 提升不得回归且始终需要人工批准

**状态：** 已接受

**决策：** 使用重复运行比较 baseline/candidate 的 held-in、私有 held-out 和 safety；要求可测改善、不允许回归、配置的 safety 全通过，且资源/交互指标受限。包括低风险在内的每个通过 candidate 都停在人工提升 Gate。

**后果：** 看似合理的文字和局部成功不能激活新 Harness；影响未来工作的修改始终由人类明确授权。

## D-018 — 进化记忆使用已评测的增量 Delta

**状态：** 已接受

**决策：** Harness 经验保存为结构化 JSONL playbook item，只增、改、合并或停用单项，不在每个任务后重写全部记忆。Playbook delta 是普通 candidate，必须经过可信评测和提升 Gate。

**后果：** 跨任务执行知识可改善，不会发生上下文坍缩或未验证记忆污染。

## D-019 — 版本谱系不可变，回滚必须显式执行

**状态：** 已接受

**决策：** 提升前后快照所有声明 surface，记录 parent、case、candidate、evaluation hash、actor、reason。回滚恢复命名的已验证快照，不自动启动替代提案。

**后果：** 每次 Harness 修改可审计、可回滚，且不会让回滚变成另一个自治循环。

## D-020 — 先做单谱系维护，再考虑开放种群

**状态：** 已接受

**决策：** 从保守、显式启动的单谱系改进开始。Population archive、novelty 和自动 parent selection 延后，直到基准证据与隔离预算证明必要。

**后果：** 设计保持易懂和安全，同时保留未来扩展到更广泛进化搜索的路径。

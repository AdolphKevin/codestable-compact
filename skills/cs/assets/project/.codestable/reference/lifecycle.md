# Lifecycle invariants

1. 软件实体与当前事实是中心，Agent 编排不是中心。
2. `/cs` 的路由必须在同一调用中继续执行；路由本身不是 Gate。
3. `state.json` 是任务阶段的权威来源，不能通过 Glob 文件猜进度。
4. 每个 active work 默认只有 `state.json`、`work.md`、`context.json`。
5. review 与 QA 是内部自动循环；默认只在真实决策风险时暂停。用户用自然语言明确要求“先给方案”“只分析原因”等阶段边界时，完成并审查该阶段、将 state 推进到下一阶段后返回；`--until <stage>` 仅作为自动化别名。这不是 Gate 或 work completion，且只影响本次调用。
6. 当前代码、测试、accepted model 优先于历史设计。
7. 完成前先 promotion，再 archive。
8. 新依赖、新抽象、新文件和兼容层都需要当前证据。
9. 正常 Skill 调用只可 best-effort 写入一份 passive observation；不得读取历史 observation 或自动进入 evolution。
10. Harness 变更只来自显式选中的 case、可信签名评测和人工 promotion Gate。

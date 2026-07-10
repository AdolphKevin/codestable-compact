# Gate policy

## Internal checks: never pause by default

- design consistency, scope and simplest mechanism;
- diff correctness, regression and unnecessary complexity;
- tests, lint, typecheck and observable acceptance;
- model/knowledge promotion correctness.

失败时回到对应阶段，修复后重跑。不要让用户手动切换 skill。

## Human Gate: pause only for authority/risk

至少命中一项：

1. 不可逆或破坏性操作；
2. 有多个合理选项的公共兼容契约；
3. 安全边界、权限策略、密钥处理；
4. 持久化数据迁移且没有已批准策略；
5. 显著成本、可用性或运维风险；
6. 与 accepted decision 冲突且证据无法自动消解；
7. 缺少权限/环境，无法观察验收；
8. 用户明确要求在此审批；
9. 经过可信评测后准备提升新的 Harness 版本。

Gate 必须包含：待决定事项、证据、推荐、备选及后果、阻塞范围。不得用“是否同意路由到某 skill”作为 Gate。


Harness promotion Gate 还必须包含：selected evidence、diagnosis、精确 surface/diff/hash、held-in/held-out/safety 对照、资源指标、批准 actor/reason 与 rollback target。不存在低风险自动晋升例外。

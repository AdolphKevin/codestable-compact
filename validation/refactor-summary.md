# CodeStable Compact 0.5 重构与效果验证摘要

日期：`2026-07-14`

## 1. 结论

本次重构已将 CodeStable Compact 的主控制轴从“当前处于哪个 lane / stage”替换为“目标、事实、风险、副作用和完成证据是否满足”。

当前定位是：

```text
Owner 自主选择实现路径
Harness 控制副作用、风险升级、证据真实性和完成权
Reviewer 只负责反证
```

生产内环使用可重复调用而非固定排序的五个动作：

```text
Inspect · Propose · Execute · Verify · Learn
```

Meta 外环继续保持显式触发、fixture 覆盖、独立评测和可回滚，不进入正常 `/cs` 上下文。

## 2. 主要实现变化

### 证据状态替代流程状态

`state.json` 现在统一承载：

- goal / acceptance / invariants / non-goals；
- facts / assumptions / risks / changes；
- proposal、side-effect boundary、blockers；
- risk level、required evidence、completion verdict。

旧 `lane` / `stage` 仅在迁移代码中读取，不再作为活动任务游标。旧版“验证已通过”的文字不会被迁移成伪造 proof。

### Harness 持有真实证据与完成权

新增追加式 `evidence.jsonl`，每条记录包含前序哈希和自身 SHA-256。`verify` 由 Harness 实际执行命令，并记录：

- command / cwd；
- exit code；
- duration；
- 有界 stdout / stderr；
- artifact 指纹；
- `PASS / FAIL / BLOCKED / PARTIAL`。

Owner 只能解释证据，不能自行声明命令已运行或证据已存在。每种必需证据现在还必须匹配规定来源：命令型证据必须来自 `command_execution` 且包含真实命令和 `exit_code=0`，状态快照和 proof 必须由 Harness 派生。`proof` 从已有 ledger 派生；`complete` 在证据缺失、开放阻塞、越界副作用或完整性失败时拒绝完成。

### 风险自适应验证

统一策略为：

| Level | 必需证据 |
|---|---|
| L0 | `diff_check`, `format_check` |
| L1 | `scope_inspect`, `targeted_test`, `lightweight_review` |
| L2 | `audit_ledger`, `proposal`, `integration_test`, `independent_review`, `proof` |
| L3 | `full_audit`, `invariant_contract`, `live_validation`, `rollback_proof`, `independent_review`, `regression_fixture` |

风险只能保持或升高。实际修改触及授权、安全、资金、删除、迁移、核心状态等可执行路径时，Harness 会动态升级验证要求。

### 副作用与 Reviewer 边界

任务必须声明可写路径或 `--no-writes`。Harness 在任务创建时保存 Git baseline，完成时比较所有 Git 可见变化；未登记或越界写入即使没有进入 change ledger 也会被拒绝。未跟踪目录会展开到实际文件后再做边界与风险判断。

L2/L3 的 `independent_review` 必须声明不同于 Owner 的 producer、`PASS` verdict 并绑定真实 artifact。本地 portable runtime 只能证明“声明的 producer 不同”，不能证明现实身份独立；密码学身份保证仍由 Host Adapter 提供。

本轮修复还将 release source hash 排除 `.git`、顶层运行时 `.codestable` 和生成的 `validation/`，因此 Git 状态、任务状态和报告重跑不会使 source-bound 测试证据自行失效。

收尾时发现并修复了 schema-v4 observation CLI 的参数冲突：`end --command` 不再覆盖 `end` 子命令分发字段，验证命令可被正常写入 passive outcome。

### Skill 与 artifact 收敛

固定阶段参考被删除或替换为按当前缺失状态读取的行动参考。隐藏的 `lifecycle.md` 已改为 `control-plane.md`。原阶段式 e2e fixture 被替换为副作用边界和证据修复 fixture。

除验证产物外，相对 0.4 基线共有：

- 13 个新增源文件；
- 12 个删除源文件；
- 56 个修改源文件；
- 70 个未变化源文件。

## 3. 已测效果

### 发布与回归

- 静态发布校验：`PASS`。
- 0.4 解压基线：`56/56` tests passed。
- 0.5 候选：`67/67` tests passed。
- 已知坏变体防线：`13/13` detected。
- 策略/fixture 审计：`9` policies、`13` fixtures、全部 evolvable policy 有所需层级覆盖。
- fresh bootstrap + doctor + policy audit：`PASS`。

候选测试通过一次完整 `unittest discover` 覆盖全部 67 项；基线与候选日志均绑定各自 release source tree 的 SHA-256。本轮新增 5 项控制平面负向单测，并补充 1 项 observation CLI 回归测试，覆盖证据、边界、归档、哈希和参数分发问题。

### 生产控制平面场景

[`control-plane-report.md`](control-plane-report.md) 实际执行了 `52` 次 Harness 操作，并通过 `22/22` 条断言：

- L0 无证据完成被拒绝；
- artifact record 不能冒充 `diff_check` / `format_check` 命令证据；
- 未登记的 Git 可见写入和越界写入均被拒绝；
- 未跟踪目录按真实文件展开，`docs/security.md` 不会因文件名误升 L3；
- 真实 command exit code 被记录；
- 精确证据满足后才可完成和归档；
- L2 中声明为 Owner 的 reviewer producer 被拒绝；
- 声明不同的 reviewer producer、artifact 与 machine proof 齐全后才具备完成资格；
- 授权代码路径将风险从 L0 自动升级为 L3；
- L3 只有在完整 audit、invariant、live、rollback、review、fixture 证据齐全后完成；
- `PASS / FAIL / BLOCKED / PARTIAL` 没有被混同；
- 被阻塞命令没有伪造 exit code；
- 修改 evidence ledger 后 `doctor` 检出完整性错误；
- 历史 `COMPLETED` verdict 在 reload 后保留，但篡改后的任务不能归档；
- Git 与运行时控制状态变化不会污染 release source hash。

### Meta 控制面

[`meta-effect-report.md`](meta-effect-report.md) 的最终 verdict：

```text
CONTROL_AND_META_MEASURED_PASS; CROSS_HOST_LLM_EFFECT_UNDERPOWERED
```

已测部分包括正常生产与 Meta 隔离、proposal authorship、fixture coverage、validity pre-pass、签名评测、authority、promotion 和 rollback。

### 真实 Codex Host campaign

[`codex-host-campaign-0.4-vs-0.5.md`](codex-host-campaign-0.4-vs-0.5.md) 使用 `codex-cli 0.144.3`、`gpt-5.6-sol`、隔离 Git workspace 和外部确定性 verifier，随机串行执行 0.4 与 0.5 各 5 次：

- 两个版本均为 `5/5` verifier pass、`5/5` issue route；
- 0.5 中位耗时 `-36.7%`、tool calls `-42.9%`、总 input tokens `-37.8%`、output tokens `-33.9%`；
- 0.5 uncached tokens `+14.8%`，因此不能宣称 token 成本整体下降；
- 这是一个公开合成任务上的实测点估计，不足以归因跨任务或跨 Host 的普遍提升。

## 4. 没有宣称的效果

本次已执行真实 Codex CLI / GPT-5.6 单任务 campaign，但没有执行 Claude Code、Cursor、Gemini 等跨 Host campaign，也没有外部私有 held-out 与签名 evaluator。因此以下结论仍是 `UNDERPOWERED`：

- 其他宿主/模型及多任务上的 route accuracy；
- 自主证据收敛和 completion-gate precision / recall；
- token、上下文、tool-call 和耗时变化；
- 真实项目交付质量提升；
- promoted policy 的跨 profile 可迁移性。

13 个公开 fixture 中，6 个确定性 fixture 实测通过，7 个依赖真实宿主的 fixture 正确返回 `underpowered`，没有被静默记为 pass。

## 5. 复现

```bash
python3 scripts/validate_skills.py
python3 scripts/validate_control_plane.py
python3 -m unittest discover -s tests -v
python3 scripts/validate_meta_effect.py
python3 scripts/benchmark_codex_host.py --baseline-runs 5 --candidate-runs 5 \
  --model gpt-5.6-sol --timeout 900 --jobs 1 \
  --output validation/codex-host-campaign-0.4-vs-0.5.json
```

`validate_meta_effect.py` 会校验当前控制平面报告；当 source-bound unittest evidence 与源树一致时复用它，否则执行 live candidate suite。报告和 proof artifact 均位于本目录。

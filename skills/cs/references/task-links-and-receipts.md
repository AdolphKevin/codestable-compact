# 外部任务、计划文件与只读提示

本接口只连接知识记录与外部任务，不负责方案批准、分派、业务验收或关闭任务。
当前格式增加可选字段，无需重建知识库。调用方运行安装技能的 `bootstrap.py --check`，
检查 `contract_version == 1` 和所需能力（`task-external-refs`、`exclusive-plan-file`、
`review-actions`、`task-source-acceptances`、`install-integrity`）；不要绑定固定提交。

## 外部任务关联

使用真实外部标识生成模板，参数可重复：

```bash
python3 <cs-skill>/scripts/cs_knowledge.py --root <project> template \
  --external-ref github=https://github.com/acme/service/issues/17 \
  --external-ref team-workflow=local-task-17
```

输出中的 `task.external_refs` 是 `[{"system":"github","id":"https://github.com/acme/service/issues/17"}]`
这样的数组，每项只接受字符串 `system` 和 `id`。GitHub 必须使用完整 HTTPS Issue URL，
包括自建 GitHub 的主机名；主机、仓库名和组织名转小写，编号去前导零，去尾部斜杠。
不接受仅编号、PR 地址、查询参数或片段。其他系统的 `id` 原样保留非空稳定标识，
`system` 转小写；输入两端空白去除，标识内部不能有空白。

`learn` 校验、去重并保存关联。更新原任务时对历史和新关联取并集，省略字段不能
删除旧关联；`template --task-id` 带回旧关联。`consolidate` 在主记录汇总关联，
归档记录继续保留自身关联及主记录指针。`task-files --format json` 返回 `external_refs`。
既有 `source` 和历史正文不变，不自动从请求文本猜测关联。

精确查找历史任务：

```bash
python3 <cs-skill>/scripts/cs_knowledge.py --root <project> brief --task '继续订单任务' \
  --external-ref github=https://github.com/acme/service/issues/17 --format json
```

提供此参数后，`related_tasks` 只返回匹配任一指定关联的活动记录，不用正文相似度
补齐；所有精确候选均返回，不受普通相关任务数量上限截断。
`external_task_matches` 返回候选编号、`multiple_candidates` 和 `auto_merge: false`。
多个记录命中同一任务时由调用方判断，不自动合并。写入时同一外部关联也是候选依据；
需要更新原记录，或明确填写 `new_task_reason` 解释独立目标。

## 多条验收引用

`task.source.workflow_acceptances` 是 `source` 内唯一受校验的保留键，记录一个任务
关联的多份验收文件，每项格式为：

```json
{"path": "docs/acceptance/orders.md", "sha256": "<64 位十六进制>", "issue": "ORDER-17", "task_id": "TW-17"}
```

- `path` 必填：仓库相对 POSIX 路径，非空，不以 `/` 开头，不含 `..`、`.` 或空段，不含空白。
- `sha256` 必填：64 位十六进制，统一转小写保存。
- `issue`、`task_id` 可选：非空且不含空白的字符串。其他键一律拒绝。
- 同一 payload 中同一路径对应不同内容时拒绝；完全相同的重复项合并；结果按 `path` 排序。

更新原任务时按 `path` 取并集：新提交的同一路径条目替换旧条目，其他旧条目保留。
因此重试同一 payload，或提交较旧、较短的列表，结果等于已保存内容时幂等返回，不丢失
已有引用；省略该键时保留已保存列表。`consolidate` 把归档记录的引用并入主记录，同一
路径以主记录为准。单数的 `source.workflow_acceptance` 仍是自由字段，不做校验。

`template --task-id` 带回已保存的列表；新增条目可直接编辑模板，或用
`--set 'task.source.workflow_acceptances=[...]'` 填写，`--set` 只允许在 `task.source`
下新建缺失的键。`doctor` 对已保存记录做同样的格式检查，问题代码为
`task.source.workflow_acceptances`；更新一条已保存格式错误的记录时返回
`error_code: task-source-invalid`。CS 只检查格式，从不打开、哈希或判断这些文件，
验收是否通过由调用方负责。

## 计划文件

`learn --dry-run --plan-out <新路径>` 的计划文件先完整写入临时文件，再原子发布；
同名并发只能一个成功。已有文件、目录、符号链接及悬空链接都返回
`error_code: plan-file-exists`、非零退出码和 `next_action`，原内容保持不变。
发布失败立即停止，不改用旧计划；新路径不能替代 CS 对并发的校验。

`learn` 返回明确的 `plan_state`：

| 状态 | 含义与下一步 |
|---|---|
| `ready` | 预览成功；应用本次返回的 `plan_token` 或 `plan_file` |
| `not-needed` | 同一请求已完整应用；没有新计划文件，不再应用 |
| `blocked` | 任务或卡片候选需要处理；退出 1，`plan_token` 和 `plan_file` 为空 |
| `applied` | 本次写入成功；继续核对 `doctor` |

普通输入和文件错误退出 2，返回 `error_code`、`error` 和 `next_action`。
批量调用每条使用独立路径，逐条完成“成功预览 → 应用同一计划 → 检查”，任一步失败
立即停止。写入成功但响应丢失时，以原 payload 和原计划重试，继续沿用幂等语义。

## 错误码

| `error_code` | 含义与下一步 |
|---|---|
| `invalid-input` | 输入格式或字段错误；按 `error` 修正后重试 |
| `plan-file-exists` | `--plan-out` 目标已存在；换一个新路径，原文件保持不变 |
| `plan-not-applicable` | 预览被任务或卡片候选阻断（退出 1）；处理候选后用新路径重新预览 |
| `revision-conflict` | 任务或卡片的 `expected_revision` 已过期；重新 `template --task-id`，再用新计划路径 `learn --dry-run` |
| `state-changed` | 预览与应用之间知识、工作区、登记文档或证据发生变化；重新生成模板并预览，不应用旧计划 |
| `plan-mismatch` | 计划属于另一个 payload；应用与本 payload 对应的计划，或重新预览 |
| `write-locked` | 另一个写入者持有 Wiki 写锁；等待其完成后重新生成模板并预览 |
| `task-source-invalid` | 已保存任务的 `source.workflow_acceptances` 格式错误；用 `doctor` 定位并修复后重试 |
| `input-output-error` | 文件路径、编码或访问失败；检查后重试，不应用旧计划 |

## 安装完整性

`bootstrap.py --check` 和安装输出都包含 `contract_version` 与 `integrity`：

```json
{"status": "intact", "manifest": "MANIFEST.json", "manifest_version": "2.2.0", "checked": 54,
 "changed": [], "missing": [], "unexpected": [], "reason": "installed files match MANIFEST.json"}
```

发行包的 `MANIFEST.json` 列出技能目录下每个常规文件的 SHA-256（不含自身、`__pycache__`、
`*.pyc`/`*.pyo` 和 `.DS_Store`）。`intact` 表示已安装文件与清单一致；`modified` 表示
有文件被修改（`changed`）、缺失（`missing`）或多出（`unexpected`），此时 `ok` 不变，
`suggested_action` 以重新安装提示开头，应从发行版重新安装 CS 技能，不在原地修补；
`unknown` 表示清单缺失或无法读取，`reason` 说明原因。检查只读，不修改技能或项目。

## 联合验证的唯一来源

CS 与 team-workflow 的跨仓库联合验证只以 team-workflow 仓库中的
`scripts/check_cs_knowledge.py`、`scripts/check_cs_delivery.py`、`scripts/check_parallel.py`
及其记录 `docs/validation.md` 为准。本仓的 `tests/test_workflow_contract.py` 只覆盖
CS 一侧的语义，不替代联合验证，也不在此复制其结果。

## 比较知识提示

```bash
python3 <cs-skill>/scripts/cs_knowledge.py --root <project> brief --task '修改订单创建' \
  --path src/orders.py --previous-receipt /tmp/previous-brief.json --format json
```

`--previous-receipt -` 从标准输入读取。可以传完整简报或其 `receipt` 对象。
只有查询的任务、范围和选项相同才标注未变化；其他查询仍展示全部本次提示。
回执只是读取证明，不表示知识被实际使用、问题已经处理或开发可以进入下一阶段。

- `review_actions.usage` 合并相同来源的问题，保留涉及卡片、关联摘要、原因和具体动作。
  同一问题与前次相比未变化时仍在正文展示。
- `review_actions.maintenance` 保留所有本次选中摘要的维护事项；
  `maintenance_summary` 提供总数、新增或变化数及未变化数。默认正文只显示计数，
  提供前次回执后展开新增或变化事项。
- 每项包含 `id`、`fingerprint`、`change`；回执的 `review_action_state` 保存只读比较依据。
  无关摘要及文档的问题不进入本次正文，完整知识库检查继续使用 `audit`。
- `receipt-check` 仍按相关来源是否变化返回状态，同时返回 `review_actions`。
  结果通过不代表证据已经有效，必须读取保留的当前使用核实项。

两条只读命令均不写已读状态、不修改摘要标记、不刷新复核时间，也不隐藏仍然存在的
来源或验证问题。摘要正文被修改或引用已不存在时，单独保留实际使用核实提示。

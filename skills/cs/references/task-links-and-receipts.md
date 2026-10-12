# 外部任务、计划文件与只读提示

本接口只连接知识记录与外部任务，不负责方案批准、分派、业务验收或关闭任务。
当前格式增加可选字段，无需重建知识库。调用方从安装技能的 `bootstrap.py --check`
检查 `task-external-refs`、`exclusive-plan-file`、`review-actions` 能力；不要绑定固定提交。

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

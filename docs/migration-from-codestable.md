# Migration from CodeStable

迁移目标不是把旧目录原样换一个位置，而是把“当前真相、可复用知识、执行历史”重新分层。

## 1. Skill 映射

| 旧入口 | 新入口/阶段 |
|---|---|
| `cs` | `cs`，默认自动路由并执行；`/cs route` 保留只看路由 |
| `cs-onboard` | `/cs init` |
| `cs-brainstorm` | `cs-feat` 的 intake/design，或 `cs-roadmap` 的 discover/frame |
| `cs-goal` | `/cs <bounded outcome>`；连续实现/验证已是默认 execution mode，跨多个 outcome 时进入 roadmap |
| `cs-feat` | `cs-feat` 全流程 |
| `cs-feat-design` | `cs-feat: design` |
| `cs-feat-design-review` | `cs-feat` 内部 design review；必要时人类 Gate |
| `cs-feat-impl` | `cs-feat: implement` |
| `cs-code-review` | feature/issue/refactor 各自内部 diff review |
| `cs-feat-qa` | `cs-feat: verify` |
| `cs-feat-accept` | `cs-feat: accept` |
| `cs-feat-ff` | `cs-feat` 的 `micro` lane |
| `cs-issue-report/analyze/fix` | `cs-issue` 的 reproduce/analyze/fix 阶段 |
| `cs-refactor-ff` | `cs-refactor` 的 `micro` lane |
| `cs-roadmap-review` | `cs-roadmap` 内部 review；必要时人类 Gate |
| `cs-req` / `cs-domain` | `cs-model` 的 requirement/domain/decision 模式 |
| `cs-keep` | 各流程 accept 时自动 promotion，或 `cs-model promote` |
| `cs-docs-neat` | 各流程 accept 的一致性检查，或 `cs-model reconcile` |
| `cs-doc-tutorial` / `cs-doc-api` | `/cs <documentation request>`；按新能力、缺陷修正或当前模型维护自动路由 |

旧的直接入口可以暂时保留为宿主 adapter alias，但不应继续持有独立工作流逻辑。

## 2. 目录分类

| 旧目录 | 新位置 | 迁移原则 |
|---|---|---|
| `requirements/VISION.md` | `migration-staging/model/vision.legacy.md` → `model/vision.md` | 先暂存，人工确认当前愿景后合并 |
| `requirements/CONTEXT.md` | `migration-staging/model/domain.legacy.md` → `model/domain.md` | 先暂存，去掉废弃术语后合并 |
| `requirements/*.md` | `migration-staging/model/requirements/` → `model/requirements/` | 只提升仍有效能力；不要自动宣布为当前真相 |
| `requirements/adrs/` | `migration-staging/model/decisions/` → `model/decisions/` | 检查 accepted/superseded 状态与替代关系 |
| `roadmap/` | `migration-staging/model/roadmaps/` → `model/roadmaps/` | 只提升仍在执行或仍约束未来的计划 |
| `compound/` | `migration-staging/knowledge/notes/` → `knowledge/notes/` | 先去重和提炼；任务日志不应提升为知识 |
| `features/` | `work/archive/legacy/features/` | 默认历史，不进入 current search |
| `issues/` | `work/archive/legacy/issues/` | 默认历史；未关闭项重建为 active work |
| `refactors/` | `work/archive/legacy/refactors/` | 默认历史；进行中的重建 state |
| `goals/` / `audits/` | `work/archive/legacy/` | 按历史处理，持久事实另行 promotion |
| `attention.md` | `attention.md` | 只保留当前且短期需要反复提醒的事项，建议不超过 80 行 |

## 3. 推荐迁移步骤

### 第一步：备份并初始化

```bash
cp -R .codestable .codestable.backup
# 通过 /cs init 创建新 runtime；已有文件不会被覆盖
```

### 第二步：预览自动分类

在本项目根目录执行：

```bash
python3 scripts/migrate_legacy.py /path/to/target-repo
```

默认只输出计划，不修改目标项目。

### 第三步：执行无损复制

```bash
python3 scripts/migrate_legacy.py /path/to/target-repo --apply
```

脚本只复制，不删除旧内容；历史执行材料直接进入 legacy archive，可能成为当前真相/知识的材料先进入 `migration-staging/`，不会自动覆盖正式 model/knowledge。报告写入：

```text
.codestable/migration-report.json
```

### 第四步：人工提炼 current truth

自动迁移无法判断一份旧 requirement 或 compound 是否仍然正确。运行：

```text
/cs 审核 migration-staging：以当前代码、测试和 accepted decision 为准，把仍有效内容提升到 model/knowledge，并去除重复与过期内容
```

### 第五步：重建正在进行的任务

不要把旧 feature 的全部文件继续当作 active 状态。对每个确实未完成的任务：

1. 新建一个 active work；
2. 把当前目标、已完成修改、剩余验收写入 `work.md`；
3. 在 `state.json.links` 中链接仍有效的旧文档或当前模型；
4. 将原目录保留在 legacy archive 作为证据。

## 4. 兼容配置

希望先保留旧 `/cs` 只路由体验时：

```json
{
  "entry": {
    "mode": "route",
    "route_summary": "debug"
  }
}
```

切换到推荐体验：

```json
{
  "entry": {
    "mode": "auto",
    "route_summary": "compact"
  }
}
```

## 5. 不应迁移的内容

- 每次 review 的“通过”套话；
- 已被代码和当前 ADR 推翻的旧设计；
- 没有复用价值的探索日志；
- 只为未来可能性创建的抽象说明；
- 重复出现在 design、review、QA、accept 中的同一段背景。

这些内容可以留在 legacy archive，但不应提升到 model 或 knowledge。

## 6. 从 0.2-alpha 的 telemetry 升级

执行 `/cs upgrade` 后，配置 schema 会升级到 2：

- 旧 `telemetry` 配置移动到 `migration.legacy_telemetry_config` 作为记录；
- 新 `observability.mode` 强制为 `passive`；
- raw Prompt/response/source/diff capture 强制关闭；
- `evolution.mode` 强制为 `manual`；
- `auto_diagnose / auto_propose / auto_evaluate / auto_promote` 强制为 false；
- promotion 强制要求人工 Gate。

旧 `.codestable/telemetry/runs/` 不删除。先预览：

```bash
python3 scripts/migrate_alpha_observations.py /path/to/project
```

确认后无损复制：

```bash
python3 scripts/migrate_alpha_observations.py /path/to/project --apply
```

通过的旧 run 进入 `observations/pending/`；带 failure signature 或失败 outcome 的 run 进入 `flagged/`。迁移信息保留在 observation 中，旧目录仍作为原始备份存在。

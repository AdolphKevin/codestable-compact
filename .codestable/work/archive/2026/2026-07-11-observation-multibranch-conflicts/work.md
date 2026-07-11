# 修复 observations 多分支冲突

- Work: `2026-07-11-observation-multibranch-conflicts`
- Kind: `issue`
- Lane: `standard`

## 1. Intent and acceptance

- Outcome: Observation 运行数据不再进入 Git；多分支与多 worktree 可各自记录而不产生合并冲突。
- Acceptance: 两个分支分别启动 run 后 Git 状态保持干净且可无冲突合并；旧版已跟踪的共享 index 不再被修改；现有 observation/feedback/evolution 行为保持通过。
- Non-goals: 跨 worktree 共享实时 observation，或自动修改用户现有 Git index。

## 2. Evidence

- Repository observations: 每个 run 已使用含微秒的唯一目录；所有生命周期动作仍会追加同一个已跟踪的 `observations/index.jsonl`，但仓内没有该 index 的读取者。
- Relevant current model / executable contracts: observations 是临时、项目本地、正常交付只写不读的飞行记录；bootstrap 升级必须保留已有 observation 数据。
- Baseline or reproduction: 临时 Git 仓库的两个分支各启动一次 run 后，合并在 `index.jsonl` 稳定得到 content conflict（merge exit 1）。

## 3. Design or root cause

- Chosen mechanism / root cause: 删除无人读取的共享 index 写入；在 observations 内用 scoped `.gitignore` 忽略全部运行数据，只保留 README 与 ignore 规则。
- Existing path reused: 继续以 worktree 根目录和 `pending/flagged/selected/<run-id>` 为唯一状态来源；所有消费者已直接扫描这些目录。
- Alternatives rejected and why: 分支命名空间仍会留下被跟踪的聚合文件；git-common-dir 会重新制造共享写点并破坏非 Git/相对路径语义。
- Compatibility / rollback / rollout (when relevant): bootstrap upgrade 刷新 ignore 规则但不删除数据；旧仓库需一次性从 Git index 取消跟踪，README 提供保留本地文件的命令。

## 4. Plan

- [x] 复现双分支冲突并定位共享写点。
- [x] 删除共享 index，安装 worktree-local Git ignore。
- [x] 覆盖 fresh install、upgrade 与 legacy tracked index 回归。
- [x] 运行完整发布验证并完成内部审查。

## 5. Changes and decisions

- Changed: observation recorder、alpha migration、bootstrap 资产/升级规则、README 与回归测试。
- Decisions made during execution: 不引入 branch id、锁、数据库或外部状态目录；删除 write-only index 比迁移它更小且兼容现有消费者。

## 6. Verification and review

- Commands and results: `validate_skills.py` PASS；`validate_meta_effect.py` measured control-plane PASS（跨宿主 LLM 证据 underpowered）；全量 56/56 单测 PASS。
- Observable acceptance evidence: 修复后临时仓库两个分支启动 run，两个 Git status 均为空，merge exit 0。
- Internal review findings and repairs: 发现单加 `.gitignore` 不能处理已跟踪 index，已停止写 legacy index；发现干净 clone 需要状态目录 `.gitkeep`，已保留并补 bootstrap 断言。最终复审无 blocking。

## 7. Promotion and closure

- Model updates: 无；现有 temporary observation 契约未改变。
- Knowledge promoted: scoped ignore、旧仓库一次性 untrack 说明已写入 shipped observations README。
- Remaining follow-ups: 已安装旧 runtime 需执行 upgrade，再按 README 从 Git index 取消跟踪旧 observation；bootstrap 不自动修改用户 Git index。
- Closure summary: observation 运行数据改为 worktree-local 且 Git ignored，并删除无消费者的共享 index，消除多分支稳定冲突点。

# 更新 0.4.0 中文 README 与 docs

- Work: `2026-07-10-update-chinese-docs`
- Kind: `model`
- Lane: `standard`

## 1. Intent and acceptance

- Outcome: 将 README 与 `docs/*.md` 原位整理为中文主文档，并补齐 0.4.0 已有、可核验的策略和验证事实。
- Acceptance: 9 个文档中文叙述完整；命令、路径、字段和技术专名保持可执行；链接、围栏、表格与发布验证通过。
- Non-goals: 不新增 `docs/zh-CN` 镜像；不写入会话专用下载链接、未核验 ZIP 哈希/大小或已删除的 MANIFEST；不翻译代码标识。

## 2. Evidence

- Repository observations: 工作树已包含未提交的 0.4.0 实现；根文档处于中文化中的 staged 状态，旧 `docs/zh-CN` 已 staged 删除。
- Relevant current model / executable contracts: `VERSION=0.4.0`；策略注册表 9 项、公开 fixture 12 项；`validation/meta-effect-report.*` 记录 54/54、33/33、13/13 与 6/0/6 证据结果。
- Baseline or reproduction: `sandbox:/mnt/data` 下载目标、ZIP、哈希和大小在当前工作区不可验证；`trigger-scan` 实际按 signal/policy、adapter/model_profile 与 Harness identity 分组。

## 3. Design or root cause

- Chosen mechanism / root cause: 原位翻译 8 篇 docs，并在现有 README 中只补缺失的策略、导航和验证摘要。
- Existing path reused: 保留现有 README 长期使用说明和根 `docs/*.md` 结构；机器标识沿用仓库原值。
- Alternatives rejected and why: 不恢复双份 `docs/zh-CN`，避免内容漂移；不整篇替换 README，避免丢失日常入口、上下文隔离和升级说明。
- Compatibility / rollback / rollout (when relevant): 文档改动可直接回退；验证器只兼容 Python 3.10 与新版 unittest 的两种标准 verbose 行格式。

## 4. Plan

- [x] 核验用户稿中的版本、策略、fixture、测试和下载信息。
- [x] 中文化 README 与 8 篇 docs，统一术语并修正过强陈述。
- [x] 修复 Python 3.10 下效果验证器误判已通过 mutant 测试的问题。
- [x] 完成最终发布验证与归档。

## 5. Changes and decisions

- Changed: `README.md`、`docs/*.md`；`scripts/validate_meta_effect.py` 增加 unittest verbose 格式兼容匹配。
- Decisions made during execution: 保留英文策略口号作为规范标签；Runtime Profile 的生产分组和评测锁分别按当前实现描述，不声称 `trigger-scan` 已锁定预算/toolset。

## 6. Verification and review

- Commands and results: `python3 scripts/validate_skills.py` PASS；`python3 -m unittest discover -s tests -v` 54/54 PASS；`python3 scripts/validate_meta_effect.py --output-dir /tmp/codestable-compact-meta-effect-docs-final` PASS，结论为 `CONTROL_PLANE_MEASURED_PASS; CROSS_HOST_LLM_EFFECT_UNDERPOWERED`。
- Observable acceptance evidence: 9 个文档无遗漏英文叙述（机器标识/专名除外），全部相对链接存在，代码围栏成对，`git diff --check` 通过。
- Internal review findings and repairs: 修正旧“所有晋升均需人工 Gate”、不完整 Runtime Profile 分组、术语多译和直译腔；验证器初次在 Python 3.10 将 13 项通过误报为缺失，已在共享解析点修复。

## 7. Promotion and closure

- Model updates: 无需新增 `.codestable/model` 文档；公开 README/docs 本身是本次维护的当前说明。
- Knowledge promoted: 无。
- Remaining follow-ups: 发布 ZIP、SHA-256 与 MANIFEST 需在最终文档和代码冻结后重新生成，不能沿用会话外部值。
- Closure summary: README 与 8 篇 docs 已完成中文化和事实校准；链接、Markdown 与三项发布验证全部通过。

# Current model index

这是当前真相的紧凑指针，不是完整文档汇总。只有与当前任务相关时才打开具体文件。

| Area | Path | Summary / tags |
|---|---|---|
| Vision | `vision.md` | 产品边界与长期能力方向 |
| Domain | `domain.md` | 当前领域词汇、实体与不变量 |
| Requirements | `requirements/` | 当前有效、可观察的能力要求 |
| Contracts | `contracts/` | 公共 API、事件、协议和持久化契约 |
| Decisions | `decisions/` | accepted / superseded 架构决策 |
| Roadmaps | `roadmaps/` | 当前仍有效的跨 feature 计划 |

维护规则：新增或移动 model 文档时更新本表的一行摘要与 tags。不要在这里复制正文。

规模规则：顶层 INDEX 建议不超过 160 行；超过时按 bounded context/domain 分片，顶层只保留分片指针。

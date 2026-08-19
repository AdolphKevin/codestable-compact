# 兼容性 · Index

公共或持久化兼容、版本、迁移、回滚与弃用

## 当前知识

- [旧项目内工具仅在显式升级时安全退役](k-20260819-130200-02-765d2222-旧项目内工具仅在显式升级时安全退役.md) · verified
  - 已有项目中的 .codestable/tools/cs_knowledge.py 由发行清单声明为退役文件；普通检查不改动它，只有显式升级才会先把它备份到 .codestable/backups 后再移除。
- [upgrade 逐页证据聚合到单一任务记录](k-20260807-151302-02-2608ee7f-upgrade-逐页证据聚合到单一任务记录.md) · verified
  - 一次 CodeStable upgrade 维护一条 knowledge-migration task-note，并在完整逐页账本中保存 legacy 哈希、备份、结论和证据；pending 页面保留且使升级保持 partial。
- [旧知识页仅在审计和可恢复性校验后移除](k-20260729-103956-02-039346a2-旧知识页仅在审计和可恢复性校验后移除.md) · verified
  - 一个 legacy Markdown 页只有在 current 实现/测试真相和 current Wiki 覆盖均已核对、该页的 learn 与 doctor 成功、源 SHA-256 未变化且同哈希备份存在时，才能从原 legacy 目录移除；证据不足的 pending 页必须保留并使 upgrade 保持未完成。

## 提议知识

- 无

已弃用和被取代的卡片见 [历史索引](../HISTORY.md#兼容性)。

本页由 `cs_knowledge.py reindex` 或 `learn` 生成；人工摘要请维护在 [README.md](README.md)。

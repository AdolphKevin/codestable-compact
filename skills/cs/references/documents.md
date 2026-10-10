# 原文档和引用

当前配置格式为 5。旧配置只报告需要调整，不自动迁移或重建知识。卡片、任务记录
和历史格式不变；每份原文保留在原位置，登记文件只有来源、范围和状态等元数据。
与开发方法组合时，产物归属见[开发方法与知识归属](development-methods.md)。

例如 `.codestable/documents/terms.json`：

```json
{"repository":"self","path":"GLOSSARY.md","title":"业务词汇","category":"requirements","status":"current","always":true}
```

跨仓来源 `.codestable/documents/ownership.json`：

```json
{"repository":"contracts","path":"docs/adr/0001-ownership.md","title":"资源归属","category":"decisions","status":"current","applies_to":[{"repository":"self","path":"src/auth"}]}
```

本机位置放在被 Git 忽略的 `.codestable/local.json`：

```json
{"repositories":{"contracts":"../contracts"}}
```

也可以传 `cs_knowledge.py --root <项目> --repository contracts=/本机目录 documents list`。
命令参数优先；本机路径与登记汇总视图不写回共享配置。不同成员新增不同登记文件，
无需共同编辑总表。编号在原文重命名时保持稳定；重复来源、编号冲突、越界路径和
缺失来源会报告问题。不能把配置调整作为删除或批量搬迁知识的依据。

路径只指向指定仓库内的 Markdown 原文，不支持网络抓取、目录通配或 Wiki 自引用。
`always` 适合项目规则与核心词汇；其余原文按任务、主题、路径和符号检索。
默认最多 12 份来源摘录，省略数明确返回。`documents list/read` 只读且不创建缓存。
登记每个具体 ADR；新 ADR 需要明确登记。读取支持工作区、暂存区和提交版本，
历史读取不会用当前登记内容冒充旧版本。原文全文不再复制为经验卡片。

从 `documents read --id terms` 取得 sha256 后，learn 的 items 可以填写：

```json
{
  "category": "requirements",
  "title": "术语原文引用",
  "reference": {"document": "terms", "section": "订单", "sha256": "填写实际原文 SHA-256"},
  "supersedes": ["填写被重复表达的旧卡片编号"],
  "supersession_reason": "已复核此结论由登记原文完整表达，保留旧卡片为历史"
}
```

`section` 是唯一的 Markdown 标题文本，可省略以引用全文。不复制正文、理由、影响、
证据或未来场景。同一文档同一章节只允许一个当前引用；相同 payload 保持幂等。
更新原文后重新读取并复核，再用既有 card_id/expected_revision 更新引用哈希；旧哈希
保留在 reference_history 中。实际含义变化应先处理原文的接受状态与取代关系。

CS 不自动判断两段业务文字是否等义。原文完整覆盖的卡片改为引用；局部重叠的经验
继续保留独有结论和证据；真实矛盾保留并报告，不能批量覆盖成“已核对”。查询回执
记录本次查询相关来源，`receipt-check` 只读核对相关原文和知识，忽略无关任务或缓存变化。
新增适用知识、相关原文变化或删除会要求复核。learn 计划仍绑定写入所需状态和跨仓原文，
避免预览与应用之间来源变化。
Git 暂存/提交检查不会把外部仓库当前工作区冒充成历史版本，而会明确报告无法验证。

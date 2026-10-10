# 原文档和引用

CS 2.1.0 在格式 4 上增加可选登记。旧项目无需重建；未登记来源时仍按原有 Wiki 检索。

与开发方法组合时，各类产物的归属和任务记录方式见[开发方法与知识归属](development-methods.md)。

```json
{
  "wiki": {
    "repositories": {"contracts": {"root": "../contracts"}},
    "documents": {
      "terms": {"repository": "self", "path": "GLOSSARY.md", "title": "业务词汇", "category": "requirements", "status": "current", "always": true},
      "ownership": {"repository": "contracts", "path": "docs/adr/0001-ownership.md", "title": "资源归属", "category": "decisions", "status": "current", "applies_to": [{"repository": "self", "path": "src/auth"}]}
    }
  }
}
```

将该片段合并进既有配置，保留其他字段。编号在文件重命名时保持稳定，路径只指向
已配置仓库内的 Markdown 原文，不支持网络抓取、通配目录或 Wiki 自引用。
`always` 适合项目规则与核心词汇；其余原文按任务、主题、路径和符号检索。
默认最多 12 份来源摘录，省略数明确返回。`documents list/read` 均只读且不创建缓存。
登记每个具体 ADR，让状态和适用范围可审查；新 ADR 需要明确加入登记。

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
记录全部登记原文的状态，learn 计划也绑定跨仓原文，避免预览与应用之间来源变化。
Git 暂存/提交检查不会把外部仓库当前工作区冒充成历史版本，而会明确报告无法验证。

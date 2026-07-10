# Retrieval protocol

## Read order

0. 当前对话中已经给出的事实；
1. exact active work 的 `state.json`；
2. 当前 stage 所需的 `work.md` 小节；
3. 非空且自上次读取后变化的 `attention.md`；
4. `state.json.links` 中显式链接、且变化的 model/knowledge 文档；
5. `scope` 对应的代码、测试、配置和可执行契约；
6. `search --scope current` 的少量定向命中；
7. 只有写明理由时才 `search --scope archive`；它先查 `archive-index.jsonl`，命中候选后才可用 `--deep` 搜具体历史正文。

## Prohibited defaults

- 不递归 Glob 整个 `.codestable/`；
- 不因存在 ADR 目录就读取全部 ADR；
- 不对所有 compound/knowledge 执行无关键词 grep；
- 不把所有历史 feature 当作新设计输入；
- 不重复读取哈希未变化且当前对话已包含的文件；
- 正常 delivery 不读取 `observations/`、`evolution/`、`evals/` 或 `harness/versions/`；
- observation recorder 的确定性写入/清理不等于把其内容装入模型上下文。

## Establishing links

首次取证找到真正约束本任务的 requirement/contract/decision/knowledge 后，把相对路径加入 `state.json.links`。后续阶段从链接恢复，不重新发现整棵树。

## Receipt

读取后执行：

```bash
python3 .codestable/tools/cs_context.py receipt --work <id> \
  --session <live-conversation-key> --stage <stage> \
  --reason <reason> <path>...
```

收据只表示“该版本已读取”，不替代 Agent 的语义判断。

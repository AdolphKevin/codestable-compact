# Rebuild knowledge from current evidence

CodeStable 2.0 uses configuration Schema 4. It supports a fresh knowledge base
and explicit complete rebuilds. Old configuration, card formats, task history
and generated indexes are not migrated. The former upgrade command and old-page
search are removed.

## Scope and execution

`$cs rebuild` replaces the selected project's entire `.codestable`, including
configuration, authored knowledge, task history, caches and old directories.
Everything outside that directory is left in place. Ordinary tasks, read-only
checks and tool updates never imply permission to clear knowledge. Existing user
authorization is sufficient; do not ask again for the same scope.

```bash
python3 <skill>/scripts/bootstrap.py --root <project> --check
python3 <skill>/scripts/bootstrap.py --root <project> --rebuild --dry-run
python3 <skill>/scripts/bootstrap.py --root <project> --rebuild --plan-token '<token>'
```

The preview makes no filesystem writes and lists the full replacement. Its token
binds the target path, directory contents and release files. Changes invalidate
the plan. The script validates the release and prepares a checked empty layout
before removing old data. It refuses a symlinked `.codestable` and never follows
nested symlinks to remove their targets. No automatic backup is created.

For an absent or empty directory, plain bootstrap initializes the layout. It
refuses existing content instead of overwriting it. A damaged or old config is
reported as `needs-rebuild`; no repair or format merge is attempted.

## Build the actual knowledge

An empty layout is not a completed rebuild. Bootstrap returns
`knowledge_build.complete: false` so the Agent continues:

1. Inspect current application entries, implementation, tests, contracts and
   accepted requirements, without treating old knowledge as an input.
2. Write the project overview and review all 11 knowledge categories. Create
   evidence-backed cards for durable conclusions; identify uncovered categories
   rather than inventing content. Requirements describe accepted targets; facts
   describe behavior supported by code and executable tests.
3. Use one `kind: knowledge-rebuild` task note for the rebuild. Once the requested
   validation is complete, apply a learning plan with current scopes, evidence and
   concrete future use. Fill related category summaries from the resulting cards.
4. Run `doctor --check-current-references`, `audit` and representative `brief`
   queries. Verify that the new cards answer useful questions and point to actual
   implementation or tests. Report incomplete work if essential evidence is absent.

Current knowledge still distinguishes accepted targets, verified behavior,
proposals and superseded history. Normal conclusion changes use `supersedes`.
A complete rebuild starts new record IDs and task provenance; it does not rewrite
or migrate an old task into a new one.

## Validation

`tests/test_bootstrap.py` verifies zero-write previews, old-format rejection,
full replacement boundaries, stale and cross-project plans, preparation failure,
symlink isolation and the removed upgrade command. `tests/test_compact_storage.py`
checks that application source survives a reset and the new library starts empty.
The release validator exercises preview, rebuild, new knowledge write, retrieval
and reference checks through the actual command-line entry points.

## 分类摘要复核

运行 `audit --format json` 查看具体问题。补写分类摘要后，诊断中的
`expected_knowledge_hash` 是该类当前卡片集合的标识。实际对照卡片复核摘要后，在
分类 README 中加入标记，使用真实复核时间：

```text
<!-- codestable:summary-review {"knowledge_hash":"<该分类 expected_knowledge_hash>","reviewed_at":"<实际复核时间，ISO-8601>"} -->
```

缺少、过期或与当前卡片不一致的摘要需要复核，不应仅为消除提示填写标记。

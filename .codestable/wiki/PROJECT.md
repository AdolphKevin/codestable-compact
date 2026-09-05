# CodeStable 项目总览

<!-- codestable:canonical:start -->
CodeStable 只提供一个公开技能 `$cs`：工作前查询项目知识，工作后记录任务结果和可复用结论。
项目数据位于 `.codestable`，各项目通过 `--root` 复用 Skill 中的共享工具。源码维护目录是 `skills/cs/runtime_src`，发布脚本由 `scripts/build_runtime.py` 生成。
当前数据格式为 4；新库以当前代码、测试和已确认需求为依据建立。明确授权的 `$cs rebuild` 清空目标 `.codestable` 后重新建库，旧配置、卡片和任务不迁入。
知识固定分为 11 类，按当前、提议、弃用和被取代状态区分。普通任务的知识演进保留来源和取代关系；只在最终验证后沉淀长期卡片。
知识卡片、任务记录和人工摘要纳入 Git；动态目录与机器索引放在可重建的本地缓存。带范围的查询聚焦该范围，提交检查读取对应 Git 版本。
发布验证入口：`python3 -m unittest discover -s tests -v` 与 `python3 scripts/validate_release.py --source .`。项目运行工具仅使用 Python 标准库，支持 Python 3.10 及以上。
<!-- codestable:canonical:end -->

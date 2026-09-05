# CodeStable 项目文件

当前知识入口是 [wiki/INDEX.md](wiki/INDEX.md)。命令由已安装 cs 技能的共享工具提供，通过 `--root` 指定项目；项目不保存运行工具副本。

- `config.json`：分类、主题、仓库映射和检索设置。
- `wiki/PROJECT.md`、分类 `README.md`、知识卡片和任务记录：项目维护的知识来源，纳入版本管理。
- `wiki/INDEX.md`、分类 `INDEX.md`、`TOPICS.md`、`HISTORY.md`：稳定阅读入口。
- `cache/wiki/`：可重建的目录和机器索引，默认忽略；缺失不会阻止检索或提交检查。
- `VERSION`、`manifest.json`、Wiki 使用说明和输入格式：发行文件。

完整重建替换整个 `.codestable`，不迁移旧配置、卡片、任务或旧目录；只有用户明确授权才执行。建立目录后还必须从当前代码、测试和已确认需求填写新知识并验证。

# Runtime maintenance source

`00_core.py` through `70_cli.py` are the reviewed maintenance sections for the
project-local runtime. The sections are ordered by `scripts/build_runtime.py` and
assembled into the dependency-free distribution asset at
`skills/cs/assets/project/.codestable/tools/cs_knowledge.py`.

Only the generated asset is copied into consuming projects. Edit the smallest
relevant maintenance section, run `python3 scripts/build_runtime.py`, then run
the unit and release checks. The build embeds a source digest and fails in
`--check` mode if source and distribution differ.

The sections deliberately share one runtime namespace so the installed artifact
remains a single Python-standard-library file. Their boundaries separate common
formats, capture validation, storage/indexes, mutations, retrieval, drift,
governance/audit, and the command-line interface.

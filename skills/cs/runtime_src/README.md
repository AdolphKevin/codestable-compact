# Runtime maintenance source

`00_core.py` through `70_cli.py` are the reviewed maintenance sections for the
shared Skill runtime. The sections are ordered by `scripts/build_runtime.py` and
assembled into the dependency-free distribution asset at
`skills/cs/scripts/cs_knowledge.py`.

Consuming projects keep only their data and call this shared asset with `--root`.
Edit the smallest relevant maintenance section, run
`python3 scripts/build_runtime.py`, then run the unit and release checks. The
build embeds a source digest and fails in `--check` mode if source and
distribution differ.

The sections deliberately share one runtime namespace so the generated artifact
remains a single Python-standard-library file. Their boundaries separate common
formats, capture validation, storage/indexes, mutations, retrieval, drift,
governance/audit, and the command-line interface.

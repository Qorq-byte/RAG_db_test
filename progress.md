# Progress Log: 网页与公开 GitHub 仓库导入

## 2026-09-20

- 审阅当前实施计划、最近提交和搜索链路。
- 用户确认：先完成规划，再实施；每个完成步骤均提交并推送 GitHub。
- 用户确认：多个 `--tag` 必须同时匹配。
- 用户确认了元数据契约与索引/错误处理设计。
- 已提交并推送设计文档：`0657573 docs: design search metadata filters`。
- 用户已审阅并确认设计文档。
- 已写入三步实施计划；下一步为提交并推送该计划，然后实施步骤 1。
- 步骤 1 已完成并推送：`47a148b feat: add controlled ingestion metadata`；定向测试 14 passed。
- 步骤 2 已完成并推送：`63b509e feat: filter retrieval by controlled metadata`；后端集成测试 17 passed。
- 步骤 3 已完成并推送：`06f923b feat: expose metadata search filters`；全量测试 93 passed。

## 2026-09-21

- 审查项目主计划、当前实现、Git 历史与工作树：第六里程碑（网页与公开 GitHub 导入）是下一项未完成范围。
- 用户确认严格按既有里程碑顺序继续，并批准独立受限适配器方案。
- 已写入网页与公开 GitHub 仓库导入设计规格，待提交并推送后请用户审阅。
- 设计规格已提交并推送：`5930141 docs: design web and GitHub import`。
- 用户已审阅并确认规格；已写入三步实施计划，待提交并推送后开始步骤 1。
- 实施计划已提交并推送：`3505866 docs: plan web and GitHub import`；开始步骤 1。
- `uv` 首次检查因沙箱禁止访问用户缓存失败，待授权后更新 HTTPX 与 Trafilatura 锁定依赖。
- 已在授权后锁定并安装 HTTPX、Trafilatura；`uv.lock` 已更新。
- 步骤 1 已完成：新增受限网页抓取、robots 策略和正文提取模块，以及 6 项定向测试；`uv run pytest tests/unit/web` 通过（6 passed），待提交推送。
- 步骤 1 已推送：`34b4ade feat: add bounded web crawler`。
- 步骤 2 已完成：网页正文可作为 `web` 资料以 URL 为稳定标识导入、更新或跳过，`ragdb crawl` 已替换占位命令；定向测试 13 passed，待提交推送。
- 步骤 2 已推送：`80f7574 feat: import crawled web pages`。
- 步骤 3 已完成：`ragdb repo` 支持经校验的公开 GitHub HTTPS 仓库浅克隆与受控文件过滤；定向测试 9 passed，待提交推送。
- 步骤 3 已推送：`a39f32e feat: import public GitHub repositories`。
- 第六里程碑验收：`uv run pytest` 通过（104 passed）；`uv run python -m ragdb crawl --help` 与 `repo --help` 通过，待提交验收记录。
- 用户批准前台持续运行的目录监听与显式集合重建方案；正在写入设计规格。
- 第七里程碑验收：`uv run pytest` 通过（109 passed）；`watch --help` 与 `reindex --help` 通过。

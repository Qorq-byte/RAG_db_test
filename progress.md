# Progress Log: 桌面端实际体验与交互完善

## 2026-09-24 桌面端模型设置

- 用户批准模型设置设计，范围包括问答/生成模型、本地/云端嵌入模型、连接测试及所有集合的安全重建。
- 设计规格提交：`be70c06 docs: design desktop model settings`。
- 创建并推送功能分支：`codex/desktop-model-settings`。分支首推包含本地尚未上传的项目收尾提交与模型设置规格提交。
- 已建立五阶段实施计划；之后每阶段独立验证、提交并推送该分支。

## 2026-09-24 项目进度核验与执行

- 确认核心路线、问答、学习产物和桌面工作台均已完成；开始发布前健康检查。
- 工作区保护：不改动既有集合 CLI 测试修改或未跟踪的“前端设计”草稿。
- 全量验证：`uv run pytest -q`，152 passed in 24.50s。
- CLI 验证：`uv run ragdb --help` 成功；所有既有命令组均可发现。
- 未发现项目代码回归；本次仅更新项目跟踪文档，没有产品代码改动。

## 2026-09-24 项目收尾

- 将 2026-09-16 主实施计划中的八个里程碑状态更新为最终完成情况，并注明后续问答、学习产物与桌面工作台进展。
- 移除 CLI 中没有调用点的 `_pending()` 占位辅助函数及 `NOT_IMPLEMENTED` 退出码。
- 保留既有 `tests/integration/test_collection_cli.py` 工作区状态和未跟踪 `前端设计/` 目录。
- 按当前指令未运行测试；改动仅涉及状态文档与无调用点代码清理。

## 2026-09-23

- 审查已完成的桌面工作台与 UI 重构；确认当前主线已与 `origin/main` 对齐，工作区存在用户保留的测试改动及“前端设计”目录。
- 在用户确认的范围内完成完整回归：`uv run pytest`，`144 passed in 19.63s`。
- 用户确认以提供的侧栏交互语言为基准，并批准导航布局、操作反馈、键盘可访问性三阶段方案。
- 设计规格已提交：`098922c docs: design desktop experience polish`。
- 已建立详细实施计划。
- 步骤 1 完成：侧栏宽度、折叠和详情栏偏好均已安全持久化；支持边缘拖拽调宽、减少动效以及窄窗临时收起和恢复。
- `uv run pytest tests/unit/test_desktop.py` 通过（12 passed）。首次沙箱执行无法访问用户级 uv 缓存，经授权重试后通过。
- 第一阶段本地提交：`35523de feat: persist desktop layout preferences`。推送 `origin/main` 被安全策略拒绝，因为直接修改共享默认分支需要用户明确确认；未重试。
- 步骤 2 完成：检索、问答和学习产物提交会防止重复请求、在后台任务结束后恢复入口并展示结果状态；集合导入也采用相同的防重复与恢复规则。
- `uv run pytest tests/unit/test_desktop.py` 通过（14 passed），覆盖成功、失败和重复提交防护。
- 步骤 3 完成：增加页面切换、侧栏切换与 Escape 快捷键；调整手柄支持键盘；导航、详情栏和主要动作补足可访问名称及焦点样式。
- `uv run pytest tests/unit/test_desktop.py` 通过（17 passed），覆盖键盘手柄、快捷键、Escape 和多行编辑器焦点保护。
- 验收完成：`uv run pytest` 通过（152 passed in 21.49s）；受控无头 `ragdb-gui` 启动检查正常退出。

---

# Historical Progress Log: 网页与公开 GitHub 仓库导入

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

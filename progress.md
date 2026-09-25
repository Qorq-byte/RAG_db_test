# Progress Log: 桌面端实际体验与交互完善

## 2026-09-25 Ollama 嵌入扩展：步骤 1 后端

- 按用户指定新增 Ollama 本地嵌入配置与 `/api/embed` 适配器，批量向量及维度校验接入现有嵌入工厂；旧本地与云端 profile 指纹保持兼容。
- 本机 `embeddinggemma:latest` 对固定合成文本的真实请求成功，返回 1 个 768 维向量；定向回归 37 passed。密钥未进入源码、日志或提交。
- 下一步将提供桌面设置入口并在隔离集合完成真实全局重建。

## 当前交付摘要（2026-09-25）

- 阶段 1–4 已进入 `main`；阶段 5 工作分支 `codex/desktop-model-settings-acceptance`。文档 `7cea17f`、自动化验收 `ac159b6`、真实本地嵌入记录 `b093d6c` 已分别推送。
- 全量回归 198 passed；本地嵌入模型切换和检索真实通过。Ollama 无聊天模型，云端服务与测试凭据未配置，阶段 5 仍进行中。
- 验收矩阵与环境限制见 [验收记录](docs/acceptance/2026-09-25-desktop-model-settings.md)。

## 2026-09-25 模型设置阶段 5.3：真实服务联调（部分）

- 真实本地嵌入通过：隔离合成集合使用已缓存的 `BAAI/bge-small-zh-v1.5` 建索引，连接测试并重建切换至已缓存的 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`；切换前后均检索到 1 条结果，测试目录已删除。
- Ollama 0.24.0 可运行，但只安装 `embeddinggemma:latest`，无聊天模型；云端服务、模型与测试凭据未配置。对应真实联调保持待验证，未发送云端请求或下载模型。状态矩阵见 [验收记录](docs/acceptance/2026-09-25-desktop-model-settings.md)。

## 2026-09-25 模型设置阶段 5.2：自动化验收

- 全量回归 198 passed，桌面设置定向回归 14 passed；CLI 帮助退出码 0，隔离数据目录的受控桌面启动退出码 0，Windows 原生模型设置页渲染成功。
- 修正 Qt 异步进度测试的等待时序，复核后未发现产品代码回归。完整命令、结果与环境限制见 [验收记录](docs/acceptance/2026-09-25-desktop-model-settings.md)。
- `uv run` 因沙箱缓存 ACL 和离线构建依赖获取失败；使用现有 `.venv` 运行同一测试集完成验收。

## 2026-09-25 模型设置阶段 5.1：使用指南

- 在 README 补充“系统 → 模型设置”的本地与云端配置步骤、连接测试、保存、全局嵌入重建、凭据与外部覆盖说明；纠正 `reindex` 只能处理集合本地文件的旧描述。
- 为 `config.example.toml` 与 `.env.example` 增加安全示例和两类云端密钥字段，未写入真实密钥。
- 验证：示例 TOML 可解析，`load_settings` 可加载；README 本地链接检查无缺失，`git diff --check` 通过。使用现有 `.venv` 运行检查；默认 uv 用户缓存受沙箱 ACL 限制。
- 当前 `main` 和 `origin/main` 已包含阶段 4；本阶段工作分支为 `codex/desktop-model-settings-acceptance`。保留用户既有 CLI 测试修改与“前端设计”目录。

## 历史交付摘要（2026-09-24）

- 模型设置阶段 1–4 完成；阶段 5“文档与最终验收”待执行。当前路线以 [task_plan.md](task_plan.md) 为入口。
- 阶段 4 提交 `a8240ae` 已推送至 `origin/codex/desktop-model-settings-ui`；尚未合并 `main`。阶段 1–3 已合并至主线 `f021716`。
- 最近一次完整回归：198 passed in 80.28s；Windows 原生 Qt 隐藏窗口渲染成功，已检查中文显示。
- 验证边界：自动化包含替身模型服务和故障注入；真实 Ollama、真实云端接口及真实系统凭据读写链路尚需最终联调确认。
- 本轮仅整理进度与下一阶段规划，未改动产品代码，未重新运行测试；保留下方历史记录。

文档分工：本文件保留交付证据；[实施计划](docs/superpowers/plans/2026-09-24-desktop-model-settings-implementation.md) 维护执行步骤和验收条件；[findings.md](findings.md) 保留技术结论。

## 2026-09-24 模型设置阶段 4

- 系统导航新增“模型设置”，分开配置问答/生成与嵌入模型；支持本地 Ollama、Sentence Transformers 和云端 OpenAI 兼容服务。
- 提供模型、地址、超时、批大小、掩码密钥、连接测试和 Ollama 已安装模型刷新；标注并锁定环境变量和 `.env` 接管字段。
- Chat 保存后更新运行时并可重启恢复；密钥仅保存在系统凭据库，按服务地址隔离，错误信息不回显服务响应或密钥。
- 嵌入候选配置显示当前模型、待应用模型和集合数；后台重建支持确认、进度、取消、失败重试和关闭窗口保护；云端发送资料前明确确认。
- 全量回归：`uv run pytest -q`，198 passed。包含目标服务变化后阻止未确认请求、密钥隔离、后台线程与取消保护。
- 按 frontend-design 的截图复核要求检查既有工作台布局：Qt offscreen 字体显示方框；改用 Windows 原生 Qt 平台（355 个字体族）后中文、字段和分区显示正常，无需修改产品字体。
- 原生隐藏窗口渲染成功生成 `model-settings-windows.png`；真实云端 API/Ollama 调用尚未实测，属于阶段 5 的可用环境验收范围。
- 本阶段提交推送分支为 `codex/desktop-model-settings-ui`；保留用户既有 CLI 测试修改和“前端设计”目录，不纳入提交。

## 2026-09-24 模型设置阶段 3

- 新增 `EmbeddingRebuildService`：直接读取 SQLite 当前代次切片，覆盖本地文件、网页、GitHub 和手动文本；分批生成新向量、校验持久化结果并汇报进度，不修改切片与 FTS。
- 完整构建后在同一 SQLite 事务中发布活动 profile 与来源模型信息；保留旧命名空间。嵌入、向量写入、校验、发布失败或取消时，清理暂存向量并维持旧索引可检索。
- schema v5 增加跨进程重建门禁与导入租约；导入、目录监听删除、集合和来源删除受门禁保护。旧服务实例在 profile 切换后拒绝继续写入，新建 runtime 服务读取最新 profile。
- Windows 使用 OpenProcess/GetExitCodeProcess 查询进程存活，替换不适用于该平台的 `os.kill(pid, 0)`；死进程留下的门禁/租约可恢复，重试先清理对应暂存空间。
- 云端候选凭据在发布前安全保存；发布后原子同步 TOML。同步失败返回明确警告，数据库保持权威，`from_config` 启动时重试恢复配置文件。
- 定向回归：50 passed。最终全量回归：`uv run pytest -q`，178 passed in 70.16s。新增测试覆盖四类来源、不同维度、当前代次过滤、FTS 保持、三类存储故障、末批次取消、进程探测、跨进程门禁及重启恢复。
- 本阶段按约定独立提交并推送 `codex/desktop-model-settings`；桌面设置页面仍属于下一阶段。

## 2026-09-24 模型设置阶段 1

- 新增 `ModelSettingsService`：TOML 原位保留其他配置与注释，系统凭据库存放云端 API Key；环境变量和 `.env` 仍优先，密钥不可用时不回退到明文文件。
- 新增 Chat/embedding 固定最小请求连接测试，以及 Ollama 已安装模型列表查询；模型测试不触碰知识库索引。
- 声明并锁定 `keyring`、`tomlkit` 依赖。
- 定向验证：`uv run pytest tests/unit/test_model_settings.py tests/unit/test_config.py tests/unit/chat/test_chat_models.py tests/unit/embeddings/test_openai_compatible.py`，18 passed；新增覆盖环境密钥优先和凭据删除。
- `/browse` 打开 TOMLKit 官方页面时遇到状态目录 ACL 启动超时；未进行其他网页浏览。keyring Windows 凭据库资料此前已由 `/browse` 查阅。
- 用户既有 `tests/integration/test_collection_cli.py` 修改与未跟踪 `前端设计/` 仍保持原样。

## 2026-09-24 模型设置阶段 2

- SQLite schema 升至 v4，新增单例活动嵌入 profile；JSON 仅记录非敏感配置，保存稳定 SHA-256 指纹与向量命名空间。
- `ApplicationRuntime` 初始化时以数据库 profile 为活动嵌入配置；旧数据库首次初始化继续指向旧版 Chroma 命名空间，避免既有向量失联。
- Chroma 集合名支持按 profile 指纹隔离；collection/source/ingestion/search runtime 路径共用当前 profile 命名空间。
- 云端嵌入凭据改按非敏感 profile 指纹区分，避免保存候选配置时覆盖旧活动 profile 的 key。
- 定向验证：模型配置、数据库迁移/仓储、Chroma 向量测试和配置测试共 49 passed。
- 全量验证：`uv run pytest -q`，163 passed in 22.94s。

## 2026-09-24 桌面端模型设置

- 用户批准模型设置设计，范围包括问答/生成模型、本地/云端嵌入模型、连接测试及所有集合的安全重建。
- 设计规格提交：`be70c06 docs: design desktop model settings`。
- 创建并推送功能分支：`codex/desktop-model-settings`。分支首推包含本地尚未上传的项目收尾提交与模型设置规格提交。
- 已建立五阶段实施计划；之后每阶段独立验证、提交并推送该分支。
- 依赖分析后调整阶段顺序：先完成活动嵌入命名空间和全集合安全重建，再向用户开放可保存的嵌入模型设置。

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

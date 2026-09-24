# Findings: 桌面端实际体验与交互完善

## 安全重建实现（2026-09-24）

- Windows 上不能使用 `os.kill(pid, 0)` 探测进程存活：这会走终止进程路径。现使用只查询状态的系统句柄，并用独立子进程回归验证其不会发出终止信号。
- 仅在导入开始前判断“正在重建”不足以避免竞态；导入需持有 SQLite 租约，重建只有在所有租约释放后才取得独占门禁。删除资料/集合也需要同一门禁。
- 模型切换后其他进程可能仍持有旧模型和向量库实例；绑定活动指纹与命名空间的校验可阻止旧实例写入，runtime 新服务从 SQLite 获取最新配置。
- 发布 profile 与来源模型字段必须处于同一事务。注入来源元数据更新失败后，已执行的 profile 更新也会回滚，旧向量仍可检索。

## 模型设置实现基线（2026-09-24）

- 用户已批准同时配置问答/学习生成模型与嵌入模型；UI 和安全索引切换要求记录于 `docs/superpowers/specs/2026-09-24-desktop-model-settings-design.md`。
- Chat adapter 已支持 Ollama `/api/chat` 与 OpenAI 兼容 `/chat/completions`；嵌入支持 Sentence Transformers 与 OpenAI 兼容 `/embeddings`。
- TOML 明文 API Key 当前被有意忽略；需要系统 keyring 凭据存储，并维持环境变量/`.env` 优先级。
- Chroma 当前按知识集合创建固定向量集合；应按嵌入配置指纹隔离不同向量维数。
- SQLite `chunks` 保存所有来源的当前切片文本；重建可覆盖网页、GitHub、手动文本，而不依赖源文件可访问。
- 现有 `reindex` 仅重新处理 `file://` 来源；全局模型更换需要新服务，不能复用现命令作为完整实现。
- schema v4 的活动 profile 不含 API Key；`namespace_id=legacy` 兼容原有 `ragdb_{collection UUID}` 向量集合，新的 profile 使用自身指纹隔离。
- 运行时的嵌入配置从 SQLite 活动 profile 还原；云端嵌入 key 依 profile 指纹存放，防止待切换模型的 key 替换当前活动模型密钥。

## 2026-09-24 进度核验

- 主实施计划的八个里程碑均标记为完成；README 已覆盖 CLI、网页/仓库导入、监听、问答、学习产物和桌面工作台。
- 当前 `main` HEAD 为 `83d5da1`，远端 `origin/main` 为 `2356b49`；本地收尾提交尚未推送。
- 用户工作区已有 `tests/integration/test_collection_cli.py` 修改以及未跟踪 `前端设计/` 目录，均不属于本次健康检查的可修改范围。
- `uv run pytest -q` 于 2026-09-24 通过：152 passed in 24.50s；桌面工作台的离屏 Qt 测试包含页面、响应式布局、异步防重复提交与可访问性快捷键。
- `uv run ragdb --help` 能正常退出并列出所有命令组。当前 PowerShell 捕获将中文帮助显示为乱码，属于终端代码页呈现，未构成 CLI 失败。

## 2026-09-23 当前基线

- 桌面端使用原生 PySide6，现有设计明确不引入 React、Tailwind 或 WebEngine。
- `SidebarWidget` 已有分组、折叠、悬停高亮与宽度动效，但没有拖拽调宽、布局偏好持久化或响应式状态恢复。
- `MainWindow` 在窄窗口会强制收起导航和隐藏详情栏，恢复宽度时不会还原用户偏好。
- `CollectionsPage` 为后台导入维护了局部任务集与状态徽标；其余异步页面缺少统一的重复提交与过期结果防护契约。
- 当前完整自动回归：`144 passed`（2026-09-23）。

---

# Historical Findings: 网页与公开 GitHub 仓库导入

## 当前实现

- `crawl`、`repo` 为占位 CLI 命令；`SourceType` 已有 `WEB` 和 `GITHUB_REPOSITORY`。
- `LocalIngestionService` 已管理内容哈希、资料代次、SQLite/ChromaDB 发布和失败回滚。
- 配置已有 `[crawl]` 的深度、页面数、速率、超时与 User-Agent。
- 当前依赖未包含 HTTPX 与 Trafilatura；实施时需明确加入并锁定。
- 本地资料导入已有扩展名允许列表、忽略目录与文件大小限制，可供仓库遍历复用。

## 已确认的产品契约

- 按既有里程碑顺序先实现网页与公开 GitHub 导入。
- 网页抓取遵守 robots，仅同域，受深度、页面数、限速与超时约束。
- 仓库仅接受公开 GitHub HTTPS URL，并使用系统 Git 浅克隆。
- 每完成一个验证步骤即提交并推送至 GitHub。

## 风险与处理

- Robots 获取失败与跨域重定向必须拒绝抓取，防止安全边界被绕过。
- 临时仓库清理需要只针对本次创建的已解析路径。
- 单页或单文件的失败必须隔离，不能中断整个批次。

## 设计结论

- 网页与仓库适配器不重复实现分块、向量写入或代次切换；这些职责继续归 `LocalIngestionService`。
- 网页 URL 与仓库相对路径必须保留在资料记录中，确保现有搜索结果可准确展示出处。

## 步骤 1 实施结果

- `WebCrawler` 使用同源 BFS，只有 robots 允许且为 HTML 的页面才会被提取；跨域链接与重定向不会产生页面。
- URL 规范化会去除片段、折叠默认端口并拒绝非 HTTP(S) 或含凭据 URL。
- `RobotsPolicy` 缓存 robots 规则；无法获得规则即拒绝抓取。
- `uv run pytest tests/unit/web`：6 passed。

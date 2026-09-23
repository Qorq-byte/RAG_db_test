# Findings: 桌面端实际体验与交互完善

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

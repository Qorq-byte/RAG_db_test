# 网页与公开 GitHub 仓库导入设计

## 目标与范围

为 `ragdb` 增加受边界约束的 `crawl` 与 `repo` 导入命令，并复用已有的资料、分块和索引流水线。网页资料以原始 URL 为稳定标识；仓库内每个合格文件以仓库 HTTPS URL 与相对路径为稳定标识。

本里程碑仅支持公开 GitHub HTTPS 仓库和静态网页内容；不支持私有仓库认证、任意 Git 地址、JavaScript 渲染、登录态网页或 OCR。

## 已选方案

网页导入实现为独立基础设施模块：使用 HTTPX 获取网页、Trafilatura 提取正文，并在请求前检查 `robots.txt`。抓取器从起始 URL 作同域广度优先遍历，规范化 URL、去除片段、按配置限制深度和页面数、在请求间按速率限流，并为每个请求设置超时。重定向后的最终地址若跨域则拒绝导入。

公开仓库导入通过系统 `git` 以浅克隆方式获取。仅接受 `https://github.com/<owner>/<repository>[.git]`，临时副本保存于 `.data/cache/repos/`。遍历时复用现有允许的扩展名和忽略目录，并额外排除二进制及超过大小上限的文件。

## 架构与数据流

```text
ragdb crawl URL / ragdb repo URL
  -> CLI 校验集合和输入
  -> WebCrawler / PublicGitHubImporter
  -> LocalIngestionService
  -> Source、Chunk、SQLite FTS、ChromaDB
```

`WebCrawler` 返回已提取页面的 URL、标题和正文；应用服务为每个页面创建 `SourceType.WEB` 的 `Document`，并沿用本地导入服务的代次发布和失败回滚机制。`PublicGitHubImporter` 返回临时克隆目录和仓库规范 URL；每个可导入文件交给本地导入服务，资料元数据带有仓库 URL 和相对路径，保证代码位置可追溯。

网页或文件的单项失败会被记录在批次结果中，其他项继续处理。无变化的网页内容或仓库文件沿用现有内容哈希跳过逻辑。

## 安全与错误处理

- 在任何目标页请求前检查并遵守对应域名的 `robots.txt`；robots 获取失败时拒绝抓取。
- 仅遍历起始 URL 的 scheme、host 与端口；忽略非 HTTP(S)、片段链接和跨域链接。
- 严格执行 `max_depth`、`max_pages`、`requests_per_second` 与 `timeout_seconds`，且不会因单页异常突破限制。
- 仓库地址必须是公开 GitHub HTTPS 规范地址；克隆命令不接受用户提供的额外 Git 参数。
- 临时仓库路径由应用配置生成，清理只针对本次创建的明确目录。
- 外部进程、网络与解析异常转换为可读的 `RagdbError`，不泄露环境变量或凭据。

## CLI 与配置

`ragdb crawl URL --collection NAME` 使用既有 `[crawl]` 配置。`ragdb repo URL --collection NAME` 使用相同的单文件大小限制和 `.data/cache/repos` 缓存目录。初始版本不增加可能绕过安全边界的命令行覆盖项。

输出逐项导入状态及新增、更新、跳过、失败汇总；结果资料保留 URL 或仓库相对路径，供现有 `search` 和 `source show` 展示。

## 验证与提交边界

1. 网页基础设施：本地 HTTP 测试服务器覆盖 robots、同域限制、深度、页面数、规范化和正文提取。
2. 网页命令与导入：集成测试覆盖页面创建、内容更新、跳过和单页失败隔离。
3. 仓库导入：本地 Git 夹具覆盖 URL 校验、浅克隆、路径保留、过滤和重复导入。

每一步测试通过后独立提交并推送至 `origin/main`；最终运行完整 `uv run pytest`。

# 网页与公开 GitHub 仓库导入实施计划

> 设计依据：[网页与公开 GitHub 仓库导入设计](../specs/2026-09-21-web-github-import-design.md)。
>
> 提交策略：每个步骤完成、测试通过后，单独提交并推送至 `origin/main`；后续步骤的代码不得混入当前提交。

## 步骤 1：受限网页抓取基础设施

### 修改范围

- 在 `pyproject.toml` 和 `uv.lock` 中加入 HTTPX 与 Trafilatura。
- 新增 `src/ragdb/infrastructure/web/robots.py`：获取、缓存并解析 `robots.txt`；获取或解析失败时拒绝抓取。
- 新增 `src/ragdb/infrastructure/web/crawler.py`：规范化 HTTP(S) URL、同源校验、重定向后复检、按 BFS 遍历、去重、深度/页面数/速率/超时限制。
- 新增 `src/ragdb/infrastructure/web/extractor.py`：将 HTML 提取为有标题和正文的标准页面对象；无法提取正文时返回可读失败。
- 新增 `src/ragdb/infrastructure/web/__init__.py` 与 `tests/unit/web/`，使用可控假 HTTP 客户端或本地 HTTP 服务器，不访问公网。

### 验收与测试

- 验证 URL 去片段、相对链接解析和同源定义。
- 验证 robots 拒绝、robots 获取失败、跨域链接、跨域重定向均不产生导入页面。
- 验证深度、页面数和访问速率不会被超出。
- 验证 HTML 标题和正文被提取，空正文有明确错误。

```powershell
uv run pytest tests/unit/web
```

### 提交边界

`feat: add bounded web crawler`

## 步骤 2：网页导入应用服务与 CLI

### 修改范围

- 扩展 `LocalIngestionService` 或新增小型网页导入服务，以 `SourceType.WEB`、网页 URL、标题和提取正文创建资料，并复用 `_parse_and_store` 的代次发布逻辑。
- 修改 `src/ragdb/cli.py` 的 `crawl` 命令：构建抓取器和导入服务、校验集合、逐页输出 `IngestionResult`，并在结束时输出聚合统计。
- 新增 `tests/integration/web/test_crawl.py` 和 CLI 测试，使用本地 HTTP 服务与测试嵌入提供者。

### 验收与测试

- 验证一个网页被以 `web` 资料导入，搜索/资料记录保留 URL、标题和正文。
- 验证正文不变时跳过，内容变化时创建新代次。
- 验证一个页面失败不会阻止其他允许页面的导入，批次汇总准确。
- 验证 CLI 的未找到集合、参数和抓取错误采用既有退出码与中文错误风格。

```powershell
uv run pytest tests/unit/web tests/integration/web tests/unit/test_cli.py
```

### 提交边界

`feat: import crawled web pages`

## 步骤 3：公开 GitHub 仓库导入

### 修改范围

- 新增 `src/ragdb/infrastructure/github/filters.py`：严格验证公开 GitHub HTTPS 地址、标准化 `.git` 后缀，并判断合格文本/代码文件。
- 新增 `src/ragdb/infrastructure/github/importer.py`：调用固定参数的系统 Git 浅克隆、在 `.data/cache/repos/` 下创建唯一临时目录、遍历合格文件并生成仓库 URL/相对路径元数据。
- 修改 `src/ragdb/cli.py` 的 `repo` 命令，复用本地文件导入；在每个文件导入时附加只读仓库来源元数据。
- 新增 `tests/integration/github/test_public_repo_import.py` 与必要 CLI 测试，测试中建立本地裸 Git 仓库并模拟克隆入口，不触网。

### 验收与测试

- 验证非 GitHub、非 HTTPS、带凭据或带额外路径的地址被拒绝。
- 验证只执行固定 Git 参数的浅克隆，并使用受控缓存路径。
- 验证 `.git`、依赖/构建目录、二进制和超大文件被跳过；合格文件保留仓库相对路径、语言/位置元数据。
- 验证重复导入会跳过未变文件，单文件失败不终止仓库批次。

```powershell
uv run pytest tests/integration/github tests/unit/test_cli.py
uv run pytest
uv run python -m ragdb crawl --help
uv run python -m ragdb repo --help
```

### 提交边界

`feat: import public GitHub repositories`

## 完成条件

- 三个步骤各自拥有通过的定向测试和已推送提交。
- 完整 `uv run pytest` 通过。
- `crawl` 与 `repo` 不再是占位命令；工作树干净。
- `task_plan.md`、`findings.md` 和 `progress.md` 记录提交号与验证结果。

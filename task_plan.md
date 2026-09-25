# Task Plan: 桌面端模型设置

## Goal

实现桌面端问答/生成模型和嵌入模型可视化配置，并为所有集合提供安全的嵌入向量重建与切换。

## Current Phase

第五阶段进行中：5.1 使用指南和 5.2 自动化验收已完成并推送；按用户新指定的模型，Ollama 嵌入后端与桌面配置已实现并真实联调通过，增量全量回归 206 passed；`deepseek-flash` 问答/生成仍待服务地址与本机凭据完成真实联调。

截至 2026-09-25，阶段 4 已进入 `main`。阶段 5 在 `codex/desktop-model-settings-acceptance` 分支逐步交付；详见 [验收记录](docs/acceptance/2026-09-25-desktop-model-settings.md)。

文档入口：[详细实施计划](docs/superpowers/plans/2026-09-24-desktop-model-settings-implementation.md) · [交付记录](progress.md) · [技术发现](findings.md)。历史测试结果仅代表当时的验证范围。

## Current Decisions

| Decision | Rationale |
| --- | --- |
| 独立设置页 | 问答/生成与嵌入模型是不同用途，分区展示便于用户理解。 |
| 指纹隔离向量命名空间 | Chroma 单集合向量维度固定，重建阶段必须隔离新旧维度。 |
| SQLite 活动 profile 为准 | 索引切换与配置文件写入无法跨存储事务化；活动状态必须有单一权威源。 |
| 每阶段推送 | 用户明确要求每完成一步就上传 GitHub；阶段 5 工作分支为 `codex/desktop-model-settings-acceptance`。 |

## Phases

| Phase | Status | Outcome |
| --- | --- | --- |
| 0. 设计与计划 | complete | 规格 `be70c06` 已推送；详细实施计划已建立。 |
| 1. 模型设置服务与凭据 | complete | `413ca63`：TOML 保留式保存、系统 keyring 凭据、模型连接测试与 Ollama 枚举；最终交付记录为 18 项定向测试通过。 |
| 2. 活动嵌入索引及命名空间 | complete | schema v4、SQLite 活动 profile、legacy 命名空间兼容与版本隔离接入 runtime；全量 163 项测试通过。 |
| 3. 全集合安全重建 | complete | 当前代次跨来源重建、原子发布、取消/故障回滚、跨进程门禁及重启恢复；全量 178 项测试通过。 |
| 4. 桌面设置页面 | complete | 本地/云端配置、凭据保护、外部覆盖提示、后台测试、重建取消和失败重试；198 项测试通过。 |
| 5. 文档与最终验收 | in progress | 使用指南和 198 项自动化回归通过；真实本地嵌入通过，聊天/云端项目待验证。 |

## 下一阶段执行清单

- [x] 5.1 使用文档：README 和配置示例已更新；提交 `7cea17f` 已推送。
- [x] 5.2 自动化验收：198 passed，CLI 帮助、受控桌面启动和 Windows 原生渲染完成；提交 `ac159b6` 已推送。
- [ ] 5.3 真实服务联调：Sentence Transformers 与 Ollama 嵌入切换、检索通过；`deepseek-flash` 问答/生成待服务地址及本机凭据，云端嵌入不再属于用户选定模型。
- [ ] 5.4 最终完成判定：已整理证据与限制；须待 5.3 全部通过，或用户明确接受待验证项，才可将阶段 5 标为完成。合并主线另按用户指令执行。

详细步骤和完成标准见实施计划第 5 节，实际结果见[验收记录](docs/acceptance/2026-09-25-desktop-model-settings.md)。

## 历史记录：模型设置前的项目健康检查

以下为模型设置开发前的快照；其中 HEAD、测试数和同步状态不是当前状态。

| Phase | Status | Outcome |
| --- | --- | --- |
| 1. 基线与工作区核验 | complete | 完整功能路线已交付；HEAD 为 `83d5da1`，比 `origin/main` 超前一项文档收尾提交。 |
| 2. 回归与启动检查 | complete | `uv run pytest -q`：152 passed；`uv run ragdb --help`：成功。桌面交互已包含在全量测试中。 |
| 3. 结果处置与交接 | complete | 未发现项目回归；保留用户已有工作区改动，未改动产品代码。 |

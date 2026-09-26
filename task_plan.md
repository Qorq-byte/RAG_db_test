# 项目进度总览与下一阶段

## 项目目标

提供可导入本地文件、网页和公开 GitHub 仓库的个人知识库，支持检索、问答、学习内容生成及桌面管理；模型设置和向量重建须保护现有索引。

## 当前进度（2026-09-26）

第一期知识库的八个里程碑及后续问答、学习产物、桌面工作台、模型设置均已完成。最近交付是桌面模型设置阶段 1–5：本地 Ollama `embeddinggemma:latest` 嵌入与 DeepSeek `deepseek-flash` 问答/学习生成在隔离合成集合中通过真实联调；系统凭据和重启恢复通过。合并前完整回归 **216 passed**，`ragdb doctor` 退出码 0。

上述功能已进入 GitHub `main`；阶段 5 合并为 `5efca40`。阶段 6 开发与验收已完成：最终全量回归 **249 passed**，实际 CLI、Windows 桌面流程与 `ragdb doctor` 通过。产品步骤已推送 `codex/vector-index-maintenance`，文档归档后合并主线；Chroma 间歇性读取限制见[阶段 6 验收](docs/acceptance/2026-09-26-vector-index-maintenance.md)。

文档入口：[下一阶段详细计划](docs/superpowers/plans/2026-09-25-vector-index-maintenance-implementation.md) · [模型设置验收](docs/acceptance/2026-09-25-desktop-model-settings.md) · [上阶段实施计划](docs/superpowers/plans/2026-09-24-desktop-model-settings-implementation.md) · [交付记录](progress.md) · [技术发现](findings.md)。历史测试结果仅代表当时的验证范围。

## 已确定的技术边界

| Decision | Rationale |
| --- | --- |
| 独立设置页 | 问答/生成与嵌入模型是不同用途，分区展示便于用户理解。 |
| 指纹隔离向量命名空间 | Chroma 单集合向量维度固定，重建阶段必须隔离新旧维度。 |
| SQLite 活动 profile 为准 | 索引切换与配置文件写入无法跨存储事务化；活动状态必须有单一权威源。 |
| 每步推送并合并 | 已完成步骤分别提交推送，阶段完成后合并 GitHub `main`；不纳入用户已有的工作区改动。 |

## 已完成阶段

| Phase | Status | Outcome |
| --- | --- | --- |
| 0. 设计与计划 | complete | 规格 `be70c06` 已推送；详细实施计划已建立。 |
| 1. 模型设置服务与凭据 | complete | `413ca63`：TOML 保留式保存、系统 keyring 凭据、模型连接测试与 Ollama 枚举；最终交付记录为 18 项定向测试通过。 |
| 2. 活动嵌入索引及命名空间 | complete | schema v4、SQLite 活动 profile、legacy 命名空间兼容与版本隔离接入 runtime；全量 163 项测试通过。 |
| 3. 全集合安全重建 | complete | 当前代次跨来源重建、原子发布、取消/故障回滚、跨进程门禁及重启恢复；全量 178 项测试通过。 |
| 4. 桌面设置页面 | complete | 本地/云端配置、凭据保护、外部覆盖提示、后台测试、重建取消和失败重试；198 项测试通过。 |
| 5. 文档与最终验收 | complete | 使用指南、216 项最终回归、Ollama 与 DeepSeek 真实联调和系统凭据恢复通过。 |

## 已完成：旧向量索引显式清理（阶段 6）

模型设置设计要求在新索引发布后保留旧 Chroma 命名空间。阶段 6 实现**只读盘点与预览、确认后清理、活动索引保护、故障后重试**；安全边界见[维护设计](docs/superpowers/specs/2026-09-25-vector-index-maintenance-design.md)。所有验证使用隔离合成资料。

本阶段已完成以下步骤；交付与完成标准见[详细计划](docs/superpowers/plans/2026-09-25-vector-index-maintenance-implementation.md)。

- [x] 6.1 安全边界与只读盘点：16 项定向测试通过。
- [x] 6.2 CLI 与桌面的显式预览入口：22 项定向测试通过。
- [x] 6.3 受保护的清理执行、故障恢复与重试：47 项定向测试通过。
- [x] 6.4 隔离数据回归、使用说明与最终验收：249 项全量测试通过，CLI 与原生桌面流程通过，README 和验收记录已整理。

## 上一阶段完成清单

- [x] 5.1 使用文档：README 和配置示例已更新；提交 `7cea17f` 已推送。
- [x] 5.2 自动化验收：198 passed，CLI 帮助、受控桌面启动和 Windows 原生渲染完成；提交 `ac159b6` 已推送。
- [x] 5.3 真实服务联调：Sentence Transformers 与 Ollama 嵌入切换、检索通过；`deepseek-flash` 问答/学习生成、系统凭据与重启恢复通过。云端嵌入不属于用户最终选定模型。
- [x] 5.4 最终完成判定：已整理证据；216 项回归与 `ragdb doctor` 通过。合并前修正 `023496a` 与最终验收 `cd7e169` 分别推送后，已按用户指令合并主线并推送（`5efca40`）。

详细步骤和完成标准见实施计划第 5 节，实际结果见[验收记录](docs/acceptance/2026-09-25-desktop-model-settings.md)。

## 历史记录：模型设置前的项目健康检查

以下为模型设置开发前的快照；其中 HEAD、测试数和同步状态不是当前状态。

| Phase | Status | Outcome |
| --- | --- | --- |
| 1. 基线与工作区核验 | complete | 完整功能路线已交付；HEAD 为 `83d5da1`，比 `origin/main` 超前一项文档收尾提交。 |
| 2. 回归与启动检查 | complete | `uv run pytest -q`：152 passed；`uv run ragdb --help`：成功。桌面交互已包含在全量测试中。 |
| 3. 结果处置与交接 | complete | 未发现项目回归；保留用户已有工作区改动，未改动产品代码。 |

# Task Plan: 桌面端模型设置

## Goal

实现桌面端问答/生成模型和嵌入模型可视化配置，并为所有集合提供安全的嵌入向量重建与切换。

## Current Phase

第三阶段（全集合安全嵌入重建）已完成，全量 178 项测试通过；下一阶段为桌面模型设置页面。

## Current Decisions

| Decision | Rationale |
| --- | --- |
| 独立设置页 | 问答/生成与嵌入模型是不同用途，分区展示便于用户理解。 |
| 指纹隔离向量命名空间 | Chroma 单集合向量维度固定，重建阶段必须隔离新旧维度。 |
| SQLite 活动 profile 为准 | 索引切换与配置文件写入无法跨存储事务化；活动状态必须有单一权威源。 |
| 每阶段推送 | 用户明确要求每完成一步就上传 GitHub；工作分支为 `codex/desktop-model-settings`。 |

## Phases

| Phase | Status | Outcome |
| --- | --- | --- |
| 0. 设计与计划 | complete | 规格 `be70c06` 已推送；详细实施计划已建立。 |
| 1. 模型设置服务与凭据 | complete | 增加 TOML 保留式保存、系统 keyring 凭据、模型连接测试与 Ollama 枚举；20 项定向测试通过。 |
| 2. 活动嵌入索引及命名空间 | complete | schema v4、SQLite 活动 profile、legacy 命名空间兼容与版本隔离接入 runtime；全量 163 项测试通过。 |
| 3. 全集合安全重建 | complete | 当前代次跨来源重建、原子发布、取消/故障回滚、跨进程门禁及重启恢复；全量 178 项测试通过。 |
| 4. 桌面设置页面 | pending | 设置表单、覆盖提示、后台测试与运行时更新。 |
| 5. UI 集成与最终验收 | pending | 交互、文档、完整验证；提交推送。 |

## Phases

| Phase | Status | Outcome |
| --- | --- | --- |
| 1. 基线与工作区核验 | complete | 完整功能路线已交付；HEAD 为 `83d5da1`，比 `origin/main` 超前一项文档收尾提交。 |
| 2. 回归与启动检查 | complete | `uv run pytest -q`：152 passed；`uv run ragdb --help`：成功。桌面交互已包含在全量测试中。 |
| 3. 结果处置与交接 | complete | 未发现项目回归；保留用户已有工作区改动，未改动产品代码。 |

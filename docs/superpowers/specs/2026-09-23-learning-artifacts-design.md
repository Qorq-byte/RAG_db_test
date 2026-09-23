# 第二阶段：学习内容生成设计

## 目标

在已完成的检索增强问答之上，生成并持久化五类学习产物：摘要、提纲、学习笔记、练习题和知识卡片。所有事实只能依据当前集合内检索到的资料，并保留稳定来源快照。

## 范围与边界

输入为集合、生成类型、主题，以及可选资料 ID 和现有检索筛选。首版不支持直接汇总整个集合、用户自定义提示词、流式输出或桌面界面。无检索证据时不调用模型。

## 架构

`GenerationService` 复用 `SearchService`、`ChatModel` 和既有模型配置。它依据生成类型选择固定中文模板，将排序后的证据编号为 `[1]`、`[2]`，调用模型后校验输出并持久化。五类产物共享检索、引用、错误处理和存储；模板是唯一的类型差异。

摘要、提纲和笔记返回 Markdown 文本。练习题和卡片要求模型返回固定 JSON，服务端解析、验证题干/答案或正反面非空后渲染为 Markdown；格式错误时不写入产物。

## 数据与来源追溯

SQLite schema 增加 `learning_artifacts`（ID、集合、类型、标题、正文、provider/model、创建时间）和 `artifact_citations`（产物 ID、显示序号、切片与资料标识、资料代次、标题、URI、位置快照）。删除集合时级联删除产物和引用；资料更新或删除不改变历史快照。

## CLI

```text
ragdb generate summary|outline|notes|quiz|cards "主题" --collection <name> [--source-id <uuid>]
ragdb artifact list --collection <name>
ragdb artifact show <uuid> --collection <name>
ragdb artifact delete <uuid> --collection <name> --yes
```

输出显示产物 ID、正文与来源映射。类型、资料和集合校验失败、模型调用失败或 JSON 格式不合法时以中文可操作错误终止，且不创建半成品记录。

## 验收

- 各类型模板、证据编号、空检索拒答、集合/资料隔离与模型错误不留产物。
- SQLite 迁移、产物/引用快照、级联删除与 CRUD。
- 练习题和卡片 JSON 的成功与失败校验。
- CLI 生成、列表、查看、删除、来源输出与全量回归。
- 每个可验证步骤单独测试、提交并推送 GitHub。

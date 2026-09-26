# 桌面液体按钮与主题图标验收

用户参考：`前端设计/按钮.txt`。用 PySide6 原生绘制移植靛蓝主体、四处液体延伸和错峰下落液滴；没有引入 WebView 或 React。

- 按钮周边 18px 内触发，离开停止并清除绘制层。空闲时定时器停止。
- 四处滴落位于 10% / 30% / 57% / 85%，高度 24 / 20 / 10 / 16px，延迟 0.5 / 3 / 4.25 / 1.5s。循环 2s 动效、2s 间隔。
- 绘制层不接收鼠标事件，避让相邻按钮和文字；禁用、隐藏、失去窗口激活及减少动效时停止。保留原按钮点击和键盘语义。危险操作保留红色；侧栏导航保留随机指示线。
- 顶部太阳、月亮、显示器分别对应浅色、深色、跟随系统，保留选中状态、中文提示、可访问名称和偏好持久化。
- 原生 Windows 截图验证发现兄弟控件 mapTo 坐标偏差，已改为经过全局坐标映射；确认实际液滴可见。预览位于本地 `.data/button-preview/`，不提交生成文件。

定向桌面回归：62 passed in 79.87s（坐标映射修正前）；修正后专项 11 passed in 3.07s。

全量：335 passed、1 failed in 360.52s。失败用例 `tests/integration/test_embedding_rebuild.py::test_rebuild_switches_all_source_types_after_complete_verification` 再现已记录的 Chroma `Nothing found on disk`；独立复测 1 passed in 2.38s。没有修改存储逻辑，也不宣称底层问题已解决。

实现 `7d28177` 与验收记录 `496fe82` 已推送至 `https://github.com/Qorq-byte/RAG_db_test.git` 的 `codex/desktop-welcome` 分支。首次推送曾被自动审批拒绝；用户明确确认目的仓库与分支后，推送成功。尚未合并 main。

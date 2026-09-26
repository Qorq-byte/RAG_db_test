# 桌面主题切换与导航随机线条修复

## 根因与修复

Windows 原生窗口通过真实主题下拉框复现：QComboBox 的 QVariant 将 ThemeMode（StrEnum）转为普通 str；set_mode 读取 mode.value 抛出 AttributeError，三个选项都没有应用样式。此前测试直接传枚举，遗漏真实下拉框边界。

现在在 ThemeManager.set_mode 统一转回 ThemeMode，再保存并应用。主题同时更新 QPalette 和样式表，原生控件、背景与文本采用一致的色板。“跟随系统”从 QStyleHints.colorScheme 获取系统配色并监听 colorSchemeChanged，不再根据应用自己的调色板反推；手动深浅色不受系统事件覆盖，切回跟随系统时使用最新系统状态。

系统通知只允许当前负责应用配色的 ThemeManager 更新全局样式；旧窗口或测试实例仍可记录系统状态，但不能覆盖当前手动主题。

导航线条从橙、绿、紫、红等六组非蓝色配色随机选择，点击选中时更换，同一项连续点击不重复前一颜色；绘制本身不重新随机。深浅主题采用对应的可读颜色。

## 证据

- 最终全量回归：`.venv/Scripts/python.exe -m pytest -q`，**325 passed in 202.96s**。

- 修复前下拉框三个选项均抛出 `'str' object has no attribute 'value'`，采样背景恒为 `#f3f3f3`。
- 修复后 Windows 原生下拉框浅色背景 `#f6f7f9`、深色 `#101419`、跟随系统在当前浅色 Windows 下为 `#f6f7f9`，无异常。已查看 `.data/theme-preview/after-light.png` / `after-dark.png`。
- 定向回归 **33 passed in 11.63s**：真实下拉框切换与保存、实际渲染背景像素、系统深浅配色信号模拟、手动主题不被覆盖、重复点击换色、重绘不换色、侧边栏轮播及已有桌面功能。
- 系统实时变化通过 Qt 的 colorSchemeChanged 信号测试模拟；没有修改用户 Windows 个性化设置。

## 全量中发现的问题

首次全量为 322 passed / 2 failed：一项重现历史 Chroma 微型索引 `Nothing found on disk`，另一项发现旧 ThemeManager 接收系统通知后覆盖当前手动主题。后者已以 `208169f` 修复并增加明确的双实例回归测试；失败的索引项与四项主题测试独立复测 **5 passed in 3.27s**。索引代码没有改动，单次复测通过不表示历史间歇性限制已根治。

## 交付

修复以 `46c582f` 推送 `codex/desktop-welcome`。用户已有 CLI 测试修改和设计草稿不纳入提交；不修改欢迎页参考要求的固定浅色画布。

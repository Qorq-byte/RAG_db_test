# 永久注销账号

桌面端“个人菜单 → 设置 → 永久注销账号并删除本机资料”要求用户先向当前登录邮箱发送新验证码，再输入完整验证码和“永久删除”。客户端使用当前登录会话请求 Supabase Edge Function；函数在服务端核验该会话及邮箱验证码属于同一账号，然后调用 Supabase 管理端删除账号。服务端密钥只在 Edge Function 环境中使用，不放入桌面程序、配置文件或仓库。

函数源码位于 `supabase/functions/delete-account/index.ts`。部署时在 Supabase 项目中保持 **JWT 验证开启**，函数名必须为 `delete-account`。可使用 Supabase Dashboard 的 Edge Functions 编辑器，或在管理员已登录的环境执行：

```powershell
supabase functions deploy delete-account --project-ref hzzsuckwnpvknrmynghm
```

函数部署前，桌面端会明确显示“账号删除服务尚未部署”，且不会删除本机资料。函数返回确认后，桌面端先关闭工作台，再删除 `<storage.data_dir>/accounts/<账号 UUID>/`。若本机文件清理失败，服务端账号已无法恢复，程序会提示手工检查该账号目录。其他账号目录和旧版未归属账号的资料保持不变。注销前请自行备份需要保留的资料。

2026-10-01 已使用真实测试账号验证完整流程：注销验证码投递成功，桌面端完成确认后返回登录页；系统凭据库中的会话无法恢复，本机账号目录已清空；Supabase `auth.users` 的只读查询确认该测试账号已不存在。此项真实邮箱验证针对源码运行的桌面端；v0.2.0 安装包另有隔离启动和自检验收，不把安装包验证写成第二次真实账号注销测试。

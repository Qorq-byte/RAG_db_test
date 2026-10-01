# 邮箱验证码确认注册

## 目标

保持邮箱加密码注册及“验证邮箱后才能登录”的规则，把点击邮件确认链接改为在 RAG DB 中输入邮件中的完整数字验证码。验证码位数取决于 Supabase 项目配置。邮件与认证请求仍需网络，但确认过程不再依赖浏览器跳转。

## 流程与边界

1. 用户在桌面端或 `ragdb auth register <邮箱>` 提交邮箱和密码。Supabase 继续发送注册确认邮件；管理员将 Supabase **Confirm sign up** 邮件模板改为显示 `{{ .Token }}`，不提供必须点击的确认链接。
2. 用户在桌面端输入验证码，或运行 `ragdb auth verify <邮箱>` 并在终端隐蔽输入验证码。客户端以邮箱、完整验证码及 `type=email` 调用 Supabase Auth `verify` 接口；仅接受有界长度的 ASCII 数字，准确位数由服务端判断。验证成功后检查服务端返回的已确认账号，清除该验证请求产生的会话，再提示用户用密码登录。验证步骤不打开知识库，也不保存刷新令牌。
3. 验证码过期或未收到时，桌面端和 `ragdb auth resend <邮箱>` 调用 Supabase `resend` 接口，类型为 `signup`。服务端限流与错误需给出可理解的提示；不在日志中记录验证码、密码或会话令牌。
4. 登录、会话恢复和按账号隔离本机数据的现有规则保持不变。安装包须等邮件投递与完整注册登录流程验收后，按用户单独授权更新。

## 验收

- 单元测试覆盖验证码格式、成功验证后仍未登录、错误或过期验证码、重发请求及界面状态。
- 桌面和 CLI 各完成一次注册到登录的实际流程；至少使用一个非 Supabase 组织成员邮箱验证 QQ SMTP 投递。
- 公开仓库只包含模板操作说明和代码，不包含项目密钥以外的任何私密凭据；本机 `.env` 继续被 Git 忽略。

依据：[Supabase 邮件模板](https://supabase.com/docs/guides/auth/auth-email-templates)、[verifyOtp](https://supabase.com/docs/reference/javascript/auth-verifyotp)、[resend](https://supabase.com/docs/reference/javascript/auth-resend)。

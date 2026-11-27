# Desktop plugin submission / 桌面插件提交

## 当前状态

`0.1.0-preview.1` 是面向公共插件目录的桌面提交候选包，不代表已上架。2026-11-27 在实际发布后台点击上传后，平台要求先完成开发者身份验证，因而尚未上传、提交审核或发布。

技能需要本地程序执行，在 `plugin/plugin.json` 的 `extensions.com.openai.requires_local_executor` 声明为 `true`。包中不含 MCP 服务、其他 app 引用或生命周期 hooks。邮箱使用宿主另行授权的连接器，不创建新的 Gmail 中转服务。

## 提交流程

1. 在 [组织设置](https://platform.openai.com/settings/organization/general) 完成个人或企业身份验证；由发布者本人选择身份并提供验证资料。组织所有者或具有 Apps Management Write 权限的成员执行提交。
2. 从技能仓库根运行 `python3 scripts/package_plugin.py --output <源码外的新目录>`；在 FotoNest 主仓库中先进入 `tools/skills/travel-records/`。该命令仅打包现有技能资源，不编译 App。
3. 检查生成 ZIP 内的完整资源、校验和、桌面执行标志、隐私链接与能力说明。私有 marketplace 目录用于本地测试；提交 ZIP 内不需要包含它。
4. 在 [插件后台](https://platform.openai.com/plugins) 上传 ZIP。查看自动元数据及技能扫描结果，修正实际阻塞后重新上传。当前仅技能包按平台要求填写，不虚构 MCP 凭证、工具测试或演示录像。
5. 核实发布者身份和展示名称一致。真实完成干净环境安装与主要流程验证后，提交审核。涉及条款或政策承诺时由发布者确认。
6. 审核批准后发布，并验证实际目录页面与安装入口。只有此时才能把介绍中的状态改为已上架。

年度结果仍以指定邮件年份为边界，已发现资料处理完毕不证明找回所有行程。网页、手机、无人值守续跑和正式 FotoNest 导入不得列为已验收能力。

## English

`0.1.0-preview.1` is a desktop directory submission candidate, not a published listing. On 2026-11-27, the actual portal blocked upload pending developer identity verification. No upload, review submission or directory publication was completed.

The manifest declares `extensions.com.openai.requires_local_executor: true`. There is no MCP server, app-reference configuration or lifecycle hook. Mail access uses the host's separately authorized connector.

The publisher must complete individual or business verification and hold submission access. Run `scripts/package_plugin.py` from the skill repository into a new directory outside its source, check the complete generated ZIP and its declared resources, then upload it at the plugin portal. The generated local marketplace is for desktop testing and is not part of the submission ZIP. Resolve actual automated findings, confirm the publishing identity, validate clean installation and main workflows, and submit for review. Any binding terms or policy attestations require the publisher's confirmation. Publish only after approval, then verify the real listing and installation route before changing availability claims.

Keep annual mail-year boundaries and current platform limitations explicit. Do not equate processing all discovered evidence with finding every trip.

## Official references / 官方参考

- [Desktop-only skills and the local executor flag](https://developers.openai.com/plugins/deploy/desktop-only#plugins-without-an-mcp-server)
- [Identity, upload, review and publication](https://developers.openai.com/plugins/deploy/submission)

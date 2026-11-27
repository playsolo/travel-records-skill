# Travel Records desktop distribution

This branch contains generated installable artifacts, not a separately maintained implementation. Source, privacy and support: [main branch](https://github.com/playsolo/travel-records-skill/tree/main).

## 安装

在支持 Git 插件市场的桌面客户端中添加市场，Source 填写 `https://github.com/playsolo/travel-records-skill.git`，Git ref 填写 `desktop-plugin`，Sparse paths 留空。选择 **fotonest-travel** 来源，安装 **Travel Records**。

已有支持插件的 Codex CLI 时：

```bash
codex plugin marketplace add playsolo/travel-records-skill --ref desktop-plugin
codex plugin add travel-records@fotonest-travel
```

运行首次设置，确认本地 Python 3.9+、jsonschema 和私有工作区可用，单独授权 Gmail，再新建会话核对一段已知行程。也可提供文件。不需要用户自行打包。

这是 GitHub 市场分发，不是 OpenAI 公共目录上架。仅供支持本地执行的桌面环境；网页、手机及无人值守续跑未验收。客户端和组织策略可能限制添加市场。插件安装不会自动连接 Gmail。普通清单无需 FotoNest，FotoNest v1 导入当前仅支持 Debug 构建。

## Installation

In a Git-marketplace-capable desktop client, add the repository URL above with Git ref `desktop-plugin`, leaving Sparse paths blank. Choose **fotonest-travel** and install **Travel Records**, or run the CLI commands above. Run setup, separately authorize Gmail, and start a new chat with a known trip. You can supply documents instead of connecting mail.

The plugin requires local Python 3.9+, jsonschema and a writable private workspace. Users do not package the source. This Git distribution is separate from OpenAI's public directory; client and organization policies still apply. Web, mobile and unattended continuation remain unverified. FotoNest is optional; its v1 import currently requires a Debug build.

## Regeneration

From the canonical source, run `python3 scripts/package_plugin.py --output <new-directory-outside-source> --marketplace-name fotonest-travel`. Publish the generated `.agents/` and `plugins/` trees. Do not edit runtime files directly on this branch. See `distribution.json` for source provenance and the plugin `checksums.json` for resource hashes.

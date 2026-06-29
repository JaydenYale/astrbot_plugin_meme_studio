# Meme Studio 表情工作台

一个面向 AstrBot 的 QQ 头像表情包制作插件。它可以把群友头像、消息图片或自定义素材合成为静态 PNG 与动态 GIF，并提供一个本地浏览器版 Meme Studio，用拖拽的方式制作新模板。

![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.12.0-2f80ed)
![Python](https://img.shields.io/badge/Python-3.8%2B-3776ab)
![Image](https://img.shields.io/badge/Image-Pillow%20%7C%20OpenCV-f4b400)
![Status](https://img.shields.io/badge/Status-Audit%20Ready-brightgreen)

## 亮点

- 内置多种 QQ 头像表情模板，覆盖静态图、GIF 动图、单人头像和双人头像场景。
- 支持 `/指令 @某人` 自动读取 QQ 头像，也支持“图片 + 指令”直接处理消息中的图片。
- 每个模板都接入 AstrBot 配置面板，管理员可以单独启用或关闭。
- 内置 Meme Studio 本地制作器，支持上传图片或 GIF、拖拽头像框、预览、导出与应用到机器人。
- GIF 分解与合成一体化：上传 GIF 后可拆成静态帧，再逐帧调整头像位置。
- 新增模板不需要手写 Python 脚本，制作器会生成 manifest、素材目录、命令配置和面板 schema。
- 对远程图片、路径、临时文件、子进程执行和输入大小都有边界控制，适合长期挂在群聊里使用。
- 仓库只提交源码和必要素材；本地可执行文件由使用者自行构建，不进入插件市场安装包。

## 安装

### 方式一：AstrBot 面板上传 zip

在项目根目录生成安装包：

```bash
python tools/package_plugin_zip.py
```

然后进入 AstrBot 管理面板的插件页面，选择“从文件安装”，上传生成的 `astrbot_plugin_meme_studio_install.zip`。安装完成后重启 AstrBot，或至少重载插件。

### 方式二：克隆到插件目录

```bash
cd /AstrBot/data/plugins
git clone https://github.com/zhajunyao/astrbot_plugin_meme_studio.git
```

然后重启 AstrBot。

## 依赖

依赖写在 `requirements.txt`：

```txt
Pillow>=10.0.0,<12.0.0
httpx>=0.24.0
numpy>=1.24.0
opencv-python-headless>=4.8.0
pil-utils>=0.1.7
meme_generator~=0.2.0
```

如果 AstrBot 环境没有自动安装依赖，可以在插件目录手动执行：

```bash
pip install -r requirements.txt
```

## 基本用法

使用群友头像：

```text
/摸 @某人
/摸头 @某人
/贴贴 @某人
```

使用消息图片：

```text
/敲
/啃
/草神啃
```

部分模板会使用发送者头像和目标头像一起合成，例如：

```text
/抱抱 @某人
/抱花 @某人
/撅 @某人
```

完整开关可以在 AstrBot 插件配置面板查看。

## meme-generator 大表情库引擎

插件保留本地内置模板和 Meme Studio 生成模板作为第一优先级：当本地模板和 generator 关键词重名时，优先执行本地/Studio 模板。`meme-generator` 是额外接入的可选大表情库引擎，用来补充更多关键词表情。

常用示例：

```text
/meme帮助
/meme详情 <关键词>
/<关键词> @用户 文本 key=value
```

默认需要 `/` 或全角 `／` 前缀，也可以通过唤醒/提及机器人触发。管理员可在配置面板调整 `generator_need_prefix`、`generator_extra_prefix`、`generator_fuzzy_match`、`generator_timeout_seconds`、`generator_compress_static` 和 `generator_disabled_list`。

如果服务器不希望启用 generator，或运行环境无法安装/加载它的依赖与资源，可以在插件配置中设置：

```text
generator_enabled=false
```

Linux 或 Docker 环境中，`meme-generator` 及其图片处理链路可能需要额外的图形和字体相关系统库，例如 fontconfig、freetype、libGL 或发行版对应的兼容包。不同镜像报错不同，建议按启动或生成时的缺库提示补齐。

本次集成参考了 `astrbot_plugin_memelite` 将 AstrBot 层与 meme 引擎分离的架构思想，但没有复制、vendored 或改写它的源码；两者许可不同，因此本项目只通过公开的 `meme-generator` 包实现自己的适配层。

## Meme Studio

Meme Studio 是本项目的本地模板编辑工具，适合用来快速扩展新表情。

启动源码版：

```bash
python tools/meme_studio.py
```

启动后浏览器会打开本地页面。需要 Windows 双击入口时，可以在本地运行下面的命令自行构建：

```bash
python tools/build_meme_studio_exe.py
```

构建得到的 `MemeStudio.exe` 只建议作为 GitHub Release 附件发布，不提交到插件源码仓库，也不放进 AstrBot 插件市场安装包。

### 最简单的新增模板流程

1. 运行 `python tools/meme_studio.py`。
2. 点击“新增表情”。
3. 填写指令名，例如 `拍脑袋`。
4. 上传一张图片或一个 GIF。
5. 拖动头像框到合适位置。
6. 点击预览检查效果。
7. 点击“应用到机器人”。
8. 重载插件或重启 AstrBot。
9. 在群里使用 `/拍脑袋 @某人`。

应用后会写入：

- `data/指令名/manifest.json`
- `data/指令名/frames/`
- `generated_meme_commands.json`
- `_conf_schema.json`

## 项目结构

```text
astrbot_plugin_meme_studio/
├─ main.py                         # AstrBot 插件入口、命令注册、头像读取、脚本调度
├─ meme_commands.py                # 内置命令和 Meme Studio 生成命令的统一注册表
├─ meme_studio_core.py             # 模板渲染、GIF 分解、manifest 处理
├─ meme_studio_launcher.py         # 本地制作器启动逻辑
├─ meme_studio/                    # 本地模板运行时、制作器服务与可选 meme-generator 适配层
│  └─ web/                         # 本地 Meme Studio 制作器前端资源
├─ generated_meme_commands.json    # Meme Studio 生成命令列表
├─ _conf_schema.json               # AstrBot 配置面板 schema
├─ data/                           # 内置素材和生成模板素材
├─ scripts/                        # 内置脚本和 manifest 渲染脚本
├─ tools/
│  ├─ meme_studio.py               # 本地制作器启动入口
│  ├─ meme_studio/
│  │  └─ server.py                 # 兼容旧路径的制作器服务 re-export
│  ├─ build_meme_studio_exe.py     # 本地构建 MemeStudio.exe
│  ├─ generate_conf_schema.py      # 重新生成配置 schema
│  └─ package_plugin_zip.py        # 生成 AstrBot 可上传安装包
├─ tests/                          # 单元测试
└─ SECURITY_REVIEW.md              # 安全边界与审核说明
```

## 安全与稳定性

这个插件默认按“长期运行在群聊环境”设计：

- 远程图片只允许 `http` / `https`，并在下载前解析主机地址，拒绝 localhost、内网、链路本地和保留地址。
- 单张输入图片限制为 25 MB，避免超大文件拖垮机器人。
- Base64 图片使用严格解码，异常输入会被拒绝。
- 表情生成在临时目录完成，任务结束后自动清理。
- 插件启动时会清理过期临时任务目录。
- 脚本路径限制在 `scripts/` 内，避免路径穿越。
- 子进程使用参数列表执行，不拼接 shell 字符串。
- 每次生成都有超时控制，异常会返回友好提示。
- Meme Studio 生成命令只接受 `data/<模板名>/manifest.json` 形式的 manifest。
- 带 token 的 Meme Studio URL 应视为 secret；推荐仅通过 localhost 或受信任的 SSH tunnel 访问，不要分享完整 URL、日志或截图，如已暴露请重启 Studio 生成新 token。
- 打包脚本会排除 `.git`、缓存、测试目录、构建目录、本地导出目录和可执行文件。

更完整的审核说明见 [SECURITY_REVIEW.md](./SECURITY_REVIEW.md)。

## 开发与验证

运行单元测试：

```bash
python -m unittest discover -v
```

检查 Python 文件能否正常编译：

```bash
python -m compileall -q .
```

检查前端脚本语法：

```bash
node --check meme_studio/web/app.js
```

生成 AstrBot 上传包：

```bash
python tools/package_plugin_zip.py
```

生成 Windows 制作器：

```bash
python tools/build_meme_studio_exe.py
```

## 插件市场信息

提交到 AstrBot 官方插件库时可使用：

```json
{
  "name": "astrbot_plugin_meme_studio",
  "display_name": "Meme Studio 表情工作台",
  "desc": "将 QQ 群友头像快速生成静态或 GIF 表情包，支持本地 Meme Studio 扩展自定义模板。",
  "author": "zhajunyao",
  "repo": "https://github.com/zhajunyao/astrbot_plugin_meme_studio",
  "tags": ["娱乐", "表情包", "图片"],
  "social_link": "https://github.com/zhajunyao"
}
```

## 发布建议

提交到 GitHub 时建议只提交源码、必要素材和脚本，不提交下面这些本地运行产物：

- `MemeStudio.exe`
- `.meme_studio_sessions/`
- `.meme_studio_previews/`
- `.ruff_cache/`
- `__pycache__/`
- `exports/`
- `build/`
- `dist/`

如果要面向普通用户发布，可以在 GitHub Release 里额外附上：

- `astrbot_plugin_meme_studio_install.zip`
- `MemeStudio.exe`，可选，仅作为本地制作器附件

## 常见问题

### 群里输入指令没有反应

先确认插件已经启用，并且 AstrBot 已经重启或重载插件。命令注册发生在插件加载阶段，如果刚刚新增模板，只保存配置是不够的。

### 新增模板后面板没有开关

点击 Meme Studio 的“应用到机器人”后会同步更新 `_conf_schema.json`。如果面板仍然没有显示，重载插件或重启 AstrBot。

### GIF 预览只显示一帧

请确认使用的是新版 Meme Studio。新版预览接口会按模板输出 GIF，而不是把 GIF 当作静态图读取。

### 安装 zip 报路径错误

不要直接用 Windows 右键压缩整个项目。请使用：

```bash
python tools/package_plugin_zip.py
```

脚本会生成 AstrBot 兼容的 zip 结构，并统一使用 `/` 作为压缩包路径分隔符。

## 贡献

欢迎提交 Issue 和 Pull Request。适合贡献的方向包括：

- 新增内置模板。
- 优化 Meme Studio 的交互体验。
- 补充更多自动化测试。
- 适配更多平台头像源。
- 改进 GIF 生成质量和性能。

新增模板时，请尽量提供清晰素材、合理的头像框位置，并保证命令名简短好记。

## 致谢

感谢 AstrBot 项目提供插件框架，也感谢每一个愿意把群聊变得更有趣的人。

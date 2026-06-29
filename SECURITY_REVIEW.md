# 安全审核说明

这份说明面向 AstrBot 插件市场审核，概述 `astrbot_plugin_meme_studio` 的主要边界控制。

## 运行边界

- 插件不执行 shell 字符串，所有模板脚本通过 `asyncio.create_subprocess_exec` 参数列表启动。
- 子进程运行目录固定为插件目录，生成超时默认 120 秒。
- 每次表情生成使用独立临时目录，结束后清理；启动时会清理过期任务目录。
- 脚本路径通过 `Path.resolve()` 和 `relative_to()` 限制在 `scripts/` 目录内。

## Meme Studio 访问令牌边界

- Meme Studio API 支持 Bearer token；静态入口资源保持无 token 可访问，旧的无鉴权启动方式在 `auth_config=None` 时仍兼容。
- 预览图由浏览器 `<img>` 加载，无法附带 `Authorization` header，因此预览图 URL 会通过 query string 携带 token；这类 token URL 只应在 localhost 或受信任隧道环境使用，避免外泄到聊天、日志、截图、浏览器历史或第三方代理。
- 如带 token 的 Studio URL 已经暴露，应重启 Studio 生成新的访问 token。

## 输入边界

- 远程图片只允许 `http` 与 `https`。
- 下载前解析目标主机，拒绝 localhost、内网、链路本地、保留地址等非公网 IP。
- 单张输入图片最大 25 MB。
- Base64 输入使用严格解码，非法 payload 会被拒绝。
- 本地文件输入同样检查大小。

## meme-generator 集成边界

- `meme-generator` 引擎通过适配层懒加载；缺依赖、目录资源不可用或 catalog 加载失败时，只会跳过 generator 请求，不影响本地内置模板和 Meme Studio 生成模板。
- generator 的图片和头像读取复用 runtime 的安全读取路径，包括 URL 协议校验、内网/保留地址阻断、单图大小限制和临时目录清理。
- 用户显式提供的图片读取失败时会中止本次 generator 生成并返回读取失败提示，不会回退成发送者头像或其它错误头像结果。
- generator 输出使用超时保护；过大的静态输出可按配置缩放，GIF 动图保持原样。
- 参考插件代码未复制、未 vendored，也没有随仓库打包外部 meme 资源；本项目仅接入公开的 `meme-generator` 包并维护自己的适配代码。

## 自定义模板边界

- Meme Studio 生成的命令名会拒绝路径字符和控制字符。
- `generated_meme_commands.json` 只接受 `data/<模板名>/manifest.json` 形式的相对 manifest 路径。
- 模板渲染时，帧素材通过安全 join 限制在 manifest 所在目录内。
- 头像区域必须包含正数宽高，旋转角必须是数字。

## 发布包边界

- 仓库不包含 `MemeStudio.exe` 等二进制可执行文件。
- 可执行文件可由用户在本地自行构建，但不会作为插件市场安装包的一部分提交。
- 打包脚本会排除 `.git`、测试、文档、构建目录、运行缓存和本地导出目录。

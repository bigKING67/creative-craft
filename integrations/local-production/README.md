# Local production MVP

可选的本地制作模块：已有视频 → 版本化工程 → 裁切/重排/字幕/音轨 → 预览 MP4 → 修改 → 导出。它是 Creative Craft 的执行工具，不包含自然语言规划器、DataHub UI、素材检索或 Seedance 调用。现有 Python CLI 和轻量 Skill 安装保持不变；本模块目前只随源码 checkout 使用，不在根 npm/Skill 发布包中。

## 安装和运行

Node.js >=22、FFmpeg/ffprobe、可用的独立 Chrome 渲染进程。固定 `@hyperframes/producer@0.8.53` 和 `gsap@3.13.0`，依赖闭包见 package-lock.json。不要在用户浏览器 Profile 上执行渲染。

```sh
cd integrations/local-production
PUPPETEER_SKIP_DOWNLOAD=true npm ci --ignore-scripts
npm run fetch-font   # 下载 fonts/manifest.json 固定的字幕字体并核对 SHA-256；二进制不入库
export PRODUCER_HEADLESS_SHELL_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
node cli.mjs --help
npm test
npm run smoke
```

Chrome 路径示例仅适用于对应 macOS 安装；其他主机指定自己的渲染 Chrome 路径。模块不会自动下载 ASR/TTS 模型或调用云端语音服务。`ffmpeg`/`ffprobe` 需在 worker 的 PATH；`CREATIVE_FFMPEG`/`CREATIVE_FFPROBE` 仅覆盖本模块校验/样例命令，不修改 HyperFrames 的二进制解析方式。

这是受信任本地用户的执行工具，不是多租户沙箱。DataHub 接入前必须另建隔离 worker、权限检查、任务队列、预算及受控素材解析。当前只接受本地普通文件；不接受 URL、任意 HTML、脚本或外部工程导入。项目路径与素材路径拒绝 symlink；macOS `/tmp`/`/var` 的系统别名需改用其真实路径。

## 创建工程

创建 `spec.json`（媒体路径相对于命令 cwd；样例要求源视频至少 5 秒）：

```json
{
  "project_id": "first-edit",
  "title": "自有素材初剪",
  "canvas": { "width": 1280, "height": 720, "fps": 24 },
  "assets": [{ "id": "take", "path": "/absolute/path/to/source.mp4" }],
  "clips": [
    {
      "id": "opening", "asset_id": "take", "in_seconds": 0,
      "frames": 48, "volume": 1, "fit": "contain",
      "captions": [{ "from": 0, "to": 2, "text": "第一句字幕" }]
    },
    {
      "id": "detail", "asset_id": "take", "in_seconds": 4,
      "frames": 24, "volume": 0.7, "fit": "cover", "captions": []
    }
  ],
  "audio": []
}
```

```sh
node cli.mjs create /absolute/new-project spec.json
node cli.mjs read /absolute/new-project
node cli.mjs preview /absolute/new-project /absolute/new-preview 1
```

创建工程会 ffprobe 输入、复制素材并记录 SHA-256，不修改源文件。工程目录必须不存在；所有素材先在 spec 中声明。片段按数组顺序连续拼接；`in_seconds` 是源媒体时间，`frames` 是成片帧数。暂不支持变速、叠加 B-roll、多视频轨、转场或自动语音分句。

字幕 `from/to` 是源媒体秒数；裁切和重排时自动截取相交范围并重定位。替换 `asset_id` 而未给出新字幕时清空旧字幕，避免把原台词贴到新素材。字幕文本 HTML 转义；同时输出 WebVTT。字体使用本机 PingFang SC / Noto Sans CJK SC 回退，跨主机字体一致性尚未保证。

独立音轨结构：`{ "id": "music", "asset_id": "music-source", "in_seconds": 0, "start_frame": 0, "frames": 72, "volume": 0.2 }`。对应素材须已导入并含音频。音轨按成片时间放置，超过片尾自动截断；不会自动 ducking/响度归一化，多个音轨叠加需要听检。

## Agent 有界编辑

先读取当前版本，再提交 `operations.json`：

```json
[
  { "type": "reorder", "clip_ids": ["detail", "opening"] },
  { "type": "update_clip", "clip_id": "opening", "changes": { "frames": 24 } }
]
```

```sh
node cli.mjs edit /absolute/new-project 1 operations.json
node cli.mjs read /absolute/new-project 2
node cli.mjs render /absolute/new-project /absolute/new-export 2
```

工具支持 `reorder`、`update_clip`、`replace_clips`（增删/拆分片段）、`set_audio`。完整操作批次验证通过才发布下一版本；旧版本保留，预期版本冲突则重读，不自动覆盖。修改单个 clip 时可更新切点、长度、音量、fit、字幕或已导入素材引用。

渲染必须使用新的、工程目录外的输出目录；失败目录也不自动覆盖。输出 `project.json`、`index.html`、复制的素材、`captions.vtt`、`video.mp4` 和 `receipt.json`。实际文件通过结构与解码检查后才能记为 completed；失败/取消有不同状态，半成品不应当作交付。SIGINT/SIGTERM 请求取消；强制杀进程可能留下 running 回执，重开不会把它升级为成功，也没有后台自动恢复服务。

预览是相同语义工程编译出的低分辨率 MP4（最长边最高 640），非交互式 HTML 编辑器。正式导出使用项目画布。每次固定工程 revision 和素材 hash；执行前、复制时均核验素材，项目与编译文件 digest 进入回执。

## 验证与限制

`npm test` 覆盖字幕随剪辑重定位、非法范围、路径约束、版本冲突、并发发布、父版本变化、输入变化及取消。

`npm run smoke` 生成自有测试图案和两种测试音，完成五个工程版本，包含口播/品牌/电商风格文字、静音及独立音轨的技术流程；输出在根 `dist/local-production/<timestamp>/`。画面取样比对源时间范围，音频信号检查不同音调是否随重排移动，另检查时长、分辨率、音轨、全文件解码、重开工程及原输入 hash。合成样例不能证明真实口播语义、品牌一致性、商业表现或专业剪辑效果；回执始终将人工听检和视觉验收独立标注。

输入时长上限 30 分钟，成片上限 10 分钟是当前合同限制，尚非长时长性能验收结果。无生成、云凭据、上传、发布、自动剪辑决策；用户/Agent 自行给出合法选片和已获授权素材。

上游接入依据是已安装固定版本的类型声明及实测。该版本真实签名为 `executeRenderJob(job, projectDir, outputPath, progressSink, signal)`；README 的 `inputPath/outputPath` 写法与安装包不一致。输出尺寸从编译 HTML 的 composition 定义读取，不能依靠无效的 `width/height` RenderConfig 字段。

### 可选的源字幕样式

单条 caption 可带 `style: {fontHeight, centerY, color, strokeWidth, weight}`。fontHeight 为画布高度比例0.015–0.08，centerY 为高度比例0.1–0.9，strokeWidth 为高度比例0–0.004，color 为六位十六进制色，weight 为400/600/700/900。显式样式使用透明背景与深色描边；预览按输出尺寸同比缩放。不接受任意 CSS、外部 URL 或字体路径。不传 style 时保留默认排版；新建含字幕工程的实际字体按下述固定制品绑定。

### 固定字幕字体

新建且含有效字幕的工程复制 `fonts/NotoSansSC.ttf`，将 `caption_font` 的 profile、SHA256 和内容寻址路径写入不可变工程修订；渲染时再次核对并复制同一字节。来源为 Google Fonts 固定 revision，见 `fonts/manifest.json`；OFL-1.1 原许可随 `fonts/OFL.txt` 交付。文件约17.8MB，运行时不下载、不安装到系统，也不依赖系统字体名。400/600/700/900 使用同一可变字体的对应字重，禁用合成粗体。

缺文件、摘要不符、符号链接及字体未覆盖的字符均拒绝；未知字体/profile 不回退。字形覆盖直接检查已验证文件的 Unicode cmap；Chromium 必须成功加载请求的字重才解除 producer 就绪门槛。仅等待 `document.fonts.ready` 不足以发现加载失败。`receipt.caption_font` 分开记录制品完整性、字形覆盖与运行时加载；`source_match` 始终 `unverified`，这套绑定不证明所选字体就是原片字体。

没有 `caption_font` 的既存工程仍按原来的系统字体行为渲染，并标记 `legacy-system-fonts/unverified`；不自动重写旧修订。要使用固定字体，须显式创建新工程。无新增字幕的原画面不会被重打字幕。制品升级必须保留旧 profile 的兼容支持，或明确拒绝旧绑定，不能用新字节冒充相同 profile。AIOS Run 冻结前对整套能力包版本的绑定与升级调度仍由宿主负责；本模块只验证已保存的渲染工程。

这是一份经宿主确认并冻结的样式参数，不是自动识别原片字体的能力。原片已有烧录字幕在保留画面时直接保留，无需擦除再重做；当前系统字体回退不保证原片字形一致或跨主机字体一致。样式进入工程和摘要，可随编辑保存；消费者若无法携带样式，应拒绝转换而不是静默丢弃。


时间边界按半开区间 `[start, end)` 执行：画面、字幕与音轨的 HTML 时间边界统一提前 1 纳秒以吸收浮点误差，避免小数序列化向上舍入造成整帧延迟。保存的工程帧数、源媒体裁切点、VTT 语义时间均不变；媒体 seek 使用完整数值精度。该容差远小于支持的24/30/60 fps一帧，属于输出序列化约定，不是整体提前字幕或修改原片。

实际浏览器故障回归：配置已安装的 `PRODUCER_HEADLESS_SHELL_PATH` 后运行 `node --test tests/font-render.integration.mjs`。使用1秒合成黑色视频验证400/900字重，再故意让字体URL不存在；必须失败，不能输出可交付结果。producer 0.8.53会覆盖内部tween-building标志，且把已拒绝的buildReady当作结束，因此字体门槛使用独立buildReady项，加载失败后保持未就绪，交给其有界超时中止。不要以`document.fonts.ready`已完成替代加载成功检查。

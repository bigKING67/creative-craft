# Local production MVP

可选的本地制作模块：已有/生成素材 → 版本化多轨工程（EditDocument v2）→ 有界批次编辑 → 预览 MP4 → 技术检查（QA）→ 修改 → 导出。它是 Creative Craft 的执行工具（Video Harness v1 的 P0 执行层），不包含自然语言规划器、阶段关卡、DataHub UI、素材检索或 Seedance 调用。现有 Python CLI 和轻量 Skill 安装保持不变；本模块目前只随源码 checkout 使用，不在根 npm/Skill 发布包中。

## 安装和运行

Node.js >=22、FFmpeg/ffprobe、可用的独立 Chrome 渲染进程。不要在用户浏览器 Profile 上执行渲染。

```sh
cd integrations/local-production
PUPPETEER_SKIP_DOWNLOAD=true npm ci --ignore-scripts
npm run fetch-font   # 下载 fonts/manifest.json 固定的字幕字体并核对 SHA-256；二进制不入库
export PRODUCER_HEADLESS_SHELL_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
node cli.mjs --help
npm test
npm run smoke        # 需要带 jsonschema 的 Python，见“验证与限制”
```

Chrome 路径示例仅适用于对应 macOS 安装；其他主机指定自己的渲染 Chrome 路径。模块不会自动下载 ASR/TTS 模型或调用云端语音服务。`ffmpeg`/`ffprobe` 需在 worker 的 PATH；`CREATIVE_FFMPEG`/`CREATIVE_FFPROBE` 仅覆盖本模块校验/QA/样例命令，不修改 HyperFrames 的二进制解析方式。

这是受信任本地用户的执行工具，不是多租户沙箱。DataHub 接入前必须另建隔离 worker、权限检查、任务队列、预算及受控素材解析。当前只接受本地普通文件；不接受 URL、任意 HTML、脚本或外部工程导入。项目路径与素材路径拒绝 symlink；macOS `/tmp`/`/var` 的系统别名需改用其真实路径。

### 固定版本（HyperFrames 升级评估结论）

所有 `@hyperframes/*` 精确固定为 **0.8.108**：`@hyperframes/producer` 与 `@hyperframes/lint` 为直接依赖，`core`/`engine`/`parsers`/`studio-server` 通过 package.json `overrides` 固定为同一版本（producer 自身声明为 `^0.8.108`，不加 overrides 会随发布漂移）；`gsap@3.13.0`。依赖闭包见 package-lock.json（其中 `puppeteer-core@25.12.0`）。

升级前（0.1.0）锁定为 `@hyperframes/producer@0.8.53`，但其 `^0.8.53` 间接依赖实际解析为 core/engine/lint/parsers/studio-server **0.8.54**，版本并不一致。2026-10-02 评估：升级到 0.8.108 后 `npm test`、`npm run smoke`、`node --test tests/font-render.integration.mjs` 全部通过，故保留升级。0.8.108 的 `executeRenderJob(job, projectDir, outputPath, progressSink, signal, assertRenderActive?)` 前五个参数与 0.8.53 相同（新增可选第六参数，本模块不使用）；上游 README 的 `inputPath/outputPath` 写法仍与安装包不一致。输出尺寸仍从编译 HTML 的 composition 定义读取，不能依靠无效的 `width/height` RenderConfig 字段。回执的 `engine_version`、`lint.version` 从已安装包读取，不再写死。

## 工程模型：EditDocument v2

共享合同为 `skills/creative-craft/schemas/edit-document-v2.schema.json`；语义规则由 `edit-document.mjs` 的 `validateV2` 执行，并以 `tests/fixtures/edit-document-v2/{valid,invalid}` 与 Python 核心保持一致（invalid 文件名即被违反的规则）。

- **素材（assets）与时间线实例（items）分离**；同一素材可多处引用。素材按 SHA-256 内容寻址复制到 `assets/<sha256>.media`，记录 `origin.kind = import | generated | render`（生成镜头须带 `provenance_ref`）。
- **轨道（tracks）** `video | audio | caption`，数组顺序即视频叠放顺序（靠前在下）；`locked` 轨道上的 item 不可被任何操作修改、删除或移入。修改锁定状态的 `edit_track` 必须单独成批（不能与其他操作同批，堵住“先解锁再修改”）；`revert_to` 保留当前锁定，且不能改动当前锁定轨道的内容。v2 `create` 与 `add_asset` 同样要求 `origin.kind = generated` 的素材带 `provenance_ref`。
- **输出时间**为 canvas.fps 下的整数帧，半开区间 `[start_frame, start_frame + frames)`；**源时间**为秒。同一轨道 media item 不可重叠，允许空隙（空隙为黑场/静音）。
- **media item** 必须有 `asset_id/start_frame/frames/source_in_seconds/volume`；视频轨要求素材有画面，音频轨要求有声音；`source_in_seconds + frames/fps ≤ asset.duration`。视频轨 item 可带 `fit`（默认 contain）、`opacity`、`transform {x, y, scale}`：x/y 是 item 中心占画布的比例，scale 是 item 框占画布宽高的比例（0.05–1）。音频轨 item 不接受画面属性。
- **caption item** 只能在字幕轨。`link {item_id, source_from, source_to}` 形式按所链接 media item 的**源时间**换算输出时间：显示区间 = link 源区间 ∩ 该 item 当前源窗口，随 item 移动、裁切自动生效，**不存输出时间**（带 link 时不得有 start_frame/frames）。无 link 时必须给 `start_frame/frames`。
- 与 Python 核心一致的附加规则：media item 不得带 `text/style/link`；caption item 不得带 `asset_id/source_in_seconds/volume`；`revision = 1` 时 `parent_sha256` 必须为 null，否则必须为 64 位十六进制。
- **成片时长** = 所有 media item 与非 link 字幕的最大结束帧，1 帧至 10 分钟。
- 每个修订带 `change {author: agent|human|system|migration, summary, operations_sha256}`。

## 创建工程

`create` 按 spec 格式决定工程格式：v2 spec（`tracks/items`）产出 v2 工程。v2 spec（媒体路径相对于命令 cwd）：

```json
{
  "project_id": "talk-broll",
  "title": "口播 + B-roll",
  "canvas": { "width": 1280, "height": 720, "fps": 24 },
  "assets": [
    { "id": "talk", "path": "/absolute/path/to/talk.mp4" },
    { "id": "music", "path": "/absolute/path/to/music.m4a" }
  ],
  "tracks": [
    { "id": "v_main", "kind": "video", "locked": false, "name": "主轨" },
    { "id": "a_music", "kind": "audio", "locked": false },
    { "id": "c_sub", "kind": "caption", "locked": false }
  ],
  "items": [
    { "id": "talk1", "track_id": "v_main", "kind": "media", "asset_id": "talk", "start_frame": 0, "frames": 48, "source_in_seconds": 0, "volume": 1, "fit": "cover" },
    { "id": "bed", "track_id": "a_music", "kind": "media", "asset_id": "music", "start_frame": 0, "frames": 48, "source_in_seconds": 0, "volume": 0.2 },
    { "id": "cap1", "track_id": "c_sub", "kind": "caption", "text": "第一句字幕", "link": { "item_id": "talk1", "source_from": 0.2, "source_to": 1.5 } },
    { "id": "title", "track_id": "c_sub", "kind": "caption", "text": "标题", "start_frame": 24, "frames": 24 }
  ]
}
```

```sh
node cli.mjs create /absolute/new-project spec.json
node cli.mjs read /absolute/new-project
node cli.mjs preview /absolute/new-project /absolute/new-preview 1
```

旧 v1 spec（`clips/audio`，片段按数组顺序连续拼接、字幕 `from/to` 为源秒）仍创建 `local-edit.v1` 工程，与 0.1.0 行为一致，宿主原有的 `edit <project> <revision> operations.json` 流程不变；首次提交 v2 编辑批次时按下文迁移规则升级（`tests/host-compat.test.mjs` 覆盖这条宿主路径）。创建会 ffprobe 输入、复制素材并记录 SHA-256，不修改源文件；工程目录必须不存在。暂不支持变速、转场、淡入淡出、音乐自动闪避、图形模板（P2）或自动语音分句。

## Agent 有界编辑（批次 v2）

先 `read` 当前修订，再提交批次文件：

```json
{
  "base_revision": 1,
  "author": "agent",
  "summary": "补导入 B-roll 叠在主轨上",
  "operations": [
    { "type": "add_asset", "id": "broll", "path": "/absolute/path/to/broll.mp4", "origin": { "kind": "generated", "provenance_ref": "jobs/broll.json" } },
    { "type": "add_track", "track": { "id": "v_broll", "kind": "video", "locked": false }, "index": 1 },
    { "type": "add_item", "item": { "id": "over", "track_id": "v_broll", "kind": "media", "asset_id": "broll", "start_frame": 12, "frames": 24, "source_in_seconds": 0, "volume": 0, "transform": { "x": 0.75, "y": 0.25, "scale": 0.4 } } }
  ]
}
```

```sh
node cli.mjs edit /absolute/project batch.json --dry-run   # 只返回 diff，不写任何文件
node cli.mjs edit /absolute/project batch.json
node cli.mjs render /absolute/project /absolute/new-export 2
```

操作（字段之外的键一律拒绝）：

| 操作 | 字段 | 说明 |
| --- | --- | --- |
| `add_asset` | `id, path, origin?` | 工程创建后补导入（含生成镜头）；默认 `origin.kind = import` |
| `add_track` | `track, index?` | 插入位置即叠放顺序，默认置顶；`locked` 缺省 false |
| `edit_track` | `track_id, locked?, name?` | 锁定/解锁/改名 |
| `add_item` | `item` | 完整 item；不能放进锁定轨道 |
| `remove_item` | `item_id, ripple?` | 同时删除链接到它的字幕；`ripple` 把同轨后续 item 前移 |
| `move_item` | `item_id, track_id?, start_frame?` | 只能移到同类轨道；link 字幕只能改轨，不能改起点 |
| `trim_item` | `item_id, head_frames?, tail_frames?, slip_seconds?` | 正数剪掉头/尾、负数延长；剪头同步推进源入点；`slip_seconds` 只移源入点、时序不变 |
| `split_item` | `item_id, at_frame, new_item_id` | 在输出帧处切开，后半段取新 id 并顺延源入点 |
| `replace_media` | `item_id, asset_id, source_in_seconds?, captions?` | 保持时序；未给 `captions` 时移除旧 link 字幕；`captions` 为 `{id, track_id, text, style?, source_from, source_to}` |
| `set_item_props` | `item_id, props` | `volume/fit/opacity/transform/text/style`；值为 null 表示移除（volume/text 不可移除） |
| `revert_to` | `revision` | 以旧修订内容发布新修订，**必须单独成批** |

规则：

- **整批原子**：先在内存中按序应用全部操作并对结果做完整 `validateV2`，任一失败则不复制素材、不发布。`base_revision` 不是最新修订直接拒绝（需重读），不自动合并。发布沿用硬链接无替换写入，并发写只有一个成功。
- **dry-run** 返回 `diff`：新增/删除/变更的 item id、轨道变化、新增素材 id、新旧成片帧数；`add_asset` 只 ffprobe 探测，不复制。
- **锁定轨道**：锁定轨道上的 item 不能被修改、删除或作为移动目标；`split/replace_media/remove_item` 需要改动的 link 字幕所在轨道也必须未锁定。link 字幕的存储数据不变，只随其 media item 的位置自然换算，这不算修改。`revert_to` 若会改变当前任一锁定轨道上的 item 也被拒绝。
- **split 的字幕归属（确定规则）**：link 字幕归属到**源区间起点 `source_from` 落在哪一半**（`source_from ≥ 切点源时间` 归后半，否则留在前半）。不复制字幕：跨越切点的字幕只在其所属那一半内显示相交部分，切点之后的部分不再显示；如需两半都显示，在后半段另加一条 link 字幕。
- **trim/move**：link 字幕按源时间自动跟随，不存输出时间；裁掉的源区间内的字幕自然不再显示。
- `change.operations_sha256` = 批次 `operations` 规范化 JSON（对象键递归排序、无空白、UTF-8）的 SHA-256。批次 `author` 只能是 agent/human/system（`migration` 保留给迁移）。
- 字幕字体：批次首次引入字幕时绑定固定字体（见下）；已绑定的工程每次编辑都校验新字幕字形覆盖。

## v1 工程兼容与迁移

`creative-craft.local-edit.v1` 修订保持可读、可渲染；对 v1 工程，旧 CLI 形式 `edit PROJECT EXPECTED_REVISION OPERATIONS.json` 与 `reorder/update_clip/replace_clips/set_audio` 行为不变。v2 工程收到 v1 操作时明确报错。

对 v1 工程首次提交 v2 批次时，先发布一个**纯迁移修订**（`change.author = "migration"`，不含任何编辑），再在其上发布本次编辑修订；旧文件不改写。迁移映射：clips → `v_main` 视频轨按顺序排列的 item（id 不变）；clip 内 captions → `c_main` 字幕轨 link 字幕（id 为 `cap1…`，避开已有 id）；audio → `a_bed` 音频轨 item（v1 允许重叠的音轨，重叠者依次放入 `a_bed_2…`）；assets 补 `origin.kind = "import"`。v1 音轨超出最后一个片段的部分在渲染时本就被截断，迁移把截断写实（完全落在片尾之后的音轨被丢弃），以免 v2 成片被拉长。smoke 实测迁移修订与原 v1 修订的导出逐帧画面 MAE 为 0、音频 RMS 相同。迁移修订与编辑修订分两次无替换发布：极端并发下若编辑修订冲突，已发布的迁移修订仍是合法且等价的 v2 版本。

## 渲染与 lint 关卡

渲染必须使用新的、工程目录外的输出目录；失败目录也不自动覆盖。输出 `project.json`、`index.html`、复制的素材、`captions.vtt`、`video.mp4` 和 `receipt.json`。多轨编译：视频轨按数组顺序叠放（显式 z-index，字幕始终在画面之上），每条轨道独立 `data-track-index` 通道；视频 item 的素材含音频且 volume>0 时输出独立 `<audio>`；音频轨 item 输出 `<audio>`；link 与非 link 字幕均生成 WebVTT。

编译 HTML 后用 `@hyperframes/lint` 的 `lintHyperframeHtml` 检查，按 `shouldBlockRender(strictErrors=true, strictAll=false, …)` 判定：存在 error 级发现即中止，回执 `failed`、不产出视频；结果（版本、计数、发现）写入 `receipt.lint`。v2 字幕带 `class="clip"`，编译结果无 lint 警告；v1 编译保持原样（字幕缺 clip 类会产生 warning，不阻断）。

回执还记录 `document_schema`、`revision_sha256`（工程修订文件摘要，QA 据此绑定修订）、`project_sha256`、`composition_sha256`。实际文件通过结构（含“工程有可听音频 ⇔ 输出有音轨”）与全文件解码检查后才能记为 completed；失败/取消有不同状态，半成品不应当作交付。SIGINT/SIGTERM 请求取消；强制杀进程可能留下 running 回执，重开不会把它升级为成功，也没有后台自动恢复服务。

预览是相同语义工程编译出的低分辨率 MP4（最长边最高 640），非交互式 HTML 编辑器。正式导出使用项目画布。每次固定工程 revision 和素材 hash；执行前、复制时均核验素材。

## 技术检查（QA）

```sh
node cli.mjs qa /absolute/project /absolute/render-dir /absolute/new-qa-dir
```

读取渲染目录回执与工程快照：回执必须 `completed`，`revision_sha256` 与工程修订文件一致，快照与修订内容一致，视频 SHA-256 与回执一致；否则拒绝检查。QA 目录必须是新目录且在工程外。生成符合 `render-qa.schema.json` 的 `qa.json`：

- **structure**：时长与修订帧数相差 ≤1 帧（取视频流时长）、分辨率（导出=画布，预览=缩放尺寸）、帧率、音轨（工程有可听 item 而无音轨为 fail）。
- **video**：ffmpeg `blackdetect`（d=0.5, pix_th=0.10）与 `freezedetect`（-60dB, d=2）。与时间线空隙重叠的部分视为预期黑场/静止，只有落在有画面区间内的 >0.5 s 黑场、>2 s 静止记 warn。
- **audio**：`silencedetect`（-50dB, d=2）只统计工程有声音区间内的 >2 s 静音（warn）；`ebur128=peak=true` 积分响度超出 -14±3 LUFS 记 warn，真峰值 > -1 dBTP 记 warn。无音轨时为 unknown/not_applicable。
- **captions**：每条可见字幕在显示区间中点采样合成帧，帧存在记 pass（不判断文字是否可读）。
- **lint**：引用渲染回执的 lint 结果（error→fail，warning→warn，旧回执无结果→unknown）。

采样合成后的成片帧（不是源素材帧）：每个 media item 中点、每个视频剪辑点前后各一帧、每条字幕中点，PNG 写入 `frames/` 并记 SHA-256；采样按帧号精确定位（`-ss` 提前 1/4 帧，避免落到下一帧）。用 ffmpeg `tile` 把采样（超过 40 张时均匀抽取）拼成 `contact-sheet.png`；每个剪辑点前后各 1 秒导出 `clips/cut-<帧号>.mp4` 供听看。

`verdict`：任一 fail → fail；否则有 warn → pass_with_warnings；否则 pass。`review` 初始为 `{status:"pending", reviewer:null, decision:"pending", findings:[]}`，由 Agent 或人工依据采样填写；`unverified` 固定声明人工听检、创意质量、合成画面评审与字幕可读性未验证。自动检查只反映技术信号：不检测音画同步、字幕与语音是否对应、画面内容是否正确，也不替代对合成画面的评审。

## 验证与限制

`npm test` 覆盖：共享样例（valid 全部通过、invalid 逐文件按违反规则拒绝）、Python 侧附加规则的内联负向用例、11 个操作、批次原子性、过期修订、锁定轨道、dry-run 零写入、split 字幕归属、replace_media 字幕规则、revert_to 单独成批、规范化 operations 摘要、v1 迁移（时序/字幕/音轨分道与截断）与 v2 工程拒绝 v1 操作、多轨编译（z 序/transform/opacity/独立音频/转义）、lint 关卡放行与阻断；以及原有的字幕重定位、路径约束、版本冲突、并发发布、父版本变化、输入变化与取消。

`npm run smoke` 用自有测试图案和测试音（无客户素材），输出在根 `dist/local-production/<timestamp>/`：

1. v1 旧流程（以 `createProject(…, { legacyV1: true })` 建立 v1 工程，仅供兼容验证）：五个版本、旧 CLI `edit` 形式、画面/音调信号核对、静音导出与独立音轨。
2. 对该 v1 工程提交 v2 批次：迁移修订 + 编辑修订，迁移修订导出与 v1 导出逐帧比对。
3. v2 多轨：主轨 + 补导入 B-roll（transform 叠放）+ 音乐轨 + link 字幕 + 非 link 字幕；dry-run 不发布不复制、过期修订拒绝、锁定轨道拒绝、split、revert_to；导出后核对 B-roll 框内为 B-roll、框外为主画面、开始前不可见，以及主轨音调与 660 Hz 音乐同时存在。
4. CLI `qa` 生成 `qa.json`；以带 jsonschema 的 Python（`CREATIVE_PYTHON`，默认仓库根 `.venv/bin/python`）按 Draft 2020-12 校验 qa.json 与所有 v2 修订文件，缺少 Python/jsonschema 时 smoke 直接失败。再复制该导出、剥离音轨并改写回执摘要，模拟“声称完成但丢音轨”的导出器，QA 必须给出 `verdict = fail`。

合成样例不能证明真实口播语义、品牌一致性、商业表现或专业剪辑效果；样例响度（约 -19.7 LUFS）落在目标外，QA 如实给出 pass_with_warnings。输入时长上限 30 分钟，成片上限 10 分钟是当前合同限制，尚非长时长性能验收结果；QA 对每个采样单独调用 ffmpeg，长工程/大量 item 时耗时随采样数线性增长。无生成、云凭据、上传、发布、自动剪辑决策；用户/Agent 自行给出合法选片和已获授权素材。

### 可选的源字幕样式

字幕可带 `style: {fontHeight, centerY, color, strokeWidth, weight}`。fontHeight 为画布高度比例0.015–0.08，centerY 为高度比例0.1–0.9，strokeWidth 为高度比例0–0.004，color 为六位十六进制色，weight 为400/600/700/900。显式样式使用透明背景与深色描边；预览按输出尺寸同比缩放。不接受任意 CSS、外部 URL 或字体路径。不传 style 时保留默认排版；新建含字幕工程的实际字体按下述固定制品绑定。

### 固定字幕字体

新建且含有效字幕的工程（以及首次通过批次引入字幕的 v2 工程）复制 `fonts/NotoSansSC.ttf`，将 `caption_font` 的 profile、SHA256 和内容寻址路径写入不可变工程修订；渲染时再次核对并复制同一字节。来源为 Google Fonts 固定 revision，见 `fonts/manifest.json`；OFL-1.1 原许可随 `fonts/OFL.txt` 交付。文件约17.8MB，运行时不下载、不安装到系统，也不依赖系统字体名。400/600/700/900 使用同一可变字体的对应字重，禁用合成粗体。

缺文件、摘要不符、符号链接及字体未覆盖的字符均拒绝；未知字体/profile 不回退。字形覆盖直接检查已验证文件的 Unicode cmap；Chromium 必须成功加载请求的字重才解除 producer 就绪门槛。仅等待 `document.fonts.ready` 不足以发现加载失败。`receipt.caption_font` 分开记录制品完整性、字形覆盖与运行时加载；`source_match` 始终 `unverified`，这套绑定不证明所选字体就是原片字体。

没有 `caption_font` 且已有字幕的既存工程（含迁移而来的此类 v1 工程）仍按原来的系统字体行为渲染，并标记 `legacy-system-fonts/unverified`；不自动重写旧修订，后续编辑也不改绑。要使用固定字体，须显式创建新工程。无新增字幕的原画面不会被重打字幕。制品升级必须保留旧 profile 的兼容支持，或明确拒绝旧绑定，不能用新字节冒充相同 profile。AIOS Run 冻结前对整套能力包版本的绑定与升级调度仍由宿主负责；本模块只验证已保存的渲染工程。

这是一份经宿主确认并冻结的样式参数，不是自动识别原片字体的能力。原片已有烧录字幕在保留画面时直接保留，无需擦除再重做；当前系统字体回退不保证原片字形一致或跨主机字体一致。样式进入工程和摘要，可随编辑保存；消费者若无法携带样式，应拒绝转换而不是静默丢弃。

时间边界按半开区间 `[start, end)` 执行：画面、字幕与音轨的 HTML 时间边界统一提前 1 纳秒以吸收浮点误差，避免小数序列化向上舍入造成整帧延迟。保存的工程帧数、源媒体裁切点、VTT 语义时间均不变；媒体 seek 使用完整数值精度。该容差远小于支持的24/30/60 fps一帧，属于输出序列化约定，不是整体提前字幕或修改原片。

实际浏览器故障回归：配置已安装的 `PRODUCER_HEADLESS_SHELL_PATH` 后运行 `node --test tests/font-render.integration.mjs`。使用1秒合成黑色视频验证400/900字重，再故意让字体URL不存在；必须失败，不能输出可交付结果。producer 0.8.53会覆盖内部tween-building标志，且把已拒绝的buildReady当作结束，因此字体门槛使用独立buildReady项，加载失败后保持未就绪，交给其有界超时中止；该门槛在 0.8.108 上经同一回归测试复核通过。不要以`document.fonts.ready`已完成替代加载成功检查。

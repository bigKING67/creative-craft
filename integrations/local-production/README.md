# Local production MVP

可选的本地制作模块：已有/生成素材 → 版本化多轨工程（EditDocument v2）→ 有界批次编辑 → 预览 MP4 → 技术检查（QA）→ 修改 → 导出。它是 Creative Craft 的执行工具（Video Harness v1 的 P0 执行层，0.3.0 起含 P2 包装与音频：变速、淡入淡出、交叉淡化、音乐自动闪避、带类型变量的图形模板），不包含自然语言规划器、阶段关卡、DataHub UI、素材检索或 Seedance 调用。现有 Python CLI 和轻量 Skill 安装保持不变；本模块目前只随源码 checkout 使用，不在根 npm/Skill 发布包中。

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

### P2 字段：包装与音频

均为可选字段，旧文档继续合法。规则见 `docs/content-production-architecture.md`「P2 语义规则」，Node 与 Python 各实现一次。

- **变速** `speed`（media，0.1–10，缺省 1）：源区间 = `source_in_seconds + frames/fps × speed`，须在素材时长 +0.001 s 内；link 字幕输出时间 = item 起点 + (源时间 − 源入点) / speed。
- **淡变** `fade_in_frames` / `fade_out_frames`（media、graphic）：非负整数帧，二者之和 ≤ `frames`。画面为透明度，声音为音量包络。
- **转场** `transition_in: {kind: "crossfade", frames}`（media）：同轨 item 不得重叠，唯一例外是后一 item 声明 crossfade、起点严格晚于紧邻前一 item、且重叠帧数恰好等于 `frames`（不超过两者各自长度）；重叠检查覆盖所有在前 item，不只相邻的；声明 crossfade 却无重叠同样无效。
- **自动闪避** 轨道 `duck: {under_track_id, depth_db (−24…−3), attack_frames (0–60), release_frames (0–120)}`：只在 audio 轨；参照轨必须存在、不是自身、是 video 或 audio 轨，且自身不带 duck（只有一层）。
- **图形** item `kind: "graphic"`：只在 video 轨，只接受 `id, track_id, kind, template, vars, start_frame, frames, fade_in_frames, fade_out_frames, opacity`；参与同轨不重叠与成片时长；`vars` 值只能是 1–200 字符字符串、有限数字或布尔值。模板存在性与变量类型由 Node 校验（见下文“图形模板”）。
- caption 不得带 speed、淡变或转场字段。

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

旧 v1 spec（`clips/audio`，片段按数组顺序连续拼接、字幕 `from/to` 为源秒）仍创建 `local-edit.v1` 工程，与 0.1.0 行为一致，宿主原有的 `edit <project> <revision> operations.json` 流程不变；首次提交 v2 编辑批次时按下文迁移规则升级（`tests/host-compat.test.mjs` 覆盖这条宿主路径）。创建会 ffprobe 输入、复制素材并记录 SHA-256，不修改源文件；工程目录必须不存在。P2 字段（变速、转场、淡变、闪避、图形）只在 v2 工程中可用；不支持自动语音分句。

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
| `edit_track` | `track_id, locked?, name?, duck?` | 锁定/解锁/改名；`duck` 为对象时设置、为 null 时清除自动闪避（锁定轨道不能改 duck） |
| `add_item` | `item` | 完整 item（含 `kind: "graphic"`）；不能放进锁定轨道 |
| `remove_item` | `item_id, ripple?` | 同时删除链接到它的字幕；`ripple` 把同轨后续 item 前移 |
| `move_item` | `item_id, track_id?, start_frame?` | 只能移到同类轨道；link 字幕只能改轨，不能改起点 |
| `trim_item` | `item_id, head_frames?, tail_frames?, slip_seconds?` | 正数剪掉头/尾、负数延长；剪头同步推进源入点；`slip_seconds` 只移源入点、时序不变 |
| `split_item` | `item_id, at_frame, new_item_id` | 在输出帧处切开，后半段取新 id 并顺延源入点 |
| `replace_media` | `item_id, asset_id, source_in_seconds?, captions?` | 保持时序；未给 `captions` 时移除旧 link 字幕；`captions` 为 `{id, track_id, text, style?, source_from, source_to}` |
| `set_item_props` | `item_id, props` | `volume/fit/opacity/transform/text/style/speed/fade_in_frames/fade_out_frames/transition_in/vars`；值为 null 表示移除（volume/text/vars 不可移除） |
| `revert_to` | `revision` | 以旧修订内容发布新修订，**必须单独成批** |

规则：

- **整批原子**：先在内存中按序应用全部操作并对结果做完整 `validateV2`，任一失败则不复制素材、不发布。`base_revision` 不是最新修订直接拒绝（需重读），不自动合并。发布沿用硬链接无替换写入，并发写只有一个成功。
- **dry-run** 返回 `diff`：新增/删除/变更的 item id、轨道变化、新增素材 id、新旧成片帧数；`add_asset` 只 ffprobe 探测，不复制。
- **锁定轨道**：锁定轨道上的 item 不能被修改、删除或作为移动目标；`split/replace_media/remove_item` 需要改动的 link 字幕所在轨道也必须未锁定。link 字幕的存储数据不变，只随其 media item 的位置自然换算，这不算修改。`revert_to` 若会改变当前任一锁定轨道上的 item（或目标修订缺少该轨道）也被拒绝。锁定冻结的是该轨道自身的 item 与设置（含 `duck` 配置与名称）：`revert_to` 时锁定轨道整体保持当前定义，不被目标修订的轨道对象覆盖。锁定不冻结由被参照轨道派生的闪避包络——被参照轨道（如未锁定的口播轨）的 item 变化时，锁定音乐轨的实际音量曲线会随之重新计算。
- **split 的字幕归属（确定规则）**：link 字幕归属到**源区间起点 `source_from` 落在哪一半**（`source_from ≥ 切点源时间` 归后半，否则留在前半）。不复制字幕：跨越切点的字幕只在其所属那一半内显示相交部分，切点之后的部分不再显示；如需两半都显示，在后半段另加一条 link 字幕。
- **trim/move**：link 字幕按源时间自动跟随，不存输出时间；裁掉的源区间内的字幕自然不再显示。
- **P2 下的 split/trim/move（确定规则）**：
  - 变速：split 两半都保留 `speed`；后半源入点 = 原源入点 + 前半帧数/fps × speed。`trim_item` 剪头同样按 `head_frames/fps × speed` 推进源入点；`slip_seconds` 是源秒，不乘 speed。
  - 淡变与转场：split 后**前半保留 `fade_in_frames` 与 `transition_in`，后半保留 `fade_out_frames`**，新切点是硬切（前半去掉 fade_out，后半去掉 fade_in 与 transition_in）。原 item 若是下一个 item crossfade 的前驱，重叠落在后半上，后半长度须 ≥ 转场帧数。
  - trim/move 不自动改写淡变与转场：结果必须仍满足规则（淡变之和 ≤ 长度；crossfade 重叠恰好等于帧数），否则整批拒绝；需要时在同一批次里用 `set_item_props` 调整或删除 `transition_in`/淡变。
  - split 遇到淡变长于所在半段时整批拒绝（例如 fade_in 10 帧、在第 5 帧切），不做截断。
- **duck 变更不是锁定变更**：`edit_track` 只有改 `locked` 时必须单独成批；设置/清除 `duck` 可与其他操作同批。
- `change.operations_sha256` = 批次 `operations` 规范化 JSON（对象键递归排序、无空白、UTF-8）的 SHA-256。批次 `author` 只能是 agent/human/system（`migration` 保留给迁移）。
- 字幕字体：批次首次引入字幕时绑定固定字体（见下）；已绑定的工程每次编辑都校验新字幕字形覆盖。

## 图形模板

模板是执行层资源，位于 `templates/<id>.json`（`schema_version: creative-craft.graphic-template.v2`、整数 `version`、命名位置 `placements` 与 `default_placement`、带类型变量、固定 `html`/`css`），加载时逐项校验，不合格的模板直接使模块加载失败：

- `placements`：一个或多个命名位置（名称 `^[a-z][a-z0-9_]{0,31}$`），每个是一个 `box`（画布比例 left/top/width/height），**每个**都必须完整位于 5% 安全区内（left/top ≥ 0.05，right/bottom ≤ 0.95）；`default_placement` 必须是其中之一。
- 变量类型：`string`（`max_length` 1–200、`font_em`、`weight`，可选 `optional`）、`color`（`#rrggbb`）、`boolean`、`number`（`min/max`）；可选变量可带 `default`。`placement` 是保留变量名，模板不得声明。按最坏情况（每个字符 1 em 全角）对**最窄的位置框**校验 `max_length × font_em ≤ 100 × box.width × 0.95`，保证最长文本在任一位置都放得下。
- **最小字号**：任何文本变量渲染字号 ≥ 3 em = 画布短边的 3%（竖屏 1080 宽 ≥ 32.4 px，720 宽 ≥ 21.6 px）。加载时 `font_em` 小于 3 的字符串变量先被抬到 3 再做上面的放得下校验（抬高后放不下则加载失败）；CSS 里的字号只能写 `font-size:var(--fs-<变量名>)`，编译时由 `font_em` 生成 `--fs-<变量名>:<font_em>em`，因此 CSS 不能绕过该下限。说明：需求表述为“画布宽度的 3%”，竖屏与方形画布上两者相同；横屏若按宽度计（1920 宽需 57.6 px ≈ 5.3 em），现有模板的最长文本放不进框，所以统一按短边计，横屏实际下限为高度的 3%。
- `html` 只能含 `<span class="…">`（HyperFrames lint 会把计时元素内嵌套的块结构标为 warning），每个字符串变量以 `{{name}}` 恰好出现一次；`html`/`css` 禁止 script、事件属性、`url(`、`@import`、`src/href` 等；CSS 每条规则必须以 `.gfx-<id>` 作用域开头。
- 编译：字符串值 HTML 转义后填入；颜色/数字写成根元素内联 CSS 自定义属性（`--accent:#2f9e8f`），字号写成 `--fs-<name>`；布尔写成固定 `data-<name>="true|false"`；所选位置写成 `data-placement="<name>"`。不接受任意 HTML、URL 或脚本。根元素字号 = 画布短边 / 100 px（1 em = 短边 1%），各平台比例下同一模板文本相对尺寸一致；文本 `nowrap + ellipsis`，最坏情况仍在框内。
- 位置选择：graphic item 用保留变量 `vars.placement`（字符串，取该模板声明的位置名）选择位置；缺省为模板的 `default_placement`，与旧文档（无 placement）的位置一致。Node 校验 placement 必须是该模板的位置名（不是则拒绝并列出可选名）；Python 侧只校验 vars 为原始值，`placement` 是字符串，无需改动。`graphic-safe-area` 与采样都使用所选位置的框。
- 字体：图形与字幕共用已绑定的字幕字体（`.caption,.gfx` 同一 `@font-face`），存在 graphic item 时与字幕一样触发字体绑定、字形覆盖检查和运行时字重加载门槛。没有字体绑定却已有系统字体字幕的旧工程不能加图形（否则会改变原字幕字体），须新建工程。

当前模板（v2；与 v1 相比：位置可选；`lower-third` 副标题从 2.4 em 提到 3 em 以满足最小字号，框宽从 0.62 放宽到 0.78 以容纳最长副标题；默认位置不变）：

| id | 位置（placements，默认加粗） | 变量 |
| --- | --- | --- |
| `lower-third` v2 | **`bottom`** 左下 0.06/0.70，宽 0.78 × 高 0.20；`upper` 0.06/0.14，宽 0.78 × 高 0.20（高度 14–34%，避开底部烧录字幕与免责声明） | `title` 字符串 ≤16（3.6 em, 700）、`subtitle` 可选 ≤24（3 em, 400）、`accent` 可选颜色（默认 #e3b341） |
| `title-card` v2 | **`center`** 0.10/0.30，宽 0.80 × 高 0.40；`top` 0.10/0.08，宽 0.80 × 高 0.20（高度 8–28%，避开竖屏居中人脸） | `title` ≤12（6 em, 900）、`subtitle` 可选 ≤24（3 em）、`background`/`text_color` 可选颜色、`panel` 可选布尔（false 时面板透明） |

示例：`{"template": "lower-third", "vars": {"title": "主讲人", "placement": "upper"}}`。

## v1 工程兼容与迁移

`creative-craft.local-edit.v1` 修订保持可读、可渲染；对 v1 工程，旧 CLI 形式 `edit PROJECT EXPECTED_REVISION OPERATIONS.json` 与 `reorder/update_clip/replace_clips/set_audio` 行为不变。v2 工程收到 v1 操作时明确报错。

对 v1 工程首次提交 v2 批次时，先发布一个**纯迁移修订**（`change.author = "migration"`，不含任何编辑），再在其上发布本次编辑修订；旧文件不改写。迁移映射：clips → `v_main` 视频轨按顺序排列的 item（id 不变）；clip 内 captions → `c_main` 字幕轨 link 字幕（id 为 `cap1…`，避开已有 id）；audio → `a_bed` 音频轨 item（v1 允许重叠的音轨，重叠者依次放入 `a_bed_2…`）；assets 补 `origin.kind = "import"`。v1 音轨超出最后一个片段的部分在渲染时本就被截断，迁移把截断写实（完全落在片尾之后的音轨被丢弃），以免 v2 成片被拉长。smoke 实测迁移修订与原 v1 修订的导出逐帧画面 MAE 为 0、音频 RMS 相同。迁移修订与编辑修订分两次无替换发布：极端并发下若编辑修订冲突，已发布的迁移修订仍是合法且等价的 v2 版本。

## 渲染与 lint 关卡

渲染必须使用新的、工程目录外的输出目录；失败目录也不自动覆盖。输出 `project.json`、`index.html`、复制的素材、`captions.vtt`、`video.mp4` 和 `receipt.json`。多轨编译：视频轨按数组顺序叠放（显式 z-index，字幕始终在画面之上），每条轨道独立 `data-track-index` 通道；视频 item 的素材含音频且 volume>0 时输出独立 `<audio>`；音频轨 item 输出 `<audio>`；link 与非 link 字幕均生成 WebVTT。

**P2 编译映射**（按已安装的 `@hyperframes/*` 0.8.108 dist 实测，而非文档推断）：

- 变速：`<video>`/`<audio>` 写 `data-playback-rate="<speed>"`（core `readPlaybackRate` 读取并限制在 0.1–10；engine 抽帧按 `sourceTimeAt` 换算画面源时间，混音用 `atempo` 变速不变调）。`data-media-start` 仍是源入点。
- 音量：所有随时间变化的音量（淡入淡出、crossfade 两侧、闪避）合成为每个 `<audio>` 上**一条** `data-automation` volume lane，此时不再写 `data-volume`，也不生成任何 GSAP 音量补间，因此不会出现 `audio_volume_double_automation`。实测语法：`data-automation='{"version":1,"lanes":[{"target":"volume","points":[{"t":0,"v":0},{"t":0.333333,"v":1},…]}]}'`（HTML 属性内转义为 `&quot;`）；`t` 为**相对该元素 data-start 的秒数**（clip-local），`v` 为**绝对线性增益**（替代而非乘以 data-volume；engine `volumeLaneKeyframes` 把首点之前保持首值、末点之后保持末值，再逐样本乘入 PCM），点间线性插值，每条最多 512 点：`create` 与编辑批次（含 dry-run）用与编译相同的包络函数（`timeline.mjs` 的 `volumeEnvelope`）逐条计算，超出即拒绝并指明 item 与轨道，不会留到渲染才失败。音量恒定的 item 仍只写 `data-volume`。
- 包络计算：增益 = volume × 淡入斜坡 × 淡出斜坡 × crossfade 入（后一段 0→1）× crossfade 出（前一段 1→0，线性）× 闪避；在所有斜坡端点精确相乘，端点之间线性。闪避：参照轨上有声 media（volume>0 且素材有音频）的输出区间；相邻区间若“释放 + 下一次起音”会相接则合并；每段在说话开始前 attack 帧内降到 `10^(depth_db/20)`（时间线已知，提前起音），说话结束后 release 帧内回到 1；0 帧按 1 ms 斜坡处理以免爆音。
- 画面：有淡变/转场的视频与图形以 `opacity:0` 编写，再按包络生成首尾相接的 `tl.fromTo("#id",{opacity:a},{opacity:b,duration,ease:"none",immediateRender:false},t)`；首段之后的恒定段不再生成补间（完成的补间保持终值）；起点与 clip 边界一样提前 1 ns，时长再缩 2 ns，避免相邻补间被 lint 判为重叠。crossfade 时前一段保持不透明，后一段在上层 0→1，所以重叠中点是 50/50 混合。
- 同轨 crossfade 的两段处于重叠，会在 HyperFrames 中被判为同一 `data-track-index` 上的重复音轨，所以链式 crossfade 的 item 在两个“卷”之间交替：视频 `n`/`n+40`、声音 `100+n`/`140+n`，叠放（z-index）不变，后一段在 DOM 中位于前一段之后。
- 回执新增 `audio_limiter: {ceiling_dbtp: -1, engaged, audio_lowered_db, source: "RenderJob.audioLoweredDb"}`：producer 的 AAC 真峰值限幅只在需要压低整段混音时在 RenderJob 上写 `audioLoweredDb`（缺省即未触发，记为 0）。

编译 HTML 后用 `@hyperframes/lint` 的 `lintHyperframeHtml` 检查，按 `shouldBlockRender(strictErrors=true, strictAll=false, …)` 判定：存在 error 级发现即中止，回执 `failed`、不产出视频；结果（版本、计数、发现）写入 `receipt.lint`。v2 字幕带 `class="clip"`，编译结果无 lint 警告；v1 编译保持原样（字幕缺 clip 类会产生 warning，不阻断）。

回执还记录 `document_schema`、`revision_sha256`（工程修订文件摘要，QA 据此绑定修订）、`project_sha256`、`composition_sha256`。实际文件通过结构（含“工程有可听音频 ⇔ 输出有音轨”）与全文件解码检查后才能记为 completed；失败/取消有不同状态，半成品不应当作交付。SIGINT/SIGTERM 请求取消；强制杀进程可能留下 running 回执，重开不会把它升级为成功，也没有后台自动恢复服务。

预览是相同语义工程编译出的低分辨率 MP4（最长边最高 640），非交互式 HTML 编辑器。正式导出使用项目画布。每次固定工程 revision 和素材 hash；执行前、复制时均核验素材。

## 技术检查（QA）

```sh
node cli.mjs qa /absolute/project /absolute/render-dir /absolute/new-qa-dir [--caption-band 0.62:0.86] [--scene-threshold 0.3]
```

可选参数：`--caption-band TOP:BOTTOM` 覆盖烧录字幕带（源画面高度比例，默认 0.62:0.86，带高 ≥ 0.05）；`--scene-threshold N` 覆盖成片镜头检测阈值（0–1，默认 0.3）。模块调用为 `qaRender(root, renderDir, qaDir, { captionBand: {top, bottom}, sceneThreshold })`。

读取渲染目录回执与工程快照：回执必须 `completed`，`revision_sha256` 与工程修订文件一致，快照与修订内容一致，视频 SHA-256 与回执一致；否则拒绝检查。QA 目录必须是新目录且在工程外。生成符合 `render-qa.schema.json` 的 `qa.json`：

- **structure**：时长与修订帧数相差 ≤1 帧（取视频流时长）、分辨率（导出=画布，预览=缩放尺寸）、帧率、音轨（工程有可听 item 而无音轨为 fail）。
- **video**：ffmpeg `blackdetect`（d=0.5, pix_th=0.10）与 `freezedetect`（-60dB, d=2）。与时间线空隙重叠的部分视为预期黑场/静止，只有落在有画面区间内的 >0.5 s 黑场、>2 s 静止记 warn。
- **audio**：`silencedetect`（-50dB, d=2）只统计工程有声音区间内的 >2 s 静音（warn）；`ebur128=peak=true` 积分响度超出 -14±3 LUFS 记 warn，真峰值 > -1 dBTP 记 warn。真峰值检查的 `measured` 同时引用回执的限幅证据：`audio_lowered_db`、`limiter_engaged`、`limiter_ceiling_dbtp`（旧回执无记录时为 null，observation 注明）。无音轨时为 unknown/not_applicable。
- **captions**：每条可见字幕在显示区间中点采样合成帧，帧存在记 pass（不判断文字是否可读）。
- **安全区**（`caption-safe-area`，category captions；`graphic-safe-area`，category video）：在字幕采样帧与图形中点采样帧上检查元素框是否距四边 ≥5%，都不是像素检测。图形（`measured.method = template-load-guarantee`）：框即模板框，模板加载校验已保证其在安全区内，该检查只是把这一保证记入 QA 并给出采样引用，observation 明确写明“由模板加载校验保证、非像素检测、不测量文字是否放得下”；不再做文字截断估算。字幕（`compiled-layout-estimate`）**按编译布局计算**：按编译 CSS 推算（默认样式：7%–93% 宽、底边 8%、行高 1.35、8 px 内边距；显式样式：以 centerY 为中心、行高 1.1、加描边），文本宽度按字符估算（全角 CJK/符号 1 em、其他 0.55 em、空格 0.3 em）推算换行行数。越界 → fail。`measured.boxes` 记录每个框。局限：字宽为估算，不是浏览器实测；不检测画面内容本身（如素材里已有的贴边文字）；图形检查不提供模板加载之外的新证据。
- **lint**：引用渲染回执的 lint 结果（error→fail，warning→warn，旧回执无结果→unknown）。
- **烧录字幕剪辑点**（`burned-caption-cut-points`，category captions）：素材自带的烧录字幕常比语音晚切换，按语音间隙选的入点可能仍显示被剪掉那句的字幕。对视频轨每个 media item 的**源入点与源出点**，在**源素材**上解码附近帧（灰度、短边缩到 360 px），检测字幕带（默认画面高度 62%–86%）的“阶跃”变化：
  - 判据：某像素在变化前 3 帧内稳定（极差 ≤ 12 灰度级）、变化后 3 帧内也稳定，且均值变化 ≥ 40，记为阶跃像素。烧录字幕在两次切换之间静止、在一帧内整体切换，字形像素会同时阶跃；手、脸、运镜不稳定，不产生阶跃。在带内取一行字幕高的窗口（画面高度 5%），阶跃像素占比 ≥ 10%，且其中“亮字形”阶跃（变化前或后的均值 ≥ 200，即白/黄字）占比 ≥ 5%，判为字幕变化。若同一时刻带外整帧平均绝对差 ≥ 30（灰度级），判为整帧镜头切换，视为对齐，不算字幕变化。
  - 入点：入点之后 ≤0.5 s（源时间）内出现字幕变化、而入点本身（±半帧）没有变化 → warn（入点时仍显示上一行字幕），建议把入点移到变化时刻；入点正好落在变化上记 aligned。出点：出点之前 ≤0.5 s 内出现字幕变化 → warn（下一行字幕在出点前闪现），建议出点提前到变化时刻。`measured` 记录 `method`、字幕带、阈值和每个剪辑点（item、in/out、源时间、成片时间、结果、附近的字幕变化与镜头切换、`suggested_source_seconds`/`suggested_shift_seconds`）；`refs` 指向成片剪辑点时间、item 与剪辑点采样帧。
  - 阈值实测（`byq-cream-01` 真实口播/实测/促销素材，竖屏 1080×1920 30 fps，只读）：人工核对过的字幕切换 `line_share` 0.11–0.41、亮字形占比 0.066–0.19；手和刷子掠过字幕带的误检 `line_share` 可达 0.12，但亮字形占比 ≤ 0.023，所以亮字形判据取 0.05；真实镜头切换的带外平均差 41–133，同一机位的跳切（字幕同时切换）约 17，所以镜头阈值取 30。在该素材修订 1 上，recap 入点（源 31.47 s）被 warn 并建议 31.60 s；修订 2（入点 31.60 s）记为 aligned，全片 8 个剪辑点无 warn。smoke 中无字幕的测试图案素材不报。
  - 局限：这是帧差启发式，不是 OCR：不能读字幕内容、不能判断字幕与语音是否对应；只识别亮色（白/黄）字幕，深色或彩色字幕、字幕带外的字幕会漏报；字幕淡入淡出、滚动字幕不是一帧阶跃，可能漏报；字幕带内持续静止后突然变化的亮色画面元素（如贴纸、产品特写）可能误报；字幕消失（变为空白）通常不触发。窗口在源时间上计（变速 item 同样按源秒 0.5 s）。无字幕素材应基本不报。解码失败、或解码帧数与 showinfo 时间数不一致（帧时间不可信）的剪辑点记 unknown；解码用 `-fps_mode passthrough`，变帧率素材每帧对应自己的源时间。汇总：任一剪辑点 warn → 检查 warn；否则任一 unknown → 检查 unknown（observation 写明未检查的数量、剪辑点与原因）；全部分析完且无 warn 才 pass。剪辑点窗口默认 4 路并发解码。
- **按镜头采样**（`shot-sampled`，category video）：对渲染成片做镜头检测（ffmpeg `select='gt(scene,T)'`，T 默认 0.3，可配置），把成片切成镜头；每个镜头若已有采样帧（item 中点、剪辑点、字幕）则不重复，否则在镜头中点加一帧 `reason: "shot"` 的采样，短镜头（<1 s）同样覆盖。`measured.shots` 记录每个镜头的起止与采样 id；有镜头取不到帧记 fail。局限：crossfade/淡变等渐变转场不产生场景分数峰值，渐变中的镜头边界由剪辑点采样覆盖；阈值以下的跳切（同机位小变化）不单独成镜头。

采样合成后的成片帧（不是源素材帧）：每个 media 与 graphic item 中点、每个视频剪辑点前后各一帧、每条字幕中点、每个尚无采样的镜头中点，PNG 写入 `frames/` 并记 SHA-256；采样按帧号精确定位（`-ss` 提前 1/4 帧，避免落到下一帧）。用 ffmpeg `tile` 把采样按时间顺序拼成 `contact-sheet.png`：最多 40 张（镜头多于 40 个时为镜头数），超出时先保证每个镜头一张，再均匀抽取其余采样；每个剪辑点前后各 1 秒导出 `clips/cut-<帧号>.mp4` 供听看。

`verdict`：任一 fail → fail；否则有 warn → pass_with_warnings；否则 pass。`review` 初始为 `{status:"pending", reviewer:null, decision:"pending", findings:[]}`，由 Agent 或人工依据采样填写；`unverified` 固定声明人工听检、创意质量、合成画面评审、字幕可读性未验证，以及烧录字幕检查只是帧差启发式。自动检查只反映技术信号：不检测音画同步、字幕与语音是否对应、画面内容是否正确，也不替代对合成画面的评审。

## 验证与限制

`npm test` 覆盖：共享样例（valid 全部通过、invalid 逐文件按违反规则拒绝）、Python 侧附加规则的内联负向用例、11 个操作、批次原子性、过期修订、锁定轨道、dry-run 零写入、split 字幕归属、replace_media 字幕规则、revert_to 单独成批、规范化 operations 摘要、v1 迁移（时序/字幕/音轨分道与截断）与 v2 工程拒绝 v1 操作、多轨编译（z 序/transform/opacity/独立音频/转义）、lint 关卡放行与阻断；P2：16 个新增共享 invalid 样例的拒绝原因、与 Python 对齐的附加规则内联负例（graphic 字段白名单、duck 指向字幕轨、crossfade 起点须严格晚于前驱、全量重叠扫描）、P2 编译（playback rate、volume lane 用 HyperFrames engine/core 解析并取样核对增益、透明度补间、图形转义、变速字幕换算、lint 零发现）、模板与变量类型校验、P2 编辑操作（props、graphic、duck、split/trim 规则、锁定轨道 duck、revert_to 保持锁定轨道的 duck）、512 点 volume 自动化上限在 create 与编辑（含 dry-run）时即拒绝、约 1000 item/100 crossfade/400 段被闪避音乐的编译耗时、安全区布局估算；P2.1：模板命名位置（缺省=旧位置、非法 placement 拒绝、lint 零发现）、最小字号（加载时抬高、抬高后仍须放得下、CSS 只能用 --fs 变量）、烧录字幕剪辑点判定（入点晚于字幕切换 warn 并给出变化时刻、对齐不报、出点前闪现 warn、无字幕素材与错位字幕带不报、整帧镜头切换不算字幕变化）与镜头检测（文件内 0.6 s 短镜头被切出、阈值可配置）；以及原有的字幕重定位、路径约束、版本冲突、并发发布、父版本变化、输入变化与取消。

`npm run smoke` 用自有测试图案和测试音（无客户素材），输出在根 `dist/local-production/<timestamp>/`：

1. v1 旧流程（以 `createProject(…, { legacyV1: true })` 建立 v1 工程，仅供兼容验证）：五个版本、旧 CLI `edit` 形式、画面/音调信号核对、静音导出与独立音轨。
2. 对该 v1 工程提交 v2 批次：迁移修订 + 编辑修订，迁移修订导出与 v1 导出逐帧比对。
3. v2 多轨：主轨 + 补导入 B-roll（transform 叠放）+ 音乐轨 + link 字幕 + 非 link 字幕；dry-run 不发布不复制、过期修订拒绝、锁定轨道拒绝、split、revert_to；导出后核对 B-roll 框内为 B-roll、框外为主画面、开始前不可见，以及主轨音调与 660 Hz 音乐同时存在。
4. CLI `qa` 生成 `qa.json`。再复制该导出、剥离音轨并改写回执摘要，模拟“声称完成但丢音轨”的导出器，QA 必须给出 `verdict = fail`。
5. P2 品牌包装（`packaging/`，24 fps 1280×720）：标题卡（0–36 帧）+ 下三分之一（76–116 帧）、两段主画面 crossfade（口播 0–72 淡入，色条 60–120 以 12 帧 crossfade 进入）、一段 1.5× 变速（口播源 2.5 s 起）带淡出、音乐轨在主画面轨下 −12 dB 闪避并淡入淡出、变速段上的 link 字幕。断言：lint 0 error/0 warning 且无 `audio_volume_double_automation`、三个 `<audio>` 全为 volume lane、VTT 中变速字幕为 5.667→6.333 s。信号检查：变速段第 132 帧与源 3.25 s 的画面 MAE 远小于与 1× 位置 3.0 s；crossfade 中点（第 66 帧）与两源平均帧的 MAE 远小于与任一单源；淡入首帧为黑、淡出末帧亮度降到 20% 以下；660 Hz 音乐能量在口播区间相对非口播区间约为 depth_db（±2 dB）；音乐淡入首窗明显更低；标题卡与下三分之一区域与下层画面显著不同且含白字与深色底。导出 QA 的 `graphic-safe-area`/`caption-safe-area`/lint 为 pass，`true-peak` 引用 `audio_lowered_db`。人为失败：新增一条 fontHeight 0.08、centerY 0.9 的两行字幕，预览 QA 必须在 `caption-safe-area` 上 fail。
6. P2.1 竖屏 QA（`portrait/`，30 fps 360×640 预览）：合成素材 `captioned.mp4`（移动测试图案 + 约 70% 高度的白色“字形”方块与深色描边，1.5 s 时从 A 行切到 B 行）与 `short-shot.mp4`（0.6–1.2 s 为一段色条短镜头）。item `late` 入点 1.3 s（字幕晚 0.2 s 切换，正例）、`shots` 含短镜头（成片 1.6–2.2 s，远离 item 中点与剪辑点）、`aligned` 入点 1.5 s（负例）；`title-card` 用 `placement: top`、`lower-third` 用 `placement: upper`。断言：lint 0/0；编译 HTML 的位置与 `--fs-*` 字号；`burned-caption-cut-points` 为 warn 且只有 `late` 入点 warn、建议 1.5 s，`aligned` 入点为 aligned；`shot-sampled` pass 且有一帧 `reason: "shot"` 落在 1.6–2.2 s，该帧高饱和像素（色条）占比 > 30%；`graphic-safe-area` pass。前面几个场景的测试图案素材在该检查上都是 pass（无字幕不报）。
7. 以带 jsonschema 的 Python（`CREATIVE_PYTHON`，默认仓库根 `.venv/bin/python`）按 Draft 2020-12 校验全部 v2 修订文件（含品牌包装与竖屏工程）与 5 份 qa.json，缺少 Python/jsonschema 时 smoke 直接失败。

合成样例不能证明真实口播语义、品牌一致性、商业表现或专业剪辑效果；样例响度（约 -19.7 LUFS）落在目标外，QA 如实给出 pass_with_warnings。输入时长上限 30 分钟，成片上限 10 分钟是当前合同限制，尚非长时长性能验收结果；QA 对每个采样单独调用 ffmpeg，长工程/大量 item 时耗时随采样数线性增长。无生成、云凭据、上传、发布、自动剪辑决策；用户/Agent 自行给出合法选片和已获授权素材。

P2 的已知限制：闪避依据参照轨上**有声 item 的区间**，不是语音活动检测（item 内部的停顿同样被压低）；crossfade 的音量为线性互补斜坡（相关信号恒幅，不相关信号中点约低 3 dB），不是等功率曲线；包络在斜坡端点精确、端点之间线性，两个斜坡同时变化时略偏离精确乘积；smoke 样例真峰值约 −19.9 dBTP，限幅器未触发，`audio_limiter.engaged = true` 的路径只按 producer 源码确认字段位置，尚无真实触发样例；安全区为布局估算或模板加载保证（见上）。遗留：模板加载时的“max_length 文本放得下模板框”估算按框宽 95% 计算，**未计入模板 CSS 的内边距**，极端长文本可能仍被省略号截断，QA 不再对此给出估算证据，需看采样帧。

### 可选的源字幕样式

字幕可带 `style: {fontHeight, centerY, color, strokeWidth, weight}`。fontHeight 为画布高度比例0.015–0.08，centerY 为高度比例0.1–0.9，strokeWidth 为高度比例0–0.004，color 为六位十六进制色，weight 为400/600/700/900。显式样式使用透明背景与深色描边；预览按输出尺寸同比缩放。不接受任意 CSS、外部 URL 或字体路径。不传 style 时保留默认排版；新建含字幕工程的实际字体按下述固定制品绑定。

### 固定字幕字体

新建且含有效字幕的工程（以及首次通过批次引入字幕的 v2 工程）复制 `fonts/NotoSansSC.ttf`，将 `caption_font` 的 profile、SHA256 和内容寻址路径写入不可变工程修订；渲染时再次核对并复制同一字节。来源为 Google Fonts 固定 revision，见 `fonts/manifest.json`；OFL-1.1 原许可随 `fonts/OFL.txt` 交付。文件约17.8MB，运行时不下载、不安装到系统，也不依赖系统字体名。400/600/700/900 使用同一可变字体的对应字重，禁用合成粗体。

缺文件、摘要不符、符号链接及字体未覆盖的字符均拒绝；未知字体/profile 不回退。字形覆盖直接检查已验证文件的 Unicode cmap；Chromium 必须成功加载请求的字重才解除 producer 就绪门槛。仅等待 `document.fonts.ready` 不足以发现加载失败。`receipt.caption_font` 分开记录制品完整性、字形覆盖与运行时加载；`source_match` 始终 `unverified`，这套绑定不证明所选字体就是原片字体。

没有 `caption_font` 且已有字幕的既存工程（含迁移而来的此类 v1 工程）仍按原来的系统字体行为渲染，并标记 `legacy-system-fonts/unverified`；不自动重写旧修订，后续编辑也不改绑。要使用固定字体，须显式创建新工程。无新增字幕的原画面不会被重打字幕。制品升级必须保留旧 profile 的兼容支持，或明确拒绝旧绑定，不能用新字节冒充相同 profile。AIOS Run 冻结前对整套能力包版本的绑定与升级调度仍由宿主负责；本模块只验证已保存的渲染工程。

这是一份经宿主确认并冻结的样式参数，不是自动识别原片字体的能力。原片已有烧录字幕在保留画面时直接保留，无需擦除再重做；当前系统字体回退不保证原片字形一致或跨主机字体一致。样式进入工程和摘要，可随编辑保存；消费者若无法携带样式，应拒绝转换而不是静默丢弃。

时间边界按半开区间 `[start, end)` 执行：画面、字幕与音轨的 HTML 时间边界统一提前 1 纳秒以吸收浮点误差，避免小数序列化向上舍入造成整帧延迟。保存的工程帧数、源媒体裁切点、VTT 语义时间均不变；媒体 seek 使用完整数值精度。该容差远小于支持的24/30/60 fps一帧，属于输出序列化约定，不是整体提前字幕或修改原片。

实际浏览器故障回归：配置已安装的 `PRODUCER_HEADLESS_SHELL_PATH` 后运行 `node --test tests/font-render.integration.mjs`。使用1秒合成黑色视频验证400/900字重，再故意让字体URL不存在；必须失败，不能输出可交付结果。producer 0.8.53会覆盖内部tween-building标志，且把已拒绝的buildReady当作结束，因此字体门槛使用独立buildReady项，加载失败后保持未就绪，交给其有界超时中止；该门槛在 0.8.108 上经同一回归测试复核通过。不要以`document.fonts.ready`已完成替代加载成功检查。

### 模板版本与回执

编辑修订只按 id 引用模板，不固定模板内容；模板升级后重新渲染旧修订，图形外观可能变化。渲染回执的 `templates` 记录本次使用的每个模板 `{id, version, sha256}`（模板 JSON 原始字节摘要），与 `composition_sha256` 一起用于追溯差异。把模板内容按内容寻址绑定进修订（类似字幕字体）属于共享 schema 变更，尚未实现。

## 本地语音转写

`transcribe` 用本机 whisper.cpp 把素材口播转成带句级时间戳的 JSON，作为 production-plan 选片证据（evidence modality `asr`）。客户音频不离开本机：ffmpeg 抽取 16 kHz 单声道 PCM 到私有临时目录，转写结束（含失败）即删除；不调用任何云端服务。

```sh
brew install whisper-cpp            # 提供 whisper-cli；或用 CREATIVE_WHISPER 指向其他构建
npm run fetch-asr-model             # 下载固定模型到 ~/.cache/whisper-cpp/（CREATIVE_WHISPER_MODEL_DIR 可覆盖）
node cli.mjs transcribe MEDIA NEW_OUT.json [--lang zh] [--model PATH] [--clean auto|on|off]
```

模型固定为 `ggml-large-v3-turbo.bin`（1624555275 字节，SHA-256 `1fc70f77…e2bc69`，来源 `huggingface.co/ggerganov/whisper.cpp`，清单见 `asr.mjs` 的 `ASR_MODEL`），不入库。下载先写 `.partial`，大小与摘要均吻合后原子 rename；已存在且吻合则跳过，不吻合直接拒绝。每次转写前都核对模型：文件名必须是固定模型、大小与摘要必须吻合，否则报错（缺失时提示 `npm run fetch-asr-model`）；为免每次散列 1.6 GB，校验通过后在模型旁写 `*.sha256-verified.json`，仅当大小、inode、mtime、ctime 都未变时复用（ctime 无法由用户态改回，原地覆盖后即使恢复大小与 mtime 也会重新散列）。转写期间收到 SIGINT/SIGTERM 时先停止正在运行的 ffmpeg/whisper 子进程、同步删除私有临时音频目录，再以 130/143 退出；正常结束后注销该处理器。

whisper 参数：`-l zh` 时附加 `--prompt "以下是普通话的句子。"`（引导简体与标点）。`--clean`：

- `off`：只做常规转写。
- `on`：只做预处理转写：`ffmpeg -af "highpass=f=120,lowpass=f=6000,afftdn=nf=-25,dynaudnorm"` 后加 `-mc 0 -et 2.8 -nth 0.3`。
- `auto`（默认）：先常规转写；用 `silencedetect=n=-35dB:d=0.5` 估算有声时长（总时长减去 ≥0.5 s 的静音段）。若有声 ≥ 2 s 且识别覆盖（句子区间并集）< 有声时长的 50%，再做预处理转写，取覆盖更大的一次（相等时保留常规结果），理由写入 `choice_reason`。

判据实测（whisper.cpp 1.9.2）：背景音乐很重的 27 s 直播口播片段全程有声（-35 dB 下无静音段，有声 26.842 s），常规转写只识别前 2.28 s（8.5%），触发重试；预处理转写 13 句覆盖 26.84 s，被选中。`say -v Tingting` 合成的 2.1 s 中文语音常规覆盖 1.86 s，不触发重试；纯静音有声 0 s，不触发重试。

输出（时间单位秒）：

```text
{schema: "creative-craft.local-transcript.v1",
 media: {path_basename, sha256, duration},
 engine: {name: "whisper.cpp", binary_version, model, model_sha256},
 language, audio_activity: {active_seconds, detector},
 attempts: [{params: {preprocess, whisper_args}, coverage_seconds}],
 chosen_attempt, choice_reason, note, segments: [{start, end, text}]}
```

`asr.mjs` 导出 `toPlanEvidence(segments, from, to, method)`：返回与 `[from, to]` 有重叠的句子，形如 `{modality: "asr", start_seconds, end_seconds, excerpt, raw_score: null, method}`，时间保留句子原始边界（不裁到区间）。

限制：ASR 文本可能有错字和同音字（如品牌名、人名），引用前需核对；时间戳是句级，不是逐字或逐帧对齐，剪辑点必须人工听审确认。覆盖率只说明“有文字的时间段”，不说明文字正确：whisper 会在纯音乐/持续音调上幻觉出整句（测试中 440 Hz 正弦音被“转写”为一句视频结尾套话并覆盖全程），此时覆盖足够、不会重试，幻觉内容也会进入结果。`auto` 判据只在上述片段上实测，阈值尚未在更多素材上标定。输出文件必须不存在。

`npm test` 中的 ASR 测试只用合成音频（ffmpeg 静音与正弦音、macOS `say -v Tingting`），不含客户素材；whisper-cli 或模型缺失时两项端到端测试跳过并给出原因，模型存在但摘要不符则失败。

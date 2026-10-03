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
- 可选 `graphic_templates: [{id, version, sha256, file}]`：本修订固定的图形模板（`file` 必须是 `templates/<sha256>.json`）。字段存在时每个 graphic 的 `template` 恰有一个同 id 绑定，绑定不得重复、不得有未被使用的绑定；见“模板版本与回执”。

### P2 字段：包装与音频

均为可选字段，旧文档继续合法。规则见 `docs/content-production-architecture.md`「P2 语义规则」，Node 与 Python 各实现一次。

- **变速** `speed`（media，0.1–10，缺省 1）：源区间 = `source_in_seconds + frames/fps × speed`，须在素材时长 +0.001 s 内；link 字幕输出时间 = item 起点 + (源时间 − 源入点) / speed。
- **淡变** `fade_in_frames` / `fade_out_frames`（media、graphic）：非负整数帧，二者之和 ≤ `frames`。画面为透明度，声音为音量包络。
- **转场** `transition_in: {kind: "crossfade", frames}`（media）：同轨 item 不得重叠，唯一例外是后一 item 声明 crossfade、起点严格晚于紧邻前一 item、且重叠帧数恰好等于 `frames`（不超过两者各自长度）；重叠检查覆盖所有在前 item，不只相邻的；声明 crossfade 却无重叠同样无效。
- **自动闪避** 轨道 `duck: {under_track_id, depth_db (−24…−3), attack_frames (0–60), release_frames (0–120)}`：只在 audio 轨；参照轨必须存在、不是自身、是 video 或 audio 轨，且自身不带 duck（只有一层）。
- **图形** item `kind: "graphic"`：只在 video 轨，只接受 `id, track_id, kind, template, vars, start_frame, frames, fade_in_frames, fade_out_frames, opacity`；参与同轨不重叠与成片时长；`vars` 值只能是 1–200 字符字符串、有限数字或布尔值。模板存在性与变量类型由 Node 校验（见下文“图形模板”）。
- caption 不得带 speed、淡变或转场字段。

### 源素材帧对齐（0.6.0）

合同见 `docs/content-production-architecture.md`「源素材帧对齐（2026-10-03）」。入点常被写成截断的小数（镜头首帧是 733/30 = 24.4333… 而写成 24.4333），渲染器显示“时间 ≤ 入点”的帧，于是成片第 0 帧是上一帧（旧镜头末帧）。

- **asset `frame_rate`**（可选，有理数字符串，如 `"30/1"`、`"30000/1001"`）：v2 `create` 与 `add_asset` 导入时由 ffprobe 写入，只在 `video: true` 的素材上合法（`validateV2` 拒绝纯音频素材上的该字段及非 `<num>/<den>` 形式；这是素材规则的唯一来源，编译时的修正函数只看 `frame_rate`）。导入时按工程格式决定：v1 工程（`local-edit.v1`）的导入不探测也不写该字段；已有工程不改写、不补写；v1 迁移得到的素材也没有该字段。
- **导入规则**（`probe` + `probedFrameRate`）：`video` 标记与宽高**保持原行为**，取自第一条视频流（任何视频流，包括封面图 `attached_pic`）；因此带封面图的音频文件仍是 `video: true`、宽高为封面尺寸，v1 工程照旧可把它用作 clip。`frame_rate` **只在第一条视频流不是封面图时**记录（保证帧率与宽高来自同一条流；封面图在前、画面流在后的文件不记录）。该流 `r_frame_rate` 与 `avg_frame_rate` 约分后**完全相等**（恒定帧率），且该流**自身起点**（`start_pts × time_base`，与 QA `sourceTiming` 同一来源）**为 0**，才记录约分后的帧率；文件 `format.start_time` 与其他流起点不参与判断，音频起点为负（AAC priming）不影响。否则（可变帧率、视频起点偏移如 0.5 s、缺 `start_pts` 等）不记录，这类素材保持渲染器原口径，由 QA 按解码出的实际帧时间检查并报警。“分析画面流”（第一条非封面视频流，`pictureStream`）与比值解析（`rational`）、流起点（`streamStart`）由导入与 QA `sourceTiming` 共用。
- **修正规则**（`truncatedFrame` / `correctedSourceIn`，`source-frames.mjs`）：只修正“小数截断”。视频轨 media item 的源入点若低于某帧起点（k/帧率）**不超过 2 ms 且严格不足 0.1 帧**（两条同时满足；覆盖截到毫秒的写法，如 30 fps 第 733 帧写成 24.433、24.4327 或 24.4333，29.97 fps 写成 24.457，24 fps 写成 30.541），编译为该帧起点 **+ 0.1 ms**（0.0001 s，保留到 1e-9 s）；恰在帧起点、或低于帧起点超过 2 ms（如 30 fps 下 24.430，低 3.3 ms）、或达到 0.1 帧（60 fps 下 0.1 帧 = 1.67 ms，先于 2 ms 生效）的入点**保持原值**（不再整体对齐到帧中点）。全程用 BigInt 有理数精确计算：入点按文档中 JSON 数值的最短十进制形式（如 `24.4333` = 244333/10000），帧率按整数比；恰低 2 ms 仍修正，恰低 0.1 帧不修正。位移上限为 min(2 ms, 0.1 帧) + 0.1 ms。帧率参数可传字符串或 `parseFrameRate` 的解析结果，`correctedSourceIn` 只解析一次，两种形式结果一致。
- **编译视图**（`compiledView(doc)`）：一次算出带修正入点的 items（文档不被改写，未修正的 item 与原文档共用同一对象，`correctionOf(item)` 给出原 item 与修正到的帧号）；对视图再调用直接返回自身。编译（`data-media-start`、link 字幕窗口、字体绑定的可见字幕）、`activeCaptions`、QA 字幕采样与两项剪辑点检查都使用同一个视图，不各自调用修正函数：渲染时 `renderProject` 只计算一次视图，传给字体校验（`verifyAssets`、`copyCaptionFont`）与 `compose`（`project.json` 仍写原文档）；`qaRender` 计算一次，供字幕采样与剪辑点检查；创建/编辑时 `planCaptionFont` 只算一次字体 runs，`editBatch` 对 base 与 next 各算一次。同一视频轨 item 的 `<audio>` 与 `<video>` 用同一个修正后的入点（位移 ≤ 2 ms + 0.1 ms，音画同步不变）。
  - **音频轨** item（包括放在音频轨上的同一视频素材）**不修正**，精确写定的音频入点保持不变。
  - **拆分连续性**：`split_item` 写定的尾段入点 = 头段入点 + 头段时长，一般不在截断容差内，编译后仍等于头段结束处；头段本身被修正时，接缝两侧相差不超过 2 ms + 0.1 ms。
  - **片尾范围**：修正后的入点 + 时长若超出素材时长 + 0.001 s（与 `validateV2` 同一容差 `SOURCE_END_TOLERANCE`），该 item 不修正，保持写定入点。
- **QA**：两项剪辑点检查（烧录字幕、相邻镜头碎片）按编译视图判断（渲染实际起播时间），但**按文档写定值报告与建议**：`measured.points` 的 `source_seconds` 是文档写定值（入点为写定入点，出点为写定入点 + 时长换算的写定出点），`suggested_shift_seconds` 以它为基准（写定值 + shift = 建议值，按 shift 改文档即得到目标帧中点），描述文本中的 “source in X” / “at source X” 也是写定值。入点被修正的 item 另列 `compiled_source_seconds`（编译后实际值，文本中写作 “(compiled X s)”），入点还记录 `source_frame`（修正到的帧号）。未修正的剪辑点不加这些字段，按渲染器口径判断（见下文 QA）。内部剪辑点（`cutPoints`）不携带原 item，需要写定值时用 `correctionOf(point.item)`。
- **真实素材复验**（`byq-foundation-02` 整片，720×1280 30 fps，视频与文件起点均为 0，只读，临时工程已删除）：v2 导入记录 `"30/1"`。item `cut` 入点 24.4333、30 帧，编译为 24.433433333（第 733 帧起点 + 0.1 ms）；预览第 0 帧（`select=eq(n\,0)`）与源第 733 帧（新镜头首帧）MAE 0.89、与第 732 帧 55.0。同工程 item `plain` 入点 60.65（帧内，非截断）编译后仍为 60.65。QA `cut-boundary-fragments` 与 `burned-caption-cut-points` 均为 pass；`cut` 入点记录 `document_source_seconds` 24.4333、`source_frame` 733（碎片检查 aligned），出点记录写定出点 25.4333。
- **局限**：只修正入点，不改输出帧数；帧网格假设第 0 帧位于媒体时间零点、恒定帧率（导入规则已排除不满足的素材）；源帧率与画布帧率不同时，后续帧仍按画布 fps 推进，与原行为一致；入点在帧内但离帧起点很近（如晚 0.001 帧）不属于截断，保持原值。

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
| `rebind_template` | `template` | 把该模板的绑定升级到当前执行层模板字节，**必须单独成批**；模板未被任何 graphic 使用、当前执行层字节与本修订实际渲染所用字节相同（已绑定该字节，或本修订是未绑定的历史修订）即无变化、或使用该模板的 graphic 位于锁定轨道时拒绝 |

规则：

- **整批原子**：先在内存中按序应用全部操作并对结果做完整 `validateV2`，任一失败则不复制素材、不发布。`base_revision` 不是最新修订直接拒绝（需重读），不自动合并。发布沿用硬链接无替换写入，并发写只有一个成功。
- **dry-run** 返回 `diff`：新增/删除/变更的 item id、轨道变化、新增素材 id、新旧成片帧数、模板绑定变化 `graphic_templates {added, removed, changed}`；`add_asset` 只 ffprobe 探测，不复制；不复制模板文件。批次结果另有 `notes`（如历史修订首次获得模板绑定的说明）。
- **锁定轨道**：锁定轨道上的 item 不能被修改、删除或作为移动目标；`split/replace_media/remove_item` 需要改动的 link 字幕所在轨道也必须未锁定。link 字幕的存储数据不变，只随其 media item 的位置自然换算，这不算修改。`revert_to` 若会改变当前任一锁定轨道上的 item（或目标修订缺少该轨道）也被拒绝。锁定轨道上的 graphic 所用模板字节同样冻结：任何批次（`rebind_template`、`revert_to` 等）若会改变它们实际渲染所用的模板字节即被拒绝。锁定冻结的是该轨道自身的 item 与设置（含 `duck` 配置与名称）：`revert_to` 时锁定轨道整体保持当前定义，不被目标修订的轨道对象覆盖。锁定不冻结由被参照轨道派生的闪避包络——被参照轨道（如未锁定的口播轨）的 item 变化时，锁定音乐轨的实际音量曲线会随之重新计算。
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
- **最小字号**：任何文本变量渲染字号 ≥ 3 em = 画布短边的 3%（竖屏 1080 宽 ≥ 32.4 px，720 宽 ≥ 21.6 px）。加载时 `font_em` 小于 3 的字符串变量先被抬到 3 再做上面的放得下校验（抬高后放不下则加载失败）；CSS 里的字号只能写 `font-size:var(--fs-<变量名>)`，编译时由 `font_em` 生成 `--fs-<变量名>:<font_em>em`，且模板 CSS 不得出现 `font` 简写、`zoom`、`transform`/`scale` 属性（含厂商前缀）、`scale()`/`matrix()`、`font-size-adjust`/`text-size-adjust`、对 `--fs-*` 的再定义以及 CSS 注释与转义，因此 CSS 不能绕过该下限。说明：需求表述为“画布宽度的 3%”，竖屏与方形画布上两者相同；横屏若按宽度计（1920 宽需 57.6 px ≈ 5.3 em），现有模板的最长文本放不进框，所以统一按短边计，横屏实际下限为高度的 3%。
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
  - 剪辑点按编译视图的入点判断（见“源素材帧对齐”）：素材带 `frame_rate` 时，低于帧起点不超过 2 ms 且不足 0.1 帧的截断入点已在编译时修正，不再出现下面所述“截断入点显示上一帧”的情形（低于帧起点更多的入点仍按渲染器口径判断）；其余入点与无 `frame_rate` 的素材按以下口径判断。
  - 显示帧口径与渲染器一致：输出第 j 帧显示源时间 `入点 + j × 速度/fps` 处、时间戳 ≤ 该时间的源帧。所以入点显示的是“时间 ≤ 入点”的那一帧——写成 24.4333 的入点（略小于 733/30 = 24.433333…）仍显示第 732 帧；出点（不含）之前最后显示的是“时间 ≤ 出点 − 速度/fps”的帧。比较严格按此口径：入点哪怕只比某帧起点早 1e-7 s 也判为显示前一帧，容差只有 1e-9 s（吸收浮点误差，不向后放宽）。源帧时间不读 showinfo 打印的 `pts_time`（小数位随 ffmpeg 版本变化），而是用每帧的整数 `pts` × ffprobe 读到的视频流 `time_base`，减去各流 `start_pts × time_base` 的最小值（媒体时间零点，同 data-media-start），与 ffmpeg 版本无关。
  - 入点：入点帧之后、入点后 ≤0.5 s（源时间）内出现字幕变化，而入点帧本身不是变化帧 → warn（入点时仍显示上一行字幕）；入点帧正好是变化帧记 aligned。出点：出点前 ≤0.5 s 内、仍会显示的帧上出现字幕变化 → warn（下一行字幕在出点前闪现）；变化帧正好是出点后第一帧记 aligned。`suggested_source_seconds` 是**变化后首帧的帧中点**（该帧与下一帧时间的中点，按源素材帧率，保留到微秒、不再截成 4 位小数）：作入点时首帧就是变化帧，作出点时最后显示的是变化前一帧；写在帧边界或截成 4 位小数的时间可能落在目标帧之前、仍显示上一帧，帧中点没有这个问题。`measured` 记录 `method`、字幕带、阈值和每个剪辑点（item、in/out、源时间、成片时间、结果、附近的字幕变化与镜头切换、`suggested_source_seconds`/`suggested_shift_seconds`）；`refs` 指向成片剪辑点时间、item 与剪辑点采样帧。
  - 阈值实测（`byq-cream-01` 真实口播/实测/促销素材，竖屏 1080×1920 30 fps，只读）：人工核对过的字幕切换 `line_share` 0.11–0.41、亮字形占比 0.066–0.19；手和刷子掠过字幕带的误检 `line_share` 可达 0.12，但亮字形占比 ≤ 0.023，所以亮字形判据取 0.05；真实镜头切换的带外平均差 41–133，同一机位的跳切（字幕同时切换）约 17，所以镜头阈值取 30。在该素材修订 1 上，recap 入点（源 31.47 s）被 warn 并建议 31.60 s；修订 2（入点 31.60 s）记为 aligned，全片 8 个剪辑点无 warn。smoke 中无字幕的测试图案素材不报。
  - 局限：这是帧差启发式，不是 OCR：不能读字幕内容、不能判断字幕与语音是否对应；只识别亮色（白/黄）字幕，深色或彩色字幕、字幕带外的字幕会漏报；字幕淡入淡出、滚动字幕不是一帧阶跃，可能漏报；字幕带内持续静止后突然变化的亮色画面元素（如贴纸、产品特写）可能误报；字幕消失（变为空白）通常不触发。窗口在源时间上计（变速 item 同样按源秒 0.5 s）。无字幕素材应基本不报。解码失败、解码帧数与 showinfo 帧行数不一致、帧行缺少整数 `pts` 或帧尺寸、showinfo 输入时间基与流时间基不符（帧时间不可信）的剪辑点记 unknown，错误写明缺失的字段；解码用 `-fps_mode passthrough`，变帧率素材每帧对应自己的源时间。汇总：任一剪辑点 warn → 检查 warn；否则任一 unknown → 检查 unknown（observation 写明未检查的数量、剪辑点与原因）；全部分析完且无 warn 才 pass。剪辑点窗口默认 4 路并发解码。
- **剪辑点相邻镜头碎片**（`cut-boundary-fragments`，category video）：入点比源素材自己的镜头切换略早，成片开头会带上一个镜头的尾巴（真实素材：入点 22.68 s 而源镜头 23.23 s 才切换，开头 0.55 s 是旧镜头；入点 24.4333 s 略小于 733/30，第 0 帧是旧镜头末帧）；入点落在闪白转场里，开头是几帧白场；出点比源切换略晚，结尾会闪出下一个镜头的开头。对视频轨每个 media item 的源入点与源出点，在**源素材**上解码前后各约 1.5 s（灰度、短边 360 px）。两项剪辑点检查共用一次遍历（`cut-checks.mjs`）：每个剪辑点只解码一次，范围取两项检查所需窗口的并集，各检查只判断自己窗口内的帧；每个源文件只 ffprobe 一次；状态、observation 与 refs 的汇总规则由同一函数 `summarizeCutChecks` 产出，逐帧算整帧平均绝对差 MAD 与平均亮度：
  - 镜头切换判据（阈值与现有检查一致，写入 `measured.thresholds`）：MAD ≥ `shot_mad` = 30（烧录字幕检查的整帧镜头阈值，灰度级），且满足其一：MAD 比上一帧跃升 ≥ `scene_jump` = 场景阈值 × 100 = 30（与成片镜头检测 `--scene-threshold 0.3` 同口径：ffmpeg 场景分数即 min(MAD, ΔMAD)/100），即从运动中突出的硬切；或平均亮度阶跃 ≥ 30，即闪白/淡变帧。快速运镜 MAD 高但平稳、亮度不变，不算切换；ffmpeg 场景分数漏掉的闪白转场（真实素材 126.77–127.00 s）在进、出闪白时亮度阶跃，可以检出。
  - 判定（显示帧口径同上一条）：入点帧之后、入点后 ≤1.0 s 内（且在 item 内）有切换时，只有入点所在镜头**有一部分在入点之前**（入点不在该镜头首帧），且它**大部分在 item 之外**（入点前的部分长于 item 内显示的部分；向前 1 s 内没有切换即视为更长）或该镜头短于 0.5 s（闪场），才记 warn「开头含相邻镜头碎片 N 帧」，`suggested_source_in_seconds` = 切换后首帧的帧中点；紧随其后的短于 0.5 s 的镜头（闪白的出场）一并跳过，`kind` 记 `flash`。出点前 ≤1.0 s 内、仍会显示的帧上有切换时，只有出点所在镜头**有一部分在出点之后**（出点后第一帧不是下一次切换），且大部分在出点之后或短于 0.5 s，才记 warn「结尾含下一镜头碎片 N 帧」，给出 `suggested_frames`（保留到切换前末帧的输出帧数）、`drop_output_frames` 与 `suggested_source_out_seconds`（切换帧的帧中点，作出点时最后显示切换前一帧）。入点帧正好是切换帧（含入点写在该帧帧中点）、或切换帧正好是出点后第一帧，记 aligned：从首帧起显示的镜头（入点前没有它的部分）或显示到末帧的镜头（出点后没有它的部分）即使短于 0.5 s 也是完整的剪辑选择，不报。帧数口径：`fragment_frames` 是**成片**中显示碎片的输出帧数（按渲染器口径，第 j 个输出帧显示源时间 `入点 + j × 速度/画布 fps` 处的源帧，已计入变速与源/画布帧率差异），`source_frames` 另列碎片跨越的源帧数。observation 与建议中的时间一律是帧中点、6 位小数（出点碎片同时给出切换帧帧中点 `change_mid_seconds`；`change_seconds` 是切换帧起点，只作测量记录）。`measured.points` 记录每个剪辑点的源时间、成片时间、结果、附近切换时间与建议；`refs` 指向 item、成片剪辑点时间与剪辑点采样帧。
  - 真实素材复验（`byq-foundation-02`，只读）：修订 1 报 hook 入点 17 帧碎片（建议 23.25 s）与 cta 入点闪场 2 帧（建议 127.016667 s）；修订 2 报 hook 入点 1 帧碎片（建议 24.45 s）；修订 3 不报（hook 出点前 0.88 s 的同人跳切是 0.93 s 的完整短镜头，只少 1 帧，不算碎片）。`byq-cream-01` 修订 2 不报。
  - 局限：帧差启发式，不理解画面内容：低于阈值的同机位跳切、缓慢叠化不检出；大面积快速亮度变化（如闪光灯）可能误报为闪场。窗口在源时间上计。解码失败的剪辑点记 unknown；汇总规则同烧录字幕检查（任一 warn → warn，否则任一 unknown → unknown）。
- **按镜头采样**（`shot-sampled`，category video）：对渲染成片做镜头检测（ffmpeg `select='gt(scene,T)'`，T 默认 0.3，可配置），把成片切成镜头；每个镜头若已有采样帧（item 中点、剪辑点、字幕）则不重复，否则在镜头中点加一帧 `reason: "shot"` 的采样，短镜头（<1 s）同样覆盖。`measured.shots` 记录每个镜头的起止与采样 id；有镜头取不到帧记 fail。局限：crossfade/淡变等渐变转场不产生场景分数峰值，渐变中的镜头边界由剪辑点采样覆盖；阈值以下的跳切（同机位小变化）不单独成镜头。

采样合成后的成片帧（不是源素材帧）：每个 media 与 graphic item 中点、每个视频剪辑点前后各一帧、每条字幕中点、每个尚无采样的镜头中点，PNG 写入 `frames/` 并记 SHA-256。采样按帧号精确提取：粗定位到目标帧前 2 帧后，用 `-copyts` 保留原时间戳、`select='gte(t, (n−0.5)/fps)'` 取第 n 帧并 `-fps_mode passthrough` 原样写出（单纯 `-ss <秒>` 在剪辑点附近会差一帧）；`time_seconds` 记录该帧的帧中点时间 `(n+0.5)/fps`，`s-cut<n>-before`/`s-cut<n>-after` 分别是剪辑点前最后一帧（n−1）与剪辑点后第一帧（n）。用 ffmpeg `tile` 把采样按时间顺序拼成 `contact-sheet.png`：最多 40 张（镜头多于 40 个时为镜头数），超出时先保证每个镜头一张，再均匀抽取其余采样；每个剪辑点前后各 1 秒导出 `clips/cut-<帧号>.mp4` 供听看。

`verdict`：任一 fail → fail；否则有 warn → pass_with_warnings；否则 pass。`review` 初始为 `{status:"pending", reviewer:null, decision:"pending", findings:[]}`，由 Agent 或人工依据采样填写；`unverified` 固定声明人工听检、创意质量、合成画面评审、字幕可读性未验证，以及烧录字幕检查只是帧差启发式。自动检查只反映技术信号：不检测音画同步、字幕与语音是否对应、画面内容是否正确，也不替代对合成画面的评审。

## 验证与限制

`npm test` 覆盖：共享样例（valid 全部通过、invalid 逐文件按违反规则拒绝）、Python 侧附加规则的内联负向用例、11 个操作、批次原子性、过期修订、锁定轨道、dry-run 零写入、split 字幕归属、replace_media 字幕规则、revert_to 单独成批、规范化 operations 摘要、v1 迁移（时序/字幕/音轨分道与截断）与 v2 工程拒绝 v1 操作、多轨编译（z 序/transform/opacity/独立音频/转义）、lint 关卡放行与阻断；P2：16 个新增共享 invalid 样例的拒绝原因、与 Python 对齐的附加规则内联负例（graphic 字段白名单、duck 指向字幕轨、crossfade 起点须严格晚于前驱、全量重叠扫描）、P2 编译（playback rate、volume lane 用 HyperFrames engine/core 解析并取样核对增益、透明度补间、图形转义、变速字幕换算、lint 零发现）、模板与变量类型校验、P2 编辑操作（props、graphic、duck、split/trim 规则、锁定轨道 duck、revert_to 保持锁定轨道的 duck）、512 点 volume 自动化上限在 create 与编辑（含 dry-run）时即拒绝、约 1000 item/100 crossfade/400 段被闪避音乐的编译耗时、安全区布局估算；P2.1：模板命名位置（缺省=旧位置、非法 placement 拒绝、lint 零发现）、最小字号（加载时抬高、抬高后仍须放得下、CSS 只能用 --fs 变量）、烧录字幕剪辑点判定（入点晚于字幕切换 warn 并给出变化时刻、对齐不报、出点前闪现 warn、无字幕素材与错位字幕带不报、整帧镜头切换不算字幕变化）与镜头检测（文件内 0.6 s 短镜头被切出、阈值可配置）；模板固定（0.5.0）：4 个新增共享 invalid 样例的拒绝原因、创建/编辑自动绑定与内容寻址复制、dry-run 只报告不写文件、删除最后使用者时移除绑定、执行层模板变化后旧修订仍按绑定字节编译出相同 HTML、`rebind_template` 的单独成批/未使用/无变化拒绝与升级后使用新字节、绑定文件缺失/篡改/符号链接/校验失败时读取与渲染失败、旧版原始字节绑定的规则差异拒绝、提高最小字号后旧绑定修订 HTML 不变、`revert_to` 恢复目标修订的变量与模板字节（HTML 一致）及未绑定目标的说明、锁定轨道上 graphic 的 rebind/revert 拒绝、未绑定历史修订上的无变化 rebind 拒绝、缺模板集时校验与编译拒绝、编辑批次每个绑定文件只读一次、写一次辅助函数、历史修订用执行层模板（`pinned: false`）且编辑后获得绑定、渲染目录复制绑定文件；源素材帧对齐（0.6.0）：`truncatedFrame`/`correctedSourceIn` 在 30/1、30000/1001、24/1 与 60/1 下只修正低于帧起点不超过 2 ms 且不足 0.1 帧的入点（修正为帧起点 + 0.1 ms；30/1 下 24.433、24.4327、24.4333 均为第 733 帧，恰低 2 ms 修正，24.430 等低于 2 ms 以上与 60/1 下达到 0.1 帧的不修正），帧起点、帧中点与帧内入点保持原值，帧率字符串与解析结果行为一致；帧率解析/约分与导入规则（可变帧率、视频流起点 0.5 s 或缺 `start_pts`、纯音频、封面图均不记录；音频起点为负、文件起点非 0 而视频流起点为 0 时记录；封面图在前时 QA 分析第二条视频流、但不记录帧率；`rational`/`streamStart` 共用）；共享 invalid 样例的拒绝原因；编译只修正视频轨 item（同 item 声音同起点、音频轨 item 不修正、link 字幕随修正后入点换算、文档不被改写、无 `frame_rate` 保持原值）；编译视图单点计算（视图再次传入返回自身、剪辑点与视图 item 及原 item 对应、字体可见字幕随视图）；剪辑点出点的 `document_source_seconds` 为写定出点、剪辑点不携带原 item（写定值经 `correctionOf` 取得）；QA 建议以写定值为基准（`judgeCutPoint`/`judgeFragment` 的 `written`；修正入点 1.2999 的碎片与烧录字幕检查报告 `source_seconds` 1.2999、`compiled_source_seconds` 1.3001，写定值 + shift = 建议的帧中点，文本写 “source in 1.299900 s (compiled 1.300100 s)”）；24/1 素材在 60 fps 画布第 1 帧处拆分后尾段起点等于头段结束处；用到最后一帧的 item 修正后不超出素材时长容差，超出时不修正；`create`/`add_asset` 导入记录 `frame_rate`（含音频起点 −44 ms、视频起点 0 的合成 mkv），而纯音频、带封面图的音频（与以前一致为 `video: true`、封面宽高，v1 工程仍可用作 clip）、起点偏移的视频与 v1 不记录；以及原有的字幕重定位、路径约束、版本冲突、并发发布、父版本变化、输入变化与取消。

`npm run smoke` 用自有测试图案和测试音（无客户素材），输出在根 `dist/local-production/<timestamp>/`：

1. v1 旧流程（以 `createProject(…, { legacyV1: true })` 建立 v1 工程，仅供兼容验证）：五个版本、旧 CLI `edit` 形式、画面/音调信号核对、静音导出与独立音轨。
2. 对该 v1 工程提交 v2 批次：迁移修订 + 编辑修订，迁移修订导出与 v1 导出逐帧比对。
3. v2 多轨：主轨 + 补导入 B-roll（transform 叠放）+ 音乐轨 + link 字幕 + 非 link 字幕；dry-run 不发布不复制、过期修订拒绝、锁定轨道拒绝、split、revert_to；导出后核对 B-roll 框内为 B-roll、框外为主画面、开始前不可见，以及主轨音调与 660 Hz 音乐同时存在。
4. CLI `qa` 生成 `qa.json`。再复制该导出、剥离音轨并改写回执摘要，模拟“声称完成但丢音轨”的导出器，QA 必须给出 `verdict = fail`。
5. P2 品牌包装（`packaging/`，24 fps 1280×720）：标题卡（0–36 帧）+ 下三分之一（76–116 帧）、两段主画面 crossfade（口播 0–72 淡入，色条 60–120 以 12 帧 crossfade 进入）、一段 1.5× 变速（口播源 2.5 s 起）带淡出、音乐轨在主画面轨下 −12 dB 闪避并淡入淡出、变速段上的 link 字幕。断言：lint 0 error/0 warning 且无 `audio_volume_double_automation`、三个 `<audio>` 全为 volume lane、VTT 中变速字幕为 5.667→6.333 s（口播素材记录 `frame_rate: "24/1"`，入点 2.5 s 恰为第 60 帧起点、不是截断小数，编译保持原值）。信号检查：变速段第 132 帧与源 3.25 s 的画面 MAE 远小于与 1× 位置 3.0 s；crossfade 中点（第 66 帧）与两源平均帧的 MAE 远小于与任一单源；淡入首帧为黑、淡出末帧亮度降到 20% 以下；660 Hz 音乐能量在口播区间相对非口播区间约为 depth_db（±2 dB）；音乐淡入首窗明显更低；标题卡与下三分之一区域与下层画面显著不同且含白字与深色底。导出 QA 的 `graphic-safe-area`/`caption-safe-area`/lint 为 pass，`true-peak` 引用 `audio_lowered_db`。人为失败：新增一条 fontHeight 0.08、centerY 0.9 的两行字幕，预览 QA 必须在 `caption-safe-area` 上 fail。
6. P2.1 竖屏 QA（`portrait/`，30 fps 360×640 预览）：合成素材 `captioned.mp4`（移动测试图案 + 约 70% 高度的白色“字形”方块与深色描边，1.5 s 时从 A 行切到 B 行）与 `short-shot.mp4`（0.6–1.2 s 为一段色条短镜头）。item `late` 入点 1.3 s（字幕晚 0.2 s 切换，正例）、`shots` 含短镜头（成片 1.6–2.2 s，远离 item 中点与剪辑点）、`aligned` 入点 1.5 s（负例）；`title-card` 用 `placement: top`、`lower-third` 用 `placement: upper`。断言：lint 0/0；编译 HTML 的位置与 `--fs-*` 字号；`burned-caption-cut-points` 为 warn 且只有 `late` 入点 warn、建议 1.5 s，`aligned` 入点为 aligned；`shot-sampled` pass 且有一帧 `reason: "shot"` 落在 1.6–2.2 s，该帧高饱和像素（色条）占比 > 30%；`graphic-safe-area` pass；`cut-boundary-fragments` pass（`shots` 从文件首帧开始、完整显示 0.6 s 色条短镜头，不算碎片）。前面几个场景的测试图案素材在该检查上都是 pass（无字幕不报）。
7. 源素材帧对齐（`frame-snap/`，30 fps 320×180 预览）：合成素材在第 22 帧（22/30 = 0.7333… s）由红变蓝，入点写成 0.7333。v2 工程导入记录 `frame_rate: "30/1"`、文档保留 0.7333、编译 `data-media-start="0.733433333"`（第 22 帧起点 + 0.1 ms），成片用 `select=eq(n\,0)` 取第 0 帧为蓝（新颜色），`cut-boundary-fragments` 为 pass、入点 `source_frame = 22` 且 aligned（报告写定值 `source_seconds` 0.7333 与 `compiled_source_seconds` 0.733433）；同一素材的 v1 工程（无 `frame_rate`，历史口径）第 0 帧为红（旧颜色），该检查 warn。
8. 以带 jsonschema 的 Python（`CREATIVE_PYTHON`，默认仓库根 `.venv/bin/python`）按 Draft 2020-12 校验全部 v2 修订文件（含品牌包装、竖屏与帧对齐工程）与 7 份 qa.json，缺少 Python/jsonschema 时 smoke 直接失败。

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

图形模板随修订固定（合同见 `docs/content-production-architecture.md`“图形模板固定到修订”）。做法与固定字幕字体相同：按内容寻址把模板 JSON 原始字节复制进工程。

- **绑定**：`create` 与编辑批次产生的新修订只要含 graphic，就为所用模板写入 `graphic_templates` 绑定 `{id, version, sha256, file: "templates/<sha256>.json"}`；首次使用某模板时把执行层模板经最小字号规范化（`enforceMinimumText`）后的确定性序列化字节写入工程 `templates/<sha256>.json`，`sha256` 即这些字节的摘要（临时文件 + 硬链接、不覆盖，已存在且字节相同则复用，写后核对摘要；`templates/` 目录或文件为符号链接即拒绝）。随附模板的源文件本身已是规范化形式，因此与旧版按原始字节绑定的摘要相同。dry-run 不写文件，只在 `diff.graphic_templates.added` 里列出将新增的绑定。
- **不变性**：已有绑定在后续编辑中保持不变，执行层模板升级或规范化规则（如最小字号）变化也不影响；`revert_to` 恢复内容的同时恢复目标修订的绑定（绑定文件仍在工程内，读取目标修订时核对存在与摘要），目标修订是未绑定的历史修订时，其模板绑定到当前执行层字节并在 `notes` 中说明；锁定轨道上的 graphic 因此会改变模板字节时拒绝。删除最后一个使用某模板的 graphic 时移除该绑定（文件留在工程中）；绑定全部移除后字段保留为空数组。
- **升级**：只有 `rebind_template {template}` 能把绑定换成当前执行层字节，必须单独成批；新模板定义下现有 graphic 的变量须仍然合法，否则整批拒绝。
- **历史修订**：没有 `graphic_templates` 的旧修订不被改写，渲染与校验使用当前执行层模板。在其上提交编辑时，若结果含 graphic，新修订为其绑定当前模板字节，并在批次结果 `notes` 中说明。
- **读取与渲染**：`read`/`render`/`qa` 对有绑定的修订只从工程内绑定文件加载模板：核对 sha256、重新执行安全与结构校验（`validateTemplate`，不再做会改写内容的规范化）并核对 version，graphic 变量按绑定的模板定义校验；文件缺失、摘要不符、符号链接或校验失败即失败（读取即失败，因此也无法渲染）。旧版按原始字节写入、且不是规范化序列化的绑定：若当前规范化会改变其内容，按“规则差异”失败而不静默改写，否则按原字节使用。模块接口上模板集是显式的：`loadProject` 返回 `{doc, templates}`，`compose`/`validateV2` 等对有绑定的文档必须传入模板集（`validateV2` 仅在显式 `{structuralOnly: true}` 时只做结构校验）；`read` CLI 输出不变。渲染把绑定文件复制进渲染目录 `templates/`，渲染目录可独立重放。
- **回执**：`templates` 每项为 `{id, version, sha256, pinned, source}`。固定的修订为 `pinned: true, source: "project"` 并带 `file`；历史修订为 `pinned: false, source: "runtime"`（sha256 为执行层模板原始字节摘要），与 `composition_sha256` 一起用于追溯差异。
- Python 侧只校验结构与覆盖规则（同一组共享样例）；模板内容与变量类型仍由 Node 校验。

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
 chosen_attempt, choice_reason, note, segments: [{start, end, text}],
 phrases: [{start, end, text, text_reliable?: false}]}
```

`asr.mjs` 导出 `toPlanEvidence(spans, from, to, method, { segments })`：返回与 `[from, to]` 有重叠的句子（或短语），形如 `{modality: "asr", start_seconds, end_seconds, excerpt, raw_score: null, method}`，时间保留原始边界（不裁到区间）。传入短语时同时传 `segments`：标记 `text_reliable: false` 的短语以其所在句段（重叠最多的 segment）的文本作为 `excerpt`，时间仍是短语自己的，`method` 追加说明“短语文本乱码、摘录为整句”；没有可用句段时报错，不输出乱码摘录。

限制：ASR 文本可能有错字和同音字（如品牌名、人名），引用前需核对；时间戳是句级，不是逐字或逐帧对齐，剪辑点必须人工听审确认。覆盖率只说明“有文字的时间段”，不说明文字正确：whisper 会在纯音乐/持续音调上幻觉出整句（测试中 440 Hz 正弦音被“转写”为一句视频结尾套话并覆盖全程），此时覆盖足够、不会重试，幻觉内容也会进入结果。`auto` 判据只在上述片段上实测，阈值尚未在更多素材上标定。输出文件必须不存在。

`npm test` 中的 ASR 测试只用合成音频（ffmpeg 静音与正弦音、macOS `say -v Tingting`），不含客户素材；whisper-cli 或模型缺失时两项端到端测试跳过并给出原因，模型存在但摘要不符则失败。

**短语级时间（phrases）**：whisper 对背景音乐垫底的密集口播会把十几到二十几秒合成一个句段（segments）。转写改用 `-ojf` 读取词元时间戳，在逗号、句号等标点处切分为 `phrases`。中文标点与 `,!?;` 总是断句；`.` 与 `:` 只在下一个词元不以数字开头、且当前词元不是单个拉丁字母缩写（如 `A.`）时断句，所以 `3.`+`5倍`、`10:`+`30` 不会被切开。词元文本可能把一个多字节汉字拆在两个词元之间，拼出的短语会含替换字符 U+FFFD（句段文本不受影响）：这类短语保留时间，标记 `text_reliable: false`，取证时改用所在句段文本（见 `toPlanEvidence`）。在一条 137 秒的真实素材上，相对云端 ASR 的句末边界：中位偏差 0.09 s，p90 0.66 s；句首中位 0.14 s，个别离群达 3 s。短语只用于**提名**剪辑点，仍需结合能量谷、烧录字幕检查和人工听审确认。

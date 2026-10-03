# 内容与视频制作：参考上游及吸收登记

记录日期：2026-09-20；承接合同更新：2026-09-22。状态：HyperFrames 基础本地执行已实现并通过限定范围技术检查，其余按下述方法吸收/候选状态分别登记。新合同不改变历史验收结果。

本文件是 Creative Craft 内容制作上游的唯一详细清单。DataHub 等宿主引用这里，不维护重复清单。配套：[制作架构](content-production-architecture.md)、[来源政策](source-policy.md)。

## 使用原则

目标是提高 Agent 的创意判断、制作质量与交付效率。参考项目的名气、Skill 数量、README 宣称或演示视频不构成我们的验收证据。方法参考、代码复制、包依赖和服务连接分别记录；登记本身不安装依赖、不建立 submodule、不复制上游 Skills。

每次只吸收一个可验证的能力闭环。优先复用实现良好的执行组件，同时保持 Creative Craft 自己的创作方法、现有合同和宿主边界。上游文本是待研究材料，不能覆盖用户指令、品牌事实或现有工程规范。

状态定义：`reference` 已登记参考；`candidate` 拟验证；`implemented` 已有本地实现；`verified` 已通过注明环境和范围的验收；`deferred` 暂缓。方法吸收与引擎接入分别记状态，不能用文档更新代表运行能力。

## 审阅基线

以下 SHA 是本轮研究固定点，不宣称永远最新。除 Remotion 外，已读取对应说明、部分 Skills 或关键接口；Remotion 读取官方 Skills 与许可说明，固定 SHA 供后续比较。登记初始阶段尚未安装或渲染；后续 HyperFrames 本地执行结果见末尾记录。初始登记时尚无 DataHub 集成测试；当前限定范围的宿主验证见末尾状态更新，不将宿主自有实现归为其他上游的集成成果。

| ID / 仓库 | 固定审阅 SHA | 许可记录 | 初始处置 |
| --- | --- | --- | --- |
| [hyperframes](https://github.com/heygen-com/hyperframes) | `d11907c3255efcf6169c2eb6a5b617284d242a38` | 根项目 Apache-2.0；资源、字体与依赖另核 | candidate：首个执行底座 |
| [chatcut-agent-plugin](https://github.com/ChatCut-Inc/agent-plugin) | `f58a037d82abe0ad6b4163f84dcd8ea8c590d686` | 未确认根仓统一许可；不能推定各子包相同 | reference：工具与编辑方法 |
| [openchatcut](https://github.com/0xsline/OpenChatCut) | `07437f60257a578745262359753bfccce337510c` | AGPL-3.0；依赖和资源分别核对 | reference：协同编辑机制 |
| [openmontage](https://github.com/calesthio/OpenMontage) | `08e2151fa02de28a5d6a312b3d575692bf147ad7` | AGPL-3.0；依赖和资源分别核对 | reference：制作工作流 |
| [remotion](https://github.com/remotion-dev/remotion) | `5321b3687b0e1a4e19f0c11d5959afff473c77c8` | Remotion License；公司使用核对适用条件 | candidate：对照评估，暂不引入 |
| [cerul](https://github.com/cerul-ai/cerul) | `6a76ca302c740851fbcaba5d24d29e094fe9ae16` | Rust 核心 Apache-2.0；工具与模型权重另核 | candidate：片段检索机制 |
| [opencut](https://github.com/OpenCut-app/OpenCut) | `400f097becba5db0fbc305d5a65348cb81c20356` | MIT | deferred：观察重写进度 |

登记 AGPL 或自定义许可证不等于已判定可并入当前分发方式。复制或分发前核对目标文件、修改方式及许可要求；服务接入还需核对服务条款。当前没有复制或分发上述项目源码。

## AIOS 接入归属：2026-09-22

沿用上述固定研究点与历史许可记录，本次没有把未复核上游版本称为最新。七项目全部研究、按能力吸收；不会全部内嵌为七个应用，也不要求都先装入 Creative Craft。

| 参考 | Creative Craft 维护 | AIOS 维护 / 必须验证 |
| --- | --- | --- |
| HyperFrames | 通用制作方法及可选 adapter | 素材解析、Worker、队列/产物；重开、局部修改、预览/导出一致 |
| ChatCut Agent Plugin | 读工程—有界修改—实际检查 | 版本化读写、可见方案、修改保护；工具成功不代替成片检查 |
| OpenChatCut | 人/Agent 接续方法 | 编辑操作、撤销、状态和冲突；不是 ChatCut 官方服务接入 |
| OpenMontage | 参考拆解、分镜、混合制作方法 | 持久生成任务、候选检查与回入工程；来源/连续性/成本 |
| Remotion | 缺口证明后的模板与可选 adapter | Worker 装配、参数/预览/渲染；许可与能力限制先验 |
| Cerul | 检索需求、时间证据与选材方法 | 索引、召回/重排、权限、失效；正确片段可播、可加入工程 |
| OpenCut | 可迁移精修方法 | 时间线、多轨交互和工程组织；保存恢复、人工接续和限制可见 |

采用方式分为方法参考、复制代码、包依赖、账户服务，不能相互冒充。实际采用前核对具体包/文件、版本、许可证、分发/部署方式及回退。AIOS 特定胶水留宿主；仅有明确复用价值且不携带宿主状态的执行适配器进入可选制作包。

本轮优先 AI 剪辑自动交付与可见方案干预，后续 AI 创作采用生成镜头；模型/API 账户能力与完整专业工程各自验证。主 Skill 与重型执行模块分开交付，固定 revision/digest/兼容合同；现有未提交制作模块不因文档登记变成正式发布包。

## 能力级吸收清单

### HyperFrames

- 证据：[剪辑操作](https://github.com/heygen-com/hyperframes/blob/d11907c3255efcf6169c2eb6a5b617284d242a38/skills/hyperframes-core/references/creator-editing-recipes.md)、[播放器](https://github.com/heygen-com/hyperframes/blob/d11907c3255efcf6169c2eb6a5b617284d242a38/packages/player/README.md)、[制作执行接口](https://github.com/heygen-com/hyperframes/blob/d11907c3255efcf6169c2eb6a5b617284d242a38/packages/producer/README.md)、[编辑 SDK](https://github.com/heygen-com/hyperframes/blob/d11907c3255efcf6169c2eb6a5b617284d242a38/packages/sdk/src/index.ts)。
- 吸收目标：源片段选区、重排、音画分轨、图形包装、可嵌入预览、渲染进度、版本固定及输出检查。
- 承接位置：通用剪辑方法、可选 HyperFrames 集成；DataHub 负责项目界面与素材解析。
- 不采用：整套 Skill 全量常驻、自动追随上游升级、默认本地 Whisper 或默认云服务配置。复用宿主转写与既定云端 ASR。
- 能力边界：`talking-head-recut` 当前主要做保持原片的图形包装；删停顿和镜头重排须走实际剪辑路径，不能按 Skill 名推断。
- 验证：中文口播复剪、实拍加生成镜头、图形包装三类项目；重新打开、局部修改、音画同步、预览与成片一致性。

### ChatCut Agent Plugin

- 证据：[项目与编辑模型](https://github.com/ChatCut-Inc/agent-plugin/blob/f58a037d82abe0ad6b4163f84dcd8ea8c590d686/codex/skills/chatcut-plugin-basics/SKILL.md)、[结果验证](https://github.com/ChatCut-Inc/agent-plugin/blob/f58a037d82abe0ad6b4163f84dcd8ea8c590d686/codex/skills/verification/SKILL.md)。
- 吸收目标：先读取当前工程，再执行有界修改，最后重新读取结构并检查合成画面；区分源素材和时间线实例。
- 承接位置：Creative Craft 编辑与检查工作流；项目工具的行为约束。
- 不采用：将插件视作完整开源引擎、推定嵌入编辑器能力、未经验证依赖托管账户服务。
- 验证：用户手动移动镜头后 Agent 继续修改，不覆盖新状态；工具成功不能替代画面检查。托管接入另做账户与接口验证。

### OpenChatCut

- 证据：[固定版本说明](https://github.com/0xsline/OpenChatCut/blob/07437f60257a578745262359753bfccce337510c/README.md)、[许可证](https://github.com/0xsline/OpenChatCut/blob/07437f60257a578745262359753bfccce337510c/LICENSE)。它是独立项目，不是 ChatCut 官方开源版。
- 吸收目标：内置 Agent、MCP 与人工共用编辑操作，工程保存、撤销、任务状态和多轨语义。
- 承接位置：通用工程状态与编辑接口；DataHub 项目编辑交互。
- 不采用：整体搬入本地优先应用、重建账户设置、直接并入 AGPL 源码或默认引入 Remotion。
- 验证：重开工程、撤销、Agent 与人工交替修改、冲突可见；宿主权限与远程素材单独验证。

### OpenMontage

- 证据：[固定版本制作流程](https://github.com/calesthio/OpenMontage/blob/08e2151fa02de28a5d6a312b3d575692bf147ad7/README.md)、[许可证](https://github.com/calesthio/OpenMontage/blob/08e2151fa02de28a5d6a312b3d575692bf147ad7/LICENSE)。
- 吸收目标：参考片拆解、差异化概念、分镜与阶段产物、实拍和生成混合制作、成本可见与成片检查。
- 承接位置：Creative Craft 按需制作工作流与质量评估。
- 不采用：全部工具或 Skill 常驻、每一步强制用户确认、默认下载本地模型、默认开通全部 Provider。
- 验证：由参考片提取可迁移表达方法，使用自有素材形成不同成片；记录重试成本和人工修改量，不复刻参考片独有表达。

### Remotion

- 证据：[官方 Agent Skills](https://www.remotion.dev/docs/ai/skills)、[固定版本许可证](https://github.com/remotion-dev/remotion/blob/5321b3687b0e1a4e19f0c11d5959afff473c77c8/LICENSE.md)。
- 吸收目标：React 参数化合成、帧级时序与程序化渲染的对照方法。
- 承接位置：执行引擎对照评估；仅出现首选引擎无法满足的真实需求时考虑第二适配器。
- 不采用：因前端使用 React 就默认选择、未经对照引入双引擎、将源码可见理解为无限制免费商用。
- 验证：相同素材和脚本的文字排版、字幕、音画同步、修改成本及渲染资源对照；采用前明确许可证条件。

### Cerul

- 证据：[固定版本设计](https://github.com/cerul-ai/cerul/blob/6a76ca302c740851fbcaba5d24d29e094fe9ae16/DESIGN.md)。
- 吸收目标：画面、ASR、OCR 多路召回；保留时间范围与原始证据；模型空间隔离、分阶段缓存与可重建索引。
- 承接位置：Creative Craft 片段请求与证据使用方法；DataHub 负责索引、权限、检索运行和资产身份。
- 不采用：把通用索引窗口当精确镜头边界、把相关分数当概率、假定已有重排、整体复制本地文件库与机器人数据集功能。
- 验证：中文画面/口播/OCR 查询、按使用条件过滤、时间定位、重叠去重、索引重建；旧内容理解不能复用成新投放诊断。

### OpenCut

- 证据：[固定版本状态](https://github.com/OpenCut-app/OpenCut/blob/400f097becba5db0fbc305d5a65348cb81c20356/README.md)。主仓说明正在重写，现有 classic 与新架构应分别评估。
- 吸收目标：后续编辑器交互、插件边界与无界面制作接口。
- 承接位置：未来编辑交互评估，不进入首期依赖闭包。
- 不采用：将计划中的 Editor API、MCP、headless 能力当作现成工具。
- 重评触发：相关能力发布可运行版本，并通过实际导入、编辑、保存、导出测试。

## 吸收与更新记录

每次后续吸收在本文件追加有界记录：能力 ID、问题与预期收益、上游固定路径/版本、许可处理、承接文件、实现 revision、执行环境、测试素材与场景、真实结果、剩余限制、回退方式。只在对应证据完成后升级状态。

运行依赖采用实际验证过的版本；登记的研究 SHA 不自动成为依赖版本。升级、接口变化、回归失败或明确的新任务触发重新比较，不自动 merge/pull 上游。

2026-09-20 初始登记快照：完成以上七项文档登记与定向源码/说明研究；当时所有能力保持 reference/candidate/deferred，尚无集成或真实成片验收。后续实现与验收以以下更新为准。

## HyperFrames 本地执行 MVP：2026-09-20（初始验收快照）

- 能力 ID：`hyperframes-local-edit-render`；状态 `implemented`，合成媒体技术检查 `verified`；真实业务素材及宿主接入未验收。
- 承接：[可选本地模块](../integrations/local-production/README.md)。依赖 `@hyperframes/producer@0.8.53`、`gsap@3.13.0`，锁文件固定实际依赖闭包；没有复制上游 Skill 或引擎源码。未提交源码，无实现 commit 可引用。
- 实测修正：producer 安装包的执行签名与 README 不同；宽高由 composition 定义控制；捕获层 stdout 日志需在 CLI 入口转向 stderr。
- 验证：Node 24/macOS、独立 Chrome 渲染进程、FFmpeg；版本化工程、源时间字幕、重排/裁切、640×360 预览及 1280×720 导出。合成媒体取样验证画面与音频源区间；中文抽帧可读。
- 证据：本地 `dist/local-production/2026-09-20T04-50-43-468Z/` 的工程、回执、成片、signal-checks.json；运行 `npm run smoke` 可重建等价技术样例。回执不宣称人工听检或创意质量验收。
- 剩余限制：尚无自然语言规划器、业务素材质量验收、复杂多轨/转场、长时长性能、隔离 worker 或 DataHub 集成；本模块不进入根 Skill 发布包。回退停用该可选模块即可，旧核心合同和原媒体不变。


## 宿主验证状态更新：2026-09-20

本节更新上述初始快照；固定审阅 SHA 和许可记录未重新审阅，不据此宣称上游最新状态。核对对象为本地源码、DataHub 验收记录与已落盘回执；未重新运行测试，也没有可引用的本次实现提交。登记七个项目不等于七个项目都已接入。

| 能力 / 所属实现 | 当前证据 | 仍未证明 |
| --- | --- | --- |
| HyperFrames / Creative Craft 可选模块 | DataHub 实际 HTTP、身份、工程版本、队列、worker、真实缓存原片渲染及签名产物读取通过本地隔离联调；回执固定 producer 0.8.53 | 云端 TOS、生产部署、完整人工音画及创意质量验收 |
| 台词分镜 / DataHub | 已有选择素材范围、台词检索、模型候选校验和可编辑时间线；实际模型客户端通过本地模拟服务验证 | 真实模型创意质量；不是 ChatCut 服务接入或通用编辑 Agent 验收 |
| 镜头目录 / DataHub | 原片剪切候选、代表帧、目录导入和站内提取队列已有隔离验证；绑定原片 hash、时间与权限 | 剪切候选不等于准确识别所有镜头；不是 Cerul 引擎接入 |
| 代表帧语义与检索 / DataHub | 有限镜头选择、语义任务、取消、证据绑定及目录范围关键词检索已实现；本地 Ark 模拟 HTTP 服务及浏览器接口夹具分别验收 | 未进行真实付费视觉模型调用；单帧不证明动作、声音、完整多模态召回或识别准确率 |
| Seedance 混合制作 / 后续方向 | 分镜可列出缺失镜头需求 | 尚无生成任务、产物回入工程和真实混合成片闭环 |

证据定位（DataHub 仓库内，不复制业务素材、内部地址或原始日志到本仓库）：

- 行为、配置与限制：`docs/CONTENT_PRODUCTION_LOCAL.md`。
- 分阶段验收：`.trellis/tasks/09-20-content-production-workbench/verification.md`，重点为 catalog import、shot extraction queue、station semantic jobs/search 三节；任务归档后以宿主文档指向的归档记录为准。
- 宿主本地回执：`.cache/content-production-acceptance/catalog-real-http-e2e/receipt.json`、`semantic-jobs-http-e2e-verified/acceptance.json`；这些忽略目录不是可分发或永久公开证据。
- 最后核对的前后端综合检查记录为 295 项通过，其中 246 项缓存命中；浏览器使用接口夹具，与真实 HTTP/worker 隔离测试是不同证据层，均不等于生产验收。

上述宿主能力不自动成为共享 Skill 或可选模块的公共 API，也不证明已安装、提交或发布。源码仓库、安装版 Skill、宿主本地实现和生产运行分别核验。

## 下一批吸收与验收（计划，尚未完成）

| 优先级 / 参考方向 | Creative Craft 应沉淀的通用能力 | DataHub 承接 | 完成条件 |
| --- | --- | --- | --- |
| P1 / ChatCut、OpenChatCut | 读取当前工程 → 有界修改 → 重读结构 → 检查结果；明确素材与时间线实例 | 版本化编辑接口、人工编辑和冲突展示 | 人工先移动片段，Agent 重读后继续编辑；陈旧版本拒绝写入；检查实际成片。现有版本冲突检查只能算其中一项 |
| P1 / Cerul | 选片理由与证据引用，区分台词、代表帧观察、时序推断和复用建议 | 语义索引、权限过滤、源身份与时间定位 | 按中文画面/台词查询，结果可追溯到原片；变化来源失效，建议不冒充观察。当前关键词检索只覆盖部分条件 |
| P2 / OpenMontage | 参考拆解、缺口镜头 Brief、已有与生成镜头的连续性约束和成片检查 | Provider 任务、预算、产物入库与时间线替换 | 用已有素材加一个新生成镜头完成成片；局部替换保留工程其余内容，记录来源、成本和人工修改 |
| 持续 / HyperFrames | 已支持编辑操作的稳定编译、预览、导出与检查 | 固定模块、执行隔离及产物访问 | 相同工程可重开再修改；预览/导出时序一致；真实中文字幕、音画和失败恢复均有证据 |
| 条件触发 / Remotion、OpenCut | 保留对照与重评入口 | 只有当前执行器遇到具体限制时评估 | 先记录缺口，再用同一素材/脚本比较，不默认引入第二引擎 |

成熟方法按需沉淀到已有 video-production、iteration-and-versioning 等参考模块；只有现有模块无法承接时再拆新文件。SKILL.md 保留入口与路由，不把这些计划写成已可调用的运行能力。

### 方法沉淀更新：2026-09-20

ChatCut / OpenChatCut 参考方向已形成通用的
[读取工程、限定修改与检查结果方法](../skills/creative-craft/references/video-production.md#editing-an-existing-project)，
以及[共享工程版本处理规则](../skills/creative-craft/references/iteration-and-versioning.md#shared-project-revisions)。
覆盖源素材与时间线实例区分、人工修改保护、版本冲突、结果不明时的重试、局部恢复及实际音画检查。
这是方法文档的吸收，未复制上游实现、增加执行接口或证明接入上游服务；上述 P1 宿主完成条件仍需实际验收。

Cerul 参考方向已补充[片段检索与证据选片方法](../skills/creative-craft/references/video-production.md#evidence-grounded-footage-selection)：
从分镜用途形成检索需求，保留源身份与时间范围，区分 ASR、OCR/代表帧、实际音画观察和复用建议，
处理重叠候选与过期分析，并在回看后确定剪切边界。选片理由应说明可复用的创意机制，不能把检索分数或视觉吸引力当作投放效果。
该更新只沉淀 Agent 使用证据的方法；未接入 Cerul 引擎、增加索引或完成多模态检索验收。

OpenMontage 参考方向已补充[已有素材与生成镜头混合创作方法](../skills/creative-craft/references/video-production.md#mixing-existing-footage-with-generated-shots)：
把分镜映射到可用素材与缺口，明确生成目的、参考职责、前后镜头连续性与验收条件；生成产物先作为候选检查，再按工程版本局部替换并检查拼接结果。
方法同时区分生成 Brief、真实 Provider 任务、候选资产和已检查的成片，保留来源与成本信息。
该更新未增加 Seedance 等 Provider 连接器、执行生成或完成混合成片的宿主验收；表中的 P2 完成条件仍待验证。

本地真实素材的目录与画面抽查进一步暴露了语句跨镜头的验收风险：镜头切换不能证明语句结束，字幕和转写分段也不能替代听审。
已在选片方法中补充镜头范围与语句范围分离、保留完整语义、跨画面连续原声的时序与字幕检查，以及宿主不支持独立音轨时的替代方式。
这是由候选段落检查得到的方法修订；未完成连续听审或新的重剪成片验收，未将私有素材内容写入共享 Skill。

## 证据刷新边界：2026-09-22

AIOS 的本轮只读检查观察到媒体渲染/提取容器已运行，并发现规划/语义开关仍关闭。该宿主当前快照由其 `docs/autonomous-content-production/README.md` 维护；这里不复制客户配置或原始日志。它更新了“尚无任何部署基础”的历史判断，但没有证明完整自主剪辑、真实模型质量、云端全链路或 50 条/日和单条时延通过。

本次仅统一两份架构/参考文档的接入归属和验收，不重跑旧媒体测试、不新增上游依赖、不发布能力包。2026-09-20 各节继续作为当时的证据快照保留。

## 上游复核与方法补充：2026-10-02

触发：为视频剪辑 Agent 设计“读工程—有界修改—检查”与选片检索层而重新比较。固定审阅 SHA 不变，均可解析；本节记录固定点与 2026-10-02 当日 HEAD 的差异，不把 HEAD 视为新的固定点。

| 上游 | 当日 HEAD | 相对固定点 | 已吸收能力是否受影响 |
| --- | --- | --- | --- |
| ChatCut Agent Plugin | `877b9177144f` | 历史被重写，与固定点无共同祖先 | 否：`codex/skills/verification/SKILL.md` 与固定点逐字一致；basics 的数据模型和读取分层仍在。今后用文件级 diff，不能依赖 compare API |
| OpenChatCut | `d03acbd6c7b1` | 多 101 个提交、288 个文件 | 否：`assets/agent/openchatcut-tool-schemas.json` 编辑工具 122 个、只读 ask 工具 23 个，名单不变 |
| Cerul | `e93237887eaa` | 多 5 个提交 | 否：`DESIGN.md` 的 30 s 索引单元、60 s ASR 窗、1 fps OCR 采样及融合公式不变 |
| OpenCut | `e66801077856` | 多 1 个提交（FFmpeg CI） | 否：仍为重写期 Rust 桌面壳与 web 路由占位；Editor API、MCP、headless 只在 README 路线图。classic 版未评估，维持 `deferred` |

本次核对的固定路径（方法参考，未复制源码）：

- ChatCut：`codex/skills/chatcut-plugin-basics/SKILL.md`（Asset/Item 分离、帧单位、同轨不重叠、默认留 gap、ripple 只作用同轨；`read_project`→`preview_timeline`→`inspect_item` 分层读取，省略字段是未知而非空）、`codex/skills/verification/SKILL.md`（重读受影响范围 + 检查合成帧，修改成功不是视觉证据）。
- OpenChatCut：`src/editor/reducerHistory.ts`（整工程快照 undo，上限 100，连续手势合并，batch 为一步）、`src/editor/clipTypes.ts`、`src/editor/trackTypes.ts`、README 的 MCP 节（`begin_edit_session`→隔离草稿→`review_edit_session` manual/auto→原子提交为一步 undo；生成、导出、删除等不可回滚工具不进入草稿会话）、`edit_item{adds,updates,deletes,ripple,validateOnly}`、`verify_export`。AGPL-3.0，只吸收方法。
- Cerul：`DESIGN.md` §5–7、`schemas/search-result.json`、`schemas/fusion-moment.json`（hit 含源时间、score、matched、excerpt、`fusion_recipe`、逐条 `fusion_evidence{track,raw_score,rank,value,contributes}`；过滤先转时间区间再排序；sidecar 为真源，索引可零模型调用重建）。

方法吸收：在[读取工程、限定修改与检查结果方法](../skills/creative-craft/references/video-production.md#editing-an-existing-project)补充分层读取、校验/预览与单批提交、不可回滚操作移出草稿、结构检查清单及“源帧只证明选片、不证明合成”；在[证据选片方法](../skills/creative-craft/references/video-production.md#evidence-grounded-footage-selection)补充按模态保留分数与贡献证据、记录检索方法版本、硬约束先过滤再排序。均为方法文档更新，未增加执行接口，状态不升级。

供 AIOS/DataHub 评估的接口草案（不是 Creative Craft 公共 API，未实现）：

- 编辑操作集 v2（≤15，全部以帧为单位，写操作带 `base_revision` 与 `dry_run`，返回 diff 和新 revision）：读 `read_project`、`preview_timeline`、`inspect_items`、`render_frames`；写 `add_clip`、`remove_clip`、`move_clip`、`trim_clip`（含 slip）、`split_clip`、`replace_media`、`set_clip_props`、`edit_track`、`apply_script`；控制 `commit/undo`（一个事务一步）、`verify`（结构检查 + 合成帧 + 导出质检）。
- 选片检索返回：`{recipe_version, space_id, hits:[{asset_id, source_revision, source_start_ms, source_end_ms, score, matched[], evidence:[{track, raw_score, rank, norm, contributes, excerpt, start_ms, end_ms}], preview_frame, scene_id}], stale_excluded, capability_gaps}`，源时间为半开区间，可直接传给 `add_clip`。

剩余限制：上表 P1 宿主完成条件仍未验收；未运行任何上游代码。下次复查仍按“升级、接口变化、回归失败或新任务”触发，并优先比对上面列出的固定路径。

## 持续吸收机制与当前状态：2026-10-02

### 机器真源与检查

[`upstream-watch.json`](upstream-watch.json) 是固定研究 SHA、监控路径、上游路径到本仓库文件的映射，以及当前吸收状态的机器可读真源。前文「审阅基线」表保留为 2026-09-20 历史快照，后续更新以 watch 文件加本文件的日期记录为准，两者在同一提交中修改。

`make upstream-check`（即 `scripts/upstream_drift.py`）只读运行：对每个监控路径比较固定 SHA 与上游默认分支的文件 blob 或目录清单（不依赖 compare API，ChatCut 这类历史被重写的仓库也适用），并比对 HyperFrames 的 npm 最新版本与 `integrations/local-production/package.json` 中的锁定版本。`--offline` 只校验 watch 文件，并由 `tests/test_upstream_drift.py` 在常规测试中执行，本地文件重命名导致映射失效时会测试失败。脚本需要已登录的 `gh` 和网络，不进入 `validate-all`。

### 复查流程

触发：开始新一期 video harness 工作前、准备发布前、依赖升级或回归失败时；没有触发时可按月运行一次。

1. 运行 `make upstream-check`，只处理标记 `REVIEW` 的项目。
2. 对每个变化路径阅读实际 diff，归入以下一类：无影响（措辞、示例）/ 方法更新（改 `video-production.md` 等参考文档）/ 实现候选（进入 harness 计划，按正常测试与证据验收）/ 许可或边界变化（暂停该项吸收并重新评估）。
3. 在本文件追加日期记录：路径、上游新 SHA、分类、结论与承接文件。文件有变化不等于需要吸收。
4. 只有完成复查后，才把 watch 文件中的 `pinned_sha` 更新为已审阅的上游 SHA；已实现能力的状态只能凭对应提交和测试证据升级。npm 依赖升级另需 `npm test`、`npm run smoke` 与字体集成测试全部通过。
5. AGPL 项目（OpenChatCut、OpenMontage）只吸收方法；Remotion 采用前先复核许可证条款。

### 当前吸收状态（替代 09-20 初始处置）

| 项目 | 状态 | 已承接到 | 方式 |
| --- | --- | --- | --- |
| HyperFrames | implemented | `integrations/local-production`：EditDocument v2 编译、渲染、lint 关卡；依赖固定 `@hyperframes/*@0.8.108` | 包依赖 + 方法 |
| ChatCut Agent Plugin | implemented | 素材与实例分离（edit-document v2）、修改后重读并检查合成帧（render-qa、`qa.mjs`）、`video-production.md` 编辑循环 | 方法 |
| OpenChatCut | implemented | 整批原子编辑、`--dry-run`、批次 `operations_sha256`、锁定轨道（`operations.mjs`、`project.mjs`）；轨道角色与自动闪避留待 P2 | 方法 |
| OpenMontage | implemented | 代码强制阶段关卡、审批、交付承诺实算、先预留后结算的预算台账（`creative_craft_video.py`、production-plan） | 方法 |
| Cerul | implemented | 选片证据按模态记录、保留原始分数和检索方法（production-plan `selection.evidence`）、`video-production.md` 选片方法；未接入索引引擎 | 方法 |
| Remotion | candidate | 无；仅在 HyperFrames 无法满足具体需求且许可证适用时评估为模板引擎 | 对照 |
| OpenCut | deferred | 无；可运行的 Editor API、MCP 或 headless 发布后重评 | 无 |

`implemented` 表示已有本仓库实现与自动化测试，验证范围限于合成素材，不代表真实业务素材、创意质量或宿主生产已验收。上一节「供 AIOS/DataHub 评估的接口草案」现已部分落地为 local-production 编辑批次：操作名和粒度以 [Video Harness v1](content-production-architecture.md#video-harness-v1) 为准，`render_frames`/`verify` 对应 `qa`，`apply_script` 尚未实现。

### 首次运行结果（2026-10-02）

需复查：HyperFrames（编辑配方、CLI skill、lint/inspect 参考、SDK 类型、timeline 命令有变化；npm 最新版与锁定版同为 0.8.108）、ChatCut（basics 一行变化）、OpenChatCut（`reducerActions.ts`、工具 schema）、Remotion（`packages/skills`）、Cerul（`DESIGN.md`）。无变化：OpenMontage；OpenCut 的监控路径不变。

已复查：ChatCut `codex/skills/chatcut-plugin-basics/SKILL.md` 的唯一变化是 `inspect_item` 改为每次最多 10 个 item，归类为无影响；其余项目尚未复查，固定 SHA 保持不变。

### 首次复查结论（2026-10-02）

按上述流程复查了首次运行标记的全部变化，逐文件阅读两版内容。结论：现有实现均无需改动；HyperFrames 与 Remotion 为 P2 提供输入。复查后 watch 文件的固定 SHA 更新为：HyperFrames `70900216f0da`、ChatCut `877b9177144f`、OpenChatCut `d03acbd6c7b1`、Cerul `e93237887eaa`、Remotion `579e314165ce`；OpenMontage 不变；OpenCut 监控路径无变化，保留原固定点。

| 项目 / 路径 | 分类 | 结论 |
| --- | --- | --- |
| HyperFrames `creator-editing-recipes.md` | 实现候选（P2） | 上游默认改为视频自带声音（`data-has-audio="true"`），独立 `<audio>` 只用于 J/L 切、替换音轨、配乐与旁白；转场和闪避的音量写在 `data-automation` volume lane，不与音量补间并用（lint 规则 `audio_volume_double_automation`）；变速 0.1–10 并有 `rate` lane。均已含于锁定的 0.8.108（本地 `core/dist` 中 `MAX_PLAYBACK_RATE = 10` 已核实），P2 无需升级。我们现有“静音视频 + 独立音频”仍有效；若 P2 迁移到视频自带声音，先加 `data-has-audio` 严格取值的回归测试 |
| HyperFrames `hyperframes-cli/SKILL.md` | 方法更新 | 新增 `history`（试行）与 `clean`；我们不经 CLI 驱动，`render.mjs`/`qa.mjs` 不受影响 |
| HyperFrames `lint-validate-inspect.md` | 方法更新 | 新增 `canvas_content_at_edge`（CLI `check`，本地 lint 包不含）；P2 图形模板若用 canvas 绘字需另行检查贴边 |
| HyperFrames `packages/sdk/src/types.ts` | 观察 | `setTiming.linked`、`moveIntoSync`/`slipIntoSync`（`data-link`/`data-sync-origin` 视音链接与失步修复）需 ≥0.8.109，npm 尚未发布；我们不依赖 SDK，暂不吸收 |
| HyperFrames `cli/commands/timeline.ts` | 方法参考 | `--plan` 预演与回执撤销，与我们的 `--dry-run`、原子批次一致；不依赖 CLI |
| HyperFrames 0.8.108 producer | 实现候选（P0 补强） | 新增 `audioLoweredDb`：真峰值限幅压低整段混音时记录（本地 `producer/dist` 已核实）。`qa.mjs` 的真峰值检查可引用它作为限幅证据 |
| ChatCut basics | 无影响 | 仅 `inspect_item` 改为每次最多 10 个 |
| OpenChatCut `reducerActions.ts` | 无影响 | 新增 `durationFps` 与仅空时间线可用的 `tl.setFps`；我们的源时间为秒、fps 为固定枚举 |
| OpenChatCut 工具 schema | 无影响 / deferred | `edit_item`（validateOnly、整批原子）与 `verify_export` 定义及工具名单不变；新增 Fal 生成目录超出范围；`import_timeline`（FCPXML/EDL）记为未来工程交换参考 |
| Cerul `DESIGN.md` | 无影响 | 仅命令清单与 CI 文案；索引单元、采样与融合公式不变 |
| Remotion `packages/skills`（4.0.526→4.0.532） | 方法参考 | `LICENSE.md` blob 不变，维持 candidate。P2 可参考：音量关键帧（淡变、闪避）、带可编辑类型化 props 的独立时间线组合（图形模板）、转场统一提前挂载。监控路径已细化为 `remotion-markup/{transitions,audio,timing-props,connected-compositions}.md` |

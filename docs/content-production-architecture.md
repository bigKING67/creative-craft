# Creative Craft 内容制作架构

日期：2026-09-22。状态：通用方法与可选本地执行已有部分实现；AIOS（原 DataHub）工作区重构为待实施合同。宿主已有媒体容器运行观察，不等于完整制作、真实模型质量或生产性能验收。

配套：[上游吸收登记](upstream-absorption.md)、[现有架构](architecture.md)、[运行方式](operating-model.md)。本文件描述新增方向，不将未来能力改写为当前 API。

## 目标与当前差距

Creative Craft 是可被不同 Agent 与产品调用的创意制作能力。目标是更好的构思、脚本、选片、剪辑与实际成片，同时支持电商、品牌、口播等短中视频。AIOS 是首个业务宿主，历史记录中的 DataHub 指其原工程；核心能力保持跨宿主通用性。

现有 Brief、Concept Routes、Creative Direction、Copy Sheet、Brand/Reference Binding、Image/Video Job、Receipt、Inspection、Revision 和 Delivery 合同可以复用。核心 Python CLI 做校验、提示词编译和证据管理；没有直接模型调用、片段搜索服务或视频渲染器。Provider Profile 描述能力，不能证明账户已可调用。

可选的 [local-production 模块](../integrations/local-production/README.md) 已实现独立本地工程、版本化编辑、字幕/音轨及 HyperFrames 预览和导出。当前为源仓库可用的基础执行工具；除合成媒体检查外，DataHub 已通过宿主适配调用该模块完成真实缓存素材的本地隔离渲染。模块本身不包含自然语言规划器、DataHub 连接或真实业务创意验收；宿主适配存在不等于核心内置连接。其 local-edit/local-render 实验合同与现有正式交付合同分开，不能据此推进既有项目的 approved/delivered 状态。

Quick Craft 保持默认轻量路径。简单文案、概念或局部修改无需创建完整项目文件；真正制作与反复修改视频时，由宿主在后台保存必要工程状态。通用内容无需虚构商品、促销或转化目标。

## AIOS 产品接入：先剪辑，后创作

宿主将现有素材库的“视频创作”重构为 AI 剪辑，再增加 AI 创作。Agent 是宿主结合专业方法、模型 API、受控工具、持久任务与检查形成的执行能力，不要求聊天界面或独立 Creative Craft 服务。

AI 剪辑以已有画面为基础，支持智能成片、口播精剪、多素材混剪、原片改版、高光/摘要、批量变体；默认一条。AI 创作后续结合已有素材与经账户验证的 Seedance 等生成能力。平台投放与经营自动化不是普通制作的前置条件，通用方法不要求虚构商品或 ROI。

方法输出可见的制作方案，含结构、来源选择、字幕声音、保留/改变与缺口。默认自动执行，用户可选先看方案，也可暂停后修改、锁定满意部分和重新制作。宿主持有 plan/project revision 与执行版本，迟到结果不得覆盖用户新方案；Creative Craft 只基于最新快照提出有界编辑和检查意见。

## 三层职责

| 层 | 所有权 | 明确边界 |
| --- | --- | --- |
| 核心 Skill 与方法 | 需求理解、创意路线、参考片拆解、分镜、选片策略、剪辑决策、质量检查与迭代 | 不含特定宿主数据库、账户、对象存储和投放表结构 |
| 可选制作集成 | 工具调用、引擎编译、生成/渲染执行、进度与结果转换 | 不让网络、Node、Chromium、FFmpeg 变成轻量 Skill 安装的强制依赖 |
| 业务宿主 | 素材身份、检索、权限、存储、队列、界面、成本配置和效果数据 | 调用固定版本的能力包，不维护另一份分叉 Skill |

现有 Python 标准库核心与 v1/v2 合同继续兼容。制作集成采用独立可选模块；现有 `adapters/` 是 Agent 宿主发现与接入说明，不直接混入渲染引擎实现。已实现的首个可选执行集成为 HyperFrames，FFmpeg 负责媒体预处理及底层编码；Seedance 仍是生成或修改镜头的待接入方向。

## 交付与包边界

轻量方法包、可选制作执行包分别发布，后者才携带 Node/Chromium/FFmpeg 或引擎依赖。当前根包 files 不包含 `integrations/local-production`；AIOS 已用内容摘要锁快照装入自己的媒体镜像，不等于安装主 Skill 就获得制作模块，也不等于该模块已正式发布。

正式制品需要记录源码 revision、制品摘要、合同版本和兼容范围，并验证包内实际文件。AIOS 构建加载固定版本，运行时不读取个人 Skills 或临时更新上游；在途任务继续原锁，不兼容明确失败，升级/回退只改变新任务默认值。

通用适配器只接收经过宿主解析的确定媒体、工程输入及执行限制，返回产物/回执。认识 AIOS 数据库、素材权限、队列或预算的代码留在 AIOS；不因可能复用就提前增加公共框架。Creative Craft 不维护宿主的第二套工程或成功状态。

Commerce Growth OS 拥有经营策略和内容组合的专业方法，Creative Craft 接收其适用输出并发展概念、脚本和制作；宿主映射既有 Brief、Copy、EditDocument、Inspection，避免另造同义对象。每项交付一个主责，简单任务不强制完整策略流程。

## 制作流程与分析层次

主流程：需求 → 创意与脚本 → 分镜 → 搜索候选素材 → 选择/生成镜头 → 工程编辑 → 实际预览与检查 → 修改 → 导出 → 复盘。

按需工作流包括素材混剪、口播编辑、品牌/产品视频、参考片再创作、内容变体和成片检查。一个 Agent 可以完成多个步骤，不为每个角色默认启动独立 Agent。

分析区分：

1. 内容事实：画面、语音、文字和真实时间范围。
2. 创作判断：表达作用、可复用优点、节奏与连续性。
3. 效果诊断：投放或传播数据、比较窗口和证据边界。
4. 制作决策：具体片段、脚本修改、生成镜头和编辑动作。

整条素材表现好不能直接证明某个片段有效。品牌、口播和电商共享事实层，使用不同目标的评价；缺效果数据时仍可制作和评价内容，不虚构业务提升。

## 宿主能力接口方向

下表是跨宿主语义接口方向，不是已上线 endpoint 或 MCP 工具名。DataHub 已实现其中部分宿主能力，但尚未沉淀为 Creative Craft 通用工具接口；具体状态见下文与吸收登记。实现时先复用现有合同，只有新行为确实无法表达时再增加版本化类型。

| 能力 | 输入与结果 |
| --- | --- |
| 检索片段 | 意图、素材范围、时长及使用条件 → 稳定资产/版本/片段引用、起止时间、匹配证据与可用性 |
| 读取素材证据 | 精确引用 → 转写、画面、OCR、品牌事实与来源；未知项保持未知 |
| 创建制作任务 | Brief、分镜、引用、输出目标与预算 → 可恢复任务 ID 与状态 |
| 读取/修改工程 | 工程 ID、预期版本及有界编辑操作 → 新版本、变更摘要或明确冲突 |
| 生成镜头 | 已选参考、修改/保持约束、Provider 能力与预算 → Provider 任务、产物及执行回执 |
| 预览/渲染/检查 | 确定工程版本 → 进度、实际产物、检查证据与失败原因 |

宿主提供经过权限校验的素材解析器；公共核心只认识稳定引用。signed URL 是临时传输地址，不作为永久资产身份。API 密钥、内部地址及客户素材不进入公共仓库或共享 Skill。

## 工程状态与可编辑性

每个创作项目关联 Brief、分镜、素材引用、生成任务和工程版本。Agent 与人工使用同一编辑接口；提交基于预期版本，冲突时重读，不能覆盖用户刚完成的调整。

采用宿主持有的版本化剪辑描述作为受支持时间线操作的真源。引擎 HTML/配置为编译产物；自定义图形片段同时保存源文件和可编辑参数，以组件引用接入。首期不承诺任意 HTML 都能无损还原为可视化多轨编辑。

源时间与成片时间分开保存，源切点依据真实媒体时间戳校正。素材替换、变速、删段时同步更新相关音轨和字幕。导出固定工程版本及素材 hash，预览或重新渲染不悄悄采用最新素材。

继续复用 Receipt、Inspection 和 Revision 语义。生成、剪辑、渲染是不同任务，不能把合成任务伪装成一次 Video Job 模型生成；历史合同只读兼容，不自动迁移或批准。

## 执行约束

- Skills 固定受审阅版本、按需加载；不把上游自动更新、安装或默认 Provider 策略直接带入宿主。
- 长任务运行在隔离 worker；浏览器预览与生成代码不获得 DataHub 页面会话或服务端秘密。项目文件范围、网络访问和运行资源按任务限制。
- 宿主已有队列负责调度；重试先核实远端任务状态，保留幂等标识和计费记录，不因超时盲目重发生成请求。
- 各阶段保存可恢复结果，失败或取消不写成功回执；预算耗尽停止新的付费动作并保存已有候选。
- 技术结构检查、实际画面/听检和创意评价分别记录。模型自评不能冒充人工验收，单次成功不能变成普遍创意规律。

## 验证与实施顺序

独立制作和宿主局部接入已有基础；下一步验证 AIOS 自动剪辑及方案中途修改，随后真实生成混合制作。效果回流属于后续经营扩展。先验证已有 HyperFrames/FFmpeg 路径及普通编辑快路径，不预先实现多个引擎适配。

共同样例：口播删段加 B-roll 与中文字幕；品牌片加入新生成镜头和图形包装；电商片输出不同开场版本。每类都验证预览、再次编辑、重开工程、导出和来源追踪。

对照固定同一组素材、Brief 和输出约束，比较当前 Creative Craft 与升级后的表达质量、素材适配、剪辑连贯性、人工修改量、耗时和成本；分别记录模型、Skill、引擎版本。只有真实输出和检查证据才能证明质量改善。

设计文档阶段后已实现独立本地 MVP；DataHub 的项目、台词分镜、原片分析段落检索、镜头提取队列、目录导入、代表帧语义任务和目录范围关键词检索已有本地实现与限定验证。真实模型创意/识别质量、时序多模态检索、Seedance 混合成片、公共接口沉淀、正式制品发布、目标环境完整制作与负载仍待后续验收。现有未提交工作不因此被覆盖或发布。


## 当前接入状态与下一步

详细状态与证据定位统一见 [宿主验证状态更新](upstream-absorption.md#宿主验证状态更新2026-09-20)。DataHub 提供的队列、索引和界面留在宿主；Creative Craft 可复用的是创作/编辑方法、片段证据使用规则与可选制作集成。单帧描述不是动作识别，文字关键词匹配不是完整视频 RAG，模型模拟服务通过也不是识别质量通过。

下一批优先补通用编辑流程和选片证据合同，再验证已有素材与生成镜头混合制作。范围、承接与完成条件见 [下一批吸收与验收](upstream-absorption.md#下一批吸收与验收计划尚未完成)。这些是待办方向，不改变现有 API、Skill 加载方式或发布状态。

## 宿主性能与方法收益的验收边界

AIOS 首期目标约 10 用户、每天 50 条合格成片；已分析素材、30—60 秒/1080p，含排队 p50 ≤3 分钟、p95 ≤5 分钟是宿主待实测目标，不是 Creative Craft 对所有宿主的性能保证。1/2 渲染槽、10 用户突发、冷素材和复杂工程各自测量，容量以宿主 `docs/autonomous-content-production/05-capacity-cost-and-operations.md` 为真源。

对照人工/既有规则、仅经营方法、仅创作方法与组合方案，使用同一输入和质量标准；经营方法对照限有相关业务任务的样本。报告成片盲评、事实错误、总耗时、返工与人工分钟，以及方法加载/执行的额外成本。组件安装成功、容器运行或短样片不代表专业质量提高。

业务经验留宿主；通用方法候选经脱敏、跨任务验证和仓库评测后发布。生产 Agent 不直接修改共享 Skill、权限或验收标准。本次文档同步未更新 Skill、模块代码、包清单或任何宿主运行配置。

## Video Harness v1（2026-10-02，实施中）

承接上文三层职责，把“需求 → 分镜 → 选片 → 生成 → 工程编辑 → 实际检查 → 修改 → 导出”落成代码强制的流程。参考依据见[上游复核 2026-10-02](upstream-absorption.md)：阶段关卡与交付承诺（OpenMontage）、素材/实例分离与合成画面验证（ChatCut）、批次编辑与试运行（OpenChatCut）、lint/抽帧/检查（HyperFrames）、按模态证据（Cerul）。只吸收方法，不复制 AGPL 源码；Remotion 与 OpenCut 维持原处置。

### 分层与真源

| 层 | 内容 | 位置 |
| --- | --- | --- |
| 共享合同 | `creative-craft.edit-document.v2`（多轨剪辑真源）、`creative-craft.render-qa.v1`（成片技术检查与评审） | `skills/creative-craft/schemas/`；跨语言语义一致性样例在 `tests/fixtures/edit-document-v2/{valid,invalid}/` |
| 证据与关卡（Python 核心） | `creative-craft.production-plan.v1`（分镜每拍的来源、选片证据、交付承诺）、`creative-craft.video-production.v1`（阶段状态、产物 digest、审批、修改轮次、预算台账、事件） | Skill 包内，仅标准库 |
| 执行（可选 Node 模块） | EditDocument v2 读写与有界编辑、编译到 HyperFrames、预览/导出、QA 采样与检测 | `integrations/local-production/`，不进 Skill 包 |

EditDocument v2 是剪辑真源；HyperFrames HTML 只是编译产物，不反向解析。v1（`local-edit.v1`）旧修订保持只读；首次对 v1 工程提交编辑时在内存中迁移并发布 v2 新修订（`change.author = migration` 记录在该修订），旧文件不改写。

### EditDocument v2 语义规则

- 素材（asset）与时间线实例（item）分离；同一素材可被多处引用。工程创建后可通过 `add_asset` 继续导入（含生成镜头，`origin.kind = generated` 并记录 `provenance_ref`）。
- 轨道 `video | audio | caption`，数组顺序即视频叠放顺序（靠前在下）。`locked` 轨道上的 item 不可被任何操作修改。
- 输出时间为 canvas.fps 下的整数帧，半开区间；源时间为秒。同一轨道上的 media item 不可重叠，允许空隙。
- media item 必须有 `asset_id/start_frame/frames/source_in_seconds/volume`；视频轨要求素材含画面，音频轨要求含声音；`source_in_seconds + frames/fps ≤ asset.duration`。
- caption item 只能在 caption 轨：`link` 形式按所链接 media item 的源时间换算输出时间并随其移动、裁切；无 `link` 时必须给 `start_frame/frames`。`link.source_to > link.source_from`。
- 成片时长 = 所有 media item 与非链接字幕的最大结束帧，1 帧至 10 分钟。
- 字段按类型互斥：media item 不得带 `text/style/link`；caption item 不得带 `asset_id/source_in_seconds/volume`；音频轨 item 不得带 `fit/opacity/transform`；link 字幕不得带 `start_frame/frames`。`revision > 1` 必须有 `parent_sha256`，`revision = 1` 必须为 null。字幕之间允许重叠。
- 以上规则在 Node（`integrations/local-production/edit-document.mjs`）与 Python（`creative_craft_contracts.py`）各实现一次，由 `tests/fixtures/edit-document-v2/` 共享样例强制一致；新增规则必须同时补样例。

### 编辑操作（P0）

一次调用提交一个批次：`{ base_revision, author, summary, operations[] }`。整批校验通过才发布新修订；`--dry-run` 只返回 diff（新增/删除/变更的 item、时长变化）不发布；基于过期修订提交直接拒绝，需重读。操作：`add_asset`、`add_track`、`edit_track`（lock/unlock/rename）、`add_item`、`remove_item`（可选同轨 ripple）、`move_item`（改轨或起点）、`trim_item`（入/出点，或 slip 只移源入点）、`split_item`（链接字幕随之拆分归属）、`replace_media`（保持时序，未给新字幕则移除旧链接字幕）、`set_item_props`（volume/fit/opacity/transform/text/style）、`revert_to`（以旧修订内容发布新修订，必须单独成批；不解除当前锁定，也不能改动当前锁定轨道的内容）。修改轨道锁定状态的 `edit_track` 必须单独成批，避免“先解锁再修改”藏在同一批次中。转场、变速、淡入淡出、音乐自动闪避、图形模板属于 P2。

### 检查（P0）

`qa` 针对某一修订的实际渲染文件生成 render-qa：结构（时长/分辨率/音轨与修订一致）、视频（ffmpeg blackdetect/freezedetect）、音频（silencedetect、ebur128 响度与真峰值）、字幕（每条字幕时段内有采样帧）、lint（编译 HTML 的 HyperFrames lint，错误即阻断渲染）。采样合成后的成片帧（每个 item 中点、每个剪辑点前后、每条字幕），生成缩略图墙和剪辑点前后短片供听看。自动 `verdict` 只反映技术检查；`review` 由 Agent 或人工依据采样填写，发现须指向时间/item/采样，critical 须附修复方案。工具成功、源素材帧或自动检查都不能代替对合成画面的评审。

### 阶段与关卡（P1）

阶段：`brief → reference → plan → select → generate → assemble → inspect ⇄ revise → export`，可显式跳过（须给理由）；跳过与完成同样受前序顺序和产物漂移约束，`select/generate` 在绑定计划前不可跳过。关卡由 Python CLI 执行，不依赖提示词：

- 前序未完成或未跳过，后续不能完成；需审批的阶段（默认仅 `plan`，宿主可配置为空以自动执行）在审批前停在 `awaiting_approval`。
- `plan`：产物通过 production-plan 校验。`select`：每个 `footage` 拍都有选定源区间与证据，`tbd` 拍阻断；仅有候选证据的标为 candidate 并在状态中可见。已审批的计划文件不可覆盖，select/generate 阶段的计划修改须另存新文件；与 plan 阶段计划相比，除填写 selection、generation_ref 及 tbd 改为具体来源外的结构变化（增删或重排拍、作用、时长、约束、锁定拍的选片、交付承诺、输出规格）会使该阶段转为待审批并列出差异。`generate`：有 `generate` 拍时须绑定 Job/Receipt，否则不可完成（可改计划并记录决策）。
- `assemble`/`revise`：绑定 EditDocument v2 修订文件 digest。`inspect`：render-qa 必须绑定当前修订 digest；`verdict = fail` 或评审 `revise/reject` 进入 `revise`；`revise` 轮次超过上限（默认 3）进入 `blocked` 交人处理，不强制放行；人工决定继续时用 `video-extend-rounds --by --reason [--rounds 1–3]`，提高 `policy.max_revision_rounds`（上限 20）并写入事件。
- `export`：导出修订必须等于最近一次检查通过（`verdict ≠ fail` 且评审 `accept`）的修订；导出阶段还须绑定实际交付文件及其 `render.kind = export` 的 render-qa（同一修订、`render.sha256` 等于交付文件、`verdict ≠ fail`），预览检查不能代替导出文件检查；可机器检查的交付承诺（时长范围、含字幕、生成镜头占比上限）对该修订实算，不满足则阻断。
- 预算台账先预留后结算；`cap` 模式下预留超过上限即拒绝；结果不明的付费任务不得自动重发。

简单的局部修改（单次裁切、换一句字幕）走执行层的“读取—编辑—检查”快路径，不需要建立 production 状态。

### 分期与验收

- P0 执行底座：EditDocument v2、操作 v2、`add_asset`、v1 迁移、多轨编译、QA 与 lint 关卡、HyperFrames 升级评估。验收：共享样例两侧一致；smoke 覆盖多轨 B-roll、补导入素材、过期修订拒绝、锁定轨道、QA 产物与失败阻断。
- P1 流程与合同：production-plan / video-production 合同与 CLI、关卡、交付承诺实算、样例与评测，`video-production.md` 增加阶段路由。验收：口播删段 + B-roll + 中文字幕样例端到端可追溯，含一次修改轮。
- P2 包装与音频（转场、变速、淡变、闪避、带类型变量的图形模板）：音量包络统一用 HyperFrames `data-automation` volume lane，变速用 `data-playback-rate` 与 `rate` lane（0.8.108 已支持），图形模板参考 Remotion 的类型化 props；输入见[首次复查结论](upstream-absorption.md#首次复查结论2026-10-02)；P3 Seedance 生成适配与预算台账实接；P4 可选本地素材分析 sidecar。

以上为实施合同；各项能力以对应提交、测试与实际渲染证据为准，本节不宣称已完成。

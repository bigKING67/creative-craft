# creative-craft

面向真实创意任务的创意策略、创意导演、生成式图片与视频生产、评估迭代和交付治理系统。

```text
理解语境 -> 发展路线 -> 锁定导演方案 -> 生产执行 -> 评估迭代 -> 交付复用
```

## 它不是什么

`creative-craft` 不是“提示词大全”，也不是把“高级感、电影感、质感”
堆进提示词里。它解决的是从模糊想法到完整作品之间缺失的专业链路：

- 到底要解决什么传播任务；
- 面向谁，抓住什么矛盾、情绪或欲望；
- 创意洞察、核心主张、创意概念和执行形式分别是什么；
- 多条创意路线是否真的不同，而不是只换颜色和风格；
- 图片、视频、文案、声音和渠道版本如何共用同一套创意母体；
- GPT Image 2 与 Seedance 应该怎样接收结构化任务；
- 生成结果哪些是客观观察，哪些只是主观判断或效果假设；
- 哪些内容应该保留、放大、精修、重构、重新生成、重剪、重拍、测试或放弃；
- 最终文件、版权、肖像授权、参考素材、提示词、版本和交付规格如何追溯。

## 与 design-craft、review-craft 的边界

- `design-craft`：产品 UI/UX、交互、设计系统、动效和前端实现质量。
- `review-craft`：软件工程审查、证据验证、整改决策和项目质量治理。
- `creative-craft`：传播创意、内容创意、视觉与视频导演、生成式媒体生产和创意评估。

三者可以串联，但不互相吞并。比如广告落地页的“创意方向”由
`creative-craft` 提供，产品界面体验交给 `design-craft`，代码工程质量再交给
`review-craft`。

## 核心方法：CRAFT

- **C — Context / 语境**：目标、受众、产品、证据、资产、约束、版权和渠道。
- **R — Routes / 路线**：产生真正不同的创意机制，并明确选择理由。
- **A — Art direction / 导演**：锁定信息、视觉、叙事、表演、镜头、声音、
  参考素材角色和不可变项。
- **F — Fabrication / 制作**：生成或编辑图片、视频，检查真实输出并记录。
- **T — Testing / 测试**：比较、精修、适配、交付、测量，并回流到下一轮。

完整流程为：

```text
界定任务 -> 盘点事实 -> 补充研究 -> 锁定 Brief -> 创意发散
-> 路线选择 -> 创意导演 -> 图片/视频制作 -> 检查真实结果
-> 定向修改 -> 多渠道适配 -> 交付 -> 复盘沉淀
```

## 主要模式

- `understand`：理解想法、Brief、参考或已有成品。
- `brief`：创建或修复创意权威。
- `concept`：发展、区分、比较和选择创意路线。
- `direct`：创意阐述、视觉导演、Treatment、分镜、镜头、文案层级、
  动效和声音设计。
- `image`：GPT Image 2 图片生成或编辑任务。
- `video`：Seedance 视频生成、参考生成、续写或编辑任务。
- `campaign`：从一个母创意扩展为跨平台、跨规格、跨内容形态的系统。
- `critique`：只读创意评估。
- `refine`：对已授权方向或结果做定向优化。
- `adapt`：尺寸、构图、渠道、语言和版本适配。
- `deliver`：检查文件、规格、版权、来源、命名和交付清单。

## 专业性来自哪些约束

1. **先建立权威，再谈审美。**
2. **先讲传播策略，再讲风格。**
3. **创意路线必须是机制不同，不是换皮。**
4. **模型能力放 Provider 层，避免 Seedance 或 GPT Image 更新后核心失效。**
5. **每份参考素材必须声明控制角色。**
6. **编辑任务必须写清“只改什么”和“绝不改什么”。**
7. **客观观察、创意解读、效果假设和最终决策严格分开。**
8. **迭代默认一次只改变一个主变量。**
9. **评分必须有证据覆盖，缺 Brief、版权或交付规格时不强行打分。**
10. **提示词、输入资产、模型、版本、输出规格和文件校验值可追溯。**

## 项目权威文件

- `BRAND.md`：长期品牌权威。
- `CREATIVE.md`：本次创意任务权威。
- `DELIVERABLES.md`：渠道、规格、版本、文案和交付权威。
- `asset-ledger.json`：素材来源、用途、版权、肖像授权和校验值。

小任务不强制全部创建，但缺失内容必须标为假设，不能被 Agent 偷偷补成事实。

## 当前版本

`0.1.0` 已包含：

- 完整 Skill；
- GPT Image 2 与 Seedance 2.5 Provider Profile；
- Brief、图片任务、视频任务、资产台账、评分和交付清单的数据协议；
- JSON Schema；
- 提示词编译、任务校验、评分、文件哈希和项目初始化 CLI；
- 虚构高端洗护案例；
- 测试与 CI。

本版本默认不直接调用模型、不产生费用。它先把“创意决策和执行协议”做好。
后续再分别接入图片和视频 API，避免仓库退化成某个平台的薄封装。

## 开始使用

```bash
python3 scripts/validate.py
```

运行 CI 使用的完整 JSON Schema 校验：

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate_schemas.py
```

只检查可安装 Skill 运行包：

```bash
python3 skills/creative-craft/scripts/creative_craft.py self-test
```

初始化项目：

```bash
python3 skills/creative-craft/scripts/creative_craft.py seed \
  --target /path/to/project
```

编译 GPT Image 2 图片任务：

```bash
python3 skills/creative-craft/scripts/creative_craft.py compile-image \
  --file examples/premium-haircare-launch/image-job.json
```

编译 Seedance 视频任务：

```bash
python3 skills/creative-craft/scripts/creative_craft.py compile-video \
  --file examples/premium-haircare-launch/video-job.json
```

查看创意评分与证据覆盖：

```bash
python3 skills/creative-craft/scripts/creative_craft.py score \
  --file examples/premium-haircare-launch/evaluation.json
```

## 最重要的一条

最终交付不能只说“提示词已经写好”。必须区分：

- 已计划；
- 已生成；
- 已看到真实输出；
- 已完成定向修改；
- 已按规格检查；
- 已确认版权与授权；
- 已完成最终交付。

没有看到的结果，不得被描述成已经实现。

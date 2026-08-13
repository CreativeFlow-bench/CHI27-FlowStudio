# FlowStudio 原型理解与前后端开发规格 v1.2

状态：讨论稿，可直接用于前后端拆分与接口评审  
日期：2026-07-30  
依据：`UI Design/` 全部 UI 稿与 User Flow、工具标注图、当前前端实现、FlowStudio 后端模型与 CreativeFlow 生成链路

增量实现规格：More Creative 的“当前 3D 语义目标 → Wikidata first-hop 临域 → Getty AAT / AskNature second-hop → 无偏好打分的可选词片”采用 `FLOWSTUDIO_CONTEXTUAL_DIVERGENCE_FRAGMENT_PIPELINE_V1_ZH.md`。两者冲突时，该增量规格仅覆盖 More Creative 的检索顺序、词片数据契约和前端呈现；Intent、Planner 确认门与完整生成主链仍以本文为准。

v1.2 新增：

- 六种直接操作工具之后增加 `Cross-domain Diverge`：以当前整体内容为 source，在保留对象身份与已确认约束的前提下进行跨领域类比发散；
- 右侧星形按钮明确为 `Compose / Save Intent`：把多个左下角工具产生的 behavior、文本、图片和模型引用编组并保存为一个可编辑的 `Intent Draft`；
- `Compose / Save Intent` 只负责保存意图草稿，不立即调用 Planner；`Send` 才提交整个意图片段进行推测、确认和介入；
- 一个意图必须保留其组成 behavior 的顺序、目标、证据和回溯关系，不能只保存 Planner 总结后的单句文本。

v1.1 校正：

- 底部是一个由六种明确操作工具、多模态输入、“整体跨领域发散”、“组合/保存意图”和“发送”组成的意图表达区；
- Planner 是隐藏在界面背后的核心推理层，不应被实现成占据右栏的普通聊天机器人；
- 右栏下半部分不是通用标签推荐器，而是按具体维度组织的类比发散空间；
- AI 介入之前存在“Planner 推测意图 → 用户确认是否接受该意图”的控制门；
- 完整入口同时包括白模库编辑，以及空白界面的文本、参考图和模型输入。

## 0. 一句话结论

FlowStudio 是一个面向 3D 创作的混合主动式 AI 共创工作台：

> 用户用 Hover、Brush、Annotation、Drag、Smooth、Add、自然语言、参考图和已有模型共同表达意图；隐藏的 Planner 将多条行为组织成一个意图片段，推测用户想改变的对象、范围、属性和操作方式。用户确认 AI 的理解后，系统再沿具体的类比维度介入并生成多样内容。

它的核心不是“输入一句 prompt，AI 返回一个模型”，而是保存完整的共创闭环：

```text
多条直接操作 + 语言/图片/模型输入
→ Compose / Save Intent 保存可回溯的意图草稿
→ Planner 组织行为片段并推测意图
→ 用户接受、纠正或拒绝该意图
→ 对应的 AI 介入
→ 按具体维度给出类比发散方向
→ 2D/3D 候选
→ 人的比较、采纳、拒绝和继续编辑
→ 更新后的行为记忆与下一轮推测
```



## 1. 我对原型界面的理解



### 1.1 中央 3D Canvas：当前工作对象

中央是主要操作区，显示当前 active asset。用户可以：

- 旋转、缩放、平移和重置视角；
- 通过 Hover 获取鼠标指向位置的部件语义；
- 用 Brush 刷选部件并在3d几何上类似于雕刻绘制内容；
- 用 Annotation 在 2D 画布上画目标轮廓、箭头、文字或其它标记；
- 用 Drag、Smooth 和 Add 表达 3D 几何修改意图；
- 临时预览候选，而不立即覆盖当前对象；
- 接受候选后，将其提交为新的 active asset 或新的创意方向记忆，并在无限画布上向右侧延伸，用虚线链接。

原型中的雪人不是静态展示图，而应当是可交互 3D 对象。候选预览与正式提交必须分开。

### 1.2 左上 Perception：AI 对用户行为的实时观察

该面板展示的是 AI 对“用户此刻在关注什么、做什么”的简短判断，例如：

```text
正在观察整体结构
反复检查头部与身体的比例
正在涂刷鼻子附近区域
似乎希望保留连接边界
```

这不是 AI 的最终意图结论，而是对可观测行为的低阶描述。它的推理需要通过检索和映射得出结果，证据来自我们的intent database：/Users/primav/Documents/博一/CHI27-FlowStudio/intentdatabase，包括几类计算的证据：

- 相机轨迹与停留位置；
- 用户不停地旋转空间，对视口的放大和缩小；
- 鼠标悬停、点击、涂刷和拖拽；
- 当前选中部件；
- 操作的重复、撤销、暂停与比较行为；
- 用户自然语言和图片输入；
- 最近接受/拒绝的候选；
- 语义上下文的迁移距离；
- 用户的2d绘制内容及文字理解；
- 用户使用3d绘制内容；
- 当前的3d上下文；

面板应允许查看“为什么这样判断”，并在低置信度时使用“可能、似乎、正在尝试”等措辞，不能把推测写成事实。

上线实现口径：

- `intentdatabase` 不是用来把当前对象硬匹配到某个历史案例；它是一个 design-state IR，用来根据界面操作信号判断用户当前处于什么设计状态；
- 在线检索字段只能包含抽象后的 `design_state`、`signals`、`route`、`scope_hint` 和 `recommended_axes`，不能把 `software`、`task_group`、`episode_summary`、原始 `observed actions` 等硬案例身份字段放进 runtime retrieval text；
- UI 可显示 IR 推理出的 `Next axes`，例如 `Structural / Aesthetic`，以及低调的 source case 作为审计来源；不能把 source case 当作面向用户的主要结论；
- More Creative 的维度选择应优先使用 IR 聚合后的 `recommended_axes / axis_scores`，再结合已确认意图、当前部件、文本和参考图生成 prompt tokens。

### 1.3 右上角 Solution Space：创意空间

顶部横向卡片是本次发散过程的候选内容空间。每张卡片对应一个候选或mesh，并至少包含：

- 缩略图；
- 透明背景png前端展示；
- 候选名称或方向名称；
- 当前状态：生成中、可预览、已接受、已拒绝、已保存；
- 来源阶段：silhouette、rough form、part、texture；
- 来源行为/意图；
- 点选后生成 3D mesh，从解空间进入到主画布，可以使用动画表达正在生成；
- 可选的匹配度、差异度和边界兼容度。

默认只显示 5～8 个最相关候选，支持横向滚动。点击卡片只进入临时预览；“接受”才拉一条虚线连接第一版本的原始3d mesh，进入迭代的version2。

它同时承担轻量历史作用，但长期建议升级为无限画布分支3d查看图：

```text
source
├── 更可爱：candidate A（接受）
│   ├── 更短更宽：candidate A1
│   └── 更柔软材质：candidate A2
└── 更夸张：candidate B（拒绝）
```



### 1.4 右侧 AI Behavior：Planner 的理解、澄清与介入反馈

根据完整 UI flow，这个区域不应只被理解为静态 `Scene Context`。它是 Planner 面向用户的可见反馈层，按当前状态可以显示三类内容：

1. 对象/场景理解：简短描述 对象类别、形态、材质、颜色、部件和空间关系；
2. 意图推测：Planner 认为用户可能想改变什么，例如 `More Creative? 并且隔一定时间需要冒出来一句主动交互，类似于文用户是否需要灵感，如果需要则进入意图判断模式`；
3. 澄清或介入：要求用户确认对目标部件、功能、材质进行发散的相关关键词，可以进行点选。

UI 中出现在对象附近的 `Nose Change? / Scarf Change?` 及确认/否定按钮，也是同一个 Planner clarification 的空间化呈现，而不是独立的手工标注功能，并且在2d前端界面的最上层成为串珠泡泡形式悬浮在对向周围，直到进入下一轮编辑就保存在一个对象周围。

内部数据仍然必须区分：

- `observed_facts`：可以从几何、相机、语义部件和输入中直接获得的事实；
- `intent_hypotheses`：Planner 的一个或多个意图假设；
- `clarification`：需要用户确认的歧义；
- `intervention`：意图确认后系统准备执行的介入；
- `confidence/evidence`：置信度和证据。

不要把完整 Planner 做成右栏聊天窗口。右栏只是 Planner 的结果出口；行为聚合、上下文融合、类比检索和提示词扩展，和介入决策都在背后完成。

### 1.5 右下 More Creative：具体维度上的类比发散

该区域展示的是 Planner 根据已确认意图计算出的“类比发散方向”和可点击提示词片段，不是一般性的灵感标签，也不是最终生成结果。v1 中这里的核心作用不是直接调用 CreativeFlow 原本的结构化迁移 pipeline，而是把跨领域类比转译成一组人可读、可选择、可组合的词或短语；用户选择这些词片后，它们会被拼合到底部 prompt，再由用户明确触发图片/3D 生成。

UI 稿明确出现三个主要维度：

- `Aesthetic`：造型气质、审美语义和视觉风格类比；
- `Functional`：功能、用途、affordance、材料—功能关系的类比；
- `Structural`：轮廓、比例、构成、连接和部件结构类比。

维度不是固定同时显示。Planner 应根据目标层级和操作证据选择：

- 用户观察整体、画整体轮廓或输入“more cute”时，优先给出 `Aesthetic + Structural`；
- 用户关注或刷选部件时，优先给出 `Functional + Structural`；
- 用户添加一个体积但未说明用途时，Planner 先问“这个体积的功能和材料是什么”，确认后再给出 `Functional + Structural`；
- 材料不是必须独立成第四个一级栏目，可作为 Functional/Aesthetic 类比中的属性轴；以后证据充分时再扩展一级维度。

每个方向必须具有可追溯的类比结构，并派生出 3-6 个可选 prompt tokens：

```text
source：当前对象/部件/形态
relation：要迁移的功能、结构或审美关系
analogy target：类比来源或目标概念
transfer rationale：为什么这个类比适用于当前意图
constraints：哪些身份、边界或非目标区域必须保持
prompt tokens：可被用户点击组合的短词/短语，如 “soft toy proportion”“layered dessert rhythm”“rounded wobble base”
```

方向/词片的点击行为：

- 单击方向：展开解释，查看类比来源、关系、迁移理由、作用范围和约束；
- 单击词片：选择或取消一个 prompt token；
- 再次单击：取消；
- 选择一个或多个词片后：系统把它们附加到底部自然语言 prompt；
- 用户点击 `Send` 或生成按钮后：才把 final prompt 发送给图片/3D 生成链路；
- 若用户不选择词片：不生成，也不改变当前模型。

因此，More Creative 是一个“Planner 输出的 prompt 扩展/组合器”，不是自动生成器，也不是 CreativeFlow 旧 KG pipeline 的前端包装。



### 1.6 底部 Intent Composer：六种操作工具与两种提交动作

左下角六个工具必须按 UI 标注实现：


| #   | 工具           | 交互语义                                                               | Planner 接收到的关键证据                    |
| --- | ------------ | ------------------------------------------------------------------ | ----------------------------------- |
| 1   | `Hover`      | 根据鼠标位置识别并显示部件语义                                                    | raycast hit、part id/label、停留时间、相机视角 |
| 2   | `Brush`      | 3d笔刷，在3d表面进行绘制                                                     | surface mask、笔刷半径、覆盖率、笔刷轨迹形态、多视角截图  |
| 3   | `Annotation` | 2D pencil，在画布上画目标形状、箭头、文字或标记                                       | screen stroke、投影位置、OCR/草图语义、关联部件    |
| 4   | `Drag`       | 拖动 3D 部件、区域或控制柄                                                    | 3D 起终点、方向、距离、作用半径、目标部件              |
| 5   | `Smooth`     | 对局部 3D 几何表达平滑意图                                                    | 作用区域、强度、笔刷轨迹、边界保持                   |
| 6   | `Add`        | 添加 Plane/Cube/Circle/UV Sphere/Ico Sphere/Cylinder/Cone/Torus 等基础体 | primitive 类型、位置、尺度、朝向、与原对象关系        |


其中：

- `Annotation` 是 2D 笔刷/画布空间输入；
- `Brush`、`Drag`、`Smooth`、`Add` 与 3D 对象或表面发生关系；
- `Hover` 是部件语义展示和关注点采集机制；
- 工具产生的是 Planner 的意图证据，实时立即修改模型，并保留。
- 需要有撤销功能；

六种工具之后增加一个独立的整体发散入口：

- `Cross-domain Diverge`：以当前 active asset 或当前已选择的整体内容为 source，直接请求 Planner 进行跨领域类比发散。它不是第七种几何编辑工具，也不直接生成模型；它先提取当前对象的身份、整体形态、功能、材料、部件关系和已确认约束，再返回可解释、可选择的跨领域方向和 prompt tokens。用户选择不同词片后，系统把词片拼到底部 prompt，由人决定是否继续生成。

操作区最右侧两个按钮：

- `Compose / Save Intent`：把当前尚未编组的一个或多个 behavior，以及当前文本、图片和模型引用，保存为一个 `Intent Draft`。保存后仍可继续添加、删除、排序或编辑 behavior，也可以继续新一轮工具操作；
- `Send`：将已保存的 `Intent Draft` 连同场景快照与历史上下文封装为 `Intent Episode`，提交给 Planner。未保存的临时操作必须先由用户确认是否一起加入，不能静默丢失。

按钮语义必须严格区分：

```text
完成一次或多次 Hover / Brush / Annotation / Drag / Smooth / Add
→ 自动形成 ActionAtom[]
→ Compose / Save Intent
→ 保存为 Intent Draft（不调用 Planner）
→ 用户检查、补充、删除或调整 behavior 顺序
→ Send
→ 提交 Intent Episode 并调用 Planner
```

一个保存后的 Intent Draft 在界面上可折叠为对象附近的串珠/气泡标识。展开后应显示：

- 意图草稿名称或用户文本；
- 包含的 behavior 数量与工具类型；
- 每条 behavior 的目标部件、时间和缩略证据；
- 文本、图片或模型引用；
- 编辑、继续添加、删除和发送操作。

自然语言、参考图片和模型输入同样属于 Intent Composer：

- 空白入口：输入文本、上传参考图、上传模型；
- 编辑过程中：文本与当前行为共同表达修改意图；
- 图片：可以是对象参考、局部形态参考、审美参考或功能参考；
- Planner 必须判断图片在本轮的角色，不能默认所有图片都是 style reference。

输入不是独立聊天，而是结构化的多模态行为包。例如：

```text
Intent Episode
├── intent draft: “整体更可爱，但底部保持稳定”
├── text: “让这个雪人更可爱”
├── behavior 1: Hover 整体观察 12 秒
├── behavior 2: Annotation 画出三角形外轮廓
├── behavior 3: Add 一个 Cube 放在雪人下方
├── image reference: optional
├── active asset / camera / part semantics
└── recent accepted and rejected candidates
```

#### 1.6.1 整体内容的跨领域发散

`Cross-domain Diverge` 面向的是当前整体设计内容，而不是当前鼠标下的单一部件。默认 scope 为 `whole_object`；只有用户显式选中局部或 Planner 要求澄清时，才切换为 `part`。

其目标不是给出宽泛的风格词，而是寻找其它领域中可迁移的结构、功能、材料行为或审美关系。例如：

```text
source：三层雪人，圆润、上小下大、围巾连接头身
identity constraints：仍可识别为雪人；保留三层主体和脸部

跨领域方向 A：不倒翁
relation：低重心、自稳定、圆弧底座
transfer：把整体比例和底部结构迁移为可摇摆的稳定形态

跨领域方向 B：层叠甜点
relation：层级、软质体积、装饰性边缘
transfer：把三层身体转化为更柔软、更可爱的层叠节奏
```

Planner 至少输出：

- `source_domain` 与 `target_domain`；
- 被迁移的 `relation`；
- `transfer_rationale`；
- `preserved_constraints`；
- 对整体 Aesthetic / Functional / Structural 的影响；
- 与已有方向的语义距离和重复度。

该入口仍受用户控制门约束：

```text
Cross-domain Diverge
→ Planner 分析整体内容与约束
→ 展示跨领域方向、迁移理由和可选 prompt tokens
→ 用户选择/拒绝/固定若干词片
→ 被选词片拼入底部 prompt
→ 用户确认 final prompt 后才生成 2D/3D 候选
```



### 1.7 策略 Planner：系统的核心能力

Planner 至少需要回答七个问题：

1. 用户当前在操作什么对象、部件或范围？
2. 每条行为是实际编辑、示意、约束、参考，还是探索？
3. 多条行为与语言/图片之间是互补、冲突还是歧义？
4. 用户想要 AI 做何种介入：不介入、澄清、整体跨领域发散、轮廓发散、局部语义替换、体积/功能发散或候选生成？
5. 应沿哪些类比维度发散，并保持哪些约束？
6. 类比发散应转换成哪些可被人选择的关键词/短语？
7. 用户选的这些关键词该如何稳定拼成 final prompt，并把选择证据写入生成日志，方便之后复盘人的创意路径？

Planner 输出的是假设而非真相。对可能影响目标部件、整体轮廓或生成成本的推断，必须先经过用户的“接受意图”控制门。

### 1.8 UI 稿与工程状态映射


| UI 文件              | 表达的关键状态                              | 工程含义                                                    |
| ------------------ | ------------------------------------ | ------------------------------------------------------- |
| `Desktop - 16.png` | 初始对象与自然语言输入                          | 已加载/生成 active asset，尚无 Solution Space                   |
| `2d笔刷.png`         | 画三角轮廓并写 annotation                   | `annotation` ActionAtom；笔画是意图证据，不是最终 mesh               |
| `3d笔刷.png`         | 在语义部件表面刷选                            | `brush` ActionAtom + part semantics + surface mask      |
| `体积添加.png`         | 打开基础几何体菜单                            | `add` 工具选择 primitive                                    |
| `体积添加及发散.png`      | 新体积加入场景，AI 询问功能/材料                   | Planner clarification → Functional/Structural 发散        |
| `轮廓发散.png`         | 整体观察，系统询问 Silhouette Change          | whole-object intent confirmation → Aesthetic/Structural |
| `局部发散.png`         | Planner 在 Silhouette/Part Change 间消歧 | 多假设 + 用户接受/拒绝控制门                                        |
| `局部发散-1.png`       | 在 Nose/Scarf Change 间消歧              | part target disambiguation                              |
| `局部发散-2.png`       | 局部语义候选进入 Solution Space              | part analogy candidates + selection                     |
| `Desktop - 20.png` | 整体候选出现在顶部                            | generated candidates ready                              |
| `Desktop - 21.png` | 接受候选后进入迭代                            | commit active asset / preserve history                  |
| `Desktop - 23.png` | 多个对象/结果在画布中比较                        | comparison/composition workspace                        |
| `User Flow.png`    | 从入口到导出 3D 的控制流                       | 产品状态机的最高优先级依据                                           |




## 2. 产品边界



### 2.1 v1 必须形成的闭环

```text
进入平台
→ 白模库
→ [选择白模] 白模编辑
  或
→ [不选白模] 空白界面
→ 输入文本 / 上传参考图 / 上传模型
→ 生成或加载模型
→ 屏幕操作
→ 多条直接操作 + 语言及其它输入
→ Planner 推测意图
→ 用户决定是否接受该意图
→ [不接受] 系统不介入，回到屏幕操作
→ [接受] 系统执行对应介入
→ 对应内容出现
→ 用户选择类比发散方向
→ 生成多样内容
→ 用户决定是否选择新内容
→ [不选择] 回到发散方向选择
→ [选择] 以新内容进入下一轮迭代
→ 导出 3D
```



### 2.2 不允许的“看起来完成”

- 没有真实模型时显示假模型；
- worker 不可用时返回假候选；
- 用静态 chip 冒充 AI 计算方向；
- 点击候选立即覆盖源模型且不能撤销；
- 只保存最终 mesh，不保存行为—推断—方向—候选证据链；
- 用泛化的 `object_type=object` 替代具体对象类型；
- 将图片候选标成已经完成 3D；
- 将 dry-run、占位路径或空结果标为生成成功。



### 2.3 v1 暂不追求

- Blender/ZBrush 级完整建模能力；
- 多人实时协作；
- 每一个 mousemove 都调用大模型；
- 自动替用户接受候选；
- 一次完成生产级拓扑、UV、绑定与动画；
- 复杂版本合并。



## 3. 信息架构与推荐布局

```text
┌──────────────────────────────────────────────────────────────┐
│ Logo   Perception          Solution Space              Status│
├──────────────────────────────────────────┬───────────────────┤
│                                          │ AI Behavior       │
│             Interactive 3D               │ Planner feedback  │
│                 Canvas                   ├───────────────────┤
│                                          │ Analogical        │
│                                          │ Divergence        │
├──────────────────────────────────────────┴───────────────────┤
│ Text / image / model refs                                      │
│ Hover Brush Annotation Drag Smooth Add | + Behavior | Send     │
└──────────────────────────────────────────────────────────────┘
```

桌面端建议：

- 顶部 Solution Space：高度 180～240px，可折叠；
- 右栏：300～360px；
- 中央 Canvas 使用剩余空间；
- Intent Composer 固定在 Canvas 底部，不随右栏滚动；
- 部件语义尽量空间化显示在模型附近，不强制占据独立左栏。

当空间不足时，优先保持 Canvas、Solution Space 和 Intent Composer；右侧面板改为 drawer。

## 4. 核心交互规则



### 4.1 观察与操作事件分层

高频原始事件只在前端聚合，不逐条请求 VLM：

```text
pointer_move / orbit_change / hover
→ 前端 500～1000ms 聚合
→ behavior episode
→ 后端规则特征提取
→ 必要时请求 VLM
```

立即上报的语义事件：

- `camera_observation_ended`
- `semantic_hover_ended`
- `part_brush_end`
- `annotation_stroke_committed`
- `drag_end`
- `smooth_end`
- `primitive_added`
- `action_atom_created`
- `intent_draft_saved`
- `intent_draft_updated`
- `cross_domain_divergence_requested`
- `intent_episode_submitted`
- `intent_text_changed`
- `reference_image_attached`
- `reference_model_attached`
- `planner_intent_accepted`
- `planner_intent_rejected`
- `direction_selected`
- `generation_requested`
- `candidate_compared`
- `candidate_accepted`
- `candidate_rejected`
- `undo`
- `redo`



### 4.2 Intent Episode 与用户确认门

用户可以连续执行多个动作；每次完成的工具操作先形成 `ActionAtom`。`Compose / Save Intent` 将若干 ActionAtom 与多模态输入编组为一个可恢复的 `IntentDraft`，但不调用 Planner。只有点击 `Send`，Planner 才对这一组行为作一次完整推测。

```text
ActionAtom[]
+ text/image/model inputs
+ scene/part/camera context
+ recent history
→ Compose / Save Intent
→ Intent Draft
→ Intent Episode
→ Planner hypotheses
→ confirmation UI
→ accepted intervention or no intervention
```

确认门不是所有低成本提示都要弹窗。建议：

- Perception 的低阶观察可以静默更新；
- Hover 的部件语义可以即时显示；
- 当 Planner 要改变目标部件、修改层级、锁定约束或启动生成时，必须确认；
- 用户拒绝后记录 rejection evidence，系统不介入并回到操作状态。



### 4.3 AI 主动程度

采用五级 assistance policy：


| Policy                | 行为                      |
| --------------------- | ----------------------- |
| `observe`             | 仅记录，不改变界面               |
| `interpret_silently`  | 更新 Perception，不打断用户     |
| `soft_suggestion`     | 在 Directions 中增加建议 chip |
| `proactive_candidate` | 用户已授权时后台生成低成本预览         |
| `ask_clarification`   | 高歧义且操作代价较高时提问           |


默认策略是静默理解和软建议。未经用户授权，不应自动改变 active asset。

### 4.4 候选提交语义

候选有三种不同操作：

- `preview`：Canvas 临时显示，源资产不变；
- `accept_direction`：保存创意方向；图片候选也可被接受，但不冒充 mesh；
- `commit_asset`：将已有 mesh 的候选设为新的 active asset。

`reject` 不是删除。它是负偏好证据，仍需保留在 case history 中。

### 4.5 撤销语义

v1 撤销栈至少覆盖：

- selection 改变；
- 当前 episode 中新增/删除一条 behavior；
- Annotation 笔画；
- Brush/Drag/Smooth/Add 的本地预览；
- direction chip 选择；
- prompt 改变；
- candidate preview；
- candidate commit。

已提交的远端生成任务不能“撤销计算”，但可以取消尚未完成的 job，并将已完成结果从当前分支隐藏。

## 5. 前端开发规格



### 5.1 推荐技术栈

沿用当前项目：

- React + TypeScript + Vite；
- Three.js；
- OrbitControls；
- REST + WebSocket；
- CSS variables 建立轻量 design tokens。

若后续状态复杂度上升，建议增加：

- Zustand：工作台 UI/编辑状态；
- TanStack Query：REST 缓存、重试和失效；
- XState：生成/预览/提交状态机，可在 v1.1 引入。



### 5.2 组件拆分

```text
FlowStudioApp
├── StudioHeader
│   ├── PerceptionSummary
│   ├── SolutionSpaceStrip
│   └── RuntimeStatus
├── StudioViewport
│   ├── ThreeScene
│   ├── SemanticHoverOverlay
│   ├── PartBrushOverlay
│   ├── AnnotationCanvas
│   ├── DragHandleLayer
│   ├── SmoothPreviewLayer
│   ├── PrimitiveAddLayer
│   ├── PlannerClarificationOverlay
│   └── CandidatePreviewBanner
├── IntelligenceSidebar
│   ├── AIBehaviorPanel
│   ├── AnalogicalDirectionExplorer
│   └── EvidenceDrawer
└── IntentComposer
    ├── NaturalLanguageInput
    ├── ReferenceImageInput
    ├── ReferenceModelInput
    ├── SixToolPalette
    ├── PendingBehaviorTray
    ├── CrossDomainDivergeButton
    ├── ComposeSaveIntentButton
    └── SendEpisodeButton
```

`SixToolPalette` 固定包含：

```text
Hover | Brush | Annotation | Drag | Smooth | Add
```

空白入口另包含：

```text
BlankStart
├── NaturalLanguageInput
├── ReferenceImageUpload
├── ModelUpload
└── GenerateOrLoad
```

Planner 本身不作为一个可见组件；前端只渲染它返回的：

```text
PerceptionSummary
AIBehaviorPanel
PlannerClarificationOverlay
AnalogicalDirectionExplorer
InterventionProgress
```

当前 `frontend/src/main.tsx` 已包含 session、WebSocket、Three viewport、Planner、Candidates 和任务逻辑。落地原型时应优先做组件拆分；现有可见 `Planner` 聊天面板应逐步替换为上述结果型组件。

### 5.3 前端状态域

```ts
type Tool =
  | "hover"
  | "brush"
  | "annotation"
  | "drag"
  | "smooth"
  | "add";

type StudioState = {
  session: SessionRecord | null;
  activeAsset: AssetRecord | null;
  activePartId: string | null;
  tool: Tool;
  pendingBehaviors: ActionAtom[];
  intentDrafts: IntentDraft[];
  activeIntentDraftId: string | null;
  draftText: string;
  referenceImages: ReferenceInput[];
  referenceModels: ReferenceInput[];
  submittedEpisode: IntentEpisode | null;
  plannerInterpretation: PlannerInterpretation | null;
  pendingIntervention: PlannerIntervention | null;
  crossDomainRequest: CrossDomainDivergenceRequest | null;
  selectedDirectionIds: string[];
  perception: PerceptionSnapshot | null;
  solutionNodes: SolutionNode[];
  activeJobIds: string[];
  previewCandidateId: string | null;
  connection: "connecting" | "online" | "degraded" | "offline";
};
```

必须区分三类状态：

- server state：session、asset、intent draft、episode、interpretation、intervention、direction、candidate、job、memory；
- transient editor state：相机、hover、未结束笔画、局部几何预览、草稿文本；
- derived view state：部件语义标记、Planner 澄清、维度栏目、候选排序、按钮可用性。



### 5.4 Capability gating

前端只展示可执行能力：

- 无真实 asset：显示白模库/空白入口，以及文本、参考图、模型输入；
- 无语义分件：Hover 可以显示“未知区域”，但不能伪造部件名称；
- 无几何编辑能力：Drag/Smooth/Add 显示 unavailable，不伪造修改成功；
- asset 可用但 worker 离线：允许本地查看、Annotation 和行为暂存；服务端介入不可执行；
- PartField 不可用：不显示“语义部件已识别”；
- 候选只有 image：显示 `Image direction`，可接受方向或请求 3D；
- 候选有 mesh：允许 3D preview；
- part candidate 未 fit：显示 `Needs fitting`；
- API 失败：显示可重试错误，不回退到 mock success。



### 5.5 视觉状态

每个异步区域需要独立状态：

```text
idle / collecting / awaiting_confirmation / intervening /
loading / streaming / ready / empty / failed / cancelled
```

候选卡状态不要只靠绿色勾选表达。建议同时使用图标与文本，避免把“生成成功”“已接受”“已保存”混为一类。

## 6. 后端开发规格



### 6.1 服务边界

```text
FlowStudio API Gateway
├── Session & Asset Service
├── Event / Episode Collector
├── Multimodal Planner
│   ├── Action Semantics Parser
│   ├── Scene / Part Context Builder
│   ├── Intent Hypothesis Ranker
│   ├── Conflict & Ambiguity Resolver
│   ├── Intervention Policy
│   └── Analogy Divergence Planner
├── Generation Orchestrator
├── Candidate & Solution Graph Service
├── Memory Service
├── Case Service
└── WebSocket Broadcaster
        ↓
Remote Workers
├── Qwen3 planner / intent and analogy-word planning
├── CreativeFlow relation/rationale/analogy transfer
├── Qwen-Image-2512 / candidate generation
├── Qwen-Image-Edit-2511 / reference and semantic editing
├── Qwen-Image ControlNet Inpainting / strict masked brush fallback
├── Zero123++ / single-image multiview
├── Hunyuan3D / multiview-to-mesh
├── PartField / SAM3D / existing-mesh semantic parts
├── Geometry fit / socket replacement
├── Blender rendering
└── OSS upload
```

具体权重保留、替换、删除门槛与单 GPU 调度方式见
`FLOWSTUDIO_MODEL_DEPLOYMENT_MATRIX_V1_ZH.md`。其中 Zero123++ 与 SAM3D 位于不同
阶段，不能互相替代。



### 6.2 已有能力，应复用

当前后端已具备：

- session、asset、part、candidate、job 和 case 模型；
- `/api/v1/interaction/interpret`；
- replace、drag、diverge 生成入口；
- job 查询与取消；
- candidate preview 所需的 mesh/image 字段；
- candidate accept/reject、Hy3D 和 fit；
- WebSocket session channel；
- remote worker health/preflight；
- 保存 case 与证据元数据的基础能力。

本轮应在此基础上增加 `ActionAtom → IntentEpisode → PlannerInterpretation → Intervention → AnalogyDirection`，而不是重写整套生成 API。

### 6.3 建议新增数据对象



#### ActionAtom

一条可组合的行为。完成工具操作时创建 ActionAtom；`Compose / Save Intent` 将多条 ActionAtom 编组保存，`Send` 才统一提交。

```json
{
  "action_id": "act_001",
  "tool": "annotation",
  "target": {
    "asset_id": "asset_001",
    "part_id": null,
    "screen_region": [310, 120, 960, 740]
  },
  "payload": {
    "stroke_url": "/artifacts/annotation_001.json",
    "recognized_shape": "triangle",
    "recognized_text": "triangle"
  },
  "camera": {
    "view": "front",
    "matrix": []
  },
  "started_at": "2026-07-29T10:00:00Z",
  "ended_at": "2026-07-29T10:00:04Z"
}
```

#### IntentDraft

一个由多条 behavior 拼成、但尚未提交 Planner 的可编辑意图。必须保存 ActionAtom 引用，不能只保存总结文本。

```json
{
  "intent_draft_id": "draft_012",
  "session_id": "sess_001",
  "asset_id": "asset_001",
  "title": "整体更可爱，同时保持底部稳定",
  "action_ids": ["act_001", "act_002", "act_003"],
  "text": "让这个雪人更可爱，但不要变得头重脚轻",
  "reference_inputs": [
    {"type": "image", "artifact_id": "art_ref_001", "role": "shape_reference"}
  ],
  "scope": {"type": "whole_object", "part_ids": []},
  "status": "saved",
  "created_at": "2026-07-30T10:00:00Z",
  "updated_at": "2026-07-30T10:02:10Z"
}
```

允许的状态：

- `editing`：仍在收集 behavior；
- `saved`：已由用户保存，可折叠显示和恢复；
- `submitted`：已封装成 IntentEpisode 并发送；
- `archived`：保留历史但不再参与当前推测。



#### IntentEpisode

```json
{
  "episode_id": "ep_012",
  "session_id": "sess_001",
  "asset_id": "asset_001",
  "intent_draft_id": "draft_012",
  "actions": ["act_001", "act_002", "act_003"],
  "text": "让这个雪人的身体更像三角形",
  "reference_inputs": [
    {"type": "image", "artifact_id": "art_ref_001", "role": "unknown"}
  ],
  "context_snapshot_id": "ctx_001",
  "status": "submitted"
}
```



#### PerceptionSnapshot

```json
{
  "perception_id": "perc_001",
  "session_id": "sess_001",
  "episode_id": "ep_012",
  "summary": "正在从多个角度观察整体比例",
  "behavior_label": "inspect_global_structure",
  "confidence": 0.78,
  "ambiguity": 0.22,
  "evidence": [
    {"type": "camera", "value": "orbit 146° in 8.2s"},
    {"type": "selection", "value": "no local part selected"}
  ],
  "created_at": "2026-07-29T10:00:00Z"
}
```



#### PlannerInterpretation

```json
{
  "interpretation_id": "interp_001",
  "session_id": "sess_001",
  "episode_id": "ep_012",
  "observed_facts": {
    "object_type": "snowman",
    "hovered_parts": ["body"],
    "annotation_shape": "triangle",
    "primitive_added": "cube"
  },
  "primary_hypothesis": {
    "target_scope": "whole_object",
    "target_part_id": "body",
    "operation": "silhouette_divergence",
    "goal": "triangular body silhouette"
  },
  "alternative_hypotheses": [
    {"operation": "add_support_base", "confidence": 0.42}
  ],
  "confidence": 0.78,
  "ambiguity": 0.22,
  "evidence": ["annotation encloses whole body", "text explicitly mentions body"],
  "requires_confirmation": true
}
```



#### PlannerIntervention

```json
{
  "intervention_id": "intv_001",
  "interpretation_id": "interp_001",
  "type": "silhouette_divergence",
  "prompt": "你是想改变雪人的整体轮廓吗？",
  "target_scope": {"type": "whole_object", "part_id": null},
  "proposed_dimensions": ["aesthetic", "structural"],
  "status": "awaiting_user_confirmation"
}
```

#### CrossDomainDivergenceRequest

```json
{
  "request_id": "crossdiv_001",
  "session_id": "sess_001",
  "asset_id": "asset_001",
  "scope": {"type": "whole_object", "part_id": null},
  "context_snapshot_id": "ctx_001",
  "intent_draft_id": "draft_012",
  "preserved_constraints": [
    "preserve snowman identity",
    "preserve three-layer body",
    "preserve face"
  ],
  "dimensions": ["aesthetic", "functional", "structural"],
  "minimum_semantic_distance": 0.55,
  "direction_count": 6
}
```

`intent_draft_id` 可为空；为空时表示只依据当前整体内容和历史已确认约束发散。该请求只生成 `AnalogyDirection`，不能直接创建 Generation Job。



#### AnalogyDirection

```json
{
  "direction_id": "dir_001",
  "session_id": "sess_001",
  "asset_id": "asset_001",
  "dimension": "structural",
  "divergence_mode": "cross_domain",
  "label": "锥形层级结构",
  "description": "把三层圆球的宽度关系迁移为上窄下宽的锥形层级",
  "scope": {"type": "whole_object", "part_id": null},
  "analogy": {
    "source": "stacked snowballs",
    "source_domain": "seasonal character",
    "relation": "progressive width hierarchy",
    "target": "cone",
    "target_domain": "self-righting toy",
    "rationale": "保留三层构成，同时强化用户画出的三角轮廓"
  },
  "deltas": ["narrow_top", "broad_base", "preserve_three_layers"],
  "constraints": ["preserve_hat", "preserve_scarf", "preserve_category"],
  "provenance": {
    "episode_id": "ep_012",
    "interpretation_id": "interp_001",
    "planner": "multimodal_planner_v1"
  },
  "scores": {
    "intent_alignment": 0.86,
    "novelty": 0.61,
    "feasibility": 0.79
  },
  "status": "suggested"
}
```



#### SolutionNode

```json
{
  "node_id": "sol_001",
  "parent_node_id": "source_001",
  "candidate_id": "cand_001",
  "direction_ids": ["dir_001"],
  "artifact_level": "image",
  "decision": "pending",
  "is_active_asset": false,
  "provenance": {
    "source_event_ids": ["evt_101", "evt_102"],
    "interpretation_id": "interp_001",
    "job_id": "job_001"
  }
}
```



### 6.4 建议新增 REST API


| Method | Endpoint                                  | 用途                                             |
| ------ | ----------------------------------------- | ---------------------------------------------- |
| POST   | `/api/v1/sessions/{id}/actions`           | 暂存一条 Hover/Brush/Annotation/Drag/Smooth/Add 行为 |
| POST   | `/api/v1/sessions/{id}/intent-drafts`     | 将多条行为与多模态输入编组并保存为 Intent Draft             |
| PATCH  | `/api/v1/intent-drafts/{id}`              | 增删、排序 behavior，修改文本、scope 或引用                 |
| GET    | `/api/v1/sessions/{id}/intent-drafts`     | 恢复本次会话已保存、未提交或已归档的意图草稿                    |
| POST   | `/api/v1/sessions/{id}/episodes`          | 将多条行为与文本/图片/模型输入提交为 episode                    |
| GET    | `/api/v1/sessions/{id}/perception/latest` | 获取最新 Perception                                |
| POST   | `/api/v1/planner/interpret`               | Planner 融合多模态证据并返回意图假设                         |
| POST   | `/api/v1/interventions/{id}/accept`       | 用户接受 Planner 推测，执行对应介入                         |
| POST   | `/api/v1/interventions/{id}/reject`       | 用户拒绝推测，不介入并记录负证据                               |
| POST   | `/api/v1/directions/suggest`              | 对已确认意图计算具体类比方向                                 |
| POST   | `/api/v1/directions/cross-domain`         | 对当前整体内容计算跨领域类比方向，不直接启动生成                    |
| GET    | `/api/v1/sessions/{id}/directions`        | 查询本轮可选方向                                       |
| PATCH  | `/api/v1/directions/{id}`                 | selected/dismissed/pinned                      |
| GET    | `/api/v1/sessions/{id}/solution-space`    | 返回候选分支与历史                                      |
| POST   | `/api/v1/candidates/{id}/preview`         | 记录预览行为，不提交                                     |
| POST   | `/api/v1/candidates/{id}/commit`          | 将 mesh 候选设为 active asset                       |


现有 `/api/v1/interaction/interpret` 可先作为 Planner MVP 的兼容入口；稳定后再拆出 episode/intervention 接口。现有 `/api/v1/generation/diverge`、`replace`、`drag` 继续负责生成，不复制生成逻辑。

### 6.5 GenerationRequest 扩展

当前请求可通过 `intent.metadata` 和 `generation.metadata` 兼容加入字段；稳定后再提升为强类型字段：

```json
{
  "session_id": "sess_001",
  "asset_id": "asset_001",
  "selection": {
    "type": "none",
    "part_id": null
  },
  "intent": {
    "mode": "diverge",
    "text": "让这个雪人更可爱",
    "constraints": ["preserve snowman identity", "preserve hat and scarf"],
    "metadata": {
      "episode_id": "ep_012",
      "intent_draft_id": "draft_012",
      "interpretation_id": "interp_001",
      "intervention_id": "intv_001",
      "direction_ids": ["dir_001", "dir_004"],
      "divergence_mode": "cross_domain",
      "creative_stage": "rough_form"
    }
  },
  "generation": {
    "candidate_count": 6,
    "diversity": 0.72,
    "output_format": "glb",
    "metadata": {
      "fidelity": "medium",
      "commit_policy": "active_asset"
    }
  }
}
```



### 6.6 WebSocket 事件

服务器推送：

```text
connection_ready
event_ack
perception_updated
interaction_interpretation
intent_draft_updated
planner_clarification_requested
intervention_updated
cross_domain_directions_updated
directions_updated
stage_update
job_update
candidate_ready
solution_space_updated
memory_updated
error
```

所有消息使用统一 envelope：

```json
{
  "type": "job_update",
  "session_id": "sess_001",
  "seq": 104,
  "timestamp": "2026-07-29T10:10:00Z",
  "payload": {}
}
```

`seq` 用于重连后的缺口判断。断线恢复时，前端调用 session snapshot 与 solution-space 接口重新对齐，不依赖遗漏的 WebSocket 消息。

## 7. 数据与持久化

当前 in-memory store 适合单机调试，但 v1 联调至少需要可恢复存储。

推荐：

- PostgreSQL：session、asset、event、episode、interpretation、direction、job、candidate、decision、case；
- OSS：图片、mesh、mask、viewport snapshot、报告；
- Redis：WebSocket 在线状态、短期 event buffer、job progress；
- pgvector（可后置）：历史偏好、相似 episode 和案例检索。

关键表及关系：

```text
session
├── asset
│   └── part
├── action_atom
│   └── intent_episode
│       ├── perception_snapshot
│       ├── planner_interpretation
│       └── planner_intervention
├── analogy_direction
├── generation_job
│   └── candidate
│       ├── candidate_artifact
│       └── candidate_decision
├── solution_node
└── case
```

每个候选必须能反查：

```text
candidate
→ generation job
→ analogy direction(s)
→ accepted intervention
→ planner interpretation
→ intent episode
→ action atom(s)
```



## 8. 关键时序



### 8.1 用户观察对象，AI 更新 Perception

```text
Three.js camera events
→ frontend aggregates orbit/pause/focus
→ POST behavior episode
→ feature extraction
→ rule/VLM interpretation
→ persist perception + evidence
→ WS perception_updated
→ Perception panel refreshes
```

目标延迟：

- 本地聚合与规则摘要：1 秒内；
- VLM 增强摘要：3～8 秒，可异步覆盖；
- 不阻塞 Canvas 操作。



### 8.2 多条行为进入 Planner，并由用户决定是否接受意图

```text
perform Hover/Brush/Annotation/Drag/Smooth/Add
→ completed operations become ActionAtom[]
→ attach text/reference image/reference model
→ Compose / Save Intent creates an editable Intent Draft
→ user reviews, reorders, deletes or adds behaviors
→ Send submits IntentEpisode
→ Planner fuses geometry, semantics, strokes, text, images and history
→ returns ranked intent hypotheses + evidence
→ UI shows clarification such as “Nose Change?” / “Silhouette Change?”
→ user accepts or rejects
→ reject: no intervention, return to canvas operation
→ accept: execute corresponding intervention
→ show dimension-specific analogy directions
```

### 8.3 对整体内容进行跨领域发散

```text
user clicks Cross-domain Diverge
→ freeze current whole-object context snapshot
→ collect object identity + global structure + material/function facts
→ merge accepted constraints and excluded directions
→ Planner proposes distant source/target domains and transferable relations
→ remove duplicate, irrelevant or identity-breaking directions
→ UI presents source domain / target domain / relation / rationale / constraints
→ user selects, rejects or pins directions
→ selected directions enter the normal generation pipeline
```

该流程默认不要求用户先刷选局部，但必须有一个有效 active asset。若当前已有未保存 behavior，前端应询问它们是作为本次跨领域发散的约束加入，还是留在未保存草稿中。

### 8.4 用户选择类比方向并生成候选

```text
select Aesthetic / Functional / Structural analogy directions
→ compose structured intent
→ POST generation/diverge
→ queued job appears immediately
→ worker runs direction/image/3D pipeline
→ WS job_update streams progress
→ image candidates appear first
→ optional Hunyuan3D produces mesh
→ candidate_ready
→ solution space inserts nodes
```

完整 CreativeFlow 路径应保留：

```text
concrete request JSON
→ transfer engine
→ graph expansion / relation / rationale / pruning
→ image generation
→ Hunyuan3D post-process
→ mesh.glb + mesh.obj
→ OSS upload
→ case registration
→ frontend solution space sync
```

图片先到、3D 后到是正常状态，应渐进显示。

### 8.4 用户预览并接受

```text
click candidate
→ record candidate_compared
→ temporary 3D preview
→ user accepts
→ accept direction OR commit mesh asset
→ update active branch and memory
→ stage update
→ AI re-computes next directions
```



## 9. 生成阶段策略


| Stage        | 允许变化        | 应锁定内容           | 默认产物             |
| ------------ | ----------- | --------------- | ---------------- |
| `silhouette` | 整体轮廓、姿态、比例  | 具体对象类别          | 多张低精度图           |
| `rough_form` | 大体量、主要结构    | 已接受方向与身份线索      | 图 + 可选粗 mesh     |
| `part`       | 指定语义部件和连接方式 | 父对象、socket、非目标区 | fitted part mesh |
| `texture`    | 材质、颜色、表面细节  | 几何与部件布局         | PBR/纹理预览         |


原型中的“make it more cute”仅提供审美目标，不能单独决定生成阶段。Planner 必须结合：

- 用户是在观察整体还是局部；
- 是否有 Hover/Brush 指向具体部件；
- Annotation 是包围整体轮廓还是局部标记；
- Drag/Smooth/Add 的空间作用范围；
- 最近一次确认的意图。

若证据仍有歧义，应展示 `Silhouette Change? / Part Change?` 让用户确认，不能直接假设进入 rough form 或 part replacement。

## 10. 失败与降级


| 故障                  | UI 行为                                 |
| ------------------- | ------------------------------------- |
| API Gateway 离线      | Canvas 保留本地浏览；禁止服务端操作                 |
| WebSocket 断开        | 显示 reconnecting；REST 仍可用              |
| VLM 不可用             | 规则推断继续，标记 `rule_based`                |
| graph lookup 失败     | job 失败并显示可重试原因；不返回空成功                 |
| image generation 失败 | 保留 direction，不创建假 candidate           |
| Hy3D 失败             | image candidate 仍可作为方向保存，标记 3D failed |
| OSS 上传失败            | 不暴露不可读 private URL；允许重试上传             |
| PartField 失败        | 返回空 parts + error metadata，不创建通用 body |
| fit 失败              | 原始 part candidate 保留，标记 needs fitting |




## 11. 安全、隐私与研究记录

- 视口截图、参考图片和行为轨迹属于研究数据，采集前需明确同意；
- 默认不录制连续屏幕视频，只保存触发推断所需的稀疏 snapshot；
- 每条 AI 推断保存模型版本、prompt 版本、来源和置信度；
- 用户可查看并纠正 Perception；
- 用户纠正应写为新的 evidence，不覆盖原始记录；
- case 导出需支持匿名 user/session id；
- 日志中不得保存 API key、OSS secret 或本地绝对凭证路径。



## 12. 前后端任务拆分



### Frontend F1：原型布局与组件拆分

- 将当前单体 `main.tsx` 拆分为 Header、Viewport、AI Behavior、Analogical Directions、Intent Composer；
- 去掉显式 Planner 聊天框，把 Planner 输出映射到 Perception、澄清浮层、AI Behavior 和方向面板；
- 实现中央 Canvas + 右栏 + 底部 Intent Composer 布局；
- 保持现有真实 capability gating。



### Frontend F2：六工具与行为采集

- camera episode 聚合；
- Hover raycast + 部件语义展示；
- Brush surface mask；
- Annotation 2D 笔画层；
- Drag/Smooth/Add 3D 局部预览；
- ActionAtom 自动捕获与 pending behavior tray；
- viewport snapshot；
- 统一事件 envelope。



### Frontend F3：认知面板

- Perception 摘要与 evidence drawer；
- AI Behavior；
- `Nose Change? / Scarf Change? / Silhouette Change?` 空间化澄清；
- 接受/拒绝 Planner 意图；
- Aesthetic/Functional/Structural 类比方向；
- 整体 `Cross-domain Diverge` 入口与可解释迁移方向；
- loading/empty/failed 状态。



### Frontend F4：Solution Space

- 候选横向条；
- image/mesh/fit 状态；
- preview/accept/reject；
- active branch 与历史。



### Frontend F5：Intent Composer

- 文本草稿；
- 参考图与模型输入；
- 六工具状态；
- pending behaviors 增删与排序；
- `Compose / Save Intent` 保存、恢复与折叠展示；
- 未保存行为提示；
- `Compose / Save Intent` / `Send` 的不同语义；
- 结构化 IntentEpisode 请求。



### Backend B1：Intent Draft、Episode 与 Perception

- intent draft 持久化、编辑、排序和恢复；
- behavior episode 模型与接口；
- 高频事件聚合特征；
- perception snapshot；
- evidence 与 confidence；
- WebSocket 推送。



### Backend B2：Multimodal Planner

- 几何事实提取；
- Hover/Brush/Annotation/Drag/Smooth/Add action parser；
- 文本、图片、模型、场景、部件和历史融合；
- facts/inference 分离；
- 多意图排序、冲突检测与 evidence；
- 介入策略和用户确认门。



### Backend B3：Analogical Divergence Planner

- aesthetic/functional/structural 三个主维度；
- whole-object cross-domain divergence 模式；
- source/target domain 识别、迁移距离和重复方向过滤；
- source/relation/analogy target/transfer rationale/constraints；
- 根据整体、局部或新体积上下文动态选择维度；
- direction provenance；
- selected/dismissed/pinned；
- 与 GenerationRequest 对接。



### Backend B4：Solution Graph

- parent-child 分支；
- candidate artifact level；
- preview/accept/commit 区分；
- session solution-space 聚合接口。



### Backend B5：持久化与恢复

- PostgreSQL repository；
- Redis event buffer；
- WebSocket seq；
- session snapshot/reconnect。



### Backend B6：真实生成链路验收

- concrete object request；
- non-empty directions/rationales/targets；
- image → Hunyuan3D → mesh；
- OSS 可读 URL；
- case 注册与前端同步。



## 13. 推荐开发里程碑



### M0：契约冻结（1～2 天）

- 冻结六工具的 ActionAtom schema；
- 确认 `Cross-domain Diverge`、`Compose / Save Intent`、`Send` 和接受意图控制门的语义；
- 冻结新增数据对象与 WebSocket envelope；
- 用 snowman case 制作一组固定 contract fixtures。



### M1：可交互壳与真实数据（3～5 天）

- 完成原型布局；
- 复用现有 Three.js、session、asset、job、candidate；
- Solution Space 显示现有真实候选；
- worker 不可用时正确降级。



### M2：AI 观察闭环（4～7 天）

- Hover/Brush/Annotation/Drag/Smooth/Add episode；
- Perception；
- Multimodal Planner；
- 意图确认/拒绝；
- evidence drawer；
- 规则优先，VLM 异步增强。



### M3：类比方向到生成（5～8 天）

- Analogical Divergence Planner；
- Aesthetic/Functional/Structural 动态维度；
- chip 选择；
- 结构化 request；
- job streaming；
- 图片候选渐进出现。



### M4：3D 提交与案例证据（5～10 天）

- Hy3D；
- part fit；
- preview/accept/commit；
- solution graph；
- case 保存和报告。



### M5：研究版本硬化

- PostgreSQL/Redis；
- 重连恢复；
- 同意与匿名化；
- 行为日志导出；
- 端到端稳定性与延迟测量。



## 14. v1 验收标准

使用一个具体 snowman 资产完成以下流程：

1. 用户加载真实 GLB/OBJ，Canvas 可旋转缩放；
2. Hover 能根据 raycast 位置显示真实部件语义；
3. 用户用 Brush 刷选局部，Annotation 画整体三角轮廓，再 Add 一个 Cube；
4. 三条工具操作分别形成可回溯的 ActionAtom；
5. 用户点击 `Compose / Save Intent`，把三条 behavior 与文本保存成一个 Intent Draft，此时不得调用 Planner；
6. 用户刷新或继续操作后，仍能恢复、展开、排序、删除并继续补充该 Intent Draft；
7. 用户点击 `Send` 后，Intent Draft 才封装为 IntentEpisode 并提交；
8. Planner 返回至少两个带 evidence 的意图假设，而不是直接生成；
9. 界面显示 `Silhouette Change?`，用户可以接受或拒绝；
10. 用户拒绝时系统不介入并回到操作；接受时进入对应介入；
11. 用户点击 `Cross-domain Diverge` 后，系统基于雪人整体内容返回至少三个跨领域方向，不要求先选择局部；
12. 每个跨领域方向包含 source domain、target domain、relation、rationale 和 preserved constraints，且不会直接启动生成；
13. 右侧只显示本轮相关的 Aesthetic/Functional/Structural 维度；
14. 用户选择方向后，后端创建真实 generation job；
15. Solution Space 先显示真实图片候选，再更新至少一个真实 mesh 状态；
16. 用户能预览候选而不覆盖源对象；
17. 接受 mesh 候选后 active asset 更新，拒绝项仍保留为历史证据；
18. 保存 case 后，可反查 action atoms → intent draft → episode → interpretation → accepted intervention → analogy directions → job → candidate → decision；
19. 任一远端步骤失败时，界面显示真实失败，不出现 mock candidate；
20. 刷新或短暂断线后，intent draft、pending/accepted state、active asset、候选决策和 Solution Space 可恢复。



## 15. 已校正结论与仍需设计者决定的点

已经可以从 UI 稿确认：

1. Planner 在背后融合直接操作、自然语言、图片、模型、部件语义和历史，不是一个普通聊天面板。
2. 左下角是六个明确工具：Hover、Brush、Annotation、Drag、Smooth、Add。
3. `Compose / Save Intent` 用于把多条 behavior 组合并保存为一个可编辑、可恢复的 Intent Draft；`Send` 用于提交整个 Intent Episode。
4. 六工具之后的 `Cross-domain Diverge` 作用于当前整体内容，返回可解释的跨领域迁移方向，不直接生成。
5. 系统推测意图后，用户有接受/拒绝控制门；拒绝意味着系统不介入。
6. 右侧是具体维度的类比发散，当前主维度为 Aesthetic、Functional、Structural。
7. 整体轮廓、整体跨领域发散、局部部件和新体积会触发不同维度及不同澄清问题。
8. 顶部 Solution Space 展示生成后的多样内容，并支撑选择—迭代。
9. 平台入口包含白模库与空白入口；空白入口可接收文本、参考图和模型。

仍需你后续修改或拍板：

1. `Brush` 是只负责部件/区域选择，还是也允许产生直接几何位移；
2. `Smooth` 和 `Add` 首先生成本地可撤销几何预览，还是只作为 Planner 意图标记；
3. Annotation 是否需要 OCR、基础图形识别和 2D→3D 投影三种能力全部进入 v1；
4. 参考图片是否允许用户显式标注其角色，还是完全由 Planner 推测；
5. Aesthetic/Functional/Structural 之外，Material 是否以后成为独立一级维度；
6. 用户接受的是“Planner 对意图的文字理解”，还是连同“目标范围与介入方式”一起接受；
7. Solution Space 是否在 v1 就展示分支关系，还是先使用横向历史条；
8. 最终导出 3D 的质量门槛：粗 mesh、可编辑 mesh，还是包含 PBR 的交付资产。

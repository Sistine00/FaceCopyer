# 模型选型指南

界面上一共有六组模型可以选择。这份文档说明每个模型的来历、优缺点和适用素材，帮助在具体场景下做出选择。

先给结论：**大多数情况用默认值就行**。下面这些内容主要用于两类场景——默认值效果不理想，或者需要针对性优化（比如素材角度刁钻、脸特别小、遮挡严重）。

## 快速结论

| 需求 | 推荐 | 理由 |
| --- | --- | --- |
| 通用换脸，速度与质量兼顾 | `hyperswap_1a_256` | 官方默认，256 分辨率，训练数据量大，综合表现最稳 |
| 老素材、追求稳妥不翻车 | `inswapper_128` | 发布最久、验证最充分，兼容性最好 |
| 显存紧张或要跑长视频 | `inswapper_128_fp16` | 半精度权重，显存占用约为 fp32 的一半 |
| 换脸结果偏糊，想更清晰 | 加开 `face_enhancer`，选 `gfpgan_1.4` | 换脸模型分辨率有限，靠增强模型补细节是标准做法 |
| 想保留目标原貌，只做轻度修复 | `codeformer` | 有三个增强模型里最接近原图的结果，强度可调 |
| 素材脸很小或侧脸严重 | 检测模型换 `scrfd` | InsightFace 的新一代检测器，小脸召回更好 |
| 遮挡物边缘修不干净 | 遮挡模型换 `xseg_2` 或 `xseg_3` | 在 `xseg_1` 基础上容量更大 |

## 换脸模型

这组模型决定了"换成谁、像不像"。它们都采用同一套思路：用一个身份编码器（多为 ArcFace）提取源脸的身份特征，再由生成网络把身份注入目标脸的姿态与光照中，最后贴回原图。

分辨率是这组模型最关键的差异。`inswapper_128` 只在 128×128 上训练，所以速度快但细节少；其余模型都在 256×256。这也是为什么换脸后通常还需要叠加面部增强模型。

### 主力型号

**`hyperswap_1a_256`** 由 FaceFusion 团队自己训练（许可 ResearchRAIL，2025 年），是官方文档标注的默认模型。据官方更新说明，它的分辨率是 Inswapper 的两倍，且与 Inswapper 效果相当 [$TRAE_REF](https://defuddle.md/https%3A%2F%2Fdeepwiki.com%2Ffacefusion%2Ffacefusion-labs%2F2-hyperswap-system)。训练数据规模是它常被推荐的原因——约 331 万张人脸、覆盖 9000 多个身份 [$TRAE_REF](https://juejin.cn/post/7579551971926147112)。多个整合包作者实测后建议从 `inswapper_128` 升级到它，认为在提升清晰度的同时各方面都更优 [$TRAE_REF](https://deepface.cc/forum.php?authorid=2&mod=viewthread&tid=980)。

优点是分辨率高、细节好、速度快；缺点是三个变体（`1a`/`1b`/`1c`）的差异没有公开说明，只能自己试，且许可为 ResearchRAIL，商用前需确认。

**`inswapper_128`** 来自 InsightFace，是换脸工具生态里历史最久的换脸模型，实现的是 FaceShifter 的思路 [$TRAE_REF](https://1337sheets.com/comparing-face-swap-models-blendswap-ghost-inswapper-simswap-uniface/)。模型约 1.3 亿参数，因为只有 128 分辨率，速度极快。

优点是训练充分、结果稳定，是社区公认最"不挑素材"的选择，多数教程和整合包的默认值都是它；缺点是分辨率低，五官细节偏软，必须靠增强模型补救。许可为 InsightFace 的非商用授权。

**`inswapper_128_fp16`** 是 `inswapper_128` 的半精度版本，效果基本一致，显存占用减半、速度更快，在支持 FP16 的显卡上有明显收益。缺点是极少数素材上可能出现细微差异。显存吃紧时优先选它。

### Ghost 系列

**`ghost_1_256` / `ghost_2_256` / `ghost_3_256`** 由 ai-forever 提供，Apache-2.0 许可——这是这组换脸模型里唯一许可宽松、可放心商用的系列。三者架构相同，区别在容量：版本号越大网络越大、效果越好、速度越慢 [$TRAE_REF](https://1337sheets.com/comparing-face-swap-models-blendswap-ghost-inswapper-simswap-uniface/)。三个模型都要搭配额外的 ArcFace 转换器使用。

优点是开源许可干净、有 256 分辨率并提供三档速度/质量取舍；缺点是社区反馈显示整体观感仍不如 Inswapper 系列精细，且模型文件偏大（三档约 340MB 到 739MB）。

选型上，`ghost_1_256` 适合要速度和低显存，`ghost_3_256` 适合离线处理单张图追求极致质量。

### 其他型号

**`simswap_256` / `simswap_unofficial_512`** 出自 neuralchen 的 SimSwap 项目（2020 年，非商用许可）。它的特点是某些特定角度下表现很强，但泛化性不足，换个角度或光照就可能掉链子 [$TRAE_REF](https://aiprovideos.com/zh/facefusion-3-5-2-%E5%AE%8C%E6%95%B4%E4%BF%9D%E5%AD%98%E6%8C%87%E5%8D%97%EF%BC%9A%E4%BB%8E%E5%9F%BA%E6%9C%AC%E6%93%8D%E4%BD%9C%E5%88%B0%E4%B8%93%E4%B8%9A%E7%BA%A7%E8%B0%83%E6%95%B4%E8%AE%BE%E7%BD%AE/)。`unofficial_512` 版本分辨率到 512，质量更高但显存需求明显上涨。

优点是分辨率选择多、特定场景效果突出；缺点是通用性差、技术较旧。适合已经有明确素材、愿意逐个试模型的情况。

**`blendswap_256`** 基于 ICCV 2023 的 BlendFace 研究，用改良的身份编码器替代标准 ArcFace，宣称能更好地保留源脸身份、减少"目标脸涂了源脸妆"的违和感 [$TRAE_REF](https://1337sheets.com/comparing-face-swap-models-blendswap-ghost-inswapper-simswap-uniface/)。模型本身较轻量，速度快、显存友好。

优点是身份相似度高、速度快；缺点是社区反馈认为它偏向"合成熟悉感"，身份特征反而被淡化 [$TRAE_REF](https://aiprovideos.com/zh/facefusion-3-5-2-%E5%AE%8C%E6%95%B4%E4%BF%9D%E5%AD%98%E6%8C%87%E5%8D%97%EF%BC%9A%E4%BB%8E%E5%9F%BA%E6%9C%AC%E6%93%8D%E4%BD%9C%E5%88%B0%E4%B8%93%E4%B8%9A%E7%BA%A7%E8%B0%83%E6%95%B4%E8%AE%BE%E7%BD%AE/)，且资料较少。

**`uniface_256`**（xc-csc101，2022，许可未标注）和 **`hififace_unofficial_256`**（GuijiAI，2021，许可未标注）都是社区贡献的 256 分辨率模型。优点是提供了额外的风格选择；缺点是来历与训练数据不透明，许可未标注意味着商用有法律风险，建议只用于试验。

**`alphaface_256`**（2026，非商用）是这里最新的模型，但公开资料很少，属于尝鲜选项，不建议作为主力。

### 像素提升

换脸模型下方还有一个「换脸像素提升」下拉框。它的作用是设定贴回原图时的人脸处理分辨率——比如模型本身输出 256×256，选 `512x512` 就是把这部分放大后以更高分辨率贴回，细节更清晰但更慢、更吃显存。

可用档位取决于所选模型，`inswapper_128` 支持 `128x128` 到 `1024x1024`，`simswap_unofficial_512` 最低只能到 `512x512`。常规建议是 `512x512`，配合面部增强模型使用效果最平衡。

## 面部增强模型

换脸输出的脸分辨率有限，增强模型负责把它修清晰。这组的差异主要在"修得多干净"和"保留多少原貌"之间。

| 模型 | 来源 | 许可 | 特点 |
| --- | --- | --- | --- |
| `gfpgan_1.4` | TencentARC | Apache-2.0 | 日常首选，清晰锐利，现代感强 |
| `codeformer` | sczhou | S-Lab-1.0 | 最贴近原图，保留原有瑕疵，强度可调 |
| `gpen_bfr_512` | yangxy | 非商用 | 皮肤质感自然细腻，细节锐利 |
| `restoreformer_plus_plus` | wzhouxiff | Apache-2.0 | 结构修复能力强，风格偏平滑 |

**`gfpgan_1.4`** 是 GFP-GAN 系列的最终版本，也是本项目的默认增强模型。它是换脸场景的事实标配，修复力度适中、速度快。缺点是有时会显得"美化过度"，皮肤过于光滑。

`gfpgan_1.2` 和 `1.3` 是同系列的早期版本，效果依次递减，除非有特定需求否则没必要选。

**`codeformer`** 的特点是保真度最好——第三方对比认为它在人脸清晰化方面最接近原图、保留身份特征最到位，并且提供一个权重参数，可以在"追求细节"和"忠于原图"之间连续调节 [$TRAE_REF](https://soft.china.com/soft/2094856.html)。这正是界面上「人脸增强权重」滑块的用途，只有它支持。

缺点是速度是三家里最慢的，且需要手动调权重才能得到理想效果 [$TRAE_REF](https://blog.csdn.net/weixin_42160645/article/details/157714822)。适合想保留目标人物原本肤质、不希望被过度美化的场景。

**`gpen_bfr_512`** 的皮肤质感评价最好，自然细腻、锐利度高，而且是这组里速度较快的 [$TRAE_REF](https://blog.csdn.net/weixin_42160645/article/details/157714822)。缺点是许可为非商用。追求"人物看起来有真实皮肤"时值得一试。

`gpen_bfr_256` 分辨率低一档，`1024` 和 `2048` 档位更清晰但慢很多、显存吃紧，一般用不到。

**`restoreformer_plus_plus`**（Apache-2.0）修复结构能力强，但风格偏平滑，皮肤细节会被抹掉一些，适合素材本身噪点或压缩伪影严重的情况。

**「人脸增强混合」** 控制增强结果与原脸的融合比例。数值越高越清晰，但过高会让脸显得假、与身体肤色脱节。常年在 60 到 90 之间调即可。

## 人脸检测模型

检测模型负责"在图里找到脸"，它决定了后续所有步骤的输入质量。这组的差异是速度与召回率的取舍。

| 模型 | 来源 | 许可 | 特点 |
| --- | --- | --- | --- |
| `yolo_face` | derronqi | GPL-3.0 | 默认，速度快，正面场景足够 |
| `scrfd` | InsightFace | 非商用 | 新一代检测器，小脸与侧脸召回好 |
| `retinaface` | InsightFace | 非商用 | 老牌高精度，正面大脸稳定 |
| `yunet` | OpenCV | MIT | 最轻量，许可宽松，精度一般 |

**`yolo_face`** 是默认选项，理由是速度快、正面场景够用。缺点是它固定只支持 `640x640` 一种输入尺寸，调大尺寸也没用。

**`scrfd`** 和 **`retinaface`** 都来自 InsightFace，支持 `160x160` 到 `640x640` 多档尺寸。素材里脸占比小、或者人物转头角度大时，换成它们通常能多检出几张脸。`retinaface` 更老更稳，`scrfd` 更新更快。

**`yunet`** 是 OpenCV 自带的轻量检测器，MIT 许可、可放心商用，但精度一般，适合对速度极度敏感又不追求质量的场合。

**「人脸检测尺寸」** 是送进检测网络前把图片缩放到的尺寸。调大能发现更多小脸，但成倍增加耗时。只支持 `640x640` 的模型可选值只有一个。

**「人脸检测角度」** 是额外尝试的旋转角度。正常人脸选 `0`；如果素材里人脸明显倾斜（比如躺姿、倒置视频），勾上对应角度能显著提高检出率，代价是耗时随勾选数量成倍增加。

## 人脸关键点模型

关键点模型输出五官的坐标，换脸靠它对齐。四个选项里：

**`2dfan4`** 是默认值，稳定、够用。**`hrffa`** 更新（2025 年），在极端姿态下更稳，可以试试。**`peppa_wutz`**（Apache-2.0）是较新的开源选择。另有内部的 **`fan_68_5`**，用于把 5 点估计成 68 点，是配合去遮挡功能缓存关键点用的。

这组一般不需要调整，除非换脸结果出现明显五官错位且已排除检测问题。

## 遮挡与解析模型

**人脸遮挡模型**（`xseg_1` / `xseg_2` / `xseg_3`）来自 DeepFaceLab，作用是识别挡在脸前的东西——手、口罩、头发、贴纸。默认 `xseg_1`。如果换脸时遮挡物边缘被误当成脸、或者遮挡区域没被正确排除，可以换 `xseg_2`、`xseg_3` 试，它们容量更大。

需要注意这个模型和本项目自研的「去遮挡」是两件事：遮挡模型是**避开**遮挡物做换脸，自研的去遮挡是先用 IOPaint **把遮挡物修掉**再换脸。素材有遮挡时，优先用后者。

**人脸解析模型**（`bisenet_resnet_18` / `bisenet_resnet_34`）把脸划分成皮肤、眼睛、鼻子、嘴等区域，供「人脸掩膜类型」中的 `area` 和 `region` 使用。`resnet_34` 容量更大、通常更准，`resnet_18` 更快。默认 `resnet_34`。

## 人声提取模型

`kim_vocal_1`、`kim_vocal_2`、`uvr_mdxnet` 都来自 UVR（Ultimate Vocal Remover）系列，作用是从视频里分离人声，供唇形同步使用。三者差异不大，`uvr_mdxnet` 相对较新。只有在使用 `lip_syncer` 处理器时才需要关心。

## 许可与商用

这一节建议在正式使用前确认一遍，因为这组模型里相当一部分**不允许商用**：

- 可商用（许可宽松）：`ghost_*`（Apache-2.0）、`gfpgan_*`（Apache-2.0）、`restoreformer_plus_plus`（Apache-2.0）、`yunet`（MIT）、`bisenet_*`（MIT）
- 非商用：`inswapper_128`、`simswap_*`、`blendswap_256`、`alphaface_256`、`gpen_bfr_*`、`retinaface`、`scrfd`、`xseg_*`
- 研究用途：`hyperswap_*`（ResearchRAIL）
- 未标注许可：`uniface_256`、`hififace_unofficial_256` —— 未标注等于无法确认授权，商用有风险

以上许可以 `facefusion/processors/modules/*/core.py` 中各模型 `__metadata__` 里标注的值为准，那是随代码一起维护的权威来源。

## 本机当前情况

截至文档更新时间，本机只下载了两组换脸相关模型：

- 换脸：`inswapper_128`、`hyperswap_1a_256`
- 增强：`codeformer`、`gfpgan_1.4`

其余模型在首次选用时会自动下载。走镜像站 hf-mirror.com 下载时实测速度在 8 MB/s 以上，一个 685 MB 的模型约 80 秒即可完成，所以下载本身不算慢。需要留意的是这台机器上的下载**不支持断点续传**，一旦中断就得从零开始，建议在网络稳定的时段一次性下好要用的模型。另外 deep_swapper 的模型地址只走 huggingface 渠道，界面上「下载源」的勾选对它无效。

另外 `facefusion.ini` 里 `face_swapper_model` 被显式设为 `inswapper_128`，覆盖了官方默认的 `hyperswap_1a_256`。想用新模型把这一行改掉即可。

## 组合建议

常规图片换脸：`hyperswap_1a_256` + 像素提升 `512x512` + `gfpgan_1.4` 增强 + 混合 80。这套组合在清晰度、速度和显存之间最平衡。

长视频或显存紧张：`inswapper_128_fp16` + 像素提升 `256x256`，增强模型可以关掉或改用 `gfpgan_1.4`，并把显存策略设为 `strict`。

要求保留目标人物原本肤质：`hyperswap_1a_256` + `codeformer`，权重从 0.5 开始往上调，边调边看。

素材角度刁钻或脸很小：检测模型换 `scrfd`，检测尺寸拉到 `640x640`，必要时勾选人脸检测角度。

素材有明显遮挡（贴纸、刘海、手）：用本项目的「手动描边」画一圈遮挡物，走 IOPaint 去遮挡流程，再正常换脸。这比换遮挡模型有效得多。

## 信息来源

模型的分辨率、许可、提供方等事实取自本仓库 `facefusion/processors/modules/*/core.py` 中的 `__metadata__`，以及 `facefusion/choices.py`。默认值与参数范围取自 FaceFusion 官方文档 [$TRAE_REF](https://docs.facefusion.io/usage/cli-arguments/processors/face-swapper)。

性能与观感类的评价来自公开对比资料，包括 1337 Sheets 的换脸模型对比 [$TRAE_REF](https://1337sheets.com/comparing-face-swap-models-blendswap-ghost-inswapper-simswap-uniface/)、FaceFusion 3.5.2 设置指南 [$TRAE_REF](https://aiprovideos.com/zh/facefusion-3-5-2-%E5%AE%8C%E6%95%B4%E4%BF%9D%E5%AD%98%E6%8C%87%E5%8D%97%EF%BC%9A%E4%BB%8E%E5%9F%BA%E6%9C%AC%E6%93%8D%E4%BD%9C%E5%88%B0%E4%B8%93%E4%B8%9A%E7%BA%A7%E8%B0%83%E6%95%B4%E8%AE%BE%E7%BD%AE/)、以及人脸修复模型的横向对比 [$TRAE_REF](https://blog.csdn.net/weixin_42160645/article/details/157714822)[$TRAE_REF](https://soft.china.com/soft/2094856.html)。这类评价带有主观成分且随版本变化，实际效果仍需在自己的素材上验证。

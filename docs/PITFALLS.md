# 历史踩坑记录

记录开发过程中已经解决的疑难问题。每条都写清了现象、根因和处理方式，其中涉及 Gradio 前端的问题都附上了可复现的判断依据，方便在依赖升级后重新排查。

## 界面层

### Sketchpad 以隐藏状态挂载后无法再启用

这是本项目最隐蔽的一个问题。手动描边画布在页面上显示正常，但它处于"隐藏后再显示"的路径时，会变得完全无法绘制，而且不报任何前端错误提示。

现象是画布能显示出来，画笔拖上去没有任何反应，橡皮擦同样无效。打开浏览器控制台能看到：

```
TypeError: Cannot read properties of undefined (reading 'app')
```

根因在于 Gradio 5.50 的 `Sketchpad` 组件只在"挂载时即可见"的条件下才能正常初始化。如果以 `visible=False` 挂载、之后再切换为可见，组件内部的工具会在绘图上下文就绪之前就被 `set_tool` 调用，初始化失败后画布进入永久不可编辑状态，无法恢复。

处理方式是不再切换可见性：编辑器始终以 `visible=True` 挂载，用一张占位图表示"尚未选择目标图"的状态，运行时只更新图片内容，绝不改动 `visible`。这条约束写在 `occlusion_editor.py` 的模块注释里，后续任何改动都不要试图改回动态显隐。

排查这类问题时，用 Playwright 直接对比"隐藏后显示"与"挂载即可见"两种路径最有效，后者正常、前者失效，即可确认是同一问题。

### ImageEditor 对空上下文缺少保护

早期版本用的是 `gradio.ImageEditor`，页面在特定时机崩溃，控制台报 `background_image undefined` 或 `cleanup_dom_event_listeners` 相关异常。

根因是 Gradio 5.50 的 `ImageEditor` 在 `hide_resize_ui` 等方法中直接访问 `this.image_editor_context.background_image`，没有判断上下文是否存在。组件尚未完成初始化时上下文为 `undefined`，读取属性即抛异常。

另外 `cleanup_dom_event_listeners` 方法里也有同类问题，直接访问 `this.image_editor_context.app.canvas`。

处理方式是对 Gradio 的前端 bundle 打补丁做空值保护，具体见下方"前端 bundle 补丁"。后来编辑器整体换成了 `Sketchpad`，`ImageEditor` 相关补丁仍然保留在 bundle 中。

### CommandManager 的 history 被降级成普通对象

在"先挂载、后塞图"的路径下，图片能上传成功但进不了画布，控制台报：

```
TypeError: this.history.push is not a function
```

根因是 `CommandManager` 的 `history` 字段有时不是预期的 `Cr` 实例，而是一个形状相同的普通对象，于是 `this.history.push(e)` 直接抛错，中断了 `add_image_from_url` 的后续流程，图片因此没能进入画布，`set_zoom('fit')` 也不会执行。

处理方式是在调用前兜底重建节点：

```javascript
typeof this.history.push != "function" && (this.history = new Cr(this.history && this.history.command))
```

### 前端 bundle 补丁的维护方式

上面两个前端问题的修复都落在 Gradio 的构建产物上：

```
D:\facefusion\venv\Lib\site-packages\gradio\templates\frontend\assets\Index-DI509U_e.js
```

补丁脚本是根目录的 `_patch_bundle.py`（空值保护）和 `_patch_bundle2.py`（history 类型兜底）。两个脚本都会先备份原文件，`_patch_bundle2.py` 还会先检测是否已经打过补丁，只在未打过时才替换，并打印替换前后内容与守卫计数，可以安全地重复运行。

需要特别注意的是，**bundle 文件名带构建哈希**（当前是 `Index-DI509U_e.js`）。一旦重装或升级 Gradio，这个文件会被替换成新的哈希文件名，所有补丁随之丢失，上面几个前端问题会全部复现。因此升级 Gradio 之后必须重新运行这两个脚本，并且要先确认脚本里写死的文件名是否还是当前实际的文件名。

### 模型下拉列表的可用性上色（补丁落在 index.html）

需求是让每个模型下拉列表里「已经下载好的模型标红，没下载的正常灰」，避免选到一个跑不起来的模型再报错。实现分三段：

1. `facefusion/uis/model_status.py` 负责判定可用性。判定标准是模型的 `.onnx`（或 `.dfm`）与同名 `.hash` 文件同时存在 —— 下载器校验失败时会删掉源文件，所以两者齐备基本等价于可用。这里**刻意不做 crc32 全量校验**，因为模型总量有好几 GB，每次启动全量读盘会明显拖慢启动。`get_status_payload()` 把结果拼成 `已下载清单#全部清单`，两段各用 `|` 连接模型名。
2. `facefusion/uis/core.py` 把这个字符串传给 `gradio.Blocks(head = ...)`。Gradio 的 `index.html` 模板**并不渲染** `head` 参数，但 `head` 会随 `window.gradio_config` 一起下发到前端，所以这里把 `head` 当成纯数据通道使用。
3. 真正上色的脚本注入在 Gradio 模板里：

```
D:\facefusion\venv\Lib\site-packages\gradio\templates\frontend\index.html
```

脚本读取 `window.gradio_config.head`（失败时回退 `fetch('/config')`），扫描 `li[data-testid="dropdown-option"]`，把 label 命中已下载清单的项标红 `#e53935`（加粗），命中全部清单但未下载的标灰 `#9e9e9e`。

调试时踩了两个坑，都值得记下来：

**坑一：下拉选项只在展开时才存在于 DOM 里。** 折叠状态下 `querySelectorAll` 根本扫不到选项，所以调试标题一度显示 `painted=0`，看起来像脚本没生效。实际必须反复扫描（脚本里挂了 `click`/`focusin` 捕获与 500ms 定时器），展开的瞬间才会上色。

**坑二：`li` 的 `textContent` 前面有一个隐藏的 ✓ 勾选符。** Gradio 渲染出的选项结构是：

```html
<li class="item" data-index="N" aria-label="模型名" data-testid="dropdown-option" role="option" aria-selected="false">
  <span class="inner-item" hide>✓</span>模型名
</li>
```

所以 `li.textContent.trim()` 拿到的是 `✓inswapper_128` 而不是 `inswapper_128`，用文本精确比对**必然失配**，这就是最初 `painted=0` 的另一个原因。正确做法是优先读 `aria-label`，读不到再从 `textContent` 里剥掉 ✓ 兜底。

注意这个补丁和下面的前端 bundle 补丁属于同一类风险：它写在 venv 内的 Gradio 模板里，**重装或升级 Gradio 会直接丢失**，届时模型列表会恢复成清一色的默认颜色（不会报错，只是功能消失），需要重新注入。

### 点「开始」没反应时，原因原本只写在「终端」里

`instant_runner.run()` 在处理失败时返回的是空的输出组件，界面上不会弹任何提示；真正的原因由各处理器的 `pre_process()` 写进日志，而日志只显示在「终端」组件里。

现在「输出」下方已经补了一块失败提示：`logger.capture_errors()` 会在处理期间临时挂一个只收 ERROR 级记录的 handler，`instant_runner.make_notice()` 把抓到的消息去掉 `[FACEFUSION.XXX]` 前缀后列出来（最多 3 条），并提示去看「终端」。判定标准是「没有产出输出文件」，所以即使一条错误都没抓到，也会给出通用提示而不是静默。提示组件放在中间一列而不是紧挨着开始按钮，因为开始按钮所在的列很窄，提示塞进去会被压成竖排。

需要留意的是，这个提示只是把原因搬到明面上，并不会让失败的配置自动变好。走到这条路径的典型情况是 `lip_syncer`（唇形同步）。它的 `pre_process()` 要求「源」里必须有一个**音频文件**：

```python
if not has_audio(state_manager.get_item('source_paths')):
	logger.error(translator.get('choose_audio_source') + translator.get('exclamation_mark'), __name__)
	return False
```

而 `filesystem.has_audio()` 只按扩展名判断（`is_audio` → 扩展名在 `audio_formats` 里），**带音轨的视频文件也不算**。所以只要勾了唇形同步而源里只有图片或视频，整次处理都会在入口处中止，并且报的是「选择一个音频作为源！」，与目标是什么无关。界面上源的 `gradio.File` 没有限制文件类型，音频直接丢进同一个框即可，上传后会出现播放器。

顺带记一下：`conditional_process()` 里只要任何一个处理器 `pre_process()` 返回 False 就整体返回 2，后面排队的处理器根本不会执行，所以日志里只看到最先失败的那一条，容易误判成"只有一个地方出错"。

### 浏览器缓存导致前后端不匹配

曾经出现"源图上传按钮点了没反应"的情况，而后端日志正常。

根因是浏览器缓存了旧版本的前端资源，与后端不匹配。处理方式是在页面上按 Ctrl+F5 强制刷新。这类问题排查时，先用无痕窗口打开一次即可区分是代码问题还是缓存问题。

### File 组件自带的叉号不触发后端事件

从源图或目标图上点自带的移除叉号，界面上的图消失了，但后端状态没有清空，再点开始换脸仍会用上一张图。

根因是 Gradio 的 `File` 组件原生移除按钮不会触发 `change` 事件，后端收不到通知，`state_manager` 中的路径一直保留。

处理方式是新增独立的清除按钮，显式清空后端状态。以目标图为例，`clear_target()` 会依次调用 `clear_faces()` 清空人脸缓存、`state_manager.clear_item('target_path')` 清空路径、`occlusion_editor.reset_state()` 重置描边状态，并同时更新界面上的文件、图片、视频、按钮可见性与编辑器内容。

## 遮挡去除

### 去遮挡后的空白脸导致换脸五官错位

这是整个功能最初的核心难题。把遮挡物修掉之后，目标图对应位置变成一片空白皮肤，换脸流程在这个区域重新检测关键点必然不准，结果就是五官位置偏移。

处理方式是在去遮挡之前，先在**原始遮挡图上**检测并缓存完整的关键点，换脸时直接复用这份结果。相关注释原文：

> 去遮挡后的空白脸上已经没有可见五官, 换脸时重新检测的 landmark 必然不准(导致五官错位)。
> 因此: 在去遮挡前, 于「原始遮挡目标图」上检测并缓存完整 landmark,
> 换脸时直接复用这份 landmark, 保证五官对齐与无遮挡场景一致。

落地位置有两处：`iopaint_remove.cache_target_landmarks()` 写缓存，`face_swapper\core.py` 的 `override_target_landmarks()` 读缓存并覆盖目标人脸：

> 去遮挡后的目标是空白脸, 换脸前覆盖回「原始遮挡图」上检测到的 landmark,
> 保证五官对齐与无遮挡场景一致, 而不是在空白脸上盲猜。

缓存文件与去遮挡结果图同名，后缀为 `.lm.json`，存放在 `source\.occlusion_removed`。

### 遮挡物带偏眼睛关键点

贴纸、刘海这类遮挡物经常把被遮一侧的眼睛关键点带偏，进而导致换脸五官错位。

处理方式是基于掩码做通用校正：如果某侧眼睛中心落在遮挡掩码内，就用另一侧未遮挡的眼睛相对鼻梁中线做镜像复原。注释原文：

> 遮挡物(贴纸/刘海)常带偏被遮一侧的眼睛 landmark, 导致换脸五官错位。
> 通用校正: 眼睛中心落在遮挡 mask 内的一侧, 用另一侧(未遮挡)相对鼻梁中线镜像复原。

实现位于 `_correct_eye_symmetry()`。

### 自动掩码需要保留下巴

自动掩码最初会把整个下半张脸都算进去，结果人脸检测失去了锚点。

处理方式是掩码区域上缘到接近下巴条带处即止，且最终裁剪时把下边界限制为 `min(height, chin_y1 - 1)`，明确保留下巴。注释原文：

> 只修补贴纸区域并保留下巴作为换脸的人脸检测锚点。

> 不到下巴, 保留换脸用的人脸检测锚点

### 彩色遮挡物与肤色接近导致漏检

最初只用 YCrCb 色彩距离判断"偏离肤色"的像素，对彩色贴纸有效，但对蝴蝶结这类色相与肤色接近的遮挡物会漏检。

处理方式是补一个对象级的信号：在"脸框加边缘余量"的窗口内寻找高饱和连通域，取面积最大的那个对象整体填满其包围盒，这样连描边、飘带一起覆盖，避免因脸框截断造成对象不闭合或漏覆盖。注释原文：

> ---- 信号3: 高饱和彩色(蝴蝶结/贴纸等彩色遮挡, 其 YCrCb 可能与肤色接近) ----
> 对象级方案: 在「脸框+边缘余量」窗口内找彩色连通域, 取面积最大的那个对象(贴纸),
> 整体填满其包围盒(含黑边/描边/飘带), 避免因脸框截断导致对象不闭合或漏覆盖。

> 加宽窗口: 脸框 + %15 余量, 保证贴纸的飘带/边缘不因脸框截断而漏检

同时需要限制大块干扰：

> 取面积最大的对象(贴纸主体); 尺寸超过脸框太多则视为背景跳过大块

窗口最终还要裁回脸框范围，防止背景大块被误选：

> 最终裁剪: 把修复区限制在【脸部框+小扩展窗口】内, 杜绝背景大块被选入。

### 肤色估计不写死区间

早期的实现写死了肤色区间，在不同色调、不同白平衡的素材上表现不稳定。

处理方式是从下巴中央条带（纵向 0.82 到 1.0）实时估计本地肤色，再据此计算阈值。注释原文：

> 策略: 从下巴区估计本地肤色, 用 YCrCb 距离标记「明显偏离皮肤」的像素(彩色贴纸/发色),
> 再并上亮度信号(白色贴纸)。不依赖写死的肤色区间, 对各种色调/白平衡都稳健。

亮度信号的阈值同样基于肤色统计量动态给出，用于覆盖白色贴纸。

### 检测不到人脸时多模型回退

单一检测模型在部分素材上会漏检，而漏检的表现是静默的。

处理方式是 `detect_faces_robust()` 依次尝试 `retinaface`、`yolo_face`、`scrfd`，任一模型返回非空结果即采用，全部失败才算未检测到，并在 `finally` 中恢复原始的检测模型配置。

### 检测状态缺失被回退逻辑吞掉

在界面之外的上下文调用检测时，会出现"明明有脸却报未检测到"的情况。

根因是 `download_providers`、`execution_providers`、`execution_device_ids`、`face_detector_margin`、`face_detector_score` 等状态缺失时，`resolve_download_url` 或 `inference_manager` 会抛异常，而多模型回退逻辑把它当成"这个模型不行"继续尝试下一个，最终表现为未检测到人脸。注释原文：

> 缺失这些状态时 resolve_download_url / inference_manager 会抛异常,
> 而 detect_faces_robust 的回退逻辑会把它吞成"未检测到人脸"

处理方式是新增 `ensure_detect_state()`，在检测前补齐这些默认值。

## 手动描边

### 掩码必须取笔迹层而不是合成图

早期版本直接分析 Sketchpad 输出的合成图，把红色像素当描边，结果原图里本身就有的红色区域被误判成描边。

处理方式是改为读取笔迹层的 alpha 通道。注释原文：

> 掩码取"笔迹层"的 alpha 通道(不是整张合成图),
> 因此原图里本身存在的红色像素不会被误判成描边。

对应实现是 `_strokes_from_layer()`：

> 笔迹层是透明底 RGBA, alpha 非零处即描边.

### 描边填充分三种情况

把描边转成待修复区域时，需要区分三种用户操作，否则会出现"只画了半圈却把整块背景都修掉"或者"橡皮擦掉的地方又被填回来"。

处理方式是用从画布四边泛洪求外部区域的办法：描边闭合时只填笔迹真正围住的封闭区域；描边有开口时不会把背景圈进来；实心涂抹时不做填充、原样返回笔迹，这样橡皮擦擦除的部分不会被重新填回。注释原文：

> 描边(沿遮挡物边缘画一圈)时只填"笔迹真正围住的封闭区域": 用从画布四边泛洪求外部的办法,
> 开口的笔迹(如只画了半圈)不会把整块背景一起圈进来。
> 涂满(实心涂抹)时不做填充, 原样返回笔迹, 这样橡皮擦擦掉的地方不会被重新填回来。

对应实现是 `outline_to_filled()`。

### 画笔粗细滑块无效

早期用 `ImageEditor` 配自定义滑块控制画笔粗细，滑块拖动无任何效果，属于事件绑定没有正确落到组件上。

换成 `Sketchpad` 后问题消失，因为它自带画笔粗细弹层、橡皮、撤销、清空、全屏等控件，不需要自己接前端事件。这也是编辑器最终选型为 `Sketchpad` 的直接原因。

## 环境与部署

### IOPaint 一直在用 CPU 硬算

去遮挡单张耗时约 6.4 秒，明显偏慢。检查发现两个叠加的问题：

一是 `iopaint_venv` 里装的是 `torch 2.14.0+cpu`，`torch.version.cuda` 为 `None`，`torch.cuda.is_available()` 为 `False`，属于纯 CPU 版本。

二是即使换成 CUDA 版也还不够，IOPaint 1.6.0 的 `--device` 参数默认值就是 `cpu`：

```
--device  <cpu|cuda|mps>  [default: cpu]
```

而当时的启动脚本没有传这个参数。也就是说这是两个独立的改动，缺一不可。

处理方式是把 `iopaint_venv` 里的 torch 与 torchvision 换成 `+cu126` 构建，并在 `_iopaint_start.py` 中显式传 `--device`，同时加入设备自动探测与 CPU 回退。替换前后对比（同一张 1170x1560 图片）：

| | 替换前（CPU） | 替换后（GPU） |
| --- | --- | --- |
| 暖机单张耗时 | 6.37 / 6.40 / 6.45 秒 | 1.03 / 1.05 秒 |
| 完整流程单张耗时 | - | 1.10 / 1.36 / 1.73 秒 |

输出质量做过逐像素比对：GPU 与 CPU 结果最大差异为 2/255，平均差异 0.016，仅 3.8% 的像素相差 1 到 2 级，属于浮点计算的正常非确定性，肉眼无法分辨。

### 模型下载被静默跳过，只报「源校验失败」

选择未下载的 deep_swapper 模型后，终端反复出现这样的三行，没有下载进度，也看不出原因：

```
[FACEFUSION.DOWNLOAD] 正在删除损坏的源文件 elon_musk_224
[FACEFUSION.DOWNLOAD] elon_musk_224 的源校验失败
[FACEFUSION.DOWNLOAD] elon_musk_224 的源校验失败
```

根因是两个问题叠加。

一是 deep_swapper 的模型地址硬编码走 huggingface 渠道。它的 `core.py` 调用的是 `resolve_download_url_by_provider('huggingface', ...)`，不看界面上「下载源」的勾选，所以勾上 github 也没用。而本机访问 huggingface.co 会一直超时，只能依赖镜像 hf-mirror.com。

二是探测下载源是否可达的建连超时只有 5 秒（`download.py` 里的 `curl_builder.set_timeout(5)`），而本机访问 hf-mirror.com 实测要 20 秒左右才响应。5 秒内必然失败，镜像被判为不可达，`resolve_download_url_by_provider` 返回 `None`。接下来的问题是 `conditional_download_sources` 里对空地址的处理写成了 `if invalid_source_url:`，地址为 `None` 时**直接跳过下载**，然后照常校验、照常报「源校验失败」并删掉文件。于是一个既从不下载、又不断报错的循环就形成了。

处理方式有两处：把建连超时从 5 秒提到 40 秒（`download.py` 新增 `CONNECT_TIMEOUT` 常量）；把镜像 `hf-mirror.com` 排到 huggingface 渠道的首位（`choices.py`），否则每次解析地址都要先白等一个超时才回退到可用镜像。

修复后实测可以正常下载：685 MB 的 `elon_musk_224.dfm` 用时约 80 秒，平均 8.7 MB/s，校验通过。

### 镜像站不支持断点续传

上面的修复过程中发现，hf-mirror.com 对 Range 请求响应异常：同样的地址用 `curl --range 0-8000000` 请求，三次全部超时且一字节未收到，而普通的完整 GET 请求能跑满 8 MB/s 以上。

这个差异有实际影响。下载器带 `--continue-at -`，文件存在时会发 Range 请求续传。实测把已下载的 685 MB 模型截断到 308 MB 再触发下载，结果是文件被判定校验失败后直接删除，重新下载从零开始。

也就是说在这台机器上，模型下载一旦中断就要重来，没有续传可言。上下文是下载本身很快（大文件约 80 秒到 2 分钟），所以实际影响有限；但网络不稳时需要有心理准备。

顺带记录一个观察：`conditional_download` 用 `while current_size < download_size` 等待文件达到完整大小，这个循环原本既没有超时也没有休眠，详见下面一节。

### 下载源顺序会让界面看起来像卡死

界面加载处理器参数时会同步执行 `pre_check()`，模型没下完就一直停在 `processing`。

实测勾选「帧增强」触发下载 `span_kendata_x4.onnx`（1,718,947 字节）。默认下载源顺序来自 `types.py` 里 `DownloadProvider = Literal['github', 'huggingface']`，即**先走 github**，于是去拉了 `github.com` 的 release 直链，实测只有约 7 KB/s，一个 1.6 MB 的模型要等四分钟，界面全程显示 `processing | 48.1/5.7s`，看起来就是卡死。同一个文件改走 `hf-mirror.com` 只需 6 到 8 秒（250 到 350 KB/s），相差近 40 倍。

修了三处：

1. `choices.py` 的 `download_providers` 由 `list(get_args(DownloadProvider))` 改成显式的 `[ 'huggingface', 'github' ]`。这个列表同时决定界面「下载源」的默认勾选顺序，改这一处即可。另外 `config.get_str_list` 对空值会回退到它，所以 ini 里 `download_providers =` 为空时新顺序也能生效。
2. `download.py` 的等待循环加了 `time.sleep(DOWNLOAD_POLL_INTERVAL)`。原实现是纯忙等，实测下载期间 CPU 时间 5 秒内涨 4.91 秒，等于跑满一个核心，会让整个界面跟着发卡。
3. 同一个循环里加了 `process.poll() is not None` 就跳出。curl 已退出说明这次传输结束了，文件还没写满就只可能是失败，必须交回调用方报「源校验失败」；原实现会无限空转，请求永久挂住。另外给 curl 补了 `--speed-limit 1024 --speed-time 120`（新增 `curl_builder.set_speed_guard`），这样连接被中途掐断但不报错时也能中止并重试。

需要注意 `processing` 的基线耗时本身就有 5 到 6 秒，那是 `pre_check()` 对已下载模型做 crc32 校验的开销，与下载无关，属正常现象。

### PyTorch 官方源在国内下载极慢

替换 torch 时测得 `download.pytorch.org` 的速度只有 0.49 MB/s，而 wheel 文件有 2.48 GB，按此速度需要约 85 分钟，实际上表现为长时间无进展。

处理方式是改用国内镜像。实测上海交大镜像 `https://mirror.sjtu.edu.cn/pytorch-wheels/cu126` 速度约 12.75 MB/s，文件字节数与官方源完全一致（2,602,771,598 字节）。安装命令：

```
D:\facefusion\iopaint_venv\Scripts\python.exe -m pip install ^
  --index-url https://mirror.sjtu.edu.cn/pytorch-wheels/cu126 ^
  torch==2.14.0+cu126 torchvision==0.29.0+cu126
```

清华镜像的同路径返回 404，不可用；阿里云镜像速度约 0.21 MB/s。

### 换 torch 前必须停掉 IOPaint

Windows 上运行中的 IOPaint 会占用 torch 的动态库文件，直接替换会失败。需要先停掉 IOPaint 相关进程，安装完成后再通过 `_iopaint_start.py` 重新拉起。安装只影响 torch 与 torchvision 两个包，实测替换前后 `pip freeze` 均为 93 个包，差异仅这两项。

### 缺少 ConfigParser 导入导致启动即崩

某次改动后 `run.bat` 启动时直接退出，日志显示：

```
NameError: name 'ConfigParser' is not defined
```

根因是 `batch_runner.py` 中删改代码时丢掉了 `from configparser import ConfigParser` 这一行，而 `load_config_path()` 在多处被界面渲染阶段调用，于是启动过程直接中断。

这次故障说明一个排查顺序问题：**只要界面起不来，先看是不是渲染阶段抛异常**，因为 `render()` 里的任何错误都会让整个界面无法加载，表现得像"服务没启动"。

### 路径字符串未转义产生警告

`batch_runner.py` 里的 Windows 路径占位符写成普通字符串 `'D:\facefusion\swap_task\source'`，`\s` 被当作无效转义序列，编译时产生：

```
SyntaxWarning: invalid escape sequence '\s'
```

处理方式是改用原始字符串 `r'...'`。这类警告不影响运行，但会污染日志，且容易掩盖真正的问题。

### 中文词表缩进错误导致解析异常

往 `locales_zh.py` 手工添加词条时，曾因多出一个制表符导致缩进层级错位，文件无法正常解析，界面所有中文文案失效。

处理方式是用脚本统一缩进格式，确保同一层级的所有词条缩进一致。由于 `_gen_zh.py` 生成脚本已不在仓库中，目前新增词条需要手工维护，改动后建议立即启动一次界面确认文案正常。

### 「备份再改写」时把源文件读成了空

把 `source\facefusion.ini` 播种输出路径时，最初写成这样：

```python
with open(path, 'wb') as source, open(path + '.bak', 'wb') as target:
    target.write(source.read())          # 想备份原文
with open(path, 'w', encoding = 'utf-8') as handle:
    parser.write(handle)
```

问题在 `open(path, 'wb')` 这一句：它以写模式打开，**打开的同时就把原文件截断成 0 字节**。于是 `source.read()` 返回空、备份是空的，随后 `parser.write()` 如果因为任何原因失败，配置就彻底没了。这次实测就踩中了：`facefusion.ini` 和它的 `.bak` 同时变成 0 字节，程序只能按全默认值启动，界面上所有路径设置丢失。

修法是分三步走，并且落盘前先在内存里校验：

```python
with open(path, 'rb') as handle:          # 先完整读出来
    original = handle.read()
buffer = io.StringIO()
parser.write(buffer)                       # 再在内存里生成新内容
text = buffer.getvalue()
if not text.strip():                       # 空内容直接放弃, 不碰原文件
    return []
with open(path + '.bak', 'wb') as handle:  # 备份
    handle.write(original)
with open(path, 'w', encoding = 'utf-8') as handle:   # 最后才写
    handle.write(text)
```

教训是：**“备份 + 改写”不要用两个 `open` 放在同一个 `with` 里省略中间变量**，读模式必须先于写模式。凡是改写用户配置或状态文件，都要先判断新内容非空再落盘。

### 默认输出目录写死盘符

`uis\components\output.py` 里曾经写着 `DEFAULT_OUTPUT_ROOT = 'D:\\facefusion\\output'`。它只在 `source\facefusion.ini` 的 `paths.output_image_path` 为空时兜底，平时看不出来，但换台机器、或者用户清空了配置，成片就会往一个不存在的盘符写。

改成按文件位置推算（`resolve_relative_path` 的参数是相对 `source\facefusion` 这个包的目录）：`resolve_relative_path('../../output')` → `<项目根>\output`。**这里容易多算一层**，写成 `../../../` 会得到 `D:\output`。同类改动改完要打印一次实际值确认，不能只看代码觉得对。

### 缓存与残留文件不会自动清理

程序只在两处清磁盘：临时帧目录（同一目标下次处理时，以及正常退出时），其余一律不删。实测这台机器上的占用：

| 内容 | 位置 | 实测占用 |
| --- | --- | --- |
| Gradio 上传副本 | 系统临时目录下的 `gradio` | 411 个 / 325.6 MB |
| 动态 WebP 转码缓存 | `source\.webp_converted` | 26 个 / 118.7 MB |
| 去遮挡结果缓存 | `source\.occlusion_removed` | 14 个 / 2.7 MB |
| 任务记录 | `source\.jobs` | 273 个 / 1.8 MB |
| 临时帧残留 | 系统临时目录下的 `facefusion` | 3 个残留目录 |

临时帧目录之所以会残留，是因为 `image_to_video.process()` 的任务序列遇到 `error_code > 0` 会直接返回，跳过结尾那次 `clear`；进程被强杀时更是什么都不执行。好在同一个目标下次处理时，开头那次 `clear` 会先把它清掉，所以只有「以后不再处理的目标」会永久留着。

两个带哈希的缓存（转码、去遮挡）都以**文件绝对路径**为键，命中条件是源文件没变、缓存比源文件新。实测同一份 15 MB 的动图 WebP 放在两个不同路径下会生成两份转码结果，所以同一素材换个位置再传一次，缓存就会多存一份。这也是之前记录的「改描边掩码不会让去遮挡缓存失效」的同一个成因。

对应的人工清理入口在 `uis\components\cleanup.py`，界面位置是「输出」下方的「清理垃圾文件」。删除逻辑有两条保护：先等当前任务结束，再跳过当前会话正在引用的路径；上传副本额外要求文件超过 1 小时，因为当前目标在状态里已经被换成转码后的 mp4，单靠路径保护盖不住它。

其中 Gradio 缓存（上传副本 + 成片拷贝）另外交给了 Gradio 自己过期：`uis\core.py` 的 `Blocks(...)` 设了 `delete_cache = (CACHE_DELETE_FREQUENCY, CACHE_DELETE_AGE)`，即「每 900 秒检查一次、创建超过 7200 秒（2 小时）的文件删掉」。这两个值原先定的是 3600 / 43200，批量跑一轮后缓存涨到 3.5 GB，12 小时才过期等于整个批量期间一直在堆，所以收紧到 2 小时。两个层面都确认过：在独立的最小 Gradio 应用里实测，登记进 `temp_file_sets` 的文件确实会被定时任务删掉，而 `close()` 停止服务时整个缓存会被清空；参数为 `(None, None)` 时 `create_lifespan_handler` 里 `if frequency and age` 不成立，清理任务根本不会启动，这也解释了之前缓存为什么会一直堆着。

两个必须记住的后果：**服务正常停止时（例如在控制台按 Ctrl+C）缓存会被整体清空，所以重启后要重新选一次素材**；如果直接关窗口把进程打断，清理不一定来得及执行，这种残留由上面那条 2 小时过期兜底。清理只作用于缓存里的副本，输出目录（`D:\facefusion\output`）里的成片是原文件，不会被删 —— 这一点通过实测确认：同一个成片在输出目录和缓存目录里各存在一份。

### 缓存必须放在数据盘，不能放系统盘

批量成片会在 Gradio 缓存里各留一份完整拷贝（「批量输出」的画廊要播放它）。实测跑完 7 个目标后，缓存从 412 个文件 / 325 MB 涨到 898 个文件 / **3.5 GB**，恰好等于 7 个成片的总大小。按这个目标量（76 个）推算，整轮批量能在缓存里堆出十几 GB。

本机 C 盘当时只剩 15.5 GB，按上面的速度会被写满，所以 `facefusion.ini` 里把 `[paths] temp_path` 指到了 `D:\facefusion\temp`（有 58 GB 空闲）。`uis\core.py` 的 `init()` 用 `os.path.join(temp_path, 'gradio')` 设置 `GRADIO_TEMP_DIR`，所以这一项同时管住了临时帧目录与 Gradio 缓存两处；清理面板读的也是 `GRADIO_TEMP_DIR`，路径会自动跟着变。

顺带记一句：把缓存放到数据盘并不能减少总量，只是不再威胁系统盘。真正的量级取决于成片数量与体积。

### 排查缓存落点时会被 gradio_client 误导

验证「上传副本到底写在哪」时踩了一次假阳性。`gradio_client` 默认 `download_files=True`，会把服务端返回的文件**下载到客户端自己的临时目录**，而它默认用的也是 `%TEMP%\gradio`。于是脚本调接口测试时，C 盘凭空多出一个文件、返回值也显示成 C 盘路径，看起来像是「改了缓存目录却没生效」。实际上服务端写的是 D 盘，C 盘那份是测试脚本自己下的。

正确做法是关掉下载：`Client(url, download_files = False)`，这样拿到的是服务端真实路径。用这个方法复测确认：上传副本落在 `D:\facefusion\temp\gradio`，C 盘的旧目录删掉之后不再被重新创建。

### GRADIO_TEMP_DIR 必须在 import gradio 之前设置

gradio 里 `routes.py` 的 `DEFAULT_TEMP_DIR`、组件基类的 `GRADIO_CACHE` 都是**在 import 时求值**的常量，之后再用环境变量改已经晚了。原来只在 `uis\core.py` 的 `init()` 里设置，这依赖「init() 一定早于 gradio 导入」，属于隐式依赖，一旦导入顺序变化就会静默退回系统盘目录。

现在改由入口脚本 `source\facefusion.py` 在导入 `facefusion.core` 之前设置，路径按脚本自身位置推算为 `<项目根>\temp\gradio`；`uis\core.py` 那里改成 `setdefault` 只作兜底，避免两处取值不一致导致文件被拆到两个目录。注意 `facefusion.py` 是唯一入口，将来若更换入口要记得把这一行一起搬过去。

## 换脸与批量

### 目标人脸检测不到时，换脸会静默原样输出

`face_swapper` 的 `process_frame`（`processors\modules\face_swapper\core.py`）只在 `source_face and target_faces` 都非空时才执行替换：

```python
if source_face and target_faces:
	for target_face in target_faces:
		temp_vision_frame = swap_face(source_face, target_face, source_vision_frame, temp_vision_frame)
return temp_vision_frame, temp_vision_mask
```

而 `face_selector.select_faces` 在 `reference` 模式下拿不到参考脸时会直接 `return []`。两条路径都不报错，日志里只有「图像处理成功」「视频处理成功」，于是**输出和输入几乎一样，程序却认为一切正常**，批量列表里那个目标也会照样算作完成。

实测（目标换成一张纯色噪点图）：帧计数是 `swapped_frames=0, missed_frames=1`；换成能检测到人脸的正面照则是 `swapped_frames=1, missed_frames=0`。批量面板现在会读这个计数，把这类目标标成「未检测到可换的人脸」。

最常见的漏检原因是**人脸过小**：把 1132x1080 的照片整体缩到 384 宽，人脸只剩约 30 像素；视频里逐帧轻微转动会进一步压低检测置信度。遮挡（比如宽帽檐遮住额头并压暗眼睛）也会加重，但同一张图在原尺寸下仍能检测到，缩到 384 宽就未必 —— 这类目标处在阈值边缘，尺寸一变结果就翻转。排查手法：用界面上的「预览」看有没有框出人脸，或直接看批量进度框给出的帧计数。

### 别用像素差判断换脸是否生效

这是排查时踩过的一个大坑。我一开始拿「输出与目标的像素差」当换脸的判据，于是把几个其实**正常换了脸**的目标误判成「没换」：把同一个人换到他自己身上，像素几乎不变（实测最大差 42、显著变化像素 0.01%），和完全没有换脸时的数字无法区分。当时据此得出了「reference 模式坏了」「戴草帽的图检测不到人脸」两个错误结论，最后靠 `run_stats` 的帧计数才纠正过来。

可靠判据只有帧计数：`processors\modules\face_swapper\core.py` 在换与不换两条分支上分别累加 `swapped_frames` / `missed_frames`，`run_stats.get_stats()` 直接读出真实结果。像素差可以作为「变化多大」的参考，但不能作为「有没有换」的依据。

另外 `--face-selector-mode` 的三种取值都会经过 `select_faces`，其中 `reference` 模式多一道身份距离判断（`reference_face_distance` 默认 0.3，比较参考脸与目标脸的 embedding 距离），阈值过小同样会返回空列表。

### 批量视频的处理链路

批量目标支持图片和视频（含动图 WebP），界面上用「处理对象」筛选。两个容易漏掉的点：

- 动图 WebP 在批量里必须先过 `webp_helper.resolve_target_path` 转成 mp4，否则 `is_image` 会把它判成静图，结果是只换第一帧却输出 `.mp4` 后缀。单个处理时 `target.py` 走的就是这个函数，批量一度漏了这一步。
- 输出目录按目标类型分流：图片进 `output\picture`，视频与动图 WebP 进 `output\video`，由 `output.resolve_output_directory` 决定。`gradio.Gallery` 本身支持播放视频，所以「批量输出」不用额外组件就能直接看结果。

### 批量被打断后怎么续跑

批量任务的目标清单只存在内存里，进程一没就丢了，重跑必须重新选一次源和目标文件夹。好在成片命名是 `<目标名>_swapped_<序号>`，序号取自目标在筛选后列表里的位置，所以只要源文件夹、目标文件夹、处理对象三项不变，重新跑出来的序号与上一轮完全对应。

因此批量面板提供了「跳过已存在的成片」开关：勾上之后，目标对应的成片已经存在就整条跳过，只补算没做完的部分。它默认不勾，因为改了模型或参数后想全部重算时，勾着会静默跳过所有已完成的目标。判断依据就是输出文件是否存在，不看内容新旧。

## 尚未解决的问题

### 修改描边掩码不会让去遮挡缓存失效

去遮挡缓存的键是目标图绝对路径的哈希，命中条件是缓存文件比源图新。这个条件只跟路径和时间戳有关，**不包含掩码内容**。因此调整描边后重新运行，仍会直接命中旧缓存，用户会以为描边没生效。

目前的规避办法是手动删除 `source\.occlusion_removed` 下对应文件。彻底解决需要把掩码内容也纳入缓存键的计算。

### 批量处理不读取手动描边

`batch_runner.py` 导入了去遮挡相关函数但没有实际调用，批量任务目前只使用自动掩码。批量场景下用户在描边编辑器里画的内容不会生效。

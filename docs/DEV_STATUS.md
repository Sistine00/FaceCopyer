# 项目开发目前状况

本文档记录 FaceCopyer 相对上游 FaceFusion 的改动范围、各模块职责，以及尚未完成的部分。适用于接手项目后快速建立全局认知。

## 上游基线

代码位于 `D:\facefusion\source`，上游版本为 FaceFusion 3.9.0，许可为 OpenRAIL-AS。本项目在其上二次开发，对外名称 **FaceCopyer**，当前版本 **1.0.0**（`facefusion\metadata.py` 中的 `METADATA`）。

改名涉及的位置：`metadata.py`（name/version/author/url）、`uis\components\about.py`（关于面板的两个链接均指向 `https://github.com/Sistine00/FaceCopyer`）、4 个 layout 的 `favicon_path`、`locales.py` / `locales_zh.py` 的 `about.repository` 词条、根目录 `run.bat` 标题与回显、`README.md` / `source\README.md` / `使用教程.html`。

图标（`facecopyer.ico` 与 `facecopyer.png`）统一放在项目根目录，不放在 `source\` 下。4 个 layout 里用 `resolve_relative_path('../../facecopyer.ico')` 得到绝对路径，这样无论从哪个工作目录启动都能找到图标，不再依赖 cwd。

**刻意未改的两处**：`face_swapper/core.py`、`face_landmarker.py` 里 `__metadata__` 的 `'vendor': 'FaceFusion'`（那是模型提供方，属于事实信息），以及 `resolve_download_url('models-3.9.0', ...)`（上游模型仓库地址，改了会导致模型无法下载）。Python 包名仍为 `facefusion`，重命名包会牵动全部 import，收益不足。

`source\requirements.txt` 声明的依赖：

| 依赖 | 声明版本 | 实际安装版本 |
| --- | --- | --- |
| gradio | 5.50.0 | 5.50.0 |
| gradio-rangeslider | 0.0.8 | 0.0.8 |
| numpy | 2.4.6 | 2.4.6 |
| onnx | 1.22.0 | 1.22.0 |
| onnxruntime | 1.29.0 | onnxruntime-gpu 1.24.4 |
| opencv-python-headless | 5.0.0.93 | 5.0.0.93 |
| tqdm | 4.70.0 | 4.70.0 |
| scipy | 1.18.0 | 1.18.0 |

`onnxruntime` 的声明版本与实际安装版本不一致：声明的是 CPU 版 1.29.0，实际装的是 GPU 版 onnxruntime-gpu 1.24.4。当前运行依赖的是实际安装的 GPU 版，如果按 `requirements.txt` 重新安装，会退回 CPU 推理并显著变慢。这是一个需要修正的遗留问题。

代码中大量使用 `PIL`，但 `Pillow` 未在 `requirements.txt` 中声明，目前由 gradio 间接引入。若上游调整依赖，可能出现 `Pillow` 缺失。

## 本机设置抽取（部署可移植性）

改造前，`run.bat`、`_iopaint_start.py`、`_port_clean.py` 和 `source\facefusion.ini` 里写死了 `D:\facefusion\...`、7860 / 8081 端口、`venv` / `iopaint_venv` 目录名，换一台机器必须改代码。现在这些全部收进项目根目录的 `facecopyer.ini`。

| 文件 | 角色 |
| --- | --- |
| `facecopyer.ini.example` | 带注释的配置模板，随仓库提交 |
| `facecopyer.ini` | 本机实际配置，首次启动自动生成，已加入 `.gitignore` |
| `_facecopyer_config.py` | 配置加载器。`SPEC` 定义「规范键 → (段, 选项, 默认值)」，`Settings` 负责类型转换、相对路径解析与派生路径，`Settings.environment()` 把配置映射成环境变量 |
| `_facecopyer_launcher.py` | 启动器。`--setup` 走部署向导，`--check` 只打印设置与体检结果，默认动作是启动；还负责把配置播种进 `source\facefusion.ini` 的 `[paths]` |
| `setup.bat` | 向导入口，内部 `call run.bat --setup`，复用同一套 Python 探测逻辑 |
| `run.bat` | 只做一件事：找到 Python（先 venv，再 `py -3`，再 `python`），然后把控制权交给启动器 |

配置传到程序里的路径是「`facecopyer.ini` → 启动器 → 环境变量 / `source\facefusion.ini`」，对应的代码改动：

| 位置 | 改法 |
| --- | --- |
| `facefusion\iopaint_remove.py` | 端口与地址改读 `IOPAINT_PORT` / `IOPAINT_URL`；顺手修掉 `is_iopaint_available()` 把 inpaint 地址当 base 用的老 bug |
| `facefusion\uis\core.py` | 缓存清理参数改读 `FACECOPYER_CACHE_CHECK_INTERVAL` / `FACECOPYER_CACHE_EXPIRE_SECONDS` |
| `facefusion\choices.py` | 默认下载源顺序改读 `FACECOPYER_DOWNLOAD_PROVIDERS` |
| `facefusion\uis\components\output.py` | 默认输出根目录由写死的 `D:\facefusion\output` 改为按文件位置推算 |
| `facefusion.py` | `GRADIO_TEMP_DIR` 改用 `setdefault`，让配置里的 `temp_dir` 生效；直接运行本文件时才退回 `<项目根>\temp\gradio` |
| `source\facefusion.ini` | `[paths]` 全部留空，由启动器按配置播种；且只播种空值，界面上改过的路径不会被覆盖 |

## 代码改动清单

### 新增模块

上游 3.9.0 中不存在以下几个文件：

`facefusion\iopaint_remove.py` 是本次二次开发的核心。它负责遮挡掩码的生成、关键点的检测与缓存，以及调用 IOPaint 完成修复。对外接口：

| 函数 | 作用 |
| --- | --- |
| `preprocess_target_for_occlusion(image_path, user_mask_path)` | 去遮挡主入口，条件不满足时原样返回 |
| `remove_occlusion(image_path, user_mask_path)` | 完整去遮挡流程，返回修复后的图片路径 |
| `build_occlusion_mask(vision_frame, box, face_landmark_5)` | 生成自动遮挡掩码 |
| `load_manual_occlusion_mask(mask_path, height, width)` | 把用户描边转成 0/255 掩码 |
| `detect_faces_robust(vision_frame)` | 多模型回退的人脸检测 |
| `detect_target_landmarks(vision_frame, box, lm5_raw, mask)` | 检测 68 点并做眼部对称校正 |
| `cache_target_landmarks(...)` / `load_cached_landmarks(...)` / `get_cached_landmarks(...)` | 关键点缓存的写入与读取 |
| `ensure_detect_state()` | 补齐检测所需的状态项 |
| `is_iopaint_available()` | 探测 IOPaint 服务是否就绪 |
| `get_occlusion_mode()` | 读取当前遮挡处理模式 |
| `remove_small_components(mask, min_area)` | 去除掩码中的小连通域 |

`facefusion\webp_helper.py` 处理动态 WebP。对外接口为 `is_animated_webp(file_path)`、`resolve_target_path(target_path)`、`convert_animated_webp(webp_path)`、`get_ffmpeg_path()`。转码结果缓存在 `source\.webp_converted`。

`facefusion\locales_zh.py` 存放中文词表 `ZH_LOCALES`，按模块名分组。文件头注释注明它由 `_gen_zh.py` 生成，但该生成脚本当前不在仓库中，因此中文词表目前只能手工维护。

`facefusion\uis\model_status.py` 负责「模型是否已下载可用」的判定，供界面给模型下拉列表上色。对外接口为 `is_model_ready(model_category, model)`、`get_model_status()`、`get_status_payload()`。判定只看模型文件与同名 `.hash` 是否同时存在，不做 crc32 全量校验（模型总量数 GB，全量读盘会明显拖慢启动）。`get_status_payload()` 输出的字符串会经 `uis\core.py` 的 `gradio.Blocks(head = ...)` 下发到前端，真正上色的脚本注入在 venv 内的 Gradio 模板 `index.html` 里 —— 这属于易失补丁，详见《历史踩坑记录》。

### 被修改的上游模块

| 文件 | 改动内容 |
| --- | --- |
| `facefusion\core.py` | 引入 `webp_helper`，在目标路径解析处调用 `resolve_target_path` |
| `facefusion\program.py` | 默认界面语言改为 `zh` |
| `facefusion\translator.py` | 合并中文词表，默认语言设 `zh`，取词时按「中文 → 英文」回退 |
| `facefusion\locales.py` | 英文词表新增 `webp_*` 与整组 `batch_*`、`panel_*`、`occlusion_editor_*`、目录选择相关键 |
| `facefusion\types.py` | 语言类型由 `Literal['en']` 扩为 `Literal['en', 'zh']` |
| `facefusion\processors\modules\face_swapper\core.py` | 新增 `override_target_landmarks()`，换脸前用缓存的关键点覆盖目标人脸；在 `process_frame()` 的两条分支上累加帧计数 |
| `facefusion\run_stats.py` | 新增。按目标统计换脸结果（`swapped_frames` / `missed_frames`），供批量面板判断某个目标是否真的换过脸 |
| `facefusion\uis\layouts\default.py` | 引入并编排 `batch_runner`、`occlusion_editor`、`output`、`instant_runner` |
| `facefusion\uis\components\target.py` | 新增目标图清除按钮，接入动态 WebP 解析与描边编辑器 |
| `facefusion\uis\components\output.py` | 由单一输出路径改为图片/视频双目录，新增选择与打开目录按钮 |
| `facefusion\uis\components\instant_runner.py` | 即时运行前先做去遮挡预处理，并按目标类型套用输出目录 |
| `facefusion\uis\components\source.py` | 新增源图清除按钮 |
| `facefusion\uis\components\preview.py` | 预览前按遮挡模式做预处理 |
| `facefusion\uis\components\about.py` | 新增语言下拉框，切换后写入配置并重启进程 |
| `facefusion\uis\core.py` | 启动时把模型可用性清单经 `Blocks(head = ...)` 下发给前端脚本；设置 `delete_cache` 让 Gradio 缓存按策略自动过期 |
| `facefusion\uis\components\processors.py` | 处理器按钮改为「英文名 · 中文名」显示，值仍是英文名 |
| `facefusion\uis\components\face_enhancer_options.py` | 修正 `visible` 传入非布尔值、预检失败不回滚状态、空推理池被解引用三处缺陷 |
| `facefusion\processors\modules\face_enhancer\core.py` | `has_weight_input()` 与 `forward()` 增加空值保护，避免空推理池崩溃 |
| `facefusion\download.py` | 建连超时由 5 秒提到 `CONNECT_TIMEOUT = 40`；等待循环加休眠（原为纯忙等占满一个 CPU 核心）并在 curl 退出时跳出 |
| `facefusion\choices.py` | 默认下载源顺序改为 `['huggingface', 'github']`，避免走 github 直链导致下载仅 7 KB/s、界面长时间卡在 processing |
| `facefusion\curl_builder.py` | 新增 `set_speed_guard()`，给下载加 `--speed-limit / --speed-time` 断流保护 |
| `facefusion\logger.py` | 新增 `capture_errors()` 上下文管理器，临时收集 ERROR 级日志供界面回显失败原因 |
| `facefusion\uis\components\instant_runner.py` | 「输出」下方新增失败提示，处理未产出结果时列出原因并指向「终端」 |
| `facefusion\uis\layouts\default.py` | 接入上述失败提示组件 |
| `facefusion\locales.py` / `locales_zh.py` | 新增 `instant_runner_failed`、`instant_runner_failed_hint`、`instant_runner_failed_unknown` 三条词条 |

需要说明的是，改动清单是通过「是否引用新增模块」与「上游 3.9.0 目录交叉核对」得出的。项目此前没有版本控制，改动引入 Git 之前无法用提交记录逐行佐证，`uis\core.py`、`uis\assets\overrides.css`、`jobs\*`、`processors\*` 等文件未与上游逐行比对，可能还包含未被识别的细微改动。现在代码已托管到 `https://github.com/Sistine00/FaceCopyer`，此后的改动可以直接查提交记录。

### 新增界面组件

`facefusion\uis\components\occlusion_editor.py` 实现手动描边编辑器，基于 `gradio.Sketchpad`。对外接口包括 `render()`、`listen()`、`make_editor(value)`、`save_mask(editor_value)`、`reset_state()`、`reset_on_target_change(file)`、`get_user_mask_path()`、`outline_to_filled(strokes)`。掩码最终写到 `D:\facefusion\.temp\occlusion_user_mask.png`，由 `instant_runner` 传给去遮挡流程。

`facefusion\uis\components\batch_runner.py` 实现批量换脸面板，支持从文件或整个目录加载源图与目标，目标可以是图片或视频（含动图 WebP），逐张处理并持续输出进度。界面上有「处理对象」单选（图片 + 视频 / 仅图片 / 仅视频），切换时同步刷新目标预览并显示筛选数量。

进度分两块。**实时进度**是每秒轮询的文本框（`value = read_live_progress` + `every = 1.0`，与 `terminal.py` 用同一套机制），显示当前是第几个目标、本目标跑到第几帧、本目标已用时、已完成个数与平均耗时、预计剩余时间。之所以要轮询而不是靠生成器推送，是因为生成器在目标处理期间被阻塞，中间几分钟送不出任何更新。它靠 `install_progress_hook()` 在点击开始时再劫持一层 `tqdm.update`（`terminal.py` 启动时已劫持过一次，这里接在它后面，两边功能都保留）来抓帧进度。**进度记录**是逐行累积的结果，每个目标生成一行「换脸 N 帧 / 未检测到可换的人脸 · 用时 h:mm:ss」，收尾时追加汇总「共 N 个目标：X 个已换脸，Y 个未检测到人脸」并列出后者文件名。

对外接口包括 `run_batch(target_type)`（生成器）、`read_live_progress()`、`build_target_result()`、`install_progress_hook()`、`reset_progress_hook()`、`format_duration()`、`update_target_type()`、`filter_target_paths()`、`classify_target()`、`build_target_type_choices()`、`load_source_directory()`、`load_target_directory()`、`choose_and_load_source()`、`choose_and_load_target()`、`apply_occlusion_mode()`、`build_output_path()` 等。其中 `classify_target()` 把动图 WebP 归入视频，处理前统一经 `webp_helper.resolve_target_path` 转成 mp4。

`facefusion\uis\components\cleanup.py` 提供垃圾文件的人工清理入口，渲染在「输出」下方。可勾选清理失败的任务记录、临时帧残留、动态 WebP 转码缓存、去遮挡结果缓存、Gradio 上传副本五类内容。删除前会先等当前任务结束，并且跳过当前会话正在引用的路径；上传副本额外要求文件超过 1 小时，因为当前目标在状态里已被换成转码后的 mp4，单靠路径保护盖不住它。对外接口包括 `purge_tree()`、`cleanup_failed_jobs()`、`cleanup_temp_frames()`、`cleanup_webp_cache()`、`cleanup_occlusion_cache()`、`cleanup_upload_pool()`、`run_cleanup()`。

另外 `source\tests\test_cli_batch_runner.py` 为本地新增的测试文件，上游测试套件中没有这一项。

## 界面结构

界面在 `facefusion\uis\layouts\default.py` 中编排，整体为一个 `gradio.Row` 内的四个区域：

左栏（参数区）集中放各类处理器参数，包括 `about`、`processors`、各处理器的选项面板、`execution`、`download`、`memory`、`temp_frame`、`output_options`。

中栏放输入与运行相关内容，顺序为源图、遮挡处理说明、目标图（内部包含描边编辑器）、折叠的批量面板、输出面板、终端输出。

第三块是无 Column 包裹的运行区，依次是工作流选择、即时运行按钮组、任务运行、任务管理。

右栏放预览与模型选项，包括预览、裁剪、人脸选择器、跟踪器、遮罩、检测器、关键点检测器。

## 中文界面实现

中文化由五处协同完成。`locales_zh.py` 提供中文词表，`translator.py` 负责在加载各模块词表时合并中文并在取词时按「中文 → 英文」顺序回退，`types.py` 扩展语言类型，`program.py` 把默认语言设为 `zh`，`about.py` 提供切换入口。切换语言时程序会写入 `facefusion.ini` 的 `[uis] language` 并通过 `os.execv` 重启进程。

## 参数功能说明

界面上每个可调控件的下方都有一行灰色说明文字，说明该项的作用。实现方式是利用 Gradio 组件自带的 `info` 参数，不需要额外插入 Markdown 元素。

词条统一放在全局 `uis` 段：英文在 `facefusion/locales.py`，中文在 `locales_zh.py` 的 `facefusion.uis` 下，键名规则是「控件名 + `_info`」。处理器参数面板的控件本身用模块级词表取标签，但说明词条仍放在全局段，因此键名带上处理器前缀以避免重名，例如 `face_enhancer_blend_slider_info`。

新增或修改说明文字的步骤是在两个词表文件的 `uis` 段各加一条同名键，然后在对应组件构造里加 `info = translator.get('uis.<键名>')`。`face_detector_size_dropdown`、`preview_frame_slider`、`trim_frame_slider` 三个控件用选项字典构造，键写成 `'info': ...`。当前共 91 个可调控件带说明。

## 功能完成度

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| 自动遮挡去除 | 可用 | 基于肤色、亮度、高饱和三个信号生成掩码，对彩色贴纸与白色贴纸均有效 |
| 手动描边 | 可用 | 支持描边自动填充封闭区域，也支持实心涂抹；配有橡皮擦 |
| 关键点继承 | 可用 | 去遮挡前缓存关键点，换脸时覆盖使用 |
| 中文界面 | 可用 | 支持中英文切换 |
| 批量换脸 | 可用 | 支持图片与视频目标，可按类型筛选，逐个处理并输出进度；已通过显存与耗时实测 |
| 批量实时进度 | 可用 | 每秒刷新，显示当前第几个目标、本目标帧进度、已用时与预计剩余时间 |
| 未换脸目标提示 | 可用 | 逐目标给出换脸帧数，未检测到人脸的目标会被标出并列在汇总里 |
| 批量续跑 | 可用 | 「跳过已存在的成片」开关，中断后重跑只补算没做完的目标 |
| 分目录输出 | 可用 | 图片/视频分目录，支持自定义路径并持久化 |
| 动态 WebP | 可用 | 自动转 MP4，结果缓存复用 |
| 源/目标清除 | 可用 | 彻底清空后端状态与描边编辑器 |
| 模型可用性标色 | 可用 | 模型下拉列表里已下载的标红加粗，未下载的标灰 |
| 失败提示 | 可用 | 处理未产出结果时在「输出」下方列出原因并指向终端 |
| 垃圾文件清理 | 可用 | 手动清理失败任务记录、临时帧残留、转码与去遮挡缓存、上传副本 |
| 上传副本自动过期 | 可用 | Gradio 缓存每小时检查一次、超过 12 小时的文件自动删除，服务停止时清空 |

## 已知缺口

**批量面板未接入手动描边。** `batch_runner.py` 导入了 `preprocess_target_for_occlusion` 与 `remove_occlusion`，但文件内没有实际调用点，属于未使用的导入。批量处理目前只使用自动遮挡掩码，用户在描边编辑器中画的掩码不会作用到批量任务上。

**去遮挡缓存不跟随掩码变化失效。** 缓存键是目标图的绝对路径哈希，命中条件是缓存文件比源图新。修改描边掩码不会让缓存失效，需要手动删除 `source\.occlusion_removed` 下对应文件才会重新计算。

**`_gen_zh.py` 缺失。** 中文词表声明由脚本生成，但生成脚本不在仓库中，新增界面文案需要手工往 `locales_zh.py` 里补。

**`requirements.txt` 与 `venv` 不一致。** 声明 CPU 版 onnxruntime，实际使用 GPU 版；`Pillow` 未声明。按声明文件重建环境会退化为 CPU 推理。

**根目录调试脚本未整理。** `test_occlusion_integration.py`、`test_outline_fill.py` 是两个针对自研功能的独立验证脚本（非 pytest 风格，直接运行），已保留但尚未纳入测试套件。

**模型标色补丁写在 venv 内，会随 Gradio 重装丢失。** 上色脚本注入在 `venv\Lib\site-packages\gradio\templates\frontend\index.html`。重装或升级 Gradio 后列表会恢复成默认颜色（不报错，只是功能消失），需要按《历史踩坑记录》里的说明重新注入。

**上传副本改为自动过期。** `uis\core.py` 的 `Blocks(...)` 已设置 `delete_cache = (CACHE_DELETE_FREQUENCY, CACHE_DELETE_AGE)`，当前是「每 15 分钟检查一次、创建超过 2 小时的文件删掉」，另外服务正常停止时（控制台按 Ctrl+C）Gradio 会清空整个缓存。需要留意两个后果：一是**正常重启后素材要重新选一次**；二是清理只作用于缓存副本，输出目录里的成片是原文件，不受影响。若要调松紧，改这两个常量即可。

**缓存目录已移到数据盘。** 缓存位置由 `source\facefusion.py`（入口脚本）在导入 gradio 之前设为 `<项目根>\temp\gradio`，`uis\core.py` 的 `init()` 用 `setdefault` 兜底。必须放在入口而不是 `init()` 里，是因为 gradio 的缓存目录常量在 import 时就定下来了。`facefusion.ini` 的 `[paths] temp_path` 设为 `D:\facefusion\temp`，统管临时帧目录。原因是批量成片会在缓存里各留一份完整拷贝（实测 7 个目标就堆到 3.5 GB），而系统盘剩余空间不足以支撑整轮批量。旧系统盘缓存已清理，释放约 3.4 GB。

**无版本控制。** 没有 Git 仓库，无法追溯改动。

# FaceCopyer 1.0.0

本地离线换脸工具，支持图片与视频批量处理。所有推理都在本机完成，不联网、不上传素材。

> **本项目基于开源项目 FaceFusion 3.9.0 改进而来**（OpenRAIL-AS 许可，上游作者 Henry Ruhs）。
> 底层的换脸、人脸检测、关键点、增强等推理能力沿用上游，FaceCopyer 的改造集中在下面这张对照表里的场景化能力上。

![FaceCopyer](facecopyer.png)

## 主要特点

- **以「目标脸有遮挡」为主线做出来的工具**：口罩、刘海、贴纸、蝴蝶结挡住半张脸时，先修掉遮挡再换脸，避免五官错位和遮挡物残留
- **手动描边**：自动检测不准时，直接用画笔涂出要修复的区域，覆盖自动结果
- **关键点继承**：去遮挡前先缓存原图的人脸关键点，换脸时复用，避免在修复后的空白脸上重新检测导致错位
- **批量处理**：图片与视频可以混在同一批里跑，带实时进度、跳过已存在成片、中断后续跑
- **失败提示**：处理中止时界面直接弹出具体原因，不用去翻终端日志
- **垃圾清理**：内置清理面板，缓存与残余文件可一键回收，不必手动翻目录
- **中文界面**：完整汉化，可在界面左上角一键切换中英文
- **完全离线**：模型下载到本地后，日常使用不需要联网
- **换台机器也能跑**：端口、目录、设备、缓存策略全部收在一个配置文件里，不用改代码

## 相对 FaceFusion 3.9.0 的改动

| 能力 | FaceFusion 3.9.0 原版 | FaceCopyer 1.0.0 |
| --- | --- | --- |
| 目标脸有遮挡 | 直接换脸，遮挡物常残留或造成五官错位 | 换脸前调用本地 IOPaint（LaMa 模型）去除遮挡 |
| 修复掩码 | 无手动干预入口 | 网页画笔涂抹遮挡物，可替换自动检测结果 |
| 去遮挡后的人脸检测 | 无此环节 | 复用修复前缓存的关键点，避免在修复后的空白脸上重新检测 |
| 界面语言 | 英文 | 中英双语，界面内一键切换 |
| 批量处理 | 命令行 `batch-run`，仅图片，无进度显示 | 界面内批量面板，图片与视频混合，实时进度、跳过已存在成片、中断续跑 |
| 输出组织 | 单一输出目录 | 按类型分目录（`output\picture` / `output\video`），路径可改 |
| 动态 WebP | 不支持 | 自动转 MP4 后再进入处理流程 |
| 处理失败 | 只写终端日志 | 界面弹窗直接给出原因 |
| 缓存与残余文件 | 无清理入口 | 内置「清理垃圾文件」面板 |
| 素材退出 | 需重新上传才能清空 | 源图/目标图旁各有独立「清除」按钮 |
| 部署方式 | 路径与端口散落在代码里 | 全部收进 `facecopyer.ini`，配 `setup.bat` 向导，改配置不改代码 |

## 部署

### 前置条件

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / 11 |
| Python | 3.10 以上（3.12 已验证） |
| 显卡 | NVIDIA 显卡可选。有 CUDA 会用 GPU，没有就回退 CPU（慢很多） |
| 磁盘 | 预留 10 GB 以上：模型约数 GB，批量处理的临时副本很占空间 |

### 三步跑起来

```
1. 准备 Python 环境
   python -m venv venv
   venv\Scripts\python.exe -m pip install -r source\requirements.txt

   （可选）去遮挡功能需要独立环境，不装就只能换脸：
   python -m venv iopaint_venv
   iopaint_venv\Scripts\python.exe -m pip install iopaint

2. 双击 setup.bat     ← 部署向导，逐个确认端口、目录、设备并写入 facecopyer.ini
3. 双击 run.bat       ← 启动。会自动清端口、拉去遮挡服务、开界面
```

`run.bat` 与项目所在盘符、目录名无关，整个文件夹拷到别的机器或别的盘都能直接用。它会依次做三件事：

1. 清掉占用界面端口的旧进程
2. 按配置拉起 IOPaint 去遮挡服务（缺该环境时降级为「仅换脸」并给出重建命令）
3. 启动 FaceCopyer 界面并自动打开浏览器

启动后可以访问：

| 服务 | 地址 | 是否需要手动访问 |
| --- | --- | --- |
| FaceCopyer 主界面 | http://127.0.0.1:7860 | 是 |
| IOPaint 去遮挡后端 | http://127.0.0.1:8081 | 否，仅供程序内部调用 |

首次执行去遮挡时，需要加载人脸检测模型并完成 CUDA 首次预热，通常约 30 秒；此后每张图约 1 到 1.7 秒。这个冷启动开销与是否使用显卡无关，属于模型加载本身。

界面操作的完整说明见项目根目录的 `使用教程.html`。

### 检查当前配置

```
run.bat --check       只打印生效设置 + 环境体检结果，不启动
run.bat --setup       等价于 setup.bat
```

环境体检会逐项报告主环境、去遮挡环境、去遮挡模型、GPU 加速、模型仓库的状态，部署出问题时先看这里。

## 本地配置（facecopyer.ini）

所有与本机相关的设置都放在项目根目录的 `facecopyer.ini`。**首次运行 `run.bat` 时会按模板自动生成**，仓库里只提交带注释的模板 `facecopyer.ini.example`，你自己的配置不会进版本库。

改配置有两条路：双击 `setup.bat` 走向导，或者直接编辑 `facecopyer.ini`。任何一项留空都会退回默认值，删掉整个文件也能跑。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `root` | 空 | 项目根目录。留空 = 配置文件所在目录，只有把配置放到项目外面才需要填 |
| `ui_port` | 7860 | 界面端口，被占用时会先结束占用进程 |
| `open_browser` | yes | 启动后自动开浏览器。无桌面环境改成 no |
| `disable_nsfw` | yes | 关闭上游的 NSFW 内容检测。它对正常素材误拦较多，改 no 可恢复 |
| `cache_check_interval` | 900 | 界面缓存检查间隔（秒） |
| `cache_expire_seconds` | 7200 | 界面缓存过期时间（秒），批量处理吃磁盘时调小 |
| `download_providers` | huggingface, github | 模型下载源顺序，国内建议 huggingface 在前 |
| `venv_dir` | venv | 主 Python 环境目录 |
| `iopaint_venv_dir` | iopaint_venv | 去遮挡环境目录，留空 = 不启用去遮挡 |
| `temp_dir` | temp | 临时目录，**建议指向数据盘**，批量处理会在这里堆副本 |
| `output_dir` | output | 输出根目录，成片写到 `output/picture` 与 `output/video` |
| `iopaint_models_dir` | iopaint_models | 去遮挡模型目录 |
| `batch_source_dir` / `batch_target_dir` | 空 | 批量面板的默认源图/目标文件夹 |
| `iopaint_port` | 8081 | 去遮挡服务端口，仅供内部调用 |
| `iopaint_device` | auto | auto / cuda / cpu。auto 有 CUDA 就用，失败自动回退 CPU |
| `iopaint_log` | iopaint_runtime.log | 去遮挡服务日志 |

配置的生效路径是：`facecopyer.ini` →（启动器）→ 环境变量 / `source/facefusion.ini` 的 `[paths]` 段 → 程序内部。所以直接跑 `source/facefusion.py` 时不会经过这套映射，建议始终用 `run.bat` 启动。

## 目录结构

```
<项目根>\
├── run.bat                     一键启动入口（路径无关）
├── setup.bat                   部署向导入口
├── _facecopyer_launcher.py     启动器：读配置、体检、清端口、播种路径、拉起服务
├── _facecopyer_config.py       配置加载器（只用标准库）
├── facecopyer.ini              本机配置（自动生成，不进版本库）
├── facecopyer.ini.example      带注释的配置模板
├── _iopaint_start.py           IOPaint 服务启动器（含设备探测与 CPU 回退）
├── _port_clean.py              启动前清理被占用的端口
├── _patch_bundle.py            Gradio 前端补丁（空值保护）
├── _patch_bundle2.py           Gradio 前端补丁（history 类型兜底）
├── facecopyer.ico              界面图标（浏览器标签页 favicon）
├── facecopyer.png              图标原图（README 展示用）
├── 使用教程.html                面向使用者的图文教程（纯文字版，不含配图）
├── source\                     代码目录（FaceFusion 本体）
│   ├── facefusion.py           命令行入口
│   ├── facefusion.ini          运行配置（[paths] 由启动器按 facecopyer.ini 播种）
│   ├── facefusion\             主包
│   └── tests\                  测试套件
├── venv\                       主环境（FaceFusion 本体）
├── iopaint_venv\               去遮挡环境（独立环境）
├── iopaint_models\             IOPaint 模型权重
├── output\                     输出目录
│   ├── picture\                换脸后的图片
│   └── video\                  换脸后的视频
├── temp\                       临时目录与界面缓存
└── docs\                       项目文档
```

运行时会产生三个缓存目录，都可以随时清空，清空后首次处理时会重新生成：

| 目录 | 内容 |
| --- | --- |
| `source\.occlusion_removed` | 去遮挡结果图，以及配套的 `.lm.json` 关键点文件 |
| `source\.webp_converted` | 动态 WebP 转出的 MP4 |
| `source\facefusion\.temp` | 描边编辑器生成的占位图与用户掩码图 |

## 运行环境

项目使用两个相互隔离的 Python 环境，它们的依赖不通用，改动时务必确认在哪个环境里操作。

| | `venv` | `iopaint_venv` |
| --- | --- | --- |
| 用途 | 运行 FaceCopyer 本体与界面 | 运行 IOPaint 去遮挡服务 |
| Python | 3.12.10 | 3.12.10 |
| GPU 后端 | onnxruntime-gpu 1.24.4 | torch 2.14.0+cu126 |
| 界面库 | gradio 5.50.0 | gradio 6.28.0 |
| 其他 | numpy 2.4.6、opencv-python-headless 5.0.0.93 | IOPaint 1.6.0、diffusers 0.40.0、transformers 5.17.0 |

开发机为 NVIDIA RTX 4060 Laptop（8GB 显存）。实测去遮挡时显存峰值约 3.7GB，与换脸流程同时运行约 3.9GB。

启动器会把 venv 内 `site-packages\nvidia\*\bin` 的 CUDA 运行时目录全部加入 `PATH`（扫描而非写死目录名，换版本不会失效），并按 `disable_nsfw` 设置注入 `FACEFUSION_DISABLE_NSFW`。手动执行 `source\facefusion.py` 时需要自行补齐这些环境变量。

## 输出

换脸结果按文件类型分别落盘：

- 图片 → `<output_dir>\picture`
- 视频 → `<output_dir>\video`

两个目录都可以在界面中直接修改路径，或点「选择目录」指定其它位置，配置会写入 `source\facefusion.ini` 的 `[paths]` 段并长期保存（启动器只播种空值，不会覆盖你改过的路径）。

## 项目文档

| 文档 | 内容 |
| --- | --- |
| `docs\DEV_STATUS.md` | 项目开发目前状况：模块清单、改动范围、功能完成度、待办事项 |
| `docs\MODELS.md` | 模型选型指南：各类模型的优缺点、适用素材与组合建议 |
| `docs\PITFALLS.md` | 历史踩坑记录：已解决的疑难问题及其根因 |
| `docs\HANDOVER.md` | 历史项目交接记录：环境搭建、关键数据流、风险点与协作建议 |

## 仓库与分发说明

**模型权重不随仓库分发。** `source\.assets\` 体积达数 GB，已在 `.gitignore` 中排除，首次运行时程序会按需自动下载。其中 `inswapper_128` 等模型为 Non-Commercial 许可，请勿二次分发。

**不要删除下划线开头的文件。** `_facecopyer_config.py`、`_facecopyer_launcher.py`、`_iopaint_start.py`、`_port_clean.py`、`_patch_bundle.py`、`_patch_bundle2.py` 看起来像临时脚本，实际是启动链路的一环：前两个是配置加载器与启动器，中间两个负责拉起去遮挡服务与清端口，最后两个修 Gradio 前端。

**上游模型仓库地址不要改。** 模型条目里的 `resolve_download_url('models-3.9.0', ...)` 以及 `__metadata__` 中的 `'vendor': 'FaceFusion'` 是模型来源信息，改掉会导致模型无法下载。Python 包名也沿用上游的 `facefusion`（重命名包会牵动全部 import），与程序对外名称不冲突。

## 许可

遵循上游的 **OpenRAIL-AS** 许可（见 `source\LICENSE.md`）。使用前请阅读许可中对用途的限制条款；请勿将本工具用于任何未经当事人同意的换脸场景。

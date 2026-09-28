# FaceCopyer 1.0.0

本地离线换脸工具，支持图片与视频批量处理。所有推理都在本机完成，不联网、不上传素材。

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

## 与 FaceFusion 的关系

本项目基于开源项目 [FaceFusion](https://github.com/facefusion/facefusion) 3.9.0 二次开发，沿用其 **OpenRAIL-AS** 许可，上游作者为 Henry Ruhs。底层的换脸、人脸检测、关键点、增强等推理能力保持原样，本项目的改造集中在下面这张表里的场景化能力上：

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

## 快速开始

双击项目根目录的 `run.bat` 即可完成全部启动。它会依次做三件事：

1. 清理 7860 端口上残留的旧进程（`_port_clean.py`）
2. 在 8081 端口拉起 IOPaint 去遮挡服务（`_iopaint_start.py`）
3. 启动 FaceCopyer 界面并自动打开浏览器

启动后可以访问：

| 服务 | 地址 | 是否需要手动访问 |
| --- | --- | --- |
| FaceCopyer 主界面 | http://127.0.0.1:7860 | 是 |
| IOPaint 去遮挡后端 | http://127.0.0.1:8081 | 否，仅供程序内部调用 |

首次执行去遮挡时，需要加载人脸检测模型并完成 CUDA 首次预热，通常约 30 秒；此后每张图约 1 到 1.7 秒。这个冷启动开销与是否使用显卡无关，属于模型加载本身。

界面操作的完整说明见项目根目录的 `使用教程.html`。

## 目录结构

```
D:\facefusion\
├── run.bat                     一键启动入口
├── _iopaint_start.py           IOPaint 服务启动器（含设备探测与 CPU 回退）
├── _port_clean.py              启动前清理 7860 端口
├── _patch_bundle.py            Gradio 前端补丁（空值保护）
├── _patch_bundle2.py           Gradio 前端补丁（history 类型兜底）
├── facecopyer.ico              界面图标（浏览器标签页 favicon）
├── facecopyer.png              图标原图（README 展示用）
├── 使用教程.html                面向使用者的图文教程（纯文字版，不含配图）
├── source\                     代码目录（FaceFusion 本体）
│   ├── facefusion.py           命令行入口
│   ├── facefusion.ini          运行配置
│   ├── facefusion\             主包
│   └── tests\                  测试套件
├── venv\                       主环境（FaceFusion 本体）
├── iopaint_venv\               去遮挡环境（独立环境）
├── iopaint_models\             IOPaint 模型权重
├── output\                     输出目录
│   ├── picture\                换脸后的图片
│   └── video\                  换脸后的视频
├── test_photo\                 测试素材
├── swap_task\                  批量处理素材目录
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

两个环境都跑在 NVIDIA RTX 4060 Laptop（8GB 显存）上，驱动版本 616.92。实测去遮挡时显存峰值约 3.7GB，与换脸流程同时运行约 3.9GB，余量充足。

`run.bat` 会把 venv 内的 CUDA 运行时目录临时加入 `PATH`，并设置 `FACEFUSION_DISABLE_NSFW=1`。这两个设置只在通过 `run.bat` 启动时生效，如果手动执行 `source\facefusion.py`，需要自行补齐，否则可能出现找不到 CUDA 动态库或内容检测拦截。

## 输出

换脸结果按文件类型分别落盘：

- 图片 → `D:\facefusion\output\picture`
- 视频 → `D:\facefusion\output\video`

两个目录都可以在界面中直接修改路径，或点「选择目录」指定其它位置，配置会写入 `source\facefusion.ini` 的 `[paths]` 段并长期保存。

## 项目文档

| 文档 | 内容 |
| --- | --- |
| `docs\DEV_STATUS.md` | 项目开发目前状况：模块清单、改动范围、功能完成度、待办事项 |
| `docs\MODELS.md` | 模型选型指南：各类模型的优缺点、适用素材与组合建议 |
| `docs\PITFALLS.md` | 历史踩坑记录：已解决的疑难问题及其根因 |
| `docs\HANDOVER.md` | 历史项目交接记录：环境搭建、关键数据流、风险点与协作建议 |

## 仓库与分发说明

**模型权重不随仓库分发。** `source\.assets\` 体积达数 GB，已在 `.gitignore` 中排除，首次运行时程序会按需自动下载。其中 `inswapper_128` 等模型为 Non-Commercial 许可，请勿二次分发。

**不要删除根目录下划线开头的脚本。** `_iopaint_start.py`、`_port_clean.py`、`_patch_bundle.py`、`_patch_bundle2.py` 这四个下划线命名的文件看起来像临时脚本，实际是 `run.bat` 的依赖或关键修复工具。名称沿用历史习惯，尚未重命名。

**路径写死在 `D:\facefusion`。** `run.bat`、`source\facefusion.ini` 以及部分脚本使用绝对路径，换到别的机器上部署时需要先统一改路径。

## 许可

遵循上游的 **OpenRAIL-AS** 许可（见 `source\LICENSE.md`）。使用前请阅读许可中对用途的限制条款；请勿将本工具用于任何未经当事人同意的换脸场景。

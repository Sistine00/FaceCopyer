# 历史项目交接记录

面向接手这个项目的开发者，说明从哪里入手、哪些地方容易踩、当前还差什么。阅读顺序建议是先看项目根目录的 `README.md` 建立整体印象，再看 `DEV_STATUS.md` 了解改动范围，本文档负责交代实操层面的细节。

## 当前状态

项目在 `D:\facefusion` 下，代码在 `source` 子目录。所基于的上游版本、改动清单和功能完成度见 `DEV_STATUS.md`，这里只强调三点：

代码可以正常运行，换脸、去遮挡、手动描边、批量处理、分目录输出这几条主链路都在实测中通过。

项目**没有版本控制**，没有初始化 Git 仓库。这意味着任何改动都无法回退，多人同时修改会互相覆盖。这是接手后第一件需要处理的事。

代码里存在若干"看起来像临时文件、实际不能删"的脚本，详见下方"必须保留的文件"。

## 新机器部署

当前所有路径都是 Windows 绝对路径，写死在 `run.bat`、`_iopaint_start.py`、`_port_clean.py` 和 `facefusion.ini` 里。如果换机器或换盘符，需要同步修改这些位置。

部署步骤：

**准备主环境。** 在 `D:\facefusion\venv` 中安装 Python 3.12 环境，安装 `source\requirements.txt`。注意两处与声明文件不一致的地方：`requirements.txt` 声明的是 CPU 版 `onnxruntime==1.29.0`，实际运行用的是 GPU 版 `onnxruntime-gpu 1.24.4`，直接按声明安装会退化成 CPU 推理；`Pillow` 未在声明文件中，目前靠 gradio 间接引入。建议修正声明文件后再安装。

**准备去遮挡环境。** 在 `D:\facefusion\iopaint_venv` 中单独建立环境，安装 IOPaint 1.6.0，并把 torch 与 torchvision 换成 CUDA 构建：

```
D:\facefusion\iopaint_venv\Scripts\python.exe -m pip install ^
  --index-url https://mirror.sjtu.edu.cn/pytorch-wheels/cu126 ^
  torch==2.14.0+cu126 torchvision==0.29.0+cu126
```

这个环境与主环境相互隔离，不要混用依赖。国内直连 PyTorch 官方源极慢（实测 0.49 MB/s），务必使用镜像。

**放置模型。** IOPaint 的模型放在 `D:\facefusion\iopaint_models`，至少需要 `torch\hub\checkpoints\big-lama.pt`。FaceCopyer 自身的模型会在首次运行时自动下载。

**重新打前端补丁。** 这一步容易漏。执行根目录的 `_patch_bundle.py` 与 `_patch_bundle2.py`，它们会修改 `venv` 内 Gradio 的前端构建产物。如果跳过这一步，手动描边画布和图片加载会出现已知的前端异常，具体原理见 `PITFALLS.md`。注意补丁脚本里写死了带构建哈希的文件名，升级 Gradio 后需要先确认文件名。

**启动。** 双击 `run.bat`，它会清理 7860 端口、拉起 IOPaint、启动界面并打开浏览器。

## 必须保留的文件

根目录下有四个以下划线开头的脚本，命名沿用了开发期的临时文件习惯，但它们不是临时文件：

`_iopaint_start.py` 由 `run.bat` 调用，负责启动 IOPaint 服务，内含 CUDA 可用性探测与 CPU 回退逻辑。设备选择可以通过环境变量 `IOPAINT_DEVICE` 覆盖，取值 `auto`（默认）、`cpu` 或 `cuda`。

`_port_clean.py` 由 `run.bat` 调用，启动前清理 7860 端口上残留的旧进程。

`_patch_bundle.py` 与 `_patch_bundle2.py` 是 Gradio 前端问题的修复工具，重装或升级 Gradio 之后必须重新执行。

另外两个无下划线前缀的文件 `test_occlusion_integration.py` 与 `test_outline_fill.py` 是自研功能的验证脚本，独立运行、非 pytest 风格，可以作为回归验证使用，但尚未纳入 `source\tests` 测试套件。

## 关键文件地图

| 文件或目录 | 作用 |
| --- | --- |
| `run.bat` | 一键启动，串联端口清理、IOPaint、主界面 |
| `_iopaint_start.py` | 去遮挡服务启动器，含设备探测与回退 |
| `source\facefusion\iopaint_remove.py` | 去遮挡核心：掩码生成、关键点缓存、调用 IOPaint |
| `source\facefusion\uis\components\occlusion_editor.py` | 手动描边编辑器 |
| `source\facefusion\uis\components\batch_runner.py` | 批量换脸面板 |
| `source\facefusion\uis\components\output.py` | 图片/视频分目录输出与自定义路径 |
| `source\facefusion\webp_helper.py` | 动态 WebP 转 MP4 |
| `source\facefusion\locales_zh.py` | 中文词表 |
| `source\facefusion\uis\layouts\default.py` | 界面整体布局编排 |
| `source\facefusion.ini` | 运行配置，含语言、执行设备、输出目录、批量目录 |

## 数据流

理解下面这条链路，就掌握了这个项目与上游最核心的区别。

用户在界面上选好目标图并启动换脸后，`instant_runner` 会先判断当前是否处于去遮挡模式且 IOPaint 可用。满足条件时，把目标图路径和描边掩码路径交给 `preprocess_target_for_occlusion`。

该函数进入 `remove_occlusion`，流程是：先查缓存，未命中则读图做人脸检测（多模型回退），接着生成掩码（有手动描边就用描边，否则用自动掩码），然后在**原始遮挡图上**检测 68 个关键点并做眼部对称校正，把关键点连同检测框一起缓存成 `.lm.json`，最后把原图和掩码以 base64 编码 POST 给 IOPaint 的 `/api/v1/inpaint` 接口，拿回修复后的图片并落盘到 `source\.occlusion_removed`。

修复后的图片随后进入常规换脸流程，此时 `face_swapper` 会通过 `override_target_landmarks()` 读取先前缓存的关键点，覆盖掉在空白脸上重新检测的结果，从而保证五官对齐与无遮挡场景一致。

批量流程走 `batch_runner.run_batch()`，逐张确定输出目录（按目标类型选图片或视频目录）、构造输出路径、提交任务并持续输出进度。批量路径目前不读取手动描边掩码。

## 风险点

**没有版本控制。** 最重要的一条。建议先初始化仓库并提交当前状态作为基线，同时在 `.gitignore` 中排除 `venv`、`iopaint_venv`、`iopaint_models`、`output`、`test_photo`、`source\.occlusion_removed`、`source\.webp_converted`、`source\facefusion\.temp`，避免把数 GB 的环境和缓存提交进去。

**前端补丁会被覆盖。** 补丁打在已安装的 Gradio 包内，任何 Gradio 重装都会使其失效。可以考虑把补丁脚本改造成启动时自动执行，降低遗漏概率。

**去遮挡缓存不响应掩码变化。** 缓存键只包含目标图路径哈希与时间戳，不包含掩码内容，改描边后不会自动失效。这是当前已知的缺陷，见 `DEV_STATUS.md`。

**两个环境的依赖版本并存。** `venv` 用 gradio 5.50.0，`iopaint_venv` 用 gradio 6.28.0。升级任一库前先确认操作的是哪个环境。另外 `iopaint_venv` 内部的 IOPaint 依赖树存在若干版本警告（如 `diffusers`、`fastapi`、`huggingface-hub` 与 IOPaint 声明不一致），这些警告在功能验证前就已存在，当前不影响使用，但重装时需要留意。

**显存余量。** 显卡是 RTX 4060 Laptop，8GB 显存，与桌面显示共享。实测去遮挡单独运行峰值约 3.7GB，与换脸流程同时运行约 3.9GB，余量约 4.3GB。如果后续在同一张卡上再叠加其它模型，需要重新评估。

**绝对路径写死。** 换机器需要同步修改 `run.bat`、`_iopaint_start.py`、`_port_clean.py`、`facefusion.ini` 以及 `batch_runner.py` 中的路径占位符。

## 验证改动是否正常

**服务是否健康。** 启动后确认两个端口都在监听：

```powershell
Get-NetTCPConnection -LocalPort 7860 -State Listen   # FaceCopyer 界面
Get-NetTCPConnection -LocalPort 8081 -State Listen   # IOPaint 服务
```

或直接浏览器访问 `http://127.0.0.1:7860`。

**IOPaint 是否在跑显卡。** 查看 `D:\facefusion\iopaint_runtime.log`，搜索 `"device"` 字段，应为 `"cuda"`；同时确认 `torch: 2.14.0+cu126`。如果显示 `cpu`，说明设备探测回退到了 CPU，去遮挡会慢约 6 倍。

**去遮挡功能是否正常。** 运行根目录的 `test_occlusion_integration.py`，或直接在界面上用带遮挡的目标图跑一次。需要注意首次调用有约 30 秒的冷启动开销（加载检测模型与 CUDA 预热），属正常现象，预热后单张约 1 至 1.7 秒。

**界面是否起来。** 如果 `run.bat` 执行后浏览器打不开，先看控制台输出。界面渲染阶段的任何异常都会表现为"服务没启动"，`render()` 中抛错是常见原因。

## 待办事项

按优先级排列，均来自 `DEV_STATUS.md` 中的已知缺口。

修正 `requirements.txt`，使其与实际安装一致（GPU 版 onnxruntime、补充 Pillow），避免他人重建环境时踩坑。

建立版本控制，提交当前状态作为基线。

让批量处理支持手动描边掩码，补上 `batch_runner.py` 中已导入但未调用的去遮挡逻辑。

把掩码内容纳入去遮挡缓存键，解决改描边不生效的问题。

把根目录两个验证脚本改造成 pytest 用例，纳入 `source\tests`。

考虑给 `_iopaint_start.py` 等关键脚本改名去掉下划线前缀，消除"看起来像临时文件"的误导。改名后需同步更新 `run.bat`。

## 历史清理记录

2026 年 9 月 28 日对项目做过一次清理，移除开发期积累的调试文件共 546 个，释放约 253 MB。被清理的内容包括：根目录下开发期的截图、文本片段、日志和一次性探测脚本，Playwright 自动化脚本与 ImageEditor 复现脚本，`test_assets` 目录下遮挡算法调试过程中的全部实验产物（约 142 MB），`swap_task\_debug_test` 调试目录，`source` 目录下的一次性探测脚本与 Gradio 源码摘录，以及 `source\.occlusion_removed`、`source\.webp_converted`、`source\.temp` 三个目录中的缓存与测试残留。

保留的是运行依赖、修复工具与自研功能的验证脚本。如果发现某个文件缺失影响了正常工作，可以从本文档的"关键文件地图"和 `DEV_STATUS.md` 的模块清单反查该文件的作用，多数属于可重新生成的调试产物。

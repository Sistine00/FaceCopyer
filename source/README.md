FaceCopyer
==========

> 本地离线换脸工具，支持图片与视频批量处理。

这里是 **FaceCopyer 1.0.0** 的代码目录。面向使用者的说明、目录结构、运行环境与许可信息，请看仓库根目录的 `README.md`；界面操作教程见根目录的 `使用教程.html`。

本目录的代码底座是开源项目 [FaceFusion](https://github.com/facefusion/facefusion) 3.9.0（OpenRAIL-AS 许可，作者 Henry Ruhs）。Python 包名沿用了上游的 `facefusion`，因此你会在这里看到大量 `from facefusion import ...`，这是正常的，与界面和程序名已改为 FaceCopyer 不冲突。


命令行用法
----------

```
python facefusion.py [commands] [options]

options:
  -h, --help                                      show this help message and exit
  -v, --version                                   show program's version number and exit

commands:
    run                                           run the program
    headless-run                                  run the program in headless mode
    batch-run                                     run the program in batch mode
    force-download                                force automate downloads and exit
    benchmark                                     benchmark the program
    job-list                                      list jobs by status
    job-create                                    create a drafted job
    job-submit                                    submit a drafted job to become a queued job
    job-submit-all                                submit all drafted jobs to become a queued jobs
    job-delete                                    delete a drafted, queued, failed or completed job
    job-delete-all                                delete all drafted, queued, failed and completed jobs
    job-add-step                                  add a step to a drafted job
    job-remix-step                                remix a previous step from a drafted job
    job-insert-step                               insert a step to a drafted job
    job-remove-step                               remove a step from a drafted job
    job-run                                       run a queued job
    job-run-all                                   run all queued jobs
    job-retry                                     retry a failed job
    job-retry-all                                 retry all failed jobs
```

日常使用不需要敲命令行，直接双击根目录的 `run.bat` 即可。

#!/usr/bin/env python3

import os

os.environ['OMP_NUM_THREADS'] = '1'

# Gradio 的缓存目录是在 import gradio 的那一刻定下来的, 之后再用环境变量改已经晚了。
# 这个目录装着浏览器上传的素材副本、以及成片在界面里显示时另存的一份拷贝,
# 批量处理时会堆到十几 GB, 必须放在数据盘, 所以要在下面导入 facefusion.core 之前设置。
# 路径按本文件位置推算, 也就是 <项目根>\temp\gradio。
# uis/core.py 的 init() 里也设了一次, 但那次只在 gradio 导入之后, 只对运行期动态查询生效,
# 那里改用了 setdefault, 避免两处取值不一致导致上传副本被写到两个目录里。
os.environ['GRADIO_TEMP_DIR'] = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp', 'gradio'))

from facefusion import conda, core

if __name__ == '__main__':
	conda.setup()
	core.cli()

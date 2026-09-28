"""补丁 gradio 前端 bundle: 让 CommandManager.execute 容忍 history 被降级成普通对象的情况.

背景: Sketchpad/ImageEditor 在"挂载后再塞图"的路径下, command_manager.history 有时不是
Cr 实例而是同形状的普通对象, 于是 this.history.push(e) 抛 TypeError, 中断 add_image_from_url,
导致图片没能加载进画布(也不会执行 set_zoom('fit'))。这里在调用前兜底重建节点。
"""
import shutil

P = r'D:\facefusion\venv\Lib\site-packages\gradio\templates\frontend\assets\Index-DI509U_e.js'
OLD = b'async execute(e,t){await e.execute(t),this.history.push(e),this.history=this.history.next,this.current_history.update(()=>this.history)}'
NEW = b'async execute(e,t){await e.execute(t),typeof this.history.push!="function"&&(this.history=new Cr(this.history&&this.history.command)),this.history.push(e),this.history=this.history.next,this.current_history.update(()=>this.history)}'

data = open(P, 'rb').read()
if NEW in data and OLD not in data:
	print('already patched')
else:
	print('occurrences before =', data.count(OLD))
	if data.count(OLD) == 1:
		shutil.copyfile(P, P + '.hist.bak')
		data = data.replace(OLD, NEW)
		open(P, 'wb').write(data)
	data = open(P, 'rb').read()
	print('occurrences after  =', data.count(OLD))
	print('guard present      =', data.count(NEW))

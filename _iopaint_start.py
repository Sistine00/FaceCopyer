"""启动 IOPaint 去遮挡服务。

路径、端口、设备都来自 _facecopyer_config, 不再写死。
既能单独运行(python _iopaint_start.py), 也能被 _facecopyer_launcher.py import 后调用。
"""

import os
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _facecopyer_config as config

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

# 没有 IOPaint 环境时给用户的提示, 装回去的命令写在这里, 免得每次翻文档
INSTALL_HINT = [
	'  重建去遮挡环境(需要联网, 约 2 GB):',
	'    python -m venv iopaint_venv',
	'    iopaint_venv\\Scripts\\python.exe -m pip install iopaint',
	'  完成后重新运行 run.bat 即可。',
]


def is_port_open(port, host = '127.0.0.1'):
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
		try:
			sock.settimeout(1)
			sock.connect((host, port))
			return True
		except OSError:
			return False


def resolve_command(settings):
	"""优先用 iopaint.exe; 没有就退回 python -m iopaint。都没有则返回空列表。"""
	if os.path.isfile(settings.iopaint_exe):
		return [ settings.iopaint_exe ]
	if os.path.isfile(settings.iopaint_python):
		return [ settings.iopaint_python, '-m', 'iopaint' ]
	return []


def detect_device(settings):
	"""auto = 由 iopaint_venv 里的 torch 自己报告; 也可以在配置里写死 cuda / cpu。"""
	requested = (os.environ.get('IOPAINT_DEVICE') or settings.iopaint_device or 'auto').strip().lower()
	if requested in ( 'cpu', 'cuda' ):
		return requested
	if not os.path.isfile(settings.iopaint_python):
		return 'cpu'
	try:
		result = subprocess.run(
			[ settings.iopaint_python, '-c', 'import torch; print("cuda" if torch.cuda.is_available() else "cpu")' ],
			capture_output = True,
			text = True,
			timeout = 90
		)
		detected = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ''
		if detected in ( 'cpu', 'cuda' ):
			return detected
	except Exception:
		pass
	return 'cpu'


def launch(settings, device, env, log_handle):
	command = resolve_command(settings) + [
		'start',
		'--host', '127.0.0.1',
		'--port', str(settings.iopaint_port),
		'--model', 'lama',
		'--model-dir', settings.iopaint_models_dir,
		'--no-inbrowser',
		'--device', device,
	]
	process = subprocess.Popen(
		command,
		env = env,
		stdout = log_handle,
		stderr = subprocess.STDOUT,
		cwd = settings.root,
		creationflags = NO_WINDOW
	)
	for _ in range(60):
		time.sleep(1)
		if is_port_open(settings.iopaint_port):
			return process
		if process.poll() is not None:
			return None
	# 进程还活着但一直没监听: 主动结束它, 好给回退尝试腾出端口
	process.terminate()
	try:
		process.wait(timeout = 10)
	except Exception:
		process.kill()
	time.sleep(2)
	return None


def start(settings = None):
	"""启动去遮挡服务。返回 running / unavailable / failed。"""
	settings = settings or config.get()
	port = settings.iopaint_port

	if is_port_open(port):
		print('[INFO] 去遮挡服务已在 {} 端口运行, 跳过启动'.format(port))
		return 'running'

	if not resolve_command(settings):
		print('[WARN] 没找到 IOPaint 环境: {}'.format(settings.iopaint_venv_dir))
		print('       界面仍可正常换脸, 只是「遮挡处理」相关功能不可用。')
		for line in INSTALL_HINT:
			print(line)
		return 'unavailable'

	os.makedirs(settings.iopaint_models_dir, exist_ok = True)
	os.makedirs(settings.temp_dir or settings.root, exist_ok = True)

	env = dict(os.environ)
	env['LAMA_MODEL_URL'] = os.path.join(settings.iopaint_models_dir, 'torch', 'hub', 'checkpoints', 'big-lama.pt')
	env['HF_HUB_CACHE'] = os.path.join(settings.iopaint_models_dir, 'hub')

	device = detect_device(settings)
	print('[INFO] 去遮挡设备: {}'.format(device))

	try:
		log_handle = open(settings.iopaint_log, 'a', encoding = 'utf-8', buffering = 1)
	except OSError as error:
		print('[ERROR] 无法写去遮挡日志 {}: {}'.format(settings.iopaint_log, error))
		return 'failed'

	with log_handle:
		process = launch(settings, device, env, log_handle)

		if process is None and device == 'cuda':
			print('[WARN] CUDA 启动失败, 回退 CPU 重试')
			if is_port_open(port):
				print('[INFO] 去遮挡服务已在 {} 端口运行'.format(port))
				return 'running'
			process = launch(settings, 'cpu', env, log_handle)
			device = 'cpu'

	if process is not None:
		print('[INFO] 去遮挡服务就绪: http://127.0.0.1:{} ({})'.format(port, device))
		return 'running'

	print('[ERROR] 去遮挡服务启动失败, 详见 {}'.format(settings.iopaint_log))
	return 'failed'


def main():
	settings = config.get()
	print('[INFO] 配置来源: {}{}'.format(settings.config_path, '' if settings.config_found else ' (未找到, 使用内置默认值)'))
	start(settings)


if __name__ == '__main__':
	main()

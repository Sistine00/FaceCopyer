"""FaceCopyer 启动器 / 部署向导。

run.bat 只负责找到 Python 并把控制权交给这里, 真正的启动逻辑都在这个文件里:

  1. 读取 facecopyer.ini (缺省时用内置默认值, 并生成一份带注释的配置)
  2. 体检: 主环境、去遮挡环境、CUDA、模型目录
  3. 清掉被占用的界面端口
  4. 把配置里的输出/临时/批量目录写进 source/facefusion.ini 的 [paths]
  5. 启动 IOPaint 去遮挡服务(没有该环境时降级为「仅换脸」)
  6. 用配置好的环境变量启动 FaceCopyer 界面

用法:
  python _facecopyer_launcher.py            正常启动
  python _facecopyer_launcher.py --setup    部署向导, 生成/修改 facecopyer.ini
  python _facecopyer_launcher.py --check    只打印生效设置与环境体检结果
"""

import argparse
import configparser
import io
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _facecopyer_config as config
import _iopaint_start
import _port_clean

# 这些键会在启动时从 facecopyer.ini 播种到 source/facefusion.ini 的 [paths]
# 只在目标位置为空时写入, 已经填过的值(例如用户在界面上改的)不会被覆盖。
PATH_SEEDS = (
	('temp_path', 'temp_dir'),
	('output_path', 'output_dir'),
	('output_image_path', 'output_image_dir'),
	('output_video_path', 'output_video_dir'),
	('batch_source_dir', 'batch_source_dir'),
	('batch_target_dir', 'batch_target_dir'),
)


def display_width(text):
	"""中文按两个字符宽计算, 用来对齐输出。"""
	width = 0
	for character in text:
		width += 2 if ord(character) > 0x2E7F else 1
	return width


def pad(text, width):
	return text + ' ' * max(0, width - display_width(text))


def rule(title = ''):
	print('=' * 62)
	if title:
		print('  ' + title)
		print('=' * 62)


def print_settings(settings):
	for label, value in settings.environment_lines():
		print('  {}{}'.format(pad(label, 18), value))


def seed_app_config(settings):
	"""把配置里的目录播种到 source/facefusion.ini。返回本次写入的项。"""
	path = settings.facefusion_ini
	if not os.path.isfile(path):
		return []

	parser = configparser.ConfigParser()
	try:
		parser.read(path, encoding = 'utf-8')
	except Exception as error:
		print('[WARN] 读取 {} 失败: {}: {}'.format(path, type(error).__name__, error))
		return []
	if not parser.has_section('paths'):
		parser.add_section('paths')

	written = []
	for option, attribute in PATH_SEEDS:
		value = getattr(settings, attribute, '')
		if not value:
			continue
		try:
			current = (parser.get('paths', option, fallback = '') or '').strip() if parser.has_option('paths', option) else ''
		except Exception:
			current = ''
		if current:
			continue
		parser.set('paths', option, value)
		written.append((option, value))

	if not written:
		return []

	# 先在内存里生成新内容并确认非空, 再落盘, 避免写坏配置后没法恢复
	buffer = io.StringIO()
	try:
		parser.write(buffer)
	except Exception as error:
		print('[WARN] 生成配置内容失败: {}: {}'.format(type(error).__name__, error))
		return []
	text = buffer.getvalue()
	if not text.strip():
		print('[WARN] 生成的新配置为空, 已跳过写入以免破坏 {}'.format(path))
		return []

	try:
		with open(path, 'rb') as handle:
			original = handle.read()
		if original.strip():
			with open(path + '.bak', 'wb') as handle:
				handle.write(original)
		with open(path, 'w', encoding = 'utf-8') as handle:
			handle.write(text)
	except OSError as error:
		print('[WARN] 写入 {} 失败: {}'.format(path, error))
		return []

	for option, value in written:
		print('[INFO] 已写入 {} 的 paths.{} = {}'.format(os.path.basename(path), option, value))
	return written


def check_python(executable):
	if not os.path.isfile(executable):
		return None
	try:
		completed = subprocess.run([ executable, '-c', 'import sys; print(".".join(str(v) for v in sys.version_info[:3]))' ],
			capture_output = True, text = True, timeout = 60)
		version = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ''
		return version or None
	except Exception:
		return None


def check_cuda(settings):
	"""问一下主环境里的 onnxruntime 能不能用 GPU。"""
	if not os.path.isfile(settings.venv_python):
		return None
	try:
		completed = subprocess.run(
			[ settings.venv_python, '-c', 'import onnxruntime; print(",".join(onnxruntime.get_available_providers()))' ],
			capture_output = True, text = True, timeout = 180
		)
		providers = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ''
		if not providers:
			return None
		return 'GPU 可用' if 'CUDAExecutionProvider' in providers else '仅 CPU'
	except Exception:
		return None


def diagnose(settings):
	"""体检结果, 供向导打印。每项是 (名称, 状态, 说明)。"""
	rows = []

	python_version = check_python(settings.venv_python)
	if python_version:
		rows.append(('主环境', '正常', 'Python {} ({})'.format(python_version, settings.venv_dir)))
	else:
		rows.append(('主环境', '缺失', '找不到 {}, 界面无法启动'.format(settings.venv_python)))

	iopaint_version = check_python(settings.iopaint_python)
	if iopaint_version:
		rows.append(('去遮挡环境', '正常', 'Python {} ({})'.format(iopaint_version, settings.iopaint_venv_dir)))
	else:
		rows.append(('去遮挡环境', '缺失', '找不到 {}, 遮挡功能不可用(不影响换脸)'.format(settings.iopaint_python)))

	lama_model = os.path.join(settings.iopaint_models_dir, 'torch', 'hub', 'checkpoints', 'big-lama.pt')
	if os.path.isfile(lama_model):
		size = os.path.getsize(lama_model) / (1024 * 1024)
		rows.append(('去遮挡模型', '正常', 'big-lama.pt 已就位 ({:.0f} MB)'.format(size)))
	elif os.path.isdir(settings.iopaint_models_dir):
		rows.append(('去遮挡模型', '待下载', '首次使用去遮挡时自动下载到 {}'.format(settings.iopaint_models_dir)))
	else:
		rows.append(('去遮挡模型', '待创建', '目录 {} 会在首次使用时自动创建'.format(settings.iopaint_models_dir)))

	cuda_status = check_cuda(settings)
	if cuda_status:
		rows.append(('GPU 加速', '正常' if cuda_status == 'GPU 可用' else '受限', cuda_status + ' (onnxruntime)'))
	else:
		rows.append(('GPU 加速', '未知', '无法查询, 不影响启动'))

	assets = os.path.join(settings.source_dir, '.assets')
	if os.path.isdir(assets):
		rows.append(('模型仓库', '正常', '{} 已存在, 缺失的模型会在首次运行时下载'.format(assets)))
	else:
		rows.append(('模型仓库', '待创建', '首次运行时自动下载所需模型(约数 GB)'))

	return rows


def print_diagnose(settings):
	for name, status, detail in diagnose(settings):
		print('  {}{}{}'.format(pad(name, 14), pad(status, 10), detail))


def ask(prompt, default, choices = None):
	"""交互式提问。空输入、非交互环境(EOFError)一律取默认值。"""
	suffix = ' [{}]'.format(default) if default != '' else ''
	while True:
		try:
			answer = input('  {}{}: '.format(prompt, suffix)).strip()
		except (EOFError, KeyboardInterrupt):
			print()
			return default
		if not answer:
			return default
		if choices and answer.lower() not in choices:
			print('    只能填以下之一: {}'.format(' / '.join(choices)))
			continue
		return answer


def ask_int(prompt, default, minimum = 1, maximum = 65535):
	while True:
		answer = ask(prompt, str(default))
		try:
			value = int(answer)
		except ValueError:
			print('    需要填整数')
			continue
		if value < minimum or value > maximum:
			print('    需要 {}-{} 之间'.format(minimum, maximum))
			continue
		return value


def run_setup():
	settings = config.get()

	rule('FaceCopyer 1.0.0 部署向导')
	print('项目目录: {}'.format(config.PROJECT_ROOT))
	print('配置文件: {}'.format(settings.config_path))
	print()
	print('当前环境体检:')
	print_diagnose(settings)
	print()

	values = dict(settings.values)

	rule('第一步 · 常用设置')
	print('  直接回车表示保持括号里的值, 全部回车 = 用默认值。')
	print()
	values['ui_port'] = ask_int('界面端口', values.get('ui_port', '7860'), 1024, 65535)
	values['open_browser'] = ask('启动后自动打开浏览器(yes/no)', values.get('open_browser', 'yes'), ('yes', 'no', 'y', 'n', 'true', 'false'))
	values['disable_nsfw'] = ask('关闭 NSFW 内容检测(yes/no)', values.get('disable_nsfw', 'yes'), ('yes', 'no', 'y', 'n', 'true', 'false'))
	values['temp_dir'] = ask('临时目录(相对项目目录或绝对路径)', values.get('temp_dir', 'temp'))
	values['output_dir'] = ask('输出目录(相对项目目录或绝对路径)', values.get('output_dir', 'output'))

	print()
	advanced = ask('继续逐项设置高级选项(环境目录/去遮挡/缓存/下载源)?(yes/no)', 'no', ('yes', 'no', 'y', 'n'))

	if advanced.lower() in ('yes', 'y'):
		rule('第二步 · 高级设置')
		values['venv_dir'] = ask('主环境目录', values.get('venv_dir', 'venv'))
		values['iopaint_venv_dir'] = ask('去遮挡环境目录(留空 = 不启用去遮挡)', values.get('iopaint_venv_dir', 'iopaint_venv'))
		values['iopaint_models_dir'] = ask('去遮挡模型目录', values.get('iopaint_models_dir', 'iopaint_models'))
		values['iopaint_port'] = ask_int('去遮挡服务端口', values.get('iopaint_port', '8081'), 1024, 65535)
		values['iopaint_device'] = ask('去遮挡设备(auto/cuda/cpu)', values.get('iopaint_device', 'auto'), ('auto', 'cuda', 'cpu'))
		values['cache_check_interval'] = ask_int('界面缓存检查间隔(秒)', values.get('cache_check_interval', '900'), 60, 86400)
		values['cache_expire_seconds'] = ask_int('界面缓存过期时间(秒)', values.get('cache_expire_seconds', '7200'), 300, 604800)
		values['download_providers'] = ask('模型下载源顺序(逗号分隔)', values.get('download_providers', 'huggingface, github'))
		values['batch_source_dir'] = ask('批量处理默认源图目录(可留空)', values.get('batch_source_dir', ''))
		values['batch_target_dir'] = ask('批量处理默认目标目录(可留空)', values.get('batch_target_dir', ''))

	try:
		path = config.write_config(settings.config_path, values)
	except OSError as error:
		print()
		print('[ERROR] 写入 {} 失败: {}'.format(settings.config_path, error))
		return 1

	reloaded = config.load()
	print()
	rule('已保存')
	print('  {}'.format(path))
	print('  旧配置(如果存在)已备份为 {}.bak'.format(config.CONFIG_FILE_NAME))
	print()
	print('生效设置:')
	for label, value in reloaded.environment_lines():
		print('  {}{}'.format(pad(label, 18), value))
	print()
	print('  双击 run.bat 即可按这套设置启动。')
	print('  之后想再改, 可以直接编辑上面的文件, 也可以重新运行 setup.bat。')
	return 0


def run_check():
	settings = config.get()
	rule('FaceCopyer 1.0.0 生效设置')
	print_settings(settings)
	print()
	rule('环境体检')
	print_diagnose(settings)
	print()
	print('  界面地址: {}'.format(settings.ui_url))
	print('  去遮挡地址: {}'.format(settings.iopaint_url))
	return 0


def run_start():
	settings = config.get()

	if not os.path.isfile(settings.config_path):
		try:
			config.write_config(settings.config_path)
			print('[INFO] 首次运行, 已按默认值生成配置文件: {}'.format(settings.config_path))
			print('       需要改端口/目录/设备时, 运行 setup.bat, 或直接编辑这个文件。')
			print()
			settings = config.load()
		except OSError as error:
			print('[WARN] 生成配置文件失败: {}, 本次使用内置默认值'.format(error))
			print()

	rule('FaceCopyer 1.0.0')
	print('  基于 FaceFusion 3.9.0 二次开发 · 本地离线换脸工具')
	print_settings(settings)
	print()

	if not os.path.isfile(settings.venv_python):
		rule()
		print('[ERROR] 找不到主环境解释器:')
		print('        {}'.format(settings.venv_python))
		print()
		print('  项目依赖没有装好, 请先完成一次环境准备:')
		print('    python -m venv {}'.format(os.path.basename(settings.venv_dir) or 'venv'))
		print('    {}\\Scripts\\python.exe -m pip install -r source\\requirements.txt'.format(os.path.basename(settings.venv_dir) or 'venv'))
		print()
		print('  如果环境目录名不是默认的 venv, 请在 facecopyer.ini 的 [paths] 里改 venv_dir。')
		return 1

	entry = os.path.join(settings.source_dir, 'facefusion.py')
	if not os.path.isfile(entry):
		print('[ERROR] 找不到程序入口: {}'.format(entry))
		return 1

	print('[INFO] 清理被占用的界面端口...')
	_port_clean.free_port(settings.ui_port, '界面端口')
	print()

	seed_app_config(settings)
	print()

	print('[INFO] 启动去遮挡服务...')
	iopaint_status = _iopaint_start.start(settings)
	print()

	command = [ settings.venv_python, 'facefusion.py', 'run' ]
	if settings.open_browser:
		command.append('--open-browser')

	print('[INFO] 启动界面: {}'.format(settings.ui_url))
	if iopaint_status != 'running':
		print('[INFO] 本次为「仅换脸」模式, 「遮挡处理」相关选项不可用')
	if settings.open_browser:
		print('[INFO] 浏览器会自动打开, 首次加载需要 30-60 秒')
	print('[INFO] 关闭本窗口或按 Ctrl+C 即可停止服务')
	print()

	try:
		completed = subprocess.run(command, cwd = settings.source_dir, env = settings.environment())
	except KeyboardInterrupt:
		print()
		print('[INFO] 已手动中断')
		return 0
	except OSError as error:
		print('[ERROR] 启动失败: {}'.format(error))
		return 1

	return completed.returncode or 0


def main():
	parser = argparse.ArgumentParser(add_help = True, description = 'FaceCopyer 启动器')
	parser.add_argument('--setup', action = 'store_true', help = '部署向导: 生成/修改 facecopyer.ini')
	parser.add_argument('--check', action = 'store_true', help = '只打印生效设置与环境体检结果')
	arguments = parser.parse_args()

	if arguments.setup:
		return run_setup()
	if arguments.check:
		return run_check()
	return run_start()


if __name__ == '__main__':
	sys.exit(main())

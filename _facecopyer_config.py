"""FaceCopyer 本地配置加载器。

把原来写死在 run.bat、_iopaint_start.py、source/facefusion.ini 里的机器相关设置
(路径 / 端口 / 设备 / 开关 / 缓存策略 / 下载源) 统一收到项目根目录的 facecopyer.ini。

任何一项都可以留空或整段删掉, 缺失时退回下面的内置默认值, 所以删掉整个文件也能跑起来。
只用标准库, 兼容 Python 3.8+, 因此启动器、辅助脚本和部署向导都能直接 import。
"""

import configparser
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_NAME = 'facecopyer.ini'

# 规范键 -> (配置段, 选项名, 缺省值)
SPEC = {
	'root': ('general', 'root', ''),
	'ui_port': ('general', 'ui_port', '7860'),
	'open_browser': ('general', 'open_browser', 'yes'),
	'disable_nsfw': ('general', 'disable_nsfw', 'yes'),
	'cache_check_interval': ('general', 'cache_check_interval', '900'),
	'cache_expire_seconds': ('general', 'cache_expire_seconds', '7200'),
	'download_providers': ('general', 'download_providers', 'huggingface, github'),
	'venv_dir': ('paths', 'venv_dir', 'venv'),
	'iopaint_venv_dir': ('paths', 'iopaint_venv_dir', 'iopaint_venv'),
	'temp_dir': ('paths', 'temp_dir', 'temp'),
	'output_dir': ('paths', 'output_dir', 'output'),
	'iopaint_models_dir': ('paths', 'iopaint_models_dir', 'iopaint_models'),
	'batch_source_dir': ('paths', 'batch_source_dir', ''),
	'batch_target_dir': ('paths', 'batch_target_dir', ''),
	'iopaint_port': ('iopaint', 'port', '8081'),
	'iopaint_device': ('iopaint', 'device', 'auto'),
	'iopaint_log': ('iopaint', 'log', 'iopaint_runtime.log'),
}

DOWNLOAD_PROVIDER_CHOICES = ('huggingface', 'github')
IOPAINT_DEVICE_CHOICES = ('auto', 'cuda', 'cpu')


def default_config_path():
	return os.path.join(PROJECT_ROOT, CONFIG_FILE_NAME)


def _as_int(value, fallback):
	try:
		return int(str(value).strip())
	except (TypeError, ValueError):
		return fallback


def _as_bool(value, fallback):
	text = str(value).strip().lower()
	if not text:
		return fallback
	if text in ('1', 'true', 'yes', 'on', 'y'):
		return True
	if text in ('0', 'false', 'no', 'off', 'n'):
		return False
	return fallback


def _split_list(value):
	text = str(value).replace(';', ',').replace('\n', ',')
	return [ item.strip().lower() for item in text.split(',') if item.strip() ]


def read_raw(config_path = None):
	"""读原始配置, 返回 (键值字典, 实际使用的配置文件路径, 文件是否存在)。"""
	path = os.path.abspath(config_path or os.environ.get('FACECOPYER_CONFIG') or default_config_path())
	parser = configparser.ConfigParser()
	exists = os.path.isfile(path)
	if exists:
		try:
			parser.read(path, encoding = 'utf-8-sig')
		except (configparser.Error, OSError):
			exists = False
	values = {}
	for key, (section, option, fallback) in SPEC.items():
		value = ''
		if parser.has_section(section) and parser.has_option(section, option):
			value = (parser.get(section, option) or '').strip()
		values[key] = value if value else fallback
	return values, path, exists


class Settings():
	"""解析完成的配置。所有路径类字段都是绝对路径, 可以直接交给 subprocess。"""

	def __init__(self, values, config_path, config_found):
		self.values = values
		self.config_path = config_path
		self.config_found = config_found

		root = values.get('root', '').strip()
		self.root = os.path.normpath(root) if root else PROJECT_ROOT

		self.ui_port = _as_int(values.get('ui_port'), 7860)
		self.open_browser = _as_bool(values.get('open_browser'), True)
		self.disable_nsfw = _as_bool(values.get('disable_nsfw'), True)
		self.cache_check_interval = _as_int(values.get('cache_check_interval'), 900)
		self.cache_expire_seconds = _as_int(values.get('cache_expire_seconds'), 7200)

		providers = [ p for p in _split_list(values.get('download_providers', '')) if p in DOWNLOAD_PROVIDER_CHOICES ]
		self.download_providers = providers or list(DOWNLOAD_PROVIDER_CHOICES)

		device = (values.get('iopaint_device') or 'auto').strip().lower()
		self.iopaint_device = device if device in IOPAINT_DEVICE_CHOICES else 'auto'
		self.iopaint_port = _as_int(values.get('iopaint_port'), 8081)

		self.venv_dir = self.resolve(values.get('venv_dir'))
		self.iopaint_venv_dir = self.resolve(values.get('iopaint_venv_dir'))
		self.temp_dir = self.resolve(values.get('temp_dir'))
		self.output_dir = self.resolve(values.get('output_dir'))
		self.iopaint_models_dir = self.resolve(values.get('iopaint_models_dir'))
		self.iopaint_log = self.resolve(values.get('iopaint_log'))
		self.batch_source_dir = self.resolve(values.get('batch_source_dir'))
		self.batch_target_dir = self.resolve(values.get('batch_target_dir'))

	def resolve(self, value):
		"""把配置里的路径补成绝对路径: 相对路径按 root 解析。"""
		text = (value or '').strip()
		if not text:
			return ''
		return os.path.normpath(text if os.path.isabs(text) else os.path.join(self.root, text))

	# --- 由配置派生出来的路径 ---

	@property
	def source_dir(self):
		return os.path.join(self.root, 'source')

	@property
	def venv_python(self):
		return os.path.join(self.venv_dir, 'Scripts', 'python.exe')

	@property
	def iopaint_python(self):
		return os.path.join(self.iopaint_venv_dir, 'Scripts', 'python.exe')

	@property
	def iopaint_exe(self):
		return os.path.join(self.iopaint_venv_dir, 'Scripts', 'iopaint.exe')

	@property
	def output_image_dir(self):
		return os.path.join(self.output_dir, 'picture')

	@property
	def output_video_dir(self):
		return os.path.join(self.output_dir, 'video')

	@property
	def facefusion_ini(self):
		return os.path.join(self.source_dir, 'facefusion.ini')

	@property
	def iopaint_url(self):
		return 'http://127.0.0.1:{}/api/v1/inpaint'.format(self.iopaint_port)

	@property
	def ui_url(self):
		return 'http://127.0.0.1:{}'.format(self.ui_port)

	def cuda_bin_dirs(self):
		"""venv 里由 nvidia-*-cu12 轮子提供的 CUDA 动态库目录。

		不写死 cublas/cudnn 等具体名字, 直接扫描, 换版本或换显卡都不会失效。
		"""
		base = os.path.join(self.venv_dir, 'Lib', 'site-packages', 'nvidia')
		directories = []
		if os.path.isdir(base):
			for name in sorted(os.listdir(base)):
				binary_dir = os.path.join(base, name, 'bin')
				if os.path.isdir(binary_dir):
					directories.append(binary_dir)
		return directories

	def environment(self):
		"""构造启动 FaceCopyer 本体时使用的环境变量。"""
		env = dict(os.environ)

		path_parts = self.cuda_bin_dirs()
		path_parts.append(os.path.join(self.venv_dir, 'Scripts'))
		if env.get('PATH'):
			path_parts.append(env['PATH'])
		env['PATH'] = os.pathsep.join(path_parts)

		env['FACEFUSION_DISABLE_NSFW'] = '1' if self.disable_nsfw else '0'

		env['IOPAINT_PORT'] = str(self.iopaint_port)
		env['IOPAINT_URL'] = self.iopaint_url
		env['IOPAINT_DEVICE'] = self.iopaint_device

		env['FACECOPYER_CACHE_CHECK_INTERVAL'] = str(self.cache_check_interval)
		env['FACECOPYER_CACHE_EXPIRE_SECONDS'] = str(self.cache_expire_seconds)
		env['FACECOPYER_DOWNLOAD_PROVIDERS'] = ','.join(self.download_providers)

		if self.temp_dir:
			env['GRADIO_TEMP_DIR'] = os.path.join(self.temp_dir, 'gradio')

		return env

	def environment_lines(self):
		"""给用户看的生效设置摘要。"""
		return [
			('项目根目录', self.root),
			('配置来源', self.config_path + ('' if self.config_found else ' (未找到, 正在使用内置默认值)')),
			('界面端口', str(self.ui_port)),
			('去遮挡端口', str(self.iopaint_port)),
			('去遮挡设备', self.iopaint_device),
			('NSFW 检测', '关闭' if self.disable_nsfw else '开启'),
			('自动打开浏览器', '是' if self.open_browser else '否'),
			('主环境', self.venv_dir),
			('去遮挡环境', self.iopaint_venv_dir),
			('临时目录', self.temp_dir),
			('输出目录', self.output_dir),
			('缓存策略', '每 {} 秒检查, 超过 {} 秒删除'.format(self.cache_check_interval, self.cache_expire_seconds)),
			('下载源顺序', ', '.join(self.download_providers)),
		]


CONFIG_TEMPLATE = """\
; FaceCopyer 1.0.0 本地配置
;
; 这个文件描述的是「这台机器怎么部署」, 不属于代码本身, 已经加入 .gitignore。
; 改完保存, 下次启动生效。任何一项都可以删掉或留空, 程序会退回内置默认值。

[general]

; 项目根目录。留空 = 本文件所在目录。只有把配置放到项目外面时才需要填。
root = {root}

; 界面端口。启动时如果被占用, 会先结束占用它的进程。
ui_port = {ui_port}

; 启动后自动打开浏览器。部署在没有桌面的机器上时改成 no。
open_browser = {open_browser}

; 关闭 NSFW 内容检测。上游的检测模型对正常素材误拦较多, 所以默认关闭。
; 改成 no 会恢复检测, 可能拦下正常图片。
disable_nsfw = {disable_nsfw}

; 界面缓存的清理策略: 每 N 秒检查一次, 创建超过 M 秒的上传副本与预览拷贝会被删除。
; 批量处理很占缓存(实测 7 个成片堆到 3.5 GB), 磁盘紧张时把 M 调小, 例如 1800。
cache_check_interval = {cache_check_interval}
cache_expire_seconds = {cache_expire_seconds}

; 模型下载源优先级, 逗号分隔, 可选 huggingface / github。
; 国内直连 github 极慢(实测 7 KB/s, 相差近 40 倍), 所以 huggingface 排前面。
download_providers = {download_providers}

[paths]

; 下面的路径可以写相对路径(相对 root)或绝对路径。

; 主 Python 环境, 运行 FaceCopyer 本体与界面。
venv_dir = {venv_dir}

; 去遮挡环境, 运行 IOPaint。留空表示不启用去遮挡功能。
iopaint_venv_dir = {iopaint_venv_dir}

; 临时文件目录。批量处理会在这里堆副本, 建议放数据盘而不是系统盘。
temp_dir = {temp_dir}

; 输出目录。成片会写到 <output_dir>/picture 与 <output_dir>/video。
output_dir = {output_dir}

; 去遮挡模型目录, 首次使用去遮挡时会自动下载 big-lama.pt 到这里。
iopaint_models_dir = {iopaint_models_dir}

; 批量处理面板的默认源图/目标文件夹, 留空即可, 界面上也能选。
batch_source_dir = {batch_source_dir}
batch_target_dir = {batch_target_dir}

[iopaint]

; 去遮挡服务端口, 仅供程序内部调用, 不需要对外开放。
port = {iopaint_port}

; auto / cuda / cpu。auto = 有 CUDA 就用 CUDA, 启动失败会自动回退 CPU。
device = {iopaint_device}

; 去遮挡服务日志文件。
log = {iopaint_log}
"""


def render_config_template(values = None):
	"""生成带注释的 facecopyer.ini 内容。"""
	merged = {}
	for key, (section, option, fallback) in SPEC.items():
		merged[key] = fallback
	if values:
		for key, value in values.items():
			if key in merged and value is not None:
				merged[key] = str(value)
	return CONFIG_TEMPLATE.format(**{ key: merged[key] for key in SPEC })


def write_config(path, values = None):
	"""写入配置文件, 已存在时先备份为 .bak。"""
	path = os.path.abspath(path)
	if os.path.isfile(path):
		backup = path + '.bak'
		try:
			with open(path, 'rb') as source, open(backup, 'wb') as target:
				target.write(source.read())
		except OSError:
			pass
	with open(path, 'w', encoding = 'utf-8') as handle:
		handle.write(render_config_template(values))
	return path


def load(config_path = None):
	values, path, found = read_raw(config_path)
	return Settings(values, path, found)


SETTINGS = load()


def get():
	"""取全局配置。"""
	return SETTINGS

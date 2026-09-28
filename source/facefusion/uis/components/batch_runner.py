import os
from configparser import ConfigParser
from time import time
from typing import Dict, Generator, List, Optional, Set, Tuple

import gradio
from tqdm import tqdm

from facefusion import process_manager, run_stats, state_manager, translator, webp_helper
from facefusion.args import collect_step_args
from facefusion.core import process_step
from facefusion.filesystem import create_directory, is_directory, is_image, is_video
from facefusion.iopaint_remove import get_occlusion_mode, is_iopaint_available, preprocess_target_for_occlusion, remove_occlusion
from facefusion.jobs import job_helper, job_manager, job_runner, job_store
from facefusion.uis.components import output
from facefusion.uis.types import File
from facefusion.webp_helper import is_animated_webp

IMAGE_EXTENSIONS : Set[str] = { '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp' }
VIDEO_EXTENSIONS : Set[str] = { '.gif', '.mp4', '.mov', '.mkv', '.avi', '.webm' }

# 批量目标的类型筛选。'video' 同时涵盖动图 WebP —— 它需要先转码成 mp4 才能按视频处理。
TARGET_TYPE_ALL = 'all'
TARGET_TYPE_IMAGE = 'image'
TARGET_TYPE_VIDEO = 'video'
TARGET_TYPES : List[str] = [ TARGET_TYPE_ALL, TARGET_TYPE_IMAGE, TARGET_TYPE_VIDEO ]

BATCH_SOURCE_FILE : Optional[gradio.File] = None
BATCH_TARGET_FILE : Optional[gradio.File] = None
BATCH_SOURCE_DIR_TEXTBOX : Optional[gradio.Textbox] = None
BATCH_TARGET_DIR_TEXTBOX : Optional[gradio.Textbox] = None
BATCH_SOURCE_DIR_BUTTON : Optional[gradio.Button] = None
BATCH_TARGET_DIR_BUTTON : Optional[gradio.Button] = None
BATCH_SOURCE_CHOOSE_BUTTON : Optional[gradio.Button] = None
BATCH_TARGET_CHOOSE_BUTTON : Optional[gradio.Button] = None
BATCH_SOURCE_GALLERY : Optional[gradio.Gallery] = None
BATCH_TARGET_GALLERY : Optional[gradio.Gallery] = None
BATCH_OCCLUSION_DROPDOWN : Optional[gradio.Dropdown] = None
BATCH_OCCLUSION_NOTE : Optional[gradio.Markdown] = None
BATCH_TARGET_TYPE_RADIO : Optional[gradio.Radio] = None
BATCH_SKIP_EXISTING_CHECKBOX : Optional[gradio.Checkbox] = None
BATCH_START_BUTTON : Optional[gradio.Button] = None
BATCH_CLEAR_BUTTON : Optional[gradio.Button] = None
BATCH_LIVE_PROGRESS : Optional[gradio.Textbox] = None
BATCH_PROGRESS : Optional[gradio.Textbox] = None
BATCH_OUTPUT_GALLERY : Optional[gradio.Gallery] = None

BATCH_SOURCE_PATHS : List[str] = []
BATCH_TARGET_PATHS : List[str] = []
BATCH_OCCLUSION_MODE : str = 'remove'

# 批量运行时的实时状态。一个目标要跑好几分钟, 而生成器在目标处理期间是被阻塞的,
# 没法往外送进度, 所以进度框做成定时轮询(见 BATCH_LIVE_PROGRESS 的 every 参数)。
BATCH_LIVE_STATE : Dict[str, object] =\
{
	'active': False,
	'index': 0,
	'total': 0,
	'target_name': '',
	'started_at': 0.0,
	'durations': []
}

# 从 tqdm 抓到的当前进度条。terminal.py 已经劫持过一次 tqdm.update,
# 这里在点击开始时再挂一层, 顺序上正好接在它后面, 两边的功能都能保留。
BATCH_TQDM_STATE : Dict[str, object] =\
{
	'desc': '',
	'frame': 0,
	'frames': 0
}


def render() -> None:
	global BATCH_SOURCE_FILE
	global BATCH_TARGET_FILE
	global BATCH_SOURCE_DIR_TEXTBOX
	global BATCH_TARGET_DIR_TEXTBOX
	global BATCH_SOURCE_DIR_BUTTON
	global BATCH_TARGET_DIR_BUTTON
	global BATCH_SOURCE_CHOOSE_BUTTON
	global BATCH_TARGET_CHOOSE_BUTTON
	global BATCH_SOURCE_GALLERY
	global BATCH_TARGET_GALLERY
	global BATCH_OCCLUSION_DROPDOWN
	global BATCH_OCCLUSION_NOTE
	global BATCH_TARGET_TYPE_RADIO
	global BATCH_SKIP_EXISTING_CHECKBOX
	global BATCH_START_BUTTON
	global BATCH_CLEAR_BUTTON
	global BATCH_LIVE_PROGRESS
	global BATCH_PROGRESS
	global BATCH_OUTPUT_GALLERY

	with gradio.Accordion(translator.get('uis.batch_noocclusion_title'), open = True):
		gradio.Markdown(translator.get('uis.batch_noocclusion_note'))
		with gradio.Row():
			BATCH_SOURCE_FILE = gradio.File(
				label = translator.get('uis.batch_source_file'),
				file_count = 'multiple',
				file_types = [ '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp' ]
			)
			BATCH_TARGET_FILE = gradio.File(
				label = translator.get('uis.batch_target_file'),
				file_count = 'multiple',
				file_types = [ '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp', '.gif', '.mp4', '.mov', '.mkv', '.avi', '.webm' ]
			)
		with gradio.Row():
			with gradio.Column():
				BATCH_SOURCE_DIR_TEXTBOX = gradio.Textbox(
					label = translator.get('uis.batch_source_dir_textbox'),
					value = load_config_path('batch_source_dir') or '',
					placeholder = r'D:\facefusion\swap_task\source',
					max_lines = 1,
					interactive = True
				)
				BATCH_SOURCE_DIR_BUTTON = gradio.Button(
					value = translator.get('uis.batch_load_source_button'),
					size = 'sm'
				)
				BATCH_SOURCE_CHOOSE_BUTTON = gradio.Button(
					value = translator.get('uis.batch_choose_source_button'),
					size = 'sm'
				)
			with gradio.Column():
				BATCH_TARGET_DIR_TEXTBOX = gradio.Textbox(
					label = translator.get('uis.batch_target_dir_textbox'),
					value = load_config_path('batch_target_dir') or '',
					placeholder = r'D:\facefusion\swap_task\target',
					max_lines = 1,
					interactive = True
				)
				BATCH_TARGET_DIR_BUTTON = gradio.Button(
					value = translator.get('uis.batch_load_target_button'),
					size = 'sm'
				)
				BATCH_TARGET_CHOOSE_BUTTON = gradio.Button(
					value = translator.get('uis.batch_choose_target_button'),
					size = 'sm'
				)
		with gradio.Row():
			BATCH_SOURCE_GALLERY = gradio.Gallery(
				label = translator.get('uis.batch_source_gallery'),
				columns = 3,
				height = 220,
				object_fit = 'contain',
				show_label = True
			)
			BATCH_TARGET_GALLERY = gradio.Gallery(
				label = translator.get('uis.batch_target_gallery'),
				columns = 3,
				height = 220,
				object_fit = 'contain',
				show_label = True
			)
		with gradio.Row():
			BATCH_TARGET_TYPE_RADIO = gradio.Radio(
				label = translator.get('uis.batch_target_type'),
				choices = build_target_type_choices(),
				value = TARGET_TYPE_ALL,
				info = translator.get('uis.batch_target_type_info')
			)
		with gradio.Row():
			BATCH_SKIP_EXISTING_CHECKBOX = gradio.Checkbox(
				label = translator.get('uis.batch_skip_existing'),
				value = False,
				info = translator.get('uis.batch_skip_existing_info')
			)
		with gradio.Row():
			BATCH_START_BUTTON = gradio.Button(
				value = translator.get('uis.batch_start_button'),
				variant = 'primary',
				size = 'sm'
			)
			BATCH_CLEAR_BUTTON = gradio.Button(
				value = translator.get('uis.batch_clear_button'),
				size = 'sm'
			)
		BATCH_LIVE_PROGRESS = gradio.Textbox(
			label = translator.get('uis.batch_live_progress'),
			value = read_live_progress,
			interactive = False,
			lines = 3,
			max_lines = 3,
			every = 1.0
		)
		BATCH_PROGRESS = gradio.Textbox(
			label = translator.get('uis.batch_progress'),
			interactive = False
		)
		BATCH_OUTPUT_GALLERY = gradio.Gallery(
			label = translator.get('uis.batch_output_gallery'),
			columns = 3,
			height = 300,
			object_fit = 'contain',
			show_label = True
		)


def listen() -> None:
	BATCH_SOURCE_FILE.change(update_source, inputs = BATCH_SOURCE_FILE, outputs = BATCH_SOURCE_GALLERY)
	BATCH_TARGET_FILE.change(update_target, inputs = BATCH_TARGET_FILE, outputs = BATCH_TARGET_GALLERY)
	BATCH_SOURCE_DIR_BUTTON.click(load_source_directory, inputs = [ BATCH_SOURCE_DIR_TEXTBOX ], outputs = [ BATCH_SOURCE_GALLERY, BATCH_PROGRESS ])
	BATCH_TARGET_DIR_BUTTON.click(load_target_directory, inputs = [ BATCH_TARGET_DIR_TEXTBOX ], outputs = [ BATCH_TARGET_GALLERY, BATCH_PROGRESS ])
	BATCH_SOURCE_CHOOSE_BUTTON.click(choose_and_load_source, outputs = [ BATCH_SOURCE_DIR_TEXTBOX, BATCH_SOURCE_GALLERY, BATCH_PROGRESS ])
	BATCH_TARGET_CHOOSE_BUTTON.click(choose_and_load_target, outputs = [ BATCH_TARGET_DIR_TEXTBOX, BATCH_TARGET_GALLERY, BATCH_PROGRESS ])
	BATCH_TARGET_TYPE_RADIO.change(update_target_type, inputs = [ BATCH_TARGET_TYPE_RADIO ], outputs = [ BATCH_TARGET_GALLERY, BATCH_PROGRESS ])
	BATCH_START_BUTTON.click(run_batch, inputs = [ BATCH_TARGET_TYPE_RADIO, BATCH_SKIP_EXISTING_CHECKBOX ], outputs = [ BATCH_PROGRESS, BATCH_OUTPUT_GALLERY ])
	BATCH_CLEAR_BUTTON.click(clear_batch, outputs = [ BATCH_SOURCE_FILE, BATCH_TARGET_FILE, BATCH_SOURCE_DIR_TEXTBOX, BATCH_TARGET_DIR_TEXTBOX, BATCH_SOURCE_GALLERY, BATCH_TARGET_GALLERY, BATCH_PROGRESS, BATCH_OUTPUT_GALLERY, BATCH_TARGET_TYPE_RADIO, BATCH_SKIP_EXISTING_CHECKBOX ])


def update_source(files : List[File]) -> gradio.Gallery:
	global BATCH_SOURCE_PATHS
	if files:
		BATCH_SOURCE_PATHS = [ file.name for file in files ]
	else:
		BATCH_SOURCE_PATHS = []
	return gradio.Gallery(value = list(BATCH_SOURCE_PATHS))


def update_target(files : List[File]) -> gradio.Gallery:
	global BATCH_TARGET_PATHS
	if files:
		BATCH_TARGET_PATHS = [ file.name for file in files ]
	else:
		BATCH_TARGET_PATHS = []
	return gradio.Gallery(value = list(BATCH_TARGET_PATHS))


def load_source_directory(directory : str) -> Tuple[gradio.Gallery, gradio.Textbox]:
	global BATCH_SOURCE_PATHS
	if directory:
		if os.path.isdir(directory):
			save_config_path('batch_source_dir', directory)
		BATCH_SOURCE_PATHS = scan_directory(directory, IMAGE_EXTENSIONS)
	if BATCH_SOURCE_PATHS:
		return gradio.Gallery(value = list(BATCH_SOURCE_PATHS)), gradio.Textbox(value = translator.get('uis.batch_loaded').format(len(BATCH_SOURCE_PATHS)))
	return gradio.Gallery(value = None), gradio.Textbox(value = translator.get('uis.batch_dir_invalid'))


def load_target_directory(directory : str) -> Tuple[gradio.Gallery, gradio.Textbox]:
	global BATCH_TARGET_PATHS
	if directory:
		if os.path.isdir(directory):
			save_config_path('batch_target_dir', directory)
		BATCH_TARGET_PATHS = scan_directory(directory, IMAGE_EXTENSIONS | VIDEO_EXTENSIONS)
	if BATCH_TARGET_PATHS:
		return gradio.Gallery(value = list(BATCH_TARGET_PATHS)), gradio.Textbox(value = translator.get('uis.batch_loaded').format(len(BATCH_TARGET_PATHS)))
	return gradio.Gallery(value = None), gradio.Textbox(value = translator.get('uis.batch_dir_invalid'))


def update_occlusion_mode(mode : str) -> gradio.Markdown:
	global BATCH_OCCLUSION_MODE
	if mode:
		BATCH_OCCLUSION_MODE = mode
		sync_occlusion_state(mode)
	return gradio.Markdown(get_occlusion_note(mode))


def sync_occlusion_state(mode : str) -> None:
	state_manager.set_item('occlusion_mode', mode)
	if mode == 'remove':
		state_manager.set_item('face_mask_types', [ 'box' ])
		state_manager.set_item('face_mask_areas', [ 'upper-face', 'lower-face', 'mouth' ])
		state_manager.set_item('face_mask_padding', (30, 30, 30, 30))
	elif mode == 'preserve':
		state_manager.set_item('face_mask_types', [ 'area' ])
		state_manager.set_item('face_mask_areas', [ 'lower-face' ])


def get_occlusion_note(mode : str) -> str:
	return translator.get({ 'auto' : 'uis.batch_occlusion_note', 'remove' : 'uis.batch_occlusion_note_remove', 'preserve' : 'uis.batch_occlusion_note_preserve' }.get(mode, 'uis.batch_occlusion_note'))


def apply_occlusion_mode(step_args : dict) -> None:
	if get_occlusion_mode() == 'remove':
		step_args['face_mask_types'] = [ 'box' ]
		step_args['face_mask_areas'] = [ 'upper-face', 'lower-face', 'mouth' ]
		step_args['face_mask_padding'] = (30, 30, 30, 30)
	elif get_occlusion_mode() == 'preserve':
		step_args['face_mask_types'] = [ 'area' ]
		step_args['face_mask_areas'] = [ 'lower-face' ]


def choose_and_load_source() -> Tuple[gradio.Textbox, gradio.Gallery, gradio.Textbox]:
	global BATCH_SOURCE_PATHS
	memory_path = load_config_path('batch_source_dir')
	selected_directory = ask_directory(memory_path)
	if selected_directory:
		save_config_path('batch_source_dir', selected_directory)
		BATCH_SOURCE_PATHS = scan_directory(selected_directory, IMAGE_EXTENSIONS)
		if BATCH_SOURCE_PATHS:
			return gradio.Textbox(value = selected_directory), gradio.Gallery(value = list(BATCH_SOURCE_PATHS)), gradio.Textbox(value = translator.get('uis.batch_loaded').format(len(BATCH_SOURCE_PATHS)))
		return gradio.Textbox(value = selected_directory), gradio.Gallery(value = None), gradio.Textbox(value = translator.get('uis.batch_dir_invalid'))
	return gradio.update(), gradio.update(), gradio.update()


def choose_and_load_target() -> Tuple[gradio.Textbox, gradio.Gallery, gradio.Textbox]:
	global BATCH_TARGET_PATHS
	memory_path = load_config_path('batch_target_dir')
	selected_directory = ask_directory(memory_path)
	if selected_directory:
		save_config_path('batch_target_dir', selected_directory)
		BATCH_TARGET_PATHS = scan_directory(selected_directory, IMAGE_EXTENSIONS | VIDEO_EXTENSIONS)
		if BATCH_TARGET_PATHS:
			return gradio.Textbox(value = selected_directory), gradio.Gallery(value = list(BATCH_TARGET_PATHS)), gradio.Textbox(value = translator.get('uis.batch_loaded').format(len(BATCH_TARGET_PATHS)))
		return gradio.Textbox(value = selected_directory), gradio.Gallery(value = None), gradio.Textbox(value = translator.get('uis.batch_dir_invalid'))
	return gradio.update(), gradio.update(), gradio.update()


def ask_directory(initial_directory : Optional[str]) -> Optional[str]:
	if not initial_directory or not os.path.isdir(initial_directory):
		initial_directory = None
	try:
		import tkinter
		from tkinter import filedialog
		root = tkinter.Tk()
		root.withdraw()
		root.attributes('-topmost', True)
		selected_directory = filedialog.askdirectory(initialdir = initial_directory, title = translator.get('uis.choose_directory_title'))
		root.destroy()
		if selected_directory:
			return selected_directory
	except Exception:
		pass
	return None


def scan_directory(directory : str, extensions : Set[str]) -> List[str]:
	paths : List[str] = []
	if not os.path.isdir(directory):
		return paths
	for file_name in sorted(os.listdir(directory)):
		file_path = os.path.join(directory, file_name)
		if os.path.isfile(file_path) and os.path.splitext(file_name)[1].lower() in extensions:
			paths.append(file_path)
	return paths


def classify_target(file_path : str) -> str:
	# 动图 WebP 归到视频: 它会动, 而且处理前会被转码成 mp4
	if is_video(file_path) or is_animated_webp(file_path):
		return TARGET_TYPE_VIDEO
	if is_image(file_path):
		return TARGET_TYPE_IMAGE
	return ''


def filter_target_paths(target_paths : List[str], target_type : str) -> List[str]:
	if target_type not in ( TARGET_TYPE_IMAGE, TARGET_TYPE_VIDEO ):
		return list(target_paths)
	return [ path for path in target_paths if classify_target(path) == target_type ]


def get_target_type_label(target_type : str) -> str:
	label = translator.get('uis.batch_target_type_' + target_type)
	return label if label else target_type


def build_target_type_choices() -> List[Tuple[str, str]]:
	return [ (get_target_type_label(target_type), target_type) for target_type in TARGET_TYPES ]


def update_target_type(target_type : str) -> Tuple[gradio.Gallery, gradio.Textbox]:
	# 切换类型时同步目标预览, 让用户直接看到这一轮会处理哪些文件
	target_paths = [ path for path in BATCH_TARGET_PATHS if os.path.isfile(path) ]
	filtered_paths = filter_target_paths(target_paths, target_type or TARGET_TYPE_ALL)
	if not target_paths:
		return gradio.Gallery(value = None), gradio.Textbox(value = '')
	status = translator.get('uis.batch_target_type_filtered').format(target_type = get_target_type_label(target_type or TARGET_TYPE_ALL), count = len(filtered_paths), total = len(target_paths))
	return gradio.Gallery(value = list(filtered_paths)), gradio.Textbox(value = status)


def install_progress_hook() -> None:
	# 在点击「开始批量」时挂载: terminal.py 在启动时就劫持过一次 tqdm.update,
	# 这时再挂一层正好接在它后面, 终端面板的进度条与本面板的实时进度都能保留。
	if getattr(tqdm.update, '_batch_progress_hooked', False):
		return
	previous_update = tqdm.update

	def hooked_update(self : tqdm, n : int = 1) -> None:
		previous_update(self, n)

		if self.desc and self.total:
			BATCH_TQDM_STATE['desc'] = str(self.desc)
			BATCH_TQDM_STATE['frame'] = int(self.n)
			BATCH_TQDM_STATE['frames'] = int(self.total)

	hooked_update._batch_progress_hooked = True #type:ignore[attr-defined]
	tqdm.update = hooked_update #type:ignore[method-assign]


def reset_progress_hook() -> None:
	BATCH_TQDM_STATE['desc'] = ''
	BATCH_TQDM_STATE['frame'] = 0
	BATCH_TQDM_STATE['frames'] = 0


def format_duration(seconds : float) -> str:
	seconds = max(0, int(seconds))
	return '{:d}:{:02d}:{:02d}'.format(seconds // 3600, seconds % 3600 // 60, seconds % 60)


def read_live_progress() -> str:
	"""定时轮询的实时进度。

	一个目标要跑好几分钟, 而生成器在目标处理期间是阻塞的, 没法往外送进度,
	所以这个读数由 gradio 每秒调用一次, 直接看内存里的状态。
	"""
	if not BATCH_LIVE_STATE.get('active'):
		return translator.get('uis.batch_live_idle') or 'idle'

	index = int(BATCH_LIVE_STATE.get('index') or 0)
	total = int(BATCH_LIVE_STATE.get('total') or 0)
	started_at = float(BATCH_LIVE_STATE.get('started_at') or 0.0)
	durations = list(BATCH_LIVE_STATE.get('durations') or [])
	elapsed = time() - started_at if started_at else 0.0
	average = sum(durations) / len(durations) if durations else 0.0
	remaining = average * (total - index) + max(0.0, average - elapsed) if average else 0.0

	frames = int(BATCH_TQDM_STATE.get('frames') or 0)
	frame = int(BATCH_TQDM_STATE.get('frame') or 0)
	percent = int(frame / frames * 100) if frames else 0

	template = translator.get('uis.batch_live') or '{index}/{total} {name} {percent}% {frame}/{frames} {elapsed} {finished} {average} {remaining}'
	return template.format(
		index = index,
		total = total,
		name = BATCH_LIVE_STATE.get('target_name') or '',
		percent = percent,
		frame = frame,
		frames = frames,
		elapsed = format_duration(elapsed),
		finished = len(durations),
		average = format_duration(average) if average else '--:--:--',
		remaining = format_duration(remaining) if remaining else '--:--:--'
	)


def build_target_result(target_path : str, elapsed : float, skipped : bool = False) -> str:
	"""把一个目标的结果整理成一行。

	换脸是否真的发生, 从输出文件上是看不出来的 —— 源或目标里检测不到人脸时
	处理器会原样返回, 日志也只写「处理成功」。所以这里读 run_stats 的帧计数。
	"""
	if skipped:
		detail = translator.get('uis.batch_skipped')
	else:
		stats = run_stats.get_stats()
		swapped_frames = stats.get(run_stats.COUNTER_SWAPPED_FRAMES, 0)

		if swapped_frames:
			detail = translator.get('uis.batch_swapped_frames').format(frames = swapped_frames)
		else:
			detail = translator.get('uis.batch_no_face').format(frames = stats.get(run_stats.COUNTER_MISSED_FRAMES, 0))

	return translator.get('uis.batch_line').format(name = os.path.basename(target_path), detail = detail, elapsed = format_duration(elapsed))


def run_batch(target_type : str, skip_existing : bool = False) -> Generator[Tuple[gradio.Textbox, gradio.Gallery], None, None]:
	source_paths = [ path for path in BATCH_SOURCE_PATHS if os.path.isfile(path) ]
	all_target_paths = [ path for path in BATCH_TARGET_PATHS if os.path.isfile(path) ]
	target_paths = filter_target_paths(all_target_paths, target_type or TARGET_TYPE_ALL)

	if not target_paths:
		if all_target_paths:
			yield gradio.Textbox(value = translator.get('uis.batch_no_matching_target').format(target_type = get_target_type_label(target_type or TARGET_TYPE_ALL), total = len(all_target_paths))), gradio.Gallery(value = None)
			return
		yield gradio.Textbox(value = translator.get('uis.batch_no_target')), gradio.Gallery(value = None)
		return
	if not source_paths:
		yield gradio.Textbox(value = translator.get('uis.batch_no_source')), gradio.Gallery(value = None)
		return

	install_progress_hook()
	results : List[str] = []
	progress_lines : List[str] = []
	missed_names : List[str] = []
	output_directories : List[str] = []
	swapped_count = 0
	skipped_count = 0
	total = len(target_paths)

	BATCH_LIVE_STATE['active'] = True
	BATCH_LIVE_STATE['total'] = total
	BATCH_LIVE_STATE['durations'] = []

	try:
		for index, target_path in enumerate(target_paths, start = 1):
			if process_manager.is_stopping():
				break
			output_directory = output.resolve_output_directory(target_path) or output.DEFAULT_OUTPUT_IMAGE_DIRECTORY
			create_directory(output_directory)
			if output_directory not in output_directories:
				output_directories.append(output_directory)
			step_args = collect_step_args()
			step_args['source_paths'] = source_paths
			# 动图 WebP 必须先转码成 mp4, 否则会被当成静图只换第一帧 —— 单个处理时走的就是这个函数
			step_args['target_path'] = webp_helper.resolve_target_path(target_path) or target_path
			step_args['output_path'] = build_output_path(output_directory, target_path, index)

			reset_progress_hook()
			run_stats.reset()
			BATCH_LIVE_STATE['index'] = index
			BATCH_LIVE_STATE['target_name'] = os.path.basename(target_path)
			BATCH_LIVE_STATE['started_at'] = time()

			# 中断后重跑时, 已存在的成片直接跳过, 不必重新算一遍
			if skip_existing and os.path.isfile(step_args['output_path']):
				skipped_count += 1
				results.append(step_args['output_path'])
				progress_lines.insert(0, '[{}/{}] {}'.format(index, total, build_target_result(target_path, 0.0, skipped = True)))
				yield gradio.Textbox(value = '\n'.join(progress_lines)), gradio.Gallery(value = list(results))
				continue

			if job_manager.init_jobs(state_manager.get_item('jobs_path')):
				copy_step_keys(step_args)
				job_id = job_helper.suggest_job_id('batch')
				if job_manager.create_job(job_id) and job_manager.add_step(job_id, step_args) and job_manager.submit_job(job_id):
					job_runner.run_job(job_id, process_step)

			elapsed = time() - float(BATCH_LIVE_STATE['started_at'])
			durations = BATCH_LIVE_STATE.get('durations')
			if isinstance(durations, list):
				durations.append(elapsed)
			if os.path.isfile(step_args['output_path']):
				results.append(step_args['output_path'])
			if run_stats.has_swapped():
				swapped_count += 1
			else:
				missed_names.append(os.path.basename(target_path))

			progress_lines.insert(0, '[{}/{}] {}'.format(index, total, build_target_result(target_path, elapsed)))
			yield gradio.Textbox(value = '\n'.join(progress_lines)), gradio.Gallery(value = list(results))
	finally:
		BATCH_LIVE_STATE['active'] = False

	summary_lines : List[str] =\
	[
		'{} | {}'.format(translator.get('uis.batch_done'), translator.get('uis.batch_output_hint').format(output_path = ' , '.join(output_directories))),
		translator.get('uis.batch_summary').format(total = total, swapped = swapped_count, missed = len(missed_names), skipped = skipped_count)
	]
	if missed_names:
		summary_lines.append(translator.get('uis.batch_missed_names').format(names = ' , '.join(missed_names[:10])))
	progress_lines.insert(0, '\n'.join(summary_lines))
	yield gradio.Textbox(value = '\n'.join(progress_lines)), gradio.Gallery(value = list(results))


def load_config_path(key : str) -> str:
	config_path = state_manager.get_item('config_path')
	if not config_path:
		return ''
	config_parser = ConfigParser()
	config_parser.read(config_path, encoding = 'utf-8')
	if config_parser.has_section('paths') and config_parser.has_option('paths', key):
		return config_parser.get('paths', key, fallback = '')
	return ''


def save_config_path(key : str, value : str) -> None:
	config_path = state_manager.get_item('config_path')
	if not config_path or not value:
		return
	config_parser = ConfigParser()
	config_parser.read(config_path, encoding = 'utf-8')
	if not config_parser.has_section('paths'):
		config_parser.add_section('paths')
	config_parser.set('paths', key, value)
	with open(config_path, 'w', encoding = 'utf-8') as config_file:
		config_parser.write(config_file)


def build_output_path(output_directory : str, target_path : str, index : int) -> str:
	original_extension = os.path.splitext(target_path)[1].lower()
	if original_extension == '.webp' and is_animated_webp(target_path):
		output_extension = '.mp4'
	else:
		output_extension = original_extension or '.png'
	base_name = os.path.splitext(os.path.basename(target_path))[0]
	return os.path.join(output_directory, '{}_swapped_{}{}'.format(base_name, index, output_extension))


def copy_step_keys(step_args : dict) -> None:
	for key in job_store.get_job_keys():
		if key in step_args:
			state_manager.sync_item(key) #type:ignore[arg-type]


def clear_batch() -> Tuple[gradio.File, gradio.File, gradio.Textbox, gradio.Textbox, gradio.Gallery, gradio.Gallery, gradio.Textbox, gradio.Gallery, gradio.Radio, gradio.Checkbox]:
	global BATCH_SOURCE_PATHS
	global BATCH_TARGET_PATHS
	BATCH_SOURCE_PATHS = []
	BATCH_TARGET_PATHS = []
	BATCH_LIVE_STATE['active'] = False
	BATCH_LIVE_STATE['index'] = 0
	BATCH_LIVE_STATE['total'] = 0
	BATCH_LIVE_STATE['target_name'] = ''
	BATCH_LIVE_STATE['started_at'] = 0.0
	BATCH_LIVE_STATE['durations'] = []
	reset_progress_hook()
	return gradio.File(value = None), gradio.File(value = None), gradio.Textbox(value = ''), gradio.Textbox(value = ''), gradio.Gallery(value = None), gradio.Gallery(value = None), gradio.Textbox(value = ''), gradio.Gallery(value = None), gradio.Radio(value = TARGET_TYPE_ALL), gradio.Checkbox(value = False)
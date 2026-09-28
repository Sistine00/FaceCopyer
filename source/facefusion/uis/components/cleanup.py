"""垃圾文件清理。

程序本身只会清理临时帧目录, 而且是同一个目标下次处理时才清。失败的任务记录、
动态 WebP 转码缓存、去遮挡结果缓存以及 Gradio 的上传副本都不会被自动删除,
会一直占着磁盘。这里提供一个纯手动的清理入口, 让用户自己决定删什么。

删除时的两条保护:
1. 清理前先等当前任务结束, 避免删到正在读写的文件;
2. 当前会话正在引用的路径(源/目标/输出)一律跳过, 否则已选好的素材会失效。
"""
import os
import shutil
import tempfile
import time
from time import sleep
from typing import Dict, List, Optional, Set, Tuple

import gradio

from facefusion import process_manager, state_manager, translator
from facefusion.filesystem import get_file_size, is_directory
from facefusion.iopaint_remove import CACHE_DIRECTORY as OCCLUSION_CACHE_DIRECTORY
from facefusion.temp_helper import get_temp_directory_path
from facefusion.webp_helper import CACHE_DIRECTORY as WEBP_CACHE_DIRECTORY

CLEANUP_CHECKBOX_GROUP : Optional[gradio.CheckboxGroup] = None
CLEANUP_BUTTON : Optional[gradio.Button] = None
CLEANUP_RESULT : Optional[gradio.Markdown] = None

CLEANUP_ITEM_FAILED_JOBS = 'failed_jobs'
CLEANUP_ITEM_TEMP_FRAMES = 'temp_frames'
CLEANUP_ITEM_WEBP_CACHE = 'webp_cache'
CLEANUP_ITEM_OCCLUSION_CACHE = 'occlusion_cache'
CLEANUP_ITEM_UPLOAD_POOL = 'upload_pool'

# 顺序即界面上的顺序
CLEANUP_ITEMS : List[str] =\
[
	CLEANUP_ITEM_FAILED_JOBS,
	CLEANUP_ITEM_TEMP_FRAMES,
	CLEANUP_ITEM_WEBP_CACHE,
	CLEANUP_ITEM_OCCLUSION_CACHE,
	CLEANUP_ITEM_UPLOAD_POOL
]

# 上传副本默认不勾选: 它是浏览器当前会话里已选素材的来源, 误删会让重新开跑时报「请选择源」。
# 其余四项都是可再生的缓存或纯记录, 默认勾选, 一键即可清干净。
DEFAULT_CLEANUP_ITEMS : List[str] =\
[
	CLEANUP_ITEM_FAILED_JOBS,
	CLEANUP_ITEM_TEMP_FRAMES,
	CLEANUP_ITEM_WEBP_CACHE,
	CLEANUP_ITEM_OCCLUSION_CACHE
]

# Gradio 上传副本只清理这么久之前的。上传目标是按内容复制进临时目录的,
# 而当前的目标在状态里已经被换成转码后的 mp4, 单靠路径保护盖不住它。
UPLOAD_POOL_MINIMUM_AGE = 3600.0


def get_upload_pool_directory() -> str:
	return os.environ.get('GRADIO_TEMP_DIR') or os.path.join(tempfile.gettempdir(), 'gradio')


def get_failed_jobs_directory() -> str:
	jobs_path = state_manager.get_item('jobs_path')
	if jobs_path:
		return os.path.join(jobs_path, 'failed')
	return ''


def get_temp_frame_root() -> str:
	temp_path = state_manager.get_item('temp_path')
	if temp_path:
		return os.path.join(temp_path, 'facefusion')
	return ''


def normalize_path(file_path : str) -> str:
	return os.path.normcase(os.path.normpath(os.path.abspath(file_path)))


def collect_protected_paths() -> Set[str]:
	protected_paths : Set[str] = set()

	for item_key in [ 'source_paths', 'target_path', 'output_path' ]:
		item_value = state_manager.get_item(item_key)
		item_values = item_value if isinstance(item_value, list) else [ item_value ]

		for value in item_values:
			if isinstance(value, str) and value:
				protected_paths.add(normalize_path(value))
	return protected_paths


def measure_tree(directory_path : str) -> Tuple[int, int]:
	file_count = 0
	byte_count = 0

	for root_path, _directory_names, file_names in os.walk(directory_path):
		for file_name in file_names:
			file_path = os.path.join(root_path, file_name)
			byte_count += get_file_size(file_path)
			file_count += 1
	return file_count, byte_count


def remove_empty_directory(directory_path : str, root_path : str) -> None:
	# 自底向上清理时顺手删掉已经空掉的子目录, 根目录本身始终保留
	if normalize_path(directory_path) != normalize_path(root_path):
		try:
			os.rmdir(directory_path)
		except OSError:
			pass


def purge_tree(directory_path : str, minimum_age : float = 0.0, protected_paths : Optional[Set[str]] = None) -> Tuple[int, int]:
	"""自底向上清空目录内容, 返回 (删除的文件数, 释放的字节数)。

	minimum_age 只对文件生效: 修改时间晚于该秒数的文件会被跳过。
	protected_paths 里的路径一律跳过。
	"""
	if not directory_path or not is_directory(directory_path):
		return 0, 0

	protected_paths = protected_paths or set()
	now = time.time()
	file_count = 0
	byte_count = 0

	for root_path, _directory_names, file_names in os.walk(directory_path, topdown = False):
		for file_name in file_names:
			file_path = os.path.join(root_path, file_name)
			if normalize_path(file_path) in protected_paths:
				continue
			try:
				if minimum_age > 0 and now - os.path.getmtime(file_path) < minimum_age:
					continue
			except OSError:
				continue

			file_size = get_file_size(file_path)
			try:
				os.remove(file_path)
			except OSError:
				continue
			file_count += 1
			byte_count += file_size

		remove_empty_directory(root_path, directory_path)
	return file_count, byte_count


def cleanup_failed_jobs() -> Tuple[int, int]:
	return purge_tree(get_failed_jobs_directory())


def cleanup_temp_frames() -> Tuple[int, int]:
	"""清理临时帧残留。

	每个目标在 <系统临时目录>/facefusion/<目标名> 下有一个目录, 正常跑完会被删掉,
	中途失败或进程被强杀时会留下。当前目标的那个目录要留着, 只清其它目标的。
	"""
	root_path = get_temp_frame_root()
	if not root_path or not is_directory(root_path):
		return 0, 0

	protected_directory = ''
	target_path = state_manager.get_item('target_path')
	if target_path:
		protected_directory = normalize_path(get_temp_directory_path(target_path))

	file_count = 0
	byte_count = 0

	for entry_name in os.listdir(root_path):
		entry_path = os.path.join(root_path, entry_name)
		if not is_directory(entry_path):
			continue
		if normalize_path(entry_path) == protected_directory:
			continue

		entry_file_count, entry_byte_count = measure_tree(entry_path)
		shutil.rmtree(entry_path, ignore_errors = True)
		if not is_directory(entry_path):
			file_count += entry_file_count
			byte_count += entry_byte_count
	return file_count, byte_count


def cleanup_webp_cache() -> Tuple[int, int]:
	return purge_tree(WEBP_CACHE_DIRECTORY, protected_paths = collect_protected_paths())


def cleanup_occlusion_cache() -> Tuple[int, int]:
	return purge_tree(OCCLUSION_CACHE_DIRECTORY, protected_paths = collect_protected_paths())


def cleanup_upload_pool() -> Tuple[int, int]:
	return purge_tree(get_upload_pool_directory(), minimum_age = UPLOAD_POOL_MINIMUM_AGE, protected_paths = collect_protected_paths())


CLEANUP_HANDLERS : Dict[str, object] =\
{
	CLEANUP_ITEM_FAILED_JOBS: cleanup_failed_jobs,
	CLEANUP_ITEM_TEMP_FRAMES: cleanup_temp_frames,
	CLEANUP_ITEM_WEBP_CACHE: cleanup_webp_cache,
	CLEANUP_ITEM_OCCLUSION_CACHE: cleanup_occlusion_cache,
	CLEANUP_ITEM_UPLOAD_POOL: cleanup_upload_pool
}


def format_size(byte_count : int) -> str:
	if byte_count >= 1024 * 1024 * 1024:
		return '{:.2f} GB'.format(byte_count / (1024 ** 3))
	if byte_count >= 1024 * 1024:
		return '{:.1f} MB'.format(byte_count / (1024 ** 2))
	if byte_count >= 1024:
		return '{:.1f} KB'.format(byte_count / 1024)
	return '{} B'.format(byte_count)


def get_cleanup_label(cleanup_item : str) -> str:
	cleanup_label = translator.get('uis.cleanup_item_' + cleanup_item)
	if cleanup_label:
		return cleanup_label
	return cleanup_item


def build_cleanup_choices() -> List[Tuple[str, str]]:
	return [ (get_cleanup_label(cleanup_item), cleanup_item) for cleanup_item in CLEANUP_ITEMS ]


def render() -> None:
	global CLEANUP_CHECKBOX_GROUP
	global CLEANUP_BUTTON
	global CLEANUP_RESULT

	with gradio.Row():
		gradio.Markdown(translator.get('uis.cleanup_checkbox_group'))
	CLEANUP_CHECKBOX_GROUP = gradio.CheckboxGroup(
		show_label = False,
		choices = build_cleanup_choices(),
		value = DEFAULT_CLEANUP_ITEMS,
		info = translator.get('uis.cleanup_checkbox_group_info')
	)
	CLEANUP_BUTTON = gradio.Button(
		value = translator.get('uis.cleanup_button'),
		size = 'sm'
	)
	CLEANUP_RESULT = gradio.Markdown(value = '', visible = False)


def listen() -> None:
	CLEANUP_BUTTON.click(run_cleanup, inputs = CLEANUP_CHECKBOX_GROUP, outputs = CLEANUP_RESULT)


def run_cleanup(cleanup_items : Optional[List[str]]) -> gradio.Markdown:
	global CLEANUP_RESULT

	# 与「清除」按钮一致: 处理中不动文件, 先等当前任务结束
	while process_manager.is_processing():
		sleep(0.5)

	total_file_count = 0
	total_byte_count = 0
	detail_lines : List[str] = []

	for cleanup_item in CLEANUP_ITEMS:
		if cleanup_item not in (cleanup_items or []):
			continue

		file_count, byte_count = CLEANUP_HANDLERS[cleanup_item]() #type:ignore[operator]
		total_file_count += file_count
		total_byte_count += byte_count

		if file_count > 0:
			detail_lines.append('- ' + get_cleanup_label(cleanup_item) + translator.get('colon') + ' ' + translator.get('uis.cleanup_result_item').format(size = format_size(byte_count), file_count = file_count))

	title = '**' + translator.get('uis.cleanup_result_title') + '**'

	if total_file_count == 0:
		return gradio.Markdown(value = title + '\n\n' + translator.get('uis.cleanup_result_empty'), visible = True)

	summary = translator.get('uis.cleanup_result_summary').format(file_count = total_file_count, size = format_size(total_byte_count))
	return gradio.Markdown(value = '\n'.join([ title, summary, '' ] + detail_lines), visible = True)

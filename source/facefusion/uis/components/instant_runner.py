from time import sleep
from typing import List, Optional, Tuple

import gradio

from facefusion import logger, process_manager, state_manager, translator
from facefusion.args import collect_step_args
from facefusion.core import process_step
from facefusion.filesystem import is_directory, is_image, is_video
from facefusion.iopaint_remove import get_occlusion_mode, is_iopaint_available, preprocess_target_for_occlusion
from facefusion.jobs import job_helper, job_manager, job_runner, job_store
from facefusion.temp_helper import clear_temp_directory
from facefusion.types import Args, UiWorkflow
from facefusion.uis.components import output
from facefusion.uis.components.occlusion_editor import get_user_mask_path
from facefusion.uis.core import get_ui_component
from facefusion.uis.ui_helper import suggest_output_path

INSTANT_RUNNER_WRAPPER : Optional[gradio.Row] = None
INSTANT_RUNNER_START_BUTTON : Optional[gradio.Button] = None
INSTANT_RUNNER_STOP_BUTTON : Optional[gradio.Button] = None
INSTANT_RUNNER_CLEAR_BUTTON : Optional[gradio.Button] = None
INSTANT_RUNNER_NOTICE : Optional[gradio.Markdown] = None

# 失败提示里最多列几条原因, 避免把整段日志糊到界面上
NOTICE_REASON_LIMIT = 3


def render() -> None:
	global INSTANT_RUNNER_WRAPPER
	global INSTANT_RUNNER_START_BUTTON
	global INSTANT_RUNNER_STOP_BUTTON
	global INSTANT_RUNNER_CLEAR_BUTTON

	if job_manager.init_jobs(state_manager.get_item('jobs_path')):
		is_instant_runner = state_manager.get_item('ui_workflow') == 'instant_runner'

		with gradio.Row(visible = is_instant_runner) as INSTANT_RUNNER_WRAPPER:
			INSTANT_RUNNER_START_BUTTON = gradio.Button(
				value = translator.get('uis.start_button'),
				variant = 'primary',
				size = 'sm'
			)
			INSTANT_RUNNER_STOP_BUTTON = gradio.Button(
				value = translator.get('uis.stop_button'),
				variant = 'primary',
				size = 'sm',
				visible = False
			)
			INSTANT_RUNNER_CLEAR_BUTTON = gradio.Button(
				value = translator.get('uis.clear_button'),
				size = 'sm'
			)


def render_notice() -> None:
	global INSTANT_RUNNER_NOTICE

	# 失败提示单独渲染: 在布局里它被放在中间一列的「输出」下方, 而不是紧挨着开始按钮。
	# 因为开始按钮所在的列很窄, 提示塞进去会被压成竖排, 反而看不清。
	INSTANT_RUNNER_NOTICE = gradio.Markdown(value = '', visible = False)


def listen() -> None:
	output_image = get_ui_component('output_image')
	output_video = get_ui_component('output_video')
	ui_workflow_dropdown = get_ui_component('ui_workflow_dropdown')

	if output_image and output_video and INSTANT_RUNNER_NOTICE:
		INSTANT_RUNNER_START_BUTTON.click(start, outputs = [ INSTANT_RUNNER_START_BUTTON, INSTANT_RUNNER_STOP_BUTTON ])
		INSTANT_RUNNER_START_BUTTON.click(run, outputs = [ INSTANT_RUNNER_START_BUTTON, INSTANT_RUNNER_STOP_BUTTON, output_image, output_video, INSTANT_RUNNER_NOTICE ])
		INSTANT_RUNNER_STOP_BUTTON.click(stop, outputs = [ INSTANT_RUNNER_START_BUTTON, INSTANT_RUNNER_STOP_BUTTON, output_image, output_video, INSTANT_RUNNER_NOTICE ])
		INSTANT_RUNNER_CLEAR_BUTTON.click(clear, outputs = [ output_image, output_video, INSTANT_RUNNER_NOTICE ])
	if ui_workflow_dropdown and INSTANT_RUNNER_NOTICE:
		ui_workflow_dropdown.change(remote_update, inputs = ui_workflow_dropdown, outputs = [ INSTANT_RUNNER_WRAPPER, INSTANT_RUNNER_NOTICE ])


def remote_update(ui_workflow : UiWorkflow) -> Tuple[gradio.Row, gradio.Markdown]:
	is_instant_runner = ui_workflow == 'instant_runner'

	return gradio.Row(visible = is_instant_runner), gradio.Markdown(value = '', visible = False)


def start() -> Tuple[gradio.Button, gradio.Button]:
	while not process_manager.is_processing():
		sleep(0.5)
	return gradio.Button(visible = False), gradio.Button(visible = True)


def run() -> Tuple[gradio.Button, gradio.Button, gradio.Image, gradio.Video, gradio.Markdown]:
	output.apply_output_directory(state_manager.get_item('target_path'))
	step_args = collect_step_args()
	output_path = step_args.get('output_path')

	target_path = step_args.get('target_path')
	if target_path and is_image(target_path) and get_occlusion_mode() == 'remove':
		try:
			step_args['target_path'] = preprocess_target_for_occlusion(target_path, get_user_mask_path())
		except Exception:
			step_args['target_path'] = target_path

	if is_directory(step_args.get('output_path')):
		step_args['output_path'] = suggest_output_path(step_args.get('output_path'), state_manager.get_item('target_path'))
	failure_messages : List[str] = []
	if job_manager.init_jobs(state_manager.get_item('jobs_path')):
		# 处理期间抓取 error 级日志。处理器发现条件不满足时只写日志不弹提示,
		# 不抓出来的话用户点了开始看不到任何反馈, 只会以为程序坏了。
		with logger.capture_errors() as failure_messages:
			create_and_run_job(step_args)
		state_manager.set_item('output_path', output_path)
	if is_image(step_args.get('output_path')):
		return gradio.Button(visible = True), gradio.Button(visible = False), gradio.Image(value = step_args.get('output_path'), visible = True), gradio.Video(value = None, visible = False), make_notice(None)
	if is_video(step_args.get('output_path')):
		return gradio.Button(visible = True), gradio.Button(visible = False), gradio.Image(value = None, visible = False), gradio.Video(value = step_args.get('output_path'), visible = True), make_notice(None)
	return gradio.Button(visible = True), gradio.Button(visible = False), gradio.Image(value = None), gradio.Video(value = None), make_notice(failure_messages)


def create_and_run_job(step_args : Args) -> bool:
	job_id = job_helper.suggest_job_id('ui')

	for key in job_store.get_job_keys():
		state_manager.sync_item(key) #type:ignore[arg-type]

	return job_manager.create_job(job_id) and job_manager.add_step(job_id, step_args) and job_manager.submit_job(job_id) and job_runner.run_job(job_id, process_step)


def stop() -> Tuple[gradio.Button, gradio.Button, gradio.Image, gradio.Video, gradio.Markdown]:
	process_manager.stop()
	return gradio.Button(visible = True), gradio.Button(visible = False), gradio.Image(value = None), gradio.Video(value = None), gradio.Markdown(value = '', visible = False)


def clear() -> Tuple[gradio.Image, gradio.Video, gradio.Markdown]:
	while process_manager.is_processing():
		sleep(0.5)
	if state_manager.get_item('target_path'):
		clear_temp_directory(state_manager.get_item('target_path'))
	return gradio.Image(value = None), gradio.Video(value = None), gradio.Markdown(value = '', visible = False)


def make_notice(failure_messages : Optional[List[str]]) -> gradio.Markdown:
	# 传 None 表示这次是成功的, 提示保持隐藏; 传列表(可能为空)表示失败, 一律给出提示
	if failure_messages is None:
		return gradio.Markdown(value = '', visible = False)

	reasons : List[str] = []
	for failure_message in failure_messages:
		reason = strip_module_prefix(failure_message)
		if reason and reason not in reasons:
			reasons.append(reason)

	lines = [ '**' + translator.get('uis.instant_runner_failed') + '**' ]
	for reason in reasons[:NOTICE_REASON_LIMIT]:
		lines.append('- ' + reason)
	if not reasons:
		lines.append('- ' + translator.get('uis.instant_runner_failed_unknown'))
	lines.append('')
	lines.append(translator.get('uis.instant_runner_failed_hint'))
	return gradio.Markdown(value = '\n'.join(lines), visible = True)


def strip_module_prefix(failure_message : str) -> str:
	# 日志消息形如 "[FACEFUSION.CORE] 选择一个音频作为源！", 界面上只保留原因本身
	if failure_message.startswith('['):
		module_end = failure_message.find(']')
		if module_end > 0:
			return failure_message[module_end + 1:].strip()
	return failure_message.strip()

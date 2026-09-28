from typing import Optional, Tuple

import gradio

from facefusion import state_manager, translator, webp_helper
from facefusion.face_store import clear_faces
from facefusion.filesystem import is_image, is_video
from facefusion.uis.core import register_ui_component
from facefusion.uis.types import ComponentOptions, File
from facefusion.uis.components import occlusion_editor

TARGET_FILE : Optional[gradio.File] = None
TARGET_IMAGE : Optional[gradio.Image] = None
TARGET_VIDEO : Optional[gradio.Video] = None
TARGET_CLEAR_BUTTON : Optional[gradio.Button] = None


def render() -> None:
	global TARGET_FILE
	global TARGET_IMAGE
	global TARGET_VIDEO
	global TARGET_CLEAR_BUTTON

	target_path = webp_helper.resolve_target_path(state_manager.get_item('target_path'))
	if target_path and target_path != state_manager.get_item('target_path'):
		state_manager.set_item('target_path', target_path)
	is_target_image = is_image(state_manager.get_item('target_path'))
	is_target_video = is_video(state_manager.get_item('target_path'))
	TARGET_FILE = gradio.File(
		label = translator.get('uis.target_file'),
		value = state_manager.get_item('target_path') if is_target_image or is_target_video else None
	)
	target_image_options : ComponentOptions =\
	{
		'show_label': False,
		'visible': False
	}
	target_video_options : ComponentOptions =\
	{
		'show_label': False,
		'visible': False
	}
	if is_target_image:
		target_image_options['value'] = TARGET_FILE.value.get('path')
		target_image_options['visible'] = True
	if is_target_video:
		target_video_options['value'] = TARGET_FILE.value.get('path')
		target_video_options['visible'] = True
	TARGET_IMAGE = gradio.Image(**target_image_options)
	TARGET_VIDEO = gradio.Video(**target_video_options)
	TARGET_CLEAR_BUTTON = gradio.Button(
		value = translator.get('uis.target_clear_button'),
		size = 'sm',
		visible = is_target_image or is_target_video
	)
	register_ui_component('target_image', TARGET_IMAGE)
	register_ui_component('target_video', TARGET_VIDEO)
	occlusion_editor.render()


def listen() -> None:
	TARGET_FILE.change(update, inputs = TARGET_FILE, outputs = [ TARGET_IMAGE, TARGET_VIDEO, TARGET_CLEAR_BUTTON ])
	TARGET_CLEAR_BUTTON.click(
		clear_target,
		outputs = [ TARGET_FILE, TARGET_IMAGE, TARGET_VIDEO, TARGET_CLEAR_BUTTON, occlusion_editor.OCCLUSION_EDITOR ]
	)


def update(file : File) -> Tuple[gradio.Image, gradio.Video, gradio.Button]:
	clear_faces()
	target_path = webp_helper.resolve_target_path(file.name) if file else None

	if target_path and is_image(target_path):
		state_manager.set_item('target_path', target_path)
		return gradio.Image(value = target_path, visible = True), gradio.Video(value = None, visible = False), gradio.Button(visible = True)

	if target_path and is_video(target_path):
		state_manager.set_item('target_path', target_path)
		return gradio.Image(value = None, visible = False), gradio.Video(value = target_path, visible = True), gradio.Button(visible = True)

	state_manager.clear_item('target_path')
	return gradio.Image(value = None, visible = False), gradio.Video(value = None, visible = False), gradio.Button(visible = False)


def clear_target():
	clear_faces()
	state_manager.clear_item('target_path')
	occlusion_editor.reset_state()
	return (
		gradio.File(value = None),
		gradio.Image(value = None, visible = False),
		gradio.Video(value = None, visible = False),
		gradio.Button(visible = False),
		occlusion_editor.make_editor(None),
	)

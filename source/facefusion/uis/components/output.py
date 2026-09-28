import os
from configparser import ConfigParser
from typing import Optional

import gradio

from facefusion import state_manager, translator
from facefusion.filesystem import create_directory, is_directory, is_image, is_video, resolve_relative_path
from facefusion.uis.core import register_ui_component
from facefusion.webp_helper import is_animated_webp

# 默认输出根目录。按本文件位置推算, 也就是 <项目根>/output, 而不是写死某个盘符,
# 这样项目放在哪里都能用。界面里改过的路径会写进 source/facefusion.ini 的 paths 段并优先。
DEFAULT_OUTPUT_ROOT = resolve_relative_path('../../output')
DEFAULT_OUTPUT_IMAGE_DIRECTORY = os.path.join(DEFAULT_OUTPUT_ROOT, 'picture')
DEFAULT_OUTPUT_VIDEO_DIRECTORY = os.path.join(DEFAULT_OUTPUT_ROOT, 'video')

OUTPUT_IMAGE_PATH_TEXTBOX : Optional[gradio.Textbox] = None
OUTPUT_IMAGE_CHOOSE_BUTTON : Optional[gradio.Button] = None
OUTPUT_IMAGE_OPEN_BUTTON : Optional[gradio.Button] = None
OUTPUT_VIDEO_PATH_TEXTBOX : Optional[gradio.Textbox] = None
OUTPUT_VIDEO_CHOOSE_BUTTON : Optional[gradio.Button] = None
OUTPUT_VIDEO_OPEN_BUTTON : Optional[gradio.Button] = None
OUTPUT_IMAGE : Optional[gradio.Image] = None
OUTPUT_VIDEO : Optional[gradio.Video] = None

OUTPUT_IMAGE_DIRECTORY : Optional[str] = None
OUTPUT_VIDEO_DIRECTORY : Optional[str] = None


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


def ensure_directory(directory : Optional[str]) -> bool:
	if not directory:
		return False
	try:
		create_directory(directory)
	except OSError:
		return False
	return is_directory(directory)


def resolve_output_directory(target_path : str) -> Optional[str]:
	if is_animated_webp(target_path):
		return OUTPUT_VIDEO_DIRECTORY or DEFAULT_OUTPUT_VIDEO_DIRECTORY
	if is_image(target_path):
		return OUTPUT_IMAGE_DIRECTORY or DEFAULT_OUTPUT_IMAGE_DIRECTORY
	if is_video(target_path):
		return OUTPUT_VIDEO_DIRECTORY or DEFAULT_OUTPUT_VIDEO_DIRECTORY
	return None


def apply_output_directory(target_path : str) -> Optional[str]:
	output_directory = resolve_output_directory(target_path)
	if output_directory and ensure_directory(output_directory):
		state_manager.set_item('output_path', output_directory)
		return output_directory
	return None


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


def render() -> None:
	global OUTPUT_IMAGE_PATH_TEXTBOX
	global OUTPUT_IMAGE_CHOOSE_BUTTON
	global OUTPUT_IMAGE_OPEN_BUTTON
	global OUTPUT_VIDEO_PATH_TEXTBOX
	global OUTPUT_VIDEO_CHOOSE_BUTTON
	global OUTPUT_VIDEO_OPEN_BUTTON
	global OUTPUT_IMAGE
	global OUTPUT_VIDEO
	global OUTPUT_IMAGE_DIRECTORY
	global OUTPUT_VIDEO_DIRECTORY

	OUTPUT_IMAGE_DIRECTORY = load_config_path('output_image_path') or DEFAULT_OUTPUT_IMAGE_DIRECTORY
	OUTPUT_VIDEO_DIRECTORY = load_config_path('output_video_path') or DEFAULT_OUTPUT_VIDEO_DIRECTORY
	if not ensure_directory(OUTPUT_IMAGE_DIRECTORY):
		OUTPUT_IMAGE_DIRECTORY = DEFAULT_OUTPUT_IMAGE_DIRECTORY
		ensure_directory(OUTPUT_IMAGE_DIRECTORY)
	if not ensure_directory(OUTPUT_VIDEO_DIRECTORY):
		OUTPUT_VIDEO_DIRECTORY = DEFAULT_OUTPUT_VIDEO_DIRECTORY
		ensure_directory(OUTPUT_VIDEO_DIRECTORY)

	with gradio.Row():
		with gradio.Column():
			OUTPUT_IMAGE_PATH_TEXTBOX = gradio.Textbox(
				label = translator.get('uis.output_image_path_textbox'),
				value = OUTPUT_IMAGE_DIRECTORY,
				max_lines = 1
			)
			with gradio.Row():
				OUTPUT_IMAGE_CHOOSE_BUTTON = gradio.Button(
					value = translator.get('uis.choose_directory_button'),
					size = 'sm'
				)
				OUTPUT_IMAGE_OPEN_BUTTON = gradio.Button(
					value = translator.get('uis.open_directory_button'),
					size = 'sm'
				)
		with gradio.Column():
			OUTPUT_VIDEO_PATH_TEXTBOX = gradio.Textbox(
				label = translator.get('uis.output_video_path_textbox'),
				value = OUTPUT_VIDEO_DIRECTORY,
				max_lines = 1
			)
			with gradio.Row():
				OUTPUT_VIDEO_CHOOSE_BUTTON = gradio.Button(
					value = translator.get('uis.choose_directory_button'),
					size = 'sm'
				)
				OUTPUT_VIDEO_OPEN_BUTTON = gradio.Button(
					value = translator.get('uis.open_directory_button'),
					size = 'sm'
				)
	gradio.Markdown(translator.get('uis.output_directories_note'))
	OUTPUT_IMAGE = gradio.Image(
		label = translator.get('uis.output_image_or_video'),
		visible = False
	)
	OUTPUT_VIDEO = gradio.Video(
		label = translator.get('uis.output_image_or_video')
	)


def listen() -> None:
	OUTPUT_IMAGE_PATH_TEXTBOX.change(update_output_image_directory, inputs = OUTPUT_IMAGE_PATH_TEXTBOX, outputs = OUTPUT_IMAGE_PATH_TEXTBOX)
	OUTPUT_IMAGE_CHOOSE_BUTTON.click(choose_output_image_directory, outputs = OUTPUT_IMAGE_PATH_TEXTBOX)
	OUTPUT_IMAGE_OPEN_BUTTON.click(open_output_directory, inputs = OUTPUT_IMAGE_PATH_TEXTBOX)
	OUTPUT_VIDEO_PATH_TEXTBOX.change(update_output_video_directory, inputs = OUTPUT_VIDEO_PATH_TEXTBOX, outputs = OUTPUT_VIDEO_PATH_TEXTBOX)
	OUTPUT_VIDEO_CHOOSE_BUTTON.click(choose_output_video_directory, outputs = OUTPUT_VIDEO_PATH_TEXTBOX)
	OUTPUT_VIDEO_OPEN_BUTTON.click(open_output_directory, inputs = OUTPUT_VIDEO_PATH_TEXTBOX)
	register_ui_component('output_image', OUTPUT_IMAGE)
	register_ui_component('output_video', OUTPUT_VIDEO)


def update_output_image_directory(directory : str) -> gradio.Textbox:
	global OUTPUT_IMAGE_DIRECTORY
	directory = (directory or '').strip()
	if directory and ensure_directory(directory):
		OUTPUT_IMAGE_DIRECTORY = directory
		save_config_path('output_image_path', directory)
	return gradio.Textbox(value = OUTPUT_IMAGE_DIRECTORY or DEFAULT_OUTPUT_IMAGE_DIRECTORY)


def update_output_video_directory(directory : str) -> gradio.Textbox:
	global OUTPUT_VIDEO_DIRECTORY
	directory = (directory or '').strip()
	if directory and ensure_directory(directory):
		OUTPUT_VIDEO_DIRECTORY = directory
		save_config_path('output_video_path', directory)
	return gradio.Textbox(value = OUTPUT_VIDEO_DIRECTORY or DEFAULT_OUTPUT_VIDEO_DIRECTORY)


def choose_output_image_directory() -> gradio.Textbox:
	global OUTPUT_IMAGE_DIRECTORY
	selected_directory = ask_directory(OUTPUT_IMAGE_DIRECTORY or DEFAULT_OUTPUT_IMAGE_DIRECTORY)
	if selected_directory:
		OUTPUT_IMAGE_DIRECTORY = selected_directory
		save_config_path('output_image_path', selected_directory)
		return gradio.Textbox(value = selected_directory)
	return gradio.update()


def choose_output_video_directory() -> gradio.Textbox:
	global OUTPUT_VIDEO_DIRECTORY
	selected_directory = ask_directory(OUTPUT_VIDEO_DIRECTORY or DEFAULT_OUTPUT_VIDEO_DIRECTORY)
	if selected_directory:
		OUTPUT_VIDEO_DIRECTORY = selected_directory
		save_config_path('output_video_path', selected_directory)
		return gradio.Textbox(value = selected_directory)
	return gradio.update()


def open_output_directory(directory : str) -> None:
	if directory and os.path.isdir(directory):
		os.startfile(directory)

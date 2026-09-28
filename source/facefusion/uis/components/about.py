import os
import sys
from configparser import ConfigParser
from typing import Optional

import gradio

from facefusion import metadata, state_manager, translator

METADATA_BUTTON : Optional[gradio.Button] = None
ACTION_BUTTON : Optional[gradio.Button] = None
LANGUAGE_DROPDOWN : Optional[gradio.Dropdown] = None


def render() -> None:
	global METADATA_BUTTON
	global ACTION_BUTTON
	global LANGUAGE_DROPDOWN

	LANGUAGE_DROPDOWN = gradio.Dropdown(
		label = translator.get('uis.language_dropdown'),
		choices = [ ('中文', 'zh'), ('English', 'en') ],
		value = translator.CURRENT_LANGUAGE,
		interactive = True
	)
	LANGUAGE_DROPDOWN.change(change_language, inputs = LANGUAGE_DROPDOWN)

	METADATA_BUTTON = gradio.Button(
		value = metadata.get('name') + ' ' + metadata.get('version'),
		variant = 'primary',
		link = metadata.get('url')
	)
	ACTION_BUTTON = gradio.Button(
		# 两个按钮都指向本项目仓库: 上方显示名称与版本, 下方是进入仓库的入口
		value = translator.get('about.repository'),
		link = metadata.get('url'),
		size = 'sm'
	)


def change_language(language : str) -> None:
	if language not in ( 'zh', 'en' ):
		return

	config_path = state_manager.get_item('config_path')
	config_parser = ConfigParser()
	config_parser.read(config_path, encoding = 'utf-8')

	if not config_parser.has_section('uis'):
		config_parser.add_section('uis')
	config_parser.set('uis', 'language', language)

	with open(config_path, 'w', encoding = 'utf-8') as config_file:
		config_parser.write(config_file)

	os.execv(sys.executable, [ sys.executable ] + sys.argv)
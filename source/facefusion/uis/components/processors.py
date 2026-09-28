from typing import List, Optional, Tuple

import gradio

from facefusion import state_manager, translator
from facefusion.filesystem import get_file_name, resolve_file_paths
from facefusion.processors.core import get_processors_modules
from facefusion.uis.core import register_ui_component

PROCESSORS_CHECKBOX_GROUP : Optional[gradio.CheckboxGroup] = None


def render() -> None:
	global PROCESSORS_CHECKBOX_GROUP

	PROCESSORS_CHECKBOX_GROUP = gradio.CheckboxGroup(
		label = translator.get('uis.processors_checkbox_group'),
		choices = build_processor_choices(state_manager.get_item('processors')),
		value = state_manager.get_item('processors'),
		info = translator.get('uis.processors_checkbox_group_info'),
	)
	register_ui_component('processors_checkbox_group', PROCESSORS_CHECKBOX_GROUP)


def listen() -> None:
	PROCESSORS_CHECKBOX_GROUP.change(update_processors, inputs = PROCESSORS_CHECKBOX_GROUP, outputs = PROCESSORS_CHECKBOX_GROUP)


def update_processors(processors : List[str]) -> gradio.CheckboxGroup:
	for processor_module in get_processors_modules(state_manager.get_item('processors')):
		if hasattr(processor_module, 'clear_inference_pool'):
			processor_module.clear_inference_pool()

	for processor_module in get_processors_modules(processors):
		if not processor_module.pre_check():
			return gradio.CheckboxGroup()

	state_manager.set_item('processors', processors)
	return gradio.CheckboxGroup(value = state_manager.get_item('processors'), choices = build_processor_choices(state_manager.get_item('processors')))


def build_processor_choices(processors : List[str]) -> List[Tuple[str, str]]:
	# 按钮上显示「英文名 中文名」, 值仍然是处理器英文名, 便于对照文档与命令行参数
	choices : List[Tuple[str, str]] = []

	for processor in sort_processors(processors):
		display_name = translator.get('uis.processor_' + processor)
		if display_name:
			choices.append(('{} · {}'.format(processor, display_name), processor))
		else:
			choices.append((processor, processor))

	return choices


def sort_processors(processors : List[str]) -> List[str]:
	available_processors = [ get_file_name(file_path) for file_path in resolve_file_paths('facefusion/processors/modules') ]
	current_processors = []

	for processor in processors + available_processors:
		if processor in available_processors and processor not in current_processors:
			current_processors.append(processor)

	return current_processors

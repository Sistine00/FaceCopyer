import importlib
import logging
import os
import warnings
from types import ModuleType
from typing import Any, Dict, List, Optional

import gradio
from gradio.themes import Size

import facefusion.uis.model_status as uis_model_status
import facefusion.uis.overrides as uis_overrides
from facefusion import logger, metadata, state_manager, translator
from facefusion.exit_helper import hard_exit
from facefusion.filesystem import resolve_relative_path
from facefusion.uis.types import Component, ComponentName

UI_COMPONENTS: Dict[ComponentName, Component] = {}
UI_LAYOUT_MODULES : List[ModuleType] = []
UI_LAYOUT_METHODS =\
[
	'pre_check',
	'render',
	'listen',
	'run'
]

# Gradio 缓存目录(即 init() 里设置的 GRADIO_TEMP_DIR)装着两类东西: 浏览器上传的素材副本,
# 以及组件显示成片时另存的一份拷贝。它们不会被程序主动清理, 所以交给 gradio 自己按策略过期,
# 参数含义是 [检查间隔, 过期秒数]:
#   每 CACHE_DELETE_FREQUENCY 秒检查一次, 创建时间超过 CACHE_DELETE_AGE 秒的文件删掉。
# 这里取「每 15 分钟检查一次、超过 2 小时删除」。批量成片会在缓存里各留一份完整拷贝,
# 实测 7 个目标就堆到 3.5 GB, 长批量跑下来能到十几 GB, 所以过期时间不能放太长。
# 另外服务停止时(重启或关窗)gradio 会清空整个缓存, 所以重启后素材需要重新选一次。
# 注意清理只作用于缓存里的副本 —— 输出目录(D:\facefusion\output)里的成片是原文件, 不受影响。
# 需要更激进或更保守时可以改这两个值, 也可以把它们接到界面上让用户自己选。
CACHE_DELETE_FREQUENCY = 900
CACHE_DELETE_AGE = 7200


def load_ui_layout_module(ui_layout : str) -> Any:
	try:
		ui_layout_module = importlib.import_module('facefusion.uis.layouts.' + ui_layout)
		for method_name in UI_LAYOUT_METHODS:
			if not hasattr(ui_layout_module, method_name):
				raise NotImplementedError
	except ModuleNotFoundError as exception:
		logger.error(translator.get('ui_layout_not_loaded').format(ui_layout = ui_layout), __name__)
		logger.debug(exception.msg, __name__)
		hard_exit(1)
	except NotImplementedError:
		logger.error(translator.get('ui_layout_not_implemented').format(ui_layout = ui_layout), __name__)
		hard_exit(1)
	return ui_layout_module


def get_ui_layouts_modules(ui_layouts : List[str]) -> List[ModuleType]:
	if not UI_LAYOUT_MODULES:
		for ui_layout in ui_layouts:
			ui_layout_module = load_ui_layout_module(ui_layout)
			UI_LAYOUT_MODULES.append(ui_layout_module)
	return UI_LAYOUT_MODULES


def get_ui_component(component_name : ComponentName) -> Optional[Component]:
	if component_name in UI_COMPONENTS:
		return UI_COMPONENTS[component_name]
	return None


def get_ui_components(component_names : List[ComponentName]) -> Optional[List[Component]]:
	ui_components = []

	for component_name in component_names:
		component = get_ui_component(component_name)
		if component:
			ui_components.append(component)
	return ui_components


def register_ui_component(component_name : ComponentName, component: Component) -> None:
	UI_COMPONENTS[component_name] = component


def init() -> None:
	os.environ['GRADIO_ANALYTICS_ENABLED'] = '0'
	# 这里必须用 setdefault: gradio 的缓存目录在 import 时就定下来了, 入口脚本 facefusion.py
	# 已经按 <项目根>\temp\gradio 设过一次。若在这里用赋值覆盖, 会与导入时的取值不一致,
	# 结果上传副本被拆到两个目录里 —— 实测就是这个现象。这里只作为兜底。
	os.environ.setdefault('GRADIO_TEMP_DIR', os.path.join(state_manager.get_item('temp_path'), 'gradio'))

	logging.getLogger('asyncio').setLevel(logging.CRITICAL)
	warnings.filterwarnings('ignore', category = UserWarning, module = 'gradio')
	gradio.processing_utils._check_allowed = uis_overrides.mock
	gradio.processing_utils.convert_video_to_playable_mp4 = uis_overrides.convert_video_to_playable_mp4
	gradio.components.Number.raise_if_out_of_bounds = uis_overrides.mock


def launch() -> None:
	ui_layouts_total = len(state_manager.get_item('ui_layouts'))
	# head 只作为数据通道: 已下载模型清单会被下发到 window.gradio_config.head,
	# 由 gradio 模板 index.html 里的脚本读取并给模型下拉列表上色。
	with gradio.Blocks(theme = get_theme(), css = get_css(), head = uis_model_status.get_status_payload(), title = metadata.get('name') + ' ' + metadata.get('version'), fill_width = True, delete_cache = ( CACHE_DELETE_FREQUENCY, CACHE_DELETE_AGE )) as ui:
		for ui_layout in state_manager.get_item('ui_layouts'):
			ui_layout_module = load_ui_layout_module(ui_layout)

			if ui_layouts_total > 1:
				with gradio.Tab(ui_layout):
					ui_layout_module.render()
					ui_layout_module.listen()
			else:
				ui_layout_module.render()
				ui_layout_module.listen()

	for ui_layout in state_manager.get_item('ui_layouts'):
		ui_layout_module = load_ui_layout_module(ui_layout)
		ui_layout_module.run(ui)


def get_theme() -> gradio.Theme:
	return gradio.themes.Base(
		primary_hue = gradio.themes.colors.red,
		secondary_hue = gradio.themes.Color(
			name = 'neutral',
			c50 = '#fafafa',
			c100 = '#f5f5f5',
			c200 = '#e5e5e5',
			c300 = '#d4d4d4',
			c400 = '#a3a3a3',
			c500 = '#737373',
			c600 = '#525252',
			c700 = '#404040',
			c800 = '#262626',
			c900 = '#212121',
			c950 = '#171717',
		),
		radius_size = Size(
			xxs = '0.375rem',
			xs = '0.375rem',
			sm = '0.375rem',
			md = '0.375rem',
			lg = '0.375rem',
			xl = '0.375rem',
			xxl = '0.375rem',
		),
		font = gradio.themes.GoogleFont('Open Sans')
	).set(
		color_accent = 'transparent',
		color_accent_soft = 'transparent',
		color_accent_soft_dark = 'transparent',
		background_fill_primary = '*neutral_100',
		background_fill_primary_dark = '*neutral_950',
		background_fill_secondary = '*neutral_50',
		background_fill_secondary_dark = '*neutral_800',
		block_background_fill = 'white',
		block_background_fill_dark = '*neutral_900',
		block_border_width = '0',
		block_label_background_fill = '*neutral_100',
		block_label_background_fill_dark = '*neutral_800',
		block_label_border_width = 'none',
		block_label_margin = '0.5rem',
		block_label_radius = '*radius_md',
		block_label_text_color = '*neutral_700',
		block_label_text_size = '*text_sm',
		block_label_text_color_dark = 'white',
		block_label_text_weight = '600',
		block_title_background_fill = '*neutral_100',
		block_title_background_fill_dark = '*neutral_800',
		block_title_padding = '*block_label_padding',
		block_title_radius = '*block_label_radius',
		block_title_text_color = '*neutral_700',
		block_title_text_size = '*text_sm',
		block_title_text_weight = '600',
		block_padding = '0.5rem',
		border_color_accent = 'transparent',
		border_color_accent_dark = 'transparent',
		border_color_accent_subdued = 'transparent',
		border_color_accent_subdued_dark = 'transparent',
		border_color_primary = 'transparent',
		border_color_primary_dark = 'transparent',
		button_large_padding = '2rem 0.5rem',
		button_large_text_weight = 'normal',
		button_primary_background_fill = '*primary_500',
		button_primary_background_fill_dark = '*primary_600',
		button_primary_text_color = 'white',
		button_secondary_background_fill = 'white',
		button_secondary_background_fill_dark = '*neutral_800',
		button_secondary_background_fill_hover = 'white',
		button_secondary_background_fill_hover_dark = '*neutral_800',
		button_secondary_text_color = '*neutral_800',
		button_small_padding = '0.75rem',
		button_small_text_size = '0.875rem',
		checkbox_background_color = '*neutral_200',
		checkbox_background_color_dark = '*neutral_900',
		checkbox_background_color_selected = '*primary_600',
		checkbox_background_color_selected_dark = '*primary_700',
		checkbox_label_background_fill = '*neutral_50',
		checkbox_label_background_fill_dark = '*neutral_800',
		checkbox_label_background_fill_hover = '*neutral_50',
		checkbox_label_background_fill_hover_dark = '*neutral_800',
		checkbox_label_background_fill_selected = '*primary_500',
		checkbox_label_background_fill_selected_dark = '*primary_600',
		checkbox_label_text_color_selected = 'white',
		error_background_fill = 'white',
		error_background_fill_dark = '*neutral_900',
		error_text_color = '*primary_500',
		error_text_color_dark = '*primary_600',
		input_background_fill = '*neutral_50',
		input_background_fill_dark = '*neutral_800',
		shadow_drop = 'none',
		slider_color = '*primary_500',
		slider_color_dark = '*primary_600'
	)


def get_css() -> str:
	overrides_css_path = resolve_relative_path('uis/assets/overrides.css')
	return open(overrides_css_path).read()

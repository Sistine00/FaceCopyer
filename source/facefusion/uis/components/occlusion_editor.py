"""occlusion_editor.py — 手动描边遮挡物: 用户在 Web 上对目标图用画笔涂掉遮挡物,
把笔迹转成二值掩码 PNG; 运行时作为 IOPaint 修复掩码替换自动检测.
组件渲染进 target 区块内部, 不改变原布局.

用 gradio.Sketchpad 而非 gradio.ImageEditor: 前者自带画笔粗细弹层/橡皮/撤销/清空/全屏,
无需自定义滑块与前端补丁. 掩码取"笔迹层"的 alpha 通道(不是整张合成图),
因此原图里本身存在的红色像素不会被误判成描边.

Gradio 5.50 的 Sketchpad 只在"挂载时即可见"时能正常初始化: 以 visible=False 挂载后再切可见,
内部工具会在 context 就绪前被 set_tool, 抛 "Cannot read properties of undefined (reading 'app')",
画布从此永久不可编辑(浏览器验证结论)。因此这里始终 visible=True 挂载,
用一张占位图表示"尚未选择目标图", 并且绝不再切换 visible。"""
import os
from typing import Optional

import cv2
import gradio
import numpy as np
from gradio import Brush, Eraser
from PIL import Image

from facefusion import state_manager, translator
from facefusion.filesystem import is_image
from facefusion.uis.core import register_ui_component

OCCLUSION_EDITOR : Optional[gradio.Sketchpad] = None
OCCLUSION_NOTE : Optional[gradio.Markdown] = None
OCCLUSION_MASK_PATH : Optional[str] = None

MIN_STROKE_PIXELS = 30
PLACEHOLDER_WIDTH = 1280
PLACEHOLDER_HEIGHT = 720


def _temp_dir() -> str:
	base = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '.temp'))
	os.makedirs(base, exist_ok = True)
	return base


def _placeholder_path() -> str:
	path = os.path.join(_temp_dir(), 'occlusion_placeholder.png')
	if not os.path.isfile(path):
		canvas = np.full((PLACEHOLDER_HEIGHT, PLACEHOLDER_WIDTH, 3), 246, np.uint8)
		cv2.rectangle(canvas, (0, 0), (PLACEHOLDER_WIDTH - 1, PLACEHOLDER_HEIGHT - 1), (216, 216, 216), 2)
		cv2.putText(canvas, 'Select a target image first', (378, 368), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (168, 168, 168), 2, cv2.LINE_AA)
		cv2.imwrite(path, canvas)
	return path


def get_user_mask_path() -> Optional[str]:
	return OCCLUSION_MASK_PATH if OCCLUSION_MASK_PATH and os.path.isfile(OCCLUSION_MASK_PATH) else None


def outline_to_filled(strokes : np.ndarray) -> np.ndarray:
	"""把用户描出的笔迹转成待挖除区域。

	描边(沿遮挡物边缘画一圈)时只填"笔迹真正围住的封闭区域": 用从画布四边泛洪求外部的办法,
	开口的笔迹(如只画了半圈)不会把整块背景一起圈进来。
	涂满(实心涂抹)时不做填充, 原样返回笔迹, 这样橡皮擦擦掉的地方不会被重新填回来。"""
	if int((strokes > 0).sum()) < MIN_STROKE_PIXELS:
		return strokes
	kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
	closed = cv2.dilate(strokes, kernel, iterations = 1)
	closed = cv2.morphologyEx(closed, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)))

	num_labels, labels = cv2.connectedComponents(cv2.bitwise_not(closed), connectivity = 4)
	keep = np.ones(num_labels, dtype = bool)
	keep[0] = False
	for border_label in set(labels[0, :].tolist()) | set(labels[- 1, :].tolist()) | set(labels[:, 0].tolist()) | set(labels[:, - 1].tolist()):
		keep[border_label] = False
	enclosed = keep[labels].astype(np.uint8) * 255
	enclosed = cv2.dilate(enclosed, kernel, iterations = 1)
	region = np.maximum(enclosed, strokes)

	stroke_area = int((strokes > 0).sum())
	region_area = int((region > 0).sum())
	if region_area and stroke_area >= 0.85 * region_area:
		return strokes
	return region


def make_editor(value) -> gradio.Sketchpad:
	return gradio.Sketchpad(
		value = value if value else _placeholder_path(),
		label = translator.get('uis.occlusion_editor_label'),
		sources = [ 'upload' ],
		layers = False,
		brush = Brush(default_size = 18, colors = [ 'rgb(255,0,0)' ], default_color = 'rgb(255,0,0)', color_mode = 'fixed'),
		eraser = Eraser(default_size = 18),
		show_label = True,
		type = 'pil',
		format = 'png',
		height = 780,
		width = '100%',
		min_width = 420,
		interactive = True,
		show_fullscreen_button = True,
		visible = True,
	)


def render() -> None:
	"""在当前 Blocks 上下文(即 target 区块)内创建编辑器, 不新建分栏."""
	global OCCLUSION_EDITOR
	global OCCLUSION_NOTE

	target_path = state_manager.get_item('target_path')

	with gradio.Column():
		OCCLUSION_EDITOR = make_editor(target_path if is_image(target_path) else None)
		OCCLUSION_NOTE = gradio.Markdown(translator.get('uis.occlusion_editor_note'))
	register_ui_component('occlusion_mask_editor', OCCLUSION_EDITOR)


def listen() -> None:
	from facefusion.uis.components import target

	if OCCLUSION_EDITOR is not None:
		OCCLUSION_EDITOR.change(save_mask, inputs = OCCLUSION_EDITOR)
		if target.TARGET_FILE is not None:
			target.TARGET_FILE.change(reset_on_target_change, inputs = target.TARGET_FILE, outputs = OCCLUSION_EDITOR)


def reset_state() -> None:
	"""清除后端保存的手动描边掩码(不触碰前端编辑器)."""
	global OCCLUSION_MASK_PATH
	OCCLUSION_MASK_PATH = None


def _strokes_from_layer(layer) -> Optional[np.ndarray]:
	"""笔迹层是透明底 RGBA, alpha 非零处即描边."""
	if not isinstance(layer, Image.Image):
		return None
	alpha = np.asarray(layer.convert('RGBA'))[:, :, 3]
	if int((alpha > 0).sum()) < MIN_STROKE_PIXELS:
		return None
	return (alpha > 0).astype(np.uint8) * 255


def save_mask(editor_value) -> None:
	global OCCLUSION_MASK_PATH
	OCCLUSION_MASK_PATH = None
	if editor_value is None:
		return

	strokes = None
	if isinstance(editor_value, dict):
		layers = [ layer for layer in (editor_value.get('layers') or []) if isinstance(layer, Image.Image) ]
		for layer in reversed(layers):
			strokes = _strokes_from_layer(layer)
			if strokes is not None:
				break
	else:
		strokes = _strokes_from_layer(editor_value)

	if strokes is None:
		return
	filled = outline_to_filled(strokes)
	mask_path = os.path.join(_temp_dir(), 'occlusion_user_mask.png')
	cv2.imwrite(mask_path, filled)
	OCCLUSION_MASK_PATH = mask_path


def reset_on_target_change(file) -> gradio.Sketchpad:
	global OCCLUSION_MASK_PATH
	OCCLUSION_MASK_PATH = None
	value = file.name if file and is_image(file.name) else None
	return make_editor(value)

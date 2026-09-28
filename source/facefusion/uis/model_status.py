"""模型可用性标记。

为界面下拉框提供「该模型是否已下载可用」的判断, 并把结果注入前端:
已下载的模型在选择列表里标红, 未下载的标灰。

判断依据是模型文件与其同名 .hash 文件是否同时存在 —— 下载器在校验失败时
会删除源文件, 因此两者齐备基本等价于该模型可用。这里刻意不做 crc32 全量校验,
因为模型总量有数 GB, 每次启动全量读盘会明显拖慢启动。
"""
import os
from typing import Dict, List, Set

from facefusion.filesystem import resolve_relative_path

# 文件名与模型名不一致的少数情况
DETECTOR_FILE_NAMES : Dict[str, str] =\
{
	'retinaface': 'retinaface_10g.onnx',
	'scrfd': 'scrfd_2.5g.onnx',
	'yolo_face': 'yoloface_8n.onnx',
	'yunet': 'yunet.onnx'
}

# live_portrait 由多个子模型组成, 表情恢复与人体编辑需要的文件不完全相同
LIVE_PORTRAIT_BASE : List[str] =\
[
	'live_portrait_feature_extractor.onnx',
	'live_portrait_motion_extractor.onnx',
	'live_portrait_generator.onnx'
]
LIVE_PORTRAIT_EDITOR : List[str] = LIVE_PORTRAIT_BASE +\
[
	'live_portrait_eye_retargeter.onnx',
	'live_portrait_lip_retargeter.onnx',
	'live_portrait_stitcher.onnx'
]


def get_models_directory() -> str:
	return resolve_relative_path('../.assets/models')


def get_model_file_names(model_category : str, model : str) -> List[str]:
	if model_category == 'face_detector':
		return [ DETECTOR_FILE_NAMES.get(model, model + '.onnx') ]
	if model_category == 'deep_swapper':
		model_scope, _separator, model_name = model.partition('/')
		return [ os.path.join(model_scope, model_name + '.dfm') ]
	if model_category == 'expression_restorer':
		return list(LIVE_PORTRAIT_BASE)
	if model_category == 'face_editor':
		return list(LIVE_PORTRAIT_EDITOR)
	return [ model + '.onnx' ]


def is_model_ready(model_category : str, model : str) -> bool:
	for file_name in get_model_file_names(model_category, model):
		model_path = os.path.join(get_models_directory(), file_name)
		hash_path = os.path.splitext(model_path)[0] + '.hash'
		if not os.path.isfile(model_path) or not os.path.isfile(hash_path):
			return False
	return True


def get_model_catalog() -> List[tuple]:
	import facefusion.choices
	from facefusion.processors.modules.age_modifier import choices as age_modifier_choices
	from facefusion.processors.modules.background_remover import choices as background_remover_choices
	from facefusion.processors.modules.deep_swapper import choices as deep_swapper_choices
	from facefusion.processors.modules.expression_restorer import choices as expression_restorer_choices
	from facefusion.processors.modules.face_editor import choices as face_editor_choices
	from facefusion.processors.modules.face_enhancer import choices as face_enhancer_choices
	from facefusion.processors.modules.face_swapper import choices as face_swapper_choices
	from facefusion.processors.modules.frame_colorizer import choices as frame_colorizer_choices
	from facefusion.processors.modules.frame_enhancer import choices as frame_enhancer_choices
	from facefusion.processors.modules.lip_syncer import choices as lip_syncer_choices

	return\
	[
		('face_swapper', face_swapper_choices.face_swapper_models),
		('face_enhancer', face_enhancer_choices.face_enhancer_models),
		('face_detector', [ model for model in facefusion.choices.face_detector_models if model != 'many' ]),
		('face_landmarker', [ model for model in facefusion.choices.face_landmarker_models if model != 'many' ]),
		('face_occluder', [ model for model in facefusion.choices.face_occluder_models if model != 'many' ]),
		('face_parser', facefusion.choices.face_parser_models),
		('voice_extractor', facefusion.choices.voice_extractor_models),
		('age_modifier', age_modifier_choices.age_modifier_models),
		('expression_restorer', expression_restorer_choices.expression_restorer_models),
		('face_editor', face_editor_choices.face_editor_models),
		('frame_enhancer', frame_enhancer_choices.frame_enhancer_models),
		('frame_colorizer', frame_colorizer_choices.frame_colorizer_models),
		('lip_syncer', lip_syncer_choices.lip_syncer_models),
		('background_remover', background_remover_choices.background_remover_models),
		('deep_swapper', deep_swapper_choices.deep_swapper_models)
	]


def get_model_status() -> Dict[str, bool]:
	status : Dict[str, bool] = {}
	for model_category, models in get_model_catalog():
		for model in models:
			status.setdefault(model, is_model_ready(model_category, model))
	return status


def get_status_payload() -> str:
	"""返回前端上色脚本需要的数据。

	Gradio 的 index.html 模板并不渲染 Blocks 的 head 参数, 但 head 会随
	window.gradio_config 一起下发。因此这里把 head 当作纯数据通道:
	前半段是已下载的模型, 后半段是全部模型, 用 # 分隔、用 | 连接模型名。
	真正负责上色的脚本放在 gradio 的 index.html 模板里 (见 uis/core.py 注释)。
	"""
	status = get_model_status()
	ready_joined = '|'.join(sorted([ model for model, is_ready in status.items() if is_ready ]))
	all_joined = '|'.join(sorted(status.keys()))
	return ready_joined + '#' + all_joined

"""按目标统计换脸结果的计数器。

换脸是否真的发生, 从外面看不出来: 目标或源里检测不到人脸时,
`face_swapper.process_frame` 会把原帧原样返回, 日志里也只有「处理成功」。
所以这里让处理器把每帧的结果记下来, 批量处理时就能逐个目标给出结论
「换脸了多少帧」或「一帧都没换」。

批量面板在跑每个目标前调用 reset(), 跑完读 get_stats()。
"""
from typing import Dict

COUNTER_SWAPPED_FRAMES = 'swapped_frames'
COUNTER_MISSED_FRAMES = 'missed_frames'

_STATS : Dict[str, int] =\
{
	COUNTER_SWAPPED_FRAMES: 0,
	COUNTER_MISSED_FRAMES: 0
}


def reset() -> None:
	for counter_name in _STATS:
		_STATS[counter_name] = 0


def increment(counter_name : str, amount : int = 1) -> None:
	if counter_name in _STATS:
		_STATS[counter_name] += amount


def get_stats() -> Dict[str, int]:
	return dict(_STATS)


def has_swapped() -> bool:
	return _STATS[COUNTER_SWAPPED_FRAMES] > 0


def has_missed() -> bool:
	return _STATS[COUNTER_MISSED_FRAMES] > 0

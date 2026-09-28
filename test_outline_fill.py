"""直接验证 outline_to_filled: 描边自动填充 / 涂满保留笔迹 / 橡皮擦有效 / 开口笔迹不炸背景."""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, r'D:\facefusion\source')
os.environ.setdefault('FACEFUSION_DISABLE_NSFW', '1')

from facefusion.uis.components.occlusion_editor import outline_to_filled

H, W = 1200, 1200


def area(mask):
	return int((mask > 0).sum())


def case_closed_outline():
	canvas = np.zeros((H, W), np.uint8)
	cv2.circle(canvas, (600, 600), 200, 255, 18)
	out = outline_to_filled(canvas)
	expected = 3.14159 * 200 ** 2
	print('[closed outline] in={} out={} expected~{:.0f} ratio={:.2f}'.format(area(canvas), area(out), expected, area(out) / expected))
	return 0.75 < area(out) / expected < 1.35


def case_open_stroke():
	canvas = np.zeros((H, W), np.uint8)
	cv2.ellipse(canvas, (600, 600), (200, 200), 0, 20, 340, 255, 18)
	out = outline_to_filled(canvas)
	print('[open C stroke] in={} out={}'.format(area(canvas), area(out)))
	return area(out) < area(canvas) * 1.6


def case_solid_paint():
	canvas = np.zeros((H, W), np.uint8)
	canvas[400:700, 400:800] = 255
	out = outline_to_filled(canvas)
	print('[solid paint] in={} out={}'.format(area(canvas), area(out)))
	return area(out) == area(canvas)


def case_solid_then_erase():
	canvas = np.zeros((H, W), np.uint8)
	canvas[400:700, 400:800] = 255
	before = area(canvas)
	canvas[500:600, 550:650] = 0
	after = area(canvas)
	out = outline_to_filled(canvas)
	print('[solid + erase center] before={} strokes={} out={}'.format(before, after, area(out)))
	return area(out) <= after + 200


def main():
	results = {
		'closed outline fills': case_closed_outline(),
		'open stroke no blowup': case_open_stroke(),
		'solid paint kept': case_solid_paint(),
		'eraser survives': case_solid_then_erase(),
	}
	for name, ok in results.items():
		print('{} {}'.format('PASS' if ok else 'FAIL', name))
	print('ALL PASS' if all(results.values()) else 'HAS FAILURE')


main()

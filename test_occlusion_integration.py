"""集成验证: 手动描边掩码 -> remove_occlusion 实际只修复标注区域, 其余像素保持原样."""
import os
import shutil
import sys

import cv2
import numpy as np

sys.path.insert(0, r'D:\facefusion\source')
os.environ.setdefault('FACEFUSION_DISABLE_NSFW', '1')

TARGET = r'D:\facefusion\swap_task\occl_target.png'
MASK = r'D:\facefusion\.temp\it_mask.png'
CACHE = r'D:\facefusion\source\.occlusion_removed'


def main():
	from facefusion import state_manager
	from facefusion.iopaint_remove import is_iopaint_available, remove_occlusion
	from facefusion.vision import read_image

	state_manager.set_item('occlusion_mode', 'remove')
	print('iopaint available =', is_iopaint_available())
	if not is_iopaint_available():
		print('FAIL iopaint not reachable')
		return

	if os.path.isdir(CACHE):
		shutil.rmtree(CACHE, ignore_errors = True)
	os.makedirs(os.path.dirname(MASK), exist_ok = True)

	source = read_image(TARGET)
	h, w = source.shape[: 2]
	print('target', w, 'x', h)

	# 手动标注: 盖住画面上半部分的矩形(模拟用户描边)
	mask = np.zeros((h, w), np.uint8)
	mask[int(h * 0.18):int(h * 0.52), int(w * 0.25):int(w * 0.75)] = 255
	cv2.imwrite(MASK, mask)
	print('manual mask px =', int((mask > 0).sum()))

	out_path = remove_occlusion(TARGET, MASK)
	print('output =', out_path, 'exists =', os.path.isfile(out_path))
	if not os.path.isfile(out_path):
		print('FAIL no output')
		return

	result = read_image(out_path)
	print('output size', result.shape[1], 'x', result.shape[0])
	if result.shape[: 2] != (h, w):
		print('FAIL size mismatch')
		return

	diff = np.abs(result.astype(np.int16) - source.astype(np.int16)).max(axis = 2)
	grown = cv2.dilate(mask, np.ones((9, 9), np.uint8), iterations = 1)
	inside = diff[grown > 0]
	outside = diff[grown == 0]
	changed_inside = float((inside > 12).mean()) if inside.size else 0.0
	changed_outside = float((outside > 12).mean()) if outside.size else 0.0
	print('inside-mask changed ratio  = {:.3f}'.format(changed_inside))
	print('outside-mask changed ratio = {:.4f}'.format(changed_outside))
	print('PASS' if changed_inside > 0.30 and changed_outside < 0.02 else 'FAIL')


main()

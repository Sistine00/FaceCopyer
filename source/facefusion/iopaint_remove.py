import base64
import hashlib
import io
import json
import os
import urllib.request
from typing import List, Tuple

import cv2
import numpy as np
from PIL import Image

from facefusion import state_manager
from facefusion.face_detector import detect_faces
from facefusion.face_helper import convert_to_face_landmark_5, estimate_face_angle
from facefusion.face_landmarker import detect_face_landmark, estimate_face_landmark_68_5
from facefusion.filesystem import create_directory, get_file_extension, get_file_name, is_file
from facefusion.types import VisionFrame
from facefusion.vision import read_image

IOPAINT_PORT = 8081
IOPAINT_URL = os.environ.get('IOPAINT_URL', 'http://127.0.0.1:{}/api/v1/inpaint'.format(IOPAINT_PORT))
CACHE_DIRECTORY = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '.occlusion_removed'))

# 去遮挡后的空白脸上已经没有可见五官, 换脸时重新检测的 landmark 必然不准(导致五官错位)。
# 因此: 在去遮挡前, 于「原始遮挡目标图」上检测并缓存完整 landmark,
# 换脸时直接复用这份 landmark, 保证五官对齐与无遮挡场景一致。
_LANDMARK_CACHE : dict = {}


def _landmark_meta_path(output_path : str) -> str:
    return output_path + '.lm.json'


def cache_target_landmarks(output_path : str, box, lm5, lm68) -> None:
    def to_list(arr):
        return np.asarray(arr, dtype = np.float32).tolist()
    entry = {
        'box': to_list(box),
        'lm5': to_list(lm5),
        'lm68': to_list(lm68)
    }
    _LANDMARK_CACHE[output_path] = entry
    try:
        with open(_landmark_meta_path(output_path), 'w', encoding = 'utf-8') as f:
            json.dump(entry, f)
    except Exception:
        pass


def load_cached_landmarks(output_path : str):
    entry = _LANDMARK_CACHE.get(output_path)
    if entry is not None:
        return entry
    meta_path = _landmark_meta_path(output_path)
    if is_file(meta_path):
        try:
            with open(meta_path, 'r', encoding = 'utf-8') as f:
                entry = json.load(f)
            _LANDMARK_CACHE[output_path] = entry
            return entry
        except Exception:
            return None
    return None


def get_cached_landmarks(image_path : str):
    return load_cached_landmarks(image_path)


def _correct_eye_symmetry(lm68, mask):
    # 遮挡物(贴纸/刘海)常带偏被遮一侧的眼睛 landmark, 导致换脸五官错位。
    # 通用校正: 眼睛中心落在遮挡 mask 内的一侧, 用另一侧(未遮挡)相对鼻梁中线镜像复原。
    if lm68 is None or len(lm68) != 68 or mask is None:
        return lm68
    lm68 = np.asarray(lm68, dtype = np.float32).copy()
    h, w = mask.shape[: 2]
    def region_occ(p, r = 10):
        x0 = max(0, int(p[0]) - r); x1 = min(w, int(p[0]) + r)
        y0 = max(0, int(p[1]) - r); y1 = min(h, int(p[1]) + r)
        return x1 > x0 and y1 > y0 and mask[y0:y1, x0:x1].max() > 0
    left_eye = lm68[36:42].mean(0)
    right_eye = lm68[42:48].mean(0)
    mid_x = float(lm68[27:31, 0].mean())
    left_occ = region_occ(left_eye)
    right_occ = region_occ(right_eye)
    if right_occ and not left_occ:
        dx = mid_x - left_eye[0]
        target = np.array([ mid_x + dx, left_eye[1] ], dtype = np.float32)
        shift = target - right_eye
        lm68[42:48] += shift
        lm68[22:27] += shift
    elif left_occ and not right_occ:
        dx = right_eye[0] - mid_x
        target = np.array([ mid_x - dx, right_eye[1] ], dtype = np.float32)
        shift = target - left_eye
        lm68[36:42] += shift
        lm68[17:22] += shift
    elif left_occ and right_occ:
        avg_y = (left_eye[1] + right_eye[1]) * 0.5
        lm68[36:42, 1] += avg_y - left_eye[1]
        lm68[42:48, 1] += avg_y - right_eye[1]
    return lm68


def detect_target_landmarks(vision_frame : VisionFrame, box, lm5_raw, mask = None):
    # 返回 (lm5, lm68)。lm5 为 68 点转出的 5 点(换脸对齐锚点),
    # lm68 为 68 点(area mask / 融合用)。检测失败时退回 detector 的 5 点先验。
    lm5_raw = np.asarray(lm5_raw, dtype = np.float32)
    lm5_final = lm5_raw
    lm68 = None
    try:
        lm68_est = estimate_face_landmark_68_5(lm5_raw)
        angle = estimate_face_angle(lm68_est)
        lm68, lm68_score = detect_face_landmark(vision_frame, np.asarray(box, dtype = np.float32), angle)
        if lm68 is not None and len(lm68) == 68:
            lm68 = np.asarray(lm68, dtype = np.float32)
            lm68 = _correct_eye_symmetry(lm68, mask)
            lm5_final = convert_to_face_landmark_5(lm68)
        else:
            lm68 = lm68_est
    except Exception:
        lm68 = None
    if lm68 is None:
        try:
            lm68 = estimate_face_landmark_68_5(lm5_raw)
        except Exception:
            lm68 = None
    return lm5_final, lm68


def is_iopaint_available() -> bool:
    try:
        base = os.environ.get('IOPAINT_URL', 'http://127.0.0.1:{}/api/v1/server-config'.format(IOPAINT_PORT))
        req = urllib.request.Request(base, method = 'GET')
        resp = urllib.request.urlopen(req, timeout = 5)
        return resp.status == 200
    except Exception:
        return False


def get_occlusion_mode() -> str:
    mode = state_manager.get_item('occlusion_mode') or 'remove'
    return mode


def load_manual_occlusion_mask(mask_path : str, height : int, width : int) -> np.ndarray:
    """把用户标注的遮挡转成 (height,width) 0/255 掩码。
    支持两种来源: 画笔合成图(红描边) 或 已填充的二值 mask PNG。"""
    if not mask_path or not is_file(mask_path):
        return None
    try:
        frame = read_image(mask_path)  # BGR
        h, w = frame.shape[: 2]
        r = frame[:, :, 2].astype(np.int16)
        g = frame[:, :, 1].astype(np.int16)
        b = frame[:, :, 0].astype(np.int16)
        strokes = ((r > 190) & (g < 110) & (b < 110)).astype(np.uint8) * 255
        if int((strokes > 0).sum()) < 30:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            strokes = (gray > 128).astype(np.uint8) * 255
        if int((strokes > 0).sum()) < 30:
            return None
        if (w, h) != (width, height):
            strokes = cv2.resize(strokes, (width, height), interpolation = cv2.INTER_NEAREST)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        strokes = cv2.dilate(strokes, kernel, iterations = 1)
        return strokes.astype(np.uint8)
    except Exception:
        return None


def preprocess_target_for_occlusion(image_path : str, user_mask_path : str = None) -> str:
    if get_occlusion_mode() == 'remove' and is_iopaint_available():
        return remove_occlusion(image_path, user_mask_path)
    return image_path


def ensure_detect_state() -> None:
    # 缺失这些状态时 resolve_download_url / inference_manager 会抛异常,
    # 而 detect_faces_robust 的回退逻辑会把它吞成"未检测到人脸"
    if not state_manager.get_item('download_providers'):
        state_manager.set_item('download_providers', [ 'huggingface' ])
    if not state_manager.get_item('execution_providers'):
        state_manager.set_item('execution_providers', [ 'cpu' ])
    if state_manager.get_item('execution_device_ids') is None:
        state_manager.set_item('execution_device_ids', [ -1 ])
    if state_manager.get_item('execution_device_id') is None:
        state_manager.set_item('execution_device_id', state_manager.get_item('execution_device_ids')[0])
    if state_manager.get_item('face_detector_margin') is None:
        state_manager.set_item('face_detector_margin', (0, 0, 0, 0))
    if state_manager.get_item('face_detector_score') is None:
        state_manager.set_item('face_detector_score', 0.5)


def detect_faces_robust(vision_frame : VisionFrame) -> Tuple[List, List, List]:
    original_model = state_manager.get_item('face_detector_model')
    original_size = state_manager.get_item('face_detector_size')
    boxes : List = []
    scores : List = []
    landmarks : List = []

    ensure_detect_state()

    try:
        for face_detector_model in [ 'retinaface', 'yolo_face', 'scrfd' ]:
            try:
                state_manager.set_item('face_detector_model', face_detector_model)
                state_manager.set_item('face_detector_size', '640x640')
                model_boxes, model_scores, model_landmarks = detect_faces(vision_frame)
                if model_boxes:
                    boxes = model_boxes
                    scores = model_scores
                    landmarks = model_landmarks
                    break
            except Exception:
                continue
    finally:
        if original_model is not None:
            state_manager.set_item('face_detector_model', original_model)
        if original_size is not None:
            state_manager.set_item('face_detector_size', original_size)
    return boxes, scores, landmarks


def build_occlusion_mask(vision_frame : VisionFrame, box, face_landmark_5 = None) -> np.ndarray:
    # 生成整图修复 mask: 255=需要修复(贴纸/刘海等遮挡物)
    # 策略: 从下巴区估计本地肤色, 用 YCrCb 距离标记「明显偏离皮肤」的像素(彩色贴纸/发色),
    # 再并上亮度信号(白色贴纸)。不依赖写死的肤色区间, 对各种色调/白平衡都稳健。
    # 只修补贴纸区域并保留下巴作为换脸的人脸检测锚点。
    height, width = vision_frame.shape[: 2]
    x1 = max(0, int(box[0]))
    y1 = max(0, int(box[1]))
    x2 = min(width, int(box[2]))  # detect_faces 返回绝对坐标 [x1,y1,x2,y2]
    y2 = min(height, int(box[3]))
    face_w = x2 - x1
    face_h = y2 - y1

    window_x1 = max(0, x1 - int(face_w * 0.15))
    window_y1 = max(0, y1 - int(face_h * 0.15))
    window_x2 = min(width, x2 + int(face_w * 0.15))
    window_y2 = min(height, y2 + int(face_h * 0.15))

    ycrcb = cv2.cvtColor(vision_frame, cv2.COLOR_BGR2YCrCb).astype(np.int16)
    y_ch, cr_ch, cb_ch = ycrcb[:, :, 0], ycrcb[:, :, 1], ycrcb[:, :, 2]

    # ---- 本地肤色估计: 下巴中央条带(0.82 ~ 1.0) ----
    chin_y1 = y1 + int(face_h * 0.82)
    chin_x1 = x1 + int(face_w * 0.20)
    chin_x2 = x2 - int(face_w * 0.20)
    if chin_y1 < y2 and chin_x2 > chin_x1:
        skin_y = int(np.median(y_ch[chin_y1:y2, chin_x1:chin_x2]))
        skin_cr = int(np.median(cr_ch[chin_y1:y2, chin_x1:chin_x2]))
        skin_cb = int(np.median(cb_ch[chin_y1:y2, chin_x1:chin_x2]))
    else:
        skin_y, skin_cr, skin_cb = 128, 128, 128

    # ---- 信号1: YCrCb 距离(彩色贴纸/发色遮挡) ----
    dist = np.sqrt((cr_ch - skin_cr) ** 2 + (cb_ch - skin_cb) ** 2) + 0.4 * np.abs(y_ch - skin_y)
    chin_dist = dist[chin_y1:y2, chin_x1:chin_x2]
    chin_p90 = float(np.percentile(chin_dist, 90)) if chin_dist.size > 0 else 30.0
    dist_threshold = max(30.0, chin_p90 * 1.6)

    color_mask = np.zeros((height, width), dtype = np.uint8)
    # 覆盖范围: 脸框+微扩展的窗口, 上缘到接近下巴条带(保留下巴作检测锚点)
    mask_y1 = window_y1
    mask_y2 = min(window_y2, chin_y1 - 2)
    if mask_y2 > mask_y1:
        region = dist[mask_y1:mask_y2, window_x1:window_x2] > dist_threshold
        color_mask[mask_y1:mask_y2, window_x1:window_x2][region] = 255

    # ---- 信号2: 亮度(白色/亮色贴纸) ----
    lab = cv2.cvtColor(vision_frame, cv2.COLOR_BGR2LAB)
    lightness = lab[:, :, 0].astype(np.int16)
    skin_median = int(np.median(lightness[y1:y2, x1:x2])) if face_h > 0 and face_w > 0 else 0
    bright_threshold = max(int(np.percentile(lightness[window_y1:window_y2, window_x1:window_x2], 95)), skin_median + 45)
    bright_mask = np.zeros((height, width), dtype = np.uint8)
    if window_y2 > window_y1 and window_x2 > window_x1:
        region = lightness[window_y1:window_y2, window_x1:window_x2] >= bright_threshold
        bright_mask[window_y1:window_y2, window_x1:window_x2][region] = 255

    # ---- 信号3: 高饱和彩色(蝴蝶结/贴纸等彩色遮挡, 其 YCrCb 可能与肤色接近) ----
    # 对象级方案: 在「脸框+边缘余量」窗口内找彩色连通域, 取面积最大的那个对象(贴纸),
    # 整体填满其包围盒(含黑边/描边/飘带), 避免因脸框截断导致对象不闭合或漏覆盖。
    hsv = cv2.cvtColor(vision_frame, cv2.COLOR_BGR2HSV).astype(np.int16)
    sat_ch = hsv[:, :, 1]
    hue_ch = hsv[:, :, 0]
    chin_x1 = x1 + int(face_w * 0.20)
    chin_x2 = x2 - int(face_w * 0.20)
    chin_sat = sat_ch[chin_y1:y2, chin_x1:chin_x2] if chin_y1 < y2 and chin_x2 > chin_x1 else None
    base_sat = int(np.median(chin_sat)) if chin_sat is not None and chin_sat.size > 0 else 40
    # 彩色候选: 高饱和, 且色相明显偏离皮肤肤色(红/粉/橙/黄), 用色相扇区约束
    hue_o = hue_ch.astype(np.int64)
    pink_hue = ((hue_o > 140) & (hue_o < 180)) | ((hue_o >= 0) & (hue_o < 20))
    warm_hue = (hue_o > 20) & (hue_o < 60)
    warm = (warm_hue | pink_hue) & (sat_ch > max(55, base_sat + 18))

    sat_mask = np.zeros((height, width), dtype = np.uint8)
    # 加宽窗口: 脸框 + %15 余量, 保证贴纸的飘带/边缘不因脸框截断而漏检
    wy1 = max(0, y1 - int(face_h * 0.15))
    wy2 = min(height, y2 + int(face_h * 0.12))
    wx1 = max(0, x1 - int(face_w * 0.22))
    wx2 = min(width, x2 + int(face_w * 0.22))
    if wy2 > wy1 and wx2 > wx1:
        local = warm[wy1:wy2, wx1:wx2]
        # 大闭运算把彩色主体连成完整闭合对象(蝴蝶结)
        fill_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        cand_fill = cv2.dilate(local.astype(np.uint8), fill_kernel, iterations = 3)
        cand_fill = cv2.morphologyEx(cand_fill, cv2.MORPH_CLOSE, np.ones((23, 23), np.uint8))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(cand_fill.astype(np.uint8), connectivity = 8)
        # 取面积最大的对象(贴纸主体); 尺寸超过脸框太多则视为背景跳过大块
        best_area = 0
        best_bbox = None
        for index in range(1, count):
            area = stats[index, cv2.CC_STAT_AREA]
            ow, oh = stats[index, 2], stats[index, 3]
            if oh > face_h * 1.25:
                continue
            if area > best_area:
                best_area = area
                best_bbox = (stats[index, 0] + wx1, stats[index, 1] + wy1, ow, oh)
        if best_bbox is not None:
            ox, oy, ow, oh = best_bbox
            # 略扩一点, 覆盖黑边/描边/飘带
            padx = int(max(ow, oh) * 0.06) + 8
            pady = padx
            sat_mask[max(0, oy - pady):min(height, oy + oh + pady), max(0, ox - padx):min(width, ox + ow + padx)] = 255

    # ---- 合并 ----
    min_area = max(20, int(face_w * face_h * 0.006))
    combined = remove_small_components(cv2.bitwise_or(cv2.bitwise_or(color_mask, bright_mask), sat_mask), min_area = min_area)
    if np.any(combined):
        count, labels, stats, _ = cv2.connectedComponentsWithStats(combined.astype(np.uint8), connectivity = 8)
        for index in range(1, count):
            bw, bh = stats[index, 2], stats[index, 3]
            if bw > face_w * 1.8 or bh > face_w * 2.4:
                combined[labels == index] = 0
    mask = combined
    mask_area = np.count_nonzero(mask)

    # 找不到时退回: 覆盖额头到上脸部的窄对称窗(避开下巴)
    if mask_area < min_area:
        cx = (x1 + x2) // 2
        half_w = int(face_w * 0.30)
        top_y = y1 + int(face_h * 0.05)
        bot_y = min(y1 + int(face_h * 0.60), chin_y1 - 2)
        mask = np.zeros((height, width), dtype = np.uint8)
        mask[top_y:bot_y, max(0, cx - half_w):min(width, cx + half_w)] = 255

    # 最终裁剪: 把修复区限制在【脸部框+小扩展窗口】内, 杜绝背景大块被选入。
    crop_x1 = max(0, x1 - int(face_w * 0.10))
    crop_y1 = max(0, y1 - int(face_h * 0.10))
    crop_x2 = min(width, x2 + int(face_w * 0.10))
    crop_y2 = min(height, chin_y1 - 1)  # 不到下巴, 保留换脸用的人脸检测锚点
    out_mask = np.zeros_like(mask)
    out_mask[crop_y1:crop_y2, crop_x1:crop_x2] = mask[crop_y1:crop_y2, crop_x1:crop_x2]
    mask = out_mask

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.dilate(mask, kernel, iterations = 1)
    return mask


def remove_small_components(mask : np.ndarray, min_area : int) -> np.ndarray:
    if not np.any(mask):
        return mask
    count, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), connectivity = 8)
    cleaned = np.zeros_like(mask)
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] >= min_area:
            cleaned[labels == index] = 255
    return cleaned


def remove_occlusion(image_path : str, user_mask_path : str = None) -> str:
    file_ext = get_file_extension(image_path) or '.png'
    output_path = image_path + '.oe' + file_ext
    if create_directory(CACHE_DIRECTORY):
        file_hash = hashlib.sha1(os.path.abspath(image_path).encode('utf-8')).hexdigest()[:8]
        output_path = os.path.join(CACHE_DIRECTORY, get_file_name(image_path) + '_' + file_hash + file_ext)
        if is_file(output_path) and os.path.getmtime(output_path) >= os.path.getmtime(image_path):
            load_cached_landmarks(output_path)
            return output_path

    ensure_detect_state()
    vision_frame : VisionFrame = read_image(image_path)
    if vision_frame is None:
        raise ValueError('无法读取图像: ' + image_path)
    height, width = vision_frame.shape[: 2]

    boxes, scores, landmarks = detect_faces_robust(vision_frame)
    if not boxes:
        raise ValueError('未检测到人脸，跳过遮挡去除')

    best_index = int(np.argmax(scores))
    box = boxes[best_index]

    # 先构建遮挡 mask: 用它校正被遮挡一侧的眼睛 landmark(避免换脸五官错位)。
    # 若用户手动描边了遮挡物, 用其作为修复掩码(IOPaint), 并补回自动mask做眼部对称校正。
    manual_mask = load_manual_occlusion_mask(user_mask_path, height, width)
    auto_mask = build_occlusion_mask(vision_frame, box)
    if manual_mask is not None:
        mask = manual_mask
        eye_corr_mask = auto_mask if auto_mask is not None and np.any(auto_mask) else manual_mask
    else:
        mask = auto_mask
        eye_corr_mask = mask
    if mask is None:
        raise ValueError('未生成遮挡掩码')

    # 缓存原始目标图的 landmark, 供换脸对齐复用(去遮挡后空白脸无法再检测出正确五官位置)
    lm5_final, lm68 = detect_target_landmarks(vision_frame, box, landmarks[best_index], mask = eye_corr_mask)
    cache_target_landmarks(output_path, box, lm5_final, lm68)

    mask_pil = Image.fromarray(mask)
    img_pil = Image.fromarray(cv2.cvtColor(vision_frame, cv2.COLOR_BGR2RGB))
    img_buffer = io.BytesIO()
    img_pil.save(img_buffer, format = 'PNG')
    mask_buffer = io.BytesIO()
    mask_pil.save(mask_buffer, format = 'PNG')

    payload = {
        'image': base64.b64encode(img_buffer.getvalue()).decode(),
        'mask': base64.b64encode(mask_buffer.getvalue()).decode(),
        'hd_strategy': 'Resize',
        'model': 'lama',
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(IOPAINT_URL, data = body, headers = { 'Content-Type': 'application/json' }, method = 'POST')
    try:
        resp = urllib.request.urlopen(req, timeout = 180)
        result = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError('IOPaint API 错误: {}'.format(e.code))
    except urllib.error.URLError as e:
        raise RuntimeError('无法连接 IOPaint 服务: {}'.format(e.reason))

    out = Image.open(io.BytesIO(result))
    out_rgb = out.convert('RGB')
    if file_ext in [ '.jpg', '.jpeg', '.webp' ]:
        out_rgb.save(output_path, quality = 95)
    else:
        out_rgb.save(output_path)
    return output_path

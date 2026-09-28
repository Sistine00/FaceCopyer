import os
from typing import Optional, Tuple

import cv2
import numpy

from facefusion import face_detector, face_landmarker, logger
from facefusion.face_helper import paste_back
from facefusion.types import Face, Matrix, VisionFrame

EXPRESSION_ALIGN_STRENGTH = 0.0  # 默认关闭：数值审计显示 inswapper 的表情几何本已贴合目标（嘴 2.6px/眼 1px），启用反而劣化；僵硬感来自纹理而非几何，建议用 face_enhancer
EXPRESSION_REGIONS = [ (48, 68) ]  # 若启用仅限嘴部：眉/眼位置与下颌轮廓多属身份特征，强拉会破相
SMOOTH_DETAIL_KEEP = 0.68  # 磨皮保留的皮肤纹理比例（1=不磨）
TONE_ALIGN_STRENGTH = 0.60  # 面部肤色向身体肤色对齐幅度


def is_enabled() -> bool:
    return os.environ.get('FACEFUSION_DISABLE_SMOOTHER') != '1'


def align_expression(crop_vision_frame : VisionFrame, target_face : Face, affine_matrix : Matrix) -> VisionFrame:
    """把换脸 crop 的表情几何对齐到目标脸原始表情：分段仿射形变，仅移动五官位置，纹理身份保留。"""
    if not is_enabled() or EXPRESSION_ALIGN_STRENGTH <= 0 or target_face.landmark_set.get('68') is None:
        return crop_vision_frame

    face_landmark_68 = target_face.landmark_set.get('68')
    reference_points = cv2.transform(face_landmark_68.reshape(1, -1, 2), affine_matrix).reshape(-1, 2)
    bounding_boxes, _, _ = face_detector.detect_faces(crop_vision_frame)

    if not bounding_boxes:
        return crop_vision_frame
    source_points, _ = face_landmarker.detect_face_landmark(crop_vision_frame, bounding_boxes[0], 0)
    source_points = numpy.array(source_points).reshape(-1, 2)

    region_strength = numpy.zeros(len(source_points), numpy.float32)
    for start, end in EXPRESSION_REGIONS:
        region_strength[start:end] = EXPRESSION_ALIGN_STRENGTH
    displacements = (reference_points - source_points) * region_strength[:, None]
    return _flow_warp(crop_vision_frame, source_points, displacements)


def apply_post_smooth(temp_vision_frame : VisionFrame, crop_mask : VisionFrame, affine_matrix : Matrix) -> VisionFrame:
    """磨皮 + 色调统一：面部肤色向身体真实肤色对齐，全图皮肤保边磨皮；非皮肤区域逐像素不变。"""
    if not is_enabled():
        return temp_vision_frame

    height, width = temp_vision_frame.shape[:2]
    channels = temp_vision_frame.shape[2] if temp_vision_frame.ndim == 3 else 3
    pasted = temp_vision_frame[..., :3].copy()

    inverse_matrix = cv2.invertAffineTransform(affine_matrix)
    face_ellipse = numpy.clip(cv2.warpAffine(crop_mask.astype(numpy.float32), inverse_matrix, (width, height)), 0, 1)

    skin_mask = _create_skin_mask(pasted)
    if skin_mask is None:
        return temp_vision_frame
    distance = cv2.distanceTransform(skin_mask, cv2.DIST_L2, 5)
    skin_soft = numpy.clip(distance / 12.0, 0, 1)  # 内侧羽化：皮肤边界=0，皮肤外恒0

    smoothed = _unify_tone(pasted, skin_mask, skin_soft, face_ellipse)
    smoothed = _smooth_skin(smoothed, skin_soft)
    blend = numpy.maximum(skin_soft, face_ellipse)[..., None]
    result = (smoothed.astype(numpy.float32) * blend + pasted.astype(numpy.float32) * (1 - blend)).round().astype(numpy.uint8)

    if channels == 4:
        result = numpy.concatenate([result, temp_vision_frame[..., 3:4]], axis = -1)
    return result


def _unify_tone(vision_frame : VisionFrame, skin_mask : VisionFrame, skin_soft : numpy.ndarray, face_ellipse : numpy.ndarray) -> VisionFrame:
    """Lab 空间把换脸区皮肤色调对齐到颈/肩/臂等身体真实肤色。"""
    lab = cv2.cvtColor(vision_frame, cv2.COLOR_BGR2LAB).astype(numpy.float32)
    lightness, a_channel, b_channel = lab[..., 0], lab[..., 1], lab[..., 2]

    reference_select = (skin_mask > 0) & (face_ellipse < 0.1)
    face_select = (skin_mask > 0) & (face_ellipse > 0.3)

    if reference_select.sum() < 500 or face_select.sum() < 500:
        return vision_frame

    ref_a, ref_b = a_channel[reference_select].mean(), b_channel[reference_select].mean()
    face_a, face_b = a_channel[face_select].mean(), b_channel[face_select].mean()
    weight = skin_soft * face_ellipse * TONE_ALIGN_STRENGTH
    a_channel += (ref_a - face_a) * weight
    b_channel += (ref_b - face_b) * weight
    lab = numpy.stack([lightness, a_channel, b_channel], axis = -1)
    return cv2.cvtColor(numpy.clip(lab, 0, 255).astype(numpy.uint8), cv2.COLOR_LAB2BGR)


def _smooth_skin(vision_frame : VisionFrame, skin_soft : numpy.ndarray) -> VisionFrame:
    """保边磨皮：L 通道双边滤波，保留 SMOOTH_DETAIL_KEEP 比例的细节纹理。"""
    lab = cv2.cvtColor(vision_frame, cv2.COLOR_BGR2LAB)
    lightness = lab[..., 0]
    base = cv2.bilateralFilter(lightness, 9, 30, 30)
    detail = lightness.astype(numpy.float32) - base.astype(numpy.float32)
    smooth = numpy.clip(base.astype(numpy.float32) + detail * SMOOTH_DETAIL_KEEP, 0, 255)
    lab[..., 0] = (lightness.astype(numpy.float32) * (1 - skin_soft) + smooth * skin_soft).astype(numpy.uint8)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def _create_skin_mask(vision_frame : VisionFrame) -> Optional[numpy.ndarray]:
    """YCrCb 肤色检测 + 形态学清理 + 小连通域剔除（避免误伤米白背景）。"""
    ycrcb = cv2.cvtColor(vision_frame, cv2.COLOR_BGR2YCrCb)
    y_channel, cr_channel, cb_channel = cv2.split(ycrcb)
    skin = ((cr_channel > 133) & (cr_channel < 185) & (cb_channel > 77) & (cb_channel < 172) &
            (y_channel > 60) & (y_channel < 235)).astype(numpy.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    skin = cv2.morphologyEx(skin, cv2.MORPH_OPEN, kernel)
    skin = cv2.morphologyEx(skin, cv2.MORPH_CLOSE, kernel)
    total, labels, stats, _ = cv2.connectedComponentsWithStats(skin, 8)
    min_area = vision_frame.shape[0] * vision_frame.shape[1] * 0.002
    clean = numpy.zeros_like(skin)

    for i in range(1, total):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            clean[labels == i] = 1
    return clean if clean.sum() > 1000 else None


def _flow_warp(vision_frame : VisionFrame, source_points : numpy.ndarray, displacements : numpy.ndarray, sigma : float = 36.0) -> VisionFrame:
    """平滑位移场形变：每个关键点贡献一个高斯衰减位移，全图 remap 一次，无接缝无撕裂。"""
    if not numpy.any(displacements):
        return vision_frame

    height, width = vision_frame.shape[:2]
    grid_y, grid_x = numpy.mgrid[0:height, 0:width].astype(numpy.float32)
    flow_x = numpy.zeros((height, width), numpy.float32)
    flow_y = numpy.zeros((height, width), numpy.float32)
    weight = numpy.zeros((height, width), numpy.float32)

    for (px, py), (dx, dy) in zip(source_points, displacements):
        if dx == 0 and dy == 0:
            continue
        point_weight = numpy.exp(-((grid_x - px) ** 2 + (grid_y - py) ** 2) / (2 * sigma ** 2))
        flow_x += point_weight * dx
        flow_y += point_weight * dy
        weight += point_weight

    active = weight > 1e-3
    flow_x[active] /= weight[active]
    flow_y[active] /= weight[active]
    map_x = grid_x - flow_x  # 内容沿位移方向移动：out(x) = img(x - flow)
    map_y = grid_y - flow_y
    return cv2.remap(vision_frame, map_x, map_y, cv2.INTER_LINEAR, borderMode = cv2.BORDER_REFLECT)
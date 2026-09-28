import hashlib
import os
import shutil
import subprocess
import sys
from typing import Optional

from facefusion import logger, translator
from facefusion.filesystem import create_directory, get_file_extension, get_file_name, is_file, remove_file

CACHE_DIRECTORY = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '.webp_converted'))


def is_animated_webp(file_path : Optional[str]) -> bool:
	if is_file(file_path) and get_file_extension(file_path) == '.webp':
		try:
			from PIL import Image
			with Image.open(file_path) as image:
				return bool(getattr(image, 'is_animated', False))
		except (OSError, ValueError):
			return False
	return False


def resolve_target_path(target_path : Optional[str]) -> Optional[str]:
	if target_path and is_animated_webp(target_path):
		converted_path = convert_animated_webp(target_path)
		if converted_path:
			return converted_path
	return target_path


def convert_animated_webp(webp_path : str) -> Optional[str]:
	if create_directory(CACHE_DIRECTORY):
		file_hash = hashlib.sha1(os.path.abspath(webp_path).encode('utf-8')).hexdigest()[:8]
		output_path = os.path.join(CACHE_DIRECTORY, get_file_name(webp_path) + '_' + file_hash + '.mp4')

		if not is_file(output_path) or os.path.getmtime(output_path) < os.path.getmtime(webp_path):
			ffmpeg_path = get_ffmpeg_path()
			if not ffmpeg_path:
				logger.error(translator.get('webp_ffmpeg_missing'), __name__)
				return None
			logger.info(translator.get('webp_converting'), __name__)
			commands = [ ffmpeg_path, '-y', '-i', webp_path, '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', output_path ]
			try:
				subprocess.run(commands, stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL, check = True)
			except subprocess.CalledProcessError:
				logger.error(translator.get('webp_convert_failed'), __name__)
				remove_file(output_path)
				return None
		if is_file(output_path):
			logger.info(translator.get('webp_convert_succeeded').format(output_path = output_path), __name__)
			return output_path
	return None


def get_ffmpeg_path() -> Optional[str]:
	venv_ffmpeg_path = os.path.join(os.path.dirname(sys.executable), 'ffmpeg.exe')
	if is_file(venv_ffmpeg_path):
		return venv_ffmpeg_path
	return shutil.which('ffmpeg')

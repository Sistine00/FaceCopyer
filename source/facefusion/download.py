import os
import subprocess
import time
from functools import lru_cache
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from tqdm import tqdm

import facefusion.choices
from facefusion import curl_builder, logger, process_manager, state_manager, translator
from facefusion.filesystem import get_file_name, get_file_size, is_file, remove_file
from facefusion.hash_helper import validate_hash
from facefusion.types import Command, DownloadProvider, DownloadSet

# 建连超时时间。默认的 5 秒在受限网络下不足以完成 TLS 握手:
# 镜像站(如 hf-mirror.com)实测需要 20 秒左右才能响应, 会被误判为不可达,
# 于是模型 URL 解析成 None, 下载被静默跳过, 只报「源校验失败」。
CONNECT_TIMEOUT = 40

# 等待下载文件写满时的轮询间隔(秒)。原实现在这里纯忙等(没有任何休眠),
# 实测下载期间会持续占满一个 CPU 核心, 让整个界面都跟着发卡。
DOWNLOAD_POLL_INTERVAL = 0.2
# 断流判定: 平均速率连续低于 DOWNLOAD_SPEED_LIMIT 字节/秒达 DOWNLOAD_SPEED_TIME 秒,
# 就由 curl 中止本次传输(再走 --retry 重试)。阈值取 1 KB/s 是为了不误伤慢速线路 ——
# 实测最差的本机 github 直连也有 7 KB/s 左右。
DOWNLOAD_SPEED_LIMIT = 1024
DOWNLOAD_SPEED_TIME = 120


def open_curl(commands : List[Command]) -> subprocess.Popen[bytes]:
	commands = curl_builder.run(commands)
	return subprocess.Popen(commands, stdin = subprocess.PIPE, stdout = subprocess.PIPE)


def conditional_download(download_directory_path : str, urls : List[str]) -> None:
	for url in urls:
		download_file_name = os.path.basename(urlparse(url).path)
		download_file_path = os.path.join(download_directory_path, download_file_name)
		initial_size = get_file_size(download_file_path)
		download_size = get_static_download_size(url)

		if initial_size < download_size:
			with tqdm(total = download_size, initial = initial_size, desc = translator.get('downloading'), unit = 'B', unit_scale = True, unit_divisor = 1024, ascii = ' =', disable = state_manager.get_item('log_level') in [ 'warn', 'error' ]) as progress:
				commands = curl_builder.chain(
					curl_builder.download(url, download_file_path),
					curl_builder.set_timeout(CONNECT_TIMEOUT),
					curl_builder.set_retry(5),
					curl_builder.set_speed_guard(DOWNLOAD_SPEED_LIMIT, DOWNLOAD_SPEED_TIME)
				)

				process = open_curl(commands)
				current_size = initial_size
				progress.set_postfix(download_providers = state_manager.get_item('download_providers'), file_name = download_file_name)

				while current_size < download_size:
					# 先休眠再读进度。加了这一行之后下载期间不再占满 CPU 核心。
					time.sleep(DOWNLOAD_POLL_INTERVAL)
					if is_file(download_file_path):
						current_size = get_file_size(download_file_path)
						progress.update(current_size - progress.n)
					# curl 已退出说明这次传输结束了。文件还没写满就只可能是失败,
					# 这时必须跳出, 交给调用方走「源校验失败」的报错与清理流程;
					# 原实现在这里会无限空转, 整个请求永久挂住, 界面一直停在 processing。
					if process.poll() is not None:
						break


@lru_cache(maxsize = 64)
def get_static_download_size(url : str) -> int:
	commands = curl_builder.chain(
		curl_builder.ping(url),
		curl_builder.set_timeout(CONNECT_TIMEOUT)
	)

	process = open_curl(commands)
	lines = reversed(process.stdout.readlines())

	for line in lines:
		__line__ = line.decode().lower()
		if 'content-length:' in __line__:
			_, content_length = __line__.split('content-length:')
			return int(content_length)

	return 0


@lru_cache(maxsize = 64)
def ping_static_url(url : str) -> bool:
	commands = curl_builder.chain(
		curl_builder.ping(url),
		curl_builder.set_timeout(CONNECT_TIMEOUT)
	)

	process = open_curl(commands)
	process.communicate()
	return process.returncode == 0


def conditional_download_hashes(hash_set : DownloadSet) -> bool:
	hash_paths = [ hash_set.get(hash_key).get('path') for hash_key in hash_set.keys() ]

	process_manager.check()
	_, invalid_hash_paths = validate_hash_paths(hash_paths)
	if invalid_hash_paths:
		for index in hash_set:
			if hash_set.get(index).get('path') in invalid_hash_paths:
				invalid_hash_url = hash_set.get(index).get('url')
				if invalid_hash_url:
					download_directory_path = os.path.dirname(hash_set.get(index).get('path'))
					conditional_download(download_directory_path, [ invalid_hash_url ])

	valid_hash_paths, invalid_hash_paths = validate_hash_paths(hash_paths)

	for valid_hash_path in valid_hash_paths:
		valid_hash_file_name = get_file_name(valid_hash_path)
		logger.debug(translator.get('validating_hash_succeeded').format(hash_file_name = valid_hash_file_name), __name__)
	for invalid_hash_path in invalid_hash_paths:
		invalid_hash_file_name = get_file_name(invalid_hash_path)
		logger.error(translator.get('validating_hash_failed').format(hash_file_name = invalid_hash_file_name), __name__)

	if not invalid_hash_paths:
		process_manager.end()
	return not invalid_hash_paths


def conditional_download_sources(source_set : DownloadSet) -> bool:
	source_paths = [ source_set.get(source_key).get('path') for source_key in source_set.keys() ]

	process_manager.check()
	_, invalid_source_paths = validate_source_paths(source_paths)
	if invalid_source_paths:
		for index in source_set:
			if source_set.get(index).get('path') in invalid_source_paths:
				invalid_source_url = source_set.get(index).get('url')
				if invalid_source_url:
					download_directory_path = os.path.dirname(source_set.get(index).get('path'))
					conditional_download(download_directory_path, [ invalid_source_url ])

	valid_source_paths, invalid_source_paths = validate_source_paths(source_paths)

	for valid_source_path in valid_source_paths:
		valid_source_file_name = get_file_name(valid_source_path)
		logger.debug(translator.get('validating_source_succeeded').format(source_file_name = valid_source_file_name), __name__)
	for invalid_source_path in invalid_source_paths:
		invalid_source_file_name = get_file_name(invalid_source_path)
		logger.error(translator.get('validating_source_failed').format(source_file_name = invalid_source_file_name), __name__)

		if remove_file(invalid_source_path):
			logger.error(translator.get('deleting_corrupt_source').format(source_file_name = invalid_source_file_name), __name__)

	if not invalid_source_paths:
		process_manager.end()
	return not invalid_source_paths


def validate_hash_paths(hash_paths : List[str]) -> Tuple[List[str], List[str]]:
	valid_hash_paths = []
	invalid_hash_paths = []

	for hash_path in hash_paths:
		if is_file(hash_path):
			valid_hash_paths.append(hash_path)
		else:
			invalid_hash_paths.append(hash_path)

	return valid_hash_paths, invalid_hash_paths


def validate_source_paths(source_paths : List[str]) -> Tuple[List[str], List[str]]:
	valid_source_paths = []
	invalid_source_paths = []

	for source_path in source_paths:
		if validate_hash(source_path):
			valid_source_paths.append(source_path)
		else:
			invalid_source_paths.append(source_path)

	return valid_source_paths, invalid_source_paths


def resolve_download_url(base_name : str, file_name : str) -> Optional[str]:
	download_providers = state_manager.get_item('download_providers')

	for download_provider in download_providers:
		download_url = resolve_download_url_by_provider(download_provider, base_name, file_name)
		if download_url:
			return download_url

	return None


def resolve_download_url_by_provider(download_provider : DownloadProvider, base_name : str, file_name : str) -> Optional[str]:
	download_provider_value = facefusion.choices.download_provider_set.get(download_provider)

	for download_provider_url in download_provider_value.get('urls'):
		if ping_static_url(download_provider_url):
			return download_provider_url + download_provider_value.get('path').format(base_name = base_name, file_name = file_name)

	return None

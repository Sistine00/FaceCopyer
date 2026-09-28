import itertools
import shutil
from typing import List

from facefusion import metadata
from facefusion.types import Command


def run(commands : List[Command]) -> List[Command]:
	user_agent = metadata.get('name') + '/' + metadata.get('version')

	return [ shutil.which('curl'), '--user-agent', user_agent, '--location', '--silent', '--ssl-no-revoke' ] + commands


def chain(*commands : List[Command]) -> List[Command]:
	return list(itertools.chain(*commands))


def ping(url : str) -> List[Command]:
	return [ '-I', url ]


def download(url : str, download_file_path : str) -> List[Command]:
	return [ '--create-dirs', '--continue-at', '-', '--output', download_file_path, url ]


def set_timeout(timeout : int) -> List[Command]:
	return [ '--connect-timeout', str(timeout) ]


def set_retry(retry : int) -> List[Command]:
	return [ '--retry', str(retry) ]


def set_speed_guard(speed_limit : int, speed_time : int) -> List[Command]:
	# 平均速率连续低于 speed_limit 字节/秒达 speed_time 秒就中止本次传输。
	# curl 默认没有这个限制: 连接被中途掐断但不报错时会一直挂着,
	# 上层的等待循环也就永远退不出来, 界面会一直停在 processing。
	# 中止属于可重试错误, 会走 --retry 的退避重试。
	return [ '--speed-limit', str(speed_limit), '--speed-time', str(speed_time) ]

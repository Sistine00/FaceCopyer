"""启动前清理被占用的端口。

端口从 _facecopyer_config 读, 可以用来清界面端口, 也可以清去遮挡端口。
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _facecopyer_config as config


def find_listening_pids(port):
	"""返回监听指定端口的所有 PID(可能不止一个: IPv4 与 IPv6 各一个)。"""
	try:
		completed = subprocess.run(
			[ 'netstat', '-ano', '-p', 'TCP' ],
			capture_output = True,
			text = True,
			encoding = 'oem',
			errors = 'ignore'
		)
	except Exception:
		return []
	suffix = ':' + str(port)
	pids = set()
	for line in completed.stdout.splitlines():
		parts = line.split()
		if len(parts) >= 5 and parts[1].endswith(suffix) and parts[3].upper() == 'LISTENING':
			pids.add(parts[4])
	return sorted(pids)


def free_port(port, label = '端口'):
	"""结束占用该端口的进程, 返回被结束的 PID 列表。"""
	stopped = []
	for pid in find_listening_pids(port):
		try:
			subprocess.run([ 'taskkill', '/pid', pid, '/f' ], capture_output = True, timeout = 10)
			print('[INFO] {} {} 被 PID {} 占用, 已结束该进程'.format(label, port, pid))
			stopped.append(pid)
		except Exception:
			continue
	return stopped


def main():
	settings = config.get()
	free_port(settings.ui_port, '界面端口')
	free_port(settings.iopaint_port, '去遮挡端口')


if __name__ == '__main__':
	main()

from contextlib import contextmanager
from logging import ERROR, Handler, LogRecord, Logger, basicConfig, getLogger
from typing import Iterator, List

import facefusion.choices
from facefusion.common_helper import get_first, get_last
from facefusion.types import LogLevel


def init(log_level : LogLevel) -> None:
	basicConfig(format = '%(message)s')
	get_package_logger().setLevel(facefusion.choices.log_level_set.get(log_level))


def get_package_logger() -> Logger:
	return getLogger('facefusion')


def debug(message : str, module_name : str) -> None:
	get_package_logger().debug(create_message(message, module_name))


def info(message : str, module_name : str) -> None:
	get_package_logger().info(create_message(message, module_name))


def warn(message : str, module_name : str) -> None:
	get_package_logger().warning(create_message(message, module_name))


def error(message : str, module_name : str) -> None:
	get_package_logger().error(create_message(message, module_name))


def create_message(message : str, module_name : str) -> str:
	module_names = module_name.split('.')
	first_module_name = get_first(module_names)
	last_module_name = get_last(module_names)

	if first_module_name and last_module_name:
		return '[' + first_module_name.upper() + '.' + last_module_name.upper() + '] ' + message
	return message


def enable() -> None:
	get_package_logger().disabled = False


def disable() -> None:
	get_package_logger().disabled = True


@contextmanager
def capture_errors() -> Iterator[List[str]]:
	"""临时收集 ERROR 级别的日志消息, 用于把失败原因回显到界面上。

	处理器在 pre_process() 里发现条件不满足时(例如勾了唇形同步但源里没有音频),
	只写一条 error 日志然后返回 False, 界面上不会弹出任何提示, 用户点了开始会
	觉得「没有反应」。这里把这段期间产生的 error 消息抓出来, 交给调用方显示。
	返回的是列表本身, 退出上下文后仍可继续读取。
	"""
	messages : List[str] = []

	class ErrorSink(Handler):
		def emit(self, record : LogRecord) -> None:
			messages.append(record.getMessage())

	sink = ErrorSink(level = ERROR)
	package_logger = get_package_logger()
	package_logger.addHandler(sink)

	try:
		yield messages
	finally:
		package_logger.removeHandler(sink)

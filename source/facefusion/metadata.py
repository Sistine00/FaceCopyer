from typing import Optional

METADATA =\
{
	'name': 'FaceCopyer',
	'description': '本地离线换脸工具，支持图片与视频批量处理',
	'version': '1.0.0',
	'license': 'OpenRAIL-AS',
	'author': 'Sistine',
	'url': 'https://github.com/Sistine00/FaceCopyer'
}


def get(key : str) -> Optional[str]:
	return METADATA.get(key)

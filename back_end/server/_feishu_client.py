# back_end/server/_feishu_client.py
from library import *
from ._magnus_config import magnus_config
import sys


__all__ = [
    "feishu_client",
]


if "feishu_client" not in magnus_config.get("server", {}):
    error_msg = (
        "❌ 启动失败: 配置文件中缺少 'server.feishu_client' 字段。\n"
        "   请检查 configs/magnus_config.yaml 是否正确缩进。"
    )
    print(error_msg)
    sys.exit(1)

_config = magnus_config["server"]["feishu_client"]

required_keys = ["app_id", "app_secret"]
missing_keys = [key for key in required_keys if not _config.get(key)]

if missing_keys:
    raise RuntimeError(
        f"❌ 启动失败: 飞书配置不完整。\n"
        f"   缺少字段: {missing_keys}\n"
        f"   请在 magnus_config.yaml 中补全。"
    )

feishu_client = FeishuClient(
    app_id = _config["app_id"],
    app_secret = _config["app_secret"],
)
# back_end/server/_magnus_config.py
import sys
from library import *


__all__ = [
    "magnus_config",
]


def _load_magnus_config(
)-> Dict[str, Any]:
    
    magnus_project_root = Path(__file__).resolve().parent.parent.parent
    magnus_config_path = magnus_project_root / "configs" / "magnus_config.yaml"
    
    if not magnus_config_path.exists():
        raise FileNotFoundError(f"❌ 配置文件未找到: {magnus_config_path}")

    try:
        data = load_from_yaml(str(magnus_config_path))
        if "--deliver" not in sys.argv:
            data["server"]["front_end_port"] += 2
            data["server"]["back_end_port"] += 2
            data["server"]["root"] += "-develop"
        return data
    except Exception as error:
        raise RuntimeError(f"❌ 解析 YAML 失败: {error}\n调用栈：\n{traceback.format_exc()}")


magnus_config = _load_magnus_config()
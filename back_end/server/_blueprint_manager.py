import inspect
import logging
from typing import Any, Dict, List, Annotated, get_origin, get_args
from datetime import datetime
from pydantic import ValidationError

# 注入给 Blueprint 代码的上下文
from .models import JobType
from .schemas import JobSubmission, BlueprintParamSchema

logger = logging.getLogger(__name__)

class BlueprintManager:
    """
    负责解析用户编写的 Python Blueprint 代码，
    提取参数元数据（用于前端渲染），并执行代码生成 Job。
    """

    def __init__(self):
        # 定义 Blueprint 代码运行时的全局命名空间
        # 仅注入必要的类型和 helper，做最小限度的沙盒隔离
        self.execution_globals = {
            "JobSubmission": JobSubmission,
            "JobType": JobType,
            "Annotated": Annotated,
            "List": List,
            "Dict": Dict,
            "Any": Any,
        }

    def _compile_code(self, code: str) -> dict:
        """
        编译并执行代码定义，返回局部变量字典（包含函数定义）。
        """
        local_scope = {}
        try:
            exec(code, self.execution_globals, local_scope)
        except Exception as e:
            raise ValueError(f"Syntax Error in Blueprint: {e}")
        
        if "generate_job" not in local_scope:
            raise ValueError("Blueprint must define a function named 'generate_job'")
        
        return local_scope

    def analyze_signature(self, code: str) -> List[BlueprintParamSchema]:
        """
        静态分析 generate_job 函数的签名，生成前端表单 Schema。
        """
        local_scope = self._compile_code(code)
        func = local_scope["generate_job"]
        sig = inspect.signature(func)
        
        params_schema = []

        for name, param in sig.parameters.items():
            if name == "user_name": continue  # 自动注入参数，前端不可见

            schema = BlueprintParamSchema(
                key=name,
                label=name.replace("_", " ").title(), # simple title case
                type="text", # fallback
                default=param.default if param.default != inspect.Parameter.empty else None
            )

            # 解析类型注解 Annotated[type, metadata]
            annotation = param.annotation
            if get_origin(annotation) is Annotated:
                base_type, meta = get_args(annotation)
                
                # 1. 类型推断
                if base_type is int:
                    schema.type = "number"
                elif base_type is bool:
                    schema.type = "boolean"
                elif base_type is str:
                    schema.type = "text" # default
                
                # 2. 元数据提取 (metadata 应该是一个 dict)
                if isinstance(meta, dict):
                    if "label" in meta: schema.label = meta["label"]
                    if "description" in meta: schema.description = meta["description"]
                    if "min" in meta: schema.min = meta["min"]
                    if "max" in meta: schema.max = meta["max"]
                    if "options" in meta: 
                        schema.type = "select"
                        schema.options = meta["options"]
            
            # 普通类型推断 (非 Annotated)
            elif annotation is int:
                schema.type = "number"
            elif annotation is bool:
                schema.type = "boolean"

            params_schema.append(schema)
            
        return params_schema

    def execute(self, code: str, inputs: Dict[str, Any], context_user_name: str) -> JobSubmission:
        """
        执行 Blueprint，生成 JobSubmission 对象。
        """
        local_scope = self._compile_code(code)
        func = local_scope["generate_job"]
        
        # 注入系统级参数
        call_args = {**inputs}
        
        # 检查函数是否接受 user_name (向后兼容)
        sig = inspect.signature(func)
        if "user_name" in sig.parameters:
            call_args["user_name"] = context_user_name

        try:
            # 执行用户代码
            result = func(**call_args)
            
            # 校验返回结果
            if isinstance(result, dict):
                return JobSubmission(**result)
            elif isinstance(result, JobSubmission):
                return result
            else:
                raise ValueError(f"Blueprint returned {type(result)}, expected dict or JobSubmission")
                
        except TypeError as e:
            raise ValueError(f"Parameter mismatch: {e}")
        except ValidationError as e:
            raise ValueError(f"Generated Job data is invalid: {e}")
        except Exception as e:
            raise ValueError(f"Runtime Error in Blueprint: {e}")

blueprint_manager = BlueprintManager()
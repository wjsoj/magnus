# back_end/server/_blueprint_manager.py
import inspect
import logging
from typing import Any, Dict, List, Annotated, Literal, get_origin, get_args

from pydantic import ValidationError

from .models import JobType
from .schemas import JobSubmission, BlueprintParamSchema, BlueprintParamOption

logger = logging.getLogger(__name__)


class BlueprintManager:
    """
    负责解析用户编写的 Python Blueprint 代码，
    提取参数元数据（用于前端渲染），并执行代码生成 Job。
    """

    def __init__(self):
        self.execution_globals = {
            "JobSubmission": JobSubmission,
            "JobType": JobType,
            "Annotated": Annotated,
            "Literal": Literal,
            "List": List,
            "Dict": Dict,
            "Any": Any,
        }

    def _compile_code(self, code: str, extra_globals: Dict[str, Any]) -> dict:
        scope = self.execution_globals.copy()
        if extra_globals:
            scope.update(extra_globals)

        try:
            exec(code, scope, scope)
        except Exception as e:
            raise ValueError(f"Syntax Error in Blueprint: {e}")

        if "generate_job" not in scope:
            raise ValueError("Blueprint must define a function named 'generate_job'")

        return scope

    def analyze_signature(self, code: str) -> List[BlueprintParamSchema]:
        """静态分析 generate_job 函数的签名，生成丰富的前端表单 Schema。"""
        local_scope = self._compile_code(code, extra_globals={})
        func = local_scope["generate_job"]
        sig = inspect.signature(func)
        params_schema = []

        for name, param in sig.parameters.items():
            default_label = name.replace("_", " ").title()
            schema = BlueprintParamSchema(
                key=name,
                label=default_label,
                type="text",
                default=param.default if param.default != inspect.Parameter.empty else None,
            )

            # 解析 Annotated 元数据
            annotation = param.annotation
            base_type = annotation
            meta_dict = {}

            if get_origin(annotation) is Annotated:
                args = get_args(annotation)
                base_type = args[0]
                for arg in args[1:]:
                    if isinstance(arg, dict):
                        meta_dict.update(arg)

            if "label" in meta_dict:
                schema.label = meta_dict["label"]
            if "description" in meta_dict:
                schema.description = meta_dict["description"]
            if "scope" in meta_dict:
                schema.scope = meta_dict["scope"]

            # 类型分支处理
            origin_base = get_origin(base_type)

            # --- Integer ---
            if base_type is int:
                schema.type = "number"
                if "min" in meta_dict: schema.min = meta_dict["min"]
                if "max" in meta_dict: schema.max = meta_dict["max"]
                if "step" in meta_dict: schema.step = meta_dict["step"]

            # --- Boolean ---
            elif base_type is bool:
                schema.type = "boolean"

            # --- String ---
            elif base_type is str:
                schema.type = "text"
                if "placeholder" in meta_dict: schema.placeholder = meta_dict["placeholder"]
                if "color" in meta_dict: schema.color = meta_dict["color"]
                if "border_color" in meta_dict: schema.border_color = meta_dict["border_color"]
                if "multi_line" in meta_dict: schema.multi_line = bool(meta_dict["multi_line"])

            # --- Literal (Select) ---
            elif origin_base is Literal:
                schema.type = "select"
                allowed_values = get_args(base_type)
                meta_options = meta_dict.get("options", {})
                schema_options = []

                for val in allowed_values:
                    opt_label = str(val)
                    opt_desc = None

                    if isinstance(meta_options, dict) and val in meta_options:
                        info = meta_options[val]
                        if isinstance(info, dict):
                            opt_label = info.get("label", str(val))
                            opt_desc = info.get("description")
                        elif isinstance(info, str):
                            opt_label = info

                    schema_options.append(BlueprintParamOption(
                        label=opt_label,
                        value=val,
                        description=opt_desc
                    ))
                schema.options = schema_options

            params_schema.append(schema)

        return params_schema

    def execute(self, code: str, inputs: Dict[str, Any]) -> JobSubmission:
        local_scope = self._compile_code(code, extra_globals={})
        func = local_scope["generate_job"]
        sig = inspect.signature(func)
        call_args = {k: v for k, v in inputs.items() if k in sig.parameters}

        try:
            result = func(**call_args)
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
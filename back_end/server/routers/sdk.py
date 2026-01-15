# back_end/server/routers/sdk.py
import logging
from typing import Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session
from .. import database
from .. import models
from .._blueprint_manager import blueprint_manager
from ..routers.auth import get_current_user
from library.fundamental.json_tools import deserialize_json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sdk")

# === SDK Dedicated Schema ===
class SDKBlueprintSubmitRequest(BaseModel):
    """
    专门服务于 SDK submit_blueprint(**kwargs) 的请求体
    """
    use_preference: bool = True
    # 对应 SDK 中的 **kwargs，由 SDK 客户端打包成字典传入
    parameters: Dict[str, Any] = {}


@router.post("/blueprints/{blueprint_id}/submit")
def submit_blueprint_sdk(
    blueprint_id: str,
    request: SDKBlueprintSubmitRequest,
    db: Session = Depends(database.get_db),
    # 复用 auth.py 的混合鉴权 (支持 SDK Token)
    current_user: models.User = Depends(get_current_user), 
):
    """
    [Group A & B Support]
    SDK 提交接口：
    1. 获取蓝图
    2. 融合用户偏好 (Preference Merging)
    3. 执行蓝图生成 Job 配置
    4. 写入数据库 (Fire & Forget)
    """
    # 1. 获取蓝图
    bp = db.query(models.Blueprint).filter(models.Blueprint.id == blueprint_id).first()
    if not bp:
        raise HTTPException(status_code=404, detail=f"Blueprint {blueprint_id} not found")

    # 2. 参数融合逻辑 (The Merge Logic)
    final_params = request.parameters.copy()
    
    if request.use_preference:
        # 查用户偏好
        pref = db.query(models.BlueprintUserPreference).filter(
            models.BlueprintUserPreference.user_id == current_user.id,
            models.BlueprintUserPreference.blueprint_id == blueprint_id,
        ).first()
        
        if pref:
            try:
                # Base: 偏好设置
                cached = deserialize_json(pref.cached_params)
                if isinstance(cached, dict):
                    # Logic: SDK 显式传入的参数 (Override) 覆盖 偏好参数 (Base)
                    # Ex: Pref={epoch:100}, SDK={epoch:200} -> Final={epoch:200}
                    base_params = cached.copy()
                    base_params.update(final_params)
                    final_params = base_params
            except Exception as e:
                logger.warning(f"Failed to merge preferences for user {current_user.id}: {e}")
                # Fallback: 仅使用传入参数

    # 3. 执行 (复用 Blueprint Manager)
    try:
        job_submission = blueprint_manager.execute(
            bp.code,
            final_params,
        )
        
        job_dict = job_submission.model_dump()

        db_job = models.Job(
            **job_dict,
            user_id=current_user.id,
            status=models.JobStatus.PENDING,
        )

        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        
        logger.info(f"[SDK] User {current_user.name} submitted Job {db_job.id} via Blueprint {blueprint_id}")
        
        return {"job_id": db_job.id}

    except Exception as e:
        logger.error(f"[SDK] Submit failed for Blueprint {blueprint_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
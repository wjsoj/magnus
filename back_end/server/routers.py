# back_end/server/routers.py
import os
import jwt
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import or_

from library import *
from . import database
from . import models
from .models import JobStatus, JobType
from .schemas import *
from ._github_client import github_client
from ._jwt_signer import jwt_signer
from ._feishu_client import feishu_client
from ._magnus_config import magnus_config


__all__ = [
    "router",
]


logger = logging.getLogger(__name__)
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/feishu/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(database.get_db)
) -> models.User:
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            token, 
            magnus_config["server"]["jwt_signer"]["secret_key"], 
            algorithms=[magnus_config["server"]["jwt_signer"]["algorithm"]]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
        
    return user


# ================= GitHub Routes =================


@router.get("/github/{ns}/{repo}/branches")
async def get_branches(ns: str, repo: str):
    branches = await github_client.fetch_branches(ns, repo)
    if not branches:
        raise HTTPException(
            status_code=404, 
            detail = "Repo not found or empty",
        )
    return branches


@router.get("/github/{ns}/{repo}/commits")
async def get_commits(
    ns: str, 
    repo: str, 
    branch: str,
):
    return await github_client.fetch_commits(ns, repo, branch)


# ================= Job Routes =================


@router.post(
    "/jobs/submit", 
    response_model = JobResponse,
)
async def submit_job(
    job_data: JobSubmission, 
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    提交新任务。
    注意：此接口不再直接与 SLURM 交互，只负责写入数据库 (PENDING)。
    后台 Scheduler 会自动处理排队/抢占逻辑。
    """
    job_dict = job_data.model_dump()
    
    db_job = models.Job(
        **job_dict, 
        user_id=current_user.id,
        status=JobStatus.PENDING 
    )
    
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    
    return db_job


@router.get(
    "/jobs", 
    response_model = PagedJobResponse,
)
async def get_jobs(
    skip: int = 0, 
    limit: int = 100, 
    search: Optional[str] = None,
    creator_id: Optional[str] = None,
    db: Session = Depends(database.get_db),
):
    query = db.query(models.Job)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                models.Job.task_name.ilike(search_pattern),
                models.Job.id.ilike(search_pattern)
            )
        )
    
    if creator_id and creator_id != "all":
        query = query.filter(models.Job.user_id == creator_id)

    total = query.count()

    jobs = query.order_by(models.Job.created_at.desc())\
            .offset(skip).limit(limit).all()
            
    return {"total": total, "items": jobs}


@router.get(
    "/jobs/{job_id}",
    response_model = JobResponse,
)
async def get_job_detail(
    job_id: str,
    db: Session = Depends(database.get_db),
):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get(
    "/jobs/{job_id}/logs"
)
async def get_job_logs(
    job_id: str,
    db: Session = Depends(database.get_db),
):
    """
    获取任务实时日志 (直接读取 Slurm output 文件)
    """
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    root_path = magnus_config['server']['root']
    log_path = f"{root_path}/workspace/jobs/{job_id}/slurm/output.txt"

    if not os.path.exists(log_path):
        return {"logs": "Waiting for output stream... (Job might be PENDING or Initializing)"}

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"logs": content}
        
    except Exception as e:
        logger.error(f"Error reading log file for {job_id}: {e}")
        return {"logs": f"Error reading logs: {str(e)}"}


@router.post("/jobs/{job_id}/terminate")
async def terminate_job(
    job_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    用户主动终止任务：scancel + DB状态更新
    """
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.user_id != current_user.id:
         raise HTTPException(status_code=403, detail="Not authorized to terminate this job")

    if job.slurm_job_id:
        try:
            manager = SlurmManager()
            manager.kill_job(job.slurm_job_id)
        except Exception as e:
            logger.warning(f"Failed to kill Slurm job {job.slurm_job_id}: {e}")

    job.status = models.JobStatus.TERMINATED
    db.commit()
    db.refresh(job)
    
    return {"message": "Job terminated", "status": job.status}


# ================= Cluster & Dashboard Routes =================


def _scheduler_sort_key(job):
    """
    复刻调度器排序逻辑：优先级 (A1>A2>B1>B2) > 时间 (FIFO)
    """
    priority_map = {
        JobType.A1: 4, JobType.A2: 3,
        JobType.B1: 2, JobType.B2: 1,
    }
    p_score = priority_map.get(job.job_type, 0)
    return (p_score, -job.created_at.timestamp())


@router.get(
    "/cluster/stats",
    response_model=ClusterStatsResponse,
)
async def get_cluster_stats(
    db: Session = Depends(database.get_db),
):
    # 1. Running Jobs (按开始时间倒序，最新跑的在上面)
    running_jobs_orm = db.query(models.Job).filter(
        models.Job.status == JobStatus.RUNNING
    ).order_by(models.Job.start_time.desc()).all()

    # 2. Pending Jobs (复刻调度器逻辑)
    pending_jobs_orm = db.query(models.Job).filter(
        models.Job.status.in_([JobStatus.PENDING, JobStatus.PAUSED])
    ).all()
    
    pending_jobs_orm.sort(key=_scheduler_sort_key, reverse=True)

    # 显式手动转换为 Pydantic 模型，触发懒加载
    running_jobs = [JobResponse.model_validate(job) for job in running_jobs_orm]
    pending_jobs = [JobResponse.model_validate(job) for job in pending_jobs_orm]

    # --- 资源计算 (Magnus 视角) ---
    slurm_manager = SlurmManager()
    
    # n1: Slurm 系统级空闲
    n1_free = slurm_manager.get_cluster_free_gpus()
    
    # n2: Magnus 平台正在使用的 GPU (累加 Running 任务的 gpu_count)
    n2_used = sum(job.gpu_count for job in running_jobs_orm)
    
    # 动态总算力 = 当前 Magnus 用掉的 + 剩余还能抢的
    display_total = n1_free + n2_used

    return {
        "resources": {
            "node": "liustation",
            "gpu_model": "RTX 5090",
            "total": display_total,
            "free": n1_free,
            "used": n2_used,
        },
        "running_jobs": running_jobs,
        "pending_jobs": pending_jobs,
    }


@router.get("/dashboard/my-active-jobs", response_model=List[JobResponse])
async def get_my_active_jobs(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Dashboard 专用：获取当前用户“活跃”的任务
    逻辑：Running 在顶端(按开始时间)，Pending/Paused 在下方(按调度优先级)
    """
    
    # 1. 获取 Running 任务
    running_orm = db.query(models.Job).filter(
        models.Job.user_id == current_user.id,
        models.Job.status == JobStatus.RUNNING
    ).order_by(models.Job.start_time.desc()).all()
    
    # 2. 获取排队任务
    queued_orm = db.query(models.Job).filter(
        models.Job.user_id == current_user.id,
        models.Job.status.in_([JobStatus.PENDING, JobStatus.PAUSED])
    ).all()
    
    # 3. 对排队任务应用调度排序
    queued_orm.sort(key=_scheduler_sort_key, reverse=True)
    
    # 4. 合并并强制序列化 (User 懒加载)
    all_jobs_orm = running_orm + queued_orm
    
    return [JobResponse.model_validate(job) for job in all_jobs_orm]


# ================= Auth Routes =================


@router.post(
    "/auth/feishu/login",
    response_model=LoginResponse,
)
async def feishu_login(
    req: FeishuLoginRequest, 
    db: Session = Depends(database.get_db),
):
    try:
        feishu_user = await feishu_client.get_feishu_user(req.code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    open_id = feishu_user.get("open_id") or feishu_user.get("union_id")
    if not open_id:
        raise HTTPException(status_code=400, detail="Missing OpenID")

    db_user = db.query(models.User).filter(models.User.feishu_open_id == open_id).first()

    if not db_user:
        db_user = models.User(
            feishu_open_id=open_id,
            name=feishu_user.get("name", "Unknown"),
            avatar_url=feishu_user.get("avatar_url"),
            email=feishu_user.get("email")
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    else:
        db_user.name = feishu_user.get("name", db_user.name)
        db_user.avatar_url = feishu_user.get("avatar_url", db_user.avatar_url)
        db.commit()
        db.refresh(db_user)

    access_token = jwt_signer.create_access_token(payload={"sub": db_user.id})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": db_user,
    }


@router.get(
    "/users",
    response_model=List[UserInfo],
)
async def get_users(
    db: Session = Depends(database.get_db),
):
    users = db.query(models.User).order_by(models.User.name).all()
    return users
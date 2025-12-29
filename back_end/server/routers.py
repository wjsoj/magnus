# back_end/server/routers.py
import os
import jwt
import json
import httpx
import secrets
import logging
import asyncio
import random
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import or_

from library import *
from . import database
from . import models
from .models import *
from .schemas import *
from ._github_client import github_client
from ._jwt_signer import jwt_signer
from ._feishu_client import feishu_client
from ._magnus_config import magnus_config
from ._scheduler import scheduler
from ._slurm_manager import SlurmManager
from ._blueprint_manager import blueprint_manager
from ._service_manager import service_manager

__all__ = [
    "router",
]

logger = logging.getLogger(__name__)
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/feishu/login")


def generate_trust_token()-> str:
    return f"sk-{secrets.token_urlsafe(24)}"


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(database.get_db)
)-> models.User:
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
            detail="Repo not found or empty",
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
    response_model=JobResponse,
)
async def submit_job(
    job_data: JobSubmission,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    提交新任务。
    注意：此接口只负责将任务写入数据库并标记为 PENDING。
    后续的资源检查、抢占决策和 sbatch 提交由后台 _scheduler.py 负责。
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
    response_model=PagedJobResponse,
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
    response_model=JobResponse,
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
    获取任务实时日志。
    为了防止内存溢出，限制最大读取 1MB。
    """
    # 设定阈值：1MB
    MAX_LOG_SIZE = 1 * 1024 * 1024

    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    root_path = magnus_config['server']['root']
    log_path = f"{root_path}/workspace/jobs/{job_id}/slurm/output.txt"

    if not os.path.exists(log_path):
        if job.status == JobStatus.FAILED:
            effective_user = job.runner if job.runner is not None else "magnus"
            return {
                "logs": (
                    "Job has failed for systematic reasons. "
                    f"Please check if you have access to user {effective_user} on liustation2."
                )
            }
        return {"logs": "Waiting for output stream... (Job might be PENDING or Initializing)"}

    try:
        file_size = os.path.getsize(log_path)

        # 情况 A: 文件过大，只读最后 1MB
        if file_size > MAX_LOG_SIZE:
            with open(log_path, "rb") as f:  # 使用二进制模式以便 seek
                f.seek(-MAX_LOG_SIZE, os.SEEK_END)  # 倒退 1MB
                content_bytes = f.read()
                # decode 时使用 ignore 或 replace，防止切割点刚好在中文多字节中间导致乱码
                content = content_bytes.decode("utf-8", errors="replace")

                header = f"[Magnus Warning] Log file is too large ({file_size/1024/1024:.2f}MB). Showing last 1MB only...\n\n"
                return {"logs": header + content}

        # 情况 B: 文件较小，直接全读
        else:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                return {"logs": f.read()}

    except Exception as e:
        logger.error(f"Error reading log file for {job_id}: {e}")
        return {"logs": f"Error reading logs: {str(e)}"}


@router.get(
    "/jobs/{job_id}/metrics",
)
async def get_job_metrics(
    job_id: str,
    db: Session = Depends(database.get_db),
)-> List[Dict[str, Any]]:
    latest_metric: Optional[models.JobMetric] = db.query(models.JobMetric)\
        .filter(models.JobMetric.job_id == job_id)\
        .order_by(models.JobMetric.timestamp.desc())\
        .first()

    if not latest_metric:
        return []

    try:
        metrics: List[Dict[str, Any]] = json.loads(latest_metric.status_json)
        # 映射后端 utilization_gpu 到前端预期的 utilization 字段
        formatted_metrics = [
            {
                "index": m.get("index"),
                "utilization": m.get("utilization_gpu", 0),
            }
            for m in metrics
        ]
        return formatted_metrics

    except Exception as e:
        logger.error(f"Failed to parse metrics for job {job_id}: {e}")
        return []


@router.post("/jobs/{job_id}/terminate")
async def terminate_job(
    job_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    用户主动终止任务。
    调用 Scheduler 的 terminate_job 方法以确保资源清理和状态更新的一致性。
    """
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to terminate this job")

    try:
        await asyncio.to_thread(
            scheduler.terminate_job,
            db, job,
        )
    except Exception as e:
        logger.error(f"Error terminating job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to terminate job")

    db.refresh(job)

    return {"message": "Job terminated", "status": job.status}


# ================= Cluster & Dashboard Routes =================


def _scheduler_sort_key(job):
    """
    复刻调度器排序逻辑：优先级 (A1>A2>B1>B2) > 时间 (FIFO)
    保持此逻辑与 _scheduler.py 一致至关重要，否则前端展示顺序会误导用户
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
    running_skip: int = 0,
    running_limit: int = 10,
    pending_skip: int = 0,
    pending_limit: int = 10,
    db: Session = Depends(database.get_db),
):
    # --- 1. 获取 Slurm 真实数据 ---
    slurm_manager = SlurmManager()
    all_slurm_tasks = slurm_manager.get_all_running_tasks()

    running_slurm_ids = [task["id"] for task in all_slurm_tasks]

    # --- 2. 数据库元数据匹配 ---
    magnus_jobs_orm = []
    if running_slurm_ids:
        magnus_jobs_orm = db.query(models.Job).filter(
            models.Job.slurm_job_id.in_(running_slurm_ids)
        ).all()

    magnus_job_map = {job.slurm_job_id: job for job in magnus_jobs_orm}

    # --- 3. 构造最终列表 ---
    all_running_jobs: List[JobResponse] = []

    for task in all_slurm_tasks:
        slurm_id = task["id"]

        if slurm_id in magnus_job_map:
            # Case A: Magnus 任务
            job_orm = magnus_job_map[slurm_id]
            job_resp = JobResponse.model_validate(job_orm)
            job_resp.status = JobStatus.RUNNING
            all_running_jobs.append(job_resp)

        else:
            # Case B: External 任务
            mock_user = UserInfo(
                id=f"slurm_{task['user']}",
                name=f"{task['user']} (slurm)",
                avatar_url="/images/slurm_avatar.png",
                email=None,
            )

            try:
                start_dt = datetime.fromisoformat(task["start_time"])
            except ValueError:
                start_dt = datetime.now()

            mock_job = JobResponse(
                task_name=task["name"],
                description="External slurm task",
                namespace="External",
                repo_name="N/A",
                branch="N/A",
                commit_sha="N/A",
                entry_command="<binary execution>",
                gpu_type=task["gpu_type"].lower().replace(" ", ""),
                gpu_count=task["gpu_count"],
                job_type=JobType.EXTERNAL,

                id=f"{slurm_id} (slurm)",
                user_id=mock_user.id,
                status=JobStatus.RUNNING,
                slurm_job_id=slurm_id,
                start_time=start_dt,
                created_at=start_dt,
                user=mock_user,
            )
            all_running_jobs.append(mock_job)

    # --- 4. 排序 & 资源计算 (基于全量数据) ---
    magnus_group = [j for j in all_running_jobs if j.job_type != JobType.EXTERNAL]
    external_group = [j for j in all_running_jobs if j.job_type == JobType.EXTERNAL]

    magnus_group.sort(key=lambda x: x.start_time or datetime.min, reverse=True)
    external_group.sort(key=lambda x: x.start_time or datetime.min, reverse=True)

    sorted_all_running = magnus_group + external_group

    # 计算资源 (必须使用分页前的全量数据)
    n1_free = slurm_manager.get_cluster_free_gpus()
    n2_used = sum(job.gpu_count for job in sorted_all_running)
    display_total = n1_free + n2_used

    # --- 5. Running 列表分页切片 ---
    total_running = len(sorted_all_running)
    paginated_running = sorted_all_running[running_skip : running_skip + running_limit]

    # --- 6. Pending Jobs 处理与分页 ---
    pending_jobs_orm = db.query(models.Job).filter(
        models.Job.status.in_([JobStatus.PENDING, JobStatus.PAUSED])
    ).all()

    # 保持原有调度器排序逻辑
    pending_jobs_orm.sort(key=_scheduler_sort_key, reverse=True)

    total_pending = len(pending_jobs_orm)
    paginated_pending_orm = pending_jobs_orm[pending_skip : pending_skip + pending_limit]

    paginated_pending = [JobResponse.model_validate(job) for job in paginated_pending_orm]

    return {
        "resources": {
            "node": "liustation",
            "gpu_model": "RTX 5090",
            "total": display_total,
            "free": n1_free,
            "used": n2_used,
        },
        "running_jobs": paginated_running,
        "total_running": total_running,
        "pending_jobs": paginated_pending,
        "total_pending": total_pending,
    }


@router.get(
    "/dashboard/my-active-jobs",
    response_model=DashboardJobsResponse,
)
async def get_my_active_jobs(
    skip: int = 0,
    limit: int = 5,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Dashboard 专用：获取当前用户“活跃”的任务
    支持分页：先获取全量数据进行复杂排序，再内存切片
    """
    # 获取 Running 任务
    running_orm = db.query(models.Job).filter(
        models.Job.user_id == current_user.id,
        models.Job.status == JobStatus.RUNNING
    ).order_by(models.Job.start_time.desc()).all()

    # 获取排队任务
    queued_orm = db.query(models.Job).filter(
        models.Job.user_id == current_user.id,
        models.Job.status.in_([JobStatus.PENDING, JobStatus.PAUSED])
    ).all()

    # 对排队任务应用调度排序
    queued_orm.sort(key=_scheduler_sort_key, reverse=True)

    # 合并全量列表
    all_jobs_orm = running_orm + queued_orm

    # 计算总数与切片 (Pagination)
    total_count = len(all_jobs_orm)
    paginated_orm = all_jobs_orm[skip : skip + limit]

    return {
        "items": [JobResponse.model_validate(job) for job in paginated_orm],
        "total": total_count,
    }


@router.get("/dashboard/stats")
async def get_dashboard_stats(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Dashboard 统计接口:
    - Occupancy (占有率): 真实数据 (基于 ClusterSnapshot 历史平均)
    - Utilization (利用率): Mock 数据 (因为没有 DCGM 监控)
    """
    now = datetime.utcnow()

    # --- 逻辑 A: 计算真实的 Occupancy (Allocation) ---
    def get_real_occupancy(hours: int)-> float:
        start_time = now - timedelta(hours=hours)
        snapshots = db.query(models.ClusterSnapshot).filter(
            models.ClusterSnapshot.timestamp >= start_time
        ).all()

        if not snapshots: return 0.0

        total_cap = sum(s.total_gpus for s in snapshots)
        total_used = sum(s.slurm_used_gpus for s in snapshots)

        return (total_used / total_cap) if total_cap > 0 else 0.0

    # --- 逻辑 B: Mock 利用率 ---
    # 模拟一个 30% ~ 60% 之间的随机负载
    mock_util_24h = 0.45 + random.uniform(-0.05, 0.05)
    mock_util_7d = 0.38

    return {
        "total_occupancy_24h": get_real_occupancy(24),
        "total_occupancy_7d": get_real_occupancy(24 * 7),

        "magnus_utilization_24h": mock_util_24h,
        "magnus_utilization_7d": mock_util_7d,
    }


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
            email=feishu_user.get("email"),
            token=generate_trust_token()
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    else:
        db_user.name = feishu_user.get("name", db_user.name)
        db_user.avatar_url = feishu_user.get("avatar_url", db_user.avatar_url)
        if not db_user.token:
            db_user.token = generate_trust_token()
        db.commit()
        db.refresh(db_user)

    access_token = jwt_signer.create_access_token(payload={"sub": db_user.id})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": db_user,
    }


@router.post(
    "/auth/token/refresh",
    response_model=UserInfo,
)
async def refresh_trust_token(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    new_token = generate_trust_token()
    current_user.token = new_token

    db.commit()
    db.refresh(current_user)

    logger.info(f"User {current_user.id} ({current_user.name}) refreshed their trust token.")

    return current_user


@router.get(
    "/users",
    response_model=List[UserInfo],
)
async def get_users(
    db: Session = Depends(database.get_db),
):
    users = db.query(models.User).order_by(models.User.name).all()
    return users


# ================= Blueprint Routes =================

@router.post("/blueprints", response_model=BlueprintResponse)
async def create_blueprint(
    bp: BlueprintCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 1. 验证代码签名
    try:
        blueprint_manager.analyze_signature(bp.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. 检查 ID 是否冲突（如果是新建）
    # 注意：这里允许 overwrite (Update)，但如果是别人的蓝图则禁止覆盖
    existing = db.query(models.Blueprint).filter(models.Blueprint.id == bp.id).first()

    if existing:
        if existing.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You cannot modify a blueprint created by another user. Please verify the Blueprint ID."
            )

        # Update existing
        existing.title = bp.title
        existing.description = bp.description
        existing.code = bp.code
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    # Create new
    db_bp = models.Blueprint(
        **bp.model_dump(),
        user_id=current_user.id
    )
    db.add(db_bp)
    db.commit()
    db.refresh(db_bp)
    return db_bp


@router.delete("/blueprints/{blueprint_id}")
async def delete_blueprint(
    blueprint_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    删除蓝图。仅拥有者可操作。
    """
    bp = db.query(models.Blueprint).filter(models.Blueprint.id == blueprint_id).first()

    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    if bp.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to delete this blueprint")

    db.delete(bp)
    db.commit()

    return {"message": "Blueprint deleted successfully"}


@router.get("/blueprints", response_model=PagedBlueprintResponse)
async def list_blueprints(
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    creator_id: Optional[str] = None,
    db: Session = Depends(database.get_db),
):
    """
    获取蓝图列表（支持分页、搜索、筛选）
    """
    query = db.query(models.Blueprint)

    # 1. 搜索逻辑 (Title, ID, Description)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                models.Blueprint.title.ilike(search_pattern),
                models.Blueprint.id.ilike(search_pattern),
                models.Blueprint.description.ilike(search_pattern)
            )
        )

    # 2. 用户筛选
    if creator_id and creator_id != "all":
        query = query.filter(models.Blueprint.user_id == creator_id)

    total = query.count()

    # 3. 分页查询
    # 按更新时间倒序排列（最近更新的在前面）
    items = query.order_by(models.Blueprint.updated_at.desc())\
                 .offset(skip)\
                 .limit(limit)\
                 .all()

    return {"total": total, "items": items}


@router.get("/blueprints/{blueprint_id}/schema", response_model=List[BlueprintParamSchema])
async def get_blueprint_schema(
    blueprint_id: str,
    db: Session = Depends(database.get_db),
):
    bp = db.query(models.Blueprint).filter(models.Blueprint.id == blueprint_id).first()
    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    try:
        return blueprint_manager.analyze_signature(bp.code)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Invalid blueprint code: {e}")


@router.post("/blueprints/{blueprint_id}/run")
async def run_blueprint(
    blueprint_id: str,
    params: Dict[str, Any],
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    bp = db.query(models.Blueprint).filter(models.Blueprint.id == blueprint_id).first()
    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    try:
        job_submission = blueprint_manager.execute(
            bp.code,
            params,
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

        logger.info(f"Blueprint {blueprint_id} launched job {db_job.id}")
        return {"message": "Blueprint launched", "job_id": db_job.id}

    except Exception as e:
        logger.error(f"Blueprint run failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Service Routes ====================

@router.post("/services", response_model=ServiceResponse)
async def create_or_update_service(
    service_data: ServiceCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    创建或更新 Service 配置
    """
    existing = db.query(Service).filter(Service.id == service_data.id).first()

    data = service_data.model_dump()

    if existing:
        if existing.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to modify this service")

        # 更新配置，下次拉起时生效
        for k, v in data.items():
            setattr(existing, k, v)

        # 确保 owner 不被覆盖
        existing.owner_id = current_user.id

        db.commit()
        db.refresh(existing)
        return existing

    else:
        new_service = Service(
            **data,
            owner_id=current_user.id,
            is_active=True,
            last_activity_time=datetime.utcnow(),
        )
        db.add(new_service)
        db.commit()
        db.refresh(new_service)
        return new_service


@router.api_route("/services/{service_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_service_request(
    service_id: str,
    path: str,
    request: Request,
    db: Session = Depends(database.get_db),
):
    """
    Magnus Service Proxy
    核心状态机逻辑：Revive -> Wait -> Forward
    """
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    if not service.is_active:
        raise HTTPException(status_code=503, detail="Service is inactive")

    # ================= Step 1: 决策与拉起 (Revive) =================

    # 刷新活跃时间 (Keep-Alive)
    service.last_activity_time = datetime.utcnow()
    db.commit()  # 立即提交以防并发缩容

    current_job = service.current_job

    # 判断是否需要复活 (Case 3: Dead/None)
    should_revive = False
    if not current_job:
        should_revive = True
    elif current_job.status in [JobStatus.FAILED, JobStatus.TERMINATED, JobStatus.SUCCESS]:
        should_revive = True

    if should_revive:
        try:
            # 1. 分配端口
            port = service_manager.allocate_port(db)

            # 2. 注入环境变量 (通过修改 entry_command)
            # 最小修改原则：不改 Job Model，直接 prepend export
            original_cmd = service.entry_command
            env_cmd = f"export MAGNUS_PORT={port}; {original_cmd}"

            # 3. 创建 Job
            new_job = models.Job(
                task_name=service.name,
                description=service.id,
                user_id=service.owner_id,
                namespace=service.namespace,
                repo_name=service.repo_name,
                branch=service.branch,
                commit_sha=service.commit_sha,
                gpu_count=service.gpu_count,
                gpu_type=service.gpu_type,
                cpu_count=service.cpu_count,
                memory_demand=service.memory_demand,
                runner=service.runner,
                entry_command=env_cmd,
                status=JobStatus.PENDING,
                job_type=service.job_type,
            )

            db.add(new_job)
            db.flush()  # 获取 ID

            # 4. 关联 Service
            service.current_job_id = new_job.id
            service.assigned_port = port
            db.commit()

            current_job = new_job
            logger.info(f"Service {service.id} revived with Job {new_job.id} on port {port}")

        except Exception as e:
            logger.error(f"Failed to revive service {service.id}: {e}")
            raise HTTPException(status_code=500, detail=f"Service spawn failed: {e}")

    # ================= Step 2: 阻塞等待 (Blocking Wait) =================

    # 如果处于 PENDING/PAUSED，进入等待循环
    start_wait = datetime.utcnow()
    timeout_sec = service.request_timeout

    while current_job.status in [JobStatus.PENDING, JobStatus.PAUSED]:
        if (datetime.utcnow() - start_wait).total_seconds() > timeout_sec:
             # Timeout 504
             raise HTTPException(status_code=504, detail={"detail": "Service is queuing...", "job_id": current_job.id})

        # 刷新活跃时间
        service.last_activity_time = datetime.utcnow()
        db.commit()

        await asyncio.sleep(1)
        db.refresh(current_job)  # 重新获取状态

        # 边界检查：如果等待途中挂了
        if current_job.status in [JobStatus.FAILED, JobStatus.TERMINATED]:
             raise HTTPException(status_code=502, detail="Service job failed during startup")

    # ================= Step 3: 转发 (Forward) =================

    if current_job.status != JobStatus.RUNNING:
        # 理论上不可达，除非状态异常
        raise HTTPException(status_code=502, detail=f"Service unready (Status: {current_job.status})")

    target_url = f"http://127.0.0.1:{service.assigned_port}/{path}"
    if request.query_params:
        target_url += f"?{request.query_params}"

    # 构建转发请求
    try:
        client = httpx.AsyncClient(base_url=f"http://127.0.0.1:{service.assigned_port}")

        body = await request.body()

        rp_req = client.build_request(
            request.method,
            f"/{path}",  # use path relative to base_url
            content=body,
            headers=request.headers.raw,
            params=request.query_params,
            timeout=10.0  # 单次转发请求的超时，不同于排队超时
        )

        # 再次刷新活跃时间
        service.last_activity_time = datetime.utcnow()
        db.commit()

        r = await client.send(rp_req, stream=True)

        return StreamingResponse(
            r.aiter_raw(),
            status_code=r.status_code,
            headers=r.headers,
            background=None
        )

    except httpx.ConnectError:
         raise HTTPException(status_code=502, detail="Service process is running but port is unreachable. Application might be initializing.")
    except Exception as e:
        logger.error(f"Proxy error for {service.id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services", response_model=PagedServiceResponse)
async def list_services(
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    owner_id: Optional[str] = None,
    db: Session = Depends(database.get_db),
):
    query = db.query(models.Service)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                models.Service.name.ilike(search_pattern),
                models.Service.id.ilike(search_pattern),
                models.Service.description.ilike(search_pattern)
            )
        )

    if owner_id and owner_id != "all":
        query = query.filter(models.Service.owner_id == owner_id)

    total = query.count()

    items = query.order_by(models.Service.last_activity_time.desc())\
                 .offset(skip)\
                 .limit(limit)\
                 .all()

    return {"total": total, "items": items}
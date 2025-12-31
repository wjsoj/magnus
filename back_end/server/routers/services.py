# back_end/server/routers/services.py
import httpx
import logging
import asyncio
import socket
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from collections import defaultdict
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import database
from ..database import SessionLocal
from .. import models
from ..models import JobStatus, Service
from ..schemas import ServiceResponse, ServiceCreate, PagedServiceResponse
from .._service_manager import service_manager
from .._magnus_config import magnus_config
from .auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

# 防止同一服务的并发创建冲突
_service_spawn_locks = defaultdict(asyncio.Lock)

# 流量控制信号量字典
_service_semaphores: Dict[str, asyncio.Semaphore] = {}

# --- Pydantic 快照模型 ---
class ServiceSnapshot(BaseModel):
    id: str
    max_concurrency: int
    request_timeout: int
    assigned_port: Optional[int] = None
    entry_command: str
    job_task_name: str
    job_description: str
    owner_id: str
    namespace: str
    repo_name: str
    branch: str
    commit_sha: str
    gpu_count: int
    gpu_type: str
    # [Fix] 允许为空，与 SQLAlchemy Model 保持一致
    cpu_count: Optional[int] = None
    memory_demand: Optional[str] = None
    runner: Optional[str] = None
    job_type: str

    class Config:
        from_attributes = True

# --- 同步辅助函数区 (自带 Session 生命周期) ---

def _get_service_snapshot_standalone(service_id: str) -> ServiceSnapshot:
    """独立的获取快照函数"""
    with SessionLocal() as db:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        if not service.is_active:
            raise HTTPException(status_code=503, detail="Service is inactive")
        
        # Keep-Alive
        service.last_activity_time = datetime.utcnow()
        db.commit()
        
        # 转换为 Pydantic
        return ServiceSnapshot.model_validate(service)

def _try_revive_service_standalone(service_id: str) -> Tuple[str, int]:
    """独立的拉起函数"""
    with SessionLocal() as db:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found (during revive)")
            
        current_job = service.current_job
        
        should_revive = False
        if not current_job:
            should_revive = True
        elif current_job.status in [JobStatus.FAILED, JobStatus.TERMINATED, JobStatus.SUCCESS]:
            should_revive = True
        
        # Path A: 不需要重启
        if not should_revive:
            if current_job is None or service.assigned_port is None:
                raise HTTPException(status_code=500, detail="State Error: Service active but no job/port.")
            return current_job.id, service.assigned_port

        # Path B: 需要重启
        try:
            port = service_manager.allocate_port(db)

            env_cmd = "\n".join([
                f"export MAGNUS_PORT={port}",
                service.entry_command,
            ])

            new_job = models.Job(
                task_name=service.job_task_name,
                description=service.job_description,
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
            db.flush()

            service.current_job_id = new_job.id
            service.assigned_port = port
            db.commit()
            
            logger.info(f"Service {service.id} revived with Job {new_job.id} on port {port}")
            return new_job.id, port

        except Exception as e:
            logger.error(f"Failed to revive service {service.id}: {e}")
            raise HTTPException(status_code=500, detail=f"Service spawn failed: {e}")

def _check_socket_sync(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False

def _refresh_status_standalone(job_id: str, service_id: str) -> str:
    with SessionLocal() as db:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job:
            return JobStatus.TERMINATED
        
        service = db.query(models.Service).filter(models.Service.id == service_id).first()
        if service:
            service.last_activity_time = datetime.utcnow()
            db.commit()
        
        return job.status

def _update_activity_standalone(service_id: str):
    with SessionLocal() as db:
        service = db.query(models.Service).filter(models.Service.id == service_id).first()
        if service:
            service.last_activity_time = datetime.utcnow()
            db.commit()

# --- API 路由区 ---

@router.post("/services", response_model=ServiceResponse)
def create_service(
    service_data: ServiceCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
) -> models.Service:
    existing = db.query(Service).filter(Service.id == service_data.id).first()
    data = service_data.model_dump()

    if existing:
        if existing.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You cannot modify a service created by another user.")
        
        if service_data.max_concurrency != existing.max_concurrency:
            if existing.id in _service_semaphores:
                del _service_semaphores[existing.id]
                logger.info(f"Concurrency limit changed for {existing.id}, semaphore reset.")

        for k, v in data.items():
            setattr(existing, k, v)
        existing.owner_id = current_user.id
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    data["is_active"] = False
    new_service = Service(
        **data,
        owner_id=current_user.id,
        last_activity_time=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(new_service)
    db.commit()
    db.refresh(new_service)
    return new_service


@router.delete("/services/{service_id}")
def delete_service(
    service_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    svc = db.query(Service).filter(Service.id == service_id).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    if svc.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to delete this service")

    db.delete(svc)
    db.commit()

    if service_id in _service_semaphores:
        del _service_semaphores[service_id]

    return {"message": "Service deleted successfully"}


@router.get("/services", response_model=PagedServiceResponse)
def list_services(
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    owner_id: Optional[str] = None,
    active_only: bool = False,
    sort_by: str = Query("activity", regex="^(activity|updated)$"),
    db: Session = Depends(database.get_db)
) -> Dict[str, Any]:
    query = db.query(models.Service)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(or_(
            models.Service.name.ilike(search_pattern),
            models.Service.id.ilike(search_pattern),
            models.Service.description.ilike(search_pattern),
        ))

    if owner_id and owner_id != "all":
        query = query.filter(models.Service.owner_id == owner_id)

    if active_only:
        query = query.filter(models.Service.is_active == True)

    total = query.count()

    if sort_by == "updated":
        query = query.order_by(models.Service.updated_at.desc())
    else:
        query = query.order_by(models.Service.last_activity_time.desc())

    items = query.offset(skip).limit(limit).all()
    return {"total": total, "items": items}


@router.api_route(
    "/services/{service_id}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy_service_request(
    service_id: str,
    path: str,
    request: Request,
) -> StreamingResponse:
    
    # 1. 基础检查
    service_snap = await asyncio.to_thread(_get_service_snapshot_standalone, service_id)

    # 2. 获取或创建信号量
    if service_snap.id not in _service_semaphores:
        _service_semaphores[service_snap.id] = asyncio.Semaphore(service_snap.max_concurrency)

    sem = _service_semaphores[service_snap.id]

    # 3. SLA 控制
    start_time = datetime.utcnow()
    total_budget = service_snap.request_timeout

    def get_remaining_time() -> float:
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        return max(0.0, total_budget - elapsed)

    # 4. 流量控制
    try:
        await asyncio.wait_for(sem.acquire(), timeout=get_remaining_time())
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=429,
            detail=f"Service is busy (Max concurrency {service_snap.max_concurrency} reached)."
        )

    try:
        # === 进入流量控制区 ===

        # 5. 检查与拉起 (Spawn Logic)
        if get_remaining_time() <= 0:
            raise HTTPException(status_code=504, detail="Timeout while waiting for concurrency slot")

        async with _service_spawn_locks[service_id]:
            current_job_id, assigned_port = await asyncio.to_thread(
                _try_revive_service_standalone, service_id
            )
            service_snap.assigned_port = assigned_port

        # 6. 等待就绪 (Wait Logic)
        is_ready = False

        while get_remaining_time() > 0:
            job_status = await asyncio.to_thread(_refresh_status_standalone, current_job_id, service_id)

            if job_status in [JobStatus.FAILED, JobStatus.TERMINATED]:
                raise HTTPException(status_code=502, detail="Service job failed during startup")

            if job_status in [JobStatus.PENDING, JobStatus.PAUSED]:
                await asyncio.sleep(1)
                continue

            if job_status == JobStatus.RUNNING:
                if not service_snap.assigned_port:
                    await asyncio.sleep(1)
                    continue

                socket_ok = await asyncio.to_thread(
                    _check_socket_sync, "127.0.0.1", service_snap.assigned_port
                )
                
                if socket_ok:
                    is_ready = True
                    break
                else:
                    await asyncio.sleep(1)
                    continue

            await asyncio.sleep(1)

        if not is_ready:
            raise HTTPException(status_code=504, detail="Service startup timed out")

        # 7. 转发请求 (Forward Logic)
        service_config = magnus_config.get("server", {}).get("services", {})
        
        proxy_timeout = httpx.Timeout(
            connect=service_config.get("proxy_connect_timeout", 2.0),
            read=service_config.get("proxy_read_timeout", 600.0),
            write=service_config.get("proxy_write_timeout", 30.0),
            pool=service_config.get("proxy_pool_timeout", 5.0),
        )

        client = httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{service_snap.assigned_port}",
            timeout=proxy_timeout,
            follow_redirects=True,
        )

        try:
            body = await request.body()
            rp_req = client.build_request(
                request.method,
                f"/{path}",
                content=body,
                headers=request.headers.raw,
                params=request.query_params,
            )

            await asyncio.to_thread(_update_activity_standalone, service_id)

            r = await client.send(rp_req, stream=True)

            return StreamingResponse(
                r.aiter_raw(),
                status_code=r.status_code,
                headers=r.headers,
                background=BackgroundTask(client.aclose),
            )

        except httpx.ConnectError:
            await client.aclose()
            raise HTTPException(status_code=502, detail="Service running but connection failed.")
        except Exception as e:
            await client.aclose()
            logger.error(f"Proxy error for {service_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    finally:
        sem.release()
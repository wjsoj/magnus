# back_end/server/_service_manager.py
import logging
import asyncio
import random
from datetime import datetime

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Service, JobStatus
from ._scheduler import scheduler

logger = logging.getLogger(__name__)


class ServiceManager:
    def __init__(self):
        self._running = False

    async def start_background_loop(self):
        if self._running:
            return
        self._running = True
        logger.info("Service Manager background loop started.")
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Service Manager tick failed: {e}", exc_info=True)
            await asyncio.sleep(3)

    async def _tick(self):
        # 使用 run_in_executor 避免阻塞 asyncio loop
        await asyncio.to_thread(self._sync_logic)

    def _sync_logic(self):
        with SessionLocal() as db:
            active_services = db.query(Service).filter(Service.is_active == True).all()
            now = datetime.utcnow()

            for service in active_services:
                if not service.current_job_id:
                    continue

                job = service.current_job
                if not job:
                    continue

                if job.status in [JobStatus.PENDING, JobStatus.PAUSED]:
                    # Anti-Starvation
                    service.last_activity_time = now
                    db.add(service)

                elif job.status == JobStatus.RUNNING:
                    idle_duration = (now - service.last_activity_time).total_seconds()
                    idle_limit_seconds = service.idle_timeout * 60

                    if idle_duration > idle_limit_seconds:
                        logger.info(f"Service {service.id} idle for {idle_duration:.0f}s. Scaling to zero.")
                        scheduler.terminate_job(db, job)
                        # 注意：不置空 current_job_id，保持关联以便查看历史或状态

            db.commit()

    def allocate_port(self, db: Session)-> int:
        used_ports = set(
            db.query(Service.assigned_port)
            .filter(Service.assigned_port.is_not(None))
            .all()
        )
        used_ports = {p[0] for p in used_ports}

        for _ in range(100):
            candidate = random.randint(10000, 30000)
            if candidate not in used_ports:
                return candidate

        raise RuntimeError("Failed to allocate a free port for Service after 100 attempts.")


service_manager = ServiceManager()
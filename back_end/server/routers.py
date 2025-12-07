# 文件: back_end/server/routers.py
from fastapi import APIRouter, HTTPException
from library.fundamental.github_tools import github
from library.functional.schemas import JobSubmission

router = APIRouter()

@router.get("/github/{ns}/{repo}/branches")
async def get_branches(ns: str, repo: str):
    branches = await github.fetch_branches(ns, repo)
    if not branches:
        raise HTTPException(status_code=404, detail="Repo not found or empty")
    return branches

@router.get("/github/{ns}/{repo}/commits")
async def get_commits(ns: str, repo: str, branch: str):
    return await github.fetch_commits(ns, repo, branch)

@router.post("/jobs/submit")
async def submit_job(job: JobSubmission):
    # Milestone 1 的核心：Print 出来就算成功
    print("\n" + "="*50)
    print(f"🚀 [Magnus Backend] 收到发射指令！")
    print(f"📦 仓库位置: {job.namespace}/{job.repo_name}")
    print(f"🌿 选定分支: {job.branch}")
    print(f"🔗 锁定Commit: {job.commit_sha}")
    print(f"⌨️  启动命令: {job.entry_command}")
    print("="*50 + "\n")
    
    return {"status": "success", "msg": "任务已接收，后端日志打印成功"}
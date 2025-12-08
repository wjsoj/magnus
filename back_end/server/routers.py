# 文件: back_end/server/routers.py
from library import *
from ._github_client import *

router = APIRouter()

@router.get("/github/{ns}/{repo}/branches")
async def get_branches(ns: str, repo: str):
    branches = await github_client.fetch_branches(ns, repo)
    if not branches:
        raise HTTPException(status_code=404, detail="Repo not found or empty")
    return branches

@router.get("/github/{ns}/{repo}/commits")
async def get_commits(ns: str, repo: str, branch: str):
    return await github_client.fetch_commits(ns, repo, branch)

@router.post("/jobs/submit")
async def submit_job(job: JobSubmission):
    print("\n" + "="*50)
    print(f"🚀 [Magnus Backend] 收到发射指令！")
    print(f"📦 仓库位置: {job.namespace}/{job.repo_name}")
    print(f"🌿 选定分支: {job.branch}")
    print(f"🔗 锁定Commit: {job.commit_sha}")
    print(f"🎮 计算资源: {job.gpu_count} x {job.gpu_type}")  # ✅ 打印显卡信息
    print(f"⌨️  启动命令: \n{job.entry_command}")
    print("="*50 + "\n")
    
    return {"status": "success", "msg": f"任务接收成功! (申请 {job.gpu_count}x {job.gpu_type})"}
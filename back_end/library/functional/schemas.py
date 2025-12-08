from pydantic import BaseModel
from typing import Optional

class JobSubmission(BaseModel):
    namespace: str
    repo_name: str
    branch: str
    commit_sha: str
    entry_command: str = "python train.py"
    # ✅ 新增资源配置
    gpu_count: int = 1
    gpu_type: str = "Any"
# 文件: back_end/library/schemas.py
from pydantic import BaseModel
from typing import Optional

class JobSubmission(BaseModel):
    namespace: str
    repo_name: str
    branch: str
    commit_sha: str
    entry_command: str = "python train.py" # 默认值
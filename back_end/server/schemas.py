from library import *


__all__ = [
    "JobSubmission",
    "JobResponse",
    "PagedJobResponse", # ✅ 新增导出
    "FeishuLoginRequest",
    "UserInfo",
    "LoginResponse",
]


class UserInfo(BaseModel):
    id: str
    name: str
    avatar_url: Optional[str] = None
    email: Optional[str] = None

    class Config:
        from_attributes = True


class JobSubmission(BaseModel):
    task_name: str
    description: Optional[str] = None
    namespace: str = "PKU-Plasma"
    repo_name: str
    branch: str
    commit_sha: str
    entry_command: str
    gpu_type: str
    gpu_count: int = 1
    
    
class JobResponse(JobSubmission):
    id: str
    user_id: str
    status: str
    created_at: datetime

    # Pydantic 会自动从数据库模型的 relationship 中读取 user 对象
    user: Optional[UserInfo] = None 

    class Config:
        from_attributes = True


# ✅ 新增：分页响应包装器
class PagedJobResponse(BaseModel):
    total: int
    items: List[JobResponse]


class FeishuLoginRequest(BaseModel):
    code: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
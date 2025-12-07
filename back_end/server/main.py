# 文件: back_end/server/main.py
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from server.routers import router
from library.fundamental.github_tools import github

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时不做啥
    yield
    # 关闭时清理 HTTP Client
    await github.close()

app = FastAPI(title="Magnus API", lifespan=lifespan)

# 允许跨域 (CORS) - 关键！否则前端访问不了后端
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

if __name__ == "__main__":
    # 监听 0.0.0.0 方便你在本地浏览器访问远程服务器
    uvicorn.run("server.main:app", host="0.0.0.0", port=8017, reload=True)
# 文件: back_end/server/main.py
from library import *
from .routers import *
from ._github_client import *
from ._magnus_config import *

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时不做啥
    yield
    # 关闭时清理 HTTP Client
    await github_client.close()

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
    uvicorn.run(
        "server.main:app", 
        host = "0.0.0.0", 
        port = magnus_config["server"]["port"],
        reload = True,
    )
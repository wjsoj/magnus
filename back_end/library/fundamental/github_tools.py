# 文件: back_end/library/github_tools.py
import httpx
from typing import List, Dict, Any, Optional

class GitHubClient:
    def __init__(self):
        self.base_url = "https://api.github.com/repos"
        # 💡 如果你在国内服务器，且设置了系统代理，httpx 会自动读取
        # 如果需要强制指定，可以在这里加 proxies 参数
        self.client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)

    async def fetch_branches(self, namespace: str, repo: str) -> List[Dict[str, Any]]:
        """获取分支列表"""
        url = f"{self.base_url}/{namespace}/{repo}/branches"
        print(f"[GithubTool] Fetching: {url}")
        
        resp = await self.client.get(url)
        if resp.status_code != 200:
            print(f"❌ GitHub API Error: {resp.status_code} - {resp.text}")
            return []
            
        data = resp.json()
        # 清洗数据，只留我们前端需要的
        return [{"name": item["name"], "commit_sha": item["commit"]["sha"]} for item in data]

    async def fetch_commits(self, namespace: str, repo: str, branch_sha: str) -> List[Dict[str, Any]]:
        """获取某分支下的 Commits"""
        url = f"{self.base_url}/{namespace}/{repo}/commits"
        # 这里的 sha 参数既可以是分支名，也可以是具体的 commit hash
        params = {"sha": branch_sha, "per_page": 10} 
        
        resp = await self.client.get(url, params=params)
        if resp.status_code != 200:
            return []

        data = resp.json()
        results = []
        for item in data:
            c = item["commit"]
            results.append({
                "sha": item["sha"],
                "message": c["message"].split('\n')[0], # 只取第一行
                "author": c["author"]["name"],
                "date": c["author"]["date"]
            })
        return results

    async def close(self):
        await self.client.aclose()

# 单例模式：全局共用一个 Client
github = GitHubClient()
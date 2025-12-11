from ..fundamental import *


__all__ = [
    "FeishuClient",
]


class FeishuClient:
    
    def __init__(
        self, 
        app_id: str, 
        app_secret: str, 
        redirect_uri: str,
        verbose: bool = False,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri
        self.host = "https://open.feishu.cn"
        self.verbose = verbose


    async def _get_tenant_access_token(
        self, 
        client: httpx.AsyncClient
    )-> str:
        """
        Step 1: 获取应用维度的凭证 (Tenant Access Token)
        这是调用飞书后续接口的“入场券”。
        """
        url = f"{self.host}/open-apis/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        if self.verbose: print(f"📡 [Feishu Step 1] Getting App Token...")

        try:
            resp = await client.post(url, json=payload)
            data = resp.json()

            if data.get("code") != 0:
                raise RuntimeError(f"Step 1 Failed (App Token): {data}")
            
            return data["tenant_access_token"]
        
        except Exception as e:
            print(f"❌ [Feishu Step 1] Error: {e}")
            raise e


    async def get_feishu_user(
        self, 
        code: str,
    )-> Dict[str, Any]:
        """
        标准三步走流程：Code -> User Info
        """
        async with httpx.AsyncClient() as client:
            
            app_token = await self._get_tenant_access_token(client)
            url_step2 = f"{self.host}/open-apis/authen/v1/access_token"
            headers_app = {
                "Authorization": f"Bearer {app_token}",
                "Content-Type": "application/json; charset=utf-8"
            }
            payload_step2 = {
                "grant_type": "authorization_code",
                "code": code
            }

            if self.verbose: print(f"📡 [Feishu Step 2] Exchanging Code for User Token...")
            resp_step2 = await client.post(url_step2, json=payload_step2, headers=headers_app)
            data_step2 = resp_step2.json()
            
            if data_step2.get("code") != 0:
                if self.verbose: print(f"📩 [Feishu Step 2] Response: {data_step2}")
                raise RuntimeError(f"Step 2 Failed (User Token): {data_step2.get('msg')}")

            user_access_token = data_step2["data"]["access_token"]
            
            url_step3 = f"{self.host}/open-apis/authen/v1/user_info"
            headers_user = {
                "Authorization": f"Bearer {user_access_token}",
                "Content-Type": "application/json; charset=utf-8"
            }

            if self.verbose: print(f"📡 [Feishu Step 3] Fetching User Profile...")
            resp_step3 = await client.get(url_step3, headers=headers_user)
            data_step3 = resp_step3.json()
            
            if self.verbose: print(f"📩 [Feishu Step 3] Response: {data_step3}")

            if data_step3.get("code") != 0:
                raise RuntimeError(f"Step 3 Failed (User Info): {data_step3.get('msg')}")
            
            return data_step3["data"]
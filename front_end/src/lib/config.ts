// front_end/src/lib/config.ts

function requireEnv(value: string | undefined, key: string): string {
  if (!value) {
    throw new Error(`❌ 致命错误: 环境变量 ${key} 未定义，请检查配置文件`);
  }
  return value;
}

const API_PORT = process.env.NEXT_PUBLIC_BACK_END_PORT;
const SERVER_PUBLIC_IP = process.env.NEXT_PUBLIC_SERVER_PUBLIC_IP;
export const API_BASE = `http://${SERVER_PUBLIC_IP}:${API_PORT}`;
export const FEISHU_APP_ID = requireEnv(
    process.env.NEXT_PUBLIC_FEISHU_APP_ID, 
    "NEXT_PUBLIC_FEISHU_APP_ID",
);
export const POLL_INTERVAL = parseInt(
  requireEnv(
    process.env.NEXT_PUBLIC_POLL_INTERVAL, 
    "NEXT_PUBLIC_POLL_INTERVAL"
  ),
  10,
) * 1000;
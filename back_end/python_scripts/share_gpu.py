# back_end/python_scripts/share_gpu.py

import argparse
import os
import sys
import socket
import subprocess
import shutil
import tempfile
import time
from pathlib import Path
from datetime import datetime

def log(msg, level="INFO"):
    """带时间戳并强制刷新的日志函数"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    icon = "[*]" if level == "INFO" else "[!]"
    # flush=True 保证日志即时输出，替代 sys.stdout.reconfigure
    print(f"{icon} {timestamp} {msg}", flush=True)

def get_free_port():
    """获取一个空闲的随机端口"""
    log("正在寻找空闲端口...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        port = s.getsockname()[1]
        log(f"获取到端口: {port}")
        return port

def get_target_user_pubkey(username):
    log(f"开始寻找用户 '{username}' 的 SSH 公钥...")
    
    possible_paths = [
        Path(f"/home/{username}/.ssh/id_rsa.pub"),
        Path(f"/home/{username}/.ssh/id_ed25519.pub"),
        Path(f"/data/{username}/.ssh/id_rsa.pub"),
        Path(f"/users/{username}/.ssh/id_rsa.pub"),
        Path(f"/home/{username}/.ssh/authorized_keys"),
    ]
    
    for p in possible_paths:
        log(f"  -> 检查路径: {p}")
        if p.exists():
            log(f"  -> 成功找到公钥: {p}")
            try:
                # 只读取第一行
                content = p.read_text().strip().split('\n')[0]
                return content
            except Exception as e:
                log(f"读取公钥文件失败: {e}", "ERROR")
    
    log(f"错误: 在上述路径均未找到用户 '{username}' 的公钥", "ERROR")
    return None

def main():
    parser = argparse.ArgumentParser(description="Magnus GPU Sharing (Debug Mode)")
    parser.add_argument("username", type=str, help="接收 GPU 权限的目标用户名")
    args = parser.parse_args()
    target_user = args.username

    # 初始化变量，防止 finally 块报错
    process = None
    work_dir = None

    log(f"启动 GPU 共享脚本 (Process ID: {os.getpid()})")
    log(f"当前运行用户: {os.getenv('USER')}")

    try:
        # 1. 检查 SSHD
        sshd_path = shutil.which("sshd") or "/usr/sbin/sshd"
        log(f"检测 sshd 路径: {sshd_path}")
        if not os.path.exists(sshd_path):
            log("错误: 未找到 sshd 程序", "ERROR")
            sys.exit(1)

        # 2. 获取公钥
        pubkey = get_target_user_pubkey(target_user)
        if not pubkey:
            log("无法继续: 未找到目标用户公钥", "ERROR")
            sys.exit(1)

        # 3. 创建临时目录
        work_dir = tempfile.mkdtemp(prefix="magnus_sshd_")
        work_path = Path(work_dir)
        log(f"创建临时运行环境: {work_path}")

        # 4. 生成 Host Key
        host_key_path = work_path / "ssh_host_rsa_key"
        log("正在生成临时 Host Key...")
        subprocess.check_call(
            ["ssh-keygen", "-t", "rsa", "-f", str(host_key_path), "-N", "", "-q"],
            stdout=sys.stdout, stderr=sys.stderr
        )

        # 5. 配置 authorized_keys
        auth_keys_path = work_path / "authorized_keys"
        auth_keys_path.write_text(pubkey)
        auth_keys_path.chmod(0o600)
        log("已配置 authorized_keys")

        # 6. 配置 SSHD
        port = get_free_port()
        pid_file = work_path / "sshd.pid"
        
        sshd_config = f"""
        Port {port}
        HostKey {host_key_path}
        AuthorizedKeysFile {auth_keys_path}
        PidFile {pid_file}
        PermitRootLogin no
        PasswordAuthentication no
        ChallengeResponseAuthentication no
        UsePAM no
        X11Forwarding yes
        PrintMotd no
        LogLevel DEBUG1
        ClientAliveInterval 60
        ClientAliveCountMax 3
        """
        
        config_path = work_path / "sshd_config"
        config_path.write_text(sshd_config)
        log(f"生成配置文件: {config_path}")

        # 7. 启动 SSHD
        log(f"正在尝试启动 sshd (端口 {port})...")
        process = subprocess.Popen(
            [sshd_path, "-f", str(config_path), "-D", "-e"], 
            stderr=sys.stderr, # 错误直接输出到屏幕
            stdout=sys.stdout
        )
        
        time.sleep(2)
        if process.poll() is not None:
            log(f"错误: sshd 启动失败，返回码: {process.returncode}", "ERROR")
            sys.exit(1)
        else:
            log("sshd 启动成功，进程正在运行")

        # 8. 获取 IP
        hostname = os.uname().nodename
        try:
            ip = socket.gethostbyname(hostname)
        except:
            ip = hostname
        current_user = os.getenv("USER")
        
        # 打印邀请码
        print("\n" + "="*60, flush=True)
        print(f"🎉 隧道建立成功！GPU 环境已共享给 {target_user}", flush=True)
        print("="*60, flush=True)
        print("请把下面这行命令发给你的师兄/同学：\n", flush=True)
        print(f"   ssh -p {port} -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no {current_user}@{ip}", flush=True)
        print("\n" + "="*60, flush=True)
        
        # 9. 保活
        log("进入保活循环... (按 Ctrl+C 停止)")
        while True:
            if process.poll() is not None:
                log(f"警告: sshd 进程意外退出 (Code: {process.returncode})", "ERROR")
                break
            time.sleep(10)

    except KeyboardInterrupt:
        log("收到停止信号...")
    except Exception as e:
        log(f"发生未捕获异常: {e}", "ERROR")
    finally:
        # 安全清理
        if process and process.poll() is None:
            log("正在终止 sshd 进程...")
            process.terminate()
        
        if work_dir and os.path.exists(work_dir):
            try:
                shutil.rmtree(work_dir)
                log("临时目录已清理")
            except Exception as e:
                log(f"清理临时目录失败: {e}", "ERROR")

if __name__ == "__main__":
    main()
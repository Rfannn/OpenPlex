import json
import logging
import os
import subprocess
import asyncio
import platform
import threading
import httpx
from typing import Optional
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

ARIA2_RPC_URL = f"http://127.0.0.1:{settings.aria2_rpc_port}/jsonrpc"
aria2_process: Optional[subprocess.Popen] = None
_health_task: Optional[asyncio.Task] = None
_watchdog_thread: Optional[threading.Thread] = None


def find_aria2() -> Optional[str]:
    # Check bundled first (same dir as this file, project root)
    search_dirs = [os.getcwd(), os.path.dirname(os.path.dirname(__file__))]
    candidates = ["aria2c"] if platform.system() != "Windows" else ["aria2c.exe", "aria2c"]
    for d in search_dirs:
        for c in candidates:
            p = os.path.join(d, c)
            if os.path.exists(p) and os.access(p, os.X_OK):
                return os.path.abspath(p)
    # Check PATH
    for c in candidates:
        try:
            subprocess.run([c, "--version"], capture_output=True, timeout=3)
            return c
        except Exception:
            continue
    return None


def start_aria2():
    global aria2_process
    if aria2_process is not None:
        # Check if alive
        if aria2_process.poll() is None:
            return
        logger.warning("aria2c died, restarting...")
        aria2_process = None

    aria2_path = find_aria2()
    if not aria2_path:
        logger.warning("aria2c not found — downloads disabled")
        return
    try:
        aria2_process = subprocess.Popen(
            [
                aria2_path,
                "--enable-rpc",
                f"--rpc-listen-port={settings.aria2_rpc_port}",
                "--rpc-allow-origin-all",
                "--dir=./downloads",
                "--continue=true",
                "--max-connection-per-server=4",
                "--split=4",
                "--min-split-size=10M",
                "--console-log-level=error",
                "--summary-interval=0",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(f"aria2c started (PID {aria2_process.pid})")
    except Exception as e:
        logger.error(f"Failed to start aria2c: {e}")
        aria2_process = None


def _watchdog_loop():
    """Background thread that checks aria2 health every 30s."""
    import time
    while True:
        time.sleep(30)
        global aria2_process
        if aria2_process is None:
            continue
        if aria2_process.poll() is not None:
            logger.warning("aria2 watchdog: process died, restarting...")
            start_aria2()


def start_aria2_watchdog():
    global _watchdog_thread
    if _watchdog_thread is None or not _watchdog_thread.is_alive():
        _watchdog_thread = threading.Thread(target=_watchdog_loop, daemon=True)
        _watchdog_thread.start()
        logger.info("aria2 watchdog started")


def stop_aria2():
    global aria2_process
    if aria2_process:
        pid = aria2_process.pid
        try:
            if platform.system() == "Windows":
                aria2_process.terminate()
            else:
                aria2_process.send_signal(subprocess.signal.SIGTERM)
            try:
                aria2_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                aria2_process.kill()
                aria2_process.wait(timeout=2)
        except Exception:
            try:
                aria2_process.kill()
                aria2_process.wait(timeout=2)
            except Exception:
                pass
        aria2_process = None
        logger.info(f"aria2c stopped (PID {pid})")


_rpc_client: Optional[httpx.AsyncClient] = None

async def _get_client() -> httpx.AsyncClient:
    global _rpc_client
    if _rpc_client is None or _rpc_client.is_closed:
        _rpc_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=30.0), limits=httpx.Limits(max_connections=10))
    return _rpc_client

async def rpc_call(method: str, params: list = None) -> dict:
    if params is None:
        params = []
    payload = {
        "jsonrpc": "2.0",
        "id": "opencode",
        "method": method,
        "params": params,
    }
    try:
        client = await _get_client()
        resp = await client.post(ARIA2_RPC_URL, json=payload)
        if resp.status_code >= 500:
            logger.error(f"aria2 HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if "error" in data:
            logger.error(f"aria2 RPC error: {data['error']}")
        return data
    except httpx.ConnectError as e:
        logger.error(f"aria2 RPC connect failed: {e} — may need restart")
        return {"error": "connect_failed"}
    except Exception as e:
        logger.error(f"aria2 RPC call failed: {e}")
        return {"error": str(e)}


async def health_check() -> bool:
    """Check if aria2 is responding. Triggers restart if dead."""
    result = await rpc_call("aria2.getVersion")
    if "result" in result:
        return True
    # Try to restart
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, start_aria2)
    return False


async def add_download(url: str, dest_dir: str, file_name: str = "") -> Optional[str]:
    opts = {"dir": dest_dir}
    if file_name:
        opts["out"] = file_name
    result = await rpc_call("aria2.addUri", [[url], opts])
    if "result" in result:
        return result["result"]
    return None


async def get_progress(gid: str) -> dict:
    return await rpc_call("aria2.tellStatus", [gid])


async def cancel_download(gid: str) -> bool:
    result = await rpc_call("aria2.remove", [gid])
    return "result" in result


async def pause_download(gid: str) -> bool:
    result = await rpc_call("aria2.pause", [gid])
    return "result" in result


async def resume_download(gid: str) -> bool:
    result = await rpc_call("aria2.unpause", [gid])
    return "result" in result

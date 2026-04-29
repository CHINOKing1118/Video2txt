import os
import subprocess
import requests
from datetime import datetime

from config import OUTPUT_DIR, COOKIE_FILE
from utils import extract_url, sanitize_filename, retry_operation
from history import write_log


def get_video_title_quick(url, log):
    try:
        api_url = "https://apione.apibyte.cn/douyinparse"
        resp = requests.get(api_url, params={"url": url}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 200:
            inner = data.get("data", {})
            title = inner.get("title", "").strip()
            if title:
                log(f"📋 快速获取标题: {title}")
                return title
    except Exception as e:
        log(f"⚠️ 快速获取标题失败: {e}")
    return None


def download_via_api(url, log):
    log("🔍 方案1：第三方 API 解析...")
    write_log(f"[下载] 尝试 API 解析: {url}")
    api_url = "https://apione.apibyte.cn/douyinparse"
    resp = requests.get(api_url, params={"url": url}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise Exception(f"API 返回错误: {data.get('msg')}")
    inner = data.get("data", {})
    video_data = inner.get("video", {})
    video_url = (video_data.get("1080p")
                 or video_data.get("720p")
                 or video_data.get("play_url"))
    if not video_url:
        raise Exception("API 返回中未找到视频地址")
    title = inner.get("title", "untitled").strip()
    log(f"✅ 解析成功: {title}")
    write_log(f"[下载] 解析成功: {title}")
    log("📥 正在下载视频...")
    video_resp = requests.get(video_url, stream=True, timeout=60,
                              headers={"User-Agent": "Mozilla/5.0"})
    if video_resp.status_code != 200:
        raise Exception(f"下载失败，状态码: {video_resp.status_code}")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = sanitize_filename(title)
    path = os.path.join(OUTPUT_DIR, f"{safe}_{ts}.mp4")

    def _save_video():
        with open(path, "wb") as f:
            for chunk in video_resp.iter_content(8192):
                f.write(chunk)

    retry_operation(_save_video)
    log(f"✅ 视频已下载: {path}")
    write_log(f"[下载] 视频已下载: {path}")
    return path, title


def download_via_f2(url, log):
    log("🔍 方案2：f2 下载...")
    write_log("[下载] 尝试 f2 下载")
    before = set(os.listdir(OUTPUT_DIR))
    r = subprocess.run(["f2", "dy", "--url", url],
                       capture_output=True, text=True, timeout=120, cwd=OUTPUT_DIR,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise Exception(f"f2 失败: {r.stderr}")
    new = set(os.listdir(OUTPUT_DIR)) - before
    for f in new:
        if f.endswith((".mp4", ".webm")):
            p = os.path.join(OUTPUT_DIR, f)
            log(f"✅ 视频已下载: {p}")
            write_log(f"[下载] 视频已下载: {p}")
            title = os.path.splitext(f)[0]
            return p, title
    raise Exception("f2 未生成视频文件")


def download_via_ytdlp(url, log, browser="chrome", cookie_file=None):
    log(f"🔍 方案3：yt-dlp（{browser}）...")
    write_log(f"[下载] 尝试 yt-dlp ({browser})")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmpl = os.path.join(OUTPUT_DIR, f"video_{ts}.%(ext)s")
    if cookie_file and os.path.exists(cookie_file):
        cmd = ["yt-dlp", "--no-check-certificates",
               "--cookies", cookie_file,
               "-o", tmpl, "--merge-output-format", "mp4", url]
    else:
        cmd = ["yt-dlp", "--no-check-certificates",
               "--cookies-from-browser", browser,
               "-o", tmpl, "--merge-output-format", "mp4", url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise Exception(f"yt-dlp 失败: {r.stderr}")
    for f in os.listdir(OUTPUT_DIR):
        if f.startswith(f"video_{ts}"):
            p = os.path.join(OUTPUT_DIR, f)
            log(f"✅ 视频已下载: {p}")
            write_log(f"[下载] 视频已下载: {p}")
            title = os.path.splitext(f)[0]
            return p, title
    raise Exception("yt-dlp 未生成视频文件")


def download_video(share_text, log, browser="chrome", cookie_file=None):
    url = extract_url(share_text)
    log(f"🔗 提取到链接: {url}")
    errors = []
    for fn, name in [(download_via_api, "API"), (download_via_f2, "f2")]:
        try:
            return fn(url, log)
        except Exception as e:
            errors.append(f"{name}: {e}")
            log(f"⚠️  {e}")
    try:
        return download_via_ytdlp(url, log, browser, cookie_file)
    except Exception as e:
        errors.append(f"yt-dlp: {e}")
        log(f"⚠️  {e}")
    raise Exception("三种方案全部失败:\n" + "\n".join(errors))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate cover/article images for WeChat articles."""
import sys, io, os, json, time, base64, requests
# UTF-8 输出。用 reconfigure 而不是替换 sys.stdout 对象 ——
# 替换会让被 import 时的调用方 buffer 被 GC 关闭（ValueError: I/O operation on closed file）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except Exception:
        pass

from pathlib import Path

# 目录层级：<root>/skills/wechat-publisher/scripts/generate_cover.py
# parents[0]=scripts  [1]=wechat-publisher  [2]=skills  [3]=<root>
# ⚠ 曾经写成 parent.parent.parent（少一层），解析到不存在的 skills/wechat-assets，
#    导致 Tier-3 封面库兜底静默失效。改动此处务必跑 _selftest 验证路径存在。
_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = _ROOT / "skills" / "wechat-publisher" / "config" / "accounts.yaml"
SECURE_DIR = _ROOT / "secure"                 # C:\Users\LMD\.qclaw\secure
COVER_LIB_DIR = _ROOT / "wechat-assets"       # C:\Users\LMD\.qclaw\wechat-assets

def load_config(account_key):
    """Load account config from YAML with proper nesting."""
    import yaml
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    if not data or 'accounts' not in data:
        return None
    for acct in data['accounts']:
        if acct.get('key') == account_key:
            return acct
    return None

def load_env(env_path):
    """Load env file."""
    env = {}
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env

def gen_zhipu(prompt, size="1536x864"):
    """Generate image via Zhipu CogView-4."""
    api_key = os.environ.get('ZHIPU_API_KEY', '')
    if not api_key:
        print("ERROR: ZHIPU_API_KEY not set")
        return None
    
    # Map size to cogview params
    size_map = {
        "1536x864": "1536x864",
        "1024x576": "1024x576",
    }
    gen_size = size_map.get(size, "1536x864")
    
    url = "https://open.bigmodel.cn/api/paas/v4/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "model": "cogview-4",
        "prompt": prompt,
        "size": gen_size,
        "n": 1
    }
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    
    try:
        resp = requests.post(url, data=data, headers=headers, timeout=120)
        result = resp.json()
        if 'data' in result and len(result['data']) > 0:
            img_url = result['data'][0]['url']
            return img_url
        else:
            print(f"Zhipu error: {result}")
            return None
    except Exception as e:
        print(f"Zhipu exception: {e}")
        return None


def gen_tencent(prompt, size="1536x864", reference_image_path=None):
    """
    Generate image via Tencent Hunyuan HY-Image-V3.0 (TokenHub).
    
    Two-step async: submit job -> poll query until complete.
    Supports reference images via 'images' parameter.
    """
    api_key = os.environ.get('TENCENT_MAAS_KEY', '')
    if not api_key:
        print("ERROR: TENCENT_MAAS_KEY not set")
        return None

    # Map size to TokenHub resolution format (colon sep)
    # TokenHub supported: 1024:576, 1280:720 (1536:864 NOT supported)
    size_map = {
        "1536x864": "1280:720",
        "1024x576": "1024:576",
    }
    resolution = size_map.get(size, "1280:720")

    payload = {
        "model": "hy-image-v3.0",
        "prompt": prompt,
        "resolution": resolution,
        "revise": 0,
        "logo_add": 0,
    }
    print(f"Tencent resolution={resolution}, has_ref={reference_image_path is not None}")

    # Handle reference image
    if reference_image_path and os.path.exists(reference_image_path):
        with open(reference_image_path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')
        ext = os.path.splitext(reference_image_path)[1].lower().lstrip('.')
        if ext == 'jpg':
            ext = 'jpeg'
        data_url = f"data:image/{ext};base64,{img_b64}"
        payload["images"] = [data_url]
        print(f"Reference image loaded: {reference_image_path} ({len(img_b64)//1024}KB)")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8"
    }
    submit_url = "https://tokenhub.tencentmaas.com/v1/api/image/submit"
    query_url = "https://tokenhub.tencentmaas.com/v1/api/image/query"

    try:
        # Step 1: Submit job
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        resp = requests.post(submit_url, data=data, headers=headers, timeout=60)
        result = resp.json()
        job_id = result.get('id')
        request_id = result.get('request_id', '')
        if not job_id:
            print(f"Tencent submit error (no job_id): {result}")
            return None
        print(f"Tencent job submitted: {job_id} (req: {request_id[:16]}...)")

        # Step 2: Poll query until complete
        max_polls = 30        # max 30*10s = 300s waiting
        poll_interval = 10     # seconds
        for attempt in range(max_polls):
            time.sleep(poll_interval)
            query_payload = {
                "model": "hy-image-v3.0",
                "id": job_id
            }
            qdata = json.dumps(query_payload, ensure_ascii=False).encode('utf-8')
            qresp = requests.post(query_url, data=qdata, headers=headers, timeout=30)
            qresult = qresp.json()
            status = qresult.get('status', 'unknown')
            print(f"  Poll [{attempt+1}/{max_polls}] status={status}")
            if status == 'completed':
                data_list = qresult.get('data', [])
                if data_list and len(data_list) > 0:
                    img_url = data_list[0].get('url', '')
                    if img_url:
                        print(f"Tencent success: {img_url[:64]}...")
                        return img_url
                print(f"Tencent completed but no image URL: {qresult}")
                return None
            elif status in ('failed', 'error'):
                print(f"Tencent job failed: {qresult}")
                return None

        print(f"Tencent job timed out after {max_polls * poll_interval}s")
        return None

    except Exception as e:
        print(f"Tencent exception: {e}")
        return None

def download_image(url, output_path):
    """Download image from URL to local file."""
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(resp.content)
            print(f"Downloaded to {output_path}")
            return True
    except Exception as e:
        print(f"Download failed: {e}")
    return False

def pick_fallback(account_key, image_type="cover"):
    """Pick a random image from cover library.

    路径优先取 accounts.yaml 的 cover_library（唯一真源），
    退化时才用 COVER_LIB_DIR/<cover_library_<key>>。
    """
    import random, shutil
    cfg = load_config(account_key) or {}
    configured = cfg.get('cover_library', '')

    lib_dir = None
    if configured and os.path.isdir(configured):
        lib_dir = Path(configured)
    elif (COVER_LIB_DIR / f"cover_library_{account_key}").is_dir():
        lib_dir = COVER_LIB_DIR / f"cover_library_{account_key}"

    if lib_dir:
        images = list(lib_dir.glob("*.png")) + list(lib_dir.glob("*.jpg"))
        if images:
            chosen = random.choice(images)
            output = Path(f"output_{image_type}_{account_key}.png")
            shutil.copy(chosen, output)
            print(f"Fallback: copied {chosen.name} -> {output}  (lib={lib_dir})")
            return str(output)
        print(f"Fallback 失败：封面库为空 {lib_dir}")
        return None

    print(f"Fallback 失败：封面库路径不存在 "
          f"(accounts.yaml.cover_library={configured!r}, 默认={COVER_LIB_DIR})")
    return None

def main():
    if len(sys.argv) < 4:
        print("Usage: python generate_cover.py <account_key> <type> <prompt> [output] [--ref-path PATH]")
        print("  type: cover|img1|img2|img3")
        print("  --ref-path: override reference image file path")
        sys.exit(1)
    
    account_key = sys.argv[1]
    img_type = sys.argv[2]
    prompt = sys.argv[3]
    output = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].startswith('--') else f"{img_type}_{account_key}.png"
    
    # Parse optional --ref-path argument
    override_path = None
    for i, arg in enumerate(sys.argv):
        if arg == '--ref-path' and i + 1 < len(sys.argv):
            override_path = sys.argv[i + 1]
    
    # Load config
    config = load_config(account_key)
    if not config:
        print(f"ERROR: account {account_key} not found in config")
        sys.exit(1)
    
    env_path = config.get('env_file', str(SECURE_DIR / f'.env_{account_key}'))
    env = load_env(env_path)
    for k, v in env.items():
        os.environ.setdefault(k, v)
    
    size = "1536x864" if img_type == "cover" else "1024x576"
    
    print(f"Generating {img_type} ({size}) for {account_key}...")
    print(f"Prompt: {prompt}")
    
    # ── IP角色参考图配置 ──
    # character_dir 是完整图片路径，设了就传参考图，空则不传
    # img_type == "cover" → 取 ip_character.cover
    # img_type == "img1|img2|img3|img4|img5" → 取 ip_character.article
    reference_img = None
    ip_config = config.get('ip_character', {})
    ref_key = "cover" if img_type == "cover" else "article"
    ref_cfg = ip_config.get(ref_key, {})

    img_path = override_path or ref_cfg.get('character_dir', '')
    if img_path:
        path = Path(img_path)
        if path.exists():
            reference_img = str(path)
            kb = os.path.getsize(reference_img) // 1024
            print(f"[{ref_key}] Reference image loaded: {os.path.basename(img_path)} ({kb}KB)")
        else:
            print(f"[{ref_key}] character_dir set but file not found: {img_path} → auto-fallback")
    else:
        print(f"[{ref_key}] No character_dir set, generating without reference")
    
    use_ref = reference_img is not None

    # Tier 1: Try Tencent Hunyuan FIRST (supports reference image)
    # 重试3次，每次间隔15秒防任务上限
    img_url = None
    for attempt in range(3):
        if attempt > 0:
            delay = 15
            print(f"Tencent retry [{attempt+1}/3] after {delay}s (rate limit cooldown)...")
            time.sleep(delay)
        img_url = gen_tencent(prompt, size, reference_image_path=reference_img)
        if img_url:
            if download_image(img_url, output):
                print(f"SUCCESS (Tencent): {output}")
                sys.exit(0)
    
    # Tier 2: Try Zhipu CogView-4 as fallback
    print("Tencent failed after 3 retries, trying Zhipu CogView-4...")
    img_url = gen_zhipu(prompt, size)
    if img_url:
        if download_image(img_url, output):
            print(f"SUCCESS (Zhipu): {output}")
            sys.exit(0)
    
    # Tier 3: Fallback to local cover library
    print("All API methods failed, picking fallback from cover library...")
    fallback = pick_fallback(account_key, img_type)
    if fallback:
        if fallback != output:
            import shutil
            shutil.copy(fallback, output)
        print(f"FALLBACK SUCCESS: {output}")
        sys.exit(0)
    
    print(f"FAILED: Could not generate {img_type}")
    sys.exit(1)

if __name__ == '__main__':
    main()

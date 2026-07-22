"""
upload_material.py - 上传图片到微信素材库（永久素材接口）
用法：python upload_material.py <account> <image_path> [image_path2 ...] [--type thumb]

参数：
  account    : junxun | lanmuda（accounts.yaml 中的 key）
  image_path : 图片路径（可多个）
  --type     : thumb（缩略图）或 image（默认图片）

返回：每行一个 media_id
"""
import sys, io, os, json, requests, argparse, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def load_env(env_file):
    """加载 .env 文件到字典"""
    env = {}
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env

def get_token(app_id, app_secret, proxy):
    """获取微信 access_token"""
    url = f"{proxy}cgi-bin/token"
    params = {"grant_type": "client_credential", "appid": app_id, "secret": app_secret}
    r = requests.get(url, params=params, timeout=30, verify=False)
    r.raise_for_status()
    data = r.json()
    if "access_token" not in data:
        raise Exception(f"Token failed: {data}")
    return data["access_token"]

def upload_image_for_article(token, image_path, proxy):
    """
    上传正文配图（使用 media/uploadimg，返回含 ?from=appmsg 的 URL）
    接口：POST /cgi-bin/media/uploadimg
    这是正文配图的正确接口，返回的 URL 带 from=appmsg 标记
    """
    url = f"{proxy}cgi-bin/media/uploadimg?access_token={token}"
    with open(image_path, 'rb') as f:
        files = {'media': (os.path.basename(image_path), f, 'image/png')}
        r = requests.post(url, files=files, timeout=60, verify=False)
    r.raise_for_status()
    data = r.json()
    if "url" not in data:
        raise Exception(f"Upload failed: {data}")
    # 返回格式与 upload_material_permanent 一致：(media_id, url)
    # media/uploadimg 不返回 media_id，所以 media_id 置空
    return "", data["url"]


def upload_material_permanent(token, image_path, proxy):
    """
    上传永久素材（封面缩略图专用）
    接口：POST /cgi-bin/material/add_material?type=thumb
    ⚠️ 仅用于 --type thumb（封面缩略图），正文配图禁止使用此接口
    """
    url = f"{proxy}cgi-bin/material/add_material?access_token={token}&type=thumb"
    with open(image_path, 'rb') as f:
        files = {'media': (os.path.basename(image_path), f, 'image/png')}
        r = requests.post(url, files=files, timeout=60, verify=False)
    r.raise_for_status()
    data = r.json()
    if "media_id" not in data:
        raise Exception(f"Upload failed: {data}")
    return data["media_id"], data.get("url", "")

def upload_material_temp(token, image_path, proxy, img_type="image"):
    """
    上传临时素材（仅返回 media_id，3天过期）
    接口：POST /cgi-bin/media/upload
    """
    url = f"{proxy}cgi-bin/media/upload?access_token={token}&type={img_type}"
    with open(image_path, 'rb') as f:
        files = {'media': (os.path.basename(image_path), f, 'image/png')}
        r = requests.post(url, files=files, timeout=60, verify=False)
    r.raise_for_status()
    data = r.json()
    if "media_id" not in data:
        raise Exception(f"Upload failed: {data}")
    return data["media_id"], ""

def main():
    parser = argparse.ArgumentParser(description="上传图片到微信素材库")
    parser.add_argument("account", help="账号 key（junxun/lanmuda）")
    parser.add_argument("images", nargs="+", help="图片路径（可多个）")
    parser.add_argument("--type", choices=["image", "thumb"], default="image",
                        help="素材类型：image（图片）或 thumb（缩略图）")
    parser.add_argument("--permanent", action="store_true", help="使用永久素材接口（返回 URL）")
    args = parser.parse_args()

    # 读取配置
    config_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_file = os.path.join(os.path.dirname(config_dir), "config", "accounts.yaml")

    import yaml
    with open(yaml_file, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    # 用 key 字段匹配账号
    acct_cfg = next((a for a in cfg['accounts'] if a.get('key') == args.account), None)
    if not acct_cfg:
        # 兼容旧的 name 匹配
        acct_cfg = next(a for a in cfg['accounts'] if a['name'] == args.account)
    
    env = load_env(acct_cfg['env_file'])
    proxy = cfg['global']['proxy']

    # 使用正确的 env key 名
    app_id = env.get('WECHAT_APP_ID') or env.get('APP_ID')
    app_secret = env.get('WECHAT_APP_SECRET') or env.get('APP_SECRET')
    
    if not app_id or not app_secret:
        raise Exception(f"Missing WECHAT_APP_ID or WECHAT_APP_SECRET in {acct_cfg['env_file']}")

    token = get_token(app_id, app_secret, proxy)
    print(f"Token OK: {token[:20]}...", file=sys.stderr)

    # 🔥 接口分发规则（硬性）
    # --type thumb    → material/add_material（封面缩略图专用）
    # --type image    → media/uploadimg（正文配图专用），禁止使用 material/add_material
    # --permanent     → 仅对 thumb 有效；image 类型不区分永久/临时，都走 media/uploadimg

    for path in args.images:
        if args.type == "thumb":
            # 封面缩略图：走 material/add_material?type=thumb
            if args.permanent:
                media_id, url = upload_material_permanent(token, path, proxy)
            else:
                media_id, url = upload_material_temp(token, path, proxy, "thumb")
                url = None  # 临时素材不返回 URL
            if url:
                print(f"{media_id}\t{url}")
            else:
                print(media_id)
        else:
            # 🔥 正文配图：强制走 media/uploadimg，返回含 from=appmsg 的 URL
            # 禁止使用 material/add_material（返回的 URL 无此标记，微信不显示）
            _, url = upload_image_for_article(token, path, proxy)
            if url:
                print(f"\t{url}")
            else:
                print("")

if __name__ == '__main__':
    main()

"""
upload_article_image.py - 微信图片上传（统一入口）

⚠️ 本项目唯一的上传脚本。upload_material.py 已删除（历史遗留，功能合并至此）。

用法：
  # 正文配图（推荐用 img_tag 输出直接插正文）
  python upload_article_image.py <account> img1.png img2.png [--output url|img_tag]

  # 封面缩略图
  python upload_article_image.py <account> cover.png --type thumb [--permanent]

接口分发（硬性，不可绕过）：
  --type image (默认) → media/uploadimg      → 返回 ?from=appmsg URL，正文正常显示
  --type thumb        → material/add_material → 返回 media_id，封面缩略图专用
"""
import sys, io, os, json, requests, argparse
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def load_env(env_file):
    env = {}
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env

def get_token(app_id, app_secret, proxy):
    url = f"{proxy}cgi-bin/token"
    params = {"grant_type": "client_credential", "appid": app_id, "secret": app_secret}
    r = requests.get(url, params=params, timeout=30, verify=False)
    r.raise_for_status()
    data = r.json()
    if "access_token" not in data:
        raise Exception(f"Token failed: {data}")
    return data["access_token"]

def upload_article_image(token, image_path, proxy):
    """
    上传图文正文内嵌图片
    接口：POST /cgi-bin/media/uploadimg?access_token=TOKEN
    返回：{'media_id': '', 'url': 'https://mmecoa.qpic.cn/...?from=appmsg'}
    注：media/uploadimg 不返回 media_id，所以 media_id 置空
    """
    url = f"{proxy}cgi-bin/media/uploadimg?access_token={token}"
    with open(image_path, 'rb') as f:
        files = {'media': (os.path.basename(image_path), f, 'image/png')}
        r = requests.post(url, files=files, timeout=60, verify=False)
    r.raise_for_status()
    data = r.json()
    if "url" not in data:
        raise Exception(f"Upload failed: {data}")
    return data["url"]


def upload_thumb(token, image_path, proxy, permanent=True):
    """
    上传封面缩略图
    接口：POST /cgi-bin/material/add_material?access_token=TOKEN&type=thumb
    返回：(media_id, url|'')
    仅用于封面缩略图，严禁用于正文配图
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

def main():
    parser = argparse.ArgumentParser(description="微信图片上传（统一入口）")
    parser.add_argument("account", help="账号 key（junxun/lanmuda）")
    parser.add_argument("images", nargs="+", help="图片路径（可多个）")
    parser.add_argument("--type", choices=["image", "thumb"], default="image",
                        help="类型：image=正文配图, thumb=封面缩略图")
    parser.add_argument("--permanent", action="store_true",
                        help="thumb 类型时是否获取永久 media_id（默认 false，仅 thumb 类型有效）")
    parser.add_argument("--output", choices=["url", "img_tag"], default="url",
                        help="image 类型的输出格式：url（仅URL）或 img_tag（完整img标签；thumb 类忽略此参数）")
    args = parser.parse_args()

    # 读取配置
    config_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_file = os.path.join(os.path.dirname(config_dir), "config", "accounts.yaml")

    import yaml
    with open(yaml_file, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    acct_cfg = next((a for a in cfg['accounts'] if a.get('key') == args.account), None)
    if not acct_cfg:
        acct_cfg = next(a for a in cfg['accounts'] if a['name'] == args.account)

    env = load_env(acct_cfg['env_file'])
    proxy = cfg['global']['proxy']
    app_id = env.get('WECHAT_APP_ID') or env.get('APP_ID')
    app_secret = env.get('WECHAT_APP_SECRET') or env.get('APP_SECRET')

    if not app_id or not app_secret:
        raise Exception(f"Missing WECHAT_APP_ID or WECHAT_APP_SECRET in {acct_cfg['env_file']}")

    token = get_token(app_id, app_secret, proxy)
    print(f"Token OK: {token[:20]}...", file=sys.stderr)

    # 接口分发（硬性规则）
    # --type image → media/uploadimg（正文配图），返回 ?from=appmsg URL
    # --type thumb → material/add_material?type=thumb（封面缩略图），返回 media_id
    for path in args.images:
        if args.type == "thumb":
            media_id, url = upload_thumb(token, path, proxy, args.permanent)
            if args.permanent and url:
                print(f"{media_id}\t{url}")
            else:
                print(media_id)
        else:
            url = upload_article_image(token, path, proxy)
            if args.output == "img_tag":
                name = os.path.basename(path)
                print(f'<img src="{url}" style="width:85%;display:block;margin:20px auto;border-radius:8px;" alt="{name}"/>')
            else:
                print(url)

if __name__ == '__main__':
    main()

"""
upload_article_image.py - 上传文章正文配图专用
使用 media/uploadimg 接口（非 material/add_material）
返回微信认可的正文内嵌 URL
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
    上传图文消息内图片
    接口：POST /cgi-bin/media/uploadimg?access_token=TOKEN
    返回：JSON { "url": "https://mmecoa.qpic.cn/..." }
    这个 URL 可以直接放在正文 <img src="URL"> 中使用
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

def main():
    parser = argparse.ArgumentParser(description="上传文章正文配图（media/uploadimg接口）")
    parser.add_argument("account", help="账号 key（junxun/lanmuda）")
    parser.add_argument("images", nargs="+", help="图片路径（可多个）")
    parser.add_argument("--output", choices=["url", "img_tag"], default="url",
                        help="输出格式：url（仅URL）或 img_tag（完整img标签）")
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

    for path in args.images:
        url = upload_article_image(token, path, proxy)
        if args.output == "img_tag":
            name = os.path.basename(path)
            print(f'<img src="{url}" style="width:85%;display:block;margin:20px auto;border-radius:8px;" alt="{name}"/>')
        else:
            print(url)

if __name__ == '__main__':
    main()

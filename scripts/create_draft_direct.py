# -*- coding: utf-8 -*-
import sys, io, os, json, requests, time
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
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["access_token"]

# 配图URL
img1_url = "http://mmecoa.qpic.cn/sz_mmecoa_jpg/M5fxkjNZLxUOrKbibM9aNWeKpYpSRLFeIoIScxXXyibkrWBN4DTdFSAkSkApL4fI7lNbZzz0pbIib1nsx4KMtCJjSYV82rQ80J4y1MB6vhkrbk/0?wx_fmt=jpeg"
img2_url = "http://mmecoa.qpic.cn/mmecoa_jpg/M5fxkjNZLxVY5RMkx0ia8sQYZKdnicLUibB9EDFmgNhVLv53I5ueLoyibzS1XNdNVCgW3XwuYzSKkFKMvrRqF9xL7HDSXQG3dIY2ORxttnMcLqY/0?wx_fmt=jpeg"
img3_url = "http://mmecoa.qpic.cn/mmecoa_jpg/M5fxkjNZLxWqbYoicfib0lcT48B7fHGkyB2t4tA6XicKTyWicFWeicmAg63aqMMpSnRppP0WlGQmWqYHFBXIXUETS2KEJracPficiaQkmpD29TZSHo/0?wx_fmt=jpeg"

content = f'''<p>2026年的人形机器人赛道，正在上演一场荒诞的分裂。</p>
<p>一边是特斯拉Optimus、Figure等全球玩家轮番召开发布会，从双足跑跳、大模型交互卷到参数上限，用炫酷Demo收割行业关注；另一边是冰冷的商业化现实——全行业90%的人形机器人产品，仍停留在实验室原型阶段，能实现规模化量产交付、跑通稳定商业闭环的玩家，屈指可数。</p>
<p>当所有人都把目光死死盯在"人形整机"的秀场时，一家中国企业，已经悄悄拿下了全球力控人形双臂出货量第一的宝座。</p>
<p style="text-align:center"><img src="{img1_url}" style="max-width:100%;height:auto;" alt="天机智能Marvin系列机械臂"></p>
<p>最新官方数据显示，截至2026年3月，天机智能Marvin系列力控人形双臂当年新增订单已突破10000台，累计工业协作臂出货超30000台，服务全球1000+工业客户、45+家头部人形机器人企业，是全球首家、也是唯一一家实现全关节力控人形双臂万台级规模化交付的企业。</p>
<p>2025年全年营收约2亿元，其中工业协作臂与人形双臂业务各占半壁江山，在烧钱成风的人形机器人赛道，率先实现了核心业务的规模化盈利。</p>
<h2>行业最大认知误区：终局赢在手臂，不是腿</h2>
<p>长期以来，人形机器人赛道陷入了一个致命的认知偏差：所有人都在卷"能不能走、能不能跑"的下肢能力，卷"能不能对话、能不能规划"的大模型能力，却忽略了一个最本质的商业逻辑——</p>
<p><strong>人形机器人最终要替代人完成劳动，核心竞争力从来不是走路和聊天，而是能不能像人一样，精准、柔性、安全地完成操作任务。</strong></p>
<p style="text-align:center"><img src="{img2_url}" style="max-width:100%;height:auto;" alt="力控机械臂作业场景"></p>
<p>无论是工厂里的精密装配、柔性打磨，还是家庭里的端茶倒水、整理家务，90%以上的落地场景，最终的执行载体都是上肢的机械臂。没有高性能力控双臂，再先进的大模型都是纸上谈兵，再流畅的双足步态都是空中楼阁。</p>
<p>而力控技术，恰恰是机械臂领域的"珠穆朗玛峰"，更是横在具身智能落地面前最大的鸿沟。</p>
<h2>四款新品：把行业没说出口的痛点全堵上了</h2>
<p>2026年，天机智能发布M6S Lite、M6S-809、M6S Long、M20S四款全新产品，完成了从轻量入门到重载旗舰的全场景覆盖。</p>
<p><strong>M6S Lite</strong>：7自由度力控臂，自重仅8kg，却能稳稳拎起5kg负载，负重比达62.5%，行业领先。平均功耗仅200W，小型四足机器人、轻量AGV底盘都能轻松搭载。</p>
<p><strong>M6S-809</strong>：标准版，自重12.7kg，额定负载5kg，重复定位精度±0.04mm，踩中了3C电子精密装配的准入门槛。原生支持一拖二控制器，一块主板同时控制两条臂，毫秒级同步。</p>
<p style="text-align:center"><img src="{img3_url}" style="max-width:100%;height:auto;" alt="双臂协同作业"></p>
<p><strong>M6S Long</strong>：臂展920mm，照样保持3kg额定负载，重复定位精度±0.04mm。之前需要两台臂才能干完的活，现在一台就能搞定，部署成本直接砍半。</p>
<p><strong>M20S</strong>：重载款，自重30kg，单臂额定负载20kg，双臂协同最大负载可达50kg，负重比66.7%。全关节配高量程MEMS扭矩传感器，既能稳稳拎起20kg电池包，又能通过力控精准控制力度，不会压坏工件。</p>
<h2>抄不走的护城河</h2>
<p>天机智能构建了从基因传承、核心器件、控制算法到量产能力的全栈护城河：</p>
<ul>
<li><strong>双基因传承</strong>：安川电机+长盈精密，百年机器人巨头的品控标准与大规模量产能力</li>
<li><strong>MEMS力传感技术</strong>：全球首创并规模化量产，灵敏度是传统方案10倍，抗冲击能力提升4倍</li>
<li><strong>Fusion运动控制系统</strong>：为AI大模型打造的"小脑"，位置、力、刚度全部开放为标准API</li>
</ul>
<p>今天的天机智能，已经成为具身智能产业的"物理接口层"基础设施提供商，占据了人形机器人赛道最关键的生态位。它就像PC时代的英特尔、智能手机时代的高通，成为了人形机器人时代的核心硬件底座。</p>
<p><strong>人形机器人的战争，早已进入「量产定生死」的下半场。</strong></p>'''

# 读取配置
config_dir = os.path.dirname(os.path.abspath(__file__))
yaml_file = os.path.join(os.path.dirname(config_dir), "config", "accounts.yaml")

import yaml
with open(yaml_file, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

acct_cfg = next((a for a in cfg['accounts'] if a.get('key') == 'lanmuda'), None)
env = load_env(acct_cfg['env_file'])
proxy = cfg['global']['proxy']

app_id = env.get('WECHAT_APP_ID') or env.get('APP_ID')
app_secret = env.get('WECHAT_APP_SECRET') or env.get('APP_SECRET')

token = get_token(app_id, app_secret, proxy)
print(f"Token OK: {token[:20]}...")

# 创建草稿
url = f"{proxy}cgi-bin/draft/add?access_token={token}"

payload = {
    "articles": [{
        "title": "万台交付全球第一，这家中国企业撕开了人形机器人量产的终局",
        "author": "岚牧哒",
        "digest": "2026年人形机器人赛道进入量产定生死的下半场，天机智能以万台级交付成为全球力控人形双臂出货量第一，重新定义了行业终局。",
        "content": content,
        "thumb_media_id": "Pr_xVfmq0Kz1JQWsflFwzplKirUV27-hPc4mHd-1a9bIbVSt7jFzqlYjyB_fIwh9",
        "need_open_comment": 0,
        "only_fans_can_comment": 0
    }]
}

headers = {"Content-Type": "application/json; charset=utf-8"}
data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
r = requests.post(url, data=data, headers=headers, timeout=60)
r.raise_for_status()
resp = r.json()
print(f"Draft response: {resp}")

if resp.get("errcode", 0) == 0:
    print(f"Draft media_id: {resp.get('media_id', '')}")
else:
    print(f"Draft failed: {resp}")
import os, json, requests

TOKEN = os.environ.get("LONG_LIVED_TOKEN", "")
USER_ID = "27645316161821605"
url = f"https://graph.instagram.com/v21.0/{USER_ID}/media"
params = {
    "fields": "id,caption,media_type,timestamp,like_count,comments_count,permalink",
    "limit": 25,
    "access_token": TOKEN
}
r = requests.get(url, params=params, timeout=30)
data = r.json()
posts = data.get("data", [])
for p in posts:
    p["engagement"] = p.get("like_count", 0) + p.get("comments_count", 0) * 3
posts.sort(key=lambda x: x["engagement"], reverse=True)
for i, p in enumerate(posts[:10], 1):
    cap = p.get("caption", "")[:60].replace("\n", " ")
    print(f"[{i}] {p['engagement']}eng | {p['media_type']} | {p['timestamp'][:10]} | {cap}")
    print(f"    {p['permalink']}")

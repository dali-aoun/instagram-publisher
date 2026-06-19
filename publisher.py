"""
publisher.py — Instagram auto-publisher (GitHub Actions)
3 images + 2 reels par jour, espaces 3h
Tunisia UTC+1 : 07h(img) 10h(reel) 13h(img) 16h(reel) 19h(img)
"""

import os, sys, json, time, random, requests, traceback
from datetime import datetime, timezone, timedelta

IG_USER_ID  = os.environ.get("INSTAGRAM_USER_ID", "27645316161821605")
IG_TOKEN    = os.environ.get("LONG_LIVED_TOKEN", "")
PEXELS_KEY  = os.environ.get("PEXELS_API_KEY", "")
FUNNEL_URL  = "https://smoothie.thehappy-healthy-life.com"
BASE_URL    = "https://graph.instagram.com/v21.0"
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
STATE_FILE  = os.path.join(BASE_DIR, "published_state.json")
LOG_FILE    = os.path.join(BASE_DIR, "publish_log.txt")
CAPS_FILE   = os.path.join(BASE_DIR, "captions.json")

TZ_TUNIS = timezone(timedelta(hours=1))

# UTC hour -> slot type  (Tunisia = UTC+1)
SCHEDULE = {6: "image", 9: "reel", 12: "image", 15: "reel", 18: "image"}

IMAGE_KEYWORDS = [
    "smoothie healthy woman portrait",
    "weight loss women fitness",
    "healthy green smoothie",
    "women wellness morning routine",
    "healthy food women over 40",
    "green smoothie fresh fruit",
    "women yoga wellness",
    "flat belly healthy lifestyle",
    "healthy morning breakfast",
    "women fitness over 40",
]

REEL_KEYWORDS = [
    "smoothie making blender",
    "healthy morning routine woman",
    "women fitness home workout",
    "yoga morning routine woman",
    "green smoothie preparation",
    "smoothie bowl making",
    "women morning wellness",
    "healthy drink preparation",
]


def log(msg):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state():
    defaults = {"image_idx": 0, "reel_idx": 0, "img_kw": 0, "reel_kw": 0, "published": []}
    if not os.path.exists(STATE_FILE):
        return defaults
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in defaults.items():
                data.setdefault(k, v)
            return data
    except Exception:
        return defaults


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_captions():
    with open(CAPS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def pexels_image(keyword):
    headers = {"Authorization": PEXELS_KEY}
    params  = {"query": keyword, "per_page": 15, "orientation": "portrait"}
    try:
        r = requests.get("https://api.pexels.com/v1/search",
                         headers=headers, params=params, timeout=30)
        if r.status_code == 200:
            photos = r.json().get("photos", [])
            if photos:
                photo = random.choice(photos[:10])
                return photo["src"]["large2x"]
        log(f"  Pexels image HTTP {r.status_code}")
    except Exception as e:
        log(f"  pexels_image erreur: {e}")
    return None


def pexels_video(keyword):
    headers = {"Authorization": PEXELS_KEY}
    params  = {"query": keyword, "per_page": 15, "orientation": "portrait", "size": "medium"}
    try:
        r = requests.get("https://api.pexels.com/videos/search",
                         headers=headers, params=params, timeout=30)
        if r.status_code != 200:
            log(f"  Pexels video HTTP {r.status_code}")
            return None
        videos = r.json().get("videos", [])
        random.shuffle(videos)
        for video in videos[:8]:
            dur = video.get("duration", 0)
            if not (3 <= dur <= 90):
                continue
            files = video.get("video_files", [])
            # Prefer portrait HD from pexels CDN
            for quality in ("hd", "sd", ""):
                for vf in files:
                    link = vf.get("link", "")
                    if (vf.get("file_type") == "video/mp4" and
                            "videos.pexels.com" in link and
                            vf.get("height", 0) >= vf.get("width", 1)):
                        if not quality or vf.get("quality") == quality:
                            return link
            # Fallback: any pexels CDN mp4
            for vf in files:
                link = vf.get("link", "")
                if vf.get("file_type") == "video/mp4" and "videos.pexels.com" in link:
                    return link
    except Exception as e:
        log(f"  pexels_video erreur: {e}")
    return None


def pexels_with_fallback(keyword, keywords_list, fetch_fn):
    url = fetch_fn(keyword)
    if url:
        return url
    for kw in keywords_list:
        if kw == keyword:
            continue
        url = fetch_fn(kw)
        if url:
            return url
    return None


def ig_create_image(image_url, caption):
    data = {"image_url": image_url, "caption": caption, "access_token": IG_TOKEN}
    r = requests.post(f"{BASE_URL}/{IG_USER_ID}/media", data=data, timeout=60)
    return r.status_code, r.json()


def ig_create_reel(video_url, caption):
    data = {
        "media_type":   "REELS",
        "video_url":    video_url,
        "caption":      caption,
        "share_to_feed": "true",
        "access_token": IG_TOKEN,
    }
    r = requests.post(f"{BASE_URL}/{IG_USER_ID}/media", data=data, timeout=60)
    return r.status_code, r.json()


def ig_wait_ready(container_id, max_sec=360):
    params = {"fields": "status_code,status", "access_token": IG_TOKEN}
    for i in range(max_sec // 10):
        time.sleep(10)
        try:
            r = requests.get(f"{BASE_URL}/{container_id}", params=params, timeout=30)
            if r.status_code == 200:
                d = r.json()
                sc = d.get("status_code", "")
                if sc == "FINISHED":
                    log(f"  Container pret ({(i+1)*10}s)")
                    return True
                if sc == "ERROR":
                    log(f"  Container ERROR: {d.get('status')}")
                    return False
                log(f"  status={sc} ({(i+1)*10}s)...")
        except Exception as e:
            log(f"  wait erreur: {e}")
    log(f"  Timeout {max_sec}s")
    return False


def ig_publish(container_id):
    data = {"creation_id": container_id, "access_token": IG_TOKEN}
    r = requests.post(f"{BASE_URL}/{IG_USER_ID}/media_publish", data=data, timeout=60)
    return r.status_code, r.json()


def main():
    if not IG_TOKEN:
        log("ERREUR: LONG_LIVED_TOKEN manquant")
        sys.exit(1)
    if not PEXELS_KEY:
        log("ERREUR: PEXELS_API_KEY manquant")
        sys.exit(1)

    now_utc   = datetime.now(timezone.utc)
    now_tunis = now_utc.astimezone(TZ_TUNIS)
    utc_hour  = now_utc.hour

    slot_type = SCHEDULE.get(utc_hour)
    if not slot_type:
        log(f"Pas de slot pour UTC {utc_hour}h - skip")
        sys.exit(0)

    slot_key = f"{now_tunis.strftime('%Y-%m-%d')}_{now_tunis.hour:02d}h"
    log(f"=== Instagram Publisher {slot_key} type={slot_type} ===")

    state    = load_state()
    captions = load_captions()

    # Anti-doublon
    if any(p["slot"] == slot_key for p in state["published"]):
        log(f"Deja publie: {slot_key} - skip")
        sys.exit(0)

    media_id = None

    if slot_type == "image":
        imgs    = captions["image_captions"]
        idx     = state["image_idx"] % len(imgs)
        caption = imgs[idx]
        kw_idx  = state["img_kw"] % len(IMAGE_KEYWORDS)
        keyword = IMAGE_KEYWORDS[kw_idx]

        log(f"Recherche image Pexels: {keyword}")
        image_url = pexels_with_fallback(keyword, IMAGE_KEYWORDS, pexels_image)
        if not image_url:
            log("ERREUR: aucune image Pexels disponible")
            sys.exit(1)
        log(f"Image: {image_url[:80]}...")

        sc, resp = ig_create_image(image_url, caption)
        if sc not in (200, 201) or "id" not in resp:
            log(f"ERREUR container image: {sc} {resp}")
            sys.exit(1)
        container_id = resp["id"]
        log(f"Container: {container_id} - attente 20s...")
        time.sleep(20)

        sc2, resp2 = ig_publish(container_id)
        if sc2 not in (200, 201) or "id" not in resp2:
            log(f"ERREUR publication image: {sc2} {resp2}")
            sys.exit(1)
        media_id = resp2["id"]
        log(f"OK image publiee: {media_id}")

        state["image_idx"] = (idx + 1) % len(imgs)
        state["img_kw"]    = (kw_idx + 1) % len(IMAGE_KEYWORDS)

    elif slot_type == "reel":
        reels   = captions["reel_captions"]
        idx     = state["reel_idx"] % len(reels)
        caption = reels[idx]
        kw_idx  = state["reel_kw"] % len(REEL_KEYWORDS)
        keyword = REEL_KEYWORDS[kw_idx]

        log(f"Recherche video Pexels: {keyword}")
        video_url = pexels_with_fallback(keyword, REEL_KEYWORDS, pexels_video)
        if not video_url:
            log("ERREUR: aucune video Pexels disponible")
            sys.exit(1)
        log(f"Video: {video_url[:80]}...")

        sc, resp = ig_create_reel(video_url, caption)
        if sc not in (200, 201) or "id" not in resp:
            log(f"ERREUR container reel: {sc} {resp}")
            sys.exit(1)
        container_id = resp["id"]
        log(f"Reel container: {container_id} - processing...")

        if not ig_wait_ready(container_id, max_sec=360):
            log("ERREUR: container reel non pret")
            sys.exit(1)

        sc2, resp2 = ig_publish(container_id)
        if sc2 not in (200, 201) or "id" not in resp2:
            log(f"ERREUR publication reel: {sc2} {resp2}")
            sys.exit(1)
        media_id = resp2["id"]
        log(f"OK reel publie: {media_id}")

        state["reel_idx"] = (idx + 1) % len(reels)
        state["reel_kw"]  = (kw_idx + 1) % len(REEL_KEYWORDS)

    state["published"].append({
        "slot":     slot_key,
        "type":     slot_type,
        "media_id": media_id,
        "at":       now_utc.isoformat(),
    })
    save_state(state)
    log(f"=== Termine {slot_key} -> {media_id} ===")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log(f"EXCEPTION:\n{traceback.format_exc()}")
        sys.exit(1)

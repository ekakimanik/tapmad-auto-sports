import sys
import os
import json
import re
import subprocess
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# --- CONFIGURATION ---
PHONE_NUMBER = "01690053223"
PIN = "3223"
DEVICE_ID = "__1ea14efeb3f34338a42a044d960c6351" 
AES_KEY = b"4nH4LlNWMpVYMP3FNwSsUa030ldjDqUy"

AUTH_FILE = os.path.expanduser("~/tapmad_auth.json")
M3U_FILE = os.path.expanduser("~/tapmad_live.m3u")
REPO_DIR = os.path.expanduser("~/tapmad-auto-sports")

def do_login():
    print("🔐 Logging in to get a fresh token...")
    login_url = "https://backend-app.tapmad.com/api/SignInFreeMobileOperatorTokenByPin"
    headers = {
        "device-id": DEVICE_ID,
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": "okhttp/4.9.3"
    }
    try:
        res = requests.post(login_url, headers=headers, data={"MobileNo": PHONE_NUMBER, "UserPin": PIN})
        data = res.json()
        token = data["User"]["jwtToken"]
        user_id = data["User"]["UserId"]
        
        with open(AUTH_FILE, "w") as f:
            json.dump({"token": token, "user_id": user_id}, f)
        print("✅ Login successful! Token saved.")
    except KeyError:
        print("❌ Login failed. Message from Tapmad:")
        print(data.get("Response", {}).get("message", "Unknown error"))
        sys.exit(1)

def find_matches(data):
    matches = []
    if isinstance(data, dict):
        if 'ContentVideoName' in data and 'ContentEntityId' in data:
            matches.append({'title': data['ContentVideoName'], 'id': data['ContentEntityId']})
        for key in data:
            matches.extend(find_matches(data[key]))
    elif isinstance(data, list):
        for item in data:
            matches.extend(find_matches(item))
    return matches

def do_scrape():
    if not os.path.exists(AUTH_FILE):
        print("❌ No token found. Please run 'python ~/tapmad_master.py login' first.")
        return
        
    with open(AUTH_FILE, "r") as f:
        auth = json.load(f)
        token = auth["token"]
        user_id = auth["user_id"]

    print("Fetching live matches (Using saved token)...")
    session = requests.Session()
    headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    
    try:
        home_res = session.get("https://www.tapmad.com/", headers=headers)
        build_id = re.search(r'"buildId":"([^"]+)"', home_res.text).group(1)
        sports_url = f"https://www.tapmad.com/_next/data/{build_id}/sports.json"
        sports_data = session.get(sports_url, headers=headers).json()
        all_matches = find_matches(sports_data)
        unique_matches = {v['id']: v for v in all_matches}.values()
    except Exception as e:
        print(f"❌ Failed to fetch match list: {e}")
        return

    api_url = "https://backend-app.tapmad.com/api/getStreamEncrypt"
    m3u_lines = ["#EXTM3U"]
    clipboard_data = []
    count = 0

    print("\n========================================")
    print(" 🏏 LIVE MATCHES & DIRECT LINKS 🏏")
    print("========================================\n")

    for match in unique_matches:
        title = match['title']
        match_id = match['id']
        
        api_headers = {
            "device-id": DEVICE_ID,
            "authorization": token,
            "platformid": "5",
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": "okhttp/4.9.3"
        }
        payload = {
            "ChannelOrVODId": str(match_id),
            "IsChannel": "1",
            "UserId": str(user_id),
            "MobileNo": f"T{PHONE_NUMBER}",
            "Version": "v2",
            "Language": "en",
            "Platform": "android",
            "appVersion": "6.4.76"
        }

        try:
            res = session.post(api_url, headers=api_headers, data=payload)
            if res.status_code == 200:
                enc_data = res.json()
                if "iv" in enc_data and "encryptedJson" in enc_data:
                    iv = bytes.fromhex(enc_data["iv"])
                    ciphertext = bytes.fromhex(enc_data["encryptedJson"])
                    
                    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
                    decrypted = cipher.decrypt(ciphertext)
                    text = unpad(decrypted, AES.block_size).decode('utf-8')
                    
                    stream_json = json.loads(text)
                    video_info = stream_json.get("Video", {})
                    stream_url = video_info.get("ContentStreamAdaptive")
                    logo_url = video_info.get("VideoImagePathLarge") or video_info.get("NewChannelThumbnailPath") or ""
                    
                    if stream_url and "promo" not in stream_url.lower() and "promos" not in stream_url.lower():
                        print(f"✅ {title}")
                        print(f"🔗 {stream_url}\n")
                        m3u_lines.append(f'#EXTINF:-1 tvg-logo="{logo_url}" group-title="Tapmad Live Sports", {title}')
                        m3u_lines.append(stream_url)
                        clipboard_data.append(f"{title} : {stream_url}")
                        count += 1
        except Exception:
            pass

    with open(M3U_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_lines))
    print(f"✅ Updated playlist with {count} live matches.")

    if os.path.exists(REPO_DIR):
        print("\n📤 Pushing to GitHub...")
        os.system(f"cp {M3U_FILE} {REPO_DIR}/tapmad_live.m3u")
        subprocess.run(["git", "add", "tapmad_live.m3u"], cwd=REPO_DIR)
        subprocess.run(["git", "commit", "-m", "Auto-update"], cwd=REPO_DIR, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "pull", "origin", "main", "--rebase", "--autostash"], cwd=REPO_DIR, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push", "origin", "main"], cwd=REPO_DIR, stderr=subprocess.DEVNULL)
        print("✅ GitHub updated!")
    else:
        print(f"\n⚠️ GitHub folder not found at {REPO_DIR}. Skipping push.")

    if clipboard_data:
        clipboard_text = "\n".join(clipboard_data)
        os.system(f'echo "{clipboard_text}" | termux-clipboard-set')
        print("\n========================================")
        print(f"📋 {count} MATCHES COPIED TO CLIPBOARD!")
        print("========================================")
    else:
        print("\n❌ No live streams found right now (or token expired).")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        do_login()
    else:
        do_scrape()

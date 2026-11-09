import sys
import os
import json
import re
import subprocess
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# --- LOAD SECRETS FROM .env FILE ---
# This reads the .env file if it exists (on your phone).
# If it doesn't exist, it uses the defaults (which is what GitHub Actions will see).
def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value.strip('"').strip("'")

load_env()

PHONE_NUMBER = os.environ.get("TAPMAD_PHONE", "01690053223")
PIN = os.environ.get("TAPMAD_PIN", "3223")
DEVICE_ID = "__1ea14efeb3f34338a42a044d960c6351" 
AES_KEY = b"4nH4LlNWMpVYMP3FNwSsUa030ldjDqUy"

AUTH_FILE = os.path.expanduser("~/tapmad_auth.json")
M3U_FILE = os.path.expanduser("~/tapmad_live.m3u")
REPO_DIR = os.path.expanduser("~/tapmad-auto-sports")

def do_login():
    print("🔐 Logging in...")
    login_url = "https://backend-app.tapmad.com/api/SignInFreeMobileOperatorTokenByPin"
    headers = {"device-id": DEVICE_ID, "content-type": "application/x-www-form-urlencoded", "user-agent": "okhttp/4.9.3"}
    try:
        res = requests.post(login_url, headers=headers, data={"MobileNo": PHONE_NUMBER, "UserPin": PIN})
        data = res.json()
        token = data["User"]["jwtToken"]
        user_id = data["User"]["UserId"]
        with open(AUTH_FILE, "w") as f:
            json.dump({"token": token, "user_id": user_id}, f)
        print("✅ Login successful!")
    except KeyError:
        print("❌ Login failed:", data.get("Response", {}).get("message"))
        sys.exit(1)

def find_matches(data):
    matches = []
    if isinstance(data, dict):
        if 'ContentVideoName' in data and 'ContentEntityId' in data:
            matches.append({'title': data['ContentVideoName'], 'id': data['ContentEntityId']})
        for key in data: matches.extend(find_matches(data[key]))
    elif isinstance(data, list):
        for item in data: matches.extend(find_matches(item))
    return matches

def do_scrape():
    if not os.path.exists(AUTH_FILE):
        print("❌ No token found. Run 'token' first.")
        return
    with open(AUTH_FILE, "r") as f:
        auth = json.load(f)
        token = auth["token"]
        user_id = auth["user_id"]

    print("Fetching live matches...")
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
        print(f"❌ Failed to fetch: {e}")
        return

    api_url = "https://backend-app.tapmad.com/api/getStreamEncrypt"
    m3u_lines = ["#EXTM3U"]
    clipboard_data = []
    count = 0

    print("\n🏏 LIVE MATCHES 🏏\n")
    for match in unique_matches:
        match_id = match['id']
        api_headers = {"device-id": DEVICE_ID, "authorization": token, "platformid": "5", "content-type": "application/x-www-form-urlencoded", "user-agent": "okhttp/4.9.3"}
        payload = {"ChannelOrVODId": str(match_id), "IsChannel": "1", "UserId": str(user_id), "MobileNo": f"T{PHONE_NUMBER}", "Version": "v2", "Language": "en", "Platform": "android", "appVersion": "6.4.76"}

        try:
            res = session.post(api_url, headers=api_headers, data=payload)
            if res.status_code == 200:
                enc_data = res.json()
                if "iv" in enc_data and "encryptedJson" in enc_data:
                    iv = bytes.fromhex(enc_data["iv"])
                    ciphertext = bytes.fromhex(enc_data["encryptedJson"])
                    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
                    text = unpad(cipher.decrypt(ciphertext), AES.block_size).decode('utf-8')
                    stream_json = json.loads(text)
                    video_info = stream_json.get("Video", {})
                    stream_url = video_info.get("ContentStreamAdaptive")
                    logo_url = video_info.get("VideoImagePathLarge") or ""
                    
                    if stream_url and "promo" not in stream_url.lower():
                        m3u_lines.append(f'#EXTINF:-1 tvg-logo="{logo_url}" group-title="Tapmad Live", {title}')
                        m3u_lines.append(stream_url)
                        clipboard_data.append(f"{title} : {stream_url}")
                        count += 1
                        print(f"✅ {title}")
        except Exception: pass

    with open(M3U_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_lines))
    print(f"\n✅ Saved {count} matches.")

    if os.path.exists(REPO_DIR):
        os.system(f"cp {M3U_FILE} {REPO_DIR}/tapmad_live.m3u")
        subprocess.run(["git", "add", "tapmad_live.m3u", ".gitignore"], cwd=REPO_DIR)
        subprocess.run(["git", "commit", "-m", "Update"], cwd=REPO_DIR, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "pull", "origin", "main", "--rebase", "--autostash"], cwd=REPO_DIR, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push", "origin", "main"], cwd=REPO_DIR, stderr=subprocess.DEVNULL)
        print("✅ GitHub updated!")

    if clipboard_data:
        os.system(f'echo "{"\n".join(clipboard_data)}" | termux-clipboard-set')
        print(f"📋 {count} links copied to clipboard!")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "login": do_login()
    else: do_scrape()

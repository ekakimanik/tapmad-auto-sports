import requests
import json
import re
import os
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

PHONE_NUMBER = os.environ.get("TAPMAD_PHONE", "01690053223")
PIN = os.environ.get("TAPMAD_PIN", "3223")
DEVICE_ID = "__1ea14efeb3f34338a42a044d960c6351" 
AES_KEY = b"4nH4LlNWMpVYMP3FNwSsUa030ldjDqUy"

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

def main():
    session = requests.Session()
    
    print("1. Logging in via Android App API...")
    login_url = "https://backend-app.tapmad.com/api/SignInFreeMobileOperatorTokenByPin"
    login_headers = {
        "device-id": DEVICE_ID,
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": "okhttp/4.9.3"
    }
    
    login_res = session.post(login_url, headers=login_headers, data={"MobileNo": PHONE_NUMBER, "UserPin": PIN})
    login_data = login_res.json()
    
    try:
        token = login_data["User"]["jwtToken"]
        user_id = login_data["User"]["UserId"]
        print(f"✅ Logged in! (User ID: {user_id})")
    except KeyError:
        print("❌ Login failed. Tapmad is rate-limiting GitHub's IP.")
        with open("tapmad_live.m3u", "w") as f:
            f.write("#EXTM3U\n")
        return

    print("2. Fetching live matches...")
    # ADDED HEADERS: Making GitHub look like a real browser fetching the JSON
    web_headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "accept": "application/json",
        "referer": "https://www.tapmad.com/",
        "x-nextjs-data": "1"
    }
    
    home_res = session.get("https://www.tapmad.com/", headers=web_headers)
    build_id_match = re.search(r'"buildId":"([^"]+)"', home_res.text)
    
    if not build_id_match:
        print("❌ Could not find Build ID. Website might be blocking GitHub.")
        return
        
    build_id = build_id_match.group(1)
    
    sports_url = f"https://www.tapmad.com/_next/data/{build_id}/sports.json"
    sports_res = session.get(sports_url, headers=web_headers)
    
    try:
        sports_data = sports_res.json()
        all_matches = find_matches(sports_data)
        unique_matches = {v['id']: v for v in all_matches}.values()
        print(f"✅ Found {len(unique_matches)} matches.")
    except Exception as e:
        print(f"❌ Failed to parse JSON from Tapmad. Response might be blocked.")
        print(f"Status Code: {sports_res.status_code}")
        print(f"Response snippet: {sports_res.text[:200]}")
        with open("tapmad_live.m3u", "w") as f:
            f.write("#EXTM3U\n")
        return

    print("3. Decrypting live streams...")
    api_url = "https://backend-app.tapmad.com/api/getStreamEncrypt"
    m3u_lines = ["#EXTM3U"]
    count = 0

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
                    stream_url = stream_json.get("Video", {}).get("ContentStreamAdaptive")
                    
                    if stream_url and "promo" not in stream_url.lower() and "promos" not in stream_url.lower():
                        m3u_lines.append(f'#EXTINF:-1 group-title="Tapmad Live Sports", {title}')
                        m3u_lines.append(stream_url)
                        count += 1
                        print(f"✅ {title}")
        except Exception:
            pass

    with open("tapmad_live.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_lines))
    print(f"\n🎉 SUCCESS! Saved {count} live streams.")

if __name__ == "__main__":
    main()

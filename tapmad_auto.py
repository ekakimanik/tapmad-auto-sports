import requests
import json
import re
import os
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

JWT_TOKEN = os.environ.get("TAPMAD_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjpbeyJVc2VyVXNlcm5hbWUiOiJUMDE2OTAwNTMyMjMiLCJVc2VyQ291bnRyeUNvZGUiOiJQSyIsInRpbWVzdGFtcCI6MTc5NDE0MTQ5MSwiSWQiOiJjZWVhYTk1Yy02YTFhLTQ2MzAtYmQxOS0zNDNjZjEyYzhkMjYifV0sImlhdCI6MTc5NDE0MTQ5MX0.90CjRT7WKgVNgjcSoEK3ZAaAQ2PhYPiUSjI1RNtCcIM")
USER_ID = "65994726"
PHONE_NUMBER = "01690053223"
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
    token = JWT_TOKEN

    print("1. Fetching live matches...")
    web_headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    home_res = session.get("https://www.tapmad.com/", headers=web_headers)
    build_id = re.search(r'"buildId":"([^"]+)"', home_res.text).group(1)
    
    sports_url = f"https://www.tapmad.com/_next/data/{build_id}/sports.json"
    sports_data = session.get(sports_url, headers=web_headers).json()
    
    all_matches = find_matches(sports_data)
    unique_matches = {v['id']: v for v in all_matches}.values()
    print(f"✅ Found {len(unique_matches)} matches.")

    print("2. Decrypting live streams...")
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
            "UserId": str(USER_ID),
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
                    
                    if stream_url:
                        m3u_lines.append(f'#EXTINF:-1 group-title="Tapmad Live Sports", {title}')
                        m3u_lines.append(stream_url)
                        count += 1
                        print(f"✅ {title}")
        except Exception:
            pass

    if count > 0:
        with open("tapmad_live.m3u", "w", encoding="utf-8") as f:
            f.write("\n".join(m3u_lines))
        print(f"\n🎉 SUCCESS! Saved {count} live streams to tapmad_live.m3u")
    else:
        print("\n❌ No live streams found.")

if __name__ == "__main__":
    main()

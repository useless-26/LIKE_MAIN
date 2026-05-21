from flask import Flask, request, jsonify
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import binascii
import aiohttp
import requests
import json
import like_pb2
import like_count_pb2
import uid_generator_pb2
from google.protobuf.message import DecodeError
import base64
import threading
import time
import random
import os

app = Flask(__name__)

# ============ CONFIG ============
AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV = b'6oyZDr22E3ychjM%'

# Key Types
KEY_CONFIG = {
    "bijayfree": {"likes": 50, "type": "free"},
    "bijaypaid": {"likes": 200, "type": "paid"}
}

# File for storing accounts
ACCOUNTS_FILE = "accounts.json"

# Token management
tokens_cache = {"tokens": [], "last_update": 0}
TOKEN_UPDATE_INTERVAL = 8 * 3600  # 8 hours

# ============ ACCOUNTS MANAGEMENT ============
def load_accounts():
    """Load accounts from accounts.json file"""
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                accounts = json.load(f)
                print(f"📁 Loaded {len(accounts)} accounts from {ACCOUNTS_FILE}")
                return accounts
        else:
            # Create default accounts file
            default_accounts = [
                {"uid": "4549583213", "password": "239830A37F8E4D0534015BC31112858C8797BDE789D08DED501693045F3AB5A4"},
                {"uid": "4679147687", "password": "D30D23EAAC715B10702A53097FC48C97746224A264309A19BE0D404F2E479A35"},
                {"uid": "4523769756", "password": "D5CE7BA2281CFA08C9D0ADFCFB1D05B18C60919E1AA98A61A0EFD3C50747DEEC"}
            ]
            save_accounts(default_accounts)
            return default_accounts
    except Exception as e:
        print(f"Error loading accounts: {e}")
        return []

def save_accounts(accounts):
    """Save accounts to accounts.json file"""
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        print(f"💾 Saved {len(accounts)} accounts to {ACCOUNTS_FILE}")
        return True
    except Exception as e:
        print(f"Error saving accounts: {e}")
        return False

def add_account(uid, password):
    """Add a single account to accounts.json"""
    accounts = load_accounts()
    
    # Check if account already exists
    for acc in accounts:
        if acc['uid'] == uid:
            return False, "Account already exists"
    
    accounts.append({"uid": uid, "password": password})
    save_accounts(accounts)
    return True, "Account added successfully"

def remove_account(uid):
    """Remove account from accounts.json"""
    accounts = load_accounts()
    new_accounts = [acc for acc in accounts if acc['uid'] != uid]
    
    if len(new_accounts) == len(accounts):
        return False, "Account not found"
    
    save_accounts(new_accounts)
    return True, "Account removed successfully"

def get_all_accounts():
    """Get all accounts"""
    return load_accounts()

# ============ TOKEN MANAGEMENT ============
def generate_jwt_from_guest(uid, password):
    """Generate JWT token from guest account"""
    try:
        url = f"http://87.232.72.68:3005/token?uid={uid}&password={password}&key=dgop"
        response = requests.get(url, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            if 'token' in data:
                return {
                    "success": True,
                    "token": data['token'],
                    "region": data.get('region', 'IND'),
                    "nickname": data.get('nickname', 'Unknown')
                }
        return {"success": False}
    except Exception as e:
        print(f"Token gen error: {e}")
        return {"success": False}

def refresh_tokens():
    """Refresh all tokens from accounts.json"""
    global tokens_cache
    print("🔄 Refreshing JWT tokens...")
    
    accounts = load_accounts()
    if not accounts:
        print("⚠️ No accounts found in accounts.json")
        return []
    
    new_tokens = []
    for account in accounts:
        result = generate_jwt_from_guest(account['uid'], account['password'])
        if result.get('success'):
            new_tokens.append({
                "token": result['token'],
                "region": result['region'],
                "nickname": result['nickname'],
                "uid": account['uid']
            })
            print(f"✅ Token generated for {account['uid']}")
        else:
            print(f"❌ Failed for {account['uid']}")
    
    tokens_cache = {
        "tokens": new_tokens,
        "last_update": time.time()
    }
    print(f"📊 Total working tokens: {len(new_tokens)}/{len(accounts)}")
    return new_tokens

def get_tokens():
    """Get tokens, refresh if needed"""
    global tokens_cache
    if not tokens_cache['tokens'] or (time.time() - tokens_cache['last_update']) > TOKEN_UPDATE_INTERVAL:
        refresh_tokens()
    
    if not tokens_cache['tokens']:
        refresh_tokens()
    
    return tokens_cache['tokens']

def load_tokens():
    """Load tokens from cache"""
    tokens = get_tokens()
    if tokens:
        return tokens
    return None

# ============ ENCRYPTION & PROTOBUF ============
def encrypt_message(plaintext):
    try:
        cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
        padded_message = pad(plaintext, AES.block_size)
        encrypted_message = cipher.encrypt(padded_message)
        return binascii.hexlify(encrypted_message).decode('utf-8')
    except Exception as e:
        app.logger.error(f"Error encrypting message: {e}")
        return None

def create_protobuf_message(user_id, region):
    try:
        message = like_pb2.like()
        message.uid = int(user_id)
        message.region = region
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating protobuf message: {e}")
        return None

def create_protobuf(uid):
    try:
        message = uid_generator_pb2.uid_generator()
        message.saturn_ = int(uid)
        message.garena = 1
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating uid protobuf: {e}")
        return None

def enc(uid):
    protobuf_data = create_protobuf(uid)
    if protobuf_data is None:
        return None
    encrypted_uid = encrypt_message(protobuf_data)
    return encrypted_uid

def decode_protobuf(binary):
    try:
        items = like_count_pb2.Info()
        items.ParseFromString(binary)
        return items
    except DecodeError as e:
        app.logger.error(f"Error decoding Protobuf data: {e}")
        return None
    except Exception as e:
        app.logger.error(f"Unexpected error during protobuf decoding: {e}")
        return None

def make_request(encrypt, server_name, token):
    try:
        if server_name == "IND":
            url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
        else:
            url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"
        edata = bytes.fromhex(encrypt)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'Expect': "100-continue",
            'X-Unity-Version': "2018.4.11f1",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB53"
        }
        response = requests.post(url, data=edata, headers=headers, verify=False)
        hex_data = response.content.hex()
        binary = bytes.fromhex(hex_data)
        decode = decode_protobuf(binary)
        return decode
    except Exception as e:
        app.logger.error(f"Error in make_request: {e}")
        return None

async def send_request(encrypted_uid, token, url):
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'Expect': "100-continue",
            'X-Unity-Version': "2018.4.11f1",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB53"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=edata, headers=headers) as response:
                if response.status != 200:
                    return response.status
                return await response.text()
    except Exception as e:
        app.logger.error(f"Exception in send_request: {e}")
        return None

async def send_multiple_requests(uid, server_name, url, max_likes):
    """Send like requests based on max_likes (50 or 200)"""
    try:
        region = server_name
        protobuf_message = create_protobuf_message(uid, region)
        if protobuf_message is None:
            return None
        encrypted_uid = encrypt_message(protobuf_message)
        if encrypted_uid is None:
            return None
        
        tasks = []
        tokens = load_tokens()
        if tokens is None:
            return None
        
        # Send exactly max_likes number of requests
        for i in range(max_likes):
            token = tokens[i % len(tokens)]["token"]
            tasks.append(send_request(encrypted_uid, token, url))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    except Exception as e:
        app.logger.error(f"Exception in send_multiple_requests: {e}")
        return None

# ============ AUTO ACCOUNT GENERATOR ============
def generate_guest_accounts(count=3):
    """Generate new guest accounts from API"""
    new_accounts = []
    for i in range(count):
        try:
            url = f"https://gen-by-black-api.vercel.app/generate?name=Guest&password_prefix=FF"
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    new_accounts.append({
                        "uid": data['uid'],
                        "password": data['password']
                    })
                    print(f"✅ Generated account: {data['uid']}")
        except Exception as e:
            print(f"Account generation error: {e}")
        time.sleep(1)
    
    return new_accounts

def auto_add_generated_accounts(count=3):
    """Generate and add accounts to accounts.json"""
    new_accounts = generate_guest_accounts(count)
    added = 0
    for acc in new_accounts:
        success, _ = add_account(acc['uid'], acc['password'])
        if success:
            added += 1
    return added, new_accounts

# Background thread for auto token refresh
def token_refresh_daemon():
    while True:
        time.sleep(TOKEN_UPDATE_INTERVAL)
        print("🔄 Auto-refreshing tokens...")
        refresh_tokens()

# ============ FLASK ROUTES ============

@app.route('/', methods=['GET'])
def index():
    accounts = load_accounts()
    tokens = get_tokens()
    return jsonify({
        "credit": "BO HAKER",
        "message": "Welcome to the Free Fire Like API",
        "status": "API is running",
        "keys": {
            "free_key": "bijayfree (50 likes)",
            "paid_key": "bijaypaid (200 likes)"
        },
        "endpoints": "/like?uid=<uid>&server_name=<region>&key=<your_key>",
        "example": "/like?uid=123456789&server_name=bd&key=bijayfree",
        "stats": {
            "total_accounts": len(accounts),
            "active_tokens": len(tokens),
            "next_refresh": "8 hours"
        }
    })

@app.route('/like', methods=['GET'])
def handle_requests():
    uid = request.args.get("uid")
    key = request.args.get("key")
    server_name = request.args.get("server_name", "").upper()
    
    # Validate required parameters
    if not uid:
        return jsonify({"error": "UID is required"}), 400
    
    if not key:
        return jsonify({"error": "Key is required. Use key=bijayfree or key=bijaypaid"}), 400
    
    # Validate key
    if key not in KEY_CONFIG:
        return jsonify({
            "error": "Invalid key",
            "available_keys": {
                "bijayfree": "50 likes (Free user)",
                "bijaypaid": "200 likes (Paid user)"
            }
        }), 400
    
    # Get max likes based on key
    max_likes = KEY_CONFIG[key]["likes"]
    user_type = KEY_CONFIG[key]["type"]
    
    try:
        tokens = load_tokens()
        if tokens is None or not tokens:
            return jsonify({"error": "No valid tokens available. Please try again later."}), 500
        
        token = tokens[0]['token']
        
        # Get server_name from token if not provided
        if not server_name:
            try:
                payload = token.split('.')[1]
                payload += '=' * (-len(payload) % 4)
                decoded_payload = base64.urlsafe_b64decode(payload).decode('utf-8')
                parsed_payload = json.loads(decoded_payload)
                server_name = parsed_payload.get('lock_region', '').upper()
            except Exception as e:
                app.logger.error(f"Error decoding token payload: {e}")
        
        if not server_name:
            server_name = "BD"  # Default region
        
        encrypted_uid = enc(uid)
        if encrypted_uid is None:
            return jsonify({"error": "Encryption of UID failed."}), 500

        # Get before likes count
        before = make_request(encrypted_uid, server_name, token)
        if before is None:
            return jsonify({"error": "Failed to retrieve player info. No valid tokens found!"}), 500
        
        data_before = json.loads(MessageToJson(before))
        before_like = int(data_before.get('AccountInfo', {}).get('Likes', 0) or 0)
        app.logger.info(f"Likes before: {before_like}")

        # Determine URL based on server
        if server_name == "IND":
            url = "https://client.ind.freefiremobile.com/LikeProfile"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            url = "https://client.us.freefiremobile.com/LikeProfile"
        else:
            url = "https://clientbp.ggpolarbear.com/LikeProfile"

        # Send like requests (based on key type)
        requests_sent = asyncio.run(send_multiple_requests(uid, server_name, url, max_likes))
        
        # Count successful requests
        success_count = 0
        if requests_sent:
            for result in requests_sent:
                if result and result == 200:
                    success_count += 1
        
        app.logger.info(f"Successful likes: {success_count}/{max_likes}")

        # Get after likes count
        after = make_request(encrypted_uid, server_name, token)
        if after is None:
            return jsonify({"error": "Failed to retrieve player info after likes."}), 500
        
        data_after = json.loads(MessageToJson(after))
        account_info = data_after.get('AccountInfo', {})
        after_like = int(account_info.get('Likes', 0) or 0)
        player_uid = int(account_info.get('UID', 0) or 0)
        player_name = str(account_info.get('PlayerNickname', ''))
        
        like_given = after_like - before_like
        
        return jsonify({
            "credit": "BP HAKER",
            "key_used": key,
            "user_type": user_type,
            "max_likes": max_likes,
            "successful_requests": success_count,
            "LikesGivenByAPI": like_given,
            "LikesafterCommand": after_like,
            "LikesbeforeCommand": before_like,
            "PlayerNickname": player_name,
            "Region": server_name,
            "UID": player_uid,
            "status": 1 if like_given > 0 else 2
        })
    except Exception as e:
        app.logger.error(f"Error processing request: {e}")
        return jsonify({"error": str(e)}), 500

# ============ ACCOUNT MANAGEMENT ENDPOINTS ============

@app.route('/accounts', methods=['GET'])
def list_accounts():
    """List all accounts (without passwords)"""
    accounts = load_accounts()
    safe_accounts = []
    for acc in accounts:
        safe_accounts.append({
            "uid": acc['uid'],
            "password_preview": acc['password'][:20] + "..."
        })
    
    return jsonify({
        "total": len(accounts),
        "accounts": safe_accounts
    })

@app.route('/add-account', methods=['GET', 'POST'])
def add_account_endpoint():
    """Add a new account"""
    if request.method == 'GET':
        uid = request.args.get('uid')
        password = request.args.get('password')
    else:
        data = request.get_json()
        uid = data.get('uid')
        password = data.get('password')
    
    if not uid or not password:
        return jsonify({"error": "uid and password required"}), 400
    
    success, message = add_account(uid, password)
    
    if success:
        # Refresh tokens to include new account
        refresh_tokens()
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"error": message}), 400

@app.route('/remove-account', methods=['GET'])
def remove_account_endpoint():
    """Remove an account"""
    uid = request.args.get('uid')
    
    if not uid:
        return jsonify({"error": "uid required"}), 400
    
    success, message = remove_account(uid)
    
    if success:
        refresh_tokens()
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"error": message}), 404

@app.route('/generate-accounts', methods=['GET'])
def generate_accounts_endpoint():
    """Generate and auto-add new guest accounts"""
    count = int(request.args.get('count', 3))
    
    if count > 10:
        return jsonify({"error": "Max 10 accounts at a time"}), 400
    
    added, new_accounts = auto_add_generated_accounts(count)
    
    return jsonify({
        "success": True,
        "requested": count,
        "added": added,
        "accounts": new_accounts
    })

@app.route('/refresh-accounts', methods=['GET'])
def refresh_accounts():
    """Refresh tokens from all accounts"""
    refresh_tokens()
    accounts = load_accounts()
    tokens = get_tokens()
    
    return jsonify({
        "success": True,
        "total_accounts": len(accounts),
        "working_tokens": len(tokens),
        "message": f"{len(tokens)}/{len(accounts)} accounts working"
    })

@app.route('/tokens-status', methods=['GET'])
def tokens_status():
    """Check token status"""
    tokens = get_tokens()
    accounts = load_accounts()
    time_since_refresh = time.time() - tokens_cache['last_update']
    hours_until_refresh = max(0, (TOKEN_UPDATE_INTERVAL - time_since_refresh) / 3600)
    
    return jsonify({
        "total_accounts": len(accounts),
        "working_tokens": len(tokens),
        "last_refresh": time.ctime(tokens_cache['last_update']),
        "next_refresh_in": f"{hours_until_refresh:.1f} hours",
        "refresh_interval": "8 hours"
    })

@app.route('/refresh-tokens', methods=['GET'])
def force_refresh():
    """Force refresh tokens"""
    refresh_tokens()
    return jsonify({
        "success": True,
        "message": "Tokens refreshed",
        "total_tokens": len(tokens_cache['tokens'])
    })

if __name__ == '__main__':
    # Create accounts.json if not exists
    if not os.path.exists(ACCOUNTS_FILE):
        default_accounts = [
            {"uid": "4549583213", "password": "239830A37F8E4D0534015BC31112858C8797BDE789D08DED501693045F3AB5A4"},
            {"uid": "4679147687", "password": "D30D23EAAC715B10702A53097FC48C97746224A264309A19BE0D404F2E479A35"},
            {"uid": "4523769756", "password": "D5CE7BA2281CFA08C9D0ADFCFB1D05B18C60919E1AA98A61A0EFD3C50747DEEC"}
        ]
        save_accounts(default_accounts)
    
    # Initial token refresh
    print("🚀 Starting FreeFire Like API...")
    print("📁 Account file: accounts.json")
    print("🔑 Key System:")
    print("   - bijayfree: 50 likes (Free user)")
    print("   - bijaypaid: 200 likes (Paid user)")
    print("🔄 Refreshing JWT tokens...")
    refresh_tokens()
    
    # Start background token refresh daemon
    refresh_thread = threading.Thread(target=token_refresh_daemon, daemon=True)
    refresh_thread.start()
    
    accounts = load_accounts()
    print(f"✅ Loaded {len(accounts)} accounts from accounts.json")
    print(f"✅ Working tokens: {len(tokens_cache['tokens'])}")
    print("✅ API Ready!")
    print("📝 Usage: /like?uid=123456789&server_name=bd&key=bijayfree")
    
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=8080)
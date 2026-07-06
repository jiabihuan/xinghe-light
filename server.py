import os
import json
import hashlib
import hmac
import secrets
import random
import string
import time
import uuid
import mimetypes
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
import re

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
APK_DIR = UPLOAD_DIR / "apks"
TEMPLATE_DIR = BASE_DIR / "server" / "templates"
STATIC_DIR = BASE_DIR / "server" / "static"

for d in [DATA_DIR, UPLOAD_DIR, APK_DIR]:
    d.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = DATA_DIR / "config.json"
USERS_FILE = DATA_DIR / "users.json"
APPS_FILE = DATA_DIR / "apps.json"
CODES_FILE = DATA_DIR / "codes.json"
INVITES_FILE = DATA_DIR / "invites.json"

SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
SUPER_ADMIN_USERNAME = os.getenv("SUPER_ADMIN_USERNAME", "admin")
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "admin123456")
MAX_APPS_PER_USER = 100
CODE_LENGTH = 4
CODE_CHARS = "0123456789ABCDEF"


def load_json(filepath, default):
    if not filepath.exists():
        return default
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default


def save_json(filepath, data):
    tmp = filepath.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(filepath)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}${hash_obj}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        salt, hash_val = hashed.split('$', 1)
        test_hash = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
        return hmac.compare_digest(test_hash, hash_val)
    except:
        return False


def create_token(user_id: int) -> str:
    payload = f"{user_id}:{int(time.time()) + 86400}"
    signature = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_token(token: str) -> int:
    try:
        payload, signature = token.rsplit('.', 1)
        expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        user_id_str, exp_str = payload.split(':', 1)
        if int(time.time()) > int(exp_str):
            return None
        return int(user_id_str)
    except:
        return None


def generate_code(length=CODE_LENGTH):
    return ''.join(random.choices(CODE_CHARS, k=length))


def generate_invite_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def get_users():
    return load_json(USERS_FILE, [])


def save_users(users):
    save_json(USERS_FILE, users)


def get_apps():
    return load_json(APPS_FILE, [])


def save_apps(apps):
    save_json(APPS_FILE, apps)


def get_codes():
    return load_json(CODES_FILE, [])


def save_codes(codes):
    save_json(CODES_FILE, codes)


def get_invites():
    return load_json(INVITES_FILE, [])


def save_invites(invites):
    save_json(INVITES_FILE, invites)


def parse_multipart(content_type, body):
    result = {}
    match = re.search(r'boundary=([^;]+)', content_type)
    if not match:
        return result
    boundary = match.group(1).strip().strip('"')
    if boundary.startswith('--'):
        boundary = boundary[2:]

    parts = body.split(b'--' + boundary.encode())
    for part in parts:
        part = part.strip()
        if not part or part == b'--':
            continue

        header_end = part.find(b'\r\n\r\n')
        if header_end == -1:
            continue

        headers_text = part[:header_end].decode('utf-8', errors='ignore')
        content = part[header_end + 4:]

        if content.endswith(b'\r\n'):
            content = content[:-2]

        name_match = re.search(r'name="([^"]+)"', headers_text)
        if not name_match:
            continue
        name = name_match.group(1)

        filename_match = re.search(r'filename="([^"]*)"', headers_text)
        if filename_match:
            filename = filename_match.group(1)
            result[name] = {
                'filename': filename,
                'content': content,
                'is_file': True
            }
        else:
            try:
                result[name] = content.decode('utf-8')
            except:
                result[name] = content

    return result


def init_data():
    users = get_users()
    if not any(u.get('is_super_admin') for u in users):
        admin = {
            'id': 1,
            'username': SUPER_ADMIN_USERNAME,
            'password_hash': hash_password(SUPER_ADMIN_PASSWORD),
            'is_admin': True,
            'is_super_admin': True,
            'is_active': True,
            'invite_code_id': None,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        users.append(admin)
        save_users(users)


def next_id(items):
    if not items:
        return 1
    return max(item['id'] for item in items) + 1


def get_user_by_id(user_id):
    for u in get_users():
        if u['id'] == user_id:
            return u
    return None


def get_user_by_username(username):
    for u in get_users():
        if u['username'] == username:
            return u
    return None


def get_app_by_id(app_id):
    for a in get_apps():
        if a['id'] == app_id:
            return a
    return None


def get_code_by_code(code_str):
    for c in get_codes():
        if c['code'] == code_str and c['is_active']:
            return c
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', '*')
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, detail, status=400):
        self.send_json({'detail': detail}, status)

    def send_file(self, filepath, content_type=None):
        if not filepath.exists() or not filepath.is_file():
            self.send_error_json('文件不存在', 404)
            return
        if content_type is None:
            content_type = mimetypes.guess_type(str(filepath))[0] or 'application/octet-stream'
        size = filepath.stat().st_size
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(size))
        self.end_headers()
        with open(filepath, 'rb') as f:
            self.wfile.write(f.read())

    def get_current_user(self):
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth[7:]
            user_id = verify_token(token)
            if user_id:
                return get_user_by_id(user_id)
        return None

    def parse_json_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        body = self.rfile.read(length).decode('utf-8')
        try:
            return json.loads(body)
        except:
            return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', '*')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/' or path == '/index.html':
            self.send_file(TEMPLATE_DIR / 'index.html', 'text/html; charset=utf-8')
            return

        if path.startswith('/static/'):
            rel = path[len('/static/'):]
            filepath = STATIC_DIR / rel
            if filepath.exists() and filepath.is_file():
                self.send_file(filepath)
            else:
                self.send_error_json('Not Found', 404)
            return

        if path.startswith('/api/'):
            self.handle_api_get(path, parsed)
            return

        if path.startswith('/api/download/'):
            code_str = path[len('/api/download/'):]
            self.handle_download(code_str)
            return

        self.send_error_json('Not Found', 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/'):
            self.handle_api_post(path, parsed)
            return

        self.send_error_json('Not Found', 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/'):
            self.handle_api_delete(path, parsed)
            return

        self.send_error_json('Not Found', 404)

    def handle_api_get(self, path, parsed):
        params = parse_qs(parsed.query)

        if path == '/api/health':
            self.send_json({'status': 'ok', 'version': '2.0.0'})
            return

        if path == '/api/auth/me':
            user = self.get_current_user()
            if not user:
                self.send_error_json('未授权', 401)
                return
            self.send_json({
                'id': user['id'],
                'username': user['username'],
                'is_admin': user['is_admin'],
                'is_super_admin': user['is_super_admin']
            })
            return

        if path == '/api/apps':
            user = self.get_current_user()
            if not user:
                self.send_error_json('未授权', 401)
                return
            apps = get_apps()
            user_apps = [a for a in apps if a['owner_id'] == user['id']]
            user_apps.sort(key=lambda x: x['id'], reverse=True)
            codes = get_codes()
            result = []
            for app in user_apps:
                app_codes = [c['code'] for c in codes if c['app_id'] == app['id'] and c['is_active']]
                result.append({
                    'id': app['id'],
                    'name': app['name'],
                    'package_name': app['package_name'],
                    'version_name': app['version_name'],
                    'apk_size': app['apk_size'],
                    'apk_size_str': format_size(app['apk_size']),
                    'download_count': app['download_count'],
                    'is_duplicate': app['is_duplicate'],
                    'created_at': app['created_at'],
                    'codes': app_codes
                })
            self.send_json(result)
            return

        if path == '/api/apps/count':
            user = self.get_current_user()
            if not user:
                self.send_error_json('未授权', 401)
                return
            apps = get_apps()
            count = sum(1 for a in apps if a['owner_id'] == user['id'])
            self.send_json({
                'count': count,
                'max': MAX_APPS_PER_USER,
                'remaining': MAX_APPS_PER_USER - count
            })
            return

        if path == '/api/download/info/':
            code_str = path.rsplit('/', 1)[-1] if '/' in path else ''
            self.handle_download_info(code_str)
            return

        if path.startswith('/api/download/info/'):
            code_str = path[len('/api/download/info/'):]
            self.handle_download_info(code_str)
            return

        if path == '/api/admin/users':
            user = self.get_current_user()
            if not user or not user['is_super_admin']:
                self.send_error_json('需要超级管理员权限', 403)
                return
            users = get_users()
            apps = get_apps()
            result = []
            for u in sorted(users, key=lambda x: x['id'], reverse=True):
                app_count = sum(1 for a in apps if a['owner_id'] == u['id'])
                result.append({
                    'id': u['id'],
                    'username': u['username'],
                    'is_admin': u['is_admin'],
                    'is_super_admin': u['is_super_admin'],
                    'is_active': u['is_active'],
                    'app_count': app_count,
                    'created_at': u['created_at']
                })
            self.send_json(result)
            return

        if path == '/api/admin/invite-codes':
            user = self.get_current_user()
            if not user or not user['is_super_admin']:
                self.send_error_json('需要超级管理员权限', 403)
                return
            invites = get_invites()
            result = []
            for c in sorted(invites, key=lambda x: x['id'], reverse=True):
                result.append({
                    'id': c['id'],
                    'code': c['code'],
                    'used_count': c['used_count'],
                    'max_uses': c['max_uses'],
                    'is_used': c['is_used'],
                    'created_at': c['created_at']
                })
            self.send_json(result)
            return

        if path == '/api/admin/stats':
            user = self.get_current_user()
            if not user or not user['is_super_admin']:
                self.send_error_json('需要超级管理员权限', 403)
                return
            self.send_json({
                'user_count': len(get_users()),
                'app_count': len(get_apps()),
                'code_count': len(get_codes()),
                'invite_code_count': len(get_invites()),
                'unused_invite_codes': sum(1 for c in get_invites() if not c['is_used'])
            })
            return

        self.send_error_json('Not Found', 404)

    def handle_api_post(self, path, parsed):
        if path == '/api/auth/login':
            self.handle_login()
            return

        if path == '/api/auth/register':
            self.handle_register()
            return

        if path == '/api/auth/init-super-admin':
            users = get_users()
            if any(u.get('is_super_admin') for u in users):
                self.send_error_json('超级管理员已初始化')
                return
            init_data()
            self.send_json({'message': '初始化成功', 'username': SUPER_ADMIN_USERNAME})
            return

        if path == '/api/apps/upload':
            self.handle_upload()
            return

        if path.startswith('/api/apps/') and path.endswith('/generate-code'):
            app_id = int(path.split('/')[-2])
            self.handle_generate_code(app_id)
            return

        if path.startswith('/api/admin/users/') and path.endswith('/toggle-admin'):
            user_id = int(path.split('/')[-2])
            self.handle_toggle_admin(user_id)
            return

        if path.startswith('/api/admin/users/') and path.endswith('/toggle-active'):
            user_id = int(path.split('/')[-2])
            self.handle_toggle_active(user_id)
            return

        if path == '/api/admin/invite-codes':
            self.handle_create_invite()
            return

        self.send_error_json('Not Found', 404)

    def handle_api_delete(self, path, parsed):
        if path.startswith('/api/apps/') and '/codes/' in path:
            parts = path.split('/')
            app_id = int(parts[3])
            code_str = parts[5]
            self.handle_delete_code(app_id, code_str)
            return

        if path.startswith('/api/apps/'):
            try:
                app_id = int(path.rsplit('/', 1)[-1])
                self.handle_delete_app(app_id)
            except:
                self.send_error_json('Not Found', 404)
            return

        if path.startswith('/api/admin/invite-codes/'):
            try:
                code_id = int(path.rsplit('/', 1)[-1])
                self.handle_delete_invite(code_id)
            except:
                self.send_error_json('Not Found', 404)
            return

        self.send_error_json('Not Found', 404)

    def handle_login(self):
        content_type = self.headers.get('Content-Type', '')
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length > 0 else b''

        if 'multipart/form-data' in content_type:
            form = parse_multipart(content_type, body)
            username = form.get('username', '')
            password = form.get('password', '')
        else:
            try:
                data = json.loads(body.decode('utf-8')) if body else {}
            except:
                data = {}
            username = data.get('username', '')
            password = data.get('password', '')

        user = get_user_by_username(username)
        if not user or not verify_password(password, user['password_hash']):
            self.send_error_json('用户名或密码错误', 401)
            return
        if not user['is_active']:
            self.send_error_json('账号已被禁用', 403)
            return

        token = create_token(user['id'])
        self.send_json({
            'access_token': token,
            'token_type': 'bearer',
            'user': {
                'id': user['id'],
                'username': user['username'],
                'is_admin': user['is_admin'],
                'is_super_admin': user['is_super_admin']
            }
        })

    def handle_register(self):
        body = self.parse_json_body()
        username = body.get('username', '').strip()
        password = body.get('password', '')
        invite_code_str = body.get('invite_code', '').strip()

        invites = get_invites()
        invite = None
        for inv in invites:
            if inv['code'] == invite_code_str:
                invite = inv
                break

        if not invite:
            self.send_error_json('邀请码无效')
            return
        if invite['is_used']:
            self.send_error_json('邀请码已被使用')
            return
        if invite['used_count'] >= invite['max_uses']:
            self.send_error_json('邀请码使用次数已用完')
            return

        if get_user_by_username(username):
            self.send_error_json('用户名已存在')
            return

        if len(username) < 3:
            self.send_error_json('用户名至少3个字符')
            return
        if len(password) < 6:
            self.send_error_json('密码至少6个字符')
            return

        users = get_users()
        user_id = next_id(users)
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        user = {
            'id': user_id,
            'username': username,
            'password_hash': hash_password(password),
            'is_admin': False,
            'is_super_admin': False,
            'is_active': True,
            'invite_code_id': invite['id'],
            'created_at': now
        }
        users.append(user)
        save_users(users)

        invite['used_count'] += 1
        if invite['used_count'] >= invite['max_uses']:
            invite['is_used'] = True
        save_invites(invites)

        token = create_token(user_id)
        self.send_json({
            'access_token': token,
            'token_type': 'bearer',
            'user': {
                'id': user['id'],
                'username': user['username'],
                'is_admin': user['is_admin'],
                'is_super_admin': user['is_super_admin']
            }
        })

    def handle_upload(self):
        user = self.get_current_user()
        if not user:
            self.send_error_json('未授权', 401)
            return

        apps = get_apps()
        user_app_count = sum(1 for a in apps if a['owner_id'] == user['id'])
        if user_app_count >= MAX_APPS_PER_USER:
            self.send_error_json(f'每个用户最多上传{MAX_APPS_PER_USER}个应用')
            return

        content_type = self.headers.get('Content-Type', '')
        if 'multipart/form-data' not in content_type:
            self.send_error_json('请上传文件')
            return

        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length > 0 else b''
        form = parse_multipart(content_type, body)

        if 'file' not in form or not isinstance(form['file'], dict):
            self.send_error_json('请选择文件')
            return

        file_item = form['file']
        filename = file_item.get('filename', 'app.apk') or 'app.apk'
        if not filename.lower().endswith('.apk'):
            self.send_error_json('只能上传APK文件')
            return

        file_data = file_item.get('content', b'')
        if not file_data:
            self.send_error_json('文件不能为空')
            return

        apk_size = len(file_data)
        app_name = (form.get('app_name') or filename.rsplit('.', 1)[0])
        if isinstance(app_name, dict):
            app_name = filename.rsplit('.', 1)[0]
        package_name = f"com.uploaded.{secrets.token_hex(4)}"
        version_name = "1.0"

        file_id = str(uuid.uuid4())
        save_name = f"{file_id}.apk"
        save_path = APK_DIR / save_name

        with open(save_path, 'wb') as f:
            f.write(file_data)

        now = time.strftime('%Y-%m-%d %H:%M:%S')
        app_id = next_id(apps)
        app = {
            'id': app_id,
            'name': app_name,
            'package_name': package_name,
            'version_name': version_name,
            'apk_path': str(save_path),
            'apk_size': apk_size,
            'description': '',
            'owner_id': user['id'],
            'real_app_id': None,
            'is_duplicate': False,
            'download_count': 0,
            'created_at': now
        }
        apps.append(app)
        save_apps(apps)

        codes = get_codes()
        code_id = next_id(codes)
        for _ in range(100):
            code_str = generate_code()
            if not any(c['code'] == code_str for c in codes):
                break
        else:
            self.send_error_json('生成口令失败，请重试', 500)
            return

        code = {
            'id': code_id,
            'code': code_str,
            'app_id': app_id,
            'owner_id': user['id'],
            'is_active': True,
            'created_at': now
        }
        codes.append(code)
        save_codes(codes)

        self.send_json({
            'id': app['id'],
            'name': app['name'],
            'package_name': app['package_name'],
            'version_name': app['version_name'],
            'apk_size': app['apk_size'],
            'apk_size_str': format_size(app['apk_size']),
            'is_duplicate': app['is_duplicate'],
            'download_count': app['download_count'],
            'created_at': app['created_at'],
            'codes': [code_str]
        })

    def handle_generate_code(self, app_id):
        user = self.get_current_user()
        if not user:
            self.send_error_json('未授权', 401)
            return

        apps = get_apps()
        app = None
        for a in apps:
            if a['id'] == app_id and a['owner_id'] == user['id']:
                app = a
                break
        if not app:
            self.send_error_json('应用不存在', 404)
            return

        codes = get_codes()
        for _ in range(100):
            code_str = generate_code()
            if not any(c['code'] == code_str for c in codes):
                break
        else:
            self.send_error_json('生成口令失败，请重试', 500)
            return

        now = time.strftime('%Y-%m-%d %H:%M:%S')
        code = {
            'id': next_id(codes),
            'code': code_str,
            'app_id': app_id,
            'owner_id': user['id'],
            'is_active': True,
            'created_at': now
        }
        codes.append(code)
        save_codes(codes)
        self.send_json({'code': code_str})

    def handle_delete_app(self, app_id):
        user = self.get_current_user()
        if not user:
            self.send_error_json('未授权', 401)
            return

        apps = get_apps()
        app = None
        for a in apps:
            if a['id'] == app_id and a['owner_id'] == user['id']:
                app = a
                break
        if not app:
            self.send_error_json('应用不存在', 404)
            return

        if not app['is_duplicate'] and app['apk_path']:
            apk_path = Path(app['apk_path'])
            if apk_path.exists():
                try:
                    apk_path.unlink()
                except:
                    pass

        apps = [a for a in apps if a['id'] != app_id]
        save_apps(apps)

        codes = get_codes()
        codes = [c for c in codes if c['app_id'] != app_id]
        save_codes(codes)

        self.send_json({'message': '删除成功'})

    def handle_delete_code(self, app_id, code_str):
        user = self.get_current_user()
        if not user:
            self.send_error_json('未授权', 401)
            return

        apps = get_apps()
        app = None
        for a in apps:
            if a['id'] == app_id and a['owner_id'] == user['id']:
                app = a
                break
        if not app:
            self.send_error_json('应用不存在', 404)
            return

        codes = get_codes()
        found = False
        for c in codes:
            if c['code'] == code_str and c['app_id'] == app_id:
                c['is_active'] = False
                found = True
                break
        if not found:
            self.send_error_json('口令不存在', 404)
            return
        save_codes(codes)
        self.send_json({'message': '口令已删除'})

    def handle_download(self, code_str):
        code_obj = get_code_by_code(code_str)
        if not code_obj:
            self.send_error_json('口令无效', 404)
            return

        app = get_app_by_id(code_obj['app_id'])
        if not app:
            self.send_error_json('应用不存在', 404)
            return

        target_app = app
        if app['is_duplicate'] and app.get('real_app_id'):
            real = get_app_by_id(app['real_app_id'])
            if real:
                target_app = real

        apk_path = Path(target_app['apk_path']) if target_app.get('apk_path') else None
        if not apk_path or not apk_path.exists():
            self.send_error_json('文件不存在', 404)
            return

        apps = get_apps()
        for a in apps:
            if a['id'] == target_app['id']:
                a['download_count'] += 1
            if a['id'] == app['id'] and a['id'] != target_app['id']:
                a['download_count'] += 1
        save_apps(apps)

        filename = f"{target_app['name']}_{target_app['version_name']}.apk"
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.android.package-archive')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Content-Length', str(target_app['apk_size']))
        self.end_headers()
        with open(apk_path, 'rb') as f:
            self.wfile.write(f.read())

    def handle_download_info(self, code_str):
        code_obj = get_code_by_code(code_str)
        if not code_obj:
            self.send_error_json('口令无效', 404)
            return

        app = get_app_by_id(code_obj['app_id'])
        if not app:
            self.send_error_json('应用不存在', 404)
            return

        target_app = app
        if app['is_duplicate'] and app.get('real_app_id'):
            real = get_app_by_id(app['real_app_id'])
            if real:
                target_app = real

        self.send_json({
            'name': target_app['name'],
            'package_name': target_app['package_name'],
            'version_name': target_app['version_name'],
            'apk_size': target_app['apk_size'],
            'download_count': target_app['download_count'],
            'download_url': f'/api/download/{code_str}'
        })

    def handle_toggle_admin(self, user_id):
        current = self.get_current_user()
        if not current or not current['is_super_admin']:
            self.send_error_json('需要超级管理员权限', 403)
            return

        users = get_users()
        target = None
        for u in users:
            if u['id'] == user_id:
                target = u
                break
        if not target:
            self.send_error_json('用户不存在', 404)
            return
        if target['is_super_admin']:
            self.send_error_json('不能修改超级管理员')
            return

        target['is_admin'] = not target['is_admin']
        save_users(users)
        self.send_json({'message': '操作成功', 'is_admin': target['is_admin']})

    def handle_toggle_active(self, user_id):
        current = self.get_current_user()
        if not current or not current['is_super_admin']:
            self.send_error_json('需要超级管理员权限', 403)
            return

        users = get_users()
        target = None
        for u in users:
            if u['id'] == user_id:
                target = u
                break
        if not target:
            self.send_error_json('用户不存在', 404)
            return
        if target['is_super_admin']:
            self.send_error_json('不能禁用超级管理员')
            return

        target['is_active'] = not target['is_active']
        save_users(users)
        self.send_json({'message': '操作成功', 'is_active': target['is_active']})

    def handle_create_invite(self):
        user = self.get_current_user()
        if not user or not user['is_super_admin']:
            self.send_error_json('需要超级管理员权限', 403)
            return

        body = self.parse_json_body()
        max_uses = body.get('max_uses', 1)

        invites = get_invites()
        for _ in range(100):
            code_str = generate_invite_code(8)
            if not any(c['code'] == code_str for c in invites):
                break
        else:
            self.send_error_json('生成邀请码失败，请重试', 500)
            return

        now = time.strftime('%Y-%m-%d %H:%M:%S')
        invite = {
            'id': next_id(invites),
            'code': code_str,
            'created_by_id': user['id'],
            'is_used': False,
            'used_count': 0,
            'max_uses': max_uses,
            'created_at': now
        }
        invites.append(invite)
        save_invites(invites)

        self.send_json({
            'id': invite['id'],
            'code': invite['code'],
            'used_count': invite['used_count'],
            'max_uses': invite['max_uses'],
            'is_used': invite['is_used'],
            'created_at': invite['created_at']
        })

    def handle_delete_invite(self, code_id):
        user = self.get_current_user()
        if not user or not user['is_super_admin']:
            self.send_error_json('需要超级管理员权限', 403)
            return

        invites = get_invites()
        target = None
        for c in invites:
            if c['id'] == code_id:
                target = c
                break
        if not target:
            self.send_error_json('邀请码不存在', 404)
            return
        if target['used_count'] > 0:
            self.send_error_json('已使用的邀请码不能删除')
            return

        invites = [c for c in invites if c['id'] != code_id]
        save_invites(invites)
        self.send_json({'message': '删除成功'})


def run(host='0.0.0.0', port=8000):
    init_data()
    server = HTTPServer((host, port), Handler)
    print(f"服务器启动: http://{host}:{port}")
    print(f"管理员账号: {SUPER_ADMIN_USERNAME} / {SUPER_ADMIN_PASSWORD}")
    server.serve_forever()


if __name__ == '__main__':
    run()

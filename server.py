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

try:
    from apkutils import APK
    HAS_APKUTILS = True
except ImportError:
    HAS_APKUTILS = False

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
APK_DIR = UPLOAD_DIR / "apks"
ICON_DIR = UPLOAD_DIR / "icons"
TEMPLATE_DIR = BASE_DIR / "server" / "templates"
STATIC_DIR = BASE_DIR / "server" / "static"

for d in [DATA_DIR, UPLOAD_DIR, APK_DIR, ICON_DIR]:
    d.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = DATA_DIR / "config.json"
USERS_FILE = DATA_DIR / "users.json"
APPS_FILE = DATA_DIR / "apps.json"
CODES_FILE = DATA_DIR / "codes.json"
INVITES_FILE = DATA_DIR / "invites.json"
CATEGORIES_FILE = DATA_DIR / "categories.json"


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


def load_secret_key():
    config = load_json(CONFIG_FILE, {})
    if 'secret_key' not in config:
        config['secret_key'] = secrets.token_hex(32)
        save_json(CONFIG_FILE, config)
    return config['secret_key']


SECRET_KEY = os.getenv("SECRET_KEY", load_secret_key())
SUPER_ADMIN_USERNAME = os.getenv("SUPER_ADMIN_USERNAME", "admin")
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "admin123456")
MAX_APPS_PER_USER = 100
MAX_APPS_PER_CODE = 10
MAX_CODES_TO_MERGE = 10
CODE_LENGTH = 4
CODE_CHARS = "0123456789ABCDEF"


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


def parse_apk_info(file_path):
    info = {
        'app_name': '',
        'package_name': '',
        'version_name': '',
        'version_code': 1,
        'icon_data': None
    }
    if not HAS_APKUTILS:
        return info

    try:
        apk = APK(file_path)
        manifest = apk.get_manifest()

        if 'package' in manifest:
            info['package_name'] = manifest['package']

        if 'versionName' in manifest:
            info['version_name'] = manifest['versionName']

        if 'versionCode' in manifest:
            info['version_code'] = int(manifest['versionCode'])

        app_name = ''
        if 'application' in manifest:
            app = manifest['application']
            if 'label' in app:
                app_name = str(app['label'])
            elif app_name == '' and 'meta-data' in app:
                for md in app['meta-data']:
                    if md.get('name') == 'com.google.android.gms.appinvite.APP_NAME':
                        app_name = md.get('value', '')
                        break

        if app_name == '' or app_name.startswith('@'):
            res = apk.get_resource()
            if res is not None:
                try:
                    strings = res.get_strings()
                    if strings:
                        app_name = list(strings.values())[0] if strings else ''
                except:
                    pass

        info['app_name'] = app_name if app_name else ''

        icon_path = None
        if 'application' in manifest:
            app = manifest['application']
            if 'icon' in app:
                icon_path = str(app['icon'])

        if icon_path and icon_path.startswith('@'):
            try:
                res = apk.get_resource()
                if res is not None:
                    mipmap_dirs = ['mipmap-hdpi', 'mipmap-xhdpi', 'mipmap-xxhdpi', 'mipmap-xxxhdpi']
                    drawable_dirs = ['drawable-hdpi', 'drawable-xhdpi', 'drawable-xxhdpi', 'drawable-xxxhdpi']
                    all_dirs = mipmap_dirs + drawable_dirs
                    icon_name = icon_path[1:]
                    for dir_name in all_dirs:
                        for entry in apk.get_files():
                            if dir_name in entry and icon_name in entry:
                                icon_data = apk.get_file(entry)
                                if icon_data:
                                    info['icon_data'] = icon_data
                                    break
                        if info['icon_data']:
                            break
            except:
                pass

    except Exception as e:
        print(f"APK解析错误: {e}")

    return info


def save_icon(app_id, icon_data):
    icon_path = ICON_DIR / f"{app_id}.png"
    with open(icon_path, 'wb') as f:
        f.write(icon_data)
    return str(icon_path)


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


def get_categories():
    cats = load_json(CATEGORIES_FILE, [])
    if not cats:
        cats = [
            {'id': 1, 'name': '影音娱乐', 'color': '#FF6B6B'},
            {'id': 2, 'name': '工具软件', 'color': '#4ECDC4'},
            {'id': 3, 'name': '游戏', 'color': '#FFE66D'},
            {'id': 4, 'name': '社交聊天', 'color': '#95E1D3'},
            {'id': 5, 'name': '办公商务', 'color': '#A29BFE'},
            {'id': 6, 'name': '教育学习', 'color': '#FD79A8'},
            {'id': 7, 'name': '购物支付', 'color': '#00B894'},
            {'id': 8, 'name': '其他', 'color': '#636E72'}
        ]
        save_categories(cats)
    return cats


def save_categories(categories):
    save_json(CATEGORIES_FILE, categories)


def get_category_by_id(cat_id):
    for c in get_categories():
        if c['id'] == cat_id:
            return c
    return None


def parse_multipart(content_type, body):
    result = {}
    match = re.search(r'boundary=([^;]+)', content_type)
    if not match:
        return result
    boundary = match.group(1).strip().strip('"')
    if boundary.startswith('--'):
        boundary = boundary[2:]

    boundary_bytes = b'--' + boundary.encode()
    parts = body.split(boundary_bytes)
    for part in parts:
        part = part.strip()
        if not part or part == b'--':
            continue

        header_end = part.find(b'\r\n\r\n')
        if header_end == -1:
            continue

        headers_text = part[:header_end].decode('utf-8', errors='ignore')
        content = part[header_end + 4:]

        while content.endswith(b'\r\n'):
            content = content[:-2]
        if content.endswith(b'--'):
            content = content[:-2]
        while content.endswith(b'\r\n'):
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

    get_categories()


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

        if path.startswith('/api/download/info/'):
            code_str = path[len('/api/download/info/'):]
            self.handle_download_info(code_str)
            return

        if path.startswith('/api/download/'):
            code_str = path[len('/api/download/'):]
            self.handle_download(code_str)
            return

        if path.startswith('/api/icons/'):
            icon_name = path[len('/api/icons/'):]
            icon_path = ICON_DIR / icon_name
            if icon_path.exists() and icon_path.is_file():
                self.send_file(icon_path, 'image/png')
            else:
                self.send_error_json('图标不存在', 404)
            return

        if path.startswith('/api/'):
            self.handle_api_get(path, parsed)
            return

        if path.startswith('/static/'):
            rel = path[len('/static/'):]
            filepath = STATIC_DIR / rel
            if filepath.exists() and filepath.is_file():
                self.send_file(filepath)
            else:
                self.send_error_json('Not Found', 404)
            return

        self.send_error_json('Not Found', 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/'):
            self.handle_api_post(path, parsed)
            return

        self.send_error_json('Not Found', 404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/'):
            self.handle_api_put(path, parsed)
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
            self.send_json({'status': 'ok', 'version': '2.1.0'})
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
            categories = get_categories()
            cat_map = {c['id']: c for c in categories}
            result = []
            for app in user_apps:
                app_codes = []
                for c in codes:
                    app_ids = c.get('app_ids', [])
                    if c['app_id'] == app['id'] or app['id'] in app_ids:
                        if c['is_active']:
                            app_codes.append(c['code'])
                cat_name = cat_map.get(app.get('category_id'), {}).get('name', '')
                result.append({
                    'id': app['id'],
                    'name': app['name'],
                    'package_name': app['package_name'],
                    'version_name': app['version_name'],
                    'apk_size': app['apk_size'],
                    'apk_size_str': format_size(app['apk_size']),
                    'download_count': app['download_count'],
                    'is_duplicate': app['is_duplicate'],
                    'category_id': app.get('category_id', 0),
                    'category_name': cat_name,
                    'icon_url': app.get('icon_url', ''),
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

        if path.startswith('/api/codes/'):
            code_str = path[len('/api/codes/'):]
            self.handle_code_info_app(code_str)
            return

        if path == '/api/download/info/':
            code_str = path.rsplit('/', 1)[-1] if '/' in path else ''
            self.handle_download_info(code_str)
            return

        if path.startswith('/api/download/info/'):
            code_str = path[len('/api/download/info/'):]
            self.handle_download_info(code_str)
            return

        if path == '/api/categories':
            user = self.get_current_user()
            if not user:
                self.send_error_json('未授权', 401)
                return
            self.send_json(get_categories())
            return

        if path == '/api/my/codes':
            user = self.get_current_user()
            if not user:
                self.send_error_json('未授权', 401)
                return
            codes = get_codes()
            apps = get_apps()
            categories = get_categories()
            cat_map = {c['id']: c for c in categories}
            result = []
            for c in sorted(codes, key=lambda x: x['id'], reverse=True):
                if c['owner_id'] != user['id'] or not c['is_active']:
                    continue
                app_ids = c.get('app_ids', [])
                if not app_ids and c.get('app_id'):
                    app_ids = [c['app_id']]
                code_apps = []
                for aid in app_ids:
                    app = get_app_by_id(aid)
                    if app:
                        cat_name = cat_map.get(app.get('category_id'), {}).get('name', '')
                        code_apps.append({
                            'id': app['id'],
                            'name': app['name'],
                            'category_name': cat_name
                        })
                result.append({
                    'id': c['id'],
                    'code': c['code'],
                    'app_ids': app_ids,
                    'apps': code_apps,
                    'created_at': c['created_at']
                })
            self.send_json(result)
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

        if path == '/api/codes/merge':
            self.handle_merge_codes()
            return

        if path == '/api/codes/create-multi':
            self.handle_create_multi_code()
            return

        if path == '/api/categories':
            self.handle_create_category()
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

    def handle_api_put(self, path, parsed):
        if path.startswith('/api/apps/'):
            try:
                app_id = int(path.rsplit('/', 1)[-1])
                self.handle_update_app(app_id)
            except:
                self.send_error_json('Not Found', 404)
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

        if path.startswith('/api/codes/'):
            try:
                code_id = int(path.rsplit('/', 1)[-1])
                self.handle_delete_code_by_id(code_id)
            except:
                self.send_error_json('Not Found', 404)
            return

        if path.startswith('/api/categories/'):
            try:
                cat_id = int(path.rsplit('/', 1)[-1])
                self.handle_delete_category(cat_id)
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
        file_id = str(uuid.uuid4())
        save_name = f"{file_id}.apk"
        save_path = APK_DIR / save_name

        with open(save_path, 'wb') as f:
            f.write(file_data)

        apk_info = parse_apk_info(str(save_path))
        app_name = apk_info['app_name'] if apk_info['app_name'] else (form.get('app_name') or filename.rsplit('.', 1)[0])
        if isinstance(app_name, dict):
            app_name = filename.rsplit('.', 1)[0]
        package_name = apk_info['package_name'] if apk_info['package_name'] else f"com.uploaded.{secrets.token_hex(4)}"
        version_name = apk_info['version_name'] if apk_info['version_name'] else "1.0"

        icon_url = ''
        if apk_info['icon_data']:
            app_id_temp = next_id(apps)
            icon_path = save_icon(app_id_temp, apk_info['icon_data'])
            icon_url = f'/api/icons/{app_id_temp}.png'

        category_id = 0
        cat_str = form.get('category_id')
        if cat_str and cat_str.isdigit():
            category_id = int(cat_str)

        now = time.strftime('%Y-%m-%d %H:%M:%S')
        app_id = next_id(apps)
        app = {
            'id': app_id,
            'name': app_name,
            'package_name': package_name,
            'version_name': version_name,
            'version_code': apk_info['version_code'],
            'apk_path': str(save_path),
            'apk_size': apk_size,
            'description': '',
            'owner_id': user['id'],
            'real_app_id': None,
            'is_duplicate': False,
            'download_count': 0,
            'category_id': category_id,
            'icon_url': icon_url,
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
            'app_ids': [],
            'owner_id': user['id'],
            'is_active': True,
            'created_at': now
        }
        codes.append(code)
        save_codes(codes)

        categories = get_categories()
        cat_map = {c['id']: c for c in categories}
        cat_name = cat_map.get(category_id, {}).get('name', '')

        self.send_json({
            'id': app['id'],
            'name': app['name'],
            'package_name': app['package_name'],
            'version_name': app['version_name'],
            'apk_size': app['apk_size'],
            'apk_size_str': format_size(app['apk_size']),
            'is_duplicate': app['is_duplicate'],
            'download_count': app['download_count'],
            'category_id': category_id,
            'category_name': cat_name,
            'icon_url': icon_url,
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
            'app_ids': [],
            'owner_id': user['id'],
            'is_active': True,
            'created_at': now
        }
        codes.append(code)
        save_codes(codes)
        self.send_json({'code': code_str})

    def handle_merge_codes(self):
        user = self.get_current_user()
        if not user:
            self.send_error_json('未授权', 401)
            return

        body = self.parse_json_body()
        source_code_ids = body.get('code_ids', [])

        if len(source_code_ids) < 2:
            self.send_error_json('至少选择2个口令进行合并')
            return

        if len(source_code_ids) > MAX_CODES_TO_MERGE:
            self.send_error_json(f'最多合并{MAX_CODES_TO_MERGE}个口令')
            return

        codes = get_codes()
        apps = get_apps()
        user_codes = [c for c in codes if c['owner_id'] == user['id'] and c['is_active']]

        selected_codes = []
        all_app_ids = []
        for cid in source_code_ids:
            found = False
            for c in user_codes:
                if c['id'] == cid:
                    found = True
                    selected_codes.append(c)
                    app_ids = c.get('app_ids', [])
                    if not app_ids and c.get('app_id'):
                        app_ids = [c['app_id']]
                    for aid in app_ids:
                        if aid not in all_app_ids:
                            all_app_ids.append(aid)
                    break
            if not found:
                self.send_error_json(f'口令ID {cid} 不存在或无权操作')
                return

        if len(all_app_ids) > MAX_APPS_PER_CODE:
            self.send_error_json(f'合并后应用数量不能超过{MAX_APPS_PER_CODE}个')
            return

        for c in selected_codes:
            c['is_active'] = False
        save_codes(codes)

        for _ in range(100):
            new_code_str = generate_code()
            if not any(c['code'] == new_code_str for c in codes):
                break
        else:
            self.send_error_json('生成口令失败，请重试', 500)
            return

        now = time.strftime('%Y-%m-%d %H:%M:%S')
        new_code = {
            'id': next_id(codes),
            'code': new_code_str,
            'app_id': None,
            'app_ids': all_app_ids,
            'owner_id': user['id'],
            'is_active': True,
            'created_at': now
        }
        codes.append(new_code)
        save_codes(codes)

        merged_apps = []
        categories = get_categories()
        cat_map = {c['id']: c for c in categories}
        for aid in all_app_ids:
            app = get_app_by_id(aid)
            if app:
                cat_name = cat_map.get(app.get('category_id'), {}).get('name', '')
                merged_apps.append({
                    'id': app['id'],
                    'name': app['name'],
                    'category_name': cat_name
                })

        self.send_json({
            'code': new_code_str,
            'app_ids': all_app_ids,
            'apps': merged_apps,
            'message': f'成功合并{len(source_code_ids)}个口令，共{len(all_app_ids)}个应用'
        })

    def handle_create_multi_code(self):
        user = self.get_current_user()
        if not user:
            self.send_error_json('未授权', 401)
            return

        body = self.parse_json_body()
        app_ids = body.get('app_ids', [])

        if not app_ids:
            self.send_error_json('请选择应用')
            return

        if len(app_ids) > MAX_APPS_PER_CODE:
            self.send_error_json(f'一个口令最多包含{MAX_APPS_PER_CODE}个应用')
            return

        apps = get_apps()
        for aid in app_ids:
            found = False
            for a in apps:
                if a['id'] == aid and a['owner_id'] == user['id']:
                    found = True
                    break
            if not found:
                self.send_error_json(f'应用ID {aid} 不存在或无权操作')
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
            'app_id': None,
            'app_ids': app_ids,
            'owner_id': user['id'],
            'is_active': True,
            'created_at': now
        }
        codes.append(code)
        save_codes(codes)

        merged_apps = []
        categories = get_categories()
        cat_map = {c['id']: c for c in categories}
        for aid in app_ids:
            app = get_app_by_id(aid)
            if app:
                cat_name = cat_map.get(app.get('category_id'), {}).get('name', '')
                merged_apps.append({
                    'id': app['id'],
                    'name': app['name'],
                    'category_name': cat_name
                })

        self.send_json({
            'code': code_str,
            'app_ids': app_ids,
            'apps': merged_apps,
            'message': f'成功创建口令，包含{len(app_ids)}个应用'
        })

    def handle_create_category(self):
        user = self.get_current_user()
        if not user or not user['is_admin']:
            self.send_error_json('需要管理员权限', 403)
            return

        body = self.parse_json_body()
        name = body.get('name', '').strip()
        color = body.get('color', '#636E72')

        if not name:
            self.send_error_json('分类名称不能为空')
            return

        categories = get_categories()
        if any(c['name'] == name for c in categories):
            self.send_error_json('分类名称已存在')
            return

        new_cat = {
            'id': next_id(categories),
            'name': name,
            'color': color
        }
        categories.append(new_cat)
        save_categories(categories)
        self.send_json(new_cat)

    def handle_update_app(self, app_id):
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

        body = self.parse_json_body()
        category_id = body.get('category_id', 0)

        if category_id:
            categories = get_categories()
            if not any(c['id'] == category_id for c in categories):
                self.send_error_json('分类不存在', 404)
                return

        app['category_id'] = category_id
        save_apps(apps)

        cat_name = ''
        if category_id:
            cat = get_category_by_id(category_id)
            if cat:
                cat_name = cat.get('name', '')

        self.send_json({
            'id': app['id'],
            'category_id': category_id,
            'category_name': cat_name
        })

    def handle_delete_category(self, cat_id):
        user = self.get_current_user()
        if not user or not user['is_admin']:
            self.send_error_json('需要管理员权限', 403)
            return

        categories = get_categories()
        if not any(c['id'] == cat_id for c in categories):
            self.send_error_json('分类不存在', 404)
            return

        apps = get_apps()
        if any(a.get('category_id') == cat_id for a in apps):
            self.send_error_json('该分类下还有应用，无法删除')
            return

        categories = [c for c in categories if c['id'] != cat_id]
        save_categories(categories)
        self.send_json({'message': '删除成功'})

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

        if app.get('icon_url'):
            icon_name = app['icon_url'].split('/')[-1]
            icon_path = ICON_DIR / icon_name
            if icon_path.exists():
                try:
                    icon_path.unlink()
                except:
                    pass

        apps = [a for a in apps if a['id'] != app_id]
        save_apps(apps)

        codes = get_codes()
        for c in codes:
            app_ids = c.get('app_ids', [])
            if c['app_id'] == app_id:
                c['is_active'] = False
            elif app_id in app_ids:
                app_ids.remove(app_id)
                if not app_ids:
                    c['is_active'] = False
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

    def handle_delete_code_by_id(self, code_id):
        user = self.get_current_user()
        if not user:
            self.send_error_json('未授权', 401)
            return

        codes = get_codes()
        found = False
        for c in codes:
            if c['id'] == code_id and c['owner_id'] == user['id']:
                c['is_active'] = False
                found = True
                break
        if not found:
            self.send_error_json('口令不存在', 404)
            return
        save_codes(codes)
        self.send_json({'message': '口令已删除'})

    def handle_download(self, path_suffix):
        parts = path_suffix.rstrip('/').split('/')
        code_str = parts[0] if len(parts) > 0 else ''
        app_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None

        code_obj = get_code_by_code(code_str)
        if not code_obj:
            self.send_error_json('口令无效', 404)
            return

        app_ids = code_obj.get('app_ids', [])
        if not app_ids and code_obj.get('app_id'):
            app_ids = [code_obj['app_id']]

        if not app_ids:
            self.send_error_json('口令无效', 404)
            return

        if app_id:
            if app_id not in app_ids:
                self.send_error_json('应用不在口令中', 404)
                return
            target_app_id = app_id
        else:
            target_app_id = app_ids[0]

        app = get_app_by_id(target_app_id)
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
        try:
            filename.encode('latin-1')
            disposition = f'attachment; filename="{filename}"'
        except UnicodeEncodeError:
            import urllib.parse
            encoded_name = urllib.parse.quote(filename)
            disposition = f"attachment; filename*=UTF-8''{encoded_name}"
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.android.package-archive')
        self.send_header('Content-Disposition', disposition)
        self.send_header('Content-Length', str(target_app['apk_size']))
        self.end_headers()
        with open(apk_path, 'rb') as f:
            self.wfile.write(f.read())

    def handle_download_info(self, code_str):
        code_obj = get_code_by_code(code_str)
        if not code_obj:
            self.send_error_json('口令无效', 404)
            return

        app_ids = code_obj.get('app_ids', [])
        if not app_ids and code_obj.get('app_id'):
            app_ids = [code_obj['app_id']]

        if not app_ids:
            self.send_error_json('口令无效', 404)
            return

        app = get_app_by_id(app_ids[0])
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

    def handle_code_info_app(self, code_str):
        code_obj = get_code_by_code(code_str)
        if not code_obj:
            self.send_error_json('口令无效', 404)
            return

        app_ids = code_obj.get('app_ids', [])
        if not app_ids and code_obj.get('app_id'):
            app_ids = [code_obj['app_id']]

        if not app_ids:
            self.send_error_json('口令无效', 404)
            return

        apps = []
        for aid in app_ids:
            app = get_app_by_id(aid)
            if not app:
                continue
            target_app = app
            if app['is_duplicate'] and app.get('real_app_id'):
                real = get_app_by_id(app['real_app_id'])
                if real:
                    target_app = real
            cat_id = target_app.get('category_id', 0)
            cat_name = ''
            if cat_id:
                cat = get_category_by_id(cat_id)
                if cat:
                    cat_name = cat.get('name', '')
            apps.append({
                'id': target_app['id'],
                'name': target_app['name'],
                'package_name': target_app['package_name'],
                'version_name': target_app['version_name'],
                'version_code': target_app.get('version_code', 1),
                'apk_size': target_app['apk_size'],
                'download_url': f'/api/download/{code_str}/{target_app["id"]}',
                'description': target_app.get('description', ''),
                'download_count': target_app['download_count'],
                'category_id': cat_id,
                'category_name': cat_name,
                'icon_url': target_app.get('icon_url', '')
            })

        if not apps:
            self.send_error_json('应用不存在', 404)
            return

        categories = []
        seen_cats = set()
        for a in apps:
            cid = a['category_id']
            if cid and cid not in seen_cats:
                seen_cats.add(cid)
                categories.append({'id': cid, 'name': a['category_name']})

        if len(apps) == 1:
            self.send_json({
                'type': 'single',
                'app': apps[0]
            })
        else:
            self.send_json({
                'type': 'multi',
                'categories': categories,
                'apps': apps
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

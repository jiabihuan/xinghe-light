const API = '/api';
let token = localStorage.getItem('token') || '';
let currentUser = null;

function api(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return fetch(`${API}${url}`, { ...options, headers }).then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
            throw new Error(data.detail || '请求失败');
        }
        return data;
    });
}

function showToast(msg, type = '') {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.className = `toast show ${type}`;
    setTimeout(() => { toast.className = 'toast'; }, 2500);
}

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
    document.getElementById(pageId).classList.remove('hidden');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.add('hidden');
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('login-form').classList.toggle('hidden', tab !== 'login');
        document.getElementById('register-form').classList.toggle('hidden', tab !== 'register');
    });
});

document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');
    errorEl.textContent = '';

    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    try {
        const res = await fetch(`${API}/auth/login`, {
            method: 'POST',
            body: formData
        }).then(r => r.json().then(d => ({ ok: r.ok, data: d })));

        if (!res.ok) {
            errorEl.textContent = res.data.detail || '登录失败';
            return;
        }

        token = res.data.access_token;
        currentUser = res.data.user;
        localStorage.setItem('token', token);
        showToast('登录成功', 'success');
        enterApp();
    } catch (err) {
        errorEl.textContent = err.message;
    }
});

document.getElementById('register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('reg-username').value.trim();
    const password = document.getElementById('reg-password').value;
    const inviteCode = document.getElementById('reg-invite').value.trim();
    const errorEl = document.getElementById('reg-error');
    errorEl.textContent = '';

    try {
        const res = await api('/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, invite_code: inviteCode })
        });
        token = res.access_token;
        currentUser = res.user;
        localStorage.setItem('token', token);
        showToast('注册成功', 'success');
        enterApp();
    } catch (err) {
        errorEl.textContent = err.message;
    }
});

document.getElementById('btn-logout').addEventListener('click', () => {
    token = '';
    currentUser = null;
    localStorage.removeItem('token');
    showPage('login-page');
    showToast('已退出登录');
});

async function enterApp() {
    showPage('main-page');
    try {
        currentUser = await api('/auth/me');
    } catch {
        token = '';
        localStorage.removeItem('token');
        showPage('login-page');
        return;
    }

    document.getElementById('user-name').textContent = currentUser.username;
    if (currentUser.is_super_admin) {
        document.getElementById('user-role').textContent = '超级管理员';
        document.getElementById('nav-admin').style.display = 'flex';
    } else if (currentUser.is_admin) {
        document.getElementById('user-role').textContent = '管理员';
        document.getElementById('nav-admin').style.display = 'flex';
    } else {
        document.getElementById('user-role').textContent = '普通用户';
        document.getElementById('nav-admin').style.display = 'none';
    }

    loadApps();
    if (currentUser.is_super_admin) {
        loadAdminUsers();
        loadAdminInvites();
        loadStats();
    }
}

document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        const page = item.dataset.page;
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        item.classList.add('active');
        document.getElementById('page-apps').classList.toggle('hidden', page !== 'apps');
        document.getElementById('page-admin').classList.toggle('hidden', page !== 'admin');
    });
});

document.querySelectorAll('.admin-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const t = tab.dataset.adminTab;
        document.querySelectorAll('.admin-tab').forEach(tt => tt.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('admin-users').classList.toggle('hidden', t !== 'users');
        document.getElementById('admin-invites').classList.toggle('hidden', t !== 'invites');
        document.getElementById('admin-stats').classList.toggle('hidden', t !== 'stats');
    });
});

async function loadApps() {
    try {
        const count = await api('/apps/count');
        document.getElementById('app-count').textContent = `${count.count} / ${count.max}`;
    } catch {}

    try {
        const apps = await api('/apps?page_size=100');
        const grid = document.getElementById('app-grid');
        const empty = document.getElementById('empty-state');

        if (apps.length === 0) {
            grid.innerHTML = '';
            empty.style.display = 'block';
            return;
        }

        empty.style.display = 'none';
        grid.innerHTML = apps.map(app => `
            <div class="app-card">
                <div class="app-card-header">
                    <div class="app-icon">${escapeHtml(app.name.charAt(0))}</div>
                    <div class="app-actions">
                        <button class="action-btn delete" onclick="deleteApp(${app.id})">删除</button>
                    </div>
                </div>
                <div class="app-name">${escapeHtml(app.name)}</div>
                <div class="app-package">${escapeHtml(app.package_name)}</div>
                <div class="app-meta">
                    <span>📦 ${formatSize(app.apk_size)}</span>
                    <span>⬇️ ${app.download_count}</span>
                    ${app.is_duplicate ? '<span style="color:#ff9800">⚡ 去重</span>' : ''}
                </div>
                <div class="app-codes">
                    <div class="codes-label">口令</div>
                    <div class="code-list">
                        ${app.codes.map(c => `
                            <span class="code-tag" onclick="copyCode('${c}')" title="点击复制">
                                ${c}
                                <span class="code-delete" onclick="event.stopPropagation();deleteCode(${app.id},'${c}')">&times;</span>
                            </span>
                        `).join('')}
                        <button class="btn-add-code" onclick="addCode(${app.id})">+ 生成</button>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (err) {
        showToast('加载应用失败', 'error');
    }
}

function copyCode(code) {
    navigator.clipboard.writeText(code).then(() => {
        showToast(`口令 ${code} 已复制`, 'success');
    }).catch(() => {
        showToast('复制失败', 'error');
    });
}

async function addCode(appId) {
    try {
        const res = await api(`/apps/${appId}/generate-code`, { method: 'POST' });
        showToast(`新口令: ${res.code}`, 'success');
        loadApps();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function deleteCode(appId, code) {
    if (!confirm(`确定删除口令 ${code}?`)) return;
    try {
        await api(`/apps/${appId}/codes/${code}`, { method: 'DELETE' });
        showToast('口令已删除', 'success');
        loadApps();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function deleteApp(appId) {
    if (!confirm('确定删除此应用?所有口令也将失效')) return;
    try {
        await api(`/apps/${appId}`, { method: 'DELETE' });
        showToast('应用已删除', 'success');
        loadApps();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

document.getElementById('btn-upload').addEventListener('click', () => {
    document.getElementById('upload-modal').classList.remove('hidden');
    document.getElementById('upload-app-name').value = '';
    document.getElementById('upload-file').value = '';
    document.getElementById('file-name').textContent = '';
});

document.getElementById('upload-area').addEventListener('click', () => {
    document.getElementById('upload-file').click();
});

document.getElementById('upload-file').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        document.getElementById('file-name').textContent = file.name;
    }
});

document.getElementById('btn-upload-confirm').addEventListener('click', async () => {
    const fileInput = document.getElementById('upload-file');
    const appName = document.getElementById('upload-app-name').value.trim();

    if (!fileInput.files || fileInput.files.length === 0) {
        showToast('请选择APK文件', 'error');
        return;
    }

    const btn = document.getElementById('btn-upload-confirm');
    btn.disabled = true;
    btn.textContent = '上传中...';

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    if (appName) {
        formData.append('app_name', appName);
    }

    try {
        const res = await api('/apps/upload', {
            method: 'POST',
            body: formData
        });
        showToast('上传成功', 'success');
        closeModal('upload-modal');
        loadApps();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '上传';
    }
});

async function loadAdminUsers() {
    try {
        const users = await api('/admin/users?page_size=100');
        const tbody = document.getElementById('users-tbody');
        tbody.innerHTML = users.map(u => `
            <tr>
                <td>${u.id}</td>
                <td>${escapeHtml(u.username)}</td>
                <td>${u.app_count}</td>
                <td>
                    <span class="role-badge ${u.is_super_admin ? 'role-admin' : ''}">
                        ${u.is_super_admin ? '超管' : u.is_admin ? '管理员' : '用户'}
                    </span>
                </td>
                <td>
                    <span class="status-badge ${u.is_active ? 'status-active' : 'status-disabled'}">
                        ${u.is_active ? '正常' : '禁用'}
                    </span>
                </td>
                <td>${u.created_at}</td>
                <td>
                    ${!u.is_super_admin ? `
                        <button class="action-btn edit" onclick="toggleAdmin(${u.id})">
                            ${u.is_admin ? '取消管理' : '设为管理'}
                        </button>
                        <button class="action-btn ${u.is_active ? 'delete' : 'edit'}" onclick="toggleActive(${u.id})">
                            ${u.is_active ? '禁用' : '启用'}
                        </button>
                    ` : '-'}
                </td>
            </tr>
        `).join('');
    } catch {}
}

async function toggleAdmin(userId) {
    try {
        await api(`/admin/users/${userId}/toggle-admin`, { method: 'POST' });
        showToast('操作成功', 'success');
        loadAdminUsers();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function toggleActive(userId) {
    try {
        await api(`/admin/users/${userId}/toggle-active`, { method: 'POST' });
        showToast('操作成功', 'success');
        loadAdminUsers();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function loadAdminInvites() {
    try {
        const codes = await api('/admin/invite-codes?page_size=100');
        const tbody = document.getElementById('invites-tbody');
        tbody.innerHTML = codes.map(c => `
            <tr>
                <td>${c.id}</td>
                <td>
                    <code style="background:#f5f5f5;padding:2px 6px;border-radius:4px;cursor:pointer" onclick="navigator.clipboard.writeText('${c.code}');showToast('已复制','success')">
                        ${c.code}
                    </code>
                </td>
                <td>${c.used_count} / ${c.max_uses}</td>
                <td>
                    <span class="status-badge ${c.is_used ? 'status-used' : 'status-unused'}">
                        ${c.is_used ? '已用完' : '可用'}
                    </span>
                </td>
                <td>${c.created_at}</td>
                <td>
                    ${c.used_count === 0 ? `
                        <button class="action-btn delete" onclick="deleteInvite(${c.id})">删除</button>
                    ` : '-'}
                </td>
            </tr>
        `).join('');
    } catch {}
}

document.getElementById('btn-create-invite').addEventListener('click', async () => {
    try {
        const res = await api('/admin/invite-codes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ max_uses: 1 })
        });
        showToast(`邀请码: ${res.code}`, 'success');
        loadAdminInvites();
    } catch (err) {
        showToast(err.message, 'error');
    }
});

async function deleteInvite(id) {
    if (!confirm('确定删除此邀请码?')) return;
    try {
        await api(`/admin/invite-codes/${id}`, { method: 'DELETE' });
        showToast('已删除', 'success');
        loadAdminInvites();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function loadStats() {
    try {
        const s = await api('/admin/stats');
        document.getElementById('stat-users').textContent = s.user_count;
        document.getElementById('stat-apps').textContent = s.app_count;
        document.getElementById('stat-codes').textContent = s.code_count;
        document.getElementById('stat-invites').textContent = s.invite_code_count;
    } catch {}
}

if (token) {
    enterApp();
} else {
    showPage('login-page');
}

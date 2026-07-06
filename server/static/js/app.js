const API = '/api';
let token = localStorage.getItem('token') || '';
let currentUser = null;
let categories = [];
let apps = [];
let selectedAppIds = [];
let selectedCodeIds = [];

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
    try {
        currentUser = await api('/auth/me');
    } catch {
        token = '';
        localStorage.removeItem('token');
        showPage('login-page');
        return;
    }

    showPage('main-page');
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

    await loadCategories();
    loadApps();
    if (currentUser.is_super_admin) {
        loadAdminUsers();
        loadAdminInvites();
        loadAdminCategories();
        loadStats();
    }
}

async function loadCategories() {
    try {
        categories = await api('/categories');
        const select = document.getElementById('upload-category');
        if (select) {
            select.innerHTML = '<option value="0">请选择分类</option>' +
                categories.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
        }
    } catch {}
}

document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        const page = item.dataset.page;
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        item.classList.add('active');
        document.getElementById('page-apps').classList.toggle('hidden', page !== 'apps');
        document.getElementById('page-codes').classList.toggle('hidden', page !== 'codes');
        document.getElementById('page-admin').classList.toggle('hidden', page !== 'admin');
        if (page === 'codes') {
            loadCodes();
        }
    });
});

document.querySelectorAll('.admin-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const t = tab.dataset.adminTab;
        document.querySelectorAll('.admin-tab').forEach(tt => tt.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('admin-users').classList.toggle('hidden', t !== 'users');
        document.getElementById('admin-invites').classList.toggle('hidden', t !== 'invites');
        document.getElementById('admin-categories').classList.toggle('hidden', t !== 'categories');
        document.getElementById('admin-stats').classList.toggle('hidden', t !== 'stats');
        if (t === 'categories') {
            loadAdminCategories();
        }
    });
});

async function loadApps() {
    try {
        const count = await api('/apps/count');
        document.getElementById('app-count').textContent = `${count.count} / ${count.max}`;
    } catch {}

    try {
        apps = await api('/apps');
        const grid = document.getElementById('app-grid');
        const empty = document.getElementById('empty-state');

        if (apps.length === 0) {
            grid.innerHTML = '';
            empty.style.display = 'block';
            return;
        }

        empty.style.display = 'none';
        grid.innerHTML = apps.map(app => {
            const cat = categories.find(c => c.id === app.category_id);
            const iconHtml = app.icon_url ?
                `<img src="${app.icon_url}" alt="${escapeHtml(app.name)}">` :
                escapeHtml(app.name.charAt(0));
            const categoryOptions = categories.map(c => 
                `<option value="${c.id}" ${app.category_id === c.id ? 'selected' : ''}>${escapeHtml(c.name)}</option>`
            ).join('');
            return `
            <div class="app-card">
                <div class="app-card-header">
                    <div class="app-icon">${iconHtml}</div>
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
                <div class="app-category-select">
                    <label>分类:</label>
                    <select class="category-select" onchange="updateAppCategory(${app.id}, this.value)">
                        <option value="0">请选择分类</option>
                        ${categoryOptions}
                    </select>
                </div>
                <div class="app-codes">
                    <div class="codes-label">口令</div>
                    <div class="code-list-container">
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
        `;
        }).join('');
    } catch (err) {
        showToast('加载应用失败', 'error');
    }
}

async function updateAppCategory(appId, categoryId) {
    try {
        await api(`/apps/${appId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category_id: parseInt(categoryId) })
        });
        showToast('分类已更新', 'success');
        loadApps();
        loadCodes();
    } catch (err) {
        showToast(err.message, 'error');
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
        loadCodes();
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
        loadCodes();
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
        loadCodes();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

document.getElementById('btn-upload').addEventListener('click', () => {
    document.getElementById('upload-modal').classList.remove('hidden');
    document.getElementById('upload-app-name').value = '';
    document.getElementById('upload-category').value = '0';
    document.getElementById('upload-file').value = '';
    document.getElementById('file-name').textContent = '';
    document.getElementById('apk-preview').classList.add('hidden');
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
    const categoryId = document.getElementById('upload-category').value;

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
    if (categoryId && categoryId !== '0') {
        formData.append('category_id', categoryId);
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

async function loadCodes() {
    try {
        const codes = await api('/my/codes');
        const list = document.getElementById('code-list');
        const empty = document.getElementById('codes-empty-state');

        if (codes.length === 0) {
            list.innerHTML = '';
            empty.style.display = 'block';
            return;
        }

        empty.style.display = 'none';
        list.innerHTML = codes.map(code => `
            <div class="code-card">
                <div class="code-card-header">
                    <div class="code-display">${code.code}</div>
                    <button class="code-delete-btn" onclick="deleteCodeById(${code.id})">删除</button>
                </div>
                <div style="font-size:12px;color:#999;margin-bottom:8px">创建时间: ${code.created_at}</div>
                <div class="app-list">
                    ${code.apps.map(app => `
                        <div class="app-item">
                            <span class="app-dot"></span>
                            <span>${escapeHtml(app.name)}</span>
                            ${app.category_name ? `<span style="color:#999;font-size:11px">(${escapeHtml(app.category_name)})</span>` : ''}
                        </div>
                    `).join('')}
                </div>
            </div>
        `).join('');
    } catch (err) {
        showToast('加载口令失败', 'error');
    }
}

async function deleteCodeById(codeId) {
    if (!confirm('确定删除此口令?')) return;
    try {
        await api(`/codes/${codeId}`, { method: 'DELETE' });
        showToast('口令已删除', 'success');
        loadCodes();
        loadApps();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

document.getElementById('btn-create-multi-code').addEventListener('click', () => {
    if (apps.length === 0) {
        showToast('请先上传应用', 'error');
        return;
    }
    selectedAppIds = [];
    const list = document.getElementById('multi-code-app-list');
    list.innerHTML = apps.map(app => {
        const iconHtml = app.icon_url ?
            `<img src="${app.icon_url}" alt="${escapeHtml(app.name)}">` :
            escapeHtml(app.name.charAt(0));
        return `
            <div class="select-item" onclick="toggleSelectApp(${app.id}, this)">
                <div class="select-checkbox"></div>
                <div class="select-item-icon">${iconHtml}</div>
                <div class="select-item-info">
                    <div class="select-item-name">${escapeHtml(app.name)}</div>
                    <div class="select-item-desc">${escapeHtml(app.package_name)}</div>
                </div>
            </div>
        `;
    }).join('');
    document.getElementById('multi-code-count').textContent = '0';
    document.getElementById('multi-code-modal').classList.remove('hidden');
});

function toggleSelectApp(appId, el) {
    const idx = selectedAppIds.indexOf(appId);
    if (idx > -1) {
        selectedAppIds.splice(idx, 1);
        el.classList.remove('selected');
    } else if (selectedAppIds.length < 10) {
        selectedAppIds.push(appId);
        el.classList.add('selected');
    } else {
        showToast('最多选择10个应用', 'error');
    }
    document.getElementById('multi-code-count').textContent = selectedAppIds.length;
}

document.getElementById('btn-create-multi-confirm').addEventListener('click', async () => {
    if (selectedAppIds.length === 0) {
        showToast('请选择应用', 'error');
        return;
    }

    try {
        const res = await api('/codes/create-multi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ app_ids: selectedAppIds })
        });
        showToast(`口令 ${res.code} 创建成功，包含${selectedAppIds.length}个应用`, 'success');
        closeModal('multi-code-modal');
        loadCodes();
        loadApps();
    } catch (err) {
        showToast(err.message, 'error');
    }
});

document.getElementById('btn-merge-codes').addEventListener('click', async () => {
    try {
        const codes = await api('/my/codes');
        if (codes.length < 2) {
            showToast('至少需要2个口令才能合并', 'error');
            return;
        }

        selectedCodeIds = [];
        const list = document.getElementById('merge-code-list');
        list.innerHTML = codes.map(code => `
            <div class="select-item" onclick="toggleSelectCode(${code.id}, this)">
                <div class="select-checkbox"></div>
                <div class="select-item-info">
                    <div class="select-item-name">口令: ${code.code}</div>
                    <div class="select-item-desc">包含${code.apps.length}个应用</div>
                </div>
            </div>
        `).join('');
        document.getElementById('merge-count').textContent = '0';
        document.getElementById('merge-modal').classList.remove('hidden');
    } catch (err) {
        showToast('加载口令失败', 'error');
    }
});

function toggleSelectCode(codeId, el) {
    const idx = selectedCodeIds.indexOf(codeId);
    if (idx > -1) {
        selectedCodeIds.splice(idx, 1);
        el.classList.remove('selected');
    } else {
        selectedCodeIds.push(codeId);
        el.classList.add('selected');
    }
    document.getElementById('merge-count').textContent = selectedCodeIds.length;
}

document.getElementById('btn-merge-confirm').addEventListener('click', async () => {
    if (selectedCodeIds.length < 2) {
        showToast('至少选择2个口令', 'error');
        return;
    }

    try {
        const res = await api('/codes/merge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code_ids: selectedCodeIds })
        });
        showToast(`合并成功，新口令: ${res.code}`, 'success');
        closeModal('merge-modal');
        loadCodes();
        loadApps();
    } catch (err) {
        showToast(err.message, 'error');
    }
});

document.getElementById('btn-add-category').addEventListener('click', () => {
    document.getElementById('cat-name').value = '';
    document.getElementById('cat-color').value = '#636E72';
    document.getElementById('add-category-modal').classList.remove('hidden');
});

document.getElementById('btn-add-category-confirm').addEventListener('click', async () => {
    const name = document.getElementById('cat-name').value.trim();
    const color = document.getElementById('cat-color').value;

    if (!name) {
        showToast('分类名称不能为空', 'error');
        return;
    }

    try {
        await api('/categories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, color })
        });
        showToast('分类添加成功', 'success');
        closeModal('add-category-modal');
        loadCategories();
        loadAdminCategories();
    } catch (err) {
        showToast(err.message, 'error');
    }
});

async function loadAdminCategories() {
    try {
        const cats = await api('/categories');
        const grid = document.getElementById('category-grid');
        grid.innerHTML = cats.map(c => `
            <div class="category-card">
                <div class="category-color" style="background:${c.color}"></div>
                <div class="category-name">${escapeHtml(c.name)}</div>
                <button class="action-btn delete" onclick="deleteCategory(${c.id})">删除</button>
            </div>
        `).join('');
    } catch {}
}

async function deleteCategory(catId) {
    if (!confirm('确定删除此分类?')) return;
    try {
        await api(`/categories/${catId}`, { method: 'DELETE' });
        showToast('分类已删除', 'success');
        loadCategories();
        loadAdminCategories();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function loadAdminUsers() {
    try {
        const users = await api('/admin/users');
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
        const codes = await api('/admin/invite-codes');
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

let adminUsers = [];
let selectedPremiumAppIds = [];
let currentPremiumCodeId = null;
let adminChangePwdUserId = null;

document.getElementById('btn-change-pwd').addEventListener('click', () => {
    document.getElementById('old-password').value = '';
    document.getElementById('new-password').value = '';
    document.getElementById('confirm-password').value = '';
    document.getElementById('change-pwd-modal').classList.remove('hidden');
});

document.getElementById('btn-change-pwd-confirm').addEventListener('click', async () => {
    const oldPwd = document.getElementById('old-password').value;
    const newPwd = document.getElementById('new-password').value;
    const confirmPwd = document.getElementById('confirm-password').value;

    if (!oldPwd || !newPwd || !confirmPwd) {
        showToast('请填写所有密码字段', 'error');
        return;
    }
    if (newPwd.length < 6) {
        showToast('新密码至少6个字符', 'error');
        return;
    }
    if (newPwd !== confirmPwd) {
        showToast('两次输入的新密码不一致', 'error');
        return;
    }

    try {
        await api('/auth/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_password: oldPwd, new_password: newPwd })
        });
        showToast('密码修改成功', 'success');
        closeModal('change-pwd-modal');
    } catch (err) {
        showToast(err.message, 'error');
    }
});

function openAdminChangePwd(userId, username) {
    adminChangePwdUserId = userId;
    document.getElementById('admin-pwd-username').value = username;
    document.getElementById('admin-new-password').value = '';
    document.getElementById('admin-change-pwd-modal').classList.remove('hidden');
}

document.getElementById('btn-admin-change-pwd-confirm').addEventListener('click', async () => {
    const newPwd = document.getElementById('admin-new-password').value;

    if (!newPwd || newPwd.length < 6) {
        showToast('新密码至少6个字符', 'error');
        return;
    }

    try {
        await api('/admin/users/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: adminChangePwdUserId, new_password: newPwd })
        });
        showToast('密码修改成功', 'success');
        closeModal('admin-change-pwd-modal');
    } catch (err) {
        showToast(err.message, 'error');
    }
});

document.querySelectorAll('.admin-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const t = tab.dataset.adminTab;
        document.querySelectorAll('.admin-tab').forEach(tt => tt.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('admin-users').classList.toggle('hidden', t !== 'users');
        document.getElementById('admin-invites').classList.toggle('hidden', t !== 'invites');
        document.getElementById('admin-premium').classList.toggle('hidden', t !== 'premium');
        document.getElementById('admin-categories').classList.toggle('hidden', t !== 'categories');
        document.getElementById('admin-stats').classList.toggle('hidden', t !== 'stats');
        if (t === 'categories') {
            loadAdminCategories();
        }
        if (t === 'premium') {
            loadPremiumCodes();
        }
        if (t === 'users') {
            loadAdminUsers();
        }
    });
});

async function loadAdminUsers() {
    try {
        const users = await api('/admin/users');
        adminUsers = users;
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
                        <button class="action-btn edit" onclick="openAdminChangePwd(${u.id}, '${escapeHtml(u.username)}')">
                            改密码
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

async function loadPremiumCodes() {
    try {
        const codes = await api('/admin/premium-codes');
        const tbody = document.getElementById('premium-tbody');
        
        if (codes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#999;padding:40px">暂无豹子号</td></tr>';
            return;
        }

        tbody.innerHTML = codes.map(c => `
            <tr>
                <td>${c.id}</td>
                <td><code style="background:#f0f4ff;padding:2px 8px;border-radius:4px;color:#667eea;font-weight:600">${c.code}</code></td>
                <td>${c.app_ids ? c.app_ids.length : 0} 个</td>
                <td>${c.note ? escapeHtml(c.note) : '-'}</td>
                <td>
                    <span class="status-badge ${c.is_used ? 'status-used' : 'status-unused'}">
                        ${c.is_used ? '已分配' : '未分配'}
                    </span>
                </td>
                <td>${c.assigned_user_id ? '用户ID: ' + c.assigned_user_id : '-'}</td>
                <td>${c.created_at}</td>
                <td>
                    ${!c.is_used && c.is_active ? `
                        <button class="action-btn edit" onclick="openAssignPremium(${c.id}, '${c.code}')">分配</button>
                        <button class="action-btn delete" onclick="deletePremiumCode(${c.id})">删除</button>
                    ` : '-'}
                </td>
            </tr>
        `).join('');
    } catch (err) {
        showToast('加载豹子号失败', 'error');
    }
}

document.getElementById('btn-add-premium').addEventListener('click', () => {
    if (apps.length === 0) {
        showToast('请先上传应用', 'error');
        return;
    }
    selectedPremiumAppIds = [];
    document.getElementById('premium-code').value = '';
    document.getElementById('premium-note').value = '';
    
    const list = document.getElementById('premium-app-list');
    list.innerHTML = apps.map(app => {
        const iconHtml = app.icon_url ?
            `<img src="${app.icon_url}" alt="${escapeHtml(app.name)}">` :
            escapeHtml(app.name.charAt(0));
        return `
            <div class="select-item" onclick="toggleSelectPremiumApp(${app.id}, this)">
                <div class="select-checkbox"></div>
                <div class="select-item-icon">${iconHtml}</div>
                <div class="select-item-info">
                    <div class="select-item-name">${escapeHtml(app.name)}</div>
                    <div class="select-item-desc">${escapeHtml(app.package_name)}</div>
                </div>
            </div>
        `;
    }).join('');
    document.getElementById('premium-app-count').textContent = '0';
    document.getElementById('add-premium-modal').classList.remove('hidden');
});

function toggleSelectPremiumApp(appId, el) {
    const idx = selectedPremiumAppIds.indexOf(appId);
    if (idx > -1) {
        selectedPremiumAppIds.splice(idx, 1);
        el.classList.remove('selected');
    } else if (selectedPremiumAppIds.length < 10) {
        selectedPremiumAppIds.push(appId);
        el.classList.add('selected');
    } else {
        showToast('最多选择10个应用', 'error');
    }
    document.getElementById('premium-app-count').textContent = selectedPremiumAppIds.length;
}

document.getElementById('btn-add-premium-confirm').addEventListener('click', async () => {
    const code = document.getElementById('premium-code').value.trim().toUpperCase();
    const note = document.getElementById('premium-note').value.trim();

    if (!code) {
        showToast('请输入豹子号口令', 'error');
        return;
    }
    if (code.length < 4) {
        showToast('口令至少4个字符', 'error');
        return;
    }
    if (selectedPremiumAppIds.length === 0) {
        showToast('请选择应用', 'error');
        return;
    }

    try {
        await api('/admin/premium-codes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, app_ids: selectedPremiumAppIds, note })
        });
        showToast('豹子号添加成功', 'success');
        closeModal('add-premium-modal');
        loadPremiumCodes();
    } catch (err) {
        showToast(err.message, 'error');
    }
});

function openAssignPremium(codeId, codeStr) {
    currentPremiumCodeId = codeId;
    document.getElementById('assign-premium-code').value = codeStr;
    
    const select = document.getElementById('assign-user-select');
    select.innerHTML = '<option value="">请选择用户</option>' +
        adminUsers.filter(u => !u.is_super_admin).map(u => 
            `<option value="${u.id}">${escapeHtml(u.username)}</option>`
        ).join('');
    
    document.getElementById('assign-premium-modal').classList.remove('hidden');
}

document.getElementById('btn-assign-premium-confirm').addEventListener('click', async () => {
    const userId = parseInt(document.getElementById('assign-user-select').value);
    
    if (!userId) {
        showToast('请选择用户', 'error');
        return;
    }

    try {
        const res = await api('/admin/premium-codes/assign', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ premium_code_id: currentPremiumCodeId, user_id: userId })
        });
        showToast(`分配成功，口令 ${res.code} 已分配给 ${res.username}`, 'success');
        closeModal('assign-premium-modal');
        loadPremiumCodes();
    } catch (err) {
        showToast(err.message, 'error');
    }
});

async function deletePremiumCode(codeId) {
    if (!confirm('确定删除此豹子号?')) return;
    try {
        await api(`/admin/premium-codes/${codeId}`, { method: 'DELETE' });
        showToast('删除成功', 'success');
        loadPremiumCodes();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

if (token) {
    enterApp();
} else {
    showPage('login-page');
}

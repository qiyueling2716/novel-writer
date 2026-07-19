/**
 * AI 小说写作助手 — 前端 SPA
 * 支持桌面端和手机端响应式布局
 */

// ==================== Lucide Icon Rendering ====================
/**
 * 渲染所有 <i data-lucide="..."> 为 SVG 图标。
 * 在每次 innerHTML 变更后调用，或依赖 MutationObserver 自动触发。
 */
let _iconRenderTimer = null;
function renderIcons() {
    if (typeof lucide !== 'undefined' && lucide.createIcons) {
        try { lucide.createIcons(); } catch (e) { /* ignore */ }
    }
}

/**
 * 创建图标 HTML 字符串（用于模板字符串中）
 * @param {string} name - Lucide 图标名
 * @param {string} cls - 额外 class
 * @returns {string} HTML 字符串
 */
function ic(name, cls = 'btn-icon') {
    return `<i data-lucide="${name}" class="${cls}"></i>`;
}

// MutationObserver: 监听 DOM 变化，debounce 渲染图标
const _iconObserver = new MutationObserver(function() {
    if (_iconRenderTimer) clearTimeout(_iconRenderTimer);
    _iconRenderTimer = setTimeout(renderIcons, 50);
});
// 在 DOMContentLoaded 后启动观察
document.addEventListener('DOMContentLoaded', function() {
    _iconObserver.observe(document.getElementById('mainArea') || document.body, {
        childList: true, subtree: true,
    });
    renderIcons(); // 首次渲染
});

// ==================== Auth ====================
let authToken = localStorage.getItem('auth_token') || '';
let isAuthenticated = false;

async function checkAuth() {
    try {
        const { is_setup } = await API.get('/api/auth/status');
        if (!is_setup) {
            showSetupPage();
            return false;
        }
        if (authToken) {
            const valid = await API.post('/api/auth/verify', { token: authToken });
            if (valid.valid) {
                showAppChrome(true);
                return true;
            }
        }
        showLoginPage();
        return false;
    } catch (e) {
        showLoginPage();
        return false;
    }
}

/** 显示/隐藏侧边栏和菜单按钮（仅登录后才显示） */
function showAppChrome(show) {
    isAuthenticated = show;
    const sidebar = document.getElementById('sidebar');
    const menuBtn = document.getElementById('menuBtn');
    const isMobile = window.innerWidth <= 768;
    if (show) {
        if (sidebar) {
            if (isMobile) {
                sidebar.classList.add('visible-mobile');
                sidebar.classList.remove('visible-desktop', 'open');
            } else {
                sidebar.classList.add('visible-desktop');
                sidebar.classList.remove('visible-mobile', 'open');
            }
        }
        if (menuBtn) {
            if (isMobile) {
                menuBtn.classList.add('visible');
            } else {
                menuBtn.classList.remove('visible', 'active');
            }
        }
    } else {
        if (sidebar) { sidebar.classList.remove('visible-desktop', 'visible-mobile', 'open'); }
        if (menuBtn) menuBtn.classList.remove('visible', 'active');
        const overlay = document.getElementById('sidebarOverlay');
        if (overlay) overlay.classList.remove('show');
    }
}

// 窗口尺寸变化时重新调整 chrome 显隐
window.addEventListener('resize', function() {
    if (!isAuthenticated) return;
    const isMobile = window.innerWidth <= 768;
    const menuBtn = document.getElementById('menuBtn');
    const sidebar = document.getElementById('sidebar');
    if (menuBtn) {
        if (isMobile) menuBtn.classList.add('visible');
        else menuBtn.classList.remove('visible', 'active');
    }
    if (sidebar) {
        if (isMobile) {
            sidebar.classList.add('visible-mobile');
            sidebar.classList.remove('visible-desktop', 'open');
        } else {
            sidebar.classList.add('visible-desktop');
            sidebar.classList.remove('visible-mobile', 'open');
        }
        const overlay = document.getElementById('sidebarOverlay');
        if (overlay) overlay.classList.remove('show');
    }
});

function showSetupPage() {
    showAppChrome(false);
    const main = document.getElementById('mainArea');
    main.className = 'main-area';
    main.innerHTML = `
        <div class="auth-page">
            <div class="auth-card">
                <h2 style="margin-bottom:8px">${ic('book-open', 'icon-md')} AI 小说写作助手</h2>
                <p style="color:var(--text-secondary);margin-bottom:24px">首次使用，请设置访问密码</p>
                <div class="form-group">
                    <label>设置密码</label>
                    <input type="password" id="setupPassword" placeholder="至少6位">
                </div>
                <div class="form-group">
                    <label>确认密码</label>
                    <input type="password" id="setupPasswordConfirm" placeholder="再次输入">
                </div>
                <button class="btn btn-primary" onclick="doSetup()" style="width:100%">设置密码</button>
            </div>
        </div>`;
}

function showLoginPage() {
    showAppChrome(false);
    const main = document.getElementById('mainArea');
    main.className = 'main-area';
    main.innerHTML = `
        <div class="auth-page">
            <div class="auth-card">
                <h2 style="margin-bottom:8px">${ic('book-open', 'icon-md')} AI 小说写作助手</h2>
                <p style="color:var(--text-secondary);margin-bottom:24px">请输入密码登录</p>
                <div class="form-group">
                    <label>密码</label>
                    <input type="password" id="loginPassword" placeholder="输入密码" onkeydown="if(event.key==='Enter')doLogin()">
                </div>
                <button class="btn btn-primary" onclick="doLogin()" style="width:100%">登录</button>
            </div>
        </div>`;
}

function doLogout() {
    authToken = '';
    isAuthenticated = false;
    localStorage.removeItem('auth_token');
    stopActiveTaskPolling();
    showLoginPage();
    showToast('已退出登录', 'info');
}

async function doSetup() {
    const pwd = document.getElementById('setupPassword').value;
    const confirm = document.getElementById('setupPasswordConfirm').value;
    if (pwd.length < 6) { showToast('密码至少6位', 'error'); return; }
    if (pwd !== confirm) { showToast('两次密码不一致', 'error'); return; }
    try {
        const data = await API.post('/api/auth/setup', { password: pwd });
        authToken = data.token;
        localStorage.setItem('auth_token', authToken);
        showAppChrome(true);
        showToast('密码设置成功', 'success');
        startActiveTaskPolling();
        navigate('novels');
    } catch (e) {
        showToast('设置失败: ' + e.message, 'error');
    }
}

async function doLogin() {
    const pwd = document.getElementById('loginPassword').value;
    if (!pwd) { showToast('请输入密码', 'error'); return; }
    try {
        const data = await API.post('/api/auth/login', { password: pwd });
        authToken = data.token;
        localStorage.setItem('auth_token', authToken);
        showAppChrome(true);
        showToast('登录成功', 'success');
        startActiveTaskPolling();
        navigate('novels');
    } catch (e) {
        showToast('密码错误', 'error');
    }
}

// ==================== API 工具 ====================
const API = {
    _headers(extra = {}) {
        const h = { ...extra };
        if (extra['Content-Type'] || extra.body instanceof FormData) {
            // don't set Content-Type for FormData (let browser set boundary)
        } else if (!extra['Content-Type']) {
            h['Content-Type'] = 'application/json';
        }
        if (authToken) h['Authorization'] = 'Bearer ' + authToken;
        return h;
    },
    async get(url) {
        const r = await fetch(url, { headers: this._headers() });
        if (r.status === 401) { authToken = ''; localStorage.removeItem('auth_token'); showLoginPage(); throw new Error('请重新登录'); }
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        return r.json();
    },
    async post(url, data) {
        const isJson = typeof data === 'object' && !(data instanceof FormData);
        const r = await fetch(url, {
            method: 'POST',
            headers: this._headers(isJson ? {} : {}),
            body: isJson ? JSON.stringify(data) : data,
        });
        if (r.status === 401) { authToken = ''; localStorage.removeItem('auth_token'); showLoginPage(); throw new Error('请重新登录'); }
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        return r.json();
    },
    async put(url, data) {
        const r = await fetch(url, {
            method: 'PUT',
            headers: this._headers(),
            body: JSON.stringify(data),
        });
        if (r.status === 401) { authToken = ''; localStorage.removeItem('auth_token'); showLoginPage(); throw new Error('请重新登录'); }
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        return r.json();
    },
    async del(url) {
        const r = await fetch(url, { method: 'DELETE', headers: this._headers() });
        if (r.status === 401) { authToken = ''; localStorage.removeItem('auth_token'); showLoginPage(); throw new Error('请重新登录'); }
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        return r.json();
    },
    async upload(url, formData) {
        const r = await fetch(url, { method: 'POST', body: formData, headers: this._headers({ body: formData }) });
        if (r.status === 401) { authToken = ''; localStorage.removeItem('auth_token'); showLoginPage(); throw new Error('请重新登录'); }
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        return r.json();
    },
};

// ==================== Toast ====================
function showToast(msg, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => { toast.remove(); }, 3000);
}

// ==================== 统一 Modal 对话框 ====================
// 替代原生 confirm / alert / prompt，提供一致的 UI 风格

let _modalZIndex = 400;

/**
 * 显示统一风格的 Modal 对话框
 * @param {Object} opts
 *   - title: 标题
 *   - message: 消息内容（可以是 HTML 字符串）
 *   - icon: 'warning' | 'danger' | 'info' | 'success' | null
 *   - size: 'sm' | 'md' | 'lg'
 *   - buttons: [{text, type, value, onClick}]  type: 'primary'|'danger'|'default'
 *   - onClose: 关闭时回调（参数为按钮 value，点遮罩/ESC 为 null）
 *   - dismissible: 点击遮罩是否关闭（默认 true）
 * @returns {Promise} resolve 为按钮 value（或 null）
 */
function showModal(opts) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.style.zIndex = ++_modalZIndex;

        const sizeClass = opts.size === 'lg' ? ' modal-lg' : (opts.size === 'sm' ? ' modal-sm' : '');
        const box = document.createElement('div');
        box.className = 'modal-box' + sizeClass;

        // 图标映射
        const iconMap = {
            warning: { cls: 'modal-icon-warning', svg: 'alert-triangle' },
            danger: { cls: 'modal-icon-danger', svg: 'alert-circle' },
            info: { cls: 'modal-icon-info', svg: 'info' },
            success: { cls: 'modal-icon-success', svg: 'check-circle' },
        };
        const iconHtml = opts.icon && iconMap[opts.icon]
            ? `<div class="modal-icon ${iconMap[opts.icon].cls}">${ic(iconMap[opts.icon].svg, 'icon-md')}</div>`
            : '';

        // 按钮
        const buttons = opts.buttons || [{ text: '确定', type: 'primary', value: true }];
        const footerHtml = buttons.map((b, i) => {
            const cls = b.type === 'danger' ? 'btn btn-danger' : (b.type === 'primary' ? 'btn btn-primary' : 'btn');
            return `<button class="${cls}" data-idx="${i}">${escHtml(b.text)}</button>`;
        }).join('');

        box.innerHTML = `
            <div class="modal-header">
                ${iconHtml}
                <h3>${escHtml(opts.title || '提示')}</h3>
            </div>
            <div class="modal-body">${opts.message || ''}</div>
            <div class="modal-footer">${footerHtml}</div>
        `;
        overlay.appendChild(box);
        document.body.appendChild(overlay);

        const close = (value) => {
            overlay.remove();
            _modalZIndex--;
            document.removeEventListener('keydown', onKey);
            if (opts.onClose) opts.onClose(value);
            resolve(value);
        };

        // 收集 Modal 内所有表单元素的值（在 close 移除 DOM 之前调用）
        // 返回 { fieldName: value }，fieldName 来自元素的 name 属性或 id
        const collectForm = () => {
            const data = {};
            box.querySelectorAll('input, textarea, select').forEach(el => {
                const key = el.name || el.id;
                if (!key) return;
                if (el.type === 'checkbox') data[key] = el.checked;
                else if (el.type === 'radio') { if (el.checked) data[key] = el.value; }
                else data[key] = el.value;
            });
            return data;
        };

        // 按钮事件
        box.querySelectorAll('.modal-footer button').forEach(btn => {
            btn.onclick = () => {
                const idx = parseInt(btn.dataset.idx);
                const b = buttons[idx];
                // 先收集表单数据（DOM 还在），再调用 onClick 或 close
                if (b.onClick) b.onClick(close, collectForm());
                else close(b.value);
            };
        });

        // ESC 键
        const onKey = (e) => {
            if (e.key === 'Escape') {
                if (opts.dismissible !== false) close(null);
            }
        };
        document.addEventListener('keydown', onKey);

        // 点击遮罩关闭
        if (opts.dismissible !== false) {
            overlay.onclick = (e) => { if (e.target === overlay) close(null); };
        }
    });
}

/** 确认对话框（替代 confirm）
 * @returns Promise<boolean> true=确认, false=取消
 */
async function confirmDialog(message, opts = {}) {
    const result = await showModal({
        title: opts.title || '确认操作',
        message: `<p>${escHtml(message)}</p>`,
        icon: opts.icon || 'warning',
        size: opts.size || 'sm',
        buttons: [
            { text: opts.cancelText || '取消', type: 'default', value: false },
            { text: opts.confirmText || '确定', type: opts.danger ? 'danger' : 'primary', value: true },
        ],
        dismissible: opts.dismissible,
    });
    return result === true;
}

/** 提示对话框（替代 alert） */
async function alertDialog(message, opts = {}) {
    return showModal({
        title: opts.title || '提示',
        message: `<p>${escHtml(message)}</p>`,
        icon: opts.icon || 'info',
        size: opts.size || 'sm',
        buttons: [
            { text: '知道了', type: 'primary', value: true },
        ],
    });
}

/** 输入对话框（替代 prompt）
 * @returns Promise<string|null> 输入值或 null（取消）
 */
async function promptDialog(message, defaultValue = '', opts = {}) {
    const inputId = '_modal_input_' + Date.now();
    const placeholder = opts.placeholder ? ` placeholder="${escHtml(opts.placeholder)}"` : '';
    // 使用 onClick 回调在 Modal 关闭前收集输入值
    let inputValue = null;
    await showModal({
        title: opts.title || '输入',
        message: `
            <p>${escHtml(message)}</p>
            <div class="form-group" style="margin-bottom:0">
                <input type="${opts.type || 'text'}" id="${inputId}" name="value" value="${escHtml(defaultValue)}"${placeholder} style="width:100%">
            </div>
        `,
        icon: opts.icon || 'info',
        size: opts.size || 'md',
        buttons: [
            { text: '取消', type: 'default', value: null },
            {
                text: opts.confirmText || '确定',
                type: 'primary',
                value: null,
                onClick: (close, form) => { inputValue = form.value || ''; close('__submit__'); },
            },
        ],
    });
    // inputValue 在点击"确定"时被设置；点取消/关闭时为 null
    return inputValue;
}

// ==================== 待确认设定变更对话框 ====================
const TOOL_CHANGE_LABELS = {
    'update_outline': '大纲修改',
    'update_world_building': '世界观修改',
    'update_character': '人物档案修改',
};

// 生成简易行级 diff 显示（旧/新内容并排对比）
function renderDiffPreview(oldText, newText) {
    const oldLines = (oldText || '').split('\n');
    const newLines = (newText || '').split('\n');
    const maxLen = Math.max(oldLines.length, newLines.length, 1);
    let html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:0.82rem;font-family:var(--font-mono,monospace)">';
    html += '<div style="padding:6px;background:var(--bg-card);border-radius:4px;border:1px solid var(--border)"><div style="font-weight:600;margin-bottom:4px;color:var(--text-secondary)">修改前</div>';
    for (const line of oldLines.slice(0, 50)) {
        html += `<div style="padding:1px 4px;white-space:pre-wrap;word-break:break-all">${escHtml(line) || '&nbsp;'}</div>`;
    }
    if (oldLines.length > 50) html += `<div style="color:var(--text-secondary)">...（共 ${oldLines.length} 行）</div>`;
    html += '</div>';
    html += '<div style="padding:6px;background:var(--bg-card);border-radius:4px;border:1px solid var(--accent)"><div style="font-weight:600;margin-bottom:4px;color:var(--accent)">修改后</div>';
    for (const line of newLines.slice(0, 50)) {
        html += `<div style="padding:1px 4px;white-space:pre-wrap;word-break:break-all">${escHtml(line) || '&nbsp;'}</div>`;
    }
    if (newLines.length > 50) html += `<div style="color:var(--text-secondary)">...（共 ${newLines.length} 行）</div>`;
    html += '</div></div>';
    return html;
}

async function showPendingChangesDialog(changes, count) {
    if (!changes || !changes.length) return;
    // 清理全局缓存
    window._pendingChangesData = null;
    window._batchPendingChanges = null;

    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop';
    backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;padding:16px';

    const modal = document.createElement('div');
    modal.style.cssText = 'background:var(--bg-main);border-radius:12px;max-width:1100px;width:100%;max-height:90vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,0.3)';

    let listHtml = '';
    changes.forEach((c, idx) => {
        const label = TOOL_CHANGE_LABELS[c.tool_name] || c.tool_name;
        listHtml += `
            <div class="pending-change-item" data-id="${c.id}" data-idx="${idx}" style="border:1px solid var(--border);border-radius:8px;margin-bottom:12px;overflow:hidden">
                <div style="padding:10px 12px;background:var(--bg-card);display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                        <span style="background:var(--accent);color:white;padding:2px 8px;border-radius:4px;font-size:0.78rem;font-weight:600">${label}</span>
                        <span style="font-weight:600">${escHtml(c.target_name)}</span>
                        ${c.chapter_number ? `<span style="color:var(--text-secondary);font-size:0.82rem">第 ${c.chapter_number} 章</span>` : ''}
                    </div>
                    <div style="display:flex;gap:6px">
                        <button class="pc-accept" data-id="${c.id}" style="padding:5px 12px;background:var(--accent);color:white;border:none;border-radius:4px;cursor:pointer;font-size:0.85rem">接受</button>
                        <button class="pc-reject" data-id="${c.id}" style="padding:5px 12px;background:var(--bg-card);color:var(--text);border:1px solid var(--border);border-radius:4px;cursor:pointer;font-size:0.85rem">拒绝</button>
                    </div>
                </div>
                ${c.change_summary ? `<div style="padding:6px 12px;background:#fff3cd;color:#856404;font-size:0.82rem">${ic('info', 'icon-sm')} ${escHtml(c.change_summary)}</div>` : ''}
                <div class="pc-diff" style="padding:10px 12px;max-height:280px;overflow:auto">
                    ${renderDiffPreview(c.old_content, c.new_content)}
                </div>
            </div>
        `;
    });

    modal.innerHTML = `
        <div style="padding:16px 20px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
            <div>
                <div style="font-size:1.1rem;font-weight:700">${ic('edit', 'icon-sm')} 待确认的设定变更</div>
                <div style="color:var(--text-secondary);font-size:0.85rem;margin-top:2px">AI 在生成章节时提议修改以下设定，请逐一确认。接受后修改才会生效。</div>
            </div>
            <button id="pcCloseBtn" style="background:none;border:none;font-size:1.5rem;cursor:pointer;color:var(--text-secondary)">&times;</button>
        </div>
        <div id="pcList" style="padding:16px 20px;overflow:auto;flex:1">
            ${listHtml}
        </div>
        <div style="padding:12px 20px;border-top:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
            <div style="color:var(--text-secondary);font-size:0.85rem">
                剩余 <span id="pcRemaining" style="font-weight:700;color:var(--text)">${changes.length}</span> 条待处理
            </div>
            <div style="display:flex;gap:8px">
                <button id="pcAcceptAllBtn" style="padding:8px 16px;background:var(--accent);color:white;border:none;border-radius:6px;cursor:pointer">全部接受</button>
                <button id="pcRejectAllBtn" style="padding:8px 16px;background:var(--bg-card);color:var(--text);border:1px solid var(--border);border-radius:6px;cursor:pointer">全部拒绝</button>
                <button id="pcLaterBtn" style="padding:8px 16px;background:none;color:var(--text-secondary);border:none;cursor:pointer">稍后处理</button>
            </div>
        </div>
    `;
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);

    const close = () => backdrop.remove();
    modal.querySelector('#pcCloseBtn').onclick = close;
    modal.querySelector('#pcLaterBtn').onclick = close;
    backdrop.addEventListener('click', e => { if (e.target === backdrop) close(); });

    const updateRemaining = () => {
        const remaining = modal.querySelectorAll('.pending-change-item').length;
        modal.querySelector('#pcRemaining').textContent = remaining;
        if (remaining === 0) {
            setTimeout(() => { close(); showToast('所有变更已处理', 'success'); }, 600);
        }
    };

    const removeItem = (item) => {
        item.style.transition = 'opacity 0.3s, transform 0.3s';
        item.style.opacity = '0';
        item.style.transform = 'translateX(20px)';
        setTimeout(() => { item.remove(); updateRemaining(); }, 300);
    };

    // 单个接受
    modal.querySelectorAll('.pc-accept').forEach(btn => {
        btn.onclick = async () => {
            const id = btn.dataset.id;
            const item = btn.closest('.pending-change-item');
            btn.disabled = true;
            btn.textContent = '处理中...';
            try {
                await API.post(`/api/pending-changes/${id}/accept`, {});
                showToast('变更已接受并应用', 'success');
                removeItem(item);
            } catch (e) {
                showToast('接受失败: ' + e.message, 'error');
                btn.disabled = false;
                btn.textContent = '接受';
            }
        };
    });

    // 单个拒绝
    modal.querySelectorAll('.pc-reject').forEach(btn => {
        btn.onclick = async () => {
            const id = btn.dataset.id;
            const item = btn.closest('.pending-change-item');
            btn.disabled = true;
            try {
                await API.post(`/api/pending-changes/${id}/reject`, {});
                showToast('已拒绝', 'info');
                removeItem(item);
            } catch (e) {
                showToast('操作失败: ' + e.message, 'error');
                btn.disabled = false;
            }
        };
    });

    // 全部接受
    modal.querySelector('#pcAcceptAllBtn').onclick = async () => {
        const btn = modal.querySelector('#pcAcceptAllBtn');
        btn.disabled = true;
        btn.textContent = '处理中...';
        const items = Array.from(modal.querySelectorAll('.pending-change-item'));
        for (const item of items) {
            const id = item.dataset.id;
            try {
                await API.post(`/api/pending-changes/${id}/accept`, {});
                removeItem(item);
                await new Promise(r => setTimeout(r, 100));
            } catch (e) { /* 继续 */ }
        }
        btn.disabled = false;
        btn.textContent = '全部接受';
    };

    // 全部拒绝
    modal.querySelector('#pcRejectAllBtn').onclick = async () => {
        const btn = modal.querySelector('#pcRejectAllBtn');
        btn.disabled = true;
        btn.textContent = '处理中...';
        const items = Array.from(modal.querySelectorAll('.pending-change-item'));
        for (const item of items) {
            const id = item.dataset.id;
            try {
                await API.post(`/api/pending-changes/${id}/reject`, {});
                removeItem(item);
                await new Promise(r => setTimeout(r, 100));
            } catch (e) { /* 继续 */ }
        }
        btn.disabled = false;
        btn.textContent = '全部拒绝';
    };
}

// ==================== Dropdown Panel ====================
function closeAllDropdowns() {
    document.querySelectorAll('.dropdown-panel').forEach(el => el.remove());
    document.querySelectorAll('.dropdown-backdrop').forEach(el => el.remove());
    _activeDropdownBtn = null;
}

let _activeDropdownBtn = null;

function toggleDropdown(btnEl, contentHtml, alignLeft) {
    // 同一按钮再次点击 = 关闭
    if (_activeDropdownBtn === btnEl) {
        closeAllDropdowns();
        return;
    }
    closeAllDropdowns();
    _activeDropdownBtn = btnEl;
    const panel = document.createElement('div');
    panel.className = 'dropdown-panel' + (alignLeft ? ' left' : '');
    panel.innerHTML = contentHtml;
    panel.addEventListener('click', e => e.stopPropagation());

    const isMobile = window.innerWidth <= 768;
    if (isMobile) {
        const backdrop = document.createElement('div');
        backdrop.className = 'dropdown-backdrop';
        backdrop.addEventListener('click', closeAllDropdowns);
        document.body.appendChild(backdrop);
        document.body.appendChild(panel);
    } else {
        // 桌面端：用 fixed 定位，避免影响布局流
        const rect = btnEl.getBoundingClientRect();
        panel.style.position = 'fixed';
        panel.style.top = (rect.bottom + 6) + 'px';
        if (alignLeft) {
            panel.style.left = rect.left + 'px';
            panel.style.right = 'auto';
        } else {
            // 默认右对齐按钮，向左展开
            panel.style.right = (window.innerWidth - rect.right) + 'px';
            panel.style.left = 'auto';
        }
        // 防止超出视口
        setTimeout(() => {
            const pRect = panel.getBoundingClientRect();
            if (pRect.left < 8) {
                panel.style.left = '8px';
                panel.style.right = 'auto';
            }
            if (pRect.right > window.innerWidth - 8) {
                panel.style.right = '8px';
                panel.style.left = 'auto';
            }
        }, 0);
        // 点击空白关闭
        const backdrop = document.createElement('div');
        backdrop.className = 'dropdown-backdrop';
        backdrop.style.position = 'fixed';
        backdrop.style.top = '0';
        backdrop.style.left = '0';
        backdrop.style.width = '100%';
        backdrop.style.height = '100%';
        backdrop.style.zIndex = '140';
        backdrop.addEventListener('click', closeAllDropdowns);
        document.body.appendChild(backdrop);
        document.body.appendChild(panel);
    }

    setTimeout(() => {
        const first = panel.querySelector('input, select');
        if (first) first.focus();
    }, 150);
}

document.addEventListener('click', function(e) {
    // 如果点击的是当前活动按钮本身，由按钮的 onclick 处理 toggle，不在这里关闭
    if (_activeDropdownBtn && e.target.closest('button') === _activeDropdownBtn.closest('button')) {
        return;
    }
    if (!e.target.closest('.dropdown-panel') && !e.target.closest('.dropdown-wrapper')) {
        closeAllDropdowns();
    }
});

// ==================== Navigation ====================
let currentPage = 'novels';
let currentNovelId = null;
let currentChapterId = null;
let currentNovel = null;  // 当前小说完整对象（在 renderNovelDetailPage 中赋值）
let navHistory = [];  // 导航历史栈

function toggleSidebar(forceState) {
    // 未认证时不允许打开侧边栏
    if (!isAuthenticated) return;
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const menuBtn = document.getElementById('menuBtn');
    if (!sidebar) return;
    if (forceState === false) {
        sidebar.classList.remove('open');
        if (overlay) overlay.classList.remove('show');
        if (menuBtn) menuBtn.classList.remove('active');
    } else if (forceState === true) {
        sidebar.classList.add('open');
        if (overlay) overlay.classList.add('show');
        if (menuBtn) menuBtn.classList.add('active');
    } else {
        const isOpen = sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('show', isOpen);
        if (menuBtn) menuBtn.classList.toggle('active', isOpen);
    }
}

// 点击侧边栏外空白处关闭侧边栏（移动端）
// 注意：必须排除 Modal 弹窗的点击，否则点击 Modal 会误触发侧边栏关闭
document.addEventListener('click', function(e) {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar || !sidebar.classList.contains('open')) return;
    // 如果点击的不是侧边栏本身，也不是菜单按钮，也不是 sidebar overlay
    if (!e.target.closest('#sidebar') && !e.target.closest('.menu-btn') && !e.target.closest('.sidebar-overlay')) {
        // 排除 Modal 弹窗的点击（modal-overlay 及其子元素）
        if (e.target.closest('.modal-overlay')) return;
        toggleSidebar(false);
    }
});

function navigate(page, data = {}) {
    // 记录导航历史（跳过重复页）
    if (currentPage !== page || data.novelId !== currentNovelId) {
        navHistory.push({ page: currentPage, novelId: currentNovelId, chapterId: currentChapterId });
        // 限制历史栈深度
        if (navHistory.length > 20) navHistory.shift();
    }
    currentPage = page;
    currentNovelId = data.novelId || currentNovelId;
    // 非 chapter-edit 页面时清空 currentChapterId，防止状态泄漏
    currentChapterId = data.chapterId !== undefined ? data.chapterId : null;
    // 同步到浏览器历史
    history.pushState({ page: currentPage, novelId: currentNovelId, chapterId: currentChapterId }, '', `#${currentPage}`);
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    const navItem = document.querySelector(`[data-page="${page}"]`);
    if (navItem) navItem.classList.add('active');
    // 移动端导航后自动关闭侧边栏
    toggleSidebar(false);
    closeAllDropdowns();
    // 清理编辑器临时状态（挂起的自动保存、沉浸模式）
    if (typeof _autoSaveTimer !== 'undefined' && _autoSaveTimer) { clearTimeout(_autoSaveTimer); _autoSaveTimer = null; }
    if (typeof _immersiveActive !== 'undefined' && _immersiveActive) toggleImmersive(false);
    // 滚动到页面顶部
    window.scrollTo(0, 0);
    renderPage();
}

function goBack() {
    if (navHistory.length > 0) {
        const prev = navHistory.pop();
        currentPage = prev.page;
        currentNovelId = prev.novelId;
        currentChapterId = prev.chapterId;
        document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
        const navItem = document.querySelector(`[data-page="${currentPage}"]`);
        if (navItem) navItem.classList.add('active');
        document.getElementById('sidebar').classList.remove('open');
        closeAllDropdowns();
        renderPage();
    } else {
        // 无历史记录时回主页
        navigate('novels');
    }
}

// 浏览器后退/前进按钮支持
window.addEventListener('popstate', function(e) {
    if (e.state && e.state.page) {
        navHistory = []; // 清空内部历史，以浏览器历史为准
        currentPage = e.state.page;
        currentNovelId = e.state.novelId || null;
        currentChapterId = e.state.chapterId || null;
        document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
        const navItem = document.querySelector(`[data-page="${currentPage}"]`);
        if (navItem) navItem.classList.add('active');
        closeAllDropdowns();
        renderPage();
    }
});

function renderPage() {
    const main = document.getElementById('mainArea');
    switch (currentPage) {
        case 'novels': renderNovelsPage(main); break;
        case 'novel-detail': renderNovelDetailPage(main); break;
        case 'chapter-edit': renderChapterEditPage(main); break;
        case 'chapter-generate': renderChapterGeneratePage(main); break;
        case 'batch-generate': renderBatchGeneratePage(main); break;
        case 'chapter-read': renderChapterReadPage(main); break;
        case 'duplicates': renderDuplicatesPage(main); break;
        case 'settings': renderSettingsPage(main); break;
        case 'backup': renderBackupPage(main); break;
        default: renderNovelsPage(main);
    }
}

// ==================== 活跃创作任务追踪 ====================
let _activeTaskPollTimer = null;
let _lastActiveTaskCount = 0;

async function pollActiveTasks() {
    const panel = document.getElementById('activeTasksPanel');
    if (!panel) return;
    try {
        const data = await API.get('/api/active-batch-tasks');
        const tasks = data.tasks || [];
        const runningTasks = tasks.filter(t => t.status === 'running');

        if (tasks.length === 0) {
            panel.style.display = 'none';
            panel.innerHTML = '';
            _lastActiveTaskCount = 0;
            return;
        }

        panel.style.display = 'block';
        let html = '<div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:6px;font-weight:600;letter-spacing:0.5px">创作任务</div>';

        tasks.forEach(t => {
            const isRunning = t.status === 'running';
            const pct = t.total > 0 ? Math.round(t.completed / t.total * 100) : 0;
            const statusColor = isRunning ? 'var(--accent)' : (t.status === 'completed' ? '#28a745' : '#dc3545');
            const statusText = isRunning ? '生成中' : (t.status === 'completed' ? '已完成' : (t.status === 'aborted' ? '已中止' : '失败'));
            // 运行中用纯 CSS spinner（不依赖 lucide，避免 innerHTML 重设导致动画重置"抽搐"）
            // 其他状态用静态图标
            const statusIconHtml = isRunning
                ? `<span class="css-spinner css-spinner-sm" style="color:${statusColor}"></span>`
                : `<i data-lucide="${t.status === 'completed' ? 'check-circle' : 'alert-circle'}" class="icon-sm"></i>`;

            html += `
                <div id="taskCard_${t.novel_id}" onclick="resumeBatchTask('${t.novel_id}')" style="cursor:pointer;padding:8px;background:var(--bg-card);border-radius:6px;margin-bottom:6px;border-left:3px solid ${statusColor};transition:transform 0.15s" onmouseover="this.style.transform='translateX(2px)'" onmouseout="this.style.transform='translateX(0)'">
                    <div style="display:flex;justify-content:space-between;align-items:center;gap:4px;margin-bottom:4px">
                        <div style="font-weight:600;font-size:0.85rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">${escHtml(t.novel_title || '未命名')}</div>
                        <div style="display:flex;align-items:center;gap:3px;font-size:0.72rem;color:${statusColor};white-space:nowrap">
                            ${statusIconHtml}${statusText}
                        </div>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;font-size:0.75rem;color:var(--text-secondary)">
                        <span>${t.completed}/${t.total} 章${isRunning && t.current_chapter_number ? ' · 第' + t.current_chapter_number + '章' : ''}</span>
                        <span>${pct}%</span>
                    </div>
                    <div style="height:3px;background:var(--border);border-radius:2px;margin-top:4px;overflow:hidden">
                        <div style="height:100%;width:${pct}%;background:${statusColor};transition:width 0.3s"></div>
                    </div>
                </div>
            `;
        });

        // 只在面板内容确实变化时才更新 DOM（减少不必要的 innerHTML 重设，避免动画抖动）
        const newFingerprint = tasks.map(t => `${t.novel_id}:${t.status}:${t.completed}:${t.current_chapter_number||0}`).join('|');
        if (newFingerprint !== panel.dataset.fingerprint) {
            panel.innerHTML = html;
            panel.dataset.fingerprint = newFingerprint;
            // 只渲染静态图标（spinner 是纯 CSS，不需要 lucide）
            renderIcons();
        } else {
            // 内容未变，仅更新进度条宽度（不重设 innerHTML，动画不中断）
            tasks.forEach(t => {
                const card = document.getElementById(`taskCard_${t.novel_id}`);
                if (!card) return;
                const bar = card.querySelector('div[style*="height:100%"]');
                if (bar) {
                    const pct = t.total > 0 ? Math.round(t.completed / t.total * 100) : 0;
                    bar.style.width = pct + '%';
                }
            });
        }

        // 如果有正在运行的任务，频繁轮询；否则低频轮询
        if (_activeTaskPollTimer) clearTimeout(_activeTaskPollTimer);
        const interval = runningTasks.length > 0 ? 2000 : 10000;
        _activeTaskPollTimer = setTimeout(pollActiveTasks, interval);

        // 任务数量变化时提示
        if (runningTasks.length > _lastActiveTaskCount) {
            showToast(`有 ${runningTasks.length} 个创作任务进行中`, 'info');
        }
        _lastActiveTaskCount = runningTasks.length;
    } catch (e) {
        // 失败时降低轮询频率；首次失败时在面板显示错误提示
        if (_activeTaskPollTimer) clearTimeout(_activeTaskPollTimer);
        _activeTaskPollTimer = setTimeout(pollActiveTasks, 30000);
        // 如果是 401（未登录），不显示错误面板
        if (e.message && e.message.includes('401')) return;
        // 其他错误：在面板显示错误提示（而不是空白）
        const panel = document.getElementById('activeTasksPanel');
        if (panel && !panel.dataset.errorShown) {
            panel.style.display = 'block';
            panel.innerHTML = `<div style="padding:8px;background:#fff3cd;border:1px solid #ffeaa7;border-radius:6px;font-size:0.75rem;color:#856404">
                ${ic('alert-circle', 'icon-sm')} 创作任务状态获取失败：${escHtml(e.message || '未知错误')}
            </div>`;
            renderIcons();
            panel.dataset.errorShown = '1';
            // 30 秒后清除错误标记，允许重试
            setTimeout(() => { delete panel.dataset.errorShown; }, 30000);
        }
    }
}

async function resumeBatchTask(novelId) {
    // 先查询该小说的任务状态
    try {
        const data = await API.get('/api/active-batch-tasks');
        const task = (data.tasks || []).find(t => t.novel_id === novelId);
        if (task && task.status === 'running') {
            // 任务正在运行，导航到创作页面并恢复 SSE 流
            showToast(`正在恢复「${task.novel_title}」的创作进度（${task.completed}/${task.total} 章）`, 'info');
            navigate('chapter-generate', { novelId, resumeBatch: true });
            // 等待创作页面渲染完成后，调用恢复接口
            setTimeout(() => resumeBatchStream(novelId), 400);
        } else if (task) {
            // 任务已完成，导航到小说详情页
            showToast(`「${task.novel_title}」批量生成已完成（${task.completed}/${task.total} 章）`, 'success');
            navigate('novel-detail', { novelId });
        } else {
            // 没有找到任务，导航到生成页面
            navigate('chapter-generate', { novelId });
        }
    } catch (e) {
        // 查询失败，直接导航到小说详情页
        navigate('novel-detail', { novelId });
    }
}

// 启动活跃任务轮询（登录后调用）
function startActiveTaskPolling() {
    if (_activeTaskPollTimer) clearTimeout(_activeTaskPollTimer);
    pollActiveTasks();
}

// 停止轮询（登出时调用）
function stopActiveTaskPolling() {
    if (_activeTaskPollTimer) {
        clearTimeout(_activeTaskPollTimer);
        _activeTaskPollTimer = null;
    }
    const panel = document.getElementById('activeTasksPanel');
    if (panel) {
        panel.style.display = 'none';
        panel.innerHTML = '';
    }
    _lastActiveTaskCount = 0;
}

// ==================== Novels List Page ====================
async function renderNovelsPage(main) {
    main.className = 'main-area';
    main.innerHTML = `
        <div class="page-header">
            <h2>${ic('library', 'icon-md')} 我的小说</h2>
            <div class="dropdown-wrapper">
                <button class="btn btn-primary" onclick="toggleCreateNovel(this)">+ 创建新小说</button>
            </div>
        </div>
        <div class="novel-list" id="novelList">
            <div class="empty-state">${ic('book-open', 'icon-lg')}<p>加载中...</p></div>
        </div>
    `;
    try {
        const data = await API.get('/api/novels');
        const list = document.getElementById('novelList');
        if (!data.novels || data.novels.length === 0) {
            list.innerHTML = `<div class="empty-state">${ic('book-open', 'icon-lg')}<p>还没有小说，创建你的第一部作品吧！</p></div>`;
            return;
        }
        // 统计总览
        const totalNovels = data.novels.length;
        const totalChapters = data.novels.reduce((s, n) => s + (n.chapter_count || 0), 0);
        const totalWords = data.novels.reduce((s, n) => s + (n.total_words || 0), 0);
        const statsHtml = `
            <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap">
                <div class="card" style="flex:1;min-width:120px;padding:14px;text-align:center;margin:0">
                    <div style="font-size:1.6rem;font-weight:700;color:var(--accent)">${totalNovels}</div>
                    <div style="font-size:0.8rem;color:var(--text-secondary)">部小说</div>
                </div>
                <div class="card" style="flex:1;min-width:120px;padding:14px;text-align:center;margin:0">
                    <div style="font-size:1.6rem;font-weight:700;color:var(--accent)">${totalChapters}</div>
                    <div style="font-size:0.8rem;color:var(--text-secondary)">总章节</div>
                </div>
                <div class="card" style="flex:1;min-width:120px;padding:14px;text-align:center;margin:0">
                    <div style="font-size:1.6rem;font-weight:700;color:var(--accent)">${(totalWords / 10000).toFixed(1)}万</div>
                    <div style="font-size:0.8rem;color:var(--text-secondary)">总字数</div>
                </div>
            </div>
        `;
        list.innerHTML = statsHtml + data.novels.map(n => `
            <div class="novel-item" onclick="navigate('novel-detail', {novelId: '${n.id}'})">
                <div class="novel-info">
                    <div class="title">${escHtml(n.title || '未命名小说')}</div>
                    <div class="meta">
                        ${(n.chapter_count || 0)} 章 · ${(n.total_words || 0).toLocaleString()} 字 · 
                        更新于 ${formatDate(n.updated_at)}
                    </div>
                </div>
                <div class="novel-actions" onclick="event.stopPropagation()">
                    <button class="btn btn-sm" onclick="navigate('novel-detail', {novelId: '${n.id}'})">打开</button>
                    <button class="btn btn-sm" onclick="cloneNovel('${n.id}')" title="复制小说设定（不含章节）">${ic('clipboard')} 克隆</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteNovelConfirm('${n.id}')" title="删除">${ic('trash-2')}</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        document.getElementById('novelList').innerHTML = `<div class="empty-state"><p>加载失败: ${escHtml(e.message)}</p></div>`;
    }
}

async function cloneNovel(novelId) {
    if (!await confirmDialog('克隆将复制该小说的全部设定（世界观、人物、大纲等），但不包含章节内容。继续？', { icon: 'info', confirmText: '克隆' })) return;
    try {
        // 获取原小说数据
        const { novel } = await API.get(`/api/novels/${novelId}`);
        const { characters } = await API.get(`/api/novels/${novelId}/characters`);
        const { relationships } = await API.get(`/api/novels/${novelId}/relationships`);
        // 创建新小说
        const { novel: newNovel } = await API.post('/api/novels', {
            title: (novel.title || '未命名') + ' (副本)',
            title_mode: novel.title_mode || 'auto',
            words_per_chapter: novel.words_per_chapter || 3000,
            duplicate_check_interval: novel.duplicate_check_interval || 5,
            summary_chapters_count: novel.summary_chapters_count || 3,
        });
        // 复制设定
        await API.put(`/api/novels/${newNovel.id}`, {
            world_building: novel.world_building || '',
            character_profiles: novel.character_profiles || '',
            style_reference: novel.style_reference || '',
            outline: novel.outline || '',
        });
        // 复制人物
        if (characters && characters.length) {
            for (const c of characters) {
                await API.post(`/api/novels/${newNovel.id}/characters`, {
                    name: c.name, profile: c.profile || '',
                });
            }
        }
        // 复制关系
        if (relationships && relationships.length) {
            for (const r of relationships) {
                if (r.character_a && r.character_b) {
                    await API.post(`/api/novels/${newNovel.id}/relationships`, {
                        character_a: r.character_a, character_b: r.character_b,
                        relation_type: r.relation_type, description: r.description || '',
                    });
                }
            }
        }
        showToast('克隆成功', 'success');
        navigate('novel-detail', { novelId: newNovel.id });
    } catch (e) {
        showToast('克隆失败: ' + e.message, 'error');
    }
}

function toggleCreateNovel(btn) {
    toggleDropdown(btn, `
        <h3 style="margin-bottom:14px;font-size:1.05rem">创建新小说</h3>
        <div class="form-group">
            <label>书名（可选，可后续填写）</label>
            <input type="text" id="createNovelTitle" placeholder="未命名小说">
        </div>
        <div class="form-group">
            <label>标题模式</label>
            <select id="createNovelTitleMode">
                <option value="auto">AI 自动生成章节标题</option>
                <option value="manual">手动指定章节标题</option>
            </select>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>每章字数</label>
                <input type="number" id="createNovelWords" value="3000" min="500" step="100">
            </div>
            <div class="form-group">
                <label>重复检测间隔</label>
                <input type="number" id="createNovelDupInterval" value="3" min="1" max="20">
            </div>
        </div>
        <div class="form-group">
            <label>预期创作章节数（可选）</label>
            <input type="number" id="createNovelExpectedChapters" value="0" min="0" placeholder="0 = 不限制">
            <p style="font-size:0.78rem;color:var(--text-secondary);margin-top:4px">设置后，AI生成大纲时会按此数量规划，章节生成时会有进度提醒</p>
        </div>
        <button class="btn btn-primary" onclick="createNovel()" style="width:100%">创建</button>
    `);
}

async function createNovel() {
    try {
        const data = await API.post('/api/novels', {
            title: document.getElementById('createNovelTitle').value,
            title_mode: document.getElementById('createNovelTitleMode').value,
            words_per_chapter: parseInt(document.getElementById('createNovelWords').value),
            duplicate_check_interval: parseInt(document.getElementById('createNovelDupInterval').value),
            expected_chapters: parseInt(document.getElementById('createNovelExpectedChapters').value) || 0,
        });
        closeAllDropdowns();
        showToast('小说创建成功', 'success');
        navigate('novel-detail', { novelId: data.novel.id });
    } catch (e) {
        showToast('创建失败: ' + e.message, 'error');
    }
}

// ==================== Novel Detail Page ====================
async function renderNovelDetailPage(main) {
    main.className = 'main-area';
    main.innerHTML = `<div class="empty-state"><p>加载中...</p></div>`;
    try {
        const [{ novel }, { chapters }, { relationships }, { characters }, { entries: wikiEntries, categories: wikiCategories }] = await Promise.all([
            API.get(`/api/novels/${currentNovelId}`),
            API.get(`/api/novels/${currentNovelId}/chapters`),
            API.get(`/api/novels/${currentNovelId}/relationships`),
            API.get(`/api/novels/${currentNovelId}/characters`),
            API.get(`/api/novels/${currentNovelId}/wiki`),
        ]);
        // 兜底：旧后端可能不返回 categories
        window._wikiCategories = wikiCategories || { location: '地点', faction: '势力阵营', item: '物品道具', event: '事件时间线' };
        window._wikiEntries = wikiEntries || [];

        // 缓存当前小说对象供下拉弹窗等场景读取（如 expected_chapters）
        currentNovel = novel;

        let vecStatus = null;
        try {
            vecStatus = await API.get('/api/config/vector/status');
        } catch (e) { /* ignore */ }

        const vecHint = vecStatus && !vecStatus.available
            ? '<span style="color:var(--warning);font-size:0.8rem"><i data-lucide="alert-triangle" class="icon-sm"></i> 向量模型未就绪，重复检测暂不可用</span>'
            : '';

        main.innerHTML = `
            <div class="page-header">
                <div class="inline-flex">
                    <button class="btn btn-sm" onclick="goBack()">← 返回</button>
                    <h2>${escHtml(novel.title || '未命名小说')}</h2>
                </div>
                <div class="inline-flex">
                    <button class="btn btn-sm" onclick="checkDuplicates()">${ic('search')} 重复检测</button>
                    <button class="btn btn-sm" onclick="generateSuggestions()">${ic('lightbulb')} AI建议</button>
                    <button class="btn btn-sm" onclick="showOutlineNav(this)">${ic('list-ordered')} 大纲导航</button>
                    <button class="btn btn-sm" onclick="toggleImportAnalyzePanel(this)">${ic('file-text')} 导入分析</button>
                    <div class="dropdown-wrapper">
                        <button class="btn btn-sm" onclick="toggleExportDropdown(this)">${ic('download')} 导出</button>
                    </div>
                    <div class="dropdown-wrapper">
                        <button class="btn btn-sm" onclick="toggleImageGenDropdown(this)">${ic('palette')} 配图</button>
                    </div>
                    <button class="btn btn-sm btn-primary" onclick="navigate('chapter-generate', {novelId: '${novel.id}'})">${ic('sparkles')} 生成</button>
                    <div class="dropdown-wrapper">
                        <button class="btn btn-sm" onclick="startContinuousGenerate()">${ic('repeat')} 连续</button>
                    </div>
                </div>
            </div>

            ${vecHint}

            <div class="tabs" id="detailTabs">
                <div class="tab active" onclick="switchDetailTab('settings')">${ic('pencil')} 小说设定</div>
                <div class="tab" onclick="switchDetailTab('characters')">${ic('drama')} 人物画像</div>
                <div class="tab" onclick="switchDetailTab('style')">${ic('feather')} 文风参考</div>
                <div class="tab" onclick="switchDetailTab('chapters')">${ic('list-ordered')} 章节列表</div>
                <div class="tab" onclick="switchDetailTab('relationships')">${ic('users')} 人物关系</div>
                <div class="tab" onclick="switchDetailTab('wiki')" id="wikiTab">${ic('globe')} 世界观百科</div>
                <div class="tab" onclick="switchDetailTab('suggestions')" id="suggestionsTab">${ic('lightbulb')} 建议</div>
            </div>

            <div id="detailTabSettings">
                <div id="novelCoverPreview" style="display:none;margin-bottom:16px;text-align:center;padding:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm)">
                    <div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:8px">${ic('book-open', 'icon-sm')} 小说封面</div>
                    <img id="novelCoverImg" alt="封面" style="max-width:100%;max-height:400px;border-radius:var(--radius-sm);border:1px solid var(--border)">
                    <div style="margin-top:8px"><a id="novelCoverLink" href="#" target="_blank" class="btn btn-sm">在新窗口打开</a></div>
                </div>
                <div class="card">
                    <div class="form-row">
                        <div class="form-group">
                            <label>书名</label>
                            <input type="text" id="novelTitle" value="${escAttr(novel.title)}" placeholder="未命名小说">
                        </div>
                        <div class="form-group">
                            <label>标题模式</label>
                            <select id="novelTitleMode">
                                <option value="auto" ${novel.title_mode === 'auto' ? 'selected' : ''}>AI 自动生成</option>
                                <option value="manual" ${novel.title_mode === 'manual' ? 'selected' : ''}>手动指定</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>每章字数</label>
                            <input type="number" id="novelWordsPerChapter" value="${novel.words_per_chapter}" min="500" step="100">
                        </div>
                        <div class="form-group">
                            <label>重复检测间隔（每N章）</label>
                            <input type="number" id="novelDupInterval" value="${novel.duplicate_check_interval}" min="1" max="20">
                        </div>
                        <div class="form-group">
                            <label>前文总结章数</label>
                            <input type="number" id="novelSummaryCount" value="${novel.summary_chapters_count || 3}" min="0" max="20">
                            <small style="color:var(--text-secondary)">生成新章时，LLM 总结最近N章作为前情提要，0=不总结</small>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>大纲</label>
                            <div class="file-drop" onclick="this.querySelector('input').click()">
                                <input type="file" accept=".txt,.md" onchange="importFile(this, 'outline')">
                                ${ic('file-text', 'icon-sm')} 点击导入大纲文件 (.txt/.md)
                            </div>
                            <textarea id="novelOutline" placeholder="输入大纲内容..." style="margin-top:8px">${escHtml(novel.outline)}</textarea>
                            <div class="form-group" style="margin-top:12px">
                                <label>预期创作章节数</label>
                                <input type="number" id="expectedChapters" value="${novel.expected_chapters || 0}" min="0" onchange="saveExpectedChapters()" placeholder="0 = 不限制">
                                <p style="font-size:0.78rem;color:var(--text-secondary);margin-top:4px">设置后，AI生成大纲时会按此数量规划，章节生成时会有进度提醒</p>
                            </div>
                            <div class="form-group" style="margin-top:12px">
                                <label>Token 预算（每章生成上限）</label>
                                <input type="number" id="novelMaxTokens" value="${novel.max_tokens || 16384}" min="1024" max="65536" step="1024" onchange="saveNovelMaxTokens()" placeholder="16384">
                                <p style="font-size:0.78rem;color:var(--text-secondary);margin-top:4px">控制每章生成的最大 token 数。推理模型建议 16384+，普通模型 8192 即可。过小会导致正文被截断</p>
                            </div>
                            <div class="inline-flex" style="gap:8px;margin-top:8px">
                                <button class="btn btn-sm btn-primary" onclick="toggleOutlineGenDropdown(this)">${ic('sparkles')} AI 生成大纲</button>
                            </div>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>世界观设定</label>
                            <div class="file-drop" onclick="this.querySelector('input').click()">
                                <input type="file" accept=".txt,.md" onchange="importFile(this, 'world')">
                                ${ic('file-text', 'icon-sm')} 点击导入世界观文件 (.txt/.md)
                            </div>
                            <textarea id="novelWorldBuilding" placeholder="输入世界观设定..." style="margin-top:8px">${escHtml(novel.world_building)}</textarea>
                            <button class="btn btn-sm" onclick="toggleWorldGenDropdown(this)" style="margin-top:6px">${ic('sparkles')} AI 优化世界观</button>
                        </div>
                    </div>
                    <button class="btn btn-primary" onclick="saveNovelSettings()">${ic('save')} 保存设定</button>
                </div>
            </div>

            <div id="detailTabCharacters" style="display:none">
                <div class="card">
                    <div class="card-header">
                        <h3>${ic('drama', 'icon-md')} 人物画像 (${characters.length} 人)</h3>
                        <div class="inline-flex">
                            <button class="btn btn-sm btn-primary" onclick="toggleCharGenDropdown(this)">${ic('sparkles')} AI 生成画像</button>
                            <button class="btn btn-sm" onclick="extractFromChapters(this)">${ic('book-open')} 从章节提取</button>
                            <button class="btn btn-sm" onclick="aiOptimizeAllCharacters()">${ic('wrench')} AI 优化全部</button>
                            <div class="dropdown-wrapper">
                                <button class="btn btn-sm" onclick="toggleUploadCharacters(this)">${ic('folder')} 上传</button>
                            </div>
                        </div>
                    </div>
                    <div id="charGenPreview" style="display:none;margin-bottom:12px"></div>
                    <div id="characterList">
                        ${characters.length === 0 ? `<div class="empty-state">${ic('drama', 'icon-lg')}<p>还没有人物画像</p><p style="font-size:0.85rem;margin-top:8px">点击「AI 生成画像」从大纲自动生成，或「从章节提取」分析已写内容</p></div>` : ''}
                    </div>
                </div>
            </div>

            <div id="detailTabStyle" style="display:none">
                <div class="card">
                    <div class="card-header">
                        <h3>${ic('feather', 'icon-md')} 文风参考</h3>
                        <div class="inline-flex">
                            <div class="dropdown-wrapper">
                                <button class="btn btn-sm" onclick="toggleAnalyzeStyleFromChapters(this)">${ic('list-ordered')} 从章节分析</button>
                            </div>
                            <div class="dropdown-wrapper">
                                <button class="btn btn-sm" onclick="toggleAnalyzeStyleFromFile(this)">${ic('folder')} 上传文档分析</button>
                            </div>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>当前文风描述（可直接编辑修改）</label>
                        <textarea id="novelStyleReference" placeholder="文风描述会在这里显示。你可以让 AI 从已有章节或上传文档中提炼，也可以手动输入..." style="min-height:180px">${escHtml(novel.style_reference || '')}</textarea>
                    </div>
                    <button class="btn btn-primary" onclick="saveStyleReference()">${ic('save')} 保存文风</button>
                </div>
            </div>

            <div id="detailTabChapters" style="display:none">
                <div class="card">
                    <div class="card-header">
                        <h3>${ic('list-ordered', 'icon-md')} 章节列表 (${chapters.length} 章)</h3>
                        <div class="inline-flex">
                            <input type="text" id="chapterSearchInput" placeholder="搜索章节内容..." style="width:180px;padding:4px 8px;font-size:0.85rem" oninput="searchChapters(this.value)">
                            <button class="btn btn-sm" onclick="createManualChapter()">${ic('pencil')} 手动创建</button>
                            <button class="btn btn-sm btn-primary" onclick="navigate('chapter-generate', {novelId: '${novel.id}'})">${ic('sparkles')} AI 生成</button>
                        </div>
                    </div>
                    <div id="chapterStatusBanner" style="display:none"></div>
                    <div id="pendingChangesBanner" style="display:none"></div>
                    <div id="searchResults" style="display:none;margin-bottom:8px"></div>
                    <div class="chapter-list" id="chapterList">
                        ${chapters.length === 0 ? '<div class="empty-state"><p>暂无章节，点击上方按钮开始创作</p></div>' : ''}
                    </div>
                </div>
            </div>

            <div id="detailTabRelationships" style="display:none">
                <div class="card">
                    <div class="card-header">
                        <h3>${ic('users', 'icon-md')} 人物关系 (${relationships.length} 条)</h3>
                        <div class="inline-flex">
                            <button class="btn btn-sm btn-primary" onclick="aiRefineRelationshipsV2()">${ic('bot')} AI 分析关系</button>
                            <button class="btn btn-sm" onclick="extractFromChapters(this)">${ic('book-open')} 从章节提取</button>
                            <button class="btn btn-sm" onclick="syncRelationships()">${ic('refresh-cw')} 从画像同步</button>
                            <div class="dropdown-wrapper">
                                <button class="btn btn-sm" onclick="toggleAddRelationship(this)">+ 手动添加</button>
                            </div>
                        </div>
                    </div>
                    <div id="relGenPreview" style="display:none;margin-bottom:12px"></div>
                    <div id="relationshipList">
                        ${relationships.length === 0 ? `<div class="empty-state">${ic('users', 'icon-lg')}<p>暂无关系</p><p style="font-size:0.85rem;margin-top:8px">点击「AI 分析关系」根据设定自动生成，或「从章节提取」分析已写内容</p></div>` : ''}
                    </div>
                </div>
            </div>

            <div id="detailTabWiki" style="display:none">
                <div class="card">
                    <div class="card-header">
                        <h3>${ic('globe', 'icon-md')} 世界观百科 (<span id="wikiCount">${(wikiEntries || []).length}</span> 条)</h3>
                        <div class="inline-flex">
                            <button class="btn btn-sm btn-primary" onclick="toggleWikiGenDropdown(this)">${ic('sparkles')} AI 生成</button>
                            <button class="btn btn-sm" onclick="toggleAddWikiEntry(this)">+ 手动添加</button>
                        </div>
                    </div>
                    <div id="wikiGenPreview" style="display:none;margin-bottom:12px"></div>
                    <div id="wikiContainer">
                        <div class="empty-state">${ic('globe', 'icon-lg')}<p>加载中...</p></div>
                    </div>
                </div>
            </div>

            <div id="detailTabSuggestions" style="display:none">
                <div class="card">
                    <div class="card-header"><h3>${ic('lightbulb', 'icon-md')} AI 写作建议</h3></div>
                    <div id="suggestionsContent">
                        <div class="empty-state"><p>点击上方「${ic('lightbulb', 'icon-sm')} AI 建议」按钮获取建议</p></div>
                    </div>
                </div>
            </div>
        `;

        // Render chapters
        if (chapters.length > 0) _renderChapterList(chapters);
        // 检查是否达到预期章节数，显示番外提示
        checkChapterStatus();
        // 检查是否有待确认的设定变更
        checkPendingChanges();
        // Render relationships
        if (relationships.length > 0) _renderRelationshipList(relationships);
        // Render characters
        if (characters.length > 0) _renderCharacterList(characters);
        // Render wiki
        _renderWikiTab(wikiEntries || []);

        // 加载封面：文件名固定为 novel_{id}.png，通过 onerror 判断是否存在
        _loadNovelCover(currentNovelId);
    } catch (e) {
        main.innerHTML = `<div class="empty-state"><p>加载失败: ${escHtml(e.message)}</p><button class="btn" onclick="navigate('novels')">返回列表</button></div>`;
    }
}

/** 加载小说封面：文件名固定为 /static/covers/novel_{id}.png，404 则隐藏 */
function _loadNovelCover(novelId) {
    const box = document.getElementById('novelCoverPreview');
    const img = document.getElementById('novelCoverImg');
    const link = document.getElementById('novelCoverLink');
    if (!box || !img) return;
    const coverUrl = `/static/covers/novel_${encodeURIComponent(novelId)}.png`;
    img.onload = () => { box.style.display = 'block'; };
    img.onerror = () => { box.style.display = 'none'; };
    img.src = coverUrl;
    if (link) link.href = coverUrl;
}

// 检查章节是否达到预期数量，显示番外提示条
async function checkChapterStatus() {
    const banner = document.getElementById('chapterStatusBanner');
    if (!banner) return;
    try {
        const status = await API.get(`/api/novels/${currentNovelId}/chapter-status`);
        if (status.reached_expected && status.expected_chapters > 0) {
            if (status.is_extras) {
                banner.innerHTML = `<div style="padding:12px;background:var(--accent-light);border-radius:var(--radius);margin-bottom:12px;display:flex;align-items:center;justify-content:space-between">
                    <div>${ic('party-popper', 'icon-md')} 已完成 ${status.expected_chapters} 章预期内容！当前为番外篇（第 ${status.current_chapters} 章）</div>
                </div>`;
            } else {
                banner.innerHTML = `<div style="padding:12px;background:var(--accent-light);border-radius:var(--radius);margin-bottom:12px;display:flex;align-items:center;justify-content:space-between">
                    <div>${ic('check-check', 'icon-md')} 已达到预期 ${status.expected_chapters} 章！可以继续创作番外篇</div>
                </div>`;
            }
            banner.style.display = 'block';
        } else {
            banner.style.display = 'none';
            banner.innerHTML = '';
        }
    } catch (e) { /* 后端可能不支持，忽略 */ }
}

// 检查待确认的设定变更，显示提示条
async function checkPendingChanges() {
    const banner = document.getElementById('pendingChangesBanner');
    if (!banner) return;
    try {
        const data = await API.get(`/api/novels/${currentNovelId}/pending-changes?status=pending`);
        const count = data.changes ? data.changes.length : 0;
        if (count > 0) {
            banner.style.display = 'block';
            banner.innerHTML = `<div style="padding:10px 12px;background:#fff3cd;border:1px solid #ffeaa7;border-radius:var(--radius);margin-bottom:12px;display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap">
                <div style="color:#856404;display:flex;align-items:center;gap:6px">${ic('edit', 'icon-sm')} 有 ${count} 条 AI 提议的设定变更待确认</div>
                <button class="btn" style="padding:5px 12px;font-size:0.85rem" onclick="reviewPendingChanges()">查看并确认</button>
            </div>`;
        } else {
            banner.style.display = 'none';
            banner.innerHTML = '';
        }
    } catch (e) { /* 忽略 */ }
}

async function reviewPendingChanges() {
    try {
        const data = await API.get(`/api/novels/${currentNovelId}/pending-changes?status=pending`);
        if (data.changes && data.changes.length > 0) {
            showPendingChangesDialog(data.changes, data.changes.length);
            // 关闭对话框后刷新提示条
            const checkInterval = setInterval(() => {
                if (!document.querySelector('.modal-backdrop')) {
                    clearInterval(checkInterval);
                    checkPendingChanges();
                }
            }, 500);
        } else {
            showToast('没有待确认的变更', 'info');
        }
    } catch (e) {
        showToast('加载失败: ' + e.message, 'error');
    }
}

function _renderChapterList(chapters) {
    const list = document.getElementById('chapterList');
    if (!list) return;
    const latestId = chapters.length ? chapters[chapters.length - 1].id : '';
    // 章节总数和总字数
    const totalWords = chapters.reduce((s, ch) => s + (ch.words_count || 0), 0);
    const doneCount = chapters.filter(ch => ch.status === 'done' || ch.status === 'review').length;
    const progress = chapters.length > 0 ? Math.round(doneCount / chapters.length * 100) : 0;
    list.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-size:0.85rem;color:var(--text-secondary);flex-wrap:wrap;gap:8px">
            <span>共 ${chapters.length} 章 · ${totalWords.toLocaleString()} 字 · 完成 ${progress}%</span>
            <div class="inline-flex">
                <button class="btn btn-sm" onclick="toggleBatchMode()" id="batchModeBtn">${ic('check-square')} 批量操作</button>
            </div>
        </div>
        <div id="batchToolbar" style="display:none;margin-bottom:8px;padding:10px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm);gap:6px" class="inline-flex">
            <span style="font-size:0.85rem;color:var(--text-secondary)" id="batchSelectedCount">已选 0 章</span>
            <button class="btn btn-sm" onclick="batchSetStatus('done')">${ic('check')} 标记完成</button>
            <button class="btn btn-sm" onclick="batchSetStatus('review')">${ic('eye')} 标记审阅</button>
            <button class="btn btn-sm" onclick="batchSetStatus('draft')">${ic('pencil')} 标记草稿</button>
            <button class="btn btn-sm btn-danger" onclick="batchDelete()">${ic('trash-2')} 删除选中</button>
            <button class="btn btn-sm" onclick="toggleBatchMode()">取消</button>
        </div>
    ` + chapters.map((ch, i) => `
        <div class="chapter-item" id="chapterItem_${ch.id}" onclick="onChapterItemClick(event, '${ch.id}')">
            <span class="ch-num" style="display:none" id="chk-${ch.id}"><input type="checkbox" id="chkInput_${ch.id}" onclick="event.stopPropagation();toggleChapterSelect('${ch.id}')" style="width:auto"></span>
            <span class="ch-num" id="num-${ch.id}">#${ch.number}</span>
            <span class="ch-title">${escHtml(ch.title)}</span>
            <span class="ch-meta">${ch.words_count}字 | <span class="badge badge-${ch.status}">${ch.status}</span></span>
            <div class="ch-actions" onclick="event.stopPropagation()">
                ${i > 0 ? `<button class="btn btn-sm" title="上移" onclick="moveChapter(${i}, -1)">${ic('arrow-up')}</button>` : ''}
                ${i < chapters.length - 1 ? `<button class="btn btn-sm" title="下移" onclick="moveChapter(${i}, 1)">${ic('arrow-down')}</button>` : ''}
                <button class="btn btn-sm" title="阅读" onclick="navigate('chapter-read', {chapterId: '${ch.id}', novelId: '${currentNovelId}'})">${ic('book-open')}</button>
                ${ch.id === latestId ? `<button class="btn btn-sm" title="重新生成" onclick="regenerateChapter('${ch.id}')">${ic('refresh-cw')}</button>` : ''}
                <button class="btn btn-sm" title="编辑" onclick="navigate('chapter-edit', {chapterId: '${ch.id}', novelId: '${currentNovelId}'})">${ic('pencil')}</button>
                <button class="btn btn-sm btn-danger" title="删除" onclick="deleteChapterConfirm('${ch.id}')">${ic('trash-2')}</button>
            </div>
        </div>
    `).join('');
    // 缓存当前章节列表供重排使用
    window._currentChapterList = chapters;
    window._batchMode = false;
    window._batchSelected = new Set();
}

/**
 * 章节项点击处理：批量模式下切换选中，非批量模式下导航到编辑页
 * 避免批量模式下点击空白区域误触进入章节
 */
function onChapterItemClick(event, chapterId) {
    // 如果点击的是按钮区域内的元素（已通过 stopPropagation 处理），不触发
    if (window._batchMode) {
        // 批量模式：点击行内任何位置都切换选中（不导航）
        event.preventDefault();
        toggleChapterSelect(chapterId);
        // 同步 checkbox 状态
        const input = document.getElementById('chkInput_' + chapterId);
        if (input) input.checked = window._batchSelected.has(chapterId);
        // 视觉反馈：选中行高亮
        const item = document.getElementById('chapterItem_' + chapterId);
        if (item) {
            if (window._batchSelected.has(chapterId)) {
                item.style.background = 'var(--accent-light)';
                item.style.borderLeft = '3px solid var(--accent)';
            } else {
                item.style.background = '';
                item.style.borderLeft = '';
            }
        }
    } else {
        // 非批量模式：导航到章节编辑
        navigate('chapter-edit', { chapterId, novelId: currentNovelId });
    }
}

function toggleBatchMode() {
    window._batchMode = !window._batchMode;
    const toolbar = document.getElementById('batchToolbar');
    const btn = document.getElementById('batchModeBtn');
    if (window._batchMode) {
        toolbar.style.display = 'flex';
        if (btn) btn.innerHTML = `${ic('check-square')} 取消批量`;
        // 显示 checkbox，隐藏序号
        window._currentChapterList.forEach(ch => {
            const chk = document.getElementById('chk-' + ch.id);
            const num = document.getElementById('num-' + ch.id);
            if (chk) chk.style.display = 'inline-flex';
            if (num) num.style.display = 'none';
        });
    } else {
        toolbar.style.display = 'none';
        if (btn) btn.innerHTML = `${ic('check-square')} 批量操作`;
        window._batchSelected.clear();
        window._currentChapterList.forEach(ch => {
            const chk = document.getElementById('chk-' + ch.id);
            const num = document.getElementById('num-' + ch.id);
            if (chk) { chk.style.display = 'none'; const input = chk.querySelector('input'); if (input) input.checked = false; }
            if (num) num.style.display = 'inline';
            // 清除选中高亮样式
            const item = document.getElementById('chapterItem_' + ch.id);
            if (item) { item.style.background = ''; item.style.borderLeft = ''; }
        });
        _updateBatchCount();
    }
}

function toggleChapterSelect(chapterId) {
    if (window._batchSelected.has(chapterId)) {
        window._batchSelected.delete(chapterId);
    } else {
        window._batchSelected.add(chapterId);
    }
    _updateBatchCount();
}

function _updateBatchCount() {
    const el = document.getElementById('batchSelectedCount');
    if (el) el.textContent = `已选 ${window._batchSelected.size} 章`;
}

async function batchSetStatus(status) {
    const ids = Array.from(window._batchSelected);
    if (!ids.length) { showToast('请先选择章节', 'error'); return; }
    try {
        for (const id of ids) {
            const ch = window._currentChapterList.find(c => c.id === id);
            if (ch) await API.put(`/api/chapters/${id}`, { title: ch.title, content: ch.content, status });
        }
        showToast(`已更新 ${ids.length} 章状态`, 'success');
        toggleBatchMode();
        const novel = await API.get(`/api/novels/${currentNovelId}`);
        _renderChapterList(novel.chapters || []);
    } catch (e) {
        showToast('批量操作失败: ' + e.message, 'error');
    }
}

async function batchDelete() {
    const ids = Array.from(window._batchSelected);
    if (!ids.length) { showToast('请先选择章节', 'error'); return; }
    if (!await confirmDialog(`确定删除 ${ids.length} 个章节？此操作不可恢复。`, { icon: 'danger', confirmText: '删除', danger: true })) return;
    try {
        for (const id of ids) {
            await API.del(`/api/chapters/${id}`);
        }
        showToast(`已删除 ${ids.length} 章`, 'success');
        toggleBatchMode();
        const novel = await API.get(`/api/novels/${currentNovelId}`);
        _renderChapterList(novel.chapters || []);
    } catch (e) {
        showToast('删除失败: ' + e.message, 'error');
    }
}

async function moveChapter(index, direction) {
    const chapters = window._currentChapterList;
    if (!chapters) return;
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= chapters.length) return;
    // 交换位置
    const ids = chapters.map(c => c.id);
    [ids[index], ids[newIndex]] = [ids[newIndex], ids[index]];
    try {
        await API.put(`/api/novels/${currentNovelId}/chapters/reorder`, { chapter_ids: ids });
        showToast('章节顺序已更新', 'success');
        // 局部刷新章节列表
        const novel = await API.get(`/api/novels/${currentNovelId}`);
        _renderChapterList(novel.chapters || []);
    } catch (e) {
        showToast('重排失败: ' + e.message, 'error');
    }
}

function searchChapters(query) {
    const resultsDiv = document.getElementById('searchResults');
    if (!resultsDiv) return;
    if (!query || query.trim().length < 2) {
        resultsDiv.style.display = 'none';
        return;
    }
    const chapters = window._currentChapterList || [];
    const q = query.trim().toLowerCase();
    const matches = [];
    for (const ch of chapters) {
        if (!ch.content) continue;
        const idx = ch.content.toLowerCase().indexOf(q);
        if (idx >= 0) {
            const start = Math.max(0, idx - 30);
            const end = Math.min(ch.content.length, idx + q.length + 30);
            const snippet = ch.content.substring(start, end).replace(/\n/g, ' ');
            matches.push({ ch, snippet, idx });
        }
    }
    if (matches.length === 0) {
        resultsDiv.style.display = 'block';
        resultsDiv.innerHTML = '<div style="padding:8px;color:var(--text-secondary);font-size:0.85rem">未找到匹配的章节</div>';
        return;
    }
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = '<div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:4px">找到 ' + matches.length + ' 个结果</div>' +
        matches.map(m => `<div style="padding:6px 8px;background:var(--bg-card);border-radius:var(--radius-sm);margin-bottom:4px;cursor:pointer;font-size:0.85rem" onclick="navigate('chapter-edit', {chapterId: '${m.ch.id}', novelId: '${currentNovelId}'})">
            <strong>第${m.ch.number}章</strong> ${escHtml(m.ch.title)}: ...${escHtml(m.snippet)}...
        </div>`).join('');
}

// 大纲导航：解析大纲并显示可点击的章节列表
async function showOutlineNav(btn) {
    try {
        const { novel } = await API.get(`/api/novels/${currentNovelId}`);
        const { chapters } = await API.get(`/api/novels/${currentNovelId}/chapters`);
        const outline = novel.outline || '';
        if (!outline.trim()) {
            showToast('请先生成或输入大纲', 'info');
            return;
        }
        // 解析大纲：匹配 "第X章 标题" 或 "第X章" 格式
        const lines = outline.split('\n');
        const parsed = [];
        let currentChapter = null;
        for (const line of lines) {
            const m = line.match(/第(\d+)章\s*(.*)/);
            if (m) {
                if (currentChapter) parsed.push(currentChapter);
                currentChapter = { number: parseInt(m[1]), title: m[2].trim(), summary: '' };
            } else if (currentChapter && line.trim()) {
                currentChapter.summary = (currentChapter.summary + ' ' + line.trim()).trim();
            }
        }
        if (currentChapter) parsed.push(currentChapter);

        if (!parsed.length) {
            showToast('大纲格式无法解析（需要"第X章"格式）', 'info');
            return;
        }

        // 匹配已写章节
        const existingMap = {};
        chapters.forEach(ch => { existingMap[ch.number] = ch; });

        const html = `
            <h3 style="margin-bottom:12px;font-size:1rem">${ic('list-ordered', 'icon-md')} 大纲导航</h3>
            <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:10px">点击章节可直接生成或阅读</div>
            <div style="max-height:400px;overflow-y:auto">
            ${parsed.map(p => {
                const existing = existingMap[p.number];
                return `<div style="padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:6px;cursor:pointer" onclick="${existing ? `navigate('chapter-read', {chapterId: '${existing.id}', novelId: '${currentNovelId}'})` : `quickGenerateChapter(${p.number})`}">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <div style="flex:1;min-width:0">
                            <span style="font-weight:600;color:var(--accent)">第${p.number}章</span>
                            <span style="margin-left:6px">${escHtml(p.title || '未命名')}</span>
                        </div>
                        <span style="font-size:0.78rem;flex-shrink:0;margin-left:8px">
                            ${existing ? `<span class="badge badge-${existing.status}">已写</span>` : '<span class="badge badge-draft">未写</span>'}
                        </span>
                    </div>
                    ${p.summary ? `<div style="font-size:0.8rem;color:var(--text-secondary);margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(p.summary)}</div>` : ''}
                </div>`;
            }).join('')}
            </div>
        `;
        toggleDropdown(btn, html, false);
    } catch (e) {
        showToast('加载大纲失败: ' + e.message, 'error');
    }
}

function quickGenerateChapter(number) {
    closeAllDropdowns();
    navigate('chapter-generate', { novelId: currentNovelId });
    setTimeout(() => {
        const numInput = document.getElementById('genChapterNumber');
        if (numInput) numInput.value = number;
    }, 300);
}

function _renderRelationshipList(relationships) {
    const list = document.getElementById('relationshipList');
    if (!list) return;
    list.innerHTML = relationships.map(r => `
        <div class="provider-card">
            <div class="provider-info">
                <div class="provider-name">
                    ${escHtml(r.character_a)} ${r.relation_type && r.relation_type !== '待定义' ? '↔ ' + escHtml(r.character_b) : escHtml(r.character_b ? '↔ ' + escHtml(r.character_b) : '')}
                    ${r.relation_type === '待定义' ? '<span class="badge" style="background:#fef3c7;color:#92400e">待定义</span>' : ''}
                </div>
                ${r.relation_type && r.relation_type !== '待定义' ? `<div class="provider-meta">${escHtml(r.relation_type)}${r.description ? ' — ' + escHtml(r.description) : ''}</div>` : ''}
            </div>
            <div class="provider-actions">
                <div class="dropdown-wrapper">
                    <button class="btn btn-sm" onclick="toggleEditRelationship(this, '${r.id}')">编辑</button>
                </div>
                <button class="btn btn-sm btn-danger" onclick="deleteRelationshipConfirm('${r.id}')">删除</button>
            </div>
        </div>
    `).join('');
}

function switchDetailTab(tabName) {
    document.querySelectorAll('#detailTabs .tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`#detailTabs .tab[onclick*="${tabName}"]`)?.classList.add('active');
    ['settings', 'characters', 'style', 'chapters', 'relationships', 'wiki', 'suggestions'].forEach(name => {
        const el = document.getElementById('detailTab' + name.charAt(0).toUpperCase() + name.slice(1));
        if (el) el.style.display = name === tabName ? '' : 'none';
    });
}

// ==================== Relationships ====================

function toggleAddRelationship(btn) {
    toggleDropdown(btn, `
        <h3 style="margin-bottom:14px;font-size:1.05rem">添加人物关系</h3>
        <div class="form-group">
            <label>角色 A</label>
            <input type="text" id="addRelCharA" placeholder="如：张三">
        </div>
        <div class="form-group">
            <label>角色 B</label>
            <input type="text" id="addRelCharB" placeholder="如：李四（可为空，表示仅添加角色）">
        </div>
        <div class="form-group">
            <label>关系类型</label>
            <select id="addRelType">
                <option value="待定义">待定义</option>
                <option value="挚友">挚友</option>
                <option value="恋人">恋人</option>
                <option value="仇敌">仇敌</option>
                <option value="师徒">师徒</option>
                <option value="亲人">亲人</option>
                <option value="盟友">盟友</option>
                <option value="暗恋">暗恋</option>
                <option value="主仆">主仆</option>
                <option value="竞争">竞争</option>
                <option value="其他">其他</option>
            </select>
        </div>
        <div class="form-group">
            <label>描述</label>
            <input type="text" id="addRelDesc" placeholder="可选，补充说明">
        </div>
        <button class="btn btn-primary" onclick="addRelationship()" style="width:100%">添加</button>
    `, true);
}

async function addRelationship() {
    try {
        await API.post(`/api/novels/${currentNovelId}/relationships`, {
            character_a: document.getElementById('addRelCharA').value,
            character_b: document.getElementById('addRelCharB').value,
            relation_type: document.getElementById('addRelType').value,
            description: document.getElementById('addRelDesc').value,
        });
        closeAllDropdowns();
        showToast('关系已添加', 'success');
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('添加失败: ' + e.message, 'error');
    }
}

async function toggleEditRelationship(btn, relId) {
    const { relationships } = await API.get(`/api/novels/${currentNovelId}/relationships`);
    const r = relationships.find(x => x.id === relId);
    if (!r) { showToast('加载关系失败', 'error'); return; }
    toggleDropdown(btn, `
        <h3 style="margin-bottom:14px;font-size:1.05rem">编辑关系</h3>
        <div class="form-group">
            <label>角色 A</label>
            <input type="text" id="editRelCharA" value="${escAttr(r.character_a)}">
        </div>
        <div class="form-group">
            <label>角色 B</label>
            <input type="text" id="editRelCharB" value="${escAttr(r.character_b)}">
        </div>
        <div class="form-group">
            <label>关系类型</label>
            <select id="editRelType">
                ${['待定义','挚友','恋人','仇敌','师徒','亲人','盟友','暗恋','主仆','竞争','其他'].map(t =>
                    `<option value="${t}" ${r.relation_type === t ? 'selected' : ''}>${t}</option>`
                ).join('')}
            </select>
        </div>
        <div class="form-group">
            <label>描述</label>
            <input type="text" id="editRelDesc" value="${escAttr(r.description)}">
        </div>
        <button class="btn btn-primary" onclick="saveRelationship('${r.id}')" style="width:100%">保存</button>
    `, true);
}

async function saveRelationship(relId) {
    try {
        await API.put(`/api/relationships/${relId}`, {
            character_a: document.getElementById('editRelCharA').value,
            character_b: document.getElementById('editRelCharB').value,
            relation_type: document.getElementById('editRelType').value,
            description: document.getElementById('editRelDesc').value,
        });
        closeAllDropdowns();
        showToast('关系已更新', 'success');
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

async function deleteRelationshipConfirm(relId) {
    if (!await confirmDialog('确定要删除这个关系吗？', { icon: 'danger', confirmText: '删除', danger: true })) return;
    try {
        await API.del(`/api/relationships/${relId}`);
        showToast('关系已删除', 'success');
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('删除失败: ' + e.message, 'error');
    }
}

async function syncRelationships() {
    try {
        await API.post(`/api/novels/${currentNovelId}/relationships/sync`, {});
        showToast('已从人物画像同步角色', 'success');
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('同步失败: ' + e.message, 'error');
    }
}

// ==================== AI 关系分析（预览+选择性应用） ====================

async function aiRefineRelationshipsV2() {
    const preview = document.getElementById('relGenPreview');
    if (!preview) return;
    preview.style.display = 'block';
    preview.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-secondary)">${ic('bot', 'icon-sm')} AI 正在分析角色关系网...</div>`;
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/relationships/ai-refine`, {});
        const rels = data.relationships || [];
        if (!rels.length) {
            preview.innerHTML = '<div style="padding:16px;color:var(--text-secondary)">AI 未分析出关系（请先添加人物画像和大纲）</div>';
            return;
        }
        window._aiRefinedRels = rels;
        // 获取已有关系，标记重复
        const { relationships: existing } = await API.get(`/api/novels/${currentNovelId}/relationships`);
        const existingPairs = new Set(existing.map(r => `${r.character_a}|${r.character_b}`));

        preview.innerHTML = `
            <div style="padding:12px;background:var(--accent-light);border:1px solid var(--accent);border-radius:var(--radius-sm);margin-bottom:8px">
                <strong>${ic('bot', 'icon-sm')} AI 分析出 ${rels.length} 条关系</strong>
                <span style="font-size:0.8rem;color:var(--text-secondary);margin-left:8px">勾选要添加的关系，已存在的会标记</span>
            </div>
            ${rels.map((r, i) => {
                const pairKey = `${r.character_a}|${r.character_b}`;
                const reverseKey = `${r.character_b}|${r.character_a}`;
                const isDup = existingPairs.has(pairKey) || existingPairs.has(reverseKey);
                return `
                    <div style="padding:10px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:4px;${isDup ? 'opacity:0.6' : ''}">
                        <div style="display:flex;align-items:flex-start;gap:8px">
                            <input type="checkbox" id="relChk_${i}" ${isDup ? '' : 'checked'} style="margin-top:4px;width:auto;flex-shrink:0">
                            <div style="flex:1;min-width:0">
                                <div style="font-weight:600">
                                    ${escHtml(r.character_a)}
                                    <span style="color:var(--accent);margin:0 4px">${escHtml(r.relation_type)}</span>
                                    ${escHtml(r.character_b)}
                                    ${isDup ? '<span class="badge" style="background:#fef3c7;color:#92400e;font-size:0.7rem;margin-left:4px">已有</span>' : ''}
                                </div>
                                <div style="font-size:0.82rem;color:var(--text-secondary);margin-top:2px">${escHtml(r.description)}</div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('')}
            <div class="inline-flex" style="margin-top:8px">
                <button class="btn btn-primary btn-sm" onclick="applyAiRefinedRelationships()">${ic('check')} 应用选中</button>
                <button class="btn btn-sm" onclick="document.getElementById('relGenPreview').style.display='none'">取消</button>
            </div>
        `;
    } catch (e) {
        preview.innerHTML = `<div style="padding:16px;color:var(--danger)">分析失败: ${escHtml(e.message)}</div>`;
    }
}

async function applyAiRefinedRelationships() {
    const rels = window._aiRefinedRels || [];
    if (!rels.length) { showToast('无关系可应用', 'error'); return; }
    const selected = rels.filter((_, i) => document.getElementById('relChk_' + i)?.checked);
    if (!selected.length) { showToast('请至少选择一条关系', 'error'); return; }
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/relationships/apply-extracted`, { relationships: selected });
        showToast(`已添加 ${data.count} 条关系`, 'success');
        document.getElementById('relGenPreview').style.display = 'none';
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('应用失败: ' + e.message, 'error');
    }
}

// ==================== Character Cards ====================

function _renderCharacterList(characters) {
    const list = document.getElementById('characterList');
    if (!list) return;
    // 缓存角色数据，便于生成立绘后回填图片
    window._characterCache = characters;
    list.innerHTML = characters.map(c => `
        <div class="character-card">
            <div class="character-card-header">
                <span class="character-name">${ic('drama', 'icon-sm')} ${escHtml(c.name)}</span>
                <div class="inline-flex">
                    <button class="btn btn-sm" onclick="generateCharacterImage('${c.id}')">${ic('palette')} 生成立绘</button>
                    <button class="btn btn-sm" onclick="aiOptimizeCharacter('${c.id}')">${ic('sparkles')} AI 优化</button>
                    <div class="dropdown-wrapper">
                        <button class="btn btn-sm" onclick="toggleEditCharacter(this, '${c.id}')">编辑</button>
                    </div>
                    <button class="btn btn-sm btn-danger" onclick="deleteCharacterConfirm('${c.id}')">删除</button>
                </div>
            </div>
            <div class="character-card-body" id="charProfile_${c.id}">
                <div id="charImage_${c.id}" style="display:none;margin-bottom:10px;text-align:center">
                    <img id="charImgTag_${c.id}" src="" alt="立绘" style="max-width:100%;max-height:300px;border-radius:var(--radius-sm);border:1px solid var(--border)">
                </div>
                ${c.profile ? `<div class="content-preview" style="max-height:200px;overflow-y:auto;font-size:0.9rem">${escHtml(c.profile)}</div>` : '<div style="color:var(--text-secondary);padding:12px">暂无画像，点击「AI 优化」生成</div>'}
            </div>
        </div>
    `).join('');
}

async function generateCharacterImage(charId) {
    const chars = window._characterCache || [];
    const c = chars.find(x => x.id === charId);
    if (!c) { showToast('未找到角色信息', 'error'); return; }
    // 立绘按钮即时反馈
    const btns = document.querySelectorAll(`.character-card button[onclick*="generateCharacterImage('${charId}')"]`);
    btns.forEach(b => { b.disabled = true; b.innerHTML = `${ic('palette')} 生成中...`; });
    // 显示加载状态
    const imgBox = document.getElementById('charImage_' + charId);
    if (imgBox) {
        imgBox.style.display = 'block';
        imgBox.innerHTML = `<div style="padding:20px;color:var(--text-secondary);text-align:center">${ic('palette', 'icon-sm')} 正在生成立绘，请稍候...</div>`;
    }
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/generate-image`, {
            type: 'character',
            name: c.name,
            description: c.profile || '',
        });
        if (data.error) {
            showToast(data.error, 'error');
            if (imgBox) imgBox.style.display = 'none';
            return;
        }
        if (imgBox) {
            imgBox.innerHTML = `<img src="${escAttr(data.image_url)}" alt="立绘" style="max-width:100%;max-height:300px;border-radius:var(--radius-sm);border:1px solid var(--border)">`;
            imgBox.style.display = 'block';
        }
        showToast('立绘生成成功', 'success');
    } catch (e) {
        showToast('立绘生成失败: ' + e.message, 'error');
        if (imgBox) imgBox.style.display = 'none';
    } finally {
        btns.forEach(b => { b.disabled = false; b.innerHTML = `${ic('palette')} 生成立绘`; });
    }
}

async function generateNovelCover(btn) {
    closeAllDropdowns();
    // 读取小说标题作为描述
    let novelTitle = '';
    const titleInput = document.getElementById('novelTitle');
    if (titleInput) novelTitle = titleInput.value;
    if (btn) { btn.disabled = true; btn.innerHTML = `${ic('palette')} 生成中...`; }
    showToast('正在生成封面...', 'info');
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/generate-image`, {
            type: 'cover',
            name: novelTitle || '',
            description: '',
        });
        if (data.error) {
            showToast(data.error, 'error');
            return;
        }
        // 在小说设定Tab顶部显示封面
        let coverBox = document.getElementById('novelCoverPreview');
        if (!coverBox) {
            const settingsTab = document.getElementById('detailTabSettings');
            if (settingsTab) {
                coverBox = document.createElement('div');
                coverBox.id = 'novelCoverPreview';
                coverBox.style.cssText = 'margin-bottom:16px;text-align:center;padding:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm)';
                settingsTab.insertBefore(coverBox, settingsTab.firstChild);
            }
        }
        if (coverBox) {
            coverBox.innerHTML = `
                <div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:8px">${ic('book-open', 'icon-sm')} 小说封面</div>
                <img src="${escAttr(data.image_url)}" alt="封面" style="max-width:100%;max-height:400px;border-radius:var(--radius-sm);border:1px solid var(--border)">
                <div style="margin-top:8px"><a href="${escAttr(safeUrl(data.image_url))}" target="_blank" class="btn btn-sm">在新窗口打开</a></div>
            `;
        }
        showToast('封面生成成功', 'success');
    } catch (e) {
        showToast('封面生成失败: ' + e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = `${ic('palette')} 生成封面`; }
    }
}

function toggleUploadCharacters(btn) {
    toggleDropdown(btn, `
        <h3 style="margin-bottom:14px;font-size:1.05rem">上传人物画像</h3>
        <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:12px">
            选择多个 .txt 文件上传，文件名将作为人物名，内容作为画像。
        </p>
        <div class="form-group">
            <input type="file" id="charFilesInput" accept=".txt" multiple>
        </div>
        <button class="btn btn-primary" onclick="uploadCharacters()" style="width:100%">上传</button>
    `, true);
}

async function uploadCharacters() {
    const input = document.getElementById('charFilesInput');
    if (!input || !input.files.length) { showToast('请选择文件', 'error'); return; }
    const formData = new FormData();
    for (const f of input.files) formData.append('files', f);
    try {
        const r = await fetch(`/api/novels/${currentNovelId}/characters/upload`, {
            method: 'POST', body: formData,
            headers: authToken ? { 'Authorization': 'Bearer ' + authToken } : {},
        });
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        closeAllDropdowns();
        showToast(`已导入 ${input.files.length} 个人物`, 'success');
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('上传失败: ' + e.message, 'error');
    }
}

async function toggleEditCharacter(btn, charId) {
    const { characters } = await API.get(`/api/novels/${currentNovelId}/characters`);
    const c = characters.find(x => x.id === charId);
    if (!c) { showToast('加载人物失败', 'error'); return; }
    toggleDropdown(btn, `
        <h3 style="margin-bottom:14px;font-size:1.05rem">编辑: ${escHtml(c.name)}</h3>
        <div class="form-group">
            <label>人物名</label>
            <input type="text" id="editCharName" value="${escAttr(c.name)}">
        </div>
        <div class="form-group">
            <label>画像内容</label>
            <textarea id="editCharProfile" style="min-height:200px">${escHtml(c.profile)}</textarea>
        </div>
        <button class="btn btn-primary" onclick="saveCharacter('${c.id}')" style="width:100%">保存</button>
    `, true);
}

async function saveCharacter(charId) {
    try {
        await API.put(`/api/novels/${currentNovelId}/characters/${charId}`, {
            name: document.getElementById('editCharName').value,
            profile: document.getElementById('editCharProfile').value,
        });
        closeAllDropdowns();
        showToast('人物已更新', 'success');
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

async function deleteCharacterConfirm(charId) {
    if (!await confirmDialog('确定要删除这个人物吗？', { icon: 'danger', confirmText: '删除', danger: true })) return;
    try {
        await API.del(`/api/novels/${currentNovelId}/characters/${charId}`);
        showToast('人物已删除', 'success');
        // 局部刷新人物列表（不整页刷新，避免丢失当前滚动位置和 tab 状态）
        const { characters } = await API.get(`/api/novels/${currentNovelId}/characters`);
        _renderCharacterList(characters || []);
    } catch (e) {
        showToast('删除失败: ' + e.message, 'error');
    }
}

// ==================== AI 生成画像 & 从章节提取 ====================

// ==================== 世界观百科 ====================

const WIKI_CATEGORY_ICONS = {
    location: 'map-pin',
    faction: 'swords',
    item: 'gift',
    event: 'hourglass',
};

// 当前选中的类别（默认 location）
let _currentWikiCategory = 'location';

function _getWikiCategories() {
    return window._wikiCategories || { location: '地点', faction: '势力阵营', item: '物品道具', event: '事件时间线' };
}

function renderWikiTab(entries) {
    _renderWikiTab(entries);
}

function _renderWikiTab(entries) {
    const container = document.getElementById('wikiContainer');
    if (!container) return;
    window._wikiEntries = entries || [];

    const categories = _getWikiCategories();
    const catKeys = Object.keys(categories);
    if (!_currentWikiCategory || !categories[_currentWikiCategory]) {
        _currentWikiCategory = catKeys[0] || 'location';
    }

    // 类别切换条
    const catTabsHtml = catKeys.map(k => `
        <button class="btn btn-sm ${k === _currentWikiCategory ? 'btn-primary' : ''}"
                onclick="switchWikiCategory('${k}')" style="margin-right:6px">
            ${ic(WIKI_CATEGORY_ICONS[k] || 'pin')} ${categories[k]} (${(entries || []).filter(e => e.category === k).length})
        </button>
    `).join('');

    const filtered = (entries || []).filter(e => e.category === _currentWikiCategory);

    const listHtml = filtered.length === 0
        ? `<div class="empty-state">${ic(WIKI_CATEGORY_ICONS[_currentWikiCategory] || 'pin', 'icon-lg')}<p>暂无${categories[_currentWikiCategory]}条目</p><p style="font-size:0.85rem;margin-top:8px">点击「${ic('sparkles', 'icon-sm')} AI 生成」自动从大纲和世界观提取，或「+ 手动添加」</p></div>`
        : filtered.map(e => _renderWikiCard(e)).join('');

    container.innerHTML = `
        <div style="margin-bottom:12px;display:flex;flex-wrap:wrap;gap:6px">
            ${catTabsHtml}
        </div>
        <div id="wikiEntryList">${listHtml}</div>
    `;

    const countEl = document.getElementById('wikiCount');
    if (countEl) countEl.textContent = (entries || []).length;
}

function _renderWikiCard(e) {
    const icon = ic(WIKI_CATEGORY_ICONS[e.category] || 'pin', 'icon-sm');
    const meta = e.metadata ? (() => {
        try {
            const obj = typeof e.metadata === 'string' ? JSON.parse(e.metadata) : e.metadata;
            if (!obj || typeof obj !== 'object') return '';
            const pairs = Object.entries(obj).filter(([_, v]) => v !== null && v !== '');
            if (!pairs.length) return '';
            return `<div style="margin-top:6px;font-size:0.78rem;color:var(--text-secondary)">${pairs.map(([k, v]) => `<span style="margin-right:10px">${ic('tag', 'icon-sm')} ${escHtml(k)}: ${escHtml(String(v))}</span>`).join('')}</div>`;
        } catch (_) { return ''; }
    })() : '';
    return `
        <div class="character-card" style="margin-bottom:8px">
            <div class="character-card-header">
                <span class="character-name">${icon} ${escHtml(e.name)}</span>
                <div class="inline-flex">
                    <div class="dropdown-wrapper">
                        <button class="btn btn-sm" onclick="toggleEditWikiEntry(this, '${e.id}')">编辑</button>
                    </div>
                    <button class="btn btn-sm btn-danger" onclick="deleteWikiEntryConfirm('${e.id}')">删除</button>
                </div>
            </div>
            <div class="character-card-body">
                ${e.description ? `<div class="content-preview" style="max-height:200px;overflow-y:auto;font-size:0.9rem;white-space:pre-wrap">${escHtml(e.description)}</div>` : '<div style="color:var(--text-secondary);padding:6px 0">暂无描述</div>'}
                ${meta}
            </div>
        </div>
    `;
}

function switchWikiCategory(cat) {
    _currentWikiCategory = cat;
    _renderWikiTab(window._wikiEntries || []);
}

function toggleAddWikiEntry(btn) {
    const categories = _getWikiCategories();
    const catOptions = Object.keys(categories).map(k =>
        `<option value="${k}" ${k === _currentWikiCategory ? 'selected' : ''}>${categories[k]}</option>`
    ).join('');
    toggleDropdown(btn, `
        <h3 style="margin-bottom:14px;font-size:1.05rem">添加百科条目</h3>
        <div class="form-group">
            <label>类别</label>
            <select id="addWikiCat">${catOptions}</select>
        </div>
        <div class="form-group">
            <label>名称</label>
            <input type="text" id="addWikiName" placeholder="如：玄霄宗">
        </div>
        <div class="form-group">
            <label>描述</label>
            <textarea id="addWikiDesc" style="min-height:120px" placeholder="简明扼要说明其本质和剧情意义..."></textarea>
        </div>
        <div class="form-group">
            <label>额外属性（可选，JSON 格式）</label>
            <textarea id="addWikiMeta" style="min-height:60px" placeholder='{"地理坐标":"天柱峰顶","等级":"一流势力"}'></textarea>
        </div>
        <button class="btn btn-primary" onclick="addWikiEntry()" style="width:100%">添加</button>
    `, true);
}

async function addWikiEntry() {
    const category = document.getElementById('addWikiCat').value;
    const name = document.getElementById('addWikiName').value.trim();
    const description = document.getElementById('addWikiDesc').value;
    const metadata = document.getElementById('addWikiMeta').value.trim();
    if (!name) { showToast('请输入名称', 'error'); return; }
    // 校验 metadata 是否合法 JSON（如果非空）
    if (metadata) {
        try { JSON.parse(metadata); } catch (_) { showToast('额外属性不是合法的 JSON', 'error'); return; }
    }
    try {
        await API.post(`/api/novels/${currentNovelId}/wiki`, { category, name, description, metadata });
        closeAllDropdowns();
        showToast('条目已添加', 'success');
        _currentWikiCategory = category;
        await _reloadWiki();
    } catch (e) {
        showToast('添加失败: ' + e.message, 'error');
    }
}

async function toggleEditWikiEntry(btn, entryId) {
    const entry = (window._wikiEntries || []).find(e => e.id === entryId);
    if (!entry) { showToast('加载条目失败', 'error'); return; }
    const categories = _getWikiCategories();
    toggleDropdown(btn, `
        <h3 style="margin-bottom:14px;font-size:1.05rem">编辑条目</h3>
        <div class="form-group">
            <label>类别（不可修改）</label>
            <input type="text" value="${escAttr(categories[entry.category] || entry.category)}" disabled>
        </div>
        <div class="form-group">
            <label>名称</label>
            <input type="text" id="editWikiName" value="${escAttr(entry.name)}">
        </div>
        <div class="form-group">
            <label>描述</label>
            <textarea id="editWikiDesc" style="min-height:140px">${escHtml(entry.description || '')}</textarea>
        </div>
        <div class="form-group">
            <label>额外属性（JSON 格式）</label>
            <textarea id="editWikiMeta" style="min-height:60px">${escHtml(entry.metadata || '')}</textarea>
        </div>
        <button class="btn btn-primary" onclick="saveWikiEntry('${entry.id}')" style="width:100%">保存</button>
    `, true);
}

async function saveWikiEntry(entryId) {
    const name = document.getElementById('editWikiName').value.trim();
    const description = document.getElementById('editWikiDesc').value;
    const metadata = document.getElementById('editWikiMeta').value.trim();
    if (!name) { showToast('名称不能为空', 'error'); return; }
    if (metadata) {
        try { JSON.parse(metadata); } catch (_) { showToast('额外属性不是合法的 JSON', 'error'); return; }
    }
    try {
        await API.put(`/api/wiki/${entryId}`, { name, description, metadata });
        closeAllDropdowns();
        showToast('条目已更新', 'success');
        await _reloadWiki();
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

async function deleteWikiEntryConfirm(entryId) {
    if (!await confirmDialog('确定要删除这个百科条目吗？', { icon: 'danger', confirmText: '删除', danger: true })) return;
    try {
        await API.del(`/api/wiki/${entryId}`);
        showToast('条目已删除', 'success');
        await _reloadWiki();
    } catch (e) {
        showToast('删除失败: ' + e.message, 'error');
    }
}

async function _reloadWiki() {
    try {
        const { entries } = await API.get(`/api/novels/${currentNovelId}/wiki`);
        _renderWikiTab(entries || []);
    } catch (e) {
        showToast('刷新百科失败: ' + e.message, 'error');
    }
}

function toggleWikiGenDropdown(btn) {
    toggleDropdown(btn, `
        <h3 style="margin-bottom:8px;font-size:1.05rem">${ic('sparkles', 'icon-md')} AI 生成百科条目</h3>
        <p style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:12px">AI 将根据大纲和世界观自动生成地名、组织、物品、事件等百科条目，供创作时参考。</p>
        <div class="form-group">
            <label>自定义提示词（可选）</label>
            <textarea id="wikiCustomPrompt" rows="4" placeholder="例如：需要一套完整的货币体系；增加三大势力的详细介绍；生成一个关键遗迹的背景..." style="width:100%;resize:vertical"></textarea>
        </div>
        <div class="inline-flex" style="justify-content:flex-end">
            <button class="btn btn-primary" onclick="aiGenerateWikiEntries()">${ic('sparkles')} 开始生成</button>
        </div>
    `, true);
}

async function aiGenerateWikiEntries() {
    const preview = document.getElementById('wikiGenPreview');
    if (!preview) return;
    const customPrompt = (document.getElementById('wikiCustomPrompt')?.value || '').trim();
    closeAllDropdowns();
    preview.style.display = 'block';
    preview.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-secondary)">${ic('sparkles', 'icon-sm')} AI 正在根据大纲和世界观生成百科条目...</div>`;
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/wiki/ai-generate`, { custom_prompt: customPrompt });
        const entries = data.entries || [];
        if (!entries.length) {
            preview.innerHTML = '<div style="padding:16px;color:var(--text-secondary)">AI 未生成新条目（可能已有全部条目，或大纲信息不足）</div>';
            return;
        }
        window._genWikiEntries = entries;
        const categories = _getWikiCategories();
        preview.innerHTML = `
            <div style="padding:12px;background:var(--accent-light);border:1px solid var(--accent);border-radius:var(--radius-sm);margin-bottom:8px">
                <strong>${ic('sparkles', 'icon-sm')} AI 生成了 ${entries.length} 个条目</strong>
                <span style="font-size:0.8rem;color:var(--text-secondary);margin-left:8px">勾选要添加的条目，点击「应用选中」</span>
            </div>
            ${entries.map((e, i) => `
                <div style="padding:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:6px">
                    <div style="display:flex;align-items:flex-start;gap:8px">
                        <input type="checkbox" id="genWikiChk_${i}" checked style="margin-top:4px;width:auto;flex-shrink:0">
                        <div style="flex:1;min-width:0">
                            <div style="font-weight:700;color:var(--accent)">
                                <span style="margin-right:6px">${ic(WIKI_CATEGORY_ICONS[e.category] || 'pin', 'icon-sm')} ${escHtml(categories[e.category] || e.category)}</span>
                                ${escHtml(e.name)}
                            </div>
                            <div style="font-size:0.85rem;color:var(--text-secondary);white-space:pre-wrap;margin-top:4px">${escHtml(e.description)}</div>
                        </div>
                    </div>
                </div>
            `).join('')}
            <div class="inline-flex" style="margin-top:8px">
                <button class="btn btn-primary btn-sm" onclick="applyGeneratedWikiEntries()">${ic('check')} 应用选中</button>
                <button class="btn btn-sm" onclick="applyGeneratedWikiEntries(true)">${ic('check')} 应用全部</button>
                <button class="btn btn-sm" onclick="document.getElementById('wikiGenPreview').style.display='none'">取消</button>
            </div>
        `;
    } catch (e) {
        preview.innerHTML = `<div style="padding:16px;color:var(--danger)">生成失败: ${escHtml(e.message)}</div>`;
    }
}

async function applyGeneratedWikiEntries(all = false) {
    const entries = window._genWikiEntries || [];
    if (!entries.length) { showToast('无条目可应用', 'error'); return; }
    const selected = all ? entries : entries.filter((_, i) => document.getElementById('genWikiChk_' + i)?.checked);
    if (!selected.length) { showToast('请至少选择一个条目', 'error'); return; }
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/wiki/apply-generated`, { entries: selected });
        showToast(`已添加 ${data.count} 个条目`, 'success');
        const preview = document.getElementById('wikiGenPreview');
        if (preview) preview.style.display = 'none';
        await _reloadWiki();
    } catch (e) {
        showToast('应用失败: ' + e.message, 'error');
    }
}

// ==================== AI 生成画像 & 从章节提取 ====================

async function aiGenerateCharacters(btn) {
    const preview = document.getElementById('charGenPreview');
    if (!preview) return;
    const customPrompt = (document.getElementById('charCustomPrompt')?.value || '').trim();
    closeAllDropdowns();
    preview.style.display = 'block';
    preview.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-secondary)">${ic('sparkles', 'icon-sm')} AI 正在根据大纲和世界观生成人物画像...</div>`;
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/characters/ai-generate`, { custom_prompt: customPrompt });
        if (!data.characters || !data.characters.length) {
            preview.innerHTML = '<div style="padding:16px;color:var(--text-secondary)">AI 未生成新角色（可能已有全部角色，或大纲信息不足）</div>';
            return;
        }
        // 渲染预览，每个角色可勾选
        window._genCharacters = data.characters;
        preview.innerHTML = `
            <div style="padding:12px;background:var(--accent-light);border:1px solid var(--accent);border-radius:var(--radius-sm);margin-bottom:8px">
                <strong>${ic('sparkles', 'icon-sm')} AI 生成了 ${data.characters.length} 个角色</strong>
                <span style="font-size:0.8rem;color:var(--text-secondary);margin-left:8px">勾选要添加的角色，点击「应用选中」</span>
            </div>
            ${data.characters.map((c, i) => `
                <div style="padding:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:6px">
                    <div style="display:flex;align-items:flex-start;gap:8px">
                        <input type="checkbox" id="genChk_${i}" checked style="margin-top:4px;width:auto;flex-shrink:0">
                        <div style="flex:1;min-width:0">
                            <div style="font-weight:700;color:var(--accent)">${escHtml(c.name)}</div>
                            <div style="font-size:0.85rem;color:var(--text-secondary);white-space:pre-wrap;margin-top:4px">${escHtml(c.profile)}</div>
                        </div>
                    </div>
                </div>
            `).join('')}
            <div class="inline-flex" style="margin-top:8px">
                <button class="btn btn-primary btn-sm" onclick="applyGeneratedCharacters()">${ic('check')} 应用选中</button>
                <button class="btn btn-sm" onclick="applyGeneratedCharacters(true)">${ic('check')} 应用全部</button>
                <button class="btn btn-sm" onclick="document.getElementById('charGenPreview').style.display='none'">取消</button>
            </div>
        `;
    } catch (e) {
        preview.innerHTML = `<div style="padding:16px;color:var(--danger)">生成失败: ${escHtml(e.message)}</div>`;
    }
}

async function applyGeneratedCharacters(all = false) {
    const chars = window._genCharacters || [];
    if (!chars.length) { showToast('无角色可应用', 'error'); return; }
    const selected = all ? chars : chars.filter((_, i) => document.getElementById('genChk_' + i)?.checked);
    if (!selected.length) { showToast('请至少选择一个角色', 'error'); return; }
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/characters/apply-generated`, { characters: selected });
        showToast(`已添加 ${data.count} 个角色`, 'success');
        document.getElementById('charGenPreview').style.display = 'none';
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('应用失败: ' + e.message, 'error');
    }
}

async function extractFromChapters(btn) {
    // 优先使用角色Tab的预览区，不存在则用关系Tab的
    let preview = document.getElementById('charGenPreview');
    if (!preview || preview.style.display === 'none' || !document.getElementById('charGenPreview')) {
        preview = document.getElementById('relGenPreview') || document.getElementById('charGenPreview');
    }
    if (!preview) return;
    preview.style.display = 'block';
    preview.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-secondary)">${ic('book-open', 'icon-sm')} AI 正在从已写章节中提取角色和关系...</div>`;
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/characters/extract-from-chapters`, {});
        const chars = data.characters || [];
        const rels = data.relationships || [];
        if (!chars.length && !rels.length) {
            preview.innerHTML = '<div style="padding:16px;color:var(--text-secondary)">未提取到角色或关系</div>';
            return;
        }
        window._extractedChars = chars;
        window._extractedRels = rels;
        preview.innerHTML = `
            <div style="padding:12px;background:var(--accent-light);border:1px solid var(--accent);border-radius:var(--radius-sm);margin-bottom:8px">
                <strong>${ic('book-open', 'icon-sm')} 从 ${data.chapter_count} 章中提取</strong>
                <span style="margin-left:8px">${chars.length} 个角色 · ${rels.length} 条关系</span>
            </div>
            ${chars.length ? `
                <div style="font-weight:600;margin:8px 0 4px">角色（勾选要添加的）</div>
                ${chars.map((c, i) => `
                    <div style="padding:10px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:4px">
                        <div style="display:flex;align-items:flex-start;gap:8px">
                            <input type="checkbox" id="extChk_${i}" ${c.is_existing ? 'disabled' : 'checked'} style="margin-top:4px;width:auto;flex-shrink:0" ${c.is_existing ? '' : ''}>
                            <div style="flex:1;min-width:0">
                                <div style="font-weight:600;color:var(--accent)">${escHtml(c.name)} ${c.is_existing ? '<span class="badge" style="background:#d1fae5;color:#065f46;font-size:0.7rem">已有</span>' : ''}</div>
                                <div style="font-size:0.82rem;color:var(--text-secondary);margin-top:2px">${escHtml(c.profile)}</div>
                            </div>
                        </div>
                    </div>
                `).join('')}
            ` : ''}
            ${rels.length ? `
                <div style="font-weight:600;margin:12px 0 4px">关系（勾选要添加的）</div>
                ${rels.map((r, i) => `
                    <div style="padding:10px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:4px">
                        <div style="display:flex;align-items:flex-start;gap:8px">
                            <input type="checkbox" id="extRelChk_${i}" checked style="margin-top:4px;width:auto;flex-shrink:0">
                            <div style="flex:1;min-width:0">
                                <div style="font-weight:600">${escHtml(r.character_a)} <span style="color:var(--accent)">${escHtml(r.relation_type)}</span> ${escHtml(r.character_b)}</div>
                                <div style="font-size:0.82rem;color:var(--text-secondary);margin-top:2px">${escHtml(r.description)}</div>
                            </div>
                        </div>
                    </div>
                `).join('')}
            ` : ''}
            <div class="inline-flex" style="margin-top:8px">
                <button class="btn btn-primary btn-sm" onclick="applyExtractedAll()">${ic('check')} 应用选中</button>
                <button class="btn btn-sm" onclick="document.getElementById('charGenPreview').style.display='none'">取消</button>
            </div>
        `;
    } catch (e) {
        preview.innerHTML = `<div style="padding:16px;color:var(--danger)">提取失败: ${escHtml(e.message)}</div>`;
    }
}

async function applyExtractedAll() {
    const chars = window._extractedChars || [];
    const rels = window._extractedRels || [];
    // 选中的角色（排除已有和未勾选的）
    const selectedChars = chars.filter((c, i) => !c.is_existing && document.getElementById('extChk_' + i)?.checked);
    const selectedRels = rels.filter((_, i) => document.getElementById('extRelChk_' + i)?.checked);
    try {
        let charCount = 0, relCount = 0;
        if (selectedChars.length) {
            const data = await API.post(`/api/novels/${currentNovelId}/characters/apply-generated`, { characters: selectedChars });
            charCount = data.count;
        }
        if (selectedRels.length) {
            const data = await API.post(`/api/novels/${currentNovelId}/relationships/apply-extracted`, { relationships: selectedRels });
            relCount = data.count;
        }
        showToast(`已添加 ${charCount} 个角色、${relCount} 条关系`, 'success');
        const p1 = document.getElementById('charGenPreview');
        const p2 = document.getElementById('relGenPreview');
        if (p1) p1.style.display = 'none';
        if (p2) p2.style.display = 'none';
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('应用失败: ' + e.message, 'error');
    }
}

async function aiOptimizeCharacter(charId) {
    const el = document.getElementById('charProfile_' + charId);
    if (el) el.innerHTML = `<div style="color:var(--text-secondary);padding:12px">${ic('sparkles', 'icon-sm')} AI 优化中...</div>`;
    try {
        const { character } = await API.post(`/api/novels/${currentNovelId}/characters/${charId}/ai-optimize`, {});
        showToast(`${character.name} 画像已优化`, 'success');
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('优化失败: ' + e.message, 'error');
        if (el) el.innerHTML = '<div style="color:var(--danger);padding:12px">优化失败</div>';
    }
}

async function aiOptimizeAllCharacters() {
    showToast('正在优化全部人物画像...', 'info');
    try {
        const { characters } = await API.post(`/api/novels/${currentNovelId}/characters/ai-optimize`, {});
        const errors = characters.filter(c => c.error);
        if (errors.length) showToast(`${characters.length - errors.length} 人优化成功，${errors.length} 人失败`, 'warning');
        else showToast('全部人物画像优化完成', 'success');
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('优化失败: ' + e.message, 'error');
    }
}

// ==================== AI 生成：带自定义提示词的弹窗 ====================

function toggleWorldGenDropdown(btn) {
    toggleDropdown(btn, `
        <h3 style="margin-bottom:8px;font-size:1.05rem">${ic('sparkles', 'icon-md')} AI 优化世界观</h3>
        <p style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:12px">AI 将根据大纲和现有设定构建或优化世界观，涵盖时代背景、社会结构、文化风俗、核心体系、地理环境和历史事件。</p>
        <div class="form-group">
            <label>自定义提示词（可选）</label>
            <textarea id="worldCustomPrompt" rows="4" placeholder="例如：以蒸汽朋克为基调，科技与魔法并存；社会由五大商业家族控制；主要舞台是一座建在巨大齿轮上的城市..." style="width:100%;resize:vertical"></textarea>
        </div>
        <div class="inline-flex" style="justify-content:flex-end">
            <button class="btn btn-primary" onclick="aiOptimizeWorld()">${ic('sparkles')} 开始生成</button>
        </div>
    `, true);
}

async function aiOptimizeWorld() {
    const customPrompt = (document.getElementById('worldCustomPrompt')?.value || '').trim();
    closeAllDropdowns();
    const ta = document.getElementById('novelWorldBuilding');
    if (ta) ta.placeholder = 'AI 优化中...';
    try {
        const { world_building } = await API.post(`/api/novels/${currentNovelId}/ai-optimize-world`, { custom_prompt: customPrompt });
        if (ta) ta.value = world_building;
        showToast('世界观已优化', 'success');
    } catch (e) {
        showToast('优化失败: ' + e.message, 'error');
        if (ta) ta.placeholder = '输入世界观设定...';
    }
}

function toggleCharGenDropdown(btn) {
    toggleDropdown(btn, `
        <h3 style="margin-bottom:8px;font-size:1.05rem">${ic('sparkles', 'icon-md')} AI 生成人物画像</h3>
        <p style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:12px">AI 将根据大纲和世界观自动设计 3-6 个核心角色，包含外貌、性格、背景、动机和能力。</p>
        <div class="form-group">
            <label>自定义提示词（可选）</label>
            <textarea id="charCustomPrompt" rows="4" placeholder="例如：主角是反英雄角色，亦正亦邪；需要一个复杂的女性反派；增加一个亦敌亦友的导师角色..." style="width:100%;resize:vertical"></textarea>
        </div>
        <div class="inline-flex" style="justify-content:flex-end">
            <button class="btn btn-primary" onclick="aiGenerateCharacters()">${ic('sparkles')} 开始生成</button>
        </div>
    `, true);
}

async function aiGenerateOutline(evt) {
    const ta = document.getElementById('novelOutline');
    const btn = evt?.target || event?.target;
    if (btn) { btn.disabled = true; btn.innerHTML = `${ic('loader')} AI 生成中...`; }
    if (ta) ta.placeholder = 'AI 正在根据小说设定生成大纲...';
    try {
        const { outline } = await API.post(`/api/novels/${currentNovelId}/ai-generate-outline`, {});
        if (ta) ta.value = outline;
        showToast('大纲已生成', 'success');
    } catch (e) {
        showToast('生成失败: ' + e.message, 'error');
        if (ta) ta.placeholder = '输入大纲内容...';
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = `${ic('sparkles')} AI 生成大纲`; }
    }
}

async function aiRefineRelationships() {
    switchDetailTab('relationships');
    const list = document.getElementById('relationshipList');
    if (list) list.innerHTML = `<div class="empty-state"><p>${ic('bot', 'icon-sm')} AI 正在分析人物关系...</p></div>`;
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/relationships/ai-refine`, {});
        const rels = data.relationships || [];
        if (list) {
            if (rels.length > 0) {
                list.innerHTML = `
                    <div style="margin-bottom:8px;color:var(--text-secondary);font-size:0.85rem">
                        AI 分析了 ${data.character_count} 个角色，生成 ${rels.length} 条关系
                    </div>
                    <div class="form-group">
                        <button class="btn btn-primary btn-sm" onclick="applyAiRelationships(${escAttr(JSON.stringify(rels))})">${ic('check')} 全部应用</button>
                    </div>
                    ${rels.map(r => `
                        <div style="padding:10px;margin:6px 0;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm)">
                            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                                <strong>${escHtml(r.character_a)}</strong>
                                <span style="color:var(--accent)">↔</span>
                                <strong>${escHtml(r.character_b)}</strong>
                                <span style="padding:2px 8px;background:var(--accent-light);border-radius:10px;font-size:0.8rem">${escHtml(r.relation_type)}</span>
                            </div>
                            <div style="margin-top:4px;color:var(--text-secondary);font-size:0.9rem">${escHtml(r.description)}</div>
                        </div>
                    `).join('')}
                    <p style="margin-top:12px;font-size:0.82rem;color:var(--text-secondary)">
                        点击「全部应用」将覆盖现有关系。刷新页面可查看原始列表。
                    </p>
                `;
            } else {
                list.innerHTML = `
                    <div style="margin-bottom:8px;color:var(--text-secondary);font-size:0.85rem">
                        AI 分析结果（${data.character_count} 个角色）
                    </div>
                    <div class="content-preview" style="white-space:pre-wrap;font-family:var(--font);max-height:500px;overflow-y:auto">
                        ${escHtml(data.suggestions)}
                    </div>
                `;
            }
        }
    } catch (e) {
        if (list) list.innerHTML = `<div class="empty-state"><p>分析失败: ${escHtml(e.message)}</p></div>`;
    }
}

async function applyAiRelationships(rels) {
    try {
        // 先删除现有关系再逐条添加
        const resp = await API.get(`/api/novels/${currentNovelId}/relationships`);
        const existing = resp.relationships || resp || [];
        for (const r of existing) {
            await API.del(`/api/relationships/${r.id}`);
        }
        for (const r of rels) {
            await API.post(`/api/novels/${currentNovelId}/relationships`, {
                character_a: r.character_a, character_b: r.character_b,
                relation_type: r.relation_type, description: r.description,
            });
        }
        showToast(`已应用 ${rels.length} 条关系`, 'success');
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('应用失败: ' + e.message, 'error');
    }
}

// ==================== Suggestions ====================

async function generateSuggestions() {
    switchDetailTab('suggestions');
    const content = document.getElementById('suggestionsContent');
    content.innerHTML = `<div class="empty-state"><p>${ic('brain', 'icon-sm')} AI 正在分析你的小说...</p></div>`;
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/suggestions`, {});
        content.innerHTML = `
            <div style="margin-bottom:8px;color:var(--text-secondary);font-size:0.85rem">
                已分析 ${data.chapter_count} 章 · ${data.relationship_count} 条人物关系
            </div>
            <div class="content-preview" style="white-space:pre-wrap;font-family:var(--font)">${escHtml(data.suggestions)}</div>
        `;
    } catch (e) {
        content.innerHTML = `<div class="empty-state"><p>生成失败: ${escHtml(e.message)}</p></div>`;
    }
}

function toggleExportDropdown(btn) {
    toggleDropdown(btn, `
        <h3 style="margin-bottom:14px;font-size:1.05rem">${ic('download', 'icon-md')} 导出小说</h3>
        <div class="form-group">
            <label>导出模式</label>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                <button class="option-btn active" data-mode="content" onclick="document.querySelectorAll('[data-mode]').forEach(b=>b.classList.remove('active'));this.classList.add('active')">${ic('book-open')} 仅正文内容</button>
                <button class="option-btn" data-mode="full" onclick="document.querySelectorAll('[data-mode]').forEach(b=>b.classList.remove('active'));this.classList.add('active')">${ic('clipboard')} 完整导出（含设定）</button>
            </div>
            <p style="font-size:0.78rem;color:var(--text-secondary);margin-top:6px" id="exportModeHint">仅正文：章节间用分隔线标注，便于小说软件分章导入</p>
        </div>
        <div class="form-group">
            <label>导出格式</label>
            <select id="exportFormat">
                <option value="txt">TXT 文本（推荐小说软件导入）</option>
                <option value="md">Markdown</option>
                <option value="html">HTML 网页</option>
            </select>
        </div>
        <div class="form-group">
            <label>导出路径（留空使用默认路径）</label>
            <input type="text" id="exportPath" placeholder="默认: exports/ 目录">
        </div>
        <div class="inline-flex" style="justify-content:flex-end;gap:8px">
            <button class="btn btn-primary" onclick="exportNovel()">${ic('upload')} 导出到服务器</button>
            <button class="btn btn-primary" onclick="downloadNovel()">${ic('download')} 直接下载</button>
        </div>
    `, true);
    // 动态更新提示
    setTimeout(() => {
        document.querySelectorAll('[data-mode]').forEach(b => {
            b.addEventListener('click', function() {
                const hint = document.getElementById('exportModeHint');
                if (this.dataset.mode === 'content') {
                    hint.textContent = '仅正文：章节间用分隔线标注，便于小说软件分章导入';
                } else {
                    hint.textContent = '完整导出：包含大纲、世界观、人物画像 + 正文';
                }
            });
        });
    }, 0);
}

async function exportNovel() {
    try {
        const format = document.getElementById('exportFormat').value;
        const path = document.getElementById('exportPath').value;
        const mode = document.querySelector('[data-mode].active')?.dataset.mode || 'content';
        const include_meta = mode === 'full';
        const data = await API.post(`/api/novels/${currentNovelId}/export`, { format, path, include_meta });
        closeAllDropdowns();
        showToast(`导出成功: ${data.filepath}`, 'success');
    } catch (e) {
        showToast('导出失败: ' + e.message, 'error');
    }
}

async function downloadNovel() {
    const format = document.getElementById('exportFormat').value;
    const mode = document.querySelector('[data-mode].active')?.dataset.mode || 'content';
    const include_meta = mode === 'full' ? 'true' : 'false';
    try {
        const r = await fetch(`/api/novels/${currentNovelId}/download/${format}?include_meta=${include_meta}`, {
            headers: authToken ? { 'Authorization': 'Bearer ' + authToken } : {},
        });
        if (!r.ok) throw new Error('下载失败: ' + r.status);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const ext = format === 'md' ? 'md' : format;
        a.download = `novel.${ext}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (e) {
        showToast('下载失败: ' + e.message, 'error');
    }
    closeAllDropdowns();
}

// ==================== AI 配图下拉面板 ====================

function toggleImageGenDropdown(btn) {
    const html = `
        <h3 style="margin-bottom:14px;font-size:1.05rem">${ic('palette', 'icon-md')} AI 配图</h3>
        <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:12px">
            生成小说封面或场景图。角色立绘请在「人物画像」Tab 中生成。需先在设置中配置图片生成 API。
        </p>
        <div class="form-group">
            <button class="btn btn-primary" style="width:100%;margin-bottom:8px" onclick="generateNovelCover(this)">${ic('palette')} 生成小说封面</button>
            <button class="btn" style="width:100%" onclick="generateSceneImage(this)">${ic('image')} 生成场景图</button>
        </div>
        <div id="imageGenResult" style="margin-top:10px"></div>
    `;
    toggleDropdown(btn, html, true);
}

async function generateSceneImage(btn) {
    if (btn) { btn.disabled = true; btn.innerHTML = `${ic('palette')} 生成中...`; }
    const resultEl = document.getElementById('imageGenResult');
    if (resultEl) resultEl.innerHTML = `<div style="padding:12px;color:var(--text-secondary);text-align:center">${ic('image', 'icon-sm')} 正在生成场景图...</div>`;
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/generate-image`, {
            type: 'scene',
            name: '',
            description: '',
        });
        if (data.error) {
            showToast(data.error, 'error');
            if (resultEl) resultEl.innerHTML = `<div style="padding:12px;color:var(--danger)">${escHtml(data.error)}</div>`;
            return;
        }
        if (resultEl) {
            resultEl.innerHTML = `
                <div style="text-align:center">
                    <img src="${escAttr(data.image_url)}" alt="场景图" style="max-width:100%;max-height:300px;border-radius:var(--radius-sm);border:1px solid var(--border)">
                    <div style="margin-top:8px"><a href="${escAttr(safeUrl(data.image_url))}" target="_blank" class="btn btn-sm">在新窗口打开</a></div>
                </div>
            `;
        }
        showToast('场景图生成成功', 'success');
    } catch (e) {
        showToast('场景图生成失败: ' + e.message, 'error');
        if (resultEl) resultEl.innerHTML = `<div style="padding:12px;color:var(--danger)">${escHtml(e.message)}</div>`;
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = `${ic('image')} 生成场景图`; }
    }
}

// ==================== 文档导入分析 ====================

function toggleImportAnalyzePanel(btn) {
    const html = `
        <h3 style="margin-bottom:14px;font-size:1.05rem">${ic('file-text', 'icon-md')} 导入文档分析</h3>
        <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:12px">
            上传 .txt / .md 文件或直接粘贴文本，AI 将分析并提取可借鉴的素材。分析后可应用到小说设定。
        </p>
        <div class="form-group">
            <label>分析类型</label>
            <select id="analyzeDocType">
                <option value="reference">参考文风（提取写作风格、叙事手法）</option>
                <option value="worldbuilding">世界观提取（地理/势力/物品/事件）</option>
                <option value="character">角色提取（人物特征和关系）</option>
            </select>
        </div>
        <div class="form-group">
            <label>上传文件（.txt / .md）</label>
            <input type="file" id="analyzeDocFile" accept=".txt,.md" onchange="loadAnalyzeFile(this)">
        </div>
        <div class="form-group">
            <label>或直接粘贴文本</label>
            <textarea id="analyzeDocContent" style="min-height:120px;font-size:0.85rem" placeholder="将文档内容粘贴到此处..."></textarea>
        </div>
        <button class="btn btn-primary" onclick="analyzeDoc()" style="width:100%">${ic('bot')} 开始分析</button>
        <div id="analyzeDocResult" style="margin-top:12px"></div>
    `;
    toggleDropdown(btn, html, true);
}

function loadAnalyzeFile(input) {
    const file = input.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
        const ta = document.getElementById('analyzeDocContent');
        if (ta) ta.value = e.target.result;
    };
    reader.readAsText(file, 'utf-8');
}

async function analyzeDoc() {
    const docType = document.getElementById('analyzeDocType').value;
    const content = document.getElementById('analyzeDocContent').value;
    if (!content || !content.trim()) { showToast('请输入或上传文档内容', 'error'); return; }

    const btn = document.querySelector('.dropdown-panel button[onclick*="analyzeDoc"]');
    if (btn) { btn.disabled = true; btn.innerHTML = `${ic('loader')} 分析中...`; }
    const resultEl = document.getElementById('analyzeDocResult');
    if (resultEl) resultEl.innerHTML = `<div style="padding:12px;color:var(--text-secondary);text-align:center">${ic('bot', 'icon-sm')} AI 正在分析文档...</div>`;

    try {
        const data = await API.post(`/api/novels/${currentNovelId}/analyze-document`, {
            content, type: docType,
        });
        if (data.error) {
            if (resultEl) resultEl.innerHTML = `<div style="padding:12px;color:var(--danger)">${escHtml(data.error)}</div>`;
            return;
        }
        window._lastDocAnalysis = data;
        const typeLabel = {
            reference: '参考文风',
            worldbuilding: '世界观提取',
            character: '角色提取',
        }[data.type] || '分析';

        let applyBtn = '';
        if (data.type === 'reference') {
            applyBtn = `<button class="btn btn-sm btn-primary" onclick="applyDocAnalysis('style')">应用到文风参考</button>`;
        } else if (data.type === 'worldbuilding') {
            applyBtn = `<button class="btn btn-sm btn-primary" onclick="applyDocAnalysis('world')">应用到世界观</button>`;
        } else if (data.type === 'character') {
            applyBtn = `<button class="btn btn-sm btn-primary" onclick="applyDocAnalysis('character')">应用到人物画像</button>`;
        }

        if (resultEl) {
            resultEl.innerHTML = `
                <div style="padding:10px;background:var(--accent-light);border:1px solid var(--accent);border-radius:var(--radius-sm);margin-bottom:8px">
                    <strong>${ic('check', 'icon-sm')} ${typeLabel}完成</strong>
                    <span style="font-size:0.8rem;color:var(--text-secondary);margin-left:8px">${(data.suggestions || []).length} 条建议</span>
                </div>
                <div style="padding:10px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm);max-height:240px;overflow-y:auto;font-size:0.85rem;line-height:1.6;white-space:pre-wrap;margin-bottom:8px">${escHtml(data.analysis || '（无分析内容）')}</div>
                ${(data.suggestions && data.suggestions.length) ? `
                    <div style="font-size:0.85rem;font-weight:600;margin-bottom:4px">${ic('lightbulb', 'icon-sm')} 建议：</div>
                    <ul style="margin:0 0 8px 18px;padding:0;font-size:0.82rem;color:var(--text-secondary);line-height:1.7">
                        ${data.suggestions.map(s => `<li>${escHtml(s)}</li>`).join('')}
                    </ul>
                ` : ''}
                <div class="inline-flex" style="gap:6px">
                    ${applyBtn}
                    <button class="btn btn-sm" onclick="copyDocAnalysis()">${ic('clipboard')} 复制分析</button>
                </div>
            `;
        }
        showToast('分析完成', 'success');
    } catch (e) {
        if (resultEl) resultEl.innerHTML = `<div style="padding:12px;color:var(--danger)">${escHtml(e.message)}</div>`;
        showToast('分析失败: ' + e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = `${ic('bot')} 开始分析`; }
    }
}

async function applyDocAnalysis(target) {
    const data = window._lastDocAnalysis;
    if (!data || !data.analysis) { showToast('无可应用的分析结果', 'error'); return; }
    // 拼接分析正文 + 建议
    const text = data.analysis + (data.suggestions && data.suggestions.length
        ? '\n\n## 建议\n' + data.suggestions.map(s => '- ' + s).join('\n')
        : '');
    try {
        if (target === 'style') {
            // 追加到文风参考字段
            const ta = document.getElementById('novelStyleReference');
            if (ta) {
                ta.value = (ta.value ? ta.value + '\n\n' : '') + text;
                await API.put(`/api/novels/${currentNovelId}`, { style_reference: ta.value });
            } else {
                await API.put(`/api/novels/${currentNovelId}`, { style_reference: text });
            }
            showToast('已应用到文风参考', 'success');
        } else if (target === 'world') {
            const ta = document.getElementById('novelWorldBuilding');
            if (ta) {
                ta.value = (ta.value ? ta.value + '\n\n' : '') + text;
                await API.put(`/api/novels/${currentNovelId}`, { world_building: ta.value });
            } else {
                await API.put(`/api/novels/${currentNovelId}`, { world_building: text });
            }
            showToast('已应用到世界观设定', 'success');
        } else if (target === 'character') {
            // 创建一个新角色，名字为"参考角色"，画像为分析结果
            await API.post(`/api/novels/${currentNovelId}/characters/apply-generated`, {
                characters: [{ name: '参考角色素材', profile: text }],
            });
            showToast('已作为参考素材添加到人物画像', 'success');
        }
        closeAllDropdowns();
    } catch (e) {
        showToast('应用失败: ' + e.message, 'error');
    }
}

function copyDocAnalysis() {
    const data = window._lastDocAnalysis;
    if (!data) return;
    const text = data.analysis + (data.suggestions && data.suggestions.length
        ? '\n\n## 建议\n' + data.suggestions.map(s => '- ' + s).join('\n')
        : '');
    navigator.clipboard.writeText(text).then(() => showToast('已复制', 'success')).catch(() => showToast('复制失败', 'error'));
}

// ==================== Chapter Read Page ====================
let _readChapterIndex = 0;
let _readChapterList = [];

async function renderChapterReadPage(main) {
    main.className = 'main-area';
    main.innerHTML = `<div class="empty-state"><p>加载中...</p></div>`;
    try {
        const { chapters } = await API.get(`/api/novels/${currentNovelId}/chapters`);
        _readChapterList = chapters;
        if (!chapters.length) {
            main.innerHTML = `<div class="empty-state">${ic('book-open', 'icon-lg')}<p>暂无章节可阅读</p><button class="btn" style="margin-top:12px" onclick="navigate('novel-detail', {novelId: '${currentNovelId}'})">返回</button></div>`;
            return;
        }
        // 找到当前章节索引
        _readChapterIndex = chapters.findIndex(ch => ch.id === currentChapterId);
        if (_readChapterIndex < 0) _readChapterIndex = 0;
        await _renderReadContent(main);
    } catch (e) {
        main.innerHTML = `<div class="empty-state"><p>加载失败: ${escHtml(e.message)}</p></div>`;
    }
}

async function _renderReadContent(main) {
    const chapters = _readChapterList;
    const ch = chapters[_readChapterIndex];
    if (!ch) return;
    const novel = await API.get(`/api/novels/${currentNovelId}`);
    const prev = _readChapterIndex > 0 ? chapters[_readChapterIndex - 1] : null;
    const next = _readChapterIndex < chapters.length - 1 ? chapters[_readChapterIndex + 1] : null;

    main.innerHTML = `
        <div class="page-header">
            <div class="inline-flex">
                <button class="btn btn-sm" onclick="navigate('novel-detail', {novelId: '${currentNovelId}'})">← 返回</button>
                <h2 style="font-size:1.2rem">${escHtml(novel.title || '未命名')} · ${_readChapterIndex + 1}/${chapters.length}</h2>
            </div>
            <div class="inline-flex">
                <button class="btn btn-sm" onclick="navigate('chapter-edit', {chapterId: '${ch.id}', novelId: '${currentNovelId}'})">${ic('pencil')} 编辑</button>
                <button class="btn btn-sm" onclick="copyChapterText('${ch.id}')">${ic('clipboard')} 复制</button>
            </div>
        </div>
        <div class="card" style="max-width:720px;margin:0 auto">
            <h3 style="font-family:var(--font-serif);font-size:1.4rem;text-align:center;margin-bottom:4px;color:var(--accent)">${escHtml(ch.title)}</h3>
            <div style="text-align:center;font-size:0.8rem;color:var(--text-secondary);margin-bottom:20px;padding-bottom:12px;border-bottom:1px solid var(--border)">
                ${ch.words_count} 字
            </div>
            <div class="content-preview" style="border:none;padding:0;min-height:auto;font-size:1.05rem;line-height:2.1">${escHtml(ch.content || '（无内容）')}</div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;max-width:720px;margin-left:auto;margin-right:auto">
            ${prev ? `<button class="btn" onclick="readNavigate(-1)">← 上一章</button>` : '<span></span>'}
            <span style="font-size:0.85rem;color:var(--text-secondary)">${_readChapterIndex + 1} / ${chapters.length}</span>
            ${next ? `<button class="btn" onclick="readNavigate(1)">下一章 →</button>` : '<span></span>'}
        </div>
    `;
    window.scrollTo(0, 0);
}

function readNavigate(direction) {
    const newIndex = _readChapterIndex + direction;
    if (newIndex < 0 || newIndex >= _readChapterList.length) return;
    _readChapterIndex = newIndex;
    currentChapterId = _readChapterList[newIndex].id;
    const main = document.getElementById('mainArea');
    _renderReadContent(main);
}

async function copyChapterText(chapterId) {
    try {
        const ch = _readChapterList.find(c => c.id === chapterId);
        if (!ch) return;
        const text = `${ch.title}\n\n${ch.content || ''}`;
        await navigator.clipboard.writeText(text);
        showToast('已复制到剪贴板', 'success');
    } catch (e) {
        showToast('复制失败: ' + e.message, 'error');
    }
}

// ==================== Batch Generate Page (连续创作配置页) ====================
async function renderBatchGeneratePage(main) {
    main.className = 'main-area';
    const novelId = currentNovelId;
    if (!novelId) { navigate('novels'); return; }

    let novel = null;
    let providers = [];
    try {
        const [novelData, provData] = await Promise.all([
            API.get(`/api/novels/${novelId}`).then(d => d.novel),
            API.get('/api/providers').then(d => d.providers || []).catch(() => []),
        ]);
        novel = novelData;
        providers = provData;
    } catch (e) {
        main.innerHTML = `<div class="error-box">${ic('x-circle')} 加载失败: ${escHtml(e.message)}</div>`;
        return;
    }

    // 获取已有章节数，用于显示起始章节号
    let existingCount = 0;
    try {
        const { chapters } = await API.get(`/api/novels/${novelId}/chapters`);
        existingCount = chapters ? chapters.length : 0;
    } catch (e) { /* ignore */ }

    const defaultCount = novel.summary_chapters_count || 3;
    const providerOptions = ['<option value="">使用活跃供应商</option>']
        .concat(providers.map(p => `<option value="${p.id}" ${p.is_active ? 'selected' : ''}>${escHtml(p.name)} (${escHtml(p.model)})</option>`))
        .join('');

    // 保存已有章节数供 syncChapterList 使用
    window._batchExistingCount = existingCount;

    main.innerHTML = `
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:20px">
            <div>
                <h1 style="margin:0">${ic('repeat', 'icon-lg')} 连续创作</h1>
                <p style="margin:4px 0 0;color:var(--text-secondary);font-size:0.9rem">${escHtml(novel.title)} · 当前 ${existingCount} 章</p>
            </div>
            <div class="inline-flex" style="gap:8px">
                <button class="btn" onclick="navigate('novel-detail', {novelId: '${novelId}'})">${ic('arrow-left')} 返回</button>
                <button class="btn" onclick="navigate('chapter-generate', {novelId: '${novelId}'})">${ic('pen-tool')} 单章创作</button>
            </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr;gap:16px;max-width:900px">
            <!-- 基本配置 -->
            <div class="card" style="padding:16px">
                <h3 style="margin:0 0 12px">${ic('settings', 'icon-sm')} 基本配置</h3>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                    <div class="form-group" style="margin:0">
                        <label style="font-weight:600">${ic('layers', 'icon-sm')} 章节数量（1-50）</label>
                        <input type="number" id="batchCount" value="${defaultCount}" min="1" max="50" style="width:100%" onchange="syncChapterList()">
                        <div style="font-size:0.75rem;color:var(--text-secondary);margin-top:2px">将从第 ${existingCount + 1} 章开始生成</div>
                    </div>
                    <div class="form-group" style="margin:0">
                        <label style="font-weight:600">${ic('bot', 'icon-sm')} 供应商</label>
                        <select id="batchProvider" style="width:100%">${providerOptions}</select>
                    </div>
                </div>
            </div>

            <!-- 整体走向 -->
            <div class="card" style="padding:16px">
                <h3 style="margin:0 0 8px">${ic('compass', 'icon-sm')} 整体走向（可选）</h3>
                <p style="margin:0 0 8px;font-size:0.8rem;color:var(--text-secondary)">描述这批章节的整体剧情走向、风格基调。会作为背景信息传递给每一章的生成。</p>
                <textarea id="batchOverallDirection" placeholder="例如：本批次围绕主角探索地下城展开，基调偏悬疑惊悚。主角在第一章发现入口，中间几章遇到各种机关和怪物，最后一章面对最终BOSS。" style="width:100%;min-height:80px"></textarea>
            </div>

            <!-- 每章走向 -->
            <div class="card" style="padding:16px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                    <h3 style="margin:0">${ic('list', 'icon-sm')} 每章走向（可选）</h3>
                    <span style="font-size:0.75rem;color:var(--text-secondary)" id="chapterHint">为每一章指定具体剧情走向，留空则由 AI 自由发挥</span>
                </div>
                <div id="chapterDirectionsList" style="display:flex;flex-direction:column;gap:8px"></div>
            </div>

            <!-- 开始按钮 -->
            <div style="display:flex;justify-content:center;padding:12px 0">
                <button class="btn btn-primary" style="font-size:1.05rem;padding:10px 32px" onclick="startBatchFromConfigPage()">
                    ${ic('play')} 开始连续创作
                </button>
            </div>
        </div>
    `;
    renderIcons();
    syncChapterList();
}

/** 根据章节数量同步每章走向输入框列表 */
function syncChapterList() {
    const count = parseInt(document.getElementById('batchCount')?.value || '0');
    const list = document.getElementById('chapterDirectionsList');
    if (!list || !count || count < 1) {
        if (list) list.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem">请先设置章节数量</p>';
        return;
    }
    // 保留已输入的内容
    const existing = {};
    list.querySelectorAll('textarea[data-idx]').forEach(ta => {
        existing[ta.dataset.idx] = ta.value;
    });
    const existingCount = window._batchExistingCount || 0;
    let html = '';
    for (let i = 0; i < count; i++) {
        const chNum = existingCount + i + 1;
        const val = existing[i] || '';
        html += `
            <div style="display:flex;gap:8px;align-items:flex-start">
                <div style="flex-shrink:0;width:60px;padding-top:6px;font-weight:600;color:var(--accent)">第 ${chNum} 章</div>
                <textarea data-idx="${i}" placeholder="本章的剧情走向（可选，留空则由 AI 自由发挥）" style="flex:1;min-height:50px">${escHtml(val)}</textarea>
            </div>
        `;
    }
    list.innerHTML = html;
}

/** 从连续创作配置页启动批量生成 */
async function startBatchFromConfigPage() {
    const count = parseInt(document.getElementById('batchCount')?.value || '0');
    if (!count || count < 1 || count > 50) {
        showToast('请输入 1-50 之间的数字', 'error');
        return;
    }
    const providerId = document.getElementById('batchProvider')?.value || '';
    const overallDirection = document.getElementById('batchOverallDirection')?.value || '';

    // 收集每章走向
    const chapterDirs = [];
    for (let i = 0; i < count; i++) {
        const ta = document.querySelector(`textarea[data-idx="${i}"]`);
        chapterDirs.push(ta ? ta.value : '');
    }

    // 保存配置到全局，供导航后使用
    window._pendingBatchConfig = {
        count,
        providerId,
        overallDirection,
        chapterDirections: chapterDirs,
    };

    // 导航到单章创作页面（复用其流式输出区域），然后启动批量生成
    navigate('chapter-generate', { novelId: currentNovelId });
    // 等页面渲染完成后启动
    setTimeout(() => {
        startBatchGeneration(
            window._pendingBatchConfig.count,
            window._pendingBatchConfig.providerId,
            window._pendingBatchConfig.overallDirection,
            window._pendingBatchConfig.chapterDirections,
        );
        window._pendingBatchConfig = null;
    }, 400);
}

// ==================== Chapter Generate Page ====================
async function renderChapterGeneratePage(main) {
    main.className = 'main-area';
    const { novel } = await API.get(`/api/novels/${currentNovelId}`);
    const { chapters } = await API.get(`/api/novels/${currentNovelId}/chapters`);
    const nextNumber = chapters.length + 1;

    // Load providers for selector
    let providerOptions = '<option value="">使用活跃供应商</option>';
    try {
        const { providers } = await API.get('/api/providers');
        const active = providers.find(p => p.is_active);
        providerOptions += providers.map(p => `
            <option value="${p.id}" ${p.is_active ? 'selected' : ''}>
                ${escHtml(p.name)} (${escHtml(p.model)})
            </option>
        `).join('');
    } catch (e) {
        // no providers — will use default
    }

    main.innerHTML = `
        <div class="page-header">
            <div class="inline-flex">
                <button class="btn btn-sm" onclick="goBack()">← 返回</button>
                <h2>生成第 ${nextNumber} 章</h2>
            </div>
        </div>

        <div class="card">
            <div class="form-row">
                <div class="form-group">
                    <label>章节标题 ${novel.title_mode === 'auto' ? '（AI自动生成）' : ''}</label>
                    <input type="text" id="genChapterTitle" placeholder="${novel.title_mode === 'auto' ? '留空自动生成' : '输入章节标题'}">
                </div>
                <div class="form-group">
                    <label>章节序号</label>
                    <input type="number" id="genChapterNumber" value="${nextNumber}" min="1">
                </div>
            </div>
            <div class="form-group">
                <label>${ic('bot', 'icon-sm')} 选择供应商</label>
                <select id="genProviderId">${providerOptions}</select>
                <small style="color:var(--text-secondary)">在 <a href="javascript:void(0)" onclick="navigate('settings')">功能设置</a> 中管理供应商</small>
            </div>
            <div style="margin-top:12px;border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden">
                <div style="padding:10px 14px;background:var(--bg);cursor:pointer;user-select:none;display:flex;justify-content:space-between;align-items:center" onclick="toggleAdvancedOptions()">
                    <span style="font-weight:600">${ic('settings', 'icon-sm')} 高级选项</span>
                    <span id="advToggle" style="font-size:0.8rem;color:var(--text-secondary)">${ic('chevron-down', 'icon-sm')} 展开</span>
                </div>
                <div id="advancedOptions" style="display:none;padding:14px">
                    <div class="form-group">
                        <label>情节走向提示</label>
                        <textarea id="advPlotDirection" placeholder="本章希望发生的核心事件或情节转折" style="min-height:64px"></textarea>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>角色视角</label>
                            <select id="advPov">
                                <option value="">默认</option>
                                <option value="第一人称">第一人称</option>
                                <option value="第三人称限制视角">第三人称限制视角</option>
                                <option value="全知视角">全知视角</option>
                                <option value="指定角色视角">指定角色视角</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>情绪基调</label>
                            <select id="advTone">
                                <option value="">默认</option>
                                <option value="轻松幽默">轻松幽默</option>
                                <option value="紧张悬疑">紧张悬疑</option>
                                <option value="悲伤沉重">悲伤沉重</option>
                                <option value="热血激昂">热血激昂</option>
                                <option value="温馨治愈">温馨治愈</option>
                                <option value="黑暗压抑">黑暗压抑</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>叙事节奏</label>
                            <select id="advPace">
                                <option value="">默认</option>
                                <option value="缓慢铺垫">缓慢铺垫</option>
                                <option value="正常推进">正常推进</option>
                                <option value="快速高潮">快速高潮</option>
                                <option value="转折突变">转折突变</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>自定义指令</label>
                        <textarea id="advCustomInstructions" placeholder="任何额外的写作要求" style="min-height:64px"></textarea>
                    </div>
                    <div class="form-group">
                        <label>Token 预算（覆盖小说设置，留空使用默认）</label>
                        <input type="number" id="advMaxTokens" value="" min="1024" max="65536" step="1024" placeholder="${novel.max_tokens || 16384}">
                        <small style="color:var(--text-secondary)">本次生成使用的最大 token 数。推理模型建议调大</small>
                    </div>
                </div>
            </div>
            <div id="extrasModeHint" style="display:none;margin-top:8px;padding:10px 12px;background:var(--accent-light);border-radius:var(--radius-sm);font-size:0.85rem;color:var(--text-secondary)">
                ${ic('party-popper', 'icon-sm')} 当前为番外模式：已超过预期 ${novel.expected_chapters || 0} 章，正在创作番外篇
            </div>
            <div class="inline-flex" style="margin-top:8px">
                <button class="btn btn-primary" id="genBtn" onclick="startGenerate()">${ic('rocket')} 开始生成</button>
                <button class="btn" id="stopGenBtn" style="display:none" onclick="stopGenerate()">${ic('square')} 停止</button>
            </div>
            <div class="progress-bar" id="genProgress" style="display:none">
                <div class="fill" style="width:0%"></div>
            </div>
        </div>

        <div style="display:grid;grid-template-columns:${window.innerWidth > 768 ? '1fr 1fr' : '1fr'};gap:16px" id="genSplitView">
            <div class="card" id="thinkingCard">
                <div class="card-header" style="cursor:pointer;user-select:none" onclick="toggleThinkingPanel()">
                    <h3>${ic('brain', 'icon-md')} AI 思考过程</h3>
                    <span id="thinkingToggle" style="font-size:0.8rem;color:var(--text-secondary)">${window.innerWidth > 768 ? '' : ic('chevron-down', 'icon-sm') + ' 展开'}</span>
                </div>
                <div class="stream-output" id="thinkingOutput" style="min-height:300px;font-size:0.85rem;color:var(--text-secondary);${window.innerWidth > 768 ? '' : 'display:none'}">
                    <span style="color:var(--text-secondary)">AI 的工具调用和思考过程将在此显示...</span>
                </div>
            </div>
            <div class="card">
                <div class="card-header"><h3>${ic('file-text', 'icon-md')} 生成正文</h3></div>
                <div class="stream-output" id="streamOutput" style="min-height:300px">
                    <span style="color:var(--text-secondary)">点击"开始生成"后，正文将在此实时流式显示...</span>
                </div>
            </div>
        </div>
    `;

    // 番外模式提示：当前章节号超过预期章节数时显示
    const expected = novel.expected_chapters || 0;
    const extrasHint = document.getElementById('extrasModeHint');
    if (extrasHint && expected > 0 && nextNumber > expected) {
        extrasHint.style.display = 'block';
        extrasHint.innerHTML = `${ic('party-popper', 'icon-sm')} 当前为番外模式：已超过预期 ${expected} 章，正在创作番外篇（第 ${nextNumber} 章）`;
    }
}

function toggleThinkingPanel() {
    const output = document.getElementById('thinkingOutput');
    const toggle = document.getElementById('thinkingToggle');
    if (!output) return;
    const isShown = output.style.display !== 'none';
    output.style.display = isShown ? 'none' : 'block';
    if (toggle) toggle.innerHTML = isShown ? `${ic('chevron-down', 'icon-sm')} 展开` : `${ic('chevron-up', 'icon-sm')} 收起`;
}

function toggleAdvancedOptions() {
    const panel = document.getElementById('advancedOptions');
    const toggle = document.getElementById('advToggle');
    if (!panel) return;
    const isShown = panel.style.display !== 'none';
    panel.style.display = isShown ? 'none' : 'block';
    if (toggle) toggle.innerHTML = isShown ? `${ic('chevron-down', 'icon-sm')} 展开` : `${ic('chevron-up', 'icon-sm')} 收起`;
}

// 在移动端自动展开思考面板（当有内容时）
function showThinkingIfNeeded() {
    const output = document.getElementById('thinkingOutput');
    if (output && output.innerHTML.trim() && output.style.display === 'none') {
        toggleThinkingPanel();
    }
}

let abortGen = false;

// 流式请求超时时间：5分钟（推理模型思考 + 工具调用 + 正文生成可能需要较长时间）
const STREAM_TIMEOUT_MS = 5 * 60 * 1000;

/**
 * 流式 fetch 封装：带 5 分钟看门狗超时
 * 返回 { reader, decoder, abortController }
 * 调用方负责在结束后调用 abortController.abort() 清理
 */
function streamFetch(url, options = {}) {
    const abortController = new AbortController();
    let watchdogTimer = null;
    let lastActivity = Date.now();

    // 看门狗：每次收到数据重置计时器，超过 STREAM_TIMEOUT_MS 无数据则中止
    const resetWatchdog = () => {
        if (watchdogTimer) clearTimeout(watchdogTimer);
        watchdogTimer = setTimeout(() => {
            console.warn(`流式请求超时（${STREAM_TIMEOUT_MS / 1000}秒无数据），自动中止`);
            abortController.abort();
        }, STREAM_TIMEOUT_MS);
    };
    resetWatchdog();

    const fetchPromise = fetch(url, { ...options, signal: abortController.signal });
    return fetchPromise.then(r => {
        const reader = r.body.getReader();
        // 包装 reader.read()，每次读取后重置看门狗
        const originalRead = reader.read.bind(reader);
        reader.read = async () => {
            const result = await originalRead();
            resetWatchdog();
            return result;
        };
        reader._abortController = abortController;
        reader._clearWatchdog = () => { if (watchdogTimer) clearTimeout(watchdogTimer); };
        return { reader, response: r };
    });
}

const TOOL_LABELS = {
    get_world_building:'世界观', get_outline:'大纲', get_style_reference:'文风',
    list_characters:'人物列表', get_character:'人物档案', get_character_relationships:'人物关系',
    list_wiki_entries:'百科列表', get_wiki_entry:'百科详情',
    list_chapters:'章节列表', get_chapter:'历史章节', get_recent_chapter_summary:'近期摘要',
    search_chapters:'搜索章节', rerank_search:'智能搜索',
    update_outline:'更新大纲', update_world_building:'更新世界观',
    add_character:'添加人物', update_character:'更新人物', add_wiki_entry:'添加百科',
};

async function startGenerate() {
    abortGen = false;
    const title = document.getElementById('genChapterTitle').value.trim();
    const number = parseInt(document.getElementById('genChapterNumber').value) || 1;
    const providerId = document.getElementById('genProviderId').value;
    const output = document.getElementById('streamOutput');
    const thinkingOutput = document.getElementById('thinkingOutput');
    const genBtn = document.getElementById('genBtn');
    const stopBtn = document.getElementById('stopGenBtn');
    const progress = document.getElementById('genProgress');

    output.innerHTML = '<span class="cursor"></span>';
    thinkingOutput.innerHTML = '';
    genBtn.style.display = 'none';
    stopBtn.style.display = 'inline-flex';
    progress.style.display = 'block';

    const formData = new FormData();
    formData.append('chapter_title', title);
    formData.append('chapter_number', number);
    if (providerId) formData.append('provider_id', providerId);

    // Token 预算覆盖（高级选项）
    const maxTokensVal = parseInt((document.getElementById('advMaxTokens') || {}).value);
    if (maxTokensVal && maxTokensVal > 0) formData.append('max_tokens', maxTokensVal);

    // 高级选项 → 组合成结构化 human_suggestions
    const plotDirection = (document.getElementById('advPlotDirection') || {}).value;
    const pov = (document.getElementById('advPov') || {}).value;
    const tone = (document.getElementById('advTone') || {}).value;
    const pace = (document.getElementById('advPace') || {}).value;
    const customInstructions = (document.getElementById('advCustomInstructions') || {}).value;
    const advParts = [];
    if (plotDirection && plotDirection.trim()) advParts.push('【情节走向】' + plotDirection.trim());
    if (pov && pov.trim()) advParts.push('【角色视角】' + pov.trim());
    if (tone && tone.trim()) advParts.push('【情绪基调】' + tone.trim());
    if (pace && pace.trim()) advParts.push('【叙事节奏】' + pace.trim());
    if (customInstructions && customInstructions.trim()) advParts.push('【附加指令】' + customInstructions.trim());
    const humanSuggestions = advParts.join('\n');
    if (humanSuggestions) formData.append('human_suggestions', humanSuggestions);

    try {
        const { reader, response: r } = await streamFetch(`/api/novels/${currentNovelId}/chapters/generate`, {
            method: 'POST',
            body: formData,
            headers: authToken ? { 'Authorization': 'Bearer ' + authToken } : {},
        });
        if (r.status === 401) { showLoginPage(); return; }
        if (!r.ok) {
            const err = await r.json().catch(() => ({ detail: r.statusText }));
            throw new Error(err.detail || '生成请求失败');
        }

        const decoder = new TextDecoder();
        let buffer = '';
        let fullContent = '';

        while (true) {
            if (abortGen) break;
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.slice(6);
                    if (dataStr === '[DONE]') continue;
                    try {
                        const msg = JSON.parse(dataStr);
                        if (msg.type === 'chunk') {
                            // 正文片段
                            fullContent += msg.data;
                            output.innerHTML = escHtml(fullContent) + '<span class="cursor"></span>';
                            output.scrollTop = output.scrollHeight;
                        } else if (msg.type === 'thinking') {
                            if (msg.incremental) {
                                // 增量推理内容（reasoning_content）— 直接追加到思考区，不影响正文
                                thinkingOutput.innerHTML += `<div style="padding:4px 0;color:var(--text-secondary)">${escHtml(msg.data)}</div>`;
                            } else {
                                // 工具调用轮次的文本重分类 — 从正文区移除，显示在思考区
                                fullContent = fullContent.slice(0, -msg.data.length);
                                output.innerHTML = escHtml(fullContent) + (fullContent ? '' : '<span class="cursor"></span>');
                                thinkingOutput.innerHTML += `<div style="padding:4px 0;color:var(--text-secondary)">${escHtml(msg.data)}</div>`;
                            }
                            thinkingOutput.scrollTop = thinkingOutput.scrollHeight;
                            showThinkingIfNeeded();
                        } else if (msg.type === 'content_replace') {
                            // 用清洗后的内容替换流式内容（也用于工具调用轮次清空正文区）
                            fullContent = msg.data;
                            output.innerHTML = escHtml(fullContent) + (fullContent ? '' : '<span class="cursor"></span>');
                        } else if (msg.type === 'tool_call') {
                            // 工具调用显示在思考区
                            const label = TOOL_LABELS[msg.name] || escHtml(msg.name);
                            const args = msg.args && Object.keys(msg.args).length ? `（${Object.values(msg.args).map(v => escHtml(String(v))).join('、')}）` : '';
                            thinkingOutput.innerHTML += `<div style="padding:3px 0;color:#4a9">${ic('wrench', 'icon-sm')} ${label}${args}</div>`;
                            thinkingOutput.scrollTop = thinkingOutput.scrollHeight;
                            showThinkingIfNeeded();
                        } else if (msg.type === 'tool_result') {
                            thinkingOutput.innerHTML += `<div style="padding:2px 0 6px 16px;color:var(--text-secondary);font-size:0.8rem;border-left:2px solid var(--border);margin-left:4px">${ic('corner-down-right', 'icon-sm')} ${escHtml(msg.preview || '')}</div>`;
                            thinkingOutput.scrollTop = thinkingOutput.scrollHeight;
                        } else if (msg.type === 'pending_changes') {
                            // 收到待确认的设定变更通知
                            window._pendingChangesData = msg.data;
                            setTimeout(() => showPendingChangesDialog(msg.data, msg.count), 800);
                        } else if (msg.type === 'done') {
                            output.innerHTML = escHtml(fullContent);
                            showToast(`第 ${msg.chapter.number} 章 "${msg.chapter.title}" 生成完成！`, 'success');
                            // 如果有待确认变更，延迟跳转让用户先处理
                            const delay = window._pendingChangesData && window._pendingChangesData.length ? 3000 : 1500;
                            setTimeout(() => navigate('novel-detail', { novelId: currentNovelId }), delay);
                        } else if (msg.type === 'error') {
                            // 错误时保留思考内容，仅正文区显示错误
                            output.innerHTML = `<span style="color:red">错误: ${escHtml(msg.message)}</span>`;
                            showToast(msg.message, 'error');
                        }
                    } catch (e) { /* ignore parse errors */ }
                }
            }
        }
    } catch (e) {
        output.innerHTML = `<span style="color:red">请求失败: ${escHtml(e.message)}</span>`;
        showToast(e.message, 'error');
    } finally {
        genBtn.style.display = 'inline-flex';
        stopBtn.style.display = 'none';
        progress.style.display = 'none';
    }
}

function stopGenerate() {
    abortGen = true;
}

// ==================== Chapter Edit Page ====================
let _editChapterList = [];
let _editChapterIndex = -1;

async function renderChapterEditPage(main) {
    main.className = 'main-area full';
    try {
        const { chapter } = await API.get(`/api/chapters/${currentChapterId}`);
        const { novel } = await API.get(`/api/novels/${chapter.novel_id}`);
        // 获取章节列表用于上下章导航
        try {
            const { chapters } = await API.get(`/api/novels/${chapter.novel_id}/chapters`);
            _editChapterList = chapters;
            _editChapterIndex = chapters.findIndex(ch => ch.id === currentChapterId);
        } catch (e) { /* ignore */ }
        const hasPrev = _editChapterIndex > 0;
        const hasNext = _editChapterIndex >= 0 && _editChapterIndex < _editChapterList.length - 1;

        main.innerHTML = `
            <div class="page-header">
                <div class="inline-flex">
                    <button class="btn btn-sm" onclick="goBack()">← 返回</button>
                    <h2>${escHtml(chapter.title)}</h2>
                </div>
                <div class="inline-flex">
                    <span class="badge badge-${chapter.status}">${chapter.status}</span>
                    <span style="color:var(--text-secondary);font-size:0.85rem">${chapter.words_count} 字</span>
                    <button class="btn btn-sm" onclick="navigate('chapter-read', {chapterId: '${chapter.id}', novelId: '${chapter.novel_id}'})">${ic('book-open')} 阅读</button>
                    <button class="btn btn-sm" onclick="toggleImmersive(true)">${ic('maximize')} 沉浸模式</button>
                    <button class="btn btn-sm btn-primary" id="saveChapterBtn" onclick="saveChapter()">${ic('save')} 保存</button>
                </div>
            </div>

            <div class="card" id="editorCard">
                <div id="wordGoalTracker" style="margin-bottom:14px">
                    <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.85rem;margin-bottom:6px">
                        <span>目标：<strong id="goalWords">${novel.words_per_chapter || 0}</strong> 字 / 当前：<strong id="currentWords">${chapter.content ? chapter.content.length : 0}</strong> 字</span>
                        <span style="display:inline-flex;align-items:center;gap:10px">
                            <span id="autoSaveStatus" style="color:#22c55e">已保存</span>
                            <span id="goalPercent" style="color:var(--text-secondary)">0%</span>
                        </span>
                    </div>
                    <div class="progress-bar" style="margin:0">
                        <div class="fill" id="goalFill" style="width:0%"></div>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>章节标题</label>
                        <input type="text" id="editChapterTitle" value="${escAttr(chapter.title)}" oninput="scheduleAutoSave()">
                    </div>
                    <div class="form-group">
                        <label>状态</label>
                        <select id="editChapterStatus" onchange="scheduleAutoSave()">
                            <option value="draft" ${chapter.status === 'draft' ? 'selected' : ''}>草稿</option>
                            <option value="review" ${chapter.status === 'review' ? 'selected' : ''}>审阅中</option>
                            <option value="done" ${chapter.status === 'done' ? 'selected' : ''}>已完成</option>
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                        <label style="margin:0">正文内容</label>
                        <div class="inline-flex" style="gap:4px">
                            <button class="btn btn-sm" id="previewToggleBtn" onclick="togglePreview()">${ic('eye')} 预览</button>
                            <button class="btn btn-sm" onclick="copyEditContent()">${ic('clipboard')} 复制</button>
                            <button class="btn btn-sm" onclick="openFindReplace()">${ic('search')} 查找替换</button>
                            <button class="btn btn-sm" onclick="cleanEmptyLines()">${ic('eraser')} 清理空行</button>
                            <button class="btn btn-sm" onclick="toggleWebSearchPanel(this)">${ic('globe')} 联网搜索</button>
                        </div>
                    </div>
                    <textarea class="content-editor" id="editChapterContent" oninput="updateWordCount(); scheduleAutoSave()" placeholder="在此编写章节正文...">${escHtml(chapter.content)}</textarea>
                    <div class="content-preview" id="editPreviewArea" style="display:none;margin-top:8px">${escHtml(chapter.content)}</div>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:4px;font-size:0.8rem;color:var(--text-secondary)">
                        <span id="wordCountDisplay">字数：${chapter.content ? chapter.content.length : 0}</span>
                        <span style="color:var(--text-secondary)">编辑后自动保存</span>
                    </div>
                </div>
                <div class="inline-flex" style="margin-top:12px;flex-wrap:wrap;gap:6px">
                    ${hasPrev ? `<button class="btn btn-sm" onclick="navigate('chapter-edit', {chapterId: '${_editChapterList[_editChapterIndex - 1].id}', novelId: '${chapter.novel_id}'})">← 上一章</button>` : ''}
                    <button class="btn btn-primary" onclick="saveChapter()">${ic('save')} 保存修改</button>
                    <button class="btn" onclick="aiPolishChapter()">${ic('sparkles')} AI润色</button>
                    <button class="btn" onclick="aiExpandChapter()">${ic('pencil')} AI扩写</button>
                    ${hasNext ? `<button class="btn btn-sm" onclick="navigate('chapter-edit', {chapterId: '${_editChapterList[_editChapterIndex + 1].id}', novelId: '${chapter.novel_id}'})">下一章 →</button>` : ''}
                </div>
            </div>

            <div id="immersiveExitBtn" style="display:none;position:fixed;top:16px;right:16px;z-index:10000">
                <button class="btn btn-sm btn-primary" onclick="toggleImmersive(false)">${ic('x')} 退出沉浸</button>
            </div>
        `;

        // 实时字数统计
        window._chapterContentOriginal = document.getElementById('editChapterContent').value;

        // 初始化字数目标追踪
        updateWordGoal();

        // 重置沉浸模式（防止上次遗留）并绑定 ESC 退出
        toggleImmersive(false);
        if (!window._immersiveEscBound) {
            window._immersiveEscBound = true;
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape' && _immersiveActive) toggleImmersive(false);
            });
        }

        // Ctrl+S 自动保存 + 离开提醒
        if (window._chapterAutoSave) {
            document.removeEventListener('keydown', window._chapterAutoSave);
        }
        window._chapterAutoSave = function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                saveChapter();
            }
        };
        document.addEventListener('keydown', window._chapterAutoSave);

        // 本地草稿兜底（每30秒，内容有变化时）—— 不再占用状态指示器
        if (window._chapterDraftTimer) clearInterval(window._chapterDraftTimer);
        window._chapterDraftTimer = setInterval(() => {
            const ta = document.getElementById('editChapterContent');
            if (!ta) return;
            const current = ta.value;
            if (current !== window._chapterContentOriginal) {
                localStorage.setItem('chapter_draft_' + currentChapterId, current);
            }
        }, 30000);

        // 离开页面提醒
        if (window._chapterBeforeUnload) {
            window.removeEventListener('beforeunload', window._chapterBeforeUnload);
        }
        window._chapterBeforeUnload = function(e) {
            const ta = document.getElementById('editChapterContent');
            if (ta && ta.value !== window._chapterContentOriginal) {
                e.preventDefault();
                e.returnValue = '';
            }
        };
        window.addEventListener('beforeunload', window._chapterBeforeUnload);

        // 恢复草稿
        const draft = localStorage.getItem('chapter_draft_' + currentChapterId);
        if (draft && draft !== chapter.content && chapter.content !== draft) {
            const ta = document.getElementById('editChapterContent');
            if (ta && await confirmDialog('检测到未保存的草稿，是否恢复？', { icon: 'info', confirmText: '恢复' })) {
                ta.value = draft;
                updateWordCount();
            } else {
                localStorage.removeItem('chapter_draft_' + currentChapterId);
            }
        }
    } catch (e) {
        main.innerHTML = `<div class="empty-state"><p>加载失败: ${escHtml(e.message)}</p></div>`;
    }
}

function updateWordCount() {
    const ta = document.getElementById('editChapterContent');
    const display = document.getElementById('wordCountDisplay');
    if (ta && display) display.textContent = '字数：' + ta.value.length;
    updateWordGoal();
}

// ==================== 字数目标追踪 ====================
function updateWordGoal() {
    const ta = document.getElementById('editChapterContent');
    const goalEl = document.getElementById('goalWords');
    const curEl = document.getElementById('currentWords');
    const pctEl = document.getElementById('goalPercent');
    const fillEl = document.getElementById('goalFill');
    if (!ta || !goalEl) return;
    const goal = parseInt(goalEl.textContent) || 0;
    const cur = ta.value.length;
    if (curEl) curEl.textContent = cur;
    const pct = goal > 0 ? Math.min(100, Math.round(cur / goal * 100)) : 0;
    if (pctEl) pctEl.textContent = goal > 0 ? (pct + '%') : '未设置';
    if (fillEl) {
        fillEl.style.width = pct + '%';
        fillEl.style.background = (goal > 0 && cur >= goal) ? '#22c55e' : 'var(--accent)';
    }
}

function togglePreview() {
    const ta = document.getElementById('editChapterContent');
    const preview = document.getElementById('editPreviewArea');
    const btn = document.getElementById('previewToggleBtn');
    if (!ta || !preview) return;
    const isPreview = preview.style.display !== 'none';
    if (isPreview) {
        // 切回编辑
        preview.style.display = 'none';
        ta.style.display = 'block';
        if (btn) btn.innerHTML = `${ic('eye')} 预览`;
    } else {
        // 切到预览
        preview.innerHTML = escHtml(ta.value) || '<span style="color:var(--text-secondary)">（无内容）</span>';
        preview.style.display = 'block';
        ta.style.display = 'none';
        if (btn) btn.innerHTML = `${ic('pencil')} 编辑`;
    }
}

async function copyEditContent() {
    const ta = document.getElementById('editChapterContent');
    if (!ta) return;
    try {
        await navigator.clipboard.writeText(ta.value);
        showToast('已复制全文', 'success');
    } catch (e) {
        showToast('复制失败', 'error');
    }
}

/**
 * 清理正文中的空行
 * 提供三种模式：合并连续空行、删除所有空行、删除首尾空行
 */
async function cleanEmptyLines() {
    const ta = document.getElementById('editChapterContent');
    if (!ta) { showToast('未找到编辑器', 'error'); return; }
    const original = ta.value;
    if (!original) { showToast('没有内容可清理', 'error'); return; }

    // 统计当前空行情况
    const lines = original.split('\n');
    const totalLines = lines.length;
    const emptyLines = lines.filter(l => l.trim() === '').length;
    const consecutiveEmpty = (lines.match(/\n[ \t]*\n[ \t]*\n/g) || []).length;

    if (emptyLines === 0) {
        showToast('没有空行需要清理', 'info');
        return;
    }

    // 用 Modal 让用户选择清理模式
    let formData = null;
    await showModal({
        title: '清理空行',
        icon: 'info',
        size: 'md',
        message: `
            <div style="background:var(--bg);border-radius:var(--radius-sm);padding:10px 12px;margin-bottom:14px;font-size:0.85rem;color:var(--text-secondary)">
                <div>总行数：<strong>${totalLines}</strong></div>
                <div>空行数：<strong style="color:var(--warning)">${emptyLines}</strong></div>
                <div>连续空行处：<strong style="color:var(--warning)">${consecutiveEmpty}</strong></div>
            </div>
            <div class="form-group" style="margin-bottom:0">
                <label style="font-weight:600">${ic('eraser', 'icon-sm')} 清理模式</label>
                <select id="_clean_mode" name="mode" style="width:100%">
                    <option value="merge">合并连续空行（多个空行合并为一个，保留段落间距）</option>
                    <option value="remove_all">删除所有空行（紧凑排版，无段落间距）</option>
                    <option value="trim_ends">仅删除首尾空行（保留中间所有空行）</option>
                    <option value="merge_and_trim">合并连续 + 删除首尾（推荐）</option>
                </select>
            </div>
        `,
        buttons: [
            { text: '取消', type: 'default', value: null },
            {
                text: '清理',
                type: 'primary',
                value: null,
                onClick: (close, form) => { formData = form; close('__clean__'); },
            },
        ],
    });

    if (!formData) return;
    const mode = formData.mode || 'merge';

    let cleaned = original;
    let actionText = '';

    if (mode === 'merge') {
        // 合并连续空行为单个空行
        cleaned = original.replace(/\n[ \t]*\n[ \t]*(\n[ \t]*)*/g, '\n\n');
        actionText = '已合并连续空行';
    } else if (mode === 'remove_all') {
        // 删除所有空行（行内空白也算空行）
        cleaned = lines
            .filter(l => l.trim() !== '')
            .join('\n');
        actionText = '已删除所有空行';
    } else if (mode === 'trim_ends') {
        // 仅删除首尾空行
        cleaned = original.replace(/^\s+/, '').replace(/\s+$/, '');
        actionText = '已删除首尾空行';
    } else if (mode === 'merge_and_trim') {
        // 合并连续空行 + 删除首尾
        cleaned = original.replace(/\n[ \t]*\n[ \t]*(\n[ \t]*)*/g, '\n\n');
        cleaned = cleaned.replace(/^\s+/, '').replace(/\s+$/, '');
        actionText = '已合并连续空行并删除首尾';
    }

    // 检查是否有变化
    if (cleaned === original) {
        showToast('内容无变化', 'info');
        return;
    }

    // 应用清理结果
    const removedCount = original.split('\n').length - cleaned.split('\n').length;
    ta.value = cleaned;
    // 触发 input 事件，更新字数统计和自动保存
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    updateWordCount();
    scheduleAutoSave();

    showToast(`${actionText}（减少 ${removedCount} 行）`, 'success');
}

async function saveChapter() {
    const title = document.getElementById('editChapterTitle').value;
    const content = document.getElementById('editChapterContent').value;
    const status = document.getElementById('editChapterStatus').value;
    // 取消挂起的自动保存，避免与手动保存重复
    if (_autoSaveTimer) { clearTimeout(_autoSaveTimer); _autoSaveTimer = null; }
    const autoStatus = document.getElementById('autoSaveStatus');
    if (autoStatus) { autoStatus.textContent = '保存中...'; autoStatus.style.color = 'var(--text-secondary)'; }
    try {
        await API.put(`/api/chapters/${currentChapterId}`, { title, content, status });
        showToast('章节已保存', 'success');
        // 更新原始内容基准，清除草稿
        window._chapterContentOriginal = content;
        localStorage.removeItem('chapter_draft_' + currentChapterId);
        if (autoStatus) { autoStatus.textContent = '已保存'; autoStatus.style.color = '#22c55e'; }
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
        if (autoStatus) { autoStatus.textContent = '保存失败'; autoStatus.style.color = 'var(--danger)'; }
    }
}

async function aiPolishChapter() {
    const content = document.getElementById('editChapterContent').value;
    if (!content) { showToast('没有内容可润色', 'error'); return; }
    showToast('润色中，请稍候...', 'info');
    try {
        const r = await fetch('/api/novels/ai-polish', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...(authToken ? { 'Authorization': 'Bearer ' + authToken } : {}) },
            body: JSON.stringify({ content, chapter_id: currentChapterId }),
        });
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        const data = await r.json();
        document.getElementById('editChapterContent').value = data.polished;
        showToast('润色完成', 'success');
    } catch (e) {
        showToast('润色失败: ' + e.message, 'error');
    }
}

async function aiExpandChapter() {
    const content = document.getElementById('editChapterContent').value;
    if (!content) { showToast('没有内容可扩写', 'error'); return; }
    showToast('扩写中，请稍候...', 'info');
    try {
        const r = await fetch('/api/novels/ai-expand', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...(authToken ? { 'Authorization': 'Bearer ' + authToken } : {}) },
            body: JSON.stringify({ content, chapter_id: currentChapterId }),
        });
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        const data = await r.json();
        document.getElementById('editChapterContent').value = data.expanded;
        showToast('扩写完成', 'success');
    } catch (e) {
        showToast('扩写失败: ' + e.message, 'error');
    }
}

// ==================== 联网搜索参考资料 ====================

function toggleWebSearchPanel(btn) {
    const html = `
        <h3 style="margin-bottom:14px;font-size:1.05rem">${ic('search', 'icon-md')} 联网搜索参考资料</h3>
        <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:12px">
            输入关键词，AI 将基于其知识库返回相关参考资料，可一键插入到正文光标位置。
        </p>
        <div class="form-group" style="display:flex;gap:6px;align-items:flex-end">
            <div style="flex:1">
                <label>搜索内容</label>
                <input type="text" id="webSearchQuery" placeholder="如：唐代长安城布局、剑术招式名称" onkeydown="if(event.key==='Enter')doWebSearch()">
            </div>
            <button class="btn btn-primary" onclick="doWebSearch()">搜索</button>
        </div>
        <div id="webSearchStatus" style="display:none;margin:10px 0;font-size:0.85rem;color:var(--text-secondary)"></div>
        <div id="webSearchResults" style="max-height:340px;overflow-y:auto"></div>
    `;
    toggleDropdown(btn, html, true);
}

async function doWebSearch() {
    const query = document.getElementById('webSearchQuery').value.trim();
    if (!query) { showToast('请输入搜索内容', 'error'); return; }
    const statusEl = document.getElementById('webSearchStatus');
    const resultsEl = document.getElementById('webSearchResults');
    if (statusEl) { statusEl.style.display = 'block'; statusEl.innerHTML = `${ic('search', 'icon-sm')} 正在搜索参考资料...`; }
    if (resultsEl) resultsEl.innerHTML = '';
    try {
        const data = await API.post('/api/search', { query });
        if (statusEl) statusEl.style.display = 'none';
        if (data.error) {
            if (resultsEl) resultsEl.innerHTML = `<div style="padding:12px;color:var(--danger)">搜索失败: ${escHtml(data.error)}</div>`;
            return;
        }
        const results = data.results || [];
        if (!results.length) {
            if (resultsEl) resultsEl.innerHTML = '<div style="padding:12px;color:var(--text-secondary)">未找到相关参考资料</div>';
            return;
        }
        if (resultsEl) {
            resultsEl.innerHTML = results.map((r, i) => `
                <div style="padding:10px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:8px">
                    <div style="font-weight:600;color:var(--accent);font-size:0.92rem">${escHtml(r.title || ('资料 ' + (i + 1)))}</div>
                    <div style="font-size:0.82rem;color:var(--text-secondary);white-space:pre-wrap;margin:6px 0;line-height:1.6">${escHtml(r.content)}</div>
                    ${r.url ? `<div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:6px">${ic('link', 'icon-sm')} ${escHtml(r.url)}</div>` : ''}
                    <button class="btn btn-sm btn-primary" onclick='insertSearchResult(${JSON.stringify(JSON.stringify(r.content))})'>${ic('download')} 插入到正文</button>
                </div>
            `).join('');
        }
    } catch (e) {
        if (statusEl) statusEl.style.display = 'none';
        if (resultsEl) resultsEl.innerHTML = `<div style="padding:12px;color:var(--danger)">搜索失败: ${escHtml(e.message)}</div>`;
    }
}

function insertSearchResult(text) {
    const ta = document.getElementById('editChapterContent');
    if (!ta) { showToast('未找到编辑器', 'error'); return; }
    // 在光标位置插入
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const before = ta.value.substring(0, start);
    const after = ta.value.substring(end);
    const insertText = '\n\n' + text + '\n';
    ta.value = before + insertText + after;
    // 移动光标到插入内容之后
    const newPos = start + insertText.length;
    ta.focus();
    ta.setSelectionRange(newPos, newPos);
    updateWordCount();
    scheduleAutoSave();
    showToast('已插入到正文', 'success');
}

// ==================== 自动保存（debounce 3s）====================
let _autoSaveTimer = null;
let _autoSaveInFlight = false;

function scheduleAutoSave() {
    if (_autoSaveTimer) clearTimeout(_autoSaveTimer);
    const status = document.getElementById('autoSaveStatus');
    if (status && status.textContent !== '保存中...') {
        status.textContent = '编辑中...';
        status.style.color = 'var(--text-secondary)';
    }
    _autoSaveTimer = setTimeout(doAutoSave, 3000);
}

async function doAutoSave() {
    _autoSaveTimer = null;
    const ta = document.getElementById('editChapterContent');
    if (!ta) return;
    if (ta.value === window._chapterContentOriginal) {
        const s = document.getElementById('autoSaveStatus');
        if (s) { s.textContent = '已保存'; s.style.color = '#22c55e'; }
        return;
    }
    if (_autoSaveInFlight) { scheduleAutoSave(); return; }
    _autoSaveInFlight = true;
    const status = document.getElementById('autoSaveStatus');
    if (status) { status.textContent = '保存中...'; status.style.color = 'var(--text-secondary)'; }
    try {
        const title = document.getElementById('editChapterTitle').value;
        const content = ta.value;
        const chStatus = document.getElementById('editChapterStatus').value;
        await API.put(`/api/chapters/${currentChapterId}`, { title, content, status: chStatus });
        window._chapterContentOriginal = content;
        localStorage.removeItem('chapter_draft_' + currentChapterId);
        if (status) { status.textContent = '已保存'; status.style.color = '#22c55e'; }
    } catch (e) {
        if (status) { status.textContent = '保存失败'; status.style.color = 'var(--danger)'; }
    } finally {
        _autoSaveInFlight = false;
    }
}

// ==================== 沉浸模式 ====================
let _immersiveActive = false;

function toggleImmersive(enter) {
    const card = document.getElementById('editorCard');
    const exitBtn = document.getElementById('immersiveExitBtn');
    _immersiveActive = !!enter;
    injectEditorStyles();
    if (enter) {
        if (card) card.classList.add('immersive-editor');
        document.body.classList.add('immersive-active');
        if (exitBtn) exitBtn.style.display = 'block';
    } else {
        if (card) card.classList.remove('immersive-editor');
        document.body.classList.remove('immersive-active');
        if (exitBtn) exitBtn.style.display = 'none';
    }
}

// ==================== 查找替换 ====================
let _findMatches = [];
let _findIndex = -1;

function injectEditorStyles() {
    if (document.getElementById('editorEnhanceStyles')) return;
    const s = document.createElement('style');
    s.id = 'editorEnhanceStyles';
    s.textContent = `
        body.immersive-active #sidebar,
        body.immersive-active #menuBtn,
        body.immersive-active #sidebarOverlay { display: none !important; }
        .immersive-editor {
            position: fixed !important;
            top: 0 !important; left: 0 !important; right: 0 !important; bottom: 0 !important;
            z-index: 9990 !important;
            margin: 0 !important;
            border-radius: 0 !important;
            overflow: auto !important;
            background: var(--bg) !important;
            padding: 24px !important;
            box-sizing: border-box !important;
        }
        body.immersive-active .immersive-editor .content-editor,
        body.immersive-active .immersive-editor #editPreviewArea,
        body.immersive-active .immersive-editor #wordGoalTracker,
        body.immersive-active .immersive-editor .form-row,
        body.immersive-active .immersive-editor > .inline-flex {
            max-width: 820px; margin-left: auto; margin-right: auto;
        }
        #findHighlightOverlay {
            color: transparent;
            white-space: pre-wrap;
            word-wrap: break-word;
            overflow: hidden;
            border-style: solid;
        }
        #findHighlightOverlay mark.find-mark {
            background: #fff59d; color: transparent; border-radius: 2px;
        }
        #findHighlightOverlay mark.find-mark-current {
            background: #ff9800; color: transparent; border-radius: 2px;
        }
        #findReplacePanel { animation: slideDown 0.18s ease; }
    `;
    document.head.appendChild(s);
}

function openFindReplace() {
    const ta = document.getElementById('editChapterContent');
    if (!ta) return;
    injectEditorStyles();
    let panel = document.getElementById('findReplacePanel');
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'findReplacePanel';
        panel.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <strong style="font-size:0.9rem">${ic('search', 'icon-md')} 查找替换</strong>
                <button class="btn btn-sm" onclick="closeFindReplace()" style="padding:2px 8px">${ic('x')}</button>
            </div>
            <div class="form-group" style="margin-bottom:6px">
                <input type="text" id="findInput" placeholder="查找内容..." oninput="updateFindMatches()" style="width:100%">
            </div>
            <div class="form-group" style="margin-bottom:6px">
                <input type="text" id="replaceInput" placeholder="替换为..." style="width:100%">
            </div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:0.8rem;color:var(--text-secondary)">
                <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer">
                    <input type="checkbox" id="findRegexCheckbox" onchange="updateFindMatches()"> 正则表达式
                </label>
                <span id="findCounter" style="margin-left:auto">0/0</span>
            </div>
            <div class="inline-flex" style="gap:4px;flex-wrap:wrap">
                <button class="btn btn-sm" onclick="findPrev()">${ic('arrow-up')} 上一个</button>
                <button class="btn btn-sm" onclick="findNext()">${ic('arrow-down')} 下一个</button>
                <button class="btn btn-sm" onclick="replaceCurrent()">替换</button>
                <button class="btn btn-sm" onclick="replaceAllFind()">全部替换</button>
            </div>
        `;
        panel.style.cssText = 'position:fixed;top:72px;right:20px;z-index:10001;width:300px;max-width:calc(100vw - 40px);background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);box-shadow:0 6px 24px rgba(0,0,0,0.15);padding:14px';
        const mainArea = document.getElementById('mainArea');
        (mainArea || document.body).appendChild(panel);
    }
    panel.style.display = 'block';
    ensureFindOverlay();
    bindFindEvents();
    updateFindMatches();
    setTimeout(() => { const fi = document.getElementById('findInput'); if (fi) fi.focus(); }, 0);
}

function closeFindReplace() {
    const panel = document.getElementById('findReplacePanel');
    if (panel) panel.style.display = 'none';
    const ta = document.getElementById('editChapterContent');
    if (ta) { ta.style.background = ''; ta.style.position = ''; ta.style.zIndex = ''; }
    const overlay = document.getElementById('findHighlightOverlay');
    if (overlay) overlay.innerHTML = '';
}

function ensureFindOverlay() {
    const ta = document.getElementById('editChapterContent');
    if (!ta) return null;
    let overlay = document.getElementById('findHighlightOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'findHighlightOverlay';
        ta.parentNode.insertBefore(overlay, ta.nextSibling);
    }
    return overlay;
}

function syncFindOverlay() {
    const ta = document.getElementById('editChapterContent');
    const overlay = document.getElementById('findHighlightOverlay');
    if (!ta || !overlay) return;
    const cs = getComputedStyle(ta);
    overlay.style.position = 'absolute';
    overlay.style.left = ta.offsetLeft + 'px';
    overlay.style.top = ta.offsetTop + 'px';
    overlay.style.width = ta.offsetWidth + 'px';
    overlay.style.height = ta.offsetHeight + 'px';
    overlay.style.margin = '0';
    overlay.style.padding = cs.padding;
    overlay.style.borderWidth = cs.borderWidth;
    overlay.style.borderStyle = cs.borderStyle;
    overlay.style.borderColor = 'transparent';
    overlay.style.boxSizing = cs.boxSizing;
    overlay.style.fontFamily = cs.fontFamily;
    overlay.style.fontSize = cs.fontSize;
    overlay.style.lineHeight = cs.lineHeight;
    overlay.style.letterSpacing = cs.letterSpacing;
    overlay.style.whiteSpace = 'pre-wrap';
    overlay.style.wordWrap = 'break-word';
    overlay.style.overflow = 'hidden';
    overlay.style.pointerEvents = 'none';
    overlay.style.zIndex = '0';
    ta.style.position = 'relative';
    ta.style.zIndex = '1';
    ta.style.background = 'transparent';
    overlay.scrollTop = ta.scrollTop;
    overlay.scrollLeft = ta.scrollLeft;
}

function bindFindEvents() {
    const ta = document.getElementById('editChapterContent');
    if (!ta || ta._findBound) return;
    ta._findBound = true;
    const onScroll = function() {
        const o = document.getElementById('findHighlightOverlay');
        if (o) { o.scrollTop = ta.scrollTop; o.scrollLeft = ta.scrollLeft; }
    };
    ta.addEventListener('scroll', onScroll);
    ta.addEventListener('input', function() { updateFindMatches(); });
    if (window.ResizeObserver) {
        const ro = new ResizeObserver(function() { renderFindOverlay(); });
        ro.observe(ta);
    }
}

function computeFindMatches() {
    const ta = document.getElementById('editChapterContent');
    const findInput = document.getElementById('findInput');
    _findMatches = [];
    if (!ta || !findInput) return;
    const query = findInput.value;
    if (!query) return;
    const useRegex = !!(document.getElementById('findRegexCheckbox') && document.getElementById('findRegexCheckbox').checked);
    let re;
    try {
        const pattern = useRegex ? query : query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        re = new RegExp(pattern, 'g');
    } catch (e) { return; }
    let m;
    while ((m = re.exec(ta.value)) !== null) {
        if (m[0].length === 0) { re.lastIndex++; continue; }
        _findMatches.push({ start: m.index, end: m.index + m[0].length, g: m.slice() });
    }
}

// 解析替换模板中的反向引用（$1、$&、$$、$`、$'），仅在正则模式下使用
function resolveBackrefs(tpl, groups, text, start, end) {
    return tpl.replace(/\$(\$|&|`|'|\d{1,2})/g, function(_, tok) {
        if (tok === '$') return '$';
        if (tok === '&') return groups[0] || '';
        if (tok === '`') return text.slice(0, start);
        if (tok === "'") return text.slice(end);
        const n = parseInt(tok, 10);
        if (n >= 1 && n < groups.length) return groups[n] != null ? groups[n] : '';
        // $0 或越界组号：保留字面量（与原生 String.replace 一致）
        return '$' + tok;
    });
}

function updateFindMatches() {
    const panel = document.getElementById('findReplacePanel');
    if (!panel || panel.style.display === 'none') return;
    computeFindMatches();
    if (_findIndex >= _findMatches.length) _findIndex = _findMatches.length - 1;
    if (_findIndex < 0 && _findMatches.length > 0) _findIndex = 0;
    renderFindOverlay();
    updateFindCounter();
    scrollFindToCurrent();
}

function renderFindOverlay() {
    const panel = document.getElementById('findReplacePanel');
    if (!panel || panel.style.display === 'none') return;
    const ta = document.getElementById('editChapterContent');
    const overlay = document.getElementById('findHighlightOverlay');
    if (!ta || !overlay) return;
    syncFindOverlay();
    const text = ta.value;
    let html = '';
    let last = 0;
    for (let i = 0; i < _findMatches.length; i++) {
        const m = _findMatches[i];
        html += escHtml(text.slice(last, m.start));
        const cls = i === _findIndex ? 'find-mark-current' : 'find-mark';
        html += '<mark class="' + cls + '">' + escHtml(text.slice(m.start, m.end)) + '</mark>';
        last = m.end;
    }
    html += escHtml(text.slice(last));
    if (text === '' || text.endsWith('\n')) html += '\u200b';
    overlay.innerHTML = html;
    overlay.scrollTop = ta.scrollTop;
    overlay.scrollLeft = ta.scrollLeft;
}

function updateFindCounter() {
    const counter = document.getElementById('findCounter');
    if (!counter) return;
    if (_findMatches.length === 0) {
        counter.textContent = '0/0';
        counter.style.color = 'var(--text-secondary)';
    } else {
        counter.textContent = (_findIndex + 1) + '/' + _findMatches.length;
        counter.style.color = 'var(--accent)';
    }
}

function scrollFindToCurrent() {
    const ta = document.getElementById('editChapterContent');
    if (!ta || _findIndex < 0 || _findIndex >= _findMatches.length) return;
    const m = _findMatches[_findIndex];
    ta.focus();
    try { ta.setSelectionRange(m.start, m.end); } catch (e) {}
    const before = ta.value.slice(0, m.start);
    const lines = before.split('\n').length;
    const lh = parseFloat(getComputedStyle(ta).lineHeight) || 20;
    const targetTop = (lines - 1) * lh;
    if (targetTop < ta.scrollTop || targetTop > ta.scrollTop + ta.clientHeight - lh) {
        ta.scrollTop = Math.max(0, targetTop - ta.clientHeight / 2);
    }
    renderFindOverlay();
}

function findNext() {
    if (_findMatches.length === 0) return;
    _findIndex = (_findIndex + 1) % _findMatches.length;
    scrollFindToCurrent();
    updateFindCounter();
}

function findPrev() {
    if (_findMatches.length === 0) return;
    _findIndex = (_findIndex - 1 + _findMatches.length) % _findMatches.length;
    scrollFindToCurrent();
    updateFindCounter();
}

function replaceCurrent() {
    const ta = document.getElementById('editChapterContent');
    const replaceInput = document.getElementById('replaceInput');
    if (!ta || !replaceInput) return;
    if (_findIndex < 0 || _findIndex >= _findMatches.length) return;
    const m = _findMatches[_findIndex];
    const useRegex = !!(document.getElementById('findRegexCheckbox') && document.getElementById('findRegexCheckbox').checked);
    const replacement = useRegex
        ? resolveBackrefs(replaceInput.value, m.g, ta.value, m.start, m.end)
        : replaceInput.value;
    ta.value = ta.value.slice(0, m.start) + replacement + ta.value.slice(m.end);
    const newPos = m.start + replacement.length;
    ta.focus();
    try { ta.setSelectionRange(newPos, newPos); } catch (e) {}
    updateWordCount();
    scheduleAutoSave();
    // 重新计算匹配，并定位到下一个
    const prevStart = newPos;
    computeFindMatches();
    let nextIdx = _findMatches.findIndex(function(x) { return x.start >= prevStart; });
    if (nextIdx < 0 && _findMatches.length > 0) nextIdx = 0;
    _findIndex = _findMatches.length > 0 ? nextIdx : -1;
    renderFindOverlay();
    updateFindCounter();
    scrollFindToCurrent();
}

function replaceAllFind() {
    const ta = document.getElementById('editChapterContent');
    const findInput = document.getElementById('findInput');
    const replaceInput = document.getElementById('replaceInput');
    if (!ta || !findInput || !replaceInput) return;
    const query = findInput.value;
    if (!query) return;
    const useRegex = !!(document.getElementById('findRegexCheckbox') && document.getElementById('findRegexCheckbox').checked);
    let count = 0;
    try {
        const pattern = useRegex ? query : query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const re = new RegExp(pattern, 'g');
        if (useRegex) {
            // 正则模式：用字符串替换以支持 $1 等反向引用
            const all = ta.value.match(re) || [];
            count = all.length;
            ta.value = ta.value.replace(re, replaceInput.value);
        } else {
            // 普通模式：字面替换
            ta.value = ta.value.replace(re, function() { count++; return replaceInput.value; });
        }
    } catch (e) { return; }
    updateWordCount();
    scheduleAutoSave();
    _findMatches = [];
    _findIndex = -1;
    updateFindMatches();
    showToast('已替换 ' + count + ' 处', 'success');
}

// ==================== Duplicates Page ====================
async function renderDuplicatesPage(main) {
    main.className = 'main-area';
    main.innerHTML = `<div class="empty-state"><p>检测中...</p></div>`;
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/check-duplicates`, {});
        const duplicates = data.duplicates || [];
        const vecAvailable = data.vector_available !== false;

        if (!vecAvailable) {
            main.innerHTML = `
                <div class="page-header">
                    <div class="inline-flex">
                        <button class="btn btn-sm" onclick="goBack()">← 返回</button>
                        <h2>${ic('search', 'icon-md')} 剧情重复检测</h2>
                    </div>
                </div>
                <div class="card">
                    <div class="empty-state">
                        ${ic('alert-triangle', 'icon-lg')}
                        <p style="color:var(--warning);font-weight:600">向量模型未配置</p>
                        <p style="margin-top:8px;font-size:0.9rem;color:var(--text-secondary)">
                            请前往「${ic('settings', 'icon-sm')} 功能设置」页面配置向量模型后，再进行剧情重复检测。
                        </p>
                        <button class="btn btn-primary" style="margin-top:16px" onclick="navigate('settings')">前往设置</button>
                    </div>
                </div>
            `;
            return;
        }

        main.innerHTML = `
            <div class="page-header">
                <div class="inline-flex">
                    <button class="btn btn-sm" onclick="goBack()">← 返回</button>
                    <h2>${ic('search', 'icon-md')} 剧情重复检测</h2>
                </div>
            </div>
            <div class="card">
                ${duplicates.length === 0
                    ? `<div class="empty-state">${ic('check-circle', 'icon-lg')}<p>未检测到明显剧情重复</p></div>`
                    : `<p style="margin-bottom:12px;color:var(--danger)">检测到 ${duplicates.length} 处高相似度段落：</p>` +
                      duplicates.map(d => `
                        <div class="dup-item">
                            <div class="dup-pair">第 ${d.pair[0] + 1} 章 ↔ 第 ${d.pair[1] + 1} 章</div>
                            <div class="dup-sim">相似度: ${(d.similarity * 100).toFixed(1)}%</div>
                            <div class="dup-preview">A: ${escHtml(d.text_a_preview)}...</div>
                            <div class="dup-preview">B: ${escHtml(d.text_b_preview)}...</div>
                        </div>
                      `).join('')
                }
            </div>
        `;
    } catch (e) {
        main.innerHTML = `<div class="empty-state"><p>检测失败: ${escHtml(e.message)}</p><button class="btn" onclick="goBack()">返回</button></div>`;
    }
}

async function checkDuplicates() {
    navigate('duplicates', { novelId: currentNovelId });
}

// ==================== Settings Page ====================
async function renderSettingsPage(main) {
    main.className = 'main-area';
    main.innerHTML = `<div class="empty-state"><p>加载中...</p></div>`;
    try {
        const [vecCfg, { providers }, rerankerRes, imgCfgRes, tavilyRes, serverRes] = await Promise.all([
            API.get('/api/config/vector'),
            API.get('/api/providers'),
            API.get('/api/config/reranker').catch(() => null),
            API.get('/api/config/image').catch(() => null),
            API.get('/api/config/tavily').catch(() => null),
            API.get('/api/config/server').catch(() => null),
        ]);
        const rerankerCfg = rerankerRes || { enabled: false, use_independent: false, api_base: '', api_key: '', model: '', rerank_path: '/rerank', top_n: 3 };
        const imgCfg = imgCfgRes || { image_api_url: '', image_api_key: '', image_api_model: '' };
        const tavilyCfg = tavilyRes || { tavily_api_key: '' };
        const serverCfg = serverRes || { host: '127.0.0.1', port: 8000 };
        window._tavilyCfg = tavilyCfg;
        window._serverCfg = serverCfg;
        const isVecAPI = vecCfg.backend === 'openai';
        const isVecST = vecCfg.backend === 'sentence_transformers';
        const useIndep = vecCfg.use_independent_embedding;

        main.innerHTML = `
            <div class="page-header">
                <h2>${ic('settings', 'icon-md')} 功能设置</h2>
            </div>

            <!-- 供应商管理 -->
            <div class="card">
                <div class="card-header">
                    <h3>${ic('bot', 'icon-md')} LLM 供应商列表</h3>
                    <div class="dropdown-wrapper">
                        <button class="btn btn-primary btn-sm" onclick="toggleAddProvider(this)">+ 添加供应商</button>
                    </div>
                </div>
                <div style="padding:0 16px 8px;font-size:0.82rem;color:#e74c3c;background:#fdf0ef;border:1px solid #f5c6cb;border-radius:var(--radius-sm);padding:8px 12px;margin:8px 16px">
                    ${ic('alert-triangle', 'icon-sm')} 修改供应商配置后需点击侧边栏底部「重启应用」按钮使配置生效
                </div>
                <div id="providerList">
                    ${providers.length === 0
                        ? '<div class="empty-state"><p>暂无供应商，点击上方按钮添加</p></div>'
                        : providers.map(p => `
                            <div class="provider-card ${p.is_active ? 'active' : ''}">
                                <div class="provider-info">
                                    <div class="provider-name">
                                        ${escHtml(p.name)}
                                        ${p.is_active ? '<span class="badge badge-done">当前使用</span>' : ''}
                                    </div>
                                    <div class="provider-meta">
                                        ${escHtml(p.model)} | ${escHtml(p.api_base)}
                                    </div>
                                </div>
                                <div class="provider-actions">
                                    ${!p.is_active ? `<button class="btn btn-sm btn-primary" onclick="activateProvider('${p.id}')">启用</button>` : ''}
                                    <div class="dropdown-wrapper">
                                        <button class="btn btn-sm" onclick="toggleEditProvider(this, '${p.id}')">编辑</button>
                                    </div>
                                    <button class="btn btn-sm" onclick="duplicateProvider('${p.id}')">复制</button>
                                    ${providers.length > 1 ? `<button class="btn btn-sm btn-danger" onclick="deleteProviderConfirm('${p.id}')">删除</button>` : ''}
                                </div>
                            </div>
                        `).join('')
                    }
                </div>
            </div>

            <!-- 向量配置 -->
            <div class="card">
                <div class="card-header">
                    <h3>${ic('dna', 'icon-md')} 向量模型配置</h3>
                    <div id="vecSummary">
                        <span style="font-size:0.85rem;color:var(--text-secondary)">
                            后端: ${vecCfg.backend === 'sklearn' ? 'sklearn TF-IDF（轻量，无需GPU）' : vecCfg.backend === 'sentence_transformers' ? 'sentence-transformers' : '自定义 Embedding API'}
                            | 相似度阈值: ${vecCfg.similarity_threshold}
                        </span>
                    </div>
                    <div class="dropdown-wrapper">
                        <button class="btn btn-sm" onclick="toggleVectorConfigDropdown(this)">${ic('settings')} 修改配置</button>
                    </div>
                </div>
            </div>

            <!-- Reranker 精排配置 -->
            <div class="card">
                <div class="card-header">
                    <h3>${ic('target', 'icon-md')} Reranker 精排</h3>
                    <div id="rerankerSummary">
                        <span style="font-size:0.85rem;color:var(--text-secondary)">
                            ${rerankerCfg.enabled ? '已启用' : '未启用'} | ${rerankerCfg.model || '未配置模型'}
                        </span>
                    </div>
                    <div class="dropdown-wrapper">
                        <button class="btn btn-sm" onclick="toggleRerankerConfigDropdown(this)">${ic('settings')} 修改配置</button>
                    </div>
                </div>
                <p style="font-size:0.82rem;color:var(--text-secondary);padding:0 16px 12px">
                    可选功能。启用后，剧情重复检测将使用 Reranker 对初筛结果做精排，提升准确性。支持 Cohere/Jina 等兼容 API。
                </p>
            </div>

            <!-- 图片生成 API 配置 -->
            <div class="card">
                <div class="card-header">
                    <h3>${ic('palette', 'icon-md')} 图片生成 API</h3>
                    <div id="imgSummary">
                        <span style="font-size:0.85rem;color:var(--text-secondary)">
                            ${imgCfg.image_api_url ? `已配置 | ${escHtml(imgCfg.image_api_model || '默认模型')}` : '未配置（AI配图功能不可用）'}
                        </span>
                    </div>
                    <div class="dropdown-wrapper">
                        <button class="btn btn-sm" onclick="toggleImageConfigDropdown(this)">${ic('settings')} 修改配置</button>
                    </div>
                </div>
                <p style="font-size:0.82rem;color:var(--text-secondary);padding:0 16px 12px">
                    配置后可在人物画像中生成立绘、在小说详情页生成封面和场景图。支持 OpenAI 兼容的图片生成 API。
                </p>
            </div>

            <!-- Tavily 网络搜索配置 -->
            <div class="card">
                <div class="card-header">
                    <h3>${ic('globe', 'icon-md')} Tavily 网络搜索</h3>
                    <div id="tavilySummary">
                        <span style="font-size:0.85rem;color:var(--text-secondary)">
                            ${tavilyCfg.tavily_api_key ? '已配置' : '未配置（网络搜索不可用）'}
                        </span>
                    </div>
                    <div class="dropdown-wrapper">
                        <button class="btn btn-sm" onclick="toggleTavilyConfigDropdown(this)">${ic('settings')} 修改配置</button>
                    </div>
                </div>
                <p style="font-size:0.82rem;color:var(--text-secondary);padding:0 16px 12px">
                    配置后，AI 在创作时可以搜索网络获取参考资料（地名、历史、文化等）。在 <a href="https://tavily.com" target="_blank">tavily.com</a> 注册获取 API Key。
                </p>
            </div>

            <!-- 服务器绑定配置 -->
            <div class="card">
                <div class="card-header">
                    <h3>${ic('server', 'icon-md')} 服务器绑定</h3>
                    <div id="serverSummary">
                        <span style="font-size:0.85rem;color:var(--text-secondary)">
                            ${serverCfg.host}:${serverCfg.port}
                        </span>
                    </div>
                    <div class="dropdown-wrapper">
                        <button class="btn btn-sm" onclick="toggleServerConfigDropdown(this)">${ic('settings')} 修改配置</button>
                    </div>
                </div>
                <p style="font-size:0.82rem;color:var(--text-secondary);padding:0 16px 12px">
                    127.0.0.1 = 仅本机访问；0.0.0.0 = 允许局域网/远程访问。修改后需${ic('rotate-cw', 'icon-sm')}重启应用生效。
                </p>
            </div>
        `;

        // Store configs for the dropdowns
        window._vecCfg = vecCfg;
        window._rerankerCfg = rerankerCfg;
        window._imgCfg = imgCfg;
        window._tavilyCfg = tavilyCfg;
        window._serverCfg = serverCfg;
    } catch (e) {
        main.innerHTML = `<div class="empty-state"><p>加载失败: ${escHtml(e.message)}</p></div>`;
    }
}

// ==================== Provider Management ====================

async function _loadProviderForEdit(providerId) {
    try {
        // get full provider without mask
        const { providers } = await API.get('/api/providers');
        return providers.find(p => p.id === providerId);
    } catch (e) {
        return null;
    }
}

function toggleAddProvider(btn) {
    toggleDropdown(btn, `
        <h3 style="margin-bottom:14px;font-size:1.05rem">添加 LLM 供应商</h3>
        <div class="form-group">
            <label>供应商名称</label>
            <input type="text" id="addProvName" placeholder="如：OpenAI / DeepSeek / 硅基流动">
        </div>
        <div class="form-group">
            <label>API Base URL</label>
            <input type="text" id="addProvBase" placeholder="https://api.openai.com/v1">
        </div>
        <div class="form-group">
            <label>API Key</label>
            <input type="password" id="addProvKey" placeholder="sk-...">
        </div>
        <div class="form-group">
            <label>模型名称</label>
            <input type="text" id="addProvModel" placeholder="gpt-4o">
        </div>
        <div class="form-group">
            <label>Chat 端点路径</label>
            <input type="text" id="addProvPath" value="/chat/completions" placeholder="/chat/completions">
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>Temperature</label>
                <input type="number" id="addProvTemp" value="0.8" min="0" max="2" step="0.1">
            </div>
            <div class="form-group">
                <label>Max Tokens</label>
                <input type="number" id="addProvMaxTok" value="4096" min="256" max="32768" step="256">
            </div>
        </div>
        <button class="btn btn-primary" onclick="addProvider()" style="width:100%">添加</button>
    `, true);
}

async function addProvider() {
    try {
        await API.post('/api/providers', {
            name: document.getElementById('addProvName').value,
            api_base: document.getElementById('addProvBase').value,
            api_key: document.getElementById('addProvKey').value,
            model: document.getElementById('addProvModel').value,
            chat_path: document.getElementById('addProvPath').value,
            temperature: parseFloat(document.getElementById('addProvTemp').value),
            max_tokens: parseInt(document.getElementById('addProvMaxTok').value),
        });
        closeAllDropdowns();
        showToast('供应商已添加', 'success');
        navigate('settings');
    } catch (e) {
        showToast('添加失败: ' + e.message, 'error');
    }
}

async function toggleEditProvider(btn, providerId) {
    const p = await _loadProviderForEdit(providerId);
    if (!p) { showToast('加载供应商失败', 'error'); return; }
    toggleDropdown(btn, `
        <h3 style="margin-bottom:14px;font-size:1.05rem">编辑: ${escHtml(p.name)}</h3>
        <div class="form-group">
            <label>供应商名称</label>
            <input type="text" id="editProvName" value="${escAttr(p.name)}">
        </div>
        <div class="form-group">
            <label>API Base URL</label>
            <input type="text" id="editProvBase" value="${escAttr(p.api_base)}">
        </div>
        <div class="form-group">
            <label>API Key</label>
            <input type="password" id="editProvKey" value="${escAttr(p.api_key)}" placeholder="未修改则留空">
            <small style="color:var(--text-secondary)">已掩码，不修改请留空</small>
        </div>
        <div class="form-group">
            <label>模型名称</label>
            <input type="text" id="editProvModel" value="${escAttr(p.model)}">
        </div>
        <div class="form-group">
            <label>Chat 端点路径</label>
            <input type="text" id="editProvPath" value="${escAttr(p.chat_path)}">
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>Temperature</label>
                <input type="number" id="editProvTemp" value="${p.temperature}" min="0" max="2" step="0.1">
            </div>
            <div class="form-group">
                <label>Max Tokens</label>
                <input type="number" id="editProvMaxTok" value="${p.max_tokens}" min="256" max="32768" step="256">
            </div>
        </div>
        <button class="btn btn-primary" onclick="saveProvider('${p.id}')" style="width:100%">保存</button>
    `, true);
}

async function saveProvider(providerId) {
    const keyVal = document.getElementById('editProvKey').value;
    const body = {
        name: document.getElementById('editProvName').value,
        api_base: document.getElementById('editProvBase').value,
        model: document.getElementById('editProvModel').value,
        chat_path: document.getElementById('editProvPath').value,
        temperature: parseFloat(document.getElementById('editProvTemp').value),
        max_tokens: parseInt(document.getElementById('editProvMaxTok').value),
    };
    // 如果用户修改了 key（不以 *** 结尾），才发送
    if (keyVal && !keyVal.endsWith('***')) {
        body.api_key = keyVal;
    }
    try {
        await API.put(`/api/providers/${providerId}`, body);
        closeAllDropdowns();
        showToast('供应商已更新', 'success');
        navigate('settings');
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

async function activateProvider(providerId) {
    try {
        await API.post(`/api/providers/${providerId}/activate`, {});
        showToast('已切换供应商', 'success');
        navigate('settings');
    } catch (e) {
        showToast('切换失败: ' + e.message, 'error');
    }
}

async function duplicateProvider(providerId) {
    try {
        await API.post(`/api/providers/${providerId}/duplicate`, {});
        showToast('已复制供应商', 'success');
        navigate('settings');
    } catch (e) {
        showToast('复制失败: ' + e.message, 'error');
    }
}

async function deleteProviderConfirm(providerId) {
    if (!await confirmDialog('确定要删除这个供应商吗？', { icon: 'danger', confirmText: '删除', danger: true })) return;
    try {
        await API.del(`/api/providers/${providerId}`);
        showToast('供应商已删除', 'success');
        navigate('settings');
    } catch (e) {
        showToast('删除失败: ' + e.message, 'error');
    }
}

// ==================== Vector Config Dropdown ====================

function toggleVectorConfigDropdown(btn) {
    const cfg = window._vecCfg || {};
    const isVecST = cfg.backend === 'sentence_transformers';
    const isVecAPI = cfg.backend === 'openai';
    const useIndep = cfg.use_independent_embedding;

    const html = `
        <h3 style="margin-bottom:8px;font-size:1.05rem">${ic('dna', 'icon-md')} 向量模型配置</h3>
        <p style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:16px;padding:8px;background:var(--bg-card);border-radius:var(--radius-sm)">
            作用域：全站所有小说的剧情重复检测和章节内容搜索。<br>
            选择「复用活跃供应商」时自动使用当前 LLM 供应商的 API 地址和密钥。
        </p>
        <div class="form-group">
            <label>后端引擎</label>
            <input type="hidden" id="vecBackend" value="${cfg.backend || 'sklearn'}">
            <div class="option-group" id="vecBackendGroup">
                <button class="option-btn ${cfg.backend === 'sklearn' ? 'active' : ''}" data-val="sklearn">sklearn TF-IDF（轻量，无需GPU）</button>
                <button class="option-btn ${isVecST ? 'active' : ''}" data-val="sentence_transformers">sentence-transformers（需PyTorch）</button>
                <button class="option-btn ${isVecAPI ? 'active' : ''}" data-val="openai">自定义 Embedding API</button>
            </div>
        </div>
        <div id="vecStGroup" class="vec-cond" style="display:${isVecST ? '' : 'none'}">
            <div class="form-group">
                <label>模型名称</label>
                <input type="text" id="vecModelName" value="${escAttr(cfg.model_name)}" placeholder="paraphrase-multilingual-MiniLM-L12-v2">
            </div>
            <div class="form-group">
                <label>设备</label>
                <input type="hidden" id="vecDevice" value="${cfg.device || 'cpu'}">
                <div class="option-group" id="vecDeviceGroup">
                    <button class="option-btn ${cfg.device === 'cpu' ? 'active' : ''}" data-val="cpu">CPU</button>
                    <button class="option-btn ${cfg.device === 'cuda' ? 'active' : ''}" data-val="cuda">CUDA (GPU)</button>
                </div>
            </div>
        </div>
        <div id="vecApiGroup" class="vec-cond" style="display:${isVecAPI ? '' : 'none'}">
            <div class="form-group">
                <label>API 配置方式</label>
                <input type="hidden" id="vecUseIndep" value="${useIndep ? '1' : '0'}">
                <div class="option-group" id="vecUseIndepGroup">
                    <button class="option-btn ${!useIndep ? 'active' : ''}" data-val="0">复用活跃供应商</button>
                    <button class="option-btn ${useIndep ? 'active' : ''}" data-val="1">独立 Embedding API</button>
                </div>
            </div>
            <div id="vecIndepFields" class="vec-cond" style="display:${useIndep ? '' : 'none'}">
                <div class="form-group">
                    <label>Embedding API Base URL</label>
                    <input type="text" id="vecApiBase" value="${escAttr(cfg.embedding_api_base)}" placeholder="https://api.openai.com/v1">
                </div>
                <div class="form-group">
                    <label>Embedding API Key</label>
                    <input type="password" id="vecApiKey" value="${escAttr(cfg.embedding_api_key)}" placeholder="sk-...">
                </div>
                <div class="form-group">
                    <label>Embedding 端点路径</label>
                    <input type="text" id="vecEmbeddingPath" value="${escAttr(cfg.embedding_path)}" placeholder="/embeddings">
                </div>
            </div>
            <div class="form-group">
                <label>Embedding 模型名</label>
                <input type="text" id="vecEmbeddingModel" value="${escAttr(cfg.embedding_model)}" placeholder="text-embedding-3-small">
            </div>
        </div>
        <div class="form-group">
            <label>相似度阈值</label>
            <input type="number" id="vecThreshold" value="${cfg.similarity_threshold}" min="0.1" max="1" step="0.05">
            <small style="color:var(--text-secondary)">超过此值视为剧情重复</small>
        </div>
        <button class="btn btn-primary" onclick="saveVectorConfig()" style="width:100%">${ic('save')} 保存</button>
    `;

    toggleDropdown(btn, html, true);

    // Bind option-group toggle events + backend switch
    setTimeout(() => {
        ['vecBackendGroup', 'vecDeviceGroup', 'vecUseIndepGroup'].forEach(gid => {
            const group = document.getElementById(gid);
            if (!group) return;
            group.addEventListener('click', function(e) {
                const btn = e.target.closest('.option-btn');
                if (!btn) return;
                const val = btn.dataset.val;
                const hiddenId = gid.replace('Group', '');
                const hidden = document.getElementById(hiddenId);
                if (hidden) hidden.value = val;
                // Update active state
                group.querySelectorAll('.option-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                // If backend changed, toggle conditional fields
                if (gid === 'vecBackendGroup') {
                    const st = document.getElementById('vecStGroup');
                    const api = document.getElementById('vecApiGroup');
                    if (st) st.style.display = val === 'sentence_transformers' ? '' : 'none';
                    if (api) api.style.display = val === 'openai' ? '' : 'none';
                }
                if (gid === 'vecUseIndepGroup') {
                    const f = document.getElementById('vecIndepFields');
                    if (f) f.style.display = val === '1' ? '' : 'none';
                }
            });
        });
    }, 50);
}

async function saveVectorConfig() {
    try {
        const backend = document.getElementById('vecBackend').value;
        const useIndep = backend === 'openai' && document.getElementById('vecUseIndep').value === '1';
        const keyVal = document.getElementById('vecApiKey').value;
        const body = {
            backend: backend,
            model_name: document.getElementById('vecModelName').value,
            similarity_threshold: parseFloat(document.getElementById('vecThreshold').value),
            device: document.getElementById('vecDevice').value,
            use_independent_embedding: useIndep,
            embedding_api_base: document.getElementById('vecApiBase').value,
            embedding_model: document.getElementById('vecEmbeddingModel').value,
            embedding_path: document.getElementById('vecEmbeddingPath').value,
        };
        if (keyVal && !keyVal.endsWith('***')) {
            body.embedding_api_key = keyVal;
        }
        await API.put('/api/config/vector', body);
        closeAllDropdowns();
        showToast('向量配置已保存', 'success');
        // Refresh summary
        const summary = document.getElementById('vecSummary');
        if (summary) {
            const label = backend === 'sklearn' ? 'sklearn TF-IDF（轻量，无需GPU）' : backend === 'sentence_transformers' ? 'sentence-transformers' : '自定义 Embedding API';
            summary.innerHTML = `<span style="font-size:0.85rem;color:var(--text-secondary)">后端: ${label} | 相似度阈值: ${body.similarity_threshold}</span>`;
        }
        // Update cached config
        window._vecCfg = { ...window._vecCfg, ...body };
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

// ==================== Import Files ====================
async function importFile(input, type) {
    const file = input.files?.[0];
    if (!file) return;

    const formData = new FormData();
    if (type === 'outline') formData.append('outline_file', file);
    else if (type === 'world') formData.append('world_file', file);
    else if (type === 'character') formData.append('character_file', file);

    try {
        const data = await API.upload(`/api/novels/${currentNovelId}/import`, formData);
        showToast(`${type === 'outline' ? '大纲' : type === 'world' ? '世界观' : '人物画像'} 导入成功`, 'success');
        navigate('novel-detail', { novelId: currentNovelId });
    } catch (e) {
        showToast('导入失败: ' + e.message, 'error');
    }
}

// ==================== Novel Settings Save ====================
async function saveNovelSettings() {
    try {
        const payload = {
            title: document.getElementById('novelTitle').value,
            title_mode: document.getElementById('novelTitleMode').value,
            outline: document.getElementById('novelOutline').value,
            world_building: document.getElementById('novelWorldBuilding').value,
            words_per_chapter: parseInt(document.getElementById('novelWordsPerChapter').value),
            duplicate_check_interval: parseInt(document.getElementById('novelDupInterval').value),
            summary_chapters_count: parseInt(document.getElementById('novelSummaryCount').value),
        };
        const ecInput = document.getElementById('expectedChapters');
        if (ecInput) payload.expected_chapters = parseInt(ecInput.value) || 0;
        await API.put(`/api/novels/${currentNovelId}`, payload);
        showToast('设定已保存', 'success');
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

// 保存预期章节数（onchange 触发，独立保存）
let _saveExpectedChaptersTimer = null;
async function saveExpectedChapters() {
    const val = parseInt(document.getElementById('expectedChapters').value) || 0;
    // debounce，避免连续修改时频繁请求
    if (_saveExpectedChaptersTimer) clearTimeout(_saveExpectedChaptersTimer);
    _saveExpectedChaptersTimer = setTimeout(async () => {
        try {
            await API.put(`/api/novels/${currentNovelId}`, { expected_chapters: val });
            if (currentNovel) currentNovel.expected_chapters = val;
            showToast('预期章节数已保存', 'success');
        } catch (e) {
            showToast('保存失败: ' + e.message, 'error');
        }
        _saveExpectedChaptersTimer = null;
    }, 400);
}

// 保存 Token 预算（onchange 触发）
let _saveMaxTokensTimer = null;
async function saveNovelMaxTokens() {
    const val = parseInt(document.getElementById('novelMaxTokens').value) || 8192;
    if (_saveMaxTokensTimer) clearTimeout(_saveMaxTokensTimer);
    _saveMaxTokensTimer = setTimeout(async () => {
        try {
            await API.put(`/api/novels/${currentNovelId}`, { max_tokens: val });
            if (currentNovel) currentNovel.max_tokens = val;
            showToast('Token 预算已保存', 'success');
        } catch (e) {
            showToast('保存失败: ' + e.message, 'error');
        }
        _saveMaxTokensTimer = null;
    }, 400);
}

// AI 生成大纲弹窗（自定义提示词）
function toggleOutlineGenDropdown(btn) {
    const expected = currentNovel?.expected_chapters || 0;
    toggleDropdown(btn, `
        <h3 style="margin-bottom:8px;font-size:1.05rem">${ic('sparkles', 'icon-md')} AI 生成大纲</h3>
        <p style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:12px">AI 将根据书名、世界观、人物画像等信息生成大纲${expected > 0 ? `，按 ${expected} 章规划` : ''}</p>
        <div class="form-group">
            <label>自定义提示词（可选）</label>
            <textarea id="outlineCustomPrompt" rows="4" placeholder="例如：以悬疑开头，每个章节都有反转；主角是反英雄角色；结局是开放式的..." style="width:100%;resize:vertical"></textarea>
        </div>
        <div class="inline-flex" style="justify-content:flex-end">
            <button class="btn btn-primary" onclick="generateOutline()">${ic('sparkles')} 开始生成</button>
        </div>
    `, true);
}

async function generateOutline() {
    const customPrompt = document.getElementById('outlineCustomPrompt').value.trim();
    closeAllDropdowns();
    showToast('正在生成大纲...', 'info');
    try {
        const data = await API.post(`/api/novels/${currentNovelId}/generate-outline`, { custom_prompt: customPrompt });
        const textarea = document.getElementById('novelOutline');
        if (textarea) {
            textarea.value = data.outline;
            // 同步保存到后端
            try { await API.put(`/api/novels/${currentNovelId}`, { outline: data.outline }); } catch (e) { /* ignore */ }
        }
        showToast('大纲生成完成', 'success');
    } catch (e) {
        showToast('生成失败: ' + e.message, 'error');
    }
}

async function saveStyleReference() {
    try {
        const ref = document.getElementById('novelStyleReference').value;
        await API.put(`/api/novels/${currentNovelId}`, { style_reference: ref });
        showToast('文风参考已保存', 'success');
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

// ==================== Style Analysis ====================

function toggleAnalyzeStyleFromChapters(btn) {
    // Fetch chapters dynamically for the dropdown
    API.get(`/api/novels/${currentNovelId}/chapters`).then(({ chapters }) => {
        if (!chapters.length) {
            toggleDropdown(btn, '<p style="padding:8px;color:var(--text-secondary)">暂无章节可供分析</p>', true);
            return;
        }
        const html = `
            <h3 style="margin-bottom:14px;font-size:1.05rem">${ic('list-ordered', 'icon-md')} 从章节分析文风</h3>
            <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:12px">
                选择 1-3 个章节，AI 将分析其文风特征并提炼描述。
            </p>
            <div id="styleChaptersSelect" style="max-height:240px;overflow-y:auto;margin-bottom:12px">
                ${chapters.map(ch => `
                    <label style="display:flex;align-items:center;gap:8px;padding:8px;border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:6px;cursor:pointer">
                        <input type="checkbox" value="${ch.id}" style="width:auto">
                        <span style="flex:1;font-size:0.88rem">#${ch.number} ${escHtml(ch.title)} <span style="color:var(--text-secondary)">(${ch.words_count}字)</span></span>
                    </label>
                `).join('')}
            </div>
            <button class="btn btn-primary" onclick="analyzeStyleFromChapters()" style="width:100%">${ic('bot')} AI 分析文风</button>
        `;
        toggleDropdown(btn, html, true);
    }).catch(() => showToast('加载章节失败', 'error'));
}

async function analyzeStyleFromChapters() {
    const checkboxes = document.querySelectorAll('#styleChaptersSelect input:checked');
    const ids = Array.from(checkboxes).map(cb => cb.value);
    if (!ids.length) { showToast('请至少选择一个章节', 'error'); return; }

    const btn = document.querySelector('.dropdown-panel button[onclick*="analyzeStyleFromChapters"]');
    if (btn) { btn.disabled = true; btn.textContent = '分析中...'; }

    // 在下拉面板下方添加实时输出区域
    const panel = document.querySelector('.dropdown-panel');
    let outputDiv = panel.querySelector('#styleStreamOutput');
    if (!outputDiv) {
        outputDiv = document.createElement('div');
        outputDiv.id = 'styleStreamOutput';
        outputDiv.style.cssText = 'margin-top:12px;padding:12px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);max-height:200px;overflow-y:auto;font-size:0.85rem;line-height:1.6;white-space:pre-wrap';
        panel.appendChild(outputDiv);
    }
    outputDiv.innerHTML = '<span style="color:var(--text-secondary)">正在分析文风...</span>';

    try {
        const { reader, response: r } = await streamFetch(`/api/novels/${currentNovelId}/analyze-style`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...(authToken ? { 'Authorization': 'Bearer ' + authToken } : {}) },
            body: JSON.stringify({ chapter_ids: ids }),
        });
        if (r.status === 401) { showLoginPage(); return; }
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);

        const decoder = new TextDecoder();
        let buffer = '';
        let fullText = '';
        let finalStyle = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const payload = line.slice(6);
                if (payload === '[DONE]') break;
                try {
                    const msg = JSON.parse(payload);
                    if (msg.type === 'chunk') {
                        fullText += msg.data;
                        outputDiv.textContent = fullText;
                        outputDiv.scrollTop = outputDiv.scrollHeight;
                    } else if (msg.type === 'done') {
                        finalStyle = msg.style_reference;
                    } else if (msg.type === 'error') {
                        throw new Error(msg.message);
                    }
                } catch (e) {
                    if (e.message) throw e;
                }
            }
        }

        closeAllDropdowns();
        const ta = document.getElementById('novelStyleReference');
        if (ta) ta.value = finalStyle || fullText;
        showToast('文风分析完成', 'success');
    } catch (e) {
        showToast('分析失败: ' + e.message, 'error');
        if (btn) { btn.disabled = false; btn.innerHTML = `${ic('bot')} AI 分析文风`; }
    }
}

function toggleAnalyzeStyleFromFile(btn) {
    const html = `
        <h3 style="margin-bottom:14px;font-size:1.05rem">${ic('folder', 'icon-md')} 上传文档分析文风</h3>
        <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:12px">
            上传 .txt 或 .md 文件，AI 将分析其文风特征。
        </p>
        <div class="form-group">
            <input type="file" id="styleFileInput" accept=".txt,.md">
        </div>
        <button class="btn btn-primary" onclick="analyzeStyleFromFile()" style="width:100%">${ic('bot')} AI 分析文风</button>
    `;
    toggleDropdown(btn, html, true);
}

async function analyzeStyleFromFile() {
    const input = document.getElementById('styleFileInput');
    if (!input || !input.files[0]) { showToast('请选择文件', 'error'); return; }
    const formData = new FormData();
    formData.append('file', input.files[0]);

    const btn = document.querySelector('.dropdown-panel button[onclick*="analyzeStyleFromFile"]');
    if (btn) { btn.disabled = true; btn.textContent = '分析中...'; }

    // 实时输出区域
    const panel = document.querySelector('.dropdown-panel');
    let outputDiv = panel.querySelector('#styleStreamOutput');
    if (!outputDiv) {
        outputDiv = document.createElement('div');
        outputDiv.id = 'styleStreamOutput';
        outputDiv.style.cssText = 'margin-top:12px;padding:12px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);max-height:200px;overflow-y:auto;font-size:0.85rem;line-height:1.6;white-space:pre-wrap';
        panel.appendChild(outputDiv);
    }
    outputDiv.innerHTML = '<span style="color:var(--text-secondary)">正在分析文风...</span>';

    try {
        const { reader, response: r } = await streamFetch(`/api/novels/${currentNovelId}/analyze-style-upload`, {
            method: 'POST', body: formData,
            headers: authToken ? { 'Authorization': 'Bearer ' + authToken } : {},
        });
        if (r.status === 401) { showLoginPage(); return; }
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);

        const decoder = new TextDecoder();
        let buffer = '';
        let fullText = '';
        let finalStyle = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const payload = line.slice(6);
                if (payload === '[DONE]') break;
                try {
                    const msg = JSON.parse(payload);
                    if (msg.type === 'chunk') {
                        fullText += msg.data;
                        outputDiv.textContent = fullText;
                        outputDiv.scrollTop = outputDiv.scrollHeight;
                    } else if (msg.type === 'done') {
                        finalStyle = msg.style_reference;
                    } else if (msg.type === 'error') {
                        throw new Error(msg.message);
                    }
                } catch (e) {
                    if (e.message) throw e;
                }
            }
        }

        closeAllDropdowns();
        const ta = document.getElementById('novelStyleReference');
        if (ta) ta.value = finalStyle || fullText;
        showToast('文风分析完成', 'success');
    } catch (e) {
        showToast('分析失败: ' + e.message, 'error');
        if (btn) { btn.disabled = false; btn.innerHTML = `${ic('bot')} AI 分析文风`; }
    }
}

// ==================== Manual Chapter ====================

async function createManualChapter() {
    try {
        const { chapters } = await API.get(`/api/novels/${currentNovelId}/chapters`);
        const nextNum = chapters.length + 1;

        const html = `
            <h3 style="margin-bottom:12px;font-size:1rem">${ic('pencil', 'icon-md')} 手动创建章节</h3>
            <div class="form-group">
                <label>章节标题</label>
                <input type="text" id="manualChapterTitle" placeholder="第${nextNum}章（留空自动编号）" style="width:100%">
            </div>
            <div class="form-group">
                <label>章节序号</label>
                <input type="number" id="manualChapterNumber" value="${nextNum}" min="1" style="width:80px">
            </div>
            <button class="btn btn-primary" onclick="confirmCreateManualChapter()" style="width:100%">创建并编辑</button>
            <p style="margin-top:8px;font-size:0.8rem;color:var(--text-secondary)">创建后自动跳转到编辑页面，可在编辑器中编写正文。</p>
        `;
        toggleDropdown(event.target, html, false);
    } catch (e) {
        showToast('创建失败: ' + e.message, 'error');
    }
}

async function confirmCreateManualChapter() {
    const title = document.getElementById('manualChapterTitle')?.value.trim() || '';
    const number = parseInt(document.getElementById('manualChapterNumber')?.value) || 1;
    try {
        const { chapter } = await API.post(`/api/novels/${currentNovelId}/chapters/manual`, {
            title: title || `第${number}章`,
            content: '',
            chapter_number: number,
        });
        closeAllDropdowns();
        showToast('章节已创建', 'success');
        navigate('chapter-edit', { chapterId: chapter.id, novelId: currentNovelId });
    } catch (e) {
        showToast('创建失败: ' + e.message, 'error');
    }
}

// ==================== Delete Confirmations ====================
async function deleteNovelConfirm(novelId) {
    if (!await confirmDialog('确定要删除这部小说吗？所有章节将被永久删除。', { icon: 'danger', confirmText: '删除', danger: true })) return;
    try {
        await API.del(`/api/novels/${novelId}`);
        showToast('小说已删除', 'success');
        navigate('novels');
    } catch (e) {
        showToast('删除失败: ' + e.message, 'error');
    }
}

async function deleteChapterConfirm(chapterId) {
    if (!await confirmDialog('确定要删除这一章吗？', { icon: 'danger', confirmText: '删除', danger: true })) return;
    try {
        await API.del(`/api/chapters/${chapterId}`);
        showToast('章节已删除', 'success');
        // 局部刷新章节列表（如果当前在小说详情页且有章节列表容器）
        const list = document.getElementById('chapterList');
        if (list) {
            try {
                const { chapters } = await API.get(`/api/novels/${currentNovelId}/chapters`);
                _renderChapterList(chapters || []);
            } catch (e) {
                // 局部刷新失败则回退到整页刷新
                navigate('novel-detail', { novelId: currentNovelId });
            }
        } else {
            // 不在小说详情页（可能在阅读页等），整页刷新
            navigate('novel-detail', { novelId: currentNovelId });
        }
    } catch (e) {
        showToast('删除失败: ' + e.message, 'error');
    }
}

// ==================== Utilities ====================
function escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escAttr(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Security: 校验 URL 协议仅允许 http/https，防止 javascript: XSS
function safeUrl(url) {
    if (!url) return '';
    try {
        const u = new URL(url, location.origin);
        if (['http:', 'https:'].includes(u.protocol)) return url;
        return '';
    } catch { return ''; }
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

// ==================== Continuous Generation ====================

async function startContinuousGenerate() {
    // 导航到连续创作配置页面（不再弹 Modal 直接开始）
    // 用户可以在配置页面设置整体走向和每章走向
    if (!currentNovelId) {
        showToast('请先选择小说', 'error');
        return;
    }
    navigate('batch-generate', { novelId: currentNovelId });
}

async function startBatchGeneration(count, providerId = '', suggestions = '', chapterDirections = null) {
    // 优先使用传入的 providerId，否则从页面读取（兼容手动调用）
    if (!providerId) {
        providerId = document.getElementById('genProviderId')?.value || '';
    }
    const output = document.getElementById('streamOutput');
    const hasChapterDirs = chapterDirections && chapterDirections.some(s => s && s.trim());
    if (output) output.innerHTML = `<p style="color:var(--text-secondary)">连续创作模式：将生成 ${count} 章${suggestions ? '（含整体走向）' : ''}${hasChapterDirs ? '（含每章走向）' : ''}</p>`;

    const formData = new FormData();
    formData.append('chapter_count', count);
    formData.append('provider_id', providerId);
    if (suggestions) formData.append('suggestions', suggestions);
    // 传递每章独立的走向（JSON 数组）
    if (chapterDirections && Array.isArray(chapterDirections)) {
        formData.append('chapter_suggestions', JSON.stringify(chapterDirections));
    }

    // 立即触发一次任务轮询，让侧边栏尽快显示创作进度
    // （不等待默认的 10 秒轮询间隔）
    setTimeout(() => pollActiveTasks(), 500);

    try {
        const { reader, response: r } = await streamFetch(`/api/novels/${currentNovelId}/chapters/batch-generate`, {
            method: 'POST', body: formData,
            headers: authToken ? { 'Authorization': 'Bearer ' + authToken } : {},
        });
        if (r.status === 401) { showLoginPage(); return; }
        const decoder = new TextDecoder();
        let buffer = '';
        let chapterIdx = 0;
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const payload = line.slice(6);
                if (payload === '[DONE]') break;
                try {
                    const msg = JSON.parse(payload);
                    if (msg.type === 'chapter_start') {
                        if (output) output.innerHTML += `<div style="margin-top:12px;padding:8px;background:var(--bg-card);border-left:3px solid var(--accent);border-radius:var(--radius-sm);font-weight:600">${ic('book-open', 'icon-sm')} 正在生成第 ${msg.number}/${msg.total} 章...</div>`;
                        // 清空思考区，准备新章节
                        const thinkOut = document.getElementById('thinkingOutput');
                        if (thinkOut) thinkOut.innerHTML = '';
                    } else if (msg.type === 'chapter_done') {
                        chapterIdx = msg.number || (chapterIdx + 1);
                        showToast(`第 ${chapterIdx}/${count} 章创作完成`, 'success');
                        if (output) output.innerHTML += `<div style="margin-top:4px;padding:6px 8px;background:var(--accent-light);border-radius:var(--radius-sm);font-size:0.9rem">${ic('check', 'icon-sm')} 第 ${chapterIdx} 章「${escHtml(msg.chapter.title)}」已完成 (${msg.chapter.words_count}字)</div>`;
                    } else if (msg.type === 'pending_changes') {
                        // 累积本批次所有章节的待确认变更
                        if (!window._batchPendingChanges) window._batchPendingChanges = [];
                        window._batchPendingChanges = window._batchPendingChanges.concat(msg.data);
                        if (output) {
                            output.innerHTML += `<div style="margin-top:4px;padding:4px 8px;background:#fff3cd;border-radius:var(--radius-sm);font-size:0.85rem;color:#856404">${ic('edit', 'icon-sm')} 第 ${(msg.data[0]||{}).chapter_number||''}章产生 ${msg.count} 条设定修改提议（生成完成后统一确认）</div>`;
                        }
                    } else if (msg.type === 'batch_complete') {
                        if (output) output.innerHTML += `<div style="margin-top:16px;padding:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);text-align:center;font-weight:600">${ic('party-popper', 'icon-sm')} 连续创作完成！共生成 ${chapterIdx} 章</div>`;
                        showToast('连续创作完成', 'success');
                        // 批次完成后展示累积的待确认变更
                        if (window._batchPendingChanges && window._batchPendingChanges.length > 0) {
                            setTimeout(() => showPendingChangesDialog(window._batchPendingChanges, window._batchPendingChanges.length), 1000);
                        }
                    } else if (msg.type === 'batch_aborted') {
                        if (output) output.innerHTML += `<div style="margin-top:12px;padding:8px;color:var(--warning)">${ic('square', 'icon-sm')} 已中止，已完成 ${msg.completed} 章</div>`;
                        showToast('批量生成已中止', 'info');
                    } else if (msg.type === 'tool_call') {
                        const label = TOOL_LABELS[msg.name] || escHtml(msg.name);
                        const args = msg.args && Object.keys(msg.args).length ? `（${Object.values(msg.args).map(v => escHtml(String(v))).join('、')}）` : '';
                        const thinkOut = document.getElementById('thinkingOutput');
                        if (thinkOut) {
                            thinkOut.innerHTML += `<div style="padding:3px 0;color:#4a9">${ic('wrench', 'icon-sm')} ${label}${args}</div>`;
                            thinkOut.scrollTop = thinkOut.scrollHeight;
                            showThinkingIfNeeded();
                        }
                    } else if (msg.type === 'tool_result') {
                        const thinkOut = document.getElementById('thinkingOutput');
                        if (thinkOut) {
                            thinkOut.innerHTML += `<div style="padding:2px 0 6px 16px;color:var(--text-secondary);font-size:0.8rem;border-left:2px solid var(--border);margin-left:4px">${ic('corner-down-right', 'icon-sm')} ${escHtml(msg.preview || '')}</div>`;
                            thinkOut.scrollTop = thinkOut.scrollHeight;
                        }
                    } else if (msg.type === 'thinking') {
                        const thinkOut = document.getElementById('thinkingOutput');
                        if (thinkOut) {
                            // 增量推理和重分类都直接追加到思考区（批量模式不维护 fullContent）
                            thinkOut.innerHTML += `<div style="padding:4px 0;color:var(--text-secondary)">${escHtml(msg.data)}</div>`;
                            thinkOut.scrollTop = thinkOut.scrollHeight;
                            showThinkingIfNeeded();
                        }
                    } else if (msg.type === 'content_replace') {
                        // 批量模式忽略内容替换事件
                    } else if (msg.type === 'error') {
                        // 错误时保留思考内容，在输出区追加错误信息
                        if (output) output.innerHTML += `<div style="margin-top:4px;padding:6px;color:var(--danger);font-size:0.85rem">${ic('x-circle', 'icon-sm')} ${escHtml(msg.message)}</div>`;
                    }
                } catch (e) { /* ignore parse errors */ }
            }
        }
    } catch (e) {
        showToast('连续创作失败: ' + e.message, 'error');
    }
}

/**
 * 处理批量创作的 SSE 事件（startBatchGeneration 和 resumeBatchStream 共用）
 * @param {Object} msg - SSE 事件消息
 * @param {Object} ctx - 上下文 { output, count, chapterIdx }
 * @returns {number} 更新后的 chapterIdx
 */
function handleBatchSSEEvent(msg, ctx) {
    const output = ctx.output;
    let chapterIdx = ctx.chapterIdx;
    // isReplay 表示当前正在重放历史事件（用户离开期间错过的）
    // 重放时：不显示"正在生成"字样，改为"已生成"；不弹 toast
    const isReplay = ctx.isReplaying === true;

    if (msg.type === 'batch_resume') {
        // 恢复流时的初始状态快照
        chapterIdx = msg.completed || 0;
        if (output) output.innerHTML = `<div style="margin-bottom:8px;padding:10px;background:var(--bg-card);border-left:3px solid var(--accent);border-radius:var(--radius-sm)">
            ${ic('refresh-cw', 'icon-sm')} 已恢复创作任务「${escHtml(msg.novel_title || '')}」<br>
            <span style="font-size:0.85rem;color:var(--text-secondary)">进度：${msg.completed}/${msg.total} 章${msg.current_chapter_number ? '，正在生成第 ' + msg.current_chapter_number + ' 章' : ''}${msg.history_count ? '（含 ' + msg.history_count + ' 条历史记录）' : ''}</span>
        </div>`;
        if (msg.history_count > 0) {
            if (output) output.innerHTML += `<div style="padding:6px 8px;background:var(--bg);border-radius:var(--radius-sm);font-size:0.8rem;color:var(--text-secondary);margin-top:4px">${ic('history', 'icon-sm')} 正在加载历史记录...</div>`;
        }
        if (msg.completed > 0 && msg.completed < msg.total) {
            if (output) output.innerHTML += `<div style="padding:8px;background:var(--bg-card);border-left:3px solid var(--accent);border-radius:var(--radius-sm);font-weight:600;margin-top:4px">${ic('book-open', 'icon-sm')} 继续生成中...</div>`;
        }
    } else if (msg.type === 'history_replay_start') {
        ctx.isReplaying = true;
        // 清空 output 中的"正在加载历史记录"提示，准备重放
        if (output) {
            const loadingHint = output.querySelector('div:last-child');
            // 保留 batch_resume 和继续生成提示，但在它们之后插入历史记录分隔符
            output.innerHTML += `<div id="historySection" style="margin-top:8px;padding:8px;background:var(--bg-card);border:1px dashed var(--border);border-radius:var(--radius-sm)">
                <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:6px;font-weight:600">${ic('history', 'icon-sm')} 历史记录（离开页面期间）</div>
                <div id="historyContent"></div>
            </div>`;
        }
    } else if (msg.type === 'history_replay_end') {
        ctx.isReplaying = false;
        // 历史记录结束，插入分隔符
        if (output) {
            const historyContent = document.getElementById('historyContent');
            if (historyContent) {
                historyContent.innerHTML += `<div style="text-align:center;padding:4px;color:var(--text-secondary);font-size:0.75rem">— 以上为历史记录 —</div>`;
            }
            output.innerHTML += `<div style="margin-top:8px;padding:6px 8px;background:var(--accent-light);border-radius:var(--radius-sm);font-size:0.85rem">${ic('radio', 'icon-sm')} 实时进度</div>`;
        }
    } else if (msg.type === 'chapter_start') {
        const label = isReplay ? '已生成' : '正在生成';
        const color = isReplay ? 'var(--text-secondary)' : 'var(--accent)';
        const targetEl = isReplay ? document.getElementById('historyContent') : output;
        if (targetEl) targetEl.innerHTML += `<div style="margin-top:8px;padding:6px 8px;background:var(--bg-card);border-left:3px solid ${color};border-radius:var(--radius-sm);font-weight:600;font-size:0.85rem">${ic('book-open', 'icon-sm')} ${label}第 ${msg.number}/${msg.total} 章${isReplay ? '' : '...'}</div>`;
        // 重放时不清空思考区（避免破坏当前状态）
        if (!isReplay) {
            const thinkOut = document.getElementById('thinkingOutput');
            if (thinkOut) thinkOut.innerHTML = '';
        }
    } else if (msg.type === 'chapter_done') {
        chapterIdx = msg.number || (chapterIdx + 1);
        if (!isReplay) {
            showToast(`第 ${chapterIdx}/${ctx.count} 章创作完成`, 'success');
        }
        const targetEl = isReplay ? document.getElementById('historyContent') : output;
        if (targetEl) targetEl.innerHTML += `<div style="margin-top:4px;padding:4px 8px;background:var(--accent-light);border-radius:var(--radius-sm);font-size:0.85rem">${ic('check', 'icon-sm')} 第 ${chapterIdx} 章「${escHtml(msg.chapter.title)}」${isReplay ? '已生成' : '已完成'} (${msg.chapter.words_count}字)</div>`;
    } else if (msg.type === 'pending_changes') {
        if (!window._batchPendingChanges) window._batchPendingChanges = [];
        window._batchPendingChanges = window._batchPendingChanges.concat(msg.data);
        const targetEl = isReplay ? document.getElementById('historyContent') : output;
        if (targetEl) {
            targetEl.innerHTML += `<div style="margin-top:4px;padding:4px 8px;background:#fff3cd;border-radius:var(--radius-sm);font-size:0.8rem;color:#856404">${ic('edit', 'icon-sm')} 第 ${(msg.data[0]||{}).chapter_number||''}章产生 ${msg.count} 条设定修改提议</div>`;
        }
    } else if (msg.type === 'batch_complete') {
        const targetEl = isReplay ? document.getElementById('historyContent') : output;
        if (targetEl) targetEl.innerHTML += `<div style="margin-top:12px;padding:10px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);text-align:center;font-weight:600;font-size:0.9rem">${ic('party-popper', 'icon-sm')} 连续创作完成！共生成 ${chapterIdx} 章</div>`;
        if (!isReplay) showToast('连续创作完成', 'success');
        if (window._batchPendingChanges && window._batchPendingChanges.length > 0 && !isReplay) {
            setTimeout(() => showPendingChangesDialog(window._batchPendingChanges, window._batchPendingChanges.length), 1000);
        }
    } else if (msg.type === 'batch_aborted') {
        const targetEl = isReplay ? document.getElementById('historyContent') : output;
        if (targetEl) targetEl.innerHTML += `<div style="margin-top:8px;padding:6px;color:var(--warning);font-size:0.85rem">${ic('square', 'icon-sm')} ${isReplay ? '已' : ''}中止，已完成 ${msg.completed} 章</div>`;
        if (!isReplay) showToast('批量生成已中止', 'info');
    } else if (msg.type === 'tool_call') {
        const label = TOOL_LABELS[msg.name] || escHtml(msg.name);
        const args = msg.args && Object.keys(msg.args).length ? `（${Object.values(msg.args).map(v => escHtml(String(v))).join('、')}）` : '';
        const thinkOut = document.getElementById('thinkingOutput');
        // 重放时也显示到思考区，但如果思考区不存在则显示到历史区
        if (thinkOut) {
            thinkOut.innerHTML += `<div style="padding:3px 0;color:#4a9;${isReplay ? 'opacity:0.7;' : ''}">${ic('wrench', 'icon-sm')} ${label}${args}</div>`;
            thinkOut.scrollTop = thinkOut.scrollHeight;
            showThinkingIfNeeded();
        }
    } else if (msg.type === 'tool_result') {
        const thinkOut = document.getElementById('thinkingOutput');
        if (thinkOut) {
            thinkOut.innerHTML += `<div style="padding:2px 0 6px 16px;color:var(--text-secondary);font-size:0.8rem;border-left:2px solid var(--border);margin-left:4px;${isReplay ? 'opacity:0.7;' : ''}">${ic('corner-down-right', 'icon-sm')} ${escHtml(msg.preview || '')}</div>`;
            thinkOut.scrollTop = thinkOut.scrollHeight;
        }
    } else if (msg.type === 'thinking') {
        const thinkOut = document.getElementById('thinkingOutput');
        if (thinkOut) {
            thinkOut.innerHTML += `<div style="padding:4px 0;color:var(--text-secondary);${isReplay ? 'opacity:0.7;' : ''}">${escHtml(msg.data)}</div>`;
            thinkOut.scrollTop = thinkOut.scrollHeight;
            showThinkingIfNeeded();
        }
    } else if (msg.type === 'content_replace') {
        // 批量模式忽略内容替换事件
    } else if (msg.type === 'error') {
        const targetEl = isReplay ? document.getElementById('historyContent') : output;
        if (targetEl) targetEl.innerHTML += `<div style="margin-top:4px;padding:6px;color:var(--danger);font-size:0.85rem">${ic('x-circle', 'icon-sm')} ${escHtml(msg.message)}</div>`;
    }

    return chapterIdx;
}

/**
 * 恢复批量创作的 SSE 流（用户离开创作页面后返回时调用）
 * 连接 GET /api/novels/{novel_id}/batch-stream，从当前进度继续接收事件
 */
async function resumeBatchStream(novelId) {
    const output = document.getElementById('streamOutput');
    if (output) output.innerHTML = `<p style="color:var(--text-secondary)">${ic('loader', 'icon-sm')} 正在恢复创作任务...</p>`;
    renderIcons();

    try {
        const { reader, response: r } = await streamFetch(`/api/novels/${novelId}/batch-stream`, {
            method: 'GET',
            headers: authToken ? { 'Authorization': 'Bearer ' + authToken } : {},
        });
        if (r.status === 401) { showLoginPage(); return; }
        if (r.status === 404) {
            // 任务不存在（可能服务重启过）
            if (output) output.innerHTML = `<div style="padding:12px;background:#fff3cd;border-radius:var(--radius);color:#856404">${ic('info', 'icon-sm')} 该创作任务已结束或不存在（可能服务已重启）</div>`;
            renderIcons();
            showToast('该创作任务已结束或不存在', 'info');
            return;
        }

        // 检查是否是 JSON 响应（任务已结束，非 SSE 流）
        const contentType = r.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            const data = await r.json();
            if (data.ok === false) {
                // 任务已结束
                const statusText = data.status === 'completed' ? '已完成' : (data.status === 'aborted' ? '已中止' : (data.status === 'failed' ? '失败' : '已结束'));
                if (output) output.innerHTML = `<div style="padding:12px;background:var(--bg-card);border-radius:var(--radius);text-align:center">
                    ${ic('check-circle', 'icon-md')}<br>
                    <div style="font-weight:600;margin-top:8px">创作任务${statusText}</div>
                    <div style="color:var(--text-secondary);font-size:0.85rem;margin-top:4px">共完成 ${data.completed}/${data.total} 章</div>
                </div>`;
                renderIcons();
                showToast(`创作任务${statusText}（${data.completed}/${data.total} 章）`, 'info');
                return;
            }
        }

        const decoder = new TextDecoder();
        let buffer = '';
        let chapterIdx = 0;
        let totalCount = 0;
        const ctx = { output, count: 0, chapterIdx: 0 };

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const payload = line.slice(6);
                if (payload === '[DONE]') break;
                try {
                    const msg = JSON.parse(payload);
                    if (msg.type === 'batch_resume') {
                        ctx.count = msg.total || 0;
                    }
                    ctx.chapterIdx = handleBatchSSEEvent(msg, ctx);
                    renderIcons();
                } catch (e) { /* ignore parse errors */ }
            }
        }
    } catch (e) {
        showToast('恢复创作任务失败: ' + e.message, 'error');
    }
}

// ==================== Reranker Config Dropdown ====================

function toggleImageConfigDropdown(btn) {
    const cfg = window._imgCfg || {};
    toggleDropdown(btn, `
        <h3 style="margin-bottom:8px;font-size:1.05rem">${ic('palette', 'icon-md')} 图片生成 API 配置</h3>
        <p style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:12px">配置 OpenAI 兼容的图片生成 API（如 DALL-E、Stable Diffusion API 等）</p>
        <div class="form-group">
            <label>API 地址</label>
            <input type="text" id="imgApiUrl" value="${escHtml(cfg.image_api_url || '')}" placeholder="https://api.openai.com/v1/images/generations">
            <p style="font-size:0.75rem;color:var(--text-secondary);margin-top:4px">可填完整地址或 Base URL（如 https://api.openai.com/v1），系统会自动补全 /images/generations 路径。请勿填聊天接口地址。</p>
        </div>
        <div class="form-group">
            <label>API Key</label>
            <input type="password" id="imgApiKey" value="${escHtml(cfg.image_api_key || '')}" placeholder="sk-..." ${cfg.image_api_key ? 'data-has-value="1"' : ''}>
            ${cfg.image_api_key ? '<p style="font-size:0.78rem;color:var(--text-secondary)">已配置 Key，留空则保留原值</p>' : ''}
        </div>
        <div class="form-group">
            <label>模型名称</label>
            <input type="text" id="imgApiModel" value="${escHtml(cfg.image_api_model || '')}" placeholder="dall-e-3">
        </div>
        <div class="inline-flex" style="justify-content:flex-end">
            <button class="btn btn-primary" onclick="saveImageConfig()">保存</button>
        </div>
    `, true);
}

async function saveImageConfig() {
    const url = document.getElementById('imgApiUrl').value.trim();
    let key = document.getElementById('imgApiKey').value.trim();
    const model = document.getElementById('imgApiModel').value.trim();
    // 如果key为空且原来有值，传 *** 保留原值
    if (!key && document.getElementById('imgApiKey').dataset.hasValue) {
        key = '***';
    }
    try {
        await API.put('/api/config/image', {
            image_api_url: url,
            image_api_key: key,
            image_api_model: model,
        });
        closeAllDropdowns();
        showToast('图片 API 配置已保存', 'success');
        navigate('settings');
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

// ==================== Tavily 网络搜索配置 ====================
function toggleTavilyConfigDropdown(btn) {
    const cfg = window._tavilyCfg || {};
    toggleDropdown(btn, `
        <h3 style="margin-bottom:8px;font-size:1.05rem">${ic('globe', 'icon-md')} Tavily 网络搜索配置</h3>
        <p style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:12px">配置后，AI 在创作时可以搜索网络获取参考资料。在 <a href="https://tavily.com" target="_blank">tavily.com</a> 注册获取 API Key。</p>
        <div class="form-group">
            <label>API Key</label>
            <input type="password" id="tavilyApiKey" value="${escHtml(cfg.tavily_api_key || '')}" placeholder="tvly-..." ${cfg.tavily_api_key ? 'data-has-value="1"' : ''}>
            ${cfg.tavily_api_key ? '<p style="font-size:0.78rem;color:var(--text-secondary)">已配置 Key，留空则保留原值</p>' : ''}
        </div>
        <div class="inline-flex" style="justify-content:flex-end">
            <button class="btn btn-primary" onclick="saveTavilyConfig()">保存</button>
        </div>
    `, true);
}

async function saveTavilyConfig() {
    let key = document.getElementById('tavilyApiKey').value.trim();
    // 如果key为空且原来有值，传 *** 保留原值
    if (!key && document.getElementById('tavilyApiKey').dataset.hasValue) {
        key = '***';
    }
    try {
        await API.put('/api/config/tavily', { tavily_api_key: key });
        closeAllDropdowns();
        showToast('Tavily 配置已保存', 'success');
        navigate('settings');
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

// ==================== 服务器绑定配置 ====================
function toggleServerConfigDropdown(btn) {
    const cfg = window._serverCfg || { host: '127.0.0.1', port: 8000 };
    toggleDropdown(btn, `
        <h3 style="margin-bottom:8px;font-size:1.05rem">${ic('server', 'icon-md')} 服务器绑定配置</h3>
        <p style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:12px">
            修改后需要${ic('rotate-cw', 'icon-sm')}重启应用才能生效。环境变量 NOVEL_WRITER_HOST / NOVEL_WRITER_PORT 可覆盖此配置。
        </p>
        <div class="form-group">
            <label>绑定地址</label>
            <select id="serverHost">
                <option value="127.0.0.1" ${cfg.host === '127.0.0.1' ? 'selected' : ''}>127.0.0.1（仅本机访问）</option>
                <option value="0.0.0.0" ${cfg.host === '0.0.0.0' ? 'selected' : ''}>0.0.0.0（允许局域网/远程访问）</option>
            </select>
            <p style="font-size:0.78rem;color:var(--text-secondary);margin-top:4px">0.0.0.0 会将服务暴露到网络，建议配合防火墙或反向代理使用</p>
        </div>
        <div class="form-group">
            <label>端口</label>
            <input type="number" id="serverPort" value="${cfg.port}" min="1" max="65535">
        </div>
        <div class="inline-flex" style="justify-content:flex-end">
            <button class="btn btn-primary" onclick="saveServerConfig()">保存</button>
        </div>
    `, true);
}

async function saveServerConfig() {
    const host = document.getElementById('serverHost').value;
    const port = parseInt(document.getElementById('serverPort').value) || 8000;
    try {
        await API.put('/api/config/server', { host, port });
        closeAllDropdowns();
        showToast('服务器配置已保存，点击侧边栏「重启应用」生效', 'success');
        navigate('settings');
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

function toggleRerankerConfigDropdown(btn) {
    const cfg = window._rerankerCfg || {};
    const html = `
        <h3 style="margin-bottom:8px;font-size:1.05rem">${ic('target', 'icon-md')} Reranker 精排配置</h3>
        <p style="color:var(--text-secondary);font-size:0.82rem;margin-bottom:16px;padding:8px;background:var(--bg-card);border-radius:var(--radius-sm)">
            作用域：全站所有小说的章节内容搜索精排。启用后，AI 智能体工具「rerank_search」将可用。<br>
            选择「复用活跃供应商」时使用当前 LLM 供应商的 API 地址和密钥。
        </p>
        <div class="form-group">
            <label>启用状态</label>
            <input type="hidden" id="rerankerEnabled" value="${cfg.enabled ? '1' : '0'}">
            <div class="option-group" id="rerankerEnabledGroup">
                <button class="option-btn ${cfg.enabled ? 'active' : ''}" data-val="1">启用</button>
                <button class="option-btn ${!cfg.enabled ? 'active' : ''}" data-val="0">禁用</button>
            </div>
        </div>
        <div class="form-group">
            <label>API 配置方式</label>
            <input type="hidden" id="rerankerUseIndep" value="${cfg.use_independent ? '1' : '0'}">
            <div class="option-group" id="rerankerUseIndepGroup">
                <button class="option-btn ${!cfg.use_independent ? 'active' : ''}" data-val="0">复用 LLM 供应商</button>
                <button class="option-btn ${cfg.use_independent ? 'active' : ''}" data-val="1">独立配置</button>
            </div>
        </div>
        <div id="rerankerIndepFields" class="vec-cond" style="display:${cfg.use_independent ? '' : 'none'}">
            <div class="form-group">
                <label>API Base URL</label>
                <input type="text" id="rerankerApiBase" value="${escAttr(cfg.api_base)}" placeholder="https://api.jina.ai/v1">
            </div>
            <div class="form-group">
                <label>API Key</label>
                <input type="password" id="rerankerApiKey" value="${escAttr(cfg.api_key)}" placeholder="jina_xxx...">
            </div>
        </div>
        <div class="form-group">
            <label>模型名</label>
            <input type="text" id="rerankerModel" value="${escAttr(cfg.model)}" placeholder="jina-reranker-v2-base-multilingual">
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>端点路径</label>
                <input type="text" id="rerankerPath" value="${escAttr(cfg.rerank_path)}" placeholder="/rerank">
            </div>
            <div class="form-group">
                <label>Top N 返回数</label>
                <input type="number" id="rerankerTopN" value="${cfg.top_n}" min="1" max="20">
            </div>
        </div>
        <button class="btn btn-primary" onclick="saveRerankerConfig()" style="width:100%">${ic('save')} 保存</button>
    `;
    toggleDropdown(btn, html, true);
    setTimeout(() => {
        ['rerankerEnabledGroup', 'rerankerUseIndepGroup'].forEach(gid => {
            const group = document.getElementById(gid);
            if (!group) return;
            group.addEventListener('click', function(e) {
                const btn = e.target.closest('.option-btn');
                if (!btn) return;
                group.querySelectorAll('.option-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const hiddenId = gid.replace('Group', '');
                const hidden = document.getElementById(hiddenId);
                if (hidden) hidden.value = btn.dataset.val;
                if (gid === 'rerankerUseIndepGroup') {
                    const f = document.getElementById('rerankerIndepFields');
                    if (f) f.style.display = btn.dataset.val === '1' ? '' : 'none';
                }
            });
        });
    }, 50);
}

async function saveRerankerConfig() {
    try {
        const enabled = document.getElementById('rerankerEnabled').value === '1';
        const useIndep = document.getElementById('rerankerUseIndep').value === '1';
        const keyVal = document.getElementById('rerankerApiKey').value;
        const body = {
            enabled: enabled,
            use_independent: useIndep,
            api_base: document.getElementById('rerankerApiBase').value,
            model: document.getElementById('rerankerModel').value,
            rerank_path: document.getElementById('rerankerPath').value,
            top_n: parseInt(document.getElementById('rerankerTopN').value),
        };
        if (keyVal && !keyVal.endsWith('***')) body.api_key = keyVal;
        await API.put('/api/config/reranker', body);
        closeAllDropdowns();
        showToast('Reranker 配置已保存', 'success');
        const summary = document.getElementById('rerankerSummary');
        if (summary) {
            summary.innerHTML = `<span style="font-size:0.85rem;color:var(--text-secondary)">${enabled ? '已启用' : '未启用'} | ${body.model || '未配置模型'}</span>`;
        }
        window._rerankerCfg = { ...window._rerankerCfg, ...body };
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

// ==================== Regenerate with Suggestions ====================

async function regenerateChapter(chapterId) {
    const suggestId = '_regen_suggest_' + Date.now();
    // 使用 onClick 回调在 Modal 关闭前收集表单值
    let formData = null;
    await showModal({
        title: '重新生成章节',
        icon: 'warning',
        size: 'md',
        message: `
            <p style="margin-bottom:14px">当前章节内容将被覆盖，重新生成。请确认是否继续。</p>
            <div class="form-group" style="margin-bottom:0">
                <label style="font-weight:600">${ic('lightbulb', 'icon-sm')} 创作建议（可选）</label>
                <textarea id="${suggestId}" name="suggestions" placeholder="例如：让主角在悬崖边发现密道，引出下一章的地下城剧情" style="min-height:60px;width:100%"></textarea>
            </div>
        `,
        buttons: [
            { text: '取消', type: 'default', value: null },
            {
                text: '确认重新生成',
                type: 'danger',
                value: null,
                onClick: (close, form) => { formData = form; close('__start__'); },
            },
        ],
    });

    if (!formData) return;
    const suggestions = formData.suggestions || '';

    navigate('chapter-generate', { novelId: currentNovelId });
    setTimeout(async () => {
        const output = document.getElementById('streamOutput');
        if (output) output.innerHTML = '<p style="color:var(--text-secondary)">正在重新生成...</p>';
        const formData = new FormData();
        formData.append('provider_id', '');
        if (suggestions) formData.append('suggestions', suggestions);
        try {
            const { reader, response: r } = await streamFetch(`/api/chapters/${chapterId}/regenerate`, {
                method: 'POST', body: formData,
                headers: authToken ? { 'Authorization': 'Bearer ' + authToken } : {},
            });
            if (r.status === 401) { showLoginPage(); return; }
            const decoder = new TextDecoder();
            let buffer = '';
            let text = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const payload = line.slice(6);
                    if (payload === '[DONE]') break;
                    try {
                        const msg = JSON.parse(payload);
                        if (msg.type === 'chunk') {
                            text += msg.data;
                            if (output) output.innerHTML = escHtml(text) + '<span class="cursor"></span>';
                        }
                        else if (msg.type === 'thinking') {
                            // 思考内容显示在思考区（如果存在）
                            const thinkOut = document.getElementById('thinkingOutput');
                            if (thinkOut) {
                                if (!msg.incremental) {
                                    // 重分类：从正文移除
                                    text = text.slice(0, -msg.data.length);
                                    if (output) output.innerHTML = escHtml(text) + (text ? '' : '<span class="cursor"></span>');
                                }
                                thinkOut.innerHTML += `<div style="padding:4px 0;color:var(--text-secondary)">${escHtml(msg.data)}</div>`;
                                thinkOut.scrollTop = thinkOut.scrollHeight;
                                showThinkingIfNeeded();
                            }
                        }
                        else if (msg.type === 'content_replace') {
                            text = msg.data;
                            if (output) output.innerHTML = escHtml(text) + (text ? '' : '<span class="cursor"></span>');
                        }
                        else if (msg.type === 'tool_call') {
                            const thinkOut = document.getElementById('thinkingOutput');
                            if (thinkOut) {
                                const label = TOOL_LABELS[msg.name] || escHtml(msg.name);
                                const args = msg.args && Object.keys(msg.args).length ? `（${Object.values(msg.args).map(v => escHtml(String(v))).join('、')}）` : '';
                                thinkOut.innerHTML += `<div style="padding:3px 0;color:#4a9">${ic('wrench', 'icon-sm')} ${label}${args}</div>`;
                                thinkOut.scrollTop = thinkOut.scrollHeight;
                                showThinkingIfNeeded();
                            }
                        }
                        else if (msg.type === 'tool_result') {
                            const thinkOut = document.getElementById('thinkingOutput');
                            if (thinkOut) {
                                thinkOut.innerHTML += `<div style="padding:2px 0 6px 16px;color:var(--text-secondary);font-size:0.8rem;border-left:2px solid var(--border);margin-left:4px">${ic('corner-down-right', 'icon-sm')} ${escHtml(msg.preview || '')}</div>`;
                                thinkOut.scrollTop = thinkOut.scrollHeight;
                            }
                        }
                        else if (msg.type === 'pending_changes') {
                            window._pendingChangesData = msg.data;
                            setTimeout(() => showPendingChangesDialog(msg.data, msg.count), 800);
                        }
                        else if (msg.type === 'done') {
                            if (output) output.innerHTML = escHtml(text);
                            showToast('重新生成完成', 'success');
                            const delay = window._pendingChangesData && window._pendingChangesData.length ? 3000 : 1500;
                            setTimeout(() => navigate('novel-detail', { novelId: currentNovelId }), delay);
                        }
                        else if (msg.type === 'error') {
                            if (output) output.innerHTML += `<span style="color:red">错误: ${escHtml(msg.message)}</span>`;
                            showToast('生成失败: ' + msg.message, 'error');
                        }
                    } catch (e) { /* ignore */ }
                    }
                }
        } catch (e) {
            showToast('重新生成失败: ' + e.message, 'error');
        }
    }, 300);
}

// ==================== Restart ====================

async function confirmRestart() {
    if (!await confirmDialog('确定要重启应用吗？重启后所有配置变更将生效，期间服务会短暂中断。', { icon: 'warning', confirmText: '重启' })) return;
    try {
        showToast('正在重启...', 'info');
        await API.post('/api/system/restart', {});
        // 等待服务恢复，每 2 秒探测一次，最多 30 秒
        let attempts = 0;
        const maxAttempts = 15;
        const checkRecovery = async () => {
            attempts++;
            if (attempts > maxAttempts) {
                showToast('重启超时，请手动刷新页面', 'error');
                return;
            }
            try {
                await API.get('/api/auth/status');
                showToast('应用已重启完成', 'success');
                setTimeout(() => location.reload(), 500);
            } catch (e) {
                setTimeout(checkRecovery, 2000);
            }
        };
        setTimeout(checkRecovery, 2000);
    } catch (e) {
        // 重启请求本身可能因连接断开而失败，这是正常的
        setTimeout(async () => {
            try {
                await API.get('/api/auth/status');
                showToast('应用已重启完成', 'success');
                setTimeout(() => location.reload(), 500);
            } catch (e2) {
                // 继续等待
                const retry = async (n) => {
                    if (n <= 0) { showToast('重启超时，请手动刷新页面', 'error'); return; }
                    try {
                        await API.get('/api/auth/status');
                        showToast('应用已重启完成', 'success');
                        setTimeout(() => location.reload(), 500);
                    } catch (e3) {
                        setTimeout(() => retry(n - 1), 2000);
                    }
                };
                setTimeout(() => retry(13), 2000);
            }
        }, 2000);
    }
}

// ==================== Init ====================

async function renderBackupPage(main) {
    main.className = 'main-area';
    main.innerHTML = `
        <div class="page-header"><h2>${ic('database-backup', 'icon-md')} 备份与迁移</h2></div>
        
        <div class="card" style="max-width:680px">
            <div class="card-header"><h3>${ic('package', 'icon-md')} 导出备份</h3></div>
            <p style="color:var(--text-secondary);font-size:0.9rem;margin-bottom:16px">
                导出全部小说数据（小说、章节、人物画像、人物关系、百科条目、待确认变更）。可选包含配置和加密。
            </p>
            
            <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:12px">
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
                    <input type="checkbox" id="exportIncludeConfig" style="cursor:pointer">
                    <div>
                        <div style="font-weight:600">包含配置（API Key 等）</div>
                        <div style="color:var(--text-secondary);font-size:0.82rem">包含供应商、向量、重排序、图片生成、Tavily、服务器配置。API Key 会以明文存入备份文件（请妥善保管）。</div>
                    </div>
                </label>
            </div>
            
            <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:12px;margin-bottom:12px">
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
                    <input type="checkbox" id="exportEncrypt" style="cursor:pointer" onchange="toggleEncryptOptions()">
                    <div>
                        <div style="font-weight:600;color:#856404">${ic('lock', 'icon-sm')} 加密备份</div>
                        <div style="color:#856404;font-size:0.82rem">用密码加密整个备份文件。即使文件泄露，没有密码也无法读取内容。强烈建议勾选。</div>
                    </div>
                </label>
                <div id="encryptOptions" style="display:none;margin-top:10px;padding-top:10px;border-top:1px dashed #ffe082">
                    <div class="form-group" style="margin-bottom:8px">
                        <label style="font-size:0.85rem;font-weight:600">备份密码</label>
                        <input type="password" id="exportPassword" placeholder="设置备份密码（至少 6 位）" style="width:100%">
                    </div>
                    <div class="form-group" style="margin-bottom:0">
                        <label style="font-size:0.85rem;font-weight:600">确认密码</label>
                        <input type="password" id="exportPasswordConfirm" placeholder="再次输入密码" style="width:100%">
                    </div>
                </div>
            </div>
            
            <button class="btn btn-primary" onclick="exportBackup()">${ic('upload')} 导出备份文件</button>
        </div>
        
        <div class="card" style="max-width:680px;margin-top:16px">
            <div class="card-header"><h3>${ic('download', 'icon-md')} 导入备份</h3></div>
            <p style="color:var(--text-secondary);font-size:0.9rem;margin-bottom:16px">
                从 JSON 备份文件恢复数据。自动检测是否加密，加密备份需输入密码。
            </p>
            
            <div class="form-group">
                <input type="file" id="backupFileInput" accept=".json">
            </div>
            
            <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:12px">
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
                    <input type="checkbox" id="importIncludeConfig" style="cursor:pointer">
                    <div>
                        <div style="font-weight:600">导入配置</div>
                        <div style="color:var(--text-secondary);font-size:0.82rem">如果备份包含配置，勾选后会覆盖当前的供应商、向量、重排序等配置。不勾选则只导入小说数据。</div>
                    </div>
                </label>
            </div>
            
            <div class="form-group" id="importPasswordGroup" style="display:none">
                <label style="font-size:0.85rem;font-weight:600">${ic('lock', 'icon-sm')} 备份密码（加密备份需填写）</label>
                <input type="password" id="importPassword" placeholder="输入备份密码" style="width:100%">
            </div>
            
            <button class="btn btn-primary" onclick="importBackup()">${ic('download')} 导入备份文件</button>
        </div>
        
        <div class="card" style="max-width:680px;margin-top:16px">
            <div class="card-header"><h3>${ic('info', 'icon-md')} 备份格式说明</h3></div>
            <div style="font-size:0.85rem;color:var(--text-secondary);line-height:1.7">
                <p style="margin:0 0 8px"><strong>v2 格式（当前）</strong>：包含小说、章节、人物、关系、百科条目、待确认变更，可选包含配置。</p>
                <p style="margin:0 0 8px"><strong>v1 格式（旧版）</strong>：仅包含小说、章节、人物、关系。可正常导入，但建议导入后重新导出升级格式。</p>
                <p style="margin:0 0 8px"><strong>加密备份</strong>：整个备份文件用 AES-128 加密，需要密码才能解密。即使文件泄露也无法读取。</p>
                <p style="margin:0"><strong>注意</strong>：包含配置的备份文件中含有 API Key 明文（即使加密也只是文件级别加密），请妥善保管，不要分享给他人。</p>
            </div>
        </div>
    `;
    
    // 监听文件选择，自动检测是否加密
    const fileInput = document.getElementById('backupFileInput');
    if (fileInput) {
        fileInput.onchange = async () => {
            const pwdGroup = document.getElementById('importPasswordGroup');
            const pwdInput = document.getElementById('importPassword');
            if (!fileInput.files[0]) {
                pwdGroup.style.display = 'none';
                pwdInput.value = '';
                return;
            }
            try {
                const text = await fileInput.files[0].text();
                const data = JSON.parse(text);
                if (data && data._encrypted === true) {
                    pwdGroup.style.display = 'block';
                    pwdInput.focus();
                    showToast('检测到加密备份，请输入密码', 'info');
                } else {
                    pwdGroup.style.display = 'none';
                    pwdInput.value = '';
                }
            } catch (e) {
                pwdGroup.style.display = 'none';
            }
        };
    }
}

function toggleEncryptOptions() {
    const checked = document.getElementById('exportEncrypt').checked;
    document.getElementById('encryptOptions').style.display = checked ? 'block' : 'none';
}

async function exportBackup() {
    const includeConfig = document.getElementById('exportIncludeConfig').checked;
    const encrypt = document.getElementById('exportEncrypt').checked;
    const password = document.getElementById('exportPassword').value;
    const passwordConfirm = document.getElementById('exportPasswordConfirm').value;
    
    if (encrypt) {
        if (!password || password.length < 6) {
            showToast('备份密码至少 6 位', 'error');
            return;
        }
        if (password !== passwordConfirm) {
            showToast('两次输入的密码不一致', 'error');
            return;
        }
    }
    
    try {
        showToast('正在生成备份...', 'info');
        const data = await API.post('/api/backup/export', {
            password: encrypt ? password : '',
            include_config: includeConfig,
        });
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const suffix = encrypt ? '-encrypted' : (includeConfig ? '-full' : '');
        a.download = `novel-writer-backup-${new Date().toISOString().slice(0,10)}${suffix}.json`;
        a.click();
        URL.revokeObjectURL(url);
        let msg = '备份导出成功';
        if (encrypt) msg += '（已加密）';
        if (includeConfig) msg += '（含配置）';
        showToast(msg, 'success');
    } catch (e) {
        showToast('导出失败: ' + e.message, 'error');
    }
}

async function importBackup() {
    const input = document.getElementById('backupFileInput');
    if (!input || !input.files[0]) { showToast('请选择备份文件', 'error'); return; }
    
    const includeConfig = document.getElementById('importIncludeConfig').checked;
    const password = document.getElementById('importPassword').value;
    
    try {
        const text = await input.files[0].text();
        const data = JSON.parse(text);
        
        // 前端预检：加密备份必须有密码
        if (data && data._encrypted === true && !password) {
            showToast('此备份已加密，请输入密码', 'error');
            return;
        }
        
        const result = await API.post('/api/backup/import', {
            data,
            password,
            include_config: includeConfig,
        });
        const imp = result.imported || result;
        let msg = `导入成功：${imp.novels || 0} 部小说，${imp.chapters || 0} 个章节，${imp.characters || 0} 个人物，${imp.relationships || 0} 条关系`;
        if (imp.wiki_entries) msg += `，${imp.wiki_entries} 个百科条目`;
        if (imp.pending_changes) msg += `，${imp.pending_changes} 条待确认变更`;
        if (imp.config) msg += '，已导入配置';
        showToast(msg, 'success');
        
        // 如果是 v1 旧格式，提示重新导出
        if (imp.format_upgraded === false && imp.message) {
            setTimeout(() => showToast(imp.message, 'info'), 1500);
        }
        
        navigate('novels');
    } catch (e) {
        showToast('导入失败: ' + e.message, 'error');
    }
}

// ==================== 版本信息 ====================
let _appVersionInfo = null;

async function loadVersionInfo() {
    try {
        const data = await fetch('/api/version').then(r => r.json());
        _appVersionInfo = data;
        const el = document.getElementById('versionText');
        if (el) el.textContent = `v${data.version}`;
    } catch (e) {
        const el = document.getElementById('versionText');
        if (el) el.textContent = 'v?';
    }
}

async function showVersionInfo() {
    if (!_appVersionInfo) {
        await loadVersionInfo();
    }
    if (!_appVersionInfo) {
        await alertDialog('无法获取版本信息', { title: '错误', icon: 'danger' });
        return;
    }
    const info = _appVersionInfo;
    const notesHtml = (info.notes || []).map(n => `<li style="padding:3px 0">${escHtml(n)}</li>`).join('');
    await showModal({
        title: '应用版本信息',
        icon: 'info',
        size: 'md',
        message: `
            <div style="text-align:center;margin-bottom:16px">
                <div style="font-size:1.8rem;font-weight:700;color:var(--accent);margin-bottom:4px">v${escHtml(info.version)}</div>
                <div style="font-size:0.8rem;color:var(--text-secondary)">AI 小说写作助手</div>
            </div>
            <div style="background:var(--bg);border-radius:var(--radius-sm);padding:10px 12px;margin-bottom:12px;font-size:0.8rem;color:var(--text-secondary)">
                <div>Python: ${escHtml(info.python)}</div>
                <div>平台: ${escHtml(info.platform)}</div>
            </div>
            ${notesHtml ? `
                <div style="font-weight:600;margin-bottom:8px">${ic('sparkles', 'icon-sm')} 本次更新内容</div>
                <ul style="margin:0;padding-left:20px;font-size:0.85rem;line-height:1.6">
                    ${notesHtml}
                </ul>
            ` : ''}
        `,
        buttons: [
            { text: '关闭', type: 'primary', value: true },
        ],
    });
}

// ==================== Init ====================
document.addEventListener('DOMContentLoaded', async () => {
    loadVersionInfo();  // 后台加载版本信息，不阻塞
    const authed = await checkAuth();
    if (authed) {
        startActiveTaskPolling();
        renderPage();
    }
});
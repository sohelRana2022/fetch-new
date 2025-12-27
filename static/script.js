const API_BASE = '/api';

/* -------------------- NAVIGATION -------------------- */
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        item.classList.add('active');
        document.getElementById(item.dataset.target).classList.add('active');

        // Auto-load browse content
        if (item.dataset.target === 'search-view' &&
            document.getElementById('search-results').children.length === 0) {
            performSearch(true, 'Trending');
        }
    });
});

/* -------------------- CLIPBOARD PASTE -------------------- */
document.getElementById('paste-btn')?.addEventListener('click', async () => {
    try {
        const text = await navigator.clipboard.readText();
        document.getElementById('url-input').value = text;
    } catch (err) {
        showToast('Failed to read clipboard');
    }
});

/* -------------------- FETCH VIDEO INFO -------------------- */
document.getElementById('fetch-btn')?.addEventListener('click', async () => {
    const url = document.getElementById('url-input').value;
    if (!url) return showToast('Please enter a URL');
    setLoading(true);
    try {
        const res = await fetch(`${API_BASE}/info`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        renderPreview(data);
    } catch (err) {
        showToast(err.message);
    } finally {
        setLoading(false);
    }
});

function renderPreview(data) {
    const preview = document.getElementById('video-preview');
    document.getElementById('thumb-img').src = data.thumbnail;
    document.getElementById('video-title').textContent = data.title;

    const optionsContainer = document.querySelector('.select-options');
    optionsContainer.innerHTML = '';

    const defaultFmt = data.formats[1] || data.formats[0];
    document.getElementById('current-quality').textContent = defaultFmt.label;
    document.getElementById('custom-quality-select').dataset.value = defaultFmt.id;

    data.formats.forEach(fmt => {
        const div = document.createElement('div');
        div.className = `custom-option ${fmt.id === defaultFmt.id ? 'selected' : ''}`;
        div.dataset.value = fmt.id;
        div.textContent = fmt.label;
        optionsContainer.appendChild(div);
    });

    preview.dataset.url = data.original_url;
    preview.dataset.title = data.title;
    preview.dataset.thumb = data.thumbnail;
    preview.classList.remove('hidden');
}

/* -------------------- ADD TO DOWNLOAD QUEUE -------------------- */
document.getElementById('add-queue-btn')?.addEventListener('click', async () => {
    const preview = document.getElementById('video-preview');
    const url = preview.dataset.url;
    const quality = document.getElementById('custom-quality-select').dataset.value;

    const btn = document.getElementById('add-queue-btn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';
    btn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/download`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, quality })
        });
        const data = await res.json();
        showToastWithAction('Task Added Successfully!', 'tasks-view');

        if (data.task_id) {
            const tasksMeta = JSON.parse(localStorage.getItem('tasksMeta') || '{}');
            tasksMeta[data.task_id] = {
                title: preview.dataset.title,
                thumb: preview.dataset.thumb,
                url: preview.dataset.url
            };
            localStorage.setItem('tasksMeta', JSON.stringify(tasksMeta));
            fetchTasks();
        }
    } catch (err) {
        showToast('Failed to start download');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
});

/* -------------------- SEARCH LOGIC -------------------- */
let nextPageToken = '';
let isSearching = false;
let currentQuery = '';

async function performSearch(isNew = true, overrideQuery = null) {
    const query = overrideQuery || document.getElementById('search-input').value;
    if(!query) return;

    if (isNew) {
        currentQuery = query;
        nextPageToken = '';
        document.getElementById('search-results').innerHTML = Array(6).fill(0).map(() => `
            <div class="result-item skeleton-wrapper" style="pointer-events:none;">
                <div class="skeleton" style="width:120px; height:68px;"></div>
                <div class="result-info">
                    <div class="skeleton" style="height:16px; width:90%; margin-bottom:8px;"></div>
                    <div class="skeleton" style="height:12px; width:40%;"></div>
                </div>
            </div>
        `).join('');
    } else {
        if (!nextPageToken || isSearching) return;
        const loader = document.createElement('div');
        loader.id = 'loading-indicator';
        loader.innerHTML = '<div style="padding:20px;text-align:center;"><i class="fas fa-spinner fa-spin"></i> Loading more...</div>';
        document.getElementById('search-results').appendChild(loader);
    }

    isSearching = true;
    const resultsContainer = document.getElementById('search-results');

    try {
        const res = await fetch(`${API_BASE}/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: currentQuery, pageToken: nextPageToken })
        });
        const data = await res.json();

        const loader = document.getElementById('loading-indicator');
        if (loader) loader.remove();

        if (data.results && data.results.length > 0) {
            nextPageToken = data.nextPageToken || '';
            if (isNew) resultsContainer.innerHTML = '';
            data.results.forEach(video => {
                const div = document.createElement('div');
                div.className = 'result-item';
                div.innerHTML = `
                    <div style="position:relative;">
                        <img src="${video.thumbnail}" alt="thumb">
                        <span class="hd-badge">HD</span>
                    </div>
                    <div class="result-info">
                        <div class="result-title text-truncate-custom">${video.title}</div>
                        <div class="channel-info">Channel • <i class="fas fa-eye"></i> Views</div>
                    </div>
                `;
                div.addEventListener('click', () => {
                    document.getElementById('url-input').value = video.url;
                    document.querySelector('[data-target="home-view"]').click();
                    document.getElementById('fetch-btn').click();
                });
                resultsContainer.appendChild(div);
            });
        } else if (isNew) {
            resultsContainer.innerHTML = '<div class="no-results">No results found</div>';
        }
    } catch (err) {
        console.error(err);
        if (isNew) resultsContainer.innerHTML = '<div class="no-results text-danger">Search failed</div>';
    } finally {
        isSearching = false;
    }
}

document.getElementById('search-btn')?.addEventListener('click', () => performSearch(true));
document.getElementById('search-input')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') performSearch(true);
});

/* -------------------- DOWNLOAD HANDLER -------------------- */
const downloadedTasks = new Set();

window.handleDownload = async (taskId) => {
    const fileUrl = `${API_BASE}/get_file/${taskId}`;
    const defaultName = `video-${taskId.substring(0,8)}.mp4`;

    try {
        // Desktop SaveFilePicker fallback
        if (window.showSaveFilePicker) {
            const handle = await window.showSaveFilePicker({
                suggestedName: defaultName,
                types: [{ description: 'Video File', accept: { 'video/mp4': ['.mp4'] } }]
            });
            const writable = await handle.createWritable();
            const response = await fetch(fileUrl);
            await response.body.pipeTo(writable);
            showToast('Saved successfully');
        } else {
            const a = document.createElement('a');
            a.href = fileUrl;
            a.download = defaultName;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            showToast('Download started');
        }
        downloadedTasks.add(taskId);
    } catch (err) {
        if (err.name !== 'AbortError') showToast('Download failed');
    }
};

/* -------------------- TOASTS -------------------- */
let toastTimeout;
function showToast(msg) {
    const t = document.getElementById('toast');
    t.innerHTML = `<i class="fas fa-info-circle"></i> ${msg}`;
    t.classList.remove('hidden');
    void t.offsetWidth;
    t.classList.add('show');
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
        t.classList.remove('show');
        setTimeout(() => t.classList.add('hidden'), 400);
    }, 3000);
}

function showToastWithAction(msg, targetView) {
    const t = document.getElementById('toast');
    t.innerHTML = `
        <i class="fas fa-check-circle"></i> ${msg}
        <button class="toast-btn" onclick="document.querySelector('[data-target=\'${targetView}\']').click()">See</button>
    `;
    t.classList.remove('hidden');
    void t.offsetWidth;
    t.classList.add('show');
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
        t.classList.remove('show');
        setTimeout(() => t.classList.add('hidden'), 400);
    }, 5000);
}

/* -------------------- PROGRESS & TASKS FETCHING -------------------- */
let allTasks = {};
async function fetchTasks() {
    const tasksContainer = document.getElementById('tasks-container');
    if (!tasksContainer) return;

    const tasksMeta = JSON.parse(localStorage.getItem('tasksMeta') || '{}');
    const res = await fetch(`${API_BASE}/tasks`);
    const tasks = await res.json();
    allTasks = tasks;

    const taskIds = Object.keys(tasks).reverse();
    if (taskIds.length === 0) {
        tasksContainer.innerHTML = '<div class="no-tasks">No active tasks</div>';
        return;
    }

    taskIds.forEach(id => {
        const task = tasks[id];
        let card = document.getElementById(`task-card-${id}`);
        const meta = tasksMeta[id] || {};
        const title = meta.title || `Task ${id.substring(0,8)}`;
        const thumb = meta.thumb || '';

        const progress = task.status === 'finished' ? 100 : task.progress;

        const actionHtml = task.status === 'finished' 
            ? `<button disabled class="btn btn-success w-100"><i class="fas fa-check"></i> Downloaded</button>` 
            : `<button onclick="handleDownload('${task.id}')" class="btn btn-primary w-100"><i class="fas fa-download"></i> Download Now</button>`;

        const innerHTML = `
            <div class="task-card-inner">
                ${thumb ? `<img src="${thumb}" class="task-thumb">` : ''}
                <div class="task-info">
                    <div class="task-title">${title}</div>
                    <div class="task-meta">Progress: ${progress}%</div>
                    ${actionHtml}
                </div>
            </div>
        `;

        if (!card) {
            card = document.createElement('div');
            card.id = `task-card-${id}`;
            card.className = 'task-card';
            card.innerHTML = innerHTML;
            tasksContainer.appendChild(card);
        } else {
            card.innerHTML = innerHTML;
        }
    });
}

setInterval(fetchTasks, 1000);
fetchTasks();

/* -------------------- LOADING -------------------- */
function setLoading(state) {
    document.getElementById('loading-spinner')?.classList.toggle('hidden', !state);
}

/* -------------------- OFFLINE MONITORING -------------------- */
function updateOfflineBanners() {
    document.querySelectorAll('.offline-message').forEach(el => {
        el.classList.toggle('hidden', navigator.onLine);
    });
}

window.addEventListener('online', updateOfflineBanners);
window.addEventListener('offline', updateOfflineBanners);
updateOfflineBanners();

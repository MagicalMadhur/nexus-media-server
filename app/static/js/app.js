/**
 * Home Media Server — Global Application JavaScript
 * Handles: theme, sidebar, search, toasts, modals, TV navigation
 */

// ============================================================
// Theme Management
// ============================================================
function getTheme() {
    return document.documentElement.getAttribute('data-theme') || 'dark';
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('ms-theme', theme);
    const icon = document.getElementById('themeIcon');
    if (icon) {
        icon.className = theme === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
    }
    // Save to server
    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme })
    }).catch(() => {});
}

function toggleTheme() {
    setTheme(getTheme() === 'dark' ? 'light' : 'dark');
}

// Init theme from localStorage
(function() {
    const saved = localStorage.getItem('ms-theme');
    if (saved) {
        document.documentElement.setAttribute('data-theme', saved);
    }
    const icon = document.getElementById('themeIcon');
    if (icon) {
        icon.className = getTheme() === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
    }
})();


// ============================================================
// Sidebar (Mobile Toggle)
// ============================================================
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');

if (sidebarToggle) {
    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        sidebarOverlay.classList.toggle('active');
    });
}

if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', () => {
        sidebar.classList.remove('open');
        sidebarOverlay.classList.remove('active');
    });
}


// ============================================================
// Toast Notifications
// ============================================================
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success: 'fa-check-circle',
        error: 'fa-times-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle',
    };

    toast.innerHTML = `
        <i class="fas ${icons[type] || icons.info}" style="color: var(--${type === 'error' ? 'danger' : type})"></i>
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" 
                style="background: none; border: none; color: var(--text-muted); cursor: pointer; margin-left: auto;">
            <i class="fas fa-times"></i>
        </button>
    `;

    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100px)';
        toast.style.transition = 'all 300ms ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}


// ============================================================
// Modal
// ============================================================
function openModal(title, body, footer) {
    document.getElementById('modalTitle').textContent = title;
    document.getElementById('modalBody').innerHTML = body;
    document.getElementById('modalFooter').innerHTML = footer || '';
    document.getElementById('modalOverlay').classList.add('active');
}

function closeModal() {
    document.getElementById('modalOverlay').classList.remove('active');
}

// Close modal on overlay click
document.getElementById('modalOverlay')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeModal();
});

// Close modal on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
        document.getElementById('contextMenu')?.classList.remove('active');
    }
});


// ============================================================
// Global Search
// ============================================================
let searchTimeout;

function handleSearch(query) {
    clearTimeout(searchTimeout);
    const dropdown = document.getElementById('searchDropdown');

    if (!query || query.length < 2) {
        dropdown.classList.remove('active');
        return;
    }

    searchTimeout = setTimeout(async () => {
        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=10`);
            const data = await res.json();

            if (data.results.length === 0) {
                dropdown.innerHTML = '<div style="padding: 16px; text-align: center; color: var(--text-muted);">No results found</div>';
            } else {
                dropdown.innerHTML = data.results.map(item => {
                    const icon = item.file_type === 'video' ? 'fa-film' :
                                 item.file_type === 'audio' ? 'fa-music' :
                                 item.file_type === 'image' ? 'fa-image' : 'fa-file';
                    const color = item.file_type === 'video' ? '#8b5cf6' :
                                  item.file_type === 'audio' ? '#34d399' :
                                  item.file_type === 'image' ? '#f59e0b' : '#3b82f6';
                    const href = item.file_type === 'video' ? `/player/${item.id}` :
                                 item.file_type === 'image' ? '/photos' :
                                 item.file_type === 'audio' ? '/music' :
                                 `/explorer/${encodeURIComponent(item.parent_folder)}`;

                    return `<a href="${href}" class="search-result-item" tabindex="0">
                        <i class="fas ${icon}" style="color: ${color}; width: 20px; text-align: center;"></i>
                        <div style="flex: 1; min-width: 0;">
                            <div style="font-weight: 600; font-size: 0.85rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${item.filename}</div>
                            <div style="font-size: 0.75rem; color: var(--text-muted);">${item.file_type} · ${item.size_formatted || ''}</div>
                        </div>
                    </a>`;
                }).join('');
            }

            dropdown.classList.add('active');

            // Position near search bar
            const searchBar = document.querySelector('.search-bar');
            if (searchBar) {
                const rect = searchBar.getBoundingClientRect();
                dropdown.style.position = 'fixed';
                dropdown.style.top = (rect.bottom + 4) + 'px';
                dropdown.style.left = rect.left + 'px';
                dropdown.style.width = rect.width + 'px';
            }
        } catch (e) {
            dropdown.classList.remove('active');
        }
    }, 300);
}

// Close search dropdown on click outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-bar') && !e.target.closest('.search-results-dropdown')) {
        document.getElementById('searchDropdown')?.classList.remove('active');
    }
});


// ============================================================
// Clipboard
// ============================================================
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard!', 'success', 2000);
    }).catch(() => {
        // Fallback
        const input = document.createElement('input');
        input.value = text;
        document.body.appendChild(input);
        input.select();
        document.execCommand('copy');
        document.body.removeChild(input);
        showToast('Copied to clipboard!', 'success', 2000);
    });
}


// ============================================================
// Global Upload Handler
// ============================================================
function handleGlobalUpload(files) {
    if (files.length === 0) return;

    const formData = new FormData();
    for (const file of files) {
        formData.append('files', file);
    }

    showToast(`Uploading ${files.length} file(s)...`, 'info');

    fetch('/api/upload', {
        method: 'POST',
        body: formData
    })
    .then(r => r.json())
    .then(data => {
        const success = data.results.filter(r => r.success).length;
        showToast(`Uploaded ${success} of ${data.results.length} files`, success > 0 ? 'success' : 'error');
    })
    .catch(() => {
        showToast('Upload failed', 'error');
    });
}


// ============================================================
// TV Mode Detection
// ============================================================
(function() {
    // Detect TV by user agent or screen size
    const ua = navigator.userAgent.toLowerCase();
    const isTV = ua.includes('smart-tv') || ua.includes('smarttv') || 
                 ua.includes('tv browser') || ua.includes('jiobrowser') ||
                 ua.includes('jiosphere') || ua.includes('android tv') ||
                 ua.includes('tizen') || ua.includes('webos') ||
                 (window.screen.width >= 1920 && window.matchMedia('(hover: none)').matches);

    if (isTV) {
        document.body.classList.add('tv-mode');
        console.log('📺 TV mode activated');
    }
})();


// ============================================================
// D-pad / Remote Navigation  
// ============================================================
(function() {
    // Track focusable elements for D-pad navigation
    const FOCUSABLE = 'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])';

    function getFocusableElements() {
        return Array.from(document.querySelectorAll(FOCUSABLE)).filter(el => {
            const style = getComputedStyle(el);
            return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetParent !== null;
        });
    }

    function getAdjacentElement(current, direction) {
        const elements = getFocusableElements();
        if (!current || elements.length === 0) return elements[0];

        const currentRect = current.getBoundingClientRect();
        const cx = currentRect.left + currentRect.width / 2;
        const cy = currentRect.top + currentRect.height / 2;

        let best = null;
        let bestDist = Infinity;

        elements.forEach(el => {
            if (el === current) return;
            const rect = el.getBoundingClientRect();
            const ex = rect.left + rect.width / 2;
            const ey = rect.top + rect.height / 2;

            let valid = false;
            switch (direction) {
                case 'up': valid = ey < cy - 5; break;
                case 'down': valid = ey > cy + 5; break;
                case 'left': valid = ex < cx - 5; break;
                case 'right': valid = ex > cx + 5; break;
            }

            if (valid) {
                const dx = ex - cx;
                const dy = ey - cy;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < bestDist) {
                    bestDist = dist;
                    best = el;
                }
            }
        });

        return best;
    }

    // Only activate spatial navigation for TV mode or when no mouse is detected
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
        
        // Don't interfere with video player shortcuts
        if (document.querySelector('.player-page')) return;

        const directions = {
            'ArrowUp': 'up',
            'ArrowDown': 'down',
            'ArrowLeft': 'left',
            'ArrowRight': 'right',
        };

        if (directions[e.key]) {
            const dir = directions[e.key];
            const current = document.activeElement;
            const next = getAdjacentElement(current, dir);
            if (next) {
                e.preventDefault();
                next.focus();
                next.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }
    });
})();


// ============================================================
// Server URL copy  
// ============================================================
document.getElementById('serverUrl')?.addEventListener('click', function() {
    copyToClipboard(this.textContent.trim());
});


// ============================================================
// Service Worker (offline caching)  
// ============================================================
// Not implementing full PWA for now, but the app works on LAN without internet

// ============================================================
// Global File Operations (Rename, Delete)
// ============================================================
function showRenameModal(path, name) {
    openModal('Rename File', `
        <div style="margin-bottom: var(--space-md);">
            <label class="form-label">New Name</label>
            <input type="text" class="form-input" id="globalRenameInput" value="${name.replace(/"/g, '&quot;')}">
        </div>
    `, `
        <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        <button class="btn btn-primary" onclick="doRename('${path.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}')">Rename</button>
    `);
    setTimeout(() => {
        const input = document.getElementById('globalRenameInput');
        if (input) {
            input.focus();
            const dotIdx = name.lastIndexOf('.');
            if (dotIdx > 0) input.setSelectionRange(0, dotIdx);
        }
    }, 100);
}

async function doRename(path) {
    const newName = document.getElementById('globalRenameInput')?.value?.trim();
    if (!newName) return;

    try {
        const res = await fetch('/api/rename', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ path, new_name: newName })
        });
        const data = await res.json();
        if (data.success) {
            closeModal();
            showToast('Renamed successfully', 'success');
            location.reload();
        } else {
            showToast('Error renaming file: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (e) {
        showToast('Network error renaming file', 'error');
    }
}

async function deleteFile(path, name) {
    if (confirm(`Are you sure you want to delete "${name}"? This cannot be undone.`)) {
        try {
            const res = await fetch('/api/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ paths: [path] })
            });
            const data = await res.json();
            if (data.success) {
                showToast('Deleted successfully', 'success');
                location.reload();
            } else {
                showToast('Error deleting file', 'error');
            }
        } catch (e) {
            showToast('Network error deleting file', 'error');
        }
    }
}

// ============================================================
// Gallery Card Menus (3-dot dropdowns)
// ============================================================
document.addEventListener('click', (e) => {
    if (!e.target.closest('.menu-btn') && !e.target.closest('.btn-ghost') && !e.target.closest('div[style*="position: relative"]')) {
        document.querySelectorAll('.card-menu.show').forEach(m => m.classList.remove('show'));
    }
});

function toggleCardMenu(btn) {
    document.querySelectorAll('.card-menu.show').forEach(m => {
        if (m !== btn.nextElementSibling) m.classList.remove('show');
    });
    btn.nextElementSibling.classList.toggle('show');
}

console.log('🏠 Home Media Server loaded');

// ============================================================
// Spatial Navigation (TV Remote Support)
// ============================================================
(function() {
    let focusableElements = [];
    
    function updateFocusableElements() {
        const allElements = Array.from(document.querySelectorAll('a, button, input, [tabindex="0"]'));
        focusableElements = allElements.filter(el => {
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden' && !el.disabled;
        });
    }

    function getFocusedElement() {
        return document.activeElement && focusableElements.includes(document.activeElement) 
            ? document.activeElement 
            : null;
    }

    function calculateDistance(rect1, rect2, direction) {
        const cx1 = rect1.left + rect1.width / 2;
        const cy1 = rect1.top + rect1.height / 2;
        const cx2 = rect2.left + rect2.width / 2;
        const cy2 = rect2.top + rect2.height / 2;

        let dx = cx2 - cx1;
        let dy = cy2 - cy1;
        let distance = Infinity;

        if (direction === 'ArrowRight' && dx > 0) {
            distance = Math.pow(dx, 2) + Math.pow(dy, 2) * 8; 
        } else if (direction === 'ArrowLeft' && dx < 0) {
            distance = Math.pow(dx, 2) + Math.pow(dy, 2) * 8;
        } else if (direction === 'ArrowDown' && dy > 0) {
            distance = Math.pow(dy, 2) + Math.pow(dx, 2) * 8;
        } else if (direction === 'ArrowUp' && dy < 0) {
            distance = Math.pow(dy, 2) + Math.pow(dx, 2) * 8;
        }

        return distance;
    }

    function moveFocus(direction) {
        updateFocusableElements();
        if (focusableElements.length === 0) return;

        let current = getFocusedElement();
        if (!current) {
            focusableElements[0].focus();
            return;
        }

        const currentRect = current.getBoundingClientRect();
        let bestMatch = null;
        let minDistance = Infinity;

        focusableElements.forEach(el => {
            if (el === current) return;
            const rect = el.getBoundingClientRect();
            const dist = calculateDistance(currentRect, rect, direction);
            if (dist < minDistance) {
                minDistance = dist;
                bestMatch = el;
            }
        });

        if (bestMatch) {
            bestMatch.focus();
            bestMatch.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
        }
    }

    window.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
            return; 
        }

        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
            e.preventDefault(); 
            moveFocus(e.key);
        }
        
        if (e.key === 'Enter') {
            const current = getFocusedElement();
            if (current && current.tagName !== 'A' && current.tagName !== 'BUTTON' && current.tagName !== 'INPUT') {
                e.preventDefault();
                current.click();
            }
        }
    });

    window.addEventListener('load', () => {
        setTimeout(updateFocusableElements, 500);
    });
})();

// ============================================================
// Magic Cast Receiver
// ============================================================
(function() {
    function connectMagicCast() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = protocol + '//' + window.location.host + '/ws/cast';
        
        let ws = new WebSocket(wsUrl);
        
        ws.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'force_cast' && data.url) {
                    // Show a toast then redirect immediately
                    showToast('Magic Cast received! Opening...', 'success');
                    setTimeout(() => {
                        window.location.href = data.url;
                    }, 500);
                }
            } catch (e) {
                console.error('Error parsing Magic Cast message:', e);
            }
        };

        ws.onclose = function() {
            setTimeout(connectMagicCast, 3000); // Reconnect on close
        };
    }
    
    // Init Magic Cast Receiver
    connectMagicCast();
})();

// ============================================================
// PWA Service Worker Registration
// ============================================================
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').then(registration => {
            console.log('ServiceWorker registration successful with scope: ', registration.scope);
        }).catch(err => {
            console.log('ServiceWorker registration failed: ', err);
        });
    });
}

// ============================================================
// TV Mode Detection
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    const ua = navigator.userAgent.toLowerCase();
    if (ua.includes('tv') || ua.includes('smart-tv') || ua.includes('smarttv') || ua.includes('jio') || ua.includes('box') || ua.includes('stb')) {
        document.body.classList.add('tv-mode');
        console.log('TV Mode Enabled!');
    }
});

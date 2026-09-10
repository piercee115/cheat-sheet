// Cheatsheet: Steam Anti-Cheat Compatibility App

let currentScanData = null;
let activeStatusFilter = 'ALL';
let activeSearchQuery = '';
let activeAntiCheatFilter = '';
let activeProtonDBFilter = '';
let activeFeatureFilter = '';
let activeSortOrder = 'status_priority';
let activeViewMode = 'table'; // 'table' or 'cards'
let searchDebounceTimeout = null;
let lastScannedQuery = '';

// Status priority weighting for sorting
const STATUS_PRIORITY = {
    'Broken': 1,
    'Denied': 2,
    'Planned': 3,
    'Running': 4,
    'Supported': 5,
    'Unlisted': 6
};

const STATUS_SUPPORTED_PRIORITY = {
    'Supported': 1,
    'Running': 2,
    'Planned': 3,
    'Broken': 4,
    'Denied': 5,
    'Unlisted': 6
};

// ProtonDB tier priority weighting for sorting
const PDB_TIER_PRIORITY = {
    'platinum': 1,
    'gold': 2,
    'silver': 3,
    'bronze': 4,
    'borked': 5,
    'pending': 6
};

const PDB_BORKED_PRIORITY = {
    'borked': 1,
    'bronze': 2,
    'silver': 3,
    'gold': 4,
    'platinum': 5,
    'pending': 6
};

// Column sort state for interactive table headers
let currentSortColumn = 'status';
let currentSortDirection = 'asc'; // 'asc' or 'desc'

// Body scroll lock helpers for active modals
function disableBodyScroll() {
    document.body.classList.add('overflow-hidden');
    document.documentElement.classList.add('overflow-hidden');
}

function enableBodyScroll() {
    const anyOpen = ['game-detail-modal', 'recent-updates-modal', 'privacy-help-modal']
        .some(id => {
            const el = document.getElementById(id);
            return el && !el.classList.contains('hidden');
        });
    if (!anyOpen) {
        document.body.classList.remove('overflow-hidden');
        document.documentElement.classList.remove('overflow-hidden');
    }
}

function handleModalBackdropClick(event, modalId) {
    if (event.target.id === modalId) {
        if (modalId === 'game-detail-modal') closeGameDetailModal();
        else if (modalId === 'recent-updates-modal') closeRecentUpdatesModal();
        else if (modalId === 'privacy-help-modal') closePrivacyHelpModal();
    }
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const queryParam = urlParams.get('query');
    if (queryParam) {
        document.getElementById('steam-input').value = queryParam;
        window.history.replaceState({}, document.title, window.location.pathname);
        setTimeout(() => handleScan(), 50);
    } else {
        const savedQuery = localStorage.getItem('cheatsheet_last_query');
        if (savedQuery) {
            document.getElementById('steam-input').value = savedQuery;
        }
    }

    const savedView = localStorage.getItem('cheatsheet_view_mode');
    if (savedView === 'cards' || savedView === 'table') {
        setViewMode(savedView);
    }

    // Modal dismiss shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeGameDetailModal();
            closeRecentUpdatesModal();
            closePrivacyHelpModal();
        }
    });

    // Ensure all modal backdrops are click-offable
    ['game-detail-modal', 'recent-updates-modal', 'privacy-help-modal'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('click', (e) => {
                if (e.target === el) {
                    el.classList.add('hidden');
                    enableBodyScroll();
                }
            });
        }
    });

    updateSortIndicators();
});

// View mode switcher: 'table' vs 'cards'
function setViewMode(mode) {
    activeViewMode = mode;
    localStorage.setItem('cheatsheet_view_mode', mode);

    const btnTable = document.getElementById('view-mode-table');
    const btnCards = document.getElementById('view-mode-cards');
    const tableContainer = document.getElementById('table-view-container');
    const cardsContainer = document.getElementById('cards-view-container');

    if (mode === 'cards') {
        btnCards.className = 'px-2.5 py-1 rounded font-medium text-[#c9d1d9] bg-[#21262d] transition flex items-center gap-1';
        btnTable.className = 'px-2.5 py-1 rounded font-medium text-[#8b949e] hover:text-[#c9d1d9] transition flex items-center gap-1';
        cardsContainer.classList.remove('hidden');
        tableContainer.classList.add('hidden');
    } else {
        btnTable.className = 'px-2.5 py-1 rounded font-medium text-[#c9d1d9] bg-[#21262d] transition flex items-center gap-1';
        btnCards.className = 'px-2.5 py-1 rounded font-medium text-[#8b949e] hover:text-[#c9d1d9] transition flex items-center gap-1';
        tableContainer.classList.remove('hidden');
        cardsContainer.classList.add('hidden');
    }

    filterAndRenderGames();
}

// Primary scan handler
async function handleScan(event) {
    if (event) event.preventDefault();

    const input = document.getElementById('steam-input');
    const query = input.value.trim();
    if (!query) return;

    lastScannedQuery = query;
    localStorage.setItem('cheatsheet_last_query', query);

    setLoading(true);
    dismissAlert();
    document.getElementById('privacy-callout').classList.add('hidden');

    try {
        const honeypot = document.getElementById('bot-honeypot')?.value || '';
        const token = document.getElementById('anti-bot-token')?.value || '';
        let scanUrl = `/api/scan?query=${encodeURIComponent(query)}`;
        if (token) scanUrl += `&abt=${encodeURIComponent(token)}`;
        if (honeypot) scanUrl += `&b_check=${encodeURIComponent(honeypot)}`;

        const resp = await fetch(scanUrl);
        const data = await resp.json();

        if (!resp.ok) {
            handleScanError(resp.status, data);
            return;
        }

        renderScanResults(data);
    } catch (err) {
        showAlert('Connection Error', 'Failed to reach server. Please check your network connection.', 'error');
    } finally {
        setLoading(false);
    }
}

// Error handling
function handleScanError(status, data) {
    const detail = data.detail || {};
    const message = detail.message || (typeof detail === 'string' ? detail : 'An unexpected error occurred.');

    if (status === 503) {
        showAlert(
            'Service Notice',
            message,
            'warning',
            [
                { text: 'Try Competitive Sample', action: "loadDemo('competitive')" },
                { text: 'Try Steam Deck Sample', action: "loadDemo('steamdeck')" }
            ]
        );
        return;
    }

    if (status === 404) {
        showAlert('Profile Not Found', message, 'warning');
        return;
    }

    if (status === 429) {
        showAlert('Rate Limit Exceeded', message, 'warning');
        return;
    }

    showAlert(`Error (${status})`, message, 'error');
}

// Load sample library
async function loadDemo(profileKey) {
    setLoading(true);
    dismissAlert();
    document.getElementById('privacy-callout').classList.add('hidden');

    try {
        const resp = await fetch(`/api/demo?profile=${encodeURIComponent(profileKey)}`);
        const data = await resp.json();
        renderScanResults(data);
        document.getElementById('steam-input').value = `demo:${profileKey}`;
    } catch (err) {
        showAlert('Error', 'Could not load demo profile.', 'error');
    } finally {
        setLoading(false);
    }
}

function retryLastScan() {
    if (lastScannedQuery) {
        document.getElementById('steam-input').value = lastScannedQuery;
        handleScan();
    }
}

// Render complete scan result dashboard
function renderScanResults(data) {
    currentScanData = data;

    // Check for private profile
    if (data.is_private) {
        document.getElementById('privacy-callout').classList.remove('hidden');
        document.getElementById('results-section').classList.add('hidden');
        return;
    }

    document.getElementById('privacy-callout').classList.add('hidden');
    document.getElementById('results-section').classList.remove('hidden');

    // Header info
    document.getElementById('user-avatar').src = data.avatar || 'https://avatars.steamstatic.com/fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb_full.jpg';
    document.getElementById('user-name').textContent = data.personaname || 'Steam User';
    document.getElementById('user-steamid').textContent = `ID: ${data.steamid}`;
    document.getElementById('user-profile-link').href = data.profileurl || `https://steamcommunity.com/profiles/${data.steamid}`;

    // Demo indicator
    const demoBadge = document.getElementById('demo-indicator');
    if (data.is_demo) {
        demoBadge.classList.remove('hidden');
    } else {
        demoBadge.classList.add('hidden');
    }

    // Playability percentage and progress bars
    const total = data.total_games || 0;
    const counts = data.status_counts || {};

    document.getElementById('playability-rate').textContent = `${data.playable_percentage}%`;

    const calcPct = (count) => (total > 0 ? (count / total) * 100 : 0);
    document.getElementById('bar-supported').style.width = `${calcPct(counts['Supported'] || 0)}%`;
    document.getElementById('bar-running').style.width = `${calcPct(counts['Running'] || 0)}%`;
    document.getElementById('bar-planned').style.width = `${calcPct(counts['Planned'] || 0)}%`;
    document.getElementById('bar-broken').style.width = `${calcPct(counts['Broken'] || 0)}%`;
    document.getElementById('bar-denied').style.width = `${calcPct(counts['Denied'] || 0)}%`;
    document.getElementById('bar-unlisted').style.width = `${calcPct(counts['Unlisted'] || 0)}%`;

    // Stat cards
    document.getElementById('stat-total').textContent = total;
    document.getElementById('stat-supported').textContent = counts['Supported'] || 0;
    document.getElementById('stat-running').textContent = counts['Running'] || 0;
    document.getElementById('stat-broken').textContent = counts['Broken'] || 0;
    document.getElementById('stat-denied').textContent = counts['Denied'] || 0;
    document.getElementById('stat-unlisted').textContent = counts['Unlisted'] || 0;

    // Filter pill counters
    document.getElementById('pill-all-count').textContent = total;
    document.getElementById('pill-supported-count').textContent = counts['Supported'] || 0;
    document.getElementById('pill-running-count').textContent = counts['Running'] || 0;
    document.getElementById('pill-broken-count').textContent = counts['Broken'] || 0;
    document.getElementById('pill-denied-count').textContent = counts['Denied'] || 0;
    document.getElementById('pill-unlisted-count').textContent = counts['Unlisted'] || 0;

    // ProtonDB tier counts
    const pdbCounts = data.protondb_counts || {};
    const getPdbCount = (tier) => pdbCounts[tier] || 0;
    const statPdbPlat = document.getElementById('stat-pdb-platinum');
    const statPdbGold = document.getElementById('stat-pdb-gold');
    const statPdbSilv = document.getElementById('stat-pdb-silver');
    const statPdbBron = document.getElementById('stat-pdb-bronze');
    const statPdbBork = document.getElementById('stat-pdb-borked');
    const statPdbPend = document.getElementById('stat-pdb-pending');
    if (statPdbPlat) statPdbPlat.textContent = getPdbCount('platinum');
    if (statPdbGold) statPdbGold.textContent = getPdbCount('gold');
    if (statPdbSilv) statPdbSilv.textContent = getPdbCount('silver');
    if (statPdbBron) statPdbBron.textContent = getPdbCount('bronze');
    if (statPdbBork) statPdbBork.textContent = getPdbCount('borked');
    if (statPdbPend) statPdbPend.textContent = getPdbCount('pending');

    // Populate Anti-Cheat Tech Dropdown
    populateAntiCheatDropdown(data.games);

    // Render game cards and table
    filterAndRenderGames();
}

// Populate anti-cheat selector
function populateAntiCheatDropdown(games) {
    const select = document.getElementById('anticheat-filter');
    const existingVal = select.value;
    select.innerHTML = '<option value="">All Anti-Cheat Systems</option>';

    const engines = new Set();
    games.forEach(g => {
        if (g.anticheats && Array.isArray(g.anticheats)) {
            g.anticheats.forEach(ac => engines.add(ac));
        }
    });

    Array.from(engines).sort().forEach(engine => {
        const opt = document.createElement('option');
        opt.value = engine;
        opt.textContent = engine;
        select.appendChild(opt);
    });

    if (engines.has(existingVal)) {
        select.value = existingVal;
    } else {
        activeAntiCheatFilter = '';
    }
}

// Filter and render game items
function filterAndRenderGames() {
    if (!currentScanData || !currentScanData.games) return;

    let list = [...currentScanData.games];

    // Status filter
    if (activeStatusFilter !== 'ALL') {
        list = list.filter(g => g.status === activeStatusFilter);
    }

    // Anti-cheat filter
    if (activeAntiCheatFilter) {
        list = list.filter(g => g.anticheats && g.anticheats.includes(activeAntiCheatFilter));
    }

    // ProtonDB tier filter
    if (activeProtonDBFilter) {
        list = list.filter(g => (g.protondb_tier || 'pending').toLowerCase() === activeProtonDBFilter.toLowerCase());
    }

    // Special features filter
    if (activeFeatureFilter === 'has_notes') {
        list = list.filter(g => g.notes && g.notes.length > 0);
    } else if (activeFeatureFilter === 'has_updates') {
        list = list.filter(g => g.updates && g.updates.length > 0);
    } else if (activeFeatureFilter === 'native_only') {
        list = list.filter(g => g.native === true);
    }

    // Text search
    if (activeSearchQuery) {
        const queryLower = activeSearchQuery.toLowerCase();
        list = list.filter(g => {
            const nameMatch = g.name.toLowerCase().includes(queryLower);
            const acMatch = g.anticheats && g.anticheats.some(ac => ac.toLowerCase().includes(queryLower));
            const idMatch = String(g.appid).includes(queryLower);
            return nameMatch || acMatch || idMatch;
        });
    }

    // Sorting by selected column and direction
    list.sort((a, b) => {
        if (currentSortColumn === 'status') {
            const pA = STATUS_PRIORITY[a.status] || 99;
            const pB = STATUS_PRIORITY[b.status] || 99;
            if (pA !== pB) {
                return currentSortDirection === 'asc' ? pA - pB : pB - pA;
            }
            return b.playtime_forever - a.playtime_forever;
        }
        if (currentSortColumn === 'protondb') {
            const pA = PDB_TIER_PRIORITY[(a.protondb_tier || 'pending').toLowerCase()] || 99;
            const pB = PDB_TIER_PRIORITY[(b.protondb_tier || 'pending').toLowerCase()] || 99;
            if (pA !== pB) {
                return currentSortDirection === 'asc' ? pA - pB : pB - pA;
            }
            return b.playtime_forever - a.playtime_forever;
        }
        if (currentSortColumn === 'name') {
            return currentSortDirection === 'asc'
                ? a.name.localeCompare(b.name)
                : b.name.localeCompare(a.name);
        }
        if (currentSortColumn === 'anticheats') {
            const acA = (a.anticheats && a.anticheats.length > 0) ? a.anticheats[0].toLowerCase() : 'zzz';
            const acB = (b.anticheats && b.anticheats.length > 0) ? b.anticheats[0].toLowerCase() : 'zzz';
            const comp = acA.localeCompare(acB);
            return currentSortDirection === 'asc' ? comp : -comp;
        }
        if (currentSortColumn === 'native') {
            const natA = a.native ? 1 : 0;
            const natB = b.native ? 1 : 0;
            if (natA !== natB) {
                return currentSortDirection === 'asc' ? natB - natA : natA - natB;
            }
            return b.playtime_forever - a.playtime_forever;
        }
        if (currentSortColumn === 'notes') {
            const countA = (a.notes ? a.notes.length : 0) + (a.updates ? a.updates.length : 0);
            const countB = (b.notes ? b.notes.length : 0) + (b.updates ? b.updates.length : 0);
            if (countA !== countB) {
                return currentSortDirection === 'desc' ? countB - countA : countA - countB;
            }
            return b.playtime_forever - a.playtime_forever;
        }
        if (currentSortColumn === 'playtime') {
            return currentSortDirection === 'desc'
                ? b.playtime_forever - a.playtime_forever
                : a.playtime_forever - b.playtime_forever;
        }
        return 0;
    });

    // Count text
    document.getElementById('filtered-count-text').textContent = `Showing ${list.length} of ${currentScanData.total_games} games`;

    const tableBody = document.getElementById('games-table-body');
    const cardsGrid = document.getElementById('cards-view-container');
    const emptyState = document.getElementById('empty-state');

    if (list.length === 0) {
        tableBody.innerHTML = '';
        cardsGrid.innerHTML = '';
        emptyState.classList.remove('hidden');
        return;
    }

    emptyState.classList.add('hidden');

    if (activeViewMode === 'table') {
        tableBody.innerHTML = list.map(createTableRowHTML).join('');
    } else {
        cardsGrid.innerHTML = list.map(createGameCardHTML).join('');
    }
}

// Generate compact table row HTML (SteamDB / ProtonDB style)
function createTableRowHTML(game) {
    const statusClasses = `status-badge-${game.status}`;
    const playtimeText = game.playtime_hours > 0 ? `${game.playtime_hours} hrs` : '—';

    const pdbTier = (game.protondb_tier || 'pending').toLowerCase();
    const pdbBadgeClass = `protondb-badge-${pdbTier}`;
    const pdbConfidence = game.protondb_confidence ? ` (${game.protondb_confidence} confidence)` : '';

    const anticheatsText = (game.anticheats && game.anticheats.length > 0)
        ? game.anticheats.map(ac => `<span class="px-1.5 py-0.5 rounded bg-[#21262d] text-[#c9d1d9] text-[11px] border border-[#30363d]">${escapeHTML(ac)}</span>`).join(' ')
        : `<span class="text-[#6e7681] text-[11px]">Clean / Unlisted</span>`;

    const nativeCell = game.native
        ? `<span class="text-[#2ea043] font-mono text-[11px] font-semibold">Yes</span>`
        : `<span class="text-[#6e7681] font-mono text-[11px]">Proton</span>`;

    const notesCount = game.notes ? game.notes.length : 0;
    const updatesCount = game.updates ? game.updates.length : 0;

    let notesBadges = [];
    if (notesCount > 0) {
        notesBadges.push(`<button onclick="openGameDetailModal(${game.appid})" class="px-1.5 py-0.5 rounded bg-[#1f6feb]/15 text-[#58a6ff] hover:bg-[#1f6feb]/30 border border-[#1f6feb]/30 text-[10px] font-mono transition" title="${notesCount} community workaround note(s)">${notesCount} note${notesCount > 1 ? 's' : ''}</button>`);
    }
    if (updatesCount > 0) {
        notesBadges.push(`<button onclick="openGameDetailModal(${game.appid})" class="px-1.5 py-0.5 rounded bg-[#a371f7]/15 text-[#bc8cff] hover:bg-[#a371f7]/30 border border-[#a371f7]/30 text-[10px] font-mono transition" title="${updatesCount} anti-cheat timeline update(s)">${updatesCount} update${updatesCount > 1 ? 's' : ''}</button>`);
    }
    const notesUpdatesHTML = notesBadges.length > 0
        ? `<div class="flex items-center gap-1.5">${notesBadges.join('')}</div>`
        : `<span class="text-[#6e7681] text-[11px]">—</span>`;

    return `
    <tr class="game-row hover:bg-[#21262d]/70 transition">
        <td class="py-2.5 px-3 whitespace-nowrap">
            <span class="px-2 py-0.5 rounded text-[11px] font-semibold font-mono ${statusClasses}">
                ${game.status}
            </span>
        </td>
        <td class="py-2.5 px-3 whitespace-nowrap">
            <a href="https://www.protondb.com/app/${game.appid}" target="_blank" rel="noopener noreferrer" class="px-2 py-0.5 rounded text-[11px] font-semibold font-mono inline-block capitalize ${pdbBadgeClass}" title="ProtonDB Tier: ${pdbTier.toUpperCase()}${pdbConfidence}">
                ${pdbTier}
            </a>
        </td>
        <td class="py-2.5 px-3">
            <div class="flex items-center gap-2.5">
                <img src="${game.header_url}" alt="" onclick="openGameDetailModal(${game.appid})" class="w-12 h-6 object-cover rounded bg-[#0d1117] flex-shrink-0 cursor-pointer hover:opacity-80 transition" onerror="this.style.display='none'">
                <div>
                    <a href="javascript:void(0)" onclick="openGameDetailModal(${game.appid})" class="font-medium text-[#f0f6fc] hover:text-[#58a6ff] transition cursor-pointer">
                        ${escapeHTML(game.name)}
                    </a>
                    <span class="text-[10px] text-[#6e7681] font-mono block">AppID: ${game.appid}</span>
                </div>
            </div>
        </td>
        <td class="py-2.5 px-3">
            <div class="flex flex-wrap gap-1">
                ${anticheatsText}
            </div>
        </td>
        <td class="py-2.5 px-3 font-mono">
            ${nativeCell}
        </td>
        <td class="py-2.5 px-3">
            ${notesUpdatesHTML}
        </td>
        <td class="py-2.5 px-3 font-mono text-[#8b949e] whitespace-nowrap">
            ${playtimeText}
        </td>
        <td class="py-2.5 px-3 text-right whitespace-nowrap">
            <div class="inline-flex items-center gap-2 text-[11px]">
                <button onclick="openGameDetailModal(${game.appid})" class="px-2 py-0.5 rounded bg-[#21262d] hover:bg-[#30363d] text-[#c9d1d9] border border-[#30363d] transition font-medium">
                    Details
                </button>
                <a href="https://store.steampowered.com/app/${game.appid}" target="_blank" rel="noopener noreferrer" class="text-[#8b949e] hover:text-[#f0f6fc] transition">
                    Store
                </a>
            </div>
        </td>
    </tr>
    `;
}

// Generate clean card HTML
function createGameCardHTML(game) {
    const statusClasses = `status-badge-${game.status}`;
    const playtimeText = game.playtime_hours > 0 ? `${game.playtime_hours} hrs` : 'Unplayed';

    const pdbTier = (game.protondb_tier || 'pending').toLowerCase();
    const pdbBadgeClass = `protondb-badge-${pdbTier}`;
    const pdbConfidence = game.protondb_confidence ? ` (${game.protondb_confidence})` : '';
    const pdbBadge = `<a href="https://www.protondb.com/app/${game.appid}" target="_blank" rel="noopener noreferrer" class="px-1.5 py-0.5 rounded text-[11px] font-mono capitalize ${pdbBadgeClass}" title="ProtonDB Tier: ${pdbTier.toUpperCase()}${pdbConfidence}">Proton: ${pdbTier}</a>`;

    const anticheatBadges = (game.anticheats && game.anticheats.length > 0)
        ? game.anticheats.map(ac => `<span class="px-1.5 py-0.5 rounded text-[11px] bg-[#21262d] text-[#c9d1d9] border border-[#30363d]">${escapeHTML(ac)}</span>`).join('')
        : `<span class="px-1.5 py-0.5 rounded text-[11px] bg-[#0d1117] text-[#6e7681] border border-[#21262d]">None tracked</span>`;

    const nativeBadge = game.native
        ? `<span class="px-1.5 py-0.5 rounded text-[11px] bg-[#2ea043]/15 text-[#3fb950] border border-[#2ea043]/30 font-mono">Native Linux</span>`
        : `<span class="px-1.5 py-0.5 rounded text-[11px] bg-[#21262d] text-[#8b949e] border border-[#30363d] font-mono">Proton/Wine</span>`;

    const notesCount = game.notes ? game.notes.length : 0;
    const updatesCount = game.updates ? game.updates.length : 0;
    const notesBadge = notesCount > 0
        ? `<button onclick="openGameDetailModal(${game.appid})" class="px-1.5 py-0.5 rounded text-[11px] bg-[#1f6feb]/15 text-[#58a6ff] border border-[#1f6feb]/30 font-mono hover:bg-[#1f6feb]/30 transition">${notesCount} note${notesCount > 1 ? 's' : ''}</button>`
        : '';
    const updatesBadge = updatesCount > 0
        ? `<button onclick="openGameDetailModal(${game.appid})" class="px-1.5 py-0.5 rounded text-[11px] bg-[#a371f7]/15 text-[#bc8cff] border border-[#a371f7]/30 font-mono hover:bg-[#a371f7]/30 transition">${updatesCount} update${updatesCount > 1 ? 's' : ''}</button>`
        : '';

    // Notes preview (first note)
    let notesHTML = '';
    if (game.notes && game.notes.length > 0) {
        const noteItems = game.notes.slice(0, 1).map(n => {
            const text = Array.isArray(n) ? n[0] : String(n);
            const link = Array.isArray(n) && n[1] ? n[1] : null;
            if (link && isSafeUrl(link)) {
                return `<li class="truncate"><a href="${escapeHTML(link)}" target="_blank" rel="noopener noreferrer" class="hover:underline text-[#58a6ff]">${escapeHTML(text)}</a></li>`;
            }
            return `<li class="truncate">• ${escapeHTML(text)}</li>`;
        }).join('');
        notesHTML = `<ul class="text-[11px] text-[#8b949e] space-y-0.5 mt-2 bg-[#0d1117] p-2 rounded border border-[#21262d]">${noteItems}</ul>`;
    }

    return `
    <div class="game-card bg-[#161b22] rounded-lg border border-[#30363d] overflow-hidden flex flex-col justify-between shadow-sm">
        <div class="relative h-24 w-full bg-[#0d1117] overflow-hidden border-b border-[#21262d] cursor-pointer" onclick="openGameDetailModal(${game.appid})">
            <img
                src="${game.header_url}"
                alt="${escapeHTML(game.name)}"
                class="w-full h-full object-cover hover:scale-105 transition duration-300"
                loading="lazy"
                onerror="this.style.display='none'"
            >
            <div class="absolute top-2 right-2">
                <span class="px-2 py-0.5 rounded text-xs font-semibold font-mono shadow ${statusClasses}">
                    ${game.status}
                </span>
            </div>
            <div class="absolute bottom-1.5 left-2 text-[10px] px-1.5 py-0.5 rounded bg-[#0d1117]/90 text-[#8b949e] font-mono border border-[#30363d]">
                AppID: ${game.appid}
            </div>
        </div>

        <div class="p-3 flex-grow flex flex-col justify-between space-y-2.5">
            <div>
                <h4 class="text-xs font-bold text-[#f0f6fc] line-clamp-1 hover:text-[#58a6ff] transition cursor-pointer" onclick="openGameDetailModal(${game.appid})">
                    ${escapeHTML(game.name)}
                </h4>
                <div class="flex flex-wrap items-center gap-1 mt-1.5">
                    ${pdbBadge}
                    ${anticheatBadges}
                    ${nativeBadge}
                    ${notesBadge}
                    ${updatesBadge}
                </div>
                ${notesHTML}
            </div>

            <div class="pt-2 border-t border-[#21262d] flex items-center justify-between text-[11px] text-[#8b949e]">
                <span class="font-mono text-[#8b949e]">${playtimeText}</span>
                <div class="flex items-center gap-2">
                    <button onclick="openGameDetailModal(${game.appid})" class="px-2 py-0.5 rounded bg-[#21262d] hover:bg-[#30363d] text-[#c9d1d9] border border-[#30363d] transition font-medium">
                        Details
                    </button>
                    <span>&bull;</span>
                    <a href="https://store.steampowered.com/app/${game.appid}" target="_blank" rel="noopener noreferrer" class="hover:text-[#f0f6fc] transition">
                        Store
                    </a>
                </div>
            </div>
        </div>
    </div>
    `;
}

// Debounced input search
function onSearchInput(event) {
    clearTimeout(searchDebounceTimeout);
    searchDebounceTimeout = setTimeout(() => {
        activeSearchQuery = event.target.value.trim();
        filterAndRenderGames();
    }, 150);
}

// Status filter pill click
function selectStatusFilter(status) {
    activeStatusFilter = status;

    document.querySelectorAll('.status-pill').forEach(pill => {
        pill.classList.remove('active-pill');
    });

    const targetPillId = status === 'ALL' ? 'pill-all' : `pill-${status.toLowerCase()}`;
    const targetPill = document.getElementById(targetPillId);
    if (targetPill) {
        targetPill.classList.add('active-pill');
    }

    filterAndRenderGames();
}

function onAntiCheatFilterChange(event) {
    activeAntiCheatFilter = event.target.value;
    filterAndRenderGames();
}

function selectProtonDBFilter(tier) {
    activeProtonDBFilter = activeProtonDBFilter === tier ? '' : tier;
    const select = document.getElementById('protondb-filter');
    if (select) {
        select.value = activeProtonDBFilter;
    }
    filterAndRenderGames();
}

function onProtonDBFilterChange(event) {
    activeProtonDBFilter = event.target.value;
    filterAndRenderGames();
}

function onFeatureFilterChange(event) {
    activeFeatureFilter = event.target.value;
    filterAndRenderGames();
}

function handleColumnSort(column) {
    if (currentSortColumn === column) {
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortColumn = column;
        currentSortDirection = (column === 'playtime' || column === 'notes') ? 'desc' : 'asc';
    }
    updateSortIndicators();
    syncSortDropdown();
    filterAndRenderGames();
}

function updateSortIndicators() {
    const columns = ['status', 'protondb', 'name', 'anticheats', 'native', 'notes', 'playtime'];
    columns.forEach(col => {
        const el = document.getElementById(`col-sort-${col}`);
        if (!el) return;
        if (col === currentSortColumn) {
            el.textContent = currentSortDirection === 'asc' ? '▲' : '▼';
            el.className = 'text-[10px] text-[#e95420] font-bold';
        } else {
            el.textContent = '↕';
            el.className = 'text-[10px] text-[#6e7681]';
        }
    });
}

function syncSortDropdown() {
    const sel = document.getElementById('sort-select');
    if (!sel) return;
    if (currentSortColumn === 'status') {
        sel.value = currentSortDirection === 'asc' ? 'status_priority' : 'status_supported';
    } else if (currentSortColumn === 'protondb') {
        sel.value = currentSortDirection === 'asc' ? 'protondb_tier' : 'protondb_borked';
    } else if (currentSortColumn === 'playtime' && currentSortDirection === 'desc') {
        sel.value = 'playtime_desc';
    } else if (currentSortColumn === 'name' && currentSortDirection === 'asc') {
        sel.value = 'name_asc';
    }
}

function onSortChange(event) {
    activeSortOrder = event.target.value;
    if (activeSortOrder === 'status_priority') {
        currentSortColumn = 'status';
        currentSortDirection = 'asc';
    } else if (activeSortOrder === 'status_supported') {
        currentSortColumn = 'status';
        currentSortDirection = 'desc';
    } else if (activeSortOrder === 'protondb_tier') {
        currentSortColumn = 'protondb';
        currentSortDirection = 'asc';
    } else if (activeSortOrder === 'protondb_borked') {
        currentSortColumn = 'protondb';
        currentSortDirection = 'desc';
    } else if (activeSortOrder === 'playtime_desc') {
        currentSortColumn = 'playtime';
        currentSortDirection = 'desc';
    } else if (activeSortOrder === 'name_asc') {
        currentSortColumn = 'name';
        currentSortDirection = 'asc';
    }
    updateSortIndicators();
    filterAndRenderGames();
}

function resetFilters() {
    activeStatusFilter = 'ALL';
    activeSearchQuery = '';
    activeAntiCheatFilter = '';
    activeProtonDBFilter = '';
    activeFeatureFilter = '';
    activeSortOrder = 'status_priority';
    currentSortColumn = 'status';
    currentSortDirection = 'asc';

    document.getElementById('client-search').value = '';
    document.getElementById('anticheat-filter').value = '';
    const pdbFilter = document.getElementById('protondb-filter');
    if (pdbFilter) pdbFilter.value = '';
    const featFilter = document.getElementById('feature-filter');
    if (featFilter) featFilter.value = '';
    document.getElementById('sort-select').value = 'status_priority';

    updateSortIndicators();
    selectStatusFilter('ALL');
}

// Export scanned report
function exportData(format) {
    if (!currentScanData || !currentScanData.games) return;

    const steamid = currentScanData.steamid;

    if (format === 'json') {
        const jsonStr = JSON.stringify(currentScanData, null, 2);
        downloadFile(jsonStr, `steam_anticheat_${steamid}.json`, 'application/json');
    } else if (format === 'csv') {
        const headers = ['AppID', 'Name', 'AntiCheatStatus', 'ProtonDBTier', 'AntiCheats', 'Native', 'PlaytimeHours'];
        const rows = currentScanData.games.map(g => [
            g.appid,
            `"${g.name.replace(/"/g, '""')}"`,
            g.status,
            g.protondb_tier || 'pending',
            `"${(g.anticheats || []).join('; ')}"`,
            g.native ? 'Yes' : 'No',
            g.playtime_hours
        ]);
        const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
        downloadFile(csvContent, `steam_anticheat_${steamid}.csv`, 'text/csv');
    }
}

function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Loading state
function setLoading(isLoading) {
    const btn = document.getElementById('scan-button');
    const spinner = document.getElementById('button-spinner');
    const text = document.getElementById('button-text');

    if (isLoading) {
        btn.disabled = true;
        spinner.classList.remove('hidden');
        text.textContent = 'Checking...';
    } else {
        btn.disabled = false;
        spinner.classList.add('hidden');
        text.textContent = 'Check Library';
    }
}

// Alert banner
function showAlert(title, message, type = 'warning', actions = []) {
    const banner = document.getElementById('alert-banner');
    const titleEl = document.getElementById('alert-title');
    const msgEl = document.getElementById('alert-message');
    const actionsEl = document.getElementById('alert-actions');

    titleEl.textContent = title;
    msgEl.textContent = message;

    if (type === 'error') {
        banner.className = 'rounded-lg border border-[#f85149]/40 bg-[#f85149]/10 text-[#f85149] p-3 text-xs';
    } else {
        banner.className = 'rounded-lg border border-[#d29922]/40 bg-[#d29922]/10 text-[#d29922] p-3 text-xs';
    }

    actionsEl.innerHTML = '';
    actions.forEach(act => {
        const btn = document.createElement('button');
        btn.className = 'px-2.5 py-1 rounded bg-[#21262d] border border-[#30363d] text-xs text-[#c9d1d9] hover:bg-[#30363d] transition';
        btn.textContent = act.text;
        btn.setAttribute('onclick', act.action);
        actionsEl.appendChild(btn);
    });

    banner.classList.remove('hidden');
}

function dismissAlert() {
    document.getElementById('alert-banner').classList.add('hidden');
}

function showPrivacyHelpModal() {
    disableBodyScroll();
    document.getElementById('privacy-help-modal').classList.remove('hidden');
}
function closePrivacyHelpModal() {
    document.getElementById('privacy-help-modal').classList.add('hidden');
    enableBodyScroll();
}

// HTML escape
function escapeHTML(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Safe URL protocol validator
function isSafeUrl(urlStr) {
    if (!urlStr) return false;
    try {
        const parsed = new URL(urlStr, window.location.origin);
        return parsed.protocol === 'https:' || parsed.protocol === 'http:';
    } catch {
        return false;
    }
}

// Toast notifications
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    const colorClasses = type === 'success'
        ? 'bg-[#238636] text-white border-[#2ea043]'
        : type === 'error'
        ? 'bg-[#da3633] text-white border-[#f85149]'
        : 'bg-[#161b22] text-[#c9d1d9] border-[#30363d]';

    toast.className = `pointer-events-auto px-3.5 py-2 rounded-lg border shadow-lg text-xs font-medium flex items-center gap-2 transition-all duration-300 transform translate-y-2 opacity-0 ${colorClasses}`;
    toast.innerHTML = `<span>${escapeHTML(message)}</span>`;

    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.remove('translate-y-2', 'opacity-0');
    });

    setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-2');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, 3500);
}

// Open and render game detail modal with notes and timeline
async function openGameDetailModal(appid) {
    disableBodyScroll();
    const numericAppid = Number(appid);
    const localGame = currentScanData?.games?.find(g => g.appid === numericAppid);

    if (localGame) {
        renderGameDetailModal(localGame);
        return;
    }

    try {
        const res = await fetch(`/api/game/${numericAppid}`);
        if (!res.ok) {
            showToast(`Could not load details for game ${numericAppid}`, 'error');
            enableBodyScroll();
            return;
        }
        const game = await res.json();
        renderGameDetailModal(game);
    } catch (err) {
        showToast('Error loading game details', 'error');
        enableBodyScroll();
    }
}

function renderGameDetailModal(game) {
    const modal = document.getElementById('game-detail-modal');
    if (!modal) return;

    // Header banner
    const headerImg = document.getElementById('modal-game-header');
    if (headerImg) {
        headerImg.src = game.header_url || `https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/${game.appid}/header.jpg`;
        headerImg.alt = escapeHTML(game.name || 'Game Banner');
    }

    // Status badge
    const statusBadge = document.getElementById('modal-status-badge');
    const status = game.status || 'Unlisted';
    if (statusBadge) {
        statusBadge.className = `px-2 py-0.5 rounded text-xs font-semibold font-mono shadow status-badge-${status}`;
        statusBadge.textContent = status;
    }

    // ProtonDB badge
    const pdbBadge = document.getElementById('modal-protondb-badge');
    const pdbTier = (game.protondb_tier || (game.protondb && game.protondb.tier) || 'pending').toLowerCase();
    if (pdbBadge) {
        pdbBadge.className = `px-2 py-0.5 rounded text-xs font-semibold font-mono shadow capitalize protondb-badge-${pdbTier}`;
        pdbBadge.textContent = `ProtonDB: ${pdbTier}`;
    }

    // Title & AppID
    const titleEl = document.getElementById('modal-game-title');
    if (titleEl) titleEl.textContent = game.name || `AppID ${game.appid}`;

    const appidEl = document.getElementById('modal-appid-text');
    if (appidEl) {
        let text = `Steam AppID: ${game.appid}`;
        if (game.playtime_hours !== undefined && game.playtime_hours > 0) {
            text += ` • ${game.playtime_hours} hrs played`;
        }
        appidEl.textContent = text;
    }

    // Anti-Cheats
    const acEl = document.getElementById('modal-anticheats');
    if (acEl) {
        const acs = game.anticheats || [];
        acEl.textContent = acs.length > 0 ? acs.join(', ') : 'None tracked / Clean';
    }

    // Native execution
    const nativeEl = document.getElementById('modal-native-status');
    if (nativeEl) {
        if (game.native) {
            nativeEl.textContent = 'Native Linux Client';
            nativeEl.className = 'font-semibold text-[#2ea043] text-xs';
        } else {
            nativeEl.textContent = 'Runs via Proton / Wine';
            nativeEl.className = 'font-semibold text-[#8b949e] text-xs';
        }
    }

    // ProtonDB Score
    const pdbScoreEl = document.getElementById('modal-protondb-score');
    if (pdbScoreEl) {
        const score = game.protondb_score || (game.protondb && game.protondb.score);
        const confidence = game.protondb_confidence || (game.protondb && game.protondb.confidence);
        if (score !== undefined && score !== null && score > 0) {
            pdbScoreEl.textContent = `${score}/100 (${confidence || 'tier rating'})`;
        } else {
            pdbScoreEl.textContent = pdbTier.toUpperCase();
        }
    }

    // AWACY Updated Date
    const dateEl = document.getElementById('modal-date-changed');
    if (dateEl) {
        const dateChanged = game.date_changed || game.dateChanged || '—';
        dateEl.textContent = dateChanged;
    }

    // Notes & Workarounds
    const notesCountEl = document.getElementById('modal-notes-count');
    const notesContainer = document.getElementById('modal-notes-container');
    const notes = game.notes || [];
    if (notesCountEl) notesCountEl.textContent = `${notes.length} note${notes.length !== 1 ? 's' : ''}`;
    if (notesContainer) {
        if (notes.length > 0) {
            notesContainer.innerHTML = notes.map(n => {
                let text = '';
                let link = null;
                if (Array.isArray(n)) {
                    text = n[0] || '';
                    link = n[1] || null;
                } else if (typeof n === 'object' && n !== null) {
                    text = n.text || n.note || JSON.stringify(n);
                    link = n.url || n.link || null;
                } else {
                    text = String(n);
                }
                const safeLink = (link && isSafeUrl(link)) ? link : null;
                return `
                <div class="p-3 bg-[#0d1117] rounded-lg border border-[#21262d] space-y-1">
                    <p class="text-[#c9d1d9] leading-relaxed text-xs">${escapeHTML(text)}</p>
                    ${safeLink ? `<div class="pt-0.5"><a href="${escapeHTML(safeLink)}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 text-[#58a6ff] hover:underline text-[11px] font-mono break-all">Reference & Guide ↗</a></div>` : ''}
                </div>
                `;
            }).join('');
        } else {
            notesContainer.innerHTML = `<div class="p-3 bg-[#0d1117] rounded-lg border border-[#21262d] text-[#8b949e] italic text-xs">No specific workaround or community notes recorded for this title.</div>`;
        }
    }

    // Status Timeline & Updates
    const updatesCountEl = document.getElementById('modal-updates-count');
    const updatesContainer = document.getElementById('modal-updates-container');
    const updates = game.updates || [];
    if (updatesCountEl) updatesCountEl.textContent = `${updates.length} event${updates.length !== 1 ? 's' : ''}`;
    if (updatesContainer) {
        if (updates.length > 0) {
            updatesContainer.innerHTML = updates.map(upd => {
                let name = '';
                let date = '';
                let ref = '';
                if (typeof upd === 'object' && upd !== null) {
                    name = upd.name || 'Status Update';
                    date = upd.date || '';
                    ref = upd.reference || '';
                } else {
                    name = String(upd);
                }
                const safeRef = (ref && isSafeUrl(ref)) ? ref : null;
                return `
                <div class="relative pl-5 pb-3.5 border-l-2 border-[#30363d] last:border-l-0 last:pb-0">
                    <div class="absolute -left-[5px] top-1.5 w-2 h-2 rounded-full bg-[#bc8cff]"></div>
                    <div class="flex items-baseline justify-between gap-2">
                        <span class="font-semibold text-[#f0f6fc] text-xs">${escapeHTML(name)}</span>
                        ${date ? `<span class="text-[10px] text-[#8b949e] font-mono whitespace-nowrap">${escapeHTML(date)}</span>` : ''}
                    </div>
                    ${safeRef ? `<div class="mt-1"><a href="${escapeHTML(safeRef)}" target="_blank" rel="noopener noreferrer" class="text-[#58a6ff] hover:underline text-[11px] font-mono inline-flex items-center gap-1">Announcement & Source ↗</a></div>` : ''}
                </div>
                `;
            }).join('');
        } else {
            updatesContainer.innerHTML = `<div class="p-3 bg-[#0d1117] rounded-lg border border-[#21262d] text-[#8b949e] italic text-xs">No historical status timeline events recorded for this title.</div>`;
        }
    }

    // Reference & External Links
    const linksContainer = document.getElementById('modal-links-container');
    if (linksContainer) {
        const links = [];
        const slug = game.slug;
        if (slug) {
            links.push(`<a href="https://areweanticheatyet.com/game/${encodeURIComponent(slug)}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1 bg-[#21262d] hover:bg-[#30363d] text-[#c9d1d9] rounded border border-[#30363d] transition font-medium flex items-center gap-1"><span>AWACY Profile</span> ↗</a>`);
        }
        links.push(`<a href="https://www.protondb.com/app/${game.appid}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1 bg-[#21262d] hover:bg-[#30363d] text-[#ffd700] rounded border border-[#30363d] transition font-medium flex items-center gap-1"><span>ProtonDB</span> ↗</a>`);
        links.push(`<a href="https://store.steampowered.com/app/${game.appid}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1 bg-[#21262d] hover:bg-[#30363d] text-[#c9d1d9] rounded border border-[#30363d] transition font-medium flex items-center gap-1"><span>Steam Store</span> ↗</a>`);
        links.push(`<a href="https://steamdb.info/app/${game.appid}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1 bg-[#21262d] hover:bg-[#30363d] text-[#8b949e] hover:text-[#c9d1d9] rounded border border-[#30363d] transition font-medium flex items-center gap-1"><span>SteamDB</span> ↗</a>`);

        const refUrl = game.reference;
        if (refUrl && isSafeUrl(refUrl)) {
            links.push(`<a href="${escapeHTML(refUrl)}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1 bg-[#21262d] hover:bg-[#30363d] text-[#58a6ff] rounded border border-[#30363d] transition font-medium flex items-center gap-1"><span>Official Reference</span> ↗</a>`);
        }
        const siteUrl = game.url;
        if (siteUrl && isSafeUrl(siteUrl)) {
            links.push(`<a href="${escapeHTML(siteUrl)}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-1 bg-[#21262d] hover:bg-[#30363d] text-[#58a6ff] rounded border border-[#30363d] transition font-medium flex items-center gap-1"><span>Game Website</span> ↗</a>`);
        }

        linksContainer.innerHTML = links.join('');
    }

    modal.classList.remove('hidden');
}

function closeGameDetailModal() {
    const modal = document.getElementById('game-detail-modal');
    if (modal) modal.classList.add('hidden');
    enableBodyScroll();
}

// Anti-Cheat News Feed / Recent Updates Modal
async function openRecentUpdatesModal() {
    disableBodyScroll();
    const modal = document.getElementById('recent-updates-modal');
    const listEl = document.getElementById('recent-updates-list');
    if (!modal || !listEl) return;

    modal.classList.remove('hidden');
    listEl.innerHTML = `
        <div class="flex items-center justify-center py-10 text-[#8b949e] gap-2">
            <svg class="w-4 h-4 animate-spin text-[#e95420]" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
            </svg>
            <span>Loading latest community updates from AWACY...</span>
        </div>
    `;

    try {
        const res = await fetch('/api/db/updates?limit=50');
        if (!res.ok) {
            listEl.innerHTML = `<div class="text-center py-8 text-[#f85149]">Failed to load recent updates.</div>`;
            return;
        }
        const data = await res.json();
        const updates = data.updates || [];
        if (updates.length === 0) {
            listEl.innerHTML = `<div class="text-center py-8 text-[#8b949e]">No recent status updates recorded.</div>`;
            return;
        }

        listEl.innerHTML = updates.map(ev => {
            const statusClasses = `status-badge-${ev.status || 'Unlisted'}`;
            const safeRef = isSafeUrl(ev.reference) ? ev.reference : null;
            const acStr = (ev.anticheats && ev.anticheats.length > 0) ? ev.anticheats.join(', ') : 'None tracked';
            return `
            <div class="p-3 bg-[#0d1117] rounded-lg border border-[#21262d] hover:border-[#30363d] transition space-y-1.5">
                <div class="flex items-start justify-between gap-2">
                    <div class="flex items-center gap-2 flex-wrap">
                        <span class="font-bold text-[#f0f6fc] text-xs sm:text-sm">${escapeHTML(ev.game_name)}</span>
                        <span class="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold ${statusClasses}">${escapeHTML(ev.status)}</span>
                        ${ev.native ? '<span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-[#2ea043]/15 text-[#3fb950] border border-[#2ea043]/30">Native</span>' : ''}
                    </div>
                    ${ev.date ? `<span class="text-[10px] text-[#8b949e] font-mono whitespace-nowrap">${escapeHTML(ev.date)}</span>` : ''}
                </div>
                <p class="text-xs text-[#c9d1d9] leading-relaxed">${escapeHTML(ev.update_name)}</p>
                <div class="flex items-center justify-between gap-2 pt-1 border-t border-[#21262d]/60 text-[11px] text-[#8b949e]">
                    <span class="font-mono text-[#6e7681]">Anti-Cheat: <span class="text-[#8b949e]">${escapeHTML(acStr)}</span></span>
                    <div class="flex items-center gap-2">
                        ${ev.steam_appid ? `<button onclick="closeRecentUpdatesModal(); openGameDetailModal(${ev.steam_appid})" class="text-[#58a6ff] hover:underline font-mono">View Game Details</button>` : ''}
                        ${safeRef ? `<a href="${escapeHTML(safeRef)}" target="_blank" rel="noopener noreferrer" class="text-[#58a6ff] hover:underline font-mono">Source ↗</a>` : ''}
                    </div>
                </div>
            </div>
            `;
        }).join('');
    } catch (err) {
        listEl.innerHTML = `<div class="text-center py-8 text-[#f85149]">Error fetching timeline updates.</div>`;
    }
}

function closeRecentUpdatesModal() {
    const modal = document.getElementById('recent-updates-modal');
    if (modal) modal.classList.add('hidden');
    enableBodyScroll();
}

// Global window bindings
window.openGameDetailModal = openGameDetailModal;
window.closeGameDetailModal = closeGameDetailModal;
window.openRecentUpdatesModal = openRecentUpdatesModal;
window.closeRecentUpdatesModal = closeRecentUpdatesModal;
window.handleModalBackdropClick = handleModalBackdropClick;
window.handleColumnSort = handleColumnSort;
window.showToast = showToast;
window.showPrivacyHelpModal = showPrivacyHelpModal;
window.closePrivacyHelpModal = closePrivacyHelpModal;
window.selectStatusFilter = selectStatusFilter;
window.selectProtonDBFilter = selectProtonDBFilter;
window.onAntiCheatFilterChange = onAntiCheatFilterChange;
window.onProtonDBFilterChange = onProtonDBFilterChange;
window.onFeatureFilterChange = onFeatureFilterChange;
window.onSortChange = onSortChange;
window.resetFilters = resetFilters;
window.setViewMode = setViewMode;
window.handleScan = handleScan;
window.exportData = exportData;
window.dismissAlert = dismissAlert;


/**
 * GourmetCanvas - Main Application
 * SPA with hash routing, Three.js 3D background, and Stitch-inspired design
 */
import { initThreeBackground } from './three-bg.js';

// ============================================================
// Router
// ============================================================
const routes = {
  '/': 'home',
  '/favorites': 'favorites',
  '/mypage': 'mypage',
  '/login': 'login',
  '/register': 'register',
  '/profile-edit': 'profile-edit',
  '/detail': 'detail',
  '/review-history': 'review-history',
  '/visit-history': 'visit-history',
  '/search-history': 'search-history',
  '/theme': 'theme',
  '/admin': 'admin',
};

// Simple auth state
let isLoggedIn = false;
let currentUser = { name: '', email: '' };

function saveAuth() {
  localStorage.setItem('izakaya_auth', JSON.stringify({ isLoggedIn, currentUser }));
}

function loadAuth() {
  try {
    const saved = JSON.parse(localStorage.getItem('izakaya_auth') || 'null');
    if (saved && saved.isLoggedIn) {
      isLoggedIn = true;
      currentUser = saved.currentUser;
      loadUserData();
    }
  } catch(e) { console.error('loadAuth error', e); }
}

loadAuth();

// ============================================================
// Data Storage
// - Favorites: per-user
// - Visit count & Rating: per-user
// - Comments: SHARED across all users (each comment has authorEmail)
// ============================================================
let favorites = [];
let userShopData = {};  // { shopId: { rating, visitCount } }
let allComments = {};   // SHARED { shopId: [{ id, text, createdAt, author, authorEmail }] }

// Load shared comments (always available)
allComments = JSON.parse(localStorage.getItem('izakaya_comments') || '{}');

function getUserStorageKey(base) {
  return `${base}_${currentUser.email || 'anonymous'}`;
}

function loadUserData() {
  favorites = JSON.parse(localStorage.getItem(getUserStorageKey('izakaya_favorites')) || '[]');
  userShopData = JSON.parse(localStorage.getItem(getUserStorageKey('izakaya_userdata')) || '{}');
}

function clearUserData() {
  favorites = [];
  userShopData = {};
}

function saveFavorites() {
  localStorage.setItem(getUserStorageKey('izakaya_favorites'), JSON.stringify(favorites));
}
function saveUserData() {
  localStorage.setItem(getUserStorageKey('izakaya_userdata'), JSON.stringify(userShopData));
}
function saveComments() {
  localStorage.setItem('izakaya_comments', JSON.stringify(allComments));
}

function getUserData(shopId) {
  if (!userShopData[shopId]) {
    userShopData[shopId] = { rating: 0, visitCount: 0 };
  }
  return userShopData[shopId];
}

function getShopComments(shopId) {
  if (!allComments[shopId]) {
    allComments[shopId] = [];
  }
  return allComments[shopId];
}


// Compatibility wrapper: getReview returns a combined view

// Compatibility wrapper: getReview returns a combined view
function getReview(shopId) {
  const ud = getUserData(shopId);
  const comments = getShopComments(shopId);
  return { rating: ud.rating, visitCount: ud.visitCount, comments };
}
function saveReviews() {
  saveUserData();
  saveComments();
}

function isFavorite(shopId) {
  return favorites.some(f => f.id === shopId);
}

function toggleFavorite(shop) {
  if (isFavorite(shop.id)) {
    favorites = favorites.filter(f => f.id !== shop.id);
  } else {
    favorites.push({ ...shop, addedAt: Date.now() });
  }
  saveFavorites();
}

// ============================================================
// Navigation
// ============================================================
function navigateTo(hash) {
  const path = hash.replace('#', '') || '/';
  // Handle detail page with ID
  let pageId;
  if (path.startsWith('/detail/')) {
    pageId = 'detail';
    const shopId = path.replace('/detail/', '');
    setTimeout(() => renderDetailPage(shopId), 50);
  } else {
    pageId = routes[path] || 'home';
  }

  // Favorites requires login
  if (pageId === 'favorites' && !isLoggedIn) {
    pageId = 'favorites-locked';
  }

  // Mypage requires login
  if (pageId === 'mypage' && !isLoggedIn) {
    pageId = 'mypage-guest';
  }

  // Render favorites when navigating to that page
  if (pageId === 'favorites') {
    setTimeout(() => renderFavorites(), 50);
  }

  // Update mypage stats when navigating to mypage
  if (pageId === 'mypage') {
    setTimeout(() => updateMypageStats(), 50);
  }

  // Render history pages
  if (pageId === 'review-history') {
    setTimeout(() => renderReviewHistory(), 50);
  }
  if (pageId === 'visit-history') {
    setTimeout(() => renderVisitHistory(), 50);
  }
  if (pageId === 'search-history') {
    setTimeout(() => renderSearchHistory(), 50);
  }
  if (pageId === 'theme') {
    setTimeout(() => renderThemeSettings(), 50);
  }
  if (pageId === 'admin') {
    setTimeout(() => renderAdminStats(), 50);
  }

  // Hide all pages
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

  // Show target page
  const targetPage = document.getElementById(`page-${pageId}`);
  if (targetPage) {
    targetPage.classList.add('active');
    targetPage.style.animation = 'none';
    targetPage.offsetHeight;
    targetPage.style.animation = 'pageIn 0.4s ease forwards';
  }

  // Update bottom nav active state
  const navMap = { 'favorites-locked': 'favorites', 'mypage-guest': 'mypage', 'detail': '', 'profile-edit': 'mypage', 'review-history': 'mypage', 'visit-history': 'mypage', 'search-history': 'mypage', 'theme': 'mypage' };
  const navPageId = navMap[pageId] !== undefined ? navMap[pageId] : pageId;
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.page === navPageId);
  });

  if (pageId === 'home' && state.searchResults.length > 0 && state.lastScrollPosition > 0) {
    window.scrollTo({ top: state.lastScrollPosition, behavior: 'auto' });
  } else {
    window.scrollTo({ top: 0 });
  }
}

window.addEventListener('hashchange', () => navigateTo(location.hash));

// Track scroll position on home page
window.addEventListener('scroll', () => {
  const currentHash = location.hash || '#/';
  if (currentHash === '#/' || currentHash === '') {
    state.lastScrollPosition = window.scrollY;
  }
});

// ============================================================
// Global State
// ============================================================
const state = {
  lat: null,
  lng: null,
  genres: [],
  budgets: [],
  isLocationReady: false,
  searchResults: [],
  currentPage: 1,
  perPage: 10,
  locationMode: 'gps', // 'gps' or 'station'
  lastScrollPosition: 0
};

// ============================================================
// Fallback Data
// ============================================================
const FALLBACK_GENRES = [
  { code: 'G001', name: '居酒屋' },
  { code: 'G002', name: 'イタリアン・フレンチ' },
  { code: 'G008', name: '焼肉・ホルモン' },
  { code: 'G017', name: '韓国料理' },
  { code: 'G004', name: '和食' },
  { code: 'G005', name: '洋食' },
  { code: 'G013', name: 'ラーメン' },
  { code: 'G014', name: 'カフェ・スイーツ' },
  { code: 'G012', name: 'その他グルメ' },
];

const FALLBACK_BUDGETS = [
  { code: 'B010', name: '1,000円' },
  { code: 'B001', name: '2,000円' },
  { code: 'B002', name: '3,000円' },
  { code: 'B003', name: '4,000円' },
  { code: 'B008', name: '5,000円' },
  { code: 'B004', name: '7,000円' },
  { code: 'B005', name: '10,000円' },
  { code: 'B012', name: '20,000円' },
  { code: 'B013', name: '30,000円' },
];

// Allowed budget upper-limit values (in yen) matching HotPepper API ranges
const ALLOWED_BUDGET_VALUES = [
  500, 1000, 1500, 2000, 3000, 4000, 5000, 7000,
  10000, 15000, 20000, 30000
];

// ============================================================
// DOM Elements
// ============================================================
const locationIndicator = document.getElementById('location-indicator');
const locationText = document.getElementById('location-text');
const btnSearch = document.getElementById('search-btn');
const loaderSearch = document.getElementById('search-loader');
const btnText = document.querySelector('.btn-text');
const genreSelect = document.getElementById('genre-select');
const budgetMinSelect = document.getElementById('budget-min-select');
const budgetMaxSelect = document.getElementById('budget-max-select');
const searchForm = document.getElementById('search-form');
const resultsSection = document.getElementById('results-section');
const resultsContainer = document.getElementById('results-container');
const scrollDownBtn = document.getElementById('scroll-down-btn');
const searchSection = document.getElementById('search-section');
const slides = document.querySelectorAll('.slide');

// ============================================================
// Hero Slider
// ============================================================
let currentSlide = 0;
function nextSlide() {
  if (slides.length === 0) return;
  slides[currentSlide].classList.remove('active');
  currentSlide = (currentSlide + 1) % slides.length;
  slides[currentSlide].classList.add('active');
}
setInterval(nextSlide, 5000);

// ============================================================
// App Initialization
// ============================================================
async function init() {
  initThreeBackground();

  // Verify session with server on startup
  try {
    const res = await fetch('/api/restaurants/me/', { credentials: 'include' });
    if (res.ok) {
      const data = await res.json();
      isLoggedIn = true;
      currentUser = { name: data.display_name || data.username, email: data.email };
      saveAuth();
    }
  } catch(e) { console.warn('Session check failed', e); }

  loadAuth();
  updateAuthUI();
  updateProfileDisplay();

  navigateTo(location.hash || '#/');
  await Promise.all([fetchGenres(), fetchBudgets()]);
  setupLocationToggle();
  requestLocation();

  // Scroll to search
  if (scrollDownBtn && searchSection) {
    scrollDownBtn.addEventListener('click', () => {
      searchSection.scrollIntoView({ behavior: 'smooth' });
    });
  }

  // Login form
  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const emailInput = document.getElementById('login-email');
      const passwordInput = document.getElementById('login-password');
      const email = emailInput ? emailInput.value : '';
      const password = passwordInput ? passwordInput.value : '';

      try {
        const res = await fetch('/api/restaurants/auth/login/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
          credentials: 'include'
        });
        const data = await res.json();

        if (res.ok) {
          isLoggedIn = true;
          currentUser = { name: data.display_name || data.username, email: data.email };
          saveAuth();
          loadUserData();
          updateProfileDisplay();
          updateAuthUI();
          location.hash = '#/';
        } else {
          if (data.error === 'user_not_found') {
            alert(data.message);
            location.hash = '#/register';
          } else {
            alert(data.message || 'ログインに失敗しました');
          }
        }
      } catch (err) {
        console.error('Login error:', err);
        alert('通信エラーが発生しました');
      }
    });
  }

  // Register form
  const registerForm = document.getElementById('register-form');
  if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const nameInput = document.getElementById('register-name');
      const emailInput = document.getElementById('register-email');
      const passwordInput = document.getElementById('register-password');
      const display_name = nameInput ? nameInput.value : '';
      const email = emailInput ? emailInput.value : '';
      const password = passwordInput ? passwordInput.value : '';

      try {
        const res = await fetch('/api/restaurants/auth/register/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, display_name }),
          credentials: 'include'
        });
        const data = await res.json();
        if (res.ok) {
          isLoggedIn = true;
          currentUser = { name: data.display_name || data.username, email: data.email };
          saveAuth();
          loadUserData();
          updateProfileDisplay();
          updateAuthUI();
          alert('登録が完了しました！');
          location.hash = '#/';
        } else {
          alert(data.error || '登録に失敗しました');
        }
      } catch (err) {
        console.error('Register error:', err);
        alert('通信エラーが発生しました');
      }
    });
  }

  // Google login button
  const googleBtn = document.querySelector('.google-btn');
  if (googleBtn) {
    googleBtn.addEventListener('click', () => {
      // Simulated Google OAuth - in production, use real Google Sign-In
      const googleEmail = prompt('Googleアカウントのメールアドレスを入力:', '');
      if (!googleEmail) return;
      const userName = googleEmail.split('@')[0];
      isLoggedIn = true;
      currentUser = { name: userName, email: googleEmail };
      saveAuth();
      loadUserData();
      updateProfileDisplay();
      updateAuthUI();
      location.hash = '#/';
    });
  }

  // Password toggle
  const passwordToggle = document.getElementById('password-toggle');
  const passwordInput = document.getElementById('login-password');
  if (passwordToggle && passwordInput) {
    passwordToggle.addEventListener('click', () => {
      const isPassword = passwordInput.type === 'password';
      passwordInput.type = isPassword ? 'text' : 'password';
      passwordToggle.querySelector('.material-icons-round').textContent =
        isPassword ? 'visibility' : 'visibility_off';
    });
  }

  // Logout button
  const logoutBtn = document.getElementById('logout-btn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      isLoggedIn = false;
      currentUser = { name: '', email: '' };
      saveAuth();
      clearUserData();
      updateAuthUI();
      location.hash = '#/login';
    });
  }

  // Favorites login redirect button
  const favLoginBtn = document.getElementById('fav-login-btn');
  if (favLoginBtn) {
    favLoginBtn.addEventListener('click', () => {
      location.hash = '#/login';
    });
  }

  // Profile edit form
  const profileEditForm = document.getElementById('profile-edit-form');
  if (profileEditForm) {
    profileEditForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const nameInput = document.getElementById('edit-name');
      const emailInput = document.getElementById('edit-email');
      if (nameInput && emailInput) {
        currentUser.name = nameInput.value;
        currentUser.email = emailInput.value;
        updateProfileDisplay();
        location.hash = '#/mypage';
      }
    });
  }

  // Cancel profile edit
  const profileEditCancel = document.getElementById('profile-edit-cancel');
  const profileEditCancelBottom = document.getElementById('profile-edit-cancel-bottom');
  const cancelEdit = () => { location.hash = '#/mypage'; };
  if (profileEditCancel) profileEditCancel.addEventListener('click', cancelEdit);
  if (profileEditCancelBottom) profileEditCancelBottom.addEventListener('click', cancelEdit);

  setupScrollAnimations();
}

// ============================================================
// Location Mode Toggle (GPS vs Station)
// ============================================================
function setupLocationToggle() {
  const toggleBtns = document.querySelectorAll('.location-toggle-btn');
  const gpsSection = document.getElementById('gps-section');
  const stationSection = document.getElementById('station-section');

  toggleBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      toggleBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.locationMode = btn.dataset.mode;

      if (gpsSection && stationSection) {
        if (state.locationMode === 'gps') {
          gpsSection.classList.remove('hidden');
          stationSection.classList.add('hidden');
          // Re-enable search if GPS was already acquired
          if (state.isLocationReady) btnSearch.disabled = false;
        } else {
          gpsSection.classList.add('hidden');
          stationSection.classList.remove('hidden');
          btnSearch.disabled = false;
        }
      }
    });
  });
}

// ============================================================
// Auth UI Update
// ============================================================
function updateAuthUI() {
  const currentHash = location.hash || '#/';
  if (currentHash === '#/favorites' || currentHash === '#/mypage' || currentHash === '#/admin') {
    navigateTo(currentHash);
  }

  // Show/Hide admin nav
  const adminNav = document.getElementById('admin-nav');
  if (adminNav) {
    if (isLoggedIn && currentUser.email === 'test@gmail.com') {
      adminNav.classList.remove('hidden');
    } else {
      adminNav.classList.add('hidden');
    }
  }
}

function updateProfileDisplay() {
  const usernameEl = document.getElementById('mypage-username');
  const emailEl = document.getElementById('mypage-email');
  if (usernameEl) usernameEl.textContent = currentUser.name;
  if (emailEl) emailEl.textContent = currentUser.email;

  const editName = document.getElementById('edit-name');
  const editEmail = document.getElementById('edit-email');
  if (editName) editName.value = currentUser.name;
  if (editEmail) editEmail.value = currentUser.email;
}

// ============================================================
// Data Fetching
// ============================================================
async function fetchGenres() {
  try {
    const res = await fetch('/api/restaurants/genres/');
    const data = await res.json();
    if (data.results && data.results.length > 0) {
      const allowedGenres = [
        '居酒屋', 'イタリアン・フレンチ', '焼肉・ホルモン', '韓国料理',
        '和食', '洋食', 'ラーメン', 'カフェ・スイーツ', 'その他グルメ'
      ];
      state.genres = data.results.filter(genre => allowedGenres.includes(genre.name));
      populateSelect(genreSelect, state.genres, 'code', 'name');
      return;
    }
  } catch (error) {
    console.warn('API unavailable, using fallback genres');
  }
  state.genres = FALLBACK_GENRES;
  populateSelect(genreSelect, FALLBACK_GENRES, 'code', 'name');
}

function extractBudgetValue(name) {
  // Extract the upper limit value from budget name
  const rangeMatch = name.match(/([0-9,]+)[〜～]([0-9,]+)円/);
  if (rangeMatch) {
    return parseInt(rangeMatch[2].replace(/,/g, ''));
  }
  const manMatch = name.match(/(\d+)万円/);
  if (manMatch) {
    return parseInt(manMatch[1]) * 10000;
  }
  const simpleMatch = name.match(/([0-9,]+)円/);
  if (simpleMatch) {
    return parseInt(simpleMatch[1].replace(/,/g, ''));
  }
  return 0;
}

async function fetchBudgets() {
  try {
    const res = await fetch('/api/restaurants/budgets/');
    const data = await res.json();
    if (data.results && data.results.length > 0) {
      // Filter: only allowed values (1000円 increments, 10000円+ in 10000 increments, max 30000)
      // HotPepper API returns ranges like "501〜1000円", "2001〜3000円", etc.
      // We check if the upper limit of the range is in our allowed values
      state.budgets = data.results.filter(b => {
        const val = extractBudgetValue(b.name);
        // Allow exact matches or range upper limits that match
        return ALLOWED_BUDGET_VALUES.includes(val);
      });
      // If API filtering removed too many, use fallback
      if (state.budgets.length < 5) {
        state.budgets = FALLBACK_BUDGETS;
      }
      populateBudgetSelect(budgetMinSelect, state.budgets);
      populateBudgetSelect(budgetMaxSelect, state.budgets);
      return;
    }
  } catch (error) {
    console.warn('API unavailable, using fallback budgets');
  }
  state.budgets = FALLBACK_BUDGETS;
  populateBudgetSelect(budgetMinSelect, FALLBACK_BUDGETS);
  populateBudgetSelect(budgetMaxSelect, FALLBACK_BUDGETS);
}

function populateSelect(selectElement, items, valueKey, labelKey) {
  if (!selectElement) return;
  while (selectElement.options.length > 1) {
    selectElement.remove(1);
  }
  items.forEach(item => {
    const option = document.createElement('option');
    option.value = item[valueKey];
    option.textContent = item['name'];
    selectElement.appendChild(option);
  });
}

function formatBudgetName(rawName) {
  // HotPepper API returns "501〜1000円" or "2001〜3000円" etc.
  // Extract only the upper limit and display it as full number (e.g. 20,000円)
  const rangeMatch = rawName.match(/([0-9,]+)[〜～]([0-9,]+)円/);
  if (rangeMatch) {
    const upper = parseInt(rangeMatch[2].replace(/,/g, ''));
    return `${upper.toLocaleString()}円`;
  }
  // Handle "X万円" format -> convert to full number
  const manMatch = rawName.match(/(\d+)万円/);
  if (manMatch) {
    const val = parseInt(manMatch[1]) * 10000;
    return `${val.toLocaleString()}円`;
  }
  // Already formatted (e.g. "1,000円")
  return rawName;
}

function populateBudgetSelect(selectElement, items) {
  if (!selectElement) return;
  while (selectElement.options.length > 1) {
    selectElement.remove(1);
  }
  items.forEach(item => {
    const option = document.createElement('option');
    option.value = item.code || item.name;
    option.textContent = formatBudgetName(item.name);
    selectElement.appendChild(option);
  });
}

// ============================================================
// Geolocation
// ============================================================
function requestLocation() {
  if ('geolocation' in navigator) {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        state.lat = position.coords.latitude;
        state.lng = position.coords.longitude;
        state.isLocationReady = true;
        locationIndicator.className = 'status-indicator success';
        locationText.textContent = '現在地を取得しました';
        if (state.locationMode === 'gps') btnSearch.disabled = false;
      },
      (error) => {
        console.warn('Geolocation error:', error);
        locationIndicator.className = 'status-indicator error';
        locationText.textContent = '位置情報の取得に失敗しました';
        state.lat = 35.6580;
        state.lng = 139.7016;
        state.isLocationReady = true;
        setTimeout(() => {
          locationText.textContent = '位置情報が使えないため、渋谷駅周辺で検索します';
          if (state.locationMode === 'gps') btnSearch.disabled = false;
        }, 2000);
      },
      { enableHighAccuracy: true, timeout: 5000 }
    );
  } else {
    locationIndicator.className = 'status-indicator error';
    locationText.textContent = 'ブラウザが位置情報に対応していません';
  }
}

// ============================================================
// Search & Rendering
// ============================================================
searchForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  btnSearch.disabled = true;
  btnText.textContent = '検索中...';
  loaderSearch.classList.remove('hidden');
  resultsSection.classList.add('hidden');

  const formData = new FormData(searchForm);
  const genre = formData.get('genre');
  const budgetMin = formData.get('budget_min');
  const budgetMax = formData.get('budget_max');
  const keyword = formData.get('keyword');
  const people = formData.get('people');
  const freeDrink = formData.get('free_drink');
  const freeFood = formData.get('free_food');

  // Build params based on location mode
  let targetUrl = '/api/restaurants/search/';
  let searchParams;

  if (state.locationMode === 'station') {
    const stationInput = document.getElementById('station-input');
    const stationName = stationInput ? stationInput.value.trim() : '';
    if (!stationName) {
      alert('駅名を入力してください');
      btnSearch.disabled = false;
      btnText.textContent = 'お店を探す';
      loaderSearch.classList.add('hidden');
      return;
    }
    searchParams = new URLSearchParams({ keyword: stationName, range: 3 });
  } else {
    if (!state.isLocationReady) return;
    searchParams = new URLSearchParams({ lat: state.lat, lng: state.lng, range: 3 });
  }

  // Add filters
  if (genre) searchParams.append('genre', genre);
  if (budgetMin) searchParams.append('budget_min', budgetMin);
  if (budgetMax) searchParams.append('budget_max', budgetMax);
  if (people) searchParams.append('people', people);
  if (freeDrink) searchParams.append('free_drink', 'true');
  if (freeFood) searchParams.append('free_food', 'true');

  let fetchOptions = { method: 'GET' };

  // If keyword is present, use AI search (Gemini)
  if (keyword && keyword.trim() !== '') {
    targetUrl = '/api/restaurants/natural-search/';
    const aiQuery = keyword.trim();
    const body = {
      query: aiQuery,
      lat: state.lat,
      lng: state.lng,
      // 既存のフィルタをコンテキストとして送信
      current_genre: genre ? genreSelect.options[genreSelect.selectedIndex].text : null,
      current_budget_max: budgetMax ? budgetMaxSelect.options[budgetMaxSelect.selectedIndex].text : null,
      current_people: people || null,
      current_free_drink: !!freeDrink,
      current_free_food: !!freeFood
    };
    
    fetchOptions = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    };
  } else {
    targetUrl += '?' + searchParams.toString();
  }

  try {
    const res = await fetch(targetUrl, fetchOptions);
    const data = await res.json();

    if (data.shops && data.shops.length > 0) {
      state.searchResults = data.shops;
      state.currentPage = 1;
      // Save to search history
      saveSearchHistory({
        mode: state.locationMode,
        keyword: state.locationMode === 'station' ? (document.getElementById('station-input')?.value || '') : '',
        genre: genre ? (genreSelect?.options[genreSelect.selectedIndex]?.text || '') : '',
        budget: budgetMax ? (budgetMaxSelect?.options[budgetMaxSelect.selectedIndex]?.text || '') : '',
        resultCount: data.shops.length,
        timestamp: Date.now()
      });
      sortAndRenderResults();
    } else {
      resultsContainer.innerHTML = `
        <div class="empty-results glass-card">
          <span class="material-icons-round" style="font-size: 2.5rem; color: var(--text-muted);">search_off</span>
          <p>条件に合うお店が見つかりませんでした。</p>
          <span class="text-muted-sm">条件を変えて再度お試しください。</span>
        </div>`;
      resultsSection.classList.remove('hidden');
    }
  } catch (error) {
    console.error('Search error:', error);
    alert('検索中にエラーが発生しました。バックエンドサーバーが起動しているか確認してください。');
  } finally {
    btnSearch.disabled = false;
    btnText.textContent = 'お店を探す';
    loaderSearch.classList.add('hidden');
  }
});

// ============================================================
// Sorting Logic
// ============================================================
const sortSelect = document.getElementById('sort-select');
if (sortSelect) {
  sortSelect.addEventListener('change', () => {
    if (state.searchResults.length > 0) {
      state.currentPage = 1;
      sortAndRenderResults();
    }
  });
}

function sortAndRenderResults() {
  if (!state.searchResults.length) return;
  const sortType = sortSelect ? sortSelect.value : 'distance';
  let sortedShops = [...state.searchResults];

  if (sortType === 'distance') {
    sortedShops.sort((a, b) => (a.distance_km || 0) - (b.distance_km || 0));
  } else if (sortType === 'recommend') {
    sortedShops.sort((a, b) => (a.originalIndex || 0) - (b.originalIndex || 0));
  }

  renderResults(sortedShops);
}

function renderResults(shops) {
  const totalPages = Math.ceil(shops.length / state.perPage);
  const start = (state.currentPage - 1) * state.perPage;
  const end = start + state.perPage;
  const pageShops = shops.slice(start, end);

  resultsContainer.innerHTML = '';

  // Results count
  resultsContainer.insertAdjacentHTML('beforeend', `
    <div class="results-count">
      <span>${shops.length}件中 ${start + 1}〜${Math.min(end, shops.length)}件を表示</span>
    </div>
  `);

  pageShops.forEach((shop, index) => {
    const imgUrl = shop.photo || 'https://via.placeholder.com/150x150.png?text=No+Image';
    const favClass = isFavorite(shop.id) ? 'active' : '';
    const review = getReview(shop.id);
    const visitBadge = isLoggedIn ? `<span class="visit-badge">${review.visitCount}回来店</span>` : '';

    // Only show favorite button when logged in
    const favBtnHTML = isLoggedIn ? `
          <button class="fav-btn ${favClass}" data-shop-id="${shop.id}" title="お気に入り">
            <span class="material-icons-round">${isFavorite(shop.id) ? 'favorite' : 'favorite_border'}</span>
          </button>` : '';

    const cardHTML = `
      <div class="result-card glass-card-subtle" style="animation-delay: ${index * 0.05}s" data-shop-id="${shop.id}">
        <div class="card-img-container">
          <img src="${imgUrl}" alt="${shop.name}" class="card-img" loading="lazy" />
          ${favBtnHTML}
          ${review.visitCount > 0 ? `<div class="visit-overlay"><span class="material-icons-round">check_circle</span></div>` : ''}
        </div>
        <div class="card-body">
          <h3 class="card-title">${shop.name}</h3>
          <div class="card-rating-row">
            ${visitBadge}
          </div>

          <div class="card-info-section">
            ${shop.ai_reason ? `
              <div class="ai-reason-badge">
                <span class="material-icons-round">auto_awesome</span>
                <p>${shop.ai_reason}</p>
              </div>
            ` : ''}

            <div class="card-external-ratings">
              ${(shop.google_rating || shop.is_google) ? `
                <div class="ext-rating google" title="Google Maps 評価">
                   <img src="https://www.google.com/images/branding/product/ico/maps15_bnuw3a_32dp.ico" width="14" height="14">
                   <span>${shop.google_rating ? shop.google_rating.toFixed(1) : '評価あり'}</span>
                </div>` : ''}
              ${(shop.is_hotpepper || (shop.url && shop.url.includes('hotpepper'))) ? `
                <div class="ext-rating hotpepper" title="HotPepper 掲載">
                   <span class="hp-letter">H</span>
                   <span>HotPepper掲載</span>
                </div>` : ''}
            </div>
          </div>

          <div class="card-meta">
            ${shop.genre ? `<span class="meta-badge">${shop.genre}</span>` : ''}
            ${shop.budget ? `<span class="meta-badge">${formatBudgetName(shop.budget)}</span>` : ''}
          </div>

          <div class="card-distance">
            <span class="material-icons-round" style="font-size: 14px;">place</span>
            ${shop.distance_km ? `ここから徒歩 約${shop.walk_time_min}分 (${shop.distance_km}km)` : (shop.address || '')}
          </div>
          <div class="card-actions">
            <button class="btn detail-btn" data-shop-id="${shop.id}">
              <span class="material-icons-round">info</span>
              <span>詳細を見る</span>
            </button>
          </div>
        </div>
      </div>
    `;
    resultsContainer.insertAdjacentHTML('beforeend', cardHTML);
  });

  // Pagination
  if (totalPages > 1) {
    let paginationHTML = '<div class="pagination">';
    if (state.currentPage > 1) {
      paginationHTML += `<button class="page-btn" data-page="${state.currentPage - 1}"><span class="material-icons-round">chevron_left</span></button>`;
    }
    for (let i = 1; i <= totalPages; i++) {
      paginationHTML += `<button class="page-btn ${i === state.currentPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
    }
    if (state.currentPage < totalPages) {
      paginationHTML += `<button class="page-btn" data-page="${state.currentPage + 1}"><span class="material-icons-round">chevron_right</span></button>`;
    }
    paginationHTML += '</div>';
    resultsContainer.insertAdjacentHTML('beforeend', paginationHTML);
  }

  // Event listeners
  resultsContainer.querySelectorAll('.fav-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const shopId = btn.dataset.shopId;
      const shop = shops.find(s => s.id === shopId) || state.searchResults.find(s => s.id === shopId);
      if (shop) {
        toggleFavorite(shop);
        btn.classList.toggle('active');
        btn.querySelector('.material-icons-round').textContent = isFavorite(shopId) ? 'favorite' : 'favorite_border';
      }
    });
  });

  resultsContainer.querySelectorAll('.detail-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const shopId = btn.dataset.shopId;
      location.hash = `#/detail/${shopId}`;
    });
  });

  resultsContainer.querySelectorAll('.page-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      state.currentPage = parseInt(btn.dataset.page);
      sortAndRenderResults();
      resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  resultsSection.classList.remove('hidden');
  setTimeout(() => {
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 100);
}

// ============================================================
// Detail Page
// ============================================================
function renderDetailPage(shopId) {
  const container = document.getElementById('detail-content');
  if (!container) return;

  // Find shop from search results or favorites
  const shop = (state.searchResults || []).find(s => s.id === shopId)
    || favorites.find(s => s.id === shopId);

  if (!shop) {
    container.innerHTML = '<div class="empty-state glass-card"><p>店舗情報が見つかりません</p></div>';
    return;
  }


  const review = getReview(shopId);
  const imgUrl = shop.photo || 'https://via.placeholder.com/400x200.png?text=No+Image';

  const googleMapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(shop.name + ' ' + (shop.address || ''))}`;

  container.innerHTML = `
    <div class="detail-hero">
      <img src="${imgUrl}" alt="${shop.name}" class="detail-hero-img" />
      ${isLoggedIn ? `<button class="fav-btn-detail ${isFavorite(shopId) ? 'active' : ''}" id="detail-fav-btn">
        <span class="material-icons-round">${isFavorite(shopId) ? 'favorite' : 'favorite_border'}</span>
      </button>` : ''}
    </div>

    <div class="detail-info glass-card">
      <h2 class="detail-name">${shop.name}</h2>
      <div class="detail-meta">
        ${shop.genre ? `<span class="meta-badge">${shop.genre}</span>` : ''}
        ${shop.budget ? `<span class="meta-badge">${formatBudgetName(shop.budget)}</span>` : ''}
      </div>

      <div class="card-external-ratings" style="margin: 0.8rem 0 1.2rem 0;">
        ${(shop.google_rating || shop.is_google) ? `
          <div class="ext-rating google">
             <img src="https://www.google.com/images/branding/product/ico/maps15_bnuw3a_32dp.ico" width="14" height="14">
             <span>Google Maps: ${shop.google_rating ? shop.google_rating.toFixed(1) : '評価あり'}</span>
          </div>` : ''}
        ${(shop.is_hotpepper || (shop.url && shop.url.includes('hotpepper'))) ? `
          <div class="ext-rating hotpepper">
             <span class="hp-letter">H</span>
             <span>HotPepper掲載店</span>
          </div>` : ''}
      </div>

      <div class="detail-address">
        <span class="material-icons-round">place</span>
        <span>${shop.address || '住所情報なし'}</span>
      </div>
      ${shop.open ? `<div class="detail-open"><span class="material-icons-round">schedule</span><span>${shop.open}</span></div>` : ''}
      <div class="detail-links">
        ${shop.source === 'hotpepper' && shop.url ? `<a href="${shop.url}" target="_blank" class="detail-link"><span class="material-icons-round">open_in_new</span>HotPepperで見る</a>` : ''}
        <a href="${googleMapsUrl}" target="_blank" class="detail-link detail-link-map"><span class="material-icons-round">map</span>Googleマップで見る</a>
        <button class="detail-link share-btn" id="share-btn" data-shop-id="${shopId}">
          <span class="material-icons-round">share</span>シェア
        </button>
      </div>
    </div>

    ${isLoggedIn ? `
    <!-- Visit Counter -->
    <div class="detail-visit-card glass-card">
      <h3 class="detail-section-title">
        <span class="material-icons-round">directions_walk</span>
        来店回数
      </h3>
      <div class="visit-counter">
        <button class="counter-btn minus" id="visit-minus">
          <span class="material-icons-round">remove</span>
        </button>
        <span class="counter-value" id="visit-count">${review.visitCount}</span>
        <span class="counter-label">回</span>
        <button class="counter-btn plus" id="visit-plus">
          <span class="material-icons-round">add</span>
        </button>
      </div>
    </div>

    ` : ''}

    <!-- Comment -->
    <div class="detail-comment-card glass-card">
      <h3 class="detail-section-title">
        <span class="material-icons-round">chat</span>
        コメント
      </h3>
      <div id="comments-list"></div>
      <div class="comment-input-area">
        <textarea class="text-input textarea-input" id="detail-comment" rows="2" placeholder="このお店の感想を書いてください..."></textarea>
        <button class="btn primary-btn" id="add-comment-btn" style="margin-top: 0.75rem;">
          <span class="material-icons-round">add_comment</span>
          <span>投稿する</span>
        </button>
      </div>
    </div>
  `;

  // Event listeners - only attach favorite button listener when logged in
  const detailFavBtn = document.getElementById('detail-fav-btn');
  if (detailFavBtn) {
    detailFavBtn.addEventListener('click', () => {
      toggleFavorite(shop);
      const btn = document.getElementById('detail-fav-btn');
      btn.classList.toggle('active');
      btn.querySelector('.material-icons-round').textContent = isFavorite(shopId) ? 'favorite' : 'favorite_border';
    });
  }

  // Share button
  const shareBtn = document.getElementById('share-btn');
  if (shareBtn) {
    shareBtn.addEventListener('click', () => {
      shareShop(shopId);
    });
  }

  // Helper: update the visit count on search result cards in real-time
  function updateSearchCardVisitCount(sid) {
    const r = getReview(sid);
    // Update visit badge in search result card
    const card = resultsContainer?.querySelector(`.result-card[data-shop-id="${sid}"]`);
    if (card) {
      const badge = card.querySelector('.visit-badge');
      if (badge) badge.textContent = `${r.visitCount}回来店`;
    }
  }

  const visitMinusBtn = document.getElementById('visit-minus');
  const visitPlusBtn = document.getElementById('visit-plus');
  if (visitMinusBtn) {
    visitMinusBtn.addEventListener('click', () => {
      const ud = getUserData(shopId);
      if (ud.visitCount > 0) ud.visitCount--;
      saveUserData();
      document.getElementById('visit-count').textContent = ud.visitCount;
      updateSearchCardVisitCount(shopId);
    });
  }

  if (visitPlusBtn) {
    visitPlusBtn.addEventListener('click', () => {
      const ud = getUserData(shopId);
      ud.visitCount++;
      saveUserData();
      document.getElementById('visit-count').textContent = ud.visitCount;
      updateSearchCardVisitCount(shopId);
    });
  }

  // Rating slider removed

  // Comments system
  function renderComments() {
    const comments = getShopComments(shopId);
    const list = document.getElementById('comments-list');
    if (!list) return;
    if (comments.length === 0) {
      list.innerHTML = '<p class="no-comments-msg">まだコメントがありません</p>';
      return;
    }
    list.innerHTML = comments.map(c => {
      const authorName = c.author || '匿名';
      const isOwnComment = isLoggedIn && c.authorEmail === currentUser.email;
      const authorHTML = c.author
        ? `<a href="#/mypage" class="comment-author-link">${escapeHtml(authorName)}</a>`
        : `<span class="comment-author-anon">${authorName}</span>`;
      const menuHTML = isOwnComment ? `
        <div class="comment-menu-wrap">
          <button class="comment-menu-btn" data-id="${c.id}" title="メニュー">
            <span class="material-icons-round">more_horiz</span>
          </button>
          <div class="comment-dropdown" id="dropdown-${c.id}">
            <button class="dropdown-item edit-comment-btn" data-id="${c.id}">
              <span class="material-icons-round">edit</span>編集
            </button>
            <button class="dropdown-item delete-comment-btn" data-id="${c.id}">
              <span class="material-icons-round">delete</span>削除
            </button>
          </div>
        </div>` : '';
      return `
      <div class="comment-item" data-comment-id="${c.id}">
        <div class="comment-content">
          <div class="comment-header">
            ${authorHTML}
            <span class="comment-date">${formatCommentDate(c.createdAt)}</span>
          </div>
          <p class="comment-text">${escapeHtml(c.text)}</p>
        </div>
        ${menuHTML}
      </div>`;
    }).join('');

    // Close all dropdowns when clicking outside
    document.addEventListener('click', closeAllDropdowns, { once: true });

    list.querySelectorAll('.comment-menu-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = btn.dataset.id;
        const dropdown = document.getElementById(`dropdown-${id}`);
        const isOpen = dropdown.classList.contains('open');
        document.querySelectorAll('.comment-dropdown').forEach(d => d.classList.remove('open'));
        if (!isOpen) {
          dropdown.classList.add('open');
          document.addEventListener('click', closeAllDropdowns, { once: true });
        }
      });
    });

    list.querySelectorAll('.edit-comment-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = parseInt(btn.dataset.id);
        const comments = getShopComments(shopId);
        const comment = comments.find(c => c.id === id);
        if (!comment) return;
        closeAllDropdowns();
        // Show inline edit
        const commentItem = list.querySelector(`[data-comment-id="${id}"]`);
        commentItem.innerHTML = `
          <div class="comment-edit-area">
            <textarea class="text-input textarea-input comment-edit-ta" rows="2">${escapeHtml(comment.text)}</textarea>
            <div class="comment-edit-actions">
              <button class="btn primary-btn btn-sm comment-save-edit" data-id="${id}"><span class="material-icons-round">save</span>保存</button>
              <button class="btn btn-sm comment-cancel-edit"><span class="material-icons-round">close</span>キャンセル</button>
            </div>
          </div>
        `;
        commentItem.querySelector('.comment-save-edit').addEventListener('click', () => {
          const newText = commentItem.querySelector('.comment-edit-ta').value.trim();
          if (!newText) return;
          const comments2 = getShopComments(shopId);
          const c = comments2.find(c => c.id === id);
          if (c) { c.text = newText; c.editedAt = Date.now(); }
          saveComments();
          renderComments();
        });
        commentItem.querySelector('.comment-cancel-edit').addEventListener('click', () => {
          renderComments();
        });
      });
    });

    list.querySelectorAll('.delete-comment-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = parseInt(btn.dataset.id);
        closeAllDropdowns();
        const comments = getShopComments(shopId);
        allComments[shopId] = comments.filter(c => c.id !== id);
        saveComments();
        renderComments();
      });
    });
  }

  function closeAllDropdowns() {
    document.querySelectorAll('.comment-dropdown').forEach(d => d.classList.remove('open'));
  }

  function escapeHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;').replace(/\n/g,'<br>');
  }

  function formatCommentDate(ts) {
    const d = new Date(ts);
    return `${d.getFullYear()}/${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
  }

  renderComments();

  document.getElementById('add-comment-btn').addEventListener('click', () => {
    const ta = document.getElementById('detail-comment');
    const text = ta.value.trim();
    if (!text) return;
    const comments = getShopComments(shopId);
    const author = isLoggedIn ? currentUser.name : null;
    const authorEmail = isLoggedIn ? currentUser.email : null;
    comments.push({ id: Date.now(), text, createdAt: Date.now(), author, authorEmail });
    saveComments();
    ta.value = '';
    renderComments();
    const btn = document.getElementById('add-comment-btn');
    btn.querySelector('span:last-child').textContent = '投稿しました！';
    setTimeout(() => { btn.querySelector('span:last-child').textContent = '投稿する'; }, 1500);
  });
}

// ============================================================
// Favorites Page
// ============================================================
function renderFavorites() {
  const container = document.getElementById('favorites-list');
  const emptyState = document.querySelector('#page-favorites .empty-state');
  const sortBar = document.getElementById('fav-sort-bar');

  if (!container) return;

  if (favorites.length === 0) {
    container.innerHTML = '';
    if (emptyState) emptyState.classList.remove('hidden');
    if (sortBar) sortBar.classList.add('hidden');
    return;
  }

  if (emptyState) emptyState.classList.add('hidden');
  if (sortBar) sortBar.classList.remove('hidden');

  // Sort
  const sortType = document.getElementById('fav-sort-select')?.value || 'added';
  let sorted = [...favorites];

  if (sortType === 'visits') {
    sorted.sort((a, b) => (getReview(b.id).visitCount || 0) - (getReview(a.id).visitCount || 0));
  } else {
    sorted.sort((a, b) => (b.addedAt || 0) - (a.addedAt || 0));
  }

  container.innerHTML = '';
  sorted.forEach(shop => {
    const review = getReview(shop.id);
    const imgUrl = shop.photo || 'https://via.placeholder.com/80x80.png?text=No+Image';

    container.insertAdjacentHTML('beforeend', `
      <div class="fav-card glass-card-subtle" data-shop-id="${shop.id}">
        <img src="${imgUrl}" alt="${shop.name}" class="fav-card-img" />
        <div class="fav-card-body">
          <h3 class="fav-card-name">${shop.name}</h3>
          <div class="fav-card-meta">
            <span class="fav-visits">${review.visitCount}回来店</span>
          </div>

          <div class="card-external-ratings">
            ${(shop.google_rating || shop.is_google) ? `
              <div class="ext-rating google" title="Google Maps 評価">
                 <img src="https://www.google.com/images/branding/product/ico/maps15_bnuw3a_32dp.ico" width="14" height="14">
                 <span>${shop.google_rating ? shop.google_rating.toFixed(1) : '評価あり'}</span>
              </div>` : ''}
            ${(shop.is_hotpepper || (shop.url && shop.url.includes('hotpepper'))) ? `
              <div class="ext-rating hotpepper" title="HotPepper 掲載">
                 <span class="hp-letter">H</span>
                 <span>HotPepper掲載</span>
              </div>` : ''}
          </div>
          ${shop.genre ? `<span class="meta-badge" style="font-size: 0.7rem;">${shop.genre}</span>` : ''}
        </div>
        <div class="fav-card-actions">
          <button class="icon-btn fav-detail-btn" data-shop-id="${shop.id}" title="詳細">
            <span class="material-icons-round">chevron_right</span>
          </button>
          <button class="icon-btn fav-remove-btn" data-shop-id="${shop.id}" title="削除">
            <span class="material-icons-round" style="color: var(--primary);">delete</span>
          </button>
        </div>
      </div>
    `);
  });

  container.querySelectorAll('.fav-detail-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      location.hash = `#/detail/${btn.dataset.shopId}`;
    });
  });

  container.querySelectorAll('.fav-remove-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      favorites = favorites.filter(f => f.id !== btn.dataset.shopId);
      saveFavorites();
      renderFavorites();
    });
  });
}

  // (Manual search form handles keyword-based AI search now)
// ============================================================
// Search History Functions
// ============================================================
function saveSearchHistory(searchData) {
  if (!isLoggedIn) return; // ログインしていない場合は保存しない

  const history = JSON.parse(localStorage.getItem(getUserStorageKey('izakaya_search_history')) || '[]');
  history.unshift({
    ...searchData,
    id: Date.now()
  });

  // 最新50件のみ保持
  if (history.length > 50) {
    history.splice(50);
  }

  localStorage.setItem(getUserStorageKey('izakaya_search_history'), JSON.stringify(history));
}

function getSearchHistory() {
  if (!isLoggedIn) return [];
  return JSON.parse(localStorage.getItem(getUserStorageKey('izakaya_search_history')) || '[]');
}

function clearSearchHistory() {
  if (!isLoggedIn) return;
  localStorage.removeItem(getUserStorageKey('izakaya_search_history'));
}

// ============================================================
// Share Shop Function
// ============================================================
function shareShop(shopId) {
  // まずローカルにある店舗情報を探す
  const shop = (state.searchResults || []).find(s => s.id === shopId) || favorites.find(s => s.id === shopId);

  // 共通処理: shareTextとshareUrlを決定
  const buildShareData = (shopData) => {
    const baseUrl = window.location.origin;
    const shareUrl = `${baseUrl}/#/detail?shop_id=${shopId}`;
    const shareText = `おすすめの飲食店「${shopData?.name || ''}」を見つけました！\n${shareUrl}`;
    return { shareText, shareUrl, shop: shopData };
  };

  // Try backend first if shop exists so we can rely on stored data
  fetch(`/api/restaurants/share/${shopId}/`)
    .then(res => res.json())
    .then(data => {
      let shareText, shareUrl, shopData;
      if (data && data.share_url) {
        shareText = data.share_text;
        shareUrl = data.share_url;
        shopData = data.shop;
        // backend responded but without shop details
        if (!shopData && shop) {
          // rebuild text with local shop
          const fallback = buildShareData(shop);
          shareText = fallback.shareText;
          shareUrl = fallback.shareUrl;
          shopData = shop;
        }
      } else {
        // API失敗時はローカル情報で代用
        ({ shareText, shareUrl, shop: shopData } = buildShareData(shop));
      }

      // Web Share APIが利用可能かチェック
      if (navigator.share) {
        navigator.share({
          title: `おすすめの飲食店: ${shopData?.name || ''}`,
          text: shareText,
          url: shareUrl
        }).catch(err => {
          console.log('Share failed:', err);
          fallbackShare(shareText, shareUrl);
        });
      } else {
        fallbackShare(shareText, shareUrl);
      }
    })
    .catch(err => {
      console.error('Share API error:', err);
      // フォールバック：ローカル情報を使う
      const { shareText, shareUrl } = buildShareData(shop);
      fallbackShare(shareText, shareUrl);
    });
}

function fallbackShare(text, url) {
  // クリップボードにコピー
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => {
      alert('シェアテキストをクリップボードにコピーしました！');
    }).catch(() => {
      // フォールバック: テキストエリアを表示
      showShareDialog(text, url);
    });
  } else {
    showShareDialog(text, url);
  }
}

function showShareDialog(text, url) {
  const dialog = document.createElement('div');
  dialog.className = 'share-dialog-overlay';
  dialog.innerHTML = `
    <div class="share-dialog glass-card">
      <h3>シェア</h3>
      <p>以下のテキストをコピーしてシェアしてください：</p>
      <textarea class="share-textarea" readonly>${text}</textarea>
      <div class="share-dialog-buttons">
        <button class="btn-secondary" onclick="this.closest('.share-dialog-overlay').remove()">閉じる</button>
        <button class="btn-primary" onclick="copyShareText(this)">コピー</button>
      </div>
    </div>
  `;
  document.body.appendChild(dialog);

  // コピー機能
  dialog.querySelector('.btn-primary').addEventListener('click', function() {
    const textarea = dialog.querySelector('.share-textarea');
    textarea.select();
    document.execCommand('copy');
    this.textContent = 'コピーしました！';
    setTimeout(() => {
      dialog.remove();
    }, 1500);
  });
}

// ============================================================
// Mypage Stats
// ============================================================
function updateMypageStats() {
  const favCount = favorites.length;
  
  // Review count: shops where THIS user has authored comments
  let reviewCount = 0;
  for (const shopId in allComments) {
    const hasMyComment = allComments[shopId].some(c => c.authorEmail === currentUser.email);
    if (hasMyComment) reviewCount++;
  }
  
  // Visit count: shops where THIS user has visited
  let visitCount = 0;
  for (const shopId in userShopData) {
    if (userShopData[shopId].visitCount > 0) visitCount++;
  }
  
  const statFav = document.getElementById('stat-favorites');
  const statRev = document.getElementById('stat-reviews');
  const statVis = document.getElementById('stat-visits');
  if (statFav) statFav.textContent = favCount;
  if (statRev) statRev.textContent = reviewCount;
  if (statVis) statVis.textContent = visitCount;
}

// ============================================================
// Review History Page (only MY comments)
// ============================================================

function renderReviewHistory() {
  const container = document.getElementById('review-history-list');
  if (!container) return;

  if (!isLoggedIn) {
    container.innerHTML = `
      <div class="empty-state glass-card" style="display:flex; flex-direction:column; align-items:center;">
        <span class="material-icons-round" style="font-size: 3rem; color: var(--primary);">login</span>
        <p>ログインが必要です</p>
        <span class="text-muted-sm">レビュー履歴を表示するにはログインしてください</span>
        <button class="btn primary-btn btn-block" style="margin-top: 1rem; max-width: 280px;" onclick="location.hash='#/login'">
          <span class="material-icons-round">login</span>
          <span>ログインする</span>
        </button>
      </div>`;
    return;
  }

  const reviewedShops = [];
  for (const shopId in allComments) {
    const myComments = allComments[shopId].filter(c => c.authorEmail === currentUser.email);
    if (myComments.length > 0) {
      const shop = favorites.find(f => f.id === shopId) || (state.searchResults || []).find(s => s.id === shopId);
      const ud = userShopData[shopId] || { rating: 0 };
      reviewedShops.push({
        id: shopId,
        name: shop ? shop.name : shopId,
        photo: shop ? shop.photo : '',
        genre: shop ? shop.genre : '',
        rating: ud.rating,
        commentCount: myComments.length,
      });
    }
  }

  if (reviewedShops.length === 0) {
    container.innerHTML = `
      <div class="empty-state glass-card">
        <span class="material-icons-round" style="font-size: 3rem; color: var(--primary);">rate_review</span>
        <p>レビュー履歴はまだありません</p>
        <span class="text-muted-sm">お店の詳細ページからコメントを投稿しましょう</span>
      </div>`;
    return;
  }

  container.innerHTML = reviewedShops.map(shop => {
    const stars = '\u2605'.repeat(Math.round(shop.rating)) + '\u2606'.repeat(5 - Math.round(shop.rating));
    const imgUrl = shop.photo || 'https://via.placeholder.com/60x60.png?text=No+Image';
    return `
      <div class="history-card glass-card-subtle" onclick="location.hash='#/detail/${shop.id}'">
        <img src="${imgUrl}" alt="${shop.name}" class="history-card-img" />
        <div class="history-card-body">
          <h3 class="history-card-name">${shop.name}</h3>
          <div class="history-card-meta">
            <span class="history-stars">${stars}</span>
            <span class="history-rating">${shop.rating > 0 ? shop.rating.toFixed(1) : '-'}</span>
          </div>
          <span class="text-muted-sm">コメント ${shop.commentCount}件</span>
        </div>
        <span class="material-icons-round" style="color: var(--text-muted);">chevron_right</span>
      </div>`;
  }).join('');
}

// ============================================================
// Visit History Page (only MY visits)
// ============================================================
function renderVisitHistory() {
  const container = document.getElementById('visit-history-list');
  if (!container) return;

  if (!isLoggedIn) {
    container.innerHTML = `
      <div class="empty-state glass-card" style="display:flex; flex-direction:column; align-items:center;">
        <span class="material-icons-round" style="font-size: 3rem; color: var(--primary);">login</span>
        <p>ログインが必要です</p>
        <span class="text-muted-sm">来店履歴を表示するにはログインしてください</span>
        <button class="btn primary-btn btn-block" style="margin-top: 1rem; max-width: 280px;" onclick="location.hash='#/login'">
          <span class="material-icons-round">login</span>
          <span>ログインする</span>
        </button>
      </div>`;
    return;
  }

  const visitedShops = [];
  for (const shopId in userShopData) {
    const ud = userShopData[shopId];
    if (ud.visitCount > 0) {
      const shop = favorites.find(f => f.id === shopId) || (state.searchResults || []).find(s => s.id === shopId);
      visitedShops.push({
        id: shopId,
        name: shop ? shop.name : shopId,
        photo: shop ? shop.photo : '',
        genre: shop ? shop.genre : '',
        visitCount: ud.visitCount,
      });
    }
  }

  visitedShops.sort((a, b) => b.visitCount - a.visitCount);

  if (visitedShops.length === 0) {
    container.innerHTML = `
      <div class="empty-state glass-card">
        <span class="material-icons-round" style="font-size: 3rem; color: var(--primary);">history</span>
        <p>来店履歴はまだありません</p>
        <span class="text-muted-sm">お店の詳細ページから来店回数を記録しましょう</span>
      </div>`;
    return;
  }

  container.innerHTML = visitedShops.map(shop => {
    const imgUrl = shop.photo || 'https://via.placeholder.com/60x60.png?text=No+Image';
    return `
      <div class="history-card glass-card-subtle" onclick="location.hash='#/detail/${shop.id}'">
        <img src="${imgUrl}" alt="${shop.name}" class="history-card-img" />
        <div class="history-card-body">
          <h3 class="history-card-name">${shop.name}</h3>
          <div class="history-card-meta">
            <span class="visit-badge">${shop.visitCount}回来店</span>
            ${shop.genre ? `<span class="meta-badge" style="font-size: 0.7rem;">${shop.genre}</span>` : ''}
          </div>
        </div>
        <span class="material-icons-round" style="color: var(--text-muted);">chevron_right</span>
      </div>`;
  }).join('');
}

// ============================================================
// Search History Page
// ============================================================
function renderSearchHistory() {
  const container = document.getElementById('search-history-list');
  if (!container) return;

  if (!isLoggedIn) {
    container.innerHTML = `
      <div class="empty-state glass-card" style="display:flex; flex-direction:column; align-items:center;">
        <span class="material-icons-round" style="font-size: 3rem; color: var(--primary);">login</span>
        <p>ログインが必要です</p>
        <span class="text-muted-sm">検索履歴を表示するにはログインしてください</span>
        <button class="btn primary-btn btn-block" style="margin-top: 1rem; max-width: 280px;" onclick="location.hash='#/login'">
          <span class="material-icons-round">login</span>
          <span>ログインする</span>
        </button>
      </div>`;
    return;
  }

  // ローカルストレージから検索履歴を取得
  const history = getSearchHistory();

  if (!history || history.length === 0) {
    container.innerHTML = `
      <div class="empty-state glass-card">
        <span class="material-icons-round" style="font-size: 3rem; color: var(--primary);">search</span>
        <p>検索履歴はまだありません</p>
        <span class="text-muted-sm">店舗を検索するとここに表示されます</span>
      </div>`;
    return;
  }

  container.innerHTML = history.map(item => {
    const mode = item.mode === 'gps' ? '位置情報' : 'キーワード';
    const queryText = item.mode === 'gps' 
      ? `緯度:${state.lat?.toFixed(4)}, 経度:${state.lng?.toFixed(4)}`
      : `キーワード: ${item.keyword || 'なし'}`;
    
    const filters = [];
    if (item.genre) filters.push(`ジャンル:${item.genre}`);
    if (item.budget) filters.push(`予算:${item.budget}`);
    
    return `
      <div class="history-card glass-card-subtle search-history-item" 
           data-params='${JSON.stringify(item)}'>
        <div class="history-card-body">
          <div class="search-history-header">
            <span class="search-mode-badge">${mode}</span>
            <span class="search-date">${new Date(item.timestamp).toLocaleString('ja-JP')}</span>
          </div>
          <p class="search-query">${queryText}</p>
          ${filters.length > 0 ? `<div class="search-filters">${filters.map(f => `<span class="filter-tag">${f}</span>`).join('')}</div>` : ''}
          <div class="search-result-count">結果: ${item.resultCount}件</div>
        </div>
        <button class="btn-secondary search-again-btn" title="再検索">
          <span class="material-icons-round">search</span>
        </button>
      </div>`;
  }).join('');

  // 再検索ボタンのイベントリスナー
  container.querySelectorAll('.search-again-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const card = e.target.closest('.search-history-item');
      const params = JSON.parse(card.dataset.params);
      
      // 検索パラメータを復元して検索ページに遷移
      restoreSearchParams(params);
      location.hash = `#/`;
      // 少し待ってからスクロール
      setTimeout(() => {
        document.getElementById('search-section')?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    });
  });
}

function restoreSearchParams(params) {
  // 位置モードを復元
  state.locationMode = params.mode;
  document.querySelectorAll('.location-toggle-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === params.mode);
  });
  
  // GPSモードの場合
  if (params.mode === 'gps') {
    document.getElementById('gps-section').style.display = 'block';
    document.getElementById('station-section').style.display = 'none';
  } else {
    // 駅モードの場合
    document.getElementById('gps-section').style.display = 'none';
    document.getElementById('station-section').style.display = 'block';
    const stationInput = document.getElementById('station-input');
    if (stationInput) stationInput.value = params.keyword || '';
  }
  
  // ジャンル
  if (params.genre) {
    const genreSelect = document.getElementById('genre-select');
    if (genreSelect) {
      // テキストからvalueを探す
      for (let option of genreSelect.options) {
        if (option.text === params.genre) {
          genreSelect.value = option.value;
          break;
        }
      }
    }
  }
  
  // 予算
  if (params.budget) {
    const budgetMaxSelect = document.getElementById('budget-max-select');
    if (budgetMaxSelect) {
      for (let option of budgetMaxSelect.options) {
        if (option.text === params.budget) {
          budgetMaxSelect.value = option.value;
          break;
        }
      }
    }
  }
}

// ============================================================
// Scroll Animations
// ============================================================
function setupScrollAnimations() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('animate-in');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('.glass-card, .stat-card, .menu-item, .result-card').forEach(el => {
    observer.observe(el);
  });
}

// ============================================================
// Favorites Sort Event
// ============================================================
const favSortSelect = document.getElementById('fav-sort-select');
if (favSortSelect) {
  favSortSelect.addEventListener('change', () => {
    renderFavorites();
  });
}



// ============================================================
// Theme System
// ============================================================
const THEMES = [
  {
    id: 'red', name: 'レッド', icon: 'palette',
    colors: { bg: '#0a0a0f', bgCard: '#141420', bgElevated: '#1a1a2e', textMain: '#f0f0f5', textSecondary: '#a0a0b8', textMuted: '#6b6b80', border: 'rgba(255,255,255,0.08)', primary: '#ff416c', glassBase: 'rgba(20,20,32,0.7)', glassBorder: 'rgba(255,255,255,0.06)' }
  },
  {
    id: 'yellow', name: 'イエロー', icon: 'wb_sunny',
    colors: { bg: '#1a1708', bgCard: '#2e2a14', bgElevated: '#3d3618', textMain: '#f5f0d0', textSecondary: '#c8b870', textMuted: '#8a7a45', border: 'rgba(200,180,80,0.12)', primary: '#fdd835', glassBase: 'rgba(46,42,20,0.8)', glassBorder: 'rgba(200,180,80,0.1)' }
  },
  {
    id: 'blue', name: 'ブルー', icon: 'water_drop',
    colors: { bg: '#0d1b2a', bgCard: '#1b2838', bgElevated: '#243447', textMain: '#e0e8f0', textSecondary: '#8fa3b8', textMuted: '#5a7088', border: 'rgba(100,150,200,0.12)', primary: '#4fc3f7', glassBase: 'rgba(27,40,56,0.8)', glassBorder: 'rgba(100,150,200,0.1)' }
  },
  {
    id: 'green', name: 'グリーン', icon: 'grass',
    colors: { bg: '#0f1a0f', bgCard: '#1a2e1a', bgElevated: '#243824', textMain: '#e8f0e8', textSecondary: '#8fb88f', textMuted: '#5a7a5a', border: 'rgba(100,180,100,0.12)', primary: '#66bb6a', glassBase: 'rgba(26,46,26,0.8)', glassBorder: 'rgba(100,180,100,0.1)' }
  },
  {
    id: 'sunset', name: 'サンセット', icon: 'wb_twilight',
    colors: { bg: '#1a0f0a', bgCard: '#2e1a14', bgElevated: '#3d2418', textMain: '#f0e8e0', textSecondary: '#c8a088', textMuted: '#8a6a55', border: 'rgba(200,130,80,0.12)', primary: '#ff7043', glassBase: 'rgba(46,26,20,0.8)', glassBorder: 'rgba(200,130,80,0.1)' }
  },
  {
    id: 'royal', name: 'ロイヤル', icon: 'auto_awesome',
    colors: { bg: '#0f0a1a', bgCard: '#1a142e', bgElevated: '#24183d', textMain: '#e8e0f0', textSecondary: '#a088c8', textMuted: '#6a558a', border: 'rgba(130,80,200,0.12)', primary: '#ab47bc', glassBase: 'rgba(26,20,46,0.8)', glassBorder: 'rgba(130,80,200,0.1)' }
  },
];

function applyTheme(themeId) {
  // migrate old naming
  if (themeId === 'dark') themeId = 'red';
  const theme = THEMES.find(t => t.id === themeId);
  if (!theme) return;
  const c = theme.colors;
  const root = document.documentElement;
  root.style.setProperty('--bg', c.bg);
  root.style.setProperty('--bg-card', c.bgCard);
  root.style.setProperty('--bg-elevated', c.bgElevated);
  root.style.setProperty('--text-main', c.textMain);
  root.style.setProperty('--text-secondary', c.textSecondary);
  root.style.setProperty('--text-muted', c.textMuted);
  root.style.setProperty('--border', c.border);
  root.style.setProperty('--primary', c.primary);
  root.style.setProperty('--glass-base', c.glassBase);
  root.style.setProperty('--glass-border', c.glassBorder);
  // Update gradient
  root.style.setProperty('--gradient-primary', `linear-gradient(135deg, ${c.primary}, ${adjustColor(c.primary, 30)})`);
  localStorage.setItem('izakaya_theme', themeId);
}

function adjustColor(hex, amount) {
  const num = parseInt(hex.replace('#', ''), 16);
  const r = Math.min(255, Math.max(0, (num >> 16) + amount));
  const g = Math.min(255, Math.max(0, ((num >> 8) & 0xff) + amount));
  const b = Math.min(255, Math.max(0, (num & 0xff) + amount));
  return `#${(r << 16 | g << 8 | b).toString(16).padStart(6, '0')}`;
}

function renderThemeSettings() {
  const container = document.getElementById('theme-options');
  if (!container) return;
  let currentTheme = localStorage.getItem('izakaya_theme') || 'red';
  if (currentTheme === 'dark') currentTheme = 'red';

  container.innerHTML = THEMES.map(t => `
    <div class="theme-option ${t.id === currentTheme ? 'active' : ''}" data-theme="${t.id}">
      <div class="theme-preview" style="background: ${t.colors.bg}; border-color: ${t.colors.primary};">
        <div class="theme-preview-header" style="background: ${t.colors.bgCard};"></div>
        <div class="theme-preview-card" style="background: ${t.colors.bgElevated};"></div>
        <div class="theme-preview-accent" style="background: ${t.colors.primary};"></div>
      </div>
      <div class="theme-option-label">
        <span class="material-icons-round" style="color: ${t.colors.primary};">${t.icon}</span>
        <span>${t.name}</span>
      </div>
    </div>
  `).join('');

  container.querySelectorAll('.theme-option').forEach(opt => {
    opt.addEventListener('click', () => {
      const themeId = opt.dataset.theme;
      applyTheme(themeId);
      container.querySelectorAll('.theme-option').forEach(o => o.classList.remove('active'));
      opt.classList.add('active');
    });
  });
}

// Load saved theme on startup
(function loadSavedTheme() {
  const saved = localStorage.getItem('izakaya_theme');
  if (saved && saved !== 'dark') applyTheme(saved);
})();

// One-time cleanup of old data format
(function cleanupOldData() {
  if (localStorage.getItem('izakaya_data_migrated_v2')) return;
  const keysToRemove = Object.keys(localStorage).filter(k =>
    k.startsWith('izakaya_reviews') || 
    (k === 'izakaya_favorites') ||
    (k.startsWith('izakaya_favorites_') && k.includes('izakaya_favorites_anonymous')) ||
    (k.startsWith('izakaya_userdata_anonymous'))
  );
  keysToRemove.forEach(k => localStorage.removeItem(k));
  localStorage.setItem('izakaya_data_migrated_v2', '1');
})();

async function renderAdminStats() {
  const totalUsersVal = document.getElementById('total-users-val');
  const userEmailList = document.getElementById('user-email-list');
  
  if (!totalUsersVal || !userEmailList) return;

  try {
    const res = await fetch('/api/restaurants/admin/stats/');
    if (!res.ok) {
        if (res.status === 403) {
            userEmailList.innerHTML = `<div style="color: var(--danger)">アクセス権限がありません</div>`;
            return;
        }
        throw new Error('Stats fetch failed');
    }
    const data = await res.json();
    
    totalUsersVal.textContent = data.total_users;
    userEmailList.innerHTML = (data.user_emails || []).map(email => `<div style="border-bottom: 1px solid rgba(255,255,255,0.05); padding: 4px 0;">${email}</div>`).join('');
    
    drawAdminCharts(data);
  } catch (err) {
    console.error('Admin stats error:', err);
    userEmailList.innerHTML = `<div style="color: var(--danger)">通信エラーが発生しました</div>`;
  }
}

let budgetChartInstance = null;
let peopleChartInstance = null;

function drawAdminCharts(data) {
  const budgetCtx = document.getElementById('budgetChart');
  const peopleCtx = document.getElementById('peopleChart');
  if (!budgetCtx || !peopleCtx) return;

  const bCtx = budgetCtx.getContext('2d');
  const pCtx = peopleCtx.getContext('2d');

  // Budget Chart
  const budgetLabels = Object.keys(data.budget_stats || {});
  const budgetValues = Object.values(data.budget_stats || {});

  if (budgetChartInstance) budgetChartInstance.destroy();
  budgetChartInstance = new Chart(bCtx, {
    type: 'pie',
    data: {
      labels: budgetLabels,
      datasets: [{
        label: '検索数',
        data: budgetValues,
        backgroundColor: [
          '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40'
        ],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: '#333' } }
      }
    }
  });

  // People Chart
  const pStats = data.people_stats || {};
  const peopleLabels = Object.keys(pStats).sort((a,b) => parseInt(a)-parseInt(b)).map(k => `${k}人`);
  const peopleValues = Object.keys(pStats).sort((a,b) => parseInt(a)-parseInt(b)).map(k => pStats[k]);

  if (peopleChartInstance) peopleChartInstance.destroy();
  peopleChartInstance = new Chart(pCtx, {
    type: 'bar',
    data: {
      labels: peopleLabels,
      datasets: [{
        label: '検索数',
        data: peopleValues,
        backgroundColor: '#8e44ad',
        borderRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: { ticks: { color: '#333' } },
        y: { beginAtZero: true, ticks: { color: '#333', stepSize: 1 } }
      }
    }
  });
}

// ============================================================
// Start
// ============================================================
document.addEventListener('DOMContentLoaded', init);


// ==================== AI NEURAL NETWORK BACKGROUND ANIMATION ==================== //
let aiCanvasRunning = false;
function initAiNeuralCanvas() {
  const canvas = document.getElementById('ai-neural-canvas');
  if (!canvas || aiCanvasRunning) return;
  aiCanvasRunning = true;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  function resize() {
    canvas.width = canvas.parentElement ? canvas.parentElement.clientWidth : window.innerWidth;
    canvas.height = canvas.parentElement ? canvas.parentElement.clientHeight : 520;
  }
  resize();
  window.addEventListener('resize', resize);

  const numNodes = 36;
  const nodes = [];
  for (let i = 0; i < numNodes; i++) {
    nodes.push({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.7,
      vy: (Math.random() - 0.5) * 0.7,
      r: Math.random() * 2.2 + 1.2,
      alpha: Math.random() * 0.6 + 0.3
    });
  }

  function frame() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Neural connections
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 115) {
          const lineAlpha = (1 - dist / 115) * 0.38;
          ctx.beginPath();
          ctx.moveTo(nodes[i].x, nodes[i].y);
          ctx.lineTo(nodes[j].x, nodes[j].y);
          ctx.strokeStyle = `rgba(16, 185, 129, ${lineAlpha})`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    }

    // Glowing nodes
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      n.x += n.vx;
      n.y += n.vy;

      if (n.x < 0 || n.x > canvas.width) n.vx *= -1;
      if (n.y < 0 || n.y > canvas.height) n.vy *= -1;

      // Outer glow
      const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r * 3.5);
      g.addColorStop(0, `rgba(52, 211, 153, ${n.alpha})`);
      g.addColorStop(0.5, `rgba(99, 102, 241, ${n.alpha * 0.4})`);
      g.addColorStop(1, 'rgba(15, 23, 42, 0)');

      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r * 3.5, 0, Math.PI * 2);
      ctx.fillStyle = g;
      ctx.fill();

      // Node core
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fillStyle = '#6ee7b7';
      ctx.fill();
    }

    requestAnimationFrame(frame);
  }

  requestAnimationFrame(frame);
}

/**
 * OmniPoints - Centralized Multi-Firm Customer Reward Wallet
 * Frontend Application Controller
 */

// Application State
const state = {
  isLoggedIn: false,
  currentPhone: null,
  customer: null,
  summary: {
    total_active_points: 0,
    total_value_inr: 0,
    expiring_soon_points: 0,
    lifetime_earned: 0,
    lifetime_redeemed: 0,
    unopened_cards: 0
  },
  batches: [],
  firmBreakdowns: [],
  transactions: [],
  firms: [],
  scratchCards: [],
  businessLedger: null,
  otpSession: {
    phone: '',
    demoOtp: '',
    distinctNames: [],
    firmProfiles: [],
    defaultSelectedName: ''
  },
  activeTab: 'login',
  selectedFirm: null,
  activeRedemptionToken: null,
  activeMerchantRequest: null,
  tokenTimerInterval: null,
  pollInterval: null
};

// Initialize App
document.addEventListener('DOMContentLoaded', async () => {
  initServiceWorker();
  initAiNeuralCanvas();
  setupBottomNav();
  await loadFirms();

  // Check URL parameters for direct phone links, or saved login session
  const urlParams = new URLSearchParams(window.location.search);
  const paramPhone = urlParams.get('phone') || urlParams.get('customer_id');
  const savedPhone = localStorage.getItem('omnipoints_logged_in_phone');

  let initialPhone = null;
  if (paramPhone && paramPhone.replace(/[^0-9]/g, '').length >= 10) {
    initialPhone = paramPhone.replace(/[^0-9]/g, '');
  } else if (savedPhone && savedPhone.length >= 10) {
    initialPhone = savedPhone;
  }

  await populateCustomerDropdown();

  if (initialPhone) {
    await completeLogin(initialPhone, null, false);
  } else {
    showLoginInterface();
  }

  setupPollSync();
  LiveSync.init();

  if (urlParams.get('view') === 'id-card' && state.isLoggedIn) {
    setTimeout(() => openCustomerIdCard(), 500);
  } else if (urlParams.get('mode') === 'register') {
    setTimeout(() => openModal('customer-registration-modal'), 500);
  }
});

// ----------------- LOGIN / LANDING SCREEN CONTROLLER ----------------- //

function showLoginInterface() {
  state.isLoggedIn = false;
  state.currentPhone = null;
  localStorage.removeItem('omnipoints_logged_in_phone');

  switchTab('login', false);

  // Hide bottom navigation
  const nav = document.getElementById('app-bottom-nav');
  if (nav) nav.classList.add('hidden');

  // Mobile Header in Guest State
  const headerUser = document.getElementById('mobile-header-user');
  const headerGuest = document.getElementById('mobile-header-guest');
  const btnPass = document.getElementById('btn-mobile-pass');
  const btnLogout = document.getElementById('btn-mobile-logout');

  if (headerUser) {
    headerUser.classList.add('hidden');
    headerUser.classList.remove('flex');
  }
  if (headerGuest) {
    headerGuest.classList.remove('hidden');
    headerGuest.classList.add('flex');
  }
  const headerActions = document.getElementById('mobile-header-actions');
  if (headerActions) headerActions.classList.add('hidden');
  if (btnPass) btnPass.classList.add('hidden');
  if (btnLogout) btnLogout.classList.add('hidden');

  // Desktop Header Indicator
  const desktopLogout = document.getElementById('btn-desktop-logout');
  if (desktopLogout) {
    desktopLogout.textContent = '🔑 Sign In';
    desktopLogout.onclick = () => showLoginInterface();
  }

  const sel = document.getElementById('desktop-customer-select');
  if (sel) sel.value = '';

  // Reset landing steps
  const stepPhone = document.getElementById('landing-login-step-phone');
  const stepOtp = document.getElementById('landing-login-step-otp');
  if (stepPhone) stepPhone.classList.remove('hidden');
  if (stepOtp) stepOtp.classList.add('hidden');
}

async function completeLogin(phone, customerObj = null, doBroadcast = true) {
  state.isLoggedIn = true;
  state.currentPhone = phone;
  localStorage.setItem('omnipoints_logged_in_phone', phone);

  // Show bottom navigation
  const nav = document.getElementById('app-bottom-nav');
  if (nav) nav.classList.remove('hidden');

  // Mobile Header in User State
  const headerUser = document.getElementById('mobile-header-user');
  const headerGuest = document.getElementById('mobile-header-guest');
  const btnPass = document.getElementById('btn-mobile-pass');
  const btnLogout = document.getElementById('btn-mobile-logout');

  if (headerUser) {
    headerUser.classList.remove('hidden');
    headerUser.classList.add('flex');
  }
  if (headerGuest) {
    headerGuest.classList.add('hidden');
    headerGuest.classList.remove('flex');
  }
  const headerActions = document.getElementById('mobile-header-actions');
  if (headerActions) headerActions.classList.remove('hidden');
  if (btnPass) btnPass.classList.remove('hidden');
  const btnSettings = document.getElementById('btn-mobile-settings');
  if (btnSettings) {
    btnSettings.classList.remove('hidden');
    btnSettings.innerHTML = `<span class="text-xs">⚙️</span><span>Settings</span>`;
    btnSettings.onclick = () => openSettingsModal();
  }

  const desktopSettings = document.getElementById('btn-desktop-settings');
  if (desktopSettings) {
    desktopSettings.innerHTML = `<span class="text-xs">⚙️</span> Settings`;
    desktopSettings.onclick = () => openSettingsModal();
  }

  // Load customer data, ledger, batches
  await switchCustomer(phone, doBroadcast);

  // Switch to Home Page
  switchTab('home', doBroadcast);

  // Check for any pending merchant redemption requests
  await checkPendingMerchantRequest(phone);

  const sel = document.getElementById('desktop-customer-select');
  if (sel) sel.value = phone;

  triggerConfetti();
  showToast(`🎉 സ്വാഗതം! ${state.customer ? state.customer.name : 'Customer'} വിജയകരമായി പ്രവേശിച്ചു.`);
}

function logoutCustomer() {
  showLoginInterface();
  showToast('🚪 വിജയകരമായി ലോഗൗട്ട് ചെയ്തു. (Logged out)');
  if (typeof LiveSync !== 'undefined' && LiveSync.broadcast) {
    LiveSync.broadcast({ type: 'LOGOUT' });
  }
}


// ==================== NEUMORPHIC BADGE ONBOARDING & LOGIN SLIDER ==================== //
let currentLoginSlide = 1;

function setLoginSlide(slideNum) {
  currentLoginSlide = slideNum;
  const s1 = document.getElementById('login-slide-1');
  const s2 = document.getElementById('login-slide-2');
  const s3 = document.getElementById('login-slide-3');
  const d1 = document.getElementById('login-dot-1');
  const d2 = document.getElementById('login-dot-2');
  const d3 = document.getElementById('login-dot-3');
  const skipBtn = document.getElementById('btn-login-skip');
  const arrowBtn = document.getElementById('btn-login-arrow-action');

  if (s1) s1.classList.toggle('hidden', slideNum !== 1);
  if (s2) s2.classList.toggle('hidden', slideNum !== 2);
  if (s3) s3.classList.toggle('hidden', slideNum !== 3);

  const dots = [d1, d2, d3];
  dots.forEach((dot, idx) => {
    if (dot) {
      if (idx + 1 === slideNum) {
        dot.className = 'w-4 h-1.5 rounded-full bg-amber-500 shadow-xs transition-all';
      } else {
        dot.className = 'w-1.5 h-1.5 rounded-full bg-slate-300 transition-all';
      }
    }
  });

  if (skipBtn) {
    if (slideNum === 1) skipBtn.innerText = 'Skip';
    else if (slideNum === 2) skipBtn.innerText = '← Back';
    else if (slideNum === 3) skipBtn.innerText = '← Phone';
  }

  if (arrowBtn) {
    if (slideNum === 3) {
      arrowBtn.innerHTML = '<span>✓</span>';
      arrowBtn.classList.add('neu-btn-primary');
    } else {
      arrowBtn.innerHTML = '<span>&rarr;</span>';
      arrowBtn.classList.remove('neu-btn-primary');
    }
  }
}

function loginSlideSkip() {
  if (currentLoginSlide === 1) {
    setLoginSlide(2);
  } else if (currentLoginSlide === 2) {
    setLoginSlide(1);
  } else if (currentLoginSlide === 3) {
    setLoginSlide(2);
  }
}

async function onLoginArrowClick() {
  if (currentLoginSlide === 1) {
    setLoginSlide(2);
  } else if (currentLoginSlide === 2) {
    const phoneInput = document.getElementById('landing-phone-input');
    let phoneVal = phoneInput ? phoneInput.value.trim() : '';
    if (!phoneVal) {
      phoneVal = '9656360650'; // Midhilaj PS default
      if (phoneInput) phoneInput.value = phoneVal;
    }
    await requestLandingOtpFlow();
  } else if (currentLoginSlide === 3) {
    await verifyLandingOtpFlow();
  }
}

function selectLandingCustomer(phone) {
  const input = document.getElementById('landing-phone-input');
  if (input) input.value = phone;
  requestLandingOtpFlow();
}

async function requestLandingOtpFlow() {
  const phoneInput = document.getElementById('landing-phone-input');
  let phone = phoneInput ? phoneInput.value.trim().replace(/[^0-9]/g, '') : '';
  if (phone.length === 12 && phone.startsWith('91')) phone = phone.slice(2);
  else if (phone.length === 11 && phone.startsWith('0')) phone = phone.slice(1);
  else if (phone.length > 10) phone = phone.slice(-10);

  if (!phone || phone.length < 10) {
    alert('ദയവായി 10 അക്ക മൊബൈൽ നമ്പർ നൽകുക (Please enter valid 10-digit mobile number)');
    return;
  }

  showLoadingSpinner(true);
  try {
    const res = await fetch('/api/auth/request-otp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone })
    });
    const data = await res.json();
    if (!data.success) {
      alert(data.message || 'Failed to request OTP');
      return;
    }

    state.otpSession = {
      phone,
      demoOtp: data.demo_otp || '123456',
      isNew: data.is_new,
      isProfileIncomplete: data.is_profile_incomplete,
      distinctNames: data.distinct_names || [],
      firmProfiles: data.firm_profiles || [],
      existingCustomer: data.existing_customer,
      defaultSelectedName: data.default_selected_name || ''
    };

    // Transition to Step 2 inside Landing view
    document.getElementById('landing-login-step-phone').classList.add('hidden');
    document.getElementById('landing-login-step-otp').classList.remove('hidden');

    document.getElementById('landing-otp-target-phone').innerText = `+91 ${phone}`;
    document.getElementById('landing-demo-otp-badge').innerText = data.demo_otp;
    if (typeof setLoginSlide === 'function') setLoginSlide(3);

    // Render Name conflict / merge resolution if divergence
    const conflictBox = document.getElementById('landing-name-conflict-box');
    const radioContainer = document.getElementById('landing-firm-names-radio-container');
    const customInput = document.getElementById('landing-custom-name-input');
    if (customInput) customInput.value = '';

    if (data.has_name_divergence && data.distinct_names && data.distinct_names.length > 1) {
      conflictBox.classList.remove('hidden');
      radioContainer.innerHTML = data.distinct_names.map((name, idx) => `
        <label class="flex items-center gap-2 p-2 rounded-xl bg-slate-950 border border-slate-800 hover:border-indigo-500 cursor-pointer text-xs">
          <input type="radio" name="landing_selected_name" value="${name}" ${idx === 0 ? 'checked' : ''} class="text-indigo-600 focus:ring-indigo-500">
          <span class="font-bold text-white">${name}</span>
        </label>
      `).join('');
    } else {
      conflictBox.classList.add('hidden');
    }

    // Auto-fill OTP for ultra-smooth 1-click UX
    autoFillLandingDemoOtp();
  } catch (err) {
    console.error('Request OTP error:', err);
    alert('Error connecting to authentication server');
  } finally {
    showLoadingSpinner(false);
  }
}

function autoFillLandingDemoOtp() {
  const otpInput = document.getElementById('landing-otp-input');
  if (otpInput && state.otpSession && state.otpSession.demoOtp) {
    otpInput.value = state.otpSession.demoOtp;
  }
}

function backToLandingPhoneStep() {
  document.getElementById('landing-login-step-otp').classList.add('hidden');
  document.getElementById('landing-login-step-phone').classList.remove('hidden');
}

async function verifyLandingOtpFlow() {
  const otp = document.getElementById('landing-otp-input').value.trim();
  const phone = state.otpSession.phone;

  if (!otp || otp.length < 6) {
    alert('ദയവായി 6 അക്ക ഒടിപി നൽകുക (Please enter 6-digit OTP)');
    return;
  }

  let selectedName = '';
  const checkedRadio = document.querySelector('input[name="landing_selected_name"]:checked');
  if (checkedRadio) selectedName = checkedRadio.value;
  const customName = document.getElementById('landing-custom-name-input')?.value.trim();
  const finalChosenName = customName || selectedName || (state.otpSession && state.otpSession.defaultSelectedName) || '';

  showLoadingSpinner(true);
  try {
    const res = await fetch('/api/auth/verify-otp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        phone: phone,
        otp: otp,
        selected_name: finalChosenName,
        custom_name: customName
      })
    });

    const data = await res.json();
    if (!data.success) {
      alert(data.message || 'OTP verification failed');
      return;
    }

    state.customer = data.customer;
    state.summary = data.summary;
    state.businessLedger = data.business_ledger;

    // Check if new customer or profile incomplete (address / pincode missing)
    if (data.is_profile_incomplete || state.otpSession.isNew || !data.customer.address || !data.customer.pincode) {
      state.pendingProfilePhone = phone;
      const nameInput = document.getElementById('profile-name-input');
      const addrInput = document.getElementById('profile-address-input');
      const cityInput = document.getElementById('profile-city-input');
      const pinInput = document.getElementById('profile-pincode-input');

      if (nameInput) nameInput.value = data.customer.name || finalChosenName || '';
      if (addrInput) addrInput.value = data.customer.address || '';
      if (cityInput) cityInput.value = data.customer.city || '';
      if (pinInput) pinInput.value = data.customer.pincode || '';

      openModal('profile-setup-modal');
    } else {
      await completeLogin(phone, data.customer, true);
    }
  } catch (err) {
    console.error('Landing OTP verify error:', err);
    alert('Error verifying OTP: ' + err.message);
  } finally {
    showLoadingSpinner(false);
  }
}

async function saveCustomerProfile() {
  const phone = state.pendingProfilePhone || state.currentPhone || (state.otpSession && state.otpSession.phone);
  const name = document.getElementById('profile-name-input')?.value.trim();
  const address = document.getElementById('profile-address-input')?.value.trim();
  const city = document.getElementById('profile-city-input')?.value.trim();
  const pincode = document.getElementById('profile-pincode-input')?.value.trim();

  if (!name) {
    alert('ദയവായി പേര് നൽകുക (Please enter Full Name)');
    return;
  }
  if (!address) {
    alert('ദയവായി മേൽവിലാസം നൽകുക (Please enter Address)');
    return;
  }
  if (!pincode || pincode.length < 6) {
    alert('ദയവായി 6 അക്ക പിൻകോഡ് നൽകുക (Please enter 6-digit PIN Code)');
    return;
  }

  showLoadingSpinner(true);
  try {
    const res = await fetch('/api/customer/update-profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, name, address, city, pincode })
    });
    const data = await res.json();
    if (data.success && data.customer) {
      state.customer = data.customer;
      closeModal('profile-setup-modal');
      await completeLogin(phone, data.customer, true);
      showToast('🎉 പ്രൊഫൈൽ വിജയകരമായി അപ്‌ഡേറ്റ് ചെയ്തു!');
    } else {
      alert(data.message || 'Failed to update profile');
    }
  } catch (e) {
    console.error(e);
    alert('Error saving profile');
  } finally {
    showLoadingSpinner(false);
  }
}

// Setup real-time polling to keep balance synced with cashier deductions
function setupPollSync() {
  if (state.pollInterval) clearInterval(state.pollInterval);
  state.pollInterval = setInterval(async () => {
    if (state.currentPhone && state.isLoggedIn) {
      await refreshWalletSilent();
      await checkPendingMerchantRequest(state.currentPhone);
    }
  }, 1500);
}

// ----------------- MERCHANT REDEMPTION APPROVAL CONTROLLER ----------------- //

async function checkPendingMerchantRequest(phone) {
  const cleanPhone = (phone || state.currentPhone || '').replace(/[^0-9]/g, '');
  if (!cleanPhone) return;
  try {
    const res = await fetch(`/api/redemption/pending-merchant-request?phone=${cleanPhone}`);
    const data = await res.json();
    if (data.success && data.has_pending && data.request) {
      state.activeMerchantRequest = data.request;
      const req = data.request;

      const fn = document.getElementById('mreq-firm-name');
      const inv = document.getElementById('mreq-invoice-no');
      const pts = document.getElementById('mreq-points-val');
      const banAmt = document.getElementById('banner-mreq-amount');
      const currBal = document.getElementById('mreq-current-bal');
      const aftBal = document.getElementById('mreq-after-bal');

      if (fn) fn.textContent = req.firm_name || 'EEYES Pro Retail & Supermarket';
      if (inv) inv.textContent = `#${req.invoice_no}`;
      if (pts) pts.textContent = `₹${parseFloat(req.points).toFixed(2)}`;
      if (banAmt) banAmt.textContent = `₹${parseFloat(req.points).toFixed(2)}`;

      const current = (state.summary && state.summary.total_active_points) || 0;
      const after = Math.max(0, current - req.points);
      if (currBal) currBal.textContent = `₹${current.toFixed(2)}`;
      if (aftBal) aftBal.textContent = `₹${after.toFixed(2)}`;

      const banner = document.getElementById('merchant-approval-urgent-banner');
      if (banner) banner.classList.remove('hidden');

      openModal('merchant-approval-modal');
    } else {
      state.activeMerchantRequest = null;
      const banner = document.getElementById('merchant-approval-urgent-banner');
      if (banner) banner.classList.add('hidden');
    }
  } catch (err) {
    console.warn('Check pending merchant request note:', err);
  }
}

async function acceptMerchantRedemptionRequest() {
  if (!state.activeMerchantRequest) {
    closeModal('merchant-approval-modal');
    return;
  }
  const reqId = state.activeMerchantRequest.id;
  const pts = state.activeMerchantRequest.points;

  try {
    showLoadingSpinner(true);
    const res = await fetch('/api/redemption/customer-response', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_id: reqId,
        action: 'ACCEPT'
      })
    });
    const data = await res.json();
    showLoadingSpinner(false);

    if (data.success) {
      closeModal('merchant-approval-modal');
      const banner = document.getElementById('merchant-approval-urgent-banner');
      if (banner) banner.classList.add('hidden');

      triggerConfetti();
      showToast(`🎉 വിജയകരമായി അക്സെപ്റ്റ് ചെയ്തു! ഇൻവോയ്സിൽ ₹${parseFloat(pts).toFixed(2)} റിവാർഡ് കുറച്ചു.`);
      await refreshWalletSilent();
    } else {
      alert(data.message || 'Failed to accept request');
    }
  } catch (e) {
    showLoadingSpinner(false);
    console.error('Accept error:', e);
  }
}

async function declineMerchantRedemptionRequest() {
  if (!state.activeMerchantRequest) {
    closeModal('merchant-approval-modal');
    return;
  }
  const reqId = state.activeMerchantRequest.id;

  try {
    showLoadingSpinner(true);
    const res = await fetch('/api/redemption/customer-response', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_id: reqId,
        action: 'DECLINE'
      })
    });
    showLoadingSpinner(false);
    closeModal('merchant-approval-modal');
    const banner = document.getElementById('merchant-approval-urgent-banner');
    if (banner) banner.classList.add('hidden');
    showToast('❌ റിഡംപ്ഷൻ റിക്വസ്റ്റ് നിരസിച്ചു (Declined).');
  } catch (e) {
    showLoadingSpinner(false);
    closeModal('merchant-approval-modal');
  }
}

// ----------------- DATA FETCHING ----------------- //

async function loadFirms() {
  try {
    const res = await fetch('/api/firms');
    const data = await res.json();
    if (data.success) {
      state.firms = data.firms;
      renderFirmsList();
      if (typeof renderHomeStoresPreview === "function") renderHomeStoresPreview();
      populateRedeemFirmSelect();
    }
  } catch (err) {
    console.error('Failed to load firms:', err);
  }
}

async function populateCustomerDropdown() {
  try {
    const res = await fetch('/api/customers');
    const data = await res.json();
    if (data.success && data.customers) {
      const sel = document.getElementById('desktop-customer-select');
      if (!sel) return;
      sel.innerHTML = data.customers.map(c => {
        const isEeyes = c.es_invoices_count > 0 || ['9822012345', '9890123456', '9765432109', '9656360650'].includes(c.phone);
        const icon = isEeyes ? '🏪' : '👤';
        const tag = isEeyes ? ' [EEYES PRO]' : '';
        return `<option value="${c.phone}" ${c.phone === state.currentPhone ? 'selected' : ''}>
          ${icon} ${c.name} (${c.phone})${tag}
        </option>`;
      }).join('');
    }
  } catch (e) {
    console.warn('Customer dropdown load error:', e);
  }
}

async function syncEeyesPro() {
  const btn = document.getElementById('btn-sync-eeyes');
  const mobBtn = document.getElementById('mobile-eeyes-sync-btn');
  if (btn) btn.innerHTML = `<span>⏳</span><span>Syncing...</span>`;
  if (mobBtn) mobBtn.classList.add('animate-spin');

  try {
    const res = await fetch('/api/v1/erp/sync-eeyes-pro', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      await populateCustomerDropdown();
      await switchCustomer(state.currentPhone, false);
      triggerConfetti();
      showToast(`✨ ${data.message}`);
    } else {
      alert('Sync failed: ' + (data.message || 'Unknown error'));
    }
  } catch (e) {
    console.error('EeyesPro sync error:', e);
    showToast('Failed to connect to EEYES PRO Desktop at localhost:3000', 'error');
  } finally {
    if (btn) btn.innerHTML = `<span>🔄</span><span>Sync EEYES Pro</span>`;
    if (mobBtn) mobBtn.classList.remove('animate-spin');
  }
}

async function switchCustomer(phone, broadcast = true) {
  state.currentPhone = phone;
  const sel = document.getElementById('desktop-customer-select');
  if (sel && sel.value !== phone) {
    sel.value = phone;
  }
  if (broadcast && typeof LiveSync !== 'undefined' && LiveSync.broadcast) {
    LiveSync.broadcast({ type: 'CUSTOMER_SYNC', phone: phone });
  }
  try {
    showLoadingSpinner(true);
    const res = await fetch(`/api/wallet/${phone}`);
    const data = await res.json();
    
    if (data.success) {
      state.customer = data.customer || {};
      state.summary = data.summary || {};
      state.businessLedger = data.business_ledger || null;
      state.batches = data.batches || [];
      state.firmBreakdowns = data.firm_breakdowns || data.firmBreakdowns || [];
      state.transactions = data.transactions || [];
      state.scratchCards = data.scratch_cards || data.scratchCards || [];

      updateUI();
    } else {
      // If customer doesn't exist, login / register them
      await loginCustomer(phone);
    }
  } catch (err) {
    console.error('Error switching customer:', err);
  } finally {
    showLoadingSpinner(false);
  }
}

async function refreshWalletSilent() {
  try {
    const res = await fetch(`/api/wallet/${state.currentPhone}`);
    const data = await res.json();
    if (data.success) {
      const prevPoints = state.summary.total_active_points;
      state.summary = data.summary || {};
      state.businessLedger = data.business_ledger || state.businessLedger;
      state.batches = data.batches || [];
      state.firmBreakdowns = data.firm_breakdowns || data.firmBreakdowns || [];
      state.transactions = data.transactions || [];
      state.scratchCards = data.scratch_cards || data.scratchCards || [];

      // Update counters without re-rendering everything
      updateWalletBalanceDisplays();
      renderBusinessLedger();

      // Trigger confetti if points increased
      if (data.summary.total_active_points > prevPoints && prevPoints > 0) {
        showToast(`🎉 Points Updated! +₹${(data.summary.total_active_points - prevPoints).toFixed(2)} added!`);
        triggerConfetti();
        renderBatchesList();
      }
    }
  } catch (e) {
    // silent catch
  }
}

async function loginCustomer(phone, name = '') {
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, name })
    });
    const data = await res.json();
    if (data.success) {
      state.customer = data.customer;
      state.summary = data.summary;
      await switchCustomer(phone);
      closeModal('login-modal');
      showToast(`Welcome, ${state.customer.name}!`);
    } else {
      alert(data.message || 'Login failed');
    }
  } catch (err) {
    alert('Network error connecting to OmniPoints ERP server');
  }
}

// ----------------- UI UPDATES ----------------- //

function updateUI() {
  // Update Header & Customer Info
  document.getElementById('header-user-name').innerText = state.customer.name;
  document.getElementById('header-user-phone').innerText = `+91 ${state.customer.phone}`;
  document.getElementById('header-user-avatar').innerText = state.customer.name.charAt(0);
  document.getElementById('header-user-avatar').style.backgroundColor = state.customer.avatar_color || '#4F46E5';
  document.getElementById('header-vip-badge').innerText = state.customer.vip_tier || 'Silver';

  // Profile tab info
  document.getElementById('profile-name').innerText = state.customer.name;
  document.getElementById('profile-phone').innerText = `+91 ${state.customer.phone}`;
  document.getElementById('profile-tier').innerText = state.customer.vip_tier || 'Silver Member';
  document.getElementById('profile-earned-val').innerText = `₹${state.summary.lifetime_earned.toFixed(2)}`;
  document.getElementById('profile-redeemed-val').innerText = `₹${state.summary.lifetime_redeemed.toFixed(2)}`;

  updateWalletBalanceDisplays();
  renderExpiringAlert();
  renderBusinessLedger();
  renderFirmsBreakdownCards();
  renderBatchesList();
  renderScratchCardPreview();
  renderTransactionsList();
  renderHomeStoresPreview();
}

function updateWalletBalanceDisplays() {
  const pointsVal = state.summary.total_active_points;
  const inrVal = state.summary.total_value_inr;

  document.querySelectorAll('.wallet-points-display').forEach(el => {
    el.innerText = `${pointsVal.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  });

  document.querySelectorAll('.wallet-inr-display').forEach(el => {
    el.innerText = `₹${inrVal.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  });

  const expiringEl = document.getElementById('hero-expiring-soon');
  if (expiringEl) {
    if (state.summary.expiring_soon_points > 0) {
      expiringEl.innerHTML = `⚠️ ₹${state.summary.expiring_soon_points.toFixed(2)} expiring in 48h!`;
      expiringEl.classList.remove('hidden');
    } else {
      expiringEl.classList.add('hidden');
    }
  }

  // Scratch card count badge
  const scratchBadge = document.getElementById('scratch-card-count-badge');
  if (scratchBadge) {
    scratchBadge.innerText = `${state.summary.unopened_cards} UNOPENED`;
    scratchBadge.style.display = state.summary.unopened_cards > 0 ? 'inline-flex' : 'none';
  }
}

function renderExpiringAlert() {
  const container = document.getElementById('urgent-alert-container');
  if (!container) return;

  const expiringBatches = state.batches.filter(b => b.is_expiring_soon);
  if (expiringBatches.length > 0) {
    const b = expiringBatches[0];
    container.innerHTML = `
      <div class="glass-card batch-expiring-alert p-3 mb-4 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-full bg-rose-500/20 text-rose-400 flex items-center justify-center font-bold text-lg">
            ⏳
          </div>
          <div>
            <div class="text-xs font-bold text-rose-400 tracking-wide uppercase">Points Expiring Soon!</div>
            <div class="text-sm font-extrabold text-white">₹${b.points_remaining.toFixed(2)} at ${b.firm_name}</div>
            <div class="text-[11px] text-slate-400">Min bill required: ₹${b.required_bill_to_redeem.toFixed(2)} • Expires in ${b.days_left} days</div>
          </div>
        </div>
        <button onclick="openRedeemModalForFirm('${b.firm_id}', ${b.points_remaining})" class="bg-rose-500 hover:bg-rose-600 text-white text-xs font-bold px-3 py-2 rounded-xl transition">
          Redeem
        </button>
      </div>
    `;
    container.classList.remove('hidden');
  } else {
    container.classList.add('hidden');
  }
}

// Render Categorized Firm Balance Cards on Home View
function renderFirmsBreakdownCards() {
  const container = document.getElementById('firm-breakdown-carousel');
  if (!container) return;

  if (state.firmBreakdowns.length === 0) {
    container.innerHTML = `<div class="text-xs text-slate-500 p-4">No firm balances yet.</div>`;
    return;
  }

  container.innerHTML = state.firmBreakdowns.map(fb => {
    const hasPoints = fb.total_firm_points > 0;
    return `
      <div onclick="openFirmDetailModal('${fb.firm_id}')" class="min-w-[170px] glass-card p-3 cursor-pointer hover:border-indigo-500/50 transition-all relative overflow-hidden flex flex-col justify-between" style="border-top: 3px solid ${fb.theme_color || '#4F46E5'}">
        ${fb.is_es_pro ? '<span class="absolute top-2 right-2 text-[9px] bg-emerald-500/20 text-emerald-400 font-bold px-1.5 py-0.5 rounded">ES PRO</span>' : ''}
        <div>
          <div class="text-[11px] text-slate-400 font-medium truncate">${fb.firm_category}</div>
          <div class="text-xs font-bold text-slate-100 truncate mt-0.5">${fb.firm_name}</div>
        </div>
        <div class="mt-3">
          <div class="text-[10px] text-slate-400">Firm Balance</div>
          <div class="text-base font-extrabold ${hasPoints ? 'text-emerald-400' : 'text-slate-500'}">
            ₹${fb.total_firm_points.toFixed(2)}
          </div>
          <div class="text-[10px] text-indigo-400 flex items-center gap-1 mt-1 font-semibold">
            ${fb.batch_count} Active Batch${fb.batch_count === 1 ? '' : 'es'} &rarr;
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// Render Batches List
function renderBatchesList() {
  const container = document.getElementById('all-batches-list');
  if (!container) return;

  if (state.batches.length === 0) {
    container.innerHTML = `
      <div class="text-center py-8 glass-card p-4">
        <div class="text-3xl mb-2">🎁</div>
        <div class="text-sm font-semibold text-slate-300">No Active Batches</div>
        <div class="text-xs text-slate-500 mt-1">Make purchases at ES Supermarket or partner firms to earn profit-share cashback!</div>
      </div>
    `;
    return;
  }

  container.innerHTML = state.batches.map(b => {
    const isLocked = b.is_locked_next_day;
    const isUrgent = b.is_expiring_soon;

    return `
      <div class="glass-card p-3 mb-3 border transition-all ${isUrgent ? 'border-rose-500/40 bg-rose-950/10' : 'border-slate-800'}">
        <div class="flex items-start justify-between">
          <div class="flex items-center gap-2">
            <span class="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold text-white" style="background-color: ${b.firm_theme_color || '#4F46E5'}">
              ${b.firm_name.charAt(0)}
            </span>
            <div>
              <div class="text-xs font-bold text-white flex items-center gap-1.5">
                <span>${b.firm_name}</span>
                ${b.firm_badge ? `<span class="text-[9px] px-1 py-0.2 rounded bg-slate-800 text-slate-300 font-normal">${b.firm_badge}</span>` : ''}
              </div>
              <div class="text-[10px] text-slate-400">Invoice: #${b.invoice_no} • Earned: ${b.earned_date.split(' ')[0]}</div>
            </div>
          </div>
          <div class="text-right">
            <div class="text-sm font-black text-emerald-400">₹${b.points_remaining.toFixed(2)}</div>
            <div class="text-[10px] text-slate-400 font-mono">(${b.points_remaining} Pts)</div>
          </div>
        </div>

        <!-- Rule & Expiry Info -->
        <div class="mt-2.5 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px]">
          <div class="flex items-center gap-1 text-amber-400">
            <span>🏷️ Min Purchase:</span>
            <span class="font-bold text-white">₹${b.required_bill_to_redeem.toFixed(2)}</span>
            ${b.min_purchase_multiplier > 1 ? `<span class="text-[9px] text-indigo-400 font-semibold">(${b.min_purchase_multiplier}x Rule)</span>` : ''}
          </div>
          <div>
            ${isLocked ? 
              `<span class="timer-pill text-amber-300 bg-amber-500/10">🔒 Matures Tomorrow</span>` :
              `<span class="timer-pill ${isUrgent ? 'text-rose-400 bg-rose-500/10 font-bold' : 'text-slate-300'}">⏳ ${b.days_left}d left</span>`
            }
          </div>
        </div>

        <div class="mt-2.5 pt-2 border-t border-slate-800/80 flex items-center justify-between">
          <span class="text-[10px] text-slate-500">Originally ₹${b.points_earned.toFixed(2)} on bill ₹${b.bill_amount.toFixed(2)}</span>
          <div class="flex items-center gap-1.5">
            <button onclick="claimBatchRedemptionNow('${b.id}', '${b.firm_id}', ${b.points_remaining}, '${b.invoice_no}', '${(b.firm_name || 'EEYES Pro').replace(/'/g, "\\'")}')" class="px-2.5 py-1 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-extrabold text-[11px] rounded-lg shadow-sm transition flex items-center gap-1 cursor-pointer">
              <span>⚡</span>
              <span>Redeem Now (റെഡീം നൗ)</span>
            </button>
            <button onclick="openRedeemModalForFirm('${b.firm_id}', ${b.points_remaining})" class="text-[11px] font-semibold text-indigo-400 hover:text-indigo-300 py-1 px-2 rounded bg-indigo-500/10 hover:bg-indigo-500/20 transition">
              QR &rarr;
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// Render Participating Firms Tab
function renderFirmsList(category = 'ALL') {
  filterFirmsByCategory(category);
}

function filterFirmsByCategory(category = 'ALL', btn = null) {
  if (btn) {
    document.querySelectorAll('.firms-filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  } else {
    document.querySelectorAll('.firms-filter-btn').forEach(b => {
      const bCat = b.getAttribute('data-cat') || '';
      if (bCat === category || (category === 'ALL' && bCat === 'ALL')) {
        b.classList.add('active');
      } else {
        b.classList.remove('active');
      }
    });
  }

  searchFirms();
}

async function searchFirms() {
  if (!state.firms || state.firms.length === 0) {
    await loadFirms();
  }
  const query = (document.getElementById('firm-search-input')?.value || '').trim().toLowerCase();
  const activeBtn = document.querySelector('.firms-filter-btn.active');
  const cat = activeBtn ? (activeBtn.getAttribute('data-cat') || 'ALL') : 'ALL';

  let list = state.firms || [];
  if (cat !== 'ALL') {
    list = list.filter(f => (f.category || '').toUpperCase().includes(cat) || (cat === 'SUPERMARKET' && (f.name || '').toUpperCase().includes('SUPERMARKET')));
  }

  if (query) {
    list = list.filter(f => 
      (f.name || '').toLowerCase().includes(query) ||
      (f.category || '').toLowerCase().includes(query) ||
      (f.address || '').toLowerCase().includes(query) ||
      (f.tagline || '').toLowerCase().includes(query)
    );
  }

  renderFirmsCustomList(list);
}

function renderFirmsCustomList(list) {
  const container = document.getElementById('firms-full-list');
  if (!container) return;

  if (!list || list.length === 0) {
    container.innerHTML = `
      <div class="p-6 text-center text-slate-400 glass-card rounded-2xl">
        <div class="text-3xl mb-2">🔍</div>
        <div class="text-xs font-bold text-white">സ്റ്റോറുകൾ കണ്ടെത്തിയില്ല</div>
        <div class="text-[10px] mt-1 text-slate-400">മറ്റൊരു കാറ്റഗറിയോ പേരോ നൽകി വീണ്ടും തിരയുക</div>
      </div>
    `;
    return;
  }

  container.innerHTML = list.map(f => {
    let firmPoints = 0;
    if (state.batches && state.batches.length > 0) {
      firmPoints = state.batches
        .filter(b => b.firm_id === f.id && b.points_remaining > 0)
        .reduce((sum, b) => sum + parseFloat(b.points_remaining || 0), 0);
    }

    const icon = f.category_icon === 'fuel' ? '⛽' : (f.category_icon === 'coffee' ? '☕' : (f.category_icon === 'shopping-basket' ? '🧺' : '🛒'));

    return `
      <div class="glass-card p-4 mb-3 rounded-2xl border border-slate-700/70 hover:border-emerald-500/50 transition-all shadow-lg">
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-2xl flex items-center justify-center text-xl font-black text-white shadow-md border border-white/10" style="background-color: ${f.theme_color}">
            ${icon}
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between mb-0.5">
              <span class="text-[10px] font-extrabold uppercase tracking-wider text-emerald-400">${f.category}</span>
              ${f.is_es_pro ? '<span class="px-2 py-0.5 bg-emerald-500/20 text-emerald-400 rounded-full text-[9px] font-black border border-emerald-500/30">EEYES PRO</span>' : ''}
            </div>
            <div class="text-sm font-extrabold text-white truncate">${f.name}</div>
            <div class="text-[11px] text-slate-400 truncate">${f.address || f.tagline}</div>
          </div>
        </div>

        <!-- Store Rule -->
        <div class="mt-2.5 p-2 rounded-xl bg-slate-900/90 border border-slate-800 text-[11px] text-slate-300 flex items-center gap-2">
          <span>📜</span>
          <span class="truncate"><strong>റൂൾ:</strong> ${f.rule_summary || '10x പർച്ചേസ് റൂൾ • 7 ദിവസത്തെ വാലിഡിറ്റി'}</span>
        </div>

        <!-- Customer Points in this firm & Batches Button -->
        <div class="mt-3 flex items-center justify-between gap-2">
          <div class="text-[11px]">
            <span class="text-slate-400">ലഭ്യമായ റിവാർഡ്:</span>
            <span class="font-mono font-black text-emerald-400 text-xs ml-1">₹${firmPoints.toFixed(2)}</span>
          </div>
          <button type="button" onclick="openStoreBatchRulesModal('${f.id}')" class="py-2 px-3 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-extrabold text-xs rounded-xl shadow transition cursor-pointer flex items-center gap-1.5 transform hover:scale-[1.02]">
            <span>📋 ബാച്ചുകളും റൂളുകളും</span>
            <span>➔</span>
          </button>
        </div>
      </div>
    `;
  }).join('');
}

async function openStoreBatchRulesModal(firmId) {
  showLoadingSpinner(true);
  try {
    const phone = state.currentPhone || '';
    const res = await fetch(`/api/firm/${firmId}/batches?phone=${phone}`);
    const data = await res.json();
    if (!data.success) {
      alert('Could not load store details');
      return;
    }

    const firm = data.firm;
    const nameEl = document.getElementById('smodal-firm-name');
    const badgeEl = document.getElementById('smodal-firm-badge');
    const iconEl = document.getElementById('smodal-icon');
    const ptsEl = document.getElementById('smodal-total-pts');
    const batchesList = document.getElementById('smodal-batches-list');

    if (nameEl) nameEl.textContent = firm.name;
    if (badgeEl) badgeEl.textContent = firm.badge || firm.category;
    if (iconEl) iconEl.textContent = firm.category_icon === 'fuel' ? '⛽' : (firm.category_icon === 'coffee' ? '☕' : '🛒');
    if (ptsEl) ptsEl.textContent = `₹${parseFloat(data.total_points || 0).toFixed(2)} ലഭ്യമാണ് (${data.total_batches || 0} ബാച്ചുകൾ)`;

    if (batchesList) {
      if (!data.batches || data.batches.length === 0) {
        batchesList.innerHTML = `
          <div class="p-4 rounded-xl bg-slate-950 border border-slate-800 text-center text-xs text-slate-400">
            നിങ്ങൾക്ക് ഈ സ്റ്റോറിൽ നിലവിൽ ആക്റ്റീവ് ബാച്ചുകൾ ഒന്നും ലഭ്യമല്ല. അടുത്ത പർച്ചേസിൽ റിവാർഡ് പോയിന്റുകൾ ലഭിക്കുന്നതാണ്!
          </div>
        `;
      } else {
        batchesList.innerHTML = data.batches.map(b => {
          const isExpiring = (b.days_left <= 2);
          const isMaturingTomorrow = b.is_maturing_tomorrow;
          return `
            <div class="p-3.5 rounded-2xl bg-slate-950 border ${isExpiring ? 'border-rose-500/50' : 'border-slate-800'} space-y-2">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-mono font-bold text-white">#${b.invoice_no || b.id}</span>
                  ${isMaturingTomorrow ? '<span class="px-2 py-0.5 rounded-full text-[9px] font-black bg-amber-500/20 text-amber-400 border border-amber-500/30">⏳ മെച്ചൂരിറ്റി നാളെ</span>' : '<span class="px-2 py-0.5 rounded-full text-[9px] font-black bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">✅ ലഭ്യമാണ്</span>'}
                </div>
                <span class="text-sm font-black text-emerald-400 font-mono">₹${parseFloat(b.points_remaining).toFixed(2)}</span>
              </div>
              <div class="grid grid-cols-2 gap-2 text-[10px] text-slate-300 bg-slate-900/60 p-2 rounded-xl">
                <div>
                  <span class="text-slate-400">ലഭിച്ച തീയതി:</span> <span class="text-white font-medium">${b.earned_date ? b.earned_date.slice(0, 10) : 'N/A'}</span>
                </div>
                <div>
                  <span class="text-slate-400">മെച്ചൂരിറ്റി:</span> <span class="${isMaturingTomorrow ? 'text-amber-400 font-bold' : 'text-emerald-400 font-bold'}">${isMaturingTomorrow ? 'നാളെ 12:00 AM' : 'ഇന്ന് റെഡീം ചെയ്യാം'}</span>
                </div>
                <div>
                  <span class="text-slate-400">എക്സ്പയറി:</span> <span class="${isExpiring ? 'text-rose-400 font-bold' : 'text-slate-300'}">${b.expiry_date ? b.expiry_date.slice(0, 10) : 'N/A'} (${b.days_left} ദിവസം ബാക്കി)</span>
                </div>
                <div>
                  <span class="text-slate-400">10x മിനിമം ബിൽ:</span> <span class="text-amber-300 font-bold">₹${parseFloat(b.required_bill_to_redeem || 0).toFixed(2)}</span>
                </div>
              </div>
            </div>
          `;
        }).join('');
      }
    }

    openModal('store-batch-rules-modal');
  } catch (err) {
    console.error('Error opening store batches modal:', err);
    alert('Error loading store batches');
  } finally {
    showLoadingSpinner(false);
  }
}

// Open Firm Detail Modal
async function openFirmDetailModal(firmId, broadcast = true) {
  if (broadcast && typeof LiveSync !== 'undefined' && LiveSync.broadcast) {
    LiveSync.broadcast({ type: 'FIRM_DETAIL_OPEN', firmId: firmId });
  }
  try {
    const res = await fetch(`/api/firms/${firmId}?phone=${state.currentPhone}`);
    const data = await res.json();
    if (!data.success) return;

    const firm = data.firm;
    state.selectedFirm = firm;

    const titleEl = document.getElementById('firm-detail-title');
    if (titleEl) titleEl.innerText = firm.name;
    const catEl = document.getElementById('firm-detail-category');
    if (catEl) catEl.innerText = firm.category;
    const tagEl = document.getElementById('firm-detail-tagline');
    if (tagEl) tagEl.innerText = firm.tagline;
    const addrEl = document.getElementById('firm-detail-address');
    if (addrEl) addrEl.innerText = firm.address;
    const badgeEl = document.getElementById('firm-detail-badge');
    if (badgeEl) badgeEl.innerText = firm.badge || 'PARTNER FIRM';
    const colorEl = document.getElementById('firm-detail-header-color');
    if (colorEl) colorEl.style.backgroundColor = firm.theme_color;

    // Rules List
    document.getElementById('firm-detail-rules').innerHTML = `
      <div class="bg-slate-900/80 rounded-2xl p-3 border border-slate-800 text-xs space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-slate-400">Value Conversion:</span>
          <span class="font-bold text-emerald-400">1 Reward Point = ₹1.00</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-slate-400">Min Purchase Multiplier:</span>
          <span class="font-bold text-white">${firm.min_purchase_multiplier > 1 ? firm.min_purchase_multiplier + 'x Multiplier' : 'No Multiplier (Standard)'}</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-slate-400">Min Bill Amount:</span>
          <span class="font-bold text-white">₹${firm.min_bill_amount.toFixed(2)}</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-slate-400">Max Bill Deduction:</span>
          <span class="font-bold text-white">${firm.max_redemption_pct}% of invoice</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-slate-400">Batch Validity:</span>
          <span class="font-bold text-white">${firm.validity_days} Days from purchase</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-slate-400">Next Day Policy:</span>
          <span class="font-bold ${firm.next_day_redemption_only ? 'text-amber-400' : 'text-slate-300'}">${firm.next_day_redemption_only ? 'Active (Matures next day)' : 'Instant Same-Day Allowed'}</span>
        </div>
      </div>
    `;

    // Customer Specific Batches at this Firm
    const batchContainer = document.getElementById('firm-detail-customer-batches');
    const batches = firm.customer_batches || [];
    if (batches.length > 0) {
      const firmTotal = batches.reduce((acc, b) => acc + b.points_remaining, 0);
      batchContainer.innerHTML = `
        <div class="mb-3 p-3 bg-emerald-500/10 rounded-2xl border border-emerald-500/30 flex items-center justify-between">
          <div>
            <div class="text-[10px] text-emerald-400 font-bold uppercase">Your Available Balance at this Firm</div>
            <div class="text-lg font-black text-white">₹${firmTotal.toFixed(2)} <span class="text-xs text-slate-300">(${firmTotal} Pts)</span></div>
          </div>
          <button onclick="openRedeemModalForFirm('${firm.id}', ${firmTotal})" class="bg-emerald-500 hover:bg-emerald-600 text-white font-bold text-xs px-3 py-2 rounded-xl transition">
            Redeem Now
          </button>
        </div>
        ${batches.map(b => `
          <div class="p-2.5 rounded-xl bg-slate-900 border border-slate-800 mb-2 flex items-center justify-between text-xs">
            <div>
              <div class="font-bold text-white">Batch #${b.id}</div>
              <div class="text-[10px] text-slate-400">Inv #${b.invoice_no} • Expires: ${b.expiry_date.split(' ')[0]}</div>
              <div class="text-[10px] text-amber-400 font-semibold">Min purchase: ₹${b.required_bill_to_redeem.toFixed(2)}</div>
            </div>
            <div class="text-right">
              <div class="font-bold text-emerald-400">₹${b.points_remaining.toFixed(2)}</div>
            </div>
          </div>
        `).join('')}
      `;
    } else {
      batchContainer.innerHTML = `
        <div class="p-4 rounded-2xl bg-slate-900 border border-slate-800 text-center text-xs text-slate-400">
          No earned points at ${firm.name} yet. Shop here to earn centralized reward points!
        </div>
      `;
    }

    // Firm Offers & Targeted Advertisements
    const offersContainer = document.getElementById('firm-detail-offers');
    if (firm.offers && firm.offers.length > 0) {
      offersContainer.innerHTML = firm.offers.map(o => `
        <div class="glass-card p-3 mb-3 border border-indigo-500/20 overflow-hidden relative">
          <div class="flex items-center justify-between mb-1">
            <span class="text-[9px] font-bold px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300">${o.tag}</span>
            <span class="text-[10px] text-slate-400">Valid till: ${o.valid_till}</span>
          </div>
          <div class="text-sm font-bold text-white">${o.title}</div>
          <div class="text-xs text-slate-300 mt-1">${o.description}</div>
          <div class="mt-2 flex items-center justify-between pt-2 border-t border-slate-800">
            <span class="font-mono text-xs font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded">${o.coupon_code || 'IN-STORE'}</span>
            <span class="text-xs font-bold text-emerald-400">${o.discount_text || ''}</span>
          </div>
        </div>
      `).join('');
    } else {
      offersContainer.innerHTML = `<div class="text-xs text-slate-500 text-center py-2">No active ads at the moment.</div>`;
    }

    openModal('firm-detail-sheet');
  } catch (err) {
    console.error('Error opening firm detail:', err);
  }
}

// ----------------- IN-STORE COUNTER REDEMPTION & QR FLOW ----------------- //

function populateRedeemFirmSelect() {
  const select = document.getElementById('redeem-firm-select');
  if (!select) return;

  select.innerHTML = state.firms.map(f => {
    return `<option value="${f.id}">${f.name} (${f.category})</option>`;
  }).join('');

  select.addEventListener('change', updateRedeemFirmGuidelines);
  updateRedeemFirmGuidelines();
}

function updateRedeemFirmGuidelines() {
  const select = document.getElementById('redeem-firm-select');
  if (!select) return;
  const firm = state.firms.find(f => f.id === select.value);
  if (!firm) return;

  const guideEl = document.getElementById('redeem-rule-guideline');
  if (guideEl) {
    guideEl.innerHTML = `
      <div class="text-[11px] text-slate-300 flex items-start gap-1.5 bg-slate-900/80 p-2.5 rounded-xl border border-slate-800">
        <span class="text-amber-400">ℹ️</span>
        <div>
          <span class="font-bold text-white">${firm.name} Rules:</span> ${firm.rule_summary}
        </div>
      </div>
    `;
  }
}

function openRedeemModalForFirm(firmId, suggestedPoints = 0) {
  closeModal('firm-detail-sheet');
  switchTab('redeem');

  const select = document.getElementById('redeem-firm-select');
  if (select) {
    select.value = firmId;
    updateRedeemFirmGuidelines();
  }

  const pointsInput = document.getElementById('redeem-points-input');
  if (pointsInput) {
    pointsInput.value = suggestedPoints > 0 ? suggestedPoints : Math.min(100, state.summary.total_active_points);
  }
}

// ----------------- LIVE ERP REWARD CLAIM & REDEMPTION ----------------- //

async function claimBatchRedemptionNow(batchId, firmId, points, invoiceNo, firmName = 'EEYES Pro Retail & Supermarket') {
  if (!state.currentPhone) {
    alert('Please select or log in with a customer phone number first.');
    return;
  }

  try {
    const res = await fetch('/api/redemption/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        phone: state.currentPhone,
        firm_id: firmId,
        points: points,
        batch_id: batchId,
        invoice_no: invoiceNo
      })
    });

    const data = await res.json();
    if (!data.success) {
      alert(data.message || 'Error sending live claim to billing desk');
      return;
    }

    // Show celebratory claim modal
    showClaimSuccessModal(data.claim);

    // Broadcast sync action to connected mirror screens
    if (typeof LiveSync !== 'undefined' && LiveSync.broadcastAction) {
      LiveSync.broadcastAction({
        type: 'REDEMPTION_CLAIM_CREATED',
        phone: state.currentPhone,
        claim: data.claim,
        firm_name: firmName,
        points: points
      });
    }
  } catch (err) {
    alert('Connection note: ' + err.message);
  }
}

function showClaimSuccessModal(claim) {
  if (!claim) return;
  const modal = document.getElementById('claim-success-modal');
  if (!modal) return;

  const firmEl = document.getElementById('claim-modal-firm');
  if (firmEl) firmEl.textContent = claim.firm_name || 'EEYES Pro Retail & Supermarket';

  const custEl = document.getElementById('claim-modal-customer');
  if (custEl) custEl.textContent = `${claim.customer_name || 'Customer'} (+91 ${claim.customer_phone})`;

  const ptsEl = document.getElementById('claim-modal-points');
  if (ptsEl) ptsEl.textContent = `₹${parseFloat(claim.points || 0).toFixed(2)} (1 RP = ₹1.00)`;

  const reqEl = document.getElementById('claim-modal-req-bill');
  if (reqEl) reqEl.textContent = `Min ₹${parseFloat(claim.required_bill || 0).toFixed(2)} (10x Rule)`;

  openModal('claim-success-modal');
  triggerConfetti();
}

function showRedemptionCompletedAlert(data) {
  if (!data) return;
  const modal = document.getElementById('redemption-completed-modal');
  if (!modal) return;

  const invEl = document.getElementById('red-done-invoice');
  if (invEl) invEl.textContent = data.invoice_no || 'INV-2026';

  const firmEl = document.getElementById('red-done-firm');
  if (firmEl) firmEl.textContent = data.firm_name || 'EEYES Pro Retail & Supermarket';

  const ptsEl = document.getElementById('red-done-points');
  if (ptsEl) ptsEl.textContent = `-₹${parseFloat(data.points_deducted || 0).toFixed(2)}`;

  const balEl = document.getElementById('red-done-balance');
  if (balEl) balEl.textContent = `₹${parseFloat(data.new_balance || 0).toFixed(2)}`;

  openModal('redemption-completed-modal');
}

async function generateRedemptionCode() {
  const firmId = document.getElementById('redeem-firm-select').value;
  const points = parseFloat(document.getElementById('redeem-points-input').value);

  if (isNaN(points) || points <= 0) {
    alert('Please enter a valid amount of points to redeem');
    return;
  }

  if (points > state.summary.total_active_points) {
    alert(`Insufficient points! Your total wallet balance is ₹${state.summary.total_active_points.toFixed(2)}`);
    return;
  }

  try {
    const res = await fetch('/api/redemption/create-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        phone: state.currentPhone,
        firm_id: firmId,
        points: points
      })
    });

    const data = await res.json();
    if (!data.success) {
      alert(data.message || 'Error creating redemption token');
      return;
    }

    state.activeRedemptionToken = data;
    renderActiveRedemptionQR(data);
  } catch (err) {
    alert('Failed to connect to redemption server');
  }
}

function renderActiveRedemptionQR(tokenData) {
  const stepInput = document.getElementById('redeem-step-input');
  const stepActive = document.getElementById('redeem-step-active');

  stepInput.classList.add('hidden');
  stepActive.classList.remove('hidden');

  document.getElementById('active-qr-otp').innerText = tokenData.otp;
  document.getElementById('active-qr-firm-name').innerText = tokenData.firm_name;
  document.getElementById('active-qr-points').innerText = `₹${tokenData.points_to_redeem.toFixed(2)}`;
  document.getElementById('active-qr-rule').innerText = tokenData.rule_summary;

  // Render SVG QR Code
  generateSvgQrCode('active-qr-canvas', `OMNIPOINTS:${tokenData.token}:${tokenData.otp}:${tokenData.points_to_redeem}`);

  // Countdown timer (5 minutes)
  const timerEl = document.getElementById('active-qr-timer');
  let secondsLeft = 300;

  if (state.tokenTimerInterval) clearInterval(state.tokenTimerInterval);
  state.tokenTimerInterval = setInterval(() => {
    secondsLeft--;
    if (secondsLeft <= 0) {
      clearInterval(state.tokenTimerInterval);
      cancelActiveRedemption();
      alert('Redemption session expired. Please generate a new QR.');
      return;
    }
    const mins = Math.floor(secondsLeft / 60);
    const secs = secondsLeft % 60;
    timerEl.innerText = `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  }, 1000);
}

function cancelActiveRedemption() {
  if (state.tokenTimerInterval) clearInterval(state.tokenTimerInterval);
  state.activeRedemptionToken = null;
  document.getElementById('redeem-step-active').classList.add('hidden');
  document.getElementById('redeem-step-input').classList.remove('hidden');
}

// Generate an SVG QR code pattern client-side
function generateSvgQrCode(elementId, text) {
  const container = document.getElementById(elementId);
  if (!container) return;

  // Simple clean SVG QR representation
  const size = 180;
  let svg = `<svg width="${size}" height="${size}" viewBox="0 0 25 25" fill="none" xmlns="http://www.w3.org/2000/svg">`;
  svg += `<rect width="25" height="25" fill="white"/>`;

  // Draw Corner Target Boxes
  const drawCorner = (x, y) => {
    let s = `<rect x="${x}" y="${y}" width="7" height="7" fill="black"/>`;
    s += `<rect x="${x+1}" y="${y+1}" width="5" height="5" fill="white"/>`;
    s += `<rect x="${x+2}" y="${y+2}" width="3" height="3" fill="black"/>`;
    return s;
  };

  svg += drawCorner(1, 1);
  svg += drawCorner(17, 1);
  svg += drawCorner(1, 17);

  // Pseudo-random deterministic module grid based on text hash
  let hash = 0;
  for (let i = 0; i < text.length; i++) {
    hash = (hash << 5) - hash + text.charCodeAt(i);
    hash |= 0;
  }

  for (let r = 0; r < 25; r++) {
    for (let c = 0; c < 25; c++) {
      if ((r <= 8 && c <= 8) || (r <= 8 && c >= 16) || (r >= 16 && c <= 8)) continue;
      const bit = ((hash * (r * 31 + c)) ^ (r * c * 17)) % 7;
      if (bit === 0 || bit === 3 || (r + c) % 3 === 0) {
        svg += `<rect x="${c}" y="${r}" width="1" height="1" fill="#0F172A"/>`;
      }
    }
  }

  svg += `</svg>`;
  container.innerHTML = svg;
}

// ----------------- CASHIER POS COUNTER SIMULATOR ----------------- //

function openCashierSimulator() {
  const modal = document.getElementById('cashier-simulator-modal');
  if (!modal) return;

  // Auto-fill active OTP if user just generated one
  const codeInput = document.getElementById('cashier-code-input');
  if (state.activeRedemptionToken && codeInput) {
    codeInput.value = state.activeRedemptionToken.otp;
  }

  openModal('cashier-simulator-modal');
}

async function submitCashierVerification() {
  const code = document.getElementById('cashier-code-input').value.trim();
  const billAmount = parseFloat(document.getElementById('cashier-bill-amount').value);
  const notes = document.getElementById('cashier-notes').value.trim() || 'Store Checkout Counter';

  if (!code || isNaN(billAmount) || billAmount <= 0) {
    alert('Please enter both a valid Bill Amount and OTP/Code');
    return;
  }

  try {
    const res = await fetch('/api/redemption/cashier-verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: code,
        bill_amount: billAmount,
        notes: notes
      })
    });

    const data = await res.json();
    const resultBox = document.getElementById('cashier-result-box');
    resultBox.classList.remove('hidden');

    if (data.success) {
      resultBox.className = 'mt-4 p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-xs';
      resultBox.innerHTML = `
        <div class="text-sm font-bold text-emerald-400 flex items-center gap-1.5 mb-2">
          <span>✅</span> ${data.message}
        </div>
        <div class="space-y-1 text-slate-300">
          <div>Customer: <strong class="text-white">${data.customer_name}</strong></div>
          <div>Store/Firm: <strong class="text-white">${data.firm_name}</strong></div>
          <div>Original Bill Amount: <strong class="text-white">₹${data.bill_amount.toFixed(2)}</strong></div>
          <div>Reward Points Offset: <strong class="text-emerald-400">-₹${data.points_deducted.toFixed(2)}</strong></div>
          <div class="text-sm font-black text-white pt-1 border-t border-slate-700">
            Net Payable by Customer: ₹${data.final_payable_amount.toFixed(2)}
          </div>
          <div class="text-[10px] text-slate-400 mt-1">Transaction Ref: ${data.transaction_id}</div>
        </div>
      `;

      // Cancel customer active token view since it is completed
      cancelActiveRedemption();

      // Refresh customer wallet live
      await refreshWalletSilent();
      triggerConfetti();
      showToast(`🎉 ₹${data.points_deducted.toFixed(2)} deducted at ${data.firm_name}!`);

    } else {
      resultBox.className = 'mt-4 p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-xs';
      resultBox.innerHTML = `
        <div class="text-sm font-bold text-rose-400 flex items-center gap-1.5 mb-1">
          <span>❌ Validation Failed</span>
        </div>
        <div class="text-rose-200">${data.message}</div>
      `;
    }
  } catch (err) {
    alert('Error connecting to POS verification endpoint');
  }
}

// ----------------- SCRATCH CARD GAMIFICATION ----------------- //

function renderScratchCardPreview() {
  const container = document.getElementById('scratch-card-preview-container');
  if (!container) return;

  const unopened = state.scratchCards.filter(c => !c.is_scratched);
  if (unopened.length > 0) {
    const card = unopened[0];
    container.innerHTML = `
      <div onclick="openScratchModal('${card.id}')" class="glass-card p-3 mb-4 cursor-pointer hover:border-amber-500/50 transition-all bg-gradient-to-r from-amber-950/30 via-slate-900 to-indigo-950/30 border border-amber-500/30 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-amber-500/20 text-amber-400 flex items-center justify-center text-xl font-bold">
            🎁
          </div>
          <div>
            <div class="text-[10px] font-bold text-amber-400 uppercase tracking-wide">Customer Mystery Drop</div>
            <div class="text-xs font-bold text-white">${card.title}</div>
            <div class="text-[10px] text-slate-400">Tap to scratch & reveal bonus points!</div>
          </div>
        </div>
        <span class="text-xs font-bold text-amber-300 bg-amber-500/20 px-2.5 py-1.5 rounded-xl">Scratch Now &rarr;</span>
      </div>
    `;
    container.classList.remove('hidden');
  } else {
    container.classList.add('hidden');
  }
}

function openScratchModal(cardId) {
  const card = state.scratchCards.find(c => c.id === cardId);
  if (!card) return;

  document.getElementById('scratch-modal-title').innerText = card.title;
  document.getElementById('scratch-revealed-points').innerText = `+₹${card.points_reward.toFixed(2)}`;

  initScratchCanvas(cardId, card.points_reward);
  openModal('scratch-modal');
}

function initScratchCanvas(cardId, rewardPoints) {
  const canvas = document.getElementById('scratch-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  canvas.width = canvas.parentElement.offsetWidth || 340;
  canvas.height = 180;

  // Draw silver holographic cover
  const grad = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
  grad.addColorStop(0, '#94A3B8');
  grad.addColorStop(0.5, '#CBD5E1');
  grad.addColorStop(1, '#64748B');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Add decorative text on cover
  ctx.fillStyle = '#0F172A';
  ctx.font = 'bold 15px Plus Jakarta Sans, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('✨ SCRATCH WITH FINGER OR MOUSE ✨', canvas.width / 2, canvas.height / 2);

  let isDrawing = false;
  let scratchedPixels = 0;
  let hasClaimed = false;

  const scratch = (x, y) => {
    ctx.globalCompositeOperation = 'destination-out';
    ctx.beginPath();
    ctx.arc(x, y, 22, 0, Math.PI * 2);
    ctx.fill();
    scratchedPixels++;

    if (scratchedPixels > 25 && !hasClaimed) {
      hasClaimed = true;
      claimScratchReward(cardId);
    }
  };

  canvas.onmousedown = (e) => { isDrawing = true; scratch(e.offsetX, e.offsetY); };
  canvas.onmousemove = (e) => { if (isDrawing) scratch(e.offsetX, e.offsetY); };
  window.onmouseup = () => { isDrawing = false; };

  // Mobile Touch Support
  canvas.ontouchstart = (e) => {
    isDrawing = true;
    const rect = canvas.getBoundingClientRect();
    scratch(e.touches[0].clientX - rect.left, e.touches[0].clientY - rect.top);
  };
  canvas.ontouchmove = (e) => {
    if (!isDrawing) return;
    const rect = canvas.getBoundingClientRect();
    scratch(e.touches[0].clientX - rect.left, e.touches[0].clientY - rect.top);
  };
  canvas.ontouchend = () => { isDrawing = false; };
}

async function claimScratchReward(cardId) {
  try {
    const res = await fetch('/api/gamification/scratch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ card_id: cardId, phone: state.currentPhone })
    });
    const data = await res.json();
    if (data.success) {
      triggerConfetti();
      showToast(`🎉 Won ₹${data.points_won.toFixed(2)} Bonus Points!`);
      await refreshWalletSilent();
    }
  } catch (err) {
    console.error('Scratch claim failed:', err);
  }
}

// ----------------- ERP / ES PRO INTEGRATION SIMULATOR ----------------- //

async function simulateEsProBilling() {
  const firmId = document.getElementById('erp-sim-firm').value;
  const billAmount = parseFloat(document.getElementById('erp-sim-bill').value);
  const profitAmount = parseFloat(document.getElementById('erp-sim-profit').value);
  const paymentMode = document.getElementById('erp-sim-paymode').value;

  if (isNaN(billAmount) || billAmount <= 0) {
    alert('Please enter a valid bill amount');
    return;
  }

  try {
    const res = await fetch('/api/v1/erp/issue-reward', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        firm_id: firmId,
        customer_phone: state.currentPhone,
        customer_name: state.customer.name,
        invoice_no: `INV-ERP-${Math.floor(1000 + Math.random() * 9000)}`,
        bill_amount: billAmount,
        profit_amount: profitAmount,
        payment_mode: paymentMode
      })
    });

    const data = await res.json();
    const logBox = document.getElementById('erp-sim-log');
    logBox.classList.remove('hidden');

    if (data.success) {
      logBox.className = 'mt-3 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-300';
      logBox.innerHTML = `
        <strong>[SUCCESS 200 OK]</strong> ${data.message}<br/>
        Batch ID: ${data.batch_id}<br/>
        Points Issued: ₹${data.points_issued.toFixed(2)}<br/>
        Required Next Bill to Unlock: ₹${data.required_next_bill.toFixed(2)}
      `;
      await refreshWalletSilent();
      triggerConfetti();
      showToast(`⚡ ES PRO Invoice processed! +₹${data.points_issued.toFixed(2)} added!`);
    } else {
      logBox.className = 'mt-3 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300';
      logBox.innerHTML = `<strong>[ERROR]</strong> ${data.message}`;
    }
  } catch (err) {
    alert('Failed to connect to ERP endpoint');
  }
}

// ----------------- TRANSACTIONS LIST ----------------- //

function renderTransactionsList(filterType = 'ALL') {
  const container = document.getElementById('transactions-ledger-list');
  if (!container) return;

  const filtered = filterType === 'ALL'
    ? state.transactions
    : state.transactions.filter(t => t.type === filterType);

  if (filtered.length === 0) {
    container.innerHTML = `<div class="text-xs text-slate-500 text-center py-8">No transaction history.</div>`;
    return;
  }

  container.innerHTML = filtered.map(t => {
    const isEarn = t.type === 'EARN' || t.type === 'BONUS';
    return `
      <div class="glass-card p-3 mb-2.5 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl flex items-center justify-center text-sm font-bold ${isEarn ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}">
            ${isEarn ? '↓' : '↑'}
          </div>
          <div>
            <div class="text-xs font-bold text-white">${t.description}</div>
            <div class="text-[10px] text-slate-400">${t.firm_name} • ${t.created_at}</div>
          </div>
        </div>
        <div class="text-right">
          <div class="text-sm font-black ${isEarn ? 'text-emerald-400' : 'text-rose-400'}">
            ${isEarn ? '+' : ''}₹${Math.abs(t.points).toFixed(2)}
          </div>
          <div class="text-[10px] text-slate-400 font-mono">${isEarn ? '+' : '-'}${Math.abs(t.points)} Pts</div>
        </div>
      </div>
    `;
  }).join('');
}

function filterLedger(type, btn) {
  document.querySelectorAll('.ledger-filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderTransactionsList(type);
}

// ----------------- NAVIGATION & MODALS ----------------- //

function setupBottomNav() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      const tab = item.getAttribute('data-tab');
      switchTab(tab);
    });
  });
}

function switchTab(tabId, broadcast = true) {
  state.activeTab = tabId;
  if (broadcast && typeof LiveSync !== 'undefined' && LiveSync.broadcast) {
    LiveSync.broadcast({ type: 'TAB_CHANGE', tab: tabId });
  }

  document.querySelectorAll('.nav-item').forEach(item => {
    if (item.getAttribute('data-tab') === tabId) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });

  document.querySelectorAll('.tab-view').forEach(view => {
    view.classList.add('hidden');
  });

  const target = document.getElementById(`view-${tabId}`);
  if (target) {
    target.classList.remove('hidden');
  }

  // Scroll to top of app viewport
  const viewport = document.querySelector('.app-viewport');
  if (viewport) viewport.scrollTop = 0;
}

function openModal(id, broadcast = true, extra = {}) {
  const el = document.getElementById(id);
  const overlay = document.getElementById('global-sheet-overlay');
  if (el) el.classList.add('open');
  if (overlay) overlay.classList.add('open');

  if (broadcast && typeof LiveSync !== 'undefined' && LiveSync.broadcast) {
    LiveSync.broadcast({ type: 'MODAL_OPEN', modalId: id, extra: extra });
  }
}

function closeModal(id, broadcast = true) {
  const el = document.getElementById(id);
  const overlay = document.getElementById('global-sheet-overlay');
  if (el) el.classList.remove('open');
  if (overlay) overlay.classList.remove('open');

  if (broadcast && typeof LiveSync !== 'undefined' && LiveSync.broadcast) {
    LiveSync.broadcast({ type: 'MODAL_CLOSE', modalId: id });
  }
}

function closeAllModals(broadcast = true) {
  document.querySelectorAll('.bottom-sheet, .modal-dialog').forEach(m => m.classList.remove('open'));
  const overlay = document.getElementById('global-sheet-overlay');
  if (overlay) overlay.classList.remove('open');

  if (broadcast && typeof LiveSync !== 'undefined' && LiveSync.broadcast) {
    LiveSync.broadcast({ type: 'MODAL_CLOSE' });
  }
}

function showLoadingSpinner(show) {
  const spinner = document.getElementById('global-loading-spinner');
  if (spinner) {
    spinner.style.display = show ? 'flex' : 'none';
  }
}

function showToast(msg) {
  const toast = document.getElementById('app-toast');
  if (!toast) return;
  toast.innerText = msg;
  toast.classList.remove('hidden');
  toast.classList.add('opacity-100');
  setTimeout(() => {
    toast.classList.remove('opacity-100');
    setTimeout(() => toast.classList.add('hidden'), 300);
  }, 1500);
}

// Confetti Particle Effect
function triggerConfetti() {
  const canvas = document.getElementById('confetti-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;

  const particles = [];
  const colors = ['#4F46E5', '#10B981', '#F59E0B', '#EC4899', '#06B6D4'];

  for (let i = 0; i < 80; i++) {
    particles.push({
      x: canvas.width / 2,
      y: canvas.height / 2,
      vx: (Math.random() - 0.5) * 12,
      vy: (Math.random() - 0.8) * 14,
      size: Math.random() * 8 + 4,
      color: colors[Math.floor(Math.random() * colors.length)],
      alpha: 1,
      rotation: Math.random() * 360
    });
  }

  const render = () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let active = false;

    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.35; // gravity
      p.alpha -= 0.015;

      if (p.alpha > 0) {
        active = true;
        ctx.save();
        ctx.globalAlpha = p.alpha;
        ctx.fillStyle = p.color;
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rotation * Math.PI) / 180);
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
        ctx.restore();
      }
    });

    if (active) {
      requestAnimationFrame(render);
    } else {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  };

  requestAnimationFrame(render);
}

// ----------------- CUSTOMER REGISTERED ID PASS (EEYES PRO INTERFACE) ----------------- //

function openCustomerIdCard() {
  if (!state.customer) return;

  const phone = state.currentPhone;
  const regId = `EEYES-OP-${phone}`;

  const nameEl = document.getElementById('card-modal-name');
  if (nameEl) nameEl.innerText = state.customer.name;
  const phoneEl = document.getElementById('card-modal-phone');
  if (phoneEl) phoneEl.innerText = `+91 ${phone}`;
  const vipEl = document.getElementById('card-modal-vip');
  if (vipEl) vipEl.innerText = state.customer.vip_tier || 'Silver Member';
  const regIdEl = document.getElementById('card-modal-reg-id');
  if (regIdEl) regIdEl.innerText = regId;
  const balEl = document.getElementById('card-modal-balance');
  if (balEl) balEl.innerText = `₹${state.summary.total_active_points.toFixed(2)}`;
  const ptsEl = document.getElementById('card-modal-points');
  if (ptsEl) ptsEl.innerText = `${state.summary.total_active_points}`;
  const barcodeDigitsEl = document.getElementById('card-modal-barcode-digits');
  if (barcodeDigitsEl) barcodeDigitsEl.innerText = `OP${phone}`;

  // Render SVG Barcode
  renderBarcodeSvg('card-modal-barcode-container', `OP${phone}`);

  openModal('customer-id-card-modal');
}

function renderBarcodeSvg(containerId, codeText) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Clean Code 128 style visual SVG barcode
  const width = 280;
  const height = 48;
  let svg = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">`;
  svg += `<rect width="${width}" height="${height}" fill="white" />`;

  // Draw pattern of bars based on code hash
  let x = 12;
  const barWidths = [2, 1, 3, 1, 2, 4, 1, 3, 2, 1, 3, 2, 1, 4, 2, 3, 1, 2];
  let idx = 0;

  while (x < width - 14) {
    const w = barWidths[idx % barWidths.length];
    svg += `<rect x="${x}" y="2" width="${w}" height="${height - 4}" fill="#0F172A" />`;
    x += w + ((idx % 3 === 0) ? 2 : 1.5);
    idx++;
  }

  svg += `</svg>`;
  container.innerHTML = svg;
}

function shareCardToWhatsApp() {
  if (!state.customer) return;

  const phone = state.currentPhone;
  const name = state.customer.name;
  const regId = `EEYES-OP-${phone}`;
  const balance = state.summary.total_active_points.toFixed(2);
  const cardUrl = `${window.location.origin}/?phone=${phone}&view=id-card`;

  const msg = `🙏 *Namaste ${name} Ji!*\n\n` +
    `Here is your official *EEYES PRO Centralized Customer Reward ID Pass*:\n\n` +
    `🪪 *Registered ID:* \`${regId}\`\n` +
    `💰 *Active Wallet Balance:* *₹${balance}* (${balance} Points)\n` +
    `⭐ *Tier:* ${state.customer.vip_tier || 'Gold VIP'}\n` +
    `🏢 *Accepted at:* ES Supermarket, Highway Petroleum, Bean & Bloom Café, Nexus Tech, Urban Vogue & Aura Wellness!\n\n` +
    `📲 *Open Your Digital Card & Wallet:* ${cardUrl}\n\n` +
    `_Present your 6-digit OTP or Barcode at checkout to redeem points!_`;

  const waUrl = `https://wa.me/91${phone}?text=${encodeURIComponent(msg)}`;
  window.open(waUrl, '_blank');
}

async function submitCustomerEnrollment() {
  const phone = document.getElementById('enroll-phone').value.trim();
  const name = document.getElementById('enroll-name').value.trim();
  const vip_tier = document.getElementById('enroll-tier').value;
  const bonus = parseFloat(document.getElementById('enroll-bonus').value) || 0;
  const source_firm = document.getElementById('enroll-source-firm').value;

  if (!phone || phone.length < 10) {
    alert('Please enter a valid 10-digit mobile number');
    return;
  }
  if (!name) {
    alert('Please enter the customer full name');
    return;
  }

  try {
    const res = await fetch('/api/v1/erp/customer/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        phone: phone,
        name: name,
        vip_tier: vip_tier,
        initial_bonus: bonus,
        source_firm: source_firm
      })
    });

    const data = await res.json();
    const logBox = document.getElementById('enroll-result-log');
    logBox.classList.remove('hidden');

    if (data.success) {
      logBox.className = 'mt-3 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-300';
      logBox.innerHTML = `
        <strong>[REGISTERED IN EEYES PRO]</strong> ${data.message}<br/>
        Registered ID: <strong class="text-white">${data.customer.registered_id}</strong><br/>
        Wallet Balance: <strong>₹${data.wallet.total_active_points.toFixed(2)}</strong>
      `;

      // Switch to this new customer
      await switchCustomer(phone);
      triggerConfetti();
      closeModal('customer-registration-modal');
      openCustomerIdCard();
      showToast(`🎉 Customer ${name} registered with ID ${data.customer.registered_id}!`);
    } else {
      logBox.className = 'mt-3 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300';
      logBox.innerHTML = `<strong>[ERROR]</strong> ${data.message}`;
    }
  } catch (err) {
    alert('Error connecting to registration API');
  }
}

// ----------------- MINIMALIST EMBLEM BUSINESS LEDGER HUB ----------------- //

function renderBusinessLedger() {
  if (!state.businessLedger) return;

  const overall = state.businessLedger.overall || {};
  const firmsLedger = state.businessLedger.firms_ledger || [];

  // 1. Overall Glanceable Metrics
  const purchasesEl = document.getElementById('ledger-purchases-amount');
  const invoicesCountEl = document.getElementById('ledger-invoices-count');
  const returnsEl = document.getElementById('ledger-returns-amount');
  const returnsCountEl = document.getElementById('ledger-returns-count');
  const netEl = document.getElementById('ledger-net-amount');
  const cashbackEl = document.getElementById('ledger-cashback-amount');

  if (purchasesEl) purchasesEl.innerText = `₹${(overall.total_purchases_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  if (invoicesCountEl) invoicesCountEl.innerText = `${overall.total_invoices_count || 0} Invoices`;
  if (returnsEl) returnsEl.innerText = `₹${(overall.total_returns_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  if (returnsCountEl) returnsCountEl.innerText = `${overall.total_returns_count || 0} Returns`;
  if (netEl) netEl.innerText = `₹${(overall.net_purchases_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  if (cashbackEl) cashbackEl.innerText = `₹${(overall.points_earned || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

  // 2. Per-Store Cards with Minimalist Emblems & Expandable Invoices
  const container = document.getElementById('store-ledger-list');
  if (!container) return;

  if (firmsLedger.length === 0) {
    container.innerHTML = `<div class="text-xs text-slate-500 py-3 text-center">No connected store records found for this phone.</div>`;
    return;
  }

  container.innerHTML = firmsLedger.map((f, idx) => {
    const isCentralizedMatch = (f.registered_name && state.customer && f.registered_name === state.customer.name);
    const invoicesHtml = (f.invoices && f.invoices.length > 0) ? f.invoices.map(inv => {
      const isReturn = (inv.invoice_type === 'RETURN');
      return `
        <div class="flex items-center justify-between py-1.5 px-2.5 rounded-lg ${isReturn ? 'bg-amber-950/30 border border-amber-500/20 text-amber-200' : 'bg-slate-900/80 border border-slate-800 text-slate-200'} text-[11px]">
          <div>
            <div class="flex items-center gap-1.5 font-bold font-mono">
              <span class="${isReturn ? 'text-amber-400' : 'text-emerald-400'}">${isReturn ? '↩️ RET' : '🧾 INV'}</span>
              <span>${inv.invoice_no}</span>
            </div>
            <div class="text-[9px] text-slate-400 mt-0.5">${inv.invoice_date.split(' ')[0]} • ${inv.notes || (isReturn ? 'Goods Return Adjustment' : 'Store Billing')}</div>
          </div>
          <div class="text-right">
            <div class="font-bold ${isReturn ? 'text-amber-400' : 'text-white'} font-mono">${isReturn ? '-' : '+'}₹${parseFloat(inv.amount).toFixed(2)}</div>
            ${inv.points_affected > 0 ? `<div class="text-[9px] text-emerald-400 font-bold">+${inv.points_affected} Pts</div>` : ''}
          </div>
        </div>
      `;
    }).join('') : `<div class="text-[10px] text-slate-500 py-1 text-center">No individual invoices recorded.</div>`;

    return `
      <div class="glass-card p-3 rounded-2xl border border-slate-800/80 hover:border-slate-700 transition">
        <!-- Store Header & Registered Name Badge -->
        <div class="flex items-start justify-between mb-2">
          <div class="flex items-center gap-2">
            <div class="w-8 h-8 rounded-xl flex items-center justify-center font-black text-white text-xs shadow" style="background-color: ${f.theme_color || '#4F46E5'};">
              ${f.firm_name.charAt(0)}
            </div>
            <div>
              <div class="font-extrabold text-white text-xs flex items-center gap-1.5">
                <span>${f.firm_name}</span>
                ${f.is_es_pro ? '<span class="pill-badge bg-emerald-500/20 text-emerald-400 text-[8px]">ES PRO</span>' : ''}
              </div>
              <div class="text-[10px] text-slate-400">${f.firm_category}</div>
            </div>
          </div>
          <!-- Registered Name Status Badge -->
          <div class="text-right">
            <span class="inline-block px-2 py-0.5 rounded-full text-[9px] font-bold ${isCentralizedMatch ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30' : 'bg-amber-500/10 text-amber-300 border border-amber-500/30'}">
              ${f.registered_name ? `Stored: "${f.registered_name}"` : 'EEYES Partner'}
            </span>
            ${f.account_no ? `<div class="text-[8px] font-mono text-slate-400 mt-0.5">ID: ${f.account_no}</div>` : ''}
          </div>
        </div>

        <!-- 4 Glanceable Mini Emblem Statistics -->
        <div class="grid grid-cols-4 gap-1 py-1.5 px-2 bg-slate-900/60 rounded-xl border border-slate-800 mb-1.5">
          <div class="text-center">
            <div class="text-[9px] text-slate-400 uppercase font-semibold">Bills</div>
            <div class="text-xs font-black text-white mt-0.5">🧾 ${f.invoices_count}</div>
          </div>
          <div class="text-center border-l border-slate-800">
            <div class="text-[9px] text-slate-400 uppercase font-semibold">Bought</div>
            <div class="text-xs font-black text-indigo-300 mt-0.5">₹${f.purchases_amount.toFixed(0)}</div>
          </div>
          <div class="text-center border-l border-slate-800">
            <div class="text-[9px] text-slate-400 uppercase font-semibold">Return</div>
            <div class="text-xs font-black text-amber-400 mt-0.5">↩️ ₹${f.returns_amount.toFixed(0)}</div>
          </div>
          <div class="text-center border-l border-slate-800">
            <div class="text-[9px] text-slate-400 uppercase font-semibold">Points</div>
            <div class="text-xs font-black text-emerald-400 mt-0.5">🎁 ${f.points_remaining}</div>
          </div>
        </div>

        <!-- Toggle Invoices Button & Collapsible Container -->
        <button onclick="toggleStoreInvoices('store-inv-${idx}')" class="w-full py-1 text-[10px] font-bold text-slate-400 hover:text-indigo-400 flex items-center justify-center gap-1 transition">
          <span>View Invoices & Return Slips</span>
          <span id="store-inv-arrow-${idx}">&darr;</span>
        </button>

        <div id="store-inv-${idx}" class="space-y-1.5 mt-2 pt-2 border-t border-slate-800/80 hidden">
          ${invoicesHtml}
        </div>
      </div>
    `;
  }).join('');
}

function toggleStoreInvoices(id) {
  const el = document.getElementById(id);
  const arrow = document.getElementById(id.replace('store-inv-', 'store-inv-arrow-'));
  if (!el) return;
  if (el.classList.contains('hidden')) {
    el.classList.remove('hidden');
    if (arrow) arrow.innerHTML = '&uarr;';
  } else {
    el.classList.add('hidden');
    if (arrow) arrow.innerHTML = '&darr;';
  }
}

// ----------------- OTP LOGIN & MULTI-FIRM NAME CONFLICT RESOLUTION ----------------- //

function prefillLoginPhone(phone) {
  const input = document.getElementById('login-phone-input');
  if (input) input.value = phone;
  requestOtpFlow();
}

async function requestOtpFlow() {
  const phoneInput = document.getElementById('login-phone-input');
  const phone = phoneInput ? phoneInput.value.trim().replace(/[^0-9]/g, '') : '';

  if (!phone || phone.length < 10) {
    alert('Please enter a valid 10-digit mobile number');
    return;
  }

  showLoadingSpinner(true);
  try {
    const res = await fetch('/api/auth/request-otp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone })
    });
    const data = await res.json();
    if (!data.success) {
      alert(data.message || 'Failed to request OTP');
      return;
    }

    state.otpSession = {
      phone: phone,
      demoOtp: data.demo_otp,
      distinctNames: data.distinct_names || [],
      firmProfiles: data.firm_profiles || [],
      defaultSelectedName: data.default_selected_name || ''
    };

    // Transition to Step 2: OTP screen
    document.getElementById('login-step-phone').classList.add('hidden');
    document.getElementById('login-step-otp').classList.remove('hidden');

    document.getElementById('otp-target-phone').innerText = `+91 ${phone}`;
    document.getElementById('demo-otp-badge').innerText = data.demo_otp;
    document.getElementById('login-otp-input').value = '';

    // Render multi-firm name conflict resolution box
    const conflictBox = document.getElementById('name-conflict-resolution-box');
    const radioContainer = document.getElementById('firm-names-radio-container');
    const customNameInput = document.getElementById('login-custom-name-input');

    if (data.has_name_divergence && data.firm_profiles.length > 0) {
      conflictBox.classList.remove('hidden');
      
      radioContainer.innerHTML = data.firm_profiles.map((fp, i) => {
        const isChecked = (fp.registered_name === data.default_selected_name || i === 0);
        return `
          <label class="flex items-center justify-between p-2 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-indigo-500/50 cursor-pointer transition">
            <div class="flex items-center gap-2">
              <input type="radio" name="selected_central_name" value="${fp.registered_name}" ${isChecked ? 'checked' : ''} class="text-indigo-600 focus:ring-0">
              <div>
                <span class="font-bold text-white text-xs">${fp.registered_name}</span>
                <span class="text-[9px] text-slate-400 block">${fp.firm_name} (${fp.firm_category})</span>
              </div>
            </div>
            <span class="text-[9px] font-bold px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-300">Store Record</span>
          </label>
        `;
      }).join('');

      if (customNameInput) customNameInput.value = data.default_selected_name;
    } else {
      // Single name or new user
      conflictBox.classList.add('hidden');
      if (customNameInput) customNameInput.value = data.default_selected_name;
    }

    showToast(`📲 OTP generated for +91 ${phone}`);
  } catch (err) {
    console.error('OTP request error:', err);
    alert('Error connecting to authentication service');
  } finally {
    showLoadingSpinner(false);
  }
}

function autoFillDemoOtp() {
  const otpInput = document.getElementById('login-otp-input');
  if (otpInput && state.otpSession.demoOtp) {
    otpInput.value = state.otpSession.demoOtp;
    showToast(`Auto-filled OTP: ${state.otpSession.demoOtp}!`);
  }
}

function backToPhoneStep() {
  document.getElementById('login-step-otp').classList.add('hidden');
  document.getElementById('login-step-phone').classList.remove('hidden');
}

async function verifyOtpFlow() {
  const otp = document.getElementById('login-otp-input').value.trim();
  const phone = state.otpSession.phone;

  if (!otp || otp.length < 6) {
    alert('Please enter the 6-digit OTP');
    return;
  }

  // Get selected centralized name
  let selectedName = '';
  const checkedRadio = document.querySelector('input[name="selected_central_name"]:checked');
  if (checkedRadio) selectedName = checkedRadio.value;

  const customName = document.getElementById('login-custom-name-input').value.trim();

  showLoadingSpinner(true);
  try {
    const res = await fetch('/api/auth/verify-otp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        phone: phone,
        otp: otp,
        selected_name: selectedName,
        custom_name: customName
      })
    });

    const data = await res.json();
    if (!data.success) {
      alert(data.message || 'OTP verification failed');
      return;
    }

    state.customer = data.customer;
    state.summary = data.summary;
    state.businessLedger = data.business_ledger;
    state.currentPhone = phone;

    closeModal('login-modal');
    await switchCustomer(phone);
    triggerConfetti();
    showToast(`🎉 Welcome, ${state.customer.name}! Profile centralized across stores.`);
  } catch (err) {
    console.error('OTP verification error:', err);
    alert('Error verifying OTP');
  } finally {
    showLoadingSpinner(false);
  }
}

// ----------------- GOODS RETURN / SURRENDER SIMULATOR ----------------- //

async function submitGoodsReturn() {
  const firmId = document.getElementById('return-firm-select').value;
  const origInvoice = document.getElementById('return-orig-invoice').value.trim();
  const returnAmount = parseFloat(document.getElementById('return-amount-input').value);
  const reason = document.getElementById('return-reason-input').value.trim();

  if (isNaN(returnAmount) || returnAmount <= 0) {
    alert('Please enter a valid positive return amount');
    return;
  }

  showLoadingSpinner(true);
  try {
    const res = await fetch('/api/v1/erp/record-return', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        phone: state.currentPhone,
        firm_id: firmId,
        return_slip_no: `RET-${Math.floor(1000 + Math.random() * 9000)}`,
        original_invoice_no: origInvoice,
        return_amount: returnAmount,
        reason: reason
      })
    });

    const data = await res.json();
    const logBox = document.getElementById('return-result-log');
    logBox.classList.remove('hidden');

    if (data.success) {
      logBox.className = 'mt-3 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-300';
      logBox.innerHTML = `<strong>[RETURN RECORDED]</strong> ${data.message}`;
      state.businessLedger = data.business_ledger;
      renderBusinessLedger();
      showToast(`↩️ Surrender / Return of ₹${returnAmount.toFixed(2)} recorded!`);
      if (typeof LiveSync !== 'undefined' && LiveSync.broadcast) {
        LiveSync.broadcast({ type: 'LEDGER_REFRESH' });
      }
      setTimeout(() => closeModal('return-simulator-modal'), 1200);
    } else {
      logBox.className = 'mt-3 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300';
      logBox.innerHTML = `<strong>[ERROR]</strong> ${data.message}`;
    }
  } catch (err) {
    alert('Failed to connect to return endpoint');
  } finally {
    showLoadingSpinner(false);
  }
}

// ========================================================================= //
//       REAL-TIME MULTI-DEVICE LIVE MIRROR ENGINE (MOBILE ⇄ COMPUTER)        //
// ========================================================================= //

const LiveSync = {
  clientId: 'client_' + Math.random().toString(36).substr(2, 9),
  isMobile: (/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent) || window.innerWidth <= 640),
  ws: null,
  isConnected: false,
  isReceivingRemoteSync: false,
  deviceCount: 1,
  scrollRafId: null,
  pollInterval: null,
  lastEventTime: 0,
  syncActive: true,
  pillTimeout: null,

  init() {
    this.connectWebSocket();
    this.setupScrollSync();
    this.setupInputSync();
    console.log('[LiveSync] Engine initialized. Device mode:', this.isMobile ? 'MOBILE' : 'DESKTOP');
  },

  connectWebSocket() {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname || '127.0.0.1';
      const wsUrl = `${protocol}//${host}:5051`;

      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.updateSyncBadge(true);
        console.log('[LiveSync] Real-time mirror active via WebSocket at', wsUrl);
        if (this.pollInterval) {
          clearInterval(this.pollInterval);
          this.pollInterval = null;
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleIncomingEvent(data);
        } catch (e) {
          console.error('[LiveSync] Error parsing message:', e);
        }
      };

      this.ws.onerror = (err) => {
        console.log('[LiveSync] WebSocket error, starting HTTP fallback');
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.updateSyncBadge(false);
        setTimeout(() => this.connectWebSocket(), 2500);
        this.startHttpFallback();
      };
    } catch (e) {
      console.log('[LiveSync] WebSocket init error, starting HTTP fallback');
      this.startHttpFallback();
    }
  },

  startHttpFallback() {
    if (this.pollInterval) return;
    this.pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/sync/poll?since=${this.lastEventTime}`);
        const data = await res.json();
        if (data.success && data.events) {
          data.events.forEach(evt => {
            if (evt.sourceId !== this.clientId) {
              this.handleIncomingEvent(evt);
            }
            if (evt.serverTime > this.lastEventTime) {
              this.lastEventTime = evt.serverTime;
            }
          });
          if (data.deviceCount) {
            this.updateDeviceCount(data.deviceCount);
          }
        }
      } catch (err) {}
    }, 800);
  },

  broadcast(payload) {
    if (!this.syncActive) return;
    payload.sourceId = this.clientId;
    payload.senderDevice = this.isMobile ? 'MOBILE' : 'DESKTOP';
    payload.timestamp = Date.now();

    const str = JSON.stringify(payload);
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(str);
    } else {
      fetch('/api/sync/broadcast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: str
      }).catch(() => {});
    }
  },

  handleIncomingEvent(data) {
    if (!data || data.sourceId === this.clientId) return;

    switch (data.type) {
      case 'DEVICE_COUNT':
      case 'SYNC_CONNECTED':
        this.updateDeviceCount(data.deviceCount || data.count || 1);
        break;

      case 'SCROLL':
        this.applyRemoteScroll(data);
        break;

      case 'TAB_CHANGE':
        if (data.tab && data.tab !== state.activeTab) {
          switchTab(data.tab, false);
          this.showRemotePill(data.senderDevice === 'MOBILE' ? `📱 Switched to ${data.tab.toUpperCase()}` : `💻 Switched to ${data.tab.toUpperCase()}`);
        }
        break;

      case 'MODAL_OPEN':
        if (data.modalId) {
          openModal(data.modalId, false, data.extra);
          this.showRemotePill(data.senderDevice === 'MOBILE' ? '📱 Opened on Mobile' : '💻 Opened on Computer');
        }
        break;

      case 'MODAL_CLOSE':
        if (data.modalId) {
          closeModal(data.modalId, false);
        } else {
          closeAllModals(false);
        }
        break;

      case 'INPUT_SYNC':
        this.applyRemoteInput(data);
        break;

      case 'CUSTOMER_SYNC':
        if (data.phone && data.phone !== state.currentPhone) {
          switchCustomer(data.phone, false);
          this.showRemotePill(`👤 Switched Profile (+91 ${data.phone})`);
        }
        break;

      case 'SCRATCH_SYNC':
        showToast('🎉 Mystery card scratched on mobile!');
        triggerConfetti();
        refreshWalletSilent();
        break;

      case 'LEDGER_REFRESH':
        refreshWalletSilent();
        this.showRemotePill('📊 Business Activity Updated');
        break;

      case 'FIRM_DETAIL_OPEN':
        if (data.firmId) {
          openFirmDetailModal(data.firmId, false);
          this.showRemotePill('🏪 Store View Synced');
        }
        break;

      case 'WALLET_UPDATED':
      case 'REDEMPTION_COMPLETED':
        if (data.phone === state.currentPhone) {
          triggerConfetti();
          refreshWalletSilent();
          showRedemptionCompletedAlert(data);
          this.showRemotePill(`🎁 Redeemed ₹${data.points_deducted || ''} at ${data.firm_name || 'Store'}`);
        }
        break;

      case 'REDEMPTION_CLAIM_CREATED':
        if (data.phone === state.currentPhone) {
          this.showRemotePill(`⚡ Claim Live at ${data.firm_name || 'Counter'}`);
        }
        break;

      case 'MERCHANT_REDEMPTION_REQUEST':
        const targetClean = (data.phone || '').replace(/[^0-9]/g, '');
        const myClean = (state.currentPhone || '').replace(/[^0-9]/g, '');
        if (targetClean === myClean || (targetClean.length >= 10 && myClean.length >= 10 && (targetClean.endsWith(myClean) || myClean.endsWith(targetClean)))) {
          checkPendingMerchantRequest(state.currentPhone);
          this.showRemotePill(`🎁 Request from ${data.firm_name || 'Counter'}!`);
        }
        break;

      case 'MERCHANT_REQUEST_CANCELLED':
        closeModal('merchant-approval-modal');
        const bReq = document.getElementById('merchant-approval-urgent-banner');
        if (bReq) bReq.classList.add('hidden');
        break;
    }
  },

  setupScrollSync() {
    const vp = document.querySelector('.app-viewport');
    if (!vp) return;

    vp.addEventListener('scroll', () => {
      if (this.isReceivingRemoteSync || !this.syncActive) return;

      if (this.scrollRafId) return;
      this.scrollRafId = requestAnimationFrame(() => {
        this.scrollRafId = null;
        const maxScroll = vp.scrollHeight - vp.clientHeight;
        const scrollPct = maxScroll > 0 ? (vp.scrollTop / maxScroll) : 0;

        this.broadcast({
          type: 'SCROLL',
          scrollTop: vp.scrollTop,
          scrollPct: scrollPct
        });
      });
    }, { passive: true });
  },

  applyRemoteScroll(data) {
    const vp = document.querySelector('.app-viewport');
    if (!vp) return;

    this.isReceivingRemoteSync = true;
    vp.scrollTop = data.scrollTop;
    this.showRemotePill(data.senderDevice === 'MOBILE' ? '📱 Mobile Scrolling...' : '💻 PC Scrolling...');

    setTimeout(() => {
      this.isReceivingRemoteSync = false;
    }, 80);
  },

  setupInputSync() {
    const syncSelector = '#login-phone-input, #login-otp-input, #redeem-points-input, #cashier-code-input, #cashier-bill-amount, #return-amount-input, #return-orig-invoice, #return-reason-input, #login-custom-name-input';

    document.addEventListener('input', (e) => {
      if (this.isReceivingRemoteSync || !this.syncActive) return;
      const target = e.target;
      if (target && target.matches && target.matches(syncSelector)) {
        this.broadcast({
          type: 'INPUT_SYNC',
          elementId: target.id,
          value: target.value
        });
      }
    });

    document.addEventListener('change', (e) => {
      if (this.isReceivingRemoteSync || !this.syncActive) return;
      const target = e.target;
      if (target && target.matches && (target.matches(syncSelector) || target.name === 'selected_central_name' || target.id === 'redeem-firm-select' || target.id === 'return-firm-select')) {
        this.broadcast({
          type: 'INPUT_SYNC',
          elementId: target.id,
          name: target.name,
          value: target.value,
          checked: target.checked
        });
      }
    });
  },

  applyRemoteInput(data) {
    this.isReceivingRemoteSync = true;
    if (data.name === 'selected_central_name') {
      const radio = document.querySelector(`input[name="selected_central_name"][value="${data.value}"]`);
      if (radio) radio.checked = true;
    } else if (data.elementId) {
      const el = document.getElementById(data.elementId);
      if (el) {
        el.value = data.value;
        if (el.tagName === 'SELECT') {
          el.dispatchEvent(new Event('change'));
        }
      }
    }
    setTimeout(() => { this.isReceivingRemoteSync = false; }, 50);
  },

  updateDeviceCount(count) {
    this.deviceCount = count;
    const desktopCountEl = document.getElementById('desktop-device-count');
    const mobileTextEl = document.getElementById('mobile-sync-text');
    const desktopTextEl = document.getElementById('desktop-sync-text');

    const label = count > 1 ? `${count} Devices Synced` : '1 Device Active';
    if (desktopCountEl) desktopCountEl.innerText = `(${label})`;
    if (mobileTextEl) mobileTextEl.innerText = count > 1 ? `Synced (${count})` : 'Live Mirroring';
    if (desktopTextEl) desktopTextEl.innerText = count > 1 ? '📱 Mobile ⇄ 💻 PC Live Synced' : '📱 Mobile ⇄ 💻 PC Mirror Ready';
  },

  updateSyncBadge(connected) {
    const desktopDot = document.getElementById('desktop-sync-dot');
    const mobileDot = document.getElementById('mobile-sync-dot');
    const color = connected ? '#34D399' : '#F59E0B';

    if (desktopDot) desktopDot.style.backgroundColor = color;
    if (mobileDot) mobileDot.style.backgroundColor = color;
  },

  showRemotePill(text) {
    const pill = document.getElementById('remote-sync-pill');
    const pillText = document.getElementById('remote-sync-pill-text');
    if (!pill || !pillText) return;

    pillText.innerText = text;
    pill.style.opacity = '1';
    pill.style.transform = 'translateY(0)';

    clearTimeout(this.pillTimeout);
    this.pillTimeout = setTimeout(() => {
      pill.style.opacity = '0';
      pill.style.transform = 'translateY(-8px)';
    }, 1200);
  }
};

function searchHomeFirms() {
  const query = (document.getElementById('home-firm-search-input')?.value || '').trim().toLowerCase();
  const activeBtn = document.querySelector('.firms-filter-btn.active');
  const cat = activeBtn ? (activeBtn.getAttribute('data-cat') || 'ALL') : 'ALL';

  let list = state.firms || [];
  if (cat !== 'ALL') {
    list = list.filter(f => (f.category || '').toUpperCase().includes(cat) || (cat === 'SUPERMARKET' && (f.name || '').toUpperCase().includes('SUPERMARKET')));
  }

  if (query) {
    list = list.filter(f => 
      (f.name || '').toLowerCase().includes(query) ||
      (f.category || '').toLowerCase().includes(query) ||
      (f.address || '').toLowerCase().includes(query) ||
      (f.tagline || '').toLowerCase().includes(query)
    );
  }

  renderHomeStoresPreview(list);
}

function renderHomeStoresPreview(customList = null) {
  const container = document.getElementById('home-stores-preview-container');
  if (!container) return;

  if ((!state.firms || state.firms.length === 0) && customList === null) {
    loadFirms().then(() => renderHomeStoresPreview());
    return;
  }

  const list = customList !== null ? customList : (state.firms || []);
  if (list.length === 0) {
    container.innerHTML = `
      <div class="p-4 text-center text-slate-400 bg-slate-950 rounded-2xl border border-slate-800 text-xs">
        സ്റ്റോറുകൾ കണ്ടെത്തിയില്ല
      </div>
    `;
    return;
  }

  container.innerHTML = list.slice(0, 4).map(f => {
    let firmPoints = 0;
    if (state.batches && state.batches.length > 0) {
      firmPoints = state.batches
        .filter(b => b.firm_id === f.id && b.points_remaining > 0)
        .reduce((sum, b) => sum + parseFloat(b.points_remaining || 0), 0);
    }
    const icon = f.category_icon === 'fuel' ? '⛽' : (f.category_icon === 'coffee' ? '☕' : (f.category_icon === 'shopping-basket' ? '🧺' : '🛒'));

    return `
      <div class="p-3 bg-slate-950/90 rounded-2xl border border-slate-800 hover:border-emerald-500/50 transition shadow flex items-center justify-between gap-2.5">
        <div class="flex items-center gap-2.5 min-w-0 flex-1">
          <div class="w-10 h-10 rounded-xl flex items-center justify-center text-base font-black text-white shadow" style="background-color: ${f.theme_color}">
            ${icon}
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5">
              <span class="text-xs font-black text-white truncate">${f.name}</span>
              ${f.is_es_pro ? '<span class="text-[8px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.2 rounded font-black">EEYES PRO</span>' : ''}
            </div>
            <div class="text-[10px] text-slate-400 truncate">${f.category} • ${f.address || f.tagline}</div>
          </div>
        </div>
        <button type="button" onclick="openStoreBatchRulesModal('${f.id}')" class="py-1.5 px-2.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 text-white font-extrabold text-[11px] rounded-xl shadow transition cursor-pointer flex items-center gap-1 whitespace-nowrap">
          <span>ബാച്ചുകൾ</span>
          <span>➔</span>
        </button>
      </div>
    `;
  }).join('');
}

function filterHomeFirms(cat, btn) {
  state.homeSelectedCategory = cat;
  document.querySelectorAll('.home-firms-filter-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  searchHomeFirms();
}


// ==================== SETTINGS & SECURITY & SAFE LOGOUT ==================== //

async function openSettingsModal() {
  const phone = state.currentCustomerPhone || '9656360650';
  try {
    const res = await fetch(`/api/customer/${phone}/settings`);
    const data = await res.json();
    if (data.success && data.settings) {
      const s = data.settings;
      const uidEl = document.getElementById('settings-op-id');
      if (uidEl) uidEl.textContent = s.omnipoints_id || `OP-${phone}`;

      const eyEl = document.getElementById('settings-ey-id');
      if (eyEl) eyEl.textContent = s.eeyes_account_no || `EY-${phone.slice(-4)}`;

      const phoneEl = document.getElementById('settings-phone');
      if (phoneEl) phoneEl.textContent = `+91 ${phone}`;

      const nameInput = document.getElementById('settings-name-input');
      if (nameInput) nameInput.value = s.name || '';

      const uNameInput = document.getElementById('settings-user-id-input');
      if (uNameInput) uNameInput.value = s.user_id || '';

      const pinInput = document.getElementById('settings-pin-input');
      if (pinInput) pinInput.value = s.quick_pin || '';

      const addrInput = document.getElementById('settings-address-input');
      if (addrInput) addrInput.value = s.address || '';

      const cityInput = document.getElementById('settings-city-input');
      if (cityInput) cityInput.value = s.city || '';

      const pinCodeInput = document.getElementById('settings-pincode-input');
      if (pinCodeInput) pinCodeInput.value = s.pincode || '';

      const bioToggle = document.getElementById('settings-bio-toggle');
      if (bioToggle) bioToggle.checked = Boolean(s.bio_unlock);

      const notifToggle = document.getElementById('settings-notif-toggle');
      if (notifToggle) notifToggle.checked = Boolean(s.notifications_enabled);

      // Render linked store badges
      const storesContainer = document.getElementById('settings-linked-stores');
      if (storesContainer && s.linked_firms) {
        storesContainer.innerHTML = s.linked_firms.map(f => `
          <div class="flex items-center justify-between p-2 rounded-xl bg-slate-800/80 border border-slate-700/80 text-[11px]">
            <div class="flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${f.theme_color || '#10B981'}"></span>
              <span class="font-bold text-white">${f.name}</span>
            </div>
            <span class="text-[10px] font-mono font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-lg border border-emerald-500/20">${f.account_no || 'EY-SYNC'}</span>
          </div>
        `).join('');
      }
    }
  } catch (e) {
    console.warn('Error fetching settings:', e);
  }
  openModal('settings-modal');
}

async function saveCustomerSettings() {
  const phone = state.currentCustomerPhone || '9656360650';
  const name = document.getElementById('settings-name-input')?.value || '';
  const userId = document.getElementById('settings-user-id-input')?.value || '';
  const password = document.getElementById('settings-password-input')?.value || '';
  const quickPin = document.getElementById('settings-pin-input')?.value || '';
  const address = document.getElementById('settings-address-input')?.value || '';
  const city = document.getElementById('settings-city-input')?.value || '';
  const pincode = document.getElementById('settings-pincode-input')?.value || '';
  const bioUnlock = document.getElementById('settings-bio-toggle')?.checked ?? true;
  const notifications = document.getElementById('settings-notif-toggle')?.checked ?? true;

  try {
    const res = await fetch(`/api/customer/${phone}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        user_id: userId,
        password,
        quick_pin: quickPin,
        address,
        city,
        pincode,
        bio_unlock: bioUnlock,
        notifications_enabled: notifications
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast('✅ സെറ്റിംഗ്സുകളും പാസ്‌വേഡും സുരക്ഷിതമായി സേവ് ചെയ്തു!');
      // Update header customer name if changed
      const headerName = document.getElementById('header-user-name');
      if (headerName && name) headerName.textContent = name;
      closeModal('settings-modal');
    } else {
      showToast('⚠️ സേവ് ചെയ്യാൻ കഴിഞ്ഞില്ല: ' + (data.message || 'Error'), 'error');
    }
  } catch (e) {
    showToast('⚠️ സെർവർ പിശക്: ' + e.message, 'error');
  }
}

function togglePasswordVisibility(inputId, btnEl) {
  const input = document.getElementById(inputId);
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    if (btnEl) btnEl.innerHTML = '🙈';
  } else {
    input.type = 'password';
    if (btnEl) btnEl.innerHTML = '👁️';
  }
}

function copyToClipboard(text, feedbackId) {
  navigator.clipboard.writeText(text).then(() => {
    const feedback = document.getElementById(feedbackId);
    if (feedback) {
      const originalText = feedback.innerHTML;
      feedback.innerHTML = '✅';
      setTimeout(() => { feedback.innerHTML = originalText; }, 2000);
    }
    showToast(`📋 കോപ്പി ചെയ്തു: ${text}`);
  }).catch(() => {
    showToast(`📋 ${text}`);
  });
}

function promptSafeLogout() {
  closeModal('settings-modal');
  openModal('logout-confirm-modal');
}

function cancelLogout() {
  closeModal('logout-confirm-modal');
  showToast('🛡️ ലോഗിൻ സെഷൻ സുരക്ഷിതമായി നിലനിർത്തി!');
}

function confirmSafeLogout() {
  closeModal('logout-confirm-modal');
  logoutCustomer();
}

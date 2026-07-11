/**
 * NSE Option Chain Clone - BSM Calculator & Dynamic Solver Engine
 */

// Global State
let appState = {
    symbol: "NIFTY",
    marketSpot: 0.0,
    optionChains: {},  // Map of expiry_date -> list of OptionChainRow
    expiryDates: [],
    selectedExpiry: "",
    selectedStrike: "ALL",
    // Model parameters
    spot: 0.0,
    volatility: 12.8,
    daysToExpiry: 5,
    riskFreeRate: 6.50,
    dividendYield: 1.20,
    // ATM Option Strike Info
    atmStrike: 0.0
};

// WebSocket and inspection states
let currentSocket = null;
let activeSocketSymbol = null;
let activeInspectedStrike = null;

// DOM Elements
const elements = {
    symbolSearchInput: document.getElementById("symbol-search-input"),
    searchSuggestions: document.getElementById("search-suggestions"),
    expirySelect: document.getElementById("expiry-select"),
    strikeSelect: document.getElementById("strike-select"),
    underlyingSymbol: document.getElementById("underlying-symbol"),
    underlyingPrice: document.getElementById("underlying-price"),
    underlyingTime: document.getElementById("underlying-time"),
    reloadBtn: document.getElementById("reload-btn"),
    downloadCsvBtn: document.getElementById("download-csv-btn"),
    
    // BSM Controls
    bsmSpot: document.getElementById("bsm-spot"),
    bsmSpotSlider: document.getElementById("bsm-spot-slider"),
    spotCurrency: document.getElementById("spot-currency"),
    spotMinLbl: document.getElementById("spot-min-lbl"),
    spotMaxLbl: document.getElementById("spot-max-lbl"),
    
    bsmVol: document.getElementById("bsm-vol"),
    bsmVolSlider: document.getElementById("bsm-vol-slider"),
    
    bsmDays: document.getElementById("bsm-days"),
    bsmDaysSlider: document.getElementById("bsm-days-slider"),
    
    bsmRate: document.getElementById("bsm-rate"),
    bsmRateSlider: document.getElementById("bsm-rate-slider"),
    
    bsmDiv: document.getElementById("bsm-div"),
    bsmDivSlider: document.getElementById("bsm-div-slider"),
    
    resetMarketBtn: document.getElementById("reset-market-btn"),
    
    // ATM Outputs
    atmStrikeVal: document.getElementById("atm-strike-val"),
    atmCallPrice: document.getElementById("atm-call-price"),
    atmCallDelta: document.getElementById("atm-call-delta"),
    atmCallTheta: document.getElementById("atm-call-theta"),
    atmCallRho: document.getElementById("atm-call-rho"),
    
    atmGamma: document.getElementById("atm-gamma"),
    atmVega: document.getElementById("atm-vega"),
    
    atmPutPrice: document.getElementById("atm-put-price"),
    atmPutDelta: document.getElementById("atm-put-delta"),
    atmPutTheta: document.getElementById("atm-put-theta"),
    atmPutRho: document.getElementById("atm-put-rho"),
    
    // Table Body
    tableBody: document.getElementById("option-chain-tbody"),
    
    // Modal
    greeksModal: document.getElementById("greeks-modal"),
    modalClose: document.getElementById("modal-close"),
    modalStrikePrice: document.getElementById("modal-strike-price"),
    modalCLtp: document.getElementById("modal-c-ltp"),
    modalCBsVal: document.getElementById("modal-c-bs-val"),
    modalCEdge: document.getElementById("modal-c-edge"),
    modalCDelta: document.getElementById("modal-c-delta"),
    modalCGamma: document.getElementById("modal-c-gamma"),
    modalCVega: document.getElementById("modal-c-vega"),
    modalCTheta: document.getElementById("modal-c-theta"),
    modalCRho: document.getElementById("modal-c-rho"),
    
    modalPLtp: document.getElementById("modal-p-ltp"),
    modalPBsVal: document.getElementById("modal-p-bs-val"),
    modalPEdge: document.getElementById("modal-p-edge"),
    modalPDelta: document.getElementById("modal-p-delta"),
    modalPGamma: document.getElementById("modal-p-gamma"),
    modalPVega: document.getElementById("modal-p-vega"),
    modalPTheta: document.getElementById("modal-p-theta"),
    modalPRho: document.getElementById("modal-p-rho"),
    
    modalInSpot: document.getElementById("modal-in-spot"),
    modalInVol: document.getElementById("modal-in-vol"),
    modalInDays: document.getElementById("modal-in-days"),
    modalInRate: document.getElementById("modal-in-rate"),
    modalInDiv: document.getElementById("modal-in-div"),
    modalD1: document.getElementById("modal-d1"),
    modalD2: document.getElementById("modal-d2"),
    modalNd1: document.getElementById("modal-nd1"),
    modalNd2: document.getElementById("modal-nd2"),
    
    // Info and Regulatory modal elements
    userManualBtn: document.getElementById("user-manual-btn"),
    termsBtn: document.getElementById("terms-btn"),
    infoModal: document.getElementById("info-modal"),
    infoModalClose: document.getElementById("info-modal-close")
};

// ----------------------------------------------------
// Black-Scholes-Merton Pricing Formula Math Block
// ----------------------------------------------------

/**
 * Standard standard normal probability density function
 */
function ndensity(x) {
    return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
}

/**
 * High-precision Hastings approximation for cumulative normal distribution function
 */
function cndist(x) {
    const a1 = 0.319381530;
    const a2 = -0.356563782;
    const a3 = 1.781477937;
    const a4 = -1.821255978;
    const a5 = 1.330274429;
    const L = Math.abs(x);
    const K = 1.0 / (1.0 + 0.2316419 * L);
    const cnd = 1.0 - 1.0 / Math.sqrt(2 * Math.PI) * Math.exp(-L * L / 2) * 
        (a1 * K + a2 * Math.pow(K, 2) + a3 * Math.pow(K, 3) + a4 * Math.pow(K, 4) + a5 * Math.pow(K, 5));
    return x < 0 ? 1.0 - cnd : cnd;
}

/**
 * Black-Scholes-Merton analytic pricer and greeks calculation
 */
function calculateBSM(S, K, T_days, r_pct, sigma_pct, q_pct) {
    // Conversions
    const T = Math.max(T_days, 0.001) / 365.0; // Avoid division by zero
    const r = r_pct / 100.0;
    const sigma = sigma_pct / 100.0;
    const q = q_pct / 100.0;

    let d1, d2, Nd1, Nd2, NminusD1, NminusD2, nd1Val;
    
    try {
        d1 = (Math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T));
        d2 = d1 - sigma * Math.sqrt(T);
        Nd1 = cndist(d1);
        Nd2 = cndist(d2);
        NminusD1 = cndist(-d1);
        NminusD2 = cndist(-d2);
        nd1Val = ndensity(d1);
    } catch (e) {
        return {
            call: 0.0, put: 0.0,
            deltaCall: 0.0, deltaPut: 0.0,
            gamma: 0.0, vega: 0.0,
            thetaCall: 0.0, thetaPut: 0.0,
            rhoCall: 0.0, rhoPut: 0.0,
            d1: 0, d2: 0, nd1: 0, nd2: 0
        };
    }

    // Call and Put Prices
    const callPrice = S * Math.exp(-q * T) * Nd1 - K * Math.exp(-r * T) * Nd2;
    const putPrice = K * Math.exp(-r * T) * NminusD2 - S * Math.exp(-q * T) * NminusD1;

    // Greeks calculations
    const deltaCall = Math.exp(-q * T) * Nd1;
    const deltaPut = -Math.exp(-q * T) * NminusD1;
    
    const gamma = (Math.exp(-q * T) * nd1Val) / (S * sigma * Math.sqrt(T));
    
    // Vega per 1% change in volatility
    const vega = (S * Math.exp(-q * T) * Math.sqrt(T) * nd1Val) / 100.0;
    
    // Theta per calendar day decay
    const term1 = -(S * Math.exp(-q * T) * nd1Val * sigma) / (2 * Math.sqrt(T));
    const term2Call = r * K * Math.exp(-r * T) * Nd2;
    const term3Call = q * S * Math.exp(-q * T) * Nd1;
    const thetaCall = (term1 - term2Call + term3Call) / 365.0;

    const term2Put = r * K * Math.exp(-r * T) * NminusD2;
    const term3Put = q * S * Math.exp(-q * T) * NminusD1;
    const thetaPut = (term1 + term2Put - term3Put) / 365.0;

    // Rho per 1% change in risk-free rate
    const rhoCall = (K * T * Math.exp(-r * T) * Nd2) / 100.0;
    const rhoPut = (-K * T * Math.exp(-r * T) * NminusD2) / 100.0;

    return {
        call: Math.max(callPrice, 0.0),
        put: Math.max(putPrice, 0.0),
        deltaCall: deltaCall,
        deltaPut: deltaPut,
        gamma: gamma,
        vega: vega,
        thetaCall: thetaCall,
        thetaPut: thetaPut,
        rhoCall: rhoCall,
        rhoPut: rhoPut,
        d1: d1,
        d2: d2,
        nd1: Nd1,
        nd2: Nd2
    };
}

// ----------------------------------------------------
// UI Logic, Bindings & API Integration Block
// ----------------------------------------------------

/**
 * Format numeric value with commas as thousands separators and fixed decimals
 */
function formatNumber(num, decimals = 2, defaultVal = "-") {
    if (num === null || num === undefined || isNaN(num)) return defaultVal;
    return Number(num).toLocaleString('en-IN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

/**
 * Synchronize slider input value with numeric input field
 */
function bindSlider(numInput, sliderInput, stateProp, callback) {
    numInput.addEventListener("input", (e) => {
        let val = parseFloat(e.target.value);
        if (isNaN(val)) return;
        
        // Update state and slider without clamping on every keystroke
        sliderInput.value = val;
        appState[stateProp] = val;
        if (callback) callback();
    });
    
    numInput.addEventListener("blur", (e) => {
        let val = parseFloat(e.target.value);
        if (isNaN(val)) return;
        
        // Clamp only on blur
        const min = parseFloat(sliderInput.min);
        const max = parseFloat(sliderInput.max);
        if (val < min) val = min;
        if (val > max) val = max;
        
        numInput.value = val;
        sliderInput.value = val;
        appState[stateProp] = val;
        if (callback) callback();
    });
    
    const updateFromSlider = (e) => {
        let val = parseFloat(e.target.value);
        numInput.value = val;
        appState[stateProp] = val;
        if (callback) callback();
    };
    sliderInput.addEventListener("input", updateFromSlider);
    sliderInput.addEventListener("change", updateFromSlider);
}

let debounceTimer;
let activeSuggestionIndex = -1;
let currentSuggestions = [];

/**
 * Setup search and autocomplete bindings for the premium search component
 */
function setupAutocomplete() {
    const input = elements.symbolSearchInput;
    const container = elements.searchSuggestions;

    if (!input || !container) return;

    // Trigger search on input focus
    input.addEventListener("focus", () => {
        fetchSuggestions(input.value);
    });

    // Handle typing with debouncing (200ms)
    input.addEventListener("input", (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            fetchSuggestions(e.target.value);
        }, 200);
    });

    // Handle keyboard navigation
    input.addEventListener("keydown", (e) => {
        const items = container.querySelectorAll(".suggestion-item");

        if (e.key === "ArrowDown") {
            if (!items.length) return;
            e.preventDefault();
            activeSuggestionIndex = (activeSuggestionIndex + 1) % items.length;
            highlightSuggestion(items);
        } else if (e.key === "ArrowUp") {
            if (!items.length) return;
            e.preventDefault();
            activeSuggestionIndex = (activeSuggestionIndex - 1 + items.length) % items.length;
            highlightSuggestion(items);
        } else if (e.key === "Enter") {
            e.preventDefault();
            if (activeSuggestionIndex >= 0 && activeSuggestionIndex < items.length) {
                selectSuggestion(currentSuggestions[activeSuggestionIndex]);
            } else {
                const typedVal = input.value.trim().toUpperCase();
                if (typedVal) {
                    closeSuggestions();
                    isFirstLoad = true;
                    fetchTickerData(typedVal);
                }
            }
        } else if (e.key === "Escape") {
            closeSuggestions();
        }
    });

    // Close suggestions dropdown when clicking outside
    document.addEventListener("click", (e) => {
        if (!input.contains(e.target) && !container.contains(e.target)) {
            closeSuggestions();
        }
    });
}

async function fetchSuggestions(query) {
    try {
        const res = await fetch(`/v1/symbols/search?q=${encodeURIComponent(query)}`);
        if (!res.ok) throw new Error("Search failed");
        const data = await res.json();
        currentSuggestions = data.results || [];
        renderSuggestions(currentSuggestions);
    } catch (err) {
        console.error("Autocomplete search error: ", err);
    }
}

function renderSuggestions(suggestions) {
    const container = elements.searchSuggestions;
    if (!container) return;
    
    container.innerHTML = "";
    activeSuggestionIndex = -1;

    if (suggestions.length === 0) {
        container.classList.add("hidden");
        return;
    }

    suggestions.forEach((item, index) => {
        const div = document.createElement("div");
        div.className = "suggestion-item";
        div.innerHTML = `
            <div class="suggestion-left">
                <span class="suggestion-symbol">${item.symbol}</span>
                <span class="suggestion-name">${item.name}</span>
            </div>
            <span class="suggestion-type">${item.type}</span>
        `;
        
        div.addEventListener("click", () => {
            selectSuggestion(item);
        });

        container.appendChild(div);
    });

    container.classList.remove("hidden");
}

function highlightSuggestion(items) {
    items.forEach((item, idx) => {
        if (idx === activeSuggestionIndex) {
            item.classList.add("active");
            item.scrollIntoView({ block: "nearest" });
        } else {
            item.classList.remove("active");
        }
    });
}

function selectSuggestion(item) {
    elements.symbolSearchInput.value = item.symbol;
    closeSuggestions();
    isFirstLoad = true;
    fetchTickerData(item.symbol);
}

function closeSuggestions() {
    if (elements.searchSuggestions) {
        elements.searchSuggestions.classList.add("hidden");
    }
    activeSuggestionIndex = -1;
}


/**
 * Query live Redis or mock analytics parameters for selected instrument
 */
async function fetchTickerData(symbol) {
    try {
        // Show loading state in the table
        elements.tableBody.innerHTML = `<tr><td colspan="25" style="text-align: center; padding: 40px; font-size: 14px; font-weight: 700; color: #1a237e; background-color: rgba(26, 35, 126, 0.04);">Loading option chain for ${symbol}...</td></tr>`;
        
        const res = await fetch(`/v1/pricer/ticker/${symbol}`);
        if (!res.ok) throw new Error(`Ticker query failed for ${symbol}`);
        
        const data = await res.json();
        
        // Load data properties into state
        appState.symbol = data.symbol;
        appState.marketSpot = data.stock_price;
        appState.optionChains = data.option_chains || {};
        appState.expiryDates = data.expiry_dates || [];
        
        // Bind dynamic model values
        appState.spot = data.stock_price;
        appState.volatility = data.implied_volatility || 15.0;
        appState.daysToExpiry = data.expiry_days || 30;
        appState.riskFreeRate = data.risk_free_rate || 6.50;
        appState.dividendYield = data.dividend_yield || 0.0;
        
        // Pick nearest expiry as active default
        if (appState.expiryDates.length > 0) {
            appState.selectedExpiry = appState.expiryDates[0];
        } else {
            appState.selectedExpiry = "";
        }
        
        // Reset strike filters
        appState.selectedStrike = "ALL";
        
        // Update Info Labels
        elements.underlyingSymbol.textContent = appState.symbol;
        elements.underlyingPrice.textContent = formatNumber(appState.marketSpot, 2);
        
        const now = new Date(data.generated_at || new Date());
        elements.underlyingTime.textContent = now.toLocaleDateString("en-IN", {
            day: "2-digit", month: "short", year: "numeric"
        }) + " " + now.toLocaleTimeString("en-IN");
        
        // Update Slider limits and values
        elements.spotCurrency.textContent = (appState.symbol === "AAPL" || appState.symbol === "TSLA") ? "USD" : "INR";
        const spotMin = Math.round(appState.marketSpot * 0.7 * 100) / 100;
        const spotMax = Math.round(appState.marketSpot * 1.3 * 100) / 100;
        
        elements.bsmSpotSlider.min = spotMin;
        elements.bsmSpotSlider.max = spotMax;
        elements.bsmSpotSlider.step = Math.round((spotMax - spotMin) / 200 * 100) / 100 || 0.05;
        
        elements.spotMinLbl.textContent = formatNumber(spotMin, 2);
        elements.spotMaxLbl.textContent = formatNumber(spotMax, 2);
        
        // Update Numeric Control values
        elements.bsmSpot.value = appState.spot;
        elements.bsmSpotSlider.value = appState.spot;
        
        elements.bsmVol.value = appState.volatility;
        elements.bsmVolSlider.value = appState.volatility;
        
        elements.bsmDays.value = appState.daysToExpiry;
        elements.bsmDaysSlider.value = appState.daysToExpiry;
        
        elements.bsmRate.value = appState.riskFreeRate;
        elements.bsmRateSlider.value = appState.riskFreeRate;
        
        elements.bsmDiv.value = appState.dividendYield;
        elements.bsmDivSlider.value = appState.dividendYield;
        
        // Update Expiry Date and Strike Price filters dropdowns
        populateDropdowns();
        
        // Recalculate and render Option Chain table grid
        recalculateAndRender();
        
        // Setup/Switch WebSocket for real-time updates
        if (!currentSocket || appState.symbol !== activeSocketSymbol) {
            setupWebSocket(appState.symbol);
        }
    } catch (e) {
        console.error("Error fetching options parameters: ", e);
        elements.tableBody.innerHTML = `<tr><td colspan="25" style="text-align: center; padding: 40px; font-size: 14px; font-weight: 700; color: #dc2626; background-color: rgba(220, 38, 38, 0.04);">Error: Failed to fetch option chain for "${symbol}". Instrument may not exist or has no derivatives data.</td></tr>`;
    }
}

/**
 * Setup WebSocket connection for real-time updates
 */
function setupWebSocket(symbol) {
    if (currentSocket) {
        try {
            currentSocket.close(1000, "Switching symbol");
        } catch (e) {
            console.error("Error closing existing socket:", e);
        }
        currentSocket = null;
    }
    
    const loc = window.location;
    const wsProtocol = loc.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${loc.host}/v1/ws/${symbol}`;
    
    console.log(`Connecting WebSocket for ${symbol} to: ${wsUrl}`);
    const socket = new WebSocket(wsUrl);
    currentSocket = socket;
    activeSocketSymbol = symbol;
    
    socket.onopen = () => {
        console.log(`WebSocket connected for symbol: ${symbol}`);
    };
    
    socket.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === "price") {
                console.log(`Real-time price update received for ${symbol}:`, msg.data);
                const priceData = msg.data;
                if (priceData && priceData.last_price) {
                    const newPrice = priceData.last_price;
                    const isSpotSynced = Math.abs(appState.spot - appState.marketSpot) < 0.01 || appState.spot === 0;
                    
                    appState.marketSpot = newPrice;
                    elements.underlyingPrice.textContent = formatNumber(newPrice, 2);
                    
                    const updateTime = priceData.last_updated ? new Date(priceData.last_updated) : new Date();
                    elements.underlyingTime.textContent = updateTime.toLocaleDateString("en-IN", {
                        day: "2-digit", month: "short", year: "numeric"
                    }) + " " + updateTime.toLocaleTimeString("en-IN");
                    
                    const spotMin = Math.round(appState.marketSpot * 0.7 * 100) / 100;
                    const spotMax = Math.round(appState.marketSpot * 1.3 * 100) / 100;
                    
                    elements.bsmSpotSlider.min = spotMin;
                    elements.bsmSpotSlider.max = spotMax;
                    elements.spotMinLbl.textContent = formatNumber(spotMin, 2);
                    elements.spotMaxLbl.textContent = formatNumber(spotMax, 2);
                    
                    if (isSpotSynced) {
                        appState.spot = newPrice;
                        elements.bsmSpot.value = appState.spot;
                        elements.bsmSpotSlider.value = appState.spot;
                    }
                    
                    recalculateAndRender();
                    updateGreeksModalIfOpen();
                }
            } else if (msg.type === "options") {
                console.log(`Real-time options update received for ${symbol}`);
                fetchTickerDataBackground(symbol);
            }
        } catch (err) {
            console.error("Error parsing WebSocket message:", err);
        }
    };
    
    socket.onclose = (event) => {
        console.log(`WebSocket closed for symbol: ${symbol}. Code: ${event.code}`);
        if (currentSocket === socket) {
            currentSocket = null;
            activeSocketSymbol = null;
            
            if (event.code !== 1000 && appState.symbol === symbol) {
                console.log(`Attempting reconnection in 5s...`);
                setTimeout(() => {
                    if (appState.symbol === symbol) {
                        setupWebSocket(symbol);
                    }
                }, 5000);
            }
        }
    };
    
    socket.onerror = (err) => {
        console.error("WebSocket error:", err);
    };
}

/**
 * Silently fetch ticker data in the background and update UI
 */
async function fetchTickerDataBackground(symbol) {
    try {
        const res = await fetch(`/v1/pricer/ticker/${symbol}`);
        if (!res.ok) throw new Error(`Background ticker query failed for ${symbol}`);
        
        const data = await res.json();
        
        if (data.symbol !== appState.symbol) return;
        
        // Check if user is synced with market spot price
        const isSpotSynced = Math.abs(appState.spot - appState.marketSpot) < 0.01 || appState.spot === 0;
        
        appState.marketSpot = data.stock_price;
        appState.optionChains = data.option_chains || {};
        
        elements.underlyingPrice.textContent = formatNumber(appState.marketSpot, 2);
        
        const now = new Date(data.generated_at || new Date());
        elements.underlyingTime.textContent = now.toLocaleDateString("en-IN", {
            day: "2-digit", month: "short", year: "numeric"
        }) + " " + now.toLocaleTimeString("en-IN");
        
        const spotMin = Math.round(appState.marketSpot * 0.7 * 100) / 100;
        const spotMax = Math.round(appState.marketSpot * 1.3 * 100) / 100;
        
        elements.bsmSpotSlider.min = spotMin;
        elements.bsmSpotSlider.max = spotMax;
        elements.spotMinLbl.textContent = formatNumber(spotMin, 2);
        elements.spotMaxLbl.textContent = formatNumber(spotMax, 2);
        
        if (isSpotSynced) {
            appState.spot = data.stock_price;
            elements.bsmSpot.value = appState.spot;
            elements.bsmSpotSlider.value = appState.spot;
        }
        
        recalculateAndRender();
        updateGreeksModalIfOpen();
    } catch (e) {
        console.error("Error in background options update:", e);
    }
}

/**
 * Refresh Greeks details modal if open
 */
function updateGreeksModalIfOpen() {
    if (activeInspectedStrike !== null && elements.greeksModal.classList.contains("show")) {
        openStrikeModal(activeInspectedStrike);
    }
}

/**
 * Populate Expiry date dropdown options dynamically
 */
function populateDropdowns() {
    // 1. Expiry Dates Select
    elements.expirySelect.innerHTML = "";
    if (appState.expiryDates.length === 0) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "No Expiry";
        elements.expirySelect.appendChild(opt);
    } else {
        appState.expiryDates.forEach(dateStr => {
            const opt = document.createElement("option");
            opt.value = dateStr;
            
            // Format date beautifully (e.g. 04-Jun-2026)
            try {
                const dt = new Date(dateStr);
                const day = String(dt.getDate()).padStart(2, '0');
                const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
                const monthStr = months[dt.getMonth()];
                const year = dt.getFullYear();
                opt.textContent = `${day}-${monthStr}-${year}`;
            } catch (e) {
                opt.textContent = dateStr;
            }
            
            if (dateStr === appState.selectedExpiry) {
                opt.selected = true;
            }
            elements.expirySelect.appendChild(opt);
        });
    }

    // 2. Strike Price Filter Dropdown
    elements.strikeSelect.innerHTML = '<option value="ALL">Select</option>';
    const chainRows = appState.optionChains[appState.selectedExpiry] || [];
    chainRows.forEach(row => {
        const opt = document.createElement("option");
        opt.value = row.strike_price;
        opt.textContent = formatNumber(row.strike_price, 0);
        elements.strikeSelect.appendChild(opt);
    });
}

/**
 * Locate ATM strike and calculate option chain values and dynamic layouts
 */
function recalculateAndRender() {
    const chainRows = appState.optionChains[appState.selectedExpiry] || [];
    if (chainRows.length === 0) {
        const symbolText = appState.symbol ? appState.symbol : "selected instrument";
        elements.tableBody.innerHTML = `<tr><td colspan="25" style="text-align: center; padding: 40px; font-size: 14px; font-weight: 700; color: #ea580c; background-color: rgba(234, 88, 12, 0.04);">Option chain is not available for ${symbolText} in the Indian market.</td></tr>`;
        return;
    }

    // 1. Locate ATM strike (closest to Spot Price)
    let minDiff = Infinity;
    let atmStrike = 0.0;
    chainRows.forEach(row => {
        const diff = Math.abs(row.strike_price - appState.spot);
        if (diff < minDiff) {
            minDiff = diff;
            atmStrike = row.strike_price;
        }
    });
    appState.atmStrike = atmStrike;
    elements.atmStrikeVal.textContent = formatNumber(atmStrike, 0);

    // 2. Compute ATM Analytics
    const atmMetrics = calculateBSM(
        appState.spot,
        atmStrike,
        appState.daysToExpiry,
        appState.riskFreeRate,
        appState.volatility,
        appState.dividendYield
    );

    // Bind metrics labels in control card
    elements.atmCallPrice.textContent = formatNumber(atmMetrics.call, 2);
    elements.atmCallDelta.textContent = formatNumber(atmMetrics.deltaCall, 4);
    elements.atmCallTheta.textContent = formatNumber(atmMetrics.thetaCall, 4);
    elements.atmCallRho.textContent = formatNumber(atmMetrics.rhoCall, 4);

    elements.atmGamma.textContent = formatNumber(atmMetrics.gamma, 6);
    elements.atmVega.textContent = formatNumber(atmMetrics.vega, 4);

    elements.atmPutPrice.textContent = formatNumber(atmMetrics.put, 2);
    elements.atmPutDelta.textContent = formatNumber(atmMetrics.deltaPut, 4);
    elements.atmPutTheta.textContent = formatNumber(atmMetrics.thetaPut, 4);
    elements.atmPutRho.textContent = formatNumber(atmMetrics.rhoPut, 4);

    // 3. Render Option Chain table body
    elements.tableBody.innerHTML = "";
    
    // Filter strikes if select filter is active
    let rowsToRender = chainRows;
    if (appState.selectedStrike !== "ALL") {
        const sVal = parseFloat(appState.selectedStrike);
        rowsToRender = chainRows.filter(r => Math.abs(r.strike_price - sVal) < 0.01);
    }

    rowsToRender.forEach(row => {
        const strike = row.strike_price;
        const isATM = strike === atmStrike;
        
        // Calculate BSM values for specific strike
        // Use smile volatility (smile formula or parsed iv from option chains)
        const callIv = row.call?.iv || appState.volatility;
        const putIv = row.put?.iv || appState.volatility;
        
        const callBS = calculateBSM(appState.spot, strike, appState.daysToExpiry, appState.riskFreeRate, callIv, appState.dividendYield);
        const putBS = calculateBSM(appState.spot, strike, appState.daysToExpiry, appState.riskFreeRate, putIv, appState.dividendYield);

        const tr = document.createElement("tr");
        if (isATM) tr.className = "atm-strike-row";

        // ITM Shading: Calls ITM if strike < spot, Puts ITM if strike > spot
        const callItmClass = strike < appState.spot ? "itm-shaded" : "";
        const putItmClass = strike > appState.spot ? "itm-shaded" : "";

        // Net Change style helpers
        const cChgClass = row.call?.chng < 0 ? "negative-val" : (row.call?.chng > 0 ? "positive-val" : "");
        const pChgClass = row.put?.chng < 0 ? "negative-val" : (row.put?.chng > 0 ? "positive-val" : "");

        // Color coding for BSM Prices based on comparison with LTP (market price)
        let callBsClass = "";
        let callBsTitle = "BSM Theoretical Price";
        if (row.call?.ltp && callBS.call) {
            const edge = callBS.call - row.call.ltp;
            if (edge > 0.05) {
                callBsClass = "bs-underpriced";
                callBsTitle = `BSM Price (${formatNumber(callBS.call, 2)}) > LTP (${formatNumber(row.call.ltp, 2)}) - Option is underpriced (Theoretical Edge: +${formatNumber(edge, 2)})`;
            } else if (edge < -0.05) {
                callBsClass = "bs-overpriced";
                callBsTitle = `BSM Price (${formatNumber(callBS.call, 2)}) < LTP (${formatNumber(row.call.ltp, 2)}) - Option is overpriced (Theoretical Edge: ${formatNumber(edge, 2)})`;
            }
        }

        let putBsClass = "";
        let putBsTitle = "BSM Theoretical Price";
        if (row.put?.ltp && putBS.put) {
            const edge = putBS.put - row.put.ltp;
            if (edge > 0.05) {
                putBsClass = "bs-underpriced";
                putBsTitle = `BSM Price (${formatNumber(putBS.put, 2)}) > LTP (${formatNumber(row.put.ltp, 2)}) - Option is underpriced (Theoretical Edge: +${formatNumber(edge, 2)})`;
            } else if (edge < -0.05) {
                putBsClass = "bs-overpriced";
                putBsTitle = `BSM Price (${formatNumber(putBS.put, 2)}) < LTP (${formatNumber(row.put.ltp, 2)}) - Option is overpriced (Theoretical Edge: ${formatNumber(edge, 2)})`;
            }
        }

        tr.innerHTML = `
            <!-- CALLS -->
            <td class="chart-cell">
                <button class="chart-icon-btn" title="View Chart" onclick="openStrikeModal(${strike})">
                    <svg viewBox="0 0 24 24" width="12" height="12">
                        <path d="M5 9.2h3V19H5zM10.5 5h3v14h-3zm5.5 8h3v6h-3z"/>
                    </svg>
                </button>
            </td>
            <td class="${callItmClass}">${formatNumber(row.call?.oi, 0, "-")}</td>
            <td class="${callItmClass} ${row.call?.chng_in_oi < 0 ? 'negative-val' : ''}">${formatNumber(row.call?.chng_in_oi, 0, "-")}</td>
            <td class="${callItmClass}">${formatNumber(row.call?.volume, 0, "-")}</td>
            <td class="${callItmClass}">${formatNumber(row.call?.iv, 2, "-")}</td>
            <td class="${callItmClass} bs-field ${callBsClass}" title="${callBsTitle}">${formatNumber(callBS.call, 2)}</td>
            <td class="${callItmClass} link-blue" onclick="openStrikeModal(${strike})">${formatNumber(row.call?.ltp, 2, "-")}</td>
            <td class="${callItmClass} ${cChgClass}">${formatNumber(row.call?.chng, 2, "-")}</td>
            <td class="${callItmClass}">${formatNumber(row.call?.bid_qty, 0, "-")}</td>
            <td class="${callItmClass}">${formatNumber(row.call?.bid, 2, "-")}</td>
            <td class="${callItmClass}">${formatNumber(row.call?.ask, 2, "-")}</td>
            <td class="${callItmClass}">${formatNumber(row.call?.ask_qty, 0, "-")}</td>
            
            <!-- CENTER STRIKE -->
            <td class="strike-cell" onclick="openStrikeModal(${strike})">${formatNumber(strike, 2)}</td>
            
            <!-- PUTS -->
            <td class="${putItmClass}">${formatNumber(row.put?.bid_qty, 0, "-")}</td>
            <td class="${putItmClass}">${formatNumber(row.put?.bid, 2, "-")}</td>
            <td class="${putItmClass}">${formatNumber(row.put?.ask, 2, "-")}</td>
            <td class="${putItmClass}">${formatNumber(row.put?.ask_qty, 0, "-")}</td>
            <td class="${putItmClass} ${pChgClass}">${formatNumber(row.put?.chng, 2, "-")}</td>
            <td class="${putItmClass} link-blue" onclick="openStrikeModal(${strike})">${formatNumber(row.put?.ltp, 2, "-")}</td>
            <td class="${putItmClass} bs-field ${putBsClass}" title="${putBsTitle}">${formatNumber(putBS.put, 2)}</td>
            <td class="${putItmClass}">${formatNumber(row.put?.iv, 2, "-")}</td>
            <td class="${putItmClass}">${formatNumber(row.put?.volume, 0, "-")}</td>
            <td class="${putItmClass} ${row.put?.chng_in_oi < 0 ? 'negative-val' : ''}">${formatNumber(row.put?.chng_in_oi, 0, "-")}</td>
            <td class="${putItmClass}">${formatNumber(row.put?.oi, 0, "-")}</td>
            <td class="chart-cell">
                <button class="chart-icon-btn" title="View Chart" onclick="openStrikeModal(${strike})">
                    <svg viewBox="0 0 24 24" width="12" height="12">
                        <path d="M5 9.2h3V19H5zM10.5 5h3v14h-3zm5.5 8h3v6h-3z"/>
                    </svg>
                </button>
            </td>
        `;
        
        elements.tableBody.appendChild(tr);
    });

    // Scroll to the ATM Strike row inside table for easy visual inspection
    if (appState.selectedStrike === "ALL" && isFirstLoad) {
        setTimeout(() => {
            const atmRow = document.querySelector(".atm-strike-row");
            if (atmRow) {
                atmRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }, 100);
        isFirstLoad = false;
    }
}

let isFirstLoad = true;

/**
 * Open Greeks Details Modal loaded with specific strike's analytical parameters
 */
window.openStrikeModal = function(strikePrice) {
    activeInspectedStrike = strikePrice;
    const chainRows = appState.optionChains[appState.selectedExpiry] || [];
    const row = chainRows.find(r => Math.abs(r.strike_price - strikePrice) < 0.01);
    if (!row) return;

    const callIv = row.call?.iv || appState.volatility;
    const putIv = row.put?.iv || appState.volatility;

    const callBS = calculateBSM(appState.spot, strikePrice, appState.daysToExpiry, appState.riskFreeRate, callIv, appState.dividendYield);
    const putBS = calculateBSM(appState.spot, strikePrice, appState.daysToExpiry, appState.riskFreeRate, putIv, appState.dividendYield);

    // Call and Put edge: Fair theoretical minus LTP
    const callEdge = row.call?.ltp ? callBS.call - row.call.ltp : null;
    const putEdge = row.put?.ltp ? putBS.put - row.put.ltp : null;

    // Load values into modal HTML
    elements.modalStrikePrice.textContent = formatNumber(strikePrice, 2);

    elements.modalCLtp.textContent = formatNumber(row.call?.ltp, 2);
    elements.modalCBsVal.textContent = formatNumber(callBS.call, 2);
    elements.modalCEdge.textContent = formatNumber(callEdge, 2) + (callEdge > 0 ? " (Underpriced)" : callEdge < 0 ? " (Overpriced)" : "");
    elements.modalCEdge.className = "font-mono " + (callEdge > 0 ? "positive-val" : callEdge < 0 ? "negative-val" : "");
    elements.modalCDelta.textContent = formatNumber(callBS.deltaCall, 4);
    elements.modalCGamma.textContent = formatNumber(callBS.gamma, 6);
    elements.modalCVega.textContent = formatNumber(callBS.vega, 4);
    elements.modalCTheta.textContent = formatNumber(callBS.thetaCall, 4);
    elements.modalCRho.textContent = formatNumber(callBS.rhoCall, 4);

    elements.modalPLtp.textContent = formatNumber(row.put?.ltp, 2);
    elements.modalPBsVal.textContent = formatNumber(putBS.put, 2);
    elements.modalPEdge.textContent = formatNumber(putEdge, 2) + (putEdge > 0 ? " (Underpriced)" : putEdge < 0 ? " (Overpriced)" : "");
    elements.modalPEdge.className = "font-mono " + (putEdge > 0 ? "positive-val" : putEdge < 0 ? "negative-val" : "");
    elements.modalPDelta.textContent = formatNumber(putBS.deltaPut, 4);
    elements.modalPGamma.textContent = formatNumber(putBS.gamma, 6); // Gamma is same for Call and Put
    elements.modalPVega.textContent = formatNumber(putBS.vega, 4);   // Vega is same for Call and Put
    elements.modalPTheta.textContent = formatNumber(putBS.thetaPut, 4);
    elements.modalPRho.textContent = formatNumber(putBS.rhoPut, 4);

    elements.modalInSpot.textContent = formatNumber(appState.spot, 2);
    elements.modalInVol.textContent = formatNumber((callIv + putIv) / 2, 2) + "%";
    elements.modalInDays.textContent = appState.daysToExpiry;
    elements.modalInRate.textContent = formatNumber(appState.riskFreeRate, 2) + "%";
    elements.modalInDiv.textContent = formatNumber(appState.dividendYield, 2) + "%";
    
    elements.modalD1.textContent = formatNumber(callBS.d1, 4);
    elements.modalD2.textContent = formatNumber(callBS.d2, 4);
    elements.modalNd1.textContent = formatNumber(callBS.nd1, 4);
    elements.modalNd2.textContent = formatNumber(callBS.nd2, 4);

    elements.greeksModal.classList.add("show");
};

/**
 * Format Option Chain visible elements and export to a clean local CSV file
 */
function downloadCSV() {
    const chainRows = appState.optionChains[appState.selectedExpiry] || [];
    if (chainRows.length === 0) return;

    let csvContent = "data:text/csv;charset=utf-8,";
    
    // CSV Header row
    csvContent += "CALLS - OI,CALLS - CHNG IN OI,CALLS - VOLUME,CALLS - IV,CALLS - BSM PRICE,CALLS - LTP,CALLS - CHNG,CALLS - BID QTY,CALLS - BID,CALLS - ASK,CALLS - ASK QTY,STRIKE,PUTS - BID QTY,PUTS - BID,PUTS - ASK,PUTS - ASK QTY,PUTS - CHNG,PUTS - LTP,PUTS - BSM PRICE,PUTS - IV,PUTS - VOLUME,PUTS - CHNG IN OI,PUTS - OI\r\n";
    
    chainRows.forEach(row => {
        const strike = row.strike_price;
        const callIv = row.call?.iv || appState.volatility;
        const putIv = row.put?.iv || appState.volatility;
        const callBS = calculateBSM(appState.spot, strike, appState.daysToExpiry, appState.riskFreeRate, callIv, appState.dividendYield);
        const putBS = calculateBSM(appState.spot, strike, appState.daysToExpiry, appState.riskFreeRate, putIv, appState.dividendYield);

        const values = [
            row.call?.oi || 0,
            row.call?.chng_in_oi || 0,
            row.call?.volume || 0,
            row.call?.iv || 0.0,
            callBS.call.toFixed(2),
            row.call?.ltp || 0.0,
            row.call?.chng || 0.0,
            row.call?.bid_qty || 0,
            row.call?.bid || 0.0,
            row.call?.ask || 0.0,
            row.call?.ask_qty || 0,
            strike,
            row.put?.bid_qty || 0,
            row.put?.bid || 0.0,
            row.put?.ask || 0.0,
            row.put?.ask_qty || 0,
            row.put?.chng || 0.0,
            row.put?.ltp || 0.0,
            putBS.put.toFixed(2),
            row.put?.iv || 0.0,
            row.put?.volume || 0,
            row.put?.chng_in_oi || 0,
            row.put?.oi || 0
        ];
        
        csvContent += values.join(",") + "\r\n";
    });

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `option_chain_${appState.symbol}_${appState.selectedExpiry}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// ----------------------------------------------------
// Event Handlers Setup & Inits
// ----------------------------------------------------

// Close Greeks Modal
elements.modalClose.onclick = function() {
    elements.greeksModal.classList.remove("show");
    activeInspectedStrike = null;
};

// Help & Regulatory Info Modal Logic
function openInfoTab(tabId) {
    elements.infoModal.classList.add("show");
    
    // Deactivate all tab buttons & contents, activate target
    const tabButtons = elements.infoModal.querySelectorAll(".info-tab-btn");
    tabButtons.forEach(btn => {
        if (btn.getAttribute("data-tab") === tabId) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });
    
    const tabContents = elements.infoModal.querySelectorAll(".info-tab-content");
    tabContents.forEach(content => {
        if (content.id === tabId) {
            content.classList.add("active");
        } else {
            content.classList.remove("active");
        }
    });
}

// Robust event delegation click handler for Info Modal triggers
document.addEventListener("click", function(e) {
    const userManualTrigger = e.target.closest("#footer-user-manual-btn, #user-manual-btn");
    const termsTrigger = e.target.closest("#footer-terms-btn, #terms-btn");
    const closeTrigger = e.target.closest("#info-modal-close");
    
    if (userManualTrigger) {
        e.preventDefault();
        openInfoTab("user-manual");
    } else if (termsTrigger) {
        e.preventDefault();
        openInfoTab("terms-conditions");
    } else if (closeTrigger) {
        const infoM = elements.infoModal || document.getElementById("info-modal");
        if (infoM) infoM.classList.remove("show");
    }
});

// Bind clicks to individual tab buttons
document.querySelectorAll(".info-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        const tabId = btn.getAttribute("data-tab");
        openInfoTab(tabId);
    });
});

window.onclick = function(event) {
    if (event.target == elements.greeksModal) {
        elements.greeksModal.classList.remove("show");
        activeInspectedStrike = null;
    }
    const infoModalEl = elements.infoModal || document.getElementById("info-modal");
    if (event.target == infoModalEl) {
        infoModalEl.classList.remove("show");
    }
};

// Bind sliders to number boxes and state values
bindSlider(elements.bsmSpot, elements.bsmSpotSlider, "spot", recalculateAndRender);
bindSlider(elements.bsmVol, elements.bsmVolSlider, "volatility", recalculateAndRender);
bindSlider(elements.bsmDays, elements.bsmDaysSlider, "daysToExpiry", recalculateAndRender);
bindSlider(elements.bsmRate, elements.bsmRateSlider, "riskFreeRate", recalculateAndRender);
bindSlider(elements.bsmDiv, elements.bsmDivSlider, "dividendYield", recalculateAndRender);

// Listeners for selectors
elements.expirySelect.addEventListener("change", (e) => {
    appState.selectedExpiry = e.target.value;
    
    // Estimate expiry days automatically based on select date
    try {
        const today = new Date();
        today.setHours(0,0,0,0);
        const exp = new Date(appState.selectedExpiry);
        exp.setHours(0,0,0,0);
        const diffDays = Math.max(Math.round((exp - today) / (1000 * 60 * 60 * 24)), 1);
        
        appState.daysToExpiry = diffDays;
        elements.bsmDays.value = diffDays;
        elements.bsmDaysSlider.value = diffDays;
    } catch (err) {
        console.error(err);
    }
    
    recalculateAndRender();
});

elements.strikeSelect.addEventListener("change", (e) => {
    appState.selectedStrike = e.target.value;
    recalculateAndRender();
});

// Search button trigger
document.getElementById("main-search-btn").addEventListener("click", () => {
    const symbol = elements.symbolSearchInput.value.trim().toUpperCase();
    if (symbol) {
        closeSuggestions();
        isFirstLoad = true;
        fetchTickerData(symbol);
    }
});

// Refresh button trigger
elements.reloadBtn.addEventListener("click", () => {
    const act = appState.symbol || "NIFTY";
    fetchTickerData(act);
});

// Download CSV trigger
elements.downloadCsvBtn.addEventListener("click", downloadCSV);

// Reset BSM input panel to latest API loaded market metrics
elements.resetMarketBtn.addEventListener("click", () => {
    appState.spot = appState.marketSpot;
    
    // Restore volatility, days, rate, div
    const chainRows = appState.optionChains[appState.selectedExpiry] || [];
    let avgIV = 15.0;
    if (chainRows.length > 0) {
        let sumIV = 0, count = 0;
        chainRows.forEach(r => {
            if (r.call?.iv > 0) { sumIV += r.call.iv; count++; }
            if (r.put?.iv > 0) { sumIV += r.put.iv; count++; }
        });
        if (count > 0) avgIV = sumIV / count;
    }
    appState.volatility = avgIV;
    
    try {
        const today = new Date();
        today.setHours(0,0,0,0);
        const exp = new Date(appState.selectedExpiry);
        exp.setHours(0,0,0,0);
        appState.daysToExpiry = Math.max(Math.round((exp - today) / (1000 * 60 * 60 * 24)), 1);
    } catch (e) {
        appState.daysToExpiry = 30;
    }
    
    appState.riskFreeRate = (appState.symbol === "AAPL" || appState.symbol === "TSLA") ? 5.25 : 6.50;
    appState.dividendYield = (appState.symbol === "AAPL") ? 0.55 : (appState.symbol === "NIFTY") ? 1.20 : 0.00;
    
    // Refresh control visual values
    elements.bsmSpot.value = appState.spot;
    elements.bsmSpotSlider.value = appState.spot;
    elements.bsmVol.value = appState.volatility;
    elements.bsmVolSlider.value = appState.volatility;
    elements.bsmDays.value = appState.daysToExpiry;
    elements.bsmDaysSlider.value = appState.daysToExpiry;
    elements.bsmRate.value = appState.riskFreeRate;
    elements.bsmRateSlider.value = appState.riskFreeRate;
    elements.bsmDiv.value = appState.dividendYield;
    elements.bsmDivSlider.value = appState.dividendYield;
    
    recalculateAndRender();
});

function startHeaderClock() {
    const clockTime = document.getElementById("clock-time");
    const clockDate = document.getElementById("clock-date");
    if (!clockTime || !clockDate) return;

    function update() {
        const now = new Date();
        
        let hours = now.getHours();
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');
        const ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12;
        hours = hours ? hours : 12; // the hour '0' should be '12'
        const hoursStr = String(hours).padStart(2, '0');
        
        clockTime.textContent = `${hoursStr}:${minutes}:${seconds} ${ampm}`;
        
        const day = String(now.getDate()).padStart(2, '0');
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const monthStr = months[now.getMonth()];
        const year = now.getFullYear();
        
        clockDate.textContent = `${day} ${monthStr} ${year}`;
    }
    
    update();
    setInterval(update, 1000);
}

// App Entry Point
async function initApp() {
    startHeaderClock();
    setupAutocomplete();
    await fetchTickerData("NIFTY");
}

window.onload = initApp;

// Global State
let appState = {
    symbol: "NIFTY",
    spot: 0.0,
    prediction: null,
    derivatives: null
};

let currentSocket = null;
let activeSocketSymbol = null;
let debounceTimer;
let activeSuggestionIndex = -1;
let currentSuggestions = [];

// DOM Elements
const elements = {
    symbolSearchInput: document.getElementById("symbol-search-input"),
    searchSuggestions: document.getElementById("search-suggestions"),
    underlyingSymbol: document.getElementById("underlying-symbol"),
    underlyingPrice: document.getElementById("underlying-price"),
    underlyingTime: document.getElementById("underlying-time"),
    reloadBtn: document.getElementById("reload-btn"),
    mainSearchBtn: document.getElementById("main-search-btn"),
    
    // CNN-LSTM Panel
    volRegimeBox: document.getElementById("vol-regime-box"),
    confidencePct: document.getElementById("confidence-pct"),
    confidenceProgress: document.getElementById("confidence-progress"),
    recomputeVolBtn: document.getElementById("recompute-vol-btn"),
    
    // Macro inputs
    macroVix: document.getElementById("macro-vix"),
    macroTnx: document.getElementById("macro-tnx"),
    macroDxy: document.getElementById("macro-dxy"),
    
    // Table Body
    edgeTbody: document.getElementById("edge-tbody"),
    
    // WebSocket Status
    socketDot: document.getElementById("socket-dot"),
    socketText: document.getElementById("socket-text")
};

function formatNumber(num, decimals = 2, defaultVal = "-") {
    if (num === null || num === undefined || isNaN(num)) return defaultVal;
    return Number(num).toLocaleString('en-IN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

function updateSocketStatus(status) {
    if (status === "connected") {
        elements.socketDot.className = "socket-status-dot connected";
        elements.socketText.textContent = "Connected";
    } else {
        elements.socketDot.className = "socket-status-dot";
        elements.socketText.textContent = "Disconnected";
    }
}

// ----------------------------------------------------
// API Integration & Data Loading
// ----------------------------------------------------

async function loadAnalytics(symbol) {
    appState.symbol = symbol.toUpperCase();
    elements.underlyingSymbol.textContent = appState.symbol;
    
    elements.edgeTbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 25px; color: #3c3580;">Loading pricing & forecast models for ${appState.symbol}...</td></tr>`;
    
    try {
        // 1. Fetch Ticker parameters (for spot price)
        const priceRes = await fetch(`/v1/pricer/ticker/${appState.symbol}`);
        if (priceRes.ok) {
            const priceData = await priceRes.json();
            appState.spot = priceData.stock_price;
            elements.underlyingPrice.textContent = formatNumber(appState.spot, 2);
            
            const now = new Date(priceData.generated_at || new Date());
            elements.underlyingTime.textContent = now.toLocaleDateString("en-IN", {
                day: "2-digit", month: "short", year: "numeric"
            }) + " " + now.toLocaleTimeString("en-IN");
        }
        
        // 2. Fetch CNN Predictions
        await fetchPrediction(appState.symbol);
        
        // 3. Fetch Derivatives Pricing Edge Table
        await fetchDerivativesEdge(appState.symbol);
        
        // 4. Setup/Switch WebSocket connection
        if (!currentSocket || appState.symbol !== activeSocketSymbol) {
            setupWebSocket(appState.symbol);
        }
    } catch (err) {
        console.error("Error loading analytics data: ", err);
    }
}

async function fetchPrediction(symbol) {
    try {
        elements.volRegimeBox.textContent = "CALCULATING...";
        elements.volRegimeBox.className = "volatility-regime-box regime-neutral";
        
        const res = await fetch(`/v1/predictions/${symbol}`);
        if (!res.ok) throw new Error("Failed to load predictions");
        
        const data = await res.json();
        appState.prediction = data;
        renderPrediction(data);
    } catch (err) {
        console.error("Error fetching CNN-LSTM volatility prediction: ", err);
        elements.volRegimeBox.textContent = "UNAVAILABLE";
        elements.volRegimeBox.className = "volatility-regime-box regime-neutral";
    }
}

function renderPrediction(data) {
    if (!data || data.error) {
        elements.volRegimeBox.textContent = "ERROR";
        elements.volRegimeBox.className = "volatility-regime-box regime-neutral";
        return;
    }
    
    const regime = data.prediction || "NEUTRAL";
    elements.volRegimeBox.textContent = regime;
    
    if (regime === "VOL_CRUSH") {
        elements.volRegimeBox.className = "volatility-regime-box regime-crush";
    } else if (regime === "VOL_EXPAND") {
        elements.volRegimeBox.className = "volatility-regime-box regime-expand";
    } else {
        elements.volRegimeBox.className = "volatility-regime-box regime-neutral";
    }
    
    const confVal = Math.round((data.confidence || 0) * 100);
    elements.confidencePct.textContent = `${confVal}% (${data.confluence_status || 'LOW'})`;
    elements.confidenceProgress.style.width = `${confVal}%`;
    
    // Macro inputs
    elements.macroVix.textContent = formatNumber(data.macro_vix, 2);
    elements.macroTnx.textContent = formatNumber(data.macro_tnx_mom, 4);
    elements.macroDxy.textContent = formatNumber(data.macro_dxy_ret * 100, 2) + "%";
}

async function fetchDerivativesEdge(symbol) {
    try {
        const res = await fetch(`/v1/derivatives/${symbol}`);
        if (!res.ok) throw new Error("Failed to fetch derivatives pricing edge");
        
        const data = await res.json();
        appState.derivatives = data;
        renderDerivativesEdge(data);
    } catch (err) {
        console.error("Error fetching derivatives edge: ", err);
        elements.edgeTbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 25px; color: #dc2626;">Error: Failed to fetch option chain pricing edge.</td></tr>`;
    }
}

function renderDerivativesEdge(data) {
    const tbody = elements.edgeTbody;
    tbody.innerHTML = "";
    
    if (!data || !data.fair_priced_chain || data.fair_priced_chain.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 25px; color: #666;">No option chain edge data available.</td></tr>`;
        return;
    }
    
    // Filter options to show strikes around spot price (ATM +/- 10 strikes)
    const sortedChain = data.fair_priced_chain.sort((a, b) => a.strike - b.strike);
    
    sortedChain.forEach(row => {
        const strike = row.strike;
        const liveCall = row.live_call || 0;
        const bsCall = row.bs_fair_call || 0;
        const cnCall = row.fair_call || 0;
        
        const callEdgeVal = cnCall - liveCall;
        const callEdgePct = liveCall > 0 ? (callEdgeVal / liveCall) * 100 : 0;
        
        const livePut = row.live_put || 0;
        const cnPut = row.fair_put || 0;
        const putEdgeVal = cnPut - livePut;
        const putEdgePct = livePut > 0 ? (putEdgeVal / livePut) * 100 : 0;
        
        const tr = document.createElement("tr");
        
        // CSS coloring classes
        const callEdgeClass = callEdgeVal > 0.5 ? "edge-high" : (callEdgeVal < -0.5 ? "edge-low" : "");
        const putEdgeClass = putEdgeVal > 0.5 ? "edge-high" : (putEdgeVal < -0.5 ? "edge-low" : "");
        
        tr.innerHTML = `
            <td style="text-align: center; font-weight: 700; color: #3c3580; background-color: #f9fafb;">${formatNumber(strike, 0)}</td>
            <td>${formatNumber(liveCall, 2)}</td>
            <td>${formatNumber(bsCall, 2)}</td>
            <td>${formatNumber(cnCall, 2)}</td>
            <td class="${callEdgeClass}">${callEdgeVal > 0 ? "+" : ""}${formatNumber(callEdgeVal, 2)} (${formatNumber(callEdgePct, 1)}%)</td>
            <td class="${putEdgeClass}">${putEdgeVal > 0 ? "+" : ""}${formatNumber(putEdgeVal, 2)} (${formatNumber(putEdgePct, 1)}%)</td>
        `;
        
        tbody.appendChild(tr);
    });
}

// ----------------------------------------------------
// WebSocket Real-time Updates
// ----------------------------------------------------

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
        updateSocketStatus("connected");
    };
    
    socket.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === "price") {
                console.log(`Real-time price update received for ${symbol}:`, msg.data);
                const priceData = msg.data;
                if (priceData && priceData.last_price) {
                    appState.spot = priceData.last_price;
                    elements.underlyingPrice.textContent = formatNumber(appState.spot, 2);
                    
                    const updateTime = priceData.last_updated ? new Date(priceData.last_updated) : new Date();
                    elements.underlyingTime.textContent = updateTime.toLocaleDateString("en-IN", {
                        day: "2-digit", month: "short", year: "numeric"
                    }) + " " + updateTime.toLocaleTimeString("en-IN");
                }
            } else if (msg.type === "prediction") {
                console.log(`Real-time prediction update received for ${symbol}:`, msg.data);
                const predData = typeof msg.data === "string" ? JSON.parse(msg.data) : msg.data;
                appState.prediction = predData;
                renderPrediction(predData);
            } else if (msg.type === "options") {
                console.log(`Real-time options update received for ${symbol}`);
                fetchDerivativesEdge(symbol);
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
            updateSocketStatus("disconnected");
            
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
        updateSocketStatus("disconnected");
    };
}

// ----------------------------------------------------
// Autocomplete & Search
// ----------------------------------------------------

function setupAutocomplete() {
    const input = elements.symbolSearchInput;
    const container = elements.searchSuggestions;

    if (!input || !container) return;

    input.addEventListener("focus", () => {
        fetchSuggestions(input.value);
    });

    input.addEventListener("input", (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            fetchSuggestions(e.target.value);
        }, 200);
    });

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
                    loadAnalytics(typedVal);
                }
            }
        } else if (e.key === "Escape") {
            closeSuggestions();
        }
    });

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
    loadAnalytics(item.symbol);
}

function closeSuggestions() {
    if (elements.searchSuggestions) {
        elements.searchSuggestions.classList.add("hidden");
    }
    activeSuggestionIndex = -1;
}

// ----------------------------------------------------
// Event Handlers Setup & Inits
// ----------------------------------------------------

elements.mainSearchBtn.addEventListener("click", () => {
    const symbol = elements.symbolSearchInput.value.trim().toUpperCase();
    if (symbol) {
        closeSuggestions();
        loadAnalytics(symbol);
    }
});

elements.reloadBtn.addEventListener("click", () => {
    loadAnalytics(appState.symbol);
});

elements.recomputeVolBtn.addEventListener("click", async () => {
    try {
        elements.recomputeVolBtn.disabled = true;
        elements.recomputeVolBtn.textContent = "Recomputing...";
        await fetchPrediction(appState.symbol);
    } finally {
        elements.recomputeVolBtn.disabled = false;
        elements.recomputeVolBtn.textContent = "Recompute Volatility";
    }
});

// App Entry Point
async function initApp() {
    setupAutocomplete();
    await loadAnalytics("NIFTY");
}

window.onload = initApp;

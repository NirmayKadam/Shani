// AlphaStreams Dashboard Logic

let currentSymbol = 'NIFTY';
let refreshInterval = null;

// DOM Elements
const watchlistContainer = document.getElementById('watchlist-container');
const headlinesContainer = document.getElementById('headlines-list');
const activeSymbolEl = document.getElementById('active-symbol');
const lastPriceEl = document.getElementById('last-price');
const priceChangeEl = document.getElementById('price-change');
const volumeEl = document.getElementById('volume');
const openEl = document.getElementById('open-price');
const highEl = document.getElementById('high-price');
const lowEl = document.getElementById('low-price');
const globalSentimentEl = document.getElementById('global-sentiment');
const globalScoreFillEl = document.getElementById('global-score-fill');
const globalScoreTextEl = document.getElementById('global-score-text');
const mlPredictionEl = document.getElementById('ml-prediction');
const mlConfidenceEl = document.getElementById('ml-confidence');

const tfIntradayEl = document.getElementById('tf-intraday');
const tfDailyEl = document.getElementById('tf-daily');
const tfWeeklyEl = document.getElementById('tf-weekly');

/**
 * Initialisation
 */
async function init() {
    console.log('AlphaStreams UI Initialising...');
    await loadWatchlist();
    
    // Select first symbol by default if available
    const firstSymbol = document.querySelector('.symbol-link');
    if (firstSymbol) {
        selectSymbol(firstSymbol.dataset.symbol);
    }

    // Setup search
    document.getElementById('symbol-search').addEventListener('input', (e) => {
        const term = e.target.value.toUpperCase();
        document.querySelectorAll('.symbol-link').forEach(link => {
            link.style.display = link.dataset.symbol.includes(term) ? 'block' : 'none';
        });
    });
}

/**
 * Fetch and Render Watchlist
 */
async function loadWatchlist() {
    try {
        const resp = await fetch('/v1/symbols');
        const data = await resp.json();
        
        watchlistContainer.innerHTML = '';
        data.symbols.forEach(symbol => {
            const el = document.createElement('a');
            el.className = 'symbol-link';
            el.dataset.symbol = symbol;
            el.textContent = symbol;
            el.onclick = () => selectSymbol(symbol);
            watchlistContainer.appendChild(el);
        });
    } catch (err) {
        console.error('Failed to load symbols:', err);
        watchlistContainer.innerHTML = '<div class="error">Error loading watchlist</div>';
    }
}

/**
 * Symbol Selection
 */
async function selectSymbol(symbol) {
    if (!symbol) return;
    currentSymbol = symbol;
    
    // Update UI state
    document.querySelectorAll('.symbol-link').forEach(link => {
        link.classList.toggle('active', link.dataset.symbol === symbol);
    });
    activeSymbolEl.textContent = symbol;
    
    // Start polling
    if (refreshInterval) clearInterval(refreshInterval);
    await refreshDashboard();
    refreshInterval = setInterval(refreshDashboard, 5000); // 5s refresh
}

/**
 * Major Dashboard Refresh
 */
async function refreshDashboard() {
    try {
        const resp = await fetch(`/v1/analyze/${currentSymbol}`);
        const data = await resp.json();
        
        renderPrices(data.market_data);
        renderSentiment(data.sentiment, data.headlines);
        renderForecast(data.technical_forecast);
        renderHeadlines(data.headlines);
        
    } catch (err) {
        console.error(`Failed to refresh ${currentSymbol}:`, err);
    }
}

/**
 * UI Rendering Helpers
 */
function renderPrices(market) {
    if (!market) return;
    
    lastPriceEl.textContent = `₹${market.last_price.toLocaleString()}`;
    volumeEl.textContent = market.volume.toLocaleString();
    openEl.textContent = `₹${market.open.toLocaleString()}`;
    highEl.textContent = `₹${market.high.toLocaleString()}`;
    lowEl.textContent = `₹${market.low.toLocaleString()}`;
    
    const change = market.change_percent;
    priceChangeEl.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`;
    priceChangeEl.className = `price-change ${change >= 0 ? 'val-BULLISH' : 'val-BEARISH'}`;
}

function renderSentiment(sentiment, headlines) {
    if (!sentiment) {
        globalSentimentEl.textContent = 'NO DATA';
        return;
    }
    
    const timeframe = sentiment.daily || sentiment.intraday || { label: 'NEUTRAL', avg_score: 0 };
    globalSentimentEl.textContent = timeframe.label;
    globalSentimentEl.className = `sentiment-value val-${timeframe.label}`;
    
    // Score is -1 to 1, map to 0% to 100%
    const score = timeframe.avg_score;
    const fillPercent = ((score + 1) / 2) * 100;
    globalScoreFillEl.style.width = `${fillPercent}%`;
    globalScoreTextEl.textContent = score.toFixed(2);

    if (sentiment.intraday) {
        tfIntradayEl.textContent = sentiment.intraday.label;
        tfIntradayEl.className = `tf-val val-${sentiment.intraday.label}`;
    }
    
    if (sentiment.daily) {
        tfDailyEl.textContent = sentiment.daily.label;
        tfDailyEl.className = `tf-val val-${sentiment.daily.label}`;
    }
    
    if (sentiment.weekly) {
        tfWeeklyEl.textContent = sentiment.weekly.label;
        tfWeeklyEl.className = `tf-val val-${sentiment.weekly.label}`;
    }
}

function renderForecast(forecast) {
    if (!forecast) {
        mlPredictionEl.textContent = 'STABLE';
        mlConfidenceEl.textContent = '0%';
        return;
    }
    
    mlPredictionEl.textContent = forecast.prediction;
    mlPredictionEl.className = `prediction val-${forecast.prediction}`;
    mlConfidenceEl.textContent = `${Math.round(forecast.confidence * 100)}%`;
}

function renderHeadlines(headlines) {
    if (!headlines || headlines.length === 0) {
        headlinesContainer.innerHTML = '<div class="empty-state">No headlines found</div>';
        return;
    }
    
    headlinesContainer.innerHTML = headlines.map(h => `
        <div class="headline-item">
            <div class="headline-meta">
                <span>${h.source_name}</span>
                <span>${new Date(h.published_at).toLocaleTimeString()}</span>
            </div>
            <div class="headline-title">${h.headline}</div>
            <div class="headline-sentiment">
                <span class="sentiment-pill pill-${h.sentiment_label}">${h.sentiment_label}</span>
                <span class="pill-NEUTRAL sentiment-pill">${h.sentiment_score.toFixed(2)}</span>
            </div>
        </div>
    `).join('');
}

// Global exposure for refresh button
window.refreshAnalysis = refreshDashboard;

// Start the app
document.addEventListener('DOMContentLoaded', init);

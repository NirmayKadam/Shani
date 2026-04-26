const API_BASE = "http://localhost:8000/v1/analyze/";

const elements = {
    symbolInput: document.getElementById('symbolInput'),
    searchBtn: document.getElementById('searchBtn'),
    displaySymbol: document.getElementById('displaySymbol'),
    lastPrice: document.getElementById('lastPrice'),
    priceChange: document.getElementById('priceChange'),
    marketStatus: document.getElementById('marketStatus'),
    lastUpdate: document.getElementById('lastUpdate'),
    valOpen: document.getElementById('val-open'),
    valPrevClose: document.getElementById('val-prev-close'),
    valHigh: document.getElementById('val-high'),
    valLow: document.getElementById('val-low'),
    valVolume: document.getElementById('val-volume'),
    sentimentLabel: document.getElementById('sentimentLabel'),
    sentimentScore: document.getElementById('sentimentScore'),
    sentimentBar: document.getElementById('sentimentBar'),
    pcrValue: document.getElementById('pcrValue'),
    pcrTrend: document.getElementById('pcrTrend'),
    ceVolume: document.getElementById('ceVolume'),
    peVolume: document.getElementById('peVolume'),
    ceOI: document.getElementById('ceOI'),
    peOI: document.getElementById('peOI'),
    ceTotal: document.getElementById('ceTotal'),
    peTotal: document.getElementById('peTotal'),
    dominanceFill: document.getElementById('dominanceFill'),
    expiryDates: document.getElementById('expiryDates'),
    headlinesList: document.getElementById('headlinesList')
};

async function analyzeSymbol(symbol) {
    if (!symbol) return;
    
    // Set loading state
    elements.searchBtn.disabled = true;
    elements.searchBtn.textContent = "Analyzing...";
    
    try {
        const response = await fetch(`${API_BASE}${symbol}`);
        if (!response.ok) throw new Error(`API Error: ${response.status}`);
        
        const data = await response.json();
        updateUI(data);
    } catch (error) {
        console.error("Fetch failed:", error);
        alert(`Analysis failed for ${symbol}. Ensure backend is running at ${API_BASE}`);
    } finally {
        elements.searchBtn.disabled = false;
        elements.searchBtn.textContent = "Analyze";
    }
}

function updateUI(data) {
    // 1. Basic Info
    elements.displaySymbol.innerText = data.symbol;
    
    if (data.market_data) {
        const md = data.market_data;
        elements.lastPrice.innerText = md.last_price.toLocaleString('en-IN', { minimumFractionDigits: 2 });
        
        const change = md.change_percent;
        const colorClass = change >= 0 ? 'text-green-500' : 'text-red-500';
        const icon = change >= 0 ? 'arrow-up' : 'arrow-down';
        
        elements.priceChange.className = `text-lg font-medium flex items-center gap-1 ${colorClass}`;
        elements.priceChange.innerHTML = `<span>${change.toFixed(2)}%</span>`;
        
        elements.valOpen.innerText = md.open.toLocaleString();
        elements.valPrevClose.innerText = md.previous_close.toLocaleString();
        elements.valHigh.innerText = md.high.toLocaleString();
        elements.valLow.innerText = md.low.toLocaleString();
        elements.valVolume.innerText = md.volume.toLocaleString();
        
        elements.marketStatus.innerHTML = `
            <span class="w-2 h-2 rounded-full ${md.market_status === 'OPEN' ? 'bg-green-500 shadow-[0_0_8px_#10b981]' : 'bg-gray-500'}"></span>
            ${md.market_status.toUpperCase()}
        `;
    }

    elements.lastUpdate.innerText = `LAST UPDATE: ${new Date(data.generated_at).toLocaleTimeString()}`;

    // 2. Sentiment
    if (data.sentiment) {
        const s = data.sentiment.daily; // Use daily for overview
        elements.sentimentLabel.innerText = s.label;
        elements.sentimentScore.innerText = `${(s.avg_score * 100).toFixed(0)}%`;
        elements.sentimentBar.style.width = `${(s.avg_score * 100)}%`;
        
        // Color tweak
        if (s.avg_score > 0.6) elements.sentimentBar.className = elements.sentimentBar.className.replace(/bg-\w+-500/, 'bg-green-500');
        else if (s.avg_score < 0.4) elements.sentimentBar.className = elements.sentimentBar.className.replace(/bg-\w+-500/, 'bg-red-500');
        else elements.sentimentBar.className = elements.sentimentBar.className.replace(/bg-\w+-500/, 'bg-blue-500');
    }

    // 3. Options
    if (data.options_summary && data.options_summary.available) {
        const opt = data.options_summary;
        elements.pcrValue.innerText = opt.pcr.toFixed(2);
        
        let pcrStatus = "NEUTRAL";
        let pcrColor = "text-gray-400";
        if (opt.pcr > 1.2) { pcrStatus = "BULLISH"; pcrColor = "text-green-400"; }
        else if (opt.pcr < 0.8) { pcrStatus = "BEARISH"; pcrColor = "text-red-400"; }
        
        elements.pcrTrend.innerText = pcrStatus;
        elements.pcrTrend.className = `text-[10px] mt-1 ${pcrColor}`;
        elements.pcrValue.className = `text-3xl font-bold ${pcrColor}`;

        elements.ceVolume.innerText = opt.ce_volume.toLocaleString();
        elements.peVolume.innerText = opt.pe_volume.toLocaleString();
        elements.ceOI.innerText = opt.ce_oi.toLocaleString();
        elements.peOI.innerText = opt.pe_oi.toLocaleString();
        
        elements.ceTotal.innerText = (opt.ce_volume + opt.ce_oi).toLocaleString();
        elements.peTotal.innerText = (opt.pe_volume + opt.pe_oi).toLocaleString();
        
        const totalActivity = (opt.ce_volume + opt.pe_volume) || 1;
        const dominance = (opt.ce_volume / totalActivity) * 100;
        elements.dominanceFill.style.width = `${dominance}%`;
        
        elements.expiryDates.innerText = `EXPIRIES: ${opt.expiry_dates.slice(0,3).join(', ')}`;
    }

    // 4. Headlines
    elements.headlinesList.innerHTML = '';
    if (data.headlines && data.headlines.length > 0) {
        data.headlines.forEach(hl => {
            const card = document.createElement('div');
            card.className = "headline-card p-4 rounded-lg bg-white/5 border border-white/5 flex flex-col gap-2 animate-fade-in";
            
            const sentimentColor = hl.sentiment_label === 'Bullish' ? 'text-green-400' : (hl.sentiment_label === 'Bearish' ? 'text-red-400' : 'text-gray-400');
            
            card.innerHTML = `
                <div class="flex justify-between items-start gap-4">
                    <h4 class="text-xs font-semibold leading-relaxed">${hl.headline}</h4>
                    <span class="text-[9px] px-2 py-0.5 rounded border border-white/10 uppercase font-bold text-gray-500 whitespace-nowrap">${hl.source_name}</span>
                </div>
                <div class="flex items-center gap-3 mt-1">
                    <span class="flex items-center gap-1 text-[10px] ${sentimentColor} font-bold">
                        <span class="w-1.5 h-1.5 rounded-full bg-current"></span>
                        ${hl.sentiment_label.toUpperCase()}
                    </span>
                    <span class="text-[9px] text-gray-600">${new Date(hl.published_at).toLocaleDateString()}</span>
                </div>
            `;
            elements.headlinesList.appendChild(card);
        });
    } else {
        elements.headlinesList.innerHTML = '<div class="text-gray-600 text-center py-6 text-xs italic">No relevant headlines found.</div>';
    }

    // Trigger animations if Motion is available
    if (window.Motion) {
        window.Motion.animate(".glass-panel", { opacity: [0, 1], y: [20, 0] }, { duration: 0.5, delay: (i) => i * 0.1 });
    }
}

// Event Listeners
elements.searchBtn.addEventListener('click', () => analyzeSymbol(elements.symbolInput.value.trim().toUpperCase()));
elements.symbolInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') analyzeSymbol(elements.symbolInput.value.trim().toUpperCase());
});

// Initial load
window.addEventListener('DOMContentLoaded', () => {
    analyzeSymbol('RELIANCE.NS');
});

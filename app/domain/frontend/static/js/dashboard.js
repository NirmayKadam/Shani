document.addEventListener("DOMContentLoaded", () => {
    const symbol = window.APP_SYMBOL;
    if (!symbol) return;

    // Time handling
    const clockEl = document.getElementById("topbar-clock");
    const statusEl = document.getElementById("topbar-status");
    let ws = null;
    let wsReconnectAttempts = 0;

    function updateClock() {
        const now = new Date();
        const dtOpts = { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' };
        const tmOpts = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' };
        
        const dateStr = now.toLocaleDateString("en-GB", dtOpts).toUpperCase();
        const timeStr = now.toLocaleTimeString("en-GB", tmOpts);
        clockEl.innerText = `${dateStr}  |  ${timeStr} IST`;

        const hour = now.getUTCHours() + 5.5; 
        const day = now.getUTCDay();
        if (day >= 1 && day <= 5 && hour >= 9.25 && hour <= 15.5) {
            statusEl.innerText = "● NSE OPEN";
            statusEl.className = "topbar-status text-bull";
        } else {
            statusEl.innerText = "● NSE CLOSED";
            statusEl.className = "topbar-status text-bear";
        }
    }
    setInterval(updateClock, 1000);
    updateClock();

    function initWS() {
        const wsUrlStr = `${window.APP_WS_URL || "ws://localhost:8000/ws"}/${symbol}`;
        ws = new WebSocket(wsUrlStr);
        
        ws.onopen = () => {
            console.log(`Connected to AlphaStreams F&O WS for ${symbol}`);
            wsReconnectAttempts = 0; 
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                switch(msg.type) {
                    case 'price': updatePriceCard(msg.data); break;
                    case 'options': updateOptionsCard(msg.data); break;
                    case 'sentiment': updateSentimentCard(msg.data); break;
                    case 'headline': prependHeadline(msg.data); break;
                }
            } catch (e) {
                console.error("WS parse error", e);
            }
        };

        ws.onclose = () => {
            console.log("WS closed, attempting reconnect...");
            if(wsReconnectAttempts < 5) {
                setTimeout(initWS, Math.pow(2, wsReconnectAttempts) * 1000);
                wsReconnectAttempts++;
            }
        };
    }

    setTimeout(() => {
        document.querySelectorAll(".skeleton-wrapper").forEach(node => {
            node.innerHTML = "<div class='feed-error'>WAITING FOR DATA SOURCE ↺</div>";
        });
        
        initWS();
    }, 1200);

    function updatePriceCard(data) {
        const ltpNode = document.getElementById("price-ltp");
        const changeNode = document.getElementById("price-change");
        if(ltpNode) {
            ltpNode.innerText = data.last_price;
            ltpNode.classList.add("flash-transition");
            ltpNode.style.backgroundColor = data.change_percent > 0 ? "var(--accent-bull)" : "var(--accent-bear)";
            setTimeout(() => {
                ltpNode.style.backgroundColor = "transparent";
            }, 400);
        }
    }

    function updateOptionsCard(data) {
        if(window.drawOIButterfly) { }
    }

    function updateSentimentCard(data) {
        if(window.drawSentimentSparkline) { }
    }

    function prependHeadline(data) {
        const hContainer = document.getElementById("headlines-container");
        if(hContainer) {
            const el = document.createElement("div");
            el.innerHTML = `<div>${data.headline}</div>`;
            hContainer.prepend(el);
            if(hContainer.children.length > 20) hContainer.lastChild.remove();
        }
    }
});

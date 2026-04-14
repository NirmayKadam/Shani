// Canvas Chart Renderers
// Exposes globally on window scope for invocation without modules

function getCSSVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

window.drawOIButterfly = function(canvasId, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !data) return;
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const bullColor = getCSSVar("--accent-bull");
    const bearColor = getCSSVar("--accent-bear");
    const textColor = getCSSVar("--text-secondary");
    
    ctx.font = "10px IBM Plex Mono";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    const maxOI = Math.max(...data.map(d => Math.max(d.ce_oi, d.pe_oi)));
    const barHeight = (height - 30) / data.length;
    const center = width / 2;
    const labelWidth = 60;
    const usableWidth = (width - labelWidth) / 2;

    data.forEach((row, idx) => {
        const y = 15 + idx * barHeight;
        
        // CE bars extend left to center
        const ceWidth = (row.ce_oi / maxOI) * usableWidth;
        ctx.fillStyle = bearColor;
        ctx.fillRect(center - labelWidth/2 - ceWidth, y + 2, ceWidth, barHeight - 4);
        
        // PE bars extend right to center
        const peWidth = (row.pe_oi / maxOI) * usableWidth;
        ctx.fillStyle = bullColor;
        ctx.fillRect(center + labelWidth/2, y + 2, peWidth, barHeight - 4);

        // Strike label
        ctx.fillStyle = textColor;
        ctx.fillText(row.strike.toString(), center, y + barHeight/2);
    });
};


window.drawGreeksRadar = function(canvasId, metrics) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !metrics) return;
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    
    const center = { x: width/2, y: height/2 };
    const radius = Math.min(width, height) / 2 - 20;

    const gold = getCSSVar("--accent-gold");
    const border = getCSSVar("--border");
    const textSec = getCSSVar("--text-secondary");

    // Draw axes
    ctx.beginPath();
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    ctx.moveTo(center.x, 20); ctx.lineTo(center.x, height - 20); // vertical
    ctx.moveTo(20, center.y); ctx.lineTo(width - 20, center.y); // horizontal
    ctx.stroke();

    const points = [
        { label: "Delta", val: metrics.delta, dx: 0, dy: -1 },
        { label: "Gamma", val: metrics.gamma, dx: 1, dy: 0 },
        { label: "Theta", val: metrics.theta, dx: 0, dy: 1 },
        { label: "Vega", val: metrics.vega, dx: -1, dy: 0 }
    ];

    // Plot stroke polygon
    ctx.beginPath();
    ctx.strokeStyle = gold;
    ctx.lineWidth = 2;
    points.forEach((p, i) => {
        // assume val is normalized 0-1
        let valNorm = Math.max(0, Math.min(1, Math.abs(p.val)));
        let px = center.x + p.dx * radius * valNorm;
        let py = center.y + p.dy * radius * valNorm;
        if(i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.stroke();

    // Axis Labels
    ctx.font = "10px Inter";
    ctx.fillStyle = textSec;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("Delta", center.x, 10);
    ctx.fillText("Theta", center.x, height - 10);
    ctx.textAlign = "left";
    ctx.fillText("Gamma", width - 35, center.y);
    ctx.textAlign = "right";
    ctx.fillText("Vega", 35, center.y);
};

window.drawMLProbability = function(canvasId, confidence, isBullish) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const primaryColor = isBullish ? getCSSVar("--accent-bull") : getCSSVar("--accent-bear");
    const trackColor = getCSSVar("--bg-panel");

    // Track
    ctx.fillStyle = trackColor;
    ctx.fillRect(0, 0, width, height);

    // Fill
    const confPct = Math.max(0, Math.min(1, confidence));
    ctx.fillStyle = primaryColor;
    ctx.fillRect(0, 0, width * confPct, height);
};

window.drawFeatureImportance = function(canvasId, features) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !features) return;
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const barColor = getCSSVar("--accent-neutral");
    const textColor = getCSSVar("--text-primary");
    ctx.font = "11px Inter";
    ctx.textBaseline = "middle";
    
    // features: [{name: "MACD", val: 0.8}, ...]
    const barHeight = (height - 10) / features.length;
    
    features.forEach((f, idx) => {
        const y = 5 + idx * barHeight;
        const bW = width * 0.6 * f.val; // max width 60%
        
        ctx.fillStyle = barColor;
        ctx.fillRect(width * 0.4, y + 2, bW, barHeight - 4);
        
        ctx.fillStyle = textColor;
        ctx.textAlign = "right";
        ctx.fillText(f.name, width * 0.38, y + barHeight/2);
    });
};

window.drawSentimentSparkline = function(canvasId, scoresArray) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !scoresArray || scoresArray.length === 0) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const bullColor = getCSSVar("--accent-bull");
    const bearColor = getCSSVar("--accent-bear");
    const border = getCSSVar("--border");

    const centerY = height / 2;
    const stepX = width / (scoresArray.length - 1);

    // Draw zero line
    ctx.beginPath();
    ctx.strokeStyle = border;
    ctx.moveTo(0, centerY);
    ctx.lineTo(width, centerY);
    ctx.stroke();

    // Map score -1.0 to +1.0 roughly to Y height
    // -1 = height, +1 = 0
    function getY(val) {
        return centerY - (val * centerY);
    }

    // Since we need split color path, we can stroke twice with active clipping
    // Top Clip (Bull)
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, width, centerY);
    ctx.clip();
    drawPath(bullColor);
    ctx.restore();

    // Bottom Clip (Bear)
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, centerY, width, centerY);
    ctx.clip();
    drawPath(bearColor);
    ctx.restore();

    function drawPath(color) {
        ctx.beginPath();
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.lineJoin = "round";
        for (let i = 0; i < scoresArray.length; i++) {
            let x = i * stepX;
            let y = getY(scoresArray[i]);
            if(i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
    }
};

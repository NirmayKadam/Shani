document.addEventListener("DOMContentLoaded", () => {
    const searchInput = document.getElementById("symbol-search");
    const suggestionsContainer = document.getElementById("search-suggestions");
    
    if (!searchInput) return;

    // From router context -> window global object
    const symbols = window.APP_SYMBOLS || [];

    function renderSuggestions(matches) {
        if (!suggestionsContainer) return;
        suggestionsContainer.innerHTML = "";
        
        if (matches.length === 0) {
            suggestionsContainer.style.display = "none";
            return;
        }

        matches.forEach(symbol => {
            const div = document.createElement("div");
            div.className = "suggestion-item";
            div.textContent = symbol;
            div.onclick = () => {
                window.location.href = `/ui/dashboard/${symbol}`;
            };
            suggestionsContainer.appendChild(div);
        });
        
        suggestionsContainer.style.display = "block";
    }

    searchInput.addEventListener("input", (e) => {
        const query = e.target.value.toUpperCase().trim();
        if (!query) {
            renderSuggestions([]);
            return;
        }

        const exact = [];
        const prefix = [];
        const fuzzy = [];

        symbols.forEach(sym => {
            if (sym === query) exact.push(sym);
            else if (sym.startsWith(query)) prefix.push(sym);
            else if (sym.includes(query)) fuzzy.push(sym);
        });

        renderSuggestions([...exact, ...prefix, ...fuzzy].slice(0, 8));
    });
    
    // Keyboard Navigation
    searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && suggestionsContainer.children.length > 0) {
            suggestionsContainer.children[0].click();
        }
    });

    document.addEventListener("click", (e) => {
        if (e.target !== searchInput && suggestionsContainer) {
            suggestionsContainer.style.display = "none";
        }
    });
});

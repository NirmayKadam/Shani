document.addEventListener("DOMContentLoaded", () => {
    const overlay = document.getElementById("modal-overlay");
    if (!overlay) return;

    const modalTitle = document.getElementById("modal-title");
    const modalBody = document.getElementById("modal-body-content");
    
    // Close mapping
    const closeBtns = document.querySelectorAll(".modal-close");
    closeBtns.forEach(btn => {
        btn.addEventListener("click", closeModal);
    });

    overlay.addEventListener("click", (e) => {
        // If clicking directly on overlay (not children)
        if(e.target === overlay) {
            closeModal();
        }
    });

    document.addEventListener("keydown", (e) => {
        if(e.key === "Escape") {
            closeModal();
            closeDrawer();
        }
    });

    function closeModal() {
        overlay.classList.remove("open");
    }

    // Expand triggers
    document.querySelectorAll(".card-expand-link").forEach(trigger => {
        trigger.addEventListener("click", (e) => {
            const targetType = e.target.getAttribute("data-modal-type");
            openModalFor(targetType);
        });
    });

    function openModalFor(type) {
        // Configure modal specifically
        if(type === "greeks") {
            modalTitle.innerText = "IV SURFACE HEATMAP";
            modalBody.innerHTML = `<table style="width:100%;color:var(--text-secondary)"><tr><td>Generating Surface...</td></tr></table>`;
        } else if (type === "ml") {
            modalTitle.innerText = "ML FORECAST DEEP DIVE";
            modalBody.innerHTML = `<div>Historical validation chart loading...</div>`;
        } else if (type === "sentiment") {
            modalTitle.innerText = "SENTIMENT TIMELINE & DISTRIBUTION";
            modalBody.innerHTML = `<div>Full sentiment chart generating...</div>`;
        } else {
            return;
        }
        overlay.classList.add("open");
    }

    // Inline Drawer for Headlines
    const drawer = document.getElementById("headline-drawer");
    const drawerCloses = document.querySelectorAll(".drawer-close-btn");
    
    if(drawer) {
        drawerCloses.forEach(btn => {
            btn.addEventListener("click", closeDrawer);
        });
    }

    function closeDrawer() {
        if(drawer) drawer.classList.remove("open");
    }

    // Mock headline clicking
    window.openHeadlineDrawer = function(id) {
        if(!drawer) return;
        document.getElementById("drawer-content").innerText = `Details for Article ID: ${id}`;
        drawer.classList.add("open");
    };
});

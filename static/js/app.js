(function () {
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
    }

    let installPrompt;
    window.addEventListener("beforeinstallprompt", (event) => {
        event.preventDefault();
        installPrompt = event;
        const installButton = document.getElementById("cq-install-pwa");
        if (installButton) installButton.hidden = false;
    });

    document.addEventListener("click", async (event) => {
        if (!event.target.closest("#cq-install-pwa") || !installPrompt) return;
        installPrompt.prompt();
        await installPrompt.userChoice;
        installPrompt = null;
        event.target.closest("#cq-install-pwa").hidden = true;
    });

    function showToast(message, level) {
        const container = document.getElementById("cq-toast-container");
        if (!container) return;

        const toast = document.createElement("div");
        toast.className = `cq-toast cq-toast-${level || "info"}`;
        toast.setAttribute("role", "status");
        toast.innerHTML = `<span>${message}</span><button type="button" aria-label="Cerrar notificacion">&times;</button>`;
        toast.querySelector("button").addEventListener("click", () => toast.remove());
        container.appendChild(toast);
        window.setTimeout(() => toast.remove(), 5000);
    }

    window.cqShowToast = showToast;

    function openConfirmModal(form, message) {
        const modal = document.getElementById("cq-confirm-modal");
        const messageElement = document.getElementById("cq-confirm-message");
        const confirmButton = document.getElementById("cq-confirm-submit");
        if (!modal || !messageElement || !confirmButton) return;

        messageElement.textContent = message;
        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
        confirmButton.focus();

        const close = () => {
            modal.classList.remove("is-open");
            modal.setAttribute("aria-hidden", "true");
            confirmButton.onclick = null;
        };
        document.getElementById("cq-confirm-cancel").onclick = close;
        confirmButton.onclick = () => {
            close();
            form.submit();
        };
    }

    document.addEventListener("submit", (event) => {
        const form = event.target.closest("[data-confirm-message]");
        if (!form || form.dataset.confirmed === "true") return;
        event.preventDefault();
        openConfirmModal(form, form.dataset.confirmMessage);
    });
})();
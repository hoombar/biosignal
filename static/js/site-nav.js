document.addEventListener("DOMContentLoaded", () => {
    const mobileQuery = window.matchMedia("(max-width: 768px)");

    document.querySelectorAll(".site-header").forEach((header) => {
        const toggle = header.querySelector(".nav-toggle");
        const nav = header.querySelector(".site-nav");

        if (!toggle || !nav) {
            return;
        }

        const setOpen = (open) => {
            header.setAttribute("data-nav-open", String(open));
            toggle.setAttribute("aria-expanded", String(open));
        };

        const closeNav = () => {
            setOpen(false);
        };

        setOpen(false);

        toggle.addEventListener("click", () => {
            setOpen(header.getAttribute("data-nav-open") !== "true");
        });

        nav.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", () => {
                if (mobileQuery.matches) {
                    closeNav();
                }
            });
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                closeNav();
            }
        });

        mobileQuery.addEventListener("change", (event) => {
            if (!event.matches) {
                closeNav();
            }
        });
    });
});

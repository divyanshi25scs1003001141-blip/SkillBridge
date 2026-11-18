/*
  dashboard.js - the slide-in sidebar menu on phones and tablets.
  On wide screens the sidebar is always visible and this does nothing.
*/
document.addEventListener("DOMContentLoaded", function () {
    // Confirmation prompts are attached with data attributes, not inline JS.
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            var message = form.getAttribute("data-confirm") || "Are you sure?";
            if (!window.confirm(message)) { event.preventDefault(); }
        });
    });

    // Desktop: collapse the sidebar to an icon rail. The choice is remembered;
    // the narrow-screen rules in app.css ignore it and keep the slide-in menu.
    var shell = document.querySelector(".app-shell");
    var collapseButton = document.querySelector("[data-sidebar-collapse]");
    if (shell && collapseButton) {
        var COLLAPSE_KEY = "sb-sidebar";

        function setCollapsed(collapsed) {
            shell.classList.toggle("is-collapsed", collapsed);
            collapseButton.setAttribute("aria-expanded", String(!collapsed));
            collapseButton.setAttribute("aria-label", collapsed ? "Expand menu" : "Collapse menu");
            collapseButton.setAttribute("title", collapsed ? "Expand menu" : "Collapse menu");
            try {
                window.localStorage.setItem(COLLAPSE_KEY, collapsed ? "collapsed" : "expanded");
            } catch (problem) {
                /* the layout still changes for this page view */
            }
        }

        var savedCollapse = null;
        try { savedCollapse = window.localStorage.getItem(COLLAPSE_KEY); } catch (problem) { /* ignore */ }
        if (savedCollapse === "collapsed") { setCollapsed(true); }

        collapseButton.addEventListener("click", function () {
            setCollapsed(!shell.classList.contains("is-collapsed"));
        });
    }

    var sidebar = document.getElementById("sidebar");
    var toggleButton = document.querySelector("[data-sidebar-toggle]");
    var backdrop = document.querySelector(".sidebar-backdrop");
    if (!sidebar || !toggleButton) { return; }

    function setMenu(open) {
        sidebar.classList.toggle("is-open", open);
        if (backdrop) { backdrop.classList.toggle("is-visible", open); }
        document.body.classList.toggle("menu-open", open);
        toggleButton.setAttribute("aria-expanded", String(open));
    }

    toggleButton.addEventListener("click", function () { setMenu(true); });

    // Every element marked data-sidebar-close (the x button and the dark backdrop) closes the menu.
    document.querySelectorAll("[data-sidebar-close]").forEach(function (element) {
        element.addEventListener("click", function () {
            setMenu(false);
            toggleButton.focus();
        });
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && sidebar.classList.contains("is-open")) {
            setMenu(false);
            toggleButton.focus();
        }
    });

    // If the window is made wide again, reset the menu.
    window.addEventListener("resize", function () {
        if (window.innerWidth > 900) { setMenu(false); }
    });
});

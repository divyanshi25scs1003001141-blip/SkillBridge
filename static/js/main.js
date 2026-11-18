/*
  main.js - small bits of behaviour shared by every page.
  Each feature looks for a "data-" attribute in the HTML, so the code does
  nothing on pages that don't use it.
*/
document.addEventListener("DOMContentLoaded", function () {

    // 1. Mobile menu: the button with data-nav-toggle opens and closes the menu.
    var navToggle = document.querySelector("[data-nav-toggle]");
    var siteNav = document.getElementById("site-nav");

    function setMenu(open) {
        siteNav.classList.toggle("is-open", open);
        navToggle.setAttribute("aria-expanded", String(open));
        navToggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    }

    if (navToggle && siteNav) {
        navToggle.addEventListener("click", function () {
            setMenu(!siteNav.classList.contains("is-open"));
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && siteNav.classList.contains("is-open")) {
                setMenu(false);
                navToggle.focus();
            }
        });
        siteNav.addEventListener("click", function (event) {
            if (event.target.closest("a")) {
                setMenu(false);
            }
        });
    }

    // 2. Flash messages: the x button removes the message.
    document.querySelectorAll("[data-dismiss-alert]").forEach(function (button) {
        button.addEventListener("click", function () {
            var alertBox = button.closest(".alert");
            if (alertBox) {
                alertBox.remove();
            }
        });
    });

    // 3. Show/hide password (used by the login and register forms).
    document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
        button.addEventListener("click", function () {
            var input = document.getElementById(button.dataset.togglePassword);
            if (!input) { return; }
            var showing = input.type === "text";
            input.type = showing ? "password" : "text";
            button.textContent = showing ? "Show" : "Hide";
            button.setAttribute("aria-pressed", String(!showing));
        });
    });

    // 4. Loading state: a form with data-loading-form disables its submit
    //    button and shows a spinner while the browser sends the data.
    document.querySelectorAll("form[data-loading-form]").forEach(function (form) {
        form.addEventListener("submit", function () {
            var button = form.querySelector("[type='submit']");
            if (button) {
                button.classList.add("is-loading");
                button.disabled = true;
            }
        });
    });
});

// If the visitor presses the browser's Back button, reset any loading buttons.
window.addEventListener("pageshow", function () {
    document.querySelectorAll(".btn.is-loading").forEach(function (button) {
        button.classList.remove("is-loading");
        button.disabled = false;
    });
});

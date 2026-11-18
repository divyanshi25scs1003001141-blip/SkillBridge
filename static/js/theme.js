/**
 * static/js/theme.js - the light/dark switch.
 *
 * The saved choice lives in localStorage ("sb-theme"). When nothing is saved
 * the operating system preference is used. A tiny inline script in the page
 * head applies the choice before the first paint (templates/_theme_init.html),
 * which is why this file only has to wire the buttons up.
 *
 * Any element with [data-theme-toggle] becomes a switch. Its state is exposed
 * through aria-pressed so screen readers announce it correctly.
 */
(function () {
    "use strict";

    var STORAGE_KEY = "sb-theme";
    var EVENT_NAME = "sb:themechange";

    function stored() {
        try {
            var value = window.localStorage.getItem(STORAGE_KEY);
            return value === "light" || value === "dark" ? value : null;
        } catch (problem) {
            return null;            // private mode or storage disabled
        }
    }

    /** Light canvas is the product default; dark is only used after a choice. */
    function preferred() {
        return "light";
    }

    function current() {
        return document.documentElement.getAttribute("data-theme") || stored() || preferred();
    }

    function syncButtons(theme) {
        var dark = theme === "dark";
        document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
            button.setAttribute("aria-pressed", String(dark));
            button.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
            button.setAttribute("title", dark ? "Light theme" : "Dark theme");
            var label = button.querySelector("[data-theme-label]");
            if (label) {
                label.textContent = dark ? "Light" : "Dark";
            }
        });
    }

    function apply(theme, persist) {
        document.documentElement.setAttribute("data-theme", theme);
        document.documentElement.style.colorScheme = theme;
        if (persist) {
            try {
                window.localStorage.setItem(STORAGE_KEY, theme);
            } catch (problem) {
                /* the theme still applies for this page view */
            }
        }
        syncButtons(theme);
        // Charts read colours from CSS variables, so they re-render on change.
        window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: { theme: theme } }));
    }

    function toggle() {
        apply(current() === "dark" ? "light" : "dark", true);
    }

    function wire() {
        syncButtons(current());
        document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
            button.addEventListener("click", toggle);
        });
    }

    document.addEventListener("DOMContentLoaded", wire);
    window.SkillBridgeTheme = { apply: apply, toggle: toggle, current: current };
})();

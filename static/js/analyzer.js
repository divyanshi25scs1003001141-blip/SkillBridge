/**
 * static/js/analyzer.js - Resume Analyzer page helpers.
 *
 * Only two small jobs:
 *   1. show the chosen file's name and size, and warn early if it is too big;
 *   2. remember the improvement-checklist ticks in this browser (localStorage),
 *      because they are a private to-do list and are never sent to the server.
 */
(function () {
    "use strict";

    var MAX_MB = 5;

    function setupFileInput() {
        var input = document.querySelector("[data-file-input]");
        var label = document.querySelector("[data-file-name]");
        if (!input || !label) {
            return;
        }

        input.addEventListener("change", function () {
            var file = input.files && input.files[0];
            if (!file) {
                label.hidden = true;
                label.textContent = "";
                return;
            }
            var megabytes = file.size / (1024 * 1024);
            label.hidden = false;
            if (megabytes > MAX_MB) {
                label.textContent = file.name + " is " + megabytes.toFixed(1) +
                    " MB. The limit is " + MAX_MB + " MB.";
                label.classList.add("is-error");
                return;
            }
            label.classList.remove("is-error");
            label.textContent = file.name + " · " + (file.size / 1024).toFixed(0) + " KB";
        });
    }

    function setupChecklist() {
        var lists = document.querySelectorAll("[data-checklist]");
        Array.prototype.forEach.call(lists, function (list) {
            var key = "skillbridge-checklist-" + list.getAttribute("data-checklist");
            var saved = [];
            try {
                saved = JSON.parse(window.localStorage.getItem(key) || "[]");
            } catch (problem) {
                saved = [];
            }

            var boxes = list.querySelectorAll("input[type=checkbox]");
            Array.prototype.forEach.call(boxes, function (box) {
                var done = saved.indexOf(box.value) !== -1;
                box.checked = done;
                if (done) {
                    box.closest("li").classList.add("is-done");
                }
                box.addEventListener("change", function () {
                    var next = [];
                    Array.prototype.forEach.call(boxes, function (other) {
                        if (other.checked) {
                            next.push(other.value);
                        }
                        other.closest("li").classList.toggle("is-done", other.checked);
                    });
                    try {
                        window.localStorage.setItem(key, JSON.stringify(next));
                    } catch (problem) {
                        /* private mode: ticks simply are not remembered */
                    }
                });
            });
        });
    }

    function setupSubmitState() {
        var form = document.getElementById("analyzer-form");
        if (!form) {
            return;
        }
        form.addEventListener("submit", function () {
            var button = form.querySelector("button[type=submit]");
            if (button) {
                button.disabled = true;
                button.textContent = "Analysing…";
            }
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        setupFileInput();
        setupChecklist();
        setupSubmitState();
    });
})();

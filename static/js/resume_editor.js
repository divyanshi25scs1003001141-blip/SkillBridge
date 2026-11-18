/*
  resume_editor.js - small helpers for the resume builder.

  Adds and removes repeating rows, moves them up or down, and refreshes the
  right-hand preview from the same form the server saves. No framework and no
  build step: everything here uses plain DOM APIs.
*/
document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("resume-form");
    var preview = document.getElementById("resume-preview");
    if (!form || !preview) { return; }

    var previewUrl = preview.getAttribute("data-preview-url");
    var loading = preview.querySelector(".preview-loading");
    var timer = null;
    var lastRequest = 0;

    function csrfToken() {
        var input = form.querySelector('input[name="csrf_token"]');
        return input ? input.value : "";
    }

    function refreshPreview() {
        if (!previewUrl) { return; }
        var requestId = ++lastRequest;
        if (loading) { loading.hidden = false; }

        var data = new FormData(form);
        fetch(previewUrl, {
            method: "POST",
            body: data,
            headers: { "X-CSRF-Token": csrfToken() },
            credentials: "same-origin"
        }).then(function (response) {
            if (!response.ok) { throw new Error("preview failed"); }
            return response.text();
        }).then(function (html) {
            if (requestId !== lastRequest) { return; }  // a newer edit already won
            preview.innerHTML = html;
            var spinner = document.createElement("p");
            spinner.className = "preview-loading";
            spinner.hidden = true;
            spinner.textContent = "Updating preview…";
            preview.appendChild(spinner);
            loading = spinner;
        }).catch(function () {
            if (loading) { loading.hidden = true; }
        });
    }

    function schedulePreview() {
        window.clearTimeout(timer);
        timer = window.setTimeout(refreshPreview, 450);
    }

    function renumberRows(container) {
        var rows = container.querySelectorAll(".editor-row");
        Array.prototype.forEach.call(rows, function (row, index) {
            var legend = row.querySelector("legend");
            if (legend) {
                legend.textContent = legend.textContent.replace(/\s*\d+$/, "") + " " + (index + 1);
            }
        });
    }

    // Add row buttons
    document.querySelectorAll("[data-add-row]").forEach(function (button) {
        button.addEventListener("click", function () {
            var kind = button.getAttribute("data-add-row");
            var template = document.getElementById("row-" + kind);
            var target = document.querySelector('[data-rows="' + kind + '"]');
            if (!template || !target) { return; }
            var fragment = template.content.cloneNode(true);
            target.appendChild(fragment);
            renumberRows(target);
            var firstInput = target.lastElementChild.querySelector("input, textarea");
            if (firstInput) { firstInput.focus(); }
            schedulePreview();
        });
    });

    // Remove and move, handled from the form so cloned rows work automatically
    form.addEventListener("click", function (event) {
        var removeButton = event.target.closest("[data-remove-row]");
        if (removeButton) {
            var row = removeButton.closest(".editor-row");
            var container = row.parentElement;
            row.remove();
            renumberRows(container);
            schedulePreview();
            return;
        }
        var moveButton = event.target.closest("[data-move]");
        if (moveButton) {
            var current = moveButton.closest(".editor-row");
            var parent = current.parentElement;
            if (moveButton.getAttribute("data-move") === "up" && current.previousElementSibling) {
                parent.insertBefore(current, current.previousElementSibling);
            } else if (moveButton.getAttribute("data-move") === "down" && current.nextElementSibling) {
                parent.insertBefore(current.nextElementSibling, current);
            }
            renumberRows(parent);
            schedulePreview();
        }
    });

    form.addEventListener("input", schedulePreview);
    form.addEventListener("change", schedulePreview);
});

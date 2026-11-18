/**
 * static/js/charts.js - hand-rolled charts, no library.
 *
 * Every chart is an element with data-chart="..." and a JSON data-values
 * attribute. The script builds inline SVG (or styled bars) using the theme's
 * CSS variables, so switching light/dark needs no second data set: it simply
 * re-renders on the "sb:themechange" event.
 *
 * Supported:
 *   data-chart="donut"  [{"label":"Acquired","value":6,"tone":"mint"}, ...]
 *                       optional data-center, data-caption
 *   data-chart="ring"   data-percent="72" data-label="Goals" data-caption="12 of 16"
 *   data-chart="bars"   [{"label":"Python","value":78}, ...] optional data-max
 *   data-chart="line"   data-values="[3,5,2,8]" data-labels='["Mon",...]'
 *   data-chart="spark"  same as line, no axes
 *
 * Accessibility: each chart gets role="img" and an aria-label that states the
 * values in words, so the visual is never the only way to read the data.
 */
(function () {
    "use strict";

    var TONES = {
        accent: "--sb-accent",
        violet: "--sb-violet",
        indigo: "--sb-indigo",
        cyan: "--sb-cyan",
        mint: "--sb-mint",
        coral: "--sb-coral",
        amber: "--sb-amber",
        muted: "--sb-muted",
        line: "--sb-line"
    };

    var SVG_NS = "http://www.w3.org/2000/svg";

    function tone(element, name) {
        var variable = TONES[name] || TONES.accent;
        var value = getComputedStyle(element).getPropertyValue(variable).trim();
        return value || "#6558f5";
    }

    function readJSON(element, name, fallback) {
        var raw = element.getAttribute(name);
        if (!raw) { return fallback; }
        try {
            return JSON.parse(raw);
        } catch (problem) {
            return fallback;
        }
    }

    function reset(element) {
        element.innerHTML = "";
    }

    function svgNode(name, attributes) {
        var node = document.createElementNS(SVG_NS, name);
        Object.keys(attributes || {}).forEach(function (key) {
            node.setAttribute(key, String(attributes[key]));
        });
        return node;
    }

    function uniqueId(element, suffix) {
        var base = element.id || "sb-chart";
        return base + "-" + suffix;
    }

    function motionOff() {
        try {
            return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        } catch (problem) {
            return false;
        }
    }

    /* ------------------------------------------------------------ donut */
    function renderDonut(element) {
        var values = readJSON(element, "data-values", []);
        if (!values.length) { return; }
        var total = values.reduce(function (sum, item) { return sum + Number(item.value || 0); }, 0);
        if (total <= 0) { return; }
        var centre = element.getAttribute("data-center") || String(total);
        var caption = element.getAttribute("data-caption") || "total";
        var withLegend = element.getAttribute("data-legend") !== "false";

        reset(element);
        var wrap = document.createElement("div");
        wrap.className = "chart-donut-wrap";

        var svg = svgNode("svg", { viewBox: "0 0 160 160", role: "presentation", "aria-hidden": "true" });
        var radius = 62;
        var circumference = 2 * Math.PI * radius;
        var track = svgNode("circle", {
            cx: 80, cy: 80, r: radius, fill: "none",
            stroke: tone(element, "line"), "stroke-width": 13, opacity: 0.55
        });
        svg.appendChild(track);

        var offset = 0;
        values.forEach(function (item) {
            var share = Number(item.value || 0) / total;
            var arc = svgNode("circle", {
                cx: 80, cy: 80, r: radius, fill: "none",
                stroke: tone(element, item.tone || "accent"),
                "stroke-width": 13,
                "stroke-linecap": "butt",
                "stroke-dasharray": Math.max(1, share * circumference - 1.5) + " " + Math.max(0, circumference - share * circumference + 1.5),
                "stroke-dashoffset": -offset,
                transform: "rotate(-90 80 80)"
            });
            offset += share * circumference;
            svg.appendChild(arc);
        });

        var valueText = svgNode("text", {
            x: 80, y: 78, "text-anchor": "middle", class: "chart-center",
            "font-size": "26", "font-weight": "700"
        });
        valueText.textContent = centre;
        svg.appendChild(valueText);

        var captionText = svgNode("text", {
            x: 80, y: 94, "text-anchor": "middle", class: "chart-center-sub",
            "font-size": "9", "letter-spacing": "0.08em"
        });
        captionText.textContent = String(caption).toUpperCase();
        svg.appendChild(captionText);

        wrap.appendChild(svg);

        if (withLegend) {
            var legend = document.createElement("ul");
            legend.className = "chart-legend";
            values.forEach(function (item) {
                var row = document.createElement("li");
                var swatch = document.createElement("span");
                swatch.className = "swatch";
                swatch.style.background = tone(element, item.tone || "accent");
                var label = document.createElement("span");
                label.textContent = item.label;
                var count = document.createElement("span");
                count.className = "legend-value";
                count.textContent = Math.round((Number(item.value || 0) / total) * 100) + "%";
                row.appendChild(swatch);
                row.appendChild(label);
                row.appendChild(count);
                legend.appendChild(row);
            });
            wrap.appendChild(legend);
        }

        element.appendChild(wrap);
        element.setAttribute("role", "img");
        element.setAttribute(
            "aria-label",
            values.map(function (item) { return item.label + ": " + item.value; }).join(", ")
        );
    }

    /* ------------------------------------------------------------- ring */
    function renderRing(element) {
        var percent = Math.max(0, Math.min(100, Number(element.getAttribute("data-percent") || 0)));
        var label = element.getAttribute("data-label") || percent + "%";
        var caption = element.getAttribute("data-caption") || "";
        var size = Number(element.getAttribute("data-size") || 120);
        var stroke = Number(element.getAttribute("data-stroke") || 10);
        var radius = (size - stroke) / 2;
        var circumference = 2 * Math.PI * radius;
        var gradientId = uniqueId(element, "grad");
        var colour = tone(element, element.getAttribute("data-tone") || "accent");

        reset(element);
        var svg = svgNode("svg", {
            viewBox: "0 0 " + size + " " + size,
            width: size, height: size, role: "presentation", "aria-hidden": "true"
        });

        var defs = svgNode("defs", {});
        var gradient = svgNode("linearGradient", { id: gradientId, x1: "0", y1: "0", x2: "1", y2: "1" });
        gradient.appendChild(svgNode("stop", { offset: "0%", "stop-color": tone(element, "violet") }));
        gradient.appendChild(svgNode("stop", { offset: "100%", "stop-color": tone(element, element.getAttribute("data-tone") || "cyan") }));
        defs.appendChild(gradient);
        svg.appendChild(defs);

        svg.appendChild(svgNode("circle", {
            cx: size / 2, cy: size / 2, r: radius, fill: "none",
            stroke: tone(element, "line"), "stroke-width": stroke, opacity: 0.55
        }));

        var arc = svgNode("circle", {
            cx: size / 2, cy: size / 2, r: radius, fill: "none",
            stroke: "url(#" + gradientId + ")",
            "stroke-width": stroke,
            "stroke-linecap": "round",
            "stroke-dasharray": circumference,
            "stroke-dashoffset": motionOff() ? circumference * (1 - percent / 100) : circumference,
            transform: "rotate(-90 " + size / 2 + " " + size / 2 + ")"
        });
        svg.appendChild(arc);
        element.appendChild(svg);

        var labelBox = document.createElement("span");
        labelBox.className = "ring-label";
        var strong = document.createElement("strong");
        strong.textContent = label;
        strong.style.color = colour;
        labelBox.appendChild(strong);
        if (caption) {
            var small = document.createElement("span");
            small.textContent = caption;
            labelBox.appendChild(small);
        }
        element.appendChild(labelBox);
        element.classList.add("ring");

        if (!motionOff()) {
            // Force a layout pass, then set the final value: the CSS transition
            // animates it, and throttled rAF environments still get the result.
            void arc.getBoundingClientRect();
            arc.style.transition = "stroke-dashoffset 800ms cubic-bezier(0.22, 0.75, 0.2, 1)";
            arc.setAttribute("stroke-dashoffset", circumference * (1 - percent / 100));
        }

        element.setAttribute("role", "img");
        element.setAttribute("aria-label", (caption ? caption : "Progress") + ": " + percent + " percent");
    }

    /* ------------------------------------------------------------- bars */
    function renderBars(element) {
        var values = readJSON(element, "data-values", []);
        if (!values.length) { return; }
        var explicitMax = Number(element.getAttribute("data-max") || 0);
        var max = explicitMax || Math.max.apply(null, values.map(function (item) { return Number(item.value || 0); })) || 1;

        reset(element);
        var chart = document.createElement("div");
        chart.className = "chart-bars";
        var growth = [];

        values.forEach(function (item) {
            var column = document.createElement("div");
            column.className = "chart-bar-col";

            var track = document.createElement("div");
            track.className = "chart-bar-track";

            var bar = document.createElement("div");
            var toneClass = item.tone ? " chart-bar--" + item.tone : "";
            var share = Math.max(2, Math.round((Number(item.value || 0) / max) * 100));
            bar.className = "chart-bar" + toneClass;
            bar.style.height = motionOff() ? share + "%" : "0%";

            var value = document.createElement("span");
            value.className = "chart-bar-value";
            value.textContent = item.display != null ? item.display : item.value;
            track.appendChild(bar);
            track.appendChild(value);

            var label = document.createElement("span");
            label.className = "chart-bar-label";
            label.textContent = item.label;
            label.title = item.label;

            column.appendChild(track);
            column.appendChild(label);
            chart.appendChild(column);
            growth.push([bar, share]);
        });

        element.appendChild(chart);

        if (motionOff()) {
            growth.forEach(function (pair) { pair[0].style.height = pair[1] + "%"; });
        } else {
            void chart.getBoundingClientRect();      // start from the 0% state
            growth.forEach(function (pair) { pair[0].style.height = pair[1] + "%"; });
        }
        element.setAttribute("role", "img");
        element.setAttribute(
            "aria-label",
            values.map(function (item) { return item.label + ": " + (item.display != null ? item.display : item.value); }).join(", ")
        );
    }

    /* ------------------------------------------------------------- line */
    function renderLine(element, spark) {
        var values = readJSON(element, "data-values", []);
        if (values.length < 2) { return; }
        var labels = readJSON(element, "data-labels", []);
        var width = 600;
        var height = spark ? 44 : 170;
        var pad = spark ? 3 : 14;
        var max = Math.max.apply(null, values) || 1;
        var min = Math.min.apply(null, values);
        var span = max - min || 1;
        var stepX = (width - pad * 2) / (values.length - 1);

        var points = values.map(function (value, index) {
            var x = pad + index * stepX;
            var y = height - pad - ((value - min) / span) * (height - pad * 2);
            return [x, y];
        });

        // A light smoothing pass keeps the line elegant without hiding the data.
        var path = "M " + points[0][0] + " " + points[0][1];
        for (var index = 1; index < points.length; index += 1) {
            var previous = points[index - 1];
            var point = points[index];
            var midX = (previous[0] + point[0]) / 2;
            path += " C " + midX + " " + previous[1] + ", " + midX + " " + point[1] + ", " + point[0] + " " + point[1];
        }
        var area = path + " L " + points[points.length - 1][0] + " " + height + " L " + points[0][0] + " " + height + " Z";
        var gradientId = uniqueId(element, spark ? "spark" : "line");

        reset(element);
        var svg = svgNode("svg", {
            viewBox: "0 0 " + width + " " + height,
            preserveAspectRatio: "none",
            style: spark ? "height:44px" : "height:170px",
            role: "presentation", "aria-hidden": "true"
        });
        var defs = svgNode("defs", {});
        var gradient = svgNode("linearGradient", { id: gradientId, x1: "0", y1: "0", x2: "0", y2: "1" });
        gradient.appendChild(svgNode("stop", { offset: "0%", "stop-color": tone(element, "accent"), "stop-opacity": "0.35" }));
        gradient.appendChild(svgNode("stop", { offset: "100%", "stop-color": tone(element, "accent"), "stop-opacity": "0" }));
        defs.appendChild(gradient);
        svg.appendChild(defs);

        if (!spark) {
            [0.25, 0.5, 0.75].forEach(function (share) {
                var y = pad + (height - pad * 2) * share;
                svg.appendChild(svgNode("line", {
                    x1: pad, x2: width - pad, y1: y, y2: y, class: "chart-line-grid",
                    "stroke-width": 1, "vector-effect": "non-scaling-stroke"
                }));
            });
        }

        svg.appendChild(svgNode("path", {
            d: area, fill: "url(#" + gradientId + ")", stroke: "none"
        }));
        svg.appendChild(svgNode("path", {
            d: path, class: "chart-line-path", "vector-effect": "non-scaling-stroke"
        }));

        if (!spark) {
            points.forEach(function (point) {
                svg.appendChild(svgNode("circle", {
                    cx: point[0], cy: point[1], r: 3.4, class: "chart-line-dot",
                    "vector-effect": "non-scaling-stroke"
                }));
            });
        }

        element.appendChild(svg);

        if (!spark && labels.length === values.length) {
            var row = document.createElement("div");
            row.className = "chart-line-labels";
            labels.forEach(function (text) {
                var item = document.createElement("span");
                item.textContent = text;
                row.appendChild(item);
            });
            element.appendChild(row);
        }

        element.setAttribute("role", "img");
        element.setAttribute("aria-label", "Values: " + values.join(", "));
    }

    /* ------------------------------------------------------------- boot */
    function renderAll(root) {
        var scope = root || document;
        scope.querySelectorAll('[data-chart="donut"]').forEach(renderDonut);
        scope.querySelectorAll('[data-chart="ring"]').forEach(renderRing);
        scope.querySelectorAll('[data-chart="bars"]').forEach(renderBars);
        scope.querySelectorAll('[data-chart="line"]').forEach(function (element) { renderLine(element, false); });
        scope.querySelectorAll('[data-chart="spark"]').forEach(function (element) { renderLine(element, true); });
    }

    document.addEventListener("DOMContentLoaded", function () { renderAll(document); });

    // Colours come from CSS variables, so a theme change re-renders once.
    window.addEventListener("sb:themechange", function () { renderAll(document); });

    window.SkillBridgeCharts = { render: renderAll };
})();

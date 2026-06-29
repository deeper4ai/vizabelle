(function () {
  const root = document.documentElement;
  const splitter = document.querySelector(".splitter");
  const overviewSvg = document.querySelector(".overview-svg");
  const stepFrame = document.querySelector('iframe[name="step-frame"]');
  const zoomReadout = document.querySelector(".zoom-readout");
  const menuButton = document.querySelector("[data-menu-toggle]");
  const libraryMenu = document.querySelector("[data-library-menu]");
  const widthStorageKey = "vizabell.leftPaneWidth";
  const zoomStorageKey = "vizabell.overviewZoom";
  const minZoom = 0.35;
  const maxZoom = 3;
  const zoomStep = 0.05;

  function activeOverviewGraph() {
    return overviewSvg
      ? overviewSvg.querySelector(".overview-graph:not([hidden])")
      : null;
  }

  function activeOverviewSvg() {
    const graph = activeOverviewGraph();
    return graph ? graph.querySelector("svg") : null;
  }

  function readStorage(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (_error) {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (_error) {
      // Local file privacy settings can disable storage; resizing still works.
    }
  }

  const savedWidth = readStorage(widthStorageKey);
  if (savedWidth) {
    root.style.setProperty("--left-pane-width", savedWidth);
  }

  if (menuButton && libraryMenu) {
    menuButton.addEventListener("click", () => {
      const expanded = menuButton.getAttribute("aria-expanded") === "true";
      menuButton.setAttribute("aria-expanded", expanded ? "false" : "true");
      libraryMenu.hidden = expanded;
    });
    document.addEventListener("click", (event) => {
      if (
        libraryMenu.hidden
        || menuButton.contains(event.target)
        || libraryMenu.contains(event.target)
      ) {
        return;
      }
      menuButton.setAttribute("aria-expanded", "false");
      libraryMenu.hidden = true;
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !libraryMenu.hidden) {
        menuButton.setAttribute("aria-expanded", "false");
        libraryMenu.hidden = true;
        menuButton.focus();
      }
    });
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  const overviewHeading = document.querySelector(".overview-heading");
  const overviewViewport = document.querySelector(".overview-viewport");

  function syncHeadingOffset() {
    if (!overviewHeading || !overviewViewport) {
      return;
    }
    const offset = overviewViewport.getBoundingClientRect().top
      - overviewHeading.getBoundingClientRect().top;
    root.style.setProperty("--overview-heading-offset", `${offset}px`);
  }

  syncHeadingOffset();
  if (overviewHeading && window.ResizeObserver) {
    new ResizeObserver(syncHeadingOffset).observe(overviewHeading);
  } else {
    window.addEventListener("resize", syncHeadingOffset);
  }

  function setZoom(value) {
    const zoom = clamp(Math.round(value * 20) / 20, minZoom, maxZoom);
    root.style.setProperty("--overview-zoom", zoom.toFixed(2));
    if (overviewSvg) {
      const svg = activeOverviewSvg();
      if (svg) {
        const widthAttr = Number.parseFloat(svg.getAttribute("width") || "");
        const heightAttr = Number.parseFloat(svg.getAttribute("height") || "");
        const baseWidth = svg.viewBox.baseVal && svg.viewBox.baseVal.width
          ? svg.viewBox.baseVal.width
          : widthAttr || svg.getBoundingClientRect().width / zoom;
        const baseHeight = svg.viewBox.baseVal && svg.viewBox.baseVal.height
          ? svg.viewBox.baseVal.height
          : heightAttr || svg.getBoundingClientRect().height / zoom;
        overviewSvg.style.width = Math.ceil(baseWidth * zoom) + "px";
        overviewSvg.style.height = Math.ceil(baseHeight * zoom) + "px";
      }
    }
    if (zoomReadout) {
      zoomReadout.textContent = Math.round(zoom * 100) + "%";
    }
    writeStorage(zoomStorageKey, zoom.toFixed(2));
  }

  function baseSvgSize() {
    if (!overviewSvg) {
      return null;
    }
    const svg = activeOverviewSvg();
    if (!svg) {
      return null;
    }
    const widthValue = svg.width && svg.width.baseVal ? svg.width.baseVal.value : 0;
    const heightValue = svg.height && svg.height.baseVal ? svg.height.baseVal.value : 0;
    return {
      width: widthValue || svg.getBoundingClientRect().width,
      height: heightValue || svg.getBoundingClientRect().height,
    };
  }

  function fitZoom() {
    const viewport = document.querySelector(".overview-viewport");
    const size = baseSvgSize();
    if (!viewport || !size || !size.width || !size.height) {
      return 1;
    }
    const padding = 10;
    const widthRatio = Math.max(0.1, (viewport.clientWidth - padding) / size.width);
    const heightRatio = Math.max(0.1, (viewport.clientHeight - padding) / size.height);
    return clamp(Math.min(1, widthRatio, heightRatio), minZoom, maxZoom);
  }

  const savedZoomText = readStorage(zoomStorageKey);
  const savedZoom = Number.parseFloat(savedZoomText || "");
  setZoom(savedZoomText && Number.isFinite(savedZoom) ? savedZoom : fitZoom());

  const fitButton = document.querySelector("[data-zoom-fit]");
  if (fitButton) {
    fitButton.addEventListener("click", () => {
      setZoom(fitZoom());
    });
  }

  const proofViewButton = document.querySelector("[data-proof-view-toggle]");
  if (proofViewButton && overviewSvg) {
    proofViewButton.addEventListener("click", () => {
      const fullGraph = overviewSvg.querySelector('[data-proof-view="full"]');
      const flatGraph = overviewSvg.querySelector('[data-proof-view="flat"]');
      if (!fullGraph || !flatGraph) {
        return;
      }
      const showFlat = flatGraph.hidden;
      fullGraph.hidden = showFlat;
      flatGraph.hidden = !showFlat;
      proofViewButton.textContent = showFlat ? "Full" : "Flat";
      proofViewButton.setAttribute(
        "aria-label",
        showFlat ? "Show full proof" : "Show flat proof"
      );
      proofViewButton.setAttribute(
        "title",
        showFlat ? "Show complete proof" : "Compact linear proof chains"
      );
      setZoom(fitZoom());
      syncSelectionFromFrame();
    });
  }

  document.querySelectorAll("[data-zoom]").forEach((button) => {
    button.addEventListener("click", () => {
      const current = Number.parseFloat(
        getComputedStyle(root).getPropertyValue("--overview-zoom")
      ) || 1;
      const direction = button.getAttribute("data-zoom") === "in" ? 1 : -1;
      setZoom(current + direction * zoomStep);
    });
  });

  function stepKeyFromUrl(value) {
    if (!value) {
      return "";
    }
    let part = "";
    try {
      const url = new URL(value, window.location.href);
      part = url.pathname.split("/").pop() || "";
    } catch (_error) {
      part = value.split("/").pop() || "";
    }
    part = decodeURIComponent(part);
    return part.endsWith(".html") ? part.slice(0, -5) : part;
  }

  function svgLinkHref(link) {
    return link.getAttribute("href")
      || link.getAttribute("xlink:href")
      || link.getAttributeNS("http://www.w3.org/1999/xlink", "href")
      || "";
  }

  function closestLink(target) {
    let node = target;
    while (node && node !== document) {
      if (node.tagName && node.tagName.toLowerCase() === "a") {
        return node;
      }
      node = node.parentNode;
    }
    return null;
  }

  function closestOverviewNode(target) {
    let node = target;
    while (node && node !== overviewSvg) {
      if (node.classList && node.classList.contains("node")) {
        return node;
      }
      node = node.parentNode;
    }
    return null;
  }

  if (overviewSvg) {
    overviewSvg.querySelectorAll("a").forEach((link) => {
      const stepKey = stepKeyFromUrl(svgLinkHref(link));
      const node = closestOverviewNode(link);
      if (stepKey && node) {
        link.addEventListener("click", () => {
          setSelectedOverviewNode(stepKey);
        });
      }
    });
  }

  function setSelectedOverviewNode(stepKey) {
    if (!overviewSvg || !stepKey) {
      return;
    }
    overviewSvg.querySelectorAll(".selected-overview-node").forEach((node) => {
      node.classList.remove("selected-overview-node");
    });
    const graph = activeOverviewGraph();
    const node = graph
      ? Array.from(graph.querySelectorAll("a")).map((link) => ({
          link,
          node: closestOverviewNode(link),
        })).find(({ link }) => stepKeyFromUrl(svgLinkHref(link)) === stepKey)?.node
      : null;
    if (node) {
      node.classList.add("selected-overview-node");
    }
  }

  if (overviewSvg) {
    overviewSvg.addEventListener("click", (event) => {
      const link = closestLink(event.target);
      if (link) {
        setSelectedOverviewNode(stepKeyFromUrl(svgLinkHref(link)));
      }
    });
  }

  function syncSelectionFromFrame() {
    if (!stepFrame) {
      return;
    }
    try {
      const frameDocument = stepFrame.contentDocument;
      if (!frameDocument) {
        return;
      }
      setSelectedOverviewNode(stepKeyFromUrl(frameDocument.location.href));
      if (!frameDocument.body || frameDocument.body.dataset.selectionSync === "ready") {
        return;
      }
      frameDocument.body.dataset.selectionSync = "ready";
      frameDocument.addEventListener("click", (event) => {
        const link = closestLink(event.target);
        if (link) {
          setSelectedOverviewNode(stepKeyFromUrl(svgLinkHref(link)));
        }
      }, true);
    } catch (_error) {
      // Some browsers restrict file iframe access; overview clicks still update selection.
    }
  }

  if (stepFrame) {
    setSelectedOverviewNode(stepKeyFromUrl(stepFrame.getAttribute("src") || ""));
    stepFrame.addEventListener("load", syncSelectionFromFrame);
  }

  if (overviewViewport) {
    overviewViewport.addEventListener("wheel", (event) => {
      if (!event.ctrlKey && !event.metaKey) {
        return;
      }
      event.preventDefault();
      const current = Number.parseFloat(
        getComputedStyle(root).getPropertyValue("--overview-zoom")
      ) || 1;
      const direction = event.deltaY < 0 ? 1 : -1;
      setZoom(current + direction * zoomStep);
    }, { passive: false });
  }

  if (!splitter) {
    return;
  }

  let dragging = false;

  function setWidth(clientX) {
    const viewportWidth = window.innerWidth;
    const min = 260;
    const max = Math.max(min, viewportWidth - 420);
    const clamped = Math.min(max, Math.max(min, clientX));
    const percent = (clamped / viewportWidth) * 100;
    const value = percent.toFixed(2) + "%";
    root.style.setProperty("--left-pane-width", value);
    writeStorage(widthStorageKey, value);
  }

  splitter.addEventListener("pointerdown", (event) => {
    dragging = true;
    splitter.setPointerCapture(event.pointerId);
    document.body.classList.add("resizing");
    event.preventDefault();
  });

  splitter.addEventListener("pointermove", (event) => {
    if (!dragging) {
      return;
    }
    setWidth(event.clientX);
  });

  function stopDragging(event) {
    if (!dragging) {
      return;
    }
    dragging = false;
    document.body.classList.remove("resizing");
    if (splitter.hasPointerCapture(event.pointerId)) {
      splitter.releasePointerCapture(event.pointerId);
    }
  }

  splitter.addEventListener("pointerup", stopDragging);
  splitter.addEventListener("pointercancel", stopDragging);
})();

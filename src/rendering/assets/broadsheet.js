(function () {
  const dataEl = document.getElementById("horizon-edition-data");
  const copyEl = document.getElementById("horizon-edition-copy");
  if (!dataEl || !copyEl) return;

  const edition = JSON.parse(dataEl.textContent || "{}");
  const copy = JSON.parse(copyEl.textContent || "{}");
  const items = edition.items || [];
  const itemsById = new Map(items.map((item) => [item.id, item]));

  // Theme management
  const root = document.documentElement;
  const themeBtns = document.querySelectorAll("[data-theme-set]");
  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    try { localStorage.setItem("horizon-broadsheet-theme", theme); } catch (_) {}
    themeBtns.forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-theme-set") === theme);
    });
  }
  let savedTheme = "light";
  try { savedTheme = localStorage.getItem("horizon-broadsheet-theme") || "light"; } catch (_) {}
  applyTheme(savedTheme);
  themeBtns.forEach((btn) => {
    btn.addEventListener("click", () => applyTheme(btn.getAttribute("data-theme-set") || "light"));
  });

  // Font size toggle
  const fontBtns = document.querySelectorAll("[data-font-set]");
  function applyFont(size) {
    root.setAttribute("data-font", size);
    try { localStorage.setItem("horizon-broadsheet-font", size); } catch (_) {}
    fontBtns.forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-font-set") === size);
    });
  }
  let savedFont = "normal";
  try { savedFont = localStorage.getItem("horizon-broadsheet-font") || "normal"; } catch (_) {}
  applyFont(savedFont);
  fontBtns.forEach((btn) => {
    btn.addEventListener("click", () => applyFont(btn.getAttribute("data-font-set") || "normal"));
  });

  // Print button
  const printBtn = document.getElementById("printBtn");
  if (printBtn) printBtn.addEventListener("click", () => window.print());

  // Edition Archive Switcher (loads ./editions.json when served over HTTP/HTTPS)
  const archiveWrap = document.getElementById("editionArchiveWrap");
  const archiveSelect = document.getElementById("editionArchiveSelect");
  const currentDate = (edition.meta && edition.meta.date) || "";
  const currentLang = (edition.meta && edition.meta.language) || "zh";

  if (archiveWrap && archiveSelect && typeof fetch === "function" && location.protocol !== "file:") {
    fetch("./editions.json", { cache: "no-cache" })
      .then((res) => (res.ok ? res.json() : null))
      .then((manifest) => {
        if (!manifest || !Array.isArray(manifest.editions) || !manifest.editions.length) return;
        archiveSelect.innerHTML = "";
        manifest.editions.forEach((entry, idx) => {
          const opt = document.createElement("option");
          const langs = Array.isArray(entry.languages) ? entry.languages : [];
          const targetLang = langs.includes(currentLang) ? currentLang : (langs[0] || currentLang);
          opt.value = `./${entry.date}-${targetLang}.html`;
          const count = entry.selected_count && entry.selected_count[targetLang];
          const suffix = idx === 0 ? ` · ${copy.archive_latest || "Latest"}` : "";
          const countSuffix = typeof count === "number" ? ` (${count})` : "";
          opt.textContent = `${entry.date}${suffix}${countSuffix}`;
          if (entry.date === currentDate) opt.selected = true;
          archiveSelect.appendChild(opt);
        });
        archiveWrap.hidden = false;
        archiveSelect.addEventListener("change", () => {
          if (archiveSelect.value) window.location.href = archiveSelect.value;
        });
      })
      .catch(() => {});
  }

  // Article Reading Drawer
  const drawer = document.getElementById("articleDrawer");
  const backdrop = document.getElementById("drawerBackdrop");
  const drawerKicker = document.getElementById("drawerKicker");
  const drawerBadges = document.getElementById("drawerBadges");
  const drawerTitle = document.getElementById("drawerTitle");
  const drawerMeta = document.getElementById("drawerMeta");
  const drawerHeadLinks = document.getElementById("drawerHeadLinks");
  const drawerBlocks = document.getElementById("drawerBlocks");
  const drawerRefs = document.getElementById("drawerRefs");
  const drawerTags = document.getElementById("drawerTags");
  const drawerExtLinks = document.getElementById("drawerExtLinks");
  const drawerPrev = document.getElementById("drawerPrev");
  const drawerNext = document.getElementById("drawerNext");
  const drawerClose = document.getElementById("drawerClose");
  let currentStoryIdx = -1;

  function makeEl(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function openStory(storyId) {
    const story = itemsById.get(storyId);
    if (!story || !drawer || !backdrop) return;
    currentStoryIdx = items.findIndex((i) => i.id === storyId);

    drawerKicker.textContent = `${story.profile_name} · #${story.rank}`;
    drawerBadges.innerHTML = "";
    const scorePill = makeEl(
      "span",
      `score-pill ${(story.score || 0) >= 8.5 ? "score-hot" : "score-accent"}`,
      `${copy.drawer_score || "AI"}: ${story.score_display}/10`
    );
    drawerBadges.appendChild(scorePill);
    drawerBadges.appendChild(makeEl("span", "profile-tag", story.source_label));
    if (story.category) {
      drawerBadges.appendChild(makeEl("span", "profile-tag", story.category));
    }

    drawerTitle.textContent = story.title;
    const metaParts = [story.sub_source, story.time_display, ...(story.engagement || [])].filter(Boolean);
    drawerMeta.textContent = metaParts.join(" · ");

    if (drawerHeadLinks) {
      drawerHeadLinks.innerHTML = "";
      if (story.url) {
        const label = story.domain
          ? `${copy.original_link || "Original ↗"} (${story.domain})`
          : (copy.original_link || "Original ↗");
        const a = makeEl("a", "editorial-link", label);
        a.href = story.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        drawerHeadLinks.appendChild(a);
      }
      if (story.discussion_url) {
        const a = makeEl("a", "editorial-link", copy.discussion_link || "Discussion ↗");
        a.href = story.discussion_url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        drawerHeadLinks.appendChild(a);
      }
    }

    drawerBlocks.innerHTML = "";
    const blocks = (story.blocks && story.blocks.length)
      ? story.blocks
      : [{ title: copy.nav_front || "Summary", content: story.summary || "" }];
    blocks.forEach((blk) => {
      if (!blk.content) return;
      const box = makeEl("section", "drawer-block");
      box.appendChild(makeEl("div", "drawer-block-title", blk.title));
      box.appendChild(makeEl("p", "drawer-block-text", blk.content));
      drawerBlocks.appendChild(box);
    });

    drawerRefs.innerHTML = "";
    if (story.references && story.references.length) {
      drawerRefs.hidden = false;
      drawerRefs.appendChild(makeEl("div", "kicker", copy.drawer_refs || "References"));
      const ul = document.createElement("ul");
      story.references.forEach((ref) => {
        const li = document.createElement("li");
        if (ref.url) {
          const a = makeEl("a", "", ref.title || ref.url);
          a.href = ref.url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          li.appendChild(a);
          if (ref.domain) li.appendChild(document.createTextNode(` (${ref.domain})`));
        } else {
          li.textContent = ref.title;
        }
        ul.appendChild(li);
      });
      drawerRefs.appendChild(ul);
    } else {
      drawerRefs.hidden = true;
    }

    drawerTags.innerHTML = "";
    if (story.tags && story.tags.length) {
      drawerTags.hidden = false;
      drawerTags.appendChild(makeEl("div", "kicker", copy.drawer_tags || "Tags"));
      const row = makeEl("div", "tag-row");
      story.tags.forEach((tag) => {
        const btn = makeEl("button", "tag-chip", `#${tag}`);
        btn.type = "button";
        btn.addEventListener("click", () => {
          closeDrawer();
          filterByTag(tag);
        });
        row.appendChild(btn);
      });
      drawerTags.appendChild(row);
    } else {
      drawerTags.hidden = true;
    }

    drawerExtLinks.innerHTML = "";
    if (story.url) {
      const a = makeEl("a", "editorial-link", copy.original_link || "Original ↗");
      a.href = story.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      drawerExtLinks.appendChild(a);
    }
    if (story.discussion_url) {
      const a = makeEl("a", "editorial-link", copy.discussion_link || "Discussion ↗");
      a.href = story.discussion_url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      drawerExtLinks.appendChild(a);
    }

    drawerPrev.disabled = currentStoryIdx <= 0;
    drawerNext.disabled = currentStoryIdx < 0 || currentStoryIdx >= items.length - 1;

    drawer.hidden = false;
    backdrop.hidden = false;
    document.body.style.overflow = "hidden";
    const scroller = document.getElementById("drawerBody");
    if (scroller) scroller.scrollTop = 0;
  }

  function closeDrawer() {
    if (!drawer || !backdrop) return;
    drawer.hidden = true;
    backdrop.hidden = true;
    document.body.style.overflow = "";
  }

  if (drawerClose) drawerClose.addEventListener("click", closeDrawer);
  if (backdrop) backdrop.addEventListener("click", closeDrawer);
  if (drawerPrev) {
    drawerPrev.addEventListener("click", () => {
      if (currentStoryIdx > 0) openStory(items[currentStoryIdx - 1].id);
    });
  }
  if (drawerNext) {
    drawerNext.addEventListener("click", () => {
      if (currentStoryIdx >= 0 && currentStoryIdx < items.length - 1) openStory(items[currentStoryIdx + 1].id);
    });
  }

  // Archive Desk Filtering
  const searchInput = document.getElementById("archiveSearch");
  const sortSelect = document.getElementById("archiveSort");
  const resetBtn = document.getElementById("archiveReset");
  const ledgerEl = document.getElementById("archiveLedger");
  const activeTagBar = document.getElementById("activeTagBar");
  const profileBar = document.getElementById("profileFilterBar");
  const sourceBar = document.getElementById("sourceFilterBar");

  const filterState = { query: "", profile: "all", source: "all", tag: "", sort: "score" };

  function renderLedger() {
    if (!ledgerEl) return;
    const q = filterState.query.trim().toLowerCase();
    const filtered = items.filter((story) => {
      if (filterState.profile !== "all" && story.profile_id !== filterState.profile) return false;
      if (filterState.source !== "all" && story.source_type !== filterState.source) return false;
      if (filterState.tag && !(story.tags || []).includes(filterState.tag)) return false;
      if (q) {
        const hay = [
          story.title, story.summary, story.sub_source, story.source_label,
          story.profile_name, ...(story.tags || [])
        ].join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    filtered.sort((a, b) => {
      if (filterState.sort === "time") {
        return (b.published_at || "").localeCompare(a.published_at || "");
      }
      return (b.score ?? -1) - (a.score ?? -1) || a.rank - b.rank;
    });

    if (activeTagBar) {
      activeTagBar.innerHTML = "";
      if (filterState.tag) {
        activeTagBar.hidden = false;
        activeTagBar.appendChild(makeEl("span", "", `${copy.active_tag_prefix || "Tag: #"}${filterState.tag}`));
        const clearTag = makeEl("button", "util-btn", "×");
        clearTag.type = "button";
        clearTag.addEventListener("click", () => {
          filterState.tag = "";
          renderLedger();
        });
        activeTagBar.appendChild(clearTag);
      } else {
        activeTagBar.hidden = true;
      }
    }

    ledgerEl.innerHTML = "";
    if (!filtered.length) {
      ledgerEl.appendChild(makeEl("div", "ledger-empty", copy.no_match || "No matches."));
      return;
    }

    filtered.forEach((story) => {
      const card = makeEl("article", "ledger-item");
      const top = makeEl("div", "ledger-top");
      top.appendChild(
        makeEl("span", "ledger-meta", `${story.source_label} · ${story.sub_source} · ${story.time_display}`)
      );
      top.appendChild(
        makeEl(
          "span",
          `score-pill ${(story.score || 0) >= 8.5 ? "score-hot" : "score-accent"}`,
          story.score_display
        )
      );
      card.appendChild(top);

      const h3 = makeEl("h3", "ledger-title");
      const btn = makeEl("button", "headline-trigger", story.title);
      btn.type = "button";
      btn.addEventListener("click", () => openStory(story.id));
      h3.appendChild(btn);
      card.appendChild(h3);

      const summary = story.summary.length > 140 ? `${story.summary.slice(0, 139)}…` : story.summary;
      card.appendChild(makeEl("p", "ledger-summary", summary));

      const foot = makeEl("div", "ledger-foot");
      foot.appendChild(makeEl("span", "profile-tag", story.profile_name));
      foot.appendChild(makeEl("span", "ledger-tags", (story.tags || []).slice(0, 3).map((t) => `#${t}`).join(" ")));
      const linksWrap = makeEl("span", "inline-links");
      if (story.url) {
        const orig = makeEl("a", "inline-ext-link", copy.source_link || "Source ↗");
        orig.href = story.url;
        orig.target = "_blank";
        orig.rel = "noopener noreferrer";
        linksWrap.appendChild(orig);
      }
      if (story.discussion_url) {
        const disc = makeEl("a", "inline-ext-link", copy.discuss_short || "Discuss ↗");
        disc.href = story.discussion_url;
        disc.target = "_blank";
        disc.rel = "noopener noreferrer";
        linksWrap.appendChild(disc);
      }
      if (linksWrap.childNodes.length) foot.appendChild(linksWrap);
      card.appendChild(foot);
      ledgerEl.appendChild(card);
    });
  }

  function filterByTag(tag) {
    filterState.tag = tag;
    renderLedger();
    const desk = document.getElementById("archive-desk");
    if (desk) desk.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      filterState.query = searchInput.value;
      renderLedger();
    });
  }
  if (sortSelect) {
    sortSelect.addEventListener("change", () => {
      filterState.sort = sortSelect.value;
      renderLedger();
    });
  }
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      filterState.query = "";
      filterState.profile = "all";
      filterState.source = "all";
      filterState.tag = "";
      filterState.sort = "score";
      if (searchInput) searchInput.value = "";
      if (sortSelect) sortSelect.value = "score";
      if (profileBar) {
        profileBar.querySelectorAll(".filter-pill").forEach((p) => {
          p.classList.toggle("is-active", p.getAttribute("data-filter-profile") === "all");
        });
      }
      if (sourceBar) {
        sourceBar.querySelectorAll(".filter-pill").forEach((p) => {
          p.classList.toggle("is-active", p.getAttribute("data-filter-source") === "all");
        });
      }
      renderLedger();
    });
  }

  if (profileBar) {
    profileBar.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-filter-profile]");
      if (!btn) return;
      filterState.profile = btn.getAttribute("data-filter-profile") || "all";
      profileBar.querySelectorAll(".filter-pill").forEach((p) => p.classList.toggle("is-active", p === btn));
      renderLedger();
    });
  }
  if (sourceBar) {
    sourceBar.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-filter-source]");
      if (!btn) return;
      filterState.source = btn.getAttribute("data-filter-source") || "all";
      sourceBar.querySelectorAll(".filter-pill").forEach((p) => p.classList.toggle("is-active", p === btn));
      renderLedger();
    });
  }

  // Delegated clicks for story triggers and tag chips anywhere on the broadsheet
  document.addEventListener("click", (e) => {
    const storyTrigger = e.target.closest("[data-open-story]");
    if (storyTrigger) {
      openStory(storyTrigger.getAttribute("data-open-story"));
      return;
    }
    const tagTrigger = e.target.closest("[data-filter-tag]");
    if (tagTrigger) {
      filterByTag(tagTrigger.getAttribute("data-filter-tag") || "");
    }
  });

  // Jump-to-search button & keyboard shortcuts
  function focusSearch() {
    if (!searchInput) return;
    const desk = document.getElementById("archive-desk");
    if (desk) desk.scrollIntoView({ behavior: "smooth", block: "start" });
    setTimeout(() => searchInput.focus(), 220);
  }
  const jumpSearchBtn = document.getElementById("jumpSearchBtn");
  if (jumpSearchBtn) jumpSearchBtn.addEventListener("click", focusSearch);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeDrawer();
      if (pagerMenu) pagerMenu.hidden = true;
      if (pagerBtn) pagerBtn.setAttribute("aria-expanded", "false");
      return;
    }
    if (drawer && !drawer.hidden) {
      if (e.key === "ArrowLeft" && currentStoryIdx > 0) openStory(items[currentStoryIdx - 1].id);
      if (e.key === "ArrowRight" && currentStoryIdx < items.length - 1) openStory(items[currentStoryIdx + 1].id);
      return;
    }
    if ((e.key === "/" || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k")) &&
        document.activeElement !== searchInput) {
      e.preventDefault();
      focusSearch();
    }
  });

  // Floating Pager & Return-to-Front-Page Pill
  const pagerBtn = document.getElementById("pagerBtn");
  const pagerMenu = document.getElementById("pagerMenu");
  const pagerActiveCode = document.getElementById("pagerActiveCode");
  const pagerActiveLabel = document.getElementById("pagerActiveLabel");
  const homePill = document.getElementById("homePill");

  if (pagerBtn && pagerMenu) {
    pagerBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const willOpen = pagerMenu.hidden;
      pagerMenu.hidden = !willOpen;
      pagerBtn.setAttribute("aria-expanded", String(willOpen));
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest("#pagerWrap")) {
        pagerMenu.hidden = true;
        pagerBtn.setAttribute("aria-expanded", "false");
      }
    });
    pagerMenu.addEventListener("click", () => {
      pagerMenu.hidden = true;
      pagerBtn.setAttribute("aria-expanded", "false");
    });
  }

  const bands = Array.from(document.querySelectorAll("section[data-page-code]"));
  function setActiveSection(code, label) {
    if (pagerActiveCode) pagerActiveCode.textContent = code;
    if (pagerActiveLabel) pagerActiveLabel.textContent = label;
    document.querySelectorAll("[data-section-link]").forEach((el) => {
      el.classList.toggle("is-current", el.getAttribute("data-section-link") === code);
    });
    document.querySelectorAll("[data-pager-code]").forEach((el) => {
      el.classList.toggle("is-active", el.getAttribute("data-pager-code") === code);
    });
  }

  if ("IntersectionObserver" in window && bands.length) {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length) {
          const target = visible[0].target;
          setActiveSection(
            target.getAttribute("data-page-code") || "A1",
            target.getAttribute("data-page-label") || ""
          );
        }
      },
      { rootMargin: "-15% 0px -65% 0px", threshold: 0.01 }
    );
    bands.forEach((b) => observer.observe(b));
  }

  window.addEventListener(
    "scroll",
    () => {
      if (homePill) homePill.classList.toggle("is-visible", window.scrollY > 360);
    },
    { passive: true }
  );
})();

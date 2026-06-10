const notice = document.querySelector("#notice");
const currentMode = document.body.dataset.mode || "ds";
const filters = document.querySelector(".filters");

function showNotice(message, type = "info") {
  notice.textContent = message;
  notice.className = `notice ${type}`;
  notice.hidden = false;
}

function setLoading(element, loading, text) {
  if (!element) return;
  if (loading) {
    element.dataset.originalText = element.textContent;
    element.textContent = text || "处理中...";
    element.disabled = true;
  } else {
    element.textContent = element.dataset.originalText || element.textContent;
    element.disabled = false;
  }
}

async function postJson(url, payload = null) {
  const options = { method: "POST" };
  if (payload !== null) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(url, options);
  let data = {};
  try {
    data = await response.json();
  } catch (error) {
    data = {};
  }
  if (!response.ok) {
    throw new Error(data.detail || `请求失败：${response.status}`);
  }
  return data;
}

function collectMeta(card) {
  const payload = {};
  for (const field of ["user_note", "tags", "reading_level"]) {
    const element = card.querySelector(`[data-field="${field}"]`);
    if (element) payload[field] = element.value;
  }
  return payload;
}

function updateReadStatus(card, value) {
  const labels = {
    unread: "未读",
    opened: "已打开",
    read: "已读",
    to_read: "待读",
    filtered: "已过滤",
  };
  const status = card.querySelector(".read-status");
  if (status) status.textContent = `状态：${labels[value] || value}`;
}

function updateReadingLevel(card, value) {
  const labels = {
    none: "未分类",
    skim: "摘要够了",
    readable: "可读",
    deep_read: "精读",
  };
  const element = card.querySelector(".reading-level");
  if (element) element.textContent = `可读性：${labels[value] || value}`;
}

function updateFavorite(card, favorite) {
  card.dataset.favorite = favorite ? "1" : "0";
  const button = card.querySelector('[data-action="toggle-favorite"]');
  if (button) button.textContent = favorite ? "取消收藏" : "收藏";
  let badge = card.querySelector(".favorite-badge");
  const meta = card.querySelector(".meta");
  if (favorite && !badge && meta) {
    badge = document.createElement("span");
    badge.className = "favorite-badge";
    badge.textContent = "收藏";
    meta.appendChild(badge);
  }
  if (!favorite && badge) badge.remove();
}

function updateZotero(card, statusValue) {
  const saved = statusValue === "saved";
  const button = card.querySelector('[data-action="save-zotero"]');
  if (button) {
    button.dataset.zoteroStatus = statusValue;
    button.textContent = saved ? "已入 Zotero" : "存入 Zotero";
  }
  let badge = card.querySelector(".zotero-badge");
  const meta = card.querySelector(".meta");
  if (saved && !badge && meta) {
    badge = document.createElement("span");
    badge.className = "zotero-badge";
    badge.textContent = "已入 Zotero";
    meta.appendChild(badge);
  }
  if (!saved && badge) badge.remove();
}

function selectedArticleIds() {
  return [...document.querySelectorAll(".article-select:checked")].map((item) => Number(item.value));
}

function readStatusFilter() {
  return new URLSearchParams(window.location.search).get("read_status") || "";
}

function shouldKeepArticleVisible(readStatus) {
  const filter = readStatusFilter();
  if (filter) return readStatus === filter;
  return !["read", "filtered"].includes(readStatus);
}

function showEmptyIfNoArticles() {
  const articles = document.querySelector(".articles");
  if (!articles || articles.querySelector(".card")) return;
  articles.innerHTML = `
    <section class="empty">
      <h2>当前页没有文章</h2>
      <p>可以调整筛选条件或同步新文章。</p>
    </section>
  `;
}

function removeArticleCard(card) {
  if (!card) return;
  card.remove();
  showEmptyIfNoArticles();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

document.addEventListener("click", async (event) => {
  const originalLink = event.target.closest("[data-open-original]");
  if (originalLink) {
    const id = originalLink.dataset.id;
    const card = document.querySelector(`#article-${id}`);
    if (card) {
      updateReadStatus(card, "opened");
      card.dataset.readStatus = "opened";
    }
    if (!shouldKeepArticleVisible("opened")) removeArticleCard(card);
    return;
  }

  const target = event.target.closest("button");
  if (!target) return;

  const action = target.dataset.action;
  if (!action) return;

  try {
    if (action === "sync") {
      setLoading(target, true, "同步中...");
      const data = await postJson("/api/sync");
      const translate = data.translate || {};
      showNotice(
        `同步完成：新增 ${data.fetch?.added || 0} 篇，规则标记 ${data.rules?.tagged || 0} 篇，标题翻译 ${translate.success || 0} 篇。`
      );
      window.location.reload();
    }

    if (action === "fetch") {
      setLoading(target, true, "抓取中...");
      const data = await postJson("/api/fetch");
      showNotice(`抓取完成：新增 ${data.added} 篇，总计 ${data.total} 篇。`);
      window.location.reload();
    }

    if (action === "apply-rules") {
      setLoading(target, true, "整理中...");
      const data = await postJson("/api/apply-rules");
      showNotice(`规则已应用：标记 ${data.tagged} 篇，过滤 ${data.filtered} 篇。`);
      window.location.reload();
    }

    if (action === "translate") {
      setLoading(target, true, "翻译中...");
      const data = await postJson("/api/translate-titles");
      showNotice(`标题翻译完成：成功 ${data.success} 篇，失败 ${data.failed} 篇。`);
      window.location.reload();
    }

    if (action === "build-feed") {
      setLoading(target, true, "生成中...");
      const data = await postJson(`/api/build-feed?mode=${encodeURIComponent(currentMode)}`);
      showNotice(`RSS 已生成：${data.items} 条。`);
    }

    if (action === "save-meta") {
      const id = target.dataset.id;
      const card = document.querySelector(`#article-${id}`);
      setLoading(target, true, "保存中...");
      const data = await postJson(`/api/articles/${id}/meta`, collectMeta(card));
      updateReadStatus(card, data.read_status);
      updateReadingLevel(card, data.reading_level);
      updateFavorite(card, data.favorite);
      showNotice("笔记已保存。");
    }

    if (action === "toggle-favorite") {
      const id = target.dataset.id;
      const card = document.querySelector(`#article-${id}`);
      const nextFavorite = card.dataset.favorite !== "1";
      setLoading(target, true, "保存中...");
      const data = await postJson(`/api/articles/${id}/meta`, { favorite: nextFavorite });
      updateFavorite(card, data.favorite);
      showNotice(data.favorite ? "已收藏。" : "已取消收藏。");
    }

    if (action === "set-status") {
      const id = target.dataset.id;
      const card = document.querySelector(`#article-${id}`);
      const status = target.dataset.status;
      setLoading(target, true, "保存中...");
      const data = await postJson(`/api/articles/${id}/meta`, { read_status: status });
      updateReadStatus(card, data.read_status);
      if (card) card.dataset.readStatus = data.read_status;
      if (data.read_status === "read") {
        target.classList.add("status-done");
        target.textContent = "已读";
        target.dataset.originalText = "已读";
      }
      if (!shouldKeepArticleVisible(data.read_status)) removeArticleCard(card);
      showNotice("阅读状态已更新。");
    }

    if (action === "save-zotero") {
      const id = target.dataset.id;
      const card = document.querySelector(`#article-${id}`);
      setLoading(target, true, "保存 Zotero...");
      const data = await postJson(`/api/articles/${id}/zotero`);
      updateZotero(card, data.zotero_status);
      showNotice(data.local_only ? "未配置 Zotero API，已保存本地 Zotero 标记。" : "已保存到 Zotero。");
    }

    if (action === "delete-article") {
      const id = target.dataset.id;
      const card = document.querySelector(`#article-${id}`);
      setLoading(target, true, "删除中...");
      await postJson(`/api/articles/${id}/delete`);
      card?.remove();
      showNotice("文章已从本地数据库删除。");
    }

    if (action === "batch-status") {
      const ids = selectedArticleIds();
      const status = target.dataset.status;
      setLoading(target, true, "批量保存...");
      const data = await postJson("/api/articles/batch", { article_ids: ids, action: status });
      for (const id of ids) {
        const card = document.querySelector(`#article-${id}`);
        if (!card) continue;
        updateReadStatus(card, status);
        card.dataset.readStatus = status;
        if (shouldKeepArticleVisible(status)) {
          card.querySelector(".article-select").checked = false;
          continue;
        }
        removeArticleCard(card);
      }
      showNotice(`批量更新完成：${data.count} 篇。`);
    }

    if (action === "batch-reading-level") {
      const ids = selectedArticleIds();
      setLoading(target, true, "批量保存...");
      const data = await postJson("/api/articles/batch", {
        article_ids: ids,
        action: "reading_level",
        reading_level: target.dataset.readingLevel,
      });
      showNotice(`批量可读性更新完成：${data.count} 篇。`);
      window.location.reload();
    }

    if (action === "batch-delete") {
      const ids = selectedArticleIds();
      setLoading(target, true, "批量删除...");
      const data = await postJson("/api/articles/batch", { article_ids: ids, action: "delete" });
      for (const id of ids) document.querySelector(`#article-${id}`)?.remove();
      showNotice(`批量删除完成：${data.count} 篇。`);
    }
  } catch (error) {
    showNotice(error.message || "请求失败", "error");
  } finally {
    setLoading(target, false);
  }
});

if (filters) {
  filters.addEventListener("change", (event) => {
    const target = event.target;
    if (target.matches("select") || target.matches('input[type="checkbox"]')) {
      filters.requestSubmit();
    }
  });
}

const selectAll = document.querySelector("#select-all-articles");
if (selectAll) {
  selectAll.addEventListener("change", () => {
    for (const checkbox of document.querySelectorAll(".article-select")) {
      checkbox.checked = selectAll.checked;
    }
  });
}

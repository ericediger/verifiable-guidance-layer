/* Verifiable Guidance Layer — demo UI.
   Plain JS, no framework. Four views over the API: Ask, Compare, Releases, Issued answers.
   The page shows verdicts, sources and change; everything else lives in the layer. */

(() => {
  "use strict";

  // ── tiny helpers ────────────────────────────────────────────────────────────
  const $ = (sel, root = document) => root.querySelector(sel);
  const el = (tag, attrs = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v;
      else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      node.append(c.nodeType ? c : document.createTextNode(String(c)));
    }
    return node;
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (iso) => {
    if (!iso) return "";
    const d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  };
  const api = async (path, opts = {}) => {
    const res = await fetch(path, { headers: { "content-type": "application/json" }, ...opts });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (_) { /* ignore */ }
      throw new Error(detail);
    }
    return res.json();
  };
  const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });
  const encId = (id) => encodeURIComponent(id);

  let toastTimer;
  const toast = (msg) => {
    const t = $("#toast");
    t.textContent = msg; t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
  };

  const FLAG_LABEL = {
    carve_out: "Exception applies",
    pending_adoption: "Pending adoption here",
    upcoming_amendment: "Changes soon",
    practitioner_note: "Practitioner note",
    unresolved_reference: "Referenced material not held",
    judge_disagreement: "Independent check note",
    recommendation_not_requirement: "Recommendation, not requirement",
    claim_removed: "Claim removed by verifier",
  };
  const ROLE_LABEL = {
    entry: "Provisions asked about",
    definition: "Definitions they depend on",
    interpretation: "Interpretive guidance",
    carve_out: "Exceptions",
    reference: "Referenced material",
    annotation: "Practitioner notes",
  };
  const ROLE_ORDER = ["entry", "carve_out", "interpretation", "definition", "reference", "annotation"];
  const EDGE_SHORT = { DEPENDS_ON_DEFINITION: "depends on", INTERPRETED_BY: "interpreted by", CARVED_OUT_BY: "carved out by", REFERENCES: "references", ANNOTATED_BY: "annotated by" };
  const CLAIM_KIND = { conclusion: "Conclusion", requirement: "Requirement", condition: "Condition", caveat: "Caveat" };

  // ── state ───────────────────────────────────────────────────────────────────
  const state = {
    jurisdictions: [],
    releases: [],
    gold: [],
    form: { question: "", jurisdiction: "JN", as_of: "2025-06-01", release_id: null },
    last: null, // { request, answer, naive }
    busy: false,
  };

  async function loadBasics() {
    const [jurisdictions, releases, gold] = await Promise.all([
      api("/api/jurisdictions"), api("/api/releases"), api("/api/gold"),
    ]);
    state.jurisdictions = jurisdictions;
    state.releases = releases;
    state.gold = gold;
    if (state.form.release_id == null || !releases.some((r) => r.id === state.form.release_id)) {
      state.form.release_id = releases[releases.length - 1]?.id ?? 1;
    }
    renderBadge();
  }

  function renderBadge() {
    const latest = state.releases[state.releases.length - 1];
    const b = $("#release-badge");
    b.innerHTML = latest
      ? `<strong>Release ${latest.id}</strong> · ${latest.node_count} versions · ${latest.edge_count} relationships`
      : "No releases";
  }

  // ── tabs ────────────────────────────────────────────────────────────────────
  const views = { ask: renderAsk, compare: renderCompare, releases: renderReleases, issued: renderIssued };

  function showTab(name) {
    if (!views[name]) name = "ask";
    document.querySelectorAll(".segmented [role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
    document.querySelectorAll(".tab").forEach((s) => { s.hidden = s.dataset.tab !== name; });
    if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
    views[name]($(`#tab-${name}`));
  }
  document.querySelectorAll(".segmented [role=tab]").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  window.addEventListener("hashchange", () => showTab(location.hash.slice(1)));

  // ── ask form (shared by Ask and Compare) ────────────────────────────────────
  function askForm(onResult, { showExamples = true } = {}) {
    const q = el("textarea", { class: "question", rows: 3, placeholder: "Ask a question about the Standards…", "aria-label": "Question" });
    q.value = state.form.question;
    q.addEventListener("input", () => { state.form.question = q.value; });
    q.addEventListener("keydown", (e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit(); });

    const jur = el("select", { "aria-label": "Jurisdiction" },
      ...state.jurisdictions.map((j) => el("option", { value: j.code, selected: j.code === state.form.jurisdiction }, j.name)));
    jur.addEventListener("change", () => { state.form.jurisdiction = jur.value; });

    const asOf = el("input", { type: "date", value: state.form.as_of, "aria-label": "As-of date" });
    asOf.addEventListener("change", () => { state.form.as_of = asOf.value; });

    const rel = el("select", { "aria-label": "Release" },
      ...state.releases.map((r) => el("option", { value: r.id, selected: r.id === state.form.release_id }, `Release ${r.id}`)));
    rel.addEventListener("change", () => { state.form.release_id = Number(rel.value); });

    const btn = el("button", { class: "btn", type: "button", onclick: () => submit() }, "Ask");

    const form = el("div", { class: "ask-form" },
      q,
      el("div", { class: "controls" },
        el("label", { class: "control" }, "Jurisdiction", jur),
        el("label", { class: "control" }, "As of", asOf),
        el("label", { class: "control" }, "Release", rel),
        el("span", { class: "spacer" }),
        btn),
    );

    if (showExamples && state.gold.length) {
      form.append(
        el("div", { class: "examples-label" }, "Try one of the cases the layer is tested against"),
        el("div", { class: "examples" },
          ...state.gold.map((g) => el("button", { class: "chip", type: "button", title: g.question, onclick: () => {
            state.form.question = g.question; state.form.jurisdiction = g.jurisdiction;
            state.form.as_of = String(g.as_of); state.form.release_id = Number(g.release);
            q.value = g.question; jur.value = g.jurisdiction; asOf.value = state.form.as_of;
            if (!state.releases.some((r) => r.id === state.form.release_id)) {
              toast(`This case needs Release ${g.release}. Publish it from Releases first.`);
              state.form.release_id = state.releases[state.releases.length - 1].id;
            }
            rel.value = String(state.form.release_id);
            q.focus();
          } }, g.name))),
      );
    }

    async function submit() {
      const question = q.value.trim();
      if (!question || state.busy) return;
      state.busy = true; btn.disabled = true;
      const request = { question, jurisdiction: state.form.jurisdiction, as_of: state.form.as_of || null, release_id: state.form.release_id, compare_naive: true };
      onResult({ pending: true, request });
      try {
        const data = await post("/api/ask", request);
        state.last = { request, answer: data.answer, naive: data.naive };
        onResult({ ...state.last });
      } catch (e) {
        onResult({ error: e.message, request });
      } finally {
        state.busy = false; btn.disabled = false;
      }
    }
    return form;
  }

  const STAGES = ["Understanding the question", "Locating it in the Standards", "Resolving what was in force", "Composing", "Verifying every claim"];
  function progress() {
    const stage = el("div", { class: "progress-stage" }, STAGES[0]);
    const node = el("div", { class: "progress" }, el("div", { class: "progress-line" }), stage);
    let i = 0;
    const timer = setInterval(() => {
      if (i < STAGES.length - 1) { i += 1; stage.style.opacity = 0; setTimeout(() => { stage.textContent = STAGES[i]; stage.style.opacity = 1; }, 160); }
    }, 3200);
    const guard = setInterval(() => { if (!node.isConnected) { clearInterval(timer); clearInterval(guard); } }, 1000);
    return node;
  }

  // ── Ask view ────────────────────────────────────────────────────────────────
  function renderAsk(root) {
    root.replaceChildren();
    const result = el("div");
    root.append(askForm(handle), result);
    if (state.last) result.replaceChildren(answerView(state.last));

    function handle(r) {
      if (r.pending) { result.replaceChildren(progress()); return; }
      if (r.error) { result.replaceChildren(el("div", { class: "error" }, `The layer could not answer: ${r.error}`)); return; }
      result.replaceChildren(answerView(r));
    }
  }

  function verdictPill(outcome) {
    const cls = outcome.toLowerCase();
    if (outcome === "ANSWER_WITH_FLAGS") return el("span", { class: `verdict ${cls}` }, "ANSWER", el("span", {}, "with flags"));
    return el("span", { class: `verdict ${cls}` }, outcome);
  }

  function nodeIndex(packet) {
    const idx = {};
    for (const n of packet?.nodes || []) idx[n.version_id] = n;
    return idx;
  }

  function answerView({ answer, request }) {
    const a = answer;
    const idx = nodeIndex(a.packet);
    const wrap = el("article", { class: "answer" });
    wrap.append(verdictPill(a.outcome));
    wrap.append(el("h2", { class: "summary" }, a.summary));

    const jname = state.jurisdictions.find((j) => j.code === a.frame.jurisdiction)?.name || a.frame.jurisdiction || "jurisdiction not set";
    wrap.append(el("p", { class: "context-line" }, `${jname} · as of ${a.frame.as_of ? fmtDate(a.frame.as_of) : "date not set"} · Release ${a.release_id}`));

    if (a.outcome === "CLARIFY") {
      wrap.append(
        el("ul", { class: "clarify-list" }, ...a.clarifications.map((c) => el("li", {}, c))),
        el("p", { class: "note" }, "Jurisdiction and the as-of date are set by you, never guessed. The layer asks for a fact only when no answer at all is possible without it."),
      );
      return wrap;
    }

    if (a.flags.length) {
      wrap.append(el("ul", { class: "flags" }, ...a.flags.map((f) =>
        el("li", { class: `flag ${f.kind}` },
          el("span", { class: "flag-kind" }, FLAG_LABEL[f.kind] || f.kind),
          el("span", { class: "flag-msg" }, pretty(f.message))))));
    }

    if (a.claims.length) {
      wrap.append(el("div", { class: "claims" }, ...a.claims.map((c) => claimView(c, idx))));
    } else if (a.outcome === "REVIEW") {
      wrap.append(el("p", { class: "note" }, "Nothing in this release can be cited for this question. It has been logged as a coverage gap for the editors."));
    }

    if (a.clarifications?.length) {
      wrap.append(el("div", { class: "confirm" }, "To confirm before relying on this", el("ul", {}, ...a.clarifications.map((c) => el("li", {}, c)))));
    }

    if (a.packet) wrap.append(trustPanel(a));
    return wrap;
  }

  function claimView(c, idx) {
    const body = el("span", {}, c.text + " ");
    const cites = el("span", { class: "cites" });
    const row = el("div", { class: `claim ${c.kind}` }, el("span", { class: "claim-kind" }, CLAIM_KIND[c.kind] || c.kind), el("div", { class: "claim-body" }, body, cites));
    for (const v of c.cites) {
      const n = idx[v];
      const label = n ? (n.display_ref || n.title) : v;
      const chip = el("button", { class: "cite", type: "button", "aria-expanded": "false", title: n ? n.title : v }, label);
      let detail = null;
      chip.addEventListener("click", () => {
        if (detail) { detail.remove(); detail = null; chip.setAttribute("aria-expanded", "false"); return; }
        if (!n) return;
        detail = el("div", { class: "cite-detail" },
          el("div", {}, el("span", { class: "ref" }, n.display_ref || n.title), n.text),
          el("div", { class: "meta" }, `${n.source_title} · ${n.tier}${n.obligation !== "n/a" && n.obligation !== "definition" ? " · " + n.obligation : ""} · in force from ${fmtDate(n.in_force_from)}`));
        row.append(detail);
        chip.setAttribute("aria-expanded", "true");
      });
      cites.append(chip);
    }
    return row;
  }

  // ── trust panel ─────────────────────────────────────────────────────────────
  function trustPanel(a) {
    const p = a.packet;
    const v = a.verification;
    const d = el("details", { class: "trust" }, el("summary", {}, "Why you can trust this"));
    const body = el("div", { class: "trust-body" });
    d.append(body);
    let built = false;
    d.addEventListener("toggle", () => { if (d.open && !built) { built = true; build(); } });

    function build() {
      body.append(section("How the answer was resolved", el("div", { class: "graph-wrap" }, graphSvg(p))));

      const groups = el("div");
      for (const role of ROLE_ORDER) {
        const nodes = p.nodes.filter((n) => n.role === role);
        if (!nodes.length) continue;
        groups.append(el("div", { class: "evidence-group" },
          el("h4", {}, ROLE_LABEL[role]),
          ...nodes.map((n) => el("div", { class: `evidence ${n.tier}` },
            el("div", { class: "ref" }, n.display_ref || n.title),
            el("div", {},
              el("div", { class: "text" }, n.text),
              el("div", { class: "meta" }, `${n.source_title} · ${n.tier} · in force from ${fmtDate(n.in_force_from)}${n.jurisdiction_scope ? " · " + n.jurisdiction_scope + " only" : ""}${n.role === "carve_out" ? " · carves out " + short(n.from_concept) : ""}`)))),
        ));
      }
      body.append(section("Evidence in force", groups));

      if (p.gaps.length) {
        body.append(section("Known gaps", el("div", { style: "display:grid;gap:8px" }, ...p.gaps.map((g) =>
          el("div", { class: "gap" }, g.reason === "unresolved_reference"
            ? `${g.title} is referenced by ${short(g.referenced_from)} but its text is not held in Release ${p.release_id}.`
            : `${g.title} is not yet in force here (from ${fmtDate(g.next_in_force_from)}).`)))));
      }

      const upcoming = p.upcoming.filter((u) => u.text_changed);
      if (upcoming.length) {
        body.append(section("Coming into force after the as-of date", el("div", {}, ...upcoming.map((u) =>
          el("div", { class: "kv" }, el("span", { class: "k" }, u.display_ref || short(u.concept_id)), el("span", { class: "v" }, `${u.source_title}, from ${fmtDate(u.in_force_from)}`))))));
      }
      const superseded = p.superseded.filter((s) => s.text_changed);
      if (superseded.length) {
        body.append(section("What this would have cited before", el("div", {}, ...superseded.map((s) =>
          el("div", { class: "kv" }, el("span", { class: "k" }, s.display_ref || short(s.concept_id)), el("span", { class: "v" }, `${short(s.version_id)} · in force ${fmtDate(s.in_force_from)} to ${fmtDate(s.in_force_until)}`))))));
      }

      if (v) {
        body.append(section("Verifier checks", el("div", {}, ...v.checks.map((c) =>
          el("div", { class: `kv ${c.passed ? "pass" : "fail"}` }, el("span", { class: "k" }, `${c.rule} ${c.passed ? "✓" : "✗"}`), el("span", { class: "v" }, c.detail))))));
        if (v.judge) {
          body.append(section("Independent check", el("p", { class: "meta-line" },
            `${v.judge.checked} claim${v.judge.checked === 1 ? "" : "s"} checked by a second model, independent of the composer; ${v.judge.disagreements.length} note${v.judge.disagreements.length === 1 ? "" : "s"}.`)));
        }
      }
      body.append(el("p", { class: "meta-line" }, `Release ${p.release_id} · ${p.jurisdiction} · as of ${p.as_of} · composed by ${a.composer_model || "—"} · entry: ${p.entry_concepts.map(short).join(", ")}`));
    }
    return d;
  }

  const section = (title, content) => el("div", { class: "trust-section" }, el("h3", {}, title), content);
  const short = (id) => (id || "").replace(/^[a-z]+:/, "");
  const pretty = (s) => String(s || "").replace(/\b(gs|prov|def|ruling|note|doc|ia):/g, "");

  // ── inline SVG of the resolved subgraph ─────────────────────────────────────
  function graphSvg(p) {
    const NS = "http://www.w3.org/2000/svg";
    const W = 150, H = 30, DX = 260, DY = 46, PAD = 16;
    const nodes = p.nodes.map((n) => ({ id: n.concept_id, label: n.display_ref || n.title, depth: n.depth, cls: n.role, title: n.title }));
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    for (const g of p.gaps) {
      const from = byId[g.referenced_from];
      nodes.push({ id: g.concept_id, label: short(g.concept_id), depth: (from ? from.depth : 0) + 1, cls: "gap", title: g.title });
      byId[g.concept_id] = nodes[nodes.length - 1];
    }
    const layers = {};
    for (const n of nodes) (layers[n.depth] ||= []).push(n);
    const depths = Object.keys(layers).map(Number).sort((a, b) => a - b);
    let maxRows = 1;
    for (const d of depths) {
      layers[d].sort((a, b) => ROLE_ORDER.indexOf(a.cls) - ROLE_ORDER.indexOf(b.cls) || a.label.localeCompare(b.label));
      layers[d].forEach((n, i) => { n.x = PAD + d * DX; n.y = PAD + i * DY; });
      maxRows = Math.max(maxRows, layers[d].length);
    }
    const width = PAD * 2 + (depths.length - 1) * DX + W;
    const height = PAD * 2 + (maxRows - 1) * DY + H;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("width", width); svg.setAttribute("height", height);
    svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Resolved subgraph");

    const edges = [...p.edges];
    for (const g of p.gaps) edges.push({ kind: g.via, from_concept: g.referenced_from, to_concept: g.concept_id });
    for (const e of edges) {
      const a = byId[e.from_concept], b = byId[e.to_concept];
      if (!a || !b) continue;
      const g = document.createElementNS(NS, "g"); g.setAttribute("class", `edge ${e.kind}`);
      const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2;
      const path = document.createElementNS(NS, "path");
      const c = Math.max(30, (x2 - x1) / 2);
      path.setAttribute("d", x2 > x1 ? `M${x1},${y1} C${x1 + c},${y1} ${x2 - c},${y2} ${x2},${y2}` : `M${a.x + W / 2},${a.y + H} C${a.x + W / 2},${a.y + H + 30} ${b.x + W / 2},${b.y - 30} ${b.x + W / 2},${b.y}`);
      g.append(path);
      const t = document.createElementNS(NS, "text");
      t.setAttribute("x", (x1 + x2) / 2); t.setAttribute("y", (y1 + y2) / 2 - 4); t.setAttribute("text-anchor", "middle");
      t.textContent = EDGE_SHORT[e.kind] || e.kind.toLowerCase().replace(/_/g, " ");
      g.append(t); svg.append(g);
    }
    for (const n of nodes) {
      const g = document.createElementNS(NS, "g"); g.setAttribute("class", `node ${n.cls}`);
      const r = document.createElementNS(NS, "rect");
      r.setAttribute("x", n.x); r.setAttribute("y", n.y); r.setAttribute("width", W); r.setAttribute("height", H); r.setAttribute("rx", 7);
      const t = document.createElementNS(NS, "text");
      t.setAttribute("x", n.x + W / 2); t.setAttribute("y", n.y + H / 2 + 4); t.setAttribute("text-anchor", "middle");
      t.textContent = n.label.length > 22 ? n.label.slice(0, 21) + "…" : n.label;
      const title = document.createElementNS(NS, "title"); title.textContent = n.title;
      g.append(r, t, title); svg.append(g);
    }
    return svg;
  }

  // ── Compare view ────────────────────────────────────────────────────────────
  function renderCompare(root) {
    root.replaceChildren();
    const result = el("div");
    root.append(askForm(handle, { showExamples: true }), result);
    if (state.last) result.replaceChildren(compareView(state.last));
    else result.append(el("p", { class: "empty" }, "Ask a question to see the same answer from plain document retrieval beside it."));

    function handle(r) {
      if (r.pending) { result.replaceChildren(progress()); return; }
      if (r.error) { result.replaceChildren(el("div", { class: "error" }, `The layer could not answer: ${r.error}`)); return; }
      result.replaceChildren(compareView(r));
    }
  }

  function compareView({ answer, naive }) {
    const left = el("div", { class: "col" }, el("h2", {}, "Verifiable layer"), verdictPill(answer.outcome), el("p", { class: "summary" }, answer.summary));
    if (answer.outcome === "CLARIFY") left.append(el("ul", { class: "clarify-list" }, ...answer.clarifications.map((c) => el("li", {}, c))));
    if (answer.flags.length) left.append(el("ul", { class: "flags" }, ...answer.flags.map((f) => el("li", { class: `flag ${f.kind}` }, el("span", { class: "flag-kind" }, FLAG_LABEL[f.kind] || f.kind), el("span", { class: "flag-msg" }, pretty(f.message))))));

    const right = el("div", { class: "col" }, el("h2", {}, "Naive RAG (same documents, same model)"));
    if (!naive || naive.error) {
      right.append(el("p", { class: "empty" }, naive?.error ? `Baseline unavailable: ${naive.error}` : "Baseline not run."));
    } else {
      right.append(
        el("span", { class: "naive-conclusion" }, `concludes: ${naive.conclusion.replace("_", " ")}`),
        el("p", { class: "naive-answer" }, naive.answer),
        el("div", { class: "passages" }, el("h3", { class: "section-title", style: "margin:0" }, "Passages it relied on"),
          ...naive.cited_passages.map((c) => el("div", { class: "passage" }, el("span", { class: "doc" }, c.document), ` — ${c.heading}`,
            el("span", { class: "snippet" }, c.text.length > 150 ? c.text.slice(0, 149) + "…" : c.text)))),
      );
    }
    return el("div", { class: "compare" }, left, right);
  }

  // ── Releases view ───────────────────────────────────────────────────────────
  async function renderReleases(root) {
    root.replaceChildren(el("p", { class: "empty" }, "Loading…"));
    const [releases, proposals] = await Promise.all([api("/api/releases"), api("/api/proposals")]);
    state.releases = releases; renderBadge();

    const left = el("div", {}, el("h2", { class: "section-title" }, "Releases"),
      ...releases.map((r) => el("div", { class: "release" },
        el("div", { class: "label" }, r.label),
        el("div", { class: "counts" }, `${r.document_count} documents · ${r.node_count} versions · ${r.edge_count} relationships · ${fmtDate(r.created_at.slice(0, 10))}`),
        el("div", { class: "changelog" }, r.changelog))));

    const right = el("div");
    const list = () => {
      right.replaceChildren(el("h2", { class: "section-title" }, "Proposals"),
        ...proposals.map((p) => el("button", { class: "proposal-row", type: "button", onclick: () => openEditor(p.id) },
          el("span", { class: "title" }, p.title),
          el("span", { class: "who" }, `${p.submitted_by} · ${p.submitted_role}`),
          el("span", { class: `status ${p.status}` }, p.status === "pending" ? "Awaiting editorial decision" : `${p.status[0].toUpperCase() + p.status.slice(1)}${p.release_id ? " · Release " + p.release_id : ""}`))));
    };
    list();

    const resetRow = el("div", { class: "reset-row" }, el("button", { type: "button", onclick: async () => {
      if (!confirm("Reset the knowledge base to Release 1? Published releases will be removed.")) return;
      await post("/api/reset"); state.last = null; toast("Back to Release 1"); renderReleases(root);
    } }, "Reset to Release 1"));

    root.replaceChildren(el("div", { class: "two-col" }, left, right), resetRow);

    async function openEditor(id) {
      right.replaceChildren(el("p", { class: "empty" }, "Loading proposal…"));
      const [p, impact] = await Promise.all([api(`/api/proposals/${encId(id)}`), api(`/api/proposals/${encId(id)}/impact`)]);
      const ed = el("div", { class: "editor" });
      ed.append(el("button", { class: "back", type: "button", onclick: list }, "← All proposals"));
      ed.append(el("h2", {}, p.title));
      ed.append(el("p", { class: "who" }, `Proposed by ${p.submitted_by}, ${p.submitted_role}`));
      ed.append(el("p", { class: "rationale" }, p.rationale));

      const facts = el("dl", { class: "facts" });
      facts.append(fact("Basis", p.basis));
      for (const d of p.bundle.documents || []) {
        facts.append(fact("Source", d.title));
        facts.append(fact("Tier", d.tier));
        facts.append(fact("Effective", fmtDate(d.effective_from)));
      }
      ed.append(facts);

      if ((p.bundle.edges || []).length) {
        ed.append(el("h3", { class: "section-title", style: "margin-top:22px" }, "Proposed relationships"));
        ed.append(el("ul", { class: "edges-list" }, ...p.bundle.edges.map((e) => el("li", {}, edgeSentence(e)))));
      }
      if ((p.bundle.nodes || []).length) {
        ed.append(el("h3", { class: "section-title", style: "margin-top:22px" }, "New or revised text"));
        for (const n of p.bundle.nodes) ed.append(el("div", { class: "evidence" }, el("div", { class: "ref" }, n.display_ref), el("div", {}, el("div", { class: "text" }, n.text), el("div", { class: "meta" }, `in force from ${fmtDate(n.effective_from)}`))));
      }
      for (const d of p.bundle.documents || []) if (d.body) ed.append(el("div", { class: "doc-body", html: markdownLite(d.body) }));

      // impact
      const imp = el("div", { class: "impact" });
      imp.append(el("div", {}, el("h3", {}, "Impact preview"), el("p", { class: "big" }, `Would create Release ${impact.would_create_release} · ${impact.changed_gold_cases.length} test case${impact.changed_gold_cases.length === 1 ? "" : "s"} change · ${impact.affected_issued_answers.length} issued answer${impact.affected_issued_answers.length === 1 ? "" : "s"} affected`)));
      imp.append(el("div", {}, el("h3", {}, "Changes meaning of"), el("div", { class: "tags" }, ...impact.touched_concepts.map((c) => el("span", { class: "tag hot" }, short(c))))));
      if (impact.dependent_concepts.length) imp.append(el("div", {}, el("h3", {}, "Which these depend on"), el("div", { class: "tags" }, ...impact.dependent_concepts.map((d) => el("span", { class: "tag", title: d.via }, `${short(d.concept_id)} (${d.via.toLowerCase().replace(/_/g, " ")})`)))));
      if (impact.changed_gold_cases.length) {
        imp.append(el("div", {}, el("h3", {}, "Test cases whose evidence would change"), ...impact.changed_gold_cases.map((c) => {
          const added = c.after.versions.filter((v) => !c.before.versions.includes(v)).map(short);
          const removed = c.before.versions.filter((v) => !c.after.versions.includes(v)).map(short);
          const gapsClosed = c.before.gaps.filter((g) => !c.after.gaps.includes(g)).map(short);
          const upcomingNew = c.after.upcoming.filter((u) => !c.before.upcoming.includes(u)).map(short);
          const bits = [];
          if (gapsClosed.length) bits.push(el("span", {}, "gap closed: ", el("b", {}, gapsClosed.join(", "))));
          if (added.length) bits.push(el("span", {}, "now cites ", el("b", {}, added.join(", "))));
          if (removed.length) bits.push(el("span", {}, "no longer cites ", el("b", {}, removed.join(", "))));
          if (upcomingNew.length) bits.push(el("span", {}, "gains a change notice for ", el("b", {}, upcomingNew.join(", "))));
          return el("div", { class: "case" }, el("div", {}, `${c.id} · ${c.name}`), el("div", { class: "diff" }, ...bits.flatMap((b, i) => i ? [" · ", b] : [b])));
        })));
      }
      if (impact.affected_issued_answers.length) {
        imp.append(el("div", {}, el("h3", {}, "Issued answers affected"), ...impact.affected_issued_answers.map((ia) =>
          el("div", { class: "case" }, el("div", {}, `${ia.client_name} · ${ia.client_ref} · issued ${fmtDate(ia.issued_on)}`), statusLine(ia.staleness)))));
      } else {
        imp.append(el("div", {}, el("h3", {}, "Issued answers affected"), el("p", { class: "meta-line" }, "None.")));
      }
      ed.append(imp);

      if (p.status === "pending") {
        const note = el("input", { type: "text", placeholder: "Decision note (optional)" });
        const approve = el("button", { class: "btn", type: "button", onclick: async () => {
          approve.disabled = true;
          try {
            const r = await post(`/api/proposals/${encId(id)}/approve`, { decided_by: "editor:a.okafor", note: note.value });
            toast(`Release ${r.release_id} published`); state.last = null; await renderReleases(root);
          } catch (e) { toast(e.message); approve.disabled = false; }
        } }, "Approve and publish");
        const reject = el("button", { class: "btn btn-danger", type: "button", onclick: async () => {
          if (!note.value.trim()) { toast("A rejection needs a note."); note.focus(); return; }
          await post(`/api/proposals/${encId(id)}/reject`, { decided_by: "editor:a.okafor", note: note.value });
          toast("Proposal rejected"); await renderReleases(root);
        } }, "Reject");
        ed.append(el("div", { class: "decision" }, note, el("div", { class: "row" }, approve, reject)));
      } else {
        ed.append(el("p", { class: "note" }, `${p.status[0].toUpperCase() + p.status.slice(1)} by ${p.decided_by}${p.decision_note ? " — " + p.decision_note : ""}${p.release_id ? " · Release " + p.release_id : ""}`));
      }
      right.replaceChildren(ed);
    }
  }

  const fact = (k, v) => el("div", {}, el("dt", {}, k), el("dd", {}, v));
  const EDGE_VERB = { CARVED_OUT_BY: "is carved out by", INTERPRETED_BY: "is interpreted by", DEPENDS_ON_DEFINITION: "depends on the definition of", REFERENCES: "references", ANNOTATED_BY: "is annotated by" };
  const edgeSentence = (e) => `${short(e.from)} ${EDGE_VERB[e.kind] || e.kind.toLowerCase()} ${short(e.to)}`;

  function markdownLite(md) {
    const blocks = md.trim().split(/\n\s*\n/);
    return blocks.map((b) => {
      const m = b.match(/^(#{1,3})\s+(.*)$/);
      if (m) return `<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`;
      return `<p>${inline(b.replace(/\n/g, " "))}</p>`;
    }).join("");
    function inline(s) { return esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*(.+?)\*/g, "<em>$1</em>"); }
  }

  function statusLine(st) {
    if (!st || st.status === "current") return el("div", { class: "status-line current" }, "Current");
    const when = fmtDate(st.from);
    const line = st.status === "expires"
      ? el("div", { class: "status-line expires" }, el("strong", {}, `Expires ${when}`), "re-review before then")
      : el("div", { class: "status-line stale" }, el("strong", {}, `Stale since ${when}`), "re-review now");
    const reasons = st.reasons.map((r) => el("div", { class: "status-reason" },
      `${r.display_ref} is replaced by ${short(r.superseding_version)} (${r.source_title}) from ${fmtDate(r.from)}${r.learned_after_issue ? " — learned after this answer was issued" : ""}.`));
    return el("div", { style: "display:grid;gap:6px" }, line, ...reasons);
  }

  // ── Issued answers view ─────────────────────────────────────────────────────
  async function renderIssued(root) {
    root.replaceChildren(el("p", { class: "empty" }, "Loading…"));
    const items = await api("/api/issued-answers");
    const latest = state.releases[state.releases.length - 1];
    root.replaceChildren(
      el("h2", { class: "section-title" }, `Answers issued to clients, checked against Release ${latest?.id ?? ""}`),
      ...items.map((ia) => el("div", { class: "issued" },
        el("div", { class: "client" }, ia.client_name, el("span", {}, ia.client_ref)),
        statusLine(ia.staleness),
        el("div", { class: "meta" }, `Issued ${fmtDate(ia.issued_on)} · ${state.jurisdictions.find((j) => j.code === ia.jurisdiction)?.name || ia.jurisdiction} · as of ${fmtDate(ia.as_of)} · under Release ${ia.release_id}`),
        el("div", { class: "q" }, ia.question),
        el("div", { class: "a" }, ia.answer_text),
        el("div", { class: "cited" }, "Relied on " + ia.cited_versions.map(short).join(", ")))),
    );
    if (!items.length) root.append(el("p", { class: "empty" }, "No answers have been issued yet."));
  }

  // ── boot ────────────────────────────────────────────────────────────────────
  loadBasics().then(() => showTab(location.hash.slice(1) || "ask")).catch((e) => {
    $("#release-badge").textContent = "Offline";
    $("#tab-ask").replaceChildren(el("div", { class: "error" }, `Could not reach the layer: ${e.message}`));
  });
})();

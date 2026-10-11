/* Cookbook search: understands plain sentences such as
   "I want to make a chicken recipe which has lemon".
   Filler words are dropped, the remaining words must all match
   (title, tags, ingredients or method). Words after "without / no / not"
   are excluded. Works the same for typed or spoken text. */
(function () {
  var data = JSON.parse(document.getElementById("recipe-data").textContent);
  var input = document.getElementById("q");
  var statusEl = document.getElementById("status");
  var grid = document.getElementById("grid");
  var emptyEl = document.getElementById("empty");
  var tagBox = document.getElementById("tags");

  var STOP = new Set((
    "a an the i me my we our you your want wanna need needs would like love " +
    "to make making made cook cooking cooked prepare preparing recipe recipes " +
    "dish dishes meal something anything any some that which who whose has have " +
    "having had contains containing contain using use uses include includes " +
    "including in on of for is are be it its this please can could show find " +
    "give let lets tonight today tell about what how"
  ).split(" "));
  var NEG = new Set(["without", "no", "not", "except", "excluding", "minus"]);
  var NEG_END = new Set(["with", "and", "but", "plus", "also"]);

  function norm(s) {
    return String(s)
      .toLowerCase()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/[^\p{L}\p{N}\s]/gu, " ");
  }
  function words(s) {
    return norm(s).split(/\s+/).filter(Boolean);
  }
  function variants(t) {
    var v = [t];
    if (t.length > 3 && t.slice(-1) === "s") v.push(t.slice(0, -1));
    if (t.length > 4 && t.slice(-2) === "es") v.push(t.slice(0, -2));
    if (t.length > 4 && t.slice(-3) === "ies") v.push(t.slice(0, -3) + "y");
    return v;
  }

  // Pre-compute searchable words per recipe, grouped by importance.
  data.forEach(function (r) {
    r._f = [
      { w: 3, words: words(r.title + " " + r.tags.join(" ")) },
      { w: 2, words: words(r.ingredients.join(" ")) },
      { w: 1, words: words(r.description + " " + r.steps.join(" ")) },
    ];
  });

  function weightFor(r, token) {
    var vs = variants(token);
    var best = 0;
    r._f.forEach(function (f) {
      if (best >= f.w) return;
      for (var i = 0; i < f.words.length; i++) {
        for (var j = 0; j < vs.length; j++) {
          if (f.words[i].indexOf(vs[j]) === 0) { best = f.w; return; }
        }
      }
    });
    return best;
  }

  function parse(text) {
    var pos = [], neg = [], negating = false;
    words(text).forEach(function (t) {
      if (NEG.has(t)) { negating = true; return; }
      if (NEG_END.has(t)) { negating = false; return; }
      if (STOP.has(t) || t.length < 2) return;
      (negating ? neg : pos).push(t);
    });
    return { pos: pos, neg: neg };
  }

  var cards = {};
  Array.prototype.forEach.call(grid.children, function (el) {
    cards[el.getAttribute("data-slug")] = el;
  });

  var activeTags = [];

  function show(list) {
    var shown = {};
    list.forEach(function (r) {
      shown[r.slug] = true;
      cards[r.slug].hidden = false;
      grid.appendChild(cards[r.slug]);
    });
    data.forEach(function (r) {
      if (!shown[r.slug]) cards[r.slug].hidden = true;
    });
    emptyEl.hidden = list.length > 0;
  }

  function byTitle(a, b) { return a.title.localeCompare(b.title); }

  function run() {
    var q = parse(input.value);
    var pool = data.filter(function (r) {
      return activeTags.every(function (t) { return r.tags.indexOf(t) !== -1; });
    });

    if (!q.pos.length && !q.neg.length) {
      show(pool.slice().sort(byTitle));
      statusEl.textContent = activeTags.length
        ? pool.length + (pool.length === 1 ? " recipe" : " recipes")
        : "";
      return;
    }

    var scored = pool.map(function (r) {
      var matched = 0, score = 0;
      q.pos.forEach(function (t) {
        var w = weightFor(r, t);
        if (w) { matched++; score += w; }
      });
      var blocked = q.neg.some(function (t) { return weightFor(r, t) > 0; });
      return { r: r, matched: matched, score: score, blocked: blocked };
    }).filter(function (s) { return !s.blocked; });

    var label = q.pos.join(" + ") + (q.neg.length ? " (without " + q.neg.join(", ") + ")" : "");
    var full = scored.filter(function (s) { return s.matched === q.pos.length; });

    if (full.length || !q.pos.length) {
      full.sort(function (a, b) { return b.score - a.score || byTitle(a.r, b.r); });
      show(full.map(function (s) { return s.r; }));
      statusEl.textContent = full.length
        ? full.length + (full.length === 1 ? " recipe" : " recipes") + " with " + label
        : "";
      return;
    }

    var partial = scored.filter(function (s) { return s.matched > 0; });
    partial.sort(function (a, b) { return b.matched - a.matched || b.score - a.score || byTitle(a.r, b.r); });
    show(partial.map(function (s) { return s.r; }));
    statusEl.textContent = partial.length
      ? "Nothing has all of " + label + ". Closest matches:"
      : "";
  }

  // Tag chips
  tagBox.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b) return;
    var t = b.getAttribute("data-tag");
    var i = activeTags.indexOf(t);
    if (i === -1) activeTags.push(t); else activeTags.splice(i, 1);
    b.setAttribute("aria-pressed", i === -1 ? "true" : "false");
    run();
  });

  input.addEventListener("input", run);

  // ?q=chicken+lemon opens the page with a search already applied
  // (handy later for voice assistants or shortcuts).
  try {
    var preset = new URLSearchParams(location.search).get("q");
    if (preset) input.value = preset;
  } catch (err) { /* ignore */ }
  run();
})();

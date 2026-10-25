// The index's website: the search on the home page, the copy buttons, and
// colours for Tessel code in READMEs.
// Author: Alexius Academia
// Date: 2026-10-25
(function () {
  const q = document.getElementById("q");
  if (q) {
    const cards = Array.from(document.querySelectorAll(".lib"));
    const none = document.getElementById("none");
    const filter = () => {
      const words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
      let shown = 0;
      for (const c of cards) {
        const ok = words.every(w => c.dataset.search.includes(w));
        c.hidden = !ok;
        if (ok) shown++;
      }
      none.hidden = shown > 0;
    };
    q.addEventListener("input", filter);
    const fromUrl = new URLSearchParams(location.search).get("q");
    if (fromUrl) { q.value = fromUrl; filter(); }
  }

  for (const b of document.querySelectorAll("[data-copy]")) {
    b.addEventListener("click", () => {
      navigator.clipboard.writeText(b.dataset.copy).then(() => {
        const was = b.textContent;
        b.textContent = "Copied";
        setTimeout(() => { b.textContent = was; }, 1300);
      }, () => {});
    });
  }

  const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const keywords = /^(import|fn|var|let|if|else|for|in|while|return|match|try|true|false|nil|app|state|struct|enum|view|public|bind|interface)$/;
  const token = /(\/\/[^\n]*)|("(?:\\.|[^"\\])*")|(\b\d+(?:\.\d+)?(?:e-?\d+)?\b)|([A-Za-z_]\w*)/g;
  for (const code of document.querySelectorAll("code.language-tessel")) {
    const text = code.textContent;
    let out = "", last = 0, m;
    token.lastIndex = 0;
    while ((m = token.exec(text))) {
      out += esc(text.slice(last, m.index));
      const t = esc(m[0]);
      if (m[1]) out += '<span class="c">' + t + "</span>";
      else if (m[2]) out += '<span class="s">' + t + "</span>";
      else if (m[3]) out += '<span class="n">' + t + "</span>";
      else if (keywords.test(m[4])) out += '<span class="k">' + t + "</span>";
      else out += t;
      last = token.lastIndex;
    }
    code.innerHTML = out + esc(text.slice(last));
  }
})();

// Barra flutuante do navegador interno do Baixou.
// Injetada em cada página carregada. Usa só createElement/textContent
// (sites como o YouTube bloqueiam innerHTML com "Trusted Types").
(() => {
  if (window.__baixouBar) return;
  window.__baixouBar = true;

  const FONT = "600 14px/1 'Segoe UI', system-ui, sans-serif";
  const bar = document.createElement("div");
  bar.style.cssText = "position:fixed;z-index:2147483647;right:16px;bottom:16px;display:flex;gap:6px;align-items:center;font:" + FONT;

  function makeButton(label, title, primary) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.title = title;
    b.style.cssText = [
      "border:0", "cursor:pointer", "border-radius:999px", "color:#fff", "font:" + FONT,
      "box-shadow:0 6px 18px rgba(0,0,0,.35)",
      primary ? "padding:13px 20px;background:#FF5A1F" : "padding:11px 13px;background:rgba(20,17,14,.88)",
    ].join(";");
    bar.appendChild(b);
    return b;
  }

  const back = makeButton("←", "Voltar");
  const reload = makeButton("⟳", "Recarregar");
  const dl = makeButton("⬇ Baixar este vídeo", "Baixar com o Baixou (formato escolhido no app)", true);

  const toast = document.createElement("div");
  toast.style.cssText = "position:fixed;z-index:2147483647;right:16px;bottom:76px;max-width:340px;padding:11px 14px;border-radius:12px;color:#fff;font:500 13px/1.45 'Segoe UI',system-ui,sans-serif;box-shadow:0 6px 18px rgba(0,0,0,.35);display:none";
  let toastTimer;
  function say(text, isError) {
    toast.textContent = text;
    toast.style.background = isError ? "#D93025" : "#14110E";
    toast.style.display = "block";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast.style.display = "none"), 4500);
  }

  back.addEventListener("click", () => history.back());
  reload.addEventListener("click", () => location.reload());
  dl.addEventListener("click", async () => {
    const api = window.pywebview && window.pywebview.api;
    if (!api) return say("O Baixou ainda está carregando. Tente de novo em um segundo.", true);
    dl.disabled = true;
    dl.textContent = "Enviando…";
    try {
      const r = await api.download(location.href);
      if (r && r.ok) say("✓ Adicionado ao Baixou! Acompanhe na janela principal.");
      else say((r && r.error) || "Não deu para baixar esta página.", true);
    } catch (e) {
      say("Não deu para baixar: " + e, true);
    }
    dl.disabled = false;
    dl.textContent = "⬇ Baixar este vídeo";
  });

  function mount() {
    const root = document.body || document.documentElement;
    if (!root) return;
    root.appendChild(bar);
    root.appendChild(toast);
  }
  mount();
  // Alguns sites trocam o <body> inteiro ao navegar: recoloca a barra se sumir.
  setInterval(() => { if (!bar.isConnected) mount(); }, 1500);
})();

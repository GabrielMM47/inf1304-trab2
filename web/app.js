"use strict";

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

async function api(metodo, caminho, corpo) {
  const opcoes = { method: metodo, headers: {} };
  if (corpo !== undefined) {
    opcoes.headers["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(corpo);
  }
  const resp = await fetch(window.SEBO_API + caminho, opcoes);
  let dados = null;
  try { dados = await resp.json(); } catch (e) { dados = null; }
  if (!resp.ok) {
    throw new Error((dados && dados.erro) || "Erro " + resp.status);
  }
  return dados;
}

function el(tag, texto, classe) {
  const e = document.createElement(tag);
  if (texto !== undefined && texto !== null) e.textContent = texto;
  if (classe) e.className = classe;
  return e;
}

function mostrar(id, texto, ok) {
  const e = document.getElementById(id);
  e.textContent = texto;
  e.className = "msg " + (ok ? "ok" : "erro");
}

// Desabilita os botões enquanto a requisição está em andamento.
async function ocupado(botao, fn) {
  botao.disabled = true;
  try { return await fn(); } finally { botao.disabled = false; }
}

function hora(iso) {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function dataHora(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + " " + hora(iso);
}

function limpar(corpo) { while (corpo.firstChild) corpo.removeChild(corpo.firstChild); }

function linhaVazia(corpo, colunas, texto) {
  const tr = el("tr");
  const td = el("td", texto);
  td.colSpan = colunas;
  tr.appendChild(td);
  corpo.appendChild(tr);
}

/* ---------- comprador ---------- */

function iniciarComprador() {
  const campoEmail = document.getElementById("email");
  try { campoEmail.value = localStorage.getItem("sebo_email") || ""; } catch (e) { /* ignorado */ }
  campoEmail.addEventListener("change", () => {
    try { localStorage.setItem("sebo_email", campoEmail.value.trim()); } catch (e) { /* ignorado */ }
  });

  const corpo = document.getElementById("catalogo");

  async function carregar() {
    try {
      const livros = await api("GET", "/livros");
      limpar(corpo);
      if (!livros.length) return linhaVazia(corpo, 5, "Nenhum livro cadastrado.");
      livros.forEach((l) => {
        const tr = el("tr");
        tr.appendChild(el("td", l.titulo));
        tr.appendChild(el("td", l.autor));
        tr.appendChild(el("td", brl.format(l.preco)));
        const tdDisp = el("td");
        tdDisp.appendChild(el("span", l.disponivel > 0 ? "disponível" : "esgotado",
          "tag " + (l.disponivel > 0 ? "sim" : "nao")));
        tr.appendChild(tdDisp);
        const tdAcao = el("td", null, "acao");
        const botao = el("button", "Tenho interesse");
        botao.type = "button";
        botao.addEventListener("click", () => ocupado(botao, () => interesse(l)));
        tdAcao.appendChild(botao);
        tr.appendChild(tdAcao);
        corpo.appendChild(tr);
      });
    } catch (e) {
      mostrar("mensagem", "Não foi possível carregar o catálogo: " + e.message, false);
    }
  }

  async function interesse(livro) {
    const email = campoEmail.value.trim();
    if (!email) {
      mostrar("mensagem", "Informe seu e-mail.", false);
      campoEmail.focus();
      return;
    }
    try { localStorage.setItem("sebo_email", email); } catch (e) { /* ignorado */ }
    try {
      const r = await api("POST", "/interesses", { livroId: livro.livroId, email });
      if (r.status === "RESERVADO") {
        mostrar("mensagem", "Reservado até " + hora(r.expiraEm) + " — verifique seu e-mail", true);
      } else {
        mostrar("mensagem", "Você está na posição " + r.posicaoFila + " da fila", true);
      }
    } catch (e) {
      mostrar("mensagem", e.message, false);
    }
    await carregar();
  }

  document.getElementById("atualizar").addEventListener("click", (ev) => ocupado(ev.currentTarget, carregar));
  carregar();
}

/* ---------- funcionário ---------- */

function iniciarFuncionario() {
  const corpo = document.getElementById("catalogo");
  const seletor = document.getElementById("livro-reservas");
  const corpoReservas = document.getElementById("reservas");
  let livros = [];

  async function carregarCatalogo() {
    try {
      livros = await api("GET", "/livros");
    } catch (e) {
      mostrar("msg-catalogo", "Não foi possível carregar o catálogo: " + e.message, false);
      return;
    }
    limpar(corpo);
    if (!livros.length) linhaVazia(corpo, 4, "Nenhum livro cadastrado.");
    livros.forEach((l) => {
      const tr = el("tr");
      tr.appendChild(el("td", l.titulo));
      tr.appendChild(el("td", l.autor));
      tr.appendChild(el("td", String(l.disponivel) + " / " + String(l.quantidade)));
      const td = el("td", null, "acao");
      const qtd = el("input");
      qtd.type = "number"; qtd.min = "1"; qtd.step = "1"; qtd.value = "1";
      qtd.setAttribute("aria-label", "Quantidade de " + l.titulo);
      const botao = el("button", "Registrar chegada");
      botao.type = "button";
      botao.addEventListener("click", () => ocupado(botao, () => chegada(l, qtd.value)));
      td.appendChild(qtd);
      td.appendChild(botao);
      tr.appendChild(td);
      corpo.appendChild(tr);
    });
    const atual = seletor.value;
    limpar(seletor);
    const op0 = el("option", "Selecione um livro…");
    op0.value = "";
    seletor.appendChild(op0);
    livros.forEach((l) => {
      const op = el("option", l.titulo + " — " + l.autor);
      op.value = l.livroId;
      seletor.appendChild(op);
    });
    seletor.value = atual;
  }

  async function carregarReservas() {
    limpar(corpoReservas);
    const id = seletor.value;
    if (!id) return linhaVazia(corpoReservas, 4, "Selecione um livro.");
    try {
      const reservas = await api("GET", "/reservas?livroId=" + encodeURIComponent(id));
      if (!reservas.length) return linhaVazia(corpoReservas, 4, "Nenhuma reserva ativa.");
      reservas.forEach((r) => {
        const tr = el("tr");
        tr.appendChild(el("td", r.email));
        tr.appendChild(el("td", dataHora(r.reservadoEm)));
        tr.appendChild(el("td", dataHora(r.expiraEm)));
        const td = el("td", null, "acao");
        const botao = el("button", "Confirmar venda");
        botao.type = "button";
        botao.addEventListener("click", () => ocupado(botao, () => vender(id, r.ordem)));
        td.appendChild(botao);
        tr.appendChild(td);
        corpoReservas.appendChild(tr);
      });
    } catch (e) {
      mostrar("msg-reservas", e.message, false);
    }
  }

  async function atualizar() {
    await carregarCatalogo();
    await carregarReservas();
  }

  async function chegada(livro, valor) {
    const quantidade = parseInt(valor, 10);
    if (!(quantidade >= 1)) return mostrar("msg-catalogo", "Quantidade deve ser um inteiro maior que zero.", false);
    try {
      await api("POST", "/livros/" + encodeURIComponent(livro.livroId) + "/chegada", { quantidade });
      mostrar("msg-catalogo", "Chegada registrada: " + quantidade + " de “" + livro.titulo + "”.", true);
    } catch (e) {
      mostrar("msg-catalogo", e.message, false);
    }
    await atualizar();
  }

  async function vender(livroId, ordem) {
    try {
      await api("POST", "/vendas", { livroId, ordem });
      mostrar("msg-reservas", "Venda confirmada.", true);
    } catch (e) {
      mostrar("msg-reservas", e.message, false);
    }
    await atualizar();
  }

  const form = document.getElementById("form-livro");
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const botao = form.querySelector("button");
    await ocupado(botao, async () => {
      const preco = parseFloat(form.preco.value.replace(",", "."));
      const quantidade = parseInt(form.quantidade.value, 10);
      try {
        await api("POST", "/livros", {
          titulo: form.titulo.value.trim(), autor: form.autor.value.trim(), preco, quantidade,
        });
        mostrar("msg-cadastro", "Livro cadastrado.", true);
        form.reset();
      } catch (e) {
        mostrar("msg-cadastro", e.message, false);
      }
      await atualizar();
    });
  });

  seletor.addEventListener("change", carregarReservas);
  document.getElementById("atualizar").addEventListener("click", (ev) => ocupado(ev.currentTarget, atualizar));
  atualizar();
}

document.addEventListener("DOMContentLoaded", () => {
  const pagina = document.body.dataset.pagina;
  if (pagina === "comprador") iniciarComprador();
  else if (pagina === "funcionario") iniciarFuncionario();
});

/* NAC System - funções usadas por todas as páginas */

/* endereço da API (localhost:5000 se abrir a página fora do Flask) */
const API_BASE =
    window.API_BASE ||
    (
        location.protocol === "file:" ||
        (
            (location.hostname === "localhost" || location.hostname === "127.0.0.1") &&
            location.port !== "" &&
            location.port !== "5000"
        )
            ? "http://localhost:5000"
            : ""
    );


function limparSessao() {

    localStorage.removeItem("token");
    localStorage.removeItem("tipoUsuario");
    localStorage.removeItem("usuario");
    localStorage.removeItem("salaSelecionada");

}


/* chamada pra API, com o token. Em caso de erro lança Error(mensagem) */
async function api(caminho, opcoes) {

    opcoes = opcoes || {};

    const headers = { "Content-Type": "application/json" };
    const token = localStorage.getItem("token");

    if (token) {
        headers["Authorization"] = "Bearer " + token;
    }

    let resposta;

    try {

        resposta = await fetch(API_BASE + caminho, {
            method: opcoes.method || "GET",
            headers: headers,
            body: opcoes.body ? JSON.stringify(opcoes.body) : undefined
        });

    } catch (erro) {

        throw new Error("Não foi possível conectar ao servidor.");

    }

    let dados = {};

    try {
        dados = await resposta.json();
    } catch (erro) {
        /* resposta sem JSON */
    }

    if (resposta.status === 401 && !opcoes.semRedirecionar) {

        /* login expirou */
        limparSessao();
        window.location.replace("index.html");

        throw new Error(dados.erro || "Sessão expirada.");

    }

    /* 405 = servidor com código antigo */
    if (resposta.status === 405) {
        throw new Error("O servidor está desatualizado. Reinicie o servidor e tente de novo.");
    }

    if (!resposta.ok) {
        throw new Error(dados.erro || "Erro ao comunicar com o servidor.");
    }

    return dados;

}


/* =========================
   LOGIN / SESSÃO
========================= */

async function fazerLogin(usuario, senha, tipo) {

    const dados = await api("/api/login", {
        method: "POST",
        body: { usuario: usuario, senha: senha, tipo: tipo },
        semRedirecionar: true
    });

    localStorage.setItem("token", dados.token);
    localStorage.setItem("tipoUsuario", dados.tipo);
    localStorage.setItem("usuario", dados.usuario);

    return dados;

}


/* sem login volta pra tela inicial */
function verificarLogin() {

    const tipo = localStorage.getItem("tipoUsuario");
    const token = localStorage.getItem("token");

    if (!tipo || !token) {

        limparSessao();
        window.location.replace("index.html");

        return null;
    }

    return tipo;
}


/* página só de admin */
function verificarAdmin() {

    const tipo = verificarLogin();

    if (tipo !== "ADMIN") {

        window.location.replace("dashboard.html");

        return null;
    }

    return tipo;
}


async function sair() {

    try {
        await api("/api/logout", {
            method: "POST",
            semRedirecionar: true
        });
    } catch (erro) {
        /* sai mesmo se o servidor não responder */
    }

    limparSessao();

    window.location.href = "index.html";

}


/* =========================
   SALAS
========================= */

async function carregarSalas() {
    return await api("/api/salas");
}


async function carregarSala(numero) {
    return await api("/api/salas/" + encodeURIComponent(numero));
}


async function cadastrarSala(sala) {
    return await api("/api/salas", { method: "POST", body: sala });
}


async function apagarSalaApi(numero) {
    return await api("/api/salas/" + encodeURIComponent(numero), {
        method: "DELETE"
    });
}


/* =========================
   ATRIBUIÇÃO DE SALAS (admin)
========================= */

async function carregarAtribuicoes() {
    return await api("/api/atribuicoes");
}


async function salvarSalasDoOperador(operadorId, salas) {
    return await api("/api/operadores/" + operadorId + "/salas", {
        method: "PUT",
        body: { salas: salas }
    });
}


async function alterarProducaoSala(numero, producao) {
    return await api("/api/salas/" + encodeURIComponent(numero) + "/producao", {
        method: "PUT",
        body: { producao: producao }
    });
}


async function designarOperadores(numero, ids) {
    return await api("/api/salas/" + encodeURIComponent(numero) + "/operadores", {
        method: "PUT",
        body: { operadores: ids }
    });
}


/* =========================
   ENVASES
========================= */

/* filtros = { sala, de, ate } */
async function carregarEnvases(filtros) {

    const q = new URLSearchParams();

    Object.keys(filtros || {}).forEach(function(chave) {
        if (filtros[chave]) {
            q.set(chave, filtros[chave]);
        }
    });

    const texto = q.toString();

    return await api("/api/envases" + (texto ? "?" + texto : ""));

}


/* dados = { sala: "506", p05, p50, observacao, data, hora } */
async function registrarEnvase(dados) {
    return await api("/api/envases", { method: "POST", body: dados });
}


/* últimos envases de uma sala */
async function carregarEnvasesDaSala(numero, limite) {
    return await api(
        "/api/salas/" + encodeURIComponent(numero) +
        "/envases?limite=" + (limite || 50)
    );
}


/* cancela (não apaga) um envase */
async function cancelarEnvaseApi(id, motivo) {
    return await api("/api/envases/" + id + "/cancelar", {
        method: "POST",
        body: { motivo: motivo }
    });
}


/* dados = { numero: "507", grau: "B" } */
async function editarSalaApi(numero, dados) {
    return await api("/api/salas/" + encodeURIComponent(numero), {
        method: "PUT",
        body: dados
    });
}


/* dados = { usuario, senha } (senha vazia mantém a atual) */
async function editarOperadorApi(id, dados) {
    return await api("/api/operadores/" + id, { method: "PUT", body: dados });
}


async function ativarOperadorApi(id, ativo) {
    return await api("/api/operadores/" + id + "/ativo", {
        method: "PUT",
        body: { ativo: ativo }
    });
}


/* =========================
   JANELA PRA PEDIR UM TEXTO (motivo do cancelamento)
   devolve o texto ou null se cancelar
========================= */

function pedirTexto(op) {

    return new Promise(function(resolve) {

        const fundo = document.createElement("div");
        fundo.className = "janela-fundo";

        fundo.innerHTML = `
            <form class="janela" role="dialog" aria-modal="true">
                <h3>${escapeHTML(op.titulo || "")}</h3>
                <p>${escapeHTML(op.mensagem || "")}</p>
                <textarea maxlength="200" rows="3"
                    placeholder="${escapeHTML(op.placeholder || "")}" required></textarea>
                <small class="janela-erro"></small>
                <div class="janela-acoes">
                    <button type="button" class="btn-secundario" data-acao="voltar">VOLTAR</button>
                    <button type="submit" class="btn-perigo">${escapeHTML(op.botao || "CONFIRMAR")}</button>
                </div>
            </form>
        `;

        const form = fundo.querySelector("form");
        const campo = fundo.querySelector("textarea");
        const aviso = fundo.querySelector(".janela-erro");
        const minimo = op.minimo || 1;

        function fechar(valor) {
            document.removeEventListener("keydown", aoTeclar);
            fundo.remove();
            resolve(valor);
        }

        function aoTeclar(e) {
            if (e.key === "Escape") fechar(null);
        }

        form.addEventListener("submit", function(e) {
            e.preventDefault();
            const texto = campo.value.trim();
            if (texto.length < minimo) {
                aviso.textContent = "Escreva pelo menos " + minimo + " caracteres.";
                campo.focus();
                return;
            }
            fechar(texto);
        });

        fundo.querySelector('[data-acao="voltar"]').addEventListener("click", function() {
            fechar(null);
        });

        fundo.addEventListener("click", function(e) {
            if (e.target === fundo) fechar(null);
        });

        document.addEventListener("keydown", aoTeclar);
        document.body.appendChild(fundo);
        campo.focus();

    });

}


function classeStatus(classificacao) {

    if (classificacao === "CONTAMINADA") {
        return "status-vermelho";
    }

    if (classificacao === "ESTÉRIL") {
        return "status-verde";
    }

    return "status-amarelo";

}


function valorOuTraco(valor) {
    return (valor === null || valor === undefined) ? "--" : valor;
}


function hojeISO() {

    const d = new Date();

    return d.getFullYear() + "-" +
        String(d.getMonth() + 1).padStart(2, "0") + "-" +
        String(d.getDate()).padStart(2, "0");

}


function horaAgora() {

    const d = new Date();

    return String(d.getHours()).padStart(2, "0") + ":" +
        String(d.getMinutes()).padStart(2, "0");

}


/* =========================
   TURNOS
========================= */

/* fim não incluso (12:00 já é Tarde) */
const TURNOS = [
    { id: "manha",     nome: "Manhã",     inicio: 5,  fim: 12, faixa: "05h–12h" },
    { id: "tarde",     nome: "Tarde",     inicio: 12, fim: 18, faixa: "12h–18h" },
    { id: "noite",     nome: "Noite",     inicio: 18, fim: 24, faixa: "18h–00h" },
    { id: "madrugada", nome: "Madrugada", inicio: 0,  fim: 5,  faixa: "00h–05h" }
];

/* "17:30:00" -> turno */
function turnoDaHora(hora) {

    const h = parseInt(String(hora || "").split(":")[0], 10);

    if (isNaN(h)) {
        return null;
    }

    return TURNOS.find(function(t) {
        return h >= t.inicio && h < t.fim;
    }) || null;

}



/* =========================
   GRAUS (só pra mostrar, quem classifica é o servidor)
========================= */

/* limite de partículas por m³ em operação */
const LIMITES_GRAU = {
    A: { p05: 3520,    p50: 20 },
    B: { p05: 352000,  p50: 2900 },
    C: { p05: 3520000, p50: 29000 }
};

function descreverGrau(grau) {

    const l = LIMITES_GRAU[grau];

    if (!l) {
        return "Sem grau definido";
    }

    return "Grau " + grau +
        " · 0,5 µm até " + l.p05.toLocaleString("pt-BR") +
        " · 5,0 µm até " + l.p50.toLocaleString("pt-BR");

}


/* =========================
   MENU LATERAL
========================= */

function montarMenu(pagina) {

    const tipo =
        localStorage.getItem("tipoUsuario");

    const menu =
        document.getElementById("menuLateral");

    if (!menu || !tipo) {
        return;
    }


    /* [arquivo, texto, id] */
    let links = [

        [
            "dashboard.html",
            "Salas",
            "dashboard"
        ],

        [
            "envase.html",
            "Registrar Envase",
            "envase"
        ],

        [
            "historico.html",
            "Histórico",
            "historico"
        ],

        [
            "graficos.html",
            "Gráficos",
            "graficos"
        ],

    ];


    if (tipo === "ADMIN") {

        links.splice(
            3,
            0,
            [
                "cadastro-sala.html",
                "Cadastrar Sala",
                "cadastro"
            ]

        );

        links.push(
            [
                "config.html",
                "Configurações",
                "config"
            ]
        );

    }


    menu.innerHTML =

        links.map(function(item) {

            return `
                <a href="${item[0]}" title="${item[1]}"
                   class="${pagina === item[2] ? "active" : ""}">
                    <span class="menu-icone">${iconeMenu(item[2])}</span>
                    <span class="menu-texto">${item[1]}</span>
                </a>
            `;

        }).join("") +

        `
            <a href="#" title="Sair"
               onclick="sair(); return false;">
                <span class="menu-icone">${iconeMenu("sair")}</span>
                <span class="menu-texto">Sair</span>
            </a>
        `;

    configurarMenuRetratil();

}


function iconeMenu(nome) {

    const caminhos = {
        "dashboard": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
        "envase": '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
        "historico": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
        "cadastro": '<path d="M3 21V9l9-6 9 6v12z"/><path d="M12 11v6M9 14h6"/>',
        "graficos": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
        "config": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
        "sair": '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 16l-4-4 4-4M6 12h11"/>'
    };

    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round">' + (caminhos[nome] || "") + "</svg>";

}


/* pc: botão recolhe o menu / celular: menu abre por cima pelo ☰ */
const MENU_CELULAR = window.matchMedia("(max-width: 750px)");

function configurarMenuRetratil() {

    const app = document.querySelector(".app");
    const sidebar = document.querySelector(".sidebar");

    if (!app || !sidebar || sidebar.querySelector(".menu-toggle")) {
        return;
    }

    let salvo = null;
    try { salvo = localStorage.getItem("menuRecolhido"); } catch (e) { /* segue sem salvar */ }

    /* tela média começa recolhido */
    const recolhido = salvo === null ? window.innerWidth <= 1000 : salvo === "1";

    /* sem animação ao abrir a página */
    app.classList.add("menu-sem-animacao");
    app.classList.toggle("menu-recolhido", recolhido);
    requestAnimationFrame(function() {
        requestAnimationFrame(function() {
            app.classList.remove("menu-sem-animacao");
        });
    });

    /* botão MENU */
    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "menu-toggle";
    botao.setAttribute("aria-label", "Recolher ou expandir menu");
    botao.innerHTML = "<span>☰</span><b>MENU</b>";

    botao.addEventListener("click", function() {

        if (MENU_CELULAR.matches) {
            fecharMenuCelular();
            return;
        }

        const agora = app.classList.toggle("menu-recolhido");
        try { localStorage.setItem("menuRecolhido", agora ? "1" : "0"); } catch (e) { /* ok */ }
        atualizarTituloBotao();

    });

    function atualizarTituloBotao() {
        botao.title = MENU_CELULAR.matches
            ? "Fechar menu"
            : (app.classList.contains("menu-recolhido") ? "Expandir menu" : "Recolher menu");
    }

    atualizarTituloBotao();
    sidebar.insertBefore(botao, sidebar.firstChild);


    /* celular: botão ☰ e fundo escuro */
    const abrir = document.createElement("button");
    abrir.type = "button";
    abrir.className = "menu-abrir";
    abrir.setAttribute("aria-label", "Abrir menu");
    abrir.innerHTML = "☰";
    abrir.addEventListener("click", function() {
        app.classList.add("menu-aberto");
    });

    /* espera o topo existir */
    function colocarBotaoAbrir() {
        const topbar = document.querySelector(".topbar");
        if (topbar && !topbar.querySelector(".menu-abrir")) {
            topbar.insertBefore(abrir, topbar.firstChild);
        }
    }

    if (document.querySelector(".topbar")) {
        colocarBotaoAbrir();
    } else {
        document.addEventListener("DOMContentLoaded", colocarBotaoAbrir);
    }

    const fundo = document.createElement("div");
    fundo.className = "menu-fundo";
    fundo.addEventListener("click", fecharMenuCelular);
    app.appendChild(fundo);

    function fecharMenuCelular() {
        app.classList.remove("menu-aberto");
    }

    document.addEventListener("keydown", function(e) {
        if (e.key === "Escape") fecharMenuCelular();
    });

    MENU_CELULAR.addEventListener("change", function() {
        fecharMenuCelular();
        atualizarTituloBotao();
    });

}


function formatarData(dataISO) {

    if (!dataISO) {
        return "";
    }

    const partes =
        dataISO.split("-");

    return `${partes[2]}/${partes[1]}/${partes[0]}`;

}


/* evita injeção de HTML */
function escapeHTML(valor) {

    return String(valor)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");

}


function mostrarSenha() {

    const senha =
        document.getElementById("senhaOperador");

    if (senha.type === "password") {
        senha.type = "text";
    } else {
        senha.type = "password";
    }

}

function mostrarSenhaAdmin() {

    const senha =
        document.getElementById("novaSenha");

    if (senha.type === "password") {

        senha.type = "text";

    } else {

        senha.type = "password";

    }

}


document.addEventListener("DOMContentLoaded", function() {
    configurarMenuRetratil();
});

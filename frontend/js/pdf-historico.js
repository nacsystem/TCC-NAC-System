/* NAC System - PDF do histórico de envases (jsPDF + autotable) */

(function (raiz) {

    /* cores */
    const COR = {
        fundo:      [7, 16, 14],        /* verde quase preto da tela */
        verde:      [85, 240, 163],     /* destaque neon da marca    */
        verdeEscuro:[8, 122, 72],
        verdeClaro: [232, 247, 240],
        texto:      [28, 38, 34],
        cinza:      [110, 125, 120],
        linha:      [222, 230, 226],
        zebra:      [247, 250, 249],
        branco:     [255, 255, 255]
    };

    /* cores de cada status */
    const STATUS = {
        "ESTÉRIL":     { fundo: [220, 245, 232], texto: [8, 122, 72] },
        "CONTAMINADA": { fundo: [253, 228, 228], texto: [190, 40, 40] },
        "INDEFINIDO":  { fundo: [253, 245, 210], texto: [140, 105, 0] },
        "CANCELADO":   { fundo: [235, 237, 236], texto: [110, 125, 120] }
    };

    const M = 12;           /* margem lateral (mm) */
    const TOPO_PAGINAS = 17;
    const RODAPE = 14;


    function fmtNum(n) {
        return Number(n).toLocaleString("pt-BR");
    }

    function dataBR(iso) {
        const p = String(iso).split("-");
        return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
    }

    function agoraBR() {
        const d = new Date();
        const dois = function (v) { return String(v).padStart(2, "0"); };
        return dois(d.getDate()) + "/" + dois(d.getMonth() + 1) + "/" + d.getFullYear() +
            " às " + dois(d.getHours()) + ":" + dois(d.getMinutes());
    }

    function descreverFiltros(f) {
        f = f || {};
        const sala = f.sala ? "Sala " + f.sala : "Todas as salas";
        let periodo = "Todo o período";
        if (f.de && f.ate) periodo = dataBR(f.de) + " a " + dataBR(f.ate);
        else if (f.de) periodo = "A partir de " + dataBR(f.de);
        else if (f.ate) periodo = "Até " + dataBR(f.ate);
        const turno = (typeof TURNOS !== "undefined" ? TURNOS : []).find(function (t) { return t.id === f.turno; });
        if (turno) periodo += "   |   Turno: " + turno.nome + " (" + turno.faixa + ")";
        return { sala: sala, periodo: periodo };
    }


    function gerar(op) {

        const jsPDF = op.jsPDF;
        const envases = op.envases || [];
        const usuario = op.usuario || "";
        const gerado = agoraBR();
        const filtros = descreverFiltros(op.filtros);

        const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });

        const LARG = doc.internal.pageSize.getWidth();
        const ALT = doc.internal.pageSize.getHeight();

        function tabela(opcoes) {
            if (typeof doc.autoTable === "function") return doc.autoTable(opcoes);
            return op.autoTable(doc, opcoes);
        }

        function cor(tipo, rgb) {
            const metodo = { fill: "setFillColor", draw: "setDrawColor", text: "setTextColor" }[tipo];
            doc[metodo](rgb[0], rgb[1], rgb[2]);
        }


        /* ---------- números gerais ---------- */

        const validos = envases.filter(function (e) { return !e.cancelado; });
        const total = validos.length;
        const nCancelados = envases.length - validos.length;
        const contar = function (nome) {
            return validos.filter(function (e) { return e.classificacao === nome; }).length;
        };
        const nEsteril = contar("ESTÉRIL");
        const nContaminada = contar("CONTAMINADA");

        const grupos = {};
        envases.forEach(function (e) {
            (grupos[e.sala] = grupos[e.sala] || []).push(e);
        });
        const salas = Object.keys(grupos).sort(function (a, b) {
            return (Number(a) - Number(b)) || a.localeCompare(b);
        });


        /* ---------- cabeçalho da 1ª página ---------- */

        cor("fill", COR.fundo);
        doc.rect(0, 0, LARG, 34, "F");
        cor("fill", COR.verde);
        doc.rect(0, 34, LARG, 1.2, "F");

        let xTexto = M;

        if (op.logo) {
            try {
                cor("fill", COR.branco);
                doc.roundedRect(M, 6, 22, 22, 3, 3, "F");
                doc.addImage(op.logo, "JPEG", M + 1, 7, 20, 20);
                xTexto = M + 28;
            } catch (e) { /* segue sem o logo */ }
        }

        cor("text", COR.verde);
        doc.setFont("helvetica", "bold");
        doc.setFontSize(9);
        doc.text("NAC SYSTEM", xTexto, 14, { charSpace: 1.6 });

        cor("text", COR.branco);
        doc.setFontSize(20);
        doc.text("Histórico de Envases", xTexto, 24);

        doc.setFont("helvetica", "normal");
        doc.setFontSize(8.5);
        cor("text", [166, 181, 177]);
        doc.text("Gerado em " + gerado, LARG - M, 14, { align: "right" });
        if (usuario) doc.text("Por: " + usuario, LARG - M, 19.5, { align: "right" });


        /* ---------- filtros ---------- */

        let y = 44;

        cor("text", COR.cinza);
        doc.setFontSize(8);
        doc.setFont("helvetica", "bold");
        doc.text("FILTROS", M, y);

        cor("text", COR.texto);
        doc.setFont("helvetica", "normal");
        doc.setFontSize(10);
        doc.text(filtros.sala + "   |   " + filtros.periodo, M + 20, y);


        /* ---------- cartões-resumo ---------- */

        y += 6;

        const cartoes = [
            { rotulo: "ENVASES NO PERÍODO", valor: fmtNum(total), cor: COR.texto },
            { rotulo: "ESTÉREIS", valor: fmtNum(nEsteril), cor: STATUS["ESTÉRIL"].texto },
            { rotulo: "CONTAMINADOS", valor: fmtNum(nContaminada), cor: STATUS["CONTAMINADA"].texto },
            { rotulo: "CANCELADOS", valor: fmtNum(nCancelados), cor: COR.cinza }
        ];

        const gap = 5;
        const larguraCartao = (LARG - 2 * M - gap * (cartoes.length - 1)) / cartoes.length;

        cartoes.forEach(function (c, i) {
            const x = M + i * (larguraCartao + gap);
            cor("fill", COR.zebra);
            cor("draw", COR.linha);
            doc.setLineWidth(0.3);
            doc.roundedRect(x, y, larguraCartao, 20, 2.5, 2.5, "FD");

            cor("fill", COR.verdeEscuro);
            doc.roundedRect(x, y, 1.6, 20, 0.8, 0.8, "F");

            cor("text", COR.cinza);
            doc.setFont("helvetica", "bold");
            doc.setFontSize(7.5);
            doc.text(c.rotulo, x + 6, y + 7.5, { charSpace: 0.5 });

            cor("text", c.cor);
            doc.setFontSize(17);
            doc.text(c.valor, x + 6, y + 16);
        });

        y += 20 + 9;


        /* ---------- uma seção por sala ---------- */

        salas.forEach(function (numero) {

            const lista = grupos[numero];
            const producao = lista[0].producao;
            const ativos = lista.filter(function (e) { return !e.cancelado; });
            const nE = ativos.filter(function (e) { return e.classificacao === "ESTÉRIL"; }).length;
            const nC = ativos.filter(function (e) { return e.classificacao === "CONTAMINADA"; }).length;

            if (y > ALT - RODAPE - 38) {
                doc.addPage();
                y = TOPO_PAGINAS + 2;
            }

            /* barra da sala */
            cor("fill", COR.verdeClaro);
            doc.roundedRect(M, y, LARG - 2 * M, 9.5, 2, 2, "F");

            cor("text", COR.verdeEscuro);
            doc.setFont("helvetica", "bold");
            doc.setFontSize(11);
            doc.text("SALA " + numero, M + 4, y + 6.4);

            const rotuloProd = producao ? "EM PRODUÇÃO" : "PARADA";
            const larguraRotulo = doc.getTextWidth("SALA " + numero) + 12;
            cor("fill", producao ? COR.verdeEscuro : [200, 70, 70]);
            doc.roundedRect(M + larguraRotulo, y + 2.3, 27, 4.9, 2.4, 2.4, "F");
            cor("text", COR.branco);
            doc.setFontSize(6.5);
            doc.text(rotuloProd, M + larguraRotulo + 13.5, y + 5.7, { align: "center" });

            cor("text", COR.cinza);
            doc.setFont("helvetica", "normal");
            doc.setFontSize(8.5);
            doc.text(
                ativos.length + (ativos.length === 1 ? " envase" : " envases") +
                "   |   " + nE + " estéril(is)   |   " + nC + " contaminado(s)",
                LARG - M - 4, y + 6.2, { align: "right" }
            );

            y += 12;

            const temObs = lista.some(function (e) { return e.observacao || e.cancelado; });

            const colunas = [
                { header: "Data", dataKey: "data" },
                { header: "Hora", dataKey: "hora" },
                { header: "Grau", dataKey: "grau" },
                { header: "0,5 µm", dataKey: "p05" },
                { header: "5,0 µm", dataKey: "p50" },
                { header: "Classificação", dataKey: "classificacao" },
                { header: "Registrado por", dataKey: "registrado_por" }
            ];
            if (temObs) colunas.push({ header: "Observação", dataKey: "observacao" });

            const linhas = lista.map(function (e) {
                return {
                    data: e.data,
                    hora: e.hora,
                    grau: e.grau || "-",
                    p05: fmtNum(e.p05),
                    p50: fmtNum(e.p50),
                    classificacao: e.cancelado ? "CANCELADO" : e.classificacao,
                    registrado_por: e.registrado_por,
                    observacao: e.cancelado
                        ? "Cancelado por " + e.cancelado_por + " em " + e.cancelado_em + ": " + e.motivo_cancelamento
                        : (e.observacao || "")
                };
            });

            tabela({
                startY: y,
                columns: colunas,
                body: linhas,
                theme: "grid",
                margin: { top: TOPO_PAGINAS, bottom: RODAPE, left: M, right: M },
                styles: {
                    font: "helvetica", fontSize: 8.5, cellPadding: { top: 2.4, bottom: 2.4, left: 3, right: 3 },
                    textColor: COR.texto, lineColor: COR.linha, lineWidth: 0.15, valign: "middle"
                },
                headStyles: {
                    fillColor: COR.verdeEscuro, textColor: COR.branco, fontStyle: "bold",
                    fontSize: 8, lineColor: COR.verdeEscuro
                },
                alternateRowStyles: { fillColor: COR.zebra },
                columnStyles: {
                    p05: { halign: "right" },
                    p50: { halign: "right" },
                    classificacao: { halign: "center", fontStyle: "bold", cellWidth: 34 },
                    data: { cellWidth: 24 },
                    hora: { cellWidth: 20 },
                    grau: { cellWidth: 14, halign: "center" }
                },
                didParseCell: function (d) {
                    if (d.section === "head" && (d.column.dataKey === "p05" || d.column.dataKey === "p50")) {
                        d.cell.styles.halign = "right";
                    }
                    if (d.section === "head" && d.column.dataKey === "classificacao") {
                        d.cell.styles.halign = "center";
                    }
                    if (d.section === "body" && d.column.dataKey === "classificacao") {
                        const s = STATUS[d.cell.raw];
                        if (s) {
                            d.cell.styles.fillColor = s.fundo;
                            d.cell.styles.textColor = s.texto;
                        }
                    }
                }
            });

            y = doc.lastAutoTable.finalY + 9;

        });


        /* ---------- cabeçalho pequeno e rodapé em todas as páginas ---------- */

        const paginas = doc.getNumberOfPages();

        for (let i = 1; i <= paginas; i++) {

            doc.setPage(i);

            if (i > 1) {
                cor("fill", COR.fundo);
                doc.rect(0, 0, LARG, 10, "F");
                cor("fill", COR.verde);
                doc.rect(0, 10, LARG, 0.7, "F");
                cor("text", COR.verde);
                doc.setFont("helvetica", "bold");
                doc.setFontSize(8);
                doc.text("NAC SYSTEM", M, 6.4, { charSpace: 1.2 });
                cor("text", [166, 181, 177]);
                doc.setFont("helvetica", "normal");
                doc.text("Histórico de Envases  |  " + filtros.sala + "  |  " + filtros.periodo, LARG - M, 6.4, { align: "right" });
            }

            cor("draw", COR.linha);
            doc.setLineWidth(0.3);
            doc.line(M, ALT - 10.5, LARG - M, ALT - 10.5);

            cor("text", COR.cinza);
            doc.setFont("helvetica", "normal");
            doc.setFontSize(8);
            doc.text("NAC System  |  Gerado em " + gerado + (usuario ? " por " + usuario : ""), M, ALT - 6);
            doc.text("Página " + i + " de " + paginas, LARG - M, ALT - 6, { align: "right" });
        }

        return doc;
    }


    const NacPDF = { gerar: gerar };

    if (typeof module !== "undefined" && module.exports) {
        module.exports = NacPDF;
    } else {
        raiz.NacPDF = NacPDF;
    }

})(typeof window !== "undefined" ? window : globalThis);

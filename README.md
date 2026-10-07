# NAC System

Banco de dados automatizado para o monitoramento de partículas em envases de vacinas na indústria farmacêutica veterinária.

## Integrantes

- Marina G. Neves
- Pedro Henrique V. Amaro
- Leonardo José O. Cabral
- Murilo Antônio F. Correa

**Turma:** 3º B – Informática
**Curso:** Técnico em Informática – Colégio Técnico Bento Quirino
**Orientador:** Prof. Mateus Amendola Redivo
**Ano:** 2026

## Descrição

O NAC System recebe os dados gerados por um contador de partículas, processa essas informações com um conversor em Python e armazena tudo em um banco de dados. Assim, o registro deixa de ser feito à mão, em papel.

Cada sala tem um grau de classificação (A, B ou C). O sistema compara as contagens de partículas de 0,5 µm e 5,0 µm com os limites desse grau e classifica cada coleta.

### Funcionalidades

- Login com dois perfis: **Administrador** e **Operador**.
- O administrador cadastra salas, define o grau de cada sala, gerencia operadores e define quais salas cada operador atende.
- O operador registra envases nas salas atribuídas a ele.
- Histórico de envases por sala, com cancelamento justificado. Os registros não são apagados.
- Gráficos das partículas por sala.
- Exportação do histórico em PDF.

> Os resultados apresentados no TCC foram obtidos por simulação. O sistema não foi validado em uma linha de produção real.

## Tecnologias

| Camada | Ferramentas |
|---|---|
| Backend | Python, Flask |
| Banco de dados | SQLite (local), PostgreSQL (online) |
| Frontend | HTML, CSS, JavaScript |
| Gráficos / PDF | Chart.js, jsPDF |
| Hospedagem | Render |

## Como executar localmente

Pré-requisito: Python 3.10 ou superior.

```bash
# 1. Clonar o repositório
git clone [LINK DO REPOSITÓRIO]
cd [PASTA DO PROJETO]

# 2. Instalar as dependências
pip install -r requirements.txt

# 3. Iniciar o servidor
python app.py
```

Depois, acesse `http://localhost:5000` no navegador. Rodando localmente, o sistema usa SQLite, que é criado automaticamente.

## Fluxo de uso

1. O **administrador** cadastra as salas e define o grau de cada uma.
2. O administrador cadastra os operadores e atribui as salas que cada um vai atender.
3. O **operador** registra os envases nas suas salas.
4. O histórico, os gráficos e a exportação em PDF ficam disponíveis por sala.

---

## Termos de Uso e Compartilhamento

**Autores:** Marina G. Neves, Pedro Henrique V. Amaro, Leonardo José O. Cabral, Murilo Antônio F. Correa
**Orientador:** Mateus Amendola Redivo
**Projeto:** NAC System, TCC Técnico em Informática, Colégio Técnico Bento Quirino, 2026

© 2026 Marina G. Neves, Pedro Henrique V. Amaro, Leonardo José O. Cabral e Murilo Antônio F. Correa. Todos os direitos reservados, exceto o que está expressamente permitido abaixo.

### Permitido
- Consultar e estudar o código para fins educacionais.
- Uso para avaliação do TCC e apresentação acadêmica.
- Uso não comercial por terceiros, desde que respeitadas as condições de crédito abaixo.

### Condições
1. **Crédito obrigatório:** qualquer uso, cópia, adaptação ou divulgação deve citar os autores pelo nome e incluir link para este repositório.
2. **Sem fins lucrativos:** é proibido usar, vender, licenciar ou oferecer este código (ou derivados) como produto ou serviço comercial sem contratar os autores previamente.
3. **Uso institucional:** o uso pela instituição de ensino além da avaliação do TCC (outros projetos, sistemas internos, divulgação) depende de autorização prévia e por escrito dos autores.
4. **Derivados:** trabalhos derivados devem manter este aviso e indicar o que foi alterado.

### Contato
Para solicitar autorização ou contratar os autores:

**Marina G. Neves**
- E-mail: marinagneves00@gmail.com
- GitHub: [marinagneves](https://github.com/marinagneves)
- LinkedIn: [marina-neves](https://www.linkedin.com/in/marina-neves-660a21441)

**Pedro Henrique V. Amaro**
- E-mail: pvamaro08@gmail.com
- GitHub: [wyphamaro](https://github.com/wyphamaro)
- LinkedIn: [pedro-henrique-vicente-amaro](https://www.linkedin.com/in/pedro-henrique-vicente-amaro-25aa19441)

**Leonardo José O. Cabral**
- E-mail: leoonardo.jose.cabral@gmail.com
- GitHub: [leocabral747](https://github.com/leocabral747)
- LinkedIn: [leo-cabral](https://www.linkedin.com/in/leo-cabral-aa2a1b441)

**Murilo Antônio F. Correa**
- E-mail: muriloafc08@gmail.com
- GitHub: [MuriloAntonio08574](https://github.com/MuriloAntonio08574)
- LinkedIn: [murilo-antonio-fernandes-correa](https://www.linkedin.com/in/murilo-antonio-fernandes-correa-75a0b1442)

### Isenção de garantia
O software é fornecido "como está", sem garantias de qualquer tipo.

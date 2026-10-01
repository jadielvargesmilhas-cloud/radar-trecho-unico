# Radar de Tarifas — Trecho único Europa → Salvador

Um robô gratuito que, todo dia às 08:00, pesquisa no Google Flights o menor preço **só de ida** para **2 adultos** saindo de **Madrid, Lisboa, Barcelona e Paris (Charles de Gaulle e Orly) para Salvador**, nos dias **3, 4, 5 e 6 de julho de 2027**, em **econômica e executiva**. São 32 combinações por dia. O painel responde à pergunta: *em cada dia, qual rota é a mais barata?* E você recebe **um resumo no celular** sempre que algum preço cair.

Custo: R$ 0. Tempo para montar: cerca de 20 minutos, uma vez só.

**Outras cidades da Europa:** uma vez por semana (domingo), o robô também varre 21 outras cidades europeias (Porto, Vigo, Londres, Amsterdã, Frankfurt, Roma e outras, lista completa no `config.json`) com as mesmas datas e classes. **Só entram as cidades com voo mais barato que as 4 principais** em pelo menos uma das datas (até 5 por classe, as de maior economia). Elas viram **alternativas** e passam a ser monitoradas todo dia, entrando na disputa de "mais barata de cada dia". Na varredura seguinte a lista é refeita: quem piorou sai, quem melhorou entra. Quando uma cidade nova sai mais barata, chega um aviso **🔎** no celular.

**Como a busca funciona:** a fonte principal é gratuita e sem limite (fast-flights, que lê o Google Flights). A SerpApi entra só como reserva, no máximo 8 buscas por dia, para caber no plano grátis de 250 por mês. Se a fonte principal falhar, a reserva atualiza primeiro as combinações que estão há mais tempo sem leitura; assim, em no máximo 4 dias, todas as 32 são atualizadas.

---

## O que você vai precisar (todos gratuitos)

1. Uma conta no **GitHub** (é onde o robô mora e roda sozinho).
2. Uma conta na **SerpApi** (reserva: 250 pesquisas grátis por mês; o robô usa no máximo 8 por dia e só quando a fonte principal falha).
3. O aplicativo **ntfy** no celular (é por onde chegam os avisos).

---

## Passo 1 — Instalar o app de avisos no celular

1. Abra a Play Store (Android) ou App Store (iPhone) e instale o app **ntfy**.
2. Abra o app e toque no botão **+**.
3. Em "Topic name", invente um nome difícil de adivinhar, por exemplo `radar-jadiel-7k29q`. **Anote esse nome.** (Qualquer pessoa que souber o nome consegue ler os avisos, por isso ele precisa ser difícil.)
4. Toque em **Subscribe**.

## Passo 2 — Pegar a chave grátis da SerpApi

1. Entre em **serpapi.com** e clique em **Register**. Crie a conta (o plano Free não pede cartão).
2. Confirme o e-mail.
3. No painel, procure **Your Private API Key** e clique no ícone de copiar. **Guarde essa chave**, ela é como uma senha.

## Passo 3 — Criar o repositório no GitHub

1. Entre em **github.com**, clique em **Sign up** e crie a conta (se ainda não tiver).
2. No canto superior direito, clique no **+** e depois em **New repository**.
3. Em "Repository name" escreva `radar-trecho-unico`.
4. Use um repositório **novo**, separado do outro radar. Marque **Public**, ligue **Add a README file** (precisa ser público para o painel funcionar de graça; ninguém vê suas chaves, só os preços).
5. Clique em **Create repository**.

## Passo 4 — Enviar os arquivos

1. Descompacte o arquivo `radar-trecho-unico.zip` no seu computador.
2. Na página do repositório recém-criado, clique no link **uploading an existing file**.
3. Abra a pasta descompactada, selecione **tudo que está dentro dela** e arraste para a página do GitHub.
   - Atenção: dentro dela existe uma pasta chamada `.github`. Ela precisa ir junto. No Mac, se não aparecer, aperte **Cmd + Shift + .** (ponto) para mostrar pastas ocultas.
4. Espere a lista de arquivos carregar e clique no botão verde **Commit changes**.
5. Confira: na página do repositório devem aparecer `.github`, `data`, `tests`, `config.json`, `index.html`, `monitor.py`, `requirements.txt` e este `LEIAME.md`.

**Se a pasta `.github` não subir** (acontece em alguns navegadores): clique em **Add file** e depois **Create new file**. No campo do nome, digite exatamente `.github/workflows/radar.yml`. Abra o arquivo `radar.yml` do seu computador no Bloco de Notas, copie tudo, cole no GitHub e clique em **Commit changes**.

## Passo 5 — Guardar as chaves em segredo

1. No repositório, clique em **Settings** (a engrenagem, no alto).
2. No menu da esquerda: **Secrets and variables**, depois **Actions**.
3. Clique em **New repository secret** e crie:
   - Name: `SERPAPI_KEY` / Secret: a chave do Passo 2. Clique em **Add secret**.
   - Name: `NTFY_TOPIC` / Secret: o nome do tópico do Passo 1. Clique em **Add secret**.

## Passo 6 — Ligar o painel

1. Ainda em **Settings**, no menu da esquerda, clique em **Pages**.
2. Em "Build and deployment", no campo **Source**, escolha **GitHub Actions**.
3. Não clique em nenhum botão "Configure" de modelos sugeridos: o robô publica o painel sozinho ao final de cada busca.
4. O endereço do painel será `https://SEU-USUARIO.github.io/radar-trecho-unico/` (ele passa a funcionar depois da primeira busca com ✅ verde). **Salve nos favoritos do celular.**

## Passo 7 — Primeira busca e teste do aviso (o teste de verdade)

1. Clique na aba **Actions** do repositório. Se aparecer um botão verde pedindo para habilitar, clique nele.
2. À esquerda, clique em **Radar de Tarifas**.
3. À direita, clique em **Run workflow**, mude a primeira opção (notificação de teste) para **sim** e clique no botão verde **Run workflow**.
4. Espere uns 25 minutos. A primeira execução já inclui a varredura das outras cidades da Europa (mais de 200 buscas, com pausas para não ser bloqueado). Nos dias comuns, leva de 5 a 10 minutos. Deve aparecer um círculo verde ✅.
5. No celular deve chegar: **"✅ Radar trecho único conectado"**.
6. Abra o painel. Devem aparecer os 4 dias, cada um com a cidade mais barata, a tabela completa com as alternativas (marcadas como "alternativa") e a seção **Outras cidades da Europa**. Use o botão **Econômica / Executiva** para alternar.

**Conferência obrigatória na 1ª vez:** no painel, clique em **Ver voos** de um dos dias, confira no Google Flights que é só ida, 2 adultos, na classe certa, e compare o total. Os valores devem bater (pode haver pequena diferença se o preço mudou entre uma consulta e outra).

A partir daí não precisa fazer mais nada: o robô roda sozinho todo dia às 08:00.

---

## Como funcionam os avisos

Uma mensagem por dia, só se algo caiu. Ela lista cada queda (📉) e os recordes (🏆 menor preço já visto daquela combinação), e termina com a rota mais barata de cada dia na econômica. Se nada for lido, chega **⚠️ Radar trecho único falhou hoje**: um dia isolado é normal; se repetir por 3 dias, me chame.

Quer ser avisado só de quedas grandes? No `config.json`, mude `alertar_quando_cair_pelo_menos_reais` de `1` para, por exemplo, `200`.

## O botão "Ver voos"

Abre o Google Flights **já preenchido**: cidade de origem, Salvador, a data, 2 adultos, a classe (econômica ou executiva) e "só ida". É o mesmo endereço que o robô usa para ler o preço. Também dá para clicar nos preços verdes da seção "Outras cidades mais baratas" e no botão "Ver este voo" do gráfico, quando você escolhe uma casa da tabela.

Na seção "Outras cidades mais baratas", se nenhuma cidade bater as 4 principais, a tabela não aparece: fica só uma linha avisando que a varredura rodou.

## Varrer a Europa fora do domingo

Aba **Actions**, depois **Radar Trecho Unico** e **Run workflow**. Mude a segunda opção (varrer a Europa) para **sim**.

## Como mudar a lista de cidades da varredura

No `config.json`, dentro de `descoberta`:
- `candidatas`: a lista de cidades. Para incluir uma, copie uma linha existente e troque o código do aeroporto (por exemplo `{"id":"DUB","cidade":"Dublin","aeroportos":["DUB"]}`).
- `promover_ate_por_classe`: no máximo quantas cidades mais baratas ficam no monitoramento diário (padrão 5).
- `dia_da_semana`: o dia da varredura (`segunda` a `domingo`).
- `ativa`: `false` desliga a varredura.

## Como mudar datas, classes, passageiros ou cidades

Tudo fica no arquivo `config.json`. No GitHub, clique nele, depois no lápis ✏️, altere e clique em **Commit changes**.

- `datas`: a lista de dias, no formato ano-mês-dia. Pode pôr mais ou menos dias.
- `classes`: `"economy"` (econômica) e `"business"` (executiva). Tire uma se não quiser.
- `adultos`: número de passageiros.
- Cada data a mais soma 8 buscas por dia (4 cidades × 2 classes). Até umas 10 datas o robô dá conta tranquilamente.
- Datas que já passaram saem do monitoramento sozinhas.

Se mudar passageiros ou classe, o histórico antigo deixa de ser comparável. Nesse caso, apague o conteúdo de `data/historico.json` e deixe só isto: `{"combos": {}, "alertas": [], "execucoes": [], "uso_serpapi": {}}`

## Avisos também no Telegram (opcional)

1. No Telegram, fale com **@BotFather**, envie `/newbot` e siga as instruções. Ele te dá um *token*.
2. Mande qualquer mensagem para o seu robô novo.
3. Abra no navegador `https://api.telegram.org/botSEU_TOKEN/getUpdates` e procure `"chat":{"id":` — esse número é o seu *chat id*.
4. Crie dois segredos no GitHub (como no Passo 5): `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`.

## Limites honestos

- **O preço das alternativas não inclui chegar até elas.** Se você estiver em Madri, Porto só compensa se a diferença cobrir o trem ou voo até lá, mais o tempo. O painel mostra a diferença em reais justamente para você fazer essa conta.
- A varredura só encontra cidades que estão na lista. Nenhuma ferramenta gratuita permite pesquisar "qualquer lugar da Europa → Salvador" de uma vez.
- A varredura faz muitas buscas seguidas no Google. Se ele bloquear parte delas, as cidades sem resposta aparecem como "Sem voo encontrado nesta varredura" (a reserva paga da SerpApi não é gasta com a varredura).

- A fonte é o **Google Flights**, que reúne companhias aéreas e agências. Não existe forma gratuita e legal de varrer todos os sites (Decolar, MaxMilhas etc.) automaticamente.
- **Passagens com milhas não entram** neste robô.
- O GitHub pode atrasar o horário das 08:00 em alguns minutos (às vezes até 1 hora) em dias de muito uso.
- A fonte principal (fast-flights) não é um serviço oficial: lê a página do Google Flights e pode ser bloqueada em alguns dias. Por isso existe a reserva com rodízio. Se o bloqueio virar rotina, o painel mostra quantas combinações ficaram sem leitura, e a solução é um plano pago pequeno da SerpApi.
- O valor mostrado é o menor total encontrado no momento da leitura. Sempre confirme no site antes de pagar.

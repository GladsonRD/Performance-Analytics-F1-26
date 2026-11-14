# Telemetria F1 26 → relatório HTML

Grava a telemetria do F1 26 enquanto você joga e, quando a sessão termina
(qualificação ou corrida), gera um relatório HTML com as análises e abre no navegador.

## 1. Instalar (uma vez só)

Baixe o programa em https://github.com/GladsonRD/Performance-Analytics-F1-26 (botão verde
**Code → Download ZIP**), extraia e abra a pasta **f1_telemetria**. Depois dê dois cliques em **INSTALAR.vbs** (não abre janela de comando, só avisos). Ele confere se o Python está instalado
(se não estiver, tenta instalar sozinho) e cria o atalho **"Telemetria F1 26"**
na Área de Trabalho.

Se o Windows mostrar "O Windows protegeu o computador", clique em
*Mais informações → Executar assim mesmo*.

## 2. Configurar o jogo (uma vez só)

No F1 26: **Configurações → Configurações de telemetria**

| Opção | Valor |
|---|---|
| UDP Telemetry | On |
| UDP Broadcast Mode | Off |
| UDP IP Address | 127.0.0.1 |
| UDP Port | 20777 |
| UDP Send Rate | 60 Hz (ou 30/20 Hz para arquivos menores) |
| UDP Format | **2026** |

Se você já usa outro app de telemetria na porta 20777, só um dos dois consegue
escutar por vez. Nesse caso, rode o gravador em outra porta (`--porta 20778`)
e configure o jogo para essa porta.

## 3. Usar

1. Abra o atalho **Telemetria F1 26** antes de jogar.
2. Na primeira vez, clique em **Escolher pasta...** e escolha onde os relatórios
   vão ficar. A pasta fica salva e, das próximas vezes, a gravação já começa sozinha.
3. Jogue normalmente, com a janela aberta (pode minimizar).
4. No fim de cada sessão o relatório é gerado e aberto no navegador. Tudo fica
   organizado por fim de semana:

       Sua pasta/
         Brasil 11-11-2026 19h07/
           Q1 11-11-2026 19h07.html
           Q2 11-11-2026 19h31.html
           Q3 11-11-2026 19h52.html
           Corrida 11-11-2026 20h15.html
           dados/        (gravações brutas, para gerar o relatório de novo)

   O horário da pasta é o da primeira sessão. Sessões do mesmo GP no mesmo dia,
   com até 4 horas de diferença, ficam juntas na mesma pasta.

5. Para parar, clique em **Parar** ou feche a janela. Se uma sessão estiver em
   andamento, ele gera o relatório do que foi gravado até ali.

Cada arquivo leva a data e o horário de início da sessão, então nada é sobrescrito.

Para gerar um relatório de novo (por exemplo, quando o relatório ganhar análises
novas), arraste o arquivo da pasta `dados` para cima do **gerar_relatorio.bat**.

Quem preferir o modo texto pode rodar `modo_texto.bat` ou `python gravar.py`.

## O que tem no relatório

- **Resumo**: posição, melhor volta e diferença para a mais rápida, volta ideal
  (soma dos seus melhores setores), ritmo médio e consistência, velocidade máxima,
  pit stops, punições.
  - **Seu resumo**: curvas onde você perde para o mais rápido da sessão (freada antes ou
    depois, velocidade no meio, retomada do acelerador), travamentos, patinação,
    sub/sobreesterço com sugestão de acerto, bateria (onde zera, onde o rival usa boost
    e você não) e pneus (temperatura de abertura da volta, janela ideal do composto,
    superaquecimento e pressão). Clique no número da curva para abrir na Análise de volta.
  - **Resumo da sessão**: rankings de velocidade máxima, velocidade média, speed trap,
    melhor volta, melhores setores, volta ideal, consistência, voltas válidas e avisos
    de limite de pista.
- **Resultado / classificação** completa (passe o mouse nos pneus para ver o desgaste).
- **Corrida**: posição volta a volta; diferença entre os pilotos que você escolher
  (em relação ao líder ou a qualquer piloto); dispersão do ritmo de até 8 pilotos;
  estratégia de pneus de todos, com o desgaste no fim de cada stint.
- **Voltas da sessão**: suas voltas e as dos outros pilotos; tempos, setores, voltas inválidas, pneu, desgaste total e na volta,
  combustível (kg, gasto, saldo em voltas e quanto economizou ou gastou a mais em cada volta).
- **Onde o pneu se gasta** (corrida, aba Pneus e combustível): mapa da pista colorido pelo
  desgaste do pneu em cada trecho de 25 m (% por km), por piloto, composto e roda, e as curvas
  que mais gastam pneu.
- **Volta rápida** (só na classificação): a melhor volta de cada piloto — tabela de tempos (setores, velocidade no
  fim de cada setor, velocidade máxima e speed trap, com o melhor de cada coluna em roxo),
  diferença para a volta mais rápida, velocidade máxima e o **domínio da pista** (mapa com a
  cor do piloto mais rápido em cada um dos 25 minissetores; escolha até 4 pilotos).
- **Análise de volta**: escolha duas voltas (suas ou a melhor de qualquer piloto).
  O mapa, a tabela curva a curva e os gráficos de diferença, velocidade, acelerador,
  freio, marcha, volante, yaw rate (°/s), bateria e modo de bateria andam juntos:
  passe o mouse em um e o ponto aparece nos outros; clique numa curva (na faixa, na tabela
  ou no mapa) para dar zoom; clique em S1, S2 ou S3 para ver só aquele setor.
  O mapa pode ser colorido por ganho/perda, bateria, velocidade ou setores.
  Na opção **traçado e replay**, o mapa mostra a pista com os dois traçados e os dois
  carrinhos andando no mesmo tempo de volta (play/pause, velocidade 0,25× a 2×, câmera
  seguindo os carros, botão ⛶ para tela cheia). Quando a asa abre (modo reta), sai um
  rastro de ar da traseira do carro. Embaixo, volante, freio, acelerador, velocidade,
  marcha, asa e a diferença entre os dois.
  A opção **mostrar trecho antes da linha** inclui o fim da volta de saída (ou da volta
  anterior) nos gráficos, no mapa e no replay. O trecho começa 10 m antes do primeiro dos
  dois pilotos ligar a bateria (procurando até 700 m antes da linha): dá para ver onde
  cada um ligou e com que velocidade e bateria cruzou a linha. O tempo da volta continua
  contando da linha.
- **Pneus, combustível e energia** (corrida): desgaste e temperatura dos pneus,
  saldo de combustível desde a largada e ERS em %. Na classificação, aba **Energia**.
  Nas duas, dá para comparar a energia volta a volta com outros pilotos.
- **Eventos**: punições, ultrapassagens, safety car, colisões, voltas mais rápidas.

Todos os gráficos arrastam (pan) com o mouse; use os botões + e − no canto para zoom.

Observações:
- Os gráficos usam a biblioteca Plotly carregada da internet ao abrir o relatório.
- Em sessões online, a telemetria detalhada dos outros pilotos só aparece se eles
  deixaram a telemetria pública no jogo.
- Flashbacks são tratados: os dados "desfeitos" são descartados.

## Testar sem o jogo

`python simulador.py corrida --udp` manda uma corrida fictícia para o gravador
(abra o painel antes). Use `quali` para uma qualificação.


## Bordas da pista (traçado e replay)

O jogo não manda onde fica o asfalto, então cada pista tem um arquivo em `pistas/` com as bordas:

- **Mapeada (mais precisa):** com o programa gravando, dê uma volta colado na borda esquerda e outra
  colado na direita (no contra o relógio, por exemplo). Depois clique em **Mapear bordas da pista...**
  na janela e escolha a gravação (`.f1rec.gz`, na pasta `dados` do evento). Basta uma vez por pista.
- **Acumulada (automática):** cada relatório junta os traçados de todos os pilotos da sessão; a borda
  é até onde os carros já passaram, com folga. Fica melhor a cada sessão gravada.


## Atualizar

Ao abrir, a janela confere se há versão nova no GitHub. Quando houver, o botão **Atualizar** ganha
um ● — clique nele, espere o aviso e abra o programa de novo pelo atalho. A atualização não mexe
na sua pasta de saída, nas gravações nem nas bordas das pistas.

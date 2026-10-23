# Rastreador de Preços de Mercado 🥩🏷️

Aplicativo **desktop para Windows** que acompanha o preço de itens de
supermercado em **R$/kg** em três lojas com entrega no Distrito Federal —
**Sam's Club**, **Swift** e **Superadega** — e avisa quando aparece uma
**nova mínima** ou uma **queda de preço**, por **Telegram** e/ou **notificação
do Windows**.

Interface nativa (não é um servidor web). Você escolhe os itens, define os
padrões de busca e de **exclusão**, e o programa varre as lojas no intervalo
configurado, guardando o histórico de preços localmente.

> Projeto independente, derivado do rastreador do meu homelab. Sem chaves de
> API, sem servidores externos: tudo roda na sua máquina.

## Como usar (versão portátil)

1. Baixe o `RastreadorPrecos-portable.zip` na aba **[Releases](../../releases)**.
2. Extraia a pasta em qualquer lugar (Documentos, Área de Trabalho, um pendrive…).
3. Rode **`Iniciar.bat`**.
   - Na **primeira execução** o programa pergunta se pode baixar os componentes
     (interface e rede, ~100 MB). Tudo é instalado **dentro da própria pasta** —
     nada é alterado no sistema.
4. Abra a aba **⚙️ Configurações**, preencha seu **CEP** (para ver os preços do
   DF) e, se quiser alertas no Telegram, o **token do bot** e o **chat ID**.
   Ative/desative notificações à vontade — as configurações são **persistentes**.
5. Na aba **📋 Itens rastreados**, clique **➕ Adicionar** para incluir um item.
6. Clique **🔍 Escanear agora** (ou espere o intervalo agendado).

A pasta é **portátil**: mova-a e seus dados (banco de preços, configurações,
itens) vão junto, em `data/`.

### Campos de um item

| Campo | Exemplo | Para quê |
|---|---|---|
| Nome | `Bacalhau (lombo/posta)` | rótulo exibido e agrupador |
| Sam's Club (busca) | `bacalhau` | busca full-text no Sam's |
| Swift (categorias) | `pescados/bacalhau` | caminho de categoria da Swift |
| Superadega (busca) | `bacalhau` | termo de busca na Superadega |
| Padrão válido (regex) | `bacalhau\|saithe` | título **precisa** casar |
| **Texto de exclusão (regex)** | `desfiad\|bolinho\|croquete` | título **não** pode casar |
| Exigir R$/kg | ✔ | descarta itens sem peso computável |

## Notificações

- **Telegram** — crie um bot com o [@BotFather](https://t.me/BotFather), copie o
  token, descubra seu chat ID (ex.: [@userinfobot](https://t.me/userinfobot)).
- **Toast do Windows** — nativo, não precisa de nada.
- Há um interruptor **mestre** e interruptores por canal e por tipo de evento
  (novas mínimas / quedas). Botão **“Enviar notificação de teste”** para validar.

## Desenvolvimento

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r app/requirements.txt
python app/main.py
```

- `app/engine/` — motor sem GUI: scrapers httpx (VTEX + ibecom), banco SQLite,
  normalização R$/kg, notificações. Verificável isoladamente:
  `python tests/verify_engine.py` faz uma varredura real e confere os R$/kg.
- `app/gui/` — interface PySide6 (Qt), gráficos via QtCharts.

### Gerar o ZIP portátil

```powershell
pwsh -File build/build_portable.ps1
```

Baixa o Python embutido, habilita o pip, empacota `app/` + `Iniciar.bat` e gera
`build/RastreadorPrecos-portable.zip`. O mesmo passo roda no CI
(`.github/workflows/release.yml`) ao publicar uma tag `vX.Y.Z`.

## Licença

MIT.

## Telegram: grupo e tópico

Após sincronizar, abra Configurações, selecione o tópico aprovado no grupo
Notificações e salve. Configurações antigas com chat privado são recusadas até
essa atualização. O envio exige tópico explícito; não há fallback para General.
Os testes de roteamento usam HTTP simulado e não enviam mensagens reais.

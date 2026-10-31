# ALITA – Getting started

> **🤖 AI-generated guide.** This guide was written entirely by the AI assistant Claude (Anthropic) and has not been
> edited by the ALITA team. Check it against the application; if something differs, the application is right.
> More detail: [User Manual](ALITA-User-Manual.md).

ALITA turns research material – projects in all their versions, papers, notes, laws – into a knowledge map and a
knowledge graph you can question. This page gets you from opening ALITA to your first answer in a few minutes.

## 1. What works without a key, and what needs one

| Without an OpenRouter key | Needs your own OpenRouter API key |
|---|---|
| Look at the knowledge map, clusters, the 3D/time view | **Asking questions** in the Graph Chat (B) and the Document Chat (A) |
| Browse and open documents and their details | **Ask now** in the guided tour |
| Take the **guided tour** (reading the steps, putting example questions into the chat) | Uploading documents (summaries and embeddings) |

ALITA has no shared key: **every user – reviewers too – brings their own key**. Questions are processed by the
language model GPT-6 Luna through [OpenRouter](https://openrouter.ai); each answer shows what it cost.

## 2. Get an OpenRouter API key (once)

1. **Create an account** at [openrouter.ai](https://openrouter.ai) (**Sign in** → Google, GitHub or e-mail).
2. **Add credit** at [openrouter.ai/settings/credits](https://openrouter.ai/settings/credits). ALITA uses a paid model,
   so the key needs credit; a few euros last for many questions.
3. **Create a key** at [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) → **Create Key**, name it
   e.g. `ALITA`; a spending limit is a good idea. **Copy the key right away** – it starts with `sk-or-` and is shown only once.

Fees, payment methods and limits: [User Manual → Get an OpenRouter API key](ALITA-User-Manual.md#get-an-openrouter-api-key).

## 3. Enter the key in ALITA

1. Paste the key into the field **OpenRouter API-Key** at the top and click **Save**.
2. The status next to it changes from **no key** to **Key …** with the last four characters.
3. The key stays **only in the memory of this page**. It is not stored on the server and is gone after a reload –
   paste it again then. Treat it like a password; if it leaks, delete it on OpenRouter and create a new one.

## 4. Take the guided tour

Click **▶ Guided tour** in the header, next to the version number. The tour takes about ten minutes and walks through
ALITA along the propositions of our research submission *"Explore or Exploit? An AI Research Memory Map that Makes
Scholars' Epistemic Trajectories Observable and Contestable"*:

> Research is usually judged by its final version; the trajectory behind it – ideas proposed, tested, dropped and
> recombined across drafts – stays scattered and fades. ALITA makes this trajectory visible and contestable through
> three mechanisms: it **refreshes memory** (within a project and across projects), it **makes the argument
> traceable**, and it **supports updating one's schemes** – so that the choice between **exploring** a new path and
> **exploiting** the current one is made with the trajectory in view.

| Step | What you see | Proposition |
|---|---|---|
| 1 | Welcome | the trajectory problem; the three mechanisms |
| 2 | The databases | what the collection contains (public: EU AI Act, Wachter) |
| 3 | The knowledge map | refresh memory: "where have we been?" |
| 4 | **Compare** EU AI Act ↔ Wachter | horizontal sense-making – beyond one's own research bubble |
| 5 | Ask about what the map shows | the map's links, followed through the ontology to the text |
| 6 | Version history of a law | vertical sense-making – a trajectory over versions |
| 7 | Papers → articles they discuss | traceability – explicit relations, not only similarity |
| 8 | The law's document details | the same relation, seen from the law |
| 9 | Let ALITA argue back | updating schemes – challenge a position, check the sources |
| 10 | Your own projects (with the password) | explored or exploited? knowledge stages of a project |
| 11 | Closing | explore or exploit; limits and what is planned |

**How to use it:** **Next** / **Back** (or → / ←), **Esc** or ✕ to close. Steps with an example question offer
**Put into Graph Chat** (inserts it; you press **Send**) and **Ask now** (sends it – needs your key). The tour switches
pages and highlights the part of the screen it explains; you can click around in between. A link ending in `?tour=1`
starts the tour on opening.

## 5. Everyday use in five points

1. **Pick the scope.** The database bar on top selects databases; a click on a cluster or project in the knowledge map
   narrows both chats to it. **Clear selection** widens the scope again.
2. **Choose the chat.** **B – Graph Chat** (B page) follows the connections: clusters, projects, people, methods,
   citations, laws. **A – Document Chat** (tab A/B) searches the text and is best for content and details.
3. **Ask in your own words**, in English or German. Name clusters ("C8 and C9"), articles ("Art. 31 AI Act") or a project.
4. **Check the sources.** Every statement cites numbered sources [n]; click a number to read the passage. The graph path
   under the answer shows how ALITA got there. ALITA's answers come from a language model and **can be wrong**.
5. **Open documents** in the tab **Documents** or by clicking them in the map: summary, methods, versions, citations,
   and for papers and laws the articles discussed.

Other databases (research projects) appear after entering the password next to the key field. Conversations stay only
in this page; export them via **History** → ⤓ .txt before closing.

---

> **🤖 AI-generated guide** – written entirely by Claude (Anthropic) for ALITA 3.12.0, not edited by the ALITA team.

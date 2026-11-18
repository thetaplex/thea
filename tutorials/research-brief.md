# Write a Sourced Research Brief

In this tutorial, you will use the **Research Assistant** persona to search the web and record sources in a ledger. Then you will take notes and write a checked research brief.

## Before You Start

Complete [Build and Preview a Local Project](first-project.md) first. You also need:

- `Docker` (`https://docs.docker.com/get-docker/`) for local web search
- `Node.js` 24 or later (`https://nodejs.org`) for the `sequential-thinking` `MCP` server

## Step 1: Start the Local Search Engine

The **Research Assistant** searches through a local `SearXNG` container first.

1. Make sure Docker is running.
2. Start `SearXNG` from the repository folder:
   ```bash
   docker run -d --name thea-searxng --restart unless-stopped \
     -p 127.0.0.1:8888:8080 -e SEARXNG_SECRET=$(openssl rand -hex 32) \
     -v "$PWD/docker/searxng:/etc/searxng" searxng/searxng:latest
   ```
3. Check that the container answers on `http://127.0.0.1:8888`.

## Step 2: Create a Research Project

1. In the left sidebar of Thea, click **New** next to **Projects**.
2. Select **Research Assistant** in **Assistant Persona**.
3. Select the **Empty Project** template.
4. Choose a new empty folder, such as `~/projects/reflexion-study`.
5. Type `Reflexion Study` in **Project Name** and click **Create Project**.

## Step 3: Ask a Research Question

1. In the chat box, type this prompt and press **Enter**:
   ```text
   Write a short research brief at research/drafts/reflexion.md on how the Reflexion paper (arXiv 2303.11366) uses verbal reinforcement. Cite at least 2 sources.
   ```
2. If an approval card asks to write files in this project, click **Always Allow for Project**.

## Step 4: Watch the Research Pipeline Run

As Thea works, it follows a strict sequence of tools:

1. It plans with `sequentialthinking` and writes `TASK.md` in the project root.
2. It plans its steps with the `sequentialthinking` tool. Each thought appears as a collapsed **Thought** block in the chat. Click **Thought** to read it.
3. It looks up the paper metadata with `lookup_paper` and searches the web with `web_search`.
4. It registers each source with `add_source`. This tool writes the verified record to `research/sources.json` and returns a key such as `[S1]`.
5. It writes factual notes to `research/notes.md`, tagged with `[S1]` and `[S2]`.
6. It writes the draft to `research/drafts/reflexion.md` from `research/notes.md`.
7. It runs `check_citations` to check that every `[S#]` key exists in `research/sources.json`.

## Step 5: Inspect the Research Files

1. Open the **Files** tab in the right pane and click **Refresh**.
2. Click `TASK.md` to see the completed `- [x]` checklist items.
3. Click `research/sources.json` to see the JSON records for `[S1]` and `[S2]`.
4. Click `research/notes.md` to see the notes for each source.
5. Click `research/drafts/reflexion.md` to read the finished brief in the **Artifacts** preview.
6. Click the thumbs-up button (`Good answer`) under the reply to save a lesson from this run.

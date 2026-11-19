# Build and Preview a Local Project

In this tutorial, you will start a local model and create an empty project. Then you will ask Thea to make a web page, approve the change, and view the live preview.

## Before You Start

1. Install Thea. See [Install Thea](../how-to/install-thea.md).
2. Install `Ollama` (`https://ollama.com`).

## Step 1: Start `Ollama` and Pull a Model

1. Open a terminal and start the `Ollama` server:
   ```bash
   ollama serve
   ```
2. In a second terminal, pull `qwen3:8b`:
   ```bash
   ollama pull qwen3:8b
   ```

## Step 2: Open Thea

1. Open **Thea** from your applications.
2. Check the model selector in the top right of the titlebar. Make sure it shows `Ollama` and `qwen3:8b`. If it shows another model, click the model box and select `qwen3:8b`.

## Step 3: Create an Empty Project

1. In the left sidebar, under **Projects**, click **New**.
2. In the **Create or Open Project** dialog, select **Personal Assistant** in **Assistant Persona**.
3. Select the **Empty Project** template.
4. Click **Browse** next to **Workspace Folder Path** and choose an empty folder on your disk, such as `~/projects/thea-demo`.
5. Type `Thea Demo` in **Project Name**.
6. Click **Create Project**.

## Step 4: Ask Thea to Make a Page

1. Click the chat input box at the bottom of the center pane.
2. Type this prompt and press **Enter**:
   ```text
   Create index.html: a page with a counter button that adds 1 on each click. Put the CSS and the JavaScript in the same file.
   ```
3. Watch the chat view. Thea writes a checklist in `TASK.md`, then prepares `index.html` with `write_file`.

## Step 5: Approve the File Writes

Each time Thea calls `write_file` or `edit_file`, an approval card appears in the chat view. The first card is for `TASK.md`. The next card is for `index.html`.

1. Read the change in the approval card.
2. Click **Approve Once** to let Thea write the file. (Click **Always Allow for Project** if you want to skip write prompts for this project during this session.)
3. Do these steps again for each approval card.

## Step 6: Preview the Page

1. Click the `Open Artifacts & Files pane` button in the top right of the titlebar.
2. Click the **Files** tab at the top of the right pane, then click `index.html`.
3. Thea opens `index.html` in the **Artifacts** tab. Click **Preview** in the artifact bar and test your counter button inside the preview `iframe`.

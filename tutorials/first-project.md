# Build and Preview a Local Project

In this tutorial, you will start a local model and create a project from a template. Then you will ask Thea to edit a file, approve the change, and view the live preview.

## Before You Start

Install these tools on your computer:

- `Rust` (`https://rustup.rs`)
- `pnpm` (`https://pnpm.io/installation`)
- `just` (`https://github.com/casey/just`)
- `Ollama` (`https://ollama.com`)

Open a terminal in the repository root and install the JavaScript packages:

```bash
just setup
```

## Step 1: Start `Ollama` and Pull a Model

1. Open a terminal and start the `Ollama` server:
   ```bash
   ollama serve
   ```
2. In a second terminal, pull `qwen3:8b`:
   ```bash
   ollama pull qwen3:8b
   ```

## Step 2: Launch Thea

1. Run the development app from the repository root:
   ```bash
   just run
   ```
2. Wait for the Thea window to open.
3. Check the model selector in the top right of the titlebar. Make sure it shows `Ollama` and `qwen3:8b`. If it shows another model, click the model box and select `qwen3:8b`.

## Step 3: Create a Project from a Template

1. In the left sidebar, find the **Persona** dropdown and select **Software Engineer**.
2. Under **Projects**, click **New**.
3. In the **Create or Open Project** dialog, select the `Interactive HTML / Canvas` template (`static-html`).
4. Click **Browse** next to **Workspace Folder Path** and choose an empty folder on your disk, such as `~/projects/thea-demo`.
5. Type `Thea Demo` in **Project Name**.
6. Click **Create Project**.

Thea scaffolds `index.html`, `style.css`, and `main.js` into your folder.

## Step 4: Inspect Your Workspace Files

1. Click the `Open Artifacts & Files pane` button in the top right of the titlebar.
2. Click the **Files** tab at the top of the right pane.
3. Click `index.html` in the file list.

Thea opens `index.html` in the **Artifacts** tab and shows the live preview.

## Step 5: Ask Thea to Change the Page

1. Click the chat input box at the bottom of the center pane.
2. Type this prompt and press **Enter**:
   ```text
   Edit index.html and main.js to show a counter button that adds 1 on each click.
   ```
3. Watch the chat view. Thea reads the project files with `read_file` and then prepares an edit with `edit_file` or `write_file`.

## Step 6: Approve the File Edit

When Thea calls `edit_file` or `write_file`, an approval card appears in the chat view.

1. Read the unified diff in the approval card.
2. Click **Approve Once** to let Thea write the file. (Click **Always Allow for Project** if you want to skip write prompts for this project during this session.)
3. When the turn finishes, click the **Artifacts** tab in the right pane and select `index.html`.
4. Click **Preview** in the artifact bar and test your counter button inside the preview `iframe`.

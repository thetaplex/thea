# Create and Manage Custom Skills

A skill holds instructions in Markdown that the model loads on demand with the `load_capability` tool.

1. Click **Settings** in the left sidebar and select the **Skills** tab.
2. Click **New Skill**.
3. Type a short name in **Skill Name**, such as `api-review`.
4. Choose `Global` in **Scope** to save the skill in `~/.thea/skills.json`, or choose `Current Project` to save it in `<project>/.thea/skills.json`.
5. Type a trigger rule in **Short Trigger Description**. Start the description with `Use when` so the model knows when to load it.
6. Write the Markdown steps in **Markdown Instructions (SKILL.md body)**.
7. Click **Save Skill**.
8. Use the checkbox next to any skill in the **Skills** tab to turn it on or off.

# Review and Edit Persona Lessons

Thea writes a short lesson to `~/.thea/lessons/<persona-id>.md` after a citation check or a user rating. It also writes a lesson when a tool fails on 3 calls with the same error.

1. After a chat turn, click the thumbs-up (`Good answer`) or thumbs-down (`Bad answer`) button to start a reflection step.
2. To inspect or edit the stored lessons, open `~/.thea/lessons/<persona-id>.md` in your text editor.
3. Keep each lesson on 1 line in the format `- YYYY-MM-DD | <signal> | When X, do Y.`.
4. Delete any line that you do not want Thea to include in future prompts for that persona.

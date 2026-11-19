# Close the source, hide built-in skills, split the docs trees

Date: 2026-11-15. Status: proposed.

## Intent

Thea will be sold as a product. The repository is private and nothing has been
published, so the Apache-2.0 license and the open-source scaffolding grant
nothing and only confuse. The docs must separate what a user of the installed
app reads from what a developer of the code reads, because only the user docs
will go to a public repository later.

## Goals

- No open-source license or scaffolding remains in the repo.
- Built-in skills do not appear in the Skills pane. Custom skills still do.
- `docs/` holds only pages for users of the installed app.
- `docs/dev/` holds pages for developers of the code.
- The STE style test covers both trees.

## Non-goals

- The public repository, release automation, and installer-based user
  tutorials. These are the next piece of work and wait for a first release.
- Any change to the personas or agent.

## Anti-goals

- Deleting content. Every page moves or gets trimmed; none is lost.
- A user page that names a Rust file, a constant, or a `just` recipe.

## Approaches

1. **Two trees in one repo, dev under `docs/dev/`** (picked). One source of
   truth, the style test walks both, a release action later copies `docs/`
   out. Developer pages sit one folder deeper.
2. **Docs authored in the public repo.** Lets outsiders fix docs, but the
   style test and the docs drift from the code they describe. Rejected.
3. **Separate `docs/user/` and `docs/dev/`.** Symmetric, but every existing
   link and the sync step have to know about `user/`. More churn for no gain.

## Decisions

- **License.** `LICENSE` becomes a short copyright notice: "Copyright 2026
  ThetaPlex. All rights reserved." with a line that no license is granted.
  `NOTICE` is deleted. `package.json` gets `"license": "UNLICENSED"`,
  `Cargo.toml` gets `license = "LicenseRef-Proprietary"`.
- **Scaffolding.** Delete `CONTRIBUTING.md`. Remove the Contributing, Security
  Policy, and License links from the README. The CHANGELOG stays; it is a
  product changelog.
- **Hidden built-in skills.** `discover_skills` still returns them so
  `load_skill` works, but the `list_skills` IPC command filters out
  `source == "builtin"`. The disable toggle for built-ins becomes unreachable
  and stays in code; the setting is harmless.
- **Page moves to `docs/dev/`.** `how-to/run-eval.md`,
  `how-to/build-installers.md`, `explanation/architecture.md`,
  `reference/cli-and-ste-rules.md`, and the whole `docs/superpowers/` folder.
  `docs/dev/README.md` is a new index for them.
- **Trim user pages.** Remove source paths, constant names, and `just` recipes
  from the remaining explanation and reference pages. Where a constant backs a
  number, keep the number. Where a page explains code structure for its own
  sake, move that paragraph to the architecture page.
- **Two READMEs.** The repo `README.md` becomes a developer README: one
  paragraph on what Thea is, prerequisites, the `just` recipes, a pointer to
  `docs/` and `docs/dev/`. `docs/README.md` keeps the product description and
  becomes the future public README; its index drops the moved pages.
- **Style test.** Add `docs/dev` to the directories the test walks.

## Left to the builder

Exact wording of trimmed paragraphs, and whether the Skills pane header count
should say "Custom skills" now that built-ins are gone.

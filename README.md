<!--
SPDX-FileCopyrightText: 2020 Jan-Philipp Kappmeier
SPDX-License-Identifier: Apache-2.0
-->

# azure-flashcards

Flashcards for some Azure exams by Microsoft.

## Content

- [AZ-300 Azure Architect Technologies](az-300-azure-architect-technologies)
- [AZ-304 Azure Architect Design](az-304-azure-architect-design)
- [AZ-900 Azure Fundamentals](az-900-fundamentals)

## Compilation

### Requirements

- `LuaLaTex`
- Packages: `doclicense`, `xmpincl`

#### Ubuntu:

- `texlive`
- `texlive-luatex`
- `texlive-fonts-extra`

## Anki decks

Anki decks can be generated from the LaTeX files as source. Anki decks are generated and not
committed. The generated `.txt` files are a build artifact attached to a release.

1. `python3 tools/latex_flashcards.py` writes `draft.md` files created from the LaTeX cards.
2. `python3 tools/md_to_anki.py ./az-900-fundamentals/"` builds an Anki txt import file.
3. In Anki: File → Import, *Existing notes: Update*.

For convenience, the `tools/tex_to_anki.py` script automates the creation of all flashcards
in this repository.

### Anki deck notes

Empty placeholder cards are skipped.

Card IDs are slugs of the card title (plus the subsection if a title repeats), so adding cards does
not change other IDs. However, **renaming** a title creates a new Anki note.

The scripts can be tested with:

```shell
python3 -m unittest discover tools
```

## License

Copyright © 2020 Jan-Philipp Kappmeier

- **Content** (flashcards, text, images, and the generated decks) is licensed
  under the terms of the [Creative Commons Attribution-ShareAlike 4.0 International](LICENSES/CC-BY-SA-4.0.txt) license.
- **Code and scripts** (everything under `tools/`, plus build scripts) are licensed
  under the terms of the [Apache License 2.0](LICENSES/Apache-2.0.txt) license.

When reusing the content, attribute it as:
"Azure Flashcards" by Jan-Philipp Kappmeier, https://github.com/kappmeier/azure-flashcards, licensed under `CC BY-SA 4.0`.

# SPDX-FileCopyrightText: 2026 Jan-Philipp Kappmeier
# SPDX-License-Identifier: Apache-2.0
"""Convert this repo's LaTeX flashcards to Anki decks under anki-decks/<deck>/.

Usage: python3 tools/tex_to_anki.py
Each deck gets a draft.md (written by latex_flashcards.py) and, next to it, the Anki
import .txt (written by md_to_anki.py). This file only lists the decks of this repository.
"""

from pathlib import Path

import md_to_anki
from latex_flashcards import convert

REPO_ROOT = Path(__file__).resolve().parent.parent
DECKS_DIR = REPO_ROOT / 'anki-decks'

# The content license; the same as in README.md and REUSE.toml.
LICENSE = ('Licensed under CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). '
           'Source: https://github.com/kappmeier/azure-flashcards')

DECKS = [
    (
        'az-900-fundamentals/azure-fundamentals.tex',
        'Azure::AZ-900 Fundamentals',
        'az900',
        'azure az-900',
        'az-900-fundamentals/draft.md',
    ),
    (
        'az-300-azure-architect-technologies/azure-architect-technologies.tex',
        'Azure::AZ-300 Architect Technologies',
        'az300',
        'azure az-300',
        'az-300-architect-technologies/draft.md',
    ),
    (
        'az-304-azure-architect-design/azure-architect-design.tex',
        'Azure::AZ-304 Architect Design',
        'az304',
        'azure az-304',
        'az-304-architect-design/draft.md',
    ),
]

for tex_rel, deck, prefix, tag, out_rel in DECKS:
    front_matter = {'deck': deck, 'guid-prefix': prefix, 'tags': tag}
    convert(REPO_ROOT / tex_rel, DECKS_DIR / out_rel, front_matter, LICENSE)
    print(md_to_anki.convert(DECKS_DIR / out_rel))

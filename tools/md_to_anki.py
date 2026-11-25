# SPDX-FileCopyrightText: 2026 Jan-Philipp Kappmeier
# SPDX-License-Identifier: Apache-2.0
"""Convert draft.md files to Anki import .txt files.

Usage: python3 md_to_anki.py deck_dir [deck_dir ...] [--out DIR] [--tag TAG ...]

Each deck directory holds one draft.md. The .txt is written
next to draft.md, or to DIR/<deck> when --out is given. --tag can be repeated and adds a
tag to every card of every converted deck. Cards without tags or src are listed on stderr.

A draft.md starts with front matter (deck, guid-prefix, tags). Each "## " heading opens a
section, whose slug becomes a tag. Each card looks like this:

    ### <id> <type> | tags: <tags> | src: <source>
    <front>
    ---
    <back>
"""

import argparse
import html
import re
import sys
from pathlib import Path

from latex_flashcards import slug

HEADER = (
    '#separator:tab\n#html:true\n#guid column:1\n#notetype column:2\n#deck column:3\n'
    '#tags column:6\n#columns:GUID\tNotetype\tDeck\tFront\tBack\tTags\n'
)
NOTETYPES = {'basic': 'Einfach'}
REQUIRED_FRONT_MATTER = ('deck', 'guid-prefix', 'tags')
SOURCE_DIV = '<div style="font-size:0.75em;color:#888;margin-top:0.6em">Source: {}</div>'

TEXT_FORMAT_BOLD_PATTERN = r'\*\*(.+?)\*\*'
"""Detects bold markdown text surrounded by **."""
TEXT_FORMAT_ITALIC_PATTERN = r'(?<!\w)\*([^*\s](?:[^*]*[^*\s])?)\*(?!\w)'
"""Detects italic markdown text surrounded by *."""

FRONT_MATTER_PATTERN = r'---\n(.*?)\n---\n'
"""Pattern to match the front matter block surrounded by --- at the beginning of an input file."""

CARD_HEAD_PATTERN = re.compile(r'^### (\S+) (\S+)((?: \| \w+: .*)?)$')
"""Match the card header with id, type, and optional options."""
CARD_OPTION_PATTERN = re.compile(r'\| (\w+): (.*?)(?= \| \w+: |$)')
"""Match an individual card option like "| key: value"."""
CODE_SPAN_PATTERN = re.compile(r'((?<!`)`[^`]+`(?!`))')
"""Find inline code spans between backticks like `code`."""
LIST_ITEM_PATTERN = re.compile(r'^((?:  )*)- (.*)$')
"""Match a markdown list item with optional indentation, ignoring odd indents."""


def styled_html(text):
    """Converts markdown text to HTML.

    Escapes the plain text and converts **bold** and *italic* to HTML."""
    text = html.escape(text, quote=False)
    text = re.sub(TEXT_FORMAT_BOLD_PATTERN, r'<b>\1</b>', text)
    return re.sub(TEXT_FORMAT_ITALIC_PATTERN, r'<i>\1</i>', text)


def inline(text):
    """Converts backtick code, **bold** and *italic* in one line to HTML.

    Code spans are escaped but never styled, so `a*b*c` keeps its asterisks.
    """
    html_parts = []
    # re.split with one capture group puts the code spans at the odd indexes
    for index, part in enumerate(CODE_SPAN_PATTERN.split(text)):
        if index % 2:
            html_parts.append('<code>' + html.escape(part[1:-1], quote=False) + '</code>')
        else:
            html_parts.append(styled_html(part))
    return ''.join(html_parts)


def list_item(line):
    """Returns the depth and text of a markdown list item.

    The value is a (depth, text) tuple for markdown list item lines, `None` otherwise.
    """
    match = LIST_ITEM_PATTERN.match(line)
    return (len(match.group(1)) // 2, match.group(2)) if match else None


def list_html(items):
    """Renders parsed list items as HTML.

    Takes `[(depth, text)]` list items and converts them as nested <ul>/<li> HTML.
    """
    html_parts = []
    depth = -1
    base_depth = items[0][0]
    for item_depth, text in items:
        item_depth = max(0, item_depth - base_depth)
        if item_depth > depth:
            html_parts.append('<ul>' * (item_depth - depth))
        else:
            html_parts.append('</li>' + '</ul></li>' * (depth - item_depth))
        html_parts.append('<li>' + inline(text))
        depth = item_depth
    html_parts.append('</li>' + '</ul></li>' * depth + '</ul>')
    return ''.join(html_parts)


def back_html(body):
    """Converts a card back from markdown to Anki HTML.

    Text lines are joined with <br>, and each blank line between two text lines adds one more.
    A list directly after text sits right below it. Blank lines after a list are dropped.
    """
    html_parts = []
    pending_items = []
    blank_lines = 0  # blank lines seen since the last text line
    after_text = False  # the last non-blank line was text, so the next block needs <br> before it
    for line in body.split('\n'):
        item = list_item(line)
        if pending_items and not item:
            html_parts.append(list_html(pending_items))
            pending_items = []
        if not line.strip():
            blank_lines += 1 if after_text else 0
            continue
        if after_text:
            html_parts.append('<br>' * (blank_lines + (0 if item else 1)))
        blank_lines = 0
        after_text = item is None
        if item:
            pending_items.append(item)
        else:
            html_parts.append(inline(line))
    if pending_items:
        html_parts.append(list_html(pending_items))
    return ''.join(html_parts)


def field(text):
    """Quote one field of a tab-separated Anki row and double the quotes inside it."""
    return '"' + text.replace('"', '""') + '"'


def parse_front_matter(text):
    """Splits a draft.md text into its front matter dict and the text after it."""
    match = re.match(FRONT_MATTER_PATTERN, text, re.S)
    if not match:
        raise ValueError('missing front matter')
    front_matter = dict(line.split(': ', 1) for line in match.group(1).split('\n') if ': ' in line)
    for key in REQUIRED_FRONT_MATTER:
        if key not in front_matter:
            raise ValueError(f'front matter lacks {key}')
    return front_matter, text[match.end():]


def parse_card(chunk, section):
    """Parses one card into a card dict.

    A card starts from its "### " header line to the end of its back. After the
    header line, the body is split into front and back by a "---" separator.
    """
    header_line, _, body = chunk.partition('\n')
    head_match = CARD_HEAD_PATTERN.match(header_line)
    if not head_match:
        raise ValueError(f'bad card header: {header_line}')
    card_id, card_type, option_text = head_match.groups()
    if card_type not in NOTETYPES:
        raise ValueError(f'card {card_id} has unknown type {card_type}')
    # a '#' line here is a mistyped header ("###two basic")
    # as part of the back it would swallow the next card
    stray_heading = re.search(r'(?m)^#.*', body)
    if stray_heading:
        raise ValueError(f'card {card_id} has a heading line in its body: {stray_heading.group()}')
    parts = re.split(r'(?m)^---[ \t]*$', body, maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f'card {card_id} has no --- separator')
    front, back = parts
    if not front.strip():
        raise ValueError(f'card {card_id} has an empty front')
    options = dict(CARD_OPTION_PATTERN.findall(option_text))
    return {
        'id': card_id, 'type': card_type, 'section': section,
        'tags': options.get('tags', ''), 'src': options.get('src', ''),
        'front': front.strip(), 'back': back.strip('\n'),
    }


def parse_draft(text):
    """Returns (front matter dict, [card dict]) from a draft.md text."""
    front_matter, body = parse_front_matter(text)
    cards, section = [], ''
    for chunk in re.split(r'(?m)^(?=## |### )', body):
        if chunk.startswith('## '):
            heading, _, text_below = chunk.partition('\n')
            # text here is the rest of a card back that a "## " line cut off
            if text_below.strip():
                raise ValueError(f'text under section heading: {heading}')
            section = heading[3:].strip()
        elif chunk.startswith('### '):
            cards.append(parse_card(chunk, section))
    return front_matter, cards


def warn_missing(deck_name, card):
    """Reports a card without tags or without src on stderr."""
    for key in ('tags', 'src'):
        if not card[key]:
            print(f"WARN {deck_name}: {card['id']} has no {key}", file=sys.stderr)


def card_row(guid, card, front_matter, extra_tags):
    """Build the tab-separated Anki row for one card."""
    front = '<br>'.join(inline(line) for line in card['front'].split('\n'))
    back = back_html(card['back'])
    if card['src']:
        back += SOURCE_DIV.format(html.escape(card['src'], quote=False))
    all_tags = ' '.join((front_matter['tags'], *extra_tags, slug(card['section']), card['tags'])) \
        .split()
    tags = ' '.join(dict.fromkeys(all_tags))  # to drop repeats, e.g. duplicated --tag
    values = (guid, NOTETYPES[card['type']], front_matter['deck'], front, back, tags)
    return '\t'.join(field(value) for value in values)


def convert(draft_path, out_dir=None, extra_tags=()):
    """Converts one draft.md and returns the path of the written .txt.

    The file goes to out_dir, or next to the draft when out_dir is None.
    Raises ValueError if the draft is malformed or two cards share an id.
    """
    front_matter, cards = parse_draft(draft_path.read_text(encoding='utf-8'))
    rows, seen_guids = [], set()
    for card in cards:
        guid = f"{front_matter['guid-prefix']}-{card['id']}"
        if guid in seen_guids:
            raise ValueError(f'duplicate card id {guid}')
        seen_guids.add(guid)
        warn_missing(draft_path.parent.name, card)
        rows.append(card_row(guid, card, front_matter, extra_tags))
    out_path = (out_dir or draft_path.parent) / (front_matter['deck'].replace('::', ' - ') + '.txt')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(HEADER + '\n'.join(rows) + '\n', encoding='utf-8')
    return out_path


def main(argv):
    """Converts the deck.md files in the given the deck directories.
     
    The directories as given in argv are processed and for each input file the corresponding
    output file is written.
    """
    parser = argparse.ArgumentParser(
        description='Convert <deck_dir>/draft.md files to Anki import .txt files.')
    parser.add_argument('decks', nargs='+', type=Path,
                        help='deck directories, each with a draft.md')
    parser.add_argument('--out', type=Path,
                        help='write each .txt to OUT/<deck> instead of next to draft.md')
    parser.add_argument('--tag', action='append', default=[],
                        help='tag for every card of every deck (repeatable)')
    args = parser.parse_intermixed_args(argv)
    for deck in args.decks:
        draft_path = deck / 'draft.md'
        if not draft_path.exists():
            print(f'SKIP {deck}: no draft.md', file=sys.stderr)
            continue
        try:
            print(convert(draft_path, args.out / deck.name if args.out else None, args.tag))
        except ValueError as error:
            sys.exit(f'{draft_path}: {error}')


if __name__ == '__main__':
    main(sys.argv[1:])

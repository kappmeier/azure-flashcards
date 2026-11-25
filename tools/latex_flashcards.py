# SPDX-FileCopyrightText: 2026 Jan-Philipp Kappmeier
# SPDX-License-Identifier: Apache-2.0
"""Generic conversion of LaTeX flashcards to Anki draft.md content.

Reads a LaTeX deck that uses ``\\sectioncard``/``\\subsectioncard``/
``\\subsubsectioncard`` headings and ``\\begin{flashcard}[label]{title}``
cards, and produces the Anki draft.md format consumed by build_deck.py.
Card IDs are slugs of the card title, so inserting a card does not shift
existing IDs.
"""

import hashlib
import re

# One scanner for heading commands and the flashcard environment opener.
CARD_TOKEN = re.compile(
    r'\\(sectioncard|subsectioncard|subsubsectioncard)\{'
    r'|\\begin\{flashcard\}(\[[^\]]*\])?\{'
)

# LaTeX commands that map directly to a Unicode symbol.
SYMBOL_COMMANDS = (
    (r'\\Rightarrow', '⇒'),
    (r'\\rightarrow', '→'),
    (r'\\leftrightarrow', '↔'),
    (r'\\geq', '≥'),
)

# Symbols that stay as-is when they appear inside $...$.
MATH_SYMBOLS = ('…', '⇒', '→', '↔', '≥')


def read_braced(text, open_index):
    """Return (content, end_index) for the ``{...}`` group starting at ``open_index``."""
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return text[open_index + 1:index], index + 1
    raise ValueError("unbalanced braces")


def expand_inputs(path):
    """Read ``path``, strip LaTeX comments, and recursively inline its ``\\input{...}`` files."""
    text = path.read_text(encoding='utf-8')
    text = re.sub(r'(?m)(?<!\\)%.*$', '', text)

    def replace_input(match):
        """Inline one ``\\input`` file relative to ``path``."""
        included = path.parent / (match.group(1) + '.tex')
        return expand_inputs(included)

    return re.sub(r'\\input\{([^}]*)\}', replace_input, text)


def format_texttt(content):
    """Unescape LaTeX specials in ``\\texttt`` content and wrap it in backticks."""
    content = content.replace('\\\\', ' ')
    for escaped, plain in (('\\_', '_'), ('\\#', '#'), ('\\$', '$'), ('\\&', '&'), ('\\%', '%')):
        content = content.replace(escaped, plain)
    return '`' + content.replace('`', "'") + '`'


def replace_command(text, name, formatter):
    """Replace every ``\\name{...}`` in ``text`` using ``formatter(content)``."""
    pattern = re.compile(r'\\' + name + r'\s*\{')
    while True:
        match = pattern.search(text)
        if not match:
            return text
        content, end = read_braced(text, match.end() - 1)
        text = text[:match.start()] + formatter(content) + text[end:]


def replace_hrefs(text):
    """Rewrite every ``\\href{url}{label}`` in ``text`` as ``label (url)``."""
    pattern = re.compile(r'\\href\s*\{')
    while True:
        match = pattern.search(text)
        if not match:
            return text
        url, after_url = read_braced(text, match.end() - 1)
        label, end = read_braced(text, after_url)
        text = text[:match.start()] + f'{label} ({url})' + text[end:]


def math_content(match):
    """Return a ``$...$`` group's content, italicized unless it is already a symbol."""
    content = match.group(1)
    return content if content in MATH_SYMBOLS else '*' + content + '*'


def inline(text):
    """Convert LaTeX inline markup in ``text`` to markdown."""
    text = replace_command(text, 'texttt', format_texttt)
    text = replace_command(text, 'emph', lambda content: '*' + content + '*')
    text = replace_command(text, 'textit', lambda content: '*' + content + '*')
    text = replace_command(text, 'textbf', lambda content: '**' + content + '**')
    text = replace_hrefs(text)
    for command, symbol in SYMBOL_COMMANDS:
        text = re.sub(r'\$' + command + r'\$|' + command, symbol, text)
    text = text.replace('\\ldots', '…').replace('\\,', '\u2009').replace('\\ ', ' ')
    for escaped, plain in (('\\%', '%'), ('\\&', '&'), ('\\_', '_'), ('\\#', '#'), ('\\$', '$')):
        text = text.replace(escaped, plain)
    text = re.sub(r'\$([^$]+)\$', math_content, text.replace('$\\ldots$', '…'))
    text = text.replace('\\newline', '\n').replace('~', ' ')
    text = re.sub(r'\\(vspace|hspace)\*?\{[^}]*\}', '', text)
    return text


def table_rows(body):
    """Convert a LaTeX tabular body to markdown, one ``a | b`` string per row."""
    body = re.sub(r'\\begin\{tabular\}\{[^}]*\}', '', body).replace('\\end{tabular}', '')
    rows = []
    for row in re.split(r'\\\\\s*(?:\[[^\]]*\])?', body):
        row = row.replace('\\hline', '')
        cells = [
            inline(cell.replace('\\tabitemindent', '').replace('\\tabitem', '•')).strip()
            for cell in row.split('&')
        ]
        if any(cells):
            rows.append(' | '.join(cell for cell in cells if cell))
    return '\n'.join(rows)


def flatten_texttt(body):
    """Collapse line breaks inside ``\\texttt{...}`` so the command stays on one line."""
    pos = 0
    pattern = re.compile(r'\\texttt\{')
    while True:
        match = pattern.search(body, pos)
        if not match:
            return body
        content, end = read_braced(body, match.end() - 1)
        flattened = re.sub(r'\s*\\\\?\s*\n\s*', ' ', content) if '\n' in content else content
        body = body[:match.end()] + flattened + body[end - 1:]
        pos = match.end() + len(flattened)


def render_item(match, depth, stack):
    """Render one ``\\item`` line to markdown, updating the enumerate counter in ``stack``."""
    label = match.group(1)
    marker = '' if not label else inline(label) + ' '
    is_enumerate = bool(stack) and stack[-1][0]
    if is_enumerate:
        stack[-1][1] += 1
        marker = f'{stack[-1][1]}. '
    text = marker + inline(match.group(2))
    if is_enumerate:
        return text
    if text.strip():
        return '  ' * depth + '- ' + text
    return '- '


def body_to_markdown(body):
    """Convert a flashcard body from LaTeX to markdown."""
    body = flatten_texttt(body)
    body = body.replace('\\vspace*{\\stretch{1}}', '').replace('\\vfill', '')
    body = re.sub(r'\\vspace\*?\{[^}]*\}', '', body)
    body = re.sub(
        r'\\begin\{tabular\}.*?\\end\{tabular\}',
        lambda match: '\n\x00' + table_rows(match.group(0)).replace('\n', '\x01') + '\n',
        body,
        flags=re.S,
    )
    output = []
    depth = -1
    stack = []
    for raw_line in body.split('\n'):
        line = raw_line.strip()
        if line.startswith('\x00'):
            output.extend(line.strip('\x00').split('\x01'))
            continue
        if line in ('\\begin{itemize}', '\\begin{enumerate}'):
            depth += 1
            stack.append([line.endswith('enumerate}'), 0])
            continue
        if line in ('\\end{itemize}', '\\end{enumerate}'):
            depth -= 1
            stack.pop()
            continue
        if line in ('\\begin{center}', '\\end{center}'):
            continue
        item_match = re.match(r'\\item(?:\[([^\]]*)\])?\s*(.*)', line)
        if item_match:
            output.append(render_item(item_match, depth, stack))
            continue
        if depth >= 0 and line and output and (
            output[-1].startswith('- ') or output[-1].lstrip().startswith('- ')
        ):
            output[-1] += ' ' + inline(line)
            continue
        output.append(inline(line))
    text = '\n'.join(output)
    text = re.sub(r'\n{3,}', '\n\n', text).strip('\n')
    return '\n'.join(line.rstrip() for line in text.split('\n'))


def card_id(front):
    """Return a stable slug ID for a card front, hashing the tail if it exceeds 50 chars."""
    slug_text = front.lower()
    for umlaut, replacement in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')):
        slug_text = slug_text.replace(umlaut, replacement)
    slug_text = re.sub(r'[^a-z0-9]+', '-', slug_text).strip('-') or 'card'
    if len(slug_text) <= 50:
        return slug_text
    # Hash the tail so long titles keep a unique, stable ID; the builder catches collisions.
    return slug_text[:45].rstrip('-') + '-' + hashlib.md5(front.encode()).hexdigest()[:4]


def slug(text):
    """Slugify ``text`` for use in tags, keeping German umlauts."""
    return re.sub(r'[^a-z0-9äöüß]+', '-', text.lower()).strip('-')


def heading_text(section, subsection):
    """Combine a section and subsection into one heading string."""
    return f'{section} – {subsection}' if subsection else section


def unique_front(front, subsubsection, subsection, seen):
    """Return (front, key) with a front title not yet in ``seen``, disambiguating duplicates."""
    key = front.lower()
    if key not in seen:
        return front, key
    suffix = subsubsection or subsection
    alt = f'{front} ({suffix})' if suffix else front
    alt_key = alt.lower()
    counter = 2
    while alt_key in seen:
        alt = f'{front} ({suffix}, {counter})'
        alt_key = alt.lower()
        counter += 1
    return alt, alt_key


def read_heading(text, match):
    """Read the value of a heading command at ``match``; return (value, next_pos)."""
    value, pos = read_braced(text, match.end() - 1)
    return inline(value).strip(), pos


def extract_card(text, match):
    """Read one flashcard at ``match``; return (label, title, body, next_pos)."""
    label = (match.group(2) or '[]')[1:-1].replace('\\ ', '').strip()
    title, after_title = read_braced(text, match.end() - 1)
    end = text.index('\\end{flashcard}', after_title)
    body = text[after_title:end]
    return label, title, body, end + 1


def parse_deck(text):
    """Yield ('heading', kind, value) and ('card', label, title, body) events from a LaTeX deck."""
    text = text[text.index('\\begin{document}'):]
    pos = 0
    while True:
        match = CARD_TOKEN.search(text, pos)
        if not match:
            return
        if match.group(1):
            value, pos = read_heading(text, match)
            yield 'heading', match.group(1), value
        else:
            label, title, body, pos = extract_card(text, match)
            yield 'card', label, title, body


class DeckWriter:
    """Accumulate headings and cards for one Anki deck."""

    def __init__(self):
        self.section = ''
        self.subsection = ''
        self.subsubsection = ''
        self.seen = set()
        self.lines = []
        self.heading = None
        self.count = 0

    def add_heading(self, kind, value):
        """Update the current section, subsection, or subsubsection from a heading command."""
        if kind == 'sectioncard':
            self.section = value
            self.subsection = ''
            self.subsubsection = ''
        elif kind == 'subsectioncard':
            self.subsection = value
            self.subsubsection = ''
        else:
            self.subsubsection = value

    def add_card(self, label, title, body):
        """Append one card's markdown, or print SKIP and do nothing if the card is empty."""
        front = inline(title).strip().replace('\n', ' ')
        back = body_to_markdown(body)
        if not front or not re.sub(r'[-–\s]', '', back):
            print('SKIP', front or '(no title)', '|', self.subsubsection or self.subsection)
            return
        heading = heading_text(self.section, self.subsection)
        if heading and heading != self.heading:
            self.lines.append(f'\n## {heading}\n')
            self.heading = heading
        front, key = unique_front(front, self.subsubsection, self.subsection, self.seen)
        self.seen.add(key)
        self.count += 1
        tags = f' | tags: {slug(label)}' if label and slug(label) else ''
        src = f' | src: {self.subsubsection}' if self.subsubsection else ''
        self.lines.append(f'### {card_id(front)} basic{tags}{src}\n{front}\n---\n{back}\n')

    def write(self, out_path, deck, prefix, tag):
        """Write the accumulated lines with the deck header to ``out_path`` and print a summary."""
        header = f'---\ndeck: {deck}\nguid-prefix: {prefix}\ntags: {tag}\n---\n'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(header + '\n'.join(self.lines), encoding='utf-8')
        print(out_path, self.count)


def convert(main_tex, deck, prefix, tag, out_path):
    """Convert the LaTeX deck ``main_tex`` into an Anki draft file at ``out_path``."""
    writer = DeckWriter()
    for event in parse_deck(expand_inputs(main_tex)):
        if event[0] == 'heading':
            writer.add_heading(event[1], event[2])
        else:
            writer.add_card(event[1], event[2], event[3])
    writer.write(out_path, deck, prefix, tag)

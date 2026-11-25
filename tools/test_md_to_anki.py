"""Tests for md_to_anki. Run with: python3 -m unittest discover tools"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import md_to_anki

FRONT_MATTER = '---\ndeck: Top::Sub\nguid-prefix: pre\ntags: deck-tag shared\n---\n'
DRAFT = FRONT_MATTER + '''
## Über Section

### one basic | tags: card-tag shared | src: Book p. 1
Front `a<b`
second "line"
---
Back

### two basic
Question
---
- Answer
'''


def convert_text(draft_text, extra_tags=()):
    """Converts a draft text in a temporary deck directory.
    
    Returns (output path name, output text, stderr)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        draft_path = Path(tmp_dir) / 'my-deck' / 'draft.md'
        draft_path.parent.mkdir()
        draft_path.write_text(draft_text, encoding='utf-8')
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            out_path = md_to_anki.convert(draft_path, extra_tags=extra_tags)
        return out_path.name, out_path.read_text(encoding='utf-8'), stderr.getvalue()


class Inline(unittest.TestCase):
    """Tests the inline formatting of markdown drafts."""
    def test_code_is_escaped(self):
        self.assertEqual(md_to_anki.inline('x `a<b` y'), 'x <code>a&lt;b</code> y')

    def test_code_is_not_styled(self):
        self.assertEqual(md_to_anki.inline('`*a*`'), '<code>*a*</code>')

    def test_bold_and_italic(self):
        self.assertEqual(md_to_anki.inline('**b** and *i*'), '<b>b</b> and <i>i</i>')

    def test_asterisks_inside_word_stay(self):
        self.assertEqual(md_to_anki.inline('x*y*z'), 'x*y*z')

    def test_double_backticks_stay(self):
        self.assertEqual(md_to_anki.inline("``q''"), "``q''")


class BackHtml(unittest.TestCase):
    """Tests the html generation function of markdown drafts."""
    def test_nested_list(self):
        self.assertEqual(md_to_anki.back_html('- a\n  - b\n- c'),
                         '<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>')

    def test_list_starting_indented_is_dedented(self):
        self.assertEqual(md_to_anki.back_html('  - a\n- b'), '<ul><li>a</li><li>b</li></ul>')

    def test_odd_indent_is_text(self):
        self.assertEqual(md_to_anki.back_html(' - a'), ' - a')

    def test_text_breaks(self):
        self.assertEqual(md_to_anki.back_html('a\nb\n\nc'), 'a<br>b<br><br>c')

    def test_blank_before_list_only(self):
        self.assertEqual(md_to_anki.back_html('a\n\n- b\n\nc'), 'a<br><ul><li>b</li></ul>c')


class Helpers(unittest.TestCase):
    """Tests helper functions of md_to_anki."""
    def test_slug_keeps_umlauts(self):
        self.assertEqual(md_to_anki.slug('Überwachung – Ä'), 'überwachung-ä')

    def test_field_doubles_quotes(self):
        self.assertEqual(md_to_anki.field('a"b'), '"a""b"')


class ParseDraft(unittest.TestCase):
    """Tests parsing of anki draft files."""
    def test_malformed_drafts_raise(self):
        cases = {
            'missing front matter': 'no front matter',
            'front matter lacks tags': '---\ndeck: D\nguid-prefix: p\n---\n',
            'bad card header': FRONT_MATTER + '### only-id\nq\n---\na\n',
            'unknown type': FRONT_MATTER + '### one cloze\nq\n---\na\n',
            'no --- separator': FRONT_MATTER + '### one basic\nq\na\n',
            'card one has an empty front': FRONT_MATTER + '### one basic\n---\na\n',
            'heading line in its body: ###two basic': FRONT_MATTER
            + '### one basic\nq\n---\na\n\n###two basic\nq\n---\na\n',
            'text under section heading: ## Cut': FRONT_MATTER
            + '### one basic\nq\n---\na\n## Cut\nrest of back\n',
        }
        for message, draft_text in cases.items():
            with self.subTest(message), self.assertRaisesRegex(ValueError, message):
                md_to_anki.parse_draft(draft_text)

    def test_separator_may_have_trailing_spaces(self):
        _, cards = md_to_anki.parse_draft(FRONT_MATTER + '### one basic\nq\n--- \na\n')
        self.assertEqual((cards[0]['front'], cards[0]['back']), ('q', 'a'))


class Convert(unittest.TestCase):
    """Tests conversion of a anki draft.
    """
    def test_rows(self):
        name, text, _ = convert_text(DRAFT)
        self.assertEqual(name, 'Top - Sub.txt')
        self.assertTrue(text.startswith(md_to_anki.HEADER))
        self.assertEqual(text[len(md_to_anki.HEADER):].split('\n'), [
            '"pre-one"\t"Einfach"\t"Top::Sub"\t"'
            + 'Front <code>a&lt;b</code><br>second ""line"""\t"Back'
            + md_to_anki.SOURCE_DIV.format('Book p. 1').replace('"', '""')
            + '"\t"deck-tag shared über-section card-tag"',
            '"pre-two"\t"Einfach"\t"Top::Sub"\t"'
            + 'Question"\t"<ul><li>Answer</li></ul>"\t"deck-tag shared über-section"',
            '',
        ])

    def test_warns_about_missing_tags_and_src(self):
        _, _, stderr = convert_text(DRAFT)
        self.assertEqual(stderr, 'WARN my-deck: two has no tags\nWARN my-deck: two has no src\n')

    def test_extra_tags_are_added_once(self):
        _, text, _ = convert_text(DRAFT, ['extra', 'shared'])
        self.assertTrue(text.endswith('\t"deck-tag shared extra über-section"\n'), text[-80:])

    def test_source_is_escaped(self):
        _, text, _ = convert_text(FRONT_MATTER + '### one basic | src: A & B <x>\nq\n---\na\n')
        self.assertIn('Source: A &amp; B &lt;x&gt;</div>', text)

    def test_duplicate_id_raises(self):
        with self.assertRaisesRegex(ValueError, 'duplicate card id pre-one'):
            convert_text(FRONT_MATTER + '### one basic\nq\n---\na\n\n### one basic\nq\n---\na\n')


class Main(unittest.TestCase):
    """Tests for the main logic of md_to_anki.

    Parsing options, errors, and handling of draft files.
    """
    def test_options_between_decks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            deck = Path(tmp_dir) / 'my-deck'
            deck.mkdir()
            (deck / 'draft.md').write_text(DRAFT, encoding='utf-8')
            out_dir = Path(tmp_dir) / 'out'
            arguments = ['--tag', 'extra', str(deck),
                         '--out', str(out_dir), str(Path(tmp_dir) / 'no-deck')]
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                md_to_anki.main(arguments)
            out_path = out_dir / 'my-deck' / 'Top - Sub.txt'
            self.assertEqual(stdout.getvalue(), f'{out_path}\n')
            self.assertIn(' extra ', out_path.read_text(encoding='utf-8'))
            self.assertIn('no-deck: no draft.md', stderr.getvalue())

    def test_error_names_the_draft(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            draft_path = Path(tmp_dir) / 'draft.md'
            draft_path.write_text(FRONT_MATTER + '### only-id\n', encoding='utf-8')
            with self.assertRaises(SystemExit) as raised:
                md_to_anki.main([tmp_dir])
            self.assertEqual(raised.exception.code, f'{draft_path}: bad card header: ### only-id')


if __name__ == '__main__':
    unittest.main()

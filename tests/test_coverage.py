import unittest
from scripts.tts_contract import kokoro_coverage

class CoverageTests(unittest.TestCase):
    def test_numeric_apostrophe_and_empty_slash_paragraph(self):
        self.assertEqual(kokoro_coverage('Copyright page\n\nBF531.N.9’11—dc21\n\n/'),
                         kokoro_coverage('Copyright pageBF531.N.911—dc21'))

    def test_missing_words_digits_and_ordinary_punctuation_still_fail(self):
        for original,returned in [('One two three','One three'),('911','91'),
                                  ("can't",'cant'),('1/2','12'),('A—B','AB')]:
            with self.subTest(original=original):
                self.assertNotEqual(kokoro_coverage(original),kokoro_coverage(returned))

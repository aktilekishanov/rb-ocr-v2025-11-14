import unittest

from rbidp.processors.fio_matching import fio_match


class TestFioMatching(unittest.TestCase):
    def assertMatch(self, app_fio, doc_fio, expected=True):
        matched, diag = fio_match(app_fio, doc_fio, enable_fuzzy_fallback=False)
        self.assertEqual(matched, expected, msg=f"Expected {expected} for app='{app_fio}' vs doc='{doc_fio}', diag={diag}")

    def test_full_full(self):
        self.assertMatch("Иванов Иван Иванович", "Иванов Иван Иванович", True)

    def test_lf_lf(self):
        self.assertMatch("Иванов Иван Иванович", "Иванов Иван", True)
        self.assertMatch("Иванов Иван", "Иванов Иван", True)

    def test_fp_fp(self):
        self.assertMatch("Иванов Иван Иванович", "Иван Иванович", True)
        self.assertMatch("Иванов Иван", "Иван Иванович", False)

    def test_l_i(self):
        self.assertMatch("Иванов Иван Иванович", "Иванов И", True)
        self.assertMatch("Иванов Иван", "Иванов И.", True)

    def test_l_io(self):
        self.assertMatch("Иванов Иван Иванович", "Иванов И.О.", True)
        self.assertMatch("Иванов Иван Иванович", "Иванов И О", True)
        self.assertMatch("Иванов Иван", "Иванов И.О.", False)

    def test_negative(self):
        self.assertMatch("Иванов Иван Иванович", "Петров Иван Иванович", False)
        self.assertMatch("Иванов Иван", "Петров И", False)


if __name__ == "__main__":
    unittest.main()

from hallubib.abbrevs import expand, known_count


class TestAbbrevs:
    def test_database_loaded(self):
        assert known_count() > 1000

    def test_expand_known_abbreviation(self):
        full = expand("Am. Econ. Rev.")
        assert "american" in full and "economic" in full

    def test_expand_full_name_unchanged(self):
        result = expand("American Economic Review")
        assert "american" in result and "economic" in result

    def test_expand_unknown_passthrough(self):
        result = expand("Totally Fake Journal Name XYZ123")
        assert "totally" in result

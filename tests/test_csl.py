from hallubib.bib import to_bib
from hallubib.csl import from_csl, to_csl
from hallubib.parser import parse_bib
from hallubib.types import Name, OnlineRecord, Reference

_BIB = """
@article{gs62,
  author = {Gale, David and Shapley, Lloyd S.},
  title = {College Admissions and the Stability of Marriage},
  journal = {The American Mathematical Monthly},
  year = {1962},
  month = jan,
  volume = {69},
  number = {1},
  pages = {9--15},
  doi = {10.2307/2312726},
}

@inproceedings{conf1,
  author = {Doe, Jane},
  title = {A Conference Paper},
  booktitle = {Proceedings of the Great Conference},
  year = {2020},
  pages = {1--10},
  publisher = {ACM},
  address = {New York},
}

@incollection{chap1,
  author = {Roe, Richard},
  title = {A Chapter},
  booktitle = {The Big Book},
  editor = {Editor, Edith},
  year = {2019},
  publisher = {Springer},
  chapter = {4},
}

@book{knuth68,
  author = {Knuth, Donald E.},
  title = {The Art of Computer Programming},
  year = {1968},
  publisher = {Addison-Wesley},
  edition = {1},
  note = {Volume 1},
}

@misc{web1,
  author = {{World Health Organization}},
  title = {Some Guidelines},
  year = {2021},
  howpublished = {online},
  url = {https://who.int/x},
}
"""


class TestToCsl:
    def test_article(self):
        ref = parse_bib(_BIB)[0]
        item = to_csl(ref)
        assert item["id"] == "gs62"
        assert item["type"] == "article-journal"
        assert item["container-title"] == "The American Mathematical Monthly"
        assert item["issued"] == {"date-parts": [[1962, 1]]}
        assert item["author"][0] == {"family": "Gale", "given": "David"}
        assert item["page"] == "9--15"
        assert item["DOI"] == "10.2307/2312726"

    def test_inproceedings(self):
        item = to_csl(parse_bib(_BIB)[1])
        assert item["type"] == "paper-conference"
        assert item["container-title"] == "Proceedings of the Great Conference"
        assert item["publisher"] == "ACM"
        assert item["publisher-place"] == "New York"

    def test_incollection_editor(self):
        item = to_csl(parse_bib(_BIB)[2])
        assert item["type"] == "chapter"
        assert item["editor"] == [{"family": "Editor", "given": "Edith"}]
        assert item["chapter-number"] == "4"

    def test_unmapped_fields_ride_in_custom(self):
        item = to_csl(parse_bib(_BIB)[4])
        assert item["custom"] == {"howpublished": "online"}
        assert item["author"] == [{"literal": "World Health Organization"}]

    def test_key_override(self):
        assert to_csl(parse_bib(_BIB)[0], key="other")["id"] == "other"

    def test_online_record(self):
        rec = OnlineRecord(
            source="openalex",
            title="A Paper",
            authors=[Name(family="Doe", given="Jane")],
            year=2020,
            journal="Nature",
            doi="10.1/x",
            abstract="An abstract.",
            type="article-journal",
            publisher="Springer",
            ids={"openalex": "W123", "doi": "10.1/x"},
        )
        item = to_csl(rec, key="doe2020")
        assert item["id"] == "doe2020"
        assert item["abstract"] == "An abstract."
        assert item["custom"]["source"] == "openalex"
        assert item["custom"]["openalex"] == "W123"


class TestRoundTrip:
    def test_reference_survives_csl(self):
        for ref in parse_bib(_BIB):
            back = from_csl(to_csl(ref))
            assert back.key == ref.key
            assert back.title == ref.title
            assert back.authors == ref.authors
            assert back.year == ref.year
            assert back.journal == ref.journal
            assert back.volume == ref.volume
            assert back.number == ref.number
            assert back.pages == ref.pages
            assert back.doi == ref.doi
            assert back.url == ref.url

    def test_bib_field_set_preserved(self):
        refs = parse_bib(_BIB)
        regenerated = to_bib([to_csl(r) for r in refs])
        new_refs = parse_bib(regenerated)
        assert len(new_refs) == len(refs)
        for old, new in zip(refs, new_refs):
            assert old.key == new.key
            assert old.title == new.title
            assert old.authors == new.authors
            assert old.year == new.year
            assert old.journal == new.journal
            assert old.volume == new.volume
            assert old.pages is None or old.pages == new.pages
            assert set(old.extra) == set(new.extra), old.key

    def test_no_silent_drop(self):
        text = "@article{odd, title={T}, author={A, B}, year={2020}, weirdfield={kept}}"
        item = to_csl(parse_bib(text)[0])
        assert item["custom"]["weirdfield"] == "kept"
        assert "weirdfield = {kept}" in to_bib([item])


class TestFromCsl:
    def test_minimal(self):
        ref = from_csl({"id": "x", "type": "book", "title": "T"})
        assert ref == Reference(key="x", title="T", authors=[], type="book")

    def test_publisher_alias_by_type(self):
        thesis = from_csl(
            {"id": "t", "type": "thesis", "title": "T", "publisher": "MIT"}
        )
        assert thesis.extra["school"] == "MIT"
        report = from_csl(
            {"id": "r", "type": "report", "title": "T", "publisher": "NBER"}
        )
        assert report.extra["institution"] == "NBER"

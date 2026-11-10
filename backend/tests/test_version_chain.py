"""REQ-113: drafts with notes after the version number and in several formats are one version chain."""
from pathlib import Path

from app import progress
from app.project_add import next_version
from app.project_meta import detect_role, parse_version, version_family

STEMS = ["OrgSci_Short_Proposal_ALITA_v1_DLStoryIdeas", "OrgSci_Short_Proposal_ALITA_v2_MLDL_combined",
         "OrgSci_Short_Proposal_ALITA_v3"] + [f"OrgSci_Short_Proposal_ALITA_v{n}" for n in range(4, 13)] + [
         "OrgSci_Short_Proposal_ALITA_v13_DL", "OrgSci_Short_Proposal_ALITA_v14_LDK",
         "OrgSci_Short_Proposal_ALITA_v28_DL_Zusammenfassen von Einleitung u. Technischer Erklärung_ mache 9Uhr weiter",
         "OrgSci_Short_Proposal_ALITA_v41_LDK_only last chapter added_not includet"]
FILES = [f"{s}.docx" for s in STEMS] + ["OrgSci_Short_Proposal_ALITA_v33_merged.docx.odt",
                                        "OrgSci_Short_Proposal_ALITA_v42.docx", "OrgSci_Short_Proposal_ALITA_v42.pdf"]


def test_notes_after_the_number_keep_the_series():
    for s in STEMS:
        assert parse_version(s)[0] == "orgsci_short_proposal_alita", s
    assert parse_version("OrgSci_Short_Proposal_ALITA_v41_LDK_only last chapter added_not includet")[2] == 41
    assert parse_version("OrgSci_Short_Proposal_ALITA_v33_merged.docx") == ("orgsci_short_proposal_alita", "33", 33)
    assert parse_version("Technical Appendix_v3.12.0")[2] is None           # a software version is no draft number
    assert parse_version("Artikel_v27a") == ("artikel", "27a", 27)
    assert version_family("odt") == version_family("pdf") == version_family("docx")


def test_proposals_are_manuscripts_and_templates_are_not():
    assert detect_role("OrgSci_Short_Proposal_ALITA_v13_DL.docx", "docx", []).value == "manuscript"
    assert detect_role("OrgSci_Short_Proposal_ALITA_v33_merged.docx.odt", "odt", []).value == "manuscript"
    assert detect_role("OrgSci_Short_Proposal_Vorlage.docx", "docx", []).value == "other"


def _doc(name: str, role: str = "notes") -> dict:
    ft = Path(name).suffix.lstrip(".")
    return {"doc_id": name, "filename": name, "filetype": ft, "role": role, "date": "2026-01-01",
            "project": {"version_group": "old.docx", "version": None, "version_num": None}}


def test_one_chain_across_formats_and_old_records():
    """Old records (role 'notes', no version number stored) still give one chain v1 … v42."""
    docs = [_doc(f) for f in FILES] + [_doc("OrgSci_Short_Proposal_Vorlage.docx", "other"), _doc("Daten.xlsx", "data")]
    spine, group = progress.pick_spine(docs)
    nums = [progress._series(d)[1] for d in spine]
    assert group == "orgsci_short_proposal_alita"
    assert nums == sorted(nums) and nums[0] == 1 and nums[-1] == 42
    assert 33 in nums and 41 in nums
    assert [d["filetype"] for d in spine if progress._series(d)[1] == 42] == ["docx"]   # v42.pdf is the same version


def test_manuscripts_without_a_chain_still_fall_back_to_dates():
    docs = [_doc("Artikel.docx", "manuscript"), _doc("Notizen.docx", "notes")]
    spine, group = progress.pick_spine(docs)
    assert [d["doc_id"] for d in spine] == ["Artikel.docx"] and group is None


def test_next_version_after_a_draft_with_initials(tmp_path):
    (tmp_path / "OrgSci_Short_Proposal_ALITA_v41_LDK.docx").write_bytes(b"x")
    (tmp_path / "OrgSci_Short_Proposal_ALITA_v42.pdf").write_bytes(b"x")
    assert next_version(tmp_path, "OrgSci_Short_Proposal_ALITA_v41_LDK.docx", ".docx") == "OrgSci_Short_Proposal_ALITA_v43.docx"

"""Tests for render_scan.summarize/page/render.

The renderer is the only thing standing between a scan and a page the user
sends to someone else, so the cases that matter are the ones with a blast
radius: the schema gate that stops a comparison record rendering as a scan,
the coherence gate that stops an unmeasured run printing as a confident zero,
and the local/public allowlist that keeps this person's skill names and paths
off the shared page. Every allowlist test is written in both directions: a
guard that cannot fail is not a guard.
"""
import json
import os
import re
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from render_scan import ORDER, PUBLIC_SCHEMA, SCHEMA, page, render, summarize

OUTPUT_NAMES = {"public-scan.html", "local-scan.html", "public-scan-summary.json"}

# Names that exist only on the scanned machine. Each one is planted in a
# different part of the payload so a leak points at the field that leaked.
PRIVATE_NAMES = ["secret-skill-name", "shadowed-client-tool", "vendor-internal-helper",
                 "dormant-private-skill", "unlisted-code-skill", "private-pipeline-notes",
                 "artifact-design"]
PRIVATE_PATH = "/Users/private-person/workspace/secret-project"


def finding(code, skill):
    return {"code": code, "skill": skill, "title": "%s: %s" % (code, skill),
            "detail": "Detail mentioning %s and %s" % (skill, PRIVATE_PATH),
            "evidence": {"attempts": 1, "confirmed_loads": 0, "failed": 1}}


@pytest.fixture
def scan():
    return {
        "schema_version": SCHEMA,
        "created_at": "2026-09-18T08:00:00Z",
        "project": PRIVATE_PATH,
        "host": "auto",
        "evaluation_performed": False,
        "change_status": "not_applied",
        "totals": {"measured": True, "installed": 191, "reached": 13, "dormant": 178,
                   "loaded_outside_inventory": 2, "dormant_percent": 93,
                   "load_attempts": 41, "confirmed_loads": 39, "failed_loads": 2},
        "most_used": [{"skill": "artifact-design", "loads": 12},
                      {"skill": "private-pipeline-notes", "loads": 1}],
        "findings": [finding("load_failed", "secret-skill-name"),
                     finding("shadowed", "shadowed-client-tool"),
                     finding("inventory_gap", "vendor-internal-helper"),
                     finding("dormant", "dormant-private-skill")],
        "coverage": {"sessions_analyzed": 40, "turns_analyzed": 3406, "window_days": 30},
        "scan_limits": {"complete": True, "reasons": [], "warnings": []},
        "privacy": "Nothing left this machine.",
    }


@pytest.fixture
def out(tmp_path):
    return tmp_path / "report"


def rendered(raw, out):
    s = render(raw, out)
    return s, (out / "public-scan.html").read_text(), (out / "local-scan.html").read_text(), \
        json.loads((out / "public-scan-summary.json").read_text())


# --- schema gate ---------------------------------------------------------

def test_comparison_schema_is_rejected(scan):
    """The bug this renderer exists for, inverted: the comparison record and the
    scan record are different shapes, and rendering one as the other prints
    numbers that mean something else."""
    scan["schema_version"] = "brain-surgery/0.4"
    with pytest.raises(ValueError, match="schema_version"):
        summarize(scan)


@pytest.mark.parametrize("version", [
    "brain-surgery/0.3", "brain-surgery/0.4", "brain-surgery-scan/0.2",
    PUBLIC_SCHEMA, "", None, "brain-surgery-scan/0.1 ", "BRAIN-SURGERY-SCAN/0.1",
])
def test_only_the_scan_schema_is_accepted(scan, version):
    scan["schema_version"] = version
    with pytest.raises(ValueError):
        summarize(scan)


def test_missing_schema_version_is_rejected(scan):
    del scan["schema_version"]
    with pytest.raises(ValueError):
        summarize(scan)


def test_the_real_schema_is_accepted(scan):
    assert summarize(scan)["schema_version"] == PUBLIC_SCHEMA


def test_render_refuses_the_wrong_schema_before_writing_anything(scan, out):
    """A rejected payload must not leave a half-written report behind."""
    scan["schema_version"] = "brain-surgery/0.4"
    with pytest.raises(ValueError):
        render(scan, out)
    assert not out.exists() or list(out.iterdir()) == []


# --- measured / coherence gates ------------------------------------------

@pytest.mark.parametrize("mutate", [
    lambda t: t.update(measured=False),
    lambda t: t.pop("measured"),
])
def test_unmeasured_carries_no_dormancy_number(scan, out, mutate):
    """Unmeasured is not zero and it is not a refusal either.

    With no sessions read, every skill trivially looks dormant, so a dormancy
    headline here would be invented out of nothing. The page drops the headline.
    It does not drop the report: a name collision is on disk whether or not a
    transcript was read, and the machine with no history is exactly the one that
    needs to see it.
    """
    mutate(scan["totals"])
    s, public, local, summary = rendered(scan, out)
    assert s["measured"] is False
    assert s["dormant"] is None and s["dormant_percent"] is None
    assert summary["dormant_percent"] is None
    for text in (public, local):
        assert "Nothing was measured." in text
        assert "of installed capability was never loaded" not in text
        assert "% dormant" not in text
    # The transcript-independent finding still reaches the reader.
    assert "Skills competing for the same trigger" in public


def test_reached_above_installed_raises(scan):
    scan["totals"].update(installed=13, reached=191)
    with pytest.raises(ValueError, match="incoherent"):
        summarize(scan)


@pytest.mark.parametrize("installed,reached", [(-1, 0), (191, -13), (-5, -5)])
def test_negative_totals_raise(scan, installed, reached):
    scan["totals"].update(installed=installed, reached=reached)
    with pytest.raises(ValueError, match="incoherent"):
        summarize(scan)


def test_reached_equal_to_installed_is_coherent(scan):
    scan["totals"].update(installed=191, reached=191, dormant=0, dormant_percent=0)
    assert summarize(scan)["reached"] == 191


# --- the allowlist, public direction -------------------------------------

def test_public_html_carries_no_skill_names(scan, out):
    _, public, _, _ = rendered(scan, out)
    for name in PRIVATE_NAMES:
        assert name not in public


def test_public_summary_json_carries_no_skill_names(scan, out):
    _, _, _, summary = rendered(scan, out)
    blob = json.dumps(summary)
    for name in PRIVATE_NAMES:
        assert name not in blob


@pytest.mark.parametrize("project", [PRIVATE_PATH, "/home/fede/clients/acme-secret"])
def test_public_files_carry_no_filesystem_paths(scan, out, project):
    scan["project"] = project
    scan["findings"] = [finding("load_failed", "secret-skill-name")]
    scan["findings"][0]["detail"] = "Failed while reading %s/skills/x" % project
    _, public, _, summary = rendered(scan, out)
    for blob in (public, json.dumps(summary)):
        assert "/Users/" not in blob
        assert "/home/" not in blob
        assert project not in blob


def test_public_html_has_no_local_data_block(scan, out):
    _, public, _, _ = rendered(scan, out)
    assert 'id="local-data"' not in public
    assert 'id="summary-data"' in public


def test_public_embedded_payload_is_the_summary_not_the_scan(scan, out):
    _, public, _, summary = rendered(scan, out)
    block = re.search(r'<script id="summary-data"[^>]*>(.*?)</script>', public, re.S).group(1)
    for name in PRIVATE_NAMES:
        assert name not in block
    assert "most_used" not in block and "created_at" not in block


def test_unknown_private_key_never_reaches_the_public_summary(scan, out):
    """The allowlist proof. A key the summarizer has never heard of must be
    absent from the public side by construction, not by being stripped: a strip
    list only catches the fields somebody remembered to list."""
    scan["operator_email"] = "fede@example.com"
    scan["totals"]["secret_client_count"] = 7
    scan["coverage"]["transcript_dir"] = "/Users/private-person/.claude/projects"
    _, public, local, summary = rendered(scan, out)
    for needle in ("operator_email", "fede@example.com", "secret_client_count",
                   "transcript_dir", "/Users/private-person/.claude"):
        assert needle not in json.dumps(summary)
        assert needle not in public
    # Same payload, local side: the renderer did receive the new key.
    assert "operator_email" in local and "fede@example.com" in local


def test_public_summary_keys_are_exactly_the_allowlist(scan, out):
    _, _, _, summary = rendered(scan, out)
    assert set(summary) == {
        "schema_version", "measured", "installed", "reached", "dormant", "dormant_percent",
        "load_attempts", "confirmed_loads", "failed_loads", "sessions_analyzed",
        "turns_analyzed", "window_days", "finding_counts", "evaluation_performed",
        "change_status", "scan_complete"}


def test_public_summary_holds_counts_and_known_strings_only(scan, out):
    """Anything free-text on the public side is a leak channel, so pin the shape:
    counts, flags, and two strings from a known vocabulary."""
    _, _, _, summary = rendered(scan, out)
    assert summary["schema_version"] == PUBLIC_SCHEMA
    assert summary["change_status"] in {"not_applied", "applied", "reverted"}
    for key, value in summary.items():
        if key in ("schema_version", "change_status", "finding_counts"):
            continue
        assert isinstance(value, (int, bool)), key
    assert all(isinstance(v, int) and k in ORDER for k, v in summary["finding_counts"].items())


def test_finding_counts_are_counts_not_names(scan, out):
    _, _, _, summary = rendered(scan, out)
    assert summary["finding_counts"] == {"load_failed": 1, "shadowed": 1,
                                         "inventory_gap": 1, "dormant": 1}


def test_most_used_names_stay_local(scan, out):
    _, public, local, _ = rendered(scan, out)
    assert "artifact-design" in local and "artifact-design" not in public
    assert "What your agent actually reaches" not in public


def test_finding_with_an_unrecognised_code_does_not_leak_its_name(scan, out):
    """An unknown code is dropped from both the counts and the groups. The
    skill name riding on it must not arrive on the public page by accident."""
    scan["findings"].append(finding("some_future_code", "unlisted-code-skill"))
    scan["findings"].append({"skill": "unlisted-code-skill", "detail": "no code at all"})
    s, public, local, summary = rendered(scan, out)
    assert "some_future_code" not in summary["finding_counts"]
    assert "unlisted-code-skill" not in public
    assert "unlisted-code-skill" in local


# --- the allowlist, local direction (prove the guard can fail) ------------

def test_local_html_shows_every_skill_name(scan, out):
    _, _, local, _ = rendered(scan, out)
    for name in ["secret-skill-name", "shadowed-client-tool", "vendor-internal-helper",
                 "dormant-private-skill", "artifact-design", "private-pipeline-notes"]:
        assert name in local


def test_local_html_has_the_local_data_block_with_the_raw_scan(scan, out):
    _, _, local, _ = rendered(scan, out)
    assert 'id="local-data"' in local and 'id="summary-data"' not in local
    block = re.search(r'<script id="local-data"[^>]*>(.*?)</script>', local, re.S).group(1)
    assert "secret-skill-name" in block and "most_used" in block


def test_local_html_keeps_the_project_path(scan, out):
    _, _, local, _ = rendered(scan, out)
    assert PRIVATE_PATH in local


def test_local_and_public_pages_differ(scan, out):
    _, public, local, _ = rendered(scan, out)
    assert public != local
    assert "Local scan" in local and "Shared scan" in public


# --- grammar and number formatting on edge values ------------------------

def test_zero_installed_does_not_divide_by_zero(scan, out):
    """A machine with nothing installed is a legitimate scan, not a crash."""
    scan["totals"].update(installed=0, reached=0, dormant=0, dormant_percent=0,
                          load_attempts=0, confirmed_loads=0, failed_loads=0)
    scan["findings"] = []
    scan["most_used"] = []
    s, public, local, _ = rendered(scan, out)
    assert s["installed"] == 0
    # The property is the absent division, not the wording. The strip below the
    # headline now carries the counts; the headline carries the verdict.
    assert 'style="width:0%"' in public
    assert "0 of 0 skills reached" in public and "0 of 0 skills reached" in local


def test_one_affected_skill_reads_as_singular(scan, out):
    scan["findings"] = [finding("load_failed", "secret-skill-name")]
    _, public, _, _ = rendered(scan, out)
    assert "1 skill affected" in public and "1 skills affected" not in public


def test_several_affected_skills_read_as_plural(scan, out):
    scan["findings"] = [finding("load_failed", "a-one"), finding("load_failed", "a-two")]
    _, public, _, _ = rendered(scan, out)
    assert "2 skills affected" in public


def test_single_load_reads_as_singular_in_the_local_evidence(scan, out):
    _, _, local, _ = rendered(scan, out)
    assert "1 load</small>" in local and "12 loads</small>" in local


def test_large_counts_are_grouped_and_do_not_crash(scan, out):
    scan["totals"].update(installed=100000, reached=99999, dormant=1, dormant_percent=1,
                          load_attempts=1234567, confirmed_loads=1234000, failed_loads=567)
    scan["coverage"].update(sessions_analyzed=9876, turns_analyzed=1234567)
    s, public, _, _ = rendered(scan, out)
    assert "1,234,567 turns" in public
    assert s["reached"] == 99999


def test_a_single_installed_skill_renders(scan, out):
    scan["totals"].update(installed=1, reached=1, dormant=0, dormant_percent=0)
    scan["coverage"].update(sessions_analyzed=1, turns_analyzed=1, window_days=1)
    s, public, local, _ = rendered(scan, out)
    assert s["installed"] == 1
    assert 'style="width:100%"' in public
    assert "1 of 1 skills reached" in public and "1 of 1 skills reached" in local


def test_singular_counts_read_as_singular_in_the_headline(scan, out):
    scan["totals"].update(installed=1, reached=1, dormant=0, dormant_percent=0)
    scan["coverage"].update(sessions_analyzed=1, turns_analyzed=1, window_days=1)
    _, public, _, _ = rendered(scan, out)
    assert "1 skills installed" not in public
    assert "1 sessions" not in public and "1 turns" not in public and "1 days" not in public


@pytest.mark.parametrize("local,block_id", [(False, "summary-data"), (True, "local-data")])
def test_embedded_data_block_is_parseable_json(scan, out, local, block_id):
    _, public, local_html, _ = rendered(scan, out)
    html_text = local_html if local else public
    block = re.search(r'<script id="%s"[^>]*>(.*?)</script>' % block_id, html_text, re.S).group(1)
    json.loads(block)


def test_every_finding_code_renders_its_group(scan, out):
    _, public, local, _ = rendered(scan, out)
    for heading in ("Skills that failed when your agent reached for them",
                    "Skills competing for the same trigger",
                    "Loaded from somewhere this scan did not look",
                    "Installed and never reached"):
        assert heading in public and heading in local


def test_no_findings_renders_a_page_anyway(scan, out):
    scan["findings"] = []
    s, public, local, summary = rendered(scan, out)
    assert summary["finding_counts"] == {}
    assert "skills installed" in public and "skills installed" in local


def test_absent_optional_blocks_do_not_crash(scan, out):
    """A scan can arrive with no coverage, findings, or most_used at all."""
    for key in ("coverage", "findings", "most_used", "scan_limits"):
        scan.pop(key)
    s, public, _, summary = rendered(scan, out)
    assert (s["sessions_analyzed"], s["turns_analyzed"], s["window_days"]) == (0, 0, 0)
    assert summary["scan_complete"] is False
    assert "0 sessions" in public


def test_html_escapes_a_skill_name_that_looks_like_markup(scan, out):
    """A skill name is user data on the local page; it must not become markup."""
    scan["findings"] = [finding("load_failed", "<script>alert(1)</script>")]
    scan["most_used"] = [{"skill": "<img src=x onerror=1>", "loads": 2}]
    _, _, local, _ = rendered(scan, out)
    assert "<script>alert(1)</script>" not in local
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in local
    assert "<img src=x onerror=1>" not in local


def test_long_detail_is_not_cut_through_an_entity(scan, out):
    scan["findings"] = [finding("load_failed", "secret-skill-name")]
    scan["findings"][0]["detail"] = "A" * 157 + " & more"
    _, _, local, _ = rendered(scan, out)
    assert not re.search(r"&[a-z]{1,6}(?![a-z]*;)", local.split("</ul>")[0])


# --- output contract -----------------------------------------------------

def test_the_three_output_files_and_nothing_else(scan, out):
    render(scan, out)
    assert {p.name for p in out.iterdir()} == OUTPUT_NAMES


def test_output_files_are_owner_only(scan, out):
    """The report holds the names of this person's private work; group and other
    must not be able to read it off a shared machine."""
    render(scan, out)
    for name in OUTPUT_NAMES:
        assert os.stat(out / name).st_mode & 0o777 == 0o600, name


def test_render_creates_a_missing_output_directory(scan, tmp_path):
    out = tmp_path / "nested" / "deeper"
    render(scan, out)
    assert (out / "public-scan.html").exists()


def test_render_returns_the_public_summary(scan, out):
    s = render(scan, out)
    assert s == json.loads((out / "public-scan-summary.json").read_text())


def test_rerendering_overwrites_in_place(scan, out):
    render(scan, out)
    scan["totals"]["reached"] = 14
    s = render(scan, out)
    assert s["reached"] == 14
    assert {p.name for p in out.iterdir()} == OUTPUT_NAMES
    assert "14 of 191 skills reached" in (out / "public-scan.html").read_text()


def test_pages_are_well_formed_enough_to_open(scan, out):
    _, public, local, _ = rendered(scan, out)
    for html_text in (public, local):
        assert html_text.startswith("<!doctype html>")
        assert html_text.count("<html") == 1 and html_text.rstrip().endswith("</html>")
        assert 'name="robots" content="noindex,nofollow"' in html_text


def test_page_is_a_pure_function_of_its_input(scan):
    """summarize and page must not mutate the scan they were handed; render
    calls page twice on the same record."""
    before = json.dumps(scan, sort_keys=True)
    s = summarize(scan)
    page(s, scan, local=True)
    page(s, scan, local=False)
    assert json.dumps(scan, sort_keys=True) == before


def test_fix_text_never_reaches_the_public_report(scan, out):
    """A fix names absolute paths on the user's machine and sometimes a shell
    command containing them. The public payload is an allowlist, so this should
    hold by construction, and it is worth pinning because the fix field was added
    after that allowlist was written."""
    scan["findings"] = [{
        "code": "duplicated", "skill": "secret-skill-name", "confidence": "observation",
        "title": "secret-skill-name is stored twice, identically",
        "detail": "Both copies are byte-identical.",
        "fix": "Replace one with a symlink:\nln -sfn /Users/private/.agents/skills/x /Users/private/.claude/skills/x",
        "evidence": {"paths": ["/Users/private/a/SKILL.md", "/Users/private/b/SKILL.md"],
                     "identical": True, "digests": ["abc"]},
    }]
    _, public, local, _ = rendered(scan, out)
    assert "ln -sfn" in local and "/Users/private" in local
    assert "ln -sfn" not in public
    assert "/Users/private" not in public
    assert "secret-skill-name" not in public


def test_a_finding_without_a_fix_renders_without_an_empty_box(scan, out):
    """Dormancy deliberately carries no fix: suggesting people delete skills they
    have not needed yet is advice this scan has no evidence for."""
    scan["findings"] = [{
        "code": "dormant", "skill": None, "confidence": "observation",
        "title": "3 of 4 installed skills were never used",
        "detail": "Present and not loaded.", "fix": None,
        "evidence": {"installed": 4, "reached": 1, "dormant": 3, "names": ["a", "b", "c"]},
    }]
    _, _, local, _ = rendered(scan, out)
    assert 'class="fix"' not in local


def test_a_clean_page_does_not_contradict_its_own_error_count(scan, out):
    """The hero said "no failed loads" while the strip beneath it counted four.
    Both were true, since those failures had been fixed, and saying only one of
    them made the page read as a mistake."""
    scan["findings"] = []
    scan["resolved_since"] = ["gmail-operations", "agentwallet-credential-ops"]
    scan["totals"]["failed_loads"] = 4
    _, _, local, _ = rendered(scan, out)
    assert "no failed loads" not in local
    assert "failed in earlier sessions and load now" in local
    assert "since resolved" in local


def test_a_genuinely_clean_page_still_says_so_plainly(scan, out):
    scan["findings"] = []
    scan["resolved_since"] = []
    scan["totals"]["failed_loads"] = 0
    _, _, local, _ = rendered(scan, out)
    assert "No name collisions, no failed loads" in local


def test_excluded_evaluation_sessions_are_declared_on_the_page(scan, out):
    """60 sessions were excluded on a real machine and the report said nothing.
    Evidence removed on purpose still has to be declared, or a reader comparing
    the session count against what they know they ran concludes the scan missed
    them."""
    scan["coverage"]["harness_sessions_excluded"] = 60
    _, public, local, _ = rendered(scan, out)
    assert "60 sessions excluded as evaluation runs" in local
    assert "60 sessions excluded as evaluation runs" in public


def test_nothing_excluded_means_no_sentence_about_it(scan, out):
    scan["coverage"]["harness_sessions_excluded"] = 0
    _, _, local, _ = rendered(scan, out)
    assert "excluded as evaluation runs" not in local


def test_a_project_scoped_scan_says_its_window_was_narrow(scan, out):
    """205 of 205 dormant from two sessions, with nothing saying the window was
    deliberately one project wide. The dormancy false alarm in a different hat."""
    scan["coverage"]["scope"] = "project"
    _, public, local, _ = rendered(scan, out)
    assert "Scope was one project" in local
    assert "--scope user" in local
    assert "Scope was one project" in public


def test_a_user_scoped_scan_says_nothing_about_scope(scan, out):
    scan["coverage"]["scope"] = "user"
    _, _, local, _ = rendered(scan, out)
    assert "Scope was one project" not in local

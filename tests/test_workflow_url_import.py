"""Importing a workflow from a link -- the user story the dialog had no front door for.

The import dialog was local-file only, so "I found this workflow on Civitai" was unsupported; the
only paste-a-link affordances in the app were for models. And the Civitai API key the user saved in
Settings never reached the import path, so a link needing auth failed with a 401 the app already had
the answer to.

This fetches attacker-influenceable input, so the tests pin the security properties as hard as the
happy path:

  * https only, from an explicit host allowlist -- a fetcher that follows any pasted URL is an SSRF
    primitive aimed at the user's LAN;
  * a redirect off the allowlist is refused, and the Civitai token is stripped when a redirect
    leaves civitai.com;
  * "it downloaded" is not "it is a workflow" -- a JSON error page parses perfectly well.
"""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import workflow_url_import as wui  # noqa: E402

UI_GRAPH = {"nodes": [{"id": 1, "type": "KSampler", "widgets_values": []}], "links": []}
API_PROMPT = {"1": {"class_type": "KSampler", "inputs": {}}}


class _Resp:
    def __init__(self, body: bytes, content_type="application/json", length=None):
        self._buf = io.BytesIO(body)
        self.headers = {"Content-Type": content_type,
                        "Content-Length": str(length if length is not None else len(body))}

    def read(self, n=-1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def served(monkeypatch):
    """Serves one body for any allowlisted URL, recording the request that was made."""
    state = {"body": json.dumps(UI_GRAPH).encode(), "content_type": "application/json",
             "requests": [], "error": None, "length": None}

    class Opener:
        def open(self, request, timeout=None):
            state["requests"].append(request)
            if state["error"] is not None:
                raise state["error"]
            return _Resp(state["body"], state["content_type"], state["length"])

    monkeypatch.setattr(wui.urllib.request, "build_opener", lambda *a, **k: Opener())
    return state


# --- URL handling ---------------------------------------------------------------------------------

def test_a_github_page_link_is_rewritten_to_its_raw_file():
    """The blob URL is what people copy; it serves HTML, not the workflow."""
    assert wui.normalize_workflow_url("https://github.com/o/r/blob/main/wf/flux.json") == \
        "https://raw.githubusercontent.com/o/r/main/wf/flux.json"


def test_other_urls_are_left_alone():
    url = "https://civitai.com/api/download/attachments/12345"
    assert wui.normalize_workflow_url(url) == url


def test_http_is_refused(served):
    with pytest.raises(wui.WorkflowFetchError, match="https"):
        wui.fetch_workflow_from_url("http://civitai.com/x.json")


def test_an_unlisted_host_is_refused(served):
    """A fetcher that follows any pasted URL can be pointed at the user's own network."""
    with pytest.raises(wui.WorkflowFetchError, match="does not download"):
        wui.fetch_workflow_from_url("https://169.254.169.254/latest/meta-data")
    assert served["requests"] == [], "nothing was requested"


# --- fetching -------------------------------------------------------------------------------------

def test_a_json_workflow_is_imported(served):
    result = wui.fetch_workflow_from_url("https://raw.githubusercontent.com/o/r/main/flux.json")
    assert result.payload == UI_GRAPH
    assert result.via == "json"
    assert result.display_name == "flux"


def test_an_api_prompt_is_also_a_workflow(served):
    served["body"] = json.dumps(API_PROMPT).encode()
    assert wui.fetch_workflow_from_url("https://raw.githubusercontent.com/o/r/main/p.json").payload == API_PROMPT


def test_json_that_is_not_a_workflow_is_rejected(served):
    """An error page or a model index parses fine and would import as a broken profile."""
    served["body"] = json.dumps({"error": "not found", "status": 404}).encode()
    with pytest.raises(wui.WorkflowFetchError, match="not a ComfyUI workflow"):
        wui.fetch_workflow_from_url("https://civitai.com/api/x.json")


def test_html_is_rejected_with_actionable_advice(served):
    """Still the right answer for a link that is genuinely a page and nothing else.

    This used to be asserted against a CIVITAI MODEL PAGE, which pinned the designed non-feature:
    those pages are now resolved through the Civitai API to their downloadable file, so the case is
    exercised here on a host we cannot resolve instead. See
    test_a_versioned_page_resolves_to_its_file for the behaviour that replaced it.
    """
    served["body"] = b"<!doctype html><html>...</html>"
    served["content_type"] = "text/html"
    with pytest.raises(wui.WorkflowFetchError, match="attachment"):
        wui.fetch_workflow_from_url("https://huggingface.co/some/page")


def test_an_oversized_body_is_refused_before_it_is_read(served):
    served["length"] = wui.MAX_WORKFLOW_BYTES + 1
    with pytest.raises(wui.WorkflowFetchError, match="too large"):
        wui.fetch_workflow_from_url("https://civitai.com/x.json")


def test_a_lying_content_length_is_still_capped_while_streaming(served):
    served["body"] = b"x" * (wui.MAX_WORKFLOW_BYTES + 10)
    served["length"] = 10
    with pytest.raises(wui.WorkflowFetchError, match="too large"):
        wui.fetch_workflow_from_url("https://civitai.com/x.json")


# --- credentials ----------------------------------------------------------------------------------

def test_the_civitai_key_is_sent_to_civitai(served):
    wui.fetch_workflow_from_url("https://civitai.com/api/x.json", civitai_api_key="secret")
    assert served["requests"][0].get_header("Authorization") == "Bearer secret"


def test_the_civitai_key_is_not_sent_anywhere_else(served):
    wui.fetch_workflow_from_url("https://raw.githubusercontent.com/o/r/main/x.json", civitai_api_key="secret")
    assert served["requests"][0].get_header("Authorization") is None


def test_a_401_says_what_to_do_about_it(served):
    served["error"] = urllib.error.HTTPError("https://civitai.com/x.json", 401, "Unauthorized", {}, None)
    with pytest.raises(wui.WorkflowFetchError, match="Civitai API key in Settings"):
        wui.fetch_workflow_from_url("https://civitai.com/x.json")


# --- redirects ------------------------------------------------------------------------------------

def _redirect_to(url):
    handler = wui._AllowlistRedirectHandler()
    request = wui.urllib.request.Request("https://civitai.com/a.json",
                                         headers={"Authorization": "Bearer secret"})
    return handler.redirect_request(request, io.BytesIO(b""), 302, "Found", {}, url)


def test_a_redirect_off_the_allowlist_is_refused():
    """Without this the allowlist only checks the first hop, which checks nothing."""
    with pytest.raises(wui.WorkflowFetchError, match="redirected"):
        _redirect_to("https://evil.invalid/payload.json")


def test_a_redirect_to_another_allowed_host_drops_the_civitai_token():
    new_request = _redirect_to("https://huggingface.co/x/resolve/main/wf.json")
    assert new_request is not None
    assert new_request.get_header("Authorization") is None


def test_a_redirect_within_civitai_keeps_the_token():
    new_request = _redirect_to("https://image.civitai.com/xyz/file.json")
    assert new_request.get_header("Authorization") == "Bearer secret"


# --- shape check ----------------------------------------------------------------------------------

def test_looks_like_workflow_accepts_both_graph_forms():
    assert wui.looks_like_workflow(UI_GRAPH)
    assert wui.looks_like_workflow(API_PROMPT)


def test_looks_like_workflow_rejects_other_json():
    assert not wui.looks_like_workflow({})
    assert not wui.looks_like_workflow({"error": "nope"})
    assert not wui.looks_like_workflow([1, 2, 3])


# --- host policy must not disagree between the two import lanes ---------------------------


def test_civitai_red_is_accepted_like_civitai_com():
    r"""The same link was accepted by the MODEL importer and refused by the WORKFLOW importer:
    model_sources matches `civitai\.(?:com|red)` and this module listed only .com. Every link in
    the batch that prompted this fix was civitai.red."""
    for host in ("civitai.red", "www.civitai.red", "image.civitai.red"):
        assert host in wui.ALLOWED_HOSTS
        assert host in wui.CIVITAI_HOSTS


def test_the_two_lanes_agree_on_civitai_hosts():
    """Pins the agreement rather than the list, so adding a host to one lane and not the other
    fails here instead of in a user's import."""
    import re

    import model_sources

    for pattern in (model_sources.CIVITAI_DOWNLOAD_RE, model_sources.CIVITAI_MODEL_PAGE_RE):
        for host in ("civitai.com", "civitai.red"):
            probe = f"https://{host}/models/12345"
            if pattern is model_sources.CIVITAI_DOWNLOAD_RE:
                probe = f"https://{host}/api/download/models/12345"
            assert pattern.match(probe), f"model lane rejects {host}"
            assert host in wui.ALLOWED_HOSTS, f"workflow lane rejects {host}"


def test_the_civitai_delivery_host_is_reachable_so_the_advice_is_not_a_dead_end():
    """The download endpoint 302s to a delivery host. The redirect was refused, so the error
    message's own recommendation -- copy the attachment link -- also dead-ended.

    Matched by registrable domain, not a hostname list: a first attempt hardcoded two guessed
    Cloudflare R2 names and BOTH were wrong. The live redirect goes to b2.civitai.com."""
    assert wui.host_allowed("b2.civitai.com")
    assert wui.host_allowed("some-future-cdn.civitai.red")


def test_the_domain_rule_cannot_be_spoofed_by_a_lookalike_host():
    """endswith on a bare name would let civitai.com.evil.com through; the leading dot is what
    makes it a subdomain test rather than a substring test."""
    for host in ("evil.com", "notcivitai.com", "civitai.com.evil.com", "xcivitai.red", ""):
        assert not wui.host_allowed(host)


# --- a Civitai model page is HTML; it has to become a file URL first -----------------------


def _model_payload(versions):
    return {"name": "M", "type": "Workflows", "modelVersions": versions}


def _version(vid, name, base="Krea 2", size=120.0):
    return {"id": vid, "name": f"v{vid}", "baseModel": base,
            "files": [{"name": name, "sizeKB": size, "primary": True,
                       "downloadUrl": f"https://civitai.com/api/download/models/{vid}?fileId=9"}]}


def test_a_model_page_url_is_recognised_with_and_without_a_version():
    assert wui.civitai_model_page_ids(
        "https://civitai.red/models/2799333/krea2-two-image-edit-v12?modelVersionId=3155617"
    ) == ("2799333", "3155617")
    assert wui.civitai_model_page_ids(
        "https://civitai.red/models/2790822/easy-krea-2-workflow"
    ) == ("2790822", "")
    assert wui.civitai_model_page_ids("https://example.test/models/1") is None
    assert wui.civitai_model_page_ids("https://civitai.com/api/download/models/5") is None


def test_a_versioned_page_resolves_to_its_file(monkeypatch):
    monkeypatch.setattr(wui, "_civitai_api_get_json", lambda *a, **k: None, raising=False)
    import model_sources

    monkeypatch.setattr(
        model_sources, "_civitai_api_get_json",
        lambda url, **k: {"files": [{"name": "wf.json", "sizeKB": 12.0,
                                     "downloadUrl": "https://civitai.com/api/download/models/7?fileId=1"}]},
    )
    resolved, note = wui.resolve_civitai_workflow_url(
        "https://civitai.red/models/99/x?modelVersionId=7")
    assert resolved.endswith("fileId=1")
    assert "version 7" in note


def test_a_version_less_page_with_several_versions_refuses_rather_than_guessing(monkeypatch):
    """One Civitai model id can hold versions built on different architectures, so taking the
    first is a silent wrong-file import -- the defect already fixed on the model lane."""
    import model_sources

    monkeypatch.setattr(
        model_sources, "_civitai_api_get_json",
        lambda url, **k: _model_payload([_version(1, "a.json"), _version(2, "b.json", base="Flux.1 D")]),
    )
    with pytest.raises(wui.WorkflowFetchError, match="names no version"):
        wui.resolve_civitai_workflow_url("https://civitai.red/models/99/x")


def test_a_version_less_page_with_one_version_resolves(monkeypatch):
    import model_sources

    monkeypatch.setattr(model_sources, "_civitai_api_get_json",
                        lambda url, **k: _model_payload([_version(4, "only.json")]))
    resolved, note = wui.resolve_civitai_workflow_url("https://civitai.red/models/99/x")
    assert "models/4" in resolved
    assert "only version" in note


def test_a_workflow_json_is_preferred_over_weights_in_the_same_version():
    """A checkpoint page that also attaches its workflow ships both files. Pasting it into the
    WORKFLOW importer must fetch the .json, not several gigabytes of weights."""
    chosen = wui._pick_workflow_file([
        {"name": "model.safetensors", "sizeKB": 23_000_000.0, "downloadUrl": "https://x/1"},
        {"name": "workflow.json", "sizeKB": 40.0, "downloadUrl": "https://x/2"},
    ])
    assert chosen["name"] == "workflow.json"


def test_a_non_civitai_url_passes_through_untouched():
    resolved, note = wui.resolve_civitai_workflow_url("https://raw.githubusercontent.com/a/b/c.json")
    assert resolved == "https://raw.githubusercontent.com/a/b/c.json"
    assert note == ""

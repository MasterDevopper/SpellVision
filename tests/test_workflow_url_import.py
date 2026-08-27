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
    served["body"] = b"<!doctype html><html>...</html>"
    served["content_type"] = "text/html"
    with pytest.raises(wui.WorkflowFetchError, match="attachment"):
        wui.fetch_workflow_from_url("https://civitai.com/models/12345")


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

"""The structural post-condition on a converted API prompt: **no input may reference a node id
that is not in the prompt.**

Why this is its own module rather than a few lines inside the converter: the specific reason a node
went missing keeps changing, and the guarantee must not. The known cause (2026-09-17) was an
unresolvable node class -- the converter omitted the node, kept every reference to it, and reported
nothing; ComfyUI then rejected the prompt with ``KeyError: '3024'`` from inside ``validate_inputs``,
which names an id the user has never seen. Ten of the imported library's UI graphs converted to such
a prompt. The next cause will be something else. This check does not care which.

The link shape is not guessed: it mirrors ``comfy_execution.graph_utils.is_link`` in the live core
exactly -- a list of length 2 whose first element is a ``str`` and whose second is an ``int`` or a
``float``. Anything the server would read as a link is a link here, which is the only definition
that makes the post-condition mean what it claims. A widget value that happens to take that shape is
therefore reported too, and rightly: ComfyUI would misread it the same way.
"""
from __future__ import annotations

from typing import Any, NamedTuple


class DanglingLink(NamedTuple):
    """An input on ``node_id`` that points at ``missing_id``, which the prompt does not contain."""

    node_id: str
    input_name: str
    missing_id: str

    def describe(self) -> str:
        return f"{self.node_id}.{self.input_name} -> {self.missing_id}"


def is_link(value: Any) -> bool:
    """Exactly ComfyUI's own link test (``comfy_execution/graph_utils.py::is_link``)."""
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], (int, float))
        and not isinstance(value[1], bool)
    )


def find_dangling_links(prompt: Any) -> list[DanglingLink]:
    """Every input in ``prompt`` whose link target is absent from ``prompt``.

    Empty list for a well-formed prompt (and for anything that is not a prompt-shaped dict -- this
    is a post-condition, not a schema validator).
    """
    if not isinstance(prompt, dict):
        return []
    present = {str(key) for key in prompt}
    out: list[DanglingLink] = []
    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for name, value in inputs.items():
            if is_link(value) and value[0] not in present:
                out.append(DanglingLink(str(node_id), str(name), str(value[0])))
    out.sort()
    return out


def describe_dangling_links(dangling: list[DanglingLink], *, limit: int = 8) -> str:
    """A one-line summary naming the referring inputs, not just the missing ids.

    "node 3024 is missing" sends the reader nowhere; "2685.sigmas -> 3024" says which input broke.
    """
    if not dangling:
        return ""
    missing = sorted({link.missing_id for link in dangling})
    shown = ", ".join(link.describe() for link in dangling[:limit])
    more = f" (+{len(dangling) - limit} more)" if len(dangling) > limit else ""
    return (
        f"{len(dangling)} input(s) reference {len(missing)} node id(s) the prompt does not "
        f"contain: {shown}{more}"
    )


class PromptVerdict(NamedTuple):
    """Whether a freshly built prompt may be handed out, and why not."""

    errors: list[str]
    dangling: list[DanglingLink]
    missing_packs: list[dict[str, Any]]


def prompt_verdict(
    prompt: dict[str, Any],
    workflow: Any,
    unknown_classes: Any,
    unknown_nodes: dict[str, str],
) -> PromptVerdict:
    """The converter's post-condition: may this prompt be handed out, and if not, what to say.

    ``unknown_nodes`` maps the node ids omitted for want of a schema to their class, so a dangling
    reference can be explained by the pack it belongs to instead of by a bare id.

    TWO independent reasons to refuse, kept separate because they send the reader to different
    places:

    * an unresolvable class -- "install this pack", the user's problem to fix. This is unconditional
      even when nothing references the omitted node, which matches what the strict submit path has
      always done; softening it to "only if referenced" would let a graph through the compile path
      that the launch path refuses, and one half of the codebase disagreeing with the other about
      whether a workflow is runnable is how this defect got its foothold.
    * a dangling link with no missing class behind it -- a converter bug, ours to fix.
    """
    dangling = find_dangling_links(prompt)
    unknown = sorted({str(c) for c in (unknown_classes or [])})
    errors: list[str] = []
    packs: list[dict[str, Any]] = []
    if unknown:
        from comfy_missing_packs import missing_class_message, missing_pack_entries

        packs = missing_pack_entries(workflow, unknown)
        errors.append(missing_class_message(workflow, unknown))
    unexplained = [link for link in dangling if link.missing_id not in unknown_nodes]
    if unexplained:
        errors.append(
            "Internal error: the converted prompt is not self-consistent. "
            + describe_dangling_links(unexplained)
            + ". This prompt would be rejected by ComfyUI with an opaque KeyError, so it is "
            "refused here instead."
        )
    return PromptVerdict(errors, dangling, packs)


def assert_no_dangling_links(prompt: Any, *, context: str = "converted prompt") -> None:
    """Raise ``ValueError`` if ``prompt`` carries a dangling link.

    Used as the converter's own post-condition. A failure here is a converter bug by construction:
    every legitimate reason to omit a node (muted, bypassed, pure-UI) also drops the links into it.
    """
    dangling = find_dangling_links(prompt)
    if dangling:
        raise ValueError(
            f"Internal error: the {context} is not self-consistent. "
            + describe_dangling_links(dangling)
            + ". This prompt would be rejected by ComfyUI with an opaque KeyError, so it is "
            "refused here instead."
        )

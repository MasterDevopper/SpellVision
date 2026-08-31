# Character Studio → Jarvis character-pack contract

**Status:** Pack authoring implemented in Character Studio; downstream SpellBound concept-to-style cook remains incomplete.  
**Authority:** owner pack guidance supplied 2026-08-17; frozen-body and Wrought laws remain engine-owned.  
**Code:** `qt_ui/studios/CharacterStudioPage.*`, `python/character_pack.py`, `tests/test_character_pack.py`

## Product boundary

SpellVision prepares the evidence Jarvis needs. It does **not** claim that a reference pack is a cooked character.

- Body topology remains the frozen SpellBound `female.glb` (14,517 vertices / 53 joints).
- Body form comes from owner-reviewed sliders; a tight-clothed T/A-pose may be a weak hint.
- Clothing is authored and reconstructed as separate wearable pieces, never fused into the body.
- Grok nude plates are neither required nor requested. SpellVision must not implement an undress path.
- Fashion poses establish identity, mood, and palette; they are not body measurements or sewing patterns.
- `concept_to_style_complete` remains `false` until VL, per-piece reconstruction, Wrought transfer, bind/cook, Stage proof, and owner review are real.

## Character Studio pack surface

The **Multi-view** stage contains a Jarvis character-pack authoring panel with these slots:

```text
face_01_front.*        required
face_01_3q.*           optional
clothes_01_front.*     required; T- or A-pose on white
clothes_01_side.*      side or back required
clothes_01_back.*      side or back required
clothes_01_3q.*        optional
notes.txt              generated from named pieces + palette + pose
pack_manifest.json     generated readiness/provenance truth
```

The minimum accepted pack is:

1. face front;
2. clothes front;
3. clothes side **or** back;
4. named piece list;
5. named palette.

The optimal seven-file pack has all six image slots plus `notes.txt`.

## Builder behavior

`python/character_pack.py`:

1. validates required slots and image-file types;
2. hashes every selected still with SHA-256;
3. refuses byte-identical views so renamed duplicates cannot satisfy angle requirements;
4. writes canonical slot names while preserving supported image extensions;
5. writes `notes.txt` and `pack_manifest.json`;
6. stages output before replacing an existing pack;
7. records the downstream incomplete state rather than advertising a cook.

Character projects persist source selections in:

```text
runtime/characters/<project>/project.json
```

Built packs live at:

```text
runtime/characters/<project>/jarvis_pack/
```

The optional external handoff remains `$SB_SPELLVISION_PACKS`; copying or indexing packs into that root is a later integration step, not required for local authoring.

## Manifest truth

Every manifest records:

- contract `spellbound.jarvis-character-pack.v1`;
- canonical image names, source paths, and SHA-256 hashes;
- piece and palette lists;
- frozen-body source;
- separate-clothing policy;
- `concept_to_style_complete: false`;
- exact downstream work still required.

## Downstream blockers

A pack may be called **ready evidence**, never a finished character, until SpellBound proves:

1. `qwen3-vl:32b` inspected the image-bearing request;
2. each still was classified as `figure | garment | mixed | face | mood | reject`;
3. body and clothing lanes were split without undressing or inferring hidden anatomy;
4. every named clothing piece became a separate mesh;
5. Wrought material law was applied;
6. bind/skin/cook/hash validation passed;
7. Stage proof views exist;
8. the owner accepted eyes, face, body sliders, and clothing.

Until then the result is a **pack plateau**, not completion.

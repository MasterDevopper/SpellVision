"""Project clothes-plate silhouette pieces onto frozen female.glb 14517.

NOT a wearable cook. Builds garment-shaped cards from front product-sheet
piece masks, textures them from the plate, shrink-wraps to the body.

Usage:
  blender --background --python scripts/garment_shrinkwrap_blender.py -- \\
      --body <female.glb> --plates <garments/slug> --dest <wrap_scaffold.glb> \\
      --front-mask <silhouette_front.png> --front-plate <front.png>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Projected shrink-wrap from clothes silhouette")
    parser.add_argument("--body", required=True)
    parser.add_argument("--plates", required=True)
    parser.add_argument("--dest", default="")
    parser.add_argument("--verts", type=int, default=14517)
    parser.add_argument("--offset", type=float, default=0.006)
    parser.add_argument("--front-mask", default="")
    parser.add_argument("--front-plate", default="")
    return parser.parse_args(argv)


def _write_report(plates: Path, name: str, report: dict) -> None:
    (plates / name).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _piece_masks(plates: Path, front_mask: Path) -> list[Path]:
    pieces = sorted(plates.glob("silhouette_front_piece_*.png"))
    if pieces:
        return pieces
    if front_mask.is_file():
        return [front_mask]
    return []


def _apply_plate_material(bpy, obj, plate_path: Path) -> None:
    if not plate_path.is_file():
        return
    mat = bpy.data.materials.new(f"GarmentPlate_{obj.name}")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        return
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(plate_path))
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if "Alpha" in bsdf.inputs and "Alpha" in tex.outputs:
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def _build_cage_from_mask(bpy, mask_path: Path, body_obj, offset: float, name: str) -> object:
    import bmesh

    image = bpy.data.images.load(str(mask_path))
    w, h = int(image.size[0]), int(image.size[1])
    pixels = list(image.pixels)
    grid_w, grid_h = 48, 96
    occupied = []
    for gy in range(grid_h):
        row = []
        for gx in range(grid_w):
            px = min(w - 1, int((gx + 0.5) * w / grid_w))
            py = min(h - 1, int((1.0 - (gy + 0.5) / grid_h) * h))
            idx = (py * w + px) * 4
            row.append(pixels[idx] > 0.5)
        occupied.append(row)

    bbox = body_obj.bound_box
    xs = [v[0] for v in bbox]
    ys = [v[1] for v in bbox]
    zs = [v[2] for v in bbox]
    min_x, max_x = min(xs), max(xs)
    min_y = min(ys)
    min_z, max_z = min(zs), max(zs)
    depth = min_y - 0.08
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = [[None] * (grid_w + 1) for _ in range(grid_h + 1)]
    for gy in range(grid_h + 1):
        v = gy / grid_h
        for gx in range(grid_w + 1):
            u = gx / grid_w
            x = min_x + u * (max_x - min_x)
            z = min_z + v * (max_z - min_z)
            verts[gy][gx] = bm.verts.new((x, depth, z))
    bm.verts.ensure_lookup_table()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    faces = 0
    for gy in range(grid_h):
        for gx in range(grid_w):
            if not occupied[gy][gx]:
                continue
            face = bm.faces.new(
                (
                    verts[gy][gx],
                    verts[gy][gx + 1],
                    verts[gy + 1][gx + 1],
                    verts[gy + 1][gx],
                )
            )
            u0, u1 = gx / grid_w, (gx + 1) / grid_w
            v0, v1 = gy / grid_h, (gy + 1) / grid_h
            face.loops[0][uv_layer].uv = (u0, v0)
            face.loops[1][uv_layer].uv = (u1, v0)
            face.loops[2][uv_layer].uv = (u1, v1)
            face.loops[3][uv_layer].uv = (u0, v1)
            faces += 1
    if faces < 8:
        bm.free()
        raise RuntimeError(f"silhouette cage too sparse: {faces} faces")
    bm.to_mesh(mesh)
    bm.free()
    cage = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(cage)
    bpy.ops.object.select_all(action="DESELECT")
    cage.select_set(True)
    bpy.context.view_layer.objects.active = cage
    sw = cage.modifiers.new("SW", "SHRINKWRAP")
    sw.target = body_obj
    sw.wrap_method = "PROJECT"
    sw.use_negative_direction = True
    sw.use_positive_direction = True
    sw.offset = float(offset)
    bpy.ops.object.modifier_apply(modifier="SW")
    solid = cage.modifiers.new("SO", "SOLIDIFY")
    solid.thickness = 0.004
    solid.offset = 1.0
    bpy.ops.object.modifier_apply(modifier="SO")
    cage["sv_source"] = "clothes_plate_silhouette"
    return cage


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    body = Path(args.body)
    plates = Path(args.plates)
    dest = Path(args.dest) if args.dest else plates / "wrap_scaffold.glb"
    front_mask = Path(args.front_mask) if args.front_mask else plates / "silhouette_front.png"
    front_plate = Path(args.front_plate) if args.front_plate else plates / "front.png"
    report = {
        "method": "projected_shrinkwrap_from_plate",
        "body": str(body),
        "plates": str(plates),
        "dest": str(dest),
        "front_mask": str(front_mask) if front_mask.is_file() else "",
        "front_plate": str(front_plate) if front_plate.is_file() else "",
        "body_verts_required": int(args.verts),
        "offset_m": float(args.offset),
        "cook_complete": False,
        "blocked_on": ["stills_to_mesh", "garment_cook"],
        "blender": False,
        "note": "Separable silhouette pieces from the front plate, textured and shrink-wrapped to 14517. Not a cooked wearable.",
    }
    try:
        import bpy  # type: ignore
    except Exception:
        _write_report(plates, "wrap_blender_skipped.json", report)
        print("blender not available — wrote wrap_blender_skipped.json")
        return 0

    report["blender"] = True
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if not body.is_file():
        report["error"] = f"body missing: {body}"
        _write_report(plates, "wrap_blender_skipped.json", report)
        return 2

    bpy.ops.import_scene.gltf(filepath=str(body))
    mesh_obj = next((obj for obj in bpy.context.scene.objects if obj.type == "MESH"), None)
    verts = len(mesh_obj.data.vertices) if mesh_obj is not None else 0
    report["body_verts_seen"] = verts
    if verts != int(args.verts):
        report["error"] = f"body verts {verts} != required {args.verts}"
        _write_report(plates, "wrap_blender_skipped.json", report)
        return 3

    cages = []
    piece_paths = _piece_masks(plates, front_mask)
    report["piece_masks"] = [str(p) for p in piece_paths]
    for i, mask_path in enumerate(piece_paths):
        try:
            cage = _build_cage_from_mask(
                bpy, mask_path, mesh_obj, float(args.offset), f"GarmentPiece_{i:02d}"
            )
            _apply_plate_material(bpy, cage, front_plate)
            cages.append(cage)
        except Exception as exc:
            report.setdefault("piece_errors", []).append(f"{mask_path.name}: {exc}")

    used_plate = bool(cages)
    if not cages:
        bpy.ops.object.select_all(action="DESELECT")
        mesh_obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_obj
        bpy.ops.object.duplicate()
        cage = bpy.context.active_object
        cage.name = "GarmentCage_BodyShellFallback"
        sw = cage.modifiers.new("SW", "SHRINKWRAP")
        sw.target = mesh_obj
        sw.wrap_method = "NEAREST_SURFACEPOINT"
        sw.offset = float(args.offset)
        bpy.ops.object.modifier_apply(modifier="SW")
        cages = [cage]

    mesh_obj.hide_set(True)
    mesh_obj.hide_render = True
    dest.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for cage in cages:
        cage.select_set(True)
    bpy.context.view_layer.objects.active = cages[0]
    bpy.ops.export_scene.gltf(
        filepath=str(dest),
        export_format="GLB",
        use_selection=True,
        export_materials="EXPORT",
        export_texcoords=True,
        export_image_format="AUTO",
    )
    report["exported_shell"] = True
    report["used_plate_silhouette"] = used_plate
    report["piece_count"] = len(cages)
    report["shell_verts"] = sum(len(c.data.vertices) for c in cages)
    report["textured"] = front_plate.is_file() and used_plate
    _write_report(plates, "wrap_blender_report.json", report)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raw = sys.argv[1:]
    if "--" in raw:
        raw = raw[raw.index("--") + 1 :]
    raise SystemExit(main(raw))

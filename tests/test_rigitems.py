"""Offline tests (no WolvenKit or game files needed). Run: python -m unittest"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from rigitems import build, cr2w, icons, inputs, templates as tpl


class Naming(unittest.TestCase):
    def test_default_title(self):
        cases = {
            "06_RigDeform_Angel_Bigger_Thighs_Legs_and_Butt_With_Framework": "RigDeform Angel Bigger Thighs Legs and Butt",
            "Aphrodite_Rig_With_UVF": "Aphrodite Rig",
            "Aphrodite_Rig_(Vanilla_Angel_Breasts)_With_UVF": "Aphrodite Rig (Vanilla Angel Breasts)",
            "06_rig_mengleten_noBooba": "rig mengleten noBooba",
            "Body - Unique V Framework": "Body",
            "06_": "06_",
        }
        for stem, title in cases.items():
            self.assertEqual(inputs.default_title(stem), title, stem)

    def test_default_key(self):
        self.assertEqual(inputs.default_key("Aphrodite Rig (Vanilla Angel Breasts)"), "aphrodite_rig_vanilla_angel_breasts")
        self.assertEqual(inputs.default_key("!!!"), "rig")
        long = inputs.default_key("a b " * 40)
        self.assertLessEqual(len(long), 48)
        self.assertRegex(long, inputs.KEY_RE)

    def _rig(self, archive, origin=None):
        return inputs.Rig(Path(archive), Path(origin or archive), False)

    def test_dedupe_and_overrides(self):
        rigs = [self._rig("a/Body.archive"), self._rig("b/Body.archive"), self._rig("c/Other.archive", "c/mod.zip")]
        overrides = {"mod.zip": {"key": "custom", "title": "Custom Title"}}
        inputs.name_rigs(rigs, overrides)
        self.assertEqual([r.key for r in rigs], ["body", "body_2", "custom"])
        self.assertEqual(rigs[2].title, "Custom Title")

    def test_load_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "rigs.json"
            p.write_text(json.dumps({"Aphrodite_Rig_With_UVF.archive": {"key": "aph"}}))
            self.assertEqual(inputs.load_overrides(p), {"aphrodite_rig_with_uvf.archive": {"key": "aph"}})
            p.write_text(json.dumps({"x": {"key": "Bad Key"}}))
            self.assertRaises(inputs.InputError, inputs.load_overrides, p)
            p.write_text("[]")
            self.assertRaises(inputs.InputError, inputs.load_overrides, p)
        self.assertEqual(inputs.load_overrides(None), {})

    def test_unpack_rejects_traversal(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "evil.zip"
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("../escape.txt", "x")
            self.assertRaises(inputs.InputError, inputs.unpack, z, Path(d) / "out")
            self.assertFalse((Path(d) / "escape.txt").exists())


class Swap(unittest.TestCase):
    def test_swap_deep(self):
        depth = sys.getrecursionlimit() * 2
        root = node = {}
        for _ in range(depth):
            node["child"] = [{"s": "old"}]
            node = node["child"][0]
        cr2w.swap(root, {"old": "new"})
        self.assertEqual(set(cr2w.iter_strings(root)), {"new"})

    def test_repoint_graph(self):
        mine = build.paths("k")["rig"]
        graph = {"a": [build.VANILLA_RIG, {"b": inputs.FRAMEWORK_RIG}], "c": "keep.anims"}
        build.repoint_graph(graph, mine)
        self.assertEqual(graph, {"a": [mine, {"b": mine}], "c": "keep.anims"})

    def test_repoint_graph_rejects_stray_rig(self):
        graph = {"a": build.VANILLA_RIG, "b": r"base\characters\other.rig"}
        self.assertRaises(build.BuildError, build.repoint_graph, graph, build.paths("k")["rig"])

    def test_renumber_handles(self):
        doc = {"x": {"HandleId": "5", "Data": {}}, "y": [{"HandleRefId": "5"}, {"HandleId": "80", "Data": {}}],
               "z": {"HandleRefId": "80"}}
        cr2w.renumber_handles(doc)
        self.assertEqual((doc["x"]["HandleId"], doc["y"][0]["HandleRefId"], doc["y"][1]["HandleId"],
                          doc["z"]["HandleRefId"]), ("0", "0", "1", "1"))


class Toolchain(unittest.TestCase):
    def test_missing_runtime_messages(self):
        from rigitems import toolchain
        self.assertTrue(toolchain.missing_runtime("You must install .NET to run this application.\n\nApp: x"))
        self.assertTrue(toolchain.missing_runtime(
            "You must install or update .NET to run this application.\n"
            "Framework: 'Microsoft.NETCore.App', version '10.0.0' (x64)"))
        self.assertFalse(toolchain.missing_runtime("[ 0: Error ] - Invalid output directory."))

    def test_runtime_env_uses_private_dotnet(self):
        from unittest import mock
        from rigitems import toolchain
        with tempfile.TemporaryDirectory() as d, mock.patch.object(toolchain, "data_dir", return_value=Path(d)):
            self.assertNotEqual(toolchain.runtime_env().get("DOTNET_ROOT"), str(Path(d) / "dotnet"))
            (Path(d) / "dotnet/shared/Microsoft.NETCore.App").mkdir(parents=True)
            self.assertEqual(toolchain.runtime_env()["DOTNET_ROOT"], str(Path(d) / "dotnet"))

    def test_window_opens_for_no_args_or_dropped_files(self):
        from unittest import mock
        from rigitems import cli
        with tempfile.TemporaryDirectory() as d, mock.patch.object(cli, "_gui") as gui:
            dropped = Path(d) / "Rig.zip"
            dropped.write_bytes(b"")
            cli.main([])
            cli.main([str(dropped)])
            self.assertEqual([c.args[0] for c in gui.call_args_list], [[], [str(dropped)]])
            with self.assertRaises(SystemExit):   # unknown word that isn't a file: normal CLI error
                cli.main(["bulid"])
            self.assertEqual(gui.call_count, 2)


class Tweak(unittest.TestCase):
    def test_toes_appended_to_base_slot(self):
        # A single placementSlots entry makes Equipment-EX guess the outfit slot (Inner Torso).
        yaml = build.TWEAK.format(name="rigitem_k", key="k", mod=build.MOD)
        self.assertIn("placementSlots:\n    - !append OutfitSlots.ToesLeft\n", yaml)


class Icons(unittest.TestCase):
    def test_bc3_round_trip(self):
        big, small, _ = icons.render_atlas({"a": "Alpha", "b": "Beta Rig With A Long Name"})
        for img in (big, small):
            data = icons.encode_bc3(img)
            self.assertEqual(len(data), img.width * img.height)
            back = icons.decode_bc3(data, img.width, img.height)
            # Colour error is weighted by alpha (what shows on screen). BC3 fits one colour line per
            # 4x4 block, so the odd three-colour block is off; judge the bulk, not the worst pixel.
            s, o = img.convert("RGBA").tobytes(), back.tobytes()
            errs = sorted(max(abs(s[i + c] - o[i + c]) * (s[i + 3] if c < 3 else 255) / 255 for c in range(4))
                          for i in range(0, len(s), 4))
            self.assertLess(sum(errs) / len(errs), 4)
            self.assertLess(errs[int(len(errs) * 0.99)], 32)

    def test_flat_block_exact(self):
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
        self.assertEqual(icons.decode_bc3(icons.encode_bc3(img), 4, 4).getpixel((1, 1)), (255, 0, 0, 255))

    def test_xbm_rows_bottom_up(self):
        img = Image.new("RGBA", (4, 8), (0, 0, 255, 255))
        img.paste((255, 0, 0, 255), (0, 0, 4, 4))   # red on top
        stored = icons.decode_bc3(icons.xbm_bytes(img), 4, 8)
        self.assertEqual(stored.getpixel((0, 7)), (255, 0, 0, 255))
        self.assertEqual(stored.getpixel((0, 0)), (0, 0, 255, 255))

    def test_atlas_layout_and_uvs(self):
        labels = {f"k{i}": f"Rig {i}" for i in range(icons.COLS + 1)}
        big, small, parts = icons.render_atlas(labels)
        self.assertEqual(big.size, (icons.COLS * icons.CELL, 2 * icons.CELL))
        self.assertEqual(small.size, (big.width // 2, big.height // 2))
        self.assertEqual(parts[f"k{icons.COLS}"], (0, icons.CELL, icons.CELL, 2 * icons.CELL))
        atlas = cr2w.inkatlas("t.xbm", "t1080.xbm", big.size, parts)["Data"]["RootChunk"]
        mappers = atlas["slots"]["Elements"][0]["parts"]
        self.assertEqual([m["partName"]["$value"] for m in mappers], list(labels))
        uv = mappers[-1]["clippingRectInUVCoords"]
        self.assertEqual((uv["Left"], uv["Top"], uv["Right"], uv["Bottom"]), (0, 0.5, 1 / icons.COLS, 1))

    def test_xbm_sizes(self):
        x = cr2w.xbm_bc3(8, 4, bytes(32))["Data"]["RootChunk"]
        hdr = x["renderTextureResource"]["renderResourceBlobPC"]["Data"]["header"]
        self.assertEqual(hdr["mipMapInfo"][0]["layout"]["rowPitch"], 32)
        self.assertEqual(hdr["textureInfo"]["textureDataSize"], 32)


@unittest.skipUnless((tpl.TEMPLATE_DIR / "mesh.ent.json").is_file(), "templates not generated")
class Templates(unittest.TestCase):
    def setUp(self):
        self.t = tpl.load_all()

    def handles(self, doc):
        defs, refs, stack = [], [], [doc]
        while stack:
            n = stack.pop()
            if isinstance(n, dict):
                defs += [n["HandleId"]] if "HandleId" in n else []
                refs += [n["HandleRefId"]] if "HandleRefId" in n else []
            if isinstance(n, (dict, list)):
                stack.extend(n.values() if isinstance(n, dict) else n)
        return defs, refs

    def test_handles_unique_and_resolved(self):
        for kind, doc in self.t.items():
            defs, refs = self.handles(doc)
            self.assertEqual(len(defs), len(set(defs)), kind)
            self.assertLessEqual(set(refs), set(defs), kind)
            self.assertEqual(sorted(map(int, defs)), list(range(len(defs))), kind)

    def test_placeholders(self):
        expect = {"root": {tpl.NAME, tpl.APP}, "app": {tpl.NAME, tpl.MESH}, "mesh": {tpl.RIG, tpl.GRAPH}, "factory": set()}
        every = {tpl.NAME, tpl.APP, tpl.MESH, tpl.RIG, tpl.GRAPH}
        for kind, doc in self.t.items():
            self.assertEqual(set(cr2w.iter_strings(doc)) & every, expect[kind], kind)

    def test_mesh_binding(self):
        rc = self.t["mesh"]["Data"]["RootChunk"]
        for comps in (rc["components"], rc["compiledData"]["Data"]["Chunks"]):
            names = [c["name"]["$value"] for c in comps if "name" in c]
            self.assertIn("Component", names)
            anim = next(c for c in comps if c["$type"] == "entAnimatedComponent")
            self.assertEqual(anim["name"]["$value"], "deformations")
        self.assertEqual(rc["components"][1]["controlBinding"], {"HandleRefId": "0"})
        binding = next(c for c in rc["compiledData"]["Data"]["Chunks"] if c["$type"] == "entAnimatedComponent")["controlBinding"]
        self.assertEqual(binding["Data"]["bindName"]["$value"], "root")

    def test_no_local_paths(self):
        for kind, doc in self.t.items():
            self.assertEqual(doc["Header"]["ArchiveFileName"], "", kind)


if __name__ == "__main__":
    unittest.main()

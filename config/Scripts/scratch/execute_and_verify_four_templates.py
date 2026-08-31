import pyfbsdk
import os
import json
import traceback

src_path = r"C:\Users\zacha\Desktop\testfolder\Box_Cross.fbx"
out_dir = r"C:\Users\zacha\Desktop\testfolder"
report_path = r"W:\Repo\MotionBlender\config\Scripts\scratch\export_verification_report.json"
txt_report_path = r"W:\Repo\MotionBlender\config\Scripts\scratch\export_verification_report.txt"

app = pyfbsdk.FBApplication()
system = pyfbsdk.FBSystem()

def count_user_models(scene):
    # User models are root model children excluding internal guides
    models = []
    def recurse(model):
        for child in model.Children:
            name = str(child.Name)
            if not name.startswith("Grid Axis Guide") and child.ClassName() not in ("FBCamera", "FBCameraSwitcher"):
                models.append(name)
            recurse(child)
    recurse(scene.RootModel)
    return models

def count_animation_keys(scene):
    total_keys = 0
    for comp in scene.Components:
        if isinstance(comp, pyfbsdk.FBModel):
            node = getattr(comp, "AnimationNode", None)
            if node:
                for sub in node.Nodes:
                    for ch in sub.Nodes:
                        fc = getattr(ch, "FCurve", None)
                        if fc:
                            total_keys += len(fc.Keys)
    return total_keys

def inspect_file(filepath):
    app.FileNew()
    opts = pyfbsdk.FBFbxOptions(True) # True = Open
    opts.ShowFileDialog = False
    opts.ShowOptionsDialog = False
    opened = app.FileOpen(filepath, False, opts)
    system.Scene.Evaluate()
    
    models = count_user_models(system.Scene)
    poses = [str(p.Name) for p in system.Scene.Poses]
    takes = [str(t.Name) for t in system.Scene.Takes]
    keys = count_animation_keys(system.Scene)
    characters = [str(c.Name) for c in system.Scene.Characters]
    
    return {
        "file": filepath,
        "exists": os.path.isfile(filepath),
        "size_bytes": os.path.getsize(filepath) if os.path.isfile(filepath) else 0,
        "models_count": len(models),
        "models": models[:10], # sample
        "poses_count": len(poses),
        "poses": poses,
        "takes_count": len(takes),
        "takes": takes,
        "animation_keys_count": keys,
        "characters_count": len(characters),
        "characters": characters,
    }

results = {
    "source_file": src_path,
    "exports": {},
    "verifications": {},
    "success": False
}

logs = []

try:
    # 1. Open source file
    logs.append("Opening source file: %s" % src_path)
    src_info = inspect_file(src_path)
    results["source_info"] = src_info
    logs.append("Source contents: User Models=%d, Poses=%d, Takes=%d, Keys=%d" % (
        src_info["models_count"], src_info["poses_count"], src_info["takes_count"], src_info["animation_keys_count"]
    ))

    # Define targets
    targets = {
        "export model only": {
            "path": os.path.join(out_dir, "test_export_model_only.fbx"),
            "setup": lambda opts: (
                opts.SetAll(pyfbsdk.FBElementAction.kFBElementActionDiscard, False),
                setattr(opts, "Models", pyfbsdk.FBElementAction.kFBElementActionSave),
                setattr(opts, "ModelsAnimation", False),
                setattr(opts, "Poses", pyfbsdk.FBElementAction.kFBElementActionDiscard),
                setattr(opts, "Characters", pyfbsdk.FBElementAction.kFBElementActionDiscard),
                setattr(opts, "CharactersAnimation", False),
                setattr(opts, "GlobalLightingSettings", False),
                setattr(opts, "TransportSettings", False),
                setattr(opts, "CurrentCameraSettings", False),
                setattr(opts, "CameraSwitcherSettings", False),
                [opts.SetTakeSelect(i, False) for i in range(opts.GetTakeCount())]
            ),
            "asserts": lambda info: (
                info["models_count"] > 0 and
                info["poses_count"] == 0 and
                info["animation_keys_count"] == 0
            )
        },
        "export poses only": {
            "path": os.path.join(out_dir, "test_export_poses_only.fbx"),
            "setup": lambda opts: (
                opts.SetAll(pyfbsdk.FBElementAction.kFBElementActionDiscard, False),
                setattr(opts, "Poses", pyfbsdk.FBElementAction.kFBElementActionSave),
                setattr(opts, "Models", pyfbsdk.FBElementAction.kFBElementActionDiscard),
                setattr(opts, "ModelsAnimation", False),
                setattr(opts, "Characters", pyfbsdk.FBElementAction.kFBElementActionDiscard),
                setattr(opts, "CharactersAnimation", False),
                setattr(opts, "GlobalLightingSettings", False),
                setattr(opts, "TransportSettings", False),
                setattr(opts, "CurrentCameraSettings", False),
                setattr(opts, "CameraSwitcherSettings", False),
                [opts.SetTakeSelect(i, False) for i in range(opts.GetTakeCount())]
            ),
            "asserts": lambda info: (
                info["poses_count"] > 0 and
                info["models_count"] == 0 and
                info["animation_keys_count"] == 0
            )
        },
        "export motion only": {
            "path": os.path.join(out_dir, "test_export_motion_only.fbx"),
            "setup": lambda opts: (
                opts.SetAll(pyfbsdk.FBElementAction.kFBElementActionDiscard, False),
                setattr(opts, "Models", pyfbsdk.FBElementAction.kFBElementActionSave),
                setattr(opts, "ModelsAnimation", True),
                setattr(opts, "Characters", pyfbsdk.FBElementAction.kFBElementActionSave),
                setattr(opts, "CharactersAnimation", True),
                setattr(opts, "Poses", pyfbsdk.FBElementAction.kFBElementActionDiscard),
                setattr(opts, "Materials", pyfbsdk.FBElementAction.kFBElementActionDiscard),
                setattr(opts, "Textures", pyfbsdk.FBElementAction.kFBElementActionDiscard),
                setattr(opts, "Shaders", pyfbsdk.FBElementAction.kFBElementActionDiscard),
                setattr(opts, "GlobalLightingSettings", False),
                setattr(opts, "TransportSettings", False),
                setattr(opts, "CurrentCameraSettings", False),
                setattr(opts, "CameraSwitcherSettings", False),
                [opts.SetTakeSelect(i, True) for i in range(opts.GetTakeCount())]
            ),
            "asserts": lambda info: (
                info["animation_keys_count"] > 0 and
                info["takes_count"] > 0 and
                info["poses_count"] == 0
            )
        },
        "export model + motion": {
            "path": os.path.join(out_dir, "test_export_model_motion.fbx"),
            "setup": lambda opts: (
                opts.SetAll(pyfbsdk.FBElementAction.kFBElementActionDiscard, False),
                setattr(opts, "Models", pyfbsdk.FBElementAction.kFBElementActionSave),
                setattr(opts, "ModelsAnimation", True),
                setattr(opts, "Characters", pyfbsdk.FBElementAction.kFBElementActionSave),
                setattr(opts, "CharactersAnimation", True),
                setattr(opts, "Poses", pyfbsdk.FBElementAction.kFBElementActionDiscard),
                setattr(opts, "Materials", pyfbsdk.FBElementAction.kFBElementActionSave),
                setattr(opts, "Textures", pyfbsdk.FBElementAction.kFBElementActionSave),
                setattr(opts, "Shaders", pyfbsdk.FBElementAction.kFBElementActionSave),
                setattr(opts, "GlobalLightingSettings", False),
                setattr(opts, "TransportSettings", False),
                setattr(opts, "CurrentCameraSettings", False),
                setattr(opts, "CameraSwitcherSettings", False),
                [opts.SetTakeSelect(i, True) for i in range(opts.GetTakeCount())]
            ),
            "asserts": lambda info: (
                info["models_count"] > 0 and
                info["takes_count"] > 0 and
                info["animation_keys_count"] > 0 and
                info["poses_count"] == 0
            )
        }
    }

    # Execute exports
    for name, cfg in targets.items():
        logs.append("\n=== EXPORTING: %s ===" % name)
        # Re-open source to have clean state
        app.FileNew()
        open_opts = pyfbsdk.FBFbxOptions(True)
        open_opts.ShowFileDialog = False
        open_opts.ShowOptionsDialog = False
        app.FileOpen(src_path, False, open_opts)
        system.Scene.Evaluate()

        # Configure save options
        save_opts = pyfbsdk.FBFbxOptions(False)
        save_opts.ShowFileDialog = False
        save_opts.ShowOptionsDialog = False
        cfg["setup"](save_opts)

        dest_file = cfg["path"]
        if os.path.isfile(dest_file):
            try:
                os.remove(dest_file)
            except OSError:
                pass

        saved = app.FileSave(dest_file, save_opts)
        logs.append("Saved to %s (success: %s)" % (dest_file, saved))
        results["exports"][name] = {
            "path": dest_file,
            "saved": saved,
            "exists": os.path.isfile(dest_file)
        }

    # Verify each exported file
    all_passed = True
    for name, cfg in targets.items():
        logs.append("\n=== VERIFYING: %s ===" % name)
        dest_file = cfg["path"]
        info = inspect_file(dest_file)
        passed = cfg["asserts"](info)
        info["test_passed"] = passed
        results["verifications"][name] = info
        if not passed:
            all_passed = False
            logs.append("FAIL: %s did not meet template criteria!" % name)
        else:
            logs.append("PASS: %s verified successfully!" % name)
        logs.append("  Contents: User Models=%d, Poses=%d, Takes=%d, Keys=%d" % (
            info["models_count"], info["poses_count"], info["takes_count"], info["animation_keys_count"]
        ))

    results["success"] = all_passed
    logs.append("\nOVERALL TEST RESULT: %s" % ("ALL 4 TEMPLATES PASSED!" if all_passed else "SOME TESTS FAILED"))

except Exception:
    err = traceback.format_exc()
    results["error"] = err
    logs.append("ERROR: %s" % err)

with open(report_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

with open(txt_report_path, "w", encoding="utf-8") as f:
    f.write("\n".join(logs) + "\n")

print("Verification complete! Success: %s" % results["success"])

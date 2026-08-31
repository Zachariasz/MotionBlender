import pyfbsdk
import os

app = pyfbsdk.FBApplication()
system = pyfbsdk.FBSystem()

app.FileNew()
opts = pyfbsdk.FBFbxOptions(True)
opts.ShowFileDialog = False
opts.ShowOptionsDialog = False
app.FileOpen(r"C:\Users\zacha\Desktop\testfolder\test_export_poses_only.fbx", False, opts)
system.Scene.Evaluate()

lines = []
lines.append("--- MODELS IN test_export_poses_only.fbx ---")
for comp in system.Scene.Components:
    if isinstance(comp, pyfbsdk.FBModel):
        lines.append("Model: %s | ClassName: %s | Type: %s" % (comp.Name, comp.ClassName(), type(comp).__name__))

lines.append("\n--- POSES IN test_export_poses_only.fbx ---")
for p in system.Scene.Poses:
    lines.append("Pose: %s" % p.Name)

with open(r"W:\Repo\MotionBlender\config\Scripts\scratch\poses_only_details.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

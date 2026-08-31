import pyfbsdk
import os

src_path = r"C:\Users\zacha\Desktop\testfolder\Box_Cross.fbx"
out_lines = []
out_lines.append("Checking Box_Cross.fbx at: " + str(src_path))

app = pyfbsdk.FBApplication()
system = pyfbsdk.FBSystem()

opts = pyfbsdk.FBFbxOptions(True)
opts.ShowFileDialog = False
opts.ShowOptionsDialog = False

app.FileOpen(src_path, False, opts)
system.Scene.Evaluate()

out_lines.append("--- SCENE CONTENTS OF Box_Cross.fbx ---")
out_lines.append("Models count: " + str(len(system.Scene.RootModel.Children)))
for m in system.Scene.RootModel.Children:
    out_lines.append("  Model: " + str(m.Name) + " Class: " + str(m.ClassName()))

out_lines.append("Takes count: " + str(len(system.Scene.Takes)))
for t in system.Scene.Takes:
    out_lines.append("  Take: " + str(t.Name) + " Start: " + str(t.LocalTimeSpan.GetStart().GetFrame()) + " End: " + str(t.LocalTimeSpan.GetStop().GetFrame()))

out_lines.append("Characters count: " + str(len(system.Scene.Characters)))
out_lines.append("Poses count: " + str(len(system.Scene.Poses)))
for p in system.Scene.Poses:
    out_lines.append("  Pose: " + str(p.Name))

out_lines.append("Constraints count: " + str(len(system.Scene.Constraints)))
out_lines.append("Cameras count: " + str(len(system.Scene.Cameras)))

out_path = r"W:\Repo\MotionBlender\config\Scripts\scratch\inspect_out.txt"
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines) + "\n")


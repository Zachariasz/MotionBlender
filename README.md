# MotionBlender
Tools to MotionBuilder that fills workflow gaps. Adds flexibility to transformations, more shortcuts and other stuff known from Blender 3D. Inspired by Blender 3D tools and shortcuts.


- No more gizmo-based workflow. You can move objects freerly with just shortcuts.
- Moving keys at fcurves also supported. You can rotate them to orbit tangents or scale to make them weight based. Also You can snap handlers to aim neighbour keys with one click.
- Updated picker for multi select tools, i.e. you can select multiple effectors and change them to IK with single context menu.

  and many more..
.  
.
.
#### Press "G" to move object around. You don't need to see gizmo for translating anymore. When moving, press "X", "Y", or "Z" to lock movment to single axis in worldspace. Press axis letter twice to change to local movement (i.e. "G" to start moving, then "Y", "Y" to move object at local Y axis).

<img width="800" height="485" alt="transformations_flexibility" src="https://github.com/user-attachments/assets/b09e1725-e5ce-419b-873d-a2d6f63311f4" />

#### New control rig UI, with head, spine segments, and fingers support. Window is scalable so it fits your desire size. Also you can hide top bar, for larger UI. Also you can move buttons to vertical position for more optimized larger UI.

<img width="262" height="518" alt="picker_flexibility" src="https://github.com/user-attachments/assets/c34c1b9f-fe95-4bbe-a0dc-63897efdff99" />

#### You can edit multiple bones (selected) in same time. Select efectors and press RMB on any of those, then context slider menu appears. Just more sliders and observe that affects all effectors. LMB on empty space to deselect, RMB on empty space to select all bones. You can also pin translation/rotation via this menu by pressing pin icons.

<img width="264" height="494" alt="picker_ik_fk" src="https://github.com/user-attachments/assets/b8b8df42-2132-4df7-b0f1-d67eea5bb357" />

#### Move, rotate, scale tangents on fcurves using (G - for move, R - for rotate, S - for scale). You can lock movement by pressing axis letter so if you will press G, and then Y, it will only move at Y axis. Also you can scale with locked Y axis so it will flatten all selected to median point. Hold shift or ctrl when scaling tangents to affect only one side (one tangent).

<img width="422" height="378" alt="fcurves_transforms-ezgif com-video-to-gif-converter" src="https://github.com/user-attachments/assets/170bca0f-1cef-495e-b533-18c449e84021" />

#### Press "V" on fcurves window (cursor must be at fcurves window) to open context menu with tangents presets. You can break/unbreak selected tangent, change selected to weighted/unweighted tangents, align selected tangent to aim left key, align selected tangent to aim right key, break tangents and aim both sides.

<img width="392" height="376" alt="fcurves_vector_menu-ezgif com-video-to-gif-converter" src="https://github.com/user-attachments/assets/046ab23a-86a8-4c17-8126-ce8284c0adc4" />

#### Use "R" to rotate selected object in viewport camera orientation. Press "R" once again when rotating to change rotation type to trackball.

<img width="434" height="344" alt="trackball_rot-ezgif com-video-to-gif-converter" src="https://github.com/user-attachments/assets/a15cbcd3-ec66-477f-9a92-4dc945dcf9e2" />

#### Use "X", "Y", "Z" to lock rotation to worldspace single axis rotation. Press same axis letter twice to change to local rotation (i.e. "R" to start rotating, then "X", "X" to enter local X axis rotation).

<img width="512" height="386" alt="loc_rot_transforms-ezgif com-video-to-gif-converter" src="https://github.com/user-attachments/assets/6701a82c-febc-41fc-88c2-1f84ea9ebe8b" />

#### You can reset your object to 0,0,0 using shortcuts. Press alt+G to reset location, alt+R to reset rotation, alt+S to reset scale.

<img width="456" height="346" alt="reset_loc_rot-ezgif com-video-to-gif-converter" src="https://github.com/user-attachments/assets/509db570-a2bd-44d7-8222-b194340ff871" />

#### Press shift+A to add new objects (all available from asset browser/templates).

<img width="640" height="374" alt="add_menu-ezgif com-video-to-gif-converter" src="https://github.com/user-attachments/assets/d66c0883-4e48-4655-8323-71af17cf9c29" />

#### Remove all keys from IK (press RMB on effector and then RMB on "K" button)

<img width="264" height="444" alt="remove-all-keys-ezgif com-video-to-gif-converter" src="https://github.com/user-attachments/assets/e754a03e-68b9-4362-be9c-d538f13d230b" />





## Disclaimer:

I'm not programmer. All of those was invented by me, but vibe coded using Codex. It may contain bugs and/or absorb more performance then it should... but at the end of a day it make you work faster. Inspired by Blender 3D solutions. Some of solutions totally copied. Some of them upgraded. 





# **INSTALLATION:**

Choose scripts you'd like to use or download whole config folder and merge with:

`C:\Users\%USERPROFILE%\Documents\MB\[VERSION]\config\`

**AND**

copy or create symbolic link of "custom" folder from Scripts and place here:

`C:\Program Files\Autodesk\MotionBuilder [VERSION]\bin\config\Scripts\`

.

Second folder is needed for easier setup in ActionScript. If you rather not use it, you will have to rewrite paths in ../config/Scripts/ActionScript.txt

It was tested on motionbuilder 2025 and 2026.

import json
import os
import time

SAVED_HASH_COL0 = "2efdca60238635e8333a40be2b48ee9808e38817"
SAVED_HASH_COL1 = "74e625f6923bc9283146c8698f10d762a315d7e3"
DISCARD_HASH_COL0 = "66bb42b12dc5adff2799753ca6217e2a6b4460ec"
DISCARD_HASH_COL1 = "2faa5c08080f9f85aac9f66b113f59fd4704f8a8"
NONE_HASH_COL1 = "c5bb1c4dac8012649efbfa6486460ccda00e62be"

SCENE_ROWS_WITH_NONE_COL1 = {0, 2, 7, 10, 11, 12, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27}

def make_scene_spread(save_models=False, save_model_anim=False, save_poses=False, save_characters=False, save_char_anim=False):
    items = []
    for row in range(28):
        # Determine col 0 state
        col0_save = False
        if row == 13 and save_models:
            col0_save = True
        elif row == 17 and save_poses:
            col0_save = True
        elif row == 3 and save_characters:
            col0_save = True

        items.append({
            "row": row,
            "column": 0,
            "state": "save" if col0_save else "discard",
            "value": SAVED_HASH_COL0 if col0_save else DISCARD_HASH_COL0
        })

        # Determine col 1 state
        if row in SCENE_ROWS_WITH_NONE_COL1:
            items.append({
                "row": row,
                "column": 1,
                "state": "none",
                "value": NONE_HASH_COL1
            })
        else:
            col1_save = False
            if row == 13 and save_model_anim:
                col1_save = True
            elif row == 3 and save_char_anim:
                col1_save = True

            items.append({
                "row": row,
                "column": 1,
                "state": "save" if col1_save else "discard",
                "value": SAVED_HASH_COL1 if col1_save else DISCARD_HASH_COL1
            })

    return {
        "key": "SpreadScene",
        "name": "SpreadScene",
        "row_count": 28,
        "ratios": [30.0 / 162.0, 91.0 / 162.0],
        "items": items
    }

def make_settings_spread():
    items = []
    for row in range(5):
        items.append({
            "row": row,
            "column": 0,
            "state": "discard",
            "value": DISCARD_HASH_COL0
        })
    return {
        "key": "SpreadSetting",
        "name": "SpreadSetting",
        "row_count": 5,
        "ratios": [60.0 / 162.0],
        "items": items
    }

def make_takes_spread(save_take=False):
    items = [{
        "row": 0,
        "column": 0,
        "state": "save" if save_take else "discard",
        "value": SAVED_HASH_COL0 if save_take else DISCARD_HASH_COL0
    }]
    return {
        "key": "SpreadTakes",
        "name": "SpreadTakes",
        "row_count": 1,
        "ratios": [20.0 / 174.0],
        "items": items
    }

def create_template(name, save_models=False, save_model_anim=False, save_poses=False, save_characters=False, save_char_anim=False, save_takes=False):
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "captured_at": stamp,
        "schema": 1,
        "version": 1,
        "spreads": [
            make_scene_spread(save_models, save_model_anim, save_poses, save_characters, save_char_anim),
            make_settings_spread(),
            make_takes_spread(save_takes)
        ],
        "views": [],
        "widgets": []
    }

templates = {
    "export model only": create_template("export model only", save_models=True, save_model_anim=False, save_poses=False, save_takes=False),
    "export poses only": create_template("export poses only", save_models=False, save_model_anim=False, save_poses=True, save_takes=False),
    "export motion only": create_template("export motion only", save_models=False, save_model_anim=False, save_poses=False, save_takes=True),
    "export model + motion": create_template("export model + motion", save_models=True, save_model_anim=True, save_poses=False, save_characters=True, save_char_anim=True, save_takes=True),
}

payload = {
    "version": 1,
    "templates": templates
}

target_paths = [
    r"E:\Documents\MB\2026\config\MotionBuilderToolsManager\save_options_templates.json",
    r"W:\Repo\MotionBlender\config\MotionBuilderToolsManager\save_options_templates.json",
    os.path.expanduser(r"~\Documents\MB\2026\config\MotionBuilderToolsManager\save_options_templates.json")
]

for p in target_paths:
    d = os.path.dirname(p)
    if not os.path.isdir(d):
        try:
            os.makedirs(d)
        except OSError:
            pass
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    print("Wrote templates to:", p)

# Maya recipe: a loop that keys a shot

How the eight steps of the `loop` skill map to animation work: a loop that keys a shot in Maya until every beat on the shot sheet has its key and the playblast is complete. It runs on the local lane, on a workstation with a Maya licence.

Untested on this machine: on 2026-11-27 `mayapy` was looked for on PATH and not found. A Maya 2027 install was present outside PATH, and the recipe has not been run against it.

## Step 0: End state

Every beat the shot sheet lists has a key on its control at its frame, and the playblast holds one image for every frame of the shot's range. The shot sheet is a JSON file beside the scene:

```json
{
  "scene": "sh010.ma",
  "beats": [
    {"control": "ctrl_hand_L", "frame": 1012},
    {"control": "ctrl_head", "frame": 1030}
  ],
  "playblast": "playblast/sh010.####.png",
  "frame_range": [1001, 1048]
}
```

`scene` and `playblast` are relative to the shot sheet's folder; `####` stands for the zero-padded frame number.

## Step 1: Sensor

A `mayapy` batch script opens the scene and prints the sensor contract. An item `<control>:<frame>` names a beat with no key on that control at that frame; an item `playblast:<frame>` names a frame of the range whose image is missing. Neither holds a path or a line number, so an item keeps its identity while the shot changes around it.

```python
"""Shot sensor: `mayapy shot_sensor.py <shot sheet>` prints
{"valid", "value", "items"} for the beats missing a key and the playblast
frames missing an image."""
import json
import os
import sys


def invalid(reason):
    print(json.dumps({"valid": False, "value": 0, "items": [], "reason": reason}))
    return 0


def frame_path(folder, pattern, frame):
    hashes = pattern.count("#")
    return os.path.join(folder, pattern.replace("#" * hashes, str(frame).zfill(hashes)))


def main(argv):
    if len(argv) != 2:
        return invalid("usage: mayapy shot_sensor.py <shot sheet>")
    sheet_path = os.path.abspath(argv[1])
    folder = os.path.dirname(sheet_path)
    try:
        with open(sheet_path, encoding="utf-8") as handle:
            sheet = json.load(handle)
        scene = os.path.join(folder, sheet["scene"])
        beats = [(str(b["control"]), int(b["frame"])) for b in sheet["beats"]]
        first, last = (int(f) for f in sheet["frame_range"])
        pattern = sheet["playblast"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return invalid("cannot read the shot sheet: %s" % exc)
    if not os.path.isfile(scene):
        return invalid("scene not found: %s" % scene)

    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        import maya.cmds as cmds
        try:
            cmds.file(scene, open=True, force=True)
        except RuntimeError as exc:
            return invalid("cannot open the scene: %s" % exc)
        items = []
        for control, frame in beats:
            count = 0
            if cmds.objExists(control):
                count = cmds.keyframe(control, query=True, time=(frame, frame),
                                      keyframeCount=True) or 0
            if not count:
                items.append("%s:%d" % (control, frame))
        for frame in range(first, last + 1):
            if not os.path.isfile(frame_path(folder, pattern, frame)):
                items.append("playblast:%d" % frame)
    finally:
        maya.standalone.uninitialize()
    items.sort()
    print(json.dumps({"valid": True, "value": len(items), "items": items}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

Save it beside `loop.json` and set `sensor_command` to `mayapy .compass/loops/LOOP-NNN-shot/shot_sensor.py shots/sh010/shot.json`, `target` 0, `direction` `down`. Run the sensor command alone once: it prints a valid reading listing every beat still unkeyed.

## Step 2: Stabilize (dampener)

`compass loop baseline LOOP-NNN` records today's missing beats; `compass loop check LOOP-NNN` then lists any beat that lost its key since, which catches an animator's edit that deleted a key the loop had set.

## Step 3: Controller

`first` takes the first missing item in sorted order, so the loop keys one control at one beat per run. A `controller_command` can instead group a control's beats when keying them together is the smaller change.

## Step 4: Actuator

A headless session allowed `Bash(mayapy:*)` beside `Read` and `Write`: a headless session denies every tool it is not allowed, so `allowed_tools` names exactly these. `actuator.md` tells it to write a short `mayapy` script that opens the scene, sets the selected key (pose taken from the golden patterns), saves the scene under the next version number, and renders the playblast frames. `golden/` holds before and after poses for the shot's characters as attribute values. Against a Maya session the animator has open, the actuator sends the same commands through Maya's commandPort instead of a batch `mayapy`, so the change appears in the live scene.

## Step 5: Schedule

`compass loop schedule LOOP-NNN --local` prints the scheduler line for the workstation, since Maya needs a licensed machine and does not run on a hosted CI runner.

## Step 6: Human on the loop

The animator plays each new shot version and records the verdict with `compass loop review LOOP-NNN <run-id> accept|reject --reason "..."`; a reject reason ("hand pops at 1012") joins `feedback.md` and steers the next run.

## Step 7: Flow control

`wip_limit` 1: one unreviewed shot version at a time, so the animator never reviews a stack of versions built on a pose he would have rejected. Set `daily_budget_usd` and `total_budget_usd` to what a shot is worth, and let a halt after repeated harmful runs bring the animator in.

"""Manager-owned active-Viewer Fast Render implementation."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid


TOOL_NAME = "Render Active Camera View"
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
OUTPUT_SUFFIX = "view"
_INVALID_FILENAME = re.compile(r"[<>:\"/\\|?*\x00-\x1f]+")
_FRAME_NUMBER = re.compile(r"(-?\d+)(?=\.(?:tif|tiff)$)", re.IGNORECASE)


def _sdk_module():
    import pyfbsdk

    return pyfbsdk


def _safe_filename(value):
    value = _INVALID_FILENAME.sub("_", str(value or "").strip())
    return re.sub(r"\s+", "_", value).strip(" ._") or "take"


def _output_directory(system, application, sdk):
    scene_path = str(application.FBXFileName or "")
    if scene_path:
        directory = os.path.dirname(os.path.abspath(scene_path))
        if os.path.isdir(directory):
            return directory
    popup = sdk.FBFolderPopup()
    popup.Caption = "Select a folder for the active camera render"
    popup.Path = str(system.UserConfigPath or "")
    if not popup.Execute():
        return None
    directory = os.path.abspath(str(popup.Path or ""))
    if not os.path.isdir(directory):
        raise RuntimeError("The selected render folder does not exist: " + directory)
    return directory


def _frame_sort_key(path):
    match = _FRAME_NUMBER.search(os.path.basename(path))
    return (0, int(match.group(1))) if match else (1, path.lower())


def _encode_qtrle(images, image_dir, movie_path, fps, ffmpeg, process_runner):
    for index, source in enumerate(sorted(images, key=_frame_sort_key)):
        os.replace(source, os.path.join(image_dir, "encode_%08d.tif" % index))
    command = (
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        "%.12g" % fps,
        "-start_number",
        "0",
        "-i",
        os.path.join(image_dir, "encode_%08d.tif"),
        "-an",
        "-c:v",
        "qtrle",
        movie_path,
    )
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = process_runner(command, **kwargs)
    if result.returncode:
        raise RuntimeError(
            "FFmpeg Animation encoding failed: "
            + str(result.stderr or result.stdout or "unknown error").strip()
        )
    if not os.path.isfile(movie_path):
        raise RuntimeError("FFmpeg did not create: " + movie_path)


def _validate_ffmpeg(ffmpeg, process_runner):
    command = (ffmpeg, "-hide_banner", "-encoders")
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = process_runner(command, **kwargs)
    except OSError as error:
        raise RuntimeError("FFmpeg could not be started: " + str(error)) from error
    output = str(result.stdout or "") + "\n" + str(result.stderr or "")
    if result.returncode:
        raise RuntimeError("FFmpeg could not list its encoders: " + output.strip())
    if not re.search(r"\bqtrle\b", output):
        raise RuntimeError("The installed FFmpeg does not provide the qtrle encoder.")


def _enable_camera_antialiasing(cameras):
    states = []
    try:
        for camera in tuple(cameras):
            enabled = bool(camera.UseAntiAliasing)
            states.append((camera, enabled))
            if not enabled:
                camera.UseAntiAliasing = True
    except Exception as error:
        for camera, enabled in reversed(states):
            camera.UseAntiAliasing = enabled
        raise RuntimeError(
            "Could not enable camera anti-aliasing for the render."
        ) from error
    return states


def _restore_camera_antialiasing(states):
    for camera, enabled in reversed(states):
        camera.UseAntiAliasing = enabled


def _render_active_view(
    system,
    player,
    sdk,
    movie_path,
    fps,
    time_mode,
    ffmpeg,
    process_runner,
):
    image_dir = tempfile.mkdtemp(
        prefix=".mobu_animation_render_",
        dir=os.path.dirname(movie_path),
    )
    grabber = sdk.FBVideoGrabber()
    try:
        time_span = system.CurrentTake.LocalTimeSpan
        start_frame = int(time_span.GetStart().GetFrame(time_mode))
        stop_frame = int(time_span.GetStop().GetFrame(time_mode))
        if stop_frame < start_frame:
            raise RuntimeError("The current take has an invalid time span.")
        print(
            "[Render] Capturing active Viewer at %dx%d, frames %d-%d."
            % (OUTPUT_WIDTH, OUTPUT_HEIGHT, start_frame, stop_frame)
        )
        for index, frame in enumerate(range(start_frame, stop_frame + 1)):
            frame_time = sdk.FBTime(0)
            frame_time.SetFrame(frame, time_mode)
            player.Goto(frame_time)
            system.Scene.Evaluate()
            image = grabber.RenderSnapshot(
                OUTPUT_WIDTH,
                OUTPUT_HEIGHT,
                False,
                True,
                False,
                False,
                False,
                True,
                True,
            )
            if image is None:
                raise RuntimeError(
                    "MotionBuilder did not return an image for frame %d." % frame
                )
            image_path = os.path.join(image_dir, "frame_%08d.tif" % index)
            try:
                if not image.WriteToTif(image_path, "", True):
                    raise RuntimeError(
                        "MotionBuilder could not write frame %d." % frame
                    )
            finally:
                image.FBDelete()
        images = [
            os.path.join(image_dir, name)
            for name in os.listdir(image_dir)
            if name.lower().endswith((".tif", ".tiff"))
        ]
        if not images:
            raise RuntimeError("MotionBuilder did not create the TIFF sequence.")
        print("[Render] Encoding active Viewer with QuickTime Animation.")
        _encode_qtrle(images, image_dir, movie_path, fps, ffmpeg, process_runner)
    finally:
        # FBVideoGrabber is a utility wrapper; FBDelete() crashes this build.
        shutil.rmtree(image_dir, ignore_errors=True)


def render(
    sdk=None,
    output_dir=None,
    camera_name=None,
    ffmpeg_resolver=shutil.which,
    process_runner=subprocess.run,
):
    sdk = sdk or _sdk_module()
    system = sdk.FBSystem()
    application = sdk.FBApplication()
    player = sdk.FBPlayerControl()
    take = system.CurrentTake
    if take is None:
        raise RuntimeError("No current take.")
    output_dir = output_dir or _output_directory(system, application, sdk)
    if output_dir is None:
        return ()
    ffmpeg = ffmpeg_resolver("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg with the qtrle encoder was not found in PATH.")
    _validate_ffmpeg(ffmpeg, process_runner)

    time_mode = player.GetTransportFps()
    fps = float(player.GetTransportFpsValue(time_mode))
    take_name = _safe_filename(take.Name)
    camera_file_name = _safe_filename(camera_name or OUTPUT_SUFFIX)
    output_path = os.path.join(
        output_dir,
        "%s_%s.mov" % (take_name, camera_file_name),
    )
    staging_path = os.path.join(
        output_dir,
        ".%s.%s.rendering.mov"
        % (os.path.splitext(os.path.basename(output_path))[0], uuid.uuid4().hex),
    )
    current_time = sdk.FBTime(system.LocalTime.Get())
    antialiasing_states = _enable_camera_antialiasing(system.Scene.Cameras)

    try:
        _render_active_view(
            system,
            player,
            sdk,
            staging_path,
            fps,
            time_mode,
            ffmpeg,
            process_runner,
        )
        os.replace(staging_path, output_path)
        return (output_path,)
    finally:
        _restore_camera_antialiasing(antialiasing_states)
        player.Goto(current_time)
        system.Scene.Evaluate()
        if os.path.exists(staging_path):
            try:
                os.remove(staging_path)
            except OSError:
                pass


def run(camera_name=None):
    sdk = _sdk_module()
    try:
        paths = render(sdk=sdk, camera_name=camera_name)
    except Exception as error:
        sdk.FBMessageBox(TOOL_NAME, str(error), "OK")
        return ()
    if paths:
        sdk.FBMessageBox(TOOL_NAME, "Rendered:\n" + "\n".join(paths), "OK")
    return paths


def render_current_take(context=None, camera_name=None):
    del context
    return render(camera_name=camera_name)


def execute(context, invocation=None):
    del context
    camera_name = str((invocation or {}).get("camera_name") or "").strip()
    return run(camera_name=camera_name or None)


if __name__ in ("__main__", "__builtin__"):
    run()

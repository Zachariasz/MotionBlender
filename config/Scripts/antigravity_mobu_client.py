#!/usr/bin/env python
"""Antigravity MotionBuilder Bridge Client & CLI Tool.

Provides seamless main-thread command execution, scene introspection,
viewport capture, and diagnostic probes for MotionBuilder.
"""

from __future__ import absolute_import, print_function

import argparse
import json
import os
import sys
import time


def _find_bridge_root():
    # 1. Check environment variable
    env_root = os.environ.get("ANTIGRAVITY_MOBU_BRIDGE_ROOT")
    if env_root and os.path.isdir(env_root):
        return os.path.abspath(env_root)

    # 2. Check relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_root = os.path.join(script_dir, ".antigravity_mobu_bridge")
    if os.path.isdir(local_root) or os.path.isdir(os.path.join(script_dir, "mobu_tools_manager")):
        return local_root

    # 3. Check current working directory
    cwd_root = os.path.join(os.getcwd(), ".antigravity_mobu_bridge")
    return cwd_root


class AntigravityBridgeClient(object):
    """Client interface to interact with an active Antigravity MotionBuilder Bridge."""

    def __init__(self, bridge_root=None):
        self.bridge_root = os.path.abspath(bridge_root or _find_bridge_root())
        self.commands_dir = os.path.join(self.bridge_root, "commands")
        self.running_dir = os.path.join(self.bridge_root, "running")
        self.done_dir = os.path.join(self.bridge_root, "done")
        self.results_dir = os.path.join(self.bridge_root, "results")
        self.captures_dir = os.path.join(self.bridge_root, "captures")
        self.logs_dir = os.path.join(self.bridge_root, "logs")
        self.status_path = os.path.join(self.bridge_root, "status.json")
        self.heartbeat_path = os.path.join(self.bridge_root, "heartbeat.txt")

    def _ensure_dirs(self):
        for path in (
            self.bridge_root,
            self.commands_dir,
            self.running_dir,
            self.done_dir,
            self.results_dir,
            self.captures_dir,
            self.logs_dir,
        ):
            if not os.path.isdir(path):
                os.makedirs(path)

    def get_status(self):
        """Returns bridge status dict or None if offline."""
        if not os.path.isfile(self.status_path):
            return None
        try:
            with open(self.status_path, "r", encoding="utf-8") as stream:
                return json.load(stream)
        except Exception:
            return None

    def get_heartbeat_age(self):
        """Returns elapsed seconds since last heartbeat, or None if unavailable."""
        if not os.path.isfile(self.heartbeat_path):
            return None
        try:
            mtime = os.path.getmtime(self.heartbeat_path)
            return max(0.0, time.time() - mtime)
        except OSError:
            return None

    def is_alive(self, max_heartbeat_age=5.0):
        """Checks if bridge is running with a recent heartbeat."""
        status = self.get_status()
        if not status or status.get("state") not in ("running", "busy"):
            return False
        age = self.get_heartbeat_age()
        if age is None or age > max_heartbeat_age:
            return False
        return True

    def ping(self):
        """Pings bridge and returns health status dict."""
        status = self.get_status()
        age = self.get_heartbeat_age()
        alive = self.is_alive()
        return {
            "alive": alive,
            "state": status.get("state") if status else "offline",
            "heartbeat_age_seconds": round(age, 2) if age is not None else None,
            "processed_count": status.get("processed_count", 0) if status else 0,
            "last_command": status.get("last_command") if status else None,
            "last_error": status.get("last_error") if status else None,
            "bridge_root": self.bridge_root,
        }

    def send_command(self, code, name="cmd", timeout=20.0, poll_interval=0.1):
        """Submits a Python code payload atomically and waits for execution result."""
        self._ensure_dirs()
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        base_name = "%s_%s_%x.py" % (stamp, name, int(time.time() * 1000) & 0xFFFF)
        temp_path = os.path.join(self.commands_dir, base_name + ".tmp")
        final_path = os.path.join(self.commands_dir, base_name)

        # Write atomically
        with open(temp_path, "w", encoding="utf-8") as stream:
            stream.write(code)
        os.replace(temp_path, final_path)

        deadline = time.time() + timeout
        prefix = "%s_%s_%x" % (stamp, name, int(time.time() * 1000) & 0xFFFF)
        stem = os.path.splitext(base_name)[0]

        while time.time() < deadline:
            # Check results directory
            try:
                result_files = os.listdir(self.results_dir)
            except OSError:
                result_files = []

            for result_name in result_files:
                if result_name.startswith(stem) and result_name.endswith(".json"):
                    result_path = os.path.join(self.results_dir, result_name)
                    try:
                        with open(result_path, "r", encoding="utf-8") as stream:
                            return json.load(stream)
                    except (OSError, json.JSONDecodeError):
                        pass

            time.sleep(poll_interval)

        return {
            "ok": False,
            "error": "Timed out after %.1fs waiting for bridge execution" % timeout,
            "command": base_name,
        }

    def eval(self, expression, timeout=10.0):
        """Evaluates a single expression or Python statement in MotionBuilder."""
        payload = (
            "try:\n"
            "    __val = eval(%r)\n"
            "    set_result(__val)\n"
            "except SyntaxError:\n"
            "    exec(%r)\n"
        ) % (expression, expression)
        return self.send_command(payload, name="eval", timeout=timeout)

    def exec_file(self, script_path, timeout=30.0):
        """Executes a Python script file in MotionBuilder."""
        with open(script_path, "r", encoding="utf-8-sig") as stream:
            code = stream.read()
        name = os.path.splitext(os.path.basename(script_path))[0]
        return self.send_command(code, name=name, timeout=timeout)

    def capture_viewport(self, output_path=None, timeout=15.0):
        """Triggers a viewport snapshot and returns the resulting PNG path."""
        if output_path:
            payload = "set_result(capture_viewport(output_path=%r))\n" % output_path
        else:
            payload = "set_result(capture_viewport())\n"
        return self.send_command(payload, name="capture", timeout=timeout)

    def probe(self, target="scene", timeout=10.0):
        """Probes scene introspection helpers in MotionBuilder."""
        if target == "scene":
            payload = "set_result(get_scene_summary())\n"
        elif target in ("selected", "transforms"):
            payload = "set_result(get_selected_transforms())\n"
        elif target == "fcurves":
            payload = "set_result(get_fcurve_summary())\n"
        elif target == "all":
            payload = (
                "set_result({\n"
                "    'scene': get_scene_summary(),\n"
                "    'transforms': get_selected_transforms(),\n"
                "    'fcurves': get_fcurve_summary(),\n"
                "})\n"
            )
        else:
            payload = "set_result(get_scene_summary())\n"
        return self.send_command(payload, name="probe_%s" % target, timeout=timeout)

    def stop(self, timeout=5.0):
        """Requests graceful bridge shutdown."""
        return self.send_command("stop()\nset_result('stopped')\n", name="stop", timeout=timeout)


def _format_result(data, as_json=False):
    if as_json:
        return json.dumps(data, indent=2, sort_keys=True)

    if not isinstance(data, dict):
        return str(data)

    lines = []
    ok = data.get("ok", False)
    status_tag = "[OK]" if ok else "[ERROR]"
    lines.append("%s %s (Duration: %sms)" % (status_tag, data.get("command", ""), data.get("duration_ms", 0)))

    if data.get("stdout"):
        lines.append("--- Stdout ---")
        lines.append(data["stdout"].rstrip())

    if data.get("stderr"):
        lines.append("--- Stderr ---")
        lines.append(data["stderr"].rstrip())

    if data.get("bridge_logs"):
        lines.append("--- Bridge Logs ---")
        for log in data["bridge_logs"]:
            lines.append("  * %s" % log)

    if data.get("result") is not None:
        lines.append("--- Result ---")
        lines.append(json.dumps(data["result"], indent=2))

    if data.get("error"):
        lines.append("--- Traceback / Error ---")
        lines.append(data["error"].rstrip())

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Antigravity MotionBuilder Bridge CLI tool for testing, debugging, and development."
    )
    parser.add_argument(
        "--root",
        "-r",
        help="Path to .antigravity_mobu_bridge root folder",
        default=None,
    )
    parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output raw JSON response",
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Bridge action")

    # ping
    subparsers.add_parser("ping", help="Check bridge status and heartbeat liveness")
    subparsers.add_parser("status", help="Get detailed bridge status")

    # eval
    eval_parser = subparsers.add_parser("eval", help="Evaluate a Python expression or code in MotionBuilder")
    eval_parser.add_argument("code", help="Python code or expression to run")
    eval_parser.add_argument("--timeout", "-t", type=float, default=15.0, help="Timeout in seconds")

    # exec
    exec_parser = subparsers.add_parser("exec", help="Execute a Python script file in MotionBuilder")
    exec_parser.add_argument("script", help="Path to Python script file")
    exec_parser.add_argument("--timeout", "-t", type=float, default=30.0, help="Timeout in seconds")

    # capture
    capture_parser = subparsers.add_parser("capture", help="Capture active MotionBuilder viewport to PNG")
    capture_parser.add_argument("--output", "-o", help="Target PNG file path", default=None)
    capture_parser.add_argument("--timeout", "-t", type=float, default=15.0, help="Timeout in seconds")

    # probe
    probe_parser = subparsers.add_parser("probe", help="Probe MotionBuilder scene, objects, or fcurves")
    probe_parser.add_argument(
        "target",
        nargs="?",
        choices=["scene", "selected", "transforms", "fcurves", "all"],
        default="scene",
        help="Probe target (default: scene)",
    )
    probe_parser.add_argument("--timeout", "-t", type=float, default=10.0, help="Timeout in seconds")

    # stop
    subparsers.add_parser("stop", help="Stop bridge service")

    args = parser.parse_args()

    client = AntigravityBridgeClient(bridge_root=args.root)

    if not args.subcommand or args.subcommand in ("ping", "status"):
        res = client.ping()
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            state = res.get("state", "offline").upper()
            alive = "[ONLINE]" if res.get("alive") else "[OFFLINE]"
            print("%s Bridge State: %s" % (alive, state))
            print("Heartbeat Age : %ss" % res.get("heartbeat_age_seconds"))
            print("Processed Cmds: %s" % res.get("processed_count"))
            print("Bridge Root   : %s" % res.get("bridge_root"))
            if res.get("last_error"):
                print("Last Error    : %s" % res.get("last_error"))
        sys.exit(0 if res.get("alive") else 1)

    elif args.subcommand == "eval":
        res = client.eval(args.code, timeout=args.timeout)
        print(_format_result(res, as_json=args.json))
        sys.exit(0 if res.get("ok") else 1)

    elif args.subcommand == "exec":
        if not os.path.isfile(args.script):
            print("Error: Script file not found: %s" % args.script, file=sys.stderr)
            sys.exit(1)
        res = client.exec_file(args.script, timeout=args.timeout)
        print(_format_result(res, as_json=args.json))
        sys.exit(0 if res.get("ok") else 1)

    elif args.subcommand == "capture":
        res = client.capture_viewport(output_path=args.output, timeout=args.timeout)
        print(_format_result(res, as_json=args.json))
        sys.exit(0 if res.get("ok") else 1)

    elif args.subcommand == "probe":
        res = client.probe(target=args.target, timeout=args.timeout)
        print(_format_result(res, as_json=args.json))
        sys.exit(0 if res.get("ok") else 1)

    elif args.subcommand == "stop":
        res = client.stop()
        print(_format_result(res, as_json=args.json))
        sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()

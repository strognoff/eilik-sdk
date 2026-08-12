"""Command line entrypoint for the Eilik SDK."""

from __future__ import annotations

import argparse
import os
import sys

from .controller import EilikController


MOTION_COMMANDS = {
    "wave": "wave",
    "nod": "nod",
    "shake_head": "shake_head",
    "look_left": "look_left",
    "look_right": "look_right",
    "left_arm_up": "left_arm_up",
    "left_arm_down": "left_arm_down",
    "right_arm_up": "right_arm_up",
    "right_arm_down": "right_arm_down",
    "reset": "reset_pose",
    "reset_pose": "reset_pose",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control an Eilik robot over USB serial.")
    parser.add_argument(
        "command",
        choices=["connect", "monitor", "serve", "read_display", "write_display",
                 "read_running_number", "write_running_number", "read_servo_angles",
                 *MOTION_COMMANDS.keys()],
    )
    parser.add_argument("--port", help="Serial port. Defaults to /dev/ttyACM0, then auto-discovery.")
    parser.add_argument("--log", default="logs/eilik.log", help="Packet log file path.")
    parser.add_argument("--monitor-log", default="logs/eilik-monitor.log", help="Monitor output file.")
    parser.add_argument("--host", default="127.0.0.1", help="FastAPI bind host for `serve`.")
    parser.add_argument("--port-http", type=int, default=8765, help="FastAPI bind port for `serve`.")
    parser.add_argument("--image", help="For write_display: 1024-byte raw framebuffer file.")
    parser.add_argument("--output", help="For read_display: where to save the 1024-byte framebuffer.")
    parser.add_argument("--index", type=int, help="For write_running_number: animation index.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "serve":
        if args.port:
            os.environ["EILIK_PORT"] = args.port
        os.environ["EILIK_LOG_PATH"] = args.log

        import uvicorn

        uvicorn.run(
            "eilik.service:app",
            host=args.host,
            port=args.port_http,
            factory=False,
            reload=False,
        )
        return 0

    controller = EilikController(port=args.port, log_path=args.log)
    try:
        controller.connect()
        if args.command == "connect":
            print(f"Connected to Eilik on {controller.port} using {controller.protocol_variant} protocol")
            return 0
        if args.command == "monitor":
            controller.monitor(args.monitor_log)
            return 0

        if args.command == "read_display":
            img = controller.read_display()
            if img is None:
                print("No reply from Eilik")
                return 1
            if args.output:
                with open(args.output, "wb") as f:
                    f.write(img)
                print(f"Saved {len(img)} bytes to {args.output}")
            else:
                import sys as _sys
                _sys.stdout.buffer.write(img)
            return 0

        if args.command == "write_display":
            if not args.image:
                print("--image <1024-byte file> required for write_display")
                return 1
            with open(args.image, "rb") as f:
                payload = f.read()
            if len(payload) != 1024:
                print(f"image file must be exactly 1024 bytes (got {len(payload)})")
                return 1
            ok = controller.write_display(payload)
            print("ACK" if ok else "NO ACK")
            return 0 if ok else 1

        if args.command == "read_running_number":
            print(controller.read_running_number())
            return 0

        if args.command == "write_running_number":
            if args.index is None:
                print("--index <int> required")
                return 1
            controller.write_running_number(args.index)
            print("OK")
            return 0

        if args.command == "read_servo_angles":
            print(controller.read_servo_angles())
            return 0

        method = getattr(controller, MOTION_COMMANDS[args.command])
        method()
        print(f"Executed {args.command}")
        return 0
    finally:
        controller.disconnect()


if __name__ == "__main__":
    sys.exit(main())

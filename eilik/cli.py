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
    new_cmds = ["action", "ambient", "choreo", "list_actions", "morning",
                "welcome", "cron_done", "error", "subagent_done", "email", "quinn",
                "celebrate", "apology"]
    parser.add_argument(
        "command",
        choices=["connect", "monitor", "serve", "read_display", "write_display",
                 "display_image", "read_running_number", "write_running_number",
                 "read_servo_angles", *new_cmds, *MOTION_COMMANDS.keys()],
    )
    parser.add_argument("--port", help="Serial port. Defaults to /dev/ttyACM0, then auto-discovery.")
    parser.add_argument("--log", default="logs/eilik.log", help="Packet log file path.")
    parser.add_argument("--monitor-log", default="logs/eilik-monitor.log", help="Monitor output file.")
    parser.add_argument("--host", default="127.0.0.1", help="FastAPI bind host for `serve`.")
    parser.add_argument("--port-http", type=int, default=8765, help="FastAPI bind port for `serve`.")
    parser.add_argument("--image", help="For write_display: 1024-byte raw framebuffer file or PNG.")
    parser.add_argument("--output", help="For read_display: where to save the 1024-byte framebuffer.")
    parser.add_argument("--index", type=int, help="For write_running_number: animation index.")
    parser.add_argument("--invert", action="store_true",
                        help="For write_display with PNG: invert (white-on-black source).")
    parser.add_argument("--threshold", type=int, default=128,
                        help="For write_display with PNG: grayscale threshold for 1bpp.")
    parser.add_argument("--name", help="Action/cron/subagent name (multi-purpose).")
    parser.add_argument("--ambient", help="Ambient kind (clock, streak, weather, pr, calendar_nudge, energy_meter, mood, crypto_ticker, tts).")
    parser.add_argument("--text", help="Free-text argument (clock='HH:MM', streak='days', pr='num=author', energy_meter='percent', tts='text').")
    parser.add_argument("--hold", type=float, help="Hold seconds for the display.")
    parser.add_argument("--no-idle", action="store_true", help="Don't restore firmware idle after the action.")
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
                print("--image <1024-byte file or PNG> required for write_display")
                return 1
            if args.image.lower().endswith(".png"):
                ok = controller.display_image(args.image, invert=args.invert,
                                              threshold=args.threshold)
            else:
                with open(args.image, "rb") as f:
                    payload = f.read()
                if len(payload) != 1024:
                    print(f"image file must be exactly 1024 bytes (got {len(payload)})")
                    return 1
                ok = controller.write_display(payload)
            print("ACK" if ok else "NO ACK")
            return 0 if ok else 1

        if args.command == "display_image":
            if not args.image:
                print("--image <PNG file> required for display_image")
                return 1
            ok = controller.display_image(args.image, invert=args.invert,
                                          threshold=args.threshold)
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

        if args.command == "action":
            if not args.name:
                print("--name <action> required (try `python -m eilik.cli list-actions`)")
                return 1
            ok = controller.action(args.name, hold_seconds=args.hold, auto_idle=not args.no_idle)
            print("Executed" if ok else "Failed")
            return 0 if ok else 1

        if args.command == "ambient":
            if not args.ambient:
                print("--ambient <kind> required (clock, streak, weather, pr, calendar_nudge, energy_meter, mood, crypto_ticker, tts)")
                return 1
            fn = getattr(controller, f'show_{args.ambient}', None)
            if not fn:
                print(f"unknown ambient kind: {args.ambient}")
                return 1
            kwargs = {}
            if args.text:
                if args.ambient == 'clock':
                    # text arg interpreted as 'HH:MM'
                    if ':' in args.text:
                        h, m = args.text.split(':', 1)
                        kwargs['hour'] = int(h)
                        kwargs['minute'] = int(m)
                    else:
                        kwargs['text'] = int(args.text) if args.ambient == 'streak' else args.text
                elif args.ambient in ('streak', 'pr', 'energy_meter'):
                    if args.ambient == 'pr' and '=' in args.text:
                        # format: '42=author'
                        num, author = args.text.split('=', 1)
                        kwargs['pr_number'] = int(num)
                        kwargs['author'] = author
                    else:
                        try:
                            kwargs[{'streak': 'days', 'pr': 'pr_number', 'energy_meter': 'soi_percent'}[args.ambient]] = int(args.text)
                        except ValueError:
                            kwargs['text'] = args.text
                else:
                    kwargs['text'] = args.text
            if args.hold is not None:
                kwargs['hold_seconds'] = args.hold
            ok = fn(**kwargs)
            print("OK" if ok else "FAIL")
            return 0 if ok else 1

        if args.command == "choreo":
            from eilik.controller import EilikController as _E
            # Pass JSON-encoded step list via --name
            import json
            try:
                steps = json.loads(args.name or '[]')
            except Exception as exc:
                print(f'parse: {exc}')
                return 1
            controller.choreography(steps)
            print("OK")
            return 0

        if args.command == "list_actions":
            from eilik.actions import ACTIONS
            for name in sorted(ACTIONS):
                spec = ACTIONS[name]
                face = spec.get('face') or '-'
                motion = spec.get('motion') or '-'
                print(f"{name:30s}  motion={motion:20s}  face={face}")
            return 0

        if args.command == "morning":
            controller.morning_routine()
            print("OK")
            return 0

        if args.command == "welcome":
            controller.welcome_back()
            print("OK")
            return 0

        if args.command == "cron_done":
            controller.cron_tick_done(args.name or "")
            print("OK")
            return 0

        if args.command == "error":
            controller.error_flash(args.name or "")
            print("OK")
            return 0

        if args.command == "subagent_done":
            controller.subagent_returned(args.name or "")
            print("OK")
            return 0

        if args.command == "email":
            controller.email_arrived(args.name or "")
            print("OK")
            return 0

        if args.command == "quinn":
            controller.quinn_comms()
            print("OK")
            return 0

        if args.command == "celebrate":
            controller.celebrate(args.name or "")
            print("OK")
            return 0

        if args.command == "apology":
            controller.apology(args.name or "")
            print("OK")
            return 0

        method = getattr(controller, MOTION_COMMANDS[args.command])
        method()
        print(f"Executed {args.command}")
        return 0
    finally:
        controller.disconnect()


if __name__ == "__main__":
    sys.exit(main())

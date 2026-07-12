from __future__ import annotations

import argparse
import os

from subtitle_extractor.gradio_ui import build_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the Gradio cloud UI.")
    parser.add_argument("--share", action="store_true", help="Create a public Gradio share URL.")
    parser.add_argument("--server-name", default="0.0.0.0", help="Host interface.")
    parser.add_argument("--server-port", type=int, default=7860, help="Port to bind.")
    args = parser.parse_args()

    auth_username = os.environ.get("GRADIO_AUTH_USERNAME", "").strip()
    auth_password = os.environ.get("GRADIO_AUTH_PASSWORD", "").strip()
    if bool(auth_username) != bool(auth_password):
        parser.error("GRADIO_AUTH_USERNAME and GRADIO_AUTH_PASSWORD must be set together.")
    auth = (auth_username, auth_password) if auth_username else None

    demo = build_demo()
    demo.queue(default_concurrency_limit=1).launch(
        share=args.share,
        server_name=args.server_name,
        server_port=args.server_port,
        show_error=True,
        auth=auth,
    )


if __name__ == "__main__":
    main()

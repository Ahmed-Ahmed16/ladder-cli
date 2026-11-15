import argparse
import os
import time


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("n", type=int)
    parser.add_argument("code", type=int)
    parser.add_argument("first_line", nargs="?")
    parser.add_argument("--at", nargs=2, metavar=("K", "TEXT"))
    parser.add_argument("--sleep", type=float, default=0)
    args = parser.parse_args(argv)
    time.sleep(args.sleep)
    if args.first_line is not None:
        print(args.first_line, flush=True)
    for i in range(1, args.n + 1):
        text = args.at[1] if args.at and i == int(args.at[0]) else f"line {i} of {args.n}"
        print(text, flush=True)
    if "LAB_MARKER" in os.environ:
        print(os.environ["LAB_MARKER"], flush=True)
    return args.code


if __name__ == "__main__":
    raise SystemExit(main())

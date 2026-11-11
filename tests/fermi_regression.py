#!/usr/bin/env python3
"""Regression test for dekomme's Fermi mode.

Usage: fermi_regression.py --baseline PATH [--dekomme PATH] [--dekodef PATH]
                           [--maxwell DIR]
"""
import argparse
import glob
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")


def run(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit("command failed: %s\n%s" % (" ".join(cmd), res.stderr))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="dekomme built before the changes")
    ap.add_argument("--dekomme", default=os.path.join(ROOT, "build", "dekomme"))
    ap.add_argument("--dekodef", default=os.path.join(ROOT, "build", "dekodef"))
    ap.add_argument("--maxwell", default="/home/breadloaf/CLionProjects/ounce/drako3d/source/maxwell")
    args = ap.parse_args()

    work = tempfile.mkdtemp(prefix="fermireg-")
    engine = os.path.join(work, "engine_3d.mme")
    run([args.dekodef, "-h", os.path.join(work, "engine_3d.h"), "-m", engine,
         os.path.join(args.maxwell, "engine_3d.def")])
    macros = sorted(glob.glob(os.path.join(args.maxwell, "*.mme")),
                    key=os.path.basename)

    suites = {
        "drako3d mme_macros.h (%d macro files + engine_3d.mme)" % len(macros): [engine] + macros,
        "maintest.mme": [os.path.join(ROOT, "maintest.mme")],
    }
    variants = [
        ("default", [], []),
        ("--isa=fermi", ["--isa=fermi"], []),
        ("--name=Foo -s 2", ["--name=Foo", "--subchannel=2"], ["--name=Foo", "--subchannel=2"]),
    ]

    fails = 0
    for title, inputs in suites.items():
        for vname, newopts, baseopts in variants:
            ref = os.path.join(work, "ref.h")
            out = os.path.join(work, "out.h")
            run([args.baseline] + baseopts + ["-o", ref] + inputs)
            run([args.dekomme] + newopts + ["-o", out] + inputs)
            same = open(ref, "rb").read() == open(out, "rb").read()
            size = os.path.getsize(ref)
            print("%-55s %-17s %s (%d bytes)" % (title, vname, "identical" if same else "DIFFERS", size))
            fails += not same

    for fn in os.listdir(work):
        os.unlink(os.path.join(work, fn))
    os.rmdir(work)
    print("fermi regression: %s" % ("PASS" if not fails else "%d FAILURES" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

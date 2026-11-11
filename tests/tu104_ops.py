#!/usr/bin/env python3
"""Encoding test for the parts of the tu104 ISA

Usage: tu104_ops.py [--dekomme PATH]
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

ALU = {n: i for i, n in enumerate(
    ["ADD", "ADDC", "SUB", "SUBB", "MUL", "MULH", "MULU", "EXTENDED", "CLZ",
     "SLL", "SRL", "SRA", "AND", "NAND", "OR", "XOR", "MERGE", "SLT", "SLTU",
     "SLE", "SLEU", "SEQ", "STATE", "LOOP", "JAL", "BLT", "BLTU", "BLE",
     "BLEU", "BEQ", "DREAD", "DWRITE"])}
OUT = {n: i for i, n in enumerate(
    ["NONE", "ALU0", "ALU1", "LOAD0", "LOAD1", "IMM0", "IMM1", "RESERVED",
     "IMMHIGH0", "IMMHIGH1", "IMM32"])}
PRED = ["UUUU", "TTTT", "FFFF", "TTUU", "FFUU", "TFUU", "TUUU", "FUUU",
        "UUTT", "UUTF", "UUTU", "UUFT", "UUFF", "UUFU", "UUUT", "UUUF"]
ZERO, IMM, IMMPAIR, IMM32, LOAD0, LOAD1 = 24, 25, 26, 27, 28, 29


def decode(w0, w1, w2):
    b = w2 | (w1 << 32) | (w0 << 64)
    f = lambda s, n: (b >> s) & ((1 << n) - 1)
    return {
        "end": f(0, 1), "pm": f(1, 4), "pred": f(5, 5),
        "op0": f(10, 5), "dst0": f(15, 5), "s00": f(20, 5), "s01": f(25, 5),
        "imm0": f(30, 16),
        "op1": f(46, 5), "dst1": f(51, 5), "s10": f(56, 5), "s11": f(61, 5),
        "imm1": f(66, 16),
        "m0": f(82, 3), "e0": f(85, 4), "m1": f(89, 3), "e1": f(92, 4),
    }


CASES = []


def case(src, *insts):
    CASES.append((src, list(insts)))


for i, op in enumerate(["ADD", "SUB", "MUL", "MULU", "EXTENDED", "SLL", "SRL",
                        "SRA", "AND", "NAND", "OR", "XOR", "SLT", "SLTU",
                        "SLE", "SLEU", "SEQ", "DWRITE"]):
    r = 10 + i % 14
    dst = "$zero" if op in ("DWRITE", "EXTENDED") else "$r%d" % r
    case("{\n %s = %s $r%d $r23\n $r1 = %s $load0 $load1\n}" % (dst, op, r, op),
         {"op0": ALU[op], "dst0": ZERO if dst == "$zero" else r, "s00": r, "s01": 23,
          "op1": ALU[op], "dst1": 1, "s10": LOAD0, "s11": LOAD1})

for op in ("CLZ", "DREAD"):
    case("$r22 = %s $r21" % op, {"op0": ALU[op], "dst0": 22, "s00": 21, "s01": ZERO})

case("{\n $r0 = ADD $r1 $r2\n $r3 = ADDC $r4 $r5 $carry\n}",
     {"op0": ALU["ADD"], "op1": ALU["ADDC"], "dst1": 3, "s10": 4, "s11": 5})
case("{\n $r3 = SUBB $r4 $r5\n $r0 = SUB $r1 $r2\n}",
     {"op0": ALU["SUB"], "dst0": 0, "op1": ALU["SUBB"], "dst1": 3})
case("{\n $r0 = MUL $r1 $r2\n $r3 = MULH $alu0\n}",
     {"op0": ALU["MUL"], "op1": ALU["MULH"], "dst1": 3, "s10": ZERO, "s11": ZERO})
case("{\n $r0 = MULU $r1 $r2\n $r3 = MULH\n}", {"op1": ALU["MULH"]})

case("$r0 = ADD $r1 -1", {"s01": IMM, "imm0": 0xFFFF})
case("$r0 = ADD $r1 0x7fff", {"s01": IMM, "imm0": 0x7FFF})
case("$r0 = ADD $r1 0x8000", {"s01": IMM32, "imm0": 0x0000, "imm1": 0x8000})
case("$r0 = ADD $r1 0xdeadbeef", {"s01": IMM32, "imm0": 0xDEAD, "imm1": 0xBEEF})
case("EXTENDED 0x1000 1", {"op0": ALU["EXTENDED"], "s00": IMM, "s01": IMMPAIR,
                           "imm0": 0x1000, "imm1": 1})
case("{\n $r0 = ADD $r1 5\n $r2 = SUB $r3 7\n}",
     {"s01": IMM, "imm0": 5, "s11": IMM, "imm1": 7})
case("{\n $r0 = ADD $r1 $r1\n $r2 = SUB $r3 7\n}", {"s11": IMMPAIR, "imm0": 7})
case("$r0 = MERGE $r1 $r2 (12, 5, 3)", {"op0": ALU["MERGE"], "imm0": (12 << 10) | (5 << 5) | 3})
case("$r0 = MERGE $r1 $r2 (src_pos=3, dst_pos=63, bits=31)",
     {"imm0": (63 << 10) | (31 << 5) | 3})
case("%equ Base 0x200\n$r0 = STATE Base[4] + $r1",
     {"op0": ALU["STATE"], "s00": IMM, "s01": 1, "imm0": 0x204})

case("{\n $alu1 = ADD $r1 $zero\n mthd($alu1)\n emit($load0)\n mthd($load0)\n emit($load1)\n}",
     {"m0": OUT["ALU1"], "e0": OUT["LOAD0"], "m1": OUT["LOAD0"], "e1": OUT["LOAD1"],
      "op1": ALU["ADD"], "dst1": ZERO})
case("{\n mthd(0x45a, incr=3)\n emit 3\n mthd(0x100)\n emit 0\n}",
     {"m0": OUT["IMM0"], "e0": OUT["IMMHIGH0"], "imm0": 0x345A,
      "m1": OUT["IMM1"], "e1": OUT["IMMHIGH1"], "imm1": 0x100})
case("{\n emit 0xffffffff\n emit $alu0\n $alu0 = ADD $r1 $zero\n}",
     {"e0": OUT["IMM32"], "imm0": 0xFFFF, "imm1": 0xFFFF, "e1": OUT["ALU0"]})
case("{\n mthd(0x10)\n emit 0x10\n}", {"m0": OUT["IMM0"], "e0": OUT["IMM1"], "imm1": 0x10})

for i, p in enumerate(PRED):
    case("pred %s $r%d {\n $r0 = ADD $r1 $r2\n}" % (p, 10 + i % 14),
         {"pm": i, "pred": 10 + i % 14})
case("pred tfuu $load0 $r0 = ADD $r1 $r2", {"pm": 5, "pred": LOAD0})

for i, (mn, op, expect) in enumerate([
        ("BLT", "BLT", 1), ("BLTU", "BLTU", 1), ("BLE", "BLE", 1), ("BLEU", "BLEU", 1),
        ("BEQ", "BEQ", 1), ("BGE", "BLT", 0), ("BGEU", "BLTU", 0), ("BGT", "BLE", 0),
        ("BGTU", "BLEU", 0), ("BNE", "BEQ", 0)]):
    case("Top:\n %s $r1 $r2 EXIT\n %s $r1 $r2 ip 0\n *%s $r1 $r2 .fwd\n nop\n.fwd\n nop" % (mn, mn, mn),
         {"op0": ALU[op], "imm0": (expect << 15) | 0x1000},
         {"op0": ALU[op], "imm0": (expect << 15) | (-1 & 0x1FFF)},
         {"op0": ALU[op], "end": 1, "imm0": (expect << 15) | (1 << 14) | 2},
         {}, {})
case("JAL .t\n nop\n.t\n nop", {"op0": ALU["JAL"], "imm0": 0x8002, "s00": ZERO, "s01": ZERO}, {}, {})
case("LOOP $r3 .end\n nop\n nop\n.end\n nop", {"op0": ALU["LOOP"], "s00": 3, "imm0": 3}, {}, {}, {})
case("LOOP 12 .end\n nop\n.end", {"op0": ALU["LOOP"], "s00": IMMPAIR, "imm0": 2, "imm1": 12}, {})
case("Entry::\n $r0 = ADD $r1 1\n Inner:\n BEQ $r0 $zero Entry",
     {}, {"op0": ALU["BEQ"], "imm0": (1 << 15) | (-1 & 0x1FFF)})

case("#[\nblock comment #]\n$r0 = ADD $r1 ((3 << 4) | 1)  ; trailing\nexit\nnop",
     {"imm0": 0x31}, {"end": 1}, {"end": 0})

ERRORS = [
    ("$r0 = ADD $load1 $zero", "$load1 cannot be used without $load0"),
    ("{\n $r0 = STATE 1\n $r1 = STATE 2\n}", "only one STATE"),
    ("{\n $r0 = ADD $r1 $r2\n $r3 = ADD $r1 $r2\n $r4 = ADD $r1 $r2\n}", "too many ALU"),
    ("$r0 = ADDC $r1 $r2", "ADDC requires an ADD"),
    ("{\n $r0 = ADD $r1 1\n $r2 = ADD $r1 2\n mthd(0x10)\n}", "out of immediate slots"),
    ("{\n mthd(0x45a, incr=3)\n emit 3\n mthd(0x100)\n emit 0x12345\n}", "out of immediate slots"),
    ("{\n emit 1\n emit 2\n emit 3\n}", "too many mthd/emit"),
    ("$r24 = ADD $r1 $r2", "register out of range"),
    ("$r0 = BEQ $r1 $r2 EXIT", "control flow operations cannot have a destination"),
    ("JAL EXIT", "EXIT is only valid as a branch target"),
    ("L:\n nop\n JAL L", "JAL target out of range"),
    ("LOOP $r0 .e\n.e", "LOOP end out of range"),
    ("BEQ $r0 $r1 nowhere", "Undefined reference to nowhere"),
    ("mthd(0x1000, incr=0)", "method address out of range"),
    ("pred XYZW $r0 nop", "unknown predicate mode"),
    ("$r0 = ADD $r1", "syntax error"),
    ("pred TFXU $r0 $r0 = ADD $r1 $r2", "unknown predicate mode"),
    ("{\n $alu0 = ADD $r1 $r2\n $alu0 = SUB $r1 $r2\n}", "ALU slot used twice"),
    ("$r0 = MERGE $r1 $r2 (dst_pos=1, bits=2, dst_pos=3)", "exactly once"),
]


def assemble(dekomme, src, work, name):
    path = os.path.join(work, name + ".mme")
    out = os.path.join(work, name + ".bin")
    with open(path, "w") as f:
        f.write(src + "\n")
    res = subprocess.run([dekomme, "--isa=turing", "--binary", "-o", out, path],
                         capture_output=True, text=True)
    if res.returncode != 0:
        return None, res.stderr
    data = open(out, "rb").read()
    return struct.unpack("<%dI" % (len(data) // 4), data), res.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dekomme", default=os.path.join(HERE, "..", "build", "dekomme"))
    args = ap.parse_args()
    work = tempfile.mkdtemp(prefix="tu104ops-")
    fails = 0

    for n, (src, expect) in enumerate(CASES):
        words, err = assemble(args.dekomme, src, work, "case%d" % n)
        if words is None:
            print("FAIL case %d: assembler error\n%s\n%s" % (n, src, err))
            fails += 1
            continue
        if len(words) != 3 * len(expect):
            print("FAIL case %d: %d instructions, expected %d\n%s" % (n, len(words) // 3, len(expect), src))
            fails += 1
            continue
        for ip, exp in enumerate(expect):
            got = decode(*words[ip * 3:ip * 3 + 3])
            bad = {k: (v, got[k]) for k, v in exp.items() if got[k] != v}
            if bad:
                print("FAIL case %d ip %d: %s\n%s" % (n, ip, ", ".join(
                    "%s expected %#x got %#x" % (k, e, g) for k, (e, g) in bad.items()), src))
                fails += 1

    for n, (src, msg) in enumerate(ERRORS):
        words, err = assemble(args.dekomme, src, work, "err%d" % n)
        if words is not None or msg not in err:
            print("FAIL error case %d: expected '%s', got %s\n%s" % (
                n, msg, "success" if words is not None else repr(err), src))
            fails += 1

    for fn in os.listdir(work):
        os.unlink(os.path.join(work, fn))
    os.rmdir(work)
    total = len(CASES) + len(ERRORS)
    print("tu104 encoding tests: %d/%d passed (%d encoding cases, %d diagnostics)" % (
        total - fails, total, len(CASES), len(ERRORS)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Behavioural test for drako3d's tu104 MME macros.

Usage: drako_macros.py --drako DRAKO3D_DIR --sim TU104_SIM
                       [--drakomme PATH] [--drakodef PATH] [-v]
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MME_FILES = ["clear_buffers.mme", "draw.mme", "pgraph.mme", "program.mme", "state.mme", "utils.mme"]


def build(args, tmp):
    amp = os.path.join(args.drako, "source", "ampere")
    sym = os.path.join(tmp, "engine_3d.mme")
    hdr = os.path.join(tmp, "mme_macros.h")
    subprocess.run([args.drakodef, "-h", os.path.join(tmp, "engine_3d.h"), "-m", sym,
                    os.path.join(amp, "engine_3d.def")], check=True)
    subprocess.run([args.drakomme, "--isa=turing", "-o", hdr, sym] +
                   [os.path.join(amp, f) for f in MME_FILES], check=True)
    text = open(hdr).read()
    slots = {m.group(1): (int(m.group(2), 16) - 0xE00) // 2
             for m in re.finditer(r"MmeMacro(\w+) = (0x[0-9a-f]+),", text)}
    words = [int(w, 16) for w in re.findall(r"0x([0-9A-F]{8}),", text)]
    assert words[0] & 0xFFF == 0x045 and words[1] == 0
    ncode = ((words[0] >> 16) & 0x1FFF) - 1
    code = words[2:2 + ncode]
    rest = words[2 + ncode:]
    assert rest[0] & 0xFFF == 0x047 and rest[1] == 0
    starts = rest[2:2 + ((rest[0] >> 16) & 0x1FFF) - 1]
    return code, {name: starts[i] for name, i in slots.items()}


class Runner:
    def __init__(self, sim, code, starts, verbose):
        self.sim, self.code, self.starts, self.verbose = sim, code, starts, verbose
        self.failures = 0
        self.count = 0

    def run(self, name, params, state=None, hooks=()):
        lines = ["code " + " ".join("0x%08X" % w for w in self.code),
                 "start %d" % self.starts[name]]
        for m, v in (state or {}).items():
            lines.append("state %X %X" % (m, v & 0xFFFFFFFF))
        for m, t, v in hooks:
            lines.append("onwrite %X %X %X" % (m, t, v))
        lines.append("param " + " ".join("0x%X" % (p & 0xFFFFFFFF) for p in params))
        lines.append("run")
        res = subprocess.run([self.sim], input="\n".join(lines) + "\n",
                             capture_output=True, text=True, timeout=10)
        writes, unused = [], None
        for line in res.stdout.splitlines():
            f = line.split()
            if f[0] == "M":
                writes.append((int(f[1], 16), int(f[2], 16)))
            elif f[0] == "END":
                unused = int(f[1])
            elif f[0] == "ERR":
                return None, line
        if res.returncode != 0 or unused is None:
            return None, "simulator failed (rc=%d): %s" % (res.returncode, res.stderr.strip()[-300:])
        return writes, unused

    def check(self, desc, name, params, expected, state=None, hooks=()):
        self.count += 1
        writes, unused = self.run(name, params, state, hooks)
        ok = writes is not None and unused == 0 and writes == expected
        if not ok:
            self.failures += 1
            print("FAIL %s" % desc)
            if writes is None:
                print("    %s" % unused)
            else:
                if unused:
                    print("    %d parameter(s) left unconsumed" % unused)
                print("    expected: %s" % fmt(expected))
                print("    got:      %s" % fmt(writes))
        elif self.verbose:
            print("ok   %s" % desc)


def fmt(writes):
    return " ".join("%03X=%X" % w for w in writes)


NoOperation, WaitForIdle = 0x040, 0x044
Unknown0bb = 0x0BB
RenderTargetNArrayMode = 0x206
DrawArraysFirst, DrawArraysCount = 0x35D, 0x35E
ZcullStencilCriteria = 0x376
VertexIdBase = 0x446
SetConservativeRasterEnable = 0x452
DepthTargetArrayMode = 0x48C
InvalidateZcullNoWfi = 0x4B2
DepthTestEnable, DepthWriteEnable, DepthTestFunc = 0x4B3, 0x4BA, 0x4C3
ColorBlendEnable = 0x4D8
StencilEnable = 0x4E0
DrawBaseVertex, DrawBaseInstance = 0x50D, 0x50E
StencilBackOpFail = 0x566
VertexEndGl, VertexBeginGl = 0x585, 0x586
DrawElementsFirst, DrawElementsCount = 0x5F7, 0x5F8
ColorLogicOpEnable = 0x671
ClearBuffers = 0x674
ColorWriteMask = 0x680
SetProgram = 0x800
FirmwareCall = 0x8C0
ConstbufSelectorSize, LoadConstbufOffset, LoadConstbufData = 0x8E0, 0x8E3, 0x8E4
BindNConstbuf = 0x904
MmeFirmwareArgs = 0xD00
MmeDriverConstbufIova, MmeDriverConstbufSize = 0xD18, 0xD19
MmeProgramIds, MmeProgramOffsets = 0xD1A, 0xD20
MmeDepthRenderTargetIova, MmeStencilCullCriteria, MmeConservativeRasterDilateEnabled = 0xD26, 0xD27, 0xD28
MmeProgramRegion = 0xD29
CbufBaseVertex, CbufBaseInstance = 0x640, 0x644
InstanceNext = 1 << 26


def test_clears(r):
    for rt, layers, extra in ((0, 1, 0), (3, 4, 0), (7, 6, 1 << 16), (2, 0, 0)):
        arg = 0x3C | (rt << 6)
        exp = [(ClearBuffers, arg + (i << 10)) for i in range(layers)]
        r.check("ClearColor rt=%d layers=%d" % (rt, layers), "ClearColor", [arg], exp,
                {RenderTargetNArrayMode + 16 * rt: layers | extra,
                 RenderTargetNArrayMode + 16 * ((rt + 1) % 8): 9})
    for layers in (1, 3, 0):
        exp = [(ClearBuffers, 0x3 + (i << 10)) for i in range(layers)]
        r.check("ClearDepthStencil layers=%d" % layers, "ClearDepthStencil", [0x3], exp,
                {DepthTargetArrayMode: layers})

    r.check("ConditionalZcullInvalidate unchanged", "ConditionalZcullInvalidate", [0x123456], [],
            {MmeDepthRenderTargetIova: 0x123456})
    r.check("ConditionalZcullInvalidate changed", "ConditionalZcullInvalidate", [0x123456],
            [(MmeDepthRenderTargetIova, 0x123456), (InvalidateZcullNoWfi, 0x19)],
            {MmeDepthRenderTargetIova: 0xFFFFFFFF})


def draw_loop(begin, count_mthd, count, instances):
    out = []
    for i in range(instances):
        b = begin if i == 0 else (begin & ~(3 << 26)) | InstanceNext
        out += [(VertexBeginGl, b), (count_mthd, count), (VertexEndGl, 0)]
    return out


def test_draws(r):
    prim = 0x4
    r.check("Draw single", "Draw", [prim, 3, 1, 0, 0],
            [(DrawArraysFirst, 0), (DrawBaseInstance, 0)] + draw_loop(prim, DrawArraysCount, 3, 1))
    r.check("Draw first vertex", "Draw", [prim, 3, 1, 5, 0],
            [(DrawArraysFirst, 5), (DrawBaseInstance, 0),
             (LoadConstbufOffset, CbufBaseInstance), (LoadConstbufData, 0), (LoadConstbufData + 1, 0),
             (LoadConstbufData + 2, 5)] +
            draw_loop(prim, DrawArraysCount, 3, 1) +
            [(LoadConstbufOffset, CbufBaseInstance), (LoadConstbufData, 0), (LoadConstbufData + 1, 0),
             (LoadConstbufData + 2, 0)])
    r.check("Draw instanced", "Draw", [prim, 6, 3, 0, 0],
            [(DrawArraysFirst, 0), (DrawBaseInstance, 0)] + draw_loop(prim, DrawArraysCount, 6, 3))
    r.check("Draw base instance", "Draw", [prim | (3 << 26), 6, 2, 1, 7],
            [(DrawArraysFirst, 1), (DrawBaseInstance, 7),
             (LoadConstbufOffset, CbufBaseInstance), (LoadConstbufData, 7), (LoadConstbufData + 1, 0),
             (LoadConstbufData + 2, 1)] +
            draw_loop(prim | (3 << 26), DrawArraysCount, 6, 2) +
            [(LoadConstbufOffset, CbufBaseInstance), (LoadConstbufData, 0), (LoadConstbufData + 1, 0),
             (LoadConstbufData + 2, 0)])
    r.check("Draw zero instances", "Draw", [prim, 3, 0, 5, 9], [(DrawArraysFirst, 5)])

    r.check("DrawIndexed single", "DrawIndexed", [prim, 36, 1, 10, 0, 0],
            [(DrawElementsFirst, 10), (DrawBaseVertex, 0), (DrawBaseInstance, 0), (VertexIdBase, 0)] +
            draw_loop(prim, DrawElementsCount, 36, 1) +
            [(DrawBaseVertex, 0), (VertexIdBase, 0)])
    r.check("DrawIndexed base vertex/instance", "DrawIndexed", [prim, 36, 2, 10, 100, 3],
            [(DrawElementsFirst, 10), (DrawBaseVertex, 100), (DrawBaseInstance, 3), (VertexIdBase, 100),
             (LoadConstbufOffset, CbufBaseVertex), (LoadConstbufData, 100), (LoadConstbufData + 1, 3),
             (LoadConstbufData + 2, 0), (LoadConstbufData + 3, 100)] +
            draw_loop(prim, DrawElementsCount, 36, 2) +
            [(LoadConstbufOffset, CbufBaseVertex), (LoadConstbufData, 0), (LoadConstbufData + 1, 0),
             (LoadConstbufData + 2, 0), (LoadConstbufData + 3, 0), (DrawBaseVertex, 0), (VertexIdBase, 0)])
    r.check("DrawIndexed zero instances", "DrawIndexed", [prim, 36, 0, 10, 100, 3], [(DrawElementsFirst, 10)])


def test_pgraph(r):
    fw_done = [(FirmwareCall + 4, MmeFirmwareArgs, 1)]
    r.check("WriteHardwareReg", "WriteHardwareReg", [0x418800, 0x1, 0x3],
            [(WaitForIdle, 0), (MmeFirmwareArgs, 0), (MmeFirmwareArgs + 1, 1), (MmeFirmwareArgs + 2, 3),
             (FirmwareCall + 4, 0x418800), (NoOperation, 0)],
            {MmeFirmwareArgs: 1}, fw_done)

    writes, unused = r.run("WriteHardwareReg", [0x418800, 0x1, 0x3], {MmeFirmwareArgs: 1})
    r.count += 1
    if writes is not None or "runaway" not in unused:
        r.failures += 1
        print("FAIL WriteHardwareReg must keep polling until the firmware reports completion")
    elif r.verbose:
        print("ok   WriteHardwareReg polls without a firmware response")


def test_program(r):
    r.check("SelectDriverConstbuf", "SelectDriverConstbuf", [0x190],
            [(ConstbufSelectorSize, 0x7000), (ConstbufSelectorSize + 1, 0x01), (ConstbufSelectorSize + 2, 0x23456700),
             (LoadConstbufOffset, 0x640)],
            {MmeDriverConstbufIova: 0x01234567, MmeDriverConstbufSize: 0x7000})

    region = {MmeProgramRegion: 0x1, MmeProgramRegion + 1: 0xFFFFFF00}

    def prog(stage, pid, offset, gprs, hi=0x2, lo=None):
        lo = (0xFFFFFF00 + offset) & 0xFFFFFFFF if lo is None else lo
        base = SetProgram + 16 * stage
        return [(MmeProgramIds + stage, pid), (MmeProgramOffsets + stage, offset),
                (base, 1 | (stage << 4)), (base + 3, gprs), (base + 5, hi), (base + 6, lo)]

    r.check("BindProgram VertexB with cbuf (address carry)", "BindProgram", [1, 5, 0x200, 24, 0x100, 0xABCDEF],
            prog(1, 5, 0x200, 24) +
            [(ConstbufSelectorSize, 0x100), (ConstbufSelectorSize + 1, 0x00), (ConstbufSelectorSize + 2, 0xABCDEF00),
             (BindNConstbuf, 0x11)], region)
    r.check("BindProgram Fragment without cbuf", "BindProgram", [5, 9, 0x40, 32, 0, 0],
            prog(5, 9, 0x40, 32, hi=0x1, lo=0xFFFFFF40) + [(BindNConstbuf + 4 * 8, 0x10)], region)
    r.check("BindProgram VertexA", "BindProgram", [0, 3, 0x80, 16],
            prog(0, 3, 0x80, 16, hi=0x1, lo=0xFFFFFF80), region)
    r.check("BindProgram VertexB same program", "BindProgram", [1, 5, 0x200, 24, 0x100, 0xABCDEF],
            [(SetProgram + 16, 0x11)], {**region, MmeProgramIds + 1: 5})
    r.check("BindProgram VertexA same program", "BindProgram", [0, 3, 0x80, 16],
            [(SetProgram, 0x01)], {**region, MmeProgramIds: 3})
    r.check("BindProgram other stage's id does not matter", "BindProgram", [4, 3, 0x80, 16, 0x10, 0x1],
            prog(4, 3, 0x80, 16, hi=0x1, lo=0xFFFFFF80) +
            [(ConstbufSelectorSize, 0x10), (ConstbufSelectorSize + 1, 0), (ConstbufSelectorSize + 2, 0x100),
             (BindNConstbuf + 3 * 8, 0x11)],
            {**region, MmeProgramIds + 3: 3})


def test_state(r):
    for mask in (0x00, 0xA5, 0xFF, 0x80):
        r.check("BindColorBlendEnableState 0x%02X" % mask, "BindColorBlendEnableState", [mask],
                [(ColorLogicOpEnable, 0)] + [(ColorBlendEnable + i, (mask >> i) & 1) for i in range(8)])

    def cwm(n):
        return (n & 1) | ((n >> 1) & 1) << 4 | ((n >> 2) & 1) << 8 | ((n >> 3) & 1) << 12
    for masks in (0xFFFFFFFF, 0x12345678, 0x0000000F, 0x9ABCDEF0):
        r.check("BindColorWriteMasks 0x%08X" % masks, "BindColorWriteMasks", [masks],
                [(ColorWriteMask + i, cwm(masks >> (4 * i))) for i in range(8)])

    def ds(depth, write, stencil, func):
        return depth | write << 1 | stencil << 2 | func << 4
    sw = 0x87654321
    stencil_writes = [(StencilEnable + 1, 0x1), (StencilEnable + 2, 0x3), (StencilEnable + 3, 0x2), (StencilEnable + 4, 0x4),
                      (StencilBackOpFail, 0x5), (StencilBackOpFail + 1, 0x7), (StencilBackOpFail + 2, 0x6),
                      (StencilBackOpFail + 3, 0x8)]
    r.check("BindDepthStencilState depth+stencil", "BindDepthStencilState", [ds(1, 1, 1, 4), sw],
            [(DepthTestEnable, 1), (DepthWriteEnable, 1), (DepthTestFunc, 4), (StencilEnable, 1)] + stencil_writes)
    r.check("BindDepthStencilState depth only, no write", "BindDepthStencilState", [ds(1, 0, 0, 7), sw],
            [(DepthTestEnable, 1), (DepthWriteEnable, 0), (DepthTestFunc, 7), (StencilEnable, 0)])
    r.check("BindDepthStencilState stencil only", "BindDepthStencilState", [ds(0, 1, 1, 2), sw],
            [(DepthTestEnable, 0), (StencilEnable, 1)] + stencil_writes)
    r.check("BindDepthStencilState none", "BindDepthStencilState", [ds(0, 0, 0, 0), sw],
            [(DepthTestEnable, 0), (StencilEnable, 0)])

    r.check("SetStencilCullCriteria unchanged", "SetStencilCullCriteria", [0xFF0080],
            [], {MmeStencilCullCriteria: 0xFF0080})
    r.check("SetStencilCullCriteria changed", "SetStencilCullCriteria", [0xFF0080],
            [(ZcullStencilCriteria, 0xFF0080), (MmeStencilCullCriteria, 0xFF0080)], {MmeStencilCullCriteria: 0})

    for en, dil, out in ((1, 1, 0x10), (1, 0, 0), (0, 1, 0), (0, 0, 0)):
        r.check("UpdateConservativeRaster enable=%d dilate=%d" % (en, dil), "UpdateConservativeRaster", [0],
                [(Unknown0bb, out)], {SetConservativeRasterEnable: en, MmeConservativeRasterDilateEnabled: dil})


def test_utils(r):
    r.check("FillRegisters incr 1", "FillRegisters", [0x180 | (1 << 12), 4, 0],
            [(0x180 + i, 0) for i in range(4)])
    r.check("FillRegisters incr 8", "FillRegisters", [0x900 | (8 << 12), 5, 0x10],
            [(0x900 + 8 * i, 0x10) for i in range(5)])
    r.check("FillRegisters single", "FillRegisters", [0x47C, 1, 0xFFFF], [(0x47C, 0xFFFF)])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drako", required=True)
    ap.add_argument("--sim", required=True)
    ap.add_argument("--drakomme", default=os.path.join(HERE, "..", "build", "drakomme"))
    ap.add_argument("--drakodef", default=os.path.join(HERE, "..", "build", "drakodef"))
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        code, starts = build(args, tmp)
    r = Runner(args.sim, code, starts, args.verbose)
    for t in (test_clears, test_draws, test_pgraph, test_program, test_state, test_utils):
        t(r)
    print("drako3d tu104 macros: %d/%d passed (%d instructions, %d macros)" %
          (r.count - r.failures, r.count, len(code) // 3, len(starts)))
    return 1 if r.failures else 0


if __name__ == "__main__":
    sys.exit(main())

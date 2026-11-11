#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "MmeTuringDocument.h"

#include "MmeTuringParser.hpp"
#define yyscan_t mmetu_scan_t
#define YYSTYPE MMETU_STYPE
#define YYLTYPE MMETU_LTYPE
#include "MmeTuringLexer.hpp"

using namespace mme::tu104;

namespace
{
	const char* const predNames[] =
	{
		"UUUU", "TTTT", "FFFF", "TTUU", "FFUU", "TFUU", "TUUU", "FUUU",
		"UUTT", "UUTF", "UUTU", "UUFT", "UUFF", "UUFU", "UUUT", "UUUF",
	};

	struct ImmAllocator
	{
		uint16_t imm[2] = { 0, 0 };
		bool used[2] = { false, false };
		bool fixed[2] = { false, false };

		int Alloc16(uint16_t value)
		{
			for (int k = 0; k < 2; k ++)
				if (!used[k])
				{
					used[k] = true;
					imm[k] = value;
					return k;
				}

			for (int k = 0; k < 2; k ++)
				if (!fixed[k] && imm[k] == value)
					return k;
			return -1;
		}

		bool Alloc32(uint32_t value)
		{
			if (!used[0] && !used[1])
			{
				used[0] = used[1] = true;
				imm[0] = value >> 16;
				imm[1] = value;
				return true;
			}
			return used[0] && used[1] && !fixed[0] && !fixed[1] &&
				((uint32_t(imm[0]) << 16) | imm[1]) == value;
		}
	};

	bool UsesLoad(const Instruction& inst, int which)
	{
		int32_t reg = which ? Load1 : Load0;
		OutOp out = which ? OutOp::Load1 : OutOp::Load0;
		if (inst.predMode != Pred::UUUU && inst.pred == reg)
			return true;
		for (int a = 0; a < 2; a ++)
			if (inst.alu[a].src[0] == reg || inst.alu[a].src[1] == reg)
				return true;
		for (int o = 0; o < 2; o ++)
			if (inst.out[o].mthd == out || inst.out[o].emit == out)
				return true;
		return false;
	}
}

void mmetu_error(MMETU_LTYPE *llocp, mmetu_scan_t scanner, MmeTuringDocument& doc, char const* curFile, char const *msg)
{
	fprintf(stderr, "%s:%d:%d: %s\n", curFile, llocp->first_line, llocp->first_column, msg);
	fprintf(stderr, "%s:%d:%d: (error ends here)\n", curFile, llocp->last_line, llocp->last_column);
}

bool MmeTuringDocument::ResolveLabels(std::map<std::string, size_t>& labels, std::vector<LabelRef>& refs)
{
	for (auto& ref : refs)
	{
		auto it = labels.find(ref.name);
		if (it == labels.end())
		{
			fprintf(stderr, "Undefined reference to %s\n", ref.name.c_str());
			return false;
		}
		m_controlFlow[ref.cf].target = int32_t(it->second);
	}
	refs.clear();
	return true;
}

bool MmeTuringDocument::ResolveLocalLabels()
{
	bool ok = ResolveLabels(m_localLabels, m_localLabelRefs);
	m_localLabels.clear();
	return ok;
}

bool MmeTuringDocument::ResolveLabels()
{
	return ResolveLabels(m_labels, m_labelRefs);
}

bool MmeTuringDocument::Encode()
{
	size_t first = m_code.size() / 3;

	for (auto& cf : m_controlFlow)
	{
		if (cf.inst < first)
			continue;
		Instruction& inst = m_insts[cf.inst];
		AluOp op = inst.alu[cf.alu].op;
		int32_t offset = cf.target - int32_t(cf.inst);
		uint32_t imm;
		if (IsBranch(op))
		{
			imm = inst.imm[cf.alu] & BranchExpectBit;
			if (inst.endNext)
				imm |= BranchEndNextBit;
			if (cf.kind == MmeTuringTarget::Exit)
				imm |= BranchExitOffset;
			else if (offset < -0xFFF || offset > 0xFFF)
			{
				fprintf(stderr, "Branch target out of range at instruction %u\n", unsigned(cf.inst));
				return false;
			}
			else
				imm |= uint32_t(offset) & BranchOffsetMask;
		}
		else if (op == AluOp::JumpAndLink)
		{
			if (offset < 0 || offset > int32_t(JalOffsetMask))
			{
				fprintf(stderr, "JAL target out of range at instruction %u (must be forward)\n", unsigned(cf.inst));
				return false;
			}
			imm = JalBit | uint32_t(offset);
		}
		else
		{
			if (offset < 2 || offset > 0xFFFF)
			{
				fprintf(stderr, "LOOP end out of range at instruction %u (body must be at least one instruction)\n", unsigned(cf.inst));
				return false;
			}
			imm = uint32_t(offset);
		}
		inst.imm[cf.alu] = imm;
	}

	for (size_t i = first; i < m_insts.size(); i ++)
	{
		uint32_t words[3];
		m_insts[i].Encode(words);
		for (int j = 0; j < 3; j ++)
			m_code.push_back(int32_t(words[j]));
	}
	return true;
}

bool MmeTuringDocument::Load(const char* fileName)
{
	FILE* fin = fopen(fileName, "r");
	if (!fin)
	{
		fprintf(stderr, "%s: couldn't open file\n", fileName);
		return false;
	}

	mmetu_scan_t scanner;
	mmetu_lex_init(&scanner);
	mmetu_set_in(fin, scanner);
	int ret = mmetu_parse(scanner, *this, fileName);
	mmetu_lex_destroy(scanner);
	fclose(fin);

	if (ret==0)
		return ResolveLocalLabels() && ResolveLabels() && Encode();

	return false;
}

bool MmeTuringDocument::VisitLocalLabel(std::string&& ident)
{
	auto ret = m_localLabels.emplace( std::move(ident), m_insts.size() );
	return ret.second;
}

bool MmeTuringDocument::VisitLabel(std::string&& ident, bool exported)
{
	if (!ResolveLocalLabels())
		return false;
	auto ret = m_labels.emplace( std::move(ident), m_insts.size() );
	if (ret.second && exported)
		m_exports.push_back(ret.first);
	m_scopeBase = m_insts.size();
	return ret.second;
}

const char* MmeTuringDocument::VisitPredicate(std::string&& mode, int32_t reg)
{
	std::transform(mode.begin(), mode.end(), mode.begin(), [](char ch) -> char {
		return ch >= 'a' && ch <= 'z' ? ch - 'a' + 'A' : ch;
	});
	for (int i = 0; i < 16; i ++)
		if (mode == predNames[i])
		{
			m_curPredMode = Pred(i);
			m_curPred = reg;
			return nullptr;
		}
	return "unknown predicate mode (expected 4 of T/F/U)";
}

const char* MmeTuringDocument::VisitAlu(MmeTuringAlu* alu)
{
	MmeTuringAlu::Ptr ptr(alu);
	if (IsControlFlow(alu->op) && (alu->dst != Zero || alu->slot >= 0))
		return "control flow operations cannot have a destination";
	if (m_curAlus.size() >= 2)
		return "too many ALU operations in one instruction (max 2)";
	m_curAlus.push_back(std::move(ptr));
	return nullptr;
}

const char* MmeTuringDocument::VisitOut(bool isMthd, MmeTuringOperand src)
{
	m_curOuts.push_back(OutItem{ isMthd, src });
	return nullptr;
}

const char* MmeTuringDocument::VisitInstruction(bool endNext)
{
	auto alus = std::move(m_curAlus);
	auto outs = std::move(m_curOuts);
	m_curAlus.clear();
	m_curOuts.clear();

	Instruction inst;
	inst.endNext = endNext;
	inst.predMode = m_curPredMode;
	inst.pred = m_curPred;
	m_curPredMode = Pred::UUUU;
	m_curPred = Zero;

	MmeTuringAlu* slots[2] = { nullptr, nullptr };
	for (auto& a : alus)
		if (a->slot >= 0)
		{
			if (slots[a->slot])
				return "ALU slot used twice in one instruction";
			slots[a->slot] = a.get();
		}
	for (auto& a : alus)
		if (a->slot < 0 && (MustBeAlu0(a->op) || MustBeAlu1(a->op)))
		{
			a->slot = MustBeAlu1(a->op) ? 1 : 0;
			if (slots[a->slot])
				return a->slot ? "ADDC/SUBB/MULH must be in alu1, which is already used" : "control flow must be in alu0, which is already used";
			slots[a->slot] = a.get();
		}
	for (auto& a : alus)
		if (a->slot < 0)
		{
			a->slot = slots[0] ? 1 : 0;
			slots[a->slot] = a.get();
		}

	for (int s = 0; s < 2; s ++)
	{
		if (!slots[s])
			continue;
		if (MustBeAlu1(slots[s]->op) && s != 1)
			return "ADDC/SUBB/MULH can only be used in alu1";
		if (MustBeAlu0(slots[s]->op) && s != 0)
			return "control flow can only be used in alu0";
	}
	if (slots[0] && slots[1] && slots[0]->op == AluOp::State && slots[1]->op == AluOp::State)
		return "only one STATE read is allowed per instruction";
	if (slots[1] && slots[1]->op == AluOp::AddCarry && !(slots[0] && slots[0]->op == AluOp::Add))
		return "ADDC requires an ADD in alu0";
	if (slots[1] && slots[1]->op == AluOp::SubBorrow && !(slots[0] && slots[0]->op == AluOp::Sub))
		return "SUBB requires a SUB in alu0";

	struct { const OutItem* mthd; const OutItem* emit; } oslots[2] = { { nullptr, nullptr }, { nullptr, nullptr } };
	int cur = -1;
	for (auto& it : outs)
	{
		if (cur < 0 || (it.isMthd ? (oslots[cur].mthd || oslots[cur].emit) : oslots[cur].emit != nullptr))
			if (++cur >= 2)
				return "too many mthd/emit operations in one instruction (max 2 of each)";
		(it.isMthd ? oslots[cur].mthd : oslots[cur].emit) = &it;
	}

	ImmAllocator ia;
	for (int s = 0; s < 2; s ++)
	{
		if (!slots[s])
			continue;
		inst.alu[s].op = slots[s]->op;
		inst.alu[s].dst = slots[s]->dst;
		for (int i = 0; i < 2; i ++)
			inst.alu[s].src[i] = slots[s]->src[i].isImm ? Zero : slots[s]->src[i].value;
		if (HasImplicitImm(slots[s]->op))
		{
			ia.used[s] = ia.fixed[s] = true;
			ia.imm[s] = slots[s]->implicitImm;
		}
	}

	auto aluHasImm = [&slots](int s) -> bool
	{
		return slots[s] && (slots[s]->src[0].isImm || slots[s]->src[1].isImm);
	};

	auto usesImmAlu = [&aluHasImm](const OutItem* it) -> bool
	{
		return it && !it->src.isImm &&
			((it->src.value == int32_t(OutOp::Alu0) && aluHasImm(0)) ||
			 (it->src.value == int32_t(OutOp::Alu1) && aluHasImm(1)));
	};

	auto allocAlus = [&]() -> const char*
	{
		for (int s = 0; s < 2; s ++)
			for (int i = 0; slots[s] && i < 2; i ++)
			{
				if (!slots[s]->src[i].isImm)
					continue;
				int32_t value = slots[s]->src[i].value;
				if (value == int16_t(value))
				{
					int k = ia.Alloc16(uint16_t(value));
					if (k < 0)
						return "out of immediate slots";
					inst.alu[s].src[i] = k == s ? Imm : ImmPair;
				}
				else
				{
					if (!ia.Alloc32(uint32_t(value)))
						return "out of immediate slots (32-bit immediates use both)";
					inst.alu[s].src[i] = Imm32;
				}
			}
		return nullptr;
	};

	bool alusDone = false;
	for (int o = 0; o < 2; o ++)
	{
		const OutItem* mthd = oslots[o].mthd;
		const OutItem* emit = oslots[o].emit;
		if (!mthd && !emit)
			continue;

		if (!alusDone && ((mthd && !emit) || usesImmAlu(mthd) || usesImmAlu(emit)))
		{
			if (const char* err = allocAlus())
				return err;
			alusDone = true;
		}

		int mthdSlot = -1;
		if (mthd)
		{
			if (mthd->src.isImm)
			{
				mthdSlot = ia.Alloc16(uint16_t(mthd->src.value));
				if (mthdSlot < 0)
					return "out of immediate slots";
				inst.out[o].mthd = OutOp(int32_t(OutOp::Imm0) + mthdSlot);
			}
			else
				inst.out[o].mthd = OutOp(mthd->src.value);
		}

		if (emit)
		{
			if (emit->src.isImm)
			{
				uint32_t value = uint32_t(emit->src.value);
				if (mthdSlot >= 0 && uint32_t(ia.imm[mthdSlot] >> 12) == value)
					// Small values can ride along in the incr bits of the method
					inst.out[o].emit = OutOp(int32_t(OutOp::ImmHigh0) + mthdSlot);
				else if (value <= 0xFFFF)
				{
					int k = ia.Alloc16(uint16_t(value));
					if (k >= 0)
						inst.out[o].emit = OutOp(int32_t(OutOp::Imm0) + k);
					else if (value <= 0xF && (ia.imm[0] >> 12) == value)
						inst.out[o].emit = OutOp::ImmHigh0;
					else if (value <= 0xF && (ia.imm[1] >> 12) == value)
						inst.out[o].emit = OutOp::ImmHigh1;
					else
						return "out of immediate slots";
				}
				else
				{
					if (!ia.Alloc32(value))
						return "out of immediate slots (32-bit immediates use both)";
					inst.out[o].emit = OutOp::Imm32;
				}
			}
			else
				inst.out[o].emit = OutOp(emit->src.value);
		}
	}

	if (!alusDone)
		if (const char* err = allocAlus())
			return err;

	inst.imm[0] = ia.imm[0];
	inst.imm[1] = ia.imm[1];

	if (UsesLoad(inst, 1) && !UsesLoad(inst, 0))
		return "$load1 cannot be used without $load0 in the same instruction";

	for (int s = 0; s < 2; s ++)
	{
		if (!slots[s] || !IsControlFlow(slots[s]->op))
			continue;
		MmeTuringTarget& target = *slots[s]->target;
		if (target.kind == MmeTuringTarget::Exit && !IsBranch(slots[s]->op))
			return "EXIT is only valid as a branch target";
		ControlFlow cf = { m_insts.size(), s, target.kind, 0 };
		if (target.kind == MmeTuringTarget::Ip)
			cf.target = int32_t(m_scopeBase) + target.ip;
		else if (target.kind == MmeTuringTarget::Label)
			m_labelRefs.push_back(LabelRef{ m_controlFlow.size(), std::move(target.name) });
		else if (target.kind == MmeTuringTarget::LocalLabel)
			m_localLabelRefs.push_back(LabelRef{ m_controlFlow.size(), std::move(target.name) });
		m_controlFlow.push_back(cf);
	}

	m_insts.push_back(inst);
	return nullptr;
}

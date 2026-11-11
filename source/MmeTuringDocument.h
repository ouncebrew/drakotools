#pragma once
#include "MmeDocument.h"
#include "MmeTuringDefinitions.h"

struct MmeTuringOperand
{
	bool isImm;
	int32_t value;
};

struct MmeTuringTarget
{
	enum Kind { Label, LocalLabel, Ip, Exit };
	Kind kind;
	std::string name;
	int32_t ip;

	MmeTuringTarget(Kind kind, std::string&& name = std::string(), int32_t ip = 0)
		: kind(kind), name(name), ip(ip) { }
};

struct MmeTuringAlu
{
	typedef std::unique_ptr<MmeTuringAlu> Ptr;
	mme::tu104::AluOp op;
	int32_t dst = mme::tu104::Zero;
	int slot = -1;
	MmeTuringOperand src[2] = { { false, mme::tu104::Zero }, { false, mme::tu104::Zero } };
	uint32_t implicitImm = 0;
	std::unique_ptr<MmeTuringTarget> target;

	MmeTuringAlu(mme::tu104::AluOp op) : op(op) { }
};

class MmeTuringDocument : public MmeDocumentBase
{
	struct OutItem
	{
		bool isMthd;
		MmeTuringOperand src;
	};

	struct ControlFlow
	{
		size_t inst;
		int alu;
		MmeTuringTarget::Kind kind;
		int32_t target;
	};

	struct LabelRef
	{
		size_t cf;
		std::string name;
	};

	std::vector<mme::tu104::Instruction> m_insts;
	std::vector<ControlFlow> m_controlFlow;
	std::map<std::string, size_t> m_localLabels;
	std::vector<LabelRef> m_localLabelRefs;
	std::vector<LabelRef> m_labelRefs;
	size_t m_scopeBase = 0;

	std::vector<MmeTuringAlu::Ptr> m_curAlus;
	std::vector<OutItem> m_curOuts;
	mme::tu104::Pred m_curPredMode = mme::tu104::Pred::UUUU;
	int32_t m_curPred = mme::tu104::Zero;

	bool ResolveLabels(std::map<std::string, size_t>& labels, std::vector<LabelRef>& refs);
	bool ResolveLocalLabels();
	bool ResolveLabels();
	bool Encode();

public:
	bool Load(const char* fileName) override;

	bool VisitLocalLabel(std::string&& ident);
	bool VisitLabel(std::string&& ident, bool exported);
	const char* VisitPredicate(std::string&& mode, int32_t reg);
	const char* VisitAlu(MmeTuringAlu* alu);
	const char* VisitOut(bool isMthd, MmeTuringOperand src);
	const char* VisitInstruction(bool endNext);
	int32_t ScopeBase() const { return int32_t(m_scopeBase); }
};

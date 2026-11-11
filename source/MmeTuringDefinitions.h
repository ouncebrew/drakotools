#pragma once
#include <stdint.h>

namespace mme {
namespace tu104
{
	enum class Pred : int32_t
	{
		UUUU = 0, TTTT = 1, FFFF = 2, TTUU = 3,
		FFUU = 4, TFUU = 5, TUUU = 6, FUUU = 7,
		UUTT = 8, UUTF = 9, UUTU = 10, UUFT = 11,
		UUFF = 12, UUFU = 13, UUUT = 14, UUUF = 15,
	};

	enum Reg : int32_t
	{
		NumGprs = 24,
		Zero    = 24,
		Imm     = 25,
		ImmPair = 26,
		Imm32   = 27,
		Load0   = 28,
		Load1   = 29,
	};

	enum class AluOp : int32_t
	{
		Add = 0,
		AddCarry = 1,
		Sub = 2,
		SubBorrow = 3,
		Mul = 4,
		MulHigh = 5,
		MulUnsigned = 6,
		Extended = 7,
		CountLeadingZeros = 8,
		ShiftLeft = 9,
		ShiftRight = 10,
		ShiftRightArith = 11,
		And = 12,
		Nand = 13,
		Or = 14,
		Xor = 15,
		Merge = 16,
		SetLessThan = 17,
		SetLessThanUnsigned = 18,
		SetLessEqual = 19,
		SetLessEqualUnsigned = 20,
		SetEqual = 21,
		State = 22,
		Loop = 23,
		JumpAndLink = 24,
		BranchLessThan = 25,
		BranchLessThanUnsigned = 26,
		BranchLessEqual = 27,
		BranchLessEqualUnsigned = 28,
		BranchEqual = 29,
		DramRead = 30,
		DramWrite = 31,
	};

	enum class OutOp : int32_t
	{
		None = 0,
		Alu0 = 1,
		Alu1 = 2,
		Load0 = 3,
		Load1 = 4,
		Imm0 = 5,
		Imm1 = 6,
		Reserved = 7,
		ImmHigh0 = 8,
		ImmHigh1 = 9,
		Imm32 = 10,
	};

	constexpr uint32_t BranchOffsetMask = 0x1FFF;
	constexpr uint32_t BranchExitOffset = 0x1000;
	constexpr uint32_t BranchEndNextBit = 1U << 14;
	constexpr uint32_t BranchExpectBit  = 1U << 15;
	constexpr uint32_t JalBit           = 1U << 15;
	constexpr uint32_t JalOffsetMask    = 0x7FFF;

	constexpr bool IsControlFlow(AluOp op)
	{
		return op == AluOp::Loop || op == AluOp::JumpAndLink ||
			(op >= AluOp::BranchLessThan && op <= AluOp::BranchEqual);
	}

	constexpr bool IsBranch(AluOp op)
	{
		return op >= AluOp::BranchLessThan && op <= AluOp::BranchEqual;
	}

	constexpr bool HasImplicitImm(AluOp op)
	{
		return op == AluOp::Merge || IsControlFlow(op);
	}

	constexpr bool MustBeAlu1(AluOp op)
	{
		return op == AluOp::AddCarry || op == AluOp::SubBorrow || op == AluOp::MulHigh;
	}

	constexpr bool MustBeAlu0(AluOp op)
	{
		return IsControlFlow(op);
	}

	constexpr uint32_t MakeMergeImm(uint32_t dstPos, uint32_t bits, uint32_t srcPos)
	{
		return ((dstPos & 0x3F) << 10) | ((bits & 0x1F) << 5) | (srcPos & 0x1F);
	}

	struct Alu
	{
		AluOp op = AluOp::Add;
		int32_t dst = Zero;
		int32_t src[2] = { Zero, Zero };
	};

	struct Out
	{
		OutOp mthd = OutOp::None;
		OutOp emit = OutOp::None;
	};

	struct Instruction
	{
		bool endNext = false;
		Pred predMode = Pred::UUUU;
		int32_t pred = Zero;
		uint16_t imm[2] = { 0, 0 };
		Alu alu[2];
		Out out[2];

		void Encode(uint32_t words[3]) const
		{
			uint32_t b[3] = { 0, 0, 0 };
			auto put = [&b](unsigned pos, unsigned size, uint32_t value)
			{
				for (unsigned i = 0; i < size; i ++)
					if (value & (1U << i))
						b[(pos+i)/32] |= 1U << ((pos+i)%32);
			};

			put( 0,  1, endNext);
			put( 1,  4, uint32_t(predMode));
			put( 5,  5, pred);
			put(10,  5, uint32_t(alu[0].op));
			put(15,  5, alu[0].dst);
			put(20,  5, alu[0].src[0]);
			put(25,  5, alu[0].src[1]);
			put(30, 16, imm[0]);
			put(46,  5, uint32_t(alu[1].op));
			put(51,  5, alu[1].dst);
			put(56,  5, alu[1].src[0]);
			put(61,  5, alu[1].src[1]);
			put(66, 16, imm[1]);
			put(82,  3, uint32_t(out[0].mthd));
			put(85,  4, uint32_t(out[0].emit));
			put(89,  3, uint32_t(out[1].mthd));
			put(92,  4, uint32_t(out[1].emit));

			words[0] = b[2];
			words[1] = b[1];
			words[2] = b[0];
		}
	};
}
}

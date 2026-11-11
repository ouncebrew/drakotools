/*
 * Runs one tu104 MME macro in mme_tu104_sim_core and prints every method it sends.
 */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "mme_tu104.h"
#include "mme_tu104_sim.h"

#define MAX_WORDS  (3 * 4096)
#define MAX_PARAMS 4096

static uint32_t code[MAX_WORDS];
static unsigned num_words;
static uint32_t params[MAX_PARAMS];
static unsigned num_params, next_param;
static uint32_t shadow[0x1000];
static uint32_t dram[0x1000];
static struct { unsigned mthd, target, value; } hooks[16];
static unsigned num_hooks;
static unsigned num_writes;

static uint32_t op_load(void *h)
{
	(void)h;
	if (next_param >= num_params) {
		printf("ERR param underflow\n");
		exit(2);
	}
	return params[next_param++];
}

static uint32_t op_state(void *h, uint16_t addr)
{
	(void)h;
	return shadow[(addr / 4) & 0xFFF];
}

static void op_mthd(void *h, uint16_t addr, uint32_t data)
{
	(void)h;
	unsigned m = (addr / 4) & 0xFFF;
	printf("M %03X %08X\n", m, data);
	shadow[m] = data;
	for (unsigned i = 0; i < num_hooks; i++)
		if (hooks[i].mthd == m)
			shadow[hooks[i].target & 0xFFF] = hooks[i].value;
	if (++num_writes > 100000) {
		printf("ERR runaway macro\n");
		exit(2);
	}
}

static void op_barrier(void *h)
{
	(void)h;
}

static uint32_t *op_map_dram(void *h, uint32_t idx)
{
	(void)h;
	return &dram[idx & 0xFFF];
}

const char *P_PARSE_NVC597_MTHD(uint16_t idx)
{
	(void)idx;
	return "";
}

void P_DUMP_NVC597_MTHD_DATA(FILE *fp, uint16_t idx, uint32_t data, const char *prefix)
{
	(void)fp; (void)idx; (void)data; (void)prefix;
}

static const struct mme_sim_state_ops ops = {
	.load = op_load,
	.state = op_state,
	.mthd = op_mthd,
	.barrier = op_barrier,
	.map_dram = op_map_dram,
};

int main(void)
{
	char tok[64];
	unsigned start = 0;
	enum { NONE, CODE, PARAM } mode = NONE;

	while (scanf("%63s", tok) == 1) {
		if (!strcmp(tok, "code"))
			mode = CODE;
		else if (!strcmp(tok, "param"))
			mode = PARAM;
		else if (!strcmp(tok, "start")) {
			mode = NONE;
			if (scanf("%u", &start) != 1)
				return 1;
		} else if (!strcmp(tok, "state")) {
			unsigned m, v;
			mode = NONE;
			if (scanf("%x %x", &m, &v) != 2)
				return 1;
			shadow[m & 0xFFF] = v;
		} else if (!strcmp(tok, "onwrite")) {
			mode = NONE;
			if (num_hooks == 16 || scanf("%x %x %x", &hooks[num_hooks].mthd,
			                             &hooks[num_hooks].target, &hooks[num_hooks].value) != 3)
				return 1;
			num_hooks++;
		} else if (!strcmp(tok, "run"))
			break;
		else {
			uint32_t v = (uint32_t)strtoul(tok, NULL, 0);
			if (mode == CODE && num_words < MAX_WORDS)
				code[num_words++] = v;
			else if (mode == PARAM && num_params < MAX_PARAMS)
				params[num_params++] = v;
			else
				return 1;
		}
	}

	unsigned num_insts = num_words / 3;
	if (start >= num_insts)
		return 1;

	struct mme_tu104_inst *insts = calloc(num_insts, sizeof(*insts));
	mme_tu104_decode(insts, code, num_insts);
	mme_tu104_sim_core(num_insts - start, insts + start, &ops, NULL);
	printf("END %u\n", num_params - next_param);
	return 0;
}

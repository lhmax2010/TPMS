#include "protocol_v4_1.h"

#define X(id, func) register_parser(id, func);
void register_protocol_v4_1()
{
	init_list_v4_1;
}
#undef X

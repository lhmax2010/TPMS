#ifndef __PROTOCOL_V3_0_H__
#define __PROTOCOL_V3_0_H__

#include <stdbool.h>
#include "trace_parser.h"

struct addr_info {
	uint64_t offset;
	const char *map_name;
};

struct probe_info_v3_0_t {
	uint64_t addr;
	uint64_t caller_pc_address;
	uint32_t pid;
	uint32_t tid;
	uint32_t type;
	uint32_t cpu_num;
};

#define MSG_ID_LIST30 \
	X(MSG_PROCESS_INFO_v3_0,		0x0001) \
	X(MSG_TERMINATE_v3_0, 			0x0002) \
	X(MSG_ERROR_v3_0, 			0x0003) \
	X(MSG_SAMPLE_v3_0, 			0x0004) \
	X(MSG_SYSTEM_v3_0, 			0x0005) \
	X(MSG_RECORD_v3_0, 			0x0007) \
	X(MSG_FUNCTION_ENTRY_v3_0, 		0x0008) \
	X(MSG_FUNCTION_EXIT_v3_0, 		0x0009) \
	X(MSG_PROBE_FBI_v3_0, 			0x000a) \
	X(MSG_CONTEXT_SWITCH_ENTRY_v3_0,	0x0010) \
	X(MSG_CONTEXT_SWITCH_EXIT_v3_0, 	0x0011) \
	X(MSG_PROCESS_MAP_v3_0, 		0x0012) \
	X(MSG_PROCESS_UNMAP_v3_0, 		0x0013) \
	X(MSG_PROCESS_COMM_v3_0, 		0x0014) \
	X(MSG_WEB_FUNCTION_ENTRY_v3_0, 		0x0015) \
	X(MSG_WEB_FUNCTION_EXIT_v3_0, 		0x0016) \
	X(MSG_PROBE_MEMORY_v3_0, 		0x0101) \
	X(MSG_PROBE_UICONTROL_v3_0, 		0x0102) \
	X(MSG_PROBE_UIEVENT_v3_0, 		0x0103) \
	X(MSG_PROBE_RESOURCE_v3_0, 		0x0104) \
	X(MSG_PROBE_LIFECYCLE_v3_0, 		0x0105) \
	X(MSG_PROBE_SCREENSHOT_v3_0, 		0x0106) \
	X(MSG_PROBE_SCENE_v3_0, 		0x0107) \
	X(MSG_PROBE_THREAD_v3_0, 		0x0108) \
	X(MSG_PROBE_CUSTOM_v3_0, 		0x0109) \
	X(MSG_PROBE_SYNC_v3_0, 			0x0110) \
	X(MSG_PROBE_NETWORK_v3_0, 		0x0111) \
	X(MSG_PROBE_GL_v3_0, 			0x0112) \
	X(MSG_COMPRESSED_v3_0, 			0xbebe)

#define X(id, val) id = val,
enum msg_id_v3_0{
	MSG_ID_LIST30
};
#undef X

#define init_list_v3_0 \
X(MSG_PROCESS_INFO_v3_0, parse_and_print_process_info_v3_0)\
X(MSG_TERMINATE_v3_0, parse_and_print_terminate_v3_0)\
X(MSG_ERROR_v3_0, parse_and_print_error_v3_0)\
X(MSG_SAMPLE_v3_0, parse_and_print_sample_v3_0)\
X(MSG_SYSTEM_v3_0, parse_and_print_system_v3_0)\
X(MSG_RECORD_v3_0, parse_and_print_record_v3_0)\
X(MSG_FUNCTION_ENTRY_v3_0, parse_and_print_function_entry_v3_0)\
X(MSG_FUNCTION_EXIT_v3_0, parse_and_print_function_exit_v3_0)\
X(MSG_WEB_FUNCTION_ENTRY_v3_0, parse_and_print_web_function_entry_v3_0)\
X(MSG_WEB_FUNCTION_EXIT_v3_0, parse_and_print_web_function_exit_v3_0)\
X(MSG_PROBE_FBI_v3_0, parse_and_print_fbi_v3_0)\
X(MSG_CONTEXT_SWITCH_ENTRY_v3_0, parse_and_print_context_switch_entry_v3_0)\
X(MSG_CONTEXT_SWITCH_EXIT_v3_0, parse_and_print_context_switch_exit_v3_0)\
X(MSG_PROCESS_MAP_v3_0, parse_and_print_proc_map_v3_0)\
X(MSG_PROCESS_UNMAP_v3_0, parse_and_print_proc_unmap_v3_0)\
X(MSG_PROCESS_COMM_v3_0, parse_and_print_proc_comm_v3_0)\
X(MSG_PROBE_MEMORY_v3_0, parse_and_print_probe_memory_v3_0)\
X(MSG_PROBE_UICONTROL_v3_0, parse_and_print_probe_uicontrol_v3_0)\
X(MSG_PROBE_UIEVENT_v3_0, parse_and_print_probe_uievent_v3_0)\
X(MSG_PROBE_RESOURCE_v3_0, parse_and_print_probe_resource_v3_0)\
X(MSG_PROBE_LIFECYCLE_v3_0, parse_and_print_probe_lifecycle_v3_0)\
X(MSG_PROBE_SCREENSHOT_v3_0, parse_and_print_probe_screenshot_v3_0)\
X(MSG_PROBE_SCENE_v3_0, parse_and_print_probe_scene_v3_0)\
X(MSG_PROBE_THREAD_v3_0, parse_and_print_probe_thread_v3_0)\
X(MSG_PROBE_CUSTOM_v3_0, parse_and_print_probe_custom_v3_0)\
X(MSG_PROBE_SYNC_v3_0, parse_and_print_probe_sync_v3_0)\
X(MSG_PROBE_NETWORK_v3_0, parse_and_print_probe_network_v3_0)\
X(MSG_PROBE_GL_v3_0, parse_and_print_probe_gl_v3_0)

#define X(id, func) void func (char *buf, void *b, const struct conversion_base *conv_base);
init_list_v3_0
#undef X

bool addr_info_fill(uint32_t pid, uint64_t addr, struct addr_info *ainfo);
void register_protocol_v3_0();

#endif /* __PROTOCOL_V3_0_H__ */

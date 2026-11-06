#ifndef __PROTOCOL_V4_0_H__
#define __PROTOCOL_V4_0_H__

#include "protocol_v3_0.h"

#define MSG_ID_LIST40 \
	X(MSG_PROCESS_INFO_v4_0,		0x0001) \
	X(MSG_TERMINATE_v4_0,			0x0002) \
	X(MSG_ERROR_v4_0,			0x0003) \
	X(MSG_SAMPLE_v4_0,			0x0004) \
	X(MSG_SYSTEM_v4_0,			0x0005) \
	X(MSG_RECORD_v4_0,			0x0007) \
	X(MSG_FUNCTION_ENTRY_v4_0,		0x0008) \
	X(MSG_FUNCTION_EXIT_v4_0,		0x0009) \
	X(MSG_SYSCALL_ENTRY_v4_0,		0x000a) \
	X(MSG_SYSCALL_EXIT_v4_0,		0x000b) \
	X(MSG_FILE_FUNCTION_ENTRY_v4_0,		0x000c) \
	X(MSG_FILE_FUNCTION_EXIT_v4_0,		0x000d) \
	X(MSG_PROCESS_STATUS_INFO_v4_0,		0x000e) \
	X(MSG_CONTEXT_SWITCH_ENTRY_v4_0,	0x0010) \
	X(MSG_CONTEXT_SWITCH_EXIT_v4_0,		0x0011) \
	X(MSG_PROCESS_MAP_v4_0,			0x0012) \
	X(MSG_PROCESS_UNMAP_v4_0,		0x0013) \
	X(MSG_PROCESS_COMM_v4_0,		0x0014) \
	X(MSG_WEB_FUNCTION_ENTRY_v4_0,		0x0015) \
	X(MSG_WEB_FUNCTION_EXIT_v4_0,		0x0016) \
	X(MSG_WEB_JS_FUNCTION_ENTRY_v4_0,	0x0017) \
	X(MSG_WEB_JS_FUNCTION_EXIT_v4_0,	0x0018) \
	X(MSG_APP_SETUP_STAGE_v4_0,		0x0019) \
	X(MSG_WSP_v4_0,				0x001a) \
	X(MSG_PROBE_FBI_v4_0,			0x0020) \
	X(MSG_PROBE_UI_HIERARCHY_DATA,		0x0021) \
	X(MSG_PROBE_MEMORY_v4_0,		0x0101)	\
	X(MSG_PROBE_FILE_v4_0,			0x0104) \
	X(MSG_PROBE_LIFECYCLE_v4_0,		0x0105) \
	X(MSG_PROBE_SCREENSHOT_v4_0,		0x0106) \
	X(MSG_PROBE_SCENE_v4_0,			0x0107) \
	X(MSG_PROBE_THREAD_v4_0,		0x0108) \
	X(MSG_PROBE_CUSTOM_v4_0,		0x0109) \
	X(MSG_PROBE_SYNC_v4_0,			0x0110) \
	X(MSG_PROBE_NETWORK_v4_0,		0x0111) \
	X(MSG_PROBE_GL_v4_0,			0x0112) \
	X(MSG_COMPRESSED_v4_0,			0xbebe)

#define X(id, val) id = val,
enum msg_id_v4_0{
	MSG_ID_LIST40
};
#undef X

#define init_list_v4_0 \
X(MSG_PROCESS_INFO_v4_0, parse_and_print_process_info_v3_0)\
X(MSG_TERMINATE_v4_0, parse_and_print_terminate_v3_0)\
X(MSG_ERROR_v4_0, parse_and_print_error_v3_0)\
X(MSG_SAMPLE_v4_0, parse_and_print_sample_v3_0)\
X(MSG_SYSTEM_v4_0, parse_and_print_system_v3_0)\
X(MSG_RECORD_v4_0, parse_and_print_record_v3_0)\
\
X(MSG_FUNCTION_ENTRY_v4_0, parse_and_print_function_entry_v4_0)\
X(MSG_FUNCTION_EXIT_v4_0, parse_and_print_function_exit_v4_0)\
X(MSG_SYSCALL_ENTRY_v4_0, parse_and_print_syscall_entry_v4_0)\
X(MSG_SYSCALL_EXIT_v4_0, parse_and_print_syscall_exit_v4_0)\
X(MSG_FILE_FUNCTION_ENTRY_v4_0, parse_and_print_file_func_entry_v4_0)\
X(MSG_FILE_FUNCTION_EXIT_v4_0, parse_and_print_file_func_exit_v4_0)\
X(MSG_PROCESS_STATUS_INFO_v4_0, parse_and_print_process_stat_info_v4_0)\
\
X(MSG_WEB_FUNCTION_ENTRY_v4_0, parse_and_print_web_function_entry_v3_0)\
X(MSG_WEB_FUNCTION_EXIT_v4_0, parse_and_print_web_function_exit_v3_0)\
\
X(MSG_WEB_JS_FUNCTION_ENTRY_v4_0, parse_and_print_web_js_func_entry_v4_0)\
X(MSG_WEB_JS_FUNCTION_EXIT_v4_0, parse_and_print_web_js_func_exit_v4_0)\
X(MSG_APP_SETUP_STAGE_v4_0, parse_and_print_app_setup_stage_v4_0)\
X(MSG_WSP_v4_0, parse_msg_wsp_v4_0)\
X(MSG_PROBE_FBI_v4_0, parse_and_print_fbi_v3_0)\
X(MSG_PROBE_UI_HIERARCHY_DATA, parse_and_print_ui_hierarchy_data_v4_0)\
\
X(MSG_CONTEXT_SWITCH_ENTRY_v4_0, parse_and_print_context_switch_entry_v3_0)\
X(MSG_CONTEXT_SWITCH_EXIT_v4_0, parse_and_print_context_switch_exit_v3_0)\
X(MSG_PROCESS_MAP_v4_0, parse_and_print_proc_map_v3_0)\
X(MSG_PROCESS_UNMAP_v4_0, parse_and_print_proc_unmap_v3_0)\
X(MSG_PROCESS_COMM_v4_0, parse_and_print_proc_comm_v3_0)\
X(MSG_PROBE_MEMORY_v4_0, parse_and_print_probe_memory_v3_0)\
X(MSG_PROBE_FILE_v4_0, parse_and_print_probe_resource_v3_0)\
X(MSG_PROBE_LIFECYCLE_v4_0, parse_and_print_probe_lifecycle_v3_0)\
X(MSG_PROBE_SCREENSHOT_v4_0, parse_and_print_probe_screenshot_v3_0)\
X(MSG_PROBE_SCENE_v4_0, parse_and_print_probe_scene_v3_0)\
X(MSG_PROBE_THREAD_v4_0, parse_and_print_probe_thread_v3_0)\
X(MSG_PROBE_CUSTOM_v4_0, parse_and_print_probe_custom_v3_0)\
X(MSG_PROBE_SYNC_v4_0, parse_and_print_probe_sync_v3_0)\
X(MSG_PROBE_NETWORK_v4_0, parse_and_print_probe_network_v3_0)\
X(MSG_PROBE_GL_v4_0, parse_and_print_probe_gl_v3_0)

#define X(id, func) void func (char *buf, void *b, const struct conversion_base *conv_base);
init_list_v4_0
#undef X

void register_protocol_v4_0();

#endif /* __PROTOCOL_V4_0_H__ */

#ifndef __PROTOCOL_V4_2_H__
#define __PROTOCOL_V4_2_H__

#include "protocol_v3_0.h"
#include "protocol_v4_0.h"

enum msg_id_v4_2{
	MSG_PROCESS_INFO_v4_2			= 0x0001,
	MSG_TERMINATE_v4_2			= 0x0002,
	MSG_ERROR_v4_2				= 0x0003,
	MSG_SAMPLE_v4_2				= 0x0004,
	MSG_SYSTEM_v4_2				= 0x0005, /* CHANGED */
	MSG_RECORD_v4_2				= 0x0007,
	MSG_FUNCTION_ENTRY_v4_2			= 0x0008,
	MSG_FUNCTION_EXIT_v4_2			= 0x0009,

	MSG_SYSCALL_ENTRY_v4_2			= 0x000a,
	MSG_SYSCALL_EXIT_v4_2			= 0x000b,
	MSG_FILE_FUNCTION_ENTRY_v4_2		= 0x000c,
	MSG_FILE_FUNCTION_EXIT_v4_2		= 0x000d,
	MSG_PROCESS_STATUS_INFO_v4_2		= 0x000e,

	MSG_CONTEXT_SWITCH_ENTRY_v4_2		= 0x0010,
	MSG_CONTEXT_SWITCH_EXIT_v4_2		= 0x0011,
	MSG_PROCESS_MAP_v4_2			= 0x0012,
	MSG_PROCESS_UNMAP_v4_2			= 0x0013,
	MSG_PROCESS_COMM_v4_2			= 0x0014,
	MSG_WEB_PROFILING_v4_2			= 0x0015,
	MSG_APP_SETUP_STAGE_v4_2		= 0x0019,
	MSG_WSP_v4_2				= 0x001a,
	MSG_PROBE_FBI_v4_2			= 0x0020,
	MSG_PROBE_LSAN				= 0x0022,

	MSG_PROBE_MEMORY_v4_2			= 0x0101,
	MSG_PROBE_UICONTROL_v4_2		= 0x0102,
	MSG_PROBE_UIEVENT_v4_2			= 0x0103,
	MSG_PROBE_RESOURCE_v4_2			= 0x0104,
	MSG_PROBE_LIFECYCLE_v4_2		= 0x0105,
	MSG_PROBE_SCREENSHOT_v4_2		= 0x0106,
	MSG_PROBE_SCENE_v4_2			= 0x0107,
	MSG_PROBE_THREAD_v4_2			= 0x0108,
	MSG_PROBE_CUSTOM_v4_2			= 0x0109,
	MSG_PROBE_SYNC_v4_2			= 0x0110,
	MSG_PROBE_NETWORK_v4_2			= 0x0111,
	MSG_PROBE_GL_v4_2			= 0x0112,
	MSG_COMPRESSED_v4_2			= 0xbebe
};


#define init_list_v4_2 \
X(MSG_PROCESS_INFO_v4_2, parse_and_print_process_info_v3_0)\
X(MSG_TERMINATE_v4_2, parse_and_print_terminate_v3_0)\
X(MSG_ERROR_v4_2, parse_and_print_error_v3_0)\
X(MSG_SAMPLE_v4_2, parse_and_print_sample_v3_0)\
X(MSG_SYSTEM_v4_2, parse_and_print_system_v4_2)\
X(MSG_RECORD_v4_2, parse_and_print_record_v3_0)\
\
X(MSG_FUNCTION_ENTRY_v4_2, parse_and_print_function_entry_v4_0)\
X(MSG_FUNCTION_EXIT_v4_2, parse_and_print_function_exit_v4_0)\
X(MSG_SYSCALL_ENTRY_v4_2, parse_and_print_syscall_entry_v4_0)\
X(MSG_SYSCALL_EXIT_v4_2, parse_and_print_syscall_exit_v4_0)\
X(MSG_FILE_FUNCTION_ENTRY_v4_2, parse_and_print_file_func_entry_v4_0)\
X(MSG_FILE_FUNCTION_EXIT_v4_2, parse_and_print_file_func_exit_v4_0)\
X(MSG_PROCESS_STATUS_INFO_v4_2, parse_and_print_process_stat_info_v4_0)\
\
X(MSG_WEB_PROFILING_v4_2, parse_and_print_web_profiling_v4_2)\
\
X(MSG_APP_SETUP_STAGE_v4_2, parse_and_print_app_setup_stage_v4_0)\
X(MSG_WSP_v4_2, parse_msg_wsp_v4_0)\
X(MSG_PROBE_FBI_v4_2, parse_and_print_fbi_v3_0)\
X(MSG_PROBE_LSAN, parse_and_print_lsan_v4_2)\
\
X(MSG_CONTEXT_SWITCH_ENTRY_v4_2, parse_and_print_context_switch_entry_v3_0)\
X(MSG_CONTEXT_SWITCH_EXIT_v4_2, parse_and_print_context_switch_exit_v3_0)\
X(MSG_PROCESS_MAP_v4_2, parse_and_print_proc_map_v3_0)\
X(MSG_PROCESS_UNMAP_v4_2, parse_and_print_proc_unmap_v3_0)\
X(MSG_PROCESS_COMM_v4_2, parse_and_print_proc_comm_v3_0)\
X(MSG_PROBE_MEMORY_v4_2, parse_and_print_probe_memory_v3_0)\
X(MSG_PROBE_UICONTROL_v4_2, parse_and_print_probe_uicontrol_v3_0)\
X(MSG_PROBE_UIEVENT_v4_2, parse_and_print_probe_uievent_v3_0)\
X(MSG_PROBE_RESOURCE_v4_2, parse_and_print_probe_resource_v3_0)\
X(MSG_PROBE_LIFECYCLE_v4_2, parse_and_print_probe_lifecycle_v3_0)\
X(MSG_PROBE_SCREENSHOT_v4_2, parse_and_print_probe_screenshot_v3_0)\
X(MSG_PROBE_SCENE_v4_2, parse_and_print_probe_scene_v3_0)\
X(MSG_PROBE_THREAD_v4_2, parse_and_print_probe_thread_v3_0)\
X(MSG_PROBE_CUSTOM_v4_2, parse_and_print_probe_custom_v3_0)\
X(MSG_PROBE_SYNC_v4_2, parse_and_print_probe_sync_v3_0)\
X(MSG_PROBE_NETWORK_v4_2, parse_and_print_probe_network_v3_0)\
X(MSG_PROBE_GL_v4_2, parse_and_print_probe_gl_v3_0)

#define X(id, func) void func (char *buf, void *b, const struct conversion_base *conv_base);
init_list_v4_2
#undef X

void register_protocol_v4_2();

#endif /* __PROTOCOL_V4_2_H__ */

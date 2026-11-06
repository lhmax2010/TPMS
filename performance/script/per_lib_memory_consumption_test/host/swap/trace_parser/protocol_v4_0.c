#include "protocol_v4_0.h"

static void print_function_common(struct probe_info_v3_0_t *pr, void *b,
				  const struct conversion_base *conv_base)
{
	struct addr_info ainfo, caller_ainfo;

	addr_info_fill(pr->pid, pr->addr, &ainfo);
	addr_info_fill(pr->pid, pr->caller_pc_address, &caller_ainfo);

	conv_base->print_int(b, "pid", pr->pid);
	conv_base->print_int(b, "tid", pr->tid);
	conv_base->print_addr(b, "pc_address", pr->addr);
	conv_base->print_addr(b, "pc_map_addr", ainfo.offset);
	conv_base->print_str(b, "map_section", ainfo.map_name);

	conv_base->print_addr(b, "caller_pc_address", pr->caller_pc_address);
	conv_base->print_addr(b, "caller_map_addr", caller_ainfo.offset);
	conv_base->print_str(b, "caller_map_name", caller_ainfo.map_name);

	conv_base->print_int(b, "cpu_num", pr->cpu_num);
}
void parse_and_print_function_entry_v4_0(char *buf, void *b,
				    const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;
	struct probe_info_v3_0_t pr;

	SANITY_CHECK(buf)

	pr.pid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	pr.tid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	pr.addr = *(uint64_t *)p;
	p += sizeof(uint64_t);

	pr.caller_pc_address = *(uint64_t *)p;
	p += sizeof(uint64_t);

	pr.cpu_num = *(uint32_t *)p;
	p += sizeof(uint32_t);

	print_function_common(&pr, b, conv_base);

	/* get real address */

	p = conv_base->parse_and_print_args(p, b);
}

void parse_and_print_function_exit_v4_0(char *buf, void *b,
				   const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;
	struct probe_info_v3_0_t pr;

	SANITY_CHECK(buf)

	pr.pid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	pr.tid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	pr.addr = *(uint64_t *)p;
	p += sizeof(uint64_t);

	pr.caller_pc_address = *(uint64_t *)p;
	p += sizeof(uint64_t);

	pr.cpu_num = *(uint32_t *)p;
	p += sizeof(uint32_t);

	print_function_common(&pr, b, conv_base);


}

void parse_and_print_syscall_entry_v4_0(char *buf, void *b,
					const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;
	struct probe_info_v3_0_t pr;

	SANITY_CHECK(buf)

	pr.pid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	pr.tid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	pr.type = *(uint32_t *)p;
	p += sizeof(uint32_t);

	pr.addr = *(uint64_t *)p;
	p += sizeof(uint64_t);

	pr.caller_pc_address = *(uint64_t *)p;
	p += sizeof(uint64_t);

	struct addr_info ainfo;
	addr_info_fill(pr.pid, pr.addr, &ainfo);

	conv_base->print_int(b, "pid", pr.pid);
	conv_base->print_int(b, "tid", pr.tid);
	conv_base->print_int(b, "type", pr.type);
	conv_base->print_addr(b, "pc_address", pr.addr);
	conv_base->print_addr(b, "pc_map_addr", ainfo.offset);
	conv_base->print_str(b, "map_section", ainfo.map_name);
	conv_base->print_addr(b, "caller_pc_address", pr.caller_pc_address);

	conv_base->print_int(b, "cpu_num", *(uint32_t *)p);
	p += sizeof(uint32_t);
	/* get real address */

	p = conv_base->parse_and_print_args(p, b);
}

void parse_and_print_syscall_exit_v4_0(char *buf, void *b,
				       const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;
	struct probe_info_v3_0_t pr;

	SANITY_CHECK(buf)

	pr.pid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	pr.tid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	pr.type = *(uint32_t *)p;
	p += sizeof(uint32_t);

	pr.addr = *(uint64_t *)p;
	p += sizeof(uint64_t);

	pr.caller_pc_address = *(uint64_t *)p;
	p += sizeof(uint64_t);

	struct addr_info ainfo;
	addr_info_fill(pr.pid, pr.addr, &ainfo);

	conv_base->print_int(b, "pid", pr.pid);
	conv_base->print_int(b, "tid", pr.tid);
	conv_base->print_int(b, "type", pr.type);
	conv_base->print_addr(b, "pc_address", pr.addr);
	conv_base->print_addr(b, "pc_map_addr", ainfo.offset);
	conv_base->print_str(b, "map_section", ainfo.map_name);
	conv_base->print_addr(b, "caller_pc_address", pr.caller_pc_address);

	conv_base->print_int(b, "cpu_num", *(uint32_t *)p);
	p += sizeof(uint32_t);

	p = conv_base->parse_and_print_return(p, b);
}


enum ff_args_type {
	FFAT_GENIRAL = 0,
	FFAT_OPEN = 1,
	FFAT_LOCK = 2
};

static void file_func_info_open(char *buf, void *b,
				const struct conversion_base *cb)
{
	cb->print_str(b, "open_file_path", buf);
}

static void file_func_info_lock(char *buf, void *b,
				const struct conversion_base *cb)
{
	char *p = buf;
	uint32_t type, whence;
	uint64_t start, length;

	type = *(uint32_t *)p;
	p += sizeof(uint32_t);

	whence = *(uint32_t *)p;
	p += sizeof(uint32_t);

	start = *(uint64_t *)p;
	p += sizeof(uint64_t);

	length = *(uint64_t *)p;
	p += sizeof(uint64_t);

	cb->print_int(b, "type", type);
	cb->print_int(b, "whence", whence);
	cb->print_long(b, "start", start);
	cb->print_long(b, "length", length);
}

void parse_and_print_file_func_entry_v4_0(char *buf, void *b,
					  const struct conversion_base *conv_base)
{
	char *p = buf;
	struct function_entry_v4_0 {
		uint32_t pid;
		uint32_t tid;
		uint32_t fd;
		uint32_t event_type;
		char *file_path;
		enum ff_args_type args_type;
	} fe;

	SANITY_CHECK(buf);

	fe.pid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	fe.tid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	fe.fd = *(uint32_t *)p;
	p += sizeof(uint32_t);

	fe.event_type = *(uint32_t *)p;
	p += sizeof(uint32_t);

	fe.file_path = (char *)p;
	p += strlen(fe.file_path) + 1;

	fe.args_type = *(uint32_t *)p;
	p += sizeof(uint32_t);

	conv_base->print_int(b, "pid", fe.pid);
	conv_base->print_int(b, "tid", fe.tid);
	conv_base->print_int(b, "fd", fe.fd);
	conv_base->print_int(b, "event_type", fe.event_type);
	conv_base->print_str(b, "file_path", fe.file_path);
	conv_base->print_int(b, "args_type", fe.args_type);

	switch (fe.args_type) {
	case FFAT_GENIRAL:
		break;
	case FFAT_OPEN:
		file_func_info_open(p, b, conv_base);
		break;
	case FFAT_LOCK:
		file_func_info_lock(p, b, conv_base);
		break;
	default:
		conv_base->print_str(b, "args_type", "UNKNOWN");
		break;
	}
}


void parse_and_print_file_func_exit_v4_0(char *buf, void *b,
					 const struct conversion_base *conv_base)
{
	char *p = buf;
	struct function_exit_v4_0 {
		uint32_t pid;
		uint32_t tid;
	} fex;

	SANITY_CHECK(buf);

	fex.pid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	fex.tid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	conv_base->print_int(b, "pid", fex.pid);
	conv_base->print_int(b, "tid", fex.tid);
	p = conv_base->parse_and_print_return(p, b);
}



void parse_and_print_process_stat_info_v4_0(char *buf, void *b,
					    const struct conversion_base *conv_base)
{
	char *p = buf;
	uint32_t i;

	struct process_stat_info_v4_0 {
		uint32_t pid;
		uint32_t file_count;
	} psi;

	SANITY_CHECK(buf);

	psi.pid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	psi.file_count = *(uint32_t *)p;
	p += sizeof(uint32_t);

	conv_base->print_int(b, "pid", psi.pid);
	conv_base->print_int(b, "file_cnt", psi.file_count);

	for (i = 0; i < psi.file_count; i++) {
		conv_base->print_int(b, "fd", *(uint32_t *)p);
		p += sizeof(uint32_t);

		conv_base->print_int(b, "file_size", *(uint64_t *)p);
		p += sizeof(uint64_t);

		conv_base->print_str(b, "file_path", (char *)p);
		p += strlen(p) + 1;
	}
}

void parse_and_print_web_js_func_entry_v4_0(char *buf, void *b,
					    const struct conversion_base *conv_base)
{
	char *p = buf;

	SANITY_CHECK(buf);

	conv_base->print_str(b, "function_name", (char *)p);
	p += strlen(p) + 1;

	p = conv_base->parse_and_print_args(p, b);
}

void parse_and_print_web_js_func_exit_v4_0(char *buf, void *b,
					   const struct conversion_base *conv_base)
{
	char *p = buf;

	SANITY_CHECK(buf);

	conv_base->print_str(b, "function_name", (char *)p);
	p += strlen(p) + 1;

	p = conv_base->parse_and_print_return(p, b);
}

void parse_and_print_app_setup_stage_v4_0(char *buf, void *b,
					  const struct conversion_base *conv_base)
{
	char *p = buf;

	SANITY_CHECK(buf);

	conv_base->print_int(b, "pid", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "stage_ID", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_time(b, "begin_time", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_time(b, "end_time", *(uint64_t *)p);
	p += sizeof(uint64_t);

}


/* WSP */
#define WSP_ID_LIST \
	X(WSP_RES_LOAD_BEGIN, 0x0001) \
	X(WSP_RES_LOAD_END, 0x0002) \
	X(WSP_RES_PROC_BEGIN, 0x0003) \
	X(WSP_RES_PROC_END, 0x0004) \
	X(WSP_DRAW_BEGIN, 0x0005) \
	X(WSP_DRAW_END, 0x0006)

#define X(id, val) id = val,
enum wsp_id {
	WSP_ID_LIST
};
#undef X

static const char *wsp_id2name(enum wsp_id id)
{
#define X(id, val) case val: return #id;
	switch (id) {
		WSP_ID_LIST
	}
#undef X

       return NULL;
}

void parse_msg_wsp_v4_0(char *buf, void *b,
			const struct conversion_base *cb)
{
	uint32_t pid;
	enum wsp_id id;

	pid = *(uint32_t *)buf;
	buf += sizeof(uint32_t);

	id = *(uint32_t *)buf;
	buf += sizeof(uint32_t);

	cb->print_int(b, "pid", pid);
	cb->print_int(b, "wsp_id", id);
	cb->print_str(b, "describe", wsp_id2name(id));

	switch (id) {
		case WSP_DRAW_BEGIN:
		case WSP_DRAW_END:
			break;
		case WSP_RES_LOAD_BEGIN:
			cb->print_str(b, "path", buf + 4);
		case WSP_RES_LOAD_END:
		case WSP_RES_PROC_BEGIN:
		case WSP_RES_PROC_END: {
			uint32_t res_id;

			res_id = *(uint32_t *)buf;
			cb->print_int(b, "res_id", res_id);
			break;
		}
		default:
			cb->print_str(b, "warning", "unknown id");
			break;
	}
}

void parse_and_print_ui_hierarchy_data_v4_0(char *buf, void *b,
			const struct conversion_base *cb)
{
	cb->print_str(b, "path", buf);
}

#define X(id, func) register_parser(id, func);
void register_protocol_v4_0()
{
	init_list_v4_0;
}
#undef X

#include "protocol_v4_2.h"

extern int num_of_cpu;
extern const int __MAGIC__DEVICES_COUNT;

void parse_and_print_system_v4_2(char *buf, void *b,
			    const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;
	int i = 0, j = 0;
	char tmp[20];

	SANITY_CHECK(buf)

	conv_base->start_array(b, "cpu_freq");
	for (i = 0; i < num_of_cpu; i++) {
		sprintf(tmp, "cpu_freq[%d]", i);
		conv_base->print_float(b, tmp, *(float *)p);
		p += sizeof(uint32_t);
	}
	conv_base->finish_array(b);

	conv_base->start_array(b, "cpu_load");
	for (i = 0; i < num_of_cpu; i++) {
		sprintf(tmp, "cpu_load[%d]", i);
		conv_base->print_float(b, tmp, *(float *)p);
		p += sizeof(uint32_t);
	}
	conv_base->finish_array(b);

	conv_base->print_long(b, "system_mem_used", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_int(b, "target_process_count", *(uint32_t *)p);
	int proc_count = *(uint32_t *)p;
	p += sizeof(uint32_t);

	conv_base->start_array(b, "target_process");
	for (i = 0; i < proc_count; i++) {
		sprintf(tmp, "pid[%d]", i);
		conv_base->print_int(b, tmp, *(uint32_t *)p);
		p += sizeof(uint32_t);

		sprintf(tmp, "load[%d]", i);
		conv_base->print_float(b, tmp, *(float *)p);
		p += sizeof(uint32_t);

		sprintf(tmp, "virt_mem[%d]", i);
		conv_base->print_int(b, tmp, *(uint64_t *)p);
		p += sizeof(uint64_t);

		sprintf(tmp, "res_mem[%d]", i);
		conv_base->print_int(b, tmp, *(uint64_t *)p);
		p += sizeof(uint64_t);

		sprintf(tmp, "sh_mem[%d]", i);
		conv_base->print_int(b, tmp, *(uint64_t *)p);
		p += sizeof(uint64_t);

		sprintf(tmp, "pss_mem[%d]", i);
		conv_base->print_int(b, tmp, *(uint64_t *)p);
		p += sizeof(uint64_t);

		/* NEW FIELD */
		sprintf(tmp, "gem_pss[%d]", i);
		conv_base->print_int(b, tmp, *(uint64_t *)p);
		p += sizeof(uint64_t);

		/* NEW FIELD */
		sprintf(tmp, "3D_mem[%d]", i);
		conv_base->print_int(b, tmp, *(uint64_t *)p);
		p += sizeof(uint64_t);

		sprintf(tmp, "total_alloc_size[%d]", i);
		conv_base->print_long(b, tmp, *(uint64_t *)p);
		p += sizeof(uint64_t);

		sprintf(tmp, "thread_count[%d]", i);
		conv_base->print_int(b, tmp, *(uint32_t *)p);
		int thread_count = *(uint32_t *)p;
		p += sizeof(uint32_t);

		sprintf(tmp, "tid_load[%d]", i);
		conv_base->start_array(b, tmp);
		for (j = 0; j < thread_count; j++) {
			sprintf(tmp, "tid[%d:%d]", i, j);
			conv_base->print_int(b, tmp, *(uint32_t *)p);
			p += sizeof(uint32_t);

			sprintf(tmp, "load[%d:%d]", i, j);
			conv_base->print_float(b, tmp, *(float *)p);
			p += sizeof(uint32_t);
		}
		conv_base->finish_array(b);

	}
	conv_base->finish_array(b);

	conv_base->print_int(b, "other_process_count", *(uint32_t *)p);
	int other_proc_count = *(uint32_t *)p;
	p += sizeof(uint32_t);

	conv_base->start_array(b, "other_process");
	for (i = 0; i < other_proc_count; i++) {
		sprintf(tmp, "pid[%d]", i);
		conv_base->print_int(b, tmp, *(uint32_t *)p);
		p += sizeof(uint32_t);

		sprintf(tmp, "load[%d]", i);
		conv_base->print_float(b, tmp, *(float *)p);
		p += sizeof(uint32_t);
	}
	conv_base->finish_array(b);

	conv_base->print_int(b, "total_used_drive", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "disk_reads", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "disk_sectors_read", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "disk_writes", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "disk_sectors_write", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "net_send_size", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "net_recv_size", *(uint32_t *)p);
	p += sizeof(uint32_t);


	conv_base->print_int(b, "wifi", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "bt", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "gps", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "bright", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "camera", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "sound", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "audio", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "vibration", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "voltage", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "rssi", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "video", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "call", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "dnet", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "energy", *(uint32_t *)p);
	p += sizeof(uint32_t);

	for (i = 0; i != __MAGIC__DEVICES_COUNT; ++i) {
		conv_base->print_long(b, "energy/device", *(uint32_t *)p);
		p += sizeof(uint32_t);
	}
	for (i = 0; i != __MAGIC__DEVICES_COUNT; ++i) {
		conv_base->print_long(b, "energy/device|app", *(uint32_t *)p);
		p += sizeof(uint32_t);
	}
}

void parse_and_print_web_profiling_v4_2(char *buf, void *b,
				const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;
	struct {
		uint8_t subtype;
		uint32_t pid;
		uint32_t tid;
		uint32_t lnum;
		char *name;
		char *url;
	} we;

	SANITY_CHECK(buf)

	we.subtype = *(uint8_t *)p;
	p += sizeof(uint8_t);

	we.pid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	we.tid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	we.lnum = *(uint32_t *)p;
	p += sizeof(uint32_t);

	we.name = p;
	p += strlen(p) + 1;

	we.url = p;
	p += strlen(p) + 1;

	conv_base->print_int(b, "subtype", we.subtype);
	conv_base->print_int(b, "pid", we.pid);
	conv_base->print_int(b, "tid", we.tid);
	conv_base->print_str(b, "name", we.name);
	conv_base->print_str(b, "url", we.url);
	conv_base->print_int(b, "lnum", we.lnum);
}

void parse_and_print_lsan_v4_2(char *buf, void *b,
			       const struct conversion_base *conv_base)
{
	char *p = buf;
	struct {
		uint32_t status;
		uint32_t pid;
		uint32_t call_type_ptr;
		uint64_t caller_addr;
	} lsan;

	SANITY_CHECK(buf)

	lsan.status = *(uint32_t *)p;
	p += sizeof(uint32_t);

	lsan.pid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	p = conv_base->parse_and_print_args(p, b);

	lsan.call_type_ptr = *(uint32_t *)p;
	p += sizeof(uint32_t);

	lsan.caller_addr = *(uint64_t *)p;
	p += sizeof(uint64_t);

	conv_base->print_int(b, "status", lsan.status);
	conv_base->print_int(b, "pid", lsan.pid);
	conv_base->print_int(b, "call_type_ptr", lsan.call_type_ptr);
	conv_base->print_long(b, "caller_addr", lsan.caller_addr);
}
#define X(id, func) register_parser(id, func);
void register_protocol_v4_2()
{
	init_list_v4_2;
}
#undef X

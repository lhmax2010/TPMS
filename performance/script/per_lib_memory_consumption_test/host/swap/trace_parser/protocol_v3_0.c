#include "api_id_list.h"
#include "fd_api_list.h"
#include <arpa/inet.h>
#include <ctype.h>

#include "trace_parser.h"
#include "protocol_v3_0.h"
#include "library_map.h"

//-------------------- LZO ----------------------
//

/* First let's include "minizo.h". */
#include "minilzo.h"

/* We want to compress the data block at 'in' with length 'IN_LEN' to
 * the block at 'out'. Because the input block may be incompressible,
 * we must provide a little more output space in case that compression
 * is not possible.
 */

#if defined(__LZO_STRICT_16BIT)
#define IN_LEN      (8*1024u)
#elif defined(LZO_ARCH_I086) && !defined(LZO_HAVE_MM_HUGE_ARRAY)
#define IN_LEN      (60*1024u)
#else
#define IN_LEN      (128*1024ul)
#endif
#define OUT_LEN     (IN_LEN + IN_LEN / 16 + 64 + 3)

#undef IN_LEN
#define IN_LEN		(4096 << 0)


//static unsigned char __LZO_MMODEL in[IN_LEN];
//static unsigned char __LZO_MMODEL out[OUT_LEN];

/* Work-memory needed for compression. Allocate memory in units
 * of 'lzo_align_t' (instead of 'char') to make sure it is properly aligned.
 */

#define HEAP_ALLOC(var,size) \
    lzo_align_t __LZO_MMODEL var [ ((size) + (sizeof(lzo_align_t) - 1)) / sizeof(lzo_align_t) ]

//static HEAP_ALLOC(wrkmem, LZO1X_1_MEM_COMPRESS);
#define PAGES_NUM (16+1)
#define PAGES_SIZE (4*1024)

unsigned char decompressed_data [PAGES_NUM * PAGES_SIZE];
char *decompress_msg(char *compressed_p, lzo_uint data_len, lzo_uint *out_len)
{
	int r;

	r = lzo1x_decompress((unsigned char *)compressed_p, data_len,
			     decompressed_data, out_len, NULL);
	if (r == LZO_E_OK)
		printf("decompressed -> %lu\n", *out_len);
	else {
		printf("internal error - decompression failed: %d\n", r);
		return NULL;
	}
	return (char *)decompressed_data;
}

//-------------------- LZO ----------------------

#define SOCKET_SEND_SIZE 1024

//#define FILTER MSG_PROBE_NETWORK

extern const int __MAGIC__DEVICES_COUNT;

struct maps_t {
	uint64_t low_addr;
	uint64_t high_addr;
	const char *name;
};

struct app_info_t {
	uint32_t pid;
	char *comm;
	uint32_t ppid;
	uint32_t start_sec;
	uint32_t start_nsec;
	uint64_t low_addr;
	uint64_t high_addr;
	const char *name;

	uint32_t maps_c;
	struct maps_t *maps;
};


extern int num_of_cpu;
char *msg_end = 0;


bool addr_info_fill(uint32_t pid, uint64_t addr, struct addr_info *ainfo)
{
	bool ret;
	struct lmap_info info;

	ret = lmap_map_info(pid, addr, &info);
	if (ret) {
		ainfo->offset = info.offset;
		ainfo->map_name = info.name;
	} else {
		ainfo->offset = -1;
		ainfo->map_name = "?";
	}

	return ret;
}

void sanity_check(const void *p)
{
	if (p > (void *)msg_end) {
		printf_deb("Trace corrupted: event len overrun!");
		printf_deb("p = %p, end = %p", p, msg_end);
		exit(1);
	}

}




void put_line(char c)
{
	int i;
	enum {line_width = 65};
	for (i = 0; i != line_width; ++i)
		putc(c, stdout);
	putc('\n', stdout);
}

/* void print_buf(char *buf, int len, const char *info) */
/* { */
/* 	int i,j; */
/* 	char local_buf[3*16 + 2*16 + 1 + 8]; */
/* 	char * p1, * p2; */

/* 	printf_deb("BUFFER [%d] <%s>:\n", len, info); */
/* 	for ( i = 0; i < len/16 + 1; i++) */
/* 	{ */
/* 		memset(local_buf, ' ', 5*16 + 8); */

/* 		sprintf(local_buf, "0x%04X: ", i); */
/* 		p1 = local_buf + 8; */
/* 		p2 = local_buf + 8 + 3*17; */
/* 		for ( j = 0; j < 16; j++) */
/* 			if (i*16+j < len ) */
/* 			{ */
/* 				sprintf(p1, "%02X ",(unsigned char) *buf); */
/* 				p1+=3; */
/* 				if (isprint( *buf)){ */
/* 					sprintf(p2, "%c ",(int)*buf); */
/* 				}else{ */
/* 					sprintf(p2,". "); */
/* 				} */
/* 				p2+=2; */
/* 				buf++; */
/* 			} */
/* 		*p1 = ' '; */
/* 		*p2 = '\0'; */
/* 		printf_deb("%s\n",local_buf); */
/* 	} */
/* } */



char *parse_msg_hdr(char *p, struct msg_hdr *msg_hdr)
{
	msg_hdr->msg_id = *(uint32_t *)p;
	p += sizeof(msg_hdr->msg_id);
	msg_hdr->seq_num = *(uint32_t *)p;
	p += sizeof(msg_hdr->seq_num);
	msg_hdr->sec = *(uint32_t *)p;
	p += sizeof(msg_hdr->sec);
	msg_hdr->usec = *(uint32_t *)p;
	p += sizeof(msg_hdr->usec);
	msg_hdr->len = *(uint32_t *)p;
	p += sizeof(msg_hdr->len);

	return p;
}


const char *decode_api_id(uint32_t num)
{
	if ((num == 0) || (num > api_id_list_length))
		return "<unknown>";
	return api_id_list[num - 1];
}

char *parse_and_print_probe_common_v3_0(char *buf, void *b,
				   const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;
	struct probe_info_v3_0_t pr;

	SANITY_CHECK(buf)

	conv_base->print_int(b, "api_id", *(uint32_t *)p);
	conv_base->print_str(b, "api_id_str", decode_api_id(*(uint32_t *)p) );
	p += sizeof(uint32_t);

	pr.pid = *(uint32_t *)p;
	conv_base->print_int(b, "pid", pr.pid);
	p += sizeof(uint32_t);

	pr.tid = *(uint32_t *)p;
	conv_base->print_int(b, "tid", pr.tid);
	p += sizeof(uint32_t);

	p = conv_base->parse_and_print_args(p, b);

#define PACK_RETTYPE
#ifdef PACK_RETTYPE
	// print return (type, value);
	p = conv_base->parse_and_print_return(p, b);
#else
	// print uint64_t return value
	conv_base->print_long(b, "return", *(uint64_t *)p);
	p += sizeof(uint64_t);
#endif
	conv_base->print_long(b, "errno", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_int(b, "internal_call", *(uint32_t *)p);
	p += sizeof(uint32_t);

	pr.caller_pc_address = *(uint64_t *)p;
	p += sizeof(uint64_t);

	pr.addr = *(uint64_t *)p;
	conv_base->print_addr(b, "function_addr", pr.addr);
	p += sizeof(uint64_t);

	struct addr_info ainfo;
	addr_info_fill(pr.pid, pr.addr, &ainfo);
	conv_base->print_addr(b, "pc_map_addr", ainfo.offset);
	conv_base->print_str(b, "map_section", ainfo.map_name);

	addr_info_fill(pr.pid, pr.caller_pc_address, &ainfo);
	conv_base->print_addr(b, "caller_pc_address", pr.caller_pc_address);
	conv_base->print_addr(b, "caller_map_addr", ainfo.offset);
	conv_base->print_str(b, "caller_map_name", ainfo.map_name);
	return p;
}

void parse_and_print_probe_memory_v3_0(char *buf, void *b,
				  const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	p = parse_and_print_probe_common_v3_0(p, b, conv_base);

	SANITY_CHECK(p)

	conv_base->print_long(b, "size", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_int(b, "memory_api_type", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_addr(b, "addr", *(uint64_t *)p);
	p += sizeof(uint64_t);
}

void parse_and_print_probe_uicontrol_v3_0(char *buf, void *b,
				     const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	p = parse_and_print_probe_common_v3_0(p, b, conv_base);

	SANITY_CHECK(p)

	conv_base->print_str(b, "parent_name", p);
	p += strlen(p) + 1;

	conv_base->print_str(b, "parent_class_name", p);
	p += strlen(p) + 1;

	conv_base->print_long(b, "parent_ptr", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_str(b, "child_name", p);
	p += strlen(p) + 1;

	conv_base->print_str(b, "child_class_name", p);
	p += strlen(p) + 1;

	conv_base->print_long(b, "child_ptr", *(uint64_t *)p);
	p += sizeof(uint64_t);
}

void parse_and_print_probe_uievent_v3_0(char *buf, void *b,
				   const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	p = parse_and_print_probe_common_v3_0(p, b, conv_base);

	SANITY_CHECK(p)

	conv_base->print_int(b, "event_type", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "detail_type", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "x", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "y", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_str(b, "info1", p);
	p += strlen(p) + 1;

	conv_base->print_int(b, "info2", *(uint32_t *)p);
	p += sizeof(uint32_t);
}

void parse_and_print_probe_resource_v3_0(char *buf, void *b,
				    const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	p = parse_and_print_probe_common_v3_0(p, b, conv_base);

	SANITY_CHECK(p)

	conv_base->print_long(b, "size", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_long(b, "fd_value", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_int(b, "fd_api_type", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_long(b, "file_size", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_str(b, "file_path", p);
	p += strlen(p) + 1;
}

void parse_and_print_probe_network_v3_0(char *buf, void *b,
				   const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	p = parse_and_print_probe_common_v3_0(p, b, conv_base);

	SANITY_CHECK(p)

	conv_base->print_long(b, "Object_addr", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_long(b, "FDValue", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_int(b, "FDApiType", *(uint32_t *)p);
	conv_base->print_str(b, "FDApiTypeStr", fd_api_list[*(uint32_t *)p]);
	p += sizeof(uint32_t);

	char str[256];
	inet_ntop( AF_INET, p, str, 256 );

	conv_base->print_str(b, "IP", str);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "Port", *(uint32_t *)p);
	p += sizeof(uint32_t);

	uint64_t len = *(uint64_t *)p;
	conv_base->print_long(b, "Msg len", len);
	p += sizeof(uint64_t);

	if (len > SOCKET_SEND_SIZE)
		len = SOCKET_SEND_SIZE;
	conv_base->print_str(b, "message", "");

	conv_base->print_buf(p, len, "message");
	p += len;
}

void parse_and_print_probe_gl_v3_0(char *buf, void *b,
			      const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	p = parse_and_print_probe_common_v3_0(p, b, conv_base);

	SANITY_CHECK(p)

	conv_base->print_long(b, "GLCurrentContext", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_int(b, "GLApiType", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_long(b, "GLElspsedTime", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_str(b, "GLContestValue", p);
	p += strlen(p) + 1;
}

void parse_and_print_probe_lifecycle_v3_0(char *buf, void __unused *b,
				     const struct conversion_base __unused *conv_base)
{
	parse_and_print_probe_common_v3_0(buf, b, conv_base);
}

void parse_and_print_probe_screenshot_v3_0(char *buf, void *b,
				      const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	p = parse_and_print_probe_common_v3_0(p, b, conv_base);

	SANITY_CHECK(p)

	conv_base->print_str(b, "image_file_path", p);
	p += strlen(p) + 1;

	conv_base->print_int(b, "orientation", *(uint32_t *)p);
	p += sizeof(uint32_t);
}

void parse_and_print_probe_scene_v3_0(char *buf, void *b,
				 const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	p = parse_and_print_probe_common_v3_0(p, b, conv_base);

	SANITY_CHECK(p)

	conv_base->print_str(b, "scene_name", p);
	p += strlen(p) + 1;

	conv_base->print_str(b, "font_name", p);
	p += strlen(p) + 1;

	conv_base->print_long(b, "font_ptr", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_str(b, "panel_name", p);
	p += strlen(p) + 1;

	conv_base->print_long(b, "panel_ptr", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_long(b, "tranistion_time", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_long(b, "user_tranistion_time", *(uint64_t *)p);
	p += sizeof(uint64_t);
}

void parse_and_print_probe_thread_v3_0(char *buf, void *b,
				  const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	p = parse_and_print_probe_common_v3_0(p, b, conv_base);

	conv_base->print_long(b, "thread_id", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_long(b, "ospthread_id", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_int(b, "thread_type", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "api_type", *(uint32_t *)p);
	p += sizeof(uint32_t);
}

void parse_and_print_probe_custom_v3_0(char *buf, void *b,
				  const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	p = parse_and_print_probe_common_v3_0(p, b, conv_base);

	SANITY_CHECK(p)

	conv_base->print_int(b, "handle", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "type", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_str(b, "name", p);
	p += strlen(p) + 1;

	conv_base->print_int(b, "color", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_double(b, "value", *(double *)p);
	p += sizeof(double);
}

void parse_and_print_probe_sync_v3_0(char *buf, void *b,
				const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	p = parse_and_print_probe_common_v3_0(p, b, conv_base);

	SANITY_CHECK(p)

	conv_base->print_long(b, "sync_val", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_int(b, "sync_type", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "api_type", *(uint32_t *)p);
	p += sizeof(uint32_t);
}

char *parse_and_print_dep_lib_v3_0(char *buf, struct maps_t *map, void *b,
			      const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	SANITY_CHECK(buf)
	map->low_addr = *(uint64_t *)p; p += sizeof(uint64_t);
	map->high_addr = *(uint64_t *)p; p += sizeof(uint64_t);
	map->name = p; p += strlen(p) + 1;

	conv_base->print_addr(b, "low_addr", map->low_addr);
	conv_base->print_addr(b, "high_addr", map->high_addr);
	conv_base->print_str(b, "lib_path", map->name);

	return p;
}

void parse_and_print_process_info_v3_0(char *buf, void *b,
				  const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;
	uint32_t i = 0;
	struct app_info_t app;

	SANITY_CHECK(buf)

	app.pid = *(uint32_t *)p; p += sizeof(uint32_t);
	app.comm = strdup(p); p += strlen(p) + 1;
	app.ppid = *(uint32_t *)p; p += sizeof(uint32_t);
	app.start_sec = *(uint32_t *)p; p += sizeof(uint32_t);
	app.start_nsec = *(uint32_t *)p; p += sizeof(uint32_t);
	app.low_addr = *(uint64_t *)p; p += sizeof(uint64_t);
	app.high_addr = *(uint64_t *)p; p += sizeof(uint64_t);
	app.name = p; p += strlen(p) + 1;
	app.maps_c = *(uint32_t *)p; p += sizeof(uint32_t);
	app.maps = (struct maps_t *)malloc(sizeof(*app.maps) * app.maps_c);

	conv_base->print_int(b, "pid", app.pid);
	conv_base->print_str(b, "comm", app.comm);
	conv_base->print_int(b, "ppid", app.ppid);
	conv_base->print_int(b, "start_sec", app.start_sec);
	conv_base->print_int(b, "start_nsec", app.start_nsec);
	conv_base->print_addr(b, "low_addr", app.low_addr);
	conv_base->print_addr(b, "high_addr", app.high_addr);
	conv_base->print_str(b, "binary_path", app.name);
	conv_base->print_int(b, "dep_libs_count", app.maps_c);

	lmap_app_add(app.pid);
	lmap_mmap(app.pid, app.low_addr, app.high_addr, app.name);

	conv_base->start_object(b, "dep_libs");
	for (i = 0; i < app.maps_c; ++i) {
		struct maps_t *map = &app.maps[i];
		p = parse_and_print_dep_lib_v3_0(p, map, b, conv_base);

		lmap_mmap(app.pid, map->low_addr, map->high_addr, map->name);
	}
	conv_base->finish_object(b, "dep_libs");

	free(app.maps);
}

void parse_and_print_error_v3_0(char *buf, void *b,
			   const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;

	SANITY_CHECK(buf)

	conv_base->print_str(b, "error_msg", p);
	p += strlen(p) + 1;
}

char *parse_and_print_record_event_v3_0(char *buf, void *b,
				   const struct conversion_base *conv_base)
{
	// nesting: 2
	char *p = buf;

	SANITY_CHECK(buf)

	conv_base->print_int(b, "id", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "type", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "code", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "value", *(uint32_t *)p);
	p += sizeof(uint32_t);

	return p;
}

void parse_and_print_record_v3_0(char *buf, void *b,
			    const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;
	int i = 0;

	SANITY_CHECK(buf)

	conv_base->print_int(b, "count", *(uint32_t *)p);
	int count = *(uint32_t *)p;
	p += sizeof(uint32_t);

	for (i = 0; i < count; i++) {
		p = parse_and_print_record_event_v3_0(p, b, conv_base);
	}
}

void parse_and_print_system_v3_0(char *buf, void *b,
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

void parse_and_print_sample_v3_0(char *buf, void *b,
			    const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;

	SANITY_CHECK(buf)

	conv_base->print_int(b, "pid", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_addr(b, "pc_address", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_int(b, "tid", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "cpu_num", *(uint32_t *)p);
	p += sizeof(uint32_t);
}

void parse_and_print_function_entry_v3_0(char *buf, void *b,
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

	//fill abs_addr and mmap section name
	struct addr_info ainfo;
	addr_info_fill(pr.pid, pr.tid, &ainfo);

	conv_base->print_int(b, "pid", pr.pid);
	conv_base->print_int(b, "tid", pr.tid);
	conv_base->print_int(b, "type", pr.type & 0xffff);
	conv_base->print_int(b, "subtype", (pr.type & 0xffff0000) >> 16);
	conv_base->print_addr(b, "pc_address", pr.addr);
	conv_base->print_addr(b, "pc_map_addr", ainfo.offset);
	conv_base->print_str(b, "map_section", ainfo.map_name);
	conv_base->print_addr(b, "caller_pc_address", pr.caller_pc_address);

	conv_base->print_int(b, "cpu_num", *(uint32_t *)p);
	p += sizeof(uint32_t);
	//get real address

	p = conv_base->parse_and_print_args(p, b);
}

void parse_and_print_function_exit_v3_0(char *buf, void *b,
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
	addr_info_fill(pr.pid, pr.pid, &ainfo);

	conv_base->print_int(b, "pid", pr.pid);
	conv_base->print_int(b, "tid", pr.tid);
	conv_base->print_int(b, "type", pr.type & 0xffff);
	conv_base->print_int(b, "subtype", (pr.type & 0xffff0000) >> 16);
	conv_base->print_addr(b, "pc_address", pr.addr);
	conv_base->print_addr(b, "pc_map_addr", ainfo.offset);;
	conv_base->print_str(b, "map_section", ainfo.map_name);
	conv_base->print_addr(b, "caller_pc_address", pr.caller_pc_address);

	conv_base->print_int(b, "cpu_num", *(uint32_t *)p);
	p += sizeof(uint32_t);

#ifdef PACK_RETTYPE
	// print return (type, value);
	p = conv_base->parse_and_print_return(p, b);
#else
	// print uint64_t return value
	conv_base->print_long(b, "return", *(uint64_t *)p);
	p += sizeof(uint64_t);
#endif
}

void parse_and_print_web_function_entry_v3_0(char *buf, void *b,
				    const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;
	struct {
		int pid;
		int tid;
		int lnum;
		char *name;
		char *url;
	} we;

	SANITY_CHECK(buf)

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

	conv_base->print_int(b, "pid", we.pid);
	conv_base->print_int(b, "tid", we.tid);
	conv_base->print_str(b, "name", we.name);
	conv_base->print_str(b, "url", we.url);
	conv_base->print_int(b, "lnum", we.lnum);
}

void parse_and_print_web_function_exit_v3_0(char *buf, void *b,
				    const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;
	struct {
		int pid;
		int tid;
		char *name;
	} we;

	SANITY_CHECK(buf)

	we.pid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	we.tid = *(uint32_t *)p;
	p += sizeof(uint32_t);

	we.name = p;
	p += strlen(p) + 1;

	conv_base->print_int(b, "pid", we.pid);
	conv_base->print_int(b, "tid", we.tid);
	conv_base->print_str(b, "name", we.name);
}

void parse_and_print_fbi_v3_0(char *buf, void *b,
			 const struct conversion_base *conv_base)
{
	char *p = buf;
	uint32_t var_id;
	uint32_t size;

	var_id = *(uint32_t *)p;
	p += sizeof(uint32_t);

	size = *(uint32_t *)p;
	p += sizeof(uint32_t);

	conv_base->print_int(b, "var_id", var_id);
	conv_base->print_int(b, "size", size);

	conv_base->print_buf(p, size, __func__);
}

void parse_and_print_context_switch_entry_v3_0(char *buf, void *b,
					  const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;

	SANITY_CHECK(buf)

	conv_base->print_addr(b, "pc_address", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_int(b, "pid", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "tid", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "cpu_num", *(uint32_t *)p);
	p += sizeof(uint32_t);
}

void parse_and_print_context_switch_exit_v3_0(char *buf, void *b,
					 const struct conversion_base *conv_base)
{
	// nesting: 0
	char *p = buf;

	SANITY_CHECK(buf)

	conv_base->print_addr(b, "pc_address", *(uint64_t *)p);
	p += sizeof(uint64_t);

	conv_base->print_int(b, "pid", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "tid", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_int(b, "cpu_num", *(uint32_t *)p);
	p += sizeof(uint32_t);
}

void parse_and_print_proc_map_v3_0(char *buf, void *b,
				     const struct conversion_base *conv_base)
{
	char *p = buf;

	SANITY_CHECK(buf)

	uint32_t pid = *(uint32_t *)p; p += sizeof(uint32_t);
	uint64_t low_addr = *(uint64_t *)p; p += sizeof(uint64_t);
	uint64_t high_addr = *(uint64_t *)p; p += sizeof(uint64_t);
	const char *name = p; p += strlen(p) + 1;

	conv_base->print_int(b, "pid", pid);
	conv_base->print_addr(b, "low_addr", low_addr);
	conv_base->print_addr(b, "high_addr", high_addr);
	conv_base->print_str(b, "binary_path", name);

	lmap_mmap(pid, low_addr, high_addr, name);
}

void parse_and_print_proc_unmap_v3_0(char *buf, void *b,
				       const struct conversion_base *conv_base)
{
	char *p = buf;

	SANITY_CHECK(buf)

	uint32_t pid = *(uint32_t *)p; p += sizeof(uint32_t);
	uint64_t low_addr = *(uint64_t *)p; p += sizeof(uint64_t);
	uint64_t high_addr = *(uint64_t *)p; p += sizeof(uint64_t);

	conv_base->print_int(b, "pid", pid);
	conv_base->print_addr(b, "low_addr", low_addr);
	conv_base->print_addr(b, "high_addr", high_addr);

	lmap_unmap(pid, low_addr, high_addr);
}

void parse_and_print_proc_comm_v3_0(char *buf, void *b,
				      const struct conversion_base *conv_base)
{
	char *p = buf;

	SANITY_CHECK(buf)

	conv_base->print_int(b, "pid", *(uint32_t *)p);
	p += sizeof(uint32_t);

	conv_base->print_str(b, "comm", p);
	p += strlen(p) + 1;
}

void parse_and_print_terminate_v3_0(char *buf, void *b,
			       const struct conversion_base *conv_base)
{
	char *p = buf;
	SANITY_CHECK(buf);

	uint32_t pid = *(uint32_t *)p; p += sizeof(uint32_t);

	lmap_app_del(pid);
	conv_base->print_int(b, "pid", pid);
}

void parse_and_print_compressed_v3_0(char *buf, void *b,
			        const struct conversion_base *conv_base)
{

	/* FIXME implement it */
	return;

	buf++;
	b = (void *)conv_base;
	b++;
/*
	lzo_uint out_len;
	char *comp_end_p;
	char *p = buf;

	p = decompress_msg(buf, (lzo_uint)msg_hdr->len, &out_len);
	comp_end_p = p + out_len;
	printf("p = %p; comp_end_p = %p\n", p, comp_end_p);
	while (p < comp_end_p) {
		printf("parse %p\n", p);
		conv_base->print_msg_hdr((struct msg_hdr *)p, b);

		parse_and_print_msg_payload(
			(char *)(p + sizeof(*msg_hdr)),
			(const struct msg_hdr *)p, b, conv_base);
		if (bin_mode) {
			put_line('-');
			print_buf((char *)(p + sizeof(*msg_hdr)), ((struct msg_hdr *)p)->len, "");
		}
		p += (sizeof(*msg_hdr) + ((struct msg_hdr *)p)->len);
		printf("next %p\n", p);
		put_line('=');
	}
*/
}






#define X(id, func) register_parser(id, func);
void register_protocol_v3_0()
{
	init_list_v3_0;
}
#undef X

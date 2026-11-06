
#include "trace_parser.h"

#include <stdarg.h>
#define ENDLINE ""

void start_object_py(void __unused *b, const char __unused *name);
void finish_object_py(void __unused *b, const char __unused *name);

int printf_py(const char *format, ...)
{
	int val = 0;
	va_list ap;

	va_start(ap, format);
	printf("\n# ");
	val = vprintf(format, ap);
	printf("\n");
	va_end(ap);

	return val;
}

void print_int_py(void __unused *b, const char *name, const uint32_t val)
{
	printf("'%s': %u," ENDLINE, name, val);
}

void print_long_addr_py(void __unused *b, const char *name, const uint64_t val)
{
	printf("'%s': 0x%016llx," ENDLINE, name, (unsigned long long)val);
}

void print_long_py(void __unused *b, const char *name, const uint64_t val)
{
	printf("'%s': %lu," ENDLINE, name, (unsigned long)val);
}

void print_float_py(void __unused *b, const char *name, const float val)
{
	printf("'%s': %f," ENDLINE, name, val);
}

void print_double_py(void __unused *b, const char *name, const double val)
{
	printf("'%s': %e," ENDLINE, name, val);
}

void print_str_py(void __unused *b, const char *name, const char *val)
{
	int i, len;
	char *str = strdup(val);
	len = strlen(str);
	/* FIXME workaround: replace \n \r by '?' */
	for (i = 0; i < len; i++) {
		if (str[i]=='\n' || str[i]=='\r')
			str[i]='?';
	}
	printf("'%s': '%s'," ENDLINE, name, str);
	free(str);
}

void print_time_py(void __unused *b, const char *name, const uint64_t val)
{
	struct time_s {
		uint32_t sec;
		uint32_t usec;
	} *t;

	t = (struct time_s *)&val;
	printf("'%s': %8u%09u," ENDLINE, name, t->sec, t->usec);
}

void print_msg_hdr_py(struct msg_hdr *msg_hdr, void __unused *b)
{
	printf("'msg_id': 0x%05x, 'seq_num': %d, 'time': %8u%09u, 'payload_len': %d,",
	       msg_hdr->msg_id, msg_hdr->seq_num,
	       msg_hdr->sec, msg_hdr->usec,
	       msg_hdr->len);
}

#define parse_and_pr_arr(TYPE)\
char *parse_and_print_array ## _ ## TYPE ## _py(char *p, char tp, const char *format)\
{\
	uint32_t i;\
	uint64_t pp;\
	uint32_t d;\
\
	pp = *(uint64_t *)p;\
	p += sizeof(pp);\
\
	d = *(uint32_t *)p;\
	p += sizeof(d);\
\
	char *buf = malloc(d * 20 + 1024);\
	char *pb = buf;\
	pb += sprintf(pb, "  %c[%d]: %llx = { ", tp, d, (long long unsigned int)pp);\
\
	for ( i = 1; i <= d; i++) {\
		pb += sprintf(pb, format, *(TYPE *)p);\
		p += sizeof(TYPE);\
	}\
	sprintf(pb-1, " }");\
\
	printf_py("%s\n", buf);\
	free(buf);\
\
	return p;\
}

parse_and_pr_arr(float);
parse_and_pr_arr(uint32_t);


char *parse_and_print_value_by_type_py(char *p, char *add, void __unused *b)
{
	uint8_t c;
	uint32_t d;
	uint64_t x;
	uint64_t pp;
	float f;
	double w;
	char *s;
	int i, len;

	char t = *p++;

	printf("'%s_type': '%c'," ENDLINE, add, t);
	printf("'%s_val':", add);
	switch (t) {
	case 'b':
		c = *p;
		printf("%d," ENDLINE, (int)c);
		p += sizeof(c);
		break;
	case 'c':
		c = *p;
		printf("%c," ENDLINE, c);
		p += sizeof(c);
		break;
	case 'd':
		d = *(uint32_t *)p;
		printf("%i," ENDLINE, d);
		p += sizeof(d);
		break;
	case 'x':
		x = *(uint64_t *)p;
		printf("0x%llx," ENDLINE, (long long unsigned int)x);
		p += sizeof(x);
		break;
	case 'p':
		pp = *(uint64_t *)p;
		printf("0x%llx," ENDLINE, (long long unsigned int)pp);
		p += sizeof(pp);
		break;
	case 'f':
		f = *(float *)p;
		printf("%f," ENDLINE, f);
		p += sizeof(f);
		break;
	case 'w':
		w = *(double *)p;
		printf("%e," ENDLINE, w);
		p += sizeof(w);
		break;
	case 's':
		s = strdup(p);
		len = strlen(s);
		/* FIXME workaround: replace \n \r by '?' */
		for (i = 0; i < len; i++)
			if (s[i] == '\n' || s[i] == '\r')
				s[i] = '?';
		printf("'%s'," ENDLINE, s);
		p += strlen(s) + 1;
		free(s);
		break;
	case 'v':
	case 'n':
		printf("None," ENDLINE);
		break;
	case 'F':
		p = parse_and_print_array_float_py(p, t, "%f, ");
		break;
	case 'D':
		p = parse_and_print_array_uint32_t_py(p, t, "%d, ");
		break;

	default:
		printf_py("  unknown (%c)", t);
		break;
	}

	return p;
}

char *parse_and_print_args_py(char *buf, void __unused *b)
{
	char *p = buf;
	int i = 0;
	int args_num = 0;
	char tmp[256];

	SANITY_CHECK(buf)


	printf("'args_num': %d," ENDLINE, *(uint32_t *)p);

	start_object_py(b, "args");

	args_num = *(uint32_t *)p;
	p += sizeof(uint32_t);

	for (i = 0; i < args_num; i++) {
		sprintf(tmp, "arg_%d", i);
		p = parse_and_print_value_by_type_py(p, tmp, b);
	}

	finish_object_py(b, "args");

	return p;
}

char *parse_and_print_return_py(char *buf, void __unused *b)
{
	char *p = buf;
	char tmp[256] = "return";

	SANITY_CHECK(buf)

	p = parse_and_print_value_by_type_py(p, tmp, b);

	return p;
}

void start_array_py(void __unused *b, const char __unused *name)
{
	printf("'%s': {", name);
}

void finish_array_py(void __unused *b)
{
	printf("}," ENDLINE);
}

void start_object_py(void __unused *b, const char __unused *name)
{
	/* TODO make it pretty */
	if (strcmp(name, "payload") == 0)
		return;

	if ((strcmp(name, "msg_header") == 0) ||
	    (strcmp(name, "uihv_object") == 0) ||
	    (strcmp(name, "") == 0))
		printf("{");
	else if (strcmp(name, "uihv_list") == 0)
		printf("%s = {", name);
	else if ((strcmp(name, "uihv_objects_list") == 0))
		printf("'%s': [", name);
	else
		printf("'%s': {", name);
}

void finish_object_py(void __unused *b, const char __unused *name)
{
	/* TODO make it pretty */
	if ((strcmp(name, "msg_header") == 0))
		return;

	if ((strcmp(name, "uihv_objects_list") == 0))
		printf("],\n");
	else
		printf("},\n");
}

void print_py_buf(__unused char *buf, __unused int len, __unused const char *info)
{
}

void start_py_file(void)
{
}

void finish_py_file(void)
{
}

static struct conversion_base py_conversion = {
	.start_file = start_py_file,
	.finish_file = finish_py_file,


	.print_int = print_int_py,
	.print_long = print_long_py,
	.print_addr = print_long_addr_py,
	.print_float = print_float_py,
	.print_double = print_double_py,
	.print_str = print_str_py,
	.print_time = print_time_py,

	.print_buf = print_py_buf,
	.start_array = start_array_py,
	.finish_array = finish_array_py,
	.start_object = start_object_py,
	.finish_object = finish_object_py,

	.parse_and_print_args = parse_and_print_args_py,
	.parse_and_print_return = parse_and_print_return_py,
	.print_msg_hdr = print_msg_hdr_py,
};
static inline int xfeof(FILE *fp)
{
	ungetc(getc(fp), fp);
	return feof(fp);
}

static inline void *xrealloc(void *p, size_t size)
{
	if (size == 0) {
		printf_py("Ask for 0 bytes?!");
		return NULL;
	} else {
		void *result = realloc(p, size);
		if (!result) {
			printf_py("Fatal: failed to alloc %u memory",
				   (unsigned int) size);
			exit(1);
		}
		return result;
	};
}


#define static_assert(p) do { char __attribute__ ((unused)) __static_asser[(p)?1:-1];} while (0)

int py_main(char __unused *buf, FILE *fd, struct parse_config_t *conf)
{
	void *buffer = NULL;

	printf("trace_info = {\n");
	conf->conv_base->print_int(NULL, "protocol_version", (const uint32_t)get_version_number());
	printf("\n}\n");

	printf("trace_obj = [\n");

	while (!xfeof(fd)) {
		const void *b = (void *)0xDEADBEEF;
		struct msg_hdr msg_hdr;

		static_assert(sizeof(msg_hdr) == MSG_HDR_LEN);
		if (fread(&msg_hdr, sizeof(msg_hdr), 1, fd) != 1) {
			printf_py("non complete header!");
			break;
		}

		// TODO msh header for MSG_COMPRESSED will be changed
		// time willbe removed from header

		if (!check_id(msg_hdr.msg_id)) {
			buffer = xrealloc(buffer, msg_hdr.len);
			msg_end = buffer + msg_hdr.len;

			if (fread(buffer, 1, msg_hdr.len, fd) != msg_hdr.len) {
				printf_py("wrong len [%lu: %d]", ftell(fd), 0);
				break;
			}
			continue;
		}


		buffer = xrealloc(buffer, msg_hdr.len);
		msg_end = buffer + msg_hdr.len;

		if (fread(buffer, 1, msg_hdr.len, fd) != msg_hdr.len) {
			printf_py("wrong len [%lu: %d]", ftell(fd), 0 );
			break;
		}

		if (!need_to_print_msg_id(msg_hdr.msg_id))
			continue;

		//conv_base->print_msg_hdr(&msg_hdr, (void *)b);
		parse_and_print_msg_header(&msg_hdr, (void *)b, conf->conv_base);
		parse_and_print_msg_payload(buffer, &msg_hdr, (void *)b, conf->conv_base);

	}
	printf("]\n");

	free(buffer);
	return 0;
}

int init_py(struct parse_config_t *conf) {
	printf_py("init_py");
	if (conf->main_func == NULL)
		conf->main_func = py_main;
	else
		printf_py("main_func allready seted");

	conf->conv_base = &py_conversion;
	conf->log = &printf_py;
	return 0;
}

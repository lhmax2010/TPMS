
#include "trace_parser.h"

#include <stdarg.h>
#define ENDLINE ""

void start_object_json(void __unused *b, const char __unused *name);
void finish_object_json(void __unused *b, const char __unused *name);

int printf_json(const char *format, ...)
{
	int val = 0;
	va_list ap;

	va_start(ap, format);
	/* printf("\n# "); */
	/* val = vprintf(format, ap); */
	/* printf("\n"); */
	va_end(ap);

	return val;
}

/* Should be dropped to 1 after every '[' or '{' */
static int first_element = 1;

int print_element_json(const char *format, ...)
{
	int val = 0;
	va_list ap;
	va_start(ap, format);
	if (first_element) {
		first_element = 0;
	} else {
		printf(", ");
	}
	val = vprintf(format, ap);
	va_end(ap);

	return val;
}

void print_int_json(void __unused *b, const char *name, const uint32_t val)
{
	print_element_json("\"%s\": %u" ENDLINE, name, val);
}

void print_long_addr_json(void __unused *b, const char *name, const uint64_t val)
{
	print_element_json("\"%s\": %llu" ENDLINE, name, (unsigned long long)val);
}

void print_long_json(void __unused *b, const char *name, const uint64_t val)
{
	print_element_json("\"%s\": %lu" ENDLINE, name, (unsigned long)val);
}

void print_float_json(void __unused *b, const char *name, const float val)
{
	print_element_json("\"%s\": %f" ENDLINE, name, val);
}

void print_double_json(void __unused *b, const char *name, const double val)
{
	print_element_json("\"%s\": %e" ENDLINE, name, val);
}

void print_str_json(void __unused *b, const char *name, const char *val)
{
	int i, len;
	char *str = strdup(val);
	len = strlen(str);
	/* FIXME workaround: replace \n \r by '?' */
	for (i = 0; i < len; i++) {
		if (str[i]=='\n' || str[i]=='\r')
			str[i]='?';
	}
	print_element_json("\"%s\": \"%s\"" ENDLINE, name, str);
	free(str);
}

void print_time_json(void __unused *b, const char *name, const uint64_t val)
{
	struct time_s {
		uint32_t sec;
		uint32_t usec;
	} *t;

	t = (struct time_s *)&val;
	if (t->sec == 0)
		print_element_json("\"%s\": %u" ENDLINE, name, t->usec);
	else
		print_element_json("\"%s\": %u%09u" ENDLINE, name, t->sec, t->usec);
}

void print_msg_hdr_json(struct msg_hdr *msg_hdr, void __unused *b)
{
	if (msg_hdr->sec == 0)
		print_element_json("\"msg_id\": %d, \"seq_num\": %d, \"time\": %u, \"payload_len\": %d",
				   msg_hdr->msg_id, msg_hdr->seq_num,
				   msg_hdr->usec,
				   msg_hdr->len);
	else
		print_element_json("\"msg_id\": %d, \"seq_num\": %d, \"time\": %u%09u, \"payload_len\": %d",
				   msg_hdr->msg_id, msg_hdr->seq_num,
				   msg_hdr->sec, msg_hdr->usec,
				   msg_hdr->len);
}

#define parse_and_pr_arr(TYPE)\
char *parse_and_print_array ## _ ## TYPE ## _json(char *p, __unused char tp, const char *format)\
{\
	uint32_t i;\
	uint64_t pp;\
	uint32_t d;\
\
	int first;\
\
	pp = *(uint64_t *)p;\
	p += sizeof(pp);\
\
	d = *(uint32_t *)p;\
	p += sizeof(d);\
\
	char *buf = malloc(d * 20 + 1024);\
	char *pb = buf;\
/*	if (first_element) {			\
		first_element = 0;\
	} else {\
		pb += sprintf(pb, ",  ");\
		}*/\
	pb += sprintf(pb, "[ ");\
	first = 1; \
\
	for ( i = 1; i <= d; i++) {\
		if (first){\
			first = 0;\
		} else {\
			pb += sprintf(pb, ", ");\
			first = 0;\
		}\
		pb += sprintf(pb, format, *(TYPE *)p);\
		p += sizeof(TYPE);\
	}\
	sprintf(pb-1, " ]");\
\
	printf("%s", buf);\
	free(buf);\
\
	return p;\
}

parse_and_pr_arr(float);
parse_and_pr_arr(uint32_t);


char *parse_and_print_value_by_type_json(char *p, char *add, void __unused *b)
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

	if (first_element) {
		first_element = 0;
	} else {
		printf(",  ");
	}
	printf("\"%s_type\": \"%c\", " ENDLINE, add, t);
	printf("\"%s_val\": ", add);
	switch (t) {
	case 'b':
		c = *p;
		printf("%d" ENDLINE, (int)c);
		p += sizeof(c);
		break;
	case 'c':
		c = *p;
		printf("%c" ENDLINE, c);
		p += sizeof(c);
		break;
	case 'd':
		d = *(uint32_t *)p;
		printf("%i" ENDLINE, d);
		p += sizeof(d);
		break;
	case 'x':
		x = *(uint64_t *)p;
		printf("%lld" ENDLINE, (long long unsigned int)x);
		p += sizeof(x);
		break;
	case 'p':
		pp = *(uint64_t *)p;
		printf("%lld" ENDLINE, (long long unsigned int)pp);
		p += sizeof(pp);
		break;
	case 'f':
		f = *(float *)p;
		printf("%f" ENDLINE, f);
		p += sizeof(f);
		break;
	case 'w':
		w = *(double *)p;
		printf("%e" ENDLINE, w);
		p += sizeof(w);
		break;
	case 's':
		s = strdup(p);
		len = strlen(s);
		/* FIXME workaround: replace \n \r by '?' */
		for (i = 0; i < len; i++)
			if (s[i] == '\n' || s[i] == '\r')
				s[i] = '?';
		printf("\"%s\"" ENDLINE, s);
		p += strlen(s) + 1;
		free(s);
		break;
	case 'v':
	case 'n':
		printf("null" ENDLINE);
		break;
	case 'F':
		p = parse_and_print_array_float_json(p, t, "%f");
		break;
	case 'D':
		p = parse_and_print_array_uint32_t_json(p, t, "%d");
		break;

	default:
		printf_json("  unknown (%c)", t);
		break;
	}

	return p;
}

char *parse_and_print_args_json(char *buf, void __unused *b)
{
	char *p = buf;
	int i = 0;
	int args_num = 0;
	char tmp[256];

	SANITY_CHECK(buf)


	print_element_json("\"args_num\": %d" ENDLINE, *(uint32_t *)p);

	start_object_json(b, "args");

	args_num = *(uint32_t *)p;
	p += sizeof(uint32_t);

	for (i = 0; i < args_num; i++) {
		sprintf(tmp, "arg_%d", i);
		p = parse_and_print_value_by_type_json(p, tmp, b);
	}

	finish_object_json(b, "args");

	return p;
}

char *parse_and_print_return_json(char *buf, void __unused *b)
{
	char *p = buf;
	char tmp[256] = "return";

	SANITY_CHECK(buf)

	p = parse_and_print_value_by_type_json(p, tmp, b);

	return p;
}

void start_array_json(void __unused *b, const char __unused *name)
{
	print_element_json("\"%s\": {", name);
	first_element = 1;
}

void finish_array_json(void __unused *b)
{
	printf("}" ENDLINE);

	first_element = 0; // in case of blank array it's need to be updated
}

void start_object_json(void __unused *b, const char __unused *name)
{
	/* TODO make it pretty */
	if (strcmp(name, "payload") == 0)
		return;

	if ((strcmp(name, "msg_header") == 0) ||
	    (strcmp(name, "uihv_object") == 0) ||
	    (strcmp(name, "") == 0)) {
		print_element_json("{");
		first_element = 1;
	} else if (strcmp(name, "uihv_list") == 0) {
		print_element_json("\"%s\": {", name);
		first_element = 1;
	} else if ((strcmp(name, "uihv_objects_list") == 0)) {
		print_element_json("\"%s\": [", name);
		first_element = 1;
	} else {
		print_element_json("\"%s\": {", name);
		first_element = 1;
	}
}

void finish_object_json(void __unused *b, const char __unused *name)
{
	/* TODO make it pretty */
	if ((strcmp(name, "msg_header") == 0))
		return;

	if ((strcmp(name, "uihv_objects_list") == 0))
		printf("]\n");
	else
		printf("}\n");

	first_element = 0; // in case of blank array it's need to be updated
}

void print_json_buf(__unused char *buf, __unused int len, __unused const char *info)
{
}

void start_json_file(void)
{
	printf("{\n");
	/* first_element = 1; */
}

void finish_json_file(void)
{
	printf("}\n");
}

static struct conversion_base json_conversion = {
	.start_file = start_json_file,
	.finish_file = finish_json_file,

	.print_int = print_int_json,
	.print_long = print_long_json,
	.print_addr = print_long_addr_json,
	.print_float = print_float_json,
	.print_double = print_double_json,
	.print_str = print_str_json,
	.print_time = print_time_json,

	.print_buf = print_json_buf,
	.start_array = start_array_json,
	.finish_array = finish_array_json,
	.start_object = start_object_json,
	.finish_object = finish_object_json,

	.parse_and_print_args = parse_and_print_args_json,
	.parse_and_print_return = parse_and_print_return_json,
	.print_msg_hdr = print_msg_hdr_json,
};
static inline int xfeof(FILE *fp)
{
	ungetc(getc(fp), fp);
	return feof(fp);
}

static inline void *xrealloc(void *p, size_t size)
{
	if (size == 0) {
		printf_json("Ask for 0 bytes?!");
		return NULL;
	} else {
		void *result = realloc(p, size);
		if (!result) {
			printf_json("Fatal: failed to alloc %u memory",
				   (unsigned int) size);
			exit(1);
		}
		return result;
	};
}


#define static_assert(p) do { char __attribute__ ((unused)) __static_asser[(p)?1:-1];} while (0)

int json_main(char __unused *buf, FILE *fd, struct parse_config_t *conf)
{
	void *buffer = NULL;

	start_json_file();
	printf("\"trace_info\" : {\n");
	first_element = 1;
	conf->conv_base->print_int(NULL, "protocol_version", (const uint32_t)get_version_number());
	printf("\n},\n");

	printf("\"trace_obj\" : [\n");
	first_element = 1;

	while (!xfeof(fd)) {
		const void *b = (void *)0xDEADBEEF;
		struct msg_hdr msg_hdr;

		static_assert(sizeof(msg_hdr) == MSG_HDR_LEN);
		if (fread(&msg_hdr, sizeof(msg_hdr), 1, fd) != 1) {
			printf_json("non complete header!");
			break;
		}

		// TODO msh header for MSG_COMPRESSED will be changed
		// time willbe removed from header

		if (!check_id(msg_hdr.msg_id)) {
			buffer = xrealloc(buffer, msg_hdr.len);
			msg_end = buffer + msg_hdr.len;

			if (fread(buffer, 1, msg_hdr.len, fd) != msg_hdr.len) {
				printf_json("wrong len [%lu: %d]", ftell(fd), 0);
				break;
			}
			continue;
		}


		buffer = xrealloc(buffer, msg_hdr.len);
		msg_end = buffer + msg_hdr.len;

		if (fread(buffer, 1, msg_hdr.len, fd) != msg_hdr.len) {
			printf_json("wrong len [%lu: %d]", ftell(fd), 0 );
			break;
		}

		if (!need_to_print_msg_id(msg_hdr.msg_id))
			continue;

		//conv_base->print_msg_hdr(&msg_hdr, (void *)b);
		parse_and_print_msg_header(&msg_hdr, (void *)b, conf->conv_base);
		parse_and_print_msg_payload(buffer, &msg_hdr, (void *)b, conf->conv_base);

	}
	printf("]\n");
	finish_json_file();

	free(buffer);
	return 0;
}

int init_json(struct parse_config_t *conf) {
	printf_json("init_json");
	if (conf->main_func == NULL)
		conf->main_func = json_main;
	else
		printf_json("main_func allready seted");

	conf->conv_base = &json_conversion;
	conf->log = &printf_json;
	return 0;
}

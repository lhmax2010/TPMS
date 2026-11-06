
#include "trace_parser.h"

#ifdef MSG_WITH_NAMES
#include "protocol_v3_0.h"
#include "protocol_v4_0.h"

static const char *msg_id2name40(int id)
{
	enum msg_id_v4_0 eid = (enum msg_id_v4_0)id;
#define X(id, val) case val: return #id;
	switch (eid) {
		MSG_ID_LIST40
	}
#undef X
	return NULL;
}

static const char *msg_id2name30(int id)
{
	enum msg_id_v3_0 eid = (enum msg_id_v3_0)id;
#define X(id, val) case val: return #id;
	switch (eid) {
		MSG_ID_LIST30
	}
#undef X
	return NULL;
}
#endif

void print_int_text(void __unused *b, const char *name, const uint32_t val)
{
	printf("%s = %u\n", name, val);
}

void print_long_addr_text(void __unused *b, const char *name, const uint64_t val)
{
	printf("%s = 0x%016llx\n", name, (unsigned long long)val);
}

void print_long_text(void __unused *b, const char *name, const uint64_t val)
{
	printf("%s = %lu (0x%lx)\n", name, (unsigned long)val, (unsigned long)val);
}

void print_float_text(void __unused *b, const char *name, const float val)
{
	printf("%s = %f\n", name, val);
}

void print_double_text(void __unused *b, const char *name, const double val)
{
	printf("%s = %e\n", name, val);
}

void print_str_text(void __unused *b, const char *name, const char *val)
{
	printf("%s = %s\n", name, val);
}

void print_time_text(void __unused *b, const char *name, const uint64_t val)
{
	struct time_s {
		uint32_t sec;
		uint32_t usec;
	} *t;

	t = (struct time_s *)&val;
	printf("%s: %8u:%09u\n", name, t->sec, t->usec);
}

void print_msg_hdr_text(struct msg_hdr *msg_hdr, void __unused *b)
{
#ifdef MSG_WITH_NAMES
	const char * msg_name = NULL;
	static const char * (* msg_id2name)(int) = NULL;

	if (!msg_id2name)
		switch (get_version_number()) {
		case 40:
			msg_id2name = msg_id2name40;
			break;
		case 30:
			msg_id2name = msg_id2name30;
			break;
		}

	msg_name = msg_id2name(msg_hdr->msg_id);
#endif
	printf("msg_id: 0x%05x, seq_num: %d, time: %8u:%09u, len = %d\n",
		   msg_hdr->msg_id, msg_hdr->seq_num,
		   msg_hdr->sec, msg_hdr->usec,
		   msg_hdr->len);
#ifdef MSG_WITH_NAMES
	printf("msg_name: %s\n", msg_name);
#endif
}

#define parse_and_pr_arr(TYPE)\
char *parse_and_print_array ## _ ## TYPE ## _text(char *p, char tp, const char *format)\
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
	printf("%s\n", buf);\
	free(buf);\
\
	return p;\
}

parse_and_pr_arr(float);
parse_and_pr_arr(uint32_t);


char *parse_and_print_value_by_type_text(char *p, void __unused *b)
{
	uint8_t c;
	uint32_t d;
	uint64_t x;
	uint64_t pp;
	float f;
	double w;
	char *s;

	char t = *p++;

	switch (t) {
	case 'b':
		c = *p;
		printf("  b = %d\n", (int)c);
		p += sizeof(c);
		break;
	case 'c':
		c = *p;
		printf("  c = %c\n", c);
		p += sizeof(c);
		break;
	case 'd':
		d = *(uint32_t *)p;
		printf("  d = %i\n", d);
		p += sizeof(d);
		break;
	case 'x':
		x = *(uint64_t *)p;
		printf("  x = %llx\n", (long long unsigned int)x);
		p += sizeof(x);
		break;
	case 'p':
		pp = *(uint64_t *)p;
		printf("  p = %llx\n", (long long unsigned int)pp);
		p += sizeof(pp);
		break;
	case 'f':
		f = *(float *)p;
		printf("  f = %f\n", f);
		p += sizeof(f);
		break;
	case 'w':
		w = *(double *)p;
		printf("  w = %e\n", w);
		p += sizeof(w);
		break;
	case 's':
		s = p;
		printf("  s = %s\n", s);
		p += strlen(s) + 1;
		break;
	case 'v':
	case 'n':
		break;
	case 'F':
		p = parse_and_print_array_float_text(p, t, "%f, ");
		break;
	case 'D':
		p = parse_and_print_array_uint32_t_text(p, t, "%d, ");
		break;

	default:
		printf("  unknown (%c)\n", t);
		break;
	}

	return p;
}

char *parse_and_print_args_text(char *buf, void __unused *b)
{
	char *p = buf;
	int i = 0;
	int args_num = 0;

	SANITY_CHECK(buf)

	printf("args_num = %d\n", *(uint32_t *)p);
	args_num = *(uint32_t *)p;
	p += sizeof(uint32_t);

	for (i = 0; i < args_num; i++) {
		p = parse_and_print_value_by_type_text(p, b);
	}

	return p;
}

char *parse_and_print_return_text(char *buf, void __unused *b)
{
	char *p = buf;

	SANITY_CHECK(buf)

	printf("return: #%d %c\n", *p, *p);
	p = parse_and_print_value_by_type_text(p, b);

	return p;
}

void print_text_buf(char *buf, int len, const char *info)
{
	int i,j;
	char local_buf[3*16 + 2*16 + 1 + 8];
	char * p1, * p2;

	printf_deb("BUFFER [%d] <%s>:\n", len, info);
	for ( i = 0; i < len/16 + 1; i++)
	{
		memset(local_buf, ' ', 5*16 + 8);

		sprintf(local_buf, "0x%04X: ", i);
		p1 = local_buf + 8;
		p2 = local_buf + 8 + 3*17;
		for ( j = 0; j < 16; j++)
			if (i*16+j < len )
			{
				sprintf(p1, "%02X ",(unsigned char) *buf);
				p1+=3;
				if (isprint( *buf)){
					sprintf(p2, "%c ",(int)*buf);
				}else{
					sprintf(p2,". ");
				}
				p2+=2;
				buf++;
			}
		*p1 = ' ';
		*p2 = '\0';
		printf_deb("%s\n",local_buf);
	}
}

void start_text_file(void)
{
}

void finish_text_file(void)
{
}

void start_array_text(void __unused *b, const char __unused *name) {}
void finish_array_text(void __unused *b) {}
void start_object_text(void __unused *b, const char __unused *name) {}
void finish_object_text(void __unused *b, const char __unused *name) {}

static struct conversion_base text_conversion = {
	.start_file = start_text_file,
	.finish_file = finish_text_file,


	.print_int = print_int_text,
	.print_long = print_long_text,
	.print_addr = print_long_addr_text,
	.print_float = print_float_text,
	.print_double = print_double_text,
	.print_str = print_str_text,
	.print_time = print_time_text,

	.print_buf = print_text_buf,
	.start_array = start_array_text,
	.finish_array = finish_array_text,
	.start_object = start_object_text,
	.finish_object = finish_object_text,

	.parse_and_print_args = parse_and_print_args_text,
	.parse_and_print_return = parse_and_print_return_text,
	.print_msg_hdr = print_msg_hdr_text,
};
static inline int xfeof(FILE *fp)
{
	ungetc(getc(fp), fp);
	return feof(fp);
}

static inline void *xrealloc(void *p, size_t size)
{
	if (size == 0) {
		printf_deb("Ask for 0 bytes?!\n");
		return NULL;
	} else {
		void *result = realloc(p, size);
		if (!result) {
			printf_deb("Fatal: failed to alloc %u memory\n",
				   (unsigned int) size);
			exit(1);
		}
		return result;
	};
}

#define static_assert(p) do { char __attribute__ ((unused)) __static_asser[(p)?1:-1];} while (0)

int text_main(char __unused *buf, FILE *fd, struct parse_config_t *conf)
{
	void *buffer = NULL;
	while (!xfeof(fd)) {
		const void *b = (void *)0xDEADBEEF;
		struct msg_hdr msg_hdr;
		static_assert(sizeof(msg_hdr) == MSG_HDR_LEN);
		//printf_deb("File offset: %ld == 0x%lx\n", ftell(fd), ftell(fd));
		if (fread(&msg_hdr, sizeof(msg_hdr), 1, fd) != 1) {
			printf_deb("non complete header!\n");
			break;
		}

		// TODO msh header for MSG_COMPRESSED will be changed
		// time willbe removed from header

		if (!check_id(msg_hdr.msg_id)) {
			buffer = xrealloc(buffer, msg_hdr.len);
			msg_end = buffer + msg_hdr.len;

			if (fread(buffer, 1, msg_hdr.len, fd) != msg_hdr.len) {
				printf_deb("wrong len [%lu: %d]\n", ftell(fd), 0);
				break;
			}
			continue;
		}


		buffer = xrealloc(buffer, msg_hdr.len);
		msg_end = buffer + msg_hdr.len;

		if (fread(buffer, 1, msg_hdr.len, fd) != msg_hdr.len) {
			printf_deb("wrong len [%lu: %d]\n", ftell(fd), 0 );
			break;
		}

		if (!need_to_print_msg_id(msg_hdr.msg_id))
			continue;

		//conv_base->print_msg_hdr(&msg_hdr, (void *)b);
		parse_and_print_msg_header(&msg_hdr, (void *)b, conf->conv_base);
		parse_and_print_msg_payload(buffer, &msg_hdr, (void *)b, conf->conv_base);

		if (bin_mode) {
			put_line('-');
			print_text_buf(buffer, msg_hdr.len, "");
		}
		put_line('=');
	}

	free(buffer);
	return 0;
}



int init_text(struct parse_config_t *conf) {
	if (conf->main_func == NULL)
		conf->main_func = text_main;
	else
		printf_deb("main_func allready seted\n");

	conf->conv_base = &text_conversion;
	return 0;
}

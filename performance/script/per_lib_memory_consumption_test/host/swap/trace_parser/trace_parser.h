#ifndef __TRACE_PARSER_H__
#define __TRACE_PARSER_H__

#include <stdio.h>

#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>

//#include "api_id_list.h"
//#include "fd_api_list.h"
//#include <arpa/inet.h>
#include <ctype.h>

#define MSG_HDR_LEN 20

#ifdef FILTER
#define check_id(x) (x == FILTER || x == MSG_PROCESS_INFO)
#else
#define check_id(...) (1 == 1)
#endif


#define __unused __attribute__((unused))

struct msg_hdr {
	union {
		uint32_t msg_id;
		uint32_t _align_enforce;
	};
	uint32_t seq_num;
	uint32_t sec;
	uint32_t usec;
	uint32_t len;
};


struct conversion_base {
	void (*start_file)(void);
	void (*finish_file)(void);

	void (*print_int)(void *, const char *, const uint32_t);
	void (*print_long)(void *, const char *, const uint64_t);
	void (*print_addr)(void *, const char *, const uint64_t);
	void (*print_float)(void *, const char *, const float);
	void (*print_double)(void *, const char *, const double);
	void (*print_str)(void *, const char *, const char *);
	void (*print_time)(void *, const char *, const uint64_t);

	void (*print_buf)(char *, int, const char *);
	void (*start_array)(void *, const char *);
	void (*finish_array)(void *);
	void (*start_object)(void *, const char *);
	void (*finish_object)(void *, const char *);

	void (*print_msg_hdr)(struct msg_hdr *, void *);
	char * (*parse_and_print_args)(char *, void *);
	char * (*parse_and_print_return)(char *, void *);

//	char *parse_and_print_probe_common(char *buf, void *b, const struct conversion_base *conv_base)
};

typedef void (*parse_and_print_f) (char *buf, void *b,
				   const struct conversion_base *conv_base);

#define SANITY_CHECK(p) sanity_check(p);
void sanity_check(const void *p);

typedef int (*log_t)(const char *format, ...);

struct parse_config_t {
	int (*main_func)(char *buf, FILE * fd, struct parse_config_t *conv_base);
	log_t log;
	struct conversion_base *conv_base;
};

extern struct parse_config_t parse_config;
extern char *msg_end;
extern int bin_mode;

int get_version_number(void);

uint8_t need_to_print_msg_id(uint32_t id);

void parse_and_print_msg_payload(char *buf,
				 const struct msg_hdr *msg_hdr,
				 void *b,
				 const struct conversion_base *conv_base);

void parse_and_print_msg_header(const struct msg_hdr *msg_hdr,
				void *b,
				const struct conversion_base *conv_base);

void put_line(char c);
void print_buf(char *buf, int len, const char *info);
char *parse_msg_hdr(char *p, struct msg_hdr *msg_hdr);

#define printf_deb(...) do {		\
fprintf(stderr, "%s +%d:", __FUNCTION__, __LINE__);	\
fprintf(stderr, __VA_ARGS__);				\
} while (0)

int init_text(struct parse_config_t *conf);
int init_bson(struct parse_config_t *conf);
int init_table(struct parse_config_t *conf);
int init_json(struct parse_config_t *conf);
int init_py(struct parse_config_t *conf);
int init_uihv(struct parse_config_t *conf);


void register_parser(uint32_t id, parse_and_print_f callback);
#endif /* __TRACE_PARSER_H__ */

